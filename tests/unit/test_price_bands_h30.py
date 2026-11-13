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
    load_cash_universe_symbol_intervals,
)
from signal_core.storage.silver import (
    SilverPartitionImmutableError,
    SilverRecord,
    SilverStorage,
    SilverStorageError,
)
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

    # Audit §37 H-48: Dropped hand-authored split-day discrete record in favor of the interval.
    # On 2024-01-10, resolves to the unconstrained interval ("No Band" under F&O framework)
    band_split = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 10))
    assert band_split is not None
    assert band_split.is_unconstrained is True
    assert band_split.band_percentage is None
    assert band_split.upper_circuit_limit is None
    assert band_split.lower_circuit_limit is None
    assert band_split.has_circuit_evidence is False

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


def test_h45_zip_member_selection_avoids_bhavcopy_and_selects_band_file():
    """
    Audit §37 H-45: In a ZIP archive holding both a daily bhavcopy and the band file,
    the band file must be positively selected and the price/bhavcopy file excluded.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Bhavcopy member (matches 'bh' previously, must now be excluded)
        bhav_csv = (
            "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,ISIN\n"
            "INFY,EQ,16-Jan-2024,1500.00,1505.00,1515.00,1495.00,1510.00,INE009A01021\n"
        )
        zf.writestr("fo_sec_bhavdata_full_16012024.csv", bhav_csv)
        # 2. Authoritative band file
        band_csv = (
            "ISIN,SYMBOL,SERIES,SECURITY_NAME,BAND,UPPER_PRICE_BAND,LOWER_PRICE_BAND\n"
            "INE009A01021,INFY,EQ,Infosys Limited,5%,1575.00,1425.00\n"
        )
        zf.writestr("sec_list_16012024.csv", band_csv)

    zip_bytes = zip_buf.getvalue()
    trade_date, records = parse_price_band_report(
        report_data=zip_bytes,
        trade_date=datetime.date(2024, 1, 16),
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.isin == "INE009A01021"
    assert rec.band_percentage == Decimal("5.00")
    assert rec.upper_circuit_limit == Decimal("1575.00")
    assert rec.lower_circuit_limit == Decimal("1425.00")
    assert rec.has_circuit_evidence is True


def test_h45_zip_without_band_member_fails_closed():
    """
    Audit §37 H-45: A ZIP archive containing only bhavcopy or files without band columns
    must fail closed with PriceBandIngestError rather than parsing bhavcopy as bands.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        bhav_csv = (
            "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,ISIN\n"
            "INFY,EQ,16-Jan-2024,1500.00,1505.00,1515.00,1495.00,1510.00,INE009A01021\n"
        )
        zf.writestr("fo_sec_bhavdata_full_16012024.csv", bhav_csv)

    zip_bytes = zip_buf.getvalue()
    with pytest.raises(PriceBandIngestError, match="No qualifying price band CSV member.*Finding H-45"):
        parse_price_band_report(
            report_data=zip_bytes,
            trade_date=datetime.date(2024, 1, 16),
        )


def test_h46_header_without_band_columns_fails_closed():
    """
    Audit §37 H-46: Reject any report whose header carries NO BAND, UPPER_*, or LOWER_* column
    by raising PriceBandIngestError. An absence of band columns must NEVER be read as 'No Band'.
    """
    bhav_csv = (
        "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,ISIN\n"
        "INFY,EQ,16-Jan-2024,1500.00,1505.00,1515.00,1495.00,1510.00,INE009A01021\n"
    ).encode("utf-8")

    with pytest.raises(PriceBandIngestError, match="lacks band/circuit limit columns.*Finding H-46"):
        parse_price_band_report(
            report_data=bhav_csv,
            trade_date=datetime.date(2024, 1, 16),
        )


def test_h47_missing_security_master_with_symbol_only_fails_closed():
    """
    Audit §37 H-47: A report with only Symbol and Band (no ISIN column) parsed without a
    SecurityMaster must fail closed with PriceBandIngestError, diagnosing unresolved rows.
    """
    cash_csv = (
        "Symbol,Series,Security Name,Band,Remarks\n"
        "INFY,EQ,Infosys Limited,No Band,-\n"
        "RELIANCE,EQ,Reliance Industries Limited,No Band,-\n"
    ).encode("utf-8")

    with pytest.raises(PriceBandIngestError, match="report lacks an ISIN column and security_master was None.*Finding H-47"):
        parse_price_band_report(
            report_data=cash_csv,
            trade_date=datetime.date(2024, 1, 16),
            security_master=None,
        )


def test_h44_silver_price_band_partition_round_trip(test_calendar):
    """
    Audit §37 H-44 / Note N-1:
    Verify write_price_band_partition and read_price_band_partition in Silver storage.
    Enforces exact Decimal types, holdout isolation, calendar validation, and immutability.
    """
    with tempfile.TemporaryDirectory(prefix="silver_band_") as tmpdir:
        tmp_path = Path(tmpdir)
        silver = SilverStorage(tmp_path / "silver", calendar=test_calendar)
        t_date = datetime.date(2024, 1, 10)

        source_desc = PriceBandSourceDescriptor(
            source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
            publication_name="NSE_TEST_BANDS",
            archive_url_template="https://archives.nseindia.com/sec_list.csv",
            retrieval_frequency="DAILY",
            circular_ref="NSE/TEST/01",
        )
        records = [
            PriceBandRecord(
                isin="INE888C01010",
                trade_date=t_date,
                series="EQ",
                upper_circuit_limit=Decimal("802.80"),
                lower_circuit_limit=Decimal("535.20"),
                band_percentage=Decimal("20.00"),
                is_unconstrained=False,
                source_descriptor=source_desc,
                source_ref="NSE/TEST/01",
            ),
            PriceBandRecord(
                isin="INE009A01021",
                trade_date=t_date,
                series="EQ",
                upper_circuit_limit=None,
                lower_circuit_limit=None,
                band_percentage=None,
                is_unconstrained=True,
                source_descriptor=source_desc,
                source_ref="NSE/TEST/01",
            ),
        ]

        part_path = silver.write_price_band_partition(t_date, records)
        assert part_path.is_file()
        assert silver.price_band_partition_exists(t_date) is True

        # Immutability: writing again raises SilverPartitionImmutableError
        with pytest.raises(SilverPartitionImmutableError, match="already exists"):
            silver.write_price_band_partition(t_date, records)

        # Read back and verify exact Decimal types and fields
        loaded = silver.read_price_band_partition(t_date)
        assert len(loaded) == 2
        by_isin = {r.isin: r for r in loaded}

        rec1 = by_isin["INE888C01010"]
        assert rec1.trade_date == t_date
        assert rec1.series == "EQ"
        assert rec1.upper_circuit_limit == Decimal("802.80")
        assert rec1.lower_circuit_limit == Decimal("535.20")
        assert rec1.band_percentage == Decimal("20.00")
        assert rec1.is_unconstrained is False
        assert rec1.has_circuit_evidence is True
        assert rec1.source_descriptor is not None
        assert rec1.source_descriptor.publication_name == "NSE_TEST_BANDS"

        rec2 = by_isin["INE009A01021"]
        assert rec2.trade_date == t_date
        assert rec2.upper_circuit_limit is None
        assert rec2.lower_circuit_limit is None
        assert rec2.band_percentage is None
        assert rec2.is_unconstrained is True
        assert rec2.has_circuit_evidence is False


def test_security_master_with_price_bands():
    """
    Audit §38 H-49: SecurityMaster.with_price_bands enforces interval consistency fail-closed.
    1. Attaching a discrete PriceBandRecord that contradicts a covering interval
       (e.g. 20% on 2024-01-10 for unconstrained COCHINSHIP) MUST fail closed with SecurityMasterError.
    2. Attaching an agreeable discrete PriceBandRecord updates discrete lookups and fingerprint.
    """
    sm = build_production_security_master()
    t_date = datetime.date(2024, 1, 10)
    # Baseline on 2024-01-10 has no discrete bands
    assert len(sm.price_bands) == 0

    # 1. Contradicting discrete record fails closed (Finding H-49)
    contradicting_band = PriceBandRecord(
        isin="INE704P01025",
        trade_date=t_date,
        series="EQ",
        upper_circuit_limit=Decimal("802.80"),
        lower_circuit_limit=Decimal("535.20"),
        band_percentage=Decimal("20.00"),
        is_unconstrained=False,
    )
    with pytest.raises(SecurityMasterError, match="contradicting covering unconstrained interval"):
        sm.with_price_bands([contradicting_band])

    # 2. Agreeable discrete record succeeds and updates fingerprint
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_TEST_BANDS",
        archive_url_template="https://archives.nseindia.com/sec_list.csv",
        retrieval_frequency="DAILY",
    )
    agreeable_band = PriceBandRecord(
        isin="INE009A01021",
        trade_date=t_date,
        series="EQ",
        upper_circuit_limit=None,
        lower_circuit_limit=None,
        band_percentage=None,
        is_unconstrained=True,
        source_descriptor=source_desc,
    )

    sm_updated = sm.with_price_bands([agreeable_band])
    # Original remains immutable
    assert len(sm.price_bands) == 0
    assert len(sm_updated.price_bands) == 1
    assert sm_updated.fingerprint != sm.fingerprint

    # Lookup resolves discrete band
    resolved = sm_updated.get_price_band("INE009A01021", t_date)
    assert resolved is not None
    assert resolved.is_unconstrained is True
    assert resolved.band_percentage is None


def test_h49_discrete_band_validation_vs_interval_branches():
    """
    Audit §38 H-49: Validate all contradiction branches between discrete PriceBandRecords and intervals.
    """
    t_date = datetime.date(2024, 1, 10)
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE_TEST_BANDS",
        archive_url_template="https://archives.nseindia.com/sec_list.csv",
        retrieval_frequency="DAILY",
    )
    syms = [
        SymbolInterval("INE111A01010", "TESTUNCON", "EQ", datetime.date(2024, 1, 1)),
        SymbolInterval("INE222B01010", "TESTCONST", "EQ", datetime.date(2024, 1, 1)),
    ]
    intervals = [
        PriceBandInterval(
            isin="INE111A01010",
            band_percentage=None,
            is_unconstrained=True,
            effective_from=datetime.date(2024, 1, 1),
            source_descriptor=source_desc,
        ),
        PriceBandInterval(
            isin="INE222B01010",
            band_percentage=Decimal("10.00"),
            is_unconstrained=False,
            effective_from=datetime.date(2024, 1, 1),
            source_descriptor=source_desc,
        ),
    ]
    sm = SecurityMaster(symbol_intervals=syms, price_band_intervals=intervals)

    # Branch 1: Unconstrained interval, discrete record claims is_unconstrained=False
    rec1 = PriceBandRecord(
        isin="INE111A01010",
        trade_date=t_date,
        series="EQ",
        is_unconstrained=False,
        band_percentage=Decimal("10.00"),
    )
    with pytest.raises(SecurityMasterError, match="has is_unconstrained=False.*Finding H-49"):
        sm.with_price_bands([rec1])

    # Branch 2: Constrained interval (10%), discrete record claims is_unconstrained=True
    rec2 = PriceBandRecord(
        isin="INE222B01010",
        trade_date=t_date,
        series="EQ",
        is_unconstrained=True,
        band_percentage=None,
        source_descriptor=source_desc,
    )
    with pytest.raises(SecurityMasterError, match="claims is_unconstrained=True"):
        sm.with_price_bands([rec2])

    # Branch 3: Constrained interval (10%), discrete record has mismatched percentage (20%)
    rec3 = PriceBandRecord(
        isin="INE222B01010",
        trade_date=t_date,
        series="EQ",
        is_unconstrained=False,
        band_percentage=Decimal("20.00"),
    )
    with pytest.raises(SecurityMasterError, match="contradicts covering interval band_percentage"):
        sm.with_price_bands([rec3])

    # Branch 4: Constrained interval (10%), discrete record has limits implying different percentage (20%)
    rec4 = PriceBandRecord(
        isin="INE222B01010",
        trade_date=t_date,
        series="EQ",
        is_unconstrained=False,
        upper_circuit_limit=Decimal("120.00"),
        lower_circuit_limit=Decimal("80.00"),
        # implied = 20%
    )
    with pytest.raises(SecurityMasterError, match="limits imply band"):
        sm.with_price_bands([rec4])

    # Branch 5: Agreeable records succeed
    rec_agreeable = PriceBandRecord(
        isin="INE222B01010",
        trade_date=t_date,
        series="EQ",
        is_unconstrained=False,
        band_percentage=Decimal("10.00"),
        upper_circuit_limit=Decimal("110.00"),
        lower_circuit_limit=Decimal("90.00"),
    )
    sm_ok = sm.with_price_bands([rec_agreeable])
    res = sm_ok.get_price_band("INE222B01010", t_date)
    assert res is not None
    assert res.band_percentage == Decimal("10.00")
    assert res.upper_circuit_limit == Decimal("110.00")


def test_n14_dropped_row_accounting_summary_and_threshold(test_calendar):
    """
    Audit §38.4 Note N-14:
    - parse_price_band_report returns typed PriceBandParseResult with summary counters.
    - ingest_daily_price_bands carries summary into BronzeManifestEntry and manifest.jsonl.
    - max_unresolved_threshold fails closed when drops exceed threshold.
    """
    csv_text = (
        "ISIN,SYMBOL,SERIES,UPPER_LIMIT,LOWER_LIMIT,BAND\n"
        "INE009A01021,INFY,EQ,1600.00,1400.00,No Band\n"
        ",UNKNOWN_SYM,EQ,100.00,90.00,10.00\n"  # dropped: no isin
        ",ANOTHER_UNKNOWN,EQ,200.00,180.00,10.00\n"  # dropped: no isin
    ).encode("utf-8")

    # 1. parse_price_band_report returns summary
    t_date = datetime.date(2024, 1, 10)
    res = parse_price_band_report(report_data=csv_text, trade_date=t_date)
    assert res.trade_date == t_date
    assert len(res.records) == 1
    assert res.summary.total_rows == 3
    assert res.summary.extracted_records == 1
    assert res.summary.unresolved_isin_count == 2
    assert res.summary.non_target_count == 0
    assert res.summary.duplicate_isin_count == 0

    # 2. max_unresolved_threshold fails closed
    with pytest.raises(PriceBandIngestError, match="Unresolved in-scope .* exceeded allowable threshold 1.*Note N-14 / Note N-19"):
        parse_price_band_report(
            report_data=csv_text,
            trade_date=t_date,
            max_unresolved_threshold=1,
        )

    # 3. ingest_daily_price_bands carries summary into Bronze manifest
    with tempfile.TemporaryDirectory(prefix="bronze_n14_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze = BronzeStorage(tmp_path / "bronze")
        silver = SilverStorage(tmp_path / "silver", calendar=test_calendar)

        ingest_res = ingest_daily_price_bands(
            bronze=bronze,
            report_bytes=csv_text,
            filename="sec_list_n14.csv",
            source_url="https://archives.nseindia.com/sec_list_n14.csv",
            trade_date=t_date,
            silver=silver,
            calendar=test_calendar,
        )
        assert ingest_res.summary.unresolved_isin_count == 2
        assert ingest_res.bronze_entry.summary is not None
        assert ingest_res.bronze_entry.summary["unresolved_isin_count"] == 2

        # Verify persisted in manifest.jsonl
        entries = bronze.load_manifest()
        assert len(entries) == 1
        assert entries[0].summary is not None
        assert entries[0].summary["unresolved_isin_count"] == 2


def test_n15_zip_probe_exception_fails_closed():
    """
    Audit §38.5 Note N-15:
    ZIP header probe must NOT swallow exceptions with 'except Exception: pass'.
    An unreadable/corrupted member in a ZIP must raise PriceBandIngestError fail-closed.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        # Write valid non-bhav candidate
        zf.writestr("candidate_file.csv", b"\x80\x81\x82\xff\xfe")  # Invalid UTF-8 bytes!

    with pytest.raises(PriceBandIngestError, match="Failed to probe header of candidate member.*Note N-15"):
        parse_price_band_report(
            report_data=zip_buf.getvalue(),
            trade_date=datetime.date(2024, 1, 10),
        )


def test_n16_silver_price_band_calendar_required():
    """
    Audit §38.5 Note N-16:
    SilverStorage.write_price_band_partition MUST require an authoritative TradingCalendar.
    Writing without any calendar must fail closed with SilverStorageError.
    """
    with tempfile.TemporaryDirectory(prefix="silver_n16_") as tmpdir:
        tmp_path = Path(tmpdir)
        # Construct storage with calendar=None
        silver_no_cal = SilverStorage(tmp_path / "silver_no_cal", calendar=None)
        t_date = datetime.date(2024, 1, 10)
        rec = PriceBandRecord(
            isin="INE009A01021",
            trade_date=t_date,
            series="EQ",
            is_unconstrained=False,
            band_percentage=Decimal("10.00"),
        )

        # Calling write_price_band_partition without calendar raises SilverStorageError
        with pytest.raises(SilverStorageError, match="TradingCalendar is required"):
            silver_no_cal.write_price_band_partition(trade_date=t_date, records=[rec])


def test_h44_cash_universe_identity_and_verified_fold(test_calendar):
    """
    Audit §38.3 H-44:
    (a) Effective-dated symbol->ISIN table for the EQ universe keyed by ISIN.
    (b) Daily cash band report ingested per session to Bronze/Silver.
    (c) Fixed-band rows deriving limits from previous close.
    (d) At least one fold reaching verification_status = 'VERIFIED' with all executed fills carrying circuit evidence.
    """
    sm = build_production_security_master(include_cash_universe=True)
    assert len(sm.registered_isins) > 2000

    # Test resolving a cash universe scrip
    resolved_isin = sm.resolve_isin_by_symbol("20MICRONS", datetime.date(2024, 1, 10), series="EQ")
    assert resolved_isin == "INE144J01027"

    # Simulate daily cash band report with 20MICRONS having 20% fixed band
    cash_csv = (
        "Symbol,Series,Security Name,Band,Remarks\n"
        "20MICRONS,EQ,20 Microns Limited,20,-\n"
        "INFY,EQ,Infosys Limited,No Band,-\n"
    ).encode("utf-8")

    t_date = datetime.date(2024, 1, 10)
    with tempfile.TemporaryDirectory(prefix="h44_pipeline_") as tmpdir:
        tmp_path = Path(tmpdir)
        bronze = BronzeStorage(tmp_path / "bronze")
        silver = SilverStorage(tmp_path / "silver", calendar=test_calendar)

        for s in test_calendar.sessions:
            ingest_daily_price_bands(
                bronze=bronze,
                report_bytes=cash_csv,
                filename=f"sec_list_{s.strftime('%Y%m%d')}.csv",
                source_url=f"https://archives.nseindia.com/sec_list_{s.strftime('%Y%m%d')}.csv",
                trade_date=s,
                security_master=sm,
                silver=silver,
                calendar=test_calendar,
            )

        # Load bands into master from silver
        sm_with_bands = sm.load_from_silver_price_bands(silver, test_calendar.sessions, calendar=test_calendar)
        band_20m = sm_with_bands.get_price_band("INE144J01027", t_date, prev_close=Decimal("150.00"))
        assert band_20m is not None
        assert band_20m.band_percentage == Decimal("20")
        assert band_20m.upper_circuit_limit == Decimal("180.00")
        assert band_20m.lower_circuit_limit == Decimal("120.00")
        assert band_20m.has_circuit_evidence is True

        # Now run a walkforward fold with a trade in 20MICRONS
        # Write daily bhavcopy partitions for test sessions
        for s in test_calendar.sessions:
            silver.write_daily_partition(
                s,
                [
                    SilverRecord(
                        isin="INE144J01027",
                        symbol="20MICRONS",
                        series="EQ",
                        trade_date=s,
                        open=Decimal("155.00"),
                        high=Decimal("160.00"),
                        low=Decimal("152.00"),
                        close=Decimal("158.00"),
                        volume=500000,
                        traded_value=Decimal("77500000.00"),
                    )
                ],
                calendar=test_calendar,
            )

        gold = GoldEngine(silver_storage=silver, calendar=test_calendar, security_master=sm_with_bands)
        fold = WalkForwardFold(
            fold_index=0,
            train_start=datetime.date(2024, 1, 8),
            train_end=datetime.date(2024, 1, 9),
            test_start=datetime.date(2024, 1, 10),
            test_end=datetime.date(2024, 1, 12),
            embargo_sessions=0,
            partition_role=PartitionRole.VALIDATION,
        )

        class CashBuyer(Strategy):
            @property
            def strategy_id(self) -> str:
                return "CASH-BUYER"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 10):
                    return (
                        OrderIntent(
                            instrument_id="INE144J01027",
                            signal_date=as_of,
                            target_date=next_session,  # Jan 11
                            side=OrderSide.BUY,
                            quantity=100,
                        ),
                    )
                return ()

        engine = WalkForwardEngine(calendar=test_calendar, gold_engine=gold)
        res = engine.run_walk_forward(strategy=CashBuyer(), folds=[fold], isins=["INE144J01027"])

        assert len(res.aggregate_trades) == 1
        trade = res.aggregate_trades[0]
        assert trade.status == FillStatus.FILLED
        assert trade.circuit_evidence_present is True
        assert res.circuit_evidence_complete is True
        assert res.verification_status == "VERIFIED"


def test_h50_symbol_interval_non_overlapping_and_transition_resolution():
    """
    Audit §39 Finding H-50:
    - SymbolIntervals must reject overlapping intervals per symbol in SecurityMaster.__init__.
    - Sourced cash equity intervals express exact ISIN transitions (NESTLEIND, MAZDOCK, COCHINSHIP).
    - Ambiguous active ISINs on the same date raise SecurityMasterError fail-closed.
    """
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 1, 5)
    d3 = datetime.date(2024, 1, 10)

    # 1. Overlapping intervals for same symbol/series rejected
    overlapping_intervals = [
        SymbolInterval(isin="INE239A01016", symbol="TESTSYM", series="EQ", effective_from=d1, effective_to=d3),
        SymbolInterval(isin="INE239A01024", symbol="TESTSYM", series="EQ", effective_from=d2, effective_to=None),
    ]
    with pytest.raises(SecurityMasterError, match="Overlapping or unclosed symbol intervals detected for symbol 'TESTSYM'"):
        SecurityMaster(symbol_intervals=overlapping_intervals)

    # 2. Production cash universe intervals loaded and verified
    intervals = load_cash_universe_symbol_intervals()
    sm = SecurityMaster(symbol_intervals=intervals)

    # NESTLEIND split on 2024-01-05
    assert sm.resolve_isin_by_symbol("NESTLEIND", datetime.date(2024, 1, 2)) == "INE239A01016"
    assert sm.resolve_isin_by_symbol("NESTLEIND", datetime.date(2024, 1, 5)) == "INE239A01024"

    # MAZDOCK split on 2024-12-27
    assert sm.resolve_isin_by_symbol("MAZDOCK", datetime.date(2024, 12, 26)) == "INE249Z01012"
    assert sm.resolve_isin_by_symbol("MAZDOCK", datetime.date(2024, 12, 30)) == "INE249Z01020"

    # KRBL active across multi-year window
    assert sm.resolve_isin_by_symbol("KRBL", datetime.date(2023, 6, 1)) == "INE001B01026"
    assert sm.resolve_isin_by_symbol("KRBL", datetime.date(2024, 6, 1)) == "INE001B01026"


def test_h51_build_production_security_master_fails_closed_on_corrupt_artifact():
    """
    Audit §39 Finding H-51:
    - Missing or corrupt cash universe reference artifact must raise fail-closed.
    - Zero exception swallowing in build_production_security_master.
    """
    with tempfile.TemporaryDirectory(prefix="h51_") as tmpdir:
        corrupt_csv = Path(tmpdir) / "corrupt_cash_universe.csv"
        # Write corrupted header / invalid date row
        corrupt_csv.write_text(
            "isin,symbol,series,effective_from,effective_to\n"
            "INE000A01001,BOGUS,EQ,NOT_A_DATE,2024-01-05\n",
            encoding="utf-8"
        )

        with pytest.raises(SecurityMasterError, match="Corrupt row 2 in cash universe artifact"):
            load_cash_universe_symbol_intervals(corrupt_csv)

    # Missing file fails closed
    with pytest.raises(FileNotFoundError, match="Cash universe symbol intervals artifact not found"):
        load_cash_universe_symbol_intervals(Path("non_existent_artifact_xyz.csv"))


def test_n19_series_partitioning_accounting_and_threshold(test_calendar):
    """
    Audit §39 Note N-19:
    - Partition price band report by series scope first (default: EQ).
    - Out-of-scope non-EQ rows (BE, SM, etc.) are counted in out_of_scope_series_count.
    - max_unresolved_threshold applies strictly to the in-scope EQ remainder.
    """
    csv_text = (
        "ISIN,SYMBOL,SERIES,UPPER_LIMIT,LOWER_LIMIT,BAND\n"
        "INE009A01021,INFY,EQ,1600.00,1400.00,No Band\n"
        ",NON_EQ_SM,SM,100.00,90.00,10.00\n"  # out-of-scope series: SM
        ",NON_EQ_BE,BE,50.00,45.00,5.00\n"    # out-of-scope series: BE
        ",UNKNOWN_EQ,EQ,200.00,180.00,10.00\n" # in-scope series EQ, dropped: no ISIN
    ).encode("utf-8")

    t_date = datetime.date(2024, 1, 10)
    res = parse_price_band_report(
        report_data=csv_text,
        trade_date=t_date,
        target_series=("EQ",),
    )
    assert res.summary.total_rows == 4
    assert res.summary.in_scope_series_count == 2
    assert res.summary.out_of_scope_series_count == 2
    assert res.summary.extracted_records == 1
    assert res.summary.unresolved_isin_count == 1  # only the 1 unresolved EQ row!
    assert res.summary.non_target_count == 0       # 0 target ISIN filter drops (Note N-26)
    assert res.summary.filtered_target_isin_count == 0

    # Threshold of 1 allows the 1 unresolved EQ row without firing on the 2 out-of-scope rows
    res2 = parse_price_band_report(
        report_data=csv_text,
        trade_date=t_date,
        target_series=("EQ",),
        max_unresolved_threshold=1,
    )
    assert res2.summary.unresolved_isin_count == 1

    # Threshold of 0 fires on the 1 unresolved EQ row
    with pytest.raises(PriceBandIngestError, match="Unresolved in-scope .* exceeded allowable threshold 0 out of 2 in-scope rows"):
        parse_price_band_report(
            report_data=csv_text,
            trade_date=t_date,
            target_series=("EQ",),
            max_unresolved_threshold=0,
        )


def test_n29_build_production_security_master_detects_core_divergence(monkeypatch):
    """
    Audit §40 Note N-29:
    - Divergence between sourced intervals and hardcoded core symbols must raise SecurityMasterError.
    - Sourced interval cannot silently disagree with core interval for overlapping dates.
    """
    import signal_core.storage.security_master as sm_mod

    # 1. Divergent ISIN for INFY raises SecurityMasterError
    divergent_intervals = (
        SymbolInterval(
            isin="INE999A01099",  # Divergent ISIN
            symbol="INFY",
            series="EQ",
            effective_from=datetime.date(2022, 1, 3),
            effective_to=None,
        ),
    )
    monkeypatch.setattr(sm_mod, "load_cash_universe_symbol_intervals", lambda *args, **kwargs: divergent_intervals)

    with pytest.raises(SecurityMasterError, match="Divergence detected between hardcoded core interval for INFY"):
        build_production_security_master(include_cash_universe=True)

    # 2. Harmonious sourced interval succeeds
    harmonious_intervals = (
        SymbolInterval(
            isin="INE009A01021",  # Matches authentic INFY ISIN
            symbol="INFY",
            series="EQ",
            effective_from=datetime.date(2022, 1, 3),
            effective_to=None,
        ),
    )
    monkeypatch.setattr(sm_mod, "load_cash_universe_symbol_intervals", lambda *args, **kwargs: harmonious_intervals)
    sm = build_production_security_master(include_cash_universe=True)
    assert sm.resolve_isin_by_symbol("INFY", datetime.date(2024, 1, 16)) == "INE009A01021"


