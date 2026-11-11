"""Unit Tests for Single Authoritative Execution Fill Simulator and Slippage Model.

Verifies:
- Next-session invariant and zero lookahead enforcement
- Series eligibility policy separation (EQ allowed, BE rejected for entry under APPROVED_EQ_ONLY_POLICY)
- Circuit filter freeze fill restrictions (no BUY at Upper Circuit, no SELL at Lower Circuit)
- Volume participation cap and partial fill behavior
- Gap execution realism (stop orders fill at Open on gap-down, not stop price)
- Non-linear slippage calculation and market impact scaling
"""

import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.slippage import SlippageModel, SlippageResult
from signal_core.execution.types import (
    ExecutionOrder,
    ExecutionOrderValidationError,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)


def _make_bar(
    instrument_id: str = "TCS",
    trade_date: datetime.date = datetime.date(2024, 10, 15),
    open_price: Decimal = Decimal("1000.00"),
    high_price: Decimal = Decimal("1050.00"),
    low_price: Decimal = Decimal("980.00"),
    close_price: Decimal = Decimal("1020.00"),
    volume: int = 100000,
) -> PriceBar:
    return PriceBar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


def test_next_session_invariant_and_zero_lookahead_rejections():
    """Verify that same-session or reverse-dated orders are rejected at instantiation."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)

    # 1. Reject same-session execution (target == signal)
    with pytest.raises(ExecutionOrderValidationError, match="Next-session invariant violated"):
        ExecutionOrder(
            instrument_id="TCS",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=10,
            signal_date=t0,
            target_date=t0,  # Same day prohibited!
        )

    # 2. Reject lookahead reverse execution (target < signal)
    with pytest.raises(ExecutionOrderValidationError, match="Next-session invariant violated"):
        ExecutionOrder(
            instrument_id="TCS",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=10,
            signal_date=t1,
            target_date=t0,
        )

    # 3. Reject session date mismatch in simulator
    order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=t0,
        target_date=t1,
    )
    simulator = ExecutionFillSimulator()
    wrong_bar = _make_bar(trade_date=datetime.date(2024, 10, 16))
    with pytest.raises(ExecutionOrderValidationError, match="Session date mismatch"):
        simulator.simulate_order(order, wrong_bar)

    # 4. Reject instrument mismatch
    wrong_inst_bar = _make_bar(instrument_id="INFY", trade_date=t1)
    with pytest.raises(ExecutionOrderValidationError, match="Instrument mismatch"):
        simulator.simulate_order(order, wrong_inst_bar)


def test_series_eligibility_policy_eq_vs_be_entry():
    """
    Verify SEBI/NSE series settlement separation:
    - EQ observation is permitted for BUY entry under APPROVED_EQ_ONLY_POLICY.
    - BE observation is rejected for BUY entry under APPROVED_EQ_ONLY_POLICY.
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    order = ExecutionOrder(
        instrument_id="RELIANCE",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
    )
    simulator = ExecutionFillSimulator(eligibility_policy=APPROVED_EQ_ONLY_POLICY)

    # 1. EQ Observation -> Success Fill
    eq_bar = _make_bar(instrument_id="RELIANCE", trade_date=t1)
    eq_obs = ExchangeSessionObservation(
        instrument_id="RELIANCE",
        trade_date=t1,
        raw_series_code="EQ",
        series_classification=ExchangeSeries.EQ,
        isin="INE002A01018",
        price_bar=eq_bar,
    )
    result_eq = simulator.simulate_order(order, eq_obs)
    assert result_eq.status == FillStatus.FILLED
    assert result_eq.filled_quantity == 50
    assert result_eq.executed_price is not None

    # 2. BE Observation -> Rejection under EQ-only policy
    be_obs = ExchangeSessionObservation(
        instrument_id="RELIANCE",
        trade_date=t1,
        raw_series_code="BE",
        series_classification=ExchangeSeries.BE,
        isin="INE002A01018",
        price_bar=eq_bar,
    )
    result_be = simulator.simulate_order(order, be_obs)
    assert result_be.status == FillStatus.REJECTED_INELIGIBLE_SERIES
    assert result_be.filled_quantity == 0
    assert result_be.executed_price is None
    assert "not eligible for entry" in (result_be.rejection_reason or "")


def test_circuit_freeze_invariants():
    """
    Verify circuit freeze invariants per Rule 5.3 & 7:
    - Never fill BUY if High hit Upper Circuit limit (ask depth = 0; buyers rationed).
    - Never fill SELL if Low hit Lower Circuit limit (bid depth = 0; sellers trapped).
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    # 1. BUY at Upper Circuit Limit
    buy_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
    )
    upper_circuit = Decimal("1050.00")
    bar_upper = _make_bar(trade_date=t1, high_price=Decimal("1050.00"))  # High hits circuit!
    res_upper = simulator.simulate_order(buy_order, bar_upper, upper_circuit_limit=upper_circuit)

    assert res_upper.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert res_upper.filled_quantity == 0
    assert "zero ask liquidity" in (res_upper.rejection_reason or "")

    # 2. SELL / Stop-Loss at Lower Circuit Limit
    sell_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("990.00"),
    )
    lower_circuit = Decimal("980.00")
    bar_lower = _make_bar(trade_date=t1, low_price=Decimal("980.00"))  # Low hits circuit!
    res_lower = simulator.simulate_order(sell_order, bar_lower, lower_circuit_limit=lower_circuit)

    assert res_lower.status == FillStatus.REJECTED_LOWER_CIRCUIT
    assert res_lower.filled_quantity == 0
    assert "sellers trapped" in (res_lower.rejection_reason or "")


def test_volume_participation_cap_and_partial_fill():
    """
    Verify volume participation cap (3.0% of session volume):
    - Volume = 10,000 shares -> Max allowed fill = 300 shares.
    - 500 shares without partial fill -> REJECTED_VOLUME_CAP.
    - 500 shares with partial fill -> PARTIALLY_FILLED (300 filled, 200 unfilled).
    - 0 volume session -> REJECTED_ZERO_LIQUIDITY.
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()
    bar = _make_bar(trade_date=t1, volume=10000)

    # 1. Order for 500 shares without partial fill
    order_no_partial = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=500,
        signal_date=t0,
        target_date=t1,
        allow_partial_fill=False,
    )
    res_no_part = simulator.simulate_order(order_no_partial, bar)
    assert res_no_part.status == FillStatus.REJECTED_VOLUME_CAP
    assert res_no_part.filled_quantity == 0
    assert res_no_part.unfilled_quantity == 500

    # 2. Order for 500 shares with partial fill allowed
    order_partial = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=500,
        signal_date=t0,
        target_date=t1,
        allow_partial_fill=True,
    )
    res_part = simulator.simulate_order(order_partial, bar)
    assert res_part.status == FillStatus.PARTIALLY_FILLED
    assert res_part.filled_quantity == 300  # 3.0% of 10,000
    assert res_part.unfilled_quantity == 200

    # 3. Zero-volume bar
    zero_vol_bar = _make_bar(trade_date=t1, volume=0)
    res_zero = simulator.simulate_order(order_partial, zero_vol_bar)
    assert res_zero.status == FillStatus.REJECTED_ZERO_LIQUIDITY
    assert res_zero.filled_quantity == 0


def test_gap_down_stop_loss_realism():
    """
    Verify stop-loss execution realism on gap-down:
    - Stop loss price: ₹1000.00
    - Bar opens gap-down at ₹950.00 (Low: ₹940, High: ₹960)
    - Execution MUST fill based on Open (₹950) with slippage downward, NOT at ₹1000!
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    stop_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=100,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("1000.00"),
    )

    gap_bar = _make_bar(
        trade_date=t1,
        open_price=Decimal("950.00"),
        high_price=Decimal("960.00"),
        low_price=Decimal("940.00"),
        close_price=Decimal("945.00"),
        volume=100000,
    )

    result = simulator.simulate_order(stop_order, gap_bar)
    assert result.status == FillStatus.FILLED
    assert result.executed_price is not None
    # Executed price must be <= ₹950.00 (open price minus adverse slippage), never 1000!
    assert result.executed_price <= Decimal("950.00")
    assert result.executed_price >= Decimal("940.00")  # Bounded by session low


def test_limit_order_execution_and_price_boundary():
    """Verify limit order trigger and boundary behavior."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    # 1. Buy limit order where limit is above session low (triggered)
    buy_limit = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("1010.00"),
    )
    bar_triggered = _make_bar(
        trade_date=t1,
        open_price=Decimal("1005.00"),
        high_price=Decimal("1020.00"),
        low_price=Decimal("990.00"),
        close_price=Decimal("1000.00"),
    )
    res_limit = simulator.simulate_order(buy_limit, bar_triggered)
    assert res_limit.status == FillStatus.FILLED
    assert res_limit.executed_price is not None
    assert res_limit.executed_price <= Decimal("1010.00")  # Bounded by limit!

    # 2. Buy limit order where limit is below session low (untriggered)
    buy_untriggered = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("980.00"),
    )
    res_untriggered = simulator.simulate_order(buy_untriggered, bar_triggered)
    assert res_untriggered.status == FillStatus.UNTRIGGERED
    assert res_untriggered.filled_quantity == 0


def test_intraday_stop_loss_trigger_and_untriggered():
    """Verify intraday stop-loss trigger when open is above stop price."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    bar = _make_bar(
        trade_date=t1,
        open_price=Decimal("1050.00"),
        high_price=Decimal("1060.00"),
        low_price=Decimal("990.00"),
        close_price=Decimal("1000.00"),
    )

    # 1. Stop loss at 1000 (Low touches 990 -> triggered at stop price)
    stop_triggered = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("1000.00"),
    )
    res_trig = simulator.simulate_order(stop_triggered, bar)
    assert res_trig.status == FillStatus.FILLED
    assert res_trig.executed_price is not None
    # Reference is 1000.00 minus slippage
    assert res_trig.executed_price <= Decimal("1000.00")
    assert res_trig.executed_price >= Decimal("990.00")

    # 2. Stop loss at 980 (Low is 990 -> untriggered)
    stop_untrig = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("980.00"),
    )
    res_untrig = simulator.simulate_order(stop_untrig, bar)
    assert res_untrig.status == FillStatus.UNTRIGGERED
    assert res_untrig.filled_quantity == 0


def test_fill_result_statutory_costs_integration():
    """Verify that a filled order contains full TransactionCostBreakdown."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()
    order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        signal_date=t0,
        target_date=t1,
    )
    bar = _make_bar(trade_date=t1)
    result = simulator.simulate_order(order, bar)

    assert result.status == FillStatus.FILLED
    assert result.costs is not None
    assert result.costs.trade_date == t1
    assert result.costs.quantity == 100
    assert result.costs.total_charges > Decimal("0")
    assert result.costs.net_cash_flow < Decimal("0")  # Buy is cash outflow
    assert result.slippage is not None
    assert result.slippage.slippage_rate > Decimal("0")


def test_execution_order_validation_rejects_floats_and_booleans():
    """Verify strict rejection of floats, booleans, and negative numbers in ExecutionOrder."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)

    # Boolean quantity
    with pytest.raises(ExecutionOrderValidationError, match="positive integer"):
        ExecutionOrder("TCS", OrderSide.BUY, OrderProduct.DELIVERY, True, t0, t1)  # type: ignore

    # Zero quantity
    with pytest.raises(ExecutionOrderValidationError, match="positive integer"):
        ExecutionOrder("TCS", OrderSide.BUY, OrderProduct.DELIVERY, 0, t0, t1)

    # Negative quantity
    with pytest.raises(ExecutionOrderValidationError, match="positive integer"):
        ExecutionOrder("TCS", OrderSide.BUY, OrderProduct.DELIVERY, -10, t0, t1)

    # Float limit price
    with pytest.raises(ExecutionOrderValidationError, match="finite positive Decimal limit_price"):
        ExecutionOrder("TCS", OrderSide.BUY, OrderProduct.DELIVERY, 10, t0, t1, OrderType.LIMIT, limit_price=100.5)  # type: ignore

    # Non-finite Decimal limit price
    with pytest.raises(ExecutionOrderValidationError, match="finite positive Decimal limit_price"):
        ExecutionOrder("TCS", OrderSide.BUY, OrderProduct.DELIVERY, 10, t0, t1, OrderType.LIMIT, limit_price=Decimal("NaN"))



def test_slippage_model_scaling_and_mathematics():
    """
    Verify non-linear slippage model:
    - Slippage Rate = (Spread / 2) + kappa * sqrt(Order Value / ADT)
    - Larger order results in higher slippage rate.
    """
    model = SlippageModel(
        half_spread_bps=Decimal("5.0"),   # 0.0005
        impact_kappa=Decimal("0.10"),
        impact_alpha=Decimal("0.5"),
    )
    ref_price = Decimal("1000.00")
    adt = Decimal("10000000.00")  # ₹1 Crore

    # Small order: 10 shares (₹10,000 = 0.001 of ADT)
    res_small = model.compute_slippage(
        reference_price=ref_price,
        quantity=10,
        side=OrderSide.BUY,
        session_volume=50000,
        average_daily_turnover=adt,
    )
    # Large order: 1000 shares (₹10,00,000 = 0.1 of ADT)
    res_large = model.compute_slippage(
        reference_price=ref_price,
        quantity=1000,
        side=OrderSide.BUY,
        session_volume=50000,
        average_daily_turnover=adt,
    )

    assert res_large.slippage_rate > res_small.slippage_rate
    assert res_large.adjusted_price > res_small.adjusted_price
    assert res_small.half_spread_rate == Decimal("0.0005")
    assert res_large.half_spread_rate == Decimal("0.0005")
