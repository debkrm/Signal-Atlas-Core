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
import ast
import csv
import io
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, Optional

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
    # §90.7 Ruling 1: 324 is the measured count of *post-2022* boundaries as committed, not a frozen
    # numeral. §90.9 item 3 extended the log backward over the 931 warm-up sessions and measured 102
    # new boundaries (324 -> 426), each dated at its successor ISIN's first session and none of them
    # at the 2022-01-03 seam. The invariant is per pair, so both counts are asserted: the post-2022
    # tuples must all survive, and the total must equal the count this round disclosed.
    post_2022 = [pair for pair in pairs if pair[3] >= datetime.date(2022, 1, 3)]
    assert len(post_2022) == 324, (
        f"{len(post_2022)} post-2022 identity pair(s) survive, not the 324 committed at `fb02eea` "
    )
    assert len(pairs) == 426, (
        f"{len(pairs)} adjacent identity pair(s); §90.9 item 3 measured 426 (324 post-2022 + 102 warm-up)"
    )
    assert validate_documented_transition_dates(intervals, actions) == 426, (
        "not every one of the 426 pairs is dated at a documented ISIN_TRANSITION"
    )

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

    # An uncommitted source change is not certifiable by a recorded tree: every path git reports is in the
    # dirty set, and the gate runs the heavy checks instead of reusing a row (and refuses to record one).
    # The implication is asserted rather than equality, and no content is compared for a dirty path, so the
    # measurement does not depend on how much dirt a working copy holds: an untracked file has no blob in
    # HEAD (§82.6 / N-166), and a Linux checkout reports mode-only changes whose bytes equal the blob.
    reported = {
        entry.decode("utf-8")[3:]
        for entry in git(
            "status", "--porcelain", "-z", "--untracked-files=all", "--no-renames"
        ).split(b"\x00")
        if entry
    }
    dirty = dirty_source_paths()
    assert set(p for p in reported if is_source_tree_path(p)) <= set(dirty), (dirty, reported)
    assert not any(rel.endswith("/") for rel in dirty), f"a directory is in the dirty set: {dirty}"

    # The digest is composed of the object ids git stores, so a checkout cannot move it. Measured
    # unconditionally on a clean text path, so the check has teeth on an LF checkout (Ubuntu CI) as well as
    # on a CRLF one: the bytes may differ by line endings and the oid is still the blob's.
    text_paths = [
        rel for rel in sorted(entries)
        if rel not in set(dirty)
        and rel.endswith((".py", ".yaml", ".yml", ".json", ".jsonl", ".md"))
    ]
    assert text_paths, "no clean text source file to measure"
    representative = text_paths[0]
    blob = git("cat-file", "blob", f"HEAD:{representative}")
    disk = (REPO_ROOT / representative).read_bytes()
    assert disk.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n"), (
        f"{representative} differs from its committed blob by more than line endings"
    )
    assert entries[representative] == git("rev-parse", f"HEAD:{representative}").decode().strip(), (
        f"{representative} does not hash to the blob oid it was committed as"
    )

    # Where the checkout does hold CRLF for a blob git stored with LF, the two differ on disk and the entry
    # is still the blob's oid -- that is the property the digest relies on. A checkout with no CRLF at all
    # (every Linux run) has no such example and needs none: the measurement above stands in its place, and
    # byte inequality is never asserted as an invariant of a platform.
    for rel in text_paths:
        disk = (REPO_ROOT / rel).read_bytes()
        if b"\r\n" not in disk:
            continue
        blob = git("cat-file", "blob", f"HEAD:{rel}")
        if disk == blob:
            continue
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
    plan, used, _reason = select_gate_plan(
        head_hash, [healthy], now, head_commit=head, verifier_scripts=verifiers
    )
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
        forged_hash, [record(forged_hash)], now, head_commit=head, verifier_scripts=verifiers
    )
    assert plan == "full" and used is None

    # A row hashes one tree and names one commit. Naming a commit whose tree is genuinely another is a
    # tree mismatch (N-160); naming a commit that merely shares this tree is a valid record that is
    # still not reusable here (N-162). The commit is decoded before it is used (N-164): an undecoded
    # `gate_sha` is refused earlier as a non-commit string, which is not the property under test.
    parent = git("rev-parse", f"{head}^").decode().strip()
    assert commit_exists(parent), f"HEAD's parent {parent!r} is not a commit in this repository"

    def commit_with_other_tree() -> str:
        for sha in git("rev-list", "-n", "40", head).decode().split()[1:]:
            if source_tree_hash_at_commit(sha) != head_hash:
                return sha
        raise AssertionError("no ancestor within 40 commits projects a different source tree")

    other = commit_with_other_tree()
    mismatch = green_record_problem(record(head_hash, gate_sha=other), verifiers, commit_exists)
    # Asserted separately from the reason it must carry, so the failure prints the measured value instead of
    # an empty message (§82.4 / §82.8 item 3).
    assert mismatch is not None, (
        f"a row naming {other[:8]}, whose tree is not this one, was accepted as evidence"
    )
    assert "is not the tree at gate_sha" in mismatch, mismatch

    undecoded = green_record_problem(
        record(head_hash, gate_sha=str(other.encode())), verifiers, commit_exists
    )
    assert undecoded is not None and "is not a commit" in undecoded, (
        f"an undecoded sha is no longer refused for the wrong reason: {undecoded}"
    )

    # A row recorded at another commit is not reusable at HEAD, whether or not the two share a tree.
    plan, used, reason = select_gate_plan(
        head_hash, [record(head_hash, gate_sha=parent)], now,
        head_commit=head, verifier_scripts=verifiers,
    )
    assert plan == "full" and used is None, reason

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


def probe_n162() -> None:
    """
    Reuse is keyed on the commit being verified, and an untracked source file forces the full run (N-162).

    At `80ff581` the plain gate printed `ALL REPOSITORY FOUNDATION GATES PASSED` with exit 0 while
    `python -m pytest -q` printed `1 failed, 533 passed`, because the row recorded at `742324c` was spent
    on a docs-only child whose source tree is identical: `select_gate_plan` took no commit. And
    `dirty_source_paths()` ran `git status --untracked-files=no`, so a failing untracked test never
    reached the reuse decision at all. Both halves are measured here against real commits and a real
    failing test file.
    """
    import datetime
    import os
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_MIN_SUITE_COUNT,
        GREEN_CACHE_SCHEME,
        dirty_source_paths,
        discovered_verification_scripts,
        select_gate_plan,
        should_record_green,
        source_tree_hash_at_commit,
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash, f"HEAD {head[:8]} projects no source tree"
    verifiers = discovered_verification_scripts()

    def record(tree_hash: str, gate_sha: str) -> dict:
        return {
            "source_tree_hash": tree_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": max(GREEN_CACHE_MIN_SUITE_COUNT, 534),
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": gate_sha,
        }

    # A second commit carrying HEAD's exact tree: the docs-only child that made `80ff581` red. It is a
    # real commit object, so the row names a commit the repository contains rather than a label.
    built = subprocess.run(
        ["git", "commit-tree", f"{head}^{{tree}}", "-p", head, "-m", "N-162 same-tree probe"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "GIT_AUTHOR_NAME": "probe", "GIT_AUTHOR_EMAIL": "probe@invalid",
             "GIT_COMMITTER_NAME": "probe", "GIT_COMMITTER_EMAIL": "probe@invalid"},
    )
    assert built.returncode == 0, built.stderr
    same_tree = built.stdout.strip()
    assert same_tree != head
    assert source_tree_hash_at_commit(same_tree) == head_hash, (
        f"the constructed commit {same_tree[:8]} does not share HEAD's source tree"
    )

    # Half one: that row projects this very tree and is still not spendable here — reuse is the commit.
    plan, used, reason = select_gate_plan(
        head_hash, [record(head_hash, same_tree)], now, head_commit=head, verifier_scripts=verifiers
    )
    assert plan == "full" and used is None, (
        f"a row recorded at {same_tree[:8]} was reused at HEAD {head[:8]}: {reason}"
    )

    # The identical row, naming HEAD, is reusable: the rule is the commit and not the tree alone.
    plan, used, _reason = select_gate_plan(
        head_hash, [record(head_hash, head)], now, head_commit=head, verifier_scripts=verifiers
    )
    assert plan == "reuse" and used is not None, "a row naming HEAD is no longer reusable"

    # Half two: a failing untracked test reaches the reuse decision, so the heavy gates run and the run
    # is not recorded. Without this the gate reports PASS on a tree whose suite is red.
    temp = REPO_ROOT / "tests" / "unit" / "test_n162_untracked_probe.py"
    rel = "tests/unit/test_n162_untracked_probe.py"
    assert not temp.exists(), f"{temp} already exists; remove it before running N-162"
    try:
        temp.write_text("def test_n162_untracked() -> None:\n    assert False\n", encoding="utf-8")
        dirty = dirty_source_paths()
        assert rel in dirty, (
            "an untracked source file is invisible to the dirty set, so the gate can reuse green "
            "over a failing untracked test"
        )
        assert should_record_green("full", True, 534, dirty) is False
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(temp)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert collected.returncode != 0, (
            f"the untracked probe test is not a failing test: {collected.stdout[-300:]}"
        )
    finally:
        temp.unlink()
    assert rel not in dirty_source_paths(), f"{rel} is still in the dirty set after removal"


def probe_n163() -> None:
    """
    The §80 cache test compares against a commit whose tree genuinely differs, not against `HEAD^` (N-163).

    At `80ff581` the docs-only commit shares its parent's source tree, so
    `test_n160_a_hand_written_hash_names_no_tree_and_is_refused` asserted that a row naming `HEAD^` must be
    refused while `HEAD^`'s tree projects the same digest: `assert None is not None`, and the audited commit
    was red at its own SHA. The test must depend on a divergent tree it selects, never on its own
    commit's parentage.
    """
    import subprocess

    path = REPO_ROOT / "tests" / "unit" / "test_phase3b2_audit_s80_items.py"
    source = path.read_text(encoding="utf-8")
    assert "HEAD^" not in source and "}^" not in source, (
        "the §80 cache test still derives its divergent commit from HEAD's parent, whose tree may be "
        "identical: the assertion then depends on the repository's parentage rather than on the cache"
    )
    assert "source_tree_hash_at_commit" in source, (
        "the §80 cache test no longer selects a commit by the tree it projects"
    )

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert run.returncode == 0, run.stdout[-1200:]


def probe_n164() -> None:
    """
    `probe_n160` compares trees, not strings: its parent sha is decoded before it is refused (N-164).

    `git()` in `probe_n160` returns bytes, so an undecoded `parent` is `b'742324…\n'` and
    `green_record_problem` refuses the row because that string `is not a commit in this repository` — not
    because the hash names another tree. The refusal reason is therefore measured on both shapes: the
    decoded commit is refused for its tree, the undecoded bytes are refused as a non-commit.
    """
    import inspect
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_SCHEME,
        commit_exists,
        compute_source_tree_hash,
        discovered_verification_scripts,
        green_record_problem,
        source_tree_entries,
        source_tree_hash_at_commit,
    )

    source = inspect.getsource(probe_n160)
    line = next((ln for ln in source.splitlines() if "parent = git(" in ln), "")
    assert line, "probe_n160 no longer derives a parent commit; re-measure N-164"
    assert ".decode()" in line, f"probe_n160 does not decode the parent sha: {line.strip()}"

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash
    verifiers = discovered_verification_scripts()

    entries = dict(source_tree_entries())
    poisoned = dict(entries)
    poisoned["tests/unit/test_verdicts.py"] = "0" * 40
    forged_hash = compute_source_tree_hash(list(poisoned.items()))
    assert forged_hash != head_hash

    def record(gate_sha) -> dict:
        return {
            "source_tree_hash": forged_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": 534,
            "verify_exits": {s: 0 for s in verifiers},
            "utc": "2026-11-17T10:00:00+00:00",
            "gate_sha": gate_sha,
        }

    # The decoded commit is refused because its tree is not the recorded hash: the property the probe
    # claims to test, and the one that needs no assumption about this commit's parentage.
    decoded = green_record_problem(record(head), verifiers, commit_exists)
    assert decoded is not None and "is not the tree at gate_sha" in str(decoded), (
        f"a row recording another tree still names a commit it is not refused for: {decoded}"
    )

    # The undecoded shape is refused earlier, as a string that names no commit. An assertion of the form
    # `problem is not None` therefore passes on the typing accident alone, which is the finding.
    undecoded = green_record_problem(record(str(head.encode())), verifiers, commit_exists)
    assert undecoded is not None and "is not a commit" in str(undecoded), (
        f"an undecoded sha is no longer refused for the wrong reason: {undecoded}"
    )
    assert "is not the tree at gate_sha" not in str(undecoded)


def probe_n165() -> None:
    """
    A pytest-collected file hidden from git is dirty state, so no green run certifies it (N-165).

    `git status` never reports an ignored path, and the cheapest ignore rule needs no tracked edit:
    `.git/info/exclude` (or a global `core.excludesFile`) hides a new test file from git while pytest still
    collects it. `dirty_source_paths()` now asks for ignored paths (``--ignored=matching``) and keeps the
    `.py` files under the roots pytest collects from, so the forged row naming HEAD — §14.3's standing
    instrument, never written to the cache or the artefact — is refused by the same branch an edited file
    takes in main().
    """
    import datetime
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_SCHEME,
        dirty_source_paths,
        discovered_verification_scripts,
        select_gate_plan,
        should_record_green,
        source_tree_hash_at_commit,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    assert head, "HEAD resolves to no commit"
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash
    verifiers = discovered_verification_scripts()

    rel = "tests/unit/test_n165_ignored_probe.py"
    temp = REPO_ROOT / rel
    exclude = REPO_ROOT / ".git" / "info" / "exclude"
    assert not temp.exists(), f"{temp} already exists; remove it before running N-165"
    original = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text(original + ("" if original.endswith("\n") else "\n") + rel + "\n", encoding="utf-8")
        temp.write_text("def test_n165_ignored() -> None:\n    assert False\n", encoding="utf-8")

        # git does not report it, so the gate's only view of the working copy is empty.
        status = subprocess.run(
            ["git", "status", "--porcelain", "--no-renames"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        assert rel not in status, f"git status reports the ignored file: {status}"
        dirty = dirty_source_paths()
        assert rel in dirty, (
            f"an ignored-but-collected test file is still invisible to the dirty set ({dirty}), so the gate "
            f"can certify a red suite as green"
        )
        # The gate fails closed on it by the same rule as any other uncommitted source path: the heavy gates
        # run and no row is written. main() only reaches select_gate_plan for a clean working copy.
        assert should_record_green("full", True, 536, dirty) is False

        # And pytest collects it as a failing test: the suite the gate would have certified as green is red.
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(temp)], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert collected.returncode != 0, (
            f"the ignored probe test is not collected or not failing: {collected.stdout[-300:]}"
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        forged = {
            "source_tree_hash": head_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": 536,
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": head,
        }
        # Positive control: the row itself is a valid hit, so what refuses it above is the hidden file and
        # not a broken fixture. A clean checkout takes this branch; this one does not.
        plan, used, reason = select_gate_plan(head_hash, [forged], now, head_commit=head)
        assert plan == "reuse" and used is not None, (
            f"the forged row is no longer a valid hit on a clean tree: {plan} — {reason}"
        )
    finally:
        temp.unlink(missing_ok=True)
        if original:
            exclude.write_text(original, encoding="utf-8")
        elif exclude.is_file():
            exclude.unlink()
    assert rel not in dirty_source_paths(), f"{rel} still dirty after cleanup"


def probe_n166() -> None:
    """
    An untracked source file does not change either ledger consumer's verdict (N-166).

    Including untracked paths in the dirty set (§81.4) made a working copy with one stray scratch file a
    state the two oldest consumers could not describe: `probe_n160` required an empty dirty set, and the §80
    tree test asked `git cat-file HEAD:<path>` for every dirty path, which raises for a path HEAD lacks. The
    gate failed closed through the dirty path, so the ledger reported a closed finding as broken while the
    finding was intact -- and a real regression would have hidden inside that noise. With one untracked file
    present, both consumers must pass and the gate must still refuse to reuse or record over it.
    """
    import subprocess

    from verify_audit_append_only import dirty_source_paths, should_record_green

    rel = "tests/unit/test_n166_untracked_probe.py"
    temp = REPO_ROOT / rel
    assert not temp.exists(), f"{temp} already exists; remove it before running N-166"
    try:
        temp.write_text("def test_n166_untracked() -> None:\n    assert False\n", encoding="utf-8")

        # The gate fails closed on the file: it is state, and a run over it is never recorded.
        dirty = dirty_source_paths()
        assert rel in dirty, f"an untracked source file is invisible to the dirty set: {dirty}"
        assert should_record_green("full", True, 536, dirty) is False

        # Consumer one: the ledger row for N-160, which described the tree instead of the row.
        ledger = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "probe_audit_findings.py"), "N-160"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert ledger.returncode == 0, (
            f"probe_n160 still fails over an unrelated untracked source file: "
            f"{(ledger.stdout or '').strip()[-300:]}"
        )
        assert (ledger.stdout or "").strip() == "PASS N-160", ledger.stdout[-300:]

        # Consumer two: the §80 tree test, which walked the dirty set and read each path out of HEAD.
        tree_test = subprocess.run(
            [
                sys.executable, "-m", "pytest", "-q",
                "tests/unit/test_phase3b2_audit_s80_items.py::test_n160_source_tree_hash_is_the_object_id_git_stores",
            ],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert tree_test.returncode == 0, (
            f"the tree test still fails over an untracked source file: {tree_test.stdout[-800:]}"
        )
    finally:
        temp.unlink(missing_ok=True)
    assert rel not in dirty_source_paths(), f"{rel} is still dirty after cleanup"


def probe_n167() -> None:
    """
    An ignored directory and an ignored rootdir `conftest.py` are dirty state (N-167).

    `git status --ignored=matching` reports an ignored directory once, as ``dir/``, and enumerates nothing
    inside it, and a rootdir `conftest.py` sits outside the roots pytest collects tests from -- yet pytest
    executes both, so a green run certified over them can be red. `dirty_source_paths()` enumerates the
    ignored `.py` files inside an ignored directory under a collected root (§83.6 item 1) and keeps an
    ignored rootdir `conftest.py`, so both shapes refuse reuse and recording the way an edited file does
    in main() (N-165).
    """
    import datetime
    import shutil
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_SCHEME,
        dirty_source_paths,
        discovered_verification_scripts,
        select_gate_plan,
        should_record_green,
        source_tree_hash_at_commit,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash
    verifiers = discovered_verification_scripts()
    # Relative to whatever this working copy already holds, never to an empty set: a probe that requires a
    # clean tree reports its own edit as a failure (§82.6 / N-166).
    baseline_dirty = dirty_source_paths()

    hidden_dir = "tests/unit/n167_hidden"
    hidden_test = f"{hidden_dir}/test_hidden.py"
    root_conftest = "conftest.py"
    exclude = REPO_ROOT / ".git" / "info" / "exclude"
    original = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    assert not (REPO_ROOT / hidden_dir).exists(), f"{hidden_dir} already exists"
    assert not (REPO_ROOT / root_conftest).exists(), f"{root_conftest} already exists"
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        rules = original + ("" if not original or original.endswith("\n") else "\n")
        exclude.write_text(rules + f"{hidden_dir}/\n{root_conftest}\n", encoding="utf-8")

        # Shape one: an ignored directory holding a collected failing test.
        (REPO_ROOT / hidden_dir).mkdir(parents=True)
        (REPO_ROOT / hidden_test).write_text(
            "def test_hidden() -> None:\n    assert False\n", encoding="utf-8"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--no-renames"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        assert hidden_dir not in status and "conftest" not in status, status
        dirty = dirty_source_paths()
        assert hidden_test in dirty, (
            f"an ignored directory under tests/ is still invisible to the dirty set ({dirty}), so a "
            f"collected test git does not enumerate can be certified green"
        )
        assert should_record_green("full", True, 536, dirty) is False, (
            "a run over an ignored collected directory would still be recorded as green"
        )
        # The refusal is the dirty set, not a recording rule that never fires: an empty set records.
        assert should_record_green("full", True, 536, []) is True
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", hidden_dir], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert collected.returncode != 0, (
            f"the ignored directory is not collected or not failing: {collected.stdout[-300:]}"
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        forged = {
            "source_tree_hash": head_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": 536,
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": head,
        }
        plan, used, reason = select_gate_plan(head_hash, [forged], now, head_commit=head)
        assert plan == "reuse" and used is not None, (
            f"the forged row is no longer a valid hit on a clean tree: {plan} — {reason}"
        )

        # Shape two: an ignored rootdir conftest.py, which pytest imports for every run below it.
        (REPO_ROOT / root_conftest).write_text(
            "def pytest_configure(config):\n    raise RuntimeError('n167 root conftest')\n",
            encoding="utf-8",
        )
        dirty = dirty_source_paths()
        assert root_conftest in dirty, (
            f"an ignored rootdir conftest.py is still invisible to the dirty set ({dirty}), so a run "
            f"pytest configures with it can be certified green"
        )
        assert should_record_green("full", True, 536, dirty) is False, (
            "a run over an ignored rootdir conftest.py would still be recorded as green"
        )
        run = subprocess.run(
            [
                sys.executable, "-m", "pytest", "-q",
                "tests/unit/test_phase3b2_audit_s80_items.py::"
                "test_n160_source_tree_hash_is_the_object_id_git_stores",
            ],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert run.returncode != 0, (
            f"the ignored conftest.py is not loaded by pytest: {run.stdout[-300:]}"
        )
    finally:
        shutil.rmtree(REPO_ROOT / hidden_dir, ignore_errors=True)
        (REPO_ROOT / root_conftest).unlink(missing_ok=True)
        if original:
            exclude.write_text(original, encoding="utf-8")
        elif exclude.is_file():
            exclude.unlink()
    assert not (REPO_ROOT / hidden_dir).exists(), f"{hidden_dir} still present after cleanup"
    assert not (REPO_ROOT / root_conftest).exists(), f"{root_conftest} still present after cleanup"
    after = dirty_source_paths()
    assert hidden_test not in after and root_conftest not in after, (
        f"an N-167 scratch path is still dirty after cleanup: {after}"
    )
    assert set(after) == set(baseline_dirty), (
        f"cleanup left the dirty set changed: {sorted(set(after) - set(baseline_dirty))}"
    )


def probe_n168() -> None:
    """
    An ignored rootdir pytest config is dirty state (N-168).

    `pytest.ini`, `tox.ini`, `setup.cfg` and `pyproject.toml` decide the rootdir, `addopts` and
    `testpaths`, so a local `.git/info/exclude` rule can point pytest at a different suite while
    `git status` reports a clean tree. A config file is neither a `.py` file under a collected root nor
    a `conftest.py`, so before §84.6 item 1 it reached no branch of `dirty_source_paths()` and the gate
    reused a green row over a suite pytest never ran (§84.4). The probe asserts the closure: the config
    is named in the dirty set, the recording decision refuses over it, and pytest executes it, so the
    refusal is not vacuous.
    """
    import datetime
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_SCHEME,
        dirty_source_paths,
        discovered_verification_scripts,
        select_gate_plan,
        should_record_green,
        source_tree_hash_at_commit,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash
    verifiers = discovered_verification_scripts()
    # Relative to whatever this working copy already holds, never to an empty set (N-166, §82.6).
    baseline_dirty = dirty_source_paths()

    config = "pytest.ini"
    collected_test = "tests/unit/test_phase3b2_audit_s80_items.py"
    deselected_test = "test_n160_source_tree_hash_is_the_object_id_git_stores"
    assert not (REPO_ROOT / config).exists(), f"{config} already exists: the probe would clobber it"
    exclude = REPO_ROOT / ".git" / "info" / "exclude"
    original = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""

    def collect() -> str:
        # No `-q` here or in the planted config: both configurations then print the collected test
        # tree, so the comparison is the same format on both sides.
        return subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", collected_test],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout

    before = collect()
    assert "deselected" not in before, f"the working copy already deselects tests: {before[-300:]}"
    collected_before = before.count("<Function ")
    assert collected_before > 1, f"the tracked file collects no tests: {before[-300:]}"
    assert deselected_test in before, (
        f"the tracked test this probe deselects is not collected, so the config would not hide it: "
        f"{before[-300:]}"
    )
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        rules = original + ("" if not original or original.endswith("\n") else "\n")
        exclude.write_text(rules + f"{config}\n", encoding="utf-8")
        (REPO_ROOT / config).write_text(
            '[pytest]\naddopts = -k "not test_n160_source_tree_hash"\n', encoding="utf-8"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--no-renames"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        assert config not in status, status
        dirty = dirty_source_paths()
        assert config in dirty, (
            f"an ignored rootdir pytest config is still invisible to the dirty set ({dirty}), so a "
            f"local exclude rule can point pytest at a different suite under a reused green row"
        )
        assert should_record_green("full", True, 536, dirty) is False, (
            "a run over an ignored rootdir pytest config would still be recorded as green"
        )
        # The refusal is the dirty set, not a recording rule that never fires: an empty set records.
        assert should_record_green("full", True, 536, []) is True
        # The config is executed, not inert: pytest collects a different suite, so the tree a record
        # would describe is not the tree pytest ran. That deselected suite still exits 0 with a count
        # the 500 floor accepts, which is why the dirty set -- not the exit status or the count -- is
        # the instrument: the gate refuses reuse and recording over the config as it does over an edit.
        after = collect()
        assert "deselected" in after, (
            f"the ignored pytest.ini does not change collection: {after[-300:]}"
        )
        assert deselected_test not in after, (
            f"pytest still collects {deselected_test}: the config did not deselect a tracked test"
        )
        assert after.count("<Function ") == collected_before - 1, (
            f"the ignored pytest.ini does not drop exactly one tracked test: {after[-300:]}"
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        forged = {
            "source_tree_hash": head_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": 536,
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": head,
        }
        # The forged row still looks like a hit to the reuse rule, and that is the point: the dirty set
        # is what keeps it from being consulted over a tree whose pytest config git calls clean.
        plan, used, reason = select_gate_plan(head_hash, [forged], now, head_commit=head)
        assert plan == "reuse" and used is not None, (
            f"the forged row is no longer a valid hit under an ignored pytest config: {plan} — {reason}"
        )
    finally:
        (REPO_ROOT / config).unlink(missing_ok=True)
        if original:
            exclude.write_text(original, encoding="utf-8")
        elif exclude.is_file():
            exclude.unlink()
    assert not (REPO_ROOT / config).exists(), f"{config} still present after cleanup"
    after_dirty = dirty_source_paths()
    assert config not in after_dirty, f"{config} is still dirty after cleanup: {after_dirty}"
    assert set(after_dirty) == set(baseline_dirty), (
        f"cleanup left the dirty set changed: {sorted(set(after_dirty) - set(baseline_dirty))}"
    )


def probe_n169() -> None:
    """
    An ignored legacy `.pytest.ini` is dirty state (N-169).

    pytest 8.3.4 still reads the deprecated `.pytest.ini` name, and it outranks nothing else: an ignored
    rootdir `.pytest.ini` adds `addopts` and deselects a tracked test while `git status` reports a clean
    tree. The §84.6 item 1 tuple named `pytest.ini`, `tox.ini`, `setup.cfg` and `pyproject.toml`, so this
    name reached no branch of `dirty_source_paths()` and the gate reused a green row over a suite pytest
    never ran (§85.3, N-169). §85.5 item 1 adds it beside them. The probe asserts the closure: the
    config is named in the dirty set, the recording decision refuses over it, and pytest executes it, so
    the refusal is not vacuous. Before the fix it exits 1 with "still invisible to the dirty set".
    """
    import datetime
    import subprocess

    from verify_audit_append_only import (
        GREEN_CACHE_SCHEME,
        dirty_source_paths,
        discovered_verification_scripts,
        select_gate_plan,
        should_record_green,
        source_tree_hash_at_commit,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_hash = source_tree_hash_at_commit(head)
    assert head_hash
    verifiers = discovered_verification_scripts()
    baseline_dirty = dirty_source_paths()

    config = ".pytest.ini"
    collected_test = "tests/unit/test_phase3b2_audit_s80_items.py"
    deselected_test = "test_n160_source_tree_hash_is_the_object_id_git_stores"
    assert not (REPO_ROOT / config).exists(), f"{config} already exists: the probe would clobber it"
    exclude = REPO_ROOT / ".git" / "info" / "exclude"
    original = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""

    def collect() -> str:
        return subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", collected_test],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout

    before = collect()
    assert "deselected" not in before, f"the working copy already deselects tests: {before[-300:]}"
    collected_before = before.count("<Function ")
    assert collected_before > 1, f"the tracked file collects no tests: {before[-300:]}"
    assert deselected_test in before, (
        f"the tracked test this probe deselects is not collected, so the config would not hide it: "
        f"{before[-300:]}"
    )
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        rules = original + ("" if not original or original.endswith("\n") else "\n")
        exclude.write_text(rules + f"{config}\n", encoding="utf-8")
        (REPO_ROOT / config).write_text(
            '[pytest]\naddopts = -k "not test_n160_source_tree_hash"\n', encoding="utf-8"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--no-renames"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        assert config not in status, status
        dirty = dirty_source_paths()
        assert config in dirty, (
            f"an ignored legacy .pytest.ini is still invisible to the dirty set ({dirty}), so a local "
            f"exclude rule can point pytest at a different suite under a reused green row"
        )
        assert should_record_green("full", True, 536, dirty) is False, (
            "a run over an ignored legacy .pytest.ini would still be recorded as green"
        )
        # The refusal is the dirty set, not a recording rule that never fires: an empty set records.
        assert should_record_green("full", True, 536, []) is True
        # The config is executed, not inert: pytest collects a different suite, so the tree a record
        # would describe is not the tree pytest ran. That deselected suite still exits 0 with a count
        # the 500 floor accepts, which is why the dirty set -- not the exit status or the count -- is
        # the instrument: the gate refuses reuse and recording over the config as it does over an edit.
        after = collect()
        assert "deselected" in after, (
            f"the ignored .pytest.ini does not change collection, so it is not the channel N-169 names: "
            f"{after[-300:]}"
        )
        assert deselected_test not in after, (
            f"pytest still collects {deselected_test}: the config did not deselect a tracked test"
        )
        assert after.count("<Function ") == collected_before - 1, (
            f"the ignored .pytest.ini does not drop exactly one tracked test: {after[-300:]}"
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        forged = {
            "source_tree_hash": head_hash,
            "source_tree_scheme": GREEN_CACHE_SCHEME,
            "suite_count": 536,
            "verify_exits": {script: 0 for script in verifiers},
            "utc": (now - datetime.timedelta(minutes=5)).isoformat(),
            "gate_sha": head,
        }
        # The forged row still looks like a hit to the reuse rule, and that is the point: the dirty set
        # is what keeps it from being consulted over a tree whose pytest config git calls clean.
        plan, used, reason = select_gate_plan(head_hash, [forged], now, head_commit=head)
        assert plan == "reuse" and used is not None, (
            f"the forged row is no longer a valid hit under an ignored .pytest.ini: {plan} — {reason}"
        )
    finally:
        (REPO_ROOT / config).unlink(missing_ok=True)
        if original:
            exclude.write_text(original, encoding="utf-8")
        elif exclude.is_file():
            exclude.unlink()
    assert not (REPO_ROOT / config).exists(), f"{config} still present after cleanup"
    after_dirty = dirty_source_paths()
    assert config not in after_dirty, f"{config} is still dirty after cleanup: {after_dirty}"
    assert set(after_dirty) == set(baseline_dirty), (
        f"cleanup left the dirty set changed: {sorted(set(after_dirty) - set(baseline_dirty))}"
    )


ARCHIVE_SUFFIXES = (".csv.zip", ".json.gz")


def _tracked_archives() -> List[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout
    return [path for path in out.split("\0") if path.endswith(ARCHIVE_SUFFIXES)]


def probe_n170() -> None:
    """
    Every tracked archive is stored and checked out as bytes (N-170).

    `.gitattributes` applied `text=auto eol=lf` to `*.csv.zip` / `*.json.gz`, and git auto-detected
    many of those containers as text, so a fresh clone rewrote their CRLF bytes on checkout and the
    green cache could never be reused ("24 source path(s) differ from HEAD"). The repair is an
    attribute decision, not a byte rewrite: the archives are marked `-text` and the object's own
    bytes are what a checkout materialises. The probe asserts both halves over every tracked
    archive -- no text/eol conversion is configured, and each working file hashes to its index
    object -- and that the repository is therefore clean. `git hash-object` reads the file as it
    sits on disk and applies no clean filter, so a conversion shows up as a digest mismatch here.
    """
    archives = _tracked_archives()
    assert archives, f"no tracked {' / '.join(ARCHIVE_SUFFIXES)} archive is present to measure"

    attrs = subprocess.run(
        ["git", "check-attr", "--stdin", "-z", "text"],
        cwd=str(REPO_ROOT), input="\0".join(archives), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    fields = attrs.stdout.split("\0")
    triples = [(fields[i], fields[i + 2]) for i in range(0, len(fields) - 2, 3) if fields[i]]
    converted = [path for path, value in triples if value != "unset"]
    assert not converted, (
        f"{len(converted)} tracked archive(s) still carry a text attribute, so a checkout rewrites "
        f"their bytes: {converted[:3]}"
    )

    index: Dict[str, str] = {}
    listing = subprocess.run(
        ["git", "ls-files", "-s", "-z"], cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout
    for record in listing.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        _mode, oid, _stage = meta.split()
        index[path] = oid

    worktree = subprocess.run(
        ["git", "hash-object", "--stdin-paths"], cwd=str(REPO_ROOT),
        input="\n".join(archives) + "\n", capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    hashes = worktree.stdout.split()
    assert len(hashes) == len(archives), (
        f"git hash-object returned {len(hashes)} digest(s) for {len(archives)} archive(s): "
        f"{worktree.stderr.strip()[:300]}"
    )
    mismatched = [path for path, digest in zip(archives, hashes) if index.get(path) != digest]
    assert not mismatched, (
        f"{len(mismatched)} archive(s) on disk are not the bytes git stored, so every fresh clone "
        f"reports them modified: {mismatched[:3]}"
    )
    # Scoped to archives on purpose: this probe measures the attribute decision, and the
    # whole-tree clean assertion is the green cache's job on a committed tree (verify_audit_append_only).
    from verify_audit_append_only import dirty_source_paths
    dirty_archives = [path for path in dirty_source_paths() if path.endswith(ARCHIVE_SUFFIXES)]
    assert not dirty_archives, (
        f"{len(dirty_archives)} archive(s) differ from their blobs, so a fresh clone reports them "
        f"modified: {dirty_archives[:3]}"
    )


def probe_n171() -> None:
    """
    The Bronze coverage certificate reconciles each archive's own TIMESTAMP, not only its row's label
    (N-171).

    At `df97173` `probe_pre2022_bronze_coverage.py` attested a session by the `session_date` its manifest
    row declared and the row's `sha256`/`byte_count` against the bytes, but it never opened the archive,
    so swapping `session_date` between two captured archives left it printing `COVERED — 931/931`, exit
    0, while each archive's own TIMESTAMP column still named the other session (§88.3). The certificate
    now reads that column, and this probe asserts the closure: on a copy of the committed manifest with
    two rows transposed the probe exits 1 naming both dates, and the committed corpus still prints
    `COVERED — 931/931`, exit 0. The archive-date reader itself is asserted on both files first, so a
    refusal cannot come from a broken fixture.
    """
    import contextlib
    import datetime
    import io
    import json
    import shutil
    import tempfile

    import probe_pre2022_bronze_coverage as bronze

    left = REPO_ROOT / "data" / "raw" / "2018" / "cm02APR2018bhav.csv.zip"
    right = REPO_ROOT / "data" / "raw" / "2018" / "cm03APR2018bhav.csv.zip"
    left_date, right_date = datetime.date(2018, 4, 2), datetime.date(2018, 4, 3)

    assert bronze.embedded_session_dates(left) == {left_date}, bronze.embedded_session_dates(left)
    assert bronze.embedded_session_dates(right) == {right_date}, bronze.embedded_session_dates(right)

    scratch = Path(tempfile.mkdtemp())
    try:
        tampered = scratch / "manifest.jsonl"
        shutil.copyfile(REPO_ROOT / "data" / "reference" / "manifest.jsonl", tampered)
        rows = [json.loads(line) for line in tampered.read_text(encoding="utf-8").splitlines() if line.strip()]
        swapped = 0
        for row in rows:
            # Only current rows are read by the certificate; superseded rows are history and carry no
            # label to certify (Audit §92.7 Ruling 1 appended one superseded row per archive).
            if row.get("is_current") is not True:
                continue
            if row.get("session_date") == left_date.isoformat():
                row["session_date"] = right_date.isoformat()
                swapped += 1
            elif row.get("session_date") == right_date.isoformat():
                row["session_date"] = left_date.isoformat()
                swapped += 1
        assert swapped == 2, f"expected to transpose 2 rows, transposed {swapped}"
        tampered.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        def run(manifest: Path) -> tuple:
            original_manifest = bronze.MANIFEST_PATH
            bronze.MANIFEST_PATH = manifest
            try:
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    code = bronze.main()
            finally:
                bronze.MANIFEST_PATH = original_manifest
            return code, captured.getvalue()

        transposed_code, transposed_output = run(tampered)
        assert transposed_code == 1, (
            "a corpus whose session_date labels are transposed between two archives is still certified: "
            f"{transposed_output.strip().splitlines()[-1] if transposed_output.strip() else '<no output>'}"
        )
        assert "carries its own session date(s)" in transposed_output, transposed_output[-600:]
        for expected in (left_date.isoformat(), right_date.isoformat()):
            assert expected in transposed_output, (
                f"the refusal does not name {expected}: {transposed_output[-600:]}"
            )

        # The same code on the committed manifest: the certificate still covers the corpus it certifies.
        committed_code, committed_output = run(REPO_ROOT / "data" / "reference" / "manifest.jsonl")
        assert committed_code == 0, committed_output[-600:]
        assert "COVERED" in committed_output and "931/931" in committed_output, committed_output[-600:]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def probe_n172() -> None:
    """
    The two-digit-year Bhavcopy branch refuses a year no archive can carry (N-172).

    `parse_bhavcopy_date` gained `%d-%b-%y` so the one 2020-2021 archive printed with a two-digit year
    parses, and Python's `%y` maps 00-68 to 2000-2068 and 69-99 to 1969-1999. Unbounded, `13-Jul-68`
    became 2068-07-13 — a date inside the sealed holdout era (§88.6). The branch is now bounded to the
    plausible 1990-2030 range and refuses by name; the archive that needs the branch, and the in-range
    years beside the bound, still parse to their own dates.
    """
    import datetime

    from signal_core.storage.ingest import BhavcopyIngestError, parse_bhavcopy_archive, parse_bhavcopy_date

    assert parse_bhavcopy_date("13-Jul-20") == datetime.date(2020, 7, 13)
    assert parse_bhavcopy_date("13-JUL-2020") == datetime.date(2020, 7, 13)
    assert parse_bhavcopy_date("13-Jul-99") == datetime.date(1999, 7, 13)
    assert parse_bhavcopy_date("31-Dec-30") == datetime.date(2030, 12, 31)

    for refused, guessed in (("13-Jul-68", "2068-07-13"), ("13-Jul-89", "1989-07-13"), ("01-Jan-31", "2031-01-01")):
        try:
            parsed = parse_bhavcopy_date(refused)
        except BhavcopyIngestError as exc:
            assert "Implausible two-digit year" in str(exc), str(exc)
            assert refused in str(exc) and guessed in str(exc), str(exc)
        else:
            raise AssertionError(
                f"{refused!r} is still accepted as {parsed.isoformat()}, so an unbounded `%y` century "
                f"can name a session inside the sealed holdout era"
            )

    archive = REPO_ROOT / "data" / "raw" / "2020" / "cm13JUL2020bhav.csv.zip"
    resolved, records = parse_bhavcopy_archive(
        archive, trade_date=datetime.date(2020, 7, 13), target_series=("EQ",),
    )
    assert resolved == datetime.date(2020, 7, 13), resolved
    assert len(records) == 1392, f"the archive parses to {len(records)} EQ record(s), not 1,392"

    # H-24 still holds beside the parser bound: the archive is only ever read for its own session.
    try:
        parse_bhavcopy_archive(archive, trade_date=datetime.date(2068, 7, 13))
    except BhavcopyIngestError as exc:
        assert "does not match partition date" in str(exc), str(exc)
    else:
        raise AssertionError("a 2020 archive parsed under a 2068 partition date: H-24 no longer contains this")


def probe_n173() -> None:
    """
    The replay-guard benchmark pools enough CPU work that its quantized clock can resolve it (N-173).

    At `2e7f51b` `test_n1_replay_guard_o1_lookup_and_bounded_memory` timed one 1,000-fill pass and one
    4,000-fill pass with `time.process_time()`, which steps in 15.625 ms units on Windows (§89.4). A
    1,000-fill loop inside half a tick measured 0.0 µs/fill, so the ratio guard's `max(per_fill_1k_us,
    1.0)` floor divided the 4,000-fill figure by 1.0: a 5 µs/fill implementation measured 3.91 and failed
    a *faster* guard. The test now sizes each measurement by `MIN_MEASURABLE_CPU_S` and `MAX_PASSES`, and
    this probe asserts the closure arithmetically at three clock resolutions — the host's own step, a
    15.625 ms step, and a 1 µs step — so the result does not depend on which machine runs it: the pooled
    instrument must read 5 µs/fill as a ratio near 1.0 everywhere, while the single-pass instrument must
    still show the ≥ 2.5 artifact on a coarse clock (the defect is reproduced, not assumed).
    """
    import math
    import time as _time

    source = (REPO_ROOT / "tests" / "unit" / "test_portfolio.py").read_text(encoding="utf-8")
    assert "MIN_MEASURABLE_CPU_S = 0.25" in source, (
        "the benchmark no longer sizes its measurement, so N-173's quantized single pass is back"
    )
    assert "MAX_PASSES = 20" in source, "the benchmark lost the cap that bounds its pooling cost"
    assert "time.process_time()" in source, "the benchmark left the contention-robust CPU clock"
    assert "max(per_fill_1k_us, 1.0)" in source, "the ratio guard no longer floors the 1k measurement"
    for ceiling in ("per_fill_1k_us < 250.0", "per_fill_4k_us < 250.0", "scaling_ratio < 2.5"):
        assert ceiling in source, f"the ceiling `{ceiling}` was removed or widened"

    min_cpu_s, max_passes = 0.25, 20
    true_per_fill_us = 5.0  # the implementation the finding says a coarse clock misreads

    def passes_for(fill_count: int) -> int:
        estimate_s = fill_count * true_per_fill_us * 1e-6
        if estimate_s >= min_cpu_s:
            return 1
        return min(max_passes, max(2, math.ceil(min_cpu_s / estimate_s)))

    def pooled_per_fill_us(fill_count: int, tick_s: float) -> float:
        passes = passes_for(fill_count)
        cpu_s = passes * fill_count * true_per_fill_us * 1e-6
        return round(cpu_s / tick_s) * tick_s / (passes * fill_count) * 1e6

    def single_pass_per_fill_us(fill_count: int, tick_s: float) -> float:
        return round(fill_count * true_per_fill_us * 1e-6 / tick_s) * tick_s / fill_count * 1e6

    # Sample the clock while burning CPU: spin until it advances, so one step is observable even when a
    # single sample per tick would otherwise make adjacent reads look constant.
    def time_to_tick_us() -> float:
        best = 0.0
        for _ in range(5):
            start = _time.process_time()
            wall = _time.perf_counter()
            while _time.process_time() == start:
                pass
            best = max(best, (_time.perf_counter() - wall) * 1e6)
        return best

    host_tick_us = time_to_tick_us()
    assert host_tick_us > 0.0, "process_time never advanced under a CPU-bound spin, so its step cannot be measured"

    for label, tick_us in (
        ("host", host_tick_us),
        ("15.625 ms", 15625.0),
        ("1 us", 1.0),
    ):
        tick_s = tick_us * 1e-6
        old_ratio = single_pass_per_fill_us(4000, tick_s) / max(single_pass_per_fill_us(1000, tick_s), 1.0)
        one_k = pooled_per_fill_us(1000, tick_s)
        four_k = pooled_per_fill_us(4000, tick_s)
        new_ratio = four_k / max(one_k, 1.0)
        assert new_ratio < 2.5, (
            f"on a {label} clock the pooled instrument reads a 5 us/fill guard as ratio {new_ratio:.2f}, "
            f"which the ceiling still refuses: {one_k:.2f}/{four_k:.2f} us per fill"
        )
        assert abs(one_k - true_per_fill_us) / true_per_fill_us <= 0.25, (
            f"on a {label} clock the pooled 1,000-fill figure reads {one_k:.2f} us/fill for a "
            f"{true_per_fill_us:.0f} us/fill guard, outside 25%"
        )
        if tick_us >= 1000.0:
            assert old_ratio >= 2.5, (
                f"on a {label} clock the single-pass instrument reads ratio {old_ratio:.2f}, so the "
                "defect N-173 describes does not reproduce and the closure proves nothing"
            )
        else:
            assert abs(old_ratio - 1.0) < 0.5, (
                f"on a {label} clock the single-pass instrument reads ratio {old_ratio:.2f} rather than "
                "the near-1.0 result that makes this defect host-bound"
            )


def probe_n174() -> None:
    """
    The replay guard's counter must see every access, not one dunder (N-174).

    Measured at `abf198f` (§91.4): the structural check added by §90.9 item 5 counts `__contains__`
    alone. Iterating an `OrderedDict` calls no dunder this class overrides, so with §90.3's per-fill
    scan installed the counter still reads exactly 1,000 lookups for 1,000 fills and the check passes
    while an `O(n)` loop runs on every fill; the timing ceilings caught that scan in 1 of 5 runs.

    This probe therefore requires the counter to instrument the iteration-shaped accessors
    (`__iter__`, `keys`, `values`, `items`), the subscript/length paths (`__getitem__`, `__len__`) and
    `__contains__`, and requires the test to assert that grading-shaped iteration stays at zero. The
    250 us / 2.5 ceilings are asserted unchanged in either direction (§12.4).
    """
    source = (REPO_ROOT / "tests" / "unit" / "test_portfolio.py").read_text(encoding="utf-8")
    for ceiling in ("per_fill_1k_us < 250.0", "per_fill_4k_us < 250.0", "scaling_ratio < 2.5"):
        assert ceiling in source, f"the ceiling `{ceiling}` was removed or widened"
    accessors = ("__contains__", "__iter__", "keys", "values", "items", "__getitem__", "__len__")
    missing = [token for token in accessors if f"def {token}" not in source]
    assert not missing, (
        f"the replay-guard counter does not instrument `{missing[0] if missing else '?'}`; iterating an "
        "OrderedDict calls no dunder `__contains__`, so a per-fill linear scan stays invisible (N-174)"
    )
    assert "CountingReplayGuard" in source and "iteration_accesses" in source, (
        "the replay guard's O(1) claim has no structural count of its non-membership accesses (N-174)"
    )


def probe_n175() -> None:
    """
    The interval table's series attribute agrees with the archives it derives from (N-175, CLOSED).

    Measured at `fb02eea` on six fixed sessions (2022-01-03, 2022-06-30, 2022-12-30, 2023-06-30,
    2023-12-29, 2024-06-28): 13,008 observations, 0 ISIN disagreements, 0 uncovered, and 1,356 series
    disagreements (10.4%) — every one of them a symbol whose single open-ended `EQ` row described
    sessions the exchange ran in `BE`, `BZ` or `SM`. The consequence was that of 1,336 ISIN-sessions
    that traded only trade-to-trade, 1,206 resolved to `EQ` through `SecurityMaster.resolve_symbol` —
    the exact value `walkforward.py:637` feeds to Gate G2C-3's `is_eligible` — and the same 1,206 were
    returned by `get_point_in_time_active_equities(..., series="EQ")`.

    Closure (§90.9 item 1) appended 7,989 restatement rows derived from the archives' own `SERIES`
    column across 1,419 `(isin, symbol)` chains, and resolved the log at load: the superseded rows stay
    in the artifact (§10.1) and only the active rows answer a lookup. The 1,336 denominator is kept
    unchanged, so a "correction" that also dropped trade-to-trade scrips from the comparison could not
    pass by shrinking the sample.
    """
    import datetime

    from signal_core.storage.ingest import parse_bhavcopy_archive
    from signal_core.storage.security_master import SecurityMaster, load_cash_universe_symbol_intervals

    sessions = (
        ("data/raw/2022/cm03JAN2022bhav.csv.zip", datetime.date(2022, 1, 3)),
        ("data/raw/2022/cm30JUN2022bhav.csv.zip", datetime.date(2022, 6, 30)),
        ("data/raw/2022/cm30DEC2022bhav.csv.zip", datetime.date(2022, 12, 30)),
        ("data/raw/2023/cm30JUN2023bhav.csv.zip", datetime.date(2023, 6, 30)),
        ("data/raw/2023/cm29DEC2023bhav.csv.zip", datetime.date(2023, 12, 29)),
        ("data/raw/2024/cm28JUN2024bhav.csv.zip", datetime.date(2024, 6, 28)),
    )
    from signal_core.research.pit_universe import (
        get_point_in_time_active_equities,
        load_cash_equity_symbol_intervals,
    )

    intervals = load_cash_equity_symbol_intervals()
    master = SecurityMaster(symbol_intervals=load_cash_universe_symbol_intervals())
    trade_to_trade = 0
    admitted = 0
    universe_admitted = 0
    for relative, session in sessions:
        _, records = parse_bhavcopy_archive(str(REPO_ROOT / relative), trade_date=session)
        observed = {record.isin for record in records if record.series in ("BE", "BZ") and record.isin}
        trade_to_trade += len(observed)
        for isin in observed:
            interval = master.resolve_symbol(isin, session)
            if interval is not None and interval.series == "EQ":
                admitted += 1
        eq_universe = set(get_point_in_time_active_equities(session, intervals, series="EQ"))
        universe_admitted += len(observed & eq_universe)

    assert trade_to_trade == 1336, (
        f"{trade_to_trade} trade-to-trade ISIN-session(s) in the six fixed archives, not the 1,336 "
        "this finding was measured on — the sample moved, so the comparison is not the one registered"
    )
    assert admitted == 0, (
        f"{admitted} of {trade_to_trade} trade-to-trade ISIN-session(s) still resolve to EQ through "
        "the security master; the table's series attribute is contradicted by its archives (N-175)"
    )
    assert universe_admitted == 0, (
        f"{universe_admitted} trade-to-trade ISIN-session(s) are still returned by "
        "get_point_in_time_active_equities(..., series='EQ'); the entry gate reads that universe (§13.1)"
    )


def probe_n176() -> None:
    """
    Gate COV-3's attribution must be computed and its load-bearing invariant asserted (N-176).

    Measured at `abf198f` (§91.5) from `data/reference/sec_list_20240116.csv` and the same session's
    `cm16JAN2024bhav.csv.zip`, independently of the gate: of the **1,174** in-scope EQ scrips that do
    not resolve to an ISIN, **933** have no row at all in the Bhavcopy, **224** traded in `BE`/`BZ` and
    **17** in `SM`; the gate printed `930` / `220` / `24` as literals, and the claim that matters —
    **0** scrips the Bhavcopy reports as `EQ` fail to resolve — was asserted in no code (§9.1).

    This probe now fails closed unless the literals are gone, the gate's printed split is the one it
    recomputed from the archive, and the zero-EQ-unresolved invariant is a hard assertion in the gate.
    """
    import contextlib
    import csv
    import datetime
    import importlib
    import io
    import re

    gate_source = (REPO_ROOT / "scripts" / "verify_cash_universe_coverage.py").read_text(encoding="utf-8")
    typed = ("930 untraded", "220 trading in BE", "24 in another non-EQ series")
    present = [token for token in typed if token in gate_source]
    assert not present, (
        f"Gate COV-3 still prints typed attribution literals ({present[0]!r}); the split must be the one "
        "it computed from the session's own Bhavcopy (N-176, §9.1)"
    )
    if 'attribution["eq_unresolved"] != 0' not in gate_source:
        raise AssertionError(
            "Gate COV-3 does not assert that 0 scrips the Bhavcopy reports as EQ fail to resolve; that "
            "is the invariant the attribution exists to support (N-176)"
        )

    from signal_core.storage.ingest import parse_bhavcopy_archive
    from signal_core.storage.security_master import (
        SecurityMaster,
        load_cash_universe_symbol_intervals,
    )

    session = datetime.date(2024, 1, 16)
    master = SecurityMaster(symbol_intervals=load_cash_universe_symbol_intervals())
    unresolved: List[str] = []
    with (REPO_ROOT / "data" / "reference" / "sec_list_20240116.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if (row.get("Series") or "EQ").strip().upper() != "EQ":
                continue
            symbol = (row.get("Symbol") or "").strip().upper()
            resolved = master.resolve_isin_by_symbol(symbol, session, series="EQ") if symbol else None
            if not resolved or len(resolved) != 12:
                unresolved.append(symbol)

    _, records = parse_bhavcopy_archive(
        str(REPO_ROOT / "data" / "raw" / "2024" / "cm16JAN2024bhav.csv.zip"), trade_date=session
    )
    series_by_symbol: Dict[str, set] = {}
    for record in records:
        series_by_symbol.setdefault(record.symbol, set()).add(record.series)

    untraded = sum(1 for symbol in unresolved if symbol not in series_by_symbol)
    eq_rows = sum(1 for symbol in unresolved if "EQ" in series_by_symbol.get(symbol, set()))
    trade_to_trade = sum(
        1
        for symbol in unresolved
        if series_by_symbol.get(symbol) and series_by_symbol[symbol] <= {"BE", "BZ"}
    )
    other_non_eq = len(unresolved) - untraded - eq_rows - trade_to_trade

    assert eq_rows == 0, (
        f"{eq_rows} scrip(s) the Bhavcopy reports as EQ on 2024-01-16 do not resolve to an ISIN; "
        "that is Gate COV-2's invariant, not an attribution footnote"
    )
    measured = (untraded, trade_to_trade, other_non_eq)
    assert measured == (933, 224, 17) and len(unresolved) == 1174, (
        f"the attribution measured here is {len(unresolved)} unresolved as {measured}, not the "
        "1,174 / 933 / 224 / 17 registered in §91.5; the archive moved, so the comparison is not the "
        "one this finding was measured on"
    )

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    gate = importlib.import_module("scripts.verify_cash_universe_coverage")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        passed = gate.verify_gate_cov3_series_partitioned_accounting()
    output = captured.getvalue()
    assert passed, "Gate COV-3 failed on the committed 2024-01-16 artifacts"
    match = re.search(
        r"(\d+)\s+unresolved EQ scrips on 2024-01-16: (\d+) untraded.*?(\d+) trading in BE(?:/BZ)? "
        r"and (\d+) in another non-EQ series",
        output,
        re.S,
    )
    assert match, (
        "Gate COV-3 does not print the attribution it computed; expected '<N> unresolved EQ scrips on "
        "2024-01-16: <u> untraded ... <t> trading in BE and <o> in another non-EQ series'"
    )
    printed = tuple(int(group) for group in match.groups())
    assert printed == (1174,) + measured, (
        f"Gate COV-3 prints {printed} but the Bhavcopy yields (1174, {untraded}, {trade_to_trade}, "
        f"{other_non_eq}); a printed split that disagrees with the archive is not an attribution (N-176)"
    )


def _session_loop_passthrough_problem(source: str) -> Optional[str]:
    """
    The named seam between the engine loop and the harness (Audit §93.7 item 2).

    §93.3 measured the §14.4 shape: a committed test bound the *harness* while the session loop's call
    was asserted by no test, so deleting `forced_exit_isins=tuple(sorted(forced_exits))` from
    `scripts/run_phase3b2_walkforward.py` left three tests passing and `probe_n177` at exit 0. A
    substring is the wrong instrument for that claim — it is satisfied by a comment, a dead branch or
    a call in a function nobody calls — so the call is parsed and its keyword argument is compared as
    an expression.

    Returns `None` when exactly the session loop's call passes `forced_exit_isins=tuple(sorted(
    forced_exits))`; otherwise a sentence naming what was found, so a probe failure says which half of
    the seam was cut.
    """
    tree = ast.parse(source)
    # Audit §94.6 item 5 (N-178): the keyword's expression is necessary and not sufficient. A call
    # wrapped in `if forced_exits is None:` still carries the exact expression and never executes, so
    # the ancestors are read too: the call must sit in the session loop, under no branch or handler
    # that the data does not control.
    parents: dict = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    calls = 0
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "execute_swing_strategy_session":
            continue
        calls += 1
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if "forced_exit_isins" not in keywords:
            found.append(f"line {node.lineno}: no forced_exit_isins keyword")
            continue
        rendered = ast.unparse(keywords["forced_exit_isins"])
        if rendered != "tuple(sorted(forced_exits))":
            found.append(f"line {node.lineno}: forced_exit_isins={rendered}")
            continue
        guards = []
        enclosing_function = None
        cursor = parents.get(id(node))
        while cursor is not None:
            if isinstance(cursor, (ast.If, ast.While, ast.Try)):
                guards.append(cursor)
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)) and enclosing_function is None:
                enclosing_function = cursor.name
            cursor = parents.get(id(cursor))
        if guards:
            innermost = guards[0]
            found.append(
                f"line {node.lineno}: the harness call sits under {type(innermost).__name__} control "
                f"flow, so the session loop does not reach it"
            )
            continue
        if enclosing_function != "run_phase3b2_walkforward":
            found.append(
                f"line {node.lineno}: the harness call sits in {enclosing_function!r}, not in the "
                f"walk-forward session loop"
            )
    if calls == 0:
        return "no call to execute_swing_strategy_session was found in the walk-forward script"
    if found:
        return (
            "the walk-forward session loop does not hand the hold bound's exits to the harness ("
            + "; ".join(found)
            + "), so a refused hold is never routed through the single execution path (§93.7 item 2)"
        )
    return None


def probe_n177() -> None:
    """
    The hold bound must have a production consumer, and a hold past it must be refused (N-177).

    Measured at `abf198f` (§91.6): the bound was declared in criteria model and unit-tested on
    `Position`, and no production path called it, so an engine run could carry a delivery position
    past 21 authoritative sessions in silence. This probe fails closed unless the single engine
    consults the bound and a synthetic over-bound hold is refused through the portfolio-level
    consumer — no direct `Position` call — with the readiness probe printing the refusal count.
    """
    source_root = REPO_ROOT / "src" / "signal_core"
    callers = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in source_root.rglob("*.py")
        if path.name != "position.py"
        and "require_within_hold_bound(" in path.read_text(encoding="utf-8")
    ]
    position_source = (source_root / "portfolio" / "position.py").read_text(encoding="utf-8")
    for token in ("def entry_date", "def holding_sessions", "def require_within_hold_bound"):
        assert token in position_source, f"the hold-bound model `{token}` was removed"
    assert callers, (
        "the hold bound still has no production consumer outside position.py; a simulated position "
        "can be carried past the bound in silence (N-177)"
    )
    walkforward_source = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    assert "require_hold_bounds(" in walkforward_source, (
        "the walk-forward session loop does not consult the hold bound; the production consumer is "
        "never reached by a run (N-177, §13.2)"
    )
    # Audit §93.7 item 2: §93.3 measured that this edge was asserted by nothing — removing the
    # passthrough left the seam tests green and this probe at exit 0. The call is parsed, and the
    # check is then run against the mutation the work order names, so a check that cannot fail is
    # itself a failure here (§14.4).
    problem = _session_loop_passthrough_problem(walkforward_source)
    assert problem is None, problem
    passthrough_line = "forced_exit_isins=tuple(sorted(forced_exits)),"
    stripped_source = "\n".join(
        line for line in walkforward_source.splitlines() if line.strip() != passthrough_line
    )
    assert stripped_source != walkforward_source, (
        f"`{passthrough_line}` is not a line of its own in the walk-forward script, so the mutation "
        f"this probe must refuse cannot be constructed (§93.7 item 2)"
    )
    mutation_problem = _session_loop_passthrough_problem(stripped_source)
    assert mutation_problem is not None, (
        "removing the forced_exit_isins passthrough from the session loop does not fail this probe, "
        "so the engine-to-harness edge is asserted by nothing (§93.7 item 2, §14.4)"
    )

    # Audit §92.10 item 4: a string in the script does not prove the seam is reachable, so the seam is
    # driven by a committed test — and that test is executed here, not merely named (§14.4).
    seam_test = REPO_ROOT / "tests" / "unit" / "test_phase3b2_audit_s93_items.py"
    assert seam_test.is_file(), (
        "the swing seam has no committed test; forced_exit_isins is exercised only by this probe "
        "(§92.10 item 4, N-177)"
    )
    seam_source = seam_test.read_text(encoding="utf-8")
    for token in ("forced_exit_isins=", "MAX_HOLD_BOUND_EXIT", "REJECTED_LOWER_CIRCUIT", "require_hold_bounds("):
        assert token in seam_source, (
            f"the committed seam test does not exercise `{token}`, so the hold-bound exit is not driven "
            f"through the harness by the suite (§92.10 item 4, N-177)"
        )
    seam_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(seam_test)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert seam_run.returncode == 0, (
        f"the committed seam test fails at the current tree: {seam_run.stdout[-2000:]}{seam_run.stderr[-2000:]}"
    )

    import datetime

    from signal_core.contracts.criteria import load_go_no_go_criteria
    from signal_core.contracts.order_types import (
        ExecutionFillResult,
        ExecutionOrder,
        FillStatus,
        OrderProduct,
        OrderSide,
        OrderType,
    )
    from signal_core.execution.costs import TransactionCostBreakdown
    from signal_core.portfolio.portfolio import Portfolio
    from signal_core.storage.calendar import load_anchored_nse_trading_calendar

    criteria = load_go_no_go_criteria()
    bound = criteria.max_hold_trading_sessions
    calendar = load_anchored_nse_trading_calendar()
    sessions = [s for s in calendar.sessions if s >= datetime.date(2024, 1, 1)]
    entry, past = sessions[0], sessions[bound]
    previous = calendar.sessions[calendar.sessions.index(entry) - 1]
    isin = "INE000A01001"

    portfolio = Portfolio(
        initial_capital=Decimal("1000000.00"), criteria=criteria, initial_date=entry
    )
    order = ExecutionOrder(
        instrument_id=isin,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        signal_date=previous,
        target_date=entry,
        order_type=OrderType.MARKET_ON_OPEN,
        order_id="N177_PROBE",
    )
    costs = TransactionCostBreakdown(
        trade_date=entry,
        side=OrderSide.BUY,
        product=OrderProduct.DELIVERY,
        quantity=10,
        price=Decimal("100.00"),
        gross_amount=Decimal("1000.00"),
        brokerage=Decimal("20.00"),
        stt=Decimal("1.00"),
        exchange_turnover_fee=Decimal("0.03"),
        ipft=Decimal("0.00"),
        sebi_turnover_fee=Decimal("0.00"),
        stamp_duty=Decimal("0.15"),
        gst=Decimal("3.60"),
        total_statutory_taxes=Decimal("4.78"),
        total_charges=Decimal("24.78"),
        net_cash_flow=Decimal("-1024.78"),
        effective_cost_bps=Decimal("247.8000"),
        circular_ref="N177_PROBE",
        disclosures=(),
    )
    fill = ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=entry,
        latency_sessions=1,
        filled_quantity=10,
        unfilled_quantity=0,
        executed_price=Decimal("100.00"),
        slippage=None,
        costs=costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id="N177_PROBE_FILL",
    )
    portfolio.process_fill(fill, enforce_risk_limits=False)
    inside = sessions[bound - 1]
    assert portfolio.require_hold_bounds(inside, bound, calendar) == {}, (
        "a hold one session inside the bound was refused, so the consumer cannot be measuring the "
        "bound at all (N-177)"
    )
    refusals = portfolio.require_hold_bounds(past, bound, calendar)
    assert len(refusals) == 1, (
        f"a synthetic position held {bound} authoritative sessions was not refused through the "
        f"portfolio-level consumer ({refusals!r}); N-177 is not closed"
    )
    assert "Hold bound refused" in next(iter(refusals.values())), (
        "the refusal does not name the hold bound, so it is not the refusal N-177 asks for"
    )

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.probe_pre2022_preconditions import check_a4

    hold_lines = [message for status, message in check_a4() if message.startswith("A4 max hold")]
    assert hold_lines, "the readiness probe prints no A4 max-hold line"
    assert any("refusals=" in line and "refusals=0" not in line for line in hold_lines), (
        f"the A4 max-hold line reports no measured refusal count: {hold_lines}"
    )


def _dead_guarded_harness_call(source: str) -> str:
    """
    The live harness call indented under a false condition, its keyword expression untouched.

    Audit §94.2 built this mutation at `0287aae`: wrapping the assignment and its keyword arguments in
    `if forced_exits is None:` leaves `_session_loop_passthrough_problem` looking at exactly the
    expression it requires, while the session loop never calls the harness at all.
    """
    lines = source.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().startswith("summary = execute_swing_strategy_session(")
        ),
        None,
    )
    assert start is not None, "the walk-forward script no longer assigns a harness summary"
    depth = 0
    end = None
    for index in range(start, len(lines)):
        depth += lines[index].count("(") - lines[index].count(")")
        if depth == 0 and index > start:
            end = index
            break
    assert end is not None, "the harness call does not close, so the dead-guard mutation cannot be built"
    block = ["    " + lines[index] for index in range(start, end + 1)]
    lines[start : end + 1] = ["        if forced_exits is None:"] + block
    return "\n".join(lines)


def probe_n178() -> None:
    """
    The engine-to-harness check must see a live call, not merely an expression (N-178).

    Measured at `0287aae` (Audit §94.2): `_session_loop_passthrough_problem` walks the module's AST and
    compares the `forced_exit_isins` keyword's unparsed expression. The call is therefore found wherever
    it is written, not where it is executed: indenting the live call under `if forced_exits is None:`
    leaves `PASS N-177` and four committed tests green while the loop hands the harness nothing.

    This probe asserts the defect as measured, so the reachability check the work order names — a run
    whose counters are non-zero, or an assertion that the call sits in the session loop — flips it to
    exit 1 and closes N-178.
    """
    source = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    assert _session_loop_passthrough_problem(source) is None, (
        "the committed session loop does not pass forced_exit_isins, so N-178's premise has changed"
    )
    guarded = _dead_guarded_harness_call(source)
    assert guarded != source
    problem = _session_loop_passthrough_problem(guarded)
    assert problem is not None, (
        "a guarded-but-present harness call is accepted, so reachability is still unasserted (N-178)"
    )
    assert "control flow" in problem, (
        f"the dead-guarded call is refused for another reason, so the reachability check is not what "
        f"caught it: {problem}"
    )


def probe_n179() -> None:
    """
    A superseded manifest row must survive its flip, and a deletion is not a divergence (N-179).

    Measured at `0287aae` (Audit §94.3): `superseded_archive_problems` compares each superseded row's
    six archive fields against its current row, so an edited `sha256`, `byte_count`, `source_url`,
    `retrieved_at`, `session_date` or `session_type` fails the certificate. It counts the rows it read
    and never compares that count to anything, so removing a superseded row entirely exits 0 at
    `COVERED — 931/931` with four tests passing.

    This probe asserts the defect as measured, so pinning the superseded-row count (or a digest over
    those rows) flips it to exit 1 and closes N-179.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.probe_pre2022_bronze_coverage import manifest_rows, superseded_row_problems

    rows = manifest_rows()
    problems, checked = superseded_row_problems(rows)
    assert problems == [], problems[:3]
    assert checked == 931, (
        f"the certificate checks {checked} superseded session row(s), not the 931 Audit §94.3 measured"
    )
    index = next(
        position
        for position, row in enumerate(rows)
        if row.get("session_date") and row.get("is_current") is not True
    )
    artifact = str(rows[index]["artifact"])
    trimmed = rows[:index] + rows[index + 1 :]
    problems_after, checked_after = superseded_row_problems(trimmed)
    assert checked_after == checked - 1, (
        f"deleting one superseded row changed the checked count by {checked - checked_after}, not 1"
    )
    assert problems_after, (
        "a deleted superseded manifest row is still invisible, so the count is not pinned (N-179)"
    )
    assert any(artifact in problem for problem in problems_after), (
        f"the refusal does not name the artifact whose superseded row was deleted: {problems_after[:2]}"
    )


def probe_n180() -> None:
    """
    The seq-10 registration path must write the fold specification its window implies (N-180).

    Measured at `0287aae` (Audit §94.4): `run_seq10_candidate._register` copies `partition`,
    `canonical_params`, `fold_spec_fingerprint`, `dataset_fingerprint` and `execution_config` from the
    last registry row (seq 9), while `probe_seq10_candidate` recomputes the fold the window implies.
    The two values differ — `FOLD-SPEC-V1-4b44a1f2…` against `FOLD-SPEC-V1-36a39987…` — so a row
    registered through the runner would be refused by its own certificate after the registry had
    already moved to N = 10.

    This probe asserts the defect as measured, so deriving the fold from the requested window flips it
    to exit 1 and closes N-180.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts import probe_seq10_candidate as certificate
    from scripts import run_seq10_candidate as runner

    source = (REPO_ROOT / "scripts" / "run_seq10_candidate.py").read_text(encoding="utf-8")
    assert 'fold_spec_fingerprint=template["fold_spec_fingerprint"]' not in source, (
        "the registration path still copies the previous row's fold specification, so a row registered "
        "through it is refused by its own certificate after N has moved (N-180)"
    )
    assert "seq10_fold_fingerprint(" in source, (
        "the registration path no longer states the fold specification it writes, so the row's fold is "
        "whatever the previous row carried (N-180)"
    )
    registered = runner.seq10_fold_fingerprint()
    expected = certificate._expected_fold_fingerprint()
    assert registered == expected, (
        f"the registration path writes {registered!r} while the certificate demands {expected!r}; the two "
        f"derivations of one window disagree (N-180)"
    )
    assert expected.startswith("FOLD-SPEC-V1-36a39987"), (
        f"the fold the expanded window implies is {expected!r}, not the value Audit §94.4 measured for "
        f"train 2018-04-01..2022-12-30 / test 2023-01-02..2023-12-31 (N-180)"
    )


_CORPUS_CACHE: Dict[str, object] = {}


def _corpus() -> dict:
    """The committed derived corpus, materialised once per probe process."""
    import gzip
    import json

    if "corpus" not in _CORPUS_CACHE:
        with gzip.open(
            REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz",
            "rt",
            encoding="utf-8",
        ) as handle:
            _CORPUS_CACHE["corpus"] = json.load(handle)
    return _CORPUS_CACHE["corpus"]  # type: ignore[return-value]


def _applied_actions():
    """Committed corporate-action rows a build may apply: not superseded, with an archive digest."""
    from signal_core.storage.security_master import load_corporate_actions

    return [row for row in load_corporate_actions() if not row.superseded and row.source_digest]


def probe_n181() -> None:
    """
    The universe is point-in-time, not a survivor panel (N-181, §95.6 Ruling 1, §6.1).

    Measured at 77fb043 (§95.5.5): `universe_by_date` was the identical 1,082-name list on all 1,425
    dates, 564 of the 1,646 names trading on the window's first session were deleted from every date,
    and 1,653 ISINs were excluded in total. A backtest over that panel cannot lose a name that died.
    """
    corpus = _corpus()
    by_date = corpus["universe_by_date"]
    dates = sorted(by_date)
    rule = str(corpus.get("universe_selection") or "")
    assert "POINT_IN_TIME_TRADED" in rule, (
        f"the corpus does not state a point-in-time rule, so its membership is an outcome rather than a "
        f"rule: {rule[:160]!r}"
    )
    assert "every session from" not in rule, (
        "the universe is still described by the full-span filter §95.5.5 measured as survivorship"
    )
    first_members = set(by_date[dates[0]])
    last_members = set(by_date[dates[-1]])
    assert first_members != last_members, (
        f"universe_by_date is the identical {len(first_members)}-name list on the first and last session, "
        f"which is the survivor panel Ruling 1 makes inadmissible"
    )
    members = set().union(*(set(v) for v in by_date.values()))
    assert len(members) > len(first_members), (
        f"the union of all dates ({len(members)}) is not larger than one date's membership "
        f"({len(first_members)}), so membership never changes"
    )
    # A name whose observations stop inside the window is absent after its last session and present before.
    prices = corpus["prices_by_instrument"]
    stopped = [
        isin for isin, bars in prices.items()
        if bars and bars[-1]["trade_date"] < dates[-1] and len(bars) > 20
    ]
    assert stopped, "no instrument stops trading inside the window, so the rule's other half is untested"
    sample = stopped[0]
    last_bar = prices[sample][-1]["trade_date"]
    assert sample in set(by_date[last_bar]), f"{sample} is absent on its own last trading session {last_bar}"
    after = [d for d in dates if d > last_bar]
    assert after and sample not in set(by_date[after[0]]), (
        f"{sample} stopped trading on {last_bar} but is still a universe member on {after[0]}"
    )


def probe_n182() -> None:
    """
    The 94 archive-attested price actions are applied, not merely known (N-182, §95.5.3, Ruling 2).

    Measured at 77fb043: 95 attested actions were absent from the table (94 `BONUS`, 1
    `CONSOLIDATION`), 44 of them on a panel ISIN, and the corpus charged 34 of those bonus drops as
    returns. Each example below therefore has to be applied *and* absent from the corpus's returns.
    """
    from decimal import Decimal

    applied = _applied_actions()
    corpus = _corpus()
    prices = corpus["prices_by_instrument"]
    examples = (
        ("SRF", "2021-10-13"), ("KKCL", "2021-12-16"), ("AARTIDRUGS", "2020-09-30"),
        ("MAHLIFE", "2021-09-14"), ("UNOMINDA", "2018-07-11"), ("INFIBEAM", "2021-03-18"),
        ("MMFL", "2018-07-18"), ("BIOCON", "2019-06-12"), ("GICRE", "2018-07-12"),
        ("GAIL", "2019-07-09"), ("GLAXO", "2018-09-11"), ("EPL", "2018-06-20"),
        ("NIACL", "2018-06-27"), ("WHEELS", "2018-08-08"),
    )
    by_symbol_date = {
        (row.symbol, row.ex_date.isoformat(), row.action_type.value): row
        for row in applied
    }
    missing = []
    # Symbols are reused and reassigned (§10.4), so a name the archive carried as INFIBEAM is the same
    # ISIN the table now carries as CCAVENUE.
    isin_by_symbol = {"INFIBEAM": "INE483S01020"}
    for symbol, day in examples:
        key = (symbol, day, "BONUS")
        if key in by_symbol_date:
            continue
        isin = isin_by_symbol.get(symbol)
        if isin and any(
            row.isin == isin and row.ex_date.isoformat() == day and row.action_type.value == "BONUS"
            for row in applied
        ):
            continue
        missing.append(f"{symbol} {day}")
    assert not missing, (
        f"{len(missing)} of the {len(examples)} bonus actions Audit §95.5.3 measured as missing is still "
        f"not applied with an archive digest: {missing}"
    )
    # The applied ratio has to actually reach the series: a 1:1 bonus halves the price, so the corpus's
    # return on the ex-date is ~0 rather than the ~-50% the unadjusted series carried.
    charged = []
    for symbol, day in examples:
        row = by_symbol_date.get((symbol, day, "BONUS")) or next(
            r for r in applied
            if r.isin == isin_by_symbol.get(symbol) and r.ex_date.isoformat() == day
        )
        bars = prices.get(row.isin) or []
        index = next((i for i, bar in enumerate(bars) if bar["trade_date"] == day), None)
        if index is None or index == 0:
            continue
        previous = Decimal(bars[index - 1]["close"])
        current = Decimal(bars[index]["close"])
        move = (current - previous) / previous
        if abs(move) > Decimal("0.25"):
            charged.append(f"{symbol} {day} r={move.quantize(Decimal('0.0001'))}")
    assert not charged, (
        f"{len(charged)} attested bonus(es) are in the table but not in the series, so the drop is still "
        f"charged as a return: {charged}"
    )


def probe_n183() -> None:
    """
    The INFY bonus is dated where the archive dates it (N-183, §95.5.4).

    Measured at 77fb043: the committed archive attests `exDate 04-Sep-2018`, `Bonus 1:1`, the table said
    2018-09-12, so the corpus left the real halving unadjusted (−0.4860) and fabricated +1.0234 eight
    sessions later — the only observation above +1.0 on the panel.
    """
    from decimal import Decimal

    from signal_core.storage.security_master import load_corporate_actions

    rows = load_corporate_actions()
    infy = [r for r in rows if r.isin == "INE009A01021" and r.action_type.value == "BONUS"]
    wrong = [r for r in infy if r.ex_date.isoformat() == "2018-09-12" and not r.superseded]
    assert not wrong, "the 2018-09-12 INFY bonus row is still live, so the corpus dates the action wrongly"
    right = [r for r in infy if r.ex_date.isoformat() == "2018-09-04" and not r.superseded and r.source_digest]
    assert right, "no attested, applied INFY bonus row exists at the archive's 2018-09-04 ex-date"

    bars = _corpus()["prices_by_instrument"].get("INE009A01021") or []
    by_date = {bar["trade_date"]: Decimal(bar["close"]) for bar in bars}
    dates = sorted(by_date)
    for day in ("2018-09-04", "2018-09-12"):
        index = dates.index(day)
        previous = by_date[dates[index - 1]]
        move = (by_date[day] - previous) / previous
        assert abs(move) < Decimal("0.10"), (
            f"INFY returns {move.quantize(Decimal('0.0001'))} on {day}; an adjusted series shows neither "
            f"the −0.4860 unadjusted halving nor the +1.0234 fabricated move §95.5.4 measured"
        )


def probe_n184() -> None:
    """
    The IDEA consolidation is resolved, not applied (N-184, §95.5.4, Ruling 2).

    Measured at 77fb043: no archive record of any price-side action for `INE669E01016` on or near
    2023-09-15 and no fall in the raw series, yet the corpus multiplied every earlier bar by 10 and
    printed −0.8927 for the last three months of the window.
    """
    from decimal import Decimal

    from signal_core.storage.security_master import load_corporate_actions

    live = [
        row for row in load_corporate_actions()
        if row.isin == "INE669E01016"
        and row.action_type.value == "CONSOLIDATION"
        and row.ex_date.isoformat() == "2023-09-15"
        and not row.superseded
    ]
    assert not live, "the unattested IDEA 2023-09-15 consolidation is still live"
    bars = _corpus()["prices_by_instrument"].get("INE669E01016") or []
    by_date = {bar["trade_date"]: Decimal(bar["close"]) for bar in bars}
    dates = sorted(by_date)
    index = dates.index("2023-09-15")
    previous = by_date[dates[index - 1]]
    move = (by_date["2023-09-15"] - previous) / previous
    assert abs(move) < Decimal("0.20"), (
        f"IDEA returns {move.quantize(Decimal('0.0001'))} on 2023-09-15, which is the fabricated "
        f"−0.8927 consolidation move §95.5.4 measured"
    )


def probe_n185() -> None:
    """
    A demerger is a typed consideration event and a held-position exit constraint (N-185, §95.10 item 5).

    Measured at 77fb043: the archive attests 32 demerger events, 28 on panel ISINs, and the table had no
    `DEMERGER` type at all, so a position held across one booked a −65%..−95% raw drop and credited the
    consideration nowhere.
    """
    from signal_core.storage.security_master import CorporateActionType, load_corporate_actions

    assert "DEMERGER" in {member.value for member in CorporateActionType}, (
        "no DEMERGER type exists, so no consideration event can be booked or constrained"
    )
    attested = [
        row for row in load_corporate_actions()
        if row.action_type is CorporateActionType.DEMERGER and row.source_digest and not row.superseded
    ]
    assert len(attested) >= 28, (
        f"{len(attested)} attested demerger row(s) are applied, fewer than the 28 §95.5.6 measured on the "
        f"panel"
    )
    loop = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    assert "DEMERGER_FORCED_EXIT" in loop, (
        "the session loop does not force a position out of a demerger ex-date, so a held position still "
        "realises the raw drop"
    )
    assert "forced_exit_reasons=forced_reasons" in loop, (
        "the loop does not pass the exit reason, so a demerger exit would be counted as a hold-bound exit"
    )
    harness = (REPO_ROOT / "src" / "signal_core" / "strategy" / "swing.py").read_text(encoding="utf-8")
    assert 'reasons.get(isin, "MAX_HOLD_BOUND_EXIT")' in harness, (
        "the harness ignores forced_exit_reasons, so a demerger exit carries no attributable reason"
    )


def probe_n186() -> None:
    """
    A committed payload's manifest must describe the bytes git stores, not the bytes a download left.

    Measured at ac16232 (§96.2): `data/raw/circulars/NSE_STT_RATES/manifest.json` asserts 330,003 bytes
    and sha256 5df41b04…, while `git cat-file blob HEAD:` for the same path yields 330,001 bytes and
    91e8ace7… — `.gitattributes` applied `* text=auto eol=lf` to the captured `.html`, so checkout
    rewrote its CRLF bytes and the attestation was a working-copy digest that refused on every clone.

    Closure direction (feat-s97): every one of the captured statutory payloads resolves to the blob git
    stores, the attributes forbid re-normalising a captured payload, and the four criteria interval rows
    that cite `NSE_STT_RATES` carry the digest of that stored payload.
    """
    import hashlib
    import json
    import subprocess

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.ingest_statutory_sources import SOURCES

    root = REPO_ROOT / "data" / "raw" / "circulars"
    declared = {source.ref: source for source in SOURCES}
    drifting = []
    checked = 0
    digests: dict = {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        payload = directory / manifest["filename"]
        rel = payload.relative_to(REPO_ROOT).as_posix()
        blob = subprocess.run(
            ["git", "cat-file", "blob", "HEAD:" + rel],
            cwd=str(REPO_ROOT), capture_output=True,
        ).stdout
        checked += 1
        digests[directory.name] = manifest["sha256"]
        if hashlib.sha256(blob).hexdigest() != manifest["sha256"] or len(blob) != manifest["byte_count"]:
            drifting.append(
                f"{directory.name} ({manifest['byte_count']} stated vs {len(blob)} stored; "
                f"{manifest['sha256'][:8]}.. vs {hashlib.sha256(blob).hexdigest()[:8]}..)"
            )
    assert checked == len(declared), (
        f"{checked} captured source(s) on disk against {len(declared)} the capture script declares"
    )
    assert not drifting, (
        "statutory manifest(s) do not describe the bytes git stores, so the attestation is a "
        "working-copy digest: " + "; ".join(drifting)
    )

    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "data/raw/circulars/*/** -text" in attributes, (
        "no attribute pins the captured statutory payloads to their own bytes, so a checkout can "
        "rewrite them again (§96.2)"
    )

    # The chain the finding names: four interval rows cite NSE_STT_RATES, and that digest must be the
    # stored payload's, not a second copy of a number that happens to match a working copy.
    from signal_core.contracts.criteria import load_go_no_go_criteria

    criteria = load_go_no_go_criteria()
    citing = [
        interval for interval in criteria.statutory_costs.statutory_rate_intervals
        if interval.source_ref == "NSE_STT_RATES"
    ]
    assert len(citing) == 4, f"{len(citing)} interval row(s) cite NSE_STT_RATES, not the 4 §96.2 measured"
    for interval in citing:
        assert interval.source_sha256 == digests["NSE_STT_RATES"], (
            f"{interval.component} from {interval.from_date} cites {interval.source_sha256[:8]}.., which "
            f"is not the stored payload's {digests['NSE_STT_RATES'][:8]}.."
        )


def probe_n187() -> None:
    """
    The class the corpus builder documents as fatal must actually fail the build.

    Measured at ac16232 (§96.4): `classify_extreme_moves` returned six `EX_DATE_MISMATCH` entries and
    `build` bound that list to `failures` and never read it, so the build exited 0 with the six
    published in the header. The six were also misclassified: each sat within ten sessions of an
    archive record that carries **no share ratio at all** (an Annual General Meeting), which cannot be a
    mis-dated adjustment and made the fatal class fire on noise.

    Closure direction (feat-s97): the near miss is a price-side action only, the build refuses a
    non-empty fatal list by name, and the committed corpus publishes 0.
    """
    import ast
    import datetime
    import gzip
    import json
    from decimal import Decimal

    source = (REPO_ROOT / "scripts" / "derive_2018_2023_corpus.py").read_text(encoding="utf-8")
    assert "This is the class that fails the build" in source, (
        "the builder no longer documents the ex-date-mismatch class as fatal; re-scope this finding"
    )

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.derive_2018_2023_corpus as builder
    from signal_core.contracts.price_bar import PriceBar

    # 1. The fatal gate exists, refuses the INFY shape by name, and accepts an empty list.
    gate = getattr(builder, "require_no_ex_date_mismatch", None)
    assert gate is not None, (
        "derive_2018_2023_corpus exposes no ex-date-mismatch gate, so `failures` is still published not read"
    )
    gate([])
    try:
        gate([("INE009A01021", "2018-09-04", "0.5000 but the archive attests an action on 2018-09-12")])
    except SystemExit as exc:
        message = str(exc)
        assert "INE009A01021" in message and "2018-09-04" in message, (
            f"the gate refuses without naming the ISIN and session: {message!r}"
        )
    else:
        raise AssertionError("a non-empty EX_DATE_MISMATCH list did not fail the build")

    # 2. `build_corpus` is the caller: the gate is reached with the classifier's own list.
    tree = ast.parse(source)
    callers = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "require_no_ex_date_mismatch"
        and any(getattr(arg, "id", "") == "failures" for arg in node.args)
    ]
    assert callers, (
        "no module-level call passes the classifier's `failures` list into the gate, so the build still "
        "exits 0 with the class published"
    )

    # 3. The near miss is a price-side action: an AGM within the window is not a mis-dated ratio, a
    #    bonus is. (The six §96.4 named sat on AGM rows, not on price-side rows.)
    def _bars(isin: str, closes: list) -> list:
        day = datetime.date(2022, 1, 3)
        return [
            PriceBar(
                instrument_id=isin, trade_date=day + datetime.timedelta(days=index),
                open=Decimal(value), high=Decimal(value), low=Decimal(value), close=Decimal(value),
                volume=1000, traded_value=Decimal("1000"),
            )
            for index, value in enumerate(closes)
        ]

    move_day = datetime.date(2022, 1, 8)
    prices = {"INE000000001": _bars("INE000000001", ["10", "10", "10", "10", "10", "5"])}
    synthetic_calendar = [datetime.date(2022, 1, 3) + datetime.timedelta(days=index) for index in range(6)]
    agm_only = {("INE000000001", datetime.date(2022, 1, 11)): [("OTHER", "Annual General Meeting", "d" * 64)]}
    failures_agm, diagnostics_agm = builder.classify_extreme_moves(
        prices, {}, agm_only, synthetic_calendar
    )
    assert failures_agm == [], (
        "a routine AGM within the mismatch window still makes a one-session move fatal: "
        f"{failures_agm}"
    )
    assert any(row[1] == move_day.isoformat() for row in diagnostics_agm["ratio_shaped_unattested"]), (
        "the move did not land in a published class at all; the classification changed shape"
    )
    bonus_near = {("INE000000001", datetime.date(2022, 1, 11)): [("BONUS", "Bonus 1:1", "d" * 64)]}
    failures_bonus, _ = builder.classify_extreme_moves(prices, {}, bonus_near, synthetic_calendar)
    assert len(failures_bonus) == 1 and failures_bonus[0][0] == "INE000000001", (
        "an archive-attested BONUS five sessions from the move is no longer the fatal class: "
        f"{failures_bonus}"
    )

    # 4. The committed corpus publishes the class at zero.
    with gzip.open(
        REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz", "rt", encoding="utf-8"
    ) as handle:
        corpus = json.load(handle)
    reconciliation = corpus["reconciliation"]
    assert reconciliation["ex_date_mismatch"] == 0, (
        f"the committed corpus still publishes {reconciliation['ex_date_mismatch']} ex-date mismatch(es), "
        "so a fatal class this size would fail its own build"
    )


def probe_n188() -> None:
    """
    The builder must fail closed on an archive-attested action the table does not carry.

    Measured at ac16232 (§96.4): withdrawing one attested row (SRF 2021-10-13) left
    `applied_actions` at `refusals == 0` — one fewer instrument adjusted and no refusal — while the
    archive still attested the event. The only completeness check in the repository was
    `attest_price_actions.reconcile()`, which no build path and no `verify_*.py` called.

    Closure direction (feat-s97): the build calls the reconciliation and refuses a gap by name; the
    SRF witness, withdrawn from a copy of the table, is still named.
    """
    import ast
    import datetime
    import json
    import tempfile
    from pathlib import Path

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.attest_price_actions as attestation_tool
    import scripts.derive_2018_2023_corpus as builder
    from signal_core.storage.security_master import load_corporate_actions

    # 1. The gate exists and refuses a named gap.
    gate = getattr(builder, "require_attested_actions_present", None)
    assert gate is not None, (
        "derive_2018_2023_corpus exposes no attested-action completeness gate, so the missing-set "
        "direction still has no consumer"
    )
    gate([])
    try:
        gate(["INE647A01010 2021-10-13 BONUS"])
    except SystemExit as exc:
        assert "INE647A01010" in str(exc) and "2021-10-13" in str(exc), (
            f"the gate refuses without naming the ISIN and ex-date: {exc!r}"
        )
    else:
        raise AssertionError("a non-empty attested-action gap did not fail the build")

    source = (REPO_ROOT / "scripts" / "derive_2018_2023_corpus.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    callers = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "require_attested_actions_present"
    ]
    assert callers, "the build never calls the completeness gate (§14.4: the check sits beside the build)"

    # 2. With the committed table the gap set is empty; withdrawing the witness row names it.
    assert builder.attested_actions_missing_from_table() == [], (
        f"the committed table already has gap(s): {builder.attested_actions_missing_from_table()[:3]}"
    )
    actions = list(load_corporate_actions())
    witnesses = [
        row for row in actions
        if not row.superseded and row.source_digest and row.symbol == "SRF"
        and row.ex_date == datetime.date(2021, 10, 13)
    ]
    assert witnesses, "the SRF 2021-10-13 witness row is gone; re-scope this finding"
    isin = witnesses[0].isin

    original_path = attestation_tool.ACTIONS_PATH
    with tempfile.TemporaryDirectory() as workspace:
        withdrawn = Path(workspace) / "corporate_actions.jsonl"
        kept = []
        for line in original_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if (
                str(row.get("isin")) == isin
                and str(row.get("ex_date"))[:10] == "2021-10-13"
                and str(row.get("action_type")) == "BONUS"
            ):
                continue
            kept.append(line)
        withdrawn.write_text("\n".join(kept) + "\n", encoding="utf-8")
        attestation_tool.ACTIONS_PATH = withdrawn
        try:
            gaps = builder.attested_actions_missing_from_table()
        finally:
            attestation_tool.ACTIONS_PATH = original_path
    assert any("INE647A01010" in gap and "2021-10-13" in gap for gap in gaps), (
        f"withdrawing the attested SRF row produced no named gap: {gaps}"
    )


def probe_n189() -> None:
    """
    A demerger refusal counter must count refused exits, not demerger events.

    Measured at ac16232 (§96.5): the seq-10 artifact reported `demerger_forced_exits` 0 and
    `demerger_forced_refusals` 66 over 1,425 sessions with 781 closed trades, and no closed trade
    carried a `DEMERGER_FORCED_EXIT` reason. `demerger_exits` is built from every action in the security
    master, not from open positions, while the harness skips an ISIN it does not hold — so an event on a
    name the book never owned was counted as a refused exit.

    Closure direction (feat-s97): the refusal is counted over held positions only, so an unheld event
    counts as nothing, a held event that fills counts as an exit and one that does not as a refusal.
    """
    import ast

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.run_phase3b2_walkforward as runner

    counter = getattr(runner, "count_forced_exit_outcomes", None)
    assert counter is not None, (
        "the walk-forward runner still counts forced exits without a held-position rule, so a demerger "
        "event on a name the book does not hold is a refused exit"
    )

    forced = {
        "HELD_AND_FILLED": "DEMERGER_FORCED_EXIT",
        "HELD_AND_REFUSED": "DEMERGER_FORCED_EXIT",
        "NOT_HELD": "DEMERGER_FORCED_EXIT",
        "HELD_UNDER_THE_BOUND": "MAX_HOLD_BOUND_EXIT",
    }
    held = {"HELD_AND_FILLED", "HELD_AND_REFUSED", "HELD_UNDER_THE_BOUND"}
    assert counter(forced, held, {"HELD_AND_FILLED"}, "DEMERGER_FORCED_EXIT") == (1, 1), (
        "one held fill and one held refusal must read (1 exit, 1 refusal)"
    )
    assert counter(forced, held, set(), "DEMERGER_FORCED_EXIT") == (0, 2), (
        "two held, none filled must read two refusals"
    )
    assert counter(forced, set(), set(), "DEMERGER_FORCED_EXIT") == (0, 0), (
        "a demerger event on an ISIN the book never held incremented a counter"
    )
    assert counter(forced, held, {"HELD_AND_FILLED"}, "MAX_HOLD_BOUND_EXIT") == (0, 1), (
        "the bound pair must still read the position it forced and the demerger's fill must not "
        "be attributed to it"
    )

    source = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    callers = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "count_forced_exit_outcomes"
    ]
    assert callers, (
        "the counter exists but no session loop calls it, so the demerger pair still counts events (§14.4)"
    )
    assert "demerger_exits - demerger_filled" not in source, (
        "the event-counting form `demerger_exits - demerger_filled` is still in the loop"
    )


def probe_n190() -> None:
    """
    A host-sensitive CPU budget must not decide the gate's verdict on an identical source tree.

    Measured at ac16232 (§96.1): `verify_audit_append_only --force-full` exited 1 because
    `test_n1_replay_guard_o1_lookup_and_bounded_memory` measured 265.62 µs/fill (then 253.90) against
    its 250.0 ceiling, while the same test passed 3/3 in ~2.5 s serially. The gate ran the suite with
    `-n auto --dist loadfile`, so the benchmark's per-fill CPU was measured beside every other worker on
    the host, and two of four heavy runs on one source tree failed while two passed.

    Closure direction (feat-s97): the timing benchmark is deselected from the parallel invocation and
    run in an invocation of its own with no worker beside it, and both ceilings are unchanged.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.verify_audit_append_only as gate

    isolated = tuple(getattr(gate, "ISOLATED_TIMING_TESTS", ()))
    assert isolated, (
        "the gate names no isolated timing test, so the replay-guard benchmark still measures per-fill "
        "CPU under the parallel suite (§96.1)"
    )
    benchmark = [node for node in isolated if "test_n1_replay_guard_o1_lookup_and_bounded_memory" in node]
    assert benchmark, f"the replay-guard benchmark is not in the isolated set: {isolated}"

    parallel = gate.pytest_command()
    for node in isolated:
        assert "--deselect" in parallel and node in parallel, (
            f"{node} is not deselected from the parallel invocation: {' '.join(parallel[1:])}"
        )

    serial = gate.serial_pytest_command()
    assert "-n" not in serial, (
        f"the isolated invocation still starts xdist workers: {' '.join(serial[1:])}"
    )
    for node in isolated:
        assert node in serial, f"{node} is not run by the isolated invocation"

    # The two invocations must be reconciled against the collection count, not against a literal: a
    # deselect that silently dropped a test would otherwise read green.
    source = (REPO_ROOT / "scripts" / "verify_audit_append_only.py").read_text(encoding="utf-8")
    assert "serial_pytest_command()" in source and "collect-only" in source, (
        "the gate does not reconcile its parallel and isolated invocations against the collected suite"
    )

    # Neither ceiling moved, and the structural counter N-174 added is still asserted.
    test = (REPO_ROOT / "tests" / "unit" / "test_portfolio.py").read_text(encoding="utf-8")
    for ceiling in (
        "assert per_fill_1k_us < 250.0",
        "assert per_fill_4k_us < 250.0",
        "assert scaling_ratio < 2.5",
    ):
        assert ceiling in test, f"the replay-guard ceiling moved or was removed: {ceiling!r}"


def probe_n191() -> None:
    """
    No cross-gap pair may enter the reconciliation as one session's return (§97.10 item 1).

    Measured at 437e0c4 (§97.3): `classify_extreme_moves` zipped `bars` with `bars[1:]` and called the
    quotient a one-session return without asking whether the two `trade_date`s are consecutive in
    `trading_dates`; 16,194 adjacent pairs straddled a calendar gap and 58 of its 832 extremes were
    computed across one. This probe asserts the closed state: the classifier takes the calendar, a
    gap-straddling pair is a gap record, and the committed corpus publishes **zero** extreme moves
    computed across a gap — 774 of 832, with the 58 published in `cross_gap_detail` instead.
    """
    import datetime
    import gzip
    import hashlib
    import inspect
    import json
    from decimal import Decimal

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.derive_2018_2023_corpus as builder
    from signal_core.contracts.price_bar import PriceBar

    signature = inspect.signature(builder.classify_extreme_moves)
    assert "trading_dates" in signature.parameters, (
        "the classifier takes no calendar, so an adjacent pair of surviving bars is still read as one "
        "session's return (§97.10 item 1)"
    )
    body = inspect.getsource(builder.classify_extreme_moves)
    assert "calendar_previous" in body, "the classifier does not look up the calendar-previous session"

    def _bar(day: datetime.date, close: str) -> PriceBar:
        return PriceBar(
            instrument_id="INE000000091", trade_date=day,
            open=Decimal(close), high=Decimal(close), low=Decimal(close), close=Decimal(close),
            volume=1000, traded_value=Decimal("1000"),
        )

    first = datetime.date(2022, 1, 3)
    synthetic_calendar = [first, datetime.date(2022, 1, 4), datetime.date(2022, 2, 3)]
    failures_gap, diagnostics_gap = builder.classify_extreme_moves(
        {"INE000000091": [_bar(first, "10"), _bar(datetime.date(2022, 2, 3), "5")]},
        {},
        {},
        synthetic_calendar,
    )
    assert failures_gap == [], f"a cross-gap pair still fails the build as a session move: {failures_gap}"
    assert diagnostics_gap["cross_gap_pairs"] == 1, diagnostics_gap["cross_gap_pairs"]
    assert [row[1] for row in diagnostics_gap["cross_gap_moves"]] == ["2022-02-03"], (
        f"the cross-gap pair is not published as a gap record: {diagnostics_gap['cross_gap_moves']}"
    )
    assert diagnostics_gap["ratio_shaped_unattested"] == [], (
        "a cross-gap pair still enters a one-session return class"
    )

    with gzip.open(REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz", "rt") as f:
        header = json.load(f)
    dates = header["trading_dates"]
    calendar_previous = {dates[index]: dates[index - 1] for index in range(1, len(dates))}
    gap_pairs = 0
    consecutive_extremes = 0
    across_gap = []
    for isin, bars in header["prices_by_instrument"].items():
        for previous, current in zip(bars, bars[1:]):
            is_consecutive = calendar_previous.get(current["trade_date"]) == previous["trade_date"]
            if not is_consecutive:
                gap_pairs += 1
            previous_close = Decimal(previous["close"])
            if previous_close <= 0:
                continue
            move = (Decimal(current["close"]) - previous_close) / previous_close
            if abs(move) <= Decimal("0.35"):
                continue
            if is_consecutive:
                consecutive_extremes += 1
            else:
                across_gap.append((isin, current["trade_date"]))

    reconciliation = header["reconciliation"]
    assert gap_pairs == 16194, f"cross-gap adjacent pairs moved: {gap_pairs} (was 16,194 at 437e0c4)"
    assert len(across_gap) == 58, f"cross-gap extreme moves moved: {len(across_gap)} (was 58 at 437e0c4)"
    assert reconciliation["cross_gap_pairs"] == gap_pairs, (
        f"the header publishes {reconciliation['cross_gap_pairs']} cross-gap pairs, recomputed {gap_pairs}"
    )
    assert reconciliation["cross_gap_extreme_moves"] == len(across_gap), (
        f"the header publishes {reconciliation['cross_gap_extreme_moves']} cross-gap extremes, "
        f"recomputed {len(across_gap)}"
    )
    published_gaps = {
        (row["isin"], row["session"]) for row in reconciliation["cross_gap_detail"]
    }
    assert published_gaps == set(across_gap), (
        f"the published gap records differ from the recomputed set by {len(published_gaps ^ set(across_gap))} row(s)"
    )
    in_classes = (
        reconciliation["explained_by_applied_row"]
        + reconciliation["explained_by_archive_record"]
        + reconciliation["no_ratio_match"]
        + reconciliation["ratio_shaped_unattested"]
    )
    assert in_classes == consecutive_extremes, (
        f"the classes account for {in_classes} moves but only {consecutive_extremes} are computed between "
        f"consecutive sessions; {in_classes - consecutive_extremes} cross-gap pair(s) still enter a return class"
    )
    for isin, day in (("INE251H01024", "2022-08-12"), ("INE784B01035", "2023-09-26")):
        assert (isin, day) in published_gaps, f"{isin} {day} is no longer a published gap record"
        assert not any(
            row["isin"] == isin and row["session"] == day
            for row in reconciliation["ratio_shaped_detail"]
        ), f"{isin} {day} is still published as a one-session ratio-shaped move"

    # --- §98.10 item 1: the gap must partition the feature layer, not only the reconciliation -------
    from signal_core.contracts.exchange_series import PriceSeriesContinuityValidator
    from signal_core.features.engine import (
        SubsegmentIndicatorEngine,
        feature_gap_boundaries,
        trailing_continuous_bars,
    )
    from signal_core.research.pit_universe import median_turnover_as_of

    partition_path = REPO_ROOT / "reports" / "analysis" / "s99" / "feature_gap_partition.json"
    assert partition_path.is_file(), (
        "no committed feature-gap partition: the 16,194 gap pairs still reach every rolling feature "
        "unannounced, so an EMA/ATR window still spans INE784B01035's hole (§6.3, §98.10 item 1)"
    )
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    calendar_dates = [datetime.date.fromisoformat(value) for value in dates]
    session_index = {session: position for position, session in enumerate(calendar_dates)}

    class _Dated:
        __slots__ = ("trade_date",)

        def __init__(self, trade_date) -> None:
            self.trade_date = trade_date

    digest = hashlib.sha256()
    recomputed_instruments = 0
    recomputed_missing = 0
    for isin in sorted(header["prices_by_instrument"]):
        light = [
            _Dated(datetime.date.fromisoformat(row["trade_date"]))
            for row in header["prices_by_instrument"][isin]
        ]
        boundaries = feature_gap_boundaries(calendar_dates, light)
        if not boundaries:
            continue
        recomputed_instruments += 1
        recomputed_missing += len(boundaries)
        for boundary in boundaries:
            digest.update(f"{isin}\x00{boundary.trade_date.isoformat()}\n".encode("utf-8"))
    assert partition["partition_fingerprint"] == "GAP-PTN-V1-" + digest.hexdigest(), (
        "the committed partition is not the one the committed corpus derives; a rolling feature reading it "
        "would warm up at boundaries the calendar does not have"
    )
    assert partition["instruments_with_gaps"] == recomputed_instruments, (
        f"the partition publishes {partition['instruments_with_gaps']} instrument(s) with a hole, "
        f"recomputed {recomputed_instruments}"
    )
    assert partition["unexplained_missing_sessions"] == recomputed_missing, (
        f"the partition publishes {partition['unexplained_missing_sessions']} missing session(s), "
        f"recomputed {recomputed_missing}"
    )
    assert recomputed_missing != partition["unexplained_missing_sessions"] + 1, (
        "a mutated boundary count is indistinguishable from the committed one"
    )
    assert partition["feature_values"]["values_across_gap"] == 0, (
        f"{partition['feature_values']['values_across_gap']} feature value(s) are computed across a gap"
    )

    lookbacks = {
        "sma_20": 20, "sma_50": 50, "ema_20": 20, "ema_50": 50, "ema_200": 200,
        "atr_14": 14, "rsi_14": 15, "rolling_high_20": 20, "rolling_low_20": 20,
        "rolling_high_50": 50, "rolling_low_50": 50, "mom_63": 64,
    }
    for isin in ("INE251H01024", "INE784B01035"):
        bars = [
            PriceBar(
                instrument_id=isin,
                trade_date=datetime.date.fromisoformat(row["trade_date"]),
                open=Decimal(row["open"]), high=Decimal(row["high"]),
                low=Decimal(row["low"]), close=Decimal(row["close"]),
                volume=int(row["volume"]), traded_value=Decimal(row["traded_value"]),
            )
            for row in header["prices_by_instrument"][isin]
        ]
        boundaries = feature_gap_boundaries(calendar_dates, bars)
        assert boundaries, f"{isin} carries no gap boundary, so this witness cannot test the partition"
        holes = {session_index[b.trade_date] for b in boundaries}
        segments = PriceSeriesContinuityValidator.partition_into_continuous_subsegments(
            expected_calendar_sessions=calendar_dates, actual_price_bars=bars
        )
        breaks = sum(1 for boundary in boundaries if boundary.sessions_since_previous_record == 1)
        assert len(segments) == breaks + 1, (
            f"{isin} has {breaks} contiguous hole(s) but {len(segments)} segment(s); the partition does "
            f"not break where the calendar does"
        )
        features = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(
            expected_calendar_sessions=calendar_dates, actual_price_bars=bars
        )
        by_date = {feature.trade_date: feature for feature in features}
        for segment in segments[1:]:
            first = by_date[segment[0].trade_date]
            for attribute in ("sma_20", "ema_20", "atr_14", "mom_63"):
                assert getattr(first, attribute) is None, (
                    f"{isin}: {attribute} is computed at {first.trade_date}, the first bar after a gap, so "
                    f"its window spans the {len(boundaries)} boundary(ies) (§6.3, §98.10 item 1)"
                )
        for feature in features:
            end = session_index[feature.trade_date]
            for attribute, lookback in lookbacks.items():
                if getattr(feature, attribute) is None:
                    continue
                start = end - lookback + 1
                assert not any(position in holes for position in range(start, end + 1)), (
                    f"{isin}: {attribute} at {feature.trade_date} rides a window that contains an "
                    f"UNEXPLAINED_MISSING_RECORD boundary (§6.3)"
                )
        bars_by_date = {bar.trade_date: bar for bar in bars}
        crossed = [
            session for session in calendar_dates
            if trailing_continuous_bars(calendar_dates, bars_by_date, session, 20, session_index) is not None
            and any(session_index[session] - k in holes for k in range(1, 21))
        ]
        assert not crossed, f"a 20-session window still spans a {isin} hole: {crossed[:3]}"
        first_hole = min(holes)
        as_of = next(
            session for session in calendar_dates
            if session_index[session] > first_hole and session in bars_by_date
        )
        assert trailing_continuous_bars(calendar_dates, bars_by_date, as_of, 20, session_index) is None, (
            f"a 20-session window ending {as_of} still reads across {isin}'s gap"
        )
        assert median_turnover_as_of(
            as_of, calendar_sessions=calendar_dates, bars_by_date=bars_by_date, lookback_sessions=20,
            session_index=session_index,
        ) is None, f"a T-1 median turnover is computed across {isin}'s gap"


def probe_n192() -> None:
    """
    Only a price-side archive record may explain a move (§97.10 item 2).

    Measured at 437e0c4 (§97.3): the exact-date branch admitted any non-`DIVIDEND` record before the ratio
    test, so 26 moves beyond ±35% sat on a date whose records carried no share ratio and one of them —
    `INE803A01027` 2019-09-16 at **+0.5000** under an `OTHER` (AGM) record — was filed as explained. This
    probe asserts the closed state: `explained_by_archive_record` is **0**, and that move is published as
    `RATIO_SHAPED_UNATTESTED` with `OTHER` named beside it.
    """
    import datetime
    import gzip
    import json
    from decimal import Decimal

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.derive_2018_2023_corpus as builder
    from signal_core.contracts.price_bar import PriceBar

    source = (REPO_ROOT / "scripts" / "derive_2018_2023_corpus.py").read_text(encoding="utf-8")
    assert "if non_dividend:" not in source, (
        "the exact-date exoneration branch still admits a record that carries no share ratio"
    )
    assert "any(kind in PRICE_SIDE_KINDS" in source, (
        "the exact-date exoneration is not restricted to price-side records; N-192 is open"
    )

    def _bar(day: datetime.date, close: str) -> PriceBar:
        return PriceBar(
            instrument_id="INE000000092", trade_date=day,
            open=Decimal(close), high=Decimal(close), low=Decimal(close), close=Decimal(close),
            volume=1000, traded_value=Decimal("1000"),
        )

    move_day = datetime.date(2022, 1, 4)
    prices = {"INE000000092": [_bar(datetime.date(2022, 1, 3), "10"), _bar(move_day, "5")]}
    calendar = [datetime.date(2022, 1, 3), move_day]
    agm_at_exact_date = {("INE000000092", move_day): [("OTHER", "Annual General Meeting", "d" * 64)]}
    failures_agm, diagnostics_agm = builder.classify_extreme_moves(
        prices, {}, agm_at_exact_date, calendar
    )
    assert failures_agm == [], f"an AGM at the exact date is still treated as a mis-dated ratio: {failures_agm}"
    assert diagnostics_agm["explained_archive"] == 0, (
        "an AGM at the exact date still exonerates the move without a diagnostic"
    )
    published = [row for row in diagnostics_agm["ratio_shaped_unattested"] if row[1] == move_day.isoformat()]
    assert published and published[0][3] == "OTHER", (
        f"the AGM-silenced move is not published with the record named: {diagnostics_agm}"
    )
    bonus_at_exact_date = {("INE000000092", move_day): [("BONUS", "Bonus 1:1", "d" * 64)]}
    _, diagnostics_bonus = builder.classify_extreme_moves(prices, {}, bonus_at_exact_date, calendar)
    assert diagnostics_bonus["explained_archive"] == 1, (
        "a price-side record at the exact date no longer explains the move"
    )

    with gzip.open(REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz", "rt") as f:
        header = json.load(f)
    reconciliation = header["reconciliation"]
    assert reconciliation["explained_by_archive_record"] == 0, (
        f"the committed corpus still files {reconciliation['explained_by_archive_record']} move(s) as "
        f"explained by an archive record"
    )
    witness = [
        row for row in reconciliation["ratio_shaped_detail"]
        if row["isin"] == "INE803A01027" and row["session"] == "2019-09-16"
    ]
    assert witness, "the INE803A01027 2019-09-16 witness is not published as an unattested ratio-shaped move"
    assert witness[0]["record"] == "OTHER", f"the witness does not name its record: {witness[0]}"
    assert witness[0]["return"] == "0.5000", f"the witness move changed: {witness[0]}"
    named = [row for row in reconciliation["ratio_shaped_detail"] if row["record"]]
    assert len(named) == 18, (
        f"{len(named)} ratio-shaped move(s) name a non-price-side record, expected the 18 measured in §98"
    )
    price_side = set(builder.PRICE_SIDE_KINDS)
    for row in named:
        assert not price_side & set(row["record"].split(",")), (
            f"a ratio-shaped move is still exonerated by a price-side record at its exact date: {row}"
        )


def probe_n193() -> None:
    """
    A certificate's stored criteria fingerprint must reconcile with the live one (§97.10 item 3).

    Measured at 437e0c4 (§97.7): the trial_010 pair and the s94 baseline cited `CRIT-FPR-V1-9ee0a88c…`
    while the live criteria computed `b2876d98…` under the same `criteria_version 1.1.16`, and no gate read
    a stored hash. This probe asserts the closed state: the live fingerprint is `535e47f5…` (the §98
    re-seal), every certificate reconciles through `probe_seq10_candidate.certificate_problem`, a
    restatement attests the executed hash as pin-only by recomputation, and a forged or missing
    restatement is refused **naming both hashes**.
    """
    import dataclasses
    import json

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.probe_seq10_candidate as certificate
    from signal_core.contracts.criteria import compute_criteria_fingerprint, load_go_no_go_criteria

    criteria = load_go_no_go_criteria()
    live = compute_criteria_fingerprint(criteria)
    assert criteria.version == "1.1.16", f"criteria_version moved to {criteria.version}; seq 10 is append-only"
    assert live == "CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470", (
        f"the live fingerprint moved: {live}"
    )

    restatement = json.loads(certificate.CRITERIA_RESTATEMENT.read_text(encoding="utf-8"))
    executed_pin = "MAN-FPR-V1-f5b1f1f12e62564a92b6a76719013d445f58d7b3b3e4d99e3441b5637b05af3a"
    executed = "CRIT-FPR-V1-9ee0a88c260d27fbe3ab13bb7c8c4c992e7d185986f28f5f803cf5db6db8634e"
    assert restatement["live_criteria_fingerprint"] == live
    entries = {row["artifact"]: row for row in restatement["certificates"]}
    stale_certificates = []
    for path in certificate.CERTIFICATES:
        relative = path.relative_to(REPO_ROOT).as_posix()
        problem_text = certificate.certificate_problem(path, live, criteria, restatement)
        assert problem_text is None, f"{relative}: {problem_text}"
        stored = json.loads(path.read_text(encoding="utf-8"))["criteria_fingerprint"]
        assert stored in (live, executed), f"{relative} cites an unexplained fingerprint {stored}"
        if stored != live:
            stale_certificates.append(path)
            assert entries[relative]["executed_criteria_fingerprint"] == stored
            assert entries[relative]["executed_manifest_fingerprint"] == executed_pin
    assert stale_certificates, "no certificate is stale, so this finding has nothing to attest"

    recomputed = compute_criteria_fingerprint(
        dataclasses.replace(criteria, expected_manifest_fingerprint=executed_pin)
    )
    assert recomputed == executed, (
        f"the restatement's pin does not reproduce the executed fingerprint: substituting {executed_pin} "
        f"yields {recomputed}"
    )
    stale = stale_certificates[0]
    without = certificate.certificate_problem(stale, live, criteria, None)
    assert without is not None and executed[:24] in without and live[:24] in without, (
        f"a stale certificate with no restatement is accepted or names one hash only: {without}"
    )
    forged = {
        **restatement,
        "certificates": [
            {**row, "executed_criteria_fingerprint": "CRIT-FPR-V1-forged"} for row in restatement["certificates"]
        ],
    }
    forged_problem = certificate.certificate_problem(stale, live, criteria, forged)
    assert forged_problem is not None, "a restatement with a forged executed fingerprint is accepted"
    forged_pin = {
        **restatement,
        "certificates": [
            {**row, "executed_manifest_fingerprint": "MAN-FPR-V1-forged"} for row in restatement["certificates"]
        ],
    }
    assert certificate.certificate_problem(stale, live, criteria, forged_pin) is not None, (
        "a restatement whose pin does not reproduce the executed fingerprint is accepted, so the mix is "
        "not attested as pin-only"
    )

    # §98.10 item 4: a scored trial now binds its criteria hash on the evaluation row itself.
    from signal_core.research.trials import TrialRegistry

    registry = TrialRegistry(certificate.REGISTRY_PATH)
    evaluations = [
        evaluation
        for evaluation in (registry.get_evaluation(row.trial_id) for row in registry.get_trials())
        if evaluation is not None
    ]
    bound = [row.criteria_fingerprint for row in evaluations if row.criteria_fingerprint]
    assert bound, (
        "no evaluation row carries a criteria_fingerprint: `1.1.16` still labels several criteria sets "
        "and the outcome rows do not say which one judged them (§98.10 item 4)"
    )
    assert set(bound) <= {live}, f"an evaluation row cites a criteria set the live criteria do not compute: {bound}"
    seq11 = registry.get_evaluation("TRIAL-PHASE3B2-LIQUIDITY-ATR-011")
    assert seq11 is not None and seq11.criteria_fingerprint == live, (
        "the seq-11 outcome row does not name the criteria it was scored under"
    )


def probe_n194() -> None:
    """
    The seq-10 demerger pair is restated by append, and the certificate refuses while it is unmeasured (§97.10 item 4).

    Measured at 437e0c4 (§97.5): both committed artifacts still publish `demerger_forced_exits 0` /
    `demerger_forced_refusals 66` from the event counter §97.5 replaced. This probe asserts the closed
    state: the artifacts are **not** edited (§10.1), a restatement names the pair it restates and the
    held-position measurement that replaces it, that measurement reproduces the artifact's own hold-bound
    counters through `probe_seq10_candidate.demerger_restatement_problem`, and a missing measurement is
    refused naming the published pair.
    """
    import json

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.probe_seq10_candidate as certificate

    published = {}
    for relative in (
        "reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json",
        "reports/analysis/s94/seq10_baseline_2018_2023_verdict.json",
    ):
        document = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
        published[relative] = (document["demerger_forced_exits"], document["demerger_forced_refusals"])
    assert set(published.values()) == {(0, 66)}, (
        f"an artifact was edited rather than restated (§10.1); it now reads {published}"
    )

    restatement = json.loads(certificate.DEMERGER_RESTATEMENT.read_text(encoding="utf-8"))
    assert (restatement["restated"]["demerger_forced_exits"], restatement["restated"]["demerger_forced_refusals"]) == (0, 66)
    measurement = restatement["measurement"]
    for key in ("demerger_forced_exits", "demerger_forced_refusals"):
        assert isinstance(measurement[key], int) and not isinstance(measurement[key], bool), (
            f"the restatement carries no computed `{key}`"
        )
    assert restatement["counter"].startswith("count_forced_exit_outcomes"), restatement["counter"]
    replay = restatement["replay"]
    assert replay["demerger_forced_exits"] == measurement["demerger_forced_exits"]
    assert replay["demerger_forced_refusals"] == measurement["demerger_forced_refusals"]

    artifact = json.loads(
        (REPO_ROOT / "reports" / "verdicts" / "trial_010" / "phase3b2_swing_baseline_2022_2024_verdict.json")
        .read_text(encoding="utf-8")
    )
    assert certificate.demerger_restatement_problem(artifact, restatement) is None
    assert replay["hold_bound_forced_exits"] == artifact["hold_bound_forced_exits"], (
        "the restatement's replay does not reproduce the artifact's hold-bound exits"
    )
    assert replay["hold_bound_refusals"] == artifact["hold_bound_refusals"], (
        "the restatement's replay does not reproduce the artifact's hold-bound refusals"
    )
    missing = certificate.demerger_restatement_problem(artifact, None)
    assert missing is not None and "0" in missing and "66" in missing, (
        f"an unmeasured published pair is accepted, or the refusal names no pair: {missing}"
    )
    empty = certificate.demerger_restatement_problem(artifact, {**restatement, "measurement": {}})
    assert empty is not None and "demerger_forced_exits" in empty, (
        f"a restatement with no measurement is accepted: {empty}"
    )
    stale = certificate.demerger_restatement_problem(
        {**artifact, "demerger_forced_refusals": 65}, restatement
    )
    assert stale is not None, "a restatement is accepted for a pair the artifact no longer publishes"
    # §98.10 item 2: the gate must compare the measurement with its own replay, not only type-check it.
    contradictory = {**restatement, "measurement": {"demerger_forced_exits": 7, "demerger_forced_refusals": 9}}
    contradiction = certificate.demerger_restatement_problem(artifact, contradictory)
    assert contradiction is not None and "replay" in contradiction, (
        f"a measurement of 7/9 beside its own 0/0 replay is accepted: {contradiction}"
    )
    replay_without_pair = {
        **restatement,
        "replay": {k: v for k, v in replay.items() if not k.startswith("demerger_")},
    }
    assert certificate.demerger_restatement_problem(artifact, replay_without_pair) is not None, (
        "a replay that omits the demerger pair is accepted, so the measurement is never compared"
    )


def probe_n195() -> None:
    """
    A status row must publish the profit factor its artifact computes (N-195, AGENTS.md §9.1).

    The fix-assertion for the closure of N-195. It no longer asserts that the defect is present: it
    reads the two profitability fields out of
    `reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json` and requires
    `CURRENT_STAGE_OF_WORK.md`'s seq-10 column to carry those digits, so the document cannot drift
    from the artifact it cites without this probe failing. `1.1178…` / `1.1773…` — the typed pair §99.7
    opened the finding on — are refused by name, and the probe still checks that no committed artifact,
    verdict or config produces either figure (a value that is sourced is not a defect).
    """
    import json
    from decimal import Decimal

    artifact = json.loads(
        (
            REPO_ROOT
            / "reports"
            / "verdicts"
            / "trial_010"
            / "phase3b2_swing_baseline_2022_2024_verdict.json"
        ).read_text(encoding="utf-8")
    )
    closed = str(Decimal(artifact["closed_only_profit_factor"]))
    liquidated = str(Decimal(artifact["liquidated_profit_factor"]))
    closed_trades = len(artifact["closed_trades"])
    # The artifact's own nine decimals are what the row must quote; nothing here is a typed literal.
    closed_digits = closed[:11]
    liquidated_digits = liquidated[:11]
    assert closed_digits == "1.058319814", closed
    assert liquidated_digits == "1.062288461", liquidated

    document = (REPO_ROOT / "CURRENT_STAGE_OF_WORK.md").read_text(encoding="utf-8")
    status_rows = [line for line in document.splitlines() if line.startswith("| Profit factor |")]
    assert len(status_rows) == 1, status_rows
    row = status_rows[0]
    assert closed_digits in row, (
        f"the seq-10 status row publishes {row!r} but the artifact computes closed-only profit factor "
        f"{closed} for its {closed_trades} closed round trips (N-195, AGENTS.md §9.1)"
    )
    liquidated_rows = [
        line for line in document.splitlines() if line.startswith("| Liquidated profit factor |")
    ]
    assert len(liquidated_rows) == 1, liquidated_rows
    assert liquidated_digits in liquidated_rows[0], (
        f"the liquidated profit-factor row publishes {liquidated_rows[0]!r} but the artifact computes "
        f"{liquidated} (N-195, AGENTS.md §9.1)"
    )
    for stale in ("1.1178", "1.1773"):
        assert stale not in row and stale not in liquidated_rows[0], (
            f"the seq-10 status row still publishes {stale}, which no committed artifact computes"
        )

    hits = [
        path.relative_to(REPO_ROOT).as_posix()
        for root in ("reports/verdicts", "reports/analysis", "configs")
        for path in (REPO_ROOT / root).rglob("*")
        if path.is_file()
        and path.suffix in {".json", ".jsonl", ".md", ".yaml", ".yml"}
        and "1.1178" in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert hits == [], f"a committed artifact publishes 1.1178 for seq 10, so the status row is sourced: {hits}"


def _seq12_source() -> str:
    return (REPO_ROOT / "scripts" / "run_seq12_candidate.py").read_text(encoding="utf-8")


def _seq12_artifact() -> dict:
    import json

    path = REPO_ROOT / "reports" / "analysis" / "s102" / "seq12_data_qa.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _seq12_constant(name: str):
    """A module-level literal in the seq-12 QA script, read from the source, not imported."""
    for node in ast.parse(_seq12_source()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        # `Decimal("-0.20")` is a call, not a literal: unwrap the single string argument.
                        value = node.value
                        if (
                            isinstance(value, ast.Call)
                            and isinstance(value.func, ast.Name)
                            and len(value.args) == 1
                            and isinstance(value.args[0], ast.Constant)
                        ):
                            return value.args[0].value
                        raise
    raise AssertionError(
        f"`{name}` is no longer a module-level literal in run_seq12_candidate.py; re-measure N-196/N-197"
    )


# The five rows §100.4 measured as level steps on a signal day, recomputed here from the corpus and
# the committed reference table rather than read out of the artifact.
SEQ12_LEVEL_STEP_ROWS = (
    ("INE006I01046", "2021-03-18", "ASTRAL"),
    ("INE116G01013", "2021-10-28", "VARDHACRLC"),
    ("INE341R01014", "2021-08-05", "DTIL"),
    ("INE492A01029", "2020-07-16", "HEUBACHIND"),
    ("INE949H01023", "2021-11-17", "MANINFRA"),
)


def seq12_level_step_rows() -> Dict[str, dict]:
    """Recompute the five level steps from the corpus and the committed corporate-action table."""
    import datetime
    import gzip
    import json
    from decimal import Decimal

    from run_seq12_candidate import _classify_drop, _load_corporate_actions

    with gzip.open(
        REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        corpus = json.load(handle)
    sessions = [datetime.date.fromisoformat(value) for value in corpus["trading_dates"]]
    index = {session: position for position, session in enumerate(sessions)}
    actions = _load_corporate_actions()
    out: Dict[str, dict] = {}
    for isin, session_iso, _symbol in SEQ12_LEVEL_STEP_ROWS:
        bars = {row["trade_date"]: row for row in corpus["prices_by_instrument"][isin]}
        session = datetime.date.fromisoformat(session_iso)
        position = index[session]
        previous = bars.get(sessions[position - 1].isoformat())
        assert previous is not None, f"{isin} {session_iso} has no calendar-previous bar"
        current = bars[session_iso]
        previous_close = Decimal(previous["close"])
        move = (Decimal(current["close"]) - previous_close) / previous_close
        opening_gap = (Decimal(current["open"]) - previous_close) / previous_close
        out[isin] = _classify_drop(isin, session, move, opening_gap, previous_close, actions)
    return out


def probe_n196() -> None:
    """
    An ex-dividend session reprices by the dividend, so a cash record on the exact ex-date is an
    attestation test (N-196). The fix-assertion: the test is the one stated in the script's docstring
    (0.5 % of the previous close, on the close or the opening price), HEUBACHIND's Rs 140 special
    dividend explains its 2020-07-16 level step, the three rows with no record anywhere stay
    unattested, and the stop list does not empty — §100.16 item 1 names that trap.
    """
    from decimal import Decimal

    from run_seq12_candidate import CASH_ADJUSTMENT_TOLERANCE

    assert CASH_ADJUSTMENT_TOLERANCE == Decimal("0.005"), (
        f"the cash-adjustment tolerance is {CASH_ADJUSTMENT_TOLERANCE}, not the 0.5 % the test states; "
        "widening it until the stop list empties is a failure, not a fix (N-196)"
    )
    rows = seq12_level_step_rows()

    heubachind = rows["INE492A01029"]
    assert heubachind["disposition"] == "ATTESTED_CASH_ADJUSTMENT", (
        f"HEUBACHIND 2020-07-16 is {heubachind['disposition']}: a Rs 140 dividend on a 563.30 close "
        "predicts 423.30 and the session closed 423.55 (N-196)"
    )
    tested = heubachind["cash_adjustment"]["tested"]
    assert tested and Decimal(tested[0]["close_residual"]) <= CASH_ADJUSTMENT_TOLERANCE, (
        f"the attested row publishes no reproducing residual: {tested}"
    )

    for isin in ("INE006I01046", "INE341R01014", "INE949H01023"):
        row = rows[isin]
        assert row["attested"] is False and row["shape"] == "LEVEL_STEP_AT_OPEN", (
            f"{isin} {row['signal_session']} is now {row['disposition']} / {row['shape']} with no "
            "corporate-action record in either archive; it may not be attested by a test that finds "
            "nothing (N-196)"
        )
        assert row["records_on_date"] == [] and row["records_near_date"] == [], row

    vardhacrlc = rows["INE116G01013"]
    assert vardhacrlc["attested"] is False and vardhacrlc["disposition"] == "UNATTESTED_CASH_MISMATCH", (
        f"VARDHACRLC 2021-10-28 is {vardhacrlc['disposition']}: its Rs 25 interim dividend predicts "
        "47.35 against a 56.60 close, 12.8 % away, so it does not reproduce the level at 0.5 % (N-196)"
    )
    unattested = [
        isin
        for isin, row in rows.items()
        if row["shape"] == "LEVEL_STEP_AT_OPEN" and row["attested"] is False
    ]
    assert unattested, "every row attested: a fix that empties the stop list is a failure, not a pass"

    # And the published count is the recomputed one, not a number typed beside it (§9.1).
    artifact = _seq12_artifact()
    published = [
        row
        for row in artifact["below_minus_20pct_one_day"]
        if row["shape"] == "LEVEL_STEP_AT_OPEN"
    ]
    asserted = [row for row in published if row["attested"] is False]
    assert artifact["unattested_level_steps_feeding_a_signal"] == len(unattested), (
        f"the artifact publishes {artifact['unattested_level_steps_feeding_a_signal']} unattested level "
        f"steps while the corpus recomputes {len(unattested)} (N-196, AGENTS.md §9.1)"
    )
    assert len(asserted) == len(unattested), (len(asserted), len(unattested))
    by_isin = {row["isin"]: row for row in published}
    for isin, recomputed in rows.items():
        if isin not in by_isin:
            continue
        assert by_isin[isin]["disposition"] == recomputed["disposition"], (
            f"{isin} is published as {by_isin[isin]['disposition']} and recomputes as "
            f"{recomputed['disposition']} (N-196)"
        )


def probe_n197() -> None:
    """
    The level step is now tested over the feature window, not only on the signal day (N-197).

    Three measurements: a fixture whose signal day is clean but whose T−100 bar is an unattested −15 %
    step yields no usable window; the artifact publishes the window count beside the signal-day count
    with a stated policy; and the published detail rows really do hold a step inside 200 sessions, with
    the gap recomputed from the corpus rather than trusted.
    """
    import datetime
    import gzip
    import json

    from run_seq12_candidate import InstrumentSeries

    from signal_core.contracts.price_bar import PriceBar

    # The fixture: 300 flat sessions with the open 15 % lower at T−100, and a clean signal day at T.
    calendar = [datetime.date(2020, 1, 1) + datetime.timedelta(days=offset) for offset in range(300)]
    bars = [
        PriceBar(
            instrument_id="INE000000001",
            trade_date=day,
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.00"),
            volume=1000,
            traded_value=Decimal("100000"),
        )
        for day in calendar
    ]
    step = bars[199]
    bars[199] = PriceBar(
        instrument_id=step.instrument_id,
        trade_date=step.trade_date,
        open=Decimal("85.00"),
        high=Decimal("100.00"),
        low=Decimal("84.00"),
        close=Decimal("100.00"),
        volume=1000,
        traded_value=Decimal("100000"),
    )
    series = InstrumentSeries(bars, calendar)
    graded = (bars[199].trade_date, Decimal("-0.1500"), "UNATTESTED_NO_RECORD")
    assert series.steps_in_lookback([graded], bars[299].trade_date), (
        "a 15 % unattested step at T−100 is outside the window the rule reads, so the QA would call that "
        "SMA(200) usable (N-197)"
    )

    artifact = _seq12_artifact()
    policy = artifact["feature_window_policy"]
    assert policy["window_sessions"] == 200 and policy["unattested_step_gap_threshold"] == "0.10", policy
    assert policy["consequence"] and policy["rule"], policy
    published = artifact["signals_with_an_unattested_level_step_in_lookback"]
    assert published > 0, "the window measurement is empty; re-measure it rather than publishing 0"
    assert (
        artifact["entry_signals_in_a_usable_feature_window"]
        == artifact["entry_signals"] - published
    ), "the usable set does not subtract the published window count"

    with gzip.open(
        REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        corpus = json.load(handle)
    checked = 0
    for row in artifact["signal_level_steps_in_lookback"][:25]:
        corpus_bars = corpus["prices_by_instrument"][row["isin"]]
        positions = {bar["trade_date"]: at for at, bar in enumerate(corpus_bars)}
        signal_at = positions[row["signal_session"]]
        for step_row in row["level_steps_in_lookback"]:
            step_at = positions[step_row["session"]]
            assert 0 <= signal_at - step_at < 200, (row["isin"], row["signal_session"], step_row)
            previous = Decimal(corpus_bars[step_at - 1]["close"])
            recomputed = (Decimal(corpus_bars[step_at]["open"]) - previous) / previous
            assert abs(recomputed) >= Decimal("0.10"), (row["isin"], step_row, recomputed)
            assert abs(recomputed - Decimal(step_row["opening_gap"])) < Decimal("0.0001"), (
                step_row,
                recomputed,
            )
            checked += 1
    assert checked, "no detail row was checked, so the published list is unverified"


def probe_n198() -> None:
    """
    The STOP is published as gating nothing, and that statement is the scan (N-198).

    The artifact names the code that reads it; there is none, it says so, and nothing outside `tests/`
    constructs the rule, so no execution path exists for the status to refuse. A reader added later
    makes the published list disagree with the recomputed one and this probe fails.
    """
    from run_seq12_candidate import artifact_consumers

    recomputed = artifact_consumers()
    artifact = _seq12_artifact()
    gated_by = artifact["gated_by"]
    assert gated_by["consumers"] == recomputed, (
        f"the artifact publishes consumers {gated_by['consumers']} and the scan finds {recomputed}"
    )
    assert gated_by["gates_execution"] is bool(recomputed), gated_by
    if not recomputed:
        assert "not a gate" in gated_by["statement"], gated_by["statement"]
    constructed = []
    for path in sorted((REPO_ROOT / "scripts").glob("*.py")) + sorted(
        (REPO_ROOT / "src").rglob("*.py")
    ):
        if path.name in ("run_seq12_candidate.py", "probe_audit_findings.py"):
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("class "):
                continue
            if "MeanReversionSwingStrategy(" in line:
                constructed.append(str(path.relative_to(REPO_ROOT)))
                break
    assert not constructed, (
        f"`MeanReversionSwingStrategy` is now constructed by {constructed}; if an execution path exists "
        "it must refuse on the artifact's STOP by name and this probe must assert that refusal (N-198)"
    )


def probe_n199() -> None:
    """
    An empty band partition reports NOT RUN, never 0 (N-199). The three categorical counters are
    `NOT RUN` exactly while no band is recorded and integers exactly when one is, so the biconditional
    holds in both directions.
    """
    band_dir = REPO_ROOT / "data" / "silver" / "price_bands"
    files = [p for p in band_dir.rglob("*") if p.is_file()] if band_dir.is_dir() else []
    locked = _seq12_artifact()["blocked_by_locked_session"]
    counters = ("at_lower_circuit", "at_upper_circuit", "banded_but_not_at_a_limit")
    if not files:
        for name in counters:
            assert locked[name] == "NOT RUN", (
                f"`{name}` publishes {locked[name]!r} while data/silver/price_bands holds 0 files: an "
                "empty partition makes that zero a property of the reader, not of the market (N-199)"
            )
        assert locked["price_band_partition"]["populated"] is False, locked["price_band_partition"]
        assert "NOT RUN" in _seq12_artifact()["not_run"]["exit_freeze_round_trip"], (
            "the exit freezes side is not reported as NOT RUN while no band exists"
        )
    else:
        for name in counters:
            assert isinstance(locked[name], int), (
                f"`data/silver/price_bands` holds {len(files)} file(s) but `{name}` is "
                f"{locked[name]!r}; re-measure the band counters against the populated partition"
            )


def probe_n200() -> None:
    """
    The "no record" verdict travels with the archive's coverage (N-200). The artifact publishes how
    much of the scanned set the Bronze archive covers, and the recomputation of that coverage is what
    the published figure must equal.
    """
    from run_seq12_candidate import corporate_action_archive_coverage

    artifact = _seq12_artifact()
    coverage = artifact["corporate_action_archive_coverage"]
    scanned = artifact["instruments_scanned"]
    import gzip
    import json

    with gzip.open(
        REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        corpus = json.load(handle)
    recomputed, per_isin = corporate_action_archive_coverage(list(corpus["prices_by_instrument"]))
    assert coverage["instruments_scanned"] == scanned == recomputed["instruments_scanned"], (
        coverage,
        scanned,
        recomputed,
    )
    assert coverage["bronze_distinct_isins"] == recomputed["bronze_distinct_isins"], (
        f"the artifact publishes {coverage['bronze_distinct_isins']} covered ISINs and the archive holds "
        f"{recomputed['bronze_distinct_isins']} (N-200)"
    )
    assert (
        coverage["instruments_with_no_bronze_record"]
        == recomputed["instruments_with_no_bronze_record"]
    ), (coverage, recomputed)
    uncovered_rows = sorted(
        row["isin"]
        for row in artifact["below_minus_20pct_one_day"]
        if row["shape"] == "LEVEL_STEP_AT_OPEN"
        and not row["attested"]
        and per_isin.get(row["isin"], 0) == 0
    )
    assert coverage["unattested_stop_rows_on_uncovered_instruments"] == uncovered_rows, (
        coverage["unattested_stop_rows_on_uncovered_instruments"],
        uncovered_rows,
    )


def probe_n201() -> None:
    """
    The NIFTYBEES benchmark is not continuous across 2019-12-19 (N-201). Asserts the corpus carries an
    unadjusted 1:10 step while stamping the bar as back-adjusted, and that the reconciliation's own
    detail omits it.
    """
    import gzip
    import json

    corpus = json.load(
        gzip.open(
            REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz",
            "rt",
            encoding="utf-8",
        )
    )
    bars = {r["trade_date"]: r for r in corpus["prices_by_instrument"]["INF732E01011"]}
    ratio = Decimal(bars["2019-12-19"]["close"]) / Decimal(bars["2019-12-18"]["close"])
    assert ratio < Decimal("0.11"), (
        f"the corpus ratio across the ISIN transition is now {ratio}; if the series is back-adjusted "
        "the boundary N-201 measured is repaired and clause (d) may be evaluable"
    )
    detail = corpus["reconciliation"]["ratio_shaped_detail"]
    assert not [r for r in detail if r["isin"] == "INF732E01011"], (
        "the reconciliation now publishes the boundary it omitted; re-measure N-201"
    )


def probe_n202() -> None:
    """
    The exit/entry interaction is pinned and the code agrees (N-202). Two measurements: the
    pre-registration names the resolution (`EXIT_SUPPRESSES_ENTRY_ON_THE_SAME_SESSION`), and a session
    whose features satisfy both predicates emits the exit and no entry for the same name.
    """
    import datetime
    from decimal import Decimal
    from types import SimpleNamespace

    import yaml

    from signal_core.strategy.mean_reversion import MeanReversionSwingStrategy

    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "trial_012_candidate.yaml").read_text(encoding="utf-8")
    )
    interaction = config["strategy"].get("entry_exit_interaction")
    assert interaction == "EXIT_SUPPRESSES_ENTRY_ON_THE_SAME_SESSION", (
        f"the pre-registration pins {interaction!r}: a rule committed as closed-form may not leave the "
        "entry/exit interaction for the code to decide (N-202, AGENTS.md §8.1)"
    )

    # A session on which both predicates are true: exit needs close > SMA(5), entry needs
    # close > SMA(200) and RSI(2) < 10. 110 > 108, 110 > 90 and RSI(2) = 4 satisfy all three.
    isin = "INE002A01018"
    features = {
        isin: SimpleNamespace(
            close=Decimal("110.00"),
            sma_5=Decimal("108.00"),
            sma_200=Decimal("90.00"),
            rsi_2=Decimal("4.00"),
        )
    }
    strategy = MeanReversionSwingStrategy(allocation_weight=Decimal("0.05"))
    intents = strategy.generate_signals(
        as_of=datetime.date(2021, 6, 15),
        next_session=datetime.date(2021, 6, 16),
        universe=[isin],
        features=features,
    )
    sides = [intent.side.value for intent in intents]
    assert sides == ["SELL"], (
        f"a session satisfying both predicates emits {sides}, but the pre-registration pins "
        f"{interaction} (N-202)"
    )
    # And the entry branch is still reachable, so the assertion above is not vacuous.
    features[isin] = SimpleNamespace(
        close=Decimal("100.00"),
        sma_5=Decimal("101.00"),
        sma_200=Decimal("90.00"),
        rsi_2=Decimal("4.00"),
    )
    entry_intents = strategy.generate_signals(
        as_of=datetime.date(2021, 6, 15),
        next_session=datetime.date(2021, 6, 16),
        universe=[isin],
        features=features,
    )
    assert [intent.side.value for intent in entry_intents] == ["BUY"], entry_intents


def probe_n203() -> None:
    """
    A committed digest of a tracked artifact must reproduce from the bytes the repository stores
    (N-203, AGENTS.md §9.1, §12.3).

    `reports/analysis/s100/seq10_baseline_comparison.json` publishes the sha256 of the trial_010
    verdict as hashed from the author's working copy. The file is stored LF; the published digest is
    the CRLF rendering of the same bytes, so `compare_seq10_baselines.py --check` recomputes another
    value on any clone and exits 1. Both hashes are computed here from the file, so the measurement
    does not depend on this checkout's line endings.
    """
    import hashlib
    import json

    comparison = json.loads(
        (REPO_ROOT / "reports" / "analysis" / "s100" / "seq10_baseline_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    committed = str(comparison["seq10_artifact_sha256"])
    artifact = (
        REPO_ROOT
        / "reports"
        / "verdicts"
        / "trial_010"
        / "phase3b2_swing_baseline_2022_2024_verdict.json"
    ).read_bytes()
    lf = artifact.replace(b"\r\n", b"\n")
    stored = hashlib.sha256(lf).hexdigest()
    rendered = hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()
    assert committed == rendered, (
        f"the committed seq-10 digest is {committed}, not the CRLF rendering {rendered}; if it is now "
        "the stored bytes' digest, the clone failure N-203 measured is repaired"
    )
    assert committed != stored, (
        f"the committed digest is the stored bytes' own sha256 {stored}; N-203 is repaired and "
        "`compare_seq10_baselines.py --check` should exit 0 in a clean clone"
    )


def probe_n204() -> None:
    """
    A published dataset digest must be the digest of the stored file (N-204, AGENTS.md §10.5, §6.5).

    The seq-12 QA artifact publishes `corpus.sha256` computed by `_digest`, which replaces b"\\r\\n"
    with b"\\n" on every path it is given. Applied to the gzip corpus that hashes a mutated stream:
    the value is reproducible only by re-doing the mutation, and it disagrees with the manifest's own
    sha256 for the same bytes.
    """
    import hashlib
    import json

    qa = _seq12_artifact()
    committed = str(qa["corpus"]["sha256"])
    raw = (REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz").read_bytes()
    stored = hashlib.sha256(raw).hexdigest()
    mutated = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    assert committed == mutated, (
        f"the artifact publishes {committed} for the corpus, which is not the CRLF-mutated digest "
        f"{mutated}; if it now equals {stored} the field is repaired and N-204 closes"
    )
    assert committed != stored, (
        f"the artifact publishes the file's own sha256 {stored}; N-204 is repaired"
    )
    comparison = json.loads(
        (REPO_ROOT / "reports" / "analysis" / "s100" / "seq10_baseline_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(comparison["dataset_sha256"]) == stored, (
        "the s100 comparison no longer cites the corpus's stored bytes, so the disagreement N-204 "
        "measured is gone; re-measure both digests"
    )


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
    "N-162": probe_n162,
    "N-163": probe_n163,
    "N-164": probe_n164,
    "N-165": probe_n165,
    "N-166": probe_n166,
    "N-167": probe_n167,
    "N-168": probe_n168,
    "N-169": probe_n169,
    "N-170": probe_n170,
    "N-171": probe_n171,
    "N-172": probe_n172,
    "N-173": probe_n173,
    "N-174": probe_n174,
    "N-175": probe_n175,
    "N-176": probe_n176,
    "N-177": probe_n177,
    "N-178": probe_n178,
    "N-179": probe_n179,
    "N-180": probe_n180,
    "N-181": probe_n181,
    "N-182": probe_n182,
    "N-183": probe_n183,
    "N-184": probe_n184,
    "N-185": probe_n185,
    "N-186": probe_n186,
    "N-187": probe_n187,
    "N-188": probe_n188,
    "N-189": probe_n189,
    "N-190": probe_n190,
    "N-191": probe_n191,
    "N-192": probe_n192,
    "N-193": probe_n193,
    "N-194": probe_n194,
    "N-195": probe_n195,
    "N-196": probe_n196,
    "N-197": probe_n197,
    "N-198": probe_n198,
    "N-199": probe_n199,
    "N-200": probe_n200,
    "N-201": probe_n201,
    "N-202": probe_n202,
    "N-203": probe_n203,
    "N-204": probe_n204,
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
