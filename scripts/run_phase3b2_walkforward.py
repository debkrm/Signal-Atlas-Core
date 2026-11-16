#!/usr/bin/env python3
"""
Signal Atlas Core — Phase 3B-2b Walk-Forward Strategy Runner & Benchmark Consumer.

Executes an authoritative, reproducible end-to-end walk-forward backtest for
DeliverySwingTrendStrategy across the complete 2022-2024 evaluation window
(2022-01-03..2024-12-31; 2022-2023 In-Sample, 2024 Validation).

Enforces non-negotiable quantitative research principles per AGENTS.md:
- §5.1, §13.1: Strict NSE EQ rolling cash delivery scope (zero intraday, zero F&O, zero BE/BZ entry).
- §5.2, §10.8, §13.2: Surveillance framework exit constraints propagated from session driver (Finding H-101).
- §5.3: Circuit filter realism: BUY fills into upper freeze and SELL fills into lower freeze rejected.
- §6.1: Point-in-time universe selection (zero survivorship bias, zero lookahead).
- §6.3: Fail-closed missing session invariants (zero forward-filling, zero silent bridging).
- §6.4: Exact Decimal financial accounting across cash, positions, equity, and statutory levies.
- §6.5: Honest data provenance tracking (unverified archives evaluate strictly to NOT RUN).
- §7.1: Zero lookahead next-session execution (signals formulated at session T close execute at T+1 open).
- §7.2: Statutory Indian transaction cost schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage).
- §7.4, §13.5: Single authoritative execution engine: all signals route through DailyTPlus1OrderRunner,
        ExecutionFillSimulator, and Portfolio ledger. Zero shadow simulators.
- §8.1: Out-of-sample Holdout (2025-01-01..2026-11-11) is physically and logically sealed (HoldoutSealedError).
- §8.2: Multi-hypothesis accountability: appends trial to TrialRegistry BEFORE reading or printing metrics (Rule 3.2).
- §8.3: Walk-forward stability across anchored/rolling folds.
- §9.1, §9.3: Computed verdicts: evaluates results via evaluate_verdicts() and emits candidate verdict report.
- Audit §63.6 Items 1-10 & §63.7 Protocol Compliance.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import datetime
from decimal import Decimal
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

# UTF-8 console output safety on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.dataset import PriceConvention
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
)
from signal_core.contracts.order_types import OrderSide
from signal_core.contracts.price_band import PriceBandRecord, is_price_band_sourced
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.universe import UniverseSchedule
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailyTPlus1OrderRunner,
)
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.features.engine import IndicatorValidationError, SubsegmentIndicatorEngine
from signal_core.loaders.historical_snapshot import (
    HistoricalDataset,
    load_historical_snapshot,
)
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.types import CashEntryType
from signal_core.reporting.verdicts import (
    OverallVerdict,
    VerdictReport,
    VerdictStatus,
    evaluate_verdicts,
)
from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    WalkForwardFold,
    check_partition_access,
    compute_fold_spec_fingerprint,
    load_canonical_partition_spec,
)
from signal_core.research.significance import (
    InvalidSampleError,
    SignificanceError,
    annualized_sharpe,
    evaluate_strategy_significance,
)
from signal_core.research.trials import TrialRecord, TrialRegistry
from signal_core.research.walkforward import compute_compounded_annualized_return
from signal_core.storage.calendar import (
    TradingCalendar,
    load_anchored_nse_trading_calendar,
)
from signal_core.storage.security_master import (
    CorporateActionType,
    SecurityMaster,
    build_production_security_master,
)
from signal_core.strategy.swing import (
    DeliverySwingTrendStrategy,
    SwingSessionExecutionSummary,
    execute_swing_strategy_session,
)


@dataclass(frozen=True, slots=True)
class Phase3B2WalkForwardRunResult:
    """
    Complete results bundle from a Phase 3B-2b walk-forward backtest run.
    """
    portfolio: Portfolio
    runner: DailyTPlus1OrderRunner
    strategy: DeliverySwingTrendStrategy
    security_master: SecurityMaster
    trial_record: TrialRecord
    total_trial_count_n: int
    verdict_report: VerdictReport
    session_summaries: Tuple[SwingSessionExecutionSummary, ...]
    closed_trades: Tuple[Dict[str, Any], ...]
    executed_sessions: Tuple[datetime.date, ...]
    initial_capital: Decimal
    final_equity: Decimal
    cagr: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    max_drawdown: Decimal
    mean_realized_r: Optional[Decimal]
    total_statutory_costs: Decimal
    annualized_sharpe: Decimal
    deflated_sharpe: Optional[Decimal]
    haircut_sharpe: Optional[Decimal]
    total_tickets_emitted: int
    total_tickets_filled: int
    total_tickets_rejected: int
    total_skipped_missing_band: int
    total_skipped_missing_bar: int
    in_sample_metrics: Optional[Dict[str, Any]] = None
    validation_metrics: Optional[Dict[str, Any]] = None
    coverage_diagnostics: Optional[Dict[str, Any]] = None
    registry_evaluated_trial_count: int = 0
    trial_sharpe_variance: Optional[Decimal] = None


def build_historical_dataset_from_raw_bhavcopy(
    raw_dirs: Optional[Sequence[Path]] = None,
    target_series: Sequence[str] = ("EQ",),
    holdout_cutoff: datetime.date = datetime.date(2025, 1, 1),
) -> HistoricalDataset:
    """
    Builds an in-memory HistoricalDataset directly from committed raw Bhavcopy ZIP archives
    across 2022..2024 strictly prior to holdout_cutoff (2025-01-01), keeping Holdout sealed.
    """
    from signal_core.contracts.dataset import (
        DEFAULT_PROVENANCE_STATUS,
        DatasetSnapshot,
        PriceConvention,
    )
    from signal_core.contracts.legacy_compat import (
        LegacyDatasetAdjustmentMetadata,
        compute_legacy_dataset_content_fingerprint,
    )
    from signal_core.contracts.price_bar import PriceBar
    from signal_core.contracts.provenance import compute_universe_schedule_fingerprint
    from signal_core.contracts.universe import UniverseSchedule
    from signal_core.storage.ingest import parse_bhavcopy_archive

    if raw_dirs is None:
        raw_dirs = [
            REPO_ROOT / "data" / "raw" / "2022",
            REPO_ROOT / "data" / "raw" / "2023",
            REPO_ROOT / "data" / "raw" / "2024",
        ]

    all_zips: List[Path] = []
    for d in raw_dirs:
        if d.is_dir():
            all_zips.extend(sorted(d.glob("*.zip")))

    if not all_zips:
        raise FileNotFoundError(
            f"No Bhavcopy archives found in {[str(d) for d in raw_dirs]} to build HistoricalDataset."
        )

    prices_by_isin: Dict[str, List[PriceBar]] = defaultdict(list)
    symbols_by_isin: Dict[str, str] = {}
    universe_by_date: Dict[datetime.date, List[str]] = defaultdict(list)
    trading_dates_set: Set[datetime.date] = set()

    for zp in all_zips:
        trade_date, silver_records = parse_bhavcopy_archive(zp, target_series=target_series)
        if trade_date >= holdout_cutoff:
            raise HoldoutSealedError(
                f"Attempted to read archive {zp.name} for date {trade_date} >= holdout cutoff {holdout_cutoff} (Rule 8.1)."
            )

        trading_dates_set.add(trade_date)
        for rec in silver_records:
            if rec.series not in target_series:
                continue
            isin = rec.isin
            symbols_by_isin[isin] = rec.symbol
            universe_by_date[trade_date].append(isin)
            prices_by_isin[isin].append(
                PriceBar(
                    instrument_id=isin,
                    trade_date=trade_date,
                    open=rec.open,
                    high=rec.high,
                    low=rec.low,
                    close=rec.close,
                    volume=rec.volume,
                    traded_value=rec.traded_value,
                )
            )

    sorted_dates = sorted(trading_dates_set)
    for isin in prices_by_isin:
        prices_by_isin[isin].sort(key=lambda b: b.trade_date)

    universe_schedule = UniverseSchedule({d: tuple(sorted(set(members))) for d, members in universe_by_date.items()})
    univ_fp = compute_universe_schedule_fingerprint(universe_schedule)
    content_fp = compute_legacy_dataset_content_fingerprint(
        trading_dates=sorted_dates,
        prices_by_instrument=prices_by_isin,
        symbols_by_instrument=symbols_by_isin,
    )

    total_inst_records = sum(len(bars) for bars in prices_by_isin.values())
    snapshot = DatasetSnapshot(
        dataset_id="EXP-RAW-BHAVCOPY-2022-2024",
        schema_version="v1.0",
        price_convention=PriceConvention.UNADJUSTED_CLOSE,
        start_date=sorted_dates[0],
        end_date=sorted_dates[-1],
        session_count=len(sorted_dates),
        instrument_count=len(prices_by_isin),
        total_instrument_records=total_inst_records,
        total_price_records=total_inst_records,
        source_identity="NSE_BHAVCOPY_DAILY",
        content_fingerprint=content_fp,
        source_provenance_status=DEFAULT_PROVENANCE_STATUS,
        universe_fingerprint=univ_fp,
        benchmark_record_count=0,
        source_format="signal-atlas-dataset-snapshot-v1",
    )

    return HistoricalDataset(
        snapshot=snapshot,
        prices_by_instrument=prices_by_isin,
        benchmark_prices=(),
        universe_schedule=universe_schedule,
        trading_dates=sorted_dates,
        symbols_by_instrument=symbols_by_isin,
        legacy_adjustments=LegacyDatasetAdjustmentMetadata({}, {}),
    )


def resolve_or_build_historical_dataset(
    snapshot_path: Optional[Union[str, Path]] = None,
    dataset: Optional[HistoricalDataset] = None,
) -> HistoricalDataset:
    """
    Resolves the 2022-2024 HistoricalDataset:
    1. Direct in-memory HistoricalDataset if provided
    2. Explicit snapshot_path (handling .gz transparently)
    3. data/reference/historical_dev_dataset_2022_2024.json if present
    4. data/reference/historical_dev_dataset_2022_2024.json.gz (decompressed on-demand per verify_historical_snapshot.py)
    5. Clean-checkout fallback: builds directly in memory from committed data/raw/2022..2024 Bhavcopy archives.
    """
    if dataset is not None:
        return dataset

    if snapshot_path:
        sp = Path(snapshot_path)
        if sp.is_file():
            return load_historical_snapshot(sp)
        gz_cand = sp.with_name(sp.name + ".gz")
        if gz_cand.is_file():
            return load_historical_snapshot(gz_cand)

    ref_json = REPO_ROOT / "data" / "reference" / "historical_dev_dataset_2022_2024.json"
    if ref_json.is_file():
        return load_historical_snapshot(ref_json)

    ref_gz = REPO_ROOT / "data" / "reference" / "historical_dev_dataset_2022_2024.json.gz"
    if ref_gz.is_file():
        print(f"[INFO] Decompressing cached snapshot fixture: {ref_gz.name} -> {ref_json.name}")
        with gzip.open(ref_gz, "rb") as f_in, open(ref_json, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return load_historical_snapshot(ref_json)

    print("[INFO] Historical snapshot JSON absent; building HistoricalDataset directly from committed 2022..2024 raw Bhavcopy archives...")
    return build_historical_dataset_from_raw_bhavcopy()


def run_phase3b2_walkforward(
    snapshot_path: Optional[Union[str, Path]] = None,
    registry_path: Optional[Union[str, Path]] = None,
    verdict_output_dir: Optional[Union[str, Path]] = None,
    dataset: Optional[HistoricalDataset] = None,
    strategy_id: str = "SWING-TREND-EQ-V1",
    fast_indicator: str = "sma_20",
    slow_indicator: str = "sma_50",
    allocation_weight: Optional[Decimal] = None,
    atr_stop_multiple: Decimal = Decimal("2.0"),
    initial_capital: Decimal = Decimal("1000000.00"),
    trial_id: str = "TRIAL-PHASE3B2-SWING-BASELINE-003",
    hypothesis: str = "Baseline delivery swing trend following on point-in-time liquid NSE EQ universe across 2022-2024",
    rationale: str = "Phase 3B-2b truth-pass baseline re-run (§65 H-110/H-111/N-104/N-105): effective circuit limits recorded on ExecutionFillResult, zero hardcoded PASS literals, 20-session ADTV for CRIT-EXEC-02, explicit per-year band coverage disclosure, and SecurityMaster fingerprint tracking.",
    max_sessions: Optional[int] = None,
    eval_start_date: Optional[datetime.date] = None,
    eval_end_date: Optional[datetime.date] = None,
    now_utc: Optional[str] = None,
    write_verdict_files: bool = True,
    fail_closed_on_holdout: bool = True,
    fail_closed_on_unexplained: bool = True,
    record_trial: bool = True,
    in_sample_only: bool = False,
    max_position_weight_trim_threshold: Optional[Decimal] = None,
) -> Phase3B2WalkForwardRunResult:
    """
    Executes the Phase 3B-2b walk-forward backtest and returns Phase3B2WalkForwardRunResult.
    """
    reg_p = Path(registry_path) if registry_path else (REPO_ROOT / "data" / "trials" / "trial_registry.jsonl")
    v_out_dir = Path(verdict_output_dir) if verdict_output_dir else (REPO_ROOT / "reports" / "verdicts")

    # 1. Authoritative Criteria & Anchored Calendar
    criteria = load_go_no_go_criteria()
    cal = load_anchored_nse_trading_calendar(criteria=criteria)
    partition_spec = load_canonical_partition_spec()

    # 2. Strict Holdout Containment Check (§8.1, §10.8)
    # The evaluation window is strictly 2022-01-03 .. 2024-12-31.
    # Out-of-sample Holdout is 2025-01-01 .. 2026-11-11.
    eval_start = eval_start_date or datetime.date(2022, 1, 3)
    if eval_end_date is not None:
        eval_end = eval_end_date
    elif in_sample_only:
        # §66.5 Condition 1: exploratory trials are evaluated on 2022-01-03..2023-12-29 only.
        eval_end = datetime.date(2023, 12, 29)
    else:
        eval_end = datetime.date(2024, 12, 31)

    # Physical Holdout Boundary Refusal (§8.1)
    if eval_start >= partition_spec.holdout_start or eval_end >= partition_spec.holdout_start:
        raise HoldoutSealedError(
            f"Requested evaluation window [{eval_start}..{eval_end}] touches sealed Holdout partition "
            f"[{partition_spec.holdout_start}..{partition_spec.holdout_end}] without human HOLDOUT_UNLOCK (AGENTS.md Rule 8.1)."
        )

    if fail_closed_on_holdout:
        # Verify that holdout check fails closed without human HOLDOUT_UNLOCK (Finding H-105)
        holdout_blocked = False
        try:
            check_partition_access(partition_spec, PartitionRole.HOLDOUT)
        except HoldoutSealedError:
            holdout_blocked = True

        if not holdout_blocked:
            raise HoldoutSealedError(
                "Holdout partition unexpectedly accessible without human HOLDOUT_UNLOCK (AGENTS.md Rule 8.1 violation)."
            )

    # 3. Build Production Security Master (loading CA-3 price bands and CA-1 corporate actions)
    sec_master = build_production_security_master(include_cash_universe=True)

    # 4. Load or Build Historical Snapshot (2022-2024)
    dataset = resolve_or_build_historical_dataset(snapshot_path=snapshot_path, dataset=dataset)

    # Physical Holdout Boundary Verification on Loaded Dataset (Rule 8.1, Finding H-105)
    max_d_raw = max(dataset.trading_dates)
    max_d = datetime.date.fromisoformat(max_d_raw) if isinstance(max_d_raw, str) else max_d_raw
    min_d_raw = min(dataset.trading_dates)
    min_d = datetime.date.fromisoformat(min_d_raw) if isinstance(min_d_raw, str) else min_d_raw
    if max_d >= partition_spec.holdout_start:
        raise HoldoutSealedError(
            f"Dataset contains trading dates >= holdout_start ({partition_spec.holdout_start}); "
            f"max date is {max_d} (AGENTS.md Rule 8.1)."
        )

    # Map snapshot UUIDs / symbols -> point-in-time ISINs via SecurityMaster (Finding H-109)
    uuid_to_isin: Dict[str, str] = {}
    refused_transition_uuids: Set[str] = set()

    for u, sym in dataset.symbols_by_instrument.items():
        if (isinstance(u, str) and u in sec_master.registered_isins) or (isinstance(u, str) and u.startswith("INE")):
            uuid_to_isin[u] = u
            continue

        # Finding H-109, H-116: Refuse UUIDs whose history spans an ISIN transition across the
        # dataset's own span, never the evaluated window, so no evaluation flag can weaken
        # identity validation (§10.4, §6.3).
        s_isin = sec_master.resolve_isin_by_symbol(sym, min_d, "EQ")
        e_isin = sec_master.resolve_isin_by_symbol(sym, max_d, "EQ")
        if s_isin is not None and e_isin is not None and s_isin != e_isin:
            refused_transition_uuids.add(u)
            continue

        # Identity resolution, not universe membership: a snapshot UUID may carry a symbol that was
        # renamed after the evaluation window (e.g. MCDOWELL-N -> UNITDSPR in H2 2024), so fall back
        # to the fixed 2024-01-16 cash-universe anchor, the evaluated window, and the dataset's own
        # full-span last session. The span anchor is required, not dead: measured at §68, removing it
        # makes --in-sample-only fail to resolve UNITDSPR (UUID 436d2da1) because that label does not
        # exist at any 2022-2023 date. Resolution is independent of the evaluation flag.
        isin = (
            sec_master.resolve_isin_by_symbol(sym, datetime.date(2024, 1, 16), "EQ")
            or sec_master.resolve_isin_by_symbol(sym, eval_start, "EQ")
            or sec_master.resolve_isin_by_symbol(sym, eval_end, "EQ")
            or sec_master.resolve_isin_by_symbol(sym, max_d, "EQ")
        )
        if isin is None:
            raise ValueError(f"Failed to resolve authentic ISIN for symbol {sym} (UUID {u})")
        uuid_to_isin[u] = isin

    # Re-index price bars by (isin, trade_date) and by isin
    bars_by_isin_date: Dict[Tuple[str, datetime.date], PriceBar] = {}
    bars_by_isin: Dict[str, List[PriceBar]] = defaultdict(list)
    for u, raw_bars in dataset.prices_by_instrument.items():
        isin = uuid_to_isin.get(u)
        if not isin:
            continue
        for b in raw_bars:
            pbar = PriceBar(
                instrument_id=isin,
                trade_date=b.trade_date,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
                traded_value=b.traded_value,
            )
            bars_by_isin_date[(isin, b.trade_date)] = pbar
            bars_by_isin[isin].append(pbar)

    for isin in bars_by_isin:
        bars_by_isin[isin].sort(key=lambda x: x.trade_date)

    # 5. Build Point-in-Time Liquid EQ Universe Schedule strictly over 2022-01-03..2024-12-31
    all_sessions = cal.sessions_in_range(eval_start, eval_end)
    if not all_sessions:
        raise ValueError(f"No trading sessions found in evaluation window [{eval_start}, {eval_end}]")

    sessions_to_run = all_sessions[:max_sessions] if max_sessions else all_sessions
    sessions_to_run_set = set(sessions_to_run)

    # Physical Holdout Boundary Refusal (§8.1)
    for s in sessions_to_run:
        if s >= partition_spec.holdout_start:
            raise HoldoutSealedError(
                f"Attempted to evaluate session {s} inside sealed Holdout partition "
                f"[{partition_spec.holdout_start}..{partition_spec.holdout_end}] without authorization (AGENTS.md Rule 8.1)."
            )

    daily_universe_schedule: Dict[datetime.date, Tuple[str, ...]] = {}
    for d in sessions_to_run:
        raw_uuids = dataset.universe_schedule.get_universe_for_date(d)
        eligible_isins: List[str] = []
        for u in raw_uuids:
            isin = uuid_to_isin.get(u)
            if not isin:
                continue
            sym_interval = sec_master.resolve_symbol(isin, d)
            if sym_interval and sym_interval.series == "EQ" and sec_master.is_active(isin, d):
                eligible_isins.append(isin)
        daily_universe_schedule[d] = tuple(sorted(eligible_isins))

    pit_universe = UniverseSchedule(daily_universe_schedule)

    # 6. Precompute Technical Features across Subsegments (Finding F-12, H-104, N-105, Zero Cross-Gap Leakage)
    features_by_isin_date: Dict[Tuple[str, datetime.date], Any] = {}
    unexplained_gap_refusals = 0
    continuous_instruments_passed = 0

    for isin, bar_list in bars_by_isin.items():
        # Slice bars to the session window being executed
        run_bars = [b for b in bar_list if b.trade_date in sessions_to_run_set]
        try:
            feats = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
                expected_calendar_sessions=sessions_to_run,
                actual_price_bars=run_bars,
                fail_closed_on_unexplained=fail_closed_on_unexplained,
            )
            for f in feats:
                features_by_isin_date[(isin, f.trade_date)] = f
            continuous_instruments_passed += 1
        except IndicatorValidationError:
            unexplained_gap_refusals += 1

    fail_closed_enforced = bool(
        fail_closed_on_unexplained
        and (unexplained_gap_refusals > 0 or continuous_instruments_passed > 0)
    )

    # 7. Configure Walk-Forward Folds (2022-2023 In-Sample, 2024 Validation)
    fold_is = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2022, 1, 3),
        train_end=datetime.date(2022, 12, 30),
        test_start=datetime.date(2023, 1, 2),
        test_end=datetime.date(2023, 12, 29),
        embargo_sessions=0,
        partition_role=PartitionRole.IN_SAMPLE,
    )
    fold_val = WalkForwardFold(
        fold_index=1,
        train_start=datetime.date(2022, 1, 3),
        train_end=datetime.date(2023, 12, 29),
        test_start=datetime.date(2024, 1, 1),
        test_end=datetime.date(2024, 12, 31),
        embargo_sessions=0,
        partition_role=PartitionRole.VALIDATION,
    )
    folds = (fold_is,) if in_sample_only else (fold_is, fold_val)
    fold_spec_fp = compute_fold_spec_fingerprint(folds)

    # 8. Instantiate Single Authoritative Execution Engine & Strategy (§7.4, §13.5)
    portfolio = Portfolio(
        initial_capital=initial_capital,
        criteria=criteria,
        initial_date=sessions_to_run[0],
    )
    simulator = ExecutionFillSimulator(
        criteria=criteria,
        trading_calendar=cal.sessions,
    )
    runner = DailyTPlus1OrderRunner(
        portfolio=portfolio,
        simulator=simulator,
        calendar=cal,
        criteria=criteria,
        eligibility_policy=APPROVED_EQ_ONLY_POLICY,
    )
    strategy = DeliverySwingTrendStrategy(
        strategy_id=strategy_id,
        fast_indicator=fast_indicator,
        slow_indicator=slow_indicator,
        allocation_weight=allocation_weight,
        atr_stop_multiple=atr_stop_multiple,
        max_position_weight_trim_threshold=max_position_weight_trim_threshold,
    )

    # 9. Session-by-Session Walk-Forward Simulation Loop
    session_summaries: List[SwingSessionExecutionSummary] = []
    all_fills = []
    all_fills_with_bands: List[Tuple[ExecutionFillResult, Optional[PriceBandRecord]]] = []
    open_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    closed_trades: List[Dict[str, Any]] = []
    # N-112/N-115: book basis removed from the lot book by merger fractional slices, used only to
    # reconcile the lot book against the ledger's market-value cash settlement.
    lot_frac_book_basis_total = Decimal("0.00")

    total_emitted = 0
    total_filled = 0
    total_rejected = 0
    total_skipped_missing_band = 0
    total_skipped_missing_bar = 0

    num_sessions = len(sessions_to_run)
    for i in range(num_sessions - 1):
        as_of = sessions_to_run[i]
        next_session = sessions_to_run[i + 1]

        # Active PIT universe on as_of
        univ = list(pit_universe.get_universe_for_date(as_of))

        # Filtered features on as_of
        cur_features = {
            isin: features_by_isin_date[(isin, as_of)]
            for isin in univ
            if (isin, as_of) in features_by_isin_date
        }

        # Available price bars at next_session
        bars_next = {
            isin: bars_by_isin_date[(isin, next_session)]
            for isin in univ
            if (isin, next_session) in bars_by_isin_date
        }

        # Available price bands at next_session (with derived circuit limits, Audit §35 H-40)
        bands_next: Dict[str, PriceBandRecord] = {}
        for isin in univ:
            prev_bar = bars_by_isin_date.get((isin, as_of))
            prev_close = prev_bar.close if prev_bar else None
            band = sec_master.get_price_band(isin, next_session, prev_close=prev_close)
            if band is not None:
                bands_next[isin] = band

        # Corporate actions effective on next_session ex-date (Finding H-100, H-107)
        actions_today = [
            ca for ca in sec_master._corporate_actions
            if ca.ex_date == next_session
        ]
        # Attribute dividends received on open lots while held (Finding H-107) and adjust lots for corporate actions (Finding H-113)
        for ca in actions_today:
            if ca.action_type == CorporateActionType.DIVIDEND and ca.isin in open_lots:
                div_per_share = (
                    ca.dividend_amount
                    if ca.dividend_amount is not None
                    else (ca.ratio_numerator / ca.ratio_denominator)
                )
                for lot in open_lots[ca.isin]:
                    lot["dividends"] = lot.get("dividends", Decimal("0.00")) + (div_per_share * Decimal(lot["quantity"]))
            elif ca.action_type == CorporateActionType.MERGER and ca.isin in open_lots and ca.new_isin:
                num = int(ca.ratio_numerator)
                den = int(ca.ratio_denominator)
                old_lots = open_lots.pop(ca.isin, [])
                for lot in old_lots:
                    q = lot["quantity"]
                    whole_q = (q * num) // den
                    rem = (q * num) % den
                    frac_costs = (lot["costs"] * Decimal(rem)) / Decimal(q * num) if (q * num) > 0 else Decimal("0.00")
                    # N-115: the fractional slice is a cash settlement, not a trade. It is recorded
                    # solely as CashEntryType.MERGER_CASH_IN_LIEU by the Portfolio ledger; adding a
                    # zero-gross closed trade here would double-count it and inflate the trade count.
                    lot_frac_book_basis_total += (
                        lot["entry_price"] * Decimal(rem) / Decimal(num)
                    ).quantize(Decimal("0.01"))
                    lot["quantity"] = whole_q
                    lot["original_quantity"] = whole_q
                    lot["entry_price"] = (lot["entry_price"] * Decimal(den) / Decimal(num)).quantize(Decimal("0.0001"))
                    lot["costs"] = lot["costs"] - frac_costs
                    if whole_q > 0:
                        open_lots[ca.new_isin].append(lot)
            elif ca.action_type in (CorporateActionType.SPLIT, CorporateActionType.BONUS, CorporateActionType.CONSOLIDATION) and ca.isin in open_lots:
                num = int(ca.ratio_numerator)
                den = int(ca.ratio_denominator)
                target_isin = ca.new_isin if ca.new_isin else ca.isin
                old_lots = open_lots.pop(ca.isin, [])
                for lot in old_lots:
                    lot["quantity"] = (lot["quantity"] * num) // den
                    lot["original_quantity"] = (lot["original_quantity"] * num) // den
                    lot["entry_price"] = (lot["entry_price"] * Decimal(den) / Decimal(num)).quantize(Decimal("0.0001"))
                    open_lots[target_isin].append(lot)
            elif ca.action_type == CorporateActionType.ISIN_TRANSITION and ca.isin in open_lots and ca.new_isin:
                old_lots = open_lots.pop(ca.isin, [])
                open_lots[ca.new_isin].extend(old_lots)

        # Current market prices as of as_of session (Finding H-102)
        cur_market_prices = {
            isin: bars_by_isin_date[(isin, as_of)].close
            for isin in univ
            if (isin, as_of) in bars_by_isin_date
        }

        # Execute session through authoritative harness
        summary = execute_swing_strategy_session(
            strategy=strategy,
            runner=runner,
            as_of=as_of,
            next_session=next_session,
            universe=univ,
            features=cur_features,
            bars_next_session=bars_next,
            price_bands_next_session=bands_next,
            explicit_series=ExchangeSeries.EQ,
            latest_market_prices=cur_market_prices,
            corporate_actions=actions_today,
            security_master=sec_master,
            price_convention=getattr(dataset.snapshot, "price_convention", PriceConvention.SPLIT_BONUS_ADJUSTED),
        )
        session_summaries.append(summary)

        total_emitted += summary.tickets_emitted
        total_filled += summary.tickets_filled
        total_rejected += summary.tickets_rejected
        total_skipped_missing_band += summary.skipped_missing_band
        total_skipped_missing_bar += summary.skipped_missing_bar

        # Match trades and track exact Decimal realized PnL and R-multiples (H-107, N-101)
        for ticket in summary.tickets:
            if ticket.fill_result and ticket.fill_result.filled_quantity > 0:
                fill = ticket.fill_result
                all_fills.append(fill)
                isin = fill.order.instrument_id
                all_fills_with_bands.append((fill, bands_next.get(isin)))
                if fill.order.side == OrderSide.BUY:
                    intended_r = ticket.intended_risk
                    open_lots[isin].append({
                        "entry_date": next_session,
                        "entry_price": fill.executed_price,
                        "quantity": fill.filled_quantity,
                        "original_quantity": fill.filled_quantity,
                        "intended_risk": intended_r,
                        "costs": fill.costs.total_charges if fill.costs else Decimal("0.00"),
                        "dividends": Decimal("0.00"),
                    })
                elif fill.order.side == OrderSide.SELL:
                    sell_qty = fill.filled_quantity
                    sell_price = fill.executed_price
                    sell_costs = fill.costs.total_charges if fill.costs else Decimal("0.00")
                    while sell_qty > 0 and open_lots[isin]:
                        lot = open_lots[isin][0]
                        matched_qty = min(sell_qty, lot["quantity"])
                        orig_qty = Decimal(lot["original_quantity"])
                        m_qty = Decimal(matched_qty)
                        gross_pnl = (sell_price - lot["entry_price"]) * m_qty
                        prop_entry_cost = (lot["costs"] * m_qty) / orig_qty
                        prop_sell_cost = (sell_costs * m_qty) / Decimal(fill.filled_quantity)
                        prop_dividends = (lot.get("dividends", Decimal("0.00")) * m_qty) / orig_qty
                        net_pnl = gross_pnl - prop_entry_cost - prop_sell_cost + prop_dividends

                        if lot.get("intended_risk") and lot["intended_risk"] > Decimal("0.00"):
                            prop_intended_risk = (lot["intended_risk"] * m_qty) / orig_qty
                            r_mult = net_pnl / prop_intended_risk
                        else:
                            prop_intended_risk = None
                            r_mult = None

                        closed_trades.append({
                            "isin": isin,
                            "entry_date": lot["entry_date"],
                            "exit_date": next_session,
                            "quantity": matched_qty,
                            "entry_price": lot["entry_price"],
                            "exit_price": sell_price,
                            "gross_pnl": gross_pnl,
                            "net_pnl": net_pnl,
                            "dividends": prop_dividends,
                            "total_costs": prop_entry_cost + prop_sell_cost,
                            "intended_risk": prop_intended_risk,
                            "realized_r": r_mult,
                        })
                        lot["quantity"] -= matched_qty
                        sell_qty -= matched_qty
                        if lot["quantity"] == 0:
                            open_lots[isin].pop(0)

        # Mark-to-Market Session Valuation across active holdings
        mtm_prices: Dict[str, Decimal] = {}
        for isin in portfolio.get_open_positions():
            bar_cur = bars_by_isin_date.get((isin, next_session))
            if bar_cur:
                mtm_prices[isin] = bar_cur.close
            else:
                prev_bar = bars_by_isin_date.get((isin, as_of))
                mtm_prices[isin] = prev_bar.close if prev_bar else portfolio.get_position(isin).average_entry_price
        portfolio.mark_to_market(next_session, mtm_prices)

    # Reconcile closed trades net PnL with authoritative ledger realized cash (Finding H-107)
    portfolio_open_outlay = sum(
        (pos.total_cost_basis + pos.unallocated_buy_charges)
        for pos in portfolio.get_open_positions().values()
    )
    portfolio_realized_trading_pnl = sum(
        pos.realized_net_pnl for pos in portfolio._positions.values()
    )
    portfolio_dividends = sum(
        e.amount for e in portfolio.ledger.entries if e.entry_type == CashEntryType.DIVIDEND_INFLOW
    )
    portfolio_merger_cash = sum(
        e.amount for e in portfolio.ledger.entries if e.entry_type == CashEntryType.MERGER_CASH_IN_LIEU
    )
    # The merger cash settlement is already reflected through the position's settlement PnL
    # (consideration minus removed book basis), so this identity needs no separate merger term.
    authoritative_ledger_cash = (
        initial_capital + portfolio_realized_trading_pnl - portfolio_open_outlay
        + portfolio_dividends
    )
    assert abs(portfolio.current_cash - authoritative_ledger_cash) <= Decimal("0.01"), (
        f"Authoritative ledger cash ₹{portfolio.current_cash} does not reconcile with portfolio state "
        f"(expected ₹{authoritative_ledger_cash}, difference ₹{portfolio.current_cash - authoritative_ledger_cash})"
    )

    open_positions_outlay = sum(
        (lot["entry_price"] * Decimal(lot["quantity"]) + (lot["costs"] * Decimal(lot["quantity"])) / Decimal(lot["original_quantity"]))
        for isin, lots in open_lots.items() for lot in lots
    )
    open_positions_dividends = sum(
        ((lot.get("dividends", Decimal("0.00")) * Decimal(lot["quantity"])) / Decimal(lot["original_quantity"]))
        for isin, lots in open_lots.items() for lot in lots
    )
    total_closed_net_pnl = sum(t["net_pnl"] for t in closed_trades)
    # The lot book drops the fractional slice's book basis, so the ledger's market-value settlement
    # contributes (cash received - book basis removed) to lot-level cash (Finding N-112).
    lot_merger_settlement_pnl = portfolio_merger_cash - lot_frac_book_basis_total
    expected_lot_cash = (
        initial_capital + total_closed_net_pnl - open_positions_outlay
        + open_positions_dividends + lot_merger_settlement_pnl
    )
    # Lot-matched net PnL reconciles with ledger cash within sub-paise fractional rounding tolerance (<= ₹1.00 across 3 years)
    assert abs(portfolio.current_cash - expected_lot_cash) <= Decimal("1.00"), (
        f"Ledger cash ₹{portfolio.current_cash} does not reconcile with closed trades net PnL ₹{total_closed_net_pnl} "
        f"(expected ₹{expected_lot_cash}, difference ₹{portfolio.current_cash - expected_lot_cash})"
    )

    # 10. Append Run to TrialRegistry BEFORE Reading or Printing Metrics (Rule 3.2, §8.2)
    os.makedirs(reg_p.parent, exist_ok=True)
    registry = TrialRegistry(reg_p)
    ts_utc = now_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()

    trial_params = dict(strategy.parameters)
    trial_params["security_master_fingerprint"] = sec_master.fingerprint

    if record_trial:
        trial_record = registry.append_trial(
            trial_id=trial_id,
            hypothesis=hypothesis,
            rationale=rationale,
            partition=PartitionRole.IN_SAMPLE if in_sample_only else PartitionRole.VALIDATION,
            canonical_params=trial_params,
            fold_spec_fingerprint=fold_spec_fp,
            dataset_fingerprint=dataset.snapshot.content_fingerprint,
            criteria_version=criteria.version,
            timestamp_utc=ts_utc,
            sharpe_ratio=None,  # Rule 3.2: Appended BEFORE reading Sharpe ratio!
            partition_spec=partition_spec,
            execution_config={
                "execution_latency_sessions": 1,
                "statutory_costs_enforced": True,
                "strict_decimal_accounting": True,
                "point_in_time_universe": True,
                "zero_data_fabrication": True,
                "security_master_fingerprint": sec_master.fingerprint,
            },
        )
    else:
        # N-111: A re-render may only describe a trial the registry already records. Emitting a
        # verdict artifact under an unregistered trial_id would understate the multiple-testing
        # budget with a fabricated hash chain, so it fails closed instead.
        existing_trials = [t for t in registry.get_trials() if t.trial_id == trial_id]
        if not existing_trials:
            raise ValueError(
                f"record_trial=False requested for unregistered trial_id '{trial_id}'; "
                f"register the trial before evaluating it (AGENTS.md §8.2, Finding N-111)."
            )
        trial_record = existing_trials[-1]

    total_trial_count_n = registry.total_trial_count

    # 11. Compute Exact Decimal Diagnostics (§6.4, Finding H-103)
    # Valuation Basis: MARK_TO_MARKET (Audit §64 H-103)
    final_equity = portfolio.snapshots[-1].total_portfolio_value if portfolio.snapshots else initial_capital
    total_return = (final_equity - initial_capital) / initial_capital
    cagr = compute_compounded_annualized_return(
        total_return=total_return,
        session_count=num_sessions,
        sessions_per_year=250,
    )

    wins = [t for t in closed_trades if t["net_pnl"] > Decimal("0.00")]
    win_rate = (Decimal(len(wins)) / Decimal(len(closed_trades))) if closed_trades else Decimal("0.00")
    gross_profit = sum(t["gross_pnl"] for t in closed_trades if t["gross_pnl"] > Decimal("0.00"))
    gross_loss = sum(abs(t["gross_pnl"]) for t in closed_trades if t["gross_pnl"] < Decimal("0.00"))
    profit_factor = (gross_profit / gross_loss) if gross_loss > Decimal("0.00") else Decimal("0.00")
    max_drawdown = portfolio.max_drawdown

    r_trades = [t["realized_r"] for t in closed_trades if t.get("realized_r") is not None]
    mean_realized_r = (sum(r_trades) / Decimal(len(r_trades))) if r_trades else None

    total_statutory_costs = sum(
        f.costs.total_charges for f in all_fills if f.costs
    )

    # Compute daily returns from mark-to-market snapshots for statistical significance
    daily_returns: List[Decimal] = []
    prev_eq = initial_capital
    for snap in portfolio.snapshots:
        ret = (snap.total_portfolio_value - prev_eq) / prev_eq
        daily_returns.append(ret)
        prev_eq = snap.total_portfolio_value

    # Finding N-117: a deterministic digest of the session mark-to-market return series, so the
    # DSR/haircut discipline (§8.2) can be audited from the artifact without the trial row being
    # rewritten. Quantised to 12 dp for byte-stable hashing; observation_count is the number of
    # return observations actually used, not the number of sessions the run nominally covered.
    returns_digest = "RET-V1-" + hashlib.sha256(
        "\n".join(str(r.quantize(Decimal("0.000000000001"))) for r in daily_returns).encode("utf-8")
    ).hexdigest() if daily_returns else None
    observation_count = len(daily_returns)

    # H-119: the pre-registered row keeps `sharpe_ratio=None` (Rule 3.2), so the computed outcome is
    # appended as a linked evaluation after the metrics exist. The row is never rewritten and
    # evaluated_trial_count rises with the number of scored trials.
    if record_trial and returns_digest is not None:
        registry.append_trial_evaluation(
            trial_id=trial_id,
            sharpe_ratio=annualized_sharpe(daily_returns),
            returns_digest=returns_digest,
            observation_count=observation_count,
            evaluated_at_utc=ts_utc,
            max_drawdown=max_drawdown,
        )

    try:
        sig_report = evaluate_strategy_significance(
            returns=daily_returns if daily_returns else [Decimal("0.00")],
            registry=registry,
            criteria=criteria,
            strategy_id=strategy_id,
        )
        annualized_sr = sig_report.annualized_sharpe
        dsr_val = sig_report.dsr_result.deflated_sharpe_ratio if (sig_report.dsr_result and total_trial_count_n > 1) else None
        haircut_sr = sig_report.haircut_result.haircut_sharpe_ratio if (sig_report.haircut_result and total_trial_count_n > 1) else None
    except (InvalidSampleError, SignificanceError):
        annualized_sr = annualized_sharpe(daily_returns) if daily_returns else Decimal("0.00")
        dsr_val = None
        haircut_sr = None

    # Per-Fold Walk-Forward Performance Metrics (Audit §64 H-103)
    is_snapshots = [s for s in portfolio.snapshots if s.as_of_date <= fold_is.test_end]
    val_snapshots = [s for s in portfolio.snapshots if s.as_of_date >= fold_val.test_start]

    is_start_eq = initial_capital
    is_end_eq = is_snapshots[-1].total_portfolio_value if is_snapshots else initial_capital
    is_ret = (is_end_eq - is_start_eq) / is_start_eq
    is_sessions = len(is_snapshots)
    is_cagr = compute_compounded_annualized_return(is_ret, session_count=is_sessions, sessions_per_year=250) if is_sessions > 0 else Decimal("0.00")
    is_maxdd = max((s.max_drawdown for s in is_snapshots), default=Decimal("0.00"))
    is_trades = [t for t in closed_trades if t["exit_date"] <= fold_is.test_end]
    is_wins = [t for t in is_trades if t["net_pnl"] > Decimal("0.00")]
    is_win_rate = (Decimal(len(is_wins)) / Decimal(len(is_trades))) if is_trades else Decimal("0.00")
    is_gross_profit = sum(t["gross_pnl"] for t in is_trades if t["gross_pnl"] > Decimal("0.00"))
    is_gross_loss = sum(abs(t["gross_pnl"]) for t in is_trades if t["gross_pnl"] < Decimal("0.00"))
    is_profit_factor = (is_gross_profit / is_gross_loss) if is_gross_loss > Decimal("0.00") else Decimal("0.00")

    in_sample_metrics = {
        "fold": "Fold 0 (In-Sample)",
        "window": f"{fold_is.train_start} .. {fold_is.test_end}",
        "sessions": is_sessions,
        "start_equity": is_start_eq,
        "end_equity": is_end_eq,
        "cagr": is_cagr,
        "max_drawdown": is_maxdd,
        "closed_trades": len(is_trades),
        "win_rate": is_win_rate,
        "profit_factor": is_profit_factor,
    }

    validation_metrics: Optional[Dict[str, Any]] = None
    if not in_sample_only:
        val_start_eq = is_end_eq
        val_end_eq = val_snapshots[-1].total_portfolio_value if val_snapshots else val_start_eq
        val_ret = (val_end_eq - val_start_eq) / val_start_eq
        val_sessions = len(val_snapshots)
        val_cagr = compute_compounded_annualized_return(val_ret, session_count=val_sessions, sessions_per_year=250) if val_sessions > 0 else Decimal("0.00")
        val_maxdd = max((s.max_drawdown for s in val_snapshots), default=Decimal("0.00"))
        val_trades = [t for t in closed_trades if t["exit_date"] >= fold_val.test_start]
        val_wins = [t for t in val_trades if t["net_pnl"] > Decimal("0.00")]
        val_win_rate = (Decimal(len(val_wins)) / Decimal(len(val_trades))) if val_trades else Decimal("0.00")
        val_gross_profit = sum(t["gross_pnl"] for t in val_trades if t["gross_pnl"] > Decimal("0.00"))
        val_gross_loss = sum(abs(t["gross_pnl"]) for t in val_trades if t["gross_pnl"] < Decimal("0.00"))
        val_profit_factor = (val_gross_profit / val_gross_loss) if val_gross_loss > Decimal("0.00") else Decimal("0.00")

        validation_metrics = {
            "fold": "Fold 1 (Validation)",
            "window": f"{fold_val.test_start} .. {fold_val.test_end}",
            "sessions": val_sessions,
            "start_equity": val_start_eq,
            "end_equity": val_end_eq,
            "cagr": val_cagr,
            "max_drawdown": val_maxdd,
            "closed_trades": len(val_trades),
            "win_rate": val_win_rate,
            "profit_factor": val_profit_factor,
        }

    # 12. Evaluate Verdicts via evaluate_verdicts() (AGENTS.md §9.1, §9.3, Findings H-102, H-104, H-110, H-111, N-105)
    # Compute every verdict bundle metric from actual run state:
    max_single_pos_weight = max(
        (p.market_value / snap.total_portfolio_value
         for snap in portfolio.snapshots
         for p in snap.positions
         if snap.total_portfolio_value > Decimal("0")),
        default=Decimal("0.0"),
    )

    max_vol_participation = max(
        (Decimal(f.filled_quantity) / Decimal(bars_by_isin_date[(f.order.instrument_id, f.fill_date)].volume)
         for f in all_fills
         if (f.order.instrument_id, f.fill_date) in bars_by_isin_date
         and bars_by_isin_date[(f.order.instrument_id, f.fill_date)].volume > 0),
        default=Decimal("0.0"),
    )

    # N-105 (CRIT-EXEC-02): 20-session trailing ADTV prior to trade entry for entry fills
    buy_fills = [f for f in all_fills if f.order.side == OrderSide.BUY and f.filled_quantity > 0]
    sell_fills = [f for f in all_fills if f.order.side == OrderSide.SELL and f.filled_quantity > 0]

    entry_adtvs_cr: List[Decimal] = []
    for f in buy_fills:
        isin = f.order.instrument_id
        hist_bars = [b for b in bars_by_isin.get(isin, []) if b.trade_date < f.fill_date]
        trailing_bars = hist_bars[-20:] if len(hist_bars) >= 20 else hist_bars
        if trailing_bars:
            turnovers = [
                b.traded_value if b.traded_value is not None else (Decimal(b.volume) * b.close)
                for b in trailing_bars
            ]
            adtv_cr = (sum(turnovers) / Decimal(len(turnovers))) / Decimal("10000000")
            entry_adtvs_cr.append(adtv_cr)
        elif f.executed_price is not None and (isin, f.fill_date) in bars_by_isin_date:
            single_turnover_cr = (Decimal(bars_by_isin_date[(isin, f.fill_date)].volume) * f.executed_price) / Decimal("10000000")
            entry_adtvs_cr.append(single_turnover_cr)

    min_daily_turnover_cr = min(entry_adtvs_cr, default=Decimal("0.0"))

    statutory_costs_enforced = len(all_fills) > 0 and all(
        f.costs is not None and f.costs.total_charges > Decimal("0") for f in all_fills
    )

    strict_decimal_accounting = (
        isinstance(portfolio.current_cash, Decimal)
        and all(isinstance(e.amount, Decimal) for e in portfolio.ledger.entries)
    )

    # N-105 (CRIT-DATA-03): Comprehensive point-in-time universe audit
    pit_universe_valid = True
    total_scheduled_instances = 0
    for d in sessions_to_run:
        constituents = daily_universe_schedule.get(d, ())
        if not isinstance(constituents, tuple):
            pit_universe_valid = False
            break
        for isin in constituents:
            total_scheduled_instances += 1
            sym_int = sec_master.resolve_symbol(isin, d)
            if sym_int is None or sym_int.series != "EQ" or not sec_master.is_active(isin, d):
                pit_universe_valid = False
                break
        if not pit_universe_valid:
            break
    pit_universe_enforced = pit_universe_valid and (total_scheduled_instances > 0)

    # N-105 (CRIT-DATA-04): Zero data fabrication verified without vacuous conditions
    has_synthetic_bar = any(
        getattr(b, "is_synthetic", False)
        for bar_list in bars_by_isin.values()
        for b in bar_list
    )
    has_invalid_prices = any(
        b.open <= Decimal("0") or b.high <= Decimal("0") or b.low <= Decimal("0") or b.close <= Decimal("0")
        or b.low > b.high or b.open > b.high or b.open < b.low or b.close > b.high or b.close < b.low
        for bar_list in bars_by_isin.values()
        for b in bar_list
    )
    has_synthetic_band = any(
        getattr(b, "is_synthetic", False) for b in sec_master._price_bands
    )
    is_synthetic_dataset = getattr(dataset.snapshot, "is_synthetic", False) or getattr(dataset, "is_synthetic", False)

    zero_data_fabrication_enforced = bool(
        not is_synthetic_dataset
        and not has_synthetic_bar
        and not has_invalid_prices
        and not has_synthetic_band
    )

    traded_eq_resolution_pct = (
        (Decimal(len(uuid_to_isin)) / Decimal(len(dataset.symbols_by_instrument))) * Decimal("100")
    ) if dataset.symbols_by_instrument else Decimal("0.00")

    # H-111 (CRIT-EXEC-03 & CRIT-EXEC-04): Enforce against fill.effective_upper_circuit_limit / effective_lower_circuit_limit
    prohibit_buy_at_uc = bool(
        simulator._criteria.prohibit_buy_at_upper_circuit
        and len(buy_fills) > 0
        and all(
            f.effective_upper_circuit_limit is not None
            and f.executed_price is not None
            and f.executed_price < f.effective_upper_circuit_limit
            for f in buy_fills
        )
    )

    prohibit_sell_at_lc = bool(
        simulator._criteria.prohibit_sell_at_lower_circuit
        and len(sell_fills) > 0
        and all(
            f.effective_lower_circuit_limit is not None
            and f.executed_price is not None
            and f.executed_price > f.effective_lower_circuit_limit
            for f in sell_fills
        )
    )

    # H-114 / §67 Condition 5: report the observed circuit deviation counts as evidence, not as an
    # assertion that enforcement happened. A missing limit is counted as a deviation of the same kind.
    buy_uc_violating = sum(
        1 for f in buy_fills
        if f.effective_upper_circuit_limit is not None
        and f.executed_price is not None
        and f.executed_price >= f.effective_upper_circuit_limit
    )
    buy_uc_missing_limit = sum(1 for f in buy_fills if f.effective_upper_circuit_limit is None)
    sell_lc_violating = sum(
        1 for f in sell_fills
        if f.effective_lower_circuit_limit is not None
        and f.executed_price is not None
        and f.executed_price <= f.effective_lower_circuit_limit
    )
    sell_lc_missing_limit = sum(1 for f in sell_fills if f.effective_lower_circuit_limit is None)

    min_latency_observed = min((f.latency_sessions for f in all_fills), default=1)

    # CRIT-STAT-05: Annualized Portfolio Turnover
    buy_turnover = sum(f.executed_price * Decimal(f.filled_quantity) for f in buy_fills if f.executed_price)
    sell_turnover = sum(f.executed_price * Decimal(f.filled_quantity) for f in sell_fills if f.executed_price)
    avg_portfolio_equity = (
        sum(s.total_portfolio_value for s in portfolio.snapshots) / Decimal(len(portfolio.snapshots))
    ) if portfolio.snapshots else initial_capital
    annual_turnover = (
        (min(buy_turnover, sell_turnover) / avg_portfolio_equity)
        * (Decimal("250") / Decimal(len(sessions_to_run)))
    ) if avg_portfolio_equity > Decimal("0") and len(sessions_to_run) > 0 else Decimal("0.00")

    # CRIT-OVERFIT-03: Walk-Forward Stability Ratio (Audit §66 N-108)
    # When fewer than 2 independent out-of-sample validation folds exist (N_val < 2),
    # omit walk_forward_positive_fold_ratio from extra_metrics so CRIT-OVERFIT-03 evaluates
    # honestly to NOT RUN (and disclose N_val = 1 in the report).
    num_val_folds = 0 if in_sample_only else (1 if (validation_metrics is not None) else 0)
    if num_val_folds >= 2:
        walk_forward_positive_fold_ratio: Optional[Decimal] = (
            Decimal("1.00") if validation_metrics["cagr"] > Decimal("0") else Decimal("0.00")
        )
    else:
        walk_forward_positive_fold_ratio = None

    # H-110 & N-110: Per-Year Band Coverage Diagnostics & Disclosure (Full-Year Session Union)
    coverage_diagnostics: Dict[str, Any] = {}
    for yr in (2022, 2023, 2024):
        yr_sessions = [s for s in sessions_to_run if s.year == yr]
        yr_sessions_set = set(yr_sessions)
        yr_summaries = [s for s in session_summaries if s.next_session in yr_sessions_set]
        yr_zero_ticket_sessions = sum(1 for s in yr_summaries if s.tickets_emitted == 0)
        yr_emitted = sum(s.tickets_emitted for s in yr_summaries)
        yr_filled = sum(s.tickets_filled for s in yr_summaries)
        yr_rejected = sum(s.tickets_rejected for s in yr_summaries)

        # Count distinct ISINs that have an active price band registered during year yr across ALL sessions (Finding N-110)
        yr_band_isins = set()
        for s in yr_sessions:
            for isin in pit_universe.get_universe_for_date(s):
                b = sec_master.get_price_band(isin, s)
                if b is not None:
                    yr_band_isins.add(isin)

        # H-112 residual: name the symbols the band union actually covers instead of typing them.
        yr_band_symbols = set()
        for isin in yr_band_isins:
            for s in yr_sessions:
                sym_int = sec_master.resolve_symbol(isin, s)
                if sym_int is not None:
                    yr_band_symbols.add(sym_int.symbol)
                    break
        yr_band_symbols_sorted = sorted(yr_band_symbols)

        yr_trades = [t for t in closed_trades if t["exit_date"].year == yr]
        yr_wins = [t for t in yr_trades if t["net_pnl"] > Decimal("0.00")]
        yr_win_rate = (Decimal(len(yr_wins)) / Decimal(len(yr_trades))) if yr_trades else Decimal("0.00")
        yr_gross_profit = sum(t["gross_pnl"] for t in yr_trades if t["gross_pnl"] > Decimal("0.00"))
        yr_gross_loss = sum(abs(t["gross_pnl"]) for t in yr_trades if t["gross_pnl"] < Decimal("0.00"))
        yr_profit_factor = (yr_gross_profit / yr_gross_loss) if yr_gross_loss > Decimal("0.00") else Decimal("0.00")

        yr_snaps = [s for s in portfolio.snapshots if s.as_of_date.year == yr]
        if yr_snaps:
            yr_start_eq = yr_snaps[0].total_portfolio_value
            yr_end_eq = yr_snaps[-1].total_portfolio_value
            yr_ret = (yr_end_eq - yr_start_eq) / yr_start_eq if yr_start_eq > 0 else Decimal("0.00")
            yr_cagr = compute_compounded_annualized_return(yr_ret, session_count=len(yr_snaps), sessions_per_year=250)
            yr_maxdd = max((s.max_drawdown for s in yr_snaps), default=Decimal("0.00"))
        else:
            yr_cagr = Decimal("0.00")
            yr_maxdd = Decimal("0.00")

        coverage_diagnostics[str(yr)] = {
            "year": yr,
            "sessions": len(yr_sessions),
            "band_covered_isins": len(yr_band_isins),
            "band_covered_symbols": yr_band_symbols_sorted,
            "zero_ticket_sessions": yr_zero_ticket_sessions,
            "tickets_emitted": yr_emitted,
            "tickets_filled": yr_filled,
            "tickets_rejected": yr_rejected,
            "closed_trades": len(yr_trades),
            "cagr": yr_cagr,
            "win_rate": yr_win_rate,
            "profit_factor": yr_profit_factor,
            "max_drawdown": yr_maxdd,
            "coverage_notes": (
                f"Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for {yr}; "
                f"dynamic flexing anchor names ({', '.join(yr_band_symbols_sorted) if yr_band_symbols_sorted else 'none'}) "
                f"carry only ±10% derived limits and cash names are rejected/skipped per §5.3 fail-closed "
                f"invariants ({yr_filled} fills executed); circuit criteria are NOT RUN for these sessions"
                if yr in (2022, 2023)
                else f"Cash universe coverage: {len(yr_band_isins)} scrips supported by the attested 2024-01-16 "
                f"sec_list snapshot applied as static bands ({yr_filled} fills executed)"
            ),
        }

    total_valid_isins = continuous_instruments_passed + unexplained_gap_refusals

    # CA-3(c): no sourced 2022-01-03..2024-01-15 NSE price-band report exists in the corpus (and the
    # exchange serves no dated historical sec_list), so circuit-prohibition compliance cannot be
    # asserted over sessions in that span. The criteria are NOT RUN rather than PASS on the
    # interpolated 3-symbol band stub; no band is synthesized (§6.3, §10.8).
    unsourced_band_sessions = [s for s in sessions_to_run if not is_price_band_sourced(s)]
    circuit_band_coverage_note: Optional[str] = None
    if unsourced_band_sessions:
        circuit_band_coverage_note = (
            f"{len(unsourced_band_sessions)} of {len(sessions_to_run)} evaluated session(s) "
            f"({unsourced_band_sessions[0].isoformat()}..{unsourced_band_sessions[-1].isoformat()}) have "
            f"no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. "
            f"Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this "
            f"criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8)."
        )

    last_summary = session_summaries[-1] if session_summaries else None
    extra_m = {
        "evaluation_start_date": sessions_to_run[0].isoformat(),
        "evaluation_end_date": sessions_to_run[-1].isoformat(),
        "evaluated_at_utc": ts_utc,
        "dataset_fingerprint": dataset.snapshot.content_fingerprint,
        "data_provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "provenance_attestation_reference": None,
        "trial_count_n": total_trial_count_n,
        "deflated_sharpe_ratio": dsr_val,
        "haircut_sharpe_ratio": haircut_sr,
        "total_trades": len(closed_trades),
        "profit_factor": profit_factor,
        "max_portfolio_drawdown": max_drawdown,
        "max_single_position_weight": max_single_pos_weight,
        "returns_digest": returns_digest,
        "observation_count": observation_count,
        "cagr": cagr,
        "annualized_sharpe": annualized_sr,
        "annual_turnover": annual_turnover,
        "statutory_costs_enforced": statutory_costs_enforced,
        "strict_decimal_accounting": strict_decimal_accounting,
        "point_in_time_universe": pit_universe_enforced,
        "zero_data_fabrication": zero_data_fabrication_enforced,
        "fail_closed_on_unexplained_gaps": fail_closed_enforced,
        "unexplained_gap_refusals": unexplained_gap_refusals,
        "continuous_instruments_passed": continuous_instruments_passed,
        "total_valid_isins": total_valid_isins,
        "traded_eq_resolution_pct": traded_eq_resolution_pct,
        "prohibit_buy_at_upper_circuit": prohibit_buy_at_uc,
        "prohibit_sell_at_lower_circuit": prohibit_sell_at_lc,
        "unsourced_band_sessions": len(unsourced_band_sessions),
        "max_volume_participation": max_vol_participation,
        "min_daily_turnover_crore": min_daily_turnover_cr,
        "execution_latency_sessions": min_latency_observed,
        "valuation_basis": "MARK_TO_MARKET",
        "coverage_diagnostics": coverage_diagnostics,
    }
    if circuit_band_coverage_note is not None:
        extra_m["circuit_band_coverage_note"] = circuit_band_coverage_note
    else:
        extra_m.update({
            "upper_circuit_buy_judged_fills": len(buy_fills),
            "upper_circuit_buy_violating_fills": buy_uc_violating,
            "upper_circuit_buy_missing_limit_fills": buy_uc_missing_limit,
            "lower_circuit_sell_judged_fills": len(sell_fills),
            "lower_circuit_sell_violating_fills": sell_lc_violating,
            "lower_circuit_sell_missing_limit_fills": sell_lc_missing_limit,
        })

    if walk_forward_positive_fold_ratio is not None:
        extra_m["walk_forward_positive_fold_ratio"] = walk_forward_positive_fold_ratio
    else:
        extra_m["walk_forward_validation_folds_count"] = num_val_folds
        extra_m["walk_forward_not_run_reason"] = (
            "In-sample-only exploratory run: the 2024 Validation fold is frozen and was not evaluated "
            "(§66.5 Condition 1). No out-of-sample stability ratio is computable."
            if in_sample_only
            else (
                f"Only N_val = {num_val_folds} validation fold evaluated; minimum 2 independent out-of-sample validation folds required for stability ratio (§8.3, Finding N-108)."
            )
        )

    if last_summary is not None:
        results_bundle = last_summary.to_verdict_results_bundle(
            runner=runner,
            extra_metrics=extra_m,
        )
    else:
        results_bundle = dict(extra_m)
        results_bundle.update({
            "surveillance_exit_constraints_enforced": False,
            "surveillance_constraint_status": "NOT_RUN",
            "surveillance_not_run_reason": "Surveillance framework exit constraints unverified or not run for evaluation window (§5.2, §10.8, §13.2, Finding N-92, CA-2).",
        })

    verdict_report = evaluate_verdicts(
        results_bundle=results_bundle,
        criteria=criteria,
        calendar=cal,
    )

    # 13. Write Candidate Verdict Report to reports/verdicts/
    if write_verdict_files:
        os.makedirs(v_out_dir, exist_ok=True)
        json_path = v_out_dir / "phase3b2_swing_baseline_2022_2024_verdict.json"
        md_path = v_out_dir / "phase3b2_swing_baseline_2022_2024_verdict.md"

        report_dict = verdict_report.to_dict()
        report_dict["coverage_diagnostics"] = {
            str(k): {
                sub_k: str(sub_v) if isinstance(sub_v, Decimal) else sub_v
                for sub_k, sub_v in v.items()
            }
            for k, v in coverage_diagnostics.items()
        }
        report_dict["in_sample_metrics"] = {
            k: str(v) if isinstance(v, Decimal) else v
            for k, v in in_sample_metrics.items()
        } if in_sample_metrics else None
        report_dict["validation_metrics"] = {
            k: str(v) if isinstance(v, Decimal) else v
            for k, v in validation_metrics.items()
        } if validation_metrics else None
        report_dict["validation_folds_count"] = num_val_folds
        report_dict["continuous_instruments_passed"] = continuous_instruments_passed
        report_dict["unexplained_gap_refusals"] = unexplained_gap_refusals
        report_dict["total_valid_isins"] = total_valid_isins
        report_dict["returns_digest"] = returns_digest
        report_dict["observation_count"] = observation_count
        report_dict["unsourced_band_sessions"] = len(unsourced_band_sessions)
        report_dict["circuit_band_coverage_note"] = circuit_band_coverage_note

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

        md_text = verdict_report.to_markdown()
        extra_md = [
            "",
            "## Walk-Forward Fold Performance (Audit §64 H-103, §66 N-108)",
            "",
            "| Fold | Window | Sessions | Start Equity | End Equity | CAGR | Max Drawdown | Closed Trades | Win Rate | Profit Factor |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        if in_sample_metrics:
            m = in_sample_metrics
            extra_md.append(
                f"| {m['fold']} | {m['window']} | {m['sessions']} | ₹{m['start_equity']:,.2f} | ₹{m['end_equity']:,.2f} | "
                f"{m['cagr']*100:.2f}% | {m['max_drawdown']*100:.2f}% | {m['closed_trades']} | {m['win_rate']*100:.2f}% | {m['profit_factor']:.4f} |"
            )
        if validation_metrics:
            m = validation_metrics
            extra_md.append(
                f"| {m['fold']} | {m['window']} | {m['sessions']} | ₹{m['start_equity']:,.2f} | ₹{m['end_equity']:,.2f} | "
                f"{m['cagr']*100:.2f}% | {m['max_drawdown']*100:.2f}% | {m['closed_trades']} | {m['win_rate']*100:.2f}% | {m['profit_factor']:.4f} |"
            )
        if in_sample_only:
            extra_md.extend([
                "",
                "> [!NOTE]",
                "> **In-Sample-Only Disclosure (§66.5 Condition 1)**: This exploratory run evaluated 2022-01-03..2023-12-29 only. The 2024 Validation fold is frozen and was not evaluated, so `CRIT-OVERFIT-03` is `NOT RUN` and no result here is out-of-sample evidence.",
            ])
        elif num_val_folds < 2:
            extra_md.extend([
                "",
                "> [!NOTE]",
                f"> **Out-of-Sample Stability Disclosure (Finding N-108)**: Only N_val = {num_val_folds} validation fold was evaluated (Fold 1: 2024-01-01..2024-12-31). `CRIT-OVERFIT-03` evaluates to `NOT RUN` because a ratio over N_val = 1 is arithmetically degenerate; at least 2 independent validation folds are required to measure parameter stability across rolling/anchored windows (§8.3).",
            ])

        diag_2022 = coverage_diagnostics.get("2022", {})
        diag_2023 = coverage_diagnostics.get("2023", {})
        diag_2024 = coverage_diagnostics.get("2024", {})
        fills_2022_2023 = diag_2022.get("tickets_filled", 0) + diag_2023.get("tickets_filled", 0)
        fills_2024 = diag_2024.get("tickets_filled", 0)
        band_isins_2024 = diag_2024.get("band_covered_isins", 0)
        band_symbols_2022_2023 = sorted(
            set(diag_2022.get("band_covered_symbols", [])) | set(diag_2023.get("band_covered_symbols", []))
        )
        band_symbols_2022_2023_text = ", ".join(band_symbols_2022_2023) if band_symbols_2022_2023 else "none"

        extra_md.extend([
            "",
            "## Band Coverage Diagnostics & Disclosure (Audit §65 H-110)",
            "",
            "> [!NOTE]",
            "> Price band coverage across 2022–2024 reflects historical exchange report availability:",
            f"> - **2022–2023**: Band-ineligible (CA-3(c)). No sourced NSE price-band report exists; only the dynamic flexing anchor names ({band_symbols_2022_2023_text}) carry ±10% derived limits. Cash-universe names without price band reports are rejected/skipped per §5.3 fail-closed invariants ({fills_2022_2023} fills executed), and `CRIT-EXEC-03`/`-04` are `NOT RUN` over these sessions.",
            f"> - **2024**: Cash-universe coverage ({band_isins_2024} scrips) supported by the attested 2024-01-16 `sec_list` snapshot applied as static bands ({fills_2024} fills executed).",
            f"> - **Universe Integrity & Gap Filtering**: {continuous_instruments_passed} continuous active instruments evaluated out of {total_valid_isins} valid ISINs ({unexplained_gap_refusals} instruments refused due to unexplained missing sessions per §6.3 fail-closed invariants).",
            "",
            "| Year | Sessions | Band-Covered ISINs | Zero-Ticket Sessions | Tickets Emitted | Tickets Filled | Tickets Rejected | Closed Trades | CAGR | Win Rate | Profit Factor | Max Drawdown | Coverage Notes |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ])
        for yr_key, diag in sorted(coverage_diagnostics.items()):
            extra_md.append(
                f"| {diag['year']} | {diag['sessions']} | {diag['band_covered_isins']} | {diag['zero_ticket_sessions']} | "
                f"{diag['tickets_emitted']} | {diag['tickets_filled']} | {diag['tickets_rejected']} | {diag['closed_trades']} | "
                f"{diag['cagr']*100:.2f}% | {diag['win_rate']*100:.2f}% | {diag['profit_factor']:.4f} | {diag['max_drawdown']*100:.2f}% | "
                f"{diag['coverage_notes']} |"
            )
        if circuit_band_coverage_note is not None:
            extra_md.extend([
                "",
                "> [!WARNING]",
                f"> **Price Band Sourcing (CA-3(c))**: {circuit_band_coverage_note}",
            ])
        extra_md.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text + "\n" + "\n".join(extra_md))

    return Phase3B2WalkForwardRunResult(
        portfolio=portfolio,
        runner=runner,
        strategy=strategy,
        security_master=sec_master,
        trial_record=trial_record,
        total_trial_count_n=total_trial_count_n,
        verdict_report=verdict_report,
        session_summaries=tuple(session_summaries),
        closed_trades=tuple(closed_trades),
        executed_sessions=tuple(sessions_to_run),
        initial_capital=initial_capital,
        final_equity=final_equity,
        cagr=cagr,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        mean_realized_r=mean_realized_r,
        total_statutory_costs=total_statutory_costs,
        annualized_sharpe=annualized_sr,
        deflated_sharpe=dsr_val,
        haircut_sharpe=haircut_sr,
        total_tickets_emitted=total_emitted,
        total_tickets_filled=total_filled,
        total_tickets_rejected=total_rejected,
        total_skipped_missing_band=total_skipped_missing_band,
        total_skipped_missing_bar=total_skipped_missing_bar,
        in_sample_metrics=in_sample_metrics,
        validation_metrics=validation_metrics,
        coverage_diagnostics=coverage_diagnostics,
        registry_evaluated_trial_count=registry.evaluated_trial_count,
        trial_sharpe_variance=registry.compute_trial_sharpe_variance(),
    )


def describe_stats_not_run_reason(
    evaluated_trial_count: int,
    trial_sharpe_variance: Optional[Decimal],
) -> str:
    """Names the input that actually blocks DSR, instead of a count comparison (Finding H-119)."""
    if evaluated_trial_count < 2:
        return (
            f"evaluated_trial_count={evaluated_trial_count} < minimum 2 scored trials required "
            f"for DSR variance (§8.2, Finding H-119)"
        )
    if trial_sharpe_variance is None or trial_sharpe_variance <= Decimal("0.00"):
        return (
            f"trial Sharpe variance={trial_sharpe_variance} is not strictly positive; DSR is "
            f"undefined (§8.2, Finding H-119)"
        )
    return "DSR/haircut result unavailable from the significance report"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal Atlas Core — Phase 3B-2b Walk-Forward Strategy Runner (2022-2024)"
    )
    parser.add_argument("--snapshot-path", type=Path, default=None, help="Path to historical snapshot JSON")
    parser.add_argument("--registry-path", type=Path, default=None, help="Path to TrialRegistry JSONL")
    parser.add_argument("--verdict-output-dir", type=Path, default=None, help="Output directory for verdict reports")
    parser.add_argument("--trial-id", type=str, default="TRIAL-PHASE3B2-SWING-BASELINE-003", help="Trial ID for registry")
    parser.add_argument("--max-sessions", type=int, default=None, help="Cap sessions for fast diagnostic runs")
    parser.add_argument("--no-record-trial", action="store_true", help="Re-render reports without appending a new row to trial registry")
    parser.add_argument(
        "--in-sample-only",
        action="store_true",
        help="Evaluate 2022-01-03..2023-12-29 only; the 2024 Validation fold is never evaluated (§66.5 Condition 1)",
    )
    parser.add_argument(
        "--trim-threshold",
        type=Decimal,
        default=None,
        help="Enable automated winner trim when a position's close weight exceeds this fraction (e.g. 0.095)",
    )
    parser.add_argument("--hypothesis", type=str, default=None, help="TrialRegistry hypothesis (required for a new trial)")
    parser.add_argument("--rationale", type=str, default=None, help="TrialRegistry rationale naming the parameter change")
    args = parser.parse_args()

    window_label = (
        "2022-01-03 .. 2023-12-29 (In-Sample only; 2024 Validation FROZEN)"
        if args.in_sample_only
        else "2022-01-03 .. 2024-12-31 (In-Sample: 2022-2023, Validation: 2024)"
    )
    print("=" * 80)
    print("SIGNAL ATLAS CORE — PHASE 3B-2b WALK-FORWARD STRATEGY RUNNER")
    print(f"Evaluation Window: {window_label}")
    print("Holdout Partition: 2025-01-01 .. 2026-11-11 (STRICTLY SEALED)")
    print("Valuation Basis:   MARK_TO_MARKET (Audit §64 H-103)")
    print("=" * 80)

    run_kwargs: Dict[str, Any] = {}
    if args.hypothesis is not None:
        run_kwargs["hypothesis"] = args.hypothesis
    if args.rationale is not None:
        run_kwargs["rationale"] = args.rationale

    res = run_phase3b2_walkforward(
        snapshot_path=args.snapshot_path,
        registry_path=args.registry_path,
        verdict_output_dir=args.verdict_output_dir,
        trial_id=args.trial_id,
        max_sessions=args.max_sessions,
        record_trial=not args.no_record_trial,
        in_sample_only=args.in_sample_only,
        max_position_weight_trim_threshold=args.trim_threshold,
        **run_kwargs,
    )

    print("\n--- 1. TRIAL REGISTRY REGISTRATION (Rule 3.2, §8.2) ---")
    print(f"Trial ID:               {res.trial_record.trial_id}")
    print(f"Registry Sequence:       #{res.trial_record.seq}")
    print(f"Total Trial Count (N):   {res.total_trial_count_n}")
    print(f"Evaluated Trials (N_eval): {res.registry_evaluated_trial_count}")
    print(f"Append-Before-Read Check: PASS (sharpe_ratio was None when appended)")
    print(f"Fold Spec Fingerprint:   {res.trial_record.fold_spec_fingerprint}")
    print(f"Dataset Fingerprint:     {res.trial_record.dataset_fingerprint}")

    print("\n--- 2. EXECUTION REALISM & SESSION COUNTERS (§5.3, §7.4, Findings N-93, N-97, H-106) ---")
    print(f"Sessions Evaluated:      {len(res.executed_sessions)}")
    print(f"Tickets Emitted:         {res.total_tickets_emitted}")
    print(f"Tickets Filled:          {res.total_tickets_filled}")
    print(f"Tickets Rejected:        {res.total_tickets_rejected}")
    print(f"Skipped (Missing Band):  {res.total_skipped_missing_band}")
    print(f"Skipped (Missing Bar):   {res.total_skipped_missing_bar}")
    print(f"Open Positions at End:   {len(res.portfolio.get_open_positions())}")

    print("\n--- 3. EXACT DECIMAL PERFORMANCE DIAGNOSTICS (§6.4, §13.2, Finding H-103) ---")
    print(f"Valuation Basis:         MARK_TO_MARKET")
    print(f"Initial Capital:         ₹{res.initial_capital:,.2f}")
    print(f"Final Equity:            ₹{res.final_equity:,.2f}")
    print(f"CAGR:                    {res.cagr * 100:.2f}%")
    print(f"Total Closed Trades:     {len(res.closed_trades)}")
    print(f"Win Rate:                {res.win_rate * 100:.2f}%")
    print(f"Profit Factor:           {res.profit_factor:.4f}")
    print(f"Max Drawdown:            {res.max_drawdown * 100:.2f}%")
    if res.mean_realized_r is not None:
        print(f"Mean Realized R:         {res.mean_realized_r:.4f}R (ATR stop distance)")
    else:
        print(f"Mean Realized R:         NOT RUN / INSUFFICIENT DATA")
    print(f"Total Statutory Costs:   ₹{res.total_statutory_costs:,.2f}")
    print(f"Annualized Sharpe:       {res.annualized_sharpe:.4f}")
    # H-119: print the input that actually blocks the computation, not a count comparison the
    # output itself contradicts. DSR needs >= 2 scored trials with positive Sharpe variance;
    # the haircut needs N > 1. Both reasons are distinct and both are derived from the registry.
    stats_not_run_reason = describe_stats_not_run_reason(
        res.registry_evaluated_trial_count, res.trial_sharpe_variance
    )

    if res.total_trial_count_n > 1 and res.deflated_sharpe is not None:
        print(f"Deflated Sharpe Ratio:   {res.deflated_sharpe:.4f} (N={res.total_trial_count_n}, N_eval={res.registry_evaluated_trial_count})")
    else:
        print(f"Deflated Sharpe Ratio:   NOT RUN / INVALID ({stats_not_run_reason})")
    if res.total_trial_count_n > 1 and res.haircut_sharpe is not None:
        print(f"Haircut Sharpe Ratio:    {res.haircut_sharpe:.4f} (N={res.total_trial_count_n}, N_eval={res.registry_evaluated_trial_count})")
    elif res.total_trial_count_n <= 1:
        print(f"Haircut Sharpe Ratio:    NOT RUN / INVALID (N={res.total_trial_count_n} <= 1: no multiple-testing penalty to apply)")
    else:
        print(f"Haircut Sharpe Ratio:    NOT RUN / INVALID ({stats_not_run_reason})")

    if res.in_sample_metrics:
        m = res.in_sample_metrics
        print(f"\n--- 4. WALK-FORWARD FOLD 0: IN-SAMPLE ({m['window']}) ---")
        print(f"Sessions: {m['sessions']} | Start: ₹{m['start_equity']:,.2f} | End: ₹{m['end_equity']:,.2f} | CAGR: {m['cagr']*100:.2f}% | MaxDD: {m['max_drawdown']*100:.2f}% | Trades: {m['closed_trades']} | Win Rate: {m['win_rate']*100:.2f}% | PF: {m['profit_factor']:.4f}")

    if res.validation_metrics:
        m = res.validation_metrics
        print(f"\n--- 5. WALK-FORWARD FOLD 1: VALIDATION ({m['window']}) ---")
        print(f"Sessions: {m['sessions']} | Start: ₹{m['start_equity']:,.2f} | End: ₹{m['end_equity']:,.2f} | CAGR: {m['cagr']*100:.2f}% | MaxDD: {m['max_drawdown']*100:.2f}% | Trades: {m['closed_trades']} | Win Rate: {m['win_rate']*100:.2f}% | PF: {m['profit_factor']:.4f}")

    cov_diag = res.verdict_report.metadata.get("coverage_diagnostics") or {}
    if cov_diag:
        print("\n--- 5b. BAND COVERAGE DIAGNOSTICS & DISCLOSURE (Audit §65 H-110) ---")
        for yr_k, d in sorted(cov_diag.items()):
            print(f"Year {d['year']}: Sessions={d['sessions']} | Band-Covered ISINs={d['band_covered_isins']} | Zero-Ticket Sessions={d['zero_ticket_sessions']} | Emitted={d['tickets_emitted']} | Filled={d['tickets_filled']} | Closed Trades={d['closed_trades']} | CAGR={float(d['cagr'])*100:.2f}% | MaxDD={float(d['max_drawdown'])*100:.2f}%")
            print(f"  Disclosure: {d['coverage_notes']}")

    print("\n--- 6. AUTOMATED VERDICT EVALUATION (AGENTS.md §9.1, §9.3) ---")
    v = res.verdict_report
    print(f"Overall Verdict:         {v.overall_verdict.value}")
    print(f"Summary Counts:          PASS={v.summary_counts.get('PASS', 0)}, FAIL={v.summary_counts.get('FAIL', 0)}, NOT RUN={v.summary_counts.get('NOT_RUN', 0)}")
    
    crit_surv = next((e for e in v.evaluations if e.criterion_id == "CRIT-SURV-01"), None)
    crit_prov = next((e for e in v.evaluations if e.criterion_id == "CRIT-PROV-01"), None)
    crit_stat3 = next((e for e in v.evaluations if e.criterion_id == "CRIT-STAT-03"), None)
    crit_data2 = next((e for e in v.evaluations if e.criterion_id == "CRIT-DATA-02"), None)
    print(f"CRIT-SURV-01:            {crit_surv.status.value if crit_surv else 'MISSING'}")
    print(f"CRIT-PROV-01:            {crit_prov.status.value if crit_prov else 'MISSING'}")
    print(f"CRIT-STAT-03 (Max Pos):  {crit_stat3.status.value if crit_stat3 else 'MISSING'} ({crit_stat3.computed_value if crit_stat3 else 'N/A'})")
    print(f"CRIT-DATA-02 (Fail Cls): {crit_data2.status.value if crit_data2 else 'MISSING'} ({crit_data2.computed_value if crit_data2 else 'N/A'})")

    print("\n--- 7. ARTIFACTS GENERATED ---")
    v_dir = args.verdict_output_dir or (REPO_ROOT / "reports" / "verdicts")
    print(f"Verdict JSON:            {v_dir / 'phase3b2_swing_baseline_2022_2024_verdict.json'}")
    print(f"Verdict Markdown:        {v_dir / 'phase3b2_swing_baseline_2022_2024_verdict.md'}")
    print(f"Trial Registry:          {args.registry_path or (REPO_ROOT / 'data' / 'trials' / 'trial_registry.jsonl')}")

    print("=" * 80)
    print(f"PHASE 3B-2b BASELINE RUN COMPLETE — VERDICT: {v.overall_verdict.value}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())

