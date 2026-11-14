"""
Authoritative Bronze Circular Payload Loader and Registry for Indian Financial Markets.
Implements exchange circular provenance and parsing per AGENTS.md §6.3, §10.7, and Audit §§45-46 Findings H-57, H-60.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CIRCULARS_DIR = REPO_ROOT / "data" / "raw" / "circulars"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"


class CircularError(ValueError):
    """Base exception for circular loading and validation errors."""
    pass


class ProvenanceStatus(str, Enum):
    """Official dataset provenance classification per AGENTS.md Rule 6.5."""
    CONTENT_IDENTIFIED_ONLY = "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class CircularHoliday:
    """Official exchange holiday substantiated by an authentic Bronze circular payload."""
    date: datetime.date
    circular_id: str
    description: str
    is_muhurat: bool = False
    session_type: str = "HOLIDAY"
    circular_ids: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CircularSpecialSession:
    """Special live trading session substantiated by an authentic Bronze circular payload."""
    date: datetime.date
    circular_id: str
    session_type: str
    is_settlement_holiday: bool
    description: str
    local_archive_status: Optional[str] = None
    circular_ids: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CircularTradingDayClarification:
    """Trading day clarification substantiated by an authentic Bronze circular payload."""
    date: datetime.date
    circular_id: str
    description: str
    circular_ids: Tuple[str, ...] = ()


class BronzeCircularRegistry:
    """
    Immutable in-memory registry of parsed Bronze circular documents.
    Provides fail-closed verification of exchange holiday and special session claims (Findings H-57, H-60).
    """

    def __init__(
        self,
        holidays: Dict[datetime.date, CircularHoliday],
        special_sessions: Dict[datetime.date, CircularSpecialSession],
        verified_trading_days: Dict[datetime.date, CircularTradingDayClarification],
        circular_digests: Dict[str, str],
    ) -> None:
        self._holidays = dict(holidays)
        self._special_sessions = dict(special_sessions)
        self._verified_trading_days = dict(verified_trading_days)
        self._circular_digests = dict(circular_digests)

    @property
    def circular_digests(self) -> Dict[str, str]:
        return dict(self._circular_digests)

    @property
    def holidays(self) -> Dict[datetime.date, CircularHoliday]:
        return dict(self._holidays)

    @property
    def special_sessions(self) -> Dict[datetime.date, CircularSpecialSession]:
        return dict(self._special_sessions)

    @property
    def verified_trading_days(self) -> Dict[datetime.date, CircularTradingDayClarification]:
        return dict(self._verified_trading_days)

    def verify_holiday_claim(self, query_date: datetime.date, circular_id: str) -> bool:
        """
        Returns True if and only if query_date is explicitly substantiated as a holiday
        in the authentic Bronze circular payload matching circular_id (§6.3, Finding H-57).
        """
        rec = self._holidays.get(query_date)
        if rec is None:
            return False
        return circular_id == rec.circular_id or circular_id in rec.circular_ids

    def verify_special_session_claim(self, query_date: datetime.date, circular_id: str) -> bool:
        """
        Returns True if and only if query_date is explicitly substantiated as a special session
        in the authentic Bronze circular payload matching circular_id (§6.3, Finding H-57).
        """
        rec = self._special_sessions.get(query_date)
        if rec is None:
            return False
        return circular_id == rec.circular_id or circular_id in rec.circular_ids

    def verify_trading_day_claim(self, query_date: datetime.date, circular_id: str) -> bool:
        """
        Returns True if and only if query_date is explicitly substantiated as a trading day
        in the authentic Bronze circular payload matching circular_id (§6.3, Finding H-57).
        """
        rec = self._verified_trading_days.get(query_date)
        if rec is None:
            return False
        return circular_id == rec.circular_id or circular_id in rec.circular_ids


def load_all_bronze_circulars(
    circulars_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> BronzeCircularRegistry:
    """
    Discovers, digest-verifies against manifest.jsonl, and parses all Bronze circular payloads.
    Fails closed if any circular is unregistered, missing, unparseable, or tampered with (§10.7, Finding H-57).
    """
    c_dir = circulars_dir or DEFAULT_CIRCULARS_DIR
    m_path = manifest_path or DEFAULT_MANIFEST_PATH

    if not c_dir.is_dir():
        raise FileNotFoundError(f"Bronze circulars directory not found at: {c_dir}")

    manifest_entries: Dict[str, dict] = {}
    if m_path.is_file():
        with open(m_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("is_current") is True:
                    manifest_entries[entry["artifact"]] = entry

    circular_files = sorted(c_dir.glob("*.json"))
    if not circular_files:
        raise CircularError(f"No Bronze circular JSON payloads found in: {c_dir}")

    holidays: Dict[datetime.date, CircularHoliday] = {}
    special_sessions: Dict[datetime.date, CircularSpecialSession] = {}
    verified_trading_days: Dict[datetime.date, CircularTradingDayClarification] = {}
    circular_digests: Dict[str, str] = {}

    for c_path in circular_files:
        raw_bytes = c_path.read_bytes().replace(b"\r\n", b"\n")
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        byte_count = len(raw_bytes)

        # Check manifest registration - MANDATORY per Finding H-57 (refuse unregistered files fail-closed)
        rel_key = f"circulars/{c_path.name}"
        manifest_rec = manifest_entries.get(rel_key) or manifest_entries.get(c_path.name)
        if not manifest_rec:
            raise CircularError(
                f"Unregistered Bronze circular payload '{c_path.name}' found on disk without active manifest entry (Finding H-57)"
            )

        if manifest_rec.get("sha256") != sha256 or manifest_rec.get("byte_count") != byte_count:
            raise CircularError(
                f"Bronze circular {c_path.name} digest/size mismatch vs manifest: "
                f"computed sha={sha256}, byte_count={byte_count}; "
                f"manifest sha={manifest_rec.get('sha256')}, byte_count={manifest_rec.get('byte_count')}"
            )

        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise CircularError(f"Malformed Bronze circular JSON in {c_path.name}: {e}")

        c_id = payload.get("circular_id")
        if not c_id:
            raise CircularError(f"Bronze circular {c_path.name} missing mandatory circular_id")

        source_url = payload.get("source_url")
        if not source_url or not isinstance(source_url, str):
            raise CircularError(f"Bronze circular {c_path.name} missing mandatory source_url (Finding H-57)")
        if not (source_url.startswith("https://archives.nseindia.com/") or source_url.startswith("https://www.nseindia.com/")):
            raise CircularError(
                f"Bronze circular {c_path.name} has non-authentic source_url {source_url!r}. "
                f"Must start with https://archives.nseindia.com/ or https://www.nseindia.com/ (Finding H-57)"
            )

        if payload.get("http_status") != 200:
            raise CircularError(
                f"Bronze circular {c_path.name} must have http_status 200, got {payload.get('http_status')!r} (Finding H-57)"
            )

        retrieved_at_str = payload.get("retrieved_at")
        if not retrieved_at_str or not isinstance(retrieved_at_str, str):
            raise CircularError(f"Bronze circular {c_path.name} missing mandatory retrieved_at timestamp (Finding H-57)")
        try:
            retrieved_dt = datetime.datetime.fromisoformat(retrieved_at_str)
        except Exception as e:
            raise CircularError(
                f"Bronze circular {c_path.name} has invalid ISO 8601 retrieved_at timestamp {retrieved_at_str!r}: {e}"
            )
        if retrieved_dt.tzinfo is None:
            raise CircularError(
                f"Bronze circular {c_path.name} retrieved_at must include explicit timezone offset (Finding H-57): {retrieved_at_str!r}"
            )

        prov_status = payload.get("provenance_status")
        if not prov_status:
            raise CircularError(f"Bronze circular {c_path.name} missing mandatory provenance_status (Finding H-57)")
        valid_statuses = {p.value for p in ProvenanceStatus}
        if prov_status not in valid_statuses:
            raise CircularError(
                f"Bronze circular {c_path.name} has unrecognized provenance_status: {prov_status!r}. "
                f"Allowed: {sorted(valid_statuses)} (Finding H-57)"
            )
        if prov_status == ProvenanceStatus.VERIFIED.value:
            raise CircularError(
                f"Bronze circular {c_path.name} cannot claim VERIFIED without verified source certificates "
                f"per AGENTS.md Rule 6.5 (Finding H-57)"
            )

        # Collect all recognized IDs / aliases for this circular
        id_set = {c_id}
        if payload.get("download_ref_no"):
            id_set.add(payload["download_ref_no"])
        if payload.get("circular_ref_no"):
            id_set.add(payload["circular_ref_no"])
            id_set.add(f"NSE/CMTR/{payload['circular_ref_no']}")
            id_set.add(f"NSE/MSD/{payload['circular_ref_no']}")
        id_tuple = tuple(sorted(id_set))

        circular_digests[c_id] = sha256

        # Parse trading holidays
        for h in payload.get("trading_holidays", []):
            dt = datetime.date.fromisoformat(h["date"])
            desc = h.get("description", "Trading Holiday")
            session_type = h.get("session_type", "MUHURAT" if "muhurat" in desc.lower() else "HOLIDAY")
            is_muhurat = (session_type == "MUHURAT") or ("muhurat" in desc.lower())
            holidays[dt] = CircularHoliday(
                date=dt,
                circular_id=c_id,
                description=desc,
                is_muhurat=is_muhurat,
                session_type=session_type,
                circular_ids=id_tuple,
            )

        # Parse special sessions
        for s in payload.get("special_sessions", []):
            dt = datetime.date.fromisoformat(s["date"])
            st = s.get("session_type", "SPECIAL")
            sh = bool(s.get("is_settlement_holiday", False))
            desc = s.get("description", "Special Session")
            local_archive_status = s.get("local_archive_status")
            special_sessions[dt] = CircularSpecialSession(
                date=dt,
                circular_id=c_id,
                session_type=st,
                is_settlement_holiday=sh,
                description=desc,
                local_archive_status=local_archive_status,
                circular_ids=id_tuple,
            )

        # Parse verified trading days
        for t in payload.get("verified_regular_trading_sessions", []):
            dt = datetime.date.fromisoformat(t["date"])
            desc = t.get("description", "Regular Trading Session")
            verified_trading_days[dt] = CircularTradingDayClarification(
                date=dt,
                circular_id=c_id,
                description=desc,
                circular_ids=id_tuple,
            )

    return BronzeCircularRegistry(
        holidays=holidays,
        special_sessions=special_sessions,
        verified_trading_days=verified_trading_days,
        circular_digests=circular_digests,
    )
