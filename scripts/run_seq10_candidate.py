#!/usr/bin/env python3
"""
CANDIDATE seq 10 — register and run on the expanded in-sample window (Audit §93.5 Ruling 3)

§93.4 measured that the eight recorded trials cannot be a comparator: the hold bound binds 175 times on
2022-2023 and 5/5 of `trial_009`'s metrics fail to reproduce even with the consumer disabled. §93.5
therefore authorises one candidate trial on `2018-04-01..2023-12-31` whose comparability baseline is a
**current-tree run of its own configuration over its own window**.

This script performs, in one process and one dataset:

1. **Baseline** (run A) — the committed engine and criteria, 2018-04-01..2023-12-31, hold bound live,
   recording into a *copy* of the trial registry so the registry of record stays at N = 9 until the
   candidate is registered. Its verdict artifact is copied to
   `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json`.
2. **Bound-disabled counterfactual** (run B) — the same configuration with
   `max_hold_trading_sessions` raised out of reach in the loaded criteria only, which is what the
   engine did before §92 had a consumer. Not a verdict, never registered.
3. **Candidate seq 10** — one registry row (N 9 → 10, `evaluation_count` still 5), then the run as a
   re-render of that row so no evaluation row is appended; verdict artifact in
   `reports/verdicts/trial_010/`.
4. **Comparison** — `reports/verdicts/trial_010/seq10_baseline_comparison.json` carries both books, the
   bound-disabled delta, and the baseline's own path and sha256, so no reader can substitute a `1.1.5`
   artifact for it.

**Precondition, measured and enforced (Audit §93.7 item 1, §94.6 item 1, §5.4).** The window needs a
corpus whose prices are split/bonus back-adjusted: 74 split/bonus ex-dates fall before 2022-01-03
alone, and an unadjusted series carries each of them as a price jump that SMA/ATR read as a move. The
committed dev snapshot covers 2022-01-03..2024-12-31, so it is refused by coverage. The corpus this
runner accepts is `data/reference/historical_dataset_2018_2023.json.gz`
(`scripts/derive_2018_2023_corpus.py`, Audit §94.6 item 1 Route B, rebuilt point-in-time under §95.10
item 3): every ISIN that traded, 2,735 over the window and 1,646 on the first session, 1,425 sessions,
`adjustment_version` stated, `corporate_actions_fingerprint` equal to the committed table's digest. The
check is still live rather than assumed — a corpus that covers 2022+ only, omits `adjustment_version`
or names another digest is refused by name, before anything is registered.

A second precondition is asserted by measurement rather than by a flag: since Audit §94.6 item 2 the
in-sample fold is derived from the requested window (`run_phase3b2_walkforward.derive_in_sample_fold`),
so the artifact states `in_sample_metrics['window']` as `2018-04-01 .. 2023-12-31`. The baseline run
still happens **before any registration**, and its artifact's declared window must equal the requested
one; a run that describes a window it did not evaluate is refused instead of registered (§9.1).

Nothing on 2025-01-01..2026-11-11 is read, evaluated or written: the window ends 2023-12-31.

Usage:
    python scripts/run_seq10_candidate.py
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
from signal_core.contracts.criteria import compute_criteria_fingerprint  # noqa: E402
from signal_core.storage.artifact_digest import text_digest  # noqa: E402

REGISTRY_PATH = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl"
REGISTRY_SIDECARS = (".manifest", ".evaluations", ".evaluations.manifest")
BASELINE_DIR = REPO_ROOT / "reports" / "analysis" / "s94"
BASELINE_ARTIFACT = BASELINE_DIR / "seq10_baseline_2018_2023_verdict.json"
VERDICT_DIR = REPO_ROOT / "reports" / "verdicts" / "trial_010"
VERDICT_ARTIFACT = VERDICT_DIR / "phase3b2_swing_baseline_2022_2024_verdict.json"
COMPARISON_ARTIFACT = VERDICT_DIR / "seq10_baseline_comparison.json"
ARTIFACT_NAME = "phase3b2_swing_baseline_2022_2024_verdict.json"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
WINDOW_LAST_SESSION = datetime.date(2023, 12, 29)
SEALED_START = datetime.date(2025, 1, 1)

TRIAL_ID = "TRIAL-PHASE3B2-EXPANDED-010"
BASELINE_TRIAL_ID = "TRIAL-S94-BASELINE-EXPANDED-001"
UNREACHABLE_BOUND = 10**6
METRICS = ("closed_trades", "end_equity", "profit_factor", "win_rate", "max_drawdown")

HYPOTHESIS = (
    "Delivery-swing SMA(20/50) trend-following with the pre-registered mom_63 entry rank earns a "
    "positive net expectancy per completed round trip on the point-in-time liquid NSE EQ universe over "
    "the expanded in-sample window 2018-04-01..2023-12-31, with the 21-session hold bound enforced "
    "where the hold is evaluated (Audit §93.5 Ruling 3)."
)
RATIONALE = (
    "seq 10, registered before execution under Audit §93.5 Ruling 3. Configuration is seq 9's committed "
    "one — sma_20/sma_50, k = 2.0, allocation 0.0800, trim None, LOCKED_BAR_REFUSAL_ONLY, mom_63, "
    "min_entry_notional 25000, min_fill_notional 5000 — with one fact the earlier eight did not have: "
    "the engine now consults criteria.max_hold_trading_sessions (21) through Portfolio.require_hold_bounds "
    "and routes the exit through the same harness (§92.2, §91.9 item 1). Trials 1-9 were run without an "
    "enforced hold bound (§93.4), so they are history and not this row's comparator; the comparator is a "
    "current-tree run of this configuration over this window, recorded in "
    "reports/verdicts/trial_010/seq10_baseline_comparison.json. The window opens at the criteria' binding "
    "start 2018-04-01 (criteria 1.1.15, §91.8) after the 931 warm-up captures were relabelled BINDING_EVALUATION "
    "(§92.7 Ruling 1). In-sample only: the 2024 validation fold is frozen and the holdout is not read."
)


# §102.3 Ruling 1: one guarded implementation, so this normaliser cannot be handed a binary path.
_digest = text_digest


def _snapshot_header(path: Path) -> dict:
    """The metadata a corpus declares, without materialising its price panels."""
    if path.suffix == ".gz":
        import gzip

        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def locate_corporate_action_adjusted_corpus() -> tuple:
    """
    Finds a committed corpus that covers the window with SPLIT_BONUS_ADJUSTED prices (§5.4, §10.3).

    Returns `(path, None)` when one exists, or `(None, reason)` where `reason` names every candidate and
    what it lacks, so the refusal states a measurement instead of an opinion.
    """
    ca_digest = _digest(REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl")
    considered: list[str] = []
    for path in sorted((REPO_ROOT / "data" / "reference").glob("historical*dataset*.json*")):
        if path.suffix not in (".json", ".gz"):
            continue
        try:
            header = _snapshot_header(path)
        except (OSError, ValueError) as exc:
            considered.append(f"{path.name}: unreadable ({exc})")
            continue
        start = str(header.get("start_date") or "")
        end = str(header.get("end_date") or "")
        covers = start <= WINDOW_START.isoformat() and end >= WINDOW_LAST_SESSION.isoformat()
        adjustment = str(header.get("adjustment_version") or "")
        ca_fp = str(header.get("corporate_actions_fingerprint") or "")
        considered.append(
            f"{path.name}: {start}..{end}, adjustment_version={adjustment or '<none>'}, "
            f"corporate_actions_fingerprint={ca_fp[:16] or '<none>'}…"
        )
        if not covers:
            continue
        if not adjustment:
            considered[-1] += " [no adjustment_version: the series is not attested as adjusted]"
            continue
        if ca_fp != ca_digest:
            considered[-1] += f" [corporate_actions_fingerprint is not the committed table {ca_digest[:16]}…]"
            continue
        return path, None
    if not considered:
        considered.append("no historical*dataset*.json* under data/reference/")
    return None, (
        f"no committed corpus covers {WINDOW_START}..{WINDOW_LAST_SESSION} with split/bonus-adjusted prices "
        f"derived from the committed corporate-action table; candidates: " + "; ".join(considered)
    )


CIRCULARS_ROOT = REPO_ROOT / "data" / "raw" / "circulars"


def committed_source_digests() -> dict:
    """`{source_ref: {sha256, ...}}` over the committed payloads under `data/raw/circulars/<ref>/`."""
    import hashlib

    index: dict = {}
    if not CIRCULARS_ROOT.is_dir():
        return index
    for directory in sorted(p for p in CIRCULARS_ROOT.iterdir() if p.is_dir()):
        digests = set()
        for payload in sorted(p for p in directory.iterdir() if p.name != "manifest.json"):
            digests.add(hashlib.sha256(payload.read_bytes()).hexdigest())
        if digests:
            index[directory.name] = digests
    return index


def statutory_source_problem(criteria, index: Optional[dict] = None) -> Optional[str]:
    """
    Every asserted rate must resolve to a committed byte (Audit §95.10 item 1, §10.7).

    Audit §95.8 measured that five exchange-fee rows cited `NSE/FA/*` references while
    `data/raw/circulars/` held no `NSE/FA/*` payload for any period, and that STT, stamp duty and the
    SEBI turnover charge were scalars with no date dimension at all. A row that names a rate but no
    committed byte is an unsourced numeric input (§6.5); this refuses one by name instead of charging
    from it.
    """
    index = committed_source_digests() if index is None else index
    costs = criteria.statutory_costs

    def _resolve(label: str, ref: str, digest: str) -> Optional[str]:
        available = index.get(ref)
        if not available:
            return (
                f"{label} cites {ref}, but data/raw/circulars/{ref}/ holds no committed payload; the "
                f"rate resolves to no byte (§6.5, §10.7)"
            )
        if digest not in available:
            return (
                f"{label} cites {ref} with sha256 {digest[:16]}…, which is not the digest of any "
                f"committed payload under data/raw/circulars/{ref}/ ({sorted(d[:16] + '…' for d in available)})"
            )
        return None

    for fee in costs.effective_dated_exchange_fees:
        problem = _resolve(
            f"exchange-fee row {fee.circular_ref!r} ({fee.from_date}..{fee.to_date})",
            fee.circular_ref.replace("NSE/FA/", "NSE_FA_"),
            fee.circular_sha256,
        )
        if problem:
            return problem
    for interval in costs.statutory_rate_intervals:
        problem = _resolve(
            f"{interval.component} interval from {interval.from_date}",
            interval.source_ref,
            interval.source_sha256,
        )
        if problem:
            return problem
    return None


def statutory_cost_schedule_problem(criteria) -> Optional[str]:
    """
    Every session in the window must be priced by a committed, byte-attested cost schedule (§7.2).

    Two separate refusals, in order. First the sources: each fee row and each statutory rate interval
    must carry a digest that resolves to a committed payload (`statutory_source_problem`), because a
    row asserting a rate no byte supports is an unsourced numeric input (§6.5). Second the coverage:
    the window's first session must be priced by a governing fee row and by every re-ratable levy, so
    an unpriced year is NOT RUN rather than silently flat.
    """
    from signal_core.contracts.criteria import CriteriaValidationError

    source_problem = statutory_source_problem(criteria)
    if source_problem:
        return source_problem

    first_session = walkforward.load_anchored_nse_trading_calendar().sessions_in_range(
        WINDOW_START, WINDOW_END
    )[0]
    try:
        criteria.statutory_costs.get_exchange_fee_for_date(first_session)
    except CriteriaValidationError as exc:
        earliest = min(
            fee.from_date for fee in criteria.statutory_costs.effective_dated_exchange_fees
        )
        return (
            f"the committed statutory cost schedule's earliest exchange-fee row starts {earliest}, so the "
            f"window's first session {first_session} has no governing NSE circular ({exc}). No sourced "
            f"pre-{earliest} turnover rate exists in this repository, so the window cannot be priced and "
            f"AGENTS.md §7.2 prohibits a flat or invented rate (§6.5, §9.1)"
        )
    for component in (
        "STT_DELIVERY",
        "STT_INTRADAY_SELL",
        "SEBI_TURNOVER",
        "STAMP_DUTY_DELIVERY_BUY",
        "STAMP_DUTY_INTRADAY_BUY",
    ):
        try:
            criteria.statutory_costs.get_rate(component, first_session)
        except CriteriaValidationError as exc:
            return f"the window's first session {first_session} is unpriced for {component}: {exc}"
    return None


def _copy_registry(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / REGISTRY_PATH.name
    shutil.copyfile(REGISTRY_PATH, target)
    for suffix in REGISTRY_SIDECARS:
        shutil.copyfile(REGISTRY_PATH.with_name(REGISTRY_PATH.name + suffix), workspace / (REGISTRY_PATH.name + suffix))
    return target


def _metrics(result) -> dict:
    return {metric: str((result.in_sample_metrics or {}).get(metric)) for metric in METRICS}


def _check_sessions(result, label: str) -> list[datetime.date]:
    sessions = [
        s if isinstance(s, datetime.date) else datetime.date.fromisoformat(str(s))
        for s in result.executed_sessions
    ]
    assert sessions, f"{label} evaluated no session"
    assert min(sessions) >= WINDOW_START, f"{label} evaluated {min(sessions)}, before the window start"
    assert max(sessions) <= WINDOW_END, f"{label} evaluated {max(sessions)}, after the window end"
    sealed = [s for s in sessions if s >= SEALED_START]
    assert not sealed, f"{label} evaluated a sealed session ({sealed[0]})"
    return sessions


def _run(dataset, workspace: Path, trial_id: str, hypothesis: str, rationale: str, record: bool):
    registry_path = _copy_registry(workspace) if record else REGISTRY_PATH
    started = time.monotonic()
    result = walkforward.run_phase3b2_walkforward(
        registry_path=registry_path,
        verdict_output_dir=workspace / "verdicts",
        dataset=dataset,
        trial_id=trial_id,
        hypothesis=hypothesis,
        rationale=rationale,
        in_sample_only=True,
        eval_start_date=WINDOW_START,
        eval_end_date=WINDOW_END,
        record_trial=record,
    )
    return result, registry_path, time.monotonic() - started


def seq10_fold_fingerprint() -> str:
    """The fold specification this candidate's window implies, derived by the engine (N-180)."""
    return walkforward.in_sample_fold_fingerprint(WINDOW_START, WINDOW_END)


def _register(registry_copy: Path, criteria, dataset_fingerprint: str) -> str:
    """Pre-register seq 10 with the parameters the engine actually receives (§8.2, N-180)."""
    rows = [
        json.loads(line)
        for line in registry_copy.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    template = rows[-1]
    registry = walkforward.TrialRegistry(REGISTRY_PATH)
    if any(record.trial_id == TRIAL_ID for record in registry.get_trials()):
        raise SystemExit(f"{TRIAL_ID} is already registered; seq 10 may not be appended twice")
    registered = registry.append_trial(
        trial_id=TRIAL_ID,
        hypothesis=HYPOTHESIS,
        rationale=RATIONALE,
        partition=template["partition"],
        canonical_params=template["canonical_params"],
        # Audit §94.6 item 2 / §94.4 N-180: the fold is the one this window implies, not seq 9's. A row
        # that copied the template's value was refused by its own certificate after N had moved to 10.
        fold_spec_fingerprint=seq10_fold_fingerprint(),
        dataset_fingerprint=dataset_fingerprint,
        criteria_version=criteria.version,
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        sharpe_ratio=None,
        partition_spec=walkforward.load_canonical_partition_spec(),
        execution_config=template["execution_config"],
    )
    return registered.record_hash


def main() -> int:
    criteria = walkforward.load_go_no_go_criteria()
    if criteria.min_binding_evaluation_start_date != WINDOW_START:
        raise SystemExit(
            f"the criteria' binding start is {criteria.min_binding_evaluation_start_date}, not "
            f"{WINDOW_START}; the window this candidate names would not be label-consistent"
        )

    print("=" * 96)
    print("CANDIDATE seq 10 — Audit §93.5 Ruling 3 / §93.7 item 1")
    print(f"Window: {WINDOW_START.isoformat()}..{WINDOW_END.isoformat()} (in-sample only; 2024 validation FROZEN)")
    print(f"Criteria: {criteria.version} | hold bound {criteria.max_hold_trading_sessions} authoritative session(s)")
    print("Registry: runs A and B record into copies; N = 9 until seq 10 is registered")
    print("=" * 96)

    corpus_path, corpus_problem = locate_corporate_action_adjusted_corpus()
    if corpus_path is None:
        print("=" * 96)
        print(f"OVERALL: NOT REGISTERED — {corpus_problem}")
        print(
            "         No row was appended and no verdict was computed: a run on unadjusted prices would "
            "publish a result the criteria' adjustment rule does not permit (AGENTS.md §5.4, §9.3)."
        )
        print("=" * 96)
        return 1
    print(f"[INFO] Corpus: {corpus_path.relative_to(REPO_ROOT).as_posix()}")

    cost_problem = statutory_cost_schedule_problem(criteria)
    if cost_problem:
        print("=" * 96)
        print(f"OVERALL: NOT REGISTERED — {cost_problem}")
        print(
            "         No row was appended and no verdict was computed: a trial whose first year cannot "
            "be priced would publish a result the statutory schedule does not support (§9.3)."
        )
        print("=" * 96)
        return 1

    started = time.monotonic()
    dataset = walkforward.resolve_or_build_historical_dataset(snapshot_path=corpus_path)
    print(
        f"[INFO] Dataset: {dataset.snapshot.session_count} session(s), "
        f"{dataset.snapshot.instrument_count} instrument(s), "
        f"{dataset.snapshot.total_instrument_records} bar(s), fingerprint "
        f"{dataset.snapshot.content_fingerprint} (built in {time.monotonic() - started:.1f}s)"
    )

    with tempfile.TemporaryDirectory(prefix="s94_seq10_") as tmp:
        root = Path(tmp)

        run_a, copy_a, seconds_a = _run(
            dataset, root / "run_a", BASELINE_TRIAL_ID,
            "Audit §93.5 Ruling 3 baseline: the committed engine over the expanded in-sample window, "
            "hold bound live.",
            "Current-tree comparator for candidate seq 10. Not a registered hypothesis; recorded into a "
            "copy of the registry so the registry of record stays at N = 9.",
            record=True,
        )
        sessions_a = _check_sessions(run_a, "run A (baseline)")
        described_window = str((run_a.in_sample_metrics or {}).get("window"))
        expected_window = f"{WINDOW_START} .. {WINDOW_END}"
        if described_window != expected_window:
            print(
                f"OVERALL: NOT REGISTERED — the baseline traversed {min(sessions_a)}..{max(sessions_a)} "
                f"but describes its in-sample window as {described_window!r}, not {expected_window!r}; "
                f"a row naming the expanded window over an artifact that names 2022-2023 would be a "
                f"window the run did not describe (§9.1). No row was appended."
            )
            print("=" * 96)
            return 1
        print(
            f"[INFO] Run A (baseline): {len(sessions_a)} session(s) {min(sessions_a)}..{max(sessions_a)} "
            f"in {seconds_a:.1f}s; hold_bound_forced_exits={run_a.hold_bound_forced_exits}, "
            f"hold_bound_refusals={run_a.hold_bound_refusals}"
        )

        original_loader = walkforward.load_go_no_go_criteria
        try:
            walkforward.load_go_no_go_criteria = lambda: dataclasses.replace(
                original_loader(), max_hold_trading_sessions=UNREACHABLE_BOUND
            )
            run_b, _copy_b, seconds_b = _run(
                dataset, root / "run_b", "TRIAL-S94-BOUNDDISABLED-EXPANDED-001",
                "Audit §93.5 Ruling 3 counterfactual: identical configuration with the hold bound raised "
                "out of reach in the loaded criteria.",
                "Not a verdict and not a registered hypothesis; measures the delta the bound itself causes.",
                record=True,
            )
        finally:
            walkforward.load_go_no_go_criteria = original_loader
        sessions_b = _check_sessions(run_b, "run B (bound disabled)")
        assert run_b.hold_bound_forced_exits == 0 and run_b.hold_bound_refusals == 0, (
            "the bound-disabled counterfactual emitted hold-bound exits, so it does not isolate the consumer"
        )
        print(
            f"[INFO] Run B (bound disabled): {len(sessions_b)} session(s) in {seconds_b:.1f}s; "
            f"hold_bound_forced_exits=0, hold_bound_refusals=0"
        )

        # The baseline artifact is a reference, not a verdict: the candidate owns reports/verdicts/.
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "run_a" / "verdicts" / ARTIFACT_NAME, BASELINE_ARTIFACT)
        with open(BASELINE_ARTIFACT, encoding="utf-8") as handle:
            baseline = json.load(handle)
        print(f"[INFO] Baseline artifact: {BASELINE_ARTIFACT.relative_to(REPO_ROOT).as_posix()} sha256 {_digest(BASELINE_ARTIFACT)[:16]}…")

        # §93.5: the registry moves N 9 -> 10 with evaluation_count still 5, so the row is registered
        # and the run is its re-render — the evaluation ledger is not touched (§93.4 containment).
        evaluation_count_before = walkforward.TrialRegistry(REGISTRY_PATH).evaluated_trial_count
        total_before = walkforward.TrialRegistry(REGISTRY_PATH).total_trial_count
        record_hash = _register(copy_a, criteria, dataset.snapshot.content_fingerprint)
        registry_after_register = walkforward.TrialRegistry(REGISTRY_PATH)
        print(
            f"[INFO] Registered {TRIAL_ID}: N {total_before} -> {registry_after_register.total_trial_count}, "
            f"N_eval {evaluation_count_before} -> {registry_after_register.evaluated_trial_count} "
            f"(record hash {record_hash[:16]}…)"
        )
        assert registry_after_register.total_trial_count == 10, "seq 10 did not take the registry to N = 10"
        assert registry_after_register.evaluated_trial_count == evaluation_count_before == 5, (
            "registering seq 10 moved evaluation_count; §93.5 keeps it at 5"
        )

        VERDICT_DIR.mkdir(parents=True, exist_ok=True)
        run_c, _registry_c, seconds_c = _run(
            dataset, root / "run_c", TRIAL_ID, HYPOTHESIS, RATIONALE, record=False
        )
        sessions_c = _check_sessions(run_c, "seq 10")
        # The harness writes its artifact into its own workspace; `reports/verdicts/trial_010/` is the
        # citation target, so the bytes are copied while the temporary root still exists.
        shutil.copyfile(root / "run_c" / "verdicts" / ARTIFACT_NAME, VERDICT_ARTIFACT)
        print(
            f"[INFO] seq 10: {len(sessions_c)} session(s) {min(sessions_c)}..{max(sessions_c)} in "
            f"{seconds_c:.1f}s; hold_bound_forced_exits={run_c.hold_bound_forced_exits}, "
            f"hold_bound_refusals={run_c.hold_bound_refusals}"
        )

    with open(VERDICT_ARTIFACT, encoding="utf-8") as handle:
        candidate = json.load(handle)

    metrics_a, metrics_b, metrics_c = _metrics(run_a), _metrics(run_b), _metrics(run_c)
    agreement = {metric: metrics_a[metric] == metrics_c[metric] for metric in METRICS}
    bound_effect = {
        metric: [metrics_b[metric], metrics_c[metric]]
        for metric in METRICS
        if metrics_b[metric] != metrics_c[metric]
    }

    print("\n[COMPARE] candidate seq 10 against the current-tree baseline (never a 1.1.5 artifact):")
    for metric in METRICS:
        print(
            f"          {metric}: baseline {metrics_a[metric]} | seq 10 {metrics_c[metric]} | "
            f"bound disabled {metrics_b[metric]} | "
            f"{'agrees' if agreement[metric] else 'DIFFERS'}"
        )
    for metric, (without, with_consumer) in bound_effect.items():
        print(f"[INFO] Bound's own effect: {metric} {without} without the consumer -> {with_consumer} with it")

    comparison = {
        "audit_section": "§93.5 Ruling 3 / §93.7 item 1",
        "trial_id": TRIAL_ID,
        "window": f"{WINDOW_START.isoformat()}..{WINDOW_END.isoformat()}",
        "criteria_version": criteria.version,
        "criteria_fingerprint": compute_criteria_fingerprint(criteria),
        "hold_bound_trading_sessions": criteria.max_hold_trading_sessions,
        "hold_bound_active_rule": True,
        "evaluation_count": walkforward.TrialRegistry(REGISTRY_PATH).evaluated_trial_count,
        "total_trial_count_n": walkforward.TrialRegistry(REGISTRY_PATH).total_trial_count,
        "prior_trials_without_hold_bound": (
            "Trials 1-9 (seq 1..9) were run before the engine enforced max_hold_trading_sessions "
            "(Audit §92.2, §93.4). They are history; this run does not compare against them."
        ),
        "baseline": {
            "source": "current-tree run of this configuration over this window",
            "path": BASELINE_ARTIFACT.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(BASELINE_ARTIFACT),
            "trial_id": BASELINE_TRIAL_ID,
            "criteria_version": baseline.get("criteria_version"),
            "criteria_fingerprint": baseline.get("criteria_fingerprint"),
            "evaluation_start_date": baseline.get("evaluation_start_date"),
            "evaluation_end_date": baseline.get("evaluation_end_date"),
            "sessions": len(sessions_a),
            "hold_bound_forced_exits": baseline.get("hold_bound_forced_exits"),
            "hold_bound_refusals": baseline.get("hold_bound_refusals"),
            "metrics": metrics_a,
        },
        "candidate": {
            "path": VERDICT_ARTIFACT.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(VERDICT_ARTIFACT),
            "sessions": len(sessions_c),
            "hold_bound_forced_exits": candidate.get("hold_bound_forced_exits"),
            "hold_bound_refusals": candidate.get("hold_bound_refusals"),
            "metrics": metrics_c,
        },
        "bound_disabled_counterfactual": {
            "note": "Counterfactual only: the loaded criteria' max_hold_trading_sessions raised out of reach. Never a verdict.",
            "sessions": len(sessions_b),
            "hold_bound_forced_exits": run_b.hold_bound_forced_exits,
            "hold_bound_refusals": run_b.hold_bound_refusals,
            "metrics": metrics_b,
        },
        "metric_agreement": agreement,
        "bound_effect": bound_effect,
        "dataset_fingerprint": dataset.snapshot.content_fingerprint,
        "dataset_corpus": corpus_path.relative_to(REPO_ROOT).as_posix(),
        "sealed_sessions_evaluated": 0,
    }
    COMPARISON_ARTIFACT.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(f"\n[INFO] Comparison artifact: {COMPARISON_ARTIFACT.relative_to(REPO_ROOT).as_posix()}")

    print("=" * 96)
    drifted = [metric for metric, same in agreement.items() if not same]
    if drifted:
        print(
            f"OVERALL: NOT LIKE-FOR-LIKE — {len(drifted)}/{len(METRICS)} metric(s) differ between the "
            f"baseline and the candidate ({', '.join(drifted)}); the comparison above is not a comparator."
        )
        print("=" * 96)
        return 1
    print(
        f"OVERALL: REGISTERED AND RUN — seq 10 on {WINDOW_START}..{WINDOW_END}, N = 10 with "
        f"evaluation_count 5, {len(METRICS)}/{len(METRICS)} metrics reproduce the current-tree baseline, "
        f"hold bound active ({run_c.hold_bound_forced_exits} forced exit(s), {run_c.hold_bound_refusals} refusal(s))."
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
