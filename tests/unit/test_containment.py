"""
Unit tests for research containment and walk-forward fold partitioning (Phase 2A).
"""

import datetime
from pathlib import Path
import pytest

from signal_core.research.containment import (
    ContainmentError,
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    PartitionSpecValidationError,
    WalkForwardFold,
    check_partition_access,
    compute_fold_spec_fingerprint,
    compute_partition_fingerprint,
    generate_walk_forward_folds,
    verify_holdout_unlock,
)


def test_partition_spec_validation_and_temporal_invariants():
    """Verify strict temporal ordering across IS, Validation, and Holdout partitions."""
    d_is_start = datetime.date(2022, 1, 1)
    d_is_end = datetime.date(2022, 12, 31)
    d_val_start = datetime.date(2023, 1, 1)
    d_val_end = datetime.date(2023, 6, 30)
    d_ho_start = datetime.date(2023, 7, 1)
    d_ho_end = datetime.date(2023, 12, 31)

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        in_sample_start=d_is_start,
        in_sample_end=d_is_end,
        validation_start=d_val_start,
        validation_end=d_val_end,
        holdout_start=d_ho_start,
        holdout_end=d_ho_end,
    )
    assert spec.in_sample_start == d_is_start
    assert spec.holdout_end == d_ho_end

    # 1. Inverted in-sample dates
    with pytest.raises(PartitionSpecValidationError, match="in_sample_start .* cannot exceed in_sample_end"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            in_sample_start=d_is_end,
            in_sample_end=d_is_start,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )

    # 2. Overlapping in-sample and validation
    with pytest.raises(PartitionSpecValidationError, match="in_sample_end .* must strictly precede validation_start"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            in_sample_start=d_is_start,
            in_sample_end=d_val_start,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )

    # 3. Overlapping validation and holdout
    with pytest.raises(PartitionSpecValidationError, match="validation_end .* must strictly precede holdout_start"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            in_sample_start=d_is_start,
            in_sample_end=d_is_end,
            validation_start=d_val_start,
            validation_end=d_ho_start,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )

    # 4. Non-date types
    with pytest.raises(PartitionSpecValidationError, match="must be exact datetime.date"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            in_sample_start=datetime.datetime(2022, 1, 1, 9, 15),  # type: ignore
            in_sample_end=d_is_end,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )


def test_partition_fingerprint_determinism():
    """Verify cryptographic partition fingerprint determinism."""
    spec1 = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )
    fp1 = compute_partition_fingerprint(spec1)
    fp2 = compute_partition_fingerprint(spec1)
    assert fp1 == fp2
    assert fp1.startswith("PART-SPEC-V1-")


def test_holdout_access_sealed_without_unlock(tmp_path: Path):
    """Verify that holdout partition is cryptographically sealed and fails closed."""
    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    # 1. In-Sample access succeeds without unlock
    check_partition_access(spec, PartitionRole.IN_SAMPLE)

    # 2. Validation access succeeds without unlock
    check_partition_access(spec, PartitionRole.VALIDATION)

    # 3. Holdout access fails closed without unlock sentinel
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, PartitionRole.HOLDOUT)

    # 4. Holdout access with non-existent unlock file raises HoldoutSealedError
    non_existent = tmp_path / "NON_EXISTENT_HOLDOUT_UNLOCK"
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=non_existent)


def test_holdout_unlock_verification_with_human_sentinel(tmp_path: Path):
    """Verify human sentinel validation with content hash verification."""
    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    sentinel_file = tmp_path / "HOLDOUT_UNLOCK"
    token = "HUMAN_SIGN_OFF_LEGAL_CHIEF_QUANT_2026_AUTHORIZED"
    import hashlib
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # 1. Empty file fails
    sentinel_file.write_text("   \n", encoding="utf-8")
    assert not verify_holdout_unlock(sentinel_file)
    with pytest.raises(HoldoutSealedError):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file)

    # 2. Valid token with matching hash passes
    sentinel_file.write_text(f"{token}\n", encoding="utf-8")
    assert verify_holdout_unlock(sentinel_file, expected_token_hash=expected_hash)
    # Check access succeeds
    check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file, expected_token_hash=expected_hash)

    # 3. Wrong hash fails
    wrong_hash = "0" * 64
    assert not verify_holdout_unlock(sentinel_file, expected_token_hash=wrong_hash)
    with pytest.raises(HoldoutSealedError):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file, expected_token_hash=wrong_hash)


def test_zero_library_api_can_write_or_mock_holdout_unlock():
    """Verify that containment module exposes no write or mock APIs for HOLDOUT_UNLOCK."""
    import signal_core.research.containment as c
    for attr in dir(c):
        lower_attr = attr.lower()
        if "unlock" in lower_attr:
            assert "write" not in lower_attr
            assert "create" not in lower_attr
            assert "mock" not in lower_attr
            assert "bypass" not in lower_attr
            assert "generate" not in lower_attr


def test_walk_forward_fold_generation_disjoint_and_lookahead_free():
    """
    Verify walk-forward fold generation:
    - Train and test windows never overlap
    - Lookahead free: train_end strictly precedes test_start by at least embargo_sessions + 1
    - Test windows across folds are disjoint and non-overlapping
    """
    # Create 300 business days
    base_date = datetime.date(2022, 1, 1)
    sessions = []
    d = base_date
    while len(sessions) < 300:
        if d.weekday() < 5:
            sessions.append(d)
        d += datetime.timedelta(days=1)

    start_date = sessions[0]
    end_date = sessions[-1]

    # Generate 5 folds: train=100 sessions, test=30 sessions, embargo=5 sessions
    folds = generate_walk_forward_folds(
        calendar_sessions=sessions,
        start_date=start_date,
        end_date=end_date,
        num_folds=5,
        train_sessions=100,
        test_sessions=30,
        embargo_sessions=5,
        anchored=False,
    )

    assert len(folds) == 5

    # Check each fold invariants
    for i, f in enumerate(folds):
        assert f.fold_index == i
        assert f.train_start <= f.train_end
        assert f.test_start <= f.test_end
        # Test window starts strictly after train_end + embargo
        train_end_idx = sessions.index(f.train_end)
        test_start_idx = sessions.index(f.test_start)
        assert test_start_idx - train_end_idx - 1 >= 5

    # Check test windows across folds are contiguous/disjoint without overlap
    for k in range(len(folds) - 1):
        f_current = folds[k]
        f_next = folds[k + 1]
        assert f_current.test_end < f_next.test_start

    # Test anchored mode
    anchored_folds = generate_walk_forward_folds(
        calendar_sessions=sessions,
        start_date=start_date,
        end_date=end_date,
        num_folds=5,
        train_sessions=100,
        test_sessions=30,
        embargo_sessions=5,
        anchored=True,
    )
    for f in anchored_folds:
        assert f.train_start == sessions[0]

    # Test fold spec fingerprint determinism
    fp1 = compute_fold_spec_fingerprint(folds)
    fp2 = compute_fold_spec_fingerprint(folds)
    assert fp1 == fp2
    assert fp1.startswith("FOLD-SPEC-V1-")
