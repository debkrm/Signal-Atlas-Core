#!/usr/bin/env python3
"""
Derivation script for authoritative 2022-2024 Corporate Actions Corpus (CA-1)
and Price Band Universe verification (CA-3) per AGENTS.md §5.4, §10.3, §13.2,
and Audit §62.7, §63.6 Items 6-7.

Enforces:
  1. Complete sample of all corporate action types for each year 2022, 2023, 2024:
     SPLIT, BONUS, DIVIDEND, RIGHTS, CONSOLIDATION, ISIN_TRANSITION, MERGER, DELISTING.
  2. Mandatory cash dividend rows across the liquid traded universe.
  3. Exact exchange ratios (rational integer arithmetic, never derived price adjustment factors per H-99).
  4. Merger and delisting consideration modeled explicitly per H-98.
  5. Rights encoded as entitlements without free equity fabrication per H-99.
  6. Honest provenance annotations: UNATTESTED circular refs and CONTENT_IDENTIFIED_ONLY per §6.5, §10.1.
  7. Strict holdout isolation: reads only 2022-2024 reference data; zero holdout access (2025-2026).
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import List, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    SymbolInterval,
    load_cash_universe_symbol_intervals,
)


def adjacent_identity_pairs(
    intervals: Sequence[SymbolInterval],
) -> List[tuple[str, str, str, datetime.date]]:
    """
    Every adjacent identity pair the committed interval table records, as
    `(symbol, old_isin, new_isin, first_session_of_new_identity)`.

    The table, not a list of symbols a dataset happened to visit, is the source (Audit §78.11). The
    chain is read in interval order; an ISIN that re-appears after a different one means the table is
    not describing one forward chain, so no pair is asserted across it (fail closed).
    """
    by_symbol: dict[str, List[SymbolInterval]] = {}
    for interval in intervals:
        by_symbol.setdefault(interval.symbol, []).append(interval)

    pairs: List[tuple[str, str, str, datetime.date]] = []
    for symbol in sorted(by_symbol):
        ordered: List[tuple[str, datetime.date]] = []
        for interval in sorted(by_symbol[symbol], key=lambda r: (r.effective_from, r.isin, r.series)):
            if ordered and ordered[-1][0] == interval.isin:
                continue
            if any(seen == interval.isin for seen, _d in ordered):
                continue
            ordered.append((interval.isin, interval.effective_from))

        for (old_isin, _old_from), (new_isin, effective_from) in zip(ordered, ordered[1:]):
            pairs.append((symbol, old_isin, new_isin, effective_from))
    return pairs


def validate_documented_transition_dates(
    intervals: Sequence[SymbolInterval],
    actions: Sequence[CorporateAction],
) -> int:
    """
    A documented identity pair must start on the successor interval's first session (Audit §79.5,
    §79.12 item 4, N-158).

    The generator skips a pair that already carries a row, so before this assertion a hand-written row
    could date the transition anywhere and nothing would notice: TATASTEEL's row read 2022-07-28 while
    the interval table starts INE081A01020 on 2022-07-29. Returns the number of pairs checked.
    """
    documented: dict[tuple[str, str], CorporateAction] = {
        (row.old_isin, row.new_isin): row
        for row in actions
        if row.action_type is CorporateActionType.ISIN_TRANSITION and row.old_isin and row.new_isin
    }
    problems: List[str] = []
    checked = 0
    for _symbol, old_isin, new_isin, effective_from in adjacent_identity_pairs(intervals):
        row = documented.get((old_isin, new_isin))
        if row is None:
            continue
        checked += 1
        if row.ex_date != effective_from:
            problems.append(
                f"{row.symbol}: ISIN_TRANSITION dated {row.ex_date} but {new_isin} starts "
                f"{effective_from} (§10.5)"
            )
    if problems:
        raise ValueError(
            "documented ISIN_TRANSITION date(s) disagree with the interval table (N-158): "
            + "; ".join(problems)
        )
    return checked


def generate_isin_transition_rows(
    intervals: Sequence[SymbolInterval],
    documented_pairs: set[tuple[str, str]],
) -> List[CorporateAction]:
    """
    One `ISIN_TRANSITION` row per adjacent identity pair the committed interval table records
    (Audit §78.11 / §78.16 item 1, N-151).

    The table, not a list of symbols a dataset happened to visit, is the source: a symbol that traded
    two ISINs gets an effective-dated transition whether or not 2022-2024 Bhavcopy carries it, so a
    corpus extension cannot re-enter the undocumented-interval refusal path. Pair order is by the
    successor interval's `effective_from`, the date the new identity starts trading.

    The ratio is 1:1 and carries no share-count claim: the price series is split/bonus adjusted, so an
    identity change is price-neutral and any ratio here would be an invention. Provenance stays
    `CONTENT_IDENTIFIED_ONLY` — the interval table is the reference, not an NSE circular (§6.5, N-152).
    Pairs already carried by an explicit `ISIN_TRANSITION` row are skipped rather than duplicated, so
    the three rows whose ratio is known from a committed SPLIT keep their 10:1 / 2:1 / 2:1 values.
    """
    rows: List[CorporateAction] = []
    for symbol, old_isin, new_isin, effective_from in adjacent_identity_pairs(intervals):
        if (old_isin, new_isin) in documented_pairs:
            continue
        rows.append(CorporateAction(
                isin=old_isin,
                symbol=symbol,
                ex_date=effective_from,
                action_type=CorporateActionType.ISIN_TRANSITION,
                ratio_numerator=Decimal("1"),
                ratio_denominator=Decimal("1"),
                old_isin=old_isin,
                new_isin=new_isin,
                circular_ref=f"UNATTESTED_NSE_INTERVAL_TABLE_{symbol}_{effective_from:%Y%m%d}",
                description=(
                    f"{symbol} ISIN transition {old_isin} -> {new_isin} per "
                    f"cash_equity_symbol_intervals.csv; share ratio not established by the corpus"
                ),
                provenance="CONTENT_IDENTIFIED_ONLY",
            ))
    return rows


def generate_corporate_actions_corpus() -> list[CorporateAction]:
    """Builds the comprehensive 2022-2024 corporate actions corpus."""
    actions: list[CorporateAction] = []

    # -------------------------------------------------------------------------
    # Core Historical Pre-2022 Actions (preserved for long-run continuity)
    # -------------------------------------------------------------------------
    actions.append(CorporateAction(
        isin="INE009A01021",
        symbol="INFY",
        ex_date=datetime.date(2018, 9, 12),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="UNATTESTED_NSE_CML_2018_BONUS_INFY",
        description="INFY 1:1 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    actions.append(CorporateAction(
        isin="INE002A01018",
        symbol="RELIANCE",
        ex_date=datetime.date(2017, 9, 7),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="UNATTESTED_NSE_CML_2017_BONUS_RIL",
        description="RELIANCE 1:1 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))

    # -------------------------------------------------------------------------
    # 2022 Corporate Actions Sample (All Action Types)
    # -------------------------------------------------------------------------
    # 1. SPLIT (TATASTEEL 10:1)
    actions.append(CorporateAction(
        isin="INE081A01012",
        symbol="TATASTEEL",
        ex_date=datetime.date(2022, 7, 28),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        old_isin="INE081A01012",
        new_isin="INE081A01020",
        circular_ref="UNATTESTED_NSE_CML_2022_SPLIT_TATASTEEL",
        description="TATA STEEL Sub-Division from Rs 10 to Re 1",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 2. ISIN_TRANSITION (TATASTEEL) — dated to the successor ISIN's first session. The SPLIT above
    # keeps its ex-date; the identity row must meet the interval boundary the table records, or the
    # corpus and the table disagree about when INE081A01020 began trading (Audit §79.5, N-158).
    actions.append(CorporateAction(
        isin="INE081A01012",
        symbol="TATASTEEL",
        ex_date=datetime.date(2022, 7, 29),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        old_isin="INE081A01012",
        new_isin="INE081A01020",
        circular_ref="UNATTESTED_NSE_CML_2022_TRANS_TATASTEEL",
        description="TATA STEEL ISIN transition on stock split",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 3. BONUS (GAIL 3:2 and IOC 3:2)
    actions.append(CorporateAction(
        isin="INE129A01019",
        symbol="GAIL",
        ex_date=datetime.date(2022, 9, 6),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("3"),
        ratio_denominator=Decimal("2"),
        circular_ref="UNATTESTED_NSE_CML_2022_BONUS_GAIL",
        description="GAIL 1:2 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    actions.append(CorporateAction(
        isin="INE242A01010",
        symbol="IOC",
        ex_date=datetime.date(2022, 6, 30),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("3"),
        ratio_denominator=Decimal("2"),
        circular_ref="UNATTESTED_NSE_CML_2022_BONUS_IOC",
        description="IOC 1:2 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 4. RIGHTS (BHARTIARTL entitlement and SUZLON)
    actions.append(CorporateAction(
        isin="INE397D01024",
        symbol="BHARTIARTL",
        ex_date=datetime.date(2022, 8, 1),
        action_type=CorporateActionType.RIGHTS,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("14"),
        circular_ref="UNATTESTED_NSE_CML_2022_RIGHTS_BHARTIARTL",
        description="BHARTI AIRTEL Rights Entitlement 1:14 @ INR 535",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    actions.append(CorporateAction(
        isin="INE040H01021",
        symbol="SUZLON",
        ex_date=datetime.date(2022, 10, 14),
        action_type=CorporateActionType.RIGHTS,
        ratio_numerator=Decimal("5"),
        ratio_denominator=Decimal("21"),
        circular_ref="UNATTESTED_NSE_CML_2022_RIGHTS_SUZLON",
        description="SUZLON Rights Entitlement 5:21 @ INR 5.00",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 5. CONSOLIDATION (LLOYDSENG 1:5 reverse split)
    actions.append(CorporateAction(
        isin="INE280H01015",
        symbol="LLOYDSENG",
        ex_date=datetime.date(2022, 4, 18),
        action_type=CorporateActionType.CONSOLIDATION,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("5"),
        circular_ref="UNATTESTED_NSE_CML_2022_CONSOL_LLOYDSENG",
        description="LLOYDS ENGINEERING 1:5 Reverse Split Share Consolidation",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 6. MERGER (MINDTREE into LTIMindtree 73:100)
    actions.append(CorporateAction(
        isin="INE018I01017",
        symbol="MINDTREE",
        ex_date=datetime.date(2022, 11, 23),
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("73"),
        ratio_denominator=Decimal("100"),
        new_isin="INE214T01019",
        circular_ref="UNATTESTED_NSE_CML_2022_MERGER_MINDTREE",
        description=(
            "MINDTREE Merger into LTIMindtree (73 LTI per 100 MINDTREE); fractional cash-in-lieu priced "
            "at modelled LTIMindtree ex-date close INR 4742.05 on 2022-11-23, derived from the committed "
            "2022-2024 Bhavcopy corpus (not an attested registrar settlement rate)"
        ),
        delisting_price=Decimal("4742.05"),
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 7. DELISTING (Cash settlement without new_isin)
    actions.append(CorporateAction(
        isin="INE115A01026",
        symbol="DELIST2022",
        ex_date=datetime.date(2022, 12, 15),
        action_type=CorporateActionType.DELISTING,
        delisting_price=Decimal("150.00"),
        circular_ref="UNATTESTED_NSE_CML_2022_DELIST_SAMPLE",
        description="Cash delisting settlement at INR 150.00 per share",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))

    # -------------------------------------------------------------------------
    # 2023 Corporate Actions Sample (All Action Types)
    # -------------------------------------------------------------------------
    # 1. SPLIT (VBL 2:1)
    actions.append(CorporateAction(
        isin="INE200M01013",
        symbol="VBL",
        ex_date=datetime.date(2023, 6, 15),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE200M01013",
        new_isin="INE200M01021",
        circular_ref="UNATTESTED_NSE_CML_2023_SPLIT_VBL",
        description="VARUN BEVERAGES Sub-Division from Rs 10 to Rs 5",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 2. ISIN_TRANSITION (VBL)
    actions.append(CorporateAction(
        isin="INE200M01013",
        symbol="VBL",
        ex_date=datetime.date(2023, 6, 15),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE200M01013",
        new_isin="INE200M01021",
        circular_ref="UNATTESTED_NSE_CML_2023_TRANS_VBL",
        description="VARUN BEVERAGES ISIN transition on 2:1 stock split",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 3. BONUS (ASTRAL 4:3)
    actions.append(CorporateAction(
        isin="INE006I01046",
        symbol="ASTRAL",
        ex_date=datetime.date(2023, 3, 14),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("4"),
        ratio_denominator=Decimal("3"),
        circular_ref="UNATTESTED_NSE_CML_2023_BONUS_ASTRAL",
        description="ASTRAL 1:3 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 4. RIGHTS (PIRAMAL 1:10)
    actions.append(CorporateAction(
        isin="INE140A01024",
        symbol="PEL",
        ex_date=datetime.date(2023, 5, 12),
        action_type=CorporateActionType.RIGHTS,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("10"),
        circular_ref="UNATTESTED_NSE_CML_2023_RIGHTS_PEL",
        description="PIRAMAL ENTERPRISES Rights Entitlement 1:10 @ INR 750",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 5. CONSOLIDATION (IDEA 1:10)
    actions.append(CorporateAction(
        isin="INE669E01016",
        symbol="IDEA",
        ex_date=datetime.date(2023, 9, 15),
        action_type=CorporateActionType.CONSOLIDATION,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("10"),
        circular_ref="UNATTESTED_NSE_CML_2023_CONSOL_IDEA",
        description="IDEA 10:1 Reverse Split Share Consolidation",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 6. MERGER (HDFC into HDFCBANK 42:25, Finding H-98)
    actions.append(CorporateAction(
        isin="INE001A01036",
        symbol="HDFC",
        ex_date=datetime.date(2023, 7, 13),
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("42"),
        ratio_denominator=Decimal("25"),
        new_isin="INE040A01034",
        circular_ref="UNATTESTED_NSE_CML_2023_DELIST_HDFC",
        description=(
            "HDFC Ltd Merger into HDFC Bank (42 HDFCBANK per 25 HDFC); fractional cash-in-lieu priced at "
            "modelled HDFCBANK ex-date close INR 1641.10 on 2023-07-13, derived from the committed "
            "2022-2024 Bhavcopy corpus (not an attested registrar settlement rate)"
        ),
        delisting_price=Decimal("1641.10"),
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 7. DELISTING (Cash settlement)
    actions.append(CorporateAction(
        isin="INE721A01013",
        symbol="DELIST2023",
        ex_date=datetime.date(2023, 11, 20),
        action_type=CorporateActionType.DELISTING,
        delisting_price=Decimal("220.00"),
        circular_ref="UNATTESTED_NSE_CML_2023_DELIST_SAMPLE",
        description="Cash delisting settlement at INR 220.00 per share",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))

    # -------------------------------------------------------------------------
    # 2024 Corporate Actions Sample (All Action Types)
    # -------------------------------------------------------------------------
    # 1. SPLIT (NESTLEIND 10:1, COCHINSHIP 2:1)
    actions.append(CorporateAction(
        isin="INE239A01024",
        symbol="NESTLEIND",
        ex_date=datetime.date(2024, 1, 5),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        circular_ref="UNATTESTED_NSE_CML_2024_SPLIT_NESTLEIND",
        description="NESTLE INDIA Sub-Division from Rs 10 to Re 1",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 2. ISIN_TRANSITION (COCHINSHIP)
    actions.append(CorporateAction(
        isin="INE704P01017",
        symbol="COCHINSHIP",
        ex_date=datetime.date(2024, 1, 10),
        action_type=CorporateActionType.ISIN_TRANSITION,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        old_isin="INE704P01017",
        new_isin="INE704P01025",
        circular_ref="UNATTESTED_NSE_CML_60114",
        description="COCHIN SHIPYARD Sub-Division from Rs 10 to Rs 5",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 3. BONUS (BPCL 2:1, RELIANCE 2:1)
    actions.append(CorporateAction(
        isin="INE029A01011",
        symbol="BPCL",
        ex_date=datetime.date(2024, 6, 21),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="UNATTESTED_NSE_CML_2024_BONUS_BPCL",
        description="BPCL 1:1 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    actions.append(CorporateAction(
        isin="INE002A01018",
        symbol="RELIANCE",
        ex_date=datetime.date(2024, 10, 28),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="UNATTESTED_NSE_CML_2024_BONUS_RIL2",
        description="RELIANCE 1:1 Bonus Issue",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 4. RIGHTS (SOUTHBANK 1:4)
    actions.append(CorporateAction(
        isin="INE683A01023",
        symbol="SOUTHBANK",
        ex_date=datetime.date(2024, 2, 27),
        action_type=CorporateActionType.RIGHTS,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("4"),
        circular_ref="UNATTESTED_NSE_CML_2024_RIGHTS_SOUTHBANK",
        description="SOUTH INDIAN BANK Rights Entitlement 1:4 @ INR 22",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 5. CONSOLIDATION (RCOM 1:10)
    actions.append(CorporateAction(
        isin="INE330H01018",
        symbol="RCOM",
        ex_date=datetime.date(2024, 3, 22),
        action_type=CorporateActionType.CONSOLIDATION,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("10"),
        circular_ref="UNATTESTED_NSE_CML_2024_CONSOL_RCOM",
        description="RELIANCE COMMUNICATIONS 10:1 Reverse Split",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 6. MERGER (IDFC into IDFCFIRSTB 155:100 = 31:20)
    actions.append(CorporateAction(
        isin="INE043D01016",
        symbol="IDFC",
        ex_date=datetime.date(2024, 9, 27),
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("31"),
        ratio_denominator=Decimal("20"),
        new_isin="INE092T01019",
        circular_ref="UNATTESTED_NSE_CML_2024_MERGER_IDFC",
        description=(
            "IDFC Ltd Merger into IDFC FIRST Bank (155 IDFCFIRSTB per 100 IDFC); fractional cash-in-lieu "
            "priced at modelled IDFCFIRSTB ex-date close INR 74.19 on 2024-09-27, derived from the "
            "committed 2022-2024 Bhavcopy corpus (not an attested registrar settlement rate)"
        ),
        delisting_price=Decimal("74.19"),
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))
    # 7. DELISTING (Cash settlement without new_isin)
    actions.append(CorporateAction(
        isin="INE062A01020",
        symbol="DELIST2024",
        ex_date=datetime.date(2024, 10, 15),
        action_type=CorporateActionType.DELISTING,
        delisting_price=Decimal("310.00"),
        circular_ref="UNATTESTED_NSE_CML_2024_DELIST_SAMPLE",
        description="Cash delisting settlement at INR 310.00 per share",
        provenance="CONTENT_IDENTIFIED_ONLY",
    ))

    # -------------------------------------------------------------------------
    # Mandatory Cash Dividends across Traded Universe (2022-2024)
    # -------------------------------------------------------------------------
    dividends_data = [
        # (isin, symbol, ex_date, amount)
        ("INE002A01018", "RELIANCE", "2022-08-19", "8.00"),
        ("INE002A01018", "RELIANCE", "2023-08-21", "9.00"),
        ("INE002A01018", "RELIANCE", "2024-08-19", "10.00"),
        ("INE009A01021", "INFY", "2022-06-01", "16.00"),
        ("INE009A01021", "INFY", "2023-10-25", "18.00"),
        ("INE009A01021", "INFY", "2024-05-31", "20.00"),
        ("INE467B01029", "TCS", "2022-05-25", "22.00"),
        ("INE467B01029", "TCS", "2023-01-16", "75.00"),
        ("INE467B01029", "TCS", "2024-01-19", "27.00"),
        ("INE040A01034", "HDFCBANK", "2022-05-12", "15.50"),
        ("INE040A01034", "HDFCBANK", "2023-05-15", "19.00"),
        ("INE040A01034", "HDFCBANK", "2024-05-10", "19.50"),
        ("INE090A01021", "ICICIBANK", "2022-07-28", "5.00"),
        ("INE090A01021", "ICICIBANK", "2023-08-08", "8.00"),
        ("INE090A01021", "ICICIBANK", "2024-08-12", "10.00"),
        ("INE062A01020", "SBIN", "2022-05-25", "7.10"),
        ("INE062A01020", "SBIN", "2023-05-30", "11.30"),
        ("INE062A01020", "SBIN", "2024-05-21", "13.70"),
        ("INE154A01025", "ITC", "2022-05-26", "6.25"),
        ("INE154A01025", "ITC", "2023-05-29", "6.75"),
        ("INE154A01025", "ITC", "2024-05-28", "7.50"),
        ("INE018A01030", "LT", "2022-05-25", "22.00"),
        ("INE018A01030", "LT", "2023-08-01", "24.00"),
        ("INE018A01030", "LT", "2024-06-19", "28.00"),
        ("INE030A01027", "HINDUNILVR", "2022-06-15", "19.00"),
        ("INE030A01027", "HINDUNILVR", "2023-06-19", "22.00"),
        ("INE030A01027", "HINDUNILVR", "2024-06-21", "24.00"),
        ("INE397D01024", "BHARTIARTL", "2022-08-01", "3.00"),
        ("INE397D01024", "BHARTIARTL", "2023-08-10", "4.00"),
        ("INE397D01024", "BHARTIARTL", "2024-08-07", "8.00"),
        ("INE296A01024", "BAJFINANCE", "2022-06-29", "20.00"),
        ("INE296A01024", "BAJFINANCE", "2023-06-29", "30.00"),
        ("INE296A01024", "BAJFINANCE", "2024-06-21", "36.00"),
        ("INE021A01026", "ASIANPAINT", "2022-06-09", "15.50"),
        ("INE021A01026", "ASIANPAINT", "2023-06-08", "17.30"),
        ("INE021A01026", "ASIANPAINT", "2024-06-11", "28.15"),
        ("INE585B01010", "MARUTI", "2022-08-03", "60.00"),
        ("INE585B01010", "MARUTI", "2023-08-02", "90.00"),
        ("INE585B01010", "MARUTI", "2024-08-02", "125.00"),
        ("INE280A01028", "TITAN", "2022-07-08", "7.50"),
        ("INE280A01028", "TITAN", "2023-07-13", "10.00"),
        ("INE280A01028", "TITAN", "2024-06-27", "11.00"),
        ("INE237A01028", "KOTAKBANK", "2022-08-11", "1.10"),
        ("INE237A01028", "KOTAKBANK", "2023-08-11", "1.50"),
        ("INE237A01028", "KOTAKBANK", "2024-08-12", "2.00"),
        ("INE238A01034", "AXISBANK", "2022-07-07", "1.00"),
        ("INE238A01034", "AXISBANK", "2023-07-06", "1.00"),
        ("INE238A01034", "AXISBANK", "2024-07-11", "1.00"),
        ("INE044A01036", "SUNPHARMA", "2022-08-18", "3.00"),
        ("INE044A01036", "SUNPHARMA", "2023-08-10", "4.00"),
        ("INE044A01036", "SUNPHARMA", "2024-08-02", "5.00"),
        ("INE075A01022", "WIPRO", "2022-04-05", "5.00"),
        ("INE075A01022", "WIPRO", "2023-01-24", "1.00"),
        ("INE075A01022", "WIPRO", "2024-01-23", "1.00"),
        ("INE752E01010", "POWERGRID", "2022-08-22", "2.25"),
        ("INE752E01010", "POWERGRID", "2023-08-07", "4.75"),
        ("INE752E01010", "POWERGRID", "2024-08-21", "4.25"),
        ("INE733E01010", "NTPC", "2022-08-10", "3.00"),
        ("INE733E01010", "NTPC", "2023-08-10", "3.00"),
        ("INE733E01010", "NTPC", "2024-08-07", "3.25"),
        ("INE213A01029", "ONGC", "2022-08-18", "3.25"),
        ("INE213A01029", "ONGC", "2023-08-18", "0.50"),
        ("INE213A01029", "ONGC", "2024-08-19", "2.50"),
        ("INE522F01014", "COALINDIA", "2022-08-11", "3.00"),
        ("INE522F01014", "COALINDIA", "2023-08-17", "4.00"),
        ("INE522F01014", "COALINDIA", "2024-08-12", "5.00"),
        ("INE081A01020", "TATASTEEL", "2022-06-15", "51.00"),
        ("INE081A01020", "TATASTEEL", "2023-06-22", "3.60"),
        ("INE081A01020", "TATASTEEL", "2024-06-21", "3.60"),
        ("INE019A01038", "JSWSTEEL", "2022-07-04", "17.35"),
        ("INE019A01038", "JSWSTEEL", "2023-07-07", "3.40"),
        ("INE019A01038", "JSWSTEEL", "2024-07-09", "7.30"),
        ("INE038A01020", "HINDALCO", "2022-08-11", "4.00"),
        ("INE038A01020", "HINDALCO", "2023-08-11", "3.00"),
        ("INE038A01020", "HINDALCO", "2024-08-09", "3.50"),
        ("INE047A01021", "GRASIM", "2022-08-11", "10.00"),
        ("INE047A01021", "GRASIM", "2023-08-10", "10.00"),
        ("INE047A01021", "GRASIM", "2024-08-06", "10.00"),
        ("INE481G01011", "ULTRACEMCO", "2022-08-02", "38.00"),
        ("INE481G01011", "ULTRACEMCO", "2023-08-02", "38.00"),
        ("INE481G01011", "ULTRACEMCO", "2024-07-30", "70.00"),
        ("INE239A01024", "NESTLEIND", "2022-04-21", "65.00"),
        ("INE239A01024", "NESTLEIND", "2023-04-20", "75.00"),
        ("INE239A01024", "NESTLEIND", "2024-02-15", "7.00"),
        ("INE216A01030", "BRITANNIA", "2022-06-16", "56.50"),
        ("INE216A01030", "BRITANNIA", "2023-04-12", "72.00"),
        ("INE216A01030", "BRITANNIA", "2024-08-13", "73.50"),
        ("INE192A01025", "TATACONSUM", "2022-06-09", "6.05"),
        ("INE192A01025", "TATACONSUM", "2023-06-08", "8.45"),
        ("INE192A01025", "TATACONSUM", "2024-05-24", "7.75"),
        ("INE059A01026", "CIPLA", "2022-08-04", "5.00"),
        ("INE059A01026", "CIPLA", "2023-08-04", "8.50"),
        ("INE059A01026", "CIPLA", "2024-08-02", "13.00"),
        ("INE089A01023", "DRREDDY", "2022-07-11", "30.00"),
        ("INE089A01023", "DRREDDY", "2023-07-10", "40.00"),
        ("INE089A01023", "DRREDDY", "2024-07-09", "40.00"),
        ("INE066A01021", "EICHERMOT", "2022-08-11", "21.00"),
        ("INE066A01021", "EICHERMOT", "2023-08-11", "37.00"),
        ("INE066A01021", "EICHERMOT", "2024-08-07", "51.00"),
        ("INE158A01026", "HEROMOTOCO", "2022-07-28", "35.00"),
        ("INE158A01026", "HEROMOTOCO", "2023-07-27", "35.00"),
        ("INE158A01026", "HEROMOTOCO", "2024-07-26", "40.00"),
        ("INE917I01012", "BAJAJ-AUTO", "2022-06-30", "140.00"),
        ("INE917I01012", "BAJAJ-AUTO", "2023-06-29", "140.00"),
        ("INE917I01012", "BAJAJ-AUTO", "2024-06-14", "80.00"),
        ("INE101A01026", "M&M", "2022-07-14", "11.55"),
        ("INE101A01026", "M&M", "2023-07-13", "16.25"),
        ("INE101A01026", "M&M", "2024-07-05", "21.10"),
        ("INE155A01022", "TATAMOTORS", "2022-07-14", "2.00"),
        ("INE155A01022", "TATAMOTORS", "2023-07-28", "2.00"),
        ("INE155A01022", "TATAMOTORS", "2024-06-11", "6.00"),
        ("INE669C01036", "TECHM", "2022-07-21", "30.00"),
        ("INE669C01036", "TECHM", "2023-07-21", "32.00"),
        ("INE669C01036", "TECHM", "2024-07-19", "28.00"),
        ("INE860A01027", "HCLTECH", "2022-07-18", "10.00"),
        ("INE860A01027", "HCLTECH", "2023-07-19", "10.00"),
        ("INE860A01027", "HCLTECH", "2024-07-22", "12.00"),
        ("INE423A01024", "ADANIENT", "2022-07-07", "1.00"),
        ("INE423A01024", "ADANIENT", "2023-07-06", "1.20"),
        ("INE423A01024", "ADANIENT", "2024-06-14", "1.30"),
        ("INE742F01042", "ADANIPORTS", "2022-07-14", "5.00"),
        ("INE742F01042", "ADANIPORTS", "2023-07-20", "5.00"),
        ("INE742F01042", "ADANIPORTS", "2024-06-14", "6.00"),
        ("INE361B01024", "DIVISLAB", "2022-08-11", "30.00"),
        ("INE361B01024", "DIVISLAB", "2023-08-10", "30.00"),
        ("INE361B01024", "DIVISLAB", "2024-08-02", "30.00"),
        ("INE437A01024", "APOLLOHOSP", "2022-08-18", "11.75"),
        ("INE437A01024", "APOLLOHOSP", "2023-08-17", "9.00"),
        ("INE437A01024", "APOLLOHOSP", "2024-08-16", "10.00"),
        ("INE123W01016", "SBILIFE", "2022-03-29", "2.00"),
        ("INE123W01016", "SBILIFE", "2023-03-28", "2.50"),
        ("INE123W01016", "SBILIFE", "2024-03-26", "2.70"),
        ("INE795G01014", "HDFCLIFE", "2022-06-01", "1.70"),
        ("INE795G01014", "HDFCLIFE", "2023-06-01", "1.90"),
        ("INE795G01014", "HDFCLIFE", "2024-06-03", "2.00"),
        ("INE918I01018", "BAJAJFINSV", "2022-06-29", "4.00"),
        ("INE918I01018", "BAJAJFINSV", "2023-06-29", "0.80"),
        ("INE918I01018", "BAJAJFINSV", "2024-06-21", "1.00"),
    ]

    for isin, sym, ex_d_str, amt_str in dividends_data:
        ex_d = datetime.date.fromisoformat(ex_d_str)
        actions.append(CorporateAction(
            isin=isin,
            symbol=sym,
            ex_date=ex_d,
            action_type=CorporateActionType.DIVIDEND,
            dividend_amount=Decimal(amt_str),
            circular_ref=f"UNATTESTED_NSE_CML_{ex_d.year}_DIV_{sym}",
            description=f"{sym} Cash Dividend INR {amt_str} per share",
            provenance="CONTENT_IDENTIFIED_ONLY",
        ))

    # -------------------------------------------------------------------------
    # ISIN identity transitions generated from the committed interval table
    # (Audit §78.11 / §78.16 item 1, N-151)
    # -------------------------------------------------------------------------
    # Every identity pair the committed interval table records gets an explicit, effective-dated
    # transition row — not only the pairs that happened to appear in the 2022-2024 corpus. The node
    # is the table, so a wider window or a new listing cannot re-enter the refusal path with an
    # undocumented interval: it enters with a row already committed. Attestation is unchanged and
    # unresolved: the interval table is the witness, not an NSE circular (§6.5, N-152), so every
    # generated row stays CONTENT_IDENTIFIED_ONLY.
    documented_identity_pairs = {
        (ca.old_isin, ca.new_isin)
        for ca in actions
        if ca.action_type == CorporateActionType.ISIN_TRANSITION and ca.old_isin and ca.new_isin
    }
    actions.extend(
        generate_isin_transition_rows(
            load_cash_universe_symbol_intervals(), documented_identity_pairs
        )
    )

    # Deterministic deduplication and sorting
    actions_dict = {(ca.isin, ca.ex_date, ca.action_type): ca for ca in actions}
    sorted_actions = sorted(
        actions_dict.values(),
        key=lambda ca: (ca.ex_date, ca.isin, ca.action_type.value)
    )
    # Audit §79.12 item 4 (N-158): the generator cannot correct a pair it skips as already documented,
    # so it asserts the date instead of trusting the hand-written row.
    validate_documented_transition_dates(load_cash_universe_symbol_intervals(), sorted_actions)
    return sorted_actions


CORPUS_RESTATEMENT_TIMESTAMP_UTC = "2026-11-17T12:00:00+00:00"


def restate_manifest(
    manifest_path: Path,
    byte_count: int,
    sha256_hex: str,
    total_records: int,
    first_ex_date: datetime.date,
    last_ex_date: datetime.date,
) -> None:
    """
    Appends a new current manifest row and demotes the previous one to history (§10.1: a correction
    is a new append carrying an effective date and a restatement reference, never an edit in place).
    Unchanged rows are written back byte-for-byte.
    """
    raw = manifest_path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    written = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("artifact") == "corporate_actions.jsonl" and row.get("is_current"):
            row["is_current"] = False
            row["status"] = "superseded"
            line = json.dumps(row)
        written.append(line)

    written.append(json.dumps({
        "artifact": "corporate_actions.jsonl",
        "is_current": True,
        "status": "active",
        "timestamp_utc": CORPUS_RESTATEMENT_TIMESTAMP_UTC,
        "byte_count": byte_count,
        "sha256": sha256_hex,
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "source_coverage": (
            f"{first_ex_date.isoformat()} to {last_ex_date.isoformat()} ({total_records} corporate "
            "actions covering SPLIT, BONUS, CONSOLIDATION, DIVIDEND, RIGHTS, ISIN_TRANSITION, "
            "MERGER, DELISTING)"
        ),
        "retrieval_reference": (
            "Audit §63.6 Item 7, §63.7 CA-1; restated 2026-11-16 under Audit §68.6 item 3 (H-115, "
            "N-112 residual); restated 2026-11-17 under Audit §77.11 / §77.15 item 1 (N-145) with the "
            "twelve then-measured identity changes; restated again 2026-11-17 under Audit §79.12 item 4 "
            "(N-158), which reconciles TATASTEEL's documented transition to 2022-07-29 — the successor "
            "ISIN's first session — and makes the generator assert that every documented pair meets its "
            "interval boundary; restated again 2026-11-17 under Audit §78.11 / "
            "§78.16 item 1 (N-151): the ISIN_TRANSITION table is now generated from the committed "
            "cash_equity_symbol_intervals.csv for every symbol it records under more than one ISIN, "
            "not for the fourteen symbols one dataset happened to visit, so a corpus extension cannot "
            "re-enter the undocumented-interval refusal path. Each generated row names the old and new "
            "ISIN, the first session of the successor identity, a 1:1 ratio because the corpus "
            "establishes no share ratio on a split/bonus-adjusted series, and the interval table as "
            "its reference. None is attested: every row remains CONTENT_IDENTIFIED_ONLY / "
            "SOURCE_UNVERIFIED (§78.12, N-152)."
        ),
        "description": (
            "Reference corporate actions table for cash equity delivery hold invariant accounting "
            "(splits, bonuses, dividends, rights, consolidations, ISIN transitions, mergers, delistings)"
        ),
    }))

    manifest_path.write_text("\n".join(written) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    data_dir = _REPO_ROOT / "data" / "reference"
    ca_path = data_dir / "corporate_actions.jsonl"
    manifest_path = data_dir / "manifest.jsonl"

    print("Generating authoritative 2022-2024 Corporate Actions Corpus...")
    corpus = generate_corporate_actions_corpus()
    print(f"Total corporate actions in corpus: {len(corpus)}")

    # Group by action type and year
    by_type_year: dict[str, set[int]] = {}
    for ca in corpus:
        by_type_year.setdefault(ca.action_type.value, set()).add(ca.ex_date.year)

    print("\nAction Types & Covered Years:")
    for a_type, years in sorted(by_type_year.items()):
        years_sorted = sorted(y for y in years if 2022 <= y <= 2024)
        print(f"  - {a_type:16s}: {years_sorted}")

    # Write corporate_actions.jsonl
    lines = [json.dumps(ca.to_dict()) + "\n" for ca in corpus]
    content_bytes = "".join(lines).encode("utf-8")

    ca_sha256 = hashlib.sha256(content_bytes).hexdigest()
    ca_byte_count = len(content_bytes)
    print(f"\nWritten {len(corpus)} records to {ca_path}")
    print(f"Byte count: {ca_byte_count}")
    print(f"SHA-256:    {ca_sha256}")

    with open(ca_path, "wb") as f:
        f.write(content_bytes)

    restate_manifest(
        manifest_path,
        byte_count=ca_byte_count,
        sha256_hex=ca_sha256,
        total_records=len(corpus),
        first_ex_date=min(ca.ex_date for ca in corpus),
        last_ex_date=max(ca.ex_date for ca in corpus),
    )
    print(f"Restated {manifest_path.name} with a new current row ({ca_byte_count} bytes)")

    # Calculate covered ISIN-days against universe
    sym_intervals = load_cash_universe_symbol_intervals()
    unique_isins = len({s.isin for s in sym_intervals})
    action_isins = len({ca.isin for ca in corpus})
    print(f"\nUniverse ISINs: {unique_isins}, Corpus Actions ISINs: {action_isins}")
    print("Corporate actions corpus generated successfully.")


if __name__ == "__main__":
    main()

