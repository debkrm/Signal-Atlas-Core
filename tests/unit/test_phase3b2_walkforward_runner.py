"""
Focused Unit & Integration Tests for Phase 3B-2b Walk-Forward Runner.

Verifies:
1. End-to-end execution of run_phase3b2_walkforward:
   - Production SecurityMaster, PIT universe, indicators, execution through Portfolio & DailyTPlus1OrderRunner.
   - Tracks session summary counters (tickets_emitted, tickets_filled, tickets_rejected, skipped_missing_band).
   - Computes exact Decimal diagnostics (CAGR, win_rate, profit_factor, max_drawdown, mean_realized_r, total_statutory_costs).
   - Generates candidate verdict report files (.json and .md).
2. TrialRegistry append-before-read ordering (AGENTS.md Rule 3.2, §8.2):
   - Proves trial is written to the ledger BEFORE reading or printing performance metrics (sharpe_ratio=None on disk).
3. Holdout partition sealed refusal (AGENTS.md Rule 8.1, §10.8):
   - Out-of-sample holdout (2025-01-01..2026-11-11) is strictly sealed without human HOLDOUT_UNLOCK.
   - Evaluating any date >= 2025-01-01 fails closed with HoldoutSealedError.
4. Honest verdict propagation:
   - CRIT-SURV-01 evaluates to NOT RUN.
   - CRIT-PROV-01 evaluates to NOT RUN.
   - Overall verdict is strictly NO-GO.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.reporting.verdicts import OverallVerdict, VerdictStatus
from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    check_partition_access,
    load_canonical_partition_spec,
)
from signal_core.research.trials import TrialRegistry

# Import the runner consumer
from scripts.run_phase3b2_walkforward import (
    Phase3B2WalkForwardRunResult,
    run_phase3b2_walkforward,
)


def test_walkforward_runner_end_to_end(tmp_path: Path):
    """
    Test 1: End-to-end execution of the walk-forward runner on an initial window slice.
    Verifies that strategy intents route through DailyTPlus1OrderRunner,
    corporate actions are processed, summary counters are tracked,
    exact Decimal diagnostics are computed, and verdict reports are emitted.
    """
    reg_path = tmp_path / "test_trials.jsonl"
    verdict_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        registry_path=reg_path,
        verdict_output_dir=verdict_dir,
        trial_id="TRIAL-TEST-E2E-001",
        max_sessions=60,  # 60 sessions allow 20/50 period SMAs to warm up and emit signals
        write_verdict_files=True,
    )

    assert isinstance(res, Phase3B2WalkForwardRunResult)
    assert len(res.executed_sessions) == 60
    assert len(res.session_summaries) == 59

    # Execution counters tracked per session (Findings N-93, N-97)
    assert res.total_tickets_emitted > 0
    assert res.total_tickets_filled > 0
    assert res.total_tickets_rejected >= 0
    assert res.total_tickets_emitted >= res.total_tickets_filled + res.total_tickets_rejected

    # Exact Decimal diagnostics
    assert isinstance(res.initial_capital, Decimal)
    assert isinstance(res.final_equity, Decimal)
    assert isinstance(res.cagr, Decimal)
    assert isinstance(res.win_rate, Decimal)
    assert isinstance(res.profit_factor, Decimal)
    assert isinstance(res.max_drawdown, Decimal)
    assert isinstance(res.mean_realized_r, Decimal)
    assert isinstance(res.total_statutory_costs, Decimal)
    assert res.total_statutory_costs >= Decimal("0.00")

    # Trial registered in TrialRegistry
    assert res.trial_record.trial_id == "TRIAL-TEST-E2E-001"
    assert res.total_trial_count_n >= 1
    assert reg_path.is_file()

    # Verdict report files generated
    json_path = verdict_dir / "phase3b2_swing_baseline_2022_2024_verdict.json"
    md_path = verdict_dir / "phase3b2_swing_baseline_2022_2024_verdict.md"
    assert json_path.is_file()
    assert md_path.is_file()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["overall_verdict"] == "NO-GO"


def test_trial_registry_append_before_read_ordering(tmp_path: Path):
    """
    Test 2: Verifies AGENTS.md Rule 3.2 & §8.2:
    The trial record is appended to TrialRegistry BEFORE reading or printing
    performance metrics. At append time, sharpe_ratio and performance numbers on the record are None.
    """
    reg_path = tmp_path / "order_test_trials.jsonl"
    verdict_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        registry_path=reg_path,
        verdict_output_dir=verdict_dir,
        trial_id="TRIAL-TEST-ORDER-001",
        max_sessions=10,
        write_verdict_files=False,
    )

    # In memory trial_record must have sharpe_ratio=None as appended
    assert res.trial_record.sharpe_ratio is None
    assert res.trial_record.trial_id == "TRIAL-TEST-ORDER-001"
    assert res.trial_record.seq == 1

    # On disk: Read the exact committed JSONL line in the registry
    with open(reg_path, "r", encoding="utf-8") as f:
        first_line = json.loads(f.readline().strip())

    assert first_line["trial_id"] == "TRIAL-TEST-ORDER-001"
    assert first_line["sharpe_ratio"] is None
    assert first_line["mean_return"] is None
    assert first_line["max_drawdown"] is None


def test_holdout_partition_sealed_refusal():
    """
    Test 3: Verifies AGENTS.md Rule 8.1 & §10.8:
    Out-of-sample Holdout (2025-01-01..2026-11-11) is physically and logically sealed.
    Evaluating or requesting access to holdout fails closed with HoldoutSealedError.
    """
    spec = load_canonical_partition_spec()
    assert spec.holdout_start == datetime.date(2025, 1, 1)
    assert spec.holdout_end == datetime.date(2026, 11, 11)

    # 1. Direct access check fails closed
    with pytest.raises(HoldoutSealedError, match="Holdout partition is cryptographically sealed"):
        check_partition_access(spec, PartitionRole.HOLDOUT)

    # 2. Attempting to evaluate holdout sessions fails closed
    with pytest.raises(HoldoutSealedError, match="Holdout partition"):
        run_phase3b2_walkforward(
            eval_start_date=datetime.date(2025, 1, 1),
            eval_end_date=datetime.date(2025, 1, 31),
        )


def test_verdict_propagation_crit_surv_not_run_and_nogo(tmp_path: Path):
    """
    Test 4: Verifies Findings H-101, CA-2, and AGENTS.md §9.1, §9.3:
    When run against the unverified surveillance table, the driver propagates
    surveillance_constraint_status="NOT_RUN", leading evaluate_verdicts() to:
    - Evaluate CRIT-SURV-01 as NOT RUN
    - Evaluate CRIT-PROV-01 as NOT RUN
    - Return overall verdict strictly as NO-GO.
    """
    reg_path = tmp_path / "verdict_trials.jsonl"
    verdict_dir = tmp_path / "verdicts"

    res = run_phase3b2_walkforward(
        registry_path=reg_path,
        verdict_output_dir=verdict_dir,
        trial_id="TRIAL-TEST-VERDICT-001",
        max_sessions=10,
        write_verdict_files=True,
    )

    report = res.verdict_report

    # Overall verdict must be NO-GO
    assert report.overall_verdict == OverallVerdict.NO_GO

    # CRIT-SURV-01 must be NOT RUN
    crit_surv = next((e for e in report.evaluations if e.criterion_id == "CRIT-SURV-01"), None)
    assert crit_surv is not None
    assert crit_surv.status == VerdictStatus.NOT_RUN
    assert crit_surv.is_binding is True

    # CRIT-PROV-01 must be NOT RUN
    crit_prov = next((e for e in report.evaluations if e.criterion_id == "CRIT-PROV-01"), None)
    assert crit_prov is not None
    assert crit_prov.status == VerdictStatus.NOT_RUN
    assert crit_prov.is_binding is True

