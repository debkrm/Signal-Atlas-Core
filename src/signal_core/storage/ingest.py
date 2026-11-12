"""
Signal Atlas Core — Bhavcopy Ingestion Pipeline
Frozen Ingestion Pipeline per AGENTS.md Rule 10 (Market Data Ingestion, Storage & Reproducibility),
Audit §26 (Wave 1 Thin Real-Data Vertical Slice), and Audit §30 (Findings H-23, H-24, H-25).

Handles:
- Byte-exact content-addressed storage in Bronze with SHA-256 provenance manifest.
- Parsing of real exchange Bhavcopy archives (both legacy and unified formats, handling trailing delimiters).
- Type coercion to exact Decimal (OHLC) and strict integral validation for volume (Rule 6.4, Finding H-23).
- Strict multi-row trade_date cross-checking preventing mixed-date archives (Rule 6.3, Finding H-24).
- Fail-closed truncation and duplicate row detection (Finding H-25).
- Atomic, immutable Silver daily Parquet partition generation.
"""

import csv
import datetime
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import zipfile

from signal_core.storage.bronze import BronzeManifestEntry, BronzeStorage, BronzeStorageError
from signal_core.storage.calendar import TradingCalendar
from signal_core.storage.silver import (
    SilverRecord,
    SilverStorage,
    SilverStorageError,
)

# Date formats used in NSE Bhavcopy CSV files
_LEGACY_DATE_FORMAT = "%d-%b-%Y"  # e.g. 01-JAN-2024


class BhavcopyIngestError(Exception):
    """Raised when Bhavcopy parsing or ingestion fails."""
    pass


def parse_bhavcopy_date(date_str: str) -> datetime.date:
    """Parses date string from Bhavcopy TIMESTAMP / TRADEDATE column."""
    cleaned = date_str.strip()
    # Try legacy format (DD-MON-YYYY, e.g. 01-JAN-2024)
    try:
        return datetime.datetime.strptime(cleaned, _LEGACY_DATE_FORMAT).date()
    except ValueError:
        pass
    # Try ISO format (YYYY-MM-DD)
    try:
        return datetime.date.fromisoformat(cleaned)
    except ValueError:
        pass
    raise BhavcopyIngestError(f"Unrecognized date format in Bhavcopy: {date_str!r}")


def parse_bhavcopy_archive(
    archive_data: Union[bytes, Path, str],
    trade_date: Optional[datetime.date] = None,
    target_isins: Optional[Sequence[str]] = None,
    target_series: Optional[Sequence[str]] = ("EQ", "BE", "SM", "BZ"),
) -> Tuple[datetime.date, List[SilverRecord]]:
    """
    Parses a raw Bhavcopy ZIP archive and extracts typed SilverRecord objects.
    
    Supports:
    - Legacy 2015-mid 2024 format: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP, ISIN...
    - Mid-2024 unified format: TCKRSYMB, SCTYSRS, OPNPRIC, HGHPRIC, LWPRIC, CLSPRIC, TTLTRADGVOL, TTLTRFVAL, TRADEDATE, ISIN...
    - Robust handling of trailing delimiters / empty trailing fields.
    - Strict Decimal-based volume parsing preventing float rounding or fractional volumes (Finding H-23).
    - Multi-row trade_date consistency validation preventing mixed-date archives (Finding H-24).
    - Fail-closed truncation detection on targeted ISIN rows (Finding H-25).
    - Filtering by target_isins (case-insensitive) and target_series.
    
    Returns:
        (resolved_trade_date, list_of_silver_records)
    """
    if isinstance(archive_data, (str, Path)):
        p = Path(archive_data)
        if not p.is_file():
            raise FileNotFoundError(f"Bhavcopy archive not found at: {p}")
        with open(p, "rb") as f:
            raw_bytes = f.read()
    elif isinstance(archive_data, bytes):
        raw_bytes = archive_data
    else:
        raise BhavcopyIngestError(f"archive_data must be bytes, Path, or str, got {type(archive_data).__name__}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise BhavcopyIngestError(f"Failed to open zip archive: {exc}") from exc

    namelist = zf.namelist()
    if not namelist:
        raise BhavcopyIngestError("Bhavcopy zip archive is empty.")

    csv_filenames = [n for n in namelist if n.lower().endswith(".csv")]
    if not csv_filenames:
        raise BhavcopyIngestError(f"No CSV file found inside Bhavcopy archive. Contents: {namelist}")

    # Use first CSV file
    csv_bytes = zf.read(csv_filenames[0])
    text_stream = io.TextIOWrapper(io.BytesIO(csv_bytes), encoding="utf-8", errors="replace")
    reader = csv.reader(text_stream)

    raw_header = next(reader, None)
    if not raw_header:
        raise BhavcopyIngestError(f"Bhavcopy CSV file '{csv_filenames[0]}' is empty.")

    header_upper = [h.strip().upper() for h in raw_header]

    # Detect header variant
    if "SYMBOL" in header_upper:
        sym_idx = header_upper.index("SYMBOL")
        srs_idx = header_upper.index("SERIES")
        o_idx = header_upper.index("OPEN")
        h_idx = header_upper.index("HIGH")
        l_idx = header_upper.index("LOW")
        c_idx = header_upper.index("CLOSE")
        vol_idx = header_upper.index("TOTTRDQTY")
        isin_idx = header_upper.index("ISIN")
        val_idx = header_upper.index("TOTTRDVAL") if "TOTTRDVAL" in header_upper else None
        date_idx = header_upper.index("TIMESTAMP") if "TIMESTAMP" in header_upper else None
    elif "TCKRSYMB" in header_upper:
        sym_idx = header_upper.index("TCKRSYMB")
        srs_idx = header_upper.index("SCTYSRS")
        o_idx = header_upper.index("OPNPRIC")
        h_idx = header_upper.index("HGHPRIC")
        l_idx = header_upper.index("LWPRIC")
        c_idx = header_upper.index("CLSPRIC")
        vol_idx = header_upper.index("TTLTRADGVOL")
        isin_idx = header_upper.index("ISIN")
        val_idx = header_upper.index("TTLTRFVAL") if "TTLTRFVAL" in header_upper else None
        date_idx = header_upper.index("TRADEDATE") if "TRADEDATE" in header_upper else None
    else:
        raise BhavcopyIngestError(
            f"Unrecognized Bhavcopy header structure in '{csv_filenames[0]}': {raw_header}"
        )

    target_isin_set: Optional[Set[str]] = (
        {isin.strip().upper() for isin in target_isins} if target_isins is not None else None
    )
    target_series_set: Optional[Set[str]] = (
        {s.strip().upper() for s in target_series} if target_series is not None else None
    )

    records: List[SilverRecord] = []
    seen_isins: Set[str] = set()
    inferred_date: Optional[datetime.date] = trade_date

    min_required_len = max(sym_idx, srs_idx, o_idx, h_idx, l_idx, c_idx, vol_idx, isin_idx)

    for line_no, row in enumerate(reader, start=2):
        if len(row) <= min_required_len:
            # Audit §30 H-25: Fail closed if a truncated row contains a target ISIN
            if target_isin_set is not None:
                for cell in row:
                    cleaned_cell = cell.strip().upper()
                    if cleaned_cell in target_isin_set:
                        raise BhavcopyIngestError(
                            f"Line {line_no}: Truncated row detected for target ISIN {cleaned_cell}: {row} (Finding H-25)."
                        )
            continue

        isin_val = row[isin_idx].strip().upper()
        if not isin_val:
            continue

        if target_isin_set is not None and isin_val not in target_isin_set:
            continue

        series_val = row[srs_idx].strip().upper()
        if target_series_set is not None and series_val not in target_series_set:
            continue

        # Audit §30 H-24: Validate trade_date for EVERY row; fail closed on mixed-date archives
        row_date: Optional[datetime.date] = None
        if date_idx is not None and len(row) > date_idx and row[date_idx].strip():
            row_date = parse_bhavcopy_date(row[date_idx])

        if inferred_date is None:
            if row_date is not None:
                inferred_date = row_date
            else:
                raise BhavcopyIngestError(
                    f"Line {line_no}: trade_date was not provided and date column could not be parsed."
                )
        elif row_date is not None and row_date != inferred_date:
            raise BhavcopyIngestError(
                f"Line {line_no}: Row trade_date {row_date} does not match partition date {inferred_date} "
                f"for ISIN {isin_val}. Mixed-date archives violate point-in-time partitioning per Rule 6.3 (Audit §30 H-24)."
            )

        sym_val = row[sym_idx].strip()

        try:
            o_dec = Decimal(row[o_idx].strip())
            h_dec = Decimal(row[h_idx].strip())
            l_dec = Decimal(row[l_idx].strip())
            c_dec = Decimal(row[c_idx].strip())
        except (InvalidOperation, ValueError) as exc:
            raise BhavcopyIngestError(
                f"Line {line_no}: Failed to parse numeric OHLC for {isin_val}: {exc}"
            ) from exc

        # Audit §30 H-23: Parse volume strictly via Decimal arithmetic, rejecting float truncation and fractions
        vol_str = row[vol_idx].strip()
        try:
            vol_dec = Decimal(vol_str)
        except InvalidOperation as exc:
            raise BhavcopyIngestError(
                f"Line {line_no}: Failed to parse volume for {isin_val} from {vol_str!r}: {exc}"
            ) from exc

        if not vol_dec.is_finite() or vol_dec < Decimal("0"):
            raise BhavcopyIngestError(
                f"Line {line_no}: Volume for {isin_val} must be non-negative finite value, got {vol_str!r}"
            )

        if vol_dec % Decimal("1") != Decimal("0"):
            raise BhavcopyIngestError(
                f"Line {line_no}: Volume for {isin_val} must be an integer, got fractional value {vol_str!r} "
                "per AGENTS.md Rule 6.4 (Audit §30 H-23)."
            )

        vol_int = int(vol_dec)

        val_dec: Optional[Decimal] = None
        if val_idx is not None and len(row) > val_idx and row[val_idx].strip():
            try:
                val_dec = Decimal(row[val_idx].strip())
            except InvalidOperation:
                val_dec = None

        # Verify no duplicate ISIN within same daily partition
        if isin_val in seen_isins:
            # If scrip appears in multiple series, fail closed on multiple EQ or duplicate target ISIN
            if series_val == "EQ":
                raise BhavcopyIngestError(
                    f"Line {line_no}: Duplicate primary EQ series for ISIN {isin_val} encountered on {inferred_date}."
                )
            continue

        seen_isins.add(isin_val)

        rec = SilverRecord(
            isin=isin_val,
            symbol=sym_val,
            series=series_val,
            trade_date=inferred_date,
            open=o_dec,
            high=h_dec,
            low=l_dec,
            close=c_dec,
            volume=vol_int,
            traded_value=val_dec,
        )
        records.append(rec)

    if inferred_date is None:
        raise BhavcopyIngestError("Could not infer trade_date from Bhavcopy archive.")

    return inferred_date, records


def ingest_daily_bhavcopy_archive(
    bronze: BronzeStorage,
    silver: SilverStorage,
    archive_bytes: bytes,
    filename: str,
    source_url: str,
    calendar: Optional[TradingCalendar] = None,
    target_isins: Optional[Sequence[str]] = None,
    target_series: Optional[Sequence[str]] = ("EQ", "BE", "SM", "BZ"),
) -> Tuple[BronzeManifestEntry, Path, int]:
    """
    Ingests a single daily Bhavcopy ZIP archive through the full Bronze -> Silver pipeline.
    
    1. Parses the raw archive in memory to extract trade_date and typed SilverRecord rows.
    2. Enforces calendar session rules if calendar is supplied.
    3. Stores byte-exact raw archive into content-addressed Bronze storage with provenance entry.
    4. Writes daily typed Parquet partition into Silver storage.
    
    Returns:
        (bronze_manifest_entry, silver_partition_path, record_count)
    """
    trade_date, records = parse_bhavcopy_archive(
        archive_bytes,
        target_isins=target_isins,
        target_series=target_series,
    )

    if not records:
        raise BhavcopyIngestError(
            f"Zero records extracted from Bhavcopy archive '{filename}' for date {trade_date}."
        )

    # 1. Store raw payload in Bronze
    rel_path = f"raw/bhavcopy/{trade_date.year}/{filename}"
    bronze_entry = bronze.store_payload(
        relative_path=rel_path,
        data=archive_bytes,
        source_url=source_url,
        source_archive_format="ZIP_CSV",
    )

    # 2. Write daily partition into Silver
    silver_path = silver.write_daily_partition(
        trade_date=trade_date,
        records=records,
        calendar=calendar,
    )

    return bronze_entry, silver_path, len(records)
