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
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
import scripts.run_seq10_candidate as candidate_runner  # noqa: E402
from signal_core.contracts.criteria import (  # noqa: E402
    compute_criteria_fingerprint,
    load_go_no_go_criteria,
)

REGISTRY_PATH = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl"
REGISTRY_MANIFEST = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl.manifest"
TRIAL_ID = "TRIAL-PHASE3B2-EXPANDED-010"
VERDICT_ARTIFACT = (
    REPO_ROOT / "reports" / "verdicts" / "trial_010" / "phase3b2_swing_baseline_2022_2024_verdict.json"
)
COMPARISON_ARTIFACT = REPO_ROOT / "reports" / "verdicts" / "trial_010" / "seq10_baseline_comparison.json"
# Audit §97.10 items 3-4: the hash and the pair the committed artifacts publish are restated by append,
# never edited, and both restatements are read by this certificate (§10.1).
# Both restatements live outside `reports/verdicts/`, which the Phase 2A and pre-2022 gates read as the
# verdict corpus: a note is not a verdict artifact.
CRITERIA_RESTATEMENT = REPO_ROOT / "reports" / "analysis" / "s98" / "criteria_restatement.json"
DEMERGER_RESTATEMENT = REPO_ROOT / "reports" / "analysis" / "s98" / "seq10_demerger_restatement.json"
CERTIFICATES = (VERDICT_ARTIFACT, candidate_runner.BASELINE_ARTIFACT, COMPARISON_ARTIFACT)

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
# The authorised window is a date range, not a session list: 2018-04-01 and 2023-12-31 are both
# Sundays, so the first and last sessions the engine can evaluate are these two. Asserting `start ==
# WINDOW_START` would have refused every correct run of the expanded window.
WINDOW_FIRST_SESSION = datetime.date(2018, 4, 2)
WINDOW_LAST_SESSION = datetime.date(2023, 12, 29)
SEALED_START = datetime.date(2025, 1, 1)
# The literal below is the registry state this certificate certifies, and it is bumped in the same commit
# that registers a trial: a row appended without moving it fails the gate, which is the property the
# hardcoded value exists for (§8.2). seq 11 (TRIAL-PHASE3B2-LIQUIDITY-ATR-011) is the 11th row and its
# outcome is the 6th evaluation; seq 10's own row, artifacts and counters are unchanged by it.
REGISTERED_N = 11
UNREGISTERED_N = 9
EXPECTED_EVALUATION_COUNT = 6
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
    if start != WINDOW_FIRST_SESSION or end < WINDOW_LAST_SESSION or end > WINDOW_END:
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
    """The fold the authorised window implies, derived by the same function the engine runs (N-180)."""
    return walkforward.in_sample_fold_fingerprint(WINDOW_START, WINDOW_END)


def _relative(path: Path) -> str:
    try:
        return Path(path).relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def certificate_problem(certificate_path, live_fingerprint: str, criteria, restatement) -> Optional[str]:
    """
    A certificate's stored `criteria_fingerprint` must be the live one, or a pin-only restatement (§97.10 item 3).

    `criteria_version` cannot identify a criteria set: the expected manifest pin is inside
    `compute_criteria_fingerprint` (Audit §97.7). Two artifacts cited `1.1.16` under `9ee0a88c…` while the live
    criteria computed `b2876d98…` and no gate read a stored hash. A certificate that differs from the live
    fingerprint is accepted only when a restatement names its artifact, the executed fingerprint the
    certificate cites, and the manifest pin the run executed under — and substituting that pin into the
    **live** criteria reproduces the cited fingerprint exactly. That recomputation is the attestation: any
    other change to a criterion, threshold, fold, cost row or gating start would move the hash.
    """
    path = Path(certificate_path)
    relative = _relative(path)
    if not path.is_file():
        return f"no certificate at {relative}"
    stored = json.loads(path.read_text(encoding="utf-8")).get("criteria_fingerprint")
    if not isinstance(stored, str) or not stored.startswith("CRIT-FPR-V1-"):
        return f"{relative} carries no CRIT-FPR-V1 fingerprint (found {stored!r})"
    if stored == live_fingerprint:
        return None
    if not isinstance(restatement, dict):
        return (
            f"{relative} cites {stored} while the live criteria {criteria.version} compute {live_fingerprint}, "
            f"and no pin-only restatement attests the difference (§97.10 item 3)"
        )
    attested_live = restatement.get("live_criteria_fingerprint")
    if attested_live != live_fingerprint:
        return (
            f"the restatement attests live {attested_live} but the committed criteria {criteria.version} "
            f"compute {live_fingerprint}; the restatement is stale by name"
        )
    entries = [row for row in (restatement.get("certificates") or []) if row.get("artifact") == relative]
    if not entries:
        return f"the restatement names no executed fingerprint for {relative}"
    entry = entries[0]
    if entry.get("executed_criteria_fingerprint") != stored:
        return (
            f"the restatement records {entry.get('executed_criteria_fingerprint')} for {relative}, but the "
            f"certificate cites {stored}"
        )
    executed_pin = entry.get("executed_manifest_fingerprint")
    if not isinstance(executed_pin, str) or not executed_pin.startswith("MAN-FPR-V1-"):
        return f"the restatement records no executed MAN-FPR-V1 pin for {relative} (found {executed_pin!r})"
    recomputed = compute_criteria_fingerprint(
        dataclasses.replace(criteria, expected_manifest_fingerprint=executed_pin)
    )
    if recomputed != stored:
        return (
            f"substituting the restatement's pin {executed_pin} into the live criteria yields {recomputed}, "
            f"not the cited {stored}; the difference between {stored} and {live_fingerprint} is not pin-only"
        )
    return None


def demerger_restatement_problem(artifact, restatement) -> Optional[str]:
    """
    The published demerger pair must be the one the code computes, or an append must name the restatement.

    Audit §97.5 replaced the event counter with `count_forced_exit_outcomes`; the committed artifacts still
    publish `0` / `66` from the replaced one (N-194) and §10.1 makes the correction an append. The restatement
    must restate exactly the pair on disk, carry the held-position measurement that replaces it, and reproduce
    the run's other published counters so a reader cannot attach it to a different configuration.
    """
    pair = (artifact.get("demerger_forced_exits"), artifact.get("demerger_forced_refusals"))
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in pair):
        return f"the artifact carries no integer demerger pair (found {pair})"
    if not isinstance(restatement, dict):
        return f"the artifact publishes demerger_forced_exits/refusals {pair} with no restatement naming it"
    restated = restatement.get("restated") or {}
    if (restated.get("demerger_forced_exits"), restated.get("demerger_forced_refusals")) != pair:
        return (
            f"the restatement restates {restated.get('demerger_forced_exits')}/"
            f"{restated.get('demerger_forced_refusals')}, but the artifact publishes {pair[0]}/{pair[1]}"
        )
    measurement = restatement.get("measurement") or {}
    for key in ("demerger_forced_exits", "demerger_forced_refusals"):
        if not isinstance(measurement.get(key), int) or isinstance(measurement.get(key), bool):
            return f"the restatement carries no integer `{key}` measurement"
    replay = restatement.get("replay") or {}
    for key in ("hold_bound_forced_exits", "hold_bound_refusals"):
        if replay.get(key) != artifact.get(key):
            return (
                f"the restatement's replay records {key} {replay.get(key)}, but the artifact publishes "
                f"{artifact.get(key)}; the measurement is not this artifact's run"
            )
    # Audit §98.10 item 2: the measurement must be the run's own, so it is compared with the replay
    # block this function already trusts instead of being type-checked beside it. §98.5 measured a
    # restatement claiming `7/9` beside its own `0/0` replay passing this gate; only probe N-194 caught
    # it. A replay that omits the pair is refused too: an absent comparison is not an agreement.
    for key in ("demerger_forced_exits", "demerger_forced_refusals"):
        if not isinstance(replay.get(key), int) or isinstance(replay.get(key), bool):
            return (
                f"the restatement's replay carries no integer `{key}`, so its measurement "
                f"{measurement[key]} cannot be compared with the run that produced it"
            )
        if replay[key] != measurement[key]:
            return (
                f"the restatement measures {key} {measurement[key]}, but its own replay returns "
                f"{replay[key]}; the measurement is not this replay's (§98.10 item 2)"
            )
    return None


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
        cost_problem = candidate_runner.statutory_cost_schedule_problem(criteria)
        not_registered_reason = (
            "; ".join(problem for problem in (corpus_problem, cost_problem) if problem)
            or "the registry holds no seq 10 row"
        )
        print(f"[INFO] Corpus check: {'available at ' + str(corpus_path) if corpus_path else 'ABSENT'}")
        print(f"[INFO] Statutory cost check: {'prices every session in the window' if not cost_problem else cost_problem}")
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

        # Audit §97.10 items 3-4: a stored fingerprint and a published demerger pair are gates, not prose.
        live_fingerprint = compute_criteria_fingerprint(criteria)
        restatement = (
            json.loads(CRITERIA_RESTATEMENT.read_text(encoding="utf-8"))
            if CRITERIA_RESTATEMENT.is_file()
            else None
        )
        for certificate in CERTIFICATES:
            certificate_text = certificate_problem(certificate, live_fingerprint, criteria, restatement)
            if certificate_text:
                problems.append(certificate_text)
            else:
                print(f"[INFO] Certificate {_relative(certificate)} reconciles with {live_fingerprint[:24]}…")
        if restatement is not None and artifact is not None:
            stale = [
                certificate
                for certificate in CERTIFICATES
                if json.loads(certificate.read_text(encoding="utf-8")).get("criteria_fingerprint")
                != live_fingerprint
            ]
            for label, mutant in (
                ("a stale live hash", {**restatement, "live_criteria_fingerprint": "CRIT-FPR-V1-forged"}),
                (
                    "a forged executed fingerprint",
                    {
                        **restatement,
                        "certificates": [
                            {**row, "executed_criteria_fingerprint": "CRIT-FPR-V1-forged"}
                            for row in restatement.get("certificates") or []
                        ],
                    },
                ),
            ):
                if stale and certificate_problem(stale[0], live_fingerprint, criteria, mutant) is None:
                    problems.append(
                        f"a restatement carrying {label} is accepted, so the certificate gate does not fall "
                        f"closed (§97.10 item 3)"
                    )
            demerger_restatement = (
                json.loads(DEMERGER_RESTATEMENT.read_text(encoding="utf-8"))
                if DEMERGER_RESTATEMENT.is_file()
                else None
            )
            demerger_text = demerger_restatement_problem(artifact, demerger_restatement)
            if demerger_text:
                problems.append(demerger_text)
            else:
                print(
                    f"[INFO] Demerger pair {artifact.get('demerger_forced_exits')}/"
                    f"{artifact.get('demerger_forced_refusals')} restated by "
                    f"{_relative(DEMERGER_RESTATEMENT)}"
                )
                if (
                    demerger_restatement_problem(artifact, {**demerger_restatement, "measurement": {}})
                    is None
                ):
                    problems.append(
                        "a restatement with no measurement is accepted, so the demerger restatement check "
                        "does not fall closed (§97.10 item 4)"
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
