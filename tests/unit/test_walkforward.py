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
from signal_core.execution.types import FillStatus, OrderSide, OrderType
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
        fast_indicator="close",
        slow_indicator="open",
        allocation_weight=Decimal("0.20"),
    )

    engine = WalkForwardEngine(calendar=cal, gold_engine=gold)

    res1 = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=Decimal("1000000.00"))
    res2 = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=Decimal("1000000.00"))

    # Assert bit-for-bit identity across outputs
    assert res1.fingerprint == res2.fingerprint
    assert res1.final_equity == res2.final_equity
    assert res1.annualized_sharpe == res2.annualized_sharpe
    assert res1.total_return == res2.total_return
    assert res1.max_drawdown == res2.max_drawdown
    assert len(res1.aggregate_trades) == len(res2.aggregate_trades)


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
        holdout_end=datetime.date(2024, 1, 19),
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
        holdout_end=datetime.date(2024, 1, 19),
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
        holdout_end=datetime.date(2024, 1, 19),
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
        holdout_end=datetime.date(2025, 12, 31),
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

