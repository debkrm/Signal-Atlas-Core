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
import re
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
            ["git", "log", "-p", "-m", "-U0", f"{RULE_11_BASE_COMMIT}..HEAD", "--", str(AUDIT_FILE)],
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
    """Verifies that all scripts/verify_*.py in scripts/ exit with code 0 (Note N-20)."""
    print("--- Gate W0.5-2: Verification Scripts Exit Status (§12.3, Note N-20) ---")
    all_passed = True
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    # Note N-20: Dynamic discovery of all scripts/verify_*.py instead of hardcoded list
    discovered_scripts = sorted([
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "scripts").glob("verify_*.py")
        if p.name != "verify_audit_append_only.py"
    ])
    print(f"[INFO] Discovered {len(discovered_scripts)} verification scripts: {', '.join(discovered_scripts)}")

    for script_rel in discovered_scripts:
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
            errors="replace",
            env=env,
        )
        elapsed = time.perf_counter() - start_t

        if proc.returncode != 0:
            print(f"[FAIL] {script_rel} exited with non-zero code {proc.returncode} ({elapsed:.2f}s)")
            out = proc.stdout or ""
            err = proc.stderr or ""
            print("--- STDOUT ---")
            print(out[-500:] if len(out) > 500 else out)
            print("--- STDERR ---")
            print(err[-500:] if len(err) > 500 else err)
            all_passed = False
        else:
            print(f"[PASS] {script_rel} (exit 0, {elapsed:.2f}s)")

    if all_passed:
        print(f"[PASS] Gate W0.5-2: All {len(discovered_scripts)} verification scripts passed exit 0.\n")
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


def check_verdict_tags() -> bool:
    """
    Verifies that sign-offs and audit verdicts carry immutable git tags (§12.2, Note N-21, Note N-31, Finding N-36).
    Dynamically derives required wave sign-off tags directly from AUDIT_FILE citations (the §N at `sha`
    headings and verdicts written by the auditor), failing closed if the document is missing, empty, or unparsable.
    Validates all commit-bearing git tags against their target commits without hand-maintained lists.
    """
    print("--- Gate W0.5-4: Sign-Off and Verdict Tag Integrity (§12.2, Note N-21, Note N-31, Finding N-36) ---")
    all_ok = True

    # 1. Derive required wave tags directly from audit report citations (Finding N-36)
    if not AUDIT_FILE.is_file():
        print(f"[FAIL] Audit file missing at: {AUDIT_FILE} (Finding N-36)")
        return False

    audit_text = AUDIT_FILE.read_text(encoding="utf-8")
    if not audit_text.strip():
        print(f"[FAIL] Audit file is empty at: {AUDIT_FILE} (Finding N-36)")
        return False

    required_wave_tags: dict[str, str] = {}

    m0 = re.search(r"^##\s+29\..*?`([0-9a-f]{7,8})`", audit_text, re.MULTILINE)
    if m0:
        required_wave_tags[f"wave0-signed-off-{m0.group(1)}"] = m0.group(1)

    m1 = re.search(r"^##\s+30\..*?`([0-9a-f]{7,8})`", audit_text, re.MULTILINE)
    if m1:
        required_wave_tags[f"wave1-signed-off-{m1.group(1)}"] = m1.group(1)

    m2 = re.search(r"^##\s+33\..*?`([0-9a-f]{7,8})`", audit_text, re.MULTILINE)
    if m2:
        required_wave_tags[f"wave2-signed-off-{m2.group(1)}"] = m2.group(1)

    m3 = re.search(r"Wave\s+3.*?:\s+GO\s+at\s+`([0-9a-f]{7,8})`", audit_text)
    if m3:
        required_wave_tags[f"wave3-signed-off-{m3.group(1)}"] = m3.group(1)

    if len(required_wave_tags) < 4:
        print(
            f"[FAIL] Failed to derive all 4 required wave sign-off tags from audit report (Finding N-36). "
            f"Found {len(required_wave_tags)}/4 tags: {sorted(required_wave_tags.keys())}"
        )
        return False

    print(f"[INFO] Derived {len(required_wave_tags)} required wave sign-off tags from audit citations (Finding N-36):")
    for tag, sha in sorted(required_wave_tags.items()):
        print(f"       - {tag} (target commit: {sha})")

    # 2. Verify all required wave sign-off tags exist and match commit SHA
    for tag_name, expected_sha in sorted(required_wave_tags.items()):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--short", f"{tag_name}^{{commit}}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            actual_sha = proc.stdout.strip()
            if not actual_sha.startswith(expected_sha):
                print(f"[FAIL] Required Wave Tag '{tag_name}' points to {actual_sha}, expected {expected_sha}")
                all_ok = False
            else:
                print(f"[PASS] Required Wave Tag '{tag_name}' -> {actual_sha} (verified)")
        except Exception as e:
            print(f"[FAIL] Required Wave Tag '{tag_name}' missing or failed rev-parse: {e}")
            all_ok = False

    # 3. Dynamically discover and verify all tag names ending with commit SHA (Note N-31)
    try:
        tag_proc = subprocess.run(
            ["git", "tag", "-l"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        all_tags = [t.strip() for t in tag_proc.stdout.splitlines() if t.strip()]
        sha_pattern = re.compile(r"-([0-9a-f]{7,40})$")
        discovered_tags = {}
        for tag in all_tags:
            m = sha_pattern.search(tag)
            if m:
                discovered_tags[tag] = m.group(1)[:7]

        print(f"[INFO] Discovered {len(discovered_tags)} commit-bearing git tags to verify (Note N-31).")
        for tag_name, expected_sha in sorted(discovered_tags.items()):
            if tag_name in required_wave_tags:
                continue  # already verified above
            proc = subprocess.run(
                ["git", "rev-parse", "--short", f"{tag_name}^{{commit}}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            actual_sha = proc.stdout.strip()
            if not actual_sha.startswith(expected_sha):
                print(f"[FAIL] Tag '{tag_name}' points to {actual_sha}, expected {expected_sha}")
                all_ok = False
            else:
                print(f"[PASS] Tag '{tag_name}' -> {actual_sha} (verified)")
    except Exception as e:
        print(f"[FAIL] Failed to discover and verify git tags: {e}")
        all_ok = False

    if all_ok:
        print("[PASS] Gate W0.5-4: All sign-off and audit verdict tags verified.\n")
    else:
        print("[FAIL] Gate W0.5-4: One or more required verdict tags missing.\n")
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 0.5 Repository Foundation Gate Verification")
    parser.add_argument("--check-audit-only", action="store_true", help="Run audit append-only check only")
    parser.add_argument("--check-scripts-only", action="store_true", help="Run verification scripts only")
    parser.add_argument("--check-suite-only", action="store_true", help="Run pytest suite check only")
    parser.add_argument("--check-tags-only", action="store_true", help="Run verdict tags check only")
    args = parser.parse_args()

    print("=" * 80)
    print("SIGNAL ATLAS — WAVE 0.5 REPOSITORY FOUNDATION GATE VERIFICATION")
    print(f"Target: AGENTS.md §11.1, §12.3, §12.4 Compliance")
    print("=" * 80 + "\n")

    run_all = not (args.check_audit_only or args.check_scripts_only or args.check_suite_only or args.check_tags_only)

    results = []
    if run_all or args.check_audit_only:
        results.append(check_audit_report_append_only())

    if run_all or args.check_scripts_only:
        results.append(check_verification_scripts())

    if run_all or args.check_suite_only:
        results.append(check_test_suite_zero_skip_xfail())

    if run_all or args.check_tags_only:
        results.append(check_verdict_tags())

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

