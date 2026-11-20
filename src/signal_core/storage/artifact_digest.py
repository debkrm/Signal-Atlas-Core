"""The one definition of a tracked artifact's digest (Audit §102.3 Ruling 1).

A published digest is the sha256 of the byte sequence a reader of the repository will read:

* a **text** path — the stored form with CRLF normalised to LF. `.gitattributes` pins `* text=auto
  eol=lf`, `*.json`, `*.jsonl`, the audit volumes and `*.md` to `eol=lf`, so every clone stores the LF
  rendering and a digest of the writing checkout's CRLF rendering is a digest no clone can reproduce
  (N-203).
* a **binary** path — the stored bytes unmodified. A gzip stream is `-text` and has no LF form, so
  replacing CRLF bytes inside it hashes a stream no file contains (N-204).

The arms are separate functions rather than an argument because which one applies is a property of the
path, not of the caller's intent: a normaliser handed a binary is a silent defect of exactly the shape
§101 and §102 measured twice. Each arm therefore refuses the other's path instead of trusting its
caller, which is what makes "the digest names the bytes it hashes" true by construction.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Mirrors the `-text` rules in `.gitattributes` (`*.gz`, `*.json.gz`, `*.zip`, `*.csv.zip`). A path under
# `data/raw/circulars/` is `-text` too, but its payloads are captured `.html` and are digested as text.
BINARY_SUFFIXES = (".gz", ".zip")


def is_binary_path(path) -> bool:
    """Whether `.gitattributes` marks this path binary, i.e. its digest is of the stored bytes."""
    return Path(path).suffix.lower() in BINARY_SUFFIXES


def text_digest(path) -> str:
    """sha256 of a tracked **text** path's stored form (CRLF normalised to LF); refuses a binary path."""
    path = Path(path)
    if is_binary_path(path):
        raise ValueError(
            f"`{path}` is a binary payload: `.gitattributes` marks it `-text`, so it has no LF form and a "
            "normalising digest of it hashes a stream no file contains. Call `binary_digest` for the "
            "stored bytes (Audit §102.3 Ruling 1, N-204)"
        )
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def binary_digest(path) -> str:
    """sha256 of a **binary** path's stored bytes, unnormalised; refuses a text path."""
    path = Path(path)
    if not is_binary_path(path):
        raise ValueError(
            f"`{path}` is a text path: `.gitattributes` stores it with LF, so its unnormalised bytes are "
            "the writing checkout's line endings and not the bytes a clone reads. Call `text_digest` "
            "(Audit §102.3 Ruling 1, N-203)"
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()
