"""
Audit §95 items — the reachable seam, the pinned superseded count, the derived fold and the fallback.

Each test asserts the committed tree *and* the mutation Audit §94 measured passing, so a check that
cannot fail is itself a failure here (§14.4). The four items are §94.6 items 2, 4, 5 and 6.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import shutil
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.contracts.dataset import PriceConvention  # noqa: E402
from scripts.probe_audit_findings import (  # noqa: E402
    _dead_guarded_harness_call,
    _session_loop_passthrough_problem,
)
from scripts.probe_pre2022_bronze_coverage import (  # noqa: E402
    manifest_rows,
    superseded_row_problems,
)

WALKFORWARD = REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py"


def test_guarded_harness_call_is_refused() -> None:
    """§94.6 item 5 (N-178): the call must be reachable, not merely written with the right keyword."""
    source = WALKFORWARD.read_text(encoding="utf-8")
    assert _session_loop_passthrough_problem(source) is None

    guarded = _dead_guarded_harness_call(source)
    assert guarded != source
    problem = _session_loop_passthrough_problem(guarded)
    assert problem is not None, (
        "the live harness call indented under `if forced_exits is None:` is accepted, so nothing "
        "asserts that the session loop reaches the harness (N-178)"
    )
    assert "control flow" in problem, problem


def test_deleted_superseded_row_is_refused() -> None:
    """§94.6 item 6 (N-179): the cited count is pinned, and a deletion names the artifact."""
    rows = manifest_rows()
    problems, checked = superseded_row_problems(rows)
    assert problems == [], problems[:3]
    assert checked == 931

    index = next(
        position
        for position, row in enumerate(rows)
        if row.get("session_date") and row.get("is_current") is not True
    )
    artifact = str(rows[index]["artifact"])
    trimmed = rows[:index] + rows[index + 1 :]
    problems_after, checked_after = superseded_row_problems(trimmed)

    assert checked_after == checked - 1
    assert problems_after, "a deleted superseded row is invisible to the certificate (N-179)"
    assert any(artifact in problem for problem in problems_after), problems_after[:2]


def test_in_sample_fold_is_derived_from_the_requested_window() -> None:
    """§94.6 item 2 (N-180): one derivation, two windows, three registrations that must agree."""
    import scripts.probe_seq10_candidate as certificate
    import scripts.run_phase3b2_walkforward as walkforward
    import scripts.run_seq10_candidate as runner

    expanded = runner.seq10_fold_fingerprint()
    assert expanded == certificate._expected_fold_fingerprint(), (
        "the registration path and the certificate derive different folds for one window (N-180)"
    )
    assert expanded.startswith("FOLD-SPEC-V1-36a39987"), expanded

    fold = walkforward.in_sample_fold_for_dates(
        datetime.date(2018, 4, 1), datetime.date(2023, 12, 31)
    )
    assert (fold.train_start, fold.train_end) == (datetime.date(2018, 4, 1), datetime.date(2022, 12, 30))
    assert (fold.test_start, fold.test_end) == (datetime.date(2023, 1, 2), datetime.date(2023, 12, 31))
    assert fold.embargo_sessions == 0
    assert fold.partition_role is walkforward.PartitionRole.IN_SAMPLE

    # A fold derived from a window is not a fold redefined for every window: the committed
    # 2022-01-03..2023-12-29 fold that seq 1..9 were registered under must reproduce byte for byte.
    legacy = walkforward.in_sample_fold_fingerprint(
        datetime.date(2022, 1, 3), datetime.date(2023, 12, 29)
    )
    assert legacy.startswith("FOLD-SPEC-V1-4b44a1f2"), legacy


def test_expanded_window_states_the_exchange_fee_schedule_it_lacks() -> None:
    """§94.6 item 3: the seq-10 window is NOT RUN because no committed fee row prices 2018."""
    import scripts.run_phase3b2_walkforward as walkforward
    import scripts.run_seq10_candidate as runner
    from signal_core.contracts.criteria import load_go_no_go_criteria

    criteria = load_go_no_go_criteria()
    problem = runner.statutory_cost_schedule_problem(criteria)
    earliest = min(fee.from_date for fee in criteria.statutory_costs.effective_dated_exchange_fees)
    first_session = walkforward.load_anchored_nse_trading_calendar().sessions_in_range(
        runner.WINDOW_START, runner.WINDOW_END
    )[0]

    if earliest <= first_session:
        assert problem is None, problem
        return
    assert problem is not None, (
        "the window opens before the earliest committed exchange-fee row, so an unpriced session is "
        "accepted instead of refused (AGENTS.md §7.2)"
    )
    assert str(earliest) in problem and str(first_session) in problem, problem


def test_raw_bhavcopy_fallback_builds_a_stated_dataset(tmp_path) -> None:
    """§94.6 item 4: the fallback runs instead of raising, and states its price convention."""
    import scripts.run_phase3b2_walkforward as walkforward

    sources = sorted((REPO_ROOT / "data" / "raw" / "2023").glob("*.zip"))[:2]
    assert len(sources) == 2, "two committed 2023 archives are needed for the fallback fixture"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for source in sources:
        shutil.copyfile(source, raw_dir / source.name)

    dataset = walkforward.build_historical_dataset_from_raw_bhavcopy(raw_dirs=[raw_dir])

    assert dataset.snapshot.price_convention is PriceConvention.UNADJUSTED_RAW
    assert dataset.snapshot.content_fingerprint.startswith("DATA-CTNT-V2-")
    assert dataset.snapshot.session_count == len(dataset.trading_dates) == 2
    assert dataset.snapshot.instrument_count >= 1
