# Signal Atlas Core — Quantitative Research Engine & Trading Infrastructure Architecture

## 1. Executive Summary & Core Mission

**Signal Atlas Core** (`signal-core`) is an institutional-grade, deterministic, offline-first quantitative research and systematic trading infrastructure designed specifically for Indian financial markets (NSE / BSE).

The mission of Signal Atlas Core is to provide a mathematically rigorous, auditable foundation for generating and evaluating well-researched trade signals. The architecture explicitly eliminates the subtle vulnerabilities that plague retail and legacy quantitative backtests: survivorship bias, lookahead leakage, floating-point rounding distortion, silent price bridging, and regulatory disconnects between backtest assumptions and real-world Indian exchange settlement.

Signal Atlas Core was initiated as a clean, independent rebuild to establish immutable data contracts, single-engine execution realism, and statutory compliance before any trading strategy is evaluated.

---

## 2. Indian Market Structure Realism (SEBI / NSE / BSE)

Quantitative strategies operating in Indian financial markets face unique structural and regulatory mechanisms. Signal Atlas Core embeds these constraints directly into its data contracts and execution engine:

### A. Exchange Series & Settlement Disconnect (`EQ` vs `BE` vs `SM` vs `BZ`)
- **Rolling Equity (`EQ`)**: Standard rolling cash equity settlement ($T+1$ rolling cycle). Permits intraday squaring-off, intraday margin netting, and standard leverage.
- **Trade-to-Trade (`BE` / `BZ`)**: Mandatory 100% upfront delivery margin, gross trade-for-trade settlement (zero intraday netting or squaring-off allowed), and narrow price bands (typically 5% or 2%).
- **Small & Medium Enterprise (`SM`)**: Specialized lot-size and liquidity dynamics.
- **Surveillance Frameworks (ASM / GSM / ESM)**: SEBI and exchange surveillance stages impose 100% margin requirements, lower circuit bands, and in GSM Stage 2+, trading restricted to once a week.
- **Core Invariant**: A strategy designed for rolling `EQ` can never assume that order fills, liquidity, or margin requirements in `BE` or surveillance scrips are equivalent. The engine decouples historical price observations from strategy trading eligibility.

### B. Price Bands & Circuit Freeze Invariants
- **Upper Circuit Locks**: If a session's High equals the Upper Circuit limit, ask-side liquidity is zero (buyers are rationed). The simulation engine prohibits BUY fills at the High.
- **Lower Circuit Freezes**: If a session's Low equals the Lower Circuit limit, bid-side liquidity is zero (sellers are trapped). The simulation engine prohibits SELL or stop-loss fills at the Low.
- Any backtest assuming instant exit during a lower circuit freeze is rejected as structurally flawed.

### C. Statutory Transaction Costs & Indian Taxation Schedule
Backtests must compute the exact statutory transaction costs per trade; zero-cost or flat-fee approximations are strictly forbidden:
- **Securities Transaction Tax (STT)**: 0.1% on delivery (both buy and sell) or 0.025% on intraday equity sell.
- **Exchange Turnover Charges**: NSE cash equity charges (~0.00325% to 0.00345%).
- **SEBI Turnover Fees**: ₹10 per crore (0.0001%).
- **Stamp Duty**: Indian Stamp Act schedule (0.015% on delivery buy, 0.003% on intraday buy).
- **Goods & Services Tax (GST)**: 18% applied on (brokerage + exchange charges + SEBI charges).
- **Investor Protection Fund (IPFT)** charges.

### D. Liquidity Constraints & Realistic Indian Equities Slippage
- Slippage is modeled as an empirical function of bid-ask spread and market impact:
  $$\text{Slippage} \ge \frac{\text{Spread}}{2} + \kappa \cdot \left(\frac{\text{Order Value}}{\text{Average Daily Turnover}}\right)^\alpha$$
- **Volume Participation Cap**: Simulated trade execution is strictly capped at 2.5% to 5.0% of the session's actual traded volume (`TOTTRDQTY`).

---

## 3. Core Architectural Pillars

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIGNAL ATLAS CORE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. RAW OBSERVATION LAYER (Immutable exchange Bhavcopy OHLCV, ISIN, Series) │
│       │                                                                     │
│       ├──► 2. PRICE CONTINUITY LAYER (Calendar-aware, non-bridged segments) │
│       │         │                                                           │
│       │         └──► 3. FEATURE & INDICATOR ENGINE (Pure math on subsegments)│
│       │                   │                                                 │
│  4. STRATEGY ELIGIBILITY  │ (Independent Policy Injection: EQ, BE, ASM)     │
│       │                   ▼                                                 │
│       └────────► 5. SIGNAL GENERATION ENGINE (Zero lookahead: T close)      │
│                           │                                                 │
│                           ▼                                                 │
│                  6. EXECUTION ENGINE (T+1 Open / TWAP, Statutory Costs)     │
│                           │                                                 │
│                           ▼                                                 │
│                  7. EXACT DECIMAL LEDGER (Cash, Equity, PnL Accounting)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pillar 1: Three-Tier Decoupled Series Architecture
1. **Raw Market Observation (`ExchangeSessionObservation`)**:
   - Preserves what the exchange actually published.
   - Retains verbatim raw series code (`raw_series_code: str | None`), pure OHLCV (`PriceBar`), ISIN anchor, and source provenance. Never discarded because a strategy excludes that series.
2. **Price-History Continuity (`PriceSeriesContinuityValidator`)**:
   - Assesses chronological session completeness against the official NSE trading calendar.
   - Evaluates active listing boundaries and verified corporate actions.
   - An `EQ` to `BE` transition does **not** break price continuity when valid price bars exist on both sides.
3. **Research & Trading Eligibility (`SeriesEligibilityPolicy`)**:
   - Governs whether a strategy is permitted to enter a security, hold across series shifts, or participate in trade-to-trade settlement.
   - Injected explicitly by the research configuration with documented approval; zero implicit defaults.

### Pillar 2: Point-in-Time Universe Selection (Zero Survivorship Bias)
- Universe schedules (Nifty 50, Nifty 500, liquid momentum filters) are reconstructed strictly as of date $T$ open, using only data known *before* session $T$ open.
- Index additions, deletions, and liquidity criteria are tracked dynamically. Never select universe constituents using end-of-sample volume or survival.

### Pillar 3: Zero Lookahead & Next-Session Execution
- Signals calculated using information up to session $T$ close execute at earliest on session $T+1$ open (or session $T+1$ TWAP/VWAP) with realistic execution latency.
- Calculating signals at $T$ close and simulating fills at $T$ close is strictly prohibited.

### Pillar 4: Exact Decimal Arithmetic
- All financial numbers—prices, order quantities, transaction charges, statutory taxes, cash balances, equity, and PnL—are represented using exact Python `Decimal` arithmetic.
- Binary floating-point representation (`float`) is banned from trade accounting, fee computation, and portfolio ledgers to prevent cumulative rounding distortion.

### Pillar 5: Fail-Closed Data Integrity (Zero Silent Bridging)
- Every sequence of daily price bars is verified against the official NSE trading calendar.
- A sequence of $N$ available bars is never assumed to represent $N$ consecutive trading sessions if calendar dates intervened.
- Zero silent forward-filling of prices, zero back-filling, zero linear OHLC interpolation, and zero floating-point `NaN` masking.
- Unexplained missing sessions fail closed (`PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD`). The feature engine partitions continuous subsegments and refuses to compute lookbacks across gaps.

---

## 4. Anti-Overfitting & Research Integrity Protocol

1. **Holdout Containment (`HOLDOUT_UNLOCK`)**:
   - Data is split into In-Sample (IS) Training, Calibration / Validation, and Out-of-Sample (OOS) Holdout.
   - The holdout partition is cryptographically sealed. Agents must never access or inspect holdout data. `HOLDOUT_UNLOCK` is strictly human-created.
2. **Append-Only Trial Registry**:
   - Every parameter sweep, rule variation, and indicator test must be logged with its hypothesis.
   - Reports must compute and display the **Deflated Sharpe Ratio (DSR)** and **Haircut Sharpe** to penalize for multiple hypothesis testing ($N$ trials).
3. **Walk-Forward Stability**:
   - A strategy is considered viable only if it demonstrates parameter stability across anchored and rolling walk-forward windows.
4. **Computed Verdicts**:
   - Every PASS/FAIL and GO/NO-GO verdict is generated programmatically from committed threshold files (`configs/go_no_go_criteria.yaml`). Hardcoded qualitative adjectives ("HEALTHY", "ROBUST") are strictly forbidden.
5. **Single Authoritative Engine**:
   - Exactly one simulation, cost, and fill engine is used across backtesting, paper trading, and live execution. Zero shadow simulators or duplicate vectorized fill logic.

