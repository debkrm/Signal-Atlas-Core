"""
Daily T+1 Open Order Runner for Indian Cash Equities.

Enforces structural realism for delivery swing trading on NSE EQ per AGENTS.md:
- Rule 1 & 2: Simplicity and explicit assumptions.
- Rule 5.1 & 13.1: Strict NSE EQ rolling cash delivery scope (zero intraday squaring off, zero F&O, zero BE/BZ entry).
- Rule 5.3: Circuit filter realism: BUY fills into Upper Circuit freeze are rejected (zero ask depth).
- Rule 6.4: Exact Decimal accounting.
- Rule 7.1: Next-session execution and zero lookahead (signal at T close -> execute at earliest T+1 open).
- Rule 7.4 & 13.5: Single authoritative engine: routes all fills and costs strictly through
  ExecutionFillSimulator and Portfolio ledger. No secondary or shadow simulation paths.
- Phase 3B-1 specifications (Audit §58.5, §58.7 Item 6).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional, Tuple, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from signal_core.portfolio.portfolio import Portfolio
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
    SeriesEligibilityPolicy,
)
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.types import (
    ExecutionOrder,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)
from signal_core.portfolio.sizing import (
    PositionSizeResult,
    calculate_atr_r_multiple_position_size,
)
from signal_core.storage.calendar import (
    TradingCalendar,
    load_anchored_nse_trading_calendar,
)
from signal_core.strategy.base import (
    LookaheadIntentError,
    OrderIntent,
)


class OrderRunnerError(Exception):
    """Base exception for order runner errors."""
    pass


class OrderRunnerEligibilityError(OrderRunnerError):
    """Raised when an order candidate violates exchange series or trading scope invariants."""
    pass


@dataclass(frozen=True, slots=True)
class DailySignalCandidate:
    """
    Immutable specification of a trade candidate formulated at session T close.
    """
    instrument_id: str
    signal_date: datetime.date
    side: OrderSide
    entry_reference_price: Decimal
    atr: Decimal
    session_volume: int
    series: str = "EQ"
    order_type: OrderType = OrderType.MARKET_ON_OPEN
    product: OrderProduct = OrderProduct.DELIVERY
    allow_partial_fill: bool = False
    metadata: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.instrument_id, bool)
            or not isinstance(self.instrument_id, str)
            or not self.instrument_id.strip()
        ):
            raise OrderRunnerError(f"instrument_id must be a clean string, got {self.instrument_id!r}")

        if type(self.signal_date) is not datetime.date:
            raise OrderRunnerError(f"signal_date must be exact datetime.date, got {type(self.signal_date).__name__}")

        if not isinstance(self.side, OrderSide):
            raise OrderRunnerError(f"side must be an OrderSide enum, got {type(self.side)}")

        if not isinstance(self.order_type, OrderType):
            raise OrderRunnerError(f"order_type must be an OrderType enum, got {type(self.order_type)}")

        if not isinstance(self.product, OrderProduct):
            raise OrderRunnerError(f"product must be an OrderProduct enum, got {type(self.product)}")

        if (
            isinstance(self.entry_reference_price, bool)
            or not isinstance(self.entry_reference_price, Decimal)
            or not self.entry_reference_price.is_finite()
            or self.entry_reference_price <= Decimal("0")
        ):
            raise OrderRunnerError(
                f"entry_reference_price must be positive finite Decimal, got {self.entry_reference_price!r}"
            )

        if (
            isinstance(self.atr, bool)
            or not isinstance(self.atr, Decimal)
            or not self.atr.is_finite()
            or self.atr <= Decimal("0")
        ):
            raise OrderRunnerError(f"atr must be positive finite Decimal, got {self.atr!r}")

        if isinstance(self.session_volume, bool) or not isinstance(self.session_volume, int) or self.session_volume <= 0:
            raise OrderRunnerError(f"session_volume must be positive integer, got {self.session_volume!r}")


@dataclass(frozen=True, slots=True)
class DailyExecutionTicket:
    """
    Complete lifecycle ticket tracking a candidate through intent, order, sizing, and fill result.
    """
    candidate: DailySignalCandidate
    target_date: datetime.date
    intent: OrderIntent
    order: ExecutionOrder
    size_result: Optional[PositionSizeResult]
    fill_result: Optional[ExecutionFillResult]


class DailyTPlus1OrderRunner:
    """
    Authoritative Daily T+1 Order Runner for Indian Cash Delivery Swing Strategies.

    Wires ATR R-multiple position sizing directly into OrderIntent and routes
    all execution through ExecutionFillSimulator and Portfolio ledger.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        simulator: ExecutionFillSimulator,
        calendar: Optional[TradingCalendar] = None,
        criteria: Optional[GoNoGoCriteria] = None,
        risk_per_trade_pct: Decimal = Decimal("0.01"),
        atr_stop_multiple: Decimal = Decimal("2.0"),
        eligibility_policy: SeriesEligibilityPolicy = APPROVED_EQ_ONLY_POLICY,
    ) -> None:
        self._portfolio = portfolio
        self._simulator = simulator
        self._calendar = calendar if calendar is not None else load_anchored_nse_trading_calendar()
        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._risk_per_trade_pct = risk_per_trade_pct
        self._atr_stop_multiple = atr_stop_multiple
        self._eligibility_policy = eligibility_policy

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def simulator(self) -> ExecutionFillSimulator:
        return self._simulator

    @property
    def calendar(self) -> TradingCalendar:
        return self._calendar

    @property
    def criteria(self) -> GoNoGoCriteria:
        return self._criteria

    def generate_order_intent(
        self,
        candidate: DailySignalCandidate,
        target_date: Optional[datetime.date] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> Tuple[OrderIntent, Optional[PositionSizeResult]]:
        """
        Generates an authoritative OrderIntent from a DailySignalCandidate.
        Enforces:
        1. Series eligibility (EQ only; BE/BZ entry rejected fail-closed per Rule 5.1, 13.1).
        2. T+1 calendar session determination (Zero Lookahead Rule 7.1).
        3. ATR R-multiple sizing for BUY orders.
        4. Open-quantity resolution for SELL orders (no naked short sales).
        """
        # Validate series under cash delivery swing scope
        series_str = candidate.series.strip().upper()
        if series_str not in ("EQ", ExchangeSeries.EQ.value):
            raise OrderRunnerEligibilityError(
                f"Candidate {candidate.instrument_id} series '{candidate.series}' is ineligible for cash delivery swing entry "
                f"(AGENTS.md §5.1, §13.1: only EQ series is entry-eligible; Trade-to-Trade BE/BZ is strictly prohibited)."
            )

        # Resolve target date
        if target_date is None:
            try:
                resolved_target_date = self._calendar.advance_sessions(candidate.signal_date, 1)
            except Exception as e:
                raise OrderRunnerError(
                    f"Unable to resolve T+1 session from calendar for signal_date {candidate.signal_date}: {e}"
                ) from e
        else:
            resolved_target_date = target_date

        # Zero Lookahead Invariant (Rule 7.1)
        if resolved_target_date <= candidate.signal_date:
            raise LookaheadIntentError(
                f"Lookahead violation: target_date {resolved_target_date} must be strictly after "
                f"signal_date {candidate.signal_date}. Same-session (T->T) execution is prohibited."
            )

        if candidate.side == OrderSide.BUY:
            # Current portfolio equity and available cash
            current_equity = self._portfolio.current_total_equity(latest_market_prices)
            available_cash = self._portfolio.current_cash

            size_result = calculate_atr_r_multiple_position_size(
                equity=current_equity,
                entry_price=candidate.entry_reference_price,
                atr=candidate.atr,
                session_volume=candidate.session_volume,
                criteria=self._criteria,
                risk_per_trade_pct=self._risk_per_trade_pct,
                atr_stop_multiple=self._atr_stop_multiple,
                available_cash=available_cash,
            )

            intent = OrderIntent.from_position_size_result(
                instrument_id=candidate.instrument_id,
                signal_date=candidate.signal_date,
                target_date=resolved_target_date,
                side=candidate.side,
                size_result=size_result,
                order_type=candidate.order_type,
                product=candidate.product,
                allow_partial_fill=candidate.allow_partial_fill,
                additional_metadata=candidate.metadata,
            )
            return intent, size_result

        elif candidate.side == OrderSide.SELL:
            # Delivery exit must correspond to existing held position
            pos = self._portfolio.get_position(candidate.instrument_id)
            if pos is None or pos.is_closed or pos.quantity <= 0:
                raise OrderRunnerEligibilityError(
                    f"Cannot generate SELL OrderIntent for {candidate.instrument_id}: "
                    "no open held position found in Portfolio (naked short selling prohibited in cash delivery)."
                )

            intent = OrderIntent(
                instrument_id=candidate.instrument_id,
                signal_date=candidate.signal_date,
                target_date=resolved_target_date,
                side=candidate.side,
                order_type=candidate.order_type,
                product=candidate.product,
                quantity=pos.quantity,
                allow_partial_fill=candidate.allow_partial_fill,
                metadata=candidate.metadata,
            )
            return intent, None

        else:
            raise OrderRunnerError(f"Unsupported OrderSide: {candidate.side}")

    def execute_ticket(
        self,
        intent: OrderIntent,
        candidate: DailySignalCandidate,
        t_plus_1_bar: Union[PriceBar, ExchangeSessionObservation],
        size_result: Optional[PositionSizeResult] = None,
        price_band: Optional[PriceBandRecord] = None,
        explicit_series: Optional[ExchangeSeries] = None,
        average_daily_turnover: Optional[Decimal] = None,
    ) -> DailyExecutionTicket:
        """
        Executes an OrderIntent via the authoritative ExecutionFillSimulator and posts
        any resulting fill to the Portfolio cash ledger and position book.
        """
        order = intent.to_execution_order()

        # Enforce series on observation if PriceBar provided without explicit_series
        effective_series = explicit_series
        if effective_series is None and isinstance(t_plus_1_bar, PriceBar):
            if candidate.series.upper() == "EQ":
                effective_series = ExchangeSeries.EQ

        fill_result = self._simulator.simulate_order(
            order=order,
            bar=t_plus_1_bar,
            price_band=price_band,
            explicit_series=effective_series,
            average_daily_turnover=average_daily_turnover,
        )

        if fill_result.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            self._portfolio.process_fill(fill_result)

        return DailyExecutionTicket(
            candidate=candidate,
            target_date=intent.target_date,
            intent=intent,
            order=order,
            size_result=size_result,
            fill_result=fill_result,
        )

    def run_candidate(
        self,
        candidate: DailySignalCandidate,
        t_plus_1_bar: Union[PriceBar, ExchangeSessionObservation],
        target_date: Optional[datetime.date] = None,
        price_band: Optional[PriceBandRecord] = None,
        explicit_series: Optional[ExchangeSeries] = None,
        average_daily_turnover: Optional[Decimal] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> DailyExecutionTicket:
        """
        End-to-end execution of a DailySignalCandidate through intent formulation, sizing,
        fill simulation, and portfolio processing.
        """
        intent, size_res = self.generate_order_intent(
            candidate=candidate,
            target_date=target_date,
            latest_market_prices=latest_market_prices,
        )

        return self.execute_ticket(
            intent=intent,
            candidate=candidate,
            t_plus_1_bar=t_plus_1_bar,
            size_result=size_res,
            price_band=price_band,
            explicit_series=explicit_series,
            average_daily_turnover=average_daily_turnover,
        )
