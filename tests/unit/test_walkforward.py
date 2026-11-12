"""
Unit Tests for Phase 2C Walk-Forward Engine and Execution Invariants.

Covers:
- Gate G2C-1: Bit-for-bit determinism across reruns with identical inputs.
- Gate G2C-2: Strict rejection of same-session (T close -> T fill) or lookahead intents.
- Gate G2C-3: Eligibility policy enforcement (APPROVED_EQ_ONLY_POLICY; ineligible scrips fail closed).
- Gate G2C-4: Circuit evidence audit (missing circuit depth flagged CIRCUIT_UNVERIFIED).
- Gate G2C-5: Single authoritative execution simulator and portfolio ledger integration.
- Registration of WalkForwardResult into Phase 2A TrialRegistry.
"""

import dataclasses
import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import pytest

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    SeriesEligibilityPolicy,
)
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.execution.costs import TransactionCostBreakdown, TransactionCostModel
from signal_core.execution.types import ExecutionOrder, FillStatus, OrderProduct, OrderSide, OrderType
from signal_core.execution.simulator import ExecutionFillResult
from signal_core.portfolio.portfolio import Portfolio, PortfolioRiskLimitError
from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    WalkForwardFold,
)
from signal_core.research.trials import TrialRegistry
from signal_core.research.walkforward import (
    FoldExecutionResult,
    WalkForwardEngine,
    WalkForwardEngineError,
    WalkForwardLookaheadError,
    WalkForwardEligibilityError,
    WalkForwardResult,
    compute_compounded_annualized_return,
)
from signal_core.storage.calendar import (
    SessionType,
    TradingCalendar,
    TradingSessionRecord,
    compute_calendar_fingerprint,
)
from signal_core.storage.gold import GoldEngine
from signal_core.storage.security_master import (
    SecurityMaster,
    SymbolInterval,
    build_production_security_master,
)
from signal_core.storage.silver import SilverRecord, SilverStorage
from signal_core.strategy.base import (
    OrderIntent,
    Strategy,
    TechnicalCrossStrategy,
)


@pytest.fixture
def wf_calendar() -> TradingCalendar:
    """10-session January 2024 test calendar."""
    dates = [
        datetime.date(2024, 1, 8),
        datetime.date(2024, 1, 9),
        datetime.date(2024, 1, 10),
        datetime.date(2024, 1, 11),
        datetime.date(2024, 1, 12),
        datetime.date(2024, 1, 15),
        datetime.date(2024, 1, 16),
        datetime.date(2024, 1, 17),
        datetime.date(2024, 1, 18),
        datetime.date(2024, 1, 19),
    ]
    records = tuple(
        TradingSessionRecord(d, SessionType.FULL, datetime.time(9, 15), datetime.time(15, 30), "Regular")
        for d in dates
    )
    fpr = compute_calendar_fingerprint(records)
    return TradingCalendar(
        calendar_id="WF-TEST-CAL",
        market="NSE_CASH",
        session_records=records,
        binding_start_date=datetime.date(2018, 4, 1),
        fingerprint=fpr,
        provenance={"source": "WF_TEST"},
        annual_session_counts={"2024": 10},
    )


@pytest.fixture
def wf_environment(wf_calendar):
    """Sets up temporary Silver partitions, SecurityMaster, and GoldEngine."""
    with tempfile.TemporaryDirectory(prefix="wf_test_") as tmpdir:
        tmp_path = Path(tmpdir)
        silver_dir = tmp_path / "silver"

        silver = SilverStorage(silver_dir, calendar=wf_calendar)
        sec_master = SecurityMaster(
            symbol_intervals=[
                SymbolInterval(
                    isin="INE009A01021",
                    symbol="INFY",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
                SymbolInterval(
                    isin="INE002A01018",
                    symbol="RELIANCE",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
                SymbolInterval(
                    isin="INE999B01019",
                    symbol="TESTBE",
                    series="BE",  # Ineligible Trade-to-Trade series
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
            ]
        )

        # Seed 10 sessions of data for INFY (INE009A01021), RELIANCE (INE002A01018), and TESTBE (INE999B01019)
        base_infy = Decimal("1500.00")
        base_rel = Decimal("2500.00")
        base_be = Decimal("500.00")

        for i, session_date in enumerate(wf_calendar.sessions):
            p_infy = base_infy + Decimal(str(i * 10))
            p_rel = base_rel - Decimal(str(i * 15))
            p_be = base_be + Decimal(str(i * 5))

            records = [
                SilverRecord(
                    isin="INE009A01021",
                    symbol="INFY",
                    series="EQ",
                    trade_date=session_date,
                    open=p_infy,
                    high=p_infy + Decimal("15.00"),
                    low=p_infy - Decimal("10.00"),
                    close=p_infy + Decimal("5.00"),
                    volume=500000,
                    traded_value=p_infy * Decimal("500000"),
                ),
                SilverRecord(
                    isin="INE002A01018",
                    symbol="RELIANCE",
                    series="EQ",
                    trade_date=session_date,
                    open=p_rel,
                    high=p_rel + Decimal("20.00"),
                    low=p_rel - Decimal("10.00"),
                    close=p_rel - Decimal("5.00"),
                    volume=300000,
                    traded_value=p_rel * Decimal("300000"),
                ),
                SilverRecord(
                    isin="INE999B01019",
                    symbol="TESTBE",
                    series="BE",
                    trade_date=session_date,
                    open=p_be,
                    high=p_be + Decimal("10.00"),
                    low=p_be - Decimal("10.00"),
                    close=p_be,
                    volume=100000,
                    traded_value=p_be * Decimal("100000"),
                ),
            ]
            silver.write_daily_partition(session_date, records)

        gold = GoldEngine(silver, wf_calendar, sec_master)
        yield wf_calendar, sec_master, silver, gold, tmp_path


def test_gate_g2c_1_bit_for_bit_determinism(wf_environment):
    """
    Gate G2C-1: Identical inputs reproduce bit-for-bit identical results and fingerprints.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(
        strategy_id="DETERMINISM-TEST",
        fast_indicator="open",
        slow_indicator="low",
        allocation_weight=Decimal("0.08"),
    )

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    res1 = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=Decimal("1000000.00"))
    res2 = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=Decimal("1000000.00"))

    # Assert live trades executed (G-8)
    assert len(res1.aggregate_trades) > 0
    assert any(t.status == FillStatus.FILLED for t in res1.aggregate_trades)

    # Assert bit-for-bit identity across outputs
    assert res1.fingerprint == res2.fingerprint
    assert res1.final_equity == res2.final_equity
    assert res1.annualized_sharpe == res2.annualized_sharpe
    assert res1.total_return == res2.total_return
    assert res1.max_drawdown == res2.max_drawdown
    assert len(res1.aggregate_trades) == len(res2.aggregate_trades)

    # Assert authentic Gold dataset binding (G-4)
    assert res1.dataset_content_fingerprint.startswith("DATA-CTNT-V2-")
    assert res1.dataset_content_fingerprint != "DATA-CTNT-V2-UNKNOWN"


def test_gate_g2c_2_same_session_lookahead_rejection(wf_environment):
    """
    Gate G2C-2: Attempted same-session execution (T close -> T fill) is rejected fail-closed.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    # Rogue strategy attempting same-session fill (signal on T, target on T)
    class RogueSameSessionStrategy(Strategy):
        @property
        def strategy_id(self) -> str:
            return "ROGUE-SAME-SESSION"

        def generate_signals(self, as_of, next_session, universe, features):
            # Attempt to emit intent targeting the same session (T close -> T fill)
            # Note: OrderIntent itself rejects target_date <= signal_date
            return ()

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    # Directly test that if any intent with target_date <= as_of is evaluated by the engine, it raises WalkForwardLookaheadError
    t = datetime.date(2024, 1, 15)
    class MockIntent:
        instrument_id = "INE009A01021"
        signal_date = t
        target_date = t
        side = OrderSide.BUY

    class BypassStrategy(Strategy):
        @property
        def strategy_id(self) -> str:
            return "BYPASS-LOOKAHEAD"

        def generate_signals(self, as_of, next_session, universe, features):
            return (MockIntent(),)  # type: ignore

    with pytest.raises(WalkForwardLookaheadError, match="Gate G2C-2 Violation"):
        engine.run_walk_forward(strategy=BypassStrategy(), folds=[fold])


def test_gate_g2c_3_eligibility_enforcement(wf_environment):
    """
    Gate G2C-3: No fill lands outside the eligibility policy (APPROVED_EQ_ONLY_POLICY).
    Attempted trades in ineligible series (e.g. BE) are rejected fail-closed.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    be_isin = "INE999B01019"
    engine = WalkForwardEngine(
        calendar=cal,
        gold_engine=gold,
        eligibility_policy=APPROVED_EQ_ONLY_POLICY,
    )

    # Strategy that tries to buy BE instrument
    class BESeriesStrategy(Strategy):
        @property
        def strategy_id(self) -> str:
            return "BE-SERIES-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            return (
                OrderIntent(
                    instrument_id=be_isin,
                    signal_date=as_of,
                    target_date=next_session,
                    side=OrderSide.BUY,
                    quantity=50,
                ),
            )

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    res = engine.run_walk_forward(strategy=BESeriesStrategy(), folds=[fold], isins=[be_isin, "INE009A01021"])
    # Verify that NO fill occurred for BE scrip
    be_fills = [t for t in res.aggregate_trades if t.order.instrument_id == be_isin and t.status == FillStatus.FILLED]
    assert len(be_fills) == 0


def test_gate_g2c_4_circuit_evidence_audit(wf_environment):
    """
    Gate G2C-4: Results whose fills lack circuit evidence are flagged CIRCUIT_UNVERIFIED
    and cannot be promoted to VERIFIED.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    # Simple buyer strategy
    class SimpleBuyer(Strategy):
        @property
        def strategy_id(self) -> str:
            return "SIMPLE-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            if as_of == datetime.date(2024, 1, 15):
                return (
                    OrderIntent(
                        instrument_id="INE009A01021",
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=10,
                    ),
                )
            return ()

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    res = engine.run_walk_forward(strategy=SimpleBuyer(), folds=[fold])

    # Because daily bhavcopy partition currently lacks verified upper/lower circuit columns in raw parquet,
    # circuit_evidence_present is False on the fills.
    # Gate G2C-4 mandates: circuit_evidence_complete must be False and verification_status must be CIRCUIT_UNVERIFIED!
    assert res.circuit_evidence_complete is False
    assert res.verification_status == "CIRCUIT_UNVERIFIED"


def test_gate_g2c_5_single_authoritative_engine_and_portfolio_integration(wf_environment):
    """
    Gate G2C-5: Every trade routes through ExecutionFillSimulator and posts to Portfolio CashLedger.
    Statutory costs and slippage are correctly deducted from cash.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    class SingleTradeBuyer(Strategy):
        @property
        def strategy_id(self) -> str:
            return "SINGLE-TRADE-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            if as_of == datetime.date(2024, 1, 15):
                return (
                    OrderIntent(
                        instrument_id="INE009A01021",
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=50,
                    ),
                )
            return ()

    initial_capital = Decimal("1000000.00")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    res = engine.run_walk_forward(strategy=SingleTradeBuyer(), folds=[fold], initial_capital=initial_capital)

    fold_res = res.fold_results[0]
    filled_trades = [t for t in fold_res.trades if t.status == FillStatus.FILLED]
    assert len(filled_trades) == 1

    fill = filled_trades[0]
    assert fill.costs is not None
    assert fill.costs.total_charges > Decimal("0")
    assert fill.costs.stt > Decimal("0")

    # Verify that portfolio recorded the trade and snapshots reflect total equity
    assert len(fold_res.portfolio_snapshots) == 5
    first_snap = fold_res.portfolio_snapshots[0]
    second_snap = fold_res.portfolio_snapshots[1]

    # Fill executed on 2024-01-16 (session 2 of test window)
    assert second_snap.as_of_date == datetime.date(2024, 1, 16)
    assert second_snap.cash_balance < initial_capital  # Cash deducted for 50 shares + costs


def test_walk_forward_trial_registry_integration(wf_environment):
    """
    Verifies that WalkForwardResult exports a valid TrialRecord and directly registers
    into Phase 2A TrialRegistry with full hash chain integrity.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(
        strategy_id="REGISTRY-TEST-STRAT",
        fast_indicator="close",
        slow_indicator="open",
        allocation_weight=Decimal("0.10"),
    )

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    res = engine.run_walk_forward(strategy=strat, folds=[fold])

    registry_path = tmp_path / "trials.jsonl"
    registry = TrialRegistry(registry_path)

    record = res.register_in_trial_registry(
        registry=registry,
        trial_id="TRIAL-WF-001",
        hypothesis="Trend breakout on moving average cross",
        rationale="Preliminary walk-forward evaluation",
        fold_spec_fingerprint="FOLD-SPEC-V1-test",
        dataset_fingerprint="DATA-CTNT-V2-test",
        criteria_version="v1.0",
        partition="VALIDATION",
    )

    assert record.seq == 1
    assert record.trial_id == "TRIAL-WF-001"
    assert record.sharpe_ratio == res.annualized_sharpe
    assert registry.verify_integrity() is True
    assert registry.total_trial_count == 1


# ==============================================================================
# AUDIT §25 / §26 — GATE G-1 HOLDOUT CONTAINMENT & FOLD PARTITION ROLE TESTS
# ==============================================================================

def test_g1_unlabelled_fold_rejected_fail_closed(wf_environment):
    """
    Gate G-1 (Audit §25/§26): Unlabelled fold (partition_role=None) must be
    refused fail-closed with HoldoutSealedError. Unknown must not run.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    unlabelled_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=None,  # Explicitly unlabelled
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-UNLABELLED")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    # Must raise from run_fold
    with pytest.raises(HoldoutSealedError, match="unlabelled"):
        engine.run_fold(strat, unlabelled_fold)

    # Must raise from run_walk_forward
    with pytest.raises(HoldoutSealedError, match="unlabelled"):
        engine.run_walk_forward(strat, [unlabelled_fold])


def test_g1_holdout_fold_without_spec_rejected_fail_closed(wf_environment):
    """
    Gate G-1: Fold declared as HOLDOUT without supplying a PartitionSpec must
    be refused fail-closed with HoldoutSealedError.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    holdout_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.HOLDOUT,
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-HOLDOUT-NOSPEC")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    with pytest.raises(HoldoutSealedError):
        engine.run_fold(strat, holdout_fold)

    with pytest.raises(HoldoutSealedError):
        engine.run_walk_forward(strat, [holdout_fold])


def test_g1_fold_intersecting_holdout_window_without_unlock_rejected_fail_closed(wf_environment):
    """
    Gate G-1: Fold whose window intersects PartitionRole.HOLDOUT without an unlock path
    must be refused fail-closed with HoldoutSealedError.
    """
    import hashlib
    cal, sec_master, silver, gold, tmp_path = wf_environment

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-TEST",
        holdout_token_hash=hashlib.sha256(b"secret-human-token-12345").hexdigest(),
        in_sample_start=datetime.date(2024, 1, 8),
        in_sample_end=datetime.date(2024, 1, 10),
        validation_start=datetime.date(2024, 1, 11),
        validation_end=datetime.date(2024, 1, 12),
        holdout_start=datetime.date(2024, 1, 15),
        holdout_end=datetime.date(2026, 11, 11),  # Widens holdout to include canonical 2025-2026 (Audit §28 C3)
    )

    holdout_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.HOLDOUT,
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-HOLDOUT-NOUNLOCK")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    # Attempt execution with spec but no unlock file path
    with pytest.raises(HoldoutSealedError, match="sealed"):
        engine.run_walk_forward(strat, [holdout_fold], partition_spec=spec, unlock_file_path=None)


def test_g1_fold_intersecting_holdout_window_with_mismatched_role_rejected_fail_closed(wf_environment):
    """
    Gate G-1: Fold intersecting the HOLDOUT window but falsely declared as VALIDATION
    must be refused fail-closed with HoldoutSealedError.
    """
    import hashlib
    cal, sec_master, silver, gold, tmp_path = wf_environment

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-TEST",
        holdout_token_hash=hashlib.sha256(b"secret-human-token-12345").hexdigest(),
        in_sample_start=datetime.date(2024, 1, 8),
        in_sample_end=datetime.date(2024, 1, 10),
        validation_start=datetime.date(2024, 1, 11),
        validation_end=datetime.date(2024, 1, 12),
        holdout_start=datetime.date(2024, 1, 15),
        holdout_end=datetime.date(2026, 11, 11),  # Widens holdout to include canonical 2025-2026 (Audit §28 C3)
    )

    # Date span [2024-01-08, 2024-01-19] intersects holdout [2024-01-15, 2024-01-19]
    # but role is declared as VALIDATION!
    mismatched_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-MISMATCHED-ROLE")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold, partition_spec=spec)

    with pytest.raises(HoldoutSealedError, match="intersects sealed HOLDOUT partition"):
        engine.run_walk_forward(strat, [mismatched_fold])


def test_g1_fold_intersecting_holdout_with_valid_unlock_permitted(wf_environment):
    """
    Gate G-1: Fold intersecting HOLDOUT window executes successfully when
    a verified human-created HOLDOUT_UNLOCK matching spec.holdout_token_hash is provided.
    """
    import hashlib
    cal, sec_master, silver, gold, tmp_path = wf_environment

    token_secret = "human-authorized-unsealing-2026"
    token_hash = hashlib.sha256(token_secret.encode("utf-8")).hexdigest()

    unlock_file = tmp_path / "HOLDOUT_UNLOCK"
    unlock_file.write_text(token_secret, encoding="utf-8")

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-TEST",
        holdout_token_hash=token_hash,
        in_sample_start=datetime.date(2024, 1, 8),
        in_sample_end=datetime.date(2024, 1, 10),
        validation_start=datetime.date(2024, 1, 11),
        validation_end=datetime.date(2024, 1, 12),
        holdout_start=datetime.date(2024, 1, 15),
        holdout_end=datetime.date(2026, 11, 11),  # Widens holdout to include canonical 2025-2026 (Audit §28 C3)
    )

    holdout_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.HOLDOUT,
    )

    strat = TechnicalCrossStrategy(
        strategy_id="TEST-AUTHORIZED-HOLDOUT",
        allocation_weight=Decimal("0.10"),
    )
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    res = engine.run_walk_forward(
        strategy=strat,
        folds=[holdout_fold],
        partition_spec=spec,
        unlock_file_path=unlock_file,
    )
    assert res is not None
    assert len(res.fold_results) == 1


def test_g1_validation_fold_outside_holdout_executes_cleanly(wf_environment):
    """
    Gate G-1: Validation fold strictly outside HOLDOUT window executes cleanly
    with PartitionSpec without requiring an unlock sentinel.
    """
    import hashlib
    cal, sec_master, silver, gold, tmp_path = wf_environment

    spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-TEST",
        holdout_token_hash=hashlib.sha256(b"secret-holdout-token").hexdigest(),
        in_sample_start=datetime.date(2024, 1, 8),
        in_sample_end=datetime.date(2024, 1, 10),
        validation_start=datetime.date(2024, 1, 11),
        validation_end=datetime.date(2024, 1, 19),
        holdout_start=datetime.date(2025, 1, 1),
        holdout_end=datetime.date(2026, 11, 11),
    )

    val_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-VALIDATION-OK", allocation_weight=Decimal("0.10"))
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    # Must execute cleanly with spec and NO unlock file path
    res = engine.run_walk_forward(strat, [val_fold], partition_spec=spec)
    assert res is not None
    assert len(res.fold_results) == 1


def test_h2_p2_no_spec_validation_role_intersecting_canonical_holdout_rejected_fail_closed(wf_environment):
    """
    Finding H-2 / Probe P2: With NO partition_spec passed, a fold whose dates intersect
    the canonical holdout window (2025+) with role VALIDATION must NOT run.
    It must be refused fail-closed with HoldoutSealedError via the canonical spec default.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    # Fold spanning 2025 dates (canonical holdout window: 2025-01-01 -> 2026-11-11)
    holdout_dates_fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2025, 1, 6),
        train_end=datetime.date(2025, 1, 10),
        test_start=datetime.date(2025, 1, 13),
        test_end=datetime.date(2025, 1, 17),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,  # Mislabeled or default validation role
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-H2-P2", allocation_weight=Decimal("0.10"))
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)  # Uses canonical spec default

    # Must raise HoldoutSealedError fail-closed even when partition_spec is omitted
    with pytest.raises(HoldoutSealedError, match="intersects sealed HOLDOUT partition"):
        engine.run_fold(strat, holdout_dates_fold)

    with pytest.raises(HoldoutSealedError, match="intersects sealed HOLDOUT partition"):
        engine.run_walk_forward(strat, [holdout_dates_fold], partition_spec=None)


def test_h2_absent_spec_refuses_fail_closed(wf_environment):
    """
    Finding H-2: If no authoritative PartitionSpec can be resolved, execution must
    refuse fail-closed rather than defaulting to open.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-H2-NO-SPEC")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    object.__setattr__(engine, "_partition_spec", None)

    with pytest.raises(HoldoutSealedError, match="without an authoritative PartitionSpec"):
        engine.run_fold(strat, fold, partition_spec=None)

    with pytest.raises(HoldoutSealedError, match="without an authoritative PartitionSpec"):
        engine.run_walk_forward(strat, [fold], partition_spec=None)


def test_c3_p11_caller_spec_narrowing_canonical_holdout_rejected_fail_closed(wf_environment):
    """
    Criterion C3 / Probe P11 (Audit §28): An explicit caller-supplied PartitionSpec
    cannot narrow or shift the sealed holdout window away from [2025-01-01, 2026-11-11].
    Any override that attempts to narrow the window must be refused fail-closed.
    """
    import hashlib
    cal, sec_master, silver, gold, tmp_path = wf_environment

    # Probe P11 attempt: caller sets holdout_start=2030 to bypass 2025 holdout
    narrow_spec = PartitionSpec(
        dataset_fingerprint="DATA-CTNT-V2-TEST",
        holdout_token_hash=hashlib.sha256(b"token").hexdigest(),
        in_sample_start=datetime.date(2024, 1, 8),
        in_sample_end=datetime.date(2024, 1, 10),
        validation_start=datetime.date(2024, 1, 11),
        validation_end=datetime.date(2024, 1, 12),
        holdout_start=datetime.date(2030, 1, 1),
        holdout_end=datetime.date(2031, 12, 31),
    )

    strat = TechnicalCrossStrategy(strategy_id="TEST-C3-P11")
    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    # 1. Refused at engine instantiation
    with pytest.raises(HoldoutSealedError, match="cannot narrow or shift canonical holdout window"):
        WalkForwardEngine(calendar=cal, gold_engine=gold, partition_spec=narrow_spec)

    # 2. Refused if passed explicitly to run_walk_forward
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    with pytest.raises(HoldoutSealedError, match="cannot narrow or shift canonical holdout window"):
        engine.run_walk_forward(strat, [fold], partition_spec=narrow_spec)

    # 3. Refused if passed explicitly to run_fold
    with pytest.raises(HoldoutSealedError, match="cannot narrow or shift canonical holdout window"):
        engine.run_fold(strat, fold, partition_spec=narrow_spec)


def test_wave2_risk_limit_fill_rejection(wf_environment):
    """
    G-3, G-9: Orders exceeding portfolio risk limits (e.g. single position cap 10%)
    are rejected with FillStatus.REJECTED_RISK_LIMIT rather than crashing the engine.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    class OversizedBuyer(Strategy):
        @property
        def strategy_id(self) -> str:
            return "OVERSIZED-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            if as_of == datetime.date(2024, 1, 15):
                # Request 200 shares @ ~1570 = ~314,000 INR on 1,000,000 capital (31.4% > 10% limit)
                return (
                    OrderIntent(
                        instrument_id="INE009A01021",
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=200,
                    ),
                )
            return ()

    initial_capital = Decimal("1000000.00")
    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    res = engine.run_walk_forward(strategy=OversizedBuyer(), folds=[fold], initial_capital=initial_capital)

    fold_res = res.fold_results[0]
    # Trade was rejected under risk limits, not crashed
    assert len(fold_res.trades) == 1
    rejected_trade = fold_res.trades[0]
    assert rejected_trade.status == FillStatus.REJECTED_RISK_LIMIT
    assert rejected_trade.filled_quantity == 0
    # Portfolio equity untouched
    assert res.final_equity == initial_capital
    assert fold_res.portfolio_snapshots[-1].total_portfolio_value == initial_capital
    assert all(snap.cash_balance == initial_capital for snap in fold_res.portfolio_snapshots)


def test_wave2_latency_realism_dispatch(wf_environment):
    """
    G-5: execution_latency_sessions actively controls order dispatch session:
    L=1 -> target session is t+1; L=2 -> target session is t+2.
    L=0 is clamped to max(1, L).
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    class SingleTradeBuyer(Strategy):
        @property
        def strategy_id(self) -> str:
            return "SINGLE-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            if as_of == datetime.date(2024, 1, 15):
                return (
                    OrderIntent(
                        instrument_id="INE009A01021",
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=10,
                    ),
                )
            return ()

    # L=1: signal on Jan 15 executes on Jan 16
    engine_l1 = WalkForwardEngine(calendar=cal, gold_engine=gold, execution_latency_sessions=1)
    res_l1 = engine_l1.run_walk_forward(strategy=SingleTradeBuyer(), folds=[fold])
    fills_l1 = [t for t in res_l1.fold_results[0].trades if t.status == FillStatus.FILLED]
    assert len(fills_l1) == 1
    assert fills_l1[0].fill_date == datetime.date(2024, 1, 16)
    assert fills_l1[0].latency_sessions == 1

    # L=2: signal on Jan 15 executes on Jan 17
    engine_l2 = WalkForwardEngine(calendar=cal, gold_engine=gold, execution_latency_sessions=2)
    res_l2 = engine_l2.run_walk_forward(strategy=SingleTradeBuyer(), folds=[fold])
    fills_l2 = [t for t in res_l2.fold_results[0].trades if t.status == FillStatus.FILLED]
    assert len(fills_l2) == 1
    assert fills_l2[0].fill_date == datetime.date(2024, 1, 17)
    assert fills_l2[0].latency_sessions == 2

    # L=0 clamped to L=1
    engine_l0 = WalkForwardEngine(calendar=cal, gold_engine=gold, execution_latency_sessions=0)
    assert engine_l0._latency == 1


def test_wave2_dataset_content_fingerprint_binding_and_rejection(wf_environment):
    """
    G-4: Dataset content fingerprint is automatically resolved from GoldEngine snapshot
    and bound to results and trial records. Attempting to pass or register UNKNOWN or invalid
    fingerprint fails closed.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    strat = TechnicalCrossStrategy(
        strategy_id="BINDING-TEST",
        fast_indicator="open",
        slow_indicator="low",
        allocation_weight=Decimal("0.08"),
    )

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)
    res = engine.run_walk_forward(strategy=strat, folds=[fold])

    # Verified automatic binding
    expected_snap, _ = gold.build_dataset_snapshot(
        start_date=fold.train_start,
        end_date=fold.test_end,
        isins=sec_master.registered_isins,
    )
    expected_dataset_fp = expected_snap.content_fingerprint
    assert res.dataset_content_fingerprint == expected_dataset_fp
    assert res.dataset_content_fingerprint.startswith("DATA-CTNT-V2-")

    # Bound in exported trial record
    trial_rec = res.to_trial_record(
        trial_id="TRIAL-BINDING-01",
        hypothesis="Testing dataset binding in trial record",
        rationale="Wave 2 verification",
        fold_spec_fingerprint="TEST-FOLD-FPR",
    )
    assert trial_rec.dataset_fingerprint == expected_dataset_fp

    # Rejection of explicit UNKNOWN fingerprint
    with pytest.raises(WalkForwardEngineError, match="Invalid dataset_content_fingerprint"):
        engine.run_walk_forward(
            strategy=strat,
            folds=[fold],
            dataset_content_fingerprint="DATA-CTNT-V2-UNKNOWN",
        )

    # Rejection of UNKNOWN fingerprint in to_trial_record
    tampered_res = dataclasses.replace(res, dataset_content_fingerprint="DATA-CTNT-V2-UNKNOWN")
    with pytest.raises(WalkForwardEngineError, match="Cannot create TrialRecord with invalid dataset_fingerprint"):
        tampered_res.to_trial_record(
            trial_id="TRIAL-FAIL-01",
            hypothesis="Should fail",
            rationale="Fail test",
            fold_spec_fingerprint="TEST-FOLD-FPR",
        )


def test_wave2_circuit_freeze_refusal_and_zero_trade_status(wf_calendar, tmp_path):
    """
    G-6, G2C-4, Rule 5.3:
    1. Zero-trade runs must report verification_status = 'NOT RUN'.
    2. Buy at upper circuit limit is refused fail-closed (REJECTED_UPPER_CIRCUIT).
    3. Trade with complete circuit bands achieves verification_status = 'VERIFIED'.
    """
    silver_dir = tmp_path / "silver_circuit"
    silver = SilverStorage(silver_dir, calendar=wf_calendar)

    # Seed INFY price observations
    base_infy = Decimal("1500.00")
    for i, d in enumerate(wf_calendar.sessions):
        p = base_infy + Decimal(str(i * 10))
        rec = SilverRecord(
            isin="INE009A01021",
            symbol="INFY",
            series="EQ",
            trade_date=d,
            open=p,
            high=p + Decimal("15.00"),
            low=p - Decimal("10.00"),
            close=p + Decimal("5.00"),
            volume=500000,
            traded_value=p * Decimal("500000"),
        )
        silver.write_daily_partition(d, [rec])

    fold = WalkForwardFold(
        fold_index=0,
        train_start=datetime.date(2024, 1, 8),
        train_end=datetime.date(2024, 1, 11),
        test_start=datetime.date(2024, 1, 15),
        test_end=datetime.date(2024, 1, 19),
        embargo_sessions=1,
        partition_role=PartitionRole.VALIDATION,
    )

    # 1. Zero-trade strategy
    class ZeroTrader(Strategy):
        @property
        def strategy_id(self) -> str:
            return "ZERO-TRADER"

        def generate_signals(self, as_of, next_session, universe, features):
            return ()

    sec_master_empty = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE009A01021",
                symbol="INFY",
                series="EQ",
                effective_from=datetime.date(2024, 1, 1),
                effective_to=datetime.date(2024, 12, 31),
            )
        ]
    )
    gold_zero = GoldEngine(silver, wf_calendar, sec_master_empty)
    engine_zero = WalkForwardEngine(calendar=wf_calendar, gold_engine=gold_zero)
    res_zero = engine_zero.run_walk_forward(strategy=ZeroTrader(), folds=[fold])
    assert res_zero.circuit_evidence_complete is False
    assert res_zero.verification_status == "NOT RUN"

    # 2. Upper Circuit Lock: on Jan 16 (i=6: p=1560, open=1560)
    # Upper circuit limit set at 1560.00 (equal to open)
    target_date = datetime.date(2024, 1, 16)
    band_upper_lock = PriceBandRecord(
        isin="INE009A01021",
        trade_date=target_date,
        series="EQ",
        upper_circuit_limit=Decimal("1560.00"),
        lower_circuit_limit=Decimal("1400.00"),
    )
    sec_master_upper_lock = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE009A01021",
                symbol="INFY",
                series="EQ",
                effective_from=datetime.date(2024, 1, 1),
                effective_to=datetime.date(2024, 12, 31),
            )
        ],
        price_bands=[band_upper_lock],
    )

    class SingleBuyer(Strategy):
        @property
        def strategy_id(self) -> str:
            return "SINGLE-BUYER"

        def generate_signals(self, as_of, next_session, universe, features):
            if as_of == datetime.date(2024, 1, 15):
                return (
                    OrderIntent(
                        instrument_id="INE009A01021",
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=10,
                    ),
                )
            return ()

    gold_upper = GoldEngine(silver, wf_calendar, sec_master_upper_lock)
    engine_upper = WalkForwardEngine(calendar=wf_calendar, gold_engine=gold_upper)
    res_upper = engine_upper.run_walk_forward(strategy=SingleBuyer(), folds=[fold])
    trades_upper = res_upper.fold_results[0].trades
    assert len(trades_upper) == 1
    assert trades_upper[0].status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert trades_upper[0].filled_quantity == 0

    # 3. Verified Circuit Evidence with normal bands
    normal_bands = [
        PriceBandRecord(
            isin="INE009A01021",
            trade_date=d,
            series="EQ",
            upper_circuit_limit=(base_infy + Decimal(str(i * 10))) * Decimal("1.10"),
            lower_circuit_limit=(base_infy + Decimal(str(i * 10))) * Decimal("0.90"),
            band_percentage=Decimal("10.0"),
        )
        for i, d in enumerate(wf_calendar.sessions)
    ]
    sec_master_verified = SecurityMaster(
        symbol_intervals=[
            SymbolInterval(
                isin="INE009A01021",
                symbol="INFY",
                series="EQ",
                effective_from=datetime.date(2024, 1, 1),
                effective_to=datetime.date(2024, 12, 31),
            )
        ],
        price_bands=normal_bands,
    )
    gold_verified = GoldEngine(silver, wf_calendar, sec_master_verified)
    engine_verified = WalkForwardEngine(calendar=wf_calendar, gold_engine=gold_verified)
    res_verified = engine_verified.run_walk_forward(strategy=SingleBuyer(), folds=[fold])
    trades_ver = [t for t in res_verified.fold_results[0].trades if t.status == FillStatus.FILLED]
    assert len(trades_ver) == 1
    assert res_verified.circuit_evidence_complete is True
    assert res_verified.verification_status == "VERIFIED"


def test_wave2_compounded_annualized_return():
    """
    G-7: compute_compounded_annualized_return uses exact Decimal geometric compounding:
    CAGR = (1 + R)^(sessions_per_year / num_sessions) - 1.
    """
    # 1. Zero sessions returns 0.0
    assert compute_compounded_annualized_return(Decimal("0.05"), 0) == Decimal("0.0")

    # 2. Exact match on known constant return:
    # 250 sessions with total return R = 0.20 -> annualized CAGR is exactly 0.20
    cagr_250 = compute_compounded_annualized_return(Decimal("0.20"), 250, sessions_per_year=250)
    assert cagr_250 == Decimal("0.2000000000000000000000000000")

    # 3. 10 sessions with R = 0.01:
    # (1 + 0.01)^(250 / 10) - 1 = (1.01)^25 - 1
    cagr_10 = compute_compounded_annualized_return(Decimal("0.01"), 10, sessions_per_year=250)
    expected_cagr = (Decimal("1.01") ** Decimal("25")) - Decimal("1.0")
    assert abs(cagr_10 - expected_cagr) < Decimal("1e-18")

    # 4. Total loss R <= -1 returns -1.00
    assert compute_compounded_annualized_return(Decimal("-1.0"), 10) == Decimal("-1.00")
    assert compute_compounded_annualized_return(Decimal("-1.5"), 10) == Decimal("-1.00")


def test_wave2_cash_sufficiency_check(wf_environment):
    """
    G-13: Portfolio.process_fill checks available cash before executing BUY fills,
    raising PortfolioRiskLimitError if outlay exceeds available cash balance.
    """
    cal, sec_master, silver, gold, tmp_path = wf_environment

    portfolio = Portfolio(
        initial_capital=Decimal("10000.00"),
        initial_date=datetime.date(2024, 1, 15),
    )

    cost_model = TransactionCostModel()
    costs = cost_model.compute_costs(
        trade_date=datetime.date(2024, 1, 16),
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=100,
        price=Decimal("1500.00"),
    )

    # Attempt to fill BUY order for 100 shares @ 1500 = 150,000 > 10,000 cash
    oversized_fill = ExecutionFillResult(
        order=ExecutionOrder(
            instrument_id="INE009A01021",
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=100,
            signal_date=datetime.date(2024, 1, 15),
            target_date=datetime.date(2024, 1, 16),
            order_type=OrderType.MARKET_ON_OPEN,
            order_id="ORD-OVER-CASH",
        ),
        status=FillStatus.FILLED,
        fill_date=datetime.date(2024, 1, 16),
        latency_sessions=1,
        filled_quantity=100,
        unfilled_quantity=0,
        executed_price=Decimal("1500.00"),
        slippage=None,
        costs=costs,
        circuit_evidence_present=True,
        rejection_reason=None,
    )

    with pytest.raises(PortfolioRiskLimitError, match="Insufficient cash for 'INE009A01021'"):
        portfolio.process_fill(oversized_fill)



