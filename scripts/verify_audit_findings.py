#!/usr/bin/env python3
"""
Executes the probes registered in `reports/audit/findings.jsonl` (Audit §78.15 (c), §9.1).

A finding's status is a computation, not a paragraph: every row carries a probe command, an expected
exit code and a required stdout pattern, and this gate runs them. A row whose status is `ACCEPTED`
names a residual instead of a closure and is reported but not executed.

Exit 0 only when every executed probe matched its expectation.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "reports" / "audit" / "findings.jsonl"

REQUIRED_FIELDS = ("id", "section", "severity", "status", "metric", "probe", "phase")
NON_EXECUTED_STATUSES = {"ACCEPTED"}

# Audit §79.12 item 6 (N-157): the ledger is append-only per finding, so a closure is a later row with
# the same id. Ratifying that means the transition itself is checked: a finding may move forward out
# of OPEN (to CLOSED or ACCEPTED) and an accepted residual may later be CLOSED, but a CLOSED finding
# cannot be re-OPENed by appending a row, and a repeated id with the same status is still a duplicate.
ALLOWED_TRANSITIONS = {
    "OPEN": {"CLOSED", "ACCEPTED"},
    "ACCEPTED": {"CLOSED"},
}


def load_findings() -> list:
    if not LEDGER.is_file():
        raise FileNotFoundError(f"findings ledger missing: {LEDGER}")
    rows = []
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = [field for field in REQUIRED_FIELDS if field not in row]
            if missing:
                raise ValueError(f"findings ledger line {line_no} missing {missing}")
            probe = row["probe"]
            if not isinstance(probe, dict) or "command" not in probe or "stdout_regex" not in probe:
                raise ValueError(f"findings ledger line {line_no} has an unexecutable probe")
            rows.append(row)
    return rows


def validate_ledger(rows: list) -> list:
    """
    Returns the ledger's structural errors, in file order (§79.9, §79.12 item 6, N-157).
    Extracted from `main` so the transition rules are a computation a test can drive directly.
    """
    problems = []
    previous_status: dict = {}
    for row in rows:
        prior = previous_status.get(row["id"])
        if prior is not None:
            if prior == row["status"]:
                problems.append(f"Duplicate finding id {row['id']} with status {row['status']}")
                continue
            if row["status"] not in ALLOWED_TRANSITIONS.get(prior, set()):
                problems.append(
                    f"{row['id']} transitions {prior} -> {row['status']}, which is not a forward "
                    f"transition (allowed: {sorted(ALLOWED_TRANSITIONS.get(prior, set()))})"
                )
                continue
        if row["status"] == "CLOSED" and not isinstance(row.get("closed_in_section"), int):
            problems.append(
                f"{row['id']} is marked CLOSED without an integer 'closed_in_section' citation"
            )
            continue
        previous_status[row["id"]] = row["status"]
    return problems


def main() -> int:
    print("=" * 80)
    print("AUDIT FINDINGS LEDGER — EXECUTABLE PROBES (§78.15 (c), §9.1)")
    print("=" * 80)

    try:
        rows = load_findings()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}")
        return 1

    # Audit §79.9 (N-157): the ledger is append-only, so a closure is an appended row carrying the
    # same id, the new status and the section that measured it. The last row per id is authoritative
    # and earlier rows remain as history. Two rows with the same id *and* the same status are a
    # duplicate, a backward transition is refused, and a closure must cite its section (§9.1, §11.3).
    problems = validate_ledger(rows)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 1
    latest: dict = {}
    for row in rows:
        latest[row["id"]] = row
    rows = list(latest.values())

    failures = 0
    for row in rows:
        if row["status"] in NON_EXECUTED_STATUSES:
            print(f"[INFO] {row['id']} {row['status']}: {row.get('residual', 'no residual recorded')}")
            continue
        probe = row["probe"]
        expect_exit = int(probe.get("expect_exit", 0))
        proc = subprocess.run(
            probe["command"],
            cwd=str(REPO_ROOT),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        matched = re.search(probe["stdout_regex"], proc.stdout or "") is not None
        if proc.returncode != expect_exit or not matched:
            failures += 1
            print(
                f"[FAIL] {row['id']} ({row['severity']}, {row['status']}): exit {proc.returncode} "
                f"(expected {expect_exit}), stdout regex {probe['stdout_regex']!r} "
                f"{'matched' if matched else 'did not match'}"
            )
            tail = (proc.stdout or "").strip().splitlines()[-3:]
            for line in tail:
                print(f"       {line}")
        else:
            print(f"[PASS] {row['id']} ({row['severity']}, {row['status']}): probe matched")

    print("=" * 80)
    if failures:
        print(f"OVERALL VERDICT: {failures} FINDING PROBE(S) FAILED")
        print("=" * 80)
        return 1
    print(f"OVERALL VERDICT: ALL {len(rows)} FINDING PROBE(S) PASSED")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
