"""Public domain exports for execution simulation, slippage, and statutory costs."""

from signal_core.execution.costs import (
    CostCalculationError,
    SLAB_FLATTENING_DISCLOSURE,
    TransactionCostBreakdown,
    TransactionCostModel,
)
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.slippage import (
    SlippageCalculationError,
    SlippageModel,
    SlippageResult,
)
from signal_core.execution.types import (
    ExecutionOrder,
    ExecutionOrderValidationError,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)

__all__ = [
    # Types & Enums
    "OrderSide",
    "OrderProduct",
    "OrderType",
    "FillStatus",
    "ExecutionOrder",
    "ExecutionOrderValidationError",
    # Costs
    "TransactionCostModel",
    "TransactionCostBreakdown",
    "CostCalculationError",
    "SLAB_FLATTENING_DISCLOSURE",
    # Slippage
    "SlippageModel",
    "SlippageResult",
    "SlippageCalculationError",
    # Simulator
    "ExecutionFillSimulator",
    "ExecutionFillResult",
]
