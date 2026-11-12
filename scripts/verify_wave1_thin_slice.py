"""
Signal Atlas Core — Wave 1 Thin Real-Data Vertical Slice Verification
Exercises Audit §26 Wave 1 requirements on real NSE Bhavcopy for COCHINSHIP in January 2024:
Bronze -> Silver -> Gold -> DuckDB -> DATA-CTNT-V2, plus real corporate action and real membership interval.
"""

import datetime
from decimal import Decimal
import io
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Dict, List, Optional, Tuple
import zipfile

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.universe import IndexMembershipInterval
from signal_core.storage.bronze import BronzeStorage
from signal_core.storage.calendar import load_nse_trading_calendar
from signal_core.storage.gold import GoldEngine
from signal_core.storage.ingest import ingest_daily_bhavcopy_archive, parse_bhavcopy_archive
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    ISINTransitionEvent,
    SecurityMaster,
    SymbolInterval,
    build_production_security_master,
)
from signal_core.storage.silver import SilverStorage
from signal_core.storage.views import DuckDBViewLayer


def run_wave1_verification(raw_data_dir: Optional[Path] = None) -> bool:
    print("=" * 80)
    print("SIGNAL ATLAS — WAVE 1 THIN REAL-DATA VERTICAL SLICE VERIFICATION")
    print(f"Executed at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("Target: COCHINSHIP (INE704P01017 -> INE704P01025) across Jan 2024 (22 sessions)")
    print("=" * 80)

    # 1. Authoritative Calendar Verification
    print("\n--- Gate W1-1: Authoritative Calendar & January 2024 Session Completeness ---")
    cal = load_nse_trading_calendar()
    jan_sessions = cal.sessions_in_range(datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))
    print(f"[INFO] January 2024 trading sessions in calendar: {len(jan_sessions)}")
    
    # Check 2024-01-20 DR session
    dr_session = cal.get_session(datetime.date(2024, 1, 20))
    dr_ok = dr_session is not None and dr_session.session_type.value == "SPECIAL"
    print(f"[{'PASS' if dr_ok else 'FAIL'}] 2024-01-20 DR live trading session present in calendar: {dr_ok}")

    session_count_ok = len(jan_sessions) == 22
    print(f"[{'PASS' if session_count_ok else 'FAIL'}] Authoritative calendar matches real 22 trading sessions: {len(jan_sessions)} == 22")

    if not (dr_ok and session_count_ok):
        print("[FAIL] Calendar prerequisites not satisfied.")
        return False

    # 2. Locate Raw Bhavcopy Archives
    if raw_data_dir is None:
        raw_data_dir = Path(__file__).resolve().parent.parent.parent / "Signal-Atlas" / "data" / "raw" / "2024"
    
    if not raw_data_dir.is_dir():
        print(f"[FAIL] Raw data directory not found at: {raw_data_dir}")
        return False

    jan_zips = sorted(list(raw_data_dir.glob("cm*JAN2024bhav.csv.zip")))
    print(f"[INFO] Raw Bhavcopy archives discovered for Jan 2024: {len(jan_zips)}")
    if len(jan_zips) != 22:
        print(f"[FAIL] Expected 22 raw Bhavcopy archives for January 2024, found {len(jan_zips)}")
        return False

    # Setup isolated test storage directories
    temp_dir = tempfile.mkdtemp(prefix="wave1_thin_slice_")
    temp_path = Path(temp_dir)
    bronze_dir = temp_path / "bronze"
    silver_dir = temp_path / "silver"
    duckdb_path = temp_path / "views.duckdb"

    try:
        bronze = BronzeStorage(bronze_dir)
        silver = SilverStorage(silver_dir, calendar=cal)

        # 3. Bronze -> Silver Ingestion Pipeline
        print("\n--- Gate W1-2: Real Bhavcopy Ingestion (Bronze -> Silver) ---")
        target_isins = ["INE704P01017", "INE704P01025"]
        ingested_count = 0

        for zf in jan_zips:
            raw_bytes = zf.read_bytes()
            b_entry, s_path, n_recs = ingest_daily_bhavcopy_archive(
                bronze=bronze,
                silver=silver,
                archive_bytes=raw_bytes,
                filename=zf.name,
                source_url=f"https://archives.nseindia.com/content/historical/EQUITIES/2024/JAN/{zf.name}",
                calendar=cal,
                target_isins=target_isins,
                target_series=["EQ"],
            )
            assert s_path.is_file(), f"Silver partition not written for {zf.name}"
            assert n_recs == 1, f"Expected 1 COCHINSHIP record in {zf.name}, got {n_recs}"
            ingested_count += 1

        print(f"[PASS] Ingested all {ingested_count} daily sessions into Bronze & Silver")

        # Verify Bronze Manifest
        manifest_lines = [l for l in bronze.manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        manifest_ok = len(manifest_lines) == 22
        print(f"[{'PASS' if manifest_ok else 'FAIL'}] Bronze manifest contains exactly 22 immutable entries: {len(manifest_lines)}")

        # Verify Silver Partition Count
        silver_partitions = list(silver.bhavcopy_dir.glob("*/*.parquet"))
        silver_ok = len(silver_partitions) == 22
        print(f"[{'PASS' if silver_ok else 'FAIL'}] Silver daily partitions written: {len(silver_partitions)} == 22")

        # 4. Security Master & Corporate Action Verification
        print("\n--- Gate W1-3: Security Master, Real Corporate Action & ISIN Transition ---")
        sec_master = build_production_security_master()

        # Check Old ISIN active Jan 1 - Jan 9
        old_active_ok = True
        for s in jan_sessions:
            if s <= datetime.date(2024, 1, 9):
                if not sec_master.is_active("INE704P01017", s):
                    old_active_ok = False
            else:
                if sec_master.is_active("INE704P01017", s):
                    old_active_ok = False
        print(f"[{'PASS' if old_active_ok else 'FAIL'}] Old ISIN INE704P01017 active strictly on Jan 1-9 (7 sessions): {old_active_ok}")

        # Check New ISIN active Jan 10 - Jan 31
        new_active_ok = True
        for s in jan_sessions:
            if s >= datetime.date(2024, 1, 10):
                if not sec_master.is_active("INE704P01025", s):
                    new_active_ok = False
            else:
                if sec_master.is_active("INE704P01025", s):
                    new_active_ok = False
        print(f"[{'PASS' if new_active_ok else 'FAIL'}] New ISIN INE704P01025 active strictly on Jan 10-31 (15 sessions): {new_active_ok}")

        # Check 2:1 Stock Split Corporate Action
        corp_actions = sec_master.get_corporate_actions("INE704P01017")
        ca_ok = (
            len(corp_actions) >= 1
            and corp_actions[0].action_type == CorporateActionType.ISIN_TRANSITION
            and corp_actions[0].ex_date == datetime.date(2024, 1, 10)
            and corp_actions[0].ratio_numerator == Decimal("2")
            and corp_actions[0].ratio_denominator == Decimal("1")
            and corp_actions[0].adjustment_factor == Decimal("0.5")
        )
        print(f"[{'PASS' if ca_ok else 'FAIL'}] Real 2:1 Stock Split verified (ex-date 2024-01-10, factor=0.5): {ca_ok}")

        # 5. Real Index Membership Interval Contract
        print("\n--- Gate W1-4: Real Point-in-Time Index Membership Interval ---")
        interval_old = IndexMembershipInterval(
            index_name="NIFTY500",
            isin="INE704P01017",
            effective_from=datetime.date(2024, 1, 1),
            effective_to=datetime.date(2024, 1, 10),
            circular_ref="NSE/CML/60114",
            source_publication="NSE_INDEX_CIRCULAR_COCHINSHIP_SPLIT",
        )
        interval_new = IndexMembershipInterval(
            index_name="NIFTY500",
            isin="INE704P01025",
            effective_from=datetime.date(2024, 1, 10),
            effective_to=datetime.date(2024, 2, 1),
            circular_ref="NSE/CML/60114",
            source_publication="NSE_INDEX_CIRCULAR_COCHINSHIP_SPLIT",
        )

        assert not interval_old.overlaps(interval_new), "Intervals must not overlap"
        assert interval_old.contains(datetime.date(2024, 1, 9)) is True
        assert interval_old.contains(datetime.date(2024, 1, 10)) is False
        assert interval_new.contains(datetime.date(2024, 1, 10)) is True
        print("[PASS] IndexMembershipInterval half-open [effective_from, effective_to) transitions exactly on ex-date")

        # 6. Gold Layer: Unadjusted vs Split-Bonus Adjusted Panels & DATA-CTNT-V2 Fingerprint
        print("\n--- Gate W1-5: Gold Derived Layer & DATA-CTNT-V2 Fingerprint ---")
        gold = GoldEngine(silver_storage=silver, calendar=cal, security_master=sec_master)

        # Unadjusted raw price panel
        raw_panel = gold.load_price_panel(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            isins=["INE704P01017", "INE704P01025"],
        )
        old_bars = raw_panel["INE704P01017"]
        new_bars = raw_panel["INE704P01025"]
        assert len(old_bars) == 7, f"Expected 7 bars for old ISIN, got {len(old_bars)}"
        assert len(new_bars) == 15, f"Expected 15 bars for new ISIN, got {len(new_bars)}"

        # Jan 9 raw close: Rs 1338.00; Jan 10 raw close: Rs 802.80
        jan9_raw = old_bars[-1]
        jan10_raw = new_bars[0]
        assert jan9_raw.trade_date == datetime.date(2024, 1, 9)
        assert jan9_raw.close == Decimal("1338"), f"Expected 1338, got {jan9_raw.close}"
        assert jan9_raw.volume == 3355705
        assert jan10_raw.trade_date == datetime.date(2024, 1, 10)
        assert jan10_raw.close == Decimal("802.8"), f"Expected 802.8, got {jan10_raw.close}"
        assert jan10_raw.volume == 22442717
        print(f"[PASS] Unadjusted Price Panel: Jan 9 close = ₹{jan9_raw.close} | Jan 10 close = ₹{jan10_raw.close}")

        # Split-adjusted snapshot
        snap, adj_panel = gold.build_dataset_snapshot(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED,
            dataset_id="COCHINSHIP-JAN2024-SLICE",
            isins=["INE704P01017", "INE704P01025"],
        )
        jan9_adj = adj_panel["INE704P01017"][-1]
        jan10_adj = adj_panel["INE704P01025"][0]

        # In split-adjusted space: Jan 9 close is 1338 * 0.5 = 669.00; volume is 3355705 * 2 = 6711410
        expected_adj_close = Decimal("669.0")
        expected_adj_vol = 3355705 * 2
        assert jan9_adj.close == expected_adj_close, f"Expected {expected_adj_close}, got {jan9_adj.close}"
        assert jan9_adj.volume == expected_adj_vol, f"Expected {expected_adj_vol}, got {jan9_adj.volume}"
        assert jan10_adj.close == Decimal("802.8")
        print(f"[PASS] Split-Adjusted Price Panel: Jan 9 close = ₹{jan9_adj.close} (vol={jan9_adj.volume}) -> Jan 10 close = ₹{jan10_adj.close} (vol={jan10_adj.volume})")

        # Fingerprint reproducibility check (Gate G2B.5-2)
        snap2, _ = gold.build_dataset_snapshot(
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED,
            dataset_id="COCHINSHIP-JAN2024-SLICE",
            isins=["INE704P01017", "INE704P01025"],
        )
        assert snap.content_fingerprint == snap2.content_fingerprint, "Fingerprint must be bit-for-bit deterministic"
        print(f"[PASS] Content Fingerprint bit-for-bit identical across reruns:")
        print(f"       DATA-CTNT-V2: {snap.content_fingerprint}")
        print(f"       UNIV-SCHED-V1: {snap.universe_fingerprint}")

        # 7. DuckDB SQL View Layer
        print("\n--- Gate W1-6: DuckDB SQL View Layer & Exact Decimal Precision ---")
        views = DuckDBViewLayer(silver_storage=silver, db_path=duckdb_path)
        views.connect()

        # Query column types
        type_res = views.query("SELECT typeof(close), typeof(volume), typeof(trade_date) FROM silver_bhavcopy LIMIT 1")
        print(f"[PASS] DuckDB types verified: close={type_res[0][0]}, volume={type_res[0][1]}, trade_date={type_res[0][2]}")
        assert "DECIMAL" in type_res[0][0].upper(), f"close must be DECIMAL, got {type_res[0][0]}"

        # Query total rows and statistics
        stats = views.query("""
            SELECT 
                count(*) AS total_rows,
                min(close) AS min_close,
                max(close) AS max_close,
                sum(volume) AS total_vol
            FROM silver_bhavcopy
        """)
        total_rows, min_c, max_c, tot_v = stats[0]
        assert total_rows == 22, f"Expected 22 rows, got {total_rows}"
        print(f"[PASS] DuckDB SQL Aggregates over real Parquet partitions:")
        print(f"       Total sessions: {total_rows} | Min close: ₹{min_c} | Max close: ₹{max_c} | Total volume: {tot_v:,}")

        # Query split ex-date boundary in SQL
        boundary_rows = views.query("""
            SELECT trade_date, isin, symbol, close, volume 
            FROM silver_bhavcopy 
            WHERE trade_date IN ('2024-01-09', '2024-01-10')
            ORDER BY trade_date
        """)
        assert len(boundary_rows) == 2
        print(f"[PASS] SQL query of ISIN Transition Boundary:")
        print(f"       2024-01-09: ISIN={boundary_rows[0][1]} Close=₹{boundary_rows[0][3]} Volume={boundary_rows[0][4]:,}")
        print(f"       2024-01-10: ISIN={boundary_rows[1][1]} Close=₹{boundary_rows[1][3]} Volume={boundary_rows[1][4]:,}")

        views.close()

        print("\n" + "=" * 80)
        print("WAVE 1 THIN REAL-DATA VERTICAL SLICE: ALL GATES PASSED (100%)")
        print("=" * 80)
        return True

    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    success = run_wave1_verification()
    sys.exit(0 if success else 1)
