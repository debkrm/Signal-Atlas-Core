#!/usr/bin/env python3
"""
SEQ 10 CANDIDATE CERTIFICATE — Audit §93.5 Ruling 3 / §93.7 item 1

The Ruling authorises one candidate trial on `2018-04-01..2023-12-31` and names four things a reader
must be able to check rather than trust:

- the registry row's `N`, `criteria_version`, window and manifest pin agree with the committed criteria
  (`N = 10`, `evaluation_count = 5`, pin re-sealed by measurement);
- a run whose evaluated set contains any session in `2025-01-01..2026-11-11` fails closed;
- the verdict artifact carries `hold_bound_forced_exits` and `hold_bound_refusals`;
- a report naming a `1.1.5` artifact (or any recorded trial artifact) as its baseline is refused.

This certificate is state-aware, because a certificate that passes on an absent run is the defect it is
meant to catch (§9.3):

- **seq 10 registered** — every clause above is asserted, and the two refusal arms are re-measured
  against a mutated copy so a check that cannot fail fails this certificate (§14.4).
- **seq 10 not registered** — the committed state is reported as `NOT CERTIFIED`, naming the measured
  precondition that blocks the run (today: no committed corpus covers the window with split/bonus
  adjusted prices), together with the registry invariants that must hold either way (`N`, `N_eval`, the
  manifest pin, and no sealed-era path in any row).

Exit status: 0 only when seq 10 is registered and every clause is established on the committed tree.

Usage:
    python scripts/probe_seq10_candidate.py
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
import scripts.run_seq10_candidate as candidate_runner  # noqa: E402
from signal_core.contracts.criteria import load_go_no_go_criteria  # noqa: E402

REGISTRY_PATH = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl"
REGISTRY_MANIFEST = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl.manifest"
TRIAL_ID = "TRIAL-PHASE3B2-EXPANDED-010"
VERDICT_ARTIFACT = (
    REPO_ROOT / "reports" / "verdicts" / "trial_010" / "phase3b2_swing_baseline_2022_2024_verdict.json"
)
COMPARISON_ARTIFACT = REPO_ROOT / "reports" / "verdicts" / "trial_010" / "seq10_baseline_comparison.json"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
WINDOW_LAST_SESSION = datetime.date(2023, 12, 29)
SEALED_START = datetime.date(2025, 1, 1)
REGISTERED_N = 10
UNREGISTERED_N = 9
EXPECTED_EVALUATION_COUNT = 5
SUPERSEDED_CRITERIA_VERSIONS = ("1.1.5",)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def baseline_problem(block) -> Optional[str]:
    """
    A comparator must be a current-tree run, never a recorded `1.1.5` artifact (§93.5, §93.4).

    Two independent shapes are refused: a path under `reports/verdicts/` (every recorded trial artifact
    lives there, `trial_009` included) and a stated criteria version the eight artifacts were produced
    under. Either alone is enough, so a block that fixes one field and not the other is still refused.
    """
    if not isinstance(block, dict):
        return "the comparison carries no baseline block, so it has no comparator to cite"
    path = str(block.get("path") or "")
    version = str(block.get("criteria_version") or "")
    if not path:
        return "the baseline block names no artifact path"
    if "reports/verdicts/" in path.replace("\\", "/"):
        return (
            f"the baseline is {path!r}, a recorded trial verdict artifact under reports/verdicts/; "
            f"§93.5 requires a current-tree run of this configuration, not trial_00* history"
        )
    if version in SUPERSEDED_CRITERIA_VERSIONS:
        return (
            f"the baseline states criteria {version}, the version the eight recorded artifacts were "
            f"produced under (§93.4); a 1.1.5 artifact is history, not a comparator"
        )
    if not str(block.get("sha256") or ""):
        return "the baseline block carries no digest, so its bytes cannot be the ones compared"
    return None


def artifact_window_problem(artifact, binding_start: datetime.date) -> Optional[str]:
    """The artifact must carry both hold-bound counters and must not evaluate a warm-up or sealed session."""
    if not isinstance(artifact, dict):
        return "the verdict artifact is not a JSON object"
    for key in ("hold_bound_forced_exits", "hold_bound_refusals"):
        value = artifact.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return f"the verdict artifact carries no integer `{key}` (found {value!r}); §93.5 requires both"
    start_raw, end_raw = artifact.get("evaluation_start_date"), artifact.get("evaluation_end_date")
    if not start_raw or not end_raw:
        return "the verdict artifact declares no evaluation window"
    start = datetime.date.fromisoformat(str(start_raw)[:10])
    end = datetime.date.fromisoformat(str(end_raw)[:10])
    if start < binding_start:
        return (
            f"the evaluated set opens {start}, before the criteria' binding start {binding_start}; "
            f"a warm-up session may not be gated (§10.8)"
        )
    if end >= SEALED_START:
        return (
            f"the evaluated set ends {end}, inside the sealed holdout era [{SEALED_START}..2026-11-11]; "
            f"a run whose evaluated set touches it must fail closed (§8.1)"
        )
    if start != WINDOW_START or end < WINDOW_LAST_SESSION or end > WINDOW_END:
        return (
            f"the evaluated set is {start}..{end}, not the authorised window "
            f"{WINDOW_START}..{WINDOW_END} (§93.5 Ruling 3)"
        )
    return None


def registry_row_problem(row: dict, criteria) -> Optional[str]:
    """The row must name the criteria, window and partition the Ruling authorises, and no sealed path."""
    if row.get("trial_id") != TRIAL_ID:
        return f"the row is {row.get('trial_id')!r}, not {TRIAL_ID}"
    if row.get("partition") != "IN_SAMPLE":
        return f"the row's partition is {row.get('partition')!r}, expected IN_SAMPLE (2024 stays frozen)"
    if row.get("criteria_version") != criteria.version:
        return (
            f"the row names criteria {row.get('criteria_version')!r} but the committed criteria are "
            f"{criteria.version!r}; a row and its criteria must agree (§93.5)"
        )
    for name in ("fold_spec_fingerprint", "dataset_fingerprint"):
        if not str(row.get(name) or "").strip():
            return f"the row carries no {name}"
    provenance = json.dumps(row)
    for sealed in ("data/raw/2025", "data/raw/2026", "2025-01-01"):
        if sealed in provenance:
            return f"the row's provenance names {sealed!r}, inside the sealed holdout era"
    return None


def _expected_fold_fingerprint() -> str:
    fold_is = walkforward.WalkForwardFold(
        fold_index=0,
        train_start=WINDOW_START,
        train_end=datetime.date(2022, 12, 30),
        test_start=datetime.date(2023, 1, 2),
        test_end=WINDOW_END,
        embargo_sessions=0,
        partition_role=walkforward.PartitionRole.IN_SAMPLE,
    )
    return walkforward.compute_fold_spec_fingerprint((fold_is,))


def _registry_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    criteria = load_go_no_go_criteria()
    problems: list[str] = []
    not_registered_reason = ""

    print("=" * 96)
    print("SEQ 10 CANDIDATE CERTIFICATE — Audit §93.5 Ruling 3 / §93.7 item 1")
    print("=" * 96)

    registry = walkforward.TrialRegistry(REGISTRY_PATH)
    rows = _registry_rows()
    seq10_rows = [row for row in rows if row.get("trial_id") == TRIAL_ID]
    registered = len(seq10_rows) == 1

    expected_n = REGISTERED_N if registered else UNREGISTERED_N
    print(
        f"[INFO] Registry: N = {registry.total_trial_count} (expected {expected_n}), "
        f"N_eval = {registry.evaluated_trial_count}, seq 10 rows = {len(seq10_rows)}"
    )
    if registry.total_trial_count != expected_n:
        problems.append(f"the registry holds N = {registry.total_trial_count}, expected {expected_n}")
    if registry.evaluated_trial_count != EXPECTED_EVALUATION_COUNT:
        problems.append(
            f"the registry holds evaluation_count = {registry.evaluated_trial_count}, expected "
            f"{EXPECTED_EVALUATION_COUNT}; §93.5 does not move it"
        )
    if len(seq10_rows) > 1:
        problems.append(f"{len(seq10_rows)} rows carry {TRIAL_ID}; a trial may be registered once")

    manifest_digest = _digest(REGISTRY_MANIFEST)
    print(
        f"[INFO] Registry manifest {manifest_digest[:16]}… vs criteria pin "
        f"{criteria.expected_trial_registry_manifest_sha256[:16]}…"
    )
    if manifest_digest != criteria.expected_trial_registry_manifest_sha256:
        problems.append(
            f"the registry manifest digest {manifest_digest} is not the criteria pin "
            f"{criteria.expected_trial_registry_manifest_sha256}; the registry is not re-sealed"
        )

    # Either state: no registry row may name the sealed era.
    for row in rows:
        provenance = json.dumps(row)
        for sealed in ("data/raw/2025", "data/raw/2026", "2025-01-01"):
            if sealed in provenance:
                problems.append(
                    f"registry seq {row.get('seq')} names {sealed!r} in its provenance, inside the "
                    f"sealed holdout era"
                )

    if not registered:
        corpus_path, corpus_problem = candidate_runner.locate_corporate_action_adjusted_corpus()
        not_registered_reason = corpus_problem or "the registry holds no seq 10 row"
        print(f"[INFO] Corpus check: {'available at ' + str(corpus_path) if corpus_path else 'ABSENT'}")
        print(f"[INFO] Blocker: {not_registered_reason}")

    if registered:
        row = seq10_rows[0]
        print(
            f"[INFO] seq {row.get('seq')}: {TRIAL_ID}, criteria {row.get('criteria_version')}, "
            f"partition {row.get('partition')}"
        )
        row_problem = registry_row_problem(row, criteria)
        if row_problem:
            problems.append(row_problem)
        expected_fold = _expected_fold_fingerprint()
        if row.get("fold_spec_fingerprint") != expected_fold:
            problems.append(
                f"the row's fold specification {row.get('fold_spec_fingerprint')!r} is not the one the "
                f"window {WINDOW_START}..{WINDOW_END} implies ({expected_fold!r}); the row names a window "
                f"its run did not describe"
            )
        else:
            print(f"[INFO] Fold specification {expected_fold[:24]}… reproduces the row")

        if not VERDICT_ARTIFACT.is_file():
            problems.append(f"no verdict artifact at {VERDICT_ARTIFACT.relative_to(REPO_ROOT).as_posix()}")
            artifact = None
        else:
            artifact = json.loads(VERDICT_ARTIFACT.read_text(encoding="utf-8"))
            artifact_problem = artifact_window_problem(artifact, criteria.min_binding_evaluation_start_date)
            if artifact_problem:
                problems.append(artifact_problem)
            print(
                f"[INFO] Artifact: window {artifact.get('evaluation_start_date')}..{artifact.get('evaluation_end_date')}, "
                f"forced exits {artifact.get('hold_bound_forced_exits')}, refusals {artifact.get('hold_bound_refusals')}"
            )
            sealed_copy = dict(artifact)
            sealed_copy["evaluation_end_date"] = "2025-06-30"
            if artifact_window_problem(sealed_copy, criteria.min_binding_evaluation_start_date) is None:
                problems.append(
                    "an artifact whose evaluated set ends 2025-06-30 is accepted by the window check, so the "
                    "sealed-era refusal does not fail closed"
                )

        if not COMPARISON_ARTIFACT.is_file():
            problems.append(f"no comparison artifact at {COMPARISON_ARTIFACT.relative_to(REPO_ROOT).as_posix()}")
        else:
            comparison = json.loads(COMPARISON_ARTIFACT.read_text(encoding="utf-8"))
            baseline = comparison.get("baseline")
            baseline_problem_text = baseline_problem(baseline)
            if baseline_problem_text:
                problems.append(baseline_problem_text)
            else:
                baseline_path = REPO_ROOT / str(baseline["path"])
                if not baseline_path.is_file():
                    problems.append(f"the baseline artifact {baseline['path']!r} is not on disk")
                elif _digest(baseline_path) != baseline.get("sha256"):
                    problems.append(
                        f"the baseline at {baseline['path']!r} hashes to {_digest(baseline_path)[:16]}…, not "
                        f"the digest the comparison records"
                    )
                else:
                    print(
                        f"[INFO] Baseline: {baseline['path']} ({baseline['sha256'][:16]}…), "
                        f"criteria {baseline.get('criteria_version')}"
                    )
            if comparison.get("metric_agreement") and not all(comparison["metric_agreement"].values()):
                problems.append(f"the candidate does not reproduce the baseline: {comparison['metric_agreement']}")
            bound_disabled = comparison.get("bound_disabled_counterfactual") or {}
            if bound_disabled.get("hold_bound_forced_exits") != 0:
                problems.append(
                    "the bound-disabled counterfactual reports forced exits, so it does not isolate the consumer"
                )
            for label, mutant in (
                ("criteria 1.1.5", {**(baseline or {}), "criteria_version": "1.1.5"}),
                (
                    "trial_009",
                    {
                        **(baseline or {}),
                        "path": "reports/verdicts/trial_009/phase3b2_swing_baseline_2022_2024_verdict.json",
                    },
                ),
            ):
                if baseline_problem(mutant) is None:
                    problems.append(
                        f"a baseline block naming {label} is accepted, so the '1.1.5 artifact is not a "
                        f"comparator' clause does not fail closed (§93.5)"
                    )

    # The engine must refuse a window that touches the sealed era, before it reads a bar.
    try:
        walkforward.run_phase3b2_walkforward(
            trial_id=TRIAL_ID,
            in_sample_only=True,
            eval_start_date=datetime.date(2025, 1, 2),
            eval_end_date=datetime.date(2025, 3, 31),
            record_trial=False,
            write_verdict_files=False,
        )
    except walkforward.HoldoutSealedError as exc:
        print(f"[INFO] Sealed-era window refused by the engine: {str(exc)[:96]}…")
    except Exception as exc:  # noqa: BLE001 - any other refusal is not the one the Ruling names
        problems.append(
            f"a sealed-era window failed with {type(exc).__name__} ({str(exc)[:120]}), not HoldoutSealedError"
        )
    else:
        problems.append("a window inside 2025-01-01..2026-11-11 did not raise HoldoutSealedError")

    print("=" * 96)
    if not registered:
        print(f"[FAIL] seq 10 is not registered: {not_registered_reason}")
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems or not registered:
        print(
            f"OVERALL: NOT CERTIFIED — seq 10 is {'registered with ' + str(len(problems)) + ' problem(s)' if registered else 'NOT REGISTERED'}"
            f"; the registry is N = {registry.total_trial_count} / N_eval = {registry.evaluated_trial_count}"
        )
        print("=" * 96)
        return 1
    print(
        f"OVERALL: CERTIFIED — seq 10 registered at N = {REGISTERED_N} with evaluation_count "
        f"{EXPECTED_EVALUATION_COUNT}, row and pin agreeing with criteria {criteria.version}, artifact "
        f"carrying both hold-bound counters over {WINDOW_START}..{WINDOW_END}, baseline a current-tree "
        f"run, sealed-era run refused"
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
