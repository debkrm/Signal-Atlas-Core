"""
Silver Layer: Typed, Calendar-Checked, Append-Only Daily Parquet Partitions.

Implements storage invariants per AGENTS.md Rule 10.1, Rule 10.4, and Rule 10.6:
- Partitions are keyed by trading session: silver/bhavcopy/{year}/{trade_date}.parquet.
- Record identity is ISIN. Symbols and series are effective-dated attributes.
- Immutability: Partitions are strictly append-only. Rewriting an existing partition raises
  SilverPartitionImmutableError (Gate G2B.5-5).
- Calendar validation: Writing an off-calendar partition or archiving an off-calendar bar raises
  OffCalendarSessionError fail-closed (E-2).
- Exactness: Prices, turnover, and quantities persist as DECIMAL(18, 4) / int64 and read back as exact Decimal (E-4).
- Missing session invariants: Sessions present in the calendar but absent in storage classify
  as PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD (Gate G2B.5-4).
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    _PYARROW_AVAILABLE = False

from signal_core.contracts.exchange_series import PriceSeriesGapType
from signal_core.contracts.price_bar import PriceBar
from signal_core.storage.calendar import TradingCalendar
from signal_core.storage.security_master import SecurityMaster


class SilverStorageError(ValueError):
    """Base exception for silver storage failures."""
    pass


class SilverPartitionImmutableError(SilverStorageError):
    """Raised when an attempt is made to overwrite an existing immutable silver partition (Gate G2B.5-5)."""
    pass


class OffCalendarSessionError(SilverStorageError):
    """Raised when an off-calendar session or bar is written, or found on disk (E-2)."""
    pass


class MissingDependencyError(SilverStorageError):
    """Raised when pyarrow is not installed for silver storage operations."""
    pass


def _require_pyarrow() -> None:
    if not _PYARROW_AVAILABLE:
        raise MissingDependencyError(
            "pyarrow is required for Silver storage operations. Install via 'pip install pyarrow' or '.[storage]'."
        )


@dataclass(frozen=True, slots=True)
class SilverRecord:
    """
    Typed record representing a single instrument's session observation in a Silver partition.
    """
    isin: str
    symbol: str
    series: str
    trade_date: datetime.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    traded_value: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if not isinstance(self.isin, str) or not self.isin.strip():
            raise SilverStorageError("isin must be a non-empty string.")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise SilverStorageError("symbol must be a non-empty string.")
        if not isinstance(self.series, str) or not self.series.strip():
            raise SilverStorageError("series must be a non-empty string.")
        if type(self.trade_date) is not datetime.date:
            raise SilverStorageError("trade_date must be a genuine datetime.date.")
        for name, val in [("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)]:
            if not isinstance(val, Decimal) or not val.is_finite() or val <= Decimal("0"):
                raise SilverStorageError(f"{name} must be a strictly positive finite Decimal, got {val}")
        # OHLC coherence check (E-13)
        if not (self.low <= self.open <= self.high):
            raise SilverStorageError(f"Incoherent OHLC: open ({self.open}) must be within [low={self.low}, high={self.high}]")
        if not (self.low <= self.close <= self.high):
            raise SilverStorageError(f"Incoherent OHLC: close ({self.close}) must be within [low={self.low}, high={self.high}]")

        if not isinstance(self.volume, int) or isinstance(self.volume, bool) or self.volume < 0:
            raise SilverStorageError(f"volume must be a non-negative integer, got {self.volume}")
        if self.traded_value is not None:
            if not isinstance(self.traded_value, Decimal) or not self.traded_value.is_finite() or self.traded_value < Decimal("0"):
                raise SilverStorageError(f"traded_value must be a non-negative finite Decimal, got {self.traded_value}")

    def to_price_bar(self, session_type: Optional[str] = None) -> PriceBar:
        """Converts SilverRecord to immutable PriceBar contract using isin as instrument_id."""
        return PriceBar(
            instrument_id=self.isin,
            trade_date=self.trade_date,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            traded_value=self.traded_value,
            session_type=session_type,
        )


class SilverStorage:
    """
    Manages typed daily Parquet partitions partitioned by year and session date:
    {root_dir}/bhavcopy/{year}/{trade_date}.parquet
    """
    def __init__(
        self,
        root_dir: Union[str, Path],
        calendar: Optional[TradingCalendar] = None,
    ) -> None:
        self._root_dir = Path(root_dir).resolve()
        self._calendar = calendar
        self._bhavcopy_dir = self._root_dir / "bhavcopy"
        self._bhavcopy_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def bhavcopy_dir(self) -> Path:
        return self._bhavcopy_dir

    @property
    def calendar(self) -> Optional[TradingCalendar]:
        return self._calendar

    def get_partition_path(self, trade_date: datetime.date) -> Path:
        """Returns standard path for a daily session partition."""
        year_dir = self._bhavcopy_dir / str(trade_date.year)
        return year_dir / f"{trade_date.isoformat()}.parquet"

    def partition_exists(self, trade_date: datetime.date) -> bool:
        """Checks if a silver partition exists for trade_date."""
        return self.get_partition_path(trade_date).is_file()

    def write_daily_partition(
        self,
        trade_date: datetime.date,
        records: Sequence[SilverRecord],
        calendar: Optional[TradingCalendar] = None,
    ) -> Path:
        """
        Writes a daily partition to Parquet format.
        Fails closed with:
        - SilverPartitionImmutableError if partition already exists (Gate G2B.5-5).
        - OffCalendarSessionError if date or any record is off-calendar (E-2).
        """
        _require_pyarrow()

        if type(trade_date) is not datetime.date:
            raise SilverStorageError(f"trade_date must be genuine datetime.date, got {type(trade_date).__name__}")
        if not records:
            raise SilverStorageError(f"Cannot write empty partition for {trade_date}")

        # Calendar validation at write time (E-2)
        active_cal = calendar or self._calendar
        if active_cal is not None:
            if not active_cal.is_session(trade_date):
                raise OffCalendarSessionError(
                    f"Cannot write silver partition for off-calendar session {trade_date}. "
                    f"Not an authoritative session in calendar {active_cal.calendar_id}."
                )

        partition_path = self.get_partition_path(trade_date)
        if partition_path.exists():
            raise SilverPartitionImmutableError(
                f"Silver partition for {trade_date} already exists at {partition_path}. "
                "Updating or overwriting existing silver partitions is strictly prohibited per AGENTS.md Rule 10.1."
            )

        partition_path.parent.mkdir(parents=True, exist_ok=True)

        # Build columnar arrays using Decimal128(18, 4) to preserve precision across boundaries (E-4)
        isins: List[str] = []
        symbols: List[str] = []
        series_list: List[str] = []
        dates: List[datetime.date] = []
        opens: List[Decimal] = []
        highs: List[Decimal] = []
        lows: List[Decimal] = []
        closes: List[Decimal] = []
        volumes: List[int] = []
        traded_values: List[Optional[Decimal]] = []

        seen_isins: Set[str] = set()
        for r in records:
            if r.trade_date != trade_date:
                raise SilverStorageError(
                    f"Record trade_date {r.trade_date} does not match partition date {trade_date} for ISIN {r.isin}"
                )
            if active_cal is not None and not active_cal.is_session(r.trade_date):
                raise OffCalendarSessionError(
                    f"Record trade_date {r.trade_date} for ISIN {r.isin} is an off-calendar date."
                )
            if r.isin in seen_isins:
                raise SilverStorageError(f"Duplicate ISIN {r.isin} in daily partition for {trade_date}")
            seen_isins.add(r.isin)

            isins.append(r.isin)
            symbols.append(r.symbol)
            series_list.append(r.series)
            dates.append(r.trade_date)
            opens.append(r.open)
            highs.append(r.high)
            lows.append(r.low)
            closes.append(r.close)
            volumes.append(r.volume)
            traded_values.append(r.traded_value)

        table = pa.Table.from_arrays(
            [
                pa.array(isins, type=pa.string()),
                pa.array(symbols, type=pa.string()),
                pa.array(series_list, type=pa.string()),
                pa.array(dates, type=pa.date32()),
                pa.array(opens, type=pa.decimal128(18, 4)),
                pa.array(highs, type=pa.decimal128(18, 4)),
                pa.array(lows, type=pa.decimal128(18, 4)),
                pa.array(closes, type=pa.decimal128(18, 4)),
                pa.array(volumes, type=pa.int64()),
                pa.array(traded_values, type=pa.decimal128(18, 4)),
            ],
            names=[
                "isin",
                "symbol",
                "series",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "traded_value",
            ],
        )

        # Atomic write
        temp_file = partition_path.with_suffix(f".tmp_{os.getpid()}_{datetime.datetime.now().timestamp()}.parquet")
        try:
            pq.write_table(table, temp_file, compression="SNAPPY")
            temp_file.replace(partition_path)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

        return partition_path

    def read_daily_partition(self, trade_date: datetime.date) -> Tuple[SilverRecord, ...]:
        """Reads daily partition and returns typed SilverRecord instances."""
        _require_pyarrow()

        partition_path = self.get_partition_path(trade_date)
        if not partition_path.is_file():
            raise FileNotFoundError(f"No silver partition found for date {trade_date} at {partition_path}")

        table = pq.read_table(partition_path)
        records: List[SilverRecord] = []

        isin_col = table["isin"].to_pylist()
        symbol_col = table["symbol"].to_pylist()
        series_col = table["series"].to_pylist()
        date_col = table["trade_date"].to_pylist()
        open_col = table["open"].to_pylist()
        high_col = table["high"].to_pylist()
        low_col = table["low"].to_pylist()
        close_col = table["close"].to_pylist()
        vol_col = table["volume"].to_pylist()
        tv_col = table["traded_value"].to_pylist()

        for i in range(len(isin_col)):
            raw_d = date_col[i]
            d = raw_d if isinstance(raw_d, datetime.date) else datetime.date.fromisoformat(str(raw_d))
            raw_tv = tv_col[i]
            tv = Decimal(str(raw_tv)) if raw_tv is not None else None
            records.append(
                SilverRecord(
                    isin=str(isin_col[i]),
                    symbol=str(symbol_col[i]),
                    series=str(series_col[i]),
                    trade_date=d,
                    open=Decimal(str(open_col[i])),
                    high=Decimal(str(high_col[i])),
                    low=Decimal(str(low_col[i])),
                    close=Decimal(str(close_col[i])),
                    volume=int(vol_col[i]),
                    traded_value=tv,
                )
            )

        return tuple(records)

    def read_instrument_series_with_calendar_validation(
        self,
        isin: str,
        start_date: datetime.date,
        end_date: datetime.date,
        calendar: TradingCalendar,
        security_master: Optional[SecurityMaster] = None,
    ) -> Tuple[Tuple[PriceBar, ...], Tuple[Tuple[datetime.date, PriceSeriesGapType], ...]]:
        """
        Reads continuous price series for ISIN across trading sessions in [start_date, end_date].
        Validates every expected trading session in calendar against storage:
        - If an off-calendar partition exists on disk within [start_date, end_date]: raises OffCalendarSessionError (E-2).
        - If a session is present in calendar but absent in storage: classifies as UNEXPLAINED_MISSING_RECORD (Gate G2B.5-4).
        - If security was delisted or transitioned, classifies appropriately.
        - Fails closed: Never forward-fills, never linearly interpolates, never masks with NaN.
        """
        # Audit on-disk partitions within [start_date, end_date] to reject off-calendar storage fail-closed (E-2)
        if self._bhavcopy_dir.exists():
            for p_file in self._bhavcopy_dir.glob("*/*.parquet"):
                try:
                    p_date = datetime.date.fromisoformat(p_file.stem)
                except ValueError:
                    continue
                if start_date <= p_date <= end_date and not calendar.is_session(p_date):
                    raise OffCalendarSessionError(
                        f"Found archived silver partition for off-calendar date {p_date} on disk ({p_file}). "
                        "Archiving price bars outside authoritative trading calendar fails closed per AGENTS.md Rule 6.3."
                    )

        expected_sessions = calendar.sessions_in_range(start_date, end_date)
        bars: List[PriceBar] = []
        gaps: List[Tuple[datetime.date, PriceSeriesGapType]] = []

        for s in expected_sessions:
            # Check security master state if provided
            if security_master is not None:
                if security_master.is_delisted(isin, s):
                    gaps.append((s, PriceSeriesGapType.VERIFIED_CORPORATE_ACTION_DELISTING))
                    continue
                if security_master.is_transitioned_out(isin, s):
                    gaps.append((s, PriceSeriesGapType.VERIFIED_ISIN_TRANSITION))
                    continue
                if not security_master.is_active(isin, s):
                    gaps.append((s, PriceSeriesGapType.OUTSIDE_VERIFIED_LISTING_INTERVAL))
                    continue

            if not self.partition_exists(s):
                # Partition entirely missing for this calendar date!
                gaps.append((s, PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD))
                continue

            # Read partition
            records = self.read_daily_partition(s)
            matching = [r for r in records if r.isin == isin]
            if not matching:
                # Scrip missing from day's partition without documented explanation
                gaps.append((s, PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD))
            else:
                bars.append(matching[0].to_price_bar())

        return tuple(bars), tuple(gaps)
