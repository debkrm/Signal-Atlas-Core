"""
Fail-Closed Per-Artifact Verification of the Reference Manifest (Finding H-118).

The reference manifest attests a `byte_count` and a `sha256` for every artifact it lists.
Until Audit §69 the pin only protected the *attestation* — `manifest.jsonl` itself — so a
corpus could be edited without the manifest changing and every gate still passed. This module
recomputes both attrs against the file on disk and refuses to continue on any mismatch.

Scope: rows with `is_current: true`. Superseded rows are history whose bytes were
intentionally replaced at the same path (e.g. successive `cash_equity_symbol_intervals.csv`
derivations), so they cannot be verified against the current file; they are counted and reported.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


class ManifestIntegrityError(RuntimeError):
    """Raised when a manifest attestation does not match the artifact it describes."""


_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = _REPO_ROOT / "data" / "reference" / "manifest.jsonl"
DEFAULT_ARTIFACT_ROOTS: Tuple[Path, ...] = (
    _REPO_ROOT / "data" / "reference",
    _REPO_ROOT / "data" / "raw",
    _REPO_ROOT,
)


def resolve_manifest_artifact(
    artifact: str,
    roots: Sequence[Path] = DEFAULT_ARTIFACT_ROOTS,
) -> Optional[Path]:
    """Locates a manifest `artifact` path under the committed reference/raw/root directories."""
    rel = Path(artifact)
    if rel.is_absolute():
        return rel if rel.is_file() else None
    for root in roots:
        candidate = Path(root) / rel
        if candidate.is_file():
            return candidate
    return None


def verify_manifest_artifacts(
    manifest_path: Optional[Union[str, Path]] = None,
    roots: Sequence[Path] = DEFAULT_ARTIFACT_ROOTS,
) -> Dict[str, Any]:
    """
    Recomputes `byte_count` and `sha256` for every current manifest row.

    Returns a summary dict (`verified`, `superseded`, `paths`). Raises
    `ManifestIntegrityError` on a missing artifact, an incomplete attestation, a byte-count
    mismatch, or a digest mismatch. Nothing is rewritten.
    """
    mpath = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH
    if not mpath.is_file():
        raise ManifestIntegrityError(f"Reference manifest not found at {mpath}")

    verified_paths: List[str] = []
    verified = 0
    superseded = 0

    with mpath.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:  # noqa: BLE001 - fail closed on malformed attestation
                raise ManifestIntegrityError(
                    f"Line {line_no}: malformed JSON in {mpath.name}: {exc}"
                ) from exc

            # N-124: `is_current` must be an explicit boolean. A missing or non-boolean flag is not
            # history — it is an attestation the verifier cannot classify, so it fails closed rather
            # than silently leaving the verified set.
            is_current = row.get("is_current")
            if not isinstance(is_current, bool):
                raise ManifestIntegrityError(
                    f"Line {line_no}: row for {row.get('artifact')!r} has no explicit boolean "
                    f"'is_current' (got {is_current!r}); every row must state it (Finding N-124)"
                )
            if is_current is False:
                superseded += 1
                continue

            artifact = row.get("artifact")
            expected_bytes = row.get("byte_count")
            expected_sha = row.get("sha256")
            if not isinstance(artifact, str) or not artifact.strip():
                raise ManifestIntegrityError(
                    f"Line {line_no}: current row has no artifact name: {row!r}"
                )
            if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
                raise ManifestIntegrityError(
                    f"Line {line_no}: current row for {artifact!r} has no integer byte_count"
                )
            if isinstance(expected_sha, bool) or not isinstance(expected_sha, str) or len(expected_sha) != 64:
                raise ManifestIntegrityError(
                    f"Line {line_no}: current row for {artifact!r} has no 64-hex sha256"
                )

            path = resolve_manifest_artifact(artifact, roots)
            if path is None:
                raise ManifestIntegrityError(
                    f"Line {line_no}: attested artifact {artifact!r} not found under "
                    f"{[str(r) for r in roots]}"
                )

            payload = path.read_bytes()
            if len(payload) != expected_bytes:
                raise ManifestIntegrityError(
                    f"Line {line_no}: {artifact} is {len(payload)} bytes on disk but the manifest "
                    f"attests {expected_bytes} (Finding H-118)"
                )
            actual_sha = hashlib.sha256(payload).hexdigest()
            if actual_sha != expected_sha:
                raise ManifestIntegrityError(
                    f"Line {line_no}: {artifact} has sha256 {actual_sha} on disk but the manifest "
                    f"attests {expected_sha} (Finding H-118)"
                )

            verified += 1
            verified_paths.append(str(path))

    return {
        "verified": verified,
        "superseded": superseded,
        "paths": verified_paths,
        "manifest": str(mpath),
    }
