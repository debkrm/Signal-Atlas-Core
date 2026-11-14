"""
Point-in-Time Liquid Cash Equity Universe Selection Engine.
Enforces AGENTS.md §6.1 (Zero Survivorship Bias), §6.2 (Date-Aware Continuity vs Strategy Eligibility),
§10.4 (Identity Is ISIN, Never Symbol), §10.5 (Time-Varying Facts Are Interval Tables),
and Audit §56.5 / §56.6 Item 5 (Preconditions on Sourced PIT Universe).

Reconstructs universe constituents strictly as of session T using information
observable strictly prior to session T open. Static constituent lists and forward-filled
survivorship-biased sets are strictly rejected.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError

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
    return intervals


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

    active_isins: Set[str] = set()
    for iv in intervals:
        if iv.is_active(as_of, required_series=series):
            active_isins.add(iv.isin)

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
) -> UniverseSchedule:
    """
    Builds an immutable UniverseSchedule mapping discrete sessions to eligible ISINs.

    Precondition Gating (Audit §56.5):
        - If requested_index_name == 'NIFTY 500' or similar unsourced index, raises UniverseValidationError.
          Static constituent lists without sourced historical interval tables are strictly prohibited (§6.1, §10.5).

    Args:
        sessions: Ordered sequence of calendar trading sessions to map.
        intervals: Sourced CashEquityIntervals (defaults to committed CSV).
        series: Exchange series filter (defaults to 'EQ' per APPROVED_EQ_ONLY_POLICY).
        daily_turnover_inr: Historical turnover mapping (session_date, isin) -> Decimal turnover in INR.
        min_median_daily_turnover_inr: Minimum median daily turnover threshold in INR (e.g. 5 Crore = 50,000,000).
        turnover_lookback_sessions: Number of historical sessions strictly PRIOR to T to assess turnover.
        top_liquid_k: Optional cap selecting top K most liquid names as of T-1.
        requested_index_name: Optional index name check.

    Returns:
        Immutable UniverseSchedule instance.
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

    loaded_intervals = intervals if intervals is not None else load_cash_equity_symbol_intervals()
    schedule_map: Dict[datetime.date, Tuple[str, ...]] = {}

    sorted_sessions = sorted(sessions)
    session_to_idx = {s: i for i, s in enumerate(sorted_sessions)}

    for s in sorted_sessions:
        # Base PIT membership from authoritative interval table
        candidate_isins = list(get_point_in_time_active_equities(s, loaded_intervals, series=series))

        # Liquidity filter using data strictly prior to session s (zero-lookahead)
        if daily_turnover_inr is not None and (min_median_daily_turnover_inr is not None or top_liquid_k is not None):
            cur_idx = session_to_idx[s]
            start_idx = max(0, cur_idx - turnover_lookback_sessions)
            prior_sessions = sorted_sessions[start_idx:cur_idx]  # Strictly < s

            if prior_sessions:
                liquid_scores: List[Tuple[str, Decimal]] = []
                for isin in candidate_isins:
                    turnovers = [
                        daily_turnover_inr.get((prior_s, isin), Decimal("0.0"))
                        for prior_s in prior_sessions
                    ]
                    # Calculate median turnover across lookback
                    sorted_turnovers = sorted(turnovers)
                    mid = len(sorted_turnovers) // 2
                    median_val = sorted_turnovers[mid] if len(sorted_turnovers) % 2 == 1 else (sorted_turnovers[mid - 1] + sorted_turnovers[mid]) / Decimal("2")

                    if min_median_daily_turnover_inr is not None:
                        if median_val >= min_median_daily_turnover_inr:
                            liquid_scores.append((isin, median_val))
                    else:
                        liquid_scores.append((isin, median_val))

                # Sort by turnover descending, then ISIN ascending
                liquid_scores.sort(key=lambda x: (-x[1], x[0]))

                if top_liquid_k is not None and top_liquid_k > 0:
                    candidate_isins = [x[0] for x in liquid_scores[:top_liquid_k]]
                else:
                    candidate_isins = [x[0] for x in liquid_scores]

        schedule_map[s] = tuple(sorted(candidate_isins))

    return UniverseSchedule(schedule_map)

