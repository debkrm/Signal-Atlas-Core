"""
Authoritative Security Master and Time-Varying Fact Contracts for Indian Financial Markets.

Implements security identity and point-in-time intervals per AGENTS.md Rule 10.4 and Rule 10.5:
- Identity is ISIN, never symbol. Symbols and series are effective-dated attributes.
- Time-varying facts (symbol/series intervals, surveillance stages, delistings) are stored as
  half-open intervals [effective_from, effective_to) and resolved as-of date T.
- Corporate actions (splits, bonuses, mergers, ISIN transitions) are explicit events with verified ex-dates.
- Pruning of merged/delisted scrips and transitioned ISINs on exact effective dates.
- Deterministic cryptographic fingerprinting (SEC-MSTR-V1).
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
import hashlib
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple, Union

from signal_core.contracts.price_band import (
    PriceBandInterval,
    PriceBandPublicationSource,
    PriceBandRecord,
    PriceBandSourceDescriptor,
)

FORBIDDEN_CHARACTERS = (",", ";", "\n", "\r", "\t")


class SecurityMasterError(ValueError):
    """Base exception for security master validation and invariant failures."""
    pass


class SecurityNotFoundError(SecurityMasterError):
    """Raised when an ISIN cannot be resolved as-of a given date."""
    pass


class SecurityTransitionError(SecurityMasterError):
    """Raised when an invalid or unverified ISIN transition is attempted."""
    pass


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise SecurityMasterError(f"{name} must be a string, got {type(value).__name__}")
    if not value:
        raise SecurityMasterError(f"{name} cannot be empty.")
    if value != value.strip():
        raise SecurityMasterError(f"{name} '{value}' contains leading or trailing whitespace.")
    if any(c in value for c in FORBIDDEN_CHARACTERS):
        raise SecurityMasterError(f"{name} '{value}' contains forbidden characters.")
    return value


def _validate_date(d: Optional[datetime.date], name: str) -> Optional[datetime.date]:
    if d is None:
        return None
    if type(d) is not datetime.date:
        raise SecurityMasterError(f"{name} must be a genuine datetime.date, got {type(d).__name__}")
    return d


class SurveillanceStage(str, Enum):
    """Standardized SEBI/NSE surveillance framework stages."""
    NONE = "NONE"
    GSM_STAGE_1 = "GSM_STAGE_1"
    GSM_STAGE_2 = "GSM_STAGE_2"
    GSM_STAGE_3 = "GSM_STAGE_3"
    GSM_STAGE_4 = "GSM_STAGE_4"
    ASM_LONG_TERM_STAGE_1 = "ASM_LONG_TERM_STAGE_1"
    ASM_LONG_TERM_STAGE_2 = "ASM_LONG_TERM_STAGE_2"
    ASM_LONG_TERM_STAGE_3 = "ASM_LONG_TERM_STAGE_3"
    ASM_LONG_TERM_STAGE_4 = "ASM_LONG_TERM_STAGE_4"
    ASM_SHORT_TERM_STAGE_1 = "ASM_SHORT_TERM_STAGE_1"
    ASM_SHORT_TERM_STAGE_2 = "ASM_SHORT_TERM_STAGE_2"
    ESM_STAGE_1 = "ESM_STAGE_1"
    ESM_STAGE_2 = "ESM_STAGE_2"


class CorporateActionType(str, Enum):
    """Standardized Corporate Action Classifications."""
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    RIGHTS = "RIGHTS"
    DELISTING = "DELISTING"
    ISIN_TRANSITION = "ISIN_TRANSITION"
    CONSOLIDATION = "CONSOLIDATION"


@dataclass(frozen=True, slots=True)
class SymbolInterval:
    """
    Effective-dated interval mapping an ISIN to a symbol and series.
    Interval semantics: half-open [effective_from, effective_to).
    If effective_to is None, the mapping is currently active/open-ended.
    """
    isin: str
    symbol: str
    series: str
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None

    def __post_init__(self) -> None:
        _validate_identifier(self.isin, "isin")
        _validate_identifier(self.symbol, "symbol")
        _validate_identifier(self.series, "series")
        _validate_date(self.effective_from, "effective_from")
        _validate_date(self.effective_to, "effective_to")

        if self.effective_to is not None and self.effective_from >= self.effective_to:
            raise SecurityMasterError(
                f"effective_from ({self.effective_from}) must precede effective_to ({self.effective_to}) for ISIN {self.isin}"
            )

    def contains(self, as_of: datetime.date) -> bool:
        """Returns True if as_of falls within [effective_from, effective_to)."""
        _validate_date(as_of, "as_of")
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return True


@dataclass(frozen=True, slots=True)
class SurveillanceInterval:
    """
    Time-varying surveillance stage mapping for a security.
    Interval semantics: half-open [effective_from, effective_to).
    """
    isin: str
    framework: str
    stage: SurveillanceStage
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None

    def __post_init__(self) -> None:
        _validate_identifier(self.isin, "isin")
        _validate_identifier(self.framework, "framework")
        if not isinstance(self.stage, SurveillanceStage):
            raise SecurityMasterError(f"stage must be a SurveillanceStage, got {type(self.stage).__name__}")
        _validate_date(self.effective_from, "effective_from")
        _validate_date(self.effective_to, "effective_to")

        if self.effective_to is not None and self.effective_from >= self.effective_to:
            raise SecurityMasterError(
                f"effective_from ({self.effective_from}) must precede effective_to ({self.effective_to}) for ISIN {self.isin}"
            )

    def contains(self, as_of: datetime.date) -> bool:
        """Returns True if as_of falls within [effective_from, effective_to)."""
        _validate_date(as_of, "as_of")
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return True


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """
    Explicit corporate action record with verified ex-date and adjustment ratios.
    Frozen ingest contract per AGENTS.md Rule 5.4, Rule 10.3 and Wave 0 (Audit §26 / §27 H-5).

    Ratio Semantics (Unambiguous Direction per Audit §27 H-5):
    - ratio_numerator: Post-event total shares held per ratio_denominator pre-event shares held.
      * For a 1:10 stock split (1 old share subdivided into 10 new shares):
        ratio_numerator = Decimal("10")
        ratio_denominator = Decimal("1")
        adjustment_factor = ratio_denominator / ratio_numerator = 1 / 10 = Decimal("0.10")
      * For a 1:1 bonus issue (1 bonus share received for every 1 old share held -> 2 shares held):
        ratio_numerator = Decimal("2")
        ratio_denominator = Decimal("1")
        adjustment_factor = ratio_denominator / ratio_numerator = 1 / 2 = Decimal("0.50")
    - ratio_denominator: Pre-event shares held (typically 1 for splits and standard bonus expressions).
    - adjustment_factor: Multiplier applied to pre-event prices = ratio_denominator / ratio_numerator.
    """
    isin: str
    ex_date: datetime.date
    action_type: CorporateActionType
    ratio_numerator: Decimal
    ratio_denominator: Decimal
    old_isin: Optional[str] = None
    new_isin: Optional[str] = None
    circular_ref: Optional[str] = None
    description: Optional[str] = None
    record_date: Optional[datetime.date] = None

    def __post_init__(self) -> None:
        _validate_identifier(self.isin, "isin")
        _validate_date(self.ex_date, "ex_date")
        if self.record_date is not None:
            _validate_date(self.record_date, "record_date")
            if self.record_date < self.ex_date:
                raise SecurityMasterError(
                    f"record_date ({self.record_date}) cannot precede ex_date ({self.ex_date}) for ISIN {self.isin}"
                )

        if not isinstance(self.action_type, CorporateActionType):
            raise SecurityMasterError(f"action_type must be a CorporateActionType, got {type(self.action_type).__name__}")
        if not isinstance(self.ratio_numerator, Decimal) or not isinstance(self.ratio_denominator, Decimal):
            raise SecurityMasterError("ratio_numerator and ratio_denominator must be exact Decimal instances.")
        if self.ratio_numerator <= Decimal("0") or self.ratio_denominator <= Decimal("0"):
            raise SecurityMasterError("Ratios must be strictly positive Decimals.")
        if not self.ratio_numerator.is_finite() or not self.ratio_denominator.is_finite():
            raise SecurityMasterError("Ratios must be finite Decimals.")

        # Invariant H-5: Invert-proof ratio direction per action type.
        # SPLIT and BONUS increase total share count (ratio_numerator > ratio_denominator, factor < 1.0).
        if self.action_type in (CorporateActionType.SPLIT, CorporateActionType.BONUS):
            if self.ratio_numerator <= self.ratio_denominator:
                raise SecurityMasterError(
                    f"{self.action_type.value} requires ratio_numerator > ratio_denominator (post-event shares > pre-event shares). "
                    f"For a 1:10 split (1 old share subdivided into 10 new shares), use ratio_numerator=10, ratio_denominator=1, "
                    f"yielding adjustment_factor=0.1. Received ratio_numerator={self.ratio_numerator}, ratio_denominator={self.ratio_denominator}."
                )

        # Invariant H-10: CONSOLIDATION (reverse split) merges multiple old shares into fewer new shares
        # (ratio_numerator < ratio_denominator, adjustment_factor > 1.0).
        if self.action_type == CorporateActionType.CONSOLIDATION:
            if self.ratio_numerator >= self.ratio_denominator:
                raise SecurityMasterError(
                    f"CONSOLIDATION requires ratio_numerator < ratio_denominator (post-event shares < pre-event shares). "
                    f"For a 10:1 consolidation (10 old shares consolidated into 1 new share), use ratio_numerator=1, ratio_denominator=10, "
                    f"yielding adjustment_factor=10.0. Received ratio_numerator={self.ratio_numerator}, ratio_denominator={self.ratio_denominator}."
                )

        if self.action_type == CorporateActionType.ISIN_TRANSITION:
            if not self.old_isin or not self.new_isin:
                raise SecurityMasterError("ISIN_TRANSITION requires both old_isin and new_isin.")
            _validate_identifier(self.old_isin, "old_isin")
            _validate_identifier(self.new_isin, "new_isin")
            if self.old_isin == self.new_isin:
                raise SecurityMasterError(f"old_isin and new_isin must differ for ISIN_TRANSITION: {self.old_isin}")
        else:
            if self.old_isin is not None:
                _validate_identifier(self.old_isin, "old_isin")
            if self.new_isin is not None:
                _validate_identifier(self.new_isin, "new_isin")

        if self.circular_ref is not None:
            _validate_identifier(self.circular_ref, "circular_ref")

    @property
    def adjustment_factor(self) -> Decimal:
        """Multiplier to apply to pre-event prices to back-adjust to post-event basis."""
        return self.ratio_denominator / self.ratio_numerator

    def to_dict(self) -> Dict[str, Any]:
        """Serializes CorporateAction to JSON-compatible dictionary."""
        d: Dict[str, Any] = {
            "isin": self.isin,
            "ex_date": self.ex_date.isoformat(),
            "action_type": self.action_type.value,
            "ratio_numerator": str(self.ratio_numerator),
            "ratio_denominator": str(self.ratio_denominator),
        }
        if self.old_isin is not None:
            d["old_isin"] = self.old_isin
        if self.new_isin is not None:
            d["new_isin"] = self.new_isin
        if self.circular_ref is not None:
            d["circular_ref"] = self.circular_ref
        if self.description is not None:
            d["description"] = self.description
        if self.record_date is not None:
            d["record_date"] = self.record_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorporateAction":
        """Deserializes CorporateAction from mapping."""
        rec_d = datetime.date.fromisoformat(data["record_date"]) if data.get("record_date") else None
        return cls(
            isin=str(data["isin"]),
            ex_date=datetime.date.fromisoformat(data["ex_date"]),
            action_type=CorporateActionType(str(data["action_type"])),
            ratio_numerator=Decimal(str(data["ratio_numerator"])),
            ratio_denominator=Decimal(str(data["ratio_denominator"])),
            old_isin=str(data["old_isin"]) if data.get("old_isin") else None,
            new_isin=str(data["new_isin"]) if data.get("new_isin") else None,
            circular_ref=str(data["circular_ref"]) if data.get("circular_ref") else None,
            description=str(data["description"]) if data.get("description") else None,
            record_date=rec_d,
        )


@dataclass(frozen=True, slots=True)
class DelistingEvent:
    """
    Verified corporate merger or delisting event.
    The security ceases trading on and after effective_date.
    """
    isin: str
    effective_date: datetime.date
    reason: str
    circular_ref: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_identifier(self.isin, "isin")
        _validate_date(self.effective_date, "effective_date")
        _validate_identifier(self.reason, "reason")
        if self.circular_ref is not None:
            _validate_identifier(self.circular_ref, "circular_ref")


@dataclass(frozen=True, slots=True)
class ISINTransitionEvent:
    """
    Explicit ISIN replacement event (e.g. stock split or restructuring).
    On and after effective_date, old_isin is ceased and replaced by new_isin.
    """
    old_isin: str
    new_isin: str
    effective_date: datetime.date
    reason: str
    circular_ref: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_identifier(self.old_isin, "old_isin")
        _validate_identifier(self.new_isin, "new_isin")
        if self.old_isin == self.new_isin:
            raise SecurityMasterError(f"old_isin and new_isin cannot be identical: {self.old_isin}")
        _validate_date(self.effective_date, "effective_date")
        _validate_identifier(self.reason, "reason")
        if self.circular_ref is not None:
            _validate_identifier(self.circular_ref, "circular_ref")


def compute_security_master_fingerprint(
    symbol_intervals: Sequence[SymbolInterval],
    corporate_actions: Sequence[CorporateAction],
    delisting_events: Sequence[DelistingEvent],
    isin_transitions: Sequence[ISINTransitionEvent],
    price_bands: Optional[Sequence[PriceBandRecord]] = None,
    price_band_intervals: Optional[Sequence[PriceBandInterval]] = None,
) -> str:
    """Computes a deterministic SHA-256 fingerprint for security master state."""
    hasher = hashlib.sha256()
    hasher.update(b"SEC_MASTER_V1:\n")

    # 1. Symbol intervals
    hasher.update(b"SYMBOLS:\n")
    sorted_syms = sorted(symbol_intervals, key=lambda s: (s.isin, s.effective_from))
    for s in sorted_syms:
        to_str = s.effective_to.isoformat() if s.effective_to else "OPEN"
        row = f"{s.isin},{s.symbol},{s.series},{s.effective_from.isoformat()},{to_str}\n"
        hasher.update(row.encode("utf-8"))

    # 2. Corporate Actions
    hasher.update(b"CORP_ACTIONS:\n")
    sorted_ca = sorted(corporate_actions, key=lambda ca: (ca.isin, ca.ex_date, ca.action_type.value))
    for ca in sorted_ca:
        row = f"{ca.isin},{ca.ex_date.isoformat()},{ca.action_type.value},{ca.ratio_numerator},{ca.ratio_denominator}\n"
        hasher.update(row.encode("utf-8"))

    # 3. Delistings
    hasher.update(b"DELISTINGS:\n")
    sorted_del = sorted(delisting_events, key=lambda d: (d.isin, d.effective_date))
    for d in sorted_del:
        row = f"{d.isin},{d.effective_date.isoformat()},{d.reason}\n"
        hasher.update(row.encode("utf-8"))

    # 4. Transitions
    hasher.update(b"TRANSITIONS:\n")
    sorted_tr = sorted(isin_transitions, key=lambda t: (t.old_isin, t.effective_date))
    for t in sorted_tr:
        row = f"{t.old_isin},{t.new_isin},{t.effective_date.isoformat()},{t.reason}\n"
        hasher.update(row.encode("utf-8"))

    # 5. Price Bands (Audit §25 G-6 / Wave 2)
    if price_bands:
        hasher.update(b"PRICE_BANDS:\n")
        sorted_bands = sorted(price_bands, key=lambda b: (b.isin, b.trade_date))
        for b in sorted_bands:
            row = f"{b.isin},{b.trade_date.isoformat()},{b.series},{b.upper_circuit_limit},{b.lower_circuit_limit}\n"
            hasher.update(row.encode("utf-8"))

    # 6. Price Band Intervals (Rule 10.5, Audit §31 H-30)
    if price_band_intervals:
        hasher.update(b"PRICE_BAND_INTERVALS:\n")
        sorted_pbi = sorted(price_band_intervals, key=lambda b: (b.isin, b.effective_from))
        for b in sorted_pbi:
            to_str = b.effective_to.isoformat() if b.effective_to else "OPEN"
            circ_str = b.circular_ref or "NONE"
            src_str = b.source_descriptor.publication_name if b.source_descriptor else "NONE"
            pct_str = str(b.band_percentage) if b.band_percentage is not None else "NONE"
            row = f"{b.isin},{b.effective_from.isoformat()},{to_str},{pct_str},{b.is_unconstrained},{circ_str},{src_str}\n"
            hasher.update(row.encode("utf-8"))

    digest = hasher.hexdigest()[:32]
    return f"SEC-MSTR-V1-{digest}"


class SecurityMaster:
    """
    Immutable, Point-in-Time Security Master for NSE instruments.
    """
    def __init__(
        self,
        symbol_intervals: Sequence[SymbolInterval],
        surveillance_intervals: Optional[Sequence[SurveillanceInterval]] = None,
        corporate_actions: Optional[Sequence[CorporateAction]] = None,
        delisting_events: Optional[Sequence[DelistingEvent]] = None,
        isin_transitions: Optional[Sequence[ISINTransitionEvent]] = None,
        price_bands: Optional[Sequence[PriceBandRecord]] = None,
        price_band_intervals: Optional[Sequence[PriceBandInterval]] = None,
    ) -> None:
        self._symbol_intervals: Tuple[SymbolInterval, ...] = tuple(symbol_intervals)
        self._surveillance_intervals: Tuple[SurveillanceInterval, ...] = tuple(surveillance_intervals or ())
        self._corporate_actions: Tuple[CorporateAction, ...] = tuple(corporate_actions or ())
        self._delisting_events: Tuple[DelistingEvent, ...] = tuple(delisting_events or ())
        self._isin_transitions: Tuple[ISINTransitionEvent, ...] = tuple(isin_transitions or ())
        self._price_bands: Tuple[PriceBandRecord, ...] = tuple(price_bands or ())
        self._price_bands_by_isin_date: Dict[Tuple[str, datetime.date], PriceBandRecord] = {
            (b.isin, b.trade_date): b for b in self._price_bands
        }
        self._price_band_intervals: Tuple[PriceBandInterval, ...] = tuple(price_band_intervals or ())

        # Validate non-overlapping symbol intervals per ISIN
        by_isin: Dict[str, List[SymbolInterval]] = {}
        for s in self._symbol_intervals:
            by_isin.setdefault(s.isin, []).append(s)

        for isin, intervals in by_isin.items():
            sorted_intervals = sorted(intervals, key=lambda x: x.effective_from)
            for i in range(len(sorted_intervals) - 1):
                cur = sorted_intervals[i]
                nxt = sorted_intervals[i + 1]
                if cur.effective_to is None or cur.effective_to > nxt.effective_from:
                    raise SecurityMasterError(
                        f"Overlapping or unclosed symbol intervals detected for ISIN {isin}: {cur} overlaps {nxt}"
                    )

        # Validate non-overlapping price band intervals per ISIN (Rule 10.5, Audit §31 H-30)
        bands_by_isin: Dict[str, List[PriceBandInterval]] = {}
        for b in self._price_band_intervals:
            bands_by_isin.setdefault(b.isin, []).append(b)

        for isin, intervals in bands_by_isin.items():
            sorted_intervals = sorted(intervals, key=lambda x: x.effective_from)
            for i in range(len(sorted_intervals) - 1):
                cur = sorted_intervals[i]
                nxt = sorted_intervals[i + 1]
                if cur.effective_to is None or cur.effective_to > nxt.effective_from:
                    raise SecurityMasterError(
                        f"Overlapping or unclosed price band intervals detected for ISIN {isin}: {cur} overlaps {nxt}"
                    )

        # Build index for fast lookup
        self._intervals_by_isin = by_isin
        self._band_intervals_by_isin = bands_by_isin
        self._delistings_by_isin: Dict[str, DelistingEvent] = {}
        for d in self._delisting_events:
            if d.isin in self._delistings_by_isin:
                raise SecurityMasterError(f"Duplicate delisting event detected for ISIN {d.isin}")
            self._delistings_by_isin[d.isin] = d

        self._transitions_by_old_isin: Dict[str, ISINTransitionEvent] = {}
        for t in self._isin_transitions:
            if t.old_isin in self._transitions_by_old_isin:
                raise SecurityMasterError(f"Duplicate ISIN transition event detected for old ISIN {t.old_isin}")
            self._transitions_by_old_isin[t.old_isin] = t

        # Compute deterministic fingerprint
        self._fingerprint = compute_security_master_fingerprint(
            self._symbol_intervals,
            self._corporate_actions,
            self._delisting_events,
            self._isin_transitions,
            self._price_bands,
            self._price_band_intervals,
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def registered_isins(self) -> Tuple[str, ...]:
        return tuple(sorted(self._intervals_by_isin.keys()))

    def resolve_symbol(self, isin: str, as_of: datetime.date) -> Optional[SymbolInterval]:
        """Resolves the active symbol and series for an ISIN as-of date T."""
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")

        intervals = self._intervals_by_isin.get(isin, [])
        for interval in intervals:
            if interval.contains(as_of):
                return interval
        return None

    def resolve_isin_by_symbol(
        self,
        symbol: str,
        as_of: datetime.date,
        series: Optional[str] = None,
    ) -> Optional[str]:
        """Resolves active ISIN for a symbol and optional series as-of date T."""
        _validate_identifier(symbol, "symbol")
        _validate_date(as_of, "as_of")
        for isin, intervals in self._intervals_by_isin.items():
            for interval in intervals:
                if interval.symbol == symbol and interval.contains(as_of):
                    if series is None or interval.series == series:
                        if self.is_active(isin, as_of):
                            return isin
        return None

    def is_delisted(self, isin: str, as_of: datetime.date) -> bool:
        """Returns True if the security was delisted on or prior to date T."""
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")
        delisting = self._delistings_by_isin.get(isin)
        if delisting is not None and as_of >= delisting.effective_date:
            return True
        return False

    def is_transitioned_out(self, isin: str, as_of: datetime.date) -> bool:
        """Returns True if the ISIN was superseded by a new ISIN on or prior to date T."""
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")
        transition = self._transitions_by_old_isin.get(isin)
        if transition is not None and as_of >= transition.effective_date:
            return True
        return False

    def is_active(self, isin: str, as_of: datetime.date) -> bool:
        """
        Returns True if the security is currently active on date T:
        - SymbolInterval covers date T.
        - Has not been delisted on or before date T.
        - Has not been transitioned out to another ISIN on or before date T.
        """
        if self.is_delisted(isin, as_of):
            return False
        if self.is_transitioned_out(isin, as_of):
            return False
        return self.resolve_symbol(isin, as_of) is not None

    def active_isins_on(self, as_of: datetime.date) -> Tuple[str, ...]:
        """Returns ordered tuple of all ISINs active on date T (point-in-time universe)."""
        _validate_date(as_of, "as_of")
        active = [isin for isin in self.registered_isins if self.is_active(isin, as_of)]
        return tuple(sorted(active))

    def resolve_surveillance(self, isin: str, as_of: datetime.date) -> Tuple[SurveillanceInterval, ...]:
        """Returns all surveillance stages applicable to ISIN as-of date T."""
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")
        matches = [s for s in self._surveillance_intervals if s.isin == isin and s.contains(as_of)]
        return tuple(matches)

    def get_corporate_actions(self, isin: str, up_to: Optional[datetime.date] = None) -> Tuple[CorporateAction, ...]:
        """Returns corporate actions for an ISIN up to an optional date, sorted by ex-date."""
        _validate_identifier(isin, "isin")
        _validate_date(up_to, "up_to")
        actions = [
            ca for ca in self._corporate_actions
            if ca.isin == isin and (up_to is None or ca.ex_date <= up_to)
        ]
        return tuple(sorted(actions, key=lambda ca: ca.ex_date))

    def get_price_band(
        self,
        isin: str,
        as_of: datetime.date,
        prev_close: Optional[Decimal] = None,
    ) -> Optional[PriceBandRecord]:
        """
        Returns PriceBandRecord for an ISIN on session date as_of.
        Performs discrete daily lookup first; falls back to time-varying half-open PriceBandIntervals
        per AGENTS.md Rule 10.5, Audit §31 H-30, and Audit §35 H-40.
        If prev_close is provided, derives concrete numeric circuit limits from band_percentage.
        """
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")

        record: Optional[PriceBandRecord] = None

        # 1. Discrete daily record lookup
        discrete_rec = self._price_bands_by_isin_date.get((isin, as_of))
        if discrete_rec is not None:
            record = discrete_rec
        else:
            # 2. Time-varying half-open interval lookup [effective_from, effective_to)
            intervals = self._band_intervals_by_isin.get(isin, [])
            for interval in intervals:
                if interval.contains(as_of):
                    sym_interval = self.resolve_symbol(isin, as_of)
                    series = sym_interval.series if sym_interval else "EQ"
                    src_desc = interval.source_descriptor
                    if src_desc is None and interval.circular_ref:
                        src_desc = PriceBandSourceDescriptor(
                            source_type=PriceBandPublicationSource.NSE_SURVEILLANCE_CIRCULAR,
                            publication_name="NSE_SURVEILLANCE_CIRCULAR",
                            archive_url_template="https://archives.nseindia.com/circulars",
                            retrieval_frequency="EVENT_DRIVEN",
                            circular_ref=interval.circular_ref,
                            description=f"Time-varying price band interval for {isin}",
                        )
                    record = PriceBandRecord(
                        isin=isin,
                        trade_date=as_of,
                        series=series,
                        upper_circuit_limit=None,
                        lower_circuit_limit=None,
                        band_percentage=interval.band_percentage,
                        is_unconstrained=interval.is_unconstrained,
                        source_descriptor=src_desc,
                        source_ref=interval.circular_ref,
                    )
                    break

        if record is not None and prev_close is not None:
            record = record.derive_limits(prev_close)

        return record

    @property
    def price_bands(self) -> Tuple[PriceBandRecord, ...]:
        return self._price_bands

    @property
    def price_band_intervals(self) -> Tuple[PriceBandInterval, ...]:
        return self._price_band_intervals


def build_production_security_master() -> SecurityMaster:
    """
    Builds the production reference Security Master seeded with initial instruments:
    - INFY (INE009A01021): Continuous EQ rolling equity.
    - RELIANCE (INE002A01018): Continuous EQ rolling equity.
    - HDFC (INE001A01036): Merged into HDFC Bank, delisted on 2023-07-13 (pruned on 2023-07-13).
    - COCHINSHIP Old (INE704P01017): Listed 2017-08-11, split 2:1 and transitioned to INE704P01025 on 2024-01-10.
    - COCHINSHIP New (INE704P01025): Effective on 2024-01-10 onwards.
    """
    symbol_intervals = [
        # INFY
        SymbolInterval(
            isin="INE009A01021",
            symbol="INFY",
            series="EQ",
            effective_from=datetime.date(2015, 1, 1),
            effective_to=None,
        ),
        # RELIANCE
        SymbolInterval(
            isin="INE002A01018",
            symbol="RELIANCE",
            series="EQ",
            effective_from=datetime.date(2015, 1, 1),
            effective_to=None,
        ),
        # HDFC (delisted / merged into HDFC Bank effective 2023-07-13)
        SymbolInterval(
            isin="INE001A01036",
            symbol="HDFC",
            series="EQ",
            effective_from=datetime.date(2015, 1, 1),
            effective_to=datetime.date(2023, 7, 13),
        ),
        # COCHINSHIP Old ISIN
        SymbolInterval(
            isin="INE704P01017",
            symbol="COCHINSHIP",
            series="EQ",
            effective_from=datetime.date(2017, 8, 11),
            effective_to=datetime.date(2024, 1, 10),
        ),
        # COCHINSHIP New ISIN
        SymbolInterval(
            isin="INE704P01025",
            symbol="COCHINSHIP",
            series="EQ",
            effective_from=datetime.date(2024, 1, 10),
            effective_to=None,
        ),
    ]

    corporate_actions = [
        # INFY 1:1 Bonus ex-date 2018-09-12 (1 old share gives 1 additional share, total 2)
        CorporateAction(
            isin="INE009A01021",
            ex_date=datetime.date(2018, 9, 12),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="NSE/CML/2018/BONUS_INFY",
            description="INFY 1:1 Bonus Issue",
        ),
        # RELIANCE 1:1 Bonus ex-date 2017-09-07
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2017, 9, 7),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="NSE/CML/2017/BONUS_RIL",
            description="RELIANCE 1:1 Bonus Issue",
        ),
        # RELIANCE 1:1 Bonus ex-date 2024-10-28
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2024, 10, 28),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="NSE/CML/2024/BONUS_RIL2",
            description="RELIANCE 1:1 Bonus Issue",
        ),
        # COCHINSHIP 2:1 Stock Split (Rs 10 to Rs 5) ex-date 2024-01-10
        CorporateAction(
            isin="INE704P01017",
            ex_date=datetime.date(2024, 1, 10),
            action_type=CorporateActionType.ISIN_TRANSITION,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            old_isin="INE704P01017",
            new_isin="INE704P01025",
            circular_ref="NSE/CML/60114",
            description="COCHIN SHIPYARD Sub-Division from Rs 10 to Rs 5",
        ),
    ]

    delisting_events = [
        DelistingEvent(
            isin="INE001A01036",
            effective_date=datetime.date(2023, 7, 13),
            reason="MERGER_INTO_HDFC_BANK",
            circular_ref="NSE/CML/57531",
        )
    ]

    isin_transitions = [
        ISINTransitionEvent(
            old_isin="INE704P01017",
            new_isin="INE704P01025",
            effective_date=datetime.date(2024, 1, 10),
            reason="STOCK_SPLIT_SUB_DIVISION",
            circular_ref="NSE/CML/60114",
        )
    ]

    # Authoritative Price Band Intervals (Rule 10.5, Audit §27 H-4, §31 H-30)
    fo_source = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_FO_UNDERLYING_PRICE_BANDS",
        archive_url_template="https://archives.nseindia.com/content/fo/fo_sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/FAOP/60350",
        description="NSE F&O Underlyings Dynamic Flexing Price Bands",
    )
    cash_source = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_PRICE_BANDS",
        archive_url_template="https://archives.nseindia.com/content/equities/sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/SURV/PRICE_BANDS_2024",
        description="NSE Cash Equity Daily Price Bands 20%",
    )

    price_band_intervals = [
        # INFY (F&O stock: dynamic flexing band, exchange publishes "No Band", Audit §35 H-41)
        PriceBandInterval(
            isin="INE009A01021",
            band_percentage=None,
            effective_from=datetime.date(2015, 1, 1),
            effective_to=None,
            is_unconstrained=True,
            source_descriptor=fo_source,
            circular_ref="NSE/FAOP/60350",
        ),
        # RELIANCE (F&O stock: dynamic flexing band, exchange publishes "No Band", Audit §35 H-41)
        PriceBandInterval(
            isin="INE002A01018",
            band_percentage=None,
            effective_from=datetime.date(2015, 1, 1),
            effective_to=None,
            is_unconstrained=True,
            source_descriptor=fo_source,
            circular_ref="NSE/FAOP/60350",
        ),
        # HDFC (F&O stock until merger on 2023-07-13, Audit §35 H-41)
        PriceBandInterval(
            isin="INE001A01036",
            band_percentage=None,
            effective_from=datetime.date(2015, 1, 1),
            effective_to=datetime.date(2023, 7, 13),
            is_unconstrained=True,
            source_descriptor=fo_source,
            circular_ref="NSE/FAOP/57531",
        ),
        # COCHINSHIP Old ISIN (standard 20% price band)
        PriceBandInterval(
            isin="INE704P01017",
            band_percentage=Decimal("20.00"),
            effective_from=datetime.date(2017, 8, 11),
            effective_to=datetime.date(2024, 1, 10),
            is_unconstrained=False,
            source_descriptor=cash_source,
            circular_ref="NSE/SURV/PRICE_BANDS_2017",
        ),
        # COCHINSHIP New ISIN (standard 20% price band)
        PriceBandInterval(
            isin="INE704P01025",
            band_percentage=Decimal("20.00"),
            effective_from=datetime.date(2024, 1, 10),
            effective_to=None,
            is_unconstrained=False,
            source_descriptor=cash_source,
            circular_ref="NSE/SURV/PRICE_BANDS_2024",
        ),
    ]

    # Discrete daily price bands (Audit §25 G-6, §26 Wave 1, §31 H-30)
    # COCHINSHIP 2:1 Stock Split ex-date 2024-01-10: 20% Upper Circuit at Rs. 802.80, Lower Circuit at Rs. 535.20
    split_circuit_source = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_SURVEILLANCE_CIRCULAR,
        publication_name="NSE_EX_SPLIT_CIRCUIT_ADJUSTMENT",
        archive_url_template="https://archives.nseindia.com/content/equities/sec_list.csv",
        retrieval_frequency="EVENT_DRIVEN",
        circular_ref="NSE/CML/60114",
        description="Cochin Shipyard 2:1 stock split circuit limit adjustment",
    )
    price_bands = [
        PriceBandRecord(
            isin="INE704P01025",
            trade_date=datetime.date(2024, 1, 10),
            series="EQ",
            upper_circuit_limit=Decimal("802.80"),
            lower_circuit_limit=Decimal("535.20"),
            band_percentage=Decimal("20.00"),
            is_unconstrained=False,
            source_descriptor=split_circuit_source,
            source_ref="NSE/CML/60114",
        )
    ]

    return SecurityMaster(
        symbol_intervals=symbol_intervals,
        corporate_actions=corporate_actions,
        delisting_events=delisting_events,
        isin_transitions=isin_transitions,
        price_bands=price_bands,
        price_band_intervals=price_band_intervals,
    )

