"""
Unit tests for Wave 1 Thin Real-Data Vertical Slice per Audit §26.
Tests the complete pipeline:
Bronze -> Silver -> Gold -> DuckDB -> DATA-CTNT-V2, plus real corporate action and membership interval.
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


def test_wave1_thin_slice_real_or_synthetic_pipeline(wave1_test_env):
    bronze, silver, duckdb_path, cal, sec_master = wave1_test_env

    # Check if local raw archives exist
    raw_data_dir = Path(__file__).resolve().parent.parent.parent / "Signal-Atlas" / "data" / "raw" / "2024"
    use_real_data = raw_data_dir.is_dir() and len(list(raw_data_dir.glob("cm*JAN2024bhav.csv.zip"))) == 22

    if use_real_data:
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
    else:
        # Synthetic two-session split ex-date test
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
        assert adj_panel["INE704P01017"][0].close == Decimal("669.0")


def test_real_index_membership_interval_transitions():
    interval_old = IndexMembershipInterval(
        index_name="NIFTY500",
        isin="INE704P01017",
        effective_from=datetime.date(2024, 1, 1),
        effective_to=datetime.date(2024, 1, 10),
        circular_ref="NSE/CML/60114",
    )
    interval_new = IndexMembershipInterval(
        index_name="NIFTY500",
        isin="INE704P01025",
        effective_from=datetime.date(2024, 1, 10),
        effective_to=datetime.date(2024, 2, 1),
        circular_ref="NSE/CML/60114",
    )

    assert not interval_old.overlaps(interval_new)
    assert interval_old.contains(datetime.date(2024, 1, 9)) is True
    assert interval_old.contains(datetime.date(2024, 1, 10)) is False
    assert interval_new.contains(datetime.date(2024, 1, 10)) is True
    assert interval_new.contains(datetime.date(2024, 1, 31)) is True
    assert interval_new.contains(datetime.date(2024, 2, 1)) is False
