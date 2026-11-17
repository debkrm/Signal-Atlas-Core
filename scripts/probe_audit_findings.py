#!/usr/bin/env python3
"""
Executable acceptance probes for the findings registered in `reports/audit/findings.jsonl`
(Audit §78.15 (c)).

One probe per finding id, so the auditor's acceptance test is a computation the implementer can run
before committing, and a fix that only works on the new path fails the old path's probe by
construction. Each probe raises AssertionError with the measurement that failed; nothing is printed
as a verdict it did not compute.

Usage:
    python scripts/probe_audit_findings.py N-148
    python scripts/probe_audit_findings.py --list
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT / "src"), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.reporting.verdicts import evaluate_verdicts  # noqa: E402

PROBE_EVALUATED_AT = "2026-11-17T12:00:00+00:00"


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": PROBE_EVALUATED_AT}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


def probe_n148() -> None:
    """`total_trades` without liquidated evidence is NOT RUN, not a PASS on the key's name."""
    alone = _by_id({"total_trades": 193})["CRIT-STAT-01"]
    assert alone.status.value == "NOT RUN", f"total_trades alone evaluated {alone.status.value}"
    assert "liquidated_open_positions" in alone.evidence

    with_closed = _by_id({"total_trades": 193, "closed_only_trade_count": 193})["CRIT-STAT-01"]
    assert with_closed.status.value == "NOT RUN", (
        f"censored count with a closed-only label evaluated {with_closed.status.value}"
    )

    reconciled = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 193,
        "liquidated_open_positions": [{"isin": "INE000000001", "net_pnl": "1.00"} for _ in range(12)],
    })["CRIT-STAT-01"]
    assert reconciled.status.value == "PASS", reconciled.evidence
    assert reconciled.computed_value == "205"


def probe_n149() -> None:
    """`CRIT-OVERFIT-03` requires all four pre-registered anchored fold ends."""
    ends = ("2022-06-30", "2022-12-30", "2023-06-30", "2023-12-29")

    def fold(end: str, expectancy: str, pf: str) -> dict:
        return {
            "label": f"IS-{end}",
            "fold_end": end,
            "closed_net_expectancy": Decimal(expectancy),
            "liquidated_profit_factor": Decimal(pf),
        }

    one = _by_id({"is_folds": [fold(ends[0], "100.00", "1.60")]})["CRIT-OVERFIT-03"]
    assert one.status.value == "FAIL", f"one positive fold evaluated {one.status.value}"
    assert computed_missing(one), one.evidence

    two = _by_id({"is_folds": [fold(ends[0], "100.00", "1.60"), fold(ends[1], "100.00", "1.60")]})
    assert two["CRIT-OVERFIT-03"].status.value == "FAIL"

    declared = _by_id({"positive_is_fold_ratio": Decimal("0.75")})["CRIT-OVERFIT-03"]
    assert declared.status.value == "NOT RUN", declared.evidence

    full = _by_id({"is_folds": [fold(end, "100.00", "1.60") for end in ends]})["CRIT-OVERFIT-03"]
    assert full.status.value == "PASS", full.evidence
    assert full.computed_value == "1.0000"


def computed_missing(evaluation) -> bool:
    return evaluation.computed_value is None


def probe_n150() -> None:
    """`CRIT-OVERFIT-06` is NOT RUN below two validation folds, ratio or not."""
    single = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 1,
    })["CRIT-OVERFIT-06"]
    assert single.status.value == "NOT RUN", f"one validation fold evaluated {single.status.value}"
    assert "minimum 2 independent" in single.evidence

    two = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert two.status.value == "PASS", two.evidence


def probe_n151() -> None:
    """Every multi-ISIN symbol in the committed interval table carries an ISIN_TRANSITION row."""
    from derive_2022_2024_corpora import generate_isin_transition_rows
    from signal_core.storage.security_master import (
        CorporateActionType,
        load_cash_universe_symbol_intervals,
        load_corporate_actions,
    )

    intervals = load_cash_universe_symbol_intervals()
    all_pairs = {
        (row.old_isin, row.new_isin)
        for row in generate_isin_transition_rows(intervals, set())
    }
    corpus = load_corporate_actions()
    documented = {
        (row.old_isin, row.new_isin)
        for row in corpus
        if row.action_type == CorporateActionType.ISIN_TRANSITION and row.old_isin and row.new_isin
    }
    missing = sorted(all_pairs - documented)
    assert not missing, f"{len(missing)} identity pair(s) undocumented, e.g. {missing[:3]}"

    multi_isin_symbols = {
        interval.symbol
        for interval in intervals
        if len({i.isin for i in intervals if i.symbol == interval.symbol}) > 1
    }
    covered_symbols = {
        row.symbol for row in corpus if row.action_type == CorporateActionType.ISIN_TRANSITION
    }
    uncovered = sorted(multi_isin_symbols - covered_symbols)
    assert not uncovered, f"{len(uncovered)} multi-ISIN symbol(s) without a row: {uncovered[:5]}"
    assert len(documented) == len(all_pairs), (
        f"{len(documented)} transition row(s) for {len(all_pairs)} documented pair(s)"
    )


def probe_n152() -> None:
    """No transition row claims attestation without naming a circular (fail-closed provenance)."""
    from signal_core.storage.security_master import CorporateActionType, load_corporate_actions

    unverified = 0
    for row in load_corporate_actions():
        if row.action_type != CorporateActionType.ISIN_TRANSITION:
            continue
        assert row.provenance in ("CONTENT_IDENTIFIED_ONLY", "VERIFIED"), row.provenance
        if row.provenance == "VERIFIED":
            assert row.circular_ref and not str(row.circular_ref).startswith("UNATTESTED_"), (
                f"{row.symbol} claims VERIFIED identity with reference {row.circular_ref!r}"
            )
        else:
            assert str(row.circular_ref).startswith("UNATTESTED_"), (
                f"{row.symbol} is unverified but its reference is not marked UNATTESTED_: {row.circular_ref!r}"
            )
            unverified += 1
    assert unverified > 0, "no transition row was inspected"


def probe_n153() -> None:
    """
    IRB's boundary spike is post-split trading, not an unadjusted artefact.

    Raw Bhavcopy: 2023-02-21 close 297.45, 2023-02-22 open 30.40 with PREVCLOSE 297.45 (a 1:10
    face-value change at the identity boundary), then close 34.05 and 29.70. The adjusted series'
    boundary move is therefore the raw post-split move, not a print of the split itself.
    """
    from signal_core.storage.security_master import load_corporate_actions

    closes: Dict[str, Decimal] = {}
    for name in ("cm21FEB2023bhav.csv.zip", "cm22FEB2023bhav.csv.zip", "cm23FEB2023bhav.csv.zip"):
        archive = REPO_ROOT / "data" / "raw" / "2023" / name
        assert archive.is_file(), f"missing committed raw archive {archive}"
        import zipfile

        with zipfile.ZipFile(archive) as zf:
            with zf.open(zf.namelist()[0]) as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
                for row in reader:
                    if row.get("SYMBOL", "").strip() == "IRB" and row.get("SERIES", "").strip() == "EQ":
                        closes[name[:8]] = (
                            Decimal(row["CLOSE"].strip()),
                            Decimal(row["OPEN"].strip()),
                            Decimal(row["PREVCLOSE"].strip()),
                        )

    # Each entry is (close, open, prevclose).
    prior_close, _prior_open, _prior_prev = closes["cm21FEB2"]
    split_close, split_open, split_prev = closes["cm22FEB2"]
    next_close, _next_open, _next_prev = closes["cm23FEB2"]

    assert split_prev == prior_close, (split_prev, prior_close)
    face_value_ratio = prior_close / split_open
    assert Decimal("9.5") < face_value_ratio < Decimal("10.5"), (
        f"boundary open/prior-close ratio {face_value_ratio} is not a 1:10 face-value change"
    )
    boundary_move = (split_close / (prior_close / Decimal("10")) - Decimal("1")) * Decimal("100")
    assert Decimal("14.0") < boundary_move < Decimal("15.0"), (
        f"adjusted boundary move {boundary_move:.2f}% does not reproduce the raw post-split move"
    )
    next_move = (next_close / split_close - Decimal("1")) * Decimal("100")
    assert Decimal("-13.5") < next_move < Decimal("-12.0"), f"next-session move {next_move:.2f}%"

    # The corpus records the identity, not a share ratio: it must not claim IRB's split as 1:1.
    irb_rows = [row for row in load_corporate_actions() if row.symbol == "IRB"]
    assert any(row.action_type.value == "ISIN_TRANSITION" for row in irb_rows), "IRB identity row missing"


PROBES: Dict[str, Callable[[], None]] = {
    "N-148": probe_n148,
    "N-149": probe_n149,
    "N-150": probe_n150,
    "N-151": probe_n151,
    "N-152": probe_n152,
    "N-153": probe_n153,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one audit finding's acceptance probe")
    parser.add_argument("finding_id", nargs="?", help="Finding id, e.g. N-148")
    parser.add_argument("--list", action="store_true", help="List probe ids")
    args = parser.parse_args()

    if args.list:
        print("\n".join(sorted(PROBES)))
        return 0

    if not args.finding_id:
        parser.error("a finding id is required (or pass --list)")
    probe = PROBES.get(args.finding_id)
    if probe is None:
        print(f"FAIL {args.finding_id}: no probe registered")
        return 1
    try:
        probe()
    except AssertionError as exc:
        print(f"FAIL {args.finding_id}: {exc}")
        return 1
    print(f"PASS {args.finding_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
