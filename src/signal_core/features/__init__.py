"""Technical Indicators and Feature Computation Package for Signal Atlas Core.

Exports pure mathematical indicators and subsegment-bounded indicator engines:
- SMA, EMA, RSI, ATR, Rolling High/Low, Donchian Channel, MACD
- Relative Strength vs Benchmark
- WeeklyBar aggregation & Weekly trend
- SubsegmentIndicatorEngine and InstrumentTechnicalFeatures
"""

from signal_core.features.indicators import (
    IndicatorValidationError,
    PRECISION_6,
    PRECISION_4,
    PRECISION_2,
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

from signal_core.features.engine import (
    InstrumentTechnicalFeatures,
    SubsegmentIndicatorEngine,
)

__all__ = [
    "IndicatorValidationError",
    "PRECISION_6",
    "PRECISION_4",
    "PRECISION_2",
    "WeeklyBar",
    "aggregate_daily_to_weekly",
    "compute_atr",
    "compute_donchian_channel",
    "compute_ema",
    "compute_macd",
    "compute_relative_strength",
    "compute_rolling_high",
    "compute_rolling_low",
    "compute_rsi",
    "compute_sma",
    "compute_weekly_trend",
    "extract_price_series",
    "validate_and_extract_decimal",
    "InstrumentTechnicalFeatures",
    "SubsegmentIndicatorEngine",
]
