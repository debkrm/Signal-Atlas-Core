#!/usr/bin/env python3
"""
CANDIDATE seq 12 — `SWING-MEAN-REV-EQ-V1`, pre-registered in `configs/trial_012_candidate.yaml`
(committed at `f2133ef`, sha256 `66a05b4a0c6562fe10579ec0e8369577b02b1f49437aa2d37475dee903a3bfa6`)
before this script existed.

The rule, exactly as pre-registered, with no alternative and no variant:

- entry signal at the close of session T: `close_T > SMA(200)_T AND RSI(2)_T < 10`, RSI(2) by Wilder
  smoothing over split/bonus-adjusted closes;
- exit signal at the close of any session T with `close_T > SMA(5)_T`, filled at T+1's open;
- 2.0xATR(14) protective stop, 21-session hold bound, ₹25 Cr T-1 median-20-session ADTV entry floor,
  0.75% ATR risk sizing and the committed statutory cost schedule — all of them the engine's, unchanged.

**Step 2 gates Step 3.** Before any P&L is read, every entry-signal day whose one-session adjusted
return is below −20% is listed with the corporate-action evidence at that date. A signal that sits on a
move the committed corporate-action table cannot attest is not run around: it stops the round (§5.4,
§6.3, §6.1), because a pullback manufactured by an unattested split/bonus step is a fabricated signal
and every R-multiple computed after it would rest on it.

So this script has two jobs and no third one:

1. `--qa-only` prints the Step 2 counts and lists (no return, no P&L) and exits 1 when the QA is not
   CLEAR, so the refusal is the command's own exit status;
2. `--write` commits the QA evidence `reports/analysis/s101/seq12_data_qa.json`; `--check` recomputes it
   and compares the bytes, so the STOP is reproducible from committed inputs.

The one execution (Step 3), its matched-count random-entry null and the four-clause decision rule are
**NOT RUN** on this tree: the QA stopped the round before the first signal was priced. `N` and `N_eval`
are therefore unchanged, and no registry row or verdict artifact is written.

Usage:
    python scripts/run_seq12_candidate.py --qa-only   # Step 2, exit 1 when not CLEAR
    python scripts/run_seq12_candidate.py --write     # write the committed QA evidence
    python scripts/run_seq12_candidate.py --check     # reproduce the committed bytes
"""

from __future__ import annotations

import argparse
import datetime
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
import scripts.run_seq10_candidate as seq10  # noqa: E402
from signal_core.contracts.criteria import compute_criteria_fingerprint  # noqa: E402
from signal_core.contracts.exchange_series import PriceSeriesContinuityValidator  # noqa: E402
from signal_core.contracts.price_bar import PriceBar  # noqa: E402
from signal_core.features.indicators import compute_atr, compute_rsi, compute_sma  # noqa: E402
from signal_core.research.pit_universe import median_turnover_as_of  # noqa: E402

CONFIG_PATH = REPO_ROOT / "configs" / "trial_012_candidate.yaml"
OUTPUT = REPO_ROOT / "reports" / "analysis" / "s101" / "seq12_data_qa.json"
CA_PATH = REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl"
CORPUS_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
WINDOW_FIRST_SESSION = datetime.date(2018, 4, 2)
WINDOW_LAST_SESSION = datetime.date(2023, 12, 29)

ENTRY_RSI_THRESHOLD = Decimal("10")
EXIT_SMA_PERIOD = 5
TREND_SMA_PERIOD = 200
ATR_PERIOD = 14
MIN_MEDIAN_ADTV_CRORE = Decimal("25.0")
ADTV_LOOKBACK_SESSIONS = 20
PRICE_SIDE_KINDS = ("SPLIT", "BONUS", "CONSOLIDATION")
TRANSITION_KINDS = ("ISIN_TRANSITION", "MERGER", "DELISTING")
NEAR_MISMATCH_SESSIONS = 5
LARGE_DROP_THRESHOLD = Decimal("-0.20")
RATIO_TOLERANCE = Decimal("0.005")
# The corpus's own reconciliation publishes moves beyond this threshold; below it, a ratio-shaped step
# is NOT in `reconciliation.ratio_shaped_detail` and its absence there is not an exoneration.
CORPUS_RECONCILIATION_THRESHOLD = Decimal("0.35")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load_corpus() -> dict:
    corpus_path, problem = seq10.locate_corporate_action_adjusted_corpus()
    if corpus_path is None:
        raise SystemExit(problem)
    with gzip.open(corpus_path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _sessions(corpus: dict) -> List[datetime.date]:
    sessions = [datetime.date.fromisoformat(value) for value in corpus["trading_dates"]]
    return [session for session in sessions if WINDOW_START <= session <= WINDOW_END]


def _bars_by_isin(corpus: dict) -> Dict[str, List[PriceBar]]:
    out: Dict[str, List[PriceBar]] = {}
    for isin, rows in corpus["prices_by_instrument"].items():
        bars = [
            PriceBar(
                instrument_id=isin,
                trade_date=datetime.date.fromisoformat(row["trade_date"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=int(row["volume"]),
                traded_value=Decimal(row["traded_value"]),
            )
            for row in rows
        ]
        bars.sort(key=lambda bar: bar.trade_date)
        out[isin] = bars
    return out


class InstrumentSeries:
    """Per-ISIN session map of the levels the rule reads, partitioned exactly as the engine does."""

    __slots__ = ("rows",)

    def __init__(self, bars: Sequence[PriceBar], sessions: Sequence[datetime.date]) -> None:
        self.rows: Dict[datetime.date, dict] = {}
        segments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
            expected_calendar_sessions=sessions, actual_price_bars=bars
        )
        for segment in segments:
            sma5 = compute_sma(segment, EXIT_SMA_PERIOD)
            sma200 = compute_sma(segment, TREND_SMA_PERIOD)
            rsi2 = compute_rsi(segment, 2)
            atr14 = compute_atr(segment, ATR_PERIOD)
            for bar, s5, s200, r2, atr in zip(segment, sma5, sma200, rsi2, atr14):
                self.rows[bar.trade_date] = {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "sma5": s5,
                    "sma200": s200,
                    "rsi2": r2,
                    "atr14": atr,
                }


def _load_corporate_actions() -> Dict[str, List[dict]]:
    by_isin: Dict[str, List[dict]] = {}
    with CA_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("superseded"):
                continue
            by_isin.setdefault(str(row["isin"]), []).append(row)
    return by_isin


def ratio_shapes(move: Decimal) -> List[str]:
    """
    The share ratios that could produce this one-session move, enumerated the way the corpus's own
    reconciliation enumerates them (1..12 denominators, 1..24 numerators, ±0.5%).

    A non-empty result means "a split or bonus of this shape would print exactly this return", which is
    what makes such a move indistinguishable from a corporate action by price alone (§95.7). It is not
    evidence that one happened.
    """
    target = Decimal(1) + move
    if target <= 0:
        return []
    hits: List[str] = []
    for denominator in range(1, 13):
        for numerator in range(1, 25):
            for candidate in (
                Decimal(numerator) / Decimal(denominator),
                Decimal(denominator) / Decimal(numerator),
            ):
                if abs(candidate - target) / target <= RATIO_TOLERANCE:
                    hits.append(f"{numerator}/{denominator}")
    return hits


def _classify_drop(
    isin: str,
    session: datetime.date,
    move: Decimal,
    opening_gap: Decimal,
    actions: Dict[str, List[dict]],
) -> dict:
    """
    The corporate-action evidence for one signal day's one-session move, and its shape.

    Attested = a price-side record (SPLIT/BONUS/CONSOLIDATION) on the exact ex-date whose share ratio
    reproduces the move within 0.5%. Anything else — a ratio-bearing action on a nearby but different
    date, an ISIN transition, a dividend that cannot reprice anything, or nothing at all — is
    unattested and stops the round (§5.4, §6.3).
    """
    records = actions.get(isin, [])
    ex_dates = {id(r): datetime.date.fromisoformat(str(r["ex_date"])[:10]) for r in records}
    exact = [r for r in records if ex_dates[id(r)] == session]
    near = [
        r
        for r in records
        if ex_dates[id(r)] != session
        and abs((ex_dates[id(r)] - session).days) <= NEAR_MISMATCH_SESSIONS
    ]
    price_side_exact = [r for r in exact if str(r["action_type"]) in PRICE_SIDE_KINDS]
    matched = [
        r
        for r in price_side_exact
        if _ratio_matches(move, r)
    ]
    near_price_side = [r for r in near if str(r["action_type"]) in PRICE_SIDE_KINDS]
    transitions = [r for r in exact + near if str(r["action_type"]) in TRANSITION_KINDS]
    if matched:
        disposition = "ATTESTED_RATIO_MATCH"
    elif price_side_exact:
        disposition = "UNATTESTED_RATIO_MISMATCH"
    elif near_price_side:
        disposition = "UNATTESTED_EX_DATE_MISMATCH"
    elif transitions:
        disposition = "UNATTESTED_TRANSITION"
    else:
        disposition = "UNATTESTED_NO_RECORD"

    def _record(row: dict) -> dict:
        return {
            "ex_date": str(row["ex_date"])[:10],
            "action_type": row["action_type"],
            "ratio": f"{row.get('ratio_numerator')}:{row.get('ratio_denominator')}",
            "circular_ref": row.get("circular_ref"),
            "provenance": row.get("provenance"),
        }

    # Shape: a fall that is already present in the session's opening price is a change of price LEVEL
    # between two sessions — the NIFTYBEES 2019-12-19 shape — and needs an attested corporate action to
    # be a tradable series. A fall that happens after an ordinary open is a session the exchange
    # actually traded, whatever caused it.
    shape = "LEVEL_STEP_AT_OPEN" if opening_gap <= LARGE_DROP_THRESHOLD else "SESSION_MOVE"
    return {
        "isin": isin,
        "signal_session": session.isoformat(),
        "one_day_return": format(move.quantize(Decimal("0.0001")), "f"),
        "opening_gap": format(opening_gap.quantize(Decimal("0.0001")), "f"),
        "shape": shape,
        "ratio_shapes": ratio_shapes(move),
        "disposition": disposition,
        "attested": disposition.startswith("ATTESTED"),
        "records_on_date": [_record(r) for r in exact],
        "records_near_date": [_record(r) for r in near],
        "below_corpus_reconciliation_threshold": abs(move) <= CORPUS_RECONCILIATION_THRESHOLD,
    }


def _ratio_matches(move: Decimal, record: dict) -> bool:
    try:
        numerator = Decimal(str(record.get("ratio_numerator")))
        denominator = Decimal(str(record.get("ratio_denominator")))
    except (ArithmeticError, TypeError, ValueError):
        return False
    if denominator == 0:
        return False
    target = Decimal(1) + move
    if target <= 0:
        return False
    factor = numerator / denominator
    return abs(factor - target) / target <= RATIO_TOLERANCE


def data_qa(criteria) -> dict:
    """
    Step 2: counts and lists only. No return, no P&L (§9.3, §6.3).

    The signal set is the pre-registered entry condition over the point-in-time universe, restricted to
    identities the exchange master resolves to `EQ` on that session: a signal in a series the strategy
    may not enter is not an entry signal (§5.1, §13.1).
    """
    from signal_core.storage.security_master import build_production_security_master

    corpus = _load_corpus()
    sessions = _sessions(corpus)
    index = {session: position for position, session in enumerate(sessions)}
    bars_by_isin = _bars_by_isin(corpus)
    series = {isin: InstrumentSeries(bars, sessions) for isin, bars in bars_by_isin.items()}
    universe = corpus["universe_by_date"]
    actions = _load_corporate_actions()
    master = build_production_security_master()
    floor_inr = MIN_MEDIAN_ADTV_CRORE * Decimal("10000000")

    entry_signals = 0
    first_signal_session: Optional[datetime.date] = None
    blocked_adtv = 0
    blocked_locked = 0
    locked_at_lower = 0
    locked_at_upper = 0
    locked_other = 0
    locked_unbanded = 0
    no_previous_session = 0
    large_drops: List[dict] = []
    other_series_filtered = 0

    universe_days = set(universe.keys())
    for isin, instrument in series.items():
        rows = instrument.rows
        for session, row in rows.items():
            position = index.get(session)
            if position is None or position + 1 >= len(sessions):
                continue
            if row["sma200"] is None or row["rsi2"] is None:
                continue
            if not (row["close"] > row["sma200"] and row["rsi2"] < ENTRY_RSI_THRESHOLD):
                continue
            day_key = session.isoformat()
            if day_key not in universe_days or isin not in universe[day_key]:
                continue
            symbol_interval = master.resolve_symbol(isin, session)
            if symbol_interval is None or symbol_interval.series != "EQ":
                other_series_filtered += 1
                continue

            entry_signals += 1
            if first_signal_session is None or session < first_signal_session:
                first_signal_session = session

            # (i) the liquidity floor, read exactly as the engine reads it: the 20 sessions before T.
            median = median_turnover_as_of(
                session,
                calendar_sessions=sessions,
                bars_by_date={bar.trade_date: bar for bar in bars_by_isin[isin] if bar.trade_date in index},
                lookback_sessions=ADTV_LOOKBACK_SESSIONS,
                session_index=index,
            )
            if median is None or median < floor_inr:
                blocked_adtv += 1

            # (ii) a session the buyer could not have bought: the T+1 bar is locked (high == low).
            next_session = sessions[position + 1]
            next_row = rows.get(next_session)
            if next_row is not None and next_row["high"] == next_row["low"]:
                blocked_locked += 1
                band = master.get_price_band(isin, next_session, prev_close=row["close"])
                lower = band.lower_circuit_limit if band is not None else None
                upper = band.upper_circuit_limit if band is not None else None
                if band is None:
                    locked_unbanded += 1
                elif lower is not None and next_row["low"] <= lower:
                    locked_at_lower += 1
                elif upper is not None and next_row["high"] >= upper:
                    locked_at_upper += 1
                else:
                    locked_other += 1

            # (iii) every signal day whose one-session adjusted return is below −20%. The previous bar
            # must be the calendar-previous session's bar: a multi-session gap is never one session's
            # return, so a signal whose prior session is absent is counted, not computed (§6.3).
            if position == 0:
                no_previous_session += 1
                continue
            previous_row = rows.get(sessions[position - 1])
            if previous_row is None:
                no_previous_session += 1
                continue
            if previous_row["close"] <= 0:
                continue
            move = (row["close"] - previous_row["close"]) / previous_row["close"]
            if move >= LARGE_DROP_THRESHOLD:
                continue
            opening_gap = (row["open"] - previous_row["close"]) / previous_row["close"]
            large_drops.append(_classify_drop(isin, session, move, opening_gap, actions))

    unattested_steps = [
        row for row in large_drops if row["shape"] == "LEVEL_STEP_AT_OPEN" and not row["attested"]
    ]
    session_moves = [row for row in large_drops if row["shape"] == "SESSION_MOVE"]
    first_sma200 = None
    for instrument in series.values():
        available = [day for day, row in instrument.rows.items() if row["sma200"] is not None]
        if not available:
            continue
        earliest = min(available)
        if first_sma200 is None or earliest < first_sma200:
            first_sma200 = earliest

    return {
        "artifact": "seq12_data_qa",
        "section": "§101 Step 2 (AGENTS.md §5.4, §6.3, §9.3)",
        "not_audited": True,
        "mode": "COUNTS_AND_LISTS_ONLY_NO_PNL",
        "pre_registration": {
            "path": CONFIG_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(CONFIG_PATH),
            "trial_id": str(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["metadata"]["trial_id"]),
        },
        "corpus": {
            "path": CORPUS_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(CORPUS_PATH),
            "sessions": len(sessions),
            "first_session": sessions[0].isoformat(),
            "last_session": sessions[-1].isoformat(),
        },
        "criteria": {
            "version": criteria.version,
            "fingerprint": compute_criteria_fingerprint(criteria),
        },
        "method": (
            "the pre-registered entry condition (close > SMA(200) and RSI(2) < 10, Wilder, on "
            "split/bonus-adjusted closes) over the point-in-time universe, restricted to identities the "
            "exchange master resolves to EQ on that session; features partitioned into continuous "
            "subsegments exactly as the engine partitions them; counts and lists computed before any P&L "
            "is read"
        ),
        "instruments_scanned": len(series),
        "signals_in_non_eq_series": other_series_filtered,
        "sma200_available_from_session": first_sma200.isoformat() if first_sma200 else None,
        "first_signal_session": first_signal_session.isoformat() if first_signal_session else None,
        "first_signal_is_window_open": (
            first_signal_session == WINDOW_FIRST_SESSION if first_signal_session else False
        ),
        "entry_signals": entry_signals,
        "blocked_by_adtv_floor": blocked_adtv,
        "blocked_by_locked_session": {
            "total": blocked_locked,
            "at_lower_circuit": locked_at_lower,
            "at_upper_circuit": locked_at_upper,
            "banded_but_not_at_a_limit": locked_other,
            "no_band_recorded": locked_unbanded,
        },
        "signals_without_a_calendar_previous_session": no_previous_session,
        "below_minus_20pct_one_day": large_drops,
        "below_minus_20pct_count": len(large_drops),
        "below_minus_20pct_level_step_at_open": sum(
            1 for row in large_drops if row["shape"] == "LEVEL_STEP_AT_OPEN"
        ),
        "below_minus_20pct_session_move": len(session_moves),
        "unattested_level_steps_feeding_a_signal": len(unattested_steps),
        "status": "CLEAR" if not unattested_steps else "STOP",
        "stop_reason": (
            None
            if not unattested_steps
            else (
                f"{len(unattested_steps)} entry-signal day(s) open more than "
                f"{abs(LARGE_DROP_THRESHOLD) * 100:.0f}% below the previous close — a change of price "
                f"level between two sessions, not a session's trading — with no price-side corporate "
                f"action attested on that date; "
                f"{sum(1 for row in unattested_steps if row['ratio_shapes'])} of them are ratio-shaped"
            )
        ),
        "not_run": {
            "one_execution_seq12": "NOT RUN — Step 2 did not clear",
            "random_entry_null": "NOT RUN — no strategy arm to match",
            "decision_rule": "NOT RUN — no metrics to decide on",
            "registry_trial_count": "UNCHANGED at 11",
            "registry_evaluated_count": "UNCHANGED at 6",
        },
        "limitations": [
            "the QA enumerates ratio shapes the way the corpus reconciliation does (1..12 over 1..24, "
            "±0.5%); a non-empty list means a split or bonus of that shape would print exactly this "
            "return, not that one happened",
            "the corpus's reconciliation publishes moves beyond ±35%, so a smaller unattested step is "
            "absent from `reconciliation.ratio_shaped_detail` and that absence is not an exoneration",
            "the ADTV count is a per-signal counter: a name can be counted once per signal day it was "
            "excluded on, not once per name",
            "the locked-session count reads the T+1 bar's high == low and the security master's band at "
            "T+1; it is the fill-blocking condition, not a claim about queue position",
            "a move that happens inside a session whose opening price is continuous with the previous "
            "close is classified SESSION_MOVE and is not a corporate-action step: the exchange traded it, "
            "and the rule is pre-registered to buy that pullback. Only an opening gap beyond the "
            "threshold is a level step, and only an unattested level step stops the round",
            "the opening-gap test uses the corpus's own adjusted open against the previous adjusted "
            "close, so an adjustment applied at the wrong date would show as a level step here",
        ],
    }


def qa_gate(qa: dict) -> Optional[str]:
    """The Step 2 gate: Step 3 may only execute on a CLEAR QA."""
    if qa["status"] != "CLEAR":
        return str(qa["stop_reason"])
    return None


def _render(qa: dict) -> str:
    return json.dumps(qa, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-only", action="store_true", help="Step 2 counts and lists only")
    parser.add_argument("--write", action="store_true", help="write the committed QA evidence")
    parser.add_argument("--check", action="store_true", help="reproduce the committed QA evidence")
    args = parser.parse_args()

    criteria = walkforward.load_go_no_go_criteria()
    qa = data_qa(criteria)
    problems: List[str] = []
    if criteria.version != "1.1.16":
        problems.append(f"the criteria are {criteria.version}, not the pre-registered 1.1.16")
    pre_registered = json.loads(
        json.dumps(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["metadata"])
    )
    if qa["criteria"]["fingerprint"] != pre_registered["criteria_fingerprint"]:
        problems.append(
            f"the live criteria fingerprint {qa['criteria']['fingerprint']} is not the pre-registered "
            f"{pre_registered['criteria_fingerprint']}"
        )
    if problems:
        print("OVERALL: NOT REGISTERED — " + "; ".join(problems))
        return 1

    if args.check:
        if not OUTPUT.is_file():
            print(f"FAIL: no committed QA evidence at {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
            return 1
        if OUTPUT.read_text(encoding="utf-8") != _render(qa):
            print("FAIL: the recomputed Step 2 QA is not the committed one")
            return 1
        # The check's own claim is byte reproducibility. The QA verdict travels inside the bytes, so a
        # STOP is reported here as content, not as a failure to reproduce.
        print(f"PASS: the Step 2 QA reproduces the committed bytes (QA status {qa['status']})")
        return 0

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(_render(qa), encoding="utf-8", newline="\n")
        print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
        print(f"QA STATUS: {qa['status']}")
        if qa_gate(qa) is not None:
            print(f"OVERALL: STOP — {qa['stop_reason']}")
            print("         Step 3 is NOT RUN: no session was simulated, no P&L was read.")
        return 0

    print(json.dumps({k: v for k, v in qa.items() if k not in ("below_minus_20pct_one_day",)}, indent=1))
    for row in qa["below_minus_20pct_one_day"]:
        print(json.dumps(row))

    gate = qa_gate(qa)
    if gate is not None:
        print(f"OVERALL: STOP — {gate}")
        print(
            "         Step 3 is NOT RUN: no session was simulated, no P&L was read, no registry row and "
            "no verdict artifact was written."
        )
        return 1
    print("OVERALL: QA CLEAR — Step 3 is authorised (it is not executed by this command).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
