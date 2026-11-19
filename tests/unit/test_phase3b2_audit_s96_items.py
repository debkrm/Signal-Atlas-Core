"""
Audit §96 items — the non-reproducibility annotation, the statutory interval tables and the demerger seam.

These execute the work order Audit §95.10 issued against `6a04fd8` / tag `audit-s95-6a04fd8b`. Each test
asserts the committed tree and, where the defect is a missing branch, the branch's absence is made to
fail the same assertion (§14.4).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.contracts.criteria import (  # noqa: E402
    STATUTORY_RATE_COMPONENTS,
    load_go_no_go_criteria,
)
from signal_core.storage.security_master import (  # noqa: E402
    CorporateActionType,
    load_corporate_actions,
)

REGISTRY = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl"
ANNOTATIONS = REPO_ROOT / "data" / "trials" / "trial_annotations.jsonl"


def _registry_rows() -> list[dict]:
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_seq9_row_carries_the_non_reproducibility_annotation() -> None:
    """§95.10 item 7: the row that does not reproduce is annotated, and its own bytes are untouched."""
    row = next(r for r in _registry_rows() if r["trial_id"] == "TRIAL-PHASE3B2-RANKED-009")
    # The hash chain is the registry's integrity; an annotation must not rewrite it (§10.1).
    assert row["record_hash"] == "50de55e960ad59375c988fe88fef2fbf5e5a1155bd6315dacb09697d29429032"

    annotations = [
        json.loads(line) for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    matches = [a for a in annotations if a.get("record_hash") == row["record_hash"]]
    assert len(matches) == 1, (
        f"{len(matches)} annotation(s) key on the committed seq-9 record hash; the row must have exactly "
        f"one, or a reader cannot tell that it fails to reproduce"
    )
    annotation = matches[0]
    assert annotation["annotation"] == "NON_REPRODUCIBLE_AT"
    assert annotation["annotated_at_sha"] == "77fb043"
    divergence = annotation["divergence"]
    assert divergence["hold_bound_forced_exits"] > 0
    assert divergence["committed_metrics_reproduced"] == 0
    assert divergence["committed_metrics_compared"] == 5
    # Neither run reproduces the artifact, so the annotation cannot blame the hold bound alone.
    assert divergence["counterfactual_run_b_closed_trades"] != divergence["committed_closed_trades"]


def test_statutory_rates_are_interval_tables_not_scalars() -> None:
    """§95.10 item 1: each levy resolves per session, and the two mid-window revisions are modelled."""
    schedule = load_go_no_go_criteria().statutory_costs
    for component in ("STT_DELIVERY", "SEBI_TURNOVER", "STAMP_DUTY_DELIVERY_BUY"):
        assert component in STATUTORY_RATE_COMPONENTS

    assert schedule.get_rate("STT_DELIVERY", datetime.date(2018, 4, 2)) == schedule.get_rate(
        "STT_DELIVERY", datetime.date(2023, 12, 29)
    )
    # SEBI's COVID halving ran 2020-06-01..2021-03-31 and lapsed afterwards.
    before = schedule.get_rate("SEBI_TURNOVER", datetime.date(2020, 5, 29))
    during = schedule.get_rate("SEBI_TURNOVER", datetime.date(2020, 6, 1))
    after = schedule.get_rate("SEBI_TURNOVER", datetime.date(2021, 4, 1))
    assert during * 2 == before, f"{during} is not half of {before}"
    assert after == before, f"{after} does not return to the pre-2020 rate {before}"

    # The uniform Indian Stamp Act rate replaced the state schedules on 2020-07-01.
    old_stamp = schedule.get_rate("STAMP_DUTY_DELIVERY_BUY", datetime.date(2020, 6, 30))
    new_stamp = schedule.get_rate("STAMP_DUTY_DELIVERY_BUY", datetime.date(2020, 7, 1))
    assert new_stamp == Decimal("0.00015"), new_stamp
    assert old_stamp < new_stamp


def test_pre_2021_session_is_priced_from_committed_bytes() -> None:
    """§95.10 item 1: 2018-04-02 resolves an exchange fee, its digest, and no source problem."""
    from scripts.run_seq10_candidate import statutory_source_problem, statutory_cost_schedule_problem

    criteria = load_go_no_go_criteria()
    assert statutory_source_problem(criteria) is None
    assert statutory_cost_schedule_problem(criteria) is None
    fee = criteria.statutory_costs.get_exchange_fee_for_date(datetime.date(2018, 4, 2))
    assert fee.exchange_turnover_rate == Decimal("0.0000325"), fee.exchange_turnover_rate
    assert fee.ipft_rate == Decimal("0.000000001"), fee.ipft_rate
    assert len(fee.circular_sha256) == 64


def test_demerger_exit_reason_reaches_the_order() -> None:
    """§95.10 item 5: a demerger is a typed event and a forced exit with its own reason."""
    assert "DEMERGER" in {member.value for member in CorporateActionType}
    attested = [
        row
        for row in load_corporate_actions()
        if row.action_type is CorporateActionType.DEMERGER and row.source_digest and not row.superseded
    ]
    assert len(attested) >= 28, len(attested)

    source = (REPO_ROOT / "src" / "signal_core" / "strategy" / "swing.py").read_text(encoding="utf-8")
    assert 'reasons.get(isin, "MAX_HOLD_BOUND_EXIT")' in source, (
        "the harness collapses every forced exit to the hold-bound reason, so a demerger exit cannot be "
        "attributed"
    )
    loop = (REPO_ROOT / "scripts" / "run_phase3b2_walkforward.py").read_text(encoding="utf-8")
    assert "DEMERGER_FORCED_EXIT" in loop
    assert "forced_exit_reasons=forced_reasons" in loop


from decimal import Decimal  # noqa: E402
