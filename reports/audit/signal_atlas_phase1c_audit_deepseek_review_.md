# Signal Atlas Core — Independent Progress Audit (Phase 1A → 1C)

**Audit date:** 2026-11-11
**Auditor role:** Indian senior quantitative researcher (external review)
**Scope:** Verify the claims in `CURRENT_STAGE_OF_WORK.md` and `WHAT_WE_ARE_BUILDING.md` against the actual code, tests, committed artifacts and statutory rate sources.
**Repository state audited:** commit `84c7501` (`feat(features): complete Phase 1C pure indicator formulas and subsegment engine`) with 4 files dirty (+1 line each, trailing newline only).
**Code changes made by this audit:** none. This document is read-only review output.

---

## 1. Method & Environment

Nothing below is inferred from the documentation. Every status is derived from an executed command, and each finding states how it was established.

| Item | Value |
|---|---|
| Interpreter | CPython 3.13.5 (win32) |
| Test runner | pytest 8.3.4, config `pyproject.toml` |
| Suite result | **79 collected, 79 passed, exit 0, 0.44s** (`python -m pytest -q`) |
| Warning policy | `filterwarnings = ["error"]` — warnings are hard failures |
| Static review | All 22 `.py` files, `configs/go_no_go_criteria.yaml`, both reconciliation artifacts |
| Dynamic review | 5 targeted probes against the feature engine and contracts (Appendix A reproduces them verbatim) |
| Statutory verification | NSE circulars `NSE/FA/56129` (24-Mar-2023) and `NSE/FA/64323` (27-Sep-2024); SEBI uniform-charge circular `SEBI/HO/MRD/TPD-1/P/CIR/2024/92` (01-Jul-2024) |

Status vocabulary used in this document:

- `VERIFIED` — claim reproduced by an executed check.
- `CONTRADICTED` — a reproducible check shows the claim does not hold.
- `PARTIAL` — true for a subset of the claim's scope, with the boundary stated.
- `NOT RUN` — the check requires data or an artifact absent from this repository; no conclusion is drawn.

---

## 2. Documentation Claims — Verification Table

| # | Claim in `CURRENT_STAGE_OF_WORK.md` | Status | Evidence |
|---|---|---|---|
| C1 | "79 passed in 0.69s (100% pass rate, zero warnings)" | `VERIFIED` (timing differs) | 79 passed in 0.44s; warnings promoted to errors by config |
| C2 | Phase 1A `PriceBar` enforces Decimal-only, finite, positive, coherent OHLC, rejects `float`/`bool` | `VERIFIED` | `contracts/price_bar.py`, validated at construction |
| C3 | Phase 1A `UniverseSchedule` is point-in-time, sorted, immutable, rejects duplicates/survivorship-style mutation | `VERIFIED` | `contracts/universe.py`, `MappingProxyType` + tuple freeze |
| C4 | Phase 1A deterministic fingerprints `DATA-CTNT-V2` / `UNIV-SCHED-V1` | `VERIFIED` | `contracts/provenance.py`; golden vectors in `tests/unit/test_provenance.py` |
| C5 | Phase 1B series reconciliation artifacts committed | `VERIFIED` | `reports/reconciliation/bhavcopy_545_reconciliation.csv` (138 KB), `bhavcopy_series_policy_report.md` |
| C6 | `EQ`→`BE` transition preserves continuity; eligibility is decoupled from price history | `VERIFIED` | `partition_into_continuous_subsegments` keeps a transition inside one segment; `APPROVED_EQ_ONLY_POLICY` gates entry only |
| C7 | "Zero silent forward-filling" | `VERIFIED` | Missing calendar dates are absent from result maps / return `None` |
| C8 | "Zero cross-gap leakage: indicators warm up afresh after any missing session gap; state never spills across non-contiguous dates" | `CONTRADICTED` | Finding **F-01** — `relative_strength_50` spans gaps |
| C9 | Feature engine integrates with the Phase 1B enriched records (`ExchangeSessionObservation`) | `CONTRADICTED` | Finding **F-02** — `AttributeError` on that type |
| C10 | "Fail-closed verification" / "refuses to compute lookbacks across unexplained gaps" | `PARTIAL` | Finding **F-03** — off-calendar bars are silently dropped, not refused |
| C11 | Snapshot SHA-256 `502c6424…` and `DATA-CTNT-V2-659aea8f…` reproduced | `NOT RUN` | `scripts/verify_historical_snapshot.py` hardcodes an absolute path into the legacy repo; the snapshot is not present here |
| C12 | 545 missing pairs = 511 `BE`-filter omissions + 34 delisting/ISIN cases | `NOT RUN` (artifact reviewed) | Requires the 743 raw Bhavcopy ZIPs under `data/raw/`; rerun not possible in this repository |
| C13 | "Authoritative criteria committed in `configs/go_no_go_criteria.yaml`" | `PARTIAL` | File exists but is **inert**: no code, script or test reads it (grep across `src/`, `scripts/`, `tests/` returns zero matches). Also contains wrongly-sourced rates — Section 5 |
| C14 | Phase 1C complete | `PARTIAL` | 11 of 12 engine features are correctly subsegment-bounded; RS is not. See Section 3 |
| C15 | `HOLDOUT_UNLOCK` absent, holdout sealed | `VERIFIED` (absence check) | No holdout partition, unlock token or out-of-sample artifact exists in the tree |

---

## 3. Defects — P1 (research-output correctness)

### F-01 — `relative_strength_50` leaks across missing sessions

**Location:** `src/signal_core/features/engine.py:201-205` (computation), `src/signal_core/features/indicators.py:403-448` (maths)

**Mechanism.** Every other feature in `compute_standard_features_for_instrument` is routed through `compute_indicator_on_subsegments` (`engine.py:131+`). Relative strength is the sole exception:

```python
# engine.py:201-205
rs_50_map: Dict[datetime.date, Optional[Decimal]] = {}
if benchmark_bars:
    rs_values = compute_relative_strength(sorted_bars, benchmark_bars, lookback_sessions=50)
    for bar, val in zip(sorted_bars, rs_values):
        rs_50_map[bar.trade_date] = val
```

`compute_relative_strength` then indexes by **record position**, not calendar session (`indicators.py:432`):

```python
past_date = stock_dates[i - lookback_sessions]
```

So the "50-session lookback" is really "the 50th preceding *record*". Across any missing session the true horizon silently stretches to 51+ sessions, and the value is published with no flag.

**Reproduction (Probe 2, Appendix A).** 60-session calendar, session index 10 removed, benchmark present on all 60 sessions:

```
sma_20 at first bar after gap : None      <- correct: segment restarted
rs_50  at first bar after gap : not None  <- spans the missing session
non-None rs_50 values returned for post-gap bars: 9
```

All 9 of those values have a lookback window that straddles the missing session (record `i-50` falls on the pre-gap side). The first post-gap bar happens to return `None` only because its record index is 10 < 50 — the correctness is incidental, not enforced.

**Impact.** This is precisely the failure mode `AGENTS.md` §6.3 and `WHAT_WE_ARE_BUILDING.md` Pillar 5 exist to prevent. Any momentum, cross-sectional ranking or RS-vs-benchmark filter built on `relative_strength_50` inherits contaminated values whenever a constituent has a `BE`-filter omission, a suspension, or a holiday-list mismatch. Given the Phase 1B finding that 511 of 545 missing pairs are `BE` filter omissions, such gaps are **common in this dataset**, not hypothetical.

**Severity: P1.** Contaminates reported feature values; invalidates C8.

---

### F-02 — `compute_relative_strength` cannot accept `ExchangeSessionObservation`

**Location:** `src/signal_core/features/indicators.py:426,439`

```python
bench_by_date = {b.trade_date: b.close for b in benchmark_records}   # line 426
s_curr = stock_records[i].close                                      # line 439
```

`ExchangeSessionObservation` exposes OHLCV only through `.price_bar`; it has no `.close`. The declared signature is `Sequence[Union[PriceBar, ExchangeSessionObservation]]`, and every other indicator normalises via `extract_price_series`.

**Reproduction (Probe 1):**

```
FAILED: AttributeError: 'ExchangeSessionObservation' object has no attribute 'close'
```

**Impact.** `SubsegmentIndicatorEngine.compute_standard_features_for_instrument` raises the moment it is fed the enriched observation records introduced by Phase 1B.3 — i.e. the layer that carries the series code and ISIN, and the only layer that can support eligibility gating downstream. Phase 1B and Phase 1C are not integrated on the RS path. The defect survives the suite because `test_compute_relative_strength_alignment` uses raw `PriceBar` objects only.

**Severity: P1.** Blocks the intended data path; invalidates C9.

---

### F-03 — Subsegment partitioning silently discards off-calendar bars

**Location:** `src/signal_core/contracts/exchange_series.py:457-500`

The partitioner iterates the *calendar* and appends only records whose date is found in it (`line 488`). Any record whose `trade_date` is absent from `expected_calendar_sessions` is dropped with no gap record, no exception, and no return-channel for diagnostics.

**Reproduction (Probe 3):** 3 input bars, middle bar on a date missing from the supplied calendar:

```
input bars: 3  ->  bars retained in segments: 2
segments: [['2022-01-03', '2022-01-05']]
```

**Impact.** A single stale holiday list or an omitted special session (e.g. a Muhurat session, a one-off Saturday session) silently deletes real exchange observations and shortens every downstream window. This contradicts the fail-closed invariant (C10) — the correct behaviour is to raise or record `UNEXPLAINED_MISSING_RECORD`, never to drop data. The function also does not validate that the calendar is sorted and duplicate-free, although its output is only correct if both hold.

**Severity: P1.** Silent data loss in a layer stated to be fail-closed.

---

## 4. Defects — P2 / P3

| ID | Finding | Location | Severity |
|---|---|---|---|
| F-04 | `assert` used as the output-length guard: `assert len(seg_values) == len(segment)`. Under `python -O` the invariant disappears. Must be `raise IndicatorValidationError`. | `engine.py:122` | P2 |
| F-05 | `compute_weekly_trend` has zero call coverage — its only occurrence in `tests/unit/test_indicators.py` is the import (line 35). | `indicators.py:564` | P2 |
| F-06 | Weekly aggregation bypasses continuity entirely: 12 records spanning 12 ISO weeks yield 12 weekly bars, with no gap detection, so a 10-week EMA can span months of missing weeks. Duplicate dates are also not rejected. (Probe 4) | `indicators.py:474-562` | P2 |
| F-07 | `validate_series_continuity` collapses duplicate records last-wins (`records_by_date[item.trade_date] = item`) while `available_records_count` reports the raw input length. The loader rejects duplicates; the validator the engine calls does not. | `exchange_series.py:339-341` | P2 |
| F-08 | Two independent implementations of the same `DATA-CTNT-V2` digest, with no parity test asserting they agree on identical input. Duplicate-engine risk under `AGENTS.md` §7.4. | `provenance.py:63`, `legacy_compat.py:49` | P2 |
| F-09 | `load_dataset_from_dict` promotes JSON floats via `Decimal(str(v))` and truncates volume via `int(v)`. Probe 5: `105.2` → `Decimal('105.2')`, `10.9` → `10`. The parallel loader `historical_snapshot._parse_decimal_field` correctly **rejects** floats (`historical_snapshot.py:113`). Two loaders, two numeric policies, and the lenient one is the exported one. | `dataset.py:188-255` | P2 |
| F-10 | Fingerprint is representation-sensitive, not logical: `canonicalize_decimal` returns `str(value)` (`provenance.py:60`), so `Decimal("100.50")` and `Decimal("100.5")` hash differently. Any reformat invalidates recorded dataset identity. Either canonicalise (`normalize()`) or stop calling it "logical". | `provenance.py:44-60` | P3 |
| F-11 | `InstrumentTechnicalFeatures` carries no series code, ISIN or eligibility marker, so feature rows cannot be bound to `SeriesEligibilityPolicy`. Nothing today prevents a `BE` row from reaching a signal. | `engine.py:39-60` | P3 (Phase 1D gate) |
| F-12 | The full continuity audit is re-executed once per indicator — 12× per instrument in the standard suite. Acceptable at 79 tests; O(indicators × sessions × instruments) at 500 names × 750 sessions. | `engine.py:77-131` | P3 (performance) |

No finding was resolved by weakening a test, and none of the 79 tests was modified during this audit.

---

## 5. Statutory Cost Schedule Audit (`configs/go_no_go_criteria.yaml`)

The file is inert (C13) and contains two sourcing errors plus two structural defects. Rates below are for NSE cash equity, the segment this engine targets.

| Key | Committed value | Correct value for 2022–2024 | Status |
|---|---|---|---|
| `ipft_charge_rate` (line 62) | `0.0000001` = ₹1 per crore | ₹0.01 per crore before 01-Apr-2023; **₹10 per crore from 01-Apr-2023** (`NSE/FA/56129`) | **WRONG** — 10× too low for the post-Apr-2023 regime, and wrong (too high) for the preceding window |
| `exchange_turnover_charge_rate` (line 51) | `0.0000325` = ₹325 per crore | ₹325 per crore to 30-Sep-2024; **₹297 per crore from 01-Oct-2024** (`NSE/FA/64323`, following `SEBI/HO/MRD/TPD-1/P/CIR/2024/92`) | **PARTIAL** — correct for 34 of 36 months; Q4-2024 mispriced |
| `gst_rate` base (line 58) | brokerage + exchange + SEBI | NSE levies 18% GST on the IPFT contribution as well | **GAP** — IPFT excluded from the GST base |
| `stt_delivery_rate` | `0.0010` | 0.1% delivery, both legs | Correct |
| `stt_intraday_sell_rate` | `0.00025` | 0.025% intraday sell | Correct |
| `sebi_turnover_charge_rate` | `0.000001` | ₹10 per crore | Correct |
| `stamp_duty_delivery_buy_rate` / `stamp_duty_intraday_buy_rate` | `0.00015` / `0.00003` | 0.015% / 0.003% on buy | Correct |
| `max_volume_participation_cap` | `0.03` | Mandated band 2.5%–5.0% | Correct |
| `min_execution_latency_sessions` | `1` | T+1 | Correct |
| `prohibit_buy_at_upper_circuit` / `prohibit_sell_at_lower_circuit` | `true` | Required invariant | Correct |

**Structural defect S-1 — no effective-dating.** A single static rate cannot price a 2022–2024 sample that spans two NSE charge revisions and one IPFT revision. The schedule needs `(from_date, to_date)` rows resolved per session. Without it, the Phase 1D cost engine is anachronistic by construction, which is a `AGENTS.md` §7.2 violation independent of the rupee magnitude.

**Structural defect S-2 — rates stored as binary floats.** `brokerage_per_order_inr: 20.0`, `stt_delivery_rate: 0.0010`, `gst_rate: 0.18`. Any Decimal cost engine must ingest these as `Decimal(str(float))` — the exact rounding path `AGENTS.md` §6.4 bans. Store them as strings (`"0.0010"`) or integer paise.

**Structural defect S-3 — no consumer.** With zero code reading the file, `AGENTS.md` §9.2 ("verdicts generated from committed thresholds") is not yet satisfiable, and nothing prevents the file from drifting further from the circulars.

---

## 6. Test Coverage Gaps

The suite is green because the two broken paths are never entered. Coverage gaps that matter:

| Area | Evidence | Risk |
|---|---|---|
| `relative_strength_50` through the engine | 0 assertions on `relative_strength_50` across `tests/unit/` | F-01 undetected |
| `ema_200` through the engine | 0 assertions on `ema_200` | Warm-up boundary unverified |
| `compute_relative_strength` with `ExchangeSessionObservation` | test uses `PriceBar` only | F-02 undetected |
| `compute_weekly_trend` | imported, never called | Entire function unverified |
| Off-calendar bar handling in partitioning | no test | F-03 undetected |
| Exceptions under `python -O` | no test runs the interpreter with `-O` | F-04 undetected |
| Fingerprint parity between the two digest implementations | no test | F-08 drift unverified |
| `go_no_go_criteria.yaml` against the NSE rate table | no test | Section 5 errors undetected |

---

## 7. NOT RUN Register (fail-closed disclosure)

| Check | Why not run |
|---|---|
| Historical snapshot SHA-256 / content fingerprint / universe fingerprint reproduction | Snapshot artifact lives outside this repository; `verify_historical_snapshot.py` hardcodes an absolute path to the legacy project |
| 545-pair Bhavcopy reconciliation re-execution | 743 raw Bhavcopy ZIPs under `data/raw/` are not present; the committed CSV and policy report were reviewed, not recomputed |
| Any strategy performance, DSR, Haircut Sharpe, drawdown or walk-forward metric | No strategy, execution engine or ledger exists yet (Phase 1D/1E/2 outstanding). **No PASS/FAIL or GO/NO-GO verdict is expressed in this document**, because none can be computed |
| Cost-model rupee impact of the Section 5 rate errors | No cost engine exists to evaluate; the errors are established against the circulars, not quantified in PnL |

---

## 8. Phase Status Assessment

| Phase | Documented | Audit finding |
|---|---|---|
| 0 — Legacy assessment | Completed | `VERIFIED` via the committed reconciliation report narrative; not independently re-audited |
| 1A — Contracts | Completed | `VERIFIED` |
| 1B — Snapshot / Bhavcopy / series continuity | Completed | `VERIFIED` for the contract layer and artifacts; empirical counts `NOT RUN` |
| 1C — Feature & indicator foundation | Completed | `PARTIAL`: 11 of 12 engine features subsegment-bounded; RS contaminated (F-01), unusable on observations (F-02), partitioner drops data silently (F-03) |

`CURRENT_STAGE_OF_WORK.md` therefore overstates Phase 1C. The correct description is: *substantially complete, with three P1 defects on the relative-strength and partitioning paths, and two documented invariants (C8, C9) that the code does not satisfy.*

Phase 1D (execution + statutory cost engine) should not begin until F-01, F-02 and F-03 are closed. A cost engine layered beneath a feature layer that misreports lookback horizons will produce a GO verdict whose inputs are not comparable across the sample.

---

## 9. Recommended Remediation Order

Each item states its own verification criterion, per `AGENTS.md` §4.

1. **F-01 / F-02 — route RS through `compute_indicator_on_subsegments`; normalise record access via `extract_price_series`.**
   *Verify:* a regression test with a mid-series gap must return `None` for every RS value whose 50-session window would cross the gap; a test must pass `ExchangeSessionObservation` inputs and reproduce the `PriceBar` result exactly.
2. **F-03 — make off-calendar bars fail closed.**
   *Verify:* a test supplying a bar on a date absent from the calendar must raise, not silently drop; a companion test asserts sorted/unique calendar validation.
3. **F-04 — replace the `assert` guard with `IndicatorValidationError`.**
   *Verify:* the mismatch test passes under `python -O`.
4. **F-06 / F-05 — weekly path: reject duplicate dates, detect non-consecutive ISO weeks, and test `compute_weekly_trend`.**
   *Verify:* a missing-week fixture either raises or returns an explicit gap marker; bullish/bearish/insufficient-history branches each have an assertion.
5. **Section 5 — effective-dated statutory schedule with corrected IPFT and exchange rates, IPFT in the GST base, string-typed decimals, and a loader that reads the file.**
   *Verify:* a table-driven test asserts each rate resolves correctly on 2023-03-31 vs 2023-04-01 and 2024-09-30 vs 2024-10-01.
6. **F-09 / F-08 / F-10 — one numeric policy and one digest implementation.**
   *Verify:* `load_dataset_from_dict` rejects `float` prices and non-integral volume; a parity test asserts the two digests agree, or the duplicate is removed.
7. **C13 — make the criteria file authoritative in code**, so §9.2 verdicts can be computed rather than asserted.
8. **Correct `CURRENT_STAGE_OF_WORK.md`** so C8, C9 and C14 reflect the above.

---

## Appendix A — Reproducible Probe Script

Executed from the repository root. Output quoted in Sections 3 and 4 matches the run of 2026-11-11.

```python
import datetime, sys
sys.path.insert(0, 'src')
from decimal import Decimal
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.exchange_series import (
    ExchangeSessionObservation, ExchangeSeries, PriceSeriesContinuityValidator)
from signal_core.features.indicators import compute_relative_strength, aggregate_daily_to_weekly
from signal_core.features.engine import SubsegmentIndicatorEngine

def bar(d, c, inst="X"):
    c = Decimal(c)
    return PriceBar(instrument_id=inst, trade_date=d, open=c, high=c + 1, low=c - 1, close=c, volume=100)

def obs(d, c, inst="X"):
    return ExchangeSessionObservation(
        instrument_id=inst, trade_date=d, raw_series_code="EQ",
        series_classification=ExchangeSeries.EQ, isin="INE000A01001", price_bar=bar(d, c, inst))

d0 = datetime.date(2022, 1, 3)
days = [d0 + datetime.timedelta(days=i) for i in range(5)]

# Probe 1 - F-02
try:
    compute_relative_strength([obs(days[i], str(100 + i * 10)) for i in range(3)],
                              [obs(days[i], str(1000 + i * 10), "BENCH") for i in range(3)], 2)
except Exception as e:
    print("PROBE1:", type(e).__name__, e)      # AttributeError: ... no attribute 'close'

# Probe 2 - F-01
cal = [d0 + datetime.timedelta(days=i) for i in range(60)]
gap = cal[10]
prices = [bar(d, str(100 + i)) for i, d in enumerate(cal) if d != gap]
bench = [bar(d, str(1000 + i), "BENCH") for i, d in enumerate(cal)]
feats = SubsegmentIndicatorEngine.compute_standard_features_for_instrument(cal, prices, benchmark_bars=bench)
by = {f.trade_date: f for f in feats}
print("PROBE2 sma_20 after gap:", by[cal[11]].sma_20)                    # None
print("PROBE2 rs_50  after gap:", by[cal[11]].relative_strength_50)      # None by luck only
print("PROBE2 post-gap rs_50 populated:", sum(1 for f in feats[11:] if f.relative_strength_50 is not None))  # 9

# Probe 3 - F-03
stray = d0 + datetime.timedelta(days=1)
bars = [bar(cal[0], "100"), bar(stray, "101"), bar(cal[2], "102")]
segs = PriceSeriesContinuityValidator.partition_into_continuous_subsegments([cal[0], cal[2]], bars)
print("PROBE3 retained:", sum(len(s) for s in segs), "of", len(bars))    # 2 of 3

# Probe 4 - F-06
wk = [d0 + datetime.timedelta(weeks=i) for i in range(12)]
print("PROBE4 weekly bars:", len(aggregate_daily_to_weekly([bar(d, str(100 + i)) for i, d in enumerate(wk)])))  # 12

# Probe 5 - F-09
from signal_core.contracts.dataset import load_dataset_from_dict
payload = {
    "metadata": {"dataset_id": "D", "schema_version": "v1.0", "price_convention": "UNADJUSTED_RAW",
                 "start_date": "2022-01-03", "end_date": "2022-01-03", "session_count": 1,
                 "instrument_count": 1, "total_instrument_records": 1, "total_price_records": 1,
                 "source_identity": "X", "content_fingerprint": "F"},
    "prices_by_instrument": {"A": [{"trade_date": "2022-01-03", "open": 100.1, "high": 110.3,
                                    "low": 99.7, "close": 105.2, "volume": 10.9}]},
    "universe_by_date": {"2022-01-03": ["A"]},
}
_, pbi, _, _ = load_dataset_from_dict(payload)
print("PROBE5 close/volume:", repr(pbi["A"][0].close), pbi["A"][0].volume)  # Decimal('105.2') 10
```

## Appendix B — Statutory Rate Sources

| Instrument | Reference |
|---|---|
| IPFT, cash market: ₹0.01/crore → ₹10/crore effective 01-Apr-2023 | NSE circular `NSE/FA/56129`, 24-Mar-2023 |
| Cash transaction charges: ₹3.25/lakh (₹325/crore) up to 30-Sep-2024 | NSE circular `NSE/FA/56129`, 24-Mar-2023 |
| Cash transaction charges: ₹297/crore from 01-Oct-2024, uniform per-member structure | NSE circular `NSE/FA/64323`, 27-Sep-2024; SEBI `SEBI/HO/MRD/TPD-1/P/CIR/2024/92`, 01-Jul-2024 |
| 18% GST applicable to IPFT contribution in addition to brokerage, exchange and SEBI charges | NSE charge circulars; member contract-note schedules |
| STT 0.1% delivery both legs; 0.025% intraday sell; SEBI turnover ₹10/crore; stamp duty 0.015% delivery buy, 0.003% intraday buy | Finance Act / Indian Stamp Act schedules as applied by NSE members |

Rates are periodically revised. Any schedule committed for a historical backtest must be effective-dated and cited to the governing circular, per `AGENTS.md` §7.2 and §9.2.

---

## 10. Re-audit After Remediation — Computed Phase Gate

**Commit audited:** `85b5e18` — *"remediate all DeepSeek audit findings F-01 through F-12 and Section 5"*
**Environment:** Python 3.13.5, pytest 8.3.4, `filterwarnings = ["error"]`, `PYTHONPATH=src`
**Suite result (measured):** `91 passed in 0.50s`, exit 0
**Independent probes (measured):** 17 executed, **15 PASS / 2 FAIL** — script identical to Appendix A plus re-audit cases.

### 10.1 Finding closure, verified by execution

| ID | Original finding | Evidence from this re-audit run | Status |
|---|---|---|---|
| F-01 | `relative_strength_50` leaks across missing sessions | 59-bar gap probe: 0 non-None RS. 130-bar probe: first post-gap RS appears exactly at the 51st bar of the new subsegment and equals standalone segment computation (`2022-03-05`, identical=True). Pre-gap segment: 10 bars, all None. | **CLOSED** |
| F-02 | `compute_relative_strength` crashes on `ExchangeSessionObservation` | Observation and PriceBar inputs return identical values (`0.0180`) | **CLOSED** |
| F-03 | Partitioning silently discards off-calendar bars | `ValueError` ("off-calendar date ... silent data omission") | **CLOSED** |
| F-04 | `assert` guard in `engine.py` | Engine contains no `assert`; length mismatch raises `IndicatorValidationError` and survives `python -O` semantics. Five defensive `assert`s remain in `indicators.py:537,538,565,574,575` (see R-3). | **CLOSED** (residual R-3) |
| F-05 | `compute_weekly_trend` imported but never called | `test_finding_f05_f06_weekly_trend_and_gap_detection` covers bullish, bearish, short-history; probes agree | **CLOSED** |
| F-06 | Weekly aggregation bypasses calendar continuity | Whole-week gap → `(close, None, None)`. Intra-week missing session (4 of 5 sessions in week 9) → `ema=136.500000, trend=True`, emitted silently. | **PARTIAL** (R-1) |
| F-07 | Validator silently collapses duplicate dates | `validate_series_continuity` raises on duplicate date | **CLOSED** |
| F-08 | Two duplicate fingerprint engines | Clean and legacy digests agree (`a7a2c9790f` both) on the probed vector; both implementations are retained, so parity is test-enforced rather than structurally guaranteed. | **MITIGATED**, not unified |
| F-09 | Float promotion and volume truncation in `load_dataset_from_dict` | `close=100.5` → `DatasetValidationError`; `volume="10.9"` → `DatasetValidationError` | **CLOSED** |
| F-10 | Digest sensitive to Decimal representation | `Decimal("100.5")` → `…a2c9790f`; `Decimal("100.50")` → `…e2491936` for identical economic data | **OPEN** (R-2) |
| F-11 | Features lack series/eligibility fields | `raw_series_code=EQ`, `series_classification=ExchangeSeries.EQ`, ISIN carried through | **CLOSED** |
| F-12 | Continuity audit re-run per indicator | Single partition + single upfront audit per instrument | **CLOSED** |

### 10.2 Statutory schedule — verified against primary circulars

| Component | Config value | Verification | Status |
|---|---|---|---|
| STT delivery / intraday sell | `0.0010` / `0.00025` | 0.1% / 0.025% | **CORRECT** |
| SEBI turnover | `0.000001` | ₹10 per crore | **CORRECT** |
| Stamp duty delivery buy / intraday buy | `0.00015` / `0.00003` | 0.015% / 0.003% | **CORRECT** |
| GST | `0.18`, base includes `ipft` | 18% on brokerage + exchange + SEBI + IPFT | **CORRECT** |
| `NSE/FA/46730` (≤ 2023-03-31) | ₹345/cr, ₹0.01/cr | Slab-1 rate | **CORRECT as slab-1** (R-4) |
| `NSE/FA/56129` (2023-04-01) | ₹325/cr, ₹10/cr | 6% rollback | **CORRECT** |
| `NSE/FA/61137` (2024-04-01) | ₹322/cr, ₹10/cr | Circular dated 2024-03-14, eff. 2024-04-01 | **CORRECT as slab-1** (R-4) |
| `NSE/FA/64323` (2024-10-01) | ₹297/cr, ₹10/cr | Circular dated 2024-09-27, SEBI uniform rate | **CORRECT** |
| `NSE/FA/73061` (2026-03-01) | ₹306.99/cr, ₹0.01/cr | Circular dated 2026-02-27; total ₹307/cr each side | **CORRECT** |

Schedule contiguity: **PASS** (no gaps or overlaps across all five rows). Date resolution on the current session `2026-11-11` → `NSE/FA/73061`, total ₹307/cr. A query before 2021-01-01 raises `CriteriaValidationError` rather than guessing — fail-closed. The config is no longer inert: `load_go_no_go_criteria()` parses it into Decimal-typed immutable contracts.

### 10.3 Residual findings

| ID | Severity | Finding | Impact on Phase 1D |
|---|---|---|---|
| R-1 | P3 | `compute_weekly_trend` accepts no trading calendar, so a missing session *inside* a week is invisible: the weekly close becomes the last available session and the EMA smooths across it. Detail: probe F-06b returned `ema=136.500000, trend=True` for a week missing its third session. | None — Phase 1D consumes daily bars only. Must be closed before any weekly-trend signal is wired into a strategy. |
| R-2 | P3 | `canonicalize_decimal` uses `str(Decimal)`, so `100.5` and `100.50` hash differently. Two datasets with identical economics, differing only in stored scale, produce different `DATA-CTNT-V2` digests. | None, provided fingerprints are treated as byte-identity of the stored panel, not economic equivalence. Needs an explicit statement in the provenance contract. |
| R-3 | P3 | Five defensive `assert`s remain in `aggregate_daily_to_weekly`; they vanish under `-O`. The `python -O` suite exits 1 via `filterwarnings = ["error"]`, so optimized runs fail closed at the suite level, but library code itself still relies on asserts for these invariants. | None. |
| R-4 | P2 (disclosure) | Pre-Oct-2024 NSE charges were slab-based on monthly cumulative turnover; the config flattens them to the slab-1 (highest) rate. Cost estimates for 2022–2024 are therefore conservative — overstated for high-turnover accounts. | Phase 1D inherits the overstatement; every backtest spanning pre-Oct-2024 must disclose it. |

### 10.4 Documentation and reporting defects

| ID | Finding |
|---|---|
| D-1 | `CURRENT_STAGE_OF_WORK.md` §3 contains the repository tree twice: the first block states 91 tests, the second is a stale duplicate listing 79 tests with old per-file counts, and the trailing code fence is unbalanced. Two contradictory test totals now sit in one document. |
| D-2 | The commit subject claims "remediate all ... F-01 through F-12". Measured status is 10 closed, 1 mitigated, 1 partial, 1 open. Per AGENTS §9.1 a completion claim must be computed, not typed. |
| D-3 | `indicators.py` annotates a local as `Set[datetime.date]` without importing `Set`. Harmless at runtime (local annotations are not evaluated) but fails static analysis. |

### 10.5 Computed phase gate

Criteria stated before the result, each evaluated from the run above:

| Gate | Criterion | Result |
|---|---|---|
| G1 | All P1 findings (F-01, F-02, F-03) closed under independent reproduction | **PASS** |
| G2 | All P2 findings closed; any residual must be non-silent or explicitly scoped | **PARTIAL** — F-06 still emits a value across an intra-week gap |
| G3 | Statutory schedule accurate against primary circulars, effective-dated, contiguous, fail-closed outside coverage | **PASS** |
| G4 | No regression: full suite green, no new P1 introduced | **PASS** (91/91, exit 0) |
| G5 | Documentation states the measured status without overclaiming | **FAIL** (D-1, D-2) |

**Verdict: advance to Phase 1D — GO, conditional.**

Computed rationale: Phase 1D consumes `PriceBar`, `ExchangeSessionObservation`, `PriceSeriesContinuityValidator` and the criteria loader. Every gate governing those components (G1, G3, G4) passes, so the dependency surface for the execution and cost engine is sound. G2 and G5 fail only on components Phase 1D does not consume — weekly trend (R-1) and the status document (D-1/D-2).

Conditions attached to the GO:
1. Restate Phase 1C in `CURRENT_STAGE_OF_WORK.md` as **COMPLETE WITH RESIDUALS (R-1, R-2, R-4)**, not "all recommendations remediated"; fix the duplicated tree (D-1).
2. Phase 1D cost outputs must disclose R-4 (pre-Oct-2024 slab flattening) wherever they span that period.
3. Close R-1 before any weekly-trend signal reaches a strategy; close R-2 or document byte-identity semantics before any fingerprint is used as an economic-equivalence check.
4. Do not treat the legacy fingerprint path as a second engine: keep the parity test, and delete `compute_legacy_dataset_content_fingerprint` once the legacy snapshot is retired.
