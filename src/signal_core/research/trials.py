"""
Append-Only Tamper-Evident Multi-Hypothesis Trial Registry.

Implements the multi-hypothesis trial accounting protocol per AGENTS.md Rule 8.2 and Phase 2A:
- Records every parameter sweep, rule variation, and indicator trial with hypothesis and rationale.
- Cryptographically chains every record via SHA-256 hash chaining (seq, prev_hash, record_hash).
- Zero update or delete APIs; out-of-order sequence, duplicate trial_id, or broken hash chain fails closed.
- Pre-allocated schema supports Phase 2B significance fields (returns digest, moments, Sharpe, drawdown).
"""

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


GENESIS_PREV_HASH = "0" * 64


class TrialRegistryError(ValueError):
    """Base exception for trial registry and multi-hypothesis errors."""
    pass


class RegistryTamperedError(TrialRegistryError):
    """Raised when the cryptographic hash chain or record hash in the trial registry is broken."""
    pass


class DuplicateTrialError(TrialRegistryError):
    """Raised when duplicate trial_id or out-of-order sequence is attempted."""
    pass


def _canonicalize_value(val: Any) -> Any:
    """Recursively canonicalizes values for deterministic JSON serialization."""
    if isinstance(val, Decimal):
        # Canonical decimal string format
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
            return Decimal(str(v))

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


class TrialRegistry:
    """
    Append-only, tamper-evident cryptographic trial ledger.
    """

    def __init__(self, file_path: Union[str, Path], auto_verify: bool = True) -> None:
        self._path = Path(file_path)
        self._records: List[TrialRecord] = []
        self._trial_ids: set[str] = set()

        if self._path.exists():
            self._load_and_verify(auto_verify=auto_verify)

    @property
    def file_path(self) -> Path:
        return self._path

    @property
    def trial_count(self) -> int:
        return len(self._records)

    def get_trials(self) -> Tuple[TrialRecord, ...]:
        return tuple(self._records)

    def _load_and_verify(self, auto_verify: bool = True) -> None:
        """Loads all records from disk and verifies sequence, uniqueness, and hash chain."""
        self._records.clear()
        self._trial_ids.clear()

        lines = self._path.read_text(encoding="utf-8").splitlines()
        for line_num, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                data = json.loads(line_str)
            except Exception as e:
                raise RegistryTamperedError(f"Line {line_num}: Malformed JSON in trial registry: {e}") from e

            record = TrialRecord.from_dict(data)

            if auto_verify:
                # 1. Verify sequence
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

            self._records.append(record)
            self._trial_ids.add(record.trial_id)

    def verify_integrity(self) -> bool:
        """
        Re-reads the file from disk and rigorously verifies the complete cryptographic hash chain.
        Raises RegistryTamperedError or DuplicateTrialError on any anomaly.
        """
        self._load_and_verify(auto_verify=True)
        return True

    def append_trial(
        self,
        trial_id: str,
        hypothesis: str,
        rationale: str,
        partition: str,
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
        allow_holdout: bool = False,
    ) -> TrialRecord:
        """
        Atomically appends a new verified trial record to the registry.
        """
        if isinstance(trial_id, bool) or not isinstance(trial_id, str) or not trial_id.strip() or trial_id != trial_id.strip():
            raise DuplicateTrialError(f"trial_id must be non-empty stripped string, got {trial_id!r}")

        if trial_id in self._trial_ids:
            raise DuplicateTrialError(f"Duplicate entry rejected: trial_id '{trial_id}' already registered.")

        if isinstance(hypothesis, bool) or not isinstance(hypothesis, str) or not hypothesis.strip():
            raise TrialRegistryError(f"hypothesis must be non-empty string, got {hypothesis!r}")

        if isinstance(rationale, bool) or not isinstance(rationale, str) or not rationale.strip():
            raise TrialRegistryError(f"rationale must be non-empty string, got {rationale!r}")

        if isinstance(partition, bool) or not isinstance(partition, str) or not partition.strip():
            raise TrialRegistryError(f"partition must be non-empty string, got {partition!r}")

        if partition.upper() == "HOLDOUT" and not allow_holdout:
            raise TrialRegistryError(
                "Holdout partition cannot be registered in trial registry without verified human authorization."
            )

        if not isinstance(canonical_params, Mapping):
            raise TrialRegistryError(f"canonical_params must be a mapping, got {type(canonical_params)}")

        for name, fp in [
            ("fold_spec_fingerprint", fold_spec_fingerprint),
            ("dataset_fingerprint", dataset_fingerprint),
            ("criteria_version", criteria_version),
            ("timestamp_utc", timestamp_utc),
        ]:
            if isinstance(fp, bool) or not isinstance(fp, str) or not fp.strip():
                raise TrialRegistryError(f"{name} must be non-empty string, got {fp!r}")

        seq = len(self._records) + 1
        prev_hash = self._records[-1].record_hash if self._records else GENESIS_PREV_HASH

        payload: Dict[str, Any] = {
            "seq": seq,
            "prev_hash": prev_hash,
            "trial_id": trial_id,
            "hypothesis": hypothesis,
            "rationale": rationale,
            "partition": partition,
            "canonical_params": _canonicalize_value(canonical_params),
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
            partition=partition,
            canonical_params=canonical_params,
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

        # Write atomically to file
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized_line = json.dumps(record.to_dict(), separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(serialized_line)
            f.flush()

        self._records.append(record)
        self._trial_ids.add(trial_id)
        return record

    def get_trial_sharpes(self) -> Tuple[Decimal, ...]:
        """Returns tuple of all non-None Sharpe ratios recorded across trials."""
        return tuple(r.sharpe_ratio for r in self._records if r.sharpe_ratio is not None)

    def compute_trial_sharpe_variance(self) -> Decimal:
        """
        Computes the sample variance of trial Sharpe ratios using exact Decimal arithmetic.
        Formula: V = sum((SR_i - mean_SR)^2) / (N - 1)
        Returns Decimal("0.00") if trial count N < 2.
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
