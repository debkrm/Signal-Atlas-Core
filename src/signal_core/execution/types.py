"""Domain Types, Enums and Order Contracts for Execution and Costs.

Defines immutable order models, execution sides, product types, and fill status codes
in strict accordance with Indian market structure (SEBI / NSE) and AGENTS.md invariants.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Tuple


class OrderSide(str, Enum):
    """Direction of trade execution."""
    BUY = "BUY"
    SELL = "SELL"


class OrderProduct(str, Enum):
    """Settlement product classification."""
    DELIVERY = "DELIVERY"  # Cash equity rolling delivery (CNC)
    INTRADAY = "INTRADAY"  # Intraday squared-off equity (MIS)


class OrderType(str, Enum):
    """Execution order type."""
    MARKET_ON_OPEN = "MARKET_ON_OPEN"  # Execute at session open (T+1 Open)
    LIMIT = "LIMIT"                    # Execute only at or better than limit price
    STOP_LOSS = "STOP_LOSS"            # Market trigger when price reaches or breaches stop level


class FillStatus(str, Enum):
    """Execution fill outcome status."""
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED_UPPER_CIRCUIT = "REJECTED_UPPER_CIRCUIT"
    REJECTED_LOWER_CIRCUIT = "REJECTED_LOWER_CIRCUIT"
    REJECTED_VOLUME_CAP = "REJECTED_VOLUME_CAP"
    REJECTED_INSUFFICIENT_TURNOVER = "REJECTED_INSUFFICIENT_TURNOVER"
    REJECTED_INELIGIBLE_SERIES = "REJECTED_INELIGIBLE_SERIES"
    REJECTED_INVALID_LATENCY = "REJECTED_INVALID_LATENCY"
    REJECTED_LOOKAHEAD = "REJECTED_LOOKAHEAD"
    REJECTED_ZERO_LIQUIDITY = "REJECTED_ZERO_LIQUIDITY"
    REJECTED_PRICE_LIMIT = "REJECTED_PRICE_LIMIT"
    REJECTED_RISK_LIMIT = "REJECTED_RISK_LIMIT"
    REJECTED_LIQUIDITY_LIMIT = "REJECTED_LIQUIDITY_LIMIT"
    UNTRIGGERED = "UNTRIGGERED"


class ExecutionOrderValidationError(ValueError):
    """Raised when an execution order violates domain or structural invariants."""
    pass


@dataclass(frozen=True, slots=True)
class ExecutionOrder:
    """
    Immutable trade order specification for execution simulation.
    
    Enforces strict next-session invariant:
    - signal_date: date when the signal was generated (using data up to T close).
    - target_date: execution session date (T+1 or later). Must be strictly > signal_date.
    """
    instrument_id: str
    side: OrderSide
    product: OrderProduct
    quantity: int
    signal_date: datetime.date
    target_date: datetime.date
    order_type: OrderType = OrderType.MARKET_ON_OPEN
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    allow_partial_fill: bool = False
    order_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ExecutionOrderValidationError(f"Invalid instrument_id: {self.instrument_id!r}")

        if self.order_id is not None:
            if (
                isinstance(self.order_id, bool)
                or not isinstance(self.order_id, str)
                or not self.order_id.strip()
                or self.order_id != self.order_id.strip()
            ):
                raise ExecutionOrderValidationError(
                    f"order_id must be a non-empty, non-whitespace string without leading/trailing whitespace, got {self.order_id!r}"
                )
        
        if not isinstance(self.side, OrderSide):
            raise ExecutionOrderValidationError(f"side must be an OrderSide enum, got {type(self.side)}")
        
        if not isinstance(self.product, OrderProduct):
            raise ExecutionOrderValidationError(f"product must be an OrderProduct enum, got {type(self.product)}")
        
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
            raise ExecutionOrderValidationError(f"quantity must be a positive integer, got {self.quantity!r}")
        
        # Date validation: exact datetime.date, no datetime subclasses
        if type(self.signal_date) is not datetime.date:
            raise ExecutionOrderValidationError(
                f"signal_date must be exact datetime.date, got {type(self.signal_date).__name__}"
            )
        if type(self.target_date) is not datetime.date:
            raise ExecutionOrderValidationError(
                f"target_date must be exact datetime.date, got {type(self.target_date).__name__}"
            )
        
        # Order type specific validations
        if self.order_type == OrderType.LIMIT:
            if self.limit_price is None or not isinstance(self.limit_price, Decimal) or not self.limit_price.is_finite() or self.limit_price <= 0:
                raise ExecutionOrderValidationError(f"Limit order requires finite positive Decimal limit_price, got {self.limit_price!r}")
        
        if self.order_type == OrderType.STOP_LOSS:
            if self.stop_price is None or not isinstance(self.stop_price, Decimal) or not self.stop_price.is_finite() or self.stop_price <= 0:
                raise ExecutionOrderValidationError(f"Stop loss order requires finite positive Decimal stop_price, got {self.stop_price!r}")

