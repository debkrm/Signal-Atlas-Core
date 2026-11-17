# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-17T04:28:30.647846+00:00`
- **Evaluation Window:** `2022-01-03` to `2023-12-29`
- **Criteria Version:** `1.1.4`
- **Criteria Fingerprint:** `CRIT-FPR-V1-a92d85771538fba884562d25eaa6a55da20c1d70fc49e3261d4f3a4943f5b0df`
- **Calendar Fingerprint:** `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad`
- **Summary Counts:** `PASS=13`, `FAIL=5`, `NOT RUN=6` (Total=24)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2022-01-03` | `2022-01-03 .. 2023-12-29` | **PASS** | YES | Evaluation window (2022-01-03 to 2023-12-29, 494 sessions) conforms to authoritative binding evaluation schedule >= 2022-01-03 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades | `>= 100` | `438` | **PASS** | YES | Recorded 438 executed round-trip trades in evaluation window. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor | `>= 1.50` | `0.6826` | **FAIL** | YES | Computed gross profit / gross loss ratio: 0.6826. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight | `<= 0.10` | `0.1141` | **FAIL** | YES | Maximum single position capital allocation observed: 0.1141. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `0.2973` | **FAIL** | YES | Maximum closed + open position drawdown observed: 29.73%. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `8.39` | **PASS** | YES | Computed annual portfolio turnover: 8.39x. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `0.0008` | **PASS** | YES | Peak session volume participation observed: 0.0008. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `51.57` | **PASS** | YES | Minimum average daily traded turnover observed: ₹51.57 Cr. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `—` | **NOT RUN** | YES | 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) in the window 2022-01-03..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `—` | **NOT RUN** | YES | 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) in the window 2022-01-03..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `1` | **PASS** | YES | Orders execute at session T+1 following signal calculation at session T close. |
| CRIT-SURV-01 | Surveillance Realism | Surveillance Exit Constraints Enforced | `ENFORCED / VERIFIED` | `NOT_RUN` | **NOT RUN** | YES | Authoritative surveillance coverage absent for held securities: ['INE118H01025', 'INE522F01014', 'INE213A01029', 'INE752E01010', 'INE095A01012', 'INE114A01011', 'INE158A01026', 'INE917I01010', 'INE758T01015', 'INE397D01024', 'INE494B01023', 'INE860A01027', 'INE155A01022', 'INE271C01023', 'INE692A01016', 'INE04I401011', 'INE775A01035', 'INE134E01011', 'INE027H01010', 'INE020B01018', 'INE127D01025', 'INE962Y01021', 'INE669E01016', 'INE745G01035', 'INE002L01015'] |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `True` | **PASS** | YES | Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `True` | **PASS** | YES | Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4). |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `True` | **PASS** | YES | Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3). |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `True` | **PASS** | YES | Tradable constituents determined strictly prior to market open on session T (§6.1). |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `True` | **PASS** | YES | Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3). |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Resolution Pct | `>= 100.0%` | `92.8910%` | **FAIL** | YES | Active traded EQ scrips resolved to authoritative ISINs: 92.8910% (§41.3, Finding H-54). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | `CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-af8e309a6f897a670725a342aa821ec4134c5d40e56e7c3c7b1043549abfe5ad, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `N = 8` | **PASS** | YES | Trial registry records 8 parameter sweeps/trials with full parameter accountability. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `0.2446` | **FAIL** | YES | Deflated Sharpe Ratio 0.2446 adjusts for trial count, variance, skewness, and kurtosis (§8.2). |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `—` | **NOT RUN** | YES | In-sample-only exploratory run: the 2024 Validation fold is frozen and was not evaluated (§66.5 Condition 1). No out-of-sample stability ratio is computable. |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills). |


## Walk-Forward Fold Performance (Audit §64 H-103, §66 N-108)

| Fold | Window | Sessions | Start Equity | End Equity | CAGR | Max Drawdown | Closed Trades | Win Rate | Profit Factor |
|---|---|---|---|---|---|---|---|---|---|
| Fold 0 (In-Sample) | 2022-01-03 .. 2023-12-29 | 493 | ₹1,000,000.00 | ₹978,479.40 | -1.10% | 29.73% | 438 | 16.67% | 0.6826 |

> [!NOTE]
> **In-Sample-Only Disclosure (§66.5 Condition 1)**: This exploratory run evaluated 2022-01-03..2023-12-29 only. The 2024 Validation fold is frozen and was not evaluated, so `CRIT-OVERFIT-03` is `NOT RUN` and no result here is out-of-sample evidence.

## Band Coverage Diagnostics & Disclosure (Audit §65 H-110)

> [!NOTE]
> Price band coverage across 2022–2024 reflects historical exchange report availability:
> - **2022–2023**: Band-ineligible (CA-3(c)). No sourced NSE price-band report exists; only the dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry ±10% derived limits. Cash-universe names without price band reports are rejected/skipped per §5.3 fail-closed invariants (771 fills executed), and `CRIT-EXEC-03`/`-04` are `NOT RUN` over these sessions.
> - **2024**: Cash-universe coverage (0 scrips) supported by the attested 2024-01-16 `sec_list` snapshot applied as static bands (0 fills executed). Unverified assumption (N-126): those bands held for every session from 2024-01-16 to 2024-12-31; the fold's first fifteen sessions (2024-01-01..2024-01-15) are unsourced and band-ineligible.
> - **Universe Integrity & Gap Filtering**: 179 continuous active instruments evaluated out of 196 valid ISINs (17 instruments refused due to unexplained missing sessions per §6.3 fail-closed invariants).

| Year | Sessions | Band-Covered ISINs | Unbanded ISINs | Zero-Ticket Sessions | Tickets Emitted | Tickets Filled | Tickets Rejected | Locked-Bar Refusals | Closed Trades | CAGR | Win Rate | Profit Factor | Max Drawdown | Coverage Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 248 | 3 | 145 | 57 | 2857 | 355 | 111 | 0 | 205 | -13.07% | 13.66% | 0.5911 | 17.67% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2022; dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry only ±10% derived limits (355 fills executed); band_policy=LOCKED_BAR_REFUSAL_ONLY: 2803 unbanded order(s) submitted, 0 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |
| 2023 | 246 | 3 | 132 | 7 | 4290 | 416 | 84 | 0 | 233 | 11.56% | 19.31% | 0.8163 | 29.73% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2023; dynamic flexing anchor names (HDFC, INFY, RELIANCE) carry only ±10% derived limits (416 fills executed); band_policy=LOCKED_BAR_REFUSAL_ONLY: 4204 unbanded order(s) submitted, 0 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |
| 2024 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% | 0.0000 | 0.00% | Cash universe coverage: 0 scrips supported by the attested 2024-01-16 sec_list snapshot applied as static bands (0 fills executed); unverified assumption: those bands held for every session from 2024-01-16 to 2024-12-31 (N-126); band_policy=LOCKED_BAR_REFUSAL_ONLY: 0 unbanded order(s) submitted, 0 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |

> [!WARNING]
> **Price Band Sourcing (CA-3(c))**: 494 of 494 evaluated session(s) (2022-01-03..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8).

## Closed-Trade Ledger (Audit §72 N-129)

> 438 closed round trip(s); mean net expectancy -462.0250002148044109589041096; statutory costs attributable to closed trades ₹54,222.10 (₹55,760.01 across every fill, including entries still open).
> Exit reasons: SIGNAL_EXIT=308, STOP_LOSS=130. Protective stop exits 130; exits deferred by a frozen bid (§5.3) 0 of 0 deferral(s).
> Every row is in `closed_trades` in the JSON artifact, and the two aggregates above are computed from that array.

