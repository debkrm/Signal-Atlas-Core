"""Portfolio Valuation, Position Management, and Risk Tracker.

Enforces:
- Exact Decimal portfolio valuation and mark-to-market accounting.
- Multi-instrument position tracking integrated with CashLedger.
- Statutory Indian transaction cost deductions and contract-note reconciliation.
- Risk limits: max single-position concentration limit and portfolio drawdown monitoring.
"""

from collections import OrderedDict
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.order_types import ExecutionFillResult, FillStatus, OrderSide
from signal_core.portfolio.ledger import CashLedger, PAISE_PRECISION, _quantize_paise
from signal_core.portfolio.position import Position
from signal_core.portfolio.types import (
    CashLedgerEntry,
    CorporateActionError,
    LedgerValidationError,
    PortfolioRiskLimitError,
    PortfolioSnapshot,
    PositionSnapshot,
)
from signal_core.storage.security_master import CorporateAction, CorporateActionType

DRAWDOWN_PRECISION = Decimal("0.0001")


class Portfolio:
    """
    Authoritative Portfolio Accounting Engine.
    
    Coordinates the single-entry CashLedger / cash book, multi-instrument open positions,
    mark-to-market session valuations, and committed Go/No-Go risk limits.

    Replay Protection Scope (N-9):
    In-memory fill instances without explicit identifiers (fill_id or reference_id) are
    protected against replay within a bounded window of the most recent 10,000 fills
    (_max_pinned_instances). Fills bearing persistent identifiers (fill_id or caller reference_id)
    are protected indefinitely via ledger reference uniqueness.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("0.00"),
        criteria: Optional[GoNoGoCriteria] = None,
        allow_overdraft: bool = False,
        initial_date: Optional[datetime.date] = None,
    ) -> None:
        if isinstance(initial_capital, bool) or not isinstance(initial_capital, Decimal) or not initial_capital.is_finite() or initial_capital < 0:
            raise LedgerValidationError(f"initial_capital must be non-negative Decimal, got {initial_capital!r}")

        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._ledger = CashLedger(
            initial_capital=initial_capital,
            allow_overdraft=allow_overdraft,
            initial_date=initial_date,
        )
        self._positions: Dict[str, Position] = {}
        self._processed_fill_instances: OrderedDict[int, ExecutionFillResult] = OrderedDict()
        self._max_pinned_instances: int = 10000
        self._peak_portfolio_value: Decimal = _quantize_paise(initial_capital)
        self._current_drawdown: Decimal = Decimal("0.00")
        self._max_drawdown: Decimal = Decimal("0.00")
        self._drawdown_duration_sessions: int = 0
        self._snapshots: List[PortfolioSnapshot] = []
        self._last_valuation_date: Optional[datetime.date] = None

    @property
    def ledger(self) -> CashLedger:
        return self._ledger

    @property
    def criteria(self) -> GoNoGoCriteria:
        return self._criteria

    @property
    def current_cash(self) -> Decimal:
        return self._ledger.current_cash

    @property
    def peak_portfolio_value(self) -> Decimal:
        return self._peak_portfolio_value

    @property
    def current_drawdown(self) -> Decimal:
        return self._current_drawdown

    @property
    def max_drawdown(self) -> Decimal:
        return self._max_drawdown

    @property
    def drawdown_duration_sessions(self) -> int:
        return self._drawdown_duration_sessions

    @property
    def snapshots(self) -> Tuple[PortfolioSnapshot, ...]:
        return tuple(self._snapshots)

    @property
    def is_max_drawdown_breached(self) -> bool:
        """Evaluates whether observed max drawdown breaches committed criteria threshold."""
        return self._max_drawdown > self._criteria.max_portfolio_drawdown

    @property
    def is_drawdown_duration_breached(self) -> bool:
        """Evaluates whether consecutive drawdown duration breaches committed criteria threshold."""
        return self._drawdown_duration_sessions > self._criteria.max_drawdown_duration_sessions

    def get_position(self, instrument_id: str) -> Optional[Position]:
        """Returns the Position for the instrument, or None if no trades have occurred."""
        return self._positions.get(instrument_id)

    def get_open_positions(self) -> Dict[str, Position]:
        """Returns a dictionary of all currently active (non-zero quantity) positions."""
        return {inst_id: pos for inst_id, pos in self._positions.items() if not pos.is_closed}

    def require_hold_bounds(
        self,
        as_of: datetime.date,
        max_hold_trading_sessions: int,
        calendar: Any,
    ) -> Dict[str, str]:
        """
        Refuses every open position whose hold reaches `max_hold_trading_sessions` (Audit §91.9
        item 1, AGENTS.md §13.2). Returns each refused ISIN beside the refusal, so the session loop
        can exit it through the same simulator instead of carrying it in silence.

        The bound is passed in from the criteria; there is no module default (§10.8). A bid locked at
        the lower circuit leaves the position open, and it is refused again on the next session: an
        unbounded exit delay is a refusal, never an extension (§5.3).
        """
        refusals: Dict[str, str] = {}
        for isin, pos in self.get_open_positions().items():
            try:
                pos.require_within_hold_bound(as_of, max_hold_trading_sessions, calendar)
            except LedgerValidationError as exc:
                refusals[isin] = str(exc)
        return refusals

    def deposit(
        self,
        trade_date: datetime.date,
        amount: Decimal,
        description: str = "Capital Deposit",
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """Deposits capital into the portfolio ledger and adjusts peak portfolio value."""
        entry = self._ledger.deposit(trade_date, amount, description, reference_id)
        self._peak_portfolio_value += entry.amount
        return entry

    def withdraw(
        self,
        trade_date: datetime.date,
        amount: Decimal,
        description: str = "Capital Withdrawal",
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """Withdraws capital from the portfolio ledger and adjusts peak portfolio value."""
        entry = self._ledger.withdraw(trade_date, amount, description, reference_id)
        # entry.amount is negative
        self._peak_portfolio_value = max(Decimal("0.00"), self._peak_portfolio_value + entry.amount)
        return entry

    def apply_corporate_action(
        self,
        action: CorporateAction,
        price_convention: Optional[PriceConvention] = None,
    ) -> Optional[CashLedgerEntry]:
        """
        Applies a mid-hold corporate action across open portfolio positions per AGENTS.md §13.2 and Audit §59.4, §59.7, §60.6, §64.3 (H-108).
        - For SPLIT, BONUS, CONSOLIDATION: restates position shares and average cost basis, keeping equity invariant.
        - For ISIN_TRANSITION: re-keys position identity in self._positions to new_isin, keeping shares and cost constant (Finding H-86).
        - For DIVIDEND: posts cash dividend inflow to CashLedger via CashEntryType.DIVIDEND_INFLOW.
        - Finding H-108: If price_convention is PriceConvention.SPLIT_BONUS_ADJUSTED, refuses (fail closed)
          SPLIT, BONUS, CONSOLIDATION, and ISIN_TRANSITION because price series is already adjusted.
        """
        if not isinstance(action, CorporateAction):
            raise LedgerValidationError(f"Expected CorporateAction, got {type(action)}")

        pos = self.get_position(action.isin)
        if pos is None or pos.is_closed or pos.quantity <= 0:
            return None

        # Finding H-108 / Audit §75.4 H-127: when the price convention is SPLIT_BONUS_ADJUSTED the
        # split/bonus/consolidation ratio is already inside the series, so restating the position by it
        # would divide an entry price the series never multiplied. A split or bonus on the same ISIN is
        # then a no-op; a face-value ISIN transition is still a real event, but an identity-only one:
        # re-key the position 1:1 with quantity, cost basis and average entry price untouched.
        if price_convention == PriceConvention.SPLIT_BONUS_ADJUSTED and action.action_type in (
            CorporateActionType.SPLIT,
            CorporateActionType.BONUS,
            CorporateActionType.CONSOLIDATION,
            CorporateActionType.ISIN_TRANSITION,
        ):
            if action.action_type == CorporateActionType.ISIN_TRANSITION and not action.new_isin:
                raise CorporateActionError(
                    f"ISIN_TRANSITION requires new_isin for {action.isin} (Finding H-86)."
                )
            new_isin = action.new_isin
            if new_isin and new_isin != action.isin:
                if new_isin in self._positions and self._positions[new_isin] is not pos:
                    existing_target = self._positions[new_isin]
                    if not existing_target.is_closed and existing_target.quantity > 0:
                        raise CorporateActionError(
                            f"Cannot re-key {action.isin} to {new_isin} on {action.action_type.value}: "
                            f"target ISIN already has active open position."
                        )
                pos.rekey(new_isin)
                del self._positions[action.isin]
                self._positions[new_isin] = pos
            return None

        # Finding H-86 & H-96: Re-key the position in self._positions whenever new_isin is specified
        if action.action_type == CorporateActionType.ISIN_TRANSITION:
            old_isin = action.isin
            new_isin = action.new_isin
            if not new_isin:
                raise CorporateActionError(
                    f"ISIN_TRANSITION requires new_isin for {old_isin} (Finding H-86)."
                )
            if new_isin in self._positions and self._positions[new_isin] is not pos:
                existing_target = self._positions[new_isin]
                if not existing_target.is_closed and existing_target.quantity > 0:
                    raise CorporateActionError(
                        f"Cannot transition {old_isin} to {new_isin}: target ISIN already has active open position."
                    )
            pos.apply_corporate_action(action)
            del self._positions[old_isin]
            self._positions[new_isin] = pos
            return None

        elif action.action_type in (
            CorporateActionType.SPLIT,
            CorporateActionType.BONUS,
            CorporateActionType.CONSOLIDATION,
            CorporateActionType.RIGHTS,
        ):
            pos.apply_corporate_action(action)
            # Finding H-96 & H-98: If SPLIT/BONUS/CONSOLIDATION/RIGHTS carries new_isin, re-key the portfolio position mapping
            if action.new_isin and action.new_isin != action.isin:
                old_isin = action.isin
                new_isin = action.new_isin
                if new_isin in self._positions and self._positions[new_isin] is not pos:
                    existing_target = self._positions[new_isin]
                    if not existing_target.is_closed and existing_target.quantity > 0:
                        raise CorporateActionError(
                            f"Cannot re-key {old_isin} to {new_isin} on {action.action_type.value}: "
                            f"target ISIN already has active open position (Finding H-96, H-98)."
                        )
                del self._positions[old_isin]
                self._positions[new_isin] = pos
            return None

        elif action.action_type == CorporateActionType.MERGER:
            # Finding H-98 & H-113: Stock merger with new_isin consideration and fractional cash-in-lieu settlement
            old_isin = action.isin
            new_isin = action.new_isin
            if not new_isin:
                raise CorporateActionError(f"MERGER requires new_isin for {old_isin} (Finding H-98).")
            if new_isin in self._positions and self._positions[new_isin] is not pos:
                existing_target = self._positions[new_isin]
                if not existing_target.is_closed and existing_target.quantity > 0:
                    raise CorporateActionError(
                        f"Cannot re-key {old_isin} to {new_isin} on MERGER: "
                        f"target ISIN already has active open position (Finding H-96, H-98)."
                    )
            merger_res = pos.apply_corporate_action(action)
            del self._positions[old_isin]
            if pos.quantity > 0:
                self._positions[new_isin] = pos

            entry = None
            if merger_res is not None:
                frac_shares, frac_cost_basis = merger_res
                if frac_shares > Decimal("0"):
                    # Finding N-112: no silent cost-basis fallback. An unpriced fractional merger
                    # settlement fails closed with CorporateActionError.
                    price = action.delisting_price
                    if price is None:
                        raise CorporateActionError(
                            f"MERGER on {old_isin} settles {frac_shares} fractional shares but carries no "
                            f"consideration price; refusing book-value settlement (Finding N-112)."
                        )
                    cash_amount = _quantize_paise(frac_shares * price)

                    entry = self._ledger.record_merger_cash_in_lieu(
                        trade_date=action.ex_date,
                        instrument_id=old_isin,
                        amount=cash_amount,
                        description=(
                            f"Merger cash-in-lieu settlement for {old_isin} -> {new_isin}: "
                            f"{frac_shares} fractional shares @ ₹{(cash_amount / frac_shares).quantize(Decimal('0.01')) if frac_shares > 0 else Decimal('0.00')}"
                        ),
                        reference_id=f"MERGER_{old_isin}_{action.ex_date.isoformat()}",
                    )
                    # Finding N-112: the settled slice is a disposal at the consideration price, so
                    # its realized PnL is (consideration - removed book basis), keeping the ledger
                    # identity exact and refusing the zero-PnL tautology of a book-value settlement.
                    pos.record_merger_cash_settlement_pnl(cash_amount, frac_cost_basis)
                    self._peak_portfolio_value = max(self._peak_portfolio_value, self.current_total_equity())
            return entry

        elif action.action_type == CorporateActionType.DELISTING:
            if action.new_isin and action.new_isin != action.isin:
                old_isin = action.isin
                new_isin = action.new_isin
                if new_isin in self._positions and self._positions[new_isin] is not pos:
                    existing_target = self._positions[new_isin]
                    if not existing_target.is_closed and existing_target.quantity > 0:
                        raise CorporateActionError(
                            f"Cannot re-key {old_isin} to {new_isin} on {action.action_type.value}: "
                            f"target ISIN already has active open position (Finding H-96, H-98)."
                        )
                pos.apply_corporate_action(action)
                del self._positions[old_isin]
                self._positions[new_isin] = pos
                return None
            else:
                # Finding H-98: Delisting without new_isin must settle proceeds into CashLedger
                # at delisting_price (or average_entry_price), realizing PnL and leaving equity unchanged!
                delist_price = (
                    action.delisting_price
                    if getattr(action, "delisting_price", None) is not None
                    else pos.average_entry_price
                )
                settled_qty = pos.quantity
                proceeds, net_pnl = pos.close_delisting(delist_price)
                entry = self._ledger.record_delisting_settlement(
                    trade_date=action.ex_date,
                    instrument_id=action.isin,
                    amount=proceeds,
                    description=f"Delisting settlement proceeds for {action.isin} ({settled_qty} shares @ ₹{delist_price})",
                    reference_id=f"DELIST_{action.isin}_{action.ex_date.isoformat()}",
                )
                del self._positions[action.isin]
                self._peak_portfolio_value = max(self._peak_portfolio_value, self.current_total_equity())
                return entry

        elif action.action_type == CorporateActionType.DIVIDEND:
            div_per_share = (
                action.dividend_amount
                if action.dividend_amount is not None
                else (action.ratio_numerator / action.ratio_denominator)
            )
            total_dividend = _quantize_paise(Decimal(pos.quantity) * div_per_share)
            entry = self._ledger.record_dividend(
                trade_date=action.ex_date,
                instrument_id=action.isin,
                amount=total_dividend,
                description=f"Cash Dividend for {action.isin} ({pos.quantity} shares @ ₹{div_per_share})",
                reference_id=f"DIV_{action.isin}_{action.ex_date.isoformat()}",
            )
            self._peak_portfolio_value = max(self._peak_portfolio_value, self.current_total_equity())
            return entry
        else:
            return None

    def apply_corporate_actions_for_session(
        self,
        session_date: datetime.date,
        corporate_actions: Sequence[CorporateAction],
        price_convention: Optional[PriceConvention] = None,
    ) -> Sequence[CashLedgerEntry]:
        """
        Applies all corporate actions whose ex-date matches session_date to currently open held positions.
        Returns any cash ledger entries generated (e.g. dividend inflows).
        """
        entries: List[CashLedgerEntry] = []
        for ca in corporate_actions:
            if ca.ex_date == session_date:
                entry = self.apply_corporate_action(ca, price_convention=price_convention)
                if entry is not None:
                    entries.append(entry)
        return tuple(entries)

    def current_total_equity(
        self,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> Decimal:
        """
        Computes current total portfolio equity = cash + sum(open positions).
        Uses latest_market_prices if provided; otherwise falls back to position cost bases.
        """
        total_pos_val = Decimal("0.00")
        for inst_id, pos in self.get_open_positions().items():
            if latest_market_prices is not None and inst_id in latest_market_prices:
                price = latest_market_prices[inst_id]
                snap = pos.snapshot(price)
                if snap.market_value is not None:
                    total_pos_val += snap.market_value
            else:
                total_pos_val += pos.total_cost_basis

        return _quantize_paise(self._ledger.current_cash + total_pos_val)

    def validate_allocation(
        self,
        instrument_id: str,
        proposed_order_value: Decimal,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> None:
        """
        Validates whether proposed capital deployment complies with max_single_position_weight.
        Evaluates unrounded exact allocation weight against committed criteria (I-3, I-4).
        Fails closed with PortfolioRiskLimitError if limit would be breached.
        """
        if isinstance(proposed_order_value, bool) or not isinstance(proposed_order_value, Decimal) or not proposed_order_value.is_finite() or proposed_order_value < 0:
            raise PortfolioRiskLimitError(f"proposed_order_value must be non-negative Decimal, got {proposed_order_value!r}")

        total_equity = self.current_total_equity(latest_market_prices)
        if total_equity <= Decimal("0.00"):
            raise PortfolioRiskLimitError(
                f"Cannot allocate ₹{proposed_order_value} to {instrument_id}: "
                f"portfolio equity is non-positive (₹{total_equity})."
            )

        existing_pos_val = Decimal("0.00")
        pos = self.get_position(instrument_id)
        if pos is not None and not pos.is_closed:
            if latest_market_prices is not None and instrument_id in latest_market_prices:
                snap = pos.snapshot(latest_market_prices[instrument_id])
                if snap.market_value is not None:
                    existing_pos_val = snap.market_value
            else:
                existing_pos_val = pos.total_cost_basis

        proposed_pos_val = existing_pos_val + proposed_order_value
        allocation_weight = proposed_pos_val / total_equity

        if allocation_weight > self._criteria.max_single_position_weight:
            raise PortfolioRiskLimitError(
                f"Allocation breach for '{instrument_id}': proposed weight {allocation_weight:.6f} "
                f"exceeds maximum allowed single position weight {self._criteria.max_single_position_weight} "
                f"(₹{proposed_pos_val} / ₹{total_equity})."
            )

    def process_fill(
        self,
        fill: ExecutionFillResult,
        enforce_risk_limits: bool = True,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """
        Processes an executed trade fill atomically:
        1. Pre-validates fill parameters, status, and costs.
        2. Pre-validates short-sale / held quantity for SELL fills before moving cash (I-1).
        3. Pre-validates concentration risk limits on total capital deployed for BUY fills (I-3).
        4. Pre-validates fill idempotency against double-posting / replays (I-2).
        5. Posts cash entry to CashLedger with exact paise quantization.
        6. Updates target Position; rolls back CashLedger entry if position update fails.
        """
        if not isinstance(fill, ExecutionFillResult):
            raise LedgerValidationError(f"Expected ExecutionFillResult, got {type(fill)}")

        if fill.status not in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            raise LedgerValidationError(
                f"Cannot process non-fill outcome '{fill.status.value}' in portfolio: {fill.rejection_reason}"
            )

        if fill.costs is None:
            raise LedgerValidationError("ExecutionFillResult lacks required TransactionCostBreakdown.")

        # Pre-validate price and reconcile costs.gross_amount to filled_quantity × executed_price (R-2)
        if fill.executed_price is None or isinstance(fill.executed_price, bool) or not isinstance(fill.executed_price, Decimal) or not fill.executed_price.is_finite() or fill.executed_price <= Decimal("0.00"):
            raise LedgerValidationError(
                f"executed_price must be positive finite Decimal, got {fill.executed_price!r}"
            )

        paise_costs = fill.costs.to_paise()
        expected_gross = _quantize_paise(Decimal(fill.filled_quantity) * fill.executed_price)
        if paise_costs.gross_amount != expected_gross:
            raise LedgerValidationError(
                f"Reconciliation error: fill.costs.gross_amount (₹{paise_costs.gross_amount}) "
                f"does not match filled_quantity × executed_price (₹{expected_gross})."
            )

        inst_id = fill.order.instrument_id
        pos = self.get_position(inst_id)

        # 1. Pre-validate short delivery before any cash movement (I-1)
        if fill.order.side == OrderSide.SELL:
            held_quantity = 0 if pos is None else pos.quantity
            if held_quantity < fill.filled_quantity:
                raise LedgerValidationError(
                    f"Illegal short delivery: cannot sell {fill.filled_quantity} shares of {inst_id}; "
                    f"only {held_quantity} held in portfolio."
                )

        # 2. Pre-validate risk limits with full capital outlay (gross + charges) (I-3, G-13)
        if enforce_risk_limits and fill.order.side == OrderSide.BUY:
            capital_outlay = paise_costs.gross_amount + paise_costs.total_charges
            if not self._ledger.allow_overdraft and self._ledger.current_cash < capital_outlay:
                raise PortfolioRiskLimitError(
                    f"Insufficient cash for '{inst_id}': capital outlay ₹{capital_outlay} "
                    f"exceeds available cash ₹{self._ledger.current_cash}."
                )
            self.validate_allocation(inst_id, capital_outlay, latest_market_prices)

        # 3. O(1) Replay check for the exact same in-memory fill instance (N-1, R-5)
        fill_addr = id(fill)
        if fill_addr in self._processed_fill_instances:
            raise LedgerValidationError(
                f"Duplicate entry rejected: fill '{fill}' has already been processed by portfolio."
            )

        # 4. Validate reference_id or fill_id if present (N-4)
        if reference_id is not None:
            if (
                isinstance(reference_id, bool)
                or not isinstance(reference_id, str)
                or not reference_id.strip()
                or reference_id != reference_id.strip()
            ):
                raise LedgerValidationError(
                    f"reference_id must be a non-empty, non-whitespace string without leading/trailing whitespace, got {reference_id!r}"
                )
            if reference_id in self._ledger._posted_reference_ids:
                raise LedgerValidationError(
                    f"Duplicate entry rejected: fill with reference '{reference_id}' already posted to ledger."
                )
        elif fill.fill_id is not None:
            if fill.fill_id in self._ledger._posted_reference_ids:
                raise LedgerValidationError(
                    f"Duplicate entry rejected: fill with reference '{fill.fill_id}' already posted to ledger."
                )

        # 5. Post to CashLedger (CashLedger handles deterministic sequential reference commit upon posting)
        entry = self._ledger.record_fill(fill, reference_id=reference_id)

        # 6. Update Position with atomic rollback safety and clean phantom position cleanup (R-3)
        is_new_instrument = inst_id not in self._positions
        if is_new_instrument:
            self._positions[inst_id] = Position(inst_id)

        try:
            self._positions[inst_id].apply_fill(fill)
            self._processed_fill_instances[fill_addr] = fill
            if len(self._processed_fill_instances) > self._max_pinned_instances:
                self._processed_fill_instances.popitem(last=False)
        except Exception:
            self._ledger._rollback_last_entry()
            if is_new_instrument:
                del self._positions[inst_id]
            self._processed_fill_instances.pop(fill_addr, None)
            raise

        return entry

    def mark_to_market(
        self,
        as_of_date: datetime.date,
        market_prices: Mapping[str, Decimal],
    ) -> PortfolioSnapshot:
        """
        Performs session-end mark-to-market valuation across all open positions.
        
        Enforces:
        - Date monotonicity (as_of_date must be strictly after previous valuation date).
        - Fail-closed price verification: every open position MUST have an explicit,
          positive Decimal market price provided. Zero silent omitting or NaN forward-filling.
        - Exact Decimal drawdown tracking without premature rounding loss (I-4).
        """
        if type(as_of_date) is not datetime.date:
            raise LedgerValidationError(f"as_of_date must be exact datetime.date, got {type(as_of_date).__name__}")

        if self._last_valuation_date is not None and as_of_date <= self._last_valuation_date:
            raise LedgerValidationError(
                f"Valuation date {as_of_date} must be strictly after last valuation date {self._last_valuation_date}."
            )

        open_positions = self.get_open_positions()
        pos_snapshots: List[PositionSnapshot] = []

        total_market_val = Decimal("0.00")
        total_invested_capital = Decimal("0.00")

        # Sort keys deterministically for reproducible snapshots
        for inst_id in sorted(open_positions.keys()):
            pos = open_positions[inst_id]
            if inst_id not in market_prices:
                raise LedgerValidationError(
                    f"Fail-closed valuation: missing required market price for open position '{inst_id}' "
                    f"on session {as_of_date}."
                )
            price = market_prices[inst_id]
            if isinstance(price, bool) or not isinstance(price, Decimal) or not price.is_finite() or price <= Decimal("0.00"):
                raise LedgerValidationError(
                    f"Invalid market price for '{inst_id}' on {as_of_date}: {price!r}"
                )

            snap = pos.snapshot(price)
            pos_snapshots.append(snap)
            total_invested_capital += snap.total_cost_basis
            if snap.market_value is not None:
                total_market_val += snap.market_value

        cash_balance = self._ledger.current_cash
        total_val = _quantize_paise(cash_balance + total_market_val)

        # Drawdown calculation with exact Decimal precision (I-4)
        if total_val >= self._peak_portfolio_value:
            self._peak_portfolio_value = total_val
            self._current_drawdown = Decimal("0.00")
            self._drawdown_duration_sessions = 0
        else:
            if self._peak_portfolio_value > Decimal("0.00"):
                dd = (self._peak_portfolio_value - total_val) / self._peak_portfolio_value
                self._current_drawdown = dd
                if self._current_drawdown > self._max_drawdown:
                    self._max_drawdown = self._current_drawdown
            self._drawdown_duration_sessions += 1

        snapshot = PortfolioSnapshot(
            as_of_date=as_of_date,
            cash_balance=cash_balance,
            invested_capital=total_invested_capital,
            total_portfolio_value=total_val,
            peak_portfolio_value=self._peak_portfolio_value,
            current_drawdown=self._current_drawdown,
            max_drawdown=self._max_drawdown,
            drawdown_duration_sessions=self._drawdown_duration_sessions,
            open_positions_count=len(pos_snapshots),
            positions=tuple(pos_snapshots),
        )

        self._snapshots.append(snapshot)
        self._last_valuation_date = as_of_date

        return snapshot





