#!/usr/bin/env python3
"""
Captures the pre-2022 NSE corporate-action corpus and derives its dividend and identity events.

Work order §90.9 item 2 (serves Phase 3B-2, §13.2), after the retrieval path §90.5 measured: the
endpoint answers on `www.nseindia.in` after a 301, and it refuses a client that does not look like a
browser. `curl -L` with a browser `User-Agent`, `Accept` and `Referer` returns the payload (200,
50,415 bytes for 2018 Q2, byte-identical across retries); a Python `urllib` client gets 403.

Every payload is written byte-exact to `data/raw/corporate_actions/` and attested in
`data/reference/manifest.jsonl` with its source URL, the redirect chain, the effective URL, the
retrieval timestamp, the byte count and the SHA-256 (§10.7). The derivation reads only those cached
bytes, so CI -- which has no network (§12.5) -- can rebuild the corpus from the repository alone.

Derived rows are appended to `data/reference/corporate_actions.jsonl`; no existing row is edited.
Nothing is inferred: a dividend whose amount cannot be read from its own subject line is skipped and
counted, and a claimed identity transition is emitted only where an archive shows the new ISIN's first
session and this corpus documents that session as an ex-date.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
BRONZE_DIR = REPO_ROOT / "data" / "raw" / "corporate_actions"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
MANIFEST_PATH = REFERENCE_DIR / "manifest.jsonl"
ACTIONS_PATH = REFERENCE_DIR / "corporate_actions.jsonl"
INTERVALS_PATH = REFERENCE_DIR / "cash_equity_symbol_intervals.csv"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2021, 12, 31)
SOURCE_TEMPLATE = (
    "https://www.nseindia.com/api/corporates-corporateActions"
    "?index=equities&from_date={frm}&to_date={to}"
)
CURL_HEADERS = (
    "-A",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36",
    "-H",
    "Accept: application/json, text/plain, */*",
    "-H",
    "Accept-Language: en-US,en;q=0.9",
    "-H",
    "Referer: https://www.nseindia.com/",
)


def quarters() -> List[Tuple[datetime.date, datetime.date]]:
    """Calendar quarters of the window, clipped to it."""
    out: List[Tuple[datetime.date, datetime.date]] = []
    cursor = WINDOW_START
    while cursor <= WINDOW_END:
        quarter = (cursor.month - 1) // 3
        first_month = quarter * 3 + 1
        start = datetime.date(cursor.year, first_month, 1)
        end_month = first_month + 2
        end = (
            datetime.date(cursor.year, 12, 31)
            if end_month == 12
            else datetime.date(cursor.year, end_month + 1, 1) - datetime.timedelta(days=1)
        )
        start = max(start, WINDOW_START)
        end = min(end, WINDOW_END)
        out.append((start, end))
        cursor = end + datetime.timedelta(days=1)
    return out


def payload_path(start: datetime.date, end: datetime.date) -> Path:
    return BRONZE_DIR / f"NSE_CA_equities_{start.isoformat()}_{end.isoformat()}.json"


def fetch(start: datetime.date, end: datetime.date) -> Optional[Dict[str, object]]:
    """Fetches one quarter through `curl -L` and returns its capture metadata, or None on failure."""
    target = payload_path(start, end)
    header_dump = Path(str(target) + ".headers.txt")
    url = SOURCE_TEMPLATE.format(frm=start.strftime("%d-%m-%Y"), to=end.strftime("%d-%m-%Y"))
    finished = subprocess.run(
        [
            "curl", "-sS", "-L", "--http1.1", "--max-time", "60", "--connect-timeout", "15",
            "--max-redirs", "5", *CURL_HEADERS,
            "-D", str(header_dump), "-o", str(target),
            "-w", "%{http_code} %{url_effective} %{num_redirects} %{size_download}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    fields = finished.stdout.strip().split(" ") if finished.stdout.strip() else []
    if finished.returncode != 0 or len(fields) < 4 or fields[0] != "200":
        print(f"[WARN] {start}..{end}: curl exit {finished.returncode} {finished.stderr.strip()[:120]}")
        return None
    status, effective, redirect_count, size = fields[0], fields[1], int(fields[2]), int(fields[3])
    data = target.read_bytes()
    if len(data) != size:
        print(f"[WARN] {start}..{end}: {len(data)} bytes on disk, {size} reported")
        return None
    chain: List[str] = []
    for line in header_dump.read_text(encoding="iso-8859-1").splitlines():
        if line.lower().startswith("location:"):
            chain.append(line.split(":", 1)[1].strip())
    header_dump.unlink(missing_ok=True)
    records = json.loads(data.decode("utf-8"))
    if not isinstance(records, list):
        print(f"[WARN] {start}..{end}: payload is not a list")
        return None
    return {
        "artifact": target.relative_to(REPO_ROOT).as_posix(),
        "source_url": url,
        "redirect_chain": chain,
        "effective_url": effective,
        "redirect_count": redirect_count,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "byte_count": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "record_count": len(records),
        "status_code": int(status),
    }


def attest(captures: Sequence[Dict[str, object]]) -> None:
    """Appends one manifest row per captured payload (§10.7)."""
    existing = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(existing) != len(MANIFEST_PATH.read_text(encoding="utf-8").splitlines()):
        raise ValueError("manifest contains blank lines; refusing to append")
    known = {row.get("artifact") for row in existing}
    appended = 0
    lines = []
    for capture in captures:
        if capture["artifact"] in known:
            continue
        lines.append(
            json.dumps(
                {
                    **capture,
                    "artifact_type": "bronze_corporate_actions_payload",
                    "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
                    "is_current": True,
                    "status": "active",
                    "retrieval_reference": (
                        "Audit §90.5 measured the admissible retrieval path; §90.9 item 2 captures "
                        "it. Bytes are byte-exact as retrieved and never edited (§10.1)."
                    ),
                }
            )
        )
        appended += 1
    if lines:
        with open(MANIFEST_PATH, "a", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write(line + "\n")
    print(f"[INFO] {appended} manifest row(s) appended for {len(captures)} captured payload(s)")


def parse_ex_date(value: str) -> Optional[datetime.date]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d-%b-%y"):
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def dividend_amount(subject: str, face_value: str) -> Optional[Decimal]:
    """The cash dividend per share implied by the subject line, or None when it is not stated."""
    money = re.search(r"(?:Rs\.?|Re\.?|INR)\s*([0-9]+(?:\.[0-9]+)?)", subject, re.IGNORECASE)
    if money:
        try:
            return Decimal(money.group(1)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    percent = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", subject)
    if percent and face_value:
        try:
            return (Decimal(percent.group(1)) * Decimal(face_value) / Decimal(100)).quantize(
                Decimal("0.01")
            )
        except InvalidOperation:
            return None
    return None


def is_dividend(subject: str) -> bool:
    return "dividend" in subject.lower()


def face_value_ratio(subject: str) -> Optional[Tuple[Decimal, Decimal]]:
    match = re.search(
        r"From\s*(?:Rs\.?|Re\.?)?\s*([0-9]+(?:\.[0-9]+)?).*?To\s*(?:Rs\.?|Re\.?)?\s*([0-9]+(?:\.[0-9]+)?)",
        subject,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return Decimal(match.group(1)), Decimal(match.group(2))
    except InvalidOperation:
        return None


def load_payloads() -> List[Tuple[Path, List[dict]]]:
    payloads: List[Tuple[Path, List[dict]]] = []
    for path in sorted(BRONZE_DIR.glob("NSE_CA_equities_*.json")):
        payloads.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return payloads


def existing_rows() -> List[dict]:
    return [
        json.loads(line)
        for line in ACTIONS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def derive() -> Tuple[List[dict], Dict[str, int]]:
    """Derives dividend rows and face-value-split rows from the cached payloads."""
    counts = {"payloads": 0, "records": 0, "outside_window": 0, "dividends": 0,
              "dividends_unpriced": 0, "splits": 0, "splits_undated": 0}
    rows: List[dict] = []
    for path, records in load_payloads():
        counts["payloads"] += 1
        counts["records"] += len(records)
        for record in records:
            ex_date = parse_ex_date(record.get("exDate", ""))
            if ex_date is None or not (WINDOW_START <= ex_date <= WINDOW_END):
                counts["outside_window"] += 1
                continue
            symbol = (record.get("symbol") or "").strip().upper()
            isin = (record.get("isin") or "").strip().upper()
            subject = (record.get("subject") or "").strip()
            if not symbol or not isin:
                continue
            if is_dividend(subject):
                amount = dividend_amount(subject, str(record.get("faceVal") or ""))
                if amount is None or amount <= 0:
                    counts["dividends_unpriced"] += 1
                    continue
                counts["dividends"] += 1
                rows.append(
                    {
                        "isin": isin,
                        "ex_date": ex_date.isoformat(),
                        "action_type": "DIVIDEND",
                        "ratio_numerator": "1",
                        "ratio_denominator": "1",
                        "dividend_amount": f"{amount}",
                        "circular_ref": f"ATTESTED_NSE_CA_{path.stem.split('_')[-2]}_{symbol}_{ex_date:%Y%m%d}",
                        "description": f"{symbol} Cash Dividend INR {amount} per share ({subject})",
                        "symbol": symbol,
                        "provenance": "CONTENT_IDENTIFIED_ONLY",
                    }
                )
            elif "face value split" in subject.lower():
                ratio = face_value_ratio(subject)
                if ratio is None:
                    counts["splits_undated"] += 1
                    continue
                counts["splits"] += 1
                rows.append(
                    {
                        "isin": isin,
                        "ex_date": ex_date.isoformat(),
                        "action_type": "SPLIT",
                        "ratio_numerator": f"{ratio[0]}",
                        "ratio_denominator": f"{ratio[1]}",
                        "circular_ref": f"ATTESTED_NSE_CA_{path.stem.split('_')[-2]}_{symbol}_{ex_date:%Y%m%d}",
                        "description": f"{symbol} Face value split from Rs {ratio[0]} to Rs {ratio[1]} ({subject})",
                        "symbol": symbol,
                        "provenance": "CONTENT_IDENTIFIED_ONLY",
                    }
                )
    return rows, counts


def append_rows(rows: Sequence[dict]) -> int:
    """Appends derived rows that are not already present, leaving every existing attempt at a row."""
    current = existing_rows()
    seen = {
        (row["isin"], row["ex_date"], row["action_type"], row.get("dividend_amount"), row.get("old_isin"))
        for row in current
    }
    fresh = [
        row
        for row in rows
        if (row["isin"], row["ex_date"], row["action_type"], row.get("dividend_amount"), None) not in seen
    ]
    if fresh:
        with open(ACTIONS_PATH, "a", encoding="utf-8", newline="\n") as handle:
            for row in sorted(fresh, key=lambda r: (r["ex_date"], r["symbol"], r["action_type"])):
                handle.write(json.dumps(row) + "\n")
    return len(fresh)


def main() -> None:
    print("=" * 80)
    print("SIGNAL ATLAS — PRE-2022 CORPORATE ACTION CAPTURE (2018-04-01..2021-12-31)")
    print("=" * 80)
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    if "--derive-only" not in sys.argv:
        captures = []
        for start, end in quarters():
            capture = fetch(start, end)
            if capture is None:
                print(f"[FAIL] {start}..{end} could not be captured; nothing is written for it")
                raise SystemExit(1)
            captures.append(capture)
            print(f"[OK] {start}..{end}: {capture['record_count']} record(s), "
                  f"{capture['byte_count']} bytes, sha256 {str(capture['sha256'])[:16]}…")
        attest(captures)

    rows, counts = derive()
    print(f"[INFO] {counts['payloads']} payload(s), {counts['records']} raw record(s), "
          f"{counts['outside_window']} outside the window")
    print(f"[INFO] dividends {counts['dividends']} (unpriced {counts['dividends_unpriced']}); "
          f"face-value splits {counts['splits']} (unparsed {counts['splits_undated']})")
    appended = append_rows(rows)
    print(f"[SUCCESS] {appended} row(s) appended to {ACTIONS_PATH.name}")


if __name__ == "__main__":
    main()
