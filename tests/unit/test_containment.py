"""
Unit tests for research containment and walk-forward fold partitioning (Phase 2A).
"""

import datetime
import hashlib
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
    filter_partition_observations,
    generate_walk_forward_folds,
    verify_holdout_unlock,
)


VALID_TOKEN_HASH = "a" * 64


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
        holdout_token_hash=VALID_TOKEN_HASH,
        in_sample_start=d_is_start,
        in_sample_end=d_is_end,
        validation_start=d_val_start,
        validation_end=d_val_end,
        holdout_start=d_ho_start,
        holdout_end=d_ho_end,
    )
    assert spec.in_sample_start == d_is_start
    assert spec.holdout_end == d_ho_end
    assert spec.holdout_token_hash == VALID_TOKEN_HASH

    # 1. Inverted in-sample dates
    with pytest.raises(PartitionSpecValidationError, match="in_sample_start .* cannot exceed in_sample_end"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            holdout_token_hash=VALID_TOKEN_HASH,
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
            holdout_token_hash=VALID_TOKEN_HASH,
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
            holdout_token_hash=VALID_TOKEN_HASH,
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
            holdout_token_hash=VALID_TOKEN_HASH,
            in_sample_start=datetime.datetime(2022, 1, 1, 9, 15),  # type: ignore
            in_sample_end=d_is_end,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )

    # 5. Invalid holdout_token_hash (A-1)
    with pytest.raises(PartitionSpecValidationError, match="holdout_token_hash must be a valid 64-character hex"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            holdout_token_hash="short_hash",
            in_sample_start=d_is_start,
            in_sample_end=d_is_end,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )

    with pytest.raises(PartitionSpecValidationError, match="holdout_token_hash must be a valid 64-character hex"):
        PartitionSpec(
            dataset_fingerprint="DATA-CTNT-V2-test1234",
            holdout_token_hash="z" * 64,  # non-hex char
            in_sample_start=d_is_start,
            in_sample_end=d_is_end,
            validation_start=d_val_start,
            validation_end=d_val_end,
            holdout_start=d_ho_start,
            holdout_end=d_ho_end,
        )


def test_partition_fingerprint_determinism():
    """Verify cryptographic partition fingerprint determinism and token binding."""
    spec1 = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        holdout_token_hash=VALID_TOKEN_HASH,
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

    # Different token hash must yield different partition fingerprint
    spec_diff_token = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        holdout_token_hash="b" * 64,
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )
    assert compute_partition_fingerprint(spec_diff_token) != fp1


def test_holdout_access_sealed_without_unlock(tmp_path: Path):
    """Verify that holdout partition is cryptographically sealed and fails closed."""
    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        holdout_token_hash=VALID_TOKEN_HASH,
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    # 1. In-Sample access succeeds without unlock (both enum and normalized string)
    check_partition_access(spec, PartitionRole.IN_SAMPLE)
    check_partition_access(spec, "in_sample")
    check_partition_access(spec, " IN_SAMPLE ")

    # 2. Validation access succeeds without unlock
    check_partition_access(spec, PartitionRole.VALIDATION)
    check_partition_access(spec, "validation")

    # 3. Holdout access fails closed without unlock sentinel
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, PartitionRole.HOLDOUT)

    # A-2: Bypasses via trailing spaces or casing are normalized and sealed
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, "holdout ")
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, " HOLDOUT ")

    # Invalid partition role string fails validation
    with pytest.raises(PartitionSpecValidationError, match="Invalid partition role"):
        check_partition_access(spec, "NOT_A_ROLE")

    # 4. Holdout access with non-existent unlock file raises HoldoutSealedError
    non_existent = tmp_path / "NON_EXISTENT_HOLDOUT_UNLOCK"
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=non_existent)


def test_holdout_unlock_verification_with_human_sentinel(tmp_path: Path):
    """Verify human sentinel validation with mandatory expected hash (A-1 Remediation)."""
    token = "HUMAN_SIGN_OFF_LEGAL_CHIEF_QUANT_2026_AUTHORIZED"
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        holdout_token_hash=expected_hash,
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    sentinel_file = tmp_path / "HOLDOUT_UNLOCK"

    # 1. Missing or invalid expected_token_hash argument raises PartitionSpecValidationError
    sentinel_file.write_text(f"{token}\n", encoding="utf-8")
    with pytest.raises(PartitionSpecValidationError, match="expected_token_hash must be a valid 64-hex"):
        verify_holdout_unlock(sentinel_file, expected_token_hash="invalid_hash")  # type: ignore

    # 2. Empty or whitespace sentinel file returns False and fails access
    sentinel_file.write_text("   \n", encoding="utf-8")
    assert not verify_holdout_unlock(sentinel_file, expected_token_hash=expected_hash)
    with pytest.raises(HoldoutSealedError):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file)

    # 3. Arbitrary non-matching sentinel content (A-1: 'banana') fails closed
    sentinel_file.write_text("banana\n", encoding="utf-8")
    assert not verify_holdout_unlock(sentinel_file, expected_token_hash=expected_hash)
    with pytest.raises(HoldoutSealedError):
        check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file)

    # 4. Valid token matching expected_hash passes
    sentinel_file.write_text(f"{token}\n", encoding="utf-8")
    assert verify_holdout_unlock(sentinel_file, expected_token_hash=expected_hash)
    check_partition_access(spec, PartitionRole.HOLDOUT, unlock_file_path=sentinel_file)


def test_filter_partition_observations_authoritative_gate(tmp_path: Path):
    """Verify that filter_partition_observations enforces containment on observation streams (A-6)."""
    token = "AUTHORIZED_HOLDOUT_SECRET_TOKEN"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-test1234",
        holdout_token_hash=token_hash,
        in_sample_start=datetime.date(2022, 1, 1),
        in_sample_end=datetime.date(2022, 12, 31),
        validation_start=datetime.date(2023, 1, 1),
        validation_end=datetime.date(2023, 6, 30),
        holdout_start=datetime.date(2023, 7, 1),
        holdout_end=datetime.date(2023, 12, 31),
    )

    class DummyObs:
        def __init__(self, d: datetime.date, val: int):
            self.trade_date = d
            self.val = val

    obs_list = [
        DummyObs(datetime.date(2022, 5, 10), 1),
        DummyObs(datetime.date(2023, 3, 15), 2),
        DummyObs(datetime.date(2023, 9, 20), 3),
    ]

    # IS access
    is_obs = filter_partition_observations(obs_list, spec, PartitionRole.IN_SAMPLE)
    assert len(is_obs) == 1
    assert is_obs[0].val == 1

    # Validation access
    val_obs = filter_partition_observations(obs_list, spec, PartitionRole.VALIDATION)
    assert len(val_obs) == 1
    assert val_obs[0].val == 2

    # Holdout access without unlock fails closed
    with pytest.raises(HoldoutSealedError):
        filter_partition_observations(obs_list, spec, PartitionRole.HOLDOUT)

    # Holdout access with wrong sentinel fails closed
    bad_sentinel = tmp_path / "BAD_UNLOCK"
    bad_sentinel.write_text("banana\n", encoding="utf-8")
    with pytest.raises(HoldoutSealedError):
        filter_partition_observations(obs_list, spec, PartitionRole.HOLDOUT, unlock_file_path=bad_sentinel)

    # Holdout access with matching sentinel succeeds
    good_sentinel = tmp_path / "GOOD_UNLOCK"
    good_sentinel.write_text(f"{token}\n", encoding="utf-8")
    ho_obs = filter_partition_observations(obs_list, spec, PartitionRole.HOLDOUT, unlock_file_path=good_sentinel)
    assert len(ho_obs) == 1
    assert ho_obs[0].val == 3


def test_walk_forward_fold_declarative_embargo_rejection():
    """Verify that WalkForwardFold rejects declarative embargoes unbacked by calendar gap (A-8/A-10)."""
    # 1 calendar day gap cannot accommodate embargo_sessions=5
    with pytest.raises(PartitionSpecValidationError, match="violates calendar separation"):
        WalkForwardFold(
            fold_index=0,
            train_start=datetime.date(2023, 1, 1),
            train_end=datetime.date(2023, 1, 10),
            test_start=datetime.date(2023, 1, 11),
            test_end=datetime.date(2023, 1, 20),
            embargo_sessions=5,
        )


def test_generate_walk_forward_folds_calendar_validation():
    """Verify calendar validation against duplicates, ordering, and types (A-16)."""
    d1 = datetime.date(2023, 1, 1)
    d2 = datetime.date(2023, 1, 2)
    d3 = datetime.date(2023, 1, 3)

    # Duplicates rejected
    with pytest.raises(PartitionSpecValidationError, match="strictly monotonically increasing"):
        generate_walk_forward_folds(
            calendar_sessions=[d1, d1, d2, d3],
            start_date=d1,
            end_date=d3,
            num_folds=1,
            train_sessions=1,
            test_sessions=1,
            embargo_sessions=0,
        )

    # Non-monotonic rejected
    with pytest.raises(PartitionSpecValidationError, match="strictly monotonically increasing"):
        generate_walk_forward_folds(
            calendar_sessions=[d1, d3, d2],
            start_date=d1,
            end_date=d2,
            num_folds=1,
            train_sessions=1,
            test_sessions=1,
            embargo_sessions=0,
        )


def test_generate_walk_forward_folds_anchored_mode_min_required():
    """Verify anchored mode min_required calculation does not over-reject (A-17)."""
    sessions = [datetime.date(2023, 1, i) for i in range(1, 7)]
    # 6 sessions, train=4, test=3, embargo=0, anchored=True
    # Fold 0: test is indices 3..5 (Jan 4..6, 3 sessions), train is 0..2 (Jan 1..3, 3 sessions).
    folds = generate_walk_forward_folds(
        calendar_sessions=sessions,
        start_date=sessions[0],
        end_date=sessions[-1],
        num_folds=1,
        train_sessions=4,
        test_sessions=3,
        embargo_sessions=0,
        anchored=True,
    )
    assert len(folds) == 1
    assert folds[0].train_start == sessions[0]
    assert folds[0].train_end == sessions[2]
    assert folds[0].test_start == sessions[3]
    assert folds[0].test_end == sessions[5]


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
