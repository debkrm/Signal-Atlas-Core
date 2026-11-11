"""Point-in-Time Universe Schedule Contract.

Provides immutable representations of daily universe eligibility mappings.
Guarantees deterministic membership ordering, explicit interval and date query
semantics, and strict validation rejecting duplicates and whitespace corruption.
"""

from dataclasses import dataclass
import datetime
from types import MappingProxyType
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple


class UniverseValidationError(ValueError):
    """Raised when universe membership data violates structure or boundary rules."""
    pass


FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


@dataclass(frozen=True, slots=True)
class UniverseInterval:
    """
    Represents an instrument's inclusion over an explicit, closed (inclusive) date interval.

    Interval boundary semantics:
    - start_date <= date <= end_date (both boundaries inclusive).
    """
    instrument_id: str
    start_date: datetime.date
    end_date: datetime.date

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str):
            raise UniverseValidationError(f"instrument_id must be a string, got {type(self.instrument_id).__name__}.")
        if not self.instrument_id:
            raise UniverseValidationError("instrument_id cannot be empty.")
        if self.instrument_id != self.instrument_id.strip():
            raise UniverseValidationError(
                f"instrument_id '{self.instrument_id}' contains leading or trailing whitespace."
            )
        if any(c in self.instrument_id for c in FORBIDDEN_CHARACTERS):
            raise UniverseValidationError(
                f"instrument_id '{self.instrument_id}' contains forbidden delimiter or newline characters."
            )

        if type(self.start_date) is not datetime.date:
            raise UniverseValidationError(
                f"start_date must be a genuine datetime.date, got {type(self.start_date).__name__}."
            )
        if type(self.end_date) is not datetime.date:
            raise UniverseValidationError(
                f"end_date must be a genuine datetime.date, got {type(self.end_date).__name__}."
            )
        if self.start_date > self.end_date:
            raise UniverseValidationError(
                f"Invalid date interval: start_date ({self.start_date}) cannot be after end_date ({self.end_date})."
            )

    def contains(self, query_date: datetime.date) -> bool:
        """Returns True if query_date is within [start_date, end_date] inclusive."""
        if type(query_date) is not datetime.date:
            raise UniverseValidationError(f"query_date must be a genuine datetime.date, got {type(query_date).__name__}.")
        return self.start_date <= query_date <= self.end_date


class UniverseSchedule:
    """
    Immutable Point-in-Time Universe Schedule.

    Maps discrete trading dates to deterministic, sorted, immutable tuples of
    eligible instrument identifiers.

    Strict Validation Rules:
    - Dates must be genuine datetime.date instances (strictly rejecting datetime.datetime).
    - Instrument IDs must be exact strings without leading/trailing whitespace.
    - Silent deduplication is PROHIBITED: duplicate instrument IDs on any date raise UniverseValidationError.
    - Silent whitespace stripping is PROHIBITED: whitespace-padded strings raise UniverseValidationError.
    - Delimiter characters (',', ';', '\\n', '\\r', '\\t') are strictly prohibited.
    - Immutable read-only encapsulation via MappingProxyType and immutable tuples.
    """
    def __init__(self, schedule: Mapping[datetime.date, Iterable[str]]):
        if not schedule:
            raise UniverseValidationError("Universe schedule mapping cannot be empty.")

        clean_schedule: Dict[datetime.date, Tuple[str, ...]] = {}
        all_instruments: Set[str] = set()

        for d in sorted(schedule.keys()):
            if type(d) is not datetime.date:
                raise UniverseValidationError(
                    f"Schedule date key must be a genuine datetime.date instance (got {type(d).__name__}). "
                    "datetime.datetime instances are strictly rejected."
                )

            raw_members = schedule[d]
            seen_on_date: Set[str] = set()
            members_list = []

            for m in raw_members:
                if not isinstance(m, str):
                    raise UniverseValidationError(f"Instrument identifier on date {d} must be a string, got {type(m).__name__}.")
                if not m:
                    raise UniverseValidationError(f"Empty instrument identifier on date {d} is prohibited.")
                if m != m.strip():
                    raise UniverseValidationError(
                        f"Instrument identifier '{m}' on date {d} contains leading or trailing whitespace. "
                        "Silent modification is prohibited; clean identifiers must be supplied."
                    )
                if any(c in m for c in FORBIDDEN_CHARACTERS):
                    raise UniverseValidationError(
                        f"Instrument identifier '{m}' on date {d} contains forbidden delimiter or newline characters."
                    )
                if m in seen_on_date:
                    raise UniverseValidationError(
                        f"Duplicate instrument '{m}' detected on date {d}. "
                        "Silent deduplication is prohibited; universe inputs must be distinct."
                    )
                seen_on_date.add(m)
                members_list.append(m)

            sorted_tuple = tuple(sorted(members_list))
            clean_schedule[d] = sorted_tuple
            all_instruments.update(sorted_tuple)

        self._schedule: Mapping[datetime.date, Tuple[str, ...]] = MappingProxyType(clean_schedule)
        self._all_instruments: Tuple[str, ...] = tuple(sorted(all_instruments))
        self._dates: Tuple[datetime.date, ...] = tuple(sorted(clean_schedule.keys()))

    @property
    def dates(self) -> Tuple[datetime.date, ...]:
        """All trading dates covered by this universe schedule in chronological order."""
        return self._dates

    @property
    def start_date(self) -> datetime.date:
        """First trading date in the universe schedule."""
        return self._dates[0]

    @property
    def end_date(self) -> datetime.date:
        """Last trading date in the universe schedule."""
        return self._dates[-1]

    @property
    def session_count(self) -> int:
        """Total number of scheduled trading sessions."""
        return len(self._dates)

    @property
    def unique_instruments(self) -> Tuple[str, ...]:
        """All unique instruments eligible at any point in the schedule, lexicographically sorted."""
        return self._all_instruments

    def get_universe_for_date(self, trade_date: datetime.date) -> Tuple[str, ...]:
        """
        Returns the sorted, immutable tuple of instrument identifiers eligible on trade_date.
        If the date is not in the schedule, returns an empty tuple ().
        """
        if type(trade_date) is not datetime.date:
            raise UniverseValidationError(f"trade_date must be a genuine datetime.date, got {type(trade_date).__name__}.")
        return self._schedule.get(trade_date, ())

    def is_in_universe(self, instrument_id: str, trade_date: datetime.date) -> bool:
        """Returns True if instrument_id is a member of the universe on trade_date."""
        if type(trade_date) is not datetime.date:
            raise UniverseValidationError(f"trade_date must be a genuine datetime.date, got {type(trade_date).__name__}.")
        members = self._schedule.get(trade_date, ())
        return instrument_id in members

    def to_dict(self) -> Dict[datetime.date, Tuple[str, ...]]:
        """Returns a standard dictionary copy of the daily membership schedule."""
        return dict(self._schedule)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UniverseSchedule):
            return False
        return self._schedule == other._schedule

    def __hash__(self) -> int:
        return hash(self._dates)
