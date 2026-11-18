# Signal Atlas Core — Audit Report, Volume 2

Append-only continuation of `reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md`.
Volume 1 is frozen byte-for-byte at §78 (`configs/audit_volumes.yaml`); every §N from 79 onward is
appended to this file. Findings are executed from `reports/audit/findings.jsonl` by
`scripts/verify_audit_findings.py`; closures are appended rows, never edits.

## §79 — Audit of `82e3ef0..3119cb2` (tag `feat-s78-3119cb2`): the table is generated for the whole market, and the freeze pins bytes the repository does not contain

**Date:** 17 November 2026
**Commit under review:** `3119cb2` (25 files, +1,970/−94)
**Baseline:** `82e3ef0` (§78, tag `audit-s78-82e3ef05`)
**Verdicts:** N-148 CLOSED · N-149 CLOSED · N-150 **PARTIAL, held open** · N-151 CLOSED · N-153 CLOSED · N-152 ACCEPTED (unchanged) · four new findings, two HIGH

### 79.1 Baseline re-measured at `3119cb2`

The suite and every verifier were re-run, not read.

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | exit 0, `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers discovered | 9 on disk, 8 executed (the gate excludes itself), all exit 0 |
| Test suite | **523 passed, 0 skipped, 0 xfailed** (117 s) |
| W0.5-5 reference manifest | 46 current artifacts match, 21 superseded rows skipped |
| `python scripts/probe_audit_findings.py N-148 … N-153` | six probes, six `PASS`, exit 0 each |
| TrialRegistry | N = 9, N_eval = 5, manifest pin `3326b1b2…` unchanged, 323 B |
| Criteria | 1.1.8, every numeric threshold byte-identical to 1.1.7 |
| 2024 validation fold | frozen (`validation_folds_count 0`); holdout 2025-01-01..2026-11-11 sealed |

**One number in that table is only true on the machine that wrote it.** On this checkout, one `git checkout` of the audit file turned the suite into **522 passed, 1 failed** — `test_audit_volume1_is_frozen_at_its_pinned_digest`, a test the implementer wrote. That failure is finding N-154 (§79.7), and it means the committed suite is red on every fresh clone of `3119cb2`.

### 79.2 N-148 — CLOSED

`CRIT-STAT-01` now refuses a `total_trades` that arrives without liquidated evidence, and the reconciliation still fires when the evidence is present. Eleven shapes measured on the evaluator directly:

| Bundle | Status | Computed |
|---|---|---|
| `{total_trades: 193}` | **NOT RUN** | — |
| `{total_trades: 193, closed_only_trade_count: 193}` | **NOT RUN** | — |
| `{total_trades: 205, closed_only_trade_count: 193, positions: 12}` | PASS | 205 |
| `{total_trades: 205, closed_only_trade_count: 200, positions: 12}` | FAIL | 205 |
| `{total_trades: 205, closed_only_trade_count: 200}` | NOT RUN | — |
| `{total_trades: 205, closed_only_trade_count: 200, positions: []}` | **FAIL** | 205 |
| `{total_trades: 205, liquidated_open_positions: []}` | PASS | 205 |
| `{total_trades: 193, liquidated_trade_count: 193}` | PASS | 193 |
| `{total_trades: 205, liquidated_trade_count: 12}` | FAIL | 205 |

The §78 bypass is gone: omitting the column no longer buys a PASS, and a censored book now fails on the arithmetic when the closed count is present. Residual, carried as **N-159** (LOW): `{total_trades: 205, liquidated_open_positions: []}` passes with no `closed_only_trade_count` at all. An empty list is an affirmative statement ("nothing is open"), so it is not the §78 omission bypass — but it is the one shape where the reconciliation has nothing to reconcile, and a censor that sends `[]` instead of a positive count is still accepted. Cheap to close: require the closed-only count whenever `total_trades` is supplied.

### 79.3 N-149 — CLOSED

`CRIT-OVERFIT-03` is pinned to the four pre-registered anchored ends. Nine shapes measured:

| Bundle | Status | Computed |
|---|---|---|
| 4 pre-registered ends, all positive | PASS | 1.0000 |
| 3 ends | **FAIL** | — |
| 4 rows, fourth end drifted to `2024-06-28` | **FAIL** (evidence names `unexpected [2024-06-28]`) | — |
| 4 rows, duplicate end, `2023-12-29` missing | **FAIL** | — |
| declared `positive_is_fold_ratio 0.75`, no rows | **NOT RUN** | — |
| 4 ends, 3 positive 1 negative | PASS | 0.7500 |
| 4 ends, PF 1.20 (below the 1.30 floor) | FAIL | 0.0000 |
| 4 ends, no expectancy in any row | NOT RUN | — |
| 4 ends supplied as `datetime.date` | PASS | 1.0000 |

The ratio is now computed only over the committed fold ends, and a declared ratio with no rows is no longer evidence. This is the one repair of the three that closes cleanly.

Residual (unchanged, and not new): the four ends are pinned as *dates*; the per-fold expectancy and PF inside each row remain producer-declared. The engine can gate the set, not the numbers in it. That was true before §78 and is not moved here (§14.5).

### 79.4 N-150 — PARTIAL: the minimum is enforced only when the count is supplied, so it is bypassable by omission

Measured on `CRIT-OVERFIT-06`:

| Bundle | Status | Computed |
|---|---|---|
| `{ratio: 1.00, folds_count: 1}` | **NOT RUN** | — |
| `{ratio: 1.00, folds_count: 2}` | PASS | 1.0000 |
| `{ratio: 0.50, folds_count: 2}` | FAIL | 0.5000 |
| `{ratio: 1.00, folds_count: 0}` | NOT RUN | — |
| `{ratio: 1.00, folds_count: "1"}` | NOT RUN | — |
| `{folds_count: 2}` (no ratio) | NOT RUN | — |
| **`{ratio: 1.00}` — count absent** | **PASS** | **1.0000** |

The repair reads the count and gates on it. It does not require the count. A bundle that never mentions `walk_forward_validation_folds_count` clears the row with a single-fold ratio — the same shape as N-148, one field to the left, and exactly the additive-fix pattern §14.4 warns about: the guarded path is the one where the key is present, and the unguarded path is the one where it is not. Arguably worse here, because `CRIT-OVERFIT-06` is the row that will certify or refuse the 2024 fold.

Held **OPEN** as **N-156** (MEDIUM). The probe that must fail closed before it closes: `{walk_forward_positive_fold_ratio: 1.00}` with no count must evaluate **NOT RUN**, and the existing `{ratio: 1.00, folds_count: 2}` must stay PASS so the fix cannot simply reject every ratio.

### 79.5 N-151 — CLOSED as a coverage defect; the identity table is now generated for the whole market

Measured independently of the implementer's probe, from the committed interval table:

| Measurement | Value |
|---|---|
| Symbols with more than one ISIN | **310** |
| Adjacent identity pairs | **324** |
| `ISIN_TRANSITION` rows in `corporate_actions.jsonl` | **324** |
| Distinct pairs among those rows | **324** |
| Adjacent pairs with no row | **0** |
| Rows whose `ex_date` ≠ the successor interval's `effective_from` | **1** |
| Pairs bridging a hole longer than 7 days | **0** |
| Transition rows not `CONTENT_IDENTIFIED_ONLY` | **0** |
| Rows carrying a non-1:1 ratio | 3 (`TATASTEEL` 10:1, `VBL` 2:1, `COCHINSHIP` 2:1) |

Two corrections to my own §78 figure, both mine: I reported 286 multi-ISIN symbols from an `EQ`-filtered scan; the table has 310 across all series, and the implementer's generator covers all of them. And the 324 consecutive interval pairs all meet at a shared boundary day (old `effective_to` == new `effective_from`), which is correct adjacency under §10.5's half-open intervals, not an overlap — my probe prints them as `delta 0` and the honest reading is "adjacent", not "overlapping".

The §78.11 defect — a hand-written 12-row list standing in for a 286-symbol market — is gone. The residual is **N-158** (MEDIUM): `TATASTEEL`'s row is dated `2022-07-28` while the interval table starts the successor ISIN on `2022-07-29`. The generator cannot correct it, because the pair is already "documented" and skipped. One session, inside the 5-day boundary tolerance the runner uses, so identity still resolves — but the corpus and the interval table disagree about a date, and the generator has no assertion that would have caught it. The fix is one line: when the pair is already documented, assert `row.ex_date == successor_effective_from` and fail loudly instead of skipping.

**What this closure does and does not mean.** The refusal path is now unreachable for every symbol the committed table records: a wider window or a new listing enters with a row already committed, which is what §78.11 asked for. It is not evidence that any of the 324 transitions is a real corporate action. N-152 stands accepted: every row names `UNATTESTED_NSE_INTERVAL_TABLE_*`, i.e. the corpus citing itself. The corpus and a future Bhavcopy cannot contradict each other on identity, by construction.

### 79.6 N-153 — CLOSED: IRB's boundary move is post-split trading, read from the committed raw archive

Read independently from `data/raw/2023/cm{21,22,23}FEB2023bhav.csv.zip`, `IRB`, series `EQ`:

| Session | PREVCLOSE | OPEN | CLOSE |
|---|---|---|---|
| 2023-02-21 | 284.10 | 284.95 | **297.45** |
| 2023-02-22 | **297.45** | **30.40** | **34.05** |
| 2023-02-23 | 34.05 | 31.85 | **29.70** |

A 1:10 face-value change between the two sessions: `PREVCLOSE` carries the pre-split close unchanged, the open is 10.2% of it. On the split-adjusted series the predecessor close is 29.745, so the boundary move is **+14.47%** and the next session **−12.78%** — exactly the two prints §78 flagged as a suspected unadjusted artefact. They are genuine post-split trading. No adjustment row is fabricated to explain them; the split lives in the derived adjustment layer, and the manifest records the un-sourced provenance residual.

The one thing not closed: the 15% two-day move is real but unexplained. Nothing in the corpus says why IRB moved 14% on its first post-split session, and ATR, momentum and the stop all price it. Real is not the same as understood, and a strategy that trades this name in 2023 inherits an event nobody has sourced.

### 79.7 N-154 (HIGH) — the frozen-volume pin names bytes that are not in the repository, so the freeze is unverifiable from a clone

This is the most consequential finding of the round, and it is partly mine.

`configs/audit_volumes.yaml` pins Volume 1 at 8,442 lines, sha256 `7c7760f72820f195…`. Measured on the repository:

| Object | sha256 | Bytes |
|---|---|---|
| Committed blob `HEAD:reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md` | `f4ca03d58466bebb…` | 1,061,739 |
| Working copy as delivered at `3119cb2` | `7c7760f72820f195…` | 1,061,765 (implied) |
| Blob re-encoded LF→CRLF | `c42506351c0fe48e…` | 1,070,181 |
| Blob re-encoded with the §78 append as the only LF span (cuts 8267/8268/8266) | `b7b5e959…`, `ab7571ed…`, `4149b6d3…` | — |

None of them reproduces the pin. A plain `git checkout -- <file>` — the most ordinary operation git has — replaces the working copy with the blob, and then:

- `Gate W0.5-1b` fails: `sha256 f4ca03d58466bebb… != pinned 7c7760f72820f195…`;
- `Gate W0.5-1c` fails, because `INDEX.md` embeds the working file's digest;
- `test_audit_volume1_is_frozen_at_its_pinned_digest` fails, so the "523 passed" claim is a claim about one working directory, not about the commit.

The pin measures the byte sequence that sat in a Windows working tree, where `* text=auto eol=lf` and `core.autocrlf=true` mean git normalises on commit: the stored bytes are not the bytes that were hashed. My §78 append is the origin of the divergence — I appended a 175-line section to a file that was being normalised, and the implementer then pinned the resulting working copy instead of the stored object. That is a defect in a verification instrument I asked for, and I state it as mine.

**What I changed, and why.** Volume 1 itself is untouched (it is byte-identical to `HEAD`; `git status` reports no change). I changed the pin to the stored bytes — `sha256: f4ca03d5…`, `line_count: 8442` — because a pin that no checkout can satisfy verifies nothing, and re-pinning to the object the repository actually stores makes the check meaningful on a clone, on CI and on this machine. This is an auditor edit to an implementer-owned config, disclosed here and listed in §79.12 for ratification. The alternative — restoring the working copy to unreachable bytes — would make the gate green by hiding the defect.

The durable fix is not a number: mark the audit volumes non-normalising (`reports/audit/** -text` in `.gitattributes`), or compute the pin over the blob (`git cat-file blob HEAD:<path>`) rather than the working file. Either removes the platform dependence. A pin that depends on how a clone was configured is not a freeze.

### 79.8 N-155 (HIGH) — the green cache certifies itself: one JSON row, and the suite never runs

§78.15 (b) proposed a source-tree green cache so audit-only commits need not re-run 523 tests. It was implemented exactly as proposed — trusted input, no anchor — and it fails the way the audit warns about.

Replayed end to end, on this repository:

1. Append an untested edit to `src/signal_core/reporting/verdicts.py` (`PROBE_POISON = 1`).
2. Compute the new source-tree hash with the gate's own `compute_source_tree_hash(source_tree_entries())`.
3. Append one row to `data/reference/source_tree_green.json`:
   `{"source_tree_hash": "<new hash>", "suite_count": 1, "verify_exits": {}, "utc": "<now>", "gate_sha": "forged"}`.
4. Run `python scripts/verify_audit_append_only.py`.

Result: `[INFO] reused green at forged (1 passed, recorded …) — heavy gates skipped for an identical source tree`, and **`OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED`** on a tree whose only test evidence is a number the attacker typed.

Three separate holes produce this:

- **`verify_exits: {}` passes.** `select_gate_plan` uses `any(int(code) != 0 for code in exits.values())`; over an empty dict that is `False`, so "no verifier ran" reads as "every verifier passed". A record with nine zeroes and a record with none are indistinguishable to the gate.
- **`suite_count` has no floor.** The reuse message prints `1 passed` and the verdict is still PASS. A row claiming zero tests would be accepted on the same path.
- **The cache is unsigned and unpinned.** Unlike the trial registry — which has a sidecar chain and a criteria pin — nothing witnesses that a row was produced by a run. Anyone who can edit a committed JSON file can retire the entire §12.3 gate. `gate_sha` is a label: the two committed rows name `82e3ef0` and `3119cb2`, but a tree hash is a working-tree state, and the row's `gate_sha` is never checked against the commit that contains it.

Secondary defect: a full run **writes** `data/reference/source_tree_green.json`, a tracked file, so every green run leaves the tree dirty — measured at the start of this round, before I touched anything. The artifact the gate appends to is neither in the manifest nor ignored.

The cache is worth keeping; the trust model is not. The acceptance test, which must fail closed before this finding closes:

- a row whose `verify_exits` is empty, or names fewer than the discovered verifier set, is **not** reusable;
- `suite_count` below a pinned floor is not reusable;
- a record must bind to a commit that exists and whose tree hash equals the recorded hash (`git rev-parse <gate_sha>^{tree}` plus a file-set digest), so a row written by hand cannot name a tree that was never run;
- replaying the forgery above must print `unknown source-tree hash` and run the full suite.

### 79.9 N-157 (MEDIUM) — the findings ledger could not record the closure it exists to record

§78.15 (c) asked for an auditor-owned, append-only `reports/audit/findings.jsonl` with executed probes. It was built with one row per finding and a **duplicate-id rejection** (`verify_audit_findings.py`, the `len(ids) != len(set(ids))` check) plus a test asserting the same. Under that schema, appending a CLOSED row for a finding that already has an OPEN row turns both the verifier and the suite red. The ledger could hold only green rows and could never record a transition — which is the one thing it is for. This is the additive-fix shape turned on the auditor's own instrument: I specified an append-only ledger and a uniqueness constraint in the same breath, and they contradict.

Fixed here, minimally, in `scripts/verify_audit_findings.py` and in the single assertion that mirrors it in `tests/unit/test_phase3b2_audit_s78_items.py`: the **last row per id is authoritative**, earlier rows remain as history, a repeated id with an *identical* status is still a duplicate and still fails closed, and a row marked `CLOSED` must cite `closed_in_section`. The closure rows appended by this round are in §79.12's ledger. This edit is the auditor's and is listed for ratification: if the implementer prefers a different schema, revert it and record a new finding.

A consequence worth stating: because every non-ACCEPTED row's probe must pass for the gate to be green, the ledger is a closure register, not a defect register. N-154, N-155, N-156, N-158 and N-159 are therefore recorded in this section and in the work order, not in the ledger, until their fixes land with passing probes.

### 79.10 Preserved invariants

Criteria 1.1.8 moves no threshold: `min_total_trades 100`, `min_profit_factor 1.50`, `min_deflated_sharpe_ratio 0.95`, `min_haircut_sharpe_ratio 1.25`, `max_single_position_weight 0.10`, `min_traded_eq_resolution_pct 100.0`, `min_dataset_instrument_resolution_pct 100.0`, `min_positive_walk_forward_fold_ratio 0.80`, `min_positive_is_fold_ratio 0.75`, `min_fold_liquidated_pf 1.30`, `min_liquidated_pf_ex_top_1 1.40` — all byte-identical to 1.1.7. The manifest pin moved to `MAN-FPR-V1-571752f0…` because `corporate_actions.jsonl` grew from 176 to 485 rows (205,540 B, `c593bb96…`), and the superseded row is retained as history per §10.1. `corporate_actions.jsonl` reproduces byte-for-byte from its generator (asserted by `test_n151_generator_reproduces_the_committed_corpus`). N = 9 and N_eval = 5 are untouched; the probes of this round ran on the evaluator directly and created no trial row.

### 79.11 Verdicts

| Area | Verdict | Basis |
|---|---|---|
| Identity & corporate actions (N-151, N-153) | **GO** for the coverage defect | 310 symbols / 324 pairs / 324 rows / 0 undocumented, measured; IRB reproduced from raw. Carried: N-158 (TATASTEEL date), N-152 (unattested), IRB's 15% move unexplained. |
| Reporting criteria (§78 items 2–4) | **NO-GO on 1.1.8 as a closed repair** | N-149 closes; N-148 closes with N-159; N-150 is bypassable by omission (N-156). Two of three hold, and the one that does not is the row that will judge the 2024 fold. |
| Repository gate (§78.15) | **NO-GO as shipped** | N-154 (freeze unverifiable from a clone; committed suite red on clone) and N-155 (suite gate bypassable by one JSON row). Both are in the instruments §78 asked for. |
| Certification / seq 10 | **NO-GO, unchanged** | No candidate is certifiable at T = 493, N = 10 (Sharpe 2.314 required at DSR 0.95; seq 9 measures 0.873). Pre-2022 ingestion remains the unblocking work, and it is now gated on §79.13. |

### 79.12 Work order

Ordered by what each item unblocks. Each names the probe that must fail closed before it closes.

1. **N-155 — anchor the green cache** (serves §12.3; unblocks every subsequent commit). Probe: repeat §79.8's forgery; the gate must print `unknown source-tree hash` and run the suite. Also: a record with `verify_exits: {}` or `suite_count` below the pinned floor must be non-reusable, and a full run must not leave the tracked cache file dirty.
2. **N-156 — OVERFIT-06 requires the fold count** (serves Phase 3B-2 certification; unblocks the 2024 fold). Probe: `{ratio: 1.00}` with no count → NOT RUN; `{ratio: 1.00, count: 2}` → PASS.
3. **N-154 — ratify the re-pin, then remove the platform dependence** (serves §12.3). Probe: on a fresh clone, `test_audit_volume1_is_frozen_at_its_pinned_digest` passes and `W0.5-1b` passes without hand-editing a working copy.
4. **N-158 — TATASTEEL's one-session disagreement** (serves Phase 3B-2 identity). Probe: for every documented pair, `ex_date == successor.effective_from` or the generator fails.
5. **N-159 — require the closed-only count with `total_trades`** (serves reporting). Probe: `{total_trades: 205, liquidated_open_positions: []}` → NOT RUN.
6. **N-157 — ratify or revert the ledger transition semantics** (serves §11). Probe: append a CLOSED row and a later OPEN row for the same id; the verifier must reject the backward transition and accept the forward one.
7. **Pre-2022 ingestion**, gated by §79.13 (serves §10.8 and the seq-10 ruling). Then, and only then, seq 10.

### 79.13 Bronze ingestion: acceptance checklist and gates for §78.16 item 7

The target: `2018-04-01 .. 2021-12-31` NSE Bhavcopy into Bronze, the dev corpus extended to roughly 1,470 in-sample sessions, the 2024 validation fold frozen and the holdout sealed. Each gate below is a computation with a printed number; none is satisfied by a sentence. Nothing here is new machinery: every gate names an existing component.

**A. Preconditions — blocking, and none are code.**

- **A1 — an authoritative 2018-2021 session grid.** §6.3 forbids building a calendar from the price files it will judge. `data/reference/calendar_reconciliation_2022_2026.json` carries 12 dated amendment records over 2022-01-03..2026-10-31 and **zero** dates in 2018-2021; `TradingCalendar` is constructed from session records, not from a holiday formula. Gate: a committed session grid for 2018-04-01..2021-12-31 with its own provenance (NSE holiday circulars per year, each a manifest artifact), a `CAL-FPR` fingerprint, and a printed count per year. Without it, every 2018-2021 bar is an unsourced session and the whole window is warm-up.
- **A2 — identity table complete for the window** (done in `3119cb2`, §79.5) plus N-158 resolved, so a pre-2022 symbol whose ISIN changed does not refuse.
- **A3 — surveillance history.** ASM is effective 2018-03-26 and GSM 2017-03-14; both fall inside this window, and §10.8 says a GO/NO-GO may only be computed on sessions where the surveillance state exists. Gate: an interval table `[effective_from, effective_to)` for ASM/GSM/ESM covering the window, or an explicit statement that 2018-03-26..2021-12-31 is warm-up and the **binding** window starts 2022-01-03 — chosen before the run, not after seeing the result.
- **A4 — dividends.** §13.2: an ex-dividend date inside a held position is a cash inflow. A corporate-action table without dividend rows inside 2018-2021 makes every cross-quarter hold wrong. Gate: every ex-date in the window has a row, or the strategy's maximum hold is bounded below the shortest ex-date gap.

**B. Bronze gates — per archive, fail closed.**

- **B1 byte-exactness.** `BronzeStorage.store_payload` records `source_url`, `retrieved_at`, `byte_count`, `sha256` in the append-only manifest; re-storing a path with different bytes without a `restatement_ref` raises. Gate: manifest rows == archives, every digest re-verified, zero restatements.
- **B2 format coverage.** 2018-2021 uses the legacy header (`SYMBOL, SERIES, OPEN …, TOTTRDQTY, TOTTRDVAL, TIMESTAMP, ISIN`). Gate: `parse_bhavcopy_archive` exercised on one committed archive per year 2018, 2019, 2020, 2021 with the record count printed; the unified (`TCKRSYMB…`) path must not be assumed.
- **B3 one partition per session.** Gate: for each year, `archives == sessions in A1`, zero duplicates, zero off-calendar dates, zero dates missing from storage. A session in the calendar but absent in Bronze is `PriceSeriesGapType.UNEXPLAINED_MISSING_RECORD` — refused, never forward-filled, never interpolated, never `NaN`, never `0.00` (§6.3). The count of unexplained gaps in the extended corpus must print as **zero** or the extension is rejected.
- **B4 row-level invariants.** Mixed-date archives rejected (`H-24`); integral volume (`H-23`); positive finite OHLC with `low <= open, close <= high`; at most one `EQ` row per ISIN per session; truncated target rows fail closed (`H-25`). Gate: the parse summary per year — total rows, extracted, dropped by reason — printed, with zero unexplained drops.
- **B5 series.** `EQ, BE, SM, BZ` ingested; `BE` bars are continuity observations only and are never entry-eligible (`APPROVED_EQ_ONLY_POLICY`, §13.1). Gate: entry-eligible rows per year printed separately from total rows.
- **B6 ISIN identity.** Rows are keyed by ISIN; `symbol` and `series` are effective-dated attributes. Gate: zero unresolved symbols in the extended window, or each unresolved symbol listed with its session count and excluded instrument-by-instrument — never a silent skip.
- **B7 Silver append-only.** One immutable partition per session (`G2B.5-5`), off-calendar writes rejected (`E-2`), holdout dates 2025-01-01..2026-11-11 rejected for standard storage (`H-12`). Gate: `scripts/verify_phase2b5_storage.py` exit 0 (gates G2B.5-1..7) after the run, unchanged.
- **B8 exactness across the boundary.** `DECIMAL(18,4)` prices and `int64` volume read back as `Decimal`; no float at the storage boundary. Gate: a round-trip test over 1,000 random 2019 rows comparing `str(close)` to the raw CSV string.
- **B9 publication.** New manifest rows for the extended corpus, `DATA-CTNT-V2` fingerprint, `expected_manifest_fingerprint` re-pinned and criteria version bumped (1.1.9) **in the same commit**; the previous row retained as superseded.

**C. Corpus extension gates.**

- **C1 session count.** 743 today; the extended in-sample (2018-04-01..2023-12-31) must equal 743 + the sessions A1 enumerates, printed, not typed.
- **C2 partition discipline.** In-sample only; `validation_folds_count` stays 0 and the 2024 fold stays sealed until the pre-registered run; the holdout remains physically separated. Gate: the four `IS_FOLD_ENDS` unchanged, and the 2024 fold's first session absent from every in-sample artifact.
- **C3 registry untouched.** N = 9, N_eval = 5, trials manifest pin `3326b1b2…` — ingestion is data, not a trial. Gate: the registry and its manifest are byte-identical before and after.
- **C4 byte reproducibility.** `historical_dev_dataset_*.json` regenerates from the committed Bronze corpus with an identical sha256. Gate: run the generator twice, compare digests, print both.
- **C5 spot check.** 50 randomly chosen instrument-sessions in 2019: recompute OHLCV from Bronze and compare Decimal-exactly to the snapshot. Zero mismatches.
- **C6 the DSR denominator, computed.** After extension, print T, N, N_eval, and the Sharpe a DSR of 0.95 requires at that T. At T = 493, N = 10 it is 2.314 in-sample and 1.765 haircut; at T ≈ 1,470 it is roughly 1.78. If the extension does not move the bar below something the strategy can plausibly reach, extending was not the constraint and should be said.

**D. Acceptance checklist for the deliverable.**

- [ ] `scripts/verify_audit_append_only.py --force-full` exit 0; suite green, **0 skipped, 0 xfailed**.
- [ ] Every gate above prints its number in a committed report; every unrun gate prints `NOT RUN`.
- [ ] Zero unexplained session gaps; zero forward fills; zero interpolated bars; zero `0.00`/`NaN` prices.
- [ ] Every artifact `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` unless an NSE circular hash is in the manifest (§6.5).
- [ ] `CURRENT_STAGE_OF_WORK.md` cites this section and the SHA that implements it (§11.3), and does not describe ingestion as verified before §80 measures it.
- [ ] No `float` on the accounting path; no `UPDATE`/`DELETE` against the 2018-2021 history.
- [ ] The 2024 fold and the holdout are provably untouched: `validation_folds_count 0`, holdout storage empty.

**Not in scope, deliberately:** no second simulator, no `BE` entry, no annualisation or frequency change to make the extended window look better, and no seq 10 run before A1 through A4 and B1 through B9 are green.

### 79.14 What would falsify this verdict

- If the pinned digest `7c7760f…` turns out to be reproducible from some git object or clone configuration I did not test, then N-154 is my measurement error and the re-pin is unjustified. The test is one command: `git cat-file blob <sha>:<path> | sha256sum` on the commit, plus a fresh `git clone` and `pytest -q`; if the frozen test passes there, I am wrong.
- If a forged green-cache row fails to skip the suite on a machine where the gate is otherwise green, N-155 is wrong. Mine was measured with a poisoned source file and a forged row; the transcript is reproducible in five commands.
- If `{walk_forward_positive_fold_ratio: 1.00}` with no count is NOT RUN in some path I did not construct, N-156 is wrong.
- If the 324 generated transition rows contradict TATASTEEL's, VBL's or COCHINSHIP's real circulars — which none of them cites — then N-152 is not an accepted residual but a live defect, and the generator is manufacturing identity continuity. Only an external source can settle it.
- If the identity table's successor dates are themselves wrong for symbols outside the 211-instrument corpus, N-151's closure is coverage of a table that is wrong, not of the market.

### 79.15 Correction — the suite clock in §79.1

§79.1's table reports the suite as `523 passed … (117 s)`. The 117 s is the implementer's recorded
`pytest_seconds` in `source_tree_green.json`, not this round's measurement: the gate run that
validates this commit printed `523 passed in 102.50s (0:01:42)` at W0.5-3 under `--force-full`. Count,
skips and xfails stand as reported; only the clock is corrected. §79.1 is left as committed because
this volume is append-only (§11.1) — the correction is appended, never edited in place (§10.1).

## §80 — Audit of `96d24a1` (tag `feat-s79-e0290b4`): five of six §79 repairs hold, and the green cache still pays for a test it never ran

**Date:** 17 November 2026
**Commit under review:** `96d24a1` (1 file, +18 lines). The tag `feat-s79-e0290b4` names `e0290b4`, its
parent; the deliverable is the pair, because `e0290b4` is the fix and `96d24a1` is the cache row it left
behind.
**Baseline:** `3119cb2` (§79, tag `audit-s79-67235d97`)
**Verdicts:** N-154 CLOSED · N-156 CLOSED · N-157 CLOSED · N-158 CLOSED · N-159 CLOSED ·
N-155 **PARTIAL, held open** · N-152 ACCEPTED (unchanged) · two new findings, one HIGH

### 80.1 Baseline re-measured at `96d24a1`

The suite and every verifier were re-run on this checkout, not read.

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | exit 0, `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers | 10 `scripts/verify_*.py` on disk, **9** executed by W0.5-2 (the gate excludes itself), all exit 0 |
| Test suite | **529 passed, 0 skipped, 0 xfailed** (115.08 s; gate elapsed 116.17 s) |
| W0.5-5 reference manifest | 46 current artifacts match, 22 superseded rows skipped |
| W0.5-3 cache | source tree `87f0fd5d…` already recorded; **no append**, and `git status` is clean after the run |
| `verify_audit_findings.py` | exit 0, 6 ids: 5 probes executed, N-152 carried `ACCEPTED` |
| TrialRegistry | N = 9, N_eval = 5, manifest 323 B `3326b1b2…`, head `50de55e9…` |
| Criteria | 1.1.9; Phase 2D artifact fingerprint `CRIT-FPR-V1-7b21f77d…`; every numeric threshold byte-identical to §79.10 |
| Calendar | `CAL-FPR-V1-af8e309a…`, 2,935 sessions, 2015-01-01 .. 2026-11-11 |
| 2024 fold / holdout | Partition spec: IS 2018-04-01..2023-12-31, validation 2024-01-01..2024-12-31, holdout 2025-01-01..2026-11-11. No fold was run. The Phase 2D artifact carries no fold field; the only committed `validation_folds_count` is `1`, in the Phase 3B-2 baseline verdict under criteria 1.1.0. No `storage/` tree and no `HOLDOUT_UNLOCK` exist in the repository. |

### 80.2 N-154 — CLOSED

| Measurement | Value |
|---|---|
| Working file digest (`compute_volume_digest`) | `f4ca03d58466bebb…`, **8,442** lines, 0 CRLF bytes |
| The same text re-encoded as CRLF (raw bytes differ) | `f4ca03d58466bebb…`, 8,442 lines |
| Gate W0.5-1b | PASS against the pin |
| `.gitattributes` | `reports/audit/** text eol=lf` present |

`f4ca03d5…` is the digest of the blob `git` stores (§79.7 measured it independently), and the canonical
hash folds CRLF, so the pin is now satisfiable both by the stored bytes and by a Windows working copy
that holds the same text with CRLF. The committed volume is untouched. The platform dependence that made
the old pin a property of one machine is gone for line endings. **CLOSED.**

### 80.3 N-155 — PARTIAL: three holes closed, the fourth acceptance condition is not implemented

The three conditions the fix added are real. Measured directly through `green_record_problem`:

| Record | Result |
|---|---|
| `verify_exits: {}` | `cache record witnesses 0 verifier(s), not the 9 discovered one(s)` |
| `suite_count: 1` | `cache record suite_count 1 is below the pinned floor 500` |
| `gate_sha: "forged"` | `cache record gate_sha 'forged' is not a commit in this repository` |
| all nine exits 0, `suite_count: 529`, `gate_sha: 96d24a1`, fresh `utc` | **`REUSABLE`** |

That last row is the §79.8 forgery, replayed end to end on a fresh clone of `96d24a1`:
append `def test_probe_poison_fails(): assert False` to `tests/unit/test_verdicts.py`, compute the tree
hash with the gate's own `compute_source_tree_hash(source_tree_entries())`, append a row carrying that
hash, 529, all nine verifier names at 0, `gate_sha: "96d24a1"` and the current time, then run
`python scripts/verify_audit_append_only.py`. Result: `select_gate_plan` returns **reuse**, the gate
prints `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)`, exit 0, and `pytest` never
runs. A tree whose only test evidence is a number the attacker typed still certifies itself.

The missing condition is the fourth bullet of §79.8, quoted there as the acceptance test: *a record must
bind to a commit that exists and whose tree hash equals the recorded hash (`git rev-parse
gate_sha^{tree}` plus a file-set digest), so a row written by hand cannot name a tree that was never run.*
`green_record_problem` resolves `gate_sha` with `git rev-parse --verify` and stops; it never projects a
tree and never compares one to the recorded hash.

The second measurement says the same thing from the other side. The hash is taken over **working-copy
bytes**, and this checkout is not the commit: **20** tracked files differ from their committed blobs —
every one CRLF in the working copy and LF in the blob — including `configs/go_no_go_criteria.yaml`
(280 CRLF) and nine `reports/verdicts/**` artifacts. Working-copy hash `87f0fd5d…`; the same file set
hashed from `git cat-file blob` yields **`816783f8…`**, which is exactly what a fresh clone computes. The
committed row names `87f0fd5d…` and `gate_sha: e0290b4`, so on a clone it is `unknown source-tree hash`
and the heavy gates run. The row is not reproducible from the commit it is committed in, and it names no
tree `e0290b4` has. Fail-closed is the right direction for a clone, but a cache that cannot hit on a
clone is not evidence a clone can reuse. This round's own full run reproduces the same pattern from the
auditor's side: the row it appends names `96d24a1`, and the commit that carries it will be its child. The
defect is structural, not a lapse by whoever typed the row.

Held **OPEN** as **N-160** (HIGH). This is not goalpost-moving: the condition is §79.8's own, written
before the fix existed. What §79.12 item 1 did close stays closed — empty verifier maps, sub-floor suite
counts, unresolvable `gate_sha`, a 24 h age limit, the two runtime verifiers on reuse, and a full run that
no longer dirties the tracked cache.

### 80.4 N-156 — CLOSED

Measured on `CRIT-OVERFIT-06` directly:

| Bundle | Status | Computed |
|---|---|---|
| `{ratio: 1.00}` | **NOT RUN** | — |
| `{ratio: 1.00, count: 1}` | **NOT RUN** | — |
| `{ratio: 1.00, count: 2}` | PASS | 1.0000 |
| `{ratio: 0.50, count: 2}` | FAIL | 0.5000 |
| `{count: 2}` (no ratio) | NOT RUN | — |
| `{ratio: 1.00, count: true}` | NOT RUN | — |
| `{ratio: 1.00, count: 0}` | NOT RUN | — |
| `{ratio: 1.00, count: "2"}` | **PASS** | 1.0000 |

The omission bypass is gone: a ratio without a count is no longer evidence, and the two-fold floor is
read before the ratio is gated. Residual carried as **N-161** (LOW): the fold count is coerced, so the
*numeric string* `"2"` is accepted where the acceptance said a valid integer. It cannot lower the
floor — any coerced value still has to clear two — so it cannot reopen N-156, but it is a type leniency
inside the row that will judge the 2024 fold.

### 80.5 N-157 — CLOSED

| Ledger | `validate_ledger` |
|---|---|
| `OPEN → CLOSED (80)` | accepted |
| `OPEN → ACCEPTED → CLOSED (80)` | accepted |
| `OPEN → CLOSED → OPEN` | refused: `CLOSED -> OPEN ... not a forward transition` |
| duplicate `OPEN` | refused: `Duplicate finding id N-999` |
| `CLOSED` with no `closed_in_section` | refused |
| the committed 15-row ledger (10 inherited, 5 appended here) | accepted |

One property to name rather than imply: a **first** row for a new id may be `CLOSED`, because there is no
prior status to transition from. That is how this round registers five closures for findings that were
raised in §79 and deliberately never entered as `OPEN` (§79.9). It is a closure register, not a
defect register, and that is what the schema now says. **CLOSED.**

### 80.6 N-158 — CLOSED

| Measurement | Value |
|---|---|
| Adjacent identity pairs | **324** |
| Pairs whose documented `ex_date` equals the successor interval's `effective_from` | **324** |
| Misaligned | **0** |
| `TATASTEEL` `ISIN_TRANSITION` date | **2022-07-29** |
| `TATASTEEL` `SPLIT` date | 2022-07-28 (a price-adjustment claim; changes no series) |
| A hand-dated row drifted to 2022-07-28 | refused: `documented ISIN_TRANSITION date(s) disagree with the interval table (N-158)` |

The generator no longer skips a documented pair whose date disagrees with the table; it fails. The
residual from §79.5 stands unchanged as N-152: every transition row is unattested and names the interval
table that derived it. **CLOSED** as the one-session disagreement; not as evidence that any transition is
real.

### 80.7 N-159 — CLOSED

| Bundle | Status | Computed |
|---|---|---|
| `{205, positions: []}` | **NOT RUN** | — |
| `{205, positions: 12}` | **NOT RUN** | — |
| `{205, closed 193, positions 12}` | PASS | 205 |
| `{205, closed 200, positions 12}` | FAIL | 205 |
| `{205, closed 193}` (no positions) | NOT RUN | — |
| `{193, liquidated_trade_count: 193}` | PASS | 193 |
| `{193}` alone | NOT RUN | — |

The empty-list shape that §79.2 carried as N-159 no longer passes; the declared-count arm is unchanged.
**CLOSED.**

### 80.8 What the work log now says (§11.3)

`CURRENT_STAGE_OF_WORK.md`'s §79 note opens with `Not audited: no verdict judges this commit` and makes
no signed-off, verified or closed claim, so §11.3 is not violated by it. Two sentences overstate what was
measured, and the implementer should append this section's finding rather than rewrite them:

- *`N-154 … cannot recur`* — measured true for line endings only. The cache half of the same defect (a
  digest over working-copy bytes rather than over the object `git` stores) is N-160 and did recur.
- *`A cached tree is no longer trusted on its own`* — true for the three conditions that were listed, and
  false for the fourth condition §79.8 also listed.

### 80.9 §79.13 preconditions: 2018-04-01..2021-12-31 is warm-up only, and three preconditions are not met

Each line below is a measurement on this commit, against the preconditions written in §79.13 before the
work existed.

| Gate | Measurement | Status |
|---|---|---|
| **A1** session grid | `configs/trading_calendar_nse.json` covers 2015-01-01..2026-11-11: **930** sessions in 2018-04-01..2021-12-31 (2018 246, 2019 244, 2020 252, 2021 248), `CAL-FPR-V1-af8e309a…`, 5 non-`FULL` sessions in the window. But **zero holiday circulars for 2018-2021**: all 13 `data/raw/circulars` artifacts are issued 2021-12-10..2026-01-12, and the only one that names an in-window year is the 2022 list. `provenance.sha256` equals the calendar's own CAL-FPR hex — a self-digest, not a source artifact. | **NO** — the grid and counts exist, the per-year provenance does not |
| **A2** identity for the window | `cash_equity_symbol_intervals.csv`: **4,510** rows, first `effective_from` **2022-01-03**, zero rows before it. N-158 is resolved (§80.6). | **NO** for the window; the table begins where Bronze begins |
| **A3** surveillance history | `surveillance_intervals.jsonl`: **3** rows, all `SYNTHETIC_FIXTURE_*`, all 2024; **0** in 2018-2021. The alternative form is committed and predates this round: `min_binding_evaluation_start_date: 2022-01-03` in criteria and `BINDING_EVALUATION_START_DATE` in `storage/gating.py`, which forces every pre-2022 verdict to `NOT RUN` (§52.9, H-65). | **Met only in the warm-up form** — the window cannot gate |
| **A4** dividends | `corporate_actions.jsonl`: **138** `DIVIDEND` rows, 2022-03-29 .. 2024-08-21, **0** in 2018-2021; no maximum-hold bound in `configs/go_no_go_criteria.yaml`. | **NO** |

**Answer to the question this round was asked to settle: no.** The §79.13 preconditions do not authorise
treating 2018-04-01..2021-12-31 Bronze as gating in-sample material. A1 has no 2018-2021 source artifact,
A2's identity table starts on 2022-01-03, A4 has no 2018-2021 ex-dates, and A3 is satisfied only by the
committed declaration that the window is warm-up, which pins the binding start at 2022-01-03.

The ingestion can begin as *warm-up-only capture* under B1 through B9 — the archives are data, and B1-B9
fail closed per archive — but it cannot extend the binding corpus, and it cannot move C6's DSR
denominator, because the sessions it adds are `NOT RUN` for gating by the criteria's own pin. The honest
statement before the work is the one C6 asks for: at a binding window of 2022-01-03..2023-12-31
(**494** sessions) the DSR bar is unchanged by the extension, so **extending is not the constraint**. A1
provenance, A2 identity and A4 dividends are the constraints, in that order.

### 80.10 Correction — three of my own numbers

Appended, never edited in place (§10.1).

1. **§79.13 A1 said the calendar carries "zero dates in 2018-2021".** That is true of
   `calendar_reconciliation_2022_2026.json` and false of the trading calendar, which enumerates 930
   sessions in the window. What is absent is per-year *source provenance*, not dates. The gate still
   fails, for the reason A1 gives — a grid that is asserted is not a grid that is sourced — but my
   sentence was measured on the wrong artifact.
2. **§79.13 C1's arithmetic is wrong.** `743 + the sessions A1 enumerates` double-counts nothing but
   adds a year that is not in-sample: 743 is the 2022-2024 archive count (248 + 246 + 249), and 2024 is
   the validation partition. The extended in-sample total is `930 + 494 = 1,424`, and while
   `min_binding_evaluation_start_date` is 2022-01-03 the gating T is **494**.
3. **§79.1 reported "9 verifiers on disk, 8 executed".** There are **10** `scripts/verify_*.py` on disk and
   **9** executed by W0.5-2, which is what this round's gate printed and what §80.1 records.

### 80.11 Preserved invariants

Criteria 1.1.9 moves no threshold: `min_total_trades 100`, `min_profit_factor 1.50`,
`min_deflated_sharpe_ratio 0.95`, `min_haircut_sharpe_ratio 1.25`, `max_single_position_weight 0.10`,
`min_traded_eq_resolution_pct 100.0`, `min_dataset_instrument_resolution_pct 100.0`,
`min_positive_walk_forward_fold_ratio 0.80`, `min_positive_is_fold_ratio 0.75`,
`min_fold_liquidated_pf 1.30`, `min_liquidated_pf_ex_top_1 1.40`. The manifest pin is
`MAN-FPR-V1-23200ba8…` over 46 current and 22 superseded rows and reproduces (W0.5-5). The trial
registry is unmoved: N = 9, N_eval = 5, manifest `3326b1b2…` at 323 B. The probes of this round and the
five closures appended by it create no trial row. The 2024 window is still only the validation partition
in the committed spec, and the holdout is still sealed by a zero token hash with no unlock present.

### 80.12 Verdicts

| Area | Verdict | Basis |
|---|---|---|
| Frozen audit volume (N-154) | **GO** | Pin equals the stored blob's digest and a CRLF checkout reproduces it; W0.5-1b PASS |
| Reporting criteria 1.1.9 (N-156, N-159) | **GO** | Both omission bypasses measured closed, ratio-without-count NOT RUN, positions-without-count NOT RUN; no threshold moved |
| Identity & corporate actions (N-158) | **GO** for the dated row | 324/324 aligned, drift refused. Carried: N-152 unattested rows |
| Findings ledger (N-157) | **GO** | Forward transitions enforced, backward and duplicate refused, closures cite a section |
| Repository gate (§79.12 item 1) | **NO-GO as a closed repair** | N-155 PARTIAL: a hand-written row with a real `gate_sha` retires the suite (N-160), and the committed row is not reproducible from the commit |
| Certification / seq 10 | **NO-GO, unchanged** | No candidate is certifiable; pre-2022 ingestion is still the unblocking work |
| 2018-2021 Bronze | **NOT AUTHORISED as gating corpus** | §80.9: A1 provenance, A2 identity, A4 dividends unmet; A3 met only as warm-up |

### 80.13 Work order

Ordered by what each item unblocks. Each names the probe that must fail closed before it closes.

1. **N-160 — make the cache record bind to a tree, not to a directory.** Compute the source-tree hash from
   git objects (`git cat-file blob`), and require the projected hash of `gate_sha`'s tree to equal the
   recorded hash. Probe: replay §80.3's forgery with a real `gate_sha`; the plan must be `full` and the
   suite must run. Second probe: on a fresh clone, the committed row's hash must equal the clone's hash,
   so a clone can reuse green.
2. **N-161 — require an integer fold count.** Probe: `{ratio: 1.00, count: "2"}` → NOT RUN;
   `{ratio: 1.00, count: 2}` stays PASS.
3. **A1 — source the 2018-2021 grid per year** (serves §10.8, the binding window). Probe: for each of
   2018, 2019, 2020, 2021 a holiday circular artifact in the manifest whose entries reproduce that
   year's grid; a missing year fails, and the calendar's provenance hash must be a source digest rather
   than its own CAL-FPR.
4. **A4 — dividends inside the window, or a committed maximum hold** (serves §13.2). Probe: every 2018-2021
   ex-date within the strategy's maximum hold has a row, or the bound prints below the shortest gap
   between consecutive ex-dates.
5. **A2 — state how pre-2022 identity is derived** (serves §10.4). Probe: zero unresolved symbols across
   the extended window, each exception listed with its session count rather than skipped.
6. **B1-B9 on the captured Bronze, then C1-C6 with §80.10's corrected count**, before any seq 10. Probe:
   zero unexplained session gaps, zero restatements, and the 2024 fold and holdout still untouched.
7. **Ratify or revert this round's five ledger closures and their probe implementations** (§79.12 item 6's
   precedent). Probe: `scripts/verify_audit_findings.py` exit 0 with 11 ids, and each closure row's probe
   passing on its own.

### 80.14 What would falsify this verdict

- If a hand-written row with a real `gate_sha`, all nine verifier names at 0 and `suite_count: 529` is
  refused on some path I did not construct, N-160 is wrong. The transcript is four commands: poison a
  test, hash the tree with the gate's own function, append the row, run the gate.
- If a clone configured differently computes `87f0fd5d…` rather than `816783f8…`, then the
  working-copy-only hash is my measurement error and N-160 collapses to the forgery alone.
- If a 2018-2021 holiday circular artifact exists outside `data/raw/circulars` — for example inside a
  Bronze blob the manifest does not name as a circular — then A1 is met and §80.9's first row is wrong.
- If a maximum-hold bound is committed somewhere other than `configs/go_no_go_criteria.yaml`, A4's
  alternative is satisfied and the dividend gap is not blocking.
- If `743` is not the 2022-2024 archive count, the §80.10 correction is wrong and C1 stands as written.
- If `{walk_forward_positive_fold_ratio: 1.00}` with no count can still PASS through a key this round did
  not construct, N-156's closure is wrong.

---

## §81 — Audit of `80ff581` (tag `feat-s80-80ff581`): the cache binds to a tree, and a tree is not a commit

Three commits carry the §80 work order: `c285310` (N-160's blob-oid scheme and N-161's integer count),
`742324c` (a content-based dirty-tree detector) and `80ff581` (the implementer's status section and two
cache rows). The source tree of `80ff581` is byte-identical to `742324c`'s — `eb61ec28ecd13cd1…` from
both — because it touches only `CURRENT_STAGE_OF_WORK.md` and `data/reference/source_tree_green.json`,
paths the gate excludes. That identity is a property of the design, not an accident, and it is what this
round's two central measurements turn on.

### 81.1 Baseline re-measured at `80ff581`

| Instrument | Result at `80ff581` |
|---|---|
| `verify_audit_append_only.py --force-full` | **exit 1** — `ONE OR MORE GATES FAILED` |
| pytest inside that run | **1 failed, 533 passed** in 108.55 s; 534 collected, 0 skipped, 0 xfailed |
| `verify_audit_append_only.py` (no flag) | **exit 0** — `reused green at 742324c (534 passed, recorded 2026-11-17T10:21:32)` |
| `scripts/verify_*.py` discovered / executed | 9 / 9, every exit 0 (W0.5-2 PASS) |
| W0.5-1 / 1b / 1c | PASS — 8,442 lines; 2 audit volumes; INDEX reproduces at 80 section rows |
| W0.5-4 / W0.5-5 | PASS — 78 commit-bearing tags; 46 current / 22 superseded manifest rows |
| Findings ledger | 15 rows / 11 ids; 11 probes PASS; N-152 `ACCEPTED`, N-150 `OPEN` |
| Criteria / manifest pin / trials | 1.1.9 / `MAN-FPR-V1-23200ba8…` / N = 9, N_eval = 5 |
| 2024 fold / holdout | `validation_folds_count = 0`; no `HOLDOUT_UNLOCK` in the tree |
| Source-tree identity | `80ff581`, `742324c` → `eb61ec28…`; `c285310` → `333bead0…` |

The first two rows describe the same commit. The gate says the tree is green because a record exists for
that tree; pytest says it is red. §81.4 is the measurement of how both can be true, and §81.5 is why the
red one is not noise.

### 81.2 N-160 — `CLOSED`

§80.3 named four conditions on a cache record. Measured directly against `green_record_problem`, with the
scheme and the nine discovered verifiers injected rather than read:

| Record | Verdict |
|---|---|
| HEAD's tree, `gate_sha: HEAD`, 534, nine zero exits | accepted (`None`) |
| `source_tree_scheme` stripped | refused — *"was not written by the git-blob-oid-v1 source-tree scheme"* |
| HEAD's `gate_sha`, another tree's hash | refused — *"is not the tree at gate_sha … that commit's tree projects eb61ec28ecd1…"* |
| `gate_sha: "deadbeef"` | refused — *"is not a commit in this repository"* |
| `verify_exits: {}` | refused — *"witnesses 0 verifier(s), not the 9 discovered one(s)"* |
| `suite_count: 1` | refused — *"below the pinned floor 500"* |

The platform half is measured end to end, not argued: a shallow `git clone --depth 1` on this machine —
LF working copy, no CRLF anywhere — projects `eb61ec28ecd13cd1dfa851a4ba5c309ee193715ae04990c21c76939f992ee6bd`
for `80ff581` over 1,391 source entries, the same digest this CRLF checkout computes. §80's `87f0fd5d…` /
`816783f8…` split is gone because no code path reads working-copy bytes; `source_tree_entries()` and
`source_tree_hash_at_commit()` both compose `git ls-tree` object ids.

**Residual (accepted, not a work item).** The cache remains unauthenticated: a row naming a real commit's
real tree, nine verifier names at `0` and `suite_count: 534` is accepted, because the gate cannot tell a
hand-written row from one it wrote. It was measured (`suite_count: 534 (no exits run) → None`). This is
inherent to a local file and bounded by the daily `--force-full` rule; closing it would need signed rows
or gate-only writes, which is a maintainer decision, not a repair.

### 81.3 N-161 — `CLOSED`

Measured through `evaluate_verdicts` with the bundle built here, not through the implementer's probe:

| `walk_forward_validation_folds_count` | `CRIT-OVERFIT-06` |
|---|---|
| `2` (int) | **PASS** 1.0000 |
| `3` (int) | **PASS** 1.0000 |
| `"2"` | NOT RUN — *"supplied without a valid integer"* |
| `2.0` | NOT RUN — same |
| `True` | NOT RUN — same |
| `Decimal(2)` | NOT RUN — same |
| `"2.5"` | NOT RUN — same |
| `None` | NOT RUN — same |
| `1` / `0` / `-3` | NOT RUN — *"Only N_val = N validation fold evaluated; minimum 2"* |

The `bool` arm matters independently of the string arm: `isinstance(True, int)` is true in Python, so a
type-only check would have counted a boolean as one fold. The residual is closed for the reason it named.

### 81.4 N-162 (`HIGH`, new) — the reuse key is a tree, and the suite is not a function of the tree

Two measurements, both on a clean tree, neither touching the cache:

**A. A docs-only commit inherits its parent's green run.** `80ff581` adds a section and two cache rows, so
its source tree is `742324c`'s. The gate therefore printed

```
[INFO] Source-tree hash eb61ec28ecd13cd1… — source tree unchanged since a green run
[INFO] reused green at 742324c (534 passed, recorded 2026-11-17T10:21:32…) — heavy gates skipped
OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)
```

with exit 0, while `python -m pytest -q` on the same checkout printed `1 failed, 533 passed` and exit 1.
The suite is not a function of the tree here because `test_n160_a_hand_written_hash_names_no_tree_and_is_refused`
reads `HEAD^`, and `80ff581`'s parent has the same tree as `80ff581`. The green record was true for
`742324c` and false for the commit it was spent on.

**B. An untracked file is invisible to the dirty set.** Writing
`tests/unit/test_s81_untracked_temp.py` with `assert False` left `git status` reporting `?? …` and
`dirty_source_paths()` returning `[]` — it runs `git diff-index --untracked-files=no`, so a file pytest
either collects or ignores never reaches the reuse decision. The gate again printed `reused green at
742324c` and `ALL REPOSITORY FOUNDATION GATES PASSED`, exit 0; `pytest` on that file alone printed
`1 failed`. The file was removed and the tree verified clean afterwards.

Both are the same defect: the key is the source tree, and the thing whose greenness is being asserted is a
suite that also depends on the commit (parentage) and on files outside the tree (untracked tests). §80.3's
rule — "the record must be one the gate could have produced" — is satisfied at the record and violated at
the consumer, so N-160 closes on its own conditions and this is a new, separate finding rather than a
retracted closure (§14.5). The repo's own skill now states the weakened form ("it reuses a record only when
the tree of the record's `gate_sha` projects to the recorded hash"), which is exactly the predicate measured
wrong here.

**Fix direction (work item 2).** Key reuse on `(source tree, HEAD oid)` — a row is reusable only when its
`gate_sha` is the commit being verified — and add untracked source paths to the dirty set. The cost is one
full run per commit, which is already the daily rule; what reuse still buys is repeated runs of the same
HEAD, which is the local case it was built for.

### 81.5 N-163 (`MEDIUM`, new) — the audited commit is red, and the test that makes it red is a test bug

At `80ff581`, `python -m pytest -q` → `1 failed, 533 passed`, exit 1. The failure is
`tests/unit/test_phase3b2_audit_s80_items.py:108`:

```
other = _git("rev-parse", f"{head}^").decode().strip()
assert gate.green_record_problem(_green_record(head_hash, other), …) is not None
E   AssertionError: assert None is not None
```

At `742324c` the same line passed, because `HEAD^` there is `c285310` (`333bead0…` ≠ `eb61ec28…`); at
`80ff581` `HEAD^` is `742324c` and the two trees are equal, so a record naming the parent is a record of
the same tree and is correctly accepted. The test encodes an assumption about its own commit's parentage,
not a property of the cache. Restated plainly: the product behaviour is right, the test is wrong, and the
commit that claims `534 passed, 0 skipped, 0 xfailed` is red at its own SHA. The implementer's number was
true when it was taken, at `742324c`, before `80ff581` existed; it is not true of `80ff581`, and
`CURRENT_STAGE_OF_WORK.md` cites it as the round's baseline (a `§11.3` citation gap: the sentence names
`ALL REPOSITORY FOUNDATION GATES PASSED` without the caveat that the commit it describes was not the
commit measured).

### 81.6 N-164 (`MEDIUM`, new) — the ledger's N-160 evidence passes vacuously

`probe_n160` is the executable evidence behind a closure, so it was instrumented rather than trusted.
`git()` inside that probe returns **bytes**, and the probe does

```
parent = git("rev-parse", f"{head}^")
assert green_record_problem(record(head_hash, gate_sha=parent), verifiers, commit_exists) is not None
```

so `gate_sha` becomes `"b'742324ce14…\\n'"` and the refusal is *"cache record gate_sha … is not a commit in
this repository"* — a string-typing accident, not the tree comparison the assertion names. Spying on
`green_record_problem` during a probe run shows five calls: the twinned healthy records, the forged hash
twice, and then `gate_sha= b'742324…` refused as a non-commit. With the parent line decoded, the same
assertion fails (measured: `problem = None`). The probe would therefore still print `PASS` with its final
assertion deleted. The pytest twin decodes and fails, which is why the suite is red and `verify_audit_findings.py`
is green — the additive-fix pattern §14.4 describes, now inside the audit instrument itself.

N-160's closure in §81.2 does not rest on that probe: it rests on the six-row record matrix and the clone
measurement taken here. The probe must still be repaired (work item 3), because a ledger row whose probe
cannot fail is not evidence.

### 81.7 §80.13 items 3-5 — prepared, and correctly not executed

`scripts/probe_pre2022_preconditions.py` exits **1** with 8 of 8 checks `NO` (four `A1` years, `A1`
provenance, `A2`, `A4` dividends, `A4` max hold), writes nothing (`git status` clean after the run), and is
deliberately not named `verify_*.py`: the gate still discovers 9 verifiers and `pre2022` is not among them,
which is the right call under §12.4 — a readiness probe registered as a gate would either be red forever or
tempt a skip. `docs/pre2022_ingestion_preconditions.md` is honest about its own status ("prepared, not
ingested", "Nothing here is audited"), names the derivation that already exists
(`derive_cash_universe_intervals.py`) instead of inventing a mechanism, and keeps the ordering
A1 → A2 → A4 → B1-B9 → C1-C6. Two process facts belong on the record:

- The document's own arithmetic agrees with §80.10 (`930` window sessions, `494` gating, `1,424` extended
  in-sample), so the correction is carried forward rather than re-litigated.
- `c285310` adds 66 lines to `.agents/skills/audit-round/SKILL.md`, the auditor's own procedure. The content
  is consistent with §80.3 and §81.4 and is ratified here by citation, but an implementer writing the rules
  its own work is judged by is a §11.1-adjacent conflict: from this section the skill is the auditor's, and a
  proposed change arrives as a note citing the finding it serves.

### 81.8 Ruling 1 — capture eligibility and gating eligibility are different preconditions

*Evidence.* At `80ff581`, `probe_pre2022_preconditions.py` exit 1, 8/8 `NO`: no committed holiday circular
names any 2018-2021 date among the 13 artifacts on disk (all issued 2021-12-10..2026-01-12); the calendar's
`provenance.sha256` is its own `CAL-FPR-V1-af8e309a…` hex; the interval table begins 2022-01-03 (4,510 rows,
0 reaching 2021-12-31); 0 of 138 ex-dates fall in the window.

*It changes one definition.* A pre-2022 session becomes **capturable** when A1 holds — a sourced holiday
circular whose declared holidays and special sessions reproduce the calendar's session set for that year —
and it is then labelled `WARMUP_NOT_GATABLE`. A pre-2022 session becomes **gatable** only when A1, A2 and A4
all hold. The A1-first ordering is not a preference: §6.3 fails a missing session closed against an
authoritative calendar, so without A1 a captured series cannot even be checked for gaps, and A2/A4 govern
whether a held position and its ex-dates are accounted for — neither of which can be evaluated over a corpus
that is not there.

*It changes nothing else.* Not the pin (`min_binding_evaluation_start_date: 2022-01-03`), not the window
start `2018-04-01` in §10.8, not the DSR/Haircut thresholds, not N or N_eval, not the 2024 fold, not the
holdout.

*Probe that must fail closed.* The readiness probe gains a gating mode: it exits non-zero if any verdict's
evaluated session set contains a `WARMUP_NOT_GATABLE` session, and per-year A1 checks exit non-zero unless
`weekdays(year) - declared_holidays ∪ declared_special_sessions` equals the calendar's session set for that
year with zero unexplained and zero unmatched dates.

*Work item.* 5 (A1 sourcing) and 6 (the label and the gating guard), serving Phase 3B-2 / §10.8.

*Falsifier.* A 2018-2021 session whose continuity can be established without a sourced calendar — for
instance a consolidated circular covering all four years — would make A1 a single artifact rather than four,
but would not weaken the rule that capture needs provenance before it needs identity.

### 81.9 Ruling 2 — the pin is the operative window, and relaxing it re-derives the denominator

*Evidence.* `configs/go_no_go_criteria.yaml:209` pins `min_binding_evaluation_start_date: "2022-01-03"`, and
that pin is what returns `NOT RUN` for every pre-2022 session today; §80.10's counts (`1,424` in-sample,
`T = 494`) follow from it. §10.8's stated window is `2018-04-01..2021-12-31`, so the pin is stricter than the
rule it implements.

*It changes one definition.* While A1, A2 and A4 are unmet, the committed pin is the operative expression of
§10.8's window and pre-2022 sessions are warm-up only; the pin is *provisional*, not a narrowing of the
standing window. When the pin moves, the gating session count `T` and every denominator derived from it (DSR,
Haircut Sharpe, `N_eval`) are **recomputed** from the sessions actually gated, never carried from `494`.

*It changes nothing else.* The DSR/Haircut thresholds, the fold partition ends, the 2024 validation freeze,
the holdout seal, and `N = 9` / `N_eval = 5`.

*Probe that must fail closed.* A criteria test that refuses a `min_binding_evaluation_start_date` earlier than
`2022-01-03` unless `probe_pre2022_preconditions.py` exits 0 at the same commit, and a reporting test that
refuses a DSR/Haircut denominator unequal to the computed gating `T`.

*Work item.* 7, serving Phase 2D and Phase 3B-2.

*Falsifier.* A verdict that computes CRIT-STAT-01, the DSR or the Haircut Sharpe over pre-2022 sessions while
any of A1/A2/A4 is unmet would show the pin is not, in fact, operative.

### 81.10 Phase verdicts and residuals

| Phase / claim | Verdict at `80ff581` | Residuals named |
|---|---|---|
| `§12.3` repository gate | **NO-GO** — red suite, and a plain run reports PASS for the same SHA | N-162 (reuse key), N-163 (red test) |
| N-160 repair | **CLOSED** — six record-level conditions measured; clone recomputes the digest | unauthenticated cache (§81.2) |
| N-161 repair | **CLOSED** — 11 input shapes measured | none |
| ``§80.13`` items 1-2 | **DELIVERED** — the two repairs above | their probes: N-164 |
| ``§80.13`` items 3-5 | **PREPARED, NOT EXECUTED** — probe exit 1, 8/8 `NO`, 0 artifacts written | A1, A2, A4 open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, N = 9, N_eval = 5, fold 0, no unlock | N-152 `ACCEPTED`, N-150 `OPEN` |

No phase moves toward GO on this commit: a red suite plus a gate that reports it green is a stronger reason
to stop than a clean round would be to continue. The pre-2022 block is not a phase verdict — no data exists,
so there is nothing to judge, which is exactly what §9.3 requires the document to say.

### 81.11 Work order

1. **Green the suite at HEAD** (N-163). Replace the `HEAD^` assumption in
   `test_n160_a_hand_written_hash_names_no_tree_and_is_refused` with a constructed divergent tree (the probe
   in `probe_n160` already builds one by poisoning an entry; reuse that method). Probe: `python -m pytest -q`
   exit 0 **and** `verify_audit_append_only.py --force-full` exit 0, reported at the commit that carries the
   fix. Serves `§12.3`.
2. **Key reuse on the commit and see untracked files** (N-162). Add HEAD's oid to the reuse predicate and
   include untracked source paths in the dirty set. Probe: the replacement for `probe_n162` must measure
   (a) a docs-only commit is not reused from its parent and (b) an untracked failing test forces the full
   run and a non-zero exit; both fail closed today. Serves `§12.3` / `§80.3`.
3. **Repair `probe_n160`** (N-164). Decode the parent sha, and demonstrate the refusal is the tree
   comparison: with the decode removed, the probe must fail. Serves `§9.1`.
4. **Ratify this round's ledger** — five rows from §81 (two closures, three registrations) and their three
   probes. Probe: `scripts/verify_audit_findings.py` exit 0 over 16 ids / 20 rows, and every row's probe
   executable on its own.
5. **Source A1** (§81.8 Ruling 1). Four holiday circulars as Bronze artifacts with manifest rows and a
   per-year calendar provenance table; the calendar fingerprint stops standing in for provenance. Probe:
   per-year checks in `probe_pre2022_preconditions.py` exit 0 with zero unexplained sessions. Serves
   Phase 3B-2.
6. **Label warm-up and guard gating** (§81.8 Ruling 1). `WARMUP_NOT_GATABLE` on captured pre-2022 sessions,
   and a gating-mode probe that fails closed if a gated metric consumes one. Serves `§10.8`.
7. **Make pin relaxation a computed gate** (§81.9 Ruling 2). A criteria test refusing a pre-2022 pin unless
   the readiness probe exits 0 at the same commit, and a denominator check against the computed gating `T`.
   Serves Phase 2D / Phase 3B-2.

Items 1-3 are ordered by what they unblock: nothing measured after them can be trusted while the gate can
report a red commit green. Items 5-7 are the pre-2022 plan and do not start before 1-3 are green.

### 81.12 What would falsify this verdict

- If `python -m pytest -q` at `80ff581` exits 0 on a machine without this checkout's line-ending or cache
  state, N-163 is environmental and the commit is not red. The transcript is one command and its tail.
- If the plain gate at `80ff581` does **not** print `reused green at 742324c`, then this checkout's cache is
  not the one the audit measured and N-162's first attack is unproven.
- If an untracked source file appears in `dirty_source_paths()`, the second attack is wrong. The probe
  writes one such file and asserts its absence from the set; a passing probe is the defect, not the fix.
- If `probe_n160` fails when its final assertion is deleted, it is not vacuous and N-164 collapses. The
  measured call log shows the parent refusal carries a bytes `gate_sha`.
- If a cache row can be reused across two commits whose pytest outcomes differ, N-162 stands even if the
  docs-only case is closed another way; that is the property item 2 must measure.
- If `min_binding_evaluation_start_date` already permits pre-2022 gating through another key, Ruling 2 is
  redundant and §81.9 should be superseded rather than followed.

---

## §82 — Audit of `c8f56d4` (tag `feat-s81-c8f56d4`): the commit becomes the key

`df382ff` carries the three repairs §81 ordered and `c8f56d4` records the round and a green row. The
two commits have different git trees (`6f9a2c55…` versus `4515b732…`) because a committed doc and a
committed cache row are tree objects, but the same **source** tree: `7976b39b…` from both. The newest
cache row names `df382ff`, not the commit under audit — and, for the first time in this series, that
difference is the finding rather than the defect.

### 82.1 Baseline re-measured at `c8f56d4`

| Instrument | Result at `c8f56d4` |
|---|---|
| `verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| pytest | **536 passed** in 125.38 s; 0 skipped, 0 xfailed (W0.5-3 PASS) |
| `scripts/verify_*.py` discovered / executed | 9 / 9, every exit 0 (W0.5-2 PASS) |
| W0.5-1 / 1b / 1c | PASS — append-only; 2 audit volumes; INDEX reproduces at 81 section rows |
| W0.5-4 / W0.5-5 | PASS — all tags; 46 current / 22 superseded manifest rows |
| Probes in scope | `N-160`, `N-161`, `N-162`, `N-163`, `N-164` — every one `PASS`, exit 0 |
| Findings ledger | 20 rows / 16 ids |
| Criteria / config | 1.1.9; `configs/` and `data/reference/manifest.jsonl` untouched by the commit (empty diff) |
| Trees | `c8f56d4` and `df382ff` → source tree `7976b39b…`; newest row records `7976b39b…` at `df382ff`, 536 |
| Plain gate at this SHA | plan **`full`** — *"the record for this source tree was written at df382ff, not at the commit being verified (c8f56d43…)"* |

The last row is the audit's own teeth: the commit that records a green tree is not certified by that
tree, and the gate says so in a sentence that names the other commit.

### 82.2 N-162 — `CLOSED`

The key is now the commit. `select_gate_plan` takes `head_commit` as a **keyword-only parameter with no
default**, resolves it to a full oid through `commit_oid`, and compares that against the oid each row's
`gate_sha` resolves to. A row for the same tree at another commit is skipped with
*"the record for this source tree was written at …, not at the commit being verified (…)"*, and a
caller that cannot name a commit cannot reuse. Both halves were attacked in a scratch clone of this
repository, not on the tree under audit:

**A. A disjoint child of the audited commit.** A real commit object built with `git commit-tree
HEAD^{tree}` — same source tree `7976b39b…`, parent `c8f56d4` — was checked out clean. The plain gate
printed the reason above and ran the heavy gates (`536 passed`, 128 s), then
*"Source tree 7976b39b… is already recorded; not appending a duplicate row"*, and `git status` on the
cache showed **no change**. Exit 0, no reuse, no append: the case that made `80ff581` green-at-red is
gone.

**B. An untracked failing test.** `tests/unit/test_s82_untracked.py` (`assert False`) appears in
`dirty_source_paths()` as `['tests/unit/test_s82_untracked.py']` — `dirty_source_paths()` now runs
`git status --untracked-files=all` — and the plane gate selects `full` with *"1 source path(s) differ
from HEAD"*, exits **1**, and writes no row. The exit came through W0.5-2 rather than through pytest:
two ledger probes fail on a dirty tree (§82.6, N-166), which is a separate defect, but the reuse
decision it was measuring is now correct.

The positive direction was measured too: the identical row naming `HEAD` returns `reuse`, so the fix
refuses the *other commit* rather than the tree. The accepted cost is real and now permanent: a
same-tree commit neither reuses a row nor gets one, so every docs-only commit runs the heavy gates, and
the third legal post-commit outcome is *"full run, no row"*. The skill's post-commit paragraph claimed
only two outcomes; §82.7 corrects it.

Residual, not closed here: a file git **ignores** is still invisible to the dirty set while pytest
collects it — §82.5, N-165.

### 82.3 N-163 — `CLOSED`

The §80 test no longer reads its own parentage. It selects a divergent commit by the tree it projects
(`_commit_with_other_tree` walks ancestors until `source_tree_hash_at_commit(sha) != head_hash`), and a
second fixture builds a real same-tree commit with `git commit-tree`. That is not a rename of the
assumption, so it was mutated back:

| Tree under test | Test body | Result |
|---|---|---|
| Committed `c8f56d4` | `_commit_with_other_tree` | 1 passed |
| Same-tree child of `c8f56d4` (clean checkout) | `_commit_with_other_tree` | 1 passed |
| Same-tree child of `c8f56d4` | `other = git rev-parse HEAD^` (mutation) | **1 failed** — `assert (None is not None)` at line 127 |
| Same-tree child of `c8f56d4` | restored | 1 passed |

The mutant reproduces §81.5's exact failure at the exact commit shape that caused it, and the committed
test passes there. The suite is now green at a docs-only child (measured in §82.2 A: 536 passed), which
is the property the round named.

### 82.4 N-164 — `CLOSED`

The parent sha is decoded (`parent = git("rev-parse", f"{head}^").decode().strip()`), and the assertions
now test refusal *reasons*: a real divergent commit is refused with *"is not the tree at gate_sha"*, while
the undecoded bytes are refused separately as *"is not a commit"* — with `assert "is not the tree at
gate_sha" not in str(undecoded)`. Removing the decode is the falsifier, and it was measured:

| Instrument | With `.decode()` | Without `.decode()` |
|---|---|---|
| `probe_audit_findings.py N-160` | PASS, exit 0 | **FAIL**, exit 1 |
| `probe_audit_findings.py N-164` | PASS, exit 0 | **FAIL** — *"probe_n160 does not decode the parent sha"*, exit 1 |
| restored | PASS, exit 0 | — |

The ledger's N-160 evidence can now fail. One diagnostic nit, recorded not registered: the mutant's
N-160 failure prints `FAIL N-160: ` with an empty message, because the assertion's message is the
`None` it compares. Correctness is intact; a human reading that line gets no reason.

### 82.5 N-165 (`MEDIUM`, new) — an ignored file is collected and never seen

`dirty_source_paths()` reads `git status`, which by definition never reports an ignored path, and the
cheapest ignore rule needs no tracked edit: `.git/info/exclude` is local and untracked. Measured in the
scratch clone, with a row forged to name HEAD (the standing instrument of §14.3, never written to the
repository's cache):

```
$ echo 'tests/unit/test_s82_ignored.py' >> .git/info/exclude
$ printf 'def test_s82_ignored():\n    assert False\n' > tests/unit/test_s82_ignored.py
$ git status --porcelain
 M data/reference/source_tree_green.json          # the forged row only; the test file is invisible
$ python scripts/verify_audit_append_only.py
[INFO] Source-tree hash 7976b39b… — this commit's own tree was green
[INFO] reused green at afc1c2ae… (536 passed) — heavy gates skipped for an identical source tree.
OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)   exit 0
$ python -m pytest -q tests/unit/test_s82_ignored.py
1 failed   exit 1
```

This is N-162's failure mode with the guard in a different place: the commit key and the untracked set
are both correct, and a collected red test is still certified green. Reachability is narrower and worth
stating exactly — a pattern added to the repository's `.gitignore` is a tracked change, so it dirties the
tree and forces a full run; only a **local** exclude (`info/exclude`, `core.excludesFile`) reaches this,
and CI clones carry none. The defect is therefore a false green on the machine where a developer is
hiding a failing test, not a false green in CI.

Fix direction: treat ignored source paths as dirty — `git status --porcelain --ignored=matching`, keep
those for which `is_source_tree_path` is true. The cost is that a local `data/` scratch file forces a
full run, which is the fail-closed direction this gate has chosen everywhere else.

### 82.6 N-166 (`LOW`, new) — an untracked file makes two ledger consumers red for the wrong reason

Including untracked paths in the dirty set (§82.2 B) did not update the two consumers that walk that
set. With one untracked failing test present at `c8f56d4`, in a clone:

```
[FAIL] N-160 (HIGH, CLOSED): exit 1 (expected 0), stdout regex '^PASS N-160$' did not match
[FAIL] N-163 (MEDIUM, OPEN): exit 1 (expected 0), stdout regex '^PASS N-163$' did not match
OVERALL VERDICT: 2 FINDING PROBE(S) FAILED   exit 1
```

Two distinct mechanisms, both measured directly:

- `probe_n160` requires an empty dirty set and prints the list: `FAIL N-160: ['tests/unit/test_s82_untracked.py']`.
  The tree being dirty says nothing about whether the cache refuses a foreign-tree row.
- `test_n160_source_tree_hash_is_the_object_id_git_stores` iterates the dirty set and asks
  `git cat-file blob HEAD:<path>` for each entry, which raises for a path HEAD does not contain; `probe_n163`
  runs that whole file, so it inherits the crash.

The direction is right — a dirty tree must not be certified — but the ledger now reports a closed finding
as broken when it is intact, and a real regression in either probe would hide inside that noise. Fix:
skip the blob comparison for paths absent from HEAD (they are dirty without needing a blob), and let
`probe_n160` assert on the row rather than on the tree's cleanliness.

### 82.7 Phase verdicts and residuals

| Phase / claim | Verdict at `c8f56d4` | Residuals named |
|---|---|---|
| `§12.3` repository gate machinery | **GO** — 536 passed, 9/9 verifiers, `--force-full` exit 0, reproduced twice | N-165 (local ignored path); N-166 (probe diagnostics) |
| N-162 | **CLOSED** — disjoint child refused end to end; untracked test forces `full`, exit 1, no row | N-165 is the same class, unguarded |
| N-163 | **CLOSED** — mutant fails at a same-tree child, committed test passes there | — |
| N-164 | **CLOSED** — decode removed ⇒ both probes fail | empty failure message (nit) |
| ``§80.13`` items 3-5 | **PREPARED, NOT EXECUTED** — unchanged since §81.7 | A1, A2, A4 open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, no config or manifest row in the diff, no trial or validation artifact | N-152 `ACCEPTED`, N-150 `OPEN` |

This round amends the audit procedure, which is the auditor's own file: `.agents/skills/audit-round/SKILL.md`
stated that reuse depends on "the tree of the record's `gate_sha`" — false since `df382ff` — and named only
two legal post-commit outcomes. It now names the commit key, the third outcome (full run, no row, reason
naming the other commit), and the ignored-path caveat, each citing §81.4 / §82.2 / §82.5. Leaving the
stale sentence would have had a future round re-measure a closed finding from a wrong premise.

### 82.8 Work order

1. **See ignored source paths** (N-165). Add ignored-but-collected source paths to the dirty set. Probe:
   `probe_audit_findings.py N-165` asserts the defect today and must fail once fixed — then it is replaced
   by the closure probe asserting that the forged row is refused. Serves `§12.3`.
2. **Make the ledger state-independent** (N-166). Skip paths absent from HEAD in the §80 tree test; stop
   requiring an empty dirty set in `probe_n160`. Probe: `probe_audit_findings.py N-166` must fail, and
   `verify_audit_findings.py` must exit 0 with one untracked file present. Serves `§9.1`.
3. **Give the N-160 mutant a reason** (nit, same commit as 2). Assert `problem is not None` separately so
   the failure prints the measured value. Serves `§9.1`.
4. **Source A1** (§81.8 Ruling 1) — four holiday circulars as Bronze artifacts with per-year provenance;
   the calendar fingerprint stops standing in for it. Serves Phase 3B-2.
5. **Label warm-up and guard gating** (§81.8 Ruling 1) — `WARMUP_NOT_GATABLE` plus a gating-mode probe.
   Serves `§10.8`.
6. **Make pin relaxation a computed gate** (§81.9 Ruling 2) — pre-2022 pin refused unless the readiness
   probe exits 0 at the same commit; denominators recomputed from gating `T`. Serves Phase 2D / 3B-2.

Items 1-3 are the gate's own integrity and come before any research work; 4-6 are the pre-2022 plan and
are unchanged from §81.

### 82.9 What would falsify this verdict

- If a row recorded at another commit with the same source tree is reused at `HEAD`, N-162 is not closed.
  The clone's disjoint child is that row.
- If an untracked source file leaves `dirty_source_paths()` empty, or the gate reuses green over it, half B
  is not closed. Both were measured on a clean checkout with one file added.
- If the mutated §80 test (`git rev-parse HEAD^`) passes at a same-tree commit, N-163 is not closed.
- If `probe_n160` still passes with `.decode()` removed, N-164 is not closed.
- If a repository-tracked ignore rule (`.gitignore`) can hide a collected test without dirtying the tree,
  N-165 is broader than stated. Its measurement is a local `info/exclude`.
- If CI carries a local exclude file, or `core.excludesFile` is set in the CI image, the claim that CI is
  immune to N-165 is wrong.

---

## §83 — Audit of `1a20255` (tag `feat-s82-1a20255`): the file is guarded, the directory is not

`1a20255` is the work log and a cache row on top of `f6dc7da`; both commits project source tree
`06732f11…`, so the repair is the parent's and the audited commit is the one that records it. The
plain gate at this SHA selects `full` with *"the record for this source tree was written at f6dc7da,
not at the commit being verified (1a2025530…)"* — the §82 key, still working.

### 83.1 Baseline re-measured at `1a20255`

| Instrument | Result at `1a20255` |
|---|---|
| `verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| pytest | **536 passed** in 129.19 s; 0 skipped, 0 xfailed (W0.5-3 PASS) |
| `scripts/verify_*.py` discovered / executed | 9 / 9, every exit 0 (W0.5-2 PASS) |
| W0.5-1 / 1b / 1c | PASS — append-only; 2 volumes; INDEX reproduces at 82 section rows |
| W0.5-4 / W0.5-5 | PASS — all tags; 46 current / 22 superseded manifest rows |
| Probes at the audited SHA | 18 / 18 `PASS` (N-167 registered in this section takes the count to 19) |
| Findings ledger | 25 rows / 18 ids |
| Criteria / config | 1.1.9; the commit's diff is `CURRENT_STAGE_OF_WORK.md` and the cache only |
| Source tree | `06732f11…` at both `f6dc7da` and `1a20255` |

### 83.2 N-166 — `CLOSED`

One untracked source file no longer changes either consumer's verdict. In a clean clone with
`tests/unit/test_s83_untracked.py` (`assert False`) present:

| Instrument | With the untracked file | After removal |
|---|---|---|
| `dirty_source_paths()` | `['tests/unit/test_s83_untracked.py']` | `[]` |
| `verify_audit_findings.py` | **exit 0** — `ALL 18 FINDING PROBE(S) PASSED` | — |
| §80 tree test | **1 passed** | — |
| `probe_audit_findings.py N-160` | **exit 0**, stdout exactly `PASS N-160` | — |

The `cat-file` request that raised for a path HEAD lacks is gone, and `probe_n160` now asserts an
implication (every source path git reports is in the dirty set) instead of equality against a set
collected with different flags. It also compares no bytes for a dirty path, which is what made the
right verdict depend on the working copy's contents.

One assertion was removed and it is named rather than implied: the tree test used to require that a
path in the dirty set differs **byte-for-byte** from its blob. On an LF checkout a mode-only change
carries the blob's exact bytes, so that was a Windows fact dressed as an invariant; it is replaced by
an unconditional blob-oid identity check on a clean text path, which is the stronger claim the digest
actually needs. No gate decision reads working-copy bytes — `main()` decides on the dirty path *set* —
so nothing that was guarded became unguarded.

The `core.autocrlf=false` checkout the work log cites was reproduced from a fresh clone of this
commit: no committed text file contains CRLF (the only text file that does, `.pytest_cache/README.md`,
is written by the pytest run in that clone), the §80 test file is **7 passed**, and `probe N-160`
prints `PASS`. The measurements the rework replaced were the developer's machine; the ones it kept hold
on a Linux-shaped checkout.

The §82.4 diagnostic nit is also closed by measurement. Removing `.decode()` from the parent line now
fails as `FAIL N-160: HEAD's parent b'f6dc7da…' is not a commit in this repository`, `probe_n164` exits
1 naming `parent = git("rev-parse", f"{head}^").strip()`, and both print `PASS` when restored — so
N-164's closure still fails the moment it should, with a reason a human can read.

### 83.3 N-165 — `PARTIAL`; the ledger row stays `OPEN`

The fix guards the shape §82.5 measured and not the shape beside it. Both were attacked in the clone,
end to end, with the forged row naming HEAD as the instrument:

**File form — closed.** `tests/unit/test_s83_ignored.py` listed in `.git/info/exclude`: `git status`
does not report it, `dirty_source_paths()` returns `['tests/unit/test_s83_ignored.py']`, the gate
selects `full` with *"1 source path(s) differ from HEAD"*, exits **1**, and the cache row count is
unchanged (10 → 10): nothing is recorded. Removing `--ignored=matching` makes `probe_n165` exit 1 with
*"an ignored-but-collected test file is still invisible to the dirty set"*; restoring it returns
`PASS`. The closure instrument has teeth.

**Directory form — open.** A whole ignored directory under `tests/` holding one failing test:

```
$ echo 'tests/unit/n165_dir/' >> .git/info/exclude
$ git status --porcelain
                                        # empty: git reports nothing and the file is not enumerated
$ python -c "...print(dirty_source_paths())"
[]                                      # the gate's only view of the working copy
$ python -m pytest -q tests/unit/n165_dir/test_d.py
1 failed                                # the suite it would certify
$ python scripts/verify_audit_append_only.py    # with a row forged to name HEAD
[INFO] Source-tree hash 06732f11… — this commit's own tree was green
[INFO] reused green at 1a2025530… (536 passed)
OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)   exit 0
```

That is N-165's metric — *a recorded green run is not reused when the suite it would certify is red
because of a collected file git does not report* — still violated, so N-165 cannot be closed. The
mechanism is visible in the landed code: `git status --ignored=matching` reports an ignored directory
once, as `dir/`, and enumerates nothing inside it, and `dirty_source_paths()` drops every entry that
ends in `/` before the `.py`-and-root filters run.

**Rootdir `conftest.py` — open, narrower.** An ignored `conftest.py` at the repository root is not dirty
either (`[]`), because ignored files are kept only under `src/`, `scripts/` and `tests/`, and pytest
imports the rootdir conftest regardless of `testpaths = ["tests"]`. In the clone with one that raises in
`pytest_configure`: pytest exits 3 and the gate selects reuse, but exits **1** anyway — because W0.5-2's
probes invoke pytest and the broken conftest fails them. That catch is an accident of the probes' own
subprocesses, not a decision the gate makes: an ignored conftest that changes outcomes without erroring
a probe's pytest run would certify green.

The ledger has no `PARTIAL` status (`OPEN → {CLOSED, ACCEPTED}`), and accepting a false green on the
maintainer's behalf is not the auditor's call, so N-165 stays `OPEN` with this measurement as its
history and the remaining mechanism registered as N-167. §14.4's pattern is worth naming: a guard was
added beside the unguarded shape — `.py` files are covered, directories are not — and `probe_n165`
passes because it hides a *file*, so the acceptance instrument is narrower than the metric it cites.

### 83.4 N-167 (`MEDIUM`, new) — an ignored directory hides a whole collected test

Metric: an ignored path that pytest collects is dirty state, whatever shape git reports it in.
Threshold: an ignored directory under a collected root, and an ignored rootdir `conftest.py`, make the
dirty set non-empty and the gate refuse to reuse or record. Measured today: `dirty_source_paths()` is
`[]` in both cases (above), and a forged row naming HEAD reuses green while `pytest` fails.

Fix direction: when an ignored entry ends in `/` and sits under `src/`, `scripts/` or `tests/`,
enumerate it (`git ls-files --others --ignored --exclude-standard -- <dir>`) and keep the `.py` files
found there; add a rootdir `conftest.py` (and pytest configuration files) to the always-dirty set. The
cost is a full run for a directory of ignored scratch `.py` files under those roots — the fail-closed
direction the gate has chosen since §81.

`probe_n167` asserts the defect through the same instruments and passes while it stands; it must fail,
then be replaced by a closure probe, once both shapes are covered. It is written against the working
copy's own dirty set rather than an empty one after the first run of it failed on its own uncommitted
edit — the N-166 lesson applies to the probes as well as to the tests.

### 83.5 Phase verdicts and residuals

| Phase / claim | Verdict at `1a20255` | Residuals named |
|---|---|---|
| `§12.3` repository gate machinery | **GO** — 536 passed, 9/9 verifiers, `--force-full` exit 0 | N-167 (ignored directory, ignored conftest), N-165 carried `OPEN` |
| N-166 | **CLOSED** — both consumers hold with an untracked file present | — |
| N-165 | **PARTIAL** — file form closed and mutation-tested; directory and conftest forms open | N-167 |
| N-162 / N-163 / N-164 | remain **CLOSED** — key unchanged; decode mutant still fails; tree test still mutation-sensitive | N-164 nit closed (§83.2) |
| `§80.13` items 3-5 | **PREPARED, NOT EXECUTED** — unchanged since §81.7 | A1, A2, A4 open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, diff is the work log and the cache, no trial or validation artifact | N-152 `ACCEPTED`, N-150 `OPEN` |

The implementer's work log states N-165/N-166 stay `OPEN` because closure rows belong to the auditor,
and cites no verdict it does not have (§11.3). Its residual list — an ignored non-`.py` artifact — is
true and incomplete: the directory and rootdir-conftest shapes it did not measure are N-167. That is a
new finding with its own measurement, not an edit to the log.

### 83.6 Work order

1. **Cover the shapes git does not enumerate** (N-167). Enumerate ignored directories under collected
   roots and keep the `.py` files inside; treat an ignored rootdir `conftest.py` as dirty. Probe:
   `probe_audit_findings.py N-167` must fail at the fixing commit, and the full suite must go red over an
   ignored directory the way it already goes red over an ignored file. Serves `§12.3`.
2. **Carry items 4-6 of §82.8 unchanged** — A1 sourcing with per-year provenance, `WARMUP_NOT_GATABLE`
   plus a gating-mode probe, and pre-2022 pin relaxation as a computed gate. Serves Phase 3B-2 / `§10.8`.

Nothing else in §82.8 survives as work: items 1-3 are implemented, and item 1 is now measured as partial
rather than done.

### 83.7 What would falsify this verdict

- If an ignored directory under `tests/` appears in `dirty_source_paths()` at a later commit, the
  PARTIAL verdict is stale in the direction of being too harsh, and N-167 is fixed.
- If the gate ever exits non-zero over the directory-only configuration measured in §83.3, the false
  green it records is stale.
- If `verify_audit_findings.py` goes red with one untracked source file present, N-166 is not closed.
- If removing `.decode()` leaves `probe_n160` passing, N-164 has regressed through the §83.2 rework.
- If any gate decision turns out to read working-copy bytes, removing the byte-inequality assertion was a
  widening rather than a correction; today `main()` decides on the dirty path set.
---

## §84 — Audit of `f361ba8` (tag `feat-s83-f361ba8`): both named shapes refuse now; a config file does not

`f361ba8` is the cache row for `626ebba`, and the repair is `626ebba`'s. It implements §83.6 item 1 and
nothing else: `dirty_source_paths()` enumerates the `.py` files inside an ignored directory under a
collected root, and keeps an ignored rootdir `conftest.py`. The plain gate at this SHA selects `full`
with *"the record for this source tree was written at 626ebba, not at the commit being verified
(f361ba84…)"* — the §82 key, still working. The work log cites §83 and `b89dbe7` and labels itself
**not audited**, so §11.3 is satisfied by the log it wrote.

### 84.1 Baseline re-measured at `f361ba8`

| Instrument | Result at `f361ba8` |
|---|---|
| `verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| pytest | **536 passed** in 140.17 s; 0 skipped, 0 xfailed (W0.5-3 PASS) |
| `scripts/verify_*.py` discovered / executed | 9 / 9, every exit 0 (W0.5-2 PASS) |
| W0.5-1 / 1b / 1c | PASS — append-only; 2 volumes (1186 committed lines); INDEX reproduces at 83 section rows |
| W0.5-4 / W0.5-5 | PASS — 84 commit-bearing tags; 46 current / 22 superseded manifest rows |
| Probes at the audited SHA | 19 / 19 `PASS`; N-168 registered in this section takes the ledger to 20 ids |
| Findings ledger | 26 rows / 19 ids |
| Green cache | 12 rows; newest `626ebba` / tree `98d7c3a7…` / 536 |
| Trials / criteria / holdout | **N = 9, N_eval = 5**; criteria **1.1.9** (`5591656411a6c1ef…`); no `HOLDOUT_UNLOCK` sentinel |
| Source tree | `98d7c3a7…` at both `626ebba` and `f361ba8`; `dirty_source_paths()` is `[]` |

### 84.2 N-167 — `CLOSED`

Both shapes were attacked end to end in a clone at `f361ba8`, with a row forged to name HEAD as the
instrument; the forged row is first shown to be a real hit, otherwise the refusal proves nothing.

| Configuration | `git status` | `dirty_source_paths()` | Gate with the forged row |
|---|---|---|---|
| Clean tree (control) | clean | `[]` | `reused green at f361ba84… (536 passed)`, **exit 0**, no row appended |
| Ignored `tests/unit/n167_hidden/` holding a failing test | clean (not even reported) | `['tests/unit/n167_hidden/test_hidden.py']` | `1 source path(s) differ from HEAD: tests/unit/n167_hidden/test_hidden.py`, **exit 1**, cache 13 → 13 |
| Ignored rootdir `conftest.py` that raises in `pytest_runtest_setup` | clean | `['conftest.py']` | `1 source path(s) differ from HEAD: conftest.py`, **exit 1**, cache 13 → 13 |

`should_record_green("full", True, 536, [])` is `True` and the same call over either dirty set is
`False`, so the refusal is the set and not a recording rule that never fires. The enumeration is real
rather than declared: `git status --ignored=matching` still reports only `!! tests/unit/n167_hidden/`,
while `git ls-files --others --ignored --exclude-standard` lists `test_hidden.py` inside it. Both
mutations fail closed — deleting the directory branch makes `probe N-167` exit 1 with *"an ignored
directory under tests/ is still invisible to the dirty set"*, and deleting the `conftest.py` branch
makes it exit 1 with *"an ignored rootdir conftest.py is still invisible to the dirty set"*. The
implementer's claim that the flipped probe failed on the pre-fix tree reproduces: the new probe against
`74e74d3`'s verifier exits 1 with that same phrase (the dirty list it prints is that clone's, which
carries 25 modified archive files, so the list differs from the work log's while the phrase matches).

Two properties are worth recording because they were not asked for. The probe aborts when
`tests/unit/n167_hidden` already exists (`FAIL N-167: … already exists`) instead of clearing a path it
did not create — it failed that way against my own planted directory, which is the right direction.
And the fix does not over-collect: on a clean tree after a full pytest run, with `__pycache__`
directories reported as ignored, `dirty_source_paths()` is still `[]`.

### 84.3 N-165 — `CLOSED`

N-165's metric is *a recorded green run is not reused when the suite it would certify is red because of
a collected file git does not report*. Every shape a `.py` collected file can take now reaches the set:
an ignored file (§83.3, `probe N-165` still `PASS`), an ignored directory, an ignored conftest inside
one (enumerated by the same `ls-files` call), and an ignored rootdir `conftest.py`. The pre-fix probe
that could only hide a file is no longer the widest instrument: the two shapes that beat it in §83.4
are measured red above.

The row is closed with the residual named rather than implied: what still hides code from this set is
not a source path at all but a rootdir pytest *configuration* file, registered below as N-168. That is a
different input, and §14.5's contract for this round was §83.6 item 1 — the directory and the
`conftest.py`. Both are met, so the verdict changes even though a better condition can be imagined.

### 84.4 N-168 (`MEDIUM`, new) — an ignored rootdir pytest config is not dirty state

The config file is outside every branch this round added: `ignored_python_files()` keeps `.py` files,
and the new rootdir branch matches exactly `conftest.py`. Measured in the same clone, with a row forged
to name HEAD:

```
$ printf '[pytest]\naddopts = -q --ignore=tests/unit/test_phase3b2_audit_s80_items.py\n' > pytest.ini
$ printf 'pytest.ini\n' >> .git/info/exclude
$ git status --porcelain
                                        # empty: git calls the tree clean
$ python -c "...print(dirty_source_paths())"
[]                                      # and so does the gate's only view of the working copy
$ python -m pytest
529 passed in 132.84s                   # seven tests, including a §80 item, never ran
$ python scripts/verify_audit_append_only.py    # forged row naming HEAD
[INFO] reused green at f361ba84… (536 passed) — heavy gates skipped for an identical source tree.
OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)   exit 0
```

The config is executed, not inert: under `addopts = -q -k "not test_n160_source_tree_hash"` pytest
reports `6/7 tests collected (1 deselected)` for the §80 test file. So a local exclude rule can still
make a green row certify a suite that did not run — through a configuration file rather than a source
file. The threshold is that an ignored rootdir `pytest.ini`, `tox.ini`, `setup.cfg` or `pyproject.toml`
is dirty state. `probe_n168` asserts the defect through the dirty set, the recording decision, the
forged row and pytest's own collection, and passes while it stands; applying the closure form in the
verifier (keeping those four names when they are reported `!!`) makes it exit 1 with *"the dirty set
already covers a rootdir pytest config"*.

This is not a missed contract. §83.4's fix direction named configuration files, but the ordered item in
§83.6 named the directory and `conftest.py` only, and that is what was delivered and verified.

### 84.5 Phase verdicts and residuals

| Phase / claim | Verdict at `f361ba8` | Residuals named |
|---|---|---|
| `§12.3` repository gate machinery | **GO** — 536 passed, 9/9 verifiers, `--force-full` exit 0; reuse refused over both measured shapes | N-168 (ignored rootdir pytest config) |
| N-167 | **CLOSED** — both shapes in the dirty set, gate exit 1 and no row, both branches mutation-tested | — |
| N-165 | **CLOSED** — file, directory and conftest shapes all refuse; metric holds | N-168 for the config channel |
| N-162 / N-163 / N-164 / N-166 | remain **CLOSED** — key, tree identity and probe stability unchanged by this commit | — |
| `§80.13` items 3-5 | **PREPARED, NOT EXECUTED** — unchanged since §81.7 | A1, A2, A4 open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, N = 9, N_eval = 5, no trial row, 2024 fold frozen, holdout sealed | N-152 `ACCEPTED`, N-150 `OPEN` |

### 84.6 Work order

1. **Treat an ignored rootdir pytest configuration file as dirty** (N-168). `pytest.ini`, `tox.ini`,
   `setup.cfg` and `pyproject.toml` reported `!!` at the repository root are state, so they refuse reuse
   and recording the way `conftest.py` now does. Probe: `probe_audit_findings.py N-168` must be flipped
   to assert the fix and must fail at the fixing commit's parent; the full suite must go red over an
   ignored config that deselects a tracked test, not only report a different count. Serves `§12.3`.
2. **Carry items 4-6 of §82.8 unchanged** — A1 sourcing with per-year provenance, `WARMUP_NOT_GATABLE`
   plus a gating-mode probe, and pre-2022 pin relaxation as a computed gate. Serves Phase 3B-2 / `§10.8`.

No other item of §83.6 survives: item 1 is delivered and measured, and its closure probe is load-bearing
in both directions.

### 84.7 What would falsify this verdict

- If an ignored directory under `tests/`, or an ignored rootdir `conftest.py`, stops appearing in
  `dirty_source_paths()`, N-167 is not closed and this section is wrong.
- If either mutation of `probe_n167` still prints `PASS`, the closure probe is not the instrument that
  decided it.
- If `dirty_source_paths()` is non-empty on a clean tree after a full pytest run, the enumeration
  over-collects and every checkout pays the heavy gates; today it is `[]`.
- If `probe N-165` fails at a later commit, N-165's file form regressed and its closure was premature.
- If an ignored rootdir pytest config ever makes the gate refuse, N-168 is stale in the direction of
  being too harsh; today it reuses green over one.
### 84.8 A §83 closure that never reached the ledger

§83.2 declared N-166 `CLOSED`. The ledger at `f361ba8` did not contain that row: `findings.jsonl` held
26 rows and N-166's newest row was still `OPEN` with `section: 82`, so the closure lived only in prose
while `verify_audit_findings.py`, which executes every non-`ACCEPTED` row, went on treating N-166 as
open. That is the auditor's error and it is recorded rather than quietly patched: §84 appends the
closure row with `closed_in_section: 83`, the section that decided it, because the ledger is append-only
and citing §84 would move the closure to a round that did not make it. No verdict changes — the probe
has been the closure probe since `1a20255` — only the citation, and the ledger now reads 30 rows over
20 ids with N-165, N-166 and N-167 all `CLOSED`.
---

## §85 — Audit of `0b3c56d` (tag `feat-s84-0b3c56d`): the four named configs are state, the fifth name pytest reads is not

`0b3c56d` is the cache row for `120a8d0`, the one commit this round audits. `120a8d0` implements §84.6
item 1 and nothing else: `ROOTDIR_PYTEST_CONFIG_FILES` adds four names to the `!!` branch of
`dirty_source_paths()` beside the rootdir `conftest.py`, and `probe_n168` is flipped from asserting the
defect to asserting the closure. `CURRENT_STAGE_OF_WORK.md` grew a §84 entry that cites the audit section
and tag and labels itself **Not audited**, so §11.3 is satisfied by the log the implementer wrote.

Two instruments used by this round were wrong first and are recorded rather than hidden: a forged row
that witnesses two verifiers, and then eight, is not a cache hit — the gate ran the full suite both times
and the "control" proved nothing. The measurements below use a forge built from
`discovered_verification_scripts()` (9), which the gate accepts: `reused green at 0b3c56d… (536 passed)`
in 52 s. A refusal is only evidence once the thing it refuses would otherwise have been honoured.

### 85.1 Baseline re-measured at `0b3c56d`

| Instrument | Result at `0b3c56d` (clone `/tmp/s85`, clean tree) |
|---|---|
| `verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| pytest | **536 passed** in 140.70 s; 0 skipped, 0 xfailed |
| `scripts/verify_*.py` discovered / executed | 9 / 9, every exit 0 |
| W0.5-1 / 1b / 1c | append-only PASS; 2 volumes (frozen pin 1-78, 8442 lines; active 1331 committed lines, unchanged prefix); INDEX reproduces at **84** section rows |
| W0.5-4 / W0.5-5 | PASS — **86** commit-bearing tags; 46 current / 22 superseded manifest rows |
| Probes before this round's rows | 20 / 20 `PASS`; N-168 still `OPEN` in the ledger |
| Findings ledger | 30 rows / 20 ids (N-165, N-166, N-167 `CLOSED`) |
| Green cache | 14 rows; `dirty_source_paths()` is `[]` before and after a full pytest run |
| Plain plan at this SHA | `full` — *"the record for this source tree was written at 120a8d0, not at the commit being verified (0b3c56d…)"* |
| Trials / criteria / holdout | registry **9 rows** (6 `IN_SAMPLE`, 3 `VALIDATION`), no row added; criteria **1.1.9**, `configs/go_no_go_criteria.yaml` sha256 `d0a607b4…`, untouched by `120a8d0`; no `HOLDOUT_UNLOCK` sentinel |

`120a8d0` touches `scripts/verify_audit_append_only.py`, `scripts/probe_audit_findings.py` and
`CURRENT_STAGE_OF_WORK.md`; the source tree of `0b3c56d` is `b1a88925…` and nothing in `src/` or the
suite moved, which is why the baseline count is unchanged from §84.

### 85.2 N-168 — `CLOSED`

Attacked in the clone with a forged row naming HEAD and HEAD's tree, so the gate has something real to
reuse. The control is the first row and it is load-bearing: without a hit, the two refusals below would
prove only that the gate runs.

| Configuration | `git status` | `dirty_source_paths()` | Gate |
|---|---|---|---|
| Clean tree (control) | clean | `[]` | `reused green at 0b3c56d… (536 passed)`, **exit 0**, 52 s, cache 15 → 15 |
| Ignored `pytest.ini` (`addopts = -k "not …"`) | clean (hidden) | `['pytest.ini']` | *"1 source path(s) differ from HEAD: pytest.ini"*, **no** `reused green`, cache 15 → 15 |
| Ignored `tox.ini` / `setup.cfg` (decision) | clean | `['tox.ini']` / `['setup.cfg']` | plan `full`, `should_record_green("full", True, 536, dirty)` is `False` |

The `pytest.ini` gate invocation exits 1 with *1 FINDING PROBE(S) FAILED* — and that failure is
`probe_n168` refusing to clobber the planted file (`pytest.ini already exists: the probe would clobber
it`), not a red suite. The refusal being measured is the dirty set, and its own evidence is the reason
line, the absent reuse line and an unchanged cache: over a config-dirty tree the gate runs the heavy
gates and declines to record the result. That the recording rule fires is not inferred from the gate's
exit status, which my own instrument perturbed.

**Which of the four names are live here was measured, not assumed.** `pytest.ini` is executed: the §80
file collects 7, then 6 with one deselected. `tox.ini` and `setup.cfg`, planted the same way, change
nothing (7 → 7, no deselection) because the tracked `pyproject.toml` carries `[tool.pytest.ini_options]`
and outranks both — they are covered by the tuple and unreachable in this repository. `pyproject.toml`
itself is tracked, so `git status` can never report it `!!`; the implementer's log records that entry as
unexercised and this round agrees. The closure therefore rests on `pytest.ini`, the one live name, and
the tuple covers the other three defensively. No over-collection was observed: a clean tree holding the
tracked `pyproject.toml` yields `dirty_source_paths()` `[]`, before and after a full run.

The probe is the deciding instrument in both directions. Flipped, it exits 0 and prints `PASS N-168` at
`0b3c56d`. Against the pre-fix verifier at `2060a31` (with only the probe file replaced) it exits 1 with
*"an ignored rootdir pytest config is still invisible to the dirty set (['scripts/probe_audit_findings.py']),
so a local exclude rule can point pytest at a different suite under a reused green row"* — the phrase the
implementer's log claims. Removing the config clause from the fixed verifier reproduces the same phrase
in the fixed tree. The probe also stopped asserting that the recorded suite is the one pytest ran; it now
asserts the set, the recording decision and the collection change, which is the pair of facts the gate
acts on.

### 85.3 N-169 (`MEDIUM`, new) — the deprecated `.pytest.ini` is honoured and invisible

pytest 8.3.4 still reads `.pytest.ini`, and that name is in no tuple:

```
$ printf '[pytest]\naddopts = -k "not test_parse_bhavcopy_date_formats"\n' > .pytest.ini
$ printf '.pytest.ini\n' >> .git/info/exclude
$ git status --porcelain                     # empty: git calls the tree clean
$ python -m pytest --collect-only -q         # 535/536 tests collected (1 deselected)
$ python -c "...dirty_source_paths()"        # []
$ python scripts/verify_audit_append_only.py # forged row naming HEAD
[INFO] reused green at 0b3c56de4d68a9bb4209ab65d65b3eab111be049 (536 passed, …)
OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)   exit 0
```

Same channel as N-168, one name short: reuse certifies a 536-test record for a tree whose suite pytest
collected 535 of. The probe that closes it must fail closed first, so `probe_n169` is registered and
prints `PASS N-169` while the defect stands; including `.pytest.ini` in the branch makes it exit 1 with
*"the dirty set already covers an ignored legacy .pytest.ini"*. `pytest.toml` and `.pytest.toml` (the
names pytest 9 reads) were measured the same way and change nothing under 8.3.4, so they are recorded as
not-a-channel under the installed pytest rather than registered as findings.

### 85.4 Phase verdicts and residuals

| Phase / claim | Verdict at `0b3c56d` | Residuals named |
|---|---|---|
| `§12.3` repository gate machinery | **GO** — 536 passed, 9/9 verifiers, `--force-full` exit 0; the four named configs refuse reuse and recording | N-169 (ignored legacy `.pytest.ini`) |
| N-168 | **CLOSED** — `pytest.ini` in the dirty set, reuse refused, no row; probe flipped, failing at `2060a31`, load-bearing under mutation | three tuple names defensive/untracked-unreachable, recorded above |
| N-165 / N-167 | **no regression** — `probe N-165` and `probe N-167` both still `PASS` | — |
| `§80.13` items 3-5 | **PREPARED, NOT EXECUTED** — unchanged since §81.7 | A1, A2, A4 open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, 9 trial rows, no new row, 2024 fold frozen, holdout sealed | N-152 `ACCEPTED`, N-150 `OPEN` |

### 85.5 Work order

1. **Treat an ignored legacy `.pytest.ini` as dirty state** (N-169). It is the name pytest 8.3.4 actually
   reads for a rootdir ini, so it belongs beside `pytest.ini` in the branch `120a8d0` added. Probe:
   `probe_audit_findings.py N-169` flipped to assert the fix and failing at the fixing commit's parent;
   the runtime check must be the dirty set, not pytest's exit status, because the deselected suite still
   exits 0 with a count the 500 floor accepts. Serves `§12.3`.
2. **Carry items 4-6 of §82.8 unchanged** — A1 sourcing with per-year provenance, `WARMUP_NOT_GATABLE`
   plus a gating-mode probe, and pre-2022 pin relaxation as a computed gate. Serves Phase 3B-2 / `§10.8`.

No other item of §84.6 survives: item 1 is delivered and measured, and its closure probe fails closed
both before the fix and under a mutation of it.

### 85.6 What would falsify this verdict

- If an ignored rootdir `pytest.ini` stops appearing in `dirty_source_paths()`, or the gate reuses green
  over one, N-168 is not closed and this section is wrong.
- If a forged row witnessing all nine discovered verifiers is not reused on a clean tree, the control was
  not a hit and every refusal measured here needs re-taking.
- If `probe N-168` passes at `2060a31`, the closure probe is not the instrument that decided the finding.
- If `probe N-169` fails at `0b3c56d`, `.pytest.ini` has stopped being honoured by the installed pytest
  and N-169 is stale in the direction of being too harsh; today it prints `PASS` and the reuse above
  reproduces end to end.
- If a later pytest upgrade starts reading `pytest.toml`, the name measured as inert here becomes a
  channel and the tuple is short by that name too.
---

## §86 — Audit of `a3be813` (tag `feat-s85-a3be813`): the legacy ini is state; the 2019 grid is one session short, and the Ruling that authorises closing it

**Date:** 17 November 2026
**Commit under review:** `a3be813` — the cache row for `88b1921` ("Treat an ignored legacy `.pytest.ini` as dirty state"), which is the only implementation commit this round touches.
**Verdicts:** N-169 `CLOSED` · N-168/N-167/N-165 no regression · A1 measured `NO` for all four years, with **§86.5 Ruling 1** authorising the 2019 grid correction and the §86.6 provenance contract for the 2018-2021 circulars · one new environment defect, **N-170**

### 86.1 Baseline re-measured at `a3be813`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers discovered / executed | 9 / 9, every exit 0 |
| pytest | **536 passed** in 146.55 s |
| W0.5-1 / 1b / 1c | append-only PASS (frozen volume 8442 lines, 1-78); 2 volumes verified; INDEX reproduces at **85** section rows |
| W0.5-4 | PASS — **88** commit-bearing tags verified |
| `probe_pre2022_preconditions.py` | **exit 1** — 8 of 8 preconditions unmet (§86.4) |
| Findings ledger before this round | 32 rows / 21 ids; N-169 `OPEN` |
| Criteria | **1.1.9**, `configs/go_no_go_criteria.yaml` sha256 `5591656411a6c1ef…`, no threshold changed by `88b1921` |
| Trials / fold / holdout | 9 rows (6 `IN_SAMPLE`, 3 `VALIDATION`), N = 9 / N_eval = 5, 2024 fold frozen, no `HOLDOUT_UNLOCK` sentinel; the commit touches no holdout path |
| `dirty_source_paths()` on this checkout | `[]` |

**One environment fact decides how the control below could be taken.** A fresh clone of `a3be813` reports **24 tracked paths modified** before anyone edits anything: `.gitattributes` marks `*.csv.zip` and `*.json.gz` as `text` with `eol=lf`, the committed blobs nevertheless store CRLF (measured: `cm12JAN2024bhav.csv.zip` blob 100,331 bytes / 393 CR, clone worktree 100,328 bytes / 0 CR), so checkout writes bytes that differ from the object git stored. On such a clone the gate prints `24 source path(s) differ from HEAD` and can never reuse a recorded tree; §85's control would have measured a full run and called it a refusal. This checkout is clean only because its working files predate the attribute. Recorded as **N-170** in §86.3 and the work order.

### 86.2 N-169 — `CLOSED`

`88b1921` prepends `".pytest.ini"` to `ROOTDIR_PYTEST_CONFIG_FILES` and flips `probe_n169` from asserting the defect to asserting the closure. Measured on the clean checkout at `a3be813` with a forged row that witnesses all nine discovered verifiers and names HEAD:

| Configuration | `dirty_source_paths()` | Gate |
|---|---|---|
| Clean checkout + forged row (control) | `[]` | `reused green at a3be8133f5d… (536 passed)`, **exit 0** — the forge is a real hit |
| Ignored `.pytest.ini` (+ forged row) | `['.pytest.ini']` | `1 source path(s) differ from HEAD: .pytest.ini`; **no** `reused green`, **no** `Recorded green`; cache rows unchanged; **exit 1** |
| Tuple edited to drop `".pytest.ini"` | — | `probe N-169` **exit 1**: *"an ignored legacy .pytest.ini is still invisible to the dirty set …, so a local exclude rule can point pytest at a different suite under a reused green row"* |
| Parent `a906738` + the flipped probe only | — | `probe N-169` **exit 1**, same sentence |

The gate's exit 1 in row 2 is `probe_n169` refusing to clobber the planted file (`FAIL N-169: .pytest.ini already exists: the probe would clobber it`); the refusal being measured is the decision, not the exit status. The decision instruments were read directly over the same tree: `should_record_green("full", True, 536, ['.pytest.ini'])` is **False**, over `[]` it is **True**, and `select_gate_plan` reports `full` with no hit. The probe itself is load-bearing in three directions — membership, refusal, and pytest executing the config (collection 7 → 6 with the tracked `test_n160_source_tree_hash_is_the_object_id_git_stores` deselected) — and is non-vacuous on cleanup: it asserts the file left the set and the dirty set equals its baseline.

**No additive path.** `dirty_source_paths()` has one producer and one consumer inside the gate (`main()` via `should_record_green` / `select_gate_plan`); the only other references in the tree are the probes themselves. There is no second config-name list and no second reuse rule to keep in step, so `88b1921` cannot leave an unguarded sibling behind — the failure mode §14.4 names is structurally unavailable here. Neighbours re-run: `N-165`, `N-167`, `N-168`, `N-169` all exit 0.

### 86.3 N-170 (LOW) — every fresh checkout is dirty, so the green cache never pays off

Measured at `a3be813`, both with `core.autocrlf=true` and with `-c core.autocrlf=false`:

```
$ git check-attr -a -- data/reference/cm12JAN2024bhav.csv.zip
… text: set … eol: lf
$ git cat-file -s HEAD:data/reference/cm12JAN2024bhav.csv.zip        # 100331, 393 CR
$ wc -c < data/reference/cm12JAN2024bhav.csv.zip                     # clone: 100328, 0 CR
$ git status --porcelain | wc -l                                     # 24
```

The attribute demands LF on checkout; the stored object holds CRLF. Every clone — on this machine, and on a Linux CI runner that honours `eol=lf` — materialises bytes the blob does not contain, so `dirty_source_paths()` is non-empty before any edit and `select_gate_plan` runs the heavy gates every time. The failure is in the safe direction (it wastes ~250 s per run and blocks reuse; it does not certify a suite that was not run), which is why it is LOW and not a gate bypass. It is recorded here and in the work order rather than in the ledger, for the §79.9 reason: a probe that asserts this defect cannot pass on a checkout where the working files still match the blobs, and the gate runs on exactly such checkouts.

The repair is a byte decision, not a policy one: either store the archives with LF and update the manifest digests and pins in one commit, or mark them `-text` (`binary`) and store the original bytes. The second is correct for archives: forcing line-ending normalisation onto a compressed container is what created the mismatch.

### 86.4 A1 re-measured — nothing in the repository can PASS it today

`python scripts/probe_pre2022_preconditions.py` at `a3be813` exits **1**, 8 of 8 unmet:

```
[NO] A1 2018: no committed holiday circular artifact names a 2018 date (13 artifact(s) on disk, issued 2021-12-10..2026-01-12)
[NO] A1 2019: … [NO] A1 2020: … [NO] A1 2021: …
[NO] A1 provenance: the calendar's provenance.sha256 is its own CAL-FPR digest af8e309a6f897a67…, not the digest of a source artifact
[NO] A2 … [NO] A4 dividends … [NO] A4 max hold …
```

The calendar's own arithmetic, measured, with the per-year holiday counts the §85 implementer note reports from circulars that are **not committed**:

| Year | Weekdays | Calendar sessions | Weekend sessions in the grid | Implied by the reported holiday set |
|---|---|---|---|---|
| 2018 | 261 | **246** | none | 261 − 16 + 1 (muhurat Wed 2018-11-07) = 246 ✓ |
| 2019 | 261 | **244** | 2019-10-27 (Sunday muhurat) | 261 − 17 + 1 = **245** ✗ one short |
| 2020 | 262 | **252** | 2020-02-01, 2020-11-14 | 262 − 12 + 2 = 252 ✓ |
| 2021 | 261 | **248** | none | 261 − 14 + 1 (muhurat Thu 2021-11-04) = 248 ✓ |

The missing date is **2019-10-29, a Tuesday**: absent from the grid, absent from every committed artifact, and surrounded in the calendar by 2019-10-28 (absent, Balipratipada) and 2019-10-27 (present, Sunday muhurat). Totals: **2,935** sessions; **930** in `2018-04-01..2021-12-31`; **1,196** in `2022-01-03..2026-10-31`, which matches `expected_authoritative_calendar_sessions`.

Independent corroboration that 2019-10-29 traded, from contemporaneous press rather than from NSE: Sensex closed **39,831.84** (+581.64, +1.48%), Nifty 11,786.85, on Tuesday 2019-10-29 (NewsNation, ETV Bharat, both dated 2019-10-29), with markets shut 2019-10-28 for Diwali Balipratipada and the muhurat session on Sunday 2019-10-27 at Sensex 39,250. That is enough to justify a Ruling that the grid is wrong; it is **not** enough to re-seal the pin, because §6.3 requires the exchange artifact and press coverage is not one.

### 86.5 Ruling 1 — the 2019 grid is corrected, and the correction is conditional on its own provenance

**Evidence:** measured at `a3be813` (§86.4): 2019 holds 244 sessions; the weekday arithmetic with the reported holiday set implies 245; the absent date is a Tuesday; the calendar's provenance is self-referential; and no committed artifact can contradict or confirm it because the circular corpus begins at 2022.

**The single definition it changes:** the 2019 annual session grid gains one `FULL` session, `2019-10-29`, `09:15:00..15:30:00`, `"Regular Trading Session"`, taking 2019 from 244 to 245. This is a content correction to a pinned identity, not a threshold: no criterion, no fold, no window and no trial count moves.

**What it authorises, exactly:**

- `configs/trading_calendar_nse.json`: `session_records` and `sessions` gain `2019-10-29`; `annual_session_counts["2019"]` 244 → **245**; `fingerprint` recomputed (a new `CAL-FPR-V1-…`); `provenance.sha256` replaced by a digest of a named source (§86.6), never left equal to the new CAL-FPR hex; `provenance.retrieved_at` updated to the retrieval of the artifacts it names.
- `configs/go_no_go_criteria.yaml`: `expected_calendar_fingerprint` re-pinned to the new CAL-FPR; `expected_total_calendar_sessions` 2935 → **2936**; `expected_manifest_fingerprint` recomputed after the new manifest rows; `criteria.version` **1.1.9 → 1.1.10** with a comment that states, in the words §77.12 used, that no numeric threshold changed; `pre_binding_calendar_provenance_note` 930 → **931**.
- `src/signal_core/contracts/criteria.py` default `expected_total_calendar_sessions` 2935 → 2936; `scripts/verify_phase2b5_storage.py` constant 2935 → 2936; the three test constants that pin 2935 (`tests/unit/test_calendar_reconciliation.py` ×2, `tests/unit/test_storage.py` ×1). These are identity pins, not thresholds (§12.4).
- `reports/verdicts/phase2d_tier_a_2022_2026_verdict.{json,md}` regenerated, because they cite `CAL-FPR-V1-af8e309a…` four times in the JSON and twice in the markdown; `scripts/verify_phase2d_verdicts.py` must reproduce the new bytes, and the recomputed verdict must be unchanged (`NO-GO`, `PASS=3 / FAIL=0 / NOT RUN=20`) since 2019 is pre-binding.

**What it forbids moving** — these are scoped to `2022-01-03..2026-10-31`, outside the corrected date, and a re-pin of any of them is a falsifier, not diligence: `expected_sourced_window_calendar_fingerprint` (`CAL-FPR-V1-2d5ac7ac…`), `expected_baseline_calendar_sessions` 1201, `expected_authoritative_calendar_sessions` 1196, `min_binding_evaluation_start_date` 2022-01-03, `authorized_unarchived_special_sessions`, `authorized_calendar_holiday_exclusions`, `authorized_calendar_trading_inclusions`. Every numeric threshold in the file, N = 9, N_eval = 5, the 2024 fold's frozen state and the sealed holdout are equally out of bounds.

**Condition of validity (fail-closed).** The grid correction lands in the **same commit** as the committed 2019 artifacts that imply it, and the pin is re-sealed only when `scripts/probe_pre2022_preconditions.py` prints `[PASS] A1 2019: 245 session(s) reproduced by N sourced circular artifact(s)`. A correction whose evidence arrives later is a fabricated session with a fingerprint (§6.3, §6.5). If the committed 2019 circular set declares 2019-10-29 a holiday, or the annual circular's dates cannot be reconciled to 245, this Ruling is withdrawn by a superseding Ruling — not edited.

**What it does not do:** it does not move the binding window (still 2022-01-03), does not make any pre-2022 session gatable (A1 PASS is necessary, not sufficient — A3 surveillance and A4 dividends still govern), does not admit intraday, F&O or `BE` entry (§13.6), and does not touch the holdout.

**Computed status.** The item this Ruling creates is open until the A1 2019 line prints `PASS` and `expected_total_calendar_sessions` reads 2936 with `verify_phase2b5_storage.py` exit 0. Today it prints `NO` for all four years, so nothing in this Ruling is partially satisfied.

### 86.6 The provenance contract that turns A1 to `PASS` in `feat-s86`

`check_a1()` is the acceptance instrument; these are the requirements it enforces, read from the code and confirmed against the 13 artifacts on disk:

1. **One artifact per circular, under `data/raw/circulars/<CIRCULAR_ID_WITH_UNDERSCORES>.json`** — e.g. `NSE_CMTR_39612.json`. Shape mirrors the committed 2022-2026 files: `circular_id`, `circular_ref_no`, `download_ref_no`, `issue_date`, `market: NSE_CASH_EQUITY`, `segment`, `subject`, `source_url`, `http_status`, `retrieved_at`, `provenance_status`, plus dated entries under `trading_holidays`, `weekend_holidays`, `special_sessions`, `inferred_trading_sessions`. Entries may be `{"date": "2019-10-29", …}` or ISO strings; only `date[:10]` is read.
2. **Each artifact must have a current manifest row** in `data/reference/manifest.jsonl` keyed `circulars/<filename>` with `byte_count` and `sha256` equal to the file's bytes and `is_current: true`. A digest mismatch is a `NO` for the year, not a warning. Superseded rows stay as history (§10.1).
3. **Every artifact whose entries name year Y becomes mandatory calendar provenance** — its `circular_id` must appear in the calendar's `provenance.circular_references`, or A1 fails for that year. Do not deposit a partial or exploratory circular: coverage and citation are the same set, by construction.
4. **The grid must be exactly implied**: `weekdays(Y) − (trading_holidays ∪ weekend_holidays of Y) ∪ special_sessions(Y) ∪ inferred_trading_sessions(Y)` must equal the calendar's sessions for Y, with both directions checked — a calendar session no artifact implies (`unexplained`) and an artifact date the calendar lacks (`unsourced`) each fail.
5. **Per year, the set must cover both directions of the year's specials:** 2018 needs the muhurat session 2018-11-07 (a Wednesday, so it must appear as a `special_sessions` entry or the arithmetic loses it); 2019 needs 2019-10-27 (Sunday muhurat), the two election amendments 2019-04-29 and 2019-10-21, and — after Ruling 1 — the restored 2019-10-29; 2020 needs **both** weekend sessions, 2020-02-01 and 2020-11-14; 2021 needs 2021-11-04.
6. **The 2020-02-01 Union Budget session needs a Capital Market circular that declares it** as a `special_sessions` entry. It must be a cash-equity (CM) circular: `NSE/COM/43331` is a commodity-segment circular and does not attest that the Capital Market traded that Saturday. Without this artifact, 2020 is `NO` even though its twelve weekday holidays reconcile, because the calendar carries a session nothing implies.
7. **`provenance.sha256` must stop being the calendar's own digest.** It must be the digest of a named source: either the sha256 of a committed provenance bundle that is itself a manifest row, or of the primary annual circular, with `provenance.source` naming which. The probe only tests inequality with the CAL-FPR hex; the contract is the stricter statement.
8. **`provenance_status` stays `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`** unless a source certificate exists (§6.5). A1 does not require `VERIFIED`; promoting it without evidence is prohibited.
9. **Same-commit re-pins**: the manifest append, `expected_manifest_fingerprint`, the criteria version bump and (with Ruling 1) the calendar fingerprint and total-session pin all land together, with a comment stating that no threshold changed. A manifest append without its pin is a red gate, not a follow-up.
10. **What "A1 flips to PASS" does and does not mean**: the four `[PASS] A1 <year>` lines are the flip. The probe as a whole still exits 1 until A2 (identity intervals reaching 2018) and A4 (dividends or a committed maximum-hold bound) are met, so a green `probe_pre2022_preconditions.py` is a later, larger milestone than A1.

### 86.7 Phase verdicts and residuals

| Phase / claim | Verdict at `a3be813` | Residuals named |
|---|---|---|
| N-169 | **CLOSED** — dirty set names the legacy ini, recording refused, no row, probe flipped and failing at the parent and under mutation | — |
| `§12.3` gate machinery | **GO** | N-170 (every clone dirty; reuse unreachable), N-169 satisfied |
| `§10.8` A1 (2018-2021 grid) | **NO** — 4/4 years `NO`, provenance self-referential; correction authorised by Ruling 1, not executed | A1 artifacts, Ruling 1 conditions, A2/A4 untouched |
| `§80.13` items 3-5 | **PREPARED, NOT EXECUTED** — unchanged since §81.7 | A1, A2, A4 all open by design |
| Criteria / trials / holdout | **UNTOUCHED** — 1.1.9, 9 trial rows, 2024 fold frozen, holdout sealed | N-152 `ACCEPTED`, N-150 `OPEN` |

### 86.8 Work order

1. **Make a checkout byte-identical to its blobs** (N-170, serves `§12.3`). Probe: in a fresh clone, `git status --porcelain` is empty and `dirty_source_paths()` is `[]`; `git hash-object` equals the indexed oid for all 24 archives; then a recorded tree is reused (`reused green`) on the clone rather than re-run. Prefer `-text` over storing normalized bytes.
2. **Restore 2019-10-29 under Ruling 1, with its artifacts** (serves `§10.8`, unblocks A1 2019). Probe: `[PASS] A1 2019: 245 session(s)` from committed circulars, `expected_total_calendar_sessions` 2936, `verify_phase2b5_storage.py` exit 0, `verify_phase2d_verdicts.py` exit 0 after regeneration, and `expected_sourced_window_calendar_fingerprint` byte-identical.
3. **Ingest 2018, 2020 and 2021 under §86.6** (serves `§10.8`). Probe: `[PASS] A1 2018`, `[PASS] A1 2020` (with the 2020-02-01 CM special-session circular) and `[PASS] A1 2021`, each printing its session count; any artifact not cited in `provenance.circular_references` must fail that year.
4. **Carry §82.8 items 4-6** — A2 identity intervals reaching 2018, `WARMUP_NOT_GATABLE` plus a gating-mode probe, and A4 dividends or a committed maximum-hold bound. Serves Phase 3B-2.

### 86.9 What would falsify this verdict

- If an ignored `.pytest.ini` stops appearing in `dirty_source_paths()`, or a run over one is recorded, N-169 is not closed and §86.2 is wrong.
- If a forged row witnessing all nine verifiers is not reused on a clean checkout, the control was not a hit and the refusals in §86.2 need re-taking.
- If the committed 2019 circular set declares 2019-10-29 a holiday, or reconciles to 244 and not 245, Ruling 1 is wrong and must be superseded before any pin moves.
- If the grid correction lands without the 2019 artifacts in the same commit, the correction is a fabricated session regardless of who authorised it — this Ruling does not survive that.
- If `expected_sourced_window_calendar_fingerprint`, 1201 or 1196 move when the 2019 date is added, the re-pin drifted into a window the correction cannot touch.
- If a fresh clone at a later commit still reports 24 modified paths, N-170 stands and reuse remains unreachable outside this checkout.
---

## §87 — Audit of `e081886` (tag `feat-s86-3fb8f64`): the archives are bytes, the 2019 grid is sourced, A1 passes on all four years, and capture is authorised while gating is not

**Date:** 18 November 2026
**Commits under review:** `3fb8f64` (tag `feat-s86-3fb8f64`) — the code commit, 27 files, +889/−49; and `e081886` — its docs-only successor, 2 files, +72 (`CURRENT_STAGE_OF_WORK.md` 53 lines, the green row 19). Every measurement below is at `e081886`, whose tree contains `3fb8f64` unchanged.
**Verdicts:** N-170 `CLOSED` · §86.5 Ruling 1 **complied with in full** · A1 **PASS 5/5** · **§87.5 Ruling 1** authorises the 931-session Bronze capture as `WARMUP_NOT_GATABLE` · nothing here makes a pre-2022 session gating-eligible

### 87.1 Baseline re-measured at `e081886`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers discovered / executed | 9 / 9, every exit 0 (10 `scripts/verify_*.py` on disk; the gate discovers all but itself) |
| pytest | **536 passed** in 160.47 s (161.58 s wall) |
| W0.5-1 / 1b / 1c | append-only PASS (frozen volume 8,442 lines, 1–78); 2 volumes verified; index reproduces at **86** section rows |
| W0.5-4 | PASS — **90** commit-bearing tags verified |
| W0.5-5 | PASS — **54** current manifest rows match byte_count + sha256; **23** superseded rows skipped as history |
| Findings ledger before this round | 35 rows / 22 ids after N-170's two rows (§87.2); N-169 `CLOSED` |
| Criteria | **1.1.10**, `configs/go_no_go_criteria.yaml` sha256 `dedaf4310fa2da50…`, effective 2026-11-18 |
| Scratch-defect probes | **22 / 22** exit 0 (`verify_audit_findings.py`) |
| `probe_pre2022_preconditions.py` | **exit 1** — A1 5/5 `PASS`, A2 `NO`, A4 dividends `NO`, A4 max-hold `NO` (3 of 8 unmet) |
| Trials / fold / holdout | N = 9 / N_eval = 5, unchanged (no trial file appears in the diffstat); 2024 fold frozen; no `HOLDOUT_UNLOCK` sentinel; `2025-01-01..2026-11-11` sealed |
| `dirty_source_paths()` | `[]` |
| Green cache | 17 rows; the newest names `3fb8f64` (`dc67d4b4…`), which is the tree `e081886` extends |

### 87.2 N-170 — `CLOSED`

| Measurement | Result |
|---|---|
| Tracked archives (`*.zip`, `*.gz`) | **1,221** (1,220 `.zip`, 1 `.json.gz`) |
| Attribute, read back per path in one `git check-attr --stdin` call | `text: unset` on **1,221 / 1,221** — every rule that would convert them is overridden by the last-match `-text` block |
| Worktree bytes vs stored object | `git hash-object` against the index oid: **0 mismatches of 1,221** |
| Archives in `dirty_source_paths()` at `e081886` | **0** |
| Fresh clone (`git clone --no-local . /tmp/s87c` at `e081886`) | `git status --porcelain` **empty (0 paths)**; `dirty_source_paths()` **`[]`**; `cm12JAN2024bhav.csv.zip` 100,331 B on disk = 100,331 B in the object, 273 CR-bearing lines intact |
| Attack — `.gitattributes` reverted to the `a3be813` text, one archive deleted and re-checked out | probe **exit 1**: `FAIL N-170: 1221 tracked archive(s) still carry a text attribute, so a checkout rewrites their bytes: ['data/raw/2022/cm01APR2022bhav.csv.zip', …]`; the same file then hashes `db289cc9…` against index oid `66d91345…` while both report 100,331 bytes — the conversion is invisible to a size check and visible to a digest |
| Attack — attributes restored, archive re-checked out | `PASS N-170`, exit 0 |

The repair is an attribute decision, not a byte rewrite: `.gitattributes` gained 9 lines (comments plus `*.csv.zip`, `*.json.gz`, `*.zip`, `*.gz` marked `-text`) and **no archive blob changed**. The probe is scoped to archives on purpose — the whole-tree clean assertion belongs to the cache — and it fails closed on the attribute, on a digest mismatch, and on an archive in the dirty set. The one thing it cannot see is a conversion that leaves both the attribute and the digest intact, which is not a shape git can produce.

**Ledger.** N-170 was measured at §86.3 and carried in that section without a row (§79.9: a probe asserting the defect then could not pass on this checkout). It is registered here as `OPEN` with §86.3 as its opening measurement and closed in this section, in that order, because the ledger will not accept a closure with no prior row.

### 87.3 §86.5 Ruling 1 — every condition met, and the pins the Ruling forbade are untouched

| Condition from §86.5 | Measured at `e081886` |
|---|---|
| `2019-10-29` restored as a regular session | `{"date": "2019-10-29", "session_type": "FULL", "open_time": "09:15:00", "close_time": "15:30:00", "description": "Regular Trading Session"}` — present in `session_records` **and** in `sessions` |
| 2019 = 245, total = 2,936, window = 931 | `annual_session_counts` 2018 246 / **2019 245** / 2020 252 / 2021 248; `len(sessions)` **2,936**; `2018-04-01..2021-12-31` **931** (2018 186, 2019 245, 2020 252, 2021 248) |
| New CAL-FPR, provenance no longer self-referential | `CAL-FPR-V1-6acb5f45…47a9ac9`; `provenance.sha256` `7622fbf4…` — **not** equal to the CAL-FPR hex, and equal to the sha256 of the 3,483-byte bundle (recomputed) |
| Criteria 1.1.10, zero numeric threshold changes | version `1.1.9 → 1.1.10`, effective `2026-11-18`; a full walk of every numeric value in both YAML revisions finds **exactly one** changed number: `market_data_and_accounting_invariants.expected_total_calendar_sessions 2935 → 2936` |
| Manifest pin resealed | `MAN-FPR-V1-23200ba8… → MAN-FPR-V1-d05b87e19ca57dc7…`; file 47,639 B, sha256 `d05b87e1…` (recomputed) |
| `criteria.py` default, storage verifier, tests | `expected_total_calendar_sessions: int = 2936`; `verify_phase2b5_storage.py` exit 0 at 2,936; the three test constants moved with it (suite green) |
| Phase 2D artifacts regenerated | JSON and Markdown each carry **4 × `CAL-FPR-V1-6acb5f45`** and **1 × `CAL-FPR-V1-2d5ac7ac`**; `criteria_version` 1.1.10; the diff touches no criterion row — only version, fingerprints, the restatement note and the CRIT-DATA-06 row; `overall_verdict` stays **NO-GO** over `2022-01-03..2026-10-30` |
| `2d5ac7ac…`, 1201, 1196, 2022-01-03 untouched | all four byte-identical in both revisions of criteria; the sourced-window fingerprint also appears unchanged in the regenerated verdict evidence string |
| Fail-closed attacks | (A) delete `2019-10-29` → `[NO] A1 2019: 1 circular date(s) absent from the calendar, e.g. 2019-10-29`, `verify_phase2b5_storage.py` exit 1; (B) append one space to the bundle → storage exit 1, `Calendar provenance sha256 mismatch … declared '7622fbf4…' != committed source bundle digest '7b4829cf…' (Audit §86.6 item 7)`; (C) relabel `2019-10-29` `MUHURAT` → storage exit 1, `declared 'CAL-FPR-V1-6acb5f45…' != computed session content digest 'CAL-FPR-V1-29687860…'` |

The Ruling's central condition — that the correction arrive in the same commit as the artifacts that imply it — holds: `3fb8f64` adds the seven circulars, the bundle, the calendar correction, the criteria bump, the regenerated verdict and the probes together. Restoring the date without the evidence fails closed in two independent instruments (A and C), and touching the evidence without the calendar fails in a third (the `[NO] A1 2019` line).

### 87.4 A1 at `PASS` on all five checks

```
[PASS] A1 2018: 246 session(s) reproduced by 1 sourced circular artifact(s), 18 declared holiday(s)
[PASS] A1 2019: 245 session(s) reproduced by 3 sourced circular artifact(s), 21 declared holiday(s)
[PASS] A1 2020: 252 session(s) reproduced by 2 sourced circular artifact(s), 19 declared holiday(s)
[PASS] A1 2021: 248 session(s) reproduced by 1 sourced circular artifact(s), 18 declared holiday(s)
[PASS] A1 provenance: the calendar names a source digest 7622fbf4633683df…
```

| Year | Artifacts | Arithmetic that reproduces the grid |
|---|---|---|
| 2018 | `NSE/CMTR/36475` (2017-12-12, Ref 71/2017, annual) | 261 weekdays − 15 weekday holidays = **246**; the 2018-11-07 muhurat is a Wednesday and is therefore already inside the weekday count, declared as a `special_sessions` entry rather than added |
| 2019 | `NSE/CMTR/39612` (annual), `NSE/CMTR/40536` (2019-04-29 parliamentary election), `NSE/MSD/42319` (2019-10-21 Maharashtra assembly election) | 261 − 17 weekday holidays + 1 Sunday muhurat (2019-10-27) = **245** |
| 2020 | `NSE/CMTR/42877` (annual), `NSE/CMTR/43290` (2020-01-22, "Live Trading Session on February 01, 2020") | 262 − 12 weekday holidays + 2 Saturday sessions (2020-02-01, 2020-11-14) = **252** |
| 2021 | `NSE/CMTR/46623` (annual) | 261 − 13 weekday holidays = **248**; 2021-11-04 muhurat is a Thursday already counted |

Every one of the seven artifact files and the bundle matches its **current** manifest row's `sha256` and `byte_count` (0 mismatches, recomputed from disk), and every `circular_id` appears in the calendar's `provenance.circular_references`. The 2020-02-01 session is attested by a **Capital Market** circular that declares it a `special_sessions` entry (`SPECIAL`, 09:15–15:30), which is the §86.6 item 6 requirement met with the right instrument rather than the commodity circular §86.4 warned about.

**Two limits measured, not argued.** (i) `2019-10-29` enters the corpus as an `inferred_trading_sessions` entry — "the annual circular declares no holiday on this date" — not as a positive statement, and the probe's arithmetic is two-sided (`unexplained` and `unsourced` both fail, as attack A shows). Ruling 1 authorised exactly this form; it remains an attestation by absence, and it is the weakest of the 931 sessions' provenance. (ii) `[PASS] A1 provenance` *names* the source digest; it does not hash the bundle. Attack B therefore leaves that line at `PASS` while the bundle is one byte larger — but `load_nse_trading_calendar()` fails closed on the same edit with the digest mismatch above, so the corpus is verified at load even though the readiness line is a labelling check. I record the distinction rather than a finding: no artifact is accepted unverified, and the line's wording claims no more than it measures.

**The probe still exits 1** — A2 (4,510 interval rows begin 2022-01-03; 0 reach 2021-12-31) and A4 (0 of 138 committed ex-dates fall in the window; no maximum-hold bound) are open. A1 `PASS` is necessary and not sufficient, as §86.6 item 10 said.

### 87.5 Ruling 1 — the 931 sessions may be captured; they may not be gated

*Evidence.* At `e081886`: A1 5/5 `PASS` (§87.4), with the calendar's grid reproduced year by year from committed circular artifacts whose digests match their manifest rows. A2 `NO` (4,510 rows begin 2022-01-03, 0 reach 2021-12-31). A4 `NO` (0 of 138 ex-dates in the window; no maximum-hold bound committed). `probe_pre2022_preconditions.py` exit 1, 3 of 8 unmet. No file in the repository carries a `WARMUP_NOT_GATABLE` label today.

*It changes one definition.* Under §81.8 Ruling 1, a pre-2022 session becomes **capturable** when A1 holds. It now holds for all four years, so the window `2018-04-01..2021-12-31` — **931 sessions** (2018 186, 2019 245, 2020 252, 2021 248; 926 `FULL`, 4 `MUHURAT`, 1 `SPECIAL`) — may be ingested as **Bronze Bhavcopy**, byte-exact, one manifest row per archive, and every session so captured is labelled **`WARMUP_NOT_GATABLE`**. Capture eligibility is not gating eligibility: A2 and A4 are still unmet, so no metric, verdict, trial or denominator may be computed over these sessions, and the committed `min_binding_evaluation_start_date: 2022-01-03` stays exactly where it is.

*What the capture must look like.* Bronze payloads byte-exact as retrieved, never edited; one append-only Silver partition per session only after validation (§10.1); each archive a current manifest row carrying `source_url`, `retrieval timestamp`, `byte_count` and `sha256` (§10.7); atomic promotion, no partially promoted partition (§10.7); no `UPDATE`/`DELETE` against history (§10.1); `session_type` carried per session so the four muhurat bars (2018-11-07 17:30–18:30, 2019-10-27 18:15–19:15, 2020-11-14, 2021-11-04) and the 2020-02-01 Budget Saturday (09:15–15:30) are distinguishable from full sessions at the point of storage rather than reconstructed later; rows keyed by ISIN with symbol and series as effective-dated attributes (§10.4); and nothing written into `2025-01-01..2026-11-11` (§8.1).

*What it does not authorise.* It does not move the pin, the window, any threshold, N, N_eval, the 2024 fold or the holdout; it does not create a trial; it does not make any pre-2022 session `PASS`/`FAIL`-eligible; it does not license jump-adjusted or forward-filled series, which remain prohibited (§6.3); it does not stand in for A3 surveillance history (ASM effective 2018-03-26, GSM 2017-03-14) or for A2/A4. Capture is a data-acquisition decision, not a scoring decision.

*Probes that must fail closed before the item closes.* (1) A coverage probe that exits non-zero unless the window's captured sessions number **exactly 931**, each attested by a current manifest row whose bytes hash to its `sha256` and whose size equals `byte_count` — the Gate W0.5-5 / Gate 2D-6 mechanism measured working on 54 current rows in §87.1, applied to the new corpus; a session with no archive, an archive with no session, and a digest mismatch each fail. (2) The gating-mode probe §81.8 named and that does not exist yet: it must exit non-zero if any verdict's evaluated session set contains a `WARMUP_NOT_GATABLE` session, and its absence is why this Ruling authorises capture and not a single metric. (3) A1 must still print `PASS` at the capture commit, and the calendar's `CAL-FPR-V1-6acb5f45…` must not move — capture adds archives, it does not re-date the grid.

*Work item.* 1 below, serving Phase 3B-2 / §10.8; items 2 and 3 remain the gating blockers.

*Falsifier.* A capture commit whose corpus cannot be reconciled to all 931 sessions fails this Ruling; a session captured at a date the calendar does not hold, a muhurat bar stored as a full session, a Bhavcopy archive whose bytes disagree with its manifest row, or any computed metric over a `WARMUP_NOT_GATABLE` session before A2 and A4 land would each show the Ruling was applied as a gating permission rather than a capture one.

### 87.6 Phase verdicts and residuals

| Phase / claim | Verdict at `e081886` | Residuals named |
|---|---|---|
| N-170 | **CLOSED** — 1,221/1,221 archives `-text`, 0 digest mismatches, fresh clone 0 dirty paths, probe fails under the old attribute and passes restored | — |
| `§12.3` gate machinery | **GO** — green at 536, 9/9 verifiers, 90 tags, 54 manifest rows verified | N-169/N-170 both closed |
| `§86.5` Ruling 1 | **COMPLIED WITH** — every ordered pin moved, every forbidden pin byte-identical, attacks A/B/C fail closed | 2019-10-29 provenance is attestation by absence (§87.4) |
| `§10.8` A1 (2018–2021 grid) | **PASS 5/5** — 246 / 245 / 252 / 248 reproduced from 7 artifacts; bundle digest matches its bytes | A2 `NO`, A4 `NO`; probe exit 1 |
| `§86.8` items 1–3 | **DELIVERED** (item 4, parallel pytest, was not run — `pytest-xdist` absent, suite serial) | — |
| Pre-2022 gating | **NOT ELIGIBLE** — no `WARMUP_NOT_GATABLE` label exists yet and no gating-mode probe exists; capture authorised (§87.5), gating not | A2, A4, gating-mode probe |

### 87.7 Work order

1. **Capture the 931 sessions under §87.5** (serves Phase 3B-2 / `§10.8`). Probe: the coverage probe exits 0 at exactly 931 manifest-attested sessions with bytes matching every row; any missing/extra session or digest mismatch exits non-zero; A1 still `PASS` and `CAL-FPR-V1-6acb5f45…` unchanged at the same commit.
2. **Build the gating-mode probe** (§81.8, unchanged from §86.8 item 4a): it must exit non-zero if an evaluated session set contains a `WARMUP_NOT_GATABLE` session. Probe: a deliberately mis-scoped evaluation is refused, and the refusal is printed by name.
3. **A2 — identity intervals reaching 2018-04-01** (serves Phase 3B-2). Probe: the A2 line prints `PASS` with a first row at or before 2018-04-01 and 0 rows required before it; a window session with no interval fails.
4. **A4 — dividends or a committed maximum-hold bound** (serves Phase 3B-2, §13.2). Probe: the A4 lines print `PASS`, and the max-hold bound is read from criteria, not from a module default.

### 87.8 What would falsify this verdict

- If a fresh clone of a later commit reports any modified path, or an archive on disk hashes to something other than its index oid, N-170 is not closed and §87.2 is wrong.
- If `git check-attr text` returns anything but `unset` for one of the 1,221 archives, the attribute block is not last-match-wins and the repair is partial.
- If the calendar's 2019 count is not 245 with `2019-10-29` present as `FULL`, or the total is not 2,936 with `expected_total_calendar_sessions` 2,936, Ruling 1 of §86.5 was not complied with.
- If `expected_sourced_window_calendar_fingerprint`, 1201, 1196 or the 2022-01-03 start differs between `a3be813` and `3fb8f64`, the re-pin drifted into the binding window.
- If any A1 year passes with a circular whose bytes disagree with its manifest row, or with an artifact not cited in `provenance.circular_references`, the A1 measurement does not mean what §87.4 says.
- If a metric, verdict or trial is computed over a pre-2022 session while A2 or A4 is unmet, the capture authorisation was read as a gating authorisation and this Ruling's intent is violated regardless of what it says.
---

## §88 — Audit of `df97173` (tag `feat-s87-df97173`): the 931 warm-up sessions are captured and certified, the guard refuses them, and the certificate cannot see a transposed label

**Date:** 18 November 2026
**Commits under review:** `e35d8b1` (capture, criteria 1.1.11, guard, probes; 955 files, +1,903/−40, of which 931 are archives and 931 are manifest lines), `6cb7a81` (the five version literals in four test files, +7/−7), `4ebcc5e` and `df97173` (docs `CURRENT_STAGE_OF_WORK.md`, 4 files' worth of prose). Every measurement below is at `df97173`.
**Verdicts:** capture **DELIVERED and verified** · criteria 1.1.11 **reseal only, zero numeric changes, verdict artifacts correct** · A5 guard and probe **DELIVERED**, refuses a warm-up session at the call site · A1 **PASS 5/5**, A2 and A4 **NO** · capture grants no gating eligibility · **N-171** and **N-172** registered `OPEN`

### 88.1 Baseline re-measured at `df97173`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers discovered / executed | 9 / 9, every exit 0; `verify_audit_findings.py` **22/22 probes** at the commit |
| pytest | **543 passed** in 180.27 s (7 new tests in `tests/unit/test_pre2022_gating_mode.py` over §87's 536) |
| W0.5-1c | PASS — audit index reproduces at **86** section rows |
| W0.5-4 | PASS — **92** commit-bearing tags |
| W0.5-5 | PASS — **985** current manifest rows match `byte_count` + `sha256`; **23** superseded skipped as history |
| Findings ledger before this round | 35 rows / 22 ids (N-170 `CLOSED` §87); 37 rows / 24 ids after §88.2 |
| Criteria | **1.1.11**, effective 2026-11-18, `CRIT-FPR-V1-1c0131d6…` |
| `scripts/probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931` |
| `scripts/probe_pre2022_preconditions.py` | **exit 1** — A1 5/5 `PASS`, A5 `PASS`, A2 `NO`, A4 dividends `NO`, A4 max hold `NO` (3 of 9 unmet) |
| Trials / fold / holdout | **9** registry rows, `evaluation_count` **5**, pin `3326b1b2…` unchanged, no trial file in the diff; 2024 validation fold untouched; no `data/raw/2025` or `2026` path in the diff; `2025-01-01..2026-11-11` sealed |
| Worktree | `git status` clean; 2,146 tracked `data/raw` archives hash to their index oid with **0 mismatches** |

### 88.2 The capture — 931 sessions, 931 rows, bytes that match

| Measurement | Result |
|---|---|
| Calendar sessions in `2018-04-01..2021-12-31` | **931** — `FULL` 926, `MUHURAT` 4 (2018-11-07, 2019-10-27, 2020-11-14, 2021-11-04), `SPECIAL` 1 (2020-02-01) |
| Archives on disk under `data/raw/2018..2021` | **931**, one per session, no non-`.zip` files |
| Current manifest rows naming those archives | **931** — 2018 186 / 2019 245 / 2020 252 / 2021 248, **every one** `gating_mode: WARMUP_NOT_GATABLE` |
| `byte_count` / `sha256` against disk, recomputed by me | **0 size mismatches, 0 digest mismatches of 931** |
| Required row fields | `source_url`, `retrieved_at`, `byte_count`, `sha256`, `session_date`, `session_type`, `gating_mode`, `provenance_status` present on **931/931**; one host (`archives.nseindia.com`); retrieval timestamps span `05:06:55`–`05:13:46Z` on 2026-11-18; every row `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` (§6.5) |
| Manifest growth | `data/reference/manifest.jsonl` **+931 / −0** lines → 1,008 rows = **985 current** (54 + 931) + **23 superseded**; **0** superseded row concerns a warm-up archive; 714,265 bytes, sha256 `7131c213…` |
| Internal dates — the check the probe omits | I opened all 931 archives and parsed every distinct `TIMESTAMP` value: **931/931 archive-internal dates equal their `session_date`**, one archive carries a two-digit year (`cm13JUL2020bhav.csv.zip`, `13-Jul-20`) |
| Bytes vs git | `git hash-object` over all 2,146 tracked `data/raw` archives equals the index oid for **2,146/2,146**; `git check-attr text` returns `unset` on the new archives, so the capture inherits §87.2's attribute repair |
| Promotion and refusal rules, read in `scripts/ingest_pre2022_bhavcopy.py` | payload validated before promotion (one CSV member, parses to ≥ 1 record, **parsed trade_date == scheduled session**), atomic `.part` + `fsync` + `os.replace`, append-only row with `fsync`, a failed session writes neither file nor row, re-run reuses an attested archive instead of duplicating, exit non-zero on any failure |

The count is reconstructed in both directions: the probe walks the calendar and demands a row per session, then walks disk and demands a row per archive, so a missing session, an extra archive, a duplicate current row and a dead row each fail. `EXPECTED_SESSIONS = 931` is a literal in the probe; the calendar is still the authority it measures against, and the literal is the number §87.5 Ruling 1 authorised.

### 88.3 Probe attacks — five shapes refused, and one that is not

Run against a copy of the corpus (`/tmp/s88c`), each attack reverted before the next:

| Attack | Exit | Message |
|---|---|---|
| Delete one archive | **1** | `session 2019-01-03 (FULL): attested archive … is absent from disk` → `930/931` |
| Flip one byte inside an archive (size unchanged, 67,993 B) | **1** | `… sha256 mismatch (disk c6a971aa…, row 0ce5fd92…)` → `930/931` |
| Relabel the 2018-11-07 `MUHURAT` session `FULL` | **1** | `… declares session_type 'FULL' instead of the calendar's 'MUHURAT'` |
| Drop `gating_mode` from the 2020-02-01 `SPECIAL` row | **1** | `… carries gating_mode None, expected 'WARMUP_NOT_GATABLE'` |
| Add a second current row for one session | **1** | `session 2018-04-02 (FULL): 2 duplicate current row(s)` (+ an orphaned-row problem) |
| Drop an unattested archive into `data/raw/2018/` | **1** | `archive … (67993 bytes): no current manifest row attests it` |
| **Transpose `session_date` between two archives, bytes and labels otherwise untouched** | **0** | `OVERALL: COVERED — 931/931 … WARMUP_NOT_GATABLE on every row` |

The last row is **N-171**. The probe keys each archive by the `session_date` its row declares and checks the row's digest against the bytes; it never opens the archive, so a corpus in which two archives are filed under each other's session satisfies every check it makes. Each archive's own `TIMESTAMP` column still names the other date, and `parse_bhavcopy_archive` under the declared partition date refuses it (`Row trade_date 2018-04-02 does not match partition date 2018-04-03 … H-24`), so the mislabel cannot silently reach a price series — but between capture and the first Silver build, the only artefact that certifies the corpus cannot distinguish 931 correctly dated sessions from 931 labels placed on the wrong bytes. The committed corpus is not transposed (§88.2: 931/931 internal dates match); the certificate is what is short. Severity **MEDIUM**, because the property the Ruling's falsifier named — "a Bhavcopy archive whose bytes disagree with its manifest row" — holds byte-for-byte here while the row and the session disagree, and the probe was written to be that falsifier.

### 88.4 Criteria 1.1.11 and the Phase 2D artifacts

| Condition | Measured |
|---|---|
| Version and date | `1.1.10 → 1.1.11`, `effective_date 2026-11-18` |
| Zero numeric threshold changes | every numeric leaf of both revisions parsed and compared: **7 of 7 identical**; the file's own diff contains three hunks — the version line, its comment block, and the manifest pin — and **no** other line |
| The one value that moved | `expected_manifest_fingerprint`: `MAN-FPR-V1-d05b87e1… → MAN-FPR-V1-7131c2136b54ebd557c288170f00b2facec7d5e775231ecaa5bd4dedce0012ec`, recomputed from the committed manifest and equal |
| Manifest pin integrity | 1,008 rows, 714,265 bytes, sha256 `7131c213…` — the byte count and digest quoted in the criteria comment are the file's |
| Pins that must not move | `expected_calendar_fingerprint` **CAL-FPR-V1-6acb5f45…** unchanged; `expected_sourced_window_calendar_fingerprint` **2d5ac7ac…** unchanged; `min_binding_evaluation_start_date` **2022-01-03**; `expected_authoritative_calendar_sessions` **1196**; `expected_baseline_calendar_sessions` **1201**; trial pin **3326b1b2…** |
| Phase 2D verdict artifacts | both files changed **3 leaves**: `criteria_version 1.1.10 → 1.1.11`, `criteria_fingerprint 3744b520… → 1c0131d6…`, and the prepended 1.1.11 restatement paragraph. `overall_verdict` **NO-GO** unchanged, no criterion row changed, `CAL-FPR-V1-6acb5f45` appears 4× in the JSON and 2× in the Markdown, `2d5ac7ac` once in each |
| Generator | `scripts/generate_phase2d_tier_a_report.py` changed only by the new restatement string; the artifact is generator output, not hand-edited |
| Trials / fold / holdout | 9 registry rows with `evaluation_count: 5` and manifest pin `3326b1b2…`, none of them in the diff; the 2024 validation fold is untouched because no numeric value moved; no path under `data/raw/2025` or `2026`, no trial, no holdout artefact is touched |
| Test literals (`6cb7a81`) | seven `criteria_version` assertions across four files follow the bump; suite green at 543 |

A reseal that changes exactly the fingerprint its own comment explains, leaves every threshold byte-identical, and moves no verdict row is what §87.5 Ruling 1 permitted. The Ruling authorised capture, not a re-baseline, and the artifacts show no re-baseline.

### 88.5 A5 — the guard refuses a warm-up session where the corpus is built

| Measurement | Result |
|---|---|
| `assert_no_warmup_sessions_in_evaluation` | requires `binding_start_date` as a keyword (no module default to inherit), refuses with `WarmupSessionGatingViolation` naming the label, the pin, the set label and the first offending dates, and returns the inspected count otherwise |
| Call site | `build_historical_dataset_from_raw_bhavcopy`, after the archives are read and **before** either fingerprint or any verdict input is computed — the only function in the repository that builds an evaluation corpus from `data/raw` |
| Attack at the call site | `build_historical_dataset_from_raw_bhavcopy(raw_dirs=[data/raw/2021])` → `WarmupSessionGatingViolation: … 248 of 248 evaluated session(s) are WARMUP_NOT_GATABLE because they precede the binding evaluation start 2022-01-03: 2021-01-01, … (+243 more)` |
| `probe_pre2022_preconditions.py` A5 | `[PASS] A5 gating mode: 8 verdict artifact(s) evaluated, 0 of 4,903 evaluated session(s) precede the binding start 2022-01-03` |
| Probe attacks | a fabricated verdict declaring `2021-06-01..2021-12-31` → `NO … evaluates 148 of 148 session(s) labelled WARMUP_NOT_GATABLE`; a verdict declaring no window → `NO … declares no evaluation window, so its session set cannot be checked` |
| Wiring | `tests/unit/test_pre2022_gating_mode.py` — 7 tests, including the guard, the refusal at the builder, the shipped verdict corpus at `PASS`, and `probe_pre2022_bronze_coverage.main() == 0` with `931/931` |

**Residual, named rather than implied.** A5 measures *declared* windows: it reads `evaluation_start_date`/`evaluation_end_date` from each verdict and intersects them with the calendar. A verdict that computed over warm-up sessions while declaring a 2022 start would pass A5. The defence against that is the call-site guard, which refuses on the session dates actually read from archives rather than on a label; the probe is a corpus audit over the artifacts that exist, not a proof that each artifact was computed from the window it declares.

### 88.6 The two engineering changes the corpus forced

**`%d-%b-%y` TIMESTAMP parsing (`src/signal_core/storage/ingest.py`, +8 lines).** Exactly **one** of the 931 archives prints a two-digit year — `data/raw/2020/cm13JUL2020bhav.csv.zip`, whose `TIMESTAMP` cells read `13-Jul-20`. It parses to `2020-07-13` and yields 1,392 `EQ` records under `trade_date=2020-07-13`. The four-digit branch is tried first and does not swallow the string (`%d-%b-%Y` on `13-Jul-20` raises, so no year-20 date is produced), and the two-digit branch does not swallow a four-digit one (`%d-%b-%y` on `13-JUL-2020` raises). Without the branch the capture could not have included 2020-07-13 at all, so this is a necessary change, not a convenience — and it is what the probe's `validate()` relies on when it compares the parsed date to the scheduled session.

**N-172 — the branch is unbounded.** `13-Jul-68` parses to **2068-07-13** and `13-Jul-99` to 1999-07-13: Python's `%y` maps 00–68 to 2000–2068 and 69–99 to 1969–1999, and the parser never compares the result to the session the archive is filed under. `13-Jul-68` lands **inside the sealed holdout era**. Measured containment: parsing any archive with a partition date its rows do not carry raises H-24 (`Row trade_date … does not match partition date …`), and the archive's partition date comes from the calendar or filename rather than from the row, so a stray two-digit year cannot route data past the holdout check today. Severity **LOW** — a latent acceptance, contained downstream, in new code. The fix is a plausibility bound (the parsed year must lie within the corpus year it is filed under, ±1) with the refusal named.

**Binding-window year scoping (`scripts/verify_cash_universe_coverage.py`, +26/−7).** Before the capture, Gate COV-2 swept every `data/raw/<year>/` directory and would have discovered 2,126 archives against a 1,195-row archive manifest. The gate now scopes the sweep to the years the archive manifest names and prints an `[INFO]` naming the **931** archives it excludes and the instrument that does verify them. Measured at `df97173`: `1,195 / 1,195` digests and reverse coverage, `100.0000%` COV-2, `ALL CASH UNIVERSE COVERAGE GATES PASSED`, exit 0. The 1,195 is not the calendar's 1,196: the calendar holds **1,196** binding sessions and the archive manifest **1,195**, and the single difference is **2025-02-01**, a Saturday Budget session that lies inside the sealed holdout. So the gate certifies coverage of the corpus it has against the manifest derived from it, and cannot by construction certify the calendar — that comparison is made here, in this section, and its one-row deficit is holdout, not error.

**Additive-fix check (§14.4).** `resolve_all_bhavcopy_archives` has exactly one consumer, the gate itself, and it is now scoped. The only evaluation-corpus builder from raw archives is `build_historical_dataset_from_raw_bhavcopy`, and it is the guarded path — there is no second, unguarded loader beside it. `scripts/reconcile_bhavcopy_series.py` reads `data/raw` by trade date for snapshot reconciliation; it is not a gate, computes no verdict, and is unchanged.

### 88.7 Phase verdicts and residuals

| Phase / claim | Verdict at `df97173` | Residuals named |
|---|---|---|
| §87.5 Ruling 1 probe (1) — Bronze coverage | **DELIVERED and verified** — 931/931, digests, labels, bidirectional reconciliation, six attacks refused | **N-171**: the certificate cannot see a transposed `session_date` |
| §87.7 item 2 — gating-mode guard | **DELIVERED** — call site measured refusing 248/248, probe `PASS` at 0/4,903, fabricated mis-scope refused | A5 trusts declared windows (§88.5) |
| `§10.8` A1 (2018–2021 grid) | **PASS 5/5**, unchanged at 246 / 245 / 252 / 248 | — |
| `§10.8` A2 / A4 | **NO / NO** — intervals still begin 2022-01-03; 0 of 138 ex-dates in the warm-up window; no max-hold bound | A2, A4 |
| Pre-2022 gating | **NOT ELIGIBLE, and now refused** — `[NO]` A2/A4, guard raises, no verdict covers a warm-up session | A2, A4 |
| Criteria 1.1.11 | **RESEAL ONLY** — one non-threshold value moved; verdict unchanged | — |
| `§12.3` gate machinery | **GO** — 543 passed, 9/9 verifiers, 92 tags, 985 manifest rows verified | N-171, N-172 |

Capture eligibility and gating eligibility stayed separate in the code, not only in the prose: the label is written by the capture, the guard reads the calendar boundary rather than the label, and A2/A4 still print `NO`.

### 88.8 Work order

1. **Close N-171** (serves §87.5 Ruling 1 probe (1), Phase 3B-2 / `§10.8`). `scripts/probe_pre2022_bronze_coverage.py` must open each archive once and require its distinct `TIMESTAMP` values to be exactly the row's `session_date`. Probe: the transposition attack exits 1 naming both dates; the committed corpus still prints `COVERED 931/931`, exit 0.
2. **Close N-172** (serves the capture's ingest path, `§10.8`). Bound the two-digit-year branch to the session the archive is filed under. Probe: `13-Jul-68` is refused by name; `cm13JUL2020bhav.csv.zip` still parses to 2020-07-13 with 1,392 `EQ` records, and the corpus stays 931/931.
3. **A2 — identity intervals reaching 2018-04-01** (serves Phase 3B-2, unchanged from §87.7 item 3). Probe: the A2 line prints `PASS` with a first row at or before 2018-04-01.
4. **A4 — dividends or a committed maximum-hold bound** (serves Phase 3B-2, §13.2, unchanged from §87.7 item 4). Probe: both A4 lines print `PASS` and the bound is read from criteria.
5. **Ratify the A5 residual** (serves §87.5 probe (2) as a corpus audit): either A5 reads the evaluated session set from the trial/evaluation ledger rather than the verdict's declared window, or the residual is accepted in the criteria comment. Probe: a verdict whose declared window is 2022 while its ledger rows reach 2021 is refused.

### 88.9 What would falsify this verdict

- If any of the 931 archives hashes to something other than its manifest row, or a session in the window has no row, §88.2 is wrong and the capture is not delivered.
- If a row in the warm-up corpus lacks `gating_mode`, or carries a `session_type` the calendar does not, the label is not a property of the corpus.
- If `expected_manifest_fingerprint` does not equal the recomputed `MAN-FPR-V1` over `manifest.jsonl`, criteria 1.1.11 does not pin the corpus it claims to pin.
- If any numeric leaf differs between 1.1.10 and 1.1.11, or `min_binding_evaluation_start_date`, `2d5ac7ac…`, 1201, 1196, the trial pin or the 2024 fold moved, the Ruling was used to re-baseline.
- If `build_historical_dataset_from_raw_bhavcopy` accepts a pre-2022 directory, or a committed verdict's evaluated set contains a session before 2022-01-03, the guard is bypassable and this section's A5 verdict is wrong.
- If a transposed pair of archives exits 0 from *every* gate that inspects the corpus, N-171 is understated; if it now exits 1, N-171 is closed and this section's finding is stale — the probe would say so.
---

## §89 — Audit of `2e7f51b` (tag `feat-s89-2e7f51b`): both §88 findings close, the suite halves its wall time with the same assertions, and the replacement clock ticks in 15.6 ms

**Date:** 18 November 2026
**Commit under review:** `eb05053` (8 files, +293/−77: the coverage certificate reads the archives, the two-digit year is bounded, the gate gains a parallel invocation and a tolerant decoder, the ledger test drops its duplicate probe execution, one benchmark changes its clock), plus `2e7f51b` (the implementer's `CURRENT_STAGE_OF_WORK.md` note, not audited here).
**Verdicts:** **N-171 CLOSED** · **N-172 CLOSED** with a named residual · gate speedup **verified as invariant** (543 passed both ways, zero skip/xfail) · §88 work order item 5 **ratified as an accepted residual** (Ruling 1) · invariants **unchanged** · **N-173** registered `OPEN`

### 89.1 Baseline re-measured at `2e7f51b`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite invocation the gate chose | `-m pytest -n auto --dist loadfile -q` (printed by the gate) |
| Suite under the gate | **543 passed** in **50.66 s** (gate total 51.81 s); green row `eb05053` records 543 in 48.84 s |
| Suite sequential, same commit, for invariance | **543 passed** in **121.91 s**, zero `skipped`/`xfail` in the log |
| Verifiers | 9/9 exit 0; W0.5-2 executes **24/24** ledger probes; W0.5-1c index reproduces (88 sections); W0.5-5 **985** current / **23** superseded |
| Tags | 94 commit-bearing (W0.5-4 PASS) |
| Green cache | **20** rows, last `b5d9cb027d86…` at `eb05053`, `suite_count` 543 |
| Findings ledger before this round | 37 rows / 24 ids (N-171, N-172 `OPEN` §88); 40 rows / 25 ids after §89 |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931 … each archive's own session date equal to its row` |
| `probe_pre2022_preconditions.py` | **exit 1** — A1 **5/5 PASS** (246/245/252/248), A5 **PASS** (8 artifacts, 0 of 4,903), A2 **NO** (4,510 rows begin 2022-01-03, 0 reach 2021-12-31), A4 dividends **NO** (0 of 138 ex-dates), A4 max hold **NO** |
| `probe_n171` / `probe_n172` | **PASS** / **PASS** (both flipped to assert closure) |
| Criteria / pins | **1.1.11**, `MAN-FPR-V1-7131c213…`, `CAL-FPR-V1-6acb5f45…`, `2d5ac7ac…`, binding **2022-01-03**, 1,196 / 1,201 |
| Trials / fold / holdout | **N = 9**, `N_eval = 5`, pin `3326b1b2…`; 2024 validation fold frozen; holdout `2025-01-01..2026-11-11` sealed |
| Files the range touches | 8 — none under `configs/`, `data/trials/`, `reports/verdicts/`, `data/raw/`; volume 1 and the audit report untouched |

### 89.2 N-171 — CLOSED, the certificate now reads what the exchange wrote

The coverage probe gained `embedded_session_dates`, which opens the archive, requires exactly one CSV member, reads `TIMESTAMP` (or `TRADEDATE` in the unified format), parses each distinct value and requires the set to equal the row's `session_date` exactly. Attacked in a detached worktree at `2e7f51b` (`/tmp/s89w`, restored clean after each), all four shapes refuse:

| Attack | Exit | Message |
|---|---|---|
| Transpose `session_date` between `cm02APR2018` and `cm03APR2018`, bytes and digests untouched | **1** | `session 2018-04-02 (FULL): … cm03APR2018bhav.csv.zip carries its own session date(s) 2018-04-03, so the row's session_date is not on these bytes` (+ the mirror row) → `NOT COVERED — 929/931, 2 problem(s)` |
| Overwrite one archive with the other session's bytes **and re-attest the row's `sha256`/`byte_count` to the new bytes** | **1** | the same embedded-date refusal — the digest check cannot catch this and does not need to |
| Truncate an archive to 23 bytes and re-attest its digest | **1** | `… cannot be read for its own session date: File is not a zip file` |
| Committed corpus, unmodified | **0** | `COVERED — 931/931 … each archive's own session date equal to its row` |

`probe_n171` is flipped: it first asserts the reader resolves both fixture archives to their own dates (so a refusal cannot come from a broken fixture), then asserts the tampered manifest exits 1 naming **both** dates, then asserts the committed manifest exits 0 at `931/931`. That is the closure direction §88.8 item 1 specified — the transposition attack must exit 1 — measured at the probe, not only at the script.

**Additive-fix check (§14.4).** The archive-date reader is used by the coverage probe and by `probe_n171`; no second certifier claims "covered" without opening the bytes, and no unguarded path beside the guarded one was added. The capture's own `validate()` still compares the parsed row date to the scheduled session (H-24), which is the same invariant one stage earlier. Nothing else in the repository consumes `parse_bhavcopy_date` on archive bytes except `parse_bhavcopy_archive`, which refuses a row whose date differs from the partition date.

### 89.3 N-172 — CLOSED, with the bound's residual named

`parse_bhavcopy_date` now refuses a `%d-%b-%y` value whose parsed year falls outside **1990–2030**, before returning it. Boundaries measured exactly:

| Input | Result |
|---|---|
| `13-Jul-68` | **REFUSED** — `Implausible two-digit year in Bhavcopy: '13-Jul-68' parses to 2068-07-13, outside the plausible 1990-2030 range` |
| `13-Jul-69`, `13-Jul-88`, `13-Jul-89`, `13-Jul-67` | refused (1969, 1988, 1989, 2067) |
| `13-Jul-90` | 1990-07-13 — accepted, the low edge |
| `13-Jul-29`, `13-Jul-30` | 2029-07-13, 2030-07-13 — accepted, the high edge |
| `01-Jan-31` | refused (2031) |
| `13-Jul-20`, `13-JUL-2020` | 2020-07-13 — the archive that needs the branch still parses |
| `13-Jul-99`, `13-Jul-00` | 1999-07-13, 2000-07-13 — accepted (inside the window) |
| `13-Jul-2`, `13-Jul-2O` | refused as unrecognized, as before |
| `cm13JUL2020bhav.csv.zip` at its own partition date | resolves to 2020-07-13 with **1,392 EQ** records |
| the same archive at a 2068 partition date | H-24 refuses: `Row trade_date 2020-07-13 does not match partition date 2068-07-13 for ISIN INE144J01027` |

`probe_n172` is flipped: it asserts the refusals by name and by the date they would have become, asserts the three in-window years beside the bound, asserts the archive's **1,392** EQ count, and keeps the H-24 containment.

**Residual, named rather than implied.** §88's row asked for "0 two-digit-year inputs accepted outside the year of the corpus they are filed under (±1)". A parser that sees only a string has no filed year to compare against, so the implemented bound is a plausible-century filter (1990–2030) rather than a ±1 window: `13-Jul-99` is still accepted by the bare parser. The ±1 clause is satisfied where the archive context exists and more strongly than written — H-24 requires the parsed date to equal the partition date **exactly**, so an archive whose two-digit year misstates its session is refused at parse time (measured above at the 2068 partition). What the bound buys is that a stray two-digit year can no longer silently name a session inside the sealed holdout era without an archive to be wrong against. That is the danger §88 registered, and it is refused.

### 89.4 The gate speedup — same suite, same assertions, and one new clock defect

| Claim | Measured |
|---|---|
| `-n auto --dist loadfile` runs the same suite | **543 passed** parallel (50.66 s) vs **543 passed** sequential (121.91 s), zero skip, zero xfail in both logs; the gate prints which invocation it used |
| Sequential fallback when xdist is absent | `pytest_command()` returns `-m pytest -q` with `find_spec("xdist")` stubbed to `None`, and the real binary with it present; `pytest-xdist` is **absent** from `pyproject.toml`, so a fresh environment takes the fallback and the sequential run above is that exact command |
| A failure is still a failure under the tolerant decoder | Deliberate failing test that writes non-UTF-8 bytes (`0x81`, `0x8d`, `0x9d`) plus a `pytest.skip`: the gate returned **False** (`1 failed, 543 passed, 3 errors`), printed the summary, raised no decode error and did not report a pass |
| The ledger test no longer executes the probes twice | `--list` reports **24**; appending a ledger row for an unregistered `N-999` makes `verify_audit_findings.py` exit **1** (`FAIL N-999: no probe registered`) and the ledger test fail (`assert 'N-999' in registered`) — the mapping check still bites, and W0.5-2 still executes all 24 each pass |
| Ceilings unchanged | `per_fill_1k_us < 250.0`, `per_fill_4k_us < 250.0`, `scaling_ratio < 2.5` — read unchanged at `2e7f51b` |
| Instrument, live | 1,000 fills: **46.9 µs/fill CPU** (wall 51–54 µs); 4,000 fills: **46.9–66.4 µs/fill CPU**; ratio **0.75–1.42** over five repetitions — comfortably inside both ceilings |
| Instrument resolution | **15.625 ms**, with **2 distinct values in 20,000 calls** on this Windows interpreter |

**N-173 — the new clock is quantized, so a faster implementation fails the test.** Because `process_time()` advances in 15.625 ms steps, a 1,000-fill loop costing under half a tick measures **0.0 µs/fill**; the guard's `max(per_fill_1k_us, 1.0)` then divides the 4,000-fill figure by 1.0. Quantized from a 5 µs/fill implementation the two measurements are 0.0 and 3.91 µs → ratio **3.91 ≥ 2.5**, so the benchmark fails on a 9× speedup of the same O(1) code, and reports "Replay guard scaling superlinearly". The wall clock it replaced had nanosecond resolution and no such window. The defect is Windows-bound — on a host with a fine-grained `process_time` the same workload measures near 1.0 — and test-only (no gate assertion is weakened; a false failure is fail-closed for the gate but misdirects the implementer). Severity **LOW**, `OPEN`, probe `probe_n173` registered: it asserts the benchmark still uses `process_time()` and the `max(..., 1.0)` floor, measures the tick, and on a coarse-tick host reproduces the 3.91 ratio while on a fine-grained host asserts the near-1.0 result.

### 89.5 Ruling 1 — §88 work order item 5 is ratified as an accepted residual

**Evidence first.** At `2e7f51b` the A5 block still reads each verdict's declared `evaluation_start_date`/`evaluation_end_date` and intersects that window with the calendar (§89.1: `[PASS] A5 … 0 of 4,903`), while the load-bearing refusal is the call-site guard, which raises on the session dates actually read from archives (§88.5: `248 of 248`). No code changed in this round to move A5 onto the ledger, and the criteria comment carries no residual statement.

**Ruling.** §88.8 item 5 is satisfied by acceptance rather than by code: the A5 declared-window read is a **named accepted residual**, registered here and citable, not a defect awaiting closure. It changes nothing about what A5 measures and no threshold; it changes the item's completion condition from "A5 reads the ledger or the criteria comment records the residual" to "the residual is recorded in the auditor's report and cited by the criteria comment at its next revision". It does not change the guard, the probe's `PASS` semantics, or any verdict.

**Falsifier.** If a committed verdict is ever found whose declared window is 2022-onward while its evaluated fills or sessions reach before 2022-01-03, acceptance was wrong and the item returns as a defect. The probe that must fail closed before any future re-opening is the fabricated-verdict attack already measured in §88.5 (`148 of 148` refused) plus the call-site guard measured here.

### 89.6 Invariants confirmed unchanged

| Invariant | Value at `2e7f51b` | How confirmed |
|---|---|---|
| Criteria version / manifest pin | **1.1.11** / `MAN-FPR-V1-7131c213…` | read from the committed YAML; no `configs/` path in the range |
| Binding evaluation start | **2022-01-03** | read; A5 intersects against it |
| Calendar pins | `CAL-FPR-V1-6acb5f45…`, `2d5ac7ac…`, 1,196 authoritative / 1,201 baseline | read; gate W0.5-? green |
| Trials | **N = 9**, `N_eval = 5`, pin `3326b1b2…` | registry manifest; no `data/trials/` path in the range |
| 2024 validation fold | frozen | criteria untouched; no fold artifact in the range |
| Holdout | `2025-01-01..2026-11-11` sealed, no `HOLDOUT_UNLOCK` | no holdout path, no `data/raw/2025` or `2026` in the range |
| A1 / A5 | **PASS / PASS** | precondition probe at `2e7f51b` |
| A2 / A4 | **NO / NO** | precondition probe: 4,510 interval rows begin 2022-01-03; 0 of 138 ex-dates; no max-hold bound |
| Pre-2022 gating | **NOT ELIGIBLE** | guard refuses a warm-up directory (§88.5), A2/A4 `NO` |

### 89.7 Phase verdicts and residuals

| Phase / claim | Verdict at `2e7f51b` | Residuals |
|---|---|---|
| §88.8 item 1 (N-171) | **CLOSED** — four attacks refused, flipped probe passes, corpus still 931/931 | — |
| §88.8 item 2 (N-172) | **CLOSED** — bound exact at 1990/2030, H-24 exact equality retained, 1,392 EQ records preserved | bare parser accepts 1990–2030 without archive context |
| §12.3 / §12.4 gate | **GO** — 543 passed both modes, 9/9 verifiers, zero skip/xfail, 94 tags | **N-173** (quantized CPU clock) |
| §88.8 item 5 (A5 residual) | **RATIFIED** (Ruling 1) — accepted residual, call-site guard remains the defence | A5 trusts declared windows |
| `§10.8` A1 / A5 | **PASS / PASS** | — |
| `§10.8` A2 / A4 | **NO / NO** — unchanged, still blocking a pre-2022 verdict | A2, A4 dividends, A4 max hold |

### 89.8 Work order

1. **Close N-173** (serves §12.4). Make the scaling guard resolution-aware: either time with a high-resolution counter on a quiet worker, or skip the ratio assertion when the 1,000-fill loop measures below two clock ticks, keeping both ceilings. Probe: `probe_n173` fails on the changed instrument (`the benchmark no longer uses process_time`) and the replacement must show the 5 µs/fill workload measuring near 1.0 on a coarse-tick host; the 250 µs and 2.5 ceilings stay.
2. **A2 — identity intervals reaching 2018-04-01** (serves Phase 3B-2, unchanged from §88.8 item 3). Probe: the A2 line prints `PASS` with a first row at or before 2018-04-01.
3. **A4 — dividends or a committed maximum-hold bound** (serves Phase 3B-2, §13.2, unchanged from §88.8 item 4). Probe: both A4 lines print `PASS` with the bound read from criteria.
4. **Record Ruling 1's residual at the next criteria revision** (documentation carry, no gate). The criteria comment should cite §89.5 so a reader of the YAML sees why A5 reads declared windows. Probe: none is required; the citation is the check.

### 89.9 What would falsify this verdict

- If the transposed pair of archives exits 0 from the coverage probe, N-171 is not closed; if the committed corpus exits 1, the closure broke the certificate.
- If any two-digit year outside 1990–2030 is accepted by `parse_bhavcopy_date`, or `cm13JUL2020bhav.csv.zip` stops yielding 1,392 EQ records, N-172 is not closed.
- If the parallel and sequential runs ever disagree on the suite count or on skip/xfail, §12.4 invariance is false and the speedup is a different suite.
- If a failing test can produce a gate pass under the tolerant decoder, or the ledger test can pass with an unregistered id, the two "same assertions" claims are wrong.
- If `time.process_time()` on the gate host advances in finer steps than 15.625 ms, or the 1,000-fill loop measures two or more ticks at a 5 µs/fill workload, N-173 is host-specific in the other direction and should be re-registered with that measurement.
- If a committed verdict's evaluated set is ever shown to reach before 2022-01-03 while declaring a 2022 window, Ruling 1's acceptance was wrong.
