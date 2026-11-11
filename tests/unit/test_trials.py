"""
Unit tests for append-only tamper-evident trial registry (Phase 2A).
"""

import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pytest

from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
)
from signal_core.research.trials import (
    DuplicateTrialError,
    GENESIS_PREV_HASH,
    RegistryTamperedError,
    TrialRecord,
    TrialRegistry,
    TrialRegistryError,
    _compute_record_hash,
)


VALID_TOKEN_HASH = "a" * 64


def test_trial_record_serialization_and_deserialization():
    """Verify trial record serialization to/from dictionary preserves all fields exactly."""
    record = TrialRecord(
        seq=1,
        prev_hash=GENESIS_PREV_HASH,
        record_hash="abc123hash",
        trial_id="EXP_001_MOM_EMA20",
        hypothesis="20-day EMA breakout captures sustained medium-term trends.",
        rationale="Wilder smoothing filters noise across liquid Nifty constituents.",
        partition="IN_SAMPLE",
        canonical_params={"ema_span": 20, "atr_filter": "1.5"},
        fold_spec_fingerprint="FOLD-SPEC-V1-123",
        dataset_fingerprint="DATA-CTNT-V2-456",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T20:00:00Z",
        returns_digest="DIGEST789",
        observation_count=250,
        mean_return=Decimal("0.00125"),
        std_return=Decimal("0.01500"),
        skewness=Decimal("-0.125"),
        kurtosis=Decimal("3.450"),
        sharpe_ratio=Decimal("1.325"),
        max_drawdown=Decimal("0.185"),
    )

    d = record.to_dict()
    reconstructed = TrialRecord.from_dict(d)

    assert reconstructed.seq == record.seq
    assert reconstructed.prev_hash == record.prev_hash
    assert reconstructed.record_hash == record.record_hash
    assert reconstructed.trial_id == record.trial_id
    assert reconstructed.hypothesis == record.hypothesis
    assert reconstructed.rationale == record.rationale
    assert reconstructed.partition == record.partition
    assert reconstructed.canonical_params == record.canonical_params
    assert reconstructed.mean_return == record.mean_return
    assert reconstructed.sharpe_ratio == record.sharpe_ratio
    assert reconstructed.max_drawdown == record.max_drawdown


def test_trial_record_rejects_non_finite_decimals():
    """Verify that non-finite Decimals (NaN, Infinity) are rejected fail-closed (A-13)."""
    with pytest.raises(TrialRegistryError, match="must be a finite Decimal"):
        TrialRecord(
            seq=1,
            prev_hash=GENESIS_PREV_HASH,
            record_hash="hash",
            trial_id="T1",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={},
            fold_spec_fingerprint="F",
            dataset_fingerprint="D",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            sharpe_ratio=Decimal("NaN"),
        )

    with pytest.raises(TrialRegistryError, match="must be a finite Decimal"):
        TrialRecord(
            seq=1,
            prev_hash=GENESIS_PREV_HASH,
            record_hash="hash",
            trial_id="T1",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={},
            fold_spec_fingerprint="F",
            dataset_fingerprint="D",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            sharpe_ratio=Decimal("Infinity"),
        )


def test_trial_registry_append_and_hash_chain(tmp_path: Path):
    """Verify sequential append, manifest anchor, and cryptographic hash chain verification."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    assert registry.trial_count == 0

    # 1. Append first trial (Genesis)
    t1 = registry.append_trial(
        trial_id="TRIAL_01",
        hypothesis="Hypothesis 1",
        rationale="Rationale 1",
        partition="IN_SAMPLE",
        canonical_params={"param_a": 10},
        fold_spec_fingerprint="FOLD_FP_1",
        dataset_fingerprint="DATA_FP_1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
        sharpe_ratio=Decimal("1.40"),
    )
    assert t1.seq == 1
    assert t1.prev_hash == GENESIS_PREV_HASH
    assert registry.manifest_path.is_file()

    # 2. Append second trial
    t2 = registry.append_trial(
        trial_id="TRIAL_02",
        hypothesis="Hypothesis 2",
        rationale="Rationale 2",
        partition="IN_SAMPLE",
        canonical_params={"param_a": 20},
        fold_spec_fingerprint="FOLD_FP_1",
        dataset_fingerprint="DATA_FP_1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:05:00Z",
        sharpe_ratio=Decimal("1.60"),
    )
    assert t2.seq == 2
    assert t2.prev_hash == t1.record_hash

    # 3. Reload from disk and verify chain integrity
    reloaded = TrialRegistry(registry_file)
    assert reloaded.trial_count == 2
    assert reloaded.verify_integrity() is True


def test_trial_registry_duplicate_trial_id_rejection(tmp_path: Path):
    """Verify duplicate trial_id is rejected fail-closed."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    registry.append_trial(
        trial_id="TRIAL_UNIQUE",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"x": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )

    with pytest.raises(DuplicateTrialError, match="Duplicate entry rejected: trial_id 'TRIAL_UNIQUE'"):
        registry.append_trial(
            trial_id="TRIAL_UNIQUE",
            hypothesis="H2",
            rationale="R2",
            partition="IN_SAMPLE",
            canonical_params={"x": 2},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:05:00Z",
        )


def test_trial_registry_detects_tampering_fail_closed(tmp_path: Path):
    """Verify that any tampering with trial records, order, or hashes raises fail-closed errors."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    for i in range(1, 4):
        registry.append_trial(
            trial_id=f"TRIAL_{i:02d}",
            hypothesis=f"H{i}",
            rationale=f"R{i}",
            partition="IN_SAMPLE",
            canonical_params={"p": i},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc=f"2026-11-11T10:0{i}:00Z",
        )

    # 1. Tamper with record content in line 2
    manifest_bytes = registry.manifest_path.read_bytes()
    lines = registry_file.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["hypothesis"] = "TAMPERED_HYPOTHESIS"
    lines[1] = json.dumps(data)
    tampered_file = tmp_path / "tampered_registry.jsonl"
    tampered_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (tmp_path / "tampered_registry.jsonl.manifest").write_bytes(manifest_bytes)

    with pytest.raises(RegistryTamperedError, match="Tampered record hash"):
        TrialRegistry(tampered_file)

    # 2. Tamper with sequence order (swap lines 2 and 3)
    lines_swapped = [lines[0], lines[2], lines[1]]
    swapped_file = tmp_path / "swapped_registry.jsonl"
    swapped_file.write_text("\n".join(lines_swapped) + "\n", encoding="utf-8", newline="\n")
    (tmp_path / "swapped_registry.jsonl.manifest").write_bytes(manifest_bytes)

    with pytest.raises(DuplicateTrialError, match="Out-of-order sequence"):
        TrialRegistry(swapped_file)

    # 3. Tamper with prev_hash
    data_broken_prev = json.loads(lines[1])
    data_broken_prev["prev_hash"] = "0" * 64
    data_broken_prev["record_hash"] = _compute_record_hash(data_broken_prev)
    broken_chain_lines = [lines[0], json.dumps(data_broken_prev), lines[2]]
    broken_chain_file = tmp_path / "broken_chain_registry.jsonl"
    broken_chain_file.write_text("\n".join(broken_chain_lines) + "\n", encoding="utf-8", newline="\n")
    (tmp_path / "broken_chain_registry.jsonl.manifest").write_bytes(manifest_bytes)

    with pytest.raises(RegistryTamperedError, match="Broken hash chain"):
        TrialRegistry(broken_chain_file)


def test_trial_registry_truncation_detection_via_manifest(tmp_path: Path):
    """Verify that truncation is detected fail-closed via authoritative external head manifest (A-4)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    for i in range(1, 6):
        registry.append_trial(
            trial_id=f"TRIAL_{i:02d}",
            hypothesis=f"H{i}",
            rationale=f"R{i}",
            partition="IN_SAMPLE",
            canonical_params={"p": i},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc=f"2026-11-11T10:0{i}:00Z",
        )

    assert registry.trial_count == 5
    manifest_data = json.loads(registry.manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["total_trials"] == 5

    # Truncate JSONL file to 2 lines while leaving manifest pointing to 5 trials
    lines = registry_file.read_text(encoding="utf-8").splitlines()
    truncated_content = "\n".join(lines[:2]) + "\n"
    registry_file.write_text(truncated_content, encoding="utf-8", newline="\n")

    with pytest.raises(RegistryTamperedError, match="Registry truncation detected: registry has 2 records, but authoritative manifest specifies 5"):
        TrialRegistry(registry_file)


def test_trial_registry_single_authority_holdout_enforcement(tmp_path: Path):
    """Verify single authority holdout routing and rejection without valid sentinel (A-2, A-3)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    token = "LEGAL_CHIEF_QUANT_AUTHORIZATION_TOKEN"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    spec = PartitionSpec(
        dataset_fingerprint="D1",
        holdout_token_hash=token_hash,
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    # 1. Registering HOLDOUT without partition_spec raises HoldoutSealedError
    with pytest.raises(HoldoutSealedError, match="Registering a HOLDOUT trial requires providing an authoritative PartitionSpec"):
        registry.append_trial(
            trial_id="TRIAL_HO_NO_SPEC",
            hypothesis="H",
            rationale="R",
            partition="HOLDOUT",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
        )

    # 2. Registering with trailing space 'holdout ' (A-2) is caught and raises HoldoutSealedError
    with pytest.raises(HoldoutSealedError):
        registry.append_trial(
            trial_id="TRIAL_HO_SPACE",
            hypothesis="H",
            rationale="R",
            partition="holdout ",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
        )

    # 3. Registering with spec but no unlock file raises HoldoutSealedError
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        registry.append_trial(
            trial_id="TRIAL_HO_NO_UNLOCK",
            hypothesis="H",
            rationale="R",
            partition="HOLDOUT",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            partition_spec=spec,
        )

    # 4. Registering with invalid sentinel (e.g. 'banana') raises HoldoutSealedError
    bad_sentinel = tmp_path / "BAD_UNLOCK"
    bad_sentinel.write_text("banana\n", encoding="utf-8")
    with pytest.raises(HoldoutSealedError):
        registry.append_trial(
            trial_id="TRIAL_HO_BAD_UNLOCK",
            hypothesis="H",
            rationale="R",
            partition="HOLDOUT",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            partition_spec=spec,
            unlock_file_path=bad_sentinel,
        )

    # 5. Registering with valid matching sentinel succeeds
    good_sentinel = tmp_path / "GOOD_UNLOCK"
    good_sentinel.write_text(f"{token}\n", encoding="utf-8")
    rec = registry.append_trial(
        trial_id="TRIAL_HO_AUTHORIZED",
        hypothesis="H",
        rationale="R",
        partition="HOLDOUT",
        canonical_params={"p": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
        partition_spec=spec,
        unlock_file_path=good_sentinel,
    )
    assert rec.partition == "HOLDOUT"
    assert registry.trial_count == 1


def test_trial_registry_concurrent_appender_detection(tmp_path: Path):
    """Verify concurrent modification is detected before appending (A-7)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    reg1 = TrialRegistry(registry_file)
    reg2 = TrialRegistry(registry_file)

    # reg1 appends TRIAL_01
    reg1.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"x": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )

    # reg2 (which still has 0 in-memory records) attempts to append TRIAL_02
    with pytest.raises(RegistryTamperedError, match="Concurrent modification detected: on-disk record count"):
        reg2.append_trial(
            trial_id="TRIAL_02",
            hypothesis="H2",
            rationale="R2",
            partition="IN_SAMPLE",
            canonical_params={"x": 2},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:05:00Z",
        )


def test_trial_registry_missing_trailing_newline_detection(tmp_path: Path):
    """Verify missing trailing newline fails closed on load and before append (A-8)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    reg = TrialRegistry(registry_file)

    reg.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"x": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )

    # Strip trailing newline byte from disk
    content_no_nl = registry_file.read_bytes().rstrip(b"\r\n")
    registry_file.write_bytes(content_no_nl)

    # Load must fail closed
    with pytest.raises(RegistryTamperedError, match="missing trailing newline"):
        TrialRegistry(registry_file)


def test_trial_registry_shuffled_order_reproducibility(tmp_path: Path):
    """Verify canonical dictionary serialization produces identical record hashes regardless of key order."""
    p1 = {"a": 1, "b": 2, "c": 3}
    p2 = {"c": 3, "b": 2, "a": 1}

    base_dict1 = {"seq": 1, "prev_hash": GENESIS_PREV_HASH, "canonical_params": p1}
    base_dict2 = {"seq": 1, "prev_hash": GENESIS_PREV_HASH, "canonical_params": p2}

    h1 = _compute_record_hash(base_dict1)
    h2 = _compute_record_hash(base_dict2)
    assert h1 == h2


def test_trial_registry_variance_and_dsr_n_convention(tmp_path: Path):
    """Verify total_trial_count (N) vs evaluated_trial_count (N_eval) and exact Decimal sample variance (A-11)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    assert registry.compute_trial_sharpe_variance() == Decimal("0.00")
    assert registry.total_trial_count == 0
    assert registry.evaluated_trial_count == 0

    # Append 3 trials: 2 with Sharpe, 1 without
    registry.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"i": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:01:00Z",
        sharpe_ratio=Decimal("1.50"),
    )
    registry.append_trial(
        trial_id="TRIAL_02",
        hypothesis="H2",
        rationale="R2",
        partition="IN_SAMPLE",
        canonical_params={"i": 2},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:02:00Z",
        sharpe_ratio=None,  # Not evaluated
    )
    registry.append_trial(
        trial_id="TRIAL_03",
        hypothesis="H3",
        rationale="R3",
        partition="IN_SAMPLE",
        canonical_params={"i": 3},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:03:00Z",
        sharpe_ratio=Decimal("1.90"),
    )

    # Authoritative N for multiple-testing penalty is 3
    assert registry.total_trial_count == 3
    assert registry.trial_count == 3
    # Evaluated count is 2
    assert registry.evaluated_trial_count == 2

    # Sample variance across [1.50, 1.90]:
    # Mean = 1.70, (1.50 - 1.70)^2 = 0.04, (1.90 - 1.70)^2 = 0.04 -> sum = 0.08
    # Variance = 0.08 / (2 - 1) = 0.08
    assert registry.compute_trial_sharpe_variance() == Decimal("0.08")


def test_trial_registry_byte_identical_posix_lf(tmp_path: Path):
    """Verify registry writes strict POSIX LF and contains zero CRLF (A-12)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    registry.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"x": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )

    jsonl_bytes = registry_file.read_bytes()
    manifest_bytes = registry.manifest_path.read_bytes()

    assert b"\r\n" not in jsonl_bytes
    assert b"\n" in jsonl_bytes
    assert b"\r\n" not in manifest_bytes
    assert b"\n" in manifest_bytes


def test_trial_registry_malformed_json_raises_registry_tampered_error(tmp_path: Path):
    """Verify malformed JSON or missing required key raises RegistryTamperedError not KeyError (A-14)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    manifest_file = registry_file.with_name(registry_file.name + ".manifest")
    registry_file.write_text('{"seq": 1, "trial_id": "M"}\n', encoding="utf-8", newline="\n")
    manifest_file.write_text(json.dumps({
        "total_trials": 1,
        "head_hash": "0" * 64,
        "last_trial_id": "M",
        "timestamp_utc": "2026-11-11T10:00:00Z",
    }) + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(RegistryTamperedError, match="Malformed record structure"):
        TrialRegistry(registry_file)


def test_trial_registry_canonical_params_parity(tmp_path: Path):
    """Verify in-memory record and reloaded record agree on canonical params (A-15)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    rec = registry.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H1",
        rationale="R1",
        partition="IN_SAMPLE",
        canonical_params={"threshold": Decimal("0.010")},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )

    assert rec.canonical_params == {"threshold": "0.010"}

    reloaded = TrialRegistry(registry_file)
    reloaded_rec = reloaded.get_trials()[0]
    assert reloaded_rec.canonical_params == rec.canonical_params


def test_trial_registry_timestamp_validation_and_monotonicity(tmp_path: Path):
    """Verify ISO-8601 UTC parse and chronological monotonicity enforcement (A-18)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    # 1. Invalid ISO-8601 timestamp string
    with pytest.raises(TrialRegistryError, match="not a valid ISO-8601 string"):
        registry.append_trial(
            trial_id="TRIAL_BAD_TS",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={"x": 1},
            fold_spec_fingerprint="F",
            dataset_fingerprint="D",
            criteria_version="1.1.0",
            timestamp_utc="not-a-timestamp",
        )

    # 2. Append first trial at 10:05
    registry.append_trial(
        trial_id="TRIAL_01",
        hypothesis="H",
        rationale="R",
        partition="IN_SAMPLE",
        canonical_params={"x": 1},
        fold_spec_fingerprint="F",
        dataset_fingerprint="D",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:05:00Z",
    )

    # 3. Non-monotonic timestamp (earlier than previous) rejected
    with pytest.raises(TrialRegistryError, match="Non-monotonic timestamp"):
        registry.append_trial(
            trial_id="TRIAL_02_EARLY",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={"x": 2},
            fold_spec_fingerprint="F",
            dataset_fingerprint="D",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
        )


def test_trial_registry_missing_manifest_rejected_fail_closed(tmp_path: Path):
    """Verify that a non-empty registry missing its manifest fails closed (B-1)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)
    registry.append_trial(
        trial_id="T_01",
        hypothesis="H",
        rationale="R",
        partition="IN_SAMPLE",
        canonical_params={"p": 1},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.0",
        timestamp_utc="2026-11-11T10:00:00Z",
    )
    assert registry.manifest_path.is_file()
    # Delete manifest
    registry.manifest_path.unlink()
    with pytest.raises(RegistryTamperedError, match="Missing authoritative manifest anchor"):
        TrialRegistry(registry_file)


def test_trial_registry_failed_integrity_preserves_in_memory_state(tmp_path: Path):
    """Verify that verify_integrity() does not mutate in-memory trial count on failure (B-2)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)
    for i in range(1, 5):
        registry.append_trial(
            trial_id=f"T_{i:02d}",
            hypothesis=f"H{i}",
            rationale=f"R{i}",
            partition="IN_SAMPLE",
            canonical_params={"p": i},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc=f"2026-11-11T10:0{i}:00Z",
        )
    assert registry.trial_count == 4

    # Tamper with record on disk at line 2
    lines = registry_file.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["hypothesis"] = "TAMPERED"
    lines[1] = json.dumps(data)
    registry_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    # verify_integrity raises RegistryTamperedError
    with pytest.raises(RegistryTamperedError, match="Tampered record hash"):
        registry.verify_integrity()

    # In-memory trial count MUST remain 4, NOT 1 (B-2)
    assert registry.trial_count == 4


def test_trial_record_and_registry_rejects_boolean_coercion(tmp_path: Path):
    """Verify observation_count=True and boolean string fields are rejected fail-closed (B-4)."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    # 1. append_trial with observation_count=True raises TrialRegistryError
    with pytest.raises(TrialRegistryError, match="observation_count must be a non-negative integer"):
        registry.append_trial(
            trial_id="T_BOOL_OBS",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            observation_count=True,  # type: ignore
        )

    # 2. append_trial with returns_digest as boolean or non-string
    with pytest.raises(TrialRegistryError, match="returns_digest must be a non-empty stripped string"):
        registry.append_trial(
            trial_id="T_BOOL_RD",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            returns_digest=True,  # type: ignore
        )

    # 3. from_dict with observation_count=True raises RegistryTamperedError
    with pytest.raises(RegistryTamperedError, match="Field 'observation_count' must be non-negative int"):
        TrialRecord.from_dict({
            "seq": 1,
            "prev_hash": GENESIS_PREV_HASH,
            "record_hash": "hash",
            "trial_id": "T1",
            "hypothesis": "H",
            "rationale": "R",
            "partition": "IN_SAMPLE",
            "canonical_params": {},
            "fold_spec_fingerprint": "F1",
            "dataset_fingerprint": "D1",
            "criteria_version": "1.1.0",
            "timestamp_utc": "2026-11-11T10:00:00Z",
            "observation_count": True,
        })
