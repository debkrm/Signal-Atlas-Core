"""
Signal Atlas Core — Quantitative Research, Containment, and Anti-Overfitting Framework.
"""

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
from signal_core.research.trials import (
    DuplicateTrialError,
    RegistryTamperedError,
    TrialRecord,
    TrialRegistry,
    TrialRegistryError,
)

__all__ = [
    "ContainmentError",
    "HoldoutSealedError",
    "PartitionRole",
    "PartitionSpec",
    "PartitionSpecValidationError",
    "WalkForwardFold",
    "check_partition_access",
    "compute_fold_spec_fingerprint",
    "compute_partition_fingerprint",
    "generate_walk_forward_folds",
    "verify_holdout_unlock",
    "DuplicateTrialError",
    "RegistryTamperedError",
    "TrialRecord",
    "TrialRegistry",
    "TrialRegistryError",
]
