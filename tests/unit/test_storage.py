"""
Unit Tests for Phase 2B.5 Market Data Ingestion and Immutable Storage Layer.

Verifies:
- Gate G2B.5-1: Truncated or tampered Bronze payload fails closed (TamperedBronzePayloadError).
- Gate G2B.5-2: Rerun reproduces bit-for-bit identical dataset (DATA-CTNT-V2) and universe (UNIV-SCHED-V1) fingerprints.
- Gate G2B.5-3: Known ISIN transition and delisting are pruned on their exact effective dates.
- Gate G2B.5-4: Session present in calendar but absent in archive classifies as UNEXPLAINED_MISSING_RECORD.
- Gate G2B.5-5: No Silver partition is ever rewritten (SilverPartitionImmutableError).
- Gate G2B.5-6: DuckDB database is deleted and rebuilt with zero change to any fingerprint.
- Gate G2B.5-7: No session before 2018-04-01 can reach a GO verdict (classified as NOT RUN).
"""

import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import pytest

from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.exchange_series import PriceSeriesGapType
from signal_core.contracts.price_bar import PriceBar
from signal_core.storage.calendar import (
    CalendarError,
    InvalidSessionError,
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
    SecurityMasterError,
    SurveillanceInterval,
    SurveillanceStage,
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
    SilverStorageError,
)
from signal_core.storage.gold import (
    GoldEngine,
    GoldEngineError,
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


@pytest.fixture
def sample_calendar() -> TradingCalendar:
    sessions = (
        datetime.date(2024, 1, 8),
        datetime.date(2024, 1, 9),
        datetime.date(2024, 1, 10),
        datetime.date(2024, 1, 11),
        datetime.date(2024, 1, 12),
    )
    fpr = compute_calendar_fingerprint(sessions)
    return TradingCalendar(
        calendar_id="TEST-CAL",
        market="NSE_CASH",
        sessions=sessions,
        binding_start_date=datetime.date(2018, 4, 1),
        fingerprint=fpr,
    )


@pytest.fixture
def temp_storage_dirs():
    with tempfile.TemporaryDirectory(prefix="test_storage_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"
        duckdb_path = tmp_path / "views.duckdb"
        yield bronze_dir, silver_dir, duckdb_path


def test_calendar_contracts_and_queries(sample_calendar: TradingCalendar):
    cal = sample_calendar
    assert cal.total_sessions == 5
    assert cal.start_date == datetime.date(2024, 1, 8)
    assert cal.end_date == datetime.date(2024, 1, 12)
    assert cal.is_session(datetime.date(2024, 1, 10))
    assert not cal.is_session(datetime.date(2024, 1, 13))  # Saturday

    # Navigation
    assert cal.next_session(datetime.date(2024, 1, 9)) == datetime.date(2024, 1, 10)
    assert cal.previous_session(datetime.date(2024, 1, 10)) == datetime.date(2024, 1, 9)
    assert cal.advance_sessions(datetime.date(2024, 1, 8), 2) == datetime.date(2024, 1, 10)

    # Invariants
    with pytest.raises(InvalidSessionError):
        cal.advance_sessions(datetime.date(2024, 1, 13), 1)
    with pytest.raises(InvalidSessionError):
        cal.advance_sessions(datetime.date(2024, 1, 12), 1)  # out of bounds


def test_load_authoritative_nse_trading_calendar():
    cal = load_nse_trading_calendar()
    assert cal.total_sessions == 2923
    assert cal.start_date == datetime.date(2015, 1, 1)
    assert cal.end_date == datetime.date(2026, 11, 11)
    assert cal.binding_start_date == datetime.date(2018, 4, 1)
    assert cal.fingerprint.startswith("CAL-FPR-V1-")

    # Warm-up vs binding partitioning
    warmup_sessions = cal.sessions_in_range(datetime.date(2015, 1, 1), datetime.date(2018, 3, 31))
    assert len(warmup_sessions) == 798
    binding_sessions = cal.sessions_in_range(datetime.date(2018, 4, 1), datetime.date(2026, 11, 11))
    assert len(binding_sessions) == 2125
    assert len(warmup_sessions) + len(binding_sessions) == 2923


def test_gate_g2b5_1_bronze_tamper_fails_closed(temp_storage_dirs):
    bronze_dir, _, _ = temp_storage_dirs
    bronze = BronzeStorage(bronze_dir)

    payload = b"TRADE_DATE,ISIN,CLOSE\n2024-01-10,INE009A01021,1500.00\n"
    entry = bronze.store_payload("bhavcopy/2024/2024-01-10.csv", payload, source_url="https://archives.nse.test/bhav.csv")

    # Valid read verifies SHA-256 and byte count
    data = bronze.read_payload("bhavcopy/2024/2024-01-10.csv", verify=True)
    assert data == payload

    # 1. Bit flip tampering fails closed
    stored_file = bronze.root_dir / "bhavcopy/2024/2024-01-10.csv"
    with open(stored_file, "wb") as f:
        f.write(payload.replace(b"1500.00", b"9999.00"))

    with pytest.raises(TamperedBronzePayloadError, match="Payload SHA-256 mismatch"):
        bronze.read_payload("bhavcopy/2024/2024-01-10.csv", verify=True)

    # 2. Truncation tampering fails closed
    with open(stored_file, "wb") as f:
        f.write(payload[:10])

    with pytest.raises(TamperedBronzePayloadError, match="Payload size mismatch"):
        bronze.read_payload("bhavcopy/2024/2024-01-10.csv", verify=True)

    # 3. Unmanifested payload fails closed
    unmanifested_file = bronze.root_dir / "untracked.csv"
    with open(unmanifested_file, "wb") as f:
        f.write(b"rogue data")

    with pytest.raises(MissingBronzeManifestError):
        bronze.read_payload("untracked.csv", verify=True)


def test_gate_g2b5_5_silver_partition_immutability(temp_storage_dirs):
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir)

    d1 = datetime.date(2024, 1, 10)
    records = [
        SilverRecord(
            isin="INE009A01021",
            symbol="INFY",
            series="EQ",
            trade_date=d1,
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=100000,
            traded_value=Decimal("151000000.00"),
        )
    ]

    # First write succeeds
    p = silver.write_daily_partition(d1, records)
    assert p.is_file()

    # Attempting to rewrite partition fails closed with SilverPartitionImmutableError
    with pytest.raises(SilverPartitionImmutableError, match="strictly prohibited per AGENTS.md Rule 10.1"):
        silver.write_daily_partition(d1, records)


def test_gate_g2b5_4_missing_session_classifies_as_unexplained_gap(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir)
    sec_master = build_production_security_master()

    # Write partitions for 2024-01-08 and 2024-01-10 (missing 2024-01-09)
    d8 = datetime.date(2024, 1, 8)
    d10 = datetime.date(2024, 1, 10)

    r8 = [
        SilverRecord(
            isin="INE009A01021",
            symbol="INFY",
            series="EQ",
            trade_date=d8,
            open=Decimal("1480.00"),
            high=Decimal("1500.00"),
            low=Decimal("1475.00"),
            close=Decimal("1495.00"),
            volume=50000,
        )
    ]
    r10 = [
        SilverRecord(
            isin="INE009A01021",
            symbol="INFY",
            series="EQ",
            trade_date=d10,
            open=Decimal("1500.00"),
            high=Decimal("1520.00"),
            low=Decimal("1490.00"),
            close=Decimal("1510.00"),
            volume=60000,
        )
    ]

    silver.write_daily_partition(d8, r8)
    silver.write_daily_partition(d10, r10)

    # Read series across 2024-01-08 to 2024-01-10
    bars, gaps = silver.read_instrument_series_with_calendar_validation(
        isin="INE009A01021",
        start_date=d8,
        end_date=d10,
        calendar=sample_calendar,
        security_master=sec_master,
    )

    assert len(bars) == 2
    assert len(gaps) == 1
    # 2024-01-09 must be classified as UNEXPLAINED_MISSING_RECORD, NOT silently bridged!
    assert gaps[0] == (datetime.date(2024, 1, 9), PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD)


def test_gate_g2b5_3_isin_transition_and_delisting_pruned_on_exact_effective_dates():
    sec_master = build_production_security_master()

    # 1. HDFC Delisting (INE001A01036) effective 2023-07-13
    pre_delisting = datetime.date(2023, 7, 12)
    on_delisting = datetime.date(2023, 7, 13)
    post_delisting = datetime.date(2023, 7, 14)

    assert sec_master.is_active("INE001A01036", pre_delisting) is True
    assert "INE001A01036" in sec_master.active_isins_on(pre_delisting)

    # On exact effective date, HDFC is pruned from active universe
    assert sec_master.is_delisted("INE001A01036", on_delisting) is True
    assert sec_master.is_active("INE001A01036", on_delisting) is False
    assert "INE001A01036" not in sec_master.active_isins_on(on_delisting)

    assert sec_master.is_active("INE001A01036", post_delisting) is False
    assert "INE001A01036" not in sec_master.active_isins_on(post_delisting)

    # 2. COCHINSHIP ISIN Transition: INE704P01017 -> INE704P01025 effective 2024-01-10
    pre_transition = datetime.date(2024, 1, 9)
    on_transition = datetime.date(2024, 1, 10)
    post_transition = datetime.date(2024, 1, 11)

    # Pre-transition: old ISIN active, new ISIN not active
    assert sec_master.is_active("INE704P01017", pre_transition) is True
    assert sec_master.is_active("INE704P01025", pre_transition) is False
    assert "INE704P01017" in sec_master.active_isins_on(pre_transition)
    assert "INE704P01025" not in sec_master.active_isins_on(pre_transition)

    # On transition effective date: old ISIN pruned, new ISIN active
    assert sec_master.is_transitioned_out("INE704P01017", on_transition) is True
    assert sec_master.is_active("INE704P01017", on_transition) is False
    assert sec_master.is_active("INE704P01025", on_transition) is True
    assert "INE704P01017" not in sec_master.active_isins_on(on_transition)
    assert "INE704P01025" in sec_master.active_isins_on(on_transition)

    # Post-transition: new ISIN active
    assert sec_master.is_active("INE704P01017", post_transition) is False
    assert sec_master.is_active("INE704P01025", post_transition) is True


def test_gate_g2b5_2_rerun_fingerprint_reproducibility(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir)
    sec_master = build_production_security_master()

    # Seed two sessions with INFY and RELIANCE
    d8 = datetime.date(2024, 1, 8)
    d9 = datetime.date(2024, 1, 9)

    silver.write_daily_partition(
        d8,
        [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1500.00"), Decimal("1510.00"), Decimal("1495.00"), Decimal("1505.00"), 50000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d8, Decimal("2600.00"), Decimal("2620.00"), Decimal("2590.00"), Decimal("2610.00"), 80000),
        ],
    )
    silver.write_daily_partition(
        d9,
        [
            SilverRecord("INE009A01021", "INFY", "EQ", d9, Decimal("1505.00"), Decimal("1525.00"), Decimal("1500.00"), Decimal("1520.00"), 60000),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d9, Decimal("2610.00"), Decimal("2630.00"), Decimal("2605.00"), Decimal("2625.00"), 75000),
        ],
    )

    gold = GoldEngine(silver, sample_calendar, sec_master)

    # First run
    snap1, prices1 = gold.build_dataset_snapshot(d8, d9)
    fpr1_data = snap1.content_fingerprint
    fpr1_univ = snap1.universe_fingerprint

    # Second run (rerun)
    snap2, prices2 = gold.build_dataset_snapshot(d8, d9)
    fpr2_data = snap2.content_fingerprint
    fpr2_univ = snap2.universe_fingerprint

    assert fpr1_data == fpr2_data
    assert fpr1_univ == fpr2_univ
    assert fpr1_data.startswith("DATA-CTNT-V2-")
    assert fpr1_univ.startswith("UNIV-SCHED-V1-")


def test_gate_g2b5_6_duckdb_view_layer_deletion_changes_zero_fingerprints(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, duckdb_path = temp_storage_dirs
    silver = SilverStorage(silver_dir)
    sec_master = build_production_security_master()

    d8 = datetime.date(2024, 1, 8)
    silver.write_daily_partition(
        d8,
        [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1500.00"), Decimal("1510.00"), Decimal("1495.00"), Decimal("1505.00"), 50000),
        ],
    )

    gold = GoldEngine(silver, sample_calendar, sec_master)
    initial_snap, _ = gold.build_dataset_snapshot(d8, d8)
    initial_content_fpr = initial_snap.content_fingerprint
    initial_univ_fpr = initial_snap.universe_fingerprint

    # 1. Connect DuckDB view layer and execute analytical query
    views = DuckDBViewLayer(silver, db_path=duckdb_path)
    views.connect()
    rows = views.query("SELECT isin, symbol, close FROM silver_bhavcopy WHERE isin = 'INE009A01021'")
    assert len(rows) == 1
    assert rows[0][0] == "INE009A01021"
    assert rows[0][1] == "INFY"
    assert rows[0][2] == "1505.00"

    assert duckdb_path.exists()

    # 2. Unlink / delete .duckdb file
    deleted = views.unlink_database_file()
    assert deleted is True
    assert not duckdb_path.exists()

    # 3. Recompute Gold snapshot and verify zero change to fingerprints
    recomputed_snap, _ = gold.build_dataset_snapshot(d8, d8)
    assert recomputed_snap.content_fingerprint == initial_content_fpr
    assert recomputed_snap.universe_fingerprint == initial_univ_fpr

    # 4. Reconnect DuckDB view layer and verify query works again seamlessly
    views.connect()
    rows_rebuilt = views.query("SELECT count(*) FROM silver_bhavcopy")
    assert rows_rebuilt[0][0] == 1
    views.close()


def test_gate_g2b5_7_no_session_before_2018_can_reach_go_verdict():
    warmup_start = datetime.date(2017, 1, 1)
    warmup_end = datetime.date(2017, 12, 31)

    binding_start = datetime.date(2018, 4, 1)
    binding_end = datetime.date(2023, 12, 31)

    # Classifications
    assert classify_gating_window(warmup_start, warmup_end) == GatingWindowClassification.PRE_SURVEILLANCE_WARMUP
    assert classify_gating_window(binding_start, binding_end) == GatingWindowClassification.BINDING_EVALUATION

    # Pre-2018 cannot reach GO: raises GatingWindowValidationError
    with pytest.raises(GatingWindowValidationError, match="Gate G2B.5-7 Violation"):
        check_gating_verdict_eligibility(warmup_start, "GO")

    # Binding window can reach GO
    check_gating_verdict_eligibility(binding_start, "GO")  # does not raise

    # Resolution forces 'NOT RUN' for pre-2018
    assert resolve_gating_verdict(warmup_start, "GO") == "NOT RUN"
    assert resolve_gating_verdict(warmup_start, "PASS") == "NOT RUN"
    assert resolve_gating_verdict(binding_start, "GO") == "GO"
    assert resolve_gating_verdict(binding_start, "NO-GO") == "NO-GO"
