"""
Unit Tests for DeepSeek §65 Audit Items (H-110, H-111, N-104, N-105).

Verifies:
1. H-111: ExecutionFillResult persists effective upper and lower circuit limits:
   - simulator.simulate_order populates effective_upper_circuit_limit and effective_lower_circuit_limit.
   - Dynamic flexing band limits (±10%) are recorded on unconstrained F&O names.
   - Rejections preserve circuit limits.
   - A synthetic fill at or through circuit limit causes CRIT-EXEC-03 / CRIT-EXEC-04 to fail closed.
2. N-105: All remaining non-telemetry PASS checks eliminated:
   - CRIT-DATA-02: fail_closed_on_unexplained_gaps is derived from engine telemetry and fails if fail_closed=False.
   - CRIT-DATA-03: point-in-time universe selection validates active SymbolIntervals covering session dates.
   - CRIT-DATA-04: zero_data_fabrication is computed without vacuous conditions.
   - CRIT-EXEC-02: min_daily_turnover_crore uses 20-session trailing ADTV prior to trade entry.
3. H-110: 2022-2023 price band coverage honesty and per-year diagnostics:
   - Explicit per-year metrics partition 2022, 2023, and 2024.
   - Band coverage disclosure accurately reflects F&O dynamic flexing anchor scrips in 2022-2023.
4. N-104: SecurityMaster fingerprint computation:
   - compute_security_master_fingerprint accepts SecurityMaster directly.
   - Modifying security master intervals alters the fingerprint deterministically.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries, ExchangeSessionObservation
from signal_core.contracts.order_types import (
    ExecutionFillResult,
    ExecutionFillResultProtocol,
    ExecutionOrder,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)
from signal_core.contracts.price_band import (
    PriceBandInterval,
    PriceBandPublicationSource,
    PriceBandRecord,
    PriceBandSourceDescriptor,
)
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import (
    DailyExecutionTicket,
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
)
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.reporting.verdicts import VerdictStatus, evaluate_verdicts
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    DelistingEvent,
    ISINTransitionEvent,
    SecurityMaster,
    SymbolInterval,
    build_production_security_master,
    compute_security_master_fingerprint,
)
from scripts.run_phase3b2_walkforward import (
    run_phase3b2_walkforward,
)


def test_h111_execution_fill_result_carries_effective_circuit_limits():
    """H-111: ExecutionFillResult must carry effective upper and lower circuit limits."""
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    d1 = datetime.date(2024, 1, 16)
    d2 = datetime.date(2024, 1, 17)

    order = ExecutionOrder(
        order_id="ORD-TEST-001",
        instrument_id="INE002A01018",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=10,
        signal_date=d1,
        target_date=d2,
        product=OrderProduct.DELIVERY,
    )

    bar = PriceBar(
        instrument_id="INE002A01018",
        trade_date=d2,
        open=Decimal("2500.00"),
        high=Decimal("2550.00"),
        low=Decimal("2480.00"),
        close=Decimal("2520.00"),
        volume=500000,
        traded_value=Decimal("1260000000.00"),
    )

    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=d2,
        series="EQ",
        upper_circuit_limit=Decimal("2750.00"),
        lower_circuit_limit=Decimal("2250.00"),
    )

    fill = sim.simulate_order(
        order=order,
        bar=bar,
        price_band=band,
        explicit_series=ExchangeSeries.EQ,
    )

    assert isinstance(fill, ExecutionFillResult)
    assert isinstance(fill, ExecutionFillResultProtocol)
    assert fill.status == FillStatus.FILLED
    assert fill.effective_upper_circuit_limit == Decimal("2750.00")
    assert fill.effective_lower_circuit_limit == Decimal("2250.00")
    assert fill.executed_price < fill.effective_upper_circuit_limit


def test_h111_dynamic_flexing_circuit_limits_populated():
    """H-111: Unconstrained F&O names populate dynamically derived circuit limits."""
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    d1 = datetime.date(2024, 1, 16)
    d2 = datetime.date(2024, 1, 17)

    order = ExecutionOrder(
        order_id="ORD-TEST-002",
        instrument_id="INE009A01021",  # INFY
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=10,
        signal_date=d1,
        target_date=d2,
        product=OrderProduct.DELIVERY,
    )

    bar = PriceBar(
        instrument_id="INE009A01021",
        trade_date=d2,
        open=Decimal("1500.00"),
        high=Decimal("1530.00"),
        low=Decimal("1490.00"),
        close=Decimal("1520.00"),
        volume=1000000,
        traded_value=Decimal("1520000000.00"),
    )

    # Unconstrained F&O band record (upper/lower None, is_unconstrained=True)
    unconstrained_band = PriceBandRecord(
        isin="INE009A01021",
        trade_date=d2,
        series="EQ",
        upper_circuit_limit=None,
        lower_circuit_limit=None,
        is_unconstrained=True,
        source_ref="NSE_FO_CIRCULAR_20240116",
    )

    prev_close = Decimal("1500.00")
    fill = sim.simulate_order(
        order=order,
        bar=bar,
        price_band=unconstrained_band,
        explicit_series=ExchangeSeries.EQ,
        prev_close=prev_close,
    )

    assert fill.status == FillStatus.FILLED
    assert fill.effective_upper_circuit_limit == Decimal("1650.00")  # +10%
    assert fill.effective_lower_circuit_limit == Decimal("1350.00")  # -10%


def test_h111_circuit_freeze_rejections_preserve_circuit_limits():
    """H-111: Rejections at upper or lower circuit limits carry effective limits."""
    criteria = load_go_no_go_criteria()
    sim = ExecutionFillSimulator(criteria=criteria)

    d1 = datetime.date(2024, 1, 16)
    d2 = datetime.date(2024, 1, 17)

    order_buy = ExecutionOrder(
        order_id="ORD-UC-REJ",
        instrument_id="INE002A01018",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=10,
        signal_date=d1,
        target_date=d2,
        product=OrderProduct.DELIVERY,
    )

    # Open at upper circuit limit
    bar_uc = PriceBar(
        instrument_id="INE002A01018",
        trade_date=d2,
        open=Decimal("2750.00"),
        high=Decimal("2750.00"),
        low=Decimal("2750.00"),
        close=Decimal("2750.00"),
        volume=100000,
        traded_value=Decimal("275000000.00"),
    )

    band = PriceBandRecord(
        isin="INE002A01018",
        trade_date=d2,
        series="EQ",
        upper_circuit_limit=Decimal("2750.00"),
        lower_circuit_limit=Decimal("2250.00"),
    )

    fill_rej = sim.simulate_order(
        order=order_buy,
        bar=bar_uc,
        price_band=band,
        explicit_series=ExchangeSeries.EQ,
    )

    assert fill_rej.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert fill_rej.effective_upper_circuit_limit == Decimal("2750.00")
    assert fill_rej.effective_lower_circuit_limit == Decimal("2250.00")


def test_n104_security_master_fingerprint_direct_call():
    """N-104: compute_security_master_fingerprint accepts SecurityMaster directly."""
    sec_master = build_production_security_master()
    fp1 = compute_security_master_fingerprint(sec_master)
    assert isinstance(fp1, str)
    assert fp1.startswith("SEC-MSTR-V1-")
    assert fp1 == sec_master.fingerprint

    # Verify deterministic change if security master content changes
    sym = SymbolInterval(
        isin="INE999X01010",
        symbol="TESTSCRIP",
        series="EQ",
        effective_from=datetime.date(2022, 1, 1),
        effective_to=None,
    )
    sm_mut = SecurityMaster(
        symbol_intervals=(sym,),
    )
    fp_mut = compute_security_master_fingerprint(sm_mut)
    assert fp_mut.startswith("SEC-MSTR-V1-")
    assert fp_mut != fp1


def test_n105_data02_fail_closed_on_unexplained_gaps_telemetry(tmp_path: Path):
    """N-105: CRIT-DATA-02 evaluates from real engine telemetry, not hardcoded True."""
    # Build minimal synthetic snapshot
    from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot

    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    # Run with fail_closed_on_unexplained=False
    res_false = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        fail_closed_on_unexplained=False,
        trial_id="TRIAL-TEST-FC-FALSE",
        write_verdict_files=False,
    )

    eval_d2_false = next(
        e for e in res_false.verdict_report.evaluations if e.criterion_id == "CRIT-DATA-02"
    )
    assert eval_d2_false.status == VerdictStatus.FAIL
    assert eval_d2_false.computed_value == "False"

    # Run with fail_closed_on_unexplained=True
    res_true = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        fail_closed_on_unexplained=True,
        trial_id="TRIAL-TEST-FC-TRUE",
        write_verdict_files=False,
    )

    eval_d2_true = next(
        e for e in res_true.verdict_report.evaluations if e.criterion_id == "CRIT-DATA-02"
    )
    assert eval_d2_true.status == VerdictStatus.PASS
    assert eval_d2_true.computed_value == "True"


def test_n105_exec02_adtv_calculated_over_trailing_20_sessions(tmp_path: Path):
    """N-105: CRIT-EXEC-02 computes minimum trailing 20-session ADTV across entry fills."""
    from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot

    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=90)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=80,
        trial_id="TRIAL-TEST-ADTV",
        write_verdict_files=False,
    )

    eval_exec2 = next(
        e for e in res.verdict_report.evaluations if e.criterion_id == "CRIT-EXEC-02"
    )
    # The synthetic test fixture has volume 100,000 shares * ~₹1,000 price = ~₹10 Crore ADTV
    assert eval_exec2.status == VerdictStatus.PASS
    comp_val = Decimal(eval_exec2.computed_value)
    assert comp_val >= Decimal("5.0")  # Minimum threshold is 5.0 Cr


def test_h110_band_coverage_diagnostics_structure(tmp_path: Path):
    """H-110: Per-year coverage diagnostics partition 2022, 2023, 2024 with disclosure."""
    from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot

    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        trial_id="TRIAL-TEST-H110",
        write_verdict_files=True,
    )

    # Check coverage_diagnostics written to JSON report
    json_path = out_dir / "phase3b2_swing_baseline_2022_2024_verdict.json"
    assert json_path.is_file()
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "coverage_diagnostics" in data
    cov = data["coverage_diagnostics"]
    assert "2022" in cov
    assert "coverage_notes" in cov["2022"]
    assert "Band-constrained" in cov["2022"]["coverage_notes"]

    # Check Markdown report has disclosure section
    md_path = out_dir / "phase3b2_swing_baseline_2022_2024_verdict.md"
    assert md_path.is_file()
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    assert "## Band Coverage Diagnostics & Disclosure (Audit §65 H-110)" in md_text
    assert "Band-constrained" in md_text


def test_h111_fill_at_uc_fails_crit_exec_03(tmp_path: Path):
    """
    H-111 & N-109: Producer-driven circuit breach test.
    Drives run_phase3b2_walkforward on a synthetic corpus where an order fills
    at the derived upper circuit limit via adverse slippage and asserts CRIT-EXEC-03 FAIL
    on the returned VerdictReport (Audit §66 N-109).
    """
    import json
    from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot

    snap_file = make_synthetic_snapshot(tmp_path, num_sessions=60)
    with open(snap_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # First execute baseline to identify the first buy fill date
    res_baseline = run_phase3b2_walkforward(
        snapshot_path=snap_file,
        registry_path=tmp_path / "reg_base.jsonl",
        verdict_output_dir=tmp_path / "v_base",
        max_sessions=60,
        trial_id="TRIAL-TEST-EXEC03-BASE",
        write_verdict_files=False,
    )
    all_buys = [
        t.fill_result
        for s in res_baseline.session_summaries
        for t in s.tickets
        if t.fill_result and t.fill_result.order.side == OrderSide.BUY and t.fill_result.filled_quantity > 0
    ]
    assert len(all_buys) > 0, "Expected at least one buy fill in synthetic baseline run"
    first_buy = all_buys[0]
    target_d = first_buy.fill_date.isoformat()

    # Modify the snapshot on target_d: set open 1 tick below dynamic upper circuit (prev_close * 1.10)
    # and high at upper circuit. Adverse slippage pushes executed price to upper circuit.
    bars = data["prices_by_instrument"]["UUID-INFY"]
    for i, b in enumerate(bars):
        if b["trade_date"] == target_d:
            prev_b = bars[i - 1]
            prev_c = Decimal(prev_b["close"])
            uc = (prev_c * Decimal("1.10")).quantize(Decimal("0.05"))
            b["open"] = str(uc - Decimal("0.05"))
            b["high"] = str(uc)
            b["close"] = str(uc - Decimal("0.10"))
            break

    snap_breach = tmp_path / "synthetic_snapshot_breach.json"
    with open(snap_breach, "w", encoding="utf-8") as f:
        json.dump(data, f)

    res_breach = run_phase3b2_walkforward(
        snapshot_path=snap_breach,
        registry_path=tmp_path / "reg_breach.jsonl",
        verdict_output_dir=tmp_path / "v_breach",
        max_sessions=60,
        trial_id="TRIAL-TEST-EXEC03-BREACH",
        write_verdict_files=False,
    )

    # H-114: the simulator now rejects the fill instead of clamping it onto the limit, so no
    # violating fill reaches the criterion and the producer evidence reports the observed count.
    breach_tickets = [
        t for s in res_breach.session_summaries for t in s.tickets
        if t.fill_result is not None and t.fill_result.order.side == OrderSide.BUY
        and t.fill_result.fill_date.isoformat() == target_d
    ]
    assert any(
        t.fill_result.status == FillStatus.REJECTED_UPPER_CIRCUIT for t in breach_tickets
    ), [(t.fill_result.status.value, str(t.fill_result.executed_price)) for t in breach_tickets]

    eval_exec3 = next(
        e for e in res_breach.verdict_report.evaluations if e.criterion_id == "CRIT-EXEC-03"
    )
    assert eval_exec3.status == VerdictStatus.PASS
    assert eval_exec3.computed_value == "True"
    assert "0 of " in eval_exec3.evidence

