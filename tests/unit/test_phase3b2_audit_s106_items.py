"""Audit §104.12 items 1-2 — the s94 publish refuses real payloads, and the duplicate is decided first.

Every fixture-fed case below uses `tests/fixtures/s94_run_a_payload_capture.json`, the bytes
`run_seq10_candidate.py` itself copied onto `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json`
during a real end-to-end execution at `52d4679` (captured after the run, from the file the run wrote, and
restored from the committed blob). It is the producer's own output — not a hand-built copy of the
committed artifact — so the guard's refusal is measured against the input a run actually delivers
(Audit §104.4, §104.6, §14.4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

import scripts.run_seq10_candidate as run_seq10_candidate  # noqa: E402
from signal_core.storage.artifact_digest import text_digest  # noqa: E402

S94_ARTIFACT = REPO_ROOT / "reports" / "analysis" / "s94" / "seq10_baseline_2018_2023_verdict.json"
CAPTURE = REPO_ROOT / "tests" / "fixtures" / "s94_run_a_payload_capture.json"
COMMITTED_DIGEST = "f5fe3af5a1e2de836472d5d3bdbec658fd98f9cd81c33576d48004a83188072c"


def _staged_destination(tmp_path: Path) -> Path:
    """The committed artifact at a writable path, so a refusal can be shown to have written nothing."""
    destination = tmp_path / "reports" / "analysis" / "s94" / "seq10_baseline_2018_2023_verdict.json"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(S94_ARTIFACT.read_bytes())
    return destination


def test_the_publish_refuses_the_payload_a_real_run_writes(tmp_path: Path):
    destination = _staged_destination(tmp_path)
    before = destination.read_bytes()

    with pytest.raises(run_seq10_candidate.BaselinePublishRefused) as refusal:
        run_seq10_candidate.publish_baseline_artifact(CAPTURE, destination)

    message = str(refusal.value)
    for key in ("criteria_fingerprint", "evaluated_trial_count", "demerger_forced_refusals"):
        assert key in message, (
            f"the refusal does not name the moved key `{key}`, so a maintainer cannot tell what a run "
            f"would have replaced (Audit §104.12 item 1): {message}"
        )
    assert destination.read_bytes() == before, (
        "the guard refused the payload but still wrote: a published artifact is restated by append, never "
        "overwritten by a re-run (§10.1)"
    )
    assert text_digest(destination) == COMMITTED_DIGEST


def test_the_capture_is_the_producers_output_and_not_a_timestamp_copy():
    payload = json.loads(CAPTURE.read_text(encoding="utf-8"))
    committed = json.loads(S94_ARTIFACT.read_text(encoding="utf-8"))
    for key in ("daily_returns", "evaluations", "hold_bound_forced_exits", "timestamp_utc"):
        assert key in payload, f"the capture is not a run-A verdict artifact: it carries no `{key}`"

    differing = run_seq10_candidate._differing_paths(
        run_seq10_candidate._without_timestamp(committed),
        run_seq10_candidate._without_timestamp(payload),
    )
    assert differing, (
        "the committed fixture differs from the committed artifact only in timestamp_utc, which is the "
        "hand-built input the guard's green case needed and a real run cannot produce (Audit §104.4)"
    )
    for key in ("criteria_fingerprint", "evaluated_trial_count", "demerger_forced_refusals"):
        assert key in differing, f"the capture does not move `{key}`, so it exercises no cell of §104.4's table"
    assert payload["demerger_forced_refusals"] != committed["demerger_forced_refusals"]


def test_a_publish_identified_by_timestamp_only_keeps_the_bytes(tmp_path: Path):
    destination = tmp_path / "s94" / "seq10.json"
    destination.parent.mkdir(parents=True)
    assert run_seq10_candidate.publish_baseline_artifact(CAPTURE, destination) is True
    published = destination.read_bytes()

    later = json.loads(CAPTURE.read_text(encoding="utf-8"))
    later["timestamp_utc"] = "2026-11-21T00:00:00+00:00"
    fresh = tmp_path / "later" / "seq10.json"
    fresh.parent.mkdir(parents=True)
    fresh.write_text(json.dumps(later), encoding="utf-8")

    assert run_seq10_candidate.publish_baseline_artifact(fresh, destination) is False, (
        "a second run whose payload differs only in timestamp_utc was not recognised as the same artifact"
    )
    assert destination.read_bytes() == published


def test_a_registered_trial_refuses_before_any_evaluation_or_publish(monkeypatch, capsys):
    """The registry of record already holds seq 10, so this is the tree a second run finds (§104.12 item 2)."""
    touched: list[str] = []

    def _refuse(*_args, **_kwargs):
        touched.append("reached")
        raise AssertionError(
            "an already-registered seq 10 reached the dataset or the publish step: the duplicate is being "
            "discovered after the artifact has been written (Audit §104.4)"
        )

    monkeypatch.setattr(run_seq10_candidate.walkforward, "resolve_or_build_historical_dataset", _refuse)
    monkeypatch.setattr(run_seq10_candidate, "publish_baseline_artifact", _refuse)

    assert run_seq10_candidate.main() == 1
    assert touched == []
    output = capsys.readouterr().out
    assert "TRIAL-PHASE3B2-EXPANDED-010 is already registered" in output, (
        f"the refusal does not name the registered trial: {output}"
    )
