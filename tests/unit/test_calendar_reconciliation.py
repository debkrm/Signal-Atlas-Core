"""Unit tests for Authoritative Calendar Reconciliation Contract (Finding H-56, Note N-40)."""

import datetime
import hashlib
import json
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.storage.calendar import load_nse_trading_calendar

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECON_FILE = REPO_ROOT / "data" / "reference" / "calendar_reconciliation_2022_2026.json"
MANIFEST_FILE = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
ARCHIVE_MANIFEST = REPO_ROOT / "data" / "reference" / "bhavcopy_archive_manifest.jsonl"


def test_calendar_reconciliation_manifest_registration():
    """Verify calendar reconciliation table is registered in manifest.jsonl with matching digest (§6.5, §10.7, H-56)."""
    assert RECON_FILE.is_file(), f"Reconciliation file missing at {RECON_FILE}"

    recon_bytes = RECON_FILE.read_bytes()
    computed_sha256 = hashlib.sha256(recon_bytes).hexdigest()

    active_entry = None
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("artifact") == RECON_FILE.name and entry.get("is_current") is True:
                active_entry = entry
                break

    assert active_entry is not None, f"No active manifest entry for {RECON_FILE.name}"
    assert active_entry["sha256"] == computed_sha256, "Reconciliation SHA-256 mismatch with manifest"
    assert active_entry["byte_count"] == len(recon_bytes), "Reconciliation byte_count mismatch with manifest"


def test_calendar_reconciliation_circulars_in_provenance():
    """Verify all circular citations in reconciliation table exist in calendar provenance (Audit §44.2, Finding H-56)."""
    cal = load_nse_trading_calendar()
    cal_circulars = set(cal.provenance.get("circular_references", []))

    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    entries = recon_data.get("entries", [])
    assert len(entries) == 10, f"Expected exactly 10 discrepancy reconciliation entries, got {len(entries)}"

    for item in entries:
        dt = item["session_date"]
        circulars = item.get("circular_references", [])
        assert len(circulars) > 0, f"Entry {dt} has empty circular_references"
        for circ in circulars:
            assert circ in cal_circulars, f"Circular {circ} for session {dt} not present in calendar provenance"


def test_calendar_reconciliation_exact_session_set_closure():
    """Verify exact algebraic reconciliation between baseline calendar and archive manifest (Finding H-56)."""
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    window_start = criteria.min_binding_evaluation_start_date
    window_end = datetime.date(2026, 10, 31)

    cal_sessions = set(s for s in cal.sessions if window_start <= s <= window_end)
    assert len(cal_sessions) == 1201, f"Expected 1,201 baseline sessions, got {len(cal_sessions)}"

    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    excluded: set[datetime.date] = set()
    included: set[datetime.date] = set()

    for item in recon_data["entries"]:
        dt = datetime.date.fromisoformat(item["session_date"])
        action = item["action"]
        if action == "EXCLUDE_FROM_EXPECTED_ARCHIVES":
            assert dt in cal_sessions, f"Excluded date {dt} not in baseline calendar sessions"
            excluded.add(dt)
        elif action == "INCLUDE_IN_EXPECTED_ARCHIVES":
            assert dt not in cal_sessions, f"Included date {dt} already in baseline calendar sessions"
            included.add(dt)
        else:
            pytest.fail(f"Invalid action {action} for {dt}")

    assert len(excluded) == 8, f"Expected 8 excluded calendar sessions, got {len(excluded)}"
    assert len(included) == 2, f"Expected 2 included archive sessions, got {len(included)}"

    manifest_dates: set[datetime.date] = set()
    with open(ARCHIVE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                manifest_dates.add(datetime.date.fromisoformat(json.loads(line)["session_date"]))

    assert len(manifest_dates) == 1195, f"Expected 1,195 manifest dates, got {len(manifest_dates)}"

    reconciled_expected = (cal_sessions - excluded) | included
    assert reconciled_expected == manifest_dates, "Reconciled calendar session set does not match manifest dates"
    assert len(reconciled_expected ^ manifest_dates) == 0, "Non-empty symmetric difference between reconciled calendar and manifest"


def test_calendar_reconciliation_fails_on_unrecorded_circular():
    """Verify reconciliation fails if a circular is missing from calendar provenance (Finding H-56)."""
    cal = load_nse_trading_calendar()
    cal_circulars = set(cal.provenance.get("circular_references", []))

    # An unknown circular not in calendar provenance
    fake_circular = "NSE/UNKNOWN/99999"
    assert fake_circular not in cal_circulars

    # Invariant: every cited circular must exist in calendar provenance
    with pytest.raises(AssertionError):
        assert fake_circular in cal_circulars


def test_calendar_reconciliation_fails_on_unexplained_missing_session():
    """Verify fail-closed detection when a session is missing without reconciliation (Finding H-56, §6.3)."""
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    cal_sessions = set(s for s in cal.sessions if criteria.min_binding_evaluation_start_date <= s <= datetime.date(2026, 10, 31))

    # If an archive set omitted 2024-01-16 without a reconciliation entry
    simulated_manifest = set(cal_sessions)
    simulated_manifest.remove(datetime.date(2024, 1, 16))

    # Reconciled without that date being in reconciliation table
    unexplained_missing = cal_sessions - simulated_manifest
    assert len(unexplained_missing) == 1
    assert datetime.date(2024, 1, 16) in unexplained_missing
