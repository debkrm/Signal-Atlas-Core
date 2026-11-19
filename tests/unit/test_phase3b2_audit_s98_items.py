"""Audit §97.10 items 1-4 (feat-s98): calendar adjacency, price-side exoneration and the two gates.

These are the fast witnesses; `scripts/probe_audit_findings.py N-191`.. `N-194` assert the committed
corpus and artifacts the same fixes produced.
"""

from decimal import Decimal
import datetime

import scripts.derive_2018_2023_corpus as builder
import scripts.probe_seq10_candidate as certificate
from signal_core.contracts.criteria import compute_criteria_fingerprint, load_go_no_go_criteria
from signal_core.contracts.price_bar import PriceBar

ISIN = "INE000000001"


def _bar(day: datetime.date, close: str) -> PriceBar:
    value = Decimal(close)
    return PriceBar(
        instrument_id=ISIN,
        trade_date=day,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=1000,
        traded_value=Decimal("1000"),
    )


def test_adjacent_bars_across_a_gap_are_not_a_one_session_return():
    """§97.10 item 1: a pair that straddles a missing session is a gap record, never a return."""
    first, last = datetime.date(2022, 1, 3), datetime.date(2022, 2, 3)
    failures, diagnostics = builder.classify_extreme_moves(
        {ISIN: [_bar(first, "10"), _bar(last, "5")]},
        {},
        {},
        [first, datetime.date(2022, 1, 4), last],
    )
    assert failures == []
    assert diagnostics["cross_gap_pairs"] == 1
    assert diagnostics["cross_gap_moves"] == [(ISIN, "2022-02-03", "-0.5000")]
    assert diagnostics["ratio_shaped_unattested"] == []
    assert diagnostics["no_ratio_match"] == 0


def test_consecutive_bars_still_enter_the_reconciliation():
    """The calendar check must not turn a genuine session move into a gap record."""
    first, second = datetime.date(2022, 1, 3), datetime.date(2022, 1, 4)
    _, diagnostics = builder.classify_extreme_moves(
        {ISIN: [_bar(first, "10"), _bar(second, "5")]}, {}, {}, [first, second]
    )
    assert diagnostics["cross_gap_pairs"] == 0
    assert [row[1] for row in diagnostics["ratio_shaped_unattested"]] == ["2022-01-04"]


def test_a_non_price_side_record_does_not_exonerate_a_ratio_shaped_move():
    """§97.10 item 2: an AGM at the exact date is published with its record named, not accepted."""
    first, second = datetime.date(2022, 1, 3), datetime.date(2022, 1, 4)
    agm = {(ISIN, second): [("OTHER", "Annual General Meeting", "d" * 64)]}
    _, diagnostics = builder.classify_extreme_moves(
        {ISIN: [_bar(first, "10"), _bar(second, "5")]}, {}, agm, [first, second]
    )
    assert diagnostics["explained_archive"] == 0
    assert diagnostics["ratio_shaped_unattested"] == [(ISIN, "2022-01-04", "-0.5000", "OTHER")]

    bonus = {(ISIN, second): [("BONUS", "Bonus 1:1", "d" * 64)]}
    _, diagnostics_bonus = builder.classify_extreme_moves(
        {ISIN: [_bar(first, "10"), _bar(second, "5")]}, {}, bonus, [first, second]
    )
    assert diagnostics_bonus["explained_archive"] == 1


def test_a_certificate_citing_a_stale_fingerprint_is_refused_without_a_restatement(tmp_path):
    """§97.10 item 3: a stored hash that is not the live one must fail closed naming both."""
    criteria = load_go_no_go_criteria()
    live = compute_criteria_fingerprint(criteria)
    path = tmp_path / "certificate.json"
    path.write_text(
        '{"criteria_fingerprint": "CRIT-FPR-V1-9ee0a88c260d27fbe3ab13bb7c8c4c992e7d185986f28f5f803cf5db6db8634e"}',
        encoding="utf-8",
    )
    problem = certificate.certificate_problem(path, live, criteria, None)
    assert problem is not None
    assert "9ee0a88c" in problem and live in problem, (
        f"the refusal does not name both hashes: {problem}"
    )


def test_the_pin_only_attestation_is_recomputed_not_trusted():
    """The restatement's executed pin must reproduce the executed fingerprint against the live criteria."""
    criteria = load_go_no_go_criteria()
    restatement = __import__("json").loads(
        certificate.CRITERIA_RESTATEMENT.read_text(encoding="utf-8")
    )
    executed = restatement["certificates"][0]["executed_criteria_fingerprint"]
    pin = restatement["certificates"][0]["executed_manifest_fingerprint"]
    import dataclasses

    assert compute_criteria_fingerprint(
        dataclasses.replace(criteria, expected_manifest_fingerprint=pin)
    ) == executed
    forged = dataclasses.replace(criteria, expected_manifest_fingerprint="MAN-FPR-V1-forged")
    assert compute_criteria_fingerprint(forged) != executed


def test_the_demerger_restatement_must_measure_a_pair():
    """§97.10 item 4: a restatement with no held-position measurement is refused."""
    artifact = {"demerger_forced_exits": 0, "demerger_forced_refusals": 66,
                "hold_bound_forced_exits": 422, "hold_bound_refusals": 7309}
    problem = certificate.demerger_restatement_problem(artifact, None)
    assert problem is not None and "66" in problem
    restatement = {
        "restated": {"demerger_forced_exits": 0, "demerger_forced_refusals": 66},
        "measurement": {},
        "replay": {"hold_bound_forced_exits": 422, "hold_bound_refusals": 7309},
    }
    assert "demerger_forced_exits" in certificate.demerger_restatement_problem(artifact, restatement)
