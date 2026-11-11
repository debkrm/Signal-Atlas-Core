"""Portfolio Valuation, Position Management, and Risk Tracker.

Enforces:
- Exact Decimal portfolio valuation and mark-to-market accounting.
- Multi-instrument position tracking integrated with CashLedger.
- Statutory Indian transaction cost deductions and contract-note reconciliation.
- Risk limits: max single-position concentration limit and portfolio drawdown monitoring.
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.execution.simulator import ExecutionFillResult
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.portfolio.ledger import CashLedger, PAISE_PRECISION, _quantize_paise
from signal_core.portfolio.position import Position
from signal_core.portfolio.types import (
    CashLedgerEntry,
    LedgerValidationError,
    PortfolioRiskLimitError,
    PortfolioSnapshot,
    PositionSnapshot,
)

DRAWDOWN_PRECISION = Decimal("0.0001")


class Portfolio:
    """
    Authoritative Portfolio Accounting Engine.
    
    Coordinates the double-entry CashLedger, multi-instrument open positions,
    mark-to-market session valuations, and committed Go/No-Go risk limits.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("0.00"),
        criteria: Optional[GoNoGoCriteria] = None,
        allow_overdraft: bool = False,
    ) -> None:
        if isinstance(initial_capital, bool) or not isinstance(initial_capital, Decimal) or not initial_capital.is_finite() or initial_capital < 0:
            raise LedgerValidationError(f"initial_capital must be non-negative Decimal, got {initial_capital!r}")

        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._ledger = CashLedger(initial_capital=initial_capital, allow_overdraft=allow_overdraft)
        self._positions: Dict[str, Position] = {}
        self._peak_portfolio_value: Decimal = _quantize_paise(initial_capital)
        self._current_drawdown: Decimal = Decimal("0.0000")
        self._max_drawdown: Decimal = Decimal("0.0000")
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
        Validates whether proposed order value complies with max_single_position_weight.
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
        allocation_weight = (proposed_pos_val / total_equity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        if allocation_weight > self._criteria.max_single_position_weight:
            raise PortfolioRiskLimitError(
                f"Allocation breach for '{instrument_id}': proposed weight {allocation_weight:.4f} "
                f"exceeds maximum allowed single position weight {self._criteria.max_single_position_weight} "
                f"(₹{proposed_pos_val} / ₹{total_equity})."
            )

    def process_fill(
        self,
        fill: ExecutionFillResult,
        enforce_risk_limits: bool = True,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> CashLedgerEntry:
        """
        Processes an executed trade fill:
        1. Validates risk limits (max_single_position_weight on BUY).
        2. Posts cash inflow/outflow to the CashLedger.
        3. Updates the target instrument's Position (cost basis, realized PnL, average price).
        """
        if not isinstance(fill, ExecutionFillResult):
            raise LedgerValidationError(f"Expected ExecutionFillResult, got {type(fill)}")

        if fill.status not in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            raise LedgerValidationError(
                f"Cannot process non-fill outcome '{fill.status.value}' in portfolio: {fill.rejection_reason}"
            )

        inst_id = fill.order.instrument_id
        gross_trade_value = _quantize_paise(Decimal(fill.filled_quantity) * fill.executed_price)

        if enforce_risk_limits and fill.order.side == OrderSide.BUY:
            self.validate_allocation(inst_id, gross_trade_value, latest_market_prices)

        # 1. Post to CashLedger (enforces overdraft protection and paise quantization)
        entry = self._ledger.record_fill(fill)

        # 2. Update Position
        if inst_id not in self._positions:
            self._positions[inst_id] = Position(inst_id)
        
        self._positions[inst_id].apply_fill(fill)

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
        - Accurate tracking of peak portfolio value, session drawdown, and drawdown duration.
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

        # Drawdown calculation
        if total_val >= self._peak_portfolio_value:
            self._peak_portfolio_value = total_val
            self._current_drawdown = Decimal("0.0000")
            self._drawdown_duration_sessions = 0
        else:
            if self._peak_portfolio_value > Decimal("0.00"):
                dd = (self._peak_portfolio_value - total_val) / self._peak_portfolio_value
                self._current_drawdown = dd.quantize(DRAWDOWN_PRECISION, rounding=ROUND_HALF_UP)
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
