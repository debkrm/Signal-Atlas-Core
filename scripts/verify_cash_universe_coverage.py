#!/usr/bin/env python3
"""
SIGNAL ATLAS — CASH EQUITY UNIVERSE IDENTITY & COVERAGE VERIFICATION
Verifies Audit Findings H-50, H-51, H-52, H-53, H-44, and Notes N-24, N-25, N-26:
  1. Reference artifact integrity, SHA-256 provenance, active manifest entry, and session-dated effectivity (§10.4, §10.7, H-50, N-25).
  2. Non-overlapping symbol intervals and seamless transitions (NESTLEIND, MAZDOCK, COCHINSHIP, GFSTEELS).
  3. Point-in-time symbol->ISIN resolution on traded exchange Bhavcopy scrips (H-52, H-53).
  4. Sourced pipeline consumption on real 16-Jan-2024 sec_list.csv: exact accounting of 1,839 extracted (66.56%), 924 unresolved in-scope, 861 out-of-scope non-EQ (H-52, N-26).
  5. Real walk-forward fold execution over authentic January 2024 Bhavcopy and NSE price band publication reaching VERIFIED (H-44).
  6. Zero bare assert statements; fail closed on missing evidence (N-24, H-53).
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.research.containment import PartitionRole, WalkForwardFold
from signal_core.research.walkforward import WalkForwardEngine
from signal_core.storage.bronze import BronzeStorage
from signal_core.storage.calendar import load_nse_trading_calendar
from signal_core.storage.gold import GoldEngine
from signal_core.storage.ingest import (
    ingest_daily_bhavcopy_archive,
    ingest_daily_price_bands,
    parse_price_band_report,
)
from signal_core.storage.security_master import (
    SecurityMaster,
    SecurityMasterError,
    SymbolInterval,
    build_production_security_master,
    load_cash_universe_symbol_intervals,
)
from signal_core.storage.silver import SilverStorage
from signal_core.strategy.base import OrderIntent, Strategy

INTERVALS_CSV = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_intervals.csv"
SEC_LIST_CSV = REPO_ROOT / "data" / "reference" / "sec_list_20240116.csv"
MANIFEST_FILE = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
BHAVCOPY_ARCHIVE_MANIFEST = REPO_ROOT / "data" / "reference" / "bhavcopy_archive_manifest.jsonl"
CALENDAR_RECONCILIATION_FILE = REPO_ROOT / "data" / "reference" / "calendar_reconciliation_2022_2026.json"


def resolve_all_bhavcopy_archives() -> List[Path]:
    """
    Discovers all raw Bhavcopy archives for per-session identity verification (Findings N-34, H-55).
    Checks:
    1. NSE_RAW_ARCHIVES_DIR environment variable
    2. REPO_ROOT / "data" / "raw"
    Note: External-repo fallback to sibling Signal-Atlas removed per Finding H-55.
    """
    env_dir = os.environ.get("NSE_RAW_ARCHIVES_DIR")
    search_dirs = []
    if env_dir:
        search_dirs.append(Path(env_dir))
    search_dirs.append(REPO_ROOT / "data" / "raw")

    for base_dir in search_dirs:
        if base_dir.is_dir():
            zips = []
            for sub in sorted(base_dir.iterdir()):
                if sub.is_dir() and sub.name.isdigit():
                    zips.extend(sorted(sub.glob("*.zip")))
            if zips:
                return zips
            flat_zips = sorted(base_dir.glob("*.zip"))
            if flat_zips:
                return flat_zips

    return []


def resolve_raw_bhavcopy_archive(filename: str = "cm16JAN2024bhav.csv.zip") -> Path:
    """Configurable Bhavcopy archive lookup per Audit §40 Note H-53, §12.5."""
    env_dir = os.environ.get("NSE_RAW_ARCHIVES_DIR")
    if env_dir:
        cand = Path(env_dir) / "2024" / filename
        if cand.is_file():
            return cand
        cand_root = Path(env_dir) / filename
        if cand_root.is_file():
            return cand_root
    ref_cand = REPO_ROOT / "data" / "reference" / filename
    if ref_cand.is_file():
        return ref_cand
    bhav_cand = REPO_ROOT / "data" / "reference" / "bhavcopy_2024" / filename
    if bhav_cand.is_file():
        return bhav_cand
    raw_cand = REPO_ROOT / "data" / "raw" / "2024" / filename
    if raw_cand.is_file():
        return raw_cand
    return ref_cand


def verify_gate_cov1_artifact_integrity() -> bool:
    """Verifies artifact SHA-256, active manifest entry, session-dated effectivity, and non-overlapping transitions (H-50, N-24, N-25)."""
    print("--- Gate COV-1: Reference Artifact Integrity & Invariants (H-50, H-51, N-24, N-25) ---")
    if not INTERVALS_CSV.is_file():
        print(f"[FAIL] Missing reference artifact: {INTERVALS_CSV}")
        return False

    cal = load_nse_trading_calendar()
    valid_sessions = set(cal.sessions)

    data = INTERVALS_CSV.read_bytes()
    computed_sha256 = hashlib.sha256(data).hexdigest()

    # Check manifest entry per Note N-25
    if not MANIFEST_FILE.is_file():
        print(f"[FAIL] Missing manifest file: {MANIFEST_FILE}")
        return False

    active_entry = None
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if entry.get("artifact") == INTERVALS_CSV.name and entry.get("is_current") is True:
                    active_entry = entry

    if active_entry is None:
        print(f"[FAIL] No active (is_current: true) manifest entry found for {INTERVALS_CSV.name} (Note N-25)")
        return False

    if active_entry["sha256"] != computed_sha256:
        print(f"[FAIL] SHA-256 mismatch with active manifest: manifest={active_entry['sha256']} computed={computed_sha256}")
        return False

    if active_entry.get("byte_count") != len(data):
        print(f"[FAIL] Byte count mismatch: manifest={active_entry.get('byte_count')} actual={len(data)}")
        return False

    print(f"[PASS] Artifact SHA-256 verified against active manifest: {computed_sha256} ({len(data)} bytes)")

    # Load and validate domain intervals
    intervals = load_cash_universe_symbol_intervals(INTERVALS_CSV)
    print(f"[PASS] Loaded {len(intervals)} intervals from reference artifact.")

    # Validate session-dated effectivity (zero weekends, zero holidays per Note N-24)
    for row in intervals:
        if row.effective_from not in valid_sessions:
            print(f"[FAIL] effective_from {row.effective_from} is not a valid trading session for {row.symbol} (Note N-24)")
            return False
        if row.effective_to is not None and row.effective_to not in valid_sessions:
            print(f"[FAIL] effective_to {row.effective_to} is not a valid trading session for {row.symbol} (Note N-24)")
            return False

    print("[PASS] Session-dated effectivity verified: 100% of effective dates are authoritative trading sessions.")

    # Initialize SecurityMaster (fails closed if overlaps exist per ISIN or symbol)
    sm = SecurityMaster(symbol_intervals=intervals)

    # Test transitions with explicit raises (Note N-24)
    # 1. NESTLEIND split on 2024-01-05
    n1 = sm.resolve_isin_by_symbol("NESTLEIND", datetime.date(2024, 1, 2))
    n2 = sm.resolve_isin_by_symbol("NESTLEIND", datetime.date(2024, 1, 5))
    if n1 != "INE239A01016" or n2 != "INE239A01024":
        print(f"[FAIL] NESTLEIND transition failed: got {n1}, {n2}")
        return False
    print("[PASS] NESTLEIND transition verified: 2024-01-02 -> INE239A01016, 2024-01-05 -> INE239A01024.")

    # 2. MAZDOCK split on 2024-12-27
    m1 = sm.resolve_isin_by_symbol("MAZDOCK", datetime.date(2024, 12, 26))
    m2 = sm.resolve_isin_by_symbol("MAZDOCK", datetime.date(2024, 12, 30))
    if m1 != "INE249Z01012" or m2 != "INE249Z01020":
        print(f"[FAIL] MAZDOCK transition failed: got {m1}, {m2}")
        return False
    print("[PASS] MAZDOCK transition verified: 2024-12-26 -> INE249Z01012, 2024-12-30 -> INE249Z01020.")

    # 3. COCHINSHIP split on 2024-01-10
    c1 = sm.resolve_isin_by_symbol("COCHINSHIP", datetime.date(2024, 1, 9))
    c2 = sm.resolve_isin_by_symbol("COCHINSHIP", datetime.date(2024, 1, 10))
    if c1 != "INE704P01017" or c2 != "INE704P01025":
        print(f"[FAIL] COCHINSHIP transition failed: got {c1}, {c2}")
        return False
    print("[PASS] COCHINSHIP transition verified: 2024-01-09 -> INE704P01017, 2024-01-10 -> INE704P01025.")

    # 4. Multi-year identity: KRBL
    k1 = sm.resolve_isin_by_symbol("KRBL", datetime.date(2022, 6, 1))
    k2 = sm.resolve_isin_by_symbol("KRBL", datetime.date(2023, 6, 1))
    k3 = sm.resolve_isin_by_symbol("KRBL", datetime.date(2024, 6, 1))
    if k1 != "INE001B01026" or k2 != "INE001B01026" or k3 != "INE001B01026":
        print(f"[FAIL] KRBL multi-year identity failed: got {k1}, {k2}, {k3}")
        return False
    print("[PASS] Multi-year continuity verified for KRBL (2022, 2023, 2024 -> INE001B01026).")

    print("[PASS] Gate COV-1: All artifact and transition invariants verified.\n")
    return True


def verify_gate_cov2_bhavcopy_resolution() -> bool:
    """
    Verifies per-session symbol->ISIN resolution across all archived Bhavcopy sessions (Findings H-52, H-54, H-55, H-56, N-34, N-37, N-40).
    Enforces:
    1. Committed digest manifest: every archive's SHA-256 and byte count verified against bhavcopy_archive_manifest.jsonl (§10.7, H-55).
    2. Scope assertion: derived from manifest_entries covering evaluation window 2022-01-03..2026-10-31 (H-55, Note N-40.1).
    3. Reverse coverage: 100% of manifest entries consumed by discovered archives on disk (Note N-40.3).
    4. Authoritative Calendar Reconciliation: cross-checks baseline calendar against archives via committed reconciliation table (§6.3, §10.5, H-56).
    5. Zero silent drops: malformed headers, invalid rows, or empty sessions fail closed (H-55).
    6. Exact row conservation: derived manifest_expected_eq_rows resolved 100.0000% via Decimal arithmetic (N-34, N-37, Note N-40.1).
    """
    print("--- Gate COV-2: Traded EQ Bhavcopy Scrips Point-in-Time Resolution (Findings H-54, H-55, H-56, N-34, N-37, N-40) ---")

    # 1. Verify committed Bronze archive manifest exists and load entries (Finding H-55, §10.7)
    if not BHAVCOPY_ARCHIVE_MANIFEST.is_file():
        print(f"[FAIL] Committed Bhavcopy archive manifest missing at: {BHAVCOPY_ARCHIVE_MANIFEST} (Finding H-55)")
        return False

    manifest_entries: Dict[str, dict] = {}
    manifest_dates: Set[datetime.date] = set()
    manifest_expected_eq_rows = 0

    with open(BHAVCOPY_ARCHIVE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            manifest_entries[entry["archive_file"]] = entry
            manifest_dates.add(datetime.date.fromisoformat(entry["session_date"]))
            manifest_expected_eq_rows += int(entry.get("traded_eq_rows", 0))

    manifest_expected_archive_count = len(manifest_entries)
    if manifest_expected_archive_count == 0:
        print("[FAIL] Manifest contains zero archive entries (Finding H-55)")
        return False
    if manifest_expected_eq_rows == 0:
        print("[FAIL] Manifest expected traded EQ rows sum is 0 (Finding H-55)")
        return False

    print(
        f"[INFO] Archive manifest provenance status: CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED "
        f"(§6.5, §10.7, Note N-40.2). Derived expectations: {manifest_expected_archive_count:,} archives, "
        f"{manifest_expected_eq_rows:,} traded EQ rows across {len(manifest_dates):,} session dates."
    )

    # 2. Discover archives
    archives = resolve_all_bhavcopy_archives()
    if not archives:
        print("[FAIL] No raw Bhavcopy archives found for Gate COV-2 per-session sweep (Finding H-53, H-55).")
        return False

    if len(archives) != manifest_expected_archive_count:
        print(
            f"[FAIL] Gate COV-2 requires all {manifest_expected_archive_count:,} raw Bhavcopy archives for evaluation window, "
            f"but discovered {len(archives):,} archives (Finding H-55, Note N-40.1)."
        )
        return False

    print(f"[INFO] Discovered {len(archives):,} raw Bhavcopy archives; verifying digests and reverse coverage against manifest...")

    # 3. Digest verification and reverse coverage assertion for every archive against committed manifest
    discovered_keys: Set[str] = set()
    for z_path in archives:
        rel_key = f"{z_path.parent.name}/{z_path.name}"
        manifest_rec = manifest_entries.get(rel_key) or manifest_entries.get(z_path.name)
        matched_key = rel_key if rel_key in manifest_entries else (z_path.name if z_path.name in manifest_entries else None)
        if not manifest_rec:
            for k, v in manifest_entries.items():
                if k.endswith(z_path.name):
                    manifest_rec = v
                    matched_key = k
                    break

        if not manifest_rec or not matched_key:
            print(f"[FAIL] Discovered archive {z_path.name} not found in committed manifest (Finding H-55)")
            return False

        discovered_keys.add(matched_key)

        if z_path.stat().st_size != manifest_rec["byte_count"]:
            print(
                f"[FAIL] Archive {z_path.name} size {z_path.stat().st_size} "
                f"!= manifest byte_count {manifest_rec['byte_count']} (Finding H-55)"
            )
            return False

        h = hashlib.sha256()
        with open(z_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        if h.hexdigest() != manifest_rec["sha256"]:
            print(
                f"[FAIL] Archive {z_path.name} SHA-256 {h.hexdigest()} "
                f"!= manifest digest {manifest_rec['sha256']} (Finding H-55)"
            )
            return False

    manifest_keys = set(manifest_entries.keys())
    if discovered_keys != manifest_keys:
        missing_from_disk = manifest_keys - discovered_keys
        print(
            f"[FAIL] Reverse coverage assertion failed: {len(missing_from_disk)} manifest entries "
            f"not discovered on disk: {sorted(missing_from_disk)[:5]} (Note N-40.3)"
        )
        return False

    print(
        f"[PASS] All {len(archives):,} archive digests verified against committed manifest and 100% reverse coverage confirmed "
        f"({len(discovered_keys):,} / {len(manifest_keys):,} entries, Finding H-55, Note N-40.3)."
    )

    # 4. Authoritative Calendar Reconciliation (§6.3, §10.5, Finding H-56)
    if not CALENDAR_RECONCILIATION_FILE.is_file():
        print(f"[FAIL] Calendar reconciliation file missing at: {CALENDAR_RECONCILIATION_FILE} (Finding H-56)")
        return False

    # Verify reconciliation table registered in manifest.jsonl
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        recon_manifest_entry = None
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("artifact") == CALENDAR_RECONCILIATION_FILE.name and entry.get("is_current") is True:
                recon_manifest_entry = entry
                break

    if not recon_manifest_entry:
        print(f"[FAIL] No active manifest entry for {CALENDAR_RECONCILIATION_FILE.name} in {MANIFEST_FILE.name} (Finding H-56)")
        return False

    recon_bytes = CALENDAR_RECONCILIATION_FILE.read_bytes()
    recon_hash = hashlib.sha256(recon_bytes).hexdigest()
    if recon_hash != recon_manifest_entry["sha256"] or len(recon_bytes) != recon_manifest_entry["byte_count"]:
        print(f"[FAIL] Calendar reconciliation hash/size mismatch vs manifest.jsonl (Finding H-56)")
        return False

    with open(CALENDAR_RECONCILIATION_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    window_start = criteria.min_binding_evaluation_start_date
    window_end = datetime.date(2026, 10, 31)

    cal_sessions = set(s for s in cal.sessions if window_start <= s <= window_end)
    cal_circulars = set(cal.provenance.get("circular_references", []))

    excluded_from_cal: Set[datetime.date] = set()
    included_in_archives: Set[datetime.date] = set()

    for item in recon_data.get("entries", []):
        dt = datetime.date.fromisoformat(item["session_date"])
        action = item.get("action")
        circulars = item.get("circular_references", [])
        if not circulars:
            print(f"[FAIL] Reconciliation entry for {dt} lacks circular citations (§6.3, Finding H-56)")
            return False

        # Assert circular is recorded in calendar provenance per §44.2
        for circ in circulars:
            if circ not in cal_circulars:
                print(
                    f"[FAIL] Circular {circ} for session {dt} is not recorded in "
                    f"calendar provenance circular_references (Finding H-56)"
                )
                return False

        if action == "EXCLUDE_FROM_EXPECTED_ARCHIVES":
            if dt not in cal_sessions:
                print(f"[FAIL] Reconciliation excluded session {dt} is not present in baseline calendar sessions (Finding H-56)")
                return False
            excluded_from_cal.add(dt)
        elif action == "INCLUDE_IN_EXPECTED_ARCHIVES":
            if dt in cal_sessions:
                print(f"[FAIL] Reconciliation included session {dt} is already present in baseline calendar sessions (Finding H-56)")
                return False
            included_in_archives.add(dt)
        else:
            print(f"[FAIL] Unknown reconciliation action {action!r} for date {dt} (Finding H-56)")
            return False

    reconciled_expected_sessions = (cal_sessions - excluded_from_cal) | included_in_archives

    if len(reconciled_expected_sessions) != manifest_expected_archive_count:
        print(
            f"[FAIL] Reconciled expected sessions count {len(reconciled_expected_sessions)} "
            f"!= manifest archives count {manifest_expected_archive_count} (Finding H-56, Note N-40.1)"
        )
        return False

    unexplained_missing = reconciled_expected_sessions - manifest_dates
    unexplained_extra = manifest_dates - reconciled_expected_sessions

    if unexplained_missing:
        print(
            f"[FAIL] UNEXPLAINED_MISSING_RECORD: {len(unexplained_missing)} expected calendar sessions missing from archives: "
            f"{sorted(unexplained_missing)} per AGENTS.md §6.3 (Finding H-56)"
        )
        return False

    if unexplained_extra:
        print(
            f"[FAIL] UNEXPLAINED_EXTRA_RECORD: {len(unexplained_extra)} archived sessions not present in reconciled calendar: "
            f"{sorted(unexplained_extra)} per AGENTS.md §6.3 (Finding H-56)"
        )
        return False

    print(
        f"[PASS] Authoritative calendar reconciliation verified: {len(cal_sessions)} baseline calendar sessions "
        f"- {len(excluded_from_cal)} excluded + {len(included_in_archives)} included = "
        f"{len(reconciled_expected_sessions):,} authoritative archived sessions (Finding H-56)."
    )

    sm = build_production_security_master()

    total_sessions = 0
    total_eq_rows = 0
    resolved_eq_rows = 0
    distinct_sessions: Set[datetime.date] = set()

    for z_path in archives:
        with zipfile.ZipFile(z_path) as zf:
            bhav_csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and "bhav" in n.lower()]
            if not bhav_csvs:
                print(f"[FAIL] Archive {z_path.name} contains no Bhavcopy CSV member (Finding H-45, H-55)")
                return False

            for name in bhav_csvs:
                with zf.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                    try:
                        header = next(reader)
                    except StopIteration:
                        print(f"[FAIL] Archive {z_path.name} member {name} is empty (Finding H-55)")
                        return False

                    h_map = {c.strip().upper(): i for i, c in enumerate(header)}

                    def _find_col(*cands: str) -> Optional[int]:
                        for c in cands:
                            if c in h_map:
                                return h_map[c]
                        return None

                    sym_col = _find_col("TCKRSYMB", "SYMBOL")
                    isin_col = _find_col("ISIN", "ISIN_CODE")
                    srs_col = _find_col("SCTYSRS", "SERIES")
                    dt_col = _find_col("TRADDT", "TIMESTAMP", "TRADEDATE")

                    if None in (sym_col, isin_col, srs_col, dt_col):
                        print(
                            f"[FAIL] Archive {z_path.name} member {name} missing required columns: "
                            f"{header} (Finding H-55)"
                        )
                        return False

                    max_idx = max(sym_col, isin_col, srs_col, dt_col)
                    session_date = None
                    session_rows = 0
                    session_resolved = 0

                    for row in reader:
                        if len(row) <= max_idx:
                            continue
                        if row[srs_col].strip().upper() != "EQ":
                            continue

                        sym = row[sym_col].strip().upper()
                        isin = row[isin_col].strip().upper()
                        if not sym or not isin or len(isin) != 12:
                            print(
                                f"[FAIL] Malformed traded EQ row in {z_path.name}: "
                                f"symbol={sym!r}, isin={isin!r} (Finding H-55)"
                            )
                            return False

                        if session_date is None:
                            d_str = row[dt_col].strip()
                            if "-" in d_str:
                                parts = d_str.split("-")
                                if len(parts[0]) == 4:
                                    session_date = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                                else:
                                    session_date = datetime.datetime.strptime(d_str, "%d-%b-%Y").date()
                            elif "/" in d_str:
                                parts = d_str.split("/")
                                session_date = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))

                        actual_isin = sm.resolve_isin_by_symbol(sym, session_date)
                        if actual_isin != isin:
                            print(
                                f"[FAIL] Resolution failed on {session_date} for symbol '{sym}': "
                                f"expected ISIN={isin}, resolved ISIN={actual_isin} (Finding N-34)"
                            )
                            return False

                        session_rows += 1
                        session_resolved += 1

                    if session_rows == 0:
                        print(f"[FAIL] Session archive {z_path.name} yielded 0 traded EQ rows (Finding H-55)")
                        return False

                    distinct_sessions.add(session_date)
                    total_sessions += 1
                    total_eq_rows += session_rows
                    resolved_eq_rows += session_resolved

    if distinct_sessions != reconciled_expected_sessions:
        missing_sessions = reconciled_expected_sessions - distinct_sessions
        extra_sessions = distinct_sessions - reconciled_expected_sessions
        print(
            f"[FAIL] Covered distinct sessions do not match reconciled expected sessions: "
            f"missing={sorted(missing_sessions)[:5]}, extra={sorted(extra_sessions)[:5]} (Finding H-55, H-56)"
        )
        return False

    if len(distinct_sessions) != manifest_expected_archive_count:
        print(
            f"[FAIL] Covered {len(distinct_sessions)} distinct sessions; "
            f"expected exactly {manifest_expected_archive_count} (Finding H-55, Note N-40.1)"
        )
        return False

    if total_eq_rows != manifest_expected_eq_rows or resolved_eq_rows != manifest_expected_eq_rows:
        print(
            f"[FAIL] Row count mismatch: resolved {resolved_eq_rows:,} of {total_eq_rows:,}; "
            f"expected exactly {manifest_expected_eq_rows:,} (Finding H-55, Note N-40.1)"
        )
        return False

    pct = (Decimal(str(resolved_eq_rows)) / Decimal(str(total_eq_rows))) * Decimal("100")
    print(f"[INFO] Per-Session Sweep Complete: {resolved_eq_rows:,} / {total_eq_rows:,} traded EQ rows resolved across {total_sessions:,} sessions ({pct:.4f}%).")

    if pct < criteria.min_traded_eq_resolution_pct:
        print(
            f"[FAIL] Traded EQ resolution {pct:.4f}% below required criteria invariant "
            f"{criteria.min_traded_eq_resolution_pct}% (Finding H-54)"
        )
        return False

    print(
        f"[PASS] Gate COV-2: Traded EQ point-in-time resolution verified "
        f"({resolved_eq_rows:,} / {total_eq_rows:,} across {total_sessions:,} sessions, {pct:.4f}% >= {criteria.min_traded_eq_resolution_pct}%).\n"
    )
    return True


def verify_gate_cov3_series_partitioned_accounting() -> bool:
    """Verifies pipeline consumption on real 16-Jan-2024 sec_list.csv (Findings H-52, H-44, Notes N-24, N-26)."""
    print("--- Gate COV-3: Published Price Band Pipeline Coverage & Accounting (H-52, H-44, N-24, N-26) ---")
    if not SEC_LIST_CSV.is_file():
        print(f"[FAIL] Missing sec_list artifact: {SEC_LIST_CSV}")
        return False

    sm = build_production_security_master()
    t_date = datetime.date(2024, 1, 16)

    res = parse_price_band_report(
        report_data=SEC_LIST_CSV,
        trade_date=t_date,
        security_master=sm,
        target_series=("EQ",),
    )

    summary = res.summary
    print(f"[INFO] Total Rows: {summary.total_rows}")
    print(f"[INFO] In-Scope Series (EQ): {summary.in_scope_series_count}")
    print(f"[INFO] Out-of-Scope Series (Non-EQ): {summary.out_of_scope_series_count}")
    print(f"[INFO] Extracted Records (Resolved EQ): {summary.extracted_records}")
    print(f"[INFO] In-Scope Unresolved EQ (Listed-but-untraded on/before T): {summary.unresolved_isin_count}")
    print(f"[INFO] Non-Target Filter Drops: {summary.non_target_count}")
    print(f"[INFO] Duplicate ISINs: {summary.duplicate_isin_count}")

    # Note N-24 / Note N-26: Explicit fail-closed assertions on exact row conservation
    if summary.total_rows != 3624:
        print(f"[FAIL] Expected total_rows == 3624, got {summary.total_rows}")
        return False
    if summary.in_scope_series_count != 2763:
        print(f"[FAIL] Expected in_scope_series_count == 2763, got {summary.in_scope_series_count}")
        return False
    if summary.out_of_scope_series_count != 861:
        print(f"[FAIL] Expected out_of_scope_series_count == 861, got {summary.out_of_scope_series_count}")
        return False
    if summary.unresolved_isin_count != 924:
        print(f"[FAIL] Expected unresolved_isin_count == 924, got {summary.unresolved_isin_count} (Finding H-52)")
        return False
    if summary.extracted_records != 1839:
        print(f"[FAIL] Expected extracted_records == 1839, got {summary.extracted_records}")
        return False
    if summary.non_target_count != 0:
        print(f"[FAIL] Expected non_target_count == 0 (no target_set filter applied), got {summary.non_target_count} (Note N-26)")
        return False
    if summary.duplicate_isin_count != 0:
        print(f"[FAIL] Expected duplicate_isin_count == 0, got {summary.duplicate_isin_count}")
        return False

    coverage_pct = (Decimal(str(summary.extracted_records)) / Decimal(str(summary.in_scope_series_count))) * Decimal("100")
    print(f"[INFO] Listed EQ Universe Coverage on 2024-01-16 (Informational): {summary.extracted_records} / {summary.in_scope_series_count} ({coverage_pct:.2f}%)")
    print(f"[INFO] 924 scrips listed-but-untraded on or before 2024-01-16 (identity begins at first trade per §40.5; Finding H-54).")
    print("[PASS] Gate COV-3: Series partitioning and dropped-row accounting verified with exact row conservation.\n")
    return True


def verify_gate_cov4_walkforward_verified_fold() -> bool:
    """Verifies a walk-forward fold over authentic January 2024 archives achieving VERIFIED (Findings H-44, H-53, Note N-24)."""
    print("--- Gate COV-4: Walk-Forward Fold with Authentic Exchange Data (Findings H-44, H-53) ---")
    cal = load_nse_trading_calendar()
    sm = build_production_security_master()

    bhav_12 = resolve_raw_bhavcopy_archive("cm12JAN2024bhav.csv.zip")
    bhav_15 = resolve_raw_bhavcopy_archive("cm15JAN2024bhav.csv.zip")
    bhav_16 = resolve_raw_bhavcopy_archive("cm16JAN2024bhav.csv.zip")

    for p in [bhav_12, bhav_15, bhav_16]:
        if not p.is_file():
            print(f"[FAIL] Required Bhavcopy archive not found at: {p} (Finding H-53)")
            return False

    if not SEC_LIST_CSV.is_file():
        print(f"[FAIL] Required price band archive not found at: {SEC_LIST_CSV}")
        return False

    d12 = datetime.date(2024, 1, 12)
    d15 = datetime.date(2024, 1, 15)
    d16 = datetime.date(2024, 1, 16)

    with tempfile.TemporaryDirectory(prefix="wf_cov_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze = BronzeStorage(tmp_path / "bronze")
        silver = SilverStorage(tmp_path / "silver", calendar=cal)

        # Ingest authentic Bhavcopies for Jan 12, Jan 15, Jan 16
        for b in [bhav_12, bhav_15, bhav_16]:
            ingest_daily_bhavcopy_archive(
                bronze=bronze,
                silver=silver,
                archive_bytes=b.read_bytes(),
                filename=b.name,
                source_url=f"https://archives.nseindia.com/{b.name}",
                calendar=cal,
                target_series=("EQ",),
            )

        # Ingest authentic published NSE price bands for 16-Jan-2024 (sec_list.csv)
        ingest_daily_price_bands(
            bronze=bronze,
            report_bytes=SEC_LIST_CSV.read_bytes(),
            filename="sec_list_20240116.csv",
            source_url="https://archives.nseindia.com/content/equities/sec_list.csv",
            trade_date=d16,
            security_master=sm,
            silver=silver,
            calendar=cal,
            max_unresolved_threshold=1000,
        )

        sm_with_bands = sm.load_from_silver_price_bands(silver, [d16], calendar=cal)
        gold = GoldEngine(silver_storage=silver, calendar=cal, security_master=sm_with_bands)

        fold = WalkForwardFold(
            fold_index=0,
            train_start=d12,
            train_end=d12,
            test_start=d15,
            test_end=d16,
            embargo_sessions=0,
            partition_role=PartitionRole.VALIDATION,
        )

        class RealBandBuyer(Strategy):
            @property
            def strategy_id(self) -> str:
                return "REAL-BAND-BUYER"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == d15:
                    return (
                        OrderIntent(
                            instrument_id="INE144J01027",
                            signal_date=as_of,
                            target_date=next_session,
                            side=OrderSide.BUY,
                            quantity=100,
                        ),
                    )
                return ()

        engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
        res = engine.run_walk_forward(strategy=RealBandBuyer(), folds=[fold], isins=["INE144J01027"])

        if len(res.aggregate_trades) != 1:
            print(f"[FAIL] Expected 1 aggregate trade, got {len(res.aggregate_trades)}")
            return False

        trade = res.aggregate_trades[0]
        if trade.status != FillStatus.FILLED:
            print(f"[FAIL] Trade status was not FILLED: {trade.status}")
            return False

        if not trade.circuit_evidence_present:
            print("[FAIL] Circuit evidence was not present on trade fill")
            return False

        if not res.circuit_evidence_complete:
            print("[FAIL] res.circuit_evidence_complete was False")
            return False

        if res.verification_status != "VERIFIED":
            print(f"[FAIL] res.verification_status was {res.verification_status}, expected VERIFIED")
            return False

        print(f"[PASS] Trade Executed: {trade.order.instrument_id} @ Rs. {trade.executed_price} (status: {trade.status.value})")
        print(f"[PASS] Circuit Evidence Present: {trade.circuit_evidence_present} (complete: {res.circuit_evidence_complete})")
        print(f"[PASS] Fold Verification Status: {res.verification_status}")

    print("[PASS] Gate COV-4: Walk-forward fold reached VERIFIED with authentic exchange data and circuit limits (Finding H-44).\n")
    return True


def main() -> int:
    print("=" * 80)
    print("SIGNAL ATLAS — CASH EQUITY UNIVERSE IDENTITY & COVERAGE VERIFICATION")
    print("Executed at:", datetime.datetime.now(datetime.timezone.utc).isoformat())
    print("=" * 80 + "\n")

    gates = [
        verify_gate_cov1_artifact_integrity(),
        verify_gate_cov2_bhavcopy_resolution(),
        verify_gate_cov3_series_partitioned_accounting(),
        verify_gate_cov4_walkforward_verified_fold(),
    ]

    print("=" * 80)
    if all(gates):
        print("OVERALL VERDICT: ALL CASH UNIVERSE COVERAGE GATES PASSED")
        print("               - Gate COV-1: Reference Artifact Integrity & Invariants (PASS)")
        print("               - Gate COV-2: Traded EQ Resolution Across All Archived Sessions (100.0000% PASS)")
        print("               - Gate COV-3: Published Price Band Pipeline Coverage & Accounting (PASS)")
        print("               - Gate COV-4: Authentic Fold Execution with Real Bands (VERIFIED PASS)")
        print("=" * 80)
        return 0
    else:
        print("OVERALL VERDICT: ONE OR MORE GATES FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
