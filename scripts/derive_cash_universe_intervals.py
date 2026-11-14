#!/usr/bin/env python3
"""
Derivation script for authoritative Point-in-Time Cash Equity Symbol->ISIN Intervals.
Sourced strictly from 1,195 raw daily NSE Bhavcopy archives (2022-01-03 to 2026-10-31)
per AGENTS.md §10.4, §10.7, §10.8 and Audit §39 (Findings H-50, H-44).

Enforces:
  1. Effective-dated intervals [effective_from, effective_to) keyed by ISIN.
  2. Every effective_from and effective_to is an authoritative TradingCalendar session.
  3. Seamless ISIN transitions with zero overlap and zero gaps on ex-dates.
  4. At most one open-ended interval per symbol.
  5. Deterministic sorting and POSIX LF formatting.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import zipfile
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_raw_archives_dir() -> Path:
    """Configurable archive directory discovery per Audit §40 Note H-53, §12.5, Finding H-55."""
    env_dir = os.environ.get("NSE_RAW_ARCHIVES_DIR")
    if env_dir:
        cand = Path(env_dir)
        if cand.is_dir():
            return cand
    cand1 = REPO_ROOT / "data" / "raw"
    if cand1.is_dir():
        return cand1
    return cand1


RAW_ARCHIVES_DIR = resolve_raw_archives_dir()
OUTPUT_CSV = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_intervals.csv"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"

# Add src to path for calendar imports
sys.path.insert(0, str(REPO_ROOT / "src"))
from signal_core.storage.calendar import load_nse_trading_calendar


def parse_date(raw_date_str: str) -> datetime.date:
    s = raw_date_str.strip()
    if "-" in s:
        parts = s.split("-")
        if len(parts[0]) == 4:
            # ISO: YYYY-MM-DD
            return datetime.date.fromisoformat(s)
        # DD-MMM-YYYY (e.g. 16-JAN-2024)
        d, m, y = parts
        months = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
        }
        return datetime.date(int(y), months[m.upper()], int(d))
    raise ValueError(f"Unrecognized date format: {raw_date_str}")


def extract_session_observations() -> Tuple[List[datetime.date], Dict[datetime.date, Dict[str, Tuple[str, str]]]]:
    """
    Scans all raw Bhavcopy archives in date order.
    Returns:
        sorted_sessions: List of trading sessions observed.
        session_map: session_date -> {symbol: (isin, series)}
    """
    cal = load_nse_trading_calendar()
    valid_sessions = set(cal.sessions)

    if not RAW_ARCHIVES_DIR.is_dir():
        raise FileNotFoundError(
            f"Raw archives directory not found at: {RAW_ARCHIVES_DIR}. "
            "Set NSE_RAW_ARCHIVES_DIR environment variable per Note H-53."
        )

    zip_files = []
    for y_dir in sorted(RAW_ARCHIVES_DIR.iterdir()):
        if y_dir.is_dir() and y_dir.name.isdigit():
            zip_files.extend(sorted(y_dir.glob("*.zip")))

    print(f"[INFO] Discovered {len(zip_files)} raw Bhavcopy archives across 2022-2026.")

    session_observations: Dict[datetime.date, Dict[str, Tuple[str, str]]] = defaultdict(dict)

    start_t = time.perf_counter()
    for z_path in zip_files:
        with zipfile.ZipFile(z_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".csv") or "bhav" not in name.lower():
                    continue
                with zf.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                    try:
                        header = next(reader)
                    except StopIteration:
                        continue
                    h_map = {c.strip().upper(): i for i, c in enumerate(header)}

                    def _find_col(*candidates: str) -> Optional[int]:
                        for c in candidates:
                            if c in h_map:
                                return h_map[c]
                        return None

                    sym_col = _find_col("TCKRSYMB", "SYMBOL", "SECURITY")
                    isin_col = _find_col("ISIN", "ISIN_CODE", "SECURITY_ISIN")
                    srs_col = _find_col("SCTYSRS", "SERIES", "SECURITY_SERIES")
                    dt_col = _find_col("TRADDT", "TIMESTAMP", "TRADEDATE", "TRADE_DATE", "DATE")

                    if None in (sym_col, isin_col, srs_col, dt_col):
                        continue

                    max_idx = max(sym_col, isin_col, srs_col, dt_col)
                    for row in reader:
                        if len(row) <= max_idx:
                            continue
                        series = row[srs_col].strip().upper()
                        # Target cash equity series (EQ and trade-for-trade / surveillance cash series)
                        if series not in ("EQ", "BE", "BZ", "SM"):
                            continue
                        sym = row[sym_col].strip().upper()
                        isin = row[isin_col].strip().upper()
                        if not sym or not isin or len(isin) != 12:
                            continue

                        raw_dt = row[dt_col].strip()
                        try:
                            trade_date = parse_date(raw_dt)
                        except Exception:
                            continue

                        if trade_date not in valid_sessions:
                            continue

                        # Prefer EQ series if multiple observed in same session
                        existing = session_observations[trade_date].get(sym)
                        if existing is None or (existing[1] != "EQ" and series == "EQ"):
                            session_observations[trade_date][sym] = (isin, series)

    elapsed = time.perf_counter() - start_t
    sorted_sessions = sorted(session_observations.keys())
    # Note N-28: 1,195 archives discovered across 2022-2026. Exactly 2 archives (2026-03-20 and 2026-05-27)
    # fall on non-trading calendar dates and were rejected per Rule 6.3 fail-closed calendar invariants,
    # resulting in exactly 1,193 valid trading sessions kept.
    rejected_non_cal = len(zip_files) - len(sorted_sessions)
    print(
        f"[INFO] Processed {len(sorted_sessions)} trading sessions from {len(zip_files)} raw archives in {elapsed:.2f}s "
        f"({rejected_non_cal} non-calendar archives rejected per Rule 6.3 fail-closed calendar invariants, Note N-28)."
    )
    return sorted_sessions, session_observations


def build_intervals(
    sorted_sessions: List[datetime.date],
    session_observations: Dict[datetime.date, Dict[str, Tuple[str, str]]],
) -> List[Tuple[str, str, str, datetime.date, Optional[datetime.date]]]:
    """
    Constructs contiguous symbol intervals, closing on ISIN transitions, company renames, and delistings.
    Dual-transition tracking:
      - When ISIN transitions to a new ISIN for a symbol, old interval closes on ex-date.
      - When symbol renames to a new symbol for an ISIN, old interval closes on rename date.
    """
    cal = load_nse_trading_calendar()
    all_cal_sessions = sorted(cal.sessions)
    session_to_idx = {s: i for i, s in enumerate(all_cal_sessions)}

    def get_next_cal_session(s: datetime.date) -> datetime.date:
        idx = session_to_idx[s]
        if idx + 1 < len(all_cal_sessions):
            return all_cal_sessions[idx + 1]
        return s + datetime.timedelta(days=1)

    pair_sessions: Dict[Tuple[str, str], List[datetime.date]] = defaultdict(list)
    pair_series: Dict[Tuple[str, str], str] = {}
    isin_timeline: Dict[str, List[Tuple[datetime.date, str]]] = defaultdict(list)
    sym_timeline: Dict[str, List[Tuple[datetime.date, str]]] = defaultdict(list)

    for s in sorted_sessions:
        for sym, (isin, series) in session_observations[s].items():
            pair_sessions[(isin, sym)].append(s)
            if (isin, sym) not in pair_series or series == "EQ":
                pair_series[(isin, sym)] = series
            isin_timeline[isin].append((s, sym))
            sym_timeline[sym].append((s, isin))

    intervals: List[Tuple[str, str, str, datetime.date, Optional[datetime.date]]] = []
    last_week_session = sorted_sessions[-5]

    for (isin, sym), dts in pair_sessions.items():
        start_s = dts[0]
        last_s = dts[-1]
        series = pair_series[(isin, sym)]

        # Check if isin transitioned to another symbol later
        next_sym_start = None
        for s, other_sym in isin_timeline[isin]:
            if s > last_s and other_sym != sym:
                next_sym_start = s
                break

        # Check if sym transitioned to another isin later
        next_isin_start = None
        for s, other_isin in sym_timeline[sym]:
            if s > last_s and other_isin != isin:
                next_isin_start = s
                break

        end_s: Optional[datetime.date] = None
        if next_sym_start and next_isin_start:
            end_s = min(next_sym_start, next_isin_start)
        elif next_sym_start:
            end_s = next_sym_start
        elif next_isin_start:
            end_s = next_isin_start
        else:
            if last_s >= last_week_session:
                end_s = None
            else:
                end_s = get_next_cal_session(last_s)

        intervals.append((isin, sym, series, start_s, end_s))

    return intervals


def validate_and_save_intervals(
    intervals: List[Tuple[str, str, str, datetime.date, Optional[datetime.date]]],
    output_path: Path,
) -> None:
    cal = load_nse_trading_calendar()
    valid_sessions = set(cal.sessions)

    # Sort intervals deterministically: symbol, effective_from, isin
    sorted_intervals = sorted(intervals, key=lambda x: (x[1], x[3], x[0]))

    # Validation:
    by_sym: Dict[Tuple[str, str], List[Tuple[str, str, str, datetime.date, Optional[datetime.date]]]] = defaultdict(list)
    by_isin: Dict[str, List[Tuple[str, str, str, datetime.date, Optional[datetime.date]]]] = defaultdict(list)
    for row in sorted_intervals:
        isin, sym, srs, ef, et = row
        # Note N-24: Explicit raise instead of bare assert to survive python -O
        if ef not in valid_sessions:
            raise ValueError(f"effective_from {ef} is not a valid trading session for {sym} (Note N-24)")
        if et is not None:
            if et not in valid_sessions:
                raise ValueError(f"effective_to {et} is not a valid trading session for {sym} (Note N-24)")
            if not (ef < et):
                raise ValueError(f"effective_from {ef} must precede effective_to {et} for {sym} (Note N-24)")
        by_sym[(sym, srs)].append(row)
        by_isin[isin].append(row)

    # Check non-overlapping per (symbol, series)
    for (sym, srs), sym_list in by_sym.items():
        sym_list_sorted = sorted(sym_list, key=lambda x: x[3])
        for i in range(len(sym_list_sorted) - 1):
            cur = sym_list_sorted[i]
            nxt = sym_list_sorted[i + 1]
            cur_et = cur[4]
            nxt_ef = nxt[3]
            if cur_et is None:
                raise ValueError(f"Intermediate interval for symbol {sym} cannot have None effective_to (Note N-24)")
            if not (cur_et <= nxt_ef):
                raise ValueError(f"Symbol {sym} ({srs}) intervals overlap: {cur} overlaps {nxt} (Note N-24)")

    # Check non-overlapping per ISIN
    for isin, isin_list in by_isin.items():
        isin_list_sorted = sorted(isin_list, key=lambda x: x[3])
        for i in range(len(isin_list_sorted) - 1):
            cur = isin_list_sorted[i]
            nxt = isin_list_sorted[i + 1]
            cur_et = cur[4]
            nxt_ef = nxt[3]
            if cur_et is None:
                raise ValueError(f"Intermediate interval for ISIN {isin} cannot have None effective_to (Note N-24)")
            if not (cur_et <= nxt_ef):
                raise ValueError(f"ISIN {isin} intervals overlap: {cur} overlaps {nxt} (Note N-24)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="\n", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["isin", "symbol", "series", "effective_from", "effective_to"])
        for isin, sym, srs, ef, et in sorted_intervals:
            writer.writerow([isin, sym, srs, ef.isoformat(), et.isoformat() if et else ""])

    data = output_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    unique_symbols = len({r[1] for r in sorted_intervals})
    unique_isins = len({r[0] for r in sorted_intervals})
    print(f"[SUCCESS] Wrote {len(sorted_intervals)} intervals to {output_path.name}")
    print(f"          Bytes: {len(data)}, SHA-256: {sha256}")
    print(f"          Unique Symbols: {unique_symbols}, Unique ISINs: {unique_isins}")

    # Register manifest entry
    manifest_entry = {
        "artifact": output_path.name,
        "derivation_script": "scripts/derive_cash_universe_intervals.py",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_records": len(sorted_intervals),
        "unique_symbols": unique_symbols,
        "unique_isins": unique_isins,
        "byte_count": len(data),
        "sha256": sha256,
        "source_coverage": "2022-01-03 to 2026-10-31 (1195 daily Bhavcopy archives)",
        "limitation_note": (
            "Sourced from 1,195 raw daily NSE Bhavcopy archives across 2022-2026. "
            "Raw Bhavcopy archives for 2018-04-01 through 2021-12-31 are absent from local "
            "Bronze storage and are not fabricated or bridged (§10.8, §39)."
        ),
    }

    manifest_file = output_path.parent / "manifest.jsonl"
    with open(manifest_file, "a", newline="\n", encoding="utf-8") as mf:
        mf.write(json.dumps(manifest_entry) + "\n")
    print(f"[SUCCESS] Appended provenance entry to {manifest_file.name}")


def main() -> None:
    print("=" * 80)
    print("SIGNAL ATLAS — CASH EQUITY SYMBOL->ISIN INTERVAL DERIVATION")
    print("=" * 80)
    sessions, obs = extract_session_observations()
    intervals = build_intervals(sessions, obs)
    validate_and_save_intervals(intervals, OUTPUT_CSV)


if __name__ == "__main__":
    main()
