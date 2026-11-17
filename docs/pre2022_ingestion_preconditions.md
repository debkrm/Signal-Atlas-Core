# Pre-2022 ingestion preconditions — Audit §80.13 items 3-5 (A1, A2, A4)

**Status: prepared, not ingested.** No 2018-2021 archive was downloaded, no corpus row, manifest row,
criteria value or interval row was written by this work. The readiness measurement is
`scripts/probe_pre2022_preconditions.py`, which exits **1** today because every precondition fails.
This document records what each precondition requires, what artifact satisfies it, and the order the
work has to happen in. Nothing here is audited: no verdict judges it.

## 1. Why the window is still closed

The binding evaluation window is `2018-04-01..2021-12-31` (§10.8) and it is *warm-up only* at
`2022-01-03`, the date `market_data_and_accounting_invariants.min_binding_evaluation_start_date` pins
in `configs/go_no_go_criteria.yaml`. Audit §80.9 measured three missing inputs and §80.10 corrected the
session arithmetic (930 sessions in the window, 494 gating sessions at the current pin, 1,424 for the
extended in-sample `930 + 494`). Extending the corpus does **not** move the DSR bar by itself — the
sessions a pre-2022 ingest adds are `NOT RUN` for gating until A1, A2 and A4 are satisfied — so the
constraint is provenance, identity and dividends, in that order, not sample size.

Measured at the tree this file is committed in:

```
[NO] A1 2018: no committed holiday circular artifact names a 2018 date in data/raw/circulars
              (13 artifact(s) on disk, issued 2021-12-10..2026-01-12)
[NO] A1 2019: no committed holiday circular artifact names a 2019 date ...
[NO] A1 2020: no committed holiday circular artifact names a 2020 date ...
[NO] A1 2021: no committed holiday circular artifact names a 2021 date ...
[NO] A1 provenance: the calendar's provenance.sha256 is its own CAL-FPR digest af8e309a6f897a67…,
                    not the digest of a source artifact
[NO] A2: 4510 interval row(s) begin 2022-01-03, after the binding window start 2018-04-01;
         0 row(s) reach 2021-12-31
[NO] A4 dividends: 0 of 138 committed ex-date(s) fall in 2018-04-01..2021-12-31
                   (earliest committed 2022-03-29)
[NO] A4 max hold: no maximum-hold bound is committed in configs/go_no_go_criteria.yaml
OVERALL: NOT READY — 8 of 8 precondition check(s) not met
```

## 2. Invariants this work must not disturb

| Invariant | Value held while the preconditions are prepared |
|---|---|
| Trial registry | `N = 9`, `N_eval = 5`; no trial row is added, scored or re-scored |
| 2024 fold | validation partition only; `validation_folds_count = 0`; no fold is run |
| Holdout | `2025-01-01..2026-11-11` sealed; `HOLDOUT_UNLOCK` absent and not created |
| Thresholds | no numeric threshold, window pin, fold end or cost parameter moves |
| History | corpora and manifests are append-only; a restatement is a new row, never an edit |

## 3. A1 — 2018-2021 NSE holiday circulars, one per year, in the manifest (§80.13 item 3)

**Requires.** For each of 2018, 2019, 2020, 2021 a Bronze artifact of the exchange's annual trading
holiday circular (and any later amending circular, as its own artifact) under `data/raw/circulars/`,
with `circular_id`, `issue_date`, `source_url`, `retrieved_at`, `http_status`, `provenance_status` and
the declared `trading_holidays`, plus the special-session/muhurat entries that the annual circular or a
separate special-session circular declares.

**Acceptance (the probe's rule).** For each year, the union of that year's declared holidays and
declared special sessions must reproduce the calendar's session set for the year exactly:
`weekdays(year) - declared_holidays ∪ declared_special_sessions == calendar sessions in year`, with
zero unexplained sessions and zero circular dates absent from the calendar; the artifact must be a
**current** row of `data/reference/manifest.jsonl` whose `byte_count` and `sha256` match the file; and
its `circular_id` must appear in the calendar's `provenance.circular_references`.

**Provenance.** `configs/trading_calendar_nse.json` today carries one `provenance.sha256` equal to its
own `CAL-FPR-V1-…` hex, which is a self-digest and not a source digest. Satisfying A1 means recording
per-year source provenance — `{year, circular_id, source_url, retrieved_at, byte_count, sha256}` for
each year's artifact — and making the calendar declare that per-year table as its source. The calendar
fingerprint stays the calendar fingerprint; it stops standing in for provenance.

**Ordering and cost.** These are data artifacts, not code: a Bronze JSON per circular, a manifest row
per artifact, and a calendar provenance table. Adding current manifest rows restates
`expected_manifest_fingerprint`, which is a **criteria-version commit** (the §78/§79 precedent) that
moves no numeric threshold. Fail-closed rule per §12.5: the archives are cached bytes committed to
Bronze, so the gate stays offline and reproducible.

## 4. A4 — dividends inside the window, or a committed maximum hold (§80.13 item 4)

**Requires.** One of two, in this order of preference:

1. **Dividend rows.** `DIVIDEND` rows in `data/reference/corporate_actions.jsonl` for every NSE
   ex-date in `2018-04-01..2021-12-31` that falls inside a holding window the strategy could open —
   each with `ex_date`, `isin`, `symbol`, the cash amount per share and a `circular_ref`/provenance
   status, and each restated in the manifest.
2. **A committed maximum hold.** A bound in `configs/go_no_go_criteria.yaml` (the probe looks for a
   `max_hold*`/`holding*` key) that prints **below** the shortest gap between consecutive ex-dates in
   the window, so no hold can straddle an ex-date.

**Why it blocks a swing strategy (§13.2).** A multi-session hold carries an ex-dividend gap as a cash
inflow to the open position, never as a loss. A corpus with no dividend rows in the window makes every
held-position ledger wrong for those sessions, and a synthetic or bridged row is prohibited (§6.3).

**Acceptance.** The probe's two A4 checks: a non-zero count of committed in-window ex-dates (with the
first and last printed), **or** a committed maximum-hold bound; both currently `NO`.

## 5. A2 — how pre-2022 identity is derived (§80.13 item 5)

**Requires.** A pre-2022 `cash_equity_symbol_intervals` derivation whose rows are effective-dated
intervals keyed by **ISIN**, with `symbol` and `series` as effective-dated attributes, and zero
unresolved symbols across the extended window.

**How it must be derived (no new mechanism invented).** `scripts/derive_cash_universe_intervals.py`
already reads every `data/raw/<year>/*.zip` Bhavcopy, takes `(ISIN, SYMBOL, SERIES)` per session, and
builds half-open intervals `[effective_from, effective_to)`. Pre-2022 identity is the same derivation
run over 2018-2021 Bronze:

- one observation per session from the exchange file, never from a present-day constituent list
  (§10.5 — no back-solving the past from the present);
- an ISIN change is a closed interval plus a new interval, and a transition row is added only from a
  documented corporate action or a verified ISIN-transition circular (§10.4); histories are never
  stitched across differing ISINs;
- a `series` change (`EQ` ↔ `BE`/`BZ`) **does not** break price continuity (§6.2); it changes
  entry eligibility only (§13.1);
- rows are appended to the derived corpus and the manifest as a restatement; the derivation must be
  reproducible from Bronze byte-for-byte, as the 2022-2026 table is today.

**Acceptance (the probe's rule, and the part that needs Bronze).** Zero unresolved symbols across the
extended window — every traded `EQ` row resolving to an authoritative ISIN — and every exception
listed **with its session count** rather than skipped. The probe can only measure the first half today
(earliest `effective_from` and in-window row count); the resolution half reports `NOT RUN` until the
2018-2021 archives exist, because a resolution percentage cannot be computed over a corpus that is not
there (§9.3).

## 6. Order of work, and what each step unblocks

1. **A1** — source the four holiday circulars; commit Bronze artifacts, manifest rows and the per-year
   calendar provenance. Unblocks: an authoritative 2018-2021 session grid that is *sourced*.
2. **A2** — capture 2018-2021 Bhavcopy Bronze, re-run the interval derivation, restate the corpus and
   the manifest, re-pin the fingerprint under a new criteria version. Unblocks: identity and continuity
   across the extended window.
3. **A4** — dividends inside the window, or the maximum-hold bound. Unblocks: a correct held-position
   ledger across ex-dates.
4. **B1-B9** on the captured Bronze — Bronze check, per-archive fail-closed ingestion, zero unexplained
   session gaps, zero restatements (§6.3).
5. **C1-C6** with §80.10's corrected count (`930 + 494 = 1,424` in-sample sessions; `T = 494` while
   `min_binding_evaluation_start_date` is `2022-01-03`).
6. **Only then** a single `seq 10`, registered once as trial `N = 10` / `N_eval = 6`, on the extended
   in-sample, with the 2024 fold still frozen and the holdout still sealed.

Until step 1-3 land, the window is warm-up only, every pre-2022 verdict is `NOT RUN` by the criteria'
own pin, and the DSR denominator is unchanged by any warm-up sessions added.

## 7. Why the probe is not in the gate

`scripts/probe_pre2022_preconditions.py` is deliberately not named `verify_*.py`. The Wave 0.5 gate
executes every `scripts/verify_*.py` and requires exit 0 (§12.3), and this probe is expected to fail
until the ingestion exists; registering it would either turn the gate permanently red or tempt a
skip/xfail, which §12.4 forbids. It is a readiness measurement a human or the implementer runs, whose
statuses are computed per check rather than asserted in prose (§9.1).
