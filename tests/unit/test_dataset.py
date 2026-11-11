"""Unit tests for DatasetSnapshot metadata and loading contracts."""

from dataclasses import FrozenInstanceError
import datetime
import json
from pathlib import Path
import pytest

from signal_core.contracts.dataset import (
    DatasetSnapshot,
    DatasetValidationError,
    PriceConvention,
    load_dataset_from_dict,
)
from signal_core.contracts.provenance import (
    ProvenanceStatus,
    compute_dataset_content_fingerprint,
    compute_universe_schedule_fingerprint,
)


def test_valid_dataset_snapshot_creation():
    """Verify valid DatasetSnapshot construction with unverified status."""
    snap = DatasetSnapshot(
        dataset_id="TEST-DEV-2024-V1",
        schema_version="v1",
        price_convention=PriceConvention.UNADJUSTED_RAW,
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        session_count=22,
        instrument_count=100,
        total_price_records=2200,
        source_identity="NSE_BHAVCOPY_DAILY",
        content_fingerprint="DATA-CTNT-V2-test1234567890",
        universe_fingerprint="UNIV-SCHED-V1-univ1234567890",
    )
    assert snap.dataset_id == "TEST-DEV-2024-V1"
    assert snap.source_provenance_status == "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED"
    assert snap.session_count == 22


def test_snapshot_immutability():
    """Verify DatasetSnapshot is frozen and cannot be mutated."""
    snap = DatasetSnapshot(
        dataset_id="TEST-DEV-2024-V1",
        schema_version="v1",
        price_convention=PriceConvention.UNADJUSTED_RAW,
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        session_count=22,
        instrument_count=100,
        total_price_records=2200,
        source_identity="NSE_BHAVCOPY_DAILY",
        content_fingerprint="DATA-CTNT-V2-test1234567890",
    )
    with pytest.raises(FrozenInstanceError):
        snap.dataset_id = "TAMPERED"  # type: ignore[misc]


def test_rejection_of_unauthorized_verified_status():
    """Verify snapshot cannot be created with 'VERIFIED' status without external PKI proof."""
    for bad_status in ["VERIFIED", "source_verified", "OFFICIALLY_VERIFIED"]:
        with pytest.raises(DatasetValidationError, match="Cannot initialize DatasetSnapshot with 'VERIFIED' status"):
            DatasetSnapshot(
                dataset_id="TEST-DEV-2024-V1",
                schema_version="v1",
                price_convention=PriceConvention.UNADJUSTED_RAW,
                start_date=datetime.date(2024, 1, 1),
                end_date=datetime.date(2024, 1, 31),
                session_count=22,
                instrument_count=100,
                total_price_records=2200,
                source_identity="NSE_BHAVCOPY_DAILY",
                content_fingerprint="DATA-CTNT-V2-test1234567890",
                source_provenance_status=bad_status,
            )


def test_rejection_of_datetime_instances():
    """Verify datetime.datetime is strictly rejected for start_date and end_date."""
    with pytest.raises(DatasetValidationError, match="genuine datetime.date"):
        DatasetSnapshot(
            dataset_id="TEST-DEV-2024-V1",
            schema_version="v1",
            price_convention=PriceConvention.UNADJUSTED_RAW,
            start_date=datetime.datetime(2024, 1, 1, 0, 0),  # type: ignore[arg-type]
            end_date=datetime.date(2024, 1, 31),
            session_count=22,
            instrument_count=100,
            total_price_records=2200,
            source_identity="NSE_BHAVCOPY_DAILY",
            content_fingerprint="DATA-CTNT-V2-test1234567890",
        )


def test_rejection_of_booleans_in_counts():
    """Verify booleans are rejected for all count attributes."""
    for bad_bool in [True, False]:
        with pytest.raises(DatasetValidationError, match="cannot be a boolean"):
            DatasetSnapshot(
                dataset_id="TEST-DEV-2024-V1",
                schema_version="v1",
                price_convention=PriceConvention.UNADJUSTED_RAW,
                start_date=datetime.date(2024, 1, 1),
                end_date=datetime.date(2024, 1, 31),
                session_count=bad_bool,  # type: ignore[arg-type]
                instrument_count=100,
                total_price_records=2200,
                source_identity="NSE_BHAVCOPY_DAILY",
                content_fingerprint="DATA-CTNT-V2-test1234567890",
            )

        with pytest.raises(DatasetValidationError, match="cannot be a boolean"):
            DatasetSnapshot(
                dataset_id="TEST-DEV-2024-V1",
                schema_version="v1",
                price_convention=PriceConvention.UNADJUSTED_RAW,
                start_date=datetime.date(2024, 1, 1),
                end_date=datetime.date(2024, 1, 31),
                session_count=22,
                instrument_count=100,
                total_price_records=2200,
                source_identity="NSE_BHAVCOPY_DAILY",
                content_fingerprint="DATA-CTNT-V2-test1234567890",
                benchmark_record_count=bad_bool,  # type: ignore[arg-type]
            )


def test_rejection_of_unsupported_schema_versions():
    """Verify unsupported schema versions (including legacy export formats) are rejected as core schema."""
    for bad_ver in ["v2", "v0.9", "unknown_schema", "signal-atlas-dataset-snapshot-v1"]:
        with pytest.raises(DatasetValidationError, match="Unsupported schema_version"):
            DatasetSnapshot(
                dataset_id="TEST-DEV-2024-V1",
                schema_version=bad_ver,
                price_convention=PriceConvention.UNADJUSTED_RAW,
                start_date=datetime.date(2024, 1, 1),
                end_date=datetime.date(2024, 1, 31),
                session_count=22,
                instrument_count=100,
                total_price_records=2200,
                source_identity="NSE_BHAVCOPY_DAILY",
                content_fingerprint="DATA-CTNT-V2-test1234567890",
            )


def test_source_format_and_record_counts_reconciliation():
    """Verify record count reconciliation between instrument records, benchmark records, and total price records."""
    # 1. Valid snapshot with benchmark records
    snap = DatasetSnapshot(
        dataset_id="TEST-DEV-2024-V1",
        schema_version="v1.0",
        price_convention=PriceConvention.UNADJUSTED_RAW,
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        session_count=22,
        instrument_count=100,
        total_instrument_records=2178,
        benchmark_record_count=22,
        total_price_records=2200,  # 2178 + 22 = 2200
        source_identity="NSE_BHAVCOPY_DAILY",
        content_fingerprint="DATA-CTNT-V2-test1234567890",
        source_format="signal-atlas-dataset-snapshot-v1",
    )
    assert snap.total_instrument_records == 2178
    assert snap.benchmark_record_count == 22
    assert snap.total_price_records == 2200
    assert snap.source_format == "signal-atlas-dataset-snapshot-v1"

    # 2. Inconsistent record count mismatch (fails closed)
    with pytest.raises(DatasetValidationError, match="Inconsistent record counts"):
        DatasetSnapshot(
            dataset_id="TEST-DEV-2024-V1",
            schema_version="v1.0",
            price_convention=PriceConvention.UNADJUSTED_RAW,
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            session_count=22,
            instrument_count=100,
            total_instrument_records=2000,
            benchmark_record_count=22,
            total_price_records=2200,  # 2000 + 22 != 2200
            source_identity="NSE_BHAVCOPY_DAILY",
            content_fingerprint="DATA-CTNT-V2-test1234567890",
        )

    # 3. Boolean in total_instrument_records rejected
    with pytest.raises(DatasetValidationError, match="cannot be a boolean"):
        DatasetSnapshot(
            dataset_id="TEST-DEV-2024-V1",
            schema_version="v1.0",
            price_convention=PriceConvention.UNADJUSTED_RAW,
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            session_count=22,
            instrument_count=100,
            total_instrument_records=True,  # type: ignore[arg-type]
            total_price_records=2200,
            source_identity="NSE_BHAVCOPY_DAILY",
            content_fingerprint="DATA-CTNT-V2-test1234567890",
        )


def test_rejection_of_whitespace_in_metadata_strings():
    """Verify metadata strings with whitespace padding are rejected."""
    with pytest.raises(DatasetValidationError, match="contains leading or trailing whitespace"):
        DatasetSnapshot(
            dataset_id=" TEST-DEV-2024-V1 ",
            schema_version="v1",
            price_convention=PriceConvention.UNADJUSTED_RAW,
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            session_count=22,
            instrument_count=100,
            total_price_records=2200,
            source_identity="NSE_BHAVCOPY_DAILY",
            content_fingerprint="DATA-CTNT-V2-test1234567890",
        )


def test_rejection_of_invalid_date_range():
    """Verify start_date cannot exceed end_date."""
    with pytest.raises(DatasetValidationError, match="cannot be after end_date"):
        DatasetSnapshot(
            dataset_id="TEST-DEV-2024-V1",
            schema_version="v1",
            price_convention=PriceConvention.UNADJUSTED_RAW,
            start_date=datetime.date(2024, 2, 1),
            end_date=datetime.date(2024, 1, 31),
            session_count=22,
            instrument_count=100,
            total_price_records=2200,
            source_identity="NSE_BHAVCOPY_DAILY",
            content_fingerprint="DATA-CTNT-V2-test1234567890",
        )


def test_load_dataset_from_synthetic_fixture():
    """Verify loading from the synthetic test fixture and re-verifying fingerprints."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "small_synthetic_dataset.json"
    assert fixture_path.exists(), f"Missing fixture at {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    snap, prices_by_inst, benchmark_bars, universe_sched = load_dataset_from_dict(payload)

    # 1. Verify snapshot metadata
    assert snap.dataset_id == "SYNTHETIC-TEST-2024-V1"
    assert snap.session_count == 3
    assert snap.instrument_count == 3
    assert snap.total_price_records == 9
    assert snap.benchmark_record_count == 3
    assert snap.source_provenance_status == "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED"

    # 2. Verify parsed prices
    assert len(prices_by_inst) == 3
    assert len(benchmark_bars) == 3
    assert universe_sched is not None
    assert universe_sched.session_count == 3

    # 3. Independent re-fingerprinting
    trading_dates = [
        datetime.date(2024, 1, 1),
        datetime.date(2024, 1, 2),
        datetime.date(2024, 1, 3),
    ]
    computed_content_fp = compute_dataset_content_fingerprint(
        trading_dates=trading_dates,
        prices_by_instrument=prices_by_inst,
        benchmark_prices=benchmark_bars,
    )
    assert computed_content_fp == snap.content_fingerprint
    assert computed_content_fp == "DATA-CTNT-V2-a614a80bb4552a322ad2945502bac5c9"

    computed_univ_fp = compute_universe_schedule_fingerprint(universe_sched)
    assert computed_univ_fp == snap.universe_fingerprint
    assert computed_univ_fp == "UNIV-SCHED-V1-c120e21fc4b4bb6397bd9b664ac8f63c"


def test_load_dataset_from_dict_rejects_floats_and_truncated_volumes():
    """
    Finding F-09 Regression Test:
    Verify that load_dataset_from_dict strictly rejects binary float prices,
    booleans, and non-integer truncation in volume (Probe 5 from audit).
    """
    base_payload = {
        "metadata": {
            "dataset_id": "D",
            "schema_version": "v1.0",
            "price_convention": "UNADJUSTED_RAW",
            "start_date": "2024-01-01",
            "end_date": "2024-01-01",
            "session_count": 1,
            "instrument_count": 1,
            "total_instrument_records": 1,
            "total_price_records": 1,
            "source_identity": "TEST",
            "content_fingerprint": "DATA-CTNT-V2-test",
        },
        "universe_by_date": {"2024-01-01": ["A"]},
    }

    # 1. Float close price
    float_price_payload = dict(base_payload)
    float_price_payload["prices_by_instrument"] = {
        "A": [{"trade_date": "2024-01-01", "open": "100.00", "high": "105.00", "low": "95.00", "close": 105.2, "volume": 100}]
    }
    with pytest.raises(DatasetValidationError, match="cannot be a binary float"):
        load_dataset_from_dict(float_price_payload)

    # 2. Float volume
    float_vol_payload = dict(base_payload)
    float_vol_payload["prices_by_instrument"] = {
        "A": [{"trade_date": "2024-01-01", "open": "100.00", "high": "105.00", "low": "95.00", "close": "100.00", "volume": 10.9}]
    }
    with pytest.raises(DatasetValidationError, match="cannot be a binary float"):
        load_dataset_from_dict(float_vol_payload)

    # 3. Fractional volume string
    frac_vol_payload = dict(base_payload)
    frac_vol_payload["prices_by_instrument"] = {
        "A": [{"trade_date": "2024-01-01", "open": "100.00", "high": "105.00", "low": "95.00", "close": "100.00", "volume": "10.9"}]
    }
    with pytest.raises(DatasetValidationError, match="non-negative integer string"):
        load_dataset_from_dict(frac_vol_payload)

