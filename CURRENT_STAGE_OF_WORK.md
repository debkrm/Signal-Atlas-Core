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

### Audit §85 — the legacy ini name is state; A1 was measured, not ingested

Round: audit §85 (audit of `0b3c56d`, section and work order appended at `08a5fe5`, tag
`audit-s85-08a5fe5`). Item 1 — N-169 (`MEDIUM`) — is delivered. Item 2's A1 half (2018-2021 holiday
circulars plus per-year provenance) was **measured and is blocked**: two of the four years cannot be
reproduced from the exchange circulars while the committed calendar says what it says, and closing that
gap moves the calendar identity pin rather than a threshold. No artifact, manifest row, criteria value
or provenance field was written for A1. N-169's ledger row stays `OPEN`: closure rows are the auditor's
(§11.1). Criteria **1.1.9**, no threshold moved, no trial registered. **Not audited.**

- **The legacy ini name is in the tuple.** pytest 8.3.4 still reads `.pytest.ini`, and it reached no
  branch of `dirty_source_paths()` because §84.6 item 1 named only `pytest.ini`, `tox.ini`, `setup.cfg`
  and `pyproject.toml`. `ROOTDIR_PYTEST_CONFIG_FILES` now begins with `".pytest.ini"`, so an ignored
  rootdir `.pytest.ini` is dirty state exactly as its undotted sibling is.
- **The probe was flipped, and it failed first.** `probe_n169` asserted the defect; it now asserts the
  closure, and on the unfixed verifier (parent `a906738`, only the probe replaced) it exits 1 with
  *"an ignored legacy .pytest.ini is still invisible to the dirty set (['scripts/probe_audit_findings.py']),
  so a local exclude rule can point pytest at a different suite under a reused green row"*. After the
  change it prints `PASS N-169`: `.pytest.ini` is in the dirty set, `should_record_green` is `False` over
  that set and `True` over an empty one, pytest's own collection changes while the config is in place
  (7 collected, then 6 with the tracked `test_n160_source_tree_hash_is_the_object_id_git_stores`
  deselected), the forged row is still a valid `select_gate_plan` hit — so the refusal is the dirty set,
  not a rule that never fires — and the file leaves the set on cleanup with the set equal to baseline.
- **No neighbour regressed.** `probe N-169`, `N-168`, `N-167` and `N-165` each exit 0; `--list` reports
  **21** ids; `git status --ignored=matching` shows no `pytest.ini`/`.pytest.ini` after the runs.
- **A1, measured against the committed grid.** The exchange circulars were read as dated lists and
  compared with the calendar's implied holiday set (`weekdays(year) − sessions(year)` plus weekend
  sessions the calendar carries): `NSE/CMTR/36475` (2017-12-12) for 2018, `NSE/CMTR/39612` (2018-12-07)
  for 2019, `NSE/CMTR/42877` (2019-12-11) for 2020, `NSE/CMTR/46623` (2020-12-11) for 2021, with
  `NSE/CMTR/40536` (2019-04-29, Parliamentary Elections) and `NSE/MSD/42319` (2019-10-21, Maharashtra
  Assembly Elections) as the 2019 amendments.
  - **2018 reproduces exactly.** 16 declared weekday holidays (including 2018-11-07 Diwali-Laxmi Pujan,
    the muhurat session the calendar carries as a session) give `261 − 16 + 1 = 246`, the calendar's
    count, with zero date-level difference.
  - **2021 reproduces exactly.** 14 declared weekday holidays (including 2021-11-04 muhurat) give
    `261 − 14 + 1 = 248`, the calendar's count, with zero date-level difference.
  - **2019 cannot.** The annual circular declares 15 weekday holidays, the two amendments add 2019-04-29
    and 2019-10-21, and the Sunday muhurat is 2019-10-27: `261 − 17 + 1 = 245` sessions, but the calendar
    holds 244 and omits **2019-10-29**. That date is a Tuesday, no circular in this set declares it a
    holiday, and the equity market traded on it (Sensex closed 39,831.84, +582 points, on 2019-10-29).
    A1 2019 fails closed on exactly that one date: *"1 circular date(s) absent from the calendar"*.
  - **2020 cannot.** The annual circular's 12 weekday holidays match the calendar's 12 implied ones, but
    the calendar also carries **2020-02-01**, the Saturday Union Budget session, and no ingested circular
    declares that session. The 2020-02-01 live-session circular for the cash segment is not among the
    artifacts here and no download reference for it was located; the commodity-segment circular
    (`NSE/COM/43331`, 2020-01-24) is a different segment and is not admissible as its source.
- **Why nothing was ingested.** Adding artifacts and a per-year provenance table would have to re-pin
  `expected_manifest_fingerprint` (a criteria-version commit) and replace the calendar's self-referential
  `provenance.sha256` — which `load_nse_trading_calendar()` currently compares against the recomputed
  `CAL-FPR` content digest (H-26) — while the probe would still print `NO` for 2019 and 2020. Freezing
  per-year provenance around a grid that omits a real 2019 session, or declaring 2019-10-29 a holiday no
  circular declares, would be fabrication (§6.3, §6.5). Correcting the grid instead adds one session,
  moves `CAL-FPR-V1-af8e309a…`, `expected_total_calendar_sessions` 2935 → 2936, the 2019 count 244 → 245
  and the binding-window 930 → 931, and re-points the phase 2D / 3B2 verdicts' cited calendar
  fingerprint; that is a decision this work order does not authorise, so it is reported, not taken.
- **Not claimed.** A1, A2 and A4 remain unmet and `probe_pre2022_preconditions.py` still exits 1; the
  pre-2022 window is warm-up only and every pre-2022 verdict stays `NOT RUN`. No §82.8 item is touched.
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 validation
  partition stays frozen; Holdout `2025-01-01..2026-11-11` remains sealed with no `HOLDOUT_UNLOCK`
  sentinel; `reports/audit/**`, `AGENTS.md` and `.agents/skills/audit-round/SKILL.md` are untouched.

### Audit §86 — the attributes, the restored 2019 session, and A1 at PASS

Round: audit §86 (audit of `cd36177`, tag `audit-s86-cd36177`). Items 1-3 of §86.8 are delivered in
`3fb8f64`; item 4 (parallel pytest) is **not run** because `pytest-xdist` is not installed, so the
suite ran serially. Criteria **1.1.10**, no numeric threshold moved, no trial registered. N-170's
ledger row stays `OPEN`: closure rows are the auditor's (§11.1). **Not audited** — every number
below is a measurement from this round, and none of it carries an auditor verdict (§11.3).

- **N-170, measured on a fresh clone.** `.gitattributes` now marks `*.csv.zip` and `*.json.gz`
  (and their bare `*.zip` / `*.gz` forms) `-text`, and `probe N-170` reads the attribute back as
  `unset` for all **1,221** tracked archives, matches each worktree file's `git hash-object` against
  its index oid (**0** mismatches), and finds **0** archives in the dirty set. A fresh
  `git clone --no-hardlinks` of `3fb8f64` reports `git status --porcelain` **empty (0 paths)**: the
  24 rewritten paths the audit measured are gone, and the repair is an attribute decision rather
  than a byte rewrite, so no blob changed.
- **2019-10-29 is restored from the circulars, not from arithmetic.** `NSE/CMTR/39612` (2018-12-07,
  Ref 115/2018) declares 15 weekday holidays and **no** holiday on 2019-10-29; `NSE/CMTR/40536`
  (2019-03-26, Ref 30/2019) adds 2019-04-29 for the Parliamentary Elections and `NSE/MSD/42319`
  (2019-10-07, Ref 53/2019) adds 2019-10-21 for the Maharashtra Assembly Elections, with the Sunday
  muhurat on 2019-10-27: `261 − 17 + 1 = 245` sessions. The calendar now holds 2019 = **245**,
  **2936** sessions in total and **931** in `2018-04-01..2021-12-31`; `CAL-FPR-V1-6acb5f45…`
  replaces `af8e309a…`, and `load_anchored_nse_trading_calendar()` accepts the file at 2936.
- **A1 prints PASS for all four years.** `python scripts/probe_pre2022_preconditions.py` reports
  `[PASS] A1 2018: 246 session(s) reproduced by 1 sourced circular artifact(s), 18 declared
  holiday(s)`, `[PASS] A1 2019: 245 … 3 … 21`, `[PASS] A1 2020: 252 … 2 … 19`, `[PASS] A1 2021: 248
  … 1 … 18` and `[PASS] A1 provenance: the calendar names a source digest 7622fbf4…`. A2 and A4
  still print `NO`, the probe still exits 1, and the pre-2022 window stays warm-up only (§10.8).
- **The provenance field stopped naming itself (§86.6 item 7).** `provenance.sha256` is now the
  digest of `data/reference/calendar_provenance_bundle.json` (3,483 B, `7622fbf4…`), which names
  each year's circular artifacts by `sha256` and `byte_count` with the session count that year
  reconciles to; `source_bundle` says which file it is. `load_nse_trading_calendar()` seals on the
  declared `fingerprint` instead, refuses a provenance digest equal to the content digest, and
  fails closed if the bundle is missing or its bytes do not hash to the declared digest. The
  manifest attests the calendar row as a restatement (585,546 → 586,148 B, previous row superseded)
  and the bundle as a new artifact: 47,639 B, `MAN-FPR-V1-d05b87e1…`, **54** current and **23**
  superseded rows.
- **Re-pins, all computed.** Criteria `1.1.10` moves only the calendar identity anchor, the total
  session pin 2935 → 2936, the manifest pin and the warm-up note 930 → 931; `criteria.py`'s default
  total, `verify_phase2b5_storage.py` (2936 plus a bundle-digest check), the two calendar-count unit
  tests and `test_storage.py` follow. Untouched as ordered: `expected_sourced_window_calendar_
  fingerprint` `2d5ac7ac…`, `expected_baseline_calendar_sessions` 1201, `expected_authoritative_
  calendar_sessions` 1196 and window start `2022-01-03`.
- **The Phase 2D verdict did not move.** Regenerated under 1.1.10 and every criterion row
  (`criterion_id`, verdict, measured value) is identical to the pre-change artifact — only the
  criteria version, the pins and the restatement note differ. `verify_phase2d_verdicts.py` exits 0
  with Gate 2D-6 matching all 54 current rows; `verify_phase2b5_storage.py` exits 0 at 2936 sessions.
- **The suite is green serially.** **536 passed, 0 skipped, 0 xfailed** (142 s), and all **10**
  `scripts/verify_*.py` exit 0. Nothing was skipped, deselected or relaxed to reach it (§12.4).
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024
  validation partition stays frozen; Holdout `2025-01-01..2026-11-11` remains sealed with no
  `HOLDOUT_UNLOCK` sentinel; `reports/audit/**`, `AGENTS.md` and
  `.agents/skills/audit-round/SKILL.md` are untouched.

### Audit §87 — the 931 warm-up sessions are captured, and gating them is still refused

Round: audit §87 (audit of `20ba5ee`, tag `audit-s87-20ba5ee`). Items 1-2 of §87.7 are delivered in
`e35d8b1`, with `6cb7a81` following it because the first gate run on `e35d8b1` exited 1 on five stale
`criteria_version` literals; the tree `6cb7a81` names is the one the gate recorded. Item 3 (A2) and
item 4 (A4) are untouched, `probe_pre2022_preconditions.py` still exits 1, and no pre-2022 session is
`PASS`/`FAIL`-eligible. Criteria **1.1.11**, zero numeric changes, no trial registered. **Not
audited** — every number below is a measurement from this round (§9.3), and none of it carries an
auditor verdict (§11.3).

- **931 archives captured, zero failures.** `2018-04-01..2021-12-31` from the committed calendar:
  2018 **186**, 2019 **245**, 2020 **252**, 2021 **248**; **926 FULL**, **4 MUHURAT**, **1 SPECIAL**.
  Each archive is promoted atomically (temporary sibling, fsync, `os.replace`) only after it opens,
  holds exactly one CSV, parses through `parse_bhavcopy_archive` and reports the scheduled session
  date, so a refused session leaves neither file nor row. One archive per session was re-used rather
  than re-fetched on resume; `CAPTURED: 369 new archive(s); REUSED: 562 attested archive(s); FAILED: 0`.
- **The capture surfaced an ingest defect, and fixed it rather than storing around it.** Part of
  2020-2021 prints the legacy TIMESTAMP with a two-digit year (`13-Jul-20`, e.g. the 2020-07-13
  archive), which `parse_bhavcopy_date` refused; it now accepts `%d-%b-%y` as well as `%d-%b-%Y`. The
  first capture run stopped at that archive with no partial file promoted; the rerun completed.
- **931 current manifest rows, 931 added and 0 removed** (`git diff --numstat`), each carrying
  `source_url`, `retrieved_at`, `byte_count`, `sha256`, `session_date`, `session_type` and
  `gating_mode: WARMUP_NOT_GATABLE`. Gate W0.5-5/2D-6 now verify **985** current artifacts (54 prior +
  931) and skip **23** superseded rows as history.
- **Ruling probe 1.** `scripts/probe_pre2022_bronze_coverage.py` exits 0 printing
  `931/931 session(s) attested by one current manifest row each, bytes matching byte_count and sha256,
  WARMUP_NOT_GATABLE on every row`, after failing closed at `0/931, 931 problem(s)` before the capture.
  Three attacks, each restored afterwards: deleting `cm27OCT2019bhav.csv.zip` →
  `attested archive ... is absent from disk` (exit 1); appending one byte to
  `cm01FEB2020bhav.csv.zip` → `is 67477 bytes on disk but the row attests 67476` (exit 1); relabelling
  the 2020-11-14 muhurat row `session_type FULL` / `gating_mode GATABLE` → both the
  `session_type ... instead of the calendar's 'MUHURAT'` and the `gating_mode 'GATABLE'` refusals
  (exit 1). Each restored tree returns `OVERALL: COVERED` exit 0.
- **Ruling probe 2.** `scripts/probe_pre2022_preconditions.py` gained A5: it resolves every committed
  verdict artifact in `reports/verdicts/` against the calendar and refuses when an evaluated session
  precedes the criteria' `min_binding_evaluation_start_date`. It prints `[PASS] A5 gating mode: 8
  verdict artifact(s) evaluated, 0 of 4,903 evaluated session(s) precede the binding start 2022-01-03`,
  and a deliberately mis-scoped 2019 window is refused by name in
  `tests/unit/test_pre2022_gating_mode.py`. The same `assert_no_warmup_sessions_in_evaluation` guard is
  called by `build_historical_dataset_from_raw_bhavcopy`, so adding a pre-2022 directory to an
  evaluation corpus raises `WarmupSessionGatingViolation` rather than building a dataset.
- **A1 is unchanged at 5/5 PASS** with `CAL-FPR-V1-6acb5f45…` and provenance `7622fbf4…` untouched —
  capture adds archives, it does not re-date the grid. A2 (`4,510` interval rows begin `2022-01-03`,
  `0` reach `2021-12-31`) and A4 (`0` of `138` ex-dates in the window; no maximum-hold bound) still
  print `NO`, so the probe exits 1 at **3 of 9** checks.
- **Criteria 1.1.11 reseals one pin.** `expected_manifest_fingerprint` moves to
  `MAN-FPR-V1-7131c213…` (714,265 B). A walk of every numeric value in both revisions finds **zero**
  changes; `min_binding_evaluation_start_date` stays `2022-01-03`, `expected_calendar_fingerprint`,
  `expected_sourced_window_calendar_fingerprint`, `1201`, `1196`, `2936` and
  `expected_trial_registry_manifest_sha256` are byte-identical. The Phase 2D artifacts were
  regenerated: 3 changed lines each, being the version, the criteria fingerprint and the restatement
  note — no criterion row moved, and `verify_phase2d_verdicts.py` exits 0 byte-for-byte.
- **The coverage gate was scoped, not weakened.** `verify_cash_universe_coverage.py` had been
  asserting "every archive under `data/raw/<year>/` is in the binding-window archive manifest", which
  the capture makes false by construction. It now sweeps the years its own manifest names and prints
  that the **931** new archives are warm-up Bronze verified per-artifact by Gate W0.5-5/2D-6 and by the
  coverage probe: `Gate COV-2 ... (2,390,165 / 2,390,165 across 1,195 sessions, 100.0000%)`, unchanged.
- **The gate is green on the committed tree.** `verify_audit_append_only.py --force-full` at `6cb7a81`:
  **543 passed, 0 skipped, 0 xfailed** (149.78 s), **9/9** verifiers exit 0, **91** commit-bearing tags
  discovered and verified (87 general plus the 4 derived wave sign-off tags), audit index reproduces
  at **87** section rows, green row 18 recorded against tree
  `8ed078a9…`. The first run at `e35d8b1` had exited 1 on the five version literals; `6cb7a81` moves
  them, with no assertion relaxed and no threshold touched (§12.4).
- **Invariants held.** No trial row was appended or scored: **N = 9, N_eval = 5**; the 2024 validation
  partition stays frozen; Holdout `2025-01-01..2026-11-11` remains sealed with no `HOLDOUT_UNLOCK`
  sentinel; `reports/audit/**`, `AGENTS.md`, `.agents/skills/audit-round/SKILL.md` and
  `configs/trading_calendar_nse.json` (`CAL-FPR-V1-6acb5f45…`) are untouched.

### Audit §88 — the certificate reads the archive, the parser refuses the century, and the gate runs the suite in parallel

Round: audit §88 (audit of `df97173`, tag `audit-s88-ec32ed9`). Items 1-2 of §88.8 are delivered in
`eb05053`, together with the §12.3 gate work the round was asked for. Items 3 (A2), 4 (A4) and 5 (the
A5 residual ruling) are untouched: `probe_pre2022_preconditions.py` still prints `[NO]` on both A2 and
both A4 lines and exits 1, and no criteria value moved (still **1.1.11**, `MAN-FPR-V1-7131c213…`,
`CAL-FPR-V1-6acb5f45…`, `min_binding_evaluation_start_date` **2022-01-03**). **Not audited** — the
numbers below are measurements of this round (§9.3), and the ledger rows for N-171 and N-172 are still
`OPEN`, because closing them is the auditor's append (§11.1).

- **N-171 — the certificate now reads what the exchange wrote.** `probe_pre2022_bronze_coverage.py`
  opens every attested archive and parses its own `TIMESTAMP` (or `TRADEDATE`) column, requiring the
  distinct embedded dates to equal the `session_date` on the row. Measured before and after on the same
  transposition (row dates for `2018-04-02` and `2018-04-03` swapped over the committed corpus, bytes
  and digests untouched): at the parent implementation the probe module has no archive reader and
  `main()` returns **0** — `COVERED — 931/931`; at `eb05053` it returns **1** with `session 2018-04-02
  (FULL): data/raw/2018/cm03APR2018bhav.csv.zip carries its own session date(s) 2018-04-03, so the
  row's session_date is not on these bytes`, and the untouched corpus still prints `COVERED — 931/931`.
  Reading all 931 archives costs **5.3 s** for the whole probe. `probe_n171` is flipped to assert the
  closure (refusal on the tampered manifest naming both dates, coverage on the committed one) and the
  H-24 containment line is retained. `PASS N-171`.
- **N-172 — the two-digit branch is bounded.** `parse_bhavcopy_date` refuses a `%d-%b-%y` value whose
  parsed year falls outside **1990-2030**, naming the string, the date it guessed and the range:
  `13-Jul-68` → `Implausible two-digit year in Bhavcopy: '13-Jul-68' parses to 2068-07-13, outside the
  plausible 1990-2030 range`; `13-Jul-89` (1989) and `01-Jan-31` (2031) likewise. In range and
  unchanged: `13-Jul-20` and `13-JUL-2020` → 2020-07-13, `13-Jul-99` → 1999-07-13, `31-Dec-30` →
  2030-12-31, and `cm13JUL2020bhav.csv.zip` parses to **1,392 EQ** records (**1,774** across all
  series) under `trade_date=2020-07-13`. H-24 still refuses the archive under a 2068 partition date, so
  the corpus binding and the parser bound are both measured. `PASS N-172`.
- **The gate was lying about its own failures on this console.** `check_test_suite_zero_skip_xfail`
  decoded pytest's stdout as strict UTF-8 while a Windows console hands the child cp1252: a `§` in a
  failing test's message raised `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa7 in position
  727` inside the reader thread and the traceback was replaced by `[FAIL] pytest exited with code 1`.
  The reader now decodes with `errors="replace"` and the gate reconfigures its own stdout to UTF-8,
  because printing the replacement character to cp1252 raised `UnicodeEncodeError` in turn — the second
  half was found by running the first fix against a genuinely failing test. Measured with a failing
  test whose message contains `§`: the gate log now carries the assertion text and the replacement
  character and no decode error; before, the byte was undecodable and the text was lost.
- **The suite runs in parallel, with the same assertions.** `pytest_command()` uses `pytest -n auto
  --dist loadfile -q` when `pytest-xdist` is importable and `pytest -q` otherwise; the gate prints
  which it used. Measured: **543 passed** sequential in **149.78 s** (`6cb7a81`), **172.25 s**,
  **180.27 s** (audited at `df97173`); **543 passed** under `-n auto --dist loadfile` in **41.83 s**,
  **43.88 s**, **47.59 s** (clean) and **47.55 s / 48.84 s / 50.89 s** through the gate itself. No
  assertion was relaxed; the suite count the green row records is **543** in both modes.
- **The parallel run exposed a wall-clock benchmark, and the fix is the instrument, not the threshold.**
  One of eight parallel runs failed while its log was unreadable (previous bullet). Reproduced
  deliberately: with 24 CPU-bound processes competing, `test_n1_replay_guard_o1_lookup_and_bounded_memory`
  measured **357.6 µs/fill wall clock against a 250 µs ceiling** on unchanged code, and passed under the
  same load at **78-148 µs/fill** once the same two loops are timed with `time.process_time()`. The
  ceilings (250 µs, ratio < 2.5) are untouched; the property they assert is per-fill overhead, which a
  wall clock on a shared machine does not measure. After the change: 3 clean parallel runs and 2 runs
  under heavy orphan-process load (209.66 s, 192.47 s), all `543 passed`.
- **The 24 probes now run once per gate pass.** `verify_audit_findings.py` (W0.5-2) executes every
  ledger probe; `test_findings_ledger_rows_carry_executable_probes` executed all of them a second time
  inside the suite. It now asserts that every non-`ACCEPTED` ledger row is reported by
  `probe_audit_findings.py --list`, keeping the mapping check and dropping the duplicate execution:
  that test file went from **39.04 s** to **2.82 s**, measured at the parent and at `eb05053`.
- **The gate is green on the committed tree.** `verify_audit_append_only.py` at `eb05053`: ALL
  REPOSITORY FOUNDATION GATES PASSED, **543 passed / 0 skipped / 0 xfailed** in 47.55 s, **9/9**
  verifiers exit 0, W0.5-5 at **985** current artifacts, green row **20** recorded against tree
  `b5d9cb02…`.
- **Invariants held.** No trial appended or scored: **N = 9, N_eval = 5**; the 2024 validation fold is
  untouched; Holdout `2025-01-01..2026-11-11` stays sealed with no `HOLDOUT_UNLOCK`; criteria and
  `configs/trading_calendar_nse.json` are byte-identical; `reports/audit/**`, `AGENTS.md` and
  `.agents/skills/audit-round/SKILL.md` are untouched; no `data/raw` archive changed.
- **One environment note.** `pytest-xdist 3.8.0` was installed into this machine's interpreter to
  measure the parallel path; it is **not** added to `pyproject.toml`, so a fresh environment falls
  back to the sequential run with the same assertions. Adding `pytest-xdist` to the `dev` extra is a
  maintainer decision, not this round's.

### Audit §89 — N-173 delivered; A2, A4 and the criteria re-pin are **not** (round stopped with evidence)

Round: audit §89 (audit of `2e7f51b`, tag `audit-s89-75f5fb5`). One of the five ordered items is delivered,
in `6e11d91`. The other four were started, measured, and are reported here as **not delivered**, with the
measurement that stopped each. Nothing below is audited; the ledger row for N-173 stays `OPEN` for the
auditor to close (§11.1).

**Item 1 — N-173, delivered.** `test_n1_replay_guard_o1_lookup_and_bounded_memory` no longer times a
single pass per size. Each measurement accumulates whole passes, on a fresh portfolio each, until the
pooled CPU time exceeds `MIN_MEASURABLE_CPU_S` (0.25 s) or `MAX_PASSES` (20) is reached, and divides by
the work actually timed; the pass count is read from the clock after each pass, because a count
extrapolated from a cold first pass undershot the budget and failed intermittently (measured: one
failure in nine runs before the loop was changed, at the pooled-budget assertion). Both ceilings —
250 µs per fill and the 2.5 ratio — are byte-identical. `probe_n173` is flipped: it fails at the parent
instrument by name (`the benchmark no longer sizes its measurement`), and now asserts the closure
arithmetically at three clock resolutions — the host's own step, 15.625 ms, and 1 µs — requiring a
5 µs/fill implementation to read near 1.0 under the pooled instrument at every resolution while the
single-pass instrument still shows the ≥ 2.5 artifact on a coarse clock (host tick measured at
15,625 µs; the artifact computes to 3.91 there). Benchmark: 6/6 runs pass at ~1.46 s (was 1.85-1.94 s).
`verify_audit_findings.py`: 25/25 probes pass.

**Item 2 — A2, not delivered.** The identity table was rebuilt from all 2,126 committed archives and it
does what the item asks: 15,824 rows, earliest `effective_from` **2018-04-02** (the first session of the
binding window; `2018-04-01` is a Sunday and is not a session in `CAL-FPR-V1-6acb5f45…`, and the
derivation refuses a non-session effective date by construction), every one of the 931 warm-up sessions
covered by a row, and `A2` printing `PASS`. Measured against the archives' own rows, the rebuilt table
disagrees with **0 of 1,646,985** post-2022 `(symbol → isin, series)` observations; the committed table
disagrees with **186,996** of them, because its `EQ`-wins-for-the-whole-pair rule let a warm-up `EQ`
observation rewrite the series of every later `BE` row. Fixing that required the interval key to become
`(isin, symbol, series)`, which changes the number of adjacent identity pairs from **324** to **426** —
and `probe_n158` (CLOSED, MEDIUM) asserts `len(pairs) == 324` exactly. Regenerating
`corporate_actions.jsonl` from the new table restores N-151 (it passes) but not N-158. The rebuilt table,
the regenerated corpus and the criteria edit were therefore **reverted**, not committed: resolving this
means either an auditor ruling that the constant in N-158 is a measurement of the old lossy shape rather
than an invariant, or a definition of "adjacent identity pair" that is series-aware. The A2 acceptance as
written also cannot hold literally — "a first row at or before 2018-04-01" asks for a row on a date the
calendar does not schedule — so the probe line was restated as coverage of all 931 window sessions, which
is strictly stronger; that restatement is part of the same reverted change and should be ruled on
together.

**Item 3a — A4 dividends, blocked.** `scripts/ingest_pre2022_dividends.py` was written to capture
`2018-04-01..2021-12-31` from `https://www.nseindia.com/api/corporates-corporateActions` per quarter with
byte-exact Bronze payloads and one manifest attestation per payload. Every capture attempt ended in
`HTTP Error 403: Forbidden` after four retries with a fresh cookie jar, the landing-page seed request and
browser-shaped headers — while an interactive `curl` against the same URL and headers returned `200`, so
the endpoint is refusing this client rather than the window. No payload was retrieved, so **no dividend
row was written and nothing was fabricated**; the script and its empty Bronze directory were removed
rather than committed as dead code.

**Items 3b, 4, 5 — not started.** The maximum-hold bound has no enforcement point yet: `Position` carries
no entry date, so a bound read from criteria would be a threshold with nothing behind it — the probe
`A4 max hold` would pass while the exposure it bounds stayed in place, which §9.1 and §10.8 both forbid.
The criteria re-pin is unnecessary while the manifest is unchanged: no artifact was added, so `1.1.11`,
`MAN-FPR-V1-7131c213…` and `A5`'s `PASS` stand exactly as audited, and `min_binding_evaluation_start_date`
remains **2022-01-03**, N = 9, N_eval = 5, the 2024 fold frozen and the holdout `2025-01-01..2026-11-11`
sealed. `probe_pre2022_preconditions.py` still exits 1 with `A1` 5/5 `PASS`, `A5` `PASS`, and `A2`, both
`A4` lines `NO`.

**Gate.** `verify_audit_append_only.py` at `6e11d91`: ALL REPOSITORY FOUNDATION GATES PASSED, **543
passed / 0 skipped / 0 xfailed** in 46.82 s, 9/9 verifiers exit 0, green row recorded against tree
`b90a9393…`. `reports/audit/**`, `AGENTS.md`, `.agents/skills/audit-round/SKILL.md` and
`configs/trading_calendar_nse.json` are untouched, as are `data/trials/` and `data/raw/`.

### Audit §90 work order (feat-s91): one generator, an O(n) interval resolver, the 17 red tests, and the 1.1.12 artifacts (implemented; gates measured; not audited)

Round: the five items of the §90 work order, implemented over the working tree based on `e0ef0d7` (tag
`audit-s90-2c0631e`). Nothing below is audited; the wording states what was measured and what was not
(§11.3). No test was skipped or xfailed, no assertion tolerance was widened, and no threshold in
`configs/go_no_go_criteria.yaml` moved (§12.4). The binding
window stays **2022-01-03**, N = 9, N_eval = 5, the 2024 fold frozen and the holdout
`2025-01-01..2026-11-11` sealed; `reports/audit/**`, `AGENTS.md`, `.agents/skills/audit-round/SKILL.md`
and `configs/trading_calendar_nse.json` are untouched, and no `data/raw` payload was re-fetched.

**Baseline re-measured.** `pytest -n auto --dist loadfile -q` on the untouched tree: **17 failed, 527
passed in 442.12 s**. After the round: **544 passed, 0 failed, 0 skipped, 0 xfailed in 60.78 s** — same
command, same 16 workers.

**Item 1 — a direct call reproduces the whole corpus.** `generate_corporate_actions_corpus()` now ends by
merging its own output through `merge_pre2022_corporate_actions(...)`, and `main()` calls the generator
instead of re-merging it. A direct call emits **5,016 rows**, `sha256 6ff7d3ed…`, byte-identical to the
committed `data/reference/corporate_actions.jsonl` and to the manifest's current row (1,955,499 bytes);
the merge prints `15 payload(s), 4440 derived row(s), 4429 merged`. The module is imported both as
`scripts.derive_2022_2024_corpora` and run as a script, so `scripts/` now joins `sys.path` beside the
existing `src/` guard — the sibling `ingest_pre2022_corporate_actions` import resolved only in the second
shape before.

**The requested digest pin was measured, not moved.** The order asked for the corporate-action pin to move
from `6ff7d3ed…` to `856d8e2d…`. `856d8e2d…` is the digest of the **587-row pre-merge** output;
`6ff7d3ed…` is the 5,016-row committed corpus. `test_n151_generator_reproduces_the_committed_corpus`
carries no literal digest — it compares generator output against the committed file — so no pin was
edited here, and item 1 is what turns it green. Pinning `856d8e2d…` would assert that the corpus does not
reproduce.

**Item 2 — resolution is indexed, and the log is resolved in one pass.** `apply_interval_restatements`
was O(ISINs × rows): a genexpr rescanned every active row once per ISIN (4.483 s of a 4.777 s
`SecurityMaster.__init__` profile). It now groups the log once, keeps a live list per ISIN, and fails
closed on a non-contained overlap exactly as before; `resolve_symbol` reads a newest-first list, and
`resolve_isin_by_symbol` bisects an aligned `effective_from` index instead of scanning. Measured on the
committed 19,283-row log (17,864 active rows): interval load **4.34 s → 0.17 s**,
`build_production_security_master()` **> 4.8 s → 0.54 s**, and 931 warm-up sessions of
`get_point_in_time_active_equities` **3.2 s → 0.40 s** (the per-series start index is built once per
interval sequence and reused). The suite followed: 442.12 s → 60.78 s.

**A partly-restated row keeps its uncovered remainder.** Supersession used to delete the earlier row
whole. The production master seeds an open-ended core `EQ` row per name, and an appended `BE`
restatement covering only part of it therefore erased the part it did *not* cover: `INE704P01025`
(COCHINSHIP) resolved to nothing at 2024-01-15, which is what failed `test_storage` G2b5-3,
`test_price_bands_h30` (`2 == 3`) and `test_phase3b2_audit_s68_items` (`224 == 225`). The resolver now
clips: the covered slice is superseded and the remainders stay in force, so `INE704P01025` reads
`EQ 2024-01-10..2024-09-25`, `BE 2024-09-25..2024-12-30`, `EQ 2024-12-30..` — the same shape the raw
interval table states. All three tests pass **without a literal change**; no fixture count was edited.
The same defect left `INE144J01027` with an open-ended row overlapping a closed one, which made
`verify_cash_universe_coverage.py` abort at Gate COV-1 on the committed code; it now runs to COV-4.

**Item 3 — the remaining red tests.** Eleven `criteria_version`/`version` literals moved `1.1.11` →
`1.1.12` across `test_criteria`, `test_phase3b2_audit_s76_items` (×2), `test_phase3b2_audit_s77_items`
(×2), `test_phase3b2_audit_s78_items`, `test_significance` and `test_walkforward` (×4). N-158's `324`
became `426` under §90.7 Ruling 1, and the test now also asserts the **324** post-2022 tuples survive, so
the old measurement is pinned inside the new one rather than dropped.

**Item 4 — the 1.1.12 artifacts.** `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` were
regenerated by `scripts/generate_phase2d_tier_a_report.py`. The whole diff is two lines per artifact:
`criteria_version 1.1.11 → 1.1.12` and `criteria_fingerprint CRIT-FPR-V1-1c0131d6… → 50784f1a…`. All 27
criterion rows keep their verdicts and measured values, `PASS=2 / FAIL=0 / NOT RUN=25` is unchanged, the
calendar pin `CAL-FPR-V1-6acb5f45…` is unchanged, and `data/trials/` is untouched, so the eight post-2022
trial outcomes are byte-identical. `verify_phase2d_verdicts.py`: ALL PHASE 2D VERDICT ENGINE GATES
PASSED.

**One verifier expectation had to follow the data, and it got stricter rather than looser.** Gate COV-3
pinned `unresolved_isin_count == 924` from the pre-§90.9 interval table, whose post-2022 rows were
open-ended `EQ` and therefore resolved 250 names that were in trade-to-trade on 2024-01-16. With the
sourced series rows the honest count is **1,174**, attributed against the authoritative Bhavcopy of the
same session: **930** scrips have no row at all (identity begins at first trade, §40.5), **220** traded in
`BE`, **24** in another non-`EQ` series, and **zero** scrips the Bhavcopy reports as `EQ` fail to resolve.
The exact-equality assertion is kept (no tolerance added) and `max_unresolved_threshold` is the same
1,174, so the ingest guard and the gate agree on one measured number instead of the guard being 174 rows
slacker than the assertion. `verify_cash_universe_coverage.py` exits 0 with COV-1..COV-4 PASS, COV-4's
fold reaching VERIFIED.

**Gate.** `verify_audit_append_only.py --force-full`: **ALL REPOSITORY FOUNDATION GATES PASSED** —
W0.5-1 append-only, W0.5-1b volumes, W0.5-1c index, W0.5-2 **9/9 verifiers exit 0**, W0.5-3 **544 passed
/ 0 skipped / 0 xfailed**, W0.5-4 tags, W0.5-5 **1000 current artifacts** matched. `verify_audit_findings.py`
27/27 probes. Not audited: no §91 verdict exists yet, so nothing here is signed off, and the round's
green row and tag are recorded after this commit, not by it.

### Audit §91 work order (feat-s92): the hold bound gets a consumer, Gate COV-3 computes its attribution, the replay counter sees iteration, and the binding start moves to 2018-04-01 (implemented; gates measured; not audited)

Round: audit §91 at `9c79fdb` (tag `audit-s91-6068cf5`, reviewing `35e2050`), work order §91.9 items 1-4
and §91.8 Ruling 1. Criteria **1.1.13**. **Not audited** — no verdict judges this commit; every number
below is a measurement taken on this tree, and no ledger row was appended (the findings ledger is the
auditor's, §11.1).

**The three probes were flipped first, and measured failing at the parent.** At `9c79fdb`:
`probe_n174` exit 1 (`the replay-guard counter does not instrument __iter__`), `probe_n176` exit 1
(`Gate COV-3 still prints typed attribution literals ('930 untraded')`), `probe_n177` exit 1 (`the hold
bound still has no production consumer outside position.py`). Each is now `PASS` on this tree.

**Item 1 — N-177, the bound has a consumer.** `Portfolio.require_hold_bounds(as_of, bound, calendar)`
calls `Position.require_within_hold_bound` for every open position and returns each refused ISIN with its
refusal; `execute_swing_strategy_session` accepts `forced_exit_isins`, drops any strategy SELL for that
name, and emits one `MAX_HOLD_BOUND_EXIT` SELL at `next_session` through the same runner; the session loop
calls the consumer with `criteria.max_hold_trading_sessions` (21) and the authoritative calendar, and
counts a forced fill or a refusal (a locked bid or a missing bar leaves the position open and it is
refused again next session, never extended — §5.3). The result carries `hold_bound_forced_exits` and
`hold_bound_refusals`, and the A4 line now prints
`max_hold_trading_sessions=21 is committed and enforced at 1 production call site(s); refusals=1 for one
synthetic hold 21 sessions after entry`. **NOT RUN: the eight post-2022 trial outcomes were not re-run.**
The committed trial artifacts persist verdict metrics, digests and evaluation hashes, not per-trade
entry/exit dates, so no hold length can be read from them and outcome invariance is not measured here.
The enforcement emits nothing unless a hold reaches 21 authoritative sessions, but that is an argument,
not a measurement.

**Item 2 — N-176, the attribution is computed.** `scripts/verify_cash_universe_coverage.py` derives the
split from `sec_list_20240116.csv` and the same session's `cm16JAN2024bhav.csv.zip`
(`attribute_unresolved_eq_scrips`): **1,174** unresolved, **933** untraded, **224** trading in `BE`/`BZ`,
**17** in another non-`EQ` series, and **0** the Bhavcopy reports as `EQ` and unresolved. The three typed
literals are gone, the zero-`EQ` invariant is a hard `return False`, and `probe_n176` runs the gate
function, parses the printed split and asserts it equals its own recomputation.

**Item 3 — N-174, every access is counted.** `CountingReplayGuard` now counts `__contains__`, `__iter__`,
`keys`, `values`, `items`, `__getitem__` and `__len__`; the test asserts iteration-shaped accesses are
**0** and `__contains__` is exactly one per fill. §90.3's scan installed over 1,000 fills was detected
**5 of 5** runs (`iteration_accesses=1000`, `contains=1000` each), against 1 of 5 for the timing guard.
The 250 µs ceilings and the 2.5 ratio are unchanged.

**Item 4 / Ruling 1 — the binding start moves, and the sourced window does not.** Criteria **1.1.13**
sets `min_binding_evaluation_start_date: 2018-04-01`; `storage/gating.py`, `storage/calendar.py` and the
`criteria.py` defaults move with it. Three places had used the binding start as a stand-in for the
Bhavcopy source coverage start and now read the new `SOURCED_WINDOW_START_DATE = 2022-01-03`: the
calendar loader's 1,196-session and sourced-fingerprint anchors, reporting's `CRIT-DATA-06`, and the
Phase 2D generator's window. Unchanged by measurement: `MAN-FPR-V1-e95ddf90…`, sourced-window
`CAL-FPR-V1-2d5ac7ac…`, `1201` / `1196`, `CAL-FPR-V1-6acb5f45…`, **2,936** total sessions, every fold,
trial count, cost parameter and threshold. `probe_pre2022_preconditions.py`: **READY, 9/9** — A1 5/5,
A2 17,864 active of 19,283 earliest 2018-04-02 over 931 sessions, A4 4,357 ex-dates, A4 max hold
enforced with 1 refusal, A5 **0 of 4,903** evaluated sessions before 2018-04-01.

**What the promotion did NOT do.** The **931** manifest rows still read `WARMUP_NOT_GATABLE`, and
`probe_pre2022_bronze_coverage.py` still requires that label, so §91.9 item 4's acceptance — a tree whose
criteria move while its archive labels stay must fail the coverage certificate — is **not met**. The
relabel-by-append and `MAN-FPR` re-pin it implies were outside the ordered scope. Work-order items 5
(seq 10 registration) and 6 (N-150) were not ordered and were not done: **N = 9**, `N_eval = 5`, the
registry pin `3326b1b2…` unchanged, the 2024 fold frozen, holdout `2025-01-01..2026-11-11` sealed and
unread.

**Gate.** `verify_audit_append_only.py --force-full`: **ALL REPOSITORY FOUNDATION GATES PASSED** —
suite **544 passed, 0 skipped, 0 xfailed**; **9/9 verifiers exit 0**; W0.5-5 **1,000 current artifacts**
matched; the working copy differed from HEAD in 27 source paths, so no green row was recorded by that
run. `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` were regenerated: **9 lines** changed
(version, fingerprint, the 1.1.13 restatement), window still `2022-01-03..2026-10-30`,
`PASS=2 / FAIL=0 / NOT RUN=25`, overall **NO-GO**. Protected paths untouched: `reports/audit/**`,
`AGENTS.md`, `.agents/`, `configs/trading_calendar_nse.json`, `data/trials/`, `reports/verdicts/trial_00*`.

### Audit §93 work order (feat-s93): the 931 labels move to 1.1.14, the hold-bound invariance run measures a binding bound, and the swing seam gets its test (implemented; gates measured; not audited)

Implements items 1, 2 and 4 of the `reports/audit/volume2.md` §92 work order (`df8cac3`, tag
`audit-s92-df8cac3`) at the tree this section is committed in. **Not audited** — no verdict judges
this commit; every number below is measured here and nothing is claimed as closed, verified or signed
off. Items 3 (seq 10), 5 (N-150) and 6 (the replay counter's `get`/`popitem`) were not in the request
and were not done: **N = 9**, `N_eval = 5`.

**Item 1 / §92.7 Ruling 1 — the labels, the certificate and the pin move together.** The certificate's
label rule was re-expressed **first** and measured red on the parent tree: at criteria 1.1.13 with the
rows as captured, `probe_pre2022_bronze_coverage.py` exits **1** with **931** problems, each reading
`carries gating_mode 'WARMUP_NOT_GATABLE', expected 'BINDING_EVALUATION' for a session on/after the
binding start 2018-04-01 (criteria 1.1.13)`. The rule now reads
`load_go_no_go_criteria().min_binding_evaluation_start_date` through
`expected_gating_mode(session_date, binding_start)`, so both halves of §92.6's contradiction are
fail-closed: a tree whose criteria move and whose labels stay cannot pass, and the aligned tree does.

The manifest moved by append-only supersession, measured against `git show HEAD:` rather than read:
**1,026 → 1,957** rows; **931** prior rows flip `is_current: true → false` and `status: active →
superseded` with every other byte identical (**0** deletions that are anything but that flip); **931**
rows appended `is_current: true` / `status: active` with `gating_mode: BINDING_EVALUATION` and a
`retrieval_reference` naming §92.7 Ruling 1 and criteria 1.1.14; **0** appended rows whose
`byte_count`, `sha256`, `source_url`, `retrieved_at`, `session_date`, `session_type`, `description`,
`provenance_status`, `source_coverage` or `timestamp_utc` differs from the row it supersedes; **931**
distinct sessions `2018-04-02..2021-12-31`. No archive was re-read, re-hashed or re-fetched.
`expected_manifest_fingerprint` is re-pinned **by measurement** to `MAN-FPR-V1-a421d3d2de37ada0…` over
**1,865,503** bytes; Gate W0.5-5 attests **1,000 current / 957 superseded** rows, and
`probe_pre2022_bronze_coverage.py` exits **0** printing
`931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE`.

Criteria **1.1.14** changes no numeric threshold and no criterion: the pin is the only value, and
`min_binding_evaluation_start_date` stays **2018-04-01**, `expected_calendar_fingerprint`
`CAL-FPR-V1-6acb5f45…`, the sourced-window pin `CAL-FPR-V1-2d5ac7ac…` over **1,196** sessions with
**1,201** baseline and **2,936** total, `max_hold_trading_sessions` **21**, the 2024 fold and the
holdout `2025-01-01..2026-11-11`. The `pre_binding_calendar_provenance_note`'s "warm-up only / NOT
RUN" clause is corrected because it now contradicts the criteria that carry it; N-52's substance — no
per-session circular — is unchanged. Eleven live-version literals moved to `1.1.14` in six test files.
The Phase 2D artifacts were regenerated: **3/3** lines per file (version, fingerprint, the 1.1.14
restatement), window `2022-01-03..2026-10-30`, **PASS=2 / FAIL=0 / NOT RUN=25 / NO-GO**.
`probe_pre2022_preconditions.py` is **READY, 9/9** (A1 5/5, A2 17,864 of 19,283 over 931 sessions,
A4 4,357 ex-dates, A4 max hold `enforced at 1 production call site(s); refusals=1`, A5 0 of 4,903).
One committed test pins the rule's other half:
`test_bronze_coverage_probe_refuses_labels_that_disagree_with_the_criteria` exits **1** on
`931 problem(s)` when the loaded pin is pushed forward to 2022-01-03.

**Item 2 / §92.8 Ruling 2 — the invariance run measures a bound that binds, and a drift the bound does
not explain.** `scripts/probe_hold_bound_invariance.py` re-runs seq 9's committed configuration
(`TRIAL-PHASE3B2-RANKED-009`: sma_20/sma_50, k = 2.0, allocation 0.0800, trim None,
`LOCKED_BAR_REFUSAL_ONLY`, `mom_63`, notionals 25000/5000) over `2022-01-03..2023-12-29` through the
single engine, writing only into `TemporaryDirectory()`; the committed `data/trials/` registry and its
three sidecars are hashed before and after and are byte-identical, so the registry of record is
**N = 9 / N_eval = 5**. Two runs were needed because the counters alone cannot attribute drift:

| Run | Session(s) | `hold_bound_forced_exits` | `hold_bound_refusals` | Records reproduced |
|---|---|---|---|---|
| **A** — committed criteria, bound 21 | 494, `2022-01-03..2023-12-29` | **175** | **203** | **0 of 5** |
| **B** — same engine, bound raised out of reach (counterfactual, not a verdict) | 494, same window | 0 | 0 | **0 of 5** |

Run A against the committed artifact: `closed_trades` **382** vs **193**, `end_equity`
**1086020.54** vs **1283327.73**, `profit_factor` **1.106963** vs **0.991963**, `win_rate`
**0.408377** vs **0.253886**, `max_drawdown` **0.326415** vs **0.207335**. Run B against the same
artifact: **194** trades, **1164053.76**, **0.841456**, **0.262887**, **0.284222** — still not the
committed five. So the bound is **not** inert on this window (the §92.8 expectation that it would be
is contradicted), and a second, larger cause exists: the engine that produced seq 9's artifact no
longer reproduces it even with the consumer disabled. The A-vs-B difference is the bound's own
effect, and it is large: 194 → 382 closed trades, `end_equity` −₹78,033.22, `max_drawdown`
0.2842 → 0.3264.

**This is a negative result and is reported as one (§92.8: "a non-zero forced exit is a finding about
comparability… never smoothed").** §92.8's condition is **not met**, and a seq-10 result is not
comparable with the eight recorded trials until both causes are settled. The probe exits **1** while
that is true; it is a `probe_*` instrument and is not in `VERIFICATION_SCRIPTS`, so the gate neither
runs it nor is coloured by it. Not measured here: which engine change between criteria 1.1.5 and
1.1.14 accounts for run B's drift. The interval-table restatement (§91.2) is the obvious candidate and
is named as a hypothesis, not a finding.

**Item 4 / §92.10 item 4 — the seam has a committed test.** `tests/unit/test_phase3b2_audit_s93_items.py`
drives `Portfolio.require_hold_bounds` and `execute_swing_strategy_session(forced_exit_isins=…)`
together, as the session loop does, at the bound and one session inside it: at the bound on a normal
bar, **one** `FILLED` ticket with `exit_reason=MAX_HOLD_BOUND_EXIT` and the position closed; at the
bound with the bar locked at the lower circuit, **one** `REJECTED_LOWER_CIRCUIT` ticket, the position
still open at full quantity, and the engine's own accounting `len(forced − filled)` = **1**; one
session inside the bound, **no** refusal and **no** ticket. The counters are derived, not typed.
`probe_n177` now requires the file, requires it to name `forced_exit_isins=`, `MAX_HOLD_BOUND_EXIT`,
`REJECTED_LOWER_CIRCUIT` and `require_hold_bounds(`, and **executes** it; renaming the file away makes
probe N-177 exit 1 with `the swing seam has no committed test`. The three tests pass in 0.92 s.

**Gate and scope.** `verify_audit_append_only.py --force-full`: **ALL REPOSITORY FOUNDATION GATES
PASSED**, suite **548 passed, 0 skipped, 0 xfailed** (544 at §92 + 4), **9/9 verifiers exit 0**,
W0.5-5 **1,000 current artifacts**. `verify_audit_findings.py`: **29/29 finding probes**. One earlier
full run at this same tree printed `OVERALL VERDICT: ONE OR MORE GATES FAILED`; its gate section was
not captured, and **three subsequent full runs (two gates and the suite alone under `-n auto`) were
green at 548 passed**, so the failure is reported as unreproduced rather than explained — a flaky
timing-sensitive check is a hypothesis, not a measurement. Protected paths untouched: `reports/audit/**`,
`AGENTS.md`, `.agents/skills/audit-round/SKILL.md`, `configs/trading_calendar_nse.json`, `data/trials/`,
`reports/verdicts/trial_00*`. Docs corrected where they now contradicted the artifact:
`docs/bronze_storage_policy.md` and the `docs/pre2022_ingestion_preconditions.md` §87 capture record.

**§94 — round log for `feat-s94`, acting on the §93.7 work order at `e5e9217` (tag `feat-s93-e5e9217`).
NOT AUDITED: every statement below is the implementer's own measurement, and no status word here is
granted by a verdict.**

**§93.7 item 2 — the engine-loop passthrough is now asserted, and cut it fails.** `probe_n177` no longer
matches a substring: `_session_loop_passthrough_problem` parses `scripts/run_phase3b2_walkforward.py`
with `ast` and requires the call to `execute_swing_strategy_session` inside the session loop to pass a
keyword `forced_exit_isins` whose expression is exactly `tuple(sorted(forced_exits))`. Measured:
committed tree **PASS N-177, exit 0**; with that one line deleted, **exit 1** —
`the walk-forward session loop does not hand the hold bound's exits to the harness (line 1258: no
forced_exit_isins keyword), so a refused hold is never routed through the single execution path`;
restored, **exit 0**. The probe also refuses its own check against that mutation, so a check that cannot
fail is itself a failure (§14.4). Committed test:
`tests/unit/test_phase3b2_audit_s94_items.py::test_session_loop_hands_the_hold_bound_exits_to_the_harness`
asserts both directions.

**§93.7 item 3 — a superseded manifest row survives its own flip, at certificate time.**
`scripts/probe_pre2022_bronze_coverage.py` now reads every manifest row and, for each artifact that
carries a `session_date`, requires exactly one current row and compares the superseded rows' `sha256`,
`byte_count`, `source_url`, `retrieved_at`, `session_date` and `session_type` to it. Measured:
**931 superseded session rows checked, 0 problems**, certificate **COVERED — 931/931, exit 0**; editing
one superseded row's `sha256` makes it **exit 1** with
`archive data/raw/2018/cm02APR2018bhav.csv.zip: superseded row disagrees with the current row on sha256
(superseded '0000…', current '0ce5fd92…') — a supersession may move is_current/status and the label,
never the archive's digest or provenance (§10.1, Audit §93.7 item 3)`; restored, **exit 0**. The check is
deliberately scoped to session-dated rows: 23 superseded rows on derived artifacts
(`cash_equity_symbol_intervals.csv`, `corporate_actions.jsonl`) differ in digest **because their content
moved**, which is history, not a relabel; the three `circulars/NSE_CMTR_*_HOLIDAYS.json` artifacts carry
no current row and no session, so this certificate asserts nothing about them. Two committed tests
(`test_committed_superseded_session_rows_keep_their_archive_fields`,
`test_edited_superseded_sha256_is_refused`) assert the invariant and the refusal.

**§93.7 item 1 — candidate seq 10 is NOT RUN; the block is measured, not asserted.** No trial row,
evaluation row, verdict artifact or criteria re-pin was written: `data/trials/` is **N = 9 / N_eval = 5**
with manifest `3326b1b2…` equal to the criteria pin, and the criteria remain **1.1.14**. Two blockers,
both computed by `scripts/run_seq10_candidate.py` and reported by `scripts/probe_seq10_candidate.py`
(exit 1, `NOT CERTIFIED`):

1. **No committed corpus covers `2018-04-01..2023-12-29` with split/bonus-adjusted prices.** The
   candidates it inspects are `historical_dev_dataset_2022_2024.json` and `.json.gz`, both
   `2022-01-03..2024-12-31`, `adjustment_version=v1.4`, `CA-FPR-6d7aae6d8…`. `data/silver/bhavcopy`
   holds **0** partitions, so `GoldEngine` — whose `SPLIT_BONUS_ADJUSTED` branch back-adjusts by
   cumulative ratios before each ex-date — has no input. The remaining builder,
   `build_historical_dataset_from_raw_bhavcopy`, labels its series `UNADJUSTED_RAW` and is dead code
   with two latent defects measured here: `compute_legacy_dataset_content_fingerprint()` has no
   `symbols_by_instrument` parameter (TypeError), and `PriceConvention.UNADJUSTED_CLOSE` no longer exists
   (AttributeError; `UNADJUSTED_RAW` does). All 1,421 `data/raw/2018..2023` archives parse clean
   (**0 failures**); the 121 refused archives are all 2024 UDiFF files, outside the window.
2. **An unadjusted series is not a legal input for this window.** Of 5,016 committed corporate actions,
   **85 are SPLIT/BONUS/CONSOLIDATION with ratios and 74 take effect before 2022-01-03**, so a raw
   2018-2023 series carries each one as a price jump that SMA/ATR read as a move (§5.4, §10.3). Running
   either would publish a result the criteria's adjustment rule forbids, so the driver refuses before it
   registers anything and the probe reports the state as `NOT CERTIFIED` rather than passing on an
   absent run.

A third prerequisite was measured and **left unimplemented on purpose**: the engine's in-sample fold is
fixed at train `2022-01-03..2022-12-30`, test `2023-01-02..2023-12-29`, so a 2018-start run would state
`in_sample_metrics['window'] = 2022-01-03 .. 2023-12-29` while traversing `2018-04-01..2023-12-31`. A
first attempt at that plumbing was withdrawn after a two-session smoke run on the committed dev snapshot
raised `PartitionSpecValidationError: test_start (2023-01-02) exceeds test_end (2022-02-10)` — the fold
is not a window description that generalises, and shipping it ahead of the run would have been the
additive path §14.4 warns about. The driver now asserts its baseline artifact's declared window equals
the requested one **before** any registration.

**Gate and scope.** `verify_audit_append_only.py --force-full`: **ALL REPOSITORY FOUNDATION GATES
PASSED (100%)**, suite **552 passed in 56.53 s, 0 skipped, 0 xfailed** (548 at §93 plus the four new
tests), **9/9 verifiers exit 0**, Gate W0.5-5 **1,000 current / 957 superseded** rows,
`verify_audit_findings.py` **29/29**. Criteria 1.1.14 unchanged, every numeric threshold unchanged, the
2024 validation fold frozen, holdout `2025-01-01..2026-11-11` sealed, and no path under
`reports/audit/`, `AGENTS.md`, `.agents/skills/audit-round/SKILL.md`,
`configs/trading_calendar_nse.json`, `data/trials/` or `reports/verdicts/trial_00*` was written.

### Audit §94 work order (feat-s95): the 2018–2023 corpus, the derived fold, the three probes and the repaired fallback (implemented; gates measured on the committed tree; not audited)

This section implements **§94.6 items 1–6** at parent `43ab44c` (tag `audit-s94-ab4a6a8`). It is written
by the implementing agent and **is not audited**: no row here is a verdict, and the status words
`closed`, `verified` and `signed off` do not appear for any item. N-178, N-179 and N-180 stay `OPEN`
in `reports/audit/findings.jsonl` — the ledger is the auditor's, so these rows state what the probes now
assert and leave the closure to the next audit round (§11.1, §11.3).

**§94.6 item 1 — the derived `SPLIT_BONUS_ADJUSTED` 2018–2023 corpus is built (Route B).**
`scripts/derive_2018_2023_corpus.py` reads one Bronze archive per calendar session
`2018-04-01..2023-12-31` (**1,425** sessions; every session attested, no surplus archive, off-calendar
date count **0**), applies each `SPLIT` / `BONUS` / `CONSOLIDATION` row of the committed
`corporate_actions.jsonl` as an exact ratio strictly before its ex-date, and writes
`data/reference/historical_dataset_2018_2023.json.gz`: **1,082** ISINs, **1,541,850** bars, declared
`start_date 2018-04-01` (first session `2018-04-02`, a Sunday start), `end_date 2023-12-29`,
`adjustment_version v1.0-split-bonus-backadjust-2018-2023`, `corporate_actions_fingerprint
6ff7d3edb577a64d…` equal to the sha256 of the committed table, content fingerprint
`DATA-CTNT-V2-1862c1f2…`, **45,565,892** bytes, sha256 `5926e1c2…`. **8** price-side actions across **7**
instruments were applied; `DIVIDEND` rows are untouched (cash inflows, never price changes) and no
series is stitched across an `ISIN_TRANSITION` — the corpus is keyed by ISIN, so each identity keeps its
own sequence. The snapshot is registered as one current `data/reference/manifest.jsonl` row (1,959 rows
= **1,001 current** + 958 superseded; the first build's row was superseded by its restated rebuild,
never edited) and `expected_manifest_fingerprint` is re-pinned by measurement to
**`MAN-FPR-V1-4b813090…`** (1,867,504 bytes).

Two limits are named rather than hidden. Universe size: the panel is the **1,082** ISINs whose own bar
sequence covers every session from the window's first to its last (2,735 observed; 1,463 excluded for a
short span, 190 for an internal gap), which is the only shape the engine's continuity invariant can
evaluate without fabricating a session (§6.3). Of the 1,463, the names whose observations **stop** before
2023-12-29 have no verified delisting evidence in the corpus, so they are excluded rather than carried
with an unverified trailing gap — an observability limit, stated in the snapshot's
`universe_selection`, that the next round may attack. Adjustment: the committed table's 74 pre-2022
`SPLIT`/`BONUS` rows are price adjustments, and the two in-window `CONSOLIDATION` rows are applied for
the same reason (a reverse split is a share-ratio price event); `RIGHT`/`MERGER`/`DELISTING` rows are
not price adjustments and are left to the engine's position accounting.

**§94.6 item 2 — the in-sample fold is derived from the requested window.** `derive_in_sample_fold`
(`scripts/run_phase3b2_walkforward.py`) replaces the hardcoded 2022–2023 fold on the in-sample path and
the printed literal at the banner: train is the window's first session to the last session before the
evaluation year, test is the evaluation year to the requested end, embargo 0, `IN_SAMPLE`. Measured:
`2018-04-01..2023-12-31` ⇒ `FOLD-SPEC-V1-36a39987…` (the value §94.4 computed), and the committed
`2022-01-03..2023-12-29` window still reproduces **`FOLD-SPEC-V1-4b44a1f2…`**, the fold seq 1–9 were
registered under, so no existing fold moved. The 2024 validation fold is unedited and is never derived
from a request. `run_seq10_candidate._register` now writes the derived fingerprint (and the run's own
dataset fingerprint) instead of copying seq 9's, and `probe_seq10_candidate._expected_fold_fingerprint`
delegates to the same function, so the two derivations cannot disagree. `probe_n180` is flipped and
asserts that agreement; a committed test asserts the same pair plus the legacy reproduction.

**§94.6 item 3 — candidate seq 10 is NOT RUN, and the refusal is a measurement.** The corpus and fold
preconditions now pass (`run_seq10_candidate.py` prints `Corpus: …historical_dataset_2018_2023.json.gz`
and `Dataset: 1425 session(s), 1082 instrument(s), 1541850 bar(s)`). A **third** precondition then failed
during the baseline run, and it is not a defect in the corpus: the committed statutory cost schedule's
earliest `effective_dated_exchange_fees` row starts **2021-01-01**, so
`StatutoryCostCriteria.get_exchange_fee_for_date(2018-04-02)` raises
`CriteriaValidationError: No governing NSE exchange fee schedule found for trade date 2018-06-12` (the
first fill). No sourced pre-2021 NSE turnover rate exists in this repository — `data/raw/circulars`
holds calendar and surveillance circulars only — and §7.2 forbids a flat or invented rate, so pricing
2018 would be an unsourced numeric input (§6.5, §9.1). The runner therefore refuses **before** it
registers anything and names the schedule it lacks; `probe_seq10_candidate.py` reports the same blocker
next to the corpus state and exits 1 at `NOT CERTIFIED`. Measured state: `data/trials/` **N = 9** /
`evaluation_count = 5`, manifest `3326b1b2…` unchanged, no verdict artifact under
`reports/verdicts/trial_010/`, no path under `data/raw/2025` or `data/raw/2026` in any row, and
`scripts/probe_seq10_candidate.py`'s sealed-era arm still refuses `2025-01-02..2025-03-31` through
`HoldoutSealedError`. Item 3 remains the one part of the work order that is **NOT RUN**.

**§94.6 item 4 — the raw-Bhavcopy fallback is repaired, not retired.** `:648` no longer passes
`symbols_by_instrument=` to `compute_legacy_dataset_content_fingerprint` (the parameter does not exist)
and `:655` names `PriceConvention.UNADJUSTED_RAW` (the symbol that exists). A committed test builds the
fallback over two committed 2023 archives and asserts it returns a dataset whose
`price_convention is UNADJUSTED_RAW` and whose content fingerprint is `DATA-CTNT-V2-…`, so the dead path
is now a live one that states its convention.

**§94.6 item 5 — N-178: the seam's reachability is asserted, not only its shape.**
`_session_loop_passthrough_problem` now also reads the call's ancestors: an `If`/`While`/`Try` between
the call and its function, or an enclosing function other than `run_phase3b2_walkforward`, is refused
with "the harness call sits under … control flow". `probe_n178` is flipped and requires the §94.2
dead-guard mutation (`if forced_exits is None:`) to be refused for that reason; a committed test asserts
the same mutation. `probe_n177` still passes on the committed tree, so the passthrough's own check was
not weakened to get there.

**§94.6 item 6 — N-179: the superseded-row count is pinned.** `superseded_row_problems` adds two
assertions beside the field comparison: the superseded session-dated count must equal the **931** §94.3
measured, and every current window archive must still keep at least one superseded sibling, so a
deletion is refused *and* the missing artifact is named. The certificate prints `931 of 931 pinned` and
still reports `COVERED — 931/931`. `probe_n179` is flipped and requires the deletion of one superseded
row to be refused with the artifact named; a committed test asserts it.

**Criteria and scope.** Criteria **1.1.15** moves no numeric threshold and no criterion: it reseals
`expected_manifest_fingerprint` (item 1) and records that item 3 is **NOT RUN** with the pin
`expected_trial_registry_manifest_sha256` **unchanged**. `min_binding_evaluation_start_date` stays
`2018-04-01`, `expected_calendar_fingerprint` stays `CAL-FPR-V1-6acb5f45…`,
`expected_sourced_window_calendar_fingerprint` stays `2d5ac7ac…` (1,201 / 1,196), the 2024 validation
fold is frozen, and holdout `2025-01-01..2026-11-11` stays sealed. No file under `reports/audit/`, `AGENTS.md`, `.agents/skills/audit-round/SKILL.md`, `configs/trading_calendar_nse.json` or `configs/partition_spec.yaml` was written;
`data/trials/` is byte-identical to the parent commit.

**Measurements taken (not a verdict).** `tests/unit/test_phase3b2_audit_s95_items.py`: **5 passed**.
`probe_audit_findings.py N-177 / N-178 / N-179 / N-180`: **PASS 4/4**.
`probe_pre2022_bronze_coverage.py`: **exit 0**, `931/931`, `931 of 931 pinned`. `run_seq10_candidate.py`:
**exit 1**, `NOT REGISTERED` naming the 2021-01-01 schedule floor and the 2018-04-02 session.
`probe_seq10_candidate.py`: **exit 1**, `NOT CERTIFIED`, `N = 9 / N_eval = 5`. Before this commit
`verify_audit_findings.py` reported **28/29** probes matching, the exception being `probe_n170`, which
refused the new corpus because it was not yet tracked (`1 archive(s) differ from their blobs`) — the
probe working as designed; it is measured again on the committed tree in the green-cache row that
follows.

## §96 — work order §95.10 items 1-7 executed (Not audited)

**This section states what was measured. It grants no verdict:** nothing here has been reviewed by the
auditor, and every claim below is either a printed exit status or a number a committed script recomputes.

**Item 1 — statutory sources captured, levies made interval tables.** `scripts/ingest_statutory_sources.py`
captured 11 sources byte-exactly under `data/raw/circulars/<ref>/` (one `manifest.json` per payload with
`source_url`, `retrieved_at`, `byte_count`, `sha256`) and its `--check` passes. Every
`effective_dated_exchange_fees` row now carries `circular_sha256`; STT, the SEBI turnover charge and
stamp duty became `StatutoryRateInterval` half-open tables, and `costs.py` resolves them per session.
Two mid-window revisions are now modelled: the SEBI fee was halved for 2020-06-01..2021-03-31 and stamp
duty moved to the uniform Indian Stamp Act rates on 2020-07-01. The 2024 fee circular cited as
`NSE/FA/64323` resolves to 404; the real circular is **NSE/FA/64232** (2024-09-27). The IPFT 1,000× step
the audit read as a typo is real (NSE/FA/56129: "from existing Rs.0.01 per crore … to Rs.10 per crore"),
so both rows were correct. A pre-2021 row (from 2018-04-01, ₹3.25/lakh, IPFT ₹0.01/cr) makes
`statutory_cost_schedule_problem` return `None` for 2018-04-02, where §94.6 item 3 was NOT RUN.

**Item 2 — the corpus is point-in-time.** `scripts/derive_2018_2023_corpus.py` rebuilds
`data/reference/historical_dataset_2018_2023.json.gz`: **2,735 ISINs, 2,578,060 bars, 1,425 sessions**,
`universe_selection = POINT_IN_TIME_TRADED`, 1,646 members on the first session and 2,118 on the last,
`content_fingerprint DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15`. The 564 names §95.5.5 measured as
retroactively deleted are back on the dates they traded. 268 instruments were back-adjusted over 323
attested rows from exact split/bonus ratios applied strictly before each ex-date.

**Item 3 — the adjustment table is attested.** `data/reference/corporate_actions.jsonl` is **5,371 rows**
(sha256 `d7b425e5f444c8c0…`): 355 archive-attested rows appended carrying `source_digest` and
`source_artifact`, 75 digests backfilled onto rows already attested, and 10 unattested or contradicted
rows superseded by restatement — INFY's 2018-09-12 bonus (the archive dates it 2018-09-04) and IDEA's
2023-09-15 consolidation (no archive record exists) among them. 430 rows now carry a digest resolving to
a committed payload; BONUS 194, SPLIT 175, DEMERGER 68. Eight 2022-2023 payloads were captured, taking
`data/raw/corporate_actions/` to 23.

**Ruling 2's ±35% detector: measured, published, and not used as a build exit — a scoped deviation,
stated as such.** The rebuilt corpus classifies 826 one-session moves beyond ±0.35: 1 explained by an
applied row, 24 by a non-dividend archive record, 71 not ratio-shaped, 6 beside an archive action at
another ex-date, and **730 ratio-shaped but unattested**. Those 730 are not evidence of a missing
adjustment: they are rights-entitlement lines (`*-RE`) expiring at a fraction of the share price, ETF
unit re-denominations, the March-2020 circuit collapse (INDUSINDBK +44.7% on 2020-03-26) and the Yes
Bank moratorium (YESBANK −56.1% on 2020-03-06). §95.7 itself states that whether such a move is an
uncaptured action or a genuine one "cannot be decided from this repository". The header's
`reconciliation` block therefore carries all five counts, and the build gates on the three things that
are decidable: every archive-attested action applied, every applied row digest-resolved, every ex-date
equal to the archive's.

**Item 4/5 — demerger typed, exits attributable.** `CorporateActionType.DEMERGER` exists, 68 rows are
attested, and a position held across a demerger ex-date is forced out through the same harness one
session early with `exit_reason = DEMERGER_FORCED_EXIT`. Two counters were added
(`demerger_forced_exits`, `demerger_forced_refusals`) **after finding a defect this item introduced**:
`forced_exits` is the union of both reasons, so `hold_bound_refusals` was counting demerger refusals as
hold-bound ones and the bound-disabled counterfactual could not read 0/0. The baseline's figure is
**7,309** refusals on the corrected attribution.

**Item 6 — probes registered.** `N-181` (point-in-time universe), `N-182` (the 14 bonus examples applied
*and* absent from the corpus's returns), `N-183` (INFY dated 2018-09-04), `N-184` (IDEA consolidation not
applied), `N-185` (DEMERGER exit reason reaches the order). All five **PASS**; `--list` ends at `N-185`.

**Item 7 — trial 009 annotated, seq 10 registered.** `data/trials/trial_annotations.jsonl` records
`NON_REPRODUCIBLE_AT 77fb043` beside the row's committed `record_hash`
(`50de55e960ad59375c988fe88fef2fbf5e5a1155bd6315dacb09697d29429032`, unchanged): 175 hold-bound forced
exits, 203 refusals, **0 of 5** committed metrics reproduced, and the bound-disabled counterfactual also
fails (194 vs 193 closed trades, 1,164,053.76 vs 1,283,327.73), so the drift is not the bound's alone.
No historical metric was edited; the registry's hash chain is untouched because the annotation is a
separate append-only companion keyed by that hash.

**seq 10 (`TRIAL-PHASE3B2-EXPANDED-010`) is REGISTERED AND RUN.** N 9 → 10 with `evaluation_count`
still 5, window 2018-04-01..2023-12-31 (1,425 sessions, 2018-04-02..2023-12-29), **781 closed trades,
end equity 1,072,507.24, PF 1.058319814…, win rate 0.3854033290…, MaxDD 0.7264709014…**, 422 hold-bound
forced exits and 7,309 refusals. All **5 of 5** metrics reproduce the current-tree baseline exactly; the
bound-disabled counterfactual (413 trades, equity 1,501,180.25, PF 1.114037914…) shows what the consumer
itself costs. `scripts/probe_seq10_candidate.py` exits **0 — CERTIFIED**.

**Criteria 1.1.16.** No numeric threshold, criterion, fold, calendar pin or gating start moved.
`min_binding_evaluation_start_date` stays 2018-04-01, `expected_calendar_fingerprint` stays
`CAL-FPR-V1-6acb5f45…`, `expected_sourced_window_calendar_fingerprint` stays `2d5ac7ac…` (1,201/1,196),
the 2024 validation fold is frozen and the holdout stays sealed. `expected_manifest_fingerprint` is
re-sealed over the grown manifest (`MAN-FPR-V1-f5b1f1f1…`, including the corporate-actions manifest row
item 3 required) and `expected_trial_registry_manifest_sha256` over the appended registry
(`0246c276…`); `criteria_fingerprint` is `CRIT-FPR-V1-9ee0a88c…`.

**Gate state at this commit.** `pytest`: **561 passed, 0 skipped, 0 xfailed**. `verify_phase2a` and
`verify_phase2d`: exit 0. `probe_seq10_candidate.py`: exit 0. `probe_audit_findings.py`: N-181..N-185
PASS; N-170 refuses the rebuilt corpus until its bytes are committed, which this commit does.
`verify_audit_append_only.py --force-full`: green in the row that follows.

## §97 — work order §96.10 items 1-4 executed for N-186…N-190 (Not audited)

**Reviews:** `bb6d335` (tag `audit-s96-e094cbc`), the parent of this round. **Contract:** the §96 verdict at
`e094cbc` and its work order §96.10. **Nothing here is audited.** Every arrow below is a measurement this
round took, not a status the auditor has granted; `N-186`…`N-190` stay `OPEN` in the ledger until §97
says otherwise.

**Item 1 — N-190, the gate's verdict no longer depends on its own concurrency.** At `bb6d335` the gate ran
the whole suite under `-n auto --dist loadfile`, so `test_n1_replay_guard_o1_lookup_and_bounded_memory`
measured per-fill CPU beside fifteen other workers: §96.1 recorded 253.90–265.62 µs/fill against its 250.0
ceiling on two of four heavy runs of one unchanged tree (serial figure ~47 µs). `ISOLATED_TIMING_TESTS` now
deselects that node from the parallel invocation and `serial_pytest_command()` runs it in an invocation of
its own, where no xdist worker exists; `check_test_suite_zero_skip_xfail` reconciles the two counts against
`pytest --collect-only` instead of a literal, so a deselect that dropped a test cannot read green. Measured:
`--check-suite-only` exit 0 — `564 passed` parallel + `1 passed` isolated = **565 of 565 collected**,
66.89 s. **Neither ceiling moved** (`250.0` twice, `< 2.5` are byte-identical to `bb6d335`, and the
structural replay-guard count N-174 added is untouched). `probe_n190` was flipped first and exited 1 at
`bb6d335` (`the gate names no isolated timing test`).

**Item 2 — N-186, the statutory payload is the bytes git stores.** At `bb6d335` `probe_n186` measured
`NSE_STT_RATES (330003 stated vs 330001 stored; 5df41b04.. vs 91e8ace7..)`: `.gitattributes` opened with
`* text=auto eol=lf`, so the captured HTML's two CRLF bytes were rewritten on checkout and the attestation
described the download rather than the blob. The reconciliation taken is the one §96.10 item 2 offers as
its first answer and the working copy already held: **store what was retrieved.** A
`data/raw/circulars/*/** -text` rule pins every captured statutory payload to its own bytes (the calendar
JSONs at `data/raw/circulars/*.json` are not matched), and the payload was re-staged, taking the blob from
330,001 / `91e8ace7…` to the retrieved **330,003 / `5df41b04…`** — the value `manifest.json` and the four
`NSE_STT_RATES` criteria interval rows already carried, so neither the manifest, `data/reference/manifest.jsonl`,
the four `source_sha256` rows nor any threshold was edited for this item. Measured in a detached checkout of
this round's exact tree: `tests/unit/test_phase3b2_audit_s96_items.py` **4 passed**, `probe_n186` **PASS**,
`statutory_source_problem` **None**, `statutory_cost_schedule_problem` **None** — no working-copy bytes in
the path, because the checkout's bytes are the blob's.

**Item 3 — N-187/N-188, the builder fails on both directions of Ruling 2.** At `bb6d335` `failures` was
bound at `:296` and never read, and the class fired on **six** moves across four names (`UVSL`,
`ATNINTER`, `GVKPIL`, `WINSOME`) whose nearest archive record is an `Annual General Meeting` — a row that
carries no share ratio and therefore cannot be a mis-dated ratio. The near miss now requires a **price-side**
kind (`SPLIT`, `BONUS`, `CONSOLIDATION`), which is what the classifier's own sentence always said, and those
six re-enter the publish-only classes (5 `RATIO_SHAPED_UNATTESTED`, 1 `NO_RATIO_MATCH`); the move total is
unchanged at **832** (1 applied + 24 archive + 72 not-ratio-shaped + 735 ratio-shaped + **0** mismatch), which
is also the correction to §96's "826" — that figure was the four-bucket total and excluded the six it named.
`require_no_ex_date_mismatch(failures)` now raises naming ISIN and session, and
`require_attested_actions_present(attested_actions_missing_from_table())` calls
`attest_price_actions.reconcile()` from `build`, so the missing-set direction that §96.4 measured at
0 refusals / 300 applied is a build exit. Measured: the corpus was rebuilt —
**2,735 ISINs / 2,578,060 bars / 1,425 sessions, 0 ex-date mismatch (was 6)**, content fingerprint
`DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15` unchanged (prices are untouched; only the header's
reconciliation counts moved), `75,390,038` bytes / `609084fa…`, and `--check` reads **`OVERALL: CURRENT`**
over 1,425 archives. Withdrawing the attested row `SRF 2021-10-13` from a copy of the table now names
`INE647A01010 2021-10-13 BONUS` as a gap; the committed table's gap set is empty. `probe_n187` and
`probe_n188` were flipped first and both exited 1 at `bb6d335` (`exposes no ex-date-mismatch gate`,
`exposes no attested-action completeness gate`).

**The pin this forced, stated because it is the cost of item 3.** The rebuilt corpus supersedes its own
manifest row and appends one (`1,970` rows: `1,009` current + `961` superseded), so
`expected_manifest_fingerprint` is re-sealed to `MAN-FPR-V1-e79d791518a4…` over **1,876,489** bytes and
`reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` is regenerated (Gate 2D-5 compares bytes).
No numeric threshold, criterion, fold, calendar pin or gating start moved; `criteria_version` is **held at
1.1.16** deliberately rather than bumped, because the seq-10 registry row is append-only and declares
`1.1.16`, so a bump would make `probe_seq10_candidate.py` refuse the row it was registered under. The cost
is named: `criteria_fingerprint` moves from `CRIT-FPR-V1-9ee0a88c…` to `CRIT-FPR-V1-b2876d98…` **without a
version bump**, so `1.1.16` now labels two contents and a citation of the version is not a citation of the
fingerprint. `probe_seq10_candidate.py` then exits **0 — CERTIFIED** on this tree (N 10, N_eval 5, fold
`36a39987…`, baseline `f5fe3af5a1e2de83…`, 422 forced exits / 7,309 refusals).

**Item 4 — N-189, the demerger refusal counts a refused exit of a held position.** At `bb6d335`
`demerger_exits` was every non-superseded `DEMERGER` on the session after `next_session`, archive-derived,
while the harness skips an ISIN the book does not hold, so 66 events were reported as 66 refused exits with
0 fills. `count_forced_exit_outcomes(forced_reasons, held_isins, filled_isins, reason)` now computes
`(exits, refusals)` over `forced_reasons` entries whose ISIN is **held** (passed for the demerger pair,
whose refusals used `demerger_exits - demerger_filled`), with the held set read from the position book before
the session executes. `tests/unit/test_phase3b2_audit_s97_items.py` asserts the pairing — one held fill reads
(1, 0), one held refusal (0, 1), two held and none filled (0, 2), an unheld event (0, 0), and the bound pair
never absorbs a demerger fill — **4 passed**. `probe_n189` was flipped first and exited 1 at `bb6d335`
(`still counts forced exits without a held-position rule`). **Not done, deliberately:** the committed seq-10
artifacts still read `demerger_forced_exits 0` / `demerger_forced_refusals 66`, because they record a run
made by the previous counter and re-running seq 10 would rewrite a certified registration; whether any
position was ever held across a demerger ex-date therefore remains **unmeasured** on this tree, as §96.10
item 4's second clause asks, and the constraint is measured on synthetic holds instead.

**Not in this round's order, unchanged:** §96.10 items 5 (superseded rows in `get_corporate_actions()`),
6 (the certificate reading the `NON_REPRODUCIBLE_AT` annotation) and 7 (the carried residuals, N-150
included). `N-186`…`N-190` remain `OPEN` pending the auditor's §97.

**Gate state at this commit.** `pytest`: **565 passed, 0 skipped, 0 xfailed** (`564 + 1 isolated`).
`probe_seq10_candidate.py`: exit 0. `derive_2018_2023_corpus.py --check`: `OVERALL: CURRENT`. Probes
N-186…N-190 all `PASS`; `verify_audit_findings.py` runs every ledger row's probe. `verify_audit_append_only.py
--force-full` is run on this commit's tree and the row that follows records it.

## §98 — work order §97.10 items 1-4 executed for N-191…N-194, and a read-only seq-10 drawdown diagnostic (Not audited)

**Reviews:** `bf5de9f` (tag `audit-s97-78da364`), the parent of this round. **Contract:** the §97 verdict at
`612e82a`/`437e0c4` and its work order §97.10. **Nothing here is audited.** `N-191`…`N-194` stay `OPEN` in the
ledger until the next audit section says otherwise; every number below is a measurement this round took.

**Item 1 — N-191, no cross-gap pair enters the reconciliation as a return.** At `bf5de9f`
`classify_extreme_moves` zipped `bars` with `bars[1:]` and called the quotient a *one-session* return without
asking whether the two `trade_date`s were consecutive sessions, so 16,194 adjacent pairs straddled a calendar
gap and 58 of its 832 extremes were computed across one. The classifier now takes `trading_dates` and computes
`calendar_previous` first; a pair whose dates are not consecutive is a **gap record** (`cross_gap_pairs`,
`cross_gap_moves`) and never reaches a class. The corpus was rebuilt: the reconciliation now accounts for
**774** moves (was 832) — **1** applied row, **0** archive record, **699** ratio-shaped unattested, **74** not
ratio-shaped, **0** ex-date mismatch — with **16,194** cross-gap pairs and **58** cross-gap extremes published
as `cross_gap_detail` instead of as returns. `INE251H01024` 2022-08-12 (+1.2800 after a bar from 2021-08-02)
and `INE784B01035` 2023-09-26 (+56.0000 after 2020-07-20) are now gap records. `probe_n191` was flipped first
and exits **1** at `bf5de9f` (`the classifier takes no calendar…`).

**Item 2 — N-192, only a price-side record may explain a move.** The exact-date branch admitted any
non-`DIVIDEND` record before the ratio test, so an AGM, scheme, rights or demerger record disposed of the move.
Exoneration is now `kind in PRICE_SIDE_KINDS` only; a non-price-side record at the exact date is published as
`RATIO_SHAPED_UNATTESTED` with the record named (`ratio_shaped_detail[].record`). Measured on the rebuilt
corpus: `explained_by_archive_record` **0** (was 24), `ratio_shaped_unattested` **699** (was 735),
`no_ratio_match` **74** (was 72), and **18** ratio-shaped moves name their non-price-side record — including
`INE803A01027` 2019-09-16 **+0.5000** under an `OTHER` record, which §97.3 measured as a 2× move filed as
explained by an Annual General Meeting. `probe_n192` was flipped first and exits **1** at `bf5de9f`.

**The pin this forced, stated because it is the cost of items 1-2.** Prices, bars, sessions and
`content_fingerprint DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15` are unchanged; only the header's
reconciliation moved. The rebuilt artifact is **75,390,706 bytes / `ea0b65a3…`**, its manifest row supersedes
the previous current row (`1,971` rows: `1,009` current + `962` superseded over **1,877,557** bytes), so
`expected_manifest_fingerprint` is re-sealed to `MAN-FPR-V1-be45b7e7…` and `criteria_fingerprint` moves
`b2876d98…` → **`535e47f5…`**. No criterion, threshold, fold boundary, calendar pin, cost-schedule row or
gating start moved (`git diff configs/go_no_go_criteria.yaml` is one pin line and a comment), and
`criteria_version` is **held at `1.1.16`** for the reason §97.7 gives — the seq-10 registry row is append-only
and names it. `N=10`, `N_eval=5`, the 2024 validation fold untouched (`validation_folds_count = 0`) and the
holdout `2025-01-01..2026-11-11` unread.

**Item 3 — N-193, a certificate's fingerprint is compared with the live one.** `probe_seq10_candidate.py`
now carries `certificate_problem(certificate, live, criteria, restatement)`: a stored `criteria_fingerprint`
that differs from the live one is refused unless an appended restatement names that artifact, the executed
fingerprint and the executed manifest pin, **and substituting that pin into the live criteria reproduces the
cited fingerprint exactly** — the recomputation is the attestation, so any other change would move the hash.
`reports/analysis/s98/criteria_restatement.json` records `CRIT-FPR-V1-9ee0a88c…` executed under
`MAN-FPR-V1-f5b1f1f1…` for all three certificates (the trial_010 pair and the s94 baseline), with the §97 pin
`e79d7915…` → `b2876d98…` recorded as the intermediate step. Substitution reproduces both hashes; the gate
refuses a stale live hash, a forged executed fingerprint and a pin that does not reproduce, by name.
Measured: `probe_seq10_candidate.py` **exit 0 — CERTIFIED**, all three certificates reconcile with
`535e47f5…`, demerger pair `0/66` restated. `probe_n193` was flipped first and exits **1** at `bf5de9f`.

**Item 4 — N-194, the seq-10 demerger pair is restated by measurement.** The committed artifacts are **not
edited** (§10.1); `scripts/diagnose_seq10_drawdown.py` re-renders seq 10's own configuration (same
`BASELINE_TRIAL_ID`, window, criteria and parameters) into a temporary registry copy and publishes
`reports/analysis/s98/seq10_demerger_restatement.json`. Measured: `demerger_forced_exits 0` /
`demerger_forced_refusals` **0** (was `0` / `66`) over **1,425** sessions — no position was ever held across a
demerger ex-date in the only run that exercised the constraint, and the 66 were events on ISINs the book did
not own. The replay is tied to the artifact it restates: `hold_bound_forced_exits` **422**,
`hold_bound_refusals` **7,309**, **781** closed trades, `max_drawdown 0.7264709014681672238018483779`,
`final_equity 1072507.24` — the committed artifact's own numbers — and the registry's four files hash
identically before and after (`mutated: false`), so no registration was rewritten. The certificate refuses an
artifact that publishes a pair with no restatement, a restatement whose restated pair differs, and a
restatement with no measurement.

**Request item 3 — the read-only seq-10 drawdown and refusal decomposition** (`reports/analysis/s98/seq10_drawdown_decomposition.json`,
no registry mutation). The equity curve's 72.65% maximum drawdown is reached **inside March 2020**, on a book
already down 57.76% through 2018-2019:

| Period | Sessions | Max DD (running peak) | Closed trades | Net PnL (₹) | Ticket rejections |
|---|---|---|---|---|---|
| 2018-04-01..2019-12-31 | 430 | 57.7646% | 213 | **−444,938.84** | 2,547 |
| 2020-01-01..2020-02-28 | 43 | 58.9076% | 21 | −11,263.57 | 359 |
| 2020-03-02..2020-03-31 | 21 | **72.6471%** | 15 | −49,385.74 | 186 |
| 2020-04-01..2023-12-29 | 930 | 70.8510% | 532 | **+560,926.56** | 3,897 |

The first 430 sessions carry 213 of 781 closed trades and lose 44% of starting capital; the recovery is earned
in 2020-04..2023-12 (+₹560,926.56) and never closes the 2018-2019 hole in absolute terms (final equity
₹1,072,507.24 on ₹1,000,000 after 1,424 marked sessions; the 1,425th executed session carries no snapshot).
Exit mix is bound-dominated (`MAX_HOLD_BOUND_EXIT` 422 of 781, `STOP_LOSS` 304, `SIGNAL_EXIT` 55), and **16**
positions were open at the window end.

By entry-date liquidity (20-session median traded value before entry, from the committed corpus):

| Tier | Closed trades | Net PnL (₹) | Costs (₹) |
|---|---|---|---|
| ADTV20 ≥ ₹25 cr | 271 | **+176,025.68** | 43,493.65 |
| ₹5 cr ≤ ADTV20 < ₹25 cr | 314 | −93,852.09 | 48,276.39 |
| ₹1 cr ≤ ADTV20 < ₹5 cr | 152 | −104,927.79 | 22,674.69 |
| ADTV20 < ₹1 cr | 44 | +78,092.62 | 6,766.33 |

3 trades had no prior 20-session history and fall in the `< ₹1 cr` row by construction. The mid-tier book (466
trades) is where the 2018-2023 loss sits; the top tier and the sub-₹1 cr row are positive on 271 and 44 trades,
so the last row is a small-sample observation, not a finding.

**Refusals — the 7,309 are not circuit freezes, and the units differ.** `hold_bound_refusals` is a
**position-session** counter (a refused exit is counted again on the next session, which is what makes a
frozen bid an unbounded delay, §5.3), while the session summaries attribute **6,989** ticket rejections:
`SELL:REJECTED_INSUFFICIENT_TURNOVER` **5,294**, `BUY:REJECTED_INSUFFICIENT_TURNOVER` **1,322**,
`BUY:REJECTED_RISK_LIMIT` **367**, `BUY:REJECTED_LOCKED_SESSION` **4**, `SELL:REJECTED_LOCKED_SESSION` **2**
(`locked_bar_refusals` 6, all in 2020-04..2023-12). **6 of 6,989** attributed rejections are locked sessions,
so in this configuration the binding exit constraint is liquidity/participation
(`REJECTED_INSUFFICIENT_TURNOVER`), not a circuit freeze. This decomposes the two counters as each is defined
rather than re-attributing one to the other, and it is what seq 11 should size against.

**Not in this round's order, unchanged:** §97.10's carried items — §96.10 item 5 (superseded rows in
`get_corporate_actions()`), item 6 (the certificate reading the `NON_REPRODUCIBLE_AT` annotation) and item 7
(the carried residuals, `N-150` included). `N-191`…`N-194` stay `OPEN` pending the next audit.

**Gate state at this commit.** `pytest --collect-only`: **571** collected; parallel invocation **570 passed**
in 87.80 s (replay-guard benchmark deselected) + isolated **1 passed** in 2.38 s = **571 of 571**, 0 skipped,
0 xfailed. `tests/unit/test_phase3b2_audit_s98_items.py` **6 passed**. Probes N-187 and N-191…N-194 all `PASS`
on this tree, and N-191…N-194 each exit **1** in a detached worktree at `bf5de9f`.
`probe_seq10_candidate.py`: **exit 0 — CERTIFIED**. `verify_phase2a_containment_and_trials.py` and
`verify_phase2d_verdicts.py`: exit 0 after the criteria restatement was moved out of `reports/verdicts/` (a
note is not a verdict artifact: G2A-6.7 read it as a post-sidecar verdict with no ledger row, and the pre-2022
pin test read it as a verdict). One red on the pre-commit tree is recorded because it is real:
`verify_audit_findings.py` exits 1 on `N-170` alone, because the rebuilt corpus is not yet the byte git stores;
`N-170` is green only once this commit's corpus bytes are in the object store, which this commit does.`verify_audit_append_only.py --force-full` is run on this commit's tree and the row that follows records its verdict.

## §99 — work order §98.10 items 1-4 executed for N-191…N-194, and strategy candidate seq 11 registered and scored (Not audited)

**Item 1 — N-191 residual, features never compute across an unverified gap.** `feature_gap_boundaries` and
`trailing_continuous_bars` partition an instrument's sessions at every `UNEXPLAINED_MISSING_RECORD` and
return only the bars since the last hole; `median_turnover_as_of` in `pit_universe.py` now takes its 20-session
T-1 median inside one subsegment. The partition is a committed measurement, not a claim:
`reports/analysis/s99/feature_gap_partition.json` (`2.0 MiB`, fingerprint
`GAP-PTN-V1-3fe08af638a6ee72…`) covers **539** instruments, **58,941** missing sessions, **16,733**
subsegments and **74** material holes, and of **28,457,131** feature values **0** is computed across a gap.
`probe_n191` was extended to recompute the artifact's fingerprint, re-warm its witnesses and refuse a
20-session window that spans a hole: exit **0** in ~18 s on this tree, and exit **1** before the artifact existed.
The attack that must fail closed was run: removing the subsegment break in `exchange_series.py` makes it exit
**1** with `INE251H01024 has 27 contiguous hole(s) but 1 segment(s)`.

**Item 2 — N-194 residual, the demerger pair must be compared, not assumed.**
`demerger_restatement_problem` now reads the restatement's `measurement` demerger keys and the re-rendered
`replay` keys and refuses an absent pair or a disagreement; the pre-fix function returned `None` for a
measurement of `7/9` beside a replay of `0/0`. `probe_n194` carries both mutants and exits **1** on each.

**Item 3 — N-193, the certificate runs in the gate.** `scripts/verify_seq10_certificate.py` calls
`probe_seq10_candidate.main()` and is listed in `GREEN_CACHE_RUNTIME_VERIFIERS`, so the gate now discovers
**10** verifiers and certifies the three seq-10 certificates at
`CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470`; it exits **0 —
CERTIFIED**. `TrialEvaluation.criteria_fingerprint` is an optional evaluations field, included in the hashed
payload only when bound, and seq 11's evaluation row cites that fingerprint.

**The pin this forced, and the one deviation from the order's own wording.** Registering seq 11 appended a
registry row, so `expected_trial_registry_manifest_sha256` is re-sealed to **`b8ff325c…`**
(`N-139` keeps it out of `compute_criteria_fingerprint`, which is why the live hash above is unchanged and the
three seq-10 certificates still reconcile pin-only). `criteria_version` is **held at `1.1.16`** for §97.7's
reason. The order named `configs/go_no_go_criteria.yaml` as the place for seq 11's controls; they were put in a
new **`configs/trial_011_candidate.yaml`** instead, because adding any field or threshold to `GoNoGoCriteria`
moves `compute_criteria_fingerprint` past a pin-only difference, and §98.6 Ruling 1 can only attest a pin-only
difference to the three stored certificates — a field added there would have made the certificate, and the new
gate verifier, refuse permanently. Controls, hypothesis, success criteria and falsifier are all in that file;
nothing was thresholded after the run.

**Item 4 — seq 11, T-1 ADTV ≥ ₹25 Cr and 0.75%-1.0% ATR risk, registered before the run.**
`N = 10 → 11`, `N_eval = 5 → 6`, walk-forward `2018-04-02..2023-12-29`, artifacts in
`reports/verdicts/trial_011/`. Measured:

| Metric | seq 10 | seq 11 |
|---|---|---|
| Closed round trips | 781 | **1,101** |
| Final equity (₹, 1,000,000 start) | 1,072,507.24 | **1,789,528.81** |
| Profit factor | 1.058319814… | **1.215059254…** |
| Liquidated profit factor | 1.062288461… | **1.281989670…** |
| Max portfolio drawdown | 0.7264709014681672 | **0.5193109028986467** |

The drawdown claim is met: **−0.2071599985695204731369764373 absolute, 28.5159% relative**, the pre-registered
falsifier for that claim did not trigger, and the floor removed **1,974,755** ISIN-sessions from the entry
universe. It is *not* a passing candidate. The pre-registered success criteria score
`{drawdown_reduced: true, liquidated_pf_≥_1.50: false, closed_trades_≥_100: true}`, the criterion table is
**15 PASS / 6 FAIL / 7 NOT RUN**, and **CRIT-STAT-02 is FAIL** because the liquidated profit factor 1.282 is
below the committed 1.50. Seq 11 is therefore rejected on its own stated terms even though it improves on
seq 10 on both drawdown and profit factor; the row stays in the registry as a scored trial, and the Sharpe
reported for it is a rejected candidate's, not a strategy result.

**Disclosed, not gated.** The per-trade liquidity check of the entry sessions names **1,101** trades and
**2** unresolved keys — `INE947Q01028@2020-09-09` and `INE484C01030@2021-06-18` — both ISIN transitions where the
ledger's ISIN has no continuous window on the fill date and the bars sit under the neighbouring identity. That
is a property of the check's key, not evidence the floor was bypassed (the enforcement evidence is the
per-session exclusion counter), so the comparison publishes the row with its cause instead of shaping a verdict
with it. A later round should carry the signal date on the trade ledger and resolve identity there.

**Gate repair this round forced, and what it changes.** Two checks were pulled red by the append itself, and
neither was repaired by relaxing it:

- `G2A-6.7` exemption (§95.10 item 7): a registered re-render declares the ledger count it ran under, and the
  check compared that number with *today's* total, so seq 11's sixth evaluation retroactively un-attested seq 10.
  It now compares against the evaluations that precede the artifact's own row (`prior_evaluations`); an erased
  ledger computes 0 there and still fails, and a doctored artifact still fails.
- The comparison artifact names its own trial, so `H-122`/`N-128` requires it to carry the ledger's score:
  `seq11_vs_seq10_comparison.json` now publishes `annualized_sharpe 0.5599216299726306768891701591` verbatim.

**Gate state at this commit.** `pytest --collect-only`: **577** collected; parallel invocation **576 passed** in
63.33 s (replay-guard benchmark deselected) + isolated **1 passed** in 2.41 s = **577 of 577**, 0 skipped,
0 xfailed. `tests/unit/test_phase3b2_audit_s99_items.py` **6 passed** (gap partition, gap-bounded median,
measurement-vs-replay mutants, optional fingerprint). `probe_seq10_candidate.py`: **exit 0 — CERTIFIED**.
`verify_phase2a_containment_and_trials.py` and `verify_phase2d_verdicts.py` exit **0**.
`verify_audit_append_only.py --force-full` is run on this commit's tree and the row that follows records its
verdict. `N-191`…`N-194` stay `OPEN` pending the next audit; the 2024 validation fold is untouched
(`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` unread.

## §100 — work order §99.10 items 1-3 executed for N-195, the verifier inventory and the criteria-fingerprint surface, plus a read-only seq-10 benchmark comparison (Not audited)

**Not audited.** Everything below is the implementer's measurement at parent `9d9c80a` (§99, tag
`audit-s99-6177503`). No audit section reviews it yet, so no row here is signed off, verified or closed by a
verdict: `N-195`'s fix has landed and the finding's ledger status remains the auditor's row to append (§11.1),
and nothing below cites a §N verdict because none exists for this commit.

### Item 1 — N-195: the seq-10 profitability cells now carry the artifact's own digits

The `seq 10` column published `1.1178…` / `1.1773…`; no committed artifact, verdict, config or script computed
either. `probe_n195` was rewritten first as the **fix-assertion** and run at `9d9c80a` before any edit:

```
FAIL N-195: the seq-10 status row publishes '| Profit factor | 1.1178… | **1.215059254…** |' but the artifact
computes closed-only profit factor 1.058319814406791810331206697 for its 781 closed round trips (§9.1)
```

The probe reads `closed_only_profit_factor` and `liquidated_profit_factor` out of
`reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json` and requires the document's two
cells to carry those digits, so the row cannot drift from the artifact it cites without the probe failing. With
the cells corrected to **`1.058319814…`** and **`1.062288461…`** the probe exits **0**; `1.1178` / `1.1773` are
refused by name and no file under `reports/verdicts`, `reports/analysis` or `configs` contains `1.1178`.

One basis detail found while doing it and worth recording, because it is a second two-bases-in-one-document
fact: the artifact's `closed_only_profit_factor` (1.058319814…) is computed on **gross** round-trip P&L, while
its `in_sample_metrics.win_rate` (0.385403329…) counts a win on **net** P&L — 305 gross winners, 301 net
winners, over the same 781 trades. The status row quotes the fields on the basis each field actually uses; the
new comparison artifact reports both bases for both arms.

### Item 2 — the verifier inventory is pinned, so a deletion fails closed by name

Discovery was a bare `glob("verify_*.py")`: §99.3 measured that deleting one verifier dropped the count
from 10 to 9 with no complaint. `scripts/verify_audit_append_only.py` now carries
`EXPECTED_VERIFICATION_SCRIPTS` (10 names) and `verification_inventory_problem()`, which fails in **both**
directions — a pinned verifier missing from discovery, and a discovered verifier not in the pin — and names the
file. It is enforced on the full run (before any verifier executes) and on the reuse decision, where a stale
pin would otherwise let a shrunken set be reused as green (§14.4).

Measured, with `scripts/verify_wave1_thin_slice.py` moved out of the tree:

```
[FAIL] Gate W0.5-2: pinned verifier(s) missing from discovery: scripts/verify_wave1_thin_slice.py — a check
left the gate by deletion (§99.10 item 2, §12.4)
OVERALL VERDICT: ONE OR MORE GATES FAILED          (exit 1)
```

Restored, the same command is green at 10 of 10. The file was moved back and `git status` shows no residue.

### Item 3 — the registry reader surface shows the executed criteria fingerprint

`TrialRegistry.criteria_provenance(trial_id)` returns the row's `criteria_version` **and** the executed
`criteria_fingerprint` recorded on its evaluation sidecar, or `None` when the row carries no recorded hash —
`criteria_version` alone now labels three criteria sets, so the surface says *not recorded* instead of letting
the version stand in for the hash. The certificate's registry readout prints it:

```
[INFO] seq 10: TRIAL-PHASE3B2-EXPANDED-010, criteria 1.1.16, executed NOT RECORDED (no evaluation-sidecar hash
for this row), partition IN_SAMPLE
```

Measured directly: `criteria_provenance("TRIAL-PHASE3B2-LIQUIDITY-ATR-011")` returns `CRIT-FPR-V1-535e47f5a4a9…`
under `1.1.16`, and `…-EXPANDED-010` returns `None` under the same version. `verify_seq10_certificate.py` still
exits **0 — CERTIFIED** with the new line.

### Item 4 — the baseline comparison: KILL the strategy family, computed not typed

`scripts/compare_seq10_baselines.py` is read-only: it writes no registry row, appends no evaluation, writes no
verdict artifact and refuses any sealed session. Artifact:
`reports/analysis/s100/seq10_baseline_comparison.json` (4,799 bytes, sha256
`b5c14b9f5f7b5b2e239360b6ca3e1165532f20be1c47ae2e669e9b00e58a7528`), reproducible byte-for-byte with
`--check`; window `2018-04-02..2023-12-29` (1,425 sessions), the corpus's **2,735** instruments, criteria
`1.1.16` / `CRIT-FPR-V1-535e47f5a4a9…`, dataset `DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15`.

| Arm | Profit factor (round trip, net of statutory costs) | Profit factor (session curve) | Max drawdown | Win rate | Final equity (₹ from 1,000,000) |
|---|---|---|---|---|---|
| seq 10 (781 round trips) | **1.020542895…** (gross 1.058319814…) | 1.012107560… | **0.7264709014681672238018483779** | **0.3854033290653008962868117798** round trips (0.5105337078 sessions) | **1,072,507.24** |
| NIFTYBEES buy-and-hold (1 round trip) | n/a — one round trip has no ratio | 1.196362450… | 0.3633661102218156871712782986 | 0.5534458509142053445850914205 sessions | **2,242,471.30** |
| Randomized entry (200 draws × 781 trades, seed 100010010) | median **1.299237476…**, p05 1.039159477…, p95 1.602716450… | median 1.102588968… | median 0.5133485053109480802412298532 | median 0.4647887323943661971830985915 | — |

The strategy arm is attested, not quoted: the script recomputes final equity (1,072,507.24 to the paise),
max drawdown (equal to the artifact's to 1e-24), the gross round-trip profit factor (exactly
1.058319814406791810331206697) and the net round-trip win rate (exactly 0.3854033290653008962868117798) from
the artifact's own `daily_returns` and `closed_trades`, and refuses to publish if any of the four fails.

The pre-registered decision rule, recorded in the artifact before the run:

> GO iff `seq10.trade_profit_factor > p95(random_entry.trade_profit_factor)` AND
> `seq10.final_equity > niftybees_buy_hold.final_equity`; otherwise KILL.

Computed: `signal_condition_met = false` (1.0205 < 1.6027 — and seq 10 is below the null **median** 1.2992,
not merely below its tail), `investability_condition_met = false` (₹1.07 M against ₹2.24 M for a
buy-and-hold ETF). Verdict from the rule: **KILL — the strategy family is not carried into seq 12.** The
randomized-entry null beats the momentum signal on all three published metrics — higher profit factor, higher
round-trip win rate, shallower drawdown — so the signal's selection and timing are not merely unproven against
random entry on this window; they are worse than it.

**What the comparison does not model, stated rather than implied.** The randomized arm pays statutory costs
only (no market impact, no slippage, no dividend income inside a hold, no competitive cash constraint), so it
is advantaged on cost and disadvantaged on dividends against seq 10; it draws from the full point-in-time
universe including small caps, so it carries more beta than seq 10's ranked book; and it exits at a fixed
horizon with no stop. 77,191 (49.4%) of its draws were refused by the 2.5%-of-traded-quantity cap and redrawn,
and 48 matched trades exhausted 8 attempts and were dropped. None of these leans in the strategy's favour, so
none can turn the KILL into a GO; they are the reasons the verdict is *conservative*, not reasons it is wrong.

**The NIFTYBEES benchmark leaves two sessions unmeasured, by design.** The ETF trades under two ISINs in this
window (`INF732E01011` → `INF204KB14I2` from 2019-12-20) and its price level steps ~10:1 inside the old ISIN's
last bar. The committed corporate-action table records the transition with share ratio **1:1** and provenance
`CONTENT_IDENTIFIED_ONLY`, i.e. the split ratio that would make the two halves comparable is **not attested**;
chaining the levels would book a fabricated **−89.93%** session. The benchmark is therefore built from
within-ISIN returns with 2019-12-19 (level break) and 2019-12-20 (identity change) named as unmeasured, 1,422
of 1,424 session returns retained, and the sell leg priced on turnover because the split ratio needed to state
an exit unit count is exactly the unattested fact. Final equity is net of ₹3,523.70 of statutory delivery
costs for the single ₹10 lakh entry.

**Not a trial, and it moves nothing.** The comparison appends no registry row, adds no evaluation, explores no
parameter and selects no rule: `N = 11`, `N_eval = 6`, criteria `1.1.16` and its pin are unchanged, the 2024
validation fold stays frozen (`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` is unread.

**Gate state at this commit.** `tests/unit/test_phase3b2_audit_s100_items.py` **9 passed** (the N-195
fix-assertion, the inventory pin in both directions plus the deletion attack through `check_verification_scripts`,
the provenance surface on both a fingerprinted and an unfingerprinted row, and the comparison's curve convention
rebuilding the artifact's drawdown). `verify_seq10_certificate.py` exit **0 — CERTIFIED**.
The new comparison script's `--check` exits **0** against its committed bytes. `verify_audit_append_only.py` (`--force-full` and
plain) is run on this commit's tree and the row that follows records its verdict.
## §101 — seq 12 pre-registered and implemented, then stopped by its own Step 2 data QA (Not audited)

**Not audited.** Nothing below is reviewed by an audit section, so nothing below is signed off, verified or
closed by a verdict: there is no `§N` for this commit and the findings ledger holds whatever the auditor last
appended. What is written here is what was measured, and what was deliberately not measured.

### Pre-registration (committed before any code ran)

`configs/trial_012_candidate.yaml` was committed alone at **`f2133ef`**, sha256
`66a05b4a0c6562fe10579ec0e8369577b02b1f49437aa2d37475dee903a3bfa6`, before the strategy class, the runner
wiring, the QA pass or the run existed. It carries the whole specification — one rule, no alternative, no
variant — the four-clause decision rule and the null's construction. The registry stood at **N = 11**,
**N_eval = 6** before registration and stands at **N = 11**, **N_eval = 6** after this round: **no trial row
was appended**, because the QA below stopped the round before any session was simulated.

**The window's first signal is not its first session.** The pre-registered window opens 2018-04-02 and the
corpus begins there, so the 200-session trend filter cannot exist before the corpus's own first 199 sessions
have passed. Measured: `sma_200` first exists on **2019-01-18**, and the first entry signal is on that same
session. `first_signal_is_window_open = false` is published in the artifact rather than assumed.

### Step 1 — implementation (constraints, not results)

- `InstrumentTechnicalFeatures` gains `sma_5`, `sma_200` and `rsi_2`, computed through the same
  `compute_standard_features_for_instrument` subsegment partition as every other field, so a lookback still
  cannot cross an unexplained missing session (§6.3).
- `MeanReversionSwingStrategy` (`src/signal_core/strategy/mean_reversion.py`) is the pre-registered rule and
  nothing else: entry `close > SMA(200) and RSI(2) < 10`, exit `close > SMA(5)`, both stamped
  `signal_date = T` / `target_date = T+1`.
- `run_phase3b2_walkforward` takes an optional `strategy=`: the rule is a parameter of the single engine
  (§7.4, §13.5), so sizing, the protective stop, the hold bound, fills, costs and the ledger are shared with
  seq 10 and seq 11. No second fill or cost path exists.
- `tests/unit/test_phase3b2_seq12_mean_reversion.py` — **7 passed**: RSI(2) on a hand-computed Wilder series
  (100.00 / 50.00 / 25.00), features at T unchanged when every bar after T is rewritten, no entry before 200
  sessions with the same session and the filter present as a non-vacuous control, entry and exit both
  targeting T+1 with the contract refusing a same-session fill, the stop filling at its own price inside the
  bound, and at the bound one open exit with the stop retired rather than a second sell.
- `tests/unit/test_phase3b2_seq12_data_qa.py` — **7 passed** over the QA classifier and its gate.

### Step 2 — the data QA stopped the round (this is the round's outcome)

`reports/analysis/s101/seq12_data_qa.json`, 7,363 bytes, sha256
`54c08bcbe7b76b43130be0335c7366dfacf03e843f863cc2ffb6f68e13f784d7`, reproducible byte-for-byte with
`python scripts/run_seq12_candidate.py --check` (exit 0). Counts and lists only; no return and no P&L was read
to produce it.

| QA measurement | Value |
|---|---|
| sessions / instruments scanned | 1,425 / 2,735 |
| entry signals (pre-registered condition, EQ-active, in the PIT universe) | **93,463** |
| signals in a series the master does not resolve to `EQ` (not entry signals) | 15,441 |
| signals blocked by the ₹25 Cr T-1 median-20-session ADTV floor | **75,496** |
| signals blocked by a locked T+1 session (`high == low`) | **431**, all 431 with **no band record** at T+1; 0 at a lower limit, 0 at an upper limit |
| signal days whose one-session adjusted return is below −20% | **8** |
| … of those, a **change of price level at the open** (opening gap ≤ −20%) | **5** |
| … of those, a session that traded down after a continuous open | 3 |
| **unattested level steps feeding a signal** | **5 — the STOP** |

The five unattested level steps, each an opening gap on a signal day with no price-side corporate action on
that date (`records_on_date` empty, `records_near_date` empty):

| Symbol | ISIN | Signal session | One-session return | Opening gap | Ratio shapes that would print it |
|---|---|---|---|---|---|
| ASTRAL | `INE006I01046` | 2021-03-18 | −0.3011 | **−0.2972** | 10/7 |
| VARDHACRLC | `INE116G01013` | 2021-10-28 | −0.2177 | **−0.2951** | 14/11 (a `DIVIDEND` row on the date cannot reprice anything) |
| DTIL | `INE341R01014` | 2021-08-05 | −0.3348 | **−0.3668** | 3/2 |
| HEUBACHIND | `INE492A01029` | 2020-07-16 | −0.2481 | **−0.2846** | 4/3 (a `DIVIDEND` row on the date, same reason) |
| MANINFRA | `INE949H01023` | 2021-11-17 | −0.2233 | **−0.2802** | 9/7 |

The three signals below −20% that are **not** level steps are published and do not stop the round:
`INE292A01023` 2019-12-18 and 2019-12-30 (opening gap 0.0000 on a ₹0.15 scrip whose close fell one ₹0.05
tick) and `INE669E01016` 2022-01-11 (opening gap −0.0976, the fall inside the session). The exchange traded
those sessions, the pre-registered rule is written to buy exactly that pullback, and nothing about them is
unattested. Raw Bronze agrees: `cm18DEC2019` prints UVSL opening at its previous close of 0.15, while
`cm05AUG2021` prints DTIL opening at 330 against a 521.15 previous close.

Why this stops the round rather than being disclosed beside it: the trigger is `RSI(2) < 10`, and an opening
gap of −22% to −37% manufactures that condition. A signal produced by a price-level change the committed
corporate-action table cannot attest is a fabricated observation (§5.4, §6.1, §6.3), and every R-multiple
computed after it would rest on it. Patching around the five names — dropping them, shifting their dates, or
reading a ratio out of the price — would be the silent bridging §6.3 forbids.

### Step 3 — NOT RUN (reported as not run, never as passed)

| Pre-registered item | Status |
|---|---|
| seq 12 execution on 2018-04-02..2023-12-29 | **NOT RUN** — Step 2 did not clear |
| net trade profit factor / gross / liquidated | **NOT RUN** |
| net expectancy in R, max drawdown, Calmar vs NIFTYBEES buy-and-hold | **NOT RUN** |
| matched-count random-entry null (200 draws, seed 101012012) | **NOT RUN** — no strategy arm to match |
| date-block bootstrap CI on net expectancy | **NOT RUN** |
| four-clause decision rule (GO / KILL) | **NOT RUN** — there are no metrics to decide on |
| registry N / N_eval | **11 / 6, unchanged**; no evaluation appended |

`reports/analysis/s101/seq12_vs_null.json` was **not written**: a comparison artifact built without a run
would have to invent its strategy arm.

### Limitations

- The level-step test reads the corpus's own adjusted open against the previous adjusted close, so an
  adjustment applied at the wrong date shows up as a level step here. That is the intended failure, but it
  means the test cannot say whether these five are unrecorded corporate actions or band revisions.
- `ratio_shapes` enumerates ratios the way the corpus reconciliation does (1..12 over 1..24, ±0.5%). A
  non-empty list means a split or bonus of that shape would print exactly this return, not that one happened.
  `14/11` and `9/7` are not plausible share ratios, which is why the disposition rests on the missing record,
  not on the shape.
- The corpus reconciliation publishes moves beyond ±35%, so all eight of these are **absent** from
  `reconciliation.ratio_shaped_detail`; that absence is not an exoneration, and each row publishes
  `below_corpus_reconciliation_threshold: true`.
- 93,463 is a signal-day count, not a trade count: the book is capital-constrained, so how many entries a run
  would have taken is unmeasured.
- The strategy, its feature fields and the runner's `strategy=` seam are tested on synthetic fixtures only.
  They have never priced a session on this corpus, and this round does not claim they would produce a
  computable book.
- This section states a refusal, not a finding. Whether the five level steps are a data defect the auditor
  should register is the auditor's decision (§11.1, §14.8).
## §102 — §100's work order items 1-7: the cash-adjustment test re-derives the count to 4, the window is measured, and the band counters become NOT RUN (Not audited)

**Not audited.** Nothing below is reviewed by an audit section, so nothing below is signed off, verified or
closed by a verdict. The contract is `reports/audit/volume2.md` §100 (the audit of `7c0957e` at `3f7691f`) and
its work order §100.16; the findings `N-196`…`N-202` keep whatever ledger status the auditor last appended, and
this round appends no row to that ledger. The audit report is untouched (§11.1): where a measurement below
disagrees with §100, it is recorded here as new evidence and not as an edit there (§11.2).

Commits in this round, in the order the work order asks for them: `20bb6ff` (item 1's test, stated before any
count was re-derived), `11a366b` (item 5), `468b2e0` (item 7), and the commit carrying this section (items 2, 3,
4, 6 and the re-derivation itself: `reports/analysis/s102/seq12_data_qa.json`). No strategy ran: seq 12's Step 3
does not exist, no session was simulated, no P&L was read, the registry stands at **N = 11, N_eval = 6**, the
2024 fold is untouched (`validation_folds_count = 0`) and the holdout `2025-01-01..2026-11-11` was not read.

### Item 1 (N-196) — the cash-adjustment test was committed before the count, and the count is 4, not 3

The test is stated in `scripts/run_seq12_candidate.py`'s module docstring and in code constants, committed at
`20bb6ff` before the artifact was regenerated: a move is attested by a cash record when the record predicts the
session's close **or** its opening price within `CASH_ADJUSTMENT_TOLERANCE = 0.005` (0.5 % of the previous
close). A dividend predicts `previous_close − dividend_amount`; a rights entitlement predicts the theoretical
ex-rights price `(previous_close·denominator + premium·numerator) / (denominator + numerator)`, with the premium
parsed from the archive's own `description` text. A record that reproduces neither is published as
`UNATTESTED_CASH_MISMATCH` **naming its residuals** rather than being disposed of. Two attacks were run at
`20bb6ff`: emptying the cash-attestation kinds (the pre-fix behaviour) makes probe `N-196` exit 1 naming
HEUBACHIND, and widening the tolerance to 0.20 makes it exit 1 on the tolerance itself.

Re-derived from the corpus, one row at a time, with the archive's own numbers:

| ISIN | Symbol | Ex-date | Previous close | Cash record | Predicted level | Actual close | Close residual | Opening residual | Disposition |
|---|---|---|---|---|---|---|---|---|---|
| `INE492A01029` | HEUBACHIND | 2020-07-16 | 563.30 | ₹140.00 special dividend | **423.30** | **423.55** | **0.0004** | 0.0360 | **ATTESTED_CASH_ADJUSTMENT** |
| `INE116G01013` | VARDHACRLC | 2021-10-28 | 72.35 | ₹25.00 interim dividend | 47.35 | 56.60 | **0.1279** | 0.0504 | UNATTESTED_CASH_MISMATCH |
| `INE006I01046` | ASTRAL | 2021-03-18 | — | none in either archive | — | — | — | — | UNATTESTED_NO_RECORD |
| `INE341R01014` | DTIL | 2021-08-05 | — | none in either archive | — | — | — | — | UNATTESTED_NO_RECORD |
| `INE949H01023` | MANINFRA | 2021-11-17 | — | none in either archive | — | — | — | — | UNATTESTED_NO_RECORD |

**`unattested_level_steps_feeding_a_signal`: 5 → 4.** HEUBACHIND leaves the stop list because a ₹140 dividend
on a 563.30 close predicts 423.30 and the session closed 423.55 — 0.04 % of the previous close.

**VARDHACRLC does not leave it, and this is where the round disagrees with §100.4's arithmetic.** §100.4
anticipates 3, treating VARDHACRLC as corroborating: "the Rs 25 dividend is 117 % of the opening gap". A
dividend ÷ gap ratio is not a level reproduction, and the test this round committed is a level reproduction. At
0.5 % of the previous close the ₹25 dividend predicts 47.35 (the opening price was 51.00, 5.04 % away) and the
session closed 56.60 (12.79 % away) — the stock traded 19.5 % up from the dividend-adjusted level after the
dividend was removed. Reproducing *that* level would need a 25.6× wider tolerance, which is exactly the
"widen until the list empties" failure §100.16 item 1 forbids. So the row is published with its residuals and
stays unattested: the STOP stands on **four** rows, not three. The auditor is invited to contest this with a
measurement (§11.2); the count is not tuned either way.

**The three no-record rows are also the three with no archive coverage at all** (item 6, below): ASTRAL, DTIL and
MANINFRA carry **0** Bronze corporate-action rows for their ISIN across 23 payloads, so their fail-closed
verdict rests on an archive that does not mention them — correct by the §6.3 default, not by exoneration.

### Item 2 (N-197) — the level step is measured over the window, in both directions

The same attestation test is applied to every pair of consecutive sessions inside each continuous segment, with
a ₹5 previous-close floor (at a ₹0.05 prev close the 5-paise tick is a 100 % "gap") and a 10 % threshold in
either direction. A signal whose own 200-session continuous feature window (the exact window `SMA(200)` and
`RSI(2)` at T are computed over) holds one is counted and **excluded from the usable set**; the policy, the
threshold, the floor and the consequence are published in the artifact's `feature_window_policy`. It does not
extend the STOP class, which remains the signal day's −20 % step.

| Measurement (committed artifact) | Value |
|---|---|
| unattested \|opening gap\| ≥ 10 % events, corpus-wide | **6,731** |
| … on a session where the rule fires for that instrument | **128** |
| instruments with at least one such event | **1,668** |
| signals whose own 200-session window holds one — of **93,463** | **21,276** |
| entry signals in a usable feature window | **72,187** |

The scan is the artifact's own EQ resolution (93,463 signals), not §100.5's (100,310), and its attestation now
includes cash records, which removes events rather than adding them; §100.5's 6,612 / 129 / 22,740 are therefore
not reproduced to the digit, and the direction of every figure is unchanged. The published detail list is capped
at 200 rows (`signal_level_steps_in_lookback_truncated: true`); probe `N-197` recomputes 25 of them from the
corpus — window offset, gap magnitude and the 4-dp published gap — rather than trusting the list. Zeroing the
count in the artifact makes the probe exit 1; a fixture whose signal day is clean and whose T−100 bar opens 15 %
lower is refused as an unusable window.

### Item 3 (N-198) — the artifact now says it gates nothing, and the statement is the scan

`gated_by.consumers` is computed at build time by scanning `scripts/*.py` and `src/**/*.py` for the artifact's
name, excluding the producer and the audit probe (both named in `excluded_from_the_scan`). It is empty, so the
published statement is "no committed code outside this producer and the audit probe reads this artifact, so its
STOP is a record of a refusal and not a gate: no execution path exists for it to refuse". Probe `N-198`
recomputes the scan, requires the published list to equal it, and requires no committed code outside `tests/` to
construct `MeanReversionSwingStrategy`. Adding a one-line consumer under `scripts/` makes it exit 1 ("the
artifact publishes consumers [] and the scan finds ['scripts/_tmp_seq12_consumer.py']"). **The STOP still gates
no code path; the difference is that the artifact now says so where a reader looks.**

### Item 4 (N-199) — the three band counters are NOT RUN; the partition is BLOCKED, not synthesised

Implemented: `at_lower_circuit`, `at_upper_circuit` and `banded_but_not_at_a_limit` are `NOT RUN` exactly while
`data/silver/price_bands` holds no file, and integers exactly when it does (`band_counter(value, bands_recorded)`,
tested both ways). The artifact publishes `price_band_partition: {files: 0, populated: false}` beside them and
`not_run.exit_freeze_round_trip`: *"NOT RUN — data/silver/price_bands holds 0 files, so no session carries a
band and a lower-freeze exit delay cannot be measured"*. Probe `N-199` is the biconditional, so a populated
partition forces the counters to become measurements and re-measurement.

**Blocked, and reported rather than patched around:** the round-trip exit-freeze case — the case §13.2 says a
2-to-21-session hold cannot ignore — remains **NOT RUN**. No sourced band payload exists in this repository:
`data/silver/price_bands` holds 0 files and `data/raw/price_bands` does not exist at all, so no Bronze payload is
waiting to be promoted. Deriving a band from the bar it is meant to test would make the counter a restatement of
its own input. **What is needed:** a sourced per-session NSE price-band archive for `2018-04-01..2023-12-31`
(the security-wise price-band file, or the daily band circulars) dropped under `data/raw/price_bands/` as
byte-exact payloads with retrieval metadata, plus the Silver ingest that promotes it one partition per session.

### Item 5 (N-201) — clause (d) names a continuous benchmark; the corpus boundary is *not* repaired

Taken the clause half of §100.16 item 5, not the corpus half, and said why. `decision_rule.all_of[3]` now
carries a `benchmark` block naming `scripts/compare_seq10_baselines.py:buy_and_hold_arm`, its within-ISIN
construction, the two unmeasured sessions (2019-12-19 level break, 2019-12-20 ISIN transition) and the refusal.
`buy_and_hold_arm` now calls `refuse_unattested_level_break(returns, 0.5)`, so a retained one-session step of
50 % or more exits by name instead of being carried into a Calmar. Attacks: the fixture list refuses naming
`2019-12-19`; and with `LEVEL_BREAK_THRESHOLD` raised so the exclusion stops firing, the real arm refuses naming
`2019-12-19` — the exclusion is no longer the only thing between the corpus and a decision clause.

The corpus was **not** changed. A 1:10 re-denomination for `INF732E01011` is not attested in the committed table
(the row there says "share ratio not established"), Bronze holds no NIFTYBEES corporate-action row, and
back-adjusting would move the corpus fingerprint and every artifact that cites it — including the seq-10 pair
that may not be re-run this round. The residual is named: the corpus bar at 2019-12-19 is still unadjusted and
`reconciliation.ratio_shaped_detail` still omits that boundary from a 699-row list, so that list is not a
census. Nothing in this round moves a fingerprint: the artifact's `corpus.sha256` is
`0fdc728a81acbb396f626fb54e4f28862c93cec836db3b502814f850a056a984`, the same one §101 published;
`compare_seq10_baselines.py --check` reproduces its artifact byte for byte with the refusal in place, and
`verify_seq10_certificate.py` exits 0 — the seq-10 and seq-11 artifacts are untouched.

### Item 6 (N-200) — the no-record verdict travels with the archive's coverage

| Measurement | Value |
|---|---|
| Bronze corporate-action payloads / rows | 23 / 13,568 |
| Bronze distinct ISINs | **2,200** |
| corpus instruments scanned | **2,735** |
| instruments with no Bronze corporate-action record of any kind | **910 (33.3 %)** |
| unattested stop rows whose instrument the archive never mentions | **INE006I01046, INE341R01014, INE949H01023** |

Each published drop row also carries `bronze_records_for_isin`, so "no record" is readable against how much
archive exists for that instrument (HEUBACHIND 9, VARDHACRLC 7, the three no-record rows 0). Probe `N-200`
recomputes the coverage and fails if the published figures or the uncovered-stop list disagree (forging 2,735
covered ISINs makes it exit 1).

### Item 7 (N-202) — the interaction is pinned in the pre-registration

`configs/trial_012_candidate.yaml` now carries `strategy.entry_exit_interaction:
"EXIT_SUPPRESSES_ENTRY_ON_THE_SAME_SESSION"`, committed at `468b2e0` as an amendment citing `f2133ef`, before
any execution. No rule, threshold, window, clause or cost field moved; the file's sha256 changed (it is
published in the new artifact's `pre_registration` block) and the §101 parenthetical still quotes the original
one, which is history and is left unedited. Probe `N-202` reads the pin and then drives the strategy on a
session satisfying both predicates (close 110 > SMA(5) 108, > SMA(200) 90, RSI(2) 4 < 10): it must emit the
exit alone, with a non-vacuous entry control. Removing the pin, and removing the `continue` that suppresses the
entry, each make the probe exit 1.

### The re-derived artifact, and what it restates

`reports/analysis/s102/seq12_data_qa.json` (77,387 B) supersedes the §101 artifact, which is **left unedited**
(§10.1, and the §97.5 / N-194 precedent). It is pinned by `restates.sha256` and carries every field that moved
as a `published_there` / `published_here` pair: `status` (STOP → STOP), `unattested_level_steps_feeding_a_signal`
(5 → 4), `stop_reason`, `below_minus_20pct_level_step_at_open` (5 → 5) and `blocked_by_locked_session` (three
zeros → three `NOT RUN`). `python scripts/run_seq12_candidate.py --check` recomputes it and compares the bytes:
**exit 0, 129.8 s**, QA status STOP. The `stop_reason` now reads "…with no corporate action (share ratio or cash
amount) attested on that date; 4 of them are ratio-shaped".

### What is not done, and the residuals

- **N-199's populate half is BLOCKED** on a sourced NSE price-band archive (above). The exit-freeze round trip is
  therefore **NOT RUN**, and no swing verdict may be computed before it is measured.
- **N-201's corpus half is not taken**: the `INF732E01011` 2019-12-19 bar is still unadjusted in the validated
  layer, by the reason committed above. Clause (d) is evaluable against a continuous benchmark; the corpus is
  not continuous, and `ratio_shaped_detail` is still not a census.
- **N-196's number differs from §100.4's** (4 against 3) on VARDHACRLC, measured above; the row is not attested
  by the recorded tolerance and is not retuned to match a verdict.
- The published lookback detail is truncated at 200 of 21,276 signals; the counts are complete.
- No execution, so nothing about trade impact is measured: how much the 128 signal-day events or the 21,276
  in-window signals would change a book remains unmeasured.
- `N-195` (carried, §99.10 item 1) was re-measured, not re-fixed: the seq-10 status row carries
  `1.058319814…` / `1.062288461…`, the artifact's own digits, and probe `N-195` exits 0.

### Gate state at this commit

- `pytest`: **610 passed** in the parallel invocation (65.22 s) + **1 passed** isolated (2.03 s) = **611 of 611
  collected**, 0 skipped, 0 xfailed. The new files are `tests/unit/test_phase3b2_audit_s102_items.py` (7 passed)
  and the expanded `tests/unit/test_phase3b2_seq12_data_qa.py` (11 passed).
- `scripts/verify_*.py`: **10 of 10 exit 0** (`verify_audit_findings.py` 215.15 s, 54 probes passed).
- Gate verdict line: `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)`, exit 0, run with
  `--force-full` on this commit's tree; the green row is recorded by the commit that follows it (N-160).
- Protected paths: `reports/audit/**`, `AGENTS.md`, `configs/go_no_go_criteria.yaml` and `data/trials/**` are
  untouched; no fold or holdout session was read; the registry is unchanged at N = 11, N_eval = 6.
## §103 — §101's items 1, 2, 5 and 6 executed for N-203, N-204 and the two unpublished boundaries; items 3 and 4's corpus half not taken (Not audited)

This log reviews commit `46a99ec` under audit **§101** (`reports/audit/volume2.md`, tag
`feat-s102-46a99ec`) and executes four of its seven ordered items. **The work is not audited**: no finding is
marked CLOSED here, no verdict word is claimed, and the ledger stays as §101 left it — `N-150`, `N-199`,
`N-201`, `N-203`, `N-204` OPEN.

### Item 1 (N-203) — the published digest is the stored bytes' digest, and the gate runs the check

Measured on the tree as `46a99ec` left it, before any edit: `seq10_artifact_sha256` was `4a729dbc…`, the
sha256 of the trial_010 verdict with LF re-rendered as CRLF, while `git cat-file -p HEAD:` of that path
hashes `75571da3…`. `probe N-203` failed on the field, and now also fails if the check leaves discovery.

`compare_seq10_baselines.py` hashed the working copy raw. It now has `_sha256` for tracked **text** (CRLF
normalised to LF — the form `.gitattributes` stores) and `_sha256_bytes` for a binary payload. The artifact is
regenerated: `seq10_artifact_sha256` is `75571da3…` with a `seq10_artifact_sha256_of` field naming the byte
sequence. `python scripts/compare_seq10_baselines.py --check` exits 0 here and in the clone below.

The check is on the gate's discovery path: `scripts/verify_seq10_baseline_comparison.py` is a thin hook that
calls `compare_seq10_baselines.main(["--check"])` and adds no assertion of its own, and it is named in
`EXPECTED_VERIFICATION_SCRIPTS`, which moves the discovered sweep from 10 to 11. The three unit tests that
pinned the sweep at 10 are updated to 11 (they still assert exact equality with the committed inventory).

### Item 2 (N-204) — one dataset, one fingerprint

`run_seq12_candidate._digest` applied `read_bytes().replace(b"\r\n", b"\n")` to every path it was given, so
`corpus.sha256` hashed a mutated gzip stream (`0fdc728a…`). It is now `_digest_text` (config, superseded
artifact) and `_digest_bytes` (corpus). The regenerated artifact publishes `ea0b65a3…` / 75,390,706 B — the
manifest's current row and the s100 artifact's `dataset_sha256` — with a `sha256_of` field stating that this
is the file's stored bytes, unnormalised. `probe N-204` asserts the field equals `sha256(file bytes)` and
equals the manifest row; it failed before the change and passes after.

### Item 5 — the two silent boundaries are published

The artifact now carries `signals_without_a_next_session` (86), `..._in_eq_series` (62) and
`entry_signals_including_the_final_session` (93,525 = 93,463 + 62), so §101.5's "62 signals on the final
session" and the 93,525 that explained the first attempt are reproducible from the artifact. The finals are
counted **before** the series filter, so `signals_in_non_eq_series` stays 15,441 and no previously published
count moves. `signal_level_steps_in_lookback_detail_distinct_instruments` is 9 against 1,668 instruments that
carry an event, with a `..._detail_scope` field saying the list is a prefix in insertion order, not a sample.

### Item 6 — the RIGHTS branch's status, computed rather than asserted

`rights_terp_branch` publishes 4 `RIGHTS` records in the committed table and 0 sitting on a candidate level
step, beside the stated limitation: the TERP path has never fired, its premium is a regex over prose, and its
first use will attest a price level against an `UNATTESTED_` record. No sourced rights record was supplied, so
the branch is neither exercised nor retired.

### Item 4 (N-201) — the corpus half is not taken, and the reason is a pin

The corpus header is covered by the manifest and the manifest by `expected_manifest_fingerprint` in
`configs/go_no_go_criteria.yaml`. A corpus restatement therefore appends a manifest row, moves `MAN-FPR-V1`
and needs a criteria re-seal — which this round may not perform. So the boundary stays excluded, **no corpus
byte changed**, and the correction travels with the artifact that reads the corpus:
`corpus_reconciliation.detail_is_a_census` is `false` with the three filters named (±35 % threshold, ±0.5 %
ratio band, gap-straddling pairs excluded), and `unattested_unit_break` names `INF732E01011` 2019-12-19, its
ratio, its stamp and `stamp_scope = SERIES_POLICY_NOT_A_PER_BAR_ATTESTATION`. `probe N-201` now also fails if
that published claim stops matching the corpus. **The corpus-header form §101.12 item 4 asked for is not
delivered**; this is the artifact-surface mark, not the header mark. §101.4's other half — the two dropped
sessions' real return (−0.042 %, +0.108 %) stated in clause (d) — also remains untaken, because the clause
lives in `configs/trial_012_candidate.yaml`, which this round may not edit.

Measured while doing it: §101.4 prints the boundary ratio as 0.100731; the artifact recomputes
130.20 / 1292.54 = 0.100732 at 6 dp, round-half-up. A last-digit difference, not a disagreement about the
boundary. The artifact's own scope note measures the boundary as **not** in `ratio_shaped_detail` — it is
counted in `no_ratio_match` (74 rows) because 0.100732 is outside the ±0.5 % band around 0.1.

### Item 3 (N-199) — still BLOCKED

No sourced per-session NSE band archive was supplied. `data/silver/price_bands` stays empty, the three
categorical counters stay `NOT RUN`, the exit-freeze round trip stays NOT RUN, and nothing was synthesised
from prices.

### What moved, and what did not

`reports/analysis/s100/seq10_baseline_comparison.json` and `reports/analysis/s102/seq12_data_qa.json` are
regenerated **by their own producers** (`--check` exit 0 here and in a clean clone); the s102 artifact is a
restatement in place whose moved fields are the ones named above, and the s101 artifact is untouched. Scripts,
three verifier-count pins and one new verifier file also changed. **No corpus byte, content fingerprint,
manifest row, criteria value, trial-registry row, fold or holdout session moved**: corpus 75,390,706 B /
`ea0b65a3…`, `DATA-CTNT-V2-cb4832c0…`, `CRIT-FPR-V1-535e47f5…`, `N = 11` / `N_eval = 6`,
`validation_folds_count = 0`, holdout `2025-01-01..2026-11-11` unread.

### Gate state at this commit

- `scripts/verify_*.py`: **11 of 11 exit 0** in the pre-commit `--force-full` run after the pin update
  (`verify_audit_findings.py` 221.94 s / 56 probes, `verify_seq10_baseline_comparison.py` 25.20 s).
- The first pre-commit run **failed** on three tests that pinned the sweep at 10; the pin update is the fix
  and the failure is recorded here rather than smoothed over.
- `pytest`: **610 passed** in the gate's parallel invocation (66.90 s) + **1 passed** isolated (2.41 s) =
  **611 of 611 collected**, 0 skipped, 0 xfailed.
- The post-commit verdict line and the green row: see the note below — the row is **not** recorded, because
  the working tree carries three pre-existing source-path changes that this round may not commit
  (`AGENTS.md` modified, `.agents/skills/research-audit/SKILL.md` and `.agents/skills/research-round/SKILL.md`
  untracked). The gate refuses to certify a tree whose working copy it did not measure (§80.3), and that is
  the correct outcome rather than a usable one.
- Nothing here is signed off. The next round is the auditor's.
