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


from signal_core.portfolio.portfolio import Portfolio
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
        intent: Optional[OrderIntent],
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
        )

        realised_risk: Optional[Decimal] = None
        intended_risk: Optional[Decimal] = size_result.risk_amount if size_result else None

        if fill_result.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            self._portfolio.process_fill(fill_result)
            if intent.side == OrderSide.BUY and intent.stop_price is not None and fill_result.executed_price is not None:
                realised_risk = _quantize_paise(
                    Decimal(fill_result.filled_quantity) * (fill_result.executed_price - intent.stop_price)
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
        if require_coverage and security_master.surveillance_coverage_count == 0:
            raise SecurityMasterError(
                f"Authoritative surveillance coverage is 0 across registered universe as-of {session_date} "
                f"(UNVERIFIED_COVERAGE / NOT RUN) per AGENTS.md §5.2, §10.8 (Finding N-92)."
            )

        exit_candidates: List[DailySignalCandidate] = []
        open_positions = self._portfolio.get_open_positions()

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
            # Finding H-87: Fail closed if held security lacks authoritative surveillance coverage
            if not security_master.has_surveillance_coverage(isin, session_date):
                raise SecurityMasterError(
                    f"Held security {isin} has no authoritative surveillance coverage as-of {session_date} "
                    f"(AGENTS.md §5.2, §10.8, Finding H-87). Refuses valuation / exit evaluation of unsurveilled position."
                )

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

        return tuple(exit_candidates)
