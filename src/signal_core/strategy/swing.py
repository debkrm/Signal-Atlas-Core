"""
Delivery Swing Trading Strategy and Execution Harness for Indian Cash Equities.

Enforces:
- Rule 1 & 2: Minimum complexity, explicit parameter definitions.
- Rule 5.1 & 13.1: Strict NSE EQ rolling cash delivery scope (zero intraday, zero F&O, zero BE/BZ entry).
- Rule 7.1: Zero lookahead next-session execution (signals formulated at T close execute at T+1 open).
- Rule 7.4 & 13.5: Single authoritative execution path: strategy intents are wired via
  execute_swing_strategy_session into ATR R-multiple sizing and DailyTPlus1OrderRunner,
  executing strictly via ExecutionFillSimulator and Portfolio ledger (Findings N-89, §60.6 Item 8).
- Phase 3B-2a & 3B-2b integration (Audit §59.7 Item 8, §60.6 Item 8).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union, TYPE_CHECKING

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import APPROVED_EQ_ONLY_POLICY, ExchangeSeries, ExchangeSessionObservation
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.types import OrderProduct, OrderSide, OrderType
from signal_core.strategy.base import OrderIntent, Strategy

if TYPE_CHECKING:
    from signal_core.execution.order_runner import (
        DailyExecutionTicket,
        DailySignalCandidate,
        DailyTPlus1OrderRunner,
    )


class DeliverySwingTrendStrategy(Strategy):
    """
    Reference Delivery Swing Trend Following Strategy on NSE EQ cash equities.

    Generates:
    - BUY intents at session T close when close > moving average and technical trend filters confirm.
    - SELL intents at session T close when close drops below trailing stop / exit moving average.
    - Strictly targets session T+1 open (next-session execution, Rule 7.1).
    - Exposes immutable parameters for canonical trial registry registration prior to metric reading.
    - Wired into execution via execute_swing_strategy_session (Finding N-89).
    """

    def __init__(
        self,
        strategy_id: str = "SWING-TREND-EQ-V1",
        fast_indicator: str = "sma_20",
        slow_indicator: str = "sma_50",
        allocation_weight: Optional[Decimal] = None,
        atr_stop_multiple: Decimal = Decimal("2.0"),
    ) -> None:
        self._strategy_id = strategy_id
        self._fast_indicator = fast_indicator
        self._slow_indicator = slow_indicator
        self._atr_stop_multiple = atr_stop_multiple

        if allocation_weight is not None:
            self._allocation_weight = allocation_weight
        else:
            criteria = load_go_no_go_criteria()
            self._allocation_weight = criteria.max_single_position_weight * Decimal("0.80")

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Canonical dictionary of strategy parameters for TrialRegistry recording."""
        return {
            "strategy_id": self._strategy_id,
            "fast_indicator": self._fast_indicator,
            "slow_indicator": self._slow_indicator,
            "allocation_weight": str(self._allocation_weight),
            "atr_stop_multiple": str(self._atr_stop_multiple),
            "policy": "APPROVED_EQ_ONLY_POLICY",
        }

    def generate_signals(
        self,
        as_of: datetime.date,
        next_session: datetime.date,
        universe: Sequence[str],
        features: Mapping[str, Any],
    ) -> Tuple[OrderIntent, ...]:
        """
        Formulates trade intents at session as_of (T close) for execution at next_session (T+1).
        Respects APPROVED_EQ_ONLY_POLICY: only generates intents for instruments present in universe.
        """
        intents: list[OrderIntent] = []

        for isin in sorted(universe):
            inst_features = features.get(isin)
            if inst_features is None:
                continue

            fast_val = getattr(inst_features, self._fast_indicator, None)
            slow_val = getattr(inst_features, self._slow_indicator, None)
            close = getattr(inst_features, "close", None)

            if fast_val is None or slow_val is None or close is None:
                continue

            if close > fast_val and fast_val > slow_val:
                intents.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"SWING_BUY_{isin}_{as_of.isoformat()}",
                    )
                )
            elif close < slow_val:
                intents.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"SWING_SELL_{isin}_{as_of.isoformat()}",
                    )
                )

        return tuple(intents)


def execute_swing_strategy_session(
    strategy: DeliverySwingTrendStrategy,
    runner: DailyTPlus1OrderRunner,
    as_of: datetime.date,
    next_session: datetime.date,
    universe: Sequence[str],
    features: Mapping[str, Any],
    bars_next_session: Mapping[str, Union[PriceBar, ExchangeSessionObservation]],
    price_bands_next_session: Mapping[str, PriceBandRecord],
    explicit_series: Optional[ExchangeSeries] = ExchangeSeries.EQ,
    latest_market_prices: Optional[Mapping[str, Decimal]] = None,
) -> Tuple[DailyExecutionTicket, ...]:
    """
    Authoritative execution harness that routes DeliverySwingTrendStrategy signals through
    ATR R-multiple sizing into DailyTPlus1OrderRunner (Finding N-89, §60.6 Item 8).

    Enforces:
    - Zero Lookahead: signal date as_of -> next_session execution (Rule 7.1).
    - Cash delivery swing scope: only held positions can emit SELL intents; naked shorting prohibited.
    - BUY intents are sized with positive integer quantities through ATR R-multiple sizing.
    - Fills and ledger updates flow strictly through the single authoritative
      ExecutionFillSimulator and Portfolio ledger (Rule 7.4 & 13.5).
    """
    from signal_core.execution.order_runner import DailySignalCandidate

    raw_intents = strategy.generate_signals(
        as_of=as_of,
        next_session=next_session,
        universe=universe,
        features=features,
    )

    tickets: List[DailyExecutionTicket] = []

    for intent in raw_intents:
        isin = intent.instrument_id
        pos = runner.portfolio.get_position(isin)

        # Cash delivery constraint: SELL intent is only permitted if position is currently held
        if intent.side == OrderSide.SELL:
            if pos is None or pos.is_closed or pos.quantity <= 0:
                continue

        # Avoid redundant BUY if already holding an open position in this security
        if intent.side == OrderSide.BUY:
            if pos is not None and not pos.is_closed and pos.quantity > 0:
                continue

        inst_features = features.get(isin)
        if inst_features is None:
            continue

        close_val = getattr(inst_features, "close", None)
        atr_val = getattr(inst_features, "atr", None)
        vol_val = getattr(inst_features, "volume", None)

        if close_val is None:
            continue
        entry_price = Decimal(str(close_val))
        atr_dec = Decimal(str(atr_val)) if atr_val is not None else (entry_price * Decimal("0.02"))
        vol_int = int(vol_val) if vol_val is not None else 1000000

        cand = DailySignalCandidate(
            instrument_id=isin,
            signal_date=as_of,
            side=intent.side,
            entry_reference_price=entry_price,
            atr=atr_dec,
            session_volume=vol_int,
            series="EQ",
            metadata={"intent_id": intent.intent_id},
        )

        t_plus_1_bar = bars_next_session.get(isin)
        price_band = price_bands_next_session.get(isin)

        if t_plus_1_bar is None or price_band is None:
            continue

        ticket = runner.run_candidate(
            candidate=cand,
            t_plus_1_bar=t_plus_1_bar,
            target_date=next_session,
            price_band=price_band,
            explicit_series=explicit_series,
            latest_market_prices=latest_market_prices,
        )
        tickets.append(ticket)

    return tuple(tickets)
