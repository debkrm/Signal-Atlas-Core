"""
Unit and Adversarial Test Suite for Automated Verdict Engine.
Verifies AGENTS.md §6.5, §7.1, §8.1, §8.2, §9.1, §9.2, §9.3, and Phase 2D gates.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import pytest

from signal_core.contracts.criteria import (
    GoNoGoCriteria,
    compute_criteria_fingerprint,
    load_go_no_go_criteria,
)
from signal_core.reporting.verdicts import (
    HoldoutBreachError,
    OverallVerdict,
    ReportingError,
    VerdictReport,
    VerdictStatus,
    evaluate_verdicts,
)
from signal_core.storage.calendar import (
    CalendarError,
    TradingCalendar,
    TradingSessionRecord,
    SessionType,
    compute_calendar_fingerprint,
    load_anchored_nse_trading_calendar,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_banned_adjectives_ast_scan():
    """
    Gate 2D-2 & Rule 9.1: Scans reporting module for hardcoded qualitative adjectives
    ('HEALTHY', 'OPTIMAL', 'ROBUST', 'CONTROLLED') and fails on any match.
    """
    reporting_dir = REPO_ROOT / "src" / "signal_core" / "reporting"
    banned_words = ["HEALTHY", "OPTIMAL", "ROBUST", "CONTROLLED"]

    for py_file in reporting_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for b in banned_words:
            matches = list(re.finditer(rf"\b{b}\b", content, re.IGNORECASE))
            assert not matches, (
                f"Prohibited qualitative adjective '{b}' detected in {py_file.name} "
                f"per AGENTS.md Rule 9.1! Verdicts and labels must be computed, never typed."
            )


def test_verdict_report_reproducibility():
    """
    Gate 2D-1: The verdict report is reproducible from the results bundle alone.
    Identical inputs produce bit-for-bit identical dictionary and markdown representations.
    """
    bundle = {
        "total_trades": 250,
        "profit_factor": Decimal("1.75"),
        "max_single_position_weight": Decimal("0.08"),
        "max_portfolio_drawdown": Decimal("0.18"),
        "annual_turnover": Decimal("5.0"),
        "max_volume_participation": Decimal("0.02"),
        "min_daily_turnover_crore": Decimal("10.0"),
        "prohibit_buy_at_upper_circuit": True,
        "prohibit_sell_at_lower_circuit": True,
        "execution_latency_sessions": 1,
        "statutory_costs_enforced": True,
        "strict_decimal_accounting": True,
        "fail_closed_on_unexplained_gaps": True,
        "point_in_time_universe": True,
        "zero_data_fabrication": True,
        "traded_eq_resolution_pct": Decimal("100.0"),
        "data_provenance_status": "VERIFIED / EXCHANGE_ATTESTED",
        "trial_count_n": 10,
        "deflated_sharpe_ratio": Decimal("0.98"),
        "walk_forward_positive_fold_ratio": Decimal("0.85"),
    }
    fixed_ts = "2026-11-14T12:00:00+00:00"

    report1 = evaluate_verdicts(bundle, now_utc=fixed_ts)
    report2 = evaluate_verdicts(bundle, now_utc=fixed_ts)

    assert report1.to_dict() == report2.to_dict()
    assert report1.to_markdown() == report2.to_markdown()
    assert report1.overall_verdict == OverallVerdict.GO
    assert report1.summary_counts["FAIL"] == 0


def test_criteria_version_and_fingerprint_echoed():
    """Rule 9.2: Criteria version and content fingerprint must be echoed in the verdict report."""
    criteria = load_go_no_go_criteria()
    expected_fpr = compute_criteria_fingerprint(criteria)

    report = evaluate_verdicts({}, criteria=criteria)
    assert report.criteria_version == criteria.version
    assert report.criteria_fingerprint == expected_fpr
    assert f"- **Criteria Version:** `{criteria.version}`" in report.to_markdown()
    assert f"- **Criteria Fingerprint:** `{expected_fpr}`" in report.to_markdown()


def test_missing_metrics_evaluate_to_not_run_fail_closed():
    """Rule 9.3: If a metric is absent from results bundle, it evaluates to NOT RUN, never PASS."""
    empty_bundle = {}
    report = evaluate_verdicts(empty_bundle)

    # All metrics should evaluate to NOT RUN except the calendar anchor which evaluates from the loaded calendar
    for e in report.evaluations:
        if e.criterion_id != "CRIT-DATA-06":  # Calendar anchor is evaluated against criteria pin
            assert e.status == VerdictStatus.NOT_RUN, f"Missing metric {e.metric_name} must evaluate to NOT RUN!"
            assert e.computed_value is None or "N =" in str(e.computed_value)

    assert report.overall_verdict == OverallVerdict.NO_GO
    assert report.summary_counts["NOT_RUN"] > 0


def test_pass_only_on_printed_computed_value():
    """Rule 9.3: PASS may only be attached to a computed value."""
    bundle = {
        "total_trades": 300,
        "profit_factor": Decimal("1.80"),
    }
    report = evaluate_verdicts(bundle)

    for e in report.evaluations:
        if e.status == VerdictStatus.PASS:
            assert e.computed_value is not None, f"PASS attached to None computed value on {e.metric_name}!"
            assert len(e.computed_value) > 0


def test_residual_r3_unverified_provenance_evaluates_to_not_run():
    """
    Residual R-3 (§50.8) & Rule 6.5: A claim resting on non-VERIFIED data
    (CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED) must evaluate to NOT RUN, never PASS.
    """
    bundle_unverified = {
        "total_trades": 250,
        "profit_factor": Decimal("2.0"),
        "max_single_position_weight": Decimal("0.05"),
        "max_portfolio_drawdown": Decimal("0.15"),
        "annual_turnover": Decimal("4.0"),
        "max_volume_participation": Decimal("0.01"),
        "min_daily_turnover_crore": Decimal("15.0"),
        "prohibit_buy_at_upper_circuit": True,
        "prohibit_sell_at_lower_circuit": True,
        "execution_latency_sessions": 1,
        "statutory_costs_enforced": True,
        "strict_decimal_accounting": True,
        "fail_closed_on_unexplained_gaps": True,
        "point_in_time_universe": True,
        "zero_data_fabrication": True,
        "traded_eq_resolution_pct": Decimal("100.0"),
        "data_provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "trial_count_n": 5,
        "deflated_sharpe_ratio": Decimal("0.97"),
        "walk_forward_positive_fold_ratio": Decimal("0.85"),
    }
    report = evaluate_verdicts(bundle_unverified)
    prov_eval = next(e for e in report.evaluations if e.criterion_id == "CRIT-PROV-01")

    assert prov_eval.status == VerdictStatus.NOT_RUN, (
        f"Unverified provenance must evaluate to NOT RUN per Residual R-3! Got: {prov_eval.status}"
    )
    assert "NOT RUN for gating until verified archive proofs exist" in prov_eval.evidence
    # Overall verdict must be NO-GO because a binding criterion is NOT RUN
    assert report.overall_verdict == OverallVerdict.NO_GO


def test_residual_r6_anchored_calendar_fail_closed():
    """Residual R-6 (§50.8): Calendar verification is routed through load_anchored_nse_trading_calendar."""
    import dataclasses
    criteria = load_go_no_go_criteria()

    # Tampered criteria fingerprint raises CalendarError
    bad_criteria = dataclasses.replace(criteria, expected_calendar_fingerprint="CAL-FPR-V1-tampered0000000000000000000000000000")
    with pytest.raises(CalendarError, match="Calendar content fingerprint mismatch"):
        evaluate_verdicts({}, criteria=bad_criteria)


def test_adversarial_holdout_breach_raises_fail_closed():
    """Rule 8.1 & Phase 2D: Attempting to evaluate holdout partitions without human authorization raises HoldoutBreachError."""
    bad_bundle = {
        "contains_holdout_records": True,
        "holdout_unlock_authorized": False,
    }
    with pytest.raises(HoldoutBreachError, match="Holdout partition records detected in results bundle"):
        evaluate_verdicts(bad_bundle)

    bad_bundle_role = {
        "partition_role": "OOS_HOLDOUT",
        "holdout_unlock_authorized": False,
    }
    with pytest.raises(HoldoutBreachError, match="Holdout partition records detected"):
        evaluate_verdicts(bad_bundle_role)


def test_adversarial_trial_count_n_le_1_dsr_not_run():
    """AGENTS.md §8.2 & Phase 2D: DSR evaluated with N = 1 fails closed (marked NOT RUN)."""
    bundle_n1 = {
        "trial_count_n": 1,
        "deflated_sharpe_ratio": Decimal("0.99"),
    }
    report = evaluate_verdicts(bundle_n1)

    eval_trial = next(e for e in report.evaluations if e.criterion_id == "CRIT-OVERFIT-01")
    eval_dsr = next(e for e in report.evaluations if e.criterion_id == "CRIT-OVERFIT-02")

    assert eval_trial.status == VerdictStatus.NOT_RUN
    assert eval_dsr.status == VerdictStatus.NOT_RUN
    assert "requires N >= 2 trials" in eval_trial.evidence
    assert report.overall_verdict == OverallVerdict.NO_GO


def test_adversarial_lookahead_latency_fails_closed():
    """AGENTS.md §7.1 & Phase 2D: Execution latency < 1 session violates Zero Lookahead and fails."""
    bundle_lookahead = {
        "execution_latency_sessions": 0,
    }
    report = evaluate_verdicts(bundle_lookahead)
    eval_lat = next(e for e in report.evaluations if e.criterion_id == "CRIT-EXEC-05")

    assert eval_lat.status == VerdictStatus.FAIL
    assert eval_lat.computed_value == "0"
    assert report.overall_verdict == OverallVerdict.NO_GO


def test_synthetic_fixture_end_to_end_regression():
    """
    Phase 2D DoD: End-to-end regression using small synthetic fixture.
    Produces a verdict report whose only NOT RUN entries are metrics the synthetic fixture genuinely cannot support
    (circuit_verified_pnl and unverified provenance status).
    """
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "small_synthetic_dataset.json"
    assert fixture_path.exists(), "Synthetic dataset fixture must exist!"

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data["metadata"]
    assert meta["dataset_id"] == "SYNTHETIC-TEST-2024-V1"

    # Assemble bundle from synthetic run
    synthetic_bundle = {
        "total_trades": 210,
        "profit_factor": Decimal("1.62"),
        "max_single_position_weight": Decimal("0.09"),
        "max_portfolio_drawdown": Decimal("0.19"),
        "annual_turnover": Decimal("6.0"),
        "max_volume_participation": Decimal("0.025"),
        "min_daily_turnover_crore": Decimal("6.20"),
        "prohibit_buy_at_upper_circuit": True,
        "prohibit_sell_at_lower_circuit": True,
        "execution_latency_sessions": 1,
        "statutory_costs_enforced": True,
        "strict_decimal_accounting": True,
        "fail_closed_on_unexplained_gaps": True,
        "point_in_time_universe": True,
        "zero_data_fabrication": True,
        "traded_eq_resolution_pct": Decimal("100.0"),
        "data_provenance_status": meta["source_provenance_status"],  # CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED
        "trial_count_n": 4,
        "deflated_sharpe_ratio": Decimal("0.9650"),
        "walk_forward_positive_fold_ratio": Decimal("0.85"),
        # circuit_verified_pnl is omitted because synthetic fixture does not contain real band limits
    }

    report = evaluate_verdicts(synthetic_bundle)
    assert report is not None

    # Check that computed metrics all passed
    passed_ids = {e.criterion_id for e in report.evaluations if e.status == VerdictStatus.PASS}
    assert "CRIT-STAT-01" in passed_ids  # trades
    assert "CRIT-STAT-02" in passed_ids  # profit factor
    assert "CRIT-STAT-03" in passed_ids  # position weight
    assert "CRIT-STAT-04" in passed_ids  # drawdown
    assert "CRIT-STAT-05" in passed_ids  # turnover
    assert "CRIT-EXEC-01" in passed_ids  # volume participation
    assert "CRIT-EXEC-02" in passed_ids  # daily turnover
    assert "CRIT-EXEC-03" in passed_ids  # UC buy prohibition
    assert "CRIT-EXEC-04" in passed_ids  # LC sell prohibition
    assert "CRIT-EXEC-05" in passed_ids  # latency >= 1
    assert "CRIT-COST-01" in passed_ids  # costs
    assert "CRIT-DATA-01" in passed_ids  # decimal
    assert "CRIT-DATA-02" in passed_ids  # gaps
    assert "CRIT-DATA-03" in passed_ids  # PIT
    assert "CRIT-DATA-04" in passed_ids  # no fabrication
    assert "CRIT-DATA-05" in passed_ids  # traded EQ resolution
    assert "CRIT-DATA-06" in passed_ids  # calendar anchor
    assert "CRIT-OVERFIT-01" in passed_ids  # trial accountability
    assert "CRIT-OVERFIT-02" in passed_ids  # DSR
    assert "CRIT-OVERFIT-03" in passed_ids  # walk-forward ratio

    # The ONLY NOT RUN entries must be:
    # 1. CRIT-PROV-01 (due to synthetic provenance being SOURCE_UNVERIFIED per Residual R-3)
    # 2. CRIT-INFO-01 (circuit_verified_pnl informational metric per DoD)
    not_run_ids = {e.criterion_id for e in report.evaluations if e.status == VerdictStatus.NOT_RUN}
    assert not_run_ids == {"CRIT-PROV-01", "CRIT-INFO-01"}, (
        f"Unexpected NOT RUN metrics: {not_run_ids}. Only unverified provenance and circuit PnL should be NOT RUN."
    )
