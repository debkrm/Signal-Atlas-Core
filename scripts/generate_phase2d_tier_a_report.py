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
        "evaluated_at_utc": "2026-11-16T10:00:00+00:00",
        "dataset_fingerprint": dataset_fp,

        # Data provenance status sourced from manifest (Rule 6.5, Residual R-3, Finding H-70)
        "data_provenance_status": prov_status,
        "provenance_attestation_reference": str(bhavcopy_manifest_file),

        # Audit §75.10 items 3-4: criteria 1.1.5 pre-registers the cross-sectional entry rank and the
        # minimum viable order sizes. They change which signal gets a slot and what a booked trade is,
        # not a threshold, and they enter the criteria fingerprint, so the committed artifact is
        # restated rather than left describing a criteria version that no longer governs.
        "restatement_note": (
            "Restatement 2026-11-17 (Audit §76.16 items 1-6): supersedes the 1.1.5 restatement "
            "recorded under Audit §75.10 items 3-4, the 1.1.4 restatement recorded under §74.10 "
            "Ruling D, the 1.1.3 one under §73.9 items 3-4, the 1.1.2 one under §72 N-128, the 1.1.1 "
            "one under §68.6 item 3 (H-115), and the 2026-11-14T16:45:00+00:00 artifact before those. "
            "Criteria version 1.1.6 changes no numeric PASS/FAIL threshold. It (i) excludes "
            "expected_trial_registry_manifest_sha256 from the criteria fingerprint, so appending a "
            "trial and re-pinning the manifest no longer invalidates the anchor a verdict cites, "
            "while the pin stays mandatory in the loader and is still enforced by Gate G2A-6.8a "
            "(N-139); (ii) gates min_haircut_sharpe_ratio = 1.25 as CRIT-OVERFIT-04 instead of "
            "leaving a committed threshold unenforced (N-141); (iii) evaluates CRIT-STAT-01 and "
            "CRIT-STAT-02 on the liquidated book, with the closed-only pair and the PF sensitivity "
            "to the largest winners retained as disclosures on the same rows (Ruling 1); (iv) "
            "evaluates CRIT-STAT-03 at trade entry, as its own definition says, with the hold-period "
            "maximum reported and not gated (Ruling 2); (v) wires CRIT-DATA-05 to the H-54 "
            "traded-row measure and adds CRIT-DATA-07 dataset completeness at 100.0%, so 196 / 211 "
            "= 92.8910% fails closed until the 15 unresolved instruments are accounted for (Ruling "
            "3, N-140); and (vi) attributes every ticket rejection by side and reason, so a refused "
            "SELL is visible (N-142). The trials manifest pin is unchanged at 3326b1b2... with "
            "N = 9, N_eval = 5, and no trial was appended or scored in this commit. Provenance "
            "remains CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED, so CRIT-PROV-01 is still NOT RUN "
            "and every Tier-A verdict is unchanged."
        ),
    }

    # Traded EQ resolution percentage is dynamically populated only when computed from manifest
    if traded_eq_resolution_pct is not None:
        bundle["traded_eq_resolution_pct"] = traded_eq_resolution_pct

    # System invariants and execution metrics (Findings H-73, H-75):
    # Invariant flags (strict Decimal, gap fail-closed, PIT universe, zero fabrication, statutory costs)
    # and execution observation flags (circuit limits, execution latency) are omitted from the bundle
    # until backed by recorded engine execution outputs, honestly evaluating to NOT RUN per §9.1 and §55.8.

    validate_results_bundle_types(bundle)
    return bundle


def validate_results_bundle_types(bundle: Mapping[str, Any]) -> None:
    """
    Enforces runtime guard asserting zero bool, int, or float values in emitted results bundle
    (AGENTS.md §6.4, §9.1, Findings H-73, N-63, N-69, N-78).
    Only Decimal, str, or datetime types are permitted.

    Runtime vs AST Layering and Residual Limitations (Findings N-79, N-85):
    - Runtime validation inspects instantiated dictionary values directly, so it reliably
      catches bool, int, or float values regardless of syntactic origin (including annotated
      assignments, tuple unpacking, and helper return values).
    - True residual limitation escaping runtime type checks:
      String laundering into Decimal: `k = "1.6850"; b["k"] = Decimal(k)`.
    This pattern is prevented by committed diff reviews, verification assertions, and human audit (§57.4, §58.3).
    """
    for k, v in bundle.items():
        if isinstance(v, (bool, int, float)):
            raise TypeError(
                f"Bundle key {k!r} has forbidden literal type {type(v).__name__} (Findings N-69, N-78). "
                "Only Decimal, str, or datetime types are permitted."
            )


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
    if "restatement_note" in bundle:
        report.metadata["restatement_note"] = bundle["restatement_note"]

    # Output directory
    verdicts_dir = REPO_ROOT / "reports" / "verdicts"
    verdicts_dir.mkdir(parents=True, exist_ok=True)

    json_path = verdicts_dir / "phase2d_tier_a_2022_2026_verdict.json"
    md_path = verdicts_dir / "phase2d_tier_a_2022_2026_verdict.md"

    # Write deterministic outputs with LF line endings
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report.to_dict(), f, indent=2)
        f.write("\n")

    md_text = report.to_markdown()
    if "restatement_note" in bundle:
        md_text += f"\n> **Restatement:** {bundle['restatement_note']}\n"
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md_text + "\n")

    # Structural and file assertions (Findings H-76, N-68, Audit §55.5, §56.4)
    assert report is not None
    assert report.evaluations, "Verdict report evaluations cannot be empty"
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
