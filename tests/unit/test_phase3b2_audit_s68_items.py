"""
Unit tests for Phase 3B-2b Audit §68 Remediation Items (Audit §68 at e265ff5).

Target invariants:
- H-116: the ISIN-transition refusal is computed over the dataset's full trading span, so
  `--in-sample-only` cannot weaken identity validation (universe counts match the full window).
- N-112 residual: all three MERGER rows carry a modelled consideration price, and an unpriced
  fractional merger fails closed with CorporateActionError instead of settling at book value.
- N-118: CRIT-EXEC-03/04 evidence is always the computed judged/violating fill sentence; a caller
  that supplies the flag without counts evaluates NOT RUN rather than asserting enforcement.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.order_types import OrderProduct, OrderSide, OrderType
from signal_core.execution.order_runner import ExecutionOrder
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.types import CorporateActionError
from signal_core.reporting.verdicts import VerdictStatus, evaluate_verdicts
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    build_production_security_master,
)
from scripts.run_phase3b2_walkforward import run_phase3b2_walkforward


def _buy(portfolio: Portfolio, isin: str, quantity: int, price: str, trade_date: datetime.date) -> None:
    criteria = load_go_no_go_criteria()
    order = ExecutionOrder(
        order_id=f"ORD-S68-{isin}-{quantity}",
        instrument_id=isin,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=quantity,
        signal_date=trade_date - datetime.timedelta(days=1),
        target_date=trade_date,
        product=OrderProduct.DELIVERY,
    )
    fill = ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=trade_date,
        latency_sessions=1,
        filled_quantity=quantity,
        unfilled_quantity=0,
        executed_price=Decimal(price),
        slippage=None,
        costs=ExecutionFillSimulator(criteria=criteria).cost_model.compute_costs(
            trade_date=trade_date,
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=quantity,
            price=Decimal(price),
        ),
        circuit_evidence_present=True,
        rejection_reason=None,
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)


def test_h116_in_sample_universe_uses_full_span_identity_validation(tmp_path: Path):
    """
    H-116: with the transition refusal anchored at min..max of dataset.trading_dates, the
    2022-2023 in-sample run admits 196 valid ISINs (179 continuous + 17 gap refusals) — the same
    identity set the full 2022-2024 window admits, not the 203 the eval_end-anchored check allowed.
    """
    res = run_phase3b2_walkforward(
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        in_sample_only=True,
        trial_id="TRIAL-TEST-H116-IN-SAMPLE",
        write_verdict_files=True,
    )
    executed = res.executed_sessions
    assert executed[-1] == datetime.date(2023, 12, 29)

    import json

    artifact = json.loads(
        (tmp_path / "verdicts" / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    # Same identity universe as 2022-2024: 196 valid ISINs (the eval_end-anchored refusal admitted
    # 203). Gap refusals are window-scoped (17), so 179 instruments are continuous in this window.
    assert artifact["total_valid_isins"] == 196
    assert artifact["continuous_instruments_passed"] == 179
    assert artifact["unexplained_gap_refusals"] == 17

    diag = res.coverage_diagnostics
    assert set(diag) == {"2022", "2023", "2024"}
    assert {s for s in diag["2022"]["band_covered_symbols"]} == {"HDFC", "INFY", "RELIANCE"}


def test_n112_all_merger_rows_carry_a_modelled_consideration_price():
    """N-112 residual: MINDTREE, HDFC and IDFC merger rows are all priced."""
    sec_master = build_production_security_master(include_cash_universe=True)
    expected = {
        ("INE018I01017", datetime.date(2022, 11, 23)): Decimal("4742.05"),
        ("INE001A01036", datetime.date(2023, 7, 13)): Decimal("1641.10"),
        ("INE043D01016", datetime.date(2024, 9, 27)): Decimal("74.19"),
    }
    for (isin, ex_date), price in expected.items():
        rows = [
            a for a in sec_master.get_corporate_actions(isin)
            if a.ex_date == ex_date and a.action_type == CorporateActionType.MERGER
        ]
        assert len(rows) == 1, f"Expected exactly one merger row for {isin} on {ex_date}"
        assert rows[0].delisting_price == price, (isin, ex_date, rows[0].delisting_price)


def test_n112_idfc_fractional_merger_settles_at_modelled_close():
    """N-112 residual: IDFC 31/20 on 31 shares leaves 0.05 fractional, settled at 74.19."""
    criteria = load_go_no_go_criteria()
    d_buy = datetime.date(2024, 9, 25)
    d_merger = datetime.date(2024, 9, 27)
    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=d_buy
    )
    _buy(portfolio, "INE043D01016", 31, "100.00", d_buy)

    merger = [
        a for a in build_production_security_master(include_cash_universe=True).get_corporate_actions(
            "INE043D01016"
        )
        if a.ex_date == d_merger and a.action_type == CorporateActionType.MERGER
    ][0]
    cash_entry = portfolio.apply_corporate_action(merger)
    assert cash_entry is not None
    # 31 × 31 / 20 = 48 whole shares, remainder 1/20 = 0.05 shares at ₹74.19 = ₹3.7095 -> ₹3.71
    assert cash_entry.amount == Decimal("3.71")
    assert portfolio.get_position("INE092T01019").quantity == 48


def test_n112_unpriced_fractional_merger_fails_closed():
    """N-112: a fractional merger without a consideration price raises, never books book value."""
    criteria = load_go_no_go_criteria()
    d_buy = datetime.date(2024, 9, 25)
    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=d_buy
    )
    _buy(portfolio, "INE043D01016", 31, "100.00", d_buy)

    unpriced = CorporateAction(
        isin="INE043D01016",
        ex_date=datetime.date(2024, 9, 27),
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("31"),
        ratio_denominator=Decimal("20"),
        new_isin="INE092T01019",
    )
    with pytest.raises(CorporateActionError, match="no consideration price|refusing book-value"):
        portfolio.apply_corporate_action(unpriced)

    # The position is untouched: the check happens before any quantity/basis mutation.
    assert portfolio.get_position("INE043D01016").quantity == 31


def test_n118_circuit_evidence_is_numeric_only():
    """N-118: no counts -> NOT RUN; counts -> the computed numeric sentence."""
    criteria = load_go_no_go_criteria()
    # H-123: a sourced, session-bearing window is required before counts decide anything.
    window = {
        "evaluation_start_date": "2024-01-16",
        "evaluation_end_date": "2024-03-31",
    }
    bare = evaluate_verdicts(
        results_bundle={
            **window,
            "prohibit_buy_at_upper_circuit": True,
            "prohibit_sell_at_lower_circuit": True,
        },
        criteria=criteria,
    )
    exec3 = next(e for e in bare.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in bare.evaluations if e.criterion_id == "CRIT-EXEC-04")
    for ev in (exec3, exec4):
        assert ev.status == VerdictStatus.NOT_RUN
        assert "Simulator strictly enforces" not in ev.evidence
        assert "not provided in results bundle" in ev.evidence

    numeric = evaluate_verdicts(
        results_bundle={
            **window,
            "prohibit_buy_at_upper_circuit": True,
            "prohibit_sell_at_lower_circuit": True,
            "upper_circuit_buy_judged_fills": 17,
            "upper_circuit_buy_violating_fills": 0,
            "upper_circuit_buy_missing_limit_fills": 0,
            "lower_circuit_sell_judged_fills": 15,
            "lower_circuit_sell_violating_fills": 0,
            "lower_circuit_sell_missing_limit_fills": 0,
        },
        criteria=criteria,
    )
    exec3 = next(e for e in numeric.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in numeric.evaluations if e.criterion_id == "CRIT-EXEC-04")
    assert exec3.status == VerdictStatus.PASS
    assert exec3.evidence.startswith("0 of 17 judged BUY fill(s)")
    assert exec4.status == VerdictStatus.PASS
    assert exec4.evidence.startswith("0 of 15 judged SELL fill(s)")
