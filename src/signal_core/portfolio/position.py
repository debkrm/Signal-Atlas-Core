"""Position Accounting Contract for Indian Cash Equities.

Tracks multi-fill position states, weighted average entry price,
realized PnL net of statutory Indian transaction costs, and mark-to-market
valuation using exact Decimal arithmetic. Prohibits short selling under
cash equity delivery settlement (CNC).
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from signal_core.contracts.order_types import ExecutionFillResult, FillStatus, OrderSide
from signal_core.portfolio.types import (
    CorporateActionError,
    LedgerValidationError,
    PositionSnapshot,
)
from signal_core.storage.security_master import CorporateAction, CorporateActionType

PAISE_PRECISION = Decimal("0.01")
PRICE_PRECISION = Decimal("0.0001")


def _quantize_paise(val: Decimal) -> Decimal:
    """Quantizes a Decimal monetary quantity to exact paise (0.01 INR) via ROUND_HALF_UP."""
    if isinstance(val, bool) or not isinstance(val, Decimal) or not val.is_finite():
        raise LedgerValidationError(f"Expected finite Decimal monetary value, got {val!r}")
    return val.quantize(PAISE_PRECISION, rounding=ROUND_HALF_UP)


class Position:
    """
    Stateful accounting container for a single financial instrument.
    
    Invariants:
    - Quantity is strictly non-negative (no naked short selling in cash delivery).
    - All cost bases and monetary PnLs are exact Decimals quantized to paise.
    - Transaction charges are allocated proportionally across partial sales.
    """

    def __init__(self, instrument_id: str) -> None:
        if not isinstance(instrument_id, str):
            raise LedgerValidationError(f"instrument_id must be str, got {type(instrument_id).__name__}")
        cleaned_id = instrument_id.strip()
        if not cleaned_id or cleaned_id != instrument_id:
            raise LedgerValidationError(f"Invalid instrument_id: {instrument_id!r}")
        if any(c in cleaned_id for c in (",", "|", ";", "\n", "\r", "\t")):
            raise LedgerValidationError(f"instrument_id contains illegal delimiters: {instrument_id!r}")

        self._instrument_id = cleaned_id
        self._quantity: int = 0
        self._average_entry_price: Decimal = Decimal("0.0000")
        self._total_cost_basis: Decimal = Decimal("0.00")
        self._realized_gross_pnl: Decimal = Decimal("0.00")
        self._realized_net_pnl: Decimal = Decimal("0.00")
        self._total_charges_paid: Decimal = Decimal("0.00")
        self._unallocated_buy_charges: Decimal = Decimal("0.00")
        # Audit §90.9 item 4: the session the open position was first built on, so a holding-period
        # bound can be measured in authoritative calendar sessions (§13.2).
        self._entry_date: Optional[datetime.date] = None

    @property
    def instrument_id(self) -> str:
        return self._instrument_id

    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def is_closed(self) -> bool:
        return self._quantity == 0

    @property
    def entry_date(self) -> Optional[datetime.date]:
        """The session that opened the currently held quantity, or None when nothing is held."""
        return self._entry_date

    def holding_sessions(self, as_of: datetime.date, calendar) -> int:
        """
        Sessions elapsed between the entry session and `as_of`, counted on the authoritative calendar.

        Zero on the entry session itself. A date the calendar does not schedule is refused rather than
        approximated, because a holding bound counted on an invented session count is not a bound
        (§6.3).
        """
        if self._quantity <= 0 or self._entry_date is None:
            return 0
        sessions = calendar.sessions
        try:
            return sessions.index(as_of) - sessions.index(self._entry_date)
        except ValueError as exc:
            raise LedgerValidationError(
                f"Holding-period measurement needs authoritative sessions for {self._instrument_id}: "
                f"entry {self._entry_date}, as-of {as_of} (AGENTS.md §6.3)"
            ) from exc

    def require_within_hold_bound(
        self, as_of: datetime.date, max_hold_trading_sessions: int, calendar
    ) -> None:
        """
        Refuses a hold that reaches `max_hold_trading_sessions` (Audit §90.9 item 4, AGENTS.md §13.2).

        The bound is passed in from `configs/go_no_go_criteria.yaml`; there is no module default (§10.8).
        A position that cannot exit inside the bound because the bid is locked at the lower circuit is
        still refused here: an unbounded exit delay is not an extension of the holding period (§5.3).
        """
        if (
            isinstance(max_hold_trading_sessions, bool)
            or not isinstance(max_hold_trading_sessions, int)
            or max_hold_trading_sessions < 1
        ):
            raise LedgerValidationError(
                f"max_hold_trading_sessions must be a positive integer, got {max_hold_trading_sessions!r}"
            )
        if self._quantity <= 0:
            return
        elapsed = self.holding_sessions(as_of, calendar)
        if elapsed >= max_hold_trading_sessions:
            raise LedgerValidationError(
                f"Hold bound refused: {self._instrument_id} entered {self._entry_date} would be held "
                f"{elapsed} session(s) into {as_of}, at or past max_hold_trading_sessions="
                f"{max_hold_trading_sessions} (Audit §90.9 item 4); a lower-circuit freeze is a refusal, "
                f"never an extension (§5.3)"
            )

    @property
    def average_entry_price(self) -> Decimal:
        return self._average_entry_price

    @property
    def total_cost_basis(self) -> Decimal:
        return self._total_cost_basis

    @property
    def realized_gross_pnl(self) -> Decimal:
        return self._realized_gross_pnl

    @property
    def realized_net_pnl(self) -> Decimal:
        return self._realized_net_pnl

    @property
    def total_charges_paid(self) -> Decimal:
        return self._total_charges_paid

    @property
    def unallocated_buy_charges(self) -> Decimal:
        return self._unallocated_buy_charges

    def validate_fill(self, fill: ExecutionFillResult) -> None:
        """
        Validates whether a fill can be safely applied to this position.
        Fails closed before modifying any state.
        """
        if not isinstance(fill, ExecutionFillResult):
            raise LedgerValidationError(f"Expected ExecutionFillResult, got {type(fill)}")

        if fill.status not in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            raise LedgerValidationError(
                f"Cannot apply non-fill outcome '{fill.status.value}' to position: {fill.rejection_reason}"
            )

        if fill.order.instrument_id != self._instrument_id:
            raise LedgerValidationError(
                f"Fill instrument '{fill.order.instrument_id}' does not match position '{self._instrument_id}'."
            )

        if fill.costs is None:
            raise LedgerValidationError("ExecutionFillResult lacks required TransactionCostBreakdown.")

        if fill.executed_price is None or isinstance(fill.executed_price, bool) or not isinstance(fill.executed_price, Decimal) or not fill.executed_price.is_finite() or fill.executed_price <= Decimal("0.00"):
            raise LedgerValidationError(f"executed_price must be positive finite Decimal, got {fill.executed_price!r}")

        if fill.filled_quantity <= 0:
            raise LedgerValidationError(f"Fill quantity must be positive, got {fill.filled_quantity}")

        if fill.order.side == OrderSide.SELL:
            if fill.filled_quantity > self._quantity:
                raise LedgerValidationError(
                    f"Illegal short delivery: cannot sell {fill.filled_quantity} shares of {self._instrument_id}; "
                    f"only {self._quantity} shares held."
                )

    def apply_fill(self, fill: ExecutionFillResult) -> Tuple[Decimal, Decimal]:
        """
        Updates the position based on an executed fill.
        
        Returns:
            Tuple[Decimal, Decimal]: (realized_gross_pnl_for_fill, realized_net_pnl_for_fill)
        """
        self.validate_fill(fill)
        if fill.costs is None or fill.executed_price is None:
            raise LedgerValidationError("ExecutionFillResult lacks required costs or executed_price.")

        paise_costs = fill.costs.to_paise()
        charges = paise_costs.total_charges
        qty = fill.filled_quantity
        price = fill.executed_price

        if fill.order.side == OrderSide.BUY:
            was_flat = self._quantity == 0
            gross = _quantize_paise(Decimal(qty) * price)
            new_qty = self._quantity + qty
            new_cost_basis = self._total_cost_basis + gross
            new_avg_price = (new_cost_basis / Decimal(new_qty)).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)

            self._quantity = new_qty
            self._total_cost_basis = new_cost_basis
            self._average_entry_price = new_avg_price
            self._unallocated_buy_charges += charges
            self._total_charges_paid += charges
            if was_flat:
                self._entry_date = fill.fill_date

            return (Decimal("0.00"), Decimal("0.00"))

        elif fill.order.side == OrderSide.SELL:
            gross_proceeds = _quantize_paise(Decimal(qty) * price)
            self._total_charges_paid += charges

            if qty == self._quantity:
                # Full liquidation of position
                allocated_buy_charges = self._unallocated_buy_charges
                sold_cost_basis = self._total_cost_basis
                
                self._unallocated_buy_charges = Decimal("0.00")
                self._total_cost_basis = Decimal("0.00")
                self._quantity = 0
                self._average_entry_price = Decimal("0.0000")
                self._entry_date = None
            else:
                # Partial reduction: basis derived proportionally directly from total_cost_basis (I-7)
                allocated_buy_charges = _quantize_paise(
                    self._unallocated_buy_charges * Decimal(qty) / Decimal(self._quantity)
                )
                sold_cost_basis = _quantize_paise(
                    self._total_cost_basis * Decimal(qty) / Decimal(self._quantity)
                )

                self._unallocated_buy_charges -= allocated_buy_charges
                self._total_cost_basis -= sold_cost_basis
                self._quantity -= qty
                self._average_entry_price = (
                    self._total_cost_basis / Decimal(self._quantity)
                ).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)

            gross_pnl = gross_proceeds - sold_cost_basis
            net_pnl = gross_pnl - charges - allocated_buy_charges

            self._realized_gross_pnl += gross_pnl
            self._realized_net_pnl += net_pnl

            return (gross_pnl, net_pnl)

        else:
            raise LedgerValidationError(f"Unsupported OrderSide: {fill.order.side}")

    def apply_corporate_action(self, action: CorporateAction) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Applies a mid-hold corporate action to an open position per AGENTS.md §13.2 and Audit §59.4, §59.7, §66 (H-113).

        Invariants:
        - For SPLIT, BONUS, and ISIN_TRANSITION:
          * Share quantity is multiplied by ratio (ratio_numerator / ratio_denominator).
          * Average entry price is divided by ratio (restated proportionally).
          * Total cost basis and unallocated buy charges remain STRICTLY constant.
          * Mark-to-market equity at post-event price remains 100% INVARIANT (zero fabricated MTM loss).
        - For CONSOLIDATION (reverse split):
          * Share quantity is reduced by ratio.
          * Average entry price is increased proportionally.
          * Total cost basis remains constant.
        - For MERGER (Finding H-113):
          * Allocates integer whole shares ((qty * num) // den) to new_isin.
          * Returns (fractional_shares, fractional_cost_basis) for cash-in-lieu settlement, preserving total equity.
        - For DIVIDEND:
          * Share quantity and cost basis remain unchanged; cash inflow is credited at Portfolio level.
        """
        if not isinstance(action, CorporateAction):
            raise LedgerValidationError(f"Expected CorporateAction, got {type(action)}")
        if action.isin != self._instrument_id:
            raise LedgerValidationError(
                f"Corporate action ISIN '{action.isin}' does not match position '{self._instrument_id}'."
            )
        if self._quantity <= 0:
            return None

        # Finding H-99: Rights entitlement grants the right to subscribe; it does not fabricate free shares without cash outflow.
        # Holding through rights ex-date leaves position quantity and cost basis unchanged.
        if action.action_type == CorporateActionType.RIGHTS:
            return None

        # Finding H-86, H-89, H-96, H-98, H-99, H-113:
        # Exact rational integer restatement for SPLIT, BONUS, CONSOLIDATION, ISIN_TRANSITION, MERGER
        # and DELISTING carrying new_isin consideration.
        if action.action_type in (
            CorporateActionType.ISIN_TRANSITION,
            CorporateActionType.SPLIT,
            CorporateActionType.BONUS,
            CorporateActionType.CONSOLIDATION,
            CorporateActionType.MERGER,
        ) or (
            action.action_type == CorporateActionType.DELISTING and action.new_isin and action.new_isin != self._instrument_id
        ):
            if action.action_type in (CorporateActionType.ISIN_TRANSITION, CorporateActionType.MERGER) and not action.new_isin:
                raise CorporateActionError(
                    f"{action.action_type.value} requires new_isin for {self._instrument_id} (Finding H-86, H-98)."
                )

            num = int(action.ratio_numerator)
            den = int(action.ratio_denominator)

            if num != den:
                # Finding H-99 & H-113: Divisibility check.
                rem = (self._quantity * num) % den
                if rem != 0:
                    if action.action_type == CorporateActionType.MERGER:
                        # Finding H-113: Stock merger with fractional entitlement.
                        # Allocate integer whole shares to new_isin, settle fractional remainder as cash-in-lieu.
                        # Finding N-112: an unpriced fractional settlement has no consideration to book,
                        # so it fails closed here rather than silently settling at removed book basis.
                        if action.delisting_price is None:
                            raise CorporateActionError(
                                f"MERGER on {self._instrument_id} yields fractional shares {rem}/{den} but carries no "
                                f"consideration price; cash-in-lieu cannot be silently settled at book value "
                                f"(Finding N-112)."
                            )
                        whole_qty = (self._quantity * num) // den
                        fractional_shares = Decimal(rem) / Decimal(den)
                        fractional_cost_basis = _quantize_paise(
                            self._total_cost_basis * Decimal(rem) / Decimal(self._quantity * num)
                        )
                        fractional_charges = _quantize_paise(
                            self._unallocated_buy_charges * Decimal(rem) / Decimal(self._quantity * num)
                        )
                        self._total_cost_basis -= fractional_cost_basis
                        self._unallocated_buy_charges -= fractional_charges
                        self._realized_net_pnl -= fractional_charges
                        self._quantity = whole_qty
                        if self._quantity > 0:
                            self._average_entry_price = (
                                self._total_cost_basis / Decimal(self._quantity)
                            ).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)
                        else:
                            self._average_entry_price = Decimal("0.0000")
                        if action.new_isin:
                            self._instrument_id = action.new_isin
                        return (fractional_shares, fractional_cost_basis)
                    else:
                        fractional_shares = Decimal(self._quantity * num) / Decimal(den)
                        raise CorporateActionError(
                            f"Non-integral restatement from corporate action {action.action_type.value} on {self._instrument_id}: "
                            f"{self._quantity} shares × {action.ratio_numerator}/{action.ratio_denominator} = {fractional_shares} shares "
                            f"(remainder {rem}/{den}). "
                            f"Fractional entitlements cannot be silently truncated (Finding N-87, H-99)."
                        )
                new_qty = (self._quantity * num) // den
                if new_qty <= 0:
                    raise LedgerValidationError(
                        f"Corporate action {action.action_type.value} resulted in non-positive quantity {new_qty} "
                        f"from initial {self._quantity} shares."
                    )
                self._quantity = new_qty
                self._average_entry_price = (
                    self._total_cost_basis / Decimal(self._quantity)
                ).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)

            # Finding H-96 & H-98: Re-key position unconditionally if corporate action specifies new_isin
            if action.new_isin:
                self._instrument_id = action.new_isin
            return None

    def rekey(self, new_isin: str) -> None:
        """
        Moves this position onto a successor identity without touching its economics.

        Audit §75.4 H-127: on a SPLIT_BONUS_ADJUSTED series the split/bonus ratio is already in the
        prices, so a face-value ISIN transition is an identity change only and quantity, cost basis,
        average entry price and realized PnL must survive it unchanged. Applying the ratio there would
        divide an entry price the series never multiplied (Finding H-108).
        """
        if (
            isinstance(new_isin, bool)
            or not isinstance(new_isin, str)
            or not new_isin.strip()
            or new_isin != new_isin.strip()
        ):
            raise LedgerValidationError(f"new_isin must be a clean non-empty string, got {new_isin!r}")
        if new_isin == self._instrument_id:
            return
        self._instrument_id = new_isin

    def record_merger_cash_settlement_pnl(self, cash_amount: Decimal, fractional_cost_basis: Decimal) -> Decimal:
        """
        Books the realized gain or loss on a merger cash-in-lieu settlement (Finding N-112).

        The fractional slice's cost basis was already removed in apply_corporate_action; the
        consideration received is a sale of that slice, so realized PnL moves by
        (cash_amount - removed book basis) and the ledger identity stays exact.
        """
        if (
            isinstance(cash_amount, bool)
            or not isinstance(cash_amount, Decimal)
            or not cash_amount.is_finite()
            or isinstance(fractional_cost_basis, bool)
            or not isinstance(fractional_cost_basis, Decimal)
            or not fractional_cost_basis.is_finite()
        ):
            raise LedgerValidationError(
                f"Merger settlement amounts must be finite Decimal, got {cash_amount!r}, {fractional_cost_basis!r}"
            )
        settlement_pnl = cash_amount - fractional_cost_basis
        self._realized_net_pnl += settlement_pnl
        return settlement_pnl

    def close_delisting(self, delisting_price: Decimal) -> Tuple[Decimal, Decimal]:
        """
        Closes an open position upon delisting/settlement at delisting_price (Finding H-98).
        Calculates realized gross and net PnL, zeros out remaining shares, and preserves equity.
        Returns (proceeds, net_pnl).
        """
        if self._quantity <= 0:
            return Decimal("0.00"), Decimal("0.00")

        proceeds = _quantize_paise(Decimal(self._quantity) * delisting_price)
        gross_cost = _quantize_paise(Decimal(self._quantity) * self._average_entry_price)
        gross_pnl = _quantize_paise(proceeds - gross_cost)
        net_pnl = _quantize_paise(proceeds - self._total_cost_basis)

        self._realized_gross_pnl += gross_pnl
        self._realized_net_pnl += net_pnl
        self._quantity = 0
        self._average_entry_price = Decimal("0.0000")
        self._total_cost_basis = Decimal("0.00")

        return proceeds, net_pnl

    def snapshot(self, market_price: Optional[Decimal] = None) -> PositionSnapshot:
        """
        Creates an immutable valuation snapshot for this position.
        """
        if market_price is not None:
            if isinstance(market_price, bool) or not isinstance(market_price, Decimal) or not market_price.is_finite() or market_price <= Decimal("0.00"):
                raise LedgerValidationError(f"market_price must be positive finite Decimal, got {market_price!r}")
            market_val = _quantize_paise(Decimal(self._quantity) * market_price)
            unrealized = _quantize_paise(market_val - self._total_cost_basis)
        else:
            market_val = None
            unrealized = None

        return PositionSnapshot(
            instrument_id=self._instrument_id,
            quantity=self._quantity,
            average_entry_price=self._average_entry_price,
            total_cost_basis=self._total_cost_basis,
            realized_net_pnl=self._realized_net_pnl,
            market_price=market_price,
            market_value=market_val,
            unrealized_pnl=unrealized,
            realized_gross_pnl=self._realized_gross_pnl,
            total_charges_paid=self._total_charges_paid,
        )

