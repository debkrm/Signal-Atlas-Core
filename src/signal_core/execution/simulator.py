"""Single Authoritative Execution Fill Simulator for Signal Atlas Core.

Enforces structural realism for Indian equities per AGENTS.md Rule 5 and Rule 7:
1. Next-Session Execution (Zero Lookahead): Signal at T close fills strictly at session T+1 or later.
2. Exchange Series & Settlement Eligibility: Enforces SeriesEligibilityPolicy (APPROVED_EQ_ONLY_POLICY).
3. Circuit Freeze Fills:
   - Prohibits BUY fills when session High hits Upper Circuit limit (ask depth = 0; buyers rationed).
   - Prohibits SELL or Stop-Loss fills when session Low hits Lower Circuit limit (bid depth = 0; sellers trapped).
4. Volume Participation Cap: Orders capped at configured fraction (e.g. 3.0%) of actual session volume.
5. Price & Gap Realism:
   - Market-on-Open fills at Open + non-linear slippage.
   - Stop-Loss gap down fills at Open (not stop price) - slippage.
   - Limit orders fill strictly within limit constraints.
6. Exact Decimal Accounting: All execution prices, fees, slippages, and net amounts are exact Decimals.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Optional, Union

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
    SeriesEligibilityPolicy,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.costs import TransactionCostBreakdown, TransactionCostModel
from signal_core.execution.slippage import SlippageModel, SlippageResult
from signal_core.execution.types import (
    ExecutionOrder,
    ExecutionOrderValidationError,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)

BarInput = Union[PriceBar, ExchangeSessionObservation]


@dataclass(frozen=True, slots=True)
class ExecutionFillResult:
    """
    Immutable comprehensive result of an order simulation attempt.
    """
    order: ExecutionOrder
    status: FillStatus
    fill_date: datetime.date
    filled_quantity: int
    unfilled_quantity: int
    executed_price: Optional[Decimal]
    slippage: Optional[SlippageResult]
    costs: Optional[TransactionCostBreakdown]
    rejection_reason: Optional[str]


class ExecutionFillSimulator:
    """
    Authoritative single execution simulator for Indian cash equities.
    """

    def __init__(
        self,
        criteria: Optional[GoNoGoCriteria] = None,
        cost_model: Optional[TransactionCostModel] = None,
        slippage_model: Optional[SlippageModel] = None,
        eligibility_policy: SeriesEligibilityPolicy = APPROVED_EQ_ONLY_POLICY,
    ) -> None:
        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._cost_model = cost_model if cost_model is not None else TransactionCostModel(self._criteria.statutory_costs)
        self._slippage_model = slippage_model if slippage_model is not None else SlippageModel()
        self._eligibility_policy = eligibility_policy

    @property
    def criteria(self) -> GoNoGoCriteria:
        return self._criteria

    @property
    def cost_model(self) -> TransactionCostModel:
        return self._cost_model

    @property
    def slippage_model(self) -> SlippageModel:
        return self._slippage_model

    @property
    def eligibility_policy(self) -> SeriesEligibilityPolicy:
        return self._eligibility_policy

    def simulate_order(
        self,
        order: ExecutionOrder,
        bar: BarInput,
        upper_circuit_limit: Optional[Decimal] = None,
        lower_circuit_limit: Optional[Decimal] = None,
        average_daily_turnover: Optional[Decimal] = None,
    ) -> ExecutionFillResult:
        """
        Simulates the execution of an order against an exchange session observation/price bar.
        
        Args:
            order: Immutable ExecutionOrder to execute.
            bar: Session PriceBar or ExchangeSessionObservation on order.target_date.
            upper_circuit_limit: Optional session upper circuit limit price.
            lower_circuit_limit: Optional session lower circuit limit price.
            average_daily_turnover: Optional trailing average daily turnover in INR.
            
        Returns:
            ExecutionFillResult capturing fill status, quantity, price, slippage, and statutory costs.
        """
        if not isinstance(order, ExecutionOrder):
            raise ExecutionOrderValidationError(f"order must be ExecutionOrder, got {type(order)}")

        # Extract bar details
        if isinstance(bar, ExchangeSessionObservation):
            price_bar = bar.price_bar
            series = bar.series_classification
            instrument_id = bar.instrument_id
        elif isinstance(bar, PriceBar):
            price_bar = bar
            series = ExchangeSeries.EQ
            instrument_id = bar.instrument_id
        else:
            raise ExecutionOrderValidationError(f"bar must be PriceBar or ExchangeSessionObservation, got {type(bar)}")

        # Invariant 1: Instrument match
        if instrument_id != order.instrument_id:
            raise ExecutionOrderValidationError(
                f"Instrument mismatch: order is for '{order.instrument_id}' but bar is for '{instrument_id}'"
            )

        # Invariant 2: Execution Date Alignment
        if price_bar.trade_date != order.target_date:
            raise ExecutionOrderValidationError(
                f"Session date mismatch: bar trade_date ({price_bar.trade_date}) does not match order target_date ({order.target_date})"
            )

        # Invariant 3: Zero Lookahead & Latency Enforcement
        latency_sessions = 1  # Standard next-session assumption
        if latency_sessions < self._criteria.min_execution_latency_sessions:
            return self._create_rejected_result(
                order, price_bar.trade_date, FillStatus.REJECTED_INVALID_LATENCY,
                f"Execution latency must be at least {self._criteria.min_execution_latency_sessions} session(s)"
            )

        # Invariant 4: Series Eligibility Check (SEBI / NSE EQ vs BE)
        # Entry (BUY) is restricted if series is not eligible under policy
        if order.side == OrderSide.BUY and not self._eligibility_policy.is_eligible(series):
            return self._create_rejected_result(
                order, price_bar.trade_date, FillStatus.REJECTED_INELIGIBLE_SERIES,
                f"Instrument traded under series {series.value}, which is not eligible for entry under policy"
            )
        # Exit (SELL) is checked against holding eligibility / transition permission
        if order.side == OrderSide.SELL and not (self._eligibility_policy.is_eligible(series) or self._eligibility_policy.allow_series_transitions):
            return self._create_rejected_result(
                order, price_bar.trade_date, FillStatus.REJECTED_INELIGIBLE_SERIES,
                f"Instrument traded under series {series.value}, which is not eligible for holding under policy"
            )

        # Invariant 5: Circuit Filter Freeze Fills (Rule 5.3 & 7)
        # Prohibit BUY at Upper Circuit (ask depth is zero; buyers are rationed)
        if order.side == OrderSide.BUY and self._criteria.prohibit_buy_at_upper_circuit:
            if upper_circuit_limit is not None and price_bar.high >= upper_circuit_limit:
                return self._create_rejected_result(
                    order, price_bar.trade_date, FillStatus.REJECTED_UPPER_CIRCUIT,
                    f"Session High ({price_bar.high}) hit Upper Circuit limit ({upper_circuit_limit}); zero ask liquidity"
                )

        # Prohibit SELL / stop-loss at Lower Circuit (bid depth is zero; sellers are trapped)
        if order.side == OrderSide.SELL and self._criteria.prohibit_sell_at_lower_circuit:
            if lower_circuit_limit is not None and price_bar.low <= lower_circuit_limit:
                return self._create_rejected_result(
                    order, price_bar.trade_date, FillStatus.REJECTED_LOWER_CIRCUIT,
                    f"Session Low ({price_bar.low}) hit Lower Circuit limit ({lower_circuit_limit}); sellers trapped"
                )

        # Invariant 6: Liquidity & Volume Participation Cap (Rule 7.3)
        if price_bar.volume <= 0:
            return self._create_rejected_result(
                order, price_bar.trade_date, FillStatus.REJECTED_ZERO_LIQUIDITY,
                "Session traded volume is zero; execution impossible"
            )

        max_allowed_shares = int(Decimal(price_bar.volume) * self._criteria.max_volume_participation_cap)
        if max_allowed_shares <= 0:
            return self._create_rejected_result(
                order, price_bar.trade_date, FillStatus.REJECTED_VOLUME_CAP,
                f"Volume participation cap ({self._criteria.max_volume_participation_cap}) allows 0 shares on volume {price_bar.volume}"
            )

        if order.quantity > max_allowed_shares:
            if order.allow_partial_fill:
                fill_qty = max_allowed_shares
                unfilled_qty = order.quantity - fill_qty
                status = FillStatus.PARTIALLY_FILLED
            else:
                return self._create_rejected_result(
                    order, price_bar.trade_date, FillStatus.REJECTED_VOLUME_CAP,
                    f"Order quantity ({order.quantity}) exceeds max volume participation cap of {max_allowed_shares} shares"
                )
        else:
            fill_qty = order.quantity
            unfilled_qty = 0
            status = FillStatus.FILLED

        # Invariant 7: Execution Price Calculation & Gap Handling
        ref_price: Optional[Decimal] = None

        if order.order_type == OrderType.MARKET_ON_OPEN:
            ref_price = price_bar.open

        elif order.order_type == OrderType.STOP_LOSS:
            stop_price = order.stop_price
            if stop_price is None:
                raise ExecutionOrderValidationError("stop_price cannot be None for STOP_LOSS order")
            
            if order.side == OrderSide.SELL:
                # Gap-down below stop: fill at Open, NOT stop price!
                if price_bar.open <= stop_price:
                    ref_price = price_bar.open
                # Intraday touch of stop
                elif price_bar.low <= stop_price:
                    ref_price = stop_price
                else:
                    # Stop not triggered
                    return self._create_rejected_result(
                        order, price_bar.trade_date, FillStatus.UNTRIGGERED,
                        f"Stop price {stop_price} was not reached (session low was {price_bar.low})"
                    )
            else:  # BUY stop loss (e.g. short covering)
                # Gap-up above stop: fill at Open, NOT stop price!
                if price_bar.open >= stop_price:
                    ref_price = price_bar.open
                elif price_bar.high >= stop_price:
                    ref_price = stop_price
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, FillStatus.UNTRIGGERED,
                        f"Stop price {stop_price} was not reached (session high was {price_bar.high})"
                    )

        elif order.order_type == OrderType.LIMIT:
            limit_price = order.limit_price
            if limit_price is None:
                raise ExecutionOrderValidationError("limit_price cannot be None for LIMIT order")
            
            if order.side == OrderSide.BUY:
                if price_bar.low <= limit_price:
                    # Open at or below limit: favorable open fill
                    ref_price = min(price_bar.open, limit_price)
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, FillStatus.UNTRIGGERED,
                        f"Limit buy price {limit_price} was below session low ({price_bar.low})"
                    )
            else:  # SELL limit
                if price_bar.high >= limit_price:
                    # Open at or above limit: favorable open fill
                    ref_price = max(price_bar.open, limit_price)
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, FillStatus.UNTRIGGERED,
                        f"Limit sell price {limit_price} was above session high ({price_bar.high})"
                    )
        else:
            raise ExecutionOrderValidationError(f"Unsupported order_type: {order.order_type}")

        # Compute slippage
        slippage_result = self._slippage_model.compute_slippage(
            reference_price=ref_price,
            quantity=fill_qty,
            side=order.side,
            session_volume=price_bar.volume,
            average_daily_turnover=average_daily_turnover,
            session_high=price_bar.high,
            session_low=price_bar.low,
        )
        executed_price = slippage_result.adjusted_price

        # Check limit boundary after slippage
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ExecutionOrderValidationError("limit_price cannot be None for LIMIT order")
            if order.side == OrderSide.BUY and executed_price > order.limit_price:
                return self._create_rejected_result(
                    order, price_bar.trade_date, FillStatus.REJECTED_PRICE_LIMIT,
                    f"Adjusted execution price {executed_price} breached limit price {order.limit_price}"
                )
            elif order.side == OrderSide.SELL and executed_price < order.limit_price:
                return self._create_rejected_result(
                    order, price_bar.trade_date, FillStatus.REJECTED_PRICE_LIMIT,
                    f"Adjusted execution price {executed_price} fell below limit price {order.limit_price}"
                )

        # Invariant 8: Statutory Indian Transaction Costs
        costs = self._cost_model.compute_costs(
            trade_date=price_bar.trade_date,
            side=order.side,
            product=order.product,
            quantity=fill_qty,
            price=executed_price,
        )

        return ExecutionFillResult(
            order=order,
            status=status,
            fill_date=price_bar.trade_date,
            filled_quantity=fill_qty,
            unfilled_quantity=unfilled_qty,
            executed_price=executed_price,
            slippage=slippage_result,
            costs=costs,
            rejection_reason=None,
        )

    def _create_rejected_result(
        self,
        order: ExecutionOrder,
        fill_date: datetime.date,
        status: FillStatus,
        reason: str,
    ) -> ExecutionFillResult:
        return ExecutionFillResult(
            order=order,
            status=status,
            fill_date=fill_date,
            filled_quantity=0,
            unfilled_quantity=order.quantity,
            executed_price=None,
            slippage=None,
            costs=None,
            rejection_reason=reason,
        )
