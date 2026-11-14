# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-14T16:45:00+00:00`
- **Evaluation Window:** `2022-01-03` to `2026-10-31`
- **Criteria Version:** `1.1.0`
- **Criteria Fingerprint:** `CRIT-FPR-V1-68775989598c6401c37b10c96f9402d2cfc70a8307b99c10764398cafe3f104e`
- **Calendar Fingerprint:** `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad`
- **Summary Counts:** `PASS=21`, `FAIL=0`, `NOT RUN=2` (Total=23)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2022-01-03` | `2022-01-03 .. 2026-10-31` | **PASS** | YES | Evaluation window (2022-01-03 to 2026-10-31, 1196 sessions) conforms to authoritative binding evaluation schedule >= 2022-01-03 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades | `>= 100` | `342` | **PASS** | YES | Recorded 342 executed round-trip trades in evaluation window. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor | `>= 1.50` | `1.6850` | **PASS** | YES | Computed gross profit / gross loss ratio: 1.6850. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight | `<= 0.10` | `0.0800` | **PASS** | YES | Maximum single position capital allocation observed: 0.0800. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `0.1650` | **PASS** | YES | Maximum closed + open position drawdown observed: 16.50%. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `4.80` | **PASS** | YES | Computed annual portfolio turnover: 4.80x. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `0.0245` | **PASS** | YES | Peak session volume participation observed: 0.0245. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `12.50` | **PASS** | YES | Minimum average daily traded turnover observed: ₹12.50 Cr. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `True` | **PASS** | YES | Simulator strictly enforces zero BUY fills when price equals Upper Circuit band (§5.3). |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `True` | **PASS** | YES | Simulator strictly enforces zero SELL / Stop-Loss fills when price equals Lower Circuit band (§5.3). |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `1` | **PASS** | YES | Orders execute at session T+1 following signal calculation at session T close. |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `True` | **PASS** | YES | Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `True` | **PASS** | YES | Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4). |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `True` | **PASS** | YES | Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3). |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `True` | **PASS** | YES | Tradable constituents determined strictly prior to market open on session T (§6.1). |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `True` | **PASS** | YES | Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3). |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Resolution Pct | `>= 100.0%` | `100.0000%` | **PASS** | YES | Active traded EQ scrips resolved to authoritative ISINs: 100.0000% (§41.3, Finding H-54). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `N = 10` | **PASS** | YES | Trial registry records 10 parameter sweeps/trials with full parameter accountability. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `0.9720` | **PASS** | YES | Deflated Sharpe Ratio 0.9720 adjusts for trial count, variance, skewness, and kurtosis (§8.2). |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `0.8500` | **PASS** | YES | Walk-forward evaluation shows 85.00% of out-of-sample folds delivered positive edge (§8.3). |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not available in synthetic fixture. |

