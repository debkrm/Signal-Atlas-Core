"""The one definition of a tracked artifact's digest (Audit §102.3 Ruling 1, §103.12 item 2).

A published digest is the sha256 of the byte sequence a reader of the repository will read:

* a **text** path — the stored form with CRLF normalised to LF. `.gitattributes` pins `* text=auto
  eol=lf`, `*.json`, `*.jsonl`, the audit volumes and `*.md` to `eol=lf`, so every clone stores the LF
  rendering and a digest of the writing checkout's CRLF rendering is a digest no clone can reproduce
  (N-203).
* a **binary** path — the stored bytes unmodified. A gzip stream has no LF form, so replacing CRLF bytes
  inside it hashes a stream no file contains (N-204).

Which arm applies is a property of the path, measured three ways rather than taken from its name:

1. the `-text` suffixes `.gitattributes` names (`*.gz`, `*.json.gz`, `*.zip`, `*.csv.zip`);
2. the `data/raw/circulars/*/**` `-text` glob, which is keyed on **where** the payload sits — each
   captured statutory source under `data/raw/circulars/<ref>/` keeps its own bytes, while the calendar
   circulars stored directly in `data/raw/circulars/*.json` are not matched and stay text;
3. the payload's own magic (`\\x1f\\x8b` for gzip, `PK\\x03\\x04`/`\\x05\\x06`/`\\x07\\x08` for zip), so
   gzip bytes named `.json` are refused by the text arm instead of being silently normalised.

The arms are separate functions rather than an argument because a normaliser handed a binary is a silent
defect of exactly the shape §101 and §102 measured twice. Each arm therefore refuses the other's path
instead of trusting its caller, which is what makes "the digest names the bytes it hashes" true by
construction.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Mirrors the `-text` suffix rules in `.gitattributes` (`*.gz`, `*.json.gz`, `*.zip`, `*.csv.zip`).
BINARY_SUFFIXES = (".gz", ".zip")

# The payload the suffix cannot be trusted for: a compressed container is bytes whatever it is called.
BINARY_MAGIC = (b"\x1f\x8b", b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

# `.gitattributes`'s fourth `-text` rule, `data/raw/circulars/*/**`: one directory component (the
# circular reference) and then the captured payload. The rule is last-match-wins and sits after every
# `text` rule, so a nested payload's CRLF bytes are what git stores (§96.2 → §97, N-186).
CAPTURED_CIRCULARS_DIRS = ("data", "raw", "circulars")


def is_captured_circular_path(path) -> bool:
    """Whether `.gitattributes`'s `data/raw/circulars/*/**` rule makes this path binary."""
    parts = Path(path).parts
    for index in range(len(parts) - 2):
        if parts[index:index + 3] == CAPTURED_CIRCULARS_DIRS:
            # `<ref>/<payload>`: at least two components below the circulars directory.
            return len(parts) - (index + 3) >= 2
    return False


def _has_binary_magic(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(4).startswith(BINARY_MAGIC)


def is_binary_path(path) -> bool:
    """Whether this path's digest is of the stored bytes, by suffix, location or payload magic."""
    path = Path(path)
    if path.suffix.lower() in BINARY_SUFFIXES or is_captured_circular_path(path):
        return True
    return _has_binary_magic(path)


def text_bytes(path) -> bytes:
    """The stored form of a tracked **text** path (CRLF normalised to LF); refuses a binary path."""
    path = Path(path)
    if is_binary_path(path):
        raise ValueError(
            f"`{path}` is a binary payload: `.gitattributes` marks it `-text` or its bytes are a gzip/zip "
            "stream, so it has no LF form and a normalising digest of it hashes a stream no file "
            "contains. Call `binary_digest` for the stored bytes (Audit §102.3 Ruling 1, §103.12 item 2)"
        )
    return path.read_bytes().replace(b"\r\n", b"\n")


def text_digest(path) -> str:
    """sha256 of a tracked **text** path's stored form (CRLF normalised to LF); refuses a binary path."""
    return hashlib.sha256(text_bytes(path)).hexdigest()


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
