"""Single Authoritative Execution Fill Simulator for Signal Atlas Core.

Enforces structural realism for Indian equities per AGENTS.md Rule 5 and Rule 7:
1. Next-Session Execution & Calendar Latency Measurement (Zero Lookahead):
   - Computes exact latency in trading sessions from the trading calendar (or business days).
   - Records latency_sessions on every ExecutionFillResult.
   - Emits REJECTED_LOOKAHEAD if target_date <= signal_date.
   - Enforces min_execution_latency_sessions threshold against measured latency.
2. Exchange Series & Settlement Eligibility (Fail-Closed):
   - Requires explicit exchange series evidence (via ExchangeSessionObservation or explicit_series).
   - Bare PriceBar is never assumed to be EQ; fails closed with REJECTED_INELIGIBLE_SERIES.
   - Enforces SeriesEligibilityPolicy (APPROVED_EQ_ONLY_POLICY).
3. Circuit Freeze Fills (No Lookahead, Grounded in Evidence):
   - Uses fill reference price (e.g. Open) rather than end-of-day High/Low to evaluate freeze.
   - Legal open fills below Upper Circuit are executed even if session High reaches circuit later.
   - Rejects BUY when fill reference price >= Upper Circuit limit, or on whole-day lock (O=H=L=C).
   - Rejects SELL/stop when fill reference price <= Lower Circuit limit, or on whole-day lock.
4. Liquidity & Volume Participation Cap:
   - Enforces min_daily_turnover_crore threshold from criteria (REJECTED_INSUFFICIENT_TURNOVER).
   - Caps order fills at configured fraction (e.g. 3.0%) of actual session volume.
5. Price & Gap Realism:
   - Market-on-Open fills at Open + non-linear slippage.
   - Stop-Loss gap down fills at Open (not stop price) minus slippage.
   - Limit orders fill strictly within limit constraints.
6. Exact Decimal Accounting: All execution prices, fees, slippages, and net amounts are exact Decimals.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Optional, Sequence, Union

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
CRORE_MULTIPLIER = Decimal("10000000")


@dataclass(frozen=True, slots=True)
class ExecutionFillResult:
    """
    Immutable comprehensive result of an order simulation attempt.
    """
    order: ExecutionOrder
    status: FillStatus
    fill_date: datetime.date
    latency_sessions: int
    filled_quantity: int
    unfilled_quantity: int
    executed_price: Optional[Decimal]
    slippage: Optional[SlippageResult]
    costs: Optional[TransactionCostBreakdown]
    circuit_evidence_present: bool
    rejection_reason: Optional[str]
    fill_id: Optional[str] = None


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
        trading_calendar: Optional[Sequence[datetime.date]] = None,
    ) -> None:
        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._cost_model = cost_model if cost_model is not None else TransactionCostModel(self._criteria.statutory_costs)
        self._slippage_model = slippage_model if slippage_model is not None else SlippageModel()
        self._eligibility_policy = eligibility_policy
        self._trading_calendar = tuple(trading_calendar) if trading_calendar is not None else None
        self._cal_index = {d: i for i, d in enumerate(self._trading_calendar)} if self._trading_calendar is not None else None

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

    @property
    def trading_calendar(self) -> Optional[Sequence[datetime.date]]:
        return self._trading_calendar

    def _compute_latency_sessions(self, signal_date: datetime.date, target_date: datetime.date) -> int:
        """Computes the number of official trading sessions between signal_date and target_date."""
        if target_date <= signal_date:
            return 0
        if self._trading_calendar is not None and self._cal_index is not None:
            if signal_date in self._cal_index and target_date in self._cal_index:
                return self._cal_index[target_date] - self._cal_index[signal_date]
            # Fallback to counting calendar dates strictly between signal and target
            return sum(1 for d in self._trading_calendar if signal_date < d <= target_date)
        # Fallback to standard business days (Monday to Friday)
        cur = signal_date + datetime.timedelta(days=1)
        b_count = 0
        while cur <= target_date:
            if cur.weekday() < 5:  # Mon-Fri
                b_count += 1
            cur += datetime.timedelta(days=1)
        return b_count

    def simulate_order(
        self,
        order: ExecutionOrder,
        bar: BarInput,
        upper_circuit_limit: Optional[Decimal] = None,
        lower_circuit_limit: Optional[Decimal] = None,
        average_daily_turnover: Optional[Decimal] = None,
        explicit_series: Optional[ExchangeSeries] = None,
        round_to_paise: bool = False,
    ) -> ExecutionFillResult:
        """
        Simulates the execution of an order against an exchange session observation or price bar.
        
        Args:
            order: Immutable ExecutionOrder to execute.
            bar: Session PriceBar or ExchangeSessionObservation on order.target_date.
            upper_circuit_limit: Optional upper circuit limit override.
            lower_circuit_limit: Optional lower circuit limit override.
            average_daily_turnover: Optional trailing average daily turnover in INR.
            explicit_series: Optional explicit series when passing bare PriceBar.
            round_to_paise: Whether to quantize transaction costs to paise (0.01 INR).
            
        Returns:
            ExecutionFillResult capturing fill status, quantity, price, slippage, and statutory costs.
        """
        if not isinstance(order, ExecutionOrder):
            raise ExecutionOrderValidationError(f"order must be ExecutionOrder, got {type(order)}")

        # Invariant 1: Latency Measurement & Zero Lookahead Gate (E-3)
        latency_sessions = self._compute_latency_sessions(order.signal_date, order.target_date)
        
        # If target_date <= signal_date, lookahead is attempted
        if order.target_date <= order.signal_date or latency_sessions <= 0:
            return self._create_rejected_result(
                order, order.target_date, latency_sessions, FillStatus.REJECTED_LOOKAHEAD,
                f"Target execution date ({order.target_date}) must be strictly after signal date ({order.signal_date}); lookahead prohibited."
            )

        if latency_sessions < self._criteria.min_execution_latency_sessions:
            return self._create_rejected_result(
                order, order.target_date, latency_sessions, FillStatus.REJECTED_INVALID_LATENCY,
                f"Measured latency of {latency_sessions} session(s) is below required minimum of {self._criteria.min_execution_latency_sessions} session(s)."
            )

        # Invariant 2: Series Evidence Gate (E-2)
        obs_upper = None
        obs_lower = None
        if isinstance(bar, ExchangeSessionObservation):
            price_bar = bar.price_bar
            series = bar.series_classification
            instrument_id = bar.instrument_id
            obs_upper = bar.upper_circuit_limit
            obs_lower = bar.lower_circuit_limit
        elif isinstance(bar, PriceBar):
            if explicit_series is None:
                # E-2: Fail closed! Bare PriceBar lacks series evidence; cannot assume EQ
                return self._create_rejected_result(
                    order, bar.trade_date, latency_sessions, FillStatus.REJECTED_INELIGIBLE_SERIES,
                    "PriceBar lacks verified series evidence; bare PriceBar cannot be assumed to be ExchangeSeries.EQ (fail-closed invariant)."
                )
            price_bar = bar
            series = explicit_series
            instrument_id = bar.instrument_id
        else:
            raise ExecutionOrderValidationError(f"bar must be PriceBar or ExchangeSessionObservation, got {type(bar)}")

        # Invariant 3: Instrument match & Session Date Alignment
        if instrument_id != order.instrument_id:
            raise ExecutionOrderValidationError(
                f"Instrument mismatch: order is for '{order.instrument_id}' but bar is for '{instrument_id}'"
            )

        if price_bar.trade_date != order.target_date:
            raise ExecutionOrderValidationError(
                f"Session date mismatch: bar trade_date ({price_bar.trade_date}) does not match order target_date ({order.target_date})"
            )

        # Invariant 4: Series Eligibility Check (SEBI / NSE EQ vs BE)
        if order.side == OrderSide.BUY and not self._eligibility_policy.is_eligible(series):
            return self._create_rejected_result(
                order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_INELIGIBLE_SERIES,
                f"Instrument traded under series {series.value}, which is not eligible for entry under policy"
            )
        if order.side == OrderSide.SELL and not (self._eligibility_policy.is_eligible(series) or self._eligibility_policy.allow_series_transitions):
            return self._create_rejected_result(
                order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_INELIGIBLE_SERIES,
                f"Instrument traded under series {series.value}, which is not eligible for holding under policy"
            )

        # Invariant 5: Zero Volume Check (Zero Liquidity)
        if price_bar.volume <= 0:
            return self._create_rejected_result(
                order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_ZERO_LIQUIDITY,
                "Session traded volume is zero; execution impossible"
            )

        # Invariant 6: Minimum Daily Turnover Gate (E-4)
        min_turnover_inr = self._criteria.min_daily_turnover_crore * CRORE_MULTIPLIER
        actual_turnover = average_daily_turnover if average_daily_turnover is not None else (
            price_bar.traded_value if price_bar.traded_value is not None else (Decimal(price_bar.volume) * price_bar.open)
        )
        if actual_turnover < min_turnover_inr:
            return self._create_rejected_result(
                order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_INSUFFICIENT_TURNOVER,
                f"Instrument turnover of ₹{actual_turnover:,.2f} is below minimum liquidity threshold of ₹{min_turnover_inr:,.2f} ({self._criteria.min_daily_turnover_crore} Crore)."
            )

        # Invariant 7: Volume Participation Cap (Rule 7.3)

        max_allowed_shares = int(Decimal(price_bar.volume) * self._criteria.max_volume_participation_cap)
        if max_allowed_shares <= 0:
            return self._create_rejected_result(
                order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_VOLUME_CAP,
                f"Volume participation cap ({self._criteria.max_volume_participation_cap}) allows 0 shares on volume {price_bar.volume}"
            )

        if order.quantity > max_allowed_shares:
            if order.allow_partial_fill:
                fill_qty = max_allowed_shares
                unfilled_qty = order.quantity - fill_qty
                status = FillStatus.PARTIALLY_FILLED
            else:
                return self._create_rejected_result(
                    order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_VOLUME_CAP,
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
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.UNTRIGGERED,
                        f"Stop price {stop_price} was not reached (session low was {price_bar.low})"
                    )
            else:  # BUY stop loss
                if price_bar.open >= stop_price:
                    ref_price = price_bar.open
                elif price_bar.high >= stop_price:
                    ref_price = stop_price
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.UNTRIGGERED,
                        f"Stop price {stop_price} was not reached (session high was {price_bar.high})"
                    )

        elif order.order_type == OrderType.LIMIT:
            limit_price = order.limit_price
            if limit_price is None:
                raise ExecutionOrderValidationError("limit_price cannot be None for LIMIT order")
            
            if order.side == OrderSide.BUY:
                if price_bar.low <= limit_price:
                    ref_price = min(price_bar.open, limit_price)
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.UNTRIGGERED,
                        f"Limit buy price {limit_price} was below session low ({price_bar.low})"
                    )
            else:  # SELL limit
                if price_bar.high >= limit_price:
                    ref_price = max(price_bar.open, limit_price)
                else:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.UNTRIGGERED,
                        f"Limit sell price {limit_price} was above session high ({price_bar.high})"
                    )
        else:
            raise ExecutionOrderValidationError(f"Unsupported order_type: {order.order_type}")

        # Invariant 8: Circuit Filter Freeze Invariants (Rule 5.3, 7, E-1)
        # Evaluated on the fill reference price (e.g. Open) to prevent lookahead from end-of-day High/Low
        effective_upper = upper_circuit_limit if upper_circuit_limit is not None else obs_upper
        effective_lower = lower_circuit_limit if lower_circuit_limit is not None else obs_lower

        if order.side == OrderSide.BUY and self._criteria.prohibit_buy_at_upper_circuit:
            # 1. Fill reference price is at or through upper circuit limit
            if effective_upper is not None and ref_price >= effective_upper:
                return self._create_rejected_result(
                    order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_UPPER_CIRCUIT,
                    f"Fill reference price ({ref_price}) is at or above Upper Circuit limit ({effective_upper}); zero ask liquidity"
                )
            # 2. Whole-day locked upper circuit session (high == low)
            if price_bar.high == price_bar.low:
                if effective_upper is not None and price_bar.high >= effective_upper:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_UPPER_CIRCUIT,
                        f"Whole-day locked upper circuit session ({price_bar.high}); buyers rationed"
                    )
                elif effective_upper is None:
                    # Locked 0-range bar without explicit limit evidence
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_UPPER_CIRCUIT,
                        f"Locked 0-range session (high={price_bar.high} == low={price_bar.low}); buyers rationed"
                    )

        if order.side == OrderSide.SELL and self._criteria.prohibit_sell_at_lower_circuit:
            # 1. Fill reference price is at or through lower circuit limit
            if effective_lower is not None and ref_price <= effective_lower:
                return self._create_rejected_result(
                    order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_LOWER_CIRCUIT,
                    f"Fill reference price ({ref_price}) is at or below Lower Circuit limit ({effective_lower}); sellers trapped"
                )
            # 2. Whole-day locked lower circuit session (high == low)
            if price_bar.high == price_bar.low:
                if effective_lower is not None and price_bar.low <= effective_lower:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_LOWER_CIRCUIT,
                        f"Whole-day locked lower circuit session ({price_bar.low}); sellers trapped"
                    )
                elif effective_lower is None:
                    return self._create_rejected_result(
                        order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_LOWER_CIRCUIT,
                        f"Locked 0-range session (high={price_bar.high} == low={price_bar.low}); sellers trapped"
                    )

        # Invariant 9: Slippage Calculation & Execution Price Realism
        max_buy_price = min(price_bar.high, effective_upper) if effective_upper is not None else price_bar.high
        min_sell_price = max(price_bar.low, effective_lower) if effective_lower is not None else price_bar.low

        slippage_result = self._slippage_model.compute_slippage(
            reference_price=ref_price,
            quantity=fill_qty,
            side=order.side,
            session_volume=price_bar.volume,
            average_daily_turnover=average_daily_turnover,
            session_high=max_buy_price,
            session_low=min_sell_price,
        )
        executed_price = slippage_result.adjusted_price

        # Check limit boundary after slippage
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ExecutionOrderValidationError("limit_price cannot be None for LIMIT order")
            if order.side == OrderSide.BUY and executed_price > order.limit_price:
                return self._create_rejected_result(
                    order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_PRICE_LIMIT,
                    f"Adjusted execution price {executed_price} breached limit price {order.limit_price}"
                )
            elif order.side == OrderSide.SELL and executed_price < order.limit_price:
                return self._create_rejected_result(
                    order, price_bar.trade_date, latency_sessions, FillStatus.REJECTED_PRICE_LIMIT,
                    f"Adjusted execution price {executed_price} fell below limit price {order.limit_price}"
                )

        # Invariant 10: Statutory Indian Transaction Costs
        costs = self._cost_model.compute_costs(
            trade_date=price_bar.trade_date,
            side=order.side,
            product=order.product,
            quantity=fill_qty,
            price=executed_price,
            round_to_paise=round_to_paise,
        )

        circuit_evidence = (effective_upper is not None or effective_lower is not None)
        fill_id = f"FILL_{order.order_id}" if order.order_id is not None else None

        return ExecutionFillResult(
            order=order,
            status=status,
            fill_date=price_bar.trade_date,
            latency_sessions=latency_sessions,
            filled_quantity=fill_qty,
            unfilled_quantity=unfilled_qty,
            executed_price=executed_price,
            slippage=slippage_result,
            costs=costs,
            circuit_evidence_present=circuit_evidence,
            rejection_reason=None,
            fill_id=fill_id,
        )

    def _create_rejected_result(
        self,
        order: ExecutionOrder,
        fill_date: datetime.date,
        latency_sessions: int,
        status: FillStatus,
        reason: str,
        circuit_evidence_present: bool = False,
    ) -> ExecutionFillResult:
        fill_id = f"REJ_{order.order_id}" if order.order_id is not None else None
        return ExecutionFillResult(
            order=order,
            status=status,
            fill_date=fill_date,
            latency_sessions=latency_sessions,
            filled_quantity=0,
            unfilled_quantity=order.quantity,
            executed_price=None,
            slippage=None,
            costs=None,
            circuit_evidence_present=circuit_evidence_present,
            rejection_reason=reason,
            fill_id=fill_id,
        )
