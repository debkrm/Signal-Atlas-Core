#!/usr/bin/env python3
"""
DERIVED 2018–2023 SPLIT/BONUS-ADJUSTED CORPUS — Audit §95.6 Ruling 1, §95.7 Ruling 2, §95.10 items 3-4

Builds `data/reference/historical_dataset_2018_2023.json.gz`, the corpus candidate seq 10 needs.

**Universe (Ruling 1, §6.1).** `universe_by_date[D]` is exactly the ISINs that traded on `D`. There is
no full-span requirement: Audit §95.5.5 measured that the previous filter removed 564 of the 1,646 names
trading on the window's first session from *every* date, which is survivorship by construction. Continuity
keeps its role where it belongs — on a rolling feature window — and the engine already refuses a lookback
that spans an unexplained gap (`IndicatorValidationError`, `fail_closed_on_unexplained`). Bars are never
forward-filled, interpolated or bridged: a session with no observation has no bar (§6.3).

**Adjustment (Ruling 2, §10.3).** A price ratio is applied only where a committed Bronze corporate-action
payload attests the same ISIN, action type and ex-date, and the row carries the digest of that payload.
An archive-attested event on an observed ISIN that the table lacks fails the build by name; a table row
whose ex-date disagrees with the archive fails the build; a row that cannot be attested is never applied.

**Reconciliation (§95.7).** After adjustment, every one-session return beyond ±35% on the corpus is
classified and published in the header. One class fails the build: `EX_DATE_MISMATCH`, a move within
`MISMATCH_WINDOW_SESSIONS` of an archive-attested **price-side** action (split, bonus, consolidation) on
a different date — the INFY failure mode, where a real bonus was applied eight sessions late. A routine
agreement, a dividend or a scheme record carries no share ratio and cannot be a mis-dated adjustment, so
it is not a near miss (Audit §96.4, §97). The remaining classes stay publish-only: §95.7 measures that a
±35% move can be indistinguishable from a rights-entitlement expiry, an ETF re-denomination or the
March-2020 collapse, so they are reported, never silently dropped, and never a build exit.

Usage:
    python scripts/derive_2018_2023_corpus.py             # build, write, register
    python scripts/derive_2018_2023_corpus.py --report    # build in memory, print diagnostics, write nothing
    python scripts/derive_2018_2023_corpus.py --check     # rebuild in memory and compare to the file
"""

from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from signal_core.contracts.legacy_compat import compute_legacy_dataset_content_fingerprint  # noqa: E402
from signal_core.contracts.price_bar import PriceBar  # noqa: E402
from signal_core.storage.security_master import (  # noqa: E402
    CorporateActionType,
    load_corporate_actions,
)

CALENDAR_PATH = REPO_ROOT / "configs" / "trading_calendar_nse.json"
CORPORATE_ACTIONS_PATH = REPO_ROOT / "data" / "reference" / "corporate_actions.jsonl"
MANIFEST_PATH = REPO_ROOT / "data" / "reference" / "manifest.jsonl"
RAW_ROOT = REPO_ROOT / "data" / "raw"
BRONZE_ACTIONS_DIR = RAW_ROOT / "corporate_actions"
CORPUS_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"
MANIFEST_ARTIFACT = "data/reference/historical_dataset_2018_2023.json.gz"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
RAW_YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
SERIES = ("EQ", "BE", "BZ")
ADJUSTMENT_VERSION = "v2.0-attested-split-bonus-backadjust-2018-2023"
DATA_VERSION = "EXP-DEV-2018-2023-V2"
PRICE_QUANTUM = Decimal("0.0001")
PRICE_SIDE_ACTIONS = (
    CorporateActionType.SPLIT,
    CorporateActionType.BONUS,
    CorporateActionType.CONSOLIDATION,
)
# Audit §95.10 item 4: a one-session move this large without an attested explanation is treated as a
# missing corporate action, not as alpha. The threshold is the one §95.5.3/§95.7 measured with.
UNEXPLAINED_MOVE_THRESHOLD = Decimal("0.35")
# A move this close to an archive-dated action is the ex-date-mismatch defect, not a coincidence.
MISMATCH_WINDOW_SESSIONS = 10
# The action types a mis-dated adjustment can take. A dividend, a rights entitlement, an AGM or a
# demerger record states no share ratio, so it cannot be one of these (§96.4, §97).
PRICE_SIDE_KINDS = tuple(action.value for action in PRICE_SIDE_ACTIONS)
BUILT_AT_UTC = "2026-11-19T00:00:00+00:00"


def calendar_sessions() -> List[datetime.date]:
    """Authoritative sessions in the window, from the committed (human-pinned) calendar."""
    payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    sessions = sorted(
        datetime.date.fromisoformat(str(item["date"]))
        for item in payload.get("session_records") or []
        if WINDOW_START <= datetime.date.fromisoformat(str(item["date"])) <= WINDOW_END
    )
    if not sessions:
        raise SystemExit("the committed calendar schedules no session in the corpus window")
    return sessions


def archive_paths(sessions: Sequence[datetime.date]) -> Dict[datetime.date, Path]:
    """Maps each session to its attested Bronze archive, failing closed on a gap or a surplus."""
    found: Dict[datetime.date, Path] = {}
    surplus: List[str] = []
    session_set = set(sessions)
    for year in RAW_YEARS:
        directory = RAW_ROOT / str(year)
        if not directory.is_dir():
            raise SystemExit(f"no Bronze directory for {year}: {directory}")
        for path in sorted(directory.glob("*.zip")):
            from signal_core.storage.ingest import parse_bhavcopy_archive

            trade_date, _records = parse_bhavcopy_archive(path, target_series=SERIES)
            if trade_date not in session_set:
                surplus.append(f"{path.name} ({trade_date})")
                continue
            if trade_date in found:
                raise SystemExit(
                    f"session {trade_date} is attested by two archives: {found[trade_date].name}, {path.name}"
                )
            found[trade_date] = path
    if surplus:
        raise SystemExit("archive(s) attest a date that is not a calendar session in the window: " + ", ".join(surplus[:5]))
    missing = [s for s in sessions if s not in found]
    if missing:
        raise SystemExit(
            f"{len(missing)} calendar session(s) have no attested archive, first {missing[0]}, last {missing[-1]}: "
            f"a missing exchange session is never bridged (§6.3)"
        )
    return found


def bronze_attestations() -> Dict[Tuple[str, datetime.date], List[Tuple[str, str, str]]]:
    """
    `{(isin, ex_date): [(action_type, subject, payload_digest), ...]}` over the committed archive.

    Every action type is kept, not only the price-side ones: reconciliation needs to know that the
    archive records *something* at an ISIN and date (a demerger, a scheme, a rights issue) even when the
    event carries no share ratio.
    """
    from scripts.attest_price_actions import _ratio_from_subject

    index: Dict[Tuple[str, datetime.date], List[Tuple[str, str, str]]] = {}
    for path in sorted(BRONZE_ACTIONS_DIR.glob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in json.loads(path.read_text(encoding="utf-8")):
            subject = str(row.get("subject") or "").strip()
            low = subject.lower()
            isin = str(row.get("isin") or "")
            if not isin.startswith("IN") or isin == "IN0000000000":
                continue
            try:
                ex_date = datetime.datetime.strptime(str(row["exDate"]), "%d-%b-%Y").date()
            except (KeyError, ValueError):
                continue
            parsed = _ratio_from_subject(subject)
            action_type = parsed[0] if parsed else (
                "DIVIDEND" if "dividend" in low else
                "RIGHTS" if "rights" in low else
                "OTHER"
            )
            index.setdefault((isin, ex_date), []).append((action_type, subject, digest))
    return index


def applied_actions(
    actions: Sequence,
    attestations: Dict[Tuple[str, datetime.date], List[Tuple[str, str, str]]],
) -> Tuple[Dict[str, List[Tuple[datetime.date, Decimal]]], List[str]]:
    """
    The rows this build is allowed to apply, as `{isin: [(ex_date, factor), ...]}`, plus refusals.

    Audit §95.7 Ruling 2: a row is applied only when it is not superseded, carries the digest of a
    committed Bronze payload, and the archive attests the same ISIN, action type and ex-date. A row
    that claims a ratio at an ex-date the archive dates differently is refused by name.
    """
    from decimal import InvalidOperation

    factors: Dict[str, List[Tuple[datetime.date, Decimal]]] = {}
    refusals: List[str] = []
    for row in actions:
        if row.superseded or row.action_type not in PRICE_SIDE_ACTIONS:
            continue
        label = f"{row.symbol or row.isin} {row.ex_date} {row.action_type.value}"
        if not row.source_digest:
            refusals.append(f"{label}: no source_digest, so no committed byte attests it")
            continue
        archive_rows = attestations.get((row.isin, row.ex_date), [])
        if not any(kind == row.action_type.value for kind, _subject, _digest in archive_rows):
            refusals.append(
                f"{label}: the committed archive records no {row.action_type.value} at {row.isin} on {row.ex_date}"
                + (f" (it records: {sorted({kind for kind, _s, _d in archive_rows})})" if archive_rows else " at all")
            )
            continue
        if row.source_digest not in {digest for _kind, _subject, digest in archive_rows}:
            refusals.append(f"{label}: source_digest is not the digest of the payload that attests it")
            continue
        try:
            factor = row.ratio_denominator / row.ratio_numerator
        except (InvalidOperation, ZeroDivisionError):
            refusals.append(f"{label}: ratio {row.ratio_numerator}:{row.ratio_denominator} is not a factor")
            continue
        factors.setdefault(row.isin, []).append((row.ex_date, factor))
    for isin in factors:
        factors[isin].sort()
    return factors, refusals


def require_no_ex_date_mismatch(failures: Sequence[Tuple[str, str, str]]) -> None:
    """
    Fails the build on a non-empty `EX_DATE_MISMATCH` list, naming each ISIN and session (Audit §97).

    §96.4 measured the class documented as fatal being published instead: `failures` was bound and never
    read. A list this size cannot be resolved by a threshold move — the row is either re-dated to the
    archive or the archive record is named, so the build stops and prints what it found.
    """
    if not failures:
        return
    raise SystemExit(
        f"{len(failures)} one-session move(s) beyond ±{UNEXPLAINED_MOVE_THRESHOLD} sit within "
        f"{MISMATCH_WINDOW_SESSIONS} sessions of an archive-attested price-side action on a different date; "
        f"the EX_DATE_MISMATCH class fails the build (§95.7 Ruling 2): "
        + "; ".join(f"{isin} {day} ({detail})" for isin, day, detail in failures[:10])
    )


def attested_actions_missing_from_table() -> List[str]:
    """
    Archive-attested price-side events the table does not carry, one named line each (§95.7 Ruling 2).

    `applied_actions` walks the table and refuses a row it cannot admit, which by construction cannot see
    an attested event the table simply lacks: §96.4 measured that withdrawing an attested row left 0
    refusals and one fewer adjusted instrument. The completeness direction is already computed by
    `scripts/attest_price_actions.reconcile()`; this wrapper exists so the *build* consults it instead of
    the check sitting beside the build unread (§14.4).
    """
    from scripts.attest_price_actions import reconcile

    missing, _contradicted, _present = reconcile(quiet=True)
    return [f"{event.isin} {event.ex_date} {event.action_type}" for event in missing]


def require_attested_actions_present(gaps: Sequence[str]) -> None:
    """Fails the build on an archive-attested action the table does not carry (Audit §97)."""
    if not gaps:
        return
    raise SystemExit(
        f"{len(gaps)} archive-attested price-side action(s) for an in-corpus ISIN are absent from "
        f"{CORPORATE_ACTIONS_PATH.name}; the missing-set direction of §95.7 Ruling 2 fails the build, and the "
        f"row is appended (never inferred): " + "; ".join(gaps[:10])
    )


def cumulative_factor(factors: Sequence[Tuple[datetime.date, Decimal]], session: datetime.date) -> Decimal:
    """Product of every ratio whose ex-date is after `session`; 1 when there is none."""
    value = Decimal(1)
    for ex_date, ratio in factors:
        if ex_date > session:
            value *= ratio
    return value


def build_corpus(require_reconciled: bool = True):
    """
    Returns `(header, prices_by_isin, symbols_by_isin, archives_read, diagnostics)` for the window.

    The panel is built in memory once; the caller writes it as a gzipped stream.
    """
    from signal_core.storage.ingest import parse_bhavcopy_archive

    sessions = calendar_sessions()
    paths = archive_paths(sessions)
    actions = load_corporate_actions(CORPORATE_ACTIONS_PATH)
    attestations = bronze_attestations()
    factors_by_isin, refusals = applied_actions(actions, attestations)
    if refusals:
        raise SystemExit(
            f"{len(refusals)} adjustment row(s) are not admissible under Audit §95.7 Ruling 2; a build "
            f"that applies them would adjust a gating series on an unattested ratio: "
            + "; ".join(refusals[:5])
        )
    require_attested_actions_present(attested_actions_missing_from_table())

    observations: Dict[str, Dict[datetime.date, Tuple[Decimal, Decimal, Decimal, Decimal, int, Decimal]]] = {}
    symbol_by_isin: Dict[str, str] = {}
    skipped_series_rows = 0
    skipped_nonpositive = 0
    for session in sessions:
        trade_date, records = parse_bhavcopy_archive(paths[session], target_series=SERIES)
        if trade_date != session:
            raise SystemExit(f"{paths[session].name} names {trade_date}, not the session it is filed under {session}")
        seen: set = set()
        for rec in records:
            if rec.series not in SERIES:
                skipped_series_rows += 1
                continue
            if rec.isin in seen:
                raise SystemExit(f"{session}: two {rec.series} rows carry ISIN {rec.isin}")
            seen.add(rec.isin)
            if rec.close <= Decimal(0) or rec.open <= Decimal(0) or rec.high <= Decimal(0) or rec.low <= Decimal(0):
                # A zero or missing price is not an observation; it can never be materialised (§6.3).
                skipped_nonpositive += 1
                continue
            observations.setdefault(rec.isin, {})[session] = (
                rec.open, rec.high, rec.low, rec.close, rec.volume, rec.traded_value or Decimal(0)
            )
            symbol_by_isin[rec.isin] = rec.symbol

    prices_by_isin: Dict[str, List[PriceBar]] = {}
    adjusted_instruments = 0
    adjustment_rows_applied = 0
    for isin in sorted(observations):
        rows = observations[isin]
        factors = factors_by_isin.get(isin, [])
        if factors:
            adjusted_instruments += 1
            adjustment_rows_applied += len(factors)
        bars: List[PriceBar] = []
        for session in sorted(rows):
            o, h, l, c, volume, traded_value = rows[session]
            factor = cumulative_factor(factors, session)
            if factor != Decimal(1):
                o, h, l, c = (
                    (value * factor).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
                    for value in (o, h, l, c)
                )
            bars.append(
                PriceBar(
                    instrument_id=isin,
                    trade_date=session,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=volume,
                    traded_value=traded_value,
                )
            )
        prices_by_isin[isin] = bars

    if not prices_by_isin:
        raise SystemExit("no instrument has an observation in the corpus window; the panel would be empty")

    # Audit §95.7: every applied event must actually be inside the observed series, and every extreme
    # one-session move must be explained. A row for an ISIN with no series is inert, not applied.
    inert_rows = [
        isin for isin in factors_by_isin if isin not in observations
    ]
    failures, reconciliation = classify_extreme_moves(prices_by_isin, factors_by_isin, attestations)
    require_no_ex_date_mismatch(failures)
    diagnostics = {
        "observations": len(observations),
        "inert_adjustment_isins": sorted(inert_rows),
        "adjusted_instruments": adjusted_instruments,
        "adjustment_rows_applied": adjustment_rows_applied,
        "reconciliation": reconciliation,
        "skipped_nonpositive": skipped_nonpositive,
        "skipped_series_rows": skipped_series_rows,
    }
    # Audit §95.7 Ruling 2's enforceable half is attestation: no applied row without a committed byte,
    # no archive-attested action left unapplied, no ex-date disagreement. Those three now fail the build
    # above. Of the ±35% detector's classes, only EX_DATE_MISMATCH does (§97): Audit §95.7 measures that
    # a large move can be indistinguishable from a genuine one, and §95.6 Ruling 1's point-in-time
    # universe adds 2,735 names of which most are penny, rights-entitlement or fund lines, so the other
    # four classes are computed and published in the header (`reconciliation`) rather than used as exits.

    symbols_by_instrument = {isin: symbol_by_isin[isin] for isin in prices_by_isin}
    trading_dates = list(sessions)
    content_fingerprint = compute_legacy_dataset_content_fingerprint(
        trading_dates=trading_dates,
        prices_by_instrument=prices_by_isin,
    )
    total_instrument_records = sum(len(bars) for bars in prices_by_isin.values())
    corporate_actions_digest = hashlib.sha256(
        CORPORATE_ACTIONS_PATH.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    members_by_date = {
        session: sorted(isin for isin, rows in observations.items() if session in rows)
        for session in trading_dates
    }

    header = {
        "snapshot_format": "signal-atlas-dataset-snapshot-v1",
        "data_version": DATA_VERSION,
        "start_date": WINDOW_START.isoformat(),
        "first_session": trading_dates[0].isoformat(),
        "end_date": trading_dates[-1].isoformat(),
        "session_count": len(trading_dates),
        "instrument_count": len(prices_by_isin),
        "total_instrument_records": total_instrument_records,
        "benchmark_record_count": 0,
        "content_fingerprint": content_fingerprint,
        "source_identity": "NSE_BHAVCOPY_DAILY",
        "adjustment_version": ADJUSTMENT_VERSION,
        "corporate_actions_fingerprint": corporate_actions_digest,
        "created_at": BUILT_AT_UTC,
        "adjustment_rule": (
            "A SPLIT, BONUS or CONSOLIDATION ratio is applied to open/high/low/close as an exact "
            "denominator/numerator factor strictly before its ex-date, quantised to 0.0001 ROUND_HALF_UP, "
            "only where a committed Bronze corporate-action payload attests the same ISIN, action type "
            "and ex-date and the row carries that payload's sha256. Raw volume and traded value are "
            "unchanged; DIVIDEND rows are never price adjustments; DEMERGER rows carry no attested "
            "consideration ratio and are therefore exit constraints, not ratios (Audit §95.7 Ruling 2, "
            "§95.10 items 4-5, AGENTS.md §5.4, §13.2)."
        ),
        # The rule, not the outcome (§95.10 item 3).
        "universe_selection": (
            "POINT_IN_TIME_TRADED: universe_by_date[D] is exactly the set of ISINs with a valid exchange "
            "observation on D, with no full-span, survival or look-ahead condition. Continuity is enforced "
            "where it belongs — on a rolling feature lookback, which the engine refuses to compute across "
            "an unexplained gap — and bars are never forward-filled, interpolated or bridged (§6.1, §6.3, "
            "§95.6 Ruling 1)."
        ),
        "reconciliation": {
            "threshold": str(UNEXPLAINED_MOVE_THRESHOLD),
            "explained_by_applied_row": reconciliation["explained_applied"],
            "explained_by_archive_record": reconciliation["explained_archive"],
            "no_ratio_match": reconciliation["no_ratio_match"],
            "ratio_shaped_unattested": len(reconciliation["ratio_shaped_unattested"]),
            "ex_date_mismatch": len(reconciliation["ex_date_mismatch"]),
            "ratio_shaped_detail": [
                {"isin": isin, "session": day, "return": ret}
                for isin, day, ret in reconciliation["ratio_shaped_unattested"]
            ],
        },
    }
    return header, prices_by_isin, symbols_by_instrument, len(paths), members_by_date, diagnostics


def classify_extreme_moves(
    prices_by_isin: Dict[str, List[PriceBar]],
    factors_by_isin: Dict[str, List[Tuple[datetime.date, Decimal]]],
    attestations: Dict[Tuple[str, datetime.date], List[Tuple[str, str, str]]],
):
    """
    Classifies every one-session return beyond the threshold and returns `(failures, diagnostics)`.

    Four classes, computed from the data rather than asserted:

    - `APPLIED_ROW` / `ARCHIVE_RECORD`: the move is explained by an applied adjustment at that ISIN and
      date, or by a non-dividend archive record at that ISIN and date.
    - `EX_DATE_MISMATCH`: the archive attests a **price-side** action (`SPLIT`, `BONUS`,
      `CONSOLIDATION`) for that ISIN within `MISMATCH_WINDOW_SESSIONS` of the move but on a different
      date — the INFY failure mode Audit §95.5.4 measured, where a real bonus was applied eight
      sessions late and fabricated two returns. Only a ratio-bearing record can be a mis-dated ratio:
      an AGM, a dividend, a rights entitlement or a scheme record near the move is not a near miss, and
      treating it as one made this class fire on six routine AGMs (§96.4, §97).
      **This is the class that fails the build.**
    - `NO_RATIO_MATCH`: the move is not a share-ratio discontinuity within 0.5%, so no adjustment could
      express it.
    - `RATIO_SHAPED_UNATTESTED`: the move is ratio-shaped (a value a bonus or split could produce) with
      no archive record at all. It is published, never silently dropped, and does not fail the build —
      Audit §95.7 states the reason: "Whether those are actions whose payloads were never captured, or
      actions captured under a different exDate ... cannot be decided from this repository". Measured
      examples in this corpus are the March-2020 circuit-limit collapse (INDUSINDBK +44.7% on
      2020-03-26), the Yes Bank moratorium (YESBANK −56.1% on 2020-03-06), rights-entitlement lines
      (`*-RE`) expiring at a fraction of the share price, and ETF unit re-denominations — none of them a
      corporate action, and all of them indistinguishable from one by price alone.
    """
    failures: List[Tuple[str, str, str]] = []
    ratio_shaped: List[Tuple[str, str, str]] = []
    no_ratio: int = 0
    explained_applied: int = 0
    explained_archive: int = 0

    def _ratio_match(move: Decimal) -> bool:
        target = Decimal(1) + move
        if target <= Decimal(0):
            return False
        for denominator in range(1, 13):
            for numerator in range(1, 25):
                for candidate in (
                    Decimal(numerator) / Decimal(denominator),
                    Decimal(denominator) / Decimal(numerator),
                ):
                    if abs(candidate - target) / target <= Decimal("0.005"):
                        return True
        return False

    for isin, bars in prices_by_isin.items():
        applied_dates = {ex_date for ex_date, _factor in factors_by_isin.get(isin, [])}
        for previous, current in zip(bars, bars[1:]):
            if previous.close <= Decimal(0):
                continue
            move = (current.close - previous.close) / previous.close
            if abs(move) <= UNEXPLAINED_MOVE_THRESHOLD:
                continue
            rendered = format(move.quantize(Decimal("0.0001")), "f")
            if current.trade_date in applied_dates:
                explained_applied += 1
                continue
            records = attestations.get((isin, current.trade_date), [])
            non_dividend = [
                kind for kind, subject, _digest in records
                if kind != "DIVIDEND" or "dividend" not in subject.lower()
            ]
            if non_dividend:
                explained_archive += 1
                continue
            near_miss = sorted(
                day for (record_isin, day) in attestations
                if record_isin == isin
                and abs((day - current.trade_date).days) <= MISMATCH_WINDOW_SESSIONS
                and any(
                    kind in PRICE_SIDE_KINDS for kind, _subject, _digest in attestations[(record_isin, day)]
                )
            )
            if near_miss:
                failures.append(
                    (isin, current.trade_date.isoformat(), f"{rendered} but the archive attests an action on {near_miss[0]}")
                )
                continue
            if _ratio_match(move):
                ratio_shaped.append((isin, current.trade_date.isoformat(), rendered))
            else:
                no_ratio += 1
    diagnostics = {
        "explained_applied": explained_applied,
        "explained_archive": explained_archive,
        "ratio_shaped_unattested": ratio_shaped,
        "no_ratio_match": no_ratio,
        "ex_date_mismatch": failures,
    }
    return failures, diagnostics


def write_corpus(
    header: dict,
    prices_by_isin: Dict[str, List[PriceBar]],
    symbols_by_isin: Dict[str, str],
    sessions: Sequence[datetime.date],
    members_by_date: Dict[datetime.date, List[str]],
) -> Tuple[int, str]:
    """Streams the snapshot to `.json.gz`; returns its byte count and sha256 over the raw file bytes."""
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    byte_count = 0
    header_keys = (
        "snapshot_format", "data_version", "start_date", "first_session", "end_date", "session_count",
        "instrument_count", "total_instrument_records", "benchmark_record_count", "content_fingerprint",
        "source_identity", "adjustment_version", "corporate_actions_fingerprint", "created_at",
        "adjustment_rule", "universe_selection", "reconciliation",
    )
    with open(CORPUS_PATH, "wb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as gz:
            def emit(chunk: str) -> None:
                nonlocal byte_count
                gz.write(chunk.encode("utf-8"))

            emit("{")
            for key in header_keys:
                emit(f"{json.dumps(key)}: {json.dumps(header[key])}, ")
            emit('"trading_dates": ' + json.dumps([session.isoformat() for session in sessions]))
            emit(', "symbols_by_instrument": ' + json.dumps(symbols_by_isin, sort_keys=True))
            emit(', "universe_by_date": {')
            emit(
                ", ".join(
                    f'"{session.isoformat()}": {json.dumps(members_by_date[session])}'
                    for session in sessions
                )
            )
            emit('}, "prices_by_instrument": {')
            first = True
            for isin in sorted(prices_by_isin):
                payload = json.dumps([
                    {
                        "trade_date": bar.trade_date.isoformat(),
                        "open": format(bar.open, "f"),
                        "high": format(bar.high, "f"),
                        "low": format(bar.low, "f"),
                        "close": format(bar.close, "f"),
                        "raw_volume": bar.volume,
                        "volume": format(Decimal(bar.volume), "f"),
                        "traded_value": format(bar.traded_value, "f") if bar.traded_value is not None else None,
                        "adjustment_version": ADJUSTMENT_VERSION,
                    }
                    for bar in prices_by_isin[isin]
                ])
                emit(("" if first else ", ") + json.dumps(isin) + ": " + payload)
                first = False
            emit("}}")
    digest = hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()
    byte_count = CORPUS_PATH.stat().st_size
    return byte_count, digest


def register_manifest(byte_count: int, sha256_hex: str, header: dict) -> None:
    """Appends the corpus to the reference manifest as one current row (§10.1, §10.7)."""
    lines = [line for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    written: List[str] = []
    superseded = 0
    for line in lines:
        row = json.loads(line)
        if row.get("artifact") == MANIFEST_ARTIFACT and row.get("is_current"):
            row["is_current"] = False
            row["status"] = "superseded"
            superseded += 1
            line = json.dumps(row)
        written.append(line)
    written.append(json.dumps({
        "artifact": MANIFEST_ARTIFACT,
        "is_current": True,
        "status": "active",
        "timestamp_utc": BUILT_AT_UTC,
        "byte_count": byte_count,
        "sha256": sha256_hex,
        "provenance_status": "CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED",
        "source_coverage": (
            f"{header['start_date']} to {header['end_date']} ({header['session_count']} NSE sessions, "
            f"{header['instrument_count']} ISINs, {header['total_instrument_records']} adjusted bars, "
            f"point-in-time universe)"
        ),
        "retrieval_reference": (
            "Derived from the committed Bronze Bhavcopy archives data/raw/2018..2023, one archive per "
            "calendar session, by scripts/derive_2018_2023_corpus.py under Audit §95.6 Ruling 1 and §95.7 "
            "Ruling 2: every adjustment is attested by a committed corporate-action payload whose digest "
            "the row carries, and every one-session move beyond ±35% is reconciled against that archive."
        ),
        "description": (
            "Derived-layer SPLIT_BONUS_ADJUSTED cash-equity price panel 2018-04-01..2023-12-29 with a "
            "POINT_IN_TIME_TRADED universe for the expanded in-sample evaluation window (§95.10 items 3-4)"
        ),
    }))
    MANIFEST_PATH.write_text("\n".join(written) + "\n", encoding="utf-8", newline="\n")
    print(f"[INFO] Registered {MANIFEST_ARTIFACT} in manifest.jsonl ({superseded} prior current row(s) superseded)")


def main(argv: Sequence[str]) -> int:
    check_only = "--check" in argv
    report_only = "--report" in argv
    header, prices_by_isin, symbols_by_isin, archives_read, members_by_date, diagnostics = build_corpus(
        require_reconciled=False
    )
    if report_only:
        print(f"[INFO] Observed ISINs {diagnostics['observations']}, bars {header['total_instrument_records']}")
        print(
            f"[INFO] Universe members: first session {len(members_by_date[calendar_sessions()[0]])}, "
            f"last session {len(members_by_date[calendar_sessions()[-1]])}, "
            f"distinct members over the window {len({i for v in members_by_date.values() for i in v})}"
        )
        print(
            f"[INFO] Adjusted {diagnostics['adjusted_instruments']} instrument(s) over "
            f"{diagnostics['adjustment_rows_applied']} attested row(s); inert adjustment ISINs "
            f"{len(diagnostics['inert_adjustment_isins'])}"
        )
        rec = diagnostics["reconciliation"]
        print(
            f"[INFO] One-session moves beyond ±{UNEXPLAINED_MOVE_THRESHOLD}: "
            f"{rec['explained_applied'] + rec['explained_archive'] + len(rec['ratio_shaped_unattested']) + rec['no_ratio_match']} "
            f"(applied row {rec['explained_applied']}, archive record {rec['explained_archive']}, "
            f"ratio-shaped unattested {len(rec['ratio_shaped_unattested'])}, "
            f"not ratio-shaped {rec['no_ratio_match']}, ex-date mismatch {len(rec['ex_date_mismatch'])})"
        )
        for isin, day, detail in rec["ex_date_mismatch"][:10]:
            print(f"        EX_DATE_MISMATCH {day} {isin} {detail}")
        return 0
    if check_only:
        if not CORPUS_PATH.is_file():
            print(f"OVERALL: ABSENT — {CORPUS_PATH.name} is not on disk")
            return 1
        with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        mismatches = [key for key in header if on_disk.get(key) != header[key]]
        same_prices = sorted(on_disk.get("prices_by_instrument") or {}) == sorted(prices_by_isin)
        if mismatches or not same_prices:
            print(f"OVERALL: STALE — {len(mismatches)} header field(s) differ ({', '.join(mismatches[:5])}), "
                  f"instrument set equal: {same_prices}")
            return 1
        print(f"OVERALL: CURRENT — {CORPUS_PATH.name} reproduces the Bronze-derived header over {archives_read} archive(s)")
        return 0

    print("=" * 96)
    print("DERIVED 2018–2023 SPLIT/BONUS-ADJUSTED CORPUS — §95.6 Ruling 1, §95.7 Ruling 2")
    print("=" * 96)
    byte_count, sha256_hex = write_corpus(
        header, prices_by_isin, symbols_by_isin, calendar_sessions(), members_by_date
    )
    print(f"[INFO] Wrote {CORPUS_PATH.relative_to(REPO_ROOT).as_posix()}: {byte_count} bytes, sha256 {sha256_hex[:16]}…")
    register_manifest(byte_count, sha256_hex, header)
    print("=" * 96)
    print(
        f"OVERALL: BUILT — {header['instrument_count']} ISIN(s), {header['total_instrument_records']} bar(s), "
        f"{header['session_count']} session(s) {header['start_date']}..{header['end_date']}, "
        f"adjustment_version {header['adjustment_version']}, universe POINT_IN_TIME_TRADED, "
        f"{header['reconciliation']['ex_date_mismatch']} ex-date mismatch(es), "
        f"content_fingerprint {header['content_fingerprint']}"
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
