# Bronze Layer Market Data Storage & Partitioning Policy

## Context and Purpose (AGENTS.md §10.1, §10.2, §10.7, Note N-40.4)

This policy establishes the repository storage and lifecycle rules for raw Bronze payloads in Signal Atlas.

### 1. Immutability and Content Addressing (§10.1, §10.2)
- All raw Bronze payloads (e.g. daily Bhavcopy zip archives, index constituent lists, surveillance circulars) are byte-exact as retrieved from exchange distribution endpoints and are never edited or overwritten.
- Files plus their SHA-256 digests recorded in committed manifests constitute the authoritative dataset of record.

### 2. Evaluation Window Baseline vs Historical Partitions (§10.8, §12.5, Note N-40.4)
- **Binding Evaluation Window (2022-01-03 to 2026-10-31):**
  To satisfy AGENTS.md §12.3 and §12.5 (offline, zero-network continuous verification without external repository dependencies), the 1,195 raw daily NSE Bhavcopy archives (~156 MB) covering the active evaluation window are tracked in git under `data/raw/{YEAR}/` and cataloged in `data/reference/bhavcopy_archive_manifest.jsonl`.
- **Pre-Window Historical Partitions (2018-04-01 to 2021-12-31):**
  Pre-window historical archives remain separate. Ingestion of additional historical years must be performed as explicit, atomic partition releases accompanied by manifest registration and verification scripts, avoiding uncontrolled growth of cloned repository size.
  The first such release is the 931-archive warm-up capture authorised by Audit §87.5 Ruling 1: byte-exact archives under `data/raw/2018..2021`, one current `data/reference/manifest.jsonl` row per archive labelled `WARMUP_NOT_GATABLE`, coverage and digest measured by `scripts/probe_pre2022_bronze_coverage.py`. Capture grants no gating eligibility: the pre-2022 window stays `NOT RUN` until A2 and A4 land.
- **Derived Layer Rule (§10.3):**
  All corporate actions, universe schedules, and security master intervals reside strictly in derived tables (e.g. `cash_equity_symbol_intervals.csv`) and are not back-propagated into raw Bronze archives.

### 3. Provenance and Integrity Verification (§6.5, §10.7)
- Raw archives lacking full retrieval source metadata (timestamp, download URL) remain categorized as `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` per §6.5.
- All verification gates (such as Gate COV-2) verify byte count, SHA-256 digests, and reverse coverage against committed manifests before processing rows.
