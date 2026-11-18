"""
Unit tests for the Audit §93 remediation of `reports/audit/volume2.md` §92, item 4 of §92.10.

Target invariant — the hold-bound exit is a seam, not a promise (AGENTS.md §13.2, §5.3):

- `Portfolio.require_hold_bounds` and `execute_swing_strategy_session(forced_exit_isins=...)` are driven
  together, exactly as `run_phase3b2_walkforward`'s session loop drives them: a position at the bound
  produces one `MAX_HOLD_BOUND_EXIT` SELL through the single authoritative runner and simulator, and it
  closes the position;
- a bar locked at the lower circuit refuses that SELL (`REJECTED_LOWER_CIRCUIT`), leaves the position
  open and is counted as one refusal — a frozen bid is an unbounded exit delay, never an extension of
  the holding period;
- one session inside the bound produces no refusal and no ticket.

The refusal count is derived here the way the engine derives it — `len(forced - filled)` over the
session's tickets — so a test that hard-codes a number the producer does not compute cannot pass.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
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
from signal_core.portfolio.portfolio import Portfolio
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.strategy.swing import DeliverySwingTrendStrategy, execute_swing_strategy_session
from scripts.run_phase3b2_walkforward import build_authoritative_runner

ISIN = "INE002A01018"
QUANTITY = 10
ENTRY_PRICE = Decimal("1000.00")
LOWER_LIMIT = Decimal("900.00")
UPPER_LIMIT = Decimal("1100.00")


def _criteria():
    return load_go_no_go_criteria()


def _calendar():
    return load_anchored_nse_trading_calendar(criteria=_criteria())


def _strategy() -> DeliverySwingTrendStrategy:
    return DeliverySwingTrendStrategy(
        strategy_id="test_hold_bound_seam",
        fast_indicator="fast",
        slow_indicator="slow",
        allocation_weight=Decimal("0.05"),
    )


def _features() -> dict:
    """An uptrend, so the strategy emits no SELL of its own and any SELL is the bound's."""
    return {
        ISIN: SimpleNamespace(
            fast=Decimal("1005.00"),
            slow=Decimal("1000.00"),
            close=Decimal("1010.00"),
            atr=Decimal("20.00"),
            volume=100000,
        )
    }


def _band(trade_date: datetime.date) -> PriceBandRecord:
    return PriceBandRecord(
        isin=ISIN,
        trade_date=trade_date,
        series="EQ",
        upper_circuit_limit=UPPER_LIMIT,
        lower_circuit_limit=LOWER_LIMIT,
        band_percentage=Decimal("10.00"),
    )


def _bar(trade_date: datetime.date, open_: Decimal, high: Decimal, low: Decimal, close: Decimal) -> PriceBar:
    volume = 100000
    return PriceBar(
        instrument_id=ISIN,
        trade_date=trade_date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        traded_value=close * Decimal(volume),
    )


def _held_portfolio(hold_sessions: int):
    """
    A portfolio holding one open position whose entry session is `hold_sessions` authoritative
    sessions before the execution session the returned runner is about to trade.
    """
    calendar = _calendar()
    criteria = _criteria()
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
        quantity=QUANTITY,
        price=ENTRY_PRICE,
    )
    order = ExecutionOrder(
        instrument_id=ISIN,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=QUANTITY,
        signal_date=sessions[entry_index - 1],
        target_date=entry,
        order_type=OrderType.MARKET_ON_OPEN,
        order_id="S93_SEED_BUY",
    )
    portfolio.process_fill(
        ExecutionFillResult(
            order=order,
            status=FillStatus.FILLED,
            fill_date=entry,
            latency_sessions=1,
            filled_quantity=QUANTITY,
            unfilled_quantity=0,
            executed_price=ENTRY_PRICE,
            slippage=None,
            costs=costs,
            circuit_evidence_present=True,
            rejection_reason=None,
            fill_id="S93_SEED_FILL",
        ),
        enforce_risk_limits=False,
    )
    assert portfolio.get_position(ISIN).entry_date == entry

    runner = build_authoritative_runner(
        portfolio=portfolio,
        simulator=ExecutionFillSimulator(criteria=criteria, trading_calendar=sessions),
        calendar=calendar,
        criteria=criteria,
        atr_stop_multiple=Decimal("2.0"),
    )
    return portfolio, runner, calendar, signal_session, execution_session


def _execute(runner, signal_session, execution_session, bar, forced):
    return execute_swing_strategy_session(
        strategy=_strategy(),
        runner=runner,
        as_of=signal_session,
        next_session=execution_session,
        universe=[ISIN],
        features=_features(),
        bars_next_session={ISIN: bar},
        price_bands_next_session={ISIN: _band(execution_session)},
        explicit_series=ExchangeSeries.EQ,
        forced_exit_isins=forced,
    )


def _counters(summary, forced: set) -> tuple[int, int]:
    """The engine's own accounting: a forced exit that filled, and a forced exit that did not."""
    filled = {
        ticket.candidate.instrument_id
        for ticket in summary.tickets
        if (ticket.candidate.metadata or {}).get("exit_reason") == "MAX_HOLD_BOUND_EXIT"
        and ticket.fill_result is not None
        and ticket.fill_result.filled_quantity > 0
    }
    return len(filled), len(forced - filled)


def test_forced_hold_bound_exit_fills_on_a_normal_bar_and_closes_the_position():
    bound = _criteria().max_hold_trading_sessions
    portfolio, runner, calendar, signal_session, execution_session = _held_portfolio(hold_sessions=bound)

    refusals = portfolio.require_hold_bounds(execution_session, bound, calendar)
    assert list(refusals) == [ISIN], (
        f"a position held {bound} authoritative sessions was not refused at {execution_session}: {refusals!r}"
    )
    assert "Hold bound refused" in refusals[ISIN]

    summary = _execute(
        runner,
        signal_session,
        execution_session,
        _bar(execution_session, ENTRY_PRICE, Decimal("1010.00"), Decimal("990.00"), Decimal("1005.00")),
        forced=tuple(sorted(refusals)),
    )

    assert len(summary.tickets) == 1, (
        f"the bound emitted {len(summary.tickets)} ticket(s); one position is one exit (§92.2)"
    )
    ticket = summary.tickets[0]
    assert ticket.status is FillStatus.FILLED, ticket.status
    assert (ticket.candidate.metadata or {}).get("exit_reason") == "MAX_HOLD_BOUND_EXIT"
    assert ticket.fill_result is not None and ticket.fill_result.filled_quantity == QUANTITY
    assert portfolio.get_position(ISIN).is_closed, "the forced exit filled but the position is still open"
    assert _counters(summary, set(refusals)) == (1, 0)


def test_forced_hold_bound_exit_is_refused_when_the_bid_is_locked_at_the_lower_circuit():
    bound = _criteria().max_hold_trading_sessions
    portfolio, runner, calendar, signal_session, execution_session = _held_portfolio(hold_sessions=bound)

    refusals = portfolio.require_hold_bounds(execution_session, bound, calendar)
    assert list(refusals) == [ISIN]

    locked = _bar(execution_session, LOWER_LIMIT, LOWER_LIMIT, LOWER_LIMIT, LOWER_LIMIT)
    summary = _execute(runner, signal_session, execution_session, locked, forced=tuple(sorted(refusals)))

    assert len(summary.tickets) == 1, (
        f"the bound emitted {len(summary.tickets)} ticket(s) against a locked bid; a refused exit is "
        f"still one attempt, not two (§5.3)"
    )
    ticket = summary.tickets[0]
    assert ticket.status is FillStatus.REJECTED_LOWER_CIRCUIT, ticket.status
    assert (ticket.candidate.metadata or {}).get("exit_reason") == "MAX_HOLD_BOUND_EXIT"
    position = portfolio.get_position(ISIN)
    assert not position.is_closed and position.quantity == QUANTITY, (
        "a SELL filled into a frozen bid; §5.3 has no bid to fill against"
    )
    assert _counters(summary, set(refusals)) == (0, 1), (
        "the refused exit was not counted as a refusal, so the engine would report a position it "
        "considers exited while it is still carried"
    )


def test_hold_bound_emits_nothing_one_session_inside_the_bound():
    bound = _criteria().max_hold_trading_sessions
    portfolio, runner, calendar, signal_session, execution_session = _held_portfolio(hold_sessions=bound - 1)

    refusals = portfolio.require_hold_bounds(execution_session, bound, calendar)
    assert refusals == {}, f"a hold one session inside the bound was refused: {refusals!r}"

    summary = _execute(
        runner,
        signal_session,
        execution_session,
        _bar(execution_session, ENTRY_PRICE, Decimal("1010.00"), Decimal("990.00"), Decimal("1005.00")),
        forced=tuple(sorted(refusals)),
    )

    assert summary.tickets == (), "a session inside the bound produced a ticket"
    assert portfolio.get_position(ISIN).quantity == QUANTITY
    assert _counters(summary, set(refusals)) == (0, 0)
