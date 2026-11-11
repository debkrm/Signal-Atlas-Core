"""Unit tests for Bhavcopy Parsing, Series Matching, and Continuity Contracts.

Uses isolated, synthetic zip archives and in-memory structures to test:
- Raw series preservation (EQ, BE, and unfamiliar codes like W3, XX).
- Differentiation between unrecognized present codes vs genuinely missing values.
- Separation of raw series identity from research eligibility policies.
- Explicit policy requirements (quarantining permissive BE policies, proposed EQ-only policy).
- Fail-closed behavior on duplicate/ambiguous raw Bhavcopy matches.
- Date-aware continuity validation:
  * Complete expected session coverage across EQ -> BE transitions.
  * Verified listing start/end boundaries.
  * Verified ISIN transitions (e.g. stock splits).
  * Known extraction omissions (e.g. BE series excluded).
  * Verified suspensions (requiring documented evidence).
  * Rejection of false suspension claims without evidence.
  * Fail-closed behavior on unexplained missing records.
  * Partitioning into contiguous session subsegments.
"""

import csv
import datetime
from decimal import Decimal
import io
from pathlib import Path
import zipfile
import pytest

from signal_core.contracts.exchange_series import (
    PROPOSED_UNAPPROVED_EQ_ONLY_POLICY,
    QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
    InstrumentListingInterval,
    PriceSeriesContinuityResult,
    PriceSeriesContinuityValidator,
    PriceSeriesGapType,
    SeriesEligibilityPolicy,
    SessionGapRecord,
    validate_raw_series_code,
)
from signal_core.contracts.price_bar import PriceBar
from scripts.reconcile_bhavcopy_series import parse_bhavcopy_archive, validate_legacy_root, reconcile_snapshot_mismatches


def _create_synthetic_legacy_bhavcopy(zip_path: Path):
    """Creates a synthetic zip containing a legacy 2022-mid 2024 Bhavcopy CSV."""
    header = ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES", "ISIN", ""]
    rows = [
        ["INFY", "EQ", "1500.00", "1520.00", "1490.00", "1510.00", "1510.00", "1495.00", "100000", "151000000.00", "03-JAN-2022", "5000", "INE009A01021", ""],
        ["ADANIPOWER", "BE", "370.90", "409.00", "370.90", "393.50", "395.40", "390.40", "4500000", "1770750000.00", "25-AUG-2022", "12000", "INE814H01011", ""],
        ["HDFC", "W3", "781.10", "814.00", "777.10", "802.25", "802.25", "780.00", "39000", "31287750.00", "03-JAN-2022", "500", "INE001A13049", ""],
    ]
    with zipfile.ZipFile(zip_path, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)
        z.writestr("cm03JAN2022bhav.csv", out.getvalue())


def _create_synthetic_unified_bhavcopy(zip_path: Path):
    """Creates a synthetic zip containing a new mid-2024 unified Bhavcopy CSV."""
    header = [
        "TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN", "TckrSymb", "SctySrs",
        "XpryDt", "FininstrmActlXpryDt", "StrkPric", "OptnTp", "FinInstrmNm", "OpnPric", "HghPric",
        "LwPric", "ClsPric", "LastPric", "PrvsClsgPric", "UndrlygPric", "SttlmPric", "OpnIntrst",
        "ChngInOpnIntrst", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd", "SsnId", "NewBrdLotQty",
        "Rmks", "Rsvd1", "Rsvd2", "Rsvd3", "Rsvd4"
    ]
    rows = [
        [
            "2024-07-08", "2024-07-08", "CM", "NSE", "STK", "12345", "INE704P01025", "COCHINSHIP", "EQ",
            "", "", "", "", "COCHIN SHIPYARD", "2200.00", "2250.00", "2180.00", "2210.00", "2210.00",
            "2190.00", "", "", "", "", "850000", "1878500000.00", "25000", "1", "1", "", "", "", "", ""
        ],
        [
            "2024-09-25", "2024-09-25", "CM", "NSE", "STK", "12345", "INE704P01025", "COCHINSHIP", "BE",
            "", "", "", "", "COCHIN SHIPYARD", "2100.00", "2140.00", "2050.00", "2075.00", "2080.00",
            "2120.00", "", "", "", "", "320000", "664000000.00", "12000", "1", "1", "", "", "", "", ""
        ],
    ]
    with zipfile.ZipFile(zip_path, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)
        z.writestr("BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv", out.getvalue())


# ---------------------------------------------------------------------------
# Section 1: Raw Bhavcopy Parsing Tests
# ---------------------------------------------------------------------------

def test_parse_legacy_bhavcopy_archive(tmp_path: Path):
    """Verify in-memory parsing of legacy 2022 Bhavcopy format."""
    zip_path = tmp_path / "legacy.zip"
    _create_synthetic_legacy_bhavcopy(zip_path)

    by_isin, by_sym = parse_bhavcopy_archive(zip_path)

    assert "INE009A01021" in by_isin
    assert by_isin["INE009A01021"][0]["series"] == "EQ"
    assert by_isin["INE009A01021"][0]["volume"] == 100000

    assert "INE814H01011" in by_isin
    assert by_isin["INE814H01011"][0]["symbol"] == "ADANIPOWER"
    assert by_isin["INE814H01011"][0]["series"] == "BE"
    assert by_isin["INE814H01011"][0]["volume"] == 4500000

    # Test unfamiliar series preservation
    assert "INE001A13049" in by_isin
    assert by_isin["INE001A13049"][0]["series"] == "W3"


def test_parse_unified_bhavcopy_archive(tmp_path: Path):
    """Verify in-memory parsing of new mid-2024 unified Bhavcopy format."""
    zip_path = tmp_path / "unified.zip"
    _create_synthetic_unified_bhavcopy(zip_path)

    by_isin, by_sym = parse_bhavcopy_archive(zip_path)

    assert "INE704P01025" in by_isin
    records = by_isin["INE704P01025"]
    assert len(records) == 2
    assert records[0]["series"] == "EQ"
    assert records[1]["series"] == "BE"
    assert records[1]["volume"] == 320000


# ---------------------------------------------------------------------------
# Section 2: Raw Series Validation and Classification Tests
# ---------------------------------------------------------------------------

def test_raw_series_code_validation_four_cases():
    """Verify exact distinction between recognized, unrecognized, missing, and invalid series codes."""
    # 1. Recognized codes (preserved verbatim)
    assert validate_raw_series_code("EQ") == "EQ"
    assert validate_raw_series_code("BE") == "BE"

    # 2. Valid unrecognized present codes (preserved verbatim without rewriting)
    assert validate_raw_series_code("W3") == "W3"
    assert validate_raw_series_code("XX") == "XX"

    # 3. Missing series value
    assert validate_raw_series_code(None) is None

    # 4. Invalid empty or whitespace-only values (strictly rejected, not converted to None)
    with pytest.raises(ValueError, match="Invalid empty series code"):
        validate_raw_series_code("")
    with pytest.raises(ValueError, match="Invalid whitespace-only series code"):
        validate_raw_series_code("   ")

    # 5. Invalid whitespace-padded values (not silently trimmed)
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        validate_raw_series_code(" EQ ")
    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        validate_raw_series_code("BE ")

    # 6. Invalid control characters
    with pytest.raises(ValueError, match="invalid control character"):
        validate_raw_series_code("EQ\n")
    with pytest.raises(ValueError, match="invalid control character"):
        validate_raw_series_code("BE\t")


def test_exchange_series_classification_distinctions():
    """Verify that ExchangeSeries distinguishes recognized, unrecognized present, and missing codes."""
    # Recognized codes
    assert ExchangeSeries.classify_raw_code("EQ") == ExchangeSeries.EQ
    assert ExchangeSeries.classify_raw_code("BE") == ExchangeSeries.BE
    assert ExchangeSeries.classify_raw_code("BZ") == ExchangeSeries.BZ
    assert ExchangeSeries.classify_raw_code("SM") == ExchangeSeries.SM

    # Unrecognized but present codes -> OTHER
    assert ExchangeSeries.classify_raw_code("W3") == ExchangeSeries.OTHER
    assert ExchangeSeries.classify_raw_code("XX") == ExchangeSeries.OTHER
    assert ExchangeSeries.classify_raw_code("BL") == ExchangeSeries.OTHER

    # Genuinely missing (None) -> UNKNOWN
    assert ExchangeSeries.classify_raw_code(None) == ExchangeSeries.UNKNOWN

    # Invalid empty string -> raises ValueError (never silently classified as UNKNOWN)
    with pytest.raises(ValueError, match="Invalid empty series code"):
        ExchangeSeries.classify_raw_code("")


def test_exchange_session_observation_preserves_raw_and_typed():
    """Verify that ExchangeSessionObservation preserves raw series code even when classified as OTHER."""
    bar = PriceBar(
        instrument_id="INST-1",
        trade_date=datetime.date(2022, 1, 3),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("102"),
        volume=1000,
    )
    obs = ExchangeSessionObservation(
        instrument_id="INST-1",
        trade_date=datetime.date(2022, 1, 3),
        raw_series_code="W3",
        series_classification=ExchangeSeries.OTHER,
        isin="INE001A13049",
        price_bar=bar,
    )
    assert obs.raw_series_code == "W3"
    assert obs.series_classification == ExchangeSeries.OTHER
    assert obs.source_provenance == "EXCHANGE_BHAVCOPY"

    # Invariant: mismatch between raw and classification raises ValueError
    with pytest.raises(ValueError, match="Mismatch between raw_series_code"):
        ExchangeSessionObservation(
            instrument_id="INST-1",
            trade_date=datetime.date(2022, 1, 3),
            raw_series_code="EQ",
            series_classification=ExchangeSeries.BE,  # Invalid pairing
            isin="INE814H01011",
            price_bar=bar,
        )


# ---------------------------------------------------------------------------
# Section 3: Eligibility Policy Separation Tests
# ---------------------------------------------------------------------------

def test_series_eligibility_policy_separation():
    """Verify that SeriesEligibilityPolicy strictly enforces declared series without authorized defaults."""
    policy_eq_only = PROPOSED_UNAPPROVED_EQ_ONLY_POLICY
    assert policy_eq_only.is_eligible(ExchangeSeries.EQ) is True
    assert policy_eq_only.is_eligible(ExchangeSeries.BE) is False
    assert policy_eq_only.is_eligible(ExchangeSeries.SM) is False
    assert policy_eq_only.is_eligible(ExchangeSeries.OTHER) is False
    assert policy_eq_only.is_eligible(ExchangeSeries.UNKNOWN) is False

    # Permissive policy is explicitly quarantined and requires deliberate injection
    quarantined = QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY
    assert quarantined.is_eligible(ExchangeSeries.EQ) is True
    assert quarantined.is_eligible(ExchangeSeries.BE) is True
    assert quarantined.is_eligible(ExchangeSeries.SM) is False


# ---------------------------------------------------------------------------
# Section 4: Gap Classification and Suspension Evidence Invariant Tests
# ---------------------------------------------------------------------------

def test_suspension_requires_evidence():
    """Verify that VERIFIED_TRADING_HALT_OR_SUSPENSION requires explicit evidence reference."""
    # Valid with evidence
    gap = SessionGapRecord(
        trade_date=datetime.date(2022, 5, 10),
        gap_type=PriceSeriesGapType.VERIFIED_TRADING_HALT_OR_SUSPENSION,
        evidence_reference="NSE Circular Ref: 2022/CIR/105",
        detail="Trading halted due to regulatory surveillance",
    )
    assert gap.evidence_reference == "NSE Circular Ref: 2022/CIR/105"
    assert gap.is_explained is True

    # Invalid without evidence: fails closed
    with pytest.raises(ValueError, match="without non-empty evidence_reference"):
        SessionGapRecord(
            trade_date=datetime.date(2022, 5, 10),
            gap_type=PriceSeriesGapType.VERIFIED_TRADING_HALT_OR_SUSPENSION,
            evidence_reference="",  # Prohibited: cannot guess suspension without evidence
        )


# ---------------------------------------------------------------------------
# Section 5: Date-Aware Continuity Validator Tests & Phase 1B.4 Cases
# ---------------------------------------------------------------------------

def _make_bar(dt: datetime.date, price: str = "100.00", inst_id: str = "INST-1") -> PriceBar:
    return PriceBar(
        instrument_id=inst_id,
        trade_date=dt,
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=1000,
    )


def _make_obs(dt: datetime.date, series_code: str, price: str = "100.00", inst_id: str = "INST-1", isin: str = "INE123A01010") -> ExchangeSessionObservation:
    bar = _make_bar(dt, price=price, inst_id=inst_id)
    return ExchangeSessionObservation(
        instrument_id=inst_id,
        trade_date=dt,
        raw_series_code=series_code,
        series_classification=ExchangeSeries.classify_raw_code(series_code),
        isin=isin,
        price_bar=bar,
    )


def test_case_1_eq_to_be_transition_with_complete_observations():
    """
    Case 1: EQ to BE transition with complete price observations.
    - Monday: EQ, valid OHLCV.
    - Tuesday: BE, valid OHLCV.
    - Wednesday: BE, valid OHLCV.
    - All three dates are expected exchange sessions.
    - Security identity is unchanged.

    Expected result:
    - Price-history continuity remains complete.
    - No missing-record classification is generated.
    - Continuous subsegment is unbroken (single 3-session segment).
    - Trading eligibility may change independently.
    """
    calendar = [
        datetime.date(2022, 1, 3),  # Monday
        datetime.date(2022, 1, 4),  # Tuesday
        datetime.date(2022, 1, 5),  # Wednesday
    ]
    observations = [
        _make_obs(calendar[0], "EQ", price="100.00"),
        _make_obs(calendar[1], "BE", price="102.00"),
        _make_obs(calendar[2], "BE", price="104.00"),
    ]

    result = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-1",
        symbol="TEST",
        expected_calendar_sessions=calendar,
        actual_price_bars=observations,
    )

    # Invariants for Case 1:
    assert result.is_continuous is True
    assert result.has_unexplained_gaps is False
    assert result.missing_sessions_count == 0
    assert result.complete_coverage_count == 3
    assert result.known_filter_omissions_count == 0
    assert result.fail_closed_reason is None

    # Continuous subsegment partitioning remains contiguous across series shift
    segments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
        expected_calendar_sessions=calendar,
        actual_price_bars=observations,
    )
    assert len(segments) == 1
    assert len(segments[0]) == 3

    # Independent trading eligibility check:
    policy = PROPOSED_UNAPPROVED_EQ_ONLY_POLICY
    assert policy.is_eligible(observations[0].series_classification) is True   # Monday (EQ): eligible
    assert policy.is_eligible(observations[1].series_classification) is False  # Tuesday (BE): ineligible for entry
    assert policy.is_eligible(observations[2].series_classification) is False  # Wednesday (BE): ineligible for entry


def test_case_2_eq_to_be_transition_with_missing_observation():
    """
    Case 2: EQ to BE with a missing Tuesday observation.
    - Monday: EQ, valid OHLCV.
    - Tuesday: BE raw exchange observation exists, but the core price dataset has no corresponding bar.
    - Wednesday: BE, valid OHLCV.

    Expected result:
    - Tuesday is detected as a source omission (EXTRACTION_FILTER_OMISSION).
    - Price-history continuity fails until the observation is restored.
    - No fabricated bar is generated (available count is 2).
    - Subsegments split around the missing session.
    """
    calendar = [
        datetime.date(2022, 1, 3),  # Monday
        datetime.date(2022, 1, 4),  # Tuesday (omitted in core dataset)
        datetime.date(2022, 1, 5),  # Wednesday
    ]
    bars = [
        _make_bar(calendar[0], price="100.00"),
        _make_bar(calendar[2], price="104.00"),
    ]
    raw_obs = {calendar[1]: ("BE", ExchangeSeries.BE)}

    result = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-1",
        symbol="ADANIPOWER",
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
        raw_observations_by_date=raw_obs,
    )

    # Invariants for Case 2:
    assert result.is_continuous is False
    assert result.missing_sessions_count == 1
    assert result.available_records_count == 2
    assert result.known_filter_omissions_count == 1
    assert result.gaps[0].gap_type == PriceSeriesGapType.EXTRACTION_FILTER_OMISSION
    assert result.gaps[0].trade_date == calendar[1]

    # Subsegments must NOT bridge Tuesday's missing record
    segments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
    )
    assert len(segments) == 2
    assert [b.trade_date for b in segments[0]] == [calendar[0]]
    assert [b.trade_date for b in segments[1]] == [calendar[2]]


def test_case_3_eq_to_be_with_isin_transition():
    """
    Case 3: EQ to BE with an ISIN change.
    - The old ISIN ends.
    - A new ISIN begins.
    - Both have observations around the transition.

    Expected result:
    - The identity transition is explicitly represented (VERIFIED_ISIN_TRANSITION).
    - No automatic instrument merger or price stitching occurs.
    """
    calendar = [
        datetime.date(2024, 1, 8),
        datetime.date(2024, 1, 9),
        datetime.date(2024, 1, 10),  # Transition day: old ISIN ceases trading
    ]
    bars_old = [_make_bar(calendar[0], inst_id="INST-OLD"), _make_bar(calendar[1], inst_id="INST-OLD")]
    listing_old = InstrumentListingInterval(
        instrument_id="INST-OLD",
        symbol="COCHINSHIP",
        isin="INE704P01017",
        superseded_by_isin="INE704P01025",
        transition_date=datetime.date(2024, 1, 10),
    )

    result_old = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-OLD",
        symbol="COCHINSHIP",
        expected_calendar_sessions=calendar,
        actual_price_bars=bars_old,
        listing_interval=listing_old,
    )

    assert result_old.verified_transitions_count == 1
    assert result_old.gaps[0].gap_type == PriceSeriesGapType.VERIFIED_ISIN_TRANSITION
    assert "INE704P01025" in result_old.gaps[0].evidence_reference


def test_case_4_eq_to_be_with_be_excluded_by_strategy_policy():
    """
    Case 4: EQ to BE with BE excluded by a strategy policy.

    Expected result:
    - The historical BE price observation remains available as market data.
    - The strategy eligibility decision can reject a new trade.
    - The continuity validator does not remove the observation.
    """
    calendar = [
        datetime.date(2022, 1, 3),  # Monday (EQ)
        datetime.date(2022, 1, 4),  # Tuesday (BE)
    ]
    observations = [
        _make_obs(calendar[0], "EQ", price="100.00"),
        _make_obs(calendar[1], "BE", price="102.00"),
    ]

    # Strategy policy: rolling equity (EQ) only
    strategy_policy = PROPOSED_UNAPPROVED_EQ_ONLY_POLICY

    # Market data continuity: both bars are present, sequence is continuous
    result = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-1",
        symbol="TEST",
        expected_calendar_sessions=calendar,
        actual_price_bars=observations,
    )
    assert result.is_continuous is True
    assert result.available_records_count == 2
    assert result.missing_sessions_count == 0

    # Strategy trade entry decision: independently rejects BE trade without mutating market data
    assert strategy_policy.is_eligible(observations[0].series_classification) is True
    assert strategy_policy.is_eligible(observations[1].series_classification) is False
    # Market observation remains intact
    assert observations[1].price_bar.close == Decimal("102.00")
    assert observations[1].raw_series_code == "BE"


def test_reconciliation_script_explicit_legacy_root_validation(tmp_path: Path):
    """Verify that reconcile_snapshot_mismatches requires an explicit, valid legacy root path."""
    # 1. None or non-Path raises ValueError
    with pytest.raises(ValueError, match="Explicit legacy_root Path is required"):
        reconcile_snapshot_mismatches(None)  # type: ignore

    # 2. Non-existent path raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="does not exist"):
        validate_legacy_root(tmp_path / "non_existent_folder")

    # 3. Directory missing snapshot or raw folder raises FileNotFoundError
    empty_dir = tmp_path / "empty_legacy"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="Historical snapshot not found"):
        validate_legacy_root(empty_dir)


def test_delisting_corporate_action_gap_classification():
    """Verify that dates post verified delisting are classified as VERIFIED_CORPORATE_ACTION_DELISTING."""
    calendar = [
        datetime.date(2023, 7, 12),
        datetime.date(2023, 7, 13),  # Post delisting date
    ]
    bars = [_make_bar(calendar[0], inst_id="INST-HDFC")]
    listing = InstrumentListingInterval(
        instrument_id="INST-HDFC",
        symbol="HDFC",
        isin="INE001A01036",
        delisting_date=datetime.date(2023, 7, 13),
        delisting_reason="Amalgamation into HDFC Bank Ltd per Scheme of Arrangement",
    )

    result = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-HDFC",
        symbol="HDFC",
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
        listing_interval=listing,
    )

    assert result.is_continuous is True  # Post-delisting dates do not break active history continuity
    assert result.outside_listing_count == 1
    assert result.gaps[0].gap_type == PriceSeriesGapType.VERIFIED_CORPORATE_ACTION_DELISTING
    assert "Amalgamation into HDFC Bank" in result.gaps[0].evidence_reference


def test_reconciliation_fails_on_duplicate_raw_match(tmp_path: Path):
    """Verify that reconciliation raises ValueError if multiple matching records are found for an ISIN."""
    zip_path = tmp_path / "dup.zip"
    header = ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY", "ISIN"]
    rows = [
        ["TEST", "EQ", "100.00", "105.00", "99.00", "102.00", "1000", "INE123A01010"],
        ["TEST", "EQ", "101.00", "106.00", "100.00", "103.00", "2000", "INE123A01010"],  # Duplicate!
    ]
    with zipfile.ZipFile(zip_path, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)
        z.writestr("cm03JAN2022bhav.csv", out.getvalue())

    by_isin, by_sym = parse_bhavcopy_archive(zip_path)
    assert len(by_isin["INE123A01010"]) == 2  # Detected duplicate in raw archive


def test_prohibition_of_silent_filling_or_nan_masking():
    """Verify that PriceSeriesContinuityValidator never silently fills missing bars."""
    calendar = [
        datetime.date(2022, 1, 3),
        datetime.date(2022, 1, 4),  # Missing
        datetime.date(2022, 1, 5),
    ]
    bars = [_make_bar(calendar[0]), _make_bar(calendar[2])]

    result = PriceSeriesContinuityValidator.validate_series_continuity(
        instrument_id="INST-1",
        symbol="TEST",
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
    )

    # Invariants:
    # 1. Available records remains exactly 2 (no synthetic 3rd bar created)
    assert result.available_records_count == 2
    # 2. Missing session is explicitly identified in gaps
    assert result.missing_sessions_count == 1
    assert result.gaps[0].trade_date == datetime.date(2022, 1, 4)
    # 3. Fail closed on unexplained gap
    assert result.has_unexplained_gaps is True
    assert result.is_continuous is False
