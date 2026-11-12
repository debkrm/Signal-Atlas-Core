"""
Phase 2C Verification Probe: Strategy Contract & Next-Session Walk-Forward Engine.

Computes exact quantitative assertions for Phase 2C gates per AGENTS.md, CURRENT_STAGE_OF_WORK.md,
and Audit §25 / §26 (Wave 2 Closure):
- Gate G2C-1: Bit-for-bit determinism across identical runs with live trades (G-8, G-4).
- Gate G2C-2: Strict rejection of same-session (T close -> T fill) or backward-dated intents (G2C-2).
- Gate G2C-3: Series eligibility enforcement (APPROVED_EQ_ONLY_POLICY; ineligible scrips fail closed).
- Gate G2C-4: Circuit evidence audit & upper-circuit freeze refusal (G-6, Rule 5.3).
- Gate G2C-5: Single authoritative engine, latency realism & risk limit rejection (G-3, G-5, G-9).
"""

import datetime
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import tempfile

# Ensure stdout handles UTF-8 on Windows consoles without error (H-22 pattern)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure src/ is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import (
    APPROVED_EQ_ONLY_POLICY,
    ExchangeSeries,
    SeriesEligibilityPolicy,
)
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.research.containment import PartitionRole, WalkForwardFold
from signal_core.research.trials import TrialRegistry
from signal_core.research.walkforward import (
    WalkForwardEngine,
    WalkForwardEngineError,
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

        # 2. Build SecurityMaster with symbol intervals and circuit bands
        infy_isin = "INE009A01021"
        rel_isin = "INE002A01018"
        be_isin = "INE999B01019"
        base_infy = Decimal("1500.00")
        base_rel = Decimal("2500.00")
        base_be = Decimal("500.00")

        # Price bands:
        # - RELIANCE on 2024-01-16: upper circuit at 2400.00 (below open 2410.00) to test freeze refusal (Rule 5.3)
        # - INFY on all test sessions: exact 10.0% circuit limits to test verified execution
        price_bands = [
            PriceBandRecord(
                isin=rel_isin,
                trade_date=datetime.date(2024, 1, 16),
                series="EQ",
                upper_circuit_limit=Decimal("2400.00"),
                lower_circuit_limit=Decimal("2000.00"),
            ),
        ]
        for i, d in enumerate(dates[5:]):  # Jan 15-19
            p_curr = base_infy + Decimal(str((i + 5) * 10))
            price_bands.append(
                PriceBandRecord(
                    isin=infy_isin,
                    trade_date=d,
                    series="EQ",
                    upper_circuit_limit=p_curr * Decimal("1.10"),
                    lower_circuit_limit=p_curr * Decimal("0.90"),
                    band_percentage=Decimal("10.0"),
                )
            )

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
            ],
            price_bands=price_bands,
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
            execution_latency_sessions=1,
        )

        # ----------------------------------------------------------------------
        # GATE G2C-1: BIT-FOR-BIT DETERMINISM ACROSS RERUNS WITH LIVE TRADES
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-1: Bit-for-Bit Determinism across Reruns with Live Trades (G-8, G-4) ---")
        # Audit §25 G-8: Use strategy parameters that generate genuine trades on test series (close > open > low)
        strat = TechnicalCrossStrategy(
            strategy_id="WF-DET-TEST",
            fast_indicator="open",
            slow_indicator="low",
            allocation_weight=Decimal("0.08"),  # Complies with 10% risk cap
        )
        init_cap = Decimal("1000000.00")

        res_a = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=init_cap)
        res_b = engine.run_walk_forward(strategy=strat, folds=[fold], initial_capital=init_cap)

        trades_executed = len(res_a.aggregate_trades) > 0
        filled_trades = [t for t in res_a.aggregate_trades if t.status == FillStatus.FILLED]
        has_fills = len(filled_trades) > 0

        fpr_match = (res_a.fingerprint == res_b.fingerprint)
        equity_match = (res_a.final_equity == res_b.final_equity)
        sharpe_match = (res_a.annualized_sharpe == res_b.annualized_sharpe)
        returns_match = (res_a.aggregate_daily_returns == res_b.aggregate_daily_returns)
        prices_match = (
            [t.executed_price for t in res_a.aggregate_trades]
            == [t.executed_price for t in res_b.aggregate_trades]
        )

        # Audit §25 G-4: Bound directly to authoritative Gold dataset fingerprint
        dataset_fpr_valid = (
            res_a.dataset_content_fingerprint.startswith("DATA-CTNT-V2-")
            and res_a.dataset_content_fingerprint != "DATA-CTNT-V2-UNKNOWN"
        )
        trial_rec = res_a.to_trial_record(
            trial_id="TRIAL-G4-TEST",
            hypothesis="Determinism test",
            rationale="Wave 2 verification",
            fold_spec_fingerprint="FOLD-TEST",
        )
        trial_fpr_bound = (trial_rec.dataset_fingerprint == res_a.dataset_content_fingerprint)

        # Unknown dataset fingerprint rejection check
        unknown_rejected = False
        try:
            engine.run_walk_forward(
                strategy=strat,
                folds=[fold],
                dataset_content_fingerprint="DATA-CTNT-V2-UNKNOWN",
            )
        except WalkForwardEngineError:
            unknown_rejected = True

        g2c_1_passed = (
            trades_executed
            and has_fills
            and fpr_match
            and equity_match
            and sharpe_match
            and returns_match
            and prices_match
            and dataset_fpr_valid
            and trial_fpr_bound
            and unknown_rejected
        )

        all_passed = all_passed and g2c_1_passed
        print(f"[{'PASS' if g2c_1_passed else 'FAIL'}] Gate G2C-1: Bit-for-bit determinism & dataset binding verified")
        print(f"       Live trades executed: {len(res_a.aggregate_trades)} (fills: {len(filled_trades)}) | Non-empty: {has_fills}")
        print(f"       Fingerprint: {res_a.fingerprint} == {res_b.fingerprint}")
        print(f"       Final Equity: Rs. {res_a.final_equity} == Rs. {res_b.final_equity} | Sharpe: {res_a.annualized_sharpe}")
        print(f"       Dataset Fingerprint Bound: {res_a.dataset_content_fingerprint} (trial bound: {trial_fpr_bound})")
        print(f"       'UNKNOWN' Fingerprint Rejected Fail-Closed: {unknown_rejected}")

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
        # GATE G2C-4: CIRCUIT EVIDENCE AUDIT & UPPER CIRCUIT REFUSAL (G-6, Rule 5.3)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-4: Circuit Evidence Auditing & Locked Circuit Refusal (G-6, Rule 5.3) ---")

        # 1. Zero-trade run must be NOT RUN, never VERIFIED (Audit §25 G-6)
        class EmptyStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "EMPTY-STRAT"

            def generate_signals(self, as_of, next_session, universe, features):
                return ()

        res_zero = engine.run_walk_forward(strategy=EmptyStrategy(), folds=[fold])
        zero_trade_not_run = (len(res_zero.aggregate_trades) == 0 and res_zero.verification_status == "NOT RUN")

        # 2. Refusal at Upper Circuit Freeze (falsifiable circuit limit)
        # RELIANCE on Jan 16 has upper_circuit_limit = 2400.00 while open = 2410.00
        class BuyRelianceAtCircuitStrategy(Strategy):
            @property
            def strategy_id(self) -> str:
                return "BUY-RELIANCE-CIRCUIT"

            def generate_signals(self, as_of, next_session, universe, features):
                if as_of == datetime.date(2024, 1, 15):
                    return (
                        OrderIntent(
                            instrument_id=rel_isin,
                            signal_date=as_of,
                            target_date=next_session,  # Targets Jan 16
                            side=OrderSide.BUY,
                            quantity=20,
                        ),
                    )
                return ()

        res_freeze = engine.run_walk_forward(
            strategy=BuyRelianceAtCircuitStrategy(),
            folds=[fold],
            isins=[rel_isin, infy_isin],
        )
        circuit_freeze_refused = any(
            t.status == FillStatus.REJECTED_UPPER_CIRCUIT for t in res_freeze.aggregate_trades
        )

        # 3. Verified trade run with complete circuit bands
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

        res_verified = engine.run_walk_forward(strategy=BuyInfyStrategy(), folds=[fold])
        verified_ok = (
            res_verified.circuit_evidence_complete is True
            and res_verified.verification_status == "VERIFIED"
            and len([t for t in res_verified.aggregate_trades if t.status == FillStatus.FILLED]) > 0
        )

        g2c_4_passed = zero_trade_not_run and circuit_freeze_refused and verified_ok
        all_passed = all_passed and g2c_4_passed
        print(f"[{'PASS' if g2c_4_passed else 'FAIL'}] Gate G2C-4: Falsifiable circuit evidence & freeze gates verified")
        print(f"       Zero-trade status is 'NOT RUN': {zero_trade_not_run} (status: {res_zero.verification_status})")
        print(f"       BUY at Upper Circuit refused fail-closed: {circuit_freeze_refused} (REJECTED_UPPER_CIRCUIT)")
        print(f"       Trade with circuit evidence verified: {verified_ok} (status: {res_verified.verification_status})")

        # ----------------------------------------------------------------------
        # GATE G2C-5: SINGLE AUTHORITATIVE ENGINE, LATENCY & RISK LIMIT REJECTION
        # ----------------------------------------------------------------------
        print("\n--- Gate G2C-5: Single Engine, Latency Realism & Risk Limit Rejection (G-3, G-5, G-9) ---")
        filled_trades = [t for t in res_verified.aggregate_trades if t.status == FillStatus.FILLED]
        first_fill = filled_trades[0] if filled_trades else None

        has_costs = first_fill is not None and first_fill.costs is not None
        stt_present = has_costs and first_fill.costs.stt > Decimal("0")
        total_charges_present = has_costs and first_fill.costs.total_charges > Decimal("0")

        fold_res_0 = res_verified.fold_results[0]
        snap_count_ok = len(fold_res_0.portfolio_snapshots) == 5
        second_snap = fold_res_0.portfolio_snapshots[1]
        cash_deducted = second_snap.cash_balance < init_cap
        position_opened = len(second_snap.positions) == 1 and second_snap.positions[0].instrument_id == infy_isin

        # 1. Risk limit rejection: Oversized intent (> 10% weight) does NOT abort the run (Audit §25 G-3, G-9)
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

        # Execution completes without raising an unhandled exception!
        res_heavy = engine.run_walk_forward(strategy=HeavyAllocationStrategy(), folds=[fold])
        risk_limit_rejected = any(
            t.status == FillStatus.REJECTED_RISK_LIMIT for t in res_heavy.aggregate_trades
        )
        zero_heavy_fills = len([t for t in res_heavy.aggregate_trades if t.status == FillStatus.FILLED]) == 0
        heavy_equity_preserved = (res_heavy.final_equity == init_cap)

        # 2. Execution latency realism (Audit §25 G-5)
        # Latency 1 -> fills Jan 16 (T+1); Latency 2 -> fills Jan 17 (T+2)
        engine_lat2 = WalkForwardEngine(
            calendar=cal,
            gold_engine=gold,
            eligibility_policy=APPROVED_EQ_ONLY_POLICY,
            execution_latency_sessions=2,
        )
        res_lat2 = engine_lat2.run_walk_forward(strategy=BuyInfyStrategy(), folds=[fold])
        fill_lat1 = res_verified.aggregate_trades[0]
        fill_lat2 = res_lat2.aggregate_trades[0]

        latency_differentiated = (
            fill_lat1.fill_date == datetime.date(2024, 1, 16)
            and fill_lat1.latency_sessions == 1
            and fill_lat2.fill_date == datetime.date(2024, 1, 17)
            and fill_lat2.latency_sessions == 2
        )

        g2c_5_passed = (
            has_costs
            and stt_present
            and total_charges_present
            and snap_count_ok
            and cash_deducted
            and position_opened
            and risk_limit_rejected
            and zero_heavy_fills
            and heavy_equity_preserved
            and latency_differentiated
        )
        all_passed = all_passed and g2c_5_passed
        print(f"[{'PASS' if g2c_5_passed else 'FAIL'}] Gate G2C-5: Authoritative engine, latency realism & risk rejections")
        print(f"       Statutory costs applied: {has_costs} (STT: Rs. {first_fill.costs.stt if has_costs else 0})")
        print(f"       Cash deducted on fill: {cash_deducted} | Position tracked: {position_opened}")
        print(f"       Risk limit rejection recorded (G-3, G-9): {risk_limit_rejected} (REJECTED_RISK_LIMIT, 0 fills, equity preserved)")
        print(f"       Latency realism verified (G-5): {latency_differentiated} (L=1 -> {fill_lat1.fill_date}, L=2 -> {fill_lat2.fill_date})")

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
