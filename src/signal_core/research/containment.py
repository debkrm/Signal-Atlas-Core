"""
Holdout Containment and Dataset Partitioning Protocol.

Enforces strict partition separation per AGENTS.md Rule 8.1 and Phase 2A roadmap:
- In-Sample (IS): Feature extraction, preliminary exploration.
- Validation / Calibration: Walk-forward tuning and parameter calibration folds.
- Out-of-Sample (OOS) Holdout: Cryptographically sealed confirmatory evaluation partition.

Invariants:
- Access to HOLDOUT partition fails closed unless verified with a human-created HOLDOUT_UNLOCK.
- Zero library APIs are provided to create, mock, or bypass HOLDOUT_UNLOCK.
- Fold generation operates strictly over In-Sample sessions with lookback embargo isolation.
"""

from dataclasses import dataclass
import datetime
from enum import Enum
import hashlib
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union


class ContainmentError(ValueError):
    """Base exception for research containment and partition violations."""
    pass


class HoldoutSealedError(ContainmentError):
    """Raised when unauthorized access to a sealed holdout partition is attempted."""
    pass


class PartitionSpecValidationError(ContainmentError):
    """Raised when partition boundaries or specifications violate temporal or structural invariants."""
    pass


class PartitionRole(str, Enum):
    """Role classification for historical dataset partitions."""
    IN_SAMPLE = "IN_SAMPLE"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"


@dataclass(frozen=True, slots=True)
class PartitionSpec:
    """
    Immutable specification of contiguous, disjoint dataset partitions.
    
    Temporal Invariant:
    in_sample_start <= in_sample_end < validation_start <= validation_end < holdout_start <= holdout_end
    """
    dataset_fingerprint: str
    in_sample_start: datetime.date
    in_sample_end: datetime.date
    validation_start: datetime.date
    validation_end: datetime.date
    holdout_start: datetime.date
    holdout_end: datetime.date

    def __post_init__(self) -> None:
        if (
            isinstance(self.dataset_fingerprint, bool)
            or not isinstance(self.dataset_fingerprint, str)
            or not self.dataset_fingerprint.strip()
            or self.dataset_fingerprint != self.dataset_fingerprint.strip()
        ):
            raise PartitionSpecValidationError(
                f"dataset_fingerprint must be a non-empty, non-whitespace string, got {self.dataset_fingerprint!r}"
            )

        for name, d in [
            ("in_sample_start", self.in_sample_start),
            ("in_sample_end", self.in_sample_end),
            ("validation_start", self.validation_start),
            ("validation_end", self.validation_end),
            ("holdout_start", self.holdout_start),
            ("holdout_end", self.holdout_end),
        ]:
            if type(d) is not datetime.date:
                raise PartitionSpecValidationError(
                    f"{name} must be exact datetime.date, got {type(d).__name__}"
                )

        if not (self.in_sample_start <= self.in_sample_end):
            raise PartitionSpecValidationError(
                f"in_sample_start ({self.in_sample_start}) cannot exceed in_sample_end ({self.in_sample_end})"
            )

        if not (self.in_sample_end < self.validation_start):
            raise PartitionSpecValidationError(
                f"in_sample_end ({self.in_sample_end}) must strictly precede validation_start ({self.validation_start})"
            )

        if not (self.validation_start <= self.validation_end):
            raise PartitionSpecValidationError(
                f"validation_start ({self.validation_start}) cannot exceed validation_end ({self.validation_end})"
            )

        if not (self.validation_end < self.holdout_start):
            raise PartitionSpecValidationError(
                f"validation_end ({self.validation_end}) must strictly precede holdout_start ({self.holdout_start})"
            )

        if not (self.holdout_start <= self.holdout_end):
            raise PartitionSpecValidationError(
                f"holdout_start ({self.holdout_start}) cannot exceed holdout_end ({self.holdout_end})"
            )


def compute_partition_fingerprint(spec: PartitionSpec) -> str:
    """Computes a deterministic cryptographic fingerprint for a PartitionSpec."""
    if not isinstance(spec, PartitionSpec):
        raise PartitionSpecValidationError(f"Expected PartitionSpec, got {type(spec)}")

    canonical_payload = (
        f"{spec.dataset_fingerprint}|"
        f"{spec.in_sample_start.isoformat()}|{spec.in_sample_end.isoformat()}|"
        f"{spec.validation_start.isoformat()}|{spec.validation_end.isoformat()}|"
        f"{spec.holdout_start.isoformat()}|{spec.holdout_end.isoformat()}"
    )
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"PART-SPEC-V1-{digest}"


def verify_holdout_unlock(
    unlock_file_path: Union[str, Path],
    expected_token_hash: Optional[str] = None,
) -> bool:
    """
    Verifies presence and validity of human-authorized HOLDOUT_UNLOCK sentinel file.
    
    Returns True only if file exists, contains non-empty text, and matches expected hash if provided.
    Returns False otherwise.
    """
    path = Path(unlock_file_path)
    if not path.is_file():
        return False

    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return False

    if not content:
        return False

    if expected_token_hash is not None:
        computed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if computed_hash != expected_token_hash:
            return False

    return True


def check_partition_access(
    spec: PartitionSpec,
    role: PartitionRole,
    unlock_file_path: Optional[Union[str, Path]] = None,
    expected_token_hash: Optional[str] = None,
) -> None:
    """
    Guards access to partition roles.
    
    Raises HoldoutSealedError if role is HOLDOUT and valid unlock sentinel is not provided.
    """
    if not isinstance(role, PartitionRole):
        raise PartitionSpecValidationError(f"Expected PartitionRole, got {type(role)}")

    if role == PartitionRole.HOLDOUT:
        if unlock_file_path is None or not verify_holdout_unlock(unlock_file_path, expected_token_hash):
            raise HoldoutSealedError(
                "Holdout partition is cryptographically sealed. Access is strictly forbidden "
                "without verified human HOLDOUT_UNLOCK per AGENTS.md Rule 8.1."
            )


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """
    Immutable representation of an isolated walk-forward train/test fold.
    
    Invariants:
    - train_start <= train_end < test_start <= test_end
    - Session separation: (test_start_index - train_end_index - 1) >= embargo_sessions
    """
    fold_index: int
    train_start: datetime.date
    train_end: datetime.date
    test_start: datetime.date
    test_end: datetime.date
    embargo_sessions: int

    def __post_init__(self) -> None:
        if isinstance(self.fold_index, bool) or not isinstance(self.fold_index, int) or self.fold_index < 0:
            raise PartitionSpecValidationError(f"fold_index must be non-negative integer, got {self.fold_index!r}")

        for name, d in [
            ("train_start", self.train_start),
            ("train_end", self.train_end),
            ("test_start", self.test_start),
            ("test_end", self.test_end),
        ]:
            if type(d) is not datetime.date:
                raise PartitionSpecValidationError(f"{name} must be exact datetime.date, got {type(d).__name__}")

        if self.train_start > self.train_end:
            raise PartitionSpecValidationError(
                f"train_start ({self.train_start}) exceeds train_end ({self.train_end})"
            )

        if self.train_end >= self.test_start:
            raise PartitionSpecValidationError(
                f"Lookahead violation: train_end ({self.train_end}) must strictly precede test_start ({self.test_start})"
            )

        if self.test_start > self.test_end:
            raise PartitionSpecValidationError(
                f"test_start ({self.test_start}) exceeds test_end ({self.test_end})"
            )

        if isinstance(self.embargo_sessions, bool) or not isinstance(self.embargo_sessions, int) or self.embargo_sessions < 0:
            raise PartitionSpecValidationError(f"embargo_sessions must be non-negative integer, got {self.embargo_sessions!r}")


def compute_fold_spec_fingerprint(folds: Sequence[WalkForwardFold]) -> str:
    """Computes a deterministic cryptographic fingerprint for a sequence of WalkForwardFolds."""
    if not folds:
        raise PartitionSpecValidationError("Cannot compute fingerprint for empty folds sequence.")

    fold_strings = []
    for f in folds:
        if not isinstance(f, WalkForwardFold):
            raise PartitionSpecValidationError(f"Expected WalkForwardFold, got {type(f)}")
        fold_strings.append(
            f"{f.fold_index}:{f.train_start.isoformat()}:{f.train_end.isoformat()}:"
            f"{f.test_start.isoformat()}:{f.test_end.isoformat()}:{f.embargo_sessions}"
        )

    payload = "|".join(fold_strings)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"FOLD-SPEC-V1-{digest}"


def generate_walk_forward_folds(
    calendar_sessions: Sequence[datetime.date],
    start_date: datetime.date,
    end_date: datetime.date,
    num_folds: int,
    train_sessions: int,
    test_sessions: int,
    embargo_sessions: int,
    anchored: bool = False,
) -> Tuple[WalkForwardFold, ...]:
    """
    Generates deterministic, non-overlapping walk-forward folds strictly across valid calendar sessions.

    Args:
        calendar_sessions: Authoritative ordered sequence of exchange trading sessions.
        start_date: Start session date of the partition (e.g. in_sample_start).
        end_date: End session date of the partition (e.g. in_sample_end).
        num_folds: Number of walk-forward folds to generate (>= 1).
        train_sessions: Fixed session window length for training (>= 1).
        test_sessions: Session window length for out-of-fold evaluation (>= 1).
        embargo_sessions: Minimum session buffer between train_end and test_start (>= 0).
        anchored: If True, train_start remains pinned to the first session (expanding window).
                  If False, train window rolls forward with constant train_sessions (rolling window).

    Returns:
        Immutable tuple of WalkForwardFold instances.
    """
    if type(start_date) is not datetime.date or type(end_date) is not datetime.date:
        raise PartitionSpecValidationError("start_date and end_date must be exact datetime.date")

    if start_date > end_date:
        raise PartitionSpecValidationError(f"start_date ({start_date}) cannot exceed end_date ({end_date})")

    if isinstance(num_folds, bool) or not isinstance(num_folds, int) or num_folds < 1:
        raise PartitionSpecValidationError(f"num_folds must be integer >= 1, got {num_folds!r}")

    if isinstance(train_sessions, bool) or not isinstance(train_sessions, int) or train_sessions < 1:
        raise PartitionSpecValidationError(f"train_sessions must be integer >= 1, got {train_sessions!r}")

    if isinstance(test_sessions, bool) or not isinstance(test_sessions, int) or test_sessions < 1:
        raise PartitionSpecValidationError(f"test_sessions must be integer >= 1, got {test_sessions!r}")

    if isinstance(embargo_sessions, bool) or not isinstance(embargo_sessions, int) or embargo_sessions < 0:
        raise PartitionSpecValidationError(f"embargo_sessions must be integer >= 0, got {embargo_sessions!r}")

    # Extract subsegment of sessions within [start_date, end_date]
    cal_tuple = tuple(calendar_sessions)
    sub_sessions = [d for d in cal_tuple if start_date <= d <= end_date]
    if not sub_sessions:
        raise PartitionSpecValidationError(f"No trading sessions found between {start_date} and {end_date}")

    if sub_sessions[0] != start_date or sub_sessions[-1] != end_date:
        raise PartitionSpecValidationError(
            f"Partition boundary [{start_date}, {end_date}] must align with calendar sessions. "
            f"Found span [{sub_sessions[0]}, {sub_sessions[-1]}]."
        )

    total_available_sessions = len(sub_sessions)

    # Calculate required session span:
    # Fold k has test window of test_sessions.
    # Total test window span = num_folds * test_sessions
    # First fold test window begins at or after train_sessions + embargo_sessions
    min_required = train_sessions + embargo_sessions + (num_folds * test_sessions)
    if total_available_sessions < min_required:
        raise PartitionSpecValidationError(
            f"Insufficient sessions ({total_available_sessions}) in partition [{start_date}, {end_date}] "
            f"for {num_folds} folds with train={train_sessions}, test={test_sessions}, embargo={embargo_sessions}. "
            f"Minimum required is {min_required}."
        )

    folds = []
    # Test windows are placed contiguously at the end of the available period
    test_start_offset = total_available_sessions - (num_folds * test_sessions)

    for k in range(num_folds):
        fold_test_start_idx = test_start_offset + (k * test_sessions)
        fold_test_end_idx = fold_test_start_idx + test_sessions - 1

        fold_train_end_idx = fold_test_start_idx - embargo_sessions - 1
        if fold_train_end_idx < 0:
            raise PartitionSpecValidationError(
                f"Fold {k}: train_end index {fold_train_end_idx} is negative."
            )

        if anchored:
            fold_train_start_idx = 0
        else:
            fold_train_start_idx = fold_train_end_idx - train_sessions + 1
            if fold_train_start_idx < 0:
                raise PartitionSpecValidationError(
                    f"Fold {k}: rolling train_start index {fold_train_start_idx} is negative. "
                    f"train_sessions={train_sessions} exceeds available pre-test sessions."
                )

        train_start = sub_sessions[fold_train_start_idx]
        train_end = sub_sessions[fold_train_end_idx]
        test_start = sub_sessions[fold_test_start_idx]
        test_end = sub_sessions[fold_test_end_idx]

        fold = WalkForwardFold(
            fold_index=k,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            embargo_sessions=embargo_sessions,
        )
        folds.append(fold)

    return tuple(folds)
