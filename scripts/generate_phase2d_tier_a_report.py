#!/usr/bin/env python3
"""
Signal Atlas — First Real Phase 2D Tier-A Verdict Report Generator.
Assembles results bundle strictly from computed repository artifacts and criteria contracts
over 2022-01-03..2026-10-30 per AGENTS.md §6.5, §7.1, §7.2, §8.1, §8.2, §9.1, §9.2, §9.3,
§10.8, and Audit §55.8.

Invariants:
- Zero hardcoded metric or boolean literals in results bundle (Findings H-73, H-75). All values are
  read from pipeline outputs or dynamically evaluated criteria/calendar contracts.
- Metrics not yet computed across the full 2022-2026 corpus (backtest execution ledger,
  walk-forward fold ratios, DSR, circuit bands, statutory costs) are omitted, honestly evaluating to NOT RUN.
- Evaluates strictly and honestly to NO-GO on unverified archive provenance (CRIT-PROV-01: NOT RUN)
  and pending full-corpus backtest/walk-forward execution metrics.
- Deterministic evaluated_at_utc.
- UTF-8 console and cp1252 safe output (Finding H-74).
- Writes deterministic JSON and Markdown reports to reports/verdicts/.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

# H-74: Reconfigure stdout to UTF-8 when available for console safety
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.reporting.verdicts import (
    OverallVerdict,
    VerdictReport,
    VerdictStatus,
    evaluate_verdicts,
)
from signal_core.storage.calendar import TradingCalendar, load_anchored_nse_trading_calendar


def build_tier_a_results_bundle(
    criteria: GoNoGoCriteria | None = None,
    calendar: TradingCalendar | None = None,
) -> dict:
    """
    Builds the authoritative Phase 2D Tier-A results bundle over 2022-01-03..2026-10-30.
    All data is read from verified repository artifacts and criteria contracts (Findings H-73, H-75).
    Uncomputed backtest/walk-forward metrics and unobserved execution/accounting flags are omitted,
    evaluating honestly to NOT RUN per AGENTS.md §9.1 and Audit §55.8.
    """
    active_criteria = criteria or load_go_no_go_criteria()
    active_calendar = calendar or load_anchored_nse_trading_calendar(criteria=active_criteria)

    # 1. Read authoritative archive manifest entry dynamically
    manifest_path = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Authoritative reference manifest missing at {manifest_path}")

    bhavcopy_manifest_entry = None
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            rec = json.loads(line_str)
            if rec.get("artifact") == "bhavcopy_archive_manifest.jsonl" and rec.get("is_current") is True:
                bhavcopy_manifest_entry = rec
                break

    if bhavcopy_manifest_entry is None:
        raise ValueError("Active bhavcopy_archive_manifest.jsonl entry not found in reference manifest")

    dataset_fp = f"DATA-CTNT-V2-{bhavcopy_manifest_entry['sha256']}"
    prov_status = bhavcopy_manifest_entry.get("provenance_status", "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED")

    # 2. Compute traded EQ resolution percentage and derive archive end date dynamically
    bhavcopy_manifest_file = REPO_ROOT / "data" / "reference" / "bhavcopy_archive_manifest.jsonl"
    traded_eq_resolution_pct = None
    archive_dates: list[datetime.date] = []
    if bhavcopy_manifest_file.is_file():
        total_traded_rows = 0
        with open(bhavcopy_manifest_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                row = json.loads(line_str)
                total_traded_rows += int(row.get("traded_eq_rows", 0))
                if "session_date" in row:
                    archive_dates.append(datetime.date.fromisoformat(row["session_date"]))

        expected_total_rows = int(bhavcopy_manifest_entry.get("total_traded_eq_rows", 0))
        if expected_total_rows > 0:
            traded_eq_resolution_pct = (
                Decimal(str(total_traded_rows)) / Decimal(str(expected_total_rows))
            ) * Decimal("100")

    # 3. Resolve evaluation window dates dynamically from criteria and archive manifest (Finding H-73)
    start_date_str = active_criteria.min_binding_evaluation_start_date.isoformat()
    end_date_limit = max(archive_dates) if archive_dates else active_calendar.end_date
    eligible_sessions = [s for s in active_calendar.sessions if s <= end_date_limit]
    end_date_str = eligible_sessions[-1].isoformat() if eligible_sessions else end_date_limit.isoformat()

    bundle = {
        # Evaluation window (Finding H-65, H-66, H-69)
        "evaluation_start_date": start_date_str,
        "evaluation_end_date": end_date_str,
        "evaluated_at_utc": "2026-11-14T16:45:00+00:00",
        "dataset_fingerprint": dataset_fp,

        # Data provenance status sourced from manifest (Rule 6.5, Residual R-3, Finding H-70)
        "data_provenance_status": prov_status,
        "provenance_attestation_reference": str(bhavcopy_manifest_file),
    }

    # Traded EQ resolution percentage is dynamically populated only when computed from manifest
    if traded_eq_resolution_pct is not None:
        bundle["traded_eq_resolution_pct"] = traded_eq_resolution_pct

    # System invariants and execution metrics (Findings H-73, H-75):
    # Invariant flags (strict Decimal, gap fail-closed, PIT universe, zero fabrication, statutory costs)
    # and execution observation flags (circuit limits, execution latency) are omitted from the bundle
    # until backed by recorded engine execution outputs, honestly evaluating to NOT RUN per §9.1 and §55.8.

    return bundle


def generate_report() -> VerdictReport:
    """Generates, serializes, and verifies the first real Tier-A verdict report."""
    criteria = load_go_no_go_criteria()
    calendar = load_anchored_nse_trading_calendar(criteria=criteria)
    bundle = build_tier_a_results_bundle(criteria=criteria, calendar=calendar)

    report = evaluate_verdicts(
        results_bundle=bundle,
        criteria=criteria,
        calendar=calendar,
    )

    # Output directory
    verdicts_dir = REPO_ROOT / "reports" / "verdicts"
    verdicts_dir.mkdir(parents=True, exist_ok=True)

    json_path = verdicts_dir / "phase2d_tier_a_2022_2026_verdict.json"
    md_path = verdicts_dir / "phase2d_tier_a_2022_2026_verdict.md"

    # Write deterministic outputs with LF line endings
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report.to_dict(), f, indent=2)
        f.write("\n")

    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report.to_markdown() + "\n")

    # Structural and file assertions (Finding H-76, Audit §55.5)
    assert report is not None
    assert len(report.evaluations) == 23
    assert json_path.is_file() and json_path.stat().st_size > 0
    assert md_path.is_file() and md_path.stat().st_size > 0

    print("=" * 80)
    print("PHASE 2D TIER-A VERDICT REPORT GENERATED SUCCESSFULLY")
    print("=" * 80)
    print(f"- Overall Verdict:     {report.overall_verdict.value}")
    print(f"- Evaluation Window:   {report.evaluation_start_date} to {report.evaluation_end_date}")
    print(f"- Evaluated At (UTC):  {report.timestamp_utc}")
    print(f"- Criteria Version:    {report.criteria_version} ({report.criteria_fingerprint[:16]}...)")
    print(f"- Calendar Fingerprint:{report.calendar_fingerprint[:16]}...")
    print(f"- Criteria Summary:    PASS={report.summary_counts['PASS']}, FAIL={report.summary_counts['FAIL']}, NOT_RUN={report.summary_counts['NOT_RUN']}")
    print(f"- Output JSON:         {json_path.relative_to(REPO_ROOT)}")
    print(f"- Output Markdown:     {md_path.relative_to(REPO_ROOT)}")
    print("=" * 80)

    # H-74: Replace ₹ with Rs. when printing markdown to console for cp1252 console safety
    clean_md = report.to_markdown().replace("₹", "Rs.")
    print("\n" + clean_md)
    return report


if __name__ == "__main__":
    generate_report()
