"""Unit Tests for Pure Technical Indicators and Subsegment Feature Engine.

Tests mathematical correctness, zero lookahead, exact Decimal arithmetic,
Wilder smoothing, weekly aggregation, and subsegment continuity isolation.
"""

import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import pytest

from signal_core.contracts.exchange_series import (
    ExchangeSeries,
    ExchangeSessionObservation,
    InstrumentListingInterval,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.features.engine import (
    InstrumentTechnicalFeatures,
    SubsegmentIndicatorEngine,
)
from signal_core.features.indicators import (
    IndicatorValidationError,
    WeeklyBar,
    aggregate_daily_to_weekly,
    compute_atr,
    compute_donchian_channel,
    compute_ema,
    compute_macd,
    compute_relative_strength,
    compute_rolling_high,
    compute_rolling_low,
    compute_rsi,
    compute_sma,
    compute_weekly_trend,
    extract_price_series,
    validate_and_extract_decimal,
)


def _make_bar(
    trade_date: datetime.date,
    close: str,
    open_: Optional[str] = None,
    high: Optional[str] = None,
    low: Optional[str] = None,
    volume: int = 1000,
    inst_id: str = "TEST_STOCK",
) -> PriceBar:
    c = Decimal(close)
    o = Decimal(open_) if open_ is not None else c
    h = Decimal(high) if high is not None else max(o, c) + Decimal("1.00")
    l = Decimal(low) if low is not None else min(o, c) - Decimal("1.00")
    return PriceBar(
        instrument_id=inst_id,
        trade_date=trade_date,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=volume,
    )


def _make_obs(
    trade_date: datetime.date,
    close: str,
    series: str = "EQ",
    inst_id: str = "TEST_STOCK",
) -> ExchangeSessionObservation:
    bar = _make_bar(trade_date, close, inst_id=inst_id)
    return ExchangeSessionObservation(
        instrument_id=inst_id,
        trade_date=trade_date,
        raw_series_code=series,
        series_classification=ExchangeSeries.classify_raw_code(series),
        isin="INE000A01001",
        price_bar=bar,
    )


# ---------------------------------------------------------------------------
# Section 1: Decimal Validation & Type Safety Tests
# ---------------------------------------------------------------------------

def test_validate_and_extract_decimal_rejections():
    """Verify strict rejection of floats, booleans, and non-finite decimals."""
    assert validate_and_extract_decimal(Decimal("100.50")) == Decimal("100.50")
    assert validate_and_extract_decimal(100) == Decimal("100")
    assert validate_and_extract_decimal("100.50") == Decimal("100.50")

    # Rejection of float
    with pytest.raises(IndicatorValidationError, match="cannot be a binary float"):
        validate_and_extract_decimal(100.50)

    # Rejection of bool
    with pytest.raises(IndicatorValidationError, match="cannot be a boolean"):
        validate_and_extract_decimal(True)

    # Rejection of non-finite
    with pytest.raises(IndicatorValidationError, match="finite"):
        validate_and_extract_decimal(Decimal("NaN"))
    with pytest.raises(IndicatorValidationError, match="finite"):
        validate_and_extract_decimal(Decimal("Infinity"))


def test_extract_price_series_from_bars_and_observations():
    """Verify extraction of price series from PriceBar, ExchangeSessionObservation, and Decimals."""
    d1 = datetime.date(2022, 1, 3)
    d2 = datetime.date(2022, 1, 4)
    d3 = datetime.date(2022, 1, 5)

    bar = _make_bar(d1, "100.00")
    obs = _make_obs(d2, "105.00", series="BE")
    dec = Decimal("110.00")

    series = extract_price_series([bar, obs, dec], price_field="close")
    assert series == [Decimal("100.00"), Decimal("105.00"), Decimal("110.00")]


# ---------------------------------------------------------------------------
# Section 2: SMA & EMA Indicator Mathematical Correctness
# ---------------------------------------------------------------------------

def test_compute_sma_mathematics():
    """Verify SMA calculation, exact Decimal mean, and warm-up None padding."""
    prices = [Decimal(p) for p in ["10", "20", "30", "40", "50"]]
    sma_3 = compute_sma(prices, 3)

    assert len(sma_3) == 5
    assert sma_3[0] is None
    assert sma_3[1] is None
    # Index 2: (10 + 20 + 30) / 3 = 20.000000
    assert sma_3[2] == Decimal("20.000000")
    # Index 3: (20 + 30 + 40) / 3 = 30.000000
    assert sma_3[3] == Decimal("30.000000")
    # Index 4: (30 + 40 + 50) / 3 = 40.000000
    assert sma_3[4] == Decimal("40.000000")


def test_compute_ema_mathematics_and_zero_lookahead():
    """Verify EMA seeding with SMA, recursive smoothing, and zero lookahead."""
    # Period 3: alpha = 2 / (3 + 1) = 0.5
    prices = [Decimal(p) for p in ["10", "20", "30", "40", "50"]]
    ema_3 = compute_ema(prices, 3)

    assert len(ema_3) == 5
    assert ema_3[0] is None
    assert ema_3[1] is None
    # Index 2: Seed = SMA(10, 20, 30) = 20.000000
    assert ema_3[2] == Decimal("20.000000")
    # Index 3: 0.5 * 40 + 0.5 * 20 = 30.000000
    assert ema_3[3] == Decimal("30.000000")
    # Index 4: 0.5 * 50 + 0.5 * 30 = 40.000000
    assert ema_3[4] == Decimal("40.000000")

    # Zero Lookahead Test:
    # Modifying future bar at index 4 must NOT change EMA at index 2 or index 3
    prices_altered = [Decimal(p) for p in ["10", "20", "30", "40", "9999"]]
    ema_altered = compute_ema(prices_altered, 3)
    assert ema_altered[2] == ema_3[2]
    assert ema_altered[3] == ema_3[3]
    assert ema_altered[4] != ema_3[4]


def test_compute_ema_rejection_of_invalid_period():
    """Verify EMA rejects period <= 0, booleans, and floats."""
    prices = [Decimal("100"), Decimal("101")]
    with pytest.raises(IndicatorValidationError, match="Period must be a positive integer"):
        compute_ema(prices, 0)
    with pytest.raises(IndicatorValidationError, match="Period must be a positive integer"):
        compute_ema(prices, -5)
    with pytest.raises(IndicatorValidationError, match="Period must be a positive integer"):
        compute_ema(prices, True)  # type: ignore


# ---------------------------------------------------------------------------
# Section 3: RSI Indicator Tests (Wilder Smoothing)
# ---------------------------------------------------------------------------

def test_compute_rsi_all_gains_and_all_losses():
    """Verify RSI boundaries: strictly rising -> 100, strictly falling -> 0."""
    rising = [Decimal(100 + i * 2) for i in range(20)]
    rsi_rising = compute_rsi(rising, period=14)
    assert len(rsi_rising) == 20
    for i in range(14):
        assert rsi_rising[i] is None
    assert rsi_rising[14] == Decimal("100.00")
    assert rsi_rising[19] == Decimal("100.00")

    falling = [Decimal(200 - i * 2) for i in range(20)]
    rsi_falling = compute_rsi(falling, period=14)
    for i in range(14):
        assert rsi_falling[i] is None
    assert rsi_falling[14] == Decimal("0.00")
    assert rsi_falling[19] == Decimal("0.00")


def test_compute_rsi_golden_sequence():
    """Verify RSI calculation against known synthetic price oscillation."""
    # 15 prices -> 14 changes (period=14)
    # Gains: 7 sessions of +2; Losses: 7 sessions of -1
    # Total Gain = 14, Total Loss = 7
    # Avg Gain = 1.0, Avg Loss = 0.5
    # RS = 1.0 / 0.5 = 2.0
    # RSI = 100 - (100 / (1 + 2)) = 100 - 33.333333 = 66.67
    prices = [Decimal("100.00")]
    for _ in range(7):
        prices.append(prices[-1] + Decimal("2.00"))
        prices.append(prices[-1] - Decimal("1.00"))

    assert len(prices) == 15
    rsi = compute_rsi(prices, period=14)
    assert len(rsi) == 15
    for i in range(14):
        assert rsi[i] is None
    assert rsi[14] == Decimal("66.67")


# ---------------------------------------------------------------------------
# Section 4: ATR Indicator Tests
# ---------------------------------------------------------------------------

def test_compute_atr_wilder_smoothing():
    """Verify ATR True Range logic, initial SMA seed, and Wilder smoothing."""
    d0 = datetime.date(2022, 1, 3)
    bars = []
    # Create 5 bars where:
    # Bar 0: H=105, L=95, C=100 -> TR = 10
    # Bar 1: H=108, L=98, C=104 (prev C=100) -> TR = max(10, 8, 2) = 10
    # Bar 2: H=112, L=102, C=110 (prev C=104) -> TR = max(10, 8, 2) = 10
    # Bar 3: H=125, L=115, C=120 (prev C=110) -> TR = max(10, 15, 5) = 15
    # Bar 4: H=122, L=112, C=118 (prev C=120) -> TR = max(10, 2, 8) = 10
    data = [
        ("100", "105", "95", "100"),
        ("101", "108", "98", "104"),
        ("105", "112", "102", "110"),
        ("118", "125", "115", "120"),
        ("119", "122", "112", "118"),
    ]
    for i, (o, h, l, c) in enumerate(data):
        dt = d0 + datetime.timedelta(days=i)
        bars.append(_make_bar(dt, close=c, open_=o, high=h, low=l))

    # Period 3 ATR
    atr_3 = compute_atr(bars, period=3)
    assert len(atr_3) == 5
    assert atr_3[0] is None
    assert atr_3[1] is None
    # Index 2: SMA of TRs (10 + 10 + 10) / 3 = 10.000000
    assert atr_3[2] == Decimal("10.000000")
    # Index 3: TR = 15. ATR = (10 * 2 + 15) / 3 = 35 / 3 = 11.666667
    assert atr_3[3] == Decimal("11.666667")
    # Index 4: TR = 10. ATR = (11.666667 * 2 + 10) / 3 = 33.333334 / 3 = 11.111111
    assert atr_3[4] == Decimal("11.111111")


# ---------------------------------------------------------------------------
# Section 5: Rolling High/Low & Donchian Channel Tests
# ---------------------------------------------------------------------------

def test_compute_rolling_high_low_and_donchian():
    """Verify rolling extremes and Donchian channel boundaries."""
    d0 = datetime.date(2022, 1, 3)
    bars = [
        _make_bar(d0 + datetime.timedelta(days=0), close="100", high="105", low="95"),
        _make_bar(d0 + datetime.timedelta(days=1), close="110", high="115", low="105"),
        _make_bar(d0 + datetime.timedelta(days=2), close="105", high="112", low="99"),
        _make_bar(d0 + datetime.timedelta(days=3), close="120", high="125", low="104"),
    ]

    upper, lower = compute_donchian_channel(bars, period=3)
    assert len(upper) == 4
    assert len(lower) == 4

    assert upper[0] is None
    assert upper[1] is None
    # Index 2: max high in bars 0..2 = max(105, 115, 112) = 115
    assert upper[2] == Decimal("115")
    # Index 2: min low in bars 0..2 = min(95, 105, 99) = 95
    assert lower[2] == Decimal("95")

    # Index 3: max high in bars 1..3 = max(115, 112, 125) = 125
    assert upper[3] == Decimal("125")
    # Index 3: min low in bars 1..3 = min(105, 99, 104) = 99
    assert lower[3] == Decimal("99")


# ---------------------------------------------------------------------------
# Section 6: MACD & Relative Strength Tests
# ---------------------------------------------------------------------------

def test_compute_macd_relationships():
    """Verify that MACD histogram equals macd_line minus signal_line."""
    # Generate 40 bars of steady growth
    prices = [Decimal(100 + i) for i in range(40)]
    macd_line, signal_line, histogram = compute_macd(prices, fast_period=12, slow_period=26, signal_period=9)

    assert len(macd_line) == 40
    assert len(signal_line) == 40
    assert len(histogram) == 40

    # Before slow_period - 1 (25), macd_line is None
    for i in range(25):
        assert macd_line[i] is None

    # First valid macd_line is at index 25
    assert macd_line[25] is not None

    # Check relation where signal_line is present
    for i in range(40):
        if signal_line[i] is not None:
            assert macd_line[i] is not None
            assert histogram[i] is not None
            assert histogram[i] == (macd_line[i] - signal_line[i]).quantize(Decimal("0.000001"))


def test_compute_relative_strength_alignment():
    """Verify excess return vs benchmark over lookback window."""
    d0 = datetime.date(2022, 1, 3)
    # Stock doubles from 100 to 200 (+100%)
    stock_bars = [
        _make_bar(d0, close="100.00"),
        _make_bar(d0 + datetime.timedelta(days=1), close="150.00"),
        _make_bar(d0 + datetime.timedelta(days=2), close="200.00"),
    ]
    # Benchmark rises from 1000 to 1200 (+20%)
    bench_bars = [
        _make_bar(d0, close="1000.00", inst_id="NIFTY50"),
        _make_bar(d0 + datetime.timedelta(days=1), close="1100.00", inst_id="NIFTY50"),
        _make_bar(d0 + datetime.timedelta(days=2), close="1200.00", inst_id="NIFTY50"),
    ]

    # Lookback 2 sessions:
    # Stock return = (200 - 100) / 100 = 1.0000
    # Bench return = (1200 - 1000) / 1000 = 0.2000
    # RS = 1.0000 - 0.2000 = 0.8000
    rs = compute_relative_strength(stock_bars, bench_bars, lookback_sessions=2)
    assert len(rs) == 3
    assert rs[0] is None
    assert rs[1] is None
    assert rs[2] == Decimal("0.8000")


# ---------------------------------------------------------------------------
# Section 7: Weekly Bar Aggregation & Weekly Trend Tests
# ---------------------------------------------------------------------------

def test_aggregate_daily_to_weekly_boundaries():
    """Verify daily aggregation into ISO calendar weekly bars."""
    # Week 1: Monday Jan 3 to Friday Jan 7, 2022
    # Week 2: Monday Jan 10 to Wednesday Jan 12, 2022
    bars = [
        _make_bar(datetime.date(2022, 1, 3), close="100", open_="98", high="102", low="97", volume=1000),
        _make_bar(datetime.date(2022, 1, 4), close="105", open_="100", high="107", low="99", volume=1500),
        _make_bar(datetime.date(2022, 1, 7), close="110", open_="105", high="112", low="104", volume=2000),
        # Week 2
        _make_bar(datetime.date(2022, 1, 10), close="115", open_="112", high="118", low="111", volume=2500),
        _make_bar(datetime.date(2022, 1, 12), close="112", open_="115", high="116", low="110", volume=3000),
    ]

    weekly = aggregate_daily_to_weekly(bars)
    assert len(weekly) == 2

    # Week 1
    w1 = weekly[0]
    assert w1.year == 2022
    assert w1.week == 1
    assert w1.start_date == datetime.date(2022, 1, 3)
    assert w1.end_date == datetime.date(2022, 1, 7)
    assert w1.open == Decimal("98")
    assert w1.high == Decimal("112")
    assert w1.low == Decimal("97")
    assert w1.close == Decimal("110")
    assert w1.volume == 4500
    assert w1.session_count == 3

    # Week 2
    w2 = weekly[1]
    assert w2.year == 2022
    assert w2.week == 2
    assert w2.start_date == datetime.date(2022, 1, 10)
    assert w2.end_date == datetime.date(2022, 1, 12)
    assert w2.open == Decimal("112")
    assert w2.high == Decimal("118")
    assert w2.low == Decimal("110")
    assert w2.close == Decimal("112")
    assert w2.volume == 5500
    assert w2.session_count == 2


# ---------------------------------------------------------------------------
# Section 8: Subsegment Engine & Zero Cross-Gap Leakage Tests
# ---------------------------------------------------------------------------

def test_subsegment_indicator_engine_gap_isolation():
    """
    CRITICAL QUANTITATIVE RESEARCH TEST:
    Verify that an indicator warming up after a missing session never leaks state across the gap.

    Scenario:
    - Expected calendar: Monday (Jan 3), Tuesday (Jan 4), Wednesday (Jan 5), Thursday (Jan 6), Friday (Jan 7)
    - Wednesday (Jan 5) is MISSING in actual observations!
    - Segment 1: Monday, Tuesday
    - Segment 2: Thursday, Friday
    - When computing EMA(2):
      * Segment 1 (len 2): Monday is None, Tuesday is EMA(Mon, Tue)
      * Wednesday: Missing session (not in subsegment output)
      * Segment 2 (len 2): Thursday is FIRST bar of subsegment 2 -> MUST BE NONE!
        It must NOT take EMA from Tuesday because of the missing session!
      * Friday: EMA(Thu, Fri) computed cleanly.
    """
    calendar = [
        datetime.date(2022, 1, 3),  # Mon
        datetime.date(2022, 1, 4),  # Tue
        datetime.date(2022, 1, 5),  # Wed (MISSING)
        datetime.date(2022, 1, 6),  # Thu
        datetime.date(2022, 1, 7),  # Fri
    ]
    bars = [
        _make_bar(calendar[0], close="10.00"),
        _make_bar(calendar[1], close="20.00"),
        # Wed is omitted!
        _make_bar(calendar[3], close="100.00"),
        _make_bar(calendar[4], close="200.00"),
    ]

    results = SubsegmentIndicatorEngine.compute_indicator_on_subsegments(
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
        indicator_fn=lambda seg: compute_ema(seg, 2),
    )

    # Mon (idx 0 of seg 1): None
    assert results[calendar[0]] is None
    # Tue (idx 1 of seg 1): SMA(10, 20) = 15.000000
    assert results[calendar[1]] == Decimal("15.000000")

    # Wed: Not present in actual bars
    assert calendar[2] not in results

    # Thu (idx 0 of seg 2): MUST BE NONE (warm-up of new contiguous segment)!
    # Proves zero cross-gap leakage!
    assert results[calendar[3]] is None

    # Fri (idx 1 of seg 2): SMA(100, 200) = 150.000000
    assert results[calendar[4]] == Decimal("150.000000")


def test_subsegment_indicator_engine_fail_closed_on_unexplained_gaps():
    """Verify that compute_indicator_on_subsegments fails closed when fail_closed_on_unexplained=True."""
    calendar = [
        datetime.date(2022, 1, 3),
        datetime.date(2022, 1, 4),  # Missing unexplained
        datetime.date(2022, 1, 5),
    ]
    bars = [
        _make_bar(calendar[0], close="100.00"),
        _make_bar(calendar[2], close="105.00"),
    ]

    with pytest.raises(IndicatorValidationError, match="Fail-closed: Instrument TEST_STOCK has 1 unexplained missing"):
        SubsegmentIndicatorEngine.compute_indicator_on_subsegments(
            expected_calendar_sessions=calendar,
            actual_price_bars=bars,
            indicator_fn=lambda seg: compute_sma(seg, 2),
            fail_closed_on_unexplained=True,
        )


def test_compute_standard_features_for_instrument_complete():
    """Verify end-to-end feature calculation for an instrument across calendar sessions."""
    d0 = datetime.date(2022, 1, 3)
    calendar = [d0 + datetime.timedelta(days=i) for i in range(60)]
    bars = [
        _make_bar(
            dt,
            close=str(100 + i),
            open_=str(99 + i),
            high=str(102 + i),
            low=str(98 + i),
            volume=5000 + i * 100,
        )
        for i, dt in enumerate(calendar)
    ]

    features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=calendar,
        actual_price_bars=bars,
    )

    assert len(features) == 60
    assert features[0].instrument_id == "TEST_STOCK"
    assert features[0].trade_date == d0
    assert features[0].close == Decimal("100")

    # Bar 0 has all indicators None (warm-up)
    assert features[0].sma_20 is None
    assert features[0].ema_20 is None
    assert features[0].atr_14 is None
    assert features[0].rsi_14 is None

    # Bar 19 has valid 20-period indicators
    assert features[19].sma_20 is not None
    assert features[19].ema_20 is not None
    assert features[19].atr_14 is not None
    assert features[19].rsi_14 is not None
    assert features[19].rolling_high_20 is not None
    assert features[19].rolling_low_20 is not None

    # Bar 19 still has 50-period indicators None
    assert features[19].sma_50 is None
    assert features[19].ema_50 is None

    # Bar 49 has valid 50-period indicators
    assert features[49].sma_50 is not None
    assert features[49].ema_50 is not None
    assert features[49].rolling_high_50 is not None
    assert features[49].rolling_low_50 is not None


# ---------------------------------------------------------------------------
# Section 9: Audit Findings Regression Tests (DeepSeek Peer Review Remediation)
# ---------------------------------------------------------------------------

def test_finding_f01_relative_strength_gap_isolation():
    """
    Finding F-01 Regression Test:
    Verify that relative_strength_50 NEVER leaks lookbacks across a missing calendar session.

    Setup (Probe 2 from audit):
    - 60 calendar sessions.
    - Session index 10 is missing in stock price bars.
    - Subsegment 1 has 10 bars (indices 0..9).
    - Subsegment 2 has 49 bars (indices 11..59).
    - Since lookback is 50 sessions, neither subsegment has 51 continuous bars.
    - Therefore, ALL 59 available bars MUST have relative_strength_50 == None.
    - (The unpatched bug produced 9 contaminated non-None values by spanning the gap).
    """
    d0 = datetime.date(2022, 1, 3)
    calendar = [d0 + datetime.timedelta(days=i) for i in range(60)]
    gap_date = calendar[10]

    stock_bars = [_make_bar(d, close=str(100 + i)) for i, d in enumerate(calendar) if d != gap_date]
    bench_bars = [_make_bar(d, close=str(1000 + i), inst_id="BENCH") for i, d in enumerate(calendar)]

    features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=calendar,
        actual_price_bars=stock_bars,
        benchmark_bars=bench_bars,
    )

    assert len(features) == 59
    # Invariant: ZERO post-gap bars have relative_strength_50 populated because subsegment len (49) < 51
    non_none_rs_count = sum(1 for f in features if f.relative_strength_50 is not None)
    assert non_none_rs_count == 0, f"Expected 0 non-None RS values, got {non_none_rs_count} (cross-gap leakage detected)"


def test_finding_f02_compute_relative_strength_with_observations():
    """
    Finding F-02 Regression Test:
    Verify that compute_relative_strength accepts ExchangeSessionObservation directly
    without raising AttributeError, producing identical values to PriceBar inputs.
    """
    d0 = datetime.date(2022, 1, 3)
    days = [d0 + datetime.timedelta(days=i) for i in range(5)]

    obs_stock = [_make_obs(days[i], str(100 + i * 10)) for i in range(5)]
    obs_bench = [_make_obs(days[i], str(1000 + i * 10), inst_id="BENCH") for i in range(5)]

    rs_values = compute_relative_strength(obs_stock, obs_bench, lookback_sessions=2)
    assert len(rs_values) == 5
    assert rs_values[0] is None
    assert rs_values[1] is None
    # Index 2: Stock: (120 - 100) / 100 = 0.2000. Bench: (1020 - 1000) / 1000 = 0.0200. RS = 0.1800
    assert rs_values[2] == Decimal("0.1800")


def test_finding_f03_off_calendar_bar_fails_closed():
    """
    Finding F-03 Regression Test:
    Verify that partition_into_continuous_subsegments raises ValueError when
    fed an off-calendar price bar (fail-closed invariant).
    """
    d0 = datetime.date(2022, 1, 3)
    cal = [d0, d0 + datetime.timedelta(days=2)]  # Jan 3 and Jan 5
    off_cal_bar = _make_bar(d0 + datetime.timedelta(days=1), close="101")  # Jan 4 (not in cal)

    bars = [_make_bar(cal[0], close="100"), off_cal_bar, _make_bar(cal[1], close="102")]

    from signal_core.contracts.exchange_series import PriceSeriesContinuityValidator
    with pytest.raises(ValueError, match="off-calendar date"):
        PriceSeriesContinuityValidator.partition_into_continuous_subsegments(cal, bars)


def test_finding_f04_indicator_output_length_mismatch_raises_validation_error():
    """
    Finding F-04 Regression Test:
    Verify that compute_indicator_on_subsegments raises IndicatorValidationError
    when an indicator returns an invalid output length (survives python -O).
    """
    cal = [datetime.date(2022, 1, 3), datetime.date(2022, 1, 4)]
    bars = [_make_bar(cal[0], close="100"), _make_bar(cal[1], close="101")]

    # Malformed indicator returning 1 item for a 2-item segment
    with pytest.raises(IndicatorValidationError, match="Indicator output length"):
        SubsegmentIndicatorEngine.compute_indicator_on_subsegments(
            expected_calendar_sessions=cal,
            actual_price_bars=bars,
            indicator_fn=lambda seg: [Decimal("100")],  # Only 1 item returned!
        )


def test_finding_f05_f06_weekly_trend_and_gap_detection():
    """
    Finding F-05 & F-06 Regression Test:
    Verify compute_weekly_trend coverage (bullish, bearish, insufficient history)
    and verify that non-consecutive ISO weeks refuse to smooth across gaps.
    """
    d0 = datetime.date(2022, 1, 3)  # Week 1, 2022

    # 1. Insufficient history (< 10 weeks)
    short_bars = [_make_bar(d0 + datetime.timedelta(weeks=i), close=str(100 + i)) for i in range(5)]
    close, ema, trend = compute_weekly_trend(short_bars, weekly_ema_period=10)
    assert close is not None
    assert ema is None
    assert trend is None

    # 2. Continuous 12 consecutive weeks (Bullish trend: rising closes)
    continuous_bars = [_make_bar(d0 + datetime.timedelta(weeks=i), close=str(100 + i * 2)) for i in range(12)]
    close, ema, trend = compute_weekly_trend(continuous_bars, weekly_ema_period=10)
    assert close is not None
    assert ema is not None
    assert trend is True  # Rising closes -> bullish

    # 3. Continuous 12 consecutive weeks (Bearish trend: falling closes)
    bearish_bars = [_make_bar(d0 + datetime.timedelta(weeks=i), close=str(200 - i * 5)) for i in range(12)]
    close, ema, trend = compute_weekly_trend(bearish_bars, weekly_ema_period=10)
    assert close is not None
    assert ema is not None
    assert trend is False  # Falling closes -> bearish

    # 4. Weekly gap: Week 5 is missing (jump from week 4 to week 6)
    # Refuses to smooth across missing calendar week!
    gapped_weeks = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12]  # week 5 omitted
    gapped_bars = [_make_bar(d0 + datetime.timedelta(weeks=w), close=str(100 + w)) for w in gapped_weeks]
    close, ema, trend = compute_weekly_trend(gapped_bars, weekly_ema_period=10)
    assert close == Decimal("112")
    assert ema is None  # Fails closed on missing calendar week
    assert trend is None

    # 5. Duplicate daily dates reject in aggregate_daily_to_weekly
    dup_bars = [_make_bar(d0, close="100"), _make_bar(d0, close="101")]
    with pytest.raises(IndicatorValidationError, match="Duplicate daily bar"):
        aggregate_daily_to_weekly(dup_bars)


def test_finding_f07_duplicate_trade_dates_in_validator():
    """
    Finding F-07 Regression Test:
    Verify that validate_series_continuity raises ValueError on duplicate bar dates.
    """
    d0 = datetime.date(2022, 1, 3)
    cal = [d0]
    bars = [_make_bar(d0, close="100"), _make_bar(d0, close="101")]

    from signal_core.contracts.exchange_series import PriceSeriesContinuityValidator
    with pytest.raises(ValueError, match="Duplicate price record detected"):
        PriceSeriesContinuityValidator.validate_series_continuity("INST-1", "TEST", cal, bars)


def test_finding_f11_features_enriched_with_series_and_isin():
    """
    Finding F-11 Regression Test:
    Verify that InstrumentTechnicalFeatures preserves raw_series_code,
    series_classification, and isin when fed ExchangeSessionObservation.
    """
    d0 = datetime.date(2022, 1, 3)
    cal = [d0, d0 + datetime.timedelta(days=1)]
    obs1 = _make_obs(cal[0], close="100", series="EQ")
    obs2 = _make_obs(cal[1], close="102", series="BE")

    features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
        expected_calendar_sessions=cal,
        actual_price_bars=[obs1, obs2],
    )

    assert len(features) == 2
    assert features[0].raw_series_code == "EQ"
    assert features[0].series_classification == ExchangeSeries.EQ
    assert features[0].isin == "INE000A01001"

    assert features[1].raw_series_code == "BE"
    assert features[1].series_classification == ExchangeSeries.BE
    assert features[1].isin == "INE000A01001"

