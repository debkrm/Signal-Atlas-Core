# Signal Atlas — Automated Go/No-Go Research Verdict Report

- **Overall Decision:** `NO-GO`
- **Evaluated At (UTC):** `2026-11-19T16:59:32.466127+00:00`
- **Evaluation Window:** `2018-04-02` to `2023-12-29`
- **Criteria Version:** `1.1.16`
- **Criteria Fingerprint:** `CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470`
- **Calendar Fingerprint:** `CAL-FPR-V1-6acb5f45ce5686a503a53e7fc96c12a41391d16bde5abbe2f9c91073c47a9ac9`
- **Summary Counts:** `PASS=15`, `FAIL=6`, `NOT RUN=7` (Total=28)

## Detailed Criteria Evaluation Matrix

| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |
|---|---|---|---|---|---|---|---|
| CRIT-WINDOW-01 | Evaluation Window Integrity | Binding Evaluation Window Conformance | `>= 2018-04-01` | `2018-04-02 .. 2023-12-29` | **PASS** | YES | Evaluation window (2018-04-02 to 2023-12-29, 1425 sessions) conforms to authoritative binding evaluation schedule >= 2018-04-01 and calendar bounds [2015-01-01 .. 2026-11-11] (Findings H-65, H-66, H-69). |
| CRIT-STAT-01 | Risk & Performance | Total Completed Trades (Liquidated Book) | `>= 100` | `—` | **NOT RUN** | YES | total_trades = 1119 was supplied with neither 'liquidated_open_positions' nor 'liquidated_trade_count', so the de-censored basis cannot be reconciled and the row is NOT RUN rather than a PASS on the key's name (Audit §78.8, N-148). A producer that cannot enumerate the liquidated positions must fail here, not omit the column that triggers the check. |
| CRIT-STAT-02 | Risk & Performance | Profit Factor (Liquidated Book) | `>= 1.50` | `1.2820` | **FAIL** | YES | Liquidated gross profit / gross loss ratio: 1.2820. Sensitivity: 1.2471 without the single largest winner, 1.1988 without the top three. Closed-only book retained as disclosure: 1101 round trip(s) at PF 1.2151. §76.12 Ruling 1. |
| CRIT-STAT-03 | Risk & Performance | Max Single Position Weight (At Entry) | `<= 0.10` | `0.0866` | **PASS** | YES | Maximum executed entry notional / portfolio equity at entry: 0.0866. Hold-period maximum position weight (non-gating disclosure): 0.2013. §76.13 Ruling 2. |
| CRIT-STAT-04 | Risk & Performance | Max Portfolio Drawdown | `<= 0.25` | `0.5193` | **FAIL** | YES | Maximum closed + open position drawdown observed: 51.93%. |
| CRIT-STAT-05 | Risk & Performance | Annual Portfolio Turnover | `<= 12.0` | `11.60` | **PASS** | YES | Computed annual portfolio turnover: 11.60x. |
| CRIT-EXEC-01 | Execution Realism | Volume Participation Cap | `<= 0.03` | `0.0025` | **PASS** | YES | Peak session volume participation observed: 0.0025. |
| CRIT-EXEC-02 | Execution Realism | Min Traded Value (Cr) | `>= 5.0` | `25.26` | **PASS** | YES | Minimum average daily traded turnover observed: ₹25.26 Cr. |
| CRIT-EXEC-03 | Execution Realism | Upper Circuit BUY Prohibition | `True` | `—` | **NOT RUN** | YES | 1425 of 1425 evaluated session(s) (2018-04-02..2023-12-29) in the window 2018-04-02..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 1425 of 1425 evaluated session(s) (2018-04-02..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-04 | Execution Realism | Lower Circuit SELL Prohibition | `True` | `—` | **NOT RUN** | YES | 1425 of 1425 evaluated session(s) (2018-04-02..2023-12-29) in the window 2018-04-02..2023-12-29 have no sourced NSE price-band report (earliest attested snapshot 2024-01-16); circuit-prohibition compliance cannot be asserted, so this criterion is NOT RUN (§5.3, §9.1, Finding H-120). Producer note: 1425 of 1425 evaluated session(s) (2018-04-02..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8). |
| CRIT-EXEC-05 | Execution Realism | Execution Latency (Sessions) | `>= 1` | `1` | **PASS** | YES | Orders execute at session T+1 following signal calculation at session T close. |
| CRIT-SURV-01 | Surveillance Realism | Surveillance Exit Constraints Enforced | `ENFORCED / VERIFIED` | `NOT_RUN` | **NOT RUN** | YES | Authoritative surveillance coverage absent for held securities: ['INE134E01011', 'INE040H01021', 'INE070D01027', 'INE251B01027', 'INE811K01011', 'INE292B01021', 'INE737H01014', 'INE672A01018', 'INE066P01011', 'INE495S01016', 'INE863B01011', 'INE039A01010', 'INE880L01014', 'INE893I01013', 'INE509F01011', 'INE455F01025', 'INE713T01028', 'INE087A01019'] |
| CRIT-COST-01 | Cost Realism | Statutory Cost Model Enforced | `True` | `True` | **PASS** | YES | Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed. |
| CRIT-DATA-01 | Accounting Integrity | Strict Decimal Accounting | `True` | `True` | **PASS** | YES | Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4). |
| CRIT-DATA-02 | Data Integrity | Fail Closed on Unexplained Gaps | `True` | `True` | **PASS** | YES | Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3). |
| CRIT-DATA-03 | Data Integrity | Point-in-Time Universe Selection | `True` | `True` | **PASS** | YES | Tradable constituents determined strictly prior to market open on session T (§6.1). |
| CRIT-DATA-04 | Data Integrity | Zero Data Fabrication | `True` | `True` | **PASS** | YES | Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3). |
| CRIT-DATA-05 | Universe Integrity | Traded EQ Row Resolution Pct (Evaluation Window) | `>= 100.0%` | `100.0000%` | **PASS** | YES | Traded EQ bhavcopy rows inside the evaluation window that carry an authoritative identity: 100.0000% (2578060 of 2578060 window row(s)) (§41.3, Finding H-54). |
| CRIT-DATA-07 | Universe Integrity | Dataset Instrument Resolution Pct | `>= 100.0%` | `100.0000%` | **PASS** | YES | Research-dataset instruments resolved to an authoritative ISIN: 100.0000% (2735 of 2735 dataset instrument(s)); an instrument that never resolved never entered the universe, so a missing share cannot support a breadth claim (§13.4, §76.9 N-140). |
| CRIT-DATA-06 | Calendar Integrity | Calendar Fingerprint Anchor | `CAL-FPR-V1-6acb5f45ce5686a503a53e7fc96c12a41391d16bde5abbe2f9c91073c47a9ac9` | `CAL-FPR-V1-6acb5f45ce5686a503a53e7fc96c12a41391d16bde5abbe2f9c91073c47a9ac9` | **PASS** | YES | Loaded calendar anchored and verified against criteria pins: full=CAL-FPR-V1-6acb5f45ce5686a503a53e7fc96c12a41391d16bde5abbe2f9c91073c47a9ac9, sourced_1196=CAL-FPR-V1-2d5ac7ac32455327cd636d64a4e15a1f689f25eb42a815e151ea31c3cf61cda1. |
| CRIT-PROV-01 | Data Provenance | Data Provenance Verification | `VERIFIED / EXCHANGE_ATTESTED` | `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` | **NOT RUN** | YES | Dataset provenance is 'CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist. |
| CRIT-OVERFIT-01 | Anti-Overfitting | Trial Registry Accountability | `N >= 2` | `N = 11` | **PASS** | YES | Trial registry records 11 parameter sweeps/trials with full parameter accountability. |
| CRIT-OVERFIT-02 | Anti-Overfitting | Deflated Sharpe Ratio (DSR) | `>= 0.95` | `0.0963` | **FAIL** | YES | Deflated Sharpe Ratio 0.0963 adjusts for trial count, variance, skewness, and kurtosis (§8.2). |
| CRIT-OVERFIT-04 | Anti-Overfitting | Haircut Sharpe Ratio | `>= 1.25` | `0.0000` | **FAIL** | YES | Haircut Sharpe Ratio 0.0000 at N_eval = 6 against min_haircut_sharpe_ratio 1.25 (BONFERRONI); a Sharpe that survives no multiple-testing haircut is not evidence (§8.2, N-141). |
| CRIT-OVERFIT-03 | Walk-Forward Stability | Positive Anchored In-Sample Folds Ratio | `>= 0.75` | `0.0000` | **FAIL** | YES | 0 of 4 anchored expanding in-sample fold(s) met both conditions (closed-book net expectancy > 0 and liquidated PF >= 1.30): IS-F1 (exits to 2022-06-30): closed net expectancy 94.77761831753637514654161782, liquidated PF 1.075165922776280431802131898 -> not positive; IS-F2 (exits to 2022-12-30): closed net expectancy 204.0259774862495613660618997, liquidated PF 1.115117909824655957500350501 -> not positive; IS-F3 (exits to 2023-06-30): closed net expectancy 178.6593418886453053658536585, liquidated PF 1.105324681444295419256889159 -> not positive; IS-F4 (exits to 2023-12-29): closed net expectancy 505.4918025610830681198910082, liquidated PF 1.281989670001573246299919807 -> not positive. |
| CRIT-OVERFIT-05 | Anti-Overfitting | Liquidated Profit Factor Ex-Top-1 Winner | `>= 1.40` | `1.2471` | **FAIL** | YES | Liquidated profit factor recomputed without its single largest winner: 1.2471 against min_liquidated_pf_ex_top_1 1.40 (§77.12 item 4). |
| CRIT-OVERFIT-06 | Walk-Forward Stability | Positive Out-of-Sample Folds Ratio | `>= 0.80` | `—` | **NOT RUN** | YES | Only N_val = 0 validation fold evaluated; minimum 2 independent out-of-sample validation folds are required before a stability ratio is gated, so the supplied ratio NOT RUN is NOT RUN rather than PASS (§8.3, Audit §78.10, N-150). |
| CRIT-INFO-01 | Execution Accounting | Circuit-Verified PnL Accounting | `True` | `—` | **NOT RUN** | NO | Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills). |


## Walk-Forward Fold Performance (Audit §64 H-103, §66 N-108)

| Fold | Window | Sessions | Start Equity | End Equity | CAGR | Max Drawdown | Closed Trades | Win Rate | Profit Factor |
|---|---|---|---|---|---|---|---|---|---|
| Fold 0 (In-Sample) | 2018-04-01 .. 2023-12-31 | 1424 | ₹1,000,000.00 | ₹1,789,528.81 | 10.76% | 51.93% | 1101 | 37.69% | 1.2151 |

> [!NOTE]
> **In-Sample-Only Disclosure (§66.5 Condition 1)**: This exploratory run evaluated 2022-01-03..2023-12-29 only. The 2024 Validation fold is frozen and was not evaluated, so `CRIT-OVERFIT-03` is `NOT RUN` and no result here is out-of-sample evidence.

## Band Coverage Diagnostics & Disclosure (Audit §65 H-110)

> [!NOTE]
> Price band coverage across 2022–2024 reflects historical exchange report availability:
> - **2022–2023**: Band-ineligible (CA-3(c)). No sourced NSE price-band report exists; only the dynamic flexing anchor names (COCHINSHIP, HDFC, INFY, RELIANCE) carry ±10% derived limits. Cash-universe names without price band reports are rejected/skipped per §5.3 fail-closed invariants (567 fills executed), and `CRIT-EXEC-03`/`-04` are `NOT RUN` over these sessions.
> - **2024**: Cash-universe coverage (0 scrips) supported by the attested 2024-01-16 `sec_list` snapshot applied as static bands (0 fills executed). Unverified assumption (N-126): those bands held for every session from 2024-01-16 to 2024-12-31; the fold's first fifteen sessions (2024-01-01..2024-01-15) are unsourced and band-ineligible.
> - **Universe Integrity & Gap Filtering**: 1383 continuous active instruments evaluated out of 2735 valid ISINs (1352 instruments refused due to unexplained missing sessions per §6.3 fail-closed invariants).

| Year | Sessions | Band-Covered ISINs | Unbanded ISINs | Zero-Ticket Sessions | Tickets Emitted | Tickets Filled | Tickets Rejected | Locked-Bar Refusals | Closed Trades | CAGR | Win Rate | Profit Factor | Max Drawdown | Coverage Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 248 | 4 | 504 | 0 | 17536 | 300 | 77 | 1 | 198 | -11.77% | 37.88% | 1.0963 | 51.93% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2022; dynamic flexing anchor names (COCHINSHIP, HDFC, INFY, RELIANCE) carry only ±10% derived limits (300 fills executed); band_policy=LOCKED_BAR_REFUSAL_ONLY: 17374 unbanded order(s) submitted, 1 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |
| 2023 | 246 | 4 | 620 | 0 | 30231 | 267 | 63 | 0 | 164 | 32.99% | 42.68% | 1.6477 | 51.93% | Band-ineligible (CA-3(c)): no sourced NSE price-band report exists for 2023; dynamic flexing anchor names (COCHINSHIP, HDFC, INFY, RELIANCE) carry only ±10% derived limits (267 fills executed); band_policy=LOCKED_BAR_REFUSAL_ONLY: 29985 unbanded order(s) submitted, 0 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |
| 2024 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | 0.00% | 0.0000 | 0.00% | Cash universe coverage: 0 scrips supported by the attested 2024-01-16 sec_list snapshot applied as static bands (0 fills executed); unverified assumption: those bands held for every session from 2024-01-16 to 2024-12-31 (N-126); band_policy=LOCKED_BAR_REFUSAL_ONLY: 0 unbanded order(s) submitted, 0 refused on a locked bar (high == low, §5.3); CRIT-EXEC-03/-04 NOT RUN on unbanded sessions |

> [!WARNING]
> **Price Band Sourcing (CA-3(c))**: 1425 of 1425 evaluated session(s) (2018-04-02..2023-12-29) have no sourced NSE price-band report; the only attested report is sec_list_20240116.csv. Circuit-prohibition compliance cannot be asserted over unsourced sessions, so this criterion is NOT RUN rather than PASS on an interpolated band (CA-3(c), §6.3, §10.8).

## Closed-Trade Ledger (Audit §72 N-129)

> 1101 closed round trip(s); mean net expectancy 505.4918025610830681198910082; statutory costs attributable to closed trades ₹201,467.29 (₹203,742.33 across every fill, including entries still open).
> Exit reasons: DEMERGER_FORCED_EXIT=1, MAX_HOLD_BOUND_EXIT=495, SIGNAL_EXIT=125, STOP_LOSS=480. Protective stop exits 480; exits deferred by a frozen bid (§5.3) 0 of 792 deferral(s).
> Every row is in `closed_trades` in the JSON artifact, and the two aggregates above are computed from that array.

## Window-End Liquidation (Audit §75.8 N-136)

> 1101 closed round trip(s) plus 18 open position(s) liquidated at the 2023-12-29 close (0 unpriced position(s) excluded, never valued at book).
> Closed-only PF 1.2151 / expectancy 505.4918025610830681198910082; liquidated PF 1.2820 / expectancy 698.6902850220850778173742194. Open-book unrealized ₹232,982.29; liquidation exit costs ₹2,281.11 and exit slippage ₹5,413.29.
> Identity: closed net ₹556,546.47 + open unrealized ₹232,982.29 − Δequity ₹789,528.81 = ₹0.0000 (tolerance ₹11.19).
> The liquidation is a diagnostic computed through the same slippage and statutory-cost models as every fill: no ledger entry, no fill and no `closed_trades` row is produced.
> PF sensitivity: 1.247148495993224079028932645 without the single largest winner, 1.198825255646686063855152290 without the top three; `CRIT-STAT-01`/`-02` are evaluated on the liquidated book over 1119 round trip(s) (Audit §76.12 Ruling 1).

## Concentration and Refusals (Audit §76.13 Ruling 2, §76.11 N-142)

> Maximum single-position weight **at trade entry** 0.0866 (gated by `CRIT-STAT-03`); maximum hold-period weight 0.2013 (non-gating disclosure, §76.13). 0 BUY fill(s) carried no executed price or no equity snapshot and were excluded from the entry weight.
> Tickets rejected: 275. By side and reason: {"BUY": {"REJECTED_INSUFFICIENT_TURNOVER": 6, "REJECTED_LOCKED_SESSION": 1, "REJECTED_RISK_LIMIT": 264}, "SELL": {"REJECTED_INSUFFICIENT_TURNOVER": 3, "REJECTED_LOCKED_SESSION": 1}}.

## Coverage: Rows versus Instruments (Audit §76.9 N-140, Ruling 3)

> Traded EQ rows resolved (2578060 / 2578060) = **100.0000%** — this is `CRIT-DATA-05` and the H-54 measure.
> Dataset instruments resolved (2735 / 2735) = **100.0000%** — this is `CRIT-DATA-07` (dataset completeness). The two are different quantities with different thresholds and are never reported under each other's name.
> Unresolved dataset instruments: none.

## In-Sample Fold Stability (Audit §77.13)

> 0 of 4 anchored expanding in-sample fold(s) met both conditions: closed-book net expectancy > 0 and liquidated PF >= 1.30 (ratio **0.0000** against `CRIT-OVERFIT-03`'s 0.75).
> The folds share one run: anchored at 2018-04-02, ending 2022-06-30, 2022-12-30, 2023-06-30, 2023-12-29, partitioned by exit date. No re-fit and no re-run, so the four partitions are one trial and the 2024 validation fold is not spent.
> IS-F1 to 2022-06-30: closed net expectancy 94.77761831753637514654161782, liquidated PF 1.075165922776280431802131898, not positive | IS-F2 to 2022-12-30: closed net expectancy 204.0259774862495613660618997, liquidated PF 1.115117909824655957500350501, not positive | IS-F3 to 2023-06-30: closed net expectancy 178.6593418886453053658536585, liquidated PF 1.105324681444295419256889159, not positive | IS-F4 to 2023-12-29: closed net expectancy 505.4918025610830681198910082, liquidated PF 1.281989670001573246299919807, not positive

