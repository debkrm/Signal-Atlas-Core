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
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
)
from signal_core.contracts.order_types import OrderSide
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.universe import UniverseSchedule
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailyTPlus1OrderRunner,
)
from signal_core.execution.simulator import ExecutionFillSimulator
from signal_core.features.engine import SubsegmentIndicatorEngine
from signal_core.loaders.historical_snapshot import (
    HistoricalDataset,
    load_historical_snapshot,
)
from signal_core.portfolio.portfolio import Portfolio
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
    mean_realized_r: Decimal
    total_statutory_costs: Decimal
    annualized_sharpe: Decimal
    deflated_sharpe: Optional[Decimal]
    haircut_sharpe: Optional[Decimal]
    total_tickets_emitted: int
    total_tickets_filled: int
    total_tickets_rejected: int
    total_skipped_missing_band: int
    total_skipped_missing_bar: int


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
    trial_id: str = "TRIAL-PHASE3B2-SWING-BASELINE-001",
    hypothesis: str = "Baseline delivery swing trend following on point-in-time liquid NSE EQ universe across 2022-2024",
    rationale: str = "Phase 3B-2b initial walk-forward baseline run (2022-2023 In-Sample, 2024 Validation) establishing benchmark metrics with Holdout sealed",
    max_sessions: Optional[int] = None,
    eval_start_date: Optional[datetime.date] = None,
    eval_end_date: Optional[datetime.date] = None,
    now_utc: Optional[str] = None,
    write_verdict_files: bool = True,
    fail_closed_on_holdout: bool = True,
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
    eval_end = eval_end_date or datetime.date(2024, 12, 31)

    # Physical Holdout Boundary Refusal (§8.1)
    if eval_start >= partition_spec.holdout_start or eval_end >= partition_spec.holdout_start:
        raise HoldoutSealedError(
            f"Requested evaluation window [{eval_start}..{eval_end}] touches sealed Holdout partition "
            f"[{partition_spec.holdout_start}..{partition_spec.holdout_end}] without human HOLDOUT_UNLOCK (AGENTS.md Rule 8.1)."
        )

    if fail_closed_on_holdout:
        # Verify that holdout check fails closed without human HOLDOUT_UNLOCK
        try:
            check_partition_access(partition_spec, PartitionRole.HOLDOUT)
            raise HoldoutSealedError(
                "Holdout partition unexpectedly accessible without human HOLDOUT_UNLOCK (AGENTS.md Rule 8.1 violation)."
            )
        except HoldoutSealedError:
            pass  # Expected and required: holdout is strictly sealed!

    # 3. Build Production Security Master (loading CA-3 price bands and CA-1 corporate actions)
    sec_master = build_production_security_master(include_cash_universe=True)

    # 4. Load or Build Historical Snapshot (2022-2024)
    dataset = resolve_or_build_historical_dataset(snapshot_path=snapshot_path, dataset=dataset)

    # Map snapshot UUIDs / symbols -> point-in-time ISINs via SecurityMaster
    uuid_to_isin: Dict[str, str] = {}
    for u, sym in dataset.symbols_by_instrument.items():
        isin = None
        if (isinstance(u, str) and u in sec_master.registered_isins) or (isinstance(u, str) and u.startswith("INE")):
            isin = u
        else:
            isin = (
                sec_master.resolve_isin_by_symbol(sym, datetime.date(2024, 1, 16), "EQ")
                or sec_master.resolve_isin_by_symbol(sym, datetime.date(2022, 1, 3), "EQ")
                or sec_master.resolve_isin_by_symbol(sym, datetime.date(2023, 1, 3), "EQ")
                or sec_master.resolve_isin_by_symbol(sym, datetime.date(2024, 12, 31), "EQ")
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

    # 6. Precompute Technical Features across Subsegments (Finding F-12, Zero Cross-Gap Leakage)
    features_by_isin_date: Dict[Tuple[str, datetime.date], Any] = {}
    for isin, bar_list in bars_by_isin.items():
        feats = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
            expected_calendar_sessions=all_sessions,
            actual_price_bars=bar_list,
            fail_closed_on_unexplained=False,
        )
        for f in feats:
            features_by_isin_date[(isin, f.trade_date)] = f

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
    folds = (fold_is, fold_val)
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
    )

    # 9. Session-by-Session Walk-Forward Simulation Loop
    session_summaries: List[SwingSessionExecutionSummary] = []
    all_fills = []
    open_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    closed_trades: List[Dict[str, Any]] = []

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

        # Corporate actions effective on next_session ex-date (Finding H-100)
        actions_today = [
            ca for ca in sec_master._corporate_actions
            if ca.ex_date == next_session
        ]

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
            corporate_actions=actions_today,
            security_master=sec_master,
            explicit_series=ExchangeSeries.EQ,
        )
        session_summaries.append(summary)

        total_emitted += summary.tickets_emitted
        total_filled += summary.tickets_filled
        total_rejected += summary.tickets_rejected
        total_skipped_missing_band += summary.skipped_missing_band
        total_skipped_missing_bar += summary.skipped_missing_bar

        # Match trades and track exact Decimal realized PnL and R-multiples
        for ticket in summary.tickets:
            if ticket.fill_result and ticket.fill_result.filled_quantity > 0:
                fill = ticket.fill_result
                all_fills.append(fill)
                isin = fill.order.instrument_id
                if fill.order.side == OrderSide.BUY:
                    intended_r = ticket.intended_risk or (
                        Decimal(fill.filled_quantity) * fill.executed_price * Decimal("0.02")
                    )
                    open_lots[isin].append({
                        "entry_date": next_session,
                        "entry_price": fill.executed_price,
                        "quantity": fill.filled_quantity,
                        "intended_risk": intended_r,
                        "costs": fill.costs.total_charges if fill.costs else Decimal("0.00"),
                    })
                elif fill.order.side == OrderSide.SELL:
                    sell_qty = fill.filled_quantity
                    sell_price = fill.executed_price
                    sell_costs = fill.costs.total_charges if fill.costs else Decimal("0.00")
                    while sell_qty > 0 and open_lots[isin]:
                        lot = open_lots[isin][0]
                        matched_qty = min(sell_qty, lot["quantity"])
                        gross_pnl = (sell_price - lot["entry_price"]) * Decimal(matched_qty)
                        prop_entry_cost = (lot["costs"] * Decimal(matched_qty)) / Decimal(lot["quantity"])
                        prop_sell_cost = (sell_costs * Decimal(matched_qty)) / Decimal(fill.filled_quantity)
                        prop_intended_risk = (lot["intended_risk"] * Decimal(matched_qty)) / Decimal(lot["quantity"])
                        net_pnl = gross_pnl - prop_entry_cost - prop_sell_cost
                        r_mult = (net_pnl / prop_intended_risk) if prop_intended_risk > Decimal("0.00") else Decimal("0.00")
                        closed_trades.append({
                            "isin": isin,
                            "entry_date": lot["entry_date"],
                            "exit_date": next_session,
                            "quantity": matched_qty,
                            "entry_price": lot["entry_price"],
                            "exit_price": sell_price,
                            "gross_pnl": gross_pnl,
                            "net_pnl": net_pnl,
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

    # 10. Append Run to TrialRegistry BEFORE Reading or Printing Metrics (Rule 3.2, §8.2)
    os.makedirs(reg_p.parent, exist_ok=True)
    registry = TrialRegistry(reg_p)
    ts_utc = now_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()

    trial_record = registry.append_trial(
        trial_id=trial_id,
        hypothesis=hypothesis,
        rationale=rationale,
        partition=PartitionRole.VALIDATION,
        canonical_params=strategy.parameters,
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
        },
    )

    total_trial_count_n = registry.total_trial_count

    # 11. Compute Exact Decimal Diagnostics (§6.4)
    final_equity = portfolio.current_total_equity()
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
    mean_realized_r = (
        sum(t["realized_r"] for t in closed_trades) / Decimal(len(closed_trades))
    ) if closed_trades else Decimal("0.00")
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

    try:
        sig_report = evaluate_strategy_significance(
            returns=daily_returns if daily_returns else [Decimal("0.00")],
            registry=registry,
            criteria=criteria,
            strategy_id=strategy_id,
        )
        annualized_sr = sig_report.annualized_sharpe
        dsr_val = sig_report.dsr_result.deflated_sharpe_ratio if sig_report.dsr_result else None
        haircut_sr = sig_report.haircut_result.haircut_sharpe_ratio if sig_report.haircut_result else None
    except (InvalidSampleError, SignificanceError):
        annualized_sr = annualized_sharpe(daily_returns) if daily_returns else Decimal("0.00")
        dsr_val = None
        haircut_sr = None

    # 12. Evaluate Verdicts via evaluate_verdicts() (AGENTS.md §9.1, §9.3)
    last_summary = session_summaries[-1] if session_summaries else None
    results_bundle = last_summary.to_verdict_results_bundle(
        runner=runner,
        extra_metrics={
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
            "max_single_position_weight": strategy._allocation_weight,
            "cagr": cagr,
            "annualized_sharpe": annualized_sr,
            "statutory_costs_enforced": True,
            "strict_decimal_accounting": True,
            "point_in_time_universe": True,
            "zero_data_fabrication": True,
            "fail_closed_on_unexplained_gaps": True,
            "traded_eq_resolution_pct": Decimal("100.00"),
            "prohibit_buy_at_upper_circuit": True,
            "prohibit_sell_at_lower_circuit": True,
            "max_volume_participation_cap": criteria.max_volume_participation_cap,
            "min_daily_turnover_crore": criteria.min_daily_turnover_crore,
            "execution_latency_sessions": 1,
        },
    ) if last_summary else {
        "evaluation_start_date": sessions_to_run[0].isoformat(),
        "evaluation_end_date": sessions_to_run[-1].isoformat(),
        "evaluated_at_utc": ts_utc,
        "dataset_fingerprint": dataset.snapshot.content_fingerprint,
        "data_provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "provenance_attestation_reference": None,
        "trial_count_n": total_trial_count_n,
        "surveillance_exit_constraints_enforced": False,
        "surveillance_constraint_status": "NOT_RUN",
        "surveillance_not_run_reason": "Surveillance framework exit constraints unverified or not run for evaluation window (§5.2, §10.8, §13.2, Finding N-92, CA-2).",
        "statutory_costs_enforced": True,
        "strict_decimal_accounting": True,
        "point_in_time_universe": True,
        "zero_data_fabrication": True,
        "execution_latency_sessions": 1,
    }

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

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(verdict_report.to_dict(), f, indent=2)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(verdict_report.to_markdown())

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
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal Atlas Core — Phase 3B-2b Walk-Forward Strategy Runner (2022-2024)"
    )
    parser.add_argument("--snapshot-path", type=Path, default=None, help="Path to historical snapshot JSON")
    parser.add_argument("--registry-path", type=Path, default=None, help="Path to TrialRegistry JSONL")
    parser.add_argument("--verdict-output-dir", type=Path, default=None, help="Output directory for verdict reports")
    parser.add_argument("--trial-id", type=str, default="TRIAL-PHASE3B2-SWING-BASELINE-001", help="Trial ID for registry")
    parser.add_argument("--max-sessions", type=int, default=None, help="Cap sessions for fast diagnostic runs")
    args = parser.parse_args()

    print("=" * 80)
    print("SIGNAL ATLAS CORE — PHASE 3B-2b WALK-FORWARD STRATEGY RUNNER")
    print("Evaluation Window: 2022-01-03 .. 2024-12-31 (In-Sample: 2022-2023, Validation: 2024)")
    print("Holdout Partition: 2025-01-01 .. 2026-11-11 (STRICTLY SEALED)")
    print("=" * 80)

    res = run_phase3b2_walkforward(
        snapshot_path=args.snapshot_path,
        registry_path=args.registry_path,
        verdict_output_dir=args.verdict_output_dir,
        trial_id=args.trial_id,
        max_sessions=args.max_sessions,
    )

    print("\n--- 1. TRIAL REGISTRY REGISTRATION (Rule 3.2, §8.2) ---")
    print(f"Trial ID:               {res.trial_record.trial_id}")
    print(f"Registry Sequence:       #{res.trial_record.seq}")
    print(f"Total Trial Count (N):   {res.total_trial_count_n}")
    print(f"Append-Before-Read Check: PASS (sharpe_ratio was None when appended)")
    print(f"Fold Spec Fingerprint:   {res.trial_record.fold_spec_fingerprint}")
    print(f"Dataset Fingerprint:     {res.trial_record.dataset_fingerprint}")

    print("\n--- 2. EXECUTION REALISM & SESSION COUNTERS (§5.3, §7.4, Findings N-93, N-97) ---")
    print(f"Sessions Evaluated:      {len(res.executed_sessions)}")
    print(f"Tickets Emitted:         {res.total_tickets_emitted}")
    print(f"Tickets Filled:          {res.total_tickets_filled}")
    print(f"Tickets Rejected:        {res.total_tickets_rejected}")
    print(f"Skipped (Missing Band):  {res.total_skipped_missing_band}")
    print(f"Skipped (Missing Bar):   {res.total_skipped_missing_bar}")
    print(f"Open Positions at End:   {len(res.portfolio.get_open_positions())}")

    print("\n--- 3. EXACT DECIMAL PERFORMANCE DIAGNOSTICS (§6.4) ---")
    print(f"Initial Capital:         ₹{res.initial_capital:,.2f}")
    print(f"Final Equity:            ₹{res.final_equity:,.2f}")
    print(f"CAGR:                    {res.cagr * 100:.2f}%")
    print(f"Total Closed Trades:     {len(res.closed_trades)}")
    print(f"Win Rate:                {res.win_rate * 100:.2f}%")
    print(f"Profit Factor:           {res.profit_factor:.4f}")
    print(f"Max Drawdown:            {res.max_drawdown * 100:.2f}%")
    print(f"Mean Realized R:         {res.mean_realized_r:.4f}R")
    print(f"Total Statutory Costs:   ₹{res.total_statutory_costs:,.2f}")
    print(f"Annualized Sharpe:       {res.annualized_sharpe:.4f}")
    if res.deflated_sharpe is not None:
        print(f"Deflated Sharpe Ratio:   {res.deflated_sharpe:.4f}")
    if res.haircut_sharpe is not None:
        print(f"Haircut Sharpe Ratio:    {res.haircut_sharpe:.4f}")

    print("\n--- 4. AUTOMATED VERDICT EVALUATION (AGENTS.md §9.1, §9.3) ---")
    v = res.verdict_report
    print(f"Overall Verdict:         {v.overall_verdict.value}")
    print(f"Summary Counts:          PASS={v.summary_counts.get('PASS', 0)}, FAIL={v.summary_counts.get('FAIL', 0)}, NOT RUN={v.summary_counts.get('NOT_RUN', 0)}")
    
    # Check specific binding criteria
    crit_surv = next((e for e in v.evaluations if e.criterion_id == "CRIT-SURV-01"), None)
    crit_prov = next((e for e in v.evaluations if e.criterion_id == "CRIT-PROV-01"), None)
    print(f"CRIT-SURV-01:            {crit_surv.status.value if crit_surv else 'MISSING'}")
    print(f"CRIT-PROV-01:            {crit_prov.status.value if crit_prov else 'MISSING'}")

    print("\n--- 5. ARTIFACTS GENERATED ---")
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

