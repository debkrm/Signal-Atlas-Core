"""
Authoritative Trading Calendar Contract and Loader for Indian Financial Markets.

Implements exchange calendar invariants per AGENTS.md Rule 6.3 and Rule 10.8:
- Authoritative daily session schedule mapping official NSE trading sessions.
- Monotonic, disjoint, duplicate-free calendar validation.
- Distinct partition between Warm-up (2015-01-01 to 2018-03-31) and Binding (2018-04-01 to 2026-11-11).
- Cryptographic fingerprinting (CAL-FPR-V1) for content addressing and provenance audit.
"""

from dataclasses import dataclass
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

DEFAULT_CALENDAR_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "trading_calendar_nse.json"
BINDING_EVALUATION_START_DATE = datetime.date(2018, 4, 1)


class CalendarError(ValueError):
    """Base exception for calendar errors and invariants violations."""
    pass


class InvalidSessionError(CalendarError):
    """Raised when a date is not an authoritative trading session or violates ordering."""
    pass


def compute_calendar_fingerprint(sessions: Sequence[datetime.date]) -> str:
    """Computes deterministic SHA-256 fingerprint for a sequence of trading dates."""
    canonical_repr = ",".join(s.isoformat() for s in sessions)
    digest = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()
    return f"CAL-FPR-V1-{digest}"


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """
    Immutable representation of the authoritative exchange trading calendar.
    """
    calendar_id: str
    market: str
    sessions: Tuple[datetime.date, ...]
    binding_start_date: datetime.date
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.sessions:
            raise CalendarError("Trading calendar must contain at least one session.")
        # Validate monotonicity and absence of duplicates
        prev = self.sessions[0]
        if not isinstance(prev, datetime.date) or isinstance(prev, datetime.datetime):
            raise CalendarError(f"Session elements must be exact datetime.date, got {type(prev)}")
        for curr in self.sessions[1:]:
            if not isinstance(curr, datetime.date) or isinstance(curr, datetime.datetime):
                raise CalendarError(f"Session elements must be exact datetime.date, got {type(curr)}")
            if curr <= prev:
                raise CalendarError(
                    f"Non-monotonic or duplicate calendar dates detected: {prev} followed by {curr}"
                )
            prev = curr

    @property
    def start_date(self) -> datetime.date:
        return self.sessions[0]

    @property
    def end_date(self) -> datetime.date:
        return self.sessions[-1]

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    def is_session(self, query_date: datetime.date) -> bool:
        """Returns True if query_date is an authoritative exchange trading session."""
        if not isinstance(query_date, datetime.date) or isinstance(query_date, datetime.datetime):
            raise CalendarError(f"query_date must be exact datetime.date, got {type(query_date)}")
        return query_date in self.sessions

    def is_binding_session(self, query_date: datetime.date) -> bool:
        """Returns True if query_date is an authoritative session on or after binding start (2018-04-01)."""
        return self.is_session(query_date) and query_date >= self.binding_start_date

    def sessions_in_range(self, start: datetime.date, end: datetime.date) -> Tuple[datetime.date, ...]:
        """Returns ordered tuple of trading sessions within [start, end] inclusive."""
        if not isinstance(start, datetime.date) or isinstance(start, datetime.datetime):
            raise CalendarError(f"start must be exact datetime.date, got {type(start)}")
        if not isinstance(end, datetime.date) or isinstance(end, datetime.datetime):
            raise CalendarError(f"end must be exact datetime.date, got {type(end)}")
        if start > end:
            raise CalendarError(f"start date {start} cannot be after end date {end}")
        return tuple(s for s in self.sessions if start <= s <= end)

    def session_count_between(self, start: datetime.date, end: datetime.date) -> int:
        """Counts trading sessions in [start, end] inclusive."""
        return len(self.sessions_in_range(start, end))

    def advance_sessions(self, from_date: datetime.date, n: int) -> datetime.date:
        """
        Advances n trading sessions from from_date.
        If n > 0, advances forward. If n < 0, steps backward.
        If from_date is not in calendar, raises InvalidSessionError.
        """
        if not isinstance(from_date, datetime.date) or isinstance(from_date, datetime.datetime):
            raise CalendarError(f"from_date must be exact datetime.date, got {type(from_date)}")
        if not isinstance(n, int) or isinstance(n, bool):
            raise CalendarError(f"n must be an integer, got {type(n)}")

        try:
            idx = self.sessions.index(from_date)
        except ValueError:
            raise InvalidSessionError(f"from_date {from_date} is not an authoritative trading session.")

        target_idx = idx + n
        if target_idx < 0 or target_idx >= len(self.sessions):
            raise InvalidSessionError(
                f"Advancing {n} sessions from {from_date} (index {idx}) exceeds calendar bounds [0, {len(self.sessions)-1}]."
            )
        return self.sessions[target_idx]

    def next_session(self, date: datetime.date) -> datetime.date:
        """Returns the next trading session immediately following date."""
        return self.advance_sessions(date, 1)

    def previous_session(self, date: datetime.date) -> datetime.date:
        """Returns the previous trading session immediately preceding date."""
        return self.advance_sessions(date, -1)


def load_nse_trading_calendar(path: Optional[Union[str, Path]] = None) -> TradingCalendar:
    """
    Loads and validates the committed NSE trading calendar JSON file into typed immutable contract.
    Fails closed if dates are corrupt, non-monotonic, or missing.
    """
    file_path = Path(path) if path else DEFAULT_CALENDAR_PATH
    if not file_path.is_file():
        raise FileNotFoundError(f"Trading calendar configuration not found at: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise CalendarError(f"Invalid calendar JSON format in {file_path}. Must be a dictionary.")

    raw_sessions = data.get("sessions", [])
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise CalendarError("Calendar must contain a non-empty 'sessions' list.")

    parsed_dates = []
    for s_str in raw_sessions:
        if not isinstance(s_str, str):
            raise CalendarError(f"Session entry must be ISO date string, got {type(s_str)}: {s_str!r}")
        try:
            d = datetime.date.fromisoformat(s_str)
        except ValueError as exc:
            raise CalendarError(f"Invalid ISO date string {s_str!r}") from exc
        parsed_dates.append(d)

    sessions_tuple = tuple(parsed_dates)
    fingerprint = compute_calendar_fingerprint(sessions_tuple)

    binding_start_raw = data.get("binding_start_date", "2018-04-01")
    binding_start = datetime.date.fromisoformat(binding_start_raw)

    return TradingCalendar(
        calendar_id=str(data.get("calendar_id", "NSE-TRADING-CALENDAR")),
        market=str(data.get("market", "NSE_CASH_EQUITY")),
        sessions=sessions_tuple,
        binding_start_date=binding_start,
        fingerprint=fingerprint,
    )
