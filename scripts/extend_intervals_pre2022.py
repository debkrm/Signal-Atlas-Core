#!/usr/bin/env python3
"""
Extends the cash-equity interval log backward to the binding window's first session (§90.9 item 3).

The committed log starts at 2022-01-03 because the derivation only ever read the post-2022 archives.
The 931 warm-up sessions (2018-04-02..2021-12-31) are committed Bronze with their own `SERIES` and
`ISIN` columns, so the backward rows are measured, not inferred: each `(isin, symbol)` span starts at
its first observed warm-up session, ends where the symbol's next identity or the committed row begins,
and is cut wherever the archive shows a different series.

Nothing is appended at the 2022-01-03 seam as a stand-in for a date (§90.9 item 3): a transition is
dated at the successor ISIN's first observed session. `generate_isin_transition_rows` then emits the
matching `ISIN_TRANSITION` row for every new pair the extension creates, so no identity boundary is
left undocumented (N-158, Ruling 1).

Every pre-existing row is preserved byte-identically; new rows are appended.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from append_series_restatements import (
    INTERVALS_CSV,
    collect_observations,
    discover_archives,
)
from derive_2022_2024_corpora import adjacent_identity_pairs
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import SymbolInterval, load_cash_universe_symbol_intervals
from signal_core.research.pit_universe import load_cash_equity_symbol_intervals

WINDOW_START = datetime.date(2018, 4, 2)
WINDOW_END = datetime.date(2021, 12, 31)
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"


def build_rows(
    committed_rows,
    observed: Dict[Tuple[str, str], List[Tuple[datetime.date, str]]],
    calendar_sessions: List[datetime.date],
) -> List[SymbolInterval]:
    """The warm-up rows implied by the archives, in file order."""
    # The log is append-only and may hold several rows per key (a restatement), so the seam is the
    # *earliest* committed row, never whichever row happened to be written last.
    committed_start: Dict[Tuple[str, str], datetime.date] = {}
    for row in committed_rows:
        if row.effective_from >= WINDOW_END:
            key = (row.isin, row.symbol)
            if key not in committed_start or row.effective_from < committed_start[key]:
                committed_start[key] = row.effective_from
    session_index = {session: index for index, session in enumerate(calendar_sessions)}

    def next_session(session: datetime.date) -> datetime.date:
        index = session_index[session]
        return calendar_sessions[index + 1] if index + 1 < len(calendar_sessions) else session

    by_symbol: Dict[str, List[Tuple[datetime.date, str]]] = defaultdict(list)
    warm: Dict[Tuple[str, str], List[Tuple[datetime.date, str]]] = {}
    for (isin, symbol), chain in observed.items():
        window = [(session, series) for session, series in chain if session <= WINDOW_END]
        if not window:
            continue
        warm[(isin, symbol)] = window
        by_symbol[symbol].append((window[0][0], isin))

    successors: Dict[str, List[Tuple[datetime.date, str]]] = {}
    for symbol, entries in by_symbol.items():
        entries.sort()
        ordered: List[Tuple[datetime.date, str]] = []
        for session, isin in entries:
            if ordered and ordered[-1][1] == isin:
                continue
            ordered.append((session, isin))
        successors[symbol] = ordered

    rows: List[SymbolInterval] = []
    for key in sorted(warm):
        isin, symbol = key
        chain = warm[key]
        start = chain[0][0]
        if start < WINDOW_START:
            start = WINDOW_START
            chain = [(session, series) for session, series in chain if session >= WINDOW_START]
            if not chain:
                continue

        boundary: Optional[datetime.date] = committed_start.get(key)
        for session, other_isin in successors.get(symbol, []):
            if session > start and other_isin != isin:
                boundary = session if boundary is None else min(boundary, session)
                break
        if boundary is None:
            boundary = next_session(chain[-1][0])
        if boundary <= start:
            continue

        cursor = start
        current = chain[0][1]
        for session, series in chain:
            if series == current:
                continue
            if session > cursor:
                rows.append(
                    SymbolInterval(
                        isin=isin, symbol=symbol, series=current,
                        effective_from=cursor, effective_to=session,
                    )
                )
            cursor = session
            current = series
        rows.append(
            SymbolInterval(
                isin=isin, symbol=symbol, series=current,
                effective_from=cursor, effective_to=boundary,
            )
        )
    return rows


def append_rows(rows: List[SymbolInterval]) -> Tuple[int, int, str]:
    original = INTERVALS_CSV.read_bytes()
    ordered = sorted({row for row in rows}, key=lambda r: (r.symbol, r.effective_from, r.isin, r.series))
    existing = {line.strip() for line in original.decode("ascii").splitlines()}
    chunk = []
    for row in ordered:
        line = ",".join(
            [
                row.isin, row.symbol, row.series, row.effective_from.isoformat(),
                row.effective_to.isoformat() if row.effective_to else "",
            ]
        )
        if line in existing:
            continue
        chunk.append(line)
    appended = ("\n".join(chunk) + "\n").encode("ascii")
    INTERVALS_CSV.write_bytes(original + appended)
    data = INTERVALS_CSV.read_bytes()
    if not data.startswith(original):
        raise ValueError("the append rewrote committed bytes; §10.1 forbids restating in place")
    print(f"[INFO] {len(chunk)} warm-up row(s) appended; {len(original.splitlines()) - 1} preserved")
    return len(chunk), len(data), hashlib.sha256(data).hexdigest()


def supersede_manifest(rows_appended: int, byte_count: int, sha256: str, active: int) -> None:
    records = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    current = [r for r in records if r.get("artifact") == INTERVALS_CSV.name and r.get("is_current")]
    if len(current) != 1:
        raise ValueError(f"expected one current row for {INTERVALS_CSV.name}, found {len(current)}")
    current[0]["is_current"] = False
    current[0]["status"] = "superseded"
    total = sum(1 for line in INTERVALS_CSV.read_text(encoding="utf-8").splitlines() if line.strip()) - 1
    records.append(
        {
            "artifact": INTERVALS_CSV.name,
            "derivation_script": "scripts/extend_intervals_pre2022.py",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_records": total,
            "active_records": active,
            "byte_count": byte_count,
            "sha256": sha256,
            "source_coverage": "2018-04-02 to 2026-10-31 (2,126 daily Bhavcopy archives)",
            "is_current": True,
            "status": "active",
            "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
            "retrieval_reference": (
                f"Audit §90.9 item 3, §90.6 Ruling 1: {rows_appended} warm-up interval row(s) appended "
                "from the committed 2018-2021 archives' own ISIN/SERIES columns; the 324 post-2022 "
                "identity tuples are preserved unchanged, every new identity boundary is dated at the "
                "successor ISIN's first session, and no boundary is dated at the 2022-01-03 seam."
            ),
        }
    )
    MANIFEST_PATH.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8", newline="\n"
    )


def main() -> None:
    print("=" * 80)
    print("SIGNAL ATLAS — CASH EQUITY INTERVAL BACKWARD EXTENSION (A2)")
    print("=" * 80)
    calendar = load_anchored_nse_trading_calendar()
    sessions = sorted(calendar.sessions)
    warmup_sessions = [s for s in sessions if WINDOW_START <= s <= WINDOW_END]
    print(f"[INFO] Warm-up window sessions: {len(warmup_sessions)} ({warmup_sessions[0]}..{warmup_sessions[-1]})")

    before = load_cash_universe_symbol_intervals()
    pairs_before = {(s, o, n, d) for s, o, n, d in adjacent_identity_pairs(before)}
    print(f"[INFO] Committed: {len(before)} active row(s), {len(pairs_before)} identity pair(s)")

    observed, _digests = collect_observations(discover_archives())
    rows = build_rows(before, observed, sessions)
    for row in rows:
        if not calendar.is_session(row.effective_from):
            raise ValueError(f"{row} starts on a non-session; refusing to date a boundary there")
        if row.effective_to is not None and not calendar.is_session(row.effective_to):
            raise ValueError(f"{row} ends on a non-session; refusing to date a boundary there")

    rows_appended, byte_count, sha256 = append_rows(rows)
    after = load_cash_universe_symbol_intervals()
    pairs_after = {(s, o, n, d) for s, o, n, d in adjacent_identity_pairs(after)}
    lost = pairs_before - pairs_after
    if lost:
        raise ValueError(f"the extension lost or moved {len(lost)} post-2022 identity pair(s): {sorted(lost)[:3]}")

    coverage = {row.effective_from for row in after if row.isin and row.symbol}
    uncovered = 0
    for session in warmup_sessions:
        if not any(row.effective_from <= session and (row.effective_to is None or session < row.effective_to) for row in after):
            uncovered += 1
    print(f"[INFO] Active rows {len(after)}; identity pairs {len(pairs_before)} -> {len(pairs_after)} "
          f"({len(pairs_after - pairs_before)} new warm-up boundary(ies))")
    print(f"[INFO] Warm-up sessions uncovered by any row: {uncovered} of {len(warmup_sessions)}")
    if uncovered:
        raise ValueError(f"{uncovered} warm-up session(s) are not covered by the extended log")
    if min(row.effective_from for row in after) >= datetime.date(2022, 1, 3):
        raise ValueError("the log still begins at the 2022-01-03 seam")

    supersede_manifest(rows_appended, byte_count, sha256, len(load_cash_equity_symbol_intervals()))
    print(f"[SUCCESS] earliest active row {min(r.effective_from for r in after)}; "
          f"bytes {byte_count}; sha256 {sha256}")
    _ = coverage


if __name__ == "__main__":
    main()
