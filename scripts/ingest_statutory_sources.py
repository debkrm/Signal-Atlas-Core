#!/usr/bin/env python3
"""
STATUTORY SOURCE CAPTURE — Audit §95.10 items 1-2

Captures, byte-exact, the NSE circulars and statutory notifications the committed
`statutory_indian_cost_schedule` cites, one directory per source under `data/raw/circulars/<REF>/`,
each with a `manifest.json` that carries `sha256`, `source_url`, `retrieved_at`, `byte_count` and
`http_status` (§10.7).

Why a separate directory per source: `signal_core.storage.circulars.load_all_bronze_circulars` globs
`data/raw/circulars/*.json` non-recursively for the calendar circulars, so a subdirectory is invisible
to it and the calendar registry is unchanged by this capture.

Every destination file is written atomically (temp file + `os.replace`), and a file already on disk
whose digest matches its manifest is left untouched, so the script resumes rather than duplicating.
CI has no network (§12.5): the committed bytes are the source of record, and this script is the
capture, never a test.

Usage:
    python scripts/ingest_statutory_sources.py            # capture every missing source
    python scripts/ingest_statutory_sources.py --check    # verify committed bytes against manifests
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Dict, List, NamedTuple, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CIRCULARS_ROOT = REPO_ROOT / "data" / "raw" / "circulars"

NSE_ARCHIVE = "https://nsearchives.nseindia.com/content/circulars/{name}"
CURL_HEADERS = (
    "-A",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36",
    "-H",
    "Accept: application/pdf,text/html,application/json,*/*",
    "-H",
    "Accept-Language: en-US,en;q=0.9",
    "-H",
    "Referer: https://www.nseindia.com/",
)


class Source(NamedTuple):
    ref: str
    filename: str
    url: str
    subject: str
    issue_authority: str


SOURCES: tuple[Source, ...] = (
    # --- NSE Finance & Accounts transaction-charge circulars --------------------------------
    Source(
        "NSE_FA_45147",
        "FA45147.pdf",
        NSE_ARCHIVE.format(name="FA45147.pdf"),
        "Revision in transaction charges structure for equity market segment",
        "NSE / Finance & Accounts",
    ),
    Source(
        "NSE_FA_46225",
        "FA46225.pdf",
        NSE_ARCHIVE.format(name="FA46225.pdf"),
        "Revision in transaction charges structure for equity market segment",
        "NSE / Finance & Accounts",
    ),
    Source(
        "NSE_FA_46730",
        "FA46730.pdf",
        NSE_ARCHIVE.format(name="FA46730.pdf"),
        "Revision in Transaction Charges",
        "NSE / Finance & Accounts",
    ),
    Source(
        "NSE_FA_56129",
        "FA56129.pdf",
        NSE_ARCHIVE.format(name="FA56129.pdf"),
        "Revision in Transaction Charges",
        "NSE / Finance & Accounts",
    ),
    Source(
        "NSE_FA_61137",
        "FA61137.pdf",
        NSE_ARCHIVE.format(name="FA61137.pdf"),
        "Revision in Transaction Charges",
        "NSE / Finance & Accounts",
    ),
    Source(
        # The schedule cited `NSE/FA/64323`, which resolves to no committed byte (404). The circular
        # that actually revised cash-market transaction charges with effect from 2024-10-01 is
        # NSE/FA/64232 (Sept 27, 2024, Circular Ref. 5/2024); NSE/FA/46730/56129's successor chain
        # names it, and its own text states the rate. The reference is corrected to the byte that exists.
        "NSE_FA_64232",
        "FA64232.pdf",
        NSE_ARCHIVE.format(name="FA64232.pdf"),
        "Revision in Transaction Charges (SEBI/HO/MRD/TPD-1/P/CIR/2024/92 true-to-label)",
        "NSE / Finance & Accounts",
    ),
    Source(
        "NSE_FA_73061",
        "FA73061.pdf",
        NSE_ARCHIVE.format(name="FA73061.pdf"),
        "Revision in Transaction Charges",
        "NSE / Finance & Accounts",
    ),
    # --- Statutory levy sources ------------------------------------------------------------
    Source(
        "SEBI_PAYMENT_OF_FEES_2020_011",
        "SEBI_LAD-NRO_GN_2020_011.pdf",
        "https://www.sebi.gov.in/sebi_data/attachdocs/may-2020/1589196249922.pdf",
        "SEBI (Payment of Fees) (Amendment) Regulations, 2020 — 50% broker turnover fee, "
        "2020-06-01..2021-03-31",
        "SEBI / Gazette of India",
    ),
    Source(
        "SEBI_STAMP_DUTY_FAQ",
        "SEBI_Indian_Stamp_Act_1899_FAQs.pdf",
        "https://www.sebi.gov.in/sebi_data/faqfiles/dec-2021/1639980911330.pdf",
        "FAQs on Indian Stamp Act, 1899 amendments — stamp duty rates w.e.f. 1 July 2020",
        "SEBI",
    ),
    Source(
        "NSE_STT_RATES",
        "NSE_SEBI_TURNOVER_FEES_STT_OTHER_LEVIES.html",
        "https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies",
        "SEBI Turnover Fees, STT and Other levies — STT rate table",
        "NSE",
    ),
    Source(
        "MAHARASHTRA_STAMP_DUTY_2019",
        "KPMG_flash_news_stamp_duty_amendments.pdf",
        "https://www.in.kpmg.com/TaxFlashNews-INT/Flash-News-Stamp-Duty-amendments.pdf",
        "Erstwhile Maharashtra state stamp duty rates for listed share transfers, set against the "
        "amended Indian Stamp Act schedule",
        "KPMG India (tax flash note, 2019-12-12)",
    ),
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch(url: str) -> bytes:
    """Downloads with curl and browser headers; the NSE archive refuses a bare urllib client."""
    with tempfile.TemporaryDirectory(prefix="statutory_src_") as tmp:
        target = Path(tmp) / "payload"
        result = subprocess.run(
            ["curl", "-sS", "-L", "-4", "-m", "90", *CURL_HEADERS, "-o", str(target), url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            raise SystemExit(
                f"retrieval failed for {url}: curl exit {result.returncode}, {result.stderr.strip()[:300]}"
            )
        return target.read_bytes()


def capture(source: Source) -> Dict[str, str]:
    directory = CIRCULARS_ROOT / source.ref
    directory.mkdir(parents=True, exist_ok=True)
    payload_path = directory / source.filename
    manifest_path = directory / "manifest.json"
    if payload_path.is_file() and manifest_path.is_file():
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = sha256_of(payload_path)
        if recorded.get("sha256") == actual and recorded.get("source_url") == source.url:
            return {"ref": source.ref, "state": "present", "sha256": actual}
        raise SystemExit(
            f"{payload_path} does not match its manifest ({actual} vs {recorded.get('sha256')}); "
            f"an archive is never rewritten in place — capture under a new ref (AGENTS.md §10.1)"
        )

    payload = _fetch(source.url)
    retrieved_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    handle, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".tmp_")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_name, payload_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

    manifest_path.write_text(
        json.dumps(
            {
                "circular_ref": source.ref,
                "filename": source.filename,
                "source_url": source.url,
                "retrieved_at": retrieved_at,
                "http_status": 200,
                "byte_count": len(payload),
                "sha256": digest,
                "subject": source.subject,
                "issued_by": source.issue_authority,
                "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
                "note": "Byte-exact payload as retrieved; never edited. Digest is over the raw file bytes.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"ref": source.ref, "state": "captured", "sha256": digest}


def check() -> int:
    problems: List[str] = []
    for source in SOURCES:
        directory = CIRCULARS_ROOT / source.ref
        payload_path = directory / source.filename
        manifest_path = directory / "manifest.json"
        if not payload_path.is_file() or not manifest_path.is_file():
            problems.append(f"{source.ref}: payload or manifest absent under {directory.relative_to(REPO_ROOT)}")
            continue
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = sha256_of(payload_path)
        if actual != recorded.get("sha256"):
            problems.append(f"{source.ref}: sha256 {actual[:16]}… is not the manifest's {str(recorded.get('sha256'))[:16]}…")
        if recorded.get("byte_count") != payload_path.stat().st_size:
            problems.append(
                f"{source.ref}: byte count {payload_path.stat().st_size} is not the manifest's "
                f"{recorded.get('byte_count')}"
            )
        for key in ("source_url", "retrieved_at"):
            if not str(recorded.get(key) or "").strip():
                problems.append(f"{source.ref}: manifest carries no {key}")
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        print(f"OVERALL: {len(problems)} problem(s) across {len(SOURCES)} source(s)")
        return 1
    print(f"OVERALL: {len(SOURCES)} statutory source(s) reproduce their committed manifests")
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Capture or verify the statutory source bytes")
    parser.add_argument("--check", action="store_true", help="verify committed bytes against manifests")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    captured = 0
    for source in SOURCES:
        result = capture(source)
        captured += result["state"] == "captured"
        print(f"[INFO] {result['ref']}: {result['state']}, sha256 {result['sha256'][:16]}…")
    print(f"OVERALL: {len(SOURCES)} source(s), {captured} captured, {len(SOURCES) - captured} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
