"""Read-Only Historical Dataset Snapshot Loader and Verification.

Implements a deterministic, read-only loader for historical development snapshots
(e.g. historical_dev_dataset_2022_2024.json).

Key Architecture:
- Opens files strictly read-only.
- Parses complete snapshot artifact into memory via json.load in read-only mode, keeping the implementation simple and auditable.
- Computes raw file digests via streaming 1MB binary chunk reads in compute_file_sha256.
- Constructs clean, unadjusted PriceBar domain objects (using raw_volume as integer volume).
- Preserves legacy adjustment multipliers, volume strings, and metadata separately
  in LegacyDatasetAdjustmentMetadata.
- Validates data integrity fail-closed: reconciles declared counts against parsed records,
  rejects duplicate calendar dates, duplicate bars, invalid Decimals, and malformed universe memberships.
- Produces comprehensive, read-only diagnostics across market sessions and PIT universe schedules.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from signal_core.contracts.dataset import (
    DEFAULT_PROVENANCE_STATUS,
    DatasetSnapshot,
    DatasetValidationError,
    PriceConvention,
    SUPPORTED_SCHEMA_VERSIONS,
)

SUPPORTED_SNAPSHOT_FORMATS = frozenset({"signal-atlas-dataset-snapshot-v1"})
from signal_core.contracts.legacy_compat import (
    LegacyDatasetAdjustmentMetadata,
    LegacyRecordAdjustmentMetadata,
    compute_legacy_dataset_content_fingerprint,
)
from signal_core.contracts.price_bar import PriceBar, PriceBarValidationError
from signal_core.contracts.provenance import (
    ProvenanceError,
    compute_universe_schedule_fingerprint,
)
from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError


class HistoricalSnapshotError(ValueError):
    """Raised when historical snapshot format, schema, or records fail validation."""
    pass


@dataclass(frozen=True, slots=True)
class HistoricalDataset:
    """
    Immutable container representing a loaded historical research dataset.
    Cleanly separates unadjusted domain objects from legacy compatibility metadata.
    """
    snapshot: DatasetSnapshot
    prices_by_instrument: Mapping[str, Sequence[PriceBar]]
    benchmark_prices: Sequence[PriceBar]
    universe_schedule: UniverseSchedule
    trading_dates: Sequence[datetime.date]
    symbols_by_instrument: Mapping[str, str]
    legacy_adjustments: LegacyDatasetAdjustmentMetadata


@dataclass(frozen=True, slots=True)
class DatasetDiagnosticReport:
    """
    Summary diagnostics for a loaded historical dataset.
    """
    total_sessions: int
    start_date: datetime.date
    end_date: datetime.date
    instrument_count: int
    instrument_records_count: int
    benchmark_records_count: int
    total_price_records: int
    universe_schedule_dates_count: int
    unique_universe_members_count: int
    duplicate_records_count: int
    universe_dates_outside_calendar_count: int
    unmatched_universe_pairs_count: int
    unmatched_members_count: int
    min_instrument_coverage: int
    max_instrument_coverage: int
    avg_instrument_coverage: float
    unmatched_pairs_by_symbol: Mapping[str, List[datetime.date]]


def compute_file_sha256(path: Union[str, Path], chunk_size: int = 1048576) -> str:
    """
    Computes the SHA-256 checksum of an artifact file on disk using read-only streaming.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Snapshot file not found: {p}")

    hasher = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_decimal_field(val: Any, field_name: str, record_desc: str) -> Decimal:
    """Parses a value into an exact finite Decimal, rejecting booleans, floats, and invalid strings."""
    if val is None:
        raise HistoricalSnapshotError(f"Missing required Decimal field '{field_name}' in {record_desc}.")
    if isinstance(val, bool):
        raise HistoricalSnapshotError(f"Field '{field_name}' in {record_desc} cannot be boolean.")
    if isinstance(val, float):
        raise HistoricalSnapshotError(f"Field '{field_name}' in {record_desc} cannot be binary float.")
    try:
        d = Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HistoricalSnapshotError(f"Invalid Decimal for '{field_name}' in {record_desc}: {val!r}") from exc
    if not d.is_finite():
        raise HistoricalSnapshotError(f"Field '{field_name}' in {record_desc} must be finite: {val!r}")
    return d


def _parse_optional_decimal(val: Any, field_name: str, record_desc: str) -> Optional[Decimal]:
    """Parses an optional value into an exact finite Decimal or None."""
    if val is None:
        return None
    return _parse_decimal_field(val, field_name, record_desc)


def _parse_date_field(val: Any, field_name: str, record_desc: str) -> datetime.date:
    """Parses an ISO date string into a genuine datetime.date, rejecting datetime."""
    if not isinstance(val, str) or not val:
        raise HistoricalSnapshotError(f"Field '{field_name}' in {record_desc} must be a non-empty ISO date string, got {val!r}.")
    try:
        dt = datetime.date.fromisoformat(val)
    except ValueError as exc:
        raise HistoricalSnapshotError(f"Field '{field_name}' in {record_desc} is not a valid ISO date: {val!r}") from exc
    return dt


def load_historical_snapshot(path: Union[str, Path]) -> HistoricalDataset:
    """
    Loads and validates a historical dataset snapshot from disk in read-only mode.

    Fails closed on:
    - Missing file or unreadable permissions.
    - Unsupported snapshot format / schema version.
    - Duplicate calendar dates, duplicate instrument dates, or duplicate benchmark dates.
    - Invalid Decimal, integer volume, or date types.
    - Broken OHLC boundaries.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Historical snapshot file does not exist at: '{file_path}'")

    # 1. Read JSON in read-only mode
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        raise HistoricalSnapshotError(f"Failed to read/parse snapshot JSON at '{file_path}': {exc}") from exc

    if not isinstance(raw, dict):
        raise HistoricalSnapshotError(f"Snapshot root must be a JSON object, got {type(raw).__name__}.")

    # 2. Schema format validation (distinguishing source snapshot format from core schema version)
    snapshot_format = raw.get("snapshot_format")
    if not snapshot_format or snapshot_format not in SUPPORTED_SNAPSHOT_FORMATS:
        raise HistoricalSnapshotError(
            f"Unsupported snapshot_format '{snapshot_format}'. Supported formats: {sorted(SUPPORTED_SNAPSHOT_FORMATS)}"
        )

    # 3. Calendar dates validation
    raw_dates = raw.get("trading_dates")
    if not raw_dates or not isinstance(raw_dates, list):
        raise HistoricalSnapshotError("Snapshot missing required non-empty 'trading_dates' list.")

    trading_dates: List[datetime.date] = []
    seen_dates: Set[datetime.date] = set()
    for idx, d_str in enumerate(raw_dates):
        dt = _parse_date_field(d_str, f"trading_dates[{idx}]", "calendar")
        if dt in seen_dates:
            raise HistoricalSnapshotError(f"Duplicate calendar date found in snapshot: {dt}")
        seen_dates.add(dt)
        trading_dates.append(dt)

    trading_dates.sort()

    # 4. Parse prices_by_instrument
    raw_prices_by_inst = raw.get("prices_by_instrument")
    if not isinstance(raw_prices_by_inst, dict) or not raw_prices_by_inst:
        raise HistoricalSnapshotError("Snapshot missing required non-empty 'prices_by_instrument' dictionary.")

    clean_prices_by_inst: Dict[str, List[PriceBar]] = {}
    inst_adjustments_map: Dict[Tuple[str, datetime.date], LegacyRecordAdjustmentMetadata] = {}

    for inst_id, raw_bars in raw_prices_by_inst.items():
        if not isinstance(inst_id, str) or not inst_id or inst_id != inst_id.strip():
            raise HistoricalSnapshotError(f"Invalid instrument identifier: '{inst_id}'")
        if not isinstance(raw_bars, list):
            raise HistoricalSnapshotError(f"Bars for instrument '{inst_id}' must be a list, got {type(raw_bars).__name__}.")

        parsed_bars: List[PriceBar] = []
        inst_seen_dates: Set[datetime.date] = set()

        for b_idx, r in enumerate(raw_bars):
            rec_desc = f"instrument '{inst_id}' record[{b_idx}]"
            if not isinstance(r, dict):
                raise HistoricalSnapshotError(f"Bar {rec_desc} must be an object.")

            trade_date = _parse_date_field(r.get("trade_date"), "trade_date", rec_desc)
            if trade_date in inst_seen_dates:
                raise HistoricalSnapshotError(f"Duplicate trade_date {trade_date} for {rec_desc}.")
            inst_seen_dates.add(trade_date)

            o = _parse_decimal_field(r.get("open"), "open", rec_desc)
            h = _parse_decimal_field(r.get("high"), "high", rec_desc)
            l = _parse_decimal_field(r.get("low"), "low", rec_desc)
            c = _parse_decimal_field(r.get("close"), "close", rec_desc)

            # Volume: unadjusted integer raw_volume preferred for pure PriceBar
            raw_vol = r.get("raw_volume")
            if raw_vol is None:
                # Fallback to volume if raw_volume is absent, ensuring integer conversion
                vol_val = r.get("volume")
                if vol_val is None:
                    raise HistoricalSnapshotError(f"Missing volume for {rec_desc}.")
                raw_vol = int(Decimal(str(vol_val)))
            elif isinstance(raw_vol, bool) or not isinstance(raw_vol, int) or raw_vol < 0:
                raise HistoricalSnapshotError(f"Invalid raw_volume for {rec_desc}: {raw_vol!r}")

            tv = _parse_optional_decimal(r.get("traded_value"), "traded_value", rec_desc)

            try:
                bar = PriceBar(
                    instrument_id=inst_id,
                    trade_date=trade_date,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=raw_vol,
                    traded_value=tv,
                    currency="INR",
                )
            except PriceBarValidationError as exc:
                raise HistoricalSnapshotError(f"Validation failed for {rec_desc}: {exc}") from exc

            parsed_bars.append(bar)

            # Preserve legacy adjustment metadata separately
            c_mult = _parse_optional_decimal(r.get("cumulative_multiplier"), "cumulative_multiplier", rec_desc)
            s_ratio = _parse_optional_decimal(r.get("split_ratio"), "split_ratio", rec_desc)
            leg_vol = _parse_optional_decimal(r.get("volume"), "volume", rec_desc)
            prev_c = _parse_optional_decimal(r.get("prev_close"), "prev_close", rec_desc)
            prev_c_mult = _parse_optional_decimal(r.get("prev_close_multiplier"), "prev_close_multiplier", rec_desc)
            raw_prev_c = _parse_optional_decimal(r.get("raw_prev_close"), "raw_prev_close", rec_desc)
            adj_ver = r.get("adjustment_version")

            inst_adjustments_map[(inst_id, trade_date)] = LegacyRecordAdjustmentMetadata(
                cumulative_multiplier=c_mult,
                split_ratio=s_ratio,
                legacy_volume_decimal=leg_vol,
                prev_close=prev_c,
                prev_close_multiplier=prev_c_mult,
                raw_prev_close=raw_prev_c,
                adjustment_version=adj_ver,
            )

        parsed_bars.sort(key=lambda x: x.trade_date)
        clean_prices_by_inst[inst_id] = parsed_bars

    # 5. Parse benchmark series
    clean_bench_bars: List[PriceBar] = []
    bench_adjustments_map: Dict[datetime.date, LegacyRecordAdjustmentMetadata] = {}
    raw_bench = raw.get("benchmark_prices", [])
    if isinstance(raw_bench, list):
        bench_seen_dates: Set[datetime.date] = set()
        for b_idx, r in enumerate(raw_bench):
            rec_desc = f"benchmark record[{b_idx}]"
            trade_date = _parse_date_field(r.get("trade_date"), "trade_date", rec_desc)
            if trade_date in bench_seen_dates:
                raise HistoricalSnapshotError(f"Duplicate trade_date {trade_date} for {rec_desc}.")
            bench_seen_dates.add(trade_date)

            o = _parse_decimal_field(r.get("open"), "open", rec_desc)
            h = _parse_decimal_field(r.get("high"), "high", rec_desc)
            l = _parse_decimal_field(r.get("low"), "low", rec_desc)
            c = _parse_decimal_field(r.get("close"), "close", rec_desc)

            raw_vol = r.get("raw_volume")
            if raw_vol is None:
                vol_val = r.get("volume")
                raw_vol = int(Decimal(str(vol_val))) if vol_val is not None else 0
            elif isinstance(raw_vol, bool) or not isinstance(raw_vol, int) or raw_vol < 0:
                raise HistoricalSnapshotError(f"Invalid raw_volume for {rec_desc}: {raw_vol!r}")

            tv = _parse_optional_decimal(r.get("traded_value"), "traded_value", rec_desc)

            try:
                b_bar = PriceBar(
                    instrument_id="BENCHMARK",
                    trade_date=trade_date,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=raw_vol,
                    traded_value=tv,
                    currency="INR",
                )
            except PriceBarValidationError as exc:
                raise HistoricalSnapshotError(f"Validation failed for {rec_desc}: {exc}") from exc

            clean_bench_bars.append(b_bar)

            bench_adjustments_map[trade_date] = LegacyRecordAdjustmentMetadata(
                cumulative_multiplier=_parse_optional_decimal(r.get("cumulative_multiplier"), "cumulative_multiplier", rec_desc),
                split_ratio=_parse_optional_decimal(r.get("split_ratio"), "split_ratio", rec_desc),
                legacy_volume_decimal=_parse_optional_decimal(r.get("volume"), "volume", rec_desc),
                prev_close=_parse_optional_decimal(r.get("prev_close"), "prev_close", rec_desc),
                prev_close_multiplier=_parse_optional_decimal(r.get("prev_close_multiplier"), "prev_close_multiplier", rec_desc),
                raw_prev_close=_parse_optional_decimal(r.get("raw_prev_close"), "raw_prev_close", rec_desc),
                adjustment_version=r.get("adjustment_version"),
            )

        clean_bench_bars.sort(key=lambda x: x.trade_date)

    # 6. Parse Universe Schedule
    raw_universe = raw.get("universe_by_date")
    if not isinstance(raw_universe, dict):
        raise HistoricalSnapshotError("Snapshot missing required 'universe_by_date' mapping.")

    schedule_mapping: Dict[datetime.date, Sequence[str]] = {}
    for d_str, members in raw_universe.items():
        dt = _parse_date_field(d_str, "universe_date", "universe_by_date")
        if not isinstance(members, (list, set, tuple)):
            raise HistoricalSnapshotError(f"Universe members for date {d_str} must be a list/set/tuple.")
        schedule_mapping[dt] = members

    try:
        universe_schedule = UniverseSchedule(schedule_mapping)
    except UniverseValidationError as exc:
        raise HistoricalSnapshotError(f"Universe schedule construction failed: {exc}") from exc

    # 7. Construct Legacy Adjustment Metadata Container
    legacy_adjustments = LegacyDatasetAdjustmentMetadata(
        adjustments_by_inst_date=inst_adjustments_map,
        benchmark_adjustments_by_date=bench_adjustments_map,
    )

    # 8. Compute / verify Universe Schedule Fingerprint
    computed_univ_fp = compute_universe_schedule_fingerprint(universe_schedule)

    # 9. Reconcile declared metadata counts with actual parsed records
    total_inst_records = sum(len(bars) for bars in clean_prices_by_inst.values())
    total_price_records = total_inst_records + len(clean_bench_bars)

    if "session_count" in raw:
        decl_sessions = raw["session_count"]
        if isinstance(decl_sessions, bool) or not isinstance(decl_sessions, int):
            raise HistoricalSnapshotError(f"Declared session_count must be integer, got {decl_sessions!r}")
        if len(trading_dates) != decl_sessions:
            raise HistoricalSnapshotError(
                f"Declared session_count ({decl_sessions}) does not match actual trading dates count ({len(trading_dates)})."
            )

    if "instrument_count" in raw:
        decl_inst = raw["instrument_count"]
        if isinstance(decl_inst, bool) or not isinstance(decl_inst, int):
            raise HistoricalSnapshotError(f"Declared instrument_count must be integer, got {decl_inst!r}")
        if len(clean_prices_by_inst) != decl_inst:
            raise HistoricalSnapshotError(
                f"Declared instrument_count ({decl_inst}) does not match actual instrument count ({len(clean_prices_by_inst)})."
            )

    if "total_instrument_records" in raw:
        decl_inst_records = raw["total_instrument_records"]
        if isinstance(decl_inst_records, bool) or not isinstance(decl_inst_records, int):
            raise HistoricalSnapshotError(f"Declared total_instrument_records must be integer, got {decl_inst_records!r}")
        if total_inst_records != decl_inst_records:
            raise HistoricalSnapshotError(
                f"Declared total_instrument_records ({decl_inst_records}) does not match actual instrument records count ({total_inst_records})."
            )

    if "benchmark_record_count" in raw:
        decl_bench = raw["benchmark_record_count"]
        if isinstance(decl_bench, bool) or not isinstance(decl_bench, int):
            raise HistoricalSnapshotError(f"Declared benchmark_record_count must be integer, got {decl_bench!r}")
        if len(clean_bench_bars) != decl_bench:
            raise HistoricalSnapshotError(
                f"Declared benchmark_record_count ({decl_bench}) does not match actual benchmark records count ({len(clean_bench_bars)})."
            )

    # 10. Construct DatasetSnapshot metadata
    try:
        snapshot = DatasetSnapshot(
            dataset_id=str(raw.get("data_version", "EXP-DEV-2022-2024-V2")),
            schema_version="v1.0",
            price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED,
            start_date=trading_dates[0],
            end_date=trading_dates[-1],
            session_count=len(trading_dates),
            instrument_count=len(clean_prices_by_inst),
            total_instrument_records=total_inst_records,
            total_price_records=total_price_records,
            source_identity=str(raw.get("source_identity", "NSE_BHAVCOPY_DAILY")),
            content_fingerprint=str(raw.get("content_fingerprint", "")),
            source_provenance_status=DEFAULT_PROVENANCE_STATUS,
            universe_fingerprint=computed_univ_fp,
            benchmark_record_count=len(clean_bench_bars),
            source_format=str(snapshot_format),
        )
    except DatasetValidationError as exc:
        raise HistoricalSnapshotError(f"DatasetSnapshot validation failed: {exc}") from exc

    symbols_by_inst = raw.get("symbols_by_instrument", {})

    return HistoricalDataset(
        snapshot=snapshot,
        prices_by_instrument=clean_prices_by_inst,
        benchmark_prices=clean_bench_bars,
        universe_schedule=universe_schedule,
        trading_dates=trading_dates,
        symbols_by_instrument=symbols_by_inst,
        legacy_adjustments=legacy_adjustments,
    )


def run_dataset_diagnostics(dataset: HistoricalDataset) -> DatasetDiagnosticReport:
    """
    Computes read-only dataset consistency diagnostics across trading calendar,
    instrument price records, and point-in-time universe schedules.
    """
    calendar_dates = sorted(dataset.trading_dates)
    calendar_dates_set = set(calendar_dates)
    session_count = len(calendar_dates)
    start_date = calendar_dates[0]
    end_date = calendar_dates[-1]

    prices_by_inst = dataset.prices_by_instrument
    instrument_count = len(prices_by_inst)
    inst_records_count = sum(len(bars) for bars in prices_by_inst.values())
    bench_records_count = len(dataset.benchmark_prices)
    total_price_records = inst_records_count + bench_records_count

    universe_schedule = dataset.universe_schedule
    universe_dates = sorted(universe_schedule.dates)
    unique_members = universe_schedule.unique_instruments

    # Check universe dates outside dataset calendar
    outside_calendar = [d for d in universe_dates if d not in calendar_dates_set]

    # Map available dates per instrument
    dates_by_inst: Dict[str, Set[datetime.date]] = {
        inst: {b.trade_date for b in bars}
        for inst, bars in prices_by_inst.items()
    }

    # Duplicate records check (PriceBar guarantees no duplicates inside loader)
    duplicate_records_count = 0
    for bars in prices_by_inst.values():
        seen: Set[datetime.date] = set()
        for b in bars:
            if b.trade_date in seen:
                duplicate_records_count += 1
            seen.add(b.trade_date)

    # Check universe members without price record on scheduled date
    unmatched_pairs_by_symbol: Dict[str, List[datetime.date]] = {}
    unmatched_pairs_count = 0
    symbols_map = dataset.symbols_by_instrument

    for d in universe_dates:
        members = universe_schedule.get_universe_for_date(d)
        for m in members:
            if m not in dates_by_inst or d not in dates_by_inst[m]:
                unmatched_pairs_count += 1
                sym = symbols_map.get(m, m)
                if sym not in unmatched_pairs_by_symbol:
                    unmatched_pairs_by_symbol[sym] = []
                unmatched_pairs_by_symbol[sym].append(d)

    coverage_counts = [len(s) for s in dates_by_inst.values()]
    min_cov = min(coverage_counts) if coverage_counts else 0
    max_cov = max(coverage_counts) if coverage_counts else 0
    avg_cov = (sum(coverage_counts) / len(coverage_counts)) if coverage_counts else 0.0

    return DatasetDiagnosticReport(
        total_sessions=session_count,
        start_date=start_date,
        end_date=end_date,
        instrument_count=instrument_count,
        instrument_records_count=inst_records_count,
        benchmark_records_count=bench_records_count,
        total_price_records=total_price_records,
        universe_schedule_dates_count=len(universe_dates),
        unique_universe_members_count=len(unique_members),
        duplicate_records_count=duplicate_records_count,
        universe_dates_outside_calendar_count=len(outside_calendar),
        unmatched_universe_pairs_count=unmatched_pairs_count,
        unmatched_members_count=len(unmatched_pairs_by_symbol),
        min_instrument_coverage=min_cov,
        max_instrument_coverage=max_cov,
        avg_instrument_coverage=avg_cov,
        unmatched_pairs_by_symbol=unmatched_pairs_by_symbol,
    )
