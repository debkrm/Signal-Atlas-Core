"""
Unit tests for Price Band Intervals, As-Of Resolution, and Missing Band Fail-Closed Enforcement.
Addresses Audit Finding H-30 per AGENTS.md Rule 5.3, Rule 10.5, and Rule 10.7 (Audit §31 / §34).
"""

import datetime
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import zipfile
import pytest

from signal_core.contracts.exchange_series import APPROVED_EQ_ONLY_POLICY
from signal_core.contracts.price_band import (
    PriceBandInterval,
    PriceBandPublicationSource,
    PriceBandRecord,
    PriceBandSourceDescriptor,
    PriceBandValidationError,
)
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.research.containment import PartitionRole, WalkForwardFold
from signal_core.research.trials import TrialRegistry
from signal_core.research.walkforward import (
    WalkForwardEngine,
    WalkForwardEngineError,
)
from signal_core.storage.bronze import BronzeStorage
from signal_core.storage.calendar import (
    SessionType,
    TradingCalendar,
    TradingSessionRecord,
    compute_calendar_fingerprint,
)
from signal_core.storage.gold import GoldEngine
from signal_core.storage.ingest import (
    PriceBandIngestError,
    ingest_daily_price_bands,
    parse_price_band_report,
)
from signal_core.storage.security_master import (
    SecurityMaster,
    SecurityMasterError,
    SymbolInterval,
    build_production_security_master,
)
from signal_core.storage.silver import SilverRecord, SilverStorage
from signal_core.strategy.base import OrderIntent, Strategy


@pytest.fixture
def test_calendar() -> TradingCalendar:
    dates = [
        datetime.date(2024, 1, 8),
        datetime.date(2024, 1, 9),
        datetime.date(2024, 1, 10),
        datetime.date(2024, 1, 11),
        datetime.date(2024, 1, 12),
        datetime.date(2024, 1, 15),
        datetime.date(2024, 1, 16),
        datetime.date(2024, 1, 17),
        datetime.date(2024, 1, 18),
        datetime.date(2024, 1, 19),
    ]
    records = tuple(
        TradingSessionRecord(d, SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular")
        for d in dates
    )
    fpr = compute_calendar_fingerprint(records)
    return TradingCalendar(
        calendar_id="H30-TEST-CAL",
        market="NSE_CASH",
        session_records=records,
        binding_start_date=datetime.date(2018, 4, 1),
        fingerprint=fpr,
        provenance={"source": "H30_TEST"},
        annual_session_counts={"2024": 10},
    )


# ==============================================================================
# 1. PriceBandInterval Contract & Validation Tests
# ==============================================================================

def test_price_band_interval_validation_invariants():
    """Verify PriceBandInterval validations for constrained and unconstrained scrips."""
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_TEST_BANDS",
        archive_url_template="https://archives.nseindia.com/test.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/SURV/01",
    )

    # 1. Valid constrained interval
    pbi = PriceBandInterval(
        isin="INE009A01021",
        band_percentage=Decimal("20.00"),
        effective_from=datetime.date(2024, 1, 1),
        effective_to=datetime.date(2024, 12, 31),
        source_descriptor=source_desc,
        circular_ref="NSE/SURV/01",
    )
    assert pbi.contains(datetime.date(2024, 1, 1)) is True
    assert pbi.contains(datetime.date(2024, 6, 15)) is True
    assert pbi.contains(datetime.date(2024, 12, 31)) is False  # half-open [from, to)

    # 2. Roundtrip serialization
    d = pbi.to_dict()
    recovered = PriceBandInterval.from_dict(d)
    assert recovered.isin == pbi.isin
    assert recovered.band_percentage == pbi.band_percentage
    assert recovered.effective_from == pbi.effective_from
    assert recovered.effective_to == pbi.effective_to

    # 3. Constrained interval without band_percentage is rejected
    with pytest.raises(PriceBandValidationError, match="requires band_percentage"):
        PriceBandInterval(
            isin="INE009A01021",
            effective_from=datetime.date(2024, 1, 1),
            band_percentage=None,
            is_unconstrained=False,
        )

    # 4. Unconstrained interval without citation is rejected
    with pytest.raises(PriceBandValidationError, match="requires an authoritative source_descriptor or circular_ref"):
        PriceBandInterval(
            isin="INE009A01021",
            effective_from=datetime.date(2024, 1, 1),
            band_percentage=Decimal("10.00"),
            is_unconstrained=True,
            source_descriptor=None,
            circular_ref=None,
        )

    # 5. Unconstrained interval with band_percentage=None is accepted with citation (Audit §35 H-41)
    pbi_unconstrained = PriceBandInterval(
        isin="INE009A01021",
        effective_from=datetime.date(2024, 1, 1),
        band_percentage=None,
        is_unconstrained=True,
        circular_ref="NSE/FAOP/01",
    )
    assert pbi_unconstrained.band_percentage is None
    assert pbi_unconstrained.is_unconstrained is True

    # 6. Inverted dates (effective_from >= effective_to) are rejected
    with pytest.raises(PriceBandValidationError, match="must precede effective_to"):
        PriceBandInterval(
            isin="INE009A01021",
            band_percentage=Decimal("20.00"),
            effective_from=datetime.date(2024, 5, 1),
            effective_to=datetime.date(2024, 4, 1),
        )


# ==============================================================================
# 2. SecurityMaster Interval Lookup & Non-Overlap Invariants
# ==============================================================================

def test_security_master_interval_overlap_rejection():
    """SecurityMaster must reject overlapping PriceBandIntervals for same ISIN."""
    syms = [
        SymbolInterval("INE009A01021", "INFY", "EQ", datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
    ]
    overlapping_bands = [
        PriceBandInterval(
            isin="INE009A01021",
            band_percentage=Decimal("20.00"),
            effective_from=datetime.date(2024, 1, 1),
            effective_to=datetime.date(2024, 6, 1),
        ),
        PriceBandInterval(
            isin="INE009A01021",
            band_percentage=Decimal("10.00"),
            effective_from=datetime.date(2024, 5, 1),  # Overlaps!
            effective_to=datetime.date(2024, 12, 31),
        ),
    ]
    with pytest.raises(SecurityMasterError, match="Overlapping or unclosed price band intervals"):
        SecurityMaster(symbol_intervals=syms, price_band_intervals=overlapping_bands)


def test_security_master_as_of_resolution_and_precedence():
    """Discrete daily PriceBandRecord takes precedence over time-varying interval."""
    syms = [
        SymbolInterval("INE704P01025", "COCHINSHIP", "EQ", datetime.date(2024, 1, 10), None)
    ]
    intervals = [
        PriceBandInterval(
            isin="INE704P01025",
            band_percentage=Decimal("20.00"),
            effective_from=datetime.date(2024, 1, 10),
            circular_ref="NSE/SURV/2024",
        )
    ]
    discrete_split_band = PriceBandRecord(
        isin="INE704P01025",
        trade_date=datetime.date(2024, 1, 10),
        series="EQ",
        upper_circuit_limit=Decimal("802.80"),
        lower_circuit_limit=Decimal("535.20"),
        band_percentage=Decimal("20.00"),
        source_ref="NSE/CML/60114",
    )

    sm = SecurityMaster(
        symbol_intervals=syms,
        price_bands=[discrete_split_band],
        price_band_intervals=intervals,
    )

    # 1. On Jan 10: discrete record with explicit limits is returned
    band_jan10 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 10))
    assert band_jan10 is not None
    assert band_jan10.upper_circuit_limit == Decimal("802.80")
    assert band_jan10.lower_circuit_limit == Decimal("535.20")
    assert band_jan10.has_circuit_evidence is True

    # 2. On Jan 11 (day after): synthesized from interval, NOT None (resolves H-30 exact-date limitation)
    # Without prev_close: upper/lower limits are None, has_circuit_evidence is False (Audit §35 H-40)
    band_jan11 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11))
    assert band_jan11 is not None
    assert band_jan11.band_percentage == Decimal("20.00")
    assert band_jan11.trade_date == datetime.date(2024, 1, 11)
    assert band_jan11.upper_circuit_limit is None
    assert band_jan11.lower_circuit_limit is None
    assert band_jan11.has_circuit_evidence is False

    # With prev_close=802.80: derived limits tick-rounded (Audit §36 Note N-7: upper down to 963.35, lower up to 642.25)
    band_jan11_derived = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11), prev_close=Decimal("802.80"))
    assert band_jan11_derived is not None
    assert band_jan11_derived.upper_circuit_limit == Decimal("963.35")
    assert band_jan11_derived.lower_circuit_limit == Decimal("642.25")
    assert band_jan11_derived.has_circuit_evidence is True

    # 3. Before effective_from (Jan 9): outside interval and no discrete band -> returns None
    assert sm.get_price_band("INE704P01025", datetime.date(2024, 1, 9)) is None


# ==============================================================================
# 3. Production Security Master Audit (§31.3 measurements)
# ==============================================================================

def test_production_security_master_h30_audit_closure():
    """
    Verifies that build_production_security_master() closes every measurement in Audit §31.3 / §35:
    - INE704P01025 on 2024-01-10 returns ex-split upper circuit at 802.80.
    - INE704P01025 on 2024-01-11 and 2024-01-12 returns valid 20% interval bands with derived limits.
    - INFY (INE009A01021) and RELIANCE (INE002A01018) return unconstrained F&O bands ("No Band") with NSE citations.
    """
    sm = build_production_security_master()

    # Measured: get_price_band("INE704P01025", 2024-01-10) is NO LONGER None
    band_split = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 10))
    assert band_split is not None
    assert band_split.upper_circuit_limit == Decimal("802.80")
    assert band_split.lower_circuit_limit == Decimal("535.20")
    assert band_split.band_percentage == Decimal("20.00")
    assert band_split.has_circuit_evidence is True

    # Audit §36 H-43 & Note N-8: Hand-authored 20% removed from baseline intervals for COCHINSHIP.
    # Baseline interval master now honestly encodes COCHINSHIP as unconstrained ("No Band" under F&O framework).
    # On Jan 11 without daily records, resolves to unconstrained with band_percentage=None and no circuit evidence:
    band_jan11 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11))
    assert band_jan11 is not None
    assert band_jan11.is_unconstrained is True
    assert band_jan11.band_percentage is None
    assert band_jan11.upper_circuit_limit is None
    assert band_jan11.has_circuit_evidence is False

    # Calling derive_limits with prev_close on unconstrained scrip does NOT derive static limits (Audit §36 Note N-8)
    band_jan11_derived = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11), prev_close=Decimal("802.80"))
    assert band_jan11_derived.upper_circuit_limit is None
    assert band_jan11_derived.lower_circuit_limit is None
    assert band_jan11_derived.has_circuit_evidence is False

    band_jan12 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 12))
    assert band_jan12 is not None
    assert band_jan12.is_unconstrained is True
    assert band_jan12.band_percentage is None
    assert band_jan12.upper_circuit_limit is None
    assert band_jan12.has_circuit_evidence is False

    # INFY unconstrained F&O stock (Audit §35 H-41: exchange publishes "No Band", band_percentage=None)
    band_infy = sm.get_price_band("INE009A01021", datetime.date(2024, 1, 15))
    assert band_infy is not None
    assert band_infy.is_unconstrained is True
    assert band_infy.band_percentage is None
    assert band_infy.source_descriptor is not None
    assert band_infy.source_descriptor.circular_ref == "NSE/FAOP/60350"
    assert band_infy.has_circuit_evidence is False

    # RELIANCE unconstrained F&O stock (Audit §35 H-41: exchange publishes "No Band", band_percentage=None)
    band_rel = sm.get_price_band("INE002A01018", datetime.date(2024, 1, 15))
    assert band_rel is not None
    assert band_rel.is_unconstrained is True
    assert band_rel.band_percentage is None
    assert band_rel.source_descriptor.circular_ref == "NSE/FAOP/60350"
    assert band_rel.has_circuit_evidence is False


# ==============================================================================
# 4. Fail-Closed Missing Band Day in Walk-Forward Engine (H-30)
# ==============================================================================

def test_walkforward_fail_closed_on_missing_price_band(test_calendar):
    """
    Audit §31 H-30: A session with no price band row for an instrument that trades
    must fail closed rather than evaluate without limits.
    """
    with tempfile.TemporaryDirectory(prefix="h30_wf_") as tmpdir:
        tmp_path = Path(tmpdir)
        silver_dir = tmp_path / "silver"
        silver = SilverStorage(silver_dir, calendar=test_calendar)

        # Unbanded security master: INFY is active, but zero price bands or intervals registered
        sec_master_unbanded = SecurityMaster(
            symbol_intervals=[
                SymbolInterval(
                    isin="INE009A01021",
                    symbol="INFY",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                )
            ]
        )

        for d in test_calendar.sessions:
            silver.write_daily_partition(
                d,
                [
                    SilverRecord(
                        isin="INE009A01021",
                        symbol="INFY",
                        series="EQ",
                        trade_date=d,
                        open=Decimal("1500.00"),
                        high=Decimal("1520.00"),
                        low=Decimal("1490.00"),
                        close=Decimal("1510.00"),
                        volume=500000,
                        traded_value=Decimal("750000000"),
                    )
                ],
            )

        gold = GoldEngine(silver, test_calendar, sec_master_unbanded)
        fold = WalkForwardFold(
            fold_index=0,
            train_start=datetime.date(2024, 1, 8),
            train_end=datetime.date(2024, 1, 11),
            test_start=datetime.date(2024, 1, 15),
            test_end=datetime.date(2024, 1, 19),
            embargo_sessions=1,
            partition_role=PartitionRole.VALIDATION,
        )

        class Buyer(Strategy):
            @property
            def strategy_id(self) -> str:
                return "H30-BUYER"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 15):
                    return (
                        OrderIntent(
                            instrument_id="INE009A01021",
                            signal_date=as_of,
                            target_date=next_session,
                            side=OrderSide.BUY,
                            quantity=10,
                        ),
                    )
                return ()

        # Default fail_closed_on_missing_band=True MUST raise WalkForwardEngineError
        engine = WalkForwardEngine(calendar=test_calendar, gold_engine=gold)
        with pytest.raises(WalkForwardEngineError, match="Finding H-30 Violation"):
            engine.run_walk_forward(strategy=Buyer(), folds=[fold])

        # Permissive mode (fail_closed_on_missing_band=False) evaluates without limits,
        # but flags verification_status as CIRCUIT_UNVERIFIED
        engine_permissive = WalkForwardEngine(
            calendar=test_calendar,
            gold_engine=gold,
            fail_closed_on_missing_band=False,
        )
        res = engine_permissive.run_walk_forward(strategy=Buyer(), folds=[fold])
        assert res.circuit_evidence_complete is False
        assert res.verification_status == "CIRCUIT_UNVERIFIED"

        # Publishing or trial registration of CIRCUIT_UNVERIFIED is strictly blocked
        reg_file = tmp_path / "trials.jsonl"
        reg = TrialRegistry(reg_file)
        with pytest.raises(WalkForwardEngineError, match="Cannot register trial in trial registry with verification_status='CIRCUIT_UNVERIFIED'"):
            res.register_in_trial_registry(
                registry=reg,
                trial_id="TRIAL-H30-UNV",
                hypothesis="Fail closed",
                rationale="Unverified circuit",
                fold_spec_fingerprint="TEST",
            )


# ==============================================================================
# 5. Price Band Report Parsing & Bronze Ingest Invariants
# ==============================================================================

def test_parse_price_band_report_csv_and_reverse_lookup():
    """Verify parse_price_band_report on CSV data with symbol-to-ISIN resolution."""
    csv_content = (
        "Symbol,Series,Security Name,Band,Upper Price Band,Lower Price Band\n"
        "INFY,EQ,Infosys Limited,No Band,,\n"
        "RELIANCE,EQ,Reliance Industries Limited,No Band,,\n"
        "COCHINSHIP,EQ,Cochin Shipyard Limited,20%,960.00,640.00\n"
    )

    sm = build_production_security_master()
    t_date = datetime.date(2024, 1, 15)

    trade_date, records = parse_price_band_report(
        report_data=csv_content.encode("utf-8"),
        trade_date=t_date,
        security_master=sm,
    )

    assert trade_date == t_date
    assert len(records) == 3

    by_isin = {r.isin: r for r in records}
    # INFY resolved to INE009A01021, unconstrained (Audit §35 H-41: No Band -> band_percentage=None)
    assert "INE009A01021" in by_isin
    assert by_isin["INE009A01021"].is_unconstrained is True
    assert by_isin["INE009A01021"].band_percentage is None
    assert by_isin["INE009A01021"].has_circuit_evidence is False

    # COCHINSHIP resolved to INE704P01025 on Jan 15 2024
    assert "INE704P01025" in by_isin
    assert by_isin["INE704P01025"].upper_circuit_limit == Decimal("960.00")
    assert by_isin["INE704P01025"].lower_circuit_limit == Decimal("640.00")
    assert by_isin["INE704P01025"].band_percentage == Decimal("20.00")
    assert by_isin["INE704P01025"].has_circuit_evidence is True


def test_ingest_daily_price_bands_bronze_provenance():
    """Verify ingest_daily_price_bands stores byte-exact payload in Bronze with SHA-256."""
    with tempfile.TemporaryDirectory(prefix="h30_bronze_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze = BronzeStorage(tmp_path / "bronze")

        csv_content = (
            "ISIN,SYMBOL,SERIES,UPPER_LIMIT,LOWER_LIMIT,BAND_PERCENTAGE\n"
            "INE704P01025,COCHINSHIP,EQ,802.80,535.20,20.00\n"
        ).encode("utf-8")

        source_desc = PriceBandSourceDescriptor(
            source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
            publication_name="NSE_DAILY_BANDS_TEST",
            archive_url_template="https://archives.nseindia.com/sec_list.csv",
            retrieval_frequency="DAILY",
            circular_ref="NSE/SURV/TEST",
        )

        entry, records = ingest_daily_price_bands(
            bronze=bronze,
            report_bytes=csv_content,
            filename="sec_list_20240110.csv",
            source_url="https://archives.nseindia.com/sec_list_20240110.csv",
            trade_date=datetime.date(2024, 1, 10),
            source_descriptor=source_desc,
        )

        assert entry.byte_count == len(csv_content)
        assert len(records) == 1
        rec = records[0]
        assert rec.isin == "INE704P01025"
        assert rec.upper_circuit_limit == Decimal("802.80")
        assert rec.has_circuit_evidence is True

        # Verify payload retrievable from Bronze byte-exact
        retrieved = bronze.read_payload(entry.relative_path)
        assert retrieved == csv_content


def test_h40_probe_derived_upper_circuit_refusal(test_calendar):
    """
    Audit §35.2 Probe:
    With a 20% interval on a Rs 1,000.00 previous close, implied upper circuit is 1200.00.
    A BUY at open == 1200.00 MUST be rejected with REJECTED_UPPER_CIRCUIT fail-closed,
    rather than filled at 1201.80.
    """
    with tempfile.TemporaryDirectory(prefix="h40_probe_") as tmpdir:
        tmp_path = Path(tmpdir)
        silver_dir = tmp_path / "silver"
        silver = SilverStorage(silver_dir, calendar=test_calendar)

        target_isin = "INE704P01025"
        sec_master = SecurityMaster(
            symbol_intervals=[
                SymbolInterval(
                    isin=target_isin,
                    symbol="COCHINSHIP",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
            ],
            price_band_intervals=[
                PriceBandInterval(
                    isin=target_isin,
                    band_percentage=Decimal("20.00"),
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                    is_unconstrained=False,
                    source_descriptor=PriceBandSourceDescriptor(
                        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
                        publication_name="NSE_CASH_BANDS",
                        archive_url_template="https://archives.nseindia.com/sec_list.csv",
                        retrieval_frequency="DAILY",
                        circular_ref="NSE/SURV/TEST",
                    ),
                    circular_ref="NSE/SURV/TEST",
                ),
            ],
        )

        # Session 5 (Jan 15): prev close = 1000.00
        # Session 6 (Jan 16): open = 1200.00 (exactly at derived upper circuit: 1000 * 1.20 = 1200.00)
        for i, d in enumerate(test_calendar.sessions):
            if d == datetime.date(2024, 1, 15):
                p_open, p_high, p_low, p_close = Decimal("1000.00"), Decimal("1020.00"), Decimal("990.00"), Decimal("1000.00")
            elif d == datetime.date(2024, 1, 16):
                p_open, p_high, p_low, p_close = Decimal("1200.00"), Decimal("1200.00"), Decimal("1180.00"), Decimal("1190.00")
            else:
                p_open, p_high, p_low, p_close = Decimal("1000.00"), Decimal("1010.00"), Decimal("990.00"), Decimal("1000.00")

            silver.write_daily_partition(
                d,
                [
                    SilverRecord(
                        isin=target_isin,
                        symbol="COCHINSHIP",
                        series="EQ",
                        trade_date=d,
                        open=p_open,
                        high=p_high,
                        low=p_low,
                        close=p_close,
                        volume=100000,
                        traded_value=p_open * Decimal("100000"),
                    )
                ],
            )

        gold = GoldEngine(silver, test_calendar, sec_master)
        fold = WalkForwardFold(
            fold_index=0,
            train_start=datetime.date(2024, 1, 8),
            train_end=datetime.date(2024, 1, 12),
            test_start=datetime.date(2024, 1, 15),
            test_end=datetime.date(2024, 1, 19),
            embargo_sessions=1,
            partition_role=PartitionRole.VALIDATION,
        )

        class UpperCircuitBuyer(Strategy):
            @property
            def strategy_id(self) -> str:
                return "UPPER-CIRCUIT-BUYER"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 15):
                    return (
                        OrderIntent(
                            instrument_id=target_isin,
                            signal_date=as_of,
                            target_date=next_session,  # Jan 16
                            side=OrderSide.BUY,
                            quantity=10,
                        ),
                    )
                return ()

        engine = WalkForwardEngine(calendar=test_calendar, gold_engine=gold)
        res = engine.run_walk_forward(strategy=UpperCircuitBuyer(), folds=[fold])
        assert len(res.aggregate_trades) == 1
        trade = res.aggregate_trades[0]
        # §35.2 assertion: BUY at open == 1200.00 MUST be REJECTED_UPPER_CIRCUIT
        assert trade.status == FillStatus.REJECTED_UPPER_CIRCUIT
        assert trade.filled_quantity == 0
        assert trade.circuit_evidence_present is True


def test_h42_corrupt_band_row_fails_closed():
    """
    Audit §35 H-42: parse_price_band_report must fail closed when a row fails PriceBandRecord validation
    (e.g. lower_limit >= upper_limit), rather than silently deleting the corrupt row.
    """
    corrupt_csv = (
        "ISIN,SYMBOL,SERIES,UPPER_LIMIT,LOWER_LIMIT,BAND_PERCENTAGE\n"
        "INE704P01025,COCHINSHIP,EQ,500.00,800.00,20.00\n"  # Corrupt: lower > upper!
    ).encode("utf-8")

    with pytest.raises(PriceBandIngestError, match="PriceBandRecord validation failed.*Finding H-42"):
        parse_price_band_report(
            report_data=corrupt_csv,
            trade_date=datetime.date(2024, 1, 10),
        )


def test_n7_tick_rounding_derived_limits():
    """
    Audit §36 Note N-7:
    NSE publishes circuit limits on a Rs. 0.05 tick grid.
    Derived limits must round upper DOWN to tick and lower UP to tick:
    prev_close 1234.55 * 1.2 = 1481.4600 -> upper rounded down to 1481.45.
    prev_close 1234.55 * 0.8 = 987.6400  -> lower rounded up to 987.65.
    """
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_TEST_BANDS",
        archive_url_template="https://archives.nseindia.com/sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/TEST/01",
    )
    rec = PriceBandRecord(
        isin="INE704P01025",
        trade_date=datetime.date(2024, 1, 11),
        series="EQ",
        band_percentage=Decimal("20.00"),
        is_unconstrained=False,
        source_descriptor=source_desc,
    )
    derived = rec.derive_limits(Decimal("1234.55"))
    assert derived.upper_circuit_limit == Decimal("1481.45")
    assert derived.lower_circuit_limit == Decimal("987.65")
    assert (derived.upper_circuit_limit % Decimal("0.05")) == Decimal("0")
    assert (derived.lower_circuit_limit % Decimal("0.05")) == Decimal("0")
    assert derived.has_circuit_evidence is True


def test_n8_dynamic_flex_unconstrained_gated():
    """
    Audit §36 Note N-8:
    Derivation is only valid for fixed bands.
    For an unconstrained scrip with dynamic flexing bands (e.g. F&O underlying),
    derive_limits must NOT derive static fixed limits (returns self with None limits).
    """
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_FO_BANDS",
        archive_url_template="https://archives.nseindia.com/content/fo/fo_sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/FAOP/60350",
    )
    rec = PriceBandRecord(
        isin="INE009A01021",
        trade_date=datetime.date(2024, 1, 15),
        series="EQ",
        is_unconstrained=True,
        band_percentage=Decimal("10.00"),
        source_descriptor=source_desc,
        source_ref="NSE/FAOP/60350",
    )
    derived = rec.derive_limits(Decimal("1500.00"))
    assert derived.upper_circuit_limit is None
    assert derived.lower_circuit_limit is None
    assert derived.has_circuit_evidence is False


def test_n9_one_sided_observed_limits_preserved_and_validated():
    """
    Audit §36 Note N-9:
    A record with a one-sided observed limit must NOT have its authoritative limit silently overwritten.
    The missing side must be derived, and the observed side validated for consistency.
    """
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_TEST_BANDS",
        archive_url_template="https://archives.nseindia.com/sec_list.csv",
        retrieval_frequency="DAILY",
        circular_ref="NSE/TEST/01",
    )
    # Valid one-sided upper: upper=1200.00 observed, lower=None, pct=20.00, prev_close=1000.00
    rec_upper_only = PriceBandRecord(
        isin="INE704P01025",
        trade_date=datetime.date(2024, 1, 11),
        series="EQ",
        upper_circuit_limit=Decimal("1200.00"),
        lower_circuit_limit=None,
        band_percentage=Decimal("20.00"),
        is_unconstrained=False,
        source_descriptor=source_desc,
    )
    derived = rec_upper_only.derive_limits(Decimal("1000.00"))
    assert derived.upper_circuit_limit == Decimal("1200.00")  # Preserved observed limit!
    assert derived.lower_circuit_limit == Decimal("800.00")   # Filled missing side!
    assert derived.has_circuit_evidence is True

    # Inconsistent one-sided upper: observed upper=1100.00 contradicts derived upper=1200.00
    rec_contradicting = PriceBandRecord(
        isin="INE704P01025",
        trade_date=datetime.date(2024, 1, 11),
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=None,
        band_percentage=Decimal("20.00"),
        is_unconstrained=False,
        source_descriptor=source_desc,
    )
    with pytest.raises(PriceBandValidationError, match="Observed upper_circuit_limit.*contradicts derived upper"):
        rec_contradicting.derive_limits(Decimal("1000.00"))
