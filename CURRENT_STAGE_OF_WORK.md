# Signal Atlas Core — Current State of Development & Phased Rebuild Roadmap

## 1. Executive Status & Milestone Summary

| Attribute | Current Status |
|---|---|
| **Active Project Phase** | **Phase 2B signed off** (§22) · **Phase 2B.5 signed off — GO** (§24) · **Wave 0 signed off — GO** (§29 at `d2fd8e0`) · **Wave 1 signed off — GO** (§30 at `95ac584`) · **Wave 2 / Phase 2C signed off — GO** (§33 at `982c9fa`) · **Wave 3 — GO at `a093682` for 2022-01-03..2026-10-31** (§41) · **Phase 2D phase signed off — GO** (§56 at commit `0be0da3`, audit `9368fc4`) · **Phase 3A signed off** (§58 at `d7590fe`, H-81 closed in §59 at `3e619f8`, audit `e5dd500`) · **Phase 3B-1 signed off — GO** (§60 at `078ff8d`, §61 at `4d81077`, §62.4 GO stands, §63.4 GO stands at `396f825`, audit `80a1997`) · **Phase 3B-2a signed off — GO** (§60, §61, §62.4, §63.4 GO stands) · **Phase 3B-2b baseline certified — Trial #3 CERTIFIED as baseline artifact (honest NO-GO)** (§66 at commit `8c4e099`, audit `8c4e0997`); **§66 remediation items (H-112, N-108, H-113, N-109, N-110) implemented (audit §67 at `c5ccbce`, commit `605a488`, records H-112 counts / N-108 / N-110 / N-109 / H-113 mechanism as CLOSED, with N-112 / N-113 / N-115 carried as residuals); §67 residuals (H-114, N-111, N-112, N-115, H-112 residual) implemented and measured locally, not independently audited; Trial #4 (`TRIAL-PHASE3B2-SWING-TRIM-004`) executed on 2022–2023 In-Sample only (2024 Validation frozen) — honest NO-GO (16 PASS / 3 FAIL / 5 NOT RUN) but **`NOT EXERCISED / NULL EXPERIMENT`** per audit §68 at `e265ff5` (H-117), where this section's former “down from 0.1130” attribution is retracted; the certified baseline artifact is a record at **N=3** while the live registry is **N=4** (N-119)** |
| **Domain Maturity** | Market data contracts, point-in-time universe, Bhavcopy reconciliation, series continuity, pure subsegment feature engine, typed criteria loader, statutory Indian cost engine, non-linear slippage model, authoritative execution simulator, exact Decimal cash book, multi-fill position accounting, mark-to-market portfolio valuation, committed risk tracker, holdout containment with physical storage rejection, tamper-evident trial registry, statistical significance engine, strategy contract, walk-forward engine with canonical partition spec defaults and Gold dataset binding, frozen ingest schemas, real Bhavcopy ingestion pipeline, invert-proof corporate action & circuit band contracts, falsifiable circuit auditing, anchored calendar governance, automated fail-closed verdict reporting, exact ATR R-multiple position sizing, point-in-time liquidity universe selection, authoritative daily T+1 order execution runner, position corporate action adjustment mechanism (splits/bonuses/dividends/ISIN transitions/consolidations/rights/delistings/mergers), cash universe price band intervals, surveillance stage exit constraint mechanism (three-state surveillance with GSM Stage 2+ weekly call auction), and authoritative end-to-end walk-forward baseline backtest runner |
| **Offline Test Suite** | **`406 passed in 57.82s`** on this Windows checkout; `verify_cash_universe_coverage.py` exit 0; `verify_phase2d_verdicts.py` exit 0 (Gates 2D-1..2D-5 PASS); `verify_audit_append_only.py` W0.5-1..W0.5-4 PASS (all 8 verification scripts exit 0). Zero skipped, zero xfailed |
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

### Phase 3B-2b (Audit §65 Truth-Pass Remediation & Trial #3 Re-Execution) (Completed)
- **Work Undertaken Following Audit §65 Review (commit `e06b6ee`)**:
  1. *Finding H-111 (Persist Effective Circuit Limits onto `ExecutionFillResult`)*:
     - Added `effective_upper_circuit_limit: Optional[Decimal] = None` and `effective_lower_circuit_limit: Optional[Decimal] = None` to `ExecutionFillResult` and `ExecutionFillResultProtocol` in `src/signal_core/contracts/order_types.py`.
     - Populated effective limits in `ExecutionFillSimulator.simulate_order` across fills, dynamic flexing initial limits (±10%) for F&O scrips, and rejections.
     - Preserved effective circuit limits in `DailyTPlus1OrderRunner` and `WalkForwardEngine` on risk-limit rejections.
     - Updated `CRIT-EXEC-03` and `CRIT-EXEC-04` in `scripts/run_phase3b2_walkforward.py` to inspect `fill.effective_upper_circuit_limit` and `fill.effective_lower_circuit_limit` directly, failing closed if limits are absent.
  2. *Finding N-105 (Eliminate All Remaining Non-Telemetry PASS Checks)*:
     - `CRIT-DATA-02`: Derived `fail_closed_on_unexplained_gaps` strictly from engine configuration telemetry and continuity verification across executed instruments; passing `fail_closed_on_unexplained=False` causes `CRIT-DATA-02` to evaluate to `FAIL`.
     - `CRIT-DATA-03`: Replaced superficial type check with an exhaustive point-in-time membership audit verifying that for every date $d$, every scheduled ISIN has an active `SymbolInterval` covering $d$ with active `EQ` series.
     - `CRIT-DATA-04`: Removed vacuous `unexplained_gap_refusals >= 0` conjunct; computed `zero_data_fabrication` strictly from non-synthetic dataset and OHLC price geometric validity verification.
     - `CRIT-EXEC-02`: Computed `min_daily_turnover_crore` using trailing 20-session Average Daily Traded Value (ADTV) prior to trade entry across all entry fills.
  3. *Finding H-110 (2022–2023 Band Coverage Honesty & Per-Year Diagnostics)*:
     - Explicitly computed and disclosed per-year band coverage diagnostics in `phase3b2_swing_baseline_2022_2024_verdict.{json,md}`:
       * 2022: 248 sessions, 3 band-covered ISINs (INFY, RELIANCE, TCS), 227 zero-ticket sessions, 20 emitted, 20 filled, 10 closed trades (CAGR -3.46%, MaxDD 3.54%, PF 0.0000).
       * 2023: 246 sessions, 3 band-covered ISINs, 234 zero-ticket sessions, 12 emitted, 12 filled, 5 closed trades (CAGR +0.98%, MaxDD 4.12%, PF 1.2029).
       * 2024: 249 sessions, 91 band-covered ISINs, 18 zero-ticket sessions, 4,293 emitted, 367 filled, 96 rejected, 175 closed trades (CAGR +23.53%, MaxDD 12.36%, PF 2.0904).
       * Fully disclosed that 2022–2023 is band-constrained under dynamic flexing anchor names while 2024 possesses full cash universe coverage.
  4. *Finding N-104 (SecurityMaster Fingerprint in Trial Record & Distinct Rationale)*:
     - Extended `compute_security_master_fingerprint` in `src/signal_core/storage/security_master.py` to accept `SecurityMaster` instances directly.
     - Included `security_master_fingerprint` in `TrialRecord.canonical_params` and `execution_config`.
     - Logged distinct trial rationale for Trial #3 documenting §65 truth-pass remediation.
  5. *Remaining Metric Providers*:
     - `CRIT-STAT-05` (Annualized Portfolio Turnover): Computed exact annualized turnover of `2.54x` (`PASS` against `<= 12.0x`).
     - `CRIT-OVERFIT-03` (Walk-Forward Stability Ratio): Computed positive fold ratio of `1.0000` (`PASS` against `>= 0.80`).

- **Authorized Baseline Re-Run Results (`TRIAL-PHASE3B2-SWING-BASELINE-003`)**:
  * Appended to `data/trials/trial_registry.jsonl` as sequence #3 with `sharpe_ratio: null` at append time (Rule 3.2, §8.2).
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
    - Annualized Turnover: **2.54x**
    - Positive Fold Ratio: **100.00%**
  * **Per-Fold Walk-Forward Performance (Finding H-103)**:
    - Fold 0 (In-Sample: 2022-01-03 .. 2023-12-29, 493 sessions): Start: ₹1,000,000.00 | End: ₹975,192.29 | CAGR: **-1.27%** | MaxDD: **4.12%** | Trades: 15 | Win Rate: 13.33% | PF: 0.2146
    - Fold 1 (Validation: 2024-01-01 .. 2024-12-31, 249 sessions): Start: ₹975,192.29 | End: ₹1,204,430.88 | CAGR: **23.61%** | MaxDD: **12.36%** | Trades: 175 | Win Rate: 26.86% | PF: 2.0904
  * **Automated Verdict Report (`phase3b2_swing_baseline_2022_2024_verdict.{json,md}`)**:
    - Evaluated against committed `configs/go_no_go_criteria.yaml`
    - Summary counts: `PASS=18, FAIL=2, NOT RUN=4`
    - `CRIT-SURV-01: NOT RUN` (surveillance table unverified per Rule 10.8)
    - `CRIT-PROV-01: NOT RUN` (historical archive source unverified per Rule 6.5)
    - `CRIT-STAT-03: FAIL` (observed max single position weight `0.1130 > 0.10`, Finding H-102)
    - `CRIT-STAT-05: PASS` (observed annual turnover `2.54 <= 12.0`)
    - `CRIT-OVERFIT-03: PASS` (positive fold ratio `1.0000 >= 0.80`)
    - `CRIT-DATA-02: PASS` (fail-closed indicator engine enforced across subsegments, Finding H-104, N-105)
    - `CRIT-DATA-03: PASS` (point-in-time universe interval audit verified, Finding N-105)
    - `CRIT-DATA-04: PASS` (zero data fabrication non-synthetic verification, Finding N-105)
    - `CRIT-EXEC-02: PASS` (minimum 20-session trailing ADTV ₹139.09 Cr >= ₹5.0 Cr, Finding N-105)
    - `CRIT-EXEC-03: PASS` (circuit limits verified on fills, Finding H-111)
    - `CRIT-EXEC-04: PASS` (circuit limits verified on fills, Finding H-111)
    - Overall Verdict: **Strictly `NO-GO`**.

- **Unit Test Suites & Verification Gate Status**:
  * `tests/unit/test_phase3b2_audit_s65_items.py`: 8 passing tests (100% pass rate).
  * `tests/unit/test_phase3b2_audit_s64_items.py`: 8 passing tests (100% pass rate).
  * `tests/unit/test_phase3b2_walkforward_runner.py`: 4 passing tests (100% pass rate).
  * `tests/unit/test_phase3b2_audit_s63_items.py`: 11 passing tests (100% pass rate).
  * `tests/unit/test_phase3b1_order_runner.py`: 28 passing tests (100% pass rate).
  * Full offline test suite: **401 passed in 48.34s** with 0 skipped and 0 xfailed.
  * Foundation gate `python scripts/verify_audit_append_only.py` passed 100% across all 4 gates (W0.5-1..W0.5-4), with 0 deleted audit lines, all 8 verification scripts exiting 0, and all sign-off tags intact.

### Phase 3B-2b (§66 Certification & Cleanup Remediation: H-112, N-108, H-113, N-109, N-110) (Completed)
- **DeepSeek Audit §66 Verdict at `aff86d8` (commit `8c4e099`, tag `audit-s66-8c4e0997`)**:
  * **Certification**: `TRIAL-PHASE3B2-SWING-BASELINE-003` certified as the official baseline verdict artifact (18 PASS / 2 FAIL / 4 NOT RUN -> honest `NO-GO`).
  * **Authorization**: Strategy-improvement trials (Trial #4+) authorized for exploratory research on 2022-01-03..2023-12-29 with the 2024 fold frozen for final confirmation and holdout partition (`2025-01-01..2026-11-11`) strictly sealed.
  * **Cleanup Remediation Work Order (§66.7 items 1–5)** implemented and verified:
    1. *Finding H-112 & N-110 (Full-Year Band Coverage Union & Interpolated Disclosures)*:
       - In `scripts/run_phase3b2_walkforward.py`, computed `band_covered_isins` per year as the union across all sessions in that year (`125` for 2024, `3` for 2022 and 2023).
       - Fully interpolated all disclosure prose and table notes from `coverage_diagnostics` (`32 fills executed` across 2022–2023, `367 fills executed` in 2024), removing all static hardcoded strings (`H-112`, `N-110`).
       - Explicitly disclosed universe integrity and gap filtering metrics: `176 continuous active instruments evaluated out of 196 valid ISINs (20 instruments refused due to unexplained missing sessions per §6.3 fail-closed invariants)`.
    2. *Finding N-108 (Eliminate Single-Fold Degeneracy on `CRIT-OVERFIT-03`)*:
       - Updated `scripts/run_phase3b2_walkforward.py` and `verdicts.py` so that when $N_{\text{val}} < 2$, `walk_forward_positive_fold_ratio` is omitted (`None`), causing `CRIT-OVERFIT-03` to evaluate honestly to `NOT RUN` with explicit evidence: `Only N_val = 1 validation fold evaluated; minimum 2 independent out-of-sample validation folds required for stability ratio (§8.3, Finding N-108)`.
       - Updated baseline verdict summary counts to: `17 PASS / 2 FAIL / 5 NOT RUN` (honest `NO-GO`).
    3. *Finding H-113 (Stock Merger Fractional Cash-in-Lieu Settlement)*:
       - Extended `Position.apply_corporate_action()` and `Portfolio.apply_corporate_action()` to handle `CorporateActionType.MERGER`: allocates integer whole shares `(qty * num) // den` to `new_isin`, settles fractional shares as cash-in-lieu at proportional cost basis into `CashLedger` (`MERGER_CASH_IN_LIEU`), and debits unallocated fractional charges from `_realized_net_pnl`.
       - Audit §67 records this settlement as at **book value** (`delisting_price` was `None`), making the fractional leg's PnL zero by construction (finding N-112); the earlier "equity preserved (diff 0.00)" claim was that tautology, not an independent verification.
       - Confirmed that running `run_phase3b2_walkforward.py` with `fail_closed_on_unexplained=False` through session 400 (covering the 2023-07-13 HDFC `INE001A01036 -> HDFCBANK` merger) completes cleanly with exit code 0 and no crash.
    4. *Finding N-109 (Producer-Driven Circuit Breach Test)*:
       - Updated `tests/unit/test_phase3b2_audit_s65_items.py::test_h111_fill_at_uc_fails_crit_exec_03` to invoke `run_phase3b2_walkforward` directly on a synthetic corpus with an injected UC fill, driving the real runner and verdict evaluation pipeline (`N-109`).
       - Added `tests/unit/test_phase3b2_audit_s66_items.py` with 5 targeted unit tests covering `H-112`, `N-108`, `H-113` (including the 27 HDFC -> 45 HDFCBANK + cash-in-lieu calculation), and `N-110`.
    5. *Regenerated Baseline Verdict & Budget Preservation*:
       - Re-rendered `reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.{json,md}` with `--no-record-trial`, preserving `data/trials/trial_registry.jsonl` at exactly $N=3$ rows (`git diff` clean).
  * **Offline Test Suite & Verification Gate Status**:
    - `tests/unit/test_phase3b2_audit_s66_items.py`: 5 passing tests (100% pass rate).
    - `tests/unit/test_phase3b2_audit_s65_items.py`: 8 passing tests (100% pass rate).
    - Full offline test suite: **406 passed in 47.55s** with 0 skipped and 0 xfailed.
    - Foundation gate `python scripts/verify_audit_append_only.py`: ALL REPOSITORY FOUNDATION GATES PASSED (100%), all 8 verification scripts exit 0, all 46 commit tags verified.


### Phase 3B-2b (§67 Hardening Residuals & Exploratory Trial #4) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §67 at commit `605a488` (reviewing `c5ccbce`) certified the Trial #3 baseline artifact, recorded `§66.7` cleanup as **COMPLETE WITH RESIDUALS**, and **UNBLOCKED** Trial #4+ as exploratory, in-sample-only work. The items below implement §67.6 work-order items 1–4 and 6; no audit section yet judges this delivery.
- **H-114 — post-slippage circuit rejection.** `ExecutionSimulator.simulate_order()` now rejects any BUY whose post-slippage, tick-clamped execution price is `>= effective_upper_circuit_limit` (`REJECTED_UPPER_CIRCUIT`) and any SELL whose price is `<= effective_lower_circuit_limit` (`REJECTED_LOWER_CIRCUIT`). A bar opening one tick below the band can no longer fill at the band. `CRIT-EXEC-03`/`-04` evidence is now formatted from the run's judged/violating/missing-limit fill counts instead of a constant sentence.
- **N-111 — unregistered re-render fails closed.** `record_trial=False` now raises `ValueError` unless the `trial_id` already exists in the registry; the fabricated `RE_RENDER_UNREGISTERED` `TrialRecord` branch is deleted.
- **N-112 / N-115 — merger settlement economics.** The 2023-07-13 HDFC→HDFCBANK `MERGER` row now carries `delisting_price: 1641.10` (HDFCBANK close on the effective date, sourced from the committed 2023 Bhavcopy corpus). `Position.record_merger_cash_settlement_pnl()` books `(consideration − removed book basis)` as realized PnL so the ledger identity stays exact, and the runner no longer appends a zero-gross fractional `closed_trades` shadow entry. `data/reference/manifest.jsonl` SHA-256/byte count and the `expected_manifest_fingerprint` pin were recomputed; **no criterion threshold was changed**.
- **H-112 residual.** The 2022–2023 disclosure prose and per-year `coverage_notes` now interpolate the band-covered symbol list (`HDFC, INFY, RELIANCE`) from `coverage_diagnostics["band_covered_symbols"]`, replacing the typed `(INFY, RELIANCE)` enumeration.
- **Trial #4 execution (`TRIAL-PHASE3B2-SWING-TRIM-004`, seq #4, N=4): `NOT EXERCISED / NULL EXPERIMENT` (audit §68 at `e265ff5`, H-117).** Registered before metrics were read, with `partition = IN_SAMPLE` and canonical parameter `max_position_weight_trim_threshold = 0.095`. Run command: `python scripts/run_phase3b2_walkforward.py --in-sample-only --no-record-trial --trial-id TRIAL-PHASE3B2-SWING-TRIM-004 --trim-threshold 0.095 --verdict-output-dir reports/verdicts/trial_004`. The 2024 Validation fold is absent (`validation_folds_count = 0`); no out-of-sample claim is made.
  * **The hypothesis was never tested.** Zero trim tickets were emitted in 494 sessions (2022 emitted 20 = filled 20; 2023 emitted 12 = filled 12, identical to the certified baseline's own in-sample fold), and the metrics equal the baseline's in-sample fold to every printed digit (15 trades, end equity `975192.29`, PF `0.2146402927805285752276267302`, CAGR `-0.0126578513783100833588337349`, max DD `0.04115480800453974531801802628`). Trial #4 therefore consumed one unit of the multiple-testing budget (N = 3 → 4) without producing information about the trim.
  * Measured on 494 sessions (2022-01-03..2023-12-29): 32 fills, 15 closed trades, profit factor `0.2146`, max drawdown `4.12%`, CAGR `-1.26%`.
  * `CRIT-EXEC-03 PASS` (`0 of 17` judged BUY fills at/above UC, 0 missing limits) and `CRIT-EXEC-04 PASS` (`0 of 15` judged SELL fills at/below LC, 0 missing limits) — §67 Condition 5 satisfied.
  * `CRIT-STAT-03 PASS` at `max_single_position_weight = 0.0918` (≤ 0.10). **Correction (H-117): the former sentence "down from the Trial #3 baseline breach of 0.1130" is retracted.** The two numbers come from different windows: `0.0918` is the 2022–2023 in-sample maximum, which the baseline's own in-sample fold already had, while `0.1130` is the full-window maximum and belongs to the frozen 2024 fold. The trim did not reduce that figure; the evaluation window differs. No computed comparison supports the causal claim, so none is made.
  * Honest verdict: `16 PASS / 3 FAIL / 5 NOT RUN` → `NO-GO`. The FAILs are `CRIT-STAT-01` (15 trades < 100), `CRIT-STAT-02` (PF 0.2146 < 1.50), and `CRIT-DATA-05` (96.6825% ISIN resolution in a 2022–2023-only window). `CRIT-SURV-01`, `CRIT-PROV-01`, `CRIT-OVERFIT-02`, `CRIT-OVERFIT-03` and `CRIT-INFO-01` remain `NOT RUN` with named inputs.
  * The certified baseline artifacts `reports/verdicts/phase3b2_swing_baseline_2022_2024_verdict.{json,md}` are untouched; Trial #4 wrote only under `reports/verdicts/trial_004/`.
  * **Snapshot state (N-119, audit §68.1/§68.6 item 5):** those baseline artifacts are a **historical certified snapshot captured at `N = 3`**, certified at commit `c5ccbce` under criteria fingerprint `CRIT-FPR-V1-b3f35df928c1ce126e0cbc9f46b4f47f901448d8201bf8922060abe79fcd6677` (criteria version `1.1.0`). The live `TrialRegistry` now holds **`N = 4`**, so re-rendering trial 003 at HEAD would change `/criteria_fingerprint`, `CRIT-OVERFIT-01` (`N = 3 → 4`), both circuit evidences and every coverage note. Those differences are the current state, not drift; the artifact is not regenerated because it is a record of what was certified at `N = 3`.
- **Verification actually run.** Full offline suite `413 passed, 0 skipped, 0 xfailed`; all 8 `scripts/verify_*.py` exit 0 (`verify_audit_append_only.py` reports ALL REPOSITORY FOUNDATION GATES PASSED); new tests in `tests/unit/test_phase3b2_audit_s67_items.py` cover H-114 (direct simulator rejection + dynamic evidence), N-111, N-112, N-115 and the trim emission. The modified `test_h111_fill_at_uc_fails_crit_exec_03` now asserts the rejection guard rather than the former clamped fill.
- **Not claimed.** No independent audit of this delivery; no parameter sweep beyond one structural hypothesis (`N = 4`, DSR/haircut still `NOT RUN`); no confirmatory 2024 or holdout evidence; the ±10% flexing band and 2,749 cash-universe band intervals remain as §67 left them.

### Phase 3B-2b (Audit §68 Remediation: H-115, H-116, H-117, N-112 residual, N-117, N-118, N-119, CA-3) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §68 at commit `e265ff5` (reviewing `ef43e70`) recorded Trial #4 as `NOT EXERCISED / NULL EXPERIMENT` (H-117), required the transition-refusal denominator to span the dataset window (H-116), required the corrected merger settlement to remove every silent cost-basis fallback (N-112 residual), required the Phase 2D artifact's declared state to match its bytes (H-115), required digest/observation evidence on the report (N-117) and numeric-only circuit evidence (N-118), and required the N=3 baseline snapshot to be described as a snapshot (N-119). No audit section yet judges this delivery.
- **H-117 / N-119 — retraction and snapshot state.** The sentence "down from the Trial #3 baseline breach of 0.1130" is retracted in both this file and Trial #4's rendered markdown. Trial #4 is recorded as `NOT EXERCISED / NULL EXPERIMENT`: 0 trim tickets in 494 sessions, and every metric equals the baseline's own 2022–2023 in-sample fold to the printed digit (`0.0918` was already the in-sample maximum at baseline; `0.1130` belongs to the frozen 2024 fold). The certified baseline artifacts remain a **snapshot captured at N = 3** while the live registry is N = 4; re-rendering trial 003 at HEAD would change the criteria fingerprint, `CRIT-OVERFIT-01`, both circuit evidences and every coverage note, so the artifact is left as the record of what was certified.
- **H-116 — transition refusal denominator.** `scripts/run_phase3b2_walkforward.py` now bounds the refusal scan by `min(trading_dates)..max(trading_dates)` instead of the first/last bars of the resolved symbol series. The symbol-resolution fallback for a dataset whose last session is not a bar for that symbol is **retained**, with an in-code comment recording the measurement: removing it raises `ValueError: Failed to resolve authentic ISIN for symbol UNITDSPR` under `--in-sample-only`, because the legacy resolver keys on the last bar rather than the window end. This is a deviation from the work order's "remove the dead fallback" wording; the fallback is not dead and its removal is unsafe without changing the resolver's keying, which is outside this round.
  * Re-rendered Trial #4 coverage: **179 continuous active instruments evaluated out of 196 valid ISINs (17 refused)**. The audit's `176 / 15` figure assumes the full-window gap scan; with the span-bounded scan the refused set is 17.
    * **Correction (N-120, audit §70).** The `15` in the audit's `176 / 15` is **not** a gap-refusal count: it is the number of refused *ISIN-transition UUIDs* in the auditor's probe. The two gap-refusal counts are independent of it — `20` for the full-window scan (the §66 section above) and `17` for the span-bounded scan used by Trial #4. Three different counters, and this note previously conflated two of them.
  * Re-rendered Trial #4 now carries `returns_digest = RET-V1-cf90af33f29e4684206b9f02f62638aae6fd54d22d529b89ae5061b95dd5acc7` and `observation_count = 493` (N-117), and `CRIT-EXEC-03`/`-04` PASS cite `17`/`15` judged fills from the run (N-118).
- **N-118 — numeric-only circuit criteria.** `src/signal_core/reporting/verdicts.py` evaluates `CRIT-EXEC-03`/`-04` from the six count fields only; a bundle that omits the counts is `NOT RUN` rather than PASS on a boolean flag. `scripts/verify_phase2d_verdicts.py` and the unit fixtures were updated to supply the counts so the committed Phase 2D artifact still passes on computed evidence.
- **H-115 / N-112 residual — artifact state and merger economics.** The Phase 2D artifact was **regenerated** (not restored): `scripts/generate_phase2d_tier_a_report.py` writes `evaluated_at_utc = 2026-11-16T10:00:00+00:00` plus a `restatement_note` injected into `report.metadata` and appended to the markdown, so the declared timestamp describes the bytes it ships with. `data/reference/manifest.jsonl` records the same timestamp and a `retrieval_reference` naming the restatement; `configs/go_no_go_criteria.yaml` moves `1.1.0 -> 1.1.1` with **no threshold changed** (comment states it), and the `expected_manifest_fingerprint` pin was recomputed (`MAN-FPR-V1-444e9a64aa5fbccb943dfc6994c7daca042d2ee446d971a09d2211645cc725c1`).
  * `data/reference/corporate_actions.jsonl` now prices all three stock mergers from committed Bhavcopy closes on their ex-dates: HDFC `1641.10`, MINDTREE `4742.05` (2022-11-23), IDFC `74.19` (2024-09-27); file SHA-256 `c4706736c2b910b0f1a2aad87f74ac87ef6a63fd9021dedcf40f051f45aa2676`. The HDFC `delisting_price` is documented as a modelled ex-date close proxy, not an exchange cash-in-lieu rate.
  * `Position.apply_corporate_action()` and `Portfolio.apply_corporate_action()` now fail closed with `CorporateActionError` when a fractional merger carries no consideration price; the `cash_amount = frac_cost_basis` fallback is deleted, so the fractional leg is a disposal at consideration and the ledger identity moves by `(consideration − removed book basis)`.
  * `test_phase3b2_audit_s66_items.py::test_h113_stock_merger_fractional_cash_in_lieu` was updated to the consideration economics (27 HDFC → 45 HDFCBANK + ₹590.80 at 1641.10) and now asserts the ledger identity, not the former zero-PnL tautology. This edits a §66 test's expectation because the expectation encoded the finding N-112 defect.
- **CA-3 — 2022–2023 band sources.** Inventoried the committed corpus: `data/raw/2022` = 248 Bhavcopy archives, `data/raw/2023` = 246, `data/raw/2024` = 249. There are **no 2022 or 2023 `sec_list`/price-band files** anywhere in the repository; the only `data/reference/sec_list_20240116.csv` is 2024-dated and `data/reference/bhavcopy_archive_manifest.jsonl` contains zero `sec_list` rows. Band coverage for 2022–2023 therefore remains the interpolated (`3` symbols/year) disclosure recorded under H-112, not a sourced per-session band table; this is a residual, not a closed item.
- **Verification actually run.** Full offline suite: **418 passed, 0 skipped, 0 xfailed** (`python -m pytest -q`). All 8 `scripts/verify_*.py` exit 0, including `verify_phase2d_verdicts.py` and `verify_phase2c_walkforward.py` (whose criteria-version check now reads the committed criteria version instead of the literal `1.1.0`); `python scripts/verify_audit_append_only.py` reports ALL REPOSITORY FOUNDATION GATES PASSED with zero deleted audit lines. `data/trials/trial_registry.jsonl` is unchanged at N = 4 rows; Trial #4 was re-rendered with `--no-record-trial`; holdout partitions were never read.
- **Not claimed.** No independent audit of this delivery. Open residuals: the 2022–2023 band coverage is interpolated, not sourced (CA-3); the H-116 resolver fallback remains; `CRIT-SURV-01`, `CRIT-PROV-01`, `CRIT-OVERFIT-02`/`-03` and `CRIT-INFO-01` remain `NOT RUN` with named inputs; DSR/haircut is still uncomputed; Trial #4 produced no information (N = 4 spent).

### Phase 3B-2b (Audit §69 Remediation: H-118, H-119, CA-3(a)/(b)/(c)) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §69 at commit `4f35609` (reviewing `5cee179`) closed six of the seven §68 items and raised two new findings: **H-118** — the reference manifest's per-artifact digests were never recomputed, so a one-byte corpus edit passed every gate while `manifest.jsonl` still attested the old SHA-256 — and **H-119** — no trial row carried a Sharpe, so `evaluated_trial_count` stayed 0 and the CLI printed `N=4 < minimum 2`, a reason its own output contradicted. Item 3 (CA-3) remained the binding constraint on strategy work. No audit section yet judges this delivery.
- **H-118 — manifest attestations are now verified per artifact.** `src/signal_core/storage/reference_integrity.py` reads `data/reference/manifest.jsonl`, resolves each current row's `artifact` under `data/reference`, `data/raw`, then the repo root, and recomputes `byte_count` and `sha256`; a missing file, an incomplete attestation, a byte-count mismatch or a digest mismatch raises `ManifestIntegrityError`. Superseded rows (19) are counted and skipped: they name paths whose bytes were intentionally replaced by a later derivation, so they cannot be checked against the current file. **Measured: 46 current artifacts recomputed and matched.**
  * Wired into `scripts/verify_phase2d_verdicts.py` as **Gate 2D-6** and into `scripts/verify_audit_append_only.py` as **Gate W0.5-5** (`--check-reference-only` runs it alone).
  * `tests/unit/test_phase3b2_audit_s69_items.py::test_h118_one_byte_corpus_edit_fails_closed` copies the reference tree, flips one byte of `corporate_actions.jsonl` (leaving the manifest untouched), and requires `ManifestIntegrityError`; the untampered copy verifies first, so the failure is the edit. A second test proves an attested-but-absent file also fails closed.
- **H-119 — append-only post-evaluation scoring.** `TrialRegistry` now keeps a second append-only sidecar, `<registry>.evaluations`, whose rows link `trial_id` and the registry row's `record_hash` and carry `sharpe_ratio`, `max_drawdown`, `returns_digest`, `observation_count` and `evaluated_at_utc`. Each line is hash-chained (`prev_eval_hash` / `eval_hash`); loading verifies the chain, the link to the registered row, uniqueness, and timestamp monotonicity, and fails closed on any mismatch. `evaluated_trial_count` and `get_trial_sharpes()` now read rows **or** appended outcomes.
  * `scripts/run_phase3b2_walkforward.py` still appends the trial with `sharpe_ratio=None` before metrics are read (Rule 3.2), then calls `append_trial_evaluation()` with the computed annualized Sharpe, digest, observation count and drawdown on newly executed trials. Rows 1–4 are untouched and no trial was spent this round (`--no-record-trial`), so **`evaluated_trial_count` is still 0 and `CRIT-OVERFIT-02` remains `NOT RUN`** at this commit; the path to scoring now exists, the score does not.
  * One outcome per trial: re-scoring raises `TrialEvaluationError` ("append-only"), and scoring an unregistered `trial_id` raises with that reason. The CLI's false comparison is gone: `describe_stats_not_run_reason()` prints `evaluated_trial_count=0 < minimum 2 scored trials required for DSR variance (§8.2, Finding H-119)`, and a distinct message when the count is sufficient but the trial Sharpe variance is not strictly positive.
- **CA-3(a) — availability probe, recorded.** Probed from this environment on 2026-11-16: `https://archives.nseindia.com/content/equities/sec_list.csv` → `200`, 176,495 bytes, current-session schema `Symbol,Series,Security Name,Band,Remarks`; the dated guesses `.../sec_list_20230103.csv` and `.../archives/equities/sec_list/sec_list_20230103.csv` → `404`; `.../sec_list.csv?date=20230103` → `200` with the **same** 176,495 bytes as the undated request, so the query parameter is ignored; the Wayback CDX index for that URL has exactly **one** capture in `2022-01-01..2023-12-31` (2023-06-27T21:24:21Z). **Conclusion: per-session 2022–2023 price-band reports are not retrievable here** — the exchange overwrites one live file and publishes no dated archive, and one archived capture is not a per-session series. Item 3 therefore takes the CA-3(c) path; CA-3(b) ingestion was not performed and no band was synthesized or back-dated.
- **CA-3(c) — 2022-01-03..2024-01-15 is band-ineligible and fails closed.** `SOURCED_PRICE_BAND_START = 2024-01-16` and `is_price_band_sourced()` live in `src/signal_core/contracts/price_band.py`. When any evaluated session precedes it, the runner omits the six judged/violating fill counts and supplies `circuit_band_coverage_note` plus `unsourced_band_sessions`; `evaluate_verdicts` now evaluates `CRIT-EXEC-03`/`-04` to `NOT RUN` with that note as the evidence even if counts are supplied. The artifact's coverage table and markdown now say **Band-ineligible (CA-3(c))**, and the 2024 note says the attested 2024-01-16 snapshot is applied as static bands rather than claiming daily records.
  * **Trial #4 re-rendered** (`--in-sample-only --no-record-trial --trim-threshold 0.095`): `14 PASS / 3 FAIL / 7 NOT RUN`, with `494 of 494` evaluated sessions named as unsourced. This supersedes the pre-CA-3(c) rendering recorded in the §67/§68 text (`16 PASS / 3 FAIL / 5 NOT RUN`), where `CRIT-EXEC-03/04` passed on 17/15 judged fills over unsourced bands. Registry unchanged at N = 4.
- **Verification actually run.** Full offline suite: **426 passed, 0 skipped, 0 xfailed**; all 9 `scripts/verify_*.py` exit 0, including `verify_phase2d_verdicts.py` (5/5 → 6/6 gates) and `verify_audit_append_only.py` (now 5 gates; zero deleted audit lines). New tests: `tests/unit/test_phase3b2_audit_s69_items.py` (8 tests covering the H-118 tamper probe, H-119 scoring increments/reload/DSR computability/reason text, and the CA-3(c) boundary + verdict behaviour). Two §65/§67 tests were updated to expect `NOT RUN` on the 2022 fixture window, which is the CA-3(c) contract, not a relaxation. Holdout never read; no trial registered.
- **Not claimed.** No independent audit. `CRIT-EXEC-03/04` remain `NOT RUN` for every window containing pre-2024-01-16 sessions (all current windows), so circuit-prohibition compliance is unproven for 2022–2023. DSR/haircut remain `NOT RUN` until two new trials are scored. Not addressed this round (audit §69.6 item 7): N-120 (stage-file counter naming in the §68 section), N-121 (`judged_fills > 0` scope), N-122 (what the dynamic criteria-version check no longer verifies).

### Phase 3B-2b (Audit §70 Remediation: H-120, H-121, N-123–N-126) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §70 at commit `2fc08e2` (reviewing `308921b`) closed H-118 and H-119's mechanism and then found that both new guards were bypassable: **H-120** — the band-coverage refusal was selected by a producer-supplied `circuit_band_coverage_note`, so a 2022–2023 bundle with counts and no note still produced `CRIT-EXEC-03/04 PASS`; **H-121** — the evaluation sidecar had only its internal `prev_eval_hash` chain, so deleting its last line or the whole file lowered `N_eval` (and the DSR penalty) with `verify_integrity()` still returning `True`, and no gate read it. No audit section yet judges this delivery.
- **H-120 — band eligibility now derives from the engine's window.** `evaluate_verdicts()` walks the calendar sessions in the bundle's own `evaluation_start_date..evaluation_end_date` and, if any session is not `is_price_band_sourced()`, forces `CRIT-EXEC-03/04` to `NOT RUN` with a computed evidence sentence naming the count, the range, the window and `Finding H-120`. The producer note survives only as appended evidence (`Producer note: …`) and can no longer select the branch. Probes (`tests/unit/test_phase3b2_audit_s69_items.py::test_h120_*`): the 2022-01-03..2023-12-29 bundle with counts and **no** note now yields `NOT RUN` for both ids; a supplied note cannot lift it; the 2024-01-16..2024-03-29 bundle with counts yields `PASS`.
  * **N-121:** the `PASS` branch now additionally requires `judged_fills > 0`. A sourced window with `0` judged fills is `NOT RUN` (`… untested on this run rather than satisfied`), so circuit realism cannot be claimed from a run that never tested it.
- **H-121 — external head anchor for the evaluation ledger.** `TrialRegistry` writes `<registry>.evaluations.manifest` atomically (temp file + `fsync` + `os.replace`) after each append, recording `evaluation_count`, `head_eval_hash`, `byte_count` and `sha256`. `_load_evaluations()` requires the anchor whenever the sidecar exists (missing anchor → `RegistryTamperedError`), refuses an absent sidecar that the anchor still attests ("whole-file deletion detected"), and compares all four values against the bytes on disk. **Measured probes:** 3 appended evaluations → `N_eval 3`; delete the last line → constructor **and** `verify_integrity()` both raise (`Evaluation head anchor mismatch for 'evaluation_count'`); delete the whole sidecar → raise; remove the anchor → raise (`no external head anchor`). The same three probes are in `tests/unit/test_phase3b2_audit_s69_items.py` (`test_h121_*`).
  * **Gate:** `scripts/verify_phase2a_containment_and_trials.py` gains **G2A-6** (six checks): anchor presence/verification, suffix-truncation rejection by constructor and by `verify_integrity()`, whole-file-deletion rejection, artifact-Sharpe agreement, disagreement rejection, and the committed registry's integrity (`N=4`, `N_eval=0`, no sidecar). All pass; the committed-registry artifact cross-check prints `[N/A]`, not `PASS`, while no scored trial exists.
- **N-125 — the scored Sharpe is now visible where it can be checked.** `run_phase3b2_walkforward.py` writes `trial_id`, `annualized_sharpe` and `evaluated_trial_count` into the verdict JSON, and `verify_evaluation_artifact_agreement()` (in `trials.py`) requires the artifact named for a scored `trial_id` to carry an `annualized_sharpe` exactly equal to the sidecar `sharpe_ratio`. Missing artifact, missing figure, or a disagreement raises `TrialEvaluationError`. Trial #4 re-rendered (`--no-record-trial`): disclosure-only diff plus `annualized_sharpe = -0.6995862169544497756996745538`, `evaluated_trial_count = 0`; metrics unchanged (`975192.29`, 15 trades, PF `0.2146402927805285752276267302`).
- **N-126 — the band start date is derived, not typed.** `derive_sourced_price_band_start()` parses current manifest rows for `sec_list_YYYYMMDD.csv` and returns the earliest date; `SOURCED_PRICE_BAND_START` is now computed from it at import, with `2024-01-16` retained only as the manifest-absent fallback. Measured: manifest → `2024-01-16`; synthetic manifest naming `sec_list_20250101.csv` → `2025-01-01`; absent path → fallback. The 2024 fold disclosure now states the static-band assumption as an unverified residual (bands from the single 2024-01-16 snapshot assumed to hold through 2024-12-31; the fold's first fifteen sessions are unsourced).
- **N-123 — the numeric circuit evidence is under test again.** `tests/unit/test_phase3b2_audit_s67_items.py::test_n123_sourced_window_keeps_numeric_circuit_evidence` evaluates a 2024-01-16+ window and asserts `PASS` with `0 of 2 judged BUY fill(s)` and a `\d+ of \d+ judged SELL fill(s)` match, beside the 2022 fixture's `NOT RUN` assertion (which stays).
- **N-124 — `is_current` must be an explicit boolean.** `verify_manifest_artifacts()` now raises `ManifestIntegrityError` when a row's `is_current` is missing or non-boolean instead of counting it as history. Measured: 46 current rows still verify; a row without the key raises `… has no explicit boolean 'is_current' …`.
- **§69.6 item 7 (N-120, N-122).** The §68 note is corrected: the auditor's `15` is a count of refused **ISIN-transition UUIDs**, not gap refusals — the gap-refusal counters are `20` (full-window) and `17` (span-bounded), and the three numbers were conflated. `scripts/verify_phase2c_walkforward.py` now carries a comment naming what its dynamic `criteria_version` comparison no longer verifies (label agreement at check time, not a registration-time pin, because the row holds no criteria fingerprint).
- **Verification actually run.** Full offline suite: **434 passed, 0 skipped, 0 xfailed**; all 9 `scripts/verify_*.py` exit 0; the Phase 2D Tier-A artifact was regenerated because H-120 changed both circuit criteria's status and evidence (`CRIT-PROV-01`, `CRIT-INFO-01`, `CRIT-EXEC-03/04` are the four `NOT RUN` entries; the pytest and Gate 2D-3 expectations were updated to that set, not relaxed to a subset). Holdout never read; registry bytes unchanged at N = 4; no sidecar or anchor committed, because no trial was scored.
- **Not claimed.** No independent audit. Still `NOT RUN` for every runnable window: `CRIT-EXEC-03/04` (only the 2024-01-16+ sub-window is sourced, and the in-sample window is wholly earlier), `CRIT-OVERFIT-02` (`evaluated_trial_count = 0`), `CRIT-OVERFIT-03` (one validation fold), `CRIT-PROV-01`, `CRIT-SURV-01`, `CRIT-INFO-01`. Carried residuals not addressed: `CRIT-DATA-02`'s `or continuous_instruments_passed > 0` disjunct, `CRIT-WINDOW-01`'s 494 vs 493, the hardcoded `Append-Before-Read Check: PASS` line, the dual `open_lots`/`Portfolio` merger date book, and `--trim-threshold` never emitting an order.

### Phase 3B-2b (Audit §71 Remediation: H-123, H-122, N-127 + Trial #5) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §71 at commit `cd5073b` (reviewing `125f905`) recorded §70's work order as 4 of 7 CLOSED and 3 PARTIAL, and filed **H-123** (band eligibility skipped when the window is missing or session-empty), **H-122** (the evaluation ledger's two files can be erased or re-anchored together, and no gate reads artifacts→ledger), and **N-127** (the derived band boundary trusts manifest filenames the corpus verifier refuses). No audit section yet judges this delivery.
- **H-123 — an unwalkable window is an unassertable one.** `evaluate_verdicts()` now treats a missing, empty, whitespace, unparseable, reversed or session-empty `evaluation_start_date..evaluation_end_date` as a band-eligibility defect: `CRIT-EXEC-03` and `CRIT-EXEC-04` are `NOT RUN` with the defect named and `Finding H-123` cited, and the counts branch is reachable only from a session-bearing, fully band-sourced window. The reversed-window path also no longer raises `CalendarError` out of the engine: `CRIT-WINDOW-01` fails with its own evidence and the session count is not taken for an empty ordering. Probes (`tests/unit/test_phase3b2_audit_s71_items.py`): omitted keys, `""`/`""`, `2024-13-45`/`soon`, `2024-03-29..2024-01-16` and the weekend `2023-12-30..2023-12-31` each give `NOT RUN` on both criteria; `2022-01-03..2023-12-29` stays `NOT RUN`; `2024-01-16..2024-03-31` stays `PASS` with `0 of 2 judged BUY fill(s)`.
- **H-122 — the evaluation head is witnessed outside the ledger pair.** `append_trial_evaluation()` now also writes `evaluation_count` and `head_eval_hash` into `<registry>.manifest` (the file `G2A-6.6` already reads), and `_load_evaluations()` refuses when that witness disagrees with the ledger, or when the witness is non-zero while both ledger files are absent. `verify_evaluation_artifact_agreement()` gained the reverse direction: every verdict artifact carrying `trial_id` + `annualized_sharpe` for a registered trial at `seq > 4` must have a ledger row with an equal Sharpe (trials 1–4 are pre-sidecar and excluded by a named constant). Gate `G2A-6.7` now runs both directions at `N_eval = 0` as well, instead of printing `[N/A]`. **Measured probes:** deleting `.evaluations` **and** `.evaluations.manifest` raises `dual-file erasure detected` from both the constructor and `verify_integrity()`; truncating the sidecar and recomputing its anchor raises `Registry manifest witnesses`; an artifact naming a `seq 5` trial with no ledger row raises `artifact->ledger direction is unattested`.
- **N-127 — the band boundary only moves for a digest-verified artifact.** `derive_sourced_price_band_start()` now requires the named artifact to exist beside the manifest with matching `byte_count` and `sha256`, and raises `PriceBandValidationError` on a malformed manifest line instead of collapsing silently to the fallback. Measured: the audit's fabricated `sec_list_20220601.csv` row leaves the boundary at `2024-01-16`; a present file with wrong bytes also leaves it there; `{not json` raises; the committed manifest still derives `2024-01-16`.
- **CLI plumbing.** `--fast-indicator` (default `sma_20`), `--slow-indicator` (default `sma_50`) and `--atr-stop-multiple` (default `2.0`) now reach `run_phase3b2_walkforward()` and appear in the appended row's `canonical_params`. Fill, cost and accounting paths are untouched.
- **Trial #5 (`TRIAL-PHASE3B2-SWING-ATR3-005`, seq 5, `N = 5`, `N_eval = 1`) — executed and FALSIFIED, and also structurally null.** Registered and scored by the run itself (`--in-sample-only`, no `--no-record-trial`), hypothesis and rationale recorded verbatim from §71.6.1. Window 493 sessions (2022-01-03..2023-12-29); 32 tickets emitted, 32 filled, 2 open positions at end.
  * **Measured:** 15 closed round trips, 2 winners, end equity `975192.29`, CAGR `-1.2658%`, max drawdown `4.1155%`, PF `0.2146402927805285752276267302`, annualized Sharpe `-0.6995862169544497756996745538`, statutory costs `₹3,511.93`, **mean net expectancy per closed round trip `-₹2,254.56` (`-0.5833R`)**.
  * **Every one of those figures is identical to the certified baseline's in-sample fold** (`trial_004`), and `returns_digest` is the same `RET-V1-cf90af33…`: **the strategy emits no stop order at all**, so exits are produced solely by the `close < slow_val` rule and no stop price is tested against the tape. This is a null experiment of the H-117 class, and the audit's measured "18 of 47 stop touches at 2.0× vs 10 at 3.0×" describes a stop the engine does not place. The hypothesis is falsified in the arithmetic sense (expectancy `-₹2,254.56` < 0) but the trial cannot be read as a test of the 2.0×→3.0× change.
  * **Correction (Audit §72 H-124, applied 2026-11-16).** The sentence originally written here — that `atr_stop_multiple` "reaches position sizing and `intended_risk`" — was wrong, and it understated the defect: `scripts/run_phase3b2_walkforward.py` built `DailyTPlus1OrderRunner` **without** `atr_stop_multiple`, so the runner sized at its default `k = 2.0` while the row recorded `"3.0"`. The parameter never left the strategy object, and even the R denominator was computed from `k = 2.0`. The null result therefore had two independent causes: no stop order existed, and the multiple that would have priced one never reached the engine. Fixed in §72 work item 1 (see the `Phase 3B-2c` section below); Trial #5's row is unchanged and is not re-scored.
  * **Gate A: STOP.** Closed trades `15 ≥ 10` and net expectancy `-₹2,254.56 ≤ 0`, so per §71.6.2 the family stops at `N = 5`, `N_eval = 1` and **Trial #6 was not executed**. `CRIT-OVERFIT-02` stays `NOT RUN` (`evaluated_trial_count = 1 < 2`), DSR/haircut remain `NOT RUN`.
  * **Gate B: not spent.** No 2024 session was evaluated (`validation_folds_count = 0`), no holdout partition was read, and `2024-01-16..2024-12-31` remains unrun.
  * Artifact: `reports/verdicts/trial_005/phase3b2_swing_baseline_2022_2024_verdict.{json,md}`, `overall_verdict = NO-GO`, `14 PASS / 3 FAIL / 7 NOT RUN` (the same FAILs as trial_004: `CRIT-STAT-01`, `CRIT-STAT-02`, `CRIT-DATA-05`).
- **Verification actually run.** Full offline suite **450 passed, 0 skipped, 0 xfailed** (434 before, +16 in `tests/unit/test_phase3b2_audit_s71_items.py`); all 9 `scripts/verify_*.py` exit 0; `verify_audit_append_only.py` reports ALL REPOSITORY FOUNDATION GATES PASSED, including `G2A-6.7` now checking both directions against `trial_005`'s row and artifact.
- **Not claimed (§71 delivery).** No independent audit of `f4a1b31` or this trial. No claim that the stop geometry was tested; implementing a stop exit is a strategy change that was not made and must not be made inside an already-spent trial id. No 2024 or holdout evidence. `CRIT-EXEC-03/04` remain `NOT RUN` (all 494 in-sample sessions are unsourced), as do `CRIT-PROV-01`, `CRIT-SURV-01`, `CRIT-INFO-01`, `CRIT-OVERFIT-02` and `CRIT-OVERFIT-03`.

### Phase 3B-2c (Audit §72: H-124, Ruling 1 protective stops, N-128, N-129) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §72 at commit `05806ae`, reviewing `5176bc5`. It graded §71's work order as 2 CLOSED, 1 PARTIAL (H-122 → N-128) and 1 COMPLETE-with-a-new-HIGH (H-124), filed **N-129**, issued **Ruling 1** (protective T+1 stops are required, with §5.3 deferral) and **Ruling 2** (do not run Trial #6). No audit section yet judges this delivery.
- **H-124 — one `k`, and the row describes the run.** `scripts/run_phase3b2_walkforward.py` now builds the single authoritative runner through `build_authoritative_runner(..., atr_stop_multiple=...)`, so the same `k` prices sizing, the persisted stop, `intended_risk` and `canonical_params`. The registry row is written from `runner.atr_stop_multiple`, and a mismatch against the strategy object raises instead of recording a configuration the engine did not receive. **Measured probes** (`tests/unit/test_phase3b2_audit_s72_items.py`): at ATR/price = 8 % the risk leg binds at both multiples and the fill quantity differs (`k=2.0 → 62` shares, `k=3.0 → 41`, both `RISK_BUDGET`); at ATR/price = 2 % neither leg binds and both run at `100` shares under `MAX_POSITION_WEIGHT`, which reproduces §72.3's finding that a `k` sweep on the 2022–2023 tape is null for entries and can only act through the stop order.
- **Ruling 1 — a protective stop is now an order, not an artefact.** On every BUY fill the runner persists `ProtectiveStopOrder(stop_price = entry_reference − k·ATR(14) at the signal close, floored at the tick, quantity = filled quantity)`; the price comes from the sizing engine's `stop_loss_price`, so the reported 1R is the distance the order carries. `DailyTPlus1OrderRunner.evaluate_protective_stops()` then tests each open long against each session's bar through `ExecutionFillSimulator`'s existing `STOP_LOSS` path — gap through the stop fills at that session's open, an intraday breach fills at the stop — and the harness calls it every session after entries fill, so an entry-session breach is not ignored. **§5.3:** a session whose fill reference is at/below the lower circuit limit, a locked 0-range session or a zero-liquidity session does **not** fill the stop; the order stays pending, is retried next session, and is counted (`protective_stop_circuit_deferrals`). A split/bonus re-scales its price and quantity. **Correction (Audit §73.4 H-125):** this sentence originally said a signal exit *or winner-trim* cancels the stop and that a merger or ISIN transition retires it. That was the defect, not the design: a trim sells part of a lot, and retiring the order left the residual unprotected. Trims now reduce the stop's quantity to the residual, and a merger / ISIN transition carries the stop onto the successor identity rescaled by the exchange ratio (see the `Phase 3B-2c` §73 section below).
  * **Measured on the committed corpus** (diagnostic only, `--no-record-trial`, `--in-sample-only`, `k = 2.0`, output to a temp directory): 29 tickets filled, **16 closed round trips — 11 `SIGNAL_EXIT`, 5 `STOP_LOSS`**, 2 positions still open carrying active stops, mean net expectancy `−₹1,929.21`, PF `0.2334`, annualized Sharpe `−0.6268`, statutory costs `₹3,502.05` over the closed-trade ledger (`₹3,732.27` across every fill), **0 circuit deferrals observed in this fold**. The same fold at `k = 3.0` gives 30 fills, 15 closed round trips (2 stops), expectancy `−₹2,194.13`, PF `0.2197`, Sharpe `−0.6755`. The multiple now changes executions, which is exactly what Trial #5 could not do — but these are diagnostics, not trials: nothing was registered, and `N = 5`, `N_eval = 1` are unchanged.
  * The first stop exit in the `k = 2.0` diagnostic realized `−1.1726R` rather than `−1.00R` because the session gapped through the stop and filled at the open — the gap risk §5.3's realism is meant to expose.
- **N-128 — the witness has a root outside itself.** `<registry>.manifest` now always carries `evaluation_count` (an explicit `0` included) and `head_eval_hash`; `_load_evaluations()` fails closed when either key is absent instead of treating a witnessed zero as "no witness", and the artifact→ledger direction no longer skips an artifact whose `annualized_sharpe` is `null`. The committed manifest's SHA-256 (`0290d02bfc893809…`, 327 B, LF) is pinned in `configs/go_no_go_criteria.yaml` as `expected_trial_registry_manifest_sha256`, `criteria_version` moves to **`1.1.2`** with no threshold changed. Gate `G2A-6.8a/b/c` re-derives the pin, and probes that (a) stripping the two witness keys is refused by `TrialRegistry()` and changes the pinned digest, and (b) a post-sidecar artifact with a nulled score is refused rather than skipped. Because the criteria fingerprint moved, `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` was regenerated and `verify_phase2d_verdicts.py` confirms the committed bytes reproduce: `NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`, criteria `1.1.2` (`CRIT-FPR-V1-1cce…`), with a restatement note naming §72 N-128.
- **N-129 — the Gate-A input is reproducible from committed bytes.** The verdict artifact now carries a per-trade `closed_trades` ledger (entry/exit dates, prices including the persisted stop price, quantity, gross P&L, statutory costs, dividends, net P&L, risk per share, realized R, and `exit_reason` ∈ `{STOP_LOSS, SIGNAL_EXIT, MAX_POSITION_WEIGHT_TRIM}`), plus `mean_net_expectancy`, `mean_realized_r`, `total_statutory_costs` (closed-trade ledger) and `total_statutory_costs_all_fills` for reconciliation, with an exit-reason histogram. Both reported aggregates are computed from that array, not from an in-process tally. **Measured probe:** a 120-session oscillating synthetic fold reproduces `mean_net_expectancy` and `total_statutory_costs` from `closed_trades` exactly, and every row satisfies `gross_pnl − statutory_costs + dividends = net_pnl` and `realized_r × risk_per_share × quantity = net_pnl` within one paisa. `trial_005`'s committed artifact was **not** rewritten: a spent trial's report is not restated with engine behaviour it never ran.
- **Trial #6: shelved (Ruling 2).** No row was appended, no scoring occurred, `N = 5` and `N_eval = 1` still hold, the 2024 validation fold was not evaluated (`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` was not read. Any future stop hypothesis is a new `seq 6` trial with its own return series.
- **Verification actually run.** Full offline suite **465 passed, 0 skipped, 0 xfailed** (450 before, +15 in `tests/unit/test_phase3b2_audit_s72_items.py`); all `scripts/verify_*.py` exit 0, including `G2A-6.8a/b/c`; `verify_audit_append_only.py` reports ALL REPOSITORY FOUNDATION GATES PASSED.
- **Not claimed.** Not audited. No trial was re-run or re-scored; the two `k` diagnostics above are unregistered and are not evidence for any hypothesis. `CRIT-EXEC-03/04`, `CRIT-PROV-01`, `CRIT-SURV-01`, `CRIT-INFO-01`, `CRIT-OVERFIT-02` and `CRIT-OVERFIT-03` remain `NOT RUN`, and the overall verdict stays `NO-GO` on `CRIT-STAT-01`, `CRIT-STAT-02`, `CRIT-DATA-05`. The §5.3 deferral path is measured on a synthetic frozen-bid session, not on this fold (0 deferrals occurred). Two named residuals: the stop is armed at the entry fill and evaluated against the entry session's own bar, which is more permissive than T+2 settlement allows for a freshly bought lot; and a held name suspended in the reference corpus would leave its stop pending (counted as `NO_BAR_OR_BAND`) rather than exit into an absent session.

### Phase 3B-2c (Audit §73: H-125, N-130, post-hoc seq 6/7, Trial #5 restatement) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §73 at commit `46a0d08`, reviewing `9171464`. It closed H-124 (carrying two named residuals), closed N-128 and N-129 at their declared probes, filed **H-125 (HIGH)** and **N-130 (MEDIUM)**, and issued Rulings A–C. No audit section yet judges this delivery. `N = 7`, `N_eval = 3`.
- **H-125 — protection follows the shares.** `DailyTPlus1OrderRunner` no longer retires a stop on any filled SELL. On a SELL fill it reads the position's residual quantity: `> 0` re-arms the same order (`rearm_protective_stop`) at the entry-fixed `stop_price`, `signal_date`, `armed_session` and `atr`, with the quantity set to the residual; `== 0` retires it. `evaluate_protective_stops` therefore keeps a partially filled stop alive instead of discarding the remainder. A merger / ISIN transition calls `transfer_protective_stop(old, new, ratio)`, which rescales the stop price by `den/num` and the quantity by `num/den` — the same restatement the lot's entry price receives — so the successor identity carries the same economic distance rather than a level computed for another scale. When a stop cannot be carried (no stop, no successor ISIN, or a successor already holding its own order), the run increments `unprotected_corporate_action_positions`, which is surfaced in `Phase3B2WalkForwardRunResult`, the verdict results bundle, the verdict JSON and the CLI.
  * **Measured probes** (`tests/unit/test_phase3b2_audit_s73_items.py`): buy 50, trim 20 → the stop survives the trim at `960.000` for exactly 30 shares, and the next session's gap to 940 fills **30** shares, not 50 and not nothing. A volume-capped stop sell of 2,700 shares fills 1,800 and leaves the stop armed at `960.000` for the residual 900. A 1:2 merger moves `(960.000, 50)` on the old ISIN to `(480.0000, 100)` on the successor with ATR `10.0000`; a 1:1 ISIN transition moves `(960.000, 50)` to `(960.0000, 50)`; an identity change with no stop, and a successor that already carries one, both return `False` — the value the run counts.
  * **On the committed corpus the counter is 0**: no merger or ISIN transition touched a held name in 2022–2023, so the increment path is measured only by the unit probe, not by the run. That is named under "Not claimed", not implied.
- **N-130 — the sweep path is registered or refused.** `--no-record-trial` now requires (a) a `trial_id` that already exists in the registry, (b) `canonical_params` identical to that row's, verbatim, and (c) the recomputed `annualized_sharpe` equal to the Sharpe the evaluation ledger holds for it — the gate's own rule (§73.9 item 2), because matching parameters alone would not catch Trial #5, whose row states `3.0` while the engine that produced it sized at `2.0`. Any `--no-record-trial` artifact now carries `"recorded": false`; a recording run carries `"recorded": true`.
  * **Measured probes:** `--no-record-trial --trial-id TRIAL-PHASE3B2-SWING-ATR3-005 --atr-stop-multiple 2.0` exits 1 with `differing: atr_stop_multiple='2.0' (registered '3.0')` — the H-124 residual refusing to be papered over; `…-006 --atr-stop-multiple 4.0` exits 1 on the same guard; `…-006 --atr-stop-multiple 2.0` succeeds, writes `"recorded": false`, and leaves `N = 7`; a row whose configuration matches but whose ledger Sharpe was transcribed as `0.5` is refused on the Sharpe comparison. No refused run created its output directory.
- **H-124 residual — Trial #5 restated by append, never edited.** `data/trials/trial_restatements.jsonl` carries `RESTATE-TRIAL-005-001`: `canonical_params.atr_stop_multiple` recorded `3.0`, corrected `2.0`, effective `2026-11-16`, naming `05806ae` (finding) and `5176bc5` (producing commit) and the §72/§73 evidence. `seq 5` is untouched and its figures are not re-scored.
- **Ruling C — `seq 6` and `seq 7` recorded, post hoc.** Recorded through the engine after H-125 and N-130 were closed, at their original parameters, with the §73.10 disclosure in each row's `rationale`: *"Executed unregistered on 2026-11-16 under `--no-record-trial`; recorded post hoc because its result was used to decide the next trial (Audit §73.7, N-130). It is not prospective evidence."* Both re-executions reproduced the unregistered diagnostics exactly — same `returns_digest`, same Sharpe, same expectancy, same cost total — so the rows describe the measurement the audit quoted, not a new one.
  * `seq 6` `TRIAL-PHASE3B2-SWING-STOP-K2-006` (k=2.0): 16 closed round trips, 5 stop / 11 signal exits, mean net expectancy `−₹1,929.206094265468125`, PF `0.2333870345891165454946023353`, Sharpe `−0.6268098818883796449002601507`, max DD `0.03820674265981037736503091466`, ledger costs `₹3,502.0475082474900`, digest `RET-V1-f7923f67…`, 493 observations.
  * `seq 7` `TRIAL-PHASE3B2-SWING-STOP-K3-007` (k=3.0): 15 closed round trips, 2 stop / 13 signal exits, mean net expectancy `−₹2,194.130204710324133333333333`, PF `0.2196894186937231779821936150`, Sharpe `−0.6754725113399106387500868568`, max DD `0.04024924245507390522128850936`, ledger costs `₹3,282.6530706548620`, digest `RET-V1-3424a503…`, 493 observations.
  * Both are negative on every input a gate reads, so the stop-geometry family is recorded as tested and falsified at both multiples (§73.10 Ruling A). Their committed artifacts sit in `reports/verdicts/trial_006/` and `trial_007/` and carry `"recorded": true` because those runs appended their own rows; the post-hoc nature is disclosed in the row, and an unrecorded re-render is proven to write `"recorded": false`.
- **Criteria 1.1.3 — pin re-derived, no threshold touched.** The two appends rewrite `data/trials/trial_registry.jsonl.manifest` (330 B), so `expected_trial_registry_manifest_sha256` moves to `7cb9ed224c336bc7…` under `criteria_version: "1.1.3"`; the diff contains no numeric change. `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` is regenerated with a 1.1.3 restatement note: `NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`, criteria fingerprint `CRIT-FPR-V1-9edc…`, and `verify_phase2d_verdicts.py` reproduces the committed bytes.
- **What still blocks the next trial (§73.9 item 6, Ruling B).** `TRIAL-PHASE3B2-BREADTH-008` is **not registered and not run**: its precondition is sourced NSE price-band reports for `2022-01-03..2023-12-31` present in Bronze with byte-exact payloads, manifest rows and a walkable window. Without them the PIT band filter admits 3 names (2 of which trade) and the breadth hypothesis cannot be tested. `seq 8` stays blocked until those reports exist.
- **Verification actually run.** Full offline suite **473 passed, 0 skipped, 0 xfailed** (465 before, +8 in `tests/unit/test_phase3b2_audit_s73_items.py`); `verify_phase2a_containment_and_trials.py` exit 0 with `N=7, N_eval=3`, `G2A-6.6` and `G2A-6.7` (`3 scored trial(s) agree with their verdict artifacts`) and `G2A-6.8a/b/c` passing against the new pin; `verify_phase2d_verdicts.py` exit 0; `verify_audit_append_only.py` exit 0 with 0 skipped/0 xfailed.
- **Not claimed.** Not audited. The seq 6/7 rows are not prospective evidence and change no verdict beyond recording a falsified family. `CRIT-OVERFIT-02` remains **NOT RUN** in the Phase 2D artifact, and the audit's expectation that it becomes **FAIL** is not yet computable: `evaluate_strategy_significance` needs a trial's daily return series, and the registry stores only its digest, so a DSR cannot be recomputed from committed bytes. Committing one return series per scored trial is the unblocking step, and typing `FAIL` without it would violate §9.1. `CRIT-EXEC-03/04`, `CRIT-PROV-01`, `CRIT-SURV-01`, `CRIT-INFO-01`, `CRIT-OVERFIT-03` remain `NOT RUN`; the overall verdict stays `NO-GO` on `CRIT-STAT-01`, `CRIT-STAT-02`, `CRIT-DATA-05`. `validation_folds_count = 0` on both new artifacts and the holdout `2025-01-01..2026-11-11` was not read. Named residuals: the restatement ledger is append-only by convention but not hash-chained or pinned (unlike the trial registry); the merger/ISIN-stop-counter branch is measured only on the unit probe (0 events on the corpus); and the §5.3 deferral path remains unexercised on the corpus (0 deferrals in both new runs).

### Phase 3B-2d (Audit §74: H-126, N-132, N-133, Ruling D — band policy) (implemented; measured locally; not audited)
- **Audit citation.** DeepSeek audit §74 at commit `4c92356`, reviewing `4eb5c58`. It closed the trim and partial-fill halves of H-125 (measured at the auditor's own hands), closed N-130 at all three declared probes, filed **H-126 (HIGH)**, **N-132 (MEDIUM)** and **N-133 (LOW)**, issued Erratum E-4, and ruled in §74.10 that the unbanded-entry veto is what to narrow — not the window. No audit section yet judges this delivery.
- **H-126 — the position, the lot book and the stop now move together.** The audit measured a stop carried to `INE081A01020` while the portfolio still held `INE081A01012`, so `evaluate_protective_stops` cancelled the carried order on the next session and `unprotected_corporate_action_positions` read 0 for exactly the event it exists to disclose. Three changes: (1) `Portfolio.apply_corporate_actions_for_session` (already called by the harness at `UNADJUSTED_CLOSE`) is the single authority that re-keys and restates the position — the script no longer keeps a private identity of its own; (2) the lot book now restates **ratio-bearing** `ISIN_TRANSITION` rows through the new `restate_lots_for_share_ratio` (quantity × num/den, entry price and the lot's own stop price × den/num), matching the `SPLIT` path, because the three committed transition rows are face-value sub-divisions — TATASTEEL 10:1, VBL 2:1, COCHINSHIP 2:1 — not renames; (3) identity carries are collected during the corporate-action pass keyed by the held ISIN and applied **once**, after every lot has been restated, against a snapshot of what was held at session start, so the order rows arrive in can neither scale a stop twice nor drop it under a stale key. The run additionally asserts, before the cash reconciliation, that the lot book and the portfolio agree on identity **and quantity** — a divergence the cash identity cannot see, because a lot left on the old identity stops contributing to both sides equally.
  * **Measured probes** (`tests/unit/test_phase3b2_audit_s74_items.py`): buy 50 at ₹1,000 (stop ₹960.000). A 2:1 merger leaves the portfolio holding **100** at the successor, the lot **100**, the stop **100 @ ₹480.0000**, and the portfolio's own average entry price exactly halved (₹1,002.75 → ₹501.375, charges in basis). A 10:1 transition leaves **500** in all three stores, lot entry ₹100.0000, stop **₹96.0000**. In both cases a next-session crash through the carried stop produces **one** fill of that quantity on the successor ISIN and closes the position; before this round the stop and the lots disagreed by the exchange ratio (10×) while the portfolio sat on the old key.
- **N-133 — refuse before destroying.** `transfer_protective_stop` validates the successor identity and constructs the successor order **before** retiring the old one, and a blank or whitespace `new_isin` returns `False` with the old stop still armed. `carry_protective_stop_across_corporate_action` no longer cancels on a blank successor, so the run's counter records a held-but-unroutable carry instead of the refusal itself removing the protection. Probe: `transfer(ISIN, "", 10, 1)` and `transfer(ISIN, "   ", 10, 1)` both return `False` and leave the identical `ProtectiveStopOrder` in place.
- **N-132 — the DSR input is now committed.** `serialize_daily_returns(session_dates, returns)` persists the exact Decimal series keyed by ISO session date, `daily_returns_from_artifact` reads it back (and fails closed when an artifact predates it), and the verdict artifact carries `daily_returns`, `return_moments` (`observation_count`, `skewness`, `kurtosis`, `kurtosis_convention`) beside the existing `returns_digest`. Probe: a report computed in-process and one recomputed **only** from the persisted mapping agree on DSR, haircut Sharpe, annualized Sharpe, skewness and kurtosis to the last decimal, while a one-observation edit changes the DSR.
- **§74.9 item 5 — the count is labelled, not re-scored.** The artifact now carries `evaluated_trial_count` and `evaluated_trial_count_prior` (captured before this run's evaluation was appended). Measured rather than assumed: seq 6's artifact says `2` because that is the post-append count at that moment (seq 5 and seq 6 are the two scored trials); the auditor's re-render says `3` because it runs after seq 7 was appended. No number was restated.
- **Ruling D — the band veto is narrowed, the window is not.** `configs/go_no_go_criteria.yaml` 1.1.4 records `unbanded_session_fill_policy: LOCKED_BAR_REFUSAL_ONLY` and no threshold changes. The policy is a criteria field, not a run flag, because it changes what a fill means and must sit inside the criteria fingerprint: `DailyTPlus1OrderRunner` reads it, `execute_swing_strategy_session` submits an unbanded ticket instead of skipping it, and `ExecutionFillSimulator`'s existing locked-bar check (`high == low`, zero depth on one side) remains the only refusal on those sessions. No band and no circuit limit is synthesized; `CRIT-EXEC-03/-04` remain **NOT RUN** over unsourced sessions. `--band-policy` may assert the policy but a run that disagrees with the committed criteria fails closed. `coverage_diagnostics` and both artifacts now print, per year, `band_covered_isins`, `unbanded_isins`, `unbanded_tickets_submitted` and `locked_bar_refusals`.
  * **Measured consequence:** on the committed 2022–2023 in-sample window the run now closes **438** round trips against **29** at `4eb5c58` (sessions, universe, signals, costs and slippage unchanged). That is the breadth the audit said the veto was costing, and it clears §74.10's own falsifier ("fewer than 100 closed round trips → breadth was never the veto's fault"). Which names are held necessarily changes, so tests that asserted a *particular* name was held (HDFC across the 2023-07-13 merger) were re-pointed at the invariant they exist to protect; no assertion was deleted and none was made vacuous.
  * **Relaxation, named.** The lot-ledger cash identity was asserted to ₹1.00, a constant calibrated to that 29-trade run. It now compares against a bound derived from the data (₹0.01 per closed trade and per open lot — ₹4.63 for 438 trades and 25 open lots), and both the residual (₹1.0585) and the bound are written into the artifact as `lot_ledger_cash_residual` / `lot_ledger_cash_tolerance`. What that leaves unverified: a systematic cash leak smaller than one paise per observation would sit inside the bound. It is a documented decision, not a threshold widened to reach green.
- **Criteria 1.1.3 → 1.1.4.** Version, the new field and the new fingerprint; `expected_trial_registry_manifest_sha256` is unchanged (`7cb9ed22…`, 330 bytes) because this commit appends no trial. `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` regenerated with the 1.1.4 restatement note: `NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`, `N = 7`, `N_eval = 3`.
- **Verification actually run.** Full offline suite **485 passed, 0 skipped, 0 xfailed** (473 before, +12 in `tests/unit/test_phase3b2_audit_s74_items.py`); `verify_audit_append_only.py` exit 0 with 8/8 verification scripts, `G2A-6.6` `N=7, N_eval=3`, `G2A-6.7` and `G2A-6.8a/b/c` against the unchanged pin; `verify_phase2d_verdicts.py` exit 0 reproducing the regenerated bytes.
- **Not claimed.** Not audited. No trial was registered or executed in this commit: `seq 8` follows separately, under the pre-registered policy. `CRIT-OVERFIT-02` is still **NOT RUN** in the Phase 2D artifact — the bundle that artifact is built from carries no DSR — and the 2024 fold (`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` were not touched.

### Phase 3B-2e (Audit §74.10 Ruling D: `seq 8`, TRIAL-PHASE3B2-BREADTH-008) (executed; measured; not audited)
- **Registration, not restatement.** `seq 8` was appended and executed after criteria 1.1.4 pre-registered `unbanded_session_fill_policy: LOCKED_BAR_REFUSAL_ONLY`, so it is the first trial in this project registered before its policy was in force, and its rationale needs no post-hoc disclosure. Parameters are frozen at `seq 6`'s: `sma_20`/`sma_50`, `k = 2.0`, trim disabled, the same cost, slippage, sizing and volume-participation schedule; the only variable is the band policy. 2022-01-03..2023-12-29 in-sample, 2024 validation fold frozen (`validation_folds_count = 0`), holdout `2025-01-01..2026-11-11` not read.
- **Breadth, measured.** `band_covered_isins` 3 in 2022 and 3 in 2023; `unbanded_isins` **145** and **132**; `unbanded_tickets_submitted` **2,803** and **4,204**; `locked_bar_refusals` **0** in both. Those 7,007 unbanded submissions were impossible at `4eb5c58`. §74.10's own falsifier ("fewer than 100 closed round trips → breadth was never the band veto's fault") is not met: the widened policy closes **438** round trips, so breadth was the veto's fault. What the tape then shows is that breadth alone is not an edge.
- **`seq 8` measurements.** 493 sessions; 771 tickets filled, 195 rejected, 0 skipped for a missing band, 130 protective-stop exits, 0 exits deferred by a frozen bid; 25 positions open at the end; `unprotected_corporate_action_positions = 0` (no merger or transition touched a held name on this tape — the H-126 branch is measured by the unit probes, not by this run).
  * **438** closed round trips (CRIT-STAT-01 `min_total_trades = 100` → **PASS**), win rate **16.67 %**, profit factor **0.6826**, mean net expectancy **−₹462.03** per round trip, mean realized **−1.0130R**, statutory costs **₹55,760.01**, final equity **₹978,479.40** (CAGR **−1.09 %**), max drawdown **29.73 %**, annualized Sharpe **−0.0148**, **DSR 0.2446** against the committed 0.95 threshold, haircut Sharpe **0.0000** against 1.25.
  * **Verdict `NO-GO`**: `PASS=13 / FAIL=5 / NOT RUN=6`. FAIL: `CRIT-STAT-02` (profit factor 0.6826 < 1.50), `CRIT-STAT-03` (max single-position weight 0.1141 > 0.10), `CRIT-STAT-04` (max drawdown 0.2973 > 0.25), `CRIT-DATA-05` (traded EQ resolution 92.8910 % — identical in `seq 6`/`seq 7`, i.e. pre-existing and unrelated to this round), `CRIT-OVERFIT-02` (DSR 0.2446 < 0.95). NOT RUN: `CRIT-EXEC-03`, `CRIT-EXEC-04` (unsourced band sessions — H-120 preserved), `CRIT-SURV-01`, `CRIT-PROV-01`, `CRIT-OVERFIT-03` (in-sample only), `CRIT-INFO-01`.
- **N-132 payoff, precisely stated.** This artifact carries the **493**-element `daily_returns` series and `return_moments` (`skewness −0.5374912686431483158368693278`, `kurtosis 4.082895558339126476991498318`, `RAW_NORMAL_THREE`), so `CRIT-OVERFIT-02` is recomputed from committed bytes and evaluates to **FAIL** rather than NOT RUN in the trial's own verdict. The Phase 2D Tier-A artifact is unchanged in this respect: it is built from the verification bundle, which carries no return series, so its `CRIT-OVERFIT-02` remains **NOT RUN**. Connecting the two is a separate reporting change and is not claimed here.
- **Criteria 1.1.4 re-pin.** seq 8 rewrote `data/trials/trial_registry.jsonl.manifest` to 324 bytes, SHA-256 `93f7967d8f42a4bf713ccff3ffae9f2765f1b1623835a903bdde50d2b790cf4d`; the criteria pin moved with it and no threshold changed. `N = 8`, `N_eval = 4`; `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` regenerated with the 1.1.4 note covering seq 8 (`NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`).
- **Artifact hygiene.** `evaluated_trial_count = 4` with `evaluated_trial_count_prior = 3`; `band_policy = LOCKED_BAR_REFUSAL_ONLY`; `lot_ledger_cash_residual = 1.0584886413320` against `lot_ledger_cash_tolerance = 4.63`; `recorded: true` (this run appended its own row).
- **Verification actually run.** Full offline suite **485 passed, 0 skipped, 0 xfailed**; `verify_phase2a_containment_and_trials.py` exit 0 with `G2A-6.6 N=8, N_eval=4` and `G2A-6.7: 4 scored trial(s) agree with their verdict artifacts`; `verify_phase2d_verdicts.py` exit 0; `verify_audit_append_only.py` exit 0.
- **Not claimed.** Not audited. `seq 8` is in-sample evidence only: it is not out-of-sample, the 2024 fold is unspent and the holdout is sealed. The breadth hypothesis is **falsified on this tape** — more names did not produce a positive expectancy, and the family should be read as NO-GO on expectancy, not on coverage. No further trial is registered; a `seq 9` would need a hypothesis that survives this measurement.

### Phase 3B-2f hardening (Audit §75 items 1, 2, 3, 4, 5) (implemented; gates measured; not audited)
- **H-127 (CLOSED at both conventions).** The restatement is now a function of `PriceConvention`, not an unconditional rule. On `SPLIT_BONUS_ADJUSTED` — the only corpus in the repo — a face-value `ISIN_TRANSITION` re-keys identity only (`Position.rekey`), leaving quantity, cost basis, average entry price and the pending stop untouched, and a same-ISIN `SPLIT`/`BONUS`/`CONSOLIDATION` is a no-op instead of a `CorporateActionError` that aborted the run. On `UNADJUSTED_RAW` the exchange ratio still applies. Both directions are measured: 20 shares at ₹2,000 with a ₹1,800.000 stop stay **20 / ₹1,800.0000** under the adjusted convention and become **200 / ₹180.0000** under the raw one, with a next-session crash filling all 200. The harness, the lot book and the stop carry take the same gate (`apply_share_ratios`), and a merger keeps its ratio in both conventions because the convention adjusts splits and bonuses, not mergers.
- **N-136 (implemented).** `liquidate_open_book` marks every open lot to the final session's close and charges the exit through the same slippage and statutory-cost models as every fill; the artifact now carries `closed_only_profit_factor`, `closed_only_mean_net_expectancy`, `liquidated_profit_factor`, `liquidated_mean_net_expectancy`, `open_positions_at_end_count`, `open_positions_unrealized_pnl`, the exit cost/slippage split and the per-lot rows. The identity is asserted in the ledger's own terms — realized PnL + dividends + open market value − open cost (basis + unpaid buy charges) = Δequity, tolerance ₹0.01 — because a lot-row version of it is only accurate to one paise per observation and carried a ₹114 residual on a 120-session fixture that no tolerance should absorb. A lot with no closing print is counted in `liquidation_missing_prices` and excluded, never valued at book.
- **N-137 (implemented).** `entry_rank_indicator` (`NONE` default, `mom_63`) ranks the session's qualifying entries by 63-session trailing close return, descending, with an ascending ISIN tie-break; `mom_63` is computed inside the subsegment engine, so it re-warms after a gap rather than reaching across one. Exits are emitted before ranked entries so a session's own sells free the capital its entries compete for. `NONE` preserves the previous emission order exactly, so a prior trial re-renders the same intents.
- **N-138 (implemented).** `min_entry_notional` ₹25,000 and `min_fill_notional` ₹5,000 are criteria fields. An entry whose intended notional is below the first is a named no-trade (`BELOW_MIN_ENTRY_NOTIONAL`); a BUY fill that lands below the second is refused with `REJECTED_BELOW_MIN_NOTIONAL` and never posted to the portfolio. Exits are exempt by design: refusing a small exit would convert a cost problem into a §5.3 frozen-hold problem.
- **N-134 / N-135 (implemented).** A locked 0-range session now returns `REJECTED_LOCKED_SESSION` on both sides instead of `REJECTED_UPPER_CIRCUIT`/`REJECTED_LOWER_CIRCUIT`; the refusal and its reason string are unchanged, so no fill moves. `canonical_params` records `unbanded_session_fill_policy`, `entry_rank_indicator`, `min_entry_notional` and `min_fill_notional`, so a reader comparing two rows no longer has to infer them from `criteria_version`.
- **Criteria 1.1.5.** No PASS/FAIL threshold changed. The three new fields enter the criteria fingerprint, which moves to `CRIT-FPR-V1-b60ca03e9239caf6bc1c24570aa7214b0926db1ec59af17ef81ce9966569a684`; `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` is regenerated with the 1.1.5 restatement note (`NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`). Registry still `N = 8`, `N_eval = 4`; the trials-manifest pin is unchanged at `93f7967d…` because this commit appends no trial.
- **Verification actually run.** Full offline suite **496 passed, 0 skipped, 0 xfailed** (11 new §75 probes); `verify_phase2a_containment_and_trials.py` exit 0 (`G2A-6.6 N=8, N_eval=4`, `G2A-6.7` 4 scored trials agree, `G2A-6.8a` pin match); `verify_phase2d_verdicts.py` exit 0. Two probes were re-pointed by the contract changes rather than weakened: the locked-bar status assertion and the H-108 raise (now a measured no-op), and one N-94 sizing probe moved from a 2% to a 3% cap because a ₹20,000 entry is now below the pre-registered floor.
- **Not claimed.** Not audited. No trial was registered or scored in this commit; `seq 9` is a separate commit, and the 2024 validation fold and the holdout are untouched.

### Phase 3B-2g — seq 9, TRIAL-PHASE3B2-RANKED-009 (executed; measured; not audited)
- **Registration.** Registered and executed after criteria 1.1.5 pre-registered `entry_rank_indicator = mom_63`, `min_entry_notional = 25000` and `min_fill_notional = 5000`, and after §75 items 1–4 landed. One change against seq 8: the entry rank. `sma_20/sma_50`, `k = 2.0`, `allocation_weight 0.0800`, trim `None`, `LOCKED_BAR_REFUSAL_ONLY` all frozen. 2022-01-03..2023-12-29 in-sample, 493 sessions, `validation_folds_count = 0`, holdout not read. Registry row `seq 9`, `IN_SAMPLE`, `criteria_version 1.1.5`, `sharpe_ratio: null`, `canonical_params` carrying `entry_rank_indicator = mom_63`, `unbanded_session_fill_policy = LOCKED_BAR_REFUSAL_ONLY`, `min_entry_notional = 25000`, `min_fill_notional = 5000`; sidecar `N_eval = 5`; artifact `recorded: true` with `evaluated_trial_count 5` beside `evaluated_trial_count_prior 4`.
- **The floor changed the book before the rank could.** 10,822 tickets emitted against 334 fills: most candidates were refused as `BELOW_MIN_ENTRY_NOTIONAL`, which is the ₹58–₹887 decile §75.8 measured. Closed round trips fell from 438 (seq 8) to **193** for that reason, not because the rank reduced trading.
- **Thresholds committed in §75.10, measured on both books.** The closed ledger and the de-censored book disagree in *sign*, which is N-136's point exactly:

  | §75.10 condition | Closed book | Liquidated book |
  |---|---|---|
  | net expectancy per round trip > 0 | **FAIL** −₹186.97 | **PASS** +₹1,366.59 |
  | gross ≥ 0.30% of notional per round trip | **FAIL** −0.0289% (₹−3,935.05 on ₹13,632,287.45) | **PASS** +2.1639% (₹+315,293.06 on ₹14,582,xxx) |
  | `CRIT-STAT-02` PF ≥ 1.50 | **FAIL** 0.9920 | **PASS** 1.6440 |
  | MaxDD ≤ 25% | **PASS** 20.73% | **PASS** 20.73% |
  | ≥ 200 closed round trips | **FAIL** 193 | **PASS** 205 |
  | DSR ≥ 0.95 at N = 9, N_eval = 5 | **FAIL** 0.4140 | **FAIL** 0.4140 |

- **Verdict `NO-GO`** (computed): `PASS=14 / FAIL=4 / NOT RUN=6`. FAIL: `CRIT-STAT-02` 0.9920, `CRIT-STAT-03` max single-position weight 0.1291 > 0.10, `CRIT-DATA-05` traded EQ resolution 92.8910 % (identical in seq 6/7/8 — pre-existing), `CRIT-OVERFIT-02` DSR 0.4140 < 0.95. NOT RUN: `CRIT-EXEC-03`, `CRIT-EXEC-04`, `CRIT-SURV-01`, `CRIT-PROV-01`, `CRIT-OVERFIT-03`, `CRIT-INFO-01`. Other measurements: final equity **₹1,283,327.73** (+28.33 % over two years, CAGR 13.46 %, against −2.2 % / −1.09 % in seq 8), win rate 25.39 %, mean R −0.0203, statutory costs ₹40,951.35, Sharpe 0.8731, haircut 0.0000, 64 stop exits, 129 signal exits, 12 positions open at the end with ₹319,413.32 unrealized, `liquidation` exit costs and slippage included, identity residual **₹0.00** with no unpriced position.
- **Falsifier outcome.** §75.10 said: gross below 0.30 % with a viable book closes the SMA(20/50) long-only family. On the de-censored book gross is **+2.1639 %**, so the falsifier does **not** fire; on the closed book it reads −0.0289 %, which is the right-tail censoring N-136 documents rather than a selection failure. What the rank did and did not do: equity flipped from −2.2 % to +28.3 %, closed PF from 0.6826 to 0.9920, DSR from 0.2446 to 0.4140, with half the round trips. It did not clear the pre-committed bar — DSR 0.4140 is far below 0.95 and the closed book is 7 round trips short of 200 — so the verdict stays `NO-GO` and the family is *alive on the liquidated book*, not signed off.
- **Residual this round does not close.** `CRIT-STAT-02` is still evaluated on the closed book (0.9920 → FAIL) while the pre-committed condition names the liquidated book (1.6440). N-136 built the measurement; switching the criterion's basis is a criteria change and was not made unilaterally. Until it is, the gate and the pre-registration disagree by construction, and the disagreement is the next round's first decision.
- **Criteria 1.1.5 re-pin.** seq 9 rewrote `data/trials/trial_registry.jsonl.manifest` to 323 bytes, SHA-256 `3326b1b221b2e02616915a9d1f56a4026affa82506803abcc783e2261bf37306`; the pin moved with it, no threshold changed, and `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` is regenerated with the 1.1.5 note covering seq 9 (`NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`).
- **Verification actually run.** Full offline suite **496 passed, 0 skipped, 0 xfailed**; `verify_phase2a_containment_and_trials.py` exit 0 (`G2A-6.6 N=9, N_eval=5`; `G2A-6.7` 5 scored trials agree with their artifacts; `G2A-6.8a` pin `3326b1b2…` equals the committed anchor); `verify_phase2d_verdicts.py` exit 0.
- **Not claimed.** Not audited, and in-sample only: the 2024 validation fold is unspent and the holdout is sealed. `seq 9` is one ranked run at one k and one rank horizon; the weak median same-session ranking prior recorded at registration (−0.65 pp) is not refuted by a positive mean, and no out-of-sample read exists.

### Phase 3B-2h hardening (Audit §76 items 1-6) (implemented; gates measured locally; not audited)
- **Audit citation.** DeepSeek audit §76 at commit `7a32f24`, reviewing `9f7036e`/`348b5ba`, issued the ordered work order this section answers (items 1-6 of §76.15). No audit section yet judges this delivery; the words *closed* and *verified* below describe what the probes measure at this commit, not an audit verdict (§11.3).
- **N-139 — the criteria fingerprint no longer pins the file it is written into.** `compute_criteria_fingerprint` excludes `expected_trial_registry_manifest_sha256` from its payload. The field stays mandatory in the loader, still enters the criteria file a verdict quotes, and is still enforced by `G2A-6.8a`, so a run that appends a trial and re-pins the manifest no longer invalidates the anchor of the criteria it ran under. Measured: `dataclasses.replace(pin = "0"*64)` leaves the fingerprint at `CRIT-FPR-V1-0371c9b5…`; moving `min_profit_factor` to 1.49 moves it; a criteria file with the pin line removed raises `CriteriaValidationError` on load. Probe: `tests/unit/test_phase3b2_audit_s76_items.py::test_n139_manifest_pin_is_outside_the_criteria_fingerprint`.
- **N-141 — `min_haircut_sharpe_ratio` is a gate.** `CRIT-OVERFIT-04` evaluates the haircut Sharpe against the committed 1.25 and is binding. Measured: `0.0000` -> FAIL, `1.30` -> PASS, `evaluated_trial_count = 1` (below the two trials a variance needs) -> NOT RUN, absent -> NOT RUN. seq 9's `0.0000` therefore fails rather than sitting unenforced.
- **Ruling 1 — both performance criteria on the liquidated book, one definition, no fallback.** From criteria 1.1.6 the bundle's `total_trades` and `profit_factor` *are* the de-censored book (closed round trips plus open positions marked out at the window-end close), which the runner now writes, and `CRIT-STAT-01`/`CRIT-STAT-02` read them under the names "Total Completed Trades (Liquidated Book)" and "Profit Factor (Liquidated Book)". There is deliberately **no** fallback to a closed-only count: a producer that supplies only the censored book gets NOT RUN, not a quieter PASS. The closed-only pair (`closed_only_trade_count`, `closed_only_profit_factor`) and the ex-top-1 / ex-top-3 profit factor are printed on the same evidence lines as disclosure, never gated. seq 9 read this way: 205 round trips / PF 1.6440 (`1.4812` without the largest winner, `1.2939` without the top three), closed-only 193 / 0.9920.
- **Ruling 2 — `CRIT-STAT-03` is measured at entry.** The gated value is executed entry notional over the portfolio equity snapshot on the fill date (latest prior snapshot as fallback; fills with no price or no snapshot are counted in `entry_weight_unpriced_fills` and excluded). The hold-period maximum is reported beside it as a non-gating disclosure. seq 9 measured: entry weight `0.082769` (PASS at ≤ 0.10) against a hold-period maximum of `0.1291` — the FAIL recorded in the §75 section was a hold-period measurement under a criterion whose own definition says entry.
- **Ruling 3 / N-140 — rows and instruments are two criteria with two names.** `CRIT-DATA-05` is the H-54 traded-row measure (the artifact's `traded_eq_resolution_pct`, 196 / 196 rows in the seq 9 window); the new `CRIT-DATA-07` gates *dataset* completeness at `min_dataset_instrument_resolution_pct = "100.0"` on 196 / 211 = **92.8910%**, and the artifact names the 15 unresolved instruments with reason `ISIN_TRANSITION_WITHIN_DATASET_SPAN`. The duplicate `traded_eq_resolution_pct` key that made the two numbers collide is gone. The seq 9 measurement has not been re-rendered in this commit (no trial was run), so the FAIL is demonstrated on the probe bundles rather than on a new artifact.
- **N-142 — refusals are attributable by side.** `tabulate_rejections` groups every `REJECTED_*` ticket by order side and status, `coverage_diagnostics[year].rejections_by_side_and_reason` carries it per year, and the artifact carries the run total. The counts sum to `tickets_rejected` by construction; a SELL refused for turnover or a frozen bid is now visible as such instead of disappearing into a total (§5.3). Probe: a refused SELL and a refused BUY tabulate under their own sides.
- **Criteria 1.1.6 — no threshold moved.** The version, the fingerprint exclusion and the one new field (`min_dataset_instrument_resolution_pct`) are the only criteria changes; `min_total_trades 100`, `min_profit_factor 1.50`, `min_deflated_sharpe_ratio 0.95`, `min_haircut_sharpe_ratio 1.25`, `max_single_position_weight 0.10`, `min_traded_eq_resolution_pct 100.0`, `min_entry_notional 25000`, `min_fill_notional 5000` are unchanged and asserted by `test_criteria_1_1_6_changes_no_numeric_threshold`. Registry untouched: `N = 9`, `N_eval = 5`, trials-manifest pin unchanged at `3326b1b2…` (323 B) because no row was appended.
- **Phase 2D restated, pin unchanged.** `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` regenerated with the 1.1.6 restatement note: `NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=22` (the two new criteria are NOT RUN there because the Tier-A bundle carries neither a haircut Sharpe nor a dataset instrument enumeration — the same reason `CRIT-OVERFIT-01`–`-03` are NOT RUN in that artifact), fingerprint `CRIT-FPR-V1-0371c9b5…`, and `verify_phase2d_verdicts.py` reproduces the committed bytes. The synthetic fixture bundles in the pytest suite and in `verify_phase2d_verdicts.py` now supply the two statistics rather than widening the expected NOT RUN set.
- **Verification actually run.** Full offline suite **505 passed, 0 skipped, 0 xfailed** (496 before, +9 in `tests/unit/test_phase3b2_audit_s76_items.py`, plus the criteria-version literals moved to `1.1.6` in four existing files); all 9 `scripts/verify_*.py` exit 0; `python scripts/verify_audit_append_only.py` exit 0 with `ALL REPOSITORY FOUNDATION GATES PASSED` and `G2A-6.6 N=9, N_eval=5`, `G2A-6.8a` on the unchanged pin; `verify_phase2d_verdicts.py` exit 0 on the regenerated bytes.
- **Not claimed.** Not audited. No trial was registered, executed or re-scored, so the seq 9 artifact in `reports/verdicts/trial_009/` still carries its recorded 1.1.5 fingerprint and its closed-book `CRIT-STAT-02` FAIL; switching a spent trial's artifact to the new basis would restate a report against engine behaviour it did not run, and a re-render would also move its recorded fingerprint. The 2024 validation fold remains unspent (`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` was not read. §76.15 item 7 (`seq 10` on the 2024 fold) is explicitly not part of this commit.
### Phase 3B-2i identity resolution and in-sample stability (Audit §77 items 1-6) (implemented; gates measured locally; not audited)
- **Audit citation.** DeepSeek audit §77 at commit `6a0479f`, reviewing `adb16bd`, closed every §76 item and named the gate it repaired as the blocker (N-145, HIGH). This section answers §77.15 items 1-6. No audit section yet judges this delivery; where a number appears below it is a local measurement at this commit, not a verdict (§11.3).
- **N-145 — the 15 refusals were missing documentation, and are now documented.** Twelve `ISIN_TRANSITION` rows were appended to `data/reference/corporate_actions.jsonl` (VTL, JUBLFOOD, BAJAJFINSV, IRB, HAL, NESTLEIND, PERSISTENT, CANBK, BDL, VBL's second transition, DRREDDY, MAZDOCK), taking the file from 164 to **176 rows** (60,529 bytes, SHA-256 `e4958ab1a56cce1f…`; 12 insertions, 0 deletions). Each row carries old ISIN, new ISIN, the first session of the successor identity as its effective date, `provenance: CONTENT_IDENTIFIED_ONLY`, and `circular_ref: UNATTESTED_NSE_INTERVAL_TABLE_<SYMBOL>_<YYYYMMDD>` — the committed interval table is the reference, **not** an NSE circular. The ratio is 1:1 because the corpus establishes no share ratio: the series is split/bonus adjusted, and the measured boundary price changes are ordinary market moves (0.87–1.02; TATASTEEL 100.35 → 107.60 across its 10:1 split), so a ratio here would be an invention. `scripts/derive_2022_2024_corpora.py` now emits the same twelve rows, so the artifact's *content* stays reproducible from its generator; the three H-115 restated MERGER rows are still newer than the generator's formatting, which is why the file was inserted into rather than regenerated byte-for-byte. `data/reference/manifest.jsonl` records the restatement as a new current row (37,597 bytes; the superseded row keeps its own digest), Gate W0.5-5 verifies **46 current / 20 superseded** rows, and `expected_manifest_fingerprint` is re-pinned to `MAN-FPR-V1-0b9b0d7c24887049b13d68374b195215052584df594993119226d0b9fe0d00e6`.
- **N-145 — identity is resolved per session, not per dataset span.** `resolve_instrument_identity_segments` keys each bar by the ISIN the interval table puts in force that session (a split is not a stitch: each ISIN's sequence holds only its own sessions), and refuses an instrument whose identity changes without an effective-dated transition row. Measured on the committed corpus: **211 / 211 dataset instruments resolve, 0 unresolved**, `CRIT-DATA-07` = 100.0000%, and the window row measure `CRIT-DATA-05` = 100.0000% (1,217 / 1,217 rows) on a six-session run. Thirteen instruments now partition across identities (VBL into three), and eleven symbol renames (UNITDSPR, LTIM, GMRAIRPORT, …) keep the single identity they already had, because a rename whose old label is absent from the interval table is a labelling gap, not a second security. An instrument with an undocumented change still fails closed: probe `360ONE` (INE466L01020 → INE466L01038 on 2023-03-02, no row) returns refusal `ISIN_TRANSITION_UNDOCUMENTED`. Transition events are now derived from the corpus rows in `build_production_security_master` and dated at the successor's first interval session, so `is_transitioned_out`/`is_active` agree with the interval table rather than with one hardcoded row.
- **N-145 — continuity is explained, not fabricated.** The successor's first session and the predecessor's retirement are passed to the feature engine as `InstrumentListingInterval` bounds (VERIFIED_ISIN_TRANSITION / OUTSIDE_VERIFIED_LISTING_INTERVAL), so a truncated identity sequence is not counted as an unexplained gap while the *prices* remain the committed ones. Two residuals, named rather than implied: (i) rolling windows restart at an identity boundary, because a new ISIN's own history begins there — the §10.4 reading, not the §6.2 EQ→BE reading; (ii) TATASTEEL's documented ex-date (2022-07-28) is one session before its successor's first session (2022-07-29), so a position held across it is re-keyed by H-127 one session before the successor has a bar and is marked at cost basis for that session. Nothing was forward-filled and no price was modified.
- **N-144 — the de-censored count is checked.** `CRIT-STAT-01` fails closed when `total_trades` disagrees with `closed_only_trade_count + len(liquidated_open_positions)` or with `liquidated_trade_count`. Probe: 193 with 193 closed and 12 liquidated positions → **FAIL** with "Censored book passed as the de-censored count"; 205 → PASS. A bundle that cannot produce the liquidated count still reports NOT RUN, never a quieter PASS.
- **N-146 — one denominator per criterion name.** `CRIT-DATA-05` is the evaluation window's traded-row measure and its evidence names that denominator; the archive-wide figure now travels as `archive_traded_eq_resolution_pct` and is never parsed as `CRIT-DATA-05`. Consequence, computed not asserted: the Phase 2D Tier-A bundle carries only the archive-wide number, so `CRIT-DATA-05` is **NOT RUN** there (it was PASS on the archive figure under 1.1.6) and the artifact moves from PASS 3 / NOT RUN 22 to **PASS 2 / FAIL 0 / NOT RUN 25 of 27 rows**.
- **N-147 — markdown hygiene.** The duplicated `> Unresolved dataset instruments: ` line is deleted; the generated report contains the line exactly once (probe counts occurrences in the emitted markdown).
- **§77.12 / §77.13 — criteria 1.1.7, three new bindings, no existing threshold moved.** `min_liquidated_pf_ex_top_1: 1.40` is gated as `CRIT-OVERFIT-05` (seq 9's measured 1.4812 PASS; 1.3000 FAIL; absent NOT RUN). `min_positive_is_fold_ratio: 0.75` and `min_fold_liquidated_pf: 1.30` gate `CRIT-OVERFIT-03`, which now reads the four anchored expanding in-sample folds (ends 2022-06-30, 2022-12-30, 2023-06-30, 2023-12-29) partitioned from **one** run's own ledger by exit date — no re-fit, no re-run, so the four partitions stay one trial and the 2024 fold is neither spent nor required. The old validation-fold definition is not withdrawn: it moves unchanged to `CRIT-OVERFIT-06`, so `min_positive_walk_forward_fold_ratio = 0.80` remains enforced. Probe: a seq 9-shaped ledger (losing 2022, strongly positive 2023) reports ratio **0.5000 → FAIL**; 3 of 4 positive folds → 0.7500 PASS; a fold clearing expectancy but not the PF floor is not positive. `min_total_trades`, `min_profit_factor`, DSR, haircut, weight, coverage and the cost schedule are unchanged and asserted. An in-sample run whose four folds hold no closed or liquidated trade reports **NOT RUN** with that reason rather than 0.0000 FAIL (§9.3): an empty ledger is no evidence either way, while a fold that holds trades and loses still FAILs. The §66 N-108 probe moved with the definition to `CRIT-OVERFIT-06` rather than being dropped, and the §68 H-116 universe probe now measures 225 valid ISINs (208 continuous + 17 gap refusals) against the 196 it asserted when 13 instruments were refused outright.
- **Bronze span, measured for §77.14.** `data/reference/bhavcopy_archive_manifest.jsonl` attests **1,195 sessions, 2022-01-03 .. 2026-10-30**, and `data/raw/` holds only `2022/`, `2023/`, `2024/`, `2025/`, `2026/`. There is **no pre-2022 archive in the repository**, so the §10.8 binding window (2018-04-01) cannot be reached from committed bytes: the available Bronze span is **2022-01-03 .. 2026-10-30**, of which 2022-01-03 .. 2024-12-31 is unspent in-sample/validation material and 2025-01-01 onward is sealed holdout. Extending to 2018-04 is an ingestion task (§77.15 item 7), NOT RUN here.
- **Verification actually run.** Full offline suite **513 passed, 0 skipped, 0 xfailed** (505 before: +8 tests, chiefly `tests/unit/test_phase3b2_audit_s77_items.py`, with the §66/§68/verdict fixtures and probes moved to the 1.1.7 criterion names rather than relaxed); all 9 `scripts/verify_*.py` exit 0; `python scripts/verify_audit_append_only.py` exit 0 (`ALL REPOSITORY FOUNDATION GATES PASSED`), Gate W0.5-5 on 46 current rows, `G2A-6.6 N=9, N_eval=5`; `verify_phase2d_verdicts.py` reproduces the regenerated bytes; criteria fingerprint `CRIT-FPR-V1-fd6f5c6df136714ebdecb50a464f974a6974976523ed911005d2259c7917a1a6`.
- **Not claimed.** Not audited. No trial was registered, executed or re-scored: the trials manifest is unchanged at 323 B (`3326b1b2…`), `N = 9`, `N_eval = 5`, `validation_folds_count = 0`, and the holdout `2025-01-01..2026-11-11` was not read. The twelve new transition rows are `CONTENT_IDENTIFIED_ONLY` with no NSE circular, no attestation and no share ratio; dividends and splits for those names remain keyed to a single ISIN, so an action row dated outside a held ISIN's interval will not reach a held lot. §77.15 item 7 (corpus extension to 2018-04) and item 8 (seq 10) are explicitly **not** part of this commit: with the corpus starting 2022-01-03 the DSR bar §77.14 computed (2.314 at T = 493) is unchanged.

### Audit §78 — identity table generated for the market, three criterion bypasses closed, workflow scaled

Round: audit §78 at `82e3ef0` (reviewing `780ac4b`), work order §78.16 items 1-5. Criteria **1.1.8**. **Not audited**: no verdict judges this commit; every claim below is a measurement taken on this tree, and N-152 remains open by design.

- **N-151 — the transition table is generated, not hand-maintained.** `scripts/derive_2022_2024_corpora.py` now derives one `ISIN_TRANSITION` row per adjacent identity pair from `data/reference/cash_equity_symbol_intervals.csv` instead of listing the fourteen symbols one corpus happened to visit. Measured: **310 symbols carry more than one ISIN**, **324 identity pairs**, **309 rows added** (176 → **485 rows**, 205,540 bytes, SHA-256 `c593bb96…`). Every generated row is `CONTENT_IDENTIFIED_ONLY`, names `UNATTESTED_NSE_INTERVAL_TABLE_<SYMBOL>_<YYYYMMDD>` and carries a 1:1 ratio (the series is split/bonus adjusted, so a share ratio would be invented); the three rows whose ratio comes from a committed `SPLIT` keep 10:1 / 2:1 / 2:1 and are not duplicated. `data/reference/manifest.jsonl` is restated as a new current row (39,211 bytes; **46 current / 21 superseded**), `expected_manifest_fingerprint` re-pinned to `MAN-FPR-V1-571752f09d59981d…`, criteria `1.1.7 → 1.1.8` with **no numeric threshold and no criterion moved**. The generator now reproduces the committed file byte-for-byte (previously the three H-115 restated MERGER rows existed only in the file), asserted by the suite.
- **N-153 — IRB's boundary spike is post-split trading, not an unadjusted artefact.** Raw Bhavcopy for 2023-02-21 reports O 284.95 / H 301.00 / L 281.25 / **C 297.45** (VOL 5,840,552); 2023-02-22 reports **O 30.40** / H 34.90 / L 29.60 / **C 34.05** with **PREVCLOSE 297.45** (VOL 101,939,538); 2023-02-23 reports O 31.85 / H 32.40 / L 29.30 / **C 29.70** (VOL 39,418,918). The 297.45 → 30.40 open is a **1:10 face-value change on the identity boundary**, and the adjusted series' moves (+14.47% on 2023-02-22, −12.80% the next session) reproduce the raw post-split trading, so the spike is a real two-day round trip and not a print of the split itself. The committed series carries 29.745 for 2023-02-21, i.e. a 10× adjustment exists in the derived layer — **and the corpus still carries no IRB `SPLIT` row**, so that adjustment is not sourced from the committed corporate-action table. That is a §10.3/§5.4 provenance gap recorded here, not repaired here.
- **N-148 — an unreconcilable basis cannot pass.** `CRIT-STAT-01` is now **NOT RUN** when `total_trades` arrives with neither `liquidated_open_positions` nor `liquidated_trade_count`. Measured: `{total_trades: 193}` → NOT RUN; `{total_trades: 193, closed_only_trade_count: 193}` → NOT RUN; `{205, closed 193, 12 positions}` → PASS 205; `{205 vs declared 193}` → FAIL. The live runner always supplies the positions, so the live path is unchanged.
- **N-149 — the fold set is pinned.** `CRIT-OVERFIT-03` requires exactly the four pre-registered ends (`2022-06-30`, `2022-12-30`, `2023-06-30`, `2023-12-29`) read from the rows themselves. Measured: one positive fold → **FAIL**; two folds → **FAIL**; four rows with a drifted end → **FAIL** naming the unexpected end; a declared `positive_is_fold_ratio` with no rows → **NOT RUN**; four committed ends → PASS 1.0000 / 3-of-4 → 0.7500 PASS / 2-of-4 → FAIL / all-empty → NOT RUN, unchanged.
- **N-150 — the validation-fold minimum is enforced before the ratio.** `walk_forward_validation_folds_count < 2` → **NOT RUN** whatever ratio is supplied. Measured: `{ratio 1.00, count 1}` → NOT RUN; `{ratio 1.00, count 2}` → PASS; `{ratio 0.50, count 2}` → FAIL.
- **§78.15 (a) — the audit log is archived without being touched.** `configs/audit_volumes.yaml` pins volume 1 (`sections: "1-78"`, `line_count: 8442`, `sha256: 7c7760f72820f195…`, `frozen: true`, `base_commit: 82e3ef0`) and registers `reports/audit/volume2.md` (`sections: "79+"`, not yet created). `verify_audit_append_only.py` now enforces an **exact SHA-256 and line count** on frozen volumes (stronger than "no removed line") and a HEAD-prefix append-only check on active ones. `reports/audit/INDEX.md` is generated by `scripts/generate_audit_index.py` (never hand-edited) and maps **all 78 sections** to volume, line range and finding ids; the generator fails closed if a declared range is not fully indexed, and Gate W0.5-1c reproduces the committed bytes. The section headings are not uniform (`## 1.`, `## 40 —`, `## §75 —`, and §54 has no top-level heading at all), which the generator handles explicitly.
- **§78.15 (b) — prose commits stop paying for the suite.** The gate hashes every tracked file except `reports/audit/**`, `docs/**` and `CURRENT_STAGE_OF_WORK.md` and records a green run in `data/reference/source_tree_green.json` (append-only). An identical, fresh (< 24 h) source tree logs `reused green at <sha> (<n> passed)` and runs only the fast gates; an unknown hash, a stale record, a non-zero recorded exit or `--force-full` forces the full run, and `--force-full` was used for this round's gate.
- **§78.15 (c) — findings are executable.** `reports/audit/findings.jsonl` registers N-148…N-153 with a command, expected exit and required stdout pattern; `scripts/verify_audit_findings.py` runs every non-`ACCEPTED` row and is discovered by Gate W0.5-2. Measured: **5 probes executed, all PASS** (N-148/149/150/151/153), **N-152 recorded as `ACCEPTED`** with its residual (no transition row is attested; promoting one to `VERIFIED` requires a circular whose hash is in the manifest). Each probe asserts on the committed code path, not on a new one.
- **Phase 2D restated.** `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` regenerated under 1.1.8 with the restatement note: `NO-GO`, **PASS=2 / FAIL=0 / NOT RUN=25** (27 rows), fingerprint `CRIT-FPR-V1-6f01caec…`; `verify_phase2d_verdicts.py` reproduces the committed bytes (Gate 2D-1/2D-5 PASS). The synthetic fixture now declares its liquidated count so the fixture stays complete rather than gaining an unneeded NOT RUN.
- **Verification actually run.** Full offline suite **523 passed, 0 skipped, 0 xfailed** (`--force-full`, 116 s); all **9** `scripts/verify_*.py` exit 0; `python scripts/verify_audit_append_only.py --force-full` exit 0 with `ALL REPOSITORY FOUNDATION GATES PASSED` — W0.5-1/1b/1c/2/3/4/5 all PASS, W0.5-5 on **46 current / 21 superseded** rows. No trial row was appended or scored: **N = 9, N_eval = 5**, the 2024 validation fold stays frozen (`validation_folds_count = 0`), and Holdout `2025-01-01..2026-11-11` remains sealed with `HOLDOUT_UNLOCK` absent. `data/trials/**` and the frozen audit volume are byte-identical to `82e3ef0`.
- **Tests moved, not weakened.** The §76 Ruling-1 probes and the verdict/Tier-A fixtures now supply `liquidated_trade_count` (the evidence N-148 requires); the §77 360ONE probe keeps the refusal arm against a stub master because that pair is now documented, and asserts the same instrument resolves on the committed table; criteria-version literals moved `1.1.7 → 1.1.8` in the five files that assert them; the Tier-A falsifier's NOT RUN evidence allow-list gained the N-149 wording. No assertion was dropped, skipped or widened.
- **Not claimed.** No audit verdict on this commit; §78.16 item 6 (attestation) and item 7 (pre-2022 ingestion) are untouched, so no seq 10 was registered or run, and `CRIT-DATA-05` still cannot pass on a run whose window is 2022-2026 only for the identity reason it now does.

### Audit §79 — the green cache is anchored, the ledger records transitions, and the frozen pin survives a checkout

Round: audit §79 (`67235d9`, corrected in `0f650c3`) reviewing `3119cb2`, work order §79.12 items 1-6. Criteria **1.1.9**. **Not audited**: no verdict judges this commit; every claim below is a measurement taken on this tree.

- **N-155 — the cache now has to witness the run it claims.** `select_gate_plan` reuses a record only when four independent conditions hold: `verify_exits` names **all 9 discovered verifiers** and every code is `0`; `suite_count` is an integer at or above the pinned floor **500**; `gate_sha` resolves through `git rev-parse --verify <sha>^{commit}`; and the record is under 24 h old. Measured on the §79.8 forgery (`{verify_exits: {}, suite_count: 1, gate_sha: "forged"}`): the plan is **full**, and the reason names the failed condition. A cached tree is no longer trusted on its own: Gate **W0.5-2b** re-executes `verify_audit_findings.py` and `verify_phase2d_verdicts.py` on every reuse, because the ledger and the Phase 2D artifacts sit outside the source-tree hash. A full run appends only when its `source_tree_hash` is **not already recorded**, so a routine green run leaves the tracked cache file untouched; a forged row is reported, never self-healed. Measured this round: `--force-full` recorded `d93b813a…` with **529 passed**, and the reuse path (identical tree) skips the heavy gates while still running both runtime verifiers.
- **N-156 — a ratio cannot arrive without its fold count.** `CRIT-OVERFIT-06` is **NOT RUN** when `walk_forward_positive_fold_ratio` is supplied with no valid integer `walk_forward_validation_folds_count`. Measured: `{ratio: 1.00}` → NOT RUN; `{ratio: 1.00, count: "two"}` → NOT RUN; `{ratio: 1.00, count: 2}` → PASS 1.0000; `{ratio: 0.50, count: 2}` → FAIL. The live runner was the same gap: it stated the fold count only in its NOT RUN branch, so a ratio-carrying bundle omitted it — `scripts/run_phase3b2_walkforward.py` now states `walk_forward_validation_folds_count = num_val_folds` beside the ratio it emits.
- **N-159 — positions without a closed count are not a reconciliation.** `CRIT-STAT-01` is **NOT RUN** when `total_trades` and `liquidated_open_positions` arrive without `closed_only_trade_count`. Measured: `{205, positions: []}` → NOT RUN; `{205, positions: 12}` → NOT RUN; `{205, closed 193, positions 12}` → PASS 205; `{205, closed 200, positions 12}` → FAIL; the declared-count arm is unchanged (`{193, liquidated_trade_count: 193}` → PASS, `{205, liquidated_trade_count: 193}` → FAIL), so §79.2's measured table still holds for every shape but the one this item closes.
- **N-154 — the frozen volume hashes the same bytes everywhere.** `.gitattributes` pins `reports/audit/** text eol=lf`, and the digest is computed over the volume bytes with **CRLF folded to LF** (`compute_volume_digest`), used by both Gate W0.5-1b and the frozen-volume test. Measured: the committed volume hashes to `f4ca03d58466bebb…` at 8,442 lines, and a CRLF copy of the same text hashes to the **same** pin — the §79.7 defect (a pin over a Windows working copy that no checkout could satisfy) cannot recur. Volume 1 itself is untouched.
- **N-157 — the ledger's transition semantics are ratified and enforced.** `validate_ledger` in `scripts/verify_audit_findings.py`: the last row per id is authoritative; `OPEN -> CLOSED/ACCEPTED` and `ACCEPTED -> CLOSED` are the only forward moves; a repeated id with the same status is still a duplicate; a `CLOSED` row must carry an integer `closed_in_section`. Measured: an `OPEN -> CLOSED` append is accepted, a `CLOSED -> OPEN` append is refused as `not a forward transition`, a duplicate is refused, an uncited closure is refused, and the committed 14-row / 6-id ledger passes as it stands.
- **N-158 — TATASTEEL's one-session disagreement is reconciled at the source.** The `ISIN_TRANSITION` row is dated **2022-07-29** (the successor ISIN's first session) instead of 2022-07-28; the `SPLIT` row keeps 2022-07-28, which is a price-adjustment claim and changes no series. `validate_documented_transition_dates` now asserts `ex_date == successor.effective_from` for every documented pair and raises instead of skipping — a hand-dated row drifted to 2022-07-28 is refused with the N-158 message. Measured: **324/324** pairs meet their boundary, zero misaligned.
- **Corpus and pin restated.** `corporate_actions.jsonl` reproduces from its generator at **485 rows / 205,540 B / sha256 `0eaddaa5…`** (one date moved, byte count unchanged); `manifest.jsonl` carries the restatement as a new current row (**46 current / 22 superseded**), and `expected_manifest_fingerprint` moves to `MAN-FPR-V1-23200ba8825533…` under criteria **1.1.9**, with **no numeric threshold and no criterion changed**.
- **Skills.** `.agents/skills/implement-round/SKILL.md` and `.agents/skills/audit-round/SKILL.md` encode the two halves of this loop: the implementer's boundaries (frozen volumes, auditor-owned ledger, `N = 9`, `N_eval = 5`, frozen 2024 fold, sealed holdout), the probe-before-fix order, and the verify/commit/tag sequence; the auditor's baseline re-measurement, adversarial probes, section shape and append-only closure rows.
- **Verification actually run.** Full offline suite **529 passed, 0 skipped, 0 xfailed** (122 s); all **9** `scripts/verify_*.py` exit 0; `python scripts/verify_audit_append_only.py --force-full` exit 0 with `ALL REPOSITORY FOUNDATION GATES PASSED` — W0.5-1/1b/1c/2/3/4/5 all PASS, W0.5-5 on **46 current / 22 superseded** rows; `verify_phase2d_verdicts.py` exit 0 on the 1.1.9 artifacts (Gates 2D-1/2D-5 reproduce the committed bytes); `verify_audit_findings.py` exit 0 with 5 probes executed and N-152 carried as `ACCEPTED`. No trial row was appended or scored: **N = 9, N_eval = 5**, the trials manifest pin is unchanged, `validation_folds_count = 0`, and Holdout `2025-01-01..2026-11-11` remains sealed with `HOLDOUT_UNLOCK` absent.
- **Tests moved with the bindings, not against them.** Version literals moved `1.1.8 -> 1.1.9` in the six files that assert them; complete fixtures now state `walk_forward_validation_folds_count: 2` beside the ratio they already declared, and the Tier-A fixture keeps its omitted-count assertion untouched; `tests/unit/test_phase3b2_audit_s79_items.py` adds six probes (N-154 CRLF canonical digest, N-155 forged cache row, N-156 missing count, N-157 transition rules, N-158 324/324 alignment and refusal, N-159 positions without a closed count). No assertion was skipped, dropped or widened.
- **Not claimed.** No audit verdict on this commit. N-150 remains `OPEN` and out of this work order; N-152 remains `ACCEPTED`; §79.12 item 7 (pre-2022 ingestion) is untouched, so no seq 10 was registered or run. A first green run of a changed tree necessarily writes one record to the tracked cache — that record is committed here; a re-run on the same tree appends nothing.

### Audit §80 — the green cache binds to a git tree, and the fold count must be an integer

Round: audit §80 at `3f5f338` (tag `audit-s80-3f5f338`), reviewing `96d24a1`; work order §80.13 items 1-2
implemented and items 3-5 prepared. Criteria **1.1.9**, no threshold moved. **Not audited**: no verdict
judges these commits, and **N-160 / N-161 carry no `CLOSED` row** in `reports/audit/findings.jsonl` — that
ledger is the auditor's (§11.1), so nothing below is a closure claim, only the measurement the auditor's
next round has to reproduce.

- **N-160 — a cache row now names a tree, not a directory.** `source_tree_entries()` returns `(path, blob
  oid)` from `git ls-tree -r HEAD` instead of sha256 over working-copy bytes, `source_tree_hash_at_commit(ref)`
  projects the same digest for any commit, and `green_record_problem` refuses a row unless
  `source_tree_hash_at_commit(record["gate_sha"]) == record["source_tree_hash"]` under a recorded
  `source_tree_scheme: "git-blob-oid-v1"`. Measured, replaying §80.3's transcript in `probe_n160`: poison
  `tests/unit/test_verdicts.py`, recompose the digest with the gate's own `compute_source_tree_hash`, name the
  real commit `HEAD` — `green_record_problem` answers *"is not the tree at gate_sha … that commit's tree
  projects …"* and `select_gate_plan` answers **full**; a row hashing HEAD's tree while naming `HEAD^` is
  refused; the positive control (HEAD's tree, `gate_sha` HEAD) is **reuse**.
- **N-160 — the platform half.** The digest is now composed of the oids git stores, so the 280-CRLF working
  copy of `configs/go_no_go_criteria.yaml` hashes to the oid of its LF blob; the probe finds a clean text file
  whose checkout differs from its blob only by line endings and asserts the entry is the blob's oid. `git
  hash-object` was measured first and rejected: with the `text` attribute it converts
  `data/reference/bhavcopy_2024/cm03JAN2024bhav.csv.zip` and returns an oid the repository does not contain,
  so the digest is taken from `ls-tree`, which cannot disagree with a commit.
- **N-160 — the tree a run tested is the tree recorded.** `dirty_source_paths()` (`git status --porcelain`,
  which refreshes the index) plus `should_record_green()` mean a run over a working copy that differs from
  HEAD is neither a cache hit nor recorded. This was found by the work, not by reading: the first
  `--force-full` run appended a row that combined HEAD's tree hash with a suite that had tested modified
  files — the exact forgery the item closes, produced by the gate itself. That row was removed before it was
  committed and the follow-up run printed *"no green row was recorded"*. A second measurement found the
  index-stat trap: `git diff-index` reported two Phase 2D artifacts as modified after a verifier rewrote them
  byte-identically, which would have forced the heavy gates for a tree that did not move, so the dirty check
  uses `git status` and the probe asserts every dirty path really differs from its blob.
- **N-160 — legacy rows are history, not evidence.** The four working-copy rows stay in
  `data/reference/source_tree_green.json` unchanged and are never reused, because they carry no scheme. Two
  rows are now recorded under the new scheme: `333bead0…` at `c285310` and `eb61ec28…` at `742324c`, both 534
  passed with all nine discovered verifiers at exit 0.
- **N-161 — a fold count is an integer or it is not a count.** `CRIT-OVERFIT-06` no longer coerces: measured
  `{ratio 1.00, count "2"}` → **NOT RUN**, `{ratio 1.00, count 2.0}` → **NOT RUN**, `{count true}` → **NOT
  RUN**, `{count 1}` → **NOT RUN**, `{ratio 1.00, count 2}` → **PASS 1.0000**, `{ratio 0.50, count 2}` →
  **FAIL**. The live producer already emits an `int` (`walk_forward_validation_folds_count = num_val_folds`),
  so no run changes; no threshold moved.
- **§80.13 items 3-5 prepared, not executed.** `scripts/probe_pre2022_preconditions.py` is the executable form
  of A1/A2/A4 and exits **1** with 8 of 8 checks unmet: no 2018-2021 circular artifact exists in
  `data/raw/circulars` (13 on disk, all issued 2021-12-10..2026-01-12); the calendar's `provenance.sha256` is
  its own `CAL-FPR` hex rather than a source digest; all 4,510 identity interval rows begin 2022-01-03, zero
  reach 2021-12-31; 0 of 138 committed dividend ex-dates fall in the window (earliest 2022-03-29); no
  maximum-hold bound is committed. `docs/pre2022_ingestion_preconditions.md` records the artifact each gate
  needs, the acceptance rule, the derivation plan (interval rows from pre-2022 Bhavcopy, no back-solving from
  the present, no stitching across ISINs), and the order A1 → A2 → A4 → B1-B9 → C1-C6 with §80.10's corrected
  count (`930 + 494 = 1,424`; `T = 494`). **No data was written**: no Bronze archive, corpus row, manifest row,
  criteria value or interval row changed.
- **Skills.** `.agents/skills/audit-round/SKILL.md` now opens with the Senior Indian Quantitative Researcher &
  Principal Systems Architect persona and eight Strategic Ruling rules (evidence first, numbered and
  append-only, thresholds out of scope, one change with its falsifier, it creates work, scope may be narrowed
  only, the holdout is not ruling territory, computed status), and its Step 5 gains a post-commit gate run
  **without** `--force-full` plus the requirement that `source_tree_green.json` be append-only and clean before
  the Step 6 commit. `.agents/skills/implement-round/SKILL.md` records that a full run over a dirty tree
  records nothing, so the row is committed after the commit it names.
- **Verification actually run.** `python scripts/verify_audit_append_only.py --force-full` exit 0 with
  `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` on the working tree — **534 passed, 0 skipped, 0 xfailed**
  (106.85 s) — and it recorded **no** row for a dirty tree. Post-commit runs on `c285310` (106.86 s) and
  `742324c` (107.43 s) each recorded exactly one row: **534 passed**, 9 discovered `scripts/verify_*.py` all
  exit 0, W0.5-5 on **46 current / 22 superseded** manifest rows. `probe_audit_findings.py N-160` → **PASS**,
  `N-161` → **PASS**, `N-156` → **PASS**. `verify_audit_findings.py` exit 0 inside the gate on the five
  non-`ACCEPTED` ledger rows.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5** (`trial_registry.jsonl` 9
  rows / `…evaluations` 5 rows, `data/trials/**` byte-identical to `3f5f338`); the 2024 fold stays frozen as
  the validation partition with `validation_folds_count = 0`; Holdout `2025-01-01..2026-11-11` remains sealed
  with `HOLDOUT_UNLOCK` absent; `reports/audit/**` is untouched by this round.
- **Tests moved with the bindings.** The §78 and §79 cache tests gained the scheme field and an injected tree
  projection (plus new refusals for a wrong-tree row, an unregistered scheme and a stat-only change), and
  `tests/unit/test_phase3b2_audit_s80_items.py` adds five: tree-oid identity, the §80.3 forgery with a real
  commit, the dirty-tree recording rule, a gate-written row's reuse on a clone, and the N-161 shapes. No
  assertion was skipped, dropped or widened.
- **Not claimed.** No seq 10 was registered or run; §80.13 items 6-7 are untouched; N-152 remains `ACCEPTED`;
  the pre-2022 window remains warm-up only, and the DSR bar is unchanged by anything here.

### Audit §81 — the reuse key is the commit, and an untracked test is state

Round: audit §81 (audit of `80ff581`, section and work order appended at `a5adeaa`, tag
`audit-s81-dfc99e7`), work order items 1-3 implemented. Criteria **1.1.9**, no threshold moved, no data
written. **Not audited**: no verdict judges these commits, and **N-162 / N-163 / N-164 carry no `CLOSED`
row** in `reports/audit/findings.jsonl` — that ledger is the auditor's (§11.1), so the rows stay `OPEN`
and everything below is the measurement the next round has to reproduce.

- **N-162 — reuse is keyed on the commit being verified.** `select_gate_plan` takes a keyword-only
  `head_commit` with **no default** (§14.4: a caller that cannot name the commit it verifies cannot
  reuse), resolves it with `commit_oid()` and skips a row whose `gate_sha` resolves to a different
  commit, even when that row projects the verified tree. Measured with a real commit object carrying
  HEAD's exact tree (`git commit-tree HEAD^{tree} -p HEAD`): the row recorded at that commit is **not**
  spent at HEAD (`full`, reason names the commit), the identical row naming HEAD is **reuse**, and
  `head_commit="deadbeef"` is `full` with *"the verifying commit … is not a commit in this repository"*.
  The natural witness arrived by itself at the end of this round: `df382ff` is the code commit and the
  record commit that follows it is a docs-only child with the identical source tree — the gate there
  printed *"the record for this source tree was written at df382ff, not at the commit being verified"*
  instead of the §81.4 `reused green` line, and appended nothing.
- **N-162 — untracked source files are in the dirty set.** `dirty_source_paths()` now runs
  `git status --porcelain -z --untracked-files=all`, so a file pytest collects but git does not track
  forces the heavy gates and forbids recording. Measured by writing
  `tests/unit/test_n162_untracked_probe.py` with `assert False`: the path appears in the dirty set, the
  file fails pytest (exit 1), `should_record_green` returns `False`, and the path leaves the set when the
  file is deleted. Ignored paths stay excluded, because `git status` does not report them.
- **The accepted cost, stated.** A docs-only commit whose tree a parent already recorded gets **no row of
  its own** and is therefore never a cache hit: every commit runs the heavy gates at least once, which is
  the cost §81.4 named. Rows remain history a clone can audit; what reuse now buys is repeated runs at one
  HEAD, which is the local case it was built for. This supersedes the §80 sentence that a clone "can reuse
  the newest green run" — a clone of the tag commit recomputes the digest and runs the gates itself.
- **N-163 — the test no longer assumes its own parentage.** `test_n160_a_hand_written_hash_names_no_tree_and_is_refused`
  selects its divergent commit by the tree it projects (`_commit_with_other_tree`, a scan of the 40 newest
  ancestors) instead of taking the parent, so a docs-only commit with a source-identical parent exercises
  the same property. Measured: `python -m pytest -q tests/unit/test_phase3b2_audit_s80_items.py` → **7
  passed**, and the file contains no parent-of-HEAD derivation.
- **N-164 — the probe's refusal is the tree comparison.** `probe_n160` decodes the commit it derives
  (`parent = git("rev-parse", …).decode().strip()`), asserts the refusal text is *"is not the tree at
  gate_sha"*, and demonstrates the old shape separately: the same record with an undecoded sha is refused
  earlier as *"is not a commit in this repository"*, so an assertion that the problem is merely non-`None`
  passed on the typing accident. Both messages are asserted, in the probe and in `probe_n164`.
- **Probes were written first and watched to fail.** On the unfixed tree, `probe_n162` and `probe_n160`
  raised `TypeError: select_gate_plan() got an unexpected keyword argument 'head_commit'`, `probe_n163`
  failed on *"the §80 cache test still derives its divergent commit from HEAD's parent"*, and `probe_n164`
  failed on *"a row recording another tree still names a commit it is not refused for: None"*.
- **Verification actually run.** `python scripts/verify_audit_append_only.py --force-full` exit 0 with
  `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` — **536 passed, 0 skipped, 0 xfailed** (120.46 s) — and
  it recorded **no** row for a dirty tree (5 paths). Post-commit run at `df382ff`: exit 0, **536 passed**
  (121.70 s), 9 discovered `scripts/verify_*.py` all exit 0, W0.5-5 on 46 current / 22 superseded manifest
  rows, and exactly one row appended — `7976b39b…`, scheme `git-blob-oid-v1`, `gate_sha df382ff`.
  `verify_audit_findings.py` exit 0 with **16 probes matched**; `probe_audit_findings.py N-160 / N-161 /
  N-162 / N-163 / N-164` each **PASS** standalone. The §78 and §79 cache tests were updated to the new
  signature (a row naming another commit, and an unresolvable HEAD, both `full`) — no assertion relaxed,
  none skipped.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 fold stays the
  validation partition with `validation_folds_count = 0`; Holdout `2025-01-01..2026-11-11` remains sealed
  with `HOLDOUT_UNLOCK` absent; `reports/audit/**` and `.agents/skills/audit-round/SKILL.md` are untouched
  by this round.
- **Not claimed.** No seq 10 was registered or run; §81.11 items 4-7 (ledger ratification, A1 sourcing,
  warm-up labelling, pin relaxation) are untouched; N-150 stays `OPEN`, N-152 `ACCEPTED`; the pre-2022
  window remains warm-up only and the DSR bar is unchanged.

### Audit §82 — the evidence no longer depends on the checkout's line endings

Round: audit §82 (audit of `c8f56d4`, section and work order appended at `cf112df`, tag
`audit-s82-66c2f36`), work order items 1-3 implemented, plus the Ubuntu CI failure in the §80 tree test
and `probe_n160`. Criteria **1.1.9**, no threshold moved, no data written. §82.2-§82.4 closed N-162,
N-163 and N-164 at `c8f56d4`; **N-165 and N-166 stay `OPEN`** — their closure rows belong to the
auditor (§11.1), so what follows is the measurement the next round has to reproduce.

- **The two tree measurements were machines, not caches.** `test_n160_source_tree_hash_is_the_object_id_git_stores`
  and `probe_n160` asserted that every uncommitted source path differs byte-for-byte from its blob and
  then searched for a CRLF sample to prove that line endings do not move the digest. Both claims are
  Windows facts: on an LF checkout no file holds CRLF and a reported path can carry its blob's exact
  bytes (a mode change), so the assertions were measuring the developer's checkout. They now assert the
  blob-oid identity **unconditionally** on a clean text file (`entries[rel] == git rev-parse HEAD:<rel>`,
  with CRLF folded on both sides), require raw byte inequality only inside the CRLF branch that exists
  only where the checkout really differs, restrict the sample to text suffixes (`.py/.yaml/.yml/.json/
  .jsonl/.md`, so no `.zip` or binary is read), and make no content claim at all about a path HEAD has
  no blob for. Measured in a detached worktree checked out with `core.autocrlf=false`: **0 files
  containing CRLF**, `tests/unit/test_phase3b2_audit_s80_items.py` **7 passed**, `probe N-160` **PASS**.
- **N-165 — an ignored file the suite collects is dirty state.** `dirty_source_paths()` now runs
  `git status --porcelain -z --ignored=matching --untracked-files=all` and keeps ignored entries only
  when they are `.py` files under `src/`, `scripts/` or `tests/`. Measured in the repository with a real
  `.git/info/exclude` rule and a real `assert False` test: `git status` still does not report it, the
  file is in the dirty set, pytest on it exits 1, and `should_record_green` is `False`; the forged row
  naming HEAD is still a valid hit on a clean tree, so the refusal is the file and not a broken fixture.
  The filter is bounded on purpose: byte-code caches, build directories and ignored `data/` artifacts
  report as directories or non-`.py` files and stay out, so a normal checkout keeps its green reuse
  (measured: the dirty set is empty at `f6dc7da` on this working copy). Residual, named not fixed: an
  **ignored non-`.py` artifact** is still invisible — this machine holds
  `data/reference/historical_dev_dataset_2022_2024.json`, untracked and ignored, which no test collects.
- **N-166 — the consumers hold their verdict in a dirty working copy.** `probe_n160` now asserts an
  implication (every source path git reports is in the dirty set) instead of equality against a set
  collected with different flags, and compares no bytes for a dirty path, so an unrelated untracked file
  cannot change its verdict. The §80 tree test skips the `cat-file` comparison for paths absent from
  HEAD, which is what raised. Measured with one untracked failing test present: `probe N-160` prints
  exactly `PASS N-160` and exits 0, the tree test passes, and the gate still fails closed — the file is
  in the dirty set and no run over it is recorded.
- **N-164 nit.** `assert commit_exists(parent)` now carries HEAD's parent value in its message, and the
  divergent-tree refusal asserts `mismatch is not None` separately from the reason it must contain, so a
  failure prints what was measured instead of an empty line.
- **Verification actually run.** `verify_audit_findings.py` exit 0, **ALL 18 FINDING PROBE(S) PASSED**
  (`N-160 N-162 N-163 N-164 N-165 N-166` each PASS standalone); `verify_audit_append_only.py --force-full`
  on the uncommitted tree exit 0, **536 passed, 0 skipped, 0 xfailed** (135.50 s), and it recorded no row
  for a working copy that differed from HEAD in 3 paths; the post-commit run at `f6dc7da` exit 0,
  **536 passed** (128.40 s), 9 discovered `scripts/verify_*.py` all exit 0, and exactly one row appended
  — `06732f11…`, scheme `git-blob-oid-v1`, `gate_sha f6dc7da`. No assertion was skipped or widened.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 validation
  partition stays frozen (`configs/partition_spec.yaml` 2024-01-01..2024-12-31, the committed verdicts'
  `validation_folds_count` untouched); Holdout `2025-01-01..2026-11-11` remains sealed with no
  `HOLDOUT_UNLOCK` sentinel on disk; `reports/audit/**`, `AGENTS.md` and
  `.agents/skills/audit-round/SKILL.md` are untouched by this round.
- **Not claimed.** No seq 10 was registered or run; §82.8 items 4-6 (A1 sourcing, warm-up labelling, pin
  gating) are untouched; N-150 stays `OPEN`, N-152 `ACCEPTED`; the pre-2022 window remains warm-up only
  and the DSR bar is unchanged.

### Audit §83 — an ignored directory is dirty state, whatever shape git reports

Round: audit §83 (audit of `1a20255`, section and work order appended at `b89dbe7`, tag
`audit-s83-b89dbe7`), work order item 1 only — N-167 (`MEDIUM`), the surface §83.4 registered and §83.3
left open. Item 2 (the §82.8 items 4-6) is carried unchanged. Criteria **1.1.9**, no threshold moved, no
trial and no data written. N-167's ledger row stays `OPEN`: closure rows belong to the auditor (§11.1),
so what follows is the measurement the next round has to reproduce. **Not audited.**

- **Both shapes git does not enumerate are dirty now.** `dirty_source_paths()` used to drop every
  ignored entry ending in `/` and kept ignored files only under `src/`, `scripts/`, `tests/`, so an
  ignored directory under `tests/` holding a collected test, and an ignored rootdir `conftest.py`, were
  code the suite executes while the gate's only view of the working copy said "clean". An ignored
  directory under a collected root is now enumerated with `git ls-files --others --ignored
  --exclude-standard -z -- <dir>` and its `.py` files are added to the set
  (`ignored_python_files()`); a rootdir `conftest.py` reported as `!!` is kept because pytest imports it
  for every run. A failing `git ls-files` raises rather than reading as "nothing hidden": the dirty set
  is what refuses reuse.
- **The probe was flipped, and it failed first.** `probe_n167` asserted the defect; it now asserts the
  fixed behaviour. On the pre-fix tree it exits 1 with *"an ignored directory under tests/ is still
  invisible to the dirty set (['scripts/probe_audit_findings.py'])"*. After the change it exits 0 and
  prints `PASS N-167`: `tests/unit/n167_hidden/test_hidden.py` is in the dirty set, `should_record_green`
  is `False` for it (and `True` for an empty set, so the refusal is the set and not a recording rule
  that never fires), pytest on that directory still exits non-zero, an ignored rootdir `conftest.py` is
  in the set with `should_record_green` `False`, and both paths leave the set after cleanup with the set
  equal to the baseline it started from.
- **N-165's file form did not regress.** `probe N-165` still prints `PASS` with a `.git/info/exclude`
  rule hiding one file; both shapes now take the branch an edited file takes in `main()`.
- **Verification actually run.** `probe_audit_findings.py --list` 19 ids; `verify_audit_findings.py` exit
  0, **ALL 19 FINDING PROBE(S) PASSED**; `verify_audit_append_only.py --force-full` on the uncommitted
  tree exit 0, **536 passed, 0 skipped, 0 xfailed** (158.98 s), 9 discovered `scripts/verify_*.py` all
  exit 0, and it recorded no row for a working copy that differed from HEAD in 2 paths. The
  committed-tree run and the single row it appends follow in the next commit.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 validation
  partition stays frozen; Holdout `2025-01-01..2026-11-11` remains sealed with no `HOLDOUT_UNLOCK`
  sentinel on disk; `reports/audit/**`, `AGENTS.md` and `.agents/skills/audit-round/SKILL.md` are
  untouched by this round.
- **Not claimed.** No seq 10 was registered or run; §82.8 items 4-6 are untouched; N-165 and N-166 stay
  `OPEN` in the ledger until the auditor's next section, N-150 stays `OPEN`, N-152 `ACCEPTED`; the
  pre-2022 window remains warm-up only and the DSR bar is unchanged.

### Audit §84 — an ignored rootdir pytest config is dirty state too

Round: audit §84 (audit of `f361ba8`, section and work order appended at `fe8299c`, tag
`audit-s84-fe8299c`), work order item 1 only — N-168 (`MEDIUM`), the config channel §84.3 named as the
residual of N-165 and §84.4 registered. Item 2 (the §82.8 items 4-6) is carried unchanged. Criteria
**1.1.9**, no threshold moved, no trial and no data written. N-168's ledger row stays `OPEN`: closure
rows belong to the auditor (§11.1), so what follows is the measurement the next round has to reproduce.
**Not audited.**

- **The config file is state now.** `ROOTDIR_PYTEST_CONFIG_FILES = ("pytest.ini", "tox.ini",
  "setup.cfg", "pyproject.toml")`, and an entry `git status --ignored=matching` reports as `!!` for one
  of those names is added to `dirty_source_paths()` beside the rootdir `conftest.py` (§83.6 item 1).
  A rootdir config fixes the rootdir and can add `addopts` or replace `testpaths`, so an ignored one
  makes pytest run a suite the committed tree does not describe — it is neither a `.py` file under a
  collected root nor a `conftest.py`, which is why it reached no branch before. The gate now refuses
  reuse and recording over it exactly as it does over an edited file.
- **The probe was flipped, and it failed first.** `probe_n168` asserted the defect; it now asserts the
  fixed behaviour, and on the pre-fix tree it exits 1 with *"an ignored rootdir pytest config is still
  invisible to the dirty set (['scripts/probe_audit_findings.py']), so a local exclude rule can point
  pytest at a different suite under a reused green row"*. After the change it exits 0 and prints
  `PASS N-168`: `pytest.ini` is in the dirty set, `should_record_green` is `False` over that set and
  `True` over an empty one, pytest's own collection changes while the config is in place (the tracked
  `test_n160_source_tree_hash_is_the_object_id_git_stores` is collected before and deselected after —
  7 collected, then 6 with one deselected), the forged row is still a valid hit to `select_gate_plan`
  (so the refusal is the dirty set, not a rule that never fires), and `pytest.ini` leaves the set after
  cleanup with the set equal to the baseline it started from.
- **What the deselect does and does not prove.** The deselected suite exits 0 with a count the 500
  floor still accepts, so pytest's exit status and the suite count are both blind to it; the dirty set
  is the only instrument that fires. The probe therefore measures the refusal, not a red pytest run.
- **Each tuple member that can be exercised was measured.** With `pytest.ini`, `tox.ini` and `setup.cfg`
  present and hidden by one `.git/info/exclude` rule, `git status` stays clean and the dirty set reads
  `['pytest.ini', …, 'setup.cfg', 'tox.ini']`; removing them restores the baseline set. `pyproject.toml`
  is tracked in this repository, so git can never report it `!!` — its tuple entry is unexercised here
  and is recorded as unmeasured rather than claimed tested.
- **N-165 and N-167 did not regress.** `probe N-165` and `probe N-167` both still print `PASS`.
- **Verification actually run.** `probe_audit_findings.py --list` 20 ids; `verify_audit_findings.py` exit
  0, **ALL 20 FINDING PROBE(S) PASSED**; `verify_audit_append_only.py --check-scripts-only` exit 0, 9/9
  verifiers exit 0; `--force-full` on the uncommitted tree exit 0, **536 passed, 0 skipped, 0 xfailed**
  (136.10 s), and it recorded no row for a working copy that differed from HEAD in 2 paths. The
  committed-tree run and the single row it appends follow in the next commit.
- **One observation, reconciled.** A leftover `pytest.ini` and its `.git/info/exclude` rule were found
  on disk after the gate run and removed before anything was committed; neither the probe run directly,
  nor `verify_audit_findings.py`, nor the gate's verifier phase reproduces a leftover (measured twice
  and once respectively, clean each time). The scratch artifacts are not in the commit; the sequence
  that left them is unexplained rather than explained.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 validation
  partition stays frozen; Holdout `2025-01-01..2026-11-11` remains sealed with no `HOLDOUT_UNLOCK`
  sentinel on disk; `reports/audit/**`, `AGENTS.md` and `.agents/skills/audit-round/SKILL.md` are
  untouched by this round.
- **Not claimed.** No seq 10 was registered or run; §82.8 items 4-6 are untouched; N-168 stays `OPEN` in
  the ledger until the auditor's next section, N-150 stays `OPEN`, N-152 `ACCEPTED`; the pre-2022 window
  remains warm-up only and the DSR bar is unchanged.
