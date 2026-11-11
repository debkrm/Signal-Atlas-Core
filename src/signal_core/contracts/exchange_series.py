"""Exchange Series and Price Continuity Contracts.

Defines the formal data contracts separating three distinct domain concepts:
1. Raw Market Observations: What the exchange reported (OHLCV, raw series code, ISIN, provenance).
2. Price-History Continuity: Whether market observations form a complete, unbroken chronological series
   over expected trading sessions and active listing intervals, independent of trading eligibility.
3. Research and Trading Eligibility: Policies governing strategy entry, position retention across series shifts,
   and settlement rules.
"""

from dataclasses import dataclass
import datetime
from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple, Union

from signal_core.contracts.price_bar import PriceBar


def validate_raw_series_code(code: Optional[str]) -> Optional[str]:
    """
    Validates a raw series code string from an exchange record.
    Preserves the original valid raw code exactly without silently trimming or rewriting it.

    Distinguishes:
    - Missing series value: None -> returns None
    - Invalid empty string: "" -> raises ValueError
    - Invalid whitespace-only string: "   " -> raises ValueError
    - Invalid whitespace-padded string: " EQ " -> raises ValueError
    - Invalid control characters: e.g. \\n, \\t -> raises ValueError
    - Valid code: returns code exactly as supplied (e.g. "EQ", "BE", "W3", "XX")
    """
    if code is None:
        return None
    if not isinstance(code, str):
        raise TypeError(f"Raw series code must be str or None, got {type(code).__name__}")
    if len(code) == 0:
        raise ValueError("Invalid empty series code. Missing series must be represented as None.")
    for ch in code:
        code_point = ord(ch)
        if code_point < 32 or (127 <= code_point <= 159):
            raise ValueError(f"Raw series code contains invalid control character (code {code_point}): {code!r}")
    if code.isspace():
        raise ValueError("Invalid whitespace-only series code. Missing series must be represented as None.")
    if code != code.strip():
        raise ValueError(f"Raw series code cannot contain leading or trailing whitespace: {code!r}")
    return code


class ExchangeSeries(str, Enum):
    """
    Standardized National Stock Exchange (NSE) cash market trading series classifications.
    Distinguishes recognized codes, unrecognized present codes, and genuinely missing values.
    """
    EQ = "EQ"        # Normal rolling settlement cash equity segment (standard margin, intraday netting allowed)
    BE = "BE"        # Book Entry / Trade-to-Trade segment (gross settlement, 100% delivery, price bands typically 5% or 2%)
    BZ = "BZ"        # Surveillance / Non-compliant scrips traded in Trade-to-Trade
    SM = "SM"        # Small and Medium Enterprise (SME) exchange segment
    OTHER = "OTHER"  # Unrecognized but present exchange series code (e.g., W3, XX, BL, IL)
    UNKNOWN = "UNKNOWN"  # Genuinely missing, unrecorded, or unauthenticated series identifier

    @classmethod
    def classify_raw_code(cls, raw_code: Optional[str]) -> "ExchangeSeries":
        """
        Maps a raw series code string to its typed classification.
        Preserves distinction between:
        - Genuinely missing: None -> UNKNOWN
        - Recognized codes: EQ, BE, BZ, SM
        - Present but unrecognized codes: OTHER (with original raw code preserved separately)
        - Invalid empty/whitespace string: raises ValueError (enforced by validate_raw_series_code)
        """
        if raw_code is None:
            return cls.UNKNOWN
        valid_code = validate_raw_series_code(raw_code)
        upper = valid_code.upper()
        if upper == "EQ":
            return cls.EQ
        elif upper == "BE":
            return cls.BE
        elif upper == "BZ":
            return cls.BZ
        elif upper == "SM":
            return cls.SM
        else:
            return cls.OTHER

    # Backward compatibility alias
    from_raw_string = classify_raw_code


class PriceSeriesGapType(str, Enum):
    """
    Evidence-based classification of gaps in an instrument's daily price record sequence.
    Distinguishes verifiable market/corporate events from unexplained data omissions.
    """
    EXTRACTION_FILTER_OMISSION = "EXTRACTION_FILTER_OMISSION"
    # Exchange traded the security (e.g., under BE), but records were excluded by an upstream extraction filter.

    OUTSIDE_VERIFIED_LISTING_INTERVAL = "OUTSIDE_VERIFIED_LISTING_INTERVAL"
    # Session falls before the instrument's verified IPO listing date or after corporate merger/delisting.

    VERIFIED_CORPORATE_ACTION_DELISTING = "VERIFIED_CORPORATE_ACTION_DELISTING"
    # Verified delisting due to merger/acquisition/amalgamation with documented exchange circular.

    VERIFIED_ISIN_TRANSITION = "VERIFIED_ISIN_TRANSITION"
    # Instrument's historical identifier was superseded by a new ISIN due to a stock split or capital restructuring.

    VERIFIED_TRADING_HALT_OR_SUSPENSION = "VERIFIED_TRADING_HALT_OR_SUSPENSION"
    # Scrip was listed and eligible, but trading was formally suspended by exchange circular (requires evidence).

    UNEXPLAINED_MISSING_RECORD = "UNEXPLAINED_MISSING_RECORD"
    # Price record is absent without documented exchange suspension or corporate action record (fails closed).

    # Backward compatibility aliases
    SERIES_FILTER_OMISSION = EXTRACTION_FILTER_OMISSION
    PRE_LISTING_OR_POST_DELISTING = OUTSIDE_VERIFIED_LISTING_INTERVAL
    ISIN_TRANSITION_REPLACED = VERIFIED_ISIN_TRANSITION
    TRADING_HALT_OR_SUSPENSION = VERIFIED_TRADING_HALT_OR_SUSPENSION


@dataclass(frozen=True, slots=True)
class SeriesEligibilityPolicy:
    """
    Explicit research policy governing strategy and universe eligibility by exchange series.

    Decoupling Invariants:
    - Raw observation identity is NEVER mutated or deleted by eligibility rules.
    - Historical price continuity is assessed independently of whether an instrument is eligible to trade.
    - Research workflows must explicitly declare permitted series; no implicit default operating policy exists.
    - Trade-to-Trade (BE) is never implicitly or silently permitted.
    """
    permitted_series: FrozenSet[ExchangeSeries]
    allow_series_transitions: bool = False  # Whether existing positions can be held across EQ -> BE shifts

    def is_eligible(self, series: ExchangeSeries) -> bool:
        """Returns True if the exchange series is explicitly permitted under this policy."""
        return series in self.permitted_series


# AUTHORIZED PRODUCTION POLICY (Formally Approved for Cash Equity Strategies).
# Represents strict rolling equity (EQ) only. Trade-to-Trade (BE) is excluded from trade entry.
APPROVED_EQ_ONLY_POLICY = SeriesEligibilityPolicy(
    permitted_series=frozenset({ExchangeSeries.EQ}),
    allow_series_transitions=False,
)

# Backward-compatibility alias
PROPOSED_UNAPPROVED_EQ_ONLY_POLICY = APPROVED_EQ_ONLY_POLICY

# QUARANTINED CANDIDATE POLICY (NOT an authorized default).
# Permissive cash policy including BE. Requires explicit workflow injection and documented owner approval.
QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY = SeriesEligibilityPolicy(
    permitted_series=frozenset({ExchangeSeries.EQ, ExchangeSeries.BE}),
    allow_series_transitions=True,
)


@dataclass(frozen=True, slots=True)
class ExchangeSessionObservation:
    """
    Authoritative market observation preserving what the exchange actually reported
    for an instrument on a trading date.

    Preserves:
    - Instrument identity
    - Trading date
    - Raw OHLCV (encapsulated in pure PriceBar)
    - Verbatim raw exchange series code (e.g. "EQ", "BE", "W3", "XX")
    - Domain classification (ExchangeSeries enum)
    - Authoritative ISIN anchor
    - Source provenance identifier
    """
    instrument_id: str
    trade_date: datetime.date
    raw_series_code: Optional[str]
    series_classification: ExchangeSeries
    isin: str
    price_bar: PriceBar
    source_provenance: str = "EXCHANGE_BHAVCOPY"

    def __post_init__(self):
        validated = validate_raw_series_code(self.raw_series_code)
        object.__setattr__(self, "raw_series_code", validated)
        expected_class = ExchangeSeries.classify_raw_code(validated)
        if self.series_classification != expected_class:
            raise ValueError(
                f"Mismatch between raw_series_code {validated!r} and series_classification "
                f"{self.series_classification!r} (expected {expected_class!r})"
            )
        if self.price_bar.trade_date != self.trade_date:
            raise ValueError(
                f"trade_date {self.trade_date} does not match price_bar.trade_date {self.price_bar.trade_date}"
            )
        if self.price_bar.instrument_id != self.instrument_id:
            raise ValueError(
                f"instrument_id {self.instrument_id!r} does not match price_bar.instrument_id {self.price_bar.instrument_id!r}"
            )

    @property
    def series(self) -> ExchangeSeries:
        """Backward-compatibility property."""
        return self.series_classification


@dataclass(frozen=True, slots=True)
class SessionGapRecord:
    """
    Detailed, evidence-backed audit descriptor for a missing session in an instrument's history.
    Prohibits unsubstantiated assumptions of exchange halts without supporting evidence.
    """
    trade_date: datetime.date
    gap_type: PriceSeriesGapType
    raw_series_code: Optional[str] = None
    series_classification: Optional[ExchangeSeries] = None
    evidence_reference: str = ""
    detail: str = ""

    def __post_init__(self):
        if self.raw_series_code is not None:
            validated = validate_raw_series_code(self.raw_series_code)
            object.__setattr__(self, "raw_series_code", validated)

        # Invariant: TRADING_HALT_OR_SUSPENSION requires verifiable exchange circular / notice evidence
        if self.gap_type in (
            PriceSeriesGapType.VERIFIED_TRADING_HALT_OR_SUSPENSION,
            PriceSeriesGapType.TRADING_HALT_OR_SUSPENSION,
        ):
            if not self.evidence_reference or not self.evidence_reference.strip():
                raise ValueError(
                    f"Cannot classify gap on {self.trade_date} as VERIFIED_TRADING_HALT_OR_SUSPENSION "
                    "without non-empty evidence_reference (e.g. exchange circular or suspension notice)."
                )

    @property
    def raw_bhavcopy_present(self) -> bool:
        return self.raw_series_code is not None

    @property
    def observed_series(self) -> Optional[ExchangeSeries]:
        return self.series_classification

    @property
    def is_explained(self) -> bool:
        return self.gap_type != PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD


@dataclass(frozen=True, slots=True)
class InstrumentListingInterval:
    """
    Verified active listing boundaries for an instrument, including corporate actions.
    """
    instrument_id: str
    symbol: str
    isin: str
    listing_date: Optional[datetime.date] = None
    delisting_date: Optional[datetime.date] = None
    superseded_by_isin: Optional[str] = None
    transition_date: Optional[datetime.date] = None
    delisting_reason: str = ""


@dataclass(frozen=True, slots=True)
class PriceSeriesContinuityResult:
    """
    Immutable audit result for session continuity across an explicit trading calendar.
    Fails closed if unexplained missing sessions are detected.
    """
    instrument_id: str
    symbol: str
    expected_sessions_count: int
    available_records_count: int
    missing_sessions_count: int
    is_continuous: bool
    has_unexplained_gaps: bool
    gaps: Tuple[SessionGapRecord, ...]

    # Exhaustive breakdown
    complete_coverage_count: int
    outside_listing_count: int
    known_filter_omissions_count: int
    verified_transitions_count: int
    verified_suspensions_count: int
    unexplained_missing_count: int

    @property
    def fail_closed_reason(self) -> Optional[str]:
        if self.has_unexplained_gaps:
            return (
                f"Instrument {self.symbol} ({self.instrument_id}) has {self.unexplained_missing_count} "
                "unexplained missing session(s). Sequence cannot be treated as continuous."
            )
        if self.known_filter_omissions_count > 0:
            return (
                f"Instrument {self.symbol} ({self.instrument_id}) has {self.known_filter_omissions_count} "
                "filter omission session(s) (e.g. BE series excluded). Sequence is non-contiguous."
            )
        return None


# Backward-compatibility alias
InstrumentContinuityAudit = PriceSeriesContinuityResult


PriceRecordItem = Union[PriceBar, ExchangeSessionObservation]


class PriceSeriesContinuityValidator:
    """
    Date-aware price-history continuity validation engine.

    Determines whether valid market observations form a complete chronological series
    over expected exchange trading sessions and active listing intervals.

    Decoupling Guarantees:
    - Continuity is independent of research trading eligibility: a shift from EQ to BE does NOT
      break continuity if valid market observations exist on both sides of the transition.
    - Series transitions alone do NOT cause rolling feature windows to restart.
    - Never assumes N available bars represent N consecutive calendar exchange sessions.
    - Never silently fills, interpolates, or skips missing trading dates.
    - Never uses floating-point NaN or zero prices to mask missing sessions.
    - Fails closed on unexplained gaps.
    """

    @classmethod
    def validate_series_continuity(
        cls,
        instrument_id: str,
        symbol: str,
        expected_calendar_sessions: Sequence[datetime.date],
        actual_price_bars: Sequence[PriceRecordItem],
        listing_interval: Optional[InstrumentListingInterval] = None,
        raw_observations_by_date: Optional[Mapping[datetime.date, Tuple[Optional[str], ExchangeSeries]]] = None,
        verified_suspensions_by_date: Optional[Mapping[datetime.date, str]] = None,
    ) -> PriceSeriesContinuityResult:
        """
        Audits price bar coverage session-by-session against an explicit trading calendar.
        Accepts either pure PriceBar instances or enriched ExchangeSessionObservation instances.
        """
        # Validate calendar sessions
        calendar_set = set(expected_calendar_sessions)

        # Map available records by date with duplicate and off-calendar validation
        records_by_date: Dict[datetime.date, PriceRecordItem] = {}
        for item in actual_price_bars:
            if item.trade_date not in calendar_set:
                raise ValueError(
                    f"Price bar for instrument '{instrument_id}' on date {item.trade_date} is not present in expected trading calendar. "
                    "Fail-closed invariant prohibits unverified off-calendar price observations."
                )
            if item.trade_date in records_by_date:
                raise ValueError(
                    f"Duplicate price record detected for instrument '{instrument_id}' on date {item.trade_date}. "
                    "Silent deduplication is prohibited; clean inputs required."
                )
            records_by_date[item.trade_date] = item

        gaps: List[SessionGapRecord] = []
        complete_coverage_count = 0
        outside_listing_count = 0
        known_filter_omissions_count = 0
        verified_transitions_count = 0
        verified_suspensions_count = 0
        unexplained_missing_count = 0

        for session_date in expected_calendar_sessions:
            if session_date in records_by_date:
                # Valid price observation exists for this session!
                # Price continuity is preserved regardless of whether the series is EQ, BE, or other.
                complete_coverage_count += 1
                continue

            # Session is missing in price bars - determine exact evidence-based classification
            # 1. Check verified listing boundaries
            if listing_interval:
                if listing_interval.listing_date and session_date < listing_interval.listing_date:
                    outside_listing_count += 1
                    gaps.append(
                        SessionGapRecord(
                            trade_date=session_date,
                            gap_type=PriceSeriesGapType.OUTSIDE_VERIFIED_LISTING_INTERVAL,
                            detail=f"Prior to verified listing date {listing_interval.listing_date}",
                        )
                    )
                    continue

                if listing_interval.delisting_date and session_date >= listing_interval.delisting_date:
                    outside_listing_count += 1
                    gaps.append(
                        SessionGapRecord(
                            trade_date=session_date,
                            gap_type=PriceSeriesGapType.VERIFIED_CORPORATE_ACTION_DELISTING,
                            evidence_reference=listing_interval.delisting_reason or "Verified delisting",
                            detail=f"Post delisting date {listing_interval.delisting_date}: {listing_interval.delisting_reason}",
                        )
                    )
                    continue

                if listing_interval.transition_date and session_date >= listing_interval.transition_date:
                    verified_transitions_count += 1
                    gaps.append(
                        SessionGapRecord(
                            trade_date=session_date,
                            gap_type=PriceSeriesGapType.VERIFIED_ISIN_TRANSITION,
                            evidence_reference=f"Superseded by {listing_interval.superseded_by_isin}",
                            detail=f"ISIN superseded by {listing_interval.superseded_by_isin} on {listing_interval.transition_date}",
                        )
                    )
                    continue

            # 2. Check verified trading suspension with evidence
            if verified_suspensions_by_date and session_date in verified_suspensions_by_date:
                evidence = verified_suspensions_by_date[session_date]
                verified_suspensions_count += 1
                gaps.append(
                    SessionGapRecord(
                        trade_date=session_date,
                        gap_type=PriceSeriesGapType.VERIFIED_TRADING_HALT_OR_SUSPENSION,
                        evidence_reference=evidence,
                        detail=f"Trading suspended per circular: {evidence}",
                    )
                )
                continue

            # 3. Check raw Bhavcopy observations (e.g. traded under BE, but dropped by EQ filter)
            if raw_observations_by_date and session_date in raw_observations_by_date:
                raw_code, series_class = raw_observations_by_date[session_date]
                known_filter_omissions_count += 1
                gaps.append(
                    SessionGapRecord(
                        trade_date=session_date,
                        gap_type=PriceSeriesGapType.EXTRACTION_FILTER_OMISSION,
                        raw_series_code=raw_code,
                        series_classification=series_class,
                        detail=f"Raw Bhavcopy traded under series {raw_code}; omitted by extraction filter",
                    )
                )
                continue

            # 4. No verified evidence: unexplained missing record (fails closed)
            unexplained_missing_count += 1
            gaps.append(
                SessionGapRecord(
                    trade_date=session_date,
                    gap_type=PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD,
                    detail="No price bar and no verified exchange evidence found",
                )
            )

        total_missing = len(gaps)
        has_unexplained = unexplained_missing_count > 0
        is_continuous = (total_missing == outside_listing_count)  # Continuous if missing sessions only exist outside active listing

        return PriceSeriesContinuityResult(
            instrument_id=instrument_id,
            symbol=symbol,
            expected_sessions_count=len(expected_calendar_sessions),
            available_records_count=len(actual_price_bars),
            missing_sessions_count=total_missing,
            is_continuous=is_continuous,
            has_unexplained_gaps=has_unexplained,
            gaps=tuple(gaps),
            complete_coverage_count=complete_coverage_count,
            outside_listing_count=outside_listing_count,
            known_filter_omissions_count=known_filter_omissions_count,
            verified_transitions_count=verified_transitions_count,
            verified_suspensions_count=verified_suspensions_count,
            unexplained_missing_count=unexplained_missing_count,
        )

    @classmethod
    def partition_into_continuous_subsegments(
        cls,
        expected_calendar_sessions: Sequence[datetime.date],
        actual_price_bars: Sequence[PriceRecordItem],
    ) -> List[List[PriceRecordItem]]:
        """
        Partitions price records into strictly continuous sub-sequences where every
        expected exchange calendar date between records is present.

        Decoupling Guarantees:
        - Partitions are bounded strictly by chronological date continuity across calendar sessions.
        - Series transitions (e.g. EQ to BE) do NOT break a continuous subsegment.
        - Lookback windows for rolling mathematical indicators (e.g. EMA, ATR) do not restart
          merely because of a series change.
        """
        if not actual_price_bars:
            return []

        if not expected_calendar_sessions:
            raise ValueError("expected_calendar_sessions cannot be empty when actual_price_bars are provided.")

        # Validate calendar is strictly sorted, genuine dates, and unique
        seen_cal: Set[datetime.date] = set()
        for i, dt in enumerate(expected_calendar_sessions):
            if type(dt) is not datetime.date:
                raise ValueError(f"Calendar date must be genuine datetime.date, got {type(dt).__name__}")
            if dt in seen_cal:
                raise ValueError(f"Duplicate calendar session detected in expected_calendar_sessions: {dt}")
            seen_cal.add(dt)
            if i > 0 and dt < expected_calendar_sessions[i - 1]:
                raise ValueError(
                    f"expected_calendar_sessions must be strictly sorted chronologically: "
                    f"{expected_calendar_sessions[i-1]} followed by {dt}"
                )

        calendar_set = seen_cal

        # Check for duplicates and off-calendar bars
        records_by_date: Dict[datetime.date, PriceRecordItem] = {}
        for b in actual_price_bars:
            if b.trade_date not in calendar_set:
                raise ValueError(
                    f"Encountered price bar on off-calendar date {b.trade_date} not present in expected trading calendar. "
                    "Fail-closed invariant prohibits silent data omission."
                )
            if b.trade_date in records_by_date:
                raise ValueError(f"Duplicate price bar detected on date {b.trade_date}.")
            records_by_date[b.trade_date] = b

        sorted_records = sorted(actual_price_bars, key=lambda b: b.trade_date)
        first_date = sorted_records[0].trade_date
        last_date = sorted_records[-1].trade_date
        relevant_calendar = [d for d in expected_calendar_sessions if first_date <= d <= last_date]

        segments: List[List[PriceRecordItem]] = []
        current_segment: List[PriceRecordItem] = []

        for dt in relevant_calendar:
            if dt in records_by_date:
                current_segment.append(records_by_date[dt])
            else:
                # Gap encountered! Terminate current segment
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []

        if current_segment:
            segments.append(current_segment)

        return segments
