"""Non-Linear Slippage and Liquidity Impact Model for Indian Equities.

Implements the square-root market impact and bid-ask spread crossing model
mandated by AGENTS.md Rule 7.3 and WHAT_WE_ARE_BUILDING.md §2.D:

    Slippage_Rate >= (Spread / 2) + kappa * (Order_Value / Average_Daily_Turnover) ^ alpha

All calculations enforce exact Decimal arithmetic and square-root calculations.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from signal_core.execution.types import OrderSide

BPS_DIVISOR = Decimal("10000")
DEFAULT_HALF_SPREAD_BPS = Decimal("5.0")       # 5 bps half-spread default (0.05%)
DEFAULT_IMPACT_KAPPA = Decimal("0.10")          # kappa market impact coefficient
DEFAULT_IMPACT_ALPHA = Decimal("0.5")           # square-root market impact law


class SlippageCalculationError(ValueError):
    """Raised when slippage inputs or calculated parameters violate mathematical invariants."""
    pass


@dataclass(frozen=True, slots=True)
class SlippageResult:
    """
    Immutable detailed result of slippage and market impact computation.
    """
    reference_price: Decimal
    order_value: Decimal
    turnover_base: Decimal
    participation_ratio: Decimal
    half_spread_rate: Decimal
    impact_rate: Decimal
    slippage_rate: Decimal
    slippage_per_share: Decimal
    adjusted_price: Decimal


class SlippageModel:
    """
    Non-linear slippage model combining bid-ask spread crossing with square-root market impact.
    """

    def __init__(
        self,
        half_spread_bps: Decimal = DEFAULT_HALF_SPREAD_BPS,
        impact_kappa: Decimal = DEFAULT_IMPACT_KAPPA,
        impact_alpha: Decimal = DEFAULT_IMPACT_ALPHA,
    ) -> None:
        if isinstance(half_spread_bps, bool) or not isinstance(half_spread_bps, Decimal) or not half_spread_bps.is_finite() or half_spread_bps < 0:
            raise SlippageCalculationError(f"half_spread_bps must be non-negative Decimal, got {half_spread_bps!r}")
        if isinstance(impact_kappa, bool) or not isinstance(impact_kappa, Decimal) or not impact_kappa.is_finite() or impact_kappa < 0:
            raise SlippageCalculationError(f"impact_kappa must be non-negative Decimal, got {impact_kappa!r}")
        if isinstance(impact_alpha, bool) or not isinstance(impact_alpha, Decimal) or not impact_alpha.is_finite() or impact_alpha <= 0:
            raise SlippageCalculationError(f"impact_alpha must be positive Decimal, got {impact_alpha!r}")

        self._half_spread_bps = half_spread_bps
        self._impact_kappa = impact_kappa
        self._impact_alpha = impact_alpha

    @property
    def half_spread_bps(self) -> Decimal:
        return self._half_spread_bps

    @property
    def impact_kappa(self) -> Decimal:
        return self._impact_kappa

    @property
    def impact_alpha(self) -> Decimal:
        return self._impact_alpha

    def compute_slippage(
        self,
        reference_price: Decimal,
        quantity: int,
        side: OrderSide,
        session_volume: int,
        average_daily_turnover: Optional[Decimal] = None,
        session_high: Optional[Decimal] = None,
        session_low: Optional[Decimal] = None,
    ) -> SlippageResult:
        """
        Calculates adverse price slippage for an order.
        
        Args:
            reference_price: Unadjusted price (e.g. Open price).
            quantity: Order share quantity.
            side: OrderSide.BUY or OrderSide.SELL.
            session_volume: Total traded shares in session (TOTTRDQTY).
            average_daily_turnover: Optional average daily turnover in INR.
            session_high: Optional session high price for clamping.
            session_low: Optional session low price for clamping.
            
        Returns:
            SlippageResult containing rates, per-share slippage, and adjusted price.
        """
        if not isinstance(reference_price, Decimal) or not reference_price.is_finite() or reference_price <= 0:
            raise SlippageCalculationError(f"reference_price must be positive Decimal, got {reference_price!r}")
            
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise SlippageCalculationError(f"quantity must be positive int, got {quantity!r}")
            
        if not isinstance(side, OrderSide):
            raise SlippageCalculationError(f"side must be OrderSide, got {type(side)}")
            
        if isinstance(session_volume, bool) or not isinstance(session_volume, int) or session_volume <= 0:
            raise SlippageCalculationError(f"session_volume must be positive int, got {session_volume!r}")

        order_value = Decimal(quantity) * reference_price
        
        # Determine turnover base
        if average_daily_turnover is not None:
            if not isinstance(average_daily_turnover, Decimal) or not average_daily_turnover.is_finite() or average_daily_turnover <= 0:
                raise SlippageCalculationError(
                    f"average_daily_turnover must be positive Decimal, got {average_daily_turnover!r}"
                )
            turnover_base = average_daily_turnover
        else:
            turnover_base = Decimal(session_volume) * reference_price

        # Half-spread rate
        half_spread_rate = self._half_spread_bps / BPS_DIVISOR
        
        # Market impact calculation
        participation_ratio = order_value / turnover_base
        if self._impact_alpha == Decimal("0.5"):
            impact_rate = self._impact_kappa * participation_ratio.sqrt()
        else:
            # Exact Decimal exponentiation without binary float intermediate
            impact_rate = self._impact_kappa * (participation_ratio ** self._impact_alpha)

        slippage_rate = half_spread_rate + impact_rate
        slippage_per_share = reference_price * slippage_rate

        # Calculate adverse price
        if side == OrderSide.BUY:
            raw_adjusted_price = reference_price + slippage_per_share
            if session_high is not None:
                adjusted_price = min(raw_adjusted_price, session_high)
            else:
                adjusted_price = raw_adjusted_price
        else:
            raw_adjusted_price = reference_price - slippage_per_share
            if session_low is not None:
                adjusted_price = max(raw_adjusted_price, session_low)
            else:
                adjusted_price = raw_adjusted_price

        return SlippageResult(
            reference_price=reference_price,
            order_value=order_value,
            turnover_base=turnover_base,
            participation_ratio=participation_ratio,
            half_spread_rate=half_spread_rate,
            impact_rate=impact_rate,
            slippage_rate=slippage_rate,
            slippage_per_share=slippage_per_share,
            adjusted_price=adjusted_price,
        )

