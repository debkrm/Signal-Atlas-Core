"""
Comprehensive Unit Tests for Phase 2B.5 Storage Layer Remediation (§23 Closure Set E-1 through E-6).

Covers:
- E-1: Calendar modeled as sessions with session_type, open/close times, all special sessions, provenance, and annual completeness.
- E-2: Silver calendar validation: rejects off-calendar writes and raises OffCalendarSessionError if off-calendar partitions exist on disk.
- E-3: Snapshot fails closed: refuses to fingerprint non-contiguous datasets (NonContiguousDatasetError).
- E-4: Decimal-typed prices in DuckDB view: typeof(close) == DECIMAL(18, 4), numeric predicates and avg() work correctly.
- E-5: Fail-closed on corrupt partition in view layer: does not swallow corruption into empty view.
- E-6: Content-addressed Bronze with immutable restatements: overwrite without restatement_ref rejected; prior retrievals verifiable.
- E-8: SecurityMaster rejects duplicate delistings and transitions fail-closed.
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
    SessionType,
    TradingCalendar,
    TradingSessionRecord,
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
    HoldoutPartitionIsolationError,
    OffCalendarSessionError,
    SilverPartitionImmutableError,
    SilverRecord,
    SilverStorage,
    SilverStorageError,
)
from signal_core.storage.gold import (
    GoldEngine,
    GoldEngineError,
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


@pytest.fixture
def sample_calendar() -> TradingCalendar:
    sessions = (
        TradingSessionRecord(datetime.date(2024, 1, 8), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
        TradingSessionRecord(datetime.date(2024, 1, 9), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
        TradingSessionRecord(datetime.date(2024, 1, 10), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
        TradingSessionRecord(datetime.date(2024, 1, 11), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
        TradingSessionRecord(datetime.date(2024, 1, 12), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
    )
    fpr = compute_calendar_fingerprint(sessions)
    return TradingCalendar(
        calendar_id="TEST-CAL",
        market="NSE_CASH",
        session_records=sessions,
        binding_start_date=datetime.date(2018, 4, 1),
        fingerprint=fpr,
        provenance={"source": "TEST_SOURCE"},
        annual_session_counts={"2024": 5},
    )


@pytest.fixture
def temp_storage_dirs():
    with tempfile.TemporaryDirectory(prefix="test_storage_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"
        duckdb_path = tmp_path / "views.duckdb"
        yield bronze_dir, silver_dir, duckdb_path


# -----------------------------------------------------------------------------
# E-1: CALENDAR VERIFICATION & COMPLETENESS
# -----------------------------------------------------------------------------
def test_e1_calendar_completeness_and_provenance():
    cal = load_nse_trading_calendar()

    # 1. Total session count and date range (Audit §30 H-26, §45 H-59, §46 H-60)
    assert cal.total_sessions == len(cal.sessions) == 2935
    assert cal.start_date == datetime.date(2015, 1, 1)
    assert cal.end_date == datetime.date(2026, 11, 11)
    assert cal.binding_start_date == datetime.date(2018, 4, 1)

    # 2. Provenance block verification (Rule 10.7, Audit §30 H-26)
    prov = cal.provenance
    assert prov["source"] == "NSE_CIRCULARS_ANNUAL_TRADING_HOLIDAYS_AND_SPECIAL_SESSIONS"
    assert "circular_references" in prov
    assert len(prov["circular_references"]) >= 12
    assert "NSE/MSD/60300" in prov["circular_references"]
    assert "NSE/MSD/60318" in prov["circular_references"]
    assert prov["sha256"] == cal.fingerprint.replace("CAL-FPR-V1-", "")

    # 3. All special/muhurat sessions identified in §23 are present
    budget_sats = [datetime.date(2020, 2, 1), datetime.date(2025, 2, 1)]
    for bs in budget_sats:
        rec = cal.get_session(bs)
        assert rec is not None
        assert rec.session_type == SessionType.SPECIAL

    dr_sats = [datetime.date(2024, 1, 20), datetime.date(2024, 3, 2), datetime.date(2024, 5, 18)]
    for dr in dr_sats:
        rec = cal.get_session(dr)
        assert rec is not None
        assert rec.session_type == SessionType.SPECIAL

    muhurat_dates = [
        datetime.date(2015, 11, 11), datetime.date(2016, 10, 30), datetime.date(2017, 10, 19),
        datetime.date(2018, 11, 7), datetime.date(2019, 10, 27), datetime.date(2020, 11, 14),
        datetime.date(2021, 11, 4), datetime.date(2022, 10, 24), datetime.date(2023, 11, 12),
        datetime.date(2024, 11, 1), datetime.date(2025, 10, 21), datetime.date(2026, 11, 8),
    ]
    for md in muhurat_dates:
        rec = cal.get_session(md)
        assert rec is not None
        assert rec.session_type == SessionType.MUHURAT

    # 4. Annual completeness assertion
    for year in range(2015, 2027):
        cal.assert_year_completeness(year)


# -----------------------------------------------------------------------------
# E-2: SILVER CALENDAR VALIDATION & OFF-CALENDAR BAR REJECTION
# -----------------------------------------------------------------------------
def test_e2_silver_calendar_validation_and_off_calendar_rejection(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir, calendar=sample_calendar)

    # 1. Writing an off-calendar session (e.g. Sunday 2024-01-14) raises OffCalendarSessionError
    sunday = datetime.date(2024, 1, 14)
    rec_sunday = [
        SilverRecord("INE009A01021", "INFY", "EQ", sunday, Decimal("1500.00"), Decimal("1510.00"), Decimal("1490.00"), Decimal("1505.00"), 1000)
    ]
    with pytest.raises(OffCalendarSessionError, match="off-calendar session"):
        silver.write_daily_partition(sunday, rec_sunday)

    # 2. Writing a valid session succeeds
    d8 = datetime.date(2024, 1, 8)
    rec_d8 = [
        SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1500.00"), Decimal("1510.00"), Decimal("1490.00"), Decimal("1505.00"), 1000)
    ]
    silver.write_daily_partition(d8, rec_d8)

    # 3. If an off-calendar partition is placed on disk, read_instrument_series raises OffCalendarSessionError
    # (Never silently drops off-calendar partitions!)
    rogue_storage = SilverStorage(silver_dir, calendar=None)  # unvalidated writer bypass simulation
    rogue_storage.write_daily_partition(sunday, rec_sunday)

    with pytest.raises(OffCalendarSessionError, match="Found archived silver partition for off-calendar date"):
        silver.read_instrument_series_with_calendar_validation(
            isin="INE009A01021",
            start_date=d8,
            end_date=datetime.date(2024, 1, 15),
            calendar=sample_calendar,
        )


# -----------------------------------------------------------------------------
# E-3: FAIL-CLOSED SNAPSHOT GENERATION (ZERO GAPPED FINGERPRINTING)
# -----------------------------------------------------------------------------
def test_e3_build_dataset_snapshot_fails_closed_on_missing_session(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir, calendar=sample_calendar)
    sec_master = build_production_security_master()

    # Write partitions for Jan 8, 9, 11 (missing Jan 10)
    for d in [datetime.date(2024, 1, 8), datetime.date(2024, 1, 9), datetime.date(2024, 1, 11)]:
        silver.write_daily_partition(
            d,
            [
                SilverRecord("INE009A01021", "INFY", "EQ", d, Decimal("1500.00"), Decimal("1510.00"), Decimal("1490.00"), Decimal("1505.00"), 5000),
                SilverRecord("INE002A01018", "RELIANCE", "EQ", d, Decimal("2600.00"), Decimal("2620.00"), Decimal("2590.00"), Decimal("2610.00"), 8000),
            ]
        )

    gold = GoldEngine(silver, sample_calendar, sec_master)

    # 1. Missing active instrument on partition fails closed with NonContiguousDatasetError
    with pytest.raises(NonContiguousDatasetError, match="has unexplained missing record on session"):
        gold.build_dataset_snapshot(datetime.date(2024, 1, 8), datetime.date(2024, 1, 9))

    # 2. Missing daily partition entirely fails closed with NonContiguousDatasetError
    with pytest.raises(NonContiguousDatasetError, match="missing required silver partition for calendar session"):
        gold.build_dataset_snapshot(
            datetime.date(2024, 1, 8),
            datetime.date(2024, 1, 11),
            isins=["INE009A01021", "INE002A01018"],
        )


# -----------------------------------------------------------------------------
# E-4: EXACT DECIMAL TYPING IN DUCKDB VIEW LAYER
# -----------------------------------------------------------------------------
def test_e4_duckdb_view_layer_decimal_typing(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, duckdb_path = temp_storage_dirs
    silver = SilverStorage(silver_dir, calendar=sample_calendar)

    d8 = datetime.date(2024, 1, 8)
    silver.write_daily_partition(
        d8,
        [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1500.25"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1505.50"), 50000, Decimal("75275000.00")),
            SilverRecord("INE002A01018", "RELIANCE", "EQ", d8, Decimal("900.50"), Decimal("910.00"), Decimal("895.00"), Decimal("905.75"), 30000, Decimal("27172500.00")),
        ]
    )

    views = DuckDBViewLayer(silver, db_path=duckdb_path)
    views.connect()

    # 1. Column type is exact DECIMAL(18, 4), NOT VARCHAR!
    type_info = views.query("SELECT typeof(close) FROM silver_bhavcopy LIMIT 1")
    assert type_info[0][0] == "DECIMAL(18,4)"

    # 2. Numeric predicate works accurately: close >= 3000 returns 0 rows (not 1 from string comparison)
    rows_3000 = views.query("SELECT count(*) FROM silver_bhavcopy WHERE close >= 3000")
    assert rows_3000[0][0] == 0

    # 3. Numeric predicate: close >= 1000 returns INFY (1505.50), excludes RELIANCE (905.75)
    rows_1000 = views.query("SELECT isin FROM silver_bhavcopy WHERE close >= 1000")
    assert len(rows_1000) == 1
    assert rows_1000[0][0] == "INE009A01021"

    # 4. Aggregates like avg(close) compute without BinderException
    avg_close = views.query("SELECT avg(close) FROM silver_bhavcopy")
    # (1505.50 + 905.75) / 2 = 1205.625
    assert abs(avg_close[0][0] - 1205.625) < 0.001

    views.close()


# -----------------------------------------------------------------------------
# E-5: VIEW LAYER FAILS CLOSED ON CORRUPT PARTITION
# -----------------------------------------------------------------------------
def test_e5_view_layer_fails_closed_on_corrupt_partition(sample_calendar: TradingCalendar, temp_storage_dirs):
    _, silver_dir, duckdb_path = temp_storage_dirs
    silver = SilverStorage(silver_dir, calendar=sample_calendar)

    # Write a valid partition
    d8 = datetime.date(2024, 1, 8)
    p = silver.write_daily_partition(
        d8,
        [
            SilverRecord("INE009A01021", "INFY", "EQ", d8, Decimal("1500.00"), Decimal("1510.00"), Decimal("1490.00"), Decimal("1505.00"), 1000)
        ]
    )

    # Deliberately corrupt the parquet file by truncating it
    with open(p, "wb") as f:
        f.write(b"PAR1corrupt_garbage_header_and_truncated_content")

    views = DuckDBViewLayer(silver, db_path=duckdb_path)
    # Connecting/registering views must fail closed with DuckDBViewError, NOT return count(*)=0!
    with pytest.raises(DuckDBViewError, match="Archive may be corrupt"):
        views.connect()


# -----------------------------------------------------------------------------
# E-6: CONTENT-ADDRESSED BRONZE WITH IMMUTABLE RESTATEMENTS
# -----------------------------------------------------------------------------
def test_e6_bronze_content_addressed_and_immutable_restatements(temp_storage_dirs):
    bronze_dir, _, _ = temp_storage_dirs
    bronze = BronzeStorage(bronze_dir)

    payload_v1 = b"TRADE_DATE,ISIN,CLOSE\n2024-01-10,INE009A01021,1500.00\n"
    payload_v2 = b"TRADE_DATE,ISIN,CLOSE\n2024-01-10,INE009A01021,1505.00\n"  # restated close

    rel_path = "bhavcopy/2024/2024-01-10.csv"
    e1 = bronze.store_payload(rel_path, payload_v1, source_url="https://archives.nse.test/bhav_v1.csv")
    assert e1.sha256 is not None

    # 1. Attempting to overwrite existing path with different bytes without restatement_ref fails closed
    with pytest.raises(BronzeStorageError, match="without an explicit restatement_ref"):
        bronze.store_payload(rel_path, payload_v2, source_url="https://archives.nse.test/bhav_v2.csv")

    # 2. Providing explicit restatement_ref succeeds and records new content-addressed blob
    e2 = bronze.store_payload(
        rel_path,
        payload_v2,
        source_url="https://archives.nse.test/bhav_v2.csv",
        restatement_ref="NSE/RESTATEMENT/CIRCULAR_2024_01",
    )
    assert e2.sha256 != e1.sha256

    # 3. BOTH historical v1 and restated v2 blobs exist and remain fully verifiable!
    data_v1 = bronze.read_payload(rel_path, sha256_digest=e1.sha256, verify=True)
    assert data_v1 == payload_v1

    data_v2 = bronze.read_payload(rel_path, sha256_digest=e2.sha256, verify=True)
    assert data_v2 == payload_v2

    # Latest read returns v2
    assert bronze.read_payload(rel_path, verify=True) == payload_v2

    # 4. Tampering a blob fails closed
    blob_file = bronze.get_blob_path(e1.sha256)
    with open(blob_file, "wb") as f:
        f.write(b"tampered content")

    with pytest.raises(TamperedBronzePayloadError):
        bronze.read_payload(rel_path, sha256_digest=e1.sha256, verify=True)


# -----------------------------------------------------------------------------
# E-8: SECURITY MASTER REJECTS DUPLICATE DELISTINGS AND TRANSITIONS
# -----------------------------------------------------------------------------
def test_e8_security_master_rejects_duplicates():
    syms = [
        SymbolInterval("INE001A01036", "HDFC", "EQ", datetime.date(2015, 1, 1), datetime.date(2023, 7, 13)),
    ]
    # Duplicate delisting for same ISIN
    dup_delistings = [
        DelistingEvent("INE001A01036", datetime.date(2023, 7, 13), "MERGER"),
        DelistingEvent("INE001A01036", datetime.date(2023, 7, 14), "MERGER_ALT"),
    ]
    with pytest.raises(SecurityMasterError, match="Duplicate delisting event detected"):
        SecurityMaster(symbol_intervals=syms, delisting_events=dup_delistings)

    # Duplicate transition for same old ISIN
    dup_transitions = [
        ISINTransitionEvent("INE704P01017", "INE704P01025", datetime.date(2024, 1, 10), "SPLIT"),
        ISINTransitionEvent("INE704P01017", "INE704P01099", datetime.date(2024, 1, 11), "SPLIT_ALT"),
    ]
    with pytest.raises(SecurityMasterError, match="Duplicate ISIN transition event detected"):
        SecurityMaster(symbol_intervals=syms, isin_transitions=dup_transitions)


def test_calendar_contracts_and_navigation(sample_calendar: TradingCalendar):
    cal = sample_calendar
    assert cal.total_sessions == 5
    assert cal.start_date == datetime.date(2024, 1, 8)
    assert cal.end_date == datetime.date(2024, 1, 12)
    assert cal.is_session(datetime.date(2024, 1, 10))
    assert not cal.is_session(datetime.date(2024, 1, 13))

    assert cal.next_session(datetime.date(2024, 1, 9)) == datetime.date(2024, 1, 10)
    assert cal.previous_session(datetime.date(2024, 1, 10)) == datetime.date(2024, 1, 9)
    assert cal.advance_sessions(datetime.date(2024, 1, 8), 2) == datetime.date(2024, 1, 10)


def test_gate_g2b5_3_isin_transition_and_delisting_exact_date_pruning():
    sec_master = build_production_security_master()

    # 1. HDFC Delisting (INE001A01036) effective 2023-07-13
    pre_delisting = datetime.date(2023, 7, 12)
    on_delisting = datetime.date(2023, 7, 13)

    assert sec_master.is_active("INE001A01036", pre_delisting) is True
    assert "INE001A01036" in sec_master.active_isins_on(pre_delisting)

    assert sec_master.is_delisted("INE001A01036", on_delisting) is True
    assert sec_master.is_active("INE001A01036", on_delisting) is False
    assert "INE001A01036" not in sec_master.active_isins_on(on_delisting)

    # 2. COCHINSHIP ISIN Transition: INE704P01017 -> INE704P01025 effective 2024-01-10
    pre_transition = datetime.date(2024, 1, 9)
    on_transition = datetime.date(2024, 1, 10)

    assert sec_master.is_active("INE704P01017", pre_transition) is True
    assert sec_master.is_active("INE704P01025", pre_transition) is False
    assert "INE704P01017" in sec_master.active_isins_on(pre_transition)
    assert "INE704P01025" not in sec_master.active_isins_on(pre_transition)

    assert sec_master.is_transitioned_out("INE704P01017", on_transition) is True
    assert sec_master.is_active("INE704P01017", on_transition) is False
    assert sec_master.is_active("INE704P01025", on_transition) is True
    assert "INE704P01017" not in sec_master.active_isins_on(on_transition)
    assert "INE704P01025" in sec_master.active_isins_on(on_transition)


def test_gate_g2b5_7_no_session_before_2018_can_reach_go_verdict():
    warmup_start = datetime.date(2017, 1, 1)
    warmup_end = datetime.date(2017, 12, 31)
    binding_start = datetime.date(2018, 4, 1)
    binding_end = datetime.date(2023, 12, 31)

    assert classify_gating_window(warmup_start, warmup_end) == GatingWindowClassification.PRE_SURVEILLANCE_WARMUP
    assert classify_gating_window(binding_start, binding_end) == GatingWindowClassification.BINDING_EVALUATION

    with pytest.raises(GatingWindowValidationError, match="Gate G2B.5-7 Violation"):
        check_gating_verdict_eligibility(warmup_start, "GO")
    with pytest.raises(GatingWindowValidationError, match="Gate G2B.5-7 Violation"):
        check_gating_verdict_eligibility(warmup_start, "APPROVED")
    with pytest.raises(GatingWindowValidationError, match="Gate G2B.5-7 Violation"):
        check_gating_verdict_eligibility(warmup_start, "PASS")

    check_gating_verdict_eligibility(binding_start, "GO")

    assert resolve_gating_verdict(warmup_start, "GO") == "NOT RUN"
    assert resolve_gating_verdict(warmup_start, "PASS") == "NOT RUN"
    assert resolve_gating_verdict(binding_start, "GO") == "GO"
    assert resolve_gating_verdict(binding_start, "NO-GO") == "NO-GO"


def test_f1_f2_f3_remediation(sample_calendar, temp_storage_dirs):
    """
    Tests remediation of findings F-1, F-2, and F-3:
    F-1: fail_closed_on_missing parameter deleted; GoldEngine unconditionally fails closed.
    F-2: compute_calendar_fingerprint covers session type and open/close hours.
    F-3: PriceBar carries session_type, session_records_in_range and full_sessions_only work.
    """
    import inspect
    from signal_core.storage.security_master import build_production_security_master

    sec_master = build_production_security_master()
    _, silver_dir, _ = temp_storage_dirs
    silver = SilverStorage(silver_dir, calendar=sample_calendar)
    gold = GoldEngine(silver, sample_calendar, sec_master)

    # F-1: Parameter deleted and attempts to pass it raise TypeError
    sig_load = inspect.signature(gold.load_price_panel)
    assert "fail_closed_on_missing" not in sig_load.parameters

    sig_snapshot = inspect.signature(gold.build_dataset_snapshot)
    assert "fail_closed_on_missing" not in sig_snapshot.parameters

    with pytest.raises(TypeError):
        gold.load_price_panel(
            datetime.date(2024, 1, 8),
            datetime.date(2024, 1, 10),
            fail_closed_on_missing=False,  # type: ignore
        )

    # F-2: Fingerprint changes when session type or hours change
    rec_full = TradingSessionRecord(datetime.date(2024, 11, 1), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Full")
    rec_muhurat = TradingSessionRecord(datetime.date(2024, 11, 1), SessionType.MUHURAT, datetime.time(18, 0), datetime.time(19, 0), "Diwali Muhurat")

    fpr_full = compute_calendar_fingerprint([rec_full])
    fpr_muhurat = compute_calendar_fingerprint([rec_muhurat])
    assert fpr_full != fpr_muhurat

    # F-3: PriceBar carries session_type and calendar filtering works
    cal_with_muhurat = TradingCalendar(
        calendar_id="CAL-MUHURAT-TEST",
        market="NSE_CASH",
        session_records=(
            TradingSessionRecord(datetime.date(2024, 10, 31), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
            rec_muhurat,
            TradingSessionRecord(datetime.date(2024, 11, 4), SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular"),
        ),
        binding_start_date=datetime.date(2018, 4, 1),
        fingerprint="CAL-FPR-V1-test",
        provenance={"source": "TEST"},
        annual_session_counts={"2024": 3},
    )

    all_sessions = cal_with_muhurat.sessions_in_range(datetime.date(2024, 10, 31), datetime.date(2024, 11, 4))
    assert len(all_sessions) == 3

    full_only = cal_with_muhurat.sessions_in_range(datetime.date(2024, 10, 31), datetime.date(2024, 11, 4), full_sessions_only=True)
    assert len(full_only) == 2
    assert datetime.date(2024, 11, 1) not in full_only

    records_range = cal_with_muhurat.session_records_in_range(datetime.date(2024, 10, 31), datetime.date(2024, 11, 4))
    assert records_range[1].session_type == SessionType.MUHURAT

    # PriceBar carries session_type
    bar = PriceBar(
        instrument_id="INE009A01021",
        trade_date=datetime.date(2024, 11, 1),
        open=Decimal("1500.00"),
        high=Decimal("1520.00"),
        low=Decimal("1495.00"),
        close=Decimal("1510.00"),
        volume=10000,
        session_type="MUHURAT",
    )
    assert bar.session_type == "MUHURAT"


# -----------------------------------------------------------------------------
# H-1: PHYSICAL HOLDOUT SEPARATION IN STORAGE (Audit §27)
# -----------------------------------------------------------------------------
def test_h1_physical_holdout_separation_silver_rejection(temp_storage_dirs):
    """
    Finding H-1: Standard silver storage explicitly rejects writing or reading
    dates falling within sealed holdout window [2025-01-01, 2026-11-11] fail-closed.
    Dedicated holdout storage (is_holdout_storage=True) is required.
    """
    _, silver_dir, _ = temp_storage_dirs
    standard_silver = SilverStorage(silver_dir, is_holdout_storage=False)
    holdout_dir = silver_dir.parent / "storage_holdout"
    holdout_silver = SilverStorage(holdout_dir, is_holdout_storage=True)

    holdout_date = datetime.date(2025, 1, 15)
    rec = SilverRecord(
        isin="INE009A01021",
        symbol="INFY",
        series="EQ",
        trade_date=holdout_date,
        open=Decimal("1800.00"),
        high=Decimal("1820.00"),
        low=Decimal("1790.00"),
        close=Decimal("1810.00"),
        volume=10000,
        traded_value=Decimal("18100000.00"),
    )

    # 1. Standard storage MUST reject writing holdout session fail-closed (P12a)
    with pytest.raises(HoldoutPartitionIsolationError, match="explicitly rejects dates falling within"):
        standard_silver.write_daily_partition(holdout_date, [rec])

    # 2. Standard storage MUST reject reading holdout session fail-closed (P12c)
    with pytest.raises(HoldoutPartitionIsolationError, match="explicitly rejects dates falling within"):
        standard_silver.read_daily_partition(holdout_date)

    # 3. Standard storage MUST reject partition_exists query on holdout session fail-closed (P12d / H-12)
    with pytest.raises(HoldoutPartitionIsolationError, match="cannot query existence of partitions in holdout window"):
        standard_silver.partition_exists(holdout_date)

    # 4. Probe P12b / H-12: is_holdout_storage=True on STANDARD root directory without 'holdout' fails closed
    with pytest.raises(SilverStorageError, match="must be an explicit segregated holdout root"):
        SilverStorage(silver_dir, is_holdout_storage=True)

    # 5. Probe P19 / H-17: is_holdout_storage=True inside standard silver tree fails closed (path containment)
    with pytest.raises(SilverStorageError, match="cannot be located inside a standard silver tree"):
        SilverStorage(silver_dir / "holdout", is_holdout_storage=True)

    # 6. Dedicated segregated holdout storage is permitted to write and read holdout session
    partition_path = holdout_silver.write_daily_partition(holdout_date, [rec])
    assert partition_path.is_file()
    assert holdout_silver.partition_exists(holdout_date) is True
    read_recs = holdout_silver.read_daily_partition(holdout_date)
    assert len(read_recs) == 1
    assert read_recs[0].trade_date == holdout_date


def test_n30_non_overlapping_sourced_core_interval_appended(monkeypatch):
    """
    Finding N-30: build_production_security_master() appends non-overlapping sourced intervals
    for core symbols rather than silently dropping them.
    """
    from signal_core.storage.security_master import (
        SymbolInterval,
        build_production_security_master,
    )
    import signal_core.storage.security_master as sm_mod

    # Mock load_cash_universe_symbol_intervals to return an earlier non-overlapping interval for INFY
    # (e.g. 2010-01-01 to 2014-12-31, while core INFY starts at 2015-01-01)
    non_overlap_infy = SymbolInterval(
        isin="INE009A01021",
        symbol="INFY",
        series="EQ",
        effective_from=datetime.date(2010, 1, 1),
        effective_to=datetime.date(2014, 12, 31),
    )

    monkeypatch.setattr(
        sm_mod,
        "load_cash_universe_symbol_intervals",
        lambda: [non_overlap_infy],
    )

    sm = build_production_security_master(include_cash_universe=True)

    # Both the earlier sourced interval and the core interval are present and resolve correctly
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2012, 6, 1)) == "INE009A01021"
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2020, 6, 1)) == "INE009A01021"


def test_n33_partial_overlap_complement_appended(monkeypatch):
    """
    Finding N-33: build_production_security_master() performs segment complement subtraction
    for partially overlapping sourced intervals so pre-core tails are preserved rather than dropped whole.
    """
    from signal_core.storage.security_master import (
        SymbolInterval,
        build_production_security_master,
    )
    import signal_core.storage.security_master as sm_mod

    # Case B from Audit §42.7:
    # Sourced interval covers 2010-01-01..2020-12-31, while core INFY starts at 2015-01-01
    overlapping_infy = SymbolInterval(
        isin="INE009A01021",
        symbol="INFY",
        series="EQ",
        effective_from=datetime.date(2010, 1, 1),
        effective_to=datetime.date(2020, 12, 31),
    )

    monkeypatch.setattr(
        sm_mod,
        "load_cash_universe_symbol_intervals",
        lambda: [overlapping_infy],
    )

    sm = build_production_security_master(include_cash_universe=True)

    # Pre-core tail (2010-01-01..2015-01-01) is preserved via segment complement
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2012, 6, 1)) == "INE009A01021"
    # Core interval (2015-01-01 onwards) resolves correctly
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2016, 6, 1)) == "INE009A01021"
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2023, 1, 1)) == "INE009A01021"



