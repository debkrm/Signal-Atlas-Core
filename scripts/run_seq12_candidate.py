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

**What "attested" means (stated before any count is re-derived, N-196, §100.16 item 1).** A move is
attested when a corporate-action record on that exact ex-date predicts the session's level, either

- a price-side record (SPLIT / BONUS / CONSOLIDATION) whose share ratio reproduces the move within
  `RATIO_TOLERANCE` = 0.5 %, or
- a cash record (DIVIDEND / RIGHTS) whose cash amount reproduces the session's close **or** its opening
  price within `CASH_ADJUSTMENT_TOLERANCE` = **0.5 % of the previous close**: a dividend predicts
  `previous_close - amount`, a rights entitlement predicts the theoretical ex-rights price
  `(previous_close*denominator + premium*numerator) / (denominator + numerator)`.

An ex-dividend or ex-rights session reprices the stock by the cash it removes, permanently (§5.4,
§13.2), so a cash record that reproduces the level attests the step. A cash record that does not
reproduce it is published as `UNATTESTED_CASH_MISMATCH` naming its residual, not disposed of.

**The window, not only the day (N-197, §100.16 item 2).** The signal day is not the only session whose
price level the rule reads: `SMA(200)` and `RSI(2)` at T are computed over the 199 sessions before it.
So the same attestation test is applied to every pair of consecutive sessions in the corpus, in both
directions, and a signal whose own continuous 200-session window contains an unattested step of 10% or
more is counted and excluded from the usable set — it does not extend the STOP class, which remains the
signal day's −20% step.

So this script has two jobs and no third one:

1. `--qa-only` prints the Step 2 counts and lists (no return, no P&L) and exits 1 when the QA is not
   CLEAR, so the refusal is the command's own exit status;
2. `--write` commits the QA evidence `reports/analysis/s102/seq12_data_qa.json`, which cites the §101
   artifact it supersedes by hash; `--check` recomputes it and compares the bytes, so the STOP is
   reproducible from committed inputs.

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
import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

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
from signal_core.storage.artifact_digest import binary_digest, text_digest  # noqa: E402
from scripts.artifact_restatement import predecessor_pointer  # noqa: E402

CONFIG_PATH = REPO_ROOT / "configs" / "trial_012_candidate.yaml"
# §102 re-derives the Step 2 counts under the widened attestation test; the §101 artifact is left
# unedited as that round's record and is cited here by hash (AGENTS.md §10.1, §97.5 N-194).
OUTPUT = REPO_ROOT / "reports" / "analysis" / "s102" / "seq12_data_qa.json"
# The revision of this path the artifact replaced: `git log -- <path>` shows 46a99ec (created) and
# 325bab8 (rewritten in place). Pinned rather than taken from HEAD, so the artifact reproduces (§102.10).
PREDECESSOR_COMMIT = "46a99eccb8af5b4ba2ccd6bef003842eaa3ce17f"
RESTATED_ARTIFACT = REPO_ROOT / "reports" / "analysis" / "s101" / "seq12_data_qa.json"
RESTATED_FIELDS = (
    "status",
    "stop_reason",
    "unattested_level_steps_feeding_a_signal",
    "below_minus_20pct_level_step_at_open",
    "blocked_by_locked_session",
)
CA_PATH = REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl"
BRONZE_CA_DIR = REPO_ROOT / "data" / "raw" / "corporate_actions"
CORPUS_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"
PRICE_BAND_DIR = REPO_ROOT / "data" / "silver" / "price_bands"
NOT_RUN = "NOT RUN"

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
# N-196: an ex-dividend or ex-rights session reprices by the cash it removes, so a cash record on the
# exact ex-date is an attestation test like a share-ratio record is. Tolerance is on the previous close.
CASH_ADJUSTMENT_KINDS = ("DIVIDEND", "RIGHTS")
CASH_ADJUSTMENT_TOLERANCE = Decimal("0.005")
# "Rights Entitlement 1:14 @ INR 535" / "Rights 49:100 @ Premium Rs 9/-": the premium is prose.
RIGHTS_PREMIUM_PATTERN = re.compile(r"@\s*(?:Premium\s+(?:[Oo]f\s+)?)?(?:INR|Rs\.?)\s*([0-9]+(?:\.[0-9]+)?)")
TRANSITION_KINDS = ("ISIN_TRANSITION", "MERGER", "DELISTING")
NEAR_MISMATCH_SESSIONS = 5
# N-197: the trigger is manufactured by a level step anywhere in the 200-session window that feeds
# SMA(200) and RSI(2), not only on the signal day, and not only downward. A step of 10% or more on a
# previous close under ₹5 is a tick artefact rather than a change of level.
LOOKBACK_SESSIONS = TREND_SMA_PERIOD
UNATTESTED_STEP_GAP = Decimal("0.10")
GAP_TEST_MIN_PREVIOUS_CLOSE = Decimal("5")
SIGNAL_LEVEL_STEP_DETAIL_LIMIT = 200
LARGE_DROP_THRESHOLD = Decimal("-0.20")
RATIO_TOLERANCE = Decimal("0.005")
# The corpus's own reconciliation publishes moves beyond this threshold; below it, a ratio-shaped step
# is NOT in `reconciliation.ratio_shaped_detail` and its absence there is not an exoneration.
CORPUS_RECONCILIATION_THRESHOLD = Decimal("0.35")


# §102.3 Ruling 1: a text digest is the LF-normalised stored form and a binary digest the stored bytes;
# each arm refuses the other's path, so neither can be handed a path it would hash wrongly (N-203, N-204).
_digest_text = text_digest
_digest_bytes = binary_digest


def rights_branch_exercise(actions: Dict[str, List[dict]], bars_by_isin: Dict[str, List[PriceBar]], sessions):
    """
    How often the RIGHTS/TERP attestation branch could have fired (§101.12 item 6, §5.4).

    A rights entitlement is tested as the theoretical ex-rights price, which needs the issue ratio and
    premium parsed out of a free-text `description`. The branch is only exercised by a rights record on
    the exact ex-date of a candidate level step, so this counts those records and the ones that sit on
    a step of `UNATTESTED_STEP_GAP` or more. A zero here is why the branch's arithmetic is unproven
    rather than proven.
    """
    index = {session: position for position, session in enumerate(sessions)}
    rows = 0
    on_a_candidate_step = 0
    for isin, records in actions.items():
        bars = {bar.trade_date: bar for bar in bars_by_isin.get(isin, [])}
        for record in records:
            if str(record.get("action_type")) != "RIGHTS":
                continue
            rows += 1
            ex_date = datetime.date.fromisoformat(str(record["ex_date"])[:10])
            position = index.get(ex_date)
            bar = bars.get(ex_date)
            if position is None or position == 0 or bar is None:
                continue
            previous = bars.get(sessions[position - 1])
            if previous is None or previous.close < GAP_TEST_MIN_PREVIOUS_CLOSE:
                continue
            if abs((bar.open - previous.close) / previous.close) >= UNATTESTED_STEP_GAP:
                on_a_candidate_step += 1
    return {"records_in_the_table": rows, "records_on_a_candidate_step": on_a_candidate_step}


def corpus_reconciliation_claim(corpus: dict) -> dict:
    """
    What the corpus's per-bar stamp and its reconciliation detail actually claim (N-201, §101.12 item 4).

    Two claims travel with the corpus and are corrected here rather than in its bytes. First, the
    per-bar `adjustment_version` names the series-level adjustment **policy**, not an attestation that
    this bar's level was adjusted: `INF732E01011`'s 2019-12-19 bar sits at the post-renomination unit
    because no committed payload attests the 1:10 across its ISIN transition, and it still carries the
    stamp. Second, `reconciliation.ratio_shaped_detail` is a filtered list — moves beyond ±35% whose
    one-session return is ratio-shaped within ±0.5% and has no archive record — not a census of
    unadjusted level breaks: that boundary's ratio is outside the ±0.5% band around 0.1, so it is
    counted in `no_ratio_match` and appears in no detail list at all.

    The corpus itself is frozen this round: its header is covered by the manifest and the manifest by
    `expected_manifest_fingerprint`, so restating it is a criteria re-seal, not a data-hygiene edit.
    """
    bars = {row["trade_date"]: row for row in corpus["prices_by_instrument"]["INF732E01011"]}
    previous_close = Decimal(bars["2019-12-18"]["close"])
    close = Decimal(bars["2019-12-19"]["close"])
    reconciliation = corpus["reconciliation"]
    listed = any(
        row["isin"] == "INF732E01011" and row["session"] == "2019-12-19"
        for row in reconciliation["ratio_shaped_detail"]
    )
    return {
        "detail_is_a_census": False,
        "detail_scope": (
            f"`reconciliation.ratio_shaped_detail` lists the {len(reconciliation['ratio_shaped_detail'])} "
            f"moves beyond ±{reconciliation['threshold']} whose one-session return is ratio-shaped within "
            "±0.5% and carries no archive record. It is not a census of unadjusted level breaks: a move "
            "below the threshold is not listed, a move outside the ratio band is counted in "
            f"`no_ratio_match` ({reconciliation['no_ratio_match']} rows), and a pair straddling a "
            f"calendar gap ({reconciliation['cross_gap_pairs']} pairs) is a gap record, not a session "
            "return. Absence from the list is not an exoneration (N-201)."
        ),
        "unattested_unit_break": {
            "isin": "INF732E01011",
            "session": "2019-12-19",
            "previous_close": format(previous_close, "f"),
            "close": format(close, "f"),
            "ratio": format((close / previous_close).quantize(Decimal("0.000001")), "f"),
            "adjustment_stamp": corpus["adjustment_version"],
            "stamp_scope": "SERIES_POLICY_NOT_A_PER_BAR_ATTESTATION",
            "attested": False,
            "listed_in_ratio_shaped_detail": listed,
        },
    }


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

    __slots__ = ("rows", "segment_of", "segment_position")

    def __init__(self, bars: Sequence[PriceBar], sessions: Sequence[datetime.date]) -> None:
        self.rows: Dict[datetime.date, dict] = {}
        self.segment_of: Dict[datetime.date, int] = {}
        self.segment_position: Dict[datetime.date, int] = {}
        segments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
            expected_calendar_sessions=sessions, actual_price_bars=bars
        )
        for ordinal, segment in enumerate(segments):
            sma5 = compute_sma(segment, EXIT_SMA_PERIOD)
            sma200 = compute_sma(segment, TREND_SMA_PERIOD)
            rsi2 = compute_rsi(segment, 2)
            atr14 = compute_atr(segment, ATR_PERIOD)
            for position, (bar, s5, s200, r2, atr) in enumerate(
                zip(segment, sma5, sma200, rsi2, atr14)
            ):
                self.segment_of[bar.trade_date] = ordinal
                self.segment_position[bar.trade_date] = position
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

    def steps_in_lookback(
        self,
        steps: Sequence[tuple],
        session: datetime.date,
        window: int = LOOKBACK_SESSIONS,
    ) -> List[tuple]:
        """
        The level steps inside this session's own continuous feature window, `[T-window+1, T]`.

        The window is the one `SMA(200)` and `RSI(2)` at T are computed over, so a step in a previous
        continuous subsegment is not in it: the engine already refused that lookback (§6.3, N-197).
        """
        segment = self.segment_of[session]
        position = self.segment_position[session]
        return [
            step
            for step in steps
            if self.segment_of.get(step[0]) == segment
            and 0 <= position - self.segment_position[step[0]] < window
        ]


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


def artifact_consumers() -> List[str]:
    """
    Committed code that reads this artifact. Empty means the STOP gates nothing (§14.4, N-198).

    The producer itself and the audit probe are excluded by name and the exclusion is published beside
    the result, so "no consumer" is a scan with a stated boundary rather than an assumption.
    """
    consumers: List[str] = []
    for path in sorted((REPO_ROOT / "scripts").glob("*.py")) + sorted(
        (REPO_ROOT / "src").rglob("*.py")
    ):
        if path.resolve() == Path(__file__).resolve() or path.name == "probe_audit_findings.py":
            continue
        if OUTPUT.stem in path.read_text(encoding="utf-8", errors="ignore"):
            consumers.append(path.relative_to(REPO_ROOT).as_posix())
    return consumers


def _price_band_partition_files() -> List[Path]:
    return [path for path in PRICE_BAND_DIR.rglob("*") if path.is_file()] if PRICE_BAND_DIR.is_dir() else []


def band_counter(value: int, bands_recorded: bool):
    """
    A categorical band counter is a measurement only where bands are recorded (N-199, §100.16 item 4).

    While `data/silver/price_bands` is empty `get_price_band()` returns None for every session, so 0
    would report the reader's blindness as the market's quiet.
    """
    return value if bands_recorded else NOT_RUN


def corporate_action_archive_coverage(scanned_isins: Sequence[str]) -> Tuple[dict, Dict[str, int]]:
    """
    How much of the scanned set the Bronze corporate-action archive covers (N-200, §10.5).

    `UNATTESTED_NO_RECORD` is only evidence of `no corporate action` where the archive covers the
    instrument, so the coverage travels with the verdict instead of behind it.
    """
    per_isin: Dict[str, int] = {}
    rows = 0
    payloads = sorted(BRONZE_CA_DIR.glob("*.json"))
    for path in payloads:
        for row in json.loads(path.read_text(encoding="utf-8")):
            isin = str(row.get("isin") or "").strip()
            if not isin or isin == "-":
                continue
            rows += 1
            per_isin[isin] = per_isin.get(isin, 0) + 1
    uncovered = [isin for isin in scanned_isins if isin not in per_isin]
    return {
        "bronze_payloads": len(payloads),
        "bronze_rows": rows,
        "bronze_distinct_isins": len(per_isin),
        "instruments_scanned": len(scanned_isins),
        "instruments_with_no_bronze_record": len(uncovered),
        "share_of_scanned_set_with_no_bronze_record": (
            format(
                (Decimal(len(uncovered)) / Decimal(len(scanned_isins)) * 100).quantize(Decimal("0.1")),
                "f",
            )
            + "%"
            if scanned_isins
            else "0.0%"
        ),
        "reading": (
            "UNATTESTED_NO_RECORD means 'no record in this archive', not 'no corporate action': an "
            "instrument the archive does not cover at all cannot be exonerated by it (§10.5, N-200)"
        ),
    }, per_isin


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


def _level(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _cash_adjustment_prediction(previous_close: Decimal, record: dict) -> Optional[dict]:
    """
    The post-adjustment level an exact-date cash record predicts, or None when it carries no cash.

    A dividend removes its amount from the previous close. A rights entitlement removes the gap between
    the cum-rights price and the theoretical ex-rights price, `(prev*den + premium*num) / (den + num)`;
    its premium is prose in the archive's `description` ("Rights Entitlement 1:14 @ INR 535"), so it is
    parsed, and a rights row whose description carries no premium has no cash test.
    """
    kind = str(record.get("action_type"))
    try:
        numerator = Decimal(str(record.get("ratio_numerator")))
        denominator = Decimal(str(record.get("ratio_denominator")))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if previous_close <= 0:
        return None
    if kind == "DIVIDEND":
        try:
            amount = Decimal(str(record.get("dividend_amount")))
        except (ArithmeticError, TypeError, ValueError):
            return None
        if amount <= 0:
            return None
        return {"amount": amount, "predicted": previous_close - amount, "basis": "DIVIDEND_AMOUNT"}
    if kind == "RIGHTS":
        match = RIGHTS_PREMIUM_PATTERN.search(str(record.get("description") or ""))
        if match is None or numerator <= 0 or denominator <= 0:
            return None
        premium = Decimal(match.group(1))
        total = numerator + denominator
        predicted = (previous_close * denominator + premium * numerator) / total
        return {"amount": premium, "predicted": predicted, "basis": "RIGHTS_TERP"}
    return None


def _cash_adjustment_test(previous_close: Decimal, move: Decimal, opening_gap: Decimal, record: dict) -> Optional[dict]:
    """One exact-date cash record against the session's close and opening price (§100.16 item 1)."""
    prediction = _cash_adjustment_prediction(previous_close, record)
    if prediction is None:
        return None
    close = previous_close * (Decimal(1) + move)
    opening = previous_close * (Decimal(1) + opening_gap)
    close_residual = abs(close - prediction["predicted"]) / previous_close
    opening_residual = abs(opening - prediction["predicted"]) / previous_close
    return {
        "action_type": str(record.get("action_type")),
        "basis": prediction["basis"],
        "amount": _level(prediction["amount"]),
        "predicted_level": _level(prediction["predicted"]),
        "close_residual": _level(close_residual),
        "opening_residual": _level(opening_residual),
        "matched": min(close_residual, opening_residual) <= CASH_ADJUSTMENT_TOLERANCE,
    }


def _classify_drop(
    isin: str,
    session: datetime.date,
    move: Decimal,
    opening_gap: Decimal,
    previous_close: Decimal,
    actions: Dict[str, List[dict]],
) -> dict:
    """
    The corporate-action evidence for one signal day's one-session move, and its shape.

    Attested = a record on the exact ex-date that predicts the session's level: a price-side record
    (SPLIT/BONUS/CONSOLIDATION) whose share ratio reproduces the move within `RATIO_TOLERANCE`, or a
    cash record (DIVIDEND/RIGHTS) whose cash amount reproduces the close or the opening price within
    `CASH_ADJUSTMENT_TOLERANCE` of the previous close. Anything else — a cash record that does not
    reproduce the level, a ratio-bearing action on a nearby but different date, an ISIN transition, or
    nothing at all — is unattested and stops the round (§5.4, §6.3).
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
    cash_exact = [r for r in exact if str(r["action_type"]) in CASH_ADJUSTMENT_KINDS]
    cash_tests = [
        test
        for test in (
            _cash_adjustment_test(previous_close, move, opening_gap, record) for record in cash_exact
        )
        if test is not None
    ]
    cash_matched = [test for test in cash_tests if test["matched"]]
    near_price_side = [r for r in near if str(r["action_type"]) in PRICE_SIDE_KINDS]
    transitions = [r for r in exact + near if str(r["action_type"]) in TRANSITION_KINDS]
    if matched:
        disposition = "ATTESTED_RATIO_MATCH"
    elif cash_matched:
        disposition = "ATTESTED_CASH_ADJUSTMENT"
    elif price_side_exact:
        disposition = "UNATTESTED_RATIO_MISMATCH"
    elif near_price_side:
        disposition = "UNATTESTED_EX_DATE_MISMATCH"
    elif cash_exact:
        disposition = "UNATTESTED_CASH_MISMATCH"
    elif transitions:
        disposition = "UNATTESTED_TRANSITION"
    else:
        disposition = "UNATTESTED_NO_RECORD"

    def _record(row: dict) -> dict:
        return {
            "ex_date": str(row["ex_date"])[:10],
            "action_type": row["action_type"],
            "ratio": f"{row.get('ratio_numerator')}:{row.get('ratio_denominator')}",
            "dividend_amount": row.get("dividend_amount"),
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
        "cash_adjustment": {
            "tolerance_of_previous_close": format(CASH_ADJUSTMENT_TOLERANCE, "f"),
            "tested": cash_tests,
        },
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


def restatement_of_previous(qa: dict) -> dict:
    """
    The §101 artifact this one supersedes, pinned by hash, with every field that moved named (N-194).

    The correction is an append: the superseded file is untouched, and the fields that changed are
    published as `published_there` / `published_here` pairs so a reader can diff the two rounds without
    trusting either summary.
    """
    path = RESTATED_ARTIFACT.relative_to(REPO_ROOT).as_posix()
    if not RESTATED_ARTIFACT.is_file():
        return {"path": path, "available": False, "sha256": None, "changed_fields": {}}
    raw = RESTATED_ARTIFACT.read_bytes()
    previous = json.loads(raw.decode("utf-8"))
    return {
        "path": path,
        "available": True,
        "sha256": _digest_text(RESTATED_ARTIFACT),
        "sha256_of": "the superseded artifact's stored text bytes with CRLF normalised to LF",
        "superseded_artifact_left_unedited": True,
        "changed_fields": {
            field: {"published_there": previous.get(field), "published_here": qa.get(field)}
            for field in RESTATED_FIELDS
            if previous.get(field) != qa.get(field)
        },
        "reason": (
            "N-196: a DIVIDEND or RIGHTS record on the exact ex-date is now an attestation test when its "
            "cash amount reproduces the close or the opening price within 0.5% of the previous close. "
            "N-197: unattested level steps inside the 200-session feature window are counted and excluded "
            "from the usable set. N-199: the three categorical band counters report NOT RUN while "
            "data/silver/price_bands is empty. N-200: the archive's coverage travels with the no-record "
            "verdict. The window, the rule, the criteria and the corpus are unchanged."
        ),
    }


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
    coverage, bronze_records_by_isin = corporate_action_archive_coverage(list(series))
    band_files = _price_band_partition_files()
    bands_recorded = bool(band_files)
    consumers = artifact_consumers()

    entry_signals = 0
    signals_without_a_next_session = 0
    signals_without_a_next_session_in_eq_series = 0
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
    level_step_events = 0
    level_step_events_on_a_signal_day = 0
    instruments_with_a_level_step = 0
    signals_with_a_level_step_in_lookback = 0
    signal_level_steps: List[dict] = []

    universe_days = set(universe.keys())
    for isin, instrument in series.items():
        rows = instrument.rows
        # (0) every unattested change of price level inside this instrument's continuous segments: an
        # opening gap of 10% or more in either direction that no corporate-action record at that date
        # predicts. A feature window containing one is not a window the rule may be priced on (§6.3).
        steps: List[tuple] = []
        previous_by_segment: Dict[int, datetime.date] = {}
        for step_session in sorted(rows):
            segment = instrument.segment_of[step_session]
            previous_session = previous_by_segment.get(segment)
            previous_by_segment[segment] = step_session
            if previous_session is None:
                continue
            step_previous_close = rows[previous_session]["close"]
            if step_previous_close < GAP_TEST_MIN_PREVIOUS_CLOSE:
                continue
            step_gap = (rows[step_session]["open"] - step_previous_close) / step_previous_close
            if abs(step_gap) < UNATTESTED_STEP_GAP:
                continue
            step_move = (rows[step_session]["close"] - step_previous_close) / step_previous_close
            classified = _classify_drop(
                isin, step_session, step_move, step_gap, step_previous_close, actions
            )
            if classified["attested"]:
                continue
            steps.append(
                (step_session, step_gap.quantize(Decimal("0.0001")), classified["disposition"])
            )
        level_step_events += len(steps)
        instruments_with_a_level_step += 1 if steps else 0
        step_days = {step[0] for step in steps}

        for session, row in rows.items():
            position = index.get(session)
            if position is None:
                continue
            fillable = position + 1 < len(sessions)
            if row["sma200"] is None or row["rsi2"] is None:
                continue
            if not (row["close"] > row["sma200"] and row["rsi2"] < ENTRY_RSI_THRESHOLD):
                continue
            day_key = session.isoformat()
            if day_key not in universe_days or isin not in universe[day_key]:
                continue
            symbol_interval = master.resolve_symbol(isin, session)
            in_eq_series = symbol_interval is not None and symbol_interval.series == "EQ"

            # §7.1: a signal on the window's final session has no T+1 open to fill at. It is not an
            # executable signal, and it is counted rather than dropped by the guard (§101.12 item 5).
            # Counted before the series filter so `signals_in_non_eq_series` keeps describing exactly
            # the signals the runner refused for their series.
            if not fillable:
                signals_without_a_next_session += 1
                if in_eq_series:
                    signals_without_a_next_session_in_eq_series += 1
                continue
            if not in_eq_series:
                other_series_filtered += 1
                continue

            entry_signals += 1
            if first_signal_session is None or session < first_signal_session:
                first_signal_session = session

            # (iv) the same level step, over the lookback window instead of the signal day only.
            if session in step_days:
                level_step_events_on_a_signal_day += 1
            steps_in_window = instrument.steps_in_lookback(steps, session)
            if steps_in_window:
                signals_with_a_level_step_in_lookback += 1
                if len(signal_level_steps) < SIGNAL_LEVEL_STEP_DETAIL_LIMIT:
                    signal_level_steps.append(
                        {
                            "isin": isin,
                            "signal_session": session.isoformat(),
                            "level_steps_in_lookback": [
                                {
                                    "session": step[0].isoformat(),
                                    "opening_gap": format(step[1], "f"),
                                    "disposition": step[2],
                                }
                                for step in steps_in_window
                            ],
                        }
                    )

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
            drop = _classify_drop(
                isin, session, move, opening_gap, previous_row["close"], actions
            )
            drop["bronze_records_for_isin"] = bronze_records_by_isin.get(isin, 0)
            large_drops.append(drop)

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

    qa = {
        "artifact": "seq12_data_qa",
        "section": "§101 Step 2 (AGENTS.md §5.4, §6.3, §9.3)",
        "not_audited": True,
        "mode": "COUNTS_AND_LISTS_ONLY_NO_PNL",
        "pre_registration": {
            "path": CONFIG_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest_text(CONFIG_PATH),
            "sha256_of": "the config's stored text bytes with CRLF normalised to LF",
            "trial_id": str(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["metadata"]["trial_id"]),
        },
        "corpus": {
            "path": CORPUS_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest_bytes(CORPUS_PATH),
            "sha256_of": (
                "the file's stored bytes, unnormalised: a gzip stream is `-text` and has no LF form, so "
                "the raw digest is the only one a reader can reproduce and the one the manifest and the "
                "s100 comparison publish (N-204)"
            ),
            "sessions": len(sessions),
            "first_session": sessions[0].isoformat(),
            "last_session": sessions[-1].isoformat(),
        },
        "criteria": {
            "version": criteria.version,
            "fingerprint": compute_criteria_fingerprint(criteria),
        },
        "corpus_reconciliation": corpus_reconciliation_claim(corpus),
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
        "entry_signal_scope": (
            "executable signals, as the runner resolves them: EQ on that session, in the point-in-time "
            "universe, and with a T+1 session to fill at (§7.1). The final session's predicate-and-"
            "universe signals are counted in `signals_without_a_next_session` (and the EQ ones in "
            "`signals_without_a_next_session_in_eq_series`), not dropped by the guard (§101.12 item 5)."
        ),
        "signals_without_a_next_session": signals_without_a_next_session,
        "signals_without_a_next_session_in_eq_series": signals_without_a_next_session_in_eq_series,
        "entry_signals_including_the_final_session": (
            entry_signals + signals_without_a_next_session_in_eq_series
        ),
        "blocked_by_adtv_floor": blocked_adtv,
        "blocked_by_locked_session": {
            "total": blocked_locked,
            # The three categorical counters read a price-band record. While the partition is empty
            # `master.get_price_band()` returns None for every session, so 0 would be a property of the
            # reader rather than of the market: they are NOT RUN (N-199, §100.16 item 4).
            "at_lower_circuit": band_counter(locked_at_lower, bands_recorded),
            "at_upper_circuit": band_counter(locked_at_upper, bands_recorded),
            "banded_but_not_at_a_limit": band_counter(locked_other, bands_recorded),
            "no_band_recorded": locked_unbanded,
            "price_band_partition": {
                "path": PRICE_BAND_DIR.relative_to(REPO_ROOT).as_posix(),
                "files": len(band_files),
                "populated": bands_recorded,
                "needs": (
                    None
                    if bands_recorded
                    else (
                        "a sourced per-session NSE price-band payload (data/silver/price_bands is "
                        "empty and data/raw holds no price-band archive either); the bands are not "
                        "derived from prices, which would make the counter a restatement of the bar "
                        "it tests"
                    )
                ),
            },
        },
        "signals_without_a_calendar_previous_session": no_previous_session,
        "feature_window_policy": {
            "window_sessions": LOOKBACK_SESSIONS,
            "unattested_step_gap_threshold": format(UNATTESTED_STEP_GAP, "f"),
            "previous_close_floor_inr": format(GAP_TEST_MIN_PREVIOUS_CLOSE, "f"),
            "attestation": (
                "the same test the stop uses: a price-side ratio on the exact ex-date, or a cash amount "
                "on the exact ex-date within 0.5% of the previous close"
            ),
            "rule": (
                "a signal whose own continuous 200-session feature window contains an unattested price "
                "level step of 10% or more, in either direction, does not count as a usable entry "
                "signal: SMA(200) and RSI(2) at that T are computed across a step the committed "
                "corporate-action archive cannot attest, which is the assumption §6.3 forbids one step "
                "removed from the day the stop inspects"
            ),
            "consequence": (
                "such signals are counted below and excluded from the usable-feature-window set; they "
                "do not extend the STOP class, which remains the signal-day −20% level-step test"
            ),
        },
        "unattested_level_step_events_corpus_wide": level_step_events,
        "unattested_level_step_events_on_a_signal_day": level_step_events_on_a_signal_day,
        "instruments_with_an_unattested_level_step": instruments_with_a_level_step,
        "signals_with_an_unattested_level_step_in_lookback": signals_with_a_level_step_in_lookback,
        "entry_signals_in_a_usable_feature_window": entry_signals - signals_with_a_level_step_in_lookback,
        "signal_level_steps_in_lookback": signal_level_steps,
        "signal_level_steps_in_lookback_detail_distinct_instruments": len(
            {row["isin"] for row in signal_level_steps}
        ),
        "signal_level_steps_in_lookback_detail_scope": (
            f"the detail list is a prefix of at most {SIGNAL_LEVEL_STEP_DETAIL_LIMIT} signals in corpus "
            "insertion order, not a sample: the distinct-instrument count beside it is the list's reach "
            f"against the {instruments_with_a_level_step} instruments that carry such an event, so a "
            "classifier defect on an instrument outside the prefix leaves every published row clean "
            "(§101.5, §101.12 item 5)"
        ),
        "signal_level_steps_in_lookback_truncated": (
            signals_with_a_level_step_in_lookback > len(signal_level_steps)
        ),
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
                f"level between two sessions, not a session's trading — with no corporate action "
                f"(share ratio or cash amount) attested on that date; "
                f"{sum(1 for row in unattested_steps if row['ratio_shapes'])} of them are ratio-shaped"
            )
        ),
        "corporate_action_archive_coverage": {
            **coverage,
            "unattested_stop_rows_on_uncovered_instruments": sorted(
                {
                    row["isin"]
                    for row in unattested_steps
                    if bronze_records_by_isin.get(row["isin"], 0) == 0
                }
            ),
        },
        "rights_terp_branch": {
            **rights_branch_exercise(actions, bars_by_isin, sessions),
            "limitation": (
                "the RIGHTS branch of the cash test reprices to the theoretical ex-rights price from an "
                "issue ratio and premium parsed out of free-text prose, and no rights record in the "
                "committed table sits on a candidate level step, so the branch has never fired on this "
                "corpus and its first real use will attest a price level against an unattested record "
                "with a regex-extracted number — that first use is not evidence (§101.3, §101.12 item 6)"
            ),
        },
        "gated_by": {
            "consumers": consumers,
            "gates_execution": bool(consumers),
            "excluded_from_the_scan": [
                "scripts/run_seq12_candidate.py (this producer)",
                "scripts/probe_audit_findings.py (the audit probe)",
            ],
            "statement": (
                "no committed code outside this producer and the audit probe reads this artifact, so its"
                " STOP is a record of a refusal and not a gate: no execution path exists for it to "
                "refuse"
                if not consumers
                else f"{len(consumers)} committed reader(s) of this artifact: {consumers}"
            ),
        },
        "not_run": {
            "one_execution_seq12": (
                "NOT RUN — Step 2 did not clear" if unattested_steps else "NOT RUN — Step 3 is not wired"
            ),
            "exit_freeze_round_trip": (
                "NOT RUN — data/silver/price_bands holds 0 files, so no session carries a band and a "
                "lower-freeze exit delay cannot be measured; the exit side of a 2-to-21-session hold is "
                "unmeasured until that partition is populated (N-199)"
                if not bands_recorded
                else "NOT RUN — no position was simulated, so no round trip crossed a band"
            ),
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
            "the lookback count is per signal: a name is counted once per signal day whose own 200-session "
            "window holds an unattested step, so it is not a trade count; the 10% threshold, the ₹5 "
            "previous-close floor and the 200-session window are recorded in `feature_window_policy`, not "
            "pre-registered values",
        ],
    }
    qa["restates"] = restatement_of_previous(qa)
    # §102.10 / §102.14 item 5: this path was rewritten in place at 325bab8, so the revision it replaced
    # is named beside the artifact it is no longer.
    qa["predecessor"] = predecessor_pointer(OUTPUT.relative_to(REPO_ROOT).as_posix(), PREDECESSOR_COMMIT, qa)
    return qa


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
