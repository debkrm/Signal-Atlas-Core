"""
Authoritative Reproducible Verification Probe for Phase 2B.5 (Market Data Ingestion & Immutable Storage Layer).

Remediates and enforces all §23 findings (Closure set E-1 through E-6):
- Gate G2B.5-1 (E-1, E-6): Calendar completeness, circular provenance, content-addressed Bronze with immutable restatements.
- Gate G2B.5-2: Rerun reproduces bit-for-bit identical dataset (DATA-CTNT-V2) and universe (UNIV-SCHED-V1) fingerprints.
- Gate G2B.5-3: Known ISIN transition and known delisting are pruned on their exact effective dates.
- Gate G2B.5-4 (E-2, E-3): Off-calendar bar rejection, missing session UNEXPLAINED_MISSING_RECORD, and refusal to fingerprint gapped datasets.
- Gate G2B.5-5: No Silver partition is ever rewritten (SilverPartitionImmutableError).
- Gate G2B.5-6 (E-4, E-5): DuckDB views expose exact DECIMAL(18, 4) prices, fail closed on partition corruption, and file deletion changes zero fingerprints.
- Gate G2B.5-7 (E-14): Pre-2018 history strictly warm-up; GO/APPROVED/PASS verdicts blocked fail-closed.

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
    SessionType,
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
    BronzeStorageError,
    MissingBronzeManifestError,
    TamperedBronzePayloadError,
)
from signal_core.storage.silver import (
    OffCalendarSessionError,
    SilverPartitionImmutableError,
    SilverRecord,
    SilverStorage,
)
from signal_core.storage.gold import (
    GoldEngine,
    NonContiguousDatasetError,
)
from signal_core.storage.views import (
    DuckDBViewError,
    DuckDBViewLayer,
)
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
        # E-1: CALENDAR COMPLETENESS, SESSION TYPING & CIRCULAR PROVENANCE
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-1 (Part A / E-1): Calendar Completeness & Provenance ---")
        cal = load_nse_trading_calendar()

        # 1. Total sessions and provenance
        cal_total = cal.total_sessions
        cal_ok = (
            cal_total == 2939
            and cal.start_date == datetime.date(2015, 1, 1)
            and cal.end_date == datetime.date(2026, 11, 11)
            and cal.binding_start_date == datetime.date(2018, 4, 1)
        )

        prov = cal.provenance
        prov_ok = (
            prov.get("source") == "NSE_CIRCULARS_ANNUAL_TRADING_HOLIDAYS_AND_SPECIAL_SESSIONS"
            and len(prov.get("circular_references", [])) >= 12
            and prov.get("sha256") == "a1d8824f894bb90047b4adcbac560181faebaafd72a0102e0175a367134ad773"
        )

        # 2. Check special budget and DR sessions
        budget_sat_ok = (
            cal.get_session(datetime.date(2020, 2, 1)) is not None
            and cal.get_session(datetime.date(2020, 2, 1)).session_type == SessionType.SPECIAL
            and cal.get_session(datetime.date(2025, 2, 1)) is not None
        )
        dr_sat_ok = (
            cal.get_session(datetime.date(2024, 3, 2)) is not None
            and cal.get_session(datetime.date(2024, 5, 18)) is not None
            and cal.get_session(datetime.date(2024, 5, 18)).session_type == SessionType.SPECIAL
        )

        # 3. Check weekday and weekend muhurat sessions
        muhurat_ok = (
            cal.get_session(datetime.date(2018, 11, 7)) is not None
            and cal.get_session(datetime.date(2018, 11, 7)).session_type == SessionType.MUHURAT
            and cal.get_session(datetime.date(2020, 11, 14)) is not None
            and cal.get_session(datetime.date(2024, 11, 1)) is not None
        )

        # 4. Annual completeness assertion
        annual_completeness_ok = True
        try:
            for y in range(2015, 2027):
                cal.assert_year_completeness(y)
        except Exception:
            annual_completeness_ok = False

        e1_passed = cal_ok and prov_ok and budget_sat_ok and dr_sat_ok and muhurat_ok and annual_completeness_ok
        print(f"[{'PASS' if e1_passed else 'FAIL'}] E-1: Calendar modeled as sessions (2939 sessions, budget/DR/muhurat all verified, provenance intact)")

        # ----------------------------------------------------------------------
        # E-6: CONTENT-ADDRESSED BRONZE WITH IMMUTABLE RESTATEMENTS
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-1 (Part B / E-6): Content-Addressed Bronze & Immutable Restatements ---")
        bronze = BronzeStorage(bronze_dir)
        payload_v1 = b"SESSION,ISIN,CLOSE\n2024-01-10,INE009A01021,1500.00\n"
        payload_v2 = b"SESSION,ISIN,CLOSE\n2024-01-10,INE009A01021,1505.00\n"
        rel_path = "bhavcopy/2024/2024-01-10.csv"

        entry_v1 = bronze.store_payload(rel_path, payload_v1, source_url="https://archives.nse.test/bhav_v1.csv")

        # Overwrite without restatement_ref rejected fail-closed (E-6)
        unauthorized_overwrite_blocked = False
        try:
            bronze.store_payload(rel_path, payload_v2, source_url="https://archives.nse.test/bhav_v2.csv")
        except BronzeStorageError:
            unauthorized_overwrite_blocked = True

        # Restatement with reference succeeds
        entry_v2 = bronze.store_payload(
            rel_path,
            payload_v2,
            source_url="https://archives.nse.test/bhav_v2.csv",
            restatement_ref="NSE/RESTATEMENT/CIRCULAR_2024",
        )

        # Both historical versions verifiable on disk (zero orphaned records)
        v1_data = bronze.read_payload(rel_path, sha256_digest=entry_v1.sha256, verify=True)
        v2_data = bronze.read_payload(rel_path, sha256_digest=entry_v2.sha256, verify=True)
        both_verifiable = (v1_data == payload_v1 and v2_data == payload_v2)

        # Tampering detection
        blob_path = bronze.get_blob_path(entry_v1.sha256)
        with open(blob_path, "wb") as f:
            f.write(b"corrupt")
        tamper_caught = False
        try:
            bronze.read_payload(rel_path, sha256_digest=entry_v1.sha256, verify=True)
        except TamperedBronzePayloadError:
            tamper_caught = True

        # Restore blob
        with open(blob_path, "wb") as f:
            f.write(payload_v1)

        e6_passed = unauthorized_overwrite_blocked and both_verifiable and tamper_caught
        g2b5_1_passed = e1_passed and e6_passed
        all_passed = all_passed and g2b5_1_passed
        print(f"[{'PASS' if g2b5_1_passed else 'FAIL'}] Gate G2B.5-1: Provenanced calendar & content-addressed Bronze tamper/restatement invariants verified")

        # ----------------------------------------------------------------------
        # GATE G2B.5-5: Silver Partition Immutability (Append-Only)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-5: Silver Partition Immutability ---")
        silver = SilverStorage(silver_dir, calendar=cal)
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
        # E-2 & E-3 / GATE G2B.5-4: Missing Sessions, Off-Calendar Bars & Fail-Closed Snapshots
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-4 (E-2, E-3): Off-Calendar Bars, Missing Sessions & Fail-Closed Snapshots ---")
        sec_master = build_production_security_master()
        d8 = datetime.date(2024, 1, 8)
        d9 = datetime.date(2024, 1, 9)
        d10 = datetime.date(2024, 1, 10)
        sunday = datetime.date(2024, 1, 14)

        # 1. Writing off-calendar partition rejected fail-closed (E-2)
        off_cal_blocked = False
        try:
            silver.write_daily_partition(sunday, [
                SilverRecord("INE009A01021", "INFY", "EQ", sunday, Decimal("1500.00"), Decimal("1510.00"), Decimal("1490.00"), Decimal("1505.00"), 1000)
            ])
        except OffCalendarSessionError:
            off_cal_blocked = True

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

        # Snapshot refuses to fingerprint over missing session (E-3)
        gold_missing = GoldEngine(silver, cal, sec_master)
        snapshot_hole_blocked = False
        try:
            gold_missing.build_dataset_snapshot(d8, d10, isins=["INE009A01021", "INE002A01018"])
        except NonContiguousDatasetError:
            snapshot_hole_blocked = True

        g2b5_4_passed = off_cal_blocked and has_unexplained_gap and snapshot_hole_blocked
        all_passed = all_passed and g2b5_4_passed
        print(f"[{'PASS' if g2b5_4_passed else 'FAIL'}] Gate G2B.5-4: Off-calendar writes rejected, gaps classified UNEXPLAINED_MISSING_RECORD, gapped snapshots fail closed")
        print(f"       Off-calendar write blocked: {off_cal_blocked} | Missing session gap: {has_unexplained_gap} | Gapped snapshot blocked: {snapshot_hole_blocked}")

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
        temp_gold_silver = SilverStorage(temp_dir / "gold_silver", calendar=cal)
        rec_d8 = [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1480.00"), Decimal("1500.00"), Decimal("1475.00"), Decimal("1495.00"), 50000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d8, Decimal("2580.00"), Decimal("2600.00"), Decimal("2570.00"), Decimal("2590.00"), 80000),
        ]
        rec_d9 = [
            SilverRecord("INE009A01021", "INFY", "EQ", d9, Decimal("1490.00"), Decimal("1515.00"), Decimal("1485.00"), Decimal("1505.00"), 55000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d9, Decimal("2590.00"), Decimal("2615.00"), Decimal("2580.00"), Decimal("2605.00"), 82000),
        ]
        temp_gold_silver.write_daily_partition(d8, rec_d8)
        temp_gold_silver.write_daily_partition(d9, rec_d9)

        gold = GoldEngine(temp_gold_silver, cal, sec_master)

        snap1, _ = gold.build_dataset_snapshot(d8, d9, isins=["INE009A01021", "INE002A01018"])
        fpr1_data = snap1.content_fingerprint
        fpr1_univ = snap1.universe_fingerprint

        snap2, _ = gold.build_dataset_snapshot(d8, d9, isins=["INE009A01021", "INE002A01018"])
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
        # E-4 & E-5 / GATE G2B.5-6: DuckDB Views Exact DECIMAL Typing & Corruption Fail-Closed
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-6 (E-4, E-5): DuckDB Views Exact Decimal Typing & Disposable Storage ---")
        views = DuckDBViewLayer(temp_gold_silver, db_path=duckdb_path)
        views.connect()

        # E-4: Exact DECIMAL(18, 4) typing in SQL layer
        type_res = views.query("SELECT typeof(close) FROM silver_bhavcopy LIMIT 1")
        decimal_typed = (type_res[0][0] == "DECIMAL(18,4)")

        # Numeric comparisons and aggregates work correctly
        cmp_res_3000 = views.query("SELECT count(*) FROM silver_bhavcopy WHERE close >= 3000")
        numeric_cmp_ok = (cmp_res_3000[0][0] == 0)
        avg_res = views.query("SELECT avg(close) FROM silver_bhavcopy")
        avg_computed_ok = (avg_res[0][0] > 0)

        # Unlink .duckdb file and assert zero fingerprint change
        deleted = views.unlink_database_file()
        file_deleted_ok = (deleted and not duckdb_path.exists())

        snap_after_deletion, _ = gold.build_dataset_snapshot(d8, d9, isins=["INE009A01021", "INE002A01018"])
        fpr_match_after_delete = (snap_after_deletion.content_fingerprint == fpr1_data)

        # E-5: Fail closed on corrupt partition (does not swallow error into empty view)
        corrupt_silver_dir = temp_dir / "corrupt_silver"
        corrupt_silver = SilverStorage(corrupt_silver_dir, calendar=cal)
        corrupt_file = corrupt_silver.write_daily_partition(d8, rec_d8)
        with open(corrupt_file, "wb") as f:
            f.write(b"PAR1corrupted_truncated_bytes")

        corrupt_caught = False
        corrupt_views = DuckDBViewLayer(corrupt_silver, db_path=temp_dir / "corrupt.duckdb")
        try:
            corrupt_views.connect()
        except DuckDBViewError:
            corrupt_caught = True

        g2b5_6_passed = decimal_typed and numeric_cmp_ok and avg_computed_ok and file_deleted_ok and fpr_match_after_delete and corrupt_caught
        all_passed = all_passed and g2b5_6_passed
        print(f"[{'PASS' if g2b5_6_passed else 'FAIL'}] Gate G2B.5-6: DuckDB view layer DECIMAL(18,4) typing, corruption fail-closed, zero fingerprint change")
        print(f"       Column type: {type_res[0][0]} | Numeric predicate correct: {numeric_cmp_ok} | Corrupt partition caught: {corrupt_caught}")

        # ----------------------------------------------------------------------
        # E-14 / GATE G2B.5-7: Gating Window Enforcement (No GO/APPROVED/PASS Prior to 2018-04-01)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B.5-7 (E-14): Gating Window Enforcement ---")
        warmup_eval_start = datetime.date(2017, 1, 1)
        binding_eval_start = datetime.date(2018, 4, 1)

        g7_warmup_classified = (classify_gating_window(warmup_eval_start, datetime.date(2017, 12, 31)) == GatingWindowClassification.PRE_SURVEILLANCE_WARMUP)
        g7_binding_classified = (classify_gating_window(binding_eval_start, datetime.date(2023, 12, 31)) == GatingWindowClassification.BINDING_EVALUATION)

        # Check that GO, APPROVED, and PASS are all blocked fail-closed (E-14)
        go_blocked = False
        appr_blocked = False
        pass_blocked = False
        try:
            check_gating_verdict_eligibility(warmup_eval_start, "GO")
        except GatingWindowValidationError:
            go_blocked = True

        try:
            check_gating_verdict_eligibility(warmup_eval_start, "APPROVED")
        except GatingWindowValidationError:
            appr_blocked = True

        try:
            check_gating_verdict_eligibility(warmup_eval_start, "PASS")
        except GatingWindowValidationError:
            pass_blocked = True

        g7_resolution_forces_not_run = (resolve_gating_verdict(warmup_eval_start, "GO") == "NOT RUN")
        g7_resolution_allows_binding = (resolve_gating_verdict(binding_eval_start, "GO") == "GO")

        g2b5_7_passed = (
            g7_warmup_classified and g7_binding_classified
            and go_blocked and appr_blocked and pass_blocked
            and g7_resolution_forces_not_run and g7_resolution_allows_binding
        )
        all_passed = all_passed and g2b5_7_passed
        print(f"[{'PASS' if g2b5_7_passed else 'FAIL'}] Gate G2B.5-7: Pre-2018 history strictly warm-up; GO/APPROVED/PASS verdicts blocked fail-closed")
        print(f"       Pre-2018 GO blocked: {go_blocked} | APPROVED blocked: {appr_blocked} | PASS blocked: {pass_blocked}")

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
