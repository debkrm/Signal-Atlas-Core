#!/usr/bin/env python3
"""
SIGNAL ATLAS — WAVE 0.5 REPOSITORY FOUNDATION GATE VERIFICATION
Continuous verification gate enforcing AGENTS.md §11.1, §12.3, and §12.4:
  1. §11.1 & §12.3: Audit report (reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md)
     is strictly append-only (zero deleted lines in uncommitted diff and git commits since Rule 11).
  2. §12.3: Every verification script (scripts/verify_*.py) preserves exit code 0.
  3. §12.3 & §12.4: Offline test suite passes with zero skip, zero xfail, and zero failures.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_FILE = REPO_ROOT / "reports" / "audit" / "signal_atlas_phase1c_audit_deepseek_review_.md"
RULE_11_BASE_COMMIT = "a3a40f1"  # Commit ratifying Rule 11 & §37 verdict

VERIFICATION_SCRIPTS = [
    "scripts/verify_phase2a_containment_and_trials.py",
    "scripts/verify_phase2b_significance.py",
    "scripts/verify_phase2b5_storage.py",
    "scripts/verify_phase2c_walkforward.py",
    "scripts/verify_wave1_thin_slice.py",
    "scripts/verify_historical_snapshot.py",
]


def check_audit_report_append_only() -> bool:
    """Verifies that no lines have been deleted from the audit report."""
    print("--- Gate W0.5-1: Audit Report Append-Only Invariant (§11.1, §12.3) ---")

    if not AUDIT_FILE.exists():
        print(f"[FAIL] Audit file does not exist: {AUDIT_FILE}")
        return False

    line_count = len(AUDIT_FILE.read_text(encoding="utf-8").splitlines())
    if line_count == 0:
        print("[FAIL] Audit file is empty.")
        return False
    print(f"[INFO] Audit file present: {AUDIT_FILE.name} ({line_count} lines)")

    # 1. Check unstaged and staged changes vs HEAD
    try:
        diff_proc = subprocess.run(
            ["git", "diff", "-U0", "HEAD", "--", str(AUDIT_FILE)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        working_deletions = [
            line for line in diff_proc.stdout.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        if working_deletions:
            print(f"[FAIL] Working tree / staged changes contain {len(working_deletions)} deleted lines:")
            for d in working_deletions[:5]:
                print(f"       {d}")
            return False
        print("[PASS] Working tree & index diff vs HEAD: 0 deleted lines.")
    except Exception as e:
        print(f"[FAIL] Failed to inspect git diff vs HEAD: {e}")
        return False

    # 2. Check commits since Rule 11 was ratified
    try:
        log_proc = subprocess.run(
            ["git", "log", "-p", "-U0", f"{RULE_11_BASE_COMMIT}..HEAD", "--", str(AUDIT_FILE)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        commit_deletions = [
            line for line in log_proc.stdout.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        if commit_deletions:
            print(f"[FAIL] Commits since {RULE_11_BASE_COMMIT} contain {len(commit_deletions)} deleted lines:")
            for d in commit_deletions[:5]:
                print(f"       {d}")
            return False
        print(f"[PASS] Commits since {RULE_11_BASE_COMMIT}: 0 deleted lines.")
    except Exception as e:
        print(f"[FAIL] Failed to inspect git log since {RULE_11_BASE_COMMIT}: {e}")
        return False

    print("[PASS] Gate W0.5-1: Audit report append-only invariant verified 100%.\n")
    return True


def check_verification_scripts() -> bool:
    """Verifies that all registered scripts/verify_*.py exit with code 0."""
    print("--- Gate W0.5-2: Verification Scripts Exit Status (§12.3) ---")
    all_passed = True
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    for script_rel in VERIFICATION_SCRIPTS:
        script_path = REPO_ROOT / script_rel
        if not script_path.exists():
            print(f"[FAIL] Script does not exist: {script_rel}")
            all_passed = False
            continue

        start_t = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        elapsed = time.perf_counter() - start_t

        if proc.returncode != 0:
            print(f"[FAIL] {script_rel} exited with non-zero code {proc.returncode} ({elapsed:.2f}s)")
            print("--- STDOUT ---")
            print(proc.stdout[-500:] if len(proc.stdout) > 500 else proc.stdout)
            print("--- STDERR ---")
            print(proc.stderr[-500:] if len(proc.stderr) > 500 else proc.stderr)
            all_passed = False
        else:
            print(f"[PASS] {script_rel} (exit 0, {elapsed:.2f}s)")

    if all_passed:
        print(f"[PASS] Gate W0.5-2: All {len(VERIFICATION_SCRIPTS)} verification scripts passed exit 0.\n")
    else:
        print("[FAIL] Gate W0.5-2: One or more verification scripts failed.\n")
    return all_passed


def check_test_suite_zero_skip_xfail() -> bool:
    """Runs pytest -q and asserts exit 0 with zero skip, zero xfail, and zero failures (§12.4)."""
    print("--- Gate W0.5-3: Offline Test Suite with Zero Skip/Xfail (§12.3, §12.4) ---")
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    start_t = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    elapsed = time.perf_counter() - start_t

    if proc.returncode != 0:
        print(f"[FAIL] pytest exited with code {proc.returncode} ({elapsed:.2f}s)")
        print(proc.stdout[-1000:])
        print(proc.stderr[-500:])
        return False

    summary_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    print(f"[INFO] pytest summary: {summary_line} ({elapsed:.2f}s)")

    # Assert no skipped, xfailed, or failed tests
    if "failed" in summary_line.lower() and not "0 failed" in summary_line.lower():
        print(f"[FAIL] Found test failures: {summary_line}")
        return False

    if "skipped" in summary_line.lower():
        print(f"[FAIL] Found skipped tests (Rule 12.4 prohibition): {summary_line}")
        return False

    if "xfail" in summary_line.lower():
        print(f"[FAIL] Found xfailed tests (Rule 12.4 prohibition): {summary_line}")
        return False

    if "passed" not in summary_line.lower():
        print(f"[FAIL] No passed tests reported: {summary_line}")
        return False

    print("[PASS] Gate W0.5-3: Full test suite passed with 0 skipped and 0 xfailed.\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 0.5 Repository Foundation Gate Verification")
    parser.add_argument("--check-audit-only", action="store_true", help="Run audit append-only check only")
    parser.add_argument("--check-scripts-only", action="store_true", help="Run verification scripts only")
    parser.add_argument("--check-suite-only", action="store_true", help="Run pytest suite check only")
    args = parser.parse_args()

    print("=" * 80)
    print("SIGNAL ATLAS — WAVE 0.5 REPOSITORY FOUNDATION GATE VERIFICATION")
    print(f"Target: AGENTS.md §11.1, §12.3, §12.4 Compliance")
    print("=" * 80 + "\n")

    run_all = not (args.check_audit_only or args.check_scripts_only or args.check_suite_only)

    results = []
    if run_all or args.check_audit_only:
        results.append(check_audit_report_append_only())

    if run_all or args.check_scripts_only:
        results.append(check_verification_scripts())

    if run_all or args.check_suite_only:
        results.append(check_test_suite_zero_skip_xfail())

    print("=" * 80)
    if all(results):
        print("OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)")
        print("=" * 80)
        return 0
    else:
        print("OVERALL VERDICT: ONE OR MORE GATES FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())

