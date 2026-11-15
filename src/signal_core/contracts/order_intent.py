"""Order Intent Contracts for Algorithmic Trade Formulation.

Defines immutable specifications for trading decisions formulated at session T close
to be executed at session T+1 or later, decoupled from strategy implementations
to eliminate circular dependencies per AGENTS.md §7.1, §7.4, §13.5 and Audit §61.6 Item 2 (Finding H-90).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from signal_core.contracts.order_types import (
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

    @classmethod
    def from_position_size_result(
        cls,
        instrument_id: str,
        signal_date: datetime.date,
        target_date: datetime.date,
        side: OrderSide,
        size_result: Any,
        order_type: OrderType = OrderType.MARKET_ON_OPEN,
        product: OrderProduct = OrderProduct.DELIVERY,
        allow_partial_fill: bool = False,
        intent_id: Optional[str] = None,
        additional_metadata: Optional[Mapping[str, Any]] = None,
    ) -> "OrderIntent":
        """
        Constructs an OrderIntent from an ATR R-multiple PositionSizeResult (Phase 3B-1).
        Populates quantity from size_result.quantity, stop_price from size_result.stop_loss_price,
        and includes position_weight, risk_amount, stop_distance, and binding_constraint in metadata.
        """
        if hasattr(size_result, "quantity"):
            qty = size_result.quantity
            stop = getattr(size_result, "stop_loss_price", None)
            weight = getattr(size_result, "position_weight", None)
            risk = getattr(size_result, "risk_amount", None)
            dist = getattr(size_result, "stop_distance", None)
            binding = getattr(size_result, "binding_constraint", None)
            entry_p = getattr(size_result, "entry_price", None)
            atr_val = getattr(size_result, "atr", None)
        elif isinstance(size_result, dict):
            qty = size_result["quantity"]
            stop = size_result.get("stop_loss_price")
            weight = size_result.get("position_weight")
            risk = size_result.get("risk_amount")
            dist = size_result.get("stop_distance")
            binding = size_result.get("binding_constraint")
            entry_p = size_result.get("entry_price")
            atr_val = size_result.get("atr")
        else:
            raise OrderIntentValidationError(
                f"size_result must be a PositionSizeResult or mapping, got {type(size_result).__name__}"
            )

        meta: dict[str, Any] = {
            "position_weight": weight,
            "risk_amount": risk,
            "stop_distance": dist,
            "binding_constraint": binding,
            "entry_reference_price": entry_p,
            "atr": atr_val,
        }
        if additional_metadata:
            meta.update(additional_metadata)

        return cls(
            instrument_id=instrument_id,
            signal_date=signal_date,
            target_date=target_date,
            side=side,
            order_type=order_type,
            product=product,
            quantity=qty,
            target_weight=weight if qty is None else None,
            stop_price=stop,
            allow_partial_fill=allow_partial_fill,
            intent_id=intent_id,
            metadata=meta,
        )
