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

    def apply_corporate_action(self, action: CorporateAction) -> None:
        """
        Applies a mid-hold corporate action to an open position per AGENTS.md §13.2 and Audit §59.4, §59.7.

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
            return

        # Finding H-86: ISIN_TRANSITION represents continuity change of identity, not share split multiplier.
        # Re-key instrument_id to action.new_isin, keeping quantity and cost basis strictly invariant.
        if action.action_type == CorporateActionType.ISIN_TRANSITION:
            if not action.new_isin:
                raise CorporateActionError(
                    f"ISIN_TRANSITION requires new_isin for {self._instrument_id} (Finding H-86)."
                )
            self._instrument_id = action.new_isin
            return

        if action.action_type in (
            CorporateActionType.SPLIT,
            CorporateActionType.BONUS,
            CorporateActionType.CONSOLIDATION,
        ):
            multiplier = action.ratio_numerator / action.ratio_denominator
            new_qty_dec = Decimal(self._quantity) * multiplier
            # Finding N-87: Fractional entitlement cannot be silently truncated. Fail closed!
            if new_qty_dec != Decimal(int(new_qty_dec)):
                raise CorporateActionError(
                    f"Non-integral restatement from corporate action {action.action_type.value} on {self._instrument_id}: "
                    f"{self._quantity} shares × {action.ratio_numerator}/{action.ratio_denominator} = {new_qty_dec} shares. "
                    f"Fractional entitlements cannot be silently truncated (Finding N-87)."
                )
            new_qty = int(new_qty_dec)
            if new_qty <= 0:
                raise LedgerValidationError(
                    f"Corporate action {action.action_type.value} resulted in non-positive quantity {new_qty} "
                    f"from initial {self._quantity} shares."
                )
            self._quantity = new_qty
            self._average_entry_price = (
                self._total_cost_basis / Decimal(self._quantity)
            ).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)
            # Total cost basis and unallocated buy charges remain strictly unchanged

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

