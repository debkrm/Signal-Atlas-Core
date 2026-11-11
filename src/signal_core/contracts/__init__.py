"""Signal Atlas Core Contracts Package.

Exports the fundamental domain contracts:
- PriceBar
- UniverseSchedule, UniverseInterval
- DatasetSnapshot, PriceConvention
- ProvenanceStatus, compute_dataset_content_fingerprint, compute_universe_schedule_fingerprint
- ExchangeSeries, SeriesEligibilityPolicy, SessionGapRecord, PriceSeriesContinuityValidator
"""

from signal_core.contracts.price_bar import PriceBar, PriceBarValidationError
from signal_core.contracts.universe import UniverseSchedule, UniverseInterval, UniverseValidationError
from signal_core.contracts.provenance import (
    ProvenanceError,
    ProvenanceStatus,
    compute_dataset_content_fingerprint,
    compute_universe_schedule_fingerprint,
)
from signal_core.contracts.dataset import (
    DatasetSnapshot,
    DatasetValidationError,
    PriceConvention,
    load_dataset_from_dict,
)

from signal_core.contracts.exchange_series import (
    PROPOSED_UNAPPROVED_EQ_ONLY_POLICY,
    QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
    InstrumentContinuityAudit,
    InstrumentListingInterval,
    PriceSeriesContinuityResult,
    PriceSeriesContinuityValidator,
    PriceSeriesGapType,
    SeriesEligibilityPolicy,
    SessionGapRecord,
    validate_raw_series_code,
)
from signal_core.contracts.legacy_compat import (
    LegacyDatasetAdjustmentMetadata,
    LegacyRecordAdjustmentMetadata,
    compute_legacy_dataset_content_fingerprint,
)

__all__ = [
    "PriceBar",
    "PriceBarValidationError",
    "UniverseSchedule",
    "UniverseInterval",
    "UniverseValidationError",
    "DatasetSnapshot",
    "DatasetValidationError",
    "PriceConvention",
    "ProvenanceStatus",
    "ProvenanceError",
    "compute_dataset_content_fingerprint",
    "compute_universe_schedule_fingerprint",
    "load_dataset_from_dict",
    "LegacyDatasetAdjustmentMetadata",
    "LegacyRecordAdjustmentMetadata",
    "compute_legacy_dataset_content_fingerprint",
    "ExchangeSeries",
    "PriceSeriesGapType",
    "SeriesEligibilityPolicy",
    "ExchangeSessionObservation",
    "SessionGapRecord",
    "InstrumentContinuityAudit",
    "InstrumentListingInterval",
    "PriceSeriesContinuityResult",
    "PriceSeriesContinuityValidator",
    "PROPOSED_UNAPPROVED_EQ_ONLY_POLICY",
    "QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY",
    "validate_raw_series_code",
]
