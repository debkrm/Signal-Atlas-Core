# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-16T05:53:35.045730+00:00`
- **Evaluation Window:** `2022-01-03` to `2024-12-31`
- **Criteria Version:** `1.1.0`
- **Criteria Fingerprint:** `CRIT-FPR-V1-b3f35df928c1ce126e0cbc9f46b4f47f901448d8201bf8922060abe79fcd6677`
- **Calendar Fingerprint:** `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad`
- **Summary Counts:** `PASS=16`, `FAIL=2`, `NOT RUN=6` (Total=24)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2022-01-03` | `2022-01-03 .. 2024-12-31` | **PASS** | YES | Evaluation window (2022-01-03 to 2024-12-31, 743 sessions) conforms to authoritative binding evaluation schedule >= 2022-01-03 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades | `>= 100` | `190` | **PASS** | YES | Recorded 190 executed round-trip trades in evaluation window. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor | `>= 1.50` | `1.7428` | **PASS** | YES | Computed gross profit / gross loss ratio: 1.7428. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight | `<= 0.10` | `0.1130` | **FAIL** | YES | Maximum single position capital allocation observed: 0.1130. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `0.1236` | **PASS** | YES | Maximum closed + open position drawdown observed: 12.36%. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `—` | **NOT RUN** | YES | Metric 'annual_turnover' not provided in results bundle. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `0.0001` | **PASS** | YES | Peak session volume participation observed: 0.0001. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `40.32` | **PASS** | YES | Minimum average daily traded turnover observed: ₹40.32 Cr. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `True` | **PASS** | YES | Simulator strictly enforces zero BUY fills when price equals Upper Circuit band (§5.3). |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `True` | **PASS** | YES | Simulator strictly enforces zero SELL / Stop-Loss fills when price equals Lower Circuit band (§5.3). |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `1` | **PASS** | YES | Orders execute at session T+1 following signal calculation at session T close. |
| CRIT-SURV-01 | Surveillance Realism | Surveillance Exit Constraints Enforced | `ENFORCED / VERIFIED` | `NOT_RUN` | **NOT RUN** | YES | Authoritative surveillance coverage absent for held securities: ['INE075A01022', 'INE090A01021', 'INE094A01015', 'INE127D01025', 'INE101A01026', 'INE935N01020', 'INE118H01025', 'INE646L01027', 'INE437A01024', 'INE736A01011', 'INE860A01027', 'INE591G01017', 'INE040A01034', 'INE982J01020', 'INE745G01035', 'INE382Z01011', 'INE417T01026', 'INE881D01027'] |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `True` | **PASS** | YES | Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `True` | **PASS** | YES | Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4). |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `True` | **PASS** | YES | Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3). |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `True` | **PASS** | YES | Tradable constituents determined strictly prior to market open on session T (§6.1). |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `True` | **PASS** | YES | Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3). |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Resolution Pct | `>= 100.0%` | `92.8910%` | **FAIL** | YES | Active traded EQ scrips resolved to authoritative ISINs: 92.8910% (§41.3, Finding H-54). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `N = 2` | **PASS** | YES | Trial registry records 2 parameter sweeps/trials with full parameter accountability. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `—` | **NOT RUN** | YES | Metric 'deflated_sharpe_ratio' not provided in results bundle. |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `—` | **NOT RUN** | YES | Metric 'walk_forward_positive_fold_ratio' not provided in results bundle. |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills). |
