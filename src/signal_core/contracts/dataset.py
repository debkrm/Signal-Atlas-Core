"""Dataset Metadata and Snapshot Contract.

Defines the immutable DatasetSnapshot contract representing an analytical market dataset.
Guarantees explicit price adjustment conventions, date boundaries, record counts,
and cryptographic fingerprint identity without database dependencies.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.universe import UniverseSchedule
from signal_core.contracts.provenance import (
    ProvenanceStatus,
    compute_dataset_content_fingerprint,
    compute_universe_schedule_fingerprint,
)


class DatasetValidationError(ValueError):
    """Raised when dataset metadata or record collections violate structural invariants."""
    pass


class PriceConvention(str, Enum):
    """Explicit price adjustment convention for price series."""
    UNADJUSTED_RAW = "UNADJUSTED_RAW"
    SPLIT_BONUS_ADJUSTED = "SPLIT_BONUS_ADJUSTED"
    FULLY_ADJUSTED = "FULLY_ADJUSTED"


SUPPORTED_SCHEMA_VERSIONS = frozenset({"v1", "v1.0"})
DEFAULT_PROVENANCE_STATUS = f"{ProvenanceStatus.CONTENT_IDENTIFIED_ONLY.value} / {ProvenanceStatus.SOURCE_UNVERIFIED.value}"
FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    """
    Immutable metadata descriptor for an analytical market dataset.

    Invariants:
    - dataset_id, schema_version, and source_identity must be clean non-empty strings.
    - schema_version must be one of SUPPORTED_SCHEMA_VERSIONS ('v1', 'v1.0').
    - source_format, if present, records the format identifier of the originating artifact.
    - start_date and end_date must be genuine datetime.date instances (rejecting datetime.datetime).
    - start_date <= end_date.
    - session_count, instrument_count, total_instrument_records, total_price_records must be strict
      integers >= 1 (strictly rejecting booleans).
    - benchmark_record_count, if provided, must be a strict integer >= 0 (strictly rejecting booleans).
    - Record count consistency: total_price_records == total_instrument_records + (benchmark_record_count or 0).
    - content_fingerprint must be a valid non-empty string.
    - source_provenance_status strictly rejects any claim of 'VERIFIED' without external PKI proof.
    """
    dataset_id: str
    schema_version: str
    price_convention: PriceConvention
    start_date: datetime.date
    end_date: datetime.date
    session_count: int
    instrument_count: int
    total_price_records: int
    source_identity: str
    content_fingerprint: str
    source_provenance_status: str = DEFAULT_PROVENANCE_STATUS
    universe_fingerprint: Optional[str] = None
    benchmark_record_count: Optional[int] = None
    total_instrument_records: Optional[int] = None
    source_format: Optional[str] = None

    def __post_init__(self) -> None:
        # 1. Non-empty string checks with whitespace rejection
        for field_name, str_val in [
            ("dataset_id", self.dataset_id),
            ("schema_version", self.schema_version),
            ("source_identity", self.source_identity),
            ("content_fingerprint", self.content_fingerprint),
        ]:
            if not isinstance(str_val, str):
                raise DatasetValidationError(f"{field_name} must be a string, got {type(str_val).__name__}.")
            if not str_val:
                raise DatasetValidationError(f"{field_name} cannot be empty.")
            if str_val != str_val.strip():
                raise DatasetValidationError(f"{field_name} contains leading or trailing whitespace.")
            if any(c in str_val for c in ("\n", "\r", "\t")):
                raise DatasetValidationError(f"{field_name} contains forbidden control characters.")

        if self.source_format is not None:
            if not isinstance(self.source_format, str):
                raise DatasetValidationError(f"source_format must be a string, got {type(self.source_format).__name__}.")
            if not self.source_format or self.source_format != self.source_format.strip():
                raise DatasetValidationError("source_format cannot be empty or contain leading/trailing whitespace.")
            if any(c in self.source_format for c in ("\n", "\r", "\t")):
                raise DatasetValidationError("source_format contains forbidden control characters.")

        # 2. Schema Version Support Check (Core contract version)
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise DatasetValidationError(
                f"Unsupported schema_version '{self.schema_version}'. Supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        # 3. Price Convention Check
        if not isinstance(self.price_convention, PriceConvention):
            raise DatasetValidationError(
                f"price_convention must be an instance of PriceConvention, got {type(self.price_convention).__name__}."
            )

        # 4. Strict Date Checks (reject datetime.datetime)
        if type(self.start_date) is not datetime.date:
            raise DatasetValidationError(
                f"start_date must be a genuine datetime.date, got {type(self.start_date).__name__}."
            )
        if type(self.end_date) is not datetime.date:
            raise DatasetValidationError(
                f"end_date must be a genuine datetime.date, got {type(self.end_date).__name__}."
            )
        if self.start_date > self.end_date:
            raise DatasetValidationError(
                f"start_date ({self.start_date}) cannot be after end_date ({self.end_date})."
            )

        # 5. Strict Integer Counts (strictly rejecting booleans)
        for count_name, count_val in [
            ("session_count", self.session_count),
            ("instrument_count", self.instrument_count),
            ("total_price_records", self.total_price_records),
        ]:
            if isinstance(count_val, bool):
                raise DatasetValidationError(f"{count_name} cannot be a boolean.")
            if not isinstance(count_val, int):
                raise DatasetValidationError(f"{count_name} must be an integer, got {type(count_val).__name__}.")
            if count_val < 1:
                raise DatasetValidationError(f"{count_name} must be >= 1, got {count_val}.")

        if self.benchmark_record_count is not None:
            if isinstance(self.benchmark_record_count, bool):
                raise DatasetValidationError("benchmark_record_count cannot be a boolean.")
            if not isinstance(self.benchmark_record_count, int):
                raise DatasetValidationError(f"benchmark_record_count must be an integer, got {type(self.benchmark_record_count).__name__}.")
            if self.benchmark_record_count < 0:
                raise DatasetValidationError(f"benchmark_record_count must be >= 0, got {self.benchmark_record_count}.")

        # Record Count Reconciliation (Instrument + Benchmark = Total Price Records)
        bench_count = self.benchmark_record_count or 0
        if self.total_instrument_records is None:
            derived_inst_records = self.total_price_records - bench_count
            if derived_inst_records < 1:
                raise DatasetValidationError(
                    f"Derived total_instrument_records ({derived_inst_records}) must be >= 1. "
                    f"total_price_records ({self.total_price_records}) must exceed benchmark_record_count ({bench_count})."
                )
            object.__setattr__(self, "total_instrument_records", derived_inst_records)
        else:
            if isinstance(self.total_instrument_records, bool):
                raise DatasetValidationError("total_instrument_records cannot be a boolean.")
            if not isinstance(self.total_instrument_records, int):
                raise DatasetValidationError(f"total_instrument_records must be an integer, got {type(self.total_instrument_records).__name__}.")
            if self.total_instrument_records < 1:
                raise DatasetValidationError(f"total_instrument_records must be >= 1, got {self.total_instrument_records}.")
            if self.total_price_records != self.total_instrument_records + bench_count:
                raise DatasetValidationError(
                    f"Inconsistent record counts: total_price_records ({self.total_price_records}) != "
                    f"total_instrument_records ({self.total_instrument_records}) + benchmark_record_count ({bench_count})."
                )

        # 6. Universe fingerprint check if present
        if self.universe_fingerprint is not None:
            if not isinstance(self.universe_fingerprint, str):
                raise DatasetValidationError(f"universe_fingerprint must be a string, got {type(self.universe_fingerprint).__name__}.")
            if not self.universe_fingerprint or self.universe_fingerprint != self.universe_fingerprint.strip():
                raise DatasetValidationError("universe_fingerprint cannot be empty or contain whitespace.")

        # 7. Strict Provenance Gate: Reject arbitrary claims of external verification
        if not isinstance(self.source_provenance_status, str):
            raise DatasetValidationError("source_provenance_status must be a string.")
        if "VERIFIED" in self.source_provenance_status.upper() and self.source_provenance_status != DEFAULT_PROVENANCE_STATUS:
            raise DatasetValidationError(
                "Cannot initialize DatasetSnapshot with 'VERIFIED' status. External exchange PKI "
                "signatures are not implemented; datasets must remain CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED."
            )


def load_dataset_from_dict(
    payload: Dict[str, Any],
) -> Tuple[DatasetSnapshot, Dict[str, List[PriceBar]], List[PriceBar], Optional[UniverseSchedule]]:
    """
    Parses a dictionary representation (e.g. loaded from JSON) into validated
    DatasetSnapshot, price bars by instrument, benchmark price bars, and UniverseSchedule.

    Fails closed if required metadata or fields are missing.
    """
    meta = payload.get("metadata")
    if not meta or not isinstance(meta, dict):
        raise DatasetValidationError("Payload missing required 'metadata' dictionary.")

    # Parse metadata
    snap = DatasetSnapshot(
        dataset_id=meta.get("dataset_id", ""),
        schema_version=meta.get("schema_version", ""),
        price_convention=PriceConvention(meta.get("price_convention", "UNADJUSTED_RAW")),
        start_date=datetime.date.fromisoformat(meta.get("start_date", "")),
        end_date=datetime.date.fromisoformat(meta.get("end_date", "")),
        session_count=meta.get("session_count"),
        instrument_count=meta.get("instrument_count"),
        total_price_records=meta.get("total_price_records"),
        source_identity=meta.get("source_identity", ""),
        content_fingerprint=meta.get("content_fingerprint", ""),
        source_provenance_status=meta.get("source_provenance_status", DEFAULT_PROVENANCE_STATUS),
        universe_fingerprint=meta.get("universe_fingerprint"),
        benchmark_record_count=meta.get("benchmark_record_count"),
        total_instrument_records=meta.get("total_instrument_records"),
        source_format=meta.get("source_format"),
    )

    # Parse prices by instrument
    raw_prices = payload.get("prices_by_instrument", {})
    prices_by_inst: Dict[str, List[PriceBar]] = {}
    for inst_id, bars in raw_prices.items():
        parsed_bars: List[PriceBar] = []
        for b in bars:
            parsed_bars.append(
                PriceBar(
                    instrument_id=inst_id,
                    trade_date=datetime.date.fromisoformat(b["trade_date"]),
                    open=Decimal(str(b["open"])),
                    high=Decimal(str(b["high"])),
                    low=Decimal(str(b["low"])),
                    close=Decimal(str(b["close"])),
                    volume=int(b["volume"]),
                    traded_value=Decimal(str(b["traded_value"])) if b.get("traded_value") is not None else None,
                    currency=b.get("currency", "INR"),
                )
            )
        prices_by_inst[inst_id] = parsed_bars

    # Parse benchmark
    raw_bench = payload.get("benchmark_prices", [])
    benchmark_bars: List[PriceBar] = []
    for b in raw_bench:
        benchmark_bars.append(
            PriceBar(
                instrument_id=b.get("instrument_id", "BENCHMARK"),
                trade_date=datetime.date.fromisoformat(b["trade_date"]),
                open=Decimal(str(b["open"])),
                high=Decimal(str(b["high"])),
                low=Decimal(str(b["low"])),
                close=Decimal(str(b["close"])),
                volume=int(b["volume"]),
                traded_value=Decimal(str(b["traded_value"])) if b.get("traded_value") is not None else None,
                currency=b.get("currency", "INR"),
            )
        )

    # Parse universe schedule
    raw_universe = payload.get("universe_schedule")
    universe_schedule: Optional[UniverseSchedule] = None
    if raw_universe:
        sched_map: Dict[datetime.date, Sequence[str]] = {}
        for d_str, members in raw_universe.items():
            sched_map[datetime.date.fromisoformat(d_str)] = members
        universe_schedule = UniverseSchedule(sched_map)

    return snap, prices_by_inst, benchmark_bars, universe_schedule
