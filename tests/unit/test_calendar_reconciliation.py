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

    # Finding H-57: Base circular 71775 did not declare 2026-01-15; only amendment 72260 did
    assert not registry.verify_holiday_claim(datetime.date(2026, 1, 15), "NSE/CMTR/71775"), (
        "2026-01-15 must not be claimed under base circular NSE/CMTR/71775 (Finding H-57)"
    )
    assert registry.verify_holiday_claim(datetime.date(2026, 1, 15), "NSE/CMTR/72260"), (
        "2026-01-15 must be substantiated by partial modification NSE/CMTR/72260 (Finding H-57)"
    )


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

        # 2. Bronze circular registry flags daytime settlement holiday with is_muhurat=True and session_type == MUHURAT
        circ_holiday = registry.holidays.get(m_date)
        assert circ_holiday is not None, f"Muhurat date {m_date} missing from circular holidays"
        assert circ_holiday.is_muhurat is True, f"Muhurat date {m_date} not flagged as is_muhurat"
        assert circ_holiday.session_type == "MUHURAT", f"Muhurat date {m_date} session_type != MUHURAT (Note N-50)"


def test_circular_special_session_local_archive_status():
    """Verify 2025-02-01 special session models local Bronze archive absence (Finding H-60, Note N-49)."""
    registry = load_all_bronze_circulars()
    feb1 = datetime.date(2025, 2, 1)
    rec = registry.special_sessions.get(feb1)
    assert rec is not None, "2025-02-01 missing from special sessions"
    assert rec.session_type == "SPECIAL"
    assert rec.is_settlement_holiday is True
    assert rec.local_archive_status == "ABSENT_FROM_LOCAL_BRONZE_STORAGE", (
        f"2025-02-01 local_archive_status mismatch: {rec.local_archive_status!r} (Note N-49)"
    )


def test_circular_validation_rejects_unauthentic_source_url(tmp_path: Path):
    """Verify circular loader rejects non-NSE source_url fail closed (Finding H-57)."""
    payload = {
        "circular_id": "NSE/CMTR/99991",
        "circular_ref_no": "991/2023",
        "issue_date": "2023-03-10",
        "market": "NSE_CASH_EQUITY",
        "subject": "Fake URL",
        "source_url": "https://unauthorized-domain.com/fake.pdf",
        "http_status": 200,
        "retrieved_at": "2026-11-14T06:00:00+05:30",
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
    }
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    c_path = tmp_path / "NSE_CMTR_99991.json"
    c_path.write_bytes(raw_bytes)

    m_path = tmp_path / "manifest.jsonl"
    m_entry = {
        "artifact": "circulars/NSE_CMTR_99991.json",
        "is_current": True,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "byte_count": len(raw_bytes),
    }
    m_path.write_text(json.dumps(m_entry) + "\n", encoding="utf-8")

    with pytest.raises(CircularError, match="has non-authentic source_url"):
        load_all_bronze_circulars(circulars_dir=tmp_path, manifest_path=m_path)


def test_circular_validation_rejects_naive_retrieved_at_timestamp(tmp_path: Path):
    """Verify circular loader rejects naive retrieved_at timestamp lacking tz offset (Finding H-57)."""
    payload = {
        "circular_id": "NSE/CMTR/99992",
        "source_url": "https://archives.nseindia.com/content/circulars/CMTR99992.pdf",
        "http_status": 200,
        "retrieved_at": "2026-11-14T06:00:00",  # Missing timezone offset
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
    }
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    c_path = tmp_path / "NSE_CMTR_99992.json"
    c_path.write_bytes(raw_bytes)

    m_path = tmp_path / "manifest.jsonl"
    m_entry = {
        "artifact": "circulars/NSE_CMTR_99992.json",
        "is_current": True,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "byte_count": len(raw_bytes),
    }
    m_path.write_text(json.dumps(m_entry) + "\n", encoding="utf-8")

    with pytest.raises(CircularError, match="must include explicit timezone offset"):
        load_all_bronze_circulars(circulars_dir=tmp_path, manifest_path=m_path)


def test_circular_validation_rejects_unauthorized_verified_promotion(tmp_path: Path):
    """Verify circular loader rejects unauthorized VERIFIED provenance_status (Finding H-57, Rule 6.5)."""
    payload = {
        "circular_id": "NSE/CMTR/99993",
        "source_url": "https://archives.nseindia.com/content/circulars/CMTR99993.pdf",
        "http_status": 200,
        "retrieved_at": "2026-11-14T06:00:00+05:30",
        "provenance_status": "VERIFIED",  # Self-promotion prohibited
    }
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    c_path = tmp_path / "NSE_CMTR_99993.json"
    c_path.write_bytes(raw_bytes)

    m_path = tmp_path / "manifest.jsonl"
    m_entry = {
        "artifact": "circulars/NSE_CMTR_99993.json",
        "is_current": True,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "byte_count": len(raw_bytes),
    }
    m_path.write_text(json.dumps(m_entry) + "\n", encoding="utf-8")

    with pytest.raises(CircularError, match="cannot claim VERIFIED without verified source certificates"):
        load_all_bronze_circulars(circulars_dir=tmp_path, manifest_path=m_path)


def test_calendar_annual_session_counts_reconciliation_failure():
    """Verify TradingCalendar construction fails closed if annual session count mismatches actual sessions (Finding H-61)."""
    cal = load_nse_trading_calendar()
    from signal_core.storage.calendar import CalendarError, TradingCalendar

    # Tamper annual_session_counts by altering 2023 count
    tampered_counts = dict(cal.annual_session_counts)
    tampered_counts["2023"] = tampered_counts["2023"] - 1

    with pytest.raises(CalendarError, match="Calendar annual session count mismatch for year 2023"):
        TradingCalendar(
            calendar_id=cal.calendar_id,
            market=cal.market,
            session_records=cal.session_records,
            binding_start_date=cal.binding_start_date,
            fingerprint=cal.fingerprint,
            provenance=cal.provenance,
            annual_session_counts=tampered_counts,
        )


def test_criteria_calendar_invariants_and_unauthorized_special_rejection():
    """Verify criteria pins calendar session counts and authorized special session sets (Findings H-61, H-62, H-64)."""
    criteria = load_go_no_go_criteria()
    assert criteria.expected_total_calendar_sessions == 2935
    assert criteria.expected_authoritative_calendar_sessions == 1196
    assert criteria.expected_baseline_calendar_sessions == 1201
    assert criteria.authorized_unarchived_special_sessions == ("2025-02-01",)
    assert len(criteria.authorized_calendar_holiday_exclusions) == 7
    assert len(criteria.authorized_calendar_trading_inclusions) == 2
    # H-64: fingerprint pin is present and is a valid CAL-FPR-V1 string
    assert criteria.expected_calendar_fingerprint.startswith("CAL-FPR-V1-"), (
        "expected_calendar_fingerprint must carry CAL-FPR-V1- prefix (Finding H-64)"
    )


def test_h64_calendar_fingerprint_identity_anchor():
    """H-64: The criteria-pinned fingerprint must equal the fingerprint computed from the loaded session_records."""
    from signal_core.storage.calendar import load_nse_trading_calendar
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()
    assert cal.fingerprint == criteria.expected_calendar_fingerprint, (
        f"Calendar fingerprint identity mismatch (Finding H-64):\n"
        f"  computed = {cal.fingerprint}\n"
        f"  criteria = {criteria.expected_calendar_fingerprint}"
    )


def test_h64_calendar_fingerprint_detects_date_swap():
    """H-64: A tampered calendar with a date swap fails fingerprint check even if session count is unchanged."""
    import datetime
    from signal_core.storage.calendar import (
        CalendarError, TradingCalendar, TradingSessionRecord, SessionType,
        compute_calendar_fingerprint
    )
    cal = load_nse_trading_calendar()
    criteria = load_go_no_go_criteria()

    # Swap 2023-03-22 (Wednesday) for 2023-03-25 (Saturday) — same count, wrong identity
    tampered = []
    for r in cal.session_records:
        if r.date == datetime.date(2023, 3, 22):
            tampered.append(TradingSessionRecord(
                date=datetime.date(2023, 3, 25),
                session_type=r.session_type,
                open_time=r.open_time,
                close_time=r.close_time,
                description=r.description,
            ))
        else:
            tampered.append(r)

    tampered_fingerprint = compute_calendar_fingerprint(tuple(tampered))
    # Count is unchanged but fingerprint must differ from pinned criteria value
    assert len(tampered) == cal.total_sessions, "Count unchanged after date swap"
    assert tampered_fingerprint != criteria.expected_calendar_fingerprint, (
        "Date swap must produce a different fingerprint than the criteria-pinned anchor (Finding H-64)"
    )
