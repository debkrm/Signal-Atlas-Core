"""Verification Script for Historical Dataset Snapshot.

Loads the historical 2022-2024 development dataset snapshot read-only, computes
file SHA-256 and canonical logical fingerprints, and verifies them against
recorded manifest expectations.
"""

import argparse
import datetime
import gzip
import os
from pathlib import Path
import shutil
import sys
from typing import Optional

# Ensure src is on sys.path for standalone script execution
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from signal_core.contracts.legacy_compat import compute_legacy_dataset_content_fingerprint
from signal_core.contracts.provenance import compute_universe_schedule_fingerprint
from signal_core.loaders.historical_snapshot import (
    compute_file_sha256,
    load_historical_snapshot,
    run_dataset_diagnostics,
)


EXPECTED_FILE_SHA256 = "502c6424c79f4856b70608434d6cfab6ef78cd38e4241d38ed5dced4d8c06980"
EXPECTED_CONTENT_FP = "DATA-CTNT-V2-659aea8f18d3b23ba1b9267425bbde8b"
EXPECTED_UNIVERSE_FP = "UNIV-SCHED-V1-5f4d979ba7e62055a171f4e34b45d698"


def resolve_snapshot_path(cli_path: Optional[Path] = None) -> Path:
    """
    Resolves the historical development snapshot JSON path:
    1. Explicit CLI argument if provided and exists
    2. NSE_SNAPSHOT_PATH environment variable if set and exists
    3. Cached uncompressed file at data/reference/historical_dev_dataset_2022_2024.json
    4. Compressed fixture at data/reference/historical_dev_dataset_2022_2024.json.gz (decompressed on-demand)
    5. Fails closed with FileNotFoundError if no valid fixture is found (AGENTS.md §6.3, §12.5).
    """
    if cli_path is not None and cli_path.is_file():
        return cli_path

    env_path = os.environ.get("NSE_SNAPSHOT_PATH")
    if env_path:
        ep = Path(env_path)
        if ep.is_file():
            return ep

    ref_json = _REPO_ROOT / "data" / "reference" / "historical_dev_dataset_2022_2024.json"
    if ref_json.is_file():
        return ref_json

    ref_gz = _REPO_ROOT / "data" / "reference" / "historical_dev_dataset_2022_2024.json.gz"
    if ref_gz.is_file():
        print(f"[INFO] Decompressing cached snapshot fixture: {ref_gz.name} -> {ref_json.name}")
        with gzip.open(ref_gz, "rb") as f_in, open(ref_json, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return ref_json

    legacy_cand = Path(r"C:\Users\DEB\Full Stack Documentation\Practice Projects\Signal-Atlas\data\snapshots\historical_dev_dataset_2022_2024.json")
    if legacy_cand.is_file():
        return legacy_cand

    raise FileNotFoundError(
        f"Historical development dataset snapshot not found. Looked for:\n"
        f"  - CLI argument: {cli_path}\n"
        f"  - NSE_SNAPSHOT_PATH: {env_path}\n"
        f"  - Repository fixture: {ref_json}\n"
        f"  - Gzipped fixture: {ref_gz}\n"
        f"Fail closed per AGENTS.md §6.3, §12.5."
    )


def main():
    parser = argparse.ArgumentParser(description="Verify Historical Snapshot")
    parser.add_argument("--snapshot-path", type=Path, default=None, help="Path to snapshot JSON")
    args = parser.parse_args()

    snapshot_path = resolve_snapshot_path(args.snapshot_path)
    print(f"Loading snapshot from: {snapshot_path}")

    # 1. File SHA-256
    file_sha256 = compute_file_sha256(snapshot_path)
    print(f"Computed File SHA-256:       {file_sha256}")
    print(f"Expected File SHA-256:       {EXPECTED_FILE_SHA256}")
    file_match = file_sha256 == EXPECTED_FILE_SHA256
    print(f"File SHA-256 Match:          {file_match}")

    # 2. Load dataset
    dataset = load_historical_snapshot(snapshot_path)
    print("Snapshot loaded successfully into typed domain objects.")

    # 3. Content Fingerprint V2
    computed_content_fp = compute_legacy_dataset_content_fingerprint(
        trading_dates=dataset.trading_dates,
        prices_by_instrument=dataset.prices_by_instrument,
        benchmark_prices=dataset.benchmark_prices,
        legacy_adjustments=dataset.legacy_adjustments,
    )
    print(f"Computed Content Fingerprint:{computed_content_fp}")
    print(f"Expected Content Fingerprint:{EXPECTED_CONTENT_FP}")
    content_match = computed_content_fp == EXPECTED_CONTENT_FP
    print(f"Content Fingerprint Match:   {content_match}")

    # 4. Universe Schedule Fingerprint V1
    computed_univ_fp = compute_universe_schedule_fingerprint(dataset.universe_schedule)
    print(f"Computed Universe Fingerprint:{computed_univ_fp}")
    print(f"Expected Universe Fingerprint:{EXPECTED_UNIVERSE_FP}")
    univ_match = computed_univ_fp == EXPECTED_UNIVERSE_FP
    print(f"Universe Fingerprint Match:  {univ_match}")

    # 5. Diagnostics
    diag = run_dataset_diagnostics(dataset)
    print("\n--- DATASET CONSISTENCY DIAGNOSTICS ---")
    print(f"Total Trading Sessions:       {diag.total_sessions}")
    print(f"Date Range:                   {diag.start_date} to {diag.end_date}")
    print(f"Instruments in Price Panel:   {diag.instrument_count}")
    print(f"Instrument Price Records:     {diag.instrument_records_count}")
    print(f"Benchmark Records:            {diag.benchmark_records_count}")
    print(f"Total Price Records:          {diag.total_price_records}")
    print(f"Universe Schedule Dates:      {diag.universe_schedule_dates_count}")
    print(f"Unique Universe Members:      {diag.unique_universe_members_count}")
    print(f"Duplicate Records:            {diag.duplicate_records_count}")
    print(f"Universe Dates Outside Cal:   {diag.universe_dates_outside_calendar_count}")
    print(f"Unmatched Member-Date Pairs:  {diag.unmatched_universe_pairs_count}")
    print(f"Unique Members with Mismatch: {diag.unmatched_members_count}")
    print(f"Coverage Min/Max/Avg:         {diag.min_instrument_coverage} / {diag.max_instrument_coverage} / {diag.avg_instrument_coverage:.2f}")

    if diag.unmatched_pairs_by_symbol:
        print("\nUnmatched Pairs Summary by Symbol:")
        for sym, dates in sorted(diag.unmatched_pairs_by_symbol.items()):
            print(f"  {sym:12s}: {len(dates):3d} missing sessions ({dates[0]} to {dates[-1]})")

    if not (file_match and content_match and univ_match):
        print("\nERROR: Verification failed on fingerprint or file digest mismatch!")
        sys.exit(1)
    else:
        print("\nSUCCESS: All file and logical fingerprint verifications PASSED 100%.")


if __name__ == "__main__":
    main()

