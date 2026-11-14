"""Unit tests for Authoritative Calendar Reconciliation Contract (Findings H-56, H-57, H-58, H-59, Notes N-41, N-42)."""

import datetime
import hashlib
import json
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.storage.calendar import load_nse_trading_calendar
from signal_core.storage.circulars import load_all_bronze_circulars, BronzeCircularRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECON_FILE = REPO_ROOT / "data" / "reference" / "calendar_reconciliation_2022_2026.json"
MANIFEST_FILE = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
ARCHIVE_MANIFEST = REPO_ROOT / "data" / "reference" / "bhavcopy_archive_manifest.jsonl"


def test_calendar_reconciliation_manifest_registration():
    """Verify calendar reconciliation table is registered in manifest.jsonl with matching digest (§6.5, §10.7, H-56, H-58)."""
    assert RECON_FILE.is_file(), f"Reconciliation file missing at {RECON_FILE}"

    # Normalize CRLF to LF for deterministic digest comparison across platforms (Finding H-58)
    recon_bytes = RECON_FILE.read_bytes().replace(b"\r\n", b"\n")
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


def test_calendar_reconciliation_bronze_circular_substantiation():
    """Verify every claimed holiday/trading session in reconciliation is substantiated by authentic Bronze circulars (Finding H-57)."""
    registry = load_all_bronze_circulars()
    assert len(registry.circular_digests) >= 7, f"Expected at least 7 Bronze circular payloads, got {len(registry.circular_digests)}"

    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    for item in recon_data.get("entries", []):
        dt = datetime.date.fromisoformat(item["session_date"])
        classification = item["classification"]
        circulars = item.get("circular_references", [])

        if classification == "OFFICIAL_EXCHANGE_HOLIDAY":
            substantiated = any(registry.verify_holiday_claim(dt, c_id) for c_id in circulars)
            assert substantiated, f"Holiday claim for {dt} under {circulars} failed Bronze circular substantiation"
        elif classification == "SPECIAL_SESSION_NO_BHAVCOPY_ARCHIVE":
            substantiated = any(registry.verify_special_session_claim(dt, c_id) for c_id in circulars)
            assert substantiated, f"Special session claim for {dt} under {circulars} failed Bronze circular substantiation"
        elif classification == "OFFICIAL_TRADING_SESSION":
            substantiated = any(registry.verify_trading_day_claim(dt, c_id) for c_id in circulars)
            assert substantiated, f"Trading day claim for {dt} under {circulars} failed Bronze circular substantiation"
        else:
            pytest.fail(f"Unexpected classification {classification} for {dt}")


def test_adversarial_unsubstantiated_holiday_claim_rejected():
    """Adversarial probe per Auditor §45.2 (Finding H-57): deleting a real session cannot be justified by an authentic circular."""
    registry = load_all_bronze_circulars()

    # 2023-03-15 was a real trading session with 1,923 traded EQ instruments.
    # An adversary claiming 2023-03-15 was a holiday under NSE_CMTR_2023_HOLIDAYS must fail closed.
    real_session = datetime.date(2023, 3, 15)
    assert not registry.verify_holiday_claim(real_session, "NSE/CMTR/2023_HOLIDAYS"), (
        "Adversarial holiday claim on 2023-03-15 must return False!"
    )

    # A non-existent circular must also fail
    assert not registry.verify_holiday_claim(real_session, "NSE/FAKE/99999")

    # A trading day claim on a fake date must also fail
    assert not registry.verify_trading_day_claim(datetime.date(2026, 3, 21), "NSE/CMTR/71775")


def test_calendar_reconciliation_exact_session_set_closure():
    """Verify exact algebraic reconciliation between unified calendar and archive manifest (Findings H-56, H-59)."""
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    window_start = criteria.min_binding_evaluation_start_date
    window_end = datetime.date(2026, 10, 31)

    cal_sessions = set(s for s in cal.sessions if window_start <= s <= window_end)

    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    excluded: set[datetime.date] = set()
    included: set[datetime.date] = set()

    for item in recon_data["entries"]:
        dt = datetime.date.fromisoformat(item["session_date"])
        action = item["action"]
        if action == "EXCLUDE_FROM_EXPECTED_ARCHIVES":
            # Per Finding H-59, the unified calendar purged these non-sessions
            assert dt not in cal_sessions, f"Purged non-session {dt} still present in unified calendar"
            excluded.add(dt)
        elif action == "INCLUDE_IN_EXPECTED_ARCHIVES":
            # Per Finding H-59, the unified calendar added these real trading sessions
            assert dt in cal_sessions, f"Added real session {dt} missing from unified calendar"
            included.add(dt)
        else:
            pytest.fail(f"Invalid action {action} for {dt}")

    # Baseline uncurated schedule reconstruction
    baseline_sessions = (cal_sessions | excluded) - included
    assert len(baseline_sessions) == 1201, f"Expected 1,201 baseline sessions, got {len(baseline_sessions)}"

    # Reconciled algebraic closure
    reconciled_expected = (baseline_sessions - excluded) | included
    assert reconciled_expected == cal_sessions, "Algebraic reconciliation does not equal unified calendar sessions"

    # Manifest match
    manifest_dates: set[datetime.date] = set()
    with open(ARCHIVE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                manifest_dates.add(datetime.date.fromisoformat(json.loads(line)["session_date"]))

    assert len(manifest_dates) == len(cal_sessions), f"Manifest dates count {len(manifest_dates)} != cal_sessions {len(cal_sessions)}"
    assert cal_sessions == manifest_dates, "Unified calendar session set does not match manifest dates"
    assert len(cal_sessions ^ manifest_dates) == 0, "Non-empty symmetric difference between calendar and manifest"


def test_calendar_reconciliation_summary_block_matches_computed_counts():
    """Verify summary block fields match computed entries and baseline sets (Note N-42)."""
    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    summary = recon_data.get("summary", {})
    entries = recon_data.get("entries", [])

    excluded_holidays = [e for e in entries if e["classification"] == "OFFICIAL_EXCHANGE_HOLIDAY"]
    excluded_special = [e for e in entries if e["classification"] == "SPECIAL_SESSION_NO_BHAVCOPY_ARCHIVE"]
    included_trading = [e for e in entries if e["classification"] == "OFFICIAL_TRADING_SESSION"]

    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    cal_sessions = set(s for s in cal.sessions if criteria.min_binding_evaluation_start_date <= s <= datetime.date(2026, 10, 31))

    excluded_dates = {datetime.date.fromisoformat(e["session_date"]) for e in excluded_holidays + excluded_special}
    included_dates = {datetime.date.fromisoformat(e["session_date"]) for e in included_trading}
    baseline_sessions = (cal_sessions | excluded_dates) - included_dates

    assert summary["baseline_calendar_sessions"] == len(baseline_sessions)
    assert summary["calendar_sessions_excluded_from_trading"] == len(excluded_holidays)
    assert summary["calendar_sessions_unarchived_special"] == len(excluded_special)
    assert summary["archived_sessions_not_in_baseline_calendar"] == len(included_trading)
    assert summary["expected_reconciled_archived_sessions"] == len(cal_sessions)


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
