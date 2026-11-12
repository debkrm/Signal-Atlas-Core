"""
Walk-Forward Strategy Execution and Validation Engine.

Implements quantitative walk-forward backtesting per AGENTS.md Rules 5, 6, 7, 8, 9, 10 and Phase 2C:
- Consumes WalkForwardFold sequence from Phase 2A containment (WalkForwardFold).
- Single Authoritative Execution & Accounting Path (Rule 7.4):
  Every trade intent executes through ExecutionFillSimulator and posts to Portfolio / CashLedger.
  Strictly zero shadow simulators or ad-hoc vectorized fill approximations.
- Zero Lookahead Invariant (Gate G2C-2):
  Signals computed at session T close (using information <= T) execute at earliest at session T+1 open.
  Same-session execution (T close -> T fill) or backward-dated intents are strictly rejected fail-closed.
- Series Eligibility Enforcement (Gate G2C-3):
  Strictly respects APPROVED_EQ_ONLY_POLICY. Orders for ineligible series (BE, SM, BZ) fail closed.
- Circuit Evidence Auditing (Gate G2C-4):
  Records whether each execution fill had verified circuit limit depth.
  Fills lacking circuit evidence are flagged CIRCUIT_UNVERIFIED and cannot be promoted to VERIFIED.
- Bit-for-Bit Determinism (Gate G2C-1):
  Identical strategy parameters, dataset content, and fold specifications reproduce bit-for-bit identical results.
- Multi-hypothesis trial registry integration:
  Emits WalkForwardResult capable of direct registration into Phase 2A TrialRegistry.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    ExchangeSessionObservation,
    SeriesEligibilityPolicy,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.slippage import SlippageModel
from signal_core.execution.types import ExecutionOrder, FillStatus, OrderSide
from signal_core.features.engine import InstrumentTechnicalFeatures, SubsegmentIndicatorEngine
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.types import PortfolioSnapshot
from signal_core.research.containment import (
    PartitionRole,
    PartitionSpec,
    WalkForwardFold,
    compute_fold_spec_fingerprint,
)
from signal_core.research.significance import (
    annualized_sharpe,
    sample_kurtosis,
    sample_mean,
    sample_skewness,
    sample_std,
)
from signal_core.research.trials import TrialRecord, TrialRegistry
from signal_core.storage.calendar import TradingCalendar
from signal_core.storage.gold import GoldEngine
from signal_core.strategy.base import (
    LookaheadIntentError,
    OrderIntent,
    OrderIntentValidationError,
    Strategy,
)


class WalkForwardEngineError(ValueError):
    """Base exception for walk-forward execution failures."""
    pass


class WalkForwardLookaheadError(WalkForwardEngineError):
    """Raised when an intent attempts same-session or backward execution in walk-forward engine (Gate G2C-2)."""
    pass


class WalkForwardEligibilityError(WalkForwardEngineError):
    """Raised when an order or fill violates exchange series eligibility (Gate G2C-3)."""
    pass


@dataclass(frozen=True, slots=True)
class FoldExecutionResult:
    """
    Immutable results bundle for a single walk-forward test fold.
    """
    fold: WalkForwardFold
    portfolio_snapshots: Tuple[PortfolioSnapshot, ...]
    trades: Tuple[ExecutionFillResult, ...]
    daily_returns: Tuple[Decimal, ...]
    total_return: Decimal
    annualized_return: Decimal
    annualized_sharpe: Decimal
    max_drawdown: Decimal
    circuit_evidence_complete: bool
    eligibility_policy: str


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """
    Comprehensive multi-fold walk-forward result bundle across disjoint out-of-fold evaluation windows.
    """
    strategy_id: str
    canonical_params: Mapping[str, Any]
    fold_results: Tuple[FoldExecutionResult, ...]
    aggregate_equity_curve: Tuple[Tuple[datetime.date, Decimal], ...]
    aggregate_daily_returns: Tuple[Decimal, ...]
    aggregate_trades: Tuple[ExecutionFillResult, ...]
    initial_capital: Decimal
    final_equity: Decimal
    total_return: Decimal
    annualized_return: Decimal
    annualized_sharpe: Decimal
    max_drawdown: Decimal
    circuit_evidence_complete: bool
    verification_status: str
    fingerprint: str

    def to_trial_record(
        self,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        fold_spec_fingerprint: str,
        dataset_fingerprint: str,
        criteria_version: str,
        partition: Union[str, PartitionRole] = PartitionRole.VALIDATION,
        timestamp_utc: Optional[str] = None,
    ) -> TrialRecord:
        """
        Creates an immutable, fully validated TrialRecord for registration into TrialRegistry.
        """
        ts = timestamp_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()
        returns_list = list(self.aggregate_daily_returns)
        obs_count = len(returns_list)

        if obs_count > 0:
            returns_str = ",".join(str(r) for r in returns_list)
            returns_digest = hashlib.sha256(returns_str.encode("utf-8")).hexdigest()
            m_ret = sample_mean(returns_list)
            s_ret = sample_std(returns_list) if obs_count > 1 else Decimal("0")
            skew = sample_skewness(returns_list) if obs_count > 2 else Decimal("0")
            kurt = sample_kurtosis(returns_list) if obs_count > 3 else Decimal("0")
        else:
            returns_digest = "EMPTY"
            m_ret = Decimal("0")
            s_ret = Decimal("0")
            skew = Decimal("0")
            kurt = Decimal("0")

        # Mock sequence and hash chain for record instance creation
        return TrialRecord(
            seq=1,
            prev_hash="0" * 64,
            record_hash="0" * 64,
            trial_id=trial_id,
            hypothesis=hypothesis,
            rationale=rationale,
            partition=str(partition.value if isinstance(partition, PartitionRole) else partition),
            canonical_params=self.canonical_params,
            fold_spec_fingerprint=fold_spec_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            criteria_version=criteria_version,
            timestamp_utc=ts,
            returns_digest=returns_digest,
            observation_count=obs_count,
            mean_return=m_ret,
            std_return=s_ret,
            skewness=skew,
            kurtosis=kurt,
            sharpe_ratio=self.annualized_sharpe,
            max_drawdown=self.max_drawdown,
        )

    def register_in_trial_registry(
        self,
        registry: TrialRegistry,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        fold_spec_fingerprint: str,
        dataset_fingerprint: str,
        criteria_version: str,
        partition: Union[str, PartitionRole] = PartitionRole.VALIDATION,
        timestamp_utc: Optional[str] = None,
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
    ) -> TrialRecord:
        """
        Registers this walk-forward evaluation directly into an authoritative TrialRegistry.
        """
        ts = timestamp_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()
        returns_list = list(self.aggregate_daily_returns)
        obs_count = len(returns_list)

        if obs_count > 0:
            returns_str = ",".join(str(r) for r in returns_list)
            returns_digest = hashlib.sha256(returns_str.encode("utf-8")).hexdigest()
            m_ret = sample_mean(returns_list)
            s_ret = sample_std(returns_list) if obs_count > 1 else Decimal("0")
            skew = sample_skewness(returns_list) if obs_count > 2 else Decimal("0")
            kurt = sample_kurtosis(returns_list) if obs_count > 3 else Decimal("0")
        else:
            returns_digest = "EMPTY"
            m_ret = Decimal("0")
            s_ret = Decimal("0")
            skew = Decimal("0")
            kurt = Decimal("0")

        return registry.append_trial(
            trial_id=trial_id,
            hypothesis=hypothesis,
            rationale=rationale,
            partition=partition,
            canonical_params=self.canonical_params,
            fold_spec_fingerprint=fold_spec_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            criteria_version=criteria_version,
            timestamp_utc=ts,
            returns_digest=returns_digest,
            observation_count=obs_count,
            mean_return=m_ret,
            std_return=s_ret,
            skewness=skew,
            kurtosis=kurt,
            sharpe_ratio=self.annualized_sharpe,
            max_drawdown=self.max_drawdown,
            partition_spec=partition_spec,
            unlock_file_path=unlock_file_path,
        )


class WalkForwardEngine:
    """
    Authoritative Walk-Forward Simulation and Cross-Validation Engine.
    
    Coordinates:
    - Fold partitioning strictly over trading calendar sessions.
    - Zero lookahead next-session execution (session T close -> session T+1 open).
    - Point-in-time universe selection and technical feature computation.
    - Single execution simulator and single portfolio ledger path (Rule 7.4).
    - Circuit limit depth auditing (Rule 5.3).
    - Eligibility policy compliance (Rule 5.1).
    """

    def __init__(
        self,
        calendar: TradingCalendar,
        gold_engine: GoldEngine,
        criteria: Optional[GoNoGoCriteria] = None,
        cost_model: Optional[TransactionCostModel] = None,
        slippage_model: Optional[SlippageModel] = None,
        eligibility_policy: SeriesEligibilityPolicy = APPROVED_EQ_ONLY_POLICY,
        execution_latency_sessions: int = 1,
    ) -> None:
        self._calendar = calendar
        self._gold_engine = gold_engine
        self._sec_master = gold_engine.security_master
        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._cost_model = cost_model
        self._slippage_model = slippage_model
        self._eligibility_policy = eligibility_policy
        self._latency = execution_latency_sessions

    @property
    def calendar(self) -> TradingCalendar:
        return self._calendar

    @property
    def gold_engine(self) -> GoldEngine:
        return self._gold_engine

    @property
    def criteria(self) -> GoNoGoCriteria:
        return self._criteria

    @property
    def eligibility_policy(self) -> SeriesEligibilityPolicy:
        return self._eligibility_policy

    def run_fold(
        self,
        strategy: Strategy,
        fold: WalkForwardFold,
        initial_capital: Decimal = Decimal("1000000.00"),
        isins: Optional[Sequence[str]] = None,
        fail_on_lookahead: bool = True,
    ) -> FoldExecutionResult:
        """
        Simulates an individual walk-forward test fold out-of-sample.
        """
        # 1. Trading calendar sessions in test window
        test_sessions = self._calendar.sessions_in_range(fold.test_start, fold.test_end)
        if not test_sessions:
            raise WalkForwardEngineError(
                f"No trading sessions in test window [{fold.test_start}, {fold.test_end}]"
            )

        # 2. Pre-load price panel from train_start to test_end for feature lookbacks
        target_isins = tuple(isins) if isins is not None else self._sec_master.registered_isins
        price_panel = self._gold_engine.load_price_panel(
            start_date=fold.train_start,
            end_date=fold.test_end,
            isins=target_isins,
            full_sessions_only=False,
        )

        # 3. Compute technical features for each instrument strictly within subsegments
        all_cal_sessions = self._calendar.sessions_in_range(fold.train_start, fold.test_end)
        features_by_inst_date: Dict[Tuple[str, datetime.date], InstrumentTechnicalFeatures] = {}

        for isin, bars in price_panel.items():
            feat_list = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
                expected_calendar_sessions=all_cal_sessions,
                actual_price_bars=bars,
                fail_closed_on_unexplained=False,
            )
            for f in feat_list:
                features_by_inst_date[(isin, f.trade_date)] = f

        # 4. Optional Strategy Fitting Step (Train Window)
        train_features_by_inst = {
            isin: [
                f for (i, d), f in features_by_inst_date.items()
                if i == isin and fold.train_start <= d <= fold.train_end
            ]
            for isin in target_isins
        }
        train_universe = self._gold_engine.build_point_in_time_universe_schedule(
            fold.train_start, fold.train_end, series_filter="EQ"
        ).get_universe_for_date(fold.train_end)

        strategy.fit(
            train_start=fold.train_start,
            train_end=fold.train_end,
            universe=train_universe,
            features_by_instrument=train_features_by_inst,
        )

        # 5. Initialize Authoritative Engines
        portfolio = Portfolio(
            initial_capital=initial_capital,
            criteria=self._criteria,
            initial_date=fold.test_start,
        )

        simulator = ExecutionFillSimulator(
            criteria=self._criteria,
            cost_model=self._cost_model,
            slippage_model=self._slippage_model,
            eligibility_policy=self._eligibility_policy,
            trading_calendar=self._calendar.sessions,
        )

        # Index price bars by (isin, trade_date)
        bars_by_inst_date: Dict[Tuple[str, datetime.date], PriceBar] = {}
        for isin, bars in price_panel.items():
            for b in bars:
                bars_by_inst_date[(isin, b.trade_date)] = b

        pending_orders: List[ExecutionOrder] = []
        fold_trades: List[ExecutionFillResult] = []
        daily_returns: List[Decimal] = []
        prev_equity = initial_capital

        # 6. Session-by-Session Simulation over Test Window
        for t in test_sessions:
            # --- Step A: Process pending orders targeting session t ---
            orders_today = [o for o in pending_orders if o.target_date == t]
            pending_orders = [o for o in pending_orders if o.target_date > t]

            for ord_req in orders_today:
                bar = bars_by_inst_date.get((ord_req.instrument_id, t))
                if bar is None:
                    # Instrument did not trade today; order rejected for zero liquidity
                    continue

                # Resolve exchange series from Security Master
                sym_interval = self._sec_master.resolve_symbol(ord_req.instrument_id, t)
                raw_series = sym_interval.series if sym_interval else "EQ"
                try:
                    ex_series = ExchangeSeries(raw_series)
                except ValueError:
                    ex_series = ExchangeSeries.UNKNOWN

                # Gate G2C-3: Verify against eligibility policy
                fill_res = simulator.simulate_order(
                    order=ord_req,
                    bar=bar,
                    explicit_series=ex_series,
                )

                fold_trades.append(fill_res)

                if fill_res.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
                    # Gate G2C-3 Assertion: Ineligible series MUST NEVER fill
                    if not self._eligibility_policy.is_eligible(ex_series):
                        raise WalkForwardEligibilityError(
                            f"Gate G2C-3 Violation: Ineligible series {ex_series} produced fill {fill_res.fill_id}."
                        )

                    # Post fill through authoritative single ledger
                    portfolio.process_fill(fill_res, enforce_risk_limits=True)

            # --- Step B: Mark-to-Market Session Valuation ---
            market_prices_today: Dict[str, Decimal] = {}
            for isin in target_isins:
                bar = bars_by_inst_date.get((isin, t))
                if bar is not None:
                    market_prices_today[isin] = bar.close

            # Valuation enforces fail-closed pricing on all open positions
            snap = portfolio.mark_to_market(t, market_prices_today)

            # Exact Decimal daily return calculation
            cur_equity = snap.total_portfolio_value
            day_ret = (cur_equity - prev_equity) / prev_equity
            daily_returns.append(day_ret)
            prev_equity = cur_equity

            # --- Step C: Formulate next-session trade intents (t -> t+1) ---
            if t < test_sessions[-1]:
                next_session = self._calendar.next_session(t)

                # Point-in-time universe as-of session t
                univ_sched = self._gold_engine.build_point_in_time_universe_schedule(t, t, series_filter="EQ")
                active_universe_t = univ_sched.get_universe_for_date(t)

                # Pass features observable strictly <= t
                features_at_t = {
                    isin: features_by_inst_date.get((isin, t))
                    for isin in active_universe_t
                    if (isin, t) in features_by_inst_date
                }

                intents = strategy.generate_signals(
                    as_of=t,
                    next_session=next_session,
                    universe=active_universe_t,
                    features=features_at_t,
                )

                for intent in intents:
                    # Gate G2C-2 Verification: Reject same-session or backward lookahead intents
                    if intent.signal_date != t or intent.target_date <= t:
                        if fail_on_lookahead:
                            raise WalkForwardLookaheadError(
                                f"Gate G2C-2 Violation: Attempted lookahead intent with signal_date={intent.signal_date}, "
                                f"target_date={intent.target_date} on session {t}. Same-session execution is strictly prohibited."
                            )
                        continue

                    # Sizing calculation
                    computed_qty = intent.quantity
                    if computed_qty is None and intent.target_weight is not None:
                        close_p = market_prices_today.get(intent.instrument_id)
                        if close_p and close_p > Decimal("0"):
                            if intent.side == OrderSide.BUY:
                                desired_capital = snap.total_portfolio_value * intent.target_weight
                                computed_qty = int(desired_capital / close_p)
                            else:
                                pos = portfolio.get_position(intent.instrument_id)
                                computed_qty = pos.quantity if pos and not pos.is_closed else 0
                        else:
                            computed_qty = 0

                    if computed_qty and computed_qty > 0:
                        exec_ord = intent.to_execution_order(
                            computed_quantity=computed_qty,
                            order_id=f"ORD_{intent.instrument_id}_{intent.target_date.isoformat()}#{len(pending_orders)+1}",
                        )
                        pending_orders.append(exec_ord)

        # 7. Compute Fold Metrics
        final_equity = portfolio.snapshots[-1].total_portfolio_value if portfolio.snapshots else initial_capital
        total_ret = (final_equity - initial_capital) / initial_capital

        # Annualized return and Sharpe
        ann_sharpe = annualized_sharpe(daily_returns) if len(daily_returns) > 1 else Decimal("0")
        obs_sessions = len(test_sessions)
        ann_factor = Decimal("252") / Decimal(obs_sessions) if obs_sessions > 0 else Decimal("1")
        ann_ret = total_ret * ann_factor

        # Circuit evidence audit (Gate G2C-4)
        executed_fills = [f for f in fold_trades if f.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED)]
        circuit_complete = all(f.circuit_evidence_present for f in executed_fills) if executed_fills else True

        return FoldExecutionResult(
            fold=fold,
            portfolio_snapshots=portfolio.snapshots,
            trades=tuple(fold_trades),
            daily_returns=tuple(daily_returns),
            total_return=total_ret,
            annualized_return=ann_ret,
            annualized_sharpe=ann_sharpe,
            max_drawdown=portfolio.max_drawdown,
            circuit_evidence_complete=circuit_complete,
            eligibility_policy=",".join(sorted(s.value for s in self._eligibility_policy.permitted_series)),
        )

    def run_walk_forward(
        self,
        strategy: Strategy,
        folds: Sequence[WalkForwardFold],
        initial_capital: Decimal = Decimal("1000000.00"),
        isins: Optional[Sequence[str]] = None,
        dataset_content_fingerprint: str = "DATA-CTNT-V2-UNKNOWN",
        fail_on_lookahead: bool = True,
    ) -> WalkForwardResult:
        """
        Runs comprehensive walk-forward validation across all provided folds.
        Emits WalkForwardResult bundle with aggregate metrics and deterministic fingerprint (Gate G2C-1).
        """
        if not folds:
            raise WalkForwardEngineError("Cannot run walk-forward backtest with empty folds sequence.")

        fold_results: List[FoldExecutionResult] = []
        agg_daily_returns: List[Decimal] = []
        agg_trades: List[ExecutionFillResult] = []
        agg_equity_curve: List[Tuple[datetime.date, Decimal]] = []

        compounded_equity = initial_capital

        for fold in folds:
            f_res = self.run_fold(
                strategy=strategy,
                fold=fold,
                initial_capital=initial_capital,
                isins=isins,
                fail_on_lookahead=fail_on_lookahead,
            )
            fold_results.append(f_res)
            agg_trades.extend(f_res.trades)

            # Stitch out-of-fold daily returns into aggregate return stream
            for ret, snap in zip(f_res.daily_returns, f_res.portfolio_snapshots):
                agg_daily_returns.append(ret)
                compounded_equity *= (Decimal("1") + ret)
                agg_equity_curve.append((snap.as_of_date, compounded_equity))

        # Global aggregate metrics
        total_ret = (compounded_equity - initial_capital) / initial_capital if initial_capital > 0 else Decimal("0")
        total_sessions = len(agg_daily_returns)
        ann_factor = Decimal("252") / Decimal(total_sessions) if total_sessions > 0 else Decimal("1")
        ann_ret = total_ret * ann_factor
        agg_sharpe = annualized_sharpe(agg_daily_returns) if len(agg_daily_returns) > 1 else Decimal("0")

        # Global peak and drawdown
        peak = initial_capital
        max_dd = Decimal("0")
        for _, eq in agg_equity_curve:
            if eq > peak:
                peak = eq
            if peak > Decimal("0"):
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd

        # Circuit evidence audit across all folds (Gate G2C-4)
        circuit_complete = all(f.circuit_evidence_complete for f in fold_results)
        verif_status = "VERIFIED" if circuit_complete else "CIRCUIT_UNVERIFIED"

        # Deterministic Result Fingerprint (Gate G2C-1)
        fold_spec_fpr = compute_fold_spec_fingerprint(folds)
        canon_params = strategy.parameters

        hasher = hashlib.sha256()
        hasher.update(strategy.strategy_id.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(json.dumps(canon_params, sort_keys=True).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(fold_spec_fpr.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(dataset_content_fingerprint.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(initial_capital).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(compounded_equity).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(agg_sharpe).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(len(agg_trades)).encode("utf-8"))

        digest = hasher.hexdigest()
        result_fpr = f"WF-RES-V1-{digest}"

        return WalkForwardResult(
            strategy_id=strategy.strategy_id,
            canonical_params=canon_params,
            fold_results=tuple(fold_results),
            aggregate_equity_curve=tuple(agg_equity_curve),
            aggregate_daily_returns=tuple(agg_daily_returns),
            aggregate_trades=tuple(agg_trades),
            initial_capital=initial_capital,
            final_equity=compounded_equity,
            total_return=total_ret,
            annualized_return=ann_ret,
            annualized_sharpe=agg_sharpe,
            max_drawdown=max_dd,
            circuit_evidence_complete=circuit_complete,
            verification_status=verif_status,
            fingerprint=result_fpr,
        )
