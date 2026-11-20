"""Seq 12 Step 2 — the data-QA classifier and the gate it feeds (AGENTS.md §5.4, §6.3, §9.3).

The QA is a fail-closed check, so its own decision function is tested rather than trusted:

- only a price-side record (SPLIT/BONUS/CONSOLIDATION) on the exact ex-date whose ratio reproduces the
  move attests it; a dividend, a near-dated ratio or a transition does not (§97.10 item 2);
- a move that is already in the session's opening price is a level step (the NIFTYBEES 2019-12-19
  shape); a move after an ordinary open is a session the exchange traded;
- the gate refuses anything that is not CLEAR.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from scripts.run_seq12_candidate import _classify_drop, qa_gate, ratio_shapes

ISIN = "INE292A01023"
SESSION = datetime.date(2019, 12, 18)


def _record(kind: str, ex_date: str, numerator: str = "2", denominator: str = "3") -> dict:
    return {
        "isin": ISIN,
        "ex_date": ex_date,
        "action_type": kind,
        "ratio_numerator": numerator,
        "ratio_denominator": denominator,
        "circular_ref": f"TEST_{kind}",
        "provenance": "CONTENT_IDENTIFIED_ONLY",
    }


def test_ratio_shapes_enumerates_the_ratios_that_would_print_the_move():
    assert "2/3" in ratio_shapes(Decimal("-0.3333"))
    # −20.54% is not a share ratio: no bonus or split prints it.
    assert ratio_shapes(Decimal("-0.2054")) == []


def test_only_a_price_side_ratio_on_the_exact_date_attests_the_move():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.3333"),
        Decimal("-0.3333"),
        {ISIN: [_record("BONUS", "2019-12-18")]},
    )
    assert row["disposition"] == "ATTESTED_RATIO_MATCH", row
    assert row["attested"] is True
    assert row["shape"] == "LEVEL_STEP_AT_OPEN"


def test_a_dividend_on_the_date_does_not_exonerate_a_ratio_shaped_move():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.3333"),
        Decimal("-0.3333"),
        {ISIN: [_record("DIVIDEND", "2019-12-18", "1", "1")]},
    )
    assert row["disposition"] == "UNATTESTED_NO_RECORD", row
    assert row["attested"] is False
    assert [r["action_type"] for r in row["records_on_date"]] == ["DIVIDEND"]


def test_an_action_five_sessions_away_is_a_mismatch_not_an_attestation():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.3333"),
        Decimal("-0.3333"),
        {ISIN: [_record("SPLIT", "2019-12-23")]},
    )
    assert row["disposition"] == "UNATTESTED_EX_DATE_MISMATCH", row
    assert row["attested"] is False


def test_an_isin_transition_on_the_date_is_declared_but_not_an_attestation():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.5000"),
        Decimal("0.0000"),
        {ISIN: [_record("ISIN_TRANSITION", "2019-12-18", "1", "1")]},
    )
    assert row["disposition"] == "UNATTESTED_TRANSITION", row
    assert row["shape"] == "SESSION_MOVE", row


def test_the_shape_separates_a_level_step_from_a_session_that_traded():
    step = _classify_drop(ISIN, SESSION, Decimal("-0.3011"), Decimal("-0.2972"), {})
    traded = _classify_drop(ISIN, SESSION, Decimal("-0.2054"), Decimal("-0.0976"), {})
    assert step["shape"] == "LEVEL_STEP_AT_OPEN"
    assert traded["shape"] == "SESSION_MOVE"


def test_the_gate_refuses_anything_but_clear():
    assert qa_gate({"status": "STOP", "stop_reason": "unattested step"}) == "unattested step"
    assert qa_gate({"status": "CLEAR", "stop_reason": None}) is None
