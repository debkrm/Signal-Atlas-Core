"""
Unit tests for Phase 3B-2b Audit §66 Remediation Items (Commit 8c4e099 / §66).
Target Invariants:
- H-112: Interpolate all disclosure prose counts directly from computed coverage diagnostics.
- N-108: Eliminate single-fold degeneracy on CRIT-OVERFIT-03 (NOT RUN when N_val < 2).
- H-113: Stock merger fractional cash-in-lieu settlement (e.g. 27 HDFC -> 45 HDFCBANK + cash).
- N-110: Compute band coverage per year as the union across all sessions in that year.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.order_types import OrderSide, OrderType, OrderProduct
from signal_core.execution.order_runner import ExecutionOrder
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.position import Position
from signal_core.portfolio.types import CashEntryType
from signal_core.reporting.verdicts import VerdictStatus
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    build_production_security_master,
)
from scripts.run_phase3b2_walkforward import run_phase3b2_walkforward
from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot


def test_h112_disclosure_counts_interpolated_from_diagnostics(tmp_path: Path):
    """
    H-112: All counts in the Markdown disclosure paragraph and coverage_notes
    are interpolated from computed coverage_diagnostics (no hardcoded literals).
    """
    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        trial_id="TRIAL-TEST-H112",
        write_verdict_files=True,
    )

    # 1. Check JSON report
    json_path = out_dir / "phase3b2_swing_baseline_2022_2024_verdict.json"
    assert json_path.is_file()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cov = data["coverage_diagnostics"]
    assert "2022" in cov
    assert "2023" in cov
    assert "2024" in cov

    # 2. Check coverage_notes in JSON
    for yr_str in ("2022", "2023", "2024"):
        diag = cov[yr_str]
        fills = diag["tickets_filled"]
        note = diag["coverage_notes"]
        assert f"({fills} fills executed)" in note, f"Expected '({fills} fills executed)' in {note}"

    # 3. Check Markdown disclosure paragraph
    md_path = out_dir / "phase3b2_swing_baseline_2022_2024_verdict.md"
    assert md_path.is_file()
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    fills_22_23 = cov["2022"]["tickets_filled"] + cov["2023"]["tickets_filled"]
    fills_24 = cov["2024"]["tickets_filled"]
    band_isins_24 = cov["2024"]["band_covered_isins"]

    assert f"({fills_22_23} fills executed)" in md_text
    assert f"({fills_24} fills executed)" in md_text
    assert f"Cash-universe coverage ({band_isins_24} scrips)" in md_text

    # Verify no un-interpolated hardcoded string remains
    assert "(22 fills executed)" not in md_text
    assert "(86 fills executed)" not in md_text
    assert "Full cash-universe coverage (185 scrips)" not in md_text


def test_n108_single_fold_degeneracy_evaluates_not_run(tmp_path: Path):
    """
    N-108: When fewer than 2 independent validation folds exist (N_val = 1),
    CRIT-OVERFIT-03 evaluates to NOT RUN with N_val = 1 disclosed.
    """
    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        trial_id="TRIAL-TEST-N108",
        write_verdict_files=True,
    )

    eval_of3 = next(
        e for e in res.verdict_report.evaluations if e.criterion_id == "CRIT-OVERFIT-03"
    )
    assert eval_of3.status == VerdictStatus.NOT_RUN
    assert eval_of3.computed_value is None
    assert "N_val = 1" in eval_of3.evidence
    assert "minimum 2 independent" in eval_of3.evidence

    # Check Markdown report discloses N_val = 1
    md_path = out_dir / "phase3b2_swing_baseline_2022_2024_verdict.md"
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    assert "Out-of-Sample Stability Disclosure (Finding N-108)" in md_text
    assert "N_val = 1" in md_text


def test_h113_stock_merger_fractional_cash_in_lieu():
    """
    H-113: Stock merger with non-integral ratio restates whole shares to new_isin,
    settles fractional shares as cash-in-lieu into CashLedger, and preserves total
    portfolio equity to the exact paisa (e.g. 27 HDFC @ 42:25 = 45 HDFCBANK + 0.36 cash).
    """
    criteria = load_go_no_go_criteria()
    d_buy = datetime.date(2023, 7, 10)
    d_merger = datetime.date(2023, 7, 13)

    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"),
        criteria=criteria,
        initial_date=d_buy,
    )

    # Buy 27 shares of HDFC (INE001A01036) at ₹2,650.00
    order = ExecutionOrder(
        order_id="ORD-HDFC-BUY",
        instrument_id="INE001A01036",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=27,
        signal_date=datetime.date(2023, 7, 7),
        target_date=d_buy,
        product=OrderProduct.DELIVERY,
    )
    fill = ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=d_buy,
        latency_sessions=1,
        filled_quantity=27,
        unfilled_quantity=0,
        executed_price=Decimal("2650.00"),
        slippage=None,
        costs=ExecutionFillSimulator(criteria=criteria).cost_model.compute_costs(
            trade_date=datetime.date(2023, 7, 10),
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=27,
            price=Decimal("2650.00"),
        ),
        circuit_evidence_present=True,
        rejection_reason=None,
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)
    pos = portfolio.get_position("INE001A01036")

    equity_before = portfolio.current_total_equity()
    assert pos.quantity == 27
    total_cost_basis_before = pos.total_cost_basis

    # Apply HDFC -> HDFCBANK merger (42:25 ratio)
    merger_action = CorporateAction(
        isin="INE001A01036",
        ex_date=d_merger,
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("42"),
        ratio_denominator=Decimal("25"),
        new_isin="INE040A01034",
        description="HDFC Ltd Merger into HDFC Bank (42 HDFCBANK per 25 HDFC)",
        # Finding N-112: a fractional merger without a consideration price now fails closed.
        delisting_price=Decimal("1641.10"),
    )

    cash_entry = portfolio.apply_corporate_action(merger_action)
    assert cash_entry is not None
    assert cash_entry.entry_type == CashEntryType.MERGER_CASH_IN_LIEU
    assert "INE001A01036" in cash_entry.description
    assert "INE040A01034" in cash_entry.description

    # Old position removed from mapping
    assert portfolio.get_position("INE001A01036") is None

    # New position active with 45 whole shares ((27 * 42) // 25 = 45)
    new_pos = portfolio.get_position("INE040A01034")
    assert new_pos is not None
    assert new_pos.quantity == 45
    assert new_pos.instrument_id == "INE040A01034"

    # Fractional remainder 0.36 shares settled at the consideration price, not book value.
    # (27 * 42) % 25 = 9 / 25 = 0.36 shares; 0.36 × 1641.10 = 590.796 -> ₹590.80
    assert cash_entry.amount == Decimal("590.80")

    # Finding N-112: the fractional slice is a disposal, so equity moves by
    # (consideration − removed book basis), not by zero (the old book-value tautology).
    basis_removed = total_cost_basis_before - new_pos.total_cost_basis
    equity_after = portfolio.current_total_equity()
    assert equity_after == equity_before - basis_removed + cash_entry.amount
    assert equity_after != equity_before


def test_h113_fail_closed_false_does_not_crash_on_hdfc_merger(tmp_path: Path):
    """
    H-113: Running with fail_closed_on_unexplained=False over a period including
    the HDFC merger (2023-07-13) exercises the held-position merger without crashing.
    """
    criteria = load_go_no_go_criteria()
    portfolio = Portfolio(
        initial_capital=Decimal("100000.00"),
        criteria=criteria,
        initial_date=datetime.date(2023, 7, 10),
    )

    order = ExecutionOrder(
        order_id="ORD-HDFC-HELD",
        instrument_id="INE001A01036",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=27,
        signal_date=datetime.date(2023, 7, 7),
        target_date=datetime.date(2023, 7, 10),
        product=OrderProduct.DELIVERY,
    )
    fill = ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=datetime.date(2023, 7, 10),
        latency_sessions=1,
        filled_quantity=27,
        unfilled_quantity=0,
        executed_price=Decimal("2650.00"),
        slippage=None,
        costs=ExecutionFillSimulator(criteria=criteria).cost_model.compute_costs(
            trade_date=datetime.date(2023, 7, 10),
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=27,
            price=Decimal("2650.00"),
        ),
        circuit_evidence_present=True,
        rejection_reason=None,
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)

    sec_master = build_production_security_master(include_cash_universe=True)
    actions = [
        a for a in sec_master.get_corporate_actions("INE001A01036")
        if a.ex_date == datetime.date(2023, 7, 13)
    ]
    assert any(a.action_type == CorporateActionType.MERGER for a in actions)

    # Must execute cleanly without raising CorporateActionError
    entries = portfolio.apply_corporate_actions_for_session(
        session_date=datetime.date(2023, 7, 13),
        corporate_actions=actions,
    )
    assert len(entries) == 1
    assert entries[0].entry_type == CashEntryType.MERGER_CASH_IN_LIEU
    assert portfolio.get_position("INE040A01034").quantity == 45


def test_n110_full_year_band_coverage_union(tmp_path: Path):
    """
    N-110: band_covered_isins is computed as the union of ISINs with an active
    price band across ALL sessions in that year, not just yr_sessions[0].
    """
    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    reg_p = tmp_path / "trial_reg.jsonl"
    out_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=reg_p,
        verdict_output_dir=out_dir,
        max_sessions=40,
        trial_id="TRIAL-TEST-N110",
        write_verdict_files=True,
    )

    cov = res.coverage_diagnostics or {}
    assert "2022" in cov
    assert cov["2022"]["band_covered_isins"] >= 2
