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
# Audit §80.3 / §80.13 item 1 (N-160): the hash is composed of the blob oids in a git tree
# (`git ls-tree`), not of raw working-copy bytes, and a row is reusable only when the tree of its
# `gate_sha` projects to the same hash. A CRLF checkout, an LF clone and the stored blob therefore
# agree, and a hash typed by hand names no tree this repository contains.
GREEN_CACHE_PATH = REPO_ROOT / "data" / "reference" / "source_tree_green.json"
SOURCE_TREE_EXCLUDED_PREFIXES = ("reports/audit/", "docs/")
SOURCE_TREE_EXCLUDED_FILES = (
    "CURRENT_STAGE_OF_WORK.md",
    "data/reference/source_tree_green.json",
)
GREEN_CACHE_MAX_AGE = datetime.timedelta(hours=24)
# §80.3 (N-160): the identity of a source tree. `git-blob-oid-v1` composes git blob oids, so it is a
# property of the commit rather than of the machine that checked it out. A row written under any other
# scheme (the 2026-11-17 working-copy sha256 rows) cannot witness a tree and is never reused.
GREEN_CACHE_SCHEME = "git-blob-oid-v1"
# Audit §79.8 (N-155): a record is evidence only if it witnesses the run it claims. The floor is a
# pinned minimum, not a default: a row reading `suite_count: 1` used to satisfy the same comparison as
# a row reading 523. The two runtime verifiers are re-executed even on a cached source tree, because
# they read the audit ledger and the Phase 2D artifacts -- prose-excluded paths that can change
# without changing the source-tree hash.
GREEN_CACHE_MIN_SUITE_COUNT = 500
GREEN_CACHE_RUNTIME_VERIFIERS = (
    "scripts/verify_audit_findings.py",
    "scripts/verify_phase2d_verdicts.py",
)

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


def canonical_volume_bytes(path: Path) -> bytes:
    """
    Volume bytes with CRLF folded to LF (Audit §79.7, §79.12 item 3, N-154).

    A frozen volume must hash the same on a Windows working copy and a Linux checkout. `git` stores the
    committed blob with LF and `reports/audit/** text eol=lf` in `.gitattributes` asks every clone to
    check it out that way, but an existing working copy can still hold CRLF (and did). Folding CRLF
    before hashing makes the pin a property of the committed text instead of the machine that wrote it.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def compute_volume_digest(path: Path) -> Tuple[str, int]:
    canonical = canonical_volume_bytes(path)
    line_count = len(canonical.decode("utf-8").splitlines())
    return hashlib.sha256(canonical).hexdigest(), line_count


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
            actual_sha, actual_lines = compute_volume_digest(path)
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
    """
    `(relative path, blob oid)` for every source file in HEAD's tree.

    The digest is composed of the object ids git stores, never of working-copy bytes, so a Windows
    checkout holding CRLF and a fresh LF clone produce the same hash (Audit §80.3, N-160). A working
    copy that differs from HEAD is not hashed at all: `dirty_source_paths()` forces the full run, so an
    uncommitted edit can never be certified by a recorded tree.
    """
    entries = source_tree_entries_for_commit("HEAD")
    if entries is None:
        raise RuntimeError("git ls-tree HEAD failed: this checkout has no committed source tree")
    return entries


def dirty_source_paths() -> List[str]:
    """
    Source paths whose working copy (staged or unstaged) differs from HEAD.

    These are the files that could change a computation without changing HEAD's tree hash, so the gate
    must run the heavy checks for them rather than reuse a record of the committed tree (N-160).
    """
    proc = subprocess.run(
        ["git", "diff-index", "--name-only", "-z", "HEAD", "--"],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff-index failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    paths = [raw.decode("utf-8") for raw in proc.stdout.split(b"\x00") if raw]
    return sorted(path for path in paths if is_source_tree_path(path))


def source_tree_entries_for_commit(ref: str) -> Optional[List[Tuple[str, str]]]:
    """
    `(relative path, blob oid)` for every source file in commit `ref`'s tree.

    This is the projection a cache row has to equal: the oids come from `git ls-tree`, so nothing is
    read from the working copy and no checkout can disagree (Audit §80.3, N-160).
    """
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "-z", ref],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    entries: List[Tuple[str, str]] = []
    for raw in proc.stdout.split(b"\x00"):
        if not raw:
            continue
        meta, _, name = raw.partition(b"\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != b"blob":
            continue
        rel = name.decode("utf-8")
        if not is_source_tree_path(rel):
            continue
        entries.append((rel, parts[2].decode("ascii")))
    return entries


def source_tree_hash_at_commit(ref: str) -> Optional[str]:
    """The source-tree hash a commit's own tree projects, or None when `ref` names no tree."""
    entries = source_tree_entries_for_commit(ref)
    if entries is None:
        return None
    return compute_source_tree_hash(entries)


def compute_source_tree_hash(entries: Sequence[Tuple[str, str]]) -> str:
    """Order-independent digest over `(path, content oid)` pairs (N-160: oids, never raw bytes)."""
    digest = hashlib.sha256()
    for rel, oid in sorted(entries):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(oid.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def discovered_verification_scripts() -> List[str]:
    """Every `scripts/verify_*.py` the gate executes, excluding the gate itself (Note N-20)."""
    return sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "scripts").glob("verify_*.py")
        if p.name != "verify_audit_append_only.py"
    )


def commit_exists(sha: str) -> bool:
    """True when `sha` names a commit in this repository (§79.8: `gate_sha` is not a free label)."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(sha or "")):
        return False
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode == 0


def green_record_problem(
    record: dict,
    expected_verifiers: Sequence[str],
    resolve_commit,
    project_tree_hash=None,
) -> Optional[str]:
    """
    Why this record cannot witness a green run, or None when it can (Audit §79.8, §80.3).

    Four independent holes are closed: an empty `verify_exits` (no verifier ran) reads as all-zero
    under `any(...)`; `suite_count` had no floor; `gate_sha` was never resolved; and the run itself was
    never required to be one the gate could have produced. §80.3 (N-160) closes the last one: the
    record's hash must be the source-tree projection of `gate_sha`'s own git tree, so a row written by
    hand names no tree that was ever run.
    """
    exits = record.get("verify_exits")
    if not isinstance(exits, dict):
        return "cache record has no verifier exit map"
    if set(map(str, exits)) != set(expected_verifiers):
        return (
            f"cache record witnesses {len(exits)} verifier(s), not the {len(expected_verifiers)} "
            f"discovered one(s)"
        )
    for script, code in exits.items():
        if isinstance(code, bool) or not isinstance(code, int) or code != 0:
            return f"cache record reports verifier {script} exiting {code!r}"
    suite_count = record.get("suite_count")
    if isinstance(suite_count, bool) or not isinstance(suite_count, int):
        return f"cache record suite_count {suite_count!r} is not an integer"
    if suite_count < GREEN_CACHE_MIN_SUITE_COUNT:
        return (
            f"cache record suite_count {suite_count} is below the pinned floor "
            f"{GREEN_CACHE_MIN_SUITE_COUNT}"
        )
    if record.get("source_tree_scheme") != GREEN_CACHE_SCHEME:
        return (
            f"cache record was not written by the {GREEN_CACHE_SCHEME} source-tree scheme, so its "
            f"hash is not the identity of a tree"
        )
    gate_sha = str(record.get("gate_sha") or "")
    if not resolve_commit(gate_sha):
        return f"cache record gate_sha {gate_sha!r} is not a commit in this repository"
    project = project_tree_hash or source_tree_hash_at_commit
    projected = project(gate_sha)
    if projected is None:
        return f"cache record gate_sha {gate_sha!r} projects no source tree"
    recorded = str(record.get("source_tree_hash") or "")
    if recorded != projected:
        return (
            f"cache record source_tree_hash {recorded[:12]}… is not the tree at gate_sha "
            f"{gate_sha}: that commit's tree projects {projected[:12]}…"
        )
    return None


def load_green_cache() -> List[dict]:
    if not GREEN_CACHE_PATH.is_file():
        return []
    data = json.loads(GREEN_CACHE_PATH.read_text(encoding="utf-8") or "[]")
    return [record for record in data if isinstance(record, dict)] if isinstance(data, list) else []


def should_record_green(
    plan: str,
    all_ok: bool,
    suite_count: int,
    dirty_paths: Sequence[str],
) -> bool:
    """
    True only for a full, all-green pass of a clean tree (Audit §80.3, N-160).

    A row names the tree of a commit, so a run over a working copy that differs from HEAD has no tree
    to name: recording it would certify code the tests never executed.
    """
    return plan == "full" and bool(all_ok) and suite_count > 0 and not dirty_paths


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
        "source_tree_scheme": GREEN_CACHE_SCHEME,
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
    verifier_scripts: Optional[Sequence[str]] = None,
    resolve_commit=None,
    project_tree_hash=None,
) -> Tuple[str, Optional[dict], str]:
    """
    Returns `(plan, record, reason)`. `plan` is "reuse" only for an identical source tree with a
    record that witnesses a complete green run, whose `gate_sha` projects to that same tree, and that
    is younger than 24 hours; anything else is "full", the fail-closed default (Audit §79.8, §80.3).
    """
    if force_full:
        return "full", None, "forced"
    expected = list(
        verifier_scripts if verifier_scripts is not None else discovered_verification_scripts()
    )
    resolver = resolve_commit or commit_exists
    for record in reversed(list(records)):
        if record.get("source_tree_hash") != source_hash:
            continue
        problem = green_record_problem(record, expected, resolver, project_tree_hash)
        if problem is not None:
            return "full", None, problem
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
    discovered_scripts = discovered_verification_scripts()
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


def check_runtime_verifiers() -> bool:
    """
    The two verifiers that read prose-excluded inputs must run even when the source tree is cached
    (Audit §79.12 item 1, N-155): `findings.jsonl`, `volume2.md` and the Phase 2D artifacts are outside
    the source-tree hash, so a cached run that skipped them could pass on a broken audit ledger.
    """
    print("--- Gate W0.5-2b: Runtime Verifiers on a Cached Source Tree (§79.8, N-155) ---")
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if "PYTHONPATH" in env else src_path
    all_passed = True
    for rel in GREEN_CACHE_RUNTIME_VERIFIERS:
        start_t = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / rel)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        elapsed = time.perf_counter() - start_t
        if proc.returncode != 0:
            print(f"[FAIL] {rel} exited {proc.returncode} ({elapsed:.2f}s)")
            print((proc.stdout or "")[-500:])
            all_passed = False
        else:
            print(f"[PASS] {rel} (exit 0, {elapsed:.2f}s)")
    if all_passed:
        print("[PASS] Gate W0.5-2b: runtime verifiers passed on the cached source tree.\n")
    else:
        print("[FAIL] Gate W0.5-2b: a runtime verifier failed on the cached source tree.\n")
    return all_passed


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
    dirty: List[str] = []
    if run_all:
        source_hash = compute_source_tree_hash(source_tree_entries())
        # §80.3 (N-160): the hash describes HEAD's tree, so a working copy that differs from HEAD is
        # never a cache hit -- there is no committed tree to witness the run. The heavy gates run, and
        # the run is not recorded: a row would claim HEAD's tree was tested when it was not.
        dirty = dirty_source_paths()
        if dirty:
            plan, record, reason = (
                "full", None, f"{len(dirty)} source path(s) differ from HEAD: {', '.join(dirty[:3])}"
            )
        else:
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
        results.append(check_runtime_verifiers())
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

    if run_all and should_record_green(plan, all(results), suite_count, dirty):
        gate_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.strip()
        # §79.8 (N-155) / §80.3 (N-160): a hash already recorded as green is not appended again, so a
        # routine full run does not dirty a tracked file. Because the hash is HEAD's tree and this run
        # was not a cache hit, the row names a tree the commit contains by construction. A record that
        # fails validation is deliberately not replaced: the forge is reported, not self-healed.
        if any(r.get("source_tree_hash") == source_hash for r in load_green_cache()):
            print(
                f"[INFO] Source tree {source_hash[:16]}… is already recorded; not appending a "
                f"duplicate row to {GREEN_CACHE_PATH.relative_to(REPO_ROOT).as_posix()}.\n"
            )
        else:
            append_green_record(
                source_hash, suite_count, pytest_seconds, verify_exits, gate_sha
            )
            print(
                f"[INFO] Recorded green source tree {source_hash[:16]}… ({suite_count} passed) "
                f"in {GREEN_CACHE_PATH.relative_to(REPO_ROOT).as_posix()}.\n"
            )
    elif run_all and all(results) and dirty:
        print(
            f"[INFO] This run tested a working copy that differs from HEAD in {len(dirty)} source "
            f"path(s), so no green row was recorded: commit and re-run the gate (N-160).\n"
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

