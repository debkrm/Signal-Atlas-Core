"""
Unit tests for the Audit §79 remediation (audit §79 in `reports/audit/volume2.md`, reviewing `3119cb2`).

Target invariants (criteria 1.1.9):
- N-154: a frozen audit volume hashes the same bytes on a Windows working copy and a Linux checkout, so
  the pin is a property of the committed text rather than of the machine that wrote it.
- N-155: the source-tree green cache is reusable only for a record that witnesses a complete green run
  — every discovered verifier at exit 0, a suite count above the pinned floor, a commit that exists.
- N-156: `CRIT-OVERFIT-06` is NOT RUN when a positive fold ratio arrives without a validation-fold count.
- N-157: the findings ledger records forward transitions only (`OPEN -> CLOSED/ACCEPTED`), and a
  closure cites its section.
- N-158: every documented identity pair meets its successor interval boundary, and a drifted row is
  refused instead of skipped.
- N-159: `CRIT-STAT-01` is NOT RUN when `total_trades` and positions arrive without a closed-only count.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from signal_core.reporting.verdicts import evaluate_verdicts
from signal_core.storage.security_master import (
    CorporateActionType,
    load_cash_universe_symbol_intervals,
    load_corporate_actions,
)
from scripts.derive_2022_2024_corpora import (
    adjacent_identity_pairs,
    validate_documented_transition_dates,
)
from scripts.verify_audit_append_only import (
    GREEN_CACHE_MIN_SUITE_COUNT,
    GREEN_CACHE_SCHEME,
    compute_volume_digest,
    discovered_verification_scripts,
    green_record_problem,
    select_gate_plan,
)
from scripts.verify_audit_findings import validate_ledger

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": "2026-11-17T12:00:00+00:00"}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


# --- N-154: the frozen volume digest is line-ending independent --------------------------------


def test_n154_frozen_volume_digest_does_not_depend_on_the_checkout(tmp_path):
    config = yaml.safe_load((REPO_ROOT / "configs" / "audit_volumes.yaml").read_text(encoding="utf-8"))
    volume1 = {str(v["path"]): v for v in config["volumes"]}[
        "reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md"
    ]

    digest, line_count = compute_volume_digest(REPO_ROOT / volume1["path"])
    assert digest == volume1["sha256"] == (
        "f4ca03d58466bebb55e8ec0dcb30bc80847a47de3e86879c657117e8022bc7ff"
    )
    assert line_count == volume1["line_count"] == 8442

    # The same text checked out with CRLF must hash to the same pin: this is the §79.7 defect.
    text = (REPO_ROOT / volume1["path"]).read_text(encoding="utf-8")
    crlf_copy = tmp_path / "volume1_crlf.md"
    crlf_copy.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert crlf_copy.read_bytes() != (REPO_ROOT / volume1["path"]).read_bytes()
    assert compute_volume_digest(crlf_copy) == (digest, line_count)

    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "reports/audit/** text eol=lf" in attributes


# --- N-155: a forged or incomplete green-cache row cannot retire the suite ---------------------


def test_n155_forged_green_cache_row_is_not_reusable():
    now = datetime.datetime(2026, 11, 17, 12, 0, tzinfo=datetime.timezone.utc)
    verifiers = discovered_verification_scripts()
    # Audit §98.10 item 3 adds `verify_seq10_certificate.py`, so the discovered sweep is 10, not 9.
    assert len(verifiers) == 10

    healthy = {
        "source_tree_hash": "h1",
        "source_tree_scheme": GREEN_CACHE_SCHEME,
        "suite_count": 523,
        "verify_exits": {script: 0 for script in verifiers},
        "utc": (now - datetime.timedelta(hours=1)).isoformat(),
        "gate_sha": "3119cb2",
    }

    def resolves(sha: str) -> bool:
        return sha == "3119cb2"

    # §80.3 (N-160): the record's hash must be the tree its `gate_sha` contains, so the fixture projects
    # the same tree from the commit it names.
    def projects(sha: str):
        return "h1" if sha == "3119cb2" else None

    assert green_record_problem(healthy, verifiers, resolves, projects) is None

    # The §79.8 forgery: no verifier ran, one test supposedly passed, and the sha is a label.
    forged = dict(healthy, verify_exits={}, suite_count=1, gate_sha="forged")
    assert green_record_problem(forged, verifiers, lambda sha: False, projects) is not None

    assert green_record_problem(dict(healthy, verify_exits={}), verifiers, resolves, projects) is not None
    partial = {script: 0 for script in verifiers[:1]}
    assert green_record_problem(
        dict(healthy, verify_exits=partial), verifiers, resolves, projects
    ) is not None
    assert green_record_problem(
        dict(healthy, verify_exits={script: 1 for script in verifiers}), verifiers, resolves, projects
    ) is not None
    assert green_record_problem(
        dict(healthy, suite_count=GREEN_CACHE_MIN_SUITE_COUNT - 1), verifiers, resolves, projects
    ) is not None
    assert green_record_problem(healthy, verifiers, lambda sha: False, projects) is not None

    # A row whose hash is not the tree of the commit it names is not evidence (N-160).
    assert green_record_problem(dict(healthy, source_tree_hash="h2"), verifiers, resolves, projects) is not None
    assert green_record_problem(
        dict(healthy, source_tree_scheme="working-copy-sha256"), verifiers, resolves, projects
    ) is not None

    # The row names the verified commit and is still refused for what it witnesses (no verifier ran, one
    # test passed), so the content checks are not hidden behind the commit key (§81.4, N-162).
    plan, record, reason = select_gate_plan(
        "h1", [dict(forged, gate_sha="3119cb2")], now, head_commit="3119cb2",
        verifier_scripts=verifiers, resolve_commit=resolves, project_tree_hash=projects,
    )
    assert plan == "full"
    assert record is None
    assert "suite_count" in reason or "verifier" in reason

    # A label with no commit behind it is refused as a commit, whatever tree it claims.
    plan, record, reason = select_gate_plan(
        "h1", [forged], now, head_commit="3119cb2", verifier_scripts=verifiers,
        resolve_commit=resolves, project_tree_hash=projects,
    )
    assert plan == "full" and record is None
    assert "forged" in reason, reason

    plan, record, _reason = select_gate_plan(
        "h1", [healthy], now, head_commit="3119cb2", verifier_scripts=verifiers,
        resolve_commit=resolves, project_tree_hash=projects,
    )
    assert plan == "reuse" and record is healthy


# --- N-156: OVERFIT-06 requires the validation-fold count --------------------------------------


def test_n156_overfit_06_requires_the_validation_fold_count():
    missing = _by_id({"walk_forward_positive_fold_ratio": Decimal("1.00")})["CRIT-OVERFIT-06"]
    assert missing.status.value == "NOT RUN"
    assert missing.computed_value is None
    assert "walk_forward_validation_folds_count" in missing.evidence

    non_integer = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": "two",
    })["CRIT-OVERFIT-06"]
    assert non_integer.status.value == "NOT RUN"

    # The fix must not reject every ratio: two folds still gate the ratio itself.
    two = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert two.status.value == "PASS"
    assert two.computed_value == "1.0000"

    losing = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("0.50"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert losing.status.value == "FAIL"


# --- N-157: the ledger records forward transitions, and closures cite their section ------------


def test_n157_ledger_transitions_are_validated():
    base = {
        "id": "N-999",
        "section": 79,
        "severity": "LOW",
        "metric": "synthetic row",
        "phase": "synthetic",
        "probe": {"command": "python scripts/probe_audit_findings.py N-999", "stdout_regex": "^PASS N-999$"},
    }
    open_row = dict(base, status="OPEN")
    closed_row = dict(base, status="CLOSED", closed_in_section=79)
    accepted_row = dict(base, status="ACCEPTED", residual="carried")

    assert validate_ledger([open_row, closed_row]) == []
    assert validate_ledger([open_row, accepted_row]) == []
    assert validate_ledger([open_row, accepted_row, closed_row]) == []

    duplicate = validate_ledger([open_row, dict(base, status="OPEN")])
    assert duplicate and "Duplicate" in duplicate[0]

    backward = validate_ledger([open_row, closed_row, dict(base, status="OPEN")])
    assert backward and "not a forward transition" in backward[0]

    uncited = validate_ledger([open_row, dict(base, status="CLOSED")])
    assert uncited and "closed_in_section" in uncited[0]

    # The committed ledger satisfies the ratified semantics as it stands.
    committed = [
        json.loads(line)
        for line in (REPO_ROOT / "reports" / "audit" / "findings.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert validate_ledger(committed) == []


# --- N-158: documented identity pairs meet their interval boundary -----------------------------


def test_n158_every_documented_transition_meets_its_interval_boundary():
    intervals = load_cash_universe_symbol_intervals()
    actions = list(load_corporate_actions())
    pairs = adjacent_identity_pairs(intervals)
    # Audit §90.7 Ruling 1: 324 is the measured count of post-2022 boundaries, not a frozen numeral.
    # §90.9 item 3 extended the log over the 931 warm-up sessions and added 102 correctly documented
    # boundaries, so the total is 426 while every one of the 324 post-2022 tuples survives.
    post_2022 = [pair for pair in pairs if pair[3] >= datetime.date(2022, 1, 3)]
    assert len(post_2022) == 324
    assert len(pairs) == 426

    assert validate_documented_transition_dates(intervals, actions) == 426

    documented = {
        (row.old_isin, row.new_isin): row
        for row in actions
        if row.action_type is CorporateActionType.ISIN_TRANSITION
    }
    misaligned = [
        (old_isin, new_isin)
        for _symbol, old_isin, new_isin, effective_from in pairs
        if documented[(old_isin, new_isin)].ex_date != effective_from
    ]
    assert not misaligned

    tata = next(row for row in documented.values() if row.symbol == "TATASTEEL")
    assert tata.ex_date.isoformat() == "2022-07-29"

    # A hand-written row dated away from the boundary is refused, not skipped as "documented".
    drifted = [
        dataclasses.replace(tata, ex_date=datetime.date(2022, 7, 28)),
        *[row for row in actions if row.action_type is not CorporateActionType.ISIN_TRANSITION],
    ]
    with pytest.raises(ValueError, match="N-158"):
        validate_documented_transition_dates(intervals, drifted)


# --- N-159: STAT-01 requires the closed-only count alongside positions --------------------------


def test_n159_stat01_requires_the_closed_count_with_positions():
    empty = _by_id({"total_trades": 205, "liquidated_open_positions": []})["CRIT-STAT-01"]
    assert empty.status.value == "NOT RUN"
    assert empty.computed_value is None
    assert "closed_only_trade_count" in empty.evidence

    positions = [{"isin": f"INE00000000{i}", "net_pnl": "1.00"} for i in range(12)]
    unreconcilable = _by_id({
        "total_trades": 205,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert unreconcilable.status.value == "NOT RUN"

    reconciled = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 193,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert reconciled.status.value == "PASS"
    assert reconciled.computed_value == "205"

    mismatch = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 200,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert mismatch.status.value == "FAIL"

    # The declared-count arm is unchanged: N-148's PASS/FAIL shapes still hold.
    declared = _by_id({"total_trades": 193, "liquidated_trade_count": 193})["CRIT-STAT-01"]
    assert declared.status.value == "PASS"
    declared_mismatch = _by_id({"total_trades": 205, "liquidated_trade_count": 193})["CRIT-STAT-01"]
    assert declared_mismatch.status.value == "FAIL"
