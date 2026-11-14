# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-14T16:45:00+00:00`
- **Evaluation Window:** `2022-01-03` to `2026-10-30`
- **Criteria Version:** `1.1.0`
- **Criteria Fingerprint:** `CRIT-FPR-V1-22520357204d0645f0df9bd057bd4386f837a3708528376e68f2b66218a98799`
- **Calendar Fingerprint:** `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad`
- **Summary Counts:** `PASS=3`, `FAIL=0`, `NOT RUN=20` (Total=23)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2022-01-03` | `2022-01-03 .. 2026-10-30` | **PASS** | YES | Evaluation window (2022-01-03 to 2026-10-30, 1196 sessions) conforms to authoritative binding evaluation schedule >= 2022-01-03 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades | `>= 100` | `—` | **NOT RUN** | YES | Metric 'total_trades' not provided in results bundle. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor | `>= 1.50` | `—` | **NOT RUN** | YES | Metric 'profit_factor' not provided in results bundle. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight | `<= 0.10` | `—` | **NOT RUN** | YES | Metric 'max_single_position_weight' not provided in results bundle. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `—` | **NOT RUN** | YES | Metric 'max_portfolio_drawdown' not provided in results bundle. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `—` | **NOT RUN** | YES | Metric 'annual_turnover' not provided in results bundle. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `—` | **NOT RUN** | YES | Metric 'max_volume_participation' not provided in results bundle. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `—` | **NOT RUN** | YES | Metric 'min_daily_turnover_crore' not provided in results bundle. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `—` | **NOT RUN** | YES | Flag 'prohibit_buy_at_upper_circuit' not provided in results bundle. |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `—` | **NOT RUN** | YES | Flag 'prohibit_sell_at_lower_circuit' not provided in results bundle. |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `—` | **NOT RUN** | YES | Metric 'execution_latency_sessions' not provided in results bundle. |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `—` | **NOT RUN** | YES | Flag 'statutory_costs_enforced' not provided in results bundle. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `—` | **NOT RUN** | YES | Flag 'strict_decimal_accounting' not provided in results bundle. |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `—` | **NOT RUN** | YES | Flag 'fail_closed_on_unexplained_gaps' not provided in results bundle. |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `—` | **NOT RUN** | YES | Flag 'point_in_time_universe' not provided in results bundle. |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `—` | **NOT RUN** | YES | Flag 'zero_data_fabrication' not provided in results bundle. |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Resolution Pct | `>= 100.0%` | `100.0000%` | **PASS** | YES | Active traded EQ scrips resolved to authoritative ISINs: 100.0000% (§41.3, Finding H-54). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `—` | **NOT RUN** | YES | Metric 'trial_count_n' not provided in results bundle. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `—` | **NOT RUN** | YES | Metric 'deflated_sharpe_ratio' not provided in results bundle. |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `—` | **NOT RUN** | YES | Metric 'walk_forward_positive_fold_ratio' not provided in results bundle. |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills). |

