# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 1B.4 Completed** — Ready for **Phase 1C** (Feature & Indicator Foundation) |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, and continuity validation complete |
| **Offline Test Suite** | **64 passed in 0.35s** (100% pass rate, zero warnings) |
| **External Dependencies** | Zero live database connections, zero external network calls, zero shadow simulators |
| **Historical Provenance** | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` (Strictly maintained, zero false promotions) |
| **Holdout Containment** | `HOLDOUT_UNLOCK` is strictly **ABSENT**; out-of-sample data remains completely sealed |
| **Legacy `Signal-Atlas`** | 100% untouched (`historical_dev_dataset_2022_2024.json` SHA-256: `502c6424c79f4856...`) |

---

## 2. Chronological Breakdown of Completed Phases

### Phase 0: Clean-Rebuild Assessment & Migration Plan (Completed)
- Conducted a read-only audit of the legacy `Signal-Atlas` repository.
- Identified core architectural liabilities: shadow simulators, implicit `EQ`-only database extraction filters, floating-point compounding distortion, and unverified provenance promotions.
- Formulated an isolated, phased rebuild plan for `Signal-Atlas-Core` without wholesale code imports.

### Phase 1A & Phase 1A.1: Foundation Contracts & Audit (Completed)
- **`PriceBar` Contract**: Immutable daily OHLCV representation using exact `Decimal` precision. Enforces strict financial invariants: $low \le open \le high$, $low \le close \le high$, volume $\ge 0$, and positive prices. Banned binary floating-point numbers (`float`).
- **`UniverseSchedule` Contract**: Point-in-time universe schedule mapping explicit `datetime.date` sessions to sorted tuples of active instrument identifiers, eliminating survivorship bias.
- **Deterministic Content Fingerprinting**: Implemented `compute_dataset_content_fingerprint` (`DATA-CTNT-V2`) and `compute_universe_schedule_fingerprint` (`UNIV-SCHED-V1`) with canonical decimal string formatting and whitespace normalization.
- **Hardening (1A.1)**: Added strict validation against datetime subclasses, delimiter injections, and duplicate dates.

### Phase 1B & Phase 1B.1: Historical Snapshot Compatibility (Completed)
- Implemented a read-only historical snapshot loader in `Signal-Atlas-Core` to verify compatibility with `historical_dev_dataset_2022_2024.json`.
- Successfully reproduced the recorded SHA-256 file hash (`502c6424...`) and logical content fingerprint (`DATA-CTNT-V2-659aea8f18d3b23ba1b9267425bbde8b`).
- Identified 545 universe-member/date pairs present in the universe schedule that lacked corresponding price bars in the snapshot.

### Phase 1B.2: Raw Bhavcopy Investigation & Series Reconciliation (Completed)
- Audited all 545 missing pairs row-by-row across 743 raw Bhavcopy ZIP archives (2022–2024) using [`scripts/reconcile_bhavcopy_series.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/reconcile_bhavcopy_series.py).
- Output artifact: [`reports/reconciliation/bhavcopy_545_reconciliation.csv`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/reconciliation/bhavcopy_545_reconciliation.csv).
- **Audit Findings**:
  * **511 sessions (93.8%)**: Security traded on the exchange under Trade-to-Trade (`BE`), but was omitted due to a legacy hardcoded `series="EQ"` database extraction filter in `src/signal_atlas/quality/adjustment.py:441`.
  * **19 sessions (3.5%)**: Verified corporate mergers/delistings (`13` HDFC merged into HDFC Bank, `6` MINDTREE merged into LTIMindtree).
  * **15 sessions (2.8%)**: Verified pre-split ISIN superseded post 1:2 stock split (COCHINSHIP old ISIN `INE704P01017`).
  * **0 ambiguous matches, 0 duplicate raw matches**.

### Phase 1B.3 & Phase 1B.4: Exchange-Series Hardening & Continuity Decoupling (Completed)
- **Three-Tier Architecture**:
  1. *Raw Market Observation* ([`ExchangeSessionObservation`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L141)): Retains verbatim exchange series code (`raw_series_code: Optional[str]`, e.g. `"EQ"`, `"BE"`, `"W3"`, `"XX"`), OHLCV (`PriceBar`), ISIN anchor, and source provenance.
  2. *Price-History Continuity* ([`PriceSeriesContinuityValidator`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L268)): Verifies chronological session presence over the official NSE trading calendar. A transition from `EQ` to `BE` **preserves complete continuity** when valid price observations exist on both sides.
  3. *Research Eligibility Policy* ([`SeriesEligibilityPolicy`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L108)): Determines whether an instrument is eligible for strategy entry or holding, decoupled from the underlying price data.
- **Fail-Closed Continuity & Subsegments**:
  * Missing sessions fail closed (`PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD` or `EXTRACTION_FILTER_OMISSION`).
  * Implemented [`partition_into_continuous_subsegments()`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L367) to partition price bars into contiguous blocks where no trading dates were skipped, preventing rolling indicator lookbacks from bridging missing sessions.
- **Policy Quarantine**: Quarantined `QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY` and renamed the rolling candidate to `PROPOSED_UNAPPROVED_EQ_ONLY_POLICY`. Banned implicit default policies.
- **Script Hardening**: Made `--legacy-root` a required CLI argument in `reconcile_bhavcopy_series.py`, eliminating implicit paths.

---

## 3. Current Repository Structure

```
Signal-Atlas-Core/
├── AGENTS.md                                # Non-negotiable quant research guidelines & Indian market rules
├── pyproject.toml                           # Package configuration (signal-core v0.1.0, pytest pythonpath)
├── README.md                                # Core principles & overview
├── WHAT_WE_ARE_BUILDING.md                  # Comprehensive architectural vision & market realities
├── CURRENT_STAGE_OF_WORK.md                 # Current progress, completed milestones & roadmap
├── scripts/
│   └── reconcile_bhavcopy_series.py         # Reproducible Bhavcopy audit tool (strict explicit CLI root)
├── reports/
│   └── reconciliation/
│       ├── bhavcopy_545_reconciliation.csv  # 545-record row-level audit trail
│       └── bhavcopy_series_policy_report.md # Policy report & empirical evidence
├── src/
│   └── signal_core/
│       ├── __init__.py
│       └── contracts/
│           ├── __init__.py                  # Public domain exports
│           ├── price_bar.py                 # Immutable Decimal OHLCV contract
│           ├── universe.py                  # Point-in-time UniverseSchedule & UniverseInterval
│           ├── provenance.py                # Cryptographic fingerprinting (DATA-CTNT-V2, UNIV-SCHED-V1)
│           ├── dataset.py                   # DatasetSnapshot & validation engine
│           ├── exchange_series.py           # Series enum, ExchangeSessionObservation, ContinuityValidator
│           └── legacy_compat.py             # Historical loader & legacy fingerprint adapter
└── tests/
    └── unit/
        ├── test_price_bar.py                # OHLCV invariants, float rejection, decimal validation (10 tests)
        ├── test_universe.py                 # Universe schedules, date queries, immutability (9 tests)
        ├── test_provenance.py               # Golden vectors, determinism, delimiter rejection (10 tests)
        ├── test_dataset.py                  # Snapshot construction, immutability, date ranges (10 tests)
        ├── test_historical_loader.py        # Snapshot parsing, diagnostics, duplicate rejection (11 tests)
        └── test_bhavcopy_reconciliation.py  # Series preservation, continuity, subsegments, Cases 1-4 (14 tests)
                                             # Total: 64 passing unit tests
```

---

## 4. Phased Rebuild Roadmap & Next Steps

```
[Phase 1A: Core Contracts] ──► [Phase 1B: Data Integrity & Bhavcopy Audit]  (COMPLETED)
                                          │
                                          ▼
                         [Phase 1C: Feature & Indicator Engine]            (NEXT IMMEDIATE TASK)
                                          │
                                          ▼
                         [Phase 1D: Indian Execution & Cost Model]
                                          │
                                          ▼
                         [Phase 1E: Exact Decimal Portfolio Ledger]
                                          │
                                          ▼
                         [Phase 2: Strategy Validation & Walk-Forward]
```

### Phase 1C: Feature & Indicator Foundation (Next Immediate Task)
- Implement pure mathematical indicators (EMA, ATR, Rolling High/Low, RSI) operating strictly on contiguous `PriceBar` subsegments produced by `PriceSeriesContinuityValidator`.
- Ensure indicators fail closed and refuse to compute across missing sessions or unverified data gaps.
- Zero lookahead: indicator computed at bar $T$ uses information up to bar $T$ close only.

### Phase 1D: Statutory Indian Cost Engine & Execution Fill Simulator
- Implement the complete Indian statutory transaction cost schedule: STT (delivery vs intraday), NSE exchange turnover fees, SEBI turnover fees, Stamp Duty, GST (18%), and IPFT.
- Implement execution fill simulator with next-session execution ($T+1$ open/TWAP), realistic slippage models parameterized by ADT and spread, and upper/lower circuit fill restrictions.

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting
- Implement exact `Decimal` cash ledger, mark-to-market equity tracker, gross/net PnL accounting, and position tracking.
- Strict rejection of binary floating-point numbers.

### Phase 2: Walk-Forward Strategy Engine & Deflated Sharpe Evaluation
- Multi-hypothesis trial registry logging every sweep.
- Walk-forward parameter stability evaluation across market regimes.
- Automated generation of computed verdicts (PASS/FAIL) against committed `configs/go_no_go_criteria.yaml`.
- Computation of Deflated Sharpe Ratio (DSR) and Haircut Sharpe ratio.

---

## 5. Open Governance Decisions Requiring Owner Signoff

1. **Trade-to-Trade (`BE`) Strategy Eligibility**:
   - The owner must formally authorize whether the quantitative strategy will be permitted to trade securities in `BE` (accepting 100% upfront delivery margin and gross settlement) or will strictly trade rolling `EQ`.
2. **Clean Ingestion Pipeline Rebuild**:
   - In a future phase, a clean data ingestion pipeline should be built to query both `EQ` and `BE` series from raw exchange archives and construct a verified, continuous research dataset.
3. **Holdout Containment**:
   - Keep the out-of-sample holdout dataset sealed (`HOLDOUT_UNLOCK` remains absent) until Phase 2 walk-forward calibration is complete.

