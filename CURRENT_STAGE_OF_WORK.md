# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 1E In Audit Remediation** — §13 Audit Findings (I-1 through I-7) fully remediated; awaiting re-audit verdict |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, series continuity, pure subsegment feature engine, typed criteria loader, statutory Indian cost engine, non-linear slippage model, authoritative execution simulator, exact Decimal cash book, multi-fill position accounting, mark-to-market portfolio valuation, and committed risk tracker complete |
| **Offline Test Suite** | **126 passed in 0.89s** (100% pass rate, zero warnings) |
| **External Dependencies** | Zero live database connections, zero external network calls, zero shadow simulators |
| **Historical Provenance** | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` (Strictly maintained, zero false promotions) |
| **Holdout Containment** | `HOLDOUT_UNLOCK` is strictly **ABSENT**; out-of-sample data remains completely sealed |
| **Authoritative Criteria** | Committed in [`configs/go_no_go_criteria.yaml`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/configs/go_no_go_criteria.yaml), typed loader in [`criteria.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/criteria.py) (DSR, Haircut Sharpe, Max Drawdown, Effective-Dated Indian Statutory Cost Schedule) |
| **Approved Strategy Policy** | [`APPROVED_EQ_ONLY_POLICY`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L141) (Strict rolling cash equity; Trade-to-Trade `BE` excluded from trade entry) |
| **Single Execution Engine** | [`ExecutionFillSimulator`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/simulator.py) & [`TransactionCostModel`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/costs.py) (Shared identical engine across backtest and simulation) |
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
  * **Independent Re-Audit Outcome (§10)**: 10 findings closed, 1 mitigated (F-08 dual-engine test parity), 1 partial (F-06/R-1 intra-week calendar gap), 1 open (F-10/R-2 scale-sensitive byte-identity fingerprint). Residuals documented: R-1 (to be closed before strategy-level weekly consumption), R-2 (byte-identity semantics), R-4 (pre-Oct-2024 slab flattening disclosed in cost engine). Conditional GO approved for Phase 1D.
  * Comprehensive regression test suite verified at **91 passing tests in 0.46s** (100% pass rate, zero warnings).

### Phase 1D: Statutory Indian Cost Engine & Execution Fill Simulator (Completed)
- **Indian Statutory Transaction Cost Engine** ([`src/signal_core/execution/costs.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/costs.py)):
  * Implemented [`TransactionCostModel`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/costs.py) consuming authoritative criteria from committed `configs/go_no_go_criteria.yaml`.
  * Computes exact `Decimal` statutory levies for cash equities:
    - Securities Transaction Tax (STT): Delivery (0.1% on buy and sell), Intraday (0.025% on sell, 0% on buy).
    - Exchange Turnover Charges: Date-aware resolution across historical circulars (`NSE/FA/46730`, `NSE/FA/56129`, `NSE/FA/61137`, `NSE/FA/64323`, `NSE/FA/73061`).
    - Investor Protection Fund Trust (IPFT): Effective-dated rate resolution (e.g. ₹0.01/cr vs ₹10/cr).
    - SEBI Turnover Fees: Exact ₹10 per crore (0.0001%).
    - Indian Stamp Duty: Levied strictly on buyer legs (0.015% delivery buy, 0.003% intraday buy, ₹0 on sell).
    - Goods & Services Tax (GST): 18% applied on taxable base (brokerage + exchange charges + SEBI charges + IPFT).
    - Brokerage: Configurable flat fee (default ₹20/order) or basis points.
  * Emits [`TransactionCostBreakdown`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/costs.py) with net cash impact and basis points.
  * Honors Audit Condition 2 & Residual R-4: Automatically attaches slab flattening disclosure to all trades before Oct 1, 2024.
  * **Paise Rounding Policy at Boundary (E-6 Remediated)**: Provides `.to_paise()` and `round_to_paise=True` on `TransactionCostModel` to quantize all currency fields to 2 decimal places (`0.01` INR, `ROUND_HALF_UP`) for contract note and ledger reconciliation.
- **Non-Linear Slippage & Liquidity Impact Model** ([`src/signal_core/execution/slippage.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/slippage.py)):
  * Implemented [`SlippageModel`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/slippage.py) enforcing the square-root market impact law:
    $$\text{Slippage} \ge \frac{\text{Spread}}{2} + \kappa \cdot \left(\frac{\text{Order Value}}{\text{ADT}}\right)^\alpha$$
  * Evaluated using exact `Decimal.sqrt()` arithmetic; adverse price slippage upwards on BUY and downwards on SELL, clamped to session High/Low.
  * **Pure Decimal Exponentiation (E-5 Remediated)**: Removed binary float conversions from non-default alpha paths; evaluated entirely in standard library Decimal arithmetic.
- **Single Authoritative Execution Fill Simulator** ([`src/signal_core/execution/simulator.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/execution/simulator.py)):
  * **Calendar Latency Measurement & Lookahead Gate (E-3 Remediated)**:
    - Measures elapsed trading sessions between `signal_date` and `target_date` using the trading calendar (or business days).
    - Emits `FillStatus.REJECTED_LOOKAHEAD` when `target_date <= signal_date`.
    - Enforces `min_execution_latency_sessions` against measured latency (rejects T+1 when latency=2 is configured; records `latency_sessions` on every `ExecutionFillResult`).
  * **Fail-Closed Series Evidence Gate (E-2 Remediated)**:
    - Rejects bare `PriceBar` entry orders without explicit series evidence (`FillStatus.REJECTED_INELIGIBLE_SERIES`). Banned silent coercion to `EQ`.
    - Enforces [`SeriesEligibilityPolicy`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py): Rejects trade entry in `BE` instruments under [`APPROVED_EQ_ONLY_POLICY`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L141).
  * **Circuit Freeze Invariants Without Lookahead (E-1 Remediated)**:
    - Added `upper_circuit_limit` and `lower_circuit_limit` directly to [`ExchangeSessionObservation`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py#L172).
    - Freeze gate is evaluated strictly on the **fill reference price** (e.g. Open), eliminating lookahead leakage from end-of-day High/Low. Legal open fills proceed even if session High touches circuit later in the day.
    - Rejects BUY when Open is at/through Upper Circuit, or on whole-day locked bars (`high == low`).
    - Rejects SELL/stop when Open is at/through Lower Circuit, or on whole-day locked bars.
  * **Minimum Daily Turnover Gate (E-4 Remediated)**:
    - Enforces `min_daily_turnover_crore` (₹5.0 Crore) threshold from criteria; illiquid scrips fail closed with `FillStatus.REJECTED_INSUFFICIENT_TURNOVER`.
  * **Volume Participation Cap (Rule 7.3)**: Caps order fills at 3.0% of session volume (`TOTTRDQTY`); rejects zero-liquidity sessions or fills partially when authorized.
  * **Price & Gap Realism**: Stop-loss gap-down fills at session Open (not stop price) minus slippage.
- **Audit Hardening & Zero-Assertion Invariant**:
  * Remediated residual R-3: Replaced all `assert` statements across `indicators.py` and `execution/` with explicit domain validation exceptions (`IndicatorValidationError`, `ExecutionOrderValidationError`).
  * Unit test suite expanded to **108 tests**; 100% passing in 0.60s.

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting (Remediated per §13 Audit)
- **Authoritative Cash Book & Ledger** ([`src/signal_core/portfolio/ledger.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/ledger.py)):
  * Implemented [`CashLedger`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/ledger.py) tracking capital deposits, withdrawals, trade outflows (BUY), and trade inflows (SELL) as a single-entry cash journal with external position tracking (I-6).
  * **Paise Quantization at Boundary (E-6 & Rule 6.4)**: Quantizes all monetary cash flow amounts and running balances to exact paise (`0.01` INR, `ROUND_HALF_UP`) matching official Indian contract note conventions.
  * **Fail-Closed Overdraft Protection**: Prohibits negative cash balances unless explicitly authorized (`allow_overdraft=True`).
  * **Posting Idempotency & Unique Reference Enforcement (I-2)**: Enforces unique `reference_id` across all ledger entries; replaying or double-posting a fill fails closed with `LedgerValidationError`.
  * **Chronological Date Monotonicity (I-5)**: Prohibits posting back-dated entries (`trade_date < last_date`), maintaining strict sequential audit order.
  * **Circuit Evidence Provenance Tracking (Audit Condition 2)**: Automatically records `circuit_evidence_present` status on every ledger entry and tags unverified fills with `UNVERIFIED_CIRCUIT_EVIDENCE` warning metadata.
  * **Atomic Rollback Support**: Exposes `_rollback_last_entry()` ensuring failed multi-leg portfolio updates never leave orphaned cash movements behind.
- **Multi-Fill Position Accounting** ([`src/signal_core/portfolio/position.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/position.py)):
  * Implemented [`Position`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/position.py) tracking weighted average entry price, total cost basis, and cumulative charges paid.
  * **Prohibition of Naked Short Delivery (I-1)**: Pre-validates held quantity against sell volume, strictly preventing selling more shares than held under cash equity delivery settlement (`OrderProduct.DELIVERY` / CNC).
  * **Drift-Free Proportional Cost Basis Allocation (I-7)**: Derives partial-sale cost basis directly and proportionally from `total_cost_basis`, completely eliminating sub-paise basis drift across lots and ensuring exact `0.00` residual basis on full liquidation.
  * **Full Lifecycle Exact Reconciliation**: Mathematically verified invariant across multi-fill orders:
    $$\Delta \text{Cash} = \text{Final Cash} - \text{Initial Cash} \equiv \sum \text{Realized Net PnL}$$
- **Portfolio Mark-to-Market Valuation & Risk Tracker** ([`src/signal_core/portfolio/portfolio.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/portfolio.py)):
  * Implemented [`Portfolio`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/portfolio.py) coordinating the cash ledger, active positions, and committed Go/No-Go criteria.
  * **Atomic Fill Processing (I-1)**: Validates short delivery, capital outlay limits, and idempotency *before* touching the cash ledger; automatically rolls back cash if position update fails.
  * **Concentration Limit on Total Capital Deployed (I-3)**: Evaluates `max_single_position_weight = 0.10` on total cash deployed (gross trade value + statutory transaction charges), eliminating under-enforcement by transaction costs.
  * **Exact Decimal Drawdown Comparison (I-4)**: Computes and evaluates drawdown using unrounded exact Decimal precision, preventing real threshold breaches (e.g. `0.25001`) from being rounded away by premature quantization.
  * Comprehensive test suite in [`test_portfolio.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_portfolio.py) expanded to **17 tests**, bringing total repo test count to **126 passed in 0.89s**.

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
│       ├── execution/
│       │   ├── __init__.py                  # Public execution domain exports
│       │   ├── types.py                     # ExecutionOrder, OrderSide, OrderProduct, FillStatus
│       │   ├── costs.py                     # TransactionCostModel & TransactionCostBreakdown
│       │   ├── slippage.py                  # SlippageModel & SlippageResult (non-linear impact)
│       │   └── simulator.py                 # Single authoritative ExecutionFillSimulator
│       ├── portfolio/
│       │   ├── __init__.py                  # Public portfolio domain exports
│       │   ├── types.py                     # CashEntryType, CashLedgerEntry, PositionSnapshot, PortfolioSnapshot
│       │   ├── ledger.py                    # Double-entry CashLedger with paise quantization & overdraft protection
│       │   ├── position.py                  # Multi-fill Position accounting with fee allocation & short delivery ban
│       │   └── portfolio.py                 # Portfolio mark-to-market valuation, drawdown & risk limit tracker
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
        ├── test_criteria.py                 # Go/No-Go criteria & effective-dated fee resolution (3 tests)
        ├── test_costs.py                    # Statutory Indian cost engine, circulars, GST base, paise rounding (6 tests)
        ├── test_execution_simulator.py      # Next-session invariant, circuits, volume cap, slippage, latency (11 tests)
        └── test_portfolio.py                # Exact Decimal cash ledger, positions, MTM, drawdown, risk caps (17 tests)
                                             # Total: 126 passing unit tests in 0.89s
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
                         [Phase 1D: Indian Execution & Cost Model]         (COMPLETED)
                                          │
                                          ▼
                         [Phase 1E: Exact Decimal Portfolio Ledger]        (IN AUDIT REMEDIATION)
                                          │
                                          ▼
                         [Phase 2: Strategy Validation & Walk-Forward]
```

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting (In Audit Remediation)
- Remediated §13 findings: fill posting atomicity (I-1), posting idempotency (I-2), full capital outlay concentration check (I-3), exact Decimal drawdown comparison (I-4), date monotonicity (I-5), accurate documentation nomenclature (I-6), and drift-free proportional cost basis allocation (I-7). Awaiting re-audit verdict.

### Phase 2: Walk-Forward Strategy Engine & Deflated Sharpe Evaluation (Next Phase)
- Multi-hypothesis trial registry logging every sweep.
- Walk-forward parameter stability evaluation across market regimes.
- Automated generation of computed verdicts (PASS/FAIL) against committed `configs/go_no_go_criteria.yaml`.
- Computation of Deflated Sharpe Ratio (DSR) and Haircut Sharpe ratio.
