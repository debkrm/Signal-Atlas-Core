"""
Strategy Contract and Order Intent Specifications for Signal Atlas.

Implements strategy invariants per AGENTS.md Rule 1, 2, 5, 6, 7.1, 7.4, and Phase 2C:
- Strict next-session intent invariant: signal_date (session T close) -> target_date (session T+1 open).
- Same-session execution (T close -> T fill) is strictly rejected fail-closed (Gate G2C-2).
- Zero lookahead: strategies only access features and price data observable up to as_of session.
- Single authoritative execution path: OrderIntents convert to ExecutionOrders for ExecutionFillSimulator.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence, Tuple

from signal_core.execution.types import (
    ExecutionOrder,
    ExecutionOrderValidationError,
    OrderProduct,
    OrderSide,
    OrderType,
)


class OrderIntentValidationError(ValueError):
    """Raised when an OrderIntent violates structural or domain invariants."""
    pass


class LookaheadIntentError(OrderIntentValidationError):
    """Raised when an OrderIntent attempts same-session or backward-dated execution (Gate G2C-2)."""
    pass


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """
    Immutable specification of an algorithmic trading decision formulated at session T close.
    
    Invariants:
    - signal_date: date when the decision was calculated (session T close).
    - target_date: intended execution session (session T+1 or later).
    - target_date MUST be strictly greater than signal_date (zero lookahead / no same-session fill).
    - instrument_id: clean ISIN string.
    - Exactly one of quantity or target_weight must be specified.
    """
    instrument_id: str
    signal_date: datetime.date
    target_date: datetime.date
    side: OrderSide
    order_type: OrderType = OrderType.MARKET_ON_OPEN
    product: OrderProduct = OrderProduct.DELIVERY
    quantity: Optional[int] = None
    target_weight: Optional[Decimal] = None
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    allow_partial_fill: bool = False
    intent_id: Optional[str] = None
    metadata: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.instrument_id, bool)
            or not isinstance(self.instrument_id, str)
            or not self.instrument_id.strip()
            or self.instrument_id != self.instrument_id.strip()
        ):
            raise OrderIntentValidationError(
                f"instrument_id must be a clean non-empty string, got {self.instrument_id!r}"
            )

        if type(self.signal_date) is not datetime.date:
            raise OrderIntentValidationError(
                f"signal_date must be genuine datetime.date, got {type(self.signal_date).__name__}"
            )

        if type(self.target_date) is not datetime.date:
            raise OrderIntentValidationError(
                f"target_date must be genuine datetime.date, got {type(self.target_date).__name__}"
            )

        # Gate G2C-2 Invariant: Next-session execution strictly enforced
        if self.target_date <= self.signal_date:
            raise LookaheadIntentError(
                f"Lookahead violation (Gate G2C-2): target_date ({self.target_date}) must be strictly after "
                f"signal_date ({self.signal_date}). Same-session execution (T close -> T fill) is prohibited."
            )

        if not isinstance(self.side, OrderSide):
            raise OrderIntentValidationError(f"side must be an OrderSide enum, got {type(self.side)}")

        if not isinstance(self.order_type, OrderType):
            raise OrderIntentValidationError(f"order_type must be an OrderType enum, got {type(self.order_type)}")

        if not isinstance(self.product, OrderProduct):
            raise OrderIntentValidationError(f"product must be an OrderProduct enum, got {type(self.product)}")

        # Sizing validation: exactly one of quantity or target_weight must be provided
        has_qty = self.quantity is not None
        has_weight = self.target_weight is not None

        if not has_qty and not has_weight:
            raise OrderIntentValidationError(
                f"OrderIntent for {self.instrument_id} must specify either quantity or target_weight."
            )
        if has_qty and has_weight:
            raise OrderIntentValidationError(
                f"OrderIntent for {self.instrument_id} cannot specify both quantity and target_weight."
            )

        if has_qty:
            if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
                raise OrderIntentValidationError(
                    f"quantity must be a positive integer, got {self.quantity!r}"
                )

        if has_weight:
            if (
                isinstance(self.target_weight, bool)
                or not isinstance(self.target_weight, Decimal)
                or not self.target_weight.is_finite()
                or self.target_weight <= Decimal("0")
                or self.target_weight > Decimal("1.0")
            ):
                raise OrderIntentValidationError(
                    f"target_weight must be a finite Decimal in (0, 1.0], got {self.target_weight!r}"
                )

        if self.order_type == OrderType.LIMIT:
            if (
                self.limit_price is None
                or isinstance(self.limit_price, bool)
                or not isinstance(self.limit_price, Decimal)
                or not self.limit_price.is_finite()
                or self.limit_price <= Decimal("0")
            ):
                raise OrderIntentValidationError(
                    f"LIMIT order requires positive finite Decimal limit_price, got {self.limit_price!r}"
                )

        if self.order_type == OrderType.STOP_LOSS:
            if (
                self.stop_price is None
                or isinstance(self.stop_price, bool)
                or not isinstance(self.stop_price, Decimal)
                or not self.stop_price.is_finite()
                or self.stop_price <= Decimal("0")
            ):
                raise OrderIntentValidationError(
                    f"STOP_LOSS order requires positive finite Decimal stop_price, got {self.stop_price!r}"
                )

        if self.intent_id is not None:
            if (
                isinstance(self.intent_id, bool)
                or not isinstance(self.intent_id, str)
                or not self.intent_id.strip()
                or self.intent_id != self.intent_id.strip()
            ):
                raise OrderIntentValidationError(
                    f"intent_id must be a clean non-empty string, got {self.intent_id!r}"
                )

    def to_execution_order(
        self,
        computed_quantity: Optional[int] = None,
        order_id: Optional[str] = None,
    ) -> ExecutionOrder:
        """
        Converts OrderIntent into an authoritative ExecutionOrder for ExecutionFillSimulator.
        If intent has target_weight, computed_quantity must be provided.
        """
        effective_qty = computed_quantity if computed_quantity is not None else self.quantity
        if effective_qty is None or effective_qty <= 0:
            raise OrderIntentValidationError(
                f"Cannot create ExecutionOrder: valid positive quantity required (got {effective_qty!r})"
            )

        resolved_id = order_id or self.intent_id or f"ORD_{self.instrument_id}_{self.target_date.isoformat()}"

        return ExecutionOrder(
            instrument_id=self.instrument_id,
            side=self.side,
            product=self.product,
            quantity=effective_qty,
            signal_date=self.signal_date,
            target_date=self.target_date,
            order_type=self.order_type,
            limit_price=self.limit_price,
            stop_price=self.stop_price,
            allow_partial_fill=self.allow_partial_fill,
            order_id=resolved_id,
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
        allocation_weight: Decimal = Decimal("0.20"),
    ) -> None:
        self._strategy_id = strategy_id
        self._fast_indicator = fast_indicator
        self._slow_indicator = slow_indicator
        self._allocation_weight = allocation_weight

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
