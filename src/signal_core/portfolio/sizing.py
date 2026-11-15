"""
ATR-Based R-Multiple Position Sizing Engine for Signal Atlas Core.
Enforces AGENTS.md §6.4 (Strict Decimal Accounting), §7.2 (Statutory Cost Realism),
§7.3 (Liquidity Constraints & Volume Participation), §13.5 (Single Authoritative Engine),
and Audit §57.3 / §57.7 Items 1–2 (Findings H-77, H-80, N-73).

All computations are pure Decimal arithmetic with zero binary floating-point drift.
Sizes position share quantity strictly from risk budget (R) divided by effective ATR stop distance
(recomputed after minimum tick flooring so risk_amount strictly equals actual loss at stop_loss_price).
Defaults for max_single_position_weight and max_volume_participation are loaded directly
from GoNoGoCriteria (zero unlinked threshold literals), and session_volume is strictly required.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria

# Conservative modelling tick floor for position sizing and stop placement (Finding N-80).
# Note: While NSE's statutory cash-equity tick size is Re 0.01 for scrips below ₹100,
# ₹0.05 is enforced as a fail-closed conservative modelling floor to prevent penny-stock
# arithmetic distortion and ensure positive stop distances (Audit §58.3 Finding N-80).
MIN_TICK_SIZE = Decimal("0.05")


class PositionSizingValidationError(ValueError):
    """Raised when position sizing inputs violate mathematical or boundary invariants."""
    pass


def _validate_decimal(val: object, field_name: str, strictly_positive: bool = True) -> Decimal:
    """Validates that a value is a genuine finite Decimal (rejecting bool, float)."""
    if isinstance(val, bool):
        raise PositionSizingValidationError(f"{field_name} cannot be a boolean, got {val!r}")
    if isinstance(val, float):
        raise PositionSizingValidationError(f"{field_name} cannot be a binary float. Exact Decimal required.")
    if not isinstance(val, Decimal):
        raise PositionSizingValidationError(f"{field_name} must be an exact Decimal, got {type(val).__name__}")
    if not val.is_finite():
        raise PositionSizingValidationError(f"{field_name} must be a finite Decimal, got {val!r}")
    if strictly_positive and val <= Decimal("0"):
        raise PositionSizingValidationError(f"{field_name} must be strictly positive (> 0), got {val}")
    if not strictly_positive and val < Decimal("0"):
        raise PositionSizingValidationError(f"{field_name} must be non-negative (>= 0), got {val}")
    return val


@dataclass(frozen=True, slots=True)
class PositionSizeResult:
    """
    Immutable specification of computed position sizing and execution risk metrics.
    All financial metrics are exact Decimal arithmetic.
    """
    quantity: int
    entry_price: Decimal
    stop_loss_price: Decimal
    stop_distance: Decimal
    risk_amount: Decimal
    position_value: Decimal
    position_weight: Decimal
    binding_constraint: str
    risk_per_trade_pct: Decimal
    atr_stop_multiple: Decimal
    atr: Decimal


def calculate_atr_r_multiple_position_size(
    equity: Decimal,
    entry_price: Decimal,
    atr: Decimal,
    session_volume: int,
    criteria: Optional[GoNoGoCriteria] = None,
    risk_per_trade_pct: Decimal = Decimal("0.01"),
    atr_stop_multiple: Decimal = Decimal("2.0"),
    max_single_position_weight: Optional[Decimal] = None,
    max_volume_participation: Optional[Decimal] = None,
    available_cash: Optional[Decimal] = None,
    estimated_cost_buffer_pct: Decimal = Decimal("0.005"),
    min_trade_quantity: int = 1,
) -> PositionSizeResult:
    """
    Calculates exact integer share quantity using ATR-based R-multiple position sizing.

    Formulas:
        raw_stop = entry_price - (atr_stop_multiple * atr)
        stop_loss_price = max(MIN_TICK_SIZE, raw_stop)
        effective_stop_distance = entry_price - stop_loss_price  (must be > 0)
        risk_budget = equity * risk_per_trade_pct
        q_risk = floor(risk_budget / effective_stop_distance)
        q_weight = floor((equity * max_single_position_weight) / entry_price)
        q_cash = floor(available_cash / (entry_price * (1 + cost_buffer)))  [if cash provided]
        q_vol = floor(session_volume * max_volume_participation)

        final_quantity = max(0, min(q_risk, q_weight, q_cash, q_vol))
        risk_amount = final_quantity * effective_stop_distance

    Args:
        equity: Total portfolio equity in INR (must be > 0).
        entry_price: Expected execution entry price in INR (must be > MIN_TICK_SIZE).
        atr: Average True Range of instrument in INR (must be > 0).
        session_volume: Traded volume of session in shares (required positive integer, Finding H-80).
        criteria: Optional GoNoGoCriteria to source weight and participation bounds from (Finding H-80).
        risk_per_trade_pct: Fraction of equity risked per trade (default 0.01 = 1%).
        atr_stop_multiple: Stop distance multiple k (default 2.0 -> stop at 2*ATR).
        max_single_position_weight: Max capital allocation to single position (defaults to criteria.max_single_position_weight).
        max_volume_participation: Max fraction of session volume allowed (defaults to criteria.max_volume_participation_cap).
        available_cash: Settled cash available in ledger (optional).
        estimated_cost_buffer_pct: Statutory fee/tax buffer applied to cash check (default 0.005 = 0.5%).
        min_trade_quantity: Minimum acceptable share count (default 1).

    Returns:
        PositionSizeResult with exact integer quantity, prices, values, and binding constraint.
    """
    active_criteria = criteria or load_go_no_go_criteria()

    eq = _validate_decimal(equity, "equity", strictly_positive=True)
    px = _validate_decimal(entry_price, "entry_price", strictly_positive=True)
    if px <= MIN_TICK_SIZE:
        raise PositionSizingValidationError(
            f"entry_price must be strictly greater than minimum tick size {MIN_TICK_SIZE}, got {px} (Finding H-77)"
        )

    atr_val = _validate_decimal(atr, "atr", strictly_positive=True)
    risk_pct = _validate_decimal(risk_per_trade_pct, "risk_per_trade_pct", strictly_positive=True)
    k_mult = _validate_decimal(atr_stop_multiple, "atr_stop_multiple", strictly_positive=True)

    # Defaults loaded directly from GoNoGoCriteria contract (Finding H-80)
    weight_bound = max_single_position_weight if max_single_position_weight is not None else active_criteria.max_single_position_weight
    max_weight = _validate_decimal(weight_bound, "max_single_position_weight", strictly_positive=True)

    vol_bound = max_volume_participation if max_volume_participation is not None else active_criteria.max_volume_participation_cap
    vol_part = _validate_decimal(vol_bound, "max_volume_participation", strictly_positive=True)

    cost_buf = _validate_decimal(estimated_cost_buffer_pct, "estimated_cost_buffer_pct", strictly_positive=False)

    if risk_pct > Decimal("1.0"):
        raise PositionSizingValidationError(f"risk_per_trade_pct cannot exceed 1.0 (100%), got {risk_pct}")
    if max_weight > Decimal("1.0"):
        raise PositionSizingValidationError(f"max_single_position_weight cannot exceed 1.0 (100%), got {max_weight}")
    if vol_part > Decimal("1.0"):
        raise PositionSizingValidationError(f"max_volume_participation cannot exceed 1.0, got {vol_part}")
    if min_trade_quantity < 1:
        raise PositionSizingValidationError(f"min_trade_quantity must be >= 1, got {min_trade_quantity}")

    # session_volume is strictly required whenever volume participation cap is in force (Finding H-80)
    if (
        session_volume is None
        or isinstance(session_volume, bool)
        or not isinstance(session_volume, int)
        or session_volume <= 0
    ):
        raise PositionSizingValidationError(
            f"session_volume must be a strictly positive integer, got {session_volume!r} (Finding H-80)"
        )

    # 1. Stop Price and Effective Stop Distance (Finding H-77)
    # Floor the stop loss price at the minimum tick first, then recompute stop distance from floored stop
    raw_stop = px - (k_mult * atr_val)
    stop_loss_px = max(MIN_TICK_SIZE, raw_stop)
    effective_stop_distance = px - stop_loss_px
    if effective_stop_distance <= Decimal("0"):
        raise PositionSizingValidationError(
            f"effective_stop_distance must be strictly positive (> 0), got {effective_stop_distance} "
            f"(entry_price={px}, stop_loss_price={stop_loss_px}) (Finding H-77)"
        )

    # 2. Risk Budget Constraint (derived from effective stop distance)
    risk_budget = eq * risk_pct
    q_risk = int(risk_budget // effective_stop_distance)

    # 3. Maximum Single Position Weight Constraint
    max_pos_val = eq * max_weight
    q_weight = int(max_pos_val // px)

    # 4. Volume Participation Constraint
    q_vol = int(Decimal(str(session_volume)) * vol_part)

    # Track constraints: (quantity, constraint_name)
    candidates: list[tuple[int, str]] = [
        (q_risk, "RISK_BUDGET"),
        (q_weight, "MAX_POSITION_WEIGHT"),
        (q_vol, "VOLUME_PARTICIPATION"),
    ]

    # 5. Available Cash Constraint (including statutory cost buffer)
    if available_cash is not None:
        cash_val = _validate_decimal(available_cash, "available_cash", strictly_positive=False)
        effective_px = px * (Decimal("1.0") + cost_buf)
        q_cash = int(cash_val // effective_px)
        candidates.append((q_cash, "AVAILABLE_CASH"))

    # Resolve binding constraint: lowest non-negative candidate (Finding N-73: clean non-redundant branches)
    min_qty, binding_reason = min(candidates, key=lambda c: c[0])

    if min_qty <= 0:
        final_qty = 0
        final_binding = binding_reason
    elif min_qty < min_trade_quantity:
        final_qty = 0
        final_binding = "BELOW_MINIMUM_QUANTITY"
    else:
        final_qty = min_qty
        final_binding = binding_reason

    pos_val = Decimal(str(final_qty)) * px
    # Actual risk amount strictly equals final_quantity * effective_stop_distance (Finding H-77)
    pos_risk = Decimal(str(final_qty)) * effective_stop_distance
    pos_weight = pos_val / eq if eq > Decimal("0") else Decimal("0.0")

    return PositionSizeResult(
        quantity=final_qty,
        entry_price=px,
        stop_loss_price=stop_loss_px,
        stop_distance=effective_stop_distance,
        risk_amount=pos_risk,
        position_value=pos_val,
        position_weight=pos_weight,
        binding_constraint=final_binding,
        risk_per_trade_pct=risk_pct,
        atr_stop_multiple=k_mult,
        atr=atr_val,
    )
