# Signal Atlas Core — Raw Bhavcopy Reconciliation and Exchange-Series Policy Report

**Date**: 2026-11-02  
**Scope**: Complete Row-Level Audit of 545 Unmatched Universe Membership Pairs across 743 Historical NSE Bhavcopy Archives (2022–2024)

---

## 1. Executive Summary

This report establishes the empirical truth regarding the 545 Point-in-Time universe constituent dates that lack an analytical price record in the historical research dataset `historical_dev_dataset_2022_2024.json`.

Using a fully reproducible, automated reconciliation engine ([`scripts/reconcile_bhavcopy_series.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/reconcile_bhavcopy_series.py)), every one of the 545 pairs was cross-referenced directly against the raw, uncompressed exchange Bhavcopy files in `data/raw/` (248 sessions in 2022, 246 in 2023, and 249 in 2024).

### Key Empirical Findings
1. **The 511-Pair Omission is a Confirmed Extraction Filter Defect**:
   - Exactly **511 pairs** (93.8%) correspond to active exchange trading sessions where the scrip was actively traded under Series `BE` (Book Entry / Trade-to-Trade segment) on the National Stock Exchange of India.
   - The raw Bhavcopy archives confirm regular market liquidity, non-zero traded volume, and valid OHLC prints for every one of these 511 sessions.
   - They were omitted from `prices_by_instrument` because the legacy snapshot extractor (`signal_atlas.quality.adjustment.get_point_in_time_adjusted_history()`) hardcoded a filter `WHERE dpr.series = 'EQ'`, while the Point-in-Time Universe Selection Policy explicitly permitted both `EQ` and `BE` (`permitted_series = ("EQ", "BE")`).
2. **The 34-Pair Omission is Confirmed Stale Universe Schedule Retention**:
   - Exactly **34 pairs** (6.2%) correspond to dates where the instrument was legitimately absent from exchange trading due to corporate mergers, delistings, or stock-split ISIN transitions.
   - **HDFC** (13 sessions) and **MINDTREE** (6 sessions) ceased trading on the exchange upon merger into HDFC Bank and LTIMindtree respectively, yet the legacy universe schedule erroneously retained them until month-end.
   - **COCHINSHIP** (15 sessions) executed a 2:1 stock split on 2024-01-10; its old ISIN (`INE704P01017`) was superseded by new ISIN (`INE704P01025`). The legacy universe schedule retained the pre-split instrument UUID for 15 sessions past its transition date.

---

## 2. Exact Reconciliation Totals

| Audit Metric | Exact Count | Percentage | Outcome & Verification Details |
|---|---|---|---|
| **Total Missing Pairs Audited** | **545** | 100.0% | Complete set of universe membership dates lacking price records |
| **Matched to Raw Series `BE`** | **511** | 93.8% | Scrips traded under Trade-to-Trade segment; dropped by legacy extractor |
| **Matched to Raw Series `EQ`** | **0** | 0.0% | Zero instances of normal cash equity records missed |
| **Matched to Other Series** | **0** | 0.0% | Zero matches to non-equity or debt series (BL, BO, W3, etc.) |
| **No Raw Record in Exchange Bhavcopy** | **34** | 6.2% | Verified delisted, merged, or superseded ISIN |
| **Ambiguous Instrument Identity** | **0** | 0.0% | 100% of rows mapped unambiguously via verified ISINs |
| **Duplicate Raw Matches** | **0** | 0.0% | Zero duplicate records per session/ISIN |
| **OHLC or Volume Data Conflicts** | **0** | 0.0% | All raw records contain valid positive prices and non-negative volume |

---

## 3. Breakdown by Historical Symbol and Instrument Identifier

The 545 pairs involve exactly **9 instrument UUIDs** (representing 8 ticker symbols):

| Symbol | Instrument UUID | Authoritative ISIN | Missing Sessions | Period Covered | Primary Raw Series | Root Cause Classification |
|---|---|---|---|---|---|---|
| **ADANIPOWER** | `ea56179e-a084-4ab5-92a8-179cbf312450` | `INE814H01011` | 133 | 2022-08-25 to 2024-03-15 | `BE` (133 / 133) | Potential source-data defect (Series `BE` dropped by extractor) |
| **AWL** | `1bc2468e-07bc-4927-a445-3c367f685409` | `INE699H01024` | 9 | 2022-08-01 to 2022-08-12 | `BE` (9 / 9) | Potential source-data defect (Series `BE` dropped by extractor) |
| **COCHINSHIP (Post-Split)** | `b2073734-a39b-43a7-9115-5c38165564b6` | `INE704P01025` | 64 | 2024-09-25 to 2024-12-27 | `BE` (64 / 64) | Potential source-data defect (Series `BE` dropped by extractor) |
| **PATANJALI** | `29df4b21-1625-4829-b332-7b98926a0e0f` | `INE619A01035` | 130 | 2022-05-25 to 2022-11-30 | `BE` (130 / 130) | Potential source-data defect (Series `BE` dropped by extractor) |
| **RPOWER** | `995c50b6-41df-46e0-9306-87fa571f9997` | `INE614G01033` | 41 | 2024-01-31 to 2024-03-28 | `BE` (41 / 41) | Potential source-data defect (Series `BE` dropped by extractor) |
| **SUZLON** | `79af0c9a-e82c-41a0-b84d-e65f31605c64` | `INE040H01021` | 134 | 2023-10-10 to 2024-05-31 | `BE` (134 / 134) | Potential source-data defect (Series `BE` dropped by extractor) |
| **HDFC** | `327cf34f-a1b9-4fff-b46c-236de0b6200b` | `INE001A01036` | 13 | 2023-07-13 to 2023-07-31 | `NONE` (0 / 13) | Verified explained (Merger delisting; stale universe schedule) |
| **MINDTREE** | `04f442e6-f59f-4fc4-9727-5618b37ba603` | `INE018I01017` | 6 | 2022-11-23 to 2022-11-30 | `NONE` (0 / 6) | Verified explained (Merger delisting; stale universe schedule) |
| **COCHINSHIP (Pre-Split)** | `fb06e178-df18-4415-b446-6809e5959e47` | `INE704P01017` | 15 | 2024-01-10 to 2024-01-31 | `NONE` (0 / 15) | Verified explained (ISIN stock-split transition; stale universe) |

---

## 4. Verification of the Legacy Extraction Root Cause

The exact code path causing the 511-pair omission was audited in `Signal-Atlas`:

1. **Universe Selection Policy (`BE_EQ` Permitted)**:
   [`src/signal_atlas/universe/models.py#L43`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas/src/signal_atlas/universe/models.py#L43):
   ```python
   permitted_series: Tuple[str, ...] = Field(default=("EQ", "BE"), description="Allowed cash equity series")
   ```
   When the Point-in-Time universe was generated, the selection engine executed:
   ```sql
   SELECT ... WHERE series = ANY(ARRAY['EQ', 'BE'])
   ```
   Scrips trading under `BE` were explicitly verified as liquid and included in the universe.

2. **Snapshot Price Bar Extraction (`EQ` Filter Hardcoded)**:
   [`src/signal_atlas/backtest/pipeline.py#L338`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas/src/signal_atlas/backtest/pipeline.py#L338):
   ```python
   h = get_point_in_time_adjusted_history(inst_id, end_date, db=db)
   ```
   The caller passed no `series` argument.
   In [`src/signal_atlas/quality/adjustment.py#L441-L473`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas/src/signal_atlas/quality/adjustment.py#L441-L473):
   ```python
   def get_point_in_time_adjusted_history(
       instrument_id: str,
       as_of_date: datetime.date,
       series: str = "EQ",  # HARDCODED DEFAULT
       ...
   ):
       query = select(DailyPriceRaw).where(...)
       if series:
           query = query.where(DailyPriceRaw.series == series)
   ```
   Because `series="EQ"` defaulted, the query discarded all records where `DailyPriceRaw.series == 'BE'`.
3. **Causality Confirmed**:
   The universe engine deemed `BE` scrips eligible, but the snapshot extractor silently filtered them out.

---

## 5. Audit of the 34 Stale Membership Cases

### 1. HDFC (`327cf34f-a1b9-4fff-b46c-236de0b6200b`) — 13 Sessions
* Effective July 13, 2023, Housing Development Finance Corporation (HDFC) merged into HDFC Bank.
* Inspection of `data/raw/2023/cm13JUL2023bhav.csv.zip` proves that HDFC was delisted by NSE and ceased trading on July 13, 2023.
* The Point-in-Time universe schedule retained HDFC through July 31, 2023.
* **Finding**: Pure stale universe schedule defect; no price omission occurred because the scrip did not exist.

### 2. MINDTREE (`04f442e6-f59f-4fc4-9727-5618b37ba603`) — 6 Sessions
* Mindtree merged with L&T Infotech to form LTIMindtree effective November 23, 2022.
* Inspection of `data/raw/2022/cm23NOV2022bhav.csv.zip` proves that MINDTREE ceased trading on November 23, 2022.
* The universe schedule retained MINDTREE through November 30, 2022.
* **Finding**: Pure stale universe schedule defect.

### 3. COCHINSHIP Pre-Split (`fb06e178-df18-4415-b446-6809e5959e47`) — 15 Sessions
* On 2024-01-10, Cochin Shipyard executed a 2:1 stock split, transitioning from old ISIN `INE704P01017` to new ISIN `INE704P01025`.
* Pre-split UUID `fb06e178...` traded up to 2024-01-09. Post-split UUID `b2073734...` began trading on 2024-01-10.
* The universe schedule retained the pre-split UUID for 15 sessions through January 31, 2024.
* **Finding**: Stale universe membership on an ISIN transition boundary.

---

## 6. Proposed Exchange-Series Data Contract

To prevent series conflation in `Signal-Atlas-Core`, the contract in [`src/signal_core/contracts/exchange_series.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py) is adopted:

1. **Explicit `ExchangeSeries` Enum**:
   `EQ` (Normal rolling cash equity), `BE` (Trade-to-Trade gross delivery), `BZ` (Surveillance Trade-to-Trade), `SM` (SME segment), `OTHER`, `UNKNOWN`.
2. **Separation of Raw Data from Research Eligibility**:
   - `PriceBar` remains pure numerical OHLCV data.
   - `ExchangeSessionObservation` attaches the authoritative `series` and `isin`.
   - `SeriesEligibilityPolicy` governs research filtering:
     - `DEFAULT_EQUITY_ONLY_POLICY`: Permits only `EQ` (standard cash equities).
     - `DEFAULT_PERMITTED_CASH_POLICY`: Permits `EQ` and `BE` with documented delivery assumptions.
3. **No Silent Series Conversion**:
   `BE` is never silently mapped to `EQ`. Intraday shorting, margin netting, and 20% price bands must not be assumed for `BE` securities.

---

## 7. Proposed Missing-Session Continuity Policy

To prevent feature engines (EMA, ATR, RSI) from silently computing indicators across discontinuous gaps:

1. **`PriceSeriesGapType` Enumeration**:
   - `SERIES_FILTER_OMISSION`: Scrip traded on exchange, but was omitted by an extraction filter.
   - `PRE_LISTING_OR_POST_DELISTING`: Session falls before listing or after delisting/merger.
   - `ISIN_TRANSITION_REPLACED`: Superseded by a new corporate ISIN.
   - `TRADING_HALT_OR_SUSPENSION`: Listed, but zero exchange trading occurred.
   - `UNEXPLAINED_MISSING_RECORD`: Missing without identifiable record (fails closed).
2. **Fail-Closed Continuity Invariant**:
   A rolling indicator requiring $N$ sessions must verify that the underlying dates represent consecutive calendar trading sessions. If a `SERIES_FILTER_OMISSION` or `UNEXPLAINED_MISSING_RECORD` occurs, the calculation must invalidate or reset its lookback window rather than bridging the gap.

---

## 8. Artifacts Created in `Signal-Atlas-Core`

1. [`scripts/reconcile_bhavcopy_series.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/scripts/reconcile_bhavcopy_series.py): Standalone, reproducible reconciliation engine.
2. [`reports/reconciliation/bhavcopy_545_reconciliation.csv`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/reconciliation/bhavcopy_545_reconciliation.csv): Exhaustive row-level audit of all 545 pairs across 21 columns.
3. [`src/signal_core/contracts/exchange_series.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/src/signal_core/contracts/exchange_series.py): Data contracts for exchange series, eligibility policies, and continuity audits.
4. [`tests/unit/test_bhavcopy_reconciliation.py`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/tests/unit/test_bhavcopy_reconciliation.py): Synthetic unit tests covering legacy and unified Bhavcopy parsing and series policies.
5. [`reports/reconciliation/bhavcopy_series_policy_report.md`](file:///C:/Users/DEB/Full%20Stack%20Documentation/Practice%20Projects/Signal-Atlas-Core/reports/reconciliation/bhavcopy_series_policy_report.md): This report.

