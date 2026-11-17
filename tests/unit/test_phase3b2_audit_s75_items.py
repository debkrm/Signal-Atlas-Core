"""
Unit tests for the Audit §75 remediation items (audit §75 at 0674d89, reviewing 9f7036e).

Target invariants:
- H-127: the corporate-action restatement is gated on the price convention. On a
  SPLIT_BONUS_ADJUSTED corpus a face-value ISIN transition is an identity re-key (quantity, entry
  price and stop unchanged) and a same-ISIN split/bonus is a no-op; only an UNADJUSTED series takes
  the exchange ratio.
- N-136: the window-end open book is liquidated into the profit factor and the mean expectancy, so the
  statistic describes the book the equity curve describes.
- N-137: qualifying entries consume the session's capital slots in rank order, not ISIN order.
- N-138: an entry below the pre-registered notional floor is a named no-trade, and a fill below the
  viability floor is refused rather than booked.
- N-134 / N-135: a locked 0-range refusal has its own status, and the band policy and entry rank are
  `canonical_params`, not version indirections.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_types import OrderSide
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import DailySignalCandidate, DailyTPlus1OrderRunner
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import CorporateAction, CorporateActionType
from signal_core.strategy.swing import DeliverySwingTrendStrategy
from scripts.run_phase3b2_walkforward import (
    build_authoritative_runner,
    carry_protective_stop_across_corporate_action,
    liquidate_open_book,
    restate_lots_for_share_ratio,
    run_phase3b2_walkforward,
)
from signal_core.contracts.dataset import PriceConvention

ISIN = "INE081A01012"
SUCCESSOR_ISIN = "INE081A01020"
SIGNAL_SESSION = datetime.date(2024, 1, 16)
ENTRY_SESSION = datetime.date(2024, 1, 17)
RESTATE_SESSION = datetime.date(2024, 1, 18)


def _criteria():
    return load_go_no_go_criteria()


def _calendar():
    return load_anchored_nse_trading_calendar(criteria=_criteria())


def _portfolio(initial: str = "1000000.00") -> Portfolio:
    return Portfolio(
        initial_capital=Decimal(initial),
        criteria=_criteria(),
        initial_date=SIGNAL_SESSION,
    )


def _runner(portfolio: Portfolio) -> DailyTPlus1OrderRunner:
    return build_authoritative_runner(
        portfolio=portfolio,
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        calendar=_calendar(),
        criteria=_criteria(),
        atr_stop_multiple=Decimal("2.0"),
    )


def _bar(
    trade_date: datetime.date,
    open_: str,
    high: str,
    low: str,
    close: str,
    isin: str = ISIN,
    volume: int = 100000,
) -> PriceBar:
    return PriceBar(
        instrument_id=isin,
        trade_date=trade_date,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        traded_value=Decimal(close) * Decimal(volume),
    )


def _band(isin: str, upper: str, lower: str) -> PriceBandRecord:
    return PriceBandRecord(
        isin=isin,
        trade_date=ENTRY_SESSION,
        series="EQ",
        upper_circuit_limit=Decimal(upper),
        lower_circuit_limit=Decimal(lower),
    )


def _buy(runner: DailyTPlus1OrderRunner, weight: str = "0.04", atr: str = "100.00"):
    """Entry reference 2000, ATR 100, k=2.0 -> 20 shares at a 1800.000 stop (₹40,000 notional)."""
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2000.00"),
        atr=Decimal(atr),
        session_volume=100000,
        series="EQ",
        allocation_weight=Decimal(weight),
        metadata={"intent_id": "S75-BUY"},
    )
    return runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=_bar(ENTRY_SESSION, "2000.00", "2020.00", "1980.00", "2000.00"),
        target_date=ENTRY_SESSION,
        price_band=_band(ISIN, "2200.00", "1800.00"),
        explicit_series=ExchangeSeries.EQ,
    )


def _transition() -> CorporateAction:
    return CorporateAction(
        isin=ISIN,
        ex_date=RESTATE_SESSION,
        action_type=CorporateActionType.ISIN_TRANSITION,
        old_isin=ISIN,
        new_isin=SUCCESSOR_ISIN,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        description="S75 synthetic face-value sub-division",
    )


def _lot(quantity: int, entry_price: str, stop_price: str) -> dict:
    return {
        "entry_date": ENTRY_SESSION,
        "entry_price": Decimal(entry_price),
        "quantity": quantity,
        "original_quantity": quantity,
        "intended_risk": Decimal("2000.00"),
        "stop_price": Decimal(stop_price),
        "costs": Decimal("20.00"),
        "dividends": Decimal("0.00"),
    }


# --- H-127: restatement is a function of the price convention -----------------------------


def test_h127_adjusted_series_rekeys_a_ten_to_one_transition_without_restating_it():
    """§75.4 probe: on SPLIT_BONUS_ADJUSTED the ratio is already in the prices."""
    portfolio = _portfolio()
    runner = _runner(portfolio)
    ticket = _buy(runner)
    assert ticket.status == FillStatus.FILLED
    assert ticket.fill_result.filled_quantity == 20
    assert runner.protective_stops[ISIN].stop_price == Decimal("1800.000")

    equity_before = portfolio.current_total_equity({ISIN: Decimal("2000.00")})
    entry_before = portfolio.get_position(ISIN).average_entry_price
    open_lots = {ISIN: [_lot(20, "2000.0000", "1800.0000")]}

    transition = _transition()
    portfolio.apply_corporate_action(
        transition, price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED
    )
    restate_lots_for_share_ratio(open_lots, ISIN, SUCCESSOR_ISIN, 1, 1)
    assert carry_protective_stop_across_corporate_action(
        runner, transition, apply_ratio=False
    ) is True

    position = portfolio.get_position(SUCCESSOR_ISIN)
    assert portfolio.get_position(ISIN) is None
    assert position is not None
    # Identity moves; the economics do not. Twenty shares stay twenty shares at 2000, and the stop
    # stays at 1800 rather than being divided by a ratio the series never multiplied.
    assert position.quantity == 20
    assert position.average_entry_price == entry_before
    assert open_lots[SUCCESSOR_ISIN][0]["quantity"] == 20
    assert open_lots[SUCCESSOR_ISIN][0]["entry_price"] == Decimal("2000.0000")
    # Continuous equity: the same 20 shares at the same price, on the successor identity.
    assert portfolio.current_total_equity({SUCCESSOR_ISIN: Decimal("2000.00")}) == equity_before

    stop = runner.protective_stops[SUCCESSOR_ISIN]
    assert ISIN not in runner.protective_stops
    assert stop.quantity == 20
    assert stop.stop_price == Decimal("1800.0000")


def test_h127_adjusted_series_treats_a_same_isin_split_as_a_no_op():
    """A same-ISIN split on an adjusted series is information the prices already carry."""
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED
    entry_before = portfolio.get_position(ISIN).average_entry_price

    split = CorporateAction(
        isin=ISIN,
        ex_date=RESTATE_SESSION,
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        description="S75 synthetic split on an adjusted series",
    )
    # Before §75 this raised CorporateActionError and aborted the run on the only corpus in the repo.
    assert portfolio.apply_corporate_action(
        split, price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED
    ) is None

    position = portfolio.get_position(ISIN)
    assert position.quantity == 20
    assert position.average_entry_price == entry_before
    assert runner.protective_stops[ISIN].stop_price == Decimal("1800.000")


@pytest.mark.parametrize("price_convention,expected_qty,expected_stop", [
    (PriceConvention.UNADJUSTED_RAW, 200, Decimal("180.0000")),
])
def test_h127_unadjusted_series_still_takes_the_ratio(price_convention, expected_qty, expected_stop):
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED
    open_lots = {ISIN: [_lot(20, "2000.0000", "1800.0000")]}
    transition = _transition()

    portfolio.apply_corporate_action(transition, price_convention=price_convention)
    restate_lots_for_share_ratio(open_lots, ISIN, SUCCESSOR_ISIN, 10, 1)
    assert carry_protective_stop_across_corporate_action(runner, transition, apply_ratio=True)

    position = portfolio.get_position(SUCCESSOR_ISIN)
    assert position.quantity == expected_qty
    assert open_lots[SUCCESSOR_ISIN][0]["quantity"] == expected_qty
    assert runner.protective_stops[SUCCESSOR_ISIN].stop_price == expected_stop
    assert runner.protective_stops[SUCCESSOR_ISIN].quantity == expected_qty

    # The carried order is testable: a next-session crash through it fills all 200 shares.
    result = runner.evaluate_protective_stops(
        session_date=RESTATE_SESSION,
        bars={
            SUCCESSOR_ISIN: _bar(
                RESTATE_SESSION, "179.00", "180.00", "170.00", "175.00",
                isin=SUCCESSOR_ISIN, volume=600000,
            )
        },
        price_bands={
            SUCCESSOR_ISIN: PriceBandRecord(
                isin=SUCCESSOR_ISIN,
                trade_date=RESTATE_SESSION,
                series="EQ",
                upper_circuit_limit=Decimal("260.00"),
                lower_circuit_limit=Decimal("160.00"),
            )
        },
        explicit_series=ExchangeSeries.EQ,
    )
    assert result.filled_count == 1
    assert result.tickets[0].fill_result.filled_quantity == expected_qty


# --- N-136: the window-end book is in the statistic ---------------------------------------


def test_n136_liquidation_brings_open_winners_into_the_profit_factor():
    initial = Decimal("100000.00")
    closed = [{
        "isin": "INE000A01001",
        "exit_date": datetime.date(2023, 12, 20),
        "quantity": 100,
        "entry_price": Decimal("110.0000"),
        "exit_price": Decimal("100.0000"),
        "gross_pnl": Decimal("-1000.00"),
        "net_pnl": Decimal("-1040.00"),
        "total_costs": Decimal("40.00"),
        "dividends": Decimal("0.00"),
        "exit_reason": "STOP_LOSS",
    }]
    open_lots = {
        # A winner the closed ledger cannot see: 100 shares bought at 100, marked at 150.
        "INE111A01015": [_lot(100, "100.0000", "90.0000")],
    }
    bars = {
        ("INE111A01015", RESTATE_SESSION): _bar(
            RESTATE_SESSION, "150.00", "152.00", "149.00", "150.00",
            isin="INE111A01015", volume=1000000,
        )
    }

    result = liquidate_open_book(
        open_lots=open_lots,
        bars_by_isin_date=bars,
        liquidation_date=RESTATE_SESSION,
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        closed_trades=closed,
    )

    # The censored book has no winner at all: its PF is 0 and it cannot see the +5,000.
    assert result["closed_only_profit_factor"] == Decimal("0.00")
    assert result["closed_only_mean_net_expectancy"] == Decimal("-1040.00")
    # The liquidated book prices the open lot at the close, net of exit slippage and statutory costs.
    assert len(result["rows"]) == 1
    assert result["rows"][0]["exit_price"] < Decimal("150.00")
    assert result["liquidated_profit_factor"] > Decimal("1.50")
    assert result["liquidated_mean_net_expectancy"] > Decimal("0.00")
    assert result["closed_net_pnl"] == Decimal("-1040.00")
    # The +5,000 the censored book could not see is in the liquidated P&L, net of the exit costs.
    assert result["rows"][0]["net_pnl"] > Decimal("4900.00")


def test_n136_a_lot_with_no_closing_print_is_counted_not_valued_at_book():
    result = liquidate_open_book(
        open_lots={"INE111A01015": [_lot(100, "100.0000", "90.0000")]},
        bars_by_isin_date={},
        liquidation_date=RESTATE_SESSION,
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        closed_trades=[],
    )
    assert result["rows"] == []
    assert result["missing_prices"] == 1
    assert result["liquidated_mean_net_expectancy"] is None


# --- N-137: the slot goes to the rank, not the alphabet ----------------------------------


def _features(close: str, mom: str) -> SimpleNamespace:
    return SimpleNamespace(
        close=Decimal(close),
        sma_20=Decimal("95.00"),
        sma_50=Decimal("90.00"),
        mom_63=Decimal(mom),
        atr=Decimal("5.00"),
        volume=1000000,
    )


def test_n137_the_higher_rank_takes_the_slot_regardless_of_isin_order():
    low_isin, high_isin = "INE000A01001", "INE999A01009"
    features = {low_isin: _features("100.00", "0.05"), high_isin: _features("100.00", "0.30")}
    strategy = DeliverySwingTrendStrategy(
        entry_rank_indicator="mom_63", allocation_weight=Decimal("0.08")
    )

    for universe in ([low_isin, high_isin], [high_isin, low_isin]):
        intents = strategy.generate_signals(
            as_of=SIGNAL_SESSION,
            next_session=ENTRY_SESSION,
            universe=universe,
            features=features,
        )
        # Both qualify; with one capital slot the ranked order decides which one trades, and it is
        # the same decision whichever order the universe arrives in.
        assert [i.instrument_id for i in intents] == [high_isin, low_isin]


def test_n137_the_unranked_rule_keeps_the_alphabetical_order_prior_trials_used():
    low_isin, high_isin = "INE000A01001", "INE999A01009"
    features = {low_isin: _features("100.00", "0.05"), high_isin: _features("100.00", "0.30")}
    strategy = DeliverySwingTrendStrategy(allocation_weight=Decimal("0.08"))

    intents = strategy.generate_signals(
        as_of=SIGNAL_SESSION,
        next_session=ENTRY_SESSION,
        universe=[high_isin, low_isin],
        features=features,
    )
    assert [i.instrument_id for i in intents] == [low_isin, high_isin]
    assert "entry_rank_indicator" in strategy.parameters
    assert strategy.parameters["entry_rank_indicator"] == "NONE"


# --- N-138: minimum economically viable size ---------------------------------------------


def test_n138_an_entry_below_the_notional_floor_is_a_named_no_trade():
    portfolio = _portfolio("2000.00")
    runner = _runner(portfolio)
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("100.00"),
        atr=Decimal("5.00"),
        session_volume=100000,
        series="EQ",
        allocation_weight=Decimal("0.10"),
        metadata={"intent_id": "S75-MICRO"},
    )
    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=_bar(ENTRY_SESSION, "100.00", "101.00", "99.00", "100.00"),
        target_date=ENTRY_SESSION,
        price_band=_band(ISIN, "110.00", "90.00"),
        explicit_series=ExchangeSeries.EQ,
    )
    # ₹20 fixed brokerage on a ₹200 order is 10% of notional before STT.
    assert ticket.is_no_trade is True
    assert ticket.no_trade_reason == "BELOW_MIN_ENTRY_NOTIONAL"
    assert ticket.status == FillStatus.UNTRIGGERED
    assert portfolio.get_position(ISIN) is None


def test_n138_a_fill_that_lands_below_the_viability_floor_is_refused_not_booked():
    """A 97% gap-down open turns a ₹200,000 entry into a ₹3,000 fill: refuse, do not book."""
    portfolio = _portfolio()
    runner = _runner(portfolio)
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("10.00"),
        session_volume=2000000,
        series="EQ",
        allocation_weight=Decimal("0.10"),
        metadata={"intent_id": "S75-GAP"},
    )
    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=_bar(ENTRY_SESSION, "30.00", "31.00", "29.00", "30.00", volume=2000000),
        target_date=ENTRY_SESSION,
        price_band=_band(ISIN, "40.00", "20.00"),
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket.status == FillStatus.REJECTED_BELOW_MIN_NOTIONAL
    assert ticket.fill_result.filled_quantity == 0
    assert "minimum fill notional" in str(ticket.fill_result.rejection_reason)
    assert portfolio.get_position(ISIN) is None


# --- N-134 / N-135: the refusal has a status, the assumptions are parameters --------------


def test_n134_a_locked_bar_is_not_reported_as_a_circuit_hit():
    portfolio = _portfolio()
    runner = _runner(portfolio)
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("2000.00"),
        atr=Decimal("100.00"),
        session_volume=100000,
        series="EQ",
        allocation_weight=Decimal("0.04"),
    )
    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=_bar(ENTRY_SESSION, "1950.00", "1950.00", "1950.00", "1950.00"),
        target_date=ENTRY_SESSION,
        price_band=None,
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket.status == FillStatus.REJECTED_LOCKED_SESSION
    assert "Locked 0-range session" in str(ticket.fill_result.rejection_reason)


def test_n135_canonical_params_record_the_band_policy_and_the_entry_rank(tmp_path):
    res = run_phase3b2_walkforward(
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        in_sample_only=True,
        max_sessions=6,
        write_verdict_files=False,
    )
    params = dict(res.trial_record.canonical_params)
    # A reader comparing two rows sees what a fill means and how a slot was chosen, instead of
    # inferring both from `criteria_version`.
    assert params["unbanded_session_fill_policy"] == _criteria().unbanded_session_fill_policy
    assert params["entry_rank_indicator"] == _criteria().entry_rank_indicator
    assert params["min_entry_notional"] == str(_criteria().min_entry_notional)
    assert params["min_fill_notional"] == str(_criteria().min_fill_notional)
