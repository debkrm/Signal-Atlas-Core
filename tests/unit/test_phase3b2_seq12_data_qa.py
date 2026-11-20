"""Seq 12 Step 2 — the data-QA classifier and the gate it feeds (AGENTS.md §5.4, §6.3, §9.3).

The QA is a fail-closed check, so its own decision function is tested rather than trusted:

- a price-side record (SPLIT/BONUS/CONSOLIDATION) on the exact ex-date attests when its share ratio
  reproduces the move (§97.10 item 2);
- a cash record (DIVIDEND/RIGHTS) on the exact ex-date attests when its cash amount reproduces the
  session's close or its opening price within 0.5% of the previous close (N-196, §100.16 item 1), and
  is published as `UNATTESTED_CASH_MISMATCH` when it does not;
- a move that is already in the session's opening price is a level step (the NIFTYBEES 2019-12-19
  shape); a move after an ordinary open is a session the exchange traded;
- the gate refuses anything that is not CLEAR.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from scripts.run_seq12_candidate import (
    CASH_ADJUSTMENT_TOLERANCE,
    _classify_drop,
    qa_gate,
    ratio_shapes,
)

ISIN = "INE292A01023"
SESSION = datetime.date(2019, 12, 18)
PREVIOUS_CLOSE = Decimal("150.00")


def _record(
    kind: str,
    ex_date: str,
    numerator: str = "2",
    denominator: str = "3",
    amount: str | None = None,
    description: str = "",
) -> dict:
    row = {
        "isin": ISIN,
        "ex_date": ex_date,
        "action_type": kind,
        "ratio_numerator": numerator,
        "ratio_denominator": denominator,
        "description": description,
        "circular_ref": f"TEST_{kind}",
        "provenance": "CONTENT_IDENTIFIED_ONLY",
    }
    if amount is not None:
        row["dividend_amount"] = amount
    return row


def _levels(previous_close: str, close: str, opening: str) -> tuple:
    """The two arguments the classifier takes, computed from the levels rather than typed."""
    previous = Decimal(previous_close)
    move = Decimal(close) / previous - Decimal(1)
    gap = Decimal(opening) / previous - Decimal(1)
    return previous, move, gap


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
        PREVIOUS_CLOSE,
        {ISIN: [_record("BONUS", "2019-12-18")]},
    )
    assert row["disposition"] == "ATTESTED_RATIO_MATCH", row
    assert row["attested"] is True
    assert row["shape"] == "LEVEL_STEP_AT_OPEN"


def test_a_dividend_carrying_no_cash_amount_is_not_an_attestation():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.3333"),
        Decimal("-0.3333"),
        PREVIOUS_CLOSE,
        {ISIN: [_record("DIVIDEND", "2019-12-18", "1", "1")]},
    )
    assert row["disposition"] == "UNATTESTED_CASH_MISMATCH", row
    assert row["attested"] is False
    assert [r["action_type"] for r in row["records_on_date"]] == ["DIVIDEND"]
    assert row["cash_adjustment"]["tested"] == []


# --- the cash-adjustment branch (N-196) ----------------------------------------------------
#
# Both levels are the committed archive's own numbers, not typed moves: HEUBACHIND's Rs 140 special
# dividend (ex 2020-07-16) on a 563.30 close, and VARDHACRLC's Rs 25 interim (ex 2021-10-28).


def test_an_ex_date_dividend_that_reproduces_the_close_attests_the_step():
    previous, move, gap = _levels("563.30", "423.55", "403.00")
    row = _classify_drop(
        "INE492A01029",
        datetime.date(2020, 7, 16),
        move,
        gap,
        previous,
        {"INE492A01029": [_record("DIVIDEND", "2020-07-16", "1", "1", amount="140.00")]},
    )
    assert row["disposition"] == "ATTESTED_CASH_ADJUSTMENT", row
    assert row["attested"] is True
    assert row["shape"] == "LEVEL_STEP_AT_OPEN"
    tested = row["cash_adjustment"]["tested"]
    assert len(tested) == 1 and tested[0]["basis"] == "DIVIDEND_AMOUNT"
    assert tested[0]["predicted_level"] == "423.3000"
    assert Decimal(tested[0]["close_residual"]) <= CASH_ADJUSTMENT_TOLERANCE


def test_an_ex_date_dividend_that_does_not_reproduce_the_level_is_published_not_disposed_of():
    previous, move, gap = _levels("72.35", "56.60", "51.00")
    row = _classify_drop(
        "INE116G01013",
        datetime.date(2021, 10, 28),
        move,
        gap,
        previous,
        {"INE116G01013": [_record("DIVIDEND", "2021-10-28", "1", "1", amount="25.00")]},
    )
    assert row["disposition"] == "UNATTESTED_CASH_MISMATCH", row
    assert row["attested"] is False
    tested = row["cash_adjustment"]["tested"][0]
    assert tested["predicted_level"] == "47.3500"
    assert Decimal(tested["close_residual"]) > CASH_ADJUSTMENT_TOLERANCE
    assert Decimal(tested["opening_residual"]) > CASH_ADJUSTMENT_TOLERANCE


def test_a_rights_entitlement_attests_by_its_theoretical_ex_rights_price():
    # SUZLON 5:21 @ INR 5.00 with a 10.00 cum-rights close: TERP = (10*21 + 5*5) / 26 = 9.0385.
    previous = Decimal("10.00")
    predicted = (previous * Decimal(21) + Decimal("5.00") * Decimal(5)) / Decimal(26)
    move = predicted / previous - Decimal(1)
    row = _classify_drop(
        "INE040H01021",
        datetime.date(2022, 10, 14),
        move,
        move,
        previous,
        {
            "INE040H01021": [
                _record(
                    "RIGHTS",
                    "2022-10-14",
                    "5",
                    "21",
                    description="SUZLON Rights Entitlement 5:21 @ INR 5.00",
                )
            ]
        },
    )
    assert row["disposition"] == "ATTESTED_CASH_ADJUSTMENT", row
    assert row["cash_adjustment"]["tested"][0]["basis"] == "RIGHTS_TERP"


def test_the_cash_tolerance_is_the_recorded_half_percent_and_is_the_boundary():
    assert CASH_ADJUSTMENT_TOLERANCE == Decimal("0.005")
    # A Rs 50 dividend on a 100.00 close predicts 50.00; a 50.40 close is 0.40% off and attests...
    previous, move, gap = _levels("100.00", "50.40", "50.40")
    inside = _classify_drop(
        ISIN, SESSION, move, gap, previous, {ISIN: [_record("DIVIDEND", "2019-12-18", "1", "1", amount="50")]}
    )
    assert inside["disposition"] == "ATTESTED_CASH_ADJUSTMENT", inside
    # ...and a 50.60 close is 0.60% off, so the same record does not attest it.
    previous, move, gap = _levels("100.00", "50.60", "50.60")
    outside = _classify_drop(
        ISIN, SESSION, move, gap, previous, {ISIN: [_record("DIVIDEND", "2019-12-18", "1", "1", amount="50")]}
    )
    assert outside["disposition"] == "UNATTESTED_CASH_MISMATCH", outside


def test_an_action_five_sessions_away_is_a_mismatch_not_an_attestation():
    row = _classify_drop(
        ISIN,
        SESSION,
        Decimal("-0.3333"),
        Decimal("-0.3333"),
        PREVIOUS_CLOSE,
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
        PREVIOUS_CLOSE,
        {ISIN: [_record("ISIN_TRANSITION", "2019-12-18", "1", "1")]},
    )
    assert row["disposition"] == "UNATTESTED_TRANSITION", row
    assert row["shape"] == "SESSION_MOVE"


def test_the_shape_separates_a_level_step_from_a_session_that_traded():
    step = _classify_drop(ISIN, SESSION, Decimal("-0.3011"), Decimal("-0.2972"), PREVIOUS_CLOSE, {})
    traded = _classify_drop(ISIN, SESSION, Decimal("-0.2054"), Decimal("-0.0976"), PREVIOUS_CLOSE, {})
    assert step["shape"] == "LEVEL_STEP_AT_OPEN"
    assert traded["shape"] == "SESSION_MOVE"


def test_the_gate_refuses_anything_but_clear():
    assert qa_gate({"status": "STOP", "stop_reason": "unattested step"}) == "unattested step"
    assert qa_gate({"status": "CLEAR", "stop_reason": None}) is None
