"""
Audit §97 unit tests — the findings §96 registered.

- N-189: a demerger refusal counts a refused exit of a **held** position, never a demerger event on a
  name the book does not hold, and the demerger reason never absorbs a hold-bound outcome.

The counts are asserted through `count_forced_exit_outcomes`, the function the session loop calls to
attribute one forced-exit reason, rather than through a re-implementation of the arithmetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _path in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from scripts.run_phase3b2_walkforward import count_forced_exit_outcomes  # noqa: E402

DEMERGER = "DEMERGER_FORCED_EXIT"
BOUND = "MAX_HOLD_BOUND_EXIT"


def _book() -> dict:
    """One held-and-filled, one held-and-refused demerger, one unheld event, one held bound exit."""
    return {
        "HELD_AND_FILLED": DEMERGER,
        "HELD_AND_REFUSED": DEMERGER,
        "NOT_HELD": DEMERGER,
        "HELD_UNDER_THE_BOUND": BOUND,
    }


def test_n189_demerger_fill_counts_one_exit_and_no_refusal():
    exits, refusals = count_forced_exit_outcomes(
        _book(), {"HELD_AND_FILLED"}, {"HELD_AND_FILLED"}, DEMERGER
    )
    assert (exits, refusals) == (1, 0)


def test_n189_demerger_refusal_counts_only_a_held_position_that_did_not_fill():
    book = _book()
    held = {"HELD_AND_FILLED", "HELD_AND_REFUSED"}
    assert count_forced_exit_outcomes(book, held, set(), DEMERGER) == (0, 2)
    assert count_forced_exit_outcomes(book, held, {"HELD_AND_REFUSED"}, DEMERGER) == (1, 1)


def test_n189_demerger_event_on_an_unheld_isin_counts_nothing():
    """§96.5: 66 refusals against 0 fills where the artifact could not tell 'held' from 'event'."""
    assert count_forced_exit_outcomes(_book(), set(), set(), DEMERGER) == (0, 0)


def test_n189_the_two_reasons_are_attributed_apart():
    book = _book()
    held = {"HELD_AND_FILLED", "HELD_UNDER_THE_BOUND"}
    assert count_forced_exit_outcomes(book, held, {"HELD_AND_FILLED"}, BOUND) == (0, 1)
    assert count_forced_exit_outcomes(book, held, {"HELD_AND_FILLED"}, DEMERGER) == (1, 0)
