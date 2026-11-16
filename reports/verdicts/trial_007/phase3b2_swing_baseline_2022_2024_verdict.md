# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-16T18:10:25.471661+00:00`
- **Evaluation Window:** `2022-01-03` to `2023-12-29`
- **Criteria Version:** `1.1.2`
- **Criteria Fingerprint:** `CRIT-FPR-V1-1cce20a007294bd37aef5b8e75d459df4f1ce6fedefad6320759a70597ab0bae`
- **Calendar Fingerprint:** `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad`
- **Summary Counts:** `PASS=14`, `FAIL=4`, `NOT RUN=6` (Total=24)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2022-01-03` | `2022-01-03 .. 2023-12-29` | **PASS** | YES | Evaluation window (2022-01-03 to 2023-12-29, 494 sessions) conforms to authoritative binding evaluation schedule >= 2022-01-03 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades | `>= 100` | `15` | **FAIL** | YES | Recorded 15 executed round-trip trades in evaluation window. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor | `>= 1.50` | `0.2197` | **FAIL** | YES | Computed gross profit / gross loss ratio: 0.2197. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight | `<= 0.10` | `0.0918` | **PASS** | YES | Maximum single position capital allocation observed: 0.0918. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `0.0402` | **PASS** | YES | Maximum closed + open position drawdown observed: 4.02%. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `0.59` | **PASS** | YES | Computed annual portfolio turnover: 0.59x. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `0.0000` | **PASS** | YES | Peak session volume participation observed: 0.0000. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `644.39` | **PASS** | YES | Minimum average daily traded turnover observed: ₹644.39 Cr. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `—` | **NOT RUN** | YES | 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) in the window 2022-01-03..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `—` | **NOT RUN** | YES | 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) in the window 2022-01-03..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `1` | **PASS** | YES | Orders execute at session T+1 following signal calculation at session T close. |
| CRIT-SURV-01 | Surveillance Realism | Surveillance Exit Constraints Enforced | `ENFORCED / VERIFIED` | `NOT_RUN` | **NOT RUN** | YES | Authoritative surveillance coverage absent for held securities: ['INE009A01021', 'INE002A01018'] |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `True` | **PASS** | YES | Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `True` | **PASS** | YES | Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4). |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `True` | **PASS** | YES | Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3). |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `True` | **PASS** | YES | Tradable constituents determined strictly prior to market open on session T (§6.1). |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `True` | **PASS** | YES | Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3). |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Resolution Pct | `>= 100.0%` | `92.8910%` | **FAIL** | YES | Active traded EQ scrips resolved to authoritative ISINs: 92.8910% (§41.3, Finding H-54). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `N = 7` | **PASS** | YES | Trial registry records 7 parameter sweeps/trials with full parameter accountability. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `0.1449` | **FAIL** | YES | Deflated Sharpe Ratio 0.1449 adjusts for trial count, variance, skewness, and kurtosis (§8.2). |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `—` | **NOT RUN** | YES | In-sample-only exploratory run: the 2024 Validation fold is frozen and was not evaluated (§66.5 Condition 1). No out-of-sample stability ratio is computable. |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills). |


## Walk-Forward Fold Performance (Audit §64 H-103, §66 N-108)

| Fold | Window | Sessions | Start Equity | End Equity | CAGR | Max Drawdown | Closed Trades | Win Rate | Profit Factor |
|---|---|---|---|---|---|---|---|---|---|
| Fold 0 (In-Sample) | 2022-01-03 .. 2023-12-29 | 493 | ₹1,000,000.00 | ₹976,098.80 | -1.22% | 4.02% | 15 | 13.33% | 0.2197 |

> [!NOTE]
> **In-Sample-Only Disclosure (§66.5 Condition 1)**: This exploratory run evaluated 2022-01-03..2023-12-29 only. The 2024 Validation fold is frozen and was not evaluated, so `CRIT-OVERFIT-03` is `NOT RUN` and no result here is out-of-sample evidence.

## Band Coverage Diagnostics & Disclosure (Audit §65 H-110)

> [!NOTE]
> Price band coverage across 2022–2024 reflects historical exchange report availability:
> - **2022–2023**: Band-ineligible (CA-3(c)). No sourced NSE price-band report exists; only the dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry ±10% derived limits. Cash-universe names without price band reports are rejected/skipped per §5.3 fail-closed invariants (30 fills executed), and `CRIT-EXEC-03`/`-04` are `NOT RUN` over these sessions.
> - **2024**: Cash-universe coverage (0 scrips) supported by the attested 2024-01-16 `sec_list` snapshot applied as static bands (0 fills executed). Unverified assumption (N-126): those bands held for every session from 2024-01-16 to 2024-12-31; the fold's first fifteen sessions (2024-01-01..2024-01-15) are unsourced and band-ineligible.
> - **Universe Integrity & Gap Filtering**: 179 continuous active instruments evaluated out of 196 valid ISINs (17 instruments refused due to unexplained missing sessions per §6.3 fail-closed invariants).

| Year | Sessions | Band-Covered ISINs | Zero-Ticket Sessions | Tickets Emitted | Tickets Filled | Tickets Rejected | Closed Trades | CAGR | Win Rate | Profit Factor | Max Drawdown | Coverage Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 248 | 3 | 228 | 19 | 19 | 0 | 10 | -3.42% | 0.00% | 0.0000 | 3.50% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2022; dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry only ±10% derived limits and cash names are rejected/skipped per §5.3 fail-closed invariants (19 fills executed); circuit criteria are NOT RUN for these sessions |
| 2023 | 246 | 3 | 235 | 11 | 11 | 0 | 5 | 1.04% | 40.00% | 1.3043 | 4.02% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2023; dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry only ±10% derived limits and cash names are rejected/skipped per §5.3 fail-closed invariants (11 fills executed); circuit criteria are NOT RUN for these sessions |
| 2024 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% | 0.0000 | 0.00% | Cash universe coverage: 0 scrips supported by the attested 2024-01-16 sec_list snapshot applied as static bands (0 fills executed); unverified assumption: those bands held for every session from 2024-01-16 to 2024-12-31 (N-126) |

> [!WARNING]
> **Price Band Sourcing (CA-3(c))**: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8).

## Closed-Trade Ledger (Audit §72 N-129)

> 15 closed round trip(s); mean net expectancy -2194.130204710324133333333333; statutory costs attributable to closed trades ₹3,282.65 (₹3,512.87 across every fill, including entries still open).
> Exit reasons: SIGNAL_EXIT=13, STOP_LOSS=2. Protective stop exits 2; exits deferred by a frozen bid (§5.3) 0 of 0 deferral(s).
> Every row is in `closed_trades` in the JSON artifact, and the two aggregates above are computed from that array.

