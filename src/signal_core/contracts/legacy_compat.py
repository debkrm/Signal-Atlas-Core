"""Legacy Compatibility and Adjustment Metadata Preservation.

Preserves historical corporate action adjustment multipliers, legacy volume strings,
and legacy fingerprint canonicalization routines without polluting the clean,
raw-only PriceBar domain contract.

Explicitly isolates legacy V2 fingerprint reproduction semantics.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
import hashlib
from typing import Dict, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.provenance import (
    CONTENT_FINGERPRINT_PREFIX_V2,
    FORBIDDEN_CHARACTERS,
    ProvenanceError,
    canonicalize_decimal,
)


@dataclass(frozen=True, slots=True)
class LegacyRecordAdjustmentMetadata:
    """
    Preserves historical corporate action adjustment metadata and legacy volume representations
    for a single price bar record.
    """
    cumulative_multiplier: Optional[Decimal] = None
    split_ratio: Optional[Decimal] = None
    legacy_volume_decimal: Optional[Decimal] = None
    prev_close: Optional[Decimal] = None
    prev_close_multiplier: Optional[Decimal] = None
    raw_prev_close: Optional[Decimal] = None
    adjustment_version: Optional[str] = None


@dataclass(frozen=True, slots=True)
class LegacyDatasetAdjustmentMetadata:
    """
    Preserves historical dataset-level adjustment metadata across instruments and benchmark.
    """
    adjustments_by_inst_date: Mapping[Tuple[str, datetime.date], LegacyRecordAdjustmentMetadata]
    benchmark_adjustments_by_date: Mapping[datetime.date, LegacyRecordAdjustmentMetadata]


def compute_legacy_dataset_content_fingerprint(
    trading_dates: Sequence[datetime.date],
    prices_by_instrument: Mapping[str, Sequence[PriceBar]],
    benchmark_prices: Optional[Sequence[PriceBar]] = None,
    legacy_adjustments: Optional[LegacyDatasetAdjustmentMetadata] = None,
) -> str:
    """
    Computes the canonical DATA-CTNT-V2 content fingerprint from clean PriceBar objects
    combined with separately preserved LegacyDatasetAdjustmentMetadata.

    Matches the exact legacy Signal Atlas V2 fingerprinting algorithm:
    1. Calendar: 'CALENDAR:<date>;<date>;...\\n'
    2. Instruments: 'INST:<id>\\n' followed by:
       '<date>,<open>,<high>,<low>,<close>,<volume>,<tv>,<c_mult>,<s_ratio>\\n'
       where:
       - open, high, low, close are exact Decimal string representations.
       - volume uses legacy_volume_decimal if present, else PriceBar.volume.
       - tv (traded_value) is exact Decimal string or 'NONE'.
       - c_mult is exact Decimal string or 'NONE'.
       - s_ratio is exact Decimal string or 'NONE'.
    3. Benchmark: 'BENCHMARK:\\n' followed by:
       '<date>,<open>,<high>,<low>,<close>,<volume>,<tv>\\n'
    4. SHA-256 over canonical UTF-8 bytes truncated to first 32 hex chars with prefix 'DATA-CTNT-V2-'.
    """
    if not trading_dates:
        raise ProvenanceError("Cannot compute content fingerprint for empty trading_dates.")

    hasher = hashlib.sha256()

    # 1. Trading Dates Calendar
    hasher.update(b"CALENDAR:")
    seen_calendar_dates = set()
    for dt in sorted(trading_dates):
        if type(dt) is not datetime.date:
            raise ProvenanceError(f"Calendar date must be genuine datetime.date, got {type(dt).__name__}.")
        if dt in seen_calendar_dates:
            raise ProvenanceError(f"Duplicate calendar date: {dt}")
        seen_calendar_dates.add(dt)
        hasher.update(dt.isoformat().encode("utf-8"))
        hasher.update(b";")
    hasher.update(b"\n")

    # 2. Per-instrument Price Panels
    adj_map = legacy_adjustments.adjustments_by_inst_date if legacy_adjustments else {}
    for inst_id in sorted(prices_by_instrument.keys()):
        if not isinstance(inst_id, str) or not inst_id or inst_id != inst_id.strip():
            raise ProvenanceError(f"Invalid instrument_id: '{inst_id}'")
        if any(c in inst_id for c in FORBIDDEN_CHARACTERS):
            raise ProvenanceError(f"Instrument id '{inst_id}' contains forbidden characters.")

        hasher.update(b"INST:")
        hasher.update(inst_id.encode("utf-8"))
        hasher.update(b"\n")

        bars = prices_by_instrument[inst_id]
        seen_dates = set()
        for b in sorted(bars, key=lambda x: x.trade_date):
            if type(b.trade_date) is not datetime.date:
                raise ProvenanceError(f"Trade date must be genuine datetime.date, got {type(b.trade_date).__name__}.")
            if b.trade_date in seen_dates:
                raise ProvenanceError(f"Duplicate trade date {b.trade_date} for instrument {inst_id}.")
            seen_dates.add(b.trade_date)

            adj = adj_map.get((inst_id, b.trade_date))
            if adj and adj.legacy_volume_decimal is not None:
                vol_str = canonicalize_decimal(adj.legacy_volume_decimal)
            else:
                vol_str = str(b.volume)

            c_mult_str = canonicalize_decimal(adj.cumulative_multiplier) if adj and adj.cumulative_multiplier is not None else "NONE"
            s_ratio_str = canonicalize_decimal(adj.split_ratio) if adj and adj.split_ratio is not None else "NONE"
            tv_str = canonicalize_decimal(b.traded_value)

            row_str = (
                f"{b.trade_date.isoformat()},"
                f"{canonicalize_decimal(b.open)},"
                f"{canonicalize_decimal(b.high)},"
                f"{canonicalize_decimal(b.low)},"
                f"{canonicalize_decimal(b.close)},"
                f"{vol_str},"
                f"{tv_str},"
                f"{c_mult_str},"
                f"{s_ratio_str}\n"
            )
            hasher.update(row_str.encode("utf-8"))

    # 3. Benchmark Series
    hasher.update(b"BENCHMARK:\n")
    if benchmark_prices:
        bench_adj_map = legacy_adjustments.benchmark_adjustments_by_date if legacy_adjustments else {}
        seen_bench_dates = set()
        for b in sorted(benchmark_prices, key=lambda x: x.trade_date):
            if type(b.trade_date) is not datetime.date:
                raise ProvenanceError(f"Benchmark trade date must be genuine datetime.date, got {type(b.trade_date).__name__}.")
            if b.trade_date in seen_bench_dates:
                raise ProvenanceError(f"Duplicate benchmark trade date {b.trade_date}.")
            seen_bench_dates.add(b.trade_date)

            b_adj = bench_adj_map.get(b.trade_date)
            if b_adj and b_adj.legacy_volume_decimal is not None:
                b_vol_str = canonicalize_decimal(b_adj.legacy_volume_decimal)
            else:
                b_vol_str = str(b.volume)

            b_tv_str = canonicalize_decimal(b.traded_value)
            b_row_str = (
                f"{b.trade_date.isoformat()},"
                f"{canonicalize_decimal(b.open)},"
                f"{canonicalize_decimal(b.high)},"
                f"{canonicalize_decimal(b.low)},"
                f"{canonicalize_decimal(b.close)},"
                f"{b_vol_str},"
                f"{b_tv_str}\n"
            )
            hasher.update(b_row_str.encode("utf-8"))

    return f"{CONTENT_FINGERPRINT_PREFIX_V2}{hasher.hexdigest()[:32]}"

