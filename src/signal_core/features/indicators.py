"""Pure Mathematical Technical Indicator Formulas for Signal Atlas Core.

All indicator functions are pure, deterministic, and free of I/O.
Computations strictly preserve Decimal precision without binary floating-point representation drift.
All calculations enforce zero-lookahead: at index t, only records from 0..t are utilized.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional, Sequence, Tuple, Union

from signal_core.contracts.exchange_series import ExchangeSessionObservation
from signal_core.contracts.price_bar import PriceBar

PRECISION_6 = Decimal("0.000001")
PRECISION_4 = Decimal("0.0001")
PRECISION_2 = Decimal("0.01")

PriceRecordItem = Union[PriceBar, ExchangeSessionObservation]
NumericInput = Union[Decimal, int, str]


class IndicatorValidationError(ValueError):
    """Raised when indicator parameters or input series violate mathematical invariants."""
    pass


def validate_and_extract_decimal(val: Any, field_name: str = "value") -> Decimal:
    """
    Validates that a numeric value is an exact Decimal (or integer convertible to Decimal).
    Strictly rejects binary floats, booleans, and non-finite values (NaN, Inf).
    """
    if isinstance(val, bool):
        raise IndicatorValidationError(f"{field_name} cannot be a boolean.")
    if isinstance(val, float):
        raise IndicatorValidationError(f"{field_name} cannot be a binary float. Exact Decimal required.")
    if isinstance(val, int):
        return Decimal(val)
    if isinstance(val, Decimal):
        if not val.is_finite():
            raise IndicatorValidationError(f"{field_name} must be a finite Decimal, got {val}.")
        return val
    if isinstance(val, str):
        try:
            d = Decimal(val)
            if not d.is_finite():
                raise IndicatorValidationError(f"{field_name} string '{val}' is not finite.")
            return d
        except Exception as e:
            raise IndicatorValidationError(f"Invalid decimal string '{val}' for {field_name}: {e}")
    raise IndicatorValidationError(f"{field_name} must be a Decimal or int, got {type(val).__name__}.")


def extract_price_series(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    price_field: str = "close",
) -> List[Decimal]:
    """
    Extracts a validated series of Decimals from a sequence of PriceBar,
    ExchangeSessionObservation, or raw Decimal values.
    """
    if not records:
        return []

    extracted: List[Decimal] = []
    for idx, item in enumerate(records):
        if isinstance(item, PriceBar):
            val = getattr(item, price_field)
            extracted.append(validate_and_extract_decimal(val, f"{price_field}[{idx}]"))
        elif isinstance(item, ExchangeSessionObservation):
            val = getattr(item.price_bar, price_field)
            extracted.append(validate_and_extract_decimal(val, f"{price_field}[{idx}]"))
        elif isinstance(item, (Decimal, int)):
            extracted.append(validate_and_extract_decimal(item, f"item[{idx}]"))
        else:
            raise IndicatorValidationError(
                f"Unsupported record type at index {idx}: {type(item).__name__}. "
                "Expected PriceBar, ExchangeSessionObservation, or Decimal."
            )
    return extracted


def compute_sma(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    period: int,
    price_field: str = "close",
) -> List[Optional[Decimal]]:
    """
    Computes Simple Moving Average (SMA).
    Returns None for indices 0 to period - 2.
    Index period - 1 holds the first valid SMA value.
    Zero-lookahead: bar t only depends on bars t - period + 1 .. t.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    series = extract_price_series(records, price_field)
    n = len(series)
    if n < period:
        return [None] * n

    result: List[Optional[Decimal]] = [None] * (period - 1)
    period_dec = Decimal(period)

    # Initial window sum
    window_sum = sum(series[:period])
    result.append((window_sum / period_dec).quantize(PRECISION_6, rounding=ROUND_HALF_UP))

    # Rolling update
    for i in range(period, n):
        window_sum += series[i] - series[i - period]
        result.append((window_sum / period_dec).quantize(PRECISION_6, rounding=ROUND_HALF_UP))

    return result


def compute_ema(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    period: int,
    price_field: str = "close",
) -> List[Optional[Decimal]]:
    """
    Computes Exponential Moving Average (EMA).
    - Initial seed at index period - 1 is the arithmetic mean (SMA) of the first 'period' values.
    - Subsequent values: EMA_t = alpha * Price_t + (1 - alpha) * EMA_{t-1}
      where alpha = 2 / (period + 1).
    - Returns None for indices prior to period - 1.
    - Zero-lookahead: bar t depends solely on bars <= t.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    series = extract_price_series(records, price_field)
    n = len(series)
    if n < period:
        return [None] * n

    result: List[Optional[Decimal]] = [None] * (period - 1)
    period_dec = Decimal(period)

    # Initial seed is SMA of first 'period' bars
    initial_sma = sum(series[:period]) / period_dec
    current_ema = initial_sma.quantize(PRECISION_6, rounding=ROUND_HALF_UP)
    result.append(current_ema)

    alpha = Decimal("2") / Decimal(period + 1)
    one_minus_alpha = Decimal("1") - alpha

    for i in range(period, n):
        current_ema = (alpha * series[i] + one_minus_alpha * current_ema).quantize(
            PRECISION_6, rounding=ROUND_HALF_UP
        )
        result.append(current_ema)

    return result


def compute_rsi(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    period: int = 14,
    price_field: str = "close",
) -> List[Optional[Decimal]]:
    """
    Computes Relative Strength Index (RSI) using J. Welles Wilder's smoothing method.
    - Period defaults to 14 sessions.
    - Initial average gain/loss at index 'period' is the arithmetic mean of the first 'period' gains/losses.
    - Subsequent smoothed values:
        AvgGain_t = (AvgGain_{t-1} * (period - 1) + Gain_t) / period
        AvgLoss_t = (AvgLoss_{t-1} * (period - 1) + Loss_t) / period
    - RSI = 100 - (100 / (1 + RS)) where RS = AvgGain / AvgLoss.
    - Returns None for indices < period.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    series = extract_price_series(records, price_field)
    n = len(series)
    if n <= period:
        return [None] * n

    result: List[Optional[Decimal]] = [None] * period

    gains: List[Decimal] = []
    losses: List[Decimal] = []

    for i in range(1, n):
        change = series[i] - series[i - 1]
        if change > Decimal("0"):
            gains.append(change)
            losses.append(Decimal("0"))
        else:
            gains.append(Decimal("0"))
            losses.append(-change)

    # Initial average gain & loss over first 'period' price changes
    period_dec = Decimal(period)
    avg_gain = sum(gains[:period]) / period_dec
    avg_loss = sum(losses[:period]) / period_dec

    def _calc_rsi(g: Decimal, l: Decimal) -> Decimal:
        if l == Decimal("0"):
            return Decimal("100.00") if g > Decimal("0") else Decimal("50.00")
        if g == Decimal("0"):
            return Decimal("0.00")
        rs = g / l
        rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
        return rsi.quantize(PRECISION_2, rounding=ROUND_HALF_UP)

    result.append(_calc_rsi(avg_gain, avg_loss))

    # Wilder smoothing for subsequent bars
    weight_prev = period_dec - Decimal("1")
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * weight_prev + gains[i]) / period_dec
        avg_loss = (avg_loss * weight_prev + losses[i]) / period_dec
        result.append(_calc_rsi(avg_gain, avg_loss))

    return result


def compute_atr(
    records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
    period: int = 14,
) -> List[Optional[Decimal]]:
    """
    Computes Average True Range (ATR) using J. Welles Wilder's smoothing method.
    True Range:
      TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
      For bar 0: TR_0 = H_0 - L_0.
    Initial ATR at index period - 1 is arithmetic mean of first 'period' TRs.
    Subsequent ATR:
      ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period
    Returns None for indices < period - 1.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    n = len(records)
    if n < period:
        return [None] * n

    highs: List[Decimal] = []
    lows: List[Decimal] = []
    closes: List[Decimal] = []

    for idx, item in enumerate(records):
        bar = item.price_bar if isinstance(item, ExchangeSessionObservation) else item
        if not isinstance(bar, PriceBar):
            raise IndicatorValidationError(
                f"compute_atr requires PriceBar or ExchangeSessionObservation, got {type(item).__name__} at index {idx}."
            )
        highs.append(bar.high)
        lows.append(bar.low)
        closes.append(bar.close)

    true_ranges: List[Decimal] = []
    # Bar 0 True Range
    true_ranges.append(highs[0] - lows[0])

    for i in range(1, n):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(tr1, tr2, tr3))

    result: List[Optional[Decimal]] = [None] * (period - 1)
    period_dec = Decimal(period)

    initial_atr = sum(true_ranges[:period]) / period_dec
    current_atr = initial_atr.quantize(PRECISION_6, rounding=ROUND_HALF_UP)
    result.append(current_atr)

    weight_prev = period_dec - Decimal("1")
    for i in range(period, n):
        current_atr = ((current_atr * weight_prev + true_ranges[i]) / period_dec).quantize(
            PRECISION_6, rounding=ROUND_HALF_UP
        )
        result.append(current_atr)

    return result


def compute_rolling_high(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    period: int,
    price_field: str = "high",
) -> List[Optional[Decimal]]:
    """
    Computes rolling maximum price over trailing 'period' sessions.
    Returns None for indices 0 to period - 2.
    Index period - 1 holds max over bars 0..period - 1.
    Zero lookahead: bar t only inspects bars t - period + 1 .. t.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    series = extract_price_series(records, price_field)
    n = len(series)
    if n < period:
        return [None] * n

    result: List[Optional[Decimal]] = [None] * (period - 1)
    for i in range(period - 1, n):
        result.append(max(series[i - period + 1 : i + 1]))

    return result


def compute_rolling_low(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    period: int,
    price_field: str = "low",
) -> List[Optional[Decimal]]:
    """
    Computes rolling minimum price over trailing 'period' sessions.
    Returns None for indices 0 to period - 2.
    Index period - 1 holds min over bars 0..period - 1.
    Zero lookahead: bar t only inspects bars t - period + 1 .. t.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise IndicatorValidationError(f"Period must be a positive integer, got {period!r}.")

    series = extract_price_series(records, price_field)
    n = len(series)
    if n < period:
        return [None] * n

    result: List[Optional[Decimal]] = [None] * (period - 1)
    for i in range(period - 1, n):
        result.append(min(series[i - period + 1 : i + 1]))

    return result


def compute_donchian_channel(
    records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
    period: int,
) -> Tuple[List[Optional[Decimal]], List[Optional[Decimal]]]:
    """
    Computes Donchian Channel (Upper Channel = Rolling High, Lower Channel = Rolling Low).
    Returns (upper_channel, lower_channel).
    """
    upper = compute_rolling_high(records, period, price_field="high")
    lower = compute_rolling_low(records, period, price_field="low")
    return upper, lower


def compute_macd(
    records: Sequence[Union[PriceRecordItem, Decimal, int]],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_field: str = "close",
) -> Tuple[List[Optional[Decimal]], List[Optional[Decimal]], List[Optional[Decimal]]]:
    """
    Computes standard MACD (Moving Average Convergence Divergence).
    - macd_line = EMA(fast) - EMA(slow)
    - signal_line = EMA(signal_period) of macd_line
    - histogram = macd_line - signal_line
    Returns (macd_line, signal_line, histogram).
    """
    for p, name in [(fast_period, "fast_period"), (slow_period, "slow_period"), (signal_period, "signal_period")]:
        if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
            raise IndicatorValidationError(f"{name} must be a positive integer, got {p!r}.")

    if fast_period >= slow_period:
        raise IndicatorValidationError(
            f"fast_period ({fast_period}) must be strictly less than slow_period ({slow_period})."
        )

    series = extract_price_series(records, price_field)
    n = len(series)

    fast_ema = compute_ema(series, fast_period)
    slow_ema = compute_ema(series, slow_period)

    macd_line: List[Optional[Decimal]] = [None] * n
    for i in range(n):
        f = fast_ema[i]
        s = slow_ema[i]
        if f is not None and s is not None:
            macd_line[i] = (f - s).quantize(PRECISION_6, rounding=ROUND_HALF_UP)

    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]
    signal_line: List[Optional[Decimal]] = [None] * n
    histogram: List[Optional[Decimal]] = [None] * n

    if len(valid_indices) >= signal_period:
        valid_values = [macd_line[i] for i in valid_indices]  # all Decimal
        sig_ema = compute_ema(valid_values, signal_period)

        for sub_idx, orig_idx in enumerate(valid_indices):
            s_val = sig_ema[sub_idx]
            signal_line[orig_idx] = s_val
            m_val = macd_line[orig_idx]
            if s_val is not None and m_val is not None:
                histogram[orig_idx] = (m_val - s_val).quantize(PRECISION_6, rounding=ROUND_HALF_UP)

    return macd_line, signal_line, histogram


def compute_relative_strength(
    stock_records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
    benchmark_records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
    lookback_sessions: int = 50,
) -> List[Optional[Decimal]]:
    """
    Computes comparative Relative Strength (excess return) of stock vs benchmark
    over trailing lookback_sessions:
      R_stock = (Close_t - Close_{t-lookback}) / Close_{t-lookback}
      R_bench = (Bench_t - Bench_{t-lookback}) / Bench_{t-lookback}
      RS = R_stock - R_bench
    Requires exact date alignment between stock and benchmark records.
    Returns list of Optional[Decimal] aligned with stock_records.
    """
    if isinstance(lookback_sessions, bool) or not isinstance(lookback_sessions, int) or lookback_sessions <= 0:
        raise IndicatorValidationError(f"lookback_sessions must be positive integer, got {lookback_sessions!r}.")

    n = len(stock_records)
    if n <= lookback_sessions:
        return [None] * n

    # Extract dates and closes
    stock_dates = [b.trade_date for b in stock_records]
    bench_by_date = {b.trade_date: b.close for b in benchmark_records}

    result: List[Optional[Decimal]] = [None] * lookback_sessions

    for i in range(lookback_sessions, n):
        cur_date = stock_dates[i]
        past_date = stock_dates[i - lookback_sessions]

        # Verify benchmark dates exist
        if cur_date not in bench_by_date or past_date not in bench_by_date:
            result.append(None)
            continue

        s_curr = stock_records[i].close
        s_past = stock_records[i - lookback_sessions].close
        b_curr = bench_by_date[cur_date]
        b_past = bench_by_date[past_date]

        if s_past <= Decimal("0") or b_past <= Decimal("0"):
            result.append(None)
            continue

        r_stock = (s_curr - s_past) / s_past
        r_bench = (b_curr - b_past) / b_past
        rs = (r_stock - r_bench).quantize(PRECISION_4, rounding=ROUND_HALF_UP)
        result.append(rs)

    return result


@dataclass(frozen=True, slots=True)
class WeeklyBar:
    """
    Consolidated weekly market bar derived deterministically from daily trading sessions.
    Follows ISO calendar year and week.
    """
    year: int
    week: int
    start_date: datetime.date
    end_date: datetime.date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    session_count: int


def aggregate_daily_to_weekly(
    records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
) -> List[WeeklyBar]:
    """
    Aggregates daily bars into standard calendar weekly bars (ISO calendar year/week).
    Preserves exact chronological order, handles holidays and truncated trading weeks.
    """
    if not records:
        return []

    sorted_bars = sorted(
        [r.price_bar if isinstance(r, ExchangeSessionObservation) else r for r in records],
        key=lambda b: b.trade_date,
    )

    weekly_bars: List[WeeklyBar] = []
    current_key: Optional[Tuple[int, int]] = None
    w_start: Optional[datetime.date] = None
    w_end: Optional[datetime.date] = None
    w_open: Optional[Decimal] = None
    w_high: Optional[Decimal] = None
    w_low: Optional[Decimal] = None
    w_close: Optional[Decimal] = None
    w_volume: int = 0
    w_count: int = 0

    for bar in sorted_bars:
        iso_year, iso_week, _ = bar.trade_date.isocalendar()
        key = (iso_year, iso_week)

        if key != current_key:
            # Emit previous bar if exists
            if current_key is not None:
                assert w_start is not None and w_end is not None
                assert w_open is not None and w_high is not None and w_low is not None and w_close is not None
                weekly_bars.append(
                    WeeklyBar(
                        year=current_key[0],
                        week=current_key[1],
                        start_date=w_start,
                        end_date=w_end,
                        open=w_open,
                        high=w_high,
                        low=w_low,
                        close=w_close,
                        volume=w_volume,
                        session_count=w_count,
                    )
                )

            current_key = key
            w_start = bar.trade_date
            w_end = bar.trade_date
            w_open = bar.open
            w_high = bar.high
            w_low = bar.low
            w_close = bar.close
            w_volume = bar.volume
            w_count = 1
        else:
            w_end = bar.trade_date
            assert w_high is not None and w_low is not None
            w_high = max(w_high, bar.high)
            w_low = min(w_low, bar.low)
            w_close = bar.close
            w_volume += bar.volume
            w_count += 1

    # Emit final bar
    if current_key is not None:
        assert w_start is not None and w_end is not None
        assert w_open is not None and w_high is not None and w_low is not None and w_close is not None
        weekly_bars.append(
            WeeklyBar(
                year=current_key[0],
                week=current_key[1],
                start_date=w_start,
                end_date=w_end,
                open=w_open,
                high=w_high,
                low=w_low,
                close=w_close,
                volume=w_volume,
                session_count=w_count,
            )
        )

    return weekly_bars


def compute_weekly_trend(
    records: Sequence[Union[PriceBar, ExchangeSessionObservation]],
    weekly_ema_period: int = 10,
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[bool]]:
    """
    Computes latest weekly trend derived from daily data:
    - Aggregates daily records into weekly bars.
    - Computes weekly EMA (default: 10-week EMA, ~50 daily sessions).
    - Returns (latest_weekly_close, latest_weekly_ema, is_bullish).
    """
    weekly_bars = aggregate_daily_to_weekly(records)
    if len(weekly_bars) < weekly_ema_period:
        return (
            weekly_bars[-1].close if weekly_bars else None,
            None,
            None,
        )

    w_closes = [b.close for b in weekly_bars]
    w_emas = compute_ema(w_closes, weekly_ema_period)

    latest_close = w_closes[-1]
    latest_ema = w_emas[-1]
    is_bullish = (latest_close > latest_ema) if latest_ema is not None else None

    return latest_close, latest_ema, is_bullish
