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

from bisect import bisect_right
from collections import defaultdict
import csv
from dataclasses import dataclass, replace
import datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple, Union

if TYPE_CHECKING:
    from signal_core.storage.calendar import TradingCalendar
    from signal_core.storage.silver import SilverStorage

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
    NORMAL = "NORMAL"
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
    MERGER = "MERGER"
    ISIN_TRANSITION = "ISIN_TRANSITION"
    CONSOLIDATION = "CONSOLIDATION"
    DIVIDEND = "DIVIDEND"
    # Audit §95.7 Ruling 2 / §95.10 item 5 / §13.2: a demerger delivers shares in a resulting entity.
    # The archive attests the event but never the consideration ratio, so the type exists to constrain
    # a held position (exit before the event) rather than to invent a share restatement.
    DEMERGER = "DEMERGER"


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


def _interval_spans_overlap(a: "SymbolInterval", b: "SymbolInterval") -> bool:
    """True when two half-open spans share at least one date."""
    if a.effective_to is not None and b.effective_from >= a.effective_to:
        return False
    if b.effective_to is not None and a.effective_from >= b.effective_to:
        return False
    return True


def _span_is_contained(outer: "SymbolInterval", inner: "SymbolInterval") -> bool:
    """True when `inner`'s span lies wholly inside `outer`'s span (open ends included)."""
    if inner.effective_from < outer.effective_from:
        return False
    if outer.effective_to is None:
        return True
    if inner.effective_to is None:
        return False
    return inner.effective_to <= outer.effective_to


def apply_interval_restatements(intervals: Sequence["SymbolInterval"]) -> List["SymbolInterval"]:
    """
    Returns the active rows of an append-only interval log (AGENTS.md §10.1, Audit §90.7 Ruling 2).

    A correction never edits or deletes the row it corrects: the restatement is appended carrying its
    own `effective_from`/`effective_to`, and it supersedes an earlier row for the same ISIN when it
    appears later in the file and its span is contained in that row's span. The superseded row stays in
    the artifact as history and is dropped only from the resolution index.

    Two rules fail closed, because between them they distinguish a restatement from an accidental
    overlap: a later row may overlap an earlier one only as a *contained* appendant, and the surviving
    rows for an ISIN may not overlap each other at all.
    """
    rows = list(intervals)
    by_isin: Dict[str, List[Tuple[int, "SymbolInterval"]]] = {}
    for index, row in enumerate(rows):
        by_isin.setdefault(row.isin, []).append((index, row))

    superseded: Set[int] = set()
    clipped: List["SymbolInterval"] = []
    for isin, entries in by_isin.items():
        live: List[Tuple[int, "SymbolInterval"]] = []
        for index, row in entries:
            survivors: List[Tuple[int, "SymbolInterval"]] = []
            for live_index, live_row in live:
                if not _interval_spans_overlap(live_row, row):
                    survivors.append((live_index, live_row))
                    continue
                if not _span_is_contained(live_row, row):
                    raise SecurityMasterError(
                        f"Overlapping or unclosed symbol intervals detected for ISIN {isin}: {live_row} "
                        f"overlaps {row} without being an append that restates a part of it (§10.1)"
                    )
                if live_index >= 0:
                    superseded.add(live_index)
                # The append restates only the slice it covers. A row that is restated in part keeps the
                # uncovered remainder in force, so a correction never silently erases a valid session.
                if live_row.effective_from < row.effective_from:
                    survivors.append((-1, replace(live_row, effective_to=row.effective_from)))
                if row.effective_to is not None and (
                    live_row.effective_to is None or row.effective_to < live_row.effective_to
                ):
                    survivors.append((-1, replace(live_row, effective_from=row.effective_to)))
            live = survivors + [(index, row)]
            live.sort(key=lambda pair: (pair[1].effective_from, pair[0]))
            for (_i, cur), (_j, nxt) in zip(live, live[1:]):
                if _interval_spans_overlap(cur, nxt):
                    raise SecurityMasterError(
                        f"Overlapping or unclosed symbol intervals detected for ISIN {isin}: {cur} "
                        f"overlaps {nxt}; neither row restates the other (§10.1)"
                    )
        clipped.extend(row for index, row in live if index < 0)

    return [row for index, row in enumerate(rows) if index not in superseded] + clipped


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
    circular_ref: Optional[str] = None

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
        if self.circular_ref is not None:
            _validate_identifier(self.circular_ref, "circular_ref")

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
    ratio_numerator: Decimal = Decimal("1")
    ratio_denominator: Decimal = Decimal("1")
    dividend_amount: Optional[Decimal] = None
    old_isin: Optional[str] = None
    new_isin: Optional[str] = None
    circular_ref: Optional[str] = None
    description: Optional[str] = None
    record_date: Optional[datetime.date] = None
    symbol: Optional[str] = None
    provenance: Optional[str] = None
    delisting_price: Optional[Decimal] = None
    # Audit §95.7 Ruling 2 / §95.10 item 4: an adjustment row is admissible only where the committed
    # archive attests it, so a row carries the digest and artifact of the payload it came from.
    source_digest: Optional[str] = None
    source_artifact: Optional[str] = None
    # A corrected or unattested row is superseded by an appended restatement rather than edited away
    # (§10.1): the loader still returns it, and every consumer that applies a price ratio filters it.
    superseded: bool = False
    restatement_ref: Optional[str] = None

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

        if self.action_type == CorporateActionType.DIVIDEND:
            if self.dividend_amount is None:
                raise SecurityMasterError(f"DIVIDEND requires positive finite Decimal dividend_amount for ISIN {self.isin}")
            if (
                isinstance(self.dividend_amount, bool)
                or not isinstance(self.dividend_amount, Decimal)
                or not self.dividend_amount.is_finite()
                or self.dividend_amount <= Decimal("0.00")
            ):
                raise SecurityMasterError(f"dividend_amount must be positive finite Decimal, got {self.dividend_amount!r}")
        else:
            if self.dividend_amount is not None:
                raise SecurityMasterError(f"dividend_amount is only permitted for action_type DIVIDEND, got {self.action_type.value}")

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
                if self.new_isin == self.isin:
                    raise SecurityMasterError(f"new_isin cannot match isin: {self.isin} (Finding H-96)")

        if self.delisting_price is not None:
            if (
                isinstance(self.delisting_price, bool)
                or not isinstance(self.delisting_price, Decimal)
                or not self.delisting_price.is_finite()
                or self.delisting_price < Decimal("0.00")
            ):
                raise SecurityMasterError(f"delisting_price must be non-negative finite Decimal, got {self.delisting_price!r}")

        if self.action_type == CorporateActionType.MERGER:
            if not self.new_isin:
                raise SecurityMasterError("MERGER requires new_isin (Finding H-98).")

        if self.circular_ref is not None:
            _validate_identifier(self.circular_ref, "circular_ref")
        if self.symbol is not None:
            _validate_identifier(self.symbol, "symbol")
        if self.provenance is not None:
            _validate_identifier(self.provenance, "provenance")
        if self.source_digest is not None:
            digest = str(self.source_digest).strip().lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise SecurityMasterError(
                    f"source_digest must be the 64-hex sha256 of a committed archive payload, got "
                    f"{self.source_digest!r} for {self.isin} {self.ex_date} (Audit §95.7 Ruling 2)"
                )
        if not isinstance(self.superseded, bool):
            raise SecurityMasterError(f"superseded must be boolean, got {self.superseded!r}")
        if self.action_type == CorporateActionType.DEMERGER and self.new_isin is not None:
            raise SecurityMasterError(
                "DEMERGER carries no new_isin: the consideration is a different security, and a held "
                "position is exited rather than re-keyed onto an ISIN this table does not price (§13.2)"
            )

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
        if self.dividend_amount is not None:
            d["dividend_amount"] = str(self.dividend_amount)
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
        if self.symbol is not None:
            d["symbol"] = self.symbol
        if self.provenance is not None:
            d["provenance"] = self.provenance
        if self.delisting_price is not None:
            d["delisting_price"] = str(self.delisting_price)
        if self.source_digest is not None:
            d["source_digest"] = self.source_digest
        if self.source_artifact is not None:
            d["source_artifact"] = self.source_artifact
        if self.superseded:
            d["superseded"] = True
        if self.restatement_ref is not None:
            d["restatement_ref"] = self.restatement_ref
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorporateAction":
        """Deserializes CorporateAction from mapping."""
        rec_d = datetime.date.fromisoformat(data["record_date"]) if data.get("record_date") else None
        div_amt = Decimal(str(data["dividend_amount"])) if data.get("dividend_amount") else None
        delist_amt = Decimal(str(data["delisting_price"])) if data.get("delisting_price") else None
        return cls(
            isin=str(data["isin"]),
            ex_date=datetime.date.fromisoformat(data["ex_date"]),
            action_type=CorporateActionType(str(data["action_type"])),
            ratio_numerator=Decimal(str(data.get("ratio_numerator", "1"))),
            ratio_denominator=Decimal(str(data.get("ratio_denominator", "1"))),
            dividend_amount=div_amt,
            old_isin=str(data["old_isin"]) if data.get("old_isin") else None,
            new_isin=str(data["new_isin"]) if data.get("new_isin") else None,
            circular_ref=str(data["circular_ref"]) if data.get("circular_ref") else None,
            description=str(data["description"]) if data.get("description") else None,
            record_date=rec_d,
            symbol=str(data["symbol"]) if data.get("symbol") else None,
            provenance=str(data["provenance"]) if data.get("provenance") else None,
            delisting_price=delist_amt,
            source_digest=str(data["source_digest"]) if data.get("source_digest") else None,
            source_artifact=str(data["source_artifact"]) if data.get("source_artifact") else None,
            superseded=bool(data.get("superseded", False)),
            restatement_ref=str(data["restatement_ref"]) if data.get("restatement_ref") else None,
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
    symbol_intervals: Union[Any, Sequence[SymbolInterval]],
    corporate_actions: Optional[Sequence[CorporateAction]] = None,
    delisting_events: Optional[Sequence[DelistingEvent]] = None,
    isin_transitions: Optional[Sequence[ISINTransitionEvent]] = None,
    price_bands: Optional[Sequence[PriceBandRecord]] = None,
    price_band_intervals: Optional[Sequence[PriceBandInterval]] = None,
) -> str:
    """Computes a deterministic SHA-256 fingerprint for security master state (Finding N-104)."""
    if isinstance(symbol_intervals, SecurityMaster):
        return symbol_intervals.fingerprint

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
    sorted_ca = sorted(corporate_actions or (), key=lambda ca: (ca.isin, ca.ex_date, ca.action_type.value))
    for ca in sorted_ca:
        row = f"{ca.isin},{ca.ex_date.isoformat()},{ca.action_type.value},{ca.ratio_numerator},{ca.ratio_denominator}\n"
        hasher.update(row.encode("utf-8"))

    # 3. Delistings
    hasher.update(b"DELISTINGS:\n")
    sorted_del = sorted(delisting_events or (), key=lambda d: (d.isin, d.effective_date))
    for d in sorted_del:
        row = f"{d.isin},{d.effective_date.isoformat()},{d.reason}\n"
        hasher.update(row.encode("utf-8"))

    # 4. Transitions
    hasher.update(b"TRANSITIONS:\n")
    sorted_tr = sorted(isin_transitions or (), key=lambda t: (t.old_isin, t.effective_date))
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

        # Resolve the append-only interval log to its active rows (Audit §90.7 Ruling 2): a restatement
        # is appended, never edited over the row it corrects, so superseded rows stay in the artifact.
        active_intervals = apply_interval_restatements(self._symbol_intervals)

        by_isin: Dict[str, List[SymbolInterval]] = {}
        for s in active_intervals:
            by_isin.setdefault(s.isin, []).append(s)

        # Validate non-overlapping symbol intervals per (symbol, series) (Audit §39 H-50)
        by_symbol: Dict[Tuple[str, str], List[SymbolInterval]] = {}
        for s in active_intervals:
            by_symbol.setdefault((s.symbol, s.series), []).append(s)

        for (sym, srs), intervals in by_symbol.items():
            sorted_intervals = sorted(intervals, key=lambda x: x.effective_from)
            for i in range(len(sorted_intervals) - 1):
                cur = sorted_intervals[i]
                nxt = sorted_intervals[i + 1]
                if cur.effective_to is None or cur.effective_to > nxt.effective_from:
                    raise SecurityMasterError(
                        f"Overlapping or unclosed symbol intervals detected for symbol '{sym}' (series {srs}): {cur} overlaps {nxt}"
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

        # Validate discrete price bands against time-varying price band intervals (Audit §38 H-49)
        for b in self._price_bands:
            self._validate_discrete_price_band_against_intervals(b, bands_by_isin)

        # Build index for fast lookup. Rows are ordered by `effective_from` so a resolution as-of T can
        # bisect instead of scanning every interval of every ISIN (§90.9 item 2).
        self._intervals_by_isin: Dict[str, List[SymbolInterval]] = {
            isin: sorted(rows, key=lambda s: s.effective_from, reverse=True)
            for isin, rows in by_isin.items()
        }
        self._band_intervals_by_isin = bands_by_isin
        by_symbol_rows: Dict[str, List[SymbolInterval]] = {}
        for s in active_intervals:
            by_symbol_rows.setdefault(s.symbol, []).append(s)
        self._intervals_by_symbol: Dict[str, List[SymbolInterval]] = {
            symbol: sorted(rows, key=lambda s: s.effective_from)
            for symbol, rows in by_symbol_rows.items()
        }
        self._symbol_starts_by_symbol: Dict[str, List[datetime.date]] = {
            symbol: [s.effective_from for s in rows]
            for symbol, rows in self._intervals_by_symbol.items()
        }
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

        # Newest-first order: the first row that starts on or before T is the only one that can cover T,
        # because the active rows of an ISIN do not overlap.
        intervals = self._intervals_by_isin.get(isin, [])
        for interval in intervals:
            if interval.effective_from > as_of:
                continue
            return interval if interval.contains(as_of) else None
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
        candidates = self._intervals_by_symbol.get(symbol, [])
        starts = self._symbol_starts_by_symbol.get(symbol, [])
        matches: List[str] = []
        for interval in candidates[: bisect_right(starts, as_of)]:
            if interval.contains(as_of):
                if series is None or interval.series == series:
                    if self.is_active(interval.isin, as_of):
                        if interval.isin not in matches:
                            matches.append(interval.isin)
        if len(matches) > 1:
            raise SecurityMasterError(
                f"Ambiguous active ISINs for symbol '{symbol}' on date {as_of}: {matches}"
            )
        return matches[0] if matches else None

    @property
    def isin_transitions(self) -> Tuple[ISINTransitionEvent, ...]:
        """Returns the effective-dated identity transitions known to the master (Audit §77.11)."""
        return tuple(self._isin_transitions)

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

    def has_surveillance_coverage(self, isin: str, as_of: Optional[datetime.date] = None) -> bool:
        """
        Returns True if the security has explicit surveillance coverage per AGENTS.md §5.2, §10.8 (Findings H-87, N-92).
        If as_of date is provided, verifies that as_of falls within [effective_from, effective_to) of at least one interval.
        """
        _validate_identifier(isin, "isin")
        if as_of is not None:
            _validate_date(as_of, "as_of")
            return any(s.isin == isin and s.contains(as_of) for s in self._surveillance_intervals)
        return any(s.isin == isin for s in self._surveillance_intervals)

    @property
    def surveillance_coverage_count(self) -> int:
        """Returns the count of registered universe ISINs that have surveillance coverage (Finding H-87)."""
        covered = {s.isin for s in self._surveillance_intervals}
        return len(set(self.registered_isins).intersection(covered))

    def validate_hold_surveillance_coverage(self, isin: str, as_of: datetime.date) -> None:
        """Fails closed if a held security has no surveillance coverage as-of date T (Finding H-87)."""
        if not self.has_surveillance_coverage(isin, as_of):
            raise SecurityMasterError(
                f"Held security {isin} has no authoritative surveillance coverage as-of {as_of} "
                f"(AGENTS.md §5.2, §10.8, Finding H-87). Refuses valuation / evaluation of unsurveilled position."
            )

    def resolve_surveillance(
        self,
        isin: str,
        as_of: datetime.date,
        require_coverage: bool = False,
    ) -> Tuple[SurveillanceInterval, ...]:
        """Returns all surveillance stages applicable to ISIN as-of date T."""
        _validate_identifier(isin, "isin")
        _validate_date(as_of, "as_of")
        if require_coverage and not self.has_surveillance_coverage(isin, as_of):
            raise SecurityMasterError(
                f"Security {isin} lacks authoritative surveillance coverage as-of {as_of} "
                f"(AGENTS.md §5.2, §10.8, Finding H-87)."
            )
        matches = [s for s in self._surveillance_intervals if s.isin == isin and s.contains(as_of)]
        return tuple(matches)

    def has_corporate_action_coverage(self, isin: str) -> bool:
        """Returns True if the security is registered in the SecurityMaster store (Finding CA-1)."""
        _validate_identifier(isin, "isin")
        return isin in self._intervals_by_isin or any(ca.isin == isin for ca in self._corporate_actions)

    def corporate_actions(self) -> Tuple[CorporateAction, ...]:
        """Every committed corporate-action row this master was built with (read-only)."""
        return self._corporate_actions

    def get_corporate_actions(
        self,
        isin: str,
        up_to: Optional[datetime.date] = None,
        require_registration: bool = False,
    ) -> Tuple[CorporateAction, ...]:
        """
        Returns corporate actions for an ISIN up to an optional date, sorted by ex-date.
        If require_registration is True, fails closed (SecurityMasterError) if ISIN is not registered in store.
        A name with no events is distinguishable from a name with no row per CA-1.
        """
        _validate_identifier(isin, "isin")
        _validate_date(up_to, "up_to")
        if require_registration and not self.has_corporate_action_coverage(isin):
            raise SecurityMasterError(f"ISIN '{isin}' is not registered in SecurityMaster (Finding CA-1).")
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

    @staticmethod
    def _validate_discrete_price_band_against_intervals(
        b: PriceBandRecord,
        bands_by_isin: Mapping[str, Sequence[PriceBandInterval]],
    ) -> None:
        """
        Validates discrete PriceBandRecord against covering PriceBandIntervals per Audit §38 H-49.
        Discrete daily observations must not contradict the governing regulatory interval.
        """
        intervals = bands_by_isin.get(b.isin, [])
        for interval in intervals:
            if interval.contains(b.trade_date):
                if interval.is_unconstrained:
                    if not b.is_unconstrained:
                        raise SecurityMasterError(
                            f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} has is_unconstrained=False, "
                            f"contradicting covering unconstrained interval: record={b} vs interval={interval} (Finding H-49)."
                        )
                    if b.band_percentage is not None:
                        raise SecurityMasterError(
                            f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} specifies band_percentage={b.band_percentage}, "
                            f"contradicting covering unconstrained interval: record={b} vs interval={interval} (Finding H-49)."
                        )
                    if b.upper_circuit_limit is not None or b.lower_circuit_limit is not None:
                        raise SecurityMasterError(
                            f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} specifies circuit limits "
                            f"[{b.lower_circuit_limit}, {b.upper_circuit_limit}], contradicting covering unconstrained interval: "
                            f"record={b} vs interval={interval} (Finding H-49)."
                        )
                else:
                    if b.is_unconstrained:
                        raise SecurityMasterError(
                            f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} claims is_unconstrained=True, "
                            f"contradicting covering constrained interval with band_percentage {interval.band_percentage}: "
                            f"record={b} vs interval={interval} (Finding H-49)."
                        )
                    if interval.band_percentage is not None:
                        if b.band_percentage is not None and abs(b.band_percentage - interval.band_percentage) > Decimal("0.01"):
                            raise SecurityMasterError(
                                f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} band_percentage {b.band_percentage} "
                                f"contradicts covering interval band_percentage {interval.band_percentage}: "
                                f"record={b} vs interval={interval} (Finding H-49)."
                            )
                        if b.upper_circuit_limit is not None and b.lower_circuit_limit is not None:
                            implied_pct = ((b.upper_circuit_limit - b.lower_circuit_limit) / (b.upper_circuit_limit + b.lower_circuit_limit)) * Decimal("100")
                            if abs(implied_pct - interval.band_percentage) > Decimal("1.00"):
                                raise SecurityMasterError(
                                    f"Discrete PriceBandRecord for {b.isin} on {b.trade_date} limits imply band {implied_pct}%, "
                                    f"contradicting covering interval band_percentage {interval.band_percentage}%: "
                                    f"record={b} vs interval={interval} (Finding H-49)."
                                )
                break

    def validate_price_band_record(self, record: PriceBandRecord) -> None:
        """
        Public validator enforcing interval consistency for an incoming discrete PriceBandRecord (Finding H-49).
        Used by storage boundaries (e.g. SilverStorage.write_price_band_partition) to prevent unvalidated discrete records.
        """
        self._validate_discrete_price_band_against_intervals(record, self._band_intervals_by_isin)

    def load_from_silver_price_bands(
        self,
        silver: "SilverStorage",
        dates: Sequence[datetime.date],
        calendar: Optional["TradingCalendar"] = None,
    ) -> "SecurityMaster":
        """
        Loads daily price band partitions from Silver storage for the given dates,
        validates them against covering intervals, and returns an updated SecurityMaster (Finding H-49).
        Single authoritative reader from Silver storage to Security Master.
        """
        collected_records: List[PriceBandRecord] = []
        for d in dates:
            if calendar is not None and not calendar.is_session(d):
                continue
            if silver.price_band_partition_exists(d):
                part_records = silver.read_price_band_partition(d)
                collected_records.extend(part_records)
        return self.with_price_bands(collected_records)

    def with_price_bands(self, price_bands: Sequence[PriceBandRecord]) -> "SecurityMaster":
        """
        Returns a new SecurityMaster with additional discrete PriceBandRecords attached (Audit §37 H-44).
        Deduplicates against existing discrete price bands (new records take precedence).
        """
        existing_bands_by_key = {(b.isin, b.trade_date): b for b in self._price_bands}
        for b in price_bands:
            existing_bands_by_key[(b.isin, b.trade_date)] = b

        merged_bands = tuple(sorted(existing_bands_by_key.values(), key=lambda b: (b.isin, b.trade_date)))

        return SecurityMaster(
            symbol_intervals=self._symbol_intervals,
            surveillance_intervals=self._surveillance_intervals,
            corporate_actions=self._corporate_actions,
            delisting_events=self._delisting_events,
            isin_transitions=self._isin_transitions,
            price_bands=merged_bands,
            price_band_intervals=self._price_band_intervals,
        )


def load_cash_universe_symbol_intervals(csv_path: Optional[Union[str, Path]] = None) -> Tuple[SymbolInterval, ...]:
    """
    Loads authoritative effective-dated SymbolIntervals for the NSE Cash Equity (EQ) universe
    from committed reference artifact per AGENTS.md Rule 10.4, Audit §38.3 (H-44), and Audit §39 (H-50, H-51).
    Fails closed naming the artifact and corrupt row on any missing file or schema violation.
    """
    if csv_path is None:
        p = Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "cash_equity_symbol_intervals.csv"
    else:
        p = Path(csv_path)

    if not p.is_file():
        raise FileNotFoundError(f"Cash universe symbol intervals artifact not found at: {p}")

    intervals: List[SymbolInterval] = []
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        line_no = 1
        for row in reader:
            line_no += 1
            try:
                ef = datetime.date.fromisoformat(row["effective_from"].strip())
                et = datetime.date.fromisoformat(row["effective_to"].strip()) if row.get("effective_to") and row["effective_to"].strip() else None
                intervals.append(
                    SymbolInterval(
                        isin=row["isin"].strip().upper(),
                        symbol=row["symbol"].strip().upper(),
                        series=row["series"].strip().upper(),
                        effective_from=ef,
                        effective_to=et,
                    )
                )
            except Exception as exc:
                raise SecurityMasterError(
                    f"Corrupt row {line_no} in cash universe artifact '{p.name}': {exc}"
                ) from exc
    # The artifact is an append-only interval log (§10.1, §90.7 Ruling 2): a restated row supersedes the
    # row it corrects and the superseded row is retained as history, so callers see the active rows.
    return tuple(apply_interval_restatements(intervals))


def load_surveillance_intervals(path: Optional[Union[str, Path]] = None) -> Tuple[SurveillanceInterval, ...]:
    """
    Loads authoritative effective-dated SurveillanceIntervals (ASM/GSM/ESM)
    from committed reference artifact per AGENTS.md Rule 5.2, 10.5, 10.8 and Audit §59.7 Item 7, §60.6 Item 3.
    Fails closed (FileNotFoundError) if artifact file is absent.
    """
    if path is None:
        p = Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "surveillance_intervals.jsonl"
    else:
        p = Path(path)

    if not p.is_file():
        raise FileNotFoundError(f"Surveillance intervals artifact not found at: {p}")

    intervals: List[SurveillanceInterval] = []
    with open(p, "r", encoding="utf-8") as f:
        line_no = 0
        for line in f:
            line_no += 1
            line_str = line.strip()
            if not line_str:
                continue
            try:
                row = json.loads(line_str)
                ef = datetime.date.fromisoformat(row["effective_from"].strip())
                et = datetime.date.fromisoformat(row["effective_to"].strip()) if row.get("effective_to") and str(row["effective_to"]).strip() else None
                circ_ref = row.get("circular_ref")
                circ_ref_str = str(circ_ref).strip() if circ_ref and str(circ_ref).strip() else None
                intervals.append(
                    SurveillanceInterval(
                        isin=row["isin"].strip().upper(),
                        framework=row["framework"].strip().upper(),
                        stage=SurveillanceStage(row["stage"].strip().upper()),
                        effective_from=ef,
                        effective_to=et,
                        circular_ref=circ_ref_str,
                    )
                )
            except Exception as exc:
                raise SecurityMasterError(
                    f"Corrupt row {line_no} in surveillance intervals artifact '{p.name}': {exc}"
                ) from exc
    return tuple(intervals)


def load_corporate_actions(path: Optional[Union[str, Path]] = None) -> Tuple[CorporateAction, ...]:
    """
    Loads authoritative CorporateAction records (splits, bonuses, dividends)
    from committed reference artifact per AGENTS.md Rule 5.4, 10.3, 13.2 and Audit §59.7 Item 6, §60.6 Item 4.
    Fails closed (FileNotFoundError) if artifact file is absent.
    """
    if path is None:
        p = Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "corporate_actions.jsonl"
    else:
        p = Path(path)

    if not p.is_file():
        raise FileNotFoundError(f"Corporate actions artifact not found at: {p}")

    actions: List[CorporateAction] = []
    with open(p, "r", encoding="utf-8") as f:
        line_no = 0
        for line in f:
            line_no += 1
            line_str = line.strip()
            if not line_str:
                continue
            try:
                row = json.loads(line_str)
                actions.append(CorporateAction.from_dict(row))
            except Exception as exc:
                raise SecurityMasterError(
                    f"Corrupt row {line_no} in corporate actions artifact '{p.name}': {exc}"
                ) from exc
    return tuple(actions)


def load_cash_universe_price_band_intervals(
    sec_list_path: Optional[Union[str, Path]] = None,
    cash_intervals_path: Optional[Union[str, Path]] = None,
) -> Tuple[PriceBandInterval, ...]:
    """
    Loads authoritative PriceBandIntervals for the NSE cash equity universe per AGENTS.md Rule 10.5,
    Audit §31 H-30, §35 H-40, §63.6 Item 6 (CA-3).
    Sourced from NSE daily price band report sec_list_20240116.csv with circular ref NSE/CML/SEC_LIST_20240116.
    F&O dynamic flexing bands ('No Band') are mapped to is_unconstrained=True per NSE/FAOP/60350.
    Static cash equity bands (20%, 10%, 5%, 2%) are mapped to exact band_percentage.
    """
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference"
    sec_path = Path(sec_list_path) if sec_list_path else data_dir / "sec_list_20240116.csv"
    cash_path = Path(cash_intervals_path) if cash_intervals_path else data_dir / "cash_equity_symbol_intervals.csv"

    if not sec_path.is_file():
        raise FileNotFoundError(f"sec_list artifact not found at {sec_path}")
    if not cash_path.is_file():
        raise FileNotFoundError(f"cash_equity_symbol_intervals artifact not found at {cash_path}")

    # Map symbol -> ISIN for EQ series resolved point-in-time as of 2024-01-16 (Rule 10.4, 10.5)
    as_of_date = datetime.date(2024, 1, 16)
    isin_by_sym: Dict[str, str] = {}
    fallback_isin_by_sym: Dict[str, str] = {}
    all_cash_isins: Set[str] = set()

    with open(cash_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["series"] == "EQ":
                sym = row["symbol"].strip()
                isin = row["isin"].strip()
                all_cash_isins.add(isin)
                fallback_isin_by_sym[sym] = isin

                eff_from = datetime.date.fromisoformat(row["effective_from"].strip())
                eff_to_str = row["effective_to"].strip() if row.get("effective_to") else None
                eff_to = datetime.date.fromisoformat(eff_to_str) if eff_to_str else None

                if eff_from <= as_of_date and (eff_to is None or as_of_date < eff_to):
                    isin_by_sym[sym] = isin

    fo_source = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_FO_UNDERLYING_PRICE_BANDS",
        archive_url_template="https://archives.nseindia.com/content/fo/fo_sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/FAOP/60350",
        description="NSE F&O Underlyings Dynamic Flexing Price Bands",
    )

    static_source = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_DAILY_PRICE_BAND_REPORT",
        archive_url_template="https://archives.nseindia.com/content/equities/sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/CML/SEC_LIST_20240116",
        description="NSE Daily Price Band Report sec_list.csv",
    )

    intervals: List[PriceBandInterval] = []
    seen_isins: Set[str] = set()

    with open(sec_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = row["Symbol"].strip()
            series = row["Series"].strip()
            if series != "EQ":
                continue
            isin = isin_by_sym.get(sym) or fallback_isin_by_sym.get(sym)
            if not isin or isin in seen_isins:
                continue
            seen_isins.add(isin)

            raw_band = row["Band"].strip()
            if raw_band.lower() in ("no band", "noband", "none"):
                intervals.append(
                    PriceBandInterval(
                        isin=isin,
                        band_percentage=None,
                        effective_from=datetime.date(2024, 1, 16),
                        effective_to=None,
                        is_unconstrained=True,
                        source_descriptor=fo_source,
                        circular_ref="NSE/FAOP/60350",
                    )
                )
            else:
                pct = Decimal(raw_band)
                intervals.append(
                    PriceBandInterval(
                        isin=isin,
                        band_percentage=pct,
                        effective_from=datetime.date(2024, 1, 16),
                        effective_to=None,
                        is_unconstrained=False,
                        source_descriptor=static_source,
                        circular_ref="NSE/CML/SEC_LIST_20240116",
                    )
                )

    return tuple(intervals)


def build_production_security_master(include_cash_universe: bool = True) -> SecurityMaster:
    """
    Builds the production reference Security Master seeded with initial instruments:
    - INFY (INE009A01021): Continuous EQ rolling equity.
    - RELIANCE (INE002A01018): Continuous EQ rolling equity.
    - HDFC (INE001A01036): Merged into HDFC Bank, delisted on 2023-07-13 (pruned on 2023-07-13).
    - COCHINSHIP Old (INE704P01017): Listed 2017-08-11, split 2:1 and transitioned to INE704P01025 on 2024-01-10.
    - COCHINSHIP New (INE704P01025): Effective on 2024-01-10 onwards.
    - Cash Universe: When include_cash_universe is True (default), registers effective-dated
      SymbolIntervals for the broader NSE Cash Equity universe per AGENTS.md Rule 10.4 and Audit §38.3 (Finding H-44).
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

    if include_cash_universe:
        cash_intervals = load_cash_universe_symbol_intervals()
        core_by_sym: Dict[Tuple[str, str], List[SymbolInterval]] = defaultdict(list)
        for s in symbol_intervals:
            core_by_sym[(s.symbol, s.series)].append(s)

        for ci in cash_intervals:
            matching_core = core_by_sym.get((ci.symbol, ci.series), [])
            if not matching_core:
                symbol_intervals.append(ci)
                continue

            # Findings N-29, N-30, N-33:
            # Segment complement arithmetic for sourced intervals vs core intervals:
            # For overlapping segments, assert ISIN consistency.
            # Non-overlapping segments (complements) are appended so pre-core or post-core
            # documented tails are preserved rather than dropped whole (Finding N-33).
            segments: List[Tuple[datetime.date, Optional[datetime.date]]] = [(ci.effective_from, ci.effective_to)]

            for core in matching_core:
                new_segments: List[Tuple[datetime.date, Optional[datetime.date]]] = []
                for s_from, s_to in segments:
                    overlap = (
                        (s_to is None or s_to > core.effective_from)
                        and (core.effective_to is None or core.effective_to > s_from)
                    )
                    if not overlap:
                        new_segments.append((s_from, s_to))
                        continue

                    # Overlapping portion: verify ISIN consistency
                    if ci.isin != core.isin:
                        raise SecurityMasterError(
                            f"Divergence detected between hardcoded core interval for {core.symbol} ({core.series}) "
                            f"[ISIN {core.isin}, {core.effective_from}..{core.effective_to}] and sourced interval "
                            f"[ISIN {ci.isin}, {ci.effective_from}..{ci.effective_to}] (Note N-29)."
                        )

                    # Complement subtraction: [s_from, s_to) \ [core.effective_from, core.effective_to)
                    # Left remainder (pre-core segment):
                    if core.effective_from > s_from:
                        new_segments.append((s_from, core.effective_from))

                    # Right remainder (post-core segment):
                    if core.effective_to is not None and (s_to is None or core.effective_to < s_to):
                        new_segments.append((core.effective_to, s_to))

                segments = new_segments

            for sf, st in segments:
                if st is None or sf < st:
                    symbol_intervals.append(
                        SymbolInterval(
                            isin=ci.isin,
                            symbol=ci.symbol,
                            series=ci.series,
                            effective_from=sf,
                            effective_to=st,
                        )
                    )

    corporate_actions = [
        # INFY 1:1 Bonus ex-date 2018-09-12 (1 old share gives 1 additional share, total 2)
        CorporateAction(
            isin="INE009A01021",
            ex_date=datetime.date(2018, 9, 12),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="UNATTESTED_NSE_CML_2018_BONUS_INFY",
            description="INFY 1:1 Bonus Issue",
        ),
        # RELIANCE 1:1 Bonus ex-date 2017-09-07
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2017, 9, 7),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="UNATTESTED_NSE_CML_2017_BONUS_RIL",
            description="RELIANCE 1:1 Bonus Issue",
        ),
        # RELIANCE 1:1 Bonus ex-date 2024-10-28
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2024, 10, 28),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("2"),
            ratio_denominator=Decimal("1"),
            circular_ref="UNATTESTED_NSE_CML_2024_BONUS_RIL2",
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
            circular_ref="UNATTESTED_NSE_CML_60114",
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
            circular_ref="UNATTESTED_NSE_CML_60114",
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
        # COCHINSHIP Old ISIN (exchange publishes "No Band" under F&O dynamic flexing framework, Audit §36 H-43)
        PriceBandInterval(
            isin="INE704P01017",
            band_percentage=None,
            effective_from=datetime.date(2017, 8, 11),
            effective_to=datetime.date(2024, 1, 10),
            is_unconstrained=True,
            source_descriptor=fo_source,
            circular_ref="NSE/FAOP/60350",
        ),
        # COCHINSHIP New ISIN (exchange publishes "No Band" under F&O dynamic flexing framework, Audit §36 H-43)
        PriceBandInterval(
            isin="INE704P01025",
            band_percentage=None,
            effective_from=datetime.date(2024, 1, 10),
            effective_to=None,
            is_unconstrained=True,
            source_descriptor=fo_source,
            circular_ref="NSE/FAOP/60350",
        ),
    ]

    # Finding CA-3: Load universe price band intervals when include_cash_universe is True
    if include_cash_universe:
        cash_band_intervals = load_cash_universe_price_band_intervals()
        core_band_isins = {b.isin for b in price_band_intervals}
        for bi in cash_band_intervals:
            if bi.isin not in core_band_isins:
                price_band_intervals.append(bi)

    # Audit §37 H-48: Drop hand-authored 2024-01-10 split-day discrete record in favor of interval resolution.
    # Discrete daily records must be ingested from verified daily exchange reports (H-44), not hand-authored.
    price_bands: Tuple[PriceBandRecord, ...] = ()

    # Audit §59.7, §60.6: Load committed surveillance intervals and external corporate actions if available.
    # Exclude SYNTHETIC_FIXTURE rows from production security master (Finding H-87, Finding H-88).
    raw_surveillance = load_surveillance_intervals()
    surveillance_intervals = tuple(
        s for s in raw_surveillance
        if not (s.circular_ref and "SYNTHETIC_FIXTURE" in s.circular_ref)
    )

    loaded_corp_actions = load_corporate_actions()
    if loaded_corp_actions:
        existing_ca_keys = {(ca.isin, ca.ex_date) for ca in corporate_actions}
        for ca in loaded_corp_actions:
            if ca.circular_ref and "SYNTHETIC_FIXTURE" in ca.circular_ref:
                continue
            if (ca.isin, ca.ex_date) not in existing_ca_keys:
                corporate_actions.append(ca)
                existing_ca_keys.add((ca.isin, ca.ex_date))

    # Audit §77.11 / §77.15 item 1 (N-145): an `ISIN_TRANSITION` row in the committed corporate-action
    # table is an effective-dated identity event, so it must also enter the transition table that
    # `is_transitioned_out` consults — otherwise the master knows the old ISIN is superseded only for
    # the one row hardcoded below. The effective date is the successor ISIN's first session in the
    # committed interval table, falling back to the action's ex-date when the successor has no interval
    # (an identity the corpus cannot place in time is not silently placed by an ex-date that may be a
    # session earlier than the switch, as TATASTEEL's 2022-07-28 ex-date is).
    known_transitions = {(t.old_isin, t.new_isin) for t in isin_transitions}
    successor_start: Dict[str, datetime.date] = {}
    for interval in symbol_intervals:
        current = successor_start.get(interval.isin)
        if current is None or interval.effective_from < current:
            successor_start[interval.isin] = interval.effective_from
    for ca in corporate_actions:
        if ca.action_type is not CorporateActionType.ISIN_TRANSITION or not ca.old_isin or not ca.new_isin:
            continue
        if (ca.old_isin, ca.new_isin) in known_transitions:
            continue
        isin_transitions.append(
            ISINTransitionEvent(
                old_isin=ca.old_isin,
                new_isin=ca.new_isin,
                effective_date=successor_start.get(ca.new_isin, ca.ex_date),
                reason="ISIN_TRANSITION_RECORDED_IN_CORPUS",
                circular_ref=ca.circular_ref,
            )
        )
        known_transitions.add((ca.old_isin, ca.new_isin))

    return SecurityMaster(
        symbol_intervals=symbol_intervals,
        surveillance_intervals=surveillance_intervals,
        corporate_actions=corporate_actions,
        delisting_events=delisting_events,
        isin_transitions=isin_transitions,
        price_bands=price_bands,
        price_band_intervals=price_band_intervals,
    )

