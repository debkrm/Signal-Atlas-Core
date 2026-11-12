"""
Gold Layer: Derived Analytics, Forward Corporate Adjustments, and Point-in-Time Universe Schedules.

Implements derived data generation per AGENTS.md Rule 10.3 and Rule 6.3:
- Raw -> Typed/Validated (Silver) -> Derived (Gold).
- Corporate action adjustments applied in Gold only, never in Silver or Bronze.
- Point-in-time universe schedules generated strictly as-of date T with zero survivorship bias.
- Merged/delisted scrips and transitioned ISINs pruned on exact effective dates (Gate G2B.5-3).
- Deterministic cryptographic fingerprinting (DATA-CTNT-V2, UNIV-SCHED-V1) reproduced on rerun (Gate G2B.5-2).
- Fail-closed snapshot generation: Refuses to emit a fingerprint over non-contiguous or gapped datasets (E-3).
- Volume adjustment preservation: Splits adjust share volume inversely to preserve turnover representation (E-12).
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from signal_core.contracts.dataset import DatasetSnapshot, PriceConvention
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.provenance import (
    compute_dataset_content_fingerprint,
    compute_universe_schedule_fingerprint,
)
from signal_core.contracts.universe import UniverseSchedule
from signal_core.storage.calendar import TradingCalendar
from signal_core.storage.security_master import CorporateAction, CorporateActionType, SecurityMaster
from signal_core.storage.silver import SilverStorage


class GoldEngineError(ValueError):
    """Base exception for gold layer engine failures."""
    pass


class NonContiguousDatasetError(GoldEngineError):
    """Raised when an attempt is made to fingerprint or build a snapshot over a gapped series (E-3)."""
    pass


class GoldEngine:
    """
    Engine for generating derived datasets, universe schedules, and content fingerprints
    from immutable Silver partitions and Security Master facts.
    """
    def __init__(
        self,
        silver_storage: SilverStorage,
        calendar: TradingCalendar,
        security_master: SecurityMaster,
    ) -> None:
        self._silver = silver_storage
        self._calendar = calendar
        self._sec_master = security_master

    @property
    def silver_storage(self) -> SilverStorage:
        return self._silver

    @property
    def calendar(self) -> TradingCalendar:
        return self._calendar

    @property
    def security_master(self) -> SecurityMaster:
        return self._sec_master

    def build_point_in_time_universe_schedule(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        series_filter: Optional[str] = "EQ",
    ) -> UniverseSchedule:
        """
        Builds point-in-time UniverseSchedule mapping each trading session to active ISINs.
        Prunes delisted scrips and old transitioned ISINs on their exact effective dates (Gate G2B.5-3).
        """
        sessions = self._calendar.sessions_in_range(start_date, end_date)
        if not sessions:
            raise GoldEngineError(f"No trading sessions found in calendar between {start_date} and {end_date}")

        daily_membership: Dict[datetime.date, Tuple[str, ...]] = {}

        for s in sessions:
            # Point-in-time active ISINs on date s
            active_isins = self._sec_master.active_isins_on(s)
            eligible_isins: List[str] = []

            for isin in active_isins:
                sym_interval = self._sec_master.resolve_symbol(isin, s)
                if sym_interval is None:
                    continue
                if series_filter is not None and sym_interval.series != series_filter:
                    continue
                eligible_isins.append(isin)

            # Sort lexicographically for deterministic universe schedule
            daily_membership[s] = tuple(sorted(eligible_isins))

        return UniverseSchedule(daily_membership)

    def compute_universe_schedule_fingerprint(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        series_filter: Optional[str] = "EQ",
    ) -> str:
        """Computes deterministic UNIV-SCHED-V1 fingerprint for universe schedule."""
        schedule = self.build_point_in_time_universe_schedule(start_date, end_date, series_filter=series_filter)
        return compute_universe_schedule_fingerprint(schedule)

    def load_price_panel(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        isins: Optional[Sequence[str]] = None,
        fail_closed_on_missing: bool = True,
    ) -> Mapping[str, Sequence[PriceBar]]:
        """
        Loads unadjusted PriceBar sequences for specified instruments (or all registered instruments)
        across trading sessions in [start_date, end_date].
        Fails closed with NonContiguousDatasetError if any active session is missing from storage (E-3).
        """
        sessions = self._calendar.sessions_in_range(start_date, end_date)
        target_isins = tuple(isins) if isins is not None else self._sec_master.registered_isins

        prices_by_inst: Dict[str, List[PriceBar]] = {isin: [] for isin in target_isins}

        for s in sessions:
            if not self._silver.partition_exists(s):
                if fail_closed_on_missing:
                    raise NonContiguousDatasetError(
                        f"Cannot load contiguous price panel: missing required silver partition for calendar session {s}"
                    )
                continue

            records = self._silver.read_daily_partition(s)
            records_by_isin = {r.isin: r for r in records}

            for isin in target_isins:
                # Check if instrument is active on date s
                if not self._sec_master.is_active(isin, s):
                    continue

                if isin in records_by_isin:
                    prices_by_inst[isin].append(records_by_isin[isin].to_price_bar())
                elif fail_closed_on_missing:
                    raise NonContiguousDatasetError(
                        f"Active instrument {isin} has unexplained missing record on session {s}"
                    )

        # Enforce that instruments active during the range are not silently dropped with 'if v' (E-3)
        result: Dict[str, Tuple[PriceBar, ...]] = {}
        for isin, bars in prices_by_inst.items():
            if bars:
                result[isin] = tuple(bars)
            elif fail_closed_on_missing:
                # Check if instrument was active on any calendar session in [start_date, end_date]
                active_days = [s for s in sessions if self._sec_master.is_active(isin, s)]
                if active_days:
                    raise NonContiguousDatasetError(
                        f"Active instrument {isin} has 0 records across {len(active_days)} active calendar sessions."
                    )

        return result

    def build_dataset_snapshot(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        price_convention: PriceConvention = PriceConvention.UNADJUSTED_RAW,
        dataset_id: str = "NSE-CASH-EQUITY-GOLD",
        isins: Optional[Sequence[str]] = None,
        fail_closed_on_missing: bool = True,
    ) -> Tuple[DatasetSnapshot, Mapping[str, Sequence[PriceBar]]]:
        """
        Produces an immutable DatasetSnapshot descriptor and price panel.
        Fails closed by default if any session is missing: never mints a fingerprint over a gapped series (E-3).
        Computes deterministic DATA-CTNT-V2 content fingerprint and UNIV-SCHED-V1 universe fingerprint.
        Guarantees bit-for-bit reproducibility across runs (Gate G2B.5-2).
        """
        sessions = self._calendar.sessions_in_range(start_date, end_date)
        # Fail closed on missing sessions by default (E-3)
        raw_prices = self.load_price_panel(
            start_date, end_date, isins=isins, fail_closed_on_missing=fail_closed_on_missing
        )

        # Build universe schedule and fingerprint
        universe_sched = self.build_point_in_time_universe_schedule(start_date, end_date)
        univ_fpr = compute_universe_schedule_fingerprint(universe_sched)

        # Corporate action adjustments
        multipliers_by_inst_date: Dict[Tuple[str, datetime.date], Tuple[Decimal, Decimal]] = {}
        processed_prices: Dict[str, List[PriceBar]] = {}

        if price_convention == PriceConvention.SPLIT_BONUS_ADJUSTED:
            for isin, bars in raw_prices.items():
                corp_actions = self._sec_master.get_corporate_actions(isin)
                adj_bars: List[PriceBar] = []
                for b in bars:
                    # Compute cumulative adjustment factor from all corporate actions with ex_date > trade_date
                    cum_numerator = Decimal("1")
                    cum_denominator = Decimal("1")
                    split_factor = Decimal("1.0")

                    for ca in corp_actions:
                        if ca.ex_date > b.trade_date:
                            cum_numerator *= ca.ratio_numerator
                            cum_denominator *= ca.ratio_denominator
                            if ca.action_type in (CorporateActionType.SPLIT, CorporateActionType.ISIN_TRANSITION):
                                split_factor *= ca.adjustment_factor

                    cum_price_multiplier = cum_denominator / cum_numerator
                    multipliers_by_inst_date[(isin, b.trade_date)] = (cum_price_multiplier, split_factor)

                    # Inversely adjust volume to preserve turnover representation (E-12)
                    adj_volume = (b.volume * int(cum_numerator)) // int(cum_denominator)

                    adj_bar = PriceBar(
                        instrument_id=isin,
                        trade_date=b.trade_date,
                        open=b.open * cum_price_multiplier,
                        high=b.high * cum_price_multiplier,
                        low=b.low * cum_price_multiplier,
                        close=b.close * cum_price_multiplier,
                        volume=adj_volume,
                        traded_value=b.traded_value,
                        currency=b.currency,
                    )
                    adj_bars.append(adj_bar)
                processed_prices[isin] = adj_bars
        else:
            processed_prices = {k: list(v) for k, v in raw_prices.items()}

        final_prices: Dict[str, Tuple[PriceBar, ...]] = {k: tuple(v) for k, v in processed_prices.items()}

        # Content fingerprint (DATA-CTNT-V2)
        content_fpr = compute_dataset_content_fingerprint(
            trading_dates=sessions,
            prices_by_instrument=final_prices,
            corporate_multiplier_by_inst_date=multipliers_by_inst_date if multipliers_by_inst_date else None,
        )

        total_price_records = sum(len(bars) for bars in final_prices.values())
        inst_count = len(final_prices)

        snapshot = DatasetSnapshot(
            dataset_id=dataset_id,
            schema_version="v1.0",
            price_convention=price_convention,
            start_date=start_date,
            end_date=end_date,
            session_count=len(sessions),
            instrument_count=inst_count,
            total_price_records=total_price_records,
            total_instrument_records=total_price_records,
            source_identity="NSE_OFFICIAL_BHAVCOPY_SILVER_LAYER",
            content_fingerprint=content_fpr,
            universe_fingerprint=univ_fpr,
        )

        return snapshot, final_prices
