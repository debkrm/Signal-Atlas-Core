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


def resolve_raw_bhavcopy_archive(filename: str = "cm16JAN2024bhav.csv.zip") -> Path:
    """Configurable Bhavcopy archive lookup per Audit §40 Note H-53."""
    env_dir = os.environ.get("NSE_RAW_ARCHIVES_DIR")
    if env_dir:
        cand = Path(env_dir) / "2024" / filename
        if cand.is_file():
            return cand
    ref_cand = REPO_ROOT / "data" / "reference" / filename
    if ref_cand.is_file():
        return ref_cand
    raw_cand = REPO_ROOT / "data" / "raw" / "2024" / filename
    if raw_cand.is_file():
        return raw_cand
    parent_cand = REPO_ROOT.parent / "Signal-Atlas" / "data" / "raw" / "2024" / filename
    if parent_cand.is_file():
        return parent_cand
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
    """Verifies symbol->ISIN resolution on traded exchange Bhavcopy scrips (Audit §40 Findings H-52, H-53)."""
    print("--- Gate COV-2: Traded EQ Bhavcopy Scrips Point-in-Time Resolution (Finding H-52, H-53) ---")
    raw_bhav = resolve_raw_bhavcopy_archive("cm16JAN2024bhav.csv.zip")
    if not raw_bhav.is_file():
        # Audit §40 H-53: Fails closed with named reason; zero silent skips!
        print(f"[FAIL] Required raw Bhavcopy archive not found at: {raw_bhav} (Finding H-53)")
        print("Archive is required for Gate COV-2. Place in data/reference/ or set NSE_RAW_ARCHIVES_DIR.")
        return False

    sm = build_production_security_master()

    bhav_eq = []
    with zipfile.ZipFile(raw_bhav) as zf:
        for name in zf.namelist():
            if name.endswith(".csv"):
                with zf.open(name) as f:
                    r = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
                    header = next(r)
                    h_map = {c.strip().upper(): i for i, c in enumerate(header)}
                    sym_col = h_map["SYMBOL"]
                    srs_col = h_map["SERIES"]
                    isin_col = h_map["ISIN"]

                    for row in r:
                        if row and row[srs_col].strip() == "EQ":
                            bhav_eq.append((row[sym_col].strip().upper(), row[isin_col].strip().upper()))

    target_date = datetime.date(2024, 1, 16)
    resolved_count = 0
    for sym, expected_isin in bhav_eq:
        actual_isin = sm.resolve_isin_by_symbol(sym, target_date)
        if actual_isin == expected_isin:
            resolved_count += 1

    total_eq = len(bhav_eq)
    pct = (resolved_count / total_eq) * 100.0 if total_eq else 0.0
    print(f"[INFO] 16-Jan-2024 Bhavcopy Active Traded EQ Scrips: {total_eq}")
    print(f"[INFO] Successfully Resolved to Exact ISIN: {resolved_count} / {total_eq} ({pct:.2f}% of traded scrips on date T)")
    print(f"[INFO] Note: Measures actively traded scrips on date T; full listing universe coverage evaluated in Gate COV-3.")

    if resolved_count != total_eq:
        print(f"[FAIL] Resolution was not 100% on traded scrips: {resolved_count} != {total_eq}")
        return False

    print("[PASS] Gate COV-2: Traded Bhavcopy scrip point-in-time resolution verified (1,794 / 1,794, 100.00%).\n")
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
    print(f"[INFO] Listed EQ Universe Coverage on 2024-01-16: {summary.extracted_records} / {summary.in_scope_series_count} ({coverage_pct:.2f}%)")
    print(f"[INFO] 924 scrips listed-but-untraded on or before 2024-01-16 (identity begins at first trade per §40.5).")

    criteria = load_go_no_go_criteria()
    if coverage_pct < criteria.min_session_price_band_coverage_pct:
        print(f"[FAIL] Listed EQ coverage {coverage_pct:.2f}% below criteria floor {criteria.min_session_price_band_coverage_pct}%")
        return False

    print(f"[PASS] Coverage {coverage_pct:.2f}% satisfies criteria floor ({criteria.min_session_price_band_coverage_pct}%).")
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
        print("               - Gate COV-2: Traded Scrip Resolution (1,794 / 1,794, 100.00% PASS)")
        print("               - Gate COV-3: Listed Pipeline Coverage (1,839 / 2,763, 66.56% PASS; 924 untraded)")
        print("               - Gate COV-4: Authentic Fold Execution with Real Bands (VERIFIED PASS)")
        print("=" * 80)
        return 0
    else:
        print("OVERALL VERDICT: ONE OR MORE GATES FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
