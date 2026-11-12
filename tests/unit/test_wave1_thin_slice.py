"""
Unit tests for Wave 1 Thin Real-Data Vertical Slice per Audit §26 and Audit §30.
Tests the complete pipeline:
Bronze -> Silver -> Gold -> DuckDB -> DATA-CTNT-V2, plus corporate action and membership interval.
Remediates findings H-21, H-23, H-24, H-25, H-27.
"""

import datetime
from decimal import Decimal
import io
from pathlib import Path
import tempfile
import zipfile

import pytest

from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.universe import IndexMembershipInterval
from signal_core.storage.bronze import BronzeStorage
from signal_core.storage.calendar import load_nse_trading_calendar
from signal_core.storage.gold import GoldEngine
from signal_core.storage.ingest import (
    BhavcopyIngestError,
    ingest_daily_bhavcopy_archive,
    parse_bhavcopy_archive,
    parse_bhavcopy_date,
)
from signal_core.storage.security_master import (
    CorporateActionType,
    build_production_security_master,
)
from signal_core.storage.silver import SilverRecord, SilverStorage
from signal_core.storage.views import DuckDBViewLayer


@pytest.fixture
def wave1_test_env(tmp_path: Path):
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    duckdb_path = tmp_path / "test_views.duckdb"
    cal = load_nse_trading_calendar()
    sec_master = build_production_security_master()
    bronze = BronzeStorage(bronze_dir)
    silver = SilverStorage(silver_dir, calendar=cal)
    return bronze, silver, duckdb_path, cal, sec_master


def test_parse_bhavcopy_date_formats():
    # Legacy DD-MON-YYYY format
    d1 = parse_bhavcopy_date("01-JAN-2024")
    assert d1 == datetime.date(2024, 1, 1)

    # ISO YYYY-MM-DD format
    d2 = parse_bhavcopy_date("2024-01-20")
    assert d2 == datetime.date(2024, 1, 20)

    with pytest.raises(BhavcopyIngestError, match="Unrecognized date format"):
        parse_bhavcopy_date("invalid-date-string")


def test_parse_bhavcopy_trailing_delimiter_and_whitespace_resilience():
    # Create synthetic archive with trailing commas and whitespace
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
            " COCHINSHIP , EQ , 1360.25 , 1382.50 , 1358.00 , 1362.85 , 1363.00 , 1353.95 , 1408663 , 1930263889.45 , 01-JAN-2024 , 41025 , INE704P01017 ,\n"
        )
        zf.writestr("cm01JAN2024bhav.csv", csv_content)

    trade_date, recs = parse_bhavcopy_archive(buf.getvalue())
    assert trade_date == datetime.date(2024, 1, 1)
    assert len(recs) == 1
    r = recs[0]
    assert r.isin == "INE704P01017"
    assert r.symbol == "COCHINSHIP"
    assert r.series == "EQ"
    assert r.open == Decimal("1360.25")
    assert r.high == Decimal("1382.50")
    assert r.low == Decimal("1358.00")
    assert r.close == Decimal("1362.85")
    assert r.volume == 1408663
    assert r.traded_value == Decimal("1930263889.45")


# -----------------------------------------------------------------------------
# Finding H-23: Exact Integer Volume Parsing & Fraction Rejection
# -----------------------------------------------------------------------------
def test_h23_volume_float_truncation_and_fraction_rejection():
    # 1. Large integer that loses precision in IEEE 754 float: 100000000000000001
    large_vol = "100000000000000001"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
            f"TESTSCRIP,EQ,100,105,95,102,102,100,{large_vol},100000,01-JAN-2024,10,INE000000001,\n"
        )
        zf.writestr("cm01JAN2024bhav.csv", csv_content)

    _, recs = parse_bhavcopy_archive(buf.getvalue())
    assert len(recs) == 1
    assert recs[0].volume == 100000000000000001
    assert str(recs[0].volume) == large_vol

    # 2. Fractional volume like 1500000.9 must be rejected fail-closed
    buf_fraction = io.BytesIO()
    with zipfile.ZipFile(buf_fraction, "w") as zf:
        csv_fraction = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
            "TESTSCRIP,EQ,100,105,95,102,102,100,1500000.9,100000,01-JAN-2024,10,INE000000001,\n"
        )
        zf.writestr("cm01JAN2024bhav.csv", csv_fraction)

    with pytest.raises(BhavcopyIngestError, match="fractional value"):
        parse_bhavcopy_archive(buf_fraction.getvalue())


# -----------------------------------------------------------------------------
# Finding H-24: Multi-Row Date Validation Fail-Closed on Mixed-Date Archives
# -----------------------------------------------------------------------------
def test_h24_mixed_dates_in_archive_rejected_fail_closed():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
            "SCRIP1,EQ,100,105,95,102,102,100,1000,100000,01-JAN-2024,10,INE000000001,\n"
            "SCRIP2,EQ,200,205,195,202,202,200,2000,200000,02-JAN-2024,20,INE000000002,\n"
        )
        zf.writestr("cm01JAN2024bhav.csv", csv_content)

    with pytest.raises(BhavcopyIngestError, match="does not match partition date"):
        parse_bhavcopy_archive(buf.getvalue())


# -----------------------------------------------------------------------------
# Finding H-25: Fail-Closed Truncated Row Detection on Target ISIN
# -----------------------------------------------------------------------------
def test_h25_truncated_row_for_target_isin_rejected_fail_closed():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Row truncated after symbol
        csv_content = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
            "COCHINSHIP,EQ,INE704P01017\n"
        )
        zf.writestr("cm01JAN2024bhav.csv", csv_content)

    with pytest.raises(BhavcopyIngestError, match="Truncated row detected for target ISIN"):
        parse_bhavcopy_archive(buf.getvalue(), target_isins=["INE704P01017"])


# -----------------------------------------------------------------------------
# Finding H-21: Clean Split of Synthetic vs Real Pipeline Tests
# -----------------------------------------------------------------------------
def test_wave1_thin_slice_synthetic_split_and_gold_pipeline(wave1_test_env):
    """
    Synthetic two-session split ex-date test.
    Always runs in CI / clean clones without requiring external archive downloads.
    """
    bronze, silver, duckdb_path, cal, sec_master = wave1_test_env

    d_pre = datetime.date(2024, 1, 9)
    d_post = datetime.date(2024, 1, 10)

    rec_pre = SilverRecord(
        isin="INE704P01017",
        symbol="COCHINSHIP",
        series="EQ",
        trade_date=d_pre,
        open=Decimal("1300.00"),
        high=Decimal("1350.00"),
        low=Decimal("1290.00"),
        close=Decimal("1338.00"),
        volume=3355705,
    )
    rec_post = SilverRecord(
        isin="INE704P01025",
        symbol="COCHINSHIP",
        series="EQ",
        trade_date=d_post,
        open=Decimal("677.00"),
        high=Decimal("810.00"),
        low=Decimal("675.00"),
        close=Decimal("802.80"),
        volume=22442717,
    )

    silver.write_daily_partition(d_pre, [rec_pre])
    silver.write_daily_partition(d_post, [rec_post])

    gold = GoldEngine(silver_storage=silver, calendar=cal, security_master=sec_master)
    snap, adj_panel = gold.build_dataset_snapshot(
        start_date=d_pre,
        end_date=d_post,
        price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED,
        dataset_id="COCHINSHIP-SYNTHETIC-SLICE",
        isins=["INE704P01017", "INE704P01025"],
    )

    # Jan 9 pre-split close 1338 * 0.5 = 669.0
    assert adj_panel["INE704P01017"][0].close == Decimal("669.0")
    # Jan 9 volume 3355705 * 2 = 6711410
    assert adj_panel["INE704P01017"][0].volume == 6711410
    # Jan 10 post-split close 802.80
    assert adj_panel["INE704P01025"][0].close == Decimal("802.80")
    assert snap.content_fingerprint.startswith("DATA-CTNT-V2-")
    assert snap.universe_fingerprint.startswith("UNIV-SCHED-V1-")


def test_wave1_thin_slice_real_data_ingestion_and_duckdb(wave1_test_env):
    """
    Real-data test that exercises the full 22-session January 2024 Bhavcopy archives.
    Skips with an explicit reason if external archives are not present (Finding H-21).
    """
    bronze, silver, duckdb_path, cal, sec_master = wave1_test_env

    raw_data_dir = Path(__file__).resolve().parents[3] / "Signal-Atlas" / "data" / "raw" / "2024"
    if not raw_data_dir.is_dir() or len(list(raw_data_dir.glob("cm*JAN2024bhav.csv.zip"))) != 22:
        pytest.skip(
            f"Real NSE Bhavcopy archives for January 2024 (22 files) not found at {raw_data_dir}. "
            "Skipping real-data execution per Audit §30 H-21."
        )

    zips = sorted(list(raw_data_dir.glob("cm*JAN2024bhav.csv.zip")))
    target_isins = ["INE704P01017", "INE704P01025"]

    for zf in zips:
        raw_bytes = zf.read_bytes()
        b_entry, s_path, n_recs = ingest_daily_bhavcopy_archive(
            bronze=bronze,
            silver=silver,
            archive_bytes=raw_bytes,
            filename=zf.name,
            source_url=f"https://archives.nse.test/{zf.name}",
            calendar=cal,
            target_isins=target_isins,
            target_series=["EQ"],
        )
        assert s_path.is_file()
        assert n_recs == 1

    # Check total sessions ingested
    silver_partitions = list(silver.bhavcopy_dir.glob("*/*.parquet"))
    assert len(silver_partitions) == 22

    # Check DuckDB SQL view
    views = DuckDBViewLayer(silver_storage=silver, db_path=duckdb_path)
    views.connect()
    rows = views.query("SELECT count(*), min(close), max(close) FROM silver_bhavcopy")
    assert rows[0][0] == 22
    views.close()

    # Check Gold price panel and split adjustment
    gold = GoldEngine(silver_storage=silver, calendar=cal, security_master=sec_master)
    raw_panel = gold.load_price_panel(
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        isins=target_isins,
    )
    assert len(raw_panel["INE704P01017"]) == 7
    assert len(raw_panel["INE704P01025"]) == 15

    # Split-adjusted snapshot
    snap, adj_panel = gold.build_dataset_snapshot(
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        price_convention=PriceConvention.SPLIT_BONUS_ADJUSTED,
        dataset_id="COCHINSHIP-TEST-SLICE",
        isins=target_isins,
    )
    assert snap.content_fingerprint.startswith("DATA-CTNT-V2-")
    assert snap.universe_fingerprint.startswith("UNIV-SCHED-V1-")

    # Jan 9 split adjustment: 1338 * 0.5 = 669.0
    jan9_bar = adj_panel["INE704P01017"][-1]
    assert jan9_bar.close == Decimal("669.0")
    assert jan9_bar.volume == 3355705 * 2


def test_real_index_membership_interval_transitions():
    """Tests half-open interval mechanics [effective_from, effective_to) and non-overlap (H-27)."""
    interval_old = IndexMembershipInterval(
        index_name="NIFTY500",
        isin="INE704P01017",
        effective_from=datetime.date(2024, 1, 1),
        effective_to=datetime.date(2024, 1, 10),
        source_publication="INTERVAL_ARITHMETIC_TEST",
    )
    interval_new = IndexMembershipInterval(
        index_name="NIFTY500",
        isin="INE704P01025",
        effective_from=datetime.date(2024, 1, 10),
        effective_to=datetime.date(2024, 2, 1),
        source_publication="INTERVAL_ARITHMETIC_TEST",
    )

    assert not interval_old.overlaps(interval_new)
    assert interval_old.contains(datetime.date(2024, 1, 9)) is True
    assert interval_old.contains(datetime.date(2024, 1, 10)) is False
    assert interval_new.contains(datetime.date(2024, 1, 10)) is True
    assert interval_new.contains(datetime.date(2024, 1, 31)) is True
    assert interval_new.contains(datetime.date(2024, 2, 1)) is False
