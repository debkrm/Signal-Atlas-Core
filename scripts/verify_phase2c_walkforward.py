"""
Phase 2C Verification Probe: Strategy Contract & Next-Session Walk-Forward Engine.

Computes exact quantitative assertions for Phase 2C gates per AGENTS.md and CURRENT_STAGE_OF_WORK.md:
- Gate G2C-1: Bit-for-bit determinism across identical runs (fingerprint, returns, Sharpe).
- Gate G2C-2: Strict rejection of same-session (T close -> T fill) or backward-dated intents.
- Gate G2C-3: Series eligibility enforcement (APPROVED_EQ_ONLY_POLICY; ineligible scrips fail closed).
- Gate G2C-4: Circuit evidence audit (missing circuit depth flagged CIRCUIT_UNVERIFIED, blocking promotion).
- Gate G2C-5: Single authoritative execution simulator and portfolio ledger integration.
"""

import datetime
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import tempfile

# Ensure src/ is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    SeriesEligibilityPolicy,
)
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.research.containment import PartitionRole, WalkForwardFold
from signal_core.research.trials import TrialRegistry
from signal_core.research.walkforward import (
    WalkForwardEngine,
    WalkForwardLookaheadError,
    WalkForwardResult,
)
from signal_core.storage.calendar import (
    SessionType,
    TradingCalendar,
    TradingSessionRecord,
    compute_calendar_fingerprint,
)
from signal_core.storage.gold import GoldEngine
from signal_core.storage.security_master import SecurityMaster, SymbolInterval
from signal_core.storage.silver import SilverRecord, SilverStorage
from signal_core.strategy.base import (
    LookaheadIntentError,
    OrderIntent,
    Strategy,
    TechnicalCrossStrategy,
)


def run_phase_2c_verification() -> bool:
    print("=" * 80)
    print("SIGNAL ATLAS — PHASE 2C STRATEGY CONTRACT & WALK-FORWARD ENGINE VERIFICATION")
    print(f"Executed at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    all_passed = True
    temp_dir = Path(tempfile.mkdtemp(prefix="phase2c_probe_"))

    try:
        silver_dir = temp_dir / "silver"

        # 1. Build authoritative 10-session January 2024 calendar
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
        cal = TradingCalendar(
            calendar_id="WF-CAL-NSE",
            market="NSE_CASH",
            session_records=records,
            binding_start_date=datetime.date(2018, 4, 1),
            fingerprint=fpr,
            provenance={"source": "PROBE_2C"},
            annual_session_counts={"2024": 10},
        )

        # 2. Build SecurityMaster
        infy_isin = "INE009A01021"
        rel_isin = "INE002A01018"
        be_isin = "INE999B01019"

        sec_master = SecurityMaster(
            symbol_intervals=[
                SymbolInterval(
                    isin=infy_isin,
                    symbol="INFY",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
                SymbolInterval(
                    isin=rel_isin,
                    symbol="RELIANCE",
                    series="EQ",
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
                SymbolInterval(
                    isin=be_isin,
                    symbol="TESTBE",
                    series="BE",  # Ineligible Trade-to-Trade
                    effective_from=datetime.date(2024, 1, 1),
                    effective_to=datetime.date(2024, 12, 31),
                ),
            ]
        )

        # 3. Build Silver storage partitions
        silver = SilverStorage(silver_dir, calendar=cal)
        base_infy = Decimal("1500.00")
        base_rel = Decimal("2500.00")
        base_be = Decimal("500.00")

        for i, session_date in enumerate(cal.sessions):
            p_infy = base_infy + Decimal(str(i * 10))
            p_rel = base_rel - Decimal(str(i * 15))
            p_be = base_be + Decimal(str(i * 5))

            daily_records = [
                SilverRecord(
                    isin=infy_isin,
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
                    isin=rel_isin,
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
                    isin=be_isin,
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
            silver.write_daily_partition(session_date, daily_records)

        gold = GoldEngine(silver, cal, sec_master)

        fold = WalkForwardFold(
            fold_index=0,
            train_start=datetime.date(2024, 1, 8),
            train_end=datetime.date(2024, 1, 11),
            test_start=datetime.date(2024, 1, 15),
            test_end=datetime.date(2024, 1, 19),
            embargo_sessions=1,
            partition_role=PartitionRole.VALIDATION,
        )

        engine = WalkForwardEngine(
            calendar=cal,
            gold_engine=gold,
            eligibility_policy=APPROVED_EQ_ONLY_POLICY,
        )

        # ----------------------------------------------------------------------
        # GATE G2C-1: BIT-FOR-BIT DETERMINISM ACROSS RERUNS
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-1: Bit-for-Bit Determinism across Reruns ---")
        strat = TechnicalCrossStrategy(
            strategy_id="WF-DET-TEST",
            fast_indicator="close",
            slow_indicator="open",
            allocation_weight=Decimal("0.20"),
        )
        init_cap = Decimal("1000000.00")

        res_a = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=init_cap)
        res_b = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=init_cap)

        fpr_match = (res_a.fingerprint == res_b.fingerprint)
        equity_match = (res_a.final_equity == res_b.final_equity)
        sharpe_match = (res_a.annualized_sharpe == res_b.annualized_sharpe)
        trades_match = (len(res_a.aggregate_trades) == len(res_b.aggregate_trades))
        g2c_1_passed = fpr_match and equity_match and sharpe_match and trades_match

        all_passed = all_passed and g2c_1_passed
        print(f"[{'PASS' if g2c_1_passed else 'FAIL'}] Gate G2C-1: Bit-for-bit reproducibility verified")
        print(f"       Fingerprint: {res_a.fingerprint} == {res_b.fingerprint}")
        print(f"       Final Equity: ₹{res_a.final_equity} == ₹{res_b.final_equity} | Sharpe: {res_a.annualized_sharpe}")

        # ----------------------------------------------------------------------
        # GATE G2C-2: SAME-SESSION LOOKAHEAD REJECTION (T close -> T fill)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-2: Same-Session Lookahead Intent Rejection ---")
        t_sample = datetime.date(2024, 1, 15)
        intent_creation_caught = False
        engine_dispatch_caught = False

        # 1. OrderIntent creation with target_date <= signal_date
        try:
            OrderIntent(
                instrument_id=infy_isin,
                signal_date=t_sample,
                target_date=t_sample,  # Same-session execution attempt
                side=OrderSide.BUY,
                quantity=10,
            )
        except LookaheadIntentError:
            intent_creation_caught = True

        # 2. Engine level lookahead trap
        class MockRogueIntent:
            instrument_id = infy_isin
            signal_date = t_sample
            target_date = t_sample
            side = OrderSide.BUY

        class RogueLookaheadStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "ROGUE-LOOKAHEAD"

            def generate_signals(self, as_of, next_session, universe, features):
                return (MockRogueIntent(),)  # type: ignore

        try:
            engine.run_walk_forward(strategy=RogueLookaheadStrategy(), folds=[fold])
        except WalkForwardLookaheadError:
            engine_dispatch_caught = True

        g2c_2_passed = intent_creation_caught and engine_dispatch_caught
        all_passed = all_passed and g2c_2_passed
        print(f"[{'PASS' if g2c_2_passed else 'FAIL'}] Gate G2C-2: Same-session lookahead (T close -> T fill) fail-closed")
        print(f"       Intent level blocked: {intent_creation_caught} | Engine level blocked: {engine_dispatch_caught}")

        # ----------------------------------------------------------------------
        # GATE G2C-3: SERIES ELIGIBILITY ENFORCEMENT (APPROVED_EQ_ONLY_POLICY)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-3: Series Eligibility Enforcement (APPROVED_EQ_ONLY_POLICY) ---")
        class TradeToTradeAttemptStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "BE-ATTEMPT-STRAT"

            def generate_signals(self, as_of, next_session, universe, features):
                return (
                    OrderIntent(
                        instrument_id=be_isin,  # BE scrip
                        signal_date=as_of,
                        target_date=next_session,
                        side=OrderSide.BUY,
                        quantity=25,
                    ),
                )

        res_be = engine.run_walk_forward(
            strategy=TradeToTradeAttemptStrategy(),
            folds=[fold],
            isins=[infy_isin, be_isin],
        )

        be_rejected_orders = [
            t for t in res_be.aggregate_trades
            if t.order.instrument_id == be_isin and t.status == FillStatus.REJECTED_INELIGIBLE_SERIES
        ]
        be_filled_orders = [
            t for t in res_be.aggregate_trades
            if t.order.instrument_id == be_isin and t.status == FillStatus.FILLED
        ]

        g2c_3_passed = (len(be_rejected_orders) > 0) and (len(be_filled_orders) == 0)
        all_passed = all_passed and g2c_3_passed
        print(f"[{'PASS' if g2c_3_passed else 'FAIL'}] Gate G2C-3: Series eligibility enforced fail-closed")
        print(f"       BE scrip fills: {len(be_filled_orders)} | BE scrip rejected as ineligible: {len(be_rejected_orders)}")

        # ----------------------------------------------------------------------
        # GATE G2C-4: CIRCUIT EVIDENCE AUDIT & PROMOTION GATING
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-4: Circuit Evidence Auditing & Promotion Gating ---")
        class BuyInfyStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "BUY-INFY-STRAT"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 15):
                    return (
                        OrderIntent(
                            instrument_id=infy_isin,
                            signal_date=as_of,
                            target_date=next_session,
                            side=OrderSide.BUY,
                            quantity=50,
                        ),
                    )
                return ()

        res_circuit = engine.run_walk_forward(strategy=BuyInfyStrategy(), folds=[fold])
        circuit_flagged = (res_circuit.circuit_evidence_complete is False)
        status_unverified = (res_circuit.verification_status == "CIRCUIT_UNVERIFIED")

        g2c_4_passed = circuit_flagged and status_unverified
        all_passed = all_passed and g2c_4_passed
        print(f"[{'PASS' if g2c_4_passed else 'FAIL'}] Gate G2C-4: Missing circuit depth audited and promotion blocked")
        print(f"       Circuit evidence complete: {res_circuit.circuit_evidence_complete} | Status: {res_circuit.verification_status}")

        # ----------------------------------------------------------------------
        # GATE G2C-5: SINGLE AUTHORITATIVE ENGINE INTEGRATION (LEDGER & COSTS)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-5: Single Authoritative Engine & Portfolio Ledger Path ---")
        filled_trades = [t for t in res_circuit.aggregate_trades if t.status == FillStatus.FILLED]
        first_fill = filled_trades[0] if filled_trades else None

        has_costs = first_fill is not None and first_fill.costs is not None
        stt_present = has_costs and first_fill.costs.stt > Decimal("0")
        total_charges_present = has_costs and first_fill.costs.total_charges > Decimal("0")

        fold_res_0 = res_circuit.fold_results[0]
        snap_count_ok = len(fold_res_0.portfolio_snapshots) == 5
        second_snap = fold_res_0.portfolio_snapshots[1]
        cash_deducted = second_snap.cash_balance < init_cap
        position_opened = len(second_snap.positions) == 1 and second_snap.positions[0].instrument_id == infy_isin

        # Test concentration risk limit enforcement: order exceeding 10% weight fails closed
        concentration_caught = False
        class HeavyAllocationStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "HEAVY-STRAT"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 15):
                    return (
                        OrderIntent(
                            instrument_id=infy_isin,
                            signal_date=as_of,
                            target_date=next_session,
                            side=OrderSide.BUY,
                            quantity=200,  # ~30% of portfolio (> 10% max_single_position_weight)
                        ),
                    )
                return ()

        try:
            engine.run_walk_forward(strategy=HeavyAllocationStrategy(), folds=[fold])
        except Exception:
            concentration_caught = True

        g2c_5_passed = (
            has_costs and stt_present and total_charges_present
            and snap_count_ok and cash_deducted and position_opened
            and concentration_caught
        )
        all_passed = all_passed and g2c_5_passed
        print(f"[{'PASS' if g2c_5_passed else 'FAIL'}] Gate G2C-5: Single authoritative engine & ledger integration verified")
        print(f"       Statutory costs applied: {has_costs} (STT: ₹{first_fill.costs.stt if has_costs else 0})")
        print(f"       Cash deducted on fill: {cash_deducted} | Position tracked: {position_opened} | Risk limit enforced: {concentration_caught}")

        # ----------------------------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------------------------
        print("\n" + "=" * 80)
        total_gates = 5
        passed_gates = sum([g2c_1_passed, g2c_2_passed, g2c_3_passed, g2c_4_passed, g2c_5_passed])
        pct = (passed_gates / total_gates) * 100.0

        if all_passed:
            print(f"OVERALL VERDICT: ALL MEASURED GATES PASSED ({passed_gates}/{total_gates}, {pct:.1f}%)")
        else:
            print(f"OVERALL VERDICT: ONE OR MORE GATES FAILED ({passed_gates}/{total_gates}, {pct:.1f}%)")
        print("=" * 80)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return all_passed


if __name__ == "__main__":
    success = run_phase_2c_verification()
    sys.exit(0 if success else 1)

