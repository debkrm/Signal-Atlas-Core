# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 2B signed off** (§22) · **Phase 2B.5 signed off — GO** (§24) · **Wave 0 signed off — GO** (§29 at `d2fd8e0`) · **Wave 1 signed off — GO** (§30 at `95ac584`) · **Wave 2 / Phase 2C signed off — GO** (§33 at `982c9fa`) · **Wave 3 — GO at `a093682` for 2022-01-03..2026-10-31** (§41) · **Phase 2D phase signed off — GO** (§56 at commit `0be0da3`, audit `9368fc4`) · **Phase 3A signed off** (§58 at `d7590fe`, H-81 closed in §59 at `3e619f8`, audit `e5dd500`) · **Phase 3B-1 signed off — GO** (§60 at `078ff8d`, §61 at `4d81077`, §62.4 GO stands, §63.4 GO stands at `396f825`, audit `80a1997`) · **Phase 3B-2a signed off — GO** (§60, §61, §62.4, §63.4 GO stands) · **Phase 3B-2b §64 items (H-102..H-109, N-92 remainder, N-101..N-103) implemented & verified following §64 audit review at commit `817c2ba`; authorized baseline re-run executed as seq #2 in TrialRegistry (`TRIAL-PHASE3B2-SWING-BASELINE-002`, CAGR 6.46%, MaxDD 12.36%, Profit Factor 1.7428, honest NO-GO with `CRIT-SURV-01: NOT RUN`, `CRIT-PROV-01: NOT RUN`, `CRIT-STAT-03: FAIL`); awaiting auditor review** |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, series continuity, pure subsegment feature engine, typed criteria loader, statutory Indian cost engine, non-linear slippage model, authoritative execution simulator, exact Decimal cash book, multi-fill position accounting, mark-to-market portfolio valuation, committed risk tracker, holdout containment with physical storage rejection, tamper-evident trial registry, statistical significance engine, strategy contract, walk-forward engine with canonical partition spec defaults and Gold dataset binding, frozen ingest schemas, real Bhavcopy ingestion pipeline, invert-proof corporate action & circuit band contracts, falsifiable circuit auditing, anchored calendar governance, automated fail-closed verdict reporting, exact ATR R-multiple position sizing, point-in-time liquidity universe selection, authoritative daily T+1 order execution runner, position corporate action adjustment mechanism (splits/bonuses/dividends/ISIN transitions/consolidations/rights/delistings/mergers), cash universe price band intervals, surveillance stage exit constraint mechanism (three-state surveillance with GSM Stage 2+ weekly call auction), and authoritative end-to-end walk-forward baseline backtest runner |
| **Offline Test Suite** | **`393 passed in 49.38s`** on this Windows checkout; `verify_cash_universe_coverage.py` exit 0; `verify_phase2d_verdicts.py` exit 0 (Gates 2D-1..2D-5 PASS); `verify_audit_append_only.py` W0.5-1..W0.5-4 PASS (all 8 verification scripts exit 0). Zero skipped, zero xfailed |
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

 [2 pre-requisite: Wave 0.5 Repository Foundation Gate]  (scheduled — see below)
```

**Strategy scope (AGENTS.md §13).** Delivery swing on NSE `EQ`: multi-session holds, no intraday, no F&O, no `BE`/`BZ` entry. Recorded as a rule so it binds later strategy work; it changes no engine and adds no module.

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

#### Wave 0 — Pre-Ingestion Containment & Schema Freezing (Remediated & Verified)
Modules: `containment.py`, `walkforward.py`, `bronze.py`, `security_master.py`, `universe.py`, `price_band.py`, `silver.py`, `gold.py`.
Configs: [`configs/partition_spec.yaml`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/configs/partition_spec.yaml).
Documentation: [`docs/holdout_physical_separation_architecture.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/docs/holdout_physical_separation_architecture.md).

- **G-1 Holdout Containment & Physical Rejection (H-1, H-2, H-6 Closed)**:
  - **H-1 Holdout Date Rejection**: Standard `SilverStorage` and `GoldEngine` reject any read, write, or query intersecting the canonical holdout window `[2025-01-01, 2026-11-11]` fail-closed with `HoldoutPartitionIsolationError` unless instantiated with `is_holdout_storage=True`; `partition_exists` is guarded too. Verified by audit §28 (P12a/P12c/P16), §29 and §30. Physical root enforcement rejects `storage/silver/holdout` (§30 verified), but it is still a **name** test: a root nested under a standard tree not literally named `silver` is accepted (§30 H-20), and the unlock token is still caller-supplied (§29 H-16, unchanged).
  - **H-6 Committed Canonical Partition Spec**: Committed [`configs/partition_spec.yaml`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/configs/partition_spec.yaml) defining authoritative In-Sample (2018-04-01 to 2023-12-31), Validation (2024-01-01 to 2024-12-31), and Holdout (2025-01-01 to 2026-11-11) windows with placeholder token hash.
  - **H-2 Default Fail-Closed Containment**: `WalkForwardEngine` defaults to loading the canonical partition spec. Removed all fail-open defaults (`partition_spec=None` cannot run without spec resolution). Any fold intersecting the holdout window without verified human unlock raises `HoldoutSealedError`. Unlabelled folds (`partition_role=None`) fail closed.
- **Ingest Schemas Frozen & Invert-Proofed (H-3, H-4, H-5 Closed)**:
  - **H-5 Corporate Action Ratio Direction & Split Invariant**: `CorporateAction` in `security_master.py` clearly documents ratio semantics (`ratio_numerator`: post-event shares held per `ratio_denominator` pre-event shares held; `adjustment_factor = den / num`). Strictly enforces `ratio_numerator > ratio_denominator` for `SPLIT` and `BONUS`, rejecting inverted splits (`num <= den`) fail-closed. 1:10 split verified to produce `adjustment_factor == Decimal('0.1')`.
  - **H-4 Circuit Filter & Unconstrained F&O Validation**: `PriceBandRecord(is_unconstrained=True)` requires an authoritative `source_descriptor` citation and either dynamic `band_percentage` or explicit limits; anonymous unconstrained claims fail closed with `PriceBandValidationError`. Declared upper/lower circuit limits are reconciled against `band_percentage` (`|implied_pct - band_pct| <= max(1.5, 0.20 * band_pct)`), rejecting inconsistent records fail-closed.
  - **H-3 Bronze Manifest Lock — CLOSED (§29, H-19 sealed)**: `BronzeStorage._lock_manifest()` acquires with `O_CREAT|O_EXCL` and never breaks a lock on age. Inode comparison (`acquired_stat.st_ino == current_stat.st_ino`) added before unlinking, ensuring a process cannot delete a successor writer's lock.
  - **H-8 Walk-Forward Docstring Cleanup**: Removed duplicated parameter docstring lines in `generate_walk_forward_folds`.

#### Wave 1 — Thin Real-Data Vertical Slice (Completed & Verified)
Modules: `src/signal_core/storage/ingest.py` (new), `src/signal_core/storage/silver.py`, `src/signal_core/storage/bronze.py`, `src/signal_core/storage/gold.py`, `src/signal_core/storage/views.py`.
Verification script: [`scripts/verify_wave1_thin_slice.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/verify_wave1_thin_slice.py).
Unit tests: [`tests/unit/test_wave1_thin_slice.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_wave1_thin_slice.py).

- **Real Ingestion Pipeline (`ingest.py`)**:
  - `parse_bhavcopy_archive()`: Decodes raw NSE Bhavcopy archives (handling trailing delimiters, empty columns, whitespace, and column permutations across legacy and unified formats).
  - `ingest_daily_bhavcopy_archive()`: Stores byte-exact ZIP in Bronze with SHA-256 provenance manifest, parses records into exact `Decimal` and `datetime.date`, enforces calendar session compliance, and writes atomic daily Parquet partitions in Silver.
- **Authoritative Calendar Completeness & Disaster Recovery Session (Finding F-4 Closed on Real Data)**:
  - Discovered and incorporated the Saturday 2024-01-20 live Disaster Recovery trading session into `configs/trading_calendar_nse.json`. Total sessions updated to 2,940 with annual count 249 for 2024, confirmed by audit §30 against the 249 real 2024 archive dates (bidirectional set difference empty). The cited circular reference `NSE/CMTR/60309` is unverifiable — the documented references are `NSE/MSD/60300` and `NSE/MSD/60318` — and the day was in fact two windows (`09:15–10:00` primary, `11:30–12:30` DR) with a 5% band, not one `09:15–12:30` session (§30 H-27). The calendar's recorded `provenance.sha256` no longer matches the file and is not recomputed (§30 H-26).
  - Verified all 22 trading sessions of January 2024 match Bhavcopy archives without missing-session gaps.
- **Vertical Pipeline Execution on `COCHINSHIP` (January 2024)**:
  - Ingested 22 sessions of real January 2024 Bhavcopy (`cm01JAN2024bhav.csv.zip` through `cm31JAN2024bhav.csv.zip`).
  - **Security Master & Real 2:1 Stock Split**: Old ISIN `INE704P01017` active Jan 1–9 (7 sessions); New ISIN `INE704P01025` active Jan 10–31 (15 sessions). Real 2:1 stock split on ex-date 2024-01-10 verified (`ratio_numerator=2, ratio_denominator=1, factor=0.5`).
  - **Gold Derived Layer**:
    * Unadjusted raw close: 2024-01-09 = ₹1,338.00 (vol 3,355,705) -> 2024-01-10 = ₹802.80 (vol 22,442,717).
    * Split-adjusted close: 2024-01-09 = ₹669.00 (vol 6,711,410) -> 2024-01-10 = ₹802.80 (vol 22,442,717).
    * Deterministic Content Fingerprint: `DATA-CTNT-V2-53c061fb9d45a24a61929f573ad7fec3` and Universe Fingerprint: `UNIV-SCHED-V1-ad0091e85def8c9784dda2dbdbfef3c9` reproduced bit-for-bit across independent reruns.
  - **DuckDB View Layer**: Attached disposable DuckDB engine over 22 Silver Parquet files. Verified `silver_bhavcopy` schema with exact `DECIMAL(18, 4)` precision, `BIGINT` volume, `DATE` trade_date, and executed SQL aggregations (22 rows, ₹753.85 min close to ₹1,363.25 max close, 130,613,155 total volume).
  - **Index Membership Interval (interval arithmetic only)**: `IndexMembershipInterval.contains` verified half-open `[effective_from, effective_to)` across `INE704P01017` → `INE704P01025`. The two intervals are constructed from literals inside the verification script; no circular-backed NIFTY500 membership data exists, and membership does not end on a split ex-date (only the ISIN changes). Labelled a real-data gate in error (§30 H-27).
  - **Ingest contract limits (§30)**: volume parsed via `int(float(...))` (measured: `100000000000000001` → `100000000000000000`; fractional accepted silently — H-23); trade date latched from the first matching row so a multi-date archive stamps every row with that date (H-24); truncated rows and duplicate non-`EQ` rows dropped without a count (H-25). None affect the single-day January 2024 slice; all must be fixed before any multi-date archive or bulk backfill.

#### Wave 2 — Strategy Contract, Walk-Forward Engine & Falsifiable Gates (Signed off — audit §33, GO at `982c9fa`; H-38/H-39 closed per audit §34 at `085fb0a`)
Modules: `src/signal_core/strategy/base.py`, `src/signal_core/execution/types.py`, `src/signal_core/portfolio/portfolio.py`, `src/signal_core/storage/security_master.py`, `src/signal_core/research/walkforward.py`.
Verification script: [`scripts/verify_phase2c_walkforward.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/verify_phase2c_walkforward.py).
Runner: [`probe_phase2c.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/probe_phase2c.py).
Unit tests: [`tests/unit/test_walkforward.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_walkforward.py).

- **G-2 / G-3 Strategy Sizing & Portfolio Risk Limit Handling**:
  - `TechnicalCrossStrategy.allocation_weight` default set to `Decimal("0.08")` (comfortably below committed `max_single_position_weight = 0.10`).
  - `WalkForwardEngine.run_fold` catches `PortfolioRiskLimitError` raised during `portfolio.process_fill(enforce_risk_limits=True)` and converts the outcome into `ExecutionFillResult(status=FillStatus.REJECTED_RISK_LIMIT, filled_quantity=0, ...)`. Preserves fold continuity and records the rejected attempt in the fold's trade journal instead of aborting the backtest.
- **G-5 Execution Latency Realism**:
  - `execution_latency_sessions` on `WalkForwardEngine` advances the signal-generation hint via `calendar.advance_sessions(t, self._latency)`. Clamped with `max(1, latency)`. Verified: signal on Jan 15 executes on Jan 16 for $L=1$ (`latency_sessions=1`), and on Jan 17 for $L=2$ (`latency_sessions=2`). Configured latency is now **authoritative**: dispatch raises `WalkForwardEngineError` when `intent.target_date` differs from the engine-selected session, so a strategy cannot fill at T+1 inside an $L=2$ run (audit §31 H-29, closed in §32).
- **G-4 Gold Layer Dataset Binding**:
  - `dataset_content_fingerprint` in `WalkForwardEngine.run_walk_forward` automatically resolves from `GoldEngine.build_dataset_snapshot()` when omitted, binding the authentic `DATA-CTNT-V2-...` hash into `WalkForwardResult`.
  - `run_walk_forward` builds the Gold snapshot over the fold window unconditionally and rejects any supplied fingerprint that is not **exactly equal** to it, so `"DATA-CTNT-V2-" + "0"*32` fails closed (audit §31 H-28, engine side closed in §32). `criteria_version` is computed from the criteria in force, `1.1.0` (§31 H-34, closed in §32), and the execution configuration is hashed into `WF-RES-V1-…` and carried on the trial record (§31 H-33, closed in §32).
  - Cost and slippage are recorded as `{"model": class name, "parameters": {...}}` — all statutory rates, GST base components, the effective-dated exchange/IPFT schedule, and `half_spread_bps`/`impact_kappa`/`impact_alpha` (§32 H-37, **CLOSED in §33**), and `to_trial_record()` / `register_in_trial_registry()` now refuse any supplied `dataset_fingerprint` that differs from the authentic one (§32 H-35, **CLOSED in §33**), leaving no registry file or manifest behind a rejected call.
  - **H-38 / H-39 — CLOSED (§34; committed as `085fb0a`, whose `walkforward.py` diffstat `33 insertions(+), 5 deletions(-)` reproduces the audited diff exactly; second-reader countersign of §34.2 still pending per the §34 authorship disclosure).** Both boundaries reject a supplied `criteria_version` or `execution_config` that differs from the run's computed value, and `exec_config` carries `criteria_fingerprint` (`CRIT-FPR-V1-…`), a SHA-256 over every field of the typed criteria including the statutory cost schedule. Measured: `238 passed`; all five probes exit 0; `verify_phase2c_walkforward.py` 5/5 with the new H-38/H-39 discriminators, and it reports FAIL with exit 1 when either seal is removed. Behavioural proof that the fingerprinted thresholds bind the fills: `max_volume_participation_cap` set to `0.00001` turns the single fill into `REJECTED_VOLUME_CAP` and changes the fingerprint.
- **Falsifiable Gates (G-8, G-6, G-7, G-9, G-11, G-12, G-13)**:
  - **Gate G2C-1 (Live Trades & Bit-for-Bit Determinism)**: Exercises live trade entries (4 trades, 1 fill) on INFY; verifies exact bit-for-bit identity across reruns on fingerprint, final equity, Sharpe, returns, and prices.
  - **Gate G2C-4 (Falsifiable Circuit Auditing & Freeze Refusal)** — measured only with hand-built `PriceBandRecord`s (audit §35 N-6). A price-band ingest now exists, but it produces percentage-only records that carry no upper/lower limit while still reporting `has_circuit_evidence=True`, so `VERIFIED` is reachable on a run where no freeze test can fire (§35 H-40) and no committed gate walks parse → master → fill:
    * Zero-trade runs explicitly flag `verification_status = "NOT RUN"` and `circuit_evidence_complete = False`.
    * BUY fills at/above Upper Circuit limit are refused fail-closed with `FillStatus.REJECTED_UPPER_CIRCUIT`.
    * Runs with complete price bands achieve `verification_status = "VERIFIED"`.
  - **G-7 Geometric Compounded Annualized Return**: Added `compute_compounded_annualized_return` implementing exact Decimal geometric CAGR: `(factor * (1 + R).ln()).exp() - 1` with committed `sessions_per_year = 250`.
  - **G-9 Bare Exception Removal**: Removed bare `except Exception:` from risk limit checks in `verify_phase2c_walkforward.py`.
  - **G-11 Length Mismatch Fail-Closed**: Added check in `WalkForwardEngine` asserting `len(f_res.daily_returns) == len(f_res.portfolio_snapshots)` before zip, raising `WalkForwardEngineError` on discrepancy.
  - **G-12 Storage Invariants Exposed**: Exposed `full_sessions_only` and `fail_closed_on_unexplained` parameters on `WalkForwardEngine` forwarding to `GoldEngine`.
  - **G-13 Cash Sufficiency Pre-Check**: Added available cash check in `Portfolio.process_fill` before `validate_allocation`, raising `PortfolioRiskLimitError` if outlay exceeds available cash.

#### Wave 0.5 — Repository Foundation Gate (partially implemented at `581ac0f`; not audited as a wave)
No audit verdict exists for this wave. 0.5c is implemented and its two §39.6 holes are shut (§40.7 at `581ac0f`: `git log -p -m` diffs merge commits, and the gate discovers all seven `scripts/verify_*.py` instead of a hardcoded six). 0.5b is half done: `.github/workflows/ci.yml` runs pytest and the gate on push, but that gate discovers `verify_cash_universe_coverage.py`, whose COV-2 prints `[SKIP]` and returns PASS where the archive is absent — on the runner it passes vacuously (§40.6 H-53). 0.5a is untouched: no tag names `d0e18c5`, `427eb05`, `30cc4c8` or `581ac0f`, and branch protection remains unverifiable from the repository. The rest of this section remains a plan, not a claim.

- **0.5a · History protection (do first, no code).** Enable branch protection on `main`: no force-push, no deletion. Tag each GO verdict at the SHA it names. Rationale: every §N citation in the audit report and every status claim in this file points at a SHA, and the audit report is append-only, so a rewritten `main` would silently invalidate references that cannot be repaired (§12.1–12.2).
- **0.5b · Minimal offline CI.** On every push: the full test suite; every `scripts/verify_*.py` with exit status preserved and required zero; the §11.1 check that the audit report gained no removed line. One Python version, no network, no coverage threshold, no linter (§12.3–12.5).
- **0.5c · Gate honesty.** The job fails on `skip`/`xfail`/exclusion added to reach green; any relaxation is a documented decision in the same commit (§12.4).

**Why here, and not later.** H-45 was a *regression* introduced by a commit that also fixed real findings, and it was caught only because a human ran probes by hand. Wave 3 then writes immutable partitions and fingerprints — artifacts that must be guarded by a gate that exists *before* the artifact does. Wave 3 is currently NO-GO, so the window is free: the implementer's next round touches `ingest.py` while 0.5 touches repository configuration and `scripts/` only, so the two do not collide.

**Deliberately deferred to after Phase 2D:** any dashboard, coverage reporting, multi-OS or multi-version matrices, and any CI step that reaches the network. Swing *research* also waits for Wave 3 data; only the scope rule (§13) is set now.

#### Wave 3 — Full Historical Backfill (GO at `a093682` for 2022-01-03..2026-10-31, extended to `c7d3e88` — audit §41, §42; 2018-04-01..2021-12-31 NOT RUN, unsourced)
Modules: `src/signal_core/storage/ingest.py`, `security_master.py`, `contracts/price_band.py`, `execution/simulator.py`, `research/walkforward.py`.

- **H-30 — CLOSED at `1e14e8e` (§36).** H-40, H-41 and H-42 are closed: circuit evidence requires both numeric limits (a percentage alone is not evidence), limits are derived from the previous session's close with ex-date corporate-action adjustment, a BUY at the derived upper circuit is refused `REJECTED_UPPER_CIRCUIT`, `No Band` rows resolve to `band_percentage=None` with the exchange citation, and every corrupt band row aborts the ingest with its line number. Measured at `2589aed` and still standing: `parse_price_band_report()` / `ingest_daily_price_bands()` parse the live archive the production master cites (177,218 bytes, 3,624 rows) and store it byte-exact in Bronze; `get_price_band()` now resolves half-open `PriceBandInterval`s as-of a session instead of requiring an exact-date record, with overlapping intervals rejected; a traded instrument with no band on a session raises `WalkForwardEngineError` fail-closed (`fail_closed_on_missing_band`, hashed into `exec_config`); and a `CIRCUIT_UNVERIFIED` result can no longer become a trial record or registry entry.
- **H-40 / H-41 / H-42 — CLOSED (§36 at `1e14e8e`).** The percentage-only path that reported `VERIFIED` with `upper None, lower None` is inverted: without a previous close the band reports `has_circuit_evidence=False`, an unconstrained `No Band` fill is stamped unverified and the run is `CIRCUIT_UNVERIFIED` (unpublishable), and a BUY at the derived ₹1,200.00 circuit on a ₹1,000.00 previous close is refused. `parse_price_band_report` against the live archive returns `pct=None` for `COCHINSHIP`/`INFY`/`RELIANCE`.
- **H-45 / H-46 / H-47 (zero-record) / H-48 / N-12 / N-13 — CLOSED (§38.1 at `0b1504a`).** A bhavcopy member can no longer outrank the band file; a header with no band or limit column raises `PriceBandIngestError`; the real `sec_list.csv` with no security master raises naming 3,624 unresolved rows; the master's split-day record is gone; INFY/RELIANCE are honest `No Band` with a genuine 10% fixture scrip carrying the verified-fill path.
- **H-49 / N-15 / N-16 — CLOSED (§39.1 at `427eb05`).** Discrete band records are validated against the interval covering their date at construction, through a public `validate_price_band_record()`, and at the Silver write boundary: the §38.2 phantom (`20.00% / 802.80 / 535.20` on 2024-01-10) is refused with `SecurityMasterError`, and the test that asserted it was corrected. The ZIP header probe raises instead of swallowing. `write_price_band_partition` refuses to run without a `TradingCalendar`. Coverage caveat: the production master holds zero constrained intervals, so the constrained branch of the check is fixture-only (N-19).
- **H-44 / H-52 / H-53 — CLOSED (§41.2–§41.4 at `cf873fc`).** COV-4 now ingests three real January 2024 Bhavcopy archives (SHA-256 matched to Bronze) plus the real 3,624-row band publication: `20MICRONS` fills at the real 16-Jan open ₹178.00 plus modelled slippage on a real 20% band derived from the 15-Jan close ₹176.65 (upper ₹211.98), `Circuit Evidence Present: True`, fold `VERIFIED`. COV-3 measures the band publication the pipeline consumes and asserts `unresolved_in_scope == 924` and `extracted == 1839` rather than tolerating them; COV-2 is relabelled as the traded-scrip regression check it is. Both gates fail closed with a named reason when an archive is absent and resolve the archive root via `NSE_RAW_ARCHIVES_DIR`. Independently measured by the auditor over the whole window: **2,390,165 traded `EQ` rows across 1,195 archives resolve 100.0000% — zero unresolved, zero wrong-ISIN, zero ambiguous** (§41.3).
- **H-50 / H-51 — CLOSED (§40.2, §40.3 at `581ac0f`).** The cash-universe identity table is derived from 1,195 real Bhavcopy archives, re-derives byte-identically (`sha256 b1746c9e…`), resolves real ISIN transitions on the correct side of each ex-date, prunes `HDFC` at its 2023-07-13 merger, and raises on a corrupt row or a missing file. Manifest entries now carry `is_current`/`status` and COV-1 fails when the active entry's SHA or byte count diverges (N-25 CLOSED).
- **H-54 — CLOSED at `c7d3e88` (§42.2); the enforcement gap N-34 it left open is CLOSED at `5c0272a` (§43.2).** The calibrated `min_session_price_band_coverage_pct: "65.0"` is gone from the config, the loader, the dataclass and the gate; COV-2 reads the committed `min_traded_eq_resolution_pct: "100.0"` over the actively traded `EQ` set and now sweeps every discovered archive, printing `2,390,165 / 2,390,165 traded EQ rows resolved across 1,195 sessions` — the same figure §41.3 measured independently, with the resolution failure path naming session date, symbol and both ISINs. **H-55 (§43.3) is what remains:** the count of sessions swept is not asserted against anything, so the same PASS text is produced over 22 fixture archives as over the window.
- **N-19 / N-24 / N-26 / N-28 / N-29 — CLOSED (§40.4, §41.6).** Series partitioning before counting; every `assert` replaced by a `raise` that survives `python -O`; `filtered_target_isin_count` split from `out_of_scope_series_count`; the deriver reports sessions kept from archives parsed and why two were rejected; a sourced ISIN diverging from a core interval raises `SecurityMasterError` (measured: all five core intervals overlap and agree).
- **Notes (§40.7–§50):** N-20, N-21, N-23 CLOSED; N-32–N-34, N-36, N-37 CLOSED at `5c0272a` (§43); **N-39 CLOSED at `5a98981` (§44.3)**; **H-56 and N-40.1–N-40.4 CLOSED at `0edc158` (§45.1)**; **H-58, N-42, N-43 CLOSED at `0b88f67` (§46.1)**; **H-59 CLOSED as wiring at `0b88f67` (§46.1)**; **H-60 CLOSED at `95f4af2` (§47.1)**; **H-62 CLOSED at `fe3dca4` (§48.2)**; **H-64 and N-51 CLOSED at `8e67e07` (§50.2, §50.4)** on measurement (calendar identity pinned in criteria via `CAL-FPR-V1-af8e309a…`, 7 of 7 pinned invariant keys fail closed); **H-57 amendment half CLOSED at `8e67e07` (§50.5)**; **Wave 4 / Phase 2D — GO granted at `8e67e07` / `2132d7f` (§50.8)** with four carried residuals binding first report (R-3, R-4, R-5, R-6).
- **Residual Remediation & Text Corrections:**
  - **R-5 / N-53 CLOSED:** `verified_regular_trading_sessions` renamed to `inferred_trading_sessions` in `data/raw/circulars/NSE_CMTR_71775.json`; typed contract in `src/signal_core/storage/circulars.py` updated to `CircularTradingDayInference` and `verify_trading_day_inference`; classification in `data/reference/calendar_reconciliation_2022_2026.json` updated to `INFERRED_TRADING_SESSION`.
  - **N-54 CLOSED:** `amendment_note` in `data/raw/circulars/NSE_CMTR_72260.json` corrected to declare 2026-01-15 as an additional holiday (not "originally listed in 71775").
  - **N-55 CLOSED:** `data/reference/manifest.jsonl` entry for `calendar_reconciliation_2022_2026.json` description accurately reflects that 2026-01-15 is substantiated by partial modification NSE/CMTR/72260, and 2026-03-20 & 2026-05-27 are inferred non-holiday sessions.
  - **R-6 (implemented, migrated across all consumers, measured per §52.3):** `load_nse_trading_calendar()` defaults to criteria-anchored loading (`anchored=True`), and all consumer call sites (`scripts/derive_cash_universe_intervals.py`, `scripts/verify_cash_universe_coverage.py`, `src/signal_core/reporting/verdicts.py`) explicitly use `load_anchored_nse_trading_calendar()`, failing closed on date swaps or count mismatches.
  - **R-3 / H-67 (implemented, measured per §52.4):** `src/signal_core/reporting/verdicts.py` validates dataset provenance against `ProvenanceStatus` and refuses any `VERIFIED` claim lacking a resolvable committed exchange attestation in the repository (evaluating to `NOT RUN` with overall `NO-GO`), while ensuring `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` data evaluates strictly to `NOT RUN` per AGENTS.md Rule 6.5.
  - **H-65 (implemented, measured per §52.9):** `BINDING_EVALUATION_START_DATE` in `src/signal_core/storage/gating.py` and `calendar.py` aligned to `criteria.min_binding_evaluation_start_date` (`2022-01-03`); pre-2022 evaluations fail closed to `NOT RUN`.
  - **H-66 (implemented, measured per §52.9):** `evaluation_start_date` and `evaluation_end_date` required and echoed in `VerdictReport.to_dict()` and `to_markdown()`; pre-window start dates evaluate to `FAIL` and `NO-GO`.
  - **N-58 (implemented, measured per §52.9):** `evaluated_at_utc` read deterministically from results bundle, ensuring bit-for-bit reproducible verdict reports from bundle alone.
  - **R-4 (implemented, measured per §52.9):** Sourced window calendar fingerprint (`CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1`, 1,196 sessions) pinned in `configs/go_no_go_criteria.yaml` and verified by `load_anchored_nse_trading_calendar()`.

#### Phase 2D — Automated Verdict Engine & End-to-End Regression (Implemented)
Module: `src/signal_core/reporting/verdicts.py`. Tests: `tests/unit/test_verdicts.py`. Gate: `scripts/verify_phase2d_verdicts.py`.

- **Verdict Engine Contract (Finding N-60)**: `evaluate_verdicts(results_bundle, criteria=None, criteria_path=None, calendar=None, calendar_path=None, now_utc=None, manifest_path=None) -> VerdictReport`.
  - Evaluates Risk & Performance, Execution Realism, Statutory Cost Schedule, Market Data Invariants, Evaluation Window Conformance, Data Provenance, and Anti-Overfitting.
  - Computes criteria version and fingerprint (echoed in output table).
  - Emits `NOT RUN` for any metric absent from the results bundle. `PASS` is attached only to printed computed values.
  - Overall verdict computes `GO` if and only if all binding criteria evaluate to `PASS`. Any `FAIL` or binding `NOT RUN` causes `NO-GO`.
  - Honest data provenance gating (Rule 6.5, §50.8 Residual R-3, Findings H-67, H-68): `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` data evaluates to `NOT RUN` with reason; `VERIFIED` requires active manifest registration and dataset fingerprint match (Finding H-68).
- **AST / Regex Adjective Gate (`test_banned_adjectives_ast_scan`)**:
  - Scans `src/signal_core/reporting/` for prohibited qualitative adjectives (`HEALTHY`, `OPTIMAL`, `ROBUST`, `CONTROLLED`) per Rule 9.1; asserts 0 occurrences.
- **Fail-Closed Adversarial Suite**:
  - Holdout breach attempt without human `HOLDOUT_UNLOCK` raises `HoldoutBreachError` fail-closed (§8.1).
  - Multi-hypothesis trial count $N \le 1$ evaluates to `NOT RUN` fail-closed (§8.2).
  - Lookahead execution latency = 0 evaluates to `FAIL` fail-closed (§7.1).
  - Unanchored / tampered calendar raises `CalendarError` fail-closed (Finding H-64, Residual R-6).
  - Pre-binding evaluation window (< 2022-01-03) fails closed to `FAIL` and `NO-GO` (Finding H-66, §10.8).
  - Unattested `VERIFIED` provenance claim evaluates to `NOT RUN` and `NO-GO` fail-closed (Finding H-67).
  - Manifest-unregistered or digest-mismatched attestation reference rejected fail-closed to `NOT RUN` and `NO-GO` (Finding H-68).
  - Unverified manifest record or missing source_url/timestamp rejected fail-closed to `NOT RUN` and `NO-GO` (Finding H-70).
  - Forged/tampered manifest rejected fail-closed with criteria pin mismatch (Finding H-72).
  - Window outside calendar bounds and implausible session/trade count rejected fail-closed to `FAIL` and `NO-GO` (Findings H-69, H-71).
- **End-to-End Synthetic Regression (`tests/fixtures/small_synthetic_dataset.json`)**:
  - Produces complete verdict report with 21 PASS, 0 FAIL, 2 NOT RUN (the only NOT RUN entries are unverified synthetic provenance per Residual R-3 and circuit-verified PnL per Phase 2 definition of done).
- **First Real Tier-A Verdict Report (`reports/verdicts/phase2d_tier_a_2022_2026_verdict.*`)**:
  - Assembles results bundle over 2022-01-03..2026-10-30 dynamically from archive manifest and criteria contracts, with zero boolean or numeric literals assigned to bundle keys (Findings H-73, H-75, N-63).
  - Evaluates honestly to `NO-GO` on unverified archive provenance (`CRIT-PROV-01: NOT RUN`) and uncomputed full-corpus backtest, walk-forward, execution observation, and accounting metrics (`NOT RUN=20`), with 3 criteria passing on computed repository artifacts (`CRIT-WINDOW-01`, `CRIT-DATA-05`, `CRIT-DATA-06`).
- **Phase 2D Gate Measurements**:
  - `scripts/verify_phase2d_verdicts.py`: Gates 2D-1..2D-5 all PASS, exit 0 (including Tier-A report generator AST literal check, committed report byte-identity, and repeated execution reproducibility).
  - `tests/unit/test_verdicts.py`: 23 passed in 1.96s, zero skip, zero xfail.
  - `scripts/generate_phase2d_tier_a_report.py`: exits 0, writing deterministic JSON and Markdown verdict reports.
  - Status: Phase 2D signed off — GO in §56 at commit `0be0da3` (audit commit `9368fc4`). Tier-A report evaluates honestly to `NO-GO` on unverified archive provenance and uncomputed Phase 3 metrics (3 PASS, 0 FAIL, 20 NOT RUN). N-63 remainder, N-66, N-67, N-68 closed in `feat-s56`. Phase 3 opened per §56 authorization.

**Definition of done for Phase 2:** all four slices' gates measured and recorded; an end-to-end synthetic run produces a verdict report whose only `NOT RUN` entries are metrics the data genuinely cannot support (currently circuit-verified PnL and unverified data provenance); no module can reach the holdout without the human sentinel.

---

## Phase 3: ATR-Based R-Multiple Position Sizing, Point-in-Time Universe Selection, NSE EQ Swing Strategies & Daily T+1 Order Runner (In Progress)

Authorized by Auditor DeepSeek in §56 at commit `0be0da3` (audit commit `9368fc4`).
All Phase 3 research, portfolio, and execution modules strictly adhere to AGENTS.md §5 (Indian Market Realism), §6 (Data Integrity), §7 (Backtest Realism & Statutory Costs), §8 (Anti-Overfitting), §10 (Market Data Storage & Reproducibility), and §13 (Strategy Scope: Delivery Swing on NSE `EQ`):
- Multi-session holds, delivery swing only (`OrderProduct.CNC`, series `EQ`).
- Zero intraday squaring off, zero F&O, zero trade-to-trade (`BE`/`BZ` entry strictly prohibited per `APPROVED_EQ_ONLY_POLICY`).
- Single authoritative execution, cost, and ledger engine (`ExecutionFillSimulator`, `TransactionCostModel`, `Portfolio`). Zero shadow simulators (§7.4, §13.5).
- Holdout partition (`2025-01-01..2026-11-11`) remains physically sealed (`HOLDOUT_UNLOCK` strictly absent per §8.1).

### Phase 3 Gating Preconditions (§56.5)
1. **Provenance Precondition (Rule 6.5, §50.8 Residual R-3, §56.5 Precondition 1)**:
   - `CRIT-PROV-01` evaluates strictly to `NOT RUN` because all 63 manifest records currently declare `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` with `source_url: None`.
   - Every Phase 3 strategy evaluation inherits this invariant and will evaluate strictly to `NO-GO`. Zero strategy `GO` verdict may be claimed or published until archive provenance is attested with source URLs, retrieval timestamps, and byte counts across all 1,195 archives.
2. **Point-in-Time Universe Precondition (§6.1, §10.5, §56.5 Precondition 2)**:
   - Nifty 500 historical constituent membership is NOT sourced in this repository (`data/reference/` contains no index constituent intervals). Static constituent lists (e.g. current Nifty 500) are strictly forbidden due to survivorship bias (§6.1, §10.5).
   - Phase 3 operates strictly on the point-in-time traded `EQ` universe derived from `cash_equity_symbol_intervals.csv` or explicit ISIN interval tables, clearly labelled as `POINT_IN_TIME_TRADED_EQ` or `POINT_IN_TIME_LIQUID_EQ`.

### Phase 3A: Position Sizing & Point-in-Time Universe Builder (Signed Off per §58.5; H-81 Closed per §59.2)
- **Audit §58.5 Sign-Off & §59.2 Verification**:
  - Implemented in `feat-s57` (commit `d7590fe`, tag `feat-s57-d7590fe`).
  - Audited by DeepSeek in §58 (commit `f0343fe`): Phase 3A signed off as implemented and verified for §57.7 items (H-77, H-78, H-79, H-80, N-69..N-74 CLOSED).
  - Remediation in `feat-s58` (commit `3e619f8`): H-81 complete lookback window coverage across all 1,196 binding calendar sessions; N-76, N-77 parameter bounds; N-78, N-79 AST checker; N-80 minimum tick documentation; N-81 citation corrections.
  - Audited by DeepSeek in §59 (commit `e5dd500`): confirmed H-81 and N-76..N-81 CLOSED on measurement (§59.2).
- **ATR-Based R-Multiple Position Sizer (`src/signal_core/portfolio/sizing.py`)**:
  - Implements exact `Decimal` position sizing formula: $Q = \lfloor (equity \times risk\_per\_trade\_pct) / effective\_stop\_distance \rfloor$.
  - Loads defaults directly from `GoNoGoCriteria` (`max_single_position_weight=0.10`, `max_volume_participation_cap=0.03` per `configs/go_no_go_criteria.yaml`), settled cash with statutory cost buffer, and strictly requires positive integer `session_volume` (Findings H-80, N-73).
  - Stop loss price calculated as $entry\_price - atr\_stop\_multiple \times ATR$, floored at minimum tick size ₹0.05 (`MIN_TICK_SIZE = Decimal("0.05")` documented as a fail-closed conservative modelling floor per Finding N-80). Effective stop distance is recomputed after tick floor ($entry\_price - stop\_loss\_price$) so `risk_amount` strictly equals actual loss at `stop_loss_price`, and sub-tick entries ($entry\_price \le ₹0.05$) fail closed (Finding H-77).
  - Returns immutable `PositionSizeResult` tracking exact integer shares, INR risk amount, position weight, and binding constraint (`RISK_BUDGET`, `MAX_POSITION_WEIGHT`, `AVAILABLE_CASH`, `VOLUME_PARTICIPATION`).
- **Point-in-Time Liquid EQ Universe Schedule Builder (`src/signal_core/research/pit_universe.py`)**:
  - Parameter validation: strictly requires `turnover_lookback_sessions >= 1` (rejecting 0, negative values, and bool fail-closed, Finding N-76) and `top_liquid_k >= 1` if provided (rejecting 0, negative values, and bool fail-closed, Finding N-77).
  - Constructs `UniverseSchedule` strictly from half-open intervals `[effective_from, effective_to)` in `data/reference/cash_equity_symbol_intervals.csv`.
  - Refuses static Nifty 500 constituent lists fail-closed with `UniverseValidationError` per §56.5; docstring notes `requested_index_name` as a tripwire (Finding N-72).
  - Rejects dates absent from authoritative anchored NSE trading calendar (e.g. Saturdays) fail-closed (Finding H-79).
  - Lookback coverage enforcement (Finding H-81): requires complete lookback coverage across all `turnover_lookback_sessions` prior calendar sessions. If any prior lookback session is absent from `daily_turnover_inr`, raises `UniverseValidationError` naming the missing session(s) fail-closed. Over the 1,196 binding sessions (2022-01-03..2026-10-30), exactly 0 sessions silently emit empty cross-sections; all 40 incomplete sessions raise fail-closed, and all 1,156 complete sessions emit members successfully.
  - Distinguishes missing turnover records from genuine `Decimal("0.0")` turnover, excluding instruments with missing records under named reason `MISSING_TURNOVER_RECORD` and recording reasons on `UniverseSchedule` (Finding N-71).
  - Finding N-82 Remediation: When an emitted cross-section is empty and all active candidates were excluded for `MISSING_TURNOVER_RECORD`, raises `UniverseValidationError` fail-closed; genuine computed empty cross-sections (where all candidates fail turnover liquidity under `BELOW_MIN_MEDIAN_TURNOVER`) emit valid 0-member results with recorded reasons (§59.7 Item 5).
  - Preserves primary identity as ISIN (AGENTS.md Rule 10.4).
- **Unit Test Suite (`tests/unit/test_phase3a_sizing_and_universe.py`)**: 21 passing tests covering sizer constraints, boundary conditions, criteria defaults, calendar validation, lookahead elimination, N-82 empty cross-section data-omission distinction, and H-81 complete lookback enforcement across all 1,196 real Bhavcopy archives.

### Phase 3B-1: ATR Sizing Intent Wiring & Daily T+1 Order Runner (Signed Off for Full BUY/SELL Scope per §61.4 at `4d81077`, audit commit `b4a3baf`)
Module: `src/signal_core/execution/order_runner.py`. Contract helper: `OrderIntent.from_position_size_result` in `src/signal_core/contracts/order_intent.py` & re-exported in `src/signal_core/strategy/base.py`. Tests: `tests/unit/test_phase3b1_order_runner.py`.

- **Audit §61 Sign-Off & Verdicts**: Audited in §61 at commit `4d81077` (audit commit `b4a3baf`).
  - Phase 3B-1 signed off — GO for full BUY/SELL scope per §61.4.
  - Phase 3B-2a signed off — GO (strategy contract, trial registry, synthetic fixture plumbing).
  - Full-corpus Phase 3B-2b walk-forward strategy runs held on §61.6 items: H-89, H-90, N-92, N-93, N-94, N-95.
- **Remediations in `feat-s59` (audited & confirmed in §60)**:
  1. *Finding H-82 (Mandatory Exchange Series Evidence)*: Removed default `series="EQ"` from `DailySignalCandidate` (must be explicitly provided). In `DailyTPlus1OrderRunner.execute_ticket`, running a bare `PriceBar` without `explicit_series` raises `OrderRunnerEligibilityError` fail-closed; `ExchangeSessionObservation` carrying `ExchangeSeries.BE` is strictly rejected.
  2. *Finding H-83 (Mandatory Price Band / Circuit Evidence)*: `price_band` is mandatory on BUY entries. Omitting `price_band` (`price_band is None`) raises `OrderRunnerEligibilityError` fail-closed.
  3. *Finding H-84 (Realised Risk on Execution Ticket)*: Added `realised_risk: Optional[Decimal]` to `DailyExecutionTicket`, computed on fill as $quantity \times (executed\_price - stop\_price)$ to record actual risk past the reference price on overnight gap opens (e.g. 10% gap evaluates to ₹15,044.89 vs ₹10,000.00 intended).
  4. *Finding N-83 (Module-Scope Imports & Type Hints)*: Imported `GoNoGoCriteria` and `Portfolio` at module scope; eliminated circular imports; verified `typing.get_type_hints` on `DailyTPlus1OrderRunner.__init__` and `.run_candidate` resolve cleanly with zero `NameError`.
  5. *Finding N-84 (Named No-Trade on Zero-Size Result)*: When sizer returns `quantity == 0`, runner emits a named no-trade ticket (`is_no_trade=True`, `no_trade_reason="ZERO_QUANTITY_SIZED"`), avoiding leakage of `OrderIntentValidationError`.
  6. *Finding N-85 (Guard Docstrings Alignment)*: Corrected docstrings in `scripts/generate_phase2d_tier_a_report.py` and `scripts/verify_phase2d_verdicts.py` to accurately document runtime type guards and AST layer helper indirection limitations.
  7. *Finding N-86 (Status Claims Citation Accuracy)*: Corrected CSOW headers and citations to reflect §58 and §59 verdicts strictly without premature sign-off claims.
  8. *Mid-Hold Corporate Actions (§13.2)*: Committed `data/reference/corporate_actions.jsonl` with honest unverified provenance notes (H-88). Implemented `Position.apply_corporate_action` (1:2 split preserves total equity invariant at ₹9,99,876.00 with zero fabricated MTM loss), `CashLedger.record_dividend` posting `CashEntryType.DIVIDEND_INFLOW`, and `Portfolio.apply_corporate_action(s)`.
  9. *Surveillance Stage Exit Constraints (§5.2, §10.8)*: Committed `data/reference/surveillance_intervals.jsonl` with synthetic fixture annotations (H-87). Implemented `DailyTPlus1OrderRunner.evaluate_surveillance_exit_constraints(session_date, security_master)` enforcing exit constraints during holding periods.
  10. *Phase 3B-2a Synthetic Strategy Contract & Verdict Plumbing (§59.7 Item 8)*: Implemented `DeliverySwingTrendStrategy` (`src/signal_core/strategy/swing.py`) conforming to `APPROVED_EQ_ONLY_POLICY`. Proved trial is logged to `TrialRegistry` before Sharpe is readable, `evaluate_verdicts()` evaluates honestly to `NO-GO` on unverified provenance, and touching sealed holdout dates (2025–2026) fails closed with `HoldoutSealedError`.
- **Remediations in `feat-s60` (addressing §60.7 items 1–9)**:
  1. *Finding H-85 (Mandatory Price Band on SELL Exits & T+1 No-Trade Target Date)*: In `DailyTPlus1OrderRunner`, `price_band` is mandatory on SELL exits as well as BUY; `price_band is None` raises `OrderRunnerEligibilityError` fail-closed, preventing fills into lower circuit freezes. Zero-quantity no-trade ticket advances `target_date` to session $T+1$ via `advance_sessions(candidate.signal_date, 1)`.
  2. *Finding H-86 (ISIN Transition Re-Keying in Portfolio & Position)*: In `Position.apply_corporate_action`, isolated `CorporateActionType.ISIN_TRANSITION`: updates `self._instrument_id = action.new_isin`, leaving share count, average entry price, and total cost basis strictly invariant. In `Portfolio.apply_corporate_action`, re-keys the position in `self._positions` from old ISIN to new ISIN, enabling the held security to be sold under its new identity.
  3. *Finding N-87 (Non-Integral Restatements in Corporate Actions)*: In `Position.apply_corporate_action`, fractional restatements for `SPLIT`, `BONUS`, and `CONSOLIDATION` raise `CorporateActionError` fail-closed if `new_quantity` has a non-zero fractional part, preventing silent truncation.
  4. *Findings H-87 & H-88 (Surveillance Coverage, Circular Reference & Manifest Registration)*:
     - Added `circular_ref: Optional[str] = None` to `SurveillanceInterval` contract and loader.
     - In `load_surveillance_intervals` and `load_corporate_actions`: missing reference file raises `FileNotFoundError` fail-closed.
     - In `SecurityMaster`: added `has_surveillance_coverage(isin, as_of)`, `surveillance_coverage_count`, and `validate_hold_surveillance_coverage(isin, as_of)` which raises `SecurityMasterError` fail-closed when surveillance coverage is missing for a held position.
     - In `build_production_security_master`: filters out rows carrying `"SYNTHETIC_FIXTURE"`; returns honest `surveillance_coverage_count == 0` for real universe ISINs until authentic surveillance table is ingested.
     - Registered `data/reference/surveillance_intervals.jsonl` and `data/reference/corporate_actions.jsonl` in `data/reference/manifest.jsonl` with active status, byte counts, sha256 digests, and honest provenance `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`.
     - Updated manifest fingerprint pin in `configs/go_no_go_criteria.yaml` and recomputed Tier-A report with `scripts/generate_phase2d_tier_a_report.py`.
  5. *Finding N-88 (Weekly Call Auction Session Resolution for GSM Stage 2+)*: Implemented `is_weekly_surveillance_trading_session(session_date, calendar)` ensuring exits under GSM Stage 2+ fire strictly on the earliest trading session of the week (typically Monday). In `DailyTPlus1OrderRunner.evaluate_surveillance_exit_constraints`: fails closed with `SecurityMasterError` if a held position lacks surveillance coverage; derives exit candidate parameters dynamically from `security_master` and market rather than sentinels.
  6. *Findings N-89 & N-90 (Strategy Execution Harness & Eager Exports)*: Restored eager exports of `DailyTPlus1OrderRunner`, `DailySignalCandidate`, and `DailyExecutionTicket` in `signal_core.execution.__init__.__all__` and module scope (`'DailyTPlus1OrderRunner' in dir(signal_core.execution)` is True). Implemented `execute_swing_strategy_session` harness routing strategy intents through position sizing into `DailyTPlus1OrderRunner`, filtering out unheld SELL signals.
  7. *Finding N-91 (Status Claims Corrections)*: Corrected CSOW status claims for corporate actions, surveillance intervals, and 9 verification scripts.
- **Remediations in `feat-s61` (addressing §61.6 work order items 1–8)**:
  1. *Finding H-89 (Apply Share Ratio & Re-Key Position on `ISIN_TRANSITION`)*: In `Position.apply_corporate_action`, when `action_type == CorporateActionType.ISIN_TRANSITION` carries a ratio, applies `multiplier = ratio_numerator / ratio_denominator`, validates non-integral entitlement fail-closed with `CorporateActionError`, restates `self._quantity` and `self._average_entry_price` with constant cost basis, and updates `self._instrument_id = action.new_isin`. In `Portfolio.apply_corporate_action`, re-keys `self._positions` from old ISIN to new ISIN. Proved via acceptance probe: Cochin Shipyard 2:1 transition on 25 shares of `INE704P01017` (entry ₹1605.60) yields 50 shares of `INE704P01025` (entry ₹802.80); total cost basis remains exactly ₹40,140.00; old ISIN is None; marking pre/post transition gives identical equity; 1:1 transition leaves quantity unchanged.
  2. *Finding H-90 (Clean Import Graph Without Cycles or Monkey-Patching)*: Extracted `OrderIntent`, `LookaheadIntentError`, and `OrderIntentValidationError` into `src/signal_core/contracts/order_intent.py`; re-exported them in `src/signal_core/strategy/base.py` and imported directly in `src/signal_core/execution/order_runner.py`, eliminating `execution`'s dependency on `strategy` at module load time. In `src/signal_core/execution/__init__.py`, used PEP 562 lazy `__getattr__` and `__dir__` so `'DailyTPlus1OrderRunner' in dir(signal_core.execution)` resolves cleanly. Removed `except ImportError: Portfolio = None` and removed bottom monkey-patch in `src/signal_core/portfolio/portfolio.py`. Fresh interpreter subprocess imports of `signal_core.strategy.swing`, `signal_core.strategy.base`, `signal_core.strategy`, and `signal_core.execution` all exit 0.
  3. *Finding N-92 (Date-Bounded Surveillance Coverage per Session)*: In `SecurityMaster.has_surveillance_coverage(isin, as_of)`, made coverage a per-session property honoring `as_of` date (`any(s.isin == isin and s.contains(as_of) for s in self._surveillance_intervals)`); dates outside every interval return `False`. In `DailyTPlus1OrderRunner.evaluate_surveillance_exit_constraints(session_date, security_master, require_coverage=False)`, held position without coverage fails closed with `SecurityMasterError`; `require_coverage=True` raises fail-closed when coverage count is 0.
  4. *Finding N-93 (Structured Skip Reasons in Strategy Execution Harness)*: Defined `SwingSessionExecutionSummary` tracking `as_of`, `next_session`, `intents_generated`, `tickets_executed`, `skipped_missing_bar`, `skipped_missing_band`, `skipped_unheld_sell`, `skipped_already_held`, `skipped_missing_features`, and `tickets`. In `execute_swing_strategy_session`, replaced silent `continue` with counted skips returned to caller.
  5. *Finding N-94 (Position Sizing Allocation Weight Cap)*: Added `allocation_weight: Optional[Decimal] = None` to `DailySignalCandidate` with finite `(0, 1]` validation. In `DailyTPlus1OrderRunner.generate_order_intent`, caps `max_single_position_weight = min(candidate.allocation_weight, criteria.max_single_position_weight)` so declared parameter actively limits sizing. In `execute_swing_strategy_session`, forwards `allocation_weight` to candidate.
  6. *Finding N-95 (Fill Price Quantization to Indian Tick Grid)*: Implemented `quantize_to_tick_grid(price)` in `src/signal_core/execution/simulator.py`: prices $\ge ₹1.00$ quantize to ₹0.05 tick grid (ROUND_HALF_UP) and prices $< ₹1.00$ quantize to ₹0.01 tick grid. In `ExecutionFillSimulator`, added `quantize_to_tick: bool = True` to `__init__` and `simulate_order`, re-bounding against effective upper/lower circuits after quantization.
- **Audit §62 Verdicts (at commit `e66f2aa`, audit commit `605ed7c`, tag `audit-s62-605ed7cc`)**:
  - Phase 2D Tier-A gating: NO-GO (unchanged, 3 PASS / 0 FAIL / 20 NOT RUN, `CRIT-PROV-01` NOT RUN).
  - Phase 3B-1: GO stands per §62.4.
  - Phase 3B-2a: GO stands per §62.4.
  - Phase 3B-2b full-corpus walk-forward runs: NOT AUTHORIZED at `e66f2aa` pending §62.6 items.
- **Remediations in `feat-s62` (addressing §62.6 work order items 1–8)**:
  1. *Finding H-96 (Unconditional Position Re-Keying on `new_isin` across `SPLIT`, `BONUS`, `CONSOLIDATION`)*: In `Position.apply_corporate_action`, unconditionally updates `self._instrument_id = action.new_isin` for all restatement action types when `action.new_isin` is present. In `Portfolio.apply_corporate_action`, deletes `old_isin` and registers `new_isin` in `self._positions`, raising `CorporateActionError` fail-closed if target ISIN already has an active position. In `CorporateAction.__post_init__`, rejects `new_isin == isin` with `SecurityMasterError`. Verified: 25 shares split 2:1 with `new_isin="INE704P01025"` leaves `get_position(old_isin) is None` and `get_position(new_isin).quantity == 50`.
  2. *Finding H-97 (Round-Then-Clamp & Contradictory Band Refusal)*: In `ExecutionFillSimulator.simulate_order`, circuit freeze rejections (BUY at or above upper circuit -> `REJECTED_UPPER_CIRCUIT`; SELL at or below lower circuit -> `REJECTED_LOWER_CIRCUIT`) are evaluated first. Inverted bands (`effective_lower > effective_upper`), bar range contradictions (`high > upper + 0.05` or `low < lower - 0.05`), and out-of-band opens (`open > upper` or `open < lower`) return `REJECTED_PRICE_LIMIT` with `executed_price=None` (zero fill, zero rewriting). For valid fills, unconstrained price is quantized to the Indian tick grid first, then clamped to session printed bounds `[min_sell_price, max_buy_price]`. Proved: 100 randomized opens between grid points satisfy `low <= price <= high` and `price % 0.05 == 0.00`; contradictory band (`open=99.99, high=100.02, band 1560/1040`) returns `REJECTED_PRICE_LIMIT` with `executed_price=None`.
  3. *Finding N-92 Remainder (Three-State Surveillance Coverage & Exit Results)*: Added `SurveillanceStage.NORMAL = "NORMAL"` to `security_master.py`. In `SecurityMaster`, `has_surveillance_coverage(isin, as_of)` returns True inside verified intervals (including NORMAL) and False outside. In `DailyTPlus1OrderRunner`, defined `SurveillanceExitResult(tuple)` carrying `session_date`, `status`, `coverage_complete`, `reason`. `evaluate_surveillance_exit_constraints(..., require_coverage=True)` returns a `SurveillanceExitResult` on an ordinary hold rather than raising.
  4. *Finding CA-1 (Corporate Actions Corpus Covering All Action Types)*: Delivered 21 corporate actions in `data/reference/corporate_actions.jsonl` covering all 7 action types (`SPLIT`, `BONUS`, `CONSOLIDATION`, `DIVIDEND`, `RIGHTS`, `ISIN_TRANSITION`, `DELISTING`) with honest unverified provenance. Supported `RIGHTS` and `DELISTING` in `Position.apply_corporate_action` and `Portfolio.apply_corporate_action`. In `SecurityMaster`, added `has_corporate_action_coverage(isin)` and `require_registration` parameter to `get_corporate_actions` to distinguish registered names from unregistered names fail-closed. Updated `manifest.jsonl` entry and `expected_manifest_fingerprint` in `configs/go_no_go_criteria.yaml`.
  5. *Finding CA-2 (Surveillance Explicit NOT RUN Path & `CRIT-SURV-01` Propagation)*: In `src/signal_core/reporting/verdicts.py`, added `CRIT-SURV-01` evaluating surveillance status from results bundle; when unverified or not run, evaluates as `NOT RUN` keeping overall verdict `NO-GO`.
  6. *Finding N-97 (Execution Summary Ticket Counts Separation)*: In `SwingSessionExecutionSummary` (`src/signal_core/strategy/swing.py`), separated counts into `tickets_emitted`, `tickets_filled`, `tickets_rejected`, and `tickets_no_trade`; mapped `tickets_executed = tickets_filled` for backwards compatibility. Added `@property def status` on `DailyExecutionTicket`. Proved: upper freeze session yields `tickets_emitted = 1`, `tickets_filled = 0`, `tickets_rejected = 1`, `tickets_no_trade = 0`.
  7. *Finding N-98 (Exact Assertions Restored)*: In `tests/unit/test_phase3b1_order_runner.py`, restored single exact measured values at line 533 (`ticket.realised_risk == Decimal("15045.00")`) and line 700 (`pos.total_cost_basis == Decimal("50040.00")`), and updated line 636 docstring citing ₹9,99,876.81.
  8. *Finding R-90a (Clean Contracts Import Layering & Eager Exports)*: Created `src/signal_core/contracts/order_types.py` holding `OrderSide`, `OrderProduct`, `OrderType`, `FillStatus`, `ExecutionOrderValidationError`, `ExecutionOrder`, and `ExecutionFillResult`. Contracts layer is stdlib-pure and imports zero execution modules. `portfolio.ledger`, `portfolio.portfolio`, and `portfolio.position` import order contracts from `contracts.order_types`, eliminating circular imports completely. Removed PEP 562 lazy shim from `src/signal_core/execution/__init__.py`. Eager imports of `signal_core.strategy.swing`, `signal_core.strategy.base`, `signal_core.strategy`, and `signal_core.execution` all exit 0 in fresh interpreter subprocesses.
- **Unit Test Suites**:
  - `tests/unit/test_phase3b1_order_runner.py`: 28 passing tests (100% pass rate).
  - `tests/unit/test_phase3b2_audit_s62_items.py`: 11 passing tests (100% pass rate).
  - `tests/unit/test_phase3b2_audit_s63_items.py`: 11 passing tests (100% pass rate).
  - Full suite: **381 passed in 49.86s**; all 8 verification scripts exit 0; zero skips, zero xfails.

### Phase 3B-2: Walk-Forward Strategy Runs & Audit §63 Remediation (Implemented in feat-s63; Awaiting Audit Review)
- **Audit §63 Verdicts (at commit `396f825`, audit commit `80a1997`, tag `audit-s63-80a1997a`)**:
  - Phase 2D Tier-A gating: NO-GO (unchanged, 3 PASS / 0 FAIL / 20 NOT RUN, `CRIT-PROV-01` NOT RUN).
  - Phase 3B-1: GO stands per §63.4.
  - Phase 3B-2a: GO stands per §63.4.
  - Phase 3B-2b full-corpus walk-forward evaluations: NOT AUTHORIZED at `396f825` (§63.4, §63.7); §63.6 ordered items (H-98..H-101, N-92 remainder, CA-3, CA-1, N-99, R-97, N-100) required before authorization.
- **Remediations in `feat-s63` (addressing §63.6 work order items 1–10)**:
  1. *Finding H-98 (Merger & Delisting Consideration Modeling)*:
     - In `CorporateActionType`, added `MERGER = "MERGER"`; in `CorporateAction`, added `delisting_price: Optional[Decimal] = None`.
     - In `Position.apply_corporate_action`: handled `CorporateActionType.MERGER` with exact integer rational restatement; implemented `Position.close_delisting(delisting_price)` calculating realized gross and net PnL, zeroing shares, and returning `(proceeds, net_pnl)`.
     - In `Portfolio.apply_corporate_action`: handled `MERGER` (e.g. 42:25 for HDFC into HDFCBANK: 25 HDFC shares restate to 42 HDFCBANK shares with basis preserved at ₹70,000.00, old key deleted); handled `DELISTING` without `new_isin` by depositing proceeds into `CashLedger` at `delisting_price` (or `average_entry_price`) via `CashLedger.record_delisting_settlement(amount, reference_id)`, leaving portfolio equity strictly invariant (`equity_after == equity_before`).
  2. *Finding H-99 (Exact Rational Integer Restatement & Rights Semantics)*:
     - In `Position.apply_corporate_action`, replaced floating/decimal division with exact integer divisibility: `rem = (self._quantity * num) % den`. If `rem != 0`, fails closed with `CorporateActionError`; if `rem == 0`, calculates exact new quantity as `(self._quantity * num) // den`. 14 shares × 15/14 evaluates to exactly 15 shares with zero decimal expansion distortion.
     - RIGHTS action handling: rights entitlement grants the right to subscribe at an issue price; holding through rights ex-date leaves position quantity and cost basis strictly unchanged, preventing false bonus share fabrication without cash outflow.
  3. *Finding H-100 (Corporate Actions Applied Inside Session Driver)*:
     - In `execute_swing_strategy_session` (`src/signal_core/strategy/swing.py`), added `corporate_actions: Optional[Sequence[Any]] = None`. Applies `runner.portfolio.apply_corporate_actions_for_session(next_session, corporate_actions)` before session pricing and signal execution.
     - Added `corporate_action_entries: Tuple[Any, ...]` to `SwingSessionExecutionSummary`. Verified on full-session ex-dividend: INFY ₹20.00 dividend is deposited into `CashLedger` and recorded on summary.
  4. *Finding H-101 (Surveillance Explicit NOT RUN Verdict Path from Driver)*:
     - In `execute_swing_strategy_session`, added `security_master: Optional[Any] = None`; evaluates `runner.evaluate_surveillance_exit_constraints` on `next_session` and stores result in `SwingSessionExecutionSummary.surveillance_result`.
     - In `SwingSessionExecutionSummary`, implemented `to_verdict_results_bundle(runner=...)` exporting `surveillance_exit_constraints_enforced`, `surveillance_constraint_status`, and `surveillance_not_run_reason` into the results bundle. When surveillance is unverified, `evaluate_verdicts()` reads the bundle, evaluates `CRIT-SURV-01` as `NOT RUN`, and returns `overall_verdict: NO-GO`.
     - In `DailyTPlus1OrderRunner`, implemented `populate_surveillance_verdict_bundle(bundle)` reading `self.last_surveillance_result`.
  5. *Finding N-92 Remainder (Surveillance Gated Strictly Per Held Name)*:
     - In `DailyTPlus1OrderRunner.evaluate_surveillance_exit_constraints`: gates strictly on whether held positions have surveillance coverage (`uncovered_held`), rather than universe-wide count (`surveillance_coverage_count == 0`).
     - Configuration A (held name covered with explicit NORMAL interval, zero symbol intervals registered in master) evaluates cleanly (`status="RUN"`, `coverage_complete=True`, 0 exits).
     - Configuration C (held name uncovered) raises `SecurityMasterError` fail-closed.
  6. *Finding CA-3 (Price Bands for Registered 2022-2024 Cash Universe)*:
     - Implemented `load_cash_universe_price_band_intervals()` in `src/signal_core/storage/security_master.py`: loads 3,127 price band intervals covering the cash universe scrips from `sec_list_20240116.csv` mapped to ISINs via `cash_equity_symbol_intervals.csv` resolved point-in-time as of 2024-01-16.
     - F&O dynamic flexing bands ('No Band') are mapped to `is_unconstrained=True` strictly for names listed in `NSE/FAOP/60350`.
     - Static cash equity bands (20%, 10%, 5%, 2%) are preserved with exact `band_percentage`.
     - Non-core names (e.g. TCS `INE467B01029`, 20MICRONS `INE144J01027`) resolve valid `PriceBandRecord`s with derived upper and lower circuit limits.
  7. *Finding CA-1 (Corporate Actions Corpus Covering Traded Universe)*:
     - Implemented `scripts/derive_2022_2024_corpora.py` generating 164 corporate actions across 64 ISINs in `data/reference/corporate_actions.jsonl` covering all 8 action types (`SPLIT`, `BONUS`, `CONSOLIDATION`, `DIVIDEND`, `RIGHTS`, `ISIN_TRANSITION`, `DELISTING`, `MERGER`) across 2022, 2023, and 2024 with honest `CONTENT_IDENTIFIED_ONLY` and `UNATTESTED_...` references.
     - Updated `data/reference/manifest.jsonl` row for `corporate_actions.jsonl` (`byte_count: 54276`, `sha256: "ba0057c9e4409a63d9ffdb2dc9036d4575d12ced04b31496d5eaf5a4891b559d"`).
     - Recomputed manifest fingerprint pin in `configs/go_no_go_criteria.yaml` (`MAN-FPR-V1-78bf1bf559c07cc5f5856f1c824eb4c7042f5050b5547ee373c893e5ee2b54d9`).
     - Regenerated Tier-A report with `scripts/generate_phase2d_tier_a_report.py` (`PASS=3, FAIL=0, NOT_RUN=20`, `overall_verdict: NO-GO`).
  8. *Finding N-99 (Driver-Level Test Probes)*:
     - In `tests/unit/test_phase3b2_audit_s62_items.py`, rewrote `test_n97_summary_ticket_counts_separation_on_circuit_freeze` to drive through `execute_swing_strategy_session` rather than manual summary construction; verified `tickets_emitted == 1`, `tickets_filled == 0`, `tickets_rejected == 1`, `tickets_executed == 0`, `tickets_no_trade == 0`, `ticket.status == REJECTED_UPPER_CIRCUIT`.
     - Corrected `test_ca1_corporate_actions_corpus_and_sampled_types` docstring and added assertions for `RIGHTS` (shares unchanged), `MERGER` (42 shares, basis preserved), and `DELISTING` (settlement proceeds, equity continuous).
  9. *Finding R-97 (Interior Tick Grid Clamping)*:
     - In `quantize_to_tick_grid` and `ExecutionFillSimulator.simulate_order`, clamped execution prices toward the interior (`ROUND_FLOOR` for BUY upper limit, `ROUND_CEILING` for SELL lower limit) so off-grid boundary bars (`high=100.03` for BUY, `low=99.97` for SELL) never produce off-grid fill prices; fill prices unconditionally lie on the tick grid and inside `[low, high]`.
  10. *Finding N-100 (Typed Protocols on Execution Fill Result)*:
      - In `src/signal_core/contracts/order_types.py`, defined runtime-checkable `SlippageResultProtocol` and `TransactionCostBreakdownProtocol`.
      - Updated `ExecutionFillResult` to type `slippage: Optional[SlippageResultProtocol]` and `costs: Optional[TransactionCostBreakdownProtocol]` without introducing circular `contracts -> execution` dependencies.
- **Unit Test Suites**:
  - `tests/unit/test_phase3b1_order_runner.py`: 28 passing tests (100% pass rate).
  - `tests/unit/test_phase3b2_audit_s62_items.py`: 11 passing tests (100% pass rate).
  - `tests/unit/test_phase3b2_audit_s63_items.py`: 11 passing tests (100% pass rate).
  - `tests/unit/test_phase3b2_walkforward_runner.py`: 4 passing tests (100% pass rate).
  - Full suite: **385 passed in 76.25s**; all 8 verification scripts exit 0; zero skips, zero xfails.
- **Status**: Phase 3B-1 — GO stands per §63.4; Phase 3B-2a — GO stands per §63.4. §63.6 ordered items (H-98..H-101, N-92 remainder, CA-3, CA-1, N-99, R-97, N-100) committed in `f1844c5` (`feat-s63-f1844c5`).

### Phase 3B-2b: Authoritative 2022–2024 Walk-Forward Baseline Runner & Consumer (Delivered)
- **Delivered Deliverables & Architecture**:
  1. *End-to-End Walk-Forward Consumer Script* ([`scripts/run_phase3b2_walkforward.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/run_phase3b2_walkforward.py)):
     - Loads authoritative `GoNoGoCriteria` and anchored NSE trading calendar (Finding R-6).
     - Enforces physical & cryptographic Holdout refusal (`2025-01-01..2026-11-11` strictly sealed; any access or evaluation attempt raises `HoldoutSealedError` fail-closed per AGENTS.md Rule 8.1).
     - Builds production `SecurityMaster` with 3,127 cash universe price band intervals (Finding CA-3) and 164 corporate action events across 2022–2024 (Finding CA-1).
     - Loads historical snapshot (`historical_dev_dataset_2022_2024.json`), maps 211 UUIDs to authentic ISINs with verified effective-dated intervals (including Cochin Shipyard pre-split `INE704P01017` up to 2024-01-09 and post-split `INE704P01025` from 2024-01-10 onwards).
     - Constructs point-in-time liquid `EQ` universe schedule strictly over 2022-01-03..2024-12-31 without survivorship bias or lookahead (AGENTS.md §6.1).
     - Precomputes technical features via `SubsegmentIndicatorEngine.compute_standard_features_for_instrument` with zero cross-gap leakage (Finding F-12).
     - Configures canonical walk-forward folds: Fold 0 (In-Sample: 2022-01-03..2023-12-29), Fold 1 (Validation: 2024-01-01..2024-12-31).
     - Instantiates the single authoritative execution engine (`DailyTPlus1OrderRunner`, `ExecutionFillSimulator`, `Portfolio`) and strategy `DeliverySwingTrendStrategy` (`sma_20`/`sma_50` trend breakout, 5% allocation weight, 2.0x ATR stop).
     - Executes session-by-session across all 743 sessions: applies corporate actions on ex-dates (`runner.portfolio.apply_corporate_actions_for_session`, Finding H-100), evaluates surveillance exit constraints (`runner.evaluate_surveillance_exit_constraints`, Finding H-101), and tracks execution counters (`tickets_emitted`, `tickets_filled`, `tickets_rejected`, `skipped_missing_band`, `skipped_missing_bar`, Findings N-93, N-97).
     - **TrialRegistry Append-Before-Read Invariant (Rule 3.2, §8.2)**: Trial record `TRIAL-PHASE3B2-SWING-BASELINE-001` is appended to `data/trials/trial_registry.jsonl` BEFORE reading or calculating performance metrics (`sharpe_ratio=None` on initial write).
     - **Exact Decimal Performance Diagnostics (§6.4)**:
       * Initial Capital: ₹1,000,000.00
       * Final Equity: ₹1,316,560.58
       * CAGR: **9.70%**
       * Total Closed Trades: **621**
       * Win Rate: **21.26%**
       * Profit Factor: **1.6297**
       * Max Portfolio Drawdown: **23.80%**
       * Mean Realized R: **-0.9631R**
       * Total Statutory Costs: **₹76,167.48**
       * Annualized Sharpe: **0.9618**
       * Deflated Sharpe Ratio (DSR): **0.9390**
       * Haircut Sharpe Ratio: **0.9618**
     - **Automated Verdict Evaluation (AGENTS.md §9.1, §9.3)**:
       * Evaluates trial through `evaluate_verdicts()` against committed `go_no_go_criteria.yaml`.
       * Emits candidate reports: [`reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.json`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.json) and [`reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.md).
       * Computed verdicts: `PASS=16`, `FAIL=0`, `NOT RUN=8`.
       * **Honest Fail-Closed Verdicts**: `CRIT-SURV-01: NOT RUN` (surveillance table unverified per Rule 10.8), `CRIT-PROV-01: NOT RUN` (historical archive source unverified per Rule 6.5).
       * Overall Verdict: **Strictly `NO-GO`**.
  2. *Focused Unit & Integration Test Suite* ([`tests/unit/test_phase3b2_walkforward_runner.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_phase3b2_walkforward_runner.py)):
     - `test_walkforward_runner_end_to_end`: Verifies end-to-end execution of `run_phase3b2_walkforward`, session counters, exact Decimal diagnostics, and verdict report emission.
     - `test_trial_registry_append_before_read_ordering`: Asserts that `TrialRegistry` appends the trial record before any performance metrics are readable (`sharpe_ratio=None` on disk in registry line).
     - `test_holdout_partition_sealed_refusal`: Proves that accessing holdout without human `HOLDOUT_UNLOCK` or attempting to evaluate dates $\ge$ 2025-01-01 raises `HoldoutSealedError`.
     - `test_verdict_propagation_crit_surv_not_run_and_nogo`: Verifies that `CRIT-SURV-01` and `CRIT-PROV-01` evaluate to `NOT RUN` and propagate to an honest `NO-GO` overall verdict.
  3. *Clean-Checkout CI Reproducibility & Self-Contained Unit Tests*:
     - Made `tests/unit/test_phase3b2_walkforward_runner.py` completely self-contained via `make_synthetic_snapshot` (generating 60 sessions for authentic liquid symbols INFY, TCS, RELIANCE in `tmp_path`), eliminating dependency on gitignored `historical_dev_dataset_2022_2024.json` so all 4 tests pass in ~1.44s on clean CI clones.
     - Updated `src/signal_core/loaders/historical_snapshot.py` to transparently detect and decompress `.json.gz` archives if uncompressed `.json` is absent on disk.
     - Updated `scripts/run_phase3b2_walkforward.py` (`resolve_or_build_historical_dataset`) so that if `historical_dev_dataset_2022_2024.json` is missing on a clean checkout, it automatically decompresses committed `historical_dev_dataset_2022_2024.json.gz` or falls back to in-memory construction from committed `data/raw/2022`..`2024` Bhavcopy archives (< 2025-01-01, strictly preserving Holdout sealing).
     - Fixed `SecurityMaster.registered_isins` set lookup in `scripts/run_phase3b2_walkforward.py`.
- **Verification & Sign-off Status**:
  - Full test suite: **385 passed in 35.89s** with 0 skipped and 0 xfailed.
  - `python scripts/verify_audit_append_only.py` passes 100% across all 4 gates (W0.5-1..W0.5-4) with all 8 verification scripts passing exit 0.
  - All audit citations verified against §63 (`80a1997`) and `feat-s63-f1844c5`. Ready for DeepSeek audit review of Phase 3B-2b.

### Phase 3B-2b Remediation & Authorized Baseline Re-Run (§64 Audit Review at `817c2ba`)
Following DeepSeek's §64 audit review (commit `817c2ba`, tag `audit-s64-817c2ba4`), which signed off on the runner's deterministic execution while holding strategy-metric certification and authorizing ONE baseline re-execution logged as a new `TrialRegistry` entry, all §64 ordered findings were implemented and verified:
1. *Finding H-104 (Zero Hardcoded Bundle Literals & Computed Engine Telemetry)*:
   - In `scripts/run_phase3b2_walkforward.py` and `SwingSessionExecutionSummary.to_verdict_results_bundle()`, eliminated all hardcoded `True`, `100.00`, and echoed criteria literals (`fail_closed_on_unexplained_gaps`, `zero_data_fabrication`, `statutory_costs_enforced`, `prohibit_buy_at_upper_circuit`, `prohibit_sell_at_lower_circuit`, `min_daily_turnover_crore`, `max_volume_participation`).
   - Slices bars to executed session window and calls `SubsegmentIndicatorEngine.compute_standard_features_for_instrument` with `fail_closed_on_unexplained=True`, catching `IndicatorValidationError` fail-closed for uncontinuous series (verified `CRIT-DATA-02: PASS`).
   - Derived execution invariants directly from executed fills and price bands via `all_fills_with_bands`.
2. *Finding H-102 (Observed Max Single-Position Weight from Mark-to-Market Snapshots)*:
   - In `DailyTPlus1OrderRunner`, evaluates concentration limits against current mark-to-market equity (`latest_market_prices`).
   - In `run_phase3b2_walkforward.py`, computes `max_single_position_weight` as the maximum `position.market_value / snapshot.total_portfolio_value` observed across all session snapshots (observed as `0.1130` in the baseline run, honestly failing `CRIT-STAT-03` whose threshold is `0.10`).
3. *Finding H-103 (Single Consistent Mark-to-Market Equity Basis & Per-Fold Walk-Forward Metrics)*:
   - Evaluates `final_equity`, total return, and CAGR strictly on the exact same mark-to-market valuation basis (`portfolio.snapshots[-1].total_portfolio_value`) used for `max_drawdown`, eliminating book-cost ending valuation.
   - Computes and reports distinct In-Sample (2022–2023) and Validation (2024) fold metrics alongside full-window metrics so `WalkForwardFold` objects govern real out-of-sample evaluation.
4. *Finding H-105 (Inverted Holdout Guard Fixed)*:
   - Fixed the inverted `try / except HoldoutSealedError` check in `scripts/run_phase3b2_walkforward.py`: verifies that calling `check_partition_access(partition_spec, PartitionRole.HOLDOUT)` raises `HoldoutSealedError`, and aborts fail-closed if holdout access is ever granted without human `HOLDOUT_UNLOCK`.
   - Asserts `max(dataset.trading_dates) < partition_spec.holdout_start` on any loaded snapshot.
5. *Finding H-106 & CA-3 (Elimination of Back-Dated Static Bands, Invented 20% Bands & Unbounded F&O Fills)*:
   - In `src/signal_core/storage/security_master.py` (`load_cash_universe_price_band_intervals`), set `effective_from = datetime.date(2024, 1, 16)` for `sec_list_20240116.csv` (eliminating backdating to 2022-01-01) and deleted the loop fabricating 20% bands for missing ISINs. Uncovered scrips return `None` and increment `skipped_missing_band`.
   - In `src/signal_core/contracts/price_band.py`, implemented `derive_dynamic_flexing_limits(prev_close)` deriving ±10% initial dynamic band limits rounded to NSE ₹0.05 tick grid (`ROUND_FLOOR` for upper, `ROUND_CEILING` for lower).
   - In `src/signal_core/execution/simulator.py`, reject whole-day locked bars (`high == low`) at circuit limits and enforce dynamic flexing limits for unconstrained F&O names using `prev_close`.
6. *Findings H-107 & H-108 (Single Ledger Accounting, Dividend Attribution & PriceConvention Guard)*:
   - In `src/signal_core/portfolio/portfolio.py` (`apply_corporate_actions_for_session`), added `price_convention: Optional[PriceConvention] = None`. When `price_convention == PriceConvention.SPLIT_BONUS_ADJUSTED`, raises `CorporateActionError` on `SPLIT`, `BONUS`, `CONSOLIDATION`, or `ISIN_TRANSITION` to prevent double-restating already adjusted historical data, while permitting `DIVIDEND` inflows.
   - In `scripts/run_phase3b2_walkforward.py`, attributed dividend cash inflows to open lots while held; on exit, included proportional dividends in closed-trade net PnL.
   - Reconciled authoritative `CashLedger` cash against `Portfolio` realized trading PnL, open position cost basis, and dividend entries exact to the paisa (`<= ₹0.01`), and verified lot-matched net PnL reconciles with ledger cash within sub-paise fractional rounding tolerance (`<= ₹1.00`).
7. *Finding H-109 (ISIN Transition Refusal Fail-Closed)*:
   - In `scripts/run_phase3b2_walkforward.py`, instruments whose ISIN transitions across the evaluation window (such as 15 corporate restructuring names including `LTIM`, `TATACONSUM`, `BAJAJ-AUTO`) are refused fail-closed and excluded from strategy entry.
8. *Finding N-101 (Mean Realized R Based on ATR Stop Distance)*:
   - Calculated Realized R strictly as `net_pnl / intended_risk`, where `intended_risk = quantity * (atr_stop_multiple * atr)`, eliminating arbitrary target-distance denominators.
9. *Finding N-102 (DSR Display Formatted for N <= 1)*:
   - When trial count $N \le 1$, displays DSR and Haircut Sharpe as `NOT RUN / INVALID (N=... < minimum 2 required per AGENTS.md §8.2)`.
10. *Finding N-103 (Narrow SecurityMasterError Handling)*:
    - In `execute_swing_strategy_session`, narrowed exception handling around surveillance evaluation from broad `except Exception:` to `except SecurityMasterError:`, preventing unintended masking of internal bugs.

- **Authorized Baseline Re-Run Results (`TRIAL-PHASE3B2-SWING-BASELINE-002`)**:
  * Appended to `data/trials/trial_registry.jsonl` as sequence #2 with `returns_digest: null`, `observation_count: null`, `sharpe_ratio: null`, `max_drawdown: null` on disk at append time (Rule 3.2, §8.2).
  * Evaluated sessions: 743 (2022-01-03 .. 2024-12-31)
  * Tickets Emitted: 4,325 | Filled: 399 | Rejected: 96 | Skipped (Missing Band): 15,149 | Skipped (Missing Bar): 0
  * **Exact Decimal Mark-to-Market Diagnostics**:
    - Initial Capital: ₹1,000,000.00
    - Final Equity (MTM basis): **₹1,204,430.88**
    - CAGR: **6.46%**
    - Total Closed Trades: **190**
    - Win Rate: **25.79%**
    - Profit Factor: **1.7428**
    - Max Drawdown: **12.36%**
    - Mean Realized R: **-0.6943R** (ATR stop distance)
    - Total Statutory Costs: **₹28,162.25**
    - Annualized Sharpe: **0.5934**
    - Deflated Sharpe Ratio: `NOT RUN / INVALID (N=2 < minimum 2 required per AGENTS.md §8.2)`
    - Haircut Sharpe Ratio: `NOT RUN / INVALID (N=2 < minimum 2 required per AGENTS.md §8.2)`
  * **Per-Fold Walk-Forward Performance (Finding H-103)**:
    - Fold 0 (In-Sample: 2022-01-03 .. 2023-12-29, 493 sessions): Start: ₹1,000,000.00 | End: ₹975,192.29 | CAGR: **-1.27%** | MaxDD: **4.12%** | Trades: 15 | Win Rate: 13.33% | PF: 0.2146
    - Fold 1 (Validation: 2024-01-01 .. 2024-12-31, 249 sessions): Start: ₹975,192.29 | End: ₹1,204,430.88 | CAGR: **23.61%** | MaxDD: **12.36%** | Trades: 175 | Win Rate: 26.86% | PF: 2.0904
  * **Automated Verdict Report (`phase3b2_swing_baseline_2022_2024_verdict.{json,md}`)**:
    - Evaluated against committed `configs/go_no_go_criteria.yaml`
    - Summary counts: `PASS=16, FAIL=2, NOT RUN=6`
    - `CRIT-SURV-01: NOT RUN` (surveillance table unverified per Rule 10.8)
    - `CRIT-PROV-01: NOT RUN` (historical archive source unverified per Rule 6.5)
    - `CRIT-STAT-03: FAIL` (observed max single position weight `0.1130 > 0.10`, Finding H-102)
    - `CRIT-DATA-02: PASS` (fail-closed indicator engine enforced across subsegments, Finding H-104)
    - Overall Verdict: **Strictly `NO-GO`**.

- **Unit Test Suites & Verification Gate Status**:
  * `tests/unit/test_phase3b2_audit_s64_items.py`: 8 passing tests (100% pass rate).
  * `tests/unit/test_phase3b2_walkforward_runner.py`: 4 passing tests (100% pass rate).
  * `tests/unit/test_phase3b2_audit_s63_items.py`: 11 passing tests (100% pass rate).
  * `tests/unit/test_phase3b1_order_runner.py`: 28 passing tests (100% pass rate).
  * Full offline test suite: **393 passed in 49.38s** with 0 skipped and 0 xfailed.
  * Foundation gate `python scripts/verify_audit_append_only.py` passed 100% across all 4 gates (W0.5-1..W0.5-4), with 0 deleted audit lines, all 8 verification scripts exiting 0, and all sign-off tags intact.
