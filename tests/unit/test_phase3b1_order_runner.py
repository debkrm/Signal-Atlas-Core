"""
Unit tests for Phase 3B-1: Daily T+1 Order Runner and ATR R-Multiple Order Intent Wiring.

Enforces AGENTS.md Rule 1, 2, 5.1, 5.3, 6.4, 7.1, 7.4, 13.1, 13.5,
and Audit §58.5 / §58.7 Item 6:
- Higher-ATR name receives smaller quantity / weight at equal equity.
- Signal at T close -> Fill at T+1 open through single authoritative ExecutionFillSimulator and Portfolio ledger.
- Same-session execution attempt (T -> T) raises LookaheadIntentError fail-closed.
- T+1 attempt into an Upper Circuit freeze is rejected (REJECTED_UPPER_CIRCUIT) and does not touch cash/positions.
- Strict NSE EQ delivery scope: BE/BZ candidates raise OrderRunnerEligibilityError fail-closed.
- Exact Decimal accounting on all order attributes, statutory costs, and portfolio ledger movements.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
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
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.strategy.base import LookaheadIntentError, OrderIntent, OrderIntentValidationError


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
    )

    intent, size_res = runner.generate_order_intent(candidate)

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
    entry_p = Decimal("500.00")
    vol = 10000000

    # Low ATR = ₹10.00 -> Stop dist = ₹20.00 -> Q_risk = 10,000 / 20 = 500 shares (Value ₹2,50,000 -> weight cap binds at 200 shares)
    # To test pure risk budget binding, use higher entry price so weight cap does not bind:
    # Equity = 1,000,000. Max weight 10% = 100,000.
    # Entry price = ₹1,000.
    # Low ATR = ₹10 -> Stop dist = ₹20 -> Q_risk = 10,000 / 20 = 500. (500 * 1000 = 500,000 binds weight).
    # To test risk budget binding, use wide ATR:
    # Low ATR = ₹50 -> Stop dist = ₹100 -> Q_risk = 10,000 / 100 = 100 shares. Value = 100 * 1,000 = 100,000.
    # High ATR = ₹100 -> Stop dist = ₹200 -> Q_risk = 10,000 / 200 = 50 shares. Value = 50 * 1,000 = 50,000.
    cand_low_atr = DailySignalCandidate(
        instrument_id="INE001A01001",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("50.00"),
        session_volume=vol,
    )
    cand_high_atr = DailySignalCandidate(
        instrument_id="INE002A01002",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=vol,
    )

    intent_low, size_low = runner.generate_order_intent(cand_low_atr)
    intent_high, size_high = runner.generate_order_intent(cand_high_atr)

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
# 4. Exchange Series & Settlement Scope Enforcement (Rule 5.1 & 13.1)
# =============================================================================

def test_non_eq_series_rejected_fail_closed(runner):
    """
    AGENTS.md §5.1, §13.1 & Phase 3B-1: Candidates on non-EQ series (e.g. BE, BZ)
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


# =============================================================================
# 5. Circuit Freeze Protection: Upper Circuit Fill Rejection (Rule 5.3)
# =============================================================================

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
    )

    # Session bar on T+1 opens at ₹2750, which equals the upper circuit limit of ₹2750 (ask depth is zero)
    # Traded value clears ₹5 crore criteria threshold
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
    )

    assert ticket.fill_result is not None
    assert ticket.fill_result.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert ticket.fill_result.filled_quantity == 0

    # Invariant: Portfolio state remains completely untouched
    assert portfolio.current_cash == initial_cash
    assert portfolio.get_position("INE002A01018") is None


# =============================================================================
# 6. End-to-End Execution: Normal T+1 Fill Updates Cash & Position Ledger Atomically
# =============================================================================

def test_t_plus_1_normal_fill_and_portfolio_accounting(runner, portfolio):
    """
    AGENTS.md Rule 7.4 & Phase 3B-1: Proves that a normal T+1 open fill:
    1. Executes at Open + non-linear slippage.
    2. Calculates statutory transaction costs (STT, stamp duty, exchange turnover, GST, SEBI).
    3. Atomically updates the single authoritative Portfolio cash ledger and position book.
    """
    initial_cash = portfolio.current_cash
    signal_date = datetime.date(2024, 1, 2)
    target_date = datetime.date(2024, 1, 3)

    # Use entry price ₹1000 and ATR ₹100 so position size is 50 shares (₹50,000 = 5% weight),
    # leaving plenty of headroom below the 10% concentration limit for slippage and gap open.
    candidate = DailySignalCandidate(
        instrument_id="INE002A01018",
        signal_date=signal_date,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("100.00"),
        session_volume=5000000,
    )

    # Normal session bar with ample liquidity and price within circuit bands
    t_plus_1_bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=target_date,
        open=Decimal("1005.00"),
        high=Decimal("1040.00"),
        low=Decimal("995.00"),
        close=Decimal("1030.00"),
        volume=5000000,
        traded_value=Decimal("5000000000.00"),
    )
    price_band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )

    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=t_plus_1_bar,
        price_band=price_band,
        average_daily_turnover=Decimal("5000000000.00"),
    )

    assert ticket.fill_result is not None
    assert ticket.fill_result.status == FillStatus.FILLED
    assert ticket.fill_result.filled_quantity == 50
    assert ticket.fill_result.executed_price is not None
    assert ticket.fill_result.executed_price >= Decimal("1005.00")  # Open + slippage
    assert ticket.fill_result.costs is not None
    assert ticket.fill_result.costs.total_charges > Decimal("0.00")

    # Verify Portfolio position updated
    pos = portfolio.get_position("INE002A01018")
    assert pos is not None
    assert pos.quantity == 50
    assert not pos.is_closed

    # Verify CashLedger movement: cash reduced by gross amount + statutory costs (negative net_cash_flow)
    expected_cash = initial_cash + ticket.fill_result.costs.to_paise().net_cash_flow
    assert portfolio.current_cash == expected_cash
    assert portfolio.current_cash < initial_cash


# =============================================================================
# 7. SELL Order Lifecycle: Position Exit & Naked Short Prohibition
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
    runner.run_candidate(cand_buy, bar_buy, price_band=band_buy)

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

    ticket_sell = runner.run_candidate(cand_sell_valid, bar_sell, price_band=band_sell)

    assert ticket_sell.fill_result is not None
    assert ticket_sell.fill_result.status == FillStatus.FILLED
    assert ticket_sell.fill_result.filled_quantity == 50
    assert pos.is_closed
    assert pos.quantity == 0

    # Net cash must increase by sell net proceeds (gross - costs)
    assert portfolio.current_cash > cash_after_buy
