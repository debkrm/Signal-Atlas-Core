# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 1C Completed & Hardened** (All DeepSeek Audit Recommendations Remediated) — Ready for **Phase 1D** |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, series continuity, pure subsegment feature engine, and typed criteria loader complete |
| **Offline Test Suite** | **91 passed in 0.79s** (100% pass rate, zero warnings) |
| **External Dependencies** | Zero live database connections, zero external network calls, zero shadow simulators |
| **Historical Provenance** | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` (Strictly maintained, zero false promotions) |
| **Holdout Containment** | `HOLDOUT_UNLOCK` is strictly **ABSENT**; out-of-sample data remains completely sealed |
| **Authoritative Criteria** | Committed in [`configs/go_no_go_criteria.yaml`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/configs/go_no_go_criteria.yaml), typed loader in [`criteria.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/criteria.py) (DSR, Haircut Sharpe, Max Drawdown, Effective-Dated Indian Statutory Cost Schedule) |
| **Approved Strategy Policy** | [`APPROVED_EQ_ONLY_POLICY`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L141) (Strict rolling cash equity; Trade-to-Trade `BE` excluded from trade entry) |
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
  1. *Raw Market Observation* ([`ExchangeSessionObservation`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L155)): Retains verbatim exchange series code (`raw_series_code: Optional[str]`, e.g. `"EQ"`, `"BE"`, `"W3"`, `"XX"`), OHLCV (`PriceBar`), ISIN anchor, and source provenance.
  2. *Price-History Continuity* ([`PriceSeriesContinuityValidator`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L303)): Verifies chronological session presence over the official NSE trading calendar. A transition from `EQ` to `BE` **preserves complete continuity** when valid price observations exist on both sides.
  3. *Research Eligibility Policy* ([`SeriesEligibilityPolicy`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L121)): Determines whether an instrument is eligible for strategy entry or holding, decoupled from the underlying price data.
- **Fail-Closed Continuity & Subsegments**:
  * Missing sessions fail closed (`PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD` or `EXTRACTION_FILTER_OMISSION`).
  * Implemented [`partition_into_continuous_subsegments()`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L454) to partition price bars into contiguous blocks where no trading dates were skipped.
- **Policy Ratification**: Authorized `APPROVED_EQ_ONLY_POLICY` as the primary production policy. Quarantined `QUARANTINED_UNAPPROVED_PERMISSIVE_BE_POLICY`.
- **Script Hardening**: Added automatic `sys.path` injection in `verify_historical_snapshot.py` for direct standalone execution.

### Phase 1C: Feature & Technical Indicator Foundation (Completed)
- **Pure Mathematical Indicators** ([`src/signal_core/features/indicators.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/features/indicators.py)):
  * SMA, EMA, RSI (J. Welles Wilder smoothing), ATR (True Range + Wilder smoothing), Rolling High/Low, Donchian Channel, MACD.
  * Comparative Relative Strength (excess return vs benchmark across trailing lookback sessions).
  * Deterministic daily-to-weekly bar aggregation ([`WeeklyBar`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/features/indicators.py#L347)) and weekly trend indicator following ISO calendar weeks.
  * Exact `Decimal` precision enforced; strict rejection of binary floats, booleans, and non-finite values.
- **Subsegment Indicator Engine** ([`src/signal_core/features/engine.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/features/engine.py)):
  * Implemented [`SubsegmentIndicatorEngine`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/features/engine.py#L60) to bind indicator calculation strictly to contiguous subsegments from `PriceSeriesContinuityValidator`.
  * **Zero Cross-Gap Leakage**: Indicators warm up afresh after any missing session gap; state never spills across non-contiguous dates.
  * **Zero Silent Forward-Filling**: Missing calendar dates return `None`.
  * **Fail-Closed Verification**: Option to fail closed immediately on unexplained gaps.
- **Independent External Audit Remediation (DeepSeek Review)** ([`reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md)):
  * **F-01 (P1)**: Subsegment-bounded `compute_relative_strength`; post-gap RS values warm up afresh with zero cross-gap leakage.
  * **F-02 (P1)**: Enabled polymorphic handling of `ExchangeSessionObservation` in `compute_relative_strength`.
  * **F-03 (P1)**: Made subsegment partitioning fail-closed on off-calendar bars.
  * **F-04 (P2)**: Replaced output-length `assert` with explicit `IndicatorValidationError`.
  * **F-05 & F-06 (P2)**: Added weekly trend unit test suite and week-over-week ISO calendar continuity validation; duplicate daily dates fail closed.
  * **F-07 (P2)**: Detected and rejected duplicate trade dates in `PriceSeriesContinuityValidator`.
  * **F-08 (P2)**: Added golden parity regression test between clean and legacy `DATA-CTNT-V2` digests.
  * **F-09 (P2)**: Strict float and boolean rejection added to `load_dataset_from_dict`.
  * **F-11 (P3)**: Enriched `InstrumentTechnicalFeatures` with `raw_series_code`, `series_classification`, and `isin`.
  * **F-12 (P3)**: Optimized feature engine by partitioning subsegments and validating continuity once upfront per instrument.
  * **Section 5 / S-1..S-3**: Configured effective-dated historical NSE fee schedule in `go_no_go_criteria.yaml` and implemented typed contract loader [`criteria.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/criteria.py).
  * Comprehensive regression test suite expanded to **91 passing tests in 0.79s**; all 5 external audit probes pass 100%.

---

## 3. Current Repository Structure

```
Signal-Atlas-Core/
├── AGENTS.md                                # Non-negotiable quant research guidelines & Indian market rules
├── pyproject.toml                           # Package configuration (signal-core v0.1.0, pytest pythonpath)
├── README.md                                # Core principles & overview
├── WHAT_WE_ARE_BUILDING.md                  # Comprehensive architectural vision & market realities
├── CURRENT_STAGE_OF_WORK.md                 # Current progress, completed milestones & roadmap
├── configs/
│   └── go_no_go_criteria.yaml               # Committed quantitative thresholds & effective-dated fee schedule
├── scripts/
│   ├── reconcile_bhavcopy_series.py         # Reproducible Bhavcopy audit tool (strict explicit CLI root)
│   └── verify_historical_snapshot.py        # Snapshot loader & SHA-256 / canonical fingerprint verifier
├── reports/
│   ├── audit/
│   │   └── signal_atlas_phase1c_audit_deepseek_review_.md # Independent external audit report
│   └── reconciliation/
│       ├── bhavcopy_545_reconciliation.csv  # 545-record row-level audit trail
│       └── bhavcopy_series_policy_report.md # Policy report & empirical evidence
├── src/
│   └── signal_core/
│       ├── __init__.py
│       ├── contracts/
│       │   ├── __init__.py                  # Public domain exports
│       │   ├── criteria.py                  # Typed Go/No-Go criteria & effective-dated fee loader
│       │   ├── price_bar.py                 # Immutable Decimal OHLCV contract
│       │   ├── universe.py                  # Point-in-time UniverseSchedule & UniverseInterval
│       │   ├── provenance.py                # Cryptographic fingerprinting (DATA-CTNT-V2, UNIV-SCHED-V1)
│       │   ├── dataset.py                   # DatasetSnapshot & validation engine
│       │   ├── exchange_series.py           # Series enum, ExchangeSessionObservation, ContinuityValidator
│       │   └── legacy_compat.py             # Historical loader & legacy fingerprint adapter
│       ├── features/
│       │   ├── __init__.py                  # Public feature & indicator exports
│       │   ├── indicators.py                # Pure Decimal mathematical indicator formulas (EMA, ATR, RSI, etc.)
│       │   └── engine.py                    # SubsegmentIndicatorEngine & InstrumentTechnicalFeatures
│       └── loaders/
│           ├── __init__.py
│           └── historical_snapshot.py       # Snapshot parsing, diagnostics, duplicate rejection
└── tests/
    ├── fixtures/
    │   └── small_synthetic_dataset.json     # Synthetic test fixture
    └── unit/
        ├── test_price_bar.py                # OHLCV invariants, float rejection, decimal validation (10 tests)
        ├── test_universe.py                 # Universe schedules, date queries, immutability (9 tests)
        ├── test_provenance.py               # Golden vectors, determinism, dual digest parity (11 tests)
        ├── test_dataset.py                  # Snapshot construction, immutability, float rejection (11 tests)
        ├── test_historical_loader.py        # Snapshot parsing, diagnostics, duplicate rejection (11 tests)
        ├── test_bhavcopy_reconciliation.py  # Series preservation, continuity, subsegments, Cases 1-4 (14 tests)
        ├── test_indicators.py               # Indicators, subsegment isolation, audit probes (22 tests)
        └── test_criteria.py                 # Go/No-Go criteria & effective-dated fee resolution (3 tests)
                                             # Total: 91 passing unit tests in 0.79s
```
    └── unit/
        ├── test_price_bar.py                # OHLCV invariants, float rejection, decimal validation (10 tests)
        ├── test_universe.py                 # Universe schedules, date queries, immutability (9 tests)
        ├── test_provenance.py               # Golden vectors, determinism, delimiter rejection (10 tests)
        ├── test_dataset.py                  # Snapshot construction, immutability, date ranges (10 tests)
        ├── test_historical_loader.py        # Snapshot parsing, diagnostics, duplicate rejection (11 tests)
        ├── test_bhavcopy_reconciliation.py  # Series preservation, continuity, subsegments, Cases 1-4 (14 tests)
        └── test_indicators.py               # Pure math indicators, zero lookahead, subsegment isolation (15 tests)
                                             # Total: 79 passing unit tests in 0.69s
```

---

## 4. Phased Rebuild Roadmap & Next Steps

```
[Phase 1A: Core Contracts] ──► [Phase 1B: Data Integrity & Bhavcopy Audit]  (COMPLETED)
                                          │
                                          ▼
                         [Phase 1C: Feature & Indicator Engine]            (COMPLETED)
                                          │
                                          ▼
                         [Phase 1D: Indian Execution & Cost Model]         (NEXT IMMEDIATE TASK)
                                          │
                                          ▼
                         [Phase 1E: Exact Decimal Portfolio Ledger]
                                          │
                                          ▼
                         [Phase 2: Strategy Validation & Walk-Forward]
```

### Phase 1D: Statutory Indian Cost Engine & Execution Fill Simulator (Next Immediate Task)
- **Indian Statutory Transaction Cost Engine**:
  * Securities Transaction Tax (STT): 0.1% delivery buy/sell, 0.025% intraday sell.
  * NSE cash equity turnover charges (~0.00325%).
  * SEBI turnover fee (₹10 per crore = 0.0001%).
  * Indian Stamp Duty (0.015% delivery buy, 0.003% intraday buy).
  * Goods & Services Tax (GST): 18% on (brokerage + exchange charges + SEBI charges).
  * Investor Protection Fund Trust (IPFT) charges.
  * Brokerage: Fixed ₹20/order or basis points.
- **Execution Fill Simulator**:
  * Next-session execution ($T+1$ open or $T+1$ TWAP).
  * Circuit filter fill restrictions: Prohibit BUY fill at Upper Circuit (ask depth = 0); prohibit SELL fill at Lower Circuit (bid depth = 0).
  * Liquidity & Slippage model: Non-linear impact parameterized by Average Daily Turnover (ADT) and bid-ask spread.
  * Volume participation cap: Order size capped at 2.5% to 5.0% of session's traded volume (`TOTTRDQTY`).

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting
- Implement exact `Decimal` cash ledger, mark-to-market equity tracker, gross/net PnL accounting, and position tracking.
- Strict rejection of binary floating-point numbers.

### Phase 2: Walk-Forward Strategy Engine & Deflated Sharpe Evaluation
- Multi-hypothesis trial registry logging every sweep.
- Walk-forward parameter stability evaluation across market regimes.
- Automated generation of computed verdicts (PASS/FAIL) against committed `configs/go_no_go_criteria.yaml`.
- Computation of Deflated Sharpe Ratio (DSR) and Haircut Sharpe ratio.
