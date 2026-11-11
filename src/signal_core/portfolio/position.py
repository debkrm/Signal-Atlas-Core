"""Position Accounting Contract for Indian Cash Equities.

Tracks multi-fill position states, weighted average entry price,
realized PnL net of statutory Indian transaction costs, and mark-to-market
valuation using exact Decimal arithmetic. Prohibits short selling under
cash equity delivery settlement (CNC).
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from signal_core.execution.simulator import ExecutionFillResult
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.portfolio.types import (
    LedgerValidationError,
    PositionSnapshot,
)

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

    def apply_fill(self, fill: ExecutionFillResult) -> Tuple[Decimal, Decimal]:
        """
        Updates the position based on an executed fill.
        
        Returns:
            Tuple[Decimal, Decimal]: (realized_gross_pnl_for_fill, realized_net_pnl_for_fill)
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

        paise_costs = fill.costs.to_paise()
        charges = paise_costs.total_charges
        qty = fill.filled_quantity
        price = fill.executed_price

        if fill.order.side == OrderSide.BUY:
            gross = _quantize_paise(Decimal(qty) * price)
            new_qty = self._quantity + qty
            new_cost_basis = self._total_cost_basis + gross
            new_avg_price = (new_cost_basis / Decimal(new_qty)).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)

            self._quantity = new_qty
            self._total_cost_basis = new_cost_basis
            self._average_entry_price = new_avg_price
            self._unallocated_buy_charges += charges
            self._total_charges_paid += charges

            return (Decimal("0.00"), Decimal("0.00"))

        elif fill.order.side == OrderSide.SELL:
            if qty > self._quantity:
                raise LedgerValidationError(
                    f"Illegal short delivery: cannot sell {qty} shares of {self._instrument_id}; "
                    f"only {self._quantity} shares held."
                )

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
            else:
                # Partial reduction
                allocated_buy_charges = _quantize_paise(
                    self._unallocated_buy_charges * Decimal(qty) / Decimal(self._quantity)
                )
                sold_cost_basis = _quantize_paise(
                    self._average_entry_price * Decimal(qty)
                )

                self._unallocated_buy_charges -= allocated_buy_charges
                self._total_cost_basis -= sold_cost_basis
                self._quantity -= qty

            gross_pnl = gross_proceeds - sold_cost_basis
            net_pnl = gross_pnl - charges - allocated_buy_charges

            self._realized_gross_pnl += gross_pnl
            self._realized_net_pnl += net_pnl

            return (gross_pnl, net_pnl)

        else:
            raise LedgerValidationError(f"Unsupported OrderSide: {fill.order.side}")

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
