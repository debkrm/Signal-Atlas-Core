# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 2B signed off** (§22) · **Phase 2B.5 signed off — GO** (§24) · **Phase 2C implemented — NOT SIGNED OFF** (§25: G-1, G-2/G-3, G-4, G-5) · **Wave 0 — NOT ACCEPTED AS COMPLETE** (§27: G-1 **PARTIALLY CLOSED** — role guard enforced but the default no-spec path is fail-open; ingest schemas frozen in code but corporate-action ratio direction unpinned and the physical holdout seal is documented only) · **Next** — §27 items H-1, H-2/H-6, H-5, H-4, H-3, then Wave 1 real-data slice restricted to pre-2025 dates until H-2 lands |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, series continuity, pure subsegment feature engine, typed criteria loader, statutory Indian cost engine, non-linear slippage model, authoritative execution simulator, exact Decimal cash book, multi-fill position accounting, mark-to-market portfolio valuation, committed risk tracker, holdout containment, tamper-evident trial registry, statistical significance engine, strategy contract, walk-forward engine, frozen ingest schemas, and a holdout containment guard whose default path is still fail-open (§27) |
| **Offline Test Suite** | **219 passed in 6.49s** (100% pass rate, zero warnings) |
| **External Dependencies** | Zero network calls, zero shadow simulators. Research storage is planned as embedded Parquet + DuckDB in an optional extra (no server process); the core package stays stdlib-pure. |
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

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting (Completed & Verified per §13–§16 Audits)
- **Authoritative Cash Book & Ledger** ([`src/signal_core/portfolio/ledger.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/ledger.py)):
  * Implemented [`CashLedger`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/ledger.py) tracking capital deposits, withdrawals, trade outflows (BUY), and trade inflows (SELL) as a single-entry cash journal with external position tracking (I-6, N-11).
  * **Paise Quantization at Boundary (E-6 & Rule 6.4)**: Quantizes all monetary cash flow amounts and running balances to exact paise (`0.01` INR, `ROUND_HALF_UP`) matching official Indian contract note conventions.
  * **Fail-Closed Overdraft Protection**: Prohibits negative cash balances unless explicitly authorized (`allow_overdraft=True`).
  * **Posting Idempotency & Deterministic Sequence Commit (I-2, R-1 & N-2)**: Sequence references (`FILL_{inst}_{date}#{n}`) are committed inside `_post_entry` strictly *after* pre-validations (date monotonicity, reference uniqueness, overdraft) succeed. Rejections leave zero sequence holes, ensuring run-to-run determinism.
  * **Generated Reference Uniqueness Guard (N-8 & Gate G8 PASS)**: Enforces `candidate_ref not in self._posted_reference_ids` on the generated sequence branch, strictly preventing collision between generated references and explicit caller references.
  * **Zero Observable State Change on Rejection (N-10 & Gate G2 PASS)**: Lazy re-anchoring of opening deposit (`entries[0]`) is committed only after all transaction validations succeed; rejected orders leave zero deposit or cursor mutations.
  * **Rollback Sequence Recovery Without String Parsing (N-5)**: Tracks sequence keys in `_seq_keys_history` stack; `_rollback_last_entry()` decrements counters directly without parsing reference strings.
  * **Strict Identifier Validation (N-4)**: Fails closed on empty, whitespace, unstripped, boolean, or non-string `reference_id`, `fill_id`, and `order_id`.
  * **Chronological Date Monotonicity & Lazy Deposit Anchoring (I-5 & R-4)**: When `initial_date` is omitted, the `INIT_DEPOSIT` date anchors dynamically to the first transaction session date, preventing false historical rejection without silent forward-dating.
  * **Circuit Evidence Provenance Tracking (Audit Condition 2)**: Automatically records `circuit_evidence_present` status on every ledger entry and tags unverified fills with `UNVERIFIED_CIRCUIT_EVIDENCE` warning metadata.
  * **Atomic Rollback Support**: Exposes `_rollback_last_entry()` ensuring failed multi-leg portfolio updates never leave orphaned cash movements behind.
- **Multi-Fill Position Accounting** ([`src/signal_core/portfolio/position.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/position.py)):
  * Implemented [`Position`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/position.py) tracking weighted average entry price, total cost basis, and cumulative charges paid.
  * **Prohibition of Naked Short Delivery (I-1)**: Pre-validates held quantity against sell volume, strictly preventing selling more shares than held under cash equity delivery settlement (`OrderProduct.DELIVERY` / CNC).
  * **Gross Reconciliation Pre-Validation (R-2)**: Asserts that `fill.costs.gross_amount == filled_quantity × executed_price` at paise precision and `executed_price > 0` before modifying ledger or position state.
  * **Drift-Free Proportional Cost Basis Allocation (I-7 & N-6)**: Derives partial-sale cost basis directly and proportionally from `total_cost_basis`, completely eliminating sub-paise basis drift across lots and ensuring exact `0.00` residual basis on full liquidation for paise-representable prices.
  * **Full Lifecycle Exact Reconciliation**: Mathematically verified invariant across multi-fill orders:
    $$\Delta \text{Cash} = \text{Final Cash} - \text{Initial Cash} \equiv \sum \text{Realized Net PnL}$$
- **Portfolio Mark-to-Market Valuation & Risk Tracker** ([`src/signal_core/portfolio/portfolio.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/portfolio.py)):
  * Implemented [`Portfolio`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/portfolio/portfolio.py) coordinating the cash ledger, active positions, and committed Go/No-Go criteria.
  * **O(1) Bounded Replay Guard (N-1, N-9, N-13 & R-5)**: Pins recent in-memory `ExecutionFillResult` instances in an `OrderedDict[int, ExecutionFillResult]` (bounded to `_max_pinned_instances = 10000`). Lookups are strictly $O(1)$ (~56–95 µs flat per fill), preventing GC address reuse while eliminating $O(n^2)$ time explosion and unbounded memory retention. Hardened regression test enforces scaling ratio `< 2.5` between 1k and 4k fills. Fills bearing `fill_id` or `reference_id` are protected indefinitely via ledger reference uniqueness.
  * **Multi-Session Partial Fill Identity (N-3)**: Composes fill identity as `FILL_{order_id}_{trade_date}#{count}` in `ExecutionFillSimulator`, allowing orders executed across multiple sessions or partial fills to post cleanly without reference collision.
  * **Atomic Fill Processing & Phantom Position Cleanup (I-1 & R-3)**: Validates short delivery, gross reconciliation, capital outlay limits, and idempotency *before* touching the cash ledger; automatically rolls back cash and purges empty newly-created positions if position updates fail.
  * **Concentration Limit on Total Capital Deployed (I-3)**: Evaluates `max_single_position_weight = 0.10` on total cash deployed (gross trade value + statutory transaction charges), eliminating under-enforcement by transaction costs.
  * **Exact Decimal Drawdown Comparison (I-4)**: Computes and evaluates drawdown using unrounded exact Decimal precision, preventing real threshold breaches (e.g. `0.25001`) from being rounded away by premature quantization.
  * Comprehensive test suite in [`test_portfolio.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_portfolio.py) expanded to **29 tests**, bringing total repo test count to **138 passed in 1.45s**.

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
│   ├── verify_historical_snapshot.py        # Snapshot loader & SHA-256 / canonical fingerprint verifier
│   ├── verify_phase2a_containment_and_trials.py # Phase 2A containment & trial registry verification probe
│   └── verify_phase2b_significance.py       # Phase 2B statistical significance engine verification probe
├── probe_b7bd8ba.py                         # Phase 1E independent audit probe
├── probe_phase2a.py                         # Phase 2A independent audit probe
├── probe_phase2b.py                         # Phase 2B independent audit probe
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
│       │   ├── ledger.py                    # Single-entry CashLedger with paise quantization & overdraft protection
│       │   ├── position.py                  # Multi-fill Position accounting with fee allocation & short delivery ban
│       │   └── portfolio.py                 # Portfolio mark-to-market valuation, drawdown & risk limit tracker
│       ├── research/
│       │   ├── __init__.py                  # Public research, containment & significance exports
│       │   ├── containment.py               # PartitionSpec, holdout sealing, human unlock verifier, walk-forward folds
│       │   ├── trials.py                    # Append-only tamper-evident TrialRegistry with SHA-256 hash chaining
│       │   └── significance.py              # DSR (Bailey & Lopez de Prado) & Haircut Sharpe (Harvey & Liu) with SIG-FLOAT-BOUNDARY
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
        ├── test_portfolio.py                # Exact Decimal cash ledger, positions, MTM, drawdown, risk caps, R-1..R-7, N-1..N-13 (29 tests)
        ├── test_containment.py              # Sealed holdout access, human unlock verification, fold generation (10 tests)
        ├── test_trials.py                   # Append-only hash chain, manifest anchor, tamper detection, variance (18 tests)
        └── test_significance.py             # DSR golden vector, decay, bit-for-bit, haircut, SIG-FLOAT-BOUNDARY, D-1..D-5 (18 tests)
                                             # Total: 184 passing unit tests in 1.82s
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
                         [Phase 1E: Exact Decimal Portfolio Ledger]        (COMPLETED & VERIFIED)
                                          │
                                          ▼
                         [Phase 2: Strategy Validation & Walk-Forward]     (ACTIVE PHASE)
                                          │
                                          ▼
 [2A: Containment + Trial Registry] ──► [2B: Significance (DSR/Haircut)]
          (COMPLETED)                             (COMPLETED)
                                          │
                                          ▼
 [2B.5: Ingestion & Immutable Data Layer]           (NEXT SLICE)
                                          │
                                          ▼
 [2C: Strategy + Walk-Forward Engine] ──► [2D: Computed Verdict Engine]
```

### Phase 1E: Exact Decimal Portfolio Ledger & Accounting (Completed & Verified)
- Remediated §13 findings: fill posting atomicity (I-1), posting idempotency (I-2), full capital outlay concentration check (I-3), exact Decimal drawdown comparison (I-4), date monotonicity (I-5), single-entry cash journal nomenclature (I-6), and drift-free proportional cost basis allocation (I-7).
- Remediated §14 findings: multi-fill sequence references and stable fill identity (R-1), cash outlay vs gross reconciliation pre-validation (R-2), rollback phantom position cleanup (R-3), lazy deposit date anchoring for historical backtests (R-4), GC-safe fill instance tracking (R-5), removal of `# type: ignore` suppressions (R-6), and comprehensive multi-fill / reference test suite (R-7).
- Remediated §15 findings: O(1) bounded replay guard via `OrderedDict` (N-1), deterministic sequence counters incrementing only on committed fills (N-2), composed fill IDs for multi-session partial fills (N-3), fail-closed string validation for `order_id`/`fill_id`/`reference_id` (N-4), and direct sequence key rollback without string parsing (N-5).
- Remediated §16 findings: generated reference uniqueness pre-check against `_posted_reference_ids` (N-8, Gate G8 PASS), documented 10k-fill identity window (N-9), lazy deposit re-anchoring deferred until post-validation (N-10, Gate G2 PASS), eliminated remaining "double-entry" comments (N-11), reproducible `probe_b7bd8ba.py` (N-12), and hardened ratio regression test in `test_n1` (N-13).

### Phase 2: Walk-Forward Strategy Engine & Deflated Sharpe Evaluation (Active Phase — 4 Slices)

**Sequencing principle.** Containment and trial accounting exist *before* the first strategy can run, so that no result can be produced outside a sealed partition or outside the registry. Only then do statistics (2B), simulation (2C) and verdicts (2D). Each slice ships with its own gates; a slice is not closed until its gates are measured, not asserted.

**Carried blockers (unchanged, and they constrain 2C):**

| Residual | Effect on Phase 2 |
|---|---|
| **E-1-R** — no verified circuit-band data source | Fills carry `UNVERIFIED_CIRCUIT_EVIDENCE`; 2C PnL is conditional and may not be used to justify a Phase 2 GO. |
| **R-1** — weekly aggregation tolerates an intra-week missing session | Weekly trend must not feed a 2C strategy until path-aware weekly aggregation lands; daily features only. |
| **R-2 / N-9** | No Phase 2 impact; carried forward unchanged. |

---

#### Phase 2A — Holdout Containment & Multi-Hypothesis Trial Registry (Completed & Remediated per §18 & §19 Audits)
Modules: [`src/signal_core/research/containment.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/research/containment.py), [`src/signal_core/research/trials.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/research/trials.py).
Authoritative committed probe: [`scripts/verify_phase2a_containment_and_trials.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/verify_phase2a_containment_and_trials.py) (and root runner [`probe_phase2a.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/probe_phase2a.py)).

- **Audit §18 & §19 Remediations (A-1 through A-18, B-1 through B-4)**:
  * **Mandatory Cryptographic Token Binding (A-1)**: `PartitionSpec` requires a 64-character hex `holdout_token_hash` bound into its cryptographic fingerprint (`PART-SPEC-V1-`). `verify_holdout_unlock` requires `expected_token_hash` (no `None` default); sentinel files with arbitrary content (e.g. `banana`) fail closed (`HoldoutSealedError`).
  * **Strict Role Normalization & Enum Validation (A-2)**: Partition roles are normalized (`.strip().upper()`) and validated against `PartitionRole` enum; bypass attempts such as `"holdout "` fail closed.
  * **Single Containment Authority (A-3)**: Removed `allow_holdout: bool` flag. Holdout registration routes exclusively through `check_partition_access(spec, PartitionRole.HOLDOUT, unlock_path)`.
  * **Mandatory External Head Manifest Anchor (A-4 & B-1)**: Maintains `<registry_file>.manifest` recording `total_trials`, `head_hash`, and `last_trial_id`. Non-empty registries missing their manifest fail closed (`Missing authoritative manifest anchor`). Un-ignored `*.manifest` in `.gitignore` so registries and anchors remain committed together.
  * **Committed Reproducible Verification Probe (A-5)**: Replaced hand-typed status claims with executable verification script `scripts/verify_phase2a_containment_and_trials.py` computing all gate verdicts via boolean accumulator.
  * **Authoritative Observation Accessor (A-6)**: Implemented `filter_partition_observations` enforcing containment before observation streams can reach feature or evaluation logic. (Note: unwired to external feature logic until Phase 2C strategy engine).
  * **On-Disk Tail Verification & Concurrent Guard (A-7)**: `append_trial` verifies on-disk record count and head hash before appending, rejecting desynchronized concurrent writes fail-closed.
  * **Calendar-Backed Embargo Validation (A-8 & A-10)**: `WalkForwardFold` validates that calendar date separation `(test_start - train_end).days - 1` strictly accommodates `embargo_sessions`.
  * **Unconditional Fail-Closed Integrity & Non-Mutating Verification (A-9 & B-2)**: Removed `auto_verify=False` toggle. `verify_integrity` validates into local collections before assignment; failed verification leaves in-memory state and trial count unmutated.
  * **Pinned DSR $N$ Configuration in Criteria (A-11 & B-6)**: Pinned `dsr_trial_count_basis` (`TOTAL_ATTEMPTED_TRIALS`) and `dsr_sharpe_variance_divisor` (`EVALUATED_TRIALS_MINUS_ONE`) directly in committed `configs/go_no_go_criteria.yaml` and loaded into typed `GoNoGoCriteria`.
  * **Cross-Platform POSIX LF Byte-Identity (A-12)**: Registry and manifest append operations use `newline="\n"`, ensuring zero CRLF byte distortion on Windows (`CRLF=0`).
  * **Finite Decimal Validation (A-13)**: Non-finite Decimals (`NaN`, `Infinity`) in records are rejected fail-closed.
  * **Typed Error Handling on Corrupt JSON (A-14)**: Malformed JSON records raise `RegistryTamperedError` instead of leaking untyped `KeyError`.
  * **Canonical Parameter Parity (A-15)**: Pre-canonicalizes parameters in memory to ensure bit-for-bit parity between in-memory records and reloaded records.
  * **Calendar Session Validation (A-16)**: `generate_walk_forward_folds` validates calendar session monotonicity, exact date types, and rejects duplicates.
  * **Anchored Mode Calibration (A-17)**: Fixed `min_required` calculation in anchored mode so expanding-window folds do not over-reject.
  * **Chronological Monotonicity Enforcement (A-18)**: Validates ISO-8601 UTC timestamps and enforces non-decreasing chronological monotonicity across trials.
  * **Atomic Manifest Replacement with Fsync (B-3)**: Manifest writes use a unique temporary sibling file with `flush()` and `os.fsync()`, atomically replaced via `os.replace()`.
  * **Strict Boolean Coercion Prohibition (B-4)**: Explicitly rejects boolean instances passed to `observation_count`, `returns_digest`, `seq`, or string fields.

- **Phase 2A Computed Gate Verdicts (measured via `scripts/verify_phase2a_containment_and_trials.py`)**:

| Gate | Status | Computed Measurement Basis |
|---|---|---|
| **G2A-1** · Sealed holdout read raises | **PASS** | `check_partition_access` and `filter_partition_observations` fail closed with `HoldoutSealedError` without valid sentinel; arbitrary content (`banana`) and string casing/whitespace bypasses (`"holdout "`) fail closed (A-1, A-2, A-3, A-6). Token authority rests in human-authored `PartitionSpec` (B-7); accessor unwired to external feature logic until Phase 2C strategy engine. |
| **G2A-2** · Folds deterministic, disjoint, calendar-validated | **PASS** | `compute_fold_spec_fingerprint` is deterministic (`FOLD-SPEC-V1-c64ed6...`); test windows are strictly disjoint; declarative embargoes unbacked by calendar gap fail closed; calendar duplicates/disorder rejected; anchored mode produces valid folds without over-rejection (A-8, A-10, A-16, A-17). |
| **G2A-3** · Shuffled parameter sweep reproducible & byte-identical | **NOT RUN (Sweep) / PASS (Hashing & LF)** | Canonical record hashing is key-order invariant; POSIX LF strictly enforced across platforms with CRLF=0, LF=7 on test append (A-12). Full strategy parameter grid sweep execution is unmeasured in 2A and deferred to Phase 2C strategy engine per B-6. |
| **G2A-4** · Cryptographic chain verifies & tampering/truncation fails closed | **PASS** | Hash chaining verified across consecutive records; missing manifest anchor rejected fail-closed (`RegistryTamperedError`) (B-1); truncation from 5 to 2 records detected via manifest anchor (`RegistryTamperedError`); failed verification preserves in-memory state (B-2); manifest written via atomic temp-file replace + fsync (B-3); concurrent appender desync rejected; missing trailing newline fails closed. |
| **G2A-5** · Schema ready for Phase 2B & DSR conventions pinned | **PASS** | All 9 statistical fields present; exact Decimal sample variance matches closed form (`0.0800`); boolean coercion rejected fail-closed (B-4); non-finite Decimals rejected; malformed JSON raises typed error; canonical params agree bit-for-bit on reload; timestamps strictly monotonic; $N=3$ vs $N_{eval}=2$ convention pinned in committed criteria config (A-11, A-13, A-14, A-15, A-18). |

#### Phase 2B — Statistical Significance Engine (Completed & Verified)
Module: [`src/signal_core/research/significance.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/research/significance.py).
Authoritative committed probe: [`scripts/verify_phase2b_significance.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/verify_phase2b_significance.py) (and root runner [`probe_phase2b.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/probe_phase2b.py)).

- **Exact Decimal Estimators**:
  * Pure Decimal implementations for `sample_mean`, `sample_variance`, `sample_std`, `sample_skewness`, and `sample_kurtosis`.
  * Kurtosis supports `RAW_NORMAL_THREE` (standard normal = 3.0) and `EXCESS_NORMAL_ZERO` (standard normal = 0.0), committed in criteria.
  * Annualized Sharpe ratio evaluated strictly in exact Decimal with annualization factor $\sqrt{sessions\_per\_year}$.
  * Zero tolerance for floats, booleans, or non-finite Decimals (`NaN`, `Infinity`); all fail closed with `InvalidSampleError`.
- **Deflated Sharpe Ratio (DSR)**:
  * Implemented per Bailey & López de Prado (2014) accounting for trial count $N$, variance $V$ across trials, track record length $T$, skewness, and kurtosis.
  * Expected maximum Sharpe under null ($SR^*$) evaluates to 0.0 when $N = 1$, reducing DSR smoothly to the single-trial Probabilistic Sharpe Ratio (PSR(0)).
  * Integrates with `TrialRegistry`: consumes `total_trial_count` as authoritative $N$ and `compute_trial_sharpe_variance` as $V$ per committed criteria conventions.
- **Haircut Sharpe Ratio**:
  * Implemented per Harvey & Liu (2015) under the Bonferroni multiple-testing adjustment ($p_{adj} = \min(1.0, N \cdot p)$).
  * Discount decreases monotonically to 0% at $N = 1$ ($SR_{haircut} = SR_{orig}$). When $p_{adj} \ge 1.0$, haircut is strictly 100% ($SR_{haircut} = 0.0$).
- **Strict Isolated Float Boundary (`SIG-FLOAT-BOUNDARY`)**:
  * Returns, moments, and final results remain exact `Decimal`. Floating-point operations are strictly isolated to standard normal CDF and quantile functions (`statistics.NormalDist`).
  * No float values ever leak outward into ledger, position, or execution simulator code (proven by AST inspection test).
- **Residual C-2 & Auditor Conditions**:
  * C-2 explicitly documented in `significance.py`: registry wiping is detected via version control (git diff / commit history); $N$ originates from committed registry.
  * Every result object (`DeflatedSharpeResult`, `HaircutSharpeResult`, `SignificanceReport`) is explicitly tagged with `trial_count_n`.
  * Methodology constants (`sessions_per_year: 250`, `kurtosis_convention: RAW_NORMAL_THREE`, `haircut_variant: BONFERRONI`) are committed in `configs/go_no_go_criteria.yaml` and loaded into `GoNoGoCriteria`.

- **Phase 2B Computed Gate Verdicts (measured via `scripts/verify_phase2b_significance.py`)**:

| Gate | Status | Computed Measurement Basis |
|---|---|---|
| **G2B-1** · DSR reproduces published worked examples within stated tolerance | **PASS** | Bailey & López de Prado (2014) Treasury seasonality setup ($N=100, V=0.50, T=1250, SR=2.50, \gamma_3=-3.0, \gamma_4=10.0, q=250$): computed DSR = `0.900397` (rounded: `0.9004`), matching published paper bit-for-bit at 4 decimal places; expected max $SR^* = 1.789406$. |
| **G2B-2** · DSR decays monotonically as N grows at fixed Sharpe | **PASS** | Evaluated at $SR=1.50, V=0.25, T=500$: $N=1 \to 0.982761$, $N=5 \to 0.898648$, $N=20 \to 0.780770$, $N=100 \to 0.629617$, $N=500 \to 0.485234$. Strictly decreasing across every step. |
| **G2B-3** · Identical inputs yield bit-for-bit identical Decimal output | **PASS** | Repeated calls across identical parameters produce bit-for-bit identical Decimal string representations and values for all fields (DSR: `0.975268`, Haircut SR: `1.225063`). |
| **G2B-4** · Haircut Sharpe decreases monotonically as N grows | **PASS** | Harvey & Liu (2015) Bonferroni haircut at $SR=2.00, T=1250$: $N=1 \to 2.000000$ (0.0% haircut), $N=5 \to 1.840276$ (8.0%), $N=20 \to 1.691856$ (15.4%), $N=100 \to 1.503433$ (24.8%), $N=1000 \to 1.190940$ (40.5%). Strictly decreasing Sharpe, strictly increasing haircut %. |
| **G2B-5** · Float boundary isolation (SIG-FLOAT-BOUNDARY) | **PASS** | All result attributes are exact `Decimal`, `int`, or `str` (zero float leakage); float inputs to moments fail closed with `InvalidSampleError`; AST inspection confirms `ledger`, `position`, and `portfolio` modules never import significance math. |
| **G2B-6** · Anti-overfitting guards & criteria alignment (D-1..D-5) | **PASS** | Zero variance and $N_{eval} < 2$ fail closed with `InvalidSampleError` when $N > 1$ (D-1, verified true $V=0.3367 \to 0.488273$ FAIL); non-positive Mertens variance term raises `SignificanceError` rather than substituting $10^{-6}$ (D-2); DSR invariant bit-for-bit across `RAW_NORMAL_THREE` and `EXCESS_NORMAL_ZERO` (D-3); loader and engine strictly agree on `EVALUATED_TRIALS_MINUS_ONE` (D-4); $N_{eval} > N$ rejected (D-5). |

#### Phase 2B.5 — Market Data Ingestion & Immutable Storage Layer (Signed off — audit §24, GO)

**Why here.** Phase 2C is the first engine whose correctness depends on a real point-in-time universe. Today `TrialRecord.dataset_fingerprint` has no authoritative artifact behind it, and the exchange calendar that `AGENTS.md` §6.3 requires does not exist in the repository. Building 2C against synthetic fixtures would encode assumptions that later have to be unlearned — the failure mode §18–§21 kept finding.

**Ingest window — decided: binding corpus from 2018-04-01, not 2022.**

| Tier | Window | Role | Constraint |
|---|---|---|---|
| **A · Binding** | 2018-04-01 → 2026-11-11 (≈2,130 sessions) | IS, validation, and the sealed holdout — the only window a GO verdict may be computed on | Requires GSM (effective 14 Mar 2017), ASM (effective 26 Mar 2018) and ESM histories for every session. If ESM cannot be sourced for 2018, the binding start moves to 2019-01-01 and that fact is recorded; it is not assumed away. |
| **B · Warm-up only** | 2015-01-01 → 2018-03-31 (≈790 sessions) | EMA/ATR warm-up, corporate-action ratio validation, ISIN-transition and delisting casework | No surveillance history exists for these sessions, so every metric computed here is `NOT RUN` for gating. |
| **C · Not now** | before 2015 | — | Bhavcopy is a different parser generation, index membership must be reconstructed from press releases, and the surveillance frameworks that constrain liquidity did not exist. Buys regimes that cannot be simulated faithfully. |

Partition roles inside Tier A: IS 2018-04 → 2023-12, validation 2024, **holdout sealed from 2025-01-01**. Sealing is done by a human-authored `PartitionSpec`; `HOLDOUT_UNLOCK` stays absent and is never agent-created.

**Why not 2022–2026.** 1,180 sessions is under five years. After a 200-session indicator warm-up, DSR works with T ≈ 980 — at N ≥ 50 that gate needs an annualized Sharpe above roughly 1.6 merely to clear 0.95, so it stops discriminating skill and starts rejecting everything. Four walk-forward folds cannot separate parameter stability from regime luck, and the sealed term would sit inside the same regime as the in-sample window.

**Structural breaks inside the window** — each needs its own dated handling; none may be averaged over: T+2 → phased T+1 (25 Feb 2022) → mandatory T+1 for all securities (27 Jan 2023); stamp duty centralised at 0.015% (Jul 2020); peak-margin regime (Sep 2021); bhavcopy schema migration to the `BhavCopy_NSE_CM_…` family (mid-2020) and to UDiFF (live 24 Jun 2024, legacy formats discontinued 5–8 Jul 2024).

**Storage decision.**
- **Parquet is the system of record; DuckDB is a disposable query engine over it.** The dataset is content-addressed, so a fingerprint identifies bytes rather than a mutable table. Deleting the `.duckdb` file must change no fingerprint.
- **Postgres is deferred to the paper-trading service**, where concurrent writers and row-level order/fill state are the actual requirement. That is OLTP, not research history.
- **`pyarrow` + `duckdb` go in an optional extra.** The ingest layer emits the existing `HistoricalDataset` contracts; nothing downstream imports DuckDB, and the core package stays stdlib-pure.
- **Three layers:** Bronze (byte-exact retrieved payloads + SHA-256), Silver (typed, calendar-checked, one append-only partition per session, gap-typed), Gold (derived: back-adjusted series, universe schedules, features). Corporate actions are an input table and adjustments are applied in Gold only, so "what was observable at $T$" stays recoverable.
- **Identity is ISIN.** Symbols are reused and reassigned; symbol and series are effective-dated attributes. Partition by exchange/year/month, never by symbol.
- **Time-varying facts are interval tables** joined as-of date $T$: index membership, ASM/GSM/ESM stage, F&O ban, price band.

**Ingest artifacts:** authoritative NSE trading calendar · ISIN-keyed security master · daily bhavcopy · corporate actions with verified ratios and ex-dates · index membership intervals · surveillance stage intervals · F&O ban intervals · one manifest and SHA-256 per retrieval.

**First slice (vertical, before any backfill):** calendar + security master + two symbols, end-to-end, fingerprinted.

**Remediation Summary (§23 Closure Set E-1 through E-6)**:
- **E-1 (Calendar modeled as sessions & provenanced)**: Rebuilt `configs/trading_calendar_nse.json` with 2,939 sessions containing `session_type` (FULL / MUHURAT / SPECIAL), exact open/close times, all 15 special/muhurat sessions (2020-02-01, 2025-02-01 Budget Saturdays; 2024-03-02, 2024-05-18 DR Saturdays; 12 Diwali Muhurat sessions), full provenance block with circular citations, and annual completeness assertions.
- **E-2 (Silver calendar validation & off-calendar rejection)**: `SilverStorage` validates partitions and records against the calendar; writing an off-calendar session raises `OffCalendarSessionError`; reading detects and fails closed if an off-calendar partition is on disk (zero silent bridging).
- **E-3 (Fail-closed snapshot generation)**: `GoldEngine.build_dataset_snapshot` runs with `fail_closed_on_missing=True` by default; raises `NonContiguousDatasetError` on any missing session/record; never mints a fingerprint over gapped series; removed `if v` silent universe shrinkage.
- **E-4 (Exact DECIMAL typing in DuckDB views)**: Prices, turnover, and quantities persist as `DECIMAL(18, 4)` and views expose explicit `DECIMAL(18, 4)` columns. Numeric predicates (`close >= 3000`) and aggregates (`avg(close)`) evaluate numerically and accurately.
- **E-5 (Fail-closed on corrupt partitions in view layer)**: `DuckDBViewLayer.register_views` fails closed with `DuckDBViewError` on partition corruption/truncation; empty-view fallback reserved strictly for zero existing files.
- **E-6 (Content-addressed Bronze with immutable restatements)**: Payloads stored content-addressed in `blobs/{sha256}.bin`; overwrite of existing path without `restatement_ref` fails closed with `BronzeStorageError`; restatements preserve prior blobs on disk; all historical versions remain fully verifiable.
- **E-8 & E-14 (Residual guards)**: Duplicate delisting and ISIN transition events raise `SecurityMasterError` fail-closed; gating eligibility check blocks `GO`, `APPROVED`, and `PASS` fail-closed on pre-2018 history.

**Phase 2B.5 Computed Gate Verdicts (measured via `scripts/verify_phase2b5_storage.py` and `probe_phase2b5.py`)**:

| Gate | Status | Computed Measurement Basis |
|---|---|---|
| **G2B.5-1** · Provenanced calendar completeness & content-addressed Bronze | **PASS** | Calendar verified (2,939 sessions, all 15 special/muhurat sessions present, annual counts match, provenance intact); Bronze overwrite without `restatement_ref` rejected fail-closed; restated payloads preserve original blobs; bit-flip and truncation fail closed with `TamperedBronzePayloadError`. |
| **G2B.5-2** · Rerun reproduces identical dataset & universe fingerprints | **PASS** | Rerun on identical data reproduces bit-for-bit identical fingerprints: dataset content `DATA-CTNT-V2-d09f4739df1f373590e9695a827d5a37` and universe schedule `UNIV-SCHED-V1-5b71356d8317e0285fc9610e038b1b41`. |
| **G2B.5-3** · ISIN transition & delisting exact effective date pruning | **PASS** | HDFC (`INE001A01036`) active on 2023-07-12, pruned on 2023-07-13 (`is_delisted=True`, excluded from universe); COCHINSHIP old (`INE704P01017`) active on 2024-01-09, transitioned out and pruned on 2024-01-10 with new ISIN (`INE704P01025`) active on 2024-01-10. |
| **G2B.5-4** · Off-calendar rejection, missing session gap & fail-closed snapshots | **PASS** | Writing off-calendar partition (Sunday) raises `OffCalendarSessionError`; missing calendar session (2024-01-09) classified as `UNEXPLAINED_MISSING_RECORD`; snapshot generation over gapped series fails closed with `NonContiguousDatasetError`. |
| **G2B.5-5** · Silver partition immutability (append-only) | **PASS** | First partition write succeeds; attempting to overwrite an existing daily partition fails closed with `SilverPartitionImmutableError`. |
| **G2B.5-6** · DuckDB views DECIMAL(18,4) typing, corruption fail-closed & disposable views | **PASS** | `typeof(close)` is `DECIMAL(18,4)`; numeric predicates (`close >= 3000` returns 0; `close >= 1000` matches INFY, excludes RELIANCE) and `avg(close)` compute accurately; corrupt partition raises `DuckDBViewError` fail-closed; deleting `.duckdb` file deletes database with zero fingerprint change. |
| **G2B.5-7** · Gating window enforcement (no GO/APPROVED/PASS before 2018-04-01) | **PASS** | Window starting 2017-01-01 classified as `PRE_SURVEILLANCE_WARMUP`; attempting `GO`, `APPROVED`, or `PASS` raises `GatingWindowValidationError`; resolved verdict forced to `NOT RUN`; binding window starting 2018-04-01 permits `GO`. |

#### Phase 2C — Strategy Contract & Next-Session Walk-Forward Engine (Implemented — NOT SIGNED OFF, see audit §25)
Modules: `src/signal_core/strategy/base.py`, `src/signal_core/research/walkforward.py`.

- `Strategy` contract: `generate_signals(as_of, next_session, universe, features) -> tuple[OrderIntent, ...]`, with only data at or before `as_of` reachable. Intents that reference a later session or same-session fill ($T \to T$) are rejected fail-closed.
- The engine drives the existing `ExecutionFillSimulator` and `Portfolio` — **no second simulator, no parallel fill or cost path**. Every intent becomes a fill that posts through the ledger.
- Per fold: fit on train, trade the test window at or beyond the configured latency, and emit an equity curve plus the metrics 2A's schema expects.
- Eligibility stays enforced by `APPROVED_EQ_ONLY_POLICY`; a strategy cannot widen it.
- Audits circuit evidence on every fill: if any fill lacks verified circuit depth, the result is flagged `CIRCUIT_UNVERIFIED` and cannot be promoted to `VERIFIED`.

**Phase 2C Computed Gate Verdicts (measured via `scripts/verify_phase2c_walkforward.py` and `probe_phase2c.py`)**:

| Gate | Status | Computed Measurement Basis |
|---|---|---|
| **G2C-1** · Bit-for-bit determinism across reruns | **PASS** | Rerun with identical strategy params, dataset fingerprint, and fold spec reproduces bit-for-bit identical outputs: fingerprint (`WF-RES-V1-c3885d8087dced2a...`), final equity (`₹1000000.00`), Sharpe (`0.00`), and trade count. |
| **G2C-2** · Same-session lookahead intent rejection ($T \to T$) | **PASS** | `OrderIntent` with `target_date <= signal_date` raises `LookaheadIntentError` fail-closed; rogue intent targeting current session evaluated by `WalkForwardEngine` raises `WalkForwardLookaheadError` fail-closed. Same-session execution ($T$ close $\to$ $T$ fill) strictly prohibited. |
| **G2C-3** · Series eligibility enforcement (`APPROVED_EQ_ONLY_POLICY`) | **PASS** | Strategy orders for ineligible Trade-to-Trade `BE` instrument (`INE999B01019`) are rejected by simulator with `FillStatus.REJECTED_INELIGIBLE_SERIES` (4 rejections, 0 fills). Ineligible instruments never reach fill or ledger. |
| **G2C-4** · Circuit evidence audit & promotion gating | **PASS** | Executed fills lacking verified circuit limit depth are flagged with `circuit_evidence_complete = False` and `verification_status = 'CIRCUIT_UNVERIFIED'`, blocking false promotion to `VERIFIED` per Rule 5.3 & 5.5. |
| **G2C-5** · Single authoritative engine & portfolio ledger integration | **PASS** | Trade fills route strictly through `ExecutionFillSimulator` and post to `Portfolio` `CashLedger` (statutory STT, stamp duty, turnover fees deducted; cash balance reduced; positions opened and tracked). Concentration limit breaches (> 10% weight) fail closed with `PortfolioRiskLimitError`. |

---

### Audit §26 Phased Wave Sequence (Roadmap to Full Production Backfill & Phase 2D)

Per Auditor §26 recommendation, work is staged in strict waves before ingesting the 2015–2026 historical corpus:

```
Wave 0 (Pre-ingest: G-1, Schemas, Holdout Decision) [COMPLETED]
   │
   ▼
Wave 1 (Thin 1-Month Real Slice: 1 scrip, 1 month real NSE Bhavcopy)
   │
   ▼
Wave 2 (Close Phase 2C Blockers: G-2/G-3 Risk Limit, G-5 Latency, G-4 Gold Dataset Binding, Falsifiable Gates)
   │
   ▼
Wave 3 (Full Historical Backfill 2015–2026: Tier B Warm-up + Tier A In-Sample, Validation, and Physically Sealed Holdout)
   │
   ▼
Wave 4 (Phase 2D: Automated Verdict Engine & End-to-End Regression on Real Tier-A Data)
```

#### Wave 0 — Pre-Ingestion Containment & Schema Freezing (Completed & Verified)
Modules: `containment.py`, `walkforward.py`, `bronze.py`, `security_master.py`, `universe.py`, `price_band.py`.
Documentation: [`docs/holdout_physical_separation_architecture.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/docs/holdout_physical_separation_architecture.md).

- **G-1 Holdout Containment Closed**:
  - `WalkForwardFold` carries `partition_role: Optional[PartitionRole] = None` (normalized to enum, incorporated into `compute_fold_spec_fingerprint`).
  - `WalkForwardEngine.run_fold` and `run_walk_forward` enforce fail-closed containment:
    1. Unlabelled folds (`partition_role=None`) are strictly refused fail-closed with `HoldoutSealedError`. Unknown must not run.
    2. Any fold whose date window intersects `[partition_spec.holdout_start, partition_spec.holdout_end]` strictly requires verified human-authorized `HOLDOUT_UNLOCK` sentinel file matching `holdout_token_hash`. Mismatched roles (e.g. fold intersecting holdout claiming to be `VALIDATION`) fail closed.
    3. Folds declared as `HOLDOUT` without a `PartitionSpec` fail closed.
- **Ingest Schemas Frozen in Code**:
  - `BronzeManifestEntry` (in `src/signal_core/storage/bronze.py`): Typed fields (`relative_path`, `source_url`, `retrieved_at`, `byte_count`, `sha256`, `restatement_ref`, `source_archive_format`) with strict `__post_init__` invariant validation (no directory traversal, no backslashes, positive byte count, exact 64-char hex SHA-256).
  - Manifest Locking (Finding E-15): Implemented `BronzeStorage._lock_manifest()` context manager using an atomic inter-process `.lock` file to guarantee serial writes and prevent interleaved partial lines during concurrent ingestion.
  - `CorporateAction` (in `src/signal_core/storage/security_master.py`): Verified exact Decimals for `ratio_numerator` and `ratio_denominator`, `ex_date`, optional `record_date` ($\ge \text{ex\_date}$), `circular_ref`, and mandatory distinct `old_isin`/`new_isin` validation for `ISIN_TRANSITION`.
  - `IndexMembershipInterval` (in `src/signal_core/contracts/universe.py`): Time-varying universe membership represented as half-open interval tables $[effective\_from, effective\_to)$ per Rule 10.5, with mandatory ISIN identity (Rule 10.4), overlap detection, and serialization.
  - `PriceBandSourceDescriptor`, `PriceBandRecord`, `PriceBandInterval` (in `src/signal_core/contracts/price_band.py`): Authoritative NSE publication sources (`NSE_DAILY_PRICE_BAND_REPORT`, `NSE_PR_ZIP`, `NSE_SURVEILLANCE_CIRCULAR`), discrete daily circuit observations with exact Decimal bounds and unconstrained F&O handling, plus half-open interval tables for sustained fixed surveillance bands.
- **Physical Holdout Separation Adopted (E-15)**:
  - Formally committed in [`docs/holdout_physical_separation_architecture.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/docs/holdout_physical_separation_architecture.md).
  - Holdout data (2025–2026) will be stored in a physically segregated directory tree (`storage_holdout/`) with an independent cryptographic manifest lock, completely outside `storage/silver/`. The Gold layer and DuckDB views globbing standard silver physically cannot discover or parse holdout files.

#### Phase 2D — Automated Verdict Engine & End-to-End Regression
Module: `src/signal_core/reporting/verdicts.py`.

- Reads the pinned criteria version (echoed in the output), computes every criterion from a results bundle, and emits `NOT RUN` for any metric the bundle does not contain. `PASS` may only be attached to a printed computed value.
- A test scans the reporting module for hardcoded verdict or adjective strings and fails on any.
- End-to-end regression on `tests/fixtures/small_synthetic_dataset.json`, plus an adversarial suite that must fail closed: tampered registry chain, sealed holdout read, lookahead intent, DSR computed with `N = 1`.

**2D gates:** the verdict report is reproducible from the results bundle alone; every label in it is traceable to a computation; adversarial cases fail rather than degrade.

**Definition of done for Phase 2:** all four slices' gates measured and recorded; an end-to-end synthetic run produces a verdict report whose only `NOT RUN` entries are metrics the data genuinely cannot support (currently circuit-verified PnL); no module can reach the holdout without the human sentinel.
