"""
Unit tests for the Audit §77 remediation items (audit §77 at 6a0479f, reviewing adb16bd).

Target invariants (criteria 1.1.7):
- N-145: identity is resolved per session through the committed interval table and its documented
  ISIN transitions, so every dataset instrument resolves (211 / 211) and an instrument that changes
  identity without a transition row still fails closed.
- N-144: `total_trades` is gated as the de-censored book only when the bundle's own numbers say it is.
- N-147: the generated markdown names the unresolved instruments exactly once.
- §77.13 / §77.12: `CRIT-OVERFIT-03` reads the anchored expanding in-sample folds, and
  `min_liquidated_pf_ex_top_1` is a binding row rather than an unenforced committed threshold.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.price_bar import PriceBar
from signal_core.reporting.verdicts import evaluate_verdicts
from signal_core.storage.security_master import build_production_security_master
from scripts.run_phase3b2_walkforward import (
    resolve_instrument_identity_segments,
    run_phase3b2_walkforward,
)


def _criteria():
    return load_go_no_go_criteria()


def _by_id(bundle_kwargs: dict) -> dict:
    bundle = {"evaluated_at_utc": "2026-11-17T00:00:00+00:00"}
    bundle.update(bundle_kwargs)
    return {e.criterion_id: e for e in evaluate_verdicts(bundle).evaluations}


def _bar(isin: str, trade_date: datetime.date) -> PriceBar:
    return PriceBar(
        instrument_id=isin,
        trade_date=trade_date,
        open=Decimal("100.00"),
        high=Decimal("101.00"),
        low=Decimal("99.00"),
        close=Decimal("100.00"),
        volume=1000,
        traded_value=Decimal("100000.00"),
    )


@pytest.fixture(scope="module")
def security_master():
    return build_production_security_master(include_cash_universe=True)


@pytest.fixture(scope="module")
def short_run(tmp_path_factory):
    """One six-session run on the committed corpus, shared by the artifact-level probes."""
    out = tmp_path_factory.mktemp("s77")
    run_phase3b2_walkforward(
        registry_path=out / "trial_reg.jsonl",
        verdict_output_dir=out / "verdicts",
        in_sample_only=True,
        max_sessions=6,
        write_verdict_files=True,
    )
    artifact = json.loads(
        (out / "verdicts" / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    markdown = (out / "verdicts" / "phase3b2_swing_baseline_2022_2024_verdict.md").read_text(
        encoding="utf-8"
    )
    return artifact, markdown


# --- N-145: identity is point-in-time, and every dataset instrument resolves ------------------


def test_n145_identity_splits_at_each_documented_transition(security_master):
    """TATASTEEL / NESTLEIND / VBL / COCHINSHIP re-key on the first session of the successor ISIN."""
    cases = [
        ("TATASTEEL", datetime.date(2022, 7, 29), "INE081A01012", "INE081A01020"),
        ("NESTLEIND", datetime.date(2024, 1, 5), "INE239A01016", "INE239A01024"),
        ("COCHINSHIP", datetime.date(2024, 1, 10), "INE704P01017", "INE704P01025"),
    ]
    for symbol, boundary, old_isin, new_isin in cases:
        # One session on either side of the boundary is enough to place the split: the identity is a
        # function of the bar's own date, not of the span.
        bars = [
            _bar(old_isin, boundary - datetime.timedelta(days=3)),
            _bar(old_isin, boundary),
        ]
        segments, refusal = resolve_instrument_identity_segments(
            symbol=symbol,
            bars=bars,
            sec_master=security_master,
            reference_isin=new_isin,
        )
        assert refusal is None, refusal
        assert segments is not None
        resolved = [s[0] for s in segments]
        assert old_isin in resolved
        assert resolved[-1] == new_isin
        assert segments[-1][1] == boundary

    # VBL carries two transitions inside the corpus, so one instrument yields three identities.
    vbl_bars = [
        _bar("INE200M01013", d)
        for d in (
            datetime.date(2023, 6, 14),
            datetime.date(2023, 6, 15),
            datetime.date(2024, 9, 11),
            datetime.date(2024, 9, 12),
        )
    ]
    segments, refusal = resolve_instrument_identity_segments(
        symbol="VBL", bars=vbl_bars, sec_master=security_master,
        reference_isin="INE200M01039",
    )
    assert refusal is None, refusal
    assert [s[0] for s in segments] == ["INE200M01013", "INE200M01021", "INE200M01039"]
    assert [s[1] for s in segments] == [
        datetime.date(2023, 6, 14),
        datetime.date(2023, 6, 15),
        datetime.date(2024, 9, 12),
    ]


class _UndocumentedMaster:
    """An interval table that records two identities and no transition row between them."""

    isin_transitions: tuple = ()

    def resolve_isin_by_symbol(self, symbol, as_of, series):
        return {
            datetime.date(2023, 3, 1): "INE466L01020",
            datetime.date(2023, 3, 2): "INE466L01038",
        }.get(as_of)


def test_n145_undocumented_transition_still_fails_closed(security_master):
    """
    A symbol that changes ISIN with no ISIN_TRANSITION row is refused, not resolved.

    After Audit §78.11 every pair the committed interval table records carries a row, so the refusal
    arm (still live for a pair the table lacks, e.g. a newly ingested identity) is probed against a
    stub master that records the change without the row. The same probe then confirms the corpus
    state: 360ONE, undocumented at §77, is now documented by the generator and resolves.
    """
    bars = [_bar("360ONE", d) for d in (datetime.date(2023, 3, 1), datetime.date(2023, 3, 2))]
    segments, refusal = resolve_instrument_identity_segments(
        symbol="360ONE", bars=bars, sec_master=_UndocumentedMaster(),
        reference_isin="INE466L01038",
    )
    assert segments is None
    assert refusal is not None
    assert refusal[0] == "ISIN_TRANSITION_UNDOCUMENTED"

    resolved_segments, refusal = resolve_instrument_identity_segments(
        symbol="360ONE", bars=bars, sec_master=security_master,
        reference_isin="INE466L01038",
    )
    assert refusal is None, refusal
    assert [s[0] for s in resolved_segments] == ["INE466L01020", "INE466L01038"]


def test_n145_every_dataset_instrument_resolves(short_run):
    artifact, _markdown = short_run
    assert artifact["criteria_version"] == "1.1.13"
    assert artifact["dataset_instrument_resolution_denominator"] == 211
    assert artifact["dataset_instrument_resolution_numerator"] == 211
    assert Decimal(str(artifact["dataset_instrument_resolution_pct"])) == Decimal("100")
    assert artifact["unresolved_dataset_instruments"] == []
    # The window row measure is 100% on the same run, and it is a different quantity.
    assert Decimal(str(artifact["traded_eq_resolution_pct"])) == Decimal("100")
    assert artifact["traded_eq_rows_resolved"] == artifact["traded_eq_rows_total"]


# --- N-144: the de-censored count is checked, not trusted by its key name --------------------


def test_n144_censored_total_trades_fails_closed():
    liquidated_positions = [{"isin": f"INE0000000{i}", "net_pnl": "1.00"} for i in range(12)]

    censored = _by_id({
        "total_trades": 193,
        "profit_factor": Decimal("0.9920"),
        "closed_only_trade_count": 193,
        "liquidated_open_positions": liquidated_positions,
    })
    assert censored["CRIT-STAT-01"].status.value == "FAIL"
    assert "Censored book passed as the de-censored count" in censored["CRIT-STAT-01"].evidence

    honest = _by_id({
        "total_trades": 205,
        "profit_factor": Decimal("1.6440"),
        "closed_only_trade_count": 193,
        "liquidated_open_positions": liquidated_positions,
    })
    assert honest["CRIT-STAT-01"].status.value == "PASS"

    declared_mismatch = _by_id({"total_trades": 205, "liquidated_trade_count": 193})
    assert declared_mismatch["CRIT-STAT-01"].status.value == "FAIL"


# --- N-147: the unresolved-instruments line is emitted once ----------------------------------


def test_n147_unresolved_line_appears_exactly_once(short_run):
    _artifact, markdown = short_run
    assert markdown.count("Unresolved dataset instruments") == 1


# --- §77.13 / §77.12: in-sample fold stability and the ex-top-1 margin -----------------------


def _fold(label: str, end: str, expectancy: str, profit_factor: str) -> dict:
    return {
        "label": label,
        "fold_end": end,
        "closed_net_expectancy": Decimal(expectancy),
        "liquidated_profit_factor": Decimal(profit_factor),
    }


def test_overfit03_reads_anchored_in_sample_folds():
    # seq 9's shape: a losing 2022 and a strongly positive 2023. One of four folds is positive.
    seq9_like = _by_id({
        "is_folds": [
            _fold("IS-F1", "2022-06-30", "-150.00", "0.7458"),
            _fold("IS-F2", "2022-12-30", "-90.00", "0.8120"),
            _fold("IS-F3", "2023-06-30", "60.00", "1.9200"),
            _fold("IS-F4", "2023-12-29", "120.00", "2.8257"),
        ],
    })
    assert seq9_like["CRIT-OVERFIT-03"].status.value == "FAIL"
    assert seq9_like["CRIT-OVERFIT-03"].computed_value == "0.5000"
    assert "IS-F1" in seq9_like["CRIT-OVERFIT-03"].evidence

    three_of_four = _by_id({
        "is_folds": [
            _fold("IS-F1", "2022-06-30", "10.00", "1.40"),
            _fold("IS-F2", "2022-12-30", "10.00", "1.35"),
            _fold("IS-F3", "2023-06-30", "10.00", "1.30"),
            _fold("IS-F4", "2023-12-29", "-1.00", "1.10"),
        ],
    })
    assert three_of_four["CRIT-OVERFIT-03"].status.value == "PASS"
    assert three_of_four["CRIT-OVERFIT-03"].computed_value == "0.7500"

    # A fold that clears its expectancy but not the PF floor is not positive.
    expectancy_only = _by_id({
        "is_folds": [
            _fold("IS-F1", "2022-06-30", "10.00", "1.29"),
            _fold("IS-F2", "2022-12-30", "10.00", "1.29"),
            _fold("IS-F3", "2023-06-30", "10.00", "1.29"),
            _fold("IS-F4", "2023-12-29", "10.00", "1.29"),
        ],
    })
    assert expectancy_only["CRIT-OVERFIT-03"].status.value == "FAIL"

    assert _by_id({})["CRIT-OVERFIT-03"].status.value == "NOT RUN"

    # An empty fold ledger is no evidence, not a failing fold: NOT RUN with the reason printed
    # (§9.3). A fold that holds trades but no positive one is still a FAIL above.
    empty_folds = _by_id({
        "is_folds": [
            {"label": f"IS-F{i}", "fold_end": end,
             "closed_net_expectancy": None, "liquidated_profit_factor": None}
            for i, end in enumerate(("2022-06-30", "2022-12-30", "2023-06-30", "2023-12-29"), 1)
        ],
    })
    assert empty_folds["CRIT-OVERFIT-03"].status.value == "NOT RUN"
    assert empty_folds["CRIT-OVERFIT-03"].computed_value is None
    assert "No closed or liquidated trade exited" in empty_folds["CRIT-OVERFIT-03"].evidence


def test_overfit05_gates_the_ex_top_1_margin():
    crit = _criteria()
    assert crit.min_liquidated_pf_ex_top_1 == Decimal("1.40")

    # seq 9's measured ex-top-1 PF clears the margin; a concentration-dependent PF does not.
    assert _by_id({"liquidated_pf_ex_top_1": Decimal("1.4812")})["CRIT-OVERFIT-05"].status.value == "PASS"
    assert _by_id({"liquidated_pf_ex_top_1": Decimal("1.3000")})["CRIT-OVERFIT-05"].status.value == "FAIL"
    assert _by_id({})["CRIT-OVERFIT-05"].status.value == "NOT RUN"


def test_criteria_1_1_7_adds_only_the_three_committed_bindings():
    crit = _criteria()
    assert crit.version == "1.1.13"
    assert crit.min_positive_is_fold_ratio == Decimal("0.75")
    assert crit.min_fold_liquidated_pf == Decimal("1.30")
    assert crit.min_liquidated_pf_ex_top_1 == Decimal("1.40")
    # Nothing that pre-existed moved.
    assert crit.min_total_trades == 100
    assert crit.min_profit_factor == Decimal("1.50")
    assert crit.min_deflated_sharpe_ratio == Decimal("0.95")
    assert crit.min_haircut_sharpe_ratio == Decimal("1.25")
    assert crit.max_single_position_weight == Decimal("0.10")
    assert crit.min_traded_eq_resolution_pct == Decimal("100.0")
    assert crit.min_dataset_instrument_resolution_pct == Decimal("100.0")
    assert crit.min_positive_walk_forward_fold_ratio == Decimal("0.80")
