"""
Audit §98.10 work-order items, unit level.

1. The gap partition (§98.10 item 1): `feature_gap_boundaries` marks only in-series holes, the indicator
   engine re-warms after one, and a rolling window refuses to span it — including the T-1 median
   turnover a liquidity floor reads (`pit_universe.median_turnover_as_of`).
2. `demerger_restatement_problem` compares a restatement's measurement with its own replay (§98.10 item 2).
3. The evaluations sidecar binds a criteria fingerprint (§98.10 item 4).
"""

from decimal import Decimal
import datetime
from pathlib import Path

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.price_bar import PriceBar
from signal_core.features.engine import (
    SubsegmentIndicatorEngine,
    feature_gap_boundaries,
    trailing_continuous_bars,
)
from signal_core.research.pit_universe import median_turnover_as_of
from signal_core.research.trials import TrialEvaluationError, TrialRegistry


def _bar(day: datetime.date, close: str = "100", traded: str = "100000000") -> PriceBar:
    return PriceBar(
        instrument_id="INE000000099",
        trade_date=day,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
        traded_value=Decimal(traded),
    )


CALENDAR = [
    datetime.date(2022, 1, 3),
    datetime.date(2022, 1, 4),
    datetime.date(2022, 1, 5),
    datetime.date(2022, 1, 6),
    datetime.date(2022, 1, 7),
    datetime.date(2022, 1, 10),
]
HOLE = datetime.date(2022, 1, 5)


def test_gap_boundaries_mark_only_in_series_holes():
    bars = [_bar(day) for day in CALENDAR if day != HOLE]
    boundaries = feature_gap_boundaries(CALENDAR, bars)
    assert [b.trade_date for b in boundaries] == [HOLE]
    assert boundaries[0].gap_type.value == "UNEXPLAINED_MISSING_RECORD"
    assert boundaries[0].sessions_since_previous_record == 1

    # A history that starts late and ends early has listing boundaries, not in-series holes.
    late = [_bar(day) for day in CALENDAR[3:]]
    assert feature_gap_boundaries(CALENDAR, late) == []
    assert feature_gap_boundaries(CALENDAR, []) == []


def test_engine_re_warms_after_an_unexplained_gap():
    bars = [_bar(day, close=str(100 + index)) for index, day in enumerate(CALENDAR) if day != HOLE]
    features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=CALENDAR, actual_price_bars=bars
    )
    by_date = {feature.trade_date: feature for feature in features}
    first_after = by_date[datetime.date(2022, 1, 6)]
    assert first_after.atr_14 is None
    assert first_after.ema_20 is None
    assert first_after.sma_20 is None
    assert first_after.mom_63 is None
    # The first segment's warm-up completed before the gap, so the two are independent series.
    assert by_date[datetime.date(2022, 1, 3)].sma_20 is None


def test_trailing_window_refuses_to_span_a_gap():
    bars = {day: _bar(day) for day in CALENDAR if day != HOLE}
    index = {day: position for position, day in enumerate(CALENDAR)}
    # Four sessions up to 2022-01-06 would include the hole, so the window is refused, not shortened.
    assert trailing_continuous_bars(CALENDAR, bars, datetime.date(2022, 1, 6), 4, index) is None
    assert trailing_continuous_bars(CALENDAR, bars, datetime.date(2022, 1, 7), 2, index) is None
    # Two consecutive sessions after the hole are a clean window, and it is the one a floor may read.
    assert trailing_continuous_bars(CALENDAR, bars, datetime.date(2022, 1, 10), 2, index) is not None
    with pytest.raises(Exception):
        trailing_continuous_bars(CALENDAR, bars, datetime.date(2022, 1, 7), 0, index)


def test_median_turnover_is_none_across_a_gap_and_median_when_clean():
    bars = {day: _bar(day, traded=str(60_000_000 + position * 10_000_000)) for position, day in enumerate(CALENDAR) if day != HOLE}
    index = {day: position for position, day in enumerate(CALENDAR)}
    assert median_turnover_as_of(
        datetime.date(2022, 1, 10),
        calendar_sessions=CALENDAR,
        bars_by_date=bars,
        lookback_sessions=2,
        session_index=index,
    ) == Decimal("95000000")
    # A third session reaches back into the hole, so the window is refused rather than averaged.
    assert median_turnover_as_of(
        datetime.date(2022, 1, 10),
        calendar_sessions=CALENDAR,
        bars_by_date=bars,
        lookback_sessions=3,
        session_index=index,
    ) is None


def test_demerger_restatement_compares_measurement_with_its_replay():
    import scripts.probe_seq10_candidate as certificate

    artifact = {
        "demerger_forced_exits": 0,
        "demerger_forced_refusals": 66,
        "hold_bound_forced_exits": 422,
        "hold_bound_refusals": 7309,
    }
    restatement = {
        "restated": {"demerger_forced_exits": 0, "demerger_forced_refusals": 66},
        "measurement": {"demerger_forced_exits": 0, "demerger_forced_refusals": 0},
        "replay": {
            "demerger_forced_exits": 0,
            "demerger_forced_refusals": 0,
            "hold_bound_forced_exits": 422,
            "hold_bound_refusals": 7309,
        },
    }
    assert certificate.demerger_restatement_problem(artifact, restatement) is None

    contradictory = {**restatement, "measurement": {"demerger_forced_exits": 7, "demerger_forced_refusals": 9}}
    problem = certificate.demerger_restatement_problem(artifact, contradictory)
    assert problem is not None and "replay" in problem

    silent = {**restatement, "replay": {"hold_bound_forced_exits": 422, "hold_bound_refusals": 7309}}
    assert certificate.demerger_restatement_problem(artifact, silent) is not None


def _register(registry: TrialRegistry, trial_id: str, timestamp: str) -> None:
    registry.append_trial(
        trial_id=trial_id,
        hypothesis="fixture",
        rationale="fixture",
        partition="IN_SAMPLE",
        canonical_params={"variant": trial_id},
        fold_spec_fingerprint="FOLD-SPEC-V1-test",
        dataset_fingerprint="DATA-CTNT-V2-test",
        criteria_version=load_go_no_go_criteria().version,
        timestamp_utc=timestamp,
    )


def test_evaluation_sidecar_binds_the_criteria_fingerprint(tmp_path: Path):
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    _register(registry, "TRIAL-S99-A", "2026-11-19T10:00:00+00:00")
    registry.append_trial_evaluation(
        "TRIAL-S99-A",
        Decimal("0.50"),
        "RET-V1-a",
        20,
        "2026-11-19T10:02:00+00:00",
        max_drawdown=Decimal("0.04"),
        criteria_fingerprint="CRIT-FPR-V1-" + "a" * 64,
    )
    reloaded = TrialRegistry(tmp_path / "trial_registry.jsonl")
    stored = reloaded.get_evaluation("TRIAL-S99-A")
    assert stored.criteria_fingerprint == "CRIT-FPR-V1-" + "a" * 64
    assert stored.to_dict()["criteria_fingerprint"] == stored.criteria_fingerprint

    _register(reloaded, "TRIAL-S99-B", "2026-11-19T10:03:00+00:00")
    with pytest.raises(TrialEvaluationError, match="CRIT-FPR-V1"):
        reloaded.append_trial_evaluation(
            "TRIAL-S99-B",
            Decimal("0.60"),
            "RET-V1-b",
            20,
            "2026-11-19T10:04:00+00:00",
            criteria_fingerprint="not-a-fingerprint",
        )
