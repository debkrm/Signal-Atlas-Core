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

from dataclasses import dataclass, field
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from signal_core.contracts.criteria import (
    GoNoGoCriteria,
    compute_criteria_fingerprint,
    load_go_no_go_criteria,
)
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
from signal_core.portfolio.portfolio import Portfolio, PortfolioRiskLimitError
from signal_core.portfolio.types import PortfolioSnapshot
from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    PartitionSpecValidationError,
    WalkForwardFold,
    check_partition_access,
    compute_fold_spec_fingerprint,
    load_canonical_partition_spec,
)
from signal_core.research.significance import (
    annualized_sharpe,
    sample_kurtosis,
    sample_mean,
    sample_skewness,
    sample_std,
)
from signal_core.research.trials import TrialRecord, TrialRegistry
from signal_core.storage.calendar import CalendarError, TradingCalendar
from signal_core.storage.gold import GoldEngine
from signal_core.storage.silver import CANONICAL_HOLDOUT_END_DATE, CANONICAL_HOLDOUT_START_DATE
from signal_core.strategy.base import (
    LookaheadIntentError,
    OrderIntent,
    OrderIntentValidationError,
    Strategy,
)


def compute_compounded_annualized_return(
    total_return: Decimal,
    session_count: int,
    sessions_per_year: int = 250,
) -> Decimal:
    """
    Computes geometric compounded annualized return (CAGR) per AGENTS.md Rule 6.4 and Audit §25 G-7:
    CAGR = (1 + total_return)^(sessions_per_year / session_count) - 1.
    Evaluated in exact Decimal arithmetic via exp( (q / N) * ln(1 + R) ) - 1.
    """
    if session_count <= 0 or total_return == Decimal("0"):
        return Decimal("0.00")
    if total_return <= Decimal("-1.0"):
        return Decimal("-1.00")
    one_plus_r = Decimal("1") + total_return
    ann_factor = Decimal(sessions_per_year) / Decimal(session_count)
    return (ann_factor * one_plus_r.ln()).exp() - Decimal("1")


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
    dataset_content_fingerprint: str
    execution_config: Mapping[str, Any] = field(default_factory=dict)
    criteria_version: str = ""

    def to_trial_record(
        self,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        fold_spec_fingerprint: str,
        dataset_fingerprint: Optional[str] = None,
        criteria_version: Optional[str] = None,
        partition: Union[str, PartitionRole] = PartitionRole.VALIDATION,
        timestamp_utc: Optional[str] = None,
        execution_config: Optional[Mapping[str, Any]] = None,
    ) -> TrialRecord:
        """
        Creates an immutable, fully validated TrialRecord for registration into TrialRegistry.
        Binds dataset_fingerprint to authentic DATA-CTNT-V2 snapshot (Gate G-4).
        Defaults criteria_version from criteria in force (Audit §31 H-34).
        Carries execution_config onto TrialRecord (Audit §31 H-33 / §32 H-37).
        """
        # Audit §31 H-30: Refuse trial record creation if circuit evidence is unverified
        if self.verification_status == "CIRCUIT_UNVERIFIED":
            raise WalkForwardEngineError(
                "Cannot create trial record with verification_status='CIRCUIT_UNVERIFIED' (Finding H-30). "
                "Every trade must execute with verified exchange price band evidence before publishing performance."
            )

        # Invariant N-32 / N-35: Refuse trial record creation if any fold preceded min_binding_evaluation_start_date
        # Judge by execution_config carried on the result or criteria in force during the run (Finding N-35).
        min_start_str = self.execution_config.get("min_binding_evaluation_start_date")
        if min_start_str:
            min_start = datetime.date.fromisoformat(str(min_start_str))
        else:
            criteria = load_go_no_go_criteria()
            if self.criteria_version and criteria.version != self.criteria_version:
                raise WalkForwardEngineError(
                    f"Cannot create trial record: current criteria version '{criteria.version}' "
                    f"differs from criteria version '{self.criteria_version}' in force during the run (Finding N-35)."
                )
            min_start = criteria.min_binding_evaluation_start_date

        for f_res in self.fold_results:
            earliest = min(f_res.fold.train_start, f_res.fold.test_start)
            if earliest < min_start:
                raise WalkForwardEngineError(
                    f"Cannot create trial record for fold evaluated on {earliest}, which precedes "
                    f"the minimum binding evaluation start date ({min_start}) declared in criteria (Finding N-32, N-35)."
                )

        # Audit §31 H-28 / §32 H-35: Dataset fingerprint cannot be overridden with spoofed or mismatched value
        if dataset_fingerprint is not None and dataset_fingerprint != self.dataset_content_fingerprint:
            raise WalkForwardEngineError(
                f"Supplied dataset_fingerprint '{dataset_fingerprint}' does not match authentic WalkForwardResult "
                f"dataset_content_fingerprint '{self.dataset_content_fingerprint}' (Gate G-4 / H-35)."
            )
        ds_fpr = self.dataset_content_fingerprint
        if not isinstance(ds_fpr, str) or not ds_fpr.startswith("DATA-CTNT-V2-") or ds_fpr == "DATA-CTNT-V2-UNKNOWN":
            raise WalkForwardEngineError(
                f"Cannot create TrialRecord with invalid dataset_fingerprint {ds_fpr!r}. "
                "Must be a genuine DATA-CTNT-V2 content fingerprint; 'UNKNOWN' prohibited (Gate G-4)."
            )

        # Audit §33 H-38: criteria version and execution config are computed from the run, not typed
        if criteria_version is not None and criteria_version != self.criteria_version:
            raise WalkForwardEngineError(
                f"Supplied criteria_version '{criteria_version}' does not match the criteria in force "
                f"'{self.criteria_version}' that judged this run (Audit §33 H-38)."
            )
        resolved_criteria_version = self.criteria_version
        if not resolved_criteria_version:
            raise WalkForwardEngineError("criteria_version cannot be empty. Must be provided or present on WalkForwardResult.")
        if execution_config is not None and dict(execution_config) != dict(self.execution_config):
            raise WalkForwardEngineError(
                "Supplied execution_config does not match the execution configuration that produced this "
                "result (Audit §33 H-38)."
            )
        resolved_exec_config = self.execution_config

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
            dataset_fingerprint=ds_fpr,
            criteria_version=resolved_criteria_version,
            timestamp_utc=ts,
            returns_digest=returns_digest,
            observation_count=obs_count,
            mean_return=m_ret,
            std_return=s_ret,
            skewness=skew,
            kurtosis=kurt,
            sharpe_ratio=self.annualized_sharpe,
            max_drawdown=self.max_drawdown,
            execution_config=resolved_exec_config,
        )

    def register_in_trial_registry(
        self,
        registry: TrialRegistry,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        fold_spec_fingerprint: str,
        dataset_fingerprint: Optional[str] = None,
        criteria_version: Optional[str] = None,
        partition: Union[str, PartitionRole] = PartitionRole.VALIDATION,
        timestamp_utc: Optional[str] = None,
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
        execution_config: Optional[Mapping[str, Any]] = None,
    ) -> TrialRecord:
        """
        Registers this walk-forward evaluation directly into an authoritative TrialRegistry.
        Binds dataset_fingerprint to authentic DATA-CTNT-V2 snapshot (Gate G-4).
        Defaults criteria_version from criteria in force (Audit §31 H-34).
        Carries execution_config onto TrialRecord (Audit §31 H-33).
        """
        # Audit §31 H-30: Refuse trial registration if circuit evidence is unverified
        if self.verification_status == "CIRCUIT_UNVERIFIED":
            raise WalkForwardEngineError(
                "Cannot register trial in trial registry with verification_status='CIRCUIT_UNVERIFIED' (Finding H-30). "
                "Every trade must execute with verified exchange price band evidence before publishing performance."
            )

        # Audit §31 H-28 / §32 H-35: Dataset fingerprint cannot be overridden with spoofed or mismatched value
        if dataset_fingerprint is not None and dataset_fingerprint != self.dataset_content_fingerprint:
            raise WalkForwardEngineError(
                f"Supplied dataset_fingerprint '{dataset_fingerprint}' does not match authentic WalkForwardResult "
                f"dataset_content_fingerprint '{self.dataset_content_fingerprint}' (Gate G-4 / H-35)."
            )
        ds_fpr = self.dataset_content_fingerprint
        if not isinstance(ds_fpr, str) or not ds_fpr.startswith("DATA-CTNT-V2-") or ds_fpr == "DATA-CTNT-V2-UNKNOWN":
            raise WalkForwardEngineError(
                f"Cannot register trial with invalid dataset_fingerprint {ds_fpr!r}. "
                "Must be a genuine DATA-CTNT-V2 content fingerprint; 'UNKNOWN' prohibited (Gate G-4)."
            )

        # Audit §33 H-38: criteria version and execution config are computed from the run, not typed
        if criteria_version is not None and criteria_version != self.criteria_version:
            raise WalkForwardEngineError(
                f"Supplied criteria_version '{criteria_version}' does not match the criteria in force "
                f"'{self.criteria_version}' that judged this run (Audit §33 H-38)."
            )
        resolved_criteria_version = self.criteria_version
        if not resolved_criteria_version:
            raise WalkForwardEngineError("criteria_version cannot be empty. Must be provided or present on WalkForwardResult.")
        if execution_config is not None and dict(execution_config) != dict(self.execution_config):
            raise WalkForwardEngineError(
                "Supplied execution_config does not match the execution configuration that produced this "
                "result (Audit §33 H-38)."
            )
        resolved_exec_config = self.execution_config

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
            dataset_fingerprint=ds_fpr,
            criteria_version=resolved_criteria_version,
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
            execution_config=resolved_exec_config,
        )


def _validate_partition_spec_widening(spec: PartitionSpec) -> PartitionSpec:
    """
    Validates that a caller-supplied PartitionSpec does not narrow or shift the canonical holdout window.
    An explicit PartitionSpec may only widen the sealed holdout window per Audit §28 C3.
    """
    if spec.holdout_start > CANONICAL_HOLDOUT_START_DATE or spec.holdout_end < CANONICAL_HOLDOUT_END_DATE:
        raise HoldoutSealedError(
            f"Caller-supplied PartitionSpec holdout window [{spec.holdout_start}, {spec.holdout_end}] "
            f"cannot narrow or shift canonical holdout window [{CANONICAL_HOLDOUT_START_DATE}, {CANONICAL_HOLDOUT_END_DATE}]. "
            "An explicit PartitionSpec may only widen the sealed holdout window per Audit §28 C3."
        )
    return spec


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
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
        full_sessions_only: bool = True,
        fail_closed_on_unexplained: bool = True,
        fail_closed_on_missing_band: bool = True,
    ) -> None:
        self._calendar = calendar
        self._gold_engine = gold_engine
        self._sec_master = gold_engine.security_master
        self._criteria = criteria if criteria is not None else load_go_no_go_criteria()
        self._cost_model = cost_model
        self._slippage_model = slippage_model
        self._eligibility_policy = eligibility_policy
        self._latency = max(1, execution_latency_sessions)
        self._full_sessions_only = full_sessions_only
        self._fail_closed_on_unexplained = fail_closed_on_unexplained
        self._fail_closed_on_missing_band = fail_closed_on_missing_band
        if partition_spec is not None:
            self._partition_spec = _validate_partition_spec_widening(partition_spec)
        else:
            try:
                loaded_spec = load_canonical_partition_spec()
                # Audit §29 H-15: Compare loaded canonical spec against code constants
                self._partition_spec = _validate_partition_spec_widening(loaded_spec)
            except (PartitionSpecValidationError, FileNotFoundError, HoldoutSealedError):
                # Audit §28 H-13, §29 H-15: Catch specification and missing-file errors only; allow programming bugs to surface
                self._partition_spec = None
        self._unlock_file_path = unlock_file_path

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

    @property
    def partition_spec(self) -> Optional[PartitionSpec]:
        return self._partition_spec

    @property
    def unlock_file_path(self) -> Optional[Union[str, Path]]:
        return self._unlock_file_path

    @property
    def latency(self) -> int:
        return self._latency

    @property
    def full_sessions_only(self) -> bool:
        return self._full_sessions_only

    @property
    def fail_closed_on_unexplained(self) -> bool:
        return self._fail_closed_on_unexplained

    def run_fold(
        self,
        strategy: Strategy,
        fold: WalkForwardFold,
        initial_capital: Decimal = Decimal("1000000.00"),
        isins: Optional[Sequence[str]] = None,
        fail_on_lookahead: bool = True,
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
    ) -> FoldExecutionResult:
        """
        Simulates an individual walk-forward test fold out-of-sample.
        """
        # Gate G-1: Holdout containment and fold partition role validation (fail-closed per AGENTS.md Rule 8.1 / Wave 0)
        if fold.partition_role is None:
            raise HoldoutSealedError(
                f"Fold {fold.fold_index} has no declared partition role (unlabelled). "
                f"Unlabelled folds are strictly refused fail-closed per AGENTS.md Rule 8.1."
            )

        active_spec = _validate_partition_spec_widening(partition_spec) if partition_spec is not None else self._partition_spec
        active_unlock = unlock_file_path or self._unlock_file_path

        if active_spec is None:
            raise HoldoutSealedError(
                f"Cannot evaluate fold {fold.fold_index} without an authoritative PartitionSpec. "
                "Evaluating folds without partition boundaries is strictly prohibited per AGENTS.md Rule 8.1 (H-2)."
            )

        # Gate G-0 / Finding N-32: Binding evaluation start date invariant (Rule 10.8, Audit §41.6)
        min_start = self._criteria.min_binding_evaluation_start_date
        earliest_fold_date = min(fold.train_start, fold.test_start)
        if earliest_fold_date < min_start:
            raise WalkForwardEngineError(
                f"Fold {fold.fold_index} starts on {earliest_fold_date}, which precedes the minimum "
                f"binding evaluation start date ({min_start}) declared in GoNoGoCriteria. "
                "Evaluating pre-window folds on unsourced/unverified history is prohibited per Rule 10.8 and Finding N-32."
            )

        # Check if fold window [train_start, test_end] intersects sealed HOLDOUT partition
        intersects_holdout = (
            fold.train_start <= active_spec.holdout_end
            and active_spec.holdout_start <= fold.test_end
        )
        if intersects_holdout:
            if fold.partition_role != PartitionRole.HOLDOUT:
                raise HoldoutSealedError(
                    f"Fold {fold.fold_index} date window [{fold.train_start}, {fold.test_end}] "
                    f"intersects sealed HOLDOUT partition [{active_spec.holdout_start}, {active_spec.holdout_end}], "
                    f"but fold role is declared as '{fold.partition_role.value}'. Refusing execution fail-closed."
                )
            check_partition_access(active_spec, PartitionRole.HOLDOUT, unlock_file_path=active_unlock)
        else:
            if fold.partition_role == PartitionRole.HOLDOUT:
                raise HoldoutSealedError(
                    f"Fold {fold.fold_index} declared as HOLDOUT does not fall within holdout window "
                    f"[{active_spec.holdout_start}, {active_spec.holdout_end}]."
                )
            check_partition_access(active_spec, fold.partition_role, unlock_file_path=active_unlock)

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
            full_sessions_only=self._full_sessions_only,
        )

        # 3. Compute technical features for each instrument strictly within subsegments
        all_cal_sessions = self._calendar.sessions_in_range(fold.train_start, fold.test_end)
        features_by_inst_date: Dict[Tuple[str, datetime.date], InstrumentTechnicalFeatures] = {}

        for isin, bars in price_panel.items():
            feat_list = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
                expected_calendar_sessions=all_cal_sessions,
                actual_price_bars=bars,
                fail_closed_on_unexplained=self._fail_closed_on_unexplained,
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

                # Resolve previous session close for circuit limit derivation (Audit §35 H-40)
                inst_bars = price_panel.get(ord_req.instrument_id, [])
                prev_close: Optional[Decimal] = None
                for b_hist in reversed(inst_bars):
                    if b_hist.trade_date < t:
                        prev_close = b_hist.close
                        # Apply corporate action adjustment if session t is an ex-date
                        actions = self._sec_master.get_corporate_actions(ord_req.instrument_id, up_to=t)
                        for ca in actions:
                            if ca.ex_date == t:
                                prev_close = prev_close * ca.adjustment_factor
                        break

                # Resolve price band / circuit limits from Security Master (Audit §25 G-6, §31 H-30, §35 H-40)
                band = self._sec_master.get_price_band(ord_req.instrument_id, t, prev_close=prev_close)
                if band is None:
                    if self._fail_closed_on_missing_band:
                        raise WalkForwardEngineError(
                            f"Gate G-6 / Finding H-30 Violation: No price band registered for traded instrument "
                            f"'{ord_req.instrument_id}' on session {t}. Trading without circuit band evidence is strictly prohibited."
                        )
                    u_lim = None
                    l_lim = None
                else:
                    u_lim = band.upper_circuit_limit
                    l_lim = band.lower_circuit_limit

                # Gate G2C-3: Verify against eligibility policy
                fill_res = simulator.simulate_order(
                    order=ord_req,
                    bar=bar,
                    upper_circuit_limit=u_lim,
                    lower_circuit_limit=l_lim,
                    explicit_series=ex_series,
                    price_band=band,
                )

                fold_trades.append(fill_res)

                if fill_res.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
                    # Gate G2C-3 Assertion: Ineligible series MUST NEVER fill
                    if not self._eligibility_policy.is_eligible(ex_series):
                        raise WalkForwardEligibilityError(
                            f"Gate G2C-3 Violation: Ineligible series {ex_series} produced fill {fill_res.fill_id}."
                        )

                    # Post fill through authoritative single ledger (Audit §25 G-3: handle risk limit rejections gracefully)
                    try:
                        portfolio.process_fill(fill_res, enforce_risk_limits=True)
                    except PortfolioRiskLimitError as exc:
                        # Convert to REJECTED_RISK_LIMIT fill result rather than aborting run
                        rejected_fill = ExecutionFillResult(
                            order=ord_req,
                            status=FillStatus.REJECTED_RISK_LIMIT,
                            fill_date=t,
                            latency_sessions=fill_res.latency_sessions,
                            filled_quantity=0,
                            unfilled_quantity=ord_req.quantity,
                            executed_price=None,
                            slippage=None,
                            costs=None,
                            circuit_evidence_present=fill_res.circuit_evidence_present,
                            rejection_reason=str(exc),
                            fill_id=f"REJ_RISK_{ord_req.order_id}_{t}#1" if ord_req.order_id else None,
                        )
                        fold_trades[-1] = rejected_fill

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

            # --- Step C: Formulate next-session trade intents (t -> t + latency) (Audit §25 G-5) ---
            try:
                target_session = self._calendar.advance_sessions(t, self._latency)
            except CalendarError:
                target_session = None

            if target_session is not None and target_session <= fold.test_end:
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
                    next_session=target_session,
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

                    # Audit §31 H-29: Configured execution latency is authoritative, not advisory
                    if intent.target_date != target_session:
                        raise WalkForwardEngineError(
                            f"Gate G-5 / H-29 Violation: Intent target_date ({intent.target_date}) does not match "
                            f"engine configured execution session ({target_session}) for signal_date={t} with "
                            f"execution_latency_sessions={self._latency}. Strategy cannot bypass engine execution latency."
                        )

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

        # Annualized return and Sharpe (Audit §25 G-7: geometric compounding)
        ann_sharpe = (
            annualized_sharpe(daily_returns, sessions_per_year=self._criteria.sessions_per_year)
            if len(daily_returns) > 1
            else Decimal("0")
        )
        obs_sessions = len(test_sessions)
        ann_ret = compute_compounded_annualized_return(
            total_return=total_ret,
            session_count=obs_sessions,
            sessions_per_year=self._criteria.sessions_per_year,
        )

        # Circuit evidence audit (Gate G2C-4 / G-6)
        executed_fills = [f for f in fold_trades if f.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED)]
        if not executed_fills:
            circuit_complete = False
        else:
            circuit_complete = all(f.circuit_evidence_present for f in executed_fills)

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
        dataset_content_fingerprint: Optional[str] = None,
        fail_on_lookahead: bool = True,
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
    ) -> WalkForwardResult:
        """
        Runs comprehensive walk-forward validation across all provided folds.
        Emits WalkForwardResult bundle with aggregate metrics and deterministic fingerprint (Gate G2C-1).
        Enforces holdout containment and fold partition roles fail-closed (Gate G-1).
        """
        if not folds:
            raise WalkForwardEngineError("Cannot run walk-forward backtest with empty folds sequence.")

        active_spec = _validate_partition_spec_widening(partition_spec) if partition_spec is not None else self._partition_spec
        active_unlock = unlock_file_path or self._unlock_file_path

        # Gate G-1 pre-flight validation across all folds (H-2)
        for fold in folds:
            if fold.partition_role is None:
                raise HoldoutSealedError(
                    f"Fold {fold.fold_index} has no declared partition role (unlabelled). "
                    f"Unlabelled folds are strictly refused fail-closed per AGENTS.md Rule 8.1."
                )
            if active_spec is None:
                raise HoldoutSealedError(
                    f"Cannot evaluate fold {fold.fold_index} without an authoritative PartitionSpec. "
                    "Evaluating folds without partition boundaries is strictly prohibited per AGENTS.md Rule 8.1 (H-2)."
                )

            # Gate G-0 / Finding N-32: Pre-flight check against minimum binding evaluation start date
            earliest_fold_date = min(fold.train_start, fold.test_start)
            if earliest_fold_date < self._criteria.min_binding_evaluation_start_date:
                raise WalkForwardEngineError(
                    f"Fold {fold.fold_index} starts on {earliest_fold_date}, which precedes the minimum "
                    f"binding evaluation start date ({self._criteria.min_binding_evaluation_start_date}) declared in GoNoGoCriteria. "
                    "Evaluating pre-window folds on unsourced/unverified history is prohibited per Rule 10.8 and Finding N-32."
                )

            intersects = (
                fold.train_start <= active_spec.holdout_end
                and active_spec.holdout_start <= fold.test_end
            )
            if intersects:
                if fold.partition_role != PartitionRole.HOLDOUT:
                    raise HoldoutSealedError(
                        f"Fold {fold.fold_index} date window [{fold.train_start}, {fold.test_end}] "
                        f"intersects sealed HOLDOUT partition [{active_spec.holdout_start}, {active_spec.holdout_end}], "
                        f"but fold role is declared as '{fold.partition_role.value}'. Refusing execution fail-closed."
                    )
                check_partition_access(active_spec, PartitionRole.HOLDOUT, unlock_file_path=active_unlock)
            else:
                if fold.partition_role == PartitionRole.HOLDOUT:
                    raise HoldoutSealedError(
                        f"Fold {fold.fold_index} declared as HOLDOUT does not fall within holdout window "
                        f"[{active_spec.holdout_start}, {active_spec.holdout_end}]."
                    )
                check_partition_access(active_spec, fold.partition_role, unlock_file_path=active_unlock)

        target_isins = tuple(isins) if isins is not None else self._sec_master.registered_isins
        min_start = min(f.train_start for f in folds)
        max_end = max(f.test_end for f in folds)

        # Audit §25 G-4 / §31 H-28: Compute authentic Gold dataset snapshot over fold window
        snap, _ = self._gold_engine.build_dataset_snapshot(
            start_date=min_start,
            end_date=max_end,
            isins=target_isins,
            full_sessions_only=self._full_sessions_only,
        )
        authentic_fingerprint = snap.content_fingerprint

        if dataset_content_fingerprint is None:
            resolved_dataset_fingerprint = authentic_fingerprint
        else:
            if (
                not isinstance(dataset_content_fingerprint, str)
                or not dataset_content_fingerprint.startswith("DATA-CTNT-V2-")
                or dataset_content_fingerprint == "DATA-CTNT-V2-UNKNOWN"
            ):
                raise WalkForwardEngineError(
                    f"Invalid dataset_content_fingerprint {dataset_content_fingerprint!r}. "
                    "Must be a genuine DATA-CTNT-V2 content fingerprint; 'UNKNOWN' prohibited (Gate G-4)."
                )
            # Audit §31 H-28: Strict equality check against authentic snapshot; caller cannot spoof
            if dataset_content_fingerprint != authentic_fingerprint:
                raise WalkForwardEngineError(
                    f"Supplied dataset_content_fingerprint '{dataset_content_fingerprint}' does not match authentic "
                    f"Gold dataset snapshot fingerprint '{authentic_fingerprint}' for evaluation window "
                    f"[{min_start}, {max_end}] (Gate G-4 / H-28)."
                )
            resolved_dataset_fingerprint = authentic_fingerprint

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
                partition_spec=active_spec,
                unlock_file_path=active_unlock,
            )
            fold_results.append(f_res)
            agg_trades.extend(f_res.trades)

            # Stitch out-of-fold daily returns into aggregate return stream (G-11 fail-closed on length mismatch)
            if len(f_res.daily_returns) != len(f_res.portfolio_snapshots):
                raise WalkForwardEngineError(
                    f"Length mismatch in fold {fold.fold_index}: daily_returns count ({len(f_res.daily_returns)}) "
                    f"!= portfolio_snapshots count ({len(f_res.portfolio_snapshots)}) (Gate G-11)."
                )
            for ret, snap in zip(f_res.daily_returns, f_res.portfolio_snapshots):
                agg_daily_returns.append(ret)
                compounded_equity *= (Decimal("1") + ret)
                agg_equity_curve.append((snap.as_of_date, compounded_equity))

        # Global aggregate metrics (Audit §25 G-7: geometric compounding)
        total_ret = (compounded_equity - initial_capital) / initial_capital if initial_capital > 0 else Decimal("0")
        total_sessions = len(agg_daily_returns)
        ann_ret = compute_compounded_annualized_return(
            total_return=total_ret,
            session_count=total_sessions,
            sessions_per_year=self._criteria.sessions_per_year,
        )
        agg_sharpe = (
            annualized_sharpe(agg_daily_returns, sessions_per_year=self._criteria.sessions_per_year)
            if len(agg_daily_returns) > 1
            else Decimal("0")
        )

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

        # Circuit evidence audit across all folds (Gate G2C-4 / G-6)
        all_executed_fills = [f for f in agg_trades if f.status in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED)]
        if not all_executed_fills:
            circuit_complete = False
            verif_status = "NOT RUN"  # Audit §25 G-6: zero-trade run is NOT RUN, never VERIFIED
        else:
            circuit_complete = all(f.circuit_evidence_complete for f in fold_results)
            verif_status = "VERIFIED" if circuit_complete else "CIRCUIT_UNVERIFIED"

        # Execution configuration dictionary (Audit §31 H-33 / §32 H-37)
        active_cost = self._cost_model if self._cost_model is not None else TransactionCostModel(self._criteria.statutory_costs)
        if hasattr(active_cost, "criteria"):
            c = active_cost.criteria
            cost_parameters = {
                "stt_delivery_rate": str(c.stt_delivery_rate),
                "stt_intraday_sell_rate": str(c.stt_intraday_sell_rate),
                "sebi_turnover_charge_rate": str(c.sebi_turnover_charge_rate),
                "stamp_duty_delivery_buy_rate": str(c.stamp_duty_delivery_buy_rate),
                "stamp_duty_intraday_buy_rate": str(c.stamp_duty_intraday_buy_rate),
                "gst_rate": str(c.gst_rate),
                "brokerage_per_order_inr": str(c.brokerage_per_order_inr),
                "gst_taxable_base_components": sorted(c.gst_taxable_base_components),
                "effective_dated_exchange_fees": [
                    {
                        "circular_ref": f.circular_ref,
                        "from_date": f.from_date.isoformat(),
                        "to_date": f.to_date.isoformat() if f.to_date is not None else None,
                        "exchange_turnover_rate": str(f.exchange_turnover_rate),
                        "ipft_rate": str(f.ipft_rate),
                        "description": f.description,
                    }
                    for f in c.effective_dated_exchange_fees
                ],
            }
        else:
            cost_parameters = {}

        cost_config = {
            "model": active_cost.__class__.__name__,
            "parameters": cost_parameters,
        }

        active_slip = self._slippage_model if self._slippage_model is not None else SlippageModel()
        if hasattr(active_slip, "half_spread_bps"):
            slippage_parameters = {
                "half_spread_bps": str(active_slip.half_spread_bps),
                "impact_kappa": str(active_slip.impact_kappa),
                "impact_alpha": str(active_slip.impact_alpha),
            }
        else:
            slippage_parameters = {}

        slippage_config = {
            "model": active_slip.__class__.__name__,
            "parameters": slippage_parameters,
        }

        exec_config = {
            "execution_latency_sessions": self._latency,
            "full_sessions_only": self._full_sessions_only,
            "fail_closed_on_unexplained": self._fail_closed_on_unexplained,
            "fail_closed_on_missing_band": self._fail_closed_on_missing_band,
            "eligibility_policy": {
                "permitted_series": sorted(s.value for s in self._eligibility_policy.permitted_series),
                "allow_series_transitions": self._eligibility_policy.allow_series_transitions,
            },
            "cost_model": cost_config,
            "slippage_model": slippage_config,
            "criteria_version": self._criteria.version,
            "min_binding_evaluation_start_date": self._criteria.min_binding_evaluation_start_date.isoformat(),
            # Audit §33 H-39: identify the run by the thresholds in force, not by a version string
            "criteria_fingerprint": compute_criteria_fingerprint(self._criteria),
        }

        # Deterministic Result Fingerprint (Gate G2C-1 / H-33)
        fold_spec_fpr = compute_fold_spec_fingerprint(folds)
        canon_params = strategy.parameters

        hasher = hashlib.sha256()
        hasher.update(strategy.strategy_id.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(json.dumps(canon_params, sort_keys=True).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(fold_spec_fpr.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(resolved_dataset_fingerprint.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(json.dumps(exec_config, sort_keys=True).encode("utf-8"))
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
            dataset_content_fingerprint=resolved_dataset_fingerprint,
            fingerprint=result_fpr,
            execution_config=exec_config,
            criteria_version=self._criteria.version,
        )
