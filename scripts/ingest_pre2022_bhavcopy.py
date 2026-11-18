#!/usr/bin/env python3
"""
BRONZE BHAVCOPY CAPTURE — Audit §87.5 Ruling 1

Captures the 931 sessions of `2018-04-01..2021-12-31` that Audit §86.5 Ruling 1 made capturable
and §87.5 authorised: byte-exact NSE Cash Market Bhavcopy archives under `data/raw/<year>/`, one
current `data/reference/manifest.jsonl` row per archive, every session labelled
`WARMUP_NOT_GATABLE`.

Capture eligibility is not gating eligibility. This script never computes a metric, never touches a
trial, and never moves `min_binding_evaluation_start_date`.

Per AGENTS.md §10.1 and §10.7, for every session:

1. The payload is validated before promotion: the archive must open, hold exactly one CSV, parse to
   at least one typed record, and report the session date the calendar schedules.
2. Promotion is atomic: bytes are written to a temporary file in the destination directory, fsynced,
   then `os.replace`d onto the final path, so no partially written archive is ever visible.
3. A session that fails validation leaves no file and no manifest row, and the run exits non-zero.
   The coverage probe (`scripts/probe_pre2022_bronze_coverage.py`) then fails closed on the count.
4. Every promoted archive appends exactly one manifest row carrying `source_url`, `retrieved_at`,
   `byte_count`, `sha256`, `session_date`, `session_type` and `gating_mode`. Rows are append-only;
   an existing current row whose bytes match is reused rather than rewritten, so re-running the
   script after an interruption resumes instead of duplicating.

Usage:
    python scripts/ingest_pre2022_bhavcopy.py [--limit N]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.storage.ingest import parse_bhavcopy_archive  # noqa: E402

CALENDAR_PATH = REPO_ROOT / "configs" / "trading_calendar_nse.json"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
RAW_ROOT = REPO_ROOT / "data" / "raw"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2021, 12, 31)
WARMUP_LABEL = "WARMUP_NOT_GATABLE"

URL_TEMPLATE = "https://archives.nseindia.com/content/historical/EQUITIES/{year}/{mon}/{filename}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 7.0)
INTER_REQUEST_SLEEP_SECONDS = 0.15


class CaptureError(RuntimeError):
    """Raised when an authorised session cannot be captured byte-exactly."""


def archive_filename(session_date: datetime.date) -> str:
    """NSE legacy Bhavcopy archive name, e.g. `cm02APR2018bhav.csv.zip`."""
    return f"cm{session_date.day:02d}{session_date.strftime('%b').upper()}{session_date.year}bhav.csv.zip"


def source_url(session_date: datetime.date, filename: str) -> str:
    return URL_TEMPLATE.format(year=session_date.year, mon=f"{session_date:%b}".upper(), filename=filename)


def window_sessions() -> dict[datetime.date, str]:
    """Calendar sessions inside the authorised window, with their scheduled session type."""
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    records = payload.get("session_records") or []
    if not records:
        raise CaptureError(f"{CALENDAR_PATH} carries no session_records")
    sessions: dict[datetime.date, str] = {}
    for item in records:
        day = datetime.date.fromisoformat(str(item["date"]))
        if WINDOW_START <= day <= WINDOW_END:
            sessions[day] = str(item.get("session_type", "FULL"))
    return dict(sorted(sessions.items()))


def current_manifest_rows() -> dict[str, dict]:
    """Latest current row per artifact path."""
    rows: dict[str, dict] = {}
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("is_current") is True:
            rows[str(row.get("artifact"))] = row
    return rows


def fetch(url: str) -> bytes:
    """Retrieves one archive, retrying transient failures with a fixed backoff."""
    last_error: Exception | None = None
    for attempt, backoff in enumerate((0.0,) + RETRY_BACKOFF_SECONDS):
        if backoff:
            time.sleep(backoff)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise CaptureError(f"HTTP {status} for {url}")
                payload = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, CaptureError) as exc:
            last_error = exc
            continue
        if not payload.startswith(b"PK\x03\x04"):
            last_error = CaptureError(f"{url} returned {len(payload)} non-ZIP bytes")
            continue
        return payload
    raise CaptureError(f"retrieval failed after {attempt + 1} attempt(s) for {url}: {last_error}")


def validate(payload: bytes, filename: str, session_date: datetime.date) -> int:
    """Fails closed unless the archive opens, holds one CSV, and parses to the scheduled session."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    except zipfile.BadZipFile as exc:
        raise CaptureError(f"{filename} is not a readable ZIP archive: {exc}") from exc
    if len(members) != 1:
        raise CaptureError(f"{filename} holds {len(members)} CSV member(s), expected exactly 1")

    try:
        parsed_date, records = parse_bhavcopy_archive(payload)
    except Exception as exc:  # noqa: BLE001 - a refused archive is a capture failure, not a crash
        raise CaptureError(f"{filename} could not be parsed by the ingest pipeline: {exc}") from exc
    if parsed_date != session_date:
        raise CaptureError(
            f"{filename} parses to trade_date {parsed_date} but the calendar schedules {session_date}"
        )
    if not records:
        raise CaptureError(f"{filename} parsed to zero records for {session_date}")
    return len(records)


def promote(payload: bytes, destination: Path) -> None:
    """Atomic promotion: temporary sibling, fsync, replace (§10.7)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.part-{os.getpid()}-{time.time_ns()}")
    try:
        with open(temp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    except BaseException:
        if temp.exists():
            temp.unlink()
        raise


def append_manifest_row(row: dict) -> None:
    """Appends one manifest line atomically and durably."""
    line = json.dumps(row, sort_keys=True) + "\n"
    with open(MANIFEST_PATH, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def manifest_row(
    session_date: datetime.date,
    session_type: str,
    artifact: str,
    url: str,
    retrieved_at: str,
    byte_count: int,
    sha256: str,
) -> dict:
    return {
        "artifact": artifact,
        "is_current": True,
        "status": "active",
        "timestamp_utc": retrieved_at,
        "retrieved_at": retrieved_at,
        "byte_count": byte_count,
        "sha256": sha256,
        "source_url": url,
        "session_date": session_date.isoformat(),
        "session_type": session_type,
        "gating_mode": WARMUP_LABEL,
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "source_coverage": f"NSE Cash Market Bhavcopy archive for session {session_date.isoformat()}",
        "description": f"Bronze Bhavcopy {session_date.isoformat()} ({session_type}), captured as warm-up",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="capture at most N sessions (smoke run)")
    args = parser.parse_args()

    sessions = window_sessions()
    known = current_manifest_rows()

    captured = skipped = 0
    failures: list[str] = []
    print("=" * 96)
    print(
        f"BRONZE CAPTURE — {len(sessions)} authorised session(s) in "
        f"{WINDOW_START.isoformat()}..{WINDOW_END.isoformat()} (§87.5 Ruling 1, {WARMUP_LABEL})"
    )
    print("=" * 96)

    for index, (session_date, session_type) in enumerate(sessions.items(), start=1):
        if args.limit is not None and captured >= args.limit:
            break
        filename = archive_filename(session_date)
        artifact = f"data/raw/{session_date.year}/{filename}"
        destination = RAW_ROOT / str(session_date.year) / filename

        existing = known.get(artifact)
        if existing is not None and destination.is_file():
            payload = destination.read_bytes()
            if len(payload) == existing.get("byte_count") and hashlib.sha256(payload).hexdigest() == existing.get("sha256"):
                skipped += 1
                continue

        url = source_url(session_date, filename)
        try:
            payload = fetch(url)
            records = validate(payload, filename, session_date)
        except CaptureError as exc:
            failures.append(f"{session_date.isoformat()} {session_type}: {exc}")
            print(f"[FAIL] {session_date.isoformat()} {session_type}: {exc}")
            continue

        promote(payload, destination)
        retrieved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        row = manifest_row(
            session_date=session_date,
            session_type=session_type,
            artifact=artifact,
            url=url,
            retrieved_at=retrieved_at,
            byte_count=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        append_manifest_row(row)
        known[artifact] = row
        captured += 1
        if captured % 25 == 0 or index == len(sessions):
            print(
                f"[INFO] {index}/{len(sessions)} session(s) visited — captured {captured}, "
                f"reused {skipped} (latest {session_date.isoformat()} {session_type}, {records} record(s))"
            )
        time.sleep(INTER_REQUEST_SLEEP_SECONDS)

    print("=" * 96)
    print(f"CAPTURED: {captured} new archive(s); REUSED: {skipped} attested archive(s); FAILED: {len(failures)}")
    for failure in failures:
        print(f"  [FAIL] {failure}")
    print("=" * 96)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
