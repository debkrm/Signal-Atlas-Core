#!/usr/bin/env python3
"""
PRICE-ACTION ATTESTATION — Audit §95.10 items 3-5, §95.7 Ruling 2

An adjustment may be applied to a gating series only where a committed Bronze corporate-action record
attests the same ISIN, action type and ex-date (§95.7). This tool makes that measurable:

1. `--capture` fetches the cash-equity corporate-action payloads for every calendar quarter of
   `2018-04-01..2023-12-31` that is not yet committed, byte-exact, and appends one `manifest.jsonl`
   row per payload (source_url, retrieved_at, byte_count, sha256). The pre-2022 quarters were captured
   under Audit §90.9; 2022-2023 were absent, which is why 46 panel dates moved beyond ±35% with no
   archive record at all.
2. `--report` derives the archive's price-side events (`SPLIT`, `BONUS`, `CONSOLIDATION`) and its
   consideration events (`DEMERGER`: demerger, scheme of demerger/arrangement, capital reduction), then
   reconciles them against `data/reference/corporate_actions.jsonl` in both directions.
3. `--write` appends the attested rows the table lacks, carrying `source_digest` (the sha256 of the
   payload they came from) and supersedes — never edits — the rows the archive contradicts or cannot
   attest (§10.1). A superseded row stays in the file and in the loader's output; the corpus builder
   applies only rows whose `source_digest` resolves to a committed payload and that are not superseded.

Nothing is inferred: a subject whose ratio cannot be read is reported and skipped, never guessed.

Usage:
    python scripts/attest_price_actions.py --capture
    python scripts/attest_price_actions.py --report
    python scripts/attest_price_actions.py --write
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
BRONZE_DIR = REPO_ROOT / "data" / "raw" / "corporate_actions"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
MANIFEST_PATH = REFERENCE_DIR / "manifest.jsonl"
ACTIONS_PATH = REFERENCE_DIR / "corporate_actions.jsonl"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
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


class Attested(NamedTuple):
    isin: str
    ex_date: datetime.date
    action_type: str
    ratio_numerator: str
    ratio_denominator: str
    subject: str
    symbol: str
    source_artifact: str
    source_digest: str


def quarters() -> List[Tuple[datetime.date, datetime.date]]:
    out: List[Tuple[datetime.date, datetime.date]] = []
    cursor = WINDOW_START
    while cursor <= WINDOW_END:
        quarter = (cursor.month - 1) // 3
        first_month = quarter * 3 + 1
        start = max(datetime.date(cursor.year, first_month, 1), WINDOW_START)
        end_month = first_month + 2
        end = min(
            datetime.date(cursor.year, 12, 31) if end_month == 12 else datetime.date(cursor.year, end_month + 1, 1) - datetime.timedelta(days=1),
            WINDOW_END,
        )
        out.append((start, end))
        cursor = end + datetime.timedelta(days=1)
    return out


def payload_name(start: datetime.date, end: datetime.date) -> str:
    return f"NSE_CA_equities_{start.isoformat()}_{end.isoformat()}.json"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture() -> int:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing = {str(row.get("artifact")) for row in rows}
    new_rows: List[dict] = []
    for start, end in quarters():
        name = payload_name(start, end)
        relative = f"data/raw/corporate_actions/{name}"
        target = BRONZE_DIR / name
        if relative in existing and target.is_file():
            continue
        if relative in existing and not target.is_file():
            raise SystemExit(f"{relative} is in the manifest but absent on disk; refusing to re-capture over it")
        url = SOURCE_TEMPLATE.format(
            frm=start.strftime("%d-%m-%Y"), to=end.strftime("%d-%m-%Y")
        )
        with tempfile.TemporaryDirectory(prefix="ca_capture_") as tmp:
            payload_path = Path(tmp) / "payload"
            result = subprocess.run(
                ["curl", "-sS", "-L", "-4", "-m", "120", *CURL_HEADERS, "-o", str(payload_path), url],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0 or not payload_path.is_file():
                raise SystemExit(f"retrieval failed for {url}: {result.stderr.strip()[:300]}")
            payload = payload_path.read_bytes()
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, list) or not parsed:
            raise SystemExit(f"{url} returned {type(parsed).__name__} with no rows; refusing to commit it")
        digest = hashlib.sha256(payload).hexdigest()
        handle, tmp_name = tempfile.mkstemp(dir=str(BRONZE_DIR), prefix=".tmp_")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        new_rows.append({
            "artifact": relative,
            "is_current": True,
            "status": "active",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            "byte_count": len(payload),
            "sha256": digest,
            "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
            "source_url": url,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            "source_coverage": f"{start.isoformat()} to {end.isoformat()} (NSE cash-equity corporate actions)",
            "description": "Bronze corporate-action payload captured byte-exact for price-action attestation (Audit §95.10 item 3).",
        })
        print(f"[INFO] captured {relative}: {len(payload)} bytes, sha256 {digest[:16]}…, {len(parsed)} row(s)")
    if not new_rows:
        print("OVERALL: every quarter of the window is already committed")
        return 0
    with open(MANIFEST_PATH, "a", encoding="utf-8", newline="\n") as out:
        for row in new_rows:
            out.write(json.dumps(row) + "\n")
    print(f"OVERALL: captured {len(new_rows)} payload(s); manifest now has {len(rows) + len(new_rows)} row(s)")
    return 0


BONUS_RE = re.compile(r"bonus[^0-9]*(\d+)\s*:\s*(\d+)", re.IGNORECASE)
# A bonus of preference shares or debentures does not change the equity share count, so it is not a
# price-side event for this table at all.
NON_EQUITY_MARKERS = ("ncrps", "preference", "debenture", "ncd")
SPLIT_RE = re.compile(
    r"from\s+rs\.?\s*([\d.]+)\s*/?-?\s*per\s+share\s+to\s+rs?\.?e?\s*([\d.]+)",
    re.IGNORECASE,
)
DEMERGER_MARKERS = ("demerger", "scheme of arrangement", "scheme of arangement", "capital reduction")


def _ratio_from_subject(subject: str) -> Optional[Tuple[str, str, str]]:
    """`(action_type, numerator, denominator)` from a subject line, or None when it cannot be read."""
    low = subject.lower()
    if any(marker in low for marker in NON_EQUITY_MARKERS):
        return None
    if "capital reduction" in low:
        # A capital reduction returns cash and leaves the share count closer to unchanged; no ratio is
        # stated in the archive, so it is a consideration event, not a share restatement.
        return ("DEMERGER", "1", "1")
    if "demerger" in low or "scheme of arangement" in low or "scheme of arrangement" in low:
        return ("DEMERGER", "1", "1")
    if "bonus" in low:
        match = BONUS_RE.search(subject)
        if not match:
            return None
        held, free = int(match.group(1)), int(match.group(2))
        if free <= 0:
            return None
        return ("BONUS", str(held + free), str(free))
    if "split" in low or "sub-division" in low or "subdivision" in low:
        match = SPLIT_RE.search(subject)
        if not match:
            return None
        old, new = Decimal_like(match.group(1)), Decimal_like(match.group(2))
        if new <= 0 or old <= 0:
            return None
        return ("SPLIT", _plain(old / new), "1")
    if "consolidat" in low:
        match = SPLIT_RE.search(subject)
        if not match:
            return None
        old, new = Decimal_like(match.group(1)), Decimal_like(match.group(2))
        if new <= 0 or old <= 0:
            return None
        # Consolidation: N old shares become one new share, so the post-event count per pre-event share
        # is new/old after inversion: numerator 1, denominator old/new.
        return ("CONSOLIDATION", "1", _plain(old / new))
    return None


def Decimal_like(text: str):
    from decimal import Decimal

    return Decimal(text)


def _plain(value) -> str:
    """`Decimal` -> the shortest exact plain string (no exponent, no trailing zeros)."""
    text = format(value.normalize(), "f")
    return text


def attested_events() -> List[Attested]:
    """Every price-side / consideration event the committed archive attests, deduplicated by key."""
    best: Dict[Tuple[str, datetime.date, str], Attested] = {}
    unreadable: List[str] = []
    skipped_identity: List[str] = []
    for path in sorted(BRONZE_DIR.glob("*.json")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest = sha256_of(path)
        for row in json.loads(path.read_text(encoding="utf-8")):
            subject = str(row.get("subject") or "").strip()
            parsed = _ratio_from_subject(subject)
            if parsed is None:
                low = subject.lower()
                if any(marker in low for marker in NON_EQUITY_MARKERS):
                    continue
                if any(k in low for k in ("bonus", "split", "sub-division", "consolidat", "demerger")):
                    unreadable.append(f"{relative}: {row.get('isin')} {row.get('exDate')} {subject!r}")
                continue
            action_type, numerator, denominator = parsed
            isin = str(row["isin"])
            if not re.fullmatch(r"IN[A-Z0-9]{10}", isin) or isin == "IN0000000000":
                # NSE sometimes serves a placeholder identity for a corporate action; a row keyed to it
                # can be attached to no series and would fail the identifier contract, so it is named
                # and skipped rather than repaired by guesswork.
                skipped_identity.append(
                    f"{relative}: placeholder ISIN {isin!r} for {row.get('symbol')} {row.get('exDate')} {subject!r}"
                )
                continue
            ex_date = datetime.datetime.strptime(str(row["exDate"]), "%d-%b-%Y").date()
            key = (isin, ex_date, action_type)
            candidate = Attested(
                isin=isin,
                ex_date=ex_date,
                action_type=action_type,
                ratio_numerator=numerator,
                ratio_denominator=denominator,
                subject=subject,
                symbol=str(row.get("symbol") or ""),
                source_artifact=relative,
                source_digest=digest,
            )
            best.setdefault(key, candidate)
    for note in skipped_identity:
        print(f"[INFO] skipped, no attachable identity: {note}")
    if unreadable:
        raise SystemExit(
            f"{len(unreadable)} archive subject line(s) name a price event whose ratio cannot be read; "
            f"nothing is guessed: " + "; ".join(unreadable[:5])
        )
    return [best[key] for key in sorted(best)]


def table_rows() -> List[dict]:
    return [json.loads(line) for line in ACTIONS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


PRICE_SIDE = ("SPLIT", "BONUS", "CONSOLIDATION", "DEMERGER")


def reconcile() -> Tuple[List[Attested], List[dict], List[dict]]:
    """`(missing_from_table, contradicted_or_unattested_rows, attested_rows_present)`."""
    attested = attested_events()
    rows = table_rows()
    live = [
        row for row in rows
        if not row.get("superseded") and row.get("action_type") in PRICE_SIDE
    ]
    present = {
        (str(row["isin"]), datetime.date.fromisoformat(str(row["ex_date"])), str(row["action_type"]))
        for row in live
    }
    missing = [event for event in attested if (event.isin, event.ex_date, event.action_type) not in present]
    attested_keys = {(e.isin, e.ex_date, e.action_type) for e in attested}
    problems: List[dict] = []
    for row in live:
        key = (str(row["isin"]), datetime.date.fromisoformat(str(row["ex_date"])), str(row["action_type"]))
        if key not in attested_keys:
            problems.append(row)
    return missing, problems, [row for row in live if (str(row["isin"]), datetime.date.fromisoformat(str(row["ex_date"])), str(row["action_type"])) in attested_keys]


def report() -> int:
    attested = attested_events()
    missing, problems, present = reconcile()
    print(f"[INFO] Archive-attested price/consideration events: {len(attested)} over {len({a.source_artifact for a in attested})} payload(s)")
    by_type: Dict[str, int] = {}
    for event in attested:
        by_type[event.action_type] = by_type.get(event.action_type, 0) + 1
    print(f"[INFO] By type: {by_type}")
    print(f"[INFO] Table rows applied-eligible and attested: {len(present)}")
    print(f"[INFO] Attested but absent from the table: {len(missing)}")
    for event in missing[:10]:
        print(f"        MISS {event.ex_date} {event.symbol} {event.isin} {event.action_type} {event.ratio_numerator}:{event.ratio_denominator}")
    print(f"[INFO] Table rows with no archive attestation at that ISIN/ex-date: {len(problems)}")
    for row in problems[:15]:
        print(f"        UNATTESTED {row['ex_date']} {row.get('symbol')} {row['isin']} {row['action_type']} ({row.get('circular_ref')})")
    print("OVERALL: reconciled" if not (missing or problems) else "OVERALL: gaps remain")
    return 0 if not (missing or problems) else 1


def write() -> int:
    missing, problems, present = reconcile()
    attested = attested_events()
    by_key = {(e.isin, e.ex_date, e.action_type): e for e in attested}
    appended = 0
    backfilled = 0
    lines = ACTIONS_PATH.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    superseded_refs: Dict[str, str] = {}
    for row in problems:
        superseded_refs[f"{row['isin']}|{row['ex_date']}|{row['action_type']}"] = (
            f"RESTATED_S96_{row['isin']}_{row['ex_date']}"
        )
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        key = f"{row.get('isin')}|{row.get('ex_date')}|{row.get('action_type')}"
        changed = False
        if key in superseded_refs and not row.get("superseded"):
            row["superseded"] = True
            row["restatement_ref"] = superseded_refs[key]
            changed = True
        matched = by_key.get((str(row.get("isin")), datetime.date.fromisoformat(str(row.get("ex_date"))), str(row.get("action_type"))))
        if matched is not None and not row.get("source_digest") and not row.get("superseded"):
            # Attestation metadata backfill only: the ISIN, ex-date and ratio are untouched, and a row
            # without the digest of the payload that attests it may not be applied (§95.7 Ruling 2).
            row["source_artifact"] = matched.source_artifact
            row["source_digest"] = matched.source_digest
            backfilled += 1
            changed = True
        if changed:
            line = json.dumps(row)
        out.append(line)
    for event in missing:
        out.append(json.dumps({
            "isin": event.isin,
            "ex_date": event.ex_date.isoformat(),
            "action_type": event.action_type,
            "ratio_numerator": event.ratio_numerator,
            "ratio_denominator": event.ratio_denominator,
            "circular_ref": "ATTESTED_NSE_CA_S96_" + re.sub(r"[^A-Za-z0-9]", "_", event.symbol or event.isin) + "_" + event.ex_date.strftime("%Y%m%d"),
            "description": f"{event.symbol} {event.action_type} ({event.subject})",
            "symbol": event.symbol,
            "provenance": "CONTENT_IDENTIFIED_ONLY",
            "source_artifact": event.source_artifact,
            "source_digest": event.source_digest,
        }))
        appended += 1
    ACTIONS_PATH.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    digest = sha256_of(ACTIONS_PATH)
    print(
        f"OVERALL: appended {appended} attested row(s), backfilled {backfilled} attestation digest(s), "
        f"superseded {len(superseded_refs)} contradicted/unattested row(s) by restatement; "
        f"corporate_actions.jsonl sha256 {digest[:16]}… ({len(out)} row(s))"
    )
    return 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Capture and reconcile the corporate-action archive")
    parser.add_argument("--capture", action="store_true", help="capture every missing quarter's payload")
    parser.add_argument("--report", action="store_true", help="derive and reconcile, changing nothing")
    parser.add_argument("--write", action="store_true", help="append attested rows and supersede contradicted ones")
    args = parser.parse_args(argv)
    if args.capture:
        return capture()
    if args.report:
        return report()
    if args.write:
        return write()
    parser.error("one of --capture, --report, --write is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
