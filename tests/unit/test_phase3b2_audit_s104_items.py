"""Audit §102 work order (feat-s104) — the two measurements this round adds, tested directly.

1. Ruling 1 (§102.3, item 4): a digest field's subject is the byte sequence it hashes. A text path is
   digested in its LF-normalised stored form and a binary path in its stored bytes, so the two arms are
   separate functions and each refuses the other's path by construction — a normaliser handed a `.gz`
   hashes a stream no file contains (N-204).
2. Restatement discipline (§102.10, item 5): a regenerated artifact names the revision of its own path
   that it replaced, published as a digest of that revision's stored bytes and the fields that moved.
   Both are recomputed here from `git cat-file blob`, so the pointer is not a claim about itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import compare_seq10_baselines, run_seq10_candidate, run_seq11_candidate, run_seq12_candidate

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Every function that publishes or compares a tracked text artifact's digest, oldest caller first.
TEXT_DIGESTERS = (
    ("run_seq10_candidate._digest", run_seq10_candidate._digest),
    ("run_seq11_candidate._digest", run_seq11_candidate._digest),
    ("compare_seq10_baselines._sha256", compare_seq10_baselines._sha256),
    ("run_seq12_candidate._digest_text", run_seq12_candidate._digest_text),
)
BINARY_DIGESTERS = (
    ("compare_seq10_baselines._sha256_bytes", compare_seq10_baselines._sha256_bytes),
    ("run_seq12_candidate._digest_bytes", run_seq12_candidate._digest_bytes),
)


@pytest.mark.parametrize("label,digest", TEXT_DIGESTERS, ids=[label for label, _ in TEXT_DIGESTERS])
def test_a_text_digest_refuses_a_binary_path(label, digest, tmp_path: Path):
    payload = tmp_path / "corpus.json.gz"
    # A gzip-shaped byte string that contains CRLF pairs, so a normaliser would silently hash another stream.
    payload.write_bytes(b"\x1f\x8b\x08\x00\r\n\x00\r\n\x00\x00")
    with pytest.raises(ValueError) as refusal:
        digest(payload)
    assert "binary" in str(refusal.value), str(refusal.value)
    assert "Ruling 1" in str(refusal.value), str(refusal.value)


@pytest.mark.parametrize("label,digest", BINARY_DIGESTERS, ids=[label for label, _ in BINARY_DIGESTERS])
def test_a_binary_digest_refuses_a_text_path(label, digest, tmp_path: Path):
    payload = tmp_path / "artifact.json"
    payload.write_bytes(b'{\n "a": 1\n}\n')
    with pytest.raises(ValueError) as refusal:
        digest(payload)
    assert "text" in str(refusal.value), str(refusal.value)


def test_the_two_arms_are_the_documented_byte_sequences(tmp_path: Path):
    from signal_core.storage.artifact_digest import binary_digest, text_digest

    text = tmp_path / "artifact.json"
    raw = b'{\n "a": 1\n}\n'
    text.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert text_digest(text) == hashlib.sha256(raw).hexdigest()

    binary = tmp_path / "corpus.json.gz"
    payload = b"\x1f\x8b\x08\x00\r\n\n\r\n"
    binary.write_bytes(payload)
    assert binary_digest(binary) == hashlib.sha256(payload).hexdigest()


# --- 2. the predecessor a regenerated artifact replaced (item 5) ---------------------------

REGENERATED_ARTIFACTS = (
    "reports/analysis/s100/seq10_baseline_comparison.json",
    "reports/analysis/s102/seq12_data_qa.json",
)


def _stored_blob(commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{relative}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout


@pytest.mark.parametrize("relative", REGENERATED_ARTIFACTS)
def test_a_regenerated_artifact_names_the_revision_it_replaced(relative: str):
    artifact = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
    pointer = artifact.get("predecessor")
    assert pointer is not None, (
        f"`{relative}` was rewritten in place and publishes no predecessor: a reader cannot recover the "
        "bytes it replaced without walking git history (N-201 §102.10, item 5)"
    )
    assert pointer["path"] == relative, (pointer["path"], relative)
    assert isinstance(pointer["sha256_of"], str) and "stored" in pointer["sha256_of"], pointer["sha256_of"]

    previous_bytes = _stored_blob(pointer["commit"], relative)
    assert hashlib.sha256(previous_bytes).hexdigest() == pointer["sha256"], (
        f"the published predecessor digest is {pointer['sha256']}, and the blob at "
        f"{pointer['commit']}:{relative} hashes {hashlib.sha256(previous_bytes).hexdigest()}"
    )
    assert pointer["sha256"] != hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest(), (
        "the predecessor pointer names the current bytes, so it points at itself"
    )

    previous = json.loads(previous_bytes.decode("utf-8"))
    current = {key: value for key, value in artifact.items() if key != "predecessor"}
    assert pointer["fields_added"] == sorted(set(current) - set(previous)), pointer["fields_added"]
    assert pointer["fields_removed"] == sorted(set(previous) - set(current)), pointer["fields_removed"]
    assert pointer["fields_changed"] == sorted(
        key for key in set(current) & set(previous) if current[key] != previous[key]
    ), pointer["fields_changed"]
