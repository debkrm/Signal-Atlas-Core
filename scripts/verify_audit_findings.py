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
    # and earlier rows remain as history. Two rows with the same id *and* the same status are still a
    # duplicate and still fail closed, and a closure must cite its section (§9.1, §11.3).
    latest: dict = {}
    for row in rows:
        previous = latest.get(row["id"])
        if previous is not None and previous["status"] == row["status"]:
            print(f"[FAIL] Duplicate finding id {row['id']} with status {row['status']}")
            return 1
        if row["status"] == "CLOSED" and not isinstance(row.get("closed_in_section"), int):
            print(f"[FAIL] {row['id']} is marked CLOSED without an integer 'closed_in_section' citation")
            return 1
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
