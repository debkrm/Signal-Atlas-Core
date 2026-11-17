"""
Unit tests for the Audit §80 remediation (`reports/audit/volume2.md` §80, reviewing `96d24a1`).

Target invariants (criteria 1.1.9, no threshold moved):
- N-160: the source-tree green cache hashes the object ids git stores rather than the bytes of one
  checkout, and a row is reusable only when the tree of its `gate_sha` projects to the recorded hash.
- N-161: `CRIT-OVERFIT-06` requires an integer validation-fold count; a numeric string is not one.
"""

from __future__ import annotations

import datetime
import subprocess
from decimal import Decimal
from pathlib import Path

import scripts.verify_audit_append_only as gate
from signal_core.reporting.verdicts import evaluate_verdicts

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, check=True
    ).stdout


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": "2026-11-17T12:00:00+00:00"}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


def _green_record(tree_hash: str, gate_sha: str) -> dict:
    return {
        "source_tree_hash": tree_hash,
        "source_tree_scheme": gate.GREEN_CACHE_SCHEME,
        "suite_count": 529,
        "verify_exits": {script: 0 for script in gate.discovered_verification_scripts()},
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gate_sha": gate_sha,
    }


# --- N-160: the cache binds to a git tree, not to a directory ----------------------------------


def test_n160_source_tree_hash_is_the_object_id_git_stores():
    head = _git("rev-parse", "HEAD").decode().strip()
    entries = dict(gate.source_tree_entries())
    assert entries == dict(gate.source_tree_entries_for_commit(head) or {})
    assert entries, "no source file was hashed"

    # A working copy that differs from HEAD is reported, so main() runs the heavy checks instead of
    # reusing a record of the committed tree.
    reported = {
        name.decode()
        for name in _git("diff-index", "--name-only", "-z", "HEAD", "--").split(b"\x00")
        if name
    }
    dirty = gate.dirty_source_paths()
    assert dirty == sorted(p for p in reported if gate.is_source_tree_path(p))

    # A clean text path whose checkout holds CRLF while its blob holds LF must hash to the blob's id:
    # line endings must not move the digest, or a clone could not reuse the row.
    for path in sorted(entries):
        if path in set(dirty) or not path.endswith((".py", ".yaml", ".yml", ".json", ".jsonl", ".md")):
            continue
        disk = (REPO_ROOT / path).read_bytes()
        if b"\r\n" not in disk:
            continue
        blob = _git("cat-file", "blob", f"HEAD:{path}")
        assert disk.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n")
        assert entries[path] == _git("rev-parse", f"HEAD:{path}").decode().strip()
        break


def test_n160_a_hand_written_hash_names_no_tree_and_is_refused():
    head = _git("rev-parse", "HEAD").decode().strip()
    head_hash = gate.source_tree_hash_at_commit(head)
    assert head_hash

    # The §80.3 forgery: poison a test, hash the poisoned tree with the gate's own function, and name
    # a commit that exists. The commit's tree is not that tree, so the row certifies nothing.
    entries = dict(gate.source_tree_entries())
    poisoned = dict(entries)
    poisoned["tests/unit/test_verdicts.py"] = "0" * 40
    forged_hash = gate.compute_source_tree_hash(list(poisoned.items()))
    assert forged_hash != head_hash

    forged = _green_record(forged_hash, head)
    problem = gate.green_record_problem(forged, gate.discovered_verification_scripts(), gate.commit_exists)
    assert problem is not None and "tree" in problem
    plan, used, _reason = gate.select_gate_plan(
        forged_hash, [forged], datetime.datetime.now(datetime.timezone.utc)
    )
    assert plan == "full" and used is None

    # A row hashing one tree and naming another commit is refused for the same reason.
    other = _git("rev-parse", f"{head}^").decode().strip()
    assert gate.green_record_problem(
        _green_record(head_hash, other), gate.discovered_verification_scripts(), gate.commit_exists
    ) is not None


def test_n160_a_run_over_a_dirty_tree_is_never_recorded():
    # A row names a commit's tree; a run that tested uncommitted code has no tree to name.
    assert gate.should_record_green("full", True, 529, []) is True
    assert gate.should_record_green("full", True, 529, ["src/signal_core/reporting/verdicts.py"]) is False
    assert gate.should_record_green("reuse", True, 529, []) is False
    assert gate.should_record_green("full", False, 529, []) is False
    assert gate.should_record_green("full", True, 0, []) is False


def test_n160_a_row_written_by_the_gate_is_reusable_on_a_clone(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "GREEN_CACHE_PATH", tmp_path / "source_tree_green.json")
    head = _git("rev-parse", "HEAD").decode().strip()
    head_hash = gate.source_tree_hash_at_commit(head)
    assert head_hash

    gate.append_green_record(
        head_hash,
        529,
        100.0,
        {script: 0 for script in gate.discovered_verification_scripts()},
        head[:7],
    )
    records = gate.load_green_cache()
    assert records and records[-1]["source_tree_scheme"] == gate.GREEN_CACHE_SCHEME

    now = datetime.datetime.now(datetime.timezone.utc)
    plan, used, _reason = gate.select_gate_plan(head_hash, records, now)
    assert plan == "reuse" and used is records[-1]

    # The pre-N-160 rows recorded a digest over working-copy bytes and carry no scheme, so they are
    # history rather than evidence.
    legacy = dict(records[-1])
    legacy.pop("source_tree_scheme")
    assert gate.select_gate_plan(head_hash, [legacy], now)[0] == "full"


# --- N-161: the fold count is an integer -------------------------------------------------------


def test_n161_overfit_06_rejects_a_coerced_fold_count():
    def overfit_06(**bundle):
        return _by_id({
            "walk_forward_positive_fold_ratio": Decimal("1.00"),
            **bundle,
        })["CRIT-OVERFIT-06"]

    for coerced in ("2", 2.0, True):
        evaluation = overfit_06(walk_forward_validation_folds_count=coerced)
        assert evaluation.status.value == "NOT RUN", (
            f"a fold count of {coerced!r} evaluated {evaluation.status.value}"
        )
        assert evaluation.computed_value is None

    genuine = overfit_06(walk_forward_validation_folds_count=2)
    assert genuine.status.value == "PASS"
    assert genuine.computed_value == "1.0000"

    assert overfit_06(walk_forward_validation_folds_count=1).status.value == "NOT RUN"

    losing = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("0.50"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert losing.status.value == "FAIL"
