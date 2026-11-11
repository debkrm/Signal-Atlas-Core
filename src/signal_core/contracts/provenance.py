"""Cryptographic Provenance and Content Fingerprinting Contracts.

Implements deterministic, canonical hashing algorithms for market price datasets
and point-in-time universe schedules.

Strictly separates internal content integrity from external source authenticity:
- Content Fingerprints (DATA-CTNT-V2, UNIV-SCHED-V1) prove byte and record
  immutability against a known digest.
- Source Authenticity requires an independent, signed exchange trust anchor.
  In the absence of an independent PKI attestation, data remains classified as
  CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
import hashlib
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.universe import UniverseSchedule


class ProvenanceError(ValueError):
    """Raised when provenance verification or cryptographic fingerprinting fails."""
    pass


class ProvenanceStatus(str, Enum):
    """
    Standardized provenance and authenticity status for datasets.
    """
    CONTENT_IDENTIFIED_ONLY = "CONTENT_IDENTIFIED_ONLY"
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    VERIFIED = "VERIFIED"  # Strictly reserved for independent PKI-anchored exchange attestations


CONTENT_FINGERPRINT_PREFIX_V2 = "DATA-CTNT-V2-"
UNIVERSE_SCHEDULE_FINGERPRINT_PREFIX_V1 = "UNIV-SCHED-V1-"
FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


def canonicalize_decimal(value: Optional[Decimal]) -> str:
    """
    Serializes a Decimal into a canonical string format preserving exact representation.
    Returns 'NONE' if the value is None.
    Rejects binary floating-point values and booleans.
    """
    if value is None:
        return "NONE"
    if isinstance(value, bool):
        raise ProvenanceError("Cannot canonicalize boolean as Decimal.")
    if isinstance(value, float):
        raise ProvenanceError("Cannot canonicalize binary float. Exact Decimal required.")
    if not isinstance(value, Decimal):
        raise ProvenanceError(f"Expected Decimal, got {type(value).__name__}.")
    if not value.is_finite():
        raise ProvenanceError(f"Cannot canonicalize non-finite Decimal: {value}")
    return str(value)


def compute_dataset_content_fingerprint(
    trading_dates: Sequence[datetime.date],
    prices_by_instrument: Mapping[str, Sequence[PriceBar]],
    benchmark_prices: Optional[Sequence[PriceBar]] = None,
    corporate_multiplier_by_inst_date: Optional[Mapping[Tuple[str, datetime.date], Tuple[Decimal, Decimal]]] = None,
) -> str:
    """
    Computes a deterministic, canonically-ordered content fingerprint (V2) across
    all price, volume, and optional corporate action adjustment records.

    Canonicalization Rules:
    1. Trading Dates Calendar:
       - Prefix 'CALENDAR:'
       - Dates must be genuine datetime.date instances (strictly rejecting datetime.datetime).
       - Sorted in chronological order (ISO-8601: YYYY-MM-DD), separated by ';', terminated by '\\n'.
    2. Instruments Price Panel:
       - Instruments processed in strict lexicographical order: 'INST:<instrument_id>\\n'
       - Instrument IDs must not contain whitespace or forbidden delimiter characters (',', ';', '\\n', '\\r', '\\t').
       - Per-instrument records sorted chronologically by trade_date.
       - Duplicate trade dates within an instrument's series are strictly rejected.
       - Each record serialized as:
         '<trade_date>,<open>,<high>,<low>,<close>,<volume>,<traded_value>,<cumulative_multiplier>,<split_ratio>\\n'
       - Missing values serialized as 'NONE'.
       - Note on PriceBar relationship: PriceBar represents raw as-traded prices. Adjustment
         multipliers (cumulative_multiplier, split_ratio) default to 'NONE' unless provided via
         the explicit corporate_multiplier_by_inst_date parameter.
    3. Benchmark Series:
       - Prefix 'BENCHMARK:\\n'
       - Benchmark records sorted chronologically by trade_date.
       - Duplicate trade dates within the benchmark series are strictly rejected.
       - Serialized as:
         '<trade_date>,<open>,<high>,<low>,<close>,<volume>,<traded_value>\\n'
    4. Digest Construction:
       - SHA-256 over canonical UTF-8 bytes.
       - Truncated to first 32 hex characters with prefix 'DATA-CTNT-V2-'.
    """
    if not trading_dates:
        raise ProvenanceError("Cannot compute content fingerprint for empty trading_dates.")

    hasher = hashlib.sha256()

    # 1. Trading Dates Calendar
    hasher.update(b"CALENDAR:")
    seen_calendar_dates: Set[datetime.date] = set()
    for dt in sorted(trading_dates):
        if type(dt) is not datetime.date:
            raise ProvenanceError(f"Calendar date must be a genuine datetime.date, got {type(dt).__name__}.")
        if dt in seen_calendar_dates:
            raise ProvenanceError(f"Duplicate date in calendar: {dt}")
        seen_calendar_dates.add(dt)
        hasher.update(dt.isoformat().encode("utf-8"))
        hasher.update(b";")
    hasher.update(b"\n")

    # 2. Per-instrument Price Panels
    for inst_id in sorted(prices_by_instrument.keys()):
        if not isinstance(inst_id, str):
            raise ProvenanceError(f"Instrument identifier must be a string, got {type(inst_id).__name__}.")
        if not inst_id or inst_id != inst_id.strip():
            raise ProvenanceError(f"Instrument identifier '{inst_id}' cannot be empty or contain leading/trailing whitespace.")
        if any(c in inst_id for c in FORBIDDEN_CHARACTERS):
            raise ProvenanceError(f"Instrument identifier '{inst_id}' contains forbidden delimiter characters.")

        hasher.update(b"INST:")
        hasher.update(inst_id.encode("utf-8"))
        hasher.update(b"\n")

        bars = prices_by_instrument[inst_id]
        seen_inst_dates: Set[datetime.date] = set()
        sorted_bars = sorted(bars, key=lambda b: b.trade_date)

        for b in sorted_bars:
            if not isinstance(b, PriceBar):
                raise ProvenanceError(f"Expected PriceBar, got {type(b).__name__}")
            if type(b.trade_date) is not datetime.date:
                raise ProvenanceError(f"PriceBar trade_date must be a genuine datetime.date, got {type(b.trade_date).__name__}.")
            if b.trade_date in seen_inst_dates:
                raise ProvenanceError(f"Duplicate price bar detected for instrument '{inst_id}' on date {b.trade_date}.")
            seen_inst_dates.add(b.trade_date)

            # Optional corporate action adjustment multipliers
            c_mult_str = "NONE"
            s_ratio_str = "NONE"
            if corporate_multiplier_by_inst_date:
                multipliers = corporate_multiplier_by_inst_date.get((inst_id, b.trade_date))
                if multipliers:
                    c_mult_str = canonicalize_decimal(multipliers[0])
                    s_ratio_str = canonicalize_decimal(multipliers[1])

            tv_str = canonicalize_decimal(b.traded_value)
            row_str = (
                f"{b.trade_date.isoformat()},"
                f"{canonicalize_decimal(b.open)},"
                f"{canonicalize_decimal(b.high)},"
                f"{canonicalize_decimal(b.low)},"
                f"{canonicalize_decimal(b.close)},"
                f"{b.volume},"
                f"{tv_str},"
                f"{c_mult_str},"
                f"{s_ratio_str}\n"
            )
            hasher.update(row_str.encode("utf-8"))

    # 3. Benchmark Series
    hasher.update(b"BENCHMARK:\n")
    if benchmark_prices:
        seen_bench_dates: Set[datetime.date] = set()
        bench_sorted = sorted(benchmark_prices, key=lambda b: b.trade_date)
        for b in bench_sorted:
            if not isinstance(b, PriceBar):
                raise ProvenanceError(f"Expected PriceBar in benchmark, got {type(b).__name__}")
            if type(b.trade_date) is not datetime.date:
                raise ProvenanceError(f"Benchmark PriceBar trade_date must be a genuine datetime.date, got {type(b.trade_date).__name__}.")
            if b.trade_date in seen_bench_dates:
                raise ProvenanceError(f"Duplicate benchmark bar detected on date {b.trade_date}.")
            seen_bench_dates.add(b.trade_date)

            tv_str = canonicalize_decimal(b.traded_value)
            b_str = (
                f"{b.trade_date.isoformat()},"
                f"{canonicalize_decimal(b.open)},"
                f"{canonicalize_decimal(b.high)},"
                f"{canonicalize_decimal(b.low)},"
                f"{canonicalize_decimal(b.close)},"
                f"{b.volume},"
                f"{tv_str}\n"
            )
            hasher.update(b_str.encode("utf-8"))

    return f"{CONTENT_FINGERPRINT_PREFIX_V2}{hasher.hexdigest()[:32]}"


def compute_universe_schedule_fingerprint(universe_schedule: UniverseSchedule) -> str:
    """
    Computes a deterministic, canonically-ordered fingerprint (V1) from a UniverseSchedule.

    Canonicalization Rules:
    1. Prefix: 'UNIVERSE_SCHEDULE:\\n'
    2. Dates processed in strict chronological order (ISO-8601: YYYY-MM-DD).
    3. Per-date row format:
       'DATE:<date>;COUNT:<count>;MEMBERS:<id1>,<id2>,...\\n'
       where instrument IDs are sorted lexicographically.
    4. Digest Construction:
       - SHA-256 over canonical UTF-8 bytes.
       - Truncated to first 32 hex characters with prefix 'UNIV-SCHED-V1-'.
    """
    if not isinstance(universe_schedule, UniverseSchedule):
        raise ProvenanceError(f"Expected UniverseSchedule, got {type(universe_schedule).__name__}")

    hasher = hashlib.sha256()
    hasher.update(b"UNIVERSE_SCHEDULE:\n")

    for dt in universe_schedule.dates:
        if type(dt) is not datetime.date:
            raise ProvenanceError(f"Universe schedule date must be a genuine datetime.date, got {type(dt).__name__}.")
        members = universe_schedule.get_universe_for_date(dt)
        for m in members:
            if any(c in m for c in FORBIDDEN_CHARACTERS):
                raise ProvenanceError(f"Universe member '{m}' contains forbidden delimiter characters.")

        row_str = f"DATE:{dt.isoformat()};COUNT:{len(members)};MEMBERS:{','.join(members)}\n"
        hasher.update(row_str.encode("utf-8"))

    return f"{UNIVERSE_SCHEDULE_FINGERPRINT_PREFIX_V1}{hasher.hexdigest()[:32]}"
