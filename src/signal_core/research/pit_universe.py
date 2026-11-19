"""
Point-in-Time Liquid Cash Equity Universe Selection Engine.
Enforces AGENTS.md §6.1 (Zero Survivorship Bias), §6.2 (Date-Aware Continuity vs Strategy Eligibility),
§10.4 (Identity Is ISIN, Never Symbol), §10.5 (Time-Varying Facts Are Interval Tables),
and Audit §56.5, §57.3 / §57.7 Items 3–5, §58.3 / §58.7 Items 1–2 (Findings H-78, H-79, H-81, N-71, N-72, N-73, N-76, N-77).

Reconstructs universe constituents strictly as of session T using information
observable strictly prior to session T open. Static constituent lists and forward-filled
survivorship-biased sets are strictly rejected.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
import csv
from dataclasses import dataclass
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError
from signal_core.features.engine import trailing_continuous_bars
from signal_core.storage.calendar import TradingCalendar, load_anchored_nse_trading_calendar
from signal_core.storage.security_master import apply_interval_restatements

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_INTERVALS_PATH = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_intervals.csv"


@dataclass(frozen=True, slots=True)
class CashEquityInterval:
    """
    Authoritative point-in-time effective-dated symbol and series interval.
    Semantics: half-open interval [effective_from, effective_to).
    If effective_to is None, interval is open-ended (currently active).
    """
    isin: str
    symbol: str
    series: str
    effective_from: datetime.date
    effective_to: Optional[datetime.date] = None

    def __post_init__(self) -> None:
        if not isinstance(self.isin, str) or len(self.isin) != 12:
            raise UniverseValidationError(f"Invalid ISIN: {self.isin!r}")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise UniverseValidationError(f"Invalid symbol: {self.symbol!r}")
        if not isinstance(self.series, str) or not self.series:
            raise UniverseValidationError(f"Invalid series: {self.series!r}")
        if type(self.effective_from) is not datetime.date:
            raise UniverseValidationError(f"effective_from must be datetime.date, got {type(self.effective_from)}")
        if self.effective_to is not None:
            if type(self.effective_to) is not datetime.date:
                raise UniverseValidationError(f"effective_to must be datetime.date, got {type(self.effective_to)}")
            if self.effective_from >= self.effective_to:
                raise UniverseValidationError(
                    f"effective_from ({self.effective_from}) must precede effective_to ({self.effective_to})"
                )

    def is_active(self, as_of: datetime.date, required_series: Optional[str] = None) -> bool:
        """Returns True if this instrument interval was active on as_of session date."""
        if type(as_of) is not datetime.date:
            raise UniverseValidationError(f"as_of must be exact datetime.date, got {type(as_of)}")
        if required_series is not None and self.series != required_series:
            return False
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of >= self.effective_to:
            return False
        return True


def load_cash_equity_symbol_intervals(
    path: Optional[Path] = None,
) -> List[CashEquityInterval]:
    """Loads authoritative cash equity symbol intervals from committed CSV."""
    file_path = path or DEFAULT_INTERVALS_PATH
    if not file_path.is_file():
        raise FileNotFoundError(f"Cash equity symbol intervals file not found at {file_path}")

    intervals: List[CashEquityInterval] = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eff_from = datetime.date.fromisoformat(row["effective_from"].strip())
            eff_to_str = row.get("effective_to", "").strip()
            eff_to = datetime.date.fromisoformat(eff_to_str) if eff_to_str else None
            intervals.append(
                CashEquityInterval(
                    isin=row["isin"].strip().upper(),
                    symbol=row["symbol"].strip().upper(),
                    series=row["series"].strip().upper(),
                    effective_from=eff_from,
                    effective_to=eff_to,
                )
            )
    # The artifact is an append-only interval log (§10.1, §90.7 Ruling 2): a restated row supersedes the
    # row it corrects and the superseded row is retained as history, so the universe reads active rows.
    return apply_interval_restatements(intervals)


_START_INDEX_CACHE_LIMIT = 4
_START_INDEX_CACHE: "OrderedDict[Tuple[int, int], Tuple[Sequence[CashEquityInterval], Mapping[str, Tuple[List[datetime.date], List[CashEquityInterval]]]]]" = OrderedDict()


def _start_index(
    intervals: Sequence[CashEquityInterval],
) -> Mapping[str, Tuple[List[datetime.date], List[CashEquityInterval]]]:
    """Returns, per series, the intervals ordered by `effective_from` plus their aligned start dates."""
    key = (id(intervals), len(intervals))
    cached = _START_INDEX_CACHE.get(key)
    if cached is not None and cached[0] is intervals:
        _START_INDEX_CACHE.move_to_end(key)
        return cached[1]

    grouped: Dict[str, List[CashEquityInterval]] = {}
    for iv in intervals:
        grouped.setdefault(iv.series, []).append(iv)
    table = {
        series: (starts, sorted(rows, key=lambda iv: iv.effective_from))
        for series, rows in grouped.items()
        for starts in [[iv.effective_from for iv in sorted(rows, key=lambda iv: iv.effective_from)]]
    }

    _START_INDEX_CACHE[key] = (intervals, table)
    while len(_START_INDEX_CACHE) > _START_INDEX_CACHE_LIMIT:
        _START_INDEX_CACHE.popitem(last=False)
    return table


def get_point_in_time_active_equities(
    as_of: datetime.date,
    intervals: Sequence[CashEquityInterval],
    series: str = "EQ",
) -> Tuple[str, ...]:
    """
    Returns deterministic, sorted tuple of active ISINs on session date as_of.
    Zero lookahead: tests half-open interval [effective_from, effective_to) strictly as of date T.
    """
    if type(as_of) is not datetime.date:
        raise UniverseValidationError(f"as_of must be genuine datetime.date, got {type(as_of)}")

    # Sessions are evaluated in order, so the per-series start index is built once per interval
    # sequence and reused: only rows starting on or before T can be active on T (§90.9 item 2).
    starts, ordered = _start_index(intervals).get(series, ([], []))
    limit = bisect_right(starts, as_of)
    active_isins = {
        iv.isin
        for iv in ordered[:limit]
        if iv.effective_to is None or as_of < iv.effective_to
    }

    return tuple(sorted(active_isins))


def build_point_in_time_universe_schedule(
    sessions: Sequence[datetime.date],
    intervals: Optional[Sequence[CashEquityInterval]] = None,
    series: str = "EQ",
    daily_turnover_inr: Optional[Mapping[Tuple[datetime.date, str], Decimal]] = None,
    min_median_daily_turnover_inr: Optional[Decimal] = None,
    turnover_lookback_sessions: int = 20,
    top_liquid_k: Optional[int] = None,
    requested_index_name: Optional[str] = None,
    calendar: Optional[TradingCalendar] = None,
) -> UniverseSchedule:
    """
    Builds an immutable UniverseSchedule mapping discrete sessions to eligible ISINs.

    Precondition Gating (Audit §56.5):
        - If requested_index_name == 'NIFTY 500' or similar unsourced index, raises UniverseValidationError.
          Static constituent lists without sourced historical interval tables are strictly prohibited (§6.1, §10.5).

    Note on requested_index_name (Finding N-72):
        The index guard is a deliberate tripwire rejecting unsourced 'NIFTY' requests fail-closed.
        It is not an authorization of unverified index labels (e.g. 'CNX 500'). Sourced index
        constituent intervals must be loaded from explicit interval tables in data/reference/.

    Args:
        sessions: Ordered sequence of calendar trading sessions to map.
        intervals: Sourced CashEquityIntervals (defaults to committed CSV).
        series: Exchange series filter (defaults to 'EQ' per APPROVED_EQ_ONLY_POLICY).
        daily_turnover_inr: Historical turnover mapping (session_date, isin) -> Decimal turnover in INR.
        min_median_daily_turnover_inr: Minimum median daily turnover threshold in INR (e.g. 5 Crore = 50,000,000).
        turnover_lookback_sessions: Number of historical calendar sessions strictly PRIOR to T to assess turnover.
        top_liquid_k: Optional cap selecting top K most liquid names as of T-1.
        requested_index_name: Optional index name check (tripwire per Finding N-72).
        calendar: Optional TradingCalendar (defaults to anchored NSE calendar per Finding H-79).

    Returns:
        Immutable UniverseSchedule instance with recorded exclusion reasons (Finding N-71).
    """
    if requested_index_name is not None:
        norm_idx = requested_index_name.strip().upper()
        if "NIFTY" in norm_idx:
            raise UniverseValidationError(
                f"Index membership history for {norm_idx!r} is not sourced in data/reference/. "
                "Static constituent lists without effective-dated interval tables violate AGENTS.md §6.1, §10.5, "
                "and Audit §56.5. Use point-in-time liquid EQ universe derived from cash_equity_symbol_intervals.csv."
            )

    if not sessions:
        raise UniverseValidationError("sessions sequence cannot be empty")

    # Validate parameters fail-closed (Findings N-76, N-77)
    if (
        isinstance(turnover_lookback_sessions, bool)
        or not isinstance(turnover_lookback_sessions, int)
        or turnover_lookback_sessions < 1
    ):
        raise UniverseValidationError(
            f"turnover_lookback_sessions must be a strictly positive integer (>= 1), got {turnover_lookback_sessions!r} (Finding N-76)."
        )

    if top_liquid_k is not None:
        if (
            isinstance(top_liquid_k, bool)
            or not isinstance(top_liquid_k, int)
            or top_liquid_k < 1
        ):
            raise UniverseValidationError(
                f"top_liquid_k must be a strictly positive integer (>= 1) if provided, got {top_liquid_k!r} (Finding N-77)."
            )

    active_calendar = calendar or load_anchored_nse_trading_calendar()

    # Reject sessions absent from the authoritative calendar fail-closed (Finding H-79)
    for s in sessions:
        if type(s) is not datetime.date:
            raise UniverseValidationError(f"Session date must be genuine datetime.date, got {type(s).__name__}")
        if not active_calendar.is_session(s):
            raise UniverseValidationError(
                f"Requested date {s.isoformat()} is not an authoritative NSE trading session (Finding H-79)."
            )

    loaded_intervals = intervals if intervals is not None else load_cash_equity_symbol_intervals()
    schedule_map: Dict[datetime.date, Tuple[str, ...]] = {}
    exclusion_reasons: Dict[Tuple[datetime.date, str], str] = {}

    sorted_sessions = sorted(sessions)
    cal_sessions = active_calendar.sessions

    filter_liquidity = daily_turnover_inr is not None and (
        min_median_daily_turnover_inr is not None or top_liquid_k is not None
    )

    available_turnover_sessions: Set[datetime.date] = set()
    if daily_turnover_inr is not None:
        available_turnover_sessions = {k[0] for k in daily_turnover_inr.keys()}

    for s in sorted_sessions:
        # Base PIT membership from authoritative interval table
        candidate_isins = list(get_point_in_time_active_equities(s, loaded_intervals, series=series))
        base_candidates = list(candidate_isins)

        # Liquidity filter using data strictly prior to session s (zero-lookahead, calendar-derived window)
        if filter_liquidity:
            assert daily_turnover_inr is not None  # guaranteed by filter_liquidity
            s_idx = cal_sessions.index(s)
            prior_cal_sessions = cal_sessions[:s_idx]

            # Fail closed if session lacks full lookback window in calendar (Finding H-78 / H-79)
            if len(prior_cal_sessions) < turnover_lookback_sessions:
                raise UniverseValidationError(
                    f"Session {s.isoformat()} has only {len(prior_cal_sessions)} prior calendar sessions; "
                    f"requires {turnover_lookback_sessions} (Finding H-78)."
                )

            lookback_window = prior_cal_sessions[-turnover_lookback_sessions:]

            # Fail closed if any session in the lookback window is absent from daily_turnover_inr (Finding H-81)
            missing_lookback_sessions = [
                prior_s for prior_s in lookback_window if prior_s not in available_turnover_sessions
            ]
            if missing_lookback_sessions:
                missing_str = ", ".join(ms.isoformat() for ms in missing_lookback_sessions[:3])
                raise UniverseValidationError(
                    f"Session {s.isoformat()} has incomplete lookback window in daily_turnover_inr: "
                    f"missing {len(missing_lookback_sessions)} of {turnover_lookback_sessions} calendar sessions "
                    f"(e.g. {missing_str}) (Finding H-81). "
                    "Callers must declare incomplete lookback sessions as warm-up rather than emitting empty cross-sections."
                )

            liquid_scores: List[Tuple[str, Decimal]] = []
            for isin in candidate_isins:
                # Distinguish missing records from 0.0 turnover (Finding N-71)
                missing_records = [
                    prior_s for prior_s in lookback_window if (prior_s, isin) not in daily_turnover_inr
                ]
                if missing_records:
                    exclusion_reasons[(s, isin)] = (
                        f"MISSING_TURNOVER_RECORD: missing {len(missing_records)} session(s) in lookback window "
                        f"(e.g. {missing_records[0].isoformat()}) (Finding N-71)"
                    )
                    continue

                turnovers = [daily_turnover_inr[(prior_s, isin)] for prior_s in lookback_window]
                sorted_turnovers = sorted(turnovers)
                mid = len(sorted_turnovers) // 2
                median_val = (
                    sorted_turnovers[mid]
                    if len(sorted_turnovers) % 2 == 1
                    else (sorted_turnovers[mid - 1] + sorted_turnovers[mid]) / Decimal("2")
                )

                if min_median_daily_turnover_inr is not None and median_val < min_median_daily_turnover_inr:
                    exclusion_reasons[(s, isin)] = (
                        f"BELOW_MIN_MEDIAN_TURNOVER: median turnover INR {median_val} < required INR {min_median_daily_turnover_inr}"
                    )
                    continue

                liquid_scores.append((isin, median_val))

            # Sort by turnover descending, then ISIN ascending
            liquid_scores.sort(key=lambda x: (-x[1], x[0]))

            if top_liquid_k is not None and top_liquid_k > 0:
                selected_isins = [x[0] for x in liquid_scores[:top_liquid_k]]
                for rank, (isin, med_val) in enumerate(liquid_scores[top_liquid_k:], start=top_liquid_k + 1):
                    exclusion_reasons[(s, isin)] = (
                        f"OUTSIDE_TOP_LIQUID_K: rank {rank} exceeds top_liquid_k={top_liquid_k} (median turnover INR {med_val})"
                    )
                candidate_isins = selected_isins
            else:
                candidate_isins = [x[0] for x in liquid_scores]

            # Finding N-82: Differentiate genuine empty universe from internal data omissions.
            # If emitted cross-section is empty and every active candidate was excluded for MISSING_TURNOVER_RECORD,
            # fail closed with UniverseValidationError rather than silently emitting 0 members.
            if not candidate_isins and base_candidates:
                all_missing_records = all(
                    exclusion_reasons.get((s, isin), "").startswith("MISSING_TURNOVER_RECORD")
                    for isin in base_candidates
                )
                if all_missing_records:
                    raise UniverseValidationError(
                        f"Session {s.isoformat()} emitted 0 members and all {len(base_candidates)} active candidate(s) "
                        f"lacked turnover lookback history (MISSING_TURNOVER_RECORD) (Finding N-82). "
                        "Internally inconsistent or unaligned turnover partitions must fail closed."
                    )

        schedule_map[s] = tuple(sorted(candidate_isins))

    return UniverseSchedule(schedule_map, exclusion_reasons=exclusion_reasons)


def median_turnover_as_of(
    as_of: datetime.date,
    *,
    calendar_sessions: Sequence[datetime.date],
    bars_by_date: Mapping[datetime.date, Any],
    lookback_sessions: int = 20,
    session_index: Optional[Mapping[datetime.date, int]] = None,
) -> Optional[Decimal]:
    """
    Median traded value (INR) over the `lookback_sessions` sessions strictly before `as_of`.

    Audit §98.10 item 1 / §6.3: the window is a contiguous run of authoritative calendar sessions, so a
    multi-month hole cannot be read as a quiet 20 sessions. A window that crosses an
    `UNEXPLAINED_MISSING_RECORD` boundary is refused (None) rather than averaged over the bars that
    happen to survive, which is why the caller treats None as "no T-1 liquidity evidence" and not as
    zero turnover. `None` is also returned when the history is shorter than the window.
    """
    window = trailing_continuous_bars(
        expected_calendar_sessions=calendar_sessions,
        bars_by_date=bars_by_date,
        as_of=as_of,
        lookback=lookback_sessions,
        session_index=session_index,
    )
    if window is None:
        return None
    turnovers: List[Decimal] = []
    for bar in window:
        traded = getattr(bar, "traded_value", None)
        if traded is None:
            traded = Decimal(getattr(bar, "volume")) * getattr(bar, "close")
        turnovers.append(traded)
    ordered = sorted(turnovers)
    mid = len(ordered) // 2
    return (
        ordered[mid]
        if len(ordered) % 2 == 1
        else (ordered[mid - 1] + ordered[mid]) / Decimal("2")
    )

