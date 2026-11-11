"""
Unit tests for append-only tamper-evident trial registry (Phase 2A).
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest

from signal_core.research.trials import (
    DuplicateTrialError,
    GENESIS_PREV_HASH,
    RegistryTamperedError,
    TrialRecord,
    TrialRegistry,
    TrialRegistryError,
)


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


def test_trial_registry_append_and_hash_chain(tmp_path: Path):
    """Verify sequential append and cryptographic hash chain verification."""
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
    lines = registry_file.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["hypothesis"] = "TAMPERED_HYPOTHESIS"
    lines[1] = json.dumps(data)
    tampered_file = tmp_path / "tampered_registry.jsonl"
    tampered_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(RegistryTamperedError, match="Tampered record hash"):
        TrialRegistry(tampered_file)

    # 2. Tamper with sequence order (swap lines 2 and 3)
    lines_swapped = [lines[0], lines[2], lines[1]]
    swapped_file = tmp_path / "swapped_registry.jsonl"
    swapped_file.write_text("\n".join(lines_swapped) + "\n", encoding="utf-8")

    with pytest.raises(DuplicateTrialError, match="Out-of-order sequence"):
        TrialRegistry(swapped_file)

    # 3. Tamper with prev_hash
    data_broken_prev = json.loads(lines[1])
    data_broken_prev["prev_hash"] = "0" * 64
    # recompute record_hash so record_hash matches but chain is broken
    from signal_core.research.trials import _compute_record_hash
    data_broken_prev["record_hash"] = _compute_record_hash(data_broken_prev)
    broken_chain_lines = [lines[0], json.dumps(data_broken_prev), lines[2]]
    broken_chain_file = tmp_path / "broken_chain_registry.jsonl"
    broken_chain_file.write_text("\n".join(broken_chain_lines) + "\n", encoding="utf-8")

    with pytest.raises(RegistryTamperedError, match="Broken hash chain"):
        TrialRegistry(broken_chain_file)


def test_trial_registry_unauthorized_holdout_rejection(tmp_path: Path):
    """Verify that registering a trial on HOLDOUT without authorization fails closed."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    with pytest.raises(TrialRegistryError, match="Holdout partition cannot be registered"):
        registry.append_trial(
            trial_id="TRIAL_ILLEGAL_HOLDOUT",
            hypothesis="H",
            rationale="R",
            partition="HOLDOUT",
            canonical_params={"p": 1},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc="2026-11-11T10:00:00Z",
            allow_holdout=False,
        )


def test_trial_registry_shuffled_order_reproducibility(tmp_path: Path):
    """Verify canonical dictionary serialization produces identical record hashes regardless of key order."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    # Dict 1: keys in order a, b, c
    p1 = {"a": 1, "b": 2, "c": 3}
    # Dict 2: keys inserted in reverse order c, b, a
    p2 = {"c": 3, "b": 2, "a": 1}

    from signal_core.research.trials import _compute_record_hash
    base_dict1 = {"seq": 1, "prev_hash": GENESIS_PREV_HASH, "canonical_params": p1}
    base_dict2 = {"seq": 1, "prev_hash": GENESIS_PREV_HASH, "canonical_params": p2}

    h1 = _compute_record_hash(base_dict1)
    h2 = _compute_record_hash(base_dict2)
    assert h1 == h2


def test_trial_registry_variance_and_sharpe_moments(tmp_path: Path):
    """Verify pure Decimal sample variance computation across trial Sharpes."""
    registry_file = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(registry_file)

    assert registry.compute_trial_sharpe_variance() == Decimal("0.00")

    sharpes = [Decimal("1.50"), Decimal("1.70"), Decimal("1.90")]
    for i, s in enumerate(sharpes, start=1):
        registry.append_trial(
            trial_id=f"TRIAL_SHARPE_{i}",
            hypothesis="H",
            rationale="R",
            partition="IN_SAMPLE",
            canonical_params={"i": i},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.0",
            timestamp_utc=f"2026-11-11T10:0{i}:00Z",
            sharpe_ratio=s,
        )

    # Mean = 1.70
    # Differences: (1.50 - 1.70)^2 = 0.04; (1.70 - 1.70)^2 = 0; (1.90 - 1.70)^2 = 0.04
    # Sum of sq diff = 0.08
    # Sample variance V = 0.08 / (3 - 1) = 0.04
    var = registry.compute_trial_sharpe_variance()
    assert var == Decimal("0.04")
    assert registry.get_trial_sharpes() == tuple(sharpes)
