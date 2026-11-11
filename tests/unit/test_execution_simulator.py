"""Unit Tests for Single Authoritative Execution Fill Simulator and Slippage Model.

Verifies:
- E-1: Circuit freeze evaluation on fill reference price (no lookahead; locked bar rejection)
- E-2: Fail-closed series evidence requirement (bare PriceBar rejected; BE rejected under EQ policy)
- E-3: Calendar latency measurement and lookahead rejection (REJECTED_LOOKAHEAD, latency_sessions recorded)
- E-4: Minimum daily turnover eligibility gate enforcement (min_daily_turnover_crore)
- E-5: Pure Decimal non-default alpha calculation in SlippageModel
- Volume participation cap and partial fill behavior
- Gap execution realism (stop orders fill at Open on gap-down, not stop price)
"""

import datetime
from decimal import Decimal
from typing import Optional
import pytest

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
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


def _make_obs(
    instrument_id: str = "TCS",
    trade_date: datetime.date = datetime.date(2024, 10, 15),
    open_price: Decimal = Decimal("1000.00"),
    high_price: Decimal = Decimal("1050.00"),
    low_price: Decimal = Decimal("980.00"),
    close_price: Decimal = Decimal("1020.00"),
    volume: int = 100000,
    raw_series_code: str = "EQ",
    series_classification: ExchangeSeries = ExchangeSeries.EQ,
    upper_circuit_limit: Optional[Decimal] = None,
    lower_circuit_limit: Optional[Decimal] = None,
) -> ExchangeSessionObservation:
    bar = _make_bar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )
    return ExchangeSessionObservation(
        instrument_id=instrument_id,
        trade_date=trade_date,
        raw_series_code=raw_series_code,
        series_classification=series_classification,
        isin=f"INE{instrument_id[:5]}01",
        price_bar=bar,
        upper_circuit_limit=upper_circuit_limit,
        lower_circuit_limit=lower_circuit_limit,
    )


def test_latency_measurement_and_lookahead_gate_e3():
    """
    Verify E-3 remediation:
    1. Lookahead order (target_date <= signal_date) emits FillStatus.REJECTED_LOOKAHEAD.
    2. Measured latency is recorded on ExecutionFillResult.latency_sessions.
    3. min_execution_latency_sessions=2 correctly rejects T+1 (latency 1) and accepts T+2 (latency 2).
    4. 30-session gap correctly computes and records elapsed trading sessions.
    """
    simulator = ExecutionFillSimulator()

    # 1. Reverse-dated lookahead order -> REJECTED_LOOKAHEAD
    lookahead_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 10, 15),
        target_date=datetime.date(2024, 10, 14),
    )
    obs_t1 = _make_obs(trade_date=datetime.date(2024, 10, 14))
    res_lookahead = simulator.simulate_order(lookahead_order, obs_t1)
    assert res_lookahead.status == FillStatus.REJECTED_LOOKAHEAD
    assert res_lookahead.latency_sessions == 0
    assert "lookahead prohibited" in (res_lookahead.rejection_reason or "")

    # 2. Same-day lookahead order -> REJECTED_LOOKAHEAD
    same_day_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 10, 15),
        target_date=datetime.date(2024, 10, 15),
    )
    obs_same = _make_obs(trade_date=datetime.date(2024, 10, 15))
    res_same = simulator.simulate_order(same_day_order, obs_same)
    assert res_same.status == FillStatus.REJECTED_LOOKAHEAD
    assert res_same.latency_sessions == 0

    # 3. Standard T+1 next session (2024-10-14 -> 2024-10-15) -> Latency 1
    t1_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 10, 14),
        target_date=datetime.date(2024, 10, 15),
    )
    res_t1 = simulator.simulate_order(t1_order, obs_same)
    assert res_t1.status == FillStatus.FILLED
    assert res_t1.latency_sessions == 1

    # 4. Latency gate with min_execution_latency_sessions = 2
    criteria = load_go_no_go_criteria()
    # Modify criteria to require min 2 sessions
    object.__setattr__(criteria, "min_execution_latency_sessions", 2)
    sim_latency2 = ExecutionFillSimulator(criteria=criteria)

    # T+1 order is rejected with REJECTED_INVALID_LATENCY
    res_lat_fail = sim_latency2.simulate_order(t1_order, obs_same)
    assert res_lat_fail.status == FillStatus.REJECTED_INVALID_LATENCY
    assert res_lat_fail.latency_sessions == 1

    # T+2 order (2024-10-14 -> 2024-10-16) passes!
    t2_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 10, 14),
        target_date=datetime.date(2024, 10, 16),
    )
    obs_t2 = _make_obs(trade_date=datetime.date(2024, 10, 16))
    res_lat_pass = sim_latency2.simulate_order(t2_order, obs_t2)
    assert res_lat_pass.status == FillStatus.FILLED
    assert res_lat_pass.latency_sessions == 2

    # 5. 30-session gap (2024-01-02 -> 2024-02-01) computes measured business days
    gap_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 2, 1),
    )
    obs_gap = _make_obs(trade_date=datetime.date(2024, 2, 1))
    res_gap = simulator.simulate_order(gap_order, obs_gap)
    assert res_gap.status == FillStatus.FILLED
    assert res_gap.latency_sessions == 22  # 22 weekdays between 2024-01-02 and 2024-02-01


def test_series_evidence_requirement_and_be_rejection_e2():
    """
    Verify E-2 remediation:
    - Bare PriceBar without explicit series evidence is rejected (fail-closed; no silent EQ default).
    - ExchangeSessionObservation with BE series is rejected for entry under APPROVED_EQ_ONLY_POLICY.
    - ExchangeSessionObservation with EQ series fills successfully.
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

    # 1. Bare PriceBar fails closed: no implicit assumption of EQ
    bare_bar = _make_bar(instrument_id="RELIANCE", trade_date=t1)
    res_bare = simulator.simulate_order(order, bare_bar)
    assert res_bare.status == FillStatus.REJECTED_INELIGIBLE_SERIES
    assert "bare PriceBar cannot be assumed to be ExchangeSeries.EQ" in (res_bare.rejection_reason or "")

    # 2. BE Observation is rejected under EQ-only policy
    be_obs = _make_obs(
        instrument_id="RELIANCE",
        trade_date=t1,
        raw_series_code="BE",
        series_classification=ExchangeSeries.BE,
    )
    res_be = simulator.simulate_order(order, be_obs)
    assert res_be.status == FillStatus.REJECTED_INELIGIBLE_SERIES
    assert "not eligible for entry" in (res_be.rejection_reason or "")

    # 3. EQ Observation succeeds
    eq_obs = _make_obs(
        instrument_id="RELIANCE",
        trade_date=t1,
        raw_series_code="EQ",
        series_classification=ExchangeSeries.EQ,
    )
    res_eq = simulator.simulate_order(order, eq_obs)
    assert res_eq.status == FillStatus.FILLED
    assert res_eq.filled_quantity == 50


def test_circuit_freeze_reference_price_and_locked_bar_e1():
    """
    Verify E-1 remediation:
    - Legal open fill: Open 1000, High 1050 (circuit limit). Does NOT reject because Open < Circuit!
    - Reject upper circuit fill: Open 1050, High 1050, Circuit 1050. Rejects because Open >= Circuit!
    - Reject locked bar without limits: O=H=L=1050 with no limits. Rejects because high == low (locked)!
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    buy_order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        signal_date=t0,
        target_date=t1,
    )

    # 1. Open 1000, High 1050, Upper Circuit 1050
    # In b0ceaeb, this was rejected because High == 1050 (lookahead).
    # Now: Open is 1000 < 1050, so the open fill is legal and executes!
    obs_legal_open = _make_obs(
        trade_date=t1,
        open_price=Decimal("1000.00"),
        high_price=Decimal("1050.00"),
        low_price=Decimal("995.00"),
        close_price=Decimal("1048.00"),
        upper_circuit_limit=Decimal("1050.00"),
    )
    res_legal = simulator.simulate_order(buy_order, obs_legal_open)
    assert res_legal.status == FillStatus.FILLED
    assert res_legal.executed_price is not None
    assert res_legal.executed_price >= Decimal("1000.00")
    assert res_legal.executed_price <= Decimal("1050.00")

    # 2. Open 1050, High 1050, Upper Circuit 1050
    # Fill reference price (Open) is at the circuit limit -> zero ask depth, rejected!
    obs_circuit_open = _make_obs(
        trade_date=t1,
        open_price=Decimal("1050.00"),
        high_price=Decimal("1050.00"),
        low_price=Decimal("1020.00"),
        close_price=Decimal("1050.00"),
        upper_circuit_limit=Decimal("1050.00"),
    )
    res_circ_open = simulator.simulate_order(buy_order, obs_circuit_open)
    assert res_circ_open.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert res_circ_open.filled_quantity == 0

    # 3. Locked bar (O=H=L=1050) with NO limits supplied
    # In b0ceaeb, this was filled because limits were None (freeze rule was silently off).
    # Now: high == low locked bar is detected and rejected!
    obs_locked = _make_obs(
        trade_date=t1,
        open_price=Decimal("1050.00"),
        high_price=Decimal("1050.00"),
        low_price=Decimal("1050.00"),
        close_price=Decimal("1050.00"),
        upper_circuit_limit=None,
    )
    res_locked = simulator.simulate_order(buy_order, obs_locked)
    assert res_locked.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert res_locked.filled_quantity == 0


def test_min_daily_turnover_eligibility_gate_e4():
    """
    Verify E-4 remediation:
    - min_daily_turnover_crore from criteria is actively enforced.
    - Instrument with turnover below ₹5 Crore is rejected with REJECTED_INSUFFICIENT_TURNOVER.
    - Instrument with turnover >= ₹5 Crore passes.
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    order = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=t0,
        target_date=t1,
    )

    # 1. Illiquid scrip: volume=100, price=1000 -> Turnover ₹1,00,000 (0.01 Crore < 5.0 Crore)
    obs_illiquid = _make_obs(
        trade_date=t1,
        volume=100,
        open_price=Decimal("1000.00"),
    )
    res_illiquid = simulator.simulate_order(order, obs_illiquid)
    assert res_illiquid.status == FillStatus.REJECTED_INSUFFICIENT_TURNOVER
    assert "below minimum liquidity threshold" in (res_illiquid.rejection_reason or "")

    # 2. Liquid scrip: volume=100,000, price=1000 -> Turnover ₹10 Crore (>= 5.0 Crore)
    obs_liquid = _make_obs(
        trade_date=t1,
        volume=100000,
        open_price=Decimal("1000.00"),
    )
    res_liquid = simulator.simulate_order(order, obs_liquid)
    assert res_liquid.status == FillStatus.FILLED


def test_slippage_model_pure_decimal_power_without_float_e5():
    """
    Verify E-5 remediation:
    Non-default impact exponent (alpha = 0.6) uses exact Decimal arithmetic with zero float conversion.
    """
    model = SlippageModel(
        half_spread_bps=Decimal("5.0"),
        impact_kappa=Decimal("0.10"),
        impact_alpha=Decimal("0.6"),
    )
    res = model.compute_slippage(
        reference_price=Decimal("1000.00"),
        quantity=100,
        side=OrderSide.BUY,
        session_volume=50000,
        average_daily_turnover=Decimal("10000000.00"),
    )
    assert isinstance(res.impact_rate, Decimal)
    assert isinstance(res.slippage_rate, Decimal)
    assert isinstance(res.adjusted_price, Decimal)
    # Verification that no float was used: precision remains exact Decimal
    expected_part = Decimal(100 * 1000) / Decimal("10000000.00")
    expected_impact = Decimal("0.10") * (expected_part ** Decimal("0.6"))
    assert res.impact_rate == expected_impact


def test_volume_participation_cap_and_partial_fill():
    """
    Verify volume participation cap (3.0% of session volume):
    - Volume = 100,000 shares -> Max allowed fill = 3,000 shares.
    - 5,000 shares without partial fill -> REJECTED_VOLUME_CAP.
    - 5,000 shares with partial fill -> PARTIALLY_FILLED (3,000 filled, 2,000 unfilled).
    - 0 volume session -> REJECTED_ZERO_LIQUIDITY.
    """
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()
    obs = _make_obs(trade_date=t1, volume=100000)

    # 1. Order for 5,000 shares without partial fill
    order_no_partial = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=5000,
        signal_date=t0,
        target_date=t1,
        allow_partial_fill=False,
    )
    res_no_part = simulator.simulate_order(order_no_partial, obs)
    assert res_no_part.status == FillStatus.REJECTED_VOLUME_CAP
    assert res_no_part.filled_quantity == 0
    assert res_no_part.unfilled_quantity == 5000

    # 2. Order for 5,000 shares with partial fill allowed
    order_partial = ExecutionOrder(
        instrument_id="TCS",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=5000,
        signal_date=t0,
        target_date=t1,
        allow_partial_fill=True,
    )
    res_part = simulator.simulate_order(order_partial, obs)
    assert res_part.status == FillStatus.PARTIALLY_FILLED
    assert res_part.filled_quantity == 3000  # 3.0% of 100,000
    assert res_part.unfilled_quantity == 2000

    # 3. Zero-volume session
    zero_vol_obs = _make_obs(trade_date=t1, volume=0)
    res_zero = simulator.simulate_order(order_partial, zero_vol_obs)
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

    gap_obs = _make_obs(
        trade_date=t1,
        open_price=Decimal("950.00"),
        high_price=Decimal("960.00"),
        low_price=Decimal("940.00"),
        close_price=Decimal("945.00"),
        volume=100000,
    )

    result = simulator.simulate_order(stop_order, gap_obs)
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
    obs_triggered = _make_obs(
        trade_date=t1,
        open_price=Decimal("1005.00"),
        high_price=Decimal("1020.00"),
        low_price=Decimal("990.00"),
        close_price=Decimal("1000.00"),
    )
    res_limit = simulator.simulate_order(buy_limit, obs_triggered)
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
    res_untriggered = simulator.simulate_order(buy_untriggered, obs_triggered)
    assert res_untriggered.status == FillStatus.UNTRIGGERED
    assert res_untriggered.filled_quantity == 0


def test_intraday_stop_loss_trigger_and_untriggered():
    """Verify intraday stop-loss trigger when open is above stop price."""
    t0 = datetime.date(2024, 10, 14)
    t1 = datetime.date(2024, 10, 15)
    simulator = ExecutionFillSimulator()

    obs = _make_obs(
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
    res_trig = simulator.simulate_order(stop_triggered, obs)
    assert res_trig.status == FillStatus.FILLED
    assert res_trig.executed_price is not None
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
    res_untrig = simulator.simulate_order(stop_untrig, obs)
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
    obs = _make_obs(trade_date=t1)
    result = simulator.simulate_order(order, obs)

    assert result.status == FillStatus.FILLED
    assert result.costs is not None
    assert result.costs.trade_date == t1
    assert result.costs.quantity == 100
    assert result.costs.total_charges > Decimal("0")
    assert result.costs.net_cash_flow < Decimal("0")  # Buy is cash outflow
    assert result.slippage is not None
    assert result.slippage.slippage_rate > Decimal("0")
    assert result.latency_sessions == 1


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
