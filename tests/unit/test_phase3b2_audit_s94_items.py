"""
Audit §94 items — the engine-to-harness seam and the superseded manifest row (Audit §93.7).

Both tests are mutations the previous round measured passing: deleting the `forced_exit_isins`
passthrough left every seam test green (§93.3), and nothing in the suite read a superseded manifest
row after its flip (§93.2 residual). Each asserts the committed tree *and* the mutant, so a check that
cannot fail is itself a failure here (§14.4).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.probe_audit_findings import _session_loop_passthrough_problem  # noqa: E402
from scripts.probe_pre2022_bronze_coverage import (  # noqa: E402
    manifest_rows,
    superseded_archive_problems,
)

PASSTHROUGH_LINE = "forced_exit_isins=tuple(sorted(forced_exits)),"


def test_session_loop_hands_the_hold_bound_exits_to_the_harness() -> None:
    """§93.7 item 2: the edge from the loop into the harness is asserted, and cut it fails."""
    source = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    assert _session_loop_passthrough_problem(source) is None, (
        "the committed session loop does not pass forced_exit_isins=tuple(sorted(forced_exits))"
    )

    stripped = "\n".join(
        line for line in source.splitlines() if line.strip() != PASSTHROUGH_LINE
    )
    assert stripped != source, f"`{PASSTHROUGH_LINE}` is not a line of its own in the session loop"
    problem = _session_loop_passthrough_problem(stripped)
    assert problem is not None and "no forced_exit_isins keyword" in problem, (
        f"removing the passthrough is not refused by the check: {problem!r}"
    )


def test_committed_superseded_session_rows_keep_their_archive_fields() -> None:
    """§93.7 item 3: every superseded session row still attests its own archive."""
    rows = manifest_rows()
    problems, checked = superseded_archive_problems(rows)
    assert problems == [], problems[:3]
    superseded = [row for row in rows if row.get("session_date") and row.get("is_current") is not True]
    assert checked == len(superseded), (
        f"{checked} superseded session row(s) checked but the manifest holds {len(superseded)}"
    )


def test_edited_superseded_sha256_is_refused() -> None:
    """§93.7 item 3: a digest edited into a superseded row fails closed, naming the field."""
    rows = manifest_rows()
    index = next(
        position
        for position, row in enumerate(rows)
        if row.get("session_date") and row.get("is_current") is not True
    )
    artifact = str(rows[index]["artifact"])

    tampered = [dict(row) for row in rows]
    tampered[index]["sha256"] = "0" * 64
    problems, _ = superseded_archive_problems(tampered)

    assert problems, "an edited superseded sha256 was not refused"
    assert any(artifact in problem and "sha256" in problem for problem in problems), problems[:3]
    # The committed row is intact, so the refusal above is the edit and not the fixture.
    problems, _ = superseded_archive_problems(rows)
    assert problems == []


def test_superseded_rows_are_read_from_the_manifest_on_disk() -> None:
    """The certificate reads every row, not only the current ones (§10.1)."""
    rows = manifest_rows()
    assert any(row.get("is_current") is True for row in rows)
    assert any(row.get("is_current") is not True for row in rows)
    with open(REPO_ROOT / "data" / "reference" / "manifest.jsonl", encoding="utf-8") as handle:
        on_disk = [json.loads(line) for line in handle if line.strip()]
    assert len(on_disk) == len(rows)
