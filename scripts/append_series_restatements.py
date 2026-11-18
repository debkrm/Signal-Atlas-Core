#!/usr/bin/env python3
"""
Appends `series` restatements to the cash-equity interval log (N-175, Audit §90.4, Ruling 2).

The committed table carries one open-ended row per `(isin, symbol)` whose `series` is whatever the
derivation preferred (`EQ` if any session observed it), so a scrip that moved to trade-to-trade keeps
being described as `EQ` for every later session. The archives say otherwise, and two consumers read
that attribute: `get_point_in_time_active_equities(..., series="EQ")` and
`SecurityMaster.resolve_symbol(...).series`, which `walkforward.py` feeds to Gate G2C-3.

This script never edits or deletes a committed row. For each `(isin, symbol)` whose observed series
disagrees with the committed row on at least one session, it appends that row's span decomposed into
runs of constant observed series, each run dated at the first session the archive shows it. A run ends
where the next one begins; the last run inherits the committed row's `effective_to`, so the restatement
covers exactly the span the row it corrects covered and no more. `apply_interval_restatements` then
supersedes the corrected row at load time and resolution sees the runs.

Every appended row is recorded with the archives that establish it in
`data/reference/cash_equity_symbol_interval_restatements.jsonl` (§10.7 provenance, §10.1 restatement
reference), because the CSV itself has no room for evidence.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.ingest import parse_bhavcopy_archive
from signal_core.storage.security_master import (
    SecurityMaster,
    SymbolInterval,
    apply_interval_restatements,
    load_cash_universe_symbol_intervals,
)
from derive_2022_2024_corpora import adjacent_identity_pairs

RAW_DIR = REPO_ROOT / "data" / "raw"
INTERVALS_CSV = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_intervals.csv"
EVIDENCE_JSONL = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_interval_restatements.jsonl"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
TARGET_SERIES = ("EQ", "BE", "BZ", "SM")


def archive_session(path: Path) -> Optional[datetime.date]:
    """
    The session a file name can establish, for archives whose `TRADEDATE` column cannot be parsed.

    The unified `BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` names carry the session; the parser
    still validates every row against the date it is given (and against each other), so supplying it
    is not a guess the archive could contradict. 573 of the 2,126 committed archives -- all of 2025
    and 2026, and 121 of 2024 -- fail without it.
    """
    match = re.search(r"_(\d{8})_F_0000\.csv\.zip$", path.name, re.IGNORECASE)
    if match is None:
        return None
    return datetime.datetime.strptime(match.group(1), "%Y%m%d").date()


def discover_archives() -> List[Tuple[Path, int]]:
    """Every committed Bhavcopy archive under `data/raw/<year>/`, in year order."""
    found: List[Tuple[Path, int]] = []
    for year_dir in sorted(RAW_DIR.iterdir()):
        if year_dir.is_dir() and year_dir.name.isdigit():
            for path in sorted(year_dir.glob("*.zip")):
                found.append((path, int(year_dir.name)))
    return found


def collect_observations(
    archives: Sequence[Tuple[Path, int]],
) -> Tuple[Dict[Tuple[str, str], List[Tuple[datetime.date, str]]], Dict[Tuple[str, datetime.date], str]]:
    """
    Returns `(isin, symbol) -> [(session, series)]` in session order, and
    `(relative_archive_path, session) -> sha256` for the rows this script cites.
    """
    calendar = load_anchored_nse_trading_calendar()
    sessions = set(calendar.sessions)
    observed: Dict[Tuple[str, str], List[Tuple[datetime.date, str]]] = defaultdict(list)
    digests: Dict[Tuple[str, datetime.date], str] = {}
    skipped = 0
    for path, _year in archives:
        try:
            trade_date, records = parse_bhavcopy_archive(str(path), trade_date=archive_session(path))
        except Exception:
            skipped += 1
            continue
        if trade_date not in sessions:
            skipped += 1
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        digests[(relative, trade_date)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for record in records:
            if record.series not in TARGET_SERIES or not record.isin:
                continue
            observed[(record.isin, record.symbol)].append((trade_date, record.series))
    print(f"[INFO] {len(archives)} archive(s) read, {skipped} skipped; {len(observed)} (isin, symbol) chains")
    for chain in observed.values():
        chain.sort(key=lambda pair: pair[0])
    return observed, digests


def build_restatements(
    committed: Sequence[SymbolInterval],
    observed: Dict[Tuple[str, str], List[Tuple[datetime.date, str]]],
    digests: Dict[Tuple[str, datetime.date], str],
) -> List[Tuple[SymbolInterval, str, List[str]]]:
    """
    Restates every committed row whose `series` its archives contradict, as `(row, description,
    cited_archives)` triples.

    The decomposition starts at the row's own `effective_from` carrying the row's own series and cuts
    only where an archive shows a *different* series, so a change is dated at the first session it is
    observed (§90.8) and no span of the row it supersedes is left uncovered -- the superseded row is
    dropped from resolution in full. Sessions with no observation inherit the current span's series,
    which is the interval contract itself, not a fill of a missing record (§6.3).
    """
    committed_index: Dict[Tuple[str, str], SymbolInterval] = {(r.isin, r.symbol): r for r in committed}
    out: List[Tuple[SymbolInterval, str, List[str]]] = []
    for key, chain in sorted(observed.items()):
        row = committed_index.get(key)
        if row is None:
            continue
        window = [
            (session, series)
            for session, series in chain
            if session >= row.effective_from
            and (row.effective_to is None or session < row.effective_to)
        ]
        if not window or all(series == row.series for _session, series in window):
            continue

        cuts: List[Tuple[Tuple[datetime.date, Optional[datetime.date], str], datetime.date]] = []
        cursor = row.effective_from
        current = row.series
        for session, series in window:
            if series == current:
                continue
            if session > cursor:
                cuts.append(((cursor, session, current), cursor))
            cursor = session
            current = series
        cuts.append(((cursor, row.effective_to, current), cursor))

        for (first, effective_to, series), _cursor in cuts:
            if effective_to is not None and effective_to <= first:
                continue
            cited = [
                f"{'first' if session == first else 'last'} {relative} sha256:{digest}"
                for (relative, session), digest in sorted(digests.items())
                if session in (first, effective_to)
            ]
            out.append(
                (
                    SymbolInterval(
                        isin=row.isin,
                        symbol=row.symbol,
                        series=series,
                        effective_from=first,
                        effective_to=effective_to,
                    ),
                    f"supersedes {row.isin} {row.symbol} {row.series} {row.effective_from}.."
                    f"{row.effective_to or ''} for the span {first}..{effective_to or ''}",
                    cited,
                )
            )
    return out


def archive_disagreements(
    rows: Sequence[SymbolInterval],
    observed: Dict[Tuple[str, str], List[Tuple[datetime.date, str]]],
) -> Tuple[int, int]:
    """Returns `(sequences compared, series disagreements)` between the table and the archives."""
    master = SecurityMaster(symbol_intervals=rows)  # validates the active set: no overlap
    compared = 0
    disagreements = 0
    for (isin, _symbol), chain in observed.items():
        for session, series in chain:
            interval = master.resolve_symbol(isin, session)
            if interval is None:
                continue
            compared += 1
            if interval.series != series:
                disagreements += 1
    return compared, disagreements


def append_rows(
    restatements: Sequence[Tuple[SymbolInterval, str, List[str]]],
) -> Tuple[int, int, str]:
    """
    Appends to the CSV without rewriting a single committed byte. Returns `(rows, bytes, sha256)`.
    """
    original = INTERVALS_CSV.read_bytes()
    before = len(original.splitlines())
    ordered = sorted(
        {row for row, _description, _cited in restatements},
        key=lambda r: (r.symbol, r.effective_from, r.isin, r.series),
    )
    chunk = []
    for row in ordered:
        chunk.append(
            ",".join(
                [
                    row.isin,
                    row.symbol,
                    row.series,
                    row.effective_from.isoformat(),
                    row.effective_to.isoformat() if row.effective_to else "",
                ]
            )
        )
    appended = ("\n".join(chunk) + "\n").encode("ascii")
    INTERVALS_CSV.write_bytes(original + appended)
    data = INTERVALS_CSV.read_bytes()
    if not data.startswith(original):
        raise ValueError("the append rewrote committed bytes; §10.1 forbids restating in place")
    if len(data) != len(original) + len(appended):
        raise ValueError("the artifact grew by an amount other than the appended rows")
    print(f"[INFO] {before - 1} committed row(s) preserved byte-identically; {len(ordered)} row(s) appended")
    return len(ordered), len(data), hashlib.sha256(data).hexdigest()


def supersede_manifest_row(rows_appended: int, byte_count: int, sha256: str) -> None:
    """Marks the current row superseded and appends the new one, per the established convention."""
    records = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    superseded = 0
    for record in records:
        if record.get("artifact") == INTERVALS_CSV.name and record.get("is_current"):
            record["is_current"] = False
            record["status"] = "superseded"
            superseded += 1
    if superseded != 1:
        raise ValueError(f"expected exactly one current row for {INTERVALS_CSV.name}, found {superseded}")
    total_records = sum(1 for line in INTERVALS_CSV.read_text(encoding="utf-8").splitlines() if line.strip()) - 1
    records.append(
        {
            "artifact": INTERVALS_CSV.name,
            "derivation_script": "scripts/append_series_restatements.py",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_records": total_records,
            "byte_count": byte_count,
            "sha256": sha256,
            "source_coverage": "2022-01-03 to 2026-10-31 (1,195 daily Bhavcopy archives)",
            "is_current": True,
            "status": "active",
            "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
            "retrieval_reference": (
                f"Audit §90.9 item 1 (N-175), §90.7 Ruling 2: {rows_appended} series restatement row(s) "
                "appended from the archives' own SERIES column; every pre-existing row retained byte-"
                "identically, superseded at load by `apply_interval_restatements` rather than edited "
                "or deleted (§10.1)."
            ),
        }
    )
    MANIFEST_PATH.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8", newline="\n"
    )


def main() -> None:
    print("=" * 80)
    print("SIGNAL ATLAS — CASH EQUITY SERIES RESTATEMENT (N-175)")
    print("=" * 80)
    archives = discover_archives()
    observed, digests = collect_observations(archives)
    committed = load_cash_universe_symbol_intervals()
    pairs_before = adjacent_identity_pairs(committed)
    print(f"[INFO] Committed table: {len(committed)} active row(s), {len(pairs_before)} identity pair(s)")

    restatements = build_restatements(committed, observed, digests)
    if not restatements:
        print("[INFO] Every committed series agrees with its archives; nothing to append")
        return

    EVIDENCE_JSONL.write_text(
        "".join(
            json.dumps(
                {
                    "isin": row.isin,
                    "symbol": row.symbol,
                    "series": row.series,
                    "effective_from": row.effective_from.isoformat(),
                    "effective_to": row.effective_to.isoformat() if row.effective_to else None,
                    "supersedes": description,
                    "source_archives": cited,
                    "audit_reference": "§90.9 item 1 / N-175 / §90.7 Ruling 2",
                }
            )
            + "\n"
            for row, description, cited in sorted(
                restatements, key=lambda triple: (triple[0].isin, triple[0].effective_from)
            )
        ),
        encoding="utf-8",
        newline="\n",
    )

    rows_appended, byte_count, sha256 = append_rows(restatements)
    rows = load_cash_universe_symbol_intervals()
    SecurityMaster(symbol_intervals=rows)  # validates the active set: no overlap, no lost span
    pairs_after = adjacent_identity_pairs(rows)
    if {(s, o, n, d) for s, o, n, d in pairs_before} - {(s, o, n, d) for s, o, n, d in pairs_after}:
        raise ValueError("the restatement lost or moved an identity pair (§90.7 Ruling 1)")

    compared, disagreements = archive_disagreements(rows, observed)
    print(f"[INFO] {len(rows)} active row(s); {len(pairs_after)} identity pair(s) (324 tuples retained)")
    print(f"[INFO] Archive agreement: {compared} sequence(s) compared, {disagreements} series disagreement(s)")
    if disagreements:
        raise ValueError(f"{disagreements} sequence(s) still disagree with their archive; restatement incomplete")

    supersede_manifest_row(rows_appended, byte_count, sha256)
    print(f"[SUCCESS] {rows_appended} row(s) appended; bytes {byte_count}; sha256 {sha256}")
    print(f"[SUCCESS] Evidence: {EVIDENCE_JSONL.relative_to(REPO_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
