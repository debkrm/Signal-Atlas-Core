"""
Bronze Layer: Byte-Exact Raw Archive Storage and Provenance Manifest.

Implements raw storage integrity per AGENTS.md Rule 10.1 and Rule 10.7:
- Bronze payloads are byte-exact as retrieved and are never mutated or edited.
- Every retrieval records source URL, retrieval timestamp, byte count, and SHA-256 in an append-only manifest.
- Tamper detection fails closed: any modification, bit flip, or truncation raises TamperedBronzePayloadError (Gate G2B.5-1).
"""

from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union


class BronzeStorageError(ValueError):
    """Base exception for bronze storage failures."""
    pass


class TamperedBronzePayloadError(BronzeStorageError):
    """Raised when an archived bronze payload fails cryptographic SHA-256 or size verification."""
    pass


class MissingBronzeManifestError(BronzeStorageError):
    """Raised when an archived payload lacks a corresponding authoritative manifest record."""
    pass


@dataclass(frozen=True, slots=True)
class BronzeManifestEntry:
    """
    Immutable manifest record documenting a byte-exact raw payload retrieval.
    """
    relative_path: str
    source_url: str
    retrieved_at: str
    byte_count: int
    sha256: str

    def to_json_dict(self) -> Dict[str, Union[str, int]]:
        return {
            "relative_path": self.relative_path,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Union[str, int]]) -> "BronzeManifestEntry":
        return cls(
            relative_path=str(data["relative_path"]),
            source_url=str(data["source_url"]),
            retrieved_at=str(data["retrieved_at"]),
            byte_count=int(data["byte_count"]),
            sha256=str(data["sha256"]),
        )


class BronzeStorage:
    """
    Manages byte-exact raw archives and their append-only audit manifest.
    """
    def __init__(self, root_dir: Union[str, Path]) -> None:
        self._root_dir = Path(root_dir).resolve()
        self._manifest_path = self._root_dir / "manifest.jsonl"
        self._root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolves relative path within root_dir, preventing directory traversal."""
        clean_rel = Path(relative_path)
        if clean_rel.is_absolute():
            raise BronzeStorageError(f"Absolute paths not permitted in bronze storage: {relative_path}")
        target = (self._root_dir / clean_rel).resolve()
        try:
            target.relative_to(self._root_dir)
        except ValueError:
            raise BronzeStorageError(f"Path traversal detected: {relative_path}")
        return target

    def store_payload(
        self,
        relative_path: str,
        data: bytes,
        source_url: str,
        retrieved_at: Optional[datetime.datetime] = None,
    ) -> BronzeManifestEntry:
        """
        Atomically stores raw payload bytes and records provenance entry in manifest.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise BronzeStorageError(f"Payload data must be bytes, got {type(data).__name__}")
        if not relative_path or not relative_path.strip():
            raise BronzeStorageError("relative_path cannot be empty.")
        if not source_url or not source_url.strip():
            raise BronzeStorageError("source_url cannot be empty.")

        target_path = self._resolve_safe_path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write to temporary file then replace
        temp_file = target_path.with_suffix(f".tmp_{os.getpid()}_{datetime.datetime.now().timestamp()}")
        try:
            with open(temp_file, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            temp_file.replace(target_path)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

        # Compute SHA-256 and byte count
        byte_count = len(data)
        sha256_digest = hashlib.sha256(data).hexdigest()
        ts = retrieved_at or datetime.datetime.now(datetime.timezone.utc)
        ts_str = ts.isoformat()

        entry = BronzeManifestEntry(
            relative_path=relative_path.replace("\\", "/"),
            source_url=source_url,
            retrieved_at=ts_str,
            byte_count=byte_count,
            sha256=sha256_digest,
        )

        # Append to manifest.jsonl
        manifest_line = json.dumps(entry.to_json_dict(), sort_keys=True) + "\n"
        with open(self._manifest_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(manifest_line)
            f.flush()
            os.fsync(f.fileno())

        return entry

    def load_manifest(self) -> List[BronzeManifestEntry]:
        """Loads and parses all records from manifest.jsonl."""
        if not self._manifest_path.exists():
            return []
        entries: List[BronzeManifestEntry] = []
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                clean = line.strip()
                if not clean:
                    continue
                try:
                    data = json.loads(clean)
                    entries.append(BronzeManifestEntry.from_json_dict(data))
                except Exception as exc:
                    raise BronzeStorageError(f"Corrupt manifest line {line_no} in {self._manifest_path}: {line}") from exc
        return entries

    def get_manifest_entry(self, relative_path: str) -> Optional[BronzeManifestEntry]:
        """Finds latest manifest entry for relative_path."""
        normalized = relative_path.replace("\\", "/")
        entries = self.load_manifest()
        for e in reversed(entries):
            if e.relative_path == normalized:
                return e
        return None

    def read_payload(self, relative_path: str, verify: bool = True) -> bytes:
        """
        Reads payload bytes from disk. If verify is True (default), verifies
        exact byte count and SHA-256 against manifest before returning.
        Fails closed with TamperedBronzePayloadError if modified (Gate G2B.5-1).
        """
        target_path = self._resolve_safe_path(relative_path)
        if not target_path.is_file():
            raise FileNotFoundError(f"Bronze payload file not found: {target_path}")

        with open(target_path, "rb") as f:
            data = f.read()

        if verify:
            entry = self.get_manifest_entry(relative_path)
            if entry is None:
                raise MissingBronzeManifestError(
                    f"No manifest entry found for payload {relative_path}. Unanchored payload fails closed."
                )
            if len(data) != entry.byte_count:
                raise TamperedBronzePayloadError(
                    f"Payload size mismatch for {relative_path}: expected {entry.byte_count} bytes, got {len(data)}"
                )
            computed_sha = hashlib.sha256(data).hexdigest()
            if computed_sha != entry.sha256:
                raise TamperedBronzePayloadError(
                    f"Payload SHA-256 mismatch for {relative_path}: expected {entry.sha256}, got {computed_sha}"
                )

        return data
