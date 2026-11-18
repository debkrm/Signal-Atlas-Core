"""
Unit tests for the Audit §76 remediation items (audit §76 at 7a32f24, reviewing 348b5ba).

Target invariants (criteria 1.1.6, no numeric threshold changed):
- N-139: re-pinning the trials manifest does not move `criteria_fingerprint`; the pin stays mandatory
  in the loader and a threshold edit still moves the fingerprint.
- N-141: `min_haircut_sharpe_ratio` is a binding criterion (`CRIT-OVERFIT-04`), and 0.0000 FAILS it.
- Ruling 1: `CRIT-STAT-01` / `CRIT-STAT-02` evaluate the liquidated book, with the closed-only pair and
  the ex-top-1 / ex-top-3 sensitivity on the same evidence line.
- Ruling 2: `CRIT-STAT-03` evaluates the weight at trade entry; a hold-period appreciation is a
  non-gating disclosure.
- N-140 / Ruling 3: traded-row resolution and dataset instrument resolution are separate criteria with
  separate thresholds, and 196 / 211 = 92.8910% still fails closed.
- N-142: every refusal is attributed by order side and reason, so a refused SELL is visible.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from signal_core.contracts.criteria import (
    DEFAULT_CRITERIA_PATH,
    CriteriaValidationError,
    compute_criteria_fingerprint,
    load_go_no_go_criteria,
)
from signal_core.contracts.order_types import OrderSide
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.reporting.verdicts import evaluate_verdicts
from signal_core.strategy.swing import tabulate_rejections
from scripts.run_phase3b2_walkforward import liquidate_open_book, run_phase3b2_walkforward


def _criteria():
    return load_go_no_go_criteria()


def _by_id(bundle_kwargs: dict) -> dict:
    """Evaluates a minimal bundle and returns {criterion_id: CriterionEvaluation}."""
    bundle = {"evaluated_at_utc": "2026-11-17T00:00:00+00:00"}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


# --- N-139: the fingerprint is stable across a manifest re-pin --------------------------------


def test_n139_manifest_pin_is_outside_the_criteria_fingerprint(tmp_path):
    crit = _criteria()
    base = compute_criteria_fingerprint(crit)

    # Re-pinning the trials manifest (which every append rewrites) must not move the anchor.
    repinned = dataclasses.replace(
        crit, expected_trial_registry_manifest_sha256="0" * 64
    )
    assert compute_criteria_fingerprint(repinned) == base

    # A threshold edit still must move it. That is what the fingerprint is for.
    threshold_moved = dataclasses.replace(crit, min_profit_factor=Decimal("1.49"))
    assert compute_criteria_fingerprint(threshold_moved) != base

    # The pin is still mandatory: an absent pin fails the load, so G2A-6.8a still has an anchor.
    text = DEFAULT_CRITERIA_PATH.read_text(encoding="utf-8")
    pin_line = next(
        line for line in text.splitlines()
        if line.strip().startswith("expected_trial_registry_manifest_sha256:")
    )
    stripped = tmp_path / "criteria_without_pin.yaml"
    stripped.write_text(text.replace(pin_line + "\n", ""), encoding="utf-8")
    with pytest.raises(CriteriaValidationError):
        load_go_no_go_criteria(stripped)


# --- N-141: the committed haircut threshold is a gate, not a comment ---------------------------


def test_n141_haircut_sharpe_ratio_is_gated():
    assert _criteria().min_haircut_sharpe_ratio == Decimal("1.25")

    # seq 9's computed value: a Sharpe that survives no multiple-testing haircut.
    failed = _by_id({"haircut_sharpe_ratio": Decimal("0.000000"), "evaluated_trial_count": 5})
    assert failed["CRIT-OVERFIT-04"].status.value == "FAIL"
    assert failed["CRIT-OVERFIT-04"].computed_value == "0.0000"

    passed = _by_id({"haircut_sharpe_ratio": Decimal("1.30"), "evaluated_trial_count": 5})
    assert passed["CRIT-OVERFIT-04"].status.value == "PASS"

    # NOT RUN when the estimator could not produce a value — never PASS on an absent statistic.
    one_trial = _by_id({"haircut_sharpe_ratio": Decimal("1.30"), "evaluated_trial_count": 1})
    assert one_trial["CRIT-OVERFIT-04"].status.value == "NOT RUN"
    assert _by_id({})["CRIT-OVERFIT-04"].status.value == "NOT RUN"


# --- Ruling 1: both statistics on the liquidated book -----------------------------------------


def test_ruling1_statistics_are_evaluated_on_the_liquidated_book():
    live = _by_id({
        "total_trades": 205,
        # Findings N-148 (§78.8): the de-censored count is only gated when the bundle can reconcile
        # it, so a complete fixture declares the liquidated count beside the total.
        "liquidated_trade_count": 205,
        "profit_factor": Decimal("1.6440"),
        "closed_only_trade_count": 193,
        "closed_only_profit_factor": Decimal("0.9920"),
        "liquidated_pf_ex_top_1": Decimal("1.4812"),
        "liquidated_pf_ex_top_3": Decimal("1.2939"),
    })
    # 205 round trips against >= 100, and PF 1.6440 against >= 1.50 — the de-censored book.
    assert live["CRIT-STAT-01"].status.value == "PASS"
    assert live["CRIT-STAT-01"].computed_value == "205"
    assert live["CRIT-STAT-02"].status.value == "PASS"
    assert live["CRIT-STAT-02"].computed_value == "1.6440"

    # The closed-only pair and the sensitivity are on the same rows as disclosure.
    assert "193" in live["CRIT-STAT-01"].evidence
    assert "0.9920" in live["CRIT-STAT-01"].evidence
    assert "1.4812" in live["CRIT-STAT-02"].evidence
    assert "1.2939" in live["CRIT-STAT-02"].evidence

    # A censored-only bundle fails both: 193 < ... no, 193 still clears 100 on count; the PF is the
    # statistic the censoring actually flips, and the count must be the liquidated one when supplied.
    censored = _by_id({
        "total_trades": 193,
        "profit_factor": Decimal("0.9920"),
        "closed_only_trade_count": 193,
        "closed_only_profit_factor": Decimal("0.9920"),
    })
    assert censored["CRIT-STAT-02"].status.value == "FAIL"
    assert censored["CRIT-STAT-02"].computed_value == "0.9920"

    short = _by_id({
        "total_trades": 95,
        "liquidated_trade_count": 95,
        "profit_factor": Decimal("1.80"),
    })
    assert short["CRIT-STAT-01"].status.value == "FAIL"


def test_ruling1_liquidated_pf_carries_its_sensitivity():
    """The runner computes ex-top-1 / ex-top-3 from the same rows the PF came from."""
    closed = [
        {"gross_pnl": Decimal("100"), "net_pnl": Decimal("90")},
        {"gross_pnl": Decimal("200"), "net_pnl": Decimal("190")},
        {"gross_pnl": Decimal("300"), "net_pnl": Decimal("290")},
        {"gross_pnl": Decimal("400"), "net_pnl": Decimal("390")},
        {"gross_pnl": Decimal("-100"), "net_pnl": Decimal("-110")},
    ]
    result = liquidate_open_book(
        open_lots={},
        bars_by_isin_date={},
        liquidation_date=datetime.date(2023, 12, 29),
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        closed_trades=closed,
    )
    assert result["liquidated_trade_count"] == 5
    assert result["liquidated_profit_factor"] == Decimal("10")      # 1000 / 100
    assert result["liquidated_pf_ex_top_1"] == Decimal("6")         # 600 / 100
    assert result["liquidated_pf_ex_top_3"] == Decimal("1")         # 100 / 100
    assert result["closed_only_profit_factor"] == Decimal("10")


# --- Ruling 2: the weight is measured at entry -----------------------------------------------


def test_ruling2_stat03_is_evaluated_at_trade_entry():
    appreciated = _by_id({
        "max_single_position_weight": Decimal("0.082769"),
        "max_hold_period_position_weight": Decimal("0.13"),
    })
    assert appreciated["CRIT-STAT-03"].status.value == "PASS"
    assert "0.1300" in appreciated["CRIT-STAT-03"].evidence

    oversized_at_entry = _by_id({
        "max_single_position_weight": Decimal("0.12"),
        "max_hold_period_position_weight": Decimal("0.12"),
    })
    assert oversized_at_entry["CRIT-STAT-03"].status.value == "FAIL"

    assert _by_id({})["CRIT-STAT-03"].status.value == "NOT RUN"


# --- N-140 / Ruling 3: rows versus instruments ----------------------------------------------


def test_n140_row_resolution_and_dataset_completeness_are_separate():
    both = _by_id({
        "traded_eq_resolution_pct": Decimal("100.0000"),
        "dataset_instrument_resolution_pct": Decimal("92.8910"),
        "dataset_instrument_resolution_numerator": 196,
        "dataset_instrument_resolution_denominator": 211,
        "unresolved_dataset_instruments": [
            {"symbol": "SHELLCO", "reason": "ISIN_TRANSITION_WITHIN_DATASET_SPAN"}
        ],
    })
    # Every traded row carries an identity; the research universe still missed 15 instruments.
    assert both["CRIT-DATA-05"].status.value == "PASS"
    assert both["CRIT-DATA-05"].computed_value == "100.0000%"
    assert both["CRIT-DATA-07"].status.value == "FAIL"
    assert both["CRIT-DATA-07"].computed_value == "92.8910%"
    assert "196" in both["CRIT-DATA-07"].evidence
    assert "211" in both["CRIT-DATA-07"].evidence
    assert "SHELLCO" not in both["CRIT-DATA-07"].evidence  # names live in the artifact, not the row
    assert _criteria().min_dataset_instrument_resolution_pct == Decimal("100.0")

    complete = _by_id({"dataset_instrument_resolution_pct": Decimal("100.0")})
    assert complete["CRIT-DATA-07"].status.value == "PASS"

    # Neither criterion can stand in for the other.
    assert _by_id({})["CRIT-DATA-07"].status.value == "NOT RUN"


# --- N-142: refusals attributed by side and reason -------------------------------------------


def test_n142_refused_sell_is_tabulated_under_its_side_and_reason():
    refused_sell = SimpleNamespace(
        status=FillStatus.REJECTED_INSUFFICIENT_TURNOVER,
        candidate=SimpleNamespace(side=OrderSide.SELL),
    )
    refused_buy = SimpleNamespace(
        status=FillStatus.REJECTED_BELOW_MIN_NOTIONAL,
        candidate=SimpleNamespace(side=OrderSide.BUY),
    )
    locked_buy = SimpleNamespace(
        status=FillStatus.REJECTED_LOCKED_SESSION,
        candidate=SimpleNamespace(side=OrderSide.BUY),
    )
    filled = SimpleNamespace(
        status=FillStatus.FILLED,
        candidate=SimpleNamespace(side=OrderSide.BUY),
    )
    unfilled_no_ticket = SimpleNamespace(status=None, candidate=SimpleNamespace(side=OrderSide.BUY))

    table = tabulate_rejections(
        [refused_sell, refused_sell, refused_buy, locked_buy, filled, unfilled_no_ticket]
    )
    # The involuntary hold (§5.3) is visible as a SELL refusal, not hidden in a total.
    assert table["SELL"]["REJECTED_INSUFFICIENT_TURNOVER"] == 2
    assert table["BUY"]["REJECTED_BELOW_MIN_NOTIONAL"] == 1
    assert table["BUY"]["REJECTED_LOCKED_SESSION"] == 1
    assert filled.status not in table["BUY"] or "FILLED" not in table["BUY"]
    assert sum(c for reasons in table.values() for c in reasons.values()) == 4


# --- Criteria 1.1.6 changes no numeric threshold ---------------------------------------------


def test_criteria_1_1_6_changes_no_numeric_threshold():
    """1.1.6 moved definitions only. 1.1.7 (Audit §77) adds two bindings; both asserted below."""
    crit = _criteria()
    assert crit.version == "1.1.15"
    assert crit.min_positive_is_fold_ratio == Decimal("0.75")
    assert crit.min_fold_liquidated_pf == Decimal("1.30")
    assert crit.min_liquidated_pf_ex_top_1 == Decimal("1.40")
    assert crit.min_positive_walk_forward_fold_ratio == Decimal("0.80")
    assert crit.min_total_trades == 100
    assert crit.min_profit_factor == Decimal("1.50")
    assert crit.min_deflated_sharpe_ratio == Decimal("0.95")
    assert crit.min_haircut_sharpe_ratio == Decimal("1.25")
    assert crit.max_single_position_weight == Decimal("0.10")
    assert crit.max_portfolio_drawdown == Decimal("0.25")
    assert crit.min_traded_eq_resolution_pct == Decimal("100.0")
    assert crit.min_dataset_instrument_resolution_pct == Decimal("100.0")
    assert crit.min_entry_notional == Decimal("25000")
    assert crit.min_fill_notional == Decimal("5000")


# --- The artifact carries the new disclosures ------------------------------------------------


def test_short_walkforward_emits_the_s76_disclosures(tmp_path):
    res = run_phase3b2_walkforward(
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=tmp_path / "verdicts",
        in_sample_only=True,
        max_sessions=6,
        write_verdict_files=True,
    )
    art = json.loads(
        (tmp_path / "verdicts" / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    assert art["criteria_version"] == "1.1.15"
    ids = {e["criterion_id"] for e in art["evaluations"]}
    assert {"CRIT-DATA-07", "CRIT-OVERFIT-04"} <= ids

    # Ruling 1 / 2: both the gated value and the non-gating disclosure are in the bytes.
    assert art["liquidated_trade_count"] >= art["open_positions_at_end_count"]
    assert "max_hold_period_position_weight" in art
    assert "liquidated_pf_ex_top_1" in art and "liquidated_pf_ex_top_3" in art

    # Ruling 3 / N-140: numerator and denominator beside every unresolved instrument.
    assert art["dataset_instrument_resolution_denominator"] > 0
    assert art["dataset_instrument_resolution_numerator"] <= art["dataset_instrument_resolution_denominator"]
    assert art["traded_eq_rows_total"] > 0
    assert isinstance(art["unresolved_dataset_instruments"], list)
    for row in art["unresolved_dataset_instruments"]:
        assert row["reason"] == "ISIN_TRANSITION_WITHIN_DATASET_SPAN"
        assert row["symbol"]

    # N-142: per-year refusals reconcile with the rejection total.
    per_year = art["coverage_diagnostics"]
    summed = sum(
        count
        for diag in per_year.values()
        for reasons in (diag.get("rejections_by_side_and_reason") or {}).values()
        for count in reasons.values()
    )
    assert summed == sum(int(diag.get("tickets_rejected", 0)) for diag in per_year.values())
    for diag in per_year.values():
        for side, reasons in (diag.get("rejections_by_side_and_reason") or {}).items():
            assert side in ("BUY", "SELL")
            assert all(reason.startswith("REJECTED_") for reason in reasons)
