"""Point-in-Time Universe Schedule Contract.

Provides immutable representations of daily universe eligibility mappings.
Guarantees deterministic membership ordering, explicit interval and date query
semantics, and strict validation rejecting duplicates and whitespace corruption.
"""

from dataclasses import dataclass
import datetime
from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple


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


@dataclass(frozen=True, slots=True)
class IndexMembershipInterval:
    """
    Effective-dated interval representing an instrument's inclusion in an index or universe.
    Frozen ingest contract per AGENTS.md Rule 10.4, Rule 10.5 and Wave 0.

    Interval semantics: half-open [effective_from, effective_to).
    - If effective_to is None, the membership is currently active / open-ended.
    - Identity is ISIN, never symbol (Rule 10.4).
    """
    index_name: str
    isin: str
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None
    circular_ref: Optional[str] = None
    source_publication: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.index_name, bool) or not isinstance(self.index_name, str) or not self.index_name.strip():
            raise UniverseValidationError(f"index_name must be a non-empty string, got {self.index_name!r}")
        if any(c in self.index_name for c in FORBIDDEN_CHARACTERS):
            raise UniverseValidationError(f"index_name '{self.index_name}' contains forbidden characters.")
        object.__setattr__(self, "index_name", self.index_name.strip().upper())

        if isinstance(self.isin, bool) or not isinstance(self.isin, str) or not self.isin.strip():
            raise UniverseValidationError(f"isin must be a non-empty string, got {self.isin!r}")
        if any(c in self.isin for c in FORBIDDEN_CHARACTERS):
            raise UniverseValidationError(f"isin '{self.isin}' contains forbidden characters.")
        if len(self.isin.strip()) != 12:
            raise UniverseValidationError(f"ISIN must be exactly 12 alphanumeric characters, got {self.isin!r}")
        object.__setattr__(self, "isin", self.isin.strip().upper())

        if type(self.effective_from) is not datetime.date:
            raise UniverseValidationError(f"effective_from must be exact datetime.date, got {type(self.effective_from).__name__}")
        if self.effective_to is not None:
            if type(self.effective_to) is not datetime.date:
                raise UniverseValidationError(f"effective_to must be exact datetime.date, got {type(self.effective_to).__name__}")
            if self.effective_from >= self.effective_to:
                raise UniverseValidationError(
                    f"effective_from ({self.effective_from}) must precede effective_to ({self.effective_to}) for index {self.index_name}, isin {self.isin}"
                )

        if self.circular_ref is not None:
            if isinstance(self.circular_ref, bool) or not isinstance(self.circular_ref, str) or not self.circular_ref.strip():
                raise UniverseValidationError(f"circular_ref must be a non-empty string if provided, got {self.circular_ref!r}")
            object.__setattr__(self, "circular_ref", self.circular_ref.strip())

        if self.source_publication is not None:
            if isinstance(self.source_publication, bool) or not isinstance(self.source_publication, str) or not self.source_publication.strip():
                raise UniverseValidationError(f"source_publication must be a non-empty string if provided, got {self.source_publication!r}")
            object.__setattr__(self, "source_publication", self.source_publication.strip())

    def contains(self, as_of: datetime.date) -> bool:
        """Returns True if as_of falls within [effective_from, effective_to)."""
        if type(as_of) is not datetime.date:
            raise UniverseValidationError(f"as_of must be exact datetime.date, got {type(as_of).__name__}")
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return True

    def overlaps(self, other: "IndexMembershipInterval") -> bool:
        """Checks if two intervals for the same (index_name, isin) overlap in time."""
        if not isinstance(other, IndexMembershipInterval):
            raise UniverseValidationError(f"Expected IndexMembershipInterval, got {type(other).__name__}")
        if self.index_name != other.index_name or self.isin != other.isin:
            return False

        self_end = self.effective_to or datetime.date.max
        other_end = other.effective_to or datetime.date.max

        return self.effective_from < other_end and other.effective_from < self_end

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "index_name": self.index_name,
            "isin": self.isin,
            "effective_from": self.effective_from.isoformat(),
        }
        if self.effective_to is not None:
            d["effective_to"] = self.effective_to.isoformat()
        if self.circular_ref is not None:
            d["circular_ref"] = self.circular_ref
        if self.source_publication is not None:
            d["source_publication"] = self.source_publication
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IndexMembershipInterval":
        eff_to = datetime.date.fromisoformat(data["effective_to"]) if data.get("effective_to") else None
        return cls(
            index_name=str(data["index_name"]),
            isin=str(data["isin"]),
            effective_from=datetime.date.fromisoformat(data["effective_from"]),
            effective_to=eff_to,
            circular_ref=str(data["circular_ref"]) if data.get("circular_ref") else None,
            source_publication=str(data["source_publication"]) if data.get("source_publication") else None,
        )


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
