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

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries, ExchangeSessionObservation
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
    OrderRunnerEligibilityError,
    OrderRunnerError,
)
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.execution.types import FillStatus, OrderProduct, OrderSide, OrderType
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.types import CashEntryType
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
    SurveillanceInterval,
    SurveillanceStage,
    SymbolInterval,
)
from signal_core.strategy.base import LookaheadIntentError, OrderIntent, OrderIntentValidationError
from signal_core.strategy.swing import DeliverySwingTrendStrategy


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
    assert ticket.realised_risk == Decimal("15044.89")

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


# =============================================================================
# 8. Mid-Hold Corporate Actions: Stock Split & Cash Dividend (§13.2)
# =============================================================================

def test_mid_hold_split_preserves_equity_invariant(runner, portfolio):
    """
    AGENTS.md §13.2 & Audit §59.4, §59.7 Item 6:
    Proves that a 1:2 stock split occurring mid-hold:
    1. Doubles position shares (50 -> 100).
    2. Halves average entry price (1000.8162 -> 500.4081) while cost basis stays constant.
    3. Leaves total equity at ₹9,99,876.00 marked at ₹500.00 (ZERO fabricated MTM loss!).
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
    assert equity_pre_split == Decimal("999876.00")

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
    assert pos.total_cost_basis == Decimal("50040.81")

    # Mark at post-split market price of ₹500.00
    equity_post_split = portfolio.current_total_equity({"INE002A01018": Decimal("500.00")})

    # Exact Invariant: Equity remains ₹9,99,876.00, NOT ₹9,74,876.00!
    assert equity_post_split == equity_pre_split == Decimal("999876.00")


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

    # Build security master where INE999A01019 escalates to GSM_STAGE_2 on 2024-01-15
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
        surveillance_intervals=[surv_interval],
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
