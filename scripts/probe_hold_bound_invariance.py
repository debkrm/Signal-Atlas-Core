#!/usr/bin/env python3
"""
HOLD-BOUND INVARIANCE — Audit §92.8 Ruling 2, probe

Re-runs one recorded post-2022 trial's in-sample window (`2022-01-03..2023-12-29`) through the single
authoritative engine (§7.4) with the hold-bound consumer in place, and measures what §92.10 item 2
requires before any seq-10 result is compared with the eight recorded trials:

- **Run A** — the committed engine and criteria 1.1.14, hold bound **21**: the run reports
  `hold_bound_forced_exits` and `hold_bound_refusals`, and its five fold metrics
  (`closed_trades`, `end_equity`, `profit_factor`, `win_rate`, `max_drawdown`) are compared with
  `reports/verdicts/trial_009/`'s committed artifact.
- **Run B** — the same engine, the same window, the same configuration, with the bound raised out of
  reach in the loaded criteria only (a counterfactual, never a verdict and never a registry of record):
  this is what the engine did before §92 had a consumer. Its five metrics are compared with the same
  committed artifact.

The pair separates the two questions §92.8 runs together:

- if **A** reproduces the committed artifact with **0** forced exits, the enforcement is inert on this
  window and the eight recorded outcomes are hold-bound invariant — the Ruling's condition is met;
- if **A** differs and **B** reproduces the committed artifact, the drift is the bound's and nothing
  else, measured as the A-minus-B difference;
- if **B** also differs, the engine has moved since seq 9's run for a reason the bound does not explain,
  and *that* is the alarm this probe exits non-zero on.

Nothing is written outside a temporary directory. Each run receives its row in a copy of
`data/trials/trial_registry.jsonl` and its sidecars, so `data/trials/` stays at N = 9 with
`evaluation_count` 5; the probe hashes the committed registry before and after and fails closed if a
byte moved. The verification rows are registered under their own ids rather than re-rendered against
seq 9's row because `security_master_fingerprint` moved when the interval table was restated (§91.2),
which N-130 correctly refuses to treat as a re-render.

Exit status: **0** when the condition the Ruling asks for is established (A reproduces the committed
artifact with zero forced exits), **1** when it is not — a non-zero forced-exit count is reported as a
comparability finding with its attribution, never smoothed into "the bound was unlikely to bind".

Usage:
    python scripts/probe_hold_bound_invariance.py
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
from signal_core.storage.artifact_digest import text_digest  # noqa: E402

REGISTRY_PATH = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl"
REGISTRY_SIDECARS = (".manifest", ".evaluations", ".evaluations.manifest")
COMMITTED_ARTIFACT = (
    REPO_ROOT / "reports" / "verdicts" / "trial_009" / "phase3b2_swing_baseline_2022_2024_verdict.json"
)
RECORDED_TRIAL_ID = "TRIAL-PHASE3B2-RANKED-009"
WINDOW_START = datetime.date(2022, 1, 3)
WINDOW_END = datetime.date(2023, 12, 29)
SEALED_START = datetime.date(2025, 1, 1)
METRICS = ("closed_trades", "end_equity", "profit_factor", "win_rate", "max_drawdown")
# A bound no 493-session fold can reach: run B measures the engine as it behaved before the consumer.
UNREACHABLE_BOUND = 10**6
VERIFICATION_PARAMS = dict(
    in_sample_only=True,
    atr_stop_multiple=Decimal("2.0"),
    entry_rank_indicator="mom_63",
    band_policy="LOCKED_BAR_REFUSAL_ONLY",
    max_position_weight_trim_threshold=None,
)


def _digest(path: Path) -> str:
    """The registry fingerprint's per-file digest, from `artifact_digest` (§102.3 Ruling 1)."""
    return text_digest(path)


def _registry_fingerprint() -> dict:
    paths = [REGISTRY_PATH, *[REGISTRY_PATH.with_name(REGISTRY_PATH.name + s) for s in REGISTRY_SIDECARS]]
    return {p.name: _digest(p) for p in paths}


def _run(workspace: Path, trial_id: str, rationale: str):
    """One engine run, its registry a private copy, its artifacts inside `workspace`."""
    workspace.mkdir(parents=True, exist_ok=True)
    registry_copy = workspace / REGISTRY_PATH.name
    shutil.copyfile(REGISTRY_PATH, registry_copy)
    for suffix in REGISTRY_SIDECARS:
        shutil.copyfile(REGISTRY_PATH.with_name(REGISTRY_PATH.name + suffix), workspace / (REGISTRY_PATH.name + suffix))
    started = time.monotonic()
    result = walkforward.run_phase3b2_walkforward(
        registry_path=registry_copy,
        verdict_output_dir=workspace / "verdicts",
        trial_id=trial_id,
        hypothesis=(
            "Audit §92.8 Ruling 2: seq 9's committed configuration re-run over its own in-sample window "
            "measures whether the max-hold consumer moved the eight recorded outcomes."
        ),
        rationale=rationale,
        **VERIFICATION_PARAMS,
    )
    return result, time.monotonic() - started


def _checked_sessions(result) -> list[datetime.date]:
    sessions = [
        s if isinstance(s, datetime.date) else datetime.date.fromisoformat(str(s))
        for s in result.executed_sessions
    ]
    assert sessions, "a run evaluated no session, so invariance is not measured"
    assert min(sessions) >= WINDOW_START and max(sessions) <= WINDOW_END, (
        f"the run evaluated {min(sessions)}..{max(sessions)}, outside the recorded in-sample window "
        f"{WINDOW_START}..{WINDOW_END}"
    )
    sealed = [s for s in sessions if s >= SEALED_START]
    assert not sealed, f"{len(sealed)} sealed holdout session(s) entered the evaluation set (first {sealed[0]})"
    return sessions


def _compare(label: str, measured: dict, committed: dict) -> list[str]:
    drifted = []
    for metric in METRICS:
        expected, actual = committed[metric], measured.get(metric)
        same = str(actual) == str(expected)
        print(f"[{'PASS' if same else 'FAIL'}] {label} {metric}: {actual!r} vs committed {expected!r}")
        if not same:
            drifted.append(metric)
    return drifted


def main() -> int:
    committed = json.loads(COMMITTED_ARTIFACT.read_text(encoding="utf-8"))["in_sample_metrics"]
    registry_before = _registry_fingerprint()
    bound = walkforward.load_go_no_go_criteria().max_hold_trading_sessions

    print("=" * 96)
    print("HOLD-BOUND INVARIANCE — Audit §92.8 Ruling 2 / §92.10 item 2")
    print(f"Recorded trial under re-run: {RECORDED_TRIAL_ID}")
    print(f"Window: {WINDOW_START.isoformat()}..{WINDOW_END.isoformat()} (in-sample only; 2024 fold frozen)")
    print(f"Committed hold bound: {bound} authoritative session(s)")
    print("Registry: a temporary copy receives each row; data/trials/ is never written")
    print("=" * 96)

    with tempfile.TemporaryDirectory(prefix="s93_hold_bound_") as tmp:
        root = Path(tmp)
        run_a, seconds_a = _run(
            root / "run_a",
            "TRIAL-S93-HOLDBOUND-RERUN-009-A",
            "Verification run A (Audit §92.8): the committed engine with the hold-bound consumer live.",
        )
        sessions_a = _checked_sessions(run_a)
        print(
            f"[INFO] Run A: {len(sessions_a)} session(s) {min(sessions_a)}..{max(sessions_a)} in "
            f"{seconds_a:.1f}s; sandbox registry N={run_a.total_trial_count_n}"
        )
        print(
            f"[INFO] Run A counters: hold_bound_forced_exits={run_a.hold_bound_forced_exits}, "
            f"hold_bound_refusals={run_a.hold_bound_refusals}"
        )

        original_loader = walkforward.load_go_no_go_criteria
        try:
            walkforward.load_go_no_go_criteria = lambda: dataclasses.replace(
                original_loader(), max_hold_trading_sessions=UNREACHABLE_BOUND
            )
            run_b, seconds_b = _run(
                root / "run_b",
                "TRIAL-S93-HOLDBOUND-RERUN-009-B",
                "Counterfactual run B (Audit §92.8): identical configuration with the bound raised out of "
                "reach in the loaded criteria, to separate the consumer's effect from engine drift. "
                "Not a verdict and not a registered hypothesis.",
            )
        finally:
            walkforward.load_go_no_go_criteria = original_loader
        sessions_b = _checked_sessions(run_b)
        print(
            f"[INFO] Run B (bound disabled): {len(sessions_b)} session(s) {min(sessions_b)}..{max(sessions_b)} "
            f"in {seconds_b:.1f}s; counters forced={run_b.hold_bound_forced_exits}, "
            f"refusals={run_b.hold_bound_refusals}"
        )
        assert run_b.hold_bound_forced_exits == 0 and run_b.hold_bound_refusals == 0, (
            "the bound-disabled counterfactual still emitted held-bound exits, so it does not isolate the "
            "consumer and the A/B attribution below is invalid"
        )

    registry_after = _registry_fingerprint()
    assert registry_before == registry_after, (
        f"the committed trial registry moved during a verification run: {registry_before} -> "
        f"{registry_after} (AGENTS.md §8.2: data/trials/ is N = 9 / N_eval = 5 and this round may not append)"
    )

    metrics_a = run_a.in_sample_metrics or {}
    metrics_b = run_b.in_sample_metrics or {}
    drift_a = _compare("Run A", metrics_a, committed)
    drift_b = _compare("Run B (bound disabled)", metrics_b, committed)

    bound_delta = {metric: (metrics_b.get(metric), metrics_a.get(metric)) for metric in METRICS
                   if str(metrics_a.get(metric)) != str(metrics_b.get(metric))}
    if bound_delta:
        print("[INFO] A-vs-B difference (the bound's own effect):")
        for metric, (without, with_consumer) in bound_delta.items():
            print(f"       {metric}: {without!r} without the consumer -> {with_consumer!r} with it")

    print("=" * 96)
    if run_a.hold_bound_forced_exits == 0 and run_a.hold_bound_refusals == 0 and not drift_a:
        print(
            f"OVERALL: INVARIANT — {len(sessions_a)} session(s) re-run with 0 forced exits and 0 refusals; "
            f"{len(METRICS)}/{len(METRICS)} recorded metrics reproduced exactly; committed data/trials/ unchanged"
        )
        print("=" * 96)
        return 0

    print(
        f"OVERALL: NOT INVARIANT — the bound bound {run_a.hold_bound_forced_exits} time(s) and refused "
        f"{run_a.hold_bound_refusals} exit(s) inside {RECORDED_TRIAL_ID}'s in-sample window, and "
        f"{len(drift_a)}/{len(METRICS)} committed metric(s) did not reproduce ({', '.join(drift_a) or 'none'})."
    )
    if not drift_b:
        print(
            "         Attribution: run B reproduces all five committed metrics with the consumer disabled, "
            "so the drift is the hold bound's and no other engine change explains it. A seq-10 result is "
            f"not comparable with the eight recorded trials until that is settled (§92.8)."
        )
    else:
        print(
            f"         Attribution: run B, with the consumer disabled, also fails to reproduce {', '.join(drift_b)}; "
            f"the engine moved since seq 9's run for a reason the bound does not explain. That is the alarm."
        )
    print("=" * 96)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
