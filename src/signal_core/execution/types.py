"""Domain Types, Enums and Order Contracts for Execution and Costs.

Defines immutable order models, execution sides, product types, and fill status codes
in strict accordance with Indian market structure (SEBI / NSE) and AGENTS.md invariants.
Contracts live in signal_core.contracts.order_types and are re-exported here for backwards compatibility
per Audit §62.3, §62.6 (Finding R-90a).
"""

from __future__ import annotations

from signal_core.contracts.order_types import (
    ExecutionFillResult,
    ExecutionOrder,
    ExecutionOrderValidationError,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)

__all__ = [
    "OrderSide",
    "OrderProduct",
    "OrderType",
    "FillStatus",
    "ExecutionOrderValidationError",
    "ExecutionOrder",
    "ExecutionFillResult",
]
