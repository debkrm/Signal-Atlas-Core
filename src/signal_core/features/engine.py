"""Subsegment-Aware Technical Indicator and Feature Computation Engine.

Guarantees non-negotiable quantitative research invariants:
1. Indicators operate strictly within contiguous, date-continuous subsegments.
2. Zero cross-gap leakage: indicators warm up afresh after any missing session.
3. Zero silent forward-filling: calendar dates without records return None.
4. Fail-closed verification: option to fail closed if unexplained missing sessions are present.
5. Exact Decimal precision throughout all indicator outputs.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from signal_core.contracts.exchange_series import (
    ExchangeSeries,
    ExchangeSessionObservation,
    InstrumentListingInterval,
    PriceSeriesContinuityValidator,
    PriceSeriesGapType,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.features.indicators import (
    IndicatorValidationError,
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
)

PriceRecordItem = Union[PriceBar, ExchangeSessionObservation]


@dataclass(frozen=True, slots=True)
class InstrumentTechnicalFeatures:
    """
    Immutable container of computed technical indicators for a single market session.
    All numeric fields are exact Decimal instances (or None during warm-up).
    Preserves raw and typed series classification and ISIN anchor for strategy eligibility checks.
    """
    instrument_id: str
    trade_date: datetime.date
    close: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    raw_series_code: Optional[str] = None
    series_classification: Optional[ExchangeSeries] = None
    isin: Optional[str] = None
    sma_20: Optional[Decimal] = None
    sma_50: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None
    ema_50: Optional[Decimal] = None
    ema_200: Optional[Decimal] = None
    atr_14: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    rolling_high_20: Optional[Decimal] = None
    rolling_low_20: Optional[Decimal] = None
    rolling_high_50: Optional[Decimal] = None
    rolling_low_50: Optional[Decimal] = None
    relative_strength_50: Optional[Decimal] = None


class SubsegmentIndicatorEngine:
    """
    Orchestrates technical indicator calculations strictly bounded by calendar continuity.
    Uses PriceSeriesContinuityValidator to partition observations into contiguous blocks.
    """

    @classmethod
    def compute_indicator_on_subsegments(
        cls,
        expected_calendar_sessions: Sequence[datetime.date],
        actual_price_bars: Sequence[PriceRecordItem],
        indicator_fn: Callable[[Sequence[PriceRecordItem]], List[Optional[Decimal]]],
        fail_closed_on_unexplained: bool = False,
        listing_interval: Optional[InstrumentListingInterval] = None,
    ) -> Dict[datetime.date, Optional[Decimal]]:
        """
        Executes an indicator function strictly within contiguous subsegments.

        Guarantees:
        - If actual_price_bars is interrupted by a missing calendar session, the indicator
          terminates at the gap boundary and re-seeds from scratch in the next subsegment.
        - Returns a mapping from trade_date to Optional[Decimal] for every available bar.
        - If fail_closed_on_unexplained is True, raises IndicatorValidationError if any
          unexplained missing record is detected by PriceSeriesContinuityValidator.
        """
        if not actual_price_bars:
            return {}

        # 1. Check fail-closed continuity if requested
        if fail_closed_on_unexplained:
            first_bar = actual_price_bars[0]
            inst_id = first_bar.instrument_id
            audit = PriceSeriesContinuityValidator.validate_series_continuity(
                instrument_id=inst_id,
                symbol=inst_id,
                expected_calendar_sessions=expected_calendar_sessions,
                actual_price_bars=actual_price_bars,
                listing_interval=listing_interval,
            )
            if audit.has_unexplained_gaps:
                raise IndicatorValidationError(
                    f"Fail-closed: Instrument {inst_id} has {audit.unexplained_missing_count} "
                    f"unexplained missing session(s). Refusing indicator computation."
                )

        # 2. Partition into strictly contiguous subsegments
        subsegments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
            expected_calendar_sessions=expected_calendar_sessions,
            actual_price_bars=actual_price_bars,
        )

        results_by_date: Dict[datetime.date, Optional[Decimal]] = {}

        for segment in subsegments:
            seg_values = indicator_fn(segment)
            if len(seg_values) != len(segment):
                raise IndicatorValidationError(
                    f"Indicator output length ({len(seg_values)}) does not match segment length ({len(segment)})."
                )
            for bar, val in zip(segment, seg_values):
                results_by_date[bar.trade_date] = val

        return results_by_date

    @classmethod
    def compute_standard_features_for_instrument(
        cls,
        expected_calendar_sessions: Sequence[datetime.date],
        actual_price_bars: Sequence[PriceRecordItem],
        benchmark_bars: Optional[Sequence[PriceRecordItem]] = None,
        fail_closed_on_unexplained: bool = False,
        listing_interval: Optional[InstrumentListingInterval] = None,
    ) -> List[InstrumentTechnicalFeatures]:
        """
        Computes the standard suite of institutional indicators:
        - SMA: 20, 50
        - EMA: 20, 50, 200
        - ATR: 14
        - RSI: 14
        - Rolling High / Low: 20, 50
        - Relative Strength vs Benchmark (lookback 50)
        Returns a sorted list of InstrumentTechnicalFeatures, one per available price bar.
        """
        if not actual_price_bars:
            return []

        sorted_bars = sorted(actual_price_bars, key=lambda b: b.trade_date)
        first_item = sorted_bars[0]
        inst_id = first_item.instrument_id

        # 1. Validate continuity ONCE upfront (if requested)
        if fail_closed_on_unexplained:
            audit = PriceSeriesContinuityValidator.validate_series_continuity(
                instrument_id=inst_id,
                symbol=inst_id,
                expected_calendar_sessions=expected_calendar_sessions,
                actual_price_bars=sorted_bars,
                listing_interval=listing_interval,
            )
            if audit.has_unexplained_gaps:
                raise IndicatorValidationError(
                    f"Fail-closed: Instrument {inst_id} has {audit.unexplained_missing_count} "
                    f"unexplained missing session(s). Refusing indicator computation."
                )

        # 2. Partition into contiguous subsegments ONCE upfront (reused across all indicators)
        subsegments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
            expected_calendar_sessions=expected_calendar_sessions,
            actual_price_bars=sorted_bars,
        )

        def _run_subsegment_indicator(
            fn: Callable[[Sequence[PriceRecordItem]], List[Optional[Decimal]]]
        ) -> Dict[datetime.date, Optional[Decimal]]:
            res: Dict[datetime.date, Optional[Decimal]] = {}
            for seg in subsegments:
                vals = fn(seg)
                if len(vals) != len(seg):
                    raise IndicatorValidationError(
                        f"Indicator output length ({len(vals)}) does not match segment length ({len(seg)})."
                    )
                for b, v in zip(seg, vals):
                    res[b.trade_date] = v
            return res

        sma_20_map = _run_subsegment_indicator(lambda s: compute_sma(s, 20))
        sma_50_map = _run_subsegment_indicator(lambda s: compute_sma(s, 50))
        ema_20_map = _run_subsegment_indicator(lambda s: compute_ema(s, 20))
        ema_50_map = _run_subsegment_indicator(lambda s: compute_ema(s, 50))
        ema_200_map = _run_subsegment_indicator(lambda s: compute_ema(s, 200))
        atr_14_map = _run_subsegment_indicator(lambda s: compute_atr(s, 14))
        rsi_14_map = _run_subsegment_indicator(lambda s: compute_rsi(s, 14))
        hi_20_map = _run_subsegment_indicator(lambda s: compute_rolling_high(s, 20))
        lo_20_map = _run_subsegment_indicator(lambda s: compute_rolling_low(s, 20))
        hi_50_map = _run_subsegment_indicator(lambda s: compute_rolling_high(s, 50))
        lo_50_map = _run_subsegment_indicator(lambda s: compute_rolling_low(s, 50))

        # Relative strength 50 must ALSO be computed strictly per subsegment (zero cross-gap leakage)
        rs_50_map: Dict[datetime.date, Optional[Decimal]] = {}
        if benchmark_bars:
            rs_50_map = _run_subsegment_indicator(
                lambda s: compute_relative_strength(s, benchmark_bars, lookback_sessions=50)
            )

        features: List[InstrumentTechnicalFeatures] = []
        for bar_item in sorted_bars:
            bar = bar_item.price_bar if isinstance(bar_item, ExchangeSessionObservation) else bar_item
            dt = bar.trade_date

            raw_code = bar_item.raw_series_code if isinstance(bar_item, ExchangeSessionObservation) else None
            series_cls = bar_item.series_classification if isinstance(bar_item, ExchangeSessionObservation) else None
            isin = bar_item.isin if isinstance(bar_item, ExchangeSessionObservation) else None

            features.append(
                InstrumentTechnicalFeatures(
                    instrument_id=inst_id,
                    trade_date=dt,
                    close=bar.close,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    volume=bar.volume,
                    raw_series_code=raw_code,
                    series_classification=series_cls,
                    isin=isin,
                    sma_20=sma_20_map.get(dt),
                    sma_50=sma_50_map.get(dt),
                    ema_20=ema_20_map.get(dt),
                    ema_50=ema_50_map.get(dt),
                    ema_200=ema_200_map.get(dt),
                    atr_14=atr_14_map.get(dt),
                    rsi_14=rsi_14_map.get(dt),
                    rolling_high_20=hi_20_map.get(dt),
                    rolling_low_20=lo_20_map.get(dt),
                    rolling_high_50=hi_50_map.get(dt),
                    rolling_low_50=lo_50_map.get(dt),
                    relative_strength_50=rs_50_map.get(dt),
                )
            )

        return features

