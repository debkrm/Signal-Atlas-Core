#!/usr/bin/env python3
"""
The predecessor a regenerated artifact replaced (Audit §102.10, §102.14 item 5).

Two published artifacts were rewritten in place rather than restated at a new path: the s100 baseline
comparison at `325bab8` (replacing the revision `eea1757` wrote) and the s102 Step 2 QA at `325bab8`
(replacing `46a99ec`). Both rewrites are recoverable only from git history, so a reader who wants to know
what moved has to walk the log and diff two blobs by hand. This publishes that revision beside the
artifact instead: its commit, the digest of its **stored** bytes (Audit §102.3 Ruling 1), and the fields
added, removed and changed between the two revisions.

Two properties are deliberate. The commit is **pinned**, not derived from `HEAD`: a predecessor taken from
`HEAD` names a different revision after every commit, so the artifact would stop reproducing from the tree
that stores it. And the movement is **computed from the blob**, not typed into the artifact, so a pointer
cannot claim a change the bytes do not show — `tests/unit/test_phase3b2_audit_s104_items.py` recomputes
both from `git cat-file blob` and refuses a digest or a field list that disagrees.

The cost, published in the pointer itself: verifying it needs the predecessor **object**, so the reading
checkout must carry full git history. A shallow clone that fetched only the tip, or a `git archive` export
with no repository at all, cannot resolve `<commit>:<path>` and the producers' `--check` exits 1 by name
rather than publishing a pointer it cannot verify (Audit §103.5, §103.12 item 4).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent


def _stored_blob(repo_root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=str(repo_root),
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"cannot read the predecessor blob {commit}:{path} — the artifact must name the revision it "
            f"replaced, and a checkout without that object cannot publish it: "
            f"{result.stderr.decode('utf-8', 'replace').strip()} (§102.14 item 5, §12.1)"
        )
    return result.stdout


def predecessor_pointer(path: str, commit: str, payload: Dict, repo_root: Path = REPO_ROOT) -> Dict:
    """
    The revision of `path` that `payload` replaced, its stored bytes' digest, and the fields that moved.

    `payload` is the successor as it will be written, before this pointer is added to it; the diff is
    therefore between the two revisions' own fields and not between a revision and itself.
    """
    previous_bytes = _stored_blob(repo_root, commit, path)
    previous = json.loads(previous_bytes.decode("utf-8"))
    current = {key: value for key, value in payload.items() if key != "predecessor"}
    return {
        "path": path,
        "commit": commit,
        "sha256": hashlib.sha256(previous_bytes).hexdigest(),
        "sha256_of": (
            "the predecessor blob's stored bytes exactly as `git cat-file blob <commit>:<path>` returns "
            "them; this path is `eol=lf` in .gitattributes, so they are also the LF-normalised form every "
            "clone reads (Audit §102.3 Ruling 1)"
        ),
        "verification_requires": (
            "full git history: the pointer is verified by reading `git cat-file blob <commit>:<path>` for "
            "the pinned commit, so a shallow clone that fetched only the tip, or a `git archive` export "
            "with no repository, cannot verify it and the producer's `--check` refuses by name rather "
            "than publishing a pointer it cannot substantiate (Audit §103.5, §103.12 item 4)"
        ),
        "fields_added": sorted(set(current) - set(previous)),
        "fields_removed": sorted(set(previous) - set(current)),
        "fields_changed": sorted(
            key for key in set(current) & set(previous) if current[key] != previous[key]
        ),
    }
