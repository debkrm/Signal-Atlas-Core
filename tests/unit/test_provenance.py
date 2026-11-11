"""Unit tests for Cryptographic Provenance and Fingerprinting."""

import datetime
from decimal import Decimal
import hashlib
import pytest

from signal_core.contracts.price_bar import PriceBar, PriceBarValidationError
from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError
from signal_core.contracts.provenance import (
    ProvenanceError,
    ProvenanceStatus,
    canonicalize_decimal,
    compute_dataset_content_fingerprint,
    compute_universe_schedule_fingerprint,
)


def _make_sample_data():
    dates = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
    prices = {
        "INFY": [
            PriceBar("INFY", dates[0], Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100000, Decimal("151000000.00")),
            PriceBar("INFY", dates[1], Decimal("1510.00"), Decimal("1530.00"), Decimal("1505.00"), Decimal("1525.00"), 110000, Decimal("167750000.00")),
        ],
        "TCS": [
            PriceBar("TCS", dates[0], Decimal("3800.00"), Decimal("3850.00"), Decimal("3790.00"), Decimal("3820.00"), 50000, Decimal("191000000.00")),
        ],
    }
    bench = [
        PriceBar("NIFTYBEES", dates[0], Decimal("230.00"), Decimal("232.00"), Decimal("229.00"), Decimal("231.00"), 500000, Decimal("115500000.00")),
    ]
    return dates, prices, bench


# ---------------------------------------------------------------------------
# Independent Golden Vectors
# ---------------------------------------------------------------------------

def test_golden_vector_data_content_v2():
    """
    Independent Golden Vector test for DATA-CTNT-V2.
    Asserts exact UTF-8 byte stream and computed SHA-256 digest against independently
    specified reference string.
    """
    dates, prices, bench = _make_sample_data()

    expected_canonical_bytes = (
        b"CALENDAR:2024-01-01;2024-01-02;\n"
        b"INST:INFY\n"
        b"2024-01-01,1500.00,1520.00,1490.00,1510.00,100000,151000000.00,NONE,NONE\n"
        b"2024-01-02,1510.00,1530.00,1505.00,1525.00,110000,167750000.00,NONE,NONE\n"
        b"INST:TCS\n"
        b"2024-01-01,3800.00,3850.00,3790.00,3820.00,50000,191000000.00,NONE,NONE\n"
        b"BENCHMARK:\n"
        b"2024-01-01,230.00,232.00,229.00,231.00,500000,115500000.00\n"
    )
    assert len(expected_canonical_bytes) == 339

    independent_sha256 = hashlib.sha256(expected_canonical_bytes).hexdigest()
    expected_fingerprint = f"DATA-CTNT-V2-{independent_sha256[:32]}"

    assert expected_fingerprint == "DATA-CTNT-V2-f4da14a0d4a546d35e16e24e69a90b30"

    computed_fingerprint = compute_dataset_content_fingerprint(
        trading_dates=dates,
        prices_by_instrument=prices,
        benchmark_prices=bench,
    )
    assert computed_fingerprint == expected_fingerprint


def test_golden_vector_univ_sched_v1():
    """
    Independent Golden Vector test for UNIV-SCHED-V1.
    Asserts exact UTF-8 byte stream and computed SHA-256 digest against independently
    specified reference string.
    """
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 1, 2)
    schedule = UniverseSchedule({
        d1: ["INFY", "TCS"],
        d2: ["INFY", "RELIANCE"],
    })

    expected_canonical_bytes = (
        b"UNIVERSE_SCHEDULE:\n"
        b"DATE:2024-01-01;COUNT:2;MEMBERS:INFY,TCS\n"
        b"DATE:2024-01-02;COUNT:2;MEMBERS:INFY,RELIANCE\n"
    )
    assert len(expected_canonical_bytes) == 106

    independent_sha256 = hashlib.sha256(expected_canonical_bytes).hexdigest()
    expected_fingerprint = f"UNIV-SCHED-V1-{independent_sha256[:32]}"

    assert expected_fingerprint == "UNIV-SCHED-V1-757c140b126b13cb16586e9d9d0c32c6"

    computed_fingerprint = compute_universe_schedule_fingerprint(schedule)
    assert computed_fingerprint == expected_fingerprint


# ---------------------------------------------------------------------------
# Canonicalization and Decimal Serialization
# ---------------------------------------------------------------------------

def test_canonicalize_decimal_edge_cases():
    """Verify exact Decimal serialization, scale preservation, and rejection of invalid types."""
    # Scale preservation
    assert canonicalize_decimal(Decimal("1500.00")) == "1500.00"
    assert canonicalize_decimal(Decimal("1500")) == "1500"
    assert canonicalize_decimal(Decimal("0.00015")) == "0.00015"
    assert canonicalize_decimal(Decimal("0")) == "0"
    assert canonicalize_decimal(Decimal("0.00")) == "0.00"

    # None sentinel
    assert canonicalize_decimal(None) == "NONE"

    # Boolean rejection (fail closed)
    with pytest.raises(ProvenanceError, match="Cannot canonicalize boolean"):
        canonicalize_decimal(True)  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError, match="Cannot canonicalize boolean"):
        canonicalize_decimal(False)  # type: ignore[arg-type]

    # Binary float rejection (fail closed)
    with pytest.raises(ProvenanceError, match="Cannot canonicalize binary float"):
        canonicalize_decimal(1500.0)  # type: ignore[arg-type]

    # Non-finite Decimal rejection
    with pytest.raises(ProvenanceError, match="Cannot canonicalize non-finite"):
        canonicalize_decimal(Decimal("NaN"))
    with pytest.raises(ProvenanceError, match="Cannot canonicalize non-finite"):
        canonicalize_decimal(Decimal("Infinity"))
    with pytest.raises(ProvenanceError, match="Cannot canonicalize non-finite"):
        canonicalize_decimal(Decimal("-Infinity"))


# ---------------------------------------------------------------------------
# Determinism and Sensitivity
# ---------------------------------------------------------------------------

def test_content_fingerprint_determinism():
    """Verify that identical input always produces the exact same fingerprint."""
    dates, prices, bench = _make_sample_data()
    fp1 = compute_dataset_content_fingerprint(dates, prices, bench)
    fp2 = compute_dataset_content_fingerprint(dates, prices, bench)
    assert fp1 == fp2
    assert fp1.startswith("DATA-CTNT-V2-")
    assert len(fp1) == len("DATA-CTNT-V2-") + 32


def test_content_fingerprint_substantive_changes():
    """Verify that any substantive change alters the content fingerprint."""
    dates, prices, bench = _make_sample_data()
    baseline_fp = compute_dataset_content_fingerprint(dates, prices, bench)

    # 1. Price change
    tampered_prices = {
        "INFY": [
            PriceBar("INFY", dates[0], Decimal("1500.01"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100000, Decimal("151000000.00")),
            prices["INFY"][1],
        ],
        "TCS": prices["TCS"],
    }
    assert compute_dataset_content_fingerprint(dates, tampered_prices, bench) != baseline_fp

    # 2. Volume change
    tampered_volume = {
        "INFY": [
            PriceBar("INFY", dates[0], Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100001, Decimal("151000000.00")),
            prices["INFY"][1],
        ],
        "TCS": prices["TCS"],
    }
    assert compute_dataset_content_fingerprint(dates, tampered_volume, bench) != baseline_fp

    # 3. Traded value (turnover) None vs Decimal
    tampered_tv = {
        "INFY": [
            PriceBar("INFY", dates[0], Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100000, None),
            prices["INFY"][1],
        ],
        "TCS": prices["TCS"],
    }
    assert compute_dataset_content_fingerprint(dates, tampered_tv, bench) != baseline_fp

    # 4. Traded value 0.00 vs 0 (scale change)
    tampered_tv_scale = {
        "INFY": [
            PriceBar("INFY", dates[0], Decimal("1500.00"), Decimal("1520.00"), Decimal("1490.00"), Decimal("1510.00"), 100000, Decimal("151000000")),
            prices["INFY"][1],
        ],
        "TCS": prices["TCS"],
    }
    assert compute_dataset_content_fingerprint(dates, tampered_tv_scale, bench) != baseline_fp

    # 5. Benchmark price change
    tampered_bench = [
        PriceBar("NIFTYBEES", dates[0], Decimal("230.50"), Decimal("232.00"), Decimal("229.00"), Decimal("231.00"), 500000, Decimal("115500000.00")),
    ]
    assert compute_dataset_content_fingerprint(dates, prices, tampered_bench) != baseline_fp


def test_content_fingerprint_collection_order_invariance():
    """Verify that dictionary insertion order and list orders do not alter the canonical fingerprint."""
    dates, prices, bench = _make_sample_data()
    fp_base = compute_dataset_content_fingerprint(dates, prices, bench)

    # Invert dictionary order of instruments
    inverted_prices = {"TCS": prices["TCS"], "INFY": prices["INFY"]}
    assert compute_dataset_content_fingerprint(dates, inverted_prices, bench) == fp_base

    # Shuffle calendar dates
    shuffled_dates = [dates[1], dates[0]]
    assert compute_dataset_content_fingerprint(shuffled_dates, prices, bench) == fp_base

    # Shuffle instrument price bars order
    shuffled_bars = {
        "INFY": [prices["INFY"][1], prices["INFY"][0]],
        "TCS": prices["TCS"],
    }
    assert compute_dataset_content_fingerprint(dates, shuffled_bars, bench) == fp_base


# ---------------------------------------------------------------------------
# Delimiter Safety and Duplicate Rejection
# ---------------------------------------------------------------------------

def test_delimiter_rejection_in_fingerprinting():
    """Verify rejection of forbidden delimiter characters in instrument IDs and universe members."""
    dates = [datetime.date(2024, 1, 1)]

    # Delimiter in instrument key of prices dictionary
    with pytest.raises(ProvenanceError, match="forbidden delimiter characters"):
        compute_dataset_content_fingerprint(
            trading_dates=dates,
            prices_by_instrument={
                "INFY,NSE": [PriceBar("INFY", dates[0], Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), 1000)],
            },
        )

    with pytest.raises(ProvenanceError, match="forbidden delimiter characters"):
        compute_dataset_content_fingerprint(
            trading_dates=dates,
            prices_by_instrument={
                "INFY\nNSE": [PriceBar("INFY", dates[0], Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), 1000)],
            },
        )


def test_duplicate_date_rejection_in_fingerprinting():
    """Verify fail-closed rejection on duplicate dates in calendar, instruments, and benchmark."""
    d1 = datetime.date(2024, 1, 1)

    # 1. Duplicate date in calendar
    with pytest.raises(ProvenanceError, match="Duplicate date in calendar"):
        compute_dataset_content_fingerprint(
            trading_dates=[d1, d1],
            prices_by_instrument={},
        )

    # 2. Duplicate date in instrument price bars
    b1 = PriceBar("INFY", d1, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), 1000)
    b2 = PriceBar("INFY", d1, Decimal("101"), Decimal("106"), Decimal("96"), Decimal("101"), 2000)
    with pytest.raises(ProvenanceError, match="Duplicate price bar detected for instrument"):
        compute_dataset_content_fingerprint(
            trading_dates=[d1],
            prices_by_instrument={"INFY": [b1, b2]},
        )

    # 3. Duplicate date in benchmark
    bench1 = PriceBar("BENCH", d1, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), 1000)
    bench2 = PriceBar("BENCH", d1, Decimal("101"), Decimal("106"), Decimal("96"), Decimal("101"), 2000)
    with pytest.raises(ProvenanceError, match="Duplicate benchmark bar detected"):
        compute_dataset_content_fingerprint(
            trading_dates=[d1],
            prices_by_instrument={},
            benchmark_prices=[bench1, bench2],
        )


def test_datetime_subclass_rejection_in_fingerprinting():
    """Verify that datetime.datetime is strictly rejected across all fingerprint inputs."""
    d_dt = datetime.datetime(2024, 1, 1, 10, 0, 0)
    b_valid = PriceBar("INFY", datetime.date(2024, 1, 1), Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), 1000)

    # Calendar contains datetime.datetime
    with pytest.raises(ProvenanceError, match="Calendar date must be a genuine datetime.date"):
        compute_dataset_content_fingerprint(
            trading_dates=[d_dt],  # type: ignore[list-item]
            prices_by_instrument={"INFY": [b_valid]},
        )
