"""Seq 12 (`SWING-MEAN-REV-EQ-V1`) — the pre-registered rule, tested against its own specification.

Five invariants, each measured rather than asserted:

1. RSI(2) is Wilder-smoothed and reproduces a hand-computed series.
2. The features the signal reads at session T are unchanged by any bar after T (zero lookahead).
3. No entry signal exists before 200 sessions of warm-up: `sma_200` is None and the strategy emits
   nothing.
4. The exit signal is formed at T's close and the fill targets T+1's open — never T's close.
5. The 2.0xATR(14) protective stop and the 21-session hold bound both exit through the one engine, and
   they do not both exit the same position: the stop fills at its own price when nothing else exits,
   and at the bound the open exit is the one ticket and the stop is retired.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_intent import OrderIntent as IntentContract
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
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.features.engine import SubsegmentIndicatorEngine
from signal_core.features.indicators import compute_rsi
from signal_core.portfolio.portfolio import Portfolio
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.strategy.mean_reversion import MeanReversionSwingStrategy
from signal_core.strategy.swing import execute_swing_strategy_session
from scripts.run_phase3b2_walkforward import build_authoritative_runner

ISIN = "INE002A01018"


def _strategy() -> MeanReversionSwingStrategy:
    return MeanReversionSwingStrategy(allocation_weight=Decimal("0.05"))


# --- 1. RSI(2) known answer ---------------------------------------------------------------


def test_rsi2_reproduces_a_hand_computed_wilder_series():
    """
    Closes 10, 11, 12, 11, 10.

    Changes: +1, +1, -1, -1. With period 2 the seed at index 2 averages the first two changes
    (avg gain 1, avg loss 0 → RSI 100); index 3: avg gain (1*1+0)/2 = 0.5, avg loss (0*1+1)/2 = 0.5,
    RS = 1 → 50.00; index 4: avg gain (0.5*1+0)/2 = 0.25, avg loss (0.5*1+1)/2 = 0.75, RS = 1/3 →
    100 - 100/(1+1/3) = 25.00. Wilder smoothing, not a simple mean: a 2-period simple mean of the last
    two changes at index 4 would be 0/2 against 1/2 → 0.00.
    """
    values = compute_rsi([Decimal(v) for v in ("10", "11", "12", "11", "10")], period=2)
    assert values[:2] == [None, None]
    assert values[2] == Decimal("100.00")
    assert values[3] == Decimal("50.00")
    assert values[4] == Decimal("25.00")


# --- 2. zero lookahead --------------------------------------------------------------------


def _bars(sessions, closes):
    return [
        PriceBar(
            instrument_id=ISIN,
            trade_date=session,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=100000,
            traded_value=close * Decimal(100000),
        )
        for session, close in zip(sessions, closes)
    ]


def test_features_at_session_t_are_identical_whether_or_not_later_bars_exist():
    sessions = [
        datetime.date(2020, 1, 1) + datetime.timedelta(days=offset) for offset in range(260)
    ]
    closes = [Decimal(100) + Decimal(offset % 17) for offset in range(260)]
    cutoff = 219
    truncated = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=sessions,
        actual_price_bars=_bars(sessions, closes),
        fail_closed_on_unexplained=False,
    )
    # Rewrite every bar after the cutoff: a feature at or before the cutoff that moves is a leak.
    rewritten = [close for close in closes]
    for index in range(cutoff + 1, len(rewritten)):
        rewritten[index] = Decimal("1.00")
    truncated_at_cutoff = [f for f in truncated if f.trade_date <= sessions[cutoff]]

    recomputed = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=sessions,
        actual_price_bars=_bars(sessions, rewritten),
        fail_closed_on_unexplained=False,
    )
    recomputed_at_cutoff = [f for f in recomputed if f.trade_date <= sessions[cutoff]]

    assert len(truncated_at_cutoff) == cutoff + 1
    for before, after in zip(truncated_at_cutoff, recomputed_at_cutoff):
        assert (before.sma_5, before.sma_200, before.rsi_2) == (
            after.sma_5,
            after.sma_200,
            after.rsi_2,
        ), f"{before.trade_date}: a feature moved when a later bar changed"


# --- 3. warm-up ---------------------------------------------------------------------------


def test_no_entry_signal_before_two_hundred_sessions_of_warm_up():
    sessions = [
        datetime.date(2020, 1, 1) + datetime.timedelta(days=offset) for offset in range(230)
    ]
    closes = [Decimal(300) - Decimal(index) * Decimal("0.5") for index in range(230)]
    features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=sessions,
        actual_price_bars=_bars(sessions, closes),
        fail_closed_on_unexplained=False,
    )
    first_trend = min(f.trade_date for f in features if f.sma_200 is not None)
    assert first_trend == sessions[199], (
        f"sma_200 first exists at {first_trend}, not the 200th session {sessions[199]}"
    )
    for feature in features:
        if feature.trade_date < sessions[199]:
            assert feature.sma_200 is None

    # A maximally oversold RSI (2.00) inside the warm-up must still not be an entry: the trend filter
    # is absent, and an absent filter is not a pass.
    warm_up = SimpleNamespace(
        close=Decimal("100.00"),
        sma_5=Decimal("120.00"),
        sma_200=None,
        rsi_2=Decimal("2.00"),
    )
    intents = _strategy().generate_signals(
        as_of=sessions[10], next_session=sessions[11], universe=[ISIN], features={ISIN: warm_up}
    )
    assert intents == (), [i.intent_id for i in intents]

    # And the same session with the filter present is an entry, so the test above is not vacuous.
    armed = SimpleNamespace(
        close=Decimal("100.00"), sma_5=Decimal("120.00"), sma_200=Decimal("90.00"), rsi_2=Decimal("2.00")
    )
    intents = _strategy().generate_signals(
        as_of=sessions[199], next_session=sessions[200], universe=[ISIN], features={ISIN: armed}
    )
    assert [i.side for i in intents] == [OrderSide.BUY]


# --- 4. exit timing -----------------------------------------------------------------------


def test_exit_signal_is_formed_at_the_close_and_targets_the_next_open():
    as_of = datetime.date(2021, 6, 15)
    next_session = datetime.date(2021, 6, 16)
    features = {
        ISIN: SimpleNamespace(
            close=Decimal("110.00"),
            sma_5=Decimal("108.00"),
            sma_200=Decimal("90.00"),
            rsi_2=Decimal("40.00"),
        )
    }
    intents = _strategy().generate_signals(
        as_of=as_of, next_session=next_session, universe=[ISIN], features=features
    )
    assert len(intents) == 1, [i.intent_id for i in intents]
    exit_intent = intents[0]
    assert exit_intent.side == OrderSide.SELL
    assert exit_intent.signal_date == as_of, "the exit signal must be stamped at T's close"
    assert exit_intent.target_date == next_session, "the exit must fill at T+1, never at T's close"

    # The contract itself refuses a same-session fill, so the T close → T fill shape cannot be built.
    with pytest.raises(Exception):
        IntentContract(
            instrument_id=ISIN,
            signal_date=as_of,
            target_date=as_of,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET_ON_OPEN,
            product=OrderProduct.DELIVERY,
            target_weight=Decimal("0.05"),
            intent_id="SEQ12_SAME_SESSION_EXIT",
        )


def test_entry_signal_also_targets_the_next_open():
    as_of = datetime.date(2021, 6, 15)
    next_session = datetime.date(2021, 6, 16)
    features = {
        ISIN: SimpleNamespace(
            close=Decimal("100.00"),
            sma_5=Decimal("101.00"),
            sma_200=Decimal("90.00"),
            rsi_2=Decimal("4.00"),
        )
    }
    intents = _strategy().generate_signals(
        as_of=as_of, next_session=next_session, universe=[ISIN], features=features
    )
    assert [i.side for i in intents] == [OrderSide.BUY]
    assert (intents[0].signal_date, intents[0].target_date) == (as_of, next_session)


# --- 5. stop and max-hold precedence ------------------------------------------------------


ENTRY_PRICE = Decimal("1000.00")
ATR = Decimal("20.00")
STOP_PRICE = ENTRY_PRICE - Decimal("2.0") * ATR


def _bar(session, open_, high, low, close) -> PriceBar:
    return PriceBar(
        instrument_id=ISIN,
        trade_date=session,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100000,
        traded_value=close * Decimal(100000),
    )


def _band(session) -> PriceBandRecord:
    return PriceBandRecord(
        isin=ISIN,
        trade_date=session,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
        band_percentage=Decimal("10.00"),
    )


def _held(hold_sessions: int):
    criteria = load_go_no_go_criteria()
    calendar = load_anchored_nse_trading_calendar(criteria=criteria)
    sessions = calendar.sessions
    entry = next(s for s in sessions if s >= datetime.date(2024, 1, 1))
    entry_index = sessions.index(entry)
    execution_session = sessions[entry_index + hold_sessions]
    signal_session = sessions[entry_index + hold_sessions - 1]

    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=entry
    )
    costs = TransactionCostModel(criteria.statutory_costs).compute_costs(
        trade_date=entry,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        price=ENTRY_PRICE,
    )
    portfolio.process_fill(
        ExecutionFillResult(
            order=ExecutionOrder(
                instrument_id=ISIN,
                side=OrderSide.BUY,
                product=OrderProduct.DELIVERY,
                quantity=10,
                signal_date=sessions[entry_index - 1],
                target_date=entry,
                order_type=OrderType.MARKET_ON_OPEN,
                order_id="SEQ12_SEED_BUY",
            ),
            status=FillStatus.FILLED,
            fill_date=entry,
            latency_sessions=1,
            filled_quantity=10,
            unfilled_quantity=0,
            executed_price=ENTRY_PRICE,
            slippage=None,
            costs=costs,
            circuit_evidence_present=True,
            rejection_reason=None,
            fill_id="SEQ12_SEED_FILL",
        ),
        enforce_risk_limits=False,
    )
    runner = build_authoritative_runner(
        portfolio=portfolio,
        simulator=ExecutionFillSimulator(criteria=criteria, trading_calendar=sessions),
        calendar=calendar,
        criteria=criteria,
        atr_stop_multiple=Decimal("2.0"),
        risk_per_trade_pct=Decimal("0.0075"),
    )
    runner.arm_protective_stop(
        instrument_id=ISIN,
        stop_price=STOP_PRICE,
        quantity=10,
        signal_date=sessions[entry_index - 1],
        armed_session=entry,
        atr=ATR,
    )
    return portfolio, runner, calendar, signal_session, execution_session


def _run_session(runner, signal_session, execution_session, bar, forced=()):
    # close < sma_5, so the mean-reversion exit emits nothing and any exit is the stop's or the bound's
    features = {
        ISIN: SimpleNamespace(
            close=Decimal("980.00"),
            sma_5=Decimal("1010.00"),
            sma_200=Decimal("900.00"),
            rsi_2=Decimal("40.00"),
            atr=ATR,
            volume=100000,
        )
    }
    return execute_swing_strategy_session(
        strategy=_strategy(),
        runner=runner,
        as_of=signal_session,
        next_session=execution_session,
        universe=[ISIN],
        features=features,
        bars_next_session={ISIN: bar},
        price_bands_next_session={ISIN: _band(execution_session)},
        explicit_series=ExchangeSeries.EQ,
        forced_exit_isins=tuple(forced),
    )


def test_the_stop_fills_at_its_own_price_inside_the_bound():
    portfolio, runner, _calendar, signal_session, execution_session = _held(hold_sessions=10)
    bar = _bar(execution_session, Decimal("1000.00"), Decimal("1010.00"), Decimal("950.00"), Decimal("980.00"))

    summary = _run_session(runner, signal_session, execution_session, bar)

    assert summary.tickets == (), "a hold 10 sessions inside the bound emitted a strategy order"
    assert summary.protective_stop_fills == 1
    stop_ticket = summary.protective_stop_tickets[0]
    assert stop_ticket.status is FillStatus.FILLED
    assert stop_ticket.fill_result.executed_price <= STOP_PRICE
    assert (stop_ticket.candidate.metadata or {}).get("exit_reason") == "STOP_LOSS"
    assert portfolio.get_position(ISIN).is_closed
    assert not [
        t for t in summary.tickets if (t.candidate.metadata or {}).get("exit_reason") == "MAX_HOLD_BOUND_EXIT"
    ], "the bound exited a position that had not reached it"


def test_at_the_bound_the_open_exit_is_the_one_ticket_and_the_stop_is_retired():
    bound = load_go_no_go_criteria().max_hold_trading_sessions
    portfolio, runner, calendar, signal_session, execution_session = _held(hold_sessions=bound)
    refusals = portfolio.require_hold_bounds(execution_session, bound, calendar)
    assert list(refusals) == [ISIN]

    # The session opens below the stop: both an exit at the open and a stop breach are live.
    bar = _bar(execution_session, Decimal("940.00"), Decimal("950.00"), Decimal("930.00"), Decimal("940.00"))
    summary = _run_session(runner, signal_session, execution_session, bar, forced=tuple(sorted(refusals)))

    assert len(summary.tickets) == 1, [t.candidate.metadata for t in summary.tickets]
    ticket = summary.tickets[0]
    assert (ticket.candidate.metadata or {}).get("exit_reason") == "MAX_HOLD_BOUND_EXIT"
    assert ticket.status is FillStatus.FILLED
    assert summary.protective_stop_tickets == (), (
        "the stop fired on a position the open exit had already closed — a double sell"
    )
    position = portfolio.get_position(ISIN)
    assert position.is_closed and position.quantity == 0
