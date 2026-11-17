"""
Unit tests for the Audit §78 remediation (audit §78 at 82e3ef0, reviewing 780ac4b).

Target invariants (criteria 1.1.8, carried into 1.1.9 unchanged except where §79 tightened them):
- N-148: `CRIT-STAT-01` is NOT RUN when `total_trades` arrives without liquidated positions or a
  declared liquidated count, so a censored book cannot pass by omitting its own evidence.
- N-149: `CRIT-OVERFIT-03` requires the four pre-registered anchored fold ends and refuses a
  self-declared ratio that carries no fold rows.
- N-150: `CRIT-OVERFIT-06` is NOT RUN below two validation folds, whatever ratio is supplied.
- N-151: `ISIN_TRANSITION` rows are generated from the committed interval table for every multi-ISIN
  symbol, so a corpus extension cannot re-enter the undocumented-interval refusal path.
- §78.15 (a): volume 1 of the audit log is frozen byte-for-byte at its pinned digest.
- §78.15 (b): the source-tree green cache reuses only an identical source tree, and fails closed on
  an unknown hash or a stale record.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import yaml

from signal_core.contracts.criteria import compute_manifest_fingerprint, load_go_no_go_criteria
from signal_core.reporting.verdicts import IS_FOLD_ENDS, evaluate_verdicts
from signal_core.storage.security_master import (
    CorporateActionType,
    load_cash_universe_symbol_intervals,
    load_corporate_actions,
)
from scripts.derive_2022_2024_corpora import (
    generate_corporate_actions_corpus,
    generate_isin_transition_rows,
)
from scripts.probe_audit_findings import PROBES
from scripts.verify_audit_append_only import (
    GREEN_CACHE_SCHEME,
    compute_source_tree_hash,
    compute_volume_digest,
    discovered_verification_scripts,
    is_source_tree_path,
    select_gate_plan,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": "2026-11-17T12:00:00+00:00"}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


def _fold(end: str, expectancy: str, profit_factor: str) -> dict:
    return {
        "label": f"IS-{end}",
        "fold_end": end,
        "closed_net_expectancy": Decimal(expectancy),
        "liquidated_profit_factor": Decimal(profit_factor),
    }


# --- N-148: an unreconcilable basis is NOT RUN ------------------------------------------------


def test_n148_total_trades_without_liquidated_evidence_is_not_run():
    alone = _by_id({"total_trades": 193})["CRIT-STAT-01"]
    assert alone.status.value == "NOT RUN"
    assert alone.computed_value is None
    assert "liquidated_open_positions" in alone.evidence

    # The §14.4 shape: the closed-only label plus the total, and no liquidated evidence.
    censored = _by_id({"total_trades": 193, "closed_only_trade_count": 193})["CRIT-STAT-01"]
    assert censored.status.value == "NOT RUN"

    # A reconciled de-censored book still passes, and still fails when the numbers disagree.
    reconciled = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 193,
        "liquidated_open_positions": [
            {"isin": f"INE00000000{i}", "net_pnl": "1.00"} for i in range(12)
        ],
    })["CRIT-STAT-01"]
    assert reconciled.status.value == "PASS"
    assert reconciled.computed_value == "205"

    mismatch = _by_id({"total_trades": 205, "liquidated_trade_count": 193})["CRIT-STAT-01"]
    assert mismatch.status.value == "FAIL"


# --- N-149: the anchored fold set is pinned ----------------------------------------------------


def test_n149_fold_set_is_pinned_to_the_four_committed_ends():
    assert IS_FOLD_ENDS == ("2022-06-30", "2022-12-30", "2023-06-30", "2023-12-29")

    one = _by_id({"is_folds": [_fold(IS_FOLD_ENDS[0], "100.00", "1.60")]})["CRIT-OVERFIT-03"]
    assert one.status.value == "FAIL"
    assert one.computed_value is None
    assert "does not match the four pre-registered ends" in one.evidence

    two = _by_id({
        "is_folds": [_fold(IS_FOLD_ENDS[0], "100.00", "1.60"), _fold(IS_FOLD_ENDS[1], "100.00", "1.60")],
    })["CRIT-OVERFIT-03"]
    assert two.status.value == "FAIL"

    # A declared ratio with no fold rows is not evidence.
    declared = _by_id({"positive_is_fold_ratio": Decimal("0.75")})["CRIT-OVERFIT-03"]
    assert declared.status.value == "NOT RUN"
    assert declared.computed_value is None
    assert "cannot be validated" in declared.evidence

    # A different end is as wrong as a missing one.
    drifted = _by_id({
        "is_folds": [
            _fold(IS_FOLD_ENDS[0], "100.00", "1.60"),
            _fold(IS_FOLD_ENDS[1], "100.00", "1.60"),
            _fold(IS_FOLD_ENDS[2], "100.00", "1.60"),
            _fold("2024-06-28", "100.00", "1.60"),
        ],
    })["CRIT-OVERFIT-03"]
    assert drifted.status.value == "FAIL"
    assert "unexpected [2024-06-28]" in drifted.evidence

    full = _by_id({"is_folds": [_fold(end, "100.00", "1.60") for end in IS_FOLD_ENDS]})
    assert full["CRIT-OVERFIT-03"].status.value == "PASS"
    assert full["CRIT-OVERFIT-03"].computed_value == "1.0000"


# --- N-150: the validation-fold minimum is enforced --------------------------------------------


def test_n150_validation_fold_minimum_is_enforced_before_the_ratio():
    single = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 1,
    })["CRIT-OVERFIT-06"]
    assert single.status.value == "NOT RUN"
    assert "N_val = 1" in single.evidence
    assert "minimum 2 independent" in single.evidence

    two = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert two.status.value == "PASS"
    assert two.computed_value == "1.0000"

    # Two folds with a losing ratio still fails on the ratio, not on the count.
    losing = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("0.50"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert losing.status.value == "FAIL"


# --- N-151: the transition table is generated, not hand-maintained ------------------------------


def test_n151_generator_covers_every_multi_isin_symbol():
    intervals = load_cash_universe_symbol_intervals()
    multi_isin_symbols = {
        interval.symbol
        for interval in intervals
        if len({i.isin for i in intervals if i.symbol == interval.symbol}) > 1
    }
    assert len(multi_isin_symbols) > 200, (len(multi_isin_symbols), "multi-ISIN symbols")

    generated = generate_isin_transition_rows(intervals, set())
    assert generated, "generator produced no transition rows"
    covered_symbols = {row.symbol for row in generated}
    assert multi_isin_symbols == covered_symbols, (
        f"uncovered: {sorted(multi_isin_symbols - covered_symbols)[:5]}"
    )

    # Deterministic: the same table yields the same rows.
    again = generate_isin_transition_rows(intervals, set())
    assert [(r.isin, r.new_isin, r.ex_date) for r in generated] == [
        (r.isin, r.new_isin, r.ex_date) for r in again
    ]

    # The committed corpus carries every generated pair, and no pair twice.
    corpus = load_corporate_actions()
    committed_pairs = [
        (row.old_isin, row.new_isin)
        for row in corpus
        if row.action_type == CorporateActionType.ISIN_TRANSITION
    ]
    assert len(committed_pairs) == len(set(committed_pairs)), "duplicate transition pair"
    generated_pairs = {(row.isin, row.new_isin) for row in generated}
    assert generated_pairs == set(committed_pairs)

    # Every row is unattested: the interval table is the witness, not a circular (N-152). Generated
    # rows carry no share ratio, while the three rows whose ratio comes from a committed SPLIT keep it.
    generated_ref_prefix = "UNATTESTED_NSE_INTERVAL_TABLE_"
    ratio_bearing = 0
    for row in corpus:
        if row.action_type != CorporateActionType.ISIN_TRANSITION:
            continue
        assert row.provenance == "CONTENT_IDENTIFIED_ONLY"
        assert str(row.circular_ref).startswith("UNATTESTED_")
        if str(row.circular_ref).startswith(generated_ref_prefix):
            assert row.ratio_numerator == row.ratio_denominator, (
                f"{row.symbol} generated transition claims a share ratio the interval table cannot establish"
            )
        else:
            ratio_bearing += 1
    assert ratio_bearing == 3, f"{ratio_bearing} explicit transition row(s) carry a ratio, expected 3"


def test_n151_generator_reproduces_the_committed_corpus():
    corpus = generate_corporate_actions_corpus()
    committed = (REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl").read_text(
        encoding="utf-8"
    )
    rendered = "".join(json.dumps(action.to_dict()) + "\n" for action in corpus)
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == hashlib.sha256(
        committed.encode("utf-8")
    ).hexdigest(), "corporate_actions.jsonl no longer reproduces from its generator"


# --- §78.15 (a): frozen volume enforcement -----------------------------------------------------


def test_audit_volume1_is_frozen_at_its_pinned_digest():
    config = yaml.safe_load((REPO_ROOT / "configs" / "audit_volumes.yaml").read_text(encoding="utf-8"))
    volumes = {str(volume["path"]): volume for volume in config["volumes"]}
    volume1 = volumes["reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md"]
    assert volume1["frozen"] is True
    assert volume1["sections"] == "1-78"

    # Audit §79.7 (N-154): the digest is computed over the text with CRLF folded to LF, so the pin is a
    # property of the committed volume rather than of the machine that checked it out.
    path = REPO_ROOT / volume1["path"]
    digest, line_count = compute_volume_digest(path)
    assert digest == volume1["sha256"]
    assert line_count == volume1["line_count"] == 8442

    volume2 = volumes["reports/audit/volume2.md"]
    assert volume2["frozen"] is False
    assert volume2["sections"] == "79+"


# --- §78.15 (b): source-tree green cache -------------------------------------------------------


def test_source_tree_hash_ignores_audit_prose_and_docs():
    assert not is_source_tree_path("reports/audit/findings.jsonl")
    assert not is_source_tree_path("docs/notes.md")
    assert not is_source_tree_path("CURRENT_STAGE_OF_WORK.md")
    assert not is_source_tree_path("data/reference/source_tree_green.json")
    assert is_source_tree_path("src/signal_core/reporting/verdicts.py")
    assert is_source_tree_path("configs/go_no_go_criteria.yaml")
    assert is_source_tree_path("data/reference/corporate_actions.jsonl")

    entries = [("src/a.py", "a" * 64), ("tests/b.py", "b" * 64)]
    same = compute_source_tree_hash(entries)
    assert same == compute_source_tree_hash(list(reversed(entries)))
    changed = compute_source_tree_hash([("src/a.py", "c" * 64), ("tests/b.py", "b" * 64)])
    assert changed != same


def test_green_cache_reuses_only_an_identical_fresh_source_tree():
    now = datetime.datetime(2026, 11, 17, 12, 0, tzinfo=datetime.timezone.utc)
    verifier_scripts = discovered_verification_scripts()
    assert len(verifier_scripts) == 9

    # Audit §79.8 (N-155): a record is reusable only when it witnesses a complete green run — every
    # discovered verifier at exit 0, a suite count above the pinned floor, and a real commit.
    record = {
        "source_tree_hash": "h1",
        "source_tree_scheme": GREEN_CACHE_SCHEME,
        "suite_count": 523,
        "verify_exits": {script: 0 for script in verifier_scripts},
        "utc": (now - datetime.timedelta(hours=2)).isoformat(),
        "gate_sha": "3119cb2",
    }

    def resolve(sha: str) -> bool:
        return sha == "3119cb2"

    # §80.3 (N-160): the record is only evidence for the tree its `gate_sha` contains.
    def projects(sha: str):
        return "h1" if sha == "3119cb2" else None

    plan, used, reason = select_gate_plan(
        "h1", [record], now, head_commit="3119cb2", verifier_scripts=verifier_scripts,
        resolve_commit=resolve, project_tree_hash=projects,
    )
    assert plan == "reuse"
    assert used is not None and used["gate_sha"] == "3119cb2"

    assert select_gate_plan(
        "h2", [record], now, head_commit="3119cb2", verifier_scripts=verifier_scripts
    )[0] == "full"
    assert select_gate_plan(
        "h1", [], now, head_commit="3119cb2", verifier_scripts=verifier_scripts
    )[0] == "full"
    assert select_gate_plan(
        "h1", [record], now, head_commit="3119cb2", force_full=True,
        verifier_scripts=verifier_scripts,
    )[0] == "full"

    # A row whose commit projects a different tree is not a hit, whatever hash it records.
    assert select_gate_plan(
        "h1", [record], now, head_commit="3119cb2", verifier_scripts=verifier_scripts,
        resolve_commit=resolve, project_tree_hash=lambda sha: "h9",
    )[0] == "full"

    stale = dict(record, utc=(now - datetime.timedelta(hours=25)).isoformat())
    plan, _used, reason = select_gate_plan(
        "h1", [stale], now, head_commit="3119cb2", verifier_scripts=verifier_scripts,
        resolve_commit=resolve, project_tree_hash=projects,
    )
    assert plan == "full"
    assert "24h" in reason

    failing = dict(record, verify_exits={script: 1 for script in verifier_scripts})
    assert select_gate_plan(
        "h1", [failing], now, head_commit="3119cb2", verifier_scripts=verifier_scripts,
        resolve_commit=resolve,
    )[0] == "full"

    # Audit §81.4 (N-162): the tree is not the key -- a row recorded at another commit is not reused even
    # when it projects the verified tree, and a caller that cannot resolve HEAD cannot reuse at all.
    assert select_gate_plan(
        "h1", [record], now, head_commit="9999999", verifier_scripts=verifier_scripts,
        resolve_commit=resolve, project_tree_hash=projects,
    )[0] == "full"
    assert select_gate_plan(
        "h1", [record], now, head_commit="not-a-commit", verifier_scripts=verifier_scripts
    )[0] == "full"


# --- §78.15 (c): the findings ledger is executable ---------------------------------------------


def test_findings_ledger_rows_carry_executable_probes():
    ledger = (REPO_ROOT / "reports" / "audit" / "findings.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in ledger.splitlines() if line.strip()]
    # Audit §79.9: the ledger is append-only per finding, so a closure is a later row with the same
    # id and the latest row is authoritative.
    latest = {}
    for row in rows:
        latest[row["id"]] = row
    rows = list(latest.values())
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    for expected in ("N-148", "N-149", "N-150", "N-151", "N-152", "N-153"):
        assert expected in ids

    for row in rows:
        assert row["probe"]["command"].endswith(row["id"])
        assert row["probe"]["expect_exit"] == 0
        if row["status"] != "ACCEPTED":
            assert row["id"] in PROBES, f"{row['id']} has no probe implementation"
            PROBES[row["id"]]()


# --- Criteria reseal the pin and move nothing else ----------------------------------------------


def test_criteria_1_1_9_reseals_only_the_manifest_pin():
    crit = load_go_no_go_criteria()
    assert crit.version == "1.1.9"
    assert crit.expected_manifest_fingerprint == compute_manifest_fingerprint(
        REPO_ROOT / "data" / "reference" / "manifest.jsonl"
    )
    assert crit.min_total_trades == 100
    assert crit.min_profit_factor == Decimal("1.50")
    assert crit.min_deflated_sharpe_ratio == Decimal("0.95")
    assert crit.min_haircut_sharpe_ratio == Decimal("1.25")
    assert crit.max_single_position_weight == Decimal("0.10")
    assert crit.min_traded_eq_resolution_pct == Decimal("100.0")
    assert crit.min_dataset_instrument_resolution_pct == Decimal("100.0")
    assert crit.min_positive_walk_forward_fold_ratio == Decimal("0.80")
    assert crit.min_positive_is_fold_ratio == Decimal("0.75")
    assert crit.min_fold_liquidated_pf == Decimal("1.30")
    assert crit.min_liquidated_pf_ex_top_1 == Decimal("1.40")
