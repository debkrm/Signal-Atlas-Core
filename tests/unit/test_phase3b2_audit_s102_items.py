"""Audit §100 work order (feat-s102) — the four measurements this round adds, tested directly.

1. A benchmark series that carries a retained one-session level break is refused by name, and the
   buy-and-hold arm only passes because it drops the boundary — removing the drop makes it refuse (N-201).
2. A level step inside a signal's own 200-session feature window is visible to the window test and
   outside it is not (N-197).
3. A categorical price-band counter is `NOT RUN` while the band partition is empty (N-199).
4. The corporate-action archive's coverage is reported against the scanned set, so `UNATTESTED_NO_RECORD`
   is read as "no record in this archive" (N-200).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from scripts.compare_seq10_baselines import (
    BENCHMARK_LEVEL_BREAK_REFUSAL,
    buy_and_hold_arm,
    refuse_unattested_level_break,
)
from scripts.run_seq12_candidate import (
    NOT_RUN,
    InstrumentSeries,
    artifact_consumers,
    band_counter,
    corporate_action_archive_coverage,
)
from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.costs import TransactionCostModel

# --- 1. benchmark continuity (N-201) ------------------------------------------------------


def test_a_retained_level_break_is_refused_by_name():
    with pytest.raises(SystemExit) as refusal:
        refuse_unattested_level_break(
            [("2019-12-18", Decimal("-0.0123")), ("2019-12-19", Decimal("-0.8993"))],
            BENCHMARK_LEVEL_BREAK_REFUSAL,
        )
    assert "2019-12-19" in str(refusal.value)
    assert "N-201" in str(refusal.value)
    # A series whose every return is inside the threshold passes, so the refusal is not vacuous.
    refuse_unattested_level_break([("2019-12-18", Decimal("-0.0123"))], BENCHMARK_LEVEL_BREAK_REFUSAL)


def test_the_buy_and_hold_arm_refuses_the_boundary_once_its_exclusion_stops_working(monkeypatch):
    import scripts.compare_seq10_baselines as baselines

    cost_model = TransactionCostModel(load_go_no_go_criteria().statutory_costs)
    dataset = baselines._load_dataset()
    # The committed arm drops the 2019-12-19 level break, so it builds.
    arm = buy_and_hold_arm(dataset, cost_model)
    assert arm["sessions"] > 0
    assert [row["session"] for row in arm["unmeasured_sessions"]] == ["2019-12-19", "2019-12-20"], arm[
        "unmeasured_sessions"
    ]

    # Disable the exclusion: the −89.9 % step now reaches the kept returns and is refused by name.
    monkeypatch.setattr(baselines, "LEVEL_BREAK_THRESHOLD", Decimal("2"))
    with pytest.raises(SystemExit) as refusal:
        buy_and_hold_arm(dataset, cost_model)
    assert "2019-12-19" in str(refusal.value)


# --- 2. the level step over the lookback window (N-197) -----------------------------------


def _series(sessions: int) -> tuple:
    calendar = [datetime.date(2020, 1, 1) + datetime.timedelta(days=offset) for offset in range(sessions)]
    bars = [
        PriceBar(
            instrument_id="INE000000001",
            trade_date=session,
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.00"),
            volume=1000,
            traded_value=Decimal("100000"),
        )
        for session in calendar
    ]
    return calendar, bars


def test_a_level_step_is_in_the_window_the_rule_reads_and_not_before_it():
    calendar, bars = _series(560)
    # A −20 % level step at bars[300]: the open is 80 against a 100 previous close.
    step_bar = bars[300]
    bars[300] = PriceBar(
        instrument_id=step_bar.instrument_id,
        trade_date=step_bar.trade_date,
        open=Decimal("80.00"),
        high=Decimal("100.00"),
        low=Decimal("79.00"),
        close=Decimal("100.00"),
        volume=1000,
        traded_value=Decimal("100000"),
    )
    series = InstrumentSeries(bars, calendar)
    step = (bars[300].trade_date, Decimal("-0.2000"), "UNATTESTED_NO_RECORD")

    inside = series.steps_in_lookback([step], bars[399].trade_date)
    assert [day for day, _gap, _disposition in inside] == [bars[300].trade_date]
    assert series.steps_in_lookback([step], bars[499].trade_date), "T−199 is inside the window"
    assert series.steps_in_lookback([step], bars[500].trade_date) == [], "T−200 is outside it"
    assert series.steps_in_lookback([step], bars[299].trade_date) == [], "a step after T is not in its window"


def test_a_step_in_another_subsegment_is_not_in_the_window():
    calendar, bars = _series(300)
    # Remove a bar so the series partitions into two continuous subsegments.
    missing = bars[150].trade_date
    gapped = [bar for bar in bars if bar.trade_date != missing]
    series = InstrumentSeries(gapped, calendar)
    step = (gapped[100].trade_date, Decimal("-0.2000"), "UNATTESTED_NO_RECORD")
    later = [day for day in series.rows if day > missing][-1]
    assert series.steps_in_lookback([step], later) == [], (
        "a lookback may not cross a subsegment boundary the engine itself refuses"
    )


# --- 3. price-band counters while the partition is empty (N-199) --------------------------


def test_a_band_counter_is_not_run_while_the_partition_is_empty():
    assert band_counter(0, False) == NOT_RUN
    assert band_counter(7, False) == NOT_RUN
    assert band_counter(0, True) == 0
    assert band_counter(7, True) == 7


# --- 4. archive coverage (N-200) -----------------------------------------------------------


def test_coverage_is_measured_against_the_scanned_set():
    coverage, per_isin = corporate_action_archive_coverage(
        ["INE492A01029", "INE999A01099_NOT_IN_THE_ARCHIVE"]
    )
    assert coverage["instruments_scanned"] == 2
    assert coverage["instruments_with_no_bronze_record"] == 1
    assert coverage["bronze_distinct_isins"] > 0
    assert per_isin["INE492A01029"] > 0


# --- 5. no consumer (N-198) ----------------------------------------------------------------


def test_no_committed_code_reads_the_qa_artifact():
    assert artifact_consumers() == [], artifact_consumers()
