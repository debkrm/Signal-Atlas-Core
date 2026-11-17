"""
Unit tests for Phase 3B-1: Daily T+1 Order Runner and ATR R-Multiple Order Intent Wiring.

Enforces AGENTS.md Rule 1, 2, 5.1, 5.2, 5.3, 6.4, 7.1, 7.4, 8.1, 8.2, 10.8, 13.1, 13.2, 13.5,
Audit §58.5, §58.7, §59.3, §59.7:
- Higher-ATR name receives smaller quantity / weight at equal equity.
- Signal at T close -> Fill at T+1 open through single authoritative ExecutionFillSimulator and Portfolio ledger.
- Same-session execution attempt (T -> T) raises LookaheadIntentError fail-closed.
- T+1 attempt into an Upper Circuit freeze is rejected (REJECTED_UPPER_CIRCUIT) and does not touch cash/positions.
- H-83: Mandatory price band evidence for BUY entries; omitting price_band raises OrderRunnerEligibilityError.
- H-82: Authentic ExchangeSessionObservation series evidence; bare PriceBar without explicit_series raises OrderRunnerEligibilityError.
- H-84: Realised risk recorded on DailyExecutionTicket (capturing overnight gaps past reference price).
- N-83: typing.get_type_hints on DailyTPlus1OrderRunner resolves cleanly without NameError.
- N-84: Sizing quantity == 0 returns named no-trade ticket, zero leak of OrderIntentValidationError.
- Mid-hold corporate actions (§13.2): 1:2 split preserves total equity invariant (zero fabricated MTM loss), dividend credits CashEntryType.DIVIDEND_INFLOW.
- Surveillance escalation exit constraints (§5.2, §13.2): GSM Stage 2 escalation during hold triggers exit constraint.
- Phase 3B-2a plumbing: Strategy contract + TrialRegistry.append_trial before metric read + evaluate_verdicts() on synthetic fixture + sealed holdout date fails closed.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import typing
import pytest

import hashlib
from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries, ExchangeSessionObservation
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
import signal_core.execution
from signal_core.execution.band_policy import PriceBandPolicy
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
    OrderRunnerEligibilityError,
    OrderRunnerError,
    is_weekly_surveillance_trading_session,
)
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.execution.types import FillStatus, OrderProduct, OrderSide, OrderType
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.position import Position
from signal_core.portfolio.types import CashEntryType, CorporateActionError
from signal_core.reporting.verdicts import OverallVerdict, VerdictStatus, evaluate_verdicts
from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    check_partition_access,
    compute_fold_spec_fingerprint,
)
from signal_core.research.trials import TrialRegistry
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    SecurityMaster,
    SecurityMasterError,
    SurveillanceInterval,
    SurveillanceStage,
    SymbolInterval,
    build_production_security_master,
    load_corporate_actions,
    load_surveillance_intervals,
)
from signal_core.strategy.base import LookaheadIntentError, OrderIntent, OrderIntentValidationError
from signal_core.strategy.swing import DeliverySwingTrendStrategy, execute_swing_strategy_session


# =============================================================================
# Fixtures and Helpers
# =============================================================================

@pytest.fixture
def calendar():
    return load_anchored_nse_trading_calendar()


@pytest.fixture
def criteria():
    return load_go_no_go_criteria()


@pytest.fixture
def simulator(criteria, calendar):
    return ExecutionFillSimulator(
        criteria=criteria,
        trading_calendar=calendar.sessions,
    )


@pytest.fixture
def portfolio(criteria):
    # Initial capital ₹10,00,000 (10 Lakhs)
    return Portfolio(
        initial_capital=Decimal("1000000.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )


@pytest.fixture
def runner(portfolio, simulator, calendar, criteria):
    return DailyTPlus1OrderRunner(
        portfolio=portfolio,
        simulator=simulator,
        calendar=calendar,
        criteria=criteria,
        risk_per_trade_pct=Decimal("0.01"),  # 1% risk = ₹10,000
        atr_stop_multiple=Decimal("2.0"),
        # These probes exercise H-83/H-85 as written: a missing band refuses the order. Audit §74.10
        # Ruling D made the committed default LOCKED_BAR_REFUSAL_ONLY, so strict mode is selected here
        # explicitly instead of being implied by the criteria file.
        band_policy=PriceBandPolicy.STRICT_BAND_REQUIRED,
    )


# =============================================================================
# 1. OrderIntent.from_position_size_result Wiring Tests (Phase 3B-1)
# =============================================================================

def test_order_intent_from_position_size_result_wiring(runner):
    """
    §58.7 Item 6: Proves that OrderIntent.from_position_size_result wires quantity,
    stop_price, position_weight, risk_amount, stop_distance, and binding_constraint correctly.
    """
    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",  # RELIANCE
        signal_date=datetime.date(2024, 1, 2),
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2500.00"),
        atr=Decimal("50.00"),  # Stop distance = 2 * 50 = 100. Stop price = 2400.00
        session_volume=5000000,
        series="EQ",
    )

    intent, size_res = runner.generate_order_intent(candidate)

    assert intent is not None
    assert size_res is not None
    assert size_res.stop_loss_price == Decimal("2400.00")
    assert size_res.stop_distance == Decimal("100.00")
    # Risk budget = 1% of 1,000,000 = 10,000. Q = 10,000 / 100 = 100 shares.
    # Max weight = 10% of 1,000,000 = 100,000. 100 * 2500 = 250,000 (> 100,000).
    # So max weight binds: Q = 100,000 / 2500 = 40 shares.
    assert size_res.quantity == 40
    assert size_res.binding_constraint == "MAX_POSITION_WEIGHT"

    # Verify OrderIntent attributes
    assert intent.instrument_id == "INE002A01018"
    assert intent.signal_date == datetime.date(2024, 1, 2)
    assert intent.target_date == datetime.date(2024, 1, 3)  # T+1 session
    assert intent.side == OrderSide.BUY
    assert intent.quantity == 40
    assert intent.stop_price == Decimal("2400.00")
    assert intent.product == OrderProduct.DELIVERY

    # Verify metadata preserves sizing details for weight path
    assert intent.metadata is not None
    assert intent.metadata["position_weight"] == size_res.position_weight
    assert intent.metadata["risk_amount"] == size_res.risk_amount
    assert intent.metadata["binding_constraint"] == "MAX_POSITION_WEIGHT"


# =============================================================================
# 2. ATR Sizing Sensitivity: Higher ATR Receives Smaller Quantity / Weight
# =============================================================================

def test_higher_atr_receives_smaller_quantity_and_weight_at_equal_equity(runner):
    """
    §58.7 Item 6 Acceptance Probe: Proves that a higher-ATR name receives a strictly
    smaller quantity and weight than a lower-ATR name at identical equity and entry price.
    """
    signal_date = datetime.date(2024, 1, 2)
    vol = 10000000

    cand_low_atr = DailySignalCandidate(
        instrument_id="INE001A01001",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("50.00"),
        session_volume=vol,
        series="EQ",
    )
    cand_high_atr = DailySignalCandidate(
        instrument_id="INE002A01002",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=vol,
        series="EQ",
    )

    intent_low, size_low = runner.generate_order_intent(cand_low_atr)
    intent_high, size_high = runner.generate_order_intent(cand_high_atr)

    assert intent_low is not None and intent_high is not None
    assert size_low is not None and size_high is not None
    assert size_low.quantity == 100
    assert size_high.quantity == 50
    assert intent_low.quantity > intent_high.quantity
    assert size_low.position_weight > size_high.position_weight
    assert size_low.risk_amount == size_high.risk_amount == Decimal("10000.00")


# =============================================================================
# 3. Zero Lookahead Enforcement: Same-Session Execution (T -> T) Strictly Prohibited
# =============================================================================

def test_same_session_execution_prohibited_fail_closed(runner):
    """
    AGENTS.md Rule 7.1 & §58.7 Item 6: Same-session execution attempt (target_date <= signal_date)
    is strictly rejected fail-closed with LookaheadIntentError.
    """
    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=datetime.date(2024, 1, 2),
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2500.00"),
        atr=Decimal("50.00"),
        session_volume=5000000,
        series="EQ",
    )

    # Attempt same-session execution (T -> T)
    with pytest.raises(LookaheadIntentError, match="Lookahead violation"):
        runner.generate_order_intent(
            candidate,
            target_date=datetime.date(2024, 1, 2),
        )

    # Attempt backward-dated execution (T -> T-1)
    with pytest.raises(LookaheadIntentError, match="Lookahead violation"):
        runner.generate_order_intent(
            candidate,
            target_date=datetime.date(2024, 1, 1),
        )


# =============================================================================
# 4. Exchange Series & Settlement Scope Enforcement (Rule 5.1 & 13.1, Finding H-82)
# =============================================================================

def test_non_eq_series_rejected_fail_closed(runner):
    """
    AGENTS.md §5.1, §13.1 & Finding H-82: Candidates on non-EQ series (e.g. BE, BZ)
    are strictly prohibited from entry under cash delivery swing scope.
    """
    for bad_series in ("BE", "BZ", "SM", "IL"):
        cand = DailySignalCandidate(
            instrument_id="INE123A01010",
            signal_date=datetime.date(2024, 1, 2),
            side=OrderSide.BUY,
            entry_reference_price=Decimal("100.00"),
            atr=Decimal("2.00"),
            session_volume=100000,
            series=bad_series,
        )
        with pytest.raises(OrderRunnerEligibilityError, match="only EQ series is entry-eligible"):
            runner.generate_order_intent(cand)


def test_h82_bare_price_bar_without_series_evidence_refuses_fill(runner):
    """
    Finding H-82 Acceptance Probe (§59.7 Item 2):
    A candidate executed with a bare PriceBar and NO explicit_series or authentic
    series evidence must raise OrderRunnerEligibilityError. Zero default series synthesis.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    cand = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1005.00"),
        high=Decimal("1040.00"),
        low=Decimal("995.00"),
        close=Decimal("1030.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    # Calling run_candidate on bare PriceBar without explicit_series must refuse fail-closed (H-82)
    with pytest.raises(OrderRunnerEligibilityError, match="without verified exchange series evidence"):
        runner.run_candidate(
            candidate=cand,
            t_plus_1_bar=bar,
            price_band=band,
            explicit_series=None,
        )


def test_h82_be_session_observation_cannot_fill(runner):
    """
    Finding H-82 Acceptance Probe (§59.7 Item 2):
    An ExchangeSessionObservation carrying series='BE' cannot produce a fill.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    cand = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1005.00"),
        high=Decimal("1040.00"),
        low=Decimal("995.00"),
        close=Decimal("1030.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    obs_be = ExchangeSessionObservation(
        instrument_id="INE002A01018",
        trade_date=target_date,
        raw_series_code="BE",
        series_classification=ExchangeSeries.BE,
        isin="INE002A01018",
        price_bar=bar,
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="BE",
        upper_circuit_limit=Decimal("1055.00"),
        lower_circuit_limit=Decimal("955.00"),
        band_percentage=Decimal("5.00"),
    )

    with pytest.raises(OrderRunnerEligibilityError, match="is ineligible for cash delivery swing entry"):
        runner.run_candidate(
            candidate=cand,
            t_plus_1_bar=obs_be,
            price_band=band,
        )


# =============================================================================
# 5. Circuit Freeze Protection: Mandatory Price Band (Rule 5.3, Finding H-83)
# =============================================================================

def test_h83_missing_price_band_on_buy_raises_fail_closed(runner):
    """
    Finding H-83 Acceptance Probe (§59.7 Item 1):
    `run_candidate` on a BUY with `price_band is None` raises OrderRunnerEligibilityError.
    Circuit filter realism requires verified price band evidence to prevent upper circuit freeze fills.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2500.00"),
        atr=Decimal("50.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("2750.00"),
        high=Decimal("2750.00"),
        low=Decimal("2750.00"),
        close=Decimal("2750.00"),
        volume=1000000,
        traded_value=Decimal("100000000.00"),
    )

    with pytest.raises(OrderRunnerEligibilityError, match="Mandatory price band evidence missing for BUY entry"):
        runner.run_candidate(
            candidate=candidate,
            t_plus_1_bar=bar,
            price_band=None,
            explicit_series=ExchangeSeries.EQ,
        )


def test_t_plus_1_upper_circuit_freeze_rejected(runner, portfolio):
    """
    AGENTS.md §5.3 & §58.7 Item 6: A BUY order attempting to execute on a session
    where open price is at the Upper Circuit limit is rejected with REJECTED_UPPER_CIRCUIT
    and does NOT touch portfolio cash ledger or positions.
    """
    initial_cash = portfolio.current_cash
    assert initial_cash == Decimal("1000000.00")

    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2500.00"),
        atr=Decimal("50.00"),
        session_volume=5000000,
        series="EQ",
    )
    t_plus_1_bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("2750.00"),
        high=Decimal("2750.00"),
        low=Decimal("2750.00"),
        close=Decimal("2750.00"),
        volume=1000000,
        traded_value=Decimal("100000000.00"),
    )
    price_band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("2750.00"),
        lower_circuit_limit=Decimal("2250.00"),
        band_percentage=Decimal("10.00"),
    )

    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=t_plus_1_bar,
        price_band=price_band,
        explicit_series=ExchangeSeries.EQ,
    )

    assert ticket.fill_result is not None
    assert ticket.fill_result.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert ticket.fill_result.filled_quantity == 0

    # Invariant: Portfolio state remains completely untouched
    assert portfolio.current_cash == initial_cash
    assert portfolio.get_position("INE002A01018") is None


# =============================================================================
# 6. Realised Risk & Gap Accounting (Finding H-84)
# =============================================================================

def test_h84_realised_risk_records_overnight_gap_open(runner, portfolio):
    """
    Finding H-84 Acceptance Probe (§59.7 Item 4):
    Proves that when an overnight gap occurs between T-close reference price (1000.00)
    and T+1 open (1100.00), realised_risk on DailyExecutionTicket evaluates to:
    quantity × (executed_price − stop_price) = 50 × (1100.89785054 − 800.00) = 15,044.89
    rather than masking it as intended risk (10,000.00), yielding ratio 1.504.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    # Reference price 1000.00, ATR 100.00 -> 2*ATR stop distance = 200.00 -> Stop loss = 800.00
    # Intended risk = 50 shares * 200.00 = 10,000.00 INR (1% of 10 Lakhs equity)
    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )

    # Session bar on T+1 opens with a 10% upward gap at 1100.00 (within circuit limit 1200.00)
    t_plus_1_bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1100.00"),
        high=Decimal("1150.00"),
        low=Decimal("1095.00"),
        close=Decimal("1120.00"),
        volume=5000000,
        traded_value=Decimal("5500000000.00"),
    )
    price_band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1200.00"),
        lower_circuit_limit=Decimal("800.00"),
        band_percentage=Decimal("20.00"),
    )

    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=t_plus_1_bar,
        price_band=price_band,
        explicit_series=ExchangeSeries.EQ,
        average_daily_turnover=Decimal("5500000000.00"),
    )

    assert ticket.fill_result is not None
    assert ticket.fill_result.status == FillStatus.FILLED
    assert ticket.fill_result.filled_quantity == 50
    assert ticket.fill_result.executed_price is not None

    # Verify executed price includes slippage above open: 1100.8978...
    exec_p = ticket.fill_result.executed_price
    assert exec_p > Decimal("1100.00")

    # Verify intended risk vs realised risk (Finding H-84)
    assert ticket.intended_risk == Decimal("10000.00")
    assert ticket.realised_risk is not None

    expected_realised_risk = (Decimal(50) * (exec_p - Decimal("800.00"))).quantize(Decimal("0.01"))
    assert ticket.realised_risk == expected_realised_risk
    assert ticket.realised_risk == Decimal("15045.00")
    assert ticket.fill_result.executed_price % Decimal("0.05") == Decimal("0.00")

    # Realised risk is ~1.504x the intended risk
    ratio = ticket.realised_risk / ticket.intended_risk
    assert Decimal("1.504") <= ratio <= Decimal("1.505")


# =============================================================================
# 7. Type Hint Resolution & Zero-Size No-Trade Outcome (N-83, N-84)
# =============================================================================

def test_n83_type_hints_resolve_cleanly():
    """
    Finding N-83 Acceptance Probe (§59.7 Item 3):
    `typing.get_type_hints` on DailyTPlus1OrderRunner resolves with zero NameError.
    """
    hints_init = typing.get_type_hints(DailyTPlus1OrderRunner.__init__)
    hints_run = typing.get_type_hints(DailyTPlus1OrderRunner.run_candidate)

    assert hints_init["portfolio"] is Portfolio
    assert "criteria" in hints_init
    assert "candidate" in hints_run
    assert hints_run["return"] is DailyExecutionTicket


def test_n84_zero_quantity_sizing_returns_no_trade_outcome(criteria, simulator, calendar):
    """
    Finding N-84 Acceptance Probe (§59.7 Item 3):
    When the sizer returns quantity == 0, runner produces a named no-trade ticket
    instead of leaking an OrderIntentValidationError.
    """
    # Tiny portfolio of ₹500 with 1% risk = ₹5.00 risk budget
    tiny_portfolio = Portfolio(
        initial_capital=Decimal("500.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )
    runner_tiny = DailyTPlus1OrderRunner(
        portfolio=tiny_portfolio,
        simulator=simulator,
        calendar=calendar,
        criteria=criteria,
        risk_per_trade_pct=Decimal("0.01"),
    )

    # Candidate with ₹1000 price and ₹100 stop distance -> requires ₹100 risk for 1 share
    # Risk budget is ₹5.00 -> sized quantity == 0
    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=datetime.date(2024, 1, 2),
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("50.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1020.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    # Must return no-trade ticket, NOT raise OrderIntentValidationError
    ticket = runner_tiny.run_candidate(
        candidate=candidate,
        t_plus_1_bar=bar,
        price_band=band,
        explicit_series=ExchangeSeries.EQ,
    )

    assert ticket.is_no_trade is True
    assert ticket.no_trade_reason == "ZERO_QUANTITY_SIZED"
    assert ticket.intent is None
    assert ticket.order is None
    assert ticket.fill_result is None
    # Finding N-83 residual (§60.2 Item 3): No-trade ticket target_date carries T+1 (2024-01-03), not signal date
    assert ticket.target_date == datetime.date(2024, 1, 3)


# =============================================================================
# 8. Mid-Hold Corporate Actions: Stock Split & Cash Dividend (§13.2)
# =============================================================================

def test_mid_hold_split_preserves_equity_invariant(runner, portfolio):
    """
    AGENTS.md §13.2 & Audit §59.4, §59.7 Item 6:
    Proves that a 1:2 stock split occurring mid-hold:
    1. Doubles position shares (50 -> 100).
    2. Halves average entry price (1000.8162 -> 500.4081) while cost basis stays constant.
    3. Leaves total equity at ₹9,99,876.81 marked at ₹500.00 (ZERO fabricated MTM loss!).
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    cand_buy = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    ticket = runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket.fill_result is not None
    assert ticket.fill_result.filled_quantity == 50

    pos = portfolio.get_position("INE002A01018")
    assert pos is not None
    assert pos.quantity == 50

    # Total equity marked at pre-split price ₹1000.00
    equity_pre_split = portfolio.current_total_equity({"INE002A01018": Decimal("1000.00")})
    assert equity_pre_split == Decimal("999876.81")

    # Mid-hold corporate action: 1:2 stock split on ex-date 2024-01-04
    split_action = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2024, 1, 4),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="NSE/CML/2024/SPLIT_RIL",
    )

    portfolio.apply_corporate_action(split_action)

    # Position quantity doubled to 100 shares
    assert pos.quantity == 100
    assert pos.total_cost_basis == Decimal("50040.00")

    # Mark at post-split market price of ₹500.00
    equity_post_split = portfolio.current_total_equity({"INE002A01018": Decimal("500.00")})

    # Exact Invariant: Equity remains ₹9,99,876.81, NOT ₹9,74,876.81!
    assert equity_post_split == equity_pre_split == Decimal("999876.81")


def test_mid_hold_cash_dividend_credits_dividend_inflow(runner, portfolio):
    """
    AGENTS.md §13.2 & Audit §59.7 Item 6:
    Proves that a ₹5.00/share cash dividend on 50 held shares credits ₹250.00 to cash
    via CashEntryType.DIVIDEND_INFLOW.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    cand_buy = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )

    cash_before_div = portfolio.current_cash

    # Cash dividend ₹5.00 per share on ex-date 2024-01-04
    div_action = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2024, 1, 4),
        action_type=CorporateActionType.DIVIDEND,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("1"),
        dividend_amount=Decimal("5.00"),
        circular_ref="NSE/CML/2024/DIV_RIL",
    )

    div_entry = portfolio.apply_corporate_action(div_action)
    assert div_entry is not None
    assert div_entry.entry_type == CashEntryType.DIVIDEND_INFLOW
    assert div_entry.amount == Decimal("250.00")  # 50 shares * ₹5.00 = ₹250.00

    assert portfolio.current_cash == cash_before_div + Decimal("250.00")


# =============================================================================
# 9. Surveillance Escalation Exit Constraints (§5.2, §13.2)
# =============================================================================

def test_surveillance_escalation_triggers_exit_constraint(runner, portfolio):
    """
    AGENTS.md §5.2, §13.2 & Audit §59.7 Item 7:
    Proves that when a security held in portfolio escalates to GSM Stage 2 during a hold,
    `evaluate_surveillance_exit_constraints` generates a mandatory SELL candidate.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    cand_buy = DailySignalCandidate(
        instrument_id="INE999A01019",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE999A01019",
        trade_date=target_date,
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("950.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE999A01019",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )

    # Held position established: 500 shares
    pos = portfolio.get_position("INE999A01019")
    assert pos is not None and pos.quantity > 0

    # Build security master where INE999A01019 is in normal stage until escalating to GSM_STAGE_2 on 2024-01-15
    surv_normal = SurveillanceInterval(
        isin="INE999A01019",
        framework="GSM",
        stage=SurveillanceStage.NONE,
        effective_from=datetime.date(2024, 1, 1),
        effective_to=datetime.date(2024, 1, 15),
    )
    surv_interval = SurveillanceInterval(
        isin="INE999A01019",
        framework="GSM",
        stage=SurveillanceStage.GSM_STAGE_2,
        effective_from=datetime.date(2024, 1, 15),
        effective_to=datetime.date(2024, 6, 30),
    )
    sec_master = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE999A01019",
                symbol="TESTGSM",
                series="EQ",
                effective_from=datetime.date(2020, 1, 1),
                effective_to=None,
            )
        ],
        surveillance_intervals=[surv_normal, surv_interval],
    )

    # On 2024-01-10 (before escalation), zero exit constraints
    exits_pre = runner.evaluate_surveillance_exit_constraints(datetime.date(2024, 1, 10), sec_master)
    assert len(exits_pre) == 0

    # On 2024-01-15 (escalation effective date), exit constraint triggers
    exits_post = runner.evaluate_surveillance_exit_constraints(datetime.date(2024, 1, 15), sec_master)
    assert len(exits_post) == 1
    assert exits_post[0].instrument_id == "INE999A01019"
    assert exits_post[0].side == OrderSide.SELL
    assert "SURVEILLANCE_ESCALATION_EXIT" in exits_post[0].metadata["exit_reason"]


# =============================================================================
# 10. Phase 3B-2a Synthetic Strategy Contract & TrialRegistry Plumbing (§59.7 Item 8)
# =============================================================================

def test_phase3b2a_synthetic_strategy_trial_registry_and_verdict_plumbing(criteria, calendar):
    """
    §59.7 Item 8 Acceptance Probe:
    1. Strategy contract conforms to APPROVED_EQ_ONLY_POLICY.
    2. Trial is appended to TrialRegistry BEFORE its Sharpe / performance is readable.
    3. Results evaluate through evaluate_verdicts(), returning NO-GO because CRIT-PROV-01 is NOT RUN.
    4. Fold touching sealed Holdout date (2025-01-01..2026-11-11) fails closed with HoldoutSealedError.
    """
    strategy = DeliverySwingTrendStrategy(
        strategy_id="SWING-TREND-SYNTH-V1",
        fast_indicator="sma_20",
        slow_indicator="sma_50",
        allocation_weight=Decimal("0.08"),
        atr_stop_multiple=Decimal("2.0"),
    )

    params = strategy.parameters
    assert params["strategy_id"] == "SWING-TREND-SYNTH-V1"
    assert params["policy"] == "APPROVED_EQ_ONLY_POLICY"

    # Step 2: Append trial to TrialRegistry BEFORE reading Sharpe ratio
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_path = Path(tmpdir) / "test_trials.jsonl"
        registry = TrialRegistry(reg_path)

        trial_record = registry.append_trial(
            trial_id="TRIAL-SYNTH-001",
            hypothesis="Testing moving average trend breakout on synthetic liquid EQ cross-section",
            rationale="Verifying Phase 3B-2a trial logging invariant prior to metric evaluation",
            partition=PartitionRole.VALIDATION,
            canonical_params=params,
            fold_spec_fingerprint="FOLD-FPR-V1-00000000000000000000000000000001",
            dataset_fingerprint="DATA-CTNT-V2-a614a80bb4552a322ad2945502bac5c9",
            criteria_version=criteria.version,
            timestamp_utc="2026-11-15T06:00:00+00:00",
            sharpe_ratio=None,  # Not readable yet!
        )

        assert trial_record.seq == 1
        assert registry.total_trial_count == 1
        # Proves Sharpe ratio was None when appended
        assert trial_record.sharpe_ratio is None

    # Step 3: Evaluate results bundle through evaluate_verdicts()
    # Using synthetic fixture metadata: source_provenance_status = "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED"
    results_bundle = {
        "evaluation_start_date": "2024-01-01",
        "evaluation_end_date": "2024-01-03",
        "evaluated_at_utc": "2026-11-15T06:00:00+00:00",
        "dataset_fingerprint": "DATA-CTNT-V2-a614a80bb4552a322ad2945502bac5c9",
        "data_provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "trial_count_n": 5,
        "deflated_sharpe_ratio": Decimal("0.96"),
        "total_trades": 25,
        "profit_factor": Decimal("1.75"),
        "max_single_position_weight": Decimal("0.08"),
        "max_portfolio_drawdown": Decimal("0.12"),
    }

    report = evaluate_verdicts(results_bundle, criteria=criteria, calendar=calendar)

    # Must return NO-GO because CRIT-PROV-01 is NOT RUN (honest provenance gating)
    assert report.overall_verdict == OverallVerdict.NO_GO
    prov_eval = next(e for e in report.evaluations if e.criterion_id == "CRIT-PROV-01")
    assert prov_eval.status == VerdictStatus.NOT_RUN

    # Step 4: Verify that touching a sealed Holdout date (e.g. 2025-06-01) fails closed
    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-a614a80bb4552a322ad2945502bac5c9",
        holdout_token_hash="a" * 64,
        in_sample_start=datetime.date(2022, 1, 3),
        in_sample_end=datetime.date(2023, 12, 29),
        validation_start=datetime.date(2024, 1, 1),
        validation_end=datetime.date(2024, 12, 31),
        holdout_start=datetime.date(2025, 1, 1),
        holdout_end=datetime.date(2026, 11, 11),
    )
    with pytest.raises(HoldoutSealedError):
        check_partition_access(
            spec=spec,
            role=PartitionRole.HOLDOUT,
            unlock_file_path=None,  # HOLDOUT_UNLOCK is strictly absent
        )


# =============================================================================
# 11. SELL Order Lifecycle: Position Exit & Naked Short Prohibition
# =============================================================================

def test_sell_order_exits_position_and_rejects_naked_short(runner, portfolio):
    """
    Proves that a SELL candidate:
    1. Rejects naked short sale fail-closed when no position is held.
    2. Exits held position when held, crediting net proceeds to cash ledger.
    """
    signal_date = datetime.date(2024, 1, 2)
    cand_sell = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )

    # 1. Prohibit naked short sale
    with pytest.raises(OrderRunnerEligibilityError, match="naked short selling prohibited"):
        runner.generate_order_intent(cand_sell)

    # 2. Buy shares first to establish a held position (50 shares at ₹1000)
    cand_buy = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1020.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )
    runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )

    pos = portfolio.get_position("INE002A01018")
    assert pos is not None
    assert pos.quantity == 50
    cash_after_buy = portfolio.current_cash

    # 3. Now generate SELL intent on session T+2 (2024-01-03 close -> 2024-01-04 fill)
    cand_sell_valid = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=datetime.date(2024, 1, 3),
        side=OrderSide.SELL,
        entry_reference_price=Decimal("1050.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_sell = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 4),
        open=Decimal("1050.00"),
        high=Decimal("1080.00"),
        low=Decimal("1040.00"),
        close=Decimal("1070.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_sell = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 4),
        series="EQ",
        upper_circuit_limit=Decimal("1155.00"),
        lower_circuit_limit=Decimal("945.00"),
        band_percentage=Decimal("10.00"),
    )

    ticket_sell = runner.run_candidate(
        candidate=cand_sell_valid,
        t_plus_1_bar=bar_sell,
        price_band=band_sell,
        explicit_series=ExchangeSeries.EQ,
    )

    assert ticket_sell.fill_result is not None
    assert ticket_sell.fill_result.status == FillStatus.FILLED
    assert ticket_sell.fill_result.filled_quantity == 50
    assert pos.is_closed
    assert pos.quantity == 0

    # Net cash must increase by sell net proceeds (gross - costs)
    assert portfolio.current_cash > cash_after_buy


# =============================================================================
# 12. Mandatory Price Band on SELL & Lower Circuit Rejection (Finding H-85)
# =============================================================================

def test_h85_mandatory_price_band_on_sell_and_lower_circuit_rejection(runner, portfolio):
    """
    Finding H-85 Acceptance Probe (§60.6 Item 1):
    Proves that:
    1. A SELL exit without price_band raises OrderRunnerEligibilityError fail-closed (no band -> no fill).
    2. A SELL exit on a bar opening at lower circuit (O=900, H=950, L=900, C=940) with price_band
       is rejected as REJECTED_LOWER_CIRCUIT (sellers trapped per AGENTS.md §5.3).
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    # Establish held position first: 50 shares @ ₹1000 (5% weight)
    cand_buy = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )
    runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )
    pos = portfolio.get_position("INE002A01018")
    assert pos is not None and pos.quantity > 0

    # SELL candidate on session T+2 (2024-01-03 -> 2024-01-04)
    sell_signal_date = datetime.date(2024, 1, 3)
    sell_target_date = datetime.date(2024, 1, 4)
    cand_sell = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=sell_signal_date,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("950.00"),
        atr=Decimal("50.00"),
        session_volume=5000000,
        series="EQ",
    )
    # Bar opens at the lower circuit (900.00) and later trades up (H=950, C=940)
    bar_sell_lower_circuit = PriceBar(
        instrument_id="INE002A01018",
        trade_date=sell_target_date,
        open=Decimal("900.00"),
        high=Decimal("950.00"),
        low=Decimal("900.00"),
        close=Decimal("940.00"),
        volume=5000000,
        traded_value=Decimal("4600000000.00"),
    )

    # Probe 1: Omitting price_band on SELL raises OrderRunnerEligibilityError (fail-closed, no fill)
    with pytest.raises(OrderRunnerEligibilityError, match="Mandatory price band evidence missing for SELL"):
        runner.run_candidate(
            candidate=cand_sell,
            t_plus_1_bar=bar_sell_lower_circuit,
            price_band=None,
            explicit_series=ExchangeSeries.EQ,
        )

    # Probe 2: With price_band provided, fill reference price (900.00) equals lower circuit limit -> REJECTED_LOWER_CIRCUIT
    band_sell = PriceBandRecord(
        isin="INE002A01018",
        trade_date=sell_target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )
    ticket_sell = runner.run_candidate(
        candidate=cand_sell,
        t_plus_1_bar=bar_sell_lower_circuit,
        price_band=band_sell,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket_sell.fill_result is not None
    assert ticket_sell.fill_result.status == FillStatus.REJECTED_LOWER_CIRCUIT
    assert ticket_sell.fill_result.filled_quantity == 0
    # Position remains held (not filled into frozen bid!)
    assert not pos.is_closed
    assert pos.quantity > 0


# =============================================================================
# 13. ISIN Transition Re-Keying & Tradeability (Finding H-86)
# =============================================================================

def test_h86_isin_transition_rekeys_position_and_permits_sell(runner, portfolio):
    """
    Finding H-86 Acceptance Probe (§60.6 Item 2):
    Proves that applying the committed Cochin Shipyard ISIN transition row
    (INE704P01017 -> INE704P01025):
    1. Re-keys position in portfolio from old ISIN to new ISIN.
    2. Keeps quantity and cost basis strictly invariant (multiplier excluded).
    3. Marking before and after transition gives equal equity.
    4. Subsequent SELL for new ISIN INE704P01025 finds position and executes cleanly.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    # Buy 50 shares of Cochin Shipyard under old ISIN INE704P01017 (5% weight)
    cand_buy = DailySignalCandidate(
        instrument_id="INE704P01017",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE704P01017",
        trade_date=target_date,
        open=Decimal("1000.00"),
        high=Decimal("1020.00"),
        low=Decimal("990.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE704P01017",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1200.00"),
        lower_circuit_limit=Decimal("800.00"),
        band_percentage=Decimal("20.00"),
    )
    runner.run_candidate(
        candidate=cand_buy,
        t_plus_1_bar=bar_buy,
        price_band=band_buy,
        explicit_series=ExchangeSeries.EQ,
    )

    pos_old = portfolio.get_position("INE704P01017")
    assert pos_old is not None
    initial_qty = pos_old.quantity
    initial_cost = pos_old.total_cost_basis

    # Pre-transition equity marked at ₹500.00
    equity_pre = portfolio.current_total_equity({"INE704P01017": Decimal("500.00")})

    # Apply committed Cochin Shipyard ISIN transition on ex-date 2024-01-10
    transition_action = CorporateAction(
        isin="INE704P01017",
        ex_date=datetime.date(2024, 1, 10),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE704P01017",
        new_isin="INE704P01025",
        circular_ref="UNATTESTED_NSE_CML_60114",
        description="COCHIN SHIPYARD Sub-Division from Rs 10 to Rs 5",
    )
    portfolio.apply_corporate_action(transition_action)

    # Post-transition assertions:
    # 1. Old ISIN removed from open positions, new ISIN registered
    assert portfolio.get_position("INE704P01017") is None
    pos_new = portfolio.get_position("INE704P01025")
    assert pos_new is not None
    assert pos_new.instrument_id == "INE704P01025"

    # 2. Quantity doubled (2:1 ratio) and total cost basis strictly invariant (Finding H-89)
    assert pos_new.quantity == initial_qty * 2
    assert pos_new.total_cost_basis == initial_cost

    # 3. Marking at post-transition price ₹250.00 (split-adjusted from ₹500.00) gives exact same equity
    equity_post = portfolio.current_total_equity({"INE704P01025": Decimal("250.00")})
    assert equity_post == equity_pre

    # 4. SELL ticket for new ISIN INE704P01025 executes cleanly through order runner
    sell_date = datetime.date(2024, 1, 10)
    sell_target = datetime.date(2024, 1, 11)
    cand_sell = DailySignalCandidate(
        instrument_id="INE704P01025",
        signal_date=sell_date,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("500.00"),
        atr=Decimal("20.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_sell = PriceBar(
        instrument_id="INE704P01025",
        trade_date=sell_target,
        open=Decimal("500.00"),
        high=Decimal("520.00"),
        low=Decimal("490.00"),
        close=Decimal("510.00"),
        volume=5000000,
        traded_value=Decimal("2500000000.00"),
    )
    band_sell = PriceBandRecord(
        isin="INE704P01025",
        trade_date=sell_target,
        series="EQ",
        upper_circuit_limit=Decimal("600.00"),
        lower_circuit_limit=Decimal("400.00"),
        band_percentage=Decimal("20.00"),
    )
    ticket_sell = runner.run_candidate(
        candidate=cand_sell,
        t_plus_1_bar=bar_sell,
        price_band=band_sell,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket_sell.fill_result is not None
    assert ticket_sell.fill_result.status == FillStatus.FILLED
    assert ticket_sell.fill_result.filled_quantity == initial_qty * 2
    assert pos_new.is_closed


# =============================================================================
# 14. Fractional Entitlement Fail-Closed Protection (Finding N-87)
# =============================================================================

def test_n87_fractional_entitlement_raises_corporate_action_error(runner, portfolio):
    """
    Finding N-87 Acceptance Probe (§60.6 Item 6):
    Proves that a 3:2 bonus on an odd holding (5 shares) fails closed by raising
    CorporateActionError, preventing silent share truncation (5 * 1.5 = 7.5 shares).
    """
    pos = Position("INE002A01018")
    pos._quantity = 5
    pos._total_cost_basis = Decimal("5000.00")
    pos._average_entry_price = Decimal("1000.0000")
    portfolio._positions["INE002A01018"] = pos
    assert pos.quantity == 5

    # 3:2 bonus action (ratio_numerator=3, ratio_denominator=2)
    bonus_3_2 = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2024, 1, 4),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("3"),
        ratio_denominator=Decimal("2"),
        circular_ref="UNATTESTED_BONUS_3_2",
    )

    # 1. Proves Position.apply_corporate_action raises CorporateActionError
    with pytest.raises(CorporateActionError, match="Non-integral restatement.*7.5"):
        pos.apply_corporate_action(bonus_3_2)

    # 2. Proves Portfolio.apply_corporate_action raises CorporateActionError
    with pytest.raises(CorporateActionError, match="Non-integral restatement.*7.5"):
        portfolio.apply_corporate_action(bonus_3_2)


# =============================================================================
# 15. Surveillance Coverage & Manifest Provenance (Findings H-87 & H-88)
# =============================================================================

def test_h87_h88_surveillance_coverage_and_manifest_registration():
    """
    Findings H-87 & H-88 Acceptance Probes (§60.6 Items 3 & 4):
    1. Missing surveillance/CA file raises FileNotFoundError fail-closed.
    2. SurveillanceInterval carries circular_ref.
    3. SecurityMaster.has_surveillance_coverage distinguishes covered from unknown.
    4. Held security with no surveillance coverage raises SecurityMasterError fail-closed.
    5. manifest.jsonl registers both artifacts with matching sha256 and byte count.
    6. build_production_security_master excludes SYNTHETIC_FIXTURE rows (coverage count = 0).
    """
    # Probe 1: Missing artifact raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="Surveillance intervals artifact not found"):
        load_surveillance_intervals(path="data/reference/__absent_file__.jsonl")

    with pytest.raises(FileNotFoundError, match="Corporate actions artifact not found"):
        load_corporate_actions(path="data/reference/__absent_file__.jsonl")

    # Probe 2: SurveillanceInterval carries circular_ref
    loaded_surv = load_surveillance_intervals()
    assert len(loaded_surv) == 3
    for s in loaded_surv:
        assert s.circular_ref is not None
        assert "SYNTHETIC_FIXTURE" in s.circular_ref

    # Probe 3: Production SecurityMaster excludes fixtures, reporting coverage_count = 0
    sec_master_prod = build_production_security_master(include_cash_universe=True)
    assert sec_master_prod.surveillance_coverage_count == 0

    # Probe 4: SecurityMaster.has_surveillance_coverage
    assert sec_master_prod.has_surveillance_coverage("INE002A01018", datetime.date(2024, 1, 15)) is False

    # Probe 5: Held position in unsurveilled security raises SecurityMasterError fail-closed
    crit = load_go_no_go_criteria()
    cal = load_anchored_nse_trading_calendar()
    port = Portfolio(initial_capital=Decimal("1000000.00"), criteria=crit, initial_date=datetime.date(2024, 1, 1))
    sim = ExecutionFillSimulator(criteria=crit, trading_calendar=cal.sessions)
    runner = DailyTPlus1OrderRunner(portfolio=port, simulator=sim, calendar=cal, criteria=crit)

    # Establish held position in INE002A01018 (50 shares, 5% weight)
    cand_buy = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=datetime.date(2024, 1, 2),
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
        series="EQ",
    )
    bar_buy = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("1000.00"),
        high=Decimal("1020.00"),
        low=Decimal("990.00"),
        close=Decimal("1000.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band_buy = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )
    runner.run_candidate(candidate=cand_buy, t_plus_1_bar=bar_buy, price_band=band_buy, explicit_series=ExchangeSeries.EQ)

    # Evaluating surveillance exit constraints fails closed because INE002A01018 lacks surveillance coverage
    with pytest.raises(SecurityMasterError, match="has no authoritative surveillance coverage"):
        runner.evaluate_surveillance_exit_constraints(datetime.date(2024, 1, 15), sec_master_prod)

    # Probe 6: Manifest registers both artifacts with matching sha256 and byte count
    manifest_path = Path("data/reference/manifest.jsonl")
    manifest_entries = {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                if row.get("status") == "active":
                    manifest_entries[row["artifact"]] = row

    for name in ("corporate_actions.jsonl", "surveillance_intervals.jsonl"):
        assert name in manifest_entries, f"{name} must be registered in manifest.jsonl"
        reg = manifest_entries[name]
        p = Path("data/reference") / name
        b = p.read_bytes()
        assert reg["byte_count"] == len(b)
        assert reg["sha256"] == hashlib.sha256(b).hexdigest()
        assert reg["provenance_status"] == "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED"


# =============================================================================
# 16. Weekly Call Auction Cadence for GSM Stage 2+ (Finding N-88)
# =============================================================================

def test_n88_weekly_call_auction_cadence_for_gsm_stage_2(calendar, criteria):
    """
    Finding N-88 Acceptance Probe (§60.6 Item 7):
    Proves that for a position held under GSM Stage 2:
    1. An exit candidate is emitted strictly on the single weekly permitted session (Monday).
    2. Zero exit candidates are emitted on Tuesday, Wednesday, Thursday, Friday.
    3. Candidate inputs are derived from position and market.
    """
    port = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=datetime.date(2024, 1, 1))
    sim = ExecutionFillSimulator(criteria=criteria, trading_calendar=calendar.sessions)
    runner = DailyTPlus1OrderRunner(portfolio=port, simulator=sim, calendar=calendar, criteria=criteria)

    # Establish held position in fixture scrip INE999A01019
    pos = Position("INE999A01019")
    pos._quantity = 100
    pos._average_entry_price = Decimal("100.0000")
    pos._total_cost_basis = Decimal("10000.00")
    port._positions["INE999A01019"] = pos

    # Build security master with GSM Stage 2 surveillance covering January 2024
    surv_interval = SurveillanceInterval(
        isin="INE999A01019",
        framework="GSM",
        stage=SurveillanceStage.GSM_STAGE_2,
        effective_from=datetime.date(2024, 1, 1),
        effective_to=datetime.date(2024, 1, 31),
        circular_ref="SYNTHETIC_FIXTURE_GSM2",
    )
    sec_master = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE999A01019",
                symbol="TESTGSM",
                series="EQ",
                effective_from=datetime.date(2020, 1, 1),
                effective_to=None,
            )
        ],
        surveillance_intervals=[surv_interval],
    )

    # Monday 2024-01-15 is the weekly call auction session -> exactly 1 exit candidate emitted
    assert is_weekly_surveillance_trading_session(datetime.date(2024, 1, 15), calendar) is True
    exits_mon = runner.evaluate_surveillance_exit_constraints(datetime.date(2024, 1, 15), sec_master)
    assert len(exits_mon) == 1
    assert exits_mon[0].instrument_id == "INE999A01019"
    assert exits_mon[0].side == OrderSide.SELL

    # Tuesday (2024-01-16), Wednesday (2024-01-17), Thursday (2024-01-18), Friday (2024-01-19)
    # are NOT weekly trading sessions -> exactly 0 exit candidates emitted!
    for d in (
        datetime.date(2024, 1, 16),
        datetime.date(2024, 1, 17),
        datetime.date(2024, 1, 18),
        datetime.date(2024, 1, 19),
    ):
        assert is_weekly_surveillance_trading_session(d, calendar) is False
        exits_midweek = runner.evaluate_surveillance_exit_constraints(d, sec_master)
        assert len(exits_midweek) == 0, f"Session {d} must emit 0 exits under GSM Stage 2 weekly constraint"


# =============================================================================
# 17. Strategy Execution Harness & Clean Introspection Exports (Findings N-89 & N-90)
# =============================================================================

def test_n89_n90_strategy_execution_harness_and_eager_exports(runner, portfolio, criteria, calendar):
    """
    Findings N-89 & N-90 Acceptance Probes (§60.6 Items 8 & 9):
    1. 'DailyTPlus1OrderRunner' in dir(signal_core.execution) is True (clean introspection).
    2. A synthetic 2-day fold routes DeliverySwingTrendStrategy intents through
       execute_swing_strategy_session into DailyTPlus1OrderRunner and produces a real fill in portfolio.
    3. Proves unheld SELL intents are filtered out cleanly.
    """
    # Probe 1: N-90 introspection check
    assert "DailyTPlus1OrderRunner" in dir(signal_core.execution)
    assert "DailySignalCandidate" in dir(signal_core.execution)
    assert "DailyExecutionTicket" in dir(signal_core.execution)

    # Probe 2: N-89 end-to-end execution harness
    strategy = DeliverySwingTrendStrategy(
        strategy_id="SWING-TREND-SYNTH-V1",
        fast_indicator="sma_20",
        slow_indicator="sma_50",
        allocation_weight=Decimal("0.08"),
        atr_stop_multiple=Decimal("2.0"),
    )

    class FeatureMock:
        def __init__(self, close, sma_20, sma_50, atr, volume):
            self.close = close
            self.sma_20 = sma_20
            self.sma_50 = sma_50
            self.atr = atr
            self.volume = volume

    # On session T (2024-01-02 close):
    # - INE002A01018: close 1000 > sma_20 950 > sma_50 900 -> Trend BUY
    # - INE009A01021: close 400 < sma_50 500 -> Breakdown SELL (but unheld in portfolio!)
    features = {
        "INE002A01018": FeatureMock(Decimal("1000.00"), Decimal("950.00"), Decimal("900.00"), Decimal("100.00"), 5000000),
        "INE009A01021": FeatureMock(Decimal("400.00"), Decimal("450.00"), Decimal("500.00"), Decimal("20.00"), 5000000),
    }

    t_session = datetime.date(2024, 1, 2)
    t_plus_1 = datetime.date(2024, 1, 3)

    bars_t_plus_1 = {
        "INE002A01018": PriceBar(
            instrument_id="INE002A01018",
            trade_date=t_plus_1,
            open=Decimal("1000.00"),
            high=Decimal("1020.00"),
            low=Decimal("990.00"),
            close=Decimal("1010.00"),
            volume=5000000,
            traded_value=Decimal("5000000000.00"),
        )
    }
    price_bands = {
        "INE002A01018": PriceBandRecord(
            isin="INE002A01018",
            trade_date=t_plus_1,
            series="EQ",
            upper_circuit_limit=Decimal("1100.00"),
            lower_circuit_limit=Decimal("900.00"),
            band_percentage=Decimal("10.00"),
        )
    }

    # Execute session through harness
    tickets = execute_swing_strategy_session(
        strategy=strategy,
        runner=runner,
        as_of=t_session,
        next_session=t_plus_1,
        universe=["INE002A01018", "INE009A01021"],
        features=features,
        bars_next_session=bars_t_plus_1,
        price_bands_next_session=price_bands,
        explicit_series=ExchangeSeries.EQ,
    )

    # Exactly 1 ticket executed (BUY INE002A01018); unheld SELL INE009A01021 filtered out cleanly!
    assert len(tickets) == 1
    assert tickets.intents_generated == 2
    assert tickets.tickets_executed == 1
    assert tickets.skipped_unheld_sell == 1
    assert tickets.skipped_missing_band == 0
    assert tickets.skipped_missing_bar == 0

    t = tickets[0]
    assert t.candidate.instrument_id == "INE002A01018"
    assert t.candidate.side == OrderSide.BUY
    assert t.fill_result is not None
    assert t.fill_result.status == FillStatus.FILLED
    assert t.fill_result.filled_quantity > 0

    # Portfolio now holds INE002A01018
    held_pos = portfolio.get_position("INE002A01018")
    assert held_pos is not None and held_pos.quantity > 0


# =============================================================================
# 18. Findings H-89, H-90, N-92, N-93, N-94, N-95 Unit Tests (§61.6)
# =============================================================================

def test_h89_cochin_shipyard_isin_transition_ratio_and_equity_invariance(criteria):
    """
    Finding H-89 Acceptance Probe (§61.6 Item 1):
    Proves that applying Cochin Shipyard 2:1 transition to a 25-share position at
    INE704P01017 (entry ₹1605.60, cost basis ₹40,140.00):
    1. Yields exactly 50 shares of INE704P01025.
    2. Restates average entry price to exactly ₹802.80.
    3. Keeps total cost basis strictly invariant at ₹40,140.00.
    4. Old ISIN position is removed (None) and new ISIN is registered.
    5. Marking pre-transition at ₹1605.60 and post-transition at ₹802.80 gives identical equity.
    6. A 1:1 transition leaves quantity and average entry price unchanged.
    """
    portfolio = Portfolio(
        initial_capital=Decimal("100000.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )

    # Establish initial 25-share position in INE704P01017 @ ₹1605.60
    # Outlay = 25 * 1605.60 = 40,140.00 INR
    from signal_core.execution.simulator import ExecutionFillResult
    from signal_core.execution.types import ExecutionOrder
    from signal_core.execution.costs import TransactionCostBreakdown
    from signal_core.contracts.exchange_series import ExchangeSeries

    dummy_order = ExecutionOrder(
        instrument_id="INE704P01017",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=25,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 1, 3),
        order_type=OrderType.MARKET_ON_OPEN,
    )
    from signal_core.execution.costs import TransactionCostModel
    cost_model = TransactionCostModel(criteria.statutory_costs)
    dummy_costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=25,
        price=Decimal("1605.60"),
    )
    fill = ExecutionFillResult(
        order=dummy_order,
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
        fill_id="FILL-COCHIN-001",
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)

    pos_pre = portfolio.get_position("INE704P01017")
    assert pos_pre is not None
    assert pos_pre.quantity == 25
    assert pos_pre.average_entry_price == Decimal("1605.6000")
    assert pos_pre.total_cost_basis == Decimal("40140.00")

    equity_pre = portfolio.current_total_equity({"INE704P01017": Decimal("1605.60")})

    # Apply Cochin Shipyard 2:1 ISIN transition on 2024-01-10
    transition_action = CorporateAction(
        isin="INE704P01017",
        ex_date=datetime.date(2024, 1, 10),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE704P01017",
        new_isin="INE704P01025",
        circular_ref="NSE/CML/60114",
        description="COCHIN SHIPYARD Sub-Division from Rs 10 to Rs 5",
    )
    portfolio.apply_corporate_action(transition_action)

    # 1. Old ISIN removed from open positions, new ISIN registered
    assert portfolio.get_position("INE704P01017") is None
    pos_new = portfolio.get_position("INE704P01025")
    assert pos_new is not None
    assert pos_new.instrument_id == "INE704P01025"

    # 2. Qty doubled to 50 shares, entry price halved to 802.80, cost basis unchanged at 40,140.00
    assert pos_new.quantity == 50
    assert pos_new.average_entry_price == Decimal("802.8000")
    assert pos_new.total_cost_basis == Decimal("40140.00")

    # 3. MTM equity post-transition at 802.80 is strictly equal to pre-transition equity
    equity_post = portfolio.current_total_equity({"INE704P01025": Decimal("802.80")})
    assert equity_post == equity_pre

    # 4. Identity-only 1:1 transition leaves quantity unchanged
    portfolio2 = Portfolio(
        initial_capital=Decimal("100000.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )
    dummy_costs2 = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        price=Decimal("100.00"),
    )
    fill2 = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE111A01011",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=10,
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            order_type=OrderType.MARKET_ON_OPEN,
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 3),
        latency_sessions=1,
        filled_quantity=10,
        unfilled_quantity=0,
        executed_price=Decimal("100.00"),
        slippage=None,
        costs=dummy_costs2,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-1TO1-001",
    )
    portfolio2.process_fill(fill2, enforce_risk_limits=False)
    action_1_to_1 = CorporateAction(
        isin="INE111A01011",
        ex_date=datetime.date(2024, 1, 10),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("1"),
        old_isin="INE111A01011",
        new_isin="INE111A01029",
        circular_ref="NSE/CML/RESTRUCT_1",
    )
    portfolio2.apply_corporate_action(action_1_to_1)
    pos_renamed = portfolio2.get_position("INE111A01029")
    assert pos_renamed is not None
    assert pos_renamed.quantity == 10
    assert pos_renamed.total_cost_basis == Decimal("1000.00")


def test_h90_fresh_interpreter_clean_import_subprocesses():
    """
    Finding H-90 Acceptance Probe (§61.6 Item 2):
    Proves that:
    1. `import signal_core.strategy.swing` exits 0 as the first import in a fresh interpreter.
    2. `import signal_core.strategy.base` exits 0 as the first import in a fresh interpreter.
    3. `import signal_core.strategy` exits 0 as the first import in a fresh interpreter.
    4. `import signal_core.execution` exits 0 and dir(signal_core.execution) contains runner names.
    5. Zero monkey-patching or silent exception swallowing.
    """
    import subprocess
    import sys

    cmds = [
        "import signal_core.strategy.swing",
        "import signal_core.strategy.base",
        "import signal_core.strategy",
        "import signal_core.execution; assert 'DailyTPlus1OrderRunner' in dir(signal_core.execution); assert 'DailySignalCandidate' in dir(signal_core.execution)",
        "import signal_core.portfolio.portfolio; import signal_core.execution.order_runner",
    ]
    for cmd in cmds:
        res = subprocess.run(
            [sys.executable, "-c", cmd],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Command failed: {cmd!r}\nStderr: {res.stderr}\nStdout: {res.stdout}"


def test_n92_surveillance_date_bounded_coverage(criteria, simulator, calendar):
    """
    Finding N-92 Acceptance Probe (§61.6 Item 3):
    Proves that:
    1. SecurityMaster.has_surveillance_coverage honours as_of date.
    2. Dates outside every interval for that ISIN return False.
    3. Dates inside an interval return True.
    4. Evaluating exit constraints for an uncovered held security fails closed with SecurityMasterError.
    5. require_coverage=True raises fail-closed when coverage count is 0.
    """
    surv_interval = SurveillanceInterval(
        isin="INE888A01018",
        framework="GSM",
        stage=SurveillanceStage.GSM_STAGE_2,
        effective_from=datetime.date(2024, 1, 15),
        effective_to=datetime.date(2024, 6, 30),
    )
    sec_master = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE888A01018",
                symbol="TESTCOV",
                series="EQ",
                effective_from=datetime.date(2020, 1, 1),
                effective_to=None,
            )
        ],
        surveillance_intervals=[surv_interval],
    )

    # Probe 1 & 2: Outside interval bounds evaluates to False
    assert sec_master.has_surveillance_coverage("INE888A01018", datetime.date(2024, 1, 10)) is False
    assert sec_master.has_surveillance_coverage("INE888A01018", datetime.date(2024, 7, 1)) is False

    # Probe 3: Inside interval bounds evaluates to True
    assert sec_master.has_surveillance_coverage("INE888A01018", datetime.date(2024, 1, 15)) is True
    assert sec_master.has_surveillance_coverage("INE888A01018", datetime.date(2024, 6, 29)) is True

    # Probe 4: Position held whose date has no surveillance coverage fails closed
    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"),
        criteria=criteria,
        initial_date=datetime.date(2024, 1, 1),
    )
    runner = DailyTPlus1OrderRunner(
        portfolio=portfolio,
        simulator=simulator,
        calendar=calendar,
        criteria=criteria,
    )
    from signal_core.execution.simulator import ExecutionFillResult
    from signal_core.execution.types import ExecutionOrder
    from signal_core.execution.costs import TransactionCostModel
    cost_model = TransactionCostModel(criteria.statutory_costs)
    dummy_costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 3),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=50,
        price=Decimal("100.00"),
    )
    dummy_fill = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE888A01018",
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
        executed_price=Decimal("100.00"),
        slippage=None,
        costs=dummy_costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="FILL-COV-001",
    )
    portfolio.process_fill(dummy_fill, enforce_risk_limits=False)

    # On 2024-01-10, held position has no coverage -> evaluate_surveillance_exit_constraints raises SecurityMasterError
    with pytest.raises(SecurityMasterError, match="has no authoritative surveillance coverage"):
        runner.evaluate_surveillance_exit_constraints(datetime.date(2024, 1, 10), sec_master)

    # Probe 5: require_coverage=True with 0 coverage count raises SecurityMasterError
    empty_master = SecurityMaster(symbol_intervals=[], surveillance_intervals=[])
    with pytest.raises(SecurityMasterError, match="Authoritative surveillance coverage is 0"):
        runner.evaluate_surveillance_exit_constraints(
            datetime.date(2024, 1, 15), empty_master, require_coverage=True
        )


def test_n93_summary_reports_skip_reasons_when_bands_or_bars_missing(runner, portfolio):
    """
    Finding N-93 Acceptance Probe (§61.6 Item 6):
    Proves that execute_swing_strategy_session returns a SwingSessionExecutionSummary
    that counts intents, executions, and each skip reason rather than silently dropping them.
    """
    strategy = DeliverySwingTrendStrategy(
        strategy_id="SWING-TREND-SYNTH-V1",
        fast_indicator="sma_20",
        slow_indicator="sma_50",
        allocation_weight=Decimal("0.05"),
        atr_stop_multiple=Decimal("2.0"),
    )

    class FeatureMock:
        def __init__(self, close, sma_20, sma_50, atr, volume):
            self.close = close
            self.sma_20 = sma_20
            self.sma_50 = sma_50
            self.atr = atr
            self.volume = volume

    features = {
        "INE002A01018": FeatureMock(Decimal("1000.00"), Decimal("950.00"), Decimal("900.00"), Decimal("100.00"), 5000000),
        "INE009A01021": FeatureMock(Decimal("400.00"), Decimal("450.00"), Decimal("500.00"), Decimal("20.00"), 5000000),
    }

    t_session = datetime.date(2024, 1, 2)
    t_plus_1 = datetime.date(2024, 1, 3)

    bars_t_plus_1 = {
        "INE002A01018": PriceBar(
            instrument_id="INE002A01018",
            trade_date=t_plus_1,
            open=Decimal("1000.00"),
            high=Decimal("1020.00"),
            low=Decimal("990.00"),
            close=Decimal("1010.00"),
            volume=5000000,
            traded_value=Decimal("5000000000.00"),
        )
    }

    # Case 1: Empty price bands -> missing band skip counted
    summary_empty_bands = execute_swing_strategy_session(
        strategy=strategy,
        runner=runner,
        as_of=t_session,
        next_session=t_plus_1,
        universe=["INE002A01018", "INE009A01021"],
        features=features,
        bars_next_session=bars_t_plus_1,
        price_bands_next_session={},  # Empty band table
        explicit_series=ExchangeSeries.EQ,
    )
    assert summary_empty_bands.intents_generated == 2
    assert summary_empty_bands.tickets_executed == 0
    assert summary_empty_bands.skipped_missing_band == 1  # INE002A01018 BUY lacked band
    assert summary_empty_bands.skipped_unheld_sell == 1   # INE009A01021 SELL unheld
    assert len(summary_empty_bands.tickets) == 0

    # Case 2: Empty price bars -> missing bar skip counted
    price_bands = {
        "INE002A01018": PriceBandRecord(
            isin="INE002A01018",
            trade_date=t_plus_1,
            series="EQ",
            upper_circuit_limit=Decimal("1100.00"),
            lower_circuit_limit=Decimal("900.00"),
            band_percentage=Decimal("10.00"),
        )
    }
    summary_empty_bars = execute_swing_strategy_session(
        strategy=strategy,
        runner=runner,
        as_of=t_session,
        next_session=t_plus_1,
        universe=["INE002A01018", "INE009A01021"],
        features=features,
        bars_next_session={},  # Empty bar table
        price_bands_next_session=price_bands,
        explicit_series=ExchangeSeries.EQ,
    )
    assert summary_empty_bars.intents_generated == 2
    assert summary_empty_bars.tickets_executed == 0
    assert summary_empty_bars.skipped_missing_bar == 1  # INE002A01018 BUY lacked bar
    assert summary_empty_bars.skipped_unheld_sell == 1  # INE009A01021 SELL unheld


def test_n94_allocation_weight_limits_position_size(runner, portfolio):
    """
    Finding N-94 Acceptance Probe (§61.6 Item 7):
    Proves that candidate.allocation_weight actively caps position sizing.
    With criteria max_single_position_weight = 10%, setting candidate.allocation_weight = 3%
    restricts the sized position to at most 3% of equity.

    Audit §75.10 N-138: the 2% case this probe used to size (₹20,000 of ₹10,00,000) is now below the
    committed `min_entry_notional` and is refused as a named no-trade before it can be sized. 3% is
    the smallest weight on this equity that clears the floor, so the N-94 cap is measured above it.
    """
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    # 1. Candidate with allocation_weight = 2% (0.02)
    cand_2pct = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("100.00"),
        atr=Decimal("1.00"),  # ATR stop distance small enough that risk doesn't bind before allocation
        session_volume=5000000,
        series="EQ",
        allocation_weight=Decimal("0.03"),
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("101.00"),
        volume=5000000,
        traded_value=Decimal("500000000.00"),
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("110.00"),
        lower_circuit_limit=Decimal("90.00"),
        band_percentage=Decimal("10.00"),
    )

    ticket_2pct = runner.run_candidate(
        candidate=cand_2pct,
        t_plus_1_bar=bar,
        price_band=band,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket_2pct.fill_result is not None
    # 3% of ₹10,00,000 equity = ₹30,000 / ₹100 = 300 shares
    assert ticket_2pct.fill_result.filled_quantity == 300

    # 2. Candidate with default criteria max weight (5%)
    cand_5pct = DailySignalCandidate(
        instrument_id="INE009A01021",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("100.00"),
        atr=Decimal("1.00"),
        session_volume=5000000,
        series="EQ",
        allocation_weight=Decimal("0.05"),
    )
    band_5pct = PriceBandRecord(
        isin="INE009A01021",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("110.00"),
        lower_circuit_limit=Decimal("90.00"),
        band_percentage=Decimal("10.00"),
    )
    bar_5pct = PriceBar(
        instrument_id="INE009A01021",
        trade_date=target_date,
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("101.00"),
        volume=5000000,
        traded_value=Decimal("500000000.00"),
    )
    ticket_5pct = runner.run_candidate(
        candidate=cand_5pct,
        t_plus_1_bar=bar_5pct,
        price_band=band_5pct,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket_5pct.fill_result is not None
    # 5% of remaining equity (> ₹9,70,000) = ~480-500 shares > 300 shares!
    assert ticket_5pct.fill_result.filled_quantity > ticket_2pct.fill_result.filled_quantity


def test_n95_fill_prices_quantized_to_tick_grid():
    """
    Finding N-95 Acceptance Probe (§61.6 Item 8):
    Proves that:
    1. quantize_to_tick_grid quantizes prices >= 1.00 to exact 0.05 tick grid.
    2. quantize_to_tick_grid quantizes prices < 1.00 to exact 0.01 tick grid.
    3. ExecutionFillSimulator produces executed_price that strictly lies on the tick grid.
    """
    from signal_core.execution.simulator import ExecutionFillSimulator, quantize_to_tick_grid

    # Price >= 1.00 INR tick grid (0.05 INR)
    assert quantize_to_tick_grid(Decimal("1000.816227")) == Decimal("1000.80")
    assert quantize_to_tick_grid(Decimal("1000.825")) == Decimal("1000.85")
    assert quantize_to_tick_grid(Decimal("100.03")) == Decimal("100.05")
    assert quantize_to_tick_grid(Decimal("100.02")) == Decimal("100.00")

    # Price < 1.00 INR tick grid (0.01 INR)
    assert quantize_to_tick_grid(Decimal("0.553")) == Decimal("0.55")
    assert quantize_to_tick_grid(Decimal("0.558")) == Decimal("0.56")

    # Simulator fill price is quantized
    sim = ExecutionFillSimulator(quantize_to_tick=True)
    from signal_core.execution.types import ExecutionOrder
    order = ExecutionOrder(
        instrument_id="INE002A01018",
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        signal_date=datetime.date(2024, 1, 2),
        target_date=datetime.date(2024, 1, 3),
        order_type=OrderType.MARKET_ON_OPEN,
    )
    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        open=Decimal("1000.00"),
        high=Decimal("1050.00"),
        low=Decimal("990.00"),
        close=Decimal("1010.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 3),
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )
    res = sim.simulate_order(
        order=order,
        bar=bar,
        price_band=band,
        explicit_series=ExchangeSeries.EQ,
        average_daily_turnover=Decimal("5000000000.00"),
    )
    assert res.executed_price is not None
    # Must be on 0.05 grid
    assert (res.executed_price % Decimal("0.05")) == Decimal("0.00")


