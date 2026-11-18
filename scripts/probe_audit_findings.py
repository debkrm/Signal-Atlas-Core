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
import subprocess
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
    The replay-guard benchmark measures CPU time, and on Windows `time.process_time()` steps in
    15.625 ms units (N-173).

    `test_n1_replay_guard_o1_lookup_and_bounded_memory` now times its two loops with `process_time()` and
    keeps the 250 µs ceiling and the `< 2.5` scaling ratio (§89.4). On this host the clock returns only
    two distinct values in 20,000 calls — it advances in one 15.625 ms step — so a 1,000-fill loop that
    costs less than half a tick measures **0.0 µs/fill**, and the ratio guard's `max(per_fill_1k_us, 1.0)`
    floor then divides the 4,000-fill figure by 1.0: at 5 µs/fill the true ratio is 1.0 and the measured
    ratio is 3.91, so a *faster* implementation fails the test. The probe asserts the instrument is still
    the one under review and, on a coarse-tick host, that the window reproduces; on a host with a
    nanosecond clock it asserts the same workload stays near 1.0, which is why the defect is
    Windows-bound rather than universal.
    """
    import time as _time

    source = (REPO_ROOT / "tests" / "unit" / "test_portfolio.py").read_text(encoding="utf-8")
    assert "time.process_time()" in source, (
        "the benchmark no longer uses process_time, so N-173 is closed and this probe should assert the "
        "replacement instrument's resolution instead"
    )
    assert "max(per_fill_1k_us, 1.0)" in source, "the ratio guard no longer floors the 1k measurement"

    # Sample the clock while burning CPU: spin until it advances, so one step is observable even when a
    # single sample per tick would otherwise make 20,000 adjacent reads look constant.
    def time_to_tick_us() -> float:
        best = 0.0
        for _ in range(5):
            start = _time.process_time()
            wall = _time.perf_counter()
            while _time.process_time() == start:
                pass
            best = max(best, (_time.perf_counter() - wall) * 1e6)
        return best

    tick_us = time_to_tick_us()
    assert tick_us > 0.0, "process_time never advanced under a CPU-bound spin, so its step cannot be measured"

    # A 5 us/fill implementation: 5 ms for 1,000 fills, 20 ms for 4,000 — the true ratio is 1.0.
    true_ratio = 1.0

    if tick_us >= 1000.0:
        # Quantize the honest 5 us/fill workload to the clock the test actually reads.
        tick_s = tick_us * 1e-6
        one_k = round((1000 * 5e-6) / tick_s) * tick_s / 1000 * 1e6
        four_k = round((4000 * 5e-6) / tick_s) * tick_s / 4000 * 1e6
        ratio = four_k / max(one_k, 1.0)
        assert one_k == 0.0, (
            f"the coarse clock measured {one_k:.1f} us/fill for a 5 us/fill loop, so the zero-floor "
            f"window this finding describes does not reproduce"
        )
        assert ratio >= 2.5, (
            f"quantization of a 5 us/fill loop over a {tick_us:.1f} us clock gives ratio {ratio:.2f}, "
            f"under the 2.5 ceiling, so N-173 does not reproduce on this host"
        )
        assert ratio != true_ratio
    else:
        tick_s = tick_us * 1e-6
        one_k = round((1000 * 5e-6) / tick_s) * tick_s / 1000 * 1e6
        four_k = round((4000 * 5e-6) / tick_s) * tick_s / 4000 * 1e6
        assert abs(four_k / max(one_k, 1.0) - true_ratio) < 0.5, (
            f"a {tick_us:.3f} us clock quantizes a 5 us/fill workload to "
            f"{one_k:.1f}/{four_k:.1f} us, so the zero-floor window is not host-bound as described"
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
