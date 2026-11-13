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

    # 5. Unconstrained interval without band_percentage is rejected
    with pytest.raises(PriceBandValidationError, match="must declare band_percentage"):
        PriceBandInterval(
            isin="INE009A01021",
            effective_from=datetime.date(2024, 1, 1),
            band_percentage=None,
            is_unconstrained=True,
            circular_ref="NSE/FAOP/01",
        )

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
    band_jan11 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11))
    assert band_jan11 is not None
    assert band_jan11.band_percentage == Decimal("20.00")
    assert band_jan11.trade_date == datetime.date(2024, 1, 11)
    assert band_jan11.has_circuit_evidence is True

    # 3. Before effective_from (Jan 9): outside interval and no discrete band -> returns None
    assert sm.get_price_band("INE704P01025", datetime.date(2024, 1, 9)) is None


# ==============================================================================
# 3. Production Security Master Audit (§31.3 measurements)
# ==============================================================================

def test_production_security_master_h30_audit_closure():
    """
    Verifies that build_production_security_master() closes every measurement in Audit §31.3:
    - INE704P01025 on 2024-01-10 returns ex-split upper circuit at 802.80.
    - INE704P01025 on 2024-01-11 and 2024-01-12 returns valid 20% interval bands.
    - INFY (INE009A01021) and RELIANCE (INE002A01018) return unconstrained F&O bands with NSE citations.
    """
    sm = build_production_security_master()

    # Measured: get_price_band("INE704P01025", 2024-01-10) is NO LONGER None
    band_split = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 10))
    assert band_split is not None
    assert band_split.upper_circuit_limit == Decimal("802.80")
    assert band_split.lower_circuit_limit == Decimal("535.20")
    assert band_split.band_percentage == Decimal("20.00")
    assert band_split.has_circuit_evidence is True

    # Measured: a band registered on 2024-01-10 is NO LONGER None for 2024-01-11 or 2024-01-12
    band_jan11 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 11))
    assert band_jan11 is not None
    assert band_jan11.band_percentage == Decimal("20.00")
    assert band_jan11.has_circuit_evidence is True

    band_jan12 = sm.get_price_band("INE704P01025", datetime.date(2024, 1, 12))
    assert band_jan12 is not None
    assert band_jan12.band_percentage == Decimal("20.00")
    assert band_jan12.has_circuit_evidence is True

    # INFY unconstrained F&O stock
    band_infy = sm.get_price_band("INE009A01021", datetime.date(2024, 1, 15))
    assert band_infy is not None
    assert band_infy.is_unconstrained is True
    assert band_infy.source_descriptor is not None
    assert band_infy.source_descriptor.circular_ref == "NSE/FAOP/60350"
    assert band_infy.has_circuit_evidence is True

    # RELIANCE unconstrained F&O stock
    band_rel = sm.get_price_band("INE002A01018", datetime.date(2024, 1, 15))
    assert band_rel is not None
    assert band_rel.is_unconstrained is True
    assert band_rel.source_descriptor.circular_ref == "NSE/FAOP/60350"
    assert band_rel.has_circuit_evidence is True


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
    # INFY resolved to INE009A01021, unconstrained
    assert "INE009A01021" in by_isin
    assert by_isin["INE009A01021"].is_unconstrained is True
    assert by_isin["INE009A01021"].band_percentage == Decimal("10.00")

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
