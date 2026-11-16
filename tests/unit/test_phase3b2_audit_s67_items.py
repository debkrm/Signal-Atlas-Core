"""
Unit tests for Phase 3B-2b Audit §67 Remediation Items (Commit 605a488 / §67).
Target Invariants:
- H-114: The authoritative simulator rejects a post-slippage BUY at/above the effective upper
  circuit limit and a SELL at/below the effective lower limit, and mentions the observed count.
- N-111: record_trial=False refuses an unregistered trial_id instead of fabricating a record.
- N-112: Merger cash-in-lieu settles at the consideration price, not the book value.
- N-115: The fractional merger slice is not double-booked as a zero-gross closed trade.
- Trial #4: DeliverySwingTrendStrategy trims a position above the configured weight threshold.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_types import OrderProduct, OrderSide, OrderType
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import ExecutionOrder
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.reporting.verdicts import VerdictStatus, evaluate_verdicts
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import (
    CorporateAction,
    CorporateActionType,
    build_production_security_master,
)
from signal_core.strategy.swing import DeliverySwingTrendStrategy
from scripts.run_phase3b2_walkforward import run_phase3b2_walkforward
from tests.unit.test_phase3b2_walkforward_runner import make_synthetic_snapshot


def _simulator() -> ExecutionFillSimulator:
    criteria = load_go_no_go_criteria()
    cal = load_anchored_nse_trading_calendar(criteria=criteria)
    return ExecutionFillSimulator(criteria=criteria, trading_calendar=cal.sessions)


def _band(trade_date: datetime.date, upper: Decimal, lower: Decimal) -> PriceBandRecord:
    return PriceBandRecord(
        isin="INE009A01021",
        trade_date=trade_date,
        series="EQ",
        upper_circuit_limit=upper,
        lower_circuit_limit=lower,
    )


def test_h114_buy_at_upper_circuit_is_rejected():
    """
    H-114: A bar opening one tick below the upper limit with an adverse-slippage BUY cannot
    fill at the limit; the simulator rejects it rather than clamping the fill onto the band.
    """
    sim = _simulator()
    trade_date = datetime.date(2023, 7, 13)
    upper = Decimal("1375.00")
    lower = Decimal("1237.50")

    order = ExecutionOrder(
        order_id="ORD-H114-UC",
        instrument_id="INE009A01021",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=100,
        signal_date=datetime.date(2023, 7, 12),
        target_date=trade_date,
        product=OrderProduct.DELIVERY,
    )
    bar = PriceBar(
        instrument_id="INE009A01021",
        trade_date=trade_date,
        open=Decimal("1374.95"),
        high=upper,
        low=Decimal("1374.90"),
        close=Decimal("1374.95"),
        volume=100000,
    )

    result = sim.simulate_order(
        order=order, bar=bar, price_band=_band(trade_date, upper, lower), explicit_series=ExchangeSeries.EQ
    )
    assert result.status == FillStatus.REJECTED_UPPER_CIRCUIT
    assert result.executed_price is None
    assert result.filled_quantity == 0
    assert result.effective_upper_circuit_limit == upper


def test_h114_sell_at_lower_circuit_is_rejected():
    """H-114: A post-slippage SELL clamped onto the lower limit cannot fill into a frozen bid."""
    sim = _simulator()
    trade_date = datetime.date(2023, 7, 13)
    upper = Decimal("1375.00")
    lower = Decimal("1237.50")

    order = ExecutionOrder(
        order_id="ORD-H114-LC",
        instrument_id="INE009A01021",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=100,
        signal_date=datetime.date(2023, 7, 12),
        target_date=trade_date,
        product=OrderProduct.DELIVERY,
    )
    bar = PriceBar(
        instrument_id="INE009A01021",
        trade_date=trade_date,
        open=Decimal("1237.55"),
        high=Decimal("1237.60"),
        low=lower,
        close=Decimal("1237.55"),
        volume=100000,
    )

    result = sim.simulate_order(
        order=order, bar=bar, price_band=_band(trade_date, upper, lower), explicit_series=ExchangeSeries.EQ
    )
    assert result.status == FillStatus.REJECTED_LOWER_CIRCUIT
    assert result.executed_price is None
    assert result.effective_lower_circuit_limit == lower


def test_h114_runner_evidence_reports_observed_violation_count(tmp_path: Path):
    """
    H-114 (evidence half) / CA-3(c): the 2022 fixture window has no sourced price-band report, so
    the run's circuit criteria are NOT RUN with that reason rather than PASS on the band stub.
    """
    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=80)
    res = run_phase3b2_walkforward(
        snapshot_path=snap_p,
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        max_sessions=80,
        trial_id="TRIAL-TEST-S67-EVIDENCE",
        write_verdict_files=False,
    )
    exec3 = next(e for e in res.verdict_report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in res.verdict_report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    # CA-3(c): the fixture evaluates 2022 sessions, which have no attested sec_list report, so the
    # circuit criteria are out of scope and say why instead of claiming enforcement.
    assert exec3.status == VerdictStatus.NOT_RUN
    assert exec4.status == VerdictStatus.NOT_RUN
    assert "no sourced NSE price-band report" in exec3.evidence
    assert "no sourced NSE price-band report" in exec4.evidence
    assert "Simulator strictly enforces" not in exec3.evidence
    assert "Simulator strictly enforces" not in exec4.evidence


def test_n123_sourced_window_keeps_numeric_circuit_evidence():
    """N-123: a band-sourced window still exercises N-118's numeric fill-count evidence."""
    bundle = {
        "evaluation_start_date": "2024-01-16",
        "evaluation_end_date": "2024-03-29",
        "prohibit_buy_at_upper_circuit": True,
        "prohibit_sell_at_lower_circuit": True,
        "upper_circuit_buy_judged_fills": 2,
        "upper_circuit_buy_violating_fills": 0,
        "upper_circuit_buy_missing_limit_fills": 0,
        "lower_circuit_sell_judged_fills": 2,
        "lower_circuit_sell_violating_fills": 0,
        "lower_circuit_sell_missing_limit_fills": 0,
    }
    report = evaluate_verdicts(bundle)
    exec3 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-03")
    exec4 = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-04")
    assert exec3.status == VerdictStatus.PASS
    assert exec4.status == VerdictStatus.PASS
    assert exec3.evidence.startswith("0 of 2 judged BUY fill(s)"), exec3.evidence
    assert re.match(r"^\d+ of \d+ judged SELL fill\(s\)", exec4.evidence), exec4.evidence


def test_n111_rerender_unknown_trial_fails_closed(tmp_path: Path):
    """N-111: record_trial=False for an unregistered trial_id raises ValueError, no artifact."""
    snap_p = make_synthetic_snapshot(tmp_path, num_sessions=50)
    with pytest.raises(ValueError, match="unregistered trial_id"):
        run_phase3b2_walkforward(
            snapshot_path=snap_p,
            registry_path=tmp_path / "trial_reg.jsonl",
            verdict_output_dir=tmp_path / "verdicts",
            max_sessions=10,
            trial_id="TRIAL-TEST-N111-UNREGISTERED",
            record_trial=False,
        )


def _buy_27_hdfc(portfolio: Portfolio, trade_date: datetime.date) -> None:
    criteria = load_go_no_go_criteria()
    order = ExecutionOrder(
        order_id="ORD-HDFC-N112",
        instrument_id="INE001A01036",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=27,
        signal_date=trade_date - datetime.timedelta(days=1),
        target_date=trade_date,
        product=OrderProduct.DELIVERY,
    )
    fill = ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=trade_date,
        latency_sessions=1,
        filled_quantity=27,
        unfilled_quantity=0,
        executed_price=Decimal("2650.00"),
        slippage=None,
        costs=ExecutionFillSimulator(criteria=criteria).cost_model.compute_costs(
            trade_date=trade_date,
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=27,
            price=Decimal("2650.00"),
        ),
        circuit_evidence_present=True,
        rejection_reason=None,
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)


def test_n112_merger_cash_in_lieu_settles_at_consideration_price():
    """
    N-112: A merger carrying a consideration price credits (fraction × consideration), and
    portfolio equity moves by the difference between consideration and book value.
    """
    criteria = load_go_no_go_criteria()
    d_buy = datetime.date(2023, 7, 10)
    d_merger = datetime.date(2023, 7, 13)
    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=d_buy
    )
    _buy_27_hdfc(portfolio, d_buy)

    pos = portfolio.get_position("INE001A01036")
    basis_before = pos.total_cost_basis
    equity_before = portfolio.current_total_equity()

    sec_master = build_production_security_master(include_cash_universe=True)
    merger = [
        a for a in sec_master.get_corporate_actions("INE001A01036")
        if a.ex_date == d_merger and a.action_type == CorporateActionType.MERGER
    ][0]
    assert merger.delisting_price == Decimal("1641.10")

    cash_entry = portfolio.apply_corporate_action(merger)
    assert cash_entry is not None
    # 27 × 42 / 25 = 45 whole shares, remainder 9/25 = 0.36 shares at ₹1,641.10
    assert cash_entry.amount == Decimal("590.80")

    new_pos = portfolio.get_position("INE040A01034")
    assert new_pos.quantity == 45
    basis_removed = basis_before - new_pos.total_cost_basis

    equity_after = portfolio.current_total_equity()
    # The settlement moves equity by (consideration − book) × fraction, not by zero.
    assert equity_after == equity_before - basis_removed + cash_entry.amount
    assert equity_after != equity_before


def test_n115_fractional_merger_slice_is_not_a_closed_trade(tmp_path: Path):
    """
    N-115: A run that holds HDFC across the 2023-07-13 merger records the fractional
    entitlement only as MERGER_CASH_IN_LIEU, never as a fractional zero-gross closed trade.
    """
    res = run_phase3b2_walkforward(
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        in_sample_only=True,
        fail_closed_on_unexplained=False,
        trial_id="TRIAL-TEST-N115",
        write_verdict_files=False,
    )
    merger_entries = [
        e for e in res.portfolio.ledger.entries
        if e.entry_type.value == "MERGER_CASH_IN_LIEU"
    ]
    assert merger_entries, "Expected the held HDFC position to settle a fractional merger slice"
    for trade in res.closed_trades:
        qty = Decimal(trade["quantity"])
        assert qty == qty.to_integral_value(), (
            f"Fractional quantity {qty} represented as a closed trade for "
            f"{trade['isin']} (Finding N-115)"
        )


def test_trial4_trim_emits_partial_sell_above_threshold():
    """Trial #4: a position above the trim threshold emits a T+1 partial SELL back to target."""
    criteria = load_go_no_go_criteria()
    as_of = datetime.date(2023, 6, 1)
    next_session = datetime.date(2023, 6, 2)
    isin = "INE009A01021"

    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=as_of
    )
    _buy_shares = ExecutionOrder(
        order_id="ORD-TRIM-BUY",
        instrument_id=isin,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=113,
        signal_date=as_of - datetime.timedelta(days=1),
        target_date=as_of,
        product=OrderProduct.DELIVERY,
    )
    fill = ExecutionFillResult(
        order=_buy_shares,
        status=FillStatus.FILLED,
        fill_date=as_of,
        latency_sessions=1,
        filled_quantity=113,
        unfilled_quantity=0,
        executed_price=Decimal("1000.00"),
        slippage=None,
        costs=ExecutionFillSimulator(criteria=criteria).cost_model.compute_costs(
            trade_date=as_of,
            side=OrderSide.BUY,
            product=OrderProduct.DELIVERY,
            quantity=113,
            price=Decimal("1000.00"),
        ),
        circuit_evidence_present=True,
        rejection_reason=None,
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)

    marks = {isin: Decimal("1200.00")}
    features = {
        isin: SimpleNamespace(close=Decimal("1200.00"), sma_20=Decimal("1150.00"), sma_50=Decimal("1100.00"))
    }

    baseline = DeliverySwingTrendStrategy()
    baseline_intents = baseline.generate_signals(
        as_of=as_of,
        next_session=next_session,
        universe=[isin],
        features=features,
        portfolio=portfolio,
        latest_market_prices=marks,
    )
    assert not any(i.side == OrderSide.SELL for i in baseline_intents)

    trimmed = DeliverySwingTrendStrategy(
        max_position_weight_trim_threshold=Decimal("0.095")
    )
    intents = trimmed.generate_signals(
        as_of=as_of,
        next_session=next_session,
        universe=[isin],
        features=features,
        portfolio=portfolio,
        latest_market_prices=marks,
    )
    sells = [i for i in intents if i.side == OrderSide.SELL]
    assert len(sells) == 1
    trim = sells[0]
    assert trim.signal_date == as_of
    assert trim.target_date == next_session
    assert trim.quantity is not None
    equity = portfolio.current_total_equity(marks)
    residual_value = (Decimal(113) - Decimal(trim.quantity)) * Decimal("1200.00")
    assert residual_value <= equity * Decimal("0.0800")
    assert trim.quantity < 113
