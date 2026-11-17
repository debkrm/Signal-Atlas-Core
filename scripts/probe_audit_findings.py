#!/usr/bin/env python3
"""
Executable acceptance probes for the findings registered in `reports/audit/findings.jsonl`
(Audit §78.15 (c)).

One probe per finding id, so the auditor's acceptance test is a computation the implementer can run
before committing, and a fix that only works on the new path fails the old path's probe by
construction. Each probe raises AssertionError with the measurement that failed; nothing is printed
as a verdict it did not compute.

Usage:
    python scripts/probe_audit_findings.py N-148
    python scripts/probe_audit_findings.py --list
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT / "src"), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.reporting.verdicts import evaluate_verdicts  # noqa: E402

PROBE_EVALUATED_AT = "2026-11-17T12:00:00+00:00"


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": PROBE_EVALUATED_AT}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


def probe_n148() -> None:
    """`total_trades` without liquidated evidence is NOT RUN, not a PASS on the key's name."""
    alone = _by_id({"total_trades": 193})["CRIT-STAT-01"]
    assert alone.status.value == "NOT RUN", f"total_trades alone evaluated {alone.status.value}"
    assert "liquidated_open_positions" in alone.evidence

    with_closed = _by_id({"total_trades": 193, "closed_only_trade_count": 193})["CRIT-STAT-01"]
    assert with_closed.status.value == "NOT RUN", (
        f"censored count with a closed-only label evaluated {with_closed.status.value}"
    )

    reconciled = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 193,
        "liquidated_open_positions": [{"isin": "INE000000001", "net_pnl": "1.00"} for _ in range(12)],
    })["CRIT-STAT-01"]
    assert reconciled.status.value == "PASS", reconciled.evidence
    assert reconciled.computed_value == "205"


def probe_n149() -> None:
    """`CRIT-OVERFIT-03` requires all four pre-registered anchored fold ends."""
    ends = ("2022-06-30", "2022-12-30", "2023-06-30", "2023-12-29")

    def fold(end: str, expectancy: str, pf: str) -> dict:
        return {
            "label": f"IS-{end}",
            "fold_end": end,
            "closed_net_expectancy": Decimal(expectancy),
            "liquidated_profit_factor": Decimal(pf),
        }

    one = _by_id({"is_folds": [fold(ends[0], "100.00", "1.60")]})["CRIT-OVERFIT-03"]
    assert one.status.value == "FAIL", f"one positive fold evaluated {one.status.value}"
    assert computed_missing(one), one.evidence

    two = _by_id({"is_folds": [fold(ends[0], "100.00", "1.60"), fold(ends[1], "100.00", "1.60")]})
    assert two["CRIT-OVERFIT-03"].status.value == "FAIL"

    declared = _by_id({"positive_is_fold_ratio": Decimal("0.75")})["CRIT-OVERFIT-03"]
    assert declared.status.value == "NOT RUN", declared.evidence

    full = _by_id({"is_folds": [fold(end, "100.00", "1.60") for end in ends]})["CRIT-OVERFIT-03"]
    assert full.status.value == "PASS", full.evidence
    assert full.computed_value == "1.0000"


def computed_missing(evaluation) -> bool:
    return evaluation.computed_value is None


def probe_n150() -> None:
    """`CRIT-OVERFIT-06` is NOT RUN below two validation folds, ratio or not."""
    single = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 1,
    })["CRIT-OVERFIT-06"]
    assert single.status.value == "NOT RUN", f"one validation fold evaluated {single.status.value}"
    assert "minimum 2 independent" in single.evidence

    two = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert two.status.value == "PASS", two.evidence


def probe_n151() -> None:
    """Every multi-ISIN symbol in the committed interval table carries an ISIN_TRANSITION row."""
    from derive_2022_2024_corpora import generate_isin_transition_rows
    from signal_core.storage.security_master import (
        CorporateActionType,
        load_cash_universe_symbol_intervals,
        load_corporate_actions,
    )

    intervals = load_cash_universe_symbol_intervals()
    all_pairs = {
        (row.old_isin, row.new_isin)
        for row in generate_isin_transition_rows(intervals, set())
    }
    corpus = load_corporate_actions()
    documented = {
        (row.old_isin, row.new_isin)
        for row in corpus
        if row.action_type == CorporateActionType.ISIN_TRANSITION and row.old_isin and row.new_isin
    }
    missing = sorted(all_pairs - documented)
    assert not missing, f"{len(missing)} identity pair(s) undocumented, e.g. {missing[:3]}"

    multi_isin_symbols = {
        interval.symbol
        for interval in intervals
        if len({i.isin for i in intervals if i.symbol == interval.symbol}) > 1
    }
    covered_symbols = {
        row.symbol for row in corpus if row.action_type == CorporateActionType.ISIN_TRANSITION
    }
    uncovered = sorted(multi_isin_symbols - covered_symbols)
    assert not uncovered, f"{len(uncovered)} multi-ISIN symbol(s) without a row: {uncovered[:5]}"
    assert len(documented) == len(all_pairs), (
        f"{len(documented)} transition row(s) for {len(all_pairs)} documented pair(s)"
    )


def probe_n152() -> None:
    """No transition row claims attestation without naming a circular (fail-closed provenance)."""
    from signal_core.storage.security_master import CorporateActionType, load_corporate_actions

    unverified = 0
    for row in load_corporate_actions():
        if row.action_type != CorporateActionType.ISIN_TRANSITION:
            continue
        assert row.provenance in ("CONTENT_IDENTIFIED_ONLY", "VERIFIED"), row.provenance
        if row.provenance == "VERIFIED":
            assert row.circular_ref and not str(row.circular_ref).startswith("UNATTESTED_"), (
                f"{row.symbol} claims VERIFIED identity with reference {row.circular_ref!r}"
            )
        else:
            assert str(row.circular_ref).startswith("UNATTESTED_"), (
                f"{row.symbol} is unverified but its reference is not marked UNATTESTED_: {row.circular_ref!r}"
            )
            unverified += 1
    assert unverified > 0, "no transition row was inspected"


def probe_n153() -> None:
    """
    IRB's boundary spike is post-split trading, not an unadjusted artefact.

    Raw Bhavcopy: 2023-02-21 close 297.45, 2023-02-22 open 30.40 with PREVCLOSE 297.45 (a 1:10
    face-value change at the identity boundary), then close 34.05 and 29.70. The adjusted series'
    boundary move is therefore the raw post-split move, not a print of the split itself.
    """
    from signal_core.storage.security_master import load_corporate_actions

    closes: Dict[str, Decimal] = {}
    for name in ("cm21FEB2023bhav.csv.zip", "cm22FEB2023bhav.csv.zip", "cm23FEB2023bhav.csv.zip"):
        archive = REPO_ROOT / "data" / "raw" / "2023" / name
        assert archive.is_file(), f"missing committed raw archive {archive}"
        import zipfile

        with zipfile.ZipFile(archive) as zf:
            with zf.open(zf.namelist()[0]) as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
                for row in reader:
                    if row.get("SYMBOL", "").strip() == "IRB" and row.get("SERIES", "").strip() == "EQ":
                        closes[name[:8]] = (
                            Decimal(row["CLOSE"].strip()),
                            Decimal(row["OPEN"].strip()),
                            Decimal(row["PREVCLOSE"].strip()),
                        )

    # Each entry is (close, open, prevclose).
    prior_close, _prior_open, _prior_prev = closes["cm21FEB2"]
    split_close, split_open, split_prev = closes["cm22FEB2"]
    next_close, _next_open, _next_prev = closes["cm23FEB2"]

    assert split_prev == prior_close, (split_prev, prior_close)
    face_value_ratio = prior_close / split_open
    assert Decimal("9.5") < face_value_ratio < Decimal("10.5"), (
        f"boundary open/prior-close ratio {face_value_ratio} is not a 1:10 face-value change"
    )
    boundary_move = (split_close / (prior_close / Decimal("10")) - Decimal("1")) * Decimal("100")
    assert Decimal("14.0") < boundary_move < Decimal("15.0"), (
        f"adjusted boundary move {boundary_move:.2f}% does not reproduce the raw post-split move"
    )
    next_move = (next_close / split_close - Decimal("1")) * Decimal("100")
    assert Decimal("-13.5") < next_move < Decimal("-12.0"), f"next-session move {next_move:.2f}%"

    # The corpus records the identity, not a share ratio: it must not claim IRB's split as 1:1.
    irb_rows = [row for row in load_corporate_actions() if row.symbol == "IRB"]
    assert any(row.action_type.value == "ISIN_TRANSITION" for row in irb_rows), "IRB identity row missing"


def probe_n154() -> None:
    """A frozen volume's pin is a property of the committed text, not of the checkout (N-154)."""
    import os
    import tempfile

    import yaml

    from verify_audit_append_only import compute_volume_digest

    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "audit_volumes.yaml").read_text(encoding="utf-8")
    )
    volume = {str(v["path"]): v for v in config["volumes"]}[
        "reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md"
    ]
    path = REPO_ROOT / volume["path"]
    digest, line_count = compute_volume_digest(path)
    assert digest == volume["sha256"], f"volume hashes to {digest}, pinned {volume['sha256']}"
    assert line_count == int(volume["line_count"]), (
        f"{line_count} line(s), pinned {volume['line_count']}"
    )

    fd, name = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    crlf_copy = Path(name)
    try:
        crlf_copy.write_bytes(
            path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
        )
        assert compute_volume_digest(crlf_copy) == (digest, line_count), (
            "a CRLF checkout of the same text does not reproduce the pin"
        )
    finally:
        crlf_copy.unlink()

    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "reports/audit/** text eol=lf" in attributes


def probe_n156() -> None:
    """`CRIT-OVERFIT-06` cannot be cleared by a ratio that arrives without its fold count."""
    ratio_only = _by_id({"walk_forward_positive_fold_ratio": Decimal("1.00")})["CRIT-OVERFIT-06"]
    assert ratio_only.status.value == "NOT RUN", (
        f"a ratio with no fold count evaluated {ratio_only.status.value}"
    )
    assert ratio_only.computed_value is None

    one = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 1,
    })["CRIT-OVERFIT-06"]
    assert one.status.value == "NOT RUN", one.evidence

    unreadable = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": "two",
    })["CRIT-OVERFIT-06"]
    assert unreadable.status.value == "NOT RUN", unreadable.evidence

    two = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("1.00"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert two.status.value == "PASS", two.evidence
    assert two.computed_value == "1.0000"

    losing = _by_id({
        "walk_forward_positive_fold_ratio": Decimal("0.50"),
        "walk_forward_validation_folds_count": 2,
    })["CRIT-OVERFIT-06"]
    assert losing.status.value == "FAIL", losing.evidence


def probe_n157() -> None:
    """The findings ledger records forward transitions only, and every closure cites its section."""
    import json

    from verify_audit_findings import validate_ledger

    base = {
        "id": "N-999",
        "section": 79,
        "severity": "LOW",
        "metric": "synthetic row",
        "phase": "synthetic",
        "probe": {
            "command": "python scripts/probe_audit_findings.py N-999",
            "stdout_regex": "^PASS N-999$",
        },
    }

    def row(status: str, **extra) -> dict:
        entry = dict(base, status=status)
        entry.update(extra)
        return entry

    assert validate_ledger([row("OPEN"), row("CLOSED", closed_in_section=80)]) == []
    assert validate_ledger([row("OPEN"), row("ACCEPTED", residual="carried")]) == []
    assert validate_ledger(
        [row("OPEN"), row("ACCEPTED", residual="carried"), row("CLOSED", closed_in_section=80)]
    ) == []

    backward = validate_ledger([row("OPEN"), row("CLOSED", closed_in_section=80), row("OPEN")])
    assert backward and "not a forward transition" in backward[0], backward

    duplicate = validate_ledger([row("OPEN"), row("OPEN")])
    assert duplicate and "Duplicate" in duplicate[0], duplicate

    uncited = validate_ledger([row("OPEN"), row("CLOSED")])
    assert uncited and "closed_in_section" in uncited[0], uncited

    committed = [
        json.loads(line)
        for line in (REPO_ROOT / "reports" / "audit" / "findings.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert validate_ledger(committed) == [], validate_ledger(committed)


def probe_n158() -> None:
    """Every documented identity pair meets its successor interval, and a drifted row is refused."""
    import dataclasses
    import datetime

    from derive_2022_2024_corpora import adjacent_identity_pairs, validate_documented_transition_dates
    from signal_core.storage.security_master import (
        CorporateActionType,
        load_cash_universe_symbol_intervals,
        load_corporate_actions,
    )

    intervals = load_cash_universe_symbol_intervals()
    actions = list(load_corporate_actions())
    pairs = adjacent_identity_pairs(intervals)
    assert len(pairs) == 324, f"{len(pairs)} adjacent identity pair(s)"
    assert validate_documented_transition_dates(intervals, actions) == 324

    documented = {
        (row.old_isin, row.new_isin): row
        for row in actions
        if row.action_type is CorporateActionType.ISIN_TRANSITION
    }
    misaligned = [
        (symbol, old_isin, new_isin)
        for symbol, old_isin, new_isin, effective_from in pairs
        if documented[(old_isin, new_isin)].ex_date != effective_from
    ]
    assert not misaligned, f"{len(misaligned)} pair(s) dated away from the boundary: {misaligned[:3]}"

    tata = next(row for row in documented.values() if row.symbol == "TATASTEEL")
    assert tata.ex_date == datetime.date(2022, 7, 29), tata.ex_date

    drifted = [
        dataclasses.replace(tata, ex_date=datetime.date(2022, 7, 28)),
        *[row for row in actions if row.action_type is not CorporateActionType.ISIN_TRANSITION],
    ]
    try:
        validate_documented_transition_dates(intervals, drifted)
    except ValueError as exc:
        assert "N-158" in str(exc), str(exc)
    else:
        raise AssertionError("a drifted transition row was accepted instead of refused (N-158)")


def probe_n159() -> None:
    """`CRIT-STAT-01` requires the closed-only count before it reconciles positions."""
    empty = _by_id({"total_trades": 205, "liquidated_open_positions": []})["CRIT-STAT-01"]
    assert empty.status.value == "NOT RUN", f"an empty position list evaluated {empty.status.value}"
    assert empty.computed_value is None

    positions = [{"isin": f"INE00000000{i}", "net_pnl": "1.00"} for i in range(12)]
    uncounted = _by_id({
        "total_trades": 205,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert uncounted.status.value == "NOT RUN", uncounted.evidence

    reconciled = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 193,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert reconciled.status.value == "PASS", reconciled.evidence
    assert reconciled.computed_value == "205"

    mismatch = _by_id({
        "total_trades": 205,
        "closed_only_trade_count": 200,
        "liquidated_open_positions": positions,
    })["CRIT-STAT-01"]
    assert mismatch.status.value == "FAIL", mismatch.evidence

    declared = _by_id({"total_trades": 193, "liquidated_trade_count": 193})["CRIT-STAT-01"]
    assert declared.status.value == "PASS", declared.evidence


def probe_n160() -> None:
    """
    A green row binds to a git tree: a hand-written hash names no tree that was ever run (N-160).

    Half one: the recorded digest is composed of the object ids git stores, so the CRLF working copy
    this checkout holds hashes exactly as an LF clone of the same commit. Half two: a row is reusable
    only when `gate_sha`'s own tree projects to the recorded hash, so the §80.3 forgery is refused.
    """
    import datetime
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_MIN_SUITE_COUNT,
        commit_exists,
        compute_source_tree_hash,
        dirty_source_paths,
        discovered_verification_scripts,
        green_record_problem,
        is_source_tree_path,
        select_gate_plan,
        source_tree_entries,
        source_tree_entries_for_commit,
        source_tree_hash_at_commit,
    )

    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=str(REPO_ROOT), capture_output=True, check=True,
        ).stdout

    head = git("rev-parse", "HEAD").decode().strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash, f"HEAD {head[:8]} projects no source tree"

    # The digest is HEAD's tree, not this checkout's bytes. A text file whose working copy holds CRLF
    # while its blob holds LF must hash to the blob's oid, or a clone would compute a different digest.
    entries = dict(source_tree_entries())
    assert entries == dict(source_tree_entries_for_commit(head) or {}), (
        "the source-tree hash is not composed of HEAD's blob oids"
    )

    # An uncommitted source change is not certifiable by a recorded tree: it is reported, and the gate
    # runs the heavy checks instead of reusing one (measured through the same function main() calls).
    reported = {
        entry.decode("utf-8")[3:]
        for entry in git(
            "status", "--porcelain", "-z", "--untracked-files=no", "--no-renames"
        ).split(b"\x00")
        if entry
    }
    dirty = dirty_source_paths()
    assert dirty == sorted(p for p in reported if is_source_tree_path(p)), dirty
    # A path in the dirty set must actually differ from its blob: no stat-only noise may force a full run.
    for rel in dirty:
        blob = git("cat-file", "blob", f"HEAD:{rel}")
        disk = (REPO_ROOT / rel).read_bytes()
        assert disk.replace(b"\r\n", b"\n") != blob.replace(b"\r\n", b"\n"), (
            f"{rel} is reported dirty but its content is its blob"
        )

    # Find a clean text file whose checkout differs from its blob only by line endings: its entry must
    # still be the committed blob's oid. A checkout with no CRLF at all satisfies the same digest by
    # construction (entries are HEAD's tree oids), so the example is a measurement, not the invariant.
    for rel in sorted(entries):
        if rel in set(dirty) or not rel.endswith((".py", ".yaml", ".yml", ".json", ".jsonl", ".md")):
            continue
        disk = (REPO_ROOT / rel).read_bytes()
        if b"\r\n" not in disk:
            continue
        blob = git("cat-file", "blob", f"HEAD:{rel}")
        assert disk.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n"), (
            f"{rel} differs from its blob by more than line endings"
        )
        assert entries[rel] == git("rev-parse", f"HEAD:{rel}").decode().strip(), (
            f"{rel} holds CRLF on disk yet does not hash to the blob oid {rel} was committed as"
        )
        break

    verifiers = discovered_verification_scripts()
    now = datetime.datetime.now(datetime.timezone.utc)

    from verify_audit_append_only import GREEN_CACHE_SCHEME

    def record(tree_hash: str, gate_sha: str = head) -> dict:
        return {
            "source_tree_hash": tree_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": max(GREEN_CACHE_MIN_SUITE_COUNT, 529),
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": gate_sha,
        }

    # Positive control: the tree at HEAD, recorded against HEAD, is reusable.
    healthy = record(head_hash)
    assert green_record_problem(healthy, verifiers, commit_exists) is None, (
        green_record_problem(healthy, verifiers, commit_exists)
    )
    plan, used, _reason = select_gate_plan(head_hash, [healthy], now, verifier_scripts=verifiers)
    assert plan == "reuse" and used is healthy

    # The §80.3 forgery: poison a test, hash the poisoned tree with the gate's own function, and name a
    # commit that exists. No tree in the repository has that hash, so the row cannot certify itself.
    entries = dict(source_tree_entries())
    assert "tests/unit/test_verdicts.py" in entries
    poisoned = dict(entries)
    poisoned["tests/unit/test_verdicts.py"] = "0" * 40
    forged_hash = compute_source_tree_hash(list(poisoned.items()))
    assert forged_hash != head_hash
    problem = green_record_problem(record(forged_hash), verifiers, commit_exists)
    assert problem is not None and "tree" in problem, problem
    plan, used, _reason = select_gate_plan(
        forged_hash, [record(forged_hash)], now, verifier_scripts=verifiers
    )
    assert plan == "full" and used is None

    # A row that hashes one tree and names another commit is refused as well.
    parent = git("rev-parse", f"{head}^")
    assert green_record_problem(
        record(head_hash, gate_sha=parent), verifiers, commit_exists
    ) is not None

    # The committed cache rows must be trees of the commits they name, so a clone recomputes the same
    # digest and can reuse the newest green run.
    from verify_audit_append_only import load_green_cache

    scheme_rows = [row for row in load_green_cache() if row.get("source_tree_scheme") == GREEN_CACHE_SCHEME]
    assert scheme_rows, "no cache row was recorded under the git-blob-oid scheme"
    for row in scheme_rows:
        sha = str(row.get("gate_sha") or "")
        assert commit_exists(sha), f"cache row names {sha!r}, which is not a commit"
        assert source_tree_hash_at_commit(sha) == row.get("source_tree_hash"), (
            f"cache row for {sha} records {str(row.get('source_tree_hash'))[:12]} but that commit's "
            f"tree is {str(source_tree_hash_at_commit(sha))[:12]}"
        )


def probe_n161() -> None:
    """The validation-fold count is an integer, not a string that coerces to one (N-161)."""
    def overfit_06(**bundle) -> object:
        return _by_id({
            "walk_forward_positive_fold_ratio": Decimal("1.00"),
            **bundle,
        })["CRIT-OVERFIT-06"]

    numeric_string = overfit_06(walk_forward_validation_folds_count="2")
    assert numeric_string.status.value == "NOT RUN", (
        f"a fold count of \"2\" evaluated {numeric_string.status.value}"
    )
    assert numeric_string.computed_value is None

    as_float = overfit_06(walk_forward_validation_folds_count=2.0)
    assert as_float.status.value == "NOT RUN", (
        f"a fold count of 2.0 evaluated {as_float.status.value}"
    )

    as_bool = overfit_06(walk_forward_validation_folds_count=True)
    assert as_bool.status.value == "NOT RUN", f"a fold count of True evaluated {as_bool.status.value}"

    genuine = overfit_06(walk_forward_validation_folds_count=2)
    assert genuine.status.value == "PASS", genuine.evidence
    assert genuine.computed_value == "1.0000"

    one = overfit_06(walk_forward_validation_folds_count=1)
    assert one.status.value == "NOT RUN", one.evidence


PROBES: Dict[str, Callable[[], None]] = {
    "N-148": probe_n148,
    "N-149": probe_n149,
    "N-150": probe_n150,
    "N-151": probe_n151,
    "N-152": probe_n152,
    "N-153": probe_n153,
    "N-154": probe_n154,
    "N-156": probe_n156,
    "N-157": probe_n157,
    "N-158": probe_n158,
    "N-159": probe_n159,
    "N-160": probe_n160,
    "N-161": probe_n161,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one audit finding's acceptance probe")
    parser.add_argument("finding_id", nargs="?", help="Finding id, e.g. N-148")
    parser.add_argument("--list", action="store_true", help="List probe ids")
    args = parser.parse_args()

    if args.list:
        print("\n".join(sorted(PROBES)))
        return 0

    if not args.finding_id:
        parser.error("a finding id is required (or pass --list)")
    probe = PROBES.get(args.finding_id)
    if probe is None:
        print(f"FAIL {args.finding_id}: no probe registered")
        return 1
    try:
        probe()
    except AssertionError as exc:
        print(f"FAIL {args.finding_id}: {exc}")
        return 1
    print(f"PASS {args.finding_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
