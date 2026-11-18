#!/usr/bin/env python3
"""
PRE-2022 INGESTION READINESS PROBE — Audit §80.13 items 3-5

The binding evaluation window is 2018-04-01..2021-12-31 (§10.8) and §80.9 measured that it cannot
gate: A1 has no 2018-2021 holiday circular artifact, A2's identity table begins where Bronze begins
(2022-01-03), and A4 has no 2018-2021 dividend rows or committed maximum-hold bound. This probe is the
executable form of those three preconditions, so the gap is a computation rather than prose (§9.1).

Audit §87.5 Ruling 1 added a fourth precondition that is not a data gate but a mode gate: a captured
pre-2022 session is `WARMUP_NOT_GATABLE`, so no verdict or evaluation set may contain one. A5 reads
every committed verdict artifact in `reports/verdicts/`, resolves its declared window against the
calendar, and refuses (exit 1, refusal printed by name) if any evaluated session precedes the
criteria' `min_binding_evaluation_start_date`.

Each gate prints `PASS` / `NO` / `NOT RUN` with the measurement that decided it, and the process exits
0 only when all of them pass. It is expected to fail until the ingestion lands, so it is deliberately
NOT named `verify_*.py`: the Wave 0.5 gate executes only checks that are actionable today, and a
permanently red check in that list would make green meaningless (§12.4).

Usage:
    python scripts/probe_pre2022_preconditions.py
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.storage.calendar import load_anchored_nse_trading_calendar  # noqa: E402
from signal_core.storage.gating import WARMUP_NOT_GATABLE, warmup_sessions_in  # noqa: E402
from signal_core.storage.security_master import load_cash_universe_symbol_intervals  # noqa: E402
CALENDAR_PATH = REPO_ROOT / "configs" / "trading_calendar_nse.json"
CRITERIA_PATH = REPO_ROOT / "configs" / "go_no_go_criteria.yaml"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
INTERVALS_PATH = REPO_ROOT / "data" / "reference" / "cash_equity_symbol_intervals.csv"
CORPORATE_ACTIONS_PATH = REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl"
CIRCULARS_DIR = REPO_ROOT / "data" / "raw" / "circulars"
VERDICTS_DIR = REPO_ROOT / "reports" / "verdicts"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2021, 12, 31)
WINDOW_YEARS = (2018, 2019, 2020, 2021)


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_current_rows() -> List[dict]:
    rows = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("is_current")]


def _dated_entries(items: Iterable) -> List[datetime.date]:
    """`date` values from a circular's holiday / session list, tolerant of shape."""
    dates: List[datetime.date] = []
    for item in items or []:
        raw = item.get("date") if isinstance(item, dict) else item
        if not isinstance(raw, str):
            continue
        try:
            dates.append(datetime.date.fromisoformat(raw[:10]))
        except ValueError:
            continue
    return dates


def _weekdays(year: int) -> set:
    day = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    out = set()
    while day <= end:
        if day.weekday() < 5:
            out.add(day)
        day += datetime.timedelta(days=1)
    return out


def _circulars_covering(year: int) -> List[Tuple[Path, dict, List[datetime.date]]]:
    """Committed circular artifacts whose holiday/session entries name `year`."""
    covering = []
    for path in sorted(CIRCULARS_DIR.glob("*.json")):
        payload = _load_json(path)
        dates = (
            _dated_entries(payload.get("trading_holidays"))
            + _dated_entries(payload.get("weekend_holidays"))
            + _dated_entries(payload.get("special_sessions"))
            + _dated_entries(payload.get("inferred_trading_sessions"))
        )
        if any(date.year == year for date in dates):
            covering.append((path, payload, dates))
    return covering


def check_a1() -> List[Tuple[str, str]]:
    """§80.13 item 3: one sourced holiday circular per 2018-2021 year that reproduces that year's grid."""
    calendar = _load_json(CALENDAR_PATH)
    fingerprint = str(calendar.get("fingerprint") or "")
    provenance = calendar.get("provenance") or {}
    sessions = [datetime.date.fromisoformat(raw) for raw in calendar.get("sessions") or []]
    current = {str(row.get("artifact")): row for row in _manifest_current_rows()}

    results: List[Tuple[str, str]] = []
    for year in WINDOW_YEARS:
        covering = _circulars_covering(year)
        if not covering:
            results.append((
                "NO",
                f"A1 {year}: no committed holiday circular artifact names a {year} date in "
                f"{CIRCULARS_DIR.relative_to(REPO_ROOT).as_posix()} ({len(list(CIRCULARS_DIR.glob('*.json')))} "
                f"artifact(s) on disk, issued "
                f"{min(_load_json(p).get('issue_date', '?') for p in CIRCULARS_DIR.glob('*.json'))}.."
                f"{max(_load_json(p).get('issue_date', '?') for p in CIRCULARS_DIR.glob('*.json'))})",
            ))
            continue

        problems: List[str] = []
        declared_holidays: set = set()
        declared_specials: set = set()
        for path, payload, _dates in covering:
            rel = f"circulars/{path.name}"
            row = current.get(rel)
            if row is None:
                problems.append(f"{path.name} is not a current manifest row")
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != row.get("sha256") or path.stat().st_size != row.get("byte_count"):
                    problems.append(f"{path.name} does not match its manifest digest")
            if str(payload.get("circular_id")) not in (provenance.get("circular_references") or []):
                problems.append(f"{path.name} is not cited by the calendar's provenance")
            declared_holidays |= {
                date for date in _dated_entries(payload.get("trading_holidays")) if date.year == year
            }
            declared_holidays |= {
                date for date in _dated_entries(payload.get("weekend_holidays")) if date.year == year
            }
            declared_specials |= {
                date for date in _dated_entries(payload.get("special_sessions")) if date.year == year
            }
            declared_specials |= {
                date
                for date in _dated_entries(payload.get("inferred_trading_sessions"))
                if date.year == year
            }

        expected = {day for day in _weekdays(year) if day not in declared_holidays} | declared_specials
        actual = {day for day in sessions if day.year == year}
        unexplained = sorted(actual - expected)
        unsourced = sorted(expected - actual)
        if unexplained:
            problems.append(
                f"{len(unexplained)} calendar session(s) not implied by the circular, "
                f"e.g. {', '.join(d.isoformat() for d in unexplained[:3])}"
            )
        if unsourced:
            problems.append(
                f"{len(unsourced)} circular date(s) absent from the calendar, "
                f"e.g. {', '.join(d.isoformat() for d in unsourced[:3])}"
            )
        if problems:
            results.append(("NO", f"A1 {year}: " + "; ".join(problems)))
        else:
            results.append((
                "PASS",
                f"A1 {year}: {len(actual)} session(s) reproduced by {len(covering)} sourced circular "
                f"artifact(s), {len(declared_holidays)} declared holiday(s)",
            ))

    provenance_sha = str(provenance.get("sha256") or "")
    fingerprint_hex = fingerprint.split("-")[-1] if fingerprint else ""
    if provenance_sha and provenance_sha == fingerprint_hex:
        results.append((
            "NO",
            "A1 provenance: the calendar's provenance.sha256 is its own CAL-FPR digest "
            f"{provenance_sha[:16]}…, not the digest of a source artifact",
        ))
    elif not provenance_sha:
        results.append(("NO", "A1 provenance: the calendar records no provenance digest"))
    else:
        results.append((
            "PASS",
            f"A1 provenance: the calendar names a source digest {provenance_sha[:16]}…",
        ))
    return results


def check_a2() -> List[Tuple[str, str]]:
    """
    §80.13 item 5 / §90.9 item 3: the warm-up window is covered by derived identity intervals.

    The window opens on 2018-04-01, a Sunday that the authoritative calendar does not schedule, and the
    derivation refuses to date an interval on a non-session (Note N-24). The acceptance is therefore
    stated against the window's first *session* and against coverage of every session in the window,
    which is strictly stronger than comparing the earliest row with a date the calendar cannot hold: a
    table that named 2018-04-01 would fail the non-session check the derivation enforces.
    """
    with INTERVALS_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return [("NO", "A2: the identity interval table is empty")]
    active = load_cash_universe_symbol_intervals()
    sessions = [
        session
        for session in load_anchored_nse_trading_calendar().sessions
        if WINDOW_START <= session <= WINDOW_END
    ]
    first = min(row.effective_from for row in active)
    uncovered = [
        session
        for session in sessions
        if not any(
            row.effective_from <= session and (row.effective_to is None or session < row.effective_to)
            for row in active
        )
    ]
    if not sessions:
        return [("NO", "A2: the authoritative calendar names no session in the warm-up window")]
    if first > sessions[0] or uncovered:
        return [(
            "NO",
            f"A2: {len(rows)} interval row(s) with {len(active)} active; earliest "
            f"{first.isoformat()} vs the window's first session {sessions[0].isoformat()}; "
            f"{len(uncovered)} of {len(sessions)} warm-up session(s) uncovered",
        )]
    return [(
        "PASS",
        f"A2: {len(active)} active interval row(s) of {len(rows)} committed, earliest "
        f"{first.isoformat()} = the window's first session, covering all {len(sessions)} warm-up session(s)",
    )]


def _find_key(node, needles: Sequence[str]) -> Optional[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            text = str(key).lower()
            if any(needle in text for needle in needles):
                return f"{key}={value!r}"
            found = _find_key(value, needles)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_key(value, needles)
            if found:
                return found
    return None


def check_a4() -> List[Tuple[str, str]]:
    """§80.13 item 4: 2018-2021 dividends, or a committed maximum-hold bound below the ex-date gap."""
    dividends = [
        datetime.date.fromisoformat(row["ex_date"][:10])
        for row in (
            json.loads(line)
            for line in CORPORATE_ACTIONS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row.get("action_type") == "DIVIDEND" and row.get("ex_date")
    ]
    in_window = sorted(date for date in dividends if WINDOW_START <= date <= WINDOW_END)
    criteria = yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8")) or {}
    bound = _find_key(criteria, ("max_hold", "holding"))

    results: List[Tuple[str, str]] = []
    if in_window:
        results.append((
            "PASS",
            f"A4 dividends: {len(in_window)} ex-date(s) in the window, "
            f"{in_window[0].isoformat()}..{in_window[-1].isoformat()}",
        ))
    else:
        results.append((
            "NO",
            f"A4 dividends: 0 of {len(dividends)} committed ex-date(s) fall in "
            f"{WINDOW_START.isoformat()}..{WINDOW_END.isoformat()}"
            + (
                f" (earliest committed {min(dividends).isoformat()})"
                if dividends
                else ""
            ),
        ))

    if bound:
        results.append(("PASS", f"A4 max hold: {bound} is committed"))
    else:
        results.append((
            "NO",
            "A4 max hold: no maximum-hold bound is committed in "
            f"{CRITERIA_PATH.relative_to(REPO_ROOT).as_posix()}, so a held position's ex-dividend "
            "cash has no window it could be bounded to",
        ))
    return results


def check_gating_mode(verdict_paths: Optional[Iterable[Path]] = None) -> List[Tuple[str, str]]:
    """§87.5 probe (2): no verdict's evaluated session set may contain a WARMUP_NOT_GATABLE session."""
    criteria = yaml.safe_load(CRITERIA_PATH.read_text(encoding="utf-8")) or {}
    binding_start = datetime.date.fromisoformat(
        str(criteria["market_data_and_accounting_invariants"]["min_binding_evaluation_start_date"])
    )
    sessions = [
        datetime.date.fromisoformat(raw)
        for raw in _load_json(CALENDAR_PATH).get("sessions") or []
    ]

    artifacts = (
        sorted(Path(p) for p in verdict_paths)
        if verdict_paths is not None
        else sorted(VERDICTS_DIR.rglob("*.json"))
    )

    evaluated = 0
    violations: List[str] = []
    undated: List[str] = []
    for path in artifacts:
        verdict = _load_json(path)
        try:
            name = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            name = path.as_posix()
        start_raw = verdict.get("evaluation_start_date")
        end_raw = verdict.get("evaluation_end_date")
        if not start_raw or not end_raw:
            undated.append(name)
            continue
        start = datetime.date.fromisoformat(str(start_raw)[:10])
        end = datetime.date.fromisoformat(str(end_raw)[:10])
        window = [session for session in sessions if start <= session <= end]
        evaluated += len(window)
        offending = warmup_sessions_in(window, binding_start_date=binding_start)
        if offending:
            violations.append(
                f"{name} evaluates {len(offending)} of {len(window)} session(s) labelled "
                f"{WARMUP_NOT_GATABLE} ({start.isoformat()}..{end.isoformat()}), "
                f"e.g. {', '.join(d.isoformat() for d in offending[:3])}"
            )

    results: List[Tuple[str, str]] = []
    for violation in violations:
        results.append(("NO", f"A5 gating mode: {violation} — the set may not be gated (§87.5)"))
    for name in undated:
        results.append((
            "NO",
            f"A5 gating mode: {name} declares no evaluation window, so its session set cannot be "
            f"checked against the {WARMUP_NOT_GATABLE} boundary",
        ))
    if not artifacts:
        results.append(("NO", f"A5 gating mode: no verdict artifact found under {VERDICTS_DIR.relative_to(REPO_ROOT).as_posix()}"))
    elif not results:
        results.append((
            "PASS",
            f"A5 gating mode: {len(artifacts)} verdict artifact(s) evaluated, 0 of {evaluated:,} evaluated "
            f"session(s) precede the binding start {binding_start.isoformat()}",
        ))
    return results


def main() -> int:
    print("=" * 96)
    print("PRE-2022 INGESTION READINESS — Audit §80.13 items 3-5 (A1, A2, A4) and §87.5 probe 2 (A5)")
    print(f"Binding window under test: {WINDOW_START.isoformat()}..{WINDOW_END.isoformat()} (§10.8)")
    print("=" * 96)
    results = check_a1() + check_a2() + check_a4() + check_gating_mode()
    for status, message in results:
        print(f"[{status}] {message}")

    unmet = sum(1 for status, _ in results if status != "PASS")
    print("=" * 96)
    if unmet:
        print(
            f"OVERALL: NOT READY — {unmet} of {len(results)} precondition check(s) not met; the window "
            f"stays warm-up only and every pre-2022 verdict stays NOT RUN (§80.9)"
        )
        print("=" * 96)
        return 1
    print(f"OVERALL: READY — all {len(results)} precondition check(s) met")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
