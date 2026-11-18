#!/usr/bin/env python3
"""
DERIVED 2018–2023 SPLIT/BONUS-ADJUSTED CORPUS — Audit §94.6 item 1 (Route B)

Builds `data/reference/historical_dataset_2018_2023.json.gz`, the corpus candidate seq 10 needs and
`scripts/run_seq10_candidate.py` refuses without (Audit §93.4, §94.4).

Route B is the attested back-adjustment route the work order names: the same committed Bronze Bhavcopy
archives, with each `SPLIT` / `BONUS` / `CONSOLIDATION` row from `data/reference/corporate_actions.jsonl`
applied as an exact integer ratio to the price side strictly **before** its ex-date, so no adjusted bar
carries a post-ratio price level backwards. Nothing is forward-filled, interpolated or bridged:

- every calendar session in `2018-04-01..2023-12-31` must be attested by exactly one archive, and every
  archive must name a calendar session in the window (§6.3). A gap fails the build;
- an instrument enters the corpus only if its own bar sequence covers every session between its first
  and its last observation — a missing exchange session inside that span is not measurable evidence and
  is never fabricated (§6.3, §10.1);
- `ISIN_TRANSITION` rows are identity events, never price adjustments, and no series is stitched across
  two ISINs: the corpus is keyed by ISIN, so each identity keeps its own sequence (§10.4);
- `DIVIDEND` rows are untouched: a dividend is a cash inflow on a held position, never a price change
  (§13.2);
- prices and turnover stay exact `Decimal` strings in the snapshot; a binary float never enters the
  ledger (§6.4).

Selection rule, stated rather than implied: an instrument is included when it traded on the first and
the last session of the window and on every session between them. That is the only shape the engine's
continuity invariant can evaluate without a fabricated fill, and it is why the corpus is a *panel*
rather than the whole archive (~5,000 EQ rows per session). Its limit is named, not hidden: an ISIN
whose observations stop before 2023-12-29 has no verified delisting evidence in the corpus, so it is
excluded instead of carried with an unverified trailing gap (§6.3, §10.8).

Usage:
    python scripts/derive_2018_2023_corpus.py            # build, write, register
    python scripts/derive_2018_2023_corpus.py --check    # rebuild in memory and compare to the file
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
import zipfile

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
CORPUS_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"
MANIFEST_ARTIFACT = "data/reference/historical_dataset_2018_2023.json.gz"

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
RAW_YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
SERIES = ("EQ", "BE", "BZ")
ADJUSTMENT_VERSION = "v1.0-split-bonus-backadjust-2018-2023"
DATA_VERSION = "EXP-DEV-2018-2023-V1"
PRICE_QUANTUM = Decimal("0.0001")
PRICE_SIDE_ACTIONS = (
    CorporateActionType.SPLIT,
    CorporateActionType.BONUS,
    CorporateActionType.CONSOLIDATION,
)
BUILT_AT_UTC = "2026-11-18T00:00:00+00:00"


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
    """
    Maps each session to its attested Bronze archive, failing closed on a gap or a surplus.

    A session with no archive is an unmeasurable missing record (§6.3); an archive whose session is not
    a calendar session is an unverified observation. Both stop the build.
    """
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


def price_adjustment_factors(
    sessions: Sequence[datetime.date],
    isin: str,
    actions: Sequence,
) -> List[Tuple[datetime.date, Decimal]]:
    """
    `(ex_date, factor)` pairs for the price-side actions of one ISIN, factor = denominator / numerator.

    Applied strictly before the ex-date: a 10:1 split multiplies every earlier close by 1/10 and leaves
    the ex-date bar at its own traded level, which is what "back-adjust prior to ex-date" means (§5.4).
    """
    return sorted(
        (row.ex_date, row.ratio_denominator / row.ratio_numerator)
        for row in actions
        if row.isin == isin and row.action_type in PRICE_SIDE_ACTIONS and row.ratio_numerator
    )


def cumulative_factor(before: Sequence[Tuple[datetime.date, Decimal]], session: datetime.date) -> Decimal:
    """Product of every ratio whose ex-date is after `session`; 1 when there is none."""
    factor = Decimal(1)
    for ex_date, ratio in before:
        if ex_date > session:
            factor *= ratio
    return factor


def build_corpus() -> Tuple[dict, Dict[str, List[PriceBar]], Dict[str, str], int]:
    """
    Returns `(header, prices_by_isin, symbols_by_isin, archives_read)` for the window.

    The panel is built in memory once; the caller writes it as a gzipped stream.
    """
    from signal_core.storage.ingest import parse_bhavcopy_archive

    sessions = calendar_sessions()
    session_index = {s: i for i, s in enumerate(sessions)}
    paths = archive_paths(sessions)
    actions = load_corporate_actions(CORPORATE_ACTIONS_PATH)

    observations: Dict[str, Dict[datetime.date, Tuple[Decimal, Decimal, Decimal, Decimal, int, Decimal]]] = {}
    symbol_by_isin: Dict[str, str] = {}
    skipped_series_rows = 0
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
                continue
            observations.setdefault(rec.isin, {})[session] = (
                rec.open, rec.high, rec.low, rec.close, rec.volume, rec.traded_value or Decimal(0)
            )
            symbol_by_isin[rec.isin] = rec.symbol

    first_session, last_session = sessions[0], sessions[-1]
    prices_by_isin: Dict[str, List[PriceBar]] = {}
    excluded_short_span = 0
    excluded_internal_gap = 0
    adjusted_instruments = 0
    adjustment_rows_applied = 0
    for isin in sorted(observations):
        rows = observations[isin]
        if min(rows) != first_session or max(rows) != last_session:
            excluded_short_span += 1
            continue
        if len(rows) != len(sessions):
            excluded_internal_gap += 1
            continue
        factors = price_adjustment_factors(sessions, isin, actions)
        if factors:
            adjusted_instruments += 1
            adjustment_rows_applied += len(factors)
        bars: List[PriceBar] = []
        for session in sessions:
            o, h, l, c, volume, traded_value = rows[session]
            factor = cumulative_factor(factors, session)
            if factor != Decimal(1):
                o, h, l, c = ((value * factor).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP) for value in (o, h, l, c))
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
        raise SystemExit("no instrument covers the corpus window end to end; the panel would be empty")

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

    header = {
        "snapshot_format": "signal-atlas-dataset-snapshot-v1",
        "data_version": DATA_VERSION,
        # The declared coverage is the evaluation window, not its first row: 2018-04-01 is a Sunday, so
        # the first session is 2018-04-02 and the corpus states both rather than implying one.
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
            "SPLIT, BONUS and CONSOLIDATION rows of data/reference/corporate_actions.jsonl applied to "
            "open/high/low/close as an exact ratio (denominator/numerator) strictly before the ex-date, "
            "quantised to 0.0001 ROUND_HALF_UP; raw volume and traded value unchanged; DIVIDEND rows are "
            "never price adjustments; ISIN_TRANSITION rows are identity events and no series is stitched "
            "across two ISINs (Audit §94.6 item 1, AGENTS.md §5.4, §10.4, §13.2)."
        ),
        "universe_selection": (
            f"{len(prices_by_isin)} of {len(observations)} observed ISINs: every session from "
            f"{trading_dates[0]} to {trading_dates[-1]} carries an exchange observation, so no rolling "
            f"window is computed across an unexplained gap (§6.3). {excluded_short_span} ISIN(s) whose "
            f"observations start after the first session or stop before the last are excluded rather than "
            f"carried with an unverified boundary; {excluded_internal_gap} are excluded for an internal gap."
        ),
    }
    print(
        f"[INFO] Panel: {len(prices_by_isin)} instrument(s), {total_instrument_records} bar(s) over "
        f"{len(trading_dates)} session(s) {trading_dates[0]}..{trading_dates[-1]}"
    )
    print(
        f"[INFO] Observed ISINs: {len(observations)}; excluded short-span {excluded_short_span}, "
        f"internal-gap {excluded_internal_gap}, non-equity-series rows skipped {skipped_series_rows}"
    )
    print(
        f"[INFO] Adjusted instruments: {adjusted_instruments} carrying {adjustment_rows_applied} price-side "
        f"action(s); corporate_actions sha256 {corporate_actions_digest[:16]}…"
    )
    return header, prices_by_isin, symbols_by_instrument, len(paths)


def write_corpus(
    header: dict,
    prices_by_isin: Dict[str, List[PriceBar]],
    symbols_by_isin: Dict[str, str],
    sessions: Sequence[datetime.date],
) -> Tuple[int, str]:
    """Streams the snapshot to `.json.gz`; returns its byte count and sha256 over the raw file bytes."""
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    byte_count = 0
    with open(CORPUS_PATH, "wb") as raw_handle:
        with gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as gz:
            def emit(chunk: str) -> None:
                nonlocal byte_count
                gz.write(chunk.encode("utf-8"))

            emit("{")
            for key in (
                "snapshot_format", "data_version", "start_date", "first_session", "end_date", "session_count",
                "instrument_count", "total_instrument_records", "benchmark_record_count",
                "content_fingerprint", "source_identity", "adjustment_version",
                "corporate_actions_fingerprint", "created_at", "adjustment_rule", "universe_selection",
            ):
                emit(f"{json.dumps(key)}: {json.dumps(header[key])}, ")
            emit('"trading_dates": ' + json.dumps([session.isoformat() for session in sessions]))
            emit(', "symbols_by_instrument": ' + json.dumps(symbols_by_isin, sort_keys=True))
            emit(', "universe_by_date": {')
            members = json.dumps(sorted(prices_by_isin))
            emit(", ".join(f'"{session.isoformat()}": {members}' for session in sessions))
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
    """
    Appends the corpus to the reference manifest as one current row (§10.1, §10.7).

    A prior current row for the same artifact flips to history rather than being edited, so a rebuild is
    a restatement and not an in-place mutation.
    """
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
            f"{header['instrument_count']} ISINs, {header['total_instrument_records']} adjusted bars)"
        ),
        "retrieval_reference": (
            "Derived from the committed Bronze Bhavcopy archives data/raw/2018..2023, one archive per "
            "calendar session, by scripts/derive_2018_2023_corpus.py under Audit §94.6 item 1 (Route B, "
            "attested split/bonus back-adjustment). Not a retrieval: the corpus is the derived layer, and "
            "`corporate_actions_fingerprint` names the committed corporate-action table it applied."
        ),
        "description": (
            "Derived-layer SPLIT_BONUS_ADJUSTED cash-equity price panel 2018-04-01..2023-12-29 for the "
            "expanded in-sample evaluation window (Audit §94.6 item 1, §95)"
        ),
    }))
    MANIFEST_PATH.write_text("\n".join(written) + "\n", encoding="utf-8", newline="\n")
    print(f"[INFO] Registered {MANIFEST_ARTIFACT} in manifest.jsonl ({superseded} prior current row(s) superseded)")


def main(argv: Sequence[str]) -> int:
    check_only = "--check" in argv
    header, prices_by_isin, symbols_by_isin, archives_read = build_corpus()
    if check_only:
        if not CORPUS_PATH.is_file():
            print(f"OVERALL: ABSENT — {CORPUS_PATH.name} is not on disk")
            return 1
        with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        mismatches = [
            key for key in header
            if on_disk.get(key) != header[key]
        ]
        same_prices = sorted(on_disk.get("prices_by_instrument") or {}) == sorted(prices_by_isin)
        if mismatches or not same_prices:
            print(f"OVERALL: STALE — {len(mismatches)} header field(s) differ ({', '.join(mismatches[:5])}), "
                  f"instrument set equal: {same_prices}")
            return 1
        print(f"OVERALL: CURRENT — {CORPUS_PATH.name} reproduces the Bronze-derived header over {archives_read} archive(s)")
        return 0

    print("=" * 96)
    print("DERIVED 2018–2023 SPLIT/BONUS-ADJUSTED CORPUS — Audit §94.6 item 1 (Route B)")
    print("=" * 96)
    byte_count, sha256_hex = write_corpus(header, prices_by_isin, symbols_by_isin, calendar_sessions())
    print(f"[INFO] Wrote {CORPUS_PATH.relative_to(REPO_ROOT).as_posix()}: {byte_count} bytes, sha256 {sha256_hex[:16]}…")
    register_manifest(byte_count, sha256_hex, header)
    print("=" * 96)
    print(
        f"OVERALL: BUILT — {header['instrument_count']} ISIN(s), {header['total_instrument_records']} bar(s), "
        f"{header['session_count']} session(s) {header['start_date']}..{header['end_date']}, "
        f"adjustment_version {header['adjustment_version']}, corporate_actions_fingerprint "
        f"{header['corporate_actions_fingerprint'][:16]}…, content_fingerprint {header['content_fingerprint']}"
    )
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
