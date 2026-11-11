"""Statutory Indian Transaction Cost and Tax Calculation Engine.

Computes exact Decimal transaction costs and statutory levies for NSE equity trades:
- Securities Transaction Tax (STT): Delivery (both legs) vs Intraday (sell leg only)
- Exchange Turnover Charges: Date-aware resolution via official NSE circulars
- Investor Protection Fund Trust (IPFT) charges: Date-aware resolution
- SEBI Turnover Fees: ₹10 per crore (0.0001%)
- Indian Stamp Duty: Indian Stamp Act schedule (delivery buy vs intraday buy)
- Goods & Services Tax (GST): 18% applied to taxable financial services base (brokerage + exchange + sebi + ipft)
- Brokerage: Configurable flat order fee or proportional basis points

All financial values are computed in exact Decimal arithmetic. Floating-point representation is banned.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence, Tuple, Union

from signal_core.contracts.criteria import (
    EffectiveDatedExchangeFee,
    StatutoryCostCriteria,
    load_go_no_go_criteria,
)
from signal_core.execution.types import OrderProduct, OrderSide

PRECISION_4 = Decimal("0.0001")
PRECISION_2 = Decimal("0.01")
SLAB_FLATTENING_DISCLOSURE = (
    "Pre-Oct-2024 NSE turnover fee uses Slab-1 rate (conservative overstatement per R-4 "
    "audit finding; actual member turnover may qualify for lower volume slabs)."
)
OCT_2024_BOUNDARY = datetime.date(2024, 10, 1)


class CostCalculationError(ValueError):
    """Raised when cost calculation inputs violate domain invariants."""
    pass


@dataclass(frozen=True, slots=True)
class TransactionCostBreakdown:
    """
    Immutable comprehensive transaction cost and tax breakdown for an executed order.
    All financial values are exact Decimals.
    """
    trade_date: datetime.date
    side: OrderSide
    product: OrderProduct
    quantity: int
    price: Decimal
    gross_amount: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_turnover_fee: Decimal
    ipft: Decimal
    sebi_turnover_fee: Decimal
    stamp_duty: Decimal
    gst: Decimal
    total_statutory_taxes: Decimal
    total_charges: Decimal
    net_cash_flow: Decimal
    effective_cost_bps: Decimal
    circular_ref: str
    disclosures: Tuple[str, ...]


class TransactionCostModel:
    """
    Authoritative Statutory Indian Transaction Cost Engine.
    
    Consumes statutory criteria from committed go_no_go_criteria.yaml.
    Guarantees exact Decimal calculations, effective-dated regulatory compliance,
    and fail-closed behavior on unmapped dates.
    """

    def __init__(self, cost_criteria: Optional[StatutoryCostCriteria] = None) -> None:
        if cost_criteria is None:
            self._criteria = load_go_no_go_criteria().statutory_costs
        else:
            if not isinstance(cost_criteria, StatutoryCostCriteria):
                raise CostCalculationError(
                    f"cost_criteria must be StatutoryCostCriteria, got {type(cost_criteria)}"
                )
            self._criteria = cost_criteria

    @property
    def criteria(self) -> StatutoryCostCriteria:
        return self._criteria

    def compute_costs(
        self,
        trade_date: datetime.date,
        side: OrderSide,
        product: OrderProduct,
        quantity: int,
        price: Decimal,
        is_brokerage_applicable: bool = True,
        custom_brokerage: Optional[Decimal] = None,
    ) -> TransactionCostBreakdown:
        """
        Computes the complete, statutory Indian transaction cost schedule for a trade.
        
        Args:
            trade_date: Exact session date of trade execution.
            side: OrderSide.BUY or OrderSide.SELL.
            product: OrderProduct.DELIVERY or OrderProduct.INTRADAY.
            quantity: Executed quantity (positive int).
            price: Executed price (positive Decimal).
            is_brokerage_applicable: Whether to charge broker commission.
            custom_brokerage: Optional override for brokerage fee.
        
        Returns:
            TransactionCostBreakdown with all taxes, levies, and net cash flow.
        """
        if type(trade_date) is not datetime.date:
            raise CostCalculationError(f"trade_date must be exact datetime.date, got {type(trade_date).__name__}")
        
        if not isinstance(side, OrderSide):
            raise CostCalculationError(f"side must be OrderSide enum, got {type(side)}")
            
        if not isinstance(product, OrderProduct):
            raise CostCalculationError(f"product must be OrderProduct enum, got {type(product)}")
            
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise CostCalculationError(f"quantity must be a positive integer, got {quantity!r}")
            
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise CostCalculationError(f"price must be a finite positive Decimal, got {price!r}")

        gross_amount = (Decimal(quantity) * price)

        # 1. Brokerage
        if not is_brokerage_applicable:
            brokerage = Decimal("0")
        elif custom_brokerage is not None:
            if not isinstance(custom_brokerage, Decimal) or not custom_brokerage.is_finite() or custom_brokerage < 0:
                raise CostCalculationError(f"custom_brokerage must be non-negative Decimal, got {custom_brokerage!r}")
            brokerage = custom_brokerage
        else:
            brokerage = self._criteria.brokerage_per_order_inr

        # 2. Securities Transaction Tax (STT)
        # Delivery: 0.1% on BUY and 0.1% on SELL
        # Intraday: 0% on BUY and 0.025% on SELL
        if product == OrderProduct.DELIVERY:
            stt = gross_amount * self._criteria.stt_delivery_rate
        else:
            if side == OrderSide.BUY:
                stt = Decimal("0")
            else:
                stt = gross_amount * self._criteria.stt_intraday_sell_rate

        # 3. Exchange Turnover Charges & IPFT (Date-Aware NSE Circular Resolution)
        fee_info: EffectiveDatedExchangeFee = self._criteria.get_exchange_fee_for_date(trade_date)
        exchange_turnover_fee = gross_amount * fee_info.exchange_turnover_rate
        ipft = gross_amount * fee_info.ipft_rate

        # 4. SEBI Turnover Charges (₹10 per crore = 0.0001%)
        sebi_turnover_fee = gross_amount * self._criteria.sebi_turnover_charge_rate

        # 5. Indian Stamp Duty (Levied on BUY legs only per Indian Stamp Act)
        # Delivery Buy: 0.015%
        # Intraday Buy: 0.003%
        # Sell: ₹0
        if side == OrderSide.BUY:
            if product == OrderProduct.DELIVERY:
                stamp_duty = gross_amount * self._criteria.stamp_duty_delivery_buy_rate
            else:
                stamp_duty = gross_amount * self._criteria.stamp_duty_intraday_buy_rate
        else:
            stamp_duty = Decimal("0")

        # 6. Goods & Services Tax (GST: 18%)
        # Base includes: brokerage + exchange_turnover + sebi_turnover + ipft
        taxable_base = Decimal("0")
        for comp in self._criteria.gst_taxable_base_components:
            if comp == "brokerage":
                taxable_base += brokerage
            elif comp == "exchange_turnover":
                taxable_base += exchange_turnover_fee
            elif comp == "sebi_turnover":
                taxable_base += sebi_turnover_fee
            elif comp == "ipft":
                taxable_base += ipft
            else:
                raise CostCalculationError(f"Unrecognized GST taxable base component: {comp!r}")

        gst = taxable_base * self._criteria.gst_rate

        # Aggregations
        total_statutory_taxes = stt + exchange_turnover_fee + ipft + sebi_turnover_fee + stamp_duty + gst
        total_charges = brokerage + total_statutory_taxes

        # Net Cash Flow
        # Buy: Outflow of (Gross Value + All Charges)
        # Sell: Inflow of (Gross Value - All Charges)
        if side == OrderSide.BUY:
            net_cash_flow = -(gross_amount + total_charges)
        else:
            net_cash_flow = gross_amount - total_charges

        effective_cost_bps = (total_charges / gross_amount) * Decimal("10000")

        # Disclosure accounting per Rule 9 and §10 Audit Condition 2 (Residual R-4)
        disclosures: Tuple[str, ...]
        if trade_date < OCT_2024_BOUNDARY:
            disclosures = (SLAB_FLATTENING_DISCLOSURE,)
        else:
            disclosures = ()

        return TransactionCostBreakdown(
            trade_date=trade_date,
            side=side,
            product=product,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            brokerage=brokerage,
            stt=stt,
            exchange_turnover_fee=exchange_turnover_fee,
            ipft=ipft,
            sebi_turnover_fee=sebi_turnover_fee,
            stamp_duty=stamp_duty,
            gst=gst,
            total_statutory_taxes=total_statutory_taxes,
            total_charges=total_charges,
            net_cash_flow=net_cash_flow,
            effective_cost_bps=effective_cost_bps,
            circular_ref=fee_info.circular_ref,
            disclosures=disclosures,
        )
