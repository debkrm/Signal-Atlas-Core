"""
Audit §69 remediation tests (Findings H-118, H-119, CA-3(a)/(c)).

- H-118: every current manifest row's byte_count/sha256 is recomputed against the artifact on
  disk, and a one-byte corpus edit with an unchanged manifest fails closed.
- H-119: a trial is pre-registered unscored (Rule 3.2), then its computed outcome is appended as a
  linked record; evaluated_trial_count rises without rewriting rows, and the DSR prints the true
  blocking input.
- CA-3(c): sessions before the only attested sec_list report are band-ineligible, so the circuit
  criteria are NOT RUN over them.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.price_band import (
    SOURCED_PRICE_BAND_START,
    derive_sourced_price_band_start,
    is_price_band_sourced,
)
from signal_core.reporting.verdicts import VerdictStatus, evaluate_verdicts
from signal_core.research.significance import evaluate_strategy_significance
from signal_core.research.trials import (
    RegistryTamperedError,
    TrialEvaluationError,
    TrialRegistry,
    verify_evaluation_artifact_agreement,
)
from signal_core.storage.reference_integrity import (
    ManifestIntegrityError,
    verify_manifest_artifacts,
)
from scripts.run_phase3b2_walkforward import describe_stats_not_run_reason


def _copy_reference_tree(tmp_path: Path) -> Path:
    dest = tmp_path / "reference"
    shutil.copytree(REPO_ROOT / "data" / "reference", dest)
    return dest


def test_h118_committed_manifest_matches_corpus():
    summary = verify_manifest_artifacts()
    assert summary["verified"] > 0
    assert summary["superseded"] > 0


def test_h118_one_byte_corpus_edit_fails_closed(tmp_path: Path):
    ref = _copy_reference_tree(tmp_path)
    roots = (ref, REPO_ROOT / "data" / "raw", REPO_ROOT)

    # The untampered copy verifies, so the failure below is the edit and not a missing file.
    verify_manifest_artifacts(manifest_path=ref / "manifest.jsonl", roots=roots)

    corpus = ref / "corporate_actions.jsonl"
    payload = bytearray(corpus.read_bytes())
    payload[100] ^= 0x01
    corpus.write_bytes(bytes(payload))

    with pytest.raises(ManifestIntegrityError, match="sha256|bytes"):
        verify_manifest_artifacts(manifest_path=ref / "manifest.jsonl", roots=roots)


def test_h118_missing_artifact_fails_closed(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        '{"artifact": "absent.jsonl", "is_current": true, "byte_count": 1, '
        '"sha256": "' + "0" * 64 + '"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ManifestIntegrityError, match="not found"):
        verify_manifest_artifacts(manifest_path=manifest, roots=(tmp_path,))


def _register(registry: TrialRegistry, trial_id: str, ts: str) -> None:
    registry.append_trial(
        trial_id=trial_id,
        hypothesis="CA-3 test hypothesis",
        rationale="§69 item 2 acceptance probe",
        partition="IN_SAMPLE",
        canonical_params={"variant": trial_id},
        fold_spec_fingerprint="FOLD-SPEC-V1-test",
        dataset_fingerprint="DATA-CTNT-V2-test",
        criteria_version=load_go_no_go_criteria().version,
        timestamp_utc=ts,
    )


def test_h119_append_only_scoring_increments_evaluated_count(tmp_path: Path):
    reg_path = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(reg_path)
    _register(registry, "TRIAL-S69-A", "2026-11-16T10:00:00+00:00")
    _register(registry, "TRIAL-S69-B", "2026-11-16T10:01:00+00:00")

    assert registry.total_trial_count == 2
    assert registry.evaluated_trial_count == 0

    rows_before = reg_path.read_bytes()
    registry.append_trial_evaluation(
        "TRIAL-S69-A", Decimal("0.50"), "RET-V1-a", 20, "2026-11-16T10:02:00+00:00",
        max_drawdown=Decimal("0.04"),
    )
    registry.append_trial_evaluation(
        "TRIAL-S69-B", Decimal("1.50"), "RET-V1-b", 20, "2026-11-16T10:03:00+00:00",
        max_drawdown=Decimal("0.06"),
    )

    # The pre-registered rows are bytes-identical: scoring never rewrites history.
    assert reg_path.read_bytes() == rows_before
    assert registry.evaluated_trial_count == 2
    assert registry.get_trial_sharpes() == (Decimal("0.50"), Decimal("1.50"))

    reloaded = TrialRegistry(reg_path)
    assert reloaded.evaluated_trial_count == 2
    assert reloaded.get_evaluation("TRIAL-S69-A").observation_count == 20

    with pytest.raises(TrialEvaluationError, match="append-only"):
        reloaded.append_trial_evaluation(
            "TRIAL-S69-A", Decimal("0.70"), "RET-V1-a", 20, "2026-11-16T10:04:00+00:00"
        )

    with pytest.raises(TrialEvaluationError, match="unregistered"):
        reloaded.append_trial_evaluation(
            "TRIAL-S69-MISSING", Decimal("0.70"), "RET-V1-c", 20, "2026-11-16T10:05:00+00:00"
        )


def _scored_registry(tmp_path: Path, count: int = 3) -> TrialRegistry:
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    for i in range(count):
        _register(registry, f"TRIAL-H121-{i}", f"2026-11-16T10:0{i}:00+00:00")
    for i in range(count):
        registry.append_trial_evaluation(
            f"TRIAL-H121-{i}",
            Decimal(str(0.5 + i)),
            f"RET-V1-h121-{i}",
            10,
            f"2026-11-16T10:1{i}:00+00:00",
        )
    return registry


def test_h121_suffix_truncation_is_detected(tmp_path: Path):
    registry = _scored_registry(tmp_path)
    sidecar = registry.evaluation_path
    lines = sidecar.read_bytes().splitlines(keepends=True)
    sidecar.write_bytes(b"".join(lines[:-1]))

    with pytest.raises(RegistryTamperedError, match="anchor"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")
    # The in-memory instance must also refuse rather than report True over a truncated ledger.
    with pytest.raises(RegistryTamperedError, match="anchor"):
        registry.verify_integrity()


def test_h121_whole_sidecar_deletion_is_detected(tmp_path: Path):
    registry = _scored_registry(tmp_path)
    registry.evaluation_path.unlink()

    with pytest.raises(RegistryTamperedError, match="whole-file deletion"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")


def test_h121_missing_anchor_fails_closed(tmp_path: Path):
    registry = _scored_registry(tmp_path)
    registry.evaluation_manifest_path.unlink()

    with pytest.raises(RegistryTamperedError, match="no external head anchor"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")


def test_h121_anchor_records_count_head_and_bytes(tmp_path: Path):
    import json as _json

    registry = _scored_registry(tmp_path)
    anchor = _json.loads(registry.evaluation_manifest_path.read_text(encoding="utf-8"))
    assert anchor["evaluation_count"] == 3
    assert anchor["head_eval_hash"] == registry.get_evaluation("TRIAL-H121-2").eval_hash
    assert anchor["byte_count"] == registry.evaluation_path.stat().st_size
    assert len(anchor["sha256"]) == 64


def test_n125_artifact_sharpe_must_match_sidecar(tmp_path: Path):
    import json as _json

    registry = _scored_registry(tmp_path, count=2)
    art_dir = tmp_path / "verdicts"
    art_dir.mkdir()
    for tid, sharpe in (("TRIAL-H121-0", "0.5"), ("TRIAL-H121-1", "1.5")):
        (art_dir / f"{tid}.json").write_text(
            _json.dumps({"trial_id": tid, "annualized_sharpe": sharpe}), encoding="utf-8"
        )
    checked, _ = verify_evaluation_artifact_agreement(registry, art_dir)
    assert checked == 2

    (art_dir / "TRIAL-H121-1.json").write_text(
        _json.dumps({"trial_id": "TRIAL-H121-1", "annualized_sharpe": "9.99"}), encoding="utf-8"
    )
    with pytest.raises(TrialEvaluationError, match="does not equal"):
        verify_evaluation_artifact_agreement(registry, art_dir)


def test_h119_scored_trials_make_dsr_computable(tmp_path: Path):
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    _register(registry, "TRIAL-S69-A", "2026-11-16T10:00:00+00:00")
    _register(registry, "TRIAL-S69-B", "2026-11-16T10:01:00+00:00")
    registry.append_trial_evaluation(
        "TRIAL-S69-A", Decimal("0.50"), "RET-V1-a", 20, "2026-11-16T10:02:00+00:00"
    )
    registry.append_trial_evaluation(
        "TRIAL-S69-B", Decimal("1.50"), "RET-V1-b", 20, "2026-11-16T10:03:00+00:00"
    )

    returns = [Decimal(v) for v in ("0.01", "-0.005", "0.004", "0.012", "-0.002", "0.006")]
    report = evaluate_strategy_significance(returns=returns, registry=registry, criteria=load_go_no_go_criteria())

    assert report.dsr_result is not None
    assert report.dsr_result.trial_count_n == 2
    assert report.dsr_result.evaluated_trial_count == 2


def test_h119_dsr_reason_names_the_blocking_input():
    reason = describe_stats_not_run_reason(0, Decimal("0.00"))
    assert "evaluated_trial_count=0" in reason
    assert "minimum 2" in reason
    assert "N=0" not in reason

    variance_reason = describe_stats_not_run_reason(2, Decimal("0.00"))
    assert "variance=0.00" in variance_reason
    assert "evaluated_trial_count" not in variance_reason


def test_ca3c_band_sourcing_boundary():
    assert SOURCED_PRICE_BAND_START == datetime.date(2024, 1, 16)
    assert not is_price_band_sourced(datetime.date(2024, 1, 15))
    assert is_price_band_sourced(datetime.date(2024, 1, 16))
    # N-126: the constant is derived from the manifest snapshot name, not hand-typed.
    manifest = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
    assert derive_sourced_price_band_start(manifest) == SOURCED_PRICE_BAND_START


_COUNTS = {
    "prohibit_buy_at_upper_circuit": True,
    "prohibit_sell_at_lower_circuit": True,
    "upper_circuit_buy_judged_fills": 2,
    "upper_circuit_buy_violating_fills": 0,
    "lower_circuit_sell_judged_fills": 2,
    "lower_circuit_sell_violating_fills": 0,
}


def test_h120_unsourced_window_forces_not_run_without_producer_note():
    """The engine, not the caller, decides band eligibility (Finding H-120)."""
    bundle = {
        **_COUNTS,
        "evaluation_start_date": "2022-01-03",
        "evaluation_end_date": "2023-12-29",
    }
    report = evaluate_verdicts(bundle)
    exec3 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "no sourced NSE price-band report" in exec3.evidence
    assert "no sourced NSE price-band report" in exec4.evidence
    assert "H-120" in exec3.evidence

    # A producer note is evidence, not the trigger: it cannot lift the window-derived refusal.
    with_note = evaluate_verdicts({**bundle, "circuit_band_coverage_note": "producer says fine"})
    assert next(
        e for e in with_note.evaluations if e.criterion_id == "CRIT-EXEC-03"
    ).status == VerdictStatus.NOT_RUN


def test_h120_sourced_window_passes_on_judged_fills():
    bundle = {
        **_COUNTS,
        "evaluation_start_date": "2024-01-16",
        "evaluation_end_date": "2024-03-29",
    }
    report = evaluate_verdicts(bundle)
    exec3 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    assert exec3.status == VerdictStatus.PASS
    assert exec4.status == VerdictStatus.PASS
    assert exec3.evidence.startswith("0 of 2 judged BUY fill(s)")
    assert exec4.evidence.startswith("0 of 2 judged SELL fill(s)")


def test_n121_zero_judged_fills_cannot_pass():
    bundle = {
        **_COUNTS,
        "evaluation_start_date": "2024-01-16",
        "evaluation_end_date": "2024-03-29",
        "upper_circuit_buy_judged_fills": 0,
        "lower_circuit_sell_judged_fills": 0,
    }
    report = evaluate_verdicts(bundle)
    exec3 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "0 BUY fills judged" in exec3.evidence
    assert "0 SELL fills judged" in exec4.evidence
