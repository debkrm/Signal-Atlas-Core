"""
Append-Only Tamper-Evident Multi-Hypothesis Trial Registry.

Implements the multi-hypothesis trial accounting protocol per AGENTS.md Rule 8.2 and Phase 2A:
- Records every parameter sweep, rule variation, and indicator trial with hypothesis and rationale.
- Cryptographically chains every record via SHA-256 hash chaining (seq, prev_hash, record_hash).
- External head manifest anchor prevents truncation attacks (A-4).
- On-disk tail verification prevents concurrent/desynchronized corruption (A-7).
- POSIX LF (\n) enforcement ensures byte-identical cross-platform consistency (A-12).
- Finite Decimal enforcement prevents NaN / Infinity corruption (A-13).
- ISO-8601 UTC timestamp validation and monotonicity enforcement (A-18).
- Single holdout authority: routes holdout verification exclusively through containment protocol (A-3).
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from signal_core.research.containment import (
    HoldoutSealedError,
    PartitionRole,
    PartitionSpec,
    check_partition_access,
)


GENESIS_PREV_HASH = "0" * 64


class TrialRegistryError(ValueError):
    """Base exception for trial registry and multi-hypothesis errors."""
    pass


class RegistryTamperedError(TrialRegistryError):
    """Raised when the cryptographic hash chain, record hash, or manifest in the trial registry is broken."""
    pass


class DuplicateTrialError(TrialRegistryError):
    """Raised when duplicate trial_id or out-of-order sequence is attempted."""
    pass


def _canonicalize_value(val: Any) -> Any:
    """Recursively canonicalizes values for deterministic JSON serialization."""
    if isinstance(val, Decimal):
        if not val.is_finite():
            raise TrialRegistryError(f"Decimals must be finite, got {val!r}")
        return str(val)
    elif isinstance(val, (int, str, bool)):
        return val
    elif val is None:
        return None
    elif isinstance(val, Mapping):
        return {str(k): _canonicalize_value(v) for k, v in sorted(val.items(), key=lambda item: str(item[0]))}
    elif isinstance(val, (list, tuple)):
        return [_canonicalize_value(v) for v in val]
    else:
        raise TrialRegistryError(f"Unsupported type in canonical trial record: {type(val)}")


def _compute_record_hash(payload_dict: Dict[str, Any]) -> str:
    """Computes SHA-256 hash of canonical JSON representation of record fields (excluding record_hash)."""
    canonical_payload = _canonicalize_value(payload_dict)
    json_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """
    Immutable representation of an audited quantitative trial record.
    """
    seq: int
    prev_hash: str
    record_hash: str
    trial_id: str
    hypothesis: str
    rationale: str
    partition: str
    canonical_params: Mapping[str, Any]
    fold_spec_fingerprint: str
    dataset_fingerprint: str
    criteria_version: str
    timestamp_utc: str

    # Pre-allocated Phase 2B statistical fields
    returns_digest: Optional[str] = None
    observation_count: Optional[int] = None
    mean_return: Optional[Decimal] = None
    std_return: Optional[Decimal] = None
    skewness: Optional[Decimal] = None
    kurtosis: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None

    def __post_init__(self) -> None:
        # A-13 Remediation: Non-finite Decimals are strictly rejected
        for field_name in (
            "mean_return",
            "std_return",
            "skewness",
            "kurtosis",
            "sharpe_ratio",
            "max_drawdown",
        ):
            val = getattr(self, field_name)
            if val is not None:
                if isinstance(val, bool) or not isinstance(val, Decimal) or not val.is_finite():
                    raise TrialRegistryError(
                        f"Field '{field_name}' must be a finite Decimal, got {val!r}"
                    )

    def to_dict(self) -> Dict[str, Any]:
        """Converts record to JSON-serializable dictionary."""
        return {
            "seq": self.seq,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
            "trial_id": self.trial_id,
            "hypothesis": self.hypothesis,
            "rationale": self.rationale,
            "partition": self.partition,
            "canonical_params": _canonicalize_value(self.canonical_params),
            "fold_spec_fingerprint": self.fold_spec_fingerprint,
            "dataset_fingerprint": self.dataset_fingerprint,
            "criteria_version": self.criteria_version,
            "timestamp_utc": self.timestamp_utc,
            "returns_digest": self.returns_digest,
            "observation_count": self.observation_count,
            "mean_return": str(self.mean_return) if self.mean_return is not None else None,
            "std_return": str(self.std_return) if self.std_return is not None else None,
            "skewness": str(self.skewness) if self.skewness is not None else None,
            "kurtosis": str(self.kurtosis) if self.kurtosis is not None else None,
            "sharpe_ratio": str(self.sharpe_ratio) if self.sharpe_ratio is not None else None,
            "max_drawdown": str(self.max_drawdown) if self.max_drawdown is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrialRecord":
        """Reconstructs a validated TrialRecord from a dictionary."""
        def parse_dec(k: str) -> Optional[Decimal]:
            v = data.get(k)
            if v is None:
                return None
            try:
                d = Decimal(str(v))
            except Exception as e:
                raise RegistryTamperedError(f"Field '{k}' contains invalid decimal: {e}") from e
            if not d.is_finite():
                raise RegistryTamperedError(f"Field '{k}' must be finite Decimal, got {v!r}")
            return d

        try:
            return cls(
                seq=int(data["seq"]),
                prev_hash=str(data["prev_hash"]),
                record_hash=str(data["record_hash"]),
                trial_id=str(data["trial_id"]),
                hypothesis=str(data["hypothesis"]),
                rationale=str(data["rationale"]),
                partition=str(data["partition"]),
                canonical_params=dict(data["canonical_params"]),
                fold_spec_fingerprint=str(data["fold_spec_fingerprint"]),
                dataset_fingerprint=str(data["dataset_fingerprint"]),
                criteria_version=str(data["criteria_version"]),
                timestamp_utc=str(data["timestamp_utc"]),
                returns_digest=data.get("returns_digest"),
                observation_count=int(data["observation_count"]) if data.get("observation_count") is not None else None,
                mean_return=parse_dec("mean_return"),
                std_return=parse_dec("std_return"),
                skewness=parse_dec("skewness"),
                kurtosis=parse_dec("kurtosis"),
                sharpe_ratio=parse_dec("sharpe_ratio"),
                max_drawdown=parse_dec("max_drawdown"),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise RegistryTamperedError(f"Malformed record structure in trial registry: {err}") from err


class TrialRegistry:
    """
    Append-only, tamper-evident cryptographic trial ledger with external head anchor.
    """

    def __init__(self, file_path: Union[str, Path]) -> None:
        self._path = Path(file_path)
        self._manifest_path = self._path.with_name(self._path.name + ".manifest")
        self._records: List[TrialRecord] = []
        self._trial_ids: set[str] = set()

        if self._path.exists():
            self._load_and_verify()

    @property
    def file_path(self) -> Path:
        return self._path

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    @property
    def total_trial_count(self) -> int:
        """Total trials registered in ledger (the authoritative N for DSR multiple-hypothesis penalty)."""
        return len(self._records)

    @property
    def trial_count(self) -> int:
        """Alias for total_trial_count."""
        return self.total_trial_count

    @property
    def evaluated_trial_count(self) -> int:
        """Number of trials with evaluated, non-None Sharpe ratios."""
        return sum(1 for r in self._records if r.sharpe_ratio is not None)

    def get_trials(self) -> Tuple[TrialRecord, ...]:
        return tuple(self._records)

    def _load_manifest(self) -> Optional[Dict[str, Any]]:
        """Loads and verifies the external head manifest file if it exists."""
        if not self._manifest_path.is_file():
            return None

        try:
            content = self._manifest_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return data
        except Exception as e:
            raise RegistryTamperedError(f"Malformed external head manifest at {self._manifest_path}: {e}") from e

    def _write_manifest(self, total_trials: int, head_hash: str, last_trial_id: str, timestamp_utc: str) -> None:
        """Writes the external authoritative head manifest atomically with POSIX LF."""
        payload = {
            "total_trials": total_trials,
            "head_hash": head_hash,
            "last_trial_id": last_trial_id,
            "timestamp_utc": timestamp_utc,
        }
        manifest_json = json.dumps(payload, indent=2) + "\n"
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self._manifest_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(manifest_json)
            f.flush()

    def _load_and_verify(self) -> None:
        """Loads all records from disk and verifies sequence, uniqueness, hash chain, and manifest anchor."""
        self._records.clear()
        self._trial_ids.clear()

        # Check trailing newline on existing non-empty file (A-8)
        raw_bytes = self._path.read_bytes()
        if raw_bytes and not raw_bytes.endswith(b"\n"):
            raise RegistryTamperedError(
                f"Registry file {self._path} is corrupted: missing trailing newline on prior record."
            )

        lines = raw_bytes.decode("utf-8").splitlines()
        last_ts: Optional[datetime.datetime] = None

        for line_num, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                data = json.loads(line_str)
            except Exception as e:
                raise RegistryTamperedError(f"Line {line_num}: Malformed JSON in trial registry: {e}") from e

            record = TrialRecord.from_dict(data)

            # 1. Verify sequence (A-4)
            expected_seq = len(self._records) + 1
            if record.seq != expected_seq:
                raise DuplicateTrialError(
                    f"Line {line_num}: Out-of-order sequence {record.seq}; expected {expected_seq}."
                )

            # 2. Verify uniqueness of trial_id
            if record.trial_id in self._trial_ids:
                raise DuplicateTrialError(
                    f"Line {line_num}: Duplicate trial_id '{record.trial_id}' in trial registry."
                )

            # 3. Verify prev_hash
            if len(self._records) == 0:
                if record.prev_hash != GENESIS_PREV_HASH:
                    raise RegistryTamperedError(
                        f"Line {line_num}: Genesis block prev_hash must be {GENESIS_PREV_HASH}, got {record.prev_hash}"
                    )
            else:
                expected_prev = self._records[-1].record_hash
                if record.prev_hash != expected_prev:
                    raise RegistryTamperedError(
                        f"Line {line_num}: Broken hash chain for trial '{record.trial_id}'. "
                        f"prev_hash {record.prev_hash} != expected {expected_prev}."
                    )

            # 4. Verify record_hash
            payload = record.to_dict()
            del payload["record_hash"]
            computed_hash = _compute_record_hash(payload)
            if record.record_hash != computed_hash:
                raise RegistryTamperedError(
                    f"Line {line_num}: Tampered record hash for trial '{record.trial_id}'. "
                    f"Stored {record.record_hash} != computed {computed_hash}."
                )

            # 5. Verify timestamp UTC parse and monotonicity (A-18)
            try:
                rec_ts = datetime.datetime.fromisoformat(record.timestamp_utc.replace("Z", "+00:00"))
            except Exception as e:
                raise RegistryTamperedError(f"Line {line_num}: Invalid ISO-8601 timestamp '{record.timestamp_utc}': {e}")
            if last_ts is not None and rec_ts < last_ts:
                raise RegistryTamperedError(
                    f"Line {line_num}: Non-monotonic timestamp '{record.timestamp_utc}' strictly precedes prior '{last_ts.isoformat()}'."
                )
            last_ts = rec_ts

            self._records.append(record)
            self._trial_ids.add(record.trial_id)

        # 6. Verify external head manifest anchor (A-4 Truncation Detection)
        manifest = self._load_manifest()
        if manifest is not None:
            expected_total = manifest.get("total_trials")
            expected_head = manifest.get("head_hash")
            if len(self._records) != expected_total:
                raise RegistryTamperedError(
                    f"Registry truncation detected: registry has {len(self._records)} records, "
                    f"but authoritative manifest specifies {expected_total} trials."
                )
            if self._records and self._records[-1].record_hash != expected_head:
                raise RegistryTamperedError(
                    f"Registry head mismatch: last record hash '{self._records[-1].record_hash}' "
                    f"does not match manifest head '{expected_head}'."
                )

    def verify_integrity(self) -> bool:
        """
        Re-reads the file from disk and rigorously verifies the complete cryptographic hash chain
        and authoritative external head manifest.
        Raises RegistryTamperedError or DuplicateTrialError on any anomaly.
        """
        self._load_and_verify()
        return True

    def append_trial(
        self,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        partition: Union[str, PartitionRole],
        canonical_params: Mapping[str, Any],
        fold_spec_fingerprint: str,
        dataset_fingerprint: str,
        criteria_version: str,
        timestamp_utc: str,
        returns_digest: Optional[str] = None,
        observation_count: Optional[int] = None,
        mean_return: Optional[Decimal] = None,
        std_return: Optional[Decimal] = None,
        skewness: Optional[Decimal] = None,
        kurtosis: Optional[Decimal] = None,
        sharpe_ratio: Optional[Decimal] = None,
        max_drawdown: Optional[Decimal] = None,
        partition_spec: Optional[PartitionSpec] = None,
        unlock_file_path: Optional[Union[str, Path]] = None,
    ) -> TrialRecord:
        """
        Atomically appends a new verified trial record to the registry.

        A-2 & A-3 Remediation:
        - Partition is normalized and validated against PartitionRole.
        - HOLDOUT access routes strictly through check_partition_access with partition_spec and unlock sentinel.
        - External manifest is updated atomically with POSIX LF line endings.
        """
        # 1. Validate trial_id
        if isinstance(trial_id, bool) or not isinstance(trial_id, str) or not trial_id.strip() or trial_id != trial_id.strip():
            raise DuplicateTrialError(f"trial_id must be non-empty stripped string, got {trial_id!r}")

        if trial_id in self._trial_ids:
            raise DuplicateTrialError(f"Duplicate entry rejected: trial_id '{trial_id}' already registered.")

        # 2. Validate strings
        if isinstance(hypothesis, bool) or not isinstance(hypothesis, str) or not hypothesis.strip():
            raise TrialRegistryError(f"hypothesis must be non-empty string, got {hypothesis!r}")

        if isinstance(rationale, bool) or not isinstance(rationale, str) or not rationale.strip():
            raise TrialRegistryError(f"rationale must be non-empty string, got {rationale!r}")

        # 3. Validate and normalize partition role (A-2)
        if isinstance(partition, str):
            norm_part_str = partition.strip().upper()
            try:
                typed_role = PartitionRole(norm_part_str)
            except ValueError:
                raise TrialRegistryError(
                    f"Invalid partition {partition!r}; must be one of {[r.value for r in PartitionRole]}"
                )
        elif isinstance(partition, PartitionRole):
            typed_role = partition
            norm_part_str = typed_role.value
        else:
            raise TrialRegistryError(f"partition must be PartitionRole or str, got {type(partition)}")

        # 4. Route holdout partition through single containment authority (A-3)
        if typed_role == PartitionRole.HOLDOUT:
            if partition_spec is None:
                raise HoldoutSealedError(
                    "Registering a HOLDOUT trial requires providing an authoritative PartitionSpec."
                )
            check_partition_access(partition_spec, PartitionRole.HOLDOUT, unlock_file_path)

        # 5. Validate canonical parameters (A-15 parity)
        if not isinstance(canonical_params, Mapping):
            raise TrialRegistryError(f"canonical_params must be a mapping, got {type(canonical_params)}")
        canonical_params_clean = _canonicalize_value(canonical_params)

        # 6. Validate fingerprints and timestamps
        for name, fp in [
            ("fold_spec_fingerprint", fold_spec_fingerprint),
            ("dataset_fingerprint", dataset_fingerprint),
            ("criteria_version", criteria_version),
            ("timestamp_utc", timestamp_utc),
        ]:
            if isinstance(fp, bool) or not isinstance(fp, str) or not fp.strip():
                raise TrialRegistryError(f"{name} must be non-empty string, got {fp!r}")

        # A-18: Validate ISO-8601 UTC timestamp and monotonicity
        try:
            curr_ts = datetime.datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
        except Exception as e:
            raise TrialRegistryError(f"timestamp_utc '{timestamp_utc}' is not a valid ISO-8601 string: {e}")

        if self._records:
            try:
                prev_ts = datetime.datetime.fromisoformat(self._records[-1].timestamp_utc.replace("Z", "+00:00"))
            except Exception as e:
                raise TrialRegistryError(f"Previous record timestamp is invalid ISO-8601: {e}")
            if curr_ts < prev_ts:
                raise TrialRegistryError(
                    f"Non-monotonic timestamp '{timestamp_utc}' precedes previous record timestamp '{self._records[-1].timestamp_utc}'."
                )

        # 7. A-5 / A-7: Re-verify on-disk tail before appending to prevent concurrent desync
        if self._path.exists():
            disk_bytes = self._path.read_bytes()
            if disk_bytes:
                if not disk_bytes.endswith(b"\n"):
                    raise RegistryTamperedError(
                        f"Registry file {self._path} is corrupted: missing trailing newline on prior record."
                    )
                disk_lines = disk_bytes.decode("utf-8").splitlines()
                if len(disk_lines) != len(self._records):
                    raise RegistryTamperedError(
                        f"Concurrent modification detected: on-disk record count ({len(disk_lines)}) "
                        f"disagrees with registry in-memory count ({len(self._records)})."
                    )
                if self._records:
                    last_disk_rec = json.loads(disk_lines[-1])
                    if last_disk_rec.get("record_hash") != self._records[-1].record_hash:
                        raise RegistryTamperedError(
                            "Concurrent modification detected: on-disk head hash does not match in-memory head."
                        )

        seq = len(self._records) + 1
        prev_hash = self._records[-1].record_hash if self._records else GENESIS_PREV_HASH

        payload: Dict[str, Any] = {
            "seq": seq,
            "prev_hash": prev_hash,
            "trial_id": trial_id,
            "hypothesis": hypothesis,
            "rationale": rationale,
            "partition": norm_part_str,
            "canonical_params": canonical_params_clean,
            "fold_spec_fingerprint": fold_spec_fingerprint,
            "dataset_fingerprint": dataset_fingerprint,
            "criteria_version": criteria_version,
            "timestamp_utc": timestamp_utc,
            "returns_digest": returns_digest,
            "observation_count": observation_count,
            "mean_return": str(mean_return) if mean_return is not None else None,
            "std_return": str(std_return) if std_return is not None else None,
            "skewness": str(skewness) if skewness is not None else None,
            "kurtosis": str(kurtosis) if kurtosis is not None else None,
            "sharpe_ratio": str(sharpe_ratio) if sharpe_ratio is not None else None,
            "max_drawdown": str(max_drawdown) if max_drawdown is not None else None,
        }

        record_hash = _compute_record_hash(payload)

        record = TrialRecord(
            seq=seq,
            prev_hash=prev_hash,
            record_hash=record_hash,
            trial_id=trial_id,
            hypothesis=hypothesis,
            rationale=rationale,
            partition=norm_part_str,
            canonical_params=canonical_params_clean,
            fold_spec_fingerprint=fold_spec_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            criteria_version=criteria_version,
            timestamp_utc=timestamp_utc,
            returns_digest=returns_digest,
            observation_count=observation_count,
            mean_return=mean_return,
            std_return=std_return,
            skewness=skewness,
            kurtosis=kurtosis,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
        )

        # 8. Write atomically with strict POSIX LF (newline="\n") (A-12)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized_line = json.dumps(record.to_dict(), separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(serialized_line)
            f.flush()

        # 9. Update external head manifest anchor (A-4)
        self._write_manifest(
            total_trials=seq,
            head_hash=record_hash,
            last_trial_id=trial_id,
            timestamp_utc=timestamp_utc,
        )

        self._records.append(record)
        self._trial_ids.add(trial_id)
        return record

    def get_trial_sharpes(self) -> Tuple[Decimal, ...]:
        """Returns tuple of all evaluated (non-None) Sharpe ratios recorded across trials."""
        return tuple(r.sharpe_ratio for r in self._records if r.sharpe_ratio is not None)

    def compute_trial_sharpe_variance(self) -> Decimal:
        """
        Computes the sample variance of evaluated trial Sharpe ratios using exact Decimal arithmetic.
        Formula: V = sum((SR_i - mean_SR)^2) / (N_eval - 1)
        Returns Decimal("0.00") if evaluated trial count N_eval < 2.
        """
        sharpes = self.get_trial_sharpes()
        n = len(sharpes)
        if n < 2:
            return Decimal("0.00")

        total = sum(sharpes, Decimal("0.00"))
        mean = total / Decimal(n)

        sq_diff_sum = sum(((s - mean) ** 2 for s in sharpes), Decimal("0.00"))
        variance = sq_diff_sum / Decimal(n - 1)
        return variance
