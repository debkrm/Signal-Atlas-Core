"""
Price Band and Circuit Filter Contracts.

Formalizes typed contracts for exchange price bands, circuit limits, and publication sources
per AGENTS.md Rule 5.3, Rule 10.5 and Audit §25 / §26 (Wave 0):
- PriceBandPublicationSource / PriceBandSourceDescriptor: Authoritative NSE publication metadata.
- PriceBandRecord: Discrete daily circuit observation (upper/lower limits, band percentage).
- PriceBandInterval: Half-open [effective_from, effective_to) time-varying fixed band intervals (Rule 10.5).
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Union


class PriceBandValidationError(ValueError):
    """Raised when price band records or publication descriptors violate integrity rules."""
    pass


class PriceBandPublicationSource(str, Enum):
    """
    Standardized NSE source publications providing daily circuit limits and price bands.
    Bhavcopy alone does not contain circuit bands; separate authoritative publication is mandatory.
    """
    NSE_DAILY_PRICE_BAND_REPORT = "NSE_DAILY_PRICE_BAND_REPORT"  # e.g. sec_list.csv / price_bands.csv
    NSE_PR_ZIP = "NSE_PR_ZIP"                                    # PR archive containing security statistics
    NSE_SURVEILLANCE_CIRCULAR = "NSE_SURVEILLANCE_CIRCULAR"      # Framework stage bands (ASM/GSM/ESM)


FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


def _validate_non_empty_str(val: Any, field_name: str) -> str:
    if isinstance(val, bool) or not isinstance(val, str) or not val.strip():
        raise PriceBandValidationError(f"{field_name} must be a non-empty string, got {val!r}")
    if any(c in val for c in FORBIDDEN_CHARACTERS):
        raise PriceBandValidationError(f"{field_name} contains forbidden delimiter or newline characters: {val!r}")
    return val.strip()


def _validate_date(d: Any, field_name: str) -> datetime.date:
    if type(d) is not datetime.date:
        raise PriceBandValidationError(f"{field_name} must be exact datetime.date, got {type(d).__name__}")
    return d


def _validate_decimal(val: Any, field_name: str, allow_none: bool = False) -> Optional[Decimal]:
    if val is None:
        if allow_none:
            return None
        raise PriceBandValidationError(f"{field_name} cannot be None")
    if isinstance(val, bool) or isinstance(val, float):
        raise PriceBandValidationError(f"{field_name} must be exact Decimal, got {type(val).__name__}")
    if not isinstance(val, Decimal):
        raise PriceBandValidationError(f"{field_name} must be exact Decimal, got {type(val).__name__}")
    if not val.is_finite() or val <= Decimal("0"):
        raise PriceBandValidationError(f"{field_name} must be finite positive Decimal, got {val}")
    return val


@dataclass(frozen=True, slots=True)
class PriceBandSourceDescriptor:
    """
    Authoritative publication descriptor for price band and circuit filter sources.
    Frozen ingest contract per AGENTS.md Rule 10.7 and Audit §26 (Wave 0).
    """
    source_type: PriceBandPublicationSource
    publication_name: str
    archive_url_template: str
    retrieval_frequency: str
    circular_ref: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, PriceBandPublicationSource):
            raise PriceBandValidationError(
                f"source_type must be PriceBandPublicationSource, got {type(self.source_type).__name__}"
            )
        _validate_non_empty_str(self.publication_name, "publication_name")
        _validate_non_empty_str(self.archive_url_template, "archive_url_template")
        _validate_non_empty_str(self.retrieval_frequency, "retrieval_frequency")
        if self.circular_ref is not None:
            _validate_non_empty_str(self.circular_ref, "circular_ref")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "source_type": self.source_type.value,
            "publication_name": self.publication_name,
            "archive_url_template": self.archive_url_template,
            "retrieval_frequency": self.retrieval_frequency,
            "description": self.description,
        }
        if self.circular_ref is not None:
            d["circular_ref"] = self.circular_ref
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PriceBandSourceDescriptor":
        return cls(
            source_type=PriceBandPublicationSource(str(data["source_type"])),
            publication_name=str(data["publication_name"]),
            archive_url_template=str(data["archive_url_template"]),
            retrieval_frequency=str(data["retrieval_frequency"]),
            circular_ref=str(data["circular_ref"]) if data.get("circular_ref") else None,
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True, slots=True)
class PriceBandRecord:
    """
    Discrete daily price band observation for an instrument session.
    Frozen ingest contract per AGENTS.md Rule 5.3, Rule 10.5 and Audit §25 / §26 (Wave 0).
    """
    isin: str
    trade_date: datetime.date
    series: str
    upper_circuit_limit: Optional[Decimal] = None
    lower_circuit_limit: Optional[Decimal] = None
    band_percentage: Optional[Decimal] = None
    is_unconstrained: bool = False
    source_descriptor: Optional[PriceBandSourceDescriptor] = None
    source_ref: Optional[str] = None

    def __post_init__(self) -> None:
        isin_str = _validate_non_empty_str(self.isin, "isin")
        if len(isin_str) != 12:
            raise PriceBandValidationError(f"ISIN must be 12 characters, got {self.isin!r}")
        object.__setattr__(self, "isin", isin_str.upper())

        _validate_date(self.trade_date, "trade_date")
        series_str = _validate_non_empty_str(self.series, "series")
        object.__setattr__(self, "series", series_str.upper())

        if isinstance(self.is_unconstrained, bool) is False:
            raise PriceBandValidationError(f"is_unconstrained must be bool, got {type(self.is_unconstrained).__name__}")

        if self.band_percentage is not None:
            _validate_decimal(self.band_percentage, "band_percentage")

        if self.source_descriptor is not None and not isinstance(self.source_descriptor, PriceBandSourceDescriptor):
            raise PriceBandValidationError(
                f"source_descriptor must be PriceBandSourceDescriptor, got {type(self.source_descriptor).__name__}"
            )

        if self.source_ref is not None:
            _validate_non_empty_str(self.source_ref, "source_ref")

        if self.is_unconstrained:
            # Audit §27 H-4: Unconstrained scrips (e.g. F&O stocks with dynamic flexing bands)
            # must cite an authoritative publication source descriptor; anonymous claims are rejected.
            if self.source_descriptor is None:
                raise PriceBandValidationError(
                    f"is_unconstrained=True requires an authoritative source_descriptor citation for ISIN {self.isin} on {self.trade_date}."
                )
            # Cannot claim parameter-free trading without either dynamic base percentage or limits
            if self.band_percentage is None and (self.upper_circuit_limit is None or self.lower_circuit_limit is None):
                raise PriceBandValidationError(
                    f"is_unconstrained=True scrips (e.g. F&O underlyings with dynamic flexing bands) must declare "
                    f"either band_percentage (e.g. 10.0 for dynamic base band) or explicit limits for ISIN {self.isin} on {self.trade_date}."
                )
            if self.upper_circuit_limit is not None:
                _validate_decimal(self.upper_circuit_limit, "upper_circuit_limit")
            if self.lower_circuit_limit is not None:
                _validate_decimal(self.lower_circuit_limit, "lower_circuit_limit")
        else:
            # Constrained equity scrips must have valid limits if provided
            if self.upper_circuit_limit is not None:
                _validate_decimal(self.upper_circuit_limit, "upper_circuit_limit")
            if self.lower_circuit_limit is not None:
                _validate_decimal(self.lower_circuit_limit, "lower_circuit_limit")

            if self.upper_circuit_limit is not None and self.lower_circuit_limit is not None:
                if self.lower_circuit_limit >= self.upper_circuit_limit:
                    raise PriceBandValidationError(
                        f"lower_circuit_limit ({self.lower_circuit_limit}) must be strictly less than "
                        f"upper_circuit_limit ({self.upper_circuit_limit}) for ISIN {self.isin} on {self.trade_date}"
                    )

        # Audit §27 H-4: Cross-check band_percentage against upper/lower limits
        if self.upper_circuit_limit is not None and self.lower_circuit_limit is not None and self.band_percentage is not None:
            implied_pct = ((self.upper_circuit_limit - self.lower_circuit_limit) / (self.upper_circuit_limit + self.lower_circuit_limit)) * Decimal("100")
            max_discrepancy = max(Decimal("1.5"), self.band_percentage * Decimal("0.20"))
            if abs(implied_pct - self.band_percentage) > max_discrepancy:
                raise PriceBandValidationError(
                    f"Inconsistent price band limits vs band_percentage for ISIN {self.isin} on {self.trade_date}: "
                    f"limits [{self.lower_circuit_limit}, {self.upper_circuit_limit}] imply band percentage {implied_pct:.2f}%, "
                    f"which diverges from declared band_percentage {self.band_percentage}%."
                )

    @property
    def has_circuit_evidence(self) -> bool:
        """Returns True if authoritative circuit boundaries are documented."""
        if self.is_unconstrained:
            return self.source_descriptor is not None and (
                (self.upper_circuit_limit is not None and self.lower_circuit_limit is not None)
                or self.band_percentage is not None
            )
        return self.upper_circuit_limit is not None and self.lower_circuit_limit is not None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "isin": self.isin,
            "trade_date": self.trade_date.isoformat(),
            "series": self.series,
            "is_unconstrained": self.is_unconstrained,
        }
        if self.upper_circuit_limit is not None:
            d["upper_circuit_limit"] = str(self.upper_circuit_limit)
        if self.lower_circuit_limit is not None:
            d["lower_circuit_limit"] = str(self.lower_circuit_limit)
        if self.band_percentage is not None:
            d["band_percentage"] = str(self.band_percentage)
        if self.source_descriptor is not None:
            d["source_descriptor"] = self.source_descriptor.to_dict()
        if self.source_ref is not None:
            d["source_ref"] = self.source_ref
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PriceBandRecord":
        u_lim = Decimal(str(data["upper_circuit_limit"])) if data.get("upper_circuit_limit") else None
        l_lim = Decimal(str(data["lower_circuit_limit"])) if data.get("lower_circuit_limit") else None
        band_p = Decimal(str(data["band_percentage"])) if data.get("band_percentage") else None
        src_desc = PriceBandSourceDescriptor.from_dict(data["source_descriptor"]) if data.get("source_descriptor") else None
        return cls(
            isin=str(data["isin"]),
            trade_date=datetime.date.fromisoformat(data["trade_date"]),
            series=str(data["series"]),
            upper_circuit_limit=u_lim,
            lower_circuit_limit=l_lim,
            band_percentage=band_p,
            is_unconstrained=bool(data.get("is_unconstrained", False)),
            source_descriptor=src_desc,
            source_ref=str(data["source_ref"]) if data.get("source_ref") else None,
        )


@dataclass(frozen=True, slots=True)
class PriceBandInterval:
    """
    Time-varying fixed price band interval for an instrument (e.g. under ESM / GSM / Trade-to-trade).
    Interval semantics: half-open [effective_from, effective_to) per AGENTS.md Rule 10.5.
    """
    isin: str
    band_percentage: Decimal
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None
    circular_ref: Optional[str] = None

    def __post_init__(self) -> None:
        isin_str = _validate_non_empty_str(self.isin, "isin")
        if len(isin_str) != 12:
            raise PriceBandValidationError(f"ISIN must be 12 characters, got {self.isin!r}")
        object.__setattr__(self, "isin", isin_str.upper())

        _validate_decimal(self.band_percentage, "band_percentage")
        _validate_date(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _validate_date(self.effective_to, "effective_to")
            if self.effective_from >= self.effective_to:
                raise PriceBandValidationError(
                    f"effective_from ({self.effective_from}) must precede effective_to ({self.effective_to}) for ISIN {self.isin}"
                )
        if self.circular_ref is not None:
            _validate_non_empty_str(self.circular_ref, "circular_ref")

    def contains(self, as_of: datetime.date) -> bool:
        """Returns True if as_of falls within half-open [effective_from, effective_to)."""
        _validate_date(as_of, "as_of")
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return True

