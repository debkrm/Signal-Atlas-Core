"""Unit tests for Read-Only Historical Snapshot Loader and Diagnostics.

Uses self-contained synthetic fixtures to verify error handling, strict validation,
legacy adjustment preservation, and fingerprint distinction without external path dependencies.
"""

import datetime
from decimal import Decimal
import json
from pathlib import Path
import pytest

from signal_core.contracts.legacy_compat import (
    LegacyDatasetAdjustmentMetadata,
    compute_legacy_dataset_content_fingerprint,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.provenance import compute_universe_schedule_fingerprint
from signal_core.loaders.historical_snapshot import (
    HistoricalSnapshotError,
    compute_file_sha256,
    load_historical_snapshot,
    run_dataset_diagnostics,
)


def _make_synthetic_snapshot_dict():
    """Builds a minimal valid synthetic snapshot dictionary matching historical schema."""
    return {
        "snapshot_format": "signal-atlas-dataset-snapshot-v1",
        "data_version": "EXP-DEV-SYNTHETIC-V1",
        "source_identity": "NSE_BHAVCOPY_DAILY",
        "content_fingerprint": "DATA-CTNT-V2-testfingerprintplaceholder00",
        "corporate_actions_fingerprint": "CA-FPR-dummy",
        "session_count": 2,
        "instrument_count": 2,
        "trading_dates": ["2024-01-01", "2024-01-02"],
        "symbols_by_instrument": {
            "INST-AAA": "AAA",
            "INST-BBB": "BBB",
        },
        "universe_by_date": {
            "2024-01-01": ["INST-AAA", "INST-BBB"],
            "2024-01-02": ["INST-AAA"],
        },
        "prices_by_instrument": {
            "INST-AAA": [
                {
                    "trade_date": "2024-01-01",
                    "open": "100.00",
                    "high": "105.00",
                    "low": "99.00",
                    "close": "102.00",
                    "volume": "1000.000000",
                    "raw_volume": 1000,
                    "traded_value": "102000.00",
                    "cumulative_multiplier": "1.000000",
                    "prev_close": "98.00",
                    "prev_close_multiplier": "1.000000",
                    "raw_prev_close": "98.00",
                    "adjustment_version": "v1.4",
                },
                {
                    "trade_date": "2024-01-02",
                    "open": "102.50",
                    "high": "106.00",
                    "low": "101.00",
                    "close": "104.00",
                    "volume": "1200.000000",
                    "raw_volume": 1200,
                    "traded_value": "124800.00",
                    "cumulative_multiplier": "1.000000",
                    "prev_close": "102.00",
                    "prev_close_multiplier": "1.000000",
                    "raw_prev_close": "102.00",
                    "adjustment_version": "v1.4",
                },
            ],
            "INST-BBB": [
                {
                    "trade_date": "2024-01-01",
                    "open": "200.00",
                    "high": "210.00",
                    "low": "195.00",
                    "close": "205.00",
                    "volume": "500.000000",
                    "raw_volume": 500,
                    "traded_value": "102500.00",
                    "cumulative_multiplier": "1.000000",
                    "prev_close": "198.00",
                    "prev_close_multiplier": "1.000000",
                    "raw_prev_close": "198.00",
                    "adjustment_version": "v1.4",
                },
            ],
        },
        "benchmark_prices": [
            {
                "trade_date": "2024-01-01",
                "open": "50.00",
                "high": "51.00",
                "low": "49.50",
                "close": "50.50",
                "volume": "50000.000000",
                "raw_volume": 50000,
                "traded_value": "2525000.00",
                "cumulative_multiplier": "1.000000",
                "prev_close": "49.00",
                "prev_close_multiplier": "1.000000",
                "raw_prev_close": "49.00",
                "adjustment_version": "v1.4",
            },
            {
                "trade_date": "2024-01-02",
                "open": "50.60",
                "high": "52.00",
                "low": "50.00",
                "close": "51.50",
                "volume": "48000.000000",
                "raw_volume": 48000,
                "traded_value": "2472000.00",
                "cumulative_multiplier": "1.000000",
                "prev_close": "50.50",
                "prev_close_multiplier": "1.000000",
                "raw_prev_close": "50.50",
                "adjustment_version": "v1.4",
            },
        ],
    }


def test_valid_synthetic_snapshot_loading(tmp_path: Path):
    """Verify clean loading of a synthetic snapshot into domain objects."""
    data = _make_synthetic_snapshot_dict()
    file_path = tmp_path / "valid_snapshot.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    dataset = load_historical_snapshot(file_path)

    assert dataset.snapshot.dataset_id == "EXP-DEV-SYNTHETIC-V1"
    assert dataset.snapshot.schema_version == "v1.0"
    assert dataset.snapshot.source_format == "signal-atlas-dataset-snapshot-v1"
    assert dataset.snapshot.session_count == 2
    assert dataset.snapshot.instrument_count == 2
    assert dataset.snapshot.total_instrument_records == 3
    assert dataset.snapshot.benchmark_record_count == 2
    assert dataset.snapshot.total_price_records == 5  # 3 instrument + 2 bench
    assert dataset.snapshot.start_date == datetime.date(2024, 1, 1)
    assert dataset.snapshot.end_date == datetime.date(2024, 1, 2)

    # PriceBar domain contract purity: volume is pure integer raw_volume
    bar_aaa = dataset.prices_by_instrument["INST-AAA"][0]
    assert isinstance(bar_aaa, PriceBar)
    assert bar_aaa.volume == 1000
    assert isinstance(bar_aaa.volume, int)
    assert not isinstance(bar_aaa.volume, bool)
    assert bar_aaa.open == Decimal("100.00")

    # Legacy adjustment metadata preserved separately
    adj_aaa = dataset.legacy_adjustments.adjustments_by_inst_date[("INST-AAA", datetime.date(2024, 1, 1))]
    assert adj_aaa.cumulative_multiplier == Decimal("1.000000")
    assert adj_aaa.legacy_volume_decimal == Decimal("1000.000000")


def test_unsupported_schema_version_rejection(tmp_path: Path):
    """Verify rejection of unsupported schema version."""
    data = _make_synthetic_snapshot_dict()
    data["snapshot_format"] = "unsupported-schema-v999"
    file_path = tmp_path / "invalid_schema.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Unsupported snapshot_format"):
        load_historical_snapshot(file_path)


def test_rejection_of_duplicate_calendar_dates(tmp_path: Path):
    """Verify fail-closed rejection on duplicate calendar dates."""
    data = _make_synthetic_snapshot_dict()
    data["trading_dates"] = ["2024-01-01", "2024-01-01"]
    file_path = tmp_path / "dup_cal.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Duplicate calendar date"):
        load_historical_snapshot(file_path)


def test_rejection_of_duplicate_instrument_bars(tmp_path: Path):
    """Verify fail-closed rejection on duplicate bars for an instrument."""
    data = _make_synthetic_snapshot_dict()
    bar0 = data["prices_by_instrument"]["INST-AAA"][0]
    data["prices_by_instrument"]["INST-AAA"].append(bar0.copy())
    file_path = tmp_path / "dup_bar.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Duplicate trade_date"):
        load_historical_snapshot(file_path)


def test_rejection_of_duplicate_benchmark_bars(tmp_path: Path):
    """Verify fail-closed rejection on duplicate benchmark bars."""
    data = _make_synthetic_snapshot_dict()
    b0 = data["benchmark_prices"][0]
    data["benchmark_prices"].append(b0.copy())
    file_path = tmp_path / "dup_bench.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Duplicate trade_date"):
        load_historical_snapshot(file_path)


def test_rejection_of_boolean_in_numeric_fields(tmp_path: Path):
    """Verify rejection of booleans in price and volume fields."""
    data = _make_synthetic_snapshot_dict()
    data["prices_by_instrument"]["INST-AAA"][0]["open"] = True
    file_path = tmp_path / "bool_open.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="cannot be boolean"):
        load_historical_snapshot(file_path)

    data2 = _make_synthetic_snapshot_dict()
    data2["prices_by_instrument"]["INST-AAA"][0]["raw_volume"] = True
    file_path2 = tmp_path / "bool_vol.json"
    file_path2.write_text(json.dumps(data2), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Invalid raw_volume"):
        load_historical_snapshot(file_path2)


def test_rejection_of_invalid_decimal_strings(tmp_path: Path):
    """Verify fail-closed rejection of malformed Decimal strings."""
    data = _make_synthetic_snapshot_dict()
    data["prices_by_instrument"]["INST-AAA"][0]["close"] = "not-a-number"
    file_path = tmp_path / "invalid_decimal.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Invalid Decimal for 'close'"):
        load_historical_snapshot(file_path)


def test_rejection_of_malformed_universe_membership(tmp_path: Path):
    """Verify fail-closed rejection of duplicate or delimiter-containing universe members."""
    data = _make_synthetic_snapshot_dict()
    data["universe_by_date"]["2024-01-01"] = ["INST-AAA", "INST-AAA"]  # duplicate member
    file_path = tmp_path / "dup_member.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HistoricalSnapshotError, match="Universe schedule construction failed"):
        load_historical_snapshot(file_path)


def test_file_sha256_versus_logical_fingerprint(tmp_path: Path):
    """
    Asserts the strict architectural distinction between file-level SHA-256 byte digest
    and logical canonical dataset content fingerprint (DATA-CTNT-V2).
    """
    data = _make_synthetic_snapshot_dict()
    file_path = tmp_path / "distinct_digests.json"
    file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

    # 1. File SHA-256 over raw file bytes
    file_digest = compute_file_sha256(file_path)
    assert len(file_digest) == 64

    # 2. Re-format whitespace on disk (file digest MUST change, logical fingerprint MUST NOT change)
    file_path_compact = tmp_path / "compact.json"
    file_path_compact.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    file_digest_compact = compute_file_sha256(file_path_compact)

    assert file_digest != file_digest_compact  # File bytes altered

    ds1 = load_historical_snapshot(file_path)
    ds2 = load_historical_snapshot(file_path_compact)

    fp1 = compute_legacy_dataset_content_fingerprint(
        ds1.trading_dates, ds1.prices_by_instrument, ds1.benchmark_prices, ds1.legacy_adjustments
    )
    fp2 = compute_legacy_dataset_content_fingerprint(
        ds2.trading_dates, ds2.prices_by_instrument, ds2.benchmark_prices, ds2.legacy_adjustments
    )

    assert fp1 == fp2  # Logical records identical
    assert fp1.startswith("DATA-CTNT-V2-")


def test_dataset_diagnostics_coverage_and_mismatches(tmp_path: Path):
    """Verify diagnostic detection of missing sessions and unmatched universe pairs."""
    data = _make_synthetic_snapshot_dict()
    # INST-BBB is in universe on 2024-01-01, but NOT in universe on 2024-01-02.
    # Furthermore, INST-BBB has only 1 price record (coverage = 1 of 2 sessions).
    file_path = tmp_path / "diag_test.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    dataset = load_historical_snapshot(file_path)
    diag = run_dataset_diagnostics(dataset)

    assert diag.total_sessions == 2
    assert diag.instrument_count == 2
    assert diag.instrument_records_count == 3
    assert diag.benchmark_records_count == 2
    assert diag.total_price_records == 5
    assert diag.universe_schedule_dates_count == 2
    assert diag.duplicate_records_count == 0
    assert diag.universe_dates_outside_calendar_count == 0
    # No unmatched universe pairs because on 2024-01-02, universe only contains INST-AAA,
    # and INST-AAA has a price bar on 2024-01-02.
    assert diag.unmatched_universe_pairs_count == 0


def test_rejection_of_declared_count_mismatches(tmp_path: Path):
    """Verify fail-closed rejection when declared metadata counts disagree with parsed records."""
    # 1. Declared session_count mismatch
    data = _make_synthetic_snapshot_dict()
    data["session_count"] = 999  # actual is 2
    f1 = tmp_path / "mismatch_sessions.json"
    f1.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(HistoricalSnapshotError, match="Declared session_count"):
        load_historical_snapshot(f1)

    # 2. Declared instrument_count mismatch
    data2 = _make_synthetic_snapshot_dict()
    data2["instrument_count"] = 999  # actual is 2
    f2 = tmp_path / "mismatch_inst.json"
    f2.write_text(json.dumps(data2), encoding="utf-8")
    with pytest.raises(HistoricalSnapshotError, match="Declared instrument_count"):
        load_historical_snapshot(f2)

    # 3. Declared total_instrument_records mismatch
    data3 = _make_synthetic_snapshot_dict()
    data3["total_instrument_records"] = 999  # actual is 3
    f3 = tmp_path / "mismatch_inst_recs.json"
    f3.write_text(json.dumps(data3), encoding="utf-8")
    with pytest.raises(HistoricalSnapshotError, match="Declared total_instrument_records"):
        load_historical_snapshot(f3)

    # 4. Declared benchmark_record_count mismatch
    data4 = _make_synthetic_snapshot_dict()
    data4["benchmark_record_count"] = 999  # actual is 2
    f4 = tmp_path / "mismatch_bench.json"
    f4.write_text(json.dumps(data4), encoding="utf-8")
    with pytest.raises(HistoricalSnapshotError, match="Declared benchmark_record_count"):
        load_historical_snapshot(f4)

