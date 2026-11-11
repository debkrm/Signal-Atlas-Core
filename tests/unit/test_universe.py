"""Unit tests for Point-in-Time Universe contracts."""

import datetime
import pytest

from signal_core.contracts.universe import (
    UniverseInterval,
    UniverseSchedule,
    UniverseValidationError,
)


def test_universe_interval_creation_and_query():
    """Verify UniverseInterval boundary checks and queries."""
    interval = UniverseInterval(
        instrument_id="TCS",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 3, 31),
    )
    assert interval.instrument_id == "TCS"
    assert interval.start_date == datetime.date(2024, 1, 1)
    assert interval.end_date == datetime.date(2024, 3, 31)

    # Inclusive boundaries
    assert interval.contains(datetime.date(2024, 1, 1)) is True
    assert interval.contains(datetime.date(2024, 2, 15)) is True
    assert interval.contains(datetime.date(2024, 3, 31)) is True

    # Outside boundaries
    assert interval.contains(datetime.date(2023, 12, 31)) is False
    assert interval.contains(datetime.date(2024, 4, 1)) is False


def test_universe_interval_rejection_of_datetime():
    """Verify UniverseInterval rejects datetime.datetime instances."""
    with pytest.raises(UniverseValidationError, match="genuine datetime.date"):
        UniverseInterval(
            instrument_id="TCS",
            start_date=datetime.datetime(2024, 1, 1, 9, 15),  # type: ignore[arg-type]
            end_date=datetime.date(2024, 3, 31),
        )

    with pytest.raises(UniverseValidationError, match="genuine datetime.date"):
        UniverseInterval(
            instrument_id="TCS",
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.datetime(2024, 3, 31, 15, 30),  # type: ignore[arg-type]
        )


def test_universe_interval_invalid_dates():
    """Verify interval start_date cannot exceed end_date."""
    with pytest.raises(UniverseValidationError, match="cannot be after end_date"):
        UniverseInterval(
            instrument_id="TCS",
            start_date=datetime.date(2024, 4, 1),
            end_date=datetime.date(2024, 3, 31),
        )


def test_universe_schedule_construction_and_canonical_ordering():
    """Verify schedule creation sorts dates and instruments deterministically."""
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 1, 2)

    # Clean distinct members across dates
    raw = {
        d2: ["RELIANCE", "INFY", "TCS"],
        d1: ["TCS", "INFY"],
    }

    schedule = UniverseSchedule(raw)

    # Chronologically sorted dates
    assert schedule.dates == (d1, d2)
    assert schedule.start_date == d1
    assert schedule.end_date == d2
    assert schedule.session_count == 2

    # Deterministically sorted members
    assert schedule.get_universe_for_date(d1) == ("INFY", "TCS")
    assert schedule.get_universe_for_date(d2) == ("INFY", "RELIANCE", "TCS")

    # Overall unique instruments
    assert schedule.unique_instruments == ("INFY", "RELIANCE", "TCS")


def test_universe_schedule_rejection_of_duplicate_members():
    """Verify that duplicate members on the same date raise an error instead of silent deduplication."""
    d1 = datetime.date(2024, 1, 1)
    with pytest.raises(UniverseValidationError, match="Duplicate instrument 'INFY' detected"):
        UniverseSchedule({
            d1: ["INFY", "TCS", "INFY"],
        })


def test_universe_schedule_rejection_of_whitespace_members():
    """Verify that whitespace-padded identifiers raise an error instead of silent stripping."""
    d1 = datetime.date(2024, 1, 1)
    with pytest.raises(UniverseValidationError, match="contains leading or trailing whitespace"):
        UniverseSchedule({
            d1: ["INFY", " TCS "],
        })


def test_universe_schedule_rejection_of_delimiters():
    """Verify delimiter characters are strictly rejected to prevent injection."""
    d1 = datetime.date(2024, 1, 1)
    for bad_member in ["INFY,TCS", "INFY;TCS", "INFY\nTCS"]:
        with pytest.raises(UniverseValidationError, match="forbidden delimiter"):
            UniverseSchedule({
                d1: [bad_member],
            })


def test_universe_schedule_rejection_of_datetime_keys():
    """Verify datetime.datetime is rejected as a schedule key."""
    d_dt = datetime.datetime(2024, 1, 1, 9, 15)
    with pytest.raises(UniverseValidationError, match="genuine datetime.date instance"):
        UniverseSchedule({
            d_dt: ["INFY", "TCS"],  # type: ignore[dict-item]
        })


def test_universe_schedule_queries_and_immutability():
    """Verify membership queries and immutability."""
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 1, 2)
    schedule = UniverseSchedule({
        d1: ["INFY", "TCS"],
        d2: ["RELIANCE"],
    })

    assert schedule.is_in_universe("INFY", d1) is True
    assert schedule.is_in_universe("RELIANCE", d1) is False
    assert schedule.is_in_universe("RELIANCE", d2) is True
    assert schedule.is_in_universe("INFY", d2) is False

    # Date not in schedule returns empty tuple and False
    d_unknown = datetime.date(2024, 1, 3)
    assert schedule.get_universe_for_date(d_unknown) == ()
    assert schedule.is_in_universe("INFY", d_unknown) is False

    # Querying with datetime raises UniverseValidationError
    with pytest.raises(UniverseValidationError, match="must be a genuine datetime.date"):
        schedule.get_universe_for_date(datetime.datetime(2024, 1, 1, 9, 15))  # type: ignore[arg-type]

    # Immutability: returned dictionary is a copy; internal schedule cannot be mutated
    d_dict = schedule.to_dict()
    d_dict[d1] = ("HACKED",)
    assert schedule.get_universe_for_date(d1) == ("INFY", "TCS")
