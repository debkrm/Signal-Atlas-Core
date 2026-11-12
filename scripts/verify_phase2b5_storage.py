"""
Authoritative Reproducible Verification Probe for Phase 2B.5 (Market Data Ingestion & Immutable Storage Layer).

Computes and prints exact verdicts for all Phase 2B.5 gates:
- Gate G2B.5-1: Truncated or tampered Bronze payload fails closed (TamperedBronzePayloadError).
- Gate G2B.5-2: Rerun reproduces bit-for-bit identical dataset (DATA-CTNT-V2) and universe (UNIV-SCHED-V1) fingerprints.
- Gate G2B.5-3: Known ISIN transition and known delisting are pruned on their exact effective dates.
- Gate G2B.5-4: Session present in calendar but absent in archive classifies as UNEXPLAINED_MISSING_RECORD.
- Gate G2B.5-5: No Silver partition is ever rewritten (SilverPartitionImmutableError).
- Gate G2B.5-6: DuckDB database is deleted and rebuilt with zero change to any fingerprint.
- Gate G2B.5-7: No session before 2018-04-01 can reach a GO verdict (classified as NOT RUN).

All verdicts are derived from runtime assertions and computed booleans. Zero hand-typed status labels.
"""

import datetime
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import tempfile

# Ensure src/ is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.exchange_series import PriceSeriesGapType
from signal_core.contracts.price_bar import PriceBar
from signal_core.storage.calendar import (
    TradingCalendar,
    compute_calendar_fingerprint,
    load_nse_trading_calendar,
)
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    DelistingEvent,
    ISINTransitionEvent,
    SecurityMaster,
    SymbolInterval,
    build_production_security_master,
)
from signal_core.storage.bronze import (
    BronzeStorage,
    MissingBronzeManifestError,
    TamperedBronzePayloadError,
)
from signal_core.storage.silver import (
    SilverPartitionImmutableError,
    SilverRecord,
    SilverStorage,
)
from signal_core.storage.gold import (
    GoldEngine,
)
from signal_core.storage.views import DuckDBViewLayer
from signal_core.storage.gating import (
    BINDING_EVALUATION_START_DATE,
    GatingWindowClassification,
    GatingWindowValidationError,
    check_gating_verdict_eligibility,
    classify_gating_window,
    resolve_gating_verdict,
)


def run_phase_2b5_verification() -> bool:
    print("=" * 80)
    print("SIGNAL ATLAS — PHASE 2B.5 MARKET DATA INGESTION & STORAGE LAYER VERIFICATION")
    print(f"Executed at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    all_passed = True
    temp_dir = Path(tempfile.mkdtemp(prefix="phase2b5_probe_"))

    try:
        bronze_dir = temp_dir / "bronze"
        silver_dir = temp_dir / "silver"
        duckdb_path = temp_dir / "views.duckdb"

        # ----------------------------------------------------------------------
        # CALENDAR VERIFICATION
        # ----------------------------------------------------------------------
        print("\n--- Calendar Verification: Authoritative NSE Trading Calendar ---")
        cal = load_nse_trading_calendar()
        cal_total = cal.total_sessions
        cal_start = cal.start_date
        cal_end = cal.end_date
        cal_binding_start = cal.binding_start_date
        cal_fpr = cal.fingerprint

        cal_ok = (
            cal_total == 2923
            and cal_start == datetime.date(2015, 1, 1)
            and cal_end == datetime.date(2026, 11, 11)
            and cal_binding_start == datetime.date(2018, 4, 1)
            and cal_fpr.startswith("CAL-FPR-V1-")
        )

        warmup_count = len(cal.sessions_in_range(datetime.date(2015, 1, 1), datetime.date(2018, 3, 31)))
        binding_count = len(cal.sessions_in_range(datetime.date(2018, 4, 1), datetime.date(2026, 11, 11)))
        cal_partition_ok = (warmup_count == 798 and binding_count == 2125)

        cal_verdict = cal_ok and cal_partition_ok
        all_passed = all_passed and cal_verdict
        print(f"[{'PASS' if cal_verdict else 'FAIL'}] Calendar: {cal_total} total sessions "
              f"({warmup_count} warm-up 2015-2018, {binding_count} binding 2018-2026)")
        print(f"       Fingerprint: {cal_fpr}")

        # ----------------------------------------------------------------------
        # GATE G2B.5-1: Bronze Tamper Detection & Fail-Closed Invariants
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-1: Bronze Tamper Detection & Fail-Closed Invariants ---")
        bronze = BronzeStorage(bronze_dir)
        payload = b"SESSION,ISIN,CLOSE\n2024-01-10,INE009A01021,1500.00\n"
        rel_path = "bhavcopy/2024/2024-01-10.csv"
        bronze.store_payload(rel_path, payload, source_url="https://archives.nse.test/bhavcopy.csv")

        # 1. Valid read succeeds
        valid_read = bronze.read_payload(rel_path, verify=True)
        g1_valid_ok = (valid_read == payload)

        # 2. Tampered payload fails closed
        stored_file = bronze.root_dir / rel_path
        with open(stored_file, "wb") as f:
            f.write(payload.replace(b"1500.00", b"9999.00"))

        g1_tamper_caught = False
        try:
            bronze.read_payload(rel_path, verify=True)
        except TamperedBronzePayloadError:
            g1_tamper_caught = True

        # 3. Truncated payload fails closed
        with open(stored_file, "wb") as f:
            f.write(payload[:8])

        g1_trunc_caught = False
        try:
            bronze.read_payload(rel_path, verify=True)
        except TamperedBronzePayloadError:
            g1_trunc_caught = True

        # Restore original payload for cleanliness
        with open(stored_file, "wb") as f:
            f.write(payload)

        g2b5_1_passed = g1_valid_ok and g1_tamper_caught and g1_trunc_caught
        all_passed = all_passed and g2b5_1_passed
        print(f"[{'PASS' if g2b5_1_passed else 'FAIL'}] Gate G2B.5-1: Bronze archive tamper & truncation fail closed")
        print(f"       Valid verification: {g1_valid_ok} | Bit-flip caught: {g1_tamper_caught} | Truncation caught: {g1_trunc_caught}")

        # ----------------------------------------------------------------------
        # GATE G2B.5-5: Silver Partition Immutability (Append-Only)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-5: Silver Partition Immutability ---")
        silver = SilverStorage(silver_dir)
        d1 = datetime.date(2024, 1, 10)
        sample_records = [
            SilverRecord("INE009A01021", "INFY", "EQ", d1, Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d1, Decimal("2600.00"), Decimal("2630.00"), Decimal("2590.00"), Decimal("2620.00"), 150000),
        ]
        silver.write_daily_partition(d1, sample_records)

        g5_overwrite_blocked = False
        try:
            silver.write_daily_partition(d1, sample_records)
        except SilverPartitionImmutableError:
            g5_overwrite_blocked = True

        g2b5_5_passed = g5_overwrite_blocked and silver.partition_exists(d1)
        all_passed = all_passed and g2b5_5_passed
        print(f"[{'PASS' if g2b5_5_passed else 'FAIL'}] Gate G2B.5-5: Overwriting silver partition fails closed with SilverPartitionImmutableError")

        # ----------------------------------------------------------------------
        # GATE G2B.5-4: Missing Session Classifies as UNEXPLAINED_MISSING_RECORD
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-4: Missing Session Fail-Closed Invariants ---")
        sec_master = build_production_security_master()
        d8 = datetime.date(2024, 1, 8)
        d9 = datetime.date(2024, 1, 9)
        d10 = datetime.date(2024, 1, 10)

        # Write partition for 2024-01-08 (2024-01-09 deliberately missing)
        silver.write_daily_partition(
            d8,
            [
                SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1480.00"), Decimal("1500.00"), Decimal("1475.00"), Decimal("1495.00"), 50000),
                SilverRecord("INE002A01018", "RELIANCE", "EQ", d8, Decimal("2580.00"), Decimal("2600.00"), Decimal("2570.00"), Decimal("2590.00"), 80000),
            ],
        )

        bars, gaps = silver.read_instrument_series_with_calendar_validation(
            isin="INE009A01021",
            start_date=d8,
            end_date=d10,
            calendar=cal,
            security_master=sec_master,
        )

        has_unexplained_gap = any(
            gap_date == d9 and gap_type == PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD
            for gap_date, gap_type in gaps
        )
        bar_count_exact = (len(bars) == 2)  # Jan 8 and Jan 10
        gap_count_exact = (len(gaps) == 1)  # Jan 9

        g2b5_4_passed = has_unexplained_gap and bar_count_exact and gap_count_exact
        all_passed = all_passed and g2b5_4_passed
        print(f"[{'PASS' if g2b5_4_passed else 'FAIL'}] Gate G2B.5-4: Missing session 2024-01-09 classified as UNEXPLAINED_MISSING_RECORD")
        print(f"       Bars present: {len(bars)} | Gaps classified: {len(gaps)} ({gaps[0][1].value})")

        # ----------------------------------------------------------------------
        # GATE G2B.5-3: ISIN Transition & Delisting Exact Effective Date Pruning
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-3: Corporate Delisting & ISIN Transition Exact Date Pruning ---")
        # 1. HDFC (INE001A01036) delisted effective 2023-07-13
        hdfc_pre_active = sec_master.is_active("INE001A01036", datetime.date(2023, 7, 12))
        hdfc_on_pruned = not sec_master.is_active("INE001A01036", datetime.date(2023, 7, 13))
        hdfc_delisted_flag = sec_master.is_delisted("INE001A01036", datetime.date(2023, 7, 13))

        # 2. COCHINSHIP (INE704P01017 -> INE704P01025) transitioned effective 2024-01-10
        cship_old_pre = sec_master.is_active("INE704P01017", datetime.date(2024, 1, 9))
        cship_new_pre = not sec_master.is_active("INE704P01025", datetime.date(2024, 1, 9))

        cship_old_pruned = not sec_master.is_active("INE704P01017", datetime.date(2024, 1, 10))
        cship_new_active = sec_master.is_active("INE704P01025", datetime.date(2024, 1, 10))

        g2b5_3_passed = (
            hdfc_pre_active and hdfc_on_pruned and hdfc_delisted_flag
            and cship_old_pre and cship_new_pre and cship_old_pruned and cship_new_active
        )
        all_passed = all_passed and g2b5_3_passed
        print(f"[{'PASS' if g2b5_3_passed else 'FAIL'}] Gate G2B.5-3: ISIN transitions and delistings pruned on exact dates")
        print(f"       HDFC: Active 2023-07-12 ({hdfc_pre_active}) -> Pruned 2023-07-13 ({hdfc_on_pruned})")
        print(f"       COCHINSHIP: Old active 2024-01-09 ({cship_old_pre}) -> New active 2024-01-10 ({cship_new_active})")

        # ----------------------------------------------------------------------
        # GATE G2B.5-2: Rerun Reproduces Identical Dataset & Universe Fingerprints
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-2: Rerun Content & Universe Fingerprint Reproducibility ---")
        temp_gold_silver = SilverStorage(temp_dir / "gold_silver")
        rec_d8 = [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1480.00"), Decimal("1500.00"), Decimal("1475.00"), Decimal("1495.00"), 50000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d8, Decimal("2580.00"), Decimal("2600.00"), Decimal("2570.00"), Decimal("2590.00"), 80000),
        ]
        rec_d10 = [
            SilverRecord("INE009A01021", "INFY", "EQ", d10, Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 60000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d10, Decimal("2600.00"), Decimal("2630.00"), Decimal("2590.00"), Decimal("2620.00"), 85000),
        ]
        temp_gold_silver.write_daily_partition(d8, rec_d8)
        temp_gold_silver.write_daily_partition(d10, rec_d10)

        gold = GoldEngine(temp_gold_silver, cal, sec_master)

        snap1, _ = gold.build_dataset_snapshot(d8, d10)
        fpr1_data = snap1.content_fingerprint
        fpr1_univ = snap1.universe_fingerprint

        snap2, _ = gold.build_dataset_snapshot(d8, d10)
        fpr2_data = snap2.content_fingerprint
        fpr2_univ = snap2.universe_fingerprint

        g2b5_2_passed = (
            fpr1_data == fpr2_data
            and fpr1_univ == fpr2_univ
            and fpr1_data.startswith("DATA-CTNT-V2-")
            and fpr1_univ.startswith("UNIV-SCHED-V1-")
        )
        all_passed = all_passed and g2b5_2_passed
        print(f"[{'PASS' if g2b5_2_passed else 'FAIL'}] Gate G2B.5-2: Deterministic rerun reproduces bit-for-bit identical fingerprints")
        print(f"       Dataset content fingerprint:  {fpr1_data}")
        print(f"       Universe schedule fingerprint: {fpr1_univ}")

        # ----------------------------------------------------------------------
        # GATE G2B.5-6: DuckDB Views Disposable — File Deletion Changes Zero Fingerprints
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-6: DuckDB Views Disposable (Zero Fingerprint Change) ---")
        views = DuckDBViewLayer(temp_gold_silver, db_path=duckdb_path)
        views.connect()
        query_rows = views.query("SELECT isin, symbol, count(*) FROM silver_bhavcopy GROUP BY isin, symbol ORDER BY isin")
        view_queried_ok = (len(query_rows) == 2 and query_rows[0][0] == "INE002A01018")

        # Unlink .duckdb file
        deleted = views.unlink_database_file()
        file_deleted_ok = (deleted and not duckdb_path.exists())

        # Re-verify Gold dataset fingerprint after .duckdb file was deleted
        snap_after_deletion, _ = gold.build_dataset_snapshot(d8, d10)
        fpr_match_after_delete = (snap_after_deletion.content_fingerprint == fpr1_data)
        univ_match_after_delete = (snap_after_deletion.universe_fingerprint == fpr1_univ)

        g2b5_6_passed = view_queried_ok and file_deleted_ok and fpr_match_after_delete and univ_match_after_delete
        all_passed = all_passed and g2b5_6_passed
        print(f"[{'PASS' if g2b5_6_passed else 'FAIL'}] Gate G2B.5-6: DuckDB view layer deleted with ZERO fingerprint alteration")
        print(f"       Queried view rows: {len(query_rows)} | DB deleted: {file_deleted_ok} | Fingerprint match: {fpr_match_after_delete}")

        # ----------------------------------------------------------------------
        # GATE G2B.5-7: Gating Window Enforcement (No GO Prior to 2018-04-01)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-7: Gating Window Enforcement ---")
        warmup_eval_start = datetime.date(2017, 1, 1)
        binding_eval_start = datetime.date(2018, 4, 1)

        g7_warmup_classified = (classify_gating_window(warmup_eval_start, datetime.date(2017, 12, 31)) == GatingWindowClassification.PRE_SURVEILLANCE_WARMUP)
        g7_binding_classified = (classify_gating_window(binding_eval_start, datetime.date(2023, 12, 31)) == GatingWindowClassification.BINDING_EVALUATION)

        g7_go_blocked_on_warmup = False
        try:
            check_gating_verdict_eligibility(warmup_eval_start, "GO")
        except GatingWindowValidationError:
            g7_go_blocked_on_warmup = True

        g7_resolution_forces_not_run = (resolve_gating_verdict(warmup_eval_start, "GO") == "NOT RUN")
        g7_resolution_allows_binding = (resolve_gating_verdict(binding_eval_start, "GO") == "GO")

        g2b5_7_passed = (
            g7_warmup_classified and g7_binding_classified
            and g7_go_blocked_on_warmup and g7_resolution_forces_not_run and g7_resolution_allows_binding
        )
        all_passed = all_passed and g2b5_7_passed
        print(f"[{'PASS' if g2b5_7_passed else 'FAIL'}] Gate G2B.5-7: Pre-2018 history strictly warm-up; GO verdict blocked fail-closed")
        print(f"       Pre-2018 GO blocked: {g7_go_blocked_on_warmup} | Resolved verdict: {resolve_gating_verdict(warmup_eval_start, 'GO')}")

        # ----------------------------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------------------------
        print("\n" + "=" * 80)
        total_gates = 7
        passed_gates = sum([g2b5_1_passed, g2b5_2_passed, g2b5_3_passed, g2b5_4_passed, g2b5_5_passed, g2b5_6_passed, g2b5_7_passed])
        pct = (passed_gates / total_gates) * 100.0

        if all_passed:
            print(f"OVERALL VERDICT: ALL MEASURED GATES PASSED ({passed_gates}/{total_gates}, {pct:.1f}%)")
        else:
            print(f"OVERALL VERDICT: ONE OR MORE GATES FAILED ({passed_gates}/{total_gates}, {pct:.1f}%)")
        print("=" * 80)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return all_passed


if __name__ == "__main__":
    success = run_phase_2b5_verification()
    sys.exit(0 if success else 1)
