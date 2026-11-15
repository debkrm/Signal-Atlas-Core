"""Public domain exports for execution simulation, slippage, and statutory costs."""

from typing import Any, List

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

# Runner exports deferred to avoid circular dependency with portfolio/strategy at module load (Finding H-90).
# Exported via __getattr__ and __dir__ so introspection ('DailyTPlus1OrderRunner' in dir(execution))
# and attribute access resolve seamlessly per PEP 562.
_RUNNER_EXPORTS = {
    "DailyTPlus1OrderRunner": "signal_core.execution.order_runner",
    "DailySignalCandidate": "signal_core.execution.order_runner",
    "DailyExecutionTicket": "signal_core.execution.order_runner",
    "OrderRunnerError": "signal_core.execution.order_runner",
    "OrderRunnerEligibilityError": "signal_core.execution.order_runner",
    "is_weekly_surveillance_trading_session": "signal_core.execution.order_runner",
}


def __getattr__(name: str) -> Any:
    if name in _RUNNER_EXPORTS:
        module_name = _RUNNER_EXPORTS[name]
        import importlib
        mod = importlib.import_module(module_name)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(list(globals().keys()) + list(_RUNNER_EXPORTS.keys()))


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
    # Order Runner (Phase 3B-1)
    "DailySignalCandidate",
    "DailyExecutionTicket",
    "DailyTPlus1OrderRunner",
    "OrderRunnerError",
    "OrderRunnerEligibilityError",
    "is_weekly_surveillance_trading_session",
]
