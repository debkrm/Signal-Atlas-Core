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
