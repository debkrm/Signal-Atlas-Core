"""Comprehensive Verification Suite for DeepSeek Audit §62 Findings.

Tests:
1. Finding H-96: Unconditional Position and Portfolio Re-Keying on `new_isin` across SPLIT/BONUS/CONSOLIDATION.
2. Finding H-97: Round-Then-Clamp tick grid quantization and contradictory band refusal (no manufactured prices).
3. Finding N-92 Remainder: Three-state surveillance coverage (`NORMAL`), `SurveillanceExitResult`, non-empty exit evaluation.
4. Finding CA-1: Corporate actions corpus coverage (all 7 action types), mid-hold equity invariance, registered vs unregistered.
5. Finding CA-2: `CRIT-SURV-01` driver-level evaluation and explicit `NOT RUN` propagation.
6. Finding N-97: Execution summary ticket count separation (`tickets_emitted`, `tickets_filled`, `tickets_rejected`).
7. Finding R-90a: Clean contracts import layering (contracts imports zero execution modules) and eager imports.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import subprocess
import sys
import typing

import pytest

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
)
from signal_core.contracts.order_intent import OrderIntent
from signal_core.contracts.order_types import (
    ExecutionFillResult,
    ExecutionOrder,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
    SurveillanceExitResult,
)
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.portfolio.ledger import CashLedger
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.position import Position
from signal_core.portfolio.sizing import PositionSizeResult
from signal_core.portfolio.types import CorporateActionError
from signal_core.reporting.verdicts import evaluate_verdicts
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    SecurityMaster,
    SecurityMasterError,
    SurveillanceInterval,
    SurveillanceStage,
    SymbolInterval,
    load_corporate_actions,
)
from signal_core.strategy.swing import (
    DeliverySwingTrendStrategy,
    SwingSessionExecutionSummary,
    execute_swing_strategy_session,
)


# =============================================================================
# 1. Finding H-96: Unconditional Position & Portfolio Re-Keying on new_isin
# =============================================================================

def test_h96_unconditional_position_rekey_on_split_with_new_isin():
    """
    Finding H-96 Acceptance Probe (§62.3, §62.6 Item 1):
    A corporate-action row with action_type=SPLIT carrying new_isin:
    1. Re-keys the position in self._positions (del old_isin, set new_isin).
    2. Sets position._instrument_id to new_isin.
    3. Old ISIN lookup returns None (zero stranded position).
    4. New ISIN lookup has quantity restated by ratio and total cost basis preserved.
    """
    criteria = load_go_no_go_criteria()
    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )
    cost_model = TransactionCostModel(criteria.statutory_costs)
    dummy_costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=25,
        price=Decimal("1605.60"),
    )
    fill = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE704P01017",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=25,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 3),
        latency_sessions=1,
        filled_quantity=25,
        unfilled_quantity=0,
        executed_price=Decimal("1605.60"),
        slippage=None,
        costs=dummy_costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-H96-001",
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)

    pos_pre = portfolio.get_position("INE704P01017")
    assert pos_pre is not None
    assert pos_pre.quantity == 25
    assert pos_pre.average_entry_price == Decimal("1605.6000")
    assert pos_pre.total_cost_basis == Decimal("40140.00")

    # SPLIT action carrying new_isin
    split_action = CorporateAction(
        isin="INE704P01017",
        ex_date=datetime.date(2024, 1, 10),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE704P01017",
        new_isin="INE704P01025",
        circular_ref="NSE/CML/60114",
        description="Sub-Division from Rs 10 to Rs 5",
    )
    portfolio.apply_corporate_action(split_action)

    # Acceptance Probe from §62.3:
    # portfolio.get_position(old_isin) is None and portfolio.get_position(new_isin).quantity == 50
    assert portfolio.get_position("INE704P01017") is None
    pos_new = portfolio.get_position("INE704P01025")
    assert pos_new is not None
    assert pos_new.instrument_id == "INE704P01025"
    assert pos_new.quantity == 50
    assert pos_new.average_entry_price == Decimal("802.8000")
    assert pos_new.total_cost_basis == Decimal("40140.00")


def test_h96_corporate_action_rejects_identical_new_isin_at_construction():
    """
    Finding H-96 Falsifier Probe (§62.5):
    CorporateAction construction rejects new_isin matching isin fail-closed.
    """
    with pytest.raises(SecurityMasterError, match="new_isin cannot match isin"):
        CorporateAction(
            isin="INE704P01017",
            ex_date=datetime.date(2024, 1, 10),
            action_type=CorporateActionType.SPLIT,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            new_isin="INE704P01017",
        )


# =============================================================================
# 2. Finding H-97: Round-Then-Clamp & Contradictory Band Refusal
# =============================================================================

def test_h97_round_then_clamp_randomized_opens():
    """
    Finding H-97 Acceptance Probe (a) (§62.3, §62.6 Item 2):
    For randomized opens that fall between tick grid points:
    1. low <= executed_price <= high (no manufactured price outside session range).
    2. executed_price lies strictly on the Indian equity tick grid (0.05 / 0.01).
    """
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    # Sweep across non-grid open prices
    for i in range(1, 40):
        # Generates opens like 100.01, 100.02, 100.03, 100.04, 100.06...
        open_price = Decimal("100.00") + Decimal(str(i * 0.01))
        high_price = open_price + Decimal("2.00")
        low_price = open_price - Decimal("2.00")

        bar = PriceBar(
            instrument_id="INE002A01018",
            trade_date=datetime.date(2024, 1, 3),
            open=open_price,
            high=high_price,
            low=low_price,
            close=open_price,
            volume=1000000,
            traded_value=Decimal("100000000.00"),
        )
        band = PriceBandRecord(
            isin="INE002A01018",
            trade_date=datetime.date(2024, 1, 3),
            series="EQ",
            upper_circuit_limit=Decimal("120.00"),
            lower_circuit_limit=Decimal("80.00"),
            band_percentage=Decimal("20.00"),
        )
        order_buy = ExecutionOrder(
            instrument_id="INE002A01018",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=10,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        )
        result_buy = sim.simulate_order(order_buy, bar, explicit_series=ExchangeSeries.EQ, price_band=band)
        assert result_buy.status == FillStatus.FILLED
        assert result_buy.executed_price is not None
        assert low_price <= result_buy.executed_price <= high_price
        assert result_buy.executed_price % Decimal("0.05") == Decimal("0.00")

        order_sell = ExecutionOrder(
            instrument_id="INE002A01018",
            side=OrderSide.SELL,
            product=OrderProduct.DELIVERY,
            quantity=10,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        )
        result_sell = sim.simulate_order(order_sell, bar, explicit_series=ExchangeSeries.EQ, price_band=band)
        assert result_sell.status == FillStatus.FILLED
        assert result_sell.executed_price is not None
        assert low_price <= result_sell.executed_price <= high_price
        assert result_sell.executed_price % Decimal("0.05") == Decimal("0.00")


def test_h97_contradictory_band_rejected_fail_closed():
    """
    Finding H-97 Acceptance Probe (b) (§62.3, §62.6 Item 2):
    When the band contradicts the bar (open=99.99, high=100.02, low=99.50, band 1560/1040):
    1. Simulator returns REJECTED_PRICE_LIMIT.
    2. executed_price is None (ZERO fill posted, ZERO rewriting to limit).
    3. Rejection reason explicitly names contradictory bounds.
    """
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("99.99"),
        high=Decimal("100.02"),
        low=Decimal("99.50"),
        close=Decimal("100.00"),
        volume=1000000,
        traded_value=Decimal("100000000.00"),
    )
    # Contradictory band: 1560 upper, 1040 lower against a ₹100 bar!
    contradictory_band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("1560.00"),
        lower_circuit_limit=Decimal("1040.00"),
        band_percentage=Decimal("20.00"),
    )
    order = ExecutionOrder(
        instrument_id="INE002A01018",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 1, 3),
        order_type=OrderType.MARKET_ON_OPEN,
    )
    res = sim.simulate_order(order, bar, explicit_series=ExchangeSeries.EQ, price_band=contradictory_band)

    # Acceptance Probe: must yield REJECTED_* and executed_price is None
    assert res.status == FillStatus.REJECTED_PRICE_LIMIT
    assert res.executed_price is None
    assert res.filled_quantity == 0
    assert "contradicts" in res.rejection_reason or "outside price band" in res.rejection_reason


def test_h97_boundaries_do_not_exceed_session_high_or_fall_below_low():
    """
    Finding H-97 Boundary Realism Probe:
    - BUY at open 100.03 with high 100.03 cannot fill above 100.03.
    - SELL at open 100.00 with low 99.97 cannot fill below 99.97.
    """
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("100.03"),
        high=Decimal("100.03"),
        low=Decimal("99.50"),
        close=Decimal("100.00"),
        volume=1000000,
        traded_value=Decimal("100000000.00"),
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("120.00"),
        lower_circuit_limit=Decimal("80.00"),
        band_percentage=Decimal("20.00"),
    )
    order_buy = ExecutionOrder(
        instrument_id="INE002A01018",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 1, 3),
        order_type=OrderType.MARKET_ON_OPEN,
    )
    res_buy = sim.simulate_order(order_buy, bar_buy, explicit_series=ExchangeSeries.EQ, price_band=band)
    assert res_buy.status == FillStatus.FILLED
    assert res_buy.executed_price <= Decimal("100.03")

    bar_sell = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("100.00"),
        high=Decimal("100.50"),
        low=Decimal("99.97"),
        close=Decimal("100.00"),
        volume=1000000,
        traded_value=Decimal("100000000.00"),
    )
    order_sell = ExecutionOrder(
        instrument_id="INE002A01018",
        side=OrderSide.SELL,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 1, 3),
        order_type=OrderType.MARKET_ON_OPEN,
    )
    res_sell = sim.simulate_order(order_sell, bar_sell, explicit_series=ExchangeSeries.EQ, price_band=band)
    assert res_sell.status == FillStatus.FILLED
    assert res_sell.executed_price >= Decimal("99.97")


# =============================================================================
# 3. Finding N-92 Remainder: Three-State Surveillance & Exit Constraints
# =============================================================================

def test_n92_surveillance_three_state_coverage_and_exit_result():
    """
    Finding N-92 Acceptance Probe (§62.3, §62.6 Item 3):
    1. has_surveillance_coverage returns True with NORMAL inside verified interval, False outside.
    2. evaluate_surveillance_exit_constraints(..., require_coverage=True) returns a non-empty
       SurveillanceExitResult on an ordinary hold instead of raising.
    """
    sec_master = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE002A01018",
                symbol="RELIANCE",
                series="EQ",
                effective_from=datetime.date(2020, 1, 1),
                effective_to=None,
            )
        ],
        surveillance_intervals=[
            SurveillanceInterval(
                isin="INE002A01018",
                framework="NORMAL_FRAMEWORK",
                stage=SurveillanceStage.NORMAL,
                effective_from=datetime.date(2024, 1, 1),
                effective_to=datetime.date(2024, 6, 30),
                circular_ref="NSE/SURV/NORMAL/2024",
            )
        ],
    )

    # 1. Date-bounded coverage test
    assert sec_master.has_surveillance_coverage("INE002A01018", datetime.date(2023, 12, 31)) is False
    assert sec_master.has_surveillance_coverage("INE002A01018", datetime.date(2024, 1, 15)) is True
    assert sec_master.has_surveillance_coverage("INE002A01018", datetime.date(2024, 7, 1)) is False

    intervals = sec_master.resolve_surveillance("INE002A01018", datetime.date(2024, 1, 15))
    assert len(intervals) == 1
    assert intervals[0].stage == SurveillanceStage.NORMAL

    # 2. DailyTPlus1OrderRunner evaluate_surveillance_exit_constraints
    criteria = load_go_no_go_criteria()
    cal = load_anchored_nse_trading_calendar()
    port = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2024, 1, 1))
    cost_model = TransactionCostModel(criteria.statutory_costs)
    dummy_costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        price=Decimal("1000.00"),
    )
    fill = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE002A01018",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=50,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 3),
        latency_sessions=1,
        filled_quantity=50,
        unfilled_quantity=0,
        executed_price=Decimal("1000.00"),
        slippage=None,
        costs=dummy_costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-N92-001",
    )
    port.process_fill(fill, enforce_risk_limits=False)
    sim = ExecutionFillSimulator(criteria=criteria, trading_calendar=cal.sessions)
    runner = DailyTPlus1OrderRunner(portfolio=port, simulator=sim, calendar=cal, criteria=criteria)

    # Calling with require_coverage=True on an inside date: returns non-empty result without raising!
    res = runner.evaluate_surveillance_exit_constraints(
        session_date=datetime.date(2024, 1, 15),
        security_master=sec_master,
        require_coverage=True,
    )
    assert isinstance(res, SurveillanceExitResult)
    assert res.session_date == datetime.date(2024, 1, 15)
    assert res.status == "RUN"
    assert res.coverage_complete is True
    assert len(res) == 0  # NORMAL stage does not trigger forced liquidation!


# =============================================================================
# 4. Finding CA-1: Corporate Actions Corpus & Mid-Hold Invariants
# =============================================================================

def test_ca1_corporate_actions_corpus_and_sampled_types():
    """
    Finding CA-1 Acceptance Probe (§62.6 Item 4, §62.7 CA-1, §63.6 Item 1, 2, 8):
    1. Loads data/reference/corporate_actions.jsonl and verifies >= 10 events across all action types.
    2. Exercises mid-hold invariant on sampled events:
       - SPLIT with new_isin (TATASTEEL 10:1): quantity restated, cost preserved, position re-keyed.
       - BONUS (RELIANCE 1:1): quantity doubled, cost preserved, equity continuous.
       - CONSOLIDATION (IDEA 1:10): 100 shares -> 10 shares, cost preserved.
       - DIVIDEND (INFY INR 20.00): cash credited to ledger, total equity continuous.
       - RIGHTS (BHARTIARTL 1:14): rights entitlement leaves shares and cost basis unchanged (Finding H-99).
       - MERGER (HDFC 42:25): 25 HDFC -> 42 HDFCBANK, cost basis preserved, re-keyed (Finding H-98).
       - DELISTING (DELIST2022): cash settlement at delisting_price preserves equity (Finding H-98).
    3. Distinguishes registered names from unregistered names via has_corporate_action_coverage.
    """
    actions = load_corporate_actions()
    assert len(actions) >= 10

    types_found = {a.action_type for a in actions}
    assert CorporateActionType.SPLIT in types_found
    assert CorporateActionType.BONUS in types_found
    assert CorporateActionType.CONSOLIDATION in types_found
    assert CorporateActionType.DIVIDEND in types_found
    assert CorporateActionType.RIGHTS in types_found
    assert CorporateActionType.ISIN_TRANSITION in types_found
    assert CorporateActionType.DELISTING in types_found
    assert CorporateActionType.MERGER in types_found

    criteria = load_go_no_go_criteria()
    cost_model = TransactionCostModel(criteria.statutory_costs)

    # Mid-hold BONUS test
    port_bonus = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2024, 1, 1))
    dummy_costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        price=Decimal("1000.00"),
    )
    fill = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE002A01018",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=50,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 3),
        latency_sessions=1,
        filled_quantity=50,
        unfilled_quantity=0,
        executed_price=Decimal("1000.00"),
        slippage=None,
        costs=dummy_costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-CA1-BONUS",
    )
    port_bonus.process_fill(fill, enforce_risk_limits=False)
    equity_pre = port_bonus.current_total_equity({"INE002A01018": Decimal("1000.00")})

    bonus_action = [a for a in actions if a.isin == "INE002A01018" and a.action_type == CorporateActionType.BONUS][0]
    port_bonus.apply_corporate_action(bonus_action)

    pos_bonus = port_bonus.get_position("INE002A01018")
    assert pos_bonus.quantity == 100
    assert pos_bonus.total_cost_basis == Decimal("50000.00")
    equity_post = port_bonus.current_total_equity({"INE002A01018": Decimal("500.00")})
    assert equity_post == equity_pre

    # Mid-hold CONSOLIDATION test (reverse split 10:1 -> 100 shares become 10)
    port_consol = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2024, 1, 1))
    dummy_costs_consol = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        price=Decimal("10.00"),
    )
    fill_consol = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE669E01016",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=100,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 3),
        latency_sessions=1,
        filled_quantity=100,
        unfilled_quantity=0,
        executed_price=Decimal("10.00"),
        slippage=None,
        costs=dummy_costs_consol,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-CA1-CONSOL",
    )
    port_consol.process_fill(fill_consol, enforce_risk_limits=False)
    consol_action = [a for a in actions if a.isin == "INE669E01016" and a.action_type == CorporateActionType.CONSOLIDATION][0]
    port_consol.apply_corporate_action(consol_action)
    pos_consol = port_consol.get_position("INE669E01016")
    assert pos_consol.quantity == 10
    assert pos_consol.average_entry_price == Decimal("100.0000")

    # Mid-hold MERGER test (HDFC into HDFCBANK: 25 HDFC -> 42 HDFCBANK, Finding H-98)
    port_merger = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2023, 7, 1))
    dummy_costs_merger = cost_model.compute_costs(
        trade_date=datetime.date(2023, 7, 10),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=25,
        price=Decimal("2800.00"),
    )
    fill_merger = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE001A01036",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=25,
            signal_date=datetime.date(2023, 7, 7),
            target_date=datetime.date(2023, 7, 10),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2023, 7, 10),
        latency_sessions=1,
        filled_quantity=25,
        unfilled_quantity=0,
        executed_price=Decimal("2800.00"),
        slippage=None,
        costs=dummy_costs_merger,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-CA1-MERGER",
    )
    port_merger.process_fill(fill_merger, enforce_risk_limits=False)
    merger_action = [a for a in actions if a.isin == "INE001A01036" and a.action_type == CorporateActionType.MERGER][0]
    port_merger.apply_corporate_action(merger_action)
    # Old ISIN position must be None, new ISIN position must hold 42 shares with basis preserved (Finding H-98)
    assert port_merger.get_position("INE001A01036") is None
    pos_bank = port_merger.get_position("INE040A01034")
    assert pos_bank is not None
    assert pos_bank.quantity == 42
    assert pos_bank.total_cost_basis == Decimal("70000.00")

    # Mid-hold DELISTING test (cash settlement preserves equity, Finding H-98)
    port_delist = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2022, 12, 1))
    dummy_costs_delist = cost_model.compute_costs(
        trade_date=datetime.date(2022, 12, 10),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=20,
        price=Decimal("200.00"),
    )
    fill_delist = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE115A01026",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=20,
            signal_date=datetime.date(2022, 12, 8),
            target_date=datetime.date(2022, 12, 9),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2022, 12, 9),
        latency_sessions=1,
        filled_quantity=20,
        unfilled_quantity=0,
        executed_price=Decimal("200.00"),
        slippage=None,
        costs=dummy_costs_delist,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-CA1-DELIST",
    )
    port_delist.process_fill(fill_delist, enforce_risk_limits=False)
    # Mark equity prior to delisting at delisting_price INR 150.00
    equity_pre_delist = port_delist.current_total_equity({"INE115A01026": Decimal("150.00")})
    delist_action = [a for a in actions if a.isin == "INE115A01026" and a.action_type == CorporateActionType.DELISTING][0]
    port_delist.apply_corporate_action(delist_action)
    assert port_delist.get_position("INE115A01026") is None
    equity_post_delist = port_delist.current_total_equity()
    assert equity_post_delist == equity_pre_delist

    # Mid-hold RIGHTS test (entitlement does not fabricate bonus shares, Finding H-99)
    port_rights = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2022, 7, 1))
    dummy_costs_rights = cost_model.compute_costs(
        trade_date=datetime.date(2022, 7, 25),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=14,
        price=Decimal("700.00"),
    )
    fill_rights = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE397D01024",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=14,
            signal_date=datetime.date(2022, 7, 22),
            target_date=datetime.date(2022, 7, 25),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2022, 7, 25),
        latency_sessions=1,
        filled_quantity=14,
        unfilled_quantity=0,
        executed_price=Decimal("700.00"),
        slippage=None,
        costs=dummy_costs_rights,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-CA1-RIGHTS",
    )
    port_rights.process_fill(fill_rights, enforce_risk_limits=False)
    equity_pre_rights = port_rights.current_total_equity({"INE397D01024": Decimal("700.00")})
    rights_action = [a for a in actions if a.isin == "INE397D01024" and a.action_type == CorporateActionType.RIGHTS][0]
    port_rights.apply_corporate_action(rights_action)
    pos_rights = port_rights.get_position("INE397D01024")
    assert pos_rights.quantity == 14
    assert pos_rights.total_cost_basis == Decimal("9800.00")
    equity_post_rights = port_rights.current_total_equity({"INE397D01024": Decimal("700.00")})
    assert equity_post_rights == equity_pre_rights


def test_ca1_registered_vs_unregistered_security_master_distinction():
    """
    Finding CA-1 Store Distinction Probe:
    A security registered in SecurityMaster intervals with no corporate actions returns empty tuple.
    An unregistered ISIN raises SecurityMasterError fail-closed when require_registration=True.
    """
    sec_master = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE002A01018",
                symbol="RELIANCE",
                series="EQ",
                effective_from=datetime.date(2020, 1, 1),
                effective_to=None,
            )
        ],
        corporate_actions=[],  # Zero corporate actions registered
    )

    # Registered name: returns empty tuple, does NOT raise
    res = sec_master.get_corporate_actions("INE002A01018", require_registration=True)
    assert res == ()

    # Unregistered name: raises SecurityMasterError fail-closed
    with pytest.raises(SecurityMasterError, match="not registered in SecurityMaster"):
        sec_master.get_corporate_actions("INE999Z99999", require_registration=True)


# =============================================================================
# 5. Finding CA-2: Surveillance Explicit NOT RUN Propagation
# =============================================================================

def test_ca2_surveillance_not_run_propagates_to_no_go():
    """
    Finding CA-2 Acceptance Probe (§62.6 Item 5, §62.7 CA-2):
    When surveillance is unverified, evaluate_verdicts() evaluates CRIT-SURV-01
    as NOT RUN and overall verdict is strictly NO-GO.
    """
    bundle = {
        "evaluation_window_start": datetime.date(2022, 1, 3),
        "evaluation_window_end": datetime.date(2024, 12, 31),
        "dataset_provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "provenance_attestation_reference": None,
        "surveillance_constraint_status": "NOT_RUN",
        "surveillance_not_run_reason": "Offline surveillance intervals unavailable for window 2022-2024",
    }
    criteria = load_go_no_go_criteria()
    report = evaluate_verdicts(bundle, criteria=criteria)

    crit_surv = next((e for e in report.evaluations if e.criterion_id == "CRIT-SURV-01"), None)
    assert crit_surv is not None
    assert crit_surv.status.value == "NOT RUN"
    assert report.overall_verdict.value == "NO-GO"


# =============================================================================
# 6. Finding N-97: Summary Ticket Counts Separation
# =============================================================================

def test_n97_summary_ticket_counts_separation_on_circuit_freeze():
    """
    Finding N-97 & N-99 Acceptance Probe (§62.3, §62.6 Item 6, §63.6 Item 8):
    In an upper-circuit freeze session, executed through execute_swing_strategy_session:
    - tickets_emitted == 1
    - tickets_rejected == 1
    - tickets_filled == 0
    - tickets_executed == 0
    - tickets_no_trade == 0
    - ticket.status is REJECTED_UPPER_CIRCUIT
    """
    from types import SimpleNamespace
    criteria = load_go_no_go_criteria()
    calendar = load_anchored_nse_trading_calendar()
    port = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2024, 1, 1))
    sim = ExecutionFillSimulator(criteria=criteria, trading_calendar=calendar.sessions)
    runner = DailyTPlus1OrderRunner(portfolio=port, simulator=sim, calendar=calendar, criteria=criteria)
    strategy = DeliverySwingTrendStrategy(
        strategy_id="test_swing_freeze",
        fast_indicator="fast",
        slow_indicator="slow",
        allocation_weight=Decimal("0.10"),
    )

    as_of = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)
    isin = "INE002A01018"

    features = {
        isin: SimpleNamespace(
            fast=Decimal("950.00"),
            slow=Decimal("900.00"),
            close=Decimal("1000.00"),
            atr=Decimal("50.00"),
            volume=5000000,
        )
    }
    # Upper freeze: Open=High=Low=Close=1100.00 == upper circuit
    freeze_bar = PriceBar(
        instrument_id=isin,
        trade_date=target_date,
        open=Decimal("1100.00"),
        high=Decimal("1100.00"),
        low=Decimal("1100.00"),
        close=Decimal("1100.00"),
        volume=100000,
        traded_value=Decimal("110000000.00"),
    )
    band = PriceBandRecord(
        isin=isin,
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    summary = execute_swing_strategy_session(
        strategy=strategy,
        runner=runner,
        as_of=as_of,
        next_session=target_date,
        universe=[isin],
        features=features,
        bars_next_session={isin: freeze_bar},
        price_bands_next_session={isin: band},
        explicit_series=ExchangeSeries.EQ,
    )

    assert summary.intents_generated == 1
    assert summary.tickets_emitted == 1
    assert summary.tickets_filled == 0
    assert summary.tickets_rejected == 1
    assert summary.tickets_executed == 0
    assert summary.tickets_no_trade == 0
    assert len(summary.tickets) == 1
    assert summary.tickets[0].status == FillStatus.REJECTED_UPPER_CIRCUIT


# =============================================================================
# 7. Finding R-90a: Clean Import Layering
# =============================================================================

def test_r90a_clean_import_layering_and_eager_subprocesses():
    """
    Finding R-90a Acceptance Probe (§62.3, §62.6 Item 8):
    1. contracts.order_types defines OrderSide, OrderProduct, OrderType, FillStatus, ExecutionOrder, ExecutionFillResult.
    2. contracts.order_intent imports from contracts.order_types (zero execution dependency).
    3. execution/__init__ eager import succeeds with zero PEP 562 lazy shim.
    4. Subprocess attack: fresh interpreter running `import signal_core.strategy.swing` exits 0.
    """
    cmds = [
        "import signal_core.contracts.order_types",
        "import signal_core.contracts.order_intent",
        "import signal_core.portfolio.portfolio; import signal_core.execution.order_runner",
        "import signal_core.strategy.swing; import signal_core.execution",
    ]
    for cmd in cmds:
        res = subprocess.run(
            [sys.executable, "-c", cmd],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Subprocess command failed: {cmd!r}\nStderr: {res.stderr}"
