"""Audit §103 work order (feat-s105) — the four measurements this round adds, tested directly.

1. Ruling 1 at every producer (§103.4, item 2/A): a normalising digest is `artifact_digest`'s and no
   producer defines a second one, so each of the four remaining producers refuses a gzip payload by
   construction instead of hashing a mutated stream no file contains (N-204).
2. The binary key is the payload, not only the name (§103.2, item 2/B): gzip bytes named `.json` are
   refused by the text arm, and `.gitattributes`'s fourth `-text` rule — the captured circular payloads
   under `data/raw/circulars/<ref>/` — is mirrored rather than claimed.
3. The seq-10 consumer leaves the tracked s94 artifact alone (§103.3, item 3/C): two consecutive
   publishes that differ only in `timestamp_utc` leave the tree unchanged.
4. The history requirement is stated where a reader meets it (§103.5, item 4/D): both `--check` help
   texts and both artifacts' `predecessor` pointer name it, because a pointer is verified against a
   commit object a shallow clone or an exported tree does not carry.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts import compare_seq10_baselines, derive_2018_2023_corpus, probe_hold_bound_invariance
from scripts import run_seq10_candidate, run_seq12_candidate
from signal_core.contracts import criteria as criteria_module
from signal_core.storage import artifact_digest, circulars

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The gzip header with a CRLF pair inside it: a normaliser handed these bytes hashes another stream.
GZIP_PAYLOAD = b"\x1f\x8b\x08\x00\r\n\x00\r\n\x00\x00payload"

# Module and attribute, resolved inside the test: on the base tree the producer does not exist, and the
# case must fail there rather than fail collection.
PRODUCERS = (
    ("criteria.compute_manifest_fingerprint", criteria_module, "compute_manifest_fingerprint"),
    ("circulars.circular_payload_digest", circulars, "circular_payload_digest"),
    ("derive_2018_2023_corpus.corporate_actions_fingerprint", derive_2018_2023_corpus, "corporate_actions_fingerprint"),
    ("probe_hold_bound_invariance._digest", probe_hold_bound_invariance, "_digest"),
)


# --- 1. every producer refuses a binary payload rather than normalising it (item A) --------


@pytest.mark.parametrize("label,module,attribute", PRODUCERS, ids=[entry[0] for entry in PRODUCERS])
def test_each_producer_refuses_a_gzip_payload(label, module, attribute, tmp_path: Path):
    producer = getattr(module, attribute)
    payload = tmp_path / "corporate_actions.jsonl.gz"
    payload.write_bytes(GZIP_PAYLOAD)
    with pytest.raises(ValueError) as refusal:
        producer(payload)
    assert "binary" in str(refusal.value), str(refusal.value)
    assert "Ruling 1" in str(refusal.value), str(refusal.value)


def test_the_manifest_fingerprint_is_the_published_value_through_the_shared_arm():
    """Routing the producer must not move the value every criteria pin copies (§103.12 item 2)."""
    config = criteria_module.load_go_no_go_criteria()
    published = criteria_module.compute_manifest_fingerprint(REPO_ROOT / "data" / "reference" / "manifest.jsonl")
    assert published == config.expected_manifest_fingerprint, (published, config.expected_manifest_fingerprint)
    assert published.startswith(criteria_module.MANIFEST_FINGERPRINT_PREFIX), published


def test_a_circular_payload_digest_is_the_manifest_row(tmp_path: Path):
    """The circular producer still publishes the digest and byte count the manifest records."""
    row = next(
        json.loads(line)
        for line in (REPO_ROOT / "data" / "reference" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("artifact", "").endswith("/NSE_CMTR_36475.json")
        and json.loads(line).get("is_current")
    )
    path = REPO_ROOT / "data" / "raw" / "circulars" / "NSE_CMTR_36475.json"
    digest, stored = circulars.circular_payload_digest(path)
    assert digest == row["sha256"], (digest, row["sha256"])
    assert len(stored) == row["byte_count"], (len(stored), row["byte_count"])


# --- 2. the binary key is the payload and the glob, not only the suffix (item B) -----------


def test_the_text_arm_refuses_gzip_bytes_named_json(tmp_path: Path):
    payload = tmp_path / "artifact.json"
    payload.write_bytes(GZIP_PAYLOAD)
    with pytest.raises(ValueError) as refusal:
        artifact_digest.text_digest(payload)
    assert "binary" in str(refusal.value), str(refusal.value)
    # The same bytes are a binary payload whatever the name says, so the binary arm must hash them.
    assert artifact_digest.binary_digest(payload) == hashlib.sha256(GZIP_PAYLOAD).hexdigest()


def test_the_binary_arm_refuses_gzip_bytes_named_without_a_suffix(tmp_path: Path):
    payload = tmp_path / "corpus"
    payload.write_bytes(GZIP_PAYLOAD)
    assert artifact_digest.binary_digest(payload) == hashlib.sha256(GZIP_PAYLOAD).hexdigest()
    with pytest.raises(ValueError):
        artifact_digest.text_digest(payload)


def test_the_captured_circulars_glob_is_a_binary_path(tmp_path: Path):
    """`.gitattributes`'s `data/raw/circulars/*/**` is `-text`; the module must not claim otherwise."""
    captured = tmp_path / "data" / "raw" / "circulars" / "MAHARASHTRA_STAMP_DUTY_2019" / "payload.html"
    captured.parent.mkdir(parents=True)
    captured.write_bytes(b"<html>\r\nrate\r\n</html>\r\n")
    assert artifact_digest.is_binary_path(captured), (
        f"`{captured}` sits under `data/raw/circulars/*/**`, which `.gitattributes` marks `-text`, so its "
        "digest is of the stored bytes (Audit §103.2, §103.12 item 2)"
    )
    with pytest.raises(ValueError):
        artifact_digest.text_digest(captured)


def test_the_calendar_circulars_stay_text(tmp_path: Path):
    """The same rule does not reach `data/raw/circulars/*.json`, which the `*.json` rule pins to LF."""
    calendar = tmp_path / "data" / "raw" / "circulars" / "NSE_CMTR_1.json"
    calendar.parent.mkdir(parents=True)
    stored = b'{\n "circular_id": "NSE/CMTR/1"\n}\n'
    calendar.write_bytes(stored.replace(b"\n", b"\r\n"))
    assert not artifact_digest.is_binary_path(calendar)
    assert artifact_digest.text_digest(calendar) == hashlib.sha256(stored).hexdigest()


# --- 3. the seq-10 consumer stops rewriting the tracked s94 artifact (item C) --------------


S94_ARTIFACT = REPO_ROOT / "reports" / "analysis" / "s94" / "seq10_baseline_2018_2023_verdict.json"


def _verdict_payload(timestamp: str) -> dict:
    return {
        "criteria_version": "1.1.16",
        "criteria_fingerprint": "CRIT-FPR-V1-00",
        "timestamp_utc": timestamp,
        "overall_verdict": "KILL",
        "summary_counts": {"closed_trades": 422},
    }


def test_two_consecutive_publishes_leave_the_tracked_artifact_unchanged(tmp_path: Path):
    destination = tmp_path / "reports" / "analysis" / "s94" / "seq10_baseline_2018_2023_verdict.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(_verdict_payload("2026-11-19T07:19:25.918855+00:00")), encoding="utf-8")
    committed = destination.read_bytes()

    first = tmp_path / "run_a" / "seq10.json"
    first.parent.mkdir(parents=True)
    first.write_text(json.dumps(_verdict_payload("2026-11-20T18:21:11.683314+00:00")), encoding="utf-8")
    second = tmp_path / "run_b" / "seq10.json"
    second.parent.mkdir(parents=True)
    second.write_text(json.dumps(_verdict_payload("2026-11-21T09:00:00.000000+00:00")), encoding="utf-8")

    assert run_seq10_candidate.publish_baseline_artifact(first, destination) is False
    assert run_seq10_candidate.publish_baseline_artifact(second, destination) is False
    assert destination.read_bytes() == committed, (
        "a run whose payload matches the committed artifact apart from `timestamp_utc` rewrote it, so the "
        "committed digest reproduces only until the consumer is run (Audit §103.3)"
    )


def test_a_publish_that_changes_content_is_refused_by_name(tmp_path: Path):
    """§104.12 item 1 tightened this case: a changed payload is refused, not copied over the artifact."""
    destination = tmp_path / "s94" / "seq10.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(_verdict_payload("2026-11-19T07:19:25.918855+00:00")), encoding="utf-8")
    committed = destination.read_bytes()

    changed = _verdict_payload("2026-11-20T18:21:11.683314+00:00")
    changed["summary_counts"] = {"closed_trades": 423}
    fresh = tmp_path / "fresh" / "seq10.json"
    fresh.parent.mkdir(parents=True)
    fresh.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(run_seq10_candidate.BaselinePublishRefused) as refusal:
        run_seq10_candidate.publish_baseline_artifact(fresh, destination)
    assert "summary_counts.closed_trades" in str(refusal.value)
    assert destination.read_bytes() == committed


def test_the_tracked_baseline_artifact_is_the_one_its_digest_is_recorded_for():
    """The trial_010 comparison publishes this path's digest, so a run must not move it (item C)."""
    comparison = json.loads(
        (REPO_ROOT / "reports" / "verdicts" / "trial_010" / "seq10_baseline_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    assert comparison["baseline"]["path"] == S94_ARTIFACT.relative_to(REPO_ROOT).as_posix()
    assert comparison["baseline"]["sha256"] == artifact_digest.text_digest(S94_ARTIFACT), (
        "the published baseline digest no longer names the committed artifact, which is what a run that "
        "rewrote `timestamp_utc` in place produced (Audit §103.3)"
    )


# --- 4. the history requirement is stated where a reader meets it (item D) -----------------


@pytest.mark.parametrize(
    "relative",
    ("reports/analysis/s100/seq10_baseline_comparison.json", "reports/analysis/s102/seq12_data_qa.json"),
)
def test_the_predecessor_pointer_states_the_history_requirement(relative: str):
    artifact = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
    requirement = artifact["predecessor"]["verification_requires"]
    assert "full git history" in requirement, requirement
    assert "shallow clone" in requirement and "git archive" in requirement, requirement


@pytest.mark.parametrize(
    "module,arguments",
    ((compare_seq10_baselines, ["--help"]), (run_seq12_candidate, ["--help"])),
    ids=("compare_seq10_baselines", "run_seq12_candidate"),
)
def test_the_check_help_states_the_history_requirement(module, arguments, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", [module.__name__, *arguments])
    with pytest.raises(SystemExit) as exited:
        module.main()
    assert exited.value.code == 0
    help_text = capsys.readouterr().out
    assert "--check" in help_text, help_text
    assert "full git history" in help_text, (
        f"`{module.__name__} --check` cannot verify a predecessor pointer without the commit object, and "
        "its help does not say so (Audit §103.5, §103.12 item 4)"
    )
