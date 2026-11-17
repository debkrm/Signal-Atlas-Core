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
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_FILE = REPO_ROOT / "reports" / "audit" / "signal_atlas_phase1c_audit_deepseek_review_.md"
RULE_11_BASE_COMMIT = "a3a40f1"  # Commit ratifying Rule 11 & §37 verdict
AUDIT_VOLUMES_CONFIG = REPO_ROOT / "configs" / "audit_volumes.yaml"
AUDIT_FINDINGS_LEDGER = REPO_ROOT / "reports" / "audit" / "findings.jsonl"

# §78.15 (b): the source-tree green cache. A commit that touches only audit prose, docs or the work
# log cannot change a computation, so the gate reuses the recorded result for an identical source
# tree instead of re-running 500 tests. Any path outside the excluded set produces an unknown hash and
# forces the full run; --force-full exists for the human, and a full run is mandatory once a day.
GREEN_CACHE_PATH = REPO_ROOT / "data" / "reference" / "source_tree_green.json"
SOURCE_TREE_EXCLUDED_PREFIXES = ("reports/audit/", "docs/")
SOURCE_TREE_EXCLUDED_FILES = (
    "CURRENT_STAGE_OF_WORK.md",
    "data/reference/source_tree_green.json",
)
GREEN_CACHE_MAX_AGE = datetime.timedelta(hours=24)

VERIFICATION_SCRIPTS = [
    "scripts/verify_phase2a_containment_and_trials.py",
    "scripts/verify_phase2b_significance.py",
    "scripts/verify_phase2b5_storage.py",
    "scripts/verify_phase2c_walkforward.py",
    "scripts/verify_phase2d_verdicts.py",
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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_audit_volumes() -> List[dict]:
    with open(AUDIT_VOLUMES_CONFIG, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    volumes = data.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        raise ValueError(f"audit_volumes.yaml has no 'volumes' list: {AUDIT_VOLUMES_CONFIG}")
    return volumes


def check_audit_volume_integrity() -> bool:
    """
    Frozen volumes must hash exactly (stronger than "no removed line"); active volumes keep the
    append-only prefix check (Audit §78.15 (a)).
    """
    print("--- Gate W0.5-1b: Audit Volume Registry (§78.13, §78.15 (a)) ---")
    try:
        volumes = load_audit_volumes()
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        print(f"[FAIL] Audit volume registry unreadable: {exc}\n")
        return False

    all_ok = True
    for volume in volumes:
        rel = str(volume.get("path", ""))
        path = REPO_ROOT / rel
        frozen = bool(volume.get("frozen"))
        if not path.is_file():
            if frozen:
                print(f"[FAIL] Frozen volume missing: {rel}")
                all_ok = False
            else:
                print(f"[INFO] Active volume {rel} is registered and not created yet.")
            continue

        if frozen:
            expected_sha = str(volume.get("sha256", ""))
            expected_lines = volume.get("line_count")
            actual_sha = sha256_file(path)
            actual_lines = len(path.read_text(encoding="utf-8").splitlines())
            if actual_sha != expected_sha:
                print(
                    f"[FAIL] Frozen volume {rel} sha256 {actual_sha[:16]}… != pinned "
                    f"{expected_sha[:16]}… — a frozen volume is byte-identical or the pin is wrong"
                )
                all_ok = False
            elif expected_lines is not None and actual_lines != int(expected_lines):
                print(
                    f"[FAIL] Frozen volume {rel} has {actual_lines} line(s), pinned {expected_lines}"
                )
                all_ok = False
            else:
                print(
                    f"[PASS] Frozen volume {rel}: sha256 and {actual_lines} line(s) match the pin "
                    f"({volume.get('sections', '?')})."
                )
            continue

        # Active volume: only appends may land, so HEAD's content must be a prefix of the working file.
        try:
            head_proc = subprocess.run(
                ["git", "show", f"HEAD:{rel}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except subprocess.CalledProcessError:
            print(f"[INFO] Active volume {rel} is not yet committed; nothing to compare.")
            continue
        head_text = head_proc.stdout
        working_text = path.read_text(encoding="utf-8")
        if not working_text.startswith(head_text):
            print(f"[FAIL] Active volume {rel} is not an append-only extension of HEAD")
            all_ok = False
        else:
            print(
                f"[PASS] Active volume {rel}: HEAD content is an unchanged prefix "
                f"({len(head_text.splitlines())} committed line(s), {len(working_text.splitlines())} now)."
            )

    if all_ok:
        print(f"[PASS] Gate W0.5-1b: {len(volumes)} audit volume(s) verified.\n")
    else:
        print("[FAIL] Gate W0.5-1b: audit volume registry violated.\n")
    return all_ok


def check_audit_index() -> bool:
    """The committed INDEX.md must be the generator's exact output (never hand-edited)."""
    print("--- Gate W0.5-1c: Audit Index Reproducibility (§78.15 (a)) ---")
    proc = subprocess.run(
        [sys.executable, "scripts/generate_audit_index.py", "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        print((proc.stdout or "").strip())
        print("[FAIL] Gate W0.5-1c: audit index is stale.\n")
        return False
    print((proc.stdout or "").strip())
    print("[PASS] Gate W0.5-1c: audit index reproduces.\n")
    return True


def is_source_tree_path(rel_path: str) -> bool:
    """True when a tracked path can change a computation (audit prose, docs and the log cannot)."""
    if rel_path in SOURCE_TREE_EXCLUDED_FILES:
        return False
    return not any(rel_path.startswith(prefix) for prefix in SOURCE_TREE_EXCLUDED_PREFIXES)


def source_tree_entries() -> List[Tuple[str, str]]:
    """`(relative path, sha256 of bytes)` for every tracked source file."""
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=True,
    )
    entries: List[Tuple[str, str]] = []
    for raw in proc.stdout.split(b"\x00"):
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if not is_source_tree_path(rel):
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        entries.append((rel, sha256_file(path)))
    return entries


def compute_source_tree_hash(entries: Sequence[Tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for rel, file_sha in sorted(entries):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(file_sha.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_green_cache() -> List[dict]:
    if not GREEN_CACHE_PATH.is_file():
        return []
    data = json.loads(GREEN_CACHE_PATH.read_text(encoding="utf-8") or "[]")
    return [record for record in data if isinstance(record, dict)] if isinstance(data, list) else []


def append_green_record(
    source_hash: str,
    suite_count: int,
    pytest_seconds: float,
    verify_exits: Dict[str, int],
    gate_sha: str,
) -> None:
    """Appends one record. Existing rows are never rewritten: the cache is history, not state."""
    records = load_green_cache()
    records.append({
        "source_tree_hash": source_hash,
        "suite_count": int(suite_count),
        "pytest_seconds": round(float(pytest_seconds), 2),
        "verify_exits": verify_exits,
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gate_sha": gate_sha,
    })
    GREEN_CACHE_PATH.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8", newline="\n")


def select_gate_plan(
    source_hash: str,
    records: Sequence[dict],
    now: datetime.datetime,
    force_full: bool = False,
) -> Tuple[str, Optional[dict], str]:
    """
    Returns `(plan, record, reason)`. `plan` is "reuse" only for an identical source tree with a
    green record younger than 24 hours; anything else is "full", which is the fail-closed default.
    """
    if force_full:
        return "full", None, "forced"
    for record in reversed(list(records)):
        if record.get("source_tree_hash") != source_hash:
            continue
        exits = record.get("verify_exits") or {}
        if any(int(code) != 0 for code in exits.values()):
            continue
        try:
            recorded_at = datetime.datetime.fromisoformat(str(record.get("utc")))
        except ValueError:
            return "full", None, "cache record has an unreadable timestamp"
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=datetime.timezone.utc)
        if now - recorded_at > GREEN_CACHE_MAX_AGE:
            return "full", None, "cache record is older than 24h"
        return "reuse", record, "source tree unchanged since a green run"
    return "full", None, "unknown source-tree hash"


def check_verification_scripts() -> Tuple[bool, Dict[str, int]]:
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
    exits: Dict[str, int] = {}

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

        exits[script_rel] = proc.returncode
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
    return all_passed, exits


def check_test_suite_zero_skip_xfail() -> Tuple[bool, int, float]:
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
        print((proc.stdout or "")[-1000:])
        print((proc.stderr or "")[-500:])
        return False, 0, elapsed

    summary_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    print(f"[INFO] pytest summary: {summary_line} ({elapsed:.2f}s)")

    # Assert no skipped, xfailed, or failed tests
    if "failed" in summary_line.lower() and not "0 failed" in summary_line.lower():
        print(f"[FAIL] Found test failures: {summary_line}")
        return False, 0, elapsed

    if "skipped" in summary_line.lower():
        print(f"[FAIL] Found skipped tests (Rule 12.4 prohibition): {summary_line}")
        return False, 0, elapsed

    if "xfail" in summary_line.lower():
        print(f"[FAIL] Found xfailed tests (Rule 12.4 prohibition): {summary_line}")
        return False, 0, elapsed

    if "passed" not in summary_line.lower():
        print(f"[FAIL] No passed tests reported: {summary_line}")
        return False, 0, elapsed

    passed_match = re.search(r"(\d+) passed", summary_line)
    passed_count = int(passed_match.group(1)) if passed_match else 0
    print("[PASS] Gate W0.5-3: Full test suite passed with 0 skipped and 0 xfailed.\n")
    return True, passed_count, elapsed


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


def check_reference_manifest_integrity() -> bool:
    """Recomputes every current manifest row's byte_count/sha256 against the corpus (Finding H-118)."""
    print("--- Gate W0.5-5: Reference Manifest Per-Artifact Digest Verification (§10.5) ---")
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from signal_core.storage.reference_integrity import (
        ManifestIntegrityError,
        verify_manifest_artifacts,
    )

    try:
        summary = verify_manifest_artifacts()
    except ManifestIntegrityError as exc:
        print(f"[FAIL] Reference manifest attestation does not match the committed corpus: {exc}\n")
        return False

    print(
        f"[PASS] Gate W0.5-5: {summary['verified']} current artifact(s) match their manifest "
        f"byte_count and sha256; {summary['superseded']} superseded row(s) skipped as history.\n"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 0.5 Repository Foundation Gate Verification")
    parser.add_argument("--check-audit-only", action="store_true", help="Run audit append-only check only")
    parser.add_argument("--check-scripts-only", action="store_true", help="Run verification scripts only")
    parser.add_argument("--check-suite-only", action="store_true", help="Run pytest suite check only")
    parser.add_argument("--check-tags-only", action="store_true", help="Run verdict tags check only")
    parser.add_argument("--check-reference-only", action="store_true", help="Run reference manifest integrity check only")
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Ignore the source-tree green cache and re-run the full suite (§78.15 (b))",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("SIGNAL ATLAS — WAVE 0.5 REPOSITORY FOUNDATION GATE VERIFICATION")
    print(f"Target: AGENTS.md §11.1, §12.3, §12.4 Compliance")
    print("=" * 80 + "\n")

    run_all = not (args.check_audit_only or args.check_scripts_only or args.check_suite_only or args.check_tags_only or args.check_reference_only)

    results = []
    if run_all or args.check_audit_only:
        results.append(check_audit_report_append_only())
        results.append(check_audit_volume_integrity())
        results.append(check_audit_index())

    # §78.15 (b): heavy gates run only when the source tree differs from a recorded green run.
    plan, record, reason = "full", None, "targeted run"
    source_hash = ""
    if run_all:
        source_hash = compute_source_tree_hash(source_tree_entries())
        plan, record, reason = select_gate_plan(
            source_hash, load_green_cache(), datetime.datetime.now(datetime.timezone.utc),
            force_full=args.force_full,
        )
        print(f"[INFO] Source-tree hash {source_hash[:16]}… — {reason}")

    suite_count = 0
    pytest_seconds = 0.0
    verify_exits: Dict[str, int] = {}
    if plan == "reuse" and record is not None:
        print(
            f"[INFO] reused green at {record.get('gate_sha')} ({record.get('suite_count')} passed, "
            f"recorded {record.get('utc')}) — heavy gates skipped for an identical source tree.\n"
        )
    else:
        if run_all or args.check_scripts_only:
            scripts_ok, verify_exits = check_verification_scripts()
            results.append(scripts_ok)

        if run_all or args.check_suite_only:
            suite_ok, suite_count, pytest_seconds = check_test_suite_zero_skip_xfail()
            results.append(suite_ok)

    if run_all or args.check_tags_only:
        results.append(check_verdict_tags())

    if run_all or args.check_reference_only:
        results.append(check_reference_manifest_integrity())

    if run_all and plan == "full" and all(results) and suite_count > 0:
        gate_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.strip()
        append_green_record(
            source_hash, suite_count, pytest_seconds, verify_exits, gate_sha
        )
        print(
            f"[INFO] Recorded green source tree {source_hash[:16]}… ({suite_count} passed) "
            f"in {GREEN_CACHE_PATH.relative_to(REPO_ROOT).as_posix()}.\n"
        )

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

