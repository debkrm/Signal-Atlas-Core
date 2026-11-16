"""
Delivery Swing Trading Strategy and Execution Harness for Indian Cash Equities.

Enforces:
- Rule 1 & 2: Minimum complexity, explicit parameter definitions.
- Rule 5.1 & 13.1: Strict NSE EQ rolling cash delivery scope (zero intraday, zero F&O, zero BE/BZ entry).
- Rule 7.1: Zero lookahead next-session execution (signals formulated at T close execute at T+1 open).
- Rule 7.4 & 13.5: Single authoritative execution path: strategy intents are wired via
  execute_swing_strategy_session into ATR R-multiple sizing and DailyTPlus1OrderRunner,
  executing strictly via ExecutionFillSimulator and Portfolio ledger (Findings N-89, §60.6 Item 8).
- Phase 3B-2a & 3B-2b integration (Audit §59.7 Item 8, §60.6 Item 8).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal, ROUND_CEILING
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union, TYPE_CHECKING

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.exchange_series import APPROVED_EQ_ONLY_POLICY, ExchangeSeries, ExchangeSessionObservation
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.types import FillStatus, OrderProduct, OrderSide, OrderType
from signal_core.storage.security_master import SecurityMasterError
from signal_core.strategy.base import OrderIntent, Strategy

if TYPE_CHECKING:
    from signal_core.execution.order_runner import (
        DailyExecutionTicket,
        DailySignalCandidate,
        DailyTPlus1OrderRunner,
    )


class DeliverySwingTrendStrategy(Strategy):
    """
    Reference Delivery Swing Trend Following Strategy on NSE EQ cash equities.

    Generates:
    - BUY intents at session T close when close > moving average and technical trend filters confirm.
    - SELL intents at session T close when close drops below trailing stop / exit moving average.
    - Strictly targets session T+1 open (next-session execution, Rule 7.1).
    - Exposes immutable parameters for canonical trial registry registration prior to metric reading.
    - Wired into execution via execute_swing_strategy_session (Finding N-89).
    """

    def __init__(
        self,
        strategy_id: str = "SWING-TREND-EQ-V1",
        fast_indicator: str = "sma_20",
        slow_indicator: str = "sma_50",
        allocation_weight: Optional[Decimal] = None,
        atr_stop_multiple: Decimal = Decimal("2.0"),
        max_position_weight_trim_threshold: Optional[Decimal] = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._fast_indicator = fast_indicator
        self._slow_indicator = slow_indicator
        self._atr_stop_multiple = atr_stop_multiple

        # Trial #4 (Finding H-114 scope, §66.5 Condition 1): optional automated winner
        # concentration trim. None (the default) leaves the certified baseline behaviour untouched.
        if max_position_weight_trim_threshold is not None:
            if (
                isinstance(max_position_weight_trim_threshold, bool)
                or not isinstance(max_position_weight_trim_threshold, Decimal)
                or not max_position_weight_trim_threshold.is_finite()
                or max_position_weight_trim_threshold <= Decimal("0")
                or max_position_weight_trim_threshold > Decimal("1")
            ):
                raise ValueError(
                    f"max_position_weight_trim_threshold must be a finite Decimal in (0, 1], "
                    f"got {max_position_weight_trim_threshold!r}"
                )
        self._max_position_weight_trim_threshold = max_position_weight_trim_threshold

        if allocation_weight is not None:
            self._allocation_weight = allocation_weight
        else:
            criteria = load_go_no_go_criteria()
            self._allocation_weight = criteria.max_single_position_weight * Decimal("0.80")

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Canonical dictionary of strategy parameters for TrialRegistry recording."""
        return {
            "strategy_id": self._strategy_id,
            "fast_indicator": self._fast_indicator,
            "slow_indicator": self._slow_indicator,
            "allocation_weight": str(self._allocation_weight),
            "atr_stop_multiple": str(self._atr_stop_multiple),
            "max_position_weight_trim_threshold": str(self._max_position_weight_trim_threshold),
            "policy": "APPROVED_EQ_ONLY_POLICY",
        }

    def generate_signals(
        self,
        as_of: datetime.date,
        next_session: datetime.date,
        universe: Sequence[str],
        features: Mapping[str, Any],
        portfolio: Optional[Any] = None,
        latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    ) -> Tuple[OrderIntent, ...]:
        """
        Formulates trade intents at session as_of (T close) for execution at next_session (T+1).
        Respects APPROVED_EQ_ONLY_POLICY: only generates intents for instruments present in universe.
        When max_position_weight_trim_threshold is configured and a portfolio is supplied, emits a
        partial T+1 SELL trim for any position whose mark-to-market weight exceeds the threshold,
        reducing it to the strategy allocation weight (§13.2, CRIT-STAT-03).
        """
        intents: list[OrderIntent] = []

        for isin in sorted(universe):
            inst_features = features.get(isin)
            if inst_features is None:
                continue

            fast_val = getattr(inst_features, self._fast_indicator, None)
            slow_val = getattr(inst_features, self._slow_indicator, None)
            close = getattr(inst_features, "close", None)

            if fast_val is None or slow_val is None or close is None:
                continue

            if close > fast_val and fast_val > slow_val:
                intents.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"SWING_BUY_{isin}_{as_of.isoformat()}",
                    )
                )
            elif close < slow_val:
                intents.append(
                    OrderIntent(
                        instrument_id=isin,
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET_ON_OPEN,
                        product=OrderProduct.DELIVERY,
                        target_weight=self._allocation_weight,
                        intent_id=f"SWING_SELL_{isin}_{as_of.isoformat()}",
                    )
                )

        # Automated winner concentration trim (Trial #4). Only an open position already inside the
        # point-in-time universe is trimmed, and a full exit intent for the same ISIN takes precedence.
        if self._max_position_weight_trim_threshold is not None and portfolio is not None:
            equity = portfolio.current_total_equity(latest_market_prices)
            exiting_isins = {i.instrument_id for i in intents if i.side == OrderSide.SELL}
            if equity > Decimal("0"):
                for isin in sorted(universe):
                    if isin in exiting_isins:
                        continue
                    pos = portfolio.get_position(isin)
                    if pos is None or pos.is_closed or pos.quantity <= 0:
                        continue
                    mark = None
                    if latest_market_prices is not None:
                        mark = latest_market_prices.get(isin)
                    if mark is None:
                        mark = getattr(features.get(isin), "close", None)
                    if mark is None:
                        continue
                    mark = Decimal(str(mark))
                    if mark <= Decimal("0"):
                        continue
                    current_value = mark * Decimal(pos.quantity)
                    if (current_value / equity) <= self._max_position_weight_trim_threshold:
                        continue
                    target_value = equity * self._allocation_weight
                    excess_value = current_value - target_value
                    if excess_value <= Decimal("0"):
                        continue
                    trim_qty = int((excess_value / mark).to_integral_value(rounding=ROUND_CEILING))
                    trim_qty = min(trim_qty, pos.quantity)
                    if trim_qty <= 0:
                        continue
                    intents.append(
                        OrderIntent(
                            instrument_id=isin,
                            signal_date=as_of,
                            target_date=next_session,
                            side=OrderSide.SELL,
                            order_type=OrderType.MARKET_ON_OPEN,
                            product=OrderProduct.DELIVERY,
                            quantity=trim_qty,
                            intent_id=f"SWING_TRIM_{isin}_{as_of.isoformat()}",
                            metadata={"trim_reason": "MAX_POSITION_WEIGHT"},
                        )
                    )

        return tuple(intents)


@dataclass(frozen=True, slots=True)
class SwingSessionExecutionSummary:
    """
    Structured summary of a swing strategy session execution run (Findings N-93, N-97).
    Separates emitted tickets, fills, and rejections so frozen circuit sessions never
    overstate executed fills per AGENTS.md §5.3.
    """
    as_of: datetime.date
    next_session: datetime.date
    intents_generated: int
    tickets_emitted: int
    tickets_filled: int
    tickets_rejected: int
    tickets_executed: int  # reflects tickets_filled for backwards compatibility
    skipped_missing_bar: int
    skipped_missing_band: int
    skipped_unheld_sell: int
    tickets_no_trade: int = 0
    skipped_already_held: int = 0
    skipped_missing_features: int = 0
    tickets: Tuple[DailyExecutionTicket, ...] = ()
    corporate_action_entries: Tuple[Any, ...] = ()
    surveillance_result: Optional[Any] = None

    def __len__(self) -> int:
        return len(self.tickets)

    def __getitem__(self, index: int) -> DailyExecutionTicket:
        return self.tickets[index]

    def __iter__(self):
        return iter(self.tickets)

    def to_verdict_results_bundle(
        self,
        runner: Optional[Any] = None,
        extra_metrics: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Exports session execution summary into an authoritative results bundle for evaluate_verdicts()
        per AGENTS.md §9.1, §9.3, §10.8, Findings CA-2, H-101, H-104.
        Pure telemetry: zero hardcoded literals; all metrics flow from executed state or extra_metrics.
        """
        bundle: Dict[str, Any] = {}
        surv = self.surveillance_result or (getattr(runner, "last_surveillance_result", None) if runner else None)
        if surv is not None:
            bundle["surveillance_exit_constraints_enforced"] = (
                bool(surv.coverage_complete) and surv.status == "RUN"
            )
            bundle["surveillance_constraint_status"] = surv.status
            if surv.reason:
                bundle["surveillance_not_run_reason"] = surv.reason
        else:
            bundle["surveillance_exit_constraints_enforced"] = False
            bundle["surveillance_constraint_status"] = "NOT_RUN"
            bundle["surveillance_not_run_reason"] = "Surveillance framework exit constraints not evaluated"

        if extra_metrics:
            bundle.update(extra_metrics)
        return bundle


def execute_swing_strategy_session(
    strategy: DeliverySwingTrendStrategy,
    runner: DailyTPlus1OrderRunner,
    as_of: datetime.date,
    next_session: datetime.date,
    universe: Sequence[str],
    features: Mapping[str, Any],
    bars_next_session: Mapping[str, Union[PriceBar, ExchangeSessionObservation]],
    price_bands_next_session: Mapping[str, PriceBandRecord],
    explicit_series: Optional[ExchangeSeries] = ExchangeSeries.EQ,
    latest_market_prices: Optional[Mapping[str, Decimal]] = None,
    corporate_actions: Optional[Sequence[Any]] = None,
    security_master: Optional[Any] = None,
    price_convention: Optional[PriceConvention] = None,
) -> SwingSessionExecutionSummary:
    """
    Authoritative execution harness that routes DeliverySwingTrendStrategy signals through
    ATR R-multiple sizing into DailyTPlus1OrderRunner (Findings N-89, N-93, N-94, H-100, H-101, §60.6, §61.6).

    Enforces:
    - Zero Lookahead: signal date as_of -> next_session execution (Rule 7.1).
    - Cash delivery swing scope: only held positions can emit SELL intents; naked shorting prohibited.
    - BUY intents are sized with positive integer quantities through ATR R-multiple sizing,
      capped by strategy allocation_weight and criteria max_single_position_weight (Finding N-94).
    - Corporate actions on open positions applied before session execution (Finding H-100).
    - Time-varying surveillance exit constraints evaluated on held positions (Finding H-101).
    - Returns structured SwingSessionExecutionSummary recording all generated intents,
      executed tickets, and explicit skip reasons (Finding N-93).
    - Fills and ledger updates flow strictly through the single authoritative
      ExecutionFillSimulator and Portfolio ledger (Rule 7.4 & 13.5).
    """
    from signal_core.execution.order_runner import DailySignalCandidate

    # Finding H-100 & H-108: Apply corporate actions for next_session before session trading
    ca_entries: List[Any] = []
    if corporate_actions:
        applied = runner.portfolio.apply_corporate_actions_for_session(
            next_session, corporate_actions, price_convention=price_convention
        )
        ca_entries.extend(applied)

    # Finding H-101 & N-103: Evaluate surveillance exit constraints if security_master provided
    surv_result = None
    if security_master is not None:
        try:
            surv_result = runner.evaluate_surveillance_exit_constraints(
                session_date=next_session,
                security_master=security_master,
                latest_market_prices=latest_market_prices,
            )
        except SecurityMasterError:
            surv_result = runner.last_surveillance_result

    raw_intents = strategy.generate_signals(
        as_of=as_of,
        next_session=next_session,
        universe=universe,
        features=features,
        portfolio=runner.portfolio,
        latest_market_prices=latest_market_prices,
    )

    tickets: List[DailyExecutionTicket] = []
    skipped_missing_bar = 0
    skipped_missing_band = 0
    skipped_unheld_sell = 0
    skipped_already_held = 0
    skipped_missing_features = 0

    for intent in raw_intents:
        isin = intent.instrument_id
        pos = runner.portfolio.get_position(isin)

        # Cash delivery constraint: SELL intent is only permitted if position is currently held
        if intent.side == OrderSide.SELL:
            if pos is None or pos.is_closed or pos.quantity <= 0:
                skipped_unheld_sell += 1
                continue

        # Avoid redundant BUY if already holding an open position in this security
        if intent.side == OrderSide.BUY:
            if pos is not None and not pos.is_closed and pos.quantity > 0:
                skipped_already_held += 1
                continue

        inst_features = features.get(isin)
        if inst_features is None:
            skipped_missing_features += 1
            continue

        close_val = getattr(inst_features, "close", None)
        atr_val = getattr(inst_features, "atr", None) or getattr(inst_features, "atr_14", None)
        vol_val = getattr(inst_features, "volume", None)

        if close_val is None:
            skipped_missing_features += 1
            continue
        entry_price = Decimal(str(close_val))
        atr_dec = Decimal(str(atr_val)) if atr_val is not None else (entry_price * Decimal("0.02"))
        vol_int = int(vol_val) if vol_val is not None else 1000000

        # Finding N-94: Pass strategy allocation_weight to candidate so sizing enforces declared parameter cap
        alloc_weight = (
            getattr(intent, "target_weight", None)
            or getattr(intent, "allocation_weight", None)
            or getattr(strategy, "_allocation_weight", None)
        )

        cand = DailySignalCandidate(
            instrument_id=isin,
            signal_date=as_of,
            side=intent.side,
            entry_reference_price=entry_price,
            atr=atr_dec,
            session_volume=vol_int,
            series="EQ",
            allocation_weight=alloc_weight,
            metadata={"intent_id": intent.intent_id},
            sell_quantity=intent.quantity if intent.side == OrderSide.SELL else None,
        )

        t_plus_1_bar = bars_next_session.get(isin)
        price_band = price_bands_next_session.get(isin)

        # Finding N-93: Explicitly count missing bar vs missing band skips rather than silent continue
        if t_plus_1_bar is None:
            skipped_missing_bar += 1
            continue
        if price_band is None:
            skipped_missing_band += 1
            continue

        ticket = runner.run_candidate(
            candidate=cand,
            t_plus_1_bar=t_plus_1_bar,
            target_date=next_session,
            price_band=price_band,
            explicit_series=explicit_series,
            latest_market_prices=latest_market_prices,
        )
        tickets.append(ticket)

    tickets_emitted = len(tickets)
    tickets_filled = sum(
        1 for t in tickets
        if t.fill_result is not None and t.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED)
    )
    tickets_rejected = sum(
        1 for t in tickets
        if str(t.status.value if hasattr(t.status, "value") else t.status).startswith("REJECTED_")
    )
    tickets_no_trade = sum(
        1 for t in tickets
        if getattr(t, "is_no_trade", False) or t.status == FillStatus.UNTRIGGERED
    )

    return SwingSessionExecutionSummary(
        as_of=as_of,
        next_session=next_session,
        intents_generated=len(raw_intents),
        tickets_emitted=tickets_emitted,
        tickets_filled=tickets_filled,
        tickets_rejected=tickets_rejected,
        tickets_executed=tickets_filled,
        skipped_missing_bar=skipped_missing_bar,
        skipped_missing_band=skipped_missing_band,
        skipped_unheld_sell=skipped_unheld_sell,
        tickets_no_trade=tickets_no_trade,
        skipped_already_held=skipped_already_held,
        skipped_missing_features=skipped_missing_features,
        tickets=tuple(tickets),
        corporate_action_entries=tuple(ca_entries),
        surveillance_result=surv_result or runner.last_surveillance_result,
    )
