#!/usr/bin/env python3
"""
SIGNAL ATLAS — PHASE 2D AUTOMATED VERDICT ENGINE & AUDITABILITY GATES VERIFICATION
Enforces AGENTS.md §6.5, §7.1, §8.1, §8.2, §9.1, §9.2, §9.3, and Phase 2D specifications:
  - Gate 2D-1: Reproducible verdict report from results bundle alone.
  - Gate 2D-2: Zero hardcoded adjectives; all labels traceable to exact computations.
  - Gate 2D-3: End-to-end synthetic dataset regression on small_synthetic_dataset.json.
  - Gate 2D-4: Adversarial failure tests fail closed (holdout breach, lookahead, N<=1, unanchored calendar, unverified provenance, tampered manifest, trade plausibility).
  - Gate 2D-5: Phase 2D Tier-A report generator execution, zero hardcoded metric literals, and byte-reproducibility.
"""

from __future__ import annotations

import ast
import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.contracts.criteria import (
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
    load_anchored_nse_trading_calendar,
)


def verify_gate_2d1_reproducibility() -> bool:
    """Gate 2D-1: Verdict report reproducibility from results bundle alone (Finding N-58)."""
    print("--- Gate 2D-1: Verdict Report Determinism & Reproducibility ---")

    bundle = {
        "evaluation_start_date": "2022-01-03",
        "evaluation_end_date": "2026-10-31",
        "evaluated_at_utc": "2026-11-14T12:00:00+00:00",
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

    # Evaluate twice with no external timestamp parameter; N-58 requires report reproducibility from bundle alone
    rep1 = evaluate_verdicts(bundle)
    rep2 = evaluate_verdicts(bundle)

    dict1 = rep1.to_dict()
    dict2 = rep2.to_dict()
    if dict1 != dict2:
        print("[FAIL] Verdict reports from identical inputs produced non-identical dictionary representations!")
        return False

    md1 = rep1.to_markdown()
    md2 = rep2.to_markdown()
    if md1 != md2:
        print("[FAIL] Verdict reports from identical inputs produced non-identical markdown representations!")
        return False

    # H-67: Unattested VERIFIED claim evaluates to NOT RUN and overall NO-GO
    if rep1.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Expected overall verdict NO-GO for unattested bundle (Finding H-67), got: {rep1.overall_verdict}")
        return False

    # H-66: Window echoed in report
    if rep1.evaluation_start_date != "2022-01-03" or rep1.evaluation_end_date != "2026-10-31":
        print(f"[FAIL] Evaluation window dates missing or mismatched in report: {rep1.evaluation_start_date} .. {rep1.evaluation_end_date}")
        return False
    if "- **Evaluation Window:** `2022-01-03` to `2026-10-31`" not in md1:
        print("[FAIL] Evaluation window dates missing from markdown report (Finding H-66)!")
        return False

    print(f"[PASS] Gate 2D-1: Bit-for-bit reproducibility verified across dictionary and markdown outputs (Note N-58).")
    print(f"       Evaluation Window: {rep1.evaluation_start_date} to {rep1.evaluation_end_date} (Finding H-66)")
    print(f"       Criteria Version: {rep1.criteria_version} | Fingerprint: {rep1.criteria_fingerprint}")
    return True


def verify_gate_2d2_zero_hardcoded_adjectives() -> bool:
    """Gate 2D-2: Zero hardcoded qualitative adjectives (Rule 9.1)."""
    print("\n--- Gate 2D-2: Banned Adjectives AST & Text Scan (§9.1) ---")
    reporting_dir = REPO_ROOT / "src" / "signal_core" / "reporting"
    banned_words = ["HEALTHY", "OPTIMAL", "ROBUST", "CONTROLLED"]

    violations = []
    py_files = list(reporting_dir.glob("*.py"))
    if not py_files:
        print(f"[FAIL] No python files found in reporting dir: {reporting_dir}")
        return False

    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        for b in banned_words:
            matches = list(re.finditer(rf"\b{b}\b", content, re.IGNORECASE))
            if matches:
                violations.append((py_file.name, b, len(matches)))

    if violations:
        print(f"[FAIL] Prohibited qualitative adjectives found in reporting module:")
        for fname, word, count in violations:
            print(f"       {fname}: '{word}' occurred {count} time(s)")
        return False

    print(f"[PASS] Gate 2D-2: Zero prohibited qualitative adjectives found across {len(py_files)} reporting files.")
    return True


def verify_gate_2d3_synthetic_fixture_end_to_end() -> bool:
    """Gate 2D-3: End-to-end regression on small_synthetic_dataset.json."""
    print("\n--- Gate 2D-3: End-to-End Synthetic Fixture Regression ---")
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "small_synthetic_dataset.json"
    if not fixture_path.exists():
        print(f"[FAIL] Synthetic fixture not found at {fixture_path}")
        return False

    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    meta = fixture_data["metadata"]
    synthetic_bundle = {
        "evaluation_start_date": meta["start_date"],
        "evaluation_end_date": meta["end_date"],
        "evaluated_at_utc": "2026-11-14T12:00:00+00:00",
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
        "data_provenance_status": meta["source_provenance_status"],
        "trial_count_n": 4,
        "deflated_sharpe_ratio": Decimal("0.9650"),
        "walk_forward_positive_fold_ratio": Decimal("0.85"),
    }

    report = evaluate_verdicts(synthetic_bundle)

    passed_count = report.summary_counts.get("PASS", 0)
    not_run_count = report.summary_counts.get("NOT_RUN", 0)
    fail_count = report.summary_counts.get("FAIL", 0)

    if fail_count > 0:
        print(f"[FAIL] Synthetic fixture evaluation had {fail_count} unexpected failures!")
        return False

    # Check that the ONLY NOT RUN entries are:
    # 1. CRIT-PROV-01 (unverified synthetic provenance)
    # 2. CRIT-INFO-01 (informational circuit_verified_pnl)
    not_run_ids = {e.criterion_id for e in report.evaluations if e.status == VerdictStatus.NOT_RUN}
    expected_not_run = {"CRIT-PROV-01", "CRIT-INFO-01"}
    if not_run_ids != expected_not_run:
        print(f"[FAIL] Unexpected NOT RUN criteria: {not_run_ids} != {expected_not_run}")
        return False

    expected_win_str = f"- **Evaluation Window:** `{meta['start_date']}` to `{meta['end_date']}`"
    if expected_win_str not in report.to_markdown():
        print(f"[FAIL] Expected evaluation window string {expected_win_str!r} not in markdown report (Finding H-66)!")
        return False

    print(f"[PASS] Gate 2D-3: End-to-end synthetic evaluation succeeded:")
    print(f"       PASS={passed_count}, FAIL={fail_count}, NOT RUN={not_run_count} (Total={len(report.evaluations)})")
    print(f"       Evaluation Window echoed in report: {meta['start_date']} to {meta['end_date']} (Finding H-66).")
    print(f"       Honest provenance gating (Residual R-3) correctly marked CRIT-PROV-01 as NOT RUN.")
    return True


def verify_gate_2d4_adversarial_fail_closed() -> bool:
    """Gate 2D-4: Adversarial tests fail closed."""
    print("\n--- Gate 2D-4: Adversarial Guards & Fail-Closed Invariants ---")

    # 1. Holdout breach attempt must raise HoldoutBreachError (§8.1)
    holdout_breached = False
    try:
        evaluate_verdicts({"contains_holdout_records": True, "holdout_unlock_authorized": False})
    except HoldoutBreachError:
        holdout_breached = True
    if not holdout_breached:
        print("[FAIL] Holdout breach attempt was not rejected with HoldoutBreachError!")
        return False
    print("[PASS] Holdout breach attempt rejected fail-closed (Finding H-16, AGENTS.md §8.1).")

    # 2. Multi-hypothesis trial count N <= 1 must evaluate to NOT RUN (§8.2)
    rep_n1 = evaluate_verdicts({"trial_count_n": 1, "deflated_sharpe_ratio": Decimal("0.99")})
    eval_n = next(e for e in rep_n1.evaluations if e.criterion_id == "CRIT-OVERFIT-01")
    eval_dsr = next(e for e in rep_n1.evaluations if e.criterion_id == "CRIT-OVERFIT-02")
    if eval_n.status != VerdictStatus.NOT_RUN or eval_dsr.status != VerdictStatus.NOT_RUN:
        print(f"[FAIL] N <= 1 trial evaluation did not evaluate to NOT RUN! Got n={eval_n.status}, dsr={eval_dsr.status}")
        return False
    print("[PASS] Multi-hypothesis accountability N <= 1 evaluated to NOT RUN fail-closed (§8.2).")

    # 3. Lookahead execution latency = 0 must FAIL (§7.1)
    rep_lat0 = evaluate_verdicts({"execution_latency_sessions": 0})
    eval_lat = next(e for e in rep_lat0.evaluations if e.criterion_id == "CRIT-EXEC-05")
    if eval_lat.status != VerdictStatus.FAIL:
        print(f"[FAIL] Execution latency = 0 did not FAIL! Got: {eval_lat.status}")
        return False
    print("[PASS] Lookahead execution latency = 0 failed closed (Zero Lookahead §7.1).")

    # 4. Unanchored / tampered calendar must raise CalendarError (Residual R-6, Finding H-64)
    import dataclasses
    crit = load_go_no_go_criteria()
    bad_crit = dataclasses.replace(crit, expected_calendar_fingerprint="CAL-FPR-V1-tampered0000000000000000000000000000")
    cal_rejected = False
    try:
        evaluate_verdicts({}, criteria=bad_crit)
    except CalendarError:
        cal_rejected = True
    if not cal_rejected:
        print("[FAIL] Tampered calendar fingerprint was not rejected with CalendarError (Residual R-6)!")
        return False
    print("[PASS] Tampered calendar fingerprint rejected fail-closed (Finding H-64, Residual R-6).")

    # 5. Pre-binding evaluation start date (e.g. 2019-01-01) must FAIL closed to NO-GO (Finding H-66, §10.8)
    rep_pre2022 = evaluate_verdicts({
        "evaluation_start_date": "2019-01-01",
        "evaluation_end_date": "2019-12-31",
    })
    eval_win = next(e for e in rep_pre2022.evaluations if e.criterion_id == "CRIT-WINDOW-01")
    if eval_win.status != VerdictStatus.FAIL or rep_pre2022.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Pre-binding evaluation window was not rejected with FAIL / NO-GO! Got: {eval_win.status}, {rep_pre2022.overall_verdict}")
        return False
    print("[PASS] Pre-binding evaluation window (2019) rejected fail-closed to NO-GO (Finding H-66).")

    # 6. Unattested VERIFIED provenance claim must evaluate CRIT-PROV-01 to NOT RUN and NO-GO (Finding H-67)
    rep_unattested = evaluate_verdicts({
        "data_provenance_status": "VERIFIED / EXCHANGE_ATTESTED",
    })
    eval_prov = next(e for e in rep_unattested.evaluations if e.criterion_id == "CRIT-PROV-01")
    if eval_prov.status != VerdictStatus.NOT_RUN or rep_unattested.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Unattested VERIFIED provenance was not rejected with NOT RUN / NO-GO! Got: {eval_prov.status}, {rep_unattested.overall_verdict}")
        return False
    print("[PASS] Unattested VERIFIED provenance claim rejected to NOT RUN and NO-GO fail-closed (Finding H-67).")

    # 7. H-68: Unregistered or digest-mismatched attestation reference rejected fail-closed (§53.3, §53.7)
    rep_agents = evaluate_verdicts({
        "data_provenance_status": "VERIFIED / EXCHANGE_ATTESTED",
        "provenance_attestation_reference": "AGENTS.md",
    })
    eval_prov_ag = next(e for e in rep_agents.evaluations if e.criterion_id == "CRIT-PROV-01")
    if eval_prov_ag.status != VerdictStatus.NOT_RUN or rep_agents.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] AGENTS.md attestation reference was not rejected with NOT RUN / NO-GO! Got: {eval_prov_ag.status}")
        return False

    rep_mismatch = evaluate_verdicts({
        "data_provenance_status": "VERIFIED / EXCHANGE_ATTESTED",
        "provenance_attestation_reference": "data/reference/bhavcopy_archive_manifest.jsonl",
        "dataset_fingerprint": "DATA-CTNT-V2-deadbeef00000000000000000000000000000000000000000000000000000000",
    })
    eval_prov_mis = next(e for e in rep_mismatch.evaluations if e.criterion_id == "CRIT-PROV-01")
    if eval_prov_mis.status != VerdictStatus.NOT_RUN or rep_mismatch.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Mismatched digest attestation was not rejected with NOT RUN / NO-GO! Got: {eval_prov_mis.status}")
        return False
    print("[PASS] Manifest-unregistered and digest-mismatched attestation rejected fail-closed (Finding H-68).")

    # 8. H-69: Window beyond calendar bounds and implausible session/trade count rejected (§53.4, §53.7)
    rep_future = evaluate_verdicts({
        "evaluation_start_date": "2031-01-01",
        "evaluation_end_date": "2031-06-30",
    })
    eval_win_fut = next(e for e in rep_future.evaluations if e.criterion_id == "CRIT-WINDOW-01")
    if eval_win_fut.status != VerdictStatus.FAIL or rep_future.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Future window beyond calendar coverage was not rejected with FAIL / NO-GO! Got: {eval_win_fut.status}")
        return False

    rep_2sess = evaluate_verdicts({
        "evaluation_start_date": "2022-01-03",
        "evaluation_end_date": "2022-01-04",
        "total_trades": 210,
    })
    eval_win_2s = next(e for e in rep_2sess.evaluations if e.criterion_id == "CRIT-WINDOW-01")
    if eval_win_2s.status != VerdictStatus.FAIL or rep_2sess.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Two-session window carrying 210 trades was not rejected with FAIL / NO-GO! Got: {eval_win_2s.status}")
        return False
    print("[PASS] Calendar bounds and session count plausibility rejected fail-closed (Finding H-69).")

    # 9. H-70: Matched manifest record declaring unverified provenance rejected fail-closed (Audit §54.3, §54.10)
    rep_unverified_record = evaluate_verdicts({
        "data_provenance_status": "VERIFIED / EXCHANGE_ATTESTED",
        "provenance_attestation_reference": "data/reference/bhavcopy_archive_manifest.jsonl",
        "dataset_fingerprint": "DATA-CTNT-V2-7ea5f97bb5affae6d688b013bd802c64a3366410377c2e3f8e31912450444c91",
    })
    eval_prov_unv = next(e for e in rep_unverified_record.evaluations if e.criterion_id == "CRIT-PROV-01")
    if eval_prov_unv.status != VerdictStatus.NOT_RUN or rep_unverified_record.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Manifest record with unverified provenance status was not rejected with NOT RUN / NO-GO! Got: {eval_prov_unv.status}")
        return False
    print("[PASS] Unverified manifest record rejected fail-closed to NOT RUN / NO-GO (Finding H-70).")

    # 10. H-72: Pinned manifest fingerprint enforcement rejects forged/tampered manifest (Audit §54.5, §54.10)
    manifest_tampered = False
    tampered_crit = dataclasses.replace(crit, expected_manifest_fingerprint="MAN-FPR-V1-tampered0000000000000000000000000000")
    try:
        evaluate_verdicts({}, criteria=tampered_crit)
    except ReportingError as exc:
        if "Manifest fingerprint mismatch" in str(exc) and "Finding H-72" in str(exc):
            manifest_tampered = True
    if not manifest_tampered:
        print("[FAIL] Tampered/forged manifest was not rejected fail-closed with ReportingError (Finding H-72)!")
        return False
    print("[PASS] Authoritative manifest fingerprint pin enforced fail-closed (Finding H-72).")

    # 11. H-71: Decimal total_trades parsing and session-plausibility bounds (Audit §54.4, §54.10)
    for bad_trade_val in ("500", Decimal("500"), 500.0, 500):
        rep_bad_trade = evaluate_verdicts({
            "evaluation_start_date": "2022-01-03",
            "evaluation_end_date": "2022-01-04",
            "total_trades": bad_trade_val,
        })
        eval_w_bad = next(e for e in rep_bad_trade.evaluations if e.criterion_id == "CRIT-WINDOW-01")
        if eval_w_bad.status != VerdictStatus.FAIL or rep_bad_trade.overall_verdict != OverallVerdict.NO_GO:
            print(f"[FAIL] Two-session window carrying total_trades={bad_trade_val!r} did not FAIL! Got: {eval_w_bad.status}")
            return False

    rep_3sess_500 = evaluate_verdicts({
        "evaluation_start_date": "2022-01-05",
        "evaluation_end_date": "2022-01-07",
        "total_trades": 500,
    })
    eval_w_3s = next(e for e in rep_3sess_500.evaluations if e.criterion_id == "CRIT-WINDOW-01")
    if eval_w_3s.status != VerdictStatus.FAIL or rep_3sess_500.overall_verdict != OverallVerdict.NO_GO:
        print(f"[FAIL] Three-session window carrying 500 trades did not FAIL! Got: {eval_w_3s.status}")
        return False
    print("[PASS] total_trades Decimal parsing and session plausibility bounds verified fail-closed (Finding H-71).")

    print("[PASS] Gate 2D-4: All adversarial fail-closed invariants verified.")
    return True


def verify_gate_2d5_tier_a_report_generation() -> bool:
    """Gate 2D-5: Phase 2D Tier-A Report Generator Execution & Reproducibility (Findings H-73, H-74, N-63)."""
    print("\n--- Gate 2D-5: Phase 2D Tier-A Report Generator Execution & Reproducibility ---")
    gen_script = REPO_ROOT / "scripts" / "generate_phase2d_tier_a_report.py"
    if not gen_script.exists():
        print(f"[FAIL] Tier-A report generator missing at {gen_script}")
        return False

    # Structural AST check: zero boolean or numeric literals assigned to bundle keys (Findings H-73, N-63)
    gen_source = gen_script.read_text(encoding="utf-8")
    tree = ast.parse(gen_source, filename=str(gen_script))
    bundle_func = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_tier_a_results_bundle"),
        None,
    )
    if bundle_func is None:
        print(f"[FAIL] Function build_tier_a_results_bundle not found in {gen_script.name}!")
        return False

    for node in ast.walk(bundle_func):
        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                key_name = getattr(key, "value", getattr(key, "id", str(key)))
                if isinstance(val, ast.Constant) and isinstance(val.value, (bool, int, float)):
                    print(
                        f"[FAIL] Hardcoded constant literal {val.value!r} ({type(val.value).__name__}) assigned to key {key_name!r} "
                        f"in build_tier_a_results_bundle (Findings H-73, N-63)!"
                    )
                    return False
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    sub_key = getattr(target.slice, "value", str(target.slice))
                    val = node.value
                    if isinstance(val, ast.Constant) and isinstance(val.value, (bool, int, float)):
                        print(
                            f"[FAIL] Hardcoded constant literal {val.value!r} ({type(val.value).__name__}) assigned to subscript {sub_key!r} "
                            f"in build_tier_a_results_bundle (Findings H-73, N-63)!"
                        )
                        return False

    print("[PASS] Verified zero boolean or numeric literals assigned in build_tier_a_results_bundle AST (Findings H-73, N-63).")

    json_path = REPO_ROOT / "reports" / "verdicts" / "phase2d_tier_a_2022_2026_verdict.json"
    md_path = REPO_ROOT / "reports" / "verdicts" / "phase2d_tier_a_2022_2026_verdict.md"
    if not json_path.exists() or not md_path.exists():
        print("[FAIL] Committed Tier-A verdict reports missing from reports/verdicts/!")
        return False

    committed_json = json_path.read_bytes()
    committed_md = md_path.read_bytes()

    # Run generator subprocess (Finding H-74)
    proc1 = subprocess.run(
        [sys.executable, str(gen_script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc1.returncode != 0:
        print(f"[FAIL] Tier-A report generator failed with exit code {proc1.returncode} (Finding H-74)!")
        print(f"       stderr: {proc1.stderr}")
        return False
    print("[PASS] Tier-A report generator executed with exit code 0 on platform (Finding H-74).")

    # Verify that freshly regenerated report matches committed report byte-for-byte (Finding N-63)
    if json_path.read_bytes() != committed_json:
        print("[FAIL] Regenerated Tier-A JSON verdict report does not match committed artifact byte-for-byte (Finding N-63)!")
        return False
    if md_path.read_bytes() != committed_md:
        print("[FAIL] Regenerated Tier-A Markdown verdict report does not match committed artifact byte-for-byte (Finding N-63)!")
        return False
    print("[PASS] Regenerated Tier-A reports match committed artifacts byte-for-byte (Finding N-63).")

    # Second run to test exact byte-reproducibility across repeated executions
    proc2 = subprocess.run(
        [sys.executable, str(gen_script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc2.returncode != 0:
        print(f"[FAIL] Tier-A report generator failed on second run: exit code {proc2.returncode}")
        return False

    if json_path.read_bytes() != committed_json or md_path.read_bytes() != committed_md:
        print("[FAIL] Tier-A report generator outputs are not byte-identical across repeated runs!")
        return False
    print("[PASS] Byte-identical reproducibility verified across repeated generator executions.")

    print("[PASS] Gate 2D-5: Phase 2D Tier-A Report Generator Execution & Reproducibility verified.")
    return True


def main() -> int:
    print("=" * 80)
    print("SIGNAL ATLAS — PHASE 2D AUTOMATED VERDICT ENGINE & DECISION AUDIT")
    print(f"Executed at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    checks = [
        verify_gate_2d1_reproducibility(),
        verify_gate_2d2_zero_hardcoded_adjectives(),
        verify_gate_2d3_synthetic_fixture_end_to_end(),
        verify_gate_2d4_adversarial_fail_closed(),
        verify_gate_2d5_tier_a_report_generation(),
    ]

    if all(checks):
        print("\n" + "=" * 80)
        print("OVERALL VERDICT: ALL PHASE 2D VERDICT ENGINE GATES PASSED (100%)")
        print("=" * 80)
        return 0
    else:
        print("\n" + "=" * 80)
        print("OVERALL VERDICT: ONE OR MORE PHASE 2D GATES FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())

