"""Unit tests for the immutable PriceBar contract."""

from dataclasses import FrozenInstanceError
import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.price_bar import PriceBar, PriceBarValidationError


def test_valid_price_bar_creation():
    """Verify standard valid PriceBar creation with full precision Decimals."""
    bar = PriceBar(
        instrument_id="TCS",
        trade_date=datetime.date(2024, 1, 1),
        open=Decimal("3800.00"),
        high=Decimal("3850.50"),
        low=Decimal("3790.25"),
        close=Decimal("3820.00"),
        volume=125000,
        traded_value=Decimal("477500000.00"),
        currency="INR",
    )
    assert bar.instrument_id == "TCS"
    assert bar.trade_date == datetime.date(2024, 1, 1)
    assert bar.open == Decimal("3800.00")
    assert bar.high == Decimal("3850.50")
    assert bar.low == Decimal("3790.25")
    assert bar.close == Decimal("3820.00")
    assert bar.volume == 125000
    assert bar.traded_value == Decimal("477500000.00")
    assert bar.currency == "INR"


def test_price_bar_immutability():
    """Verify PriceBar is frozen and rejects attribute reassignment."""
    bar = PriceBar(
        instrument_id="INFY",
        trade_date=datetime.date(2024, 1, 1),
        open=Decimal("1500.00"),
        high=Decimal("1520.00"),
        low=Decimal("1490.00"),
        close=Decimal("1510.00"),
        volume=50000,
    )
    with pytest.raises(FrozenInstanceError):
        bar.close = Decimal("1515.00")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        bar.volume = 60000  # type: ignore[misc]


def test_rejection_of_datetime_instances():
    """Verify datetime.datetime is strictly rejected (must be genuine datetime.date)."""
    bad_datetime = datetime.datetime(2024, 1, 1, 9, 15, 0)
    with pytest.raises(PriceBarValidationError, match="genuine datetime.date instance"):
        PriceBar(
            instrument_id="INFY",
            trade_date=bad_datetime,  # type: ignore[arg-type]
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )


def test_rejection_of_booleans():
    """Verify booleans are strictly rejected for volume, prices, and traded_value."""
    # Volume as boolean
    with pytest.raises(PriceBarValidationError, match="volume cannot be a boolean"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=True,  # type: ignore[arg-type]
        )

    # Price as boolean
    with pytest.raises(PriceBarValidationError, match="cannot be a boolean"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=True,  # type: ignore[arg-type]
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    # Traded value as boolean
    with pytest.raises(PriceBarValidationError, match="traded_value cannot be a boolean"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
            traded_value=False,  # type: ignore[arg-type]
        )


def test_rejection_of_binary_floats():
    """Verify binary floats are strictly rejected to prevent precision loss."""
    with pytest.raises(PriceBarValidationError, match="cannot be a binary float"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=1500.0,  # float
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    with pytest.raises(PriceBarValidationError, match="cannot be a binary float"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000.0,  # float volume
        )


def test_rejection_of_non_finite_decimals():
    """Verify NaN and Infinities are rejected."""
    for bad_val in [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]:
        with pytest.raises(PriceBarValidationError, match="must be finite"):
            PriceBar(
                instrument_id="INFY",
                trade_date=datetime.date(2024, 1, 1),
                open=bad_val,
                high=Decimal("1520.00"),
                low=Decimal("1490.00"),
                close=Decimal("1510.00"),
                volume=50000,
            )


def test_rejection_of_non_positive_prices():
    """Verify zero or negative prices are strictly rejected."""
    with pytest.raises(PriceBarValidationError, match="must be strictly positive"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("0.00"),
            high=Decimal("1520.00"),
            low=Decimal("0.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    with pytest.raises(PriceBarValidationError, match="must be strictly positive"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("-10.00"),
            high=Decimal("1520.00"),
            low=Decimal("-10.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )


def test_rejection_of_negative_volume():
    """Verify negative volume is rejected."""
    with pytest.raises(PriceBarValidationError, match="volume must be non-negative"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=-1,
        )


def test_rejection_of_invalid_ohlc_relationships():
    """Verify low <= open <= high and low <= close <= high invariants."""
    # Low > High
    with pytest.raises(PriceBarValidationError, match="low .* cannot exceed high"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1490.00"),
            low=Decimal("1520.00"),
            close=Decimal("1500.00"),
            volume=50000,
        )

    # Open > High
    with pytest.raises(PriceBarValidationError, match="open .* must be within"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1530.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    # Open < Low
    with pytest.raises(PriceBarValidationError, match="open .* must be within"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1480.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    # Close > High
    with pytest.raises(PriceBarValidationError, match="close .* must be within"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1525.00"),
            volume=50000,
        )

    # Close < Low
    with pytest.raises(PriceBarValidationError, match="close .* must be within"):
        PriceBar(
            instrument_id="INFY",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1485.00"),
            volume=50000,
        )


def test_rejection_of_whitespace_and_delimiters_in_identifier():
    """Verify instrument_id rejects whitespace and delimiter characters without silent alteration."""
    # Blank or empty
    with pytest.raises(PriceBarValidationError, match="cannot be empty"):
        PriceBar(
            instrument_id="",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    # Leading/trailing whitespace
    with pytest.raises(PriceBarValidationError, match="contains leading or trailing whitespace"):
        PriceBar(
            instrument_id=" INFY ",
            trade_date=datetime.date(2024, 1, 1),
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=50000,
        )

    # Delimiter injection
    for bad_char in [",", ";", "\n", "\t"]:
        with pytest.raises(PriceBarValidationError, match="forbidden delimiter"):
            PriceBar(
                instrument_id=f"INFY{bad_char}NSE",
                trade_date=datetime.date(2024, 1, 1),
                open=Decimal("1500.00"),
                high=Decimal("1520.00"),
                low=Decimal("1490.00"),
                close=Decimal("1510.00"),
                volume=50000,
            )
