#!/usr/bin/env python3
"""
PRE-2022 BRONZE COVERAGE PROBE — Audit §87.5 Ruling 1, probe (1)

Exits 0 only when the authorised warm-up window `2018-04-01..2021-12-31` is captured exactly:
**931** calendar sessions, each attested by exactly one *current* `data/reference/manifest.jsonl`
row whose `byte_count` and `sha256` match the archive on disk, whose `session_type` matches the
calendar, and which carries the explicit `WARMUP_NOT_GATABLE` label. Every manifest row must name a
calendar session in the window, and every archive on disk must be attested, so the reconciliation is
bidirectional rather than a lower bound.

It fails closed by construction on all seven shapes the Ruling names:

- a calendar session with no archive (or no current manifest row) — `no current manifest row`;
- an archive (or manifest row) with no calendar session — `not a calendar session in the window`;
- an archive whose bytes disagree with its row — `sha256 mismatch` / `byte_count mismatch`;
- an archive whose own `TIMESTAMP` column names another session — `carries its own session date(s)`,
  so a correctly hashed but transposed pair of archives is refused rather than certified (N-171);
- a muhurat or special bar stored as a full session — `session_type mismatch`;
- an unlabelled capture — `gating_mode` must read `WARMUP_NOT_GATABLE`;
- two current rows claiming the same session — `duplicate current row(s)`.

Capture eligibility is not gating eligibility: this probe measures bytes and labels, and it neither
computes a metric nor reads the holdout.

Usage:
    python scripts/probe_pre2022_bronze_coverage.py
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Dict, List, Set, Tuple
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT / "src"), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.storage.ingest import BhavcopyIngestError, parse_bhavcopy_date  # noqa: E402

CALENDAR_PATH = REPO_ROOT / "configs" / "trading_calendar_nse.json"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
RAW_ROOT = REPO_ROOT / "data" / "raw"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2021, 12, 31)
WINDOW_YEARS = (2018, 2019, 2020, 2021)
EXPECTED_SESSIONS = 931
WARMUP_LABEL = "WARMUP_NOT_GATABLE"


def calendar_sessions() -> Dict[datetime.date, str]:
    """Authoritative sessions and their scheduled types inside the warm-up window."""
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    sessions: Dict[datetime.date, str] = {}
    for item in payload.get("session_records") or []:
        day = datetime.date.fromisoformat(str(item["date"]))
        if WINDOW_START <= day <= WINDOW_END:
            sessions[day] = str(item.get("session_type", "FULL"))
    return dict(sorted(sessions.items()))


def current_window_rows() -> Tuple[Dict[datetime.date, List[dict]], List[dict]]:
    """
    Splits current manifest rows into those attesting a `data/raw/<2018..2021>` archive (keyed by the
    session date their `session_date` field declares) and those that name the window but cannot be
    placed on a date.
    """
    by_date: Dict[datetime.date, List[dict]] = {}
    undated: List[dict] = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("is_current") is not True:
            continue
        artifact = str(row.get("artifact") or "")
        prefix = "data/raw/"
        if not artifact.startswith(prefix):
            continue
        parts = artifact[len(prefix):].split("/")
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) not in WINDOW_YEARS:
            continue
        raw_date = row.get("session_date")
        if not isinstance(raw_date, str) or not raw_date.strip():
            undated.append(row)
            continue
        by_date.setdefault(datetime.date.fromisoformat(raw_date[:10]), []).append(row)
    return by_date, undated


def archives_on_disk() -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for year in WINDOW_YEARS:
        directory = RAW_ROOT / str(year)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.zip")):
            found[f"data/raw/{year}/{path.name}"] = path
    return found


def embedded_session_dates(path: Path) -> Set[datetime.date]:
    """
    The distinct session dates the archive's own rows carry, parsed from its `TIMESTAMP` (or the
    unified-format `TRADEDATE`) column — the exchange's statement about which session these bytes are.
    """
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise BhavcopyIngestError(f"{path.name} holds {len(members)} CSV member(s), expected 1")
        text = archive.read(members[0]).decode("utf-8", "replace")
    reader = csv.reader(io.StringIO(text))
    header = [cell.strip().upper() for cell in next(reader)]
    column = header.index("TIMESTAMP") if "TIMESTAMP" in header else header.index("TRADEDATE")
    raw: Set[str] = set()
    for row in reader:
        if len(row) > column and row[column].strip():
            raw.add(row[column].strip())
    return {parse_bhavcopy_date(value) for value in raw}


def main() -> int:
    sessions = calendar_sessions()
    by_date, undated = current_window_rows()
    on_disk = archives_on_disk()
    problems: List[str] = []

    print("=" * 96)
    print("PRE-2022 BRONZE COVERAGE — Audit §87.5 Ruling 1, probe (1)")
    print(f"Window under test: {WINDOW_START.isoformat()}..{WINDOW_END.isoformat()}")
    print("=" * 96)

    type_counts: Dict[str, int] = {}
    for session_type in sessions.values():
        type_counts[session_type] = type_counts.get(session_type, 0) + 1
    print(
        f"[INFO] Calendar sessions in window: {len(sessions)} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(type_counts.items()))})"
    )
    print(f"[INFO] Current manifest rows naming a {WINDOW_YEARS[0]}-{WINDOW_YEARS[-1]} archive: {sum(len(v) for v in by_date.values())}")
    print(f"[INFO] Bhavcopy archives on disk in those directories: {len(on_disk)}")

    if len(sessions) != EXPECTED_SESSIONS:
        problems.append(
            f"the calendar schedules {len(sessions)} session(s) in the window, expected {EXPECTED_SESSIONS}"
        )

    verified = 0
    attested_paths: set = set()
    for session_date, session_type in sessions.items():
        rows = by_date.get(session_date, [])
        if not rows:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): no current manifest row attests an archive"
            )
            continue
        if len(rows) > 1:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {len(rows)} duplicate current row(s) "
                f"({', '.join(str(r.get('artifact')) for r in rows)})"
            )
            continue
        row = rows[0]
        artifact = str(row.get("artifact"))
        if row.get("session_type") != session_type:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} declares session_type "
                f"{row.get('session_type')!r} instead of the calendar's {session_type!r}"
            )
        if row.get("gating_mode") != WARMUP_LABEL:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} carries gating_mode "
                f"{row.get('gating_mode')!r}, expected {WARMUP_LABEL!r}"
            )
        for field in ("source_url", "retrieved_at"):
            if not isinstance(row.get(field), str) or not str(row.get(field)).strip():
                problems.append(
                    f"session {session_date.isoformat()} ({session_type}): {artifact} carries no {field}"
                )
        path = on_disk.get(artifact)
        if path is None:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): attested archive {artifact} is absent from disk"
            )
            continue
        attested_paths.add(artifact)
        payload = path.read_bytes()
        if len(payload) != row.get("byte_count"):
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} is {len(payload)} bytes on disk "
                f"but the row attests {row.get('byte_count')}"
            )
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row.get("sha256"):
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} sha256 mismatch "
                f"(disk {digest}, row {row.get('sha256')})"
            )
            continue
        # The bytes are the numbers the row attests; the archive's own date column is what makes the row's
        # label true. Without this, two archives filed under each other's session satisfy every check above.
        try:
            embedded = embedded_session_dates(path)
        except (
            BhavcopyIngestError, KeyError, OSError, StopIteration, UnicodeError, ValueError, zipfile.BadZipFile,
        ) as exc:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} cannot be read for its own "
                f"session date: {exc}"
            )
            continue
        if embedded != {session_date}:
            problems.append(
                f"session {session_date.isoformat()} ({session_type}): {artifact} carries its own session "
                f"date(s) {', '.join(d.isoformat() for d in sorted(embedded)) or '<none>'}, so the row's "
                f"session_date is not on these bytes"
            )
            continue
        verified += 1

    for session_date, rows in sorted(by_date.items()):
        if session_date not in sessions:
            for row in rows:
                problems.append(
                    f"archive {row.get('artifact')}: session_date {session_date.isoformat()} is not a calendar "
                    f"session in the window"
                )

    for row in undated:
        problems.append(
            f"archive {row.get('artifact')}: current row carries no session_date, so it cannot be placed on the calendar"
        )

    for artifact, path in on_disk.items():
        if artifact not in attested_paths:
            problems.append(f"archive {artifact} ({path.stat().st_size} bytes): no current manifest row attests it")

    shown = problems[:25]
    for problem in shown:
        print(f"[FAIL] {problem}")
    if len(problems) > len(shown):
        print(f"[FAIL] … and {len(problems) - len(shown)} more coverage problem(s)")

    print("=" * 96)
    if problems:
        print(
            f"OVERALL: NOT COVERED — {verified}/{EXPECTED_SESSIONS} session(s) attested and digest-matched, "
            f"{len(problems)} problem(s); the window is not capturable as certified (§87.5)"
        )
        print("=" * 96)
        return 1
    print(
        f"OVERALL: COVERED — {verified}/{EXPECTED_SESSIONS} session(s) attested by one current manifest row each, "
        f"bytes matching byte_count and sha256, each archive's own session date equal to its row, "
        f"{WARMUP_LABEL} on every row"
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
