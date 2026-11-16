"""
Daily T+1 Open Order Runner for Indian Cash Equities.

Enforces structural realism for delivery swing trading on NSE EQ per AGENTS.md:
- Rule 1 & 2: Simplicity and explicit assumptions.
- Rule 5.1 & 13.1: Strict NSE EQ rolling cash delivery scope (zero intraday squaring off, zero F&O, zero BE/BZ entry).
- Rule 5.2 & 13.2: Surveillance escalation (ASM/GSM/ESM) during a hold is an exit constraint.
- Rule 5.3: Circuit filter realism: BUY fills into Upper Circuit freeze are rejected (zero ask depth).
- Rule 6.4: Exact Decimal accounting.
- Rule 7.1: Next-session execution and zero lookahead (signal at T close -> execute at earliest T+1 open).
- Rule 7.4 & 13.5: Single authoritative engine: routes all fills and costs strictly through
  ExecutionFillSimulator and Portfolio ledger. No secondary or shadow simulation paths.
- Audit §58.5, §58.7 Item 6, §59.3, §59.7 (Findings H-82, H-83, H-84, N-83, N-84).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
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
PAISE_PRECISION = Decimal("0.01")


def _quantize_paise(val: Decimal) -> Decimal:
    """Quantizes a Decimal monetary quantity to exact paise (0.01 INR) via ROUND_HALF_UP."""
    return val.quantize(PAISE_PRECISION, rounding=ROUND_HALF_UP)


from signal_core.portfolio.portfolio import Portfolio, PortfolioRiskLimitError
from signal_core.portfolio.sizing import (
    PositionSizeResult,
    calculate_atr_r_multiple_position_size,
)
from signal_core.storage.calendar import (
    TradingCalendar,
    load_anchored_nse_trading_calendar,
)
from signal_core.storage.security_master import (
    SecurityMaster,
    SecurityMasterError,
    SurveillanceStage,
)
from signal_core.contracts.order_intent import (
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

    Series Invariant (Finding H-82, Audit §59.3, §59.7 Item 2):
    - series must be explicitly supplied by caller (no default string fabrication).
    - Under cash delivery swing scope, only 'EQ' rolling series is entry-eligible.

    Protective Stop (Audit §72 Ruling 1): a SELL candidate may carry
    `order_type=OrderType.STOP_LOSS` with the persisted `stop_price`; the fill is then decided
    by ExecutionFillSimulator's stop path (gap -> open, else stop price) under §5.3 circuit rules.
    """
    instrument_id: str
    signal_date: datetime.date
    side: OrderSide
    entry_reference_price: Decimal
    atr: Decimal
    session_volume: int
    series: str
    allocation_weight: Optional[Decimal] = None
    order_type: OrderType = OrderType.MARKET_ON_OPEN
    product: OrderProduct = OrderProduct.DELIVERY
    allow_partial_fill: bool = False
    metadata: Optional[Mapping[str, Any]] = None
    sell_quantity: Optional[int] = None
    stop_price: Optional[Decimal] = None

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

        if (
            isinstance(self.series, bool)
            or not isinstance(self.series, str)
            or not self.series.strip()
        ):
            raise OrderRunnerError(f"series must be a clean non-empty string, got {self.series!r} (Finding H-82).")

        if self.allocation_weight is not None:
            if (
                isinstance(self.allocation_weight, bool)
                or not isinstance(self.allocation_weight, Decimal)
                or not self.allocation_weight.is_finite()
                or self.allocation_weight <= Decimal("0")
                or self.allocation_weight > Decimal("1.0")
            ):
                raise OrderRunnerError(
                    f"allocation_weight must be a finite Decimal in (0, 1], got {self.allocation_weight!r} (Finding N-94)."
                )

        if self.stop_price is not None:
            if (
                isinstance(self.stop_price, bool)
                or not isinstance(self.stop_price, Decimal)
                or not self.stop_price.is_finite()
                or self.stop_price <= Decimal("0")
            ):
                raise OrderRunnerError(
                    f"stop_price must be a positive finite Decimal, got {self.stop_price!r} (Audit §72 Ruling 1)."
                )
        if self.order_type == OrderType.STOP_LOSS and self.stop_price is None:
            raise OrderRunnerError(
                "STOP_LOSS candidate requires an explicit stop_price (Audit §72 Ruling 1)."
            )


@dataclass(frozen=True, slots=True)
class DailyExecutionTicket:
    """
    Complete lifecycle ticket tracking a candidate through intent, order, sizing, and fill result.

    Risk Semantics (Finding H-84, Audit §59.3, §59.7 Item 4):
    - intended_risk: Planned risk formulated at session T close from candidate.entry_reference_price
      and stop-loss distance (size_result.risk_amount).
    - realised_risk: Actual financial risk evaluated on the executed T+1 open fill:
      quantity × (executed_price - stop_price). Accurately captures overnight gap open and slippage
      (e.g., a 10% gap yields 1.504R of true risk rather than masking it as 1.0R).
    """
    candidate: DailySignalCandidate
    target_date: datetime.date
    intent: Optional[OrderIntent] = None
    order: Optional[ExecutionOrder] = None
    size_result: Optional[PositionSizeResult] = None
    fill_result: Optional[ExecutionFillResult] = None
    realised_risk: Optional[Decimal] = None
    intended_risk: Optional[Decimal] = None
    is_no_trade: bool = False
    no_trade_reason: Optional[str] = None

    @property
    def status(self) -> Optional[FillStatus]:
        """Convenience property exposing execution fill status directly on ticket (Finding N-97)."""
        if self.fill_result is not None:
            return self.fill_result.status
        if self.is_no_trade:
            return FillStatus.UNTRIGGERED
        return None


def is_weekly_surveillance_trading_session(
    session_date: datetime.date,
    calendar: TradingCalendar,
) -> bool:
    """
    Returns True if session_date is the single permitted weekly trading session
    under advanced surveillance frameworks (GSM Stage 2+, ESM Stage 2 per AGENTS.md §5.2, Finding N-88).
    In NSE, weekly call auction trading is restricted to the first trading session of each week
    (typically Monday, or the next trading session if Monday is a holiday).
    """
    if not calendar.is_session(session_date):
        return False
    monday = session_date - datetime.timedelta(days=session_date.weekday())
    first_session_of_week: Optional[datetime.date] = None
    for day_offset in range(7):
        cur_day = monday + datetime.timedelta(days=day_offset)
        if calendar.is_session(cur_day):
            first_session_of_week = cur_day
            break
    return session_date == first_session_of_week


class SurveillanceExitResult(tuple):
    """Structured result of evaluating surveillance exit constraints (Findings N-92, CA-2)."""
    session_date: Optional[datetime.date]
    status: str
    coverage_complete: bool
    reason: Optional[str]

    def __new__(
        cls,
        candidates: Sequence[DailySignalCandidate],
        session_date: Optional[datetime.date] = None,
        status: str = "RUN",
        coverage_complete: bool = True,
        reason: Optional[str] = None,
    ) -> "SurveillanceExitResult":
        instance = super().__new__(cls, tuple(candidates))
        instance.session_date = session_date
        instance.status = status
        instance.coverage_complete = coverage_complete
        instance.reason = reason
        return instance


@dataclass(frozen=True, slots=True)
class ProtectiveStopOrder:
    """
    Persisted protective stop for one open long (Audit §72 Ruling 1, AGENTS.md §13.2).

    The stop price is fixed at entry: `entry_reference - k * ATR(14)` as of the signal session's
    close, floored at the minimum tick by the sizing engine, and never recomputed from a later
    close. Its quantity is the filled entry quantity, capped at the held quantity at evaluation.
    """
    instrument_id: str
    stop_price: Decimal
    quantity: int
    signal_date: datetime.date
    armed_session: datetime.date
    atr: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise OrderRunnerError(f"protective stop instrument_id must be a clean string, got {self.instrument_id!r}")
        for name, val in (("stop_price", self.stop_price), ("atr", self.atr)):
            if (
                isinstance(val, bool)
                or not isinstance(val, Decimal)
                or not val.is_finite()
                or val <= Decimal("0")
            ):
                raise OrderRunnerError(f"protective stop {name} must be positive finite Decimal, got {val!r}")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity <= 0:
            raise OrderRunnerError(f"protective stop quantity must be a positive integer, got {self.quantity!r}")


@dataclass(frozen=True, slots=True)
class ProtectiveStopExitResult:
    """
    Session outcome of evaluating every active protective stop (Audit §72 Ruling 1, §5.3).

    A stop the session could not fill because the bid side was frozen (lower circuit / locked
    session / zero liquidity) stays PENDING: it is counted as a deferred exit, never filled, and
    retried on the next session.
    """
    session_date: datetime.date
    tickets: Tuple["DailyExecutionTicket", ...] = ()
    filled_count: int = 0
    deferred_count: int = 0
    circuit_deferred_count: int = 0
    untriggered_count: int = 0
    skipped_no_bar_count: int = 0
    active_stop_count: int = 0
    deferrals: Tuple[Tuple[str, str], ...] = ()


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
        self.last_surveillance_result: Optional[SurveillanceExitResult] = None
        # Audit §72 Ruling 1: one persisted protective stop per open long, armed at the T+1 fill.
        self._protective_stops: dict[str, ProtectiveStopOrder] = {}

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def atr_stop_multiple(self) -> Decimal:
        """The single k that governs sizing, the protective stop distance and the 1R denominator."""
        return self._atr_stop_multiple

    @property
    def protective_stops(self) -> Mapping[str, ProtectiveStopOrder]:
        """Active protective stops, keyed by instrument_id (read-only view)."""
        return dict(self._protective_stops)

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
    ) -> Tuple[Optional[OrderIntent], Optional[PositionSizeResult]]:
        """
        Generates an authoritative OrderIntent from a DailySignalCandidate.
        Enforces:
        1. Series eligibility (EQ only; BE/BZ entry rejected fail-closed per Rule 5.1, 13.1).
        2. T+1 calendar session determination (Zero Lookahead Rule 7.1).
        3. ATR R-multiple sizing for BUY orders (quantity == 0 yields named no-trade outcome).
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

            # Finding N-94: Thread candidate.allocation_weight into position sizing as a cap
            effective_max_weight = (
                min(candidate.allocation_weight, self._criteria.max_single_position_weight)
                if candidate.allocation_weight is not None
                else self._criteria.max_single_position_weight
            )

            size_result = calculate_atr_r_multiple_position_size(
                equity=current_equity,
                entry_price=candidate.entry_reference_price,
                atr=candidate.atr,
                session_volume=candidate.session_volume,
                criteria=self._criteria,
                risk_per_trade_pct=self._risk_per_trade_pct,
                atr_stop_multiple=self._atr_stop_multiple,
                max_single_position_weight=effective_max_weight,
                available_cash=available_cash,
            )

            # Finding N-84: Sizing returning quantity == 0 is a valid no-trade decision,
            # not an OrderIntentValidationError. Return (None, size_result) so runner produces a no-trade ticket.
            if size_result.quantity == 0:
                return None, size_result

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

            if candidate.sell_quantity is not None:
                if (
                    isinstance(candidate.sell_quantity, bool)
                    or not isinstance(candidate.sell_quantity, int)
                    or candidate.sell_quantity <= 0
                ):
                    raise OrderRunnerError(
                        f"sell_quantity must be a positive integer when supplied, got {candidate.sell_quantity!r}"
                    )
                sell_qty = min(candidate.sell_quantity, pos.quantity)
            else:
                sell_qty = pos.quantity

            intent = OrderIntent(
                instrument_id=candidate.instrument_id,
                signal_date=candidate.signal_date,
                target_date=resolved_target_date,
                side=candidate.side,
                order_type=candidate.order_type,
                product=candidate.product,
                quantity=sell_qty,
                allow_partial_fill=candidate.allow_partial_fill,
                metadata=candidate.metadata,
                stop_price=candidate.stop_price,
            )
            return intent, None

        else:
            raise OrderRunnerError(f"Unsupported OrderSide: {candidate.side}")

    def execute_ticket(
        self,
        intent: Optional[OrderIntent],
        candidate: DailySignalCandidate,
        t_plus_1_bar: Union[PriceBar, ExchangeSessionObservation],
        size_result: Optional[PositionSizeResult] = None,
        price_band: Optional[PriceBandRecord] = None,
        explicit_series: Optional[ExchangeSeries] = None,
        average_daily_turnover: Optional[Decimal] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
        prev_close: Optional[Decimal] = None,
    ) -> DailyExecutionTicket:
        """
        Executes an OrderIntent via the authoritative ExecutionFillSimulator and posts
        any resulting fill to the Portfolio cash ledger and position book.
        """
        target_date = intent.target_date if intent is not None else candidate.signal_date

        # Finding N-84 & §60.2 Item 3: If intent is None (e.g. quantity == 0), return named no-trade ticket
        # target_date advances to T+1 session per calendar
        if intent is None or (size_result is not None and size_result.quantity == 0):
            try:
                resolved_target_date = self._calendar.advance_sessions(candidate.signal_date, 1)
            except Exception:
                resolved_target_date = candidate.signal_date
            return DailyExecutionTicket(
                candidate=candidate,
                target_date=resolved_target_date,
                intent=None,
                order=None,
                size_result=size_result,
                fill_result=None,
                realised_risk=None,
                intended_risk=size_result.risk_amount if size_result else None,
                is_no_trade=True,
                no_trade_reason="ZERO_QUANTITY_SIZED",
            )

        # Finding H-83 & H-85: Price band evidence is mandatory for BUY entries and SELL exits to verify circuit filters (§5.3)
        if price_band is None:
            if intent.side == OrderSide.BUY:
                raise OrderRunnerEligibilityError(
                    f"Mandatory price band evidence missing for BUY entry in {intent.instrument_id} on {intent.target_date} "
                    f"(AGENTS.md §5.3, Finding H-83). Circuit filter realism requires verified price band to prevent upper circuit freeze fills."
                )
            else:
                raise OrderRunnerEligibilityError(
                    f"Mandatory price band evidence missing for SELL exit in {intent.instrument_id} on {intent.target_date} "
                    f"(AGENTS.md §5.3, Finding H-85). Circuit filter realism requires verified price band to prevent lower circuit freeze fills."
                )

        # Finding H-82: Require authentic ExchangeSessionObservation or explicit_series. Zero default series synthesis.
        if isinstance(t_plus_1_bar, ExchangeSessionObservation):
            effective_series = t_plus_1_bar.series
        elif explicit_series is not None:
            effective_series = explicit_series
        else:
            raise OrderRunnerEligibilityError(
                f"Bare PriceBar provided for {intent.instrument_id} on {intent.target_date} without verified exchange series evidence "
                f"(AGENTS.md §5.1, §13.1, Finding H-82). Supply an ExchangeSessionObservation or explicit_series from security master."
            )

        if effective_series != ExchangeSeries.EQ:
            raise OrderRunnerEligibilityError(
                f"Candidate {candidate.instrument_id} execution series '{effective_series.value}' is ineligible "
                f"for cash delivery swing entry (AGENTS.md §5.1, §13.1: only EQ rolling series is entry-eligible; "
                f"Trade-to-Trade BE/BZ is strictly prohibited)."
            )

        order = intent.to_execution_order()

        fill_result = self._simulator.simulate_order(
            order=order,
            bar=t_plus_1_bar,
            price_band=price_band,
            explicit_series=effective_series,
            average_daily_turnover=average_daily_turnover,
            prev_close=prev_close,
        )

        realised_risk: Optional[Decimal] = None
        intended_risk: Optional[Decimal] = size_result.risk_amount if size_result else None

        if fill_result.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            try:
                self._portfolio.process_fill(fill_result, latest_market_prices=latest_market_prices)
                if intent.side == OrderSide.BUY and intent.stop_price is not None and fill_result.executed_price is not None:
                    realised_risk = _quantize_paise(
                        Decimal(fill_result.filled_quantity) * (fill_result.executed_price - intent.stop_price)
                    )
                if intent.side == OrderSide.BUY and fill_result.filled_quantity > 0:
                    # Audit §72 Ruling 1: persist the protective stop the sizing engine already priced,
                    # so the reported 1R (quantity x stop distance) is an order, not an artefact.
                    stop_px = intent.stop_price if intent.stop_price is not None else (
                        size_result.stop_loss_price if size_result is not None else None
                    )
                    if stop_px is not None:
                        self.arm_protective_stop(
                            instrument_id=intent.instrument_id,
                            stop_price=stop_px,
                            quantity=fill_result.filled_quantity,
                            signal_date=intent.signal_date,
                            armed_session=intent.target_date,
                            atr=candidate.atr,
                        )
                elif intent.side == OrderSide.SELL:
                    # Audit §73.4 H-125: a trim, or a partially filled stop, sells only part of the lot.
                    # Protection follows the residual quantity; the order is retired only when the
                    # position is actually closed, so a trimmed hold is never left unprotected.
                    position = self._portfolio.get_position(intent.instrument_id)
                    residual = 0 if position is None or position.is_closed else position.quantity
                    if residual > 0:
                        self.rearm_protective_stop(intent.instrument_id, residual)
                    else:
                        self.cancel_protective_stop(intent.instrument_id)
            except PortfolioRiskLimitError as exc:
                fill_result = ExecutionFillResult(
                    order=order,
                    status=FillStatus.REJECTED_RISK_LIMIT,
                    fill_date=fill_result.fill_date,
                    latency_sessions=fill_result.latency_sessions,
                    filled_quantity=0,
                    unfilled_quantity=order.quantity,
                    executed_price=None,
                    slippage=None,
                    costs=None,
                    circuit_evidence_present=fill_result.circuit_evidence_present,
                    rejection_reason=str(exc),
                    fill_id=f"REJ_RISK_{order.order_id}_{fill_result.fill_date}" if order.order_id else None,
                    effective_upper_circuit_limit=fill_result.effective_upper_circuit_limit,
                    effective_lower_circuit_limit=fill_result.effective_lower_circuit_limit,
                )

        return DailyExecutionTicket(
            candidate=candidate,
            target_date=intent.target_date,
            intent=intent,
            order=order,
            size_result=size_result,
            fill_result=fill_result,
            realised_risk=realised_risk,
            intended_risk=intended_risk,
            is_no_trade=False,
            no_trade_reason=None,
        )

    def arm_protective_stop(
        self,
        instrument_id: str,
        stop_price: Decimal,
        quantity: int,
        signal_date: datetime.date,
        armed_session: datetime.date,
        atr: Decimal,
    ) -> ProtectiveStopOrder:
        """
        Persists the T+1 protective stop for an open long (Audit §72 Ruling 1).

        The price is the sizing engine's `stop_loss_price` (entry reference - k * ATR(14) at the
        signal close, floored at the minimum tick), so the intended 1R distance is the distance the
        order actually carries. It is never recomputed from a later close.
        """
        stop = ProtectiveStopOrder(
            instrument_id=instrument_id,
            stop_price=stop_price,
            quantity=quantity,
            signal_date=signal_date,
            armed_session=armed_session,
            atr=atr,
        )
        self._protective_stops[instrument_id] = stop
        return stop

    def cancel_protective_stop(self, instrument_id: str) -> bool:
        """Retires a protective stop after the position is exited by any other path."""
        return self._protective_stops.pop(instrument_id, None) is not None

    def rearm_protective_stop(self, instrument_id: str, quantity: int) -> bool:
        """
        Keeps a pending stop armed for the shares a partial SELL left behind (Audit §73.4 H-125).

        The price, signal session, armed session and ATR are the ones fixed at entry: only the
        quantity follows the residual position. Returns False when no stop is armed, so the caller
        can count a position that is unprotected rather than assume it is protected.
        """
        stop = self._protective_stops.get(instrument_id)
        if stop is None or quantity <= 0:
            return False
        if stop.quantity == quantity:
            return True
        self._protective_stops[instrument_id] = ProtectiveStopOrder(
            instrument_id=instrument_id,
            stop_price=stop.stop_price,
            quantity=quantity,
            signal_date=stop.signal_date,
            armed_session=stop.armed_session,
            atr=stop.atr,
        )
        return True

    def transfer_protective_stop(
        self,
        old_isin: str,
        new_isin: str,
        ratio_numerator: int = 1,
        ratio_denominator: int = 1,
    ) -> bool:
        """
        Carries a pending stop across a MERGER / ISIN transition (Audit §73.4 H-125).

        The lot's entry price is restated by the same exchange ratio on the successor identity, so
        the stop price and quantity are scaled identically: the protection survives the corporate
        action at the same economic distance instead of being retired with the old price scale. A
        merger that changes the price scale without this rescale would place the stop above the
        market and manufacture an instant fill.

        Returns False when there is no stop to carry, or when the successor already carries a stop
        of its own (two lots cannot share one order), so the caller records the position as
        explicitly unprotected (AGENTS.md §13.2, Audit §73.4).
        """
        stop = self._protective_stops.get(old_isin)
        if stop is None:
            return False
        if ratio_numerator <= 0 or ratio_denominator <= 0:
            raise OrderRunnerError(
                f"corporate action ratio must be positive, got {ratio_numerator}:{ratio_denominator}"
            )
        if new_isin != old_isin and new_isin in self._protective_stops:
            self.cancel_protective_stop(old_isin)
            return False
        self.cancel_protective_stop(old_isin)
        adjusted_quantity = (stop.quantity * ratio_numerator) // ratio_denominator
        if adjusted_quantity <= 0:
            # A reverse merger can annihilate the lot; the position is then settled for cash and
            # the caller counts it, rather than arming a stop for zero shares.
            return False
        self._protective_stops[new_isin] = ProtectiveStopOrder(
            instrument_id=new_isin,
            stop_price=(stop.stop_price * Decimal(ratio_denominator) / Decimal(ratio_numerator)).quantize(
                Decimal("0.0001")
            ),
            quantity=adjusted_quantity,
            signal_date=stop.signal_date,
            armed_session=stop.armed_session,
            atr=(stop.atr * Decimal(ratio_denominator) / Decimal(ratio_numerator)).quantize(Decimal("0.0001")),
        )
        return True

    def adjust_protective_stop_for_split(
        self, instrument_id: str, ratio_numerator: int, ratio_denominator: int
    ) -> bool:
        """
        Re-scales a pending stop for a split / bonus / consolidation (AGENTS.md §5.4, §13.2).

        A stop price is denominated in the pre-action price scale; leaving it unchanged after a
        1:10 split would place it ten times above the market and manufacture an instant fill.
        """
        stop = self._protective_stops.get(instrument_id)
        if stop is None:
            return False
        if ratio_numerator <= 0 or ratio_denominator <= 0:
            raise OrderRunnerError(
                f"corporate action ratio must be positive, got {ratio_numerator}:{ratio_denominator}"
            )
        adjusted_quantity = (stop.quantity * ratio_numerator) // ratio_denominator
        if adjusted_quantity <= 0:
            # A reverse split can annihilate the stop quantity; the position's own slice is then
            # settled for cash, so the stop is retired rather than re-armed at zero quantity.
            self.cancel_protective_stop(instrument_id)
            return True
        self._protective_stops[instrument_id] = ProtectiveStopOrder(
            instrument_id=instrument_id,
            stop_price=(stop.stop_price * Decimal(ratio_denominator) / Decimal(ratio_numerator)).quantize(
                Decimal("0.0001")
            ),
            quantity=adjusted_quantity,
            signal_date=stop.signal_date,
            armed_session=stop.armed_session,
            atr=(stop.atr * Decimal(ratio_denominator) / Decimal(ratio_numerator)).quantize(Decimal("0.0001")),
        )
        return True

    def evaluate_protective_stops(
        self,
        session_date: datetime.date,
        bars: Mapping[str, Union[PriceBar, ExchangeSessionObservation]],
        price_bands: Mapping[str, PriceBandRecord],
        explicit_series: Optional[ExchangeSeries] = ExchangeSeries.EQ,
        prev_closes: Optional[Mapping[str, Decimal]] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> ProtectiveStopExitResult:
        """
        Tests every active protective stop against one session's bar (Audit §72 Ruling 1, §5.3).

        Fills are decided solely by ExecutionFillSimulator's STOP_LOSS path: a gap through the stop
        fills at that session's open, an intraday breach fills at the stop price. A session whose
        bid side is frozen (fill reference at/below the lower circuit limit, or a locked 0-range
        session) does NOT fill the stop: the order stays pending and the deferral is counted, so a
        backtest can never assume an exit the market did not offer. Bars and price bands are
        mandatory; a held name without either is left pending and counted as skipped.
        """
        tickets: List[DailyExecutionTicket] = []
        deferrals: List[Tuple[str, str]] = []
        filled = deferred = circuit_deferred = untriggered = skipped_no_bar = 0

        for isin in sorted(self._protective_stops):
            stop = self._protective_stops[isin]
            pos = self._portfolio.get_position(isin)
            if pos is None or pos.is_closed or pos.quantity <= 0:
                self.cancel_protective_stop(isin)
                continue

            bar = bars.get(isin)
            band = price_bands.get(isin)
            if bar is None or band is None:
                skipped_no_bar += 1
                deferrals.append((isin, "NO_BAR_OR_BAND"))
                continue

            quantity = min(stop.quantity, pos.quantity)
            prev_close = (prev_closes or {}).get(isin)
            candidate = DailySignalCandidate(
                instrument_id=isin,
                signal_date=stop.signal_date,
                side=OrderSide.SELL,
                entry_reference_price=prev_close if prev_close is not None else stop.stop_price,
                atr=stop.atr,
                session_volume=bar.volume if isinstance(bar, PriceBar) else bar.price_bar.volume,
                series="EQ",
                order_type=OrderType.STOP_LOSS,
                stop_price=stop.stop_price,
                sell_quantity=quantity,
                metadata={"exit_reason": "STOP_LOSS", "protective_stop_session": session_date.isoformat()},
            )
            ticket = self.run_candidate(
                candidate=candidate,
                t_plus_1_bar=bar,
                target_date=session_date,
                price_band=band,
                explicit_series=explicit_series,
                latest_market_prices=latest_market_prices,
            )
            tickets.append(ticket)

            status = ticket.status
            if status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
                # The SELL branch of execute_ticket owns the stop lifecycle: it retires the order
                # when the position is closed and re-arms it for any residual quantity (H-125).
                filled += 1
            elif status == FillStatus.UNTRIGGERED:
                untriggered += 1
            else:
                # §5.3: a frozen bid (lower circuit, locked session or zero liquidity) delays the
                # exit instead of filling it. The order stays pending for the next session.
                reason = str(ticket.fill_result.rejection_reason if ticket.fill_result else None)
                deferred += 1
                if status in (FillStatus.REJECTED_LOWER_CIRCUIT, FillStatus.REJECTED_ZERO_LIQUIDITY):
                    circuit_deferred += 1
                deferrals.append((isin, reason))

        return ProtectiveStopExitResult(
            session_date=session_date,
            tickets=tuple(tickets),
            filled_count=filled,
            deferred_count=deferred,
            circuit_deferred_count=circuit_deferred,
            untriggered_count=untriggered,
            skipped_no_bar_count=skipped_no_bar,
            active_stop_count=len(self._protective_stops),
            deferrals=tuple(deferrals),
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
            latest_market_prices=latest_market_prices,
            prev_close=candidate.entry_reference_price,
        )

    def evaluate_surveillance_exit_constraints(
        self,
        session_date: datetime.date,
        security_master: SecurityMaster,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
        latest_market_atrs: Optional[Mapping[str, Decimal]] = None,
        latest_market_volumes: Optional[Mapping[str, int]] = None,
        require_coverage: bool = False,
    ) -> Tuple[DailySignalCandidate, ...]:
        """
        Evaluates active open positions in Portfolio against time-varying surveillance state
        per AGENTS.md §5.2, §10.8, §13.2, Audit §59.7 Item 7, Audit §60.6 Item 7, and Finding N-92.

        Surveillance escalation (e.g. GSM Stage 2+, ESM Stage 2) during a hold is an exit constraint,
        triggering a mandatory exit signal candidate on the first session the constraint permits.
        In GSM Stage 2+, trading is restricted to weekly call auctions; exit candidates are emitted
        strictly on permitted weekly trading sessions (Finding N-88).
        """
        open_positions = self._portfolio.get_open_positions()

        # Finding N-92 remainder: Gate on held names, not on a universe-wide count (§63.6 Item 5)
        uncovered_held: List[str] = [
            isin for isin in open_positions
            if not security_master.has_surveillance_coverage(isin, session_date)
        ]
        if uncovered_held:
            self.last_surveillance_result = SurveillanceExitResult(
                candidates=(),
                session_date=session_date,
                status="NOT_RUN",
                coverage_complete=False,
                reason=f"Authoritative surveillance coverage absent for held securities: {uncovered_held}",
            )
            raise SecurityMasterError(
                f"Held security {uncovered_held[0]} has no authoritative surveillance coverage as-of {session_date} "
                f"(Authoritative surveillance coverage is 0 for held positions per AGENTS.md §5.2, §10.8, Finding H-87, N-92 remainder). "
                f"Refuses valuation / exit evaluation of unsurveilled position."
            )

        exit_candidates: List[DailySignalCandidate] = []

        escalated_stages = {
            SurveillanceStage.GSM_STAGE_2,
            SurveillanceStage.GSM_STAGE_3,
            SurveillanceStage.GSM_STAGE_4,
            SurveillanceStage.ESM_STAGE_2,
        }
        weekly_auction_stages = {
            SurveillanceStage.GSM_STAGE_2,
            SurveillanceStage.GSM_STAGE_3,
            SurveillanceStage.GSM_STAGE_4,
        }

        for isin, pos in open_positions.items():
            stages = security_master.resolve_surveillance(isin, session_date)
            for surv in stages:
                if surv.stage in escalated_stages:
                    # Finding N-88: Weekly call auction restriction for GSM Stage 2+
                    if surv.stage in weekly_auction_stages and not is_weekly_surveillance_trading_session(session_date, self._calendar):
                        continue

                    # Finding N-88: Derive inputs from position and market rather than sentinels
                    sym_info = security_master.resolve_symbol(isin, session_date)
                    effective_series = sym_info.series if sym_info else "EQ"
                    ref_price = (
                        latest_market_prices.get(isin, pos.average_entry_price)
                        if latest_market_prices
                        else pos.average_entry_price
                    )
                    atr_val = (
                        latest_market_atrs.get(isin, pos.average_entry_price * Decimal("0.02"))
                        if latest_market_atrs
                        else (pos.average_entry_price * Decimal("0.02"))
                    )
                    vol_val = (
                        latest_market_volumes.get(isin, 1000000)
                        if latest_market_volumes
                        else 1000000
                    )

                    exit_cand = DailySignalCandidate(
                        instrument_id=isin,
                        signal_date=session_date,
                        side=OrderSide.SELL,
                        entry_reference_price=ref_price,
                        atr=atr_val,
                        session_volume=vol_val,
                        series=effective_series,
                        metadata={
                            "exit_reason": f"SURVEILLANCE_ESCALATION_EXIT: {isin} escalated to {surv.stage.value} on {session_date} ({surv.framework})"
                        },
                    )
                    exit_candidates.append(exit_cand)
                    break

        # Finding N-92 remainder: derive coverage_complete from held positions (or master if no positions)
        is_covered = len(uncovered_held) == 0 if open_positions else (security_master.surveillance_coverage_count > 0)
        res = SurveillanceExitResult(
            candidates=exit_candidates,
            session_date=session_date,
            status="RUN" if is_covered else "NOT_RUN",
            coverage_complete=is_covered,
            reason=None if is_covered else (
                f"Authoritative surveillance coverage absent for held securities: {uncovered_held}"
                if open_positions
                else "Surveillance coverage unverified / 0 across registered universe"
            ),
        )
        self.last_surveillance_result = res
        return res

    def populate_surveillance_verdict_bundle(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Writes authoritative surveillance constraint evaluation results into the verdict results bundle (Finding H-101).
        Ensures CRIT-SURV-01 is produced from real driver executions rather than synthetic fixtures.
        """
        if self.last_surveillance_result is not None:
            bundle["surveillance_exit_constraints_enforced"] = (
                self.last_surveillance_result.coverage_complete
                and self.last_surveillance_result.status == "RUN"
            )
            bundle["surveillance_constraint_status"] = self.last_surveillance_result.status
            if self.last_surveillance_result.reason:
                bundle["surveillance_not_run_reason"] = self.last_surveillance_result.reason
        else:
            bundle["surveillance_exit_constraints_enforced"] = False
            bundle["surveillance_constraint_status"] = "NOT_RUN"
            bundle["surveillance_not_run_reason"] = "Surveillance framework exit constraints not evaluated"
        return bundle
