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

---

## 10. Market Data Ingestion, Storage & Reproducibility

1. **Immutability Over Convenience**:
   - Bronze payloads are byte-exact as retrieved and are never edited. Silver partitions are append-only, one per trading session.
   - A correction is a new append carrying an effective date and a restatement reference. `UPDATE`/`DELETE` against historical prices, membership, or surveillance data is prohibited.
2. **Files Are the System of Record; Databases Are Derived**:
   - Parquet files plus their SHA-256 hashes constitute the dataset. Any SQL engine over them (DuckDB) is a rebuildable view and must be deletable without changing a single fingerprint.
   - A mutable relational database is never the authority for research history. It may serve the live paper-trading service only, where concurrent writers and row-level order/fill state are the actual requirement.
   - Analytical dependencies belong in optional extras; the core package stays stdlib-pure and no research module imports the query engine.
3. **Layer Separation**:
   - Raw → typed/validated → derived. Corporate-action adjustment, universe schedules, and features exist only in the derived layer, so "what was observable at $T$" is always recoverable.
   - Storing split/bonus-adjusted prices in the validated layer is prohibited; adjustments are applied forward from an explicit corporate-action table.
4. **Identity Is ISIN, Never Symbol**:
   - Symbols are reused and reassigned. Rows are keyed by ISIN with symbol and series as effective-dated attributes.
   - An ISIN transition is an explicit event with a verified effective date; histories are never stitched across differing ISINs. Never partition a dataset by symbol.
5. **Time-Varying Facts Are Interval Tables**:
   - Index membership, ASM/GSM/ESM stage, F&O ban, and price band are stored as half-open intervals `[effective_from, effective_to)` and joined as-of date $T$.
   - They are never stored as a current snapshot and never reconstructed by back-solving from the present constituent list.
6. **Exactness Across the Storage Boundary**:
   - Prices, volumes, turnover, and quantities persist as `DECIMAL` (or integer paise) and must read back as `Decimal`; a cast to `float` at the storage boundary is prohibited.
7. **Ingestion Runs Are Auditable**:
   - Every retrieval records source URL, retrieval timestamp, byte count, and SHA-256 in a manifest.
   - A run that fails part-way leaves no partially promoted Silver partition; promotion is atomic.
8. **No Gating on Unsimulatable History**:
   - A GO/NO-GO verdict may only be computed on sessions in which every required input exists: authoritative calendar, verified security identity, and surveillance state.
   - Sessions before the surveillance frameworks existed (GSM effective 14 Mar 2017, ASM effective 26 Mar 2018) are warm-up only; metrics computed on them are `NOT RUN` for gating.
   - A shorter honest evaluation window is preferred to a longer one resting on fabricated or absent inputs. The binding evaluation window for this project starts **2018-04-01**; moving it earlier requires sourced surveillance history, not prose.

---

## 11. Auditor / Implementer Separation

1. **The audit report is the auditor's, and append-only**:
   - `reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md` is written by the auditor alone. An implementation agent may read it and must never edit, reword, reformat, delete, or commit a change to it — including staging an audit section that already sits uncommitted in the working tree. If an audit append is pending, leave it pending; commit only your own files.
2. **Disagreements are new evidence, never edits**:
   - To contest a finding, commit a separate note that cites the finding ID and provides the measurement contradicting it. A finding is never deleted, softened, or re-scoped by the agent it names.
3. **A status claim must cite the verdict that grants it**:
   - `CURRENT_STAGE_OF_WORK.md` may describe work as signed off, verified, closed, or complete only where the cited audit section uses that word for that item, and the sentence must name the audit section (`§N`) and the commit SHA it applies to.
   - Quote the verdict or cite it; never paraphrase upward. "Implemented" → "implemented & verified" is a false claim under §9.1.
   - With no citation, write what was measured and what was not: "implemented; gates measured on a synthetic fixture; not audited".
4. **Shared document mechanics**:
   - The implementer owns the phase sections it writes. The auditor owns the audit clauses in the phase row and may correct any claim contradicted by a delivered verdict; such a correction is the auditor's edit and must not be reverted by the implementer.
   - Implementation status notes added to `docs/` follow rule 3 too: name the audit section and SHA the note reflects.
   - The audit report is a citation target, so committed history is a citation target too (§12.1).

---

## 12. Repository Discipline and Continuous Verification

This project has one branch (`main`), no CI history, and documents that cite commit SHAs. Those facts constrain how work may be delivered.

1. **Committed history is append-only.** Never `--amend`, rebase, squash, or force-push a commit that is already on `main`. Every audit section (§N) and every status claim cites a SHA; rewriting history silently invalidates citations that, being append-only, cannot be corrected. A bad commit is fixed by a commit that follows it, never by erasing it.
2. **Sign-offs are tagged.** A GO verdict is tagged at the commit it names (`waveN-signed-off-<sha8>`). Tags survive what prose citations do not.
3. **CI is the computation behind §9.1.** The gate runs, offline, on every push to `main`: the full test suite; every `scripts/verify_*.py` with its exit status preserved and required zero; and the §11.1 check that the audit report gained no removed line. A verdict that cannot be reproduced by the gate is not a verdict.
4. **A gate is not passed by weakening it.** No `skip`, `xfail`, `pytest.ini` exclusion, or widened tolerance to reach green. No coverage-percentage threshold as a merge gate — it measures lines executed, not invariants upheld (§9.1). If a check must be relaxed, that is a documented decision in the same commit, naming what is now unverified.
5. **Offline is a test result.** CI has no network. A test that needs the live NSE archive is a fixture-extraction task (cached bytes committed to Bronze), not a test.
6. **CI never publishes, never projects, never touches holdout.** It computes and fails. Anything that writes outside the working tree is human-invoked.
7. **Commits carry no AI or co-author attribution trailers.** No `Co-Authored-By`, no "Generated with" line, no co-author identity of any kind, unless the maintainer asks for it on a specific commit. A trailer adds a name to the contributor list, and that is not a decision an agent makes.

---

## 13. Strategy Scope: Delivery Swing

Strategy scope is a researched decision, not a default. The current scope is **delivery swing trading on NSE `EQ`**: multi-session holds, no intraday squaring-off, no F&O, no trade-to-trade.

1. **Universe and series.** Entry is permitted in `EQ` only. `BE`/`BZ` bars remain valid price observations for continuity and feature windows (§6.2) but are never entry-eligible (§5.1).
2. **Holding-period realism.** A position held across sessions must survive what a one-day position can ignore:
   - Corporate actions and dividends that fall *inside* the holding window are applied to the open position, not only to the historical series. An ex-dividend gap on a held position is a cash inflow, never a loss. A corporate-action table without dividend rows makes every held-position ledger wrong.
   - Surveillance escalation (ASM/GSM/ESM) during a hold is an exit constraint, not an entry filter (§5.2).
   - A lower-circuit freeze is an unbounded exit delay, not a one-session cost (§5.3). A strategy whose expectancy depends on exiting into a frozen bid is structurally flawed.
3. **Attribution is per trade, not per day.** Costs are evaluated per completed round trip against the expected holding-period edge (§7.2). Turnover-based cost minimisation is not an objective.
4. **Breadth over frequency.** With multi-session holds, independent observations come from cross-sectional breadth (positions per rebalance), not from trade frequency. Prefer ranked baskets over single-name timing; both the multiple-testing budget (§8.2) and the observation count are measured in that unit.
5. **Swing is configuration, not a second engine.** Holding horizon, universe filter, exit rule, and cost schedule are parameters of the single authoritative engine (§7.4). A `swing_simulator` or a forked fill/cost path is a §7.4 violation regardless of intent.
6. **Scope changes are recorded.** Moving to intraday, F&O, or `BE` entry requires a committed decision stating the evidence that motivated it. It is never introduced as an experiment inside a strategy file.

---

## 14. Auditor Role and Review Cadence

A review round produces three things, in this order: a **verdict** on the commit under review, the **evidence** that produced it, and an **ordered work order** for the next round. A round that ends with a finding but no instruction to the implementer is incomplete.

1. **Audit a commit, never a working tree.** A verdict cites a SHA. Uncommitted work may be reviewed as a pre-commit check, but it must be labelled as such and it can close nothing.
2. **One round is one numbered section**, appended to the audit report (§11.1), containing four parts:
   - the baseline re-measured at that SHA: suite count with skip/xfail count, every `scripts/verify_*.py` exit status, and the gate's own verdict line;
   - per-finding status — `CLOSED`, `PARTIAL`, `OPEN` — each with the measurement that decided it;
   - the verdict for every phase the commit touches, with residuals named rather than implied;
   - the work order: numbered, ordered by what it unblocks, each item naming the probe that must fail closed before the item is closed, and the phase in `CURRENT_STAGE_OF_WORK.md` it serves.
3. **Reproduce, don't read.** Re-measure every load-bearing claim with an attack the finding implies — reseal a self-declared digest before testing a pin, delete the payload before testing substantiation, remove the pinned key before testing fail-closed. A check that passes on the unmodified tree is not a check.
4. **Watch for the additive fix.** The recurring failure in this repository is a remedy that adds a guarded path beside the unguarded one: a new anchored loader while the old one stays exported and called, a new criteria pin while the code default remains, a new set check beside the count check. When a finding says "a consumer cannot", the acceptance is measured at every existing consumer, not at the new function.
5. **Never move the goalposts.** Conditions named in a previous section are the contract for the next round. If they are met, the verdict changes even if better conditions can be imagined; if they were explicitly allowed to trail, they are carried as named residuals, not promoted to blockers.
6. **The implementer's documents are theirs.** `CURRENT_STAGE_OF_WORK.md` is not edited by the auditor. Disagreement goes in a separate note citing the finding ID and the measurement contradicting it (§11.2).
7. **Say what would falsify the verdict.** End each verdict with the observation that would make it wrong, so the next round knows what to measure rather than what to believe.
8. **Instructions to the implementer live in the audit report**, not in chat, not in this file. The report is the citation target; anything said only in a conversation is lost with it.
