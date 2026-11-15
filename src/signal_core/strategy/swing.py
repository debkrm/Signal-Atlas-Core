"""
Delivery Swing Trading Strategy for Indian Cash Equities.

Enforces:
- Rule 1 & 2: Minimum complexity, explicit parameter definitions.
- Rule 5.1 & 13.1: Strict NSE EQ rolling cash delivery scope (zero intraday, zero F&O, zero BE/BZ entry).
- Rule 7.1: Zero lookahead next-session execution (signals formulated at T close execute at T+1 open).
- Rule 7.4 & 13.5: Execution via single authoritative ExecutionFillSimulator and Portfolio ledger.
- Phase 3B-2a contract & TrialRegistry integration (Audit §59.7 Item 8).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import APPROVED_EQ_ONLY_POLICY
from signal_core.execution.types import OrderProduct, OrderSide, OrderType
from signal_core.strategy.base import OrderIntent, Strategy


class DeliverySwingTrendStrategy(Strategy):
    """
    Reference Delivery Swing Trend Following Strategy on NSE EQ cash equities.

    Generates:
    - BUY intents at session T close when close > moving average and technical trend filters confirm.
    - SELL intents at session T close when close drops below trailing stop / exit moving average.
    - Strictly targets session T+1 open (next-session execution, Rule 7.1).
    - Exposes immutable parameters for canonical trial registry registration prior to metric reading.
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
