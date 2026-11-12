# Architectural Decision: Physical Holdout Separation & Manifest Locking

## 1. Decision Summary

- **Decision**: **Physical Holdout Separation (E-15)**
- **Status**: **ADOPTED & COMMITTED**
- **Binding Boundary**: Wave 0, Wave 1, Wave 2, Wave 3, Wave 4
- **Auditor Requirement Reference**: `reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md` §24, §25, §26

---

## 2. Context & Problem Statement

Per AGENTS.md Rule 8.1, historical market datasets must maintain strict, inviolable separation between:
1. **In-Sample (IS)**: 2018-04-01 through 2023-12-31 (exploratory analysis, indicator fitting, feature engineering).
2. **Validation / Calibration**: 2024-01-01 through 2024-12-31 (walk-forward parameter stability tuning).
3. **Out-of-Sample (OOS) Holdout**: 2025-01-01 through 2026-11-11 (strictly sealed confirmatory evaluation).

In Phase 2A and Phase 2C (§25 G-1), holdout containment was implemented via programmatic access checks (`check_partition_access`) and fold date-intersection guards in Python memory. However, the auditor noted in §26:
> *"The holdout must be sealed physically — separate storage root plus a manifest lock (E-15) — not merely by a guard in one engine. A holdout the Gold layer cannot glob is a real seal."*

A procedural-only guard suffers from two fundamental attack vectors:
1. **Accidental Directory Globbing**: Any script, researcher tool, ad-hoc query, or DuckDB view engine globbing `storage/silver/*.parquet` or `storage/gold/` automatically reads holdout partitions into memory if they reside under the same filesystem directory tree.
2. **Concurrent Manifest Interleaving (Finding E-15)**: Concurrent ingestion processes appending to `manifest.jsonl` without inter-process locking can interleave partial lines or corrupt provenance records.

---

## 3. Chosen Architecture: Physical Directory Isolation & Cryptographic Manifest Lock

To guarantee that the sealed holdout cannot be leaked, globbed, or observed prior to formal human unsealing, the following physical isolation invariants are established:

### 3.1 Separate Storage Root Hierarchy

Standard research pipelines, backtest runners, DuckDB views, and strategy engines are configured with the standard data root:
```
storage/
  ├── bronze/
  │     ├── blobs/
  │     └── manifest.jsonl
  ├── silver/
  │     ├── 2018/ ... 2024/   # Only IS (2018-2023) and Validation (2024) partitions reside here
  │     └── manifest.jsonl
  └── gold/
        └── (snapshots, views derived strictly from standard silver)
```

The holdout partitions (2025-01-01 through 2026-11-11) reside in a completely distinct, physically segregated directory hierarchy:
```
storage_holdout/              # Isolated physical root
  ├── bronze/
  │     ├── blobs/
  │     └── manifest.jsonl    # Distinct cryptographic manifest
  ├── silver/
  │     └── 2025/ ... 2026/   # Sealed partitions physically unreachable from storage/silver/
  └── .sealed_manifest.sha256 # Content-addressed root lock digest
```

### 3.2 Inviolable Properties of Physical Separation

> **Implementation status (audit §30, commit `95ac584`):** property 4 below is a *target*, not shipped behaviour. The token hash is read from the caller-supplied `PartitionSpec`, so a caller who supplies both spec and unlock file is self-authorizing (§29 H-16, still open — it gates the creation of `storage_holdout/`). Property 2 is enforced by a **name** test: `storage/silver/holdout` is refused and `storage_holdout/` accepted, but a holdout root nested under a standard tree whose directory is not literally named `silver` is still accepted (§30 H-20). The loaded canonical spec is now checked against the code anchor (§29 H-15, closed at §30). Properties 1 and 3 are implemented.

1. **Physical Unglobbability**:
   `GoldEngine`, `SilverStorage("storage/silver")`, DuckDB views, and file system glob operations (`storage/silver/**/*.parquet`) physically cannot discover or parse any 2025+ holdout file. The operating system filesystem boundary enforces zero access.
2. **Zero Default Ingestion Path**:
   Ingestion tools and backfill pipelines (Wave 3) route 2025–2026 raw responses and silver partitions exclusively to `storage_holdout/`. Standard silver storage explicitly rejects dates falling within `[2025-01-01, 2026-11-11]` unless instantiated with the explicit holdout root and authorization token.
3. **Inter-Process Manifest Locking (E-15)**:
   All manifest writes to `manifest.jsonl` in both standard and holdout trees must acquire the inter-process `.lock` file via `_lock_manifest()`. This guarantees serialized, atomic line appends with zero partial line interleaving.
4. **Cryptographic Root Anchor**:
   The holdout directory tree is anchored by `PART-SPEC-V1` containing `holdout_token_hash`. Mounting or accessing `storage_holdout/` requires supplying the verified `HOLDOUT_UNLOCK` sentinel file matching the token hash.

---

## 4. Operational Sign-Off Criteria for Waves 1–4

- **Wave 0 (Current)**: Architecture decision committed in writing; schema frozen in code; G-1 fail-closed guard implemented in `WalkForwardEngine`.
- **Wave 1 (Thin Slice)**: Uses single month in 2024 (Validation), proving storage contracts on standard path.
- **Wave 2 (Phase 2C Closure)**: Binds strategy runs to dataset fingerprints without holdout access.
- **Wave 3 (Historical Backfill)**: Ingestion script partitions data across `storage/silver/` (2015–2024) and `storage_holdout/silver/` (2025–2026) with zero leakage.
- **Wave 4 (Phase 2D)**: Confirmatory evaluation engine unlocks `storage_holdout/` only when human sentinel is present.

