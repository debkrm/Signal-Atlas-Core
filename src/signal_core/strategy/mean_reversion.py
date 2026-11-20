"""Mean-Reversion Delivery Swing Strategy on NSE EQ cash equities (seq 12, pre-registered).

The rule is closed-form and pre-registered in `configs/trial_012_candidate.yaml` before this module
existed. There is one specification and no variant:

- entry signal at the close of session T: `close_T > SMA(200)_T AND RSI(2)_T < 10`, the RSI computed
  with Wilder smoothing over split/bonus-adjusted closes;
- exit signal at the close of any session T with `close_T > SMA(5)_T`;
- both fill at session T+1's open — never at the signal session's close (§7.1).

Everything downstream is the single authoritative engine (§7.4, §13.5): intents go through
`execute_swing_strategy_session`, ATR R-multiple sizing and `DailyTPlus1OrderRunner`, the protective
2.0xATR(14) stop and the 21-session hold bound are the runner's and the criteria', and the strategy
adds no fill, cost or accounting path of its own.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.execution.types import OrderProduct, OrderSide, OrderType
from signal_core.strategy.base import OrderIntent, Strategy


class MeanReversionSwingStrategy(Strategy):
    """`SWING-MEAN-REV-EQ-V1`: oversold pullback inside a long-term uptrend, exit on a 5-session mean."""

    def __init__(
        self,
        strategy_id: str = "SWING-MEAN-REV-EQ-V1",
        trend_indicator: str = "sma_200",
        entry_rsi_indicator: str = "rsi_2",
        entry_rsi_threshold: Decimal = Decimal("10"),
        exit_indicator: str = "sma_5",
        allocation_weight: Optional[Decimal] = None,
        atr_stop_multiple: Decimal = Decimal("2.0"),
    ) -> None:
        self._strategy_id = strategy_id
        self._trend_indicator = trend_indicator
        self._entry_rsi_indicator = entry_rsi_indicator
        self._entry_rsi_threshold = Decimal(entry_rsi_threshold)
        self._exit_indicator = exit_indicator
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
        return {
            "strategy_id": self._strategy_id,
            "trend_indicator": self._trend_indicator,
            "entry_rsi_indicator": self._entry_rsi_indicator,
            "entry_rsi_threshold": str(self._entry_rsi_threshold),
            "exit_indicator": self._exit_indicator,
            "allocation_weight": str(self._allocation_weight),
            "atr_stop_multiple": str(self._atr_stop_multiple),
            # Reporting honesty, not selection: this family ranks no entries, so the row must not
            # claim the committed cross-sectional rank was applied (Audit §75.10 N-137).
            "entry_rank_indicator": "NONE",
            "policy": "APPROVED_EQ_ONLY_POLICY",
        }

    def generate_signals(
        self,
        as_of: datetime.date,
        next_session: datetime.date,
        universe: Sequence[str],
        features: Mapping[str, Any],
        portfolio: Optional[Any] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> Tuple[OrderIntent, ...]:
        """
        Formulates intents at session `as_of` (T close) for execution at `next_session` (T+1 open).

        Reads only the features the caller has already computed for `as_of`, so a lookback can never
        reach beyond T (§7.1). Exits are emitted before entries: a session's exits free the capital its
        entries compete for.
        """
        exits: List[OrderIntent] = []
        entries: List[OrderIntent] = []

        for isin in sorted(universe):
            inst_features = features.get(isin)
            if inst_features is None:
                continue
            close = getattr(inst_features, "close", None)
            if close is None:
                continue

            exit_level = getattr(inst_features, self._exit_indicator, None)
            if exit_level is not None and close > exit_level:
                exits.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"MEANREV_SELL_{isin}_{as_of.isoformat()}",
                    )
                )
                continue

            trend_level = getattr(inst_features, self._trend_indicator, None)
            rsi_value = getattr(inst_features, self._entry_rsi_indicator, None)
            if trend_level is None or rsi_value is None:
                continue
            if close > trend_level and rsi_value < self._entry_rsi_threshold:
                entries.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"MEANREV_BUY_{isin}_{as_of.isoformat()}",
                    )
                )

        return tuple(exits + entries)


__all__ = ["MeanReversionSwingStrategy"]
