#!/usr/bin/env python3
"""
FEATURE GAP PARTITION — Audit §98.10 item 1 / AGENTS.md §6.3

The §97 corpus builder stopped reading a calendar gap as a one-session return, but the gap itself
survived in `prices_by_instrument`: 539 instruments carry 58,941 authoritative sessions they have no
bar for, 74 of them holes of 20 sessions or more, and no derived-layer consumer was told. §6.3 asks
for two things beyond the reconciliation half — a partition every rolling feature reads, and the count
of feature values currently computed across a gap.

This script derives the partition from the authoritative calendar and the committed corpus (`trading_dates`
× each instrument's bars), never from a typed list, and writes the committed artifact:

- `partition_fingerprint` — SHA-256 over every `(isin, session)` boundary, so a reader can recompute it;
- counts: instruments with a hole, in-series missing sessions, subsegments, and the material holes
  (>= 20 sessions) with their per-instrument segment boundaries;
- `feature_values_across_gap` — measured by recomputing the standard feature suite per instrument and
  testing, for every non-None value, whether that feature's lookback window lies inside one subsegment.
  A value whose window contains an `UNEXPLAINED_MISSING_RECORD` boundary would be counted here.

The partition is a pure function (`feature_gap_boundaries`) of the calendar and the bars, so the engine
and this artifact cannot disagree: `scripts/probe_audit_findings.py N-191` recomputes the digest and
fails closed on any difference.

Usage:
    python scripts/measure_feature_gap_partition.py [--check]
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from signal_core.contracts.exchange_series import PriceSeriesContinuityValidator  # noqa: E402
from signal_core.contracts.price_bar import PriceBar  # noqa: E402
from signal_core.features.engine import (  # noqa: E402
    SubsegmentIndicatorEngine,
    feature_gap_boundaries,
)

CORPUS_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"
OUTPUT_PATH = REPO_ROOT / "reports" / "analysis" / "s99" / "feature_gap_partition.json"

# The lookback each published feature needs, in calendar sessions ending at (and including) the bar.
# `mom_63` compares against the 63rd prior close, so it needs 64 sessions; `rsi_14` needs 15 closes.
FEATURE_LOOKBACKS = {
    "sma_20": 20,
    "sma_50": 50,
    "ema_20": 20,
    "ema_50": 50,
    "ema_200": 200,
    "atr_14": 14,
    "rsi_14": 15,
    "rolling_high_20": 20,
    "rolling_low_20": 20,
    "rolling_high_50": 50,
    "rolling_low_50": 50,
    "mom_63": 64,
}
WITNESSES = ("INE784B01035", "INE251H01024")
MATERIAL_HOLE_SESSIONS = 20


def load_corpus() -> dict:
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def bars_for(isin: str, rows: list[dict]) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_id=isin,
            trade_date=datetime.date.fromisoformat(row["trade_date"]),
            open=Decimal(row["open"]),
            high=Decimal(row["high"]),
            low=Decimal(row["low"]),
            close=Decimal(row["close"]),
            volume=int(row["volume"]),
            traded_value=Decimal(row["traded_value"]),
        )
        for row in rows
    ]


def longest_hole_sessions(boundaries, session_index) -> int:
    longest = run = 0
    previous = None
    for boundary in boundaries:
        position = session_index[boundary.trade_date]
        run = run + 1 if previous is not None and position == previous + 1 else 1
        longest = max(longest, run)
        previous = position
    return longest


def segments_for(boundaries, present_dates, session_index) -> list[list[str]]:
    """The half-open session ranges of each subsegment, from the first bar to the last (§6.3)."""
    holes = {session_index[b.trade_date] for b in boundaries}
    first, last = min(session_index[d] for d in present_dates), max(session_index[d] for d in present_dates)
    ordered = sorted(session_index.items(), key=lambda item: item[1])
    segments: list[list[str]] = []
    start = first
    for position in range(first, last + 1):
        if position in holes:
            if position - 1 >= start:
                segments.append([ordered[start][0].isoformat(), ordered[position - 1][0].isoformat()])
            start = position + 1
    if last >= start:
        segments.append([ordered[start][0].isoformat(), ordered[last][0].isoformat()])
    return segments


def count_values_across_gap(features, hole_prefix, session_index, attribute: str, lookback: int):
    """
    Counts non-None values of one feature, and how many of them ride a window containing a boundary.

    `features` is the engine's own output for this instrument: the values it would trade on. The window
    for a value at session t is the `lookback` calendar sessions ending at t; a boundary anywhere inside
    it is a cross-gap value (§6.3). `hole_prefix` is the boundary count up to each session, so the test
    is O(1) per value rather than a scan. Both numbers are measured, not inferred from the engine.
    """
    total = 0
    across = 0
    for feature in features:
        if getattr(feature, attribute) is None:
            continue
        total += 1
        end = session_index[feature.trade_date]
        start = end - lookback + 1
        if start < 0 or hole_prefix[end + 1] != hole_prefix[start]:
            across += 1
    return total, across


def measure() -> dict:
    corpus = load_corpus()
    sessions = [datetime.date.fromisoformat(value) for value in corpus["trading_dates"]]
    session_index = {session: position for position, session in enumerate(sessions)}

    partition = hashlib.sha256()
    instruments_with_gaps = 0
    missing_sessions = 0
    subsegments = 0
    material: list[dict] = []
    witness_detail: dict[str, dict] = {}
    values_total = 0
    values_across = 0

    for isin in sorted(corpus["prices_by_instrument"]):
        bars = bars_for(isin, corpus["prices_by_instrument"][isin])
        boundaries = feature_gap_boundaries(sessions, bars)
        if boundaries:
            instruments_with_gaps += 1
            missing_sessions += len(boundaries)
            subsegments += len(
                PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
                    expected_calendar_sessions=sessions,
                    actual_price_bars=bars,
                )
            )
            for boundary in boundaries:
                partition.update(f"{isin}\x00{boundary.trade_date.isoformat()}\n".encode("utf-8"))

        features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
            expected_calendar_sessions=sessions,
            actual_price_bars=bars,
        )
        hole_prefix = [0] * (len(sessions) + 1)
        holes = {session_index[b.trade_date] for b in boundaries}
        for position in range(len(sessions)):
            hole_prefix[position + 1] = hole_prefix[position] + (1 if position in holes else 0)
        for attribute, lookback in FEATURE_LOOKBACKS.items():
            total, across = count_values_across_gap(
                features, hole_prefix, session_index, attribute, lookback
            )
            values_total += total
            values_across += across

        if boundaries and longest_hole_sessions(boundaries, session_index) >= MATERIAL_HOLE_SESSIONS:
            material.append(
                {
                    "isin": isin,
                    "symbol": corpus["symbols_by_instrument"].get(isin),
                    "unexplained_missing_sessions": len(boundaries),
                    "longest_hole_sessions": longest_hole_sessions(boundaries, session_index),
                    "segments": segments_for(
                        boundaries, {bar.trade_date for bar in bars}, session_index
                    ),
                }
            )

        if isin in WITNESSES:
            first_gap = boundaries[0].trade_date if boundaries else None
            witness_detail[isin] = {
                "symbol": corpus["symbols_by_instrument"].get(isin),
                "bars": len(bars),
                "unexplained_missing_sessions": len(boundaries),
                "longest_hole_sessions": longest_hole_sessions(boundaries, session_index),
                "first_boundary": first_gap.isoformat() if first_gap else None,
                "segments": segments_for(
                    boundaries, {bar.trade_date for bar in bars}, session_index
                ),
            }

    return {
        "artifact_format": "signal-atlas-feature-gap-partition-v1",
        "section": "§98.10 item 1",
        "not_audited": True,
        "derived_from": {
            "corpus": CORPUS_PATH.relative_to(REPO_ROOT).as_posix(),
            "content_fingerprint": corpus["content_fingerprint"],
            "trading_dates": len(sessions),
            "first_session": sessions[0].isoformat(),
            "last_session": sessions[-1].isoformat(),
            "instruments": len(corpus["prices_by_instrument"]),
        },
        "rule": (
            "Every calendar session strictly between an instrument's first and last bar that carries no "
            "bar is an UNEXPLAINED_MISSING_RECORD boundary (AGENTS.md §6.3). Rolling features re-warm at "
            "each boundary: `feature_gap_boundaries` in src/signal_core/features/engine.py is the single "
            "definition, and `trailing_continuous_bars` / `pit_universe.median_turnover_as_of` refuse a "
            "window that contains one."
        ),
        "partition_fingerprint": "GAP-PTN-V1-" + partition.hexdigest(),
        "instruments_with_gaps": instruments_with_gaps,
        "unexplained_missing_sessions": missing_sessions,
        "subsegments": subsegments,
        "material_hole_sessions": MATERIAL_HOLE_SESSIONS,
        "material_holes": material,
        "feature_values": {
            "measured_on": sorted(FEATURE_LOOKBACKS),
            "values_total": values_total,
            "values_across_gap": values_across,
        },
        "witnesses": witness_detail,
    }


def main(argv: list[str]) -> int:
    artifact = measure()
    rendered = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    if "--check" in argv:
        if not OUTPUT_PATH.is_file():
            print(f"[FAIL] no committed partition at {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}")
            return 1
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != rendered:
            print("[FAIL] the committed partition is not the one this corpus derives")
            return 1
        print(
            f"[PASS] partition {artifact['partition_fingerprint'][:24]}… reproduces: "
            f"{artifact['instruments_with_gaps']} instrument(s), "
            f"{artifact['unexplained_missing_sessions']} missing session(s), "
            f"{artifact['feature_values']['values_across_gap']} cross-gap feature value(s)"
        )
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"[INFO] {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}: "
        f"{artifact['instruments_with_gaps']} instrument(s) with "
        f"{artifact['unexplained_missing_sessions']} missing session(s), "
        f"{len(artifact['material_holes'])} material hole(s), "
        f"{artifact['feature_values']['values_total']} feature value(s), "
        f"{artifact['feature_values']['values_across_gap']} across a gap"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
