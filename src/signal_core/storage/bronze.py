"""
Bronze Layer: Byte-Exact Content-Addressed Raw Archive Storage and Provenance Manifest.

Implements raw storage integrity per AGENTS.md Rule 10.1 and Rule 10.7:
- Bronze payloads are byte-exact as retrieved and are never mutated or edited in place.
- Payloads are stored content-addressed by SHA-256 digest in blobs/{sha256}.bin (E-6).
- Every retrieval records source URL, retrieval timestamp, byte count, SHA-256, and optional
  restatement reference in an append-only manifest.
- Re-storing an existing path with differing bytes without an explicit restatement_ref raises
  BronzeStorageError fail-closed (E-6).
- Historical retrievals are never orphaned or overwritten; all historical states remain verifiable.
- Tamper detection fails closed: any modification, bit flip, or truncation raises TamperedBronzePayloadError (Gate G2B.5-1).
"""

from contextlib import contextmanager
from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


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
    Frozen ingest contract per AGENTS.md Rule 10.7 and Wave 0.
    """
    relative_path: str
    source_url: str
    retrieved_at: str
    byte_count: int
    sha256: str
    restatement_ref: Optional[str] = None
    source_archive_format: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.relative_path, bool) or not isinstance(self.relative_path, str) or not self.relative_path.strip():
            raise BronzeStorageError(f"relative_path must be a non-empty string, got {self.relative_path!r}")
        if "\\" in self.relative_path:
            raise BronzeStorageError(f"relative_path cannot contain backslashes: {self.relative_path!r}")
        if ".." in self.relative_path.split("/"):
            raise BronzeStorageError(f"relative_path cannot contain directory traversal '..': {self.relative_path!r}")

        if isinstance(self.source_url, bool) or not isinstance(self.source_url, str) or not self.source_url.strip():
            raise BronzeStorageError(f"source_url must be a non-empty string, got {self.source_url!r}")

        if isinstance(self.retrieved_at, bool) or not isinstance(self.retrieved_at, str) or not self.retrieved_at.strip():
            raise BronzeStorageError(f"retrieved_at must be a non-empty string, got {self.retrieved_at!r}")

        if isinstance(self.byte_count, bool) or not isinstance(self.byte_count, int) or self.byte_count < 0:
            raise BronzeStorageError(f"byte_count must be a non-negative integer, got {self.byte_count!r}")

        if (
            isinstance(self.sha256, bool)
            or not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or not all(c in "0123456789abcdefABCDEF" for c in self.sha256)
        ):
            raise BronzeStorageError(f"sha256 must be a valid 64-character hex string, got {self.sha256!r}")
        object.__setattr__(self, "sha256", self.sha256.lower())

        if self.restatement_ref is not None:
            if isinstance(self.restatement_ref, bool) or not isinstance(self.restatement_ref, str) or not self.restatement_ref.strip():
                raise BronzeStorageError(f"restatement_ref must be a non-empty string if provided, got {self.restatement_ref!r}")

        if self.source_archive_format is not None:
            if isinstance(self.source_archive_format, bool) or not isinstance(self.source_archive_format, str) or not self.source_archive_format.strip():
                raise BronzeStorageError(f"source_archive_format must be non-empty string if provided, got {self.source_archive_format!r}")

    def to_json_dict(self) -> Dict[str, Union[str, int, None]]:
        d: Dict[str, Union[str, int, None]] = {
            "relative_path": self.relative_path,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }
        if self.restatement_ref is not None:
            d["restatement_ref"] = self.restatement_ref
        if self.source_archive_format is not None:
            d["source_archive_format"] = self.source_archive_format
        return d

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Any]) -> "BronzeManifestEntry":
        return cls(
            relative_path=str(data["relative_path"]),
            source_url=str(data["source_url"]),
            retrieved_at=str(data["retrieved_at"]),
            byte_count=int(data["byte_count"]),
            sha256=str(data["sha256"]),
            restatement_ref=str(data["restatement_ref"]) if data.get("restatement_ref") else None,
            source_archive_format=str(data["source_archive_format"]) if data.get("source_archive_format") else None,
        )


class BronzeStorage:
    """
    Manages content-addressed raw archives and their append-only audit manifest.
    """
    def __init__(self, root_dir: Union[str, Path]) -> None:
        self._root_dir = Path(root_dir).resolve()
        self._blobs_dir = self._root_dir / "blobs"
        self._manifest_path = self._root_dir / "manifest.jsonl"
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._blobs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def blobs_dir(self) -> Path:
        return self._blobs_dir

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def get_blob_path(self, sha256_digest: str) -> Path:
        """Returns storage path for a content-addressed blob."""
        return self._blobs_dir / f"{sha256_digest}.bin"

    @contextmanager
    def _lock_manifest(self, timeout_seconds: float = 10.0, stale_timeout_seconds: float = 5.0):
        """
        Cross-platform inter-process file lock for atomic manifest.jsonl appends (Finding E-15, H-3).
        Guarantees serial execution of manifest validation and writes across concurrent processes.
        Features stale-lock auto-clearing and explicit actionable remediation messaging on timeout.
        """
        lock_path = self._manifest_path.with_suffix(".lock")
        start_time = time.monotonic()
        fd = None
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                try:
                    payload = json.dumps({"pid": os.getpid(), "timestamp": time.time()}).encode("utf-8")
                    os.write(fd, payload)
                except Exception:
                    pass
                break
            except OSError:
                # Audit §27 H-3: Check for stale lock from dead or killed process
                try:
                    mtime = lock_path.stat().st_mtime
                    if time.time() - mtime > stale_timeout_seconds:
                        try:
                            lock_path.unlink()
                            continue
                        except OSError:
                            pass
                except OSError:
                    pass

                if time.monotonic() - start_time > timeout_seconds:
                    raise BronzeStorageError(
                        f"Timeout ({timeout_seconds}s) acquiring inter-process manifest lock: {lock_path}. "
                        f"If no concurrent ingestion process is running, the lock is orphaned. "
                        f"Remediation: remove the lock file '{lock_path}' to resume Bronze storage operations."
                    )
                time.sleep(0.01)
        try:
            yield
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                if lock_path.exists():
                    lock_path.unlink()
            except OSError:
                pass

    def store_payload(
        self,
        relative_path: str,
        data: bytes,
        source_url: str,
        retrieved_at: Optional[datetime.datetime] = None,
        restatement_ref: Optional[str] = None,
        source_archive_format: Optional[str] = None,
        lock_timeout_seconds: float = 10.0,
        stale_timeout_seconds: float = 5.0,
    ) -> BronzeManifestEntry:
        """
        Stores raw payload bytes in content-addressed storage and appends provenance record to manifest.
        Fails closed if attempting to overwrite an existing path with different bytes without an explicit restatement_ref (E-6).
        Acquires inter-process manifest lock with stale-lock detection (E-15, H-3).
        """
        if not isinstance(data, (bytes, bytearray)):
            raise BronzeStorageError(f"Payload data must be bytes, got {type(data).__name__}")
        if not relative_path or not relative_path.strip():
            raise BronzeStorageError("relative_path cannot be empty.")
        if not source_url or not source_url.strip():
            raise BronzeStorageError("source_url cannot be empty.")

        normalized_path = relative_path.replace("\\", "/")
        byte_count = len(data)
        sha256_digest = hashlib.sha256(data).hexdigest()

        with self._lock_manifest(timeout_seconds=lock_timeout_seconds, stale_timeout_seconds=stale_timeout_seconds):
            # Check existing manifest records for this relative_path
            existing_entries = [e for e in self.load_manifest() if e.relative_path == normalized_path]
            if existing_entries:
                latest = existing_entries[-1]
                if latest.sha256 != sha256_digest:
                    # Content has changed for an existing path!
                    if not restatement_ref:
                        raise BronzeStorageError(
                            f"Cannot overwrite archived path '{normalized_path}' with different payload "
                            f"(existing sha={latest.sha256[:12]}, new sha={sha256_digest[:12]}) "
                            "without an explicit restatement_ref per AGENTS.md Rule 10.1."
                        )

            # Store content-addressed blob atomically
            blob_path = self.get_blob_path(sha256_digest)
            if not blob_path.exists():
                temp_file = blob_path.with_suffix(f".tmp_{os.getpid()}_{datetime.datetime.now().timestamp()}")
                try:
                    with open(temp_file, "wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    temp_file.replace(blob_path)
                except Exception:
                    if temp_file.exists():
                        temp_file.unlink()
                    raise

            ts = retrieved_at or datetime.datetime.now(datetime.timezone.utc)
            entry = BronzeManifestEntry(
                relative_path=normalized_path,
                source_url=source_url,
                retrieved_at=ts.isoformat(),
                byte_count=byte_count,
                sha256=sha256_digest,
                restatement_ref=restatement_ref,
                source_archive_format=source_archive_format,
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

    def get_manifest_entries(self, relative_path: str) -> List[BronzeManifestEntry]:
        """Returns all historical manifest entries for relative_path, chronological order."""
        normalized = relative_path.replace("\\", "/")
        return [e for e in self.load_manifest() if e.relative_path == normalized]

    def get_manifest_entry(
        self, relative_path: str, sha256_digest: Optional[str] = None
    ) -> Optional[BronzeManifestEntry]:
        """Finds manifest entry for relative_path (optionally matching specific sha256)."""
        entries = self.get_manifest_entries(relative_path)
        if not entries:
            return None
        if sha256_digest is not None:
            for e in entries:
                if e.sha256 == sha256_digest:
                    return e
            return None
        return entries[-1]

    def read_payload(
        self,
        relative_path: str,
        sha256_digest: Optional[str] = None,
        verify: bool = True,
    ) -> bytes:
        """
        Reads payload bytes from content-addressed blob.
        If verify is True, asserts exact byte count and SHA-256 against manifest before returning.
        Fails closed with TamperedBronzePayloadError on corruption (Gate G2B.5-1).
        """
        entry = self.get_manifest_entry(relative_path, sha256_digest=sha256_digest)
        if entry is None:
            raise MissingBronzeManifestError(
                f"No manifest entry found for payload {relative_path}. Unanchored payload fails closed."
            )

        blob_path = self.get_blob_path(entry.sha256)
        if not blob_path.is_file():
            raise FileNotFoundError(f"Content blob not found for digest {entry.sha256} at {blob_path}")

        with open(blob_path, "rb") as f:
            data = f.read()

        if verify:
            if len(data) != entry.byte_count:
                raise TamperedBronzePayloadError(
                    f"Payload size mismatch for {relative_path} (blob {entry.sha256}): "
                    f"expected {entry.byte_count} bytes, got {len(data)}"
                )
            computed_sha = hashlib.sha256(data).hexdigest()
            if computed_sha != entry.sha256:
                raise TamperedBronzePayloadError(
                    f"Payload SHA-256 mismatch for {relative_path}: expected {entry.sha256}, got {computed_sha}"
                )

        return data
