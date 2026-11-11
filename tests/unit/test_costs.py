"""Unit Tests for Statutory Indian Transaction Cost Engine.

Verifies exact Decimal calculations across historical NSE circulars,
delivery vs intraday legs, GST base components, and fail-closed invariants.
"""

import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.criteria import CriteriaValidationError, load_go_no_go_criteria
from signal_core.execution.costs import (
    CostCalculationError,
    SLAB_FLATTENING_DISCLOSURE,
    TransactionCostBreakdown,
    TransactionCostModel,
)
from signal_core.execution.types import OrderProduct, OrderSide


def test_delivery_buy_costs_2022_with_slab_disclosure():
    """
    Test delivery BUY trade on 2022-06-15 (Circular NSE/FA/46730).
    Values:
        Quantity: 100 shares @ ₹1000.00 = Gross ₹100,000.00
        Brokerage: ₹20.00
        STT: 0.1% on ₹100,000 = ₹100.00
        Exchange Turnover: 0.0000345 * 100,000 = ₹3.45
        IPFT: 0.000000001 * 100,000 = ₹0.0001 (₹0.01 per crore)
        SEBI Turnover: 0.000001 * 100,000 = ₹0.10 (₹10 per crore)
        Stamp Duty: 0.015% on ₹100,000 = ₹15.00
        GST: 18% on (Brokerage ₹20 + Exch ₹3.45 + SEBI ₹0.10 + IPFT ₹0.0001) = 0.18 * 23.5501 = ₹4.239018
        Disclosures: Must contain R-4 pre-Oct-2024 slab flattening disclosure.
    """
    model = TransactionCostModel()
    trade_date = datetime.date(2022, 6, 15)
    breakdown = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        price=Decimal("1000.00"),
    )

    assert isinstance(breakdown, TransactionCostBreakdown)
    assert breakdown.gross_amount == Decimal("100000.00")
    assert breakdown.brokerage == Decimal("20.00")
    assert breakdown.stt == Decimal("100.000")
    assert breakdown.exchange_turnover_fee == Decimal("3.450")
    assert breakdown.ipft == Decimal("0.0001")
    assert breakdown.sebi_turnover_fee == Decimal("0.100")
    assert breakdown.stamp_duty == Decimal("15.000")

    expected_gst_base = Decimal("20.00") + Decimal("3.450") + Decimal("0.100") + Decimal("0.0001")
    assert expected_gst_base == Decimal("23.5501")
    expected_gst = expected_gst_base * Decimal("0.18")
    assert breakdown.gst == expected_gst

    expected_taxes = (
        Decimal("100.000") + Decimal("3.450") + Decimal("0.0001") +
        Decimal("0.100") + Decimal("15.000") + expected_gst
    )
    assert breakdown.total_statutory_taxes == expected_taxes
    expected_charges = Decimal("20.00") + expected_taxes
    assert breakdown.total_charges == expected_charges
    assert breakdown.net_cash_flow == -(Decimal("100000.00") + expected_charges)

    assert breakdown.circular_ref == "NSE/FA/46730"
    assert len(breakdown.disclosures) == 1
    assert breakdown.disclosures[0] == SLAB_FLATTENING_DISCLOSURE


def test_delivery_sell_costs_stamp_duty_zero():
    """
    Test delivery SELL trade:
    - STT applies on sell leg for delivery (0.1%).
    - Stamp duty is ₹0 on sell leg (levied only on buyer under Indian Stamp Act).
    - Net cash flow is positive: +(Gross - Charges).
    """
    model = TransactionCostModel()
    trade_date = datetime.date(2024, 10, 15)  # Post-Oct-2024 uniform rate
    breakdown = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=50,
        price=Decimal("2000.00"),
    )

    assert breakdown.gross_amount == Decimal("100000.00")
    assert breakdown.stt == Decimal("100.000")  # 0.1%
    assert breakdown.stamp_duty == Decimal("0")   # ZERO on SELL
    assert breakdown.exchange_turnover_fee == Decimal("2.970")  # ₹297/cr (NSE/FA/64323)
    assert breakdown.ipft == Decimal("0.100")                  # ₹10/cr
    assert breakdown.sebi_turnover_fee == Decimal("0.100")      # ₹10/cr

    expected_gst = (Decimal("20.00") + Decimal("2.970") + Decimal("0.100") + Decimal("0.100")) * Decimal("0.18")
    assert breakdown.gst == expected_gst

    assert breakdown.net_cash_flow == (Decimal("100000.00") - breakdown.total_charges)
    assert breakdown.circular_ref == "NSE/FA/64323"
    # Post-Oct-2024 has NO slab flattening disclosure
    assert len(breakdown.disclosures) == 0


def test_intraday_buy_and_sell_stt_and_stamp_duty_asymmetry():
    """
    Test Intraday equity settlement rules:
    - BUY leg: STT is 0%, Stamp duty is 0.003%.
    - SELL leg: STT is 0.025%, Stamp duty is 0%.
    """
    model = TransactionCostModel()
    trade_date = datetime.date(2024, 5, 10)  # Circular NSE/FA/61137

    # 1. Intraday BUY
    buy = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.BUY,
        product=OrderProduct.INTRADAY,
        quantity=100,
        price=Decimal("500.00"),
    )
    assert buy.gross_amount == Decimal("50000.00")
    assert buy.stt == Decimal("0")  # Zero STT on intraday buy
    assert buy.stamp_duty == Decimal("50000.00") * Decimal("0.00003")  # 0.003% = ₹1.50
    assert buy.stamp_duty == Decimal("1.50000")

    # 2. Intraday SELL
    sell = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.SELL,
        product=OrderProduct.INTRADAY,
        quantity=100,
        price=Decimal("510.00"),
    )
    assert sell.gross_amount == Decimal("51000.00")
    assert sell.stt == Decimal("51000.00") * Decimal("0.00025")  # 0.025% = ₹12.75
    assert sell.stt == Decimal("12.75000")
    assert sell.stamp_duty == Decimal("0")  # Zero stamp duty on intraday sell


def test_historical_fee_schedules_transition():
    """
    Verify exact exchange fee computation across historical circular boundaries:
    - 2023-03-31: ₹345/cr (NSE/FA/46730)
    - 2023-04-01: ₹325/cr (NSE/FA/56129)
    - 2024-09-30: ₹322/cr (NSE/FA/61137)
    - 2024-10-01: ₹297/cr (NSE/FA/64323)
    - 2026-03-01: ₹306.99/cr (NSE/FA/73061)
    """
    model = TransactionCostModel()
    qty = 1000
    price = Decimal("1000.00")  # ₹10,00,000 (0.1 Crore)

    # 1. Pre-rollback (345/cr)
    c1 = model.compute_costs(datetime.date(2023, 3, 31), OrderSide.BUY, OrderProduct.DELIVERY, qty, price)
    assert c1.exchange_turnover_fee == Decimal("34.50")
    assert c1.ipft == Decimal("0.001")  # ₹0.01/cr on 0.1 cr

    # 2. Rollback (325/cr)
    c2 = model.compute_costs(datetime.date(2023, 4, 1), OrderSide.BUY, OrderProduct.DELIVERY, qty, price)
    assert c2.exchange_turnover_fee == Decimal("32.50")
    assert c2.ipft == Decimal("1.00")   # ₹10/cr on 0.1 cr

    # 3. 2024 revision (322/cr)
    c3 = model.compute_costs(datetime.date(2024, 9, 30), OrderSide.BUY, OrderProduct.DELIVERY, qty, price)
    assert c3.exchange_turnover_fee == Decimal("32.20")
    assert c3.ipft == Decimal("1.00")

    # 4. Uniform flat rate (297/cr)
    c4 = model.compute_costs(datetime.date(2024, 10, 1), OrderSide.BUY, OrderProduct.DELIVERY, qty, price)
    assert c4.exchange_turnover_fee == Decimal("29.70")
    assert c4.ipft == Decimal("1.00")

    # 5. 2026 circular (306.99/cr + 0.01/cr IPFT = ₹307/cr total)
    c5 = model.compute_costs(datetime.date(2026, 3, 1), OrderSide.BUY, OrderProduct.DELIVERY, qty, price)
    assert c5.exchange_turnover_fee == Decimal("30.699")
    assert c5.ipft == Decimal("0.001")
    assert (c5.exchange_turnover_fee + c5.ipft) == Decimal("30.700")  # Exact ₹307 per crore!


def test_cost_model_fail_closed_rejections():
    """Verify that cost model rejects floats, invalid dates, and out-of-bounds dates."""
    model = TransactionCostModel()
    valid_date = datetime.date(2024, 1, 15)

    # 1. Reject binary float in price
    with pytest.raises(CostCalculationError, match="finite positive Decimal"):
        model.compute_costs(valid_date, OrderSide.BUY, OrderProduct.DELIVERY, 10, 100.5)  # type: ignore

    # 2. Reject boolean in quantity
    with pytest.raises(CostCalculationError, match="positive integer"):
        model.compute_costs(valid_date, OrderSide.BUY, OrderProduct.DELIVERY, True, Decimal("100"))  # type: ignore

    # 3. Reject negative price
    with pytest.raises(CostCalculationError, match="finite positive Decimal"):
        model.compute_costs(valid_date, OrderSide.BUY, OrderProduct.DELIVERY, 10, Decimal("-100"))

    # 4. Reject unmapped historical date before 2021
    with pytest.raises(CriteriaValidationError, match="No governing NSE exchange fee schedule found"):
        model.compute_costs(datetime.date(2019, 1, 1), OrderSide.BUY, OrderProduct.DELIVERY, 10, Decimal("100"))


def test_paise_rounding_policy_at_breakdown_boundary_e6():
    """
    Verify E-6 remediation:
    Explicit paise rounding policy at the breakdown boundary quantizes
    all financial amounts to 2 decimal places (0.01 INR) for ledger reconciliation.
    """
    model = TransactionCostModel()
    trade_date = datetime.date(2026, 11, 11)

    # 1. Raw breakdown retains full mathematical precision
    raw = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        price=Decimal("1000.00"),
        round_to_paise=False,
    )
    assert raw.total_charges == Decimal("142.3406000000000")
    assert raw.total_charges.as_tuple().exponent <= -11

    # 2. to_paise() rounds currency values to paise (exponent -2)
    paise_rounded = raw.to_paise()
    assert paise_rounded.total_charges.as_tuple().exponent == -2
    assert paise_rounded.net_cash_flow.as_tuple().exponent == -2
    assert paise_rounded.gross_amount.as_tuple().exponent == -2
    assert paise_rounded.total_charges == Decimal("142.34")
    assert paise_rounded.net_cash_flow == Decimal("-100142.34")

    # 3. Direct round_to_paise=True produces identical paise-rounded breakdown
    direct_paise = model.compute_costs(
        trade_date=trade_date,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        price=Decimal("1000.00"),
        round_to_paise=True,
    )
    assert direct_paise.total_charges == Decimal("142.34")
    assert direct_paise.total_charges.as_tuple().exponent == -2


