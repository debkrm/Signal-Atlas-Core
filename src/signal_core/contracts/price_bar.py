"""Immutable Market Data Price Bar Contract.

Defines the core unadjusted OHLCV price bar used throughout Signal Atlas Core.
Guarantees strict Decimal precision, finite value validation, positive prices,
non-negative volumes, and coherent high/low boundaries.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Optional


class PriceBarValidationError(ValueError):
    """Raised when PriceBar parameters violate numeric or financial invariants."""
    pass


FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


@dataclass(frozen=True, slots=True)
class PriceBar:
    """
    Immutable representation of an unadjusted daily OHLCV market session bar.

    Financial Values:
    - Must be exact Decimal instances. Binary floating-point values are strictly rejected.
    - Must be finite (NaN, +Infinity, -Infinity are rejected).
    - Prices must be strictly positive (> 0).
    - Volume must be non-negative integer (>= 0). Booleans are strictly rejected.
    - Traded value (turnover), if provided, must be a finite, non-negative Decimal.

    Invariants:
    - low <= open <= high
    - low <= close <= high
    - trade_date must be a genuine datetime.date, strictly rejecting datetime.datetime.
    - instrument_id must be a non-empty string without leading/trailing whitespace or delimiter characters.
    - currency defaults to 'INR' for NSE cash equities.
    """
    instrument_id: str
    trade_date: datetime.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    traded_value: Optional[Decimal] = None
    currency: str = "INR"

    def __post_init__(self) -> None:
        # 1. Instrument ID validation
        if not isinstance(self.instrument_id, str):
            raise PriceBarValidationError(f"instrument_id must be a string, got {type(self.instrument_id).__name__}.")
        if not self.instrument_id:
            raise PriceBarValidationError("instrument_id cannot be empty.")
        if self.instrument_id != self.instrument_id.strip():
            raise PriceBarValidationError(
                f"instrument_id '{self.instrument_id}' contains leading or trailing whitespace. "
                "Silent modification is prohibited; clean identifiers must be supplied."
            )
        if any(c in self.instrument_id for c in FORBIDDEN_CHARACTERS):
            raise PriceBarValidationError(
                f"instrument_id '{self.instrument_id}' contains forbidden delimiter or newline characters."
            )

        # 2. Strict Date Validation (reject datetime.datetime which is a subclass of date)
        if type(self.trade_date) is not datetime.date:
            raise PriceBarValidationError(
                f"trade_date must be a genuine datetime.date instance (got {type(self.trade_date).__name__}). "
                "datetime.datetime instances are strictly rejected to prevent timezone/intraday leakage."
            )

        # 3. Currency Validation
        if not isinstance(self.currency, str):
            raise PriceBarValidationError(f"currency must be a string, got {type(self.currency).__name__}.")
        if not self.currency or self.currency != self.currency.strip():
            raise PriceBarValidationError("currency must be a non-empty string without leading/trailing whitespace.")
        if any(c in self.currency for c in FORBIDDEN_CHARACTERS):
            raise PriceBarValidationError("currency contains forbidden delimiter characters.")

        # 4. Strict Price Checks (reject bool, float, non-Decimal, non-finite, <= 0)
        for name, val in [("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)]:
            if isinstance(val, bool):
                raise PriceBarValidationError(f"Price '{name}' cannot be a boolean.")
            if isinstance(val, float):
                raise PriceBarValidationError(
                    f"Price '{name}' cannot be a binary float. Exact Decimal required."
                )
            if not isinstance(val, Decimal):
                raise PriceBarValidationError(
                    f"Price '{name}' must be an instance of Decimal, got {type(val).__name__}."
                )
            if not val.is_finite():
                raise PriceBarValidationError(
                    f"Price '{name}' must be finite (got {val})."
                )
            if val <= Decimal("0"):
                raise PriceBarValidationError(
                    f"Price '{name}' must be strictly positive (> 0), got {val}."
                )

        # 5. Volume Validation (strict int, reject bool and float)
        if isinstance(self.volume, bool):
            raise PriceBarValidationError("volume cannot be a boolean.")
        if isinstance(self.volume, float):
            raise PriceBarValidationError("volume cannot be a binary float. Exact integer required.")
        if not isinstance(self.volume, int):
            raise PriceBarValidationError(f"volume must be an integer, got {type(self.volume).__name__}.")
        if self.volume < 0:
            raise PriceBarValidationError(f"volume must be non-negative (>= 0), got {self.volume}.")

        # 6. Traded Value (Turnover) Validation
        if self.traded_value is not None:
            if isinstance(self.traded_value, bool):
                raise PriceBarValidationError("traded_value cannot be a boolean.")
            if isinstance(self.traded_value, float):
                raise PriceBarValidationError("traded_value cannot be a binary float. Exact Decimal required.")
            if not isinstance(self.traded_value, Decimal):
                raise PriceBarValidationError(
                    f"traded_value must be an instance of Decimal, got {type(self.traded_value).__name__}."
                )
            if not self.traded_value.is_finite():
                raise PriceBarValidationError(f"traded_value must be finite, got {self.traded_value}.")
            if self.traded_value < Decimal("0"):
                raise PriceBarValidationError(
                    f"traded_value must be non-negative (>= 0), got {self.traded_value}."
                )

        # 7. OHLC Relationship Checks
        if self.low > self.high:
            raise PriceBarValidationError(
                f"Invalid OHLC relationship: low ({self.low}) cannot exceed high ({self.high})."
            )
        if self.open < self.low or self.open > self.high:
            raise PriceBarValidationError(
                f"Invalid OHLC relationship: open ({self.open}) must be within [low ({self.low}), high ({self.high})]."
            )
        if self.close < self.low or self.close > self.high:
            raise PriceBarValidationError(
                f"Invalid OHLC relationship: close ({self.close}) must be within [low ({self.low}), high ({self.high})]."
            )
