"""Unit tests for Authoritative Calendar Reconciliation Contract (Findings H-56, H-57, H-58, H-59, H-60, Notes N-41, N-42, N-44, N-47)."""

import datetime
import hashlib
import json
from pathlib import Path
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.storage.calendar import load_nse_trading_calendar, SessionType
from signal_core.storage.circulars import load_all_bronze_circulars, BronzeCircularRegistry, CircularError

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


def test_adversarial_unregistered_circular_payload_rejected_fail_closed(tmp_path: Path):
    """Adversarial probe per Auditor §46.2 (Finding H-57): an unregistered circular payload must be refused."""
    fake_circular = {
        "circular_id": "NSE/CMTR/99999",
        "circular_ref_no": "999/2023",
        "issue_date": "2023-03-10",
        "market": "NSE_CASH_EQUITY",
        "segment": "Capital Market",
        "subject": "Fake Holiday Circular",
        "source_url": "https://fake.url/circular.pdf",
        "retrieved_at": "2026-11-14T06:00:00Z",
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "trading_holidays": [
            {"date": "2023-03-15", "day": "Wednesday", "description": "Fake Holiday"}
        ]
    }
    fake_path = tmp_path / "NSE_CMTR_99999.json"
    fake_path.write_text(json.dumps(fake_circular), encoding="utf-8")

    # Attempting to load from a directory containing an unregistered circular must fail closed
    with pytest.raises(CircularError, match="Unregistered Bronze circular payload"):
        load_all_bronze_circulars(circulars_dir=tmp_path)


def test_calendar_reconciliation_exact_session_set_closure():
    """Verify exact algebraic reconciliation between unified calendar and archive manifest (Findings H-56, H-59, H-60)."""
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    window_start = criteria.min_binding_evaluation_start_date
    window_end = datetime.date(2026, 10, 31)

    cal_sessions = set(s for s in cal.sessions if window_start <= s <= window_end)
    assert len(cal_sessions) == 1196, f"Expected 1,196 authoritative sessions (including 2025-02-01), got {len(cal_sessions)}"
    assert datetime.date(2025, 2, 1) in cal_sessions, "2025-02-01 must be present in authoritative calendar (Finding H-60)"

    with open(RECON_FILE, "r", encoding="utf-8") as f:
        recon_data = json.load(f)

    excluded_holidays: set[datetime.date] = set()
    unarchived_special: set[datetime.date] = set()
    included_trading: set[datetime.date] = set()

    for item in recon_data["entries"]:
        dt = datetime.date.fromisoformat(item["session_date"])
        action = item["action"]
        classification = item["classification"]
        if action == "EXCLUDE_FROM_EXPECTED_ARCHIVES":
            if classification == "OFFICIAL_EXCHANGE_HOLIDAY":
                # Baseline error: holiday erroneously listed as session; purged from unified calendar
                assert dt not in cal_sessions, f"Purged holiday {dt} still present in unified calendar"
                excluded_holidays.add(dt)
            elif classification == "SPECIAL_SESSION_NO_BHAVCOPY_ARCHIVE":
                # Live special session per Finding H-60: present in calendar, absent from local archive cache
                assert dt in cal_sessions, f"Special live session {dt} missing from unified calendar (Finding H-60)"
                unarchived_special.add(dt)
        elif action == "INCLUDE_IN_EXPECTED_ARCHIVES":
            # Real trading session added to unified calendar
            assert dt in cal_sessions, f"Added real session {dt} missing from unified calendar"
            included_trading.add(dt)
        else:
            pytest.fail(f"Invalid action {action} for {dt}")

    # Baseline uncurated schedule reconstruction: 1,196 + 7 - 2 = 1,201
    baseline_sessions = (cal_sessions | excluded_holidays) - included_trading
    assert len(baseline_sessions) == 1201, f"Expected 1,201 baseline sessions, got {len(baseline_sessions)}"

    # Reconciled expected archives: 1,196 - 1 = 1,195
    expected_archived = cal_sessions - unarchived_special
    assert len(expected_archived) == 1195, f"Expected 1,195 archives, got {len(expected_archived)}"

    # Manifest match
    manifest_dates: set[datetime.date] = set()
    with open(ARCHIVE_MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                manifest_dates.add(datetime.date.fromisoformat(json.loads(line)["session_date"]))

    assert len(manifest_dates) == len(expected_archived), f"Manifest count {len(manifest_dates)} != expected {len(expected_archived)}"
    assert expected_archived == manifest_dates, "Expected archived sessions does not match manifest dates"
    assert len(expected_archived ^ manifest_dates) == 0, "Non-empty symmetric difference between expected and manifest"

    # Precise single data gap identification
    assert cal_sessions - manifest_dates == {datetime.date(2025, 2, 1)}, (
        "Expected exactly 2025-02-01 as the sole unarchived special session gap"
    )


def test_calendar_reconciliation_summary_block_matches_computed_counts():
    """Verify summary block fields match computed entries and baseline sets dynamically (Notes N-42, N-44)."""
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

    holiday_dates = {datetime.date.fromisoformat(e["session_date"]) for e in excluded_holidays}
    special_dates = {datetime.date.fromisoformat(e["session_date"]) for e in excluded_special}
    trading_dates = {datetime.date.fromisoformat(e["session_date"]) for e in included_trading}

    baseline_sessions = (cal_sessions | holiday_dates) - trading_dates
    expected_archived = cal_sessions - special_dates

    assert summary["baseline_calendar_sessions"] == len(baseline_sessions)
    assert summary["calendar_sessions_excluded_from_trading"] == len(excluded_holidays)
    assert summary["calendar_sessions_unarchived_special"] == len(excluded_special)
    assert summary["archived_sessions_not_in_baseline_calendar"] == len(included_trading)
    assert summary["expected_reconciled_archived_sessions"] == len(expected_archived)


def test_muhurat_trading_session_modeling_and_circular_coexistence():
    """Verify Diwali Muhurat evening sessions are modeled as live trading sessions without holiday conflict (Note N-47)."""
    cal = load_nse_trading_calendar()
    registry = load_all_bronze_circulars()

    muhurat_dates = [
        datetime.date(2022, 10, 24),
        datetime.date(2023, 11, 12),
        datetime.date(2024, 11, 1),
        datetime.date(2025, 10, 21),
    ]

    for m_date in muhurat_dates:
        # 1. Authoritative calendar models evening session as live MUHURAT trading session
        session_rec = cal.get_session(m_date)
        assert session_rec is not None, f"Muhurat date {m_date} missing from calendar"
        assert session_rec.session_type == SessionType.MUHURAT, f"Muhurat date {m_date} session_type != MUHURAT"

        # 2. Bronze circular registry flags daytime settlement holiday with is_muhurat=True
        circ_holiday = registry.holidays.get(m_date)
        assert circ_holiday is not None, f"Muhurat date {m_date} missing from circular holidays"
        assert circ_holiday.is_muhurat is True, f"Muhurat date {m_date} not flagged as is_muhurat"
