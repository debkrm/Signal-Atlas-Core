"""
Audit §87.5 Ruling 1 — capture eligibility is not gating eligibility.

Probe (2) of that Ruling: a probe that fails closed if an evaluated session set contains a
`WARMUP_NOT_GATABLE` session. These tests measure the guard itself, the refusal the readiness probe
prints by name, and the one consumer that builds an evaluation corpus from raw archives, so the
refusal is not merely a new function beside an unguarded loader (Audit §14.4).
"""

from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path

import pytest

from signal_core.storage.gating import (
    WARMUP_NOT_GATABLE,
    WarmupSessionGatingViolation,
    assert_no_warmup_sessions_in_evaluation,
    warmup_sessions_in,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_warmup_sessions_are_the_sessions_before_the_pin():
    # Criteria 1.1.13 / Audit §91.8 Ruling 1: the binding start is 2018-04-01, so only sessions
    # before it are warm-up; the captured 2018-2021 sessions are gating-eligible.
    sessions = [datetime.date(2018, 3, 29), datetime.date(2018, 4, 2), datetime.date(2021, 12, 31)]
    assert warmup_sessions_in(sessions, binding_start_date=datetime.date(2018, 4, 1)) == [
        datetime.date(2018, 3, 29),
    ]


def test_guard_refuses_a_warmup_session_and_names_it():
    with pytest.raises(WarmupSessionGatingViolation) as excinfo:
        assert_no_warmup_sessions_in_evaluation(
            [datetime.date(2017, 6, 1), datetime.date(2018, 4, 2)],
            label="test-evaluation-set",
            binding_start_date=datetime.date(2018, 4, 1),
        )
    message = str(excinfo.value)
    assert "test-evaluation-set" in message
    assert WARMUP_NOT_GATABLE in message
    assert "2017-06-01" in message


def test_guard_accepts_a_window_at_the_pin():
    inspected = assert_no_warmup_sessions_in_evaluation(
        [datetime.date(2018, 4, 2), datetime.date(2018, 4, 3)],
        label="test-evaluation-set",
        binding_start_date=datetime.date(2018, 4, 1),
    )
    assert inspected == 2


def test_readiness_probe_refuses_a_mis_scoped_verdict(tmp_path: Path):
    from scripts.probe_pre2022_preconditions import check_gating_mode

    mis_scoped = tmp_path / "mis_scoped_verdict.json"
    mis_scoped.write_text(
        json.dumps(
            {
                "evaluation_start_date": "2017-01-01",
                "evaluation_end_date": "2017-12-31",
                "overall_verdict": "GO",
            }
        ),
        encoding="utf-8",
    )

    results = check_gating_mode([mis_scoped])
    assert results, "the probe returned no measurement for a mis-scoped evaluation"
    statuses = {status for status, _ in results}
    assert statuses == {"NO"}, f"a pre-2022 evaluated set did not fail closed: {results}"
    message = " ".join(text for _, text in results)
    assert "mis_scoped_verdict.json" in message
    assert WARMUP_NOT_GATABLE in message


def test_committed_verdict_corpus_is_scoped_at_the_pin():
    from scripts.probe_pre2022_preconditions import check_gating_mode

    results = check_gating_mode()
    assert len(results) == 1, results
    status, message = results[0]
    assert status == "PASS", message
    assert "0 of " in message


def test_evaluation_corpus_builder_refuses_a_pre_pin_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import dataclasses

    import scripts.run_phase3b2_walkforward as walkforward
    from signal_core.contracts.criteria import load_go_no_go_criteria

    # The committed pin now begins 2018-04-01, so no archive on disk predates it. The guard is still
    # measured at the consumer: with a criteria pin at 2022-01-03, the 2018-04-02 archive is warm-up
    # and must be refused. The pin is the input, not the guard under test.
    pinned = dataclasses.replace(
        load_go_no_go_criteria(), min_binding_evaluation_start_date=datetime.date(2022, 1, 3)
    )
    monkeypatch.setattr(walkforward, "load_go_no_go_criteria", lambda: pinned)

    source = REPO_ROOT / "data" / "raw" / "2018" / "cm02APR2018bhav.csv.zip"
    shutil.copyfile(source, tmp_path / source.name)

    with pytest.raises(WarmupSessionGatingViolation) as excinfo:
        walkforward.build_historical_dataset_from_raw_bhavcopy(raw_dirs=[tmp_path])
    message = str(excinfo.value)
    assert WARMUP_NOT_GATABLE in message
    assert "2018-04-02" in message


def test_bronze_coverage_probe_attests_all_931_sessions(capsys: pytest.CaptureFixture[str]):
    from scripts.probe_pre2022_bronze_coverage import main

    assert main() == 0
    output = capsys.readouterr().out
    assert "931/931" in output
    assert WARMUP_NOT_GATABLE in output
