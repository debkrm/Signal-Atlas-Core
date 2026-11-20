"""
Audit §99.10 work-order items 1-3, unit level (§100 round).

1. N-195's closure is bound to the artifact: the seq-10 profitability cells in
   `CURRENT_STAGE_OF_WORK.md` carry the digits the trial_010 verdict artifact computes, and `probe_n195`
   is the fix-assertion that fails the moment the document drifts from it.
2. The verifier inventory is pinned (§99.10 item 2): discovery is compared against a committed set, so a
   deleted `verify_*.py` fails closed by name and a new one cannot enter the gate unnamed.
3. The registry reader surface presents the executed `criteria_fingerprint`, not only `criteria_version`
   (§99.10 item 3), and says `NOT RECORDED` for a row that carries no hash.
"""

from decimal import Decimal
import json
from pathlib import Path

import pytest

from scripts.compare_seq10_baselines import curve_metrics
from scripts.probe_audit_findings import probe_n195
from scripts.verify_audit_append_only import (
    EXPECTED_VERIFICATION_SCRIPTS,
    check_verification_scripts,
    discovered_verification_scripts,
    verification_inventory_problem,
)
from signal_core.research.trials import TrialRegistry

FINGERPRINT = "CRIT-FPR-V1-" + "5" * 64


# --- §99.10 item 1: N-195 ----------------------------------------------------------------


def test_s100_seq10_status_row_publishes_the_artifact_profit_factors():
    """The fix-assertion is the test: probe_n195 reads both figures from the artifact, never a literal."""
    probe_n195()


# --- §99.10 item 2: the pinned verifier inventory ----------------------------------------


def test_s100_verifier_inventory_pin_is_the_discovered_set():
    discovered = discovered_verification_scripts()
    assert list(EXPECTED_VERIFICATION_SCRIPTS) == discovered
    # §101.12 item 1 adds `verify_seq10_baseline_comparison.py` to the discovered sweep.
    assert len(discovered) == 11
    assert verification_inventory_problem(discovered) is None


def test_s100_deleting_a_verifier_fails_closed_by_name(monkeypatch, capsys):
    """A check must not be able to leave the gate by deleting its own file (§99.10 item 2)."""
    deleted = EXPECTED_VERIFICATION_SCRIPTS[0]
    short = [name for name in discovered_verification_scripts() if name != deleted]

    problem = verification_inventory_problem(short)
    assert problem is not None and deleted in problem, problem

    # The gate's own discovery path: the failure is reported before any verifier runs.
    monkeypatch.setattr(
        "scripts.verify_audit_append_only.discovered_verification_scripts", lambda: short
    )
    passed, exits = check_verification_scripts()
    assert passed is False
    assert exits == {}
    assert deleted in capsys.readouterr().out


def test_s100_a_new_verifier_must_be_named_in_the_pin():
    extra = sorted(discovered_verification_scripts() + ["scripts/verify_unpinned_probe.py"])
    problem = verification_inventory_problem(extra)
    assert problem is not None and "scripts/verify_unpinned_probe.py" in problem, problem
    assert "EXPECTED_VERIFICATION_SCRIPTS" in problem


# --- §99.10 item 3: the registry reader surface ------------------------------------------


def _registry(tmp_path, *, evaluated: bool) -> TrialRegistry:
    path = tmp_path / "trial_registry.jsonl"
    registry = TrialRegistry(path)
    registry.append_trial(
        trial_id="TRIAL-S100-A",
        hypothesis="surface test",
        rationale="§99.10 item 3",
        partition="IN_SAMPLE",
        canonical_params={"param_a": 1},
        fold_spec_fingerprint="FOLD-SPEC-V1-" + "a" * 64,
        dataset_fingerprint="DATA-FP-1",
        criteria_version="1.1.16",
        timestamp_utc="2026-11-20T10:00:00Z",
        sharpe_ratio=None,
    )
    if evaluated:
        registry.append_trial_evaluation(
            trial_id="TRIAL-S100-A",
            sharpe_ratio=Decimal("0.50"),
            returns_digest="RET-V1-" + "b" * 64,
            observation_count=10,
            evaluated_at_utc="2026-11-20T11:00:00Z",
            criteria_fingerprint=FINGERPRINT,
        )
    return registry


def test_s100_registry_presents_the_executed_fingerprint(tmp_path):
    provenance = _registry(tmp_path, evaluated=True).criteria_provenance("TRIAL-S100-A")
    assert provenance["criteria_version"] == "1.1.16"
    assert provenance["criteria_fingerprint"] == FINGERPRINT


def test_s100_registry_says_not_recorded_instead_of_the_version(tmp_path):
    provenance = _registry(tmp_path, evaluated=False).criteria_provenance("TRIAL-S100-A")
    assert provenance["criteria_version"] == "1.1.16"
    assert provenance["criteria_fingerprint"] is None


def test_s100_registry_provenance_refuses_an_unregistered_id(tmp_path):
    with pytest.raises(Exception) as excinfo:
        _registry(tmp_path, evaluated=False).criteria_provenance("TRIAL-ABSENT")
    assert "TRIAL-ABSENT" in str(excinfo.value)


# --- §99.10 item 3: the comparison's metric convention -----------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_s100_curve_metrics_reproduce_the_seq10_artifact():
    """The comparison's curve convention is the engine's: it rebuilds the artifact's own drawdown."""
    artifact = json.loads(
        (
            REPO_ROOT
            / "reports"
            / "verdicts"
            / "trial_010"
            / "phase3b2_swing_baseline_2022_2024_verdict.json"
        ).read_text(encoding="utf-8")
    )
    equity = [Decimal("1000000.00")]
    for day in sorted(artifact["daily_returns"]):
        equity.append(equity[-1] * (Decimal(1) + Decimal(artifact["daily_returns"][day])))
    metrics = curve_metrics(equity)
    claimed = artifact["in_sample_metrics"]
    assert equity[-1].quantize(Decimal("0.01")) == Decimal(claimed["end_equity"])
    assert abs(Decimal(metrics["max_drawdown"]) - Decimal(claimed["max_drawdown"])) < Decimal("1e-24")


def test_s100_committed_comparison_decision_is_computed_from_its_own_inputs():
    artifact = json.loads(
        (
            REPO_ROOT / "reports" / "analysis" / "s100" / "seq10_baseline_comparison.json"
        ).read_text(encoding="utf-8")
    )
    inputs = artifact["decision"]["inputs"]
    signal = Decimal(inputs["seq10_trade_profit_factor"]) > Decimal(
        inputs["random_entry_trade_profit_factor_p95"]
    )
    investable = Decimal(inputs["seq10_final_equity"]) > Decimal(
        inputs["niftybees_buy_hold_final_equity"]
    )
    assert artifact["decision"]["signal_condition_met"] is signal
    assert artifact["decision"]["investability_condition_met"] is investable
    assert artifact["decision"]["verdict"].startswith("GO" if signal and investable else "KILL")
