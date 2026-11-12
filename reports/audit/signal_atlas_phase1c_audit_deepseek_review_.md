# Signal Atlas Core — Independent Progress Audit (Phase 1A → 1C)

**Audit date:** 2026-11-11
**Auditor role:** Indian senior quantitative researcher (external review)
**Scope:** Verify the claims in `CURRENT_STAGE_OF_WORK.md` and `WHAT_WE_ARE_BUILDING.md` against the actual code, tests, committed artifacts and statutory rate sources.
**Repository state audited:** commit `84c7501` (`feat(features): complete Phase 1C pure indicator formulas and subsegment engine`) with 4 files dirty (+1 line each, trailing newline only).
**Code changes made by this audit:** none. This document is read-only review output.

**Sections:** §1–§9 Phase 1A→1C audit · §10 Phase 1C re-audit · §11–§12 Phase 1D · §13–§18 Phase 1E / Phase 2A · §19–§20 Phase 2A re-audits · §21 Phase 2B.

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
---

## 11. Phase 1D Review — Cost Engine and Execution Simulator (2026-11-11)

**Commit audited:** `b0ceaeb` — *"implement Phase 1D statutory Indian cost engine and execution fill simulator"*
**Environment:** Python 3.13.5, pytest 8.3.4, `PYTHONPATH=src`, `filterwarnings = ["error"]`
**Suite (measured):** `106 passed in 0.90s`, exit 0 — up from 91. `python -O -m pytest` exits 1 via `PytestConfigWarning`, so optimized runs still fail closed at the suite level.
**Independent probes:** 46 executed outside the repo's test suite (hand-computed expectations, no reuse of fixture values).

### 11.1 What is genuinely correct

The **statutory cost engine is exact**. All 24 arithmetic checks matched a hand computation to the last digit, with no float anywhere in the path:

| Check | Value produced |
|---|---|
| Delivery BUY 100 @ ₹1000, 2026-11-11 gross | `100000` |
| STT 0.1% delivery | `100.0000` |
| Exchange turnover ₹306.99/cr | `3.069900000` |
| IPFT ₹0.01/cr | `0.000100000` |
| SEBI ₹10/cr | `0.100000` |
| Stamp duty 0.015% buy | `15.00000` |
| GST 18% on (brokerage + exchange + SEBI + IPFT) | `4.17060000000` |
| Total charges | `142.34060000000` |
| Net cash flow | `-100142.34060000000` |

STT/stamp asymmetry across all four leg types is correct, the sell leg carries zero stamp duty, the 2024-09-30 → 2024-10-01 boundary switches circular `NSE/FA/61137` → `NSE/FA/64323` on the exact date, the R-4 slab-flattening disclosure is attached strictly before that boundary, a 2019 trade raises `CriteriaValidationError`, and a float price raises `CostCalculationError`. Slippage math also matches: `0.0005 + 0.10*sqrt(10^6/10^7) = 0.0321227766…` exactly, adverse in both directions.

Three residuals from §10 are also closed: no `assert` remains anywhere in `src/`, the missing `Set` import is fixed, and the duplicated repository tree with stale 79-test counts has been removed from `CURRENT_STAGE_OF_WORK.md`. The status document now states the residuals honestly instead of claiming total remediation.

### 11.2 Findings

| ID | Severity | Finding | Probe evidence |
|---|---|---|---|
| E-1 | **P1** | The circuit-freeze invariant is both unreachable and look-ahead. Limits are optional caller arguments and no contract (`PriceBar`, `ExchangeSessionObservation`) carries them, so a normal backtest runs with the freeze rule silently OFF. When supplied, the check uses the session **high/low** — data that exists only after the close — to reject a fill priced at the **open**. | No limits on a locked bar (O=H=L=1050): `FILLED` at 1050, i.e. a buy filled at the upper circuit. Limits supplied with open 1000 / high 1050 (circuit): `REJECTED_UPPER_CIRCUIT`, discarding a legal open fill because of what happened later in the day. |
| E-2 | **P2** | A bare `PriceBar` is silently coerced to `ExchangeSeries.EQ`, so trade-to-trade instruments pass entry screening whenever the caller passes a bar instead of an observation — the same fail-open class as 1C's F-11, one layer down. | Identical BE session: as `ExchangeSessionObservation` → `REJECTED_INELIGIBLE_SERIES`; as `PriceBar` → `FILLED`. |
| E-3 | **P2** | The latency invariant is a dead constant. `latency_sessions = 1` is hardcoded, never compared with the actual signal→target gap, and no latency is recorded on the result; `REJECTED_LOOKAHEAD` is never emitted. Config `min_execution_latency_sessions: 2` therefore rejects **every** order, including a correct T+1 one. | With latency=2: T+1 order → `REJECTED_INVALID_LATENCY`. With latency=1: a 30-session gap (2024-01-02 → 2024-02-01) → `FILLED`, result has no latency field. |
| E-4 | **P2** | `min_daily_turnover_crore` is parsed into the criteria contract and then never referenced by the simulator: the instrument-liquidity eligibility gate is dead configuration. | `grep` over `src/signal_core/execution/` returns no reference. |
| E-5 | **P3** | The non-default impact exponent path converts through `float()`, violating the Decimal-only accounting rule. | `alpha=0.6`: impact `0.0251188643150958` vs exact `0.02511886431509580111085032068`, delta `−1.11e−18`. |
| E-6 | **P3** | No rounding policy to paise. `PRECISION_4`/`PRECISION_2` are defined and unused; totals carry exponent −11 (`142.34060000000`), so the ledger can never reconcile to a contract note. | `total_charges.as_tuple().exponent == -11`. |
| E-7 | **P3** | When ADT is not supplied, the impact denominator falls back to the *current session's* turnover, which is not average daily turnover and understates impact on abnormally heavy days. | Code path inspection. |

### 11.3 Computed gate, Phase 1D → Phase 1E

| Gate | Criterion | Result |
|---|---|---|
| G1 | Statutory schedule exact across every component, leg, and date boundary | **PASS** (24/24) |
| G2 | Fail closed on non-Decimal input and on dates outside circular coverage | **PASS** |
| G3 | Circuit freeze enforced without caller-supplied evidence, and without end-of-day data deciding an open-time fill | **FAIL** (E-1) |
| G4 | Series eligibility cannot be bypassed by input typing | **FAIL** (E-2) |
| G5 | Execution latency measured against the trading calendar rather than hardcoded | **FAIL** (E-3) |
| G6 | No binary floating point in any accounting path | **FAIL** (E-5) |
| G7 | Zero `assert` guards; optimized-mode safety | **PASS** |
| G8 | Every configured liquidity gate is enforced | **FAIL** (E-4) |

**Verdict: Phase 1D cost engine — APPROVED. Execution simulator — NOT APPROVED for Phase 1E in its current form (4 PASS / 4 FAIL).**

The cost engine and slippage mathematics are correct and can be frozen; Phase 1E's ledger arithmetic will be sound on these inputs. The simulator cannot yet be the fill source for a ledger, because the ledger would permanently record fills produced under a disabled freeze rule (E-1), entry into trade-to-trade instruments (E-2), and an unmeasured latency (E-3) — and Phase 2 walk-forward results would inherit all three.

Remediation required before Phase 1E consumes fills:
1. Carry circuit limits as evidence (a field on the session observation, or a required argument resolved from a circuit-band source), and reject only when the **fill reference price** is at or through the limit — never on the basis of the session high/low (E-1). A whole-day lock (`high == low == limit`) additionally blocks the fill.
2. Remove the `ExchangeSeries.EQ` default for bare `PriceBar` input: require explicit series evidence for entry, or fail closed (E-2).
3. Compute latency in trading sessions from the calendar and record it on `ExecutionFillResult`; keep the `min_execution_latency_sessions` check against the measured value (E-3).
4. Enforce `min_daily_turnover_crore` (E-4), remove the float path for non-default alpha (E-5), and declare an explicit paise rounding policy at the breakdown boundary (E-6).
---

## 12. Phase 1D Re-audit After Remediation — E-1 … E-6 (2026-11-11)

**Commit audited:** `2852af8` — *"remediate execution simulator audit findings E-1 through E-6"* (10 files, +656/−252)
**Suite (measured):** `108 passed in 0.60s`, exit 0; `python -O -m pytest` exits 1 via `PytestConfigWarning`; `grep "^\s*assert " src/` returns 0.
**Independent probes:** 50 executed outside the repo's suite (40 first pass, 10 corrected/edge). Two probe expectations in the first pass were themselves wrong (latency index arithmetic, participation basis) and were re-run against hand-derived references before being reported.

### 12.1 Remediation status, computed

| ID | Claimed | Measured result | Status |
|---|---|---|---|
| E-1 | Remediated | Circuit gate now evaluated on the **fill reference price**; open 1000 / high 1050 (circuit) → `FILLED` at `1002.736067977…`, where §11 recorded a rejection. Open at/through the limit → `REJECTED_UPPER_CIRCUIT`. Limits now travel on `ExchangeSessionObservation` with validation (upper ≥ high, lower ≤ low, lower ≤ upper, bool/float rejected). | **Lookahead half CLOSED; evidence half PARTIAL** |
| E-2 | Remediated | Bare `PriceBar` without `explicit_series` → `REJECTED_INELIGIBLE_SERIES`; `explicit_series=BE` and a BE observation → rejected; `explicit_series=EQ` → fills. The silent `EQ` coercion is gone. | **CLOSED** |
| E-3 | Remediated | Calendar latency measured (Fri 23 Jan → Tue 27 Jan across Republic Day = 1 session); 30-session gap records `latency_sessions=21`; `min_execution_latency_sessions=2` now rejects T+1 and accepts T+2; `REJECTED_LOOKAHEAD` emitted instead of a bare exception. | **CLOSED** (fallback caveat below) |
| E-4 | Remediated | `REJECTED_INSUFFICIENT_TURNOVER` fires below ₹5 Cr; healthy ADT admits the same bar. | **CLOSED** (basis caveat below) |
| E-5 | Remediated | `alpha=0.6` result matches a hand-built exact `Decimal` reference bit-for-bit: `1025.618864315095801110850321`. No `float()` remains in the path. | **CLOSED** |
| E-6 | Remediated | `to_paise()` and `round_to_paise=` exist, but `round_to_paise` defaults to `False`, the simulator never passes it, and `grep` finds **zero** references to either name outside `costs.py` — including zero test coverage. A simulated fill still returns `total_charges` with 25 decimal places. | **NOT CLOSED at the boundary** |

### 12.2 New findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| E-1-R | **P2** | Circuit protection remains opt-in and unpopulated: `upper_circuit_limit`/`lower_circuit_limit` are fields on the observation, but no loader, dataset builder, or reconciliation path ever sets them. The zero-range (`high == low`) heuristic catches a classic locked day, but a stock that **opens at the upper circuit and then trades lower** (open = high = 1050, low = 1000) has no zero range, so a BUY still fills at 1050 — the §5.3 prohibition. | `FILLED @ 1050` with no limits; identical bar with `upper_circuit_limit=1050` → `REJECTED_UPPER_CIRCUIT`. |
| E-4-R | P3 | The turnover gate compares an **average** daily turnover threshold against a **single session's** traded value whenever `average_daily_turnover` is not supplied (it never is, absent an ADT source). A genuinely liquid scrip on a thin session is rejected; an illiquid scrip on a spike day is admitted. | Session turnover ₹10 lakh → `REJECTED_INSUFFICIENT_TURNOVER`; same bar with ADT ₹10 Cr → `FILLED`. |
| E-3-R | P3 | Without a trading calendar the latency fallback counts Mon–Fri, so NSE holidays are counted as sessions — a silent overcount that can only make the latency gate *more* permissive. | Fri 23 Jan → Tue 27 Jan: 1 session with the calendar, 2 without. |
| E-6-R | P3 | The paise policy, when invoked, is correct (all fields 2 dp, `net_cash_flow == -(gross + total_charges)` holds). The defect is that it is never invoked, and `to_paise()` has no test. | `round_to_paise=True` → `142.34`; simulated fill → `142.6654823532891115284254431`. |
| E-8 | P3 | On a zero-range bar locked at the **lower** circuit with no limit evidence, a BUY is rejected as `REJECTED_UPPER_CIRCUIT` — conservative, but it discards a legally fillable buy and mislabels why. | `REJECTED_UPPER_CIRCUIT` for `O=H=L=950`. |
| E-9 | info | The `target_date > signal_date` structural guard was removed from `ExecutionOrder` and moved into the simulator. Same-session orders are now constructible. Defensible (it is what allows `REJECTED_LOOKAHEAD` to be reported rather than raised), but the contract layer no longer prevents the state. | Constructor accepts signal == target; simulator returns `REJECTED_LOOKAHEAD`. |

### 12.3 Re-computed gate, Phase 1D → Phase 1E

| Gate | Criterion | §11 | §12 |
|---|---|---|---|
| G1 | Statutory schedule exact across every component, leg, and date boundary | PASS | **PASS** (regression clean: `142.3406`, boundary/disclosure/fail-closed intact) |
| G2 | Fail closed on non-Decimal input and on dates outside circular coverage | PASS | **PASS** |
| G3 | Circuit freeze enforced without caller-supplied evidence, without end-of-day data deciding an open-time fill | FAIL | **FAIL** (lookahead resolved; evidence still optional and unpopulated — E-1-R) |
| G4 | Series eligibility cannot be bypassed by input typing | FAIL | **PASS** |
| G5 | Execution latency measured against the calendar rather than hardcoded | FAIL | **PASS** |
| G6 | No binary floating point in any accounting path | FAIL | **PASS** |
| G7 | Zero `assert` guards; optimized-mode safety | PASS | **PASS** |
| G8 | Every configured liquidity gate is enforced | FAIL | **PASS** (enforced; basis caveat E-4-R) |

**Verdict: 7 PASS / 1 FAIL — GO to Phase 1E, conditional.** Four of the five defects that blocked §11 are closed as claimed, and the two remaining ones are narrow, localised, and do not affect the accounting layer's design.

Conditions:
1. The ledger must post paise-quantized amounts (`round_to_paise=True`, or an explicit `to_paise()` step at the posting boundary), with a test for `to_paise()` — it currently has none. Without this, the Phase 1E ledger cannot reconcile to a contract note, which is its stated purpose (E-6-R).
2. No fill may be treated as a final trade record until circuit bands are populated from an authoritative source (pre-open circuit-band file or the surveillance/band feed) and the open-at-circuit case is rejected without needing caller evidence (E-1-R). Until then, fills should carry an explicit "circuit evidence absent" marker rather than reporting silently clean.

Carry forward, non-blocking: source ADT once per instrument instead of substituting session turnover (E-4-R); require a trading calendar for latency or mark the business-day fallback as approximate (E-3-R); distinguish lower-lock from upper-lock on zero-range bars (E-8).
---

## 13. Phase 1E Review — Portfolio Ledger, Position Accounting, Risk Tracker (2026-11-11)

**Commits audited:** `874fe61` (simulator paise + circuit marker), `545ab0d` (Phase 1E: 7 files, +1304/−20). Working tree differs from `545ab0d` only by trailing newlines in three portfolio modules.
**Suite (measured):** `120 passed in 0.74s`, exit 0.
**Independent probes:** 26 executed outside the suite. One probe expectation was wrong and is reported as such: the split-lot PnL gap in D is *correct* per-order brokerage behaviour, not a defect (see §13.2).

### 13.1 Carried-over conditions from §12

| Condition | Result |
|---|---|
| Post paise-quantized amounts at the ledger boundary | **CLOSED.** `CashLedger.record_fill` calls `costs.to_paise()`; every posting is 2 dp (`exponent == -2`), and §12's 25-decimal fill cost now lands as `-100142.34`. |
| Mark fills that lack circuit evidence | **CLOSED (disclosure half).** `ExecutionFillResult.circuit_evidence_present` and `CashLedgerEntry.circuit_evidence_present` exist; a fill without limits yields `circuit_evidence_present=False` plus an `UNVERIFIED_CIRCUIT_EVIDENCE` metadata key. **The evidence half is still open:** `grep -rn upper_circuit_limit src/` outside the contract and simulator returns nothing, so no loader manufactures the band. Carries forward as E-1-R, unchanged. |

### 13.2 What is correct (verified by probe)

- **Round-trip reconciliation is exact to the paisa.** BUY 100 @ 1000 then SELL 100 @ 1100: `cash − initial == realized_net_pnl == 9719.94`, gross PnL exactly `10000.00`, cash exponent `-2`.
- **Statutory costs are per-order, not per-trade.** Selling 3 shares as 3×1 costs `47.18` more than as 1×3; the predicted gap from two extra ₹20 brokerages plus 18% GST is `47.20`, the 2 paise being per-order paise quantization. The cost engine behaves exactly as a per-order schedule should, and the resulting PnL difference is real, not an accounting bug.
- **Overdraft fails closed without side effects.** Posting a buy that overdraws raises `Cash overdraft prohibited` and leaves both the entry count and the balance untouched.
- **Valuation fails closed.** A missing price or non-positive price for an open position raises; a repeated or earlier `as_of_date` raises.
- **Non-fill outcomes are rejected** by both the ledger and the position, with the reason surfaced.

### 13.3 Findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **I-1** | **P1** | **Fill posting is not atomic.** `Portfolio.process_fill` posts cash *first*, then updates the position. When the position update raises, the cash entry stays. A rejected oversell (sell 200 while holding 100) raises `Illegal short delivery` **and** leaves a fabricated `+₹199,768.92` sell inflow in the ledger (cash `899,857.66 → 1,099,626.58`, 2 → 3 entries). The same path corrupts cash when selling an instrument never held. | Probe A |
| **I-2** | **P1** | **No posting idempotency.** The same `ExecutionFillResult` object processed twice is accepted twice: cash `899,857.66 → 799,715.32`, and two ledger entries share one `reference_id` (`FILL_<inst>_<date>`). Any retry, replay or double-dispatch silently doubles exposure and destroys the audit trail. `reference_id` is not unique-enforced. | Probe B |
| I-3 | P3 | **Concentration cap is evaluated on gross value only.** A buy of exactly 10.00% gross passes the committed `max_single_position_weight: 0.10`, but the actual cash deployed is `10.0355%` because statutory charges are excluded from the numerator and included in the denominator. The limit is under-enforced by the cost of the trade. | Probe F |
| I-4 | P3 | **A drawdown breach is quantized away before it is tested.** Drawdown is quantized to 4 dp (`ROUND_HALF_UP`) and then compared with `0.25`. An equity drop of `0.25001` is stored as `0.2500` and reports `is_max_drawdown_breached == False`; only a loss materially beyond the limit registers. A Go/No-Go verdict at exactly the threshold is decided by rounding. | Probe G: equity `74999.00`, raw `0.25001`, stored `0.2500`, breached `False` |
| I-5 | P3 | **No chronological ordering and no reversal path.** The ledger accepts a SELL dated 11 Nov after a BUY dated 12 Nov, producing an out-of-sequence balance history. Entries are append-only with no void/reversal mechanism, so I-1's phantom posting cannot be corrected without rebuilding the ledger. | Probe H: balances `1000000.00, 899857.66, 1009719.94` for dates 12 Nov, 12 Nov, 11 Nov |
| I-6 | info | **"Double-entry" overstates the structure.** Each entry carries one `amount` and a running balance; there is no contra leg, no position/cash account pair, and no journal that balances. Positions live in a separate mutable object outside the cash book. It is a single-entry cash book with an external position tracker. The module docstring and `CURRENT_STAGE_OF_WORK.md` both call it double-entry. | `types.py: CashLedgerEntry`, `ledger.py` docstring |
| I-7 | info | **Sub-paise basis drift on partial sales.** Partial-sale cost basis is derived from the 4 dp average price (`avg × qty`), not from a proportional share of `total_cost_basis`, so the identity `avg × qty == basis` is only approximate and the residual drifts within a paise across many lots. | Probe D″: residual basis `333.34` holding 1 share at avg `333.3350` |

I-1 and I-2 are invisible to the suite because `tests/unit/test_portfolio.py` exercises `ledger.record_fill()` and `pos.apply_fill()` as two independent steps (e.g. `test_position_full_and_partial_sales_reconciliation`) and tests the short-sale rejection only against a bare `Position`. The `Portfolio.process_fill` ordering is never exercised on a failing path.

### 13.4 Gate, Phase 1E

| Gate | Criterion | Result |
|---|---|---|
| G1 | Ledger arithmetic exact, every posting quantized to paise, round trip reconciles to the paisa | **PASS** |
| G2 | Fail closed on non-fill, non-Decimal, and overdraft inputs, with no state change on rejection | **PASS** |
| G3 | Posting a fill is atomic — no cash movement survives a rejected position update | **FAIL** (I-1) |
| G4 | Each fill posts exactly once, with a unique audit reference | **FAIL** (I-2) |
| G5 | Cost basis, average price and realized PnL net of the full statutory schedule | **PASS** |
| G6 | Committed concentration limit enforced on the capital actually deployed | **FAIL** (I-3) |
| G7 | Drawdown and duration tracked and compared to committed thresholds without losing breaches to rounding | **FAIL** (I-4) |
| G8 | Mark-to-market fails closed on missing, non-positive or stale prices | **PASS** |
| G9 | Ledger history is chronologically ordered and correctable | **FAIL** (I-5) |

**Verdict: 4 PASS / 5 FAIL — Phase 1E is NOT verified. Do not advance to Phase 2.**

The arithmetic core is sound and the §12 conditions are met, but a ledger that can be inflated by a rejected order (I-1) and double-debited by a replayed fill (I-2) cannot be the accounting base for a backtest, where replay and rejection are routine. Both defects are ordering/guard problems in `Portfolio.process_fill`, not design flaws:

1. **I-1** — validate the position transition before posting (preview the sell against the held quantity inside `process_fill`, or apply the position first and roll it back on a ledger rejection), and add a test that asserts the ledger is unchanged after a rejected oversell.
2. **I-2** — reject a `reference_id` already present in the ledger, and add a test that posting one `ExecutionFillResult` twice raises.

Non-blocking follow-through: I-3 (include charges in the concentration numerator), I-4 (compare unrounded drawdown, or compare at 4 dp with `>=` against a threshold expressed the same way), I-5 (reject non-monotonic `trade_date`), I-6 (rename the claim or build the contra legs), I-7 (derive partial-sale basis proportionally from `total_cost_basis`).

Carried forward from §12, still open: circuit-band evidence has no data source (E-1-R), so every fill and ledger entry will carry `circuit_evidence_present=False` in practice until a band feed exists.
---

## 14. Phase 1E Re-Audit — §13 Remediation (`2adbe90`)

**Commit audited:** `2adbe90` — 6 files, +371/−98 (`ledger.py`, `portfolio.py`, `position.py`, `__init__.py`, `test_portfolio.py`, `CURRENT_STAGE_OF_WORK.md`).
**Suite (measured):** `126 passed in 0.86s`, exit 0.
**Probes:** 26 executed outside the suite. One probe (address-reuse) was **inconclusive** and is reported as such rather than as a defect.

`CURRENT_STAGE_OF_WORK.md` has been corrected: it now reads "Phase 1E In Audit Remediation … awaiting re-audit verdict" instead of the previous "Completed & Verified — Ready for Phase 2", and the ledger is described as a single-entry cash book. That documentation finding is closed.

### 14.1 Findings resolved (each re-derived by independent probe)

| ID | Status | Probe evidence |
|---|---|---|
| **I-1** atomicity | **CLOSED** | Rejected oversell (sell 200, holding 100): `LedgerValidationError`, ledger `('1899857.66', 2) → ('1899857.66', 2)`, `untouched=True`. Selling a never-held instrument: cash and entry count unchanged, **no** phantom `Position` created on the pre-validation path. |
| **I-2** duplicate posting | **CLOSED for replay** | Replaying the same fill object, a twin object with the same reference, and an identical fill under the same explicit reference all raise `Duplicate entry rejected` with cash and entry count unchanged. (But see R-1 — the key is wrong.) |
| **I-3** concentration basis | **CLOSED** | A buy of exactly 10.00% gross now deploys `10035.48 / 100000 = 0.1003548` and is **rejected**; the previously-passing case fails closed. 9 shares (`0.0903`) is accepted. Comparison is now on the unrounded weight. |
| **I-4** drawdown rounding | **CLOSED** | Equity loss of `25001` on a `100000` peak: stored drawdown `0.25001`, `is_max_drawdown_breached=True`. Loss of `24999`: stored `0.24999`, `False`. The committed `0.25` boundary now behaves exactly. |
| **I-5** chronology | **PARTIAL** | A `2026-11-11` SELL posted after a `2026-11-12` BUY raises `Non-monotonic trade_date`. Residual in R-4. |
| **I-6** "double-entry" | **CLOSED** | Docstrings now say single-entry cash book; the claim matches the structure. |
| **I-7** basis drift | **CLOSED** | Buy 100 @ 1000, buy 3 @ 1001, sell 1: `qty=102 basis=102002.97 avg=1000.0291`, and `avg × qty == 102002.97` with **residual `0.00`**. |
| — rollback | **CLOSED** | With `Position.apply_fill` forced to raise after the cash post: `ledger_rolled_back=True`, cash `1989964.52` and entry count `2` before and after, position still `10`. |
| — round trip | **holds** | Buy 100 @ 1000 / sell 100 @ 1100: `cash_delta == realized_net_pnl == 9719.94`, exponent `-2`. |
| — bad prices | **fail closed** | A `NaN` or `Infinity` executed price raises from the position layer, ledger untouched, no partial mutation of `total_charges_paid` (100 shares, no quantity change). |

### 14.2 Findings still open

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **R-1** | **P1 (regression)** | **Distinct fills of the same instrument on the same date are indistinguishable.** The uniqueness guard keys on `reference_id`, whose default is `FILL_{instrument}_{date}`. A partial-fill remainder (order 100, filled 60 then 40) is **rejected**: `Duplicate entry rejected: fill 'FILL_INFY_2026-11-11' has already been posted`. Two orders for the same scrip in one session are rejected the same way. Only a caller-supplied per-fill id makes multi-fill work (`reference_id="O0"/"O1"/"O2"` → qty 60 accepted), and `ExecutionOrder`/`ExecutionFillResult` carry no order or fill id, so no default exists that could be unique. The fix prevents corruption by failing closed, but it also forbids the ordinary partial-fill and scale-in path a backtest must support, and it does not deliver what G4 asked for: a reference that **identifies a fill**. | Scale-in without explicit refs: leg 0 accepted, legs 1–2 rejected. With explicit refs: all accepted, `qty=60`. |
| **R-2** | **P2** | **Nothing ties `fill.costs.gross_amount` to `filled_quantity × executed_price`.** Cash is posted from the cost breakdown while cost basis is booked from the executed price; the two are separate sources of truth for the same trade and are never reconciled. A fill of 100 shares with `executed_price=1000` but costs computed at `1100` posts a ₹110,142.34 debit and a ₹100,000 basis, leaving equity at `1989845.78` where the true value is `1889845.79` — a silent ₹100,000 phantom gain, no exception. The same gap means a fill carrying `executed_price=0.00` is accepted and **writes off the entire basis** (`100000.00 → 0.00`, realized net `-100269.68`). The cost model rejects non-positive prices, so this cannot arise from the simulator today — but the portfolio is the boundary that must not trust a hand-built or deserialised fill, and AGENTS §6.3 forbids treating a zero price as a real observation. | Probe: cash `1889845.78`, basis `100000.00`, `gross_amount=110000` vs `qty×price=100000`. |
| R-3 | P3 | **Rollback leaves a phantom position.** When a fill for a new instrument fails after the cash post, the ledger is restored but the empty `Position` stays in `_positions`: `positions=['TCS']`, `open=[]`, `get_position('TCS').quantity == 0`. Invisible to `get_open_positions` but persistent and returned by `get_position`. | Probe J |
| R-4 | P3 | **The opening capital deposit defaults to today's date.** `Portfolio(initial_capital=...)` without `initial_date` posts the deposit at `date.today()` while resetting the monotonicity cursor, so a backtest begins with an entry dated *after* its first trade: `[('2026-11-11','CAPITAL_DEPOSIT'), ('2026-11-05','TRADE_BUY_OUTFLOW')]`. The I-5 ordering guarantee therefore does not hold for the first two rows of any historical run that omits `initial_date`. | Probe G2 |
| R-5 | latent | **The replay set is keyed on `id(fill)`** — a memory address, not an identity. It is redundant with the reference check, grows without bound, and `id()` values are reusable after collection, so it can in principle reject an unrelated fill. Not reproduced in 300,000 allocation attempts, so this is reported as a hazard in the design, not an observed defect. | Probe D: `inconclusive` |
| R-6 | info | The fix introduced `# type: ignore[union-attr]` and `# type: ignore[assignment]` in `Position.apply_fill` for `fill.costs` and `fill.executed_price`, which `validate_fill` has just guaranteed. Harmless, but suppressions where a validator already establishes the invariant hide future regressions. | `position.py` |
| R-7 | info | **The suite has no test with two fills of one instrument on one date**, which is exactly why R-1 survived a "fully remediated" claim. All 17 portfolio tests either use a fresh date or a distinct instrument per fill, and **no test passes `reference_id`** — the parameter that makes multi-fill work is untested at its call sites. | `grep -n reference_id tests/unit/test_portfolio.py` → no matches |

### 14.3 Gate, Phase 1E (re-run)

| Gate | Criterion | Result |
|---|---|---|
| G1 | Ledger arithmetic exact, every posting quantized to paise, round trip reconciles | **PASS** |
| G2 | Fail closed on non-fill, non-Decimal, non-finite and overdraft inputs with no state change | **PASS** |
| G3 | Posting a fill is atomic; no cash movement survives a rejected or failing position update | **PASS** |
| G4 | Each fill posts exactly once and is identified by a reference unique **to that fill** | **FAIL** (R-1) |
| G5 | Cost basis, average price and realized PnL net of the statutory schedule, with no basis drift | **PASS** |
| G6 | Committed concentration limit enforced on capital actually deployed | **PASS** |
| G7 | Drawdown compared to committed thresholds without losing breaches to rounding | **PASS** |
| G8 | Mark-to-market fails closed on missing, non-positive or stale prices | **PASS** (code path unchanged in `2adbe90`; verified by diff, not re-executed) |
| G9 | Ledger history is chronologically ordered end to end | **FAIL** (R-4) |
| G10 | A fill's cash value and cost basis derive from one reconciled source | **FAIL** (R-2) |

**Verdict: 7 PASS / 3 FAIL — Phase 1E is conditionally approved, still not verified.**

The two P1 defects I raised in §13 are genuinely closed, with proof rather than assertion: the ledger can no longer be inflated by a rejected order, a replay is refused, drawdown and concentration now behave at their committed thresholds, and basis drift is exactly zero. The remediation is small and correct in its direction. What blocks the phase is that the idempotency guard was given the wrong key, so the fix traded one P1 for another: replay protection now rests on an instrument-day identity that cannot distinguish two real fills.

The remaining work is three surgical changes, not a redesign:

1. **R-1 (blocking).** Either give a fill a real identity (`order_id`/`fill_id` on `ExecutionOrder`/`ExecutionFillResult`, propagated from the simulator) and require it for replay detection, or default the reference to a per-ledger monotonic sequence (`FILL_{inst}_{date}#{n}`) and treat uniqueness as an audit-ordering property only. Replay detection needs a stable external identity; without one, instrument+date must not be used to infer it. Add a test with a partial-fill remainder and a scale-in of the same instrument in one session.
2. **R-2.** Assert in `process_fill` that `fill.costs.gross_amount == filled_quantity × executed_price` at paise precision and that `executed_price > 0`, before any state change.
3. **R-3/R-4.** Discard a `Position` created during a rolled-back fill; require or derive `initial_date` for the opening deposit in historical runs.

Carried forward and unchanged from §12/§13: circuit-band evidence still has no data source, so every fill and entry reports `circuit_evidence_present=False` in practice (E-1-R).
---

## 15. Phase 1E Re-Audit — §14 Remediation (`7257807`)

**Commit audited:** `7257807` — 8 files, +424/−30 (`types.py`, `simulator.py`, `ledger.py`, `portfolio.py`, `position.py`, `test_portfolio.py`, `CURRENT_STAGE_OF_WORK.md`, this report).
**Suite (measured):** `132 passed in 0.94s`, exit 0.
**Probes:** 30 executed outside the suite across two rounds. Every value below is printed by a probe, not read from a commit message.

### 15.1 Findings resolved (re-derived by probe)

| ID | Status | Evidence |
|---|---|---|
| **R-1** multi-fill / scale-in | **CLOSED (ref-less path)** | Partial 60 then 40 then a 50-share scale-in at a different price, no `reference_id`, no `order_id`: all three post, references `FILL_INFY_2026-11-11#1`, `#2`, `#3`, final `qty=150`, `basis=150500.00` — exactly `60×1000 + 40×1000 + 50×1010`. The instrument-day identity collision is gone. |
| **R-2** reconciliation | **CLOSED** | Fill priced 1000 but costed at 1100: `Reconciliation error: fill.costs.gross_amount (₹110000.00) does not match filled_quantity × executed_price (₹100000.00)`, cash still `2000000.00`, entries still `1`. `executed_price=0.00` and `NaN`: rejected with `executed_price must be positive finite Decimal`, no state change. The basis-write-off and phantom-equity paths are both dead. |
| **R-3** phantom position | **CLOSED** | With `Position.apply_fill` forced to raise on a new instrument: `_positions=[]`, `open={}`, cash `2000000.00`, entries `1`. The retry of the same instrument then succeeds and yields `qty=10`. |
| **R-4** opening deposit date | **CLOSED** | `Portfolio(initial_capital=...)` with no `initial_date`, first trade `2026-11-05`: rows are `[('2026-11-05','INIT_DEPOSIT'), ('2026-11-05','FILL_INFY_…')]`, `chronological=True`. |
| **R-5** `id()`-keyed set | **CLOSED as a hazard** | Retained fills are pinned by strong reference, so an `id()` value cannot be recycled while it is remembered; the address-reuse false-positive is now structurally impossible. (The replacement brings its own problems — N-1.) |
| **R-6** type suppressions | **CLOSED** | Both `# type: ignore` comments removed; `validate_fill` now establishes the invariant explicitly instead of silencing the checker. |

`executed_price` is now validated in **both** `Portfolio.process_fill` and `Position.validate_fill`. That duplication is defence in depth at a trust boundary, not redundancy to be trimmed.

### 15.2 New findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **N-1** | **P1 (regression)** | **The replay guard is O(n²) in time and O(n) in retained fills.** Replacing `Set[int]` with a list plus `any(fill is p for p in self._processed_fills)` on every fill makes the per-fill cost grow linearly with run length. Measured: 250 fills `112 µs`/fill, 500 `158`, 1000 `232`, 2000 `427`, 4000 `936`; total time grows **×16.1 for ×4 fills** where linear would be ×4. Extrapolating the measured curve, a 100,000-fill backtest spends ~40 minutes in the duplicate scan alone, and a Nifty-500 × 10-year run (~1.2 M fills) is ~10¹² identity comparisons. Memory: **4342 B retained per fill** over 2000 fills, i.e. ~5 GB at 1.2 M fills, because every `ExecutionFillResult` (with its cost breakdown) is held forever. The previous `Set[int]` was O(1) membership. This is a backtest engine; the guard must not be superlinear. | probes D and E |
| **N-2** | **P2** | **The sequence counter counts attempts, not posted fills.** `generate_fill_reference` increments before `_post_entry` runs, and nothing rolls it back when `_post_entry` rejects. After one posted fill on `2026-11-11` and two rejected non-monotonic attempts on `2026-11-10`, the counter reads `{('INFY', 11-11): 1, ('INFY', 11-10): 2}` while only `FILL_INFY_2026-11-11#1` exists. An overdraft rejection leaves `{('INFY', 11-11): 2}` with **no** fill posted at all. Consequences: the audit sequence acquires permanent holes (the next successful fill on that date is `#3`, with no `#1` or `#2`), and two runs of the same backtest produce *different* reference ids if their rejection histories differ — so references are not reproducible, which is the one property an audit trail must have. The docstring's "deterministic monotonic sequence reference" is therefore inaccurate. | probe B, probe C |
| **N-3** | **P2** | **`fill_id` is derived from the order, so it aliases distinct fills.** The simulator sets `fill_id = f"FILL_{order.order_id}"`, and `process_fill`/`record_fill` both prefer it over the sequence. A partial-fill remainder carried under the same `order_id`, even on a *different* session, is rejected: 60 shares on `2026-11-11` then 40 on `2026-11-12` under `order_id="ORD1"` → `Duplicate entry rejected: fill with reference 'FILL_ORD1' already posted to ledger`, position stuck at `qty=60`. `unfilled_quantity` exists precisely to carry a remainder, so the primary partial-fill workflow is still blocked — R-1 reborn through the new field, and the field's name promises a fill identity it does not deliver. Compose it per fill (`FILL_{order_id}_{fill_date}#{n}`) or make remainder orders carry a new id by construction. | probe: remainder next session |
| **N-4** | P3 | **`order_id` and `fill_id` are unvalidated.** `ExecutionOrder` validates every other field and raises `ExecutionOrderValidationError` for each, but accepts `order_id=""`, which yields the reference `FILL_`. That reference then collides **across instruments**: after `order_id=""` on INFY, the same on TCS is rejected with `Duplicate entry rejected: fill with reference 'FILL_'`. A non-string id (e.g. an int) is likewise accepted and stringified into the reference. `fill_id=""` behaves the same through the `is not None` branches. | probe: `order_id=''` INFY then TCS |
| N-5 | info | `_rollback_last_entry` recovers the counter key by **parsing back its own reference string** (`rsplit("#")`, then `rsplit("_")`, then `date.fromisoformat`) inside a bare `except Exception: pass`. It works, including for `BAJAJ_AUTO` (verified: the retry reuses `#1`), but a value the ledger just generated should be carried, not re-parsed. | probe 8 |
| N-6 | info | The `avg × qty == basis` invariant I certified with residual `0.00` in §14 holds **only for prices representable in paise**. At `executed_price=1000.005` with 3 shares, `basis=3000.02` but `avg×qty=1000.0067×3=3000.0201`. Unreachable at NSE tick sizes (0.05, two decimals), so this is a scope note on the gate wording, not a defect. | probe A |
| N-7 | info | `CURRENT_STAGE_OF_WORK.md` claims "§14 Audit Findings (R-1 through R-7) **fully remediated**" and that the ledger "successfully admits legitimate scale-ins and partial fill remainders on the same session". The second clause is true only when `order_id` is absent (N-3), and N-1/N-2 remain open. A status line that asserts remediation the probes contradict is the §9.1 failure the standing rules name. | diff + probes |

### 15.3 Gate, Phase 1E (re-run)

| Gate | Criterion | Result |
|---|---|---|
| G1 | Ledger arithmetic exact, every posting quantized to paise, round trip reconciles | **PASS** — cash delta `3027.18` == `gross 3000.02 + charges 27.16`, exact |
| G2 | Fail closed on non-positive, non-finite or non-Decimal prices with no state change | **PASS** |
| G3 | A fill posts atomically; no cash movement or empty position survives a failure | **PASS** |
| G4 | A fill's cash value and its cost basis derive from one reconciled source | **PASS** |
| G5 | Cost basis, average price and realized PnL net of the statutory schedule, no drift | **PASS** (paise-representable prices; see N-6) |
| G6 | Replay of a processed fill is refused while distinct real fills are admitted | **FAIL** (N-3) |
| G7 | The replay guard costs O(1) per fill and retains bounded memory | **FAIL** (N-1) |
| G8 | Audit references are unique per fill and reproducible run to run | **FAIL** (N-2) |
| G9 | Ledger history, including the opening deposit, is chronologically ordered | **PASS** |
| G10 | Committed concentration limit enforced on capital actually deployed | **PASS** (unchanged in `7257807`; verified by diff, carried from §14, not re-executed) |
| G11 | Drawdown compared to committed thresholds without losing breaches to rounding | **PASS** (carried from §14, unchanged) |
| G12 | Mark-to-market fails closed on missing, non-positive or stale prices | **PASS** (carried from §14, unchanged) |

**Verdict: 9 PASS / 3 FAIL — no money-corruption defect remains; Phase 1E is not yet verified.**

This is a materially better commit than `2adbe90`. Every §14 finding is closed with proof: multi-fill and scale-in now post with exact basis on the ordinary path, a fill whose cost breakdown disagrees with its price is refused before touching cash, the zero-price basis write-off is dead at both layers, rolled-back positions leave nothing behind, and a historical run starts on its own first trading date. The two `# type: ignore` suppressions became real validation. Nothing in this remediation can corrupt the ledger.

All three failures are now about *how* the guard is implemented rather than what it protects:

1. **N-1 (blocking).** Keep the address-pinning the fix needs but make lookup O(1): `Dict[int, ExecutionFillResult]` keyed on `id(fill)` gives O(1) membership *and* pins the address, so the R-5 hazard stays closed without the scan. If run-length memory must also be bounded, replay detection should lean on `fill_id`/reference equality for long runs and keep identity pinning only for a recent window. Re-measure per-fill cost at 1k/4k/16k fills before calling it fixed.
2. **N-3 (blocking for partial fills).** Make `fill_id` identify a fill: `FILL_{order_id}_{fill_date}` plus a per-(order, date) sequence, and add a test for a remainder filling on T+1 under the same `order_id`.
3. **N-2.** Generate the sequence reference only once the posting is known to succeed, or roll the counter back with the entry, so holes cannot appear and reruns yield identical references. Add both a rejection-then-retry determinism test and the `order_id=""` validation from N-4.

Carried forward and unchanged: circuit-band evidence still has no data source, so every fill and entry reports `circuit_evidence_present=False` in practice (E-1-R). The 1C-era `NOT RUN` items — snapshot SHA-256 reproduction and the 545-pair reconciliation — remain `NOT RUN`.

---

## 16. Phase 1E Re-Audit — §15 Remediation (`b7bd8ba`) + Full Phase-Wise Re-Verification (2026-11-11)

**Commit audited:** `b7bd8ba` — *"Remediate Audit §15 findings: O(1) bounded replay guard, deterministic sequence commit, unaliased fill IDs, and ID string validation"* (7 files, +393/−59). Working tree additionally contains an untracked `probe_b7bd8ba.py` (see N-12).
**Environment:** CPython 3.13.5 (win32), pytest 8.3.4, `pythonpath = ["src", "."]`, `filterwarnings = ["error"]`.
**Suite (measured):** `136 passed in 1.12s`, exit 0 — up from 132. Zero warnings.
**Independent probes:** 55 executed outside the repository suite in three rounds (timing/memory, portfolio behaviour, cross-phase regression). One probe of my own first round was wrong (`D`) and was re-derived before being reported; a second (`F`) used a session volume that tripped the turnover gate and was re-run with a supplied ADT. Both are reported at their corrected values.
**Code changes made by this audit:** none. This section is read-only review output.

### 16.1 §15 findings — closure, re-derived by probe

| ID | Claimed fix | Measured result | Status |
|---|---|---|---|
| **N-1** O(n²) replay guard | `OrderedDict[int, ExecutionFillResult]`, bounded to 10,000 | Per-fill cost `72.5 µs` @1k, `68.3` @4k, `78.7` @16k, `115.5` @32k — no superlinear scan. Pinned set caps at exactly `10000`. Retained memory at the cap: `48,093,744 B` (~`4.8 KB`/fill, bounded). | **CLOSED** |
| **N-2** counter counted attempts | Sequence committed inside `_post_entry` after all validations | After a posted `#1`, a non-monotonic attempt leaves `{('INFY', 11-11): 1}` and refs `['INIT_DEPOSIT', 'FILL_INFY_2026-11-11#1']`. An overdraft rejection leaves `{}` and refs `['INIT_DEPOSIT']`; the retry posts `#1` — no holes, reproducible. | **CLOSED** |
| **N-3** `fill_id` aliased fills | `FILL_{order_id}_{trade_date}#{count}` in the simulator | End-to-end simulator path: partial fill 60 on 11-11 → `FILL_ORD1_2026-11-11#1`, remainder 40 on 11-12 → `FILL_ORD1_2026-11-12#1`; both post, `qty=100`. Two fills of one order on one date → `#1`, `#2`. | **CLOSED** |
| **N-4** unvalidated ids | Field validators on `order_id`, `fill_id`, `reference_id` | `""`, `"   "`, `"  x"`, `123`, `True` all raise `ExecutionOrderValidationError` / `LedgerValidationError`. | **CLOSED** |
| **N-5** rollback parsed its own string | `_seq_keys_history` stack | Forced position failure on `BAJAJ_AUTO` (underscore in the id): rollback restores the counter, retry posts `FILL_BAJAJ_AUTO_2026-11-11#1`. | **CLOSED** |

All five §15 findings are closed as claimed. This is the first Phase 1E commit with no money-corruption and no superlinear guard. The round-trip invariant still holds exactly: BUY 100 @ 1000 then SELL 100 @ 1100 gives `cash_delta == realized_net_pnl == 9719.94`, cash exponent `-2`.

### 16.2 New findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **N-8** | **P3 (gate G8)** | **The generated sequence reference is never checked against `_posted_reference_ids`.** `_post_entry` checks uniqueness only for caller-supplied `reference_id`; on the `seq_prefix` path it composes `FILL_{prefix}_{date}#{count}`, adds it to the set, and posts. A reference already present with that exact shape is silently duplicated. Reachable without malice: `order_id = instrument_id` is a plausible naive convention, so posting an order-id fill first and an anonymous fill of the same scrip/date second yields two ledger rows with identical reference ids. The reverse order is refused (fail-closed), so the defect is one-directional. | Explicit `FILL_INFY_2026-11-11#1` deposit, then one anonymous INFY fill → refs `['INIT_DEPOSIT', 'FILL_INFY_2026-11-11#1', 'FILL_INFY_2026-11-11#1']`, `duplicate_refs=True`. |
| N-9 | P3 (latent) | **Replay protection is a 10,000-fill window, not a property.** After eviction, replaying the *same* `ExecutionFillResult` object posts a second cash entry and doubles the position, because the anonymous path mints a fresh `#n` reference instead of colliding. Bounded memory necessarily bounds identity memory, but the contract should say so; fills that carry a `fill_id` remain protected indefinitely by reference uniqueness. | 1 INFY buy + 10,000 unrelated fills → `old still pinned? False`; replay → accepted, `INFY qty = 2`. |
| N-10 | P3 | **The lazy opening deposit is mutated before validation, so a rejected fill changes ledger state.** When `initial_date` is omitted, `_post_entry` re-anchors `entries[0].trade_date` and `_last_trade_date` before the monotonicity/overdraft checks. A rejected overdraft attempt on 2026-11-20 changes the deposit row and cursor to 2026-11-20 although no entry posted. The next successful post re-anchors again, so it self-heals; the violation is observable ledger state after a rejection (gate G2 wording). | Deposit at construction `2026-11-11` → rejected attempt `2026-11-20` → deposit row now `2026-11-20`, `_last_trade_date = 2026-11-20`. |
| N-11 | info | **The "double-entry" description survives in two modules** despite I-6 being recorded as closed: `portfolio.py:35` ("Coordinates the double-entry CashLedger") and `types.py:37` ("Immutable double-entry cash ledger record"). `ledger.py` and `CURRENT_STAGE_OF_WORK.md` correctly say single-entry. | `grep -rn "double-entry" src/` |
| N-12 | info | **The committed evidence probe cannot run.** `probe_b7bd8ba.py` has no `sys.path` injection (direct run: `ModuleNotFoundError: No module named 'signal_core'`), ends with a literal `EOF` line (SyntaxError under `-m py_compile`), and assigns `f.fill_id = ...` on a frozen slots dataclass. None of the §15/§16 evidence it appears to produce is reproducible from the repository as committed. | `python probe_b7bd8ba.py`, file read |
| N-13 | P3 (test quality) | **`test_n1_replay_guard_o1_lookup_and_bounded_memory` would have passed the defect it names.** It asserts only `< 1000 µs/fill` at 1,000 fills; §15 measured the O(n²) implementation at `232 µs/fill` at 1,000 and `936 µs` at 4,000. A single absolute threshold cannot distinguish linear from quadratic. The fix itself is verified (N-1, independently measured), but the regression guard is ineffective. Assert a ratio between 1k and 8k/16k, or a hard bound at 16k. | test source + §15.2 timing curve |

Everything else in §15.2 is closed. In particular the reference-collision direction that *is* guarded (duplicate `fill_id`, duplicate explicit `reference_id`, and reused `fill_id` across instruments) all raise before touching cash, with counts unchanged.

### 16.3 Full phase-wise re-verification (all phases, re-derived where possible)

| Phase | Re-verified in this audit | Status |
|---|---|---|
| 0 — Legacy assessment | Not re-executed: the legacy repository is a sibling outside this project's writable scope; the narrative findings were not recomputed. | `NOT RUN` |
| 1A — Contracts | `PriceBar` rejects a real `float` open, `bool` volume, `NaN` close and incoherent high; `UniverseInterval` rejects a reversed interval; `UniverseSchedule` rejects duplicate members. Suite: 10 + 9 tests green. | **VERIFIED** |
| 1B — Series continuity | 6 sessions with `EQ→EQ→BE→BE→EQ→EQ`: continuity `True`, 0 gaps, **one** continuous subsegment (series change does not break history). A missing mid-series session → `UNEXPLAINED_MISSING_RECORD`. Duplicate dates and off-calendar bars raise `ValueError`. The 545-pair empirical counts were not recomputed (`data/raw/` absent). | **VERIFIED (contract layer)**; empirical counts `NOT RUN` |
| 1C — Features | 60-session calendar with session 10 removed: post-gap `sma_20 = None`, post-gap `rs_50 = None`, **0** non-`None` `rs_50` values across 59 features. Off-calendar partition raises. Weekly path: see R-1. | **VERIFIED WITH RESIDUALS** (R-1, R-2) |
| 1D — Costs & simulator | Delivery BUY 100 @ ₹1000: 2024-09-30 → `NSE/FA/61137`, charges `142.64`; 2024-10-01 and 2026-11-11 → `NSE/FA/64323` / `NSE/FA/73061`, charges `142.34`. Criteria load with five contiguous effective-dated slabs. Simulator: 5-session latency measured and recorded; `REJECTED_LOOKAHEAD` on same-day; `BE` entry `REJECTED_INELIGIBLE_SERIES`; bare `PriceBar` `REJECTED_INELIGIBLE_SERIES`; open at upper circuit `REJECTED_UPPER_CIRCUIT`; turnover gate fires. | **VERIFIED** (E-1-R carry-forward) |
| 1E — Ledger / positions / risk | §15 findings closed; atomic posting, reconciliation, paise quantization, exact round trip, rollback cleanup, sequence determinism, multi-session partial fills, id validation all re-derived. See 16.4 gate. | **VERIFIED WITH ONE P3 RESIDUAL** (N-8) |

### 16.4 Gate, Phase 1E (re-run)

| Gate | Criterion | Result |
|---|---|---|
| G1 | Ledger arithmetic exact, every posting quantized to paise, round trip reconciles | **PASS** |
| G2 | Fail closed with no state change on rejection | **PARTIAL** — fill-level rejections leave cash, entries and positions untouched; the lazy deposit anchor is mutated before validation (N-10) |
| G3 | A fill posts atomically; no cash movement or empty position survives a failure | **PASS** |
| G4 | A fill's cash value and cost basis derive from one reconciled source | **PASS** |
| G5 | Cost basis, average price and realized PnL net of the statutory schedule, no drift | **PASS** (paise-representable prices; N-6 scope note stands) |
| G6 | Replay of a processed fill is refused while distinct real fills are admitted | **PARTIAL** — refused within the retained 10,000-fill window and indefinitely for id-bearing fills; an evicted anonymous fill can re-post (N-9) |
| G7 | The replay guard costs O(1) per fill and retains bounded memory | **PASS** (65–116 µs/fill; 10,000 cap; ~48 MB) |
| G8 | Audit references are unique per fill and reproducible run to run | **FAIL** — reproducible, but the generated path does not enforce uniqueness against an existing reference (N-8) |
| G9 | Ledger history, including the opening deposit, is chronologically ordered | **PASS** |
| G10 | Committed concentration limit enforced on capital actually deployed | **PASS** (unchanged in `b7bd8ba`; carried from §14, verified by diff) |
| G11 | Drawdown compared to committed thresholds without losing breaches to rounding | **PASS** (unchanged; carried from §14) |
| G12 | Mark-to-market fails closed on missing, non-positive or stale prices | **PASS** (unchanged; carried from §14) |

**Verdict: 9 PASS / 1 FAIL / 2 PARTIAL — §15 fully remediated; Phase 1E accounting is verified, one P3 audit-identity guard remains.**

The three blockers from §15 are genuinely gone: the replay guard is O(1) and bounded, sequence references are deterministic with no holes, and partial-fill remainders across sessions post cleanly end to end. Nothing in this commit can corrupt cash, basis or realized PnL; every probe of the ordinary fill pipeline reconciles to the paisa.

N-8 is not a money defect. It is a three-line gap in the audit-identity guard: on the generated-reference branch, `_post_entry` must verify `final_ref` is not already in `_posted_reference_ids` (and raise if it is), exactly as the explicit branch does. Until that exists, G8 cannot be signed as PASS, because two ledger rows can carry the same reference.

### 16.5 Carried-forward residuals (unchanged, must be closed before they reach Phase 2)

| ID | Severity | Residual | Scope |
|---|---|---|---|
| E-1-R | P2 | Circuit-band evidence still has no data source; every fill reports `circuit_evidence_present=False` unless the caller manufactures bands. | **Blocks treating any fill as a final trade record.** |
| R-1 / F-06 | P3 | `aggregate_daily_to_weekly` accepts an intra-week missing session: 15 daily bars with one session removed yield 3 weekly bars with `session_count = [7, 6, 1]`, and `compute_weekly_trend(..., 2)` returns `(114, 113.500000, True)` across the incomplete week. It detects whole missing weeks, not missing sessions inside a week. | **Blocks any weekly-trend signal in Phase 2.** |
| R-2 / F-10 | P3 | `canonicalize_decimal` keeps `str(Decimal)`: `100.5` → `100.5`, `100.50` → `100.50`, digests differ for identical economics. The module docstring now scopes fingerprints to "byte and record immutability", which is an acceptable disclosure, not a fix. | Treat fingerprints as byte identity only. |
| E-4-R | P3 | Turnover gate compares the average-daily-turnover threshold against a single session's traded value when ADT is not supplied. | Conservative on spikes, permissive on thin sessions. |
| E-3-R | P3 | Without a trading calendar, latency counts business days, so NSE holidays inflate the session count. | Over-permissive latency gate. |
| N-9 / N-10 / N-11 | P3/info | See 16.2. | Documented boundary / hygiene. |

### 16.6 NOT RUN register (updated)

| Check | Why not run |
|---|---|
| Snapshot SHA-256, `DATA-CTNT-V2` digest and universe fingerprint reproduction | `historical_dev_dataset_2022_2024.json` is not in this repository; the legacy project is a sibling outside the audited tree |
| 545-pair Bhavcopy reconciliation re-execution | 743 raw Bhavcopy ZIPs under `data/raw/` are absent; the committed CSV and policy report were reviewed, not recomputed |
| Phase 0 legacy-code assessment | Legacy repository outside this project's audit scope |
| Any strategy, walk-forward, DSR, Haircut Sharpe or drawdown PnL metric | No strategy layer exists yet (Phase 2). **No strategy PASS/FAIL or GO/NO-GO verdict is expressed here.** |
| Optimized-mode (`python -O`) suite | Not rerun in this round; §11/§12 established that `filterwarnings = ["error"]` exits non-zero under `-O`, and `grep "^\\s*assert " src/` was already zero |

### 16.7 Computed phase gate, Phase 1E → Phase 2

| Gate | Criterion | Result |
|---|---|---|
| P1 | Every §15 finding independently reproduced as closed | **PASS** (5/5) |
| P2 | No new P1/P2 defect introduced | **PASS** (new findings are P3/info) |
| P3 | Full suite green on the audited commit | **PASS** (136/136, exit 0, no warnings) |
| P4 | Phase 1A–1D invariants still hold after the change | **PASS** (16.3) |
| P5 | Ledger arithmetic and reconciliation exact | **PASS** |
| P6 | Audit references unique per fill | **FAIL** (N-8) |
| P7 | Status document matches the measured state | **PARTIAL** — §15 remediation is accurately described, but "double-entry" survives in two module docstrings (N-11) and the committed probe is not runnable (N-12) |

**Verdict: conditional GO to Phase 2.**

Phase 1E's accounting core is verified: exact Decimal cash, paise posting, atomic fills, reconciled gross, drift-free basis, deterministic sequence references, multi-session partial fills, bounded O(1) replay guarding and fail-closed risk limits. The §15 remediation is real, not restated.

Two conditions before Phase 2 begins:
1. **Close N-8**: on the `seq_prefix` branch of `_post_entry`, reject a generated `final_ref` that already exists in `_posted_reference_ids`, and add a test that posts an explicit `FILL_<instrument>_<date>#1` then an anonymous fill of the same instrument/date. This is the only remaining gate failure.
2. **Do not let weekly trend (R-1) or circuit evidence (E-1-R) into a strategy** until closed; both are named as Phase 2 inputs in `WHAT_WE_ARE_BUILDING.md`.

Recommended, non-blocking: make `test_n1` a ratio test (N-13); check `final_ref` uniqueness also guards the `order_id == instrument_id` convention; freeze the deposit re-anchor until validation passes (N-10); correct the two remaining "double-entry" docstrings (N-11); and either repair or delete `probe_b7bd8ba.py` so the committed evidence trail is reproducible (N-12).

---

## Appendix C — Reproduction Script for §16 Findings

Executed from the repository root with `PYTHONIOENCODING=utf-8 PYTHONPATH=src`. Output quoted in 16.1 and 16.2 matches the run of 2026-11-11.

```python
import datetime, sys, time
from decimal import Decimal
sys.path.insert(0, "src")
from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.types import (ExecutionOrder, FillStatus, OrderProduct,
    OrderSide, OrderType)
from signal_core.portfolio import Portfolio

D = datetime.date(2026, 11, 11)
M = TransactionCostModel()

def mk(inst, side, qty, price, date=D, order_id=None):
    price = Decimal(price)
    costs = M.compute_costs(trade_date=date, side=side, product=OrderProduct.DELIVERY,
        quantity=qty, price=price, round_to_paise=False)
    o = ExecutionOrder(instrument_id=inst, side=side, order_type=OrderType.MARKET_ON_OPEN,
        quantity=qty, product=OrderProduct.DELIVERY, signal_date=date - datetime.timedelta(days=1),
        target_date=date, order_id=order_id)
    return ExecutionFillResult(order=o, status=FillStatus.FILLED, fill_date=date,
        latency_sessions=1, filled_quantity=qty, unfilled_quantity=0,
        executed_price=price, slippage=None, costs=costs,
        circuit_evidence_present=True, rejection_reason=None)

# N-1 timing / bound
for n in (1000, 4000, 16000):
    pr = Portfolio(initial_capital=Decimal("100000000.00"), initial_date=D)
    t0 = time.perf_counter()
    for i in range(n):
        pr.process_fill(mk(f"I{i:06d}", OrderSide.BUY, 1, "10"), enforce_risk_limits=False)
    dt = time.perf_counter() - t0
    print(n, round(dt / n * 1e6, 2), "us/fill", len(pr._processed_fill_instances))

# N-9 eviction replay
pr = Portfolio(initial_capital=Decimal("100000000.00"), initial_date=D)
old = mk("INFY", OrderSide.BUY, 1, "10")
pr.process_fill(old, enforce_risk_limits=False)
for i in range(10000):
    pr.process_fill(mk(f"J{i:06d}", OrderSide.BUY, 1, "10"), enforce_risk_limits=False)
print("pinned old?", id(old) in pr._processed_fill_instances)
pr.process_fill(old, enforce_risk_limits=False)
print("INFY qty after replay:", pr.get_position("INFY").quantity)   # 2

# N-8 generated-reference collision
p = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
p.ledger.deposit(D, Decimal("100.00"), reference_id="FILL_INFY_2026-11-11#1")
p.ledger.record_fill(mk("INFY", OrderSide.BUY, 10, "1000"))
refs = [e.reference_id for e in p.ledger.entries]
print(refs, len(refs) != len(set(refs)))                            # duplicate True

# N-10 deposit anchor mutation on rejection
q = Portfolio(initial_capital=Decimal("10000.00"))
try:
    q.process_fill(mk("INFY", OrderSide.BUY, 100, "1000", date=datetime.date(2026, 11, 20)),
                   enforce_risk_limits=False)
except Exception as e:
    print(type(e).__name__)
print("deposit date now:", q.ledger.entries[0].trade_date)           # 2026-11-20

# N-3 simulator remainder end to end
from signal_core.contracts.price_bar import PriceBar
from signal_core.contracts.exchange_series import ExchangeSeries, ExchangeSessionObservation
d1, d2 = datetime.date(2026, 11, 11), datetime.date(2026, 11, 12)
sim = ExecutionFillSimulator(trading_calendar=[d1, d2])
def obs(d, vol, inst="INFY"):
    return ExchangeSessionObservation(instrument_id=inst, trade_date=d, raw_series_code="EQ",
        series_classification=ExchangeSeries.EQ, isin="INE009A01021",
        price_bar=PriceBar(instrument_id=inst, trade_date=d, open=Decimal("1000"),
            high=Decimal("1020"), low=Decimal("990"), close=Decimal("1010"), volume=vol))
o1 = ExecutionOrder(instrument_id="INFY", side=OrderSide.BUY, product=OrderProduct.DELIVERY,
    quantity=100, signal_date=datetime.date(2026, 11, 10), target_date=d1,
    order_id="ORD1", allow_partial_fill=True)
r1 = sim.simulate_order(o1, obs(d1, 2000), average_daily_turnover=Decimal("100000000"))
o2 = ExecutionOrder(instrument_id="INFY", side=OrderSide.BUY, product=OrderProduct.DELIVERY,
    quantity=r1.unfilled_quantity, signal_date=d1, target_date=d2, order_id="ORD1")
r2 = sim.simulate_order(o2, obs(d2, 10000000), average_daily_turnover=Decimal("100000000"))
print(r1.status.value, r1.fill_id, "|", r2.status.value, r2.fill_id)
```

---

## 17. §16 Remediation Re-Audit (`b2e8bbd`) — Final Phase 1E Verdict (2026-11-11)

**Commit audited:** `b2e8bbd` — *"Remediate Audit §16 findings: generated reference uniqueness (N-8), lazy deposit isolation (N-10), single-entry terminology (N-11), reproducible probe (N-12), and hardened ratio regression test (N-13)"* (7 files, +504/−50; includes this report's §16 as committed evidence).
**Environment:** unchanged (CPython 3.13.5 win32, pytest 8.3.4).
**Suite (measured on the audited commit):** `138 passed in 1.38s`, exit 0, zero warnings (29 of them in `test_portfolio.py`, 2 of those new: N-8 and N-10).
**Probes:** independent re-derivation of every claimed fix plus the collision routes §16 named but did not exercise. Source was not modified by this audit.

### 17.1 §16 findings — closure, re-derived

| ID | Claimed fix | Measured result | Status |
|---|---|---|---|
| **N-8** | `candidate_ref not in _posted_reference_ids` on the generated branch | Explicit `FILL_INFY_2026-11-11#1` then anonymous INFY fill on the same date → `LedgerValidationError`; entries stay `['INIT_DEPOSIT', 'FILL_INFY_2026-11-11#1']`, cash `2000100.00`, counters `{}`, position `None`, pinned `0`. A subsequent anonymous fill on 11-12 posts `#1` — the rejected attempt consumed nothing. Re-run of the realistic simulator route (`fill_id` posted first, counter untouched) is also rejected. | **CLOSED** |
| **N-9** | Scope documented on `Portfolio` | Docstring states the 10,000-fill window and indefinite protection for id-bearing fills. Behaviour unchanged and now truthfully described; the probe's own section 7 reports the boundary. | **CLOSED (documented boundary)** |
| **N-10** | Re-anchor committed after validation | Rejected overdraft on 2026-11-20 leaves deposit date and `_last_trade_date` at the construction date, entries `1`, cash `10000.00`, nothing pinned. A subsequent valid fill on 11-21 anchors both to 11-21, after which an earlier date is correctly rejected as non-monotonic. | **CLOSED** |
| **N-11** | Single-entry terminology | `grep -rn "double-entry" src/` → no matches. | **CLOSED** |
| **N-12** | Reproducible probe | `python -m py_compile probe_b7bd8ba.py` succeeds; `python probe_b7bd8ba.py` runs to completion, exit 0, printing all 11 sections including `pinned size 10000 max 10000` and the N-2/N-5/N-8 behaviours. | **CLOSED** |
| **N-13** | Ratio-based regression test | `test_n1` now measures 1k and 4k with a `< 2.5` ratio and `< 250 µs` bounds. Independently measured ratios `1.07`, `1.09`, `1.23` (55–72 µs/fill), i.e. the guard now separates linear from quadratic (≈4×). | **CLOSED** |

### 17.2 Regression checks on the remediation itself

| Check | Result |
|---|---|
| Sequence ordinals remain gap-free after a ledger-level rejection | `#1` on 11-11, overdraft rejection on 11-12, next valid fill on 11-12 → `#1`, i.e. no hole. Counters remain `{('INFY', 11-11): 1}`. |
| Rejected fill is not consumed by the replay guard | After the N-8 rejection, `Pinned = 0`, so the rejection is attributable to the reference, not to object identity. |
| Collision leaves cash, positions and references intact | Cash, entries, counters and `get_position` unchanged; refs unique. |
| Chronology still enforced once anchored | Earlier-date posting after the anchor raises `Non-monotonic trade_date`. |
| Suite, optimized-warning posture | 138/138, no warnings. |

### 17.3 New observations (none gate-blocking)

| ID | Severity | Observation |
|---|---|---|
| N-14 | info | `CURRENT_STAGE_OF_WORK.md` now contains **two** `### Phase 2: Walk-Forward Strategy Engine & Deflated Sharpe Evaluation` sections (lines 250 and 257); the second is the stale block and omits the R-1 / E-1-R isolation note. Documentation duplication only. |
| N-15 | info (accepted) | After an explicit reference occupies `FILL_<inst>_<date>#1`, the generated branch refuses **every** subsequent anonymous fill for that instrument/date, because the ordinal cannot advance past the occupied candidate. This is loud fail-closed behaviour and was the requested design; if the anonymous fallback is expected to stay alive, mint the next free ordinal instead. |
| N-16 | info | `probe_b7bd8ba.py` section 11 prints `first id evicted? id(pr) not in pr._processed_fill_instances`, testing the Portfolio object rather than the first fill, so the line is always `True` and does not demonstrate eviction; the `pinned size 10000` line does. Evidence hygiene only. |

### 17.4 Gate, Phase 1E (final)

| Gate | Criterion | Result |
|---|---|---|
| G1 | Exact ledger arithmetic, paise posting, reconciled round trip | **PASS** |
| G2 | Fail closed with no state change on rejection | **PASS** (N-10 closed; re-derived) |
| G3 | Atomic fill posting with rollback | **PASS** (unchanged, re-exercised in probe §10) |
| G4 | One reconciled source for cash and basis | **PASS** |
| G5 | Cost basis / average price / realized PnL, no drift | **PASS** |
| G6 | Replay refused, distinct fills admitted | **PASS** — within the retained window and indefinitely for id-bearing fills; the boundary is documented (N-9) |
| G7 | O(1) guard, bounded memory | **PASS** (55–72 µs at 1k/4k; 10,000 cap) |
| G8 | References unique per fill, reproducible | **PASS** (N-8 closed; duplicates impossible on both explicit and generated paths) |
| G9 | Chronological ledger history | **PASS** |
| G10 | Concentration limit on deployed capital | **PASS** (carried, unchanged) |
| G11 | Exact drawdown comparison | **PASS** (carried, unchanged) |
| G12 | Mark-to-market fails closed on bad prices | **PASS** (carried, unchanged) |

**Verdict: 12 PASS / 0 FAIL — Phase 1E signed off.**

Every §16 finding is closed by measurement, not by restatement: the reference guard fires on both routes that can reach it, a rejected order no longer moves the opening deposit, ordinals survive rejection without holes, and the regression test can now distinguish linear from quadratic behaviour. Nothing in `b2e8bbd` regressed the Phase 1A–1D invariants (§16.3 still holds; suite 138/138).

**GO to Phase 2**, under the two conditions already recorded in `CURRENT_STAGE_OF_WORK.md`:
1. Weekly trend (R-1: intra-week missing sessions silently aggregated) must remain isolated from trade signals until calendar-aware aggregation is implemented.
2. Circuit-band evidence (E-1-R) still has no data source; no fill may be treated as a final, tradable record until that exists.

Recommended housekeeping only: remove the duplicated Phase 2 block (N-14) and fix the probe's eviction line (N-16).

**Unchanged `NOT RUN` register:** snapshot SHA-256 / fingerprint reproduction, 545-pair Bhavcopy recomputation, Phase 0 legacy assessment, and any strategy/DSR/Haircut-Sharpe metric (no strategy layer exists). No strategy verdict is expressed in this section.

---

## 18. Phase 2A Audit — Holdout Containment & Trial Registry (`bbcbb6c`) (2026-11-11)

**Commit audited:** `bbcbb6c` — *"feat(research): complete Phase 2A holdout containment and append-only trial registry"* (6 files, +1358/−13).
**Working tree:** five uncommitted edits adding a trailing blank line to each new file; no behavioural content. Audited state = `bbcbb6c`.
**Suite (measured):** `151 passed in 1.59s`, exit 0, zero warnings (138 + 13 new: 6 containment, 7 trials). The document states `1.99s`; timing only.
**Method:** every guarantee claimed in `CURRENT_STAGE_OF_WORK.md` was attacked directly. All results below are printed by executed probes, not inferred from the tests.

### 18.1 Claims that survive

| Claim | Evidence |
|---|---|
| Content tampering is detected | Editing a stored `hypothesis` → `RegistryTamperedError: Tampered record hash`. |
| Reordering is detected | Swapping records 2 and 3 → `DuplicateTrialError: Out-of-order sequence 1; expected 2`. |
| Chain-link tampering is detected | Rewriting `prev_hash` and recomputing `record_hash` → `RegistryTamperedError: Broken hash chain`. |
| Canonical hashing is key-order independent | `{"a":1,"b":2,"c":3}` and the reverse insertion order hash identically. |
| Exact Decimal variance | `1.50/1.70/1.90` → `0.04`, matching the closed form. |
| Overlapping folds are rejected | `train_end >= test_start` → `PartitionSpecValidationError`. |
| No float reaches the canonicaliser | `_canonicalize_value` raises on float; `int`/`str`/`Decimal`/mapping/sequence only. |

### 18.2 Findings

| ID | Sev | Finding | Measured evidence |
|---|---|---|---|
| **A-1** | **P1** | **Holdout opens with arbitrary sentinel content.** `expected_token_hash` defaults to `None`, and `check_partition_access` forwards it, so *any* non-empty file unlocks the holdout. | `HOLDOUT_UNLOCK` containing `banana` → `verify_holdout_unlock` `True`, `check_partition_access(spec, HOLDOUT, path)` **admitted**. The suite only tests the hash-supplied and empty-file paths, so nothing catches this. |
| **A-2** | **P1** | **Partition-string bypass.** The guard compares `partition.upper() == "HOLDOUT"` without normalising, while validation only requires non-empty/stripped *truthy* content. | `"HOLDOUT"`, `"holdout"`, `"Holdout"` rejected; `"holdout "` **admitted** into the registry with no authorisation. |
| **A-3** | **P1** | **`allow_holdout: bool` is an unauthenticated bypass of containment.** The registry keeps its own holdout policy and never consults a sentinel, so a caller writes holdout trials by passing `True`. This also means two independent holdout authorities exist, contradicting the single-authority rule the slice was meant to establish. | `append_trial(..., partition="HOLDOUT", allow_holdout=True)` → **admitted**, `seq=2`, no unlock path or hash consulted. |
| **A-4** | **P1** | **Truncation is undetectable, and `verify_integrity()` certifies the shortened registry.** A hash chain with no external head anchor cannot distinguish "5 trials" from "5 trials, last 3 deleted". DSR takes `N` from this registry, so understating the trial count directly inflates the significance verdict. | 5 records written, file truncated to 2 lines → `TrialRegistry(...).trial_count == 2`, `verify_integrity()` → **`True`**. |
| **A-5** | **P1 (doc)** | **The document states guarantees the code does not provide,** and types a gate verdict by hand. `"verified with content hash"` is contradicted by A-1; `"Any accessor for a sealed partition raises"` is vacuous — no data accessor exists (A-6); `"2A Gates: 5 / 5 PASS (measured via independent probe …)"` is a hand-typed label with no 2A probe committed (only `probe_b7bd8ba.py`, which covers Phase 1E). Violates §9.1 (verdicts computed, never typed). | `git show bbcbb6c --stat` lists no 2A probe; `ls *.py` shows only `probe_b7bd8ba.py`. |
| **A-6** | **P2** | **Containment is advisory, not binding.** `check_partition_access` never uses its `spec` argument, and no module outside `research/` calls it — nothing in the codebase reads price data through the guard. | `grep -rn "check_partition_access\|HoldoutSealedError\|PartitionRole" src --include=*.py` outside `research/` → **no matches**. |
| **A-7** | **P2** | **Concurrent appenders corrupt the registry.** `append_trial` trusts its in-memory tail and appends unconditionally, with no lock and no re-verification against disk. | Two registries opened on one file, one append each → two `seq=1` rows on disk; the next load raises `DuplicateTrialError` and the file needs manual reconstruction. |
| **A-8** | **P2** | **A missing trailing newline destroys the next record.** Append does not ensure the separator. | File stripped of its final newline loads fine (`1` record), then an append produces `RegistryTamperedError: Malformed JSON … Extra data` on reload. |
| **A-9** | **P2** | **`auto_verify=False` loads tampered records and then extends their chain.** A documented switch disables the integrity check the class exists to provide. | Tampered `sharpe_ratio=99.0` → default load `RegistryTamperedError` (correct); `auto_verify=False` loads `2` records reporting `99.0` and appends `seq=3`. |
| **A-10** | **P2** | **`embargo_sessions` is declarative and unverified.** `WalkForwardFold` checks only `train_end < test_start`; the stored embargo is never compared with the actual gap, so a fabricated embargo survives into a valid-looking `FOLD-SPEC-V1` fingerprint. | `train_end=2023-01-10`, `test_start=2023-01-11`, `embargo_sessions=5` → **accepted**, fingerprint `FOLD-SPEC-V1-84aaffea03602…`. |
| **A-11** | **P2** | **The two DSR inputs disagree on `N`.** `compute_trial_sharpe_variance` divides by `(#non-None Sharpes − 1)` while `trial_count` counts all trials; DSR must use the total attempted. The convention is unpinned, so 2B would silently inherit a choice. | `get_trial_sharpes()` filters `None`; `trial_count` does not. |
| **A-12** | **P2 (reproducibility)** | **Registry files are not byte-identical across platforms.** Append opens in text mode, so Windows writes `\r\n`. Any gate phrased as "identical registry file" cannot hold cross-platform. | `CRLF count: 1, LF count: 1` for a one-record file on this machine. |
| **A-13** | **P3** | Non-finite Decimals accepted into records (`sharpe_ratio=Decimal("NaN")` → stored, reloads). | Append and reload both succeed. |
| **A-14** | **P3** | Malformed records leak `KeyError` instead of `RegistryTamperedError`. | Line `{"seq":1,"trial_id":"M"}` → `UNTYPED KeyError: 'prev_hash'`. |
| **A-15** | **P3** | In-memory and reloaded records are not equal for Decimal params, though their hashes match (`Decimal('0.010')` vs `'0.010'`) — the R-2 representation-sensitivity carried forward. | `params equal → False`, `hashes equal → True`. |
| **A-16** | **P3** | Calendar sessions are not validated: duplicates and ordering are accepted, and duplicates silently absorb into fold windows. | `[d1,d1,d2,d3,d4]` accepted; fold produced without complaint. |
| **A-17** | **P3** | Anchored mode over-rejects: `min_required` always adds `train_sessions` even when the train window is pinned to index 0. | 6 sessions, `train=4, test=3, embargo=0, anchored=True` → rejected, although train `0..2` / test `3..5` is valid. |
| **A-18** | **P3** | `timestamp_utc` is an unvalidated free string — no ISO-8601 parse and no monotonicity, so trial chronology can be back-dated. | Any non-empty string accepted. |

### 18.3 Recomputed 2A gates

| Gate (from the committed plan) | Result | Basis |
|---|---|---|
| G2A-1 · sealed read raises | **FAIL** | No accessor exists; the guard is optional, admits arbitrary sentinel content (A-1), and has two string/flag bypasses (A-2, A-3). |
| G2A-2 · folds deterministic, disjoint, exhaustive over IS | **PARTIAL** | Determinism and disjointness hold; test windows tile only the tail, so most of IS is never out-of-fold evaluated, and calendar validity is unchecked (A-16). |
| G2A-3 · shuffled sweep yields an identical registry file | **FAIL** | Not measured by the suite (only key-order hashing is), and byte-identity is platform-dependent (A-12). |
| G2A-4 · chain verifies; sample record recomputes | **FAIL** | True for content edits, false for truncation (A-4), transplant, and `auto_verify=False` (A-9). |
| G2A-5 · schema ready for 2B | **PASS** | All nine DSR fields present and round-tripped, with the `N` ambiguity recorded as A-11. |

**Verdict: Phase 2A is NOT verified — NO-GO to Phase 2B.**

The registry's tamper-evidence is real for content edits, and the fold geometry is sound. But the slice exists to make one promise — the holdout cannot be reached, and the trial count cannot be quietly reduced — and both fail open: an arbitrary file unlocks the holdout, and a truncated registry reports `verify_integrity() == True` while having lost three of five trials. Since DSR consumes exactly that count, continuing to 2B would build significance statistics on an adjustable `N`.

**Minimum closure set before 2B:**
1. Make `expected_token_hash` required (no `None` default) or bind the token into the partition fingerprint; reject content that does not match.
2. Normalise the partition value (`strip().upper()`) and validate it against `PartitionRole`, not an ad-hoc string comparison.
3. Remove `allow_holdout`; route every holdout access through one shared authorisation function.
4. Anchor the registry head (count + final `record_hash`) outside the appendable file and verify it on load; make truncation a `RegistryTamperedError`.
5. Re-verify the on-disk tail before appending (tail hash + size) and refuse concurrent or separator-less writes.
6. Bind a fold's `embargo_sessions` to its actual session gap, and settle the DSR `N` convention (total trials) in the 2B contract.
7. Rewrite the 2A status claims in `CURRENT_STAGE_OF_WORK.md` to computed gate results, and commit the 2A probe that produces them.

**Unchanged `NOT RUN` register:** all Phase 0–1B empirical items, and every Phase 2B/2C metric (no significance, strategy or walk-forward evaluation module exists).

---

## 19. Phase 2A Re-Audit — §18 Remediation (`3cbcba4`) (2026-11-11)

**Commit audited:** `3cbcba4` — *"fix(research): remediate §18 audit findings A-1 through A-18 for Phase 2A"* (9 files, +1619/−185).
**Working tree:** two uncommitted edits, a trailing blank line each in `probe_phase2a.py` and `scripts/verify_phase2a_containment_and_trials.py`; no behavioural content.
**Suite (measured):** `163 passed in 1.53s`, exit 0, zero warnings (138 + 10 containment + 15 trials). The document states `1.67s`; timing only.
**Committed probe (measured):** `python probe_phase2a.py` → exit 0, `ALL 5 GATES PASSED (100%)`. The probe now accumulates real booleans into `all_passed`, so its verdict is computed rather than typed — the A-5 mechanism is fixed.
**Method:** each §18 finding was re-attacked with an independent probe, not re-read from the new tests.

### 19.1 §18 findings — closure status

| ID | Status | Independent evidence |
|---|---|---|
| A-1 arbitrary sentinel content | **CLOSED** | `verify_holdout_unlock(path)` → `TypeError: missing 1 required positional argument: 'expected_token_hash'`; `holdout_token_hash` is now a required 64-hex `PartitionSpec` field and is bound into `PART-SPEC-V1`; content `banana` against the human token hash → `HoldoutSealedError`. |
| A-2 partition string bypass | **CLOSED** | `partition="holdout "` → `HoldoutSealedError` (normalised then enum-validated in both modules). |
| A-3 `allow_holdout` bypass | **CLOSED** | Parameter no longer exists (`inspect.signature` → `False`); HOLDOUT without a `PartitionSpec` raises `HoldoutSealedError`; with spec + valid sentinel it appends, as intended. `trials.py` now imports `check_partition_access` — single authority. |
| A-4 truncation | **PARTIAL — remains open in the versioned workflow** | Manifest present: 5→2 truncation → `RegistryTamperedError`. Manifest **absent**: loads with `count=2` and `verify_integrity()` → **`True`**. `.gitignore:30` is `*.manifest`, so any clone, restore or archive of a committed registry loses the anchor and silently restores the A-4 defect. See B-1. |
| A-5 doc overclaim / typed verdict | **PARTIAL** | A probe is now committed and its verdict is computed. The two gate-basis sentences still overstate what is measured (B-6). |
| A-6 advisory containment | **PARTIAL** | `check_partition_access` now consumes `spec`, and `filter_partition_observations` exists. It has **zero callers** — `grep -rn filter_partition_observations src --include=*.py` outside `research/` → no matches. Still advisory, now with an unused accessor. |
| A-7 concurrent corruption | **CLOSED (detection)** | Second appender → `RegistryTamperedError: Concurrent modification detected: on-disk record count (1) disagrees with in-memory count (0)`. Check-then-write is still unlocked (TOCTOU window), which is acceptable for fail-closed detection. |
| A-8 missing trailing newline | **CLOSED** | Rejected on load *and* on append. |
| A-9 `auto_verify=False` | **CLOSED** | Parameter removed; all loads verify. |
| A-10 declarative embargo | **PARTIAL** | A `WalkForwardFold` now rejects a 1-day gap claiming `embargo_sessions=5`; the generator's session-exact check is intact. The class-level check compares **calendar days** to a **session count** (B-5). |
| A-11 `N` ambiguity | **CLOSED (documentation)** | `total_trial_count` (authoritative `N`) vs `evaluated_trial_count` (`N_eval`), stated in the property docstrings. Must still be pinned in the committed 2B config, not only in prose. |
| A-12 CRLF | **CLOSED** | `CRLF=0, LF=1` on a fresh append; registry and manifest both use `newline="\n"`. |
| A-13 non-finite Decimal | **CLOSED** | `sharpe_ratio=Decimal("NaN")` → `TrialRegistryError`. |
| A-14 untyped `KeyError` | **CLOSED** | Record missing `prev_hash` → `RegistryTamperedError`. |
| A-15 Decimal param parity | **CLOSED** | In-memory and reloaded `canonical_params` compare equal. |
| A-16 calendar validation | **CLOSED** | Duplicate sessions and non-increasing order rejected. |
| A-17 anchored over-rejection | **CLOSED** | Anchored mode no longer adds `train_sessions` to `min_required`. |
| A-18 timestamp chronology | **CLOSED** | `2020-01-01T00:00:00Z` after a 2026 record → `Non-monotonic timestamp ... precedes previous record`. |

Score: **13 closed, 5 partial (A-4, A-5, A-6, A-10, A-11), 0 unchanged.** The three P1 holdout bypasses that blocked §18 are genuinely closed.

### 19.2 Remaining findings

| ID | Sev | Finding | Measured evidence |
|---|---|---|---|
| **B-1** | **P1** | **The truncation anchor is optional and deliberately unversioned.** `_load_and_verify` treats a missing manifest as "no anchor" instead of "anchor missing"; `.gitignore` excludes `*.manifest`, so the file that makes truncation detectable is exactly the one git will not carry. A committed registry restored from git, cloned, or audited on another machine has no anchor and `verify_integrity()` certifies a truncated file as intact. | `truncate, manifest DELETED` → `LOADED count=2 verify_integrity=True`; `git check-ignore -v data/registry.jsonl.manifest` → `.gitignore:30:*.manifest`. |
| **B-2** | **P2** | **`verify_integrity()` destroys in-memory state before verifying.** It clears `_records`/`_trial_ids` and re-populates them as it walks the file, so a raised `RegistryTamperedError` leaves the object holding the records read up to the failure. A caller that catches the error (the obvious pipeline pattern) then reads a silently reduced `total_trial_count` — the A-4 harm reached through a different door. | Registry with 4 records, record 2 tampered → `verify_integrity()` raises, `trial_count` becomes **1** (was 4). |
| **B-3** | **P2** | **An interrupted append bricks the registry, and the only recovery is B-1.** The record is written first, the manifest second, so a crash between them leaves a valid file failing the anchor check; `_write_manifest` is documented as "atomic" but is a truncating `open("w")` with no temp-file rename and no `fsync`. Recovery means deleting the manifest, which re-opens B-1. | Manifest hand-set to `total_trials=2` with 3 records on disk → `RegistryTamperedError: registry has 3 records, but authoritative manifest specifies 2`. |
| **B-4** | **P2** | **The write path accepts values that make the ledger unloadable.** `append_trial(observation_count=True)` is accepted and hashed; reload coerces with `int(...)` → `1`, the payload hash no longer matches, and the registry can never be opened again. `TrialRecord.__post_init__` validates the six Decimal fields but not `observation_count`/`returns_digest`, and `from_dict` coerces one but not the other. | Append accepted; reload → `RegistryTamperedError: Tampered record hash for trial 'B1'`. |
| **B-5** | **P3** | **`embargo_sessions` is still checked as calendar days, not sessions.** The class-level guard is a lower bound: a fold claiming a 5-session embargo with only 4 trading sessions in the gap is accepted and receives a valid `FOLD-SPEC-V1` fingerprint. Trust therefore rests on the generator, which is correct. | `train_end=2023-01-06` (Fri), `test_start=2023-01-13` (Fri), `embargo_sessions=5`, 4 sessions between → accepted, `FOLD-SPEC-V1-4445647e3…`. |
| **B-6** | **P3 (doc)** | **Two gate bases still overstate what the probe measures.** G2A-1 credits `filter_partition_observations` with enforcing containment "before observation streams can reach feature or evaluation logic" — the function has no callers (A-6). G2A-3 is titled "Shuffled parameter sweep reproducible & byte-identical", but measures key-order hashing and LF bytes only; no sweep is executed, so the gate as originally defined is still unmeasured. | `grep` → no callers; probe G2A-3.1/3.2 bodies assert hashing and newline counts. |
| **B-7** | **Residual (design)** | **The seal's authority is the `PartitionSpec`, not cryptography.** `holdout_token_hash` and the unsigned manifest are both caller-authored, so any actor who can write code can bind a token it controls (`sha256("banana")`) and open the holdout; nothing distinguishes a human-authored spec from a generated one. No code fix exists locally — the control is that the spec and the committed criteria are human-reviewed. Worth stating in the doc instead of implying a cryptographic barrier. | `spec(holdout_token_hash=sha256("banana"))` + file containing `banana` → **admitted**; the human-token spec seals it. |

### 19.3 Recomputed 2A gates

| Gate | Result | Basis |
|---|---|---|
| G2A-1 · sealed read raises | **PASS** | Three original bypasses closed and re-attacked: A-1/A-2/A-3 all fail closed. Caveats: the accessor is unwired (A-6) and the token authority is the spec (B-7). |
| G2A-2 · folds deterministic, disjoint, calendar-validated | **PASS** | Determinism, disjointness, calendar validation, anchored mode and exact session embargo in the generator all verified. Test windows still tile only the tail of IS — a design property to carry into 2C, not a defect. |
| G2A-3 · shuffled sweep yields an identical registry file | **FAIL** | Not measured: no sweep is executed. Key-order hashing and LF byte-stability are verified; the gate as written remains unmet (B-6). |
| G2A-4 · chain verifies; truncation fails closed | **PARTIAL** | True with the manifest present (content edits, reordering, head mismatch, concurrent desync, separator loss). False whenever the manifest is absent (B-1), and a failed check corrupts the in-memory count (B-2). |
| G2A-5 · schema ready for 2B | **PASS** | All nine fields round-trip; `N` vs `N_eval` pinned in code; non-finite and malformed inputs rejected. |

**Verdict: Phase 2A is not yet signed off. Two-P1-to-P2 closure set before Phase 2B.**

The remediation is real work and most of it holds under attack: the holdout is no longer reachable by arbitrary content, whitespace, or a boolean flag, and the hash chain now detects reordering, chain breaks, concurrent desync and separator loss. What keeps 2A open is narrower: the anti-truncation anchor is a sibling file that is optional to the loader and excluded from version control, so the property that matters — "the trial count cannot be quietly reduced" — holds only on the one machine where the untracked file happens to survive. That is the number DSR consumes.

**Closure set for 2B:**
1. Make the manifest mandatory: a non-empty registry with no manifest raises `RegistryTamperedError` (B-1).
2. Stop ignoring `*.manifest` in `.gitignore`, and commit registries together with their anchors (B-1).
3. Verify into a temporary list and assign to `self._records` only after the walk succeeds, so a failed `verify_integrity()` leaves `trial_count` unchanged (B-2).
4. Write the manifest via temp-file + `os.replace`, or write it before the record and treat a stale anchor as a recoverable state with an explicit repair API (B-3).
5. Validate `observation_count` (int, not bool) and `returns_digest` (str) in `TrialRecord.__post_init__` (B-4).
6. Restate G2A-1 and G2A-3 in the document to what is measured, and pin the DSR `N` convention in the committed 2B config rather than in prose (B-6, A-11).

**Carried as accepted residuals:** `embargo_sessions` remains calendar-day-bounded at class level while the generator is session-exact (B-5); the holdout seal is only as strong as human authorship of `PartitionSpec` (B-7).

**Unchanged `NOT RUN` register:** all Phase 0–1B empirical items, and every Phase 2B/2C metric.

---

## 20. Phase 2A Re-Audit — §19 Remediation (`b4e9149`)

**Commit audited:** `b4e9149` — *"fix(research): remediate §19 audit findings B-1 through B-4 and pin DSR N criteria"* (9 files, +455/−76).
**Working tree:** clean (`git status --short` → empty).
**Suite (measured):** `166 passed in 1.84s`, exit 0 (138 + 10 containment + 18 trials). The document states `1.60s`; timing only, and the test count matches.
**Committed probe (measured):** exit 0, `ALL MEASURED CHECKS PASSED (100%)` — the wording no longer asserts five passing gates, which is the correct claim once G2A-3 is split.
**Audit integrity:** §18 and the §19 body were committed verbatim; only the section-index line changed. This section supersedes the *status* of A-4, A-5, A-6, A-11, B-1…B-4 below without rewriting them, so the trail of what was believed when remains readable.

### 20.1 §19 findings — closure status

| ID | Status | Independent evidence |
|---|---|---|
| **B-1** manifest optional / ignored | **CLOSED** | Truncate 5→2 with the manifest present → `RegistryTamperedError: Registry truncation detected: registry has 2 records, but authoritative manifest specifies 2 trials`. Truncate with the manifest **deleted** → `RegistryTamperedError: Missing authoritative manifest anchor at ... for non-empty registry`. Higher-severity hole from §19 is gone. `.gitignore` no longer carries `*.manifest`; `git check-ignore -v data/registry.jsonl.manifest` now exits 1 (not ignored). A third check was added: `last_trial_id` must match the manifest, so a forged tail cannot reuse a valid head hash. |
| **B-2 state destroyed on failed verify** | **CLOSED** | 4-record registry with record 2 tampered → `verify_integrity()` raises `RegistryTamperedError`, `trial_count` **4 before / 4 after**. `_load_and_verify` now builds `temp_records`/`temp_trial_ids` and assigns only after the full walk and the anchor check succeed. A catch-and-continue caller can no longer read a reduced `N`. |
| **B-3 interrupted append** | **PARTIAL (downgraded P2→P3)** | Manifest replacement is genuinely atomic now: unique `.tmp_<pid>_<ns>` sibling, `flush()` + `os.fsync()`, `os.replace()`, temp unlinked on failure, and no residue observed after a successful append (`manifest tmp files left: []`). The **ordering** gap is unchanged: appending the record first and the manifest second means a crash in between leaves 3 records against a 2-record anchor → `RegistryTamperedError: Registry truncation detected: registry has 3 records, but authoritative manifest specifies 2 trials`, and a fresh `TrialRegistry(path)` cannot open it. There is still no repair entry point (`repair`/`rebuild_manifest`/`recover` → `[]`). Severity drops because the failure is loud and fail-closed — it blocks reads rather than silently certifying a wrong `N` — but an operator restarting after a crash has no supported way back. See C-1. |
| **B-4 write path accepts unreadable values** | **CLOSED** | `observation_count=True` → `TrialRegistryError: observation_count must be a non-negative integer`; `returns_digest=123` → `TrialRegistryError: returns_digest must be a non-empty stripped string`. Valid values (`observation_count=10, returns_digest="sha256:abc"`) append and reload. Read path matches: a JSON `observation_count: 1.0` in the file → `RegistryTamperedError: Field 'observation_count' must be non-negative int`. `seq` and all ten string fields are type-checked on both paths, and `from_dict` no longer coerces. |
| **B-6 doc overclaim (G2A-3 sweep, A-6 accessor)** | **CLOSED** | The gate table now reads `NOT RUN (Sweep) / PASS (Hashing & LF)` with the deferral stated; the probe prints `[INFO] G2A-3: Strategy grid sweep unmeasured in 2A (deferred to Phase 2C strategy engine per B-6)` instead of a PASS, and the final line is `ALL MEASURED CHECKS PASSED`. A-6's bullet now carries "unwired to external feature logic until Phase 2C strategy engine". Both are accurate descriptions of the code. |
| **A-11 `N` convention in prose only** | **CLOSED** | `configs/go_no_go_criteria.yaml` now pins `dsr_trial_count_basis: TOTAL_ATTEMPTED_TRIALS` and `dsr_sharpe_variance_divisor: EVALUATED_TRIALS_MINUS_ONE`; `GoNoGoCriteria` carries both as typed fields and `tests/unit/test_criteria.py` asserts them against the committed file. The constant lives where §9 of `AGENTS.md` requires, not in a docstring. |

Score: **5 closed, 1 partial (B-3, now P3), 0 unchanged.** Every P1/P2 from §19 is closed.

### 20.2 New findings

| ID | Sev | Finding | Measured evidence |
|---|---|---|---|
| **C-1** | **P3** | **No recovery path after an interrupted append.** The two-file update (record then manifest) is not transactional, and nothing in the API can reconcile a stale anchor with a longer file. Recovery requires hand-editing or deleting the manifest — the latter is now refused as a load, so the registry is simply unopenable until a human intervenes. Acceptable for an audit ledger (loud, fail-closed, never silently wrong), but should be either a documented `rebuild_manifest_from_file(path)` with an explicit human-confirm argument, or the record written after the manifest so the weaker state is a duplicate-tail rather than a blocked registry. | 3 records vs 2-record anchor → `RegistryTamperedError`; `[m for m in dir(TrialRegistry) if repair/rebuild/recover]` → `[]`. |
| **C-2** | **P3 (residual)** | **Truncating a registry to an empty file and deleting its manifest yields a clean, empty registry.** `lines` is empty and `manifest is None`, so both checks are skipped: `count=0, verify_integrity()=True`. No local mechanism can distinguish "new registry" from "audit trail wiped"; the only controls are that the registry and its anchor are now both versioned files, so `git diff`/review exposes the deletion, and that `N` feeding DSR comes from a registry whose history is in the repository. Worth one sentence in the 2B significance doc rather than a code change. | `p.write_text("")` + `manifest.unlink()` → `loads, count= 0 verify= True`. |

**Accepted residuals carried forward unchanged:** B-5 (`embargo_sessions` calendar-day-bounded in `WalkForwardFold`; the generator remains session-exact), B-7 (seal authority is the human-authored `PartitionSpec`, not a signature), A-6 (containment accessor still has no caller outside `research/` and its tests).

### 20.3 Recomputed 2A gates

| Gate | Result | Basis |
|---|---|---|
| G2A-1 · sealed read raises | **PASS** | Unchanged from §19 and still holds under re-attack. |
| G2A-2 · folds deterministic, disjoint, calendar-validated | **PASS** | Unchanged. |
| G2A-3 · shuffled sweep yields an identical registry file | **NOT RUN** | Correctly declared as deferred to 2C. The hashing/LF half passes; the gate as originally written is unmet by design, not by omission. |
| G2A-4 · chain verifies; truncation fails closed | **PASS** | Now true unconditionally: anchor present, anchor absent, forged tail, reordering, content edit, concurrent desync, separator loss all raise. Failed verification no longer mutates state. Residual C-1 (recovery) and C-2 (empty reset) are operational, not detection, gaps. |
| G2A-5 · schema ready for 2B | **PASS** | Nine fields round-trip; write and read paths agree on types; `N` and variance divisor pinned in committed config and asserted by test. |

**Verdict: Phase 2A is signed off. GO to Phase 2B.**

Every blocker from §18 and §19 is closed and verified by independent execution, not by the commit message or the repository's own probe: the holdout cannot be opened by arbitrary content, whitespace, casing, or a boolean flag; the trial count cannot be quietly reduced by truncation, a deleted anchor, a forged tail, or a caught verification failure; the ledger cannot be bricked by a public API call; and the DSR `N` convention now lives in the committed criteria file that `AGENTS.md` requires. The two remaining items are operational — how an operator recovers from a crash mid-append (C-1) and the fact that a full wipe of both files is only detectable through version control (C-2) — and neither permits a silently wrong `N` to reach a report.

**Unchanged `NOT RUN` register:** all Phase 0–1B empirical items, and every Phase 2B/2C metric.

---

## 21. Phase 2B — Statistical Significance Engine (`eafdc14`)

**Commit audited:** `eafdc14` — *"feat(research): implement Phase 2B statistical significance engine (DSR and Haircut Sharpe)"* (9 files, +1526/−21).
**Working tree:** `probe_phase2b.py` and `scripts/verify_phase2b_significance.py` modified with a trailing newline only.
**Suite (measured):** `180 passed in 1.70s`, exit 0 (166 + 14 significance). The document states `1.86s`; timing only.
**Committed probe (measured):** exit 0, `ALL MEASURED GATES PASSED (100%)`.
**Method:** the estimators and both statistics were re-implemented from the papers' formulas in a separate script and compared numerically; then the decision path was attacked for fail-open behaviour, which is where the gate's real risk lies.

### 21.1 What is verified correct

| Claim | Evidence |
|---|---|
| DSR formula (Bailey & López de Prado 2014) | Independent re-implementation — `SR* = sqrt(V/q)·[(1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(Ne))]`, `z = (SR_d - SR*_d)·sqrt(T-1)/sqrt(1 - γ3·SR_d + ((γ4-1)/4)SR_d²)`, `DSR = Φ(z)` — reproduces the engine to the printed 6 decimals on three parameter sets: `0.626502`, `0.618962`, `0.003381`, with `SR*` agreeing to `1.265301`, `0.497932`, `3.687703`. Dimensionally consistent: trial Sharpe variance is treated as annualized and de-annualized by `sqrt(q)` before use. |
| Monotone decay in `N` | `SR=1.50, V=0.25, T=500`: `0.982761, 0.898648, 0.780770, 0.629617, 0.485234` for `N = 1, 5, 20, 100, 500` — matches the document's G2B-2 row exactly. |
| Haircut Sharpe (Harvey & Liu 2015, Bonferroni) | `SR=2.00, T=1250`: `2.000000 (0%)`, `1.840276 (7.99%)`, `1.691856 (15.41%)`, `1.503433 (24.83%)`, `1.190940 (40.45%)` — matches the G2B-4 row. `t = SR·sqrt(T_years)` is dimensionally correct against the annualized Sharpe; non-positive Sharpe returns a 100% haircut rather than a sign-flipped one. |
| Float containment | Every result field is `Decimal`/`int`/`str`; floats exist only in `Φ`, `Φ⁻¹`, the Euler–Mascheroni constant, and `sqrt` of already-validated scalars. Ledger/position/portfolio do not import the module. |
| Boundary hygiene | `Float` → `Decimal` conversion is quantized to 6 decimals when leaving the boundary; `N = 10¹²` produces finite, in-range output. |
| `N` / `N_eval` wiring | `evaluate_strategy_significance` resolves `N` from `criteria.dsr_trial_count_basis` against `registry.total_trial_count`, and `V` from `registry.compute_trial_sharpe_variance()`; both are tagged onto every result. The DSR `N` convention and variance divisor are read from committed `configs/go_no_go_criteria.yaml` — auditor conditions 1 and 3 from §20 hold. |

Not verified by me: the G2B-1 claim that `0.900397` matches the published paper "bit-for-bit at 4 decimal places". The paper text is not in the repository; what is established is that the engine agrees with an independent transcription of the published formula, not with the paper's printed example.

### 21.2 Findings

| ID | Sev | Finding | Measured evidence |
|---|---|---|---|
| **D-1** | **P1** | **A registry with fewer than two recorded Sharpe ratios silently deletes the entire multiple-testing penalty while still tagging `N`.** `TrialRegistry.compute_trial_sharpe_variance()` returns `Decimal("0.00")` by design when `N_eval < 2`; `compute_deflated_sharpe_ratio` then sets `SR* = 0` (its `variance_ann <= 0` branch) and `evaluate_strategy_significance` passes the value straight through with no guard. The report still carries `trial_count_n = 50`, so it asserts a 50-trial deflation that was never applied. This is a verdict-flipping hole in the exact test that exists to prevent overfitting, reached by an ordinary workflow — `append_trial(sharpe_ratio=None)` is legal for every trial that was not individually evaluated. | Same strategy, same `N=50`, `T=500`, `SR=1.30`: with `V=0` → `SR*=0.000000`, `DSR=0.966639` → **PASS**; with the registry's own dispersion `V=0.3367` → `SR*=1.320844`, `DSR=0.488273` → **FAIL**. End-to-end: 50 trials with one `sharpe_ratio` → `N=50, N_eval=1, V=0.00`, integration verdict `PASS`. |
| **D-2** | **P2** | **A negative Mertens variance term is replaced by a fabricated denominator instead of raising.** `_compute_dsr_float` does `if variance_term <= 0.0: denom = 1e-6`. For impossible inputs (high Sharpe with strong positive skew) the term legitimately goes negative; the fallback then turns it into a denominator of one millionth and reports near-certainty. Fail-closed behaviour would be `InvalidSampleError`. | `SR_ann=4.74, V=0.01, T=100, N=10, γ3=5.00, γ4=3.00` → `z = 2,883,725.206350`, `DSR = 1.000000`, verdict `PASS`. Mirror case `γ3=-5.00` → `z = 1.808039`, `DSR = 0.964700` — sane, confirming the asymmetry is the sign guard, not the data. |
| **D-3** | **P3** | **`kurtosis_convention` can silently corrupt the DSR.** The Mertens term is `((γ4 - 1)/4)·SR_d²`, valid only for **raw** kurtosis. `evaluate_strategy_significance` forwards whatever `criteria.kurtosis_convention` produces; with `EXCESS_NORMAL_ZERO` the value is 3 lower, and for fat-tailed data whose excess kurtosis is still positive the `kurtosis <= 0` guard does not fire — the statistic is simply computed with the wrong moment. The loader blesses both conventions. | Same series, `SR=2.00, V=0.25, T=500, N=100`: `DSR(γ4=41.5033) = 0.832203` vs `DSR(γ4=38.5033) = 0.833457`. Small in magnitude at realistic daily Sharpe, but silent. |
| **D-4** | **P3** | **The criteria loader blesses a variance-divisor value the engine rejects.** `dsr_sharpe_variance_divisor` accepts `EVALUATED_TRIALS_MINUS_ONE` and `TOTAL_TRIALS_MINUS_ONE`, but `evaluate_strategy_significance` implements only the first and raises `Unsupported dsr_sharpe_variance_divisor` for the second. Fail-closed, but a committed configuration the loader reports as valid cannot produce a report. | `criteria.replace(dsr_sharpe_variance_divisor="TOTAL_TRIALS_MINUS_ONE")` → `SignificanceError: Unsupported …`. |
| **D-5** | **P3** | **No consistency check between `N` and `N_eval`.** `evaluated_trial_count > trial_count_n` is accepted and tagged verbatim, producing a self-contradictory report (`N=2, N_eval=50`). | `compute_deflated_sharpe_ratio(..., trial_count_n=2, evaluated_trial_count=50)` → accepted, tags `2 / 50`. |
| **D-6** | **P3** | **The verdict is computed on a 6-decimal rounding of the statistic.** Both results quantize before returning, and `evaluate_strategy_significance` compares the rounded `Decimal` against the threshold, so a true `0.9499996` is a `PASS`. I could not construct a case that flips at the committed `0.95` threshold in a bounded search, so impact is theoretical; the principled fix is to compare the unrounded statistic and keep two fields (raw and reported). | No flip found scanning `T ∈ [150,1200), N ∈ [2,300)` at `SR=0.75, V=0.05`. |
| **D-7** | **Residual** | **`SignificanceReport` has no `NOT RUN` / `UNDEFINED` state.** Every report carries a `PASS`/`FAIL` verdict for DSR and Haircut; there is no representation for "not computable" (which D-1 currently masquerades as). §9.3 of `AGENTS.md` requires unrun or inapplicable metrics to be stated as `NOT RUN`. | Dataclass fields are `dsr_verdict`/`haircut_verdict`/`overall_verdict: str`, populated only with `"PASS"`/`"FAIL"`. |

### 21.3 Recomputed 2B gates

| Gate | Result | Basis |
|---|---|---|
| G2B-1 · DSR reproduces published worked example | **NOT VERIFIED** | Engine matches an independent transcription of the formula exactly; the paper's printed example is external to the repository and was not checked. |
| G2B-2 · DSR decays monotonically in `N` | **PASS** | Recomputed, matches to every printed digit. |
| G2B-3 · bit-for-bit reproducibility | **PASS** | Deterministic pure-Decimal estimators over a float-free computation of the moments; quantization is stable. |
| G2B-4 · Haircut decreases monotonically in `N` | **PASS** | Recomputed, matches to every printed digit. |
| G2B-5 · SIG-FLOAT-BOUNDARY isolation | **PASS** | Floats confined to `Φ`/`Φ⁻¹`; report fields Decimal; no ledger/position/portfolio import. |
| G2B-6 · DSR/Haircut verdicts computed, `N` tagged, conventions from committed config | **FAIL** | Verdicts and tags are computed, and conventions are read from `configs/go_no_go_criteria.yaml` — but D-1 lets a report assert `N=50` while applying none of the penalty, and D-2 manufactures certainty from an invalid variance term. |

**Verdict: Phase 2B is not yet signed off. Two-item closure set before Phase 2C.**

The estimators and both published statistics are correct, and the wiring honours the §20 conditions: `N` comes from the registry via the committed convention, every result is tagged, and floats do not escape the normal-distribution boundary. What blocks sign-off is the decision path around the statistics rather than the statistics themselves: the one input that switches the whole multiple-testing penalty off — a trial Sharpe variance of zero — is reachable by legitimate use of the registry, produces a report that still says `N=50`, and flips a `FAIL` into a `PASS`. A gate whose failure mode is "reports maximum confidence from a value that could not be computed" cannot be the gate that certifies anti-overfitting.

**Closure set for 2C:**
1. When `N > 1`, require `N_eval >= 2` **and** `V > 0` before computing a DSR; otherwise raise `InvalidSampleError` (or emit an explicit `NOT RUN` verdict, per D-7). Add a regression test asserting the `PASS`/`FAIL` flip above cannot occur (D-1).
2. Raise instead of substituting `1e-6` when the Mertens variance term is non-positive (D-2).
3. Reject `kurtosis_convention != RAW_NORMAL_THREE` inside the DSR path, or convert excess to raw before the Mertens term — and add a test that pins the DSR to be invariant under the two conventions (D-3).
4. Remove `TOTAL_TRIALS_MINUS_ONE` from the loader, or implement it in the engine, so loader and engine agree (D-4).
5. Reject `evaluated_trial_count > trial_count_n` (D-5).

**Carried forward:** D-6 (verdicts compare rounded statistics) and D-7 (`NOT RUN` has no representation) are accepted for 2B only because they cannot manufacture a `PASS` on their own; both must be settled when the Phase 2C report emitter is written, since that is the point where `AGENTS.md` §9.3 becomes executable.

**Unchanged `NOT RUN` register:** all Phase 0–1B empirical items, every Phase 2C metric, and the G2A-3 parameter-sweep measurement.

---

## 22. Phase 2B Re-audit — §21 remediation (`13ce7c7`)

**Commit audited:** `13ce7c7` — *"fix(research): remediate §21 audit findings D-1 through D-5"* (6 files, +340/−7).
**Suite (measured):** `184 passed in 1.67s` (180 + 4 closure tests).
**Committed probe (measured):** exit 0, `ALL MEASURED GATES PASSED (100%)`.
**Method:** each of D-1…D-5 was re-attacked with the exact input that produced the finding in §21; then the guards were probed for over-blocking (legitimate cases must still compute) and for bypass; then the statistic was re-checked against the independent reference implementation to confirm the guards did not alter the maths.

### 22.1 Closure table

| ID | §21 evidence | Re-probe against `13ce7c7` | Status |
|---|---|---|---|
| **D-1** | `N=50, V=0` → `DSR 0.966639` PASS, tagged `N=50` | `compute_deflated_sharpe_ratio(SR=1.30, V=0, T=500, N=50)` → `InvalidSampleError: When trial_count_n (50) > 1, computing DSR requires strictly positive trial Sharpe variance…`. `N=50, N_eval=1` → `InvalidSampleError: …requires at least 2 evaluated trials to establish empirical variance`. End-to-end, registry of 50 trials with one `sharpe_ratio` → `InvalidSampleError` propagates out of `evaluate_strategy_significance`, no report produced. Legitimate paths unaffected: `N=1, V=0` → `0.966639` (PSR), `N=2, V=0.05` → `0.952503`. `V<0` rejected earlier as `trial_sharpe_variance must be a non-negative finite Decimal`. | **CLOSED** |
| **D-2** | `γ3=5, SR_ann=4.74` → `z=2,883,725`, `DSR=1.000000` PASS | Same inputs → `SignificanceError: Mertens asymptotic Sharpe variance term is non-positive (-4.539844e-01); DSR cannot be evaluated for extreme non-normal return moments…`. No `1e-6` substitution remains in the source. Mirror case `γ3=-5` still computes `0.964700`. | **CLOSED** |
| **D-3** | `EXCESS_NORMAL_ZERO` silently shifted DSR `0.832203 → 0.833457` | `DeflatedSharpeResult` gained `kurtosis_convention`; the Mertens term now always receives normalized raw `γ4`. Field-wise comparison of `deflated_sharpe_ratio`, `expected_max_sharpe`, `z_score`, `p_value`, `trial_sharpe_variance`, `kurtosis` across `(γ4=3.00, RAW)` and `(γ4=0.00, EXCESS)` → identical on all six, both reporting `kurtosis=3.00`. End-to-end through `evaluate_strategy_significance` with criteria convention switched: DSR `0.999998` both ways. Unknown convention → `SignificanceError`. | **CLOSED** |
| **D-4** | Loader accepted `TOTAL_TRIALS_MINUS_ONE`, engine raised `Unsupported` | `load_go_no_go_criteria` now rejects anything other than `EVALUATED_TRIALS_MINUS_ONE` with `CriteriaValidationError`; committed YAML still loads; probe and 184 tests green. Loader and engine can no longer disagree. | **CLOSED** |
| **D-5** | `N=2, N_eval=50` accepted and tagged | → `SignificanceError: evaluated_trial_count (50) cannot exceed total trial_count_n (2).` Boundary `N=5, N_eval=5` still computes (`0.898648`). | **CLOSED** |

**No regression in the statistic.** The guards are validation-only; the computation is untouched. Re-running the three independent-reference cases from §21 against `13ce7c7` reproduces `0.626502 / 0.618962 / 0.003381` with `SR* = 1.265301 / 0.497932 / 3.687703` — identical to the pre-remediation engine and to my own transcription of the formula. The probe's own D-1 regression asserts the true-penalty value `0.488273`, i.e. the number §21 produced with real dispersion, so the test pins the failure rather than the symptom.

### 22.2 Residuals (not blocking)

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| **D-1b** | P3 | The new guard is on the **sign** of `V`, not its magnitude. A vanishing but positive variance passes and deflates by nothing, reproducing the old outcome numerically while now being technically "valid". A registry whose evaluated Sharpes differ only in the sixth decimal can reach this. It is defensible — no dispersion means no selection bias to correct — but the report cannot show whether deflation was actually applied. | `N=100, V=1e-18, SR=1.30, T=500` → `SR*=0.000000`, `DSR=0.966639` PASS. Recommend flagging any `N>1` result whose `expected_max_sharpe` quantizes to `0.000000`, since that is indistinguishable from the D-1 failure mode in the output. |
| **D-6** | P3 | Verdicts still compare the 6-decimal rounded statistic. Unchanged from §21; no flip constructible at the committed `0.95` threshold. | Carried from §21. |
| **D-7** | P3 | `SignificanceReport` still has no `NOT RUN` state. After D-1 the inapplicable case raises instead of mislabelling, which is fail-closed and strictly better, but `AGENTS.md` §9.3 still has no representation in the schema. Must be settled by the 2C/2D report emitter. | Carried from §21. |

**Operational consequence of D-1, to be honoured in 2C:** a registry with `N > 1` must record `sharpe_ratio` for at least two trials and must exhibit real dispersion, or evaluation raises. That is the intended fail-closed behaviour and must not be worked around by padding a fabricated Sharpe into the registry.

### 22.3 Recomputed gates

| Gate | Result | Basis |
|---|---|---|
| G2B-1 · DSR reproduces published worked example | **NOT VERIFIED** | Formula verified against an independent transcription (`0.626502 / 0.618962 / 0.003381`); the paper's printed example remains external to the repository. |
| G2B-2 · monotone decay in `N` | **PASS** | Unchanged by remediation. |
| G2B-3 · bit-for-bit reproducibility | **PASS** | Unchanged; `kurtosis_convention` tag is deterministic. |
| G2B-4 · Haircut monotone in `N` | **PASS** | Haircut path untouched. |
| G2B-5 · float boundary isolation | **PASS** | Unchanged; no float reintroduced by the guards. |
| G2B-6 · anti-overfitting guards & criteria alignment | **PASS** | D-1…D-5 all reproduced as closed by the probes in §22.1. |

**Verdict: Phase 2B is signed off. GO.**

All five §21 findings are closed by execution, not by description: the fail-open path that deleted the multiple-testing penalty while reporting `N=50` now raises at both the function and the orchestration level, the fabricated `1e-6` denominator is gone, the kurtosis convention is normalized so the DSR is invariant, loader and engine agree on the variance divisor, and contradictory `N_eval > N` is rejected. The legitimate cases — `N=1` probabilistic Sharpe, two-trial registries with real dispersion — still compute, and the statistic matches an independent implementation to the printed precision, so the guards closed the hole without moving the maths.

Three residuals are carried and none can manufacture a `PASS`: D-1b (a near-zero variance still deflates by nothing, though it is now at least a mathematically coherent input), D-6 (rounded verdicts), D-7 (`NOT RUN` has no schema). D-6 and D-7 land on the Phase 2C/2D report emitter, which is where `AGENTS.md` §9.3 becomes executable.

**Next per the committed roadmap:** Phase 2B.5 (market data ingestion and immutable storage layer) before 2C, per the window decision recorded in `CURRENT_STAGE_OF_WORK.md` — binding corpus from 2018-04-01, warm-up from 2015, Parquet as system of record with DuckDB as a rebuildable engine.

---

## 23. Phase 2B.5 — Market Data Ingestion & Immutable Storage Layer (`fc9ecde`)

**Commit audited:** `fc9ecde` — *"feat(storage): implement Phase 2B.5 market data ingestion and immutable storage layer"* (14 files, +5,516/−20).
**Suite (measured):** `193 passed in 4.61s`.
**Committed probe (measured):** `probe_phase2b5.py` exit 0, `ALL MEASURED GATES PASSED (7/7, 100.0%)`.
**Scope of the slice as committed:** trading calendar, ISIN-keyed security master, Bronze/Silver/Gold storage, disposable DuckDB views, gating-window enforcement, for a five-scrip reference set.

### 23.1 What is structurally right

These are not ornaments and should survive the remediation unchanged:

- **Layer boundaries exist and are honest about dependency direction.** `pyarrow`/`duckdb` land in a `storage` extra (`pyproject.toml`), both modules guard the import, and nothing in `research/`, `portfolio/`, or `execution/` imports storage. The core stays stdlib-pure as §10.2 requires.
- **ISIN is the identity key** (§10.4). `SilverRecord.to_price_bar()` uses ISIN as `instrument_id`; symbol and series are per-row effective-dated attributes; nothing partitions by symbol.
- **Interval semantics are correct.** `SymbolInterval`/`SurveillanceInterval` are half-open `[effective_from, effective_to)` with `effective_to=None` as open-ended, `effective_from >= effective_to` rejected, and overlap detection across an ISIN's own symbol intervals. Delisting and transition predicates are `as_of >= effective_date`, which is the right side of the boundary.
- **Writes are atomic.** Both Bronze and Silver write to a temp file, `fsync`, then `replace()`; Silver refuses to create an empty partition and rejects a duplicate ISIN or a record whose `trade_date` disagrees with the partition date.
- **Exactness is preserved on the round trip.** Prices are written as decimal *strings*, not floats, so `Decimal(str)` reads back bit-identical. No binary float enters the storage path.
- **Fingerprints are deterministic** (sorted iteration, `sort_keys=True`, canonical row strings) and the DuckDB file is genuinely disposable — deleting it changes no fingerprint, which §10.2 requires.

The architecture is the right shape. The problem is that four of the eight §10 rules are asserted in docstrings and in the docs but not enforced in code, and the probe only exercises the paths where they happen to hold.

### 23.2 Findings

#### E-1 · P1 · The trading calendar is unverified and structurally incomplete

`configs/trading_calendar_nse.json` carries **no provenance of any kind** — no source URL, retrieval timestamp, SHA-256, or verification status. It is a weekday list minus a holiday list, which is why it contains **zero weekend sessions** and omits every special session NSE actually ran:

| Missing session | What actually happened |
|---|---|
| 2020-02-01 (Sat), 2025-02-01 (Sat) | Special live Saturday sessions on Union Budget days |
| 2024-05-18 (Sat) | Special live session from the disaster-recovery site |
| 2020-11-14 (Sat), 2019-10-27 (Sun), 2016-10-30 (Sun), 2023-11-12 (Sun) | Diwali muhurat trading |
| 2015-11-11, 2017-10-19, 2018-11-07, 2021-11-04, 2022-10-24, 2024-11-01, 2025-10-21 | Diwali muhurat trading on weekdays — i.e. full-weekday sessions that are still dropped |

The weekday *closure* list is sound: 0 of 122 spot-checked NSE closures appear as sessions (Holi, Good Friday, Id-Ul-Fitr, Maharashtra Day, Ram Navami, Muharram, Guru Nanak Jayanti, election-day closures, and the 2024-01-22 Ram-temple closure are all correctly absent). That makes the defect precise: **the calendar models weekdays, not sessions.**

Why this is a P1 and not a data-quality nit: the calendar is the authority every gap classification is measured against. A real session absent from the calendar can never be reported as `UNEXPLAINED_MISSING_RECORD` — the detector only walks dates the calendar already believes in — after which a bar on that date either is rejected as off-calendar or vanishes from the series (proved in E-2). The omission is invisible by construction. §10.7 (provenance and hash for every retrieved artifact) is also flatly unmet by the calendar file itself.

Separately, a muhurat session is a ~1-hour session, not a full day. Its OHLC range and volume are not comparable with a 09:15–15:30 session, so a correct model carries `session_type` and `open_time`/`close_time`. Silently dropping the day is one failure; silently treating an evening session as a full day would be the other.

#### E-2 · P1 · Silver has no calendar validation, and off-calendar bars vanish without a gap

`silver.py`'s header and the docs both describe partitions as *"calendar-checked"* / *"calendar-validated"*. They are not: `write_daily_partition(trade_date, records)` takes no calendar and never consults one. Measured — both writes succeed with no error:

```
calendar.is_session(2024-05-18) = False  [real NSE session, DR-site] -> ACCEPTED, no calendar check
calendar.is_session(2024-05-19) = False  [Sunday]                    -> ACCEPTED, no calendar check
```

Worse is the read side. `read_instrument_series_with_calendar_validation` iterates `calendar.sessions_in_range(...)` and therefore never visits an off-calendar partition, so the bar is neither returned nor classified:

```
[A] series dates = ['2024-05-16', '2024-05-17', '2024-05-21']   gaps = []
```

The 2024-05-18 bar is on disk, is absent from the returned series, and produces **no gap of any type** — numerically indistinguishable from a two-session jump. That is precisely the silent-bridging failure §6.3 forbids, and it composes with E-1: the calendar's own omissions are exactly the dates whose bars disappear this way.

#### E-3 · P1 · `build_dataset_snapshot` fingerprints datasets that have holes in them

`GoldEngine.load_price_panel` does support fail-closed behaviour (`fail_closed_on_missing=True` and it raises `GoldEngineError: Missing required silver partition for calendar session ...` when tested). But `build_dataset_snapshot` — the function that mints the `DatasetSnapshot` and its `DATA-CTNT-V2` content fingerprint — calls it with `fail_closed_on_missing=False`:

```
[B] calendar sessions = 4, snapshot.session_count = 4, bars returned = 3
    dates = ['2024-01-10', '2024-01-11', '2024-01-15']      (2024-01-12 missing from disk)
[B] snapshot built with a hole on 2024-01-12, no exception, fpr = DATA-CTNT-V2-b4b4125b04447e1dc86ff3bfa6f424fc
```

Three separate violations in one call: the snapshot claims `session_count=4` while carrying 3 bars; the missing session is recorded nowhere in the returned panel (no gap metadata, so a downstream feature engine sees three bars and assumes three consecutive sessions); and the content fingerprint certifies the truncated dataset as the identified artifact. `TrialRecord.dataset_fingerprint` would then point at data that was silently shortened. Additionally `return {k: tuple(v) for k, v in ... if v}` drops instruments with zero bars entirely, shrinking the universe without a record.

#### E-4 · P2 · The DuckDB view exposes prices as `VARCHAR`, so numeric predicates silently return wrong answers

Exactness is preserved on write (E-1's sibling strength), but the disposable query layer is where §10.6's `DECIMAL` requirement actually bites, and there the column type is text:

```
typeof(close) = 'VARCHAR'
SELECT count(*) ... WHERE close >= '3000'   -> 1 row     (numeric answer: 0)
'900.00' >= '1500'                          -> True
SELECT avg(close)                           -> BinderException: No function matches
```

A researcher writing `WHERE close > 100` against the *analytical engine built for this exact purpose* gets lexicographic comparison: every three-digit price outranks every four-digit price. No error, no warning. Either the Parquet columns are `DECIMAL(p,s)` (or integer paise) and the view inherits it, or the view exposes explicit `CAST(close AS DECIMAL(18,4))` columns — with exactness documented, not left to the caller's memory.

#### E-5 · P2 · The view layer fails open on corrupt partitions

`register_views` wraps `CREATE OR REPLACE VIEW ... read_parquet(glob)` in `except Exception:` and substitutes an empty typed view. With a deliberately truncated Parquet file:

```
[C] TRUNCATED partition -> count(*) = 0        (silently empty view, no error raised)
```

"No files exist yet" and "the archive is corrupt" are indistinguishable, and the failing answer is the reassuring one. A backtest run against a corrupt partition would see zero rows for that instrument and quietly exclude it. The empty-view fallback should apply only when the glob matches no files.

#### E-6 · P2 · Bronze accepts an overwrite of an archived path, orphaning the prior verification

`store_payload` writes via temp file then `replace()`, so re-storing the same `relative_path` overwrites the archived bytes. The manifest keeps both entries and `get_manifest_entry` walks the manifest in reverse, so tamper verification always checks against the *newest* entry:

```
[D] overwrite accepted: True | bytes now: b'REVISED,DIFFERENT,BYTES\n'
[D] manifest entries for path: 2 | original retrieval verifiable: its sha256 is in the manifest but its payload is gone
```

The old retrieval becomes unverifiable while still appearing in the audit trail, and Gate G2B.5-1 passes only because it never re-stores an existing path. §10.1 requires that corrections be *new appends carrying an effective date and a restatement reference* — an in-place replacement is exactly the edit it prohibits. Content-addressed payload filenames (`<sha256>.bin` plus a path index) would make this structurally impossible rather than policy-dependent.

### 23.3 Residuals (non-blocking for 2B.5, must be settled before they touch a verdict)

| ID | Sev | Finding |
|---|---|---|
| **E-7** | P3 | Surveillance intervals are never checked for overlap or contradiction, and `resolve_surveillance` returns *all* applicable stages as a tuple with no precedence rule — a scrip simultaneously ASM-LT-2 and GSM-2 resolves to both, and §5.2's "most restrictive" logic does not exist yet. |
| **E-8** | P3 | Duplicate delisting/transition events for one ISIN are built into dicts (`{d.isin: d}`), so the last one silently wins instead of raising. |
| **E-9** | P3 | `circular_ref` is free text with no verification status; committed values (`NSE/CML/2018/BONUS_INFY`, `NSE/CML/57531`) are not in NSE's circular identifier format. Under §6.5 these must be `SOURCE_UNVERIFIED` until a real circular is filed. |
| **E-10** | P3 | `build_production_security_master()` hardcodes five scrips inside library code — reference data as a code literal, with no file, no fingerprint artifact, and no provenance. It is named "production" and will be consumed as such. |
| **E-11** | P3 | The "point-in-time universe" is *every ISIN registered in the hardcoded master*, filtered by series — there is no Nifty membership data anywhere in the commit. G2B.5-3 therefore tests delisting arithmetic, not universe reconstruction. 2C must not assume a universe schedule exists. |
| **E-12** | P3 | Adjustment scales prices but not `volume` or `traded_value`, so an adjusted dataset mixes post-split prices with pre-split share counts — which corrupts the §7.3 participation cap and any turnover-based slippage. Additionally `adjustment_factor` is a `Decimal` **division**, so non-terminating ratios (3:2, 2:3) round at the ambient context precision (28 digits): exactness is silently approximate and the content fingerprint becomes process-context-dependent. |
| **E-13** | P3 | No OHLC sanity validation (`high < low` or `high < close` is accepted), and no whitelist on `series`, so §5.1's `EQ`/`BE`/`SM`/`BZ` semantics are carried as free text. |
| **E-14** | P3 | `check_gating_verdict_eligibility` matches only the literal `"GO"`; `"APPROVED"`/`"PASS"` pass through unchecked. Narrow, because `resolve_gating_verdict` does force `NOT RUN` for pre-2018 windows. |
| **E-15** | P3 | Manifest append has no inter-process lock; two concurrent ingests can interleave a partial line into `manifest.jsonl`. |

### 23.4 Gate assessment

All seven gates pass as written, but each fixture avoids the failure mode that the corresponding rule exists to prevent:

| Gate | Probe result | What it actually establishes |
|---|---|---|
| G2B.5-1 | **PASS** | Bit-flip and truncation are caught. Never re-stores an existing path, so E-6 is invisible. |
| G2B.5-2 | **PASS** | Determinism on identical input — genuine, and unaffected by these findings. |
| G2B.5-3 | **PASS** | Delisting/transition boundary arithmetic is right. Universe reconstruction is untested because none exists (E-11). |
| G2B.5-4 | **PASS** | Only tests a *whole partition missing on a calendar date*. Off-calendar bars (E-1/E-2) and the snapshot builder's own non-fail-closed path (E-3) are not exercised. |
| G2B.5-5 | **PASS** | Rewrite through the API is refused. A second writer or a same-path Bronze restatement is not modelled. |
| G2B.5-6 | **PASS** | Database deletion leaves fingerprints intact — genuine. Queries use equality on ISIN/date, so no numeric predicate ever touches the `VARCHAR` prices (E-4). |
| G2B.5-7 | **PASS** | Preserving a computed verdict on a pre-2018 window does force `NOT RUN`. Literal-`GO`-only matching remains (E-14). |

No gate tests calendar completeness against an authoritative source, no gate rejects an off-calendar bar, no gate asserts that a gapped dataset cannot be fingerprinted, and no gate performs arithmetic on a stored price. The gates are measured — but measured against the paths that already work.

### 23.5 Documentation integrity

The commit rewrites the Phase 2B.5 section heading to **"(Implemented & Verified)"**, states in the gate table that all seven gates are `PASS`, and describes Silver as *"Typed, calendar-validated daily Parquet partitions"*. The first two are defensible readings of the probe; the third is falsified by E-2, and "Verified" is a verdict this audit does not grant. The commit also **deletes the design rationale** that justified the window and the storage decision (why not 2022–2026, the structural-break inventory, Parquet-as-system-of-record, the artifact list, the original gate definitions). Under §9.1 the replaces are only as good as the computation behind them, and the reasoning that produced the plan is now missing from the document that is supposed to hold it.

### 23.6 Verdict

**Phase 2B.5 is NOT signed off.**

This is a competent skeleton with the right module boundaries, the right identity key, correct interval semantics, atomic writes, deterministic fingerprints, and a genuinely disposable query engine — the hard architectural decisions are sound and none of them needs reversing. But four of the eight §10 rules are unenforced in code while being asserted in docstrings and documentation: §10.1 (Bronze overwrite, E-6), §10.3/§6.3 (holes inside a fingerprinted dataset, E-3; off-calendar bars dropped without a gap, E-2), §10.6 (text-typed prices in the query layer, E-4), and §10.7 (calendar with no provenance, E-1). Two of those — E-1 and E-2 — can silently remove real NSE sessions from a series, which is the exact class of failure this project has rejected at every prior phase.

**Closure set (must all be closed, by execution, before 2C):**

1. **E-1** — Rebuild the calendar as *sessions*, not weekdays: `session_type` (FULL / MUHURAT / SPECIAL) with open and close times, every special session included, plus a provenance block (source, retrieved_at, sha256, verification status) and a per-year completeness count asserted against NSE's annual holiday circular.
2. **E-2** — Pass the calendar into Silver; reject any partition whose date is not an authoritative session; reject (never drop) an archived bar outside the calendar, and surface off-calendar storage as an explicit error type.
3. **E-3** — `build_dataset_snapshot` must fail closed by default on a missing session, must carry gap metadata for any session it can legitimately skip, and must never emit a fingerprint over a non-contiguous series. Remove the `if v` silent universe shrinkage.
4. **E-4** — Persist prices as `DECIMAL`/integer paise, or expose explicitly cast `DECIMAL` columns in the view, so numeric predicates and aggregates are exact and correct.
5. **E-5** — Fail closed on unreadable partitions; reserve the empty-view fallback for "no files match".
6. **E-6** — Make Bronze content-addressed and reject in-place restatement without an explicit restatement reference.

E-7…E-15 are carried as residuals; E-11 and E-12 must be resolved before any universe or participation-cap computation is presented as measured. The gate table must gain tests for: calendar completeness and provenance, off-calendar bar rejection, fingerprint refusal over a gapped series, Bronze restatement, numeric typing through the view, and corrupt-partition fail-closed behaviour — each of which currently passes without being checked.
