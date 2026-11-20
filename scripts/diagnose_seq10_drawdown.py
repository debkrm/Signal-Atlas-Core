#!/usr/bin/env python3
"""
SEQ 10 READ-ONLY DRAWDOWN & REFUSAL DECOMPOSITION — Audit §97.10 items 3-4 (§98)

Reads the committed corpus and the committed engine, runs **one** re-render of seq 10's baseline
configuration (the same `BASELINE_TRIAL_ID`, window, criteria and parameters `run_seq10_candidate`
records into a temporary registry copy), and publishes two artifacts:

- `reports/analysis/s98/seq10_drawdown_decomposition.json` — closed trades, refusals and the equity curve
  across `2018-2019` vs `2020-03` vs the rest, and across entry-date liquidity tiers;
- `reports/analysis/s98/seq10_demerger_restatement.json` — the held-position demerger counter the fixed
  code produces, restating the `0` / `66` pair the committed artifacts publish (§10.1, N-194).

Nothing registered, evaluated or sealed is written: the run records into a copy of the trial registry in a
temporary directory, the holdout window is never read (the window ends 2023-12-31), and the registry of
record is hashed before and after to prove it. This is a diagnostic, not a verdict (§9.1): every number it
prints is computed here, and it is not audited.

Usage:
    python scripts/diagnose_seq10_drawdown.py
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
import scripts.run_seq10_candidate as candidate_runner  # noqa: E402
from signal_core.contracts.criteria import compute_criteria_fingerprint  # noqa: E402
from signal_core.storage.artifact_digest import text_digest  # noqa: E402

ANALYSIS_DIR = REPO_ROOT / "reports" / "analysis" / "s98"
DECOMPOSITION_ARTIFACT = ANALYSIS_DIR / "seq10_drawdown_decomposition.json"
RESTATEMENT_ARTIFACT = ANALYSIS_DIR / "seq10_demerger_restatement.json"
RESTATED_ARTIFACTS = (
    "reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json",
    "reports/analysis/s94/seq10_baseline_2018_2023_verdict.json",
)
REGISTRY_FILES = (
    "data/trials/trial_registry.jsonl",
    "data/trials/trial_registry.jsonl.manifest",
    "data/trials/trial_registry.jsonl.evaluations",
    "data/trials/trial_registry.jsonl.evaluations.manifest",
)
PERIODS = (
    ("2018-2019", datetime.date(2018, 4, 1), datetime.date(2019, 12, 31)),
    ("2020-03", datetime.date(2020, 3, 1), datetime.date(2020, 3, 31)),
    ("2020-04..2023-12", datetime.date(2020, 4, 1), datetime.date(2023, 12, 31)),
)
# Entry-date liquidity: the median traded value of the 20 sessions before entry, in rupees.
LIQUIDITY_TIERS = (
    ("ADTV_20 >= 25 cr", Decimal("250000000")),
    ("5 cr <= ADTV_20 < 25 cr", Decimal("50000000")),
    ("1 cr <= ADTV_20 < 5 cr", Decimal("10000000")),
    ("ADTV_20 < 1 cr", Decimal("0")),
)
ADTV_LOOKBACK = 20


def _digest(path: Path) -> str:
    # §102.3 Ruling 1: delegates to the guarded normaliser, which refuses a binary path.
    return text_digest(path) if path.is_file() else "ABSENT"


def _period_of(day: datetime.date) -> str:
    for label, start, end in PERIODS:
        if start <= day <= end:
            return label
    return "outside"


def _tier_of(median_value: Decimal) -> str:
    for label, floor in LIQUIDITY_TIERS:
        if median_value >= floor:
            return label
    return LIQUIDITY_TIERS[-1][0]


def _entry_liquidity(dataset, isin: str, entry: datetime.date) -> Decimal:
    """Median traded value over the 20 sessions before entry, from the committed corpus."""
    bars = dataset.prices_by_instrument.get(isin) or ()
    prior = [bar.traded_value for bar in bars if bar.trade_date < entry]
    window = prior[-ADTV_LOOKBACK:]
    if not window:
        return Decimal("0")
    ordered = sorted(Decimal(value) for value in window)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _drawdown_by_period(snapshots) -> dict:
    """Max drawdown inside each period, measured against the equity curve's running peak."""
    peak = None
    rows = {}
    for snapshot in snapshots:
        equity = snapshot.total_portfolio_value
        peak = equity if peak is None or equity > peak else peak
        drawdown = (peak - equity) / peak if peak > 0 else Decimal("0")
        label = _period_of(snapshot.as_of_date)
        row = rows.setdefault(
            label,
            {
                "sessions": 0,
                "first_session": snapshot.as_of_date.isoformat(),
                "last_session": snapshot.as_of_date.isoformat(),
                "start_equity": str(equity),
                "end_equity": str(equity),
                "max_drawdown": "0",
            },
        )
        row["sessions"] += 1
        row["last_session"] = snapshot.as_of_date.isoformat()
        row["end_equity"] = str(equity)
        if drawdown > Decimal(row["max_drawdown"]):
            row["max_drawdown"] = str(drawdown)
    return rows


def main() -> int:
    criteria = walkforward.load_go_no_go_criteria()
    corpus_path, corpus_problem = candidate_runner.locate_corporate_action_adjusted_corpus()
    if corpus_path is None:
        print(f"OVERALL: NOT RUN — {corpus_problem}")
        return 1
    started = time.monotonic()
    dataset = walkforward.resolve_or_build_historical_dataset(snapshot_path=corpus_path)
    print(
        f"[INFO] Dataset {dataset.snapshot.content_fingerprint[:24]}… "
        f"({dataset.snapshot.session_count} sessions, {dataset.snapshot.instrument_count} instruments, "
        f"built in {time.monotonic() - started:.1f}s)"
    )
    registry_before = {name: _digest(REPO_ROOT / name) for name in REGISTRY_FILES}

    with tempfile.TemporaryDirectory(prefix="s98_seq10_diag_") as tmp:
        result, _registry_copy, seconds = candidate_runner._run(
            dataset,
            Path(tmp) / "run_a",
            candidate_runner.BASELINE_TRIAL_ID,
            candidate_runner.HYPOTHESIS,
            candidate_runner.RATIONALE,
            True,
        )
    print(f"[INFO] Replay finished in {seconds:.1f}s — this is seq 10's own configuration, not a new trial")

    registry_after = {name: _digest(REPO_ROOT / name) for name in REGISTRY_FILES}
    if registry_after != registry_before:
        print("OVERALL: REGISTRY MUTATED — a diagnostic may not write the registry of record")
        return 1

    published = json.loads((REPO_ROOT / RESTATED_ARTIFACTS[0]).read_text(encoding="utf-8"))
    replay = {
        "corpus_fingerprint": dataset.snapshot.content_fingerprint,
        "criteria_fingerprint": compute_criteria_fingerprint(criteria),
        "criteria_version": criteria.version,
        "sessions": len(result.executed_sessions),
        "first_session": min(result.executed_sessions).isoformat(),
        "last_session": max(result.executed_sessions).isoformat(),
        "hold_bound_forced_exits": result.hold_bound_forced_exits,
        "hold_bound_refusals": result.hold_bound_refusals,
        "demerger_forced_exits": result.demerger_forced_exits,
        "demerger_forced_refusals": result.demerger_forced_refusals,
        "max_drawdown": str(result.max_drawdown),
        "closed_trades": len(result.closed_trades),
        "final_equity": str(result.final_equity),
    }
    print(
        f"[INFO] Replay counters: hold_bound {result.hold_bound_forced_exits}/{result.hold_bound_refusals}, "
        f"demerger {result.demerger_forced_exits}/{result.demerger_forced_refusals}, "
        f"max_drawdown {result.max_drawdown:.6f}, closed trades {len(result.closed_trades)}"
    )
    if result.hold_bound_forced_exits != published.get("hold_bound_forced_exits") or (
        result.hold_bound_refusals != published.get("hold_bound_refusals")
    ):
        print(
            "OVERALL: NOT A REPLAY — the run does not reproduce the published hold-bound counters "
            f"({published.get('hold_bound_forced_exits')}/{published.get('hold_bound_refusals')})"
        )
        return 1

    trades_by_period: dict = {}
    trades_by_tier: dict = {}
    missing_liquidity = 0
    for trade in result.closed_trades:
        exit_day = trade["exit_date"]
        label = _period_of(exit_day)
        median_value = _entry_liquidity(dataset, trade["isin"], trade["entry_date"])
        if median_value == 0:
            missing_liquidity += 1
        tier = _tier_of(median_value)
        for table, key in ((trades_by_period, label), (trades_by_tier, tier)):
            row = table.setdefault(
                key,
                {
                    "closed_trades": 0,
                    "wins": 0,
                    "net_pnl": Decimal("0"),
                    "gross_pnl": Decimal("0"),
                    "costs": Decimal("0"),
                    "exit_reasons": {},
                },
            )
            row["closed_trades"] += 1
            row["wins"] += 1 if trade["net_pnl"] > Decimal("0") else 0
            row["net_pnl"] += trade["net_pnl"]
            row["gross_pnl"] += trade["gross_pnl"]
            row["costs"] += trade["total_costs"]
            row["exit_reasons"][trade["exit_reason"]] = row["exit_reasons"].get(trade["exit_reason"], 0) + 1

    def _render(table: dict) -> dict:
        return {
            key: {
                **{name: value for name, value in row.items() if name not in ("net_pnl", "gross_pnl", "costs")},
                "net_pnl": str(row["net_pnl"]),
                "gross_pnl": str(row["gross_pnl"]),
                "costs": str(row["costs"]),
            }
            for key, row in sorted(table.items())
        }

    refusals_by_period: dict = {}
    rejection_reasons: dict = {}
    for summary in result.session_summaries:
        label = _period_of(summary.next_session)
        row = refusals_by_period.setdefault(
            label,
            {
                "sessions": 0,
                "tickets_rejected": 0,
                "skipped_missing_band": 0,
                "locked_bar_refusals": 0,
                "tickets_no_trade": 0,
            },
        )
        row["sessions"] += 1
        row["tickets_rejected"] += summary.tickets_rejected
        row["skipped_missing_band"] += summary.skipped_missing_band
        row["locked_bar_refusals"] += summary.locked_bar_refusals
        row["tickets_no_trade"] += summary.tickets_no_trade
        for side, reasons in (summary.rejections_by_side_and_reason or {}).items():
            for reason, count in reasons.items():
                key = f"{side}:{reason}"
                rejection_reasons[key] = rejection_reasons.get(key, 0) + count

    decomposition = {
        "artifact_format": "signal-atlas-seq10-drawdown-decomposition-v1",
        "section": "§97.10 item 3",
        "read_only": True,
        "registry": {
            "paths": list(REGISTRY_FILES),
            "digest_before": registry_before,
            "digest_after": registry_after,
            "mutated": registry_after != registry_before,
        },
        "replay": replay,
        "published_comparison": {
            "hold_bound_forced_exits": published.get("hold_bound_forced_exits"),
            "hold_bound_refusals": published.get("hold_bound_refusals"),
            "artifact": RESTATED_ARTIFACTS[0],
        },
        "drawdown_by_period": _drawdown_by_period(result.portfolio.snapshots),
        "trades_by_period": _render(trades_by_period),
        "trades_by_liquidity_tier": _render(trades_by_tier),
        "refusals_by_period": refusals_by_period,
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "trades_without_prior_liquidity": missing_liquidity,
        "open_positions_at_end_count": result.open_positions_at_end_count,
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "not_audited": True,
    }
    restatement = {
        "artifact_format": "signal-atlas-demerger-restatement-v1",
        "section": "§97.10 item 4",
        "trial_id": candidate_runner.TRIAL_ID,
        "restates": list(RESTATED_ARTIFACTS),
        "restated": {
            "demerger_forced_exits": published.get("demerger_forced_exits"),
            "demerger_forced_refusals": published.get("demerger_forced_refusals"),
        },
        "measurement": {
            "demerger_forced_exits": result.demerger_forced_exits,
            "demerger_forced_refusals": result.demerger_forced_refusals,
        },
        "counter": (
            "count_forced_exit_outcomes(forced_reasons, held_isins, filled_isins, reason): exits and "
            "refusals over forced reasons whose ISIN the position book held before the session executed "
            "(scripts/run_phase3b2_walkforward.py, Audit §96.5 / §97.5)"
        ),
        "replay": replay,
        "read_only": True,
        "not_audited": True,
        "generated_at_utc": decomposition["generated_at_utc"],
    }

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    DECOMPOSITION_ARTIFACT.write_text(
        json.dumps(decomposition, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    RESTATEMENT_ARTIFACT.write_text(
        json.dumps(restatement, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    print("=" * 96)
    for label, _start, _end in PERIODS:
        drawdown = decomposition["drawdown_by_period"].get(label, {})
        trades = decomposition["trades_by_period"].get(label, {})
        refusals = refusals_by_period.get(label, {})
        print(
            f"[INFO] {label:18s} sessions {drawdown.get('sessions', 0):4d} | "
            f"maxDD {Decimal(drawdown.get('max_drawdown', '0')):.4%} | "
            f"trades {trades.get('closed_trades', 0):4d} net {trades.get('net_pnl', '0')} | "
            f"rejected {refusals.get('tickets_rejected', 0):5d} "
            f"no-band {refusals.get('skipped_missing_band', 0):4d}"
        )
    for label, _floor in LIQUIDITY_TIERS:
        trades = decomposition["trades_by_liquidity_tier"].get(label, {})
        print(
            f"[INFO] tier {label:26s} trades {trades.get('closed_trades', 0):4d} "
            f"net {trades.get('net_pnl', '0')} costs {trades.get('costs', '0')}"
        )
    print(
        f"[INFO] Wrote {DECOMPOSITION_ARTIFACT.relative_to(REPO_ROOT).as_posix()} and "
        f"{RESTATEMENT_ARTIFACT.relative_to(REPO_ROOT).as_posix()}"
    )
    print("OVERALL: MEASURED — a diagnostic; nothing registered, no verdict claimed, not audited")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
