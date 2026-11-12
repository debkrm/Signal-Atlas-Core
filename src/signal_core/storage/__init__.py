"""
Signal Atlas Storage Layer Package.

Exports authoritative trading calendar, security master, and three-tier storage layer
(Bronze, Silver, Gold, DuckDB Views, Gating Window enforcement).
"""

from signal_core.storage.calendar import (
    DEFAULT_CALENDAR_PATH,
    BINDING_EVALUATION_START_DATE,
    CalendarError,
    InvalidSessionError,
    TradingCalendar,
    compute_calendar_fingerprint,
    load_nse_trading_calendar,
)
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    DelistingEvent,
    ISINTransitionEvent,
    SecurityMaster,
    SecurityMasterError,
    SecurityNotFoundError,
    SecurityTransitionError,
    SurveillanceInterval,
    SurveillanceStage,
    SymbolInterval,
    build_production_security_master,
    compute_security_master_fingerprint,
)
from signal_core.storage.bronze import (
    BronzeManifestEntry,
    BronzeStorage,
    BronzeStorageError,
    MissingBronzeManifestError,
    TamperedBronzePayloadError,
)
from signal_core.storage.silver import (
    MissingDependencyError,
    SilverPartitionImmutableError,
    SilverRecord,
    SilverStorage,
    SilverStorageError,
)
from signal_core.storage.gold import (
    GoldEngine,
    GoldEngineError,
)
from signal_core.storage.views import (
    DuckDBDependencyMissingError,
    DuckDBViewError,
    DuckDBViewLayer,
)
from signal_core.storage.gating import (
    GatingWindowClassification,
    GatingWindowValidationError,
    check_gating_verdict_eligibility,
    classify_gating_window,
    resolve_gating_verdict,
)

__all__ = [
    # Calendar
    "DEFAULT_CALENDAR_PATH",
    "BINDING_EVALUATION_START_DATE",
    "CalendarError",
    "InvalidSessionError",
    "TradingCalendar",
    "compute_calendar_fingerprint",
    "load_nse_trading_calendar",
    # Security Master
    "CorporateAction",
    "CorporateActionType",
    "DelistingEvent",
    "ISINTransitionEvent",
    "SecurityMaster",
    "SecurityMasterError",
    "SecurityNotFoundError",
    "SecurityTransitionError",
    "SurveillanceInterval",
    "SurveillanceStage",
    "SymbolInterval",
    "build_production_security_master",
    "compute_security_master_fingerprint",
    # Bronze
    "BronzeManifestEntry",
    "BronzeStorage",
    "BronzeStorageError",
    "MissingBronzeManifestError",
    "TamperedBronzePayloadError",
    # Silver
    "MissingDependencyError",
    "SilverPartitionImmutableError",
    "SilverRecord",
    "SilverStorage",
    "SilverStorageError",
    # Gold
    "GoldEngine",
    "GoldEngineError",
    # DuckDB Views
    "DuckDBDependencyMissingError",
    "DuckDBViewError",
    "DuckDBViewLayer",
    # Gating
    "GatingWindowClassification",
    "GatingWindowValidationError",
    "check_gating_verdict_eligibility",
    "classify_gating_window",
    "resolve_gating_verdict",
]
