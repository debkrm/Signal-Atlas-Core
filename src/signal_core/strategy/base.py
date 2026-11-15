"""Strategy Contract and Order Intent Specifications for Signal Atlas.

Implements strategy invariants per AGENTS.md Rule 1, 2, 5, 6, 7.1, 7.4, and Phase 2C:
- Strict next-session intent invariant: signal_date (session T close) -> target_date (session T+1 open).
- Same-session execution (T close -> T fill) is strictly rejected fail-closed (Gate G2C-2).
- Zero lookahead: strategies only access features and price data observable up to as_of session.
- Single authoritative execution path: OrderIntents convert to ExecutionOrders for ExecutionFillSimulator.
"""

from abc import ABC, abstractmethod
import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence, Tuple

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.order_intent import (
    LookaheadIntentError,
    OrderIntent,
    OrderIntentValidationError,
)
from signal_core.execution.types import (
    ExecutionOrder,
    ExecutionOrderValidationError,
    OrderProduct,
    OrderSide,
    OrderType,
)


class Strategy(ABC):
    """
    Abstract Base Class for quantitative trading strategies.
    
    Guarantees:
    - Pure point-in-time calculation at as_of date: only data up to as_of is accessible.
    - Emits OrderIntent tuples targeting next session (as_of + latency) or later.
    - Parameters are inspectable for trial registry canonicalization.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy name or identifier."""
        pass

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Canonical dictionary of strategy parameters for trial registry recording."""
        return {}

    def fit(
        self,
        train_start: datetime.date,
        train_end: datetime.date,
        universe: Sequence[str],
        features_by_instrument: Mapping[str, Any],
    ) -> None:
        """
        Optional model training / parameter fitting step on walk-forward training partition.
        Default implementation is stateless (rule-based).
        """
        pass

    @abstractmethod
    def generate_signals(
        self,
        as_of: datetime.date,
        next_session: datetime.date,
        universe: Sequence[str],
        features: Mapping[str, Any],
    ) -> Tuple[OrderIntent, ...]:
        """
        Formulates trade intents at session as_of (T close) for execution at next_session (T+1).
        
        Args:
            as_of: Current session date T. Only historical data up to T is reachable.
            next_session: The official exchange session immediately following as_of (T+1).
            universe: Point-in-time active eligible universe constituents on as_of.
            features: Point-in-time technical features / price history up to as_of.
            
        Returns:
            Tuple of OrderIntent instances with signal_date=as_of and target_date=next_session.
        """
        pass


class TechnicalCrossStrategy(Strategy):
    """
    Reference Technical Moving Average / Price Trend Cross Strategy.
    
    Generates:
    - BUY when close > fast_indicator (e.g. sma_20 or rolling high) and no position is open.
    - SELL when close < slow_indicator (e.g. sma_50 or trailing stop).
    """

    def __init__(
        self,
        strategy_id: str = "TECH-CROSS-V1",
        fast_indicator: str = "sma_20",
        slow_indicator: str = "sma_50",
        allocation_weight: Optional[Decimal] = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._fast_indicator = fast_indicator
        self._slow_indicator = slow_indicator
        if allocation_weight is not None:
            self._allocation_weight = allocation_weight
        else:
            # Audit §31 H-32: Derive sizing default from committed criteria (80% of max_single_position_weight)
            # avoids hardcoded literal drift against criteria
            criteria = load_go_no_go_criteria()
            self._allocation_weight = criteria.max_single_position_weight * Decimal("0.80")

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "strategy_id": self._strategy_id,
            "fast_indicator": self._fast_indicator,
            "slow_indicator": self._slow_indicator,
            "allocation_weight": str(self._allocation_weight),
        }

    def generate_signals(
        self,
        as_of: datetime.date,
        next_session: datetime.date,
        universe: Sequence[str],
        features: Mapping[str, Any],
    ) -> Tuple[OrderIntent, ...]:
        intents: list[OrderIntent] = []

        for isin in sorted(universe):
            inst_features = features.get(isin)
            if inst_features is None:
                continue

            # Look up feature object
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
                        intent_id=f"INT_BUY_{isin}_{as_of.isoformat()}",
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
                        intent_id=f"INT_SELL_{isin}_{as_of.isoformat()}",
                    )
                )

        return tuple(intents)


__all__ = [
    "OrderIntent",
    "OrderIntentValidationError",
    "LookaheadIntentError",
    "Strategy",
    "TechnicalCrossStrategy",
]
