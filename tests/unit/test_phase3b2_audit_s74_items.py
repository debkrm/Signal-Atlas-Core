"""
Unit tests for the Audit §74 remediation items (audit §74 at 4c92356, reviewing 4eb5c58).

Target invariants:
- H-126: a merger or a face-value ISIN transition moves the Portfolio position, the lot book and the
  pending ProtectiveStopOrder onto the successor identity at the same ratio, so the carried stop is
  still testable on the next session and fills the quantity the position actually holds.
- N-133: a blank successor identity leaves the old stop armed (refuse before destroying).
- N-132: the daily return series and its moments are persisted, so the DSR/CRIT-OVERFIT-02 is
  recomputable offline from committed bytes instead of only in-process.
- Ruling D: the committed `unbanded_session_fill_policy` fills an unbanded session unless the bar is
  locked (high == low), and STRICT_BAND_REQUIRED still refuses an unbanded order (H-83 preserved).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_types import OrderSide
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.band_policy import PriceBandPolicy
from signal_core.execution.order_runner import (
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
    OrderRunnerEligibilityError,
)
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.research.containment import PartitionRole
from signal_core.research.significance import (
    annualized_sharpe,
    daily_returns_from_artifact,
    evaluate_strategy_significance,
    sample_kurtosis,
    sample_skewness,
    serialize_daily_returns,
)
from signal_core.research.trials import TrialRegistry
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import CorporateAction, CorporateActionType
from scripts.run_phase3b2_walkforward import (
    build_authoritative_runner,
    carry_protective_stop_across_corporate_action,
    restate_lots_across_merger,
    restate_lots_for_share_ratio,
    run_phase3b2_walkforward,
)

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


def _runner(portfolio: Portfolio, band_policy=None) -> DailyTPlus1OrderRunner:
    return build_authoritative_runner(
        portfolio=portfolio,
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        calendar=_calendar(),
        criteria=_criteria(),
        atr_stop_multiple=Decimal("2.0"),
        band_policy=band_policy,
    )


def _band(isin: str, trade_date: datetime.date) -> PriceBandRecord:
    return PriceBandRecord(
        isin=isin,
        trade_date=trade_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
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


def _buy(runner: DailyTPlus1OrderRunner, target: datetime.date = ENTRY_SESSION):
    """Entry reference 1000, ATR 20, k=2.0 -> 50 shares at a 960.000 stop."""
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=100000,
        series="EQ",
        allocation_weight=Decimal("0.05"),
        metadata={"intent_id": "S74-BUY"},
    )
    return runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=_bar(target, "1000.00", "1010.00", "990.00", "1000.00"),
        target_date=target,
        price_band=_band(ISIN, target),
        explicit_series=ExchangeSeries.EQ,
    )


def _lot(quantity: int, entry_price: str, stop_price: str = "960.000") -> dict:
    return {
        "entry_date": ENTRY_SESSION,
        "entry_price": Decimal(entry_price),
        "quantity": quantity,
        "original_quantity": quantity,
        "intended_risk": Decimal("2000.00"),
        "stop_price": Decimal(stop_price),
        "costs": Decimal("10.00"),
        "dividends": Decimal("0.00"),
    }


def _merger(num: str = "2", den: str = "1") -> CorporateAction:
    return CorporateAction(
        isin=ISIN,
        ex_date=RESTATE_SESSION,
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal(num),
        ratio_denominator=Decimal(den),
        new_isin=SUCCESSOR_ISIN,
        delisting_price=Decimal("480.00"),
        description="S74 synthetic merger",
    )


def _transition(num: str = "10", den: str = "1") -> CorporateAction:
    return CorporateAction(
        isin=ISIN,
        ex_date=RESTATE_SESSION,
        action_type=CorporateActionType.ISIN_TRANSITION,
        old_isin=ISIN,
        new_isin=SUCCESSOR_ISIN,
        ratio_numerator=Decimal(num),
        ratio_denominator=Decimal(den),
        description="S74 synthetic face-value sub-division",
    )


# --- H-126: the position, the lot book and the stop move together -------------------------


def test_h126_merger_rekeys_portfolio_lots_and_stop_to_one_identity():
    """Probe §74.9 item 1: buy 20, apply a 2:1 merger, and all three stores hold 40 at 480."""
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED
    stop_before = runner.protective_stops[ISIN]
    assert stop_before.quantity == 50 and stop_before.stop_price == Decimal("960.000")

    open_lots = {ISIN: [_lot(50, "1000.0000")]}
    merger = _merger("2", "1")
    price_before = portfolio.get_position(ISIN).average_entry_price

    # The Portfolio is the authority for identity: the same call the harness makes each session.
    portfolio.apply_corporate_action(merger)
    frac_basis = restate_lots_across_merger(open_lots, merger)
    assert carry_protective_stop_across_corporate_action(runner, merger) is True

    # 50 x 2 = 100 whole shares, no fractional slice, so no cash-in-lieu basis to reconcile.
    assert frac_basis == Decimal("0.00")
    position = portfolio.get_position(SUCCESSOR_ISIN)
    assert portfolio.get_position(ISIN) is None
    assert position is not None and position.quantity == 100
    assert sum(lot["quantity"] for lot in open_lots[SUCCESSOR_ISIN]) == 100
    assert open_lots.get(ISIN, []) == []
    stop = runner.protective_stops[SUCCESSOR_ISIN]
    assert ISIN not in runner.protective_stops
    # One identity, one quantity, one price scale across all three stores.
    assert stop.quantity == position.quantity == open_lots[SUCCESSOR_ISIN][0]["quantity"] == 100
    assert stop.stop_price == Decimal("480.0000")
    # The portfolio restates its own entry price by the same ratio (it carries buy charges in the
    # basis, so it is not the lot's price; the invariant is the ratio, not a literal).
    assert position.average_entry_price == price_before * Decimal("1") / Decimal("2")
    assert open_lots[SUCCESSOR_ISIN][0]["entry_price"] * Decimal("2") == Decimal("1000.0000")


def test_h126_isin_transition_rescales_all_three_stores_for_a_10_to_1_subdivision():
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED

    open_lots = {ISIN: [_lot(50, "1000.0000")]}
    transition = _transition("10", "1")

    portfolio.apply_corporate_action(transition)
    restate_lots_for_share_ratio(open_lots, ISIN, SUCCESSOR_ISIN, 10, 1)
    assert carry_protective_stop_across_corporate_action(runner, transition) is True

    position = portfolio.get_position(SUCCESSOR_ISIN)
    assert position is not None and position.quantity == 500
    lot = open_lots[SUCCESSOR_ISIN][0]
    assert lot["quantity"] == 500
    assert lot["entry_price"] == Decimal("100.0000")
    assert lot["stop_price"] == Decimal("96.0000")
    stop = runner.protective_stops[SUCCESSOR_ISIN]
    assert stop.quantity == 500
    assert stop.stop_price == Decimal("96.0000")
    # Before §74 the lot kept its pre-subdivision 50 shares while the stop carried 500: the market
    # value of the lot and the size of its protection disagreed by the exchange ratio.
    assert lot["quantity"] == position.quantity == stop.quantity


@pytest.mark.parametrize(
    "action,expected_qty,bar_prices,band_limits",
    [
        # Successor trades on a ~480 scale after a 2:1 merger.
        (_merger("2", "1"), 100, ("470.00", "475.00", "460.00", "465.00"), ("550.00", "430.00")),
        # Successor trades on a ~96 scale after a 10:1 face-value sub-division.
        (_transition("10", "1"), 500, ("94.00", "95.00", "92.00", "93.00"), ("110.00", "86.00")),
    ],
)
def test_h126_carried_stop_still_fires_on_the_successor_next_session(
    action, expected_qty, bar_prices, band_limits
):
    """The carried order is not decoration: a next-session crash through it fills the successor."""
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED
    open_lots = {ISIN: [_lot(50, "1000.0000")]}

    portfolio.apply_corporate_action(action)
    if action.action_type == CorporateActionType.MERGER:
        restate_lots_across_merger(open_lots, action)
    else:
        restate_lots_for_share_ratio(open_lots, ISIN, SUCCESSOR_ISIN, 10, 1)
    assert carry_protective_stop_across_corporate_action(runner, action) is True

    open_, high, low, close = bar_prices
    result = runner.evaluate_protective_stops(
        session_date=RESTATE_SESSION,
        bars={
            SUCCESSOR_ISIN: _bar(
                RESTATE_SESSION, open_, high, low, close, isin=SUCCESSOR_ISIN, volume=600000
            )
        },
        price_bands={
            SUCCESSOR_ISIN: PriceBandRecord(
                isin=SUCCESSOR_ISIN,
                trade_date=RESTATE_SESSION,
                series="EQ",
                upper_circuit_limit=Decimal(band_limits[0]),
                lower_circuit_limit=Decimal(band_limits[1]),
            )
        },
        explicit_series=ExchangeSeries.EQ,
    )
    assert result.filled_count == 1
    fill = result.tickets[0].fill_result
    assert fill.status == FillStatus.FILLED
    assert fill.order.instrument_id == SUCCESSOR_ISIN
    # One fill, of the quantity the portfolio holds under the successor identity.
    assert fill.filled_quantity == expected_qty
    assert runner.protective_stops == {}
    assert portfolio.get_position(SUCCESSOR_ISIN).is_closed


# --- N-133: refuse before destroying -----------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
def test_n133_blank_successor_leaves_the_old_stop_armed(blank):
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert _buy(runner).status == FillStatus.FILLED
    before = runner.protective_stops[ISIN]

    assert runner.transfer_protective_stop(ISIN, blank, 10, 1) is False

    # The stop is the only protection the position has: the refusal must not be what removes it.
    assert runner.protective_stops[ISIN] is before
    assert before.quantity == 50 and before.stop_price == Decimal("960.000")

    # ... and the run's counter therefore sees a held-but-unroutable carry rather than a silent drop.
    class _Action:
        isin = ISIN
        new_isin = blank
        ratio_numerator = Decimal("10")
        ratio_denominator = Decimal("1")

    assert carry_protective_stop_across_corporate_action(runner, _Action()) is False
    assert runner.protective_stops[ISIN] is before


# --- N-132: the DSR input is persisted and recomputable ----------------------------------


def _registry_with_two_scored_trials(path: Path) -> TrialRegistry:
    registry = TrialRegistry(path)
    for index, (trial_id, sharpe) in enumerate(
        [("TRIAL-S74-N132-A", Decimal("0.400000")), ("TRIAL-S74-N132-B", Decimal("-0.300000"))]
    ):
        registry.append_trial(
            trial_id=trial_id,
            hypothesis="S74 N-132 probe",
            rationale="Two scored trials so the DSR variance is strictly positive.",
            partition=PartitionRole.IN_SAMPLE,
            canonical_params={"probe": "n132"},
            fold_spec_fingerprint="FOLD-SPEC-V1-S74",
            dataset_fingerprint="DATA-CTNT-V2-S74",
            criteria_version=_criteria().version,
            timestamp_utc=f"2026-11-17T0{index + 1}:00:00+00:00",
        )
        registry.append_trial_evaluation(
            trial_id=trial_id,
            sharpe_ratio=sharpe,
            returns_digest=f"RET-V1-s74{index}",
            observation_count=60,
            evaluated_at_utc=f"2026-11-17T0{index + 3}:00:00+00:00",
        )
    return registry


def _returns() -> list[Decimal]:
    # A deterministic series with non-zero variance, skew and kurtosis.
    out = []
    for i in range(60):
        magnitude = Decimal((i % 7) + 1) / Decimal("100000")
        out.append(magnitude if i % 3 else -magnitude * Decimal("2"))
    return out


def _dates(count: int) -> list[datetime.date]:
    start = datetime.date(2022, 1, 3)
    return [start + datetime.timedelta(days=i) for i in range(count)]


def test_n132_dsr_is_recomputable_from_the_persisted_return_series(tmp_path):
    registry = _registry_with_two_scored_trials(tmp_path / "reg.jsonl")
    criteria = _criteria()
    returns = _returns()

    in_process = evaluate_strategy_significance(returns, registry, criteria)
    assert in_process.dsr_result is not None

    # What the artifact carries: the exact series, keyed by session date, and nothing else.
    artifact = {"daily_returns": serialize_daily_returns(_dates(len(returns)), returns)}
    recomputed = evaluate_strategy_significance(
        daily_returns_from_artifact(artifact), registry, criteria
    )

    # Byte-for-byte recomputable: the probe §74.7 names.
    assert recomputed.dsr_result.deflated_sharpe_ratio == in_process.dsr_result.deflated_sharpe_ratio
    assert recomputed.haircut_result.haircut_sharpe_ratio == in_process.haircut_result.haircut_sharpe_ratio
    assert recomputed.annualized_sharpe == in_process.annualized_sharpe == annualized_sharpe(returns)
    assert recomputed.skewness == in_process.skewness == sample_skewness(returns)
    assert recomputed.kurtosis == in_process.kurtosis == sample_kurtosis(
        returns, convention=criteria.kurtosis_convention
    )
    assert recomputed.observation_count == len(returns)

    # A one-observation edit changes the answer, so the equality above is not vacuous.
    tampered = dict(artifact["daily_returns"])
    tampered[sorted(tampered)[10]] = str(Decimal("0.050000"))
    altered = evaluate_strategy_significance(
        daily_returns_from_artifact({"daily_returns": tampered}), registry, criteria
    )
    assert altered.dsr_result.deflated_sharpe_ratio != in_process.dsr_result.deflated_sharpe_ratio


def test_n132_artifact_without_the_series_cannot_be_recomputed():
    from signal_core.research.significance import SignificanceError

    # An artifact that carries only the digest describes an input nobody can feed back in.
    with pytest.raises(SignificanceError, match="no persisted daily_returns series"):
        daily_returns_from_artifact({"returns_digest": "RET-V1-deadbeef", "observation_count": 493})


# --- Ruling D: the unbanded-session fill policy ------------------------------------------


def _unbanded_buy(runner: DailyTPlus1OrderRunner, bar: PriceBar):
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=bar.volume,
        series="EQ",
        allocation_weight=Decimal("0.05"),
        metadata={"intent_id": "S74-UNBANDED"},
    )
    return runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=bar,
        target_date=ENTRY_SESSION,
        price_band=None,
        explicit_series=ExchangeSeries.EQ,
    )


def test_ruling_d_committed_policy_fills_an_unbanded_session_with_a_real_range():
    criteria = _criteria()
    assert criteria.unbanded_session_fill_policy == "LOCKED_BAR_REFUSAL_ONLY"
    portfolio = _portfolio()
    runner = _runner(portfolio)
    assert runner.band_policy is PriceBandPolicy.LOCKED_BAR_REFUSAL_ONLY

    ticket = _unbanded_buy(runner, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    # 176 of 179 instruments in this corpus have no attested band; under H-83 they could not trade.
    assert ticket.status == FillStatus.FILLED
    assert ticket.fill_result.filled_quantity == 50
    # No limit was invented for the session: the evidence flag says so, and nothing was synthesized.
    assert ticket.fill_result.circuit_evidence_present is False
    assert ticket.fill_result.effective_upper_circuit_limit is None
    assert ticket.fill_result.effective_lower_circuit_limit is None


def test_ruling_d_locked_bar_is_refused_even_without_a_band():
    portfolio = _portfolio()
    runner = _runner(portfolio)

    # high == low is §5.3's actual failure mode: zero depth on one side of the book.
    ticket = _unbanded_buy(runner, _bar(ENTRY_SESSION, "975.00", "975.00", "975.00", "975.00"))

    assert ticket.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert "Locked 0-range session" in str(ticket.fill_result.rejection_reason)
    assert ticket.fill_result.filled_quantity == 0
    assert portfolio.get_position(ISIN) is None


def test_ruling_d_strict_policy_still_refuses_an_unbanded_session():
    """H-83 as written is preserved: selecting STRICT restores the refusal exactly."""
    portfolio = _portfolio()
    runner = _runner(portfolio, band_policy=PriceBandPolicy.STRICT_BAND_REQUIRED)
    assert runner.band_policy is PriceBandPolicy.STRICT_BAND_REQUIRED

    with pytest.raises(OrderRunnerEligibilityError, match="Mandatory price band evidence missing for BUY entry"):
        _unbanded_buy(runner, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))


def test_ruling_d_a_run_may_not_differ_from_the_committed_policy(tmp_path):
    with pytest.raises(ValueError, match="disagrees with the committed criteria"):
        run_phase3b2_walkforward(
            registry_path=tmp_path / "trial_reg.jsonl",
            verdict_output_dir=tmp_path / "verdicts",
            in_sample_only=True,
            max_sessions=5,
            band_policy="STRICT_BAND_REQUIRED",
        )
