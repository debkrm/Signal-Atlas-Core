# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes and enforce quantitative research integrity. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

---

# Standing Rules for Indian Quantitative Research, Backtesting & Market Data Integrity

As senior quantitative researchers building Signal Atlas for production-grade, well-researched trade signals in Indian financial markets (NSE / BSE), you and all agents working on this project must strictly comply with the following non-negotiable principles.

---

## 5. Indian Market Structure & Regulatory Realism (SEBI / NSE / BSE)

1. **Exchange Series & Settlement Separation (`EQ` vs `BE` vs `SM` vs `BZ`)**:
   - Rolling equity (`EQ`) permits intraday netting, standard margin, and normal settlement.
   - Trade-to-Trade (`BE` / `BZ`) mandates 100% upfront delivery margin, gross trade-for-trade settlement (zero intraday squaring off), and rigid price bands (typically 5% or 2%).
   - Never assume liquidity, execution fills, or margin treatment in `BE` are equivalent to `EQ`.
   - Never automatically discard `BE` price bars from historical continuity when the security traded, but never assume a strategy designed for `EQ` rolling settlement can enter or execute in a `BE` instrument without explicit strategy authorization.
2. **Surveillance Frameworks (ASM / GSM / ESM)**:
   - SEBI and NSE impose surveillance stages (Long-Term ASM, Short-Term ASM, Graded Surveillance Measure GSM, Enhanced Surveillance Measure ESM).
   - Scrips under advanced surveillance stages face 100% margin requirements, lower circuit bands, and in GSM Stage 2+, trading is restricted to once a week with additional surveillance deposits.
   - Simulators must never model fills or assume unconstrained liquidity in surveillance-restricted securities.
3. **Circuit Filters & Upper/Lower Freeze Fills**:
   - Never simulate a BUY fill at the High if the High equals the Upper Circuit limit (ask depth is zero; buyers are rationed).
   - Never simulate a SELL or stop-loss fill at the Low if the Low equals the Lower Circuit limit (bid depth is zero; sellers are trapped).
   - Any backtest assuming instant exit during a lower freeze is structurally flawed and rejected.
4. **Corporate Actions & Security Identity (ISINs)**:
   - Splits, Bonuses, and Rights: Back-adjust historical series using exact corporate action ratios applied strictly prior to the ex-date. Never leak post-split unadjusted price levels backward.
   - ISIN Transitions: Never stitch price histories across differing ISINs without verified corporate action documentation (e.g. stock split or restructuring). An ISIN transition must be explicitly modeled with its verified effective date.
   - Mergers & Delistings: Prune merged or delisted companies (e.g. HDFC into HDFC Bank, Mindtree into LTIMindtree) on their exact effective delisting date. Never silently carry delisted members forward or bridge across missing post-delisting dates.

---

## 6. Point-in-Time Data Integrity & Fail-Closed Invariants

1. **Point-in-Time Universe Selection (Zero Survivorship Bias)**:
   - Universe schedules (Nifty 50, Nifty 500, liquid momentum filters) must be reconstructed strictly as of date $T$ using information available *before* the market open on date $T$.
   - Never select universe constituents based on end-of-sample volume, market capitalization, or survival.
2. **Date-Aware Continuity vs. Strategy Eligibility**:
   - A valid exchange price observation and permission to trade that security are two distinct concepts.
   - A series transition (e.g. `EQ` to `BE`) does NOT break price-history continuity if valid observations exist for both sessions under the same security identity.
   - Rolling feature windows (EMA, ATR) do not restart merely because a series changed, but trading eligibility policies may independently reject new trade entry.
3. **Fail-Closed Missing-Session Invariants (Zero Silent Bridging)**:
   - Every instrument's price sequence must be verified against an explicit, authoritative NSE trading calendar.
   - A sequence of $N$ available bars must never be assumed to represent $N$ consecutive trading sessions if expected calendar dates intervened.
   - Zero silent data fabrication:
     * Zero forward-filling of prices.
     * Zero back-filling or linear interpolation of missing OHLC.
     * Zero fabrication of zero prices ($0.00$) or masking missing records with floating-point `NaN`.
   - Missing sessions without verified exchange circular evidence must trigger `PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD` and fail closed. Feature engines must partition continuous subsegments and refuse to compute lookbacks across unexplained gaps.
4. **Exact Decimal Accounting**:
   - All financial quantities—prices, order sizes, fees, taxes, slippage, cash ledger, equity, and PnL—must be represented using exact `Decimal` arithmetic.
   - Binary floating-point (`float`) representation in trade accounting, ledger records, or PnL is strictly prohibited due to compounding rounding distortion.
5. **Data Provenance & Fingerprint Verification**:
   - Every dataset and universe schedule must have a deterministic, versioned logical content fingerprint.
   - Missing or unverified source metadata must remain explicitly `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`. Never promote unverified datasets to `VERIFIED` without verified source certificates or raw archive audit proofs.

---

## 7. Backtest Realism, Statutory Transaction Costs & Execution Invariants

1. **Next-Session Execution & Zero Lookahead**:
   - Signals calculated at session $T$ close (using data up to $T$ close) execute at earliest on session $T+1$ open (or TWAP/VWAP of $T+1$) with realistic execution latency.
   - Never calculate a signal at $T$ close and fill at $T$ close.
2. **Indian Statutory & Regulatory Cost Schedule (SEBI / NSE / Stamp Duty / GST / STT)**:
   - All backtests and strategy evaluations must compute the complete, statutory Indian transaction cost schedule:
     * **STT (Securities Transaction Tax)**: 0.1% on delivery (both buy and sell) or 0.025% on intraday equity sell.
     * **Exchange Transaction Charges**: NSE cash equity turnover charges (typically ~0.00325% to 0.00345%).
     * **SEBI Turnover Charges**: ₹10 per crore (0.0001%).
     * **Stamp Duty**: Indian Stamp Act schedule (0.015% on delivery buy, 0.003% on intraday buy).
     * **GST**: 18% applied on (brokerage + exchange charges + SEBI charges).
     * **Brokerage**: Fixed per-order (e.g. ₹20 per executed order) or basis points.
     * **Investor Protection Fund (IPFT)** charges.
   - Flat fees or zero transaction costs are strictly prohibited in any evaluation submitted for review.
3. **Liquidity Constraints & Realistic Slippage**:
   - Slippage must be modeled as a function of bid-ask spread and market impact:
     $$\text{Slippage} \ge \frac{\text{Spread}}{2} + \kappa \cdot \left(\frac{\text{Order Value}}{\text{Average Daily Turnover}}\right)^\alpha$$
   - Volume participation cap: An order must not exceed 2.5% to 5.0% of the session's actual traded volume (`TOTTRDQTY`).
4. **Single Authoritative Engine**:
   - There is exactly ONE execution, cost, and accounting engine.
   - No shadow simulator, ad-hoc spreadsheet vectorization, or duplicate fill logic.
   - Production paper trading and backtesting must share identical fill and cost calculations.

---

## 8. Anti-Overfitting, Holdout Containment & Multi-Hypothesis Testing

1. **Holdout Containment (`HOLDOUT_UNLOCK`)**:
   - Historical datasets must maintain strict separation between:
     * Training / In-Sample (IS): Exploration, parameter estimation, feature extraction.
     * Validation / Calibration: Walk-forward tuning, threshold calibration.
     * Test / Out-of-Sample (OOS) Holdout: Strictly sealed confirmatory evaluation.
   - Agents must NEVER access, inspect, or load holdout partitions.
   - `HOLDOUT_UNLOCK` is strictly human-created. Any agent attempting to create, mock, or bypass `HOLDOUT_UNLOCK` is strictly violating safety protocols.
2. **Multi-Hypothesis & Multi-Trial Accountability**:
   - An append-only trial registry must record every parameter sweep, indicator alteration, and rule trial with its explicit rationale.
   - Never present the best-performing trial without reporting the total number of tested variations ($N$).
   - Compute the Deflated Sharpe Ratio (DSR) or Haircut Sharpe ratio to adjust for trial count, variance of trials, and skewness/kurtosis of returns.
3. **Walk-Forward Stability Over Point In Time**:
   - A strategy is considered viable only if it displays parameter stability across rolling/anchored walk-forward windows.
   - Performance that collapses outside a narrow parameter spike indicates curve-fitting, not alpha.

---

## 9. Quantitative Reporting & Auditability Protocols

1. **Verdicts are Computed, Never Typed**:
   - Every PASS, FAIL, GO, NO-GO, status label, and summary metric in a report must be generated from computed values or automated assertions.
   - Hardcoded qualitative adjectives ("HEALTHY", "OPTIMAL", "ROBUST", "CONTROLLED") are strictly prohibited.
2. **Criteria Live in a Committed File**:
   - Go/No-Go criteria live in committed configuration files (`configs/go_no_go_criteria.yaml`).
   - Thresholds must never be adjusted post-hoc after inspecting backtest results.
3. **Fail-Closed Reporting**:
   - If a metric or test was not run, the report explicitly states "NOT RUN".
   - A criterion is PASS only if backed by printed computation, reproducible test output, or mathematical unit test proof.
