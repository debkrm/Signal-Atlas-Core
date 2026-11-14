"""
Authoritative Trading Calendar Contract and Loader for Indian Financial Markets.

Implements exchange calendar invariants per AGENTS.md Rule 6.3, Rule 10.7, and Rule 10.8:
- Authoritative daily session schedule mapping official NSE trading sessions.
- Detailed session typing (FULL / MUHURAT / SPECIAL) with open and close times.
- Inclusion of all special weekend/budget sessions and Diwali Muhurat trading sessions.
- Full provenance metadata block (source, retrieval timestamp, circular references, SHA-256).
- Annual session count completeness assertions.
- Monotonic, disjoint, duplicate-free calendar validation.
- Distinct partition between Warm-up (2015-01-01 to 2018-03-31) and Binding (2018-04-01 to 2026-11-11).
- Cryptographic fingerprinting (CAL-FPR-V1) for content addressing and provenance audit.
"""

from dataclasses import dataclass
import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

DEFAULT_CALENDAR_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "trading_calendar_nse.json"
BINDING_EVALUATION_START_DATE = datetime.date(2018, 4, 1)


class CalendarError(ValueError):
    """Base exception for calendar errors and invariants violations."""
    pass


class InvalidSessionError(CalendarError):
    """Raised when a date is not an authoritative trading session or violates ordering."""
    pass


class SessionType(str, Enum):
    """Classification of exchange trading sessions."""
    FULL = "FULL"          # Regular full-day trading session (09:15 - 15:30)
    MUHURAT = "MUHURAT"    # Special Diwali evening Muhurat trading session (~1 hour)
    SPECIAL = "SPECIAL"    # Special live trading session (e.g. Budget Saturday, DR site test)


@dataclass(frozen=True, slots=True)
class TradingSessionRecord:
    """
    Detailed descriptor for an individual exchange trading session.
    """
    date: datetime.date
    session_type: SessionType
    open_time: datetime.time
    close_time: datetime.time
    description: str

    def __post_init__(self) -> None:
        if type(self.date) is not datetime.date:
            raise CalendarError(f"date must be exact datetime.date, got {type(self.date).__name__}")
        if not isinstance(self.session_type, SessionType):
            raise CalendarError(f"session_type must be a SessionType enum, got {type(self.session_type).__name__}")
        if not isinstance(self.open_time, datetime.time):
            raise CalendarError(f"open_time must be datetime.time, got {type(self.open_time).__name__}")
        if not isinstance(self.close_time, datetime.time):
            raise CalendarError(f"close_time must be datetime.time, got {type(self.close_time).__name__}")
        if self.open_time >= self.close_time:
            raise CalendarError(f"open_time ({self.open_time}) must precede close_time ({self.close_time})")


def compute_calendar_fingerprint(
    sessions: Sequence[Union[TradingSessionRecord, datetime.date]]
) -> str:
    """
    Computes deterministic SHA-256 fingerprint covering dates, session types, and open/close hours (CAL-FPR-V1).
    Distinguishes a 1-hour evening Muhurat session from a full trading day (F-2).
    """
    items = []
    for s in sessions:
        if isinstance(s, TradingSessionRecord):
            items.append(f"{s.date.isoformat()}:{s.session_type.value}:{s.open_time.isoformat()}:{s.close_time.isoformat()}")
        elif isinstance(s, datetime.date):
            items.append(f"{s.isoformat()}:FULL:09:15:00:15:30:00")
        else:
            raise CalendarError(f"Unsupported session item type: {type(s)}")
    canonical_repr = ",".join(items)
    digest = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()
    return f"CAL-FPR-V1-{digest}"


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """
    Immutable representation of the authoritative exchange trading calendar.
    """
    calendar_id: str
    market: str
    session_records: Tuple[TradingSessionRecord, ...]
    binding_start_date: datetime.date
    fingerprint: str
    provenance: Mapping[str, Any]
    annual_session_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if not self.session_records:
            raise CalendarError("Trading calendar must contain at least one session.")

        # Validate monotonicity and absence of duplicates
        prev_date = self.session_records[0].date
        for curr in self.session_records[1:]:
            curr_date = curr.date
            if curr_date <= prev_date:
                raise CalendarError(
                    f"Non-monotonic or duplicate calendar dates detected: {prev_date} followed by {curr_date}"
                )
            prev_date = curr_date

        # Reconcile annual session counts against actual sessions per Finding H-61
        actual_counts: Dict[str, int] = {}
        for r in self.session_records:
            y_str = str(r.date.year)
            actual_counts[y_str] = actual_counts.get(y_str, 0) + 1

        for y_str, declared in self.annual_session_counts.items():
            actual = actual_counts.get(str(y_str), 0)
            if actual != int(declared):
                raise CalendarError(
                    f"Calendar annual session count mismatch for year {y_str}: "
                    f"declared {declared} != actual {actual} sessions (Finding H-61)."
                )

        for y_str, actual in actual_counts.items():
            if y_str not in self.annual_session_counts:
                raise CalendarError(
                    f"Calendar contains {actual} sessions in year {y_str} not tracked in annual_session_counts (Finding H-61)."
                )

    @property
    def sessions(self) -> Tuple[datetime.date, ...]:
        """Ordered tuple of all session dates."""
        return tuple(r.date for r in self.session_records)

    @property
    def start_date(self) -> datetime.date:
        return self.session_records[0].date

    @property
    def end_date(self) -> datetime.date:
        return self.session_records[-1].date

    @property
    def total_sessions(self) -> int:
        return len(self.session_records)

    def get_session(self, query_date: datetime.date) -> Optional[TradingSessionRecord]:
        """Returns the TradingSessionRecord for query_date if present, else None."""
        if type(query_date) is not datetime.date:
            raise CalendarError(f"query_date must be exact datetime.date, got {type(query_date).__name__}")
        for r in self.session_records:
            if r.date == query_date:
                return r
            if r.date > query_date:
                break
        return None

    def is_session(self, query_date: datetime.date) -> bool:
        """Returns True if query_date is an authoritative exchange trading session."""
        return self.get_session(query_date) is not None

    def is_binding_session(self, query_date: datetime.date) -> bool:
        """Returns True if query_date is an authoritative session on or after binding start (2018-04-01)."""
        return self.is_session(query_date) and query_date >= self.binding_start_date

    def session_records_in_range(
        self,
        start: datetime.date,
        end: datetime.date,
        full_sessions_only: bool = False,
    ) -> Tuple[TradingSessionRecord, ...]:
        """
        Returns ordered tuple of TradingSessionRecord within [start, end] inclusive.
        If full_sessions_only=True, filters out Muhurat and Special sessions (F-3).
        """
        if type(start) is not datetime.date:
            raise CalendarError(f"start must be exact datetime.date, got {type(start).__name__}")
        if type(end) is not datetime.date:
            raise CalendarError(f"end must be exact datetime.date, got {type(end).__name__}")
        if start > end:
            raise CalendarError(f"start date {start} cannot be after end date {end}")
        records = [r for r in self.session_records if start <= r.date <= end]
        if full_sessions_only:
            records = [r for r in records if r.session_type == SessionType.FULL]
        return tuple(records)

    def sessions_in_range(
        self,
        start: datetime.date,
        end: datetime.date,
        full_sessions_only: bool = False,
    ) -> Tuple[datetime.date, ...]:
        """Returns ordered tuple of trading session dates within [start, end] inclusive."""
        return tuple(r.date for r in self.session_records_in_range(start, end, full_sessions_only=full_sessions_only))

    def session_count_between(self, start: datetime.date, end: datetime.date) -> int:
        """Counts trading sessions in [start, end] inclusive."""
        return len(self.sessions_in_range(start, end))

    def advance_sessions(self, from_date: datetime.date, n: int) -> datetime.date:
        """
        Advances n trading sessions from from_date.
        If n > 0, advances forward. If n < 0, steps backward.
        If from_date is not in calendar, raises InvalidSessionError.
        """
        if type(from_date) is not datetime.date:
            raise CalendarError(f"from_date must be exact datetime.date, got {type(from_date).__name__}")
        if not isinstance(n, int) or isinstance(n, bool):
            raise CalendarError(f"n must be an integer, got {type(n)}")

        dates = self.sessions
        try:
            idx = dates.index(from_date)
        except ValueError:
            raise InvalidSessionError(f"from_date {from_date} is not an authoritative trading session.")

        target_idx = idx + n
        if target_idx < 0 or target_idx >= len(dates):
            raise InvalidSessionError(
                f"Advancing {n} sessions from {from_date} (index {idx}) exceeds calendar bounds [0, {len(dates)-1}]."
            )
        return dates[target_idx]

    def next_session(self, date: datetime.date) -> datetime.date:
        """Returns the next trading session immediately following date."""
        return self.advance_sessions(date, 1)

    def previous_session(self, date: datetime.date) -> datetime.date:
        """Returns the previous trading session immediately preceding date."""
        return self.advance_sessions(date, -1)

    def assert_year_completeness(self, year: int) -> None:
        """Asserts that the loaded calendar matches expected session counts for year."""
        year_str = str(year)
        if year_str not in self.annual_session_counts:
            raise CalendarError(f"Year {year} is not tracked in annual session counts.")
        expected = self.annual_session_counts[year_str]
        actual = len([r for r in self.session_records if r.date.year == year])
        if actual != expected:
            raise CalendarError(f"Annual session count mismatch for {year}: expected {expected}, actual {actual}")


def load_nse_trading_calendar(path: Optional[Union[str, Path]] = None) -> TradingCalendar:
    """
    Loads and validates the committed NSE trading calendar JSON file into typed immutable contract.
    Fails closed if dates are corrupt, non-monotonic, missing, or lack provenance.
    """
    file_path = Path(path) if path else DEFAULT_CALENDAR_PATH
    if not file_path.is_file():
        raise FileNotFoundError(f"Trading calendar configuration not found at: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise CalendarError(f"Invalid calendar JSON format in {file_path}. Must be a dictionary.")

    provenance = data.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source"):
        raise CalendarError(f"Calendar file {file_path} lacks mandatory provenance metadata block.")

    annual_counts = data.get("annual_session_counts", {})
    if not isinstance(annual_counts, dict) or not annual_counts:
        raise CalendarError(f"Calendar file {file_path} lacks annual_session_counts metadata.")

    raw_session_records = data.get("session_records")
    session_records_list = []

    if isinstance(raw_session_records, list) and raw_session_records:
        for item in raw_session_records:
            d = datetime.date.fromisoformat(item["date"])
            st = SessionType(item.get("session_type", "FULL"))
            ot = datetime.time.fromisoformat(item.get("open_time", "09:15:00"))
            ct = datetime.time.fromisoformat(item.get("close_time", "15:30:00"))
            desc = str(item.get("description", "Trading Session"))
            session_records_list.append(
                TradingSessionRecord(
                    date=d,
                    session_type=st,
                    open_time=ot,
                    close_time=ct,
                    description=desc,
                )
            )
    else:
        # Fallback from flat dates list if session_records not present
        raw_sessions = data.get("sessions", [])
        if not isinstance(raw_sessions, list) or not raw_sessions:
            raise CalendarError("Calendar must contain a non-empty 'sessions' or 'session_records' list.")
        for s_str in raw_sessions:
            d = datetime.date.fromisoformat(s_str)
            session_records_list.append(
                TradingSessionRecord(
                    date=d,
                    session_type=SessionType.FULL,
                    open_time=datetime.time(9, 15, 0),
                    close_time=datetime.time(15, 30, 0),
                    description="Regular Trading Session",
                )
            )

    session_records_tuple = tuple(session_records_list)
    dates_tuple = tuple(r.date for r in session_records_tuple)
    fingerprint = compute_calendar_fingerprint(session_records_tuple)
    expected_digest = fingerprint.replace("CAL-FPR-V1-", "")

    # Audit §30 H-26: Reconcile declared provenance SHA-256 against actual session content digest
    prov_sha256 = provenance.get("sha256")
    if prov_sha256 is not None and prov_sha256.lower() != expected_digest.lower():
        raise CalendarError(
            f"Calendar provenance sha256 mismatch in {file_path}: declared {prov_sha256!r} != "
            f"computed session content digest {expected_digest!r} per AGENTS.md Rule 6.5 (Audit §30 H-26)."
        )

    binding_start_raw = data.get("binding_start_date", "2018-04-01")
    binding_start = datetime.date.fromisoformat(binding_start_raw)

    calendar = TradingCalendar(
        calendar_id=str(data.get("calendar_id", "NSE-TRADING-CALENDAR")),
        market=str(data.get("market", "NSE_CASH_EQUITY")),
        session_records=session_records_tuple,
        binding_start_date=binding_start,
        fingerprint=fingerprint,
        provenance=provenance,
        annual_session_counts={str(k): int(v) for k, v in annual_counts.items()},
    )

    return calendar
