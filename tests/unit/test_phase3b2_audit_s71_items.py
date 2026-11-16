"""
Unit tests for Phase 3B-2b Audit §71 Remediation Items (Commit 125f905 / §71).

Target Invariants:
- H-123: a missing, empty, unparseable, reversed or session-empty evaluation window makes
  CRIT-EXEC-03/04 NOT RUN instead of PASS on caller-supplied counts.
- H-122: erasing both evaluation ledger files, or truncating and re-anchoring them, is detected
  from the registry manifest witness; an artifact claiming a scored post-sidecar trial with no
  ledger row fails the reverse check.
- N-127: only a present, digest-verified `sec_list_YYYYMMDD.csv` row may move the band boundary;
  a malformed manifest raises rather than silently collapsing to the fallback date.
- CLI: --fast-indicator / --slow-indicator / --atr-stop-multiple reach canonical_params.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from signal_core.contracts.price_band import (
    PriceBandValidationError,
    SOURCED_PRICE_BAND_START,
    derive_sourced_price_band_start,
)
from signal_core.reporting.verdicts import VerdictStatus, evaluate_verdicts
from signal_core.research.trials import (
    RegistryTamperedError,
    TrialEvaluationError,
    TrialRegistry,
    verify_evaluation_artifact_agreement,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

_COUNTS = {
    "prohibit_buy_at_upper_circuit": True,
    "prohibit_sell_at_lower_circuit": True,
    "upper_circuit_buy_judged_fills": 2,
    "upper_circuit_buy_violating_fills": 0,
    "lower_circuit_sell_judged_fills": 2,
    "lower_circuit_sell_violating_fills": 0,
}


def _exec_statuses(bundle):
    report = evaluate_verdicts(bundle)
    exec3 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    return exec3, exec4


# --- H-123: an unwalkable window cannot be a compliant one -------------------------------


def test_h123_missing_window_keys_are_not_run():
    exec3, exec4 = _exec_statuses(dict(_COUNTS))
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "Finding H-123" in exec3.evidence
    assert "must both be supplied" in exec3.evidence


def test_h123_empty_window_strings_are_not_run():
    bundle = {**_COUNTS, "evaluation_start_date": "", "evaluation_end_date": ""}
    exec3, exec4 = _exec_statuses(bundle)
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "must both be supplied" in exec4.evidence


def test_h123_unparseable_window_is_not_run():
    bundle = {**_COUNTS, "evaluation_start_date": "2024-13-45", "evaluation_end_date": "soon"}
    exec3, exec4 = _exec_statuses(bundle)
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "not parseable" in exec3.evidence


def test_h123_reversed_window_is_not_run():
    bundle = {**_COUNTS, "evaluation_start_date": "2024-03-29", "evaluation_end_date": "2024-01-16"}
    exec3, exec4 = _exec_statuses(bundle)
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "reversed" in exec4.evidence


def test_h123_zero_session_window_is_not_run():
    # 2023-12-30..2023-12-31 is a Saturday/Sunday: no NSE sessions in range.
    bundle = {
        **_COUNTS,
        "evaluation_start_date": "2023-12-30",
        "evaluation_end_date": "2023-12-31",
    }
    exec3, exec4 = _exec_statuses(bundle)
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "0 calendar sessions" in exec3.evidence


def test_h123_unsourced_window_stays_not_run_and_sourced_window_passes():
    unsourced = {
        **_COUNTS,
        "evaluation_start_date": "2022-01-03",
        "evaluation_end_date": "2023-12-29",
    }
    exec3, exec4 = _exec_statuses(unsourced)
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN

    sourced = {
        **_COUNTS,
        "evaluation_start_date": "2024-01-16",
        "evaluation_end_date": "2024-03-31",
    }
    exec3, exec4 = _exec_statuses(sourced)
    assert exec3.status == VerdictStatus.PASS
    assert exec4.status == VerdictStatus.PASS
    assert exec3.evidence.startswith("0 of 2 judged BUY fill(s)")


# --- H-122: the registry manifest witnesses the evaluation head --------------------------


def _register(registry: TrialRegistry, trial_id: str, ts: str) -> None:
    registry.append_trial(
        trial_id=trial_id,
        hypothesis="H-122 test hypothesis",
        rationale="H-122 test rationale",
        partition="IN_SAMPLE",
        canonical_params={"strategy_id": "TEST", "atr_stop_multiple": "2.0"},
        fold_spec_fingerprint="FOLD-FPR-V1-test",
        dataset_fingerprint="DS-FPR-V1-test",
        criteria_version="1.1.1",
        timestamp_utc=ts,
    )


def _scored_registry(tmp_path: Path, count: int) -> TrialRegistry:
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    for i in range(count):
        _register(registry, f"TRIAL-S71-{i}", f"2026-11-16T09:0{i}:00+00:00")
    for i in range(count):
        registry.append_trial_evaluation(
            f"TRIAL-S71-{i}",
            Decimal(str(0.25 + i)),
            f"RET-V1-s71-{i}",
            100,
            f"2026-11-16T09:1{i}:00+00:00",
        )
    return registry


def test_h122_both_ledger_files_deleted_is_detected(tmp_path: Path):
    registry = _scored_registry(tmp_path, 1)
    registry.evaluation_path.unlink()
    registry.evaluation_manifest_path.unlink()

    with pytest.raises(RegistryTamperedError, match="dual-file erasure"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")
    with pytest.raises(RegistryTamperedError, match="dual-file erasure"):
        registry.verify_integrity()


def test_h122_truncate_and_reanchor_is_detected(tmp_path: Path):
    registry = _scored_registry(tmp_path, 2)
    sidecar = registry.evaluation_path
    kept = sidecar.read_bytes().splitlines(keepends=True)[:1]
    sidecar.write_bytes(b"".join(kept))

    payload = sidecar.read_bytes()
    head = json.loads(kept[0].decode("utf-8"))["eval_hash"]
    registry.evaluation_manifest_path.write_text(
        json.dumps(
            {
                "evaluation_count": 1,
                "head_eval_hash": head,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RegistryTamperedError, match="Registry manifest witnesses"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")
    with pytest.raises(RegistryTamperedError, match="Registry manifest witnesses"):
        registry.verify_integrity()


def test_h122_manifest_witness_matches_appended_head(tmp_path: Path):
    registry = _scored_registry(tmp_path, 1)
    manifest = json.loads((tmp_path / "trial_registry.jsonl.manifest").read_text(encoding="utf-8"))
    evaluation = registry.get_evaluation("TRIAL-S71-0")
    assert manifest["evaluation_count"] == 1
    assert manifest["head_eval_hash"] == evaluation.eval_hash
    assert manifest["total_trials"] == 1


def test_h122_reverse_direction_requires_a_ledger_row(tmp_path: Path):
    registry = _scored_registry(tmp_path, 5)
    art_dir = tmp_path / "verdicts"
    art_dir.mkdir()
    for i in range(5):
        (art_dir / f"trial_{i:03d}.json").write_text(
            json.dumps({"trial_id": f"TRIAL-S71-{i}", "annualized_sharpe": str(Decimal("0.25") + i)}),
            encoding="utf-8",
        )
    checked, _ = verify_evaluation_artifact_agreement(registry, art_dir)
    assert checked == 5

    # Erase the ledger row for the seq-5 trial and re-anchor consistently; the artifact direction
    # must still refuse, because the artifact attests a scored figure with no ledger row.
    registry.evaluation_path.write_bytes(
        b"".join(registry.evaluation_path.read_bytes().splitlines(keepends=True)[:4])
    )
    payload = registry.evaluation_path.read_bytes()
    head = json.loads(payload.decode("utf-8").splitlines()[-1])["eval_hash"]
    registry.evaluation_manifest_path.write_text(
        json.dumps(
            {
                "evaluation_count": 4,
                "head_eval_hash": head,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    manifest = json.loads((tmp_path / "trial_registry.jsonl.manifest").read_text(encoding="utf-8"))
    manifest["evaluation_count"] = 4
    manifest["head_eval_hash"] = head
    (tmp_path / "trial_registry.jsonl.manifest").write_text(json.dumps(manifest), encoding="utf-8")

    reloaded = TrialRegistry(tmp_path / "trial_registry.jsonl")
    assert reloaded.evaluated_trial_count == 4
    with pytest.raises(TrialEvaluationError, match="artifact->ledger direction"):
        verify_evaluation_artifact_agreement(reloaded, art_dir)


# --- N-127: the band boundary only moves for a verified artifact ------------------------


def _row(artifact: str, payload: bytes, **overrides):
    row = {
        "artifact": artifact,
        "is_current": True,
        "byte_count": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    row.update(overrides)
    return row


def test_n127_unverified_earlier_snapshot_is_ignored(tmp_path: Path):
    real = b"sec_list,2024-01-16\n"
    (tmp_path / "sec_list_20240116.csv").write_bytes(real)
    manifest = tmp_path / "manifest.jsonl"
    # The fabricated 2022 row names a file that does not exist; its digest fields are copied.
    manifest.write_text(
        json.dumps(_row("sec_list_20240116.csv", real))
        + "\n"
        + json.dumps(_row("sec_list_20220601.csv", real))
        + "\n",
        encoding="utf-8",
    )
    assert derive_sourced_price_band_start(manifest) == datetime.date(2024, 1, 16)


def test_n127_digest_mismatch_is_ignored(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    (tmp_path / "sec_list_20220601.csv").write_bytes(b"not the attested bytes")
    manifest.write_text(
        json.dumps(_row("sec_list_20220601.csv", b"attested bytes")) + "\n", encoding="utf-8"
    )
    assert derive_sourced_price_band_start(manifest) == datetime.date(2024, 1, 16)


def test_n127_malformed_manifest_raises(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(PriceBandValidationError, match="Malformed reference manifest line 1"):
        derive_sourced_price_band_start(manifest)


def test_n127_committed_manifest_derives_the_committed_boundary():
    assert derive_sourced_price_band_start(REPO_ROOT / "data" / "reference" / "manifest.jsonl") == (
        SOURCED_PRICE_BAND_START
    )


# --- CLI plumbing ----------------------------------------------------------------------


def test_cli_exposes_indicator_and_stop_flags():
    result = subprocess.run(
        [sys.executable, "scripts/run_phase3b2_walkforward.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for flag in ("--fast-indicator", "--slow-indicator", "--atr-stop-multiple"):
        assert flag in result.stdout


def test_cli_indicator_and_stop_values_reach_canonical_params(tmp_path: Path):
    from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot

    from scripts.run_phase3b2_walkforward import run_phase3b2_walkforward

    snap = make_synthetic_snapshot(tmp_path, num_sessions=40)
    res = run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        max_sessions=40,
        trial_id="TRIAL-S71-CLI",
        in_sample_only=True,
        fast_indicator="sma_20",
        slow_indicator="ema_200",
        atr_stop_multiple=Decimal("3.0"),
        write_verdict_files=False,
    )
    params = res.trial_record.canonical_params
    assert params["fast_indicator"] == "sma_20"
    assert params["slow_indicator"] == "ema_200"
    assert params["atr_stop_multiple"] == "3.0"
