"""
Unit Tests for Wave 0 Frozen Ingest Schemas and Manifest Lock (E-15).

Verifies typed contracts in code (not prose) per Audit §26:
1. Provenance record fields (BronzeManifestEntry & manifest lock E-15).
2. Corporate-action record (CorporateAction with verified ratios, ex-date, record-date, circular_ref).
3. Index / universe membership interval (IndexMembershipInterval half-open [effective_from, effective_to)).
4. Circuit / price-band source publication descriptor & record (PriceBandRecord, PriceBandSourceDescriptor, PriceBandInterval).
"""

import datetime
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import time
import pytest

from signal_core.contracts.price_band import (
    PriceBandInterval,
    PriceBandPublicationSource,
    PriceBandRecord,
    PriceBandSourceDescriptor,
    PriceBandValidationError,
)
from signal_core.contracts.universe import (
    IndexMembershipInterval,
    UniverseValidationError,
)
from signal_core.storage.bronze import (
    BronzeManifestEntry,
    BronzeStorage,
    BronzeStorageError,
)
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    SecurityMasterError,
)


# ==============================================================================
# 1. PROVENANCE RECORD FIELDS (BronzeManifestEntry & E-15 Manifest Lock)
# ==============================================================================

def test_bronze_manifest_entry_validation():
    """Verify BronzeManifestEntry rejects malformed paths, non-hex hashes, and negative byte counts."""
    valid_sha = "a" * 64
    valid_entry = BronzeManifestEntry(
        relative_path="raw/bhavcopy/2024/sec_bhavdata_20240115.csv",
        source_url="https://archives.nseindia.com/content/cm/sec_bhavdata_20240115.csv",
        retrieved_at="2026-11-12T08:00:00Z",
        byte_count=1024,
        sha256=valid_sha.upper(),  # Should be normalized to lowercase
        restatement_ref=None,
        source_archive_format="CSV",
    )
    assert valid_entry.sha256 == valid_sha.lower()
    assert valid_entry.to_json_dict()["source_archive_format"] == "CSV"

    # Reject backslashes in relative_path
    with pytest.raises(BronzeStorageError, match="backslashes"):
        BronzeManifestEntry(
            relative_path="raw\\bhavcopy\\file.csv",
            source_url="https://example.com",
            retrieved_at="2026-11-12T08:00:00Z",
            byte_count=10,
            sha256=valid_sha,
        )

    # Reject directory traversal
    with pytest.raises(BronzeStorageError, match="traversal"):
        BronzeManifestEntry(
            relative_path="raw/../secret/file.csv",
            source_url="https://example.com",
            retrieved_at="2026-11-12T08:00:00Z",
            byte_count=10,
            sha256=valid_sha,
        )

    # Reject invalid SHA-256 (length != 64 or non-hex)
    with pytest.raises(BronzeStorageError, match="sha256"):
        BronzeManifestEntry(
            relative_path="raw/file.csv",
            source_url="https://example.com",
            retrieved_at="2026-11-12T08:00:00Z",
            byte_count=10,
            sha256="not-a-valid-sha256",
        )

    # Reject negative byte count
    with pytest.raises(BronzeStorageError, match="byte_count"):
        BronzeManifestEntry(
            relative_path="raw/file.csv",
            source_url="https://example.com",
            retrieved_at="2026-11-12T08:00:00Z",
            byte_count=-1,
            sha256=valid_sha,
        )

    # Reject boolean as byte_count
    with pytest.raises(BronzeStorageError, match="byte_count"):
        BronzeManifestEntry(
            relative_path="raw/file.csv",
            source_url="https://example.com",
            retrieved_at="2026-11-12T08:00:00Z",
            byte_count=True,
            sha256=valid_sha,
        )


def test_bronze_manifest_lock_concurrent_serialization_e15():
    """Verify BronzeStorage inter-process lock serializes concurrent manifest writes fail-closed (E-15, H-3, H-9)."""
    with tempfile.TemporaryDirectory(prefix="bronze_lock_test_") as tmpdir:
        storage = BronzeStorage(tmpdir)
        payload = b"test-content-bytes"

        # Normal store acquires and releases lock
        entry1 = storage.store_payload(
            relative_path="raw/session_1.csv",
            data=payload,
            source_url="https://example.com/session_1.csv",
        )
        assert entry1 is not None
        assert storage.manifest_path.exists()

        # Audit §28 H-9 / Probe P15: An aged/held lock (e.g. 6s old) is NEVER stolen.
        # Second writer must wait fail-closed and not steal or unlink the lock.
        lock_path = storage.manifest_path.with_suffix(".lock")
        lock_path.write_text("held by live writer process")
        # Age the lock file by 6 seconds
        aged_time = time.time() - 6.0
        os.utime(str(lock_path), (aged_time, aged_time))

        try:
            with pytest.raises(BronzeStorageError, match=r"Remediation: remove the lock file"):
                storage.store_payload(
                    relative_path="raw/session_2.csv",
                    data=b"other-payload",
                    source_url="https://example.com/session_2.csv",
                    lock_timeout_seconds=0.2,
                )
            # Critical H-9 invariant: Lock was NOT stolen/unlinked by the second writer
            assert lock_path.exists()
            assert lock_path.read_text() == "held by live writer process"
        finally:
            if lock_path.exists():
                lock_path.unlink()


# ==============================================================================
# 2. CORPORATE ACTION RECORD CONTRACT
# ==============================================================================

def test_corporate_action_record_invariants_and_serialization():
    """Verify CorporateAction ratios, ex-date, record_date, and transition constraints (Finding H-5)."""
    ca = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2023, 9, 1),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        circular_ref="NSE/CML/2023/105",
        record_date=datetime.date(2023, 9, 2),
        description="1:1 Bonus Issue",
    )
    assert ca.adjustment_factor == Decimal("0.5")

    # Audit §27 H-5: Standard 1:10 stock split produces factor 0.10
    ca_split = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2024, 2, 1),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=Decimal("10"),
        ratio_denominator=Decimal("1"),
        circular_ref="NSE/CML/2024/SPLIT10",
        description="1:10 Stock Split",
    )
    assert ca_split.adjustment_factor == Decimal("0.1")

    # Audit §27 H-5: Inverted split (num <= den) must be rejected fail-closed
    with pytest.raises(SecurityMasterError, match="SPLIT requires ratio_numerator > ratio_denominator"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2024, 2, 1),
            action_type=CorporateActionType.SPLIT,
            ratio_numerator=Decimal("1"),
            ratio_denominator=Decimal("10"),
        )

    # Inverted or equal bonus (num <= den) must be rejected fail-closed
    with pytest.raises(SecurityMasterError, match="BONUS requires ratio_numerator > ratio_denominator"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2024, 2, 1),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=Decimal("1"),
            ratio_denominator=Decimal("1"),
        )

    # Audit §28 H-10 / Probe P14a: 10:1 Consolidation / Reverse Split (num=1, den=10) produces factor 10.0
    ca_consolidation = CorporateAction(
        isin="INE002A01018",
        ex_date=datetime.date(2024, 2, 1),
        action_type=CorporateActionType.CONSOLIDATION,
        ratio_numerator=Decimal("1"),
        ratio_denominator=Decimal("10"),
        circular_ref="NSE/CML/2024/CONSOL10",
        description="10:1 Stock Consolidation",
    )
    assert ca_consolidation.adjustment_factor == Decimal("10")
    d_consol = ca_consolidation.to_dict()
    assert CorporateAction.from_dict(d_consol) == ca_consolidation

    # Inverted consolidation (num >= den) must be rejected fail-closed
    with pytest.raises(SecurityMasterError, match="CONSOLIDATION requires ratio_numerator < ratio_denominator"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2024, 2, 1),
            action_type=CorporateActionType.CONSOLIDATION,
            ratio_numerator=Decimal("10"),
            ratio_denominator=Decimal("1"),
        )

    # Roundtrip serialization
    d = ca.to_dict()
    ca_recovered = CorporateAction.from_dict(d)
    assert ca_recovered == ca

    # Reject record_date before ex_date
    with pytest.raises(SecurityMasterError, match="cannot precede ex_date"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2023, 9, 5),
            action_type=CorporateActionType.SPLIT,
            ratio_numerator=Decimal("10"),
            ratio_denominator=Decimal("2"),
            record_date=datetime.date(2023, 9, 1),
        )

    # Reject zero or negative ratios
    with pytest.raises(SecurityMasterError, match="strictly positive Decimals"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2023, 9, 5),
            action_type=CorporateActionType.SPLIT,
            ratio_numerator=Decimal("0"),
            ratio_denominator=Decimal("2"),
        )

    # ISIN_TRANSITION requires both old_isin and new_isin and they must differ
    with pytest.raises(SecurityMasterError, match="ISIN_TRANSITION requires both"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2023, 9, 5),
            action_type=CorporateActionType.ISIN_TRANSITION,
            ratio_numerator=Decimal("1"),
            ratio_denominator=Decimal("1"),
            old_isin="INE002A01018",
            new_isin=None,
        )

    with pytest.raises(SecurityMasterError, match="must differ"):
        CorporateAction(
            isin="INE002A01018",
            ex_date=datetime.date(2023, 9, 5),
            action_type=CorporateActionType.ISIN_TRANSITION,
            ratio_numerator=Decimal("1"),
            ratio_denominator=Decimal("1"),
            old_isin="INE002A01018",
            new_isin="INE002A01018",
        )


# ==============================================================================
# 3. INDEX / UNIVERSE MEMBERSHIP INTERVAL CONTRACT
# ==============================================================================

def test_index_membership_interval_half_open_semantics():
    """Verify IndexMembershipInterval half-open [effective_from, effective_to) and overlap detection."""
    interval_1 = IndexMembershipInterval(
        index_name="NIFTY_50",
        isin="INE002A01018",
        effective_from=datetime.date(2020, 1, 1),
        effective_to=datetime.date(2022, 6, 30),
        circular_ref="NSE/INDEX/2019/99",
        source_publication="NSE_INDEX_RECONSTITUTION_PRESS_RELEASE",
    )

    # Half-open test: effective_from is included, effective_to is EXCLUDED
    assert interval_1.contains(datetime.date(2020, 1, 1)) is True
    assert interval_1.contains(datetime.date(2022, 6, 29)) is True
    assert interval_1.contains(datetime.date(2022, 6, 30)) is False
    assert interval_1.contains(datetime.date(2019, 12, 31)) is False

    # Active / open-ended interval
    interval_2 = IndexMembershipInterval(
        index_name="NIFTY_50",
        isin="INE002A01018",
        effective_from=datetime.date(2022, 6, 30),
        effective_to=None,
    )
    assert interval_2.contains(datetime.date(2022, 6, 30)) is True
    assert interval_2.contains(datetime.date(2026, 11, 12)) is True

    # Interval 1 and 2 touch at 2022-06-30 but DO NOT overlap due to half-open semantics
    assert interval_1.overlaps(interval_2) is False

    # Overlapping interval
    interval_overlap = IndexMembershipInterval(
        index_name="NIFTY_50",
        isin="INE002A01018",
        effective_from=datetime.date(2021, 1, 1),
        effective_to=datetime.date(2023, 1, 1),
    )
    assert interval_1.overlaps(interval_overlap) is True

    # Reject effective_from >= effective_to
    with pytest.raises(UniverseValidationError, match="must precede effective_to"):
        IndexMembershipInterval(
            index_name="NIFTY_50",
            isin="INE002A01018",
            effective_from=datetime.date(2022, 6, 30),
            effective_to=datetime.date(2022, 6, 30),
        )

    # Roundtrip serialization
    d = interval_1.to_dict()
    recovered = IndexMembershipInterval.from_dict(d)
    assert recovered == interval_1


# ==============================================================================
# 4. PRICE BAND PUBLICATION SOURCE & RECORD CONTRACT
# ==============================================================================

def test_price_band_source_descriptor_and_record():
    """Verify PriceBandSourceDescriptor and PriceBandRecord validation and circuit evidence."""
    source_desc = PriceBandSourceDescriptor(
        source_type=PriceBandPublicationSource.NSE_DAILY_PRICE_BAND_REPORT,
        publication_name="NSE Daily Security Price Band List",
        archive_url_template="https://nsearchives.nseindia.com/content/equities/sec_list.csv",
        retrieval_frequency="DAILY_PRE_OPEN",
        circular_ref="NSE/SURV/2024/01",
        description="Authoritative pre-open price bands published daily by NSE",
    )
    assert source_desc.to_dict()["source_type"] == "NSE_DAILY_PRICE_BAND_REPORT"

    # Standard equity scrip with 10% band
    record = PriceBandRecord(
        isin="INE002A01018",
        trade_date=datetime.date(2024, 1, 15),
        series="EQ",
        upper_circuit_limit=Decimal("2750.00"),
        lower_circuit_limit=Decimal("2250.00"),
        band_percentage=Decimal("10.00"),
        is_unconstrained=False,
        source_descriptor=source_desc,
        source_ref="a" * 64,
    )
    assert record.has_circuit_evidence is True

    # Roundtrip serialization
    rec_d = record.to_dict()
    rec_recovered = PriceBandRecord.from_dict(rec_d)
    assert rec_recovered.isin == record.isin
    assert rec_recovered.upper_circuit_limit == record.upper_circuit_limit
    assert rec_recovered.lower_circuit_limit == record.lower_circuit_limit
    assert rec_recovered.source_descriptor.source_type == record.source_descriptor.source_type

    # Fixed-band scrip (standard equity with declared band percentage)
    fixed_record = PriceBandRecord(
        isin="INE009A01021",
        trade_date=datetime.date(2024, 1, 15),
        series="EQ",
        is_unconstrained=False,
        band_percentage=Decimal("10.00"),
        source_descriptor=source_desc,
        source_ref="NSE/CASH/2024/01",
    )
    # Audit §35 H-40: numeric limits required for circuit evidence; percentage alone is not evidence
    assert fixed_record.has_circuit_evidence is False
    fixed_derived = fixed_record.derive_limits(Decimal("1500.00"))
    assert fixed_derived.upper_circuit_limit == Decimal("1650.00")
    assert fixed_derived.lower_circuit_limit == Decimal("1350.00")
    assert fixed_derived.has_circuit_evidence is True

    # Unconstrained scrip (F&O stock) with dynamic flexing framework (Audit §36 Note N-8)
    fno_record = PriceBandRecord(
        isin="INE009A01021",
        trade_date=datetime.date(2024, 1, 15),
        series="EQ",
        is_unconstrained=True,
        band_percentage=Decimal("10.00"),
        source_descriptor=source_desc,
        source_ref="NSE/FO/2024/01",
    )
    assert fno_record.has_circuit_evidence is False
    # Dynamic flexing bands do not derive static fixed limits
    fno_derived = fno_record.derive_limits(Decimal("1500.00"))
    assert fno_derived.upper_circuit_limit is None
    assert fno_derived.lower_circuit_limit is None
    assert fno_derived.has_circuit_evidence is False

    # Audit §27 H-4: Anonymous unconstrained claim without source descriptor is rejected fail-closed
    with pytest.raises(PriceBandValidationError, match="requires an authoritative source_descriptor"):
        PriceBandRecord(
            isin="INE009A01021",
            trade_date=datetime.date(2024, 1, 15),
            series="EQ",
            is_unconstrained=True,
        )

    # Audit §35 H-41: Unconstrained scrip with No Band (band_percentage=None and no limits) is valid with citation
    noband_rec = PriceBandRecord(
        isin="INE009A01021",
        trade_date=datetime.date(2024, 1, 15),
        series="EQ",
        is_unconstrained=True,
        source_descriptor=source_desc,
    )
    assert noband_rec.band_percentage is None
    assert noband_rec.has_circuit_evidence is False

    # Audit §27 H-4: Inconsistent band_percentage vs declared upper/lower limits is rejected
    # upper=2200, lower=1800 implies 10% band ((2200-1800)/(2200+1800) = 400/4000 = 10%), but 5% declared
    with pytest.raises(PriceBandValidationError, match="Inconsistent price band limits vs band_percentage"):
        PriceBandRecord(
            isin="INE002A01018",
            trade_date=datetime.date(2024, 1, 15),
            series="EQ",
            upper_circuit_limit=Decimal("2200.00"),
            lower_circuit_limit=Decimal("1800.00"),
            band_percentage=Decimal("5.00"),
            source_descriptor=source_desc,
        )

    # Reject lower_circuit_limit >= upper_circuit_limit
    with pytest.raises(PriceBandValidationError, match="strictly less than upper_circuit_limit"):
        PriceBandRecord(
            isin="INE002A01018",
            trade_date=datetime.date(2024, 1, 15),
            series="EQ",
            upper_circuit_limit=Decimal("2000.00"),
            lower_circuit_limit=Decimal("2500.00"),
        )

    # Reject float in circuit limit
    with pytest.raises(PriceBandValidationError, match="must be exact Decimal"):
        PriceBandRecord(
            isin="INE002A01018",
            trade_date=datetime.date(2024, 1, 15),
            series="EQ",
            upper_circuit_limit=2750.0,
        )


def test_price_band_interval_half_open_semantics():
    """Verify PriceBandInterval half-open [effective_from, effective_to) for sustained bands."""
    p_int = PriceBandInterval(
        isin="INE999B01019",
        band_percentage=Decimal("5.00"),
        effective_from=datetime.date(2023, 1, 1),
        effective_to=datetime.date(2023, 7, 1),
        circular_ref="NSE/SURV/ESM/2023/12",
    )
    assert p_int.contains(datetime.date(2023, 1, 1)) is True
    assert p_int.contains(datetime.date(2023, 6, 30)) is True
    assert p_int.contains(datetime.date(2023, 7, 1)) is False
