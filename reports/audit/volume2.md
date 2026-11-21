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
## §90 — Audit of `fb02eea` (tag `feat-s90-fb02eea`): the pooled clock closes N-173, the timing guard still cannot see a linear scan, and the interval table seats 1,206 trade-to-trade ISIN-sessions in the EQ universe

**Date:** 18 November 2026
**Commit under review:** `6e11d91` (4 files, +200/−67: the replay benchmark pools its measurement over whole passes, `probe_n173` is flipped, the state note records §89 items 1–5), plus `fb02eea` (the implementer's `CURRENT_STAGE_OF_WORK.md` note; it carries the tag, and it changes no source path — the gate projects the same tree hash, `b90a9393…`, as `6e11d91`).
**Verdicts:** **N-173 CLOSED** · **N-174** registered `OPEN` (LOW — the timing guard cannot see the regression it names) · **N-175** registered `OPEN` (HIGH — the interval table's `series` attribute contradicts the archives, and the EQ-only entry gate consumes it) · A2, A4 dividends and A4 max-hold **correctly held back** and all invariants **unchanged** · criteria stays **1.1.11** (no re-pin was needed and none was made) · the retrieval that blocked A4 dividends now has a **measured admissible path** · **Rulings 1 and 2** appended

### 90.1 Baseline re-measured at `fb02eea`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite invocation the gate chose | `-m pytest -n auto --dist loadfile -q` |
| Suite under the gate | **543 passed** in **52.67 s** (gate total 53.78 s), **0 skipped / 0 xfailed** |
| Verifiers | 9/9 exit 0; W0.5-1c index reproduces (**89** sections); W0.5-2 executes **25/25** ledger probes; W0.5-5 **985** current / **23** superseded |
| Tags | **96** total, all verified (W0.5-4 PASS), `feat-s90-fb02eea` → `fb02eea` |
| Green cache | **22** rows; the tree this commit projects is already recorded at `6e11d91` (`suite_count` 543), so the gate printed `already recorded; not appending a duplicate row` — the `fb02eea` change is a document, not a source path |
| Findings ledger before this round | **40** rows / **25** ids (last: N-173 `OPEN` §89) |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931` |
| `probe_pre2022_preconditions.py` | **exit 1** — A1 **5/5 PASS** (246/245/252/248 + provenance digest), A5 **PASS** (8 artifacts, 0 of 4,903), A2 **NO** (4,510 rows begin 2022-01-03, 0 reach 2021-12-31), A4 dividends **NO** (0 of 138 ex-dates), A4 max hold **NO** |
| `probe_n171` / `probe_n172` / `probe_n173` | PASS / PASS / PASS (all three assert their closures) |
| Criteria / pins | **1.1.11**, `MAN-FPR-V1-7131c213…`, `CAL-FPR-V1-6acb5f45…`, `2d5ac7ac…`, binding **2022-01-03** |
| Trials / fold / holdout | **N = 9**, `N_eval = 5`, registry manifest `3326b1b2…`; 2024 validation fold `2024-01-01..2024-12-31` frozen; holdout `2025-01-01..2026-11-11` sealed (`configs/partition_spec.yaml`, token hash all-zero) |
| Files the range touches | **4** — `tests/unit/test_portfolio.py`, `scripts/probe_audit_findings.py`, `CURRENT_STAGE_OF_WORK.md`, `data/reference/source_tree_green.json`; none under `configs/`, `data/trials/`, `data/raw/`, `reports/verdicts/` |

### 90.2 N-173 — CLOSED, on the measurement the finding asked for

The benchmark no longer times one pass per size. `measure(fill_count)` builds a fresh portfolio per pass, times only the fill loop, and accumulates whole passes until the pooled CPU time exceeds `MIN_MEASURABLE_CPU_S` (0.25 s) or `MAX_PASSES` (20), then divides by the work it actually timed. Attacked in a detached worktree at `fb02eea` (`/tmp/s90w`, `PYTHONPATH` pointed at its `src` so the injected code is the code under test):

| Attack | Result |
|---|---|
| Restore the parent instrument (`37ebf90` test file), pooled constants absent | `probe_n173` **exit 1** — `FAIL N-173: the benchmark no longer sizes its measurement, so N-173's quantized single pass is back` |
| Unmodified instrument, 5 samples | 1k **44.3–50.0 µs/fill** over **5–6 passes** (0.25–0.28 s pooled); 4k **50.8–74.2 µs/fill**; ratio **1.15–1.50**; test passes in 1.32–1.56 s |
| Disable the pooling loop but keep both constants (`while passes < 1 and passes < MAX_PASSES and …`) | `probe_n173` **PASS** (it is a shape check) · the test **fails closed** — `the 1,000-fill figure pools only 0.047 s of CPU over 1 pass(es), which a clock ticking at 15.625 ms cannot resolve`, `assert (0.046875 >= 0.25 or 1 == 20)` |
| Add a uniform **+400 µs/fill** cost (still O(1)) | test **fails** — `Per fill 1k time too high: 250.00 µs` |
| Ceilings | the two `250.0` assertions and `< 2.5` are byte-identical to `37ebf90` (context lines in the diff, no touch), and `probe_n173` asserts all three strings |

Resolution, computed from the constants rather than assumed: the pooled 1,000-fill figure is quantised to `tick / (passes × 1,000)` = **2.6 µs** at 6 passes on a 47 µs base (**5.5 %**); at the pathological 5 µs/fill workload the `MAX_PASSES` escape gives 20 passes = 0.1 s = 6 ticks → **4.69 µs** per fill, 6.2 % low, inside the probe's 25 % bound. The floor `max(per_fill_1k_us, 1.0)` is therefore no longer load-bearing: it can only fire when the pooled figure is genuinely near zero, which now requires a workload three orders of magnitude cheaper than anything this engine does.

**Named residual.** `probe_n173` certifies the instrument's *shape* (constants, clock, ceilings) and the arithmetic of the pooling at three resolutions (host tick 15,625 µs, 15.625 ms, 1 µs); it does not execute the benchmark. The behavioural guard is the test's own `pooled_1k_cpu_s >= MIN_MEASURABLE_CPU_S` assertion, which was measured above to fail closed when the pooling is disabled — so the closure does not rest on the probe alone.

### 90.3 The guard still cannot see the regression it names — N-174 registered (LOW)

N-173's subject was the *measurement*; the guards it feeds were not re-attacked, so I re-introduced the defect the guard exists for. In the worktree, `Portfolio.process_fill` gained a linear scan over `self._processed_fill_instances` before any other work — the shape N-1 replaced with a dict membership test:

| Injected replay path | 1k µs/fill | 4k µs/fill | ratio | test verdict |
|---|---|---|---|---|
| Cheap scan, `_scan += 1.0` per entry (≈78 ns/entry) | 83.3 | 187.5 | **2.25** | **passes** |
| Comparison scan, `if _e == fill.order.instrument_id` per entry | 88.5–109.4 | 203.1–230.5 | **1.96–2.60** | **fails 3 of 5 runs, passes 2 of 5** |
| Uniform +400 µs/fill (O(1), for contrast) | 250.00 | 230.5 | 0.98 | fails the 250 µs ceiling |

The reason is arithmetic, not flakiness: the ceilings leave `250 − base` ≈ **200 µs of room per fill at 4,000 fills**, and a Python-level scan at ~78 ns/entry costs ~156 µs there, so an O(n) replay guard lands *inside* both ceilings. The ratio guard is not useless — it catches a genuinely quadratic cost — but it cannot certify the claim the test's docstring makes ("O(1) dict lookup"), and its verdict on a realistic reintroduction is a coin flip. This is test-only and performance-only (no correctness or accounting impact), so it is `LOW`; the remedy is a structural assertion (count the replay-path membership lookups and require one per fill) rather than a threshold move, which §12.4 forbids and which would only chase the host.

### 90.4 The interval table's `series` attribute — N-175 registered (HIGH)

This is where the round's item 2 stops being bookkeeping. Held-back A2 leaves `data/reference/cash_equity_symbol_intervals.csv` untouched, and the review asked whether "the 4,510 post-2022 rows" can be preserved. They cannot be preserved as they stand: the table's `series` attribute is contradicted by the archives it is derived from.

Measured with the repository's own `parse_bhavcopy_archive` (so the unified 2024+ header format is not my parser's problem) on six fixed post-2022 sessions — 2022-01-03, 2022-06-30, 2022-12-30, 2023-06-30, 2023-12-29, 2024-06-28 — joined as-of date T against the committed table:

| Measure | Result |
|---|---|
| Observations compared | **13,008** |
| ISIN disagreements | **0** — identity is right; `min_traded_eq_resolution_pct` 100 % holds |
| Observations with no covering interval | **0** |
| **`series` disagreements** | **1,356 / 13,008 = 10.4 %** — the observed series is absent from every interval covering T |
| Breakdown (2 sessions, 4,451 obs) | BE **341 / 346**, BZ **13 / 40**, SM **47 / 333** observations resolve to an `EQ` row |
| Distinct symbols affected (2 sessions) | **350** |

The failure has one shape: a single open-ended `EQ` row per symbol from 2022-01-03, so every later BE/BZ/SM session for that symbol is still described as EQ. The implementer's §89 report measured the same thing on the full corpus (186,996 of 1,646,985 = 11.4 %); my 10.4 % on six sessions is consistent and was taken independently.

Two consumers make this a gating defect rather than a documentation defect:

| Consumer | Measurement |
|---|---|
| `get_point_in_time_active_equities(T, intervals, series="EQ")` | of **1,336** ISIN-sessions that traded **only** BE/BZ on those six sessions, **1,206 (90.3 %)** are returned in the *EQ* universe for that same session |
| `SecurityMaster.resolve_symbol(isin, T).series` — the value `walkforward.py:637` feeds to Gate G2C-3's `is_eligible` | resolves to **`EQ`** for the same **1,206 of 1,336** |

So the §13.1 invariant "entry is permitted in `EQ` only" is enforced against a field that says `EQ` for nine out of ten sessions in which the scrip was in trade-to-trade. Gate G2C-3 (`Ineligible series MUST NEVER fill`) is not wrong — it is being asked the wrong question, with an answer that is stale by construction because the table records no series transition at all. This is a §5.1 (EQ vs BE settlement), §6.1/§10.5 (time-varying facts as half-open intervals joined as-of T) and §13.1 defect; it is `HIGH`, and it is why Ruling 2 below splits "unchanged" into evidence and attribute.

### 90.5 The three held-back items held the invariants — confirmed

| Item | Status in `6e11d91` | Measurement |
|---|---|---|
| A2 identity intervals to 2018-04-01 | **NOT DELIVERED** | table unchanged: **4,510** rows, earliest **2022-01-03**, **0** rows reach 2021-12-31; probe A2 `NO` |
| A4 dividends | **NOT DELIVERED** | **0 of 138** committed ex-dates fall in 2018-04-01..2021-12-31 (earliest 2022-03-29); no Bronze payload written |
| A4 max hold | **NOT DELIVERED** | no `max_hold_trading_sessions` and no `entry_date` on `Position`; probe `NO` |
| Criteria re-pin to 1.1.12 | **NOT MADE (correct)** | version **1.1.11**; `expected_manifest_fingerprint` `MAN-FPR-V1-7131c213…`; `expected_calendar_fingerprint` `CAL-FPR-V1-6acb5f45…`; `expected_sourced_window_calendar_fingerprint` `2d5ac7ac…`; `min_binding_evaluation_start_date` **2022-01-03**; trials **N = 9 / N_eval = 5**; registry manifest `3326b1b2…`; 2024 fold frozen; holdout sealed; A1/A5 **PASS**, A2/A4 **NO** |

Not re-pinning was the correct call, and the reason is a measurement rather than an opinion: no artifact was added, so the manifest the pin describes did not move, and a 1.1.12 that resealed an identical fingerprint would have been a version bump that certified nothing. The claim "criteria 1.1.12 preserved the invariants" is therefore best read as the weaker, true statement: **no criteria change was needed and none was made**, and the pins still describe the committed corpus.

**The blocked retrieval now has an admissible path — measured, not argued.** The implementer reported `HTTP 403` from a Python client while an interactive `curl` returned 200. Reproduced from this host on 18 November 2026, against `https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=01-04-2018&to_date=30-06-2018`:

| Probe | Result |
|---|---|
| `curl` without `-L` | **301**, 0 bytes (the endpoint answers on `www.nseindia.in`) |
| `curl -L` | **200**, **50,415 bytes** of JSON, effective URL `https://www.nseindia.in/api/…` |
| Landing page `https://www.nseindia.com/` first, cookie jar | landing **403**; the API still **301** without `-L` — the seed request is not what gates the payload |
| Two consecutive `curl -L` fetches | **byte-identical**, `sha256 3e6d41c1f0dbc78e…` — the payload is stable enough to attest |
| Schema | `symbol`, `series`, `isin`, `exDate`, `subject`, `comp`, `faceVal`, `recDate`, `bcStartDate`… — 161 records for 2018 Q2, of which **101** carry a dividend subject and **10** an ISIN/face-value change |

So the endpoint is not refusing the window, and it is not refusing non-interactive clients: it is refusing a request that does not follow the 301 to the `.in` host. That is a fact the work order can use, and it also means the corpus that unblocks A4 dividends is the same corpus A2 needs for its pre-2022 transitions.

**A2's backward extension has a measured prerequisite.** Extending intervals to 2018-04-02 requires identity boundaries inside the warm-up window that the committed corporate-action corpus does not document:

| Measure | Result |
|---|---|
| 2018-04-02 archive, symbols also present on 2022-01-03 | 1,523 (symbol, series) combinations |
| …whose ISIN **differs** from the 2022-01-03 row | **72** (e.g. `ALKYLAMINE` `INE150B01021 → INE150B01039`, `AMRUTANJAN` `INE098F01023 → INE098F01031`) |
| Already documented as `ISIN_TRANSITION` in `corporate_actions.jsonl` | **0** |
| Pre-2022-dated rows in that corpus | **2 of 485** (the corpus's 324 transitions are all ≥ 2022) |
| 2021-12-31 archive vs the 2022-01-03 rows | **0** ISIN differences among matched combinations — the seam at the binding start is clean, the transitions lie inside the warm-up window |

An extension built today would therefore either date 72+ transitions at the seam (false by measurement) or refuse to build. That, and not a stylistic preference, is why the A4-dividends retrieval is ordered ahead of A2 below.

### 90.6 Phase verdicts

| Phase | Verdict at `fb02eea` | Named residuals |
|---|---|---|
| §12.4 test invariant (N-173) | **CLOSED** — pooled measurement, ceilings untouched, resolution 5.5 % | probe is a shape check; the budget assertion is the behavioural guard |
| §12.4 test invariant (N-174) | **OPEN** — an O(n) replay scan passes 2 of 5 runs, and the cheap variant always | detection is timing-based, not structural |
| §5.1 / §13.1 entry eligibility (N-175) | **OPEN** — the EQ-only gate reads a series attribute that is EQ for 1,206 / 1,336 trade-to-trade ISIN-sessions | the table records no series transition at all |
| `§10.8` A1 / A5 | **PASS / PASS** | — |
| `§10.8` A2 / A4 | **NO / NO** — unchanged; the window stays warm-up, every pre-2022 verdict stays `NOT RUN` | A2 needs pre-2022 transitions; A4 needs the dividend corpus and a hold bound |
| Criteria and pins | **unchanged at 1.1.11** — no re-pin was required | — |
| Gate / cache | **GO** — 543 passed, 9/9 verifiers, reuse of `b90a9393…` at `6e11d91` is the accepted §81.4 cost | — |

### 90.7 Ruling 1 — `probe_n158`'s 324 is a measured count of documented transitions, never a frozen numeral

*Evidence:* at `fb02eea`, `adjacent_identity_pairs(load_cash_universe_symbol_intervals())` returns **324** over **4,510** rows, and `validate_documented_transition_dates` returns 324 — every pair dated at its `ISIN_TRANSITION` ex-date, with `TATASTEEL` at 2022-07-29. The corpus that dates them holds **485** rows, of which **2** are pre-2022. The implementer's §89 round measured that a series-aware key yields **426** pairs and reverted rather than edit the constant.

*Ruling:* the invariant `probe_n158` enforces is **per pair**: every adjacent identity boundary is dated at a documented transition, and a drifted row is refused. The numeral **324** is the count of such boundaries in the corpus as committed, not an independent invariant. A change that *adds* correctly documented boundaries (a backward extension, a series-aware key) must report the new exact count and re-pin it as a measurement; a change that *loses* or *mis-dates* any of the 324 is a regression regardless of the numeral. Hand-editing 324 to 426 in the probe is forbidden; appending a section that measures 426 and cites why is the permitted route.

*It does not change:* the datedness requirement, the refusal of a drifted transition, the 4,510 post-2022 rows' pair tuples (all 324 must survive unchanged), or any threshold.

*Work item:* §90.9 item 3, serving Phase 3B-2. *Probe:* `probe_n158` continues to assert `len(pairs) == 324` and per-pair dating until the re-measure lands; after it, the probe asserts the freshly measured count and the same per-pair dating, and any interim tree where a pair is lost fails it.

*Falsified by:* any tree where the 324 tuples are not a subset of the pairs the probe validates, or where a pair is dated away from its documented ex-date.

### 90.8 Ruling 2 — "unchanged" protects the evidence, not an attribute its own archive contradicts

*Evidence:* §90.4 — 10.4 % of 13,008 observations disagree on `series`; 90.3 % of trade-to-trade ISIN-sessions resolve to `EQ` in the security master and in the EQ universe.

*Ruling:* an instruction to preserve the post-2022 rows protects **(a)** every ISIN boundary and its date, **(b)** every `(isin, symbol)` chain the 324 pairs are read from, and **(c)** the row count as evidence of what was committed. It does **not** protect a `series` value that the session's own archive contradicts. Such a row is corrected by an **append**: a new interval with its `effective_from`/`effective_to` and the session archive(s) that establish it, leaving the superseded row in place as history (§10.1). No interval is edited or deleted, and no correction is derived from the present constituent list or from a symbol's later `EQ` state (§6.1, §10.5).

*It does not change:* append-only storage, the ISIN-keyed identity rule, the pair tuples of Ruling 1, or any criteria threshold — a series row is a fact, not a threshold.

*Work item:* §90.9 item 1, serving Phase 3B-2 and §13.1. *Probe:* `probe_n175` currently asserts the disagreement (1,336 trade-to-trade ISIN-sessions, 1,206 resolving to `EQ`); at closure it must assert **0 of 1,336**, and `probe_n158` must still validate every one of its pairs at the new count.

*Falsified by:* a corrected table where any of the six sampled sessions still returns a BE/BZ-only ISIN in the EQ universe, or one where a superseded row was deleted instead of appended.

### 90.9 Work order for feat-s91

Ordered by what it unblocks. Each item names the probe that must fail closed before the item is closed.

1. **N-175 — correct the `series` attribute by append** (serves Phase 3B-2 and `§13.1`; `HIGH`). Derive a `(isin, symbol, series)` interval chain from the committed archives' own `SERIES` column, date every transition at the first session the new series appears, append rows rather than editing the 4,510, and re-derive the EQ universe from it. Do not touch the pair tuples of Ruling 1. **Probe:** `probe_n175` must read **0 of 1,336** (it reads 1,206 today) and `probe_n158` must still date every pair at its documented transition. **Residual to report:** the pair count moves off 324, with the new exact count and the rows that create it.
2. **A4 dividends and the pre-2022 corporate-action corpus** (serves Phase 3B-2, §13.2). Capture `2018-04-01..2021-12-31` quarter by quarter through the measured recipe — `curl -L` to the `www.nseindia.in` host, one byte-exact Bronze payload per quarter, one manifest row per payload carrying `source_url`, the redirect's effective URL, `retrieved_at`, `byte_count` and `sha256` (§10.7). Cached bytes committed, because CI has no network (§12.5). Parse dividends (`exDate`, `subject`, `isin`) and `ISIN_TRANSITION`/face-value rows from the same payloads. **Probe:** the `A4 dividends` line must print `PASS` with a non-zero count of warm-up ex-dates and no fabricated date; a payload whose digest does not match its manifest row must fail closed.
3. **A2 — identity intervals back to 2018-04-02** (serves Phase 3B-2). Extend backward over the 931 warm-up sessions, leave all 4,510 post-2022 rows byte-identical, and date each of the 72+ warm-up boundaries from item 2's corpus — never at the 2022-01-03 seam. A boundary that is a delisted-and-reused symbol is pruned, not stitched (§10.4). **Probe:** the A2 line prints `PASS` covering all 931 window sessions, `probe_n158` validates every pair at its documented date under the Ruling 1 count, and a run that dates a transition at the seam exits 1.
4. **A4 max hold — a bound with an enforcement point** (serves Phase 3B-2, §13.2). Authorised: add `entry_date` to `Position`, carry it through the single ledger, and enforce `max_hold_trading_sessions` read from `configs/go_no_go_criteria.yaml`, counted in authoritative calendar sessions (§6.3). A hold that cannot exit inside the bound because of a lower-circuit freeze is a `NOT RUN`/refusal, not a silent extension (§5.3). The bound is declared before any run, uses only the training/validation windows, and **no existing post-2022 trial outcome may move** — the 8 verdict artifacts must be byte-identical afterwards. **Probe:** the `A4 max hold` line prints `PASS`, and a synthetic position held one session past the bound must be refused.
5. **N-174 — make the O(1) claim structural** (serves §12.4; `LOW`). Assert the replay path's membership lookups directly (one per fill, independent of how many instances the guard holds) instead of inferring O(1) from a ratio, keeping the 250 µs ceilings and the 2.5 ratio as coarser performance bounds. **Probe:** `probe_n174` must assert the structural check exists and the ceilings are unchanged; the acceptance attack is the linear scan of §90.3 failing **5 of 5** runs.

### 90.10 What would falsify this verdict

- If `time.process_time()` on this host resolves a 1,000-fill loop that costs under 7.8 µs/fill into anything other than 0.0, or if the pooled figure's resolution exceeds 10 % at the measured 44–50 µs base, N-173 is not closed.
- If `probe_n173` passes with the pooling loop degenerated to one pass (measured: it does), the probe's role must be described as shape-only, and the closure then rests entirely on the test's budget assertion — which measured as failing closed.
- If a reintroduced O(n) replay scan makes the benchmark fail deterministically on any host, N-174 is wrong as stated and should be re-measured rather than re-scoped.
- If any of the six sampled sessions returns 0 series disagreements after this round without a table change, my N-175 measurement was an artifact of the join; if a corrected table still returns a BE/BZ ISIN in the EQ universe, the correction is incomplete.
- If the interval table's rows are edited in place rather than superseded by append, Ruling 2 was misapplied and §10.1 was violated.
- If a warm-up transition is dated at 2022-01-03 for want of a source, A2 is fabricated and Ruling 1 does not apply to it.
- If any existing post-2022 trial outcome, verdict artifact, criteria fingerprint, fold or holdout seal moves in feat-s91, the invariant table in §90.5 was describing the wrong tree.
## §91 — Audit of `abf198f` (tag `feat-s91-35e2050`): the interval log is corrected by append and N-175 closes, the new replay counter cannot see the scan it was added for, and the warm-up window becomes gating-eligible

**Date:** 18 November 2026
**Commit under review:** `35e2050` (42 files, +28,810/−92: two new derivation scripts, the interval log and its restatement evidence, 15 Bronze corporate-action payloads, the append-only resolver and its bisect index, `max_hold_trading_sessions`, and the regenerated 1.1.12 artifacts), plus `abf198f` (the green-cache row, +19 lines, no source path — the gate projects the same tree hash `457d2691…` at both).
**Verdicts:** **N-175 CLOSED** · **N-174 PARTIAL** — the structural counter the fix added passes with the regression installed, so no CLOSED row was written and the finding stays `OPEN` · **N-176** registered `OPEN` (MEDIUM — Gate COV-3's attribution is typed prose and three of its four numbers are wrong) · **N-177** registered `OPEN` (MEDIUM — the hold bound is declared, modelled and unit-tested, and no production path calls it) · A4 dividends **PASS**, A2 **PASS**, A4 max-hold **declared, unenforced**, A1/A5 **PASS** · criteria **1.1.12**, 27 criterion rows and 5 trial evaluations unchanged · **Ruling 1**: `2018-04-01..2021-12-31` (931 sessions) becomes gating-eligible, candidate seq 10 is authorised to register `2018-04-01..2023-12-31` in-sample, the 2024 fold stays frozen and `2025-01-01..2026-11-11` stays sealed

### 91.1 Baseline re-measured at `abf198f`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite invocation the gate chose | `-m pytest -n auto --dist loadfile -q` |
| Suite under the gate | **544 passed** in **53.38 s**, **0 skipped / 0 xfailed** (543 at `fb02eea`; the difference is `test_max_hold_bound_refuses_the_session_past_it`) |
| Verifiers | **9/9 exit 0** — `verify_audit_findings` 85.53 s, `verify_cash_universe_coverage` 38.09 s, `verify_historical_snapshot` 5.46 s, `verify_phase2a_containment_and_trials` 1.26 s, `verify_phase2b5_storage` 2.60 s, `verify_phase2b_significance` 0.91 s, `verify_phase2c_walkforward` 2.69 s, `verify_phase2d_verdicts` 3.92 s, `verify_wave1_thin_slice` 4.65 s |
| W0.5-1c / W0.5-4 / W0.5-5 | index reproduces at **90** section rows; **98** tags verified, `feat-s91-35e2050` → `35e2050`; **1,000** current manifest artifacts match byte count and sha256, **26** superseded rows skipped as history |
| Green cache | tree `457d2691…` is already recorded at `abf198f`, so the forced run printed `already recorded; not appending a duplicate row`; `git status` clean before and after |
| Findings ledger before this round | **43** rows / **27** ids; **3** open — N-150 (MEDIUM), N-174 (LOW), N-175 (HIGH) |
| Criteria / pins | **1.1.12**, `MAN-FPR-V1-e95ddf90…`, `CAL-FPR-V1-6acb5f45…`, sourced-window `2d5ac7ac…`, `min_binding_evaluation_start_date` **2022-01-03**, `max_hold_trading_sessions` **21** |
| Trials / fold / holdout | **N = 9**, `N_eval = 5`, registry manifest `3326b1b2…`; 2024 fold `2024-01-01..2024-12-31` frozen; holdout `2025-01-01..2026-11-11` sealed, token hash all-zero, no `HOLDOUT_UNLOCK` sentinel |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931`, each archive's own session date equal to its row, `WARMUP_NOT_GATABLE` on every row |
| `probe_pre2022_preconditions.py` | **exit 0** — A1 **5/5 PASS** (246/245/252/248 + digest `7622fbf4…`), A2 **PASS** (17,864 active of 19,283 committed, earliest 2018-04-02 = the window's first session, all **931** sessions covered), A4 dividends **PASS** (**4,357** ex-dates, 2018-04-03..2021-12-30), A4 max hold **PASS** (`=21 is committed`), A5 **PASS** (8 verdict artifacts = every `*.json` under `reports/verdicts/`, 0 of 4,903 evaluated sessions precede 2022-01-03) |
| Ledger probes | N-171, N-172, N-173, N-174, N-175, N-176, N-177 all PASS; the 24 other executed probes pass inside `verify_audit_findings` |
| Files the range touches | 42; **no** path under `data/trials/`, `configs/partition_spec.yaml`, `data/raw/2025/`, `data/raw/2026/`; `reports/verdicts/` changes **2** files by **2** lines each |

### 91.2 N-175 — CLOSED, on the measurement §90.8 said would falsify the non-closure

§90.8's closure test was explicit: **0 of 1,336** trade-to-trade ISIN-sessions may resolve to `EQ`, and the corrected table must be an append, never an edit. I re-measured it with my own join, on the six fixed sessions, using the repository's `parse_bhavcopy_archive` and `SecurityMaster.resolve_symbol` — and, separately, against a brute-force oracle over the active rows:

| Measure | `fb02eea` (parent) | `abf198f` |
|---|---|---|
| Trade-to-trade ISIN-sessions in the six archives | 1,336 | **1,336** (sample unchanged) |
| …resolving to `EQ` through `resolve_symbol` | **1,206** | **0** |
| …returned by `get_point_in_time_active_equities(…, series="EQ")` | **1,206** | **0** |
| …whose resolved series is one the archive actually shows | 130 | **1,336** |
| …unresolved (`None`) | 0 | **0** |
| EQ ISIN-sessions / resolving `EQ` / in the EQ universe | 10,849 / 10,849 / 10,849 | **10,849 / 10,849 / 10,849** |

The last two rows are the ones that decide the finding rather than the probe. `probe_n175` asserts only `admitted == 0` and `universe_admitted == 0`, so a "correction" that resolved those 1,336 scrips to nothing at all would satisfy it; I measured the stronger properties instead, and the table answers correctly, not merely non-`EQ`: every one of the 1,336 resolves to a series its own session archive shows, and the 10,849 `EQ` ISIN-sessions are untouched by the correction. The over-correction risk (a restatement that eats an `EQ` span) is the one the commit message says it fixed, and §91.3 attacks it directly.

**Append, not edit (§10.1, §90.8 Ruling 2).** `git diff --numstat fb02eea..35e2050` reports `14773 0` for `cash_equity_symbol_intervals.csv`: 14,773 added lines and **no** removed line, and the first **4,511** lines (header + the 4,510 committed rows) hash to `b7a08976994a35fb…`, byte-identical to the parent file. The evidence file `cash_equity_symbol_interval_restatements.jsonl` is new: **7,989** rows over **1,380** ISINs / **1,419** `(isin, symbol)` chains, each naming the row it supersedes and the first and last archive (with sha256) that establish it. No superseded row was deleted.

**Ruling 1 of §90.7 is satisfied by measurement, not by editing the numeral.** `adjacent_identity_pairs` now returns **426** = **324** post-2022 `+` **102** warm-up, every one dated at a documented `ISIN_TRANSITION`; the parent's **324** tuples were extracted at `fb02eea`, compared as a set against the new pairs, and **324 of 324** survive. `probe_n158` asserts both the 324 subset and the 426 total rather than the old flat numeral.

**Residual named, not implied.** `probe_n175` is a two-sided sample check and, as written, admits a vacuous pass; the closure therefore rests on the measurements above rather than on the probe (the same relationship §90.2 recorded for N-173). Second residual: the restatement derivation reads the holdout-era archives — **2,710** of the 7,989 rows are dated 2025-01-01..2026-10-30, and the parent table already carried **1,180** rows dated `>= 2025-01-01`, so this is an increase in volume of an existing practice, not a new access. The rows carry series and identity only — no price, no return, no verdict — the seal, the token hash and the 2024 fold are untouched, and no metric can read a 2025 or 2026 session through a point-in-time join over an earlier date. It is recorded here because a reader of §88's "no path under `data/raw/2025` or `2026`" rows would otherwise be surprised by the span.

### 91.3 The resolver's remainder clipping — attacked directly, because it is the repair most likely to be additive

The commit's own claim is that a partly-restated row keeps the span the append did not cover, and that the old behaviour deleted `EQ` spans (`INE704P01025`, `INE144J01027`). A repair of that shape is exactly the additive fix §14.4 warns about — a new guarded path beside the unguarded one — so I drove `apply_interval_restatements` and `SecurityMaster.resolve_symbol` with synthesised logs at `abf198f`:

| Attack on the append-only log | Result |
|---|---|
| `EQ 2022-01-03..` then `BE 2022-01-03..2022-01-10` | active rows `BE 01-03..01-10`, `EQ 01-10..` — the uncovered remainder survives; `resolve_symbol` returns `BE` on 01-04 and `EQ` from 01-10 |
| `EQ …01-03..01-20`, `SM …01-20..01-25` inside a longer span | three contiguous runs, no gap, no duplicate; `EQ` at 01-25 and 01-26 |
| Two contained appends cutting a middle window | five rows, the `EQ` remainder present on **both** sides of the cut (`…01-03..02-01`, `…03-01..05-01`, `…06-01..`) |
| Full-span restatement | the superseded row is dropped from the active set and the append answers alone |
| Append that is **not** contained (`EQ 2022-03-01..` and `BE 2022-01-03..2022-06-01`) | `SecurityMasterError` — `Overlaps … without being an append that restates a part of it (§10.1)` |

The real corpus exercises the same path: `INE144J01027` (`20MICRONS`) is `EQ 2022-01-03..2023-06-23`, `BE 2023-06-23..2023-11-28`, `EQ 2023-11-28..2024-10-09`… A whole-row supersede would have erased the pre-2023-06-23 `EQ` identity; with clipping, `resolve_symbol` returns `EQ` on 2022-06-01 and 2023-06-01 and 2024-01-16. This is why the finding closes on 1,336 correct rather than 1,336 merely non-`EQ`.

**The bisect index is answer-preserving.** §90.9 item 2 replaced an `O(ISINs × rows)` scan with `bisect_right` over per-series start dates. I compared it against a brute-force oracle over the active rows: `resolve_symbol` for every one of **4,583** ISINs on **353** dates spaced a week apart from 2018-04-02 to 2024-12-31 (**≈1.6 M** lookups) — **0** mismatches on the returned row's series or span, and `get_point_in_time_active_equities` on **71** of those dates — **0** set differences. The speed-up is therefore not bought with a changed answer. The universe loader's cache is keyed on `(id(intervals), len(intervals))` with an identity check and holds a strong reference to the sequence, so a recycled `id` cannot return another table's index.

### 91.4 N-174 — PARTIAL: the counter the fix added passes with the regression installed

§90.9 item 5 set its own acceptance: "the acceptance attack is the linear scan of §90.3 failing **5 of 5** runs". The fix adds a `CountingReplayGuard(OrderedDict)` whose `__contains__` increments a counter, and asserts `lookup_count == fill_count` at 1,000 and 4,000 fills. The two `250.0 µs` ceilings and `< 2.5` are unchanged — no assertion line touching them is added or removed between `37ebf90` and this commit (§90.2 measured them byte-identical) — and `probe_n174` PASSes. So I installed the regression.

In a detached worktree at `35e2050`, `Portfolio.process_fill` gained the per-fill scan over every instance the guard holds, before the membership test:

```python
        fill_addr = id(fill)
        for _seen in self._processed_fill_instances:
            if _seen == fill_addr:
                break
        if fill_addr in self._processed_fill_instances:
```

| Run | Verdict |
|---|---|
| 1 | **failed** (timing) |
| 2 | passed |
| 3 | passed |
| 4 | passed |
| 5 | passed |

**1 of 5.** Not 5 of 5. And the reason is structural, not flaky: iterating an `OrderedDict` never calls `__contains__`. Measured under the same injection, the new assertion's counter reads exactly **1,000 for 1,000 fills** — the structural check passes while a scan of every held instance runs on every fill. The count certifies "the replay path performs one `in` test per fill", which the regression does not change; it does not certify `O(1)`.

That is the additive fix in miniature: a guarded measurement was added beside the timing guard, and the property that actually regresses is invisible to both. The finding is **PARTIAL**, the section's work order item 3 asks for a counter over *every* access to the guard (iteration, `keys`, `values`, `get`, `__contains__`) rather than one dunder, and **I did not write the CLOSED row the round asked for** — the acceptance test it was conditioned on measured 1 of 5, and §9.1 does not let a probe that passes for the wrong reason stand in for a verdict. The ledger's N-174 row remains `OPEN`; no append was made.

### 91.5 Gate COV-3 under §12.4 — the counts conserve, the attribution does not describe the archive (N-176)

The gate's hard assertions are exact equalities, and I reproduced all five from `sec_list_20240116.csv` and the session's own Bhavcopy, independently of the gate: **3,624** total rows, **2,763** in-scope `EQ`, **861** out-of-scope non-`EQ`, **1,174** unresolved, **1,589** extracted. At the parent the same instrument reads **924** unresolved / **1,839** extracted, so the 250 scrips moved from "extracted" to "unresolved" because they were in trade-to-trade on that session, exactly as the commit message says.

| Attribution of the 1,174 unresolved, measured here | Count |
|---|---|
| No row at all in the 2024-01-16 Bhavcopy (identity begins at first trade, §40.5) | **933** |
| Traded in `BE` on the session | **221** |
| Traded in `BE`/`BZ` on the session | **3** |
| Traded in `SM` (another non-`EQ` series) | **17** |
| **Reported as `EQ` by the Bhavcopy and unresolved — the invariant that matters** | **0** |
| Sum | **1,174** ✓ |

The gate prints `"[INFO] 1,174 unresolved EQ scrips … 930 untraded …, 220 trading in BE and 24 in another non-EQ series"`. Those three numbers are **literals inside a `print`**, and three of the four disagree with the archive: 933, not 930; 224 trade-to-trade, not 220; 17 other non-`EQ`, not 24. The totals conserve, so nothing about the counts is misstated — but §9.1 ("verdicts are computed, never typed") is about exactly this, and the one claim in the paragraph that would matter as evidence — **0** Bhavcopy-`EQ` scrips fail to resolve — is asserted in no code at all. It is true; I measured it; the gate does not know it. **N-176 registered (MEDIUM)**; `probe_n176` recomputes the split and asserts both the typed literals and their disagreement with the Bhavcopy, so it fails closed the day the gate starts printing what it computed.

**Is `924 → 1,174` a weakened gate (§12.4)?** No, and the ceiling is live rather than slack: `max_unresolved_threshold` is pinned at **1,174** in COV-4 and the parser refuses at **1,173** (`Unresolved in-scope (('EQ',)) ISINs (1174) exceeded allowable threshold 1173`) and accepts at 1,174 and 1,175. The operative gate is the exact equality in COV-3, which is tighter than either ceiling, and the 250 that raised the ceiling are scrips that the table no longer misdescribes as `EQ`. Raising a ceiling to the measured truth while tightening an equality beside it is not the §12.4 failure mode; the failure mode would have been widening the equality.

### 91.6 A4 dividends, A2 backward extension, the 1.1.12 artifacts, and A4 max-hold

| Item | Measured at `abf198f` | Verdict |
|---|---|---|
| **A4 dividends — capture** | **15** payloads under `data/raw/corporate_actions/`, one per quarter 2018-04-01..2021-12-31, **8,500** records; every payload attested by `byte_count` **and** `sha256` against its current manifest row; `source_url` on `www.nseindia.com`, `effective_url` on `www.nseindia.in`, `redirect_count` **1**, `retrieved_at` 2026-11-18; provenance `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` — correctly **not** promoted to VERIFIED (§6.5) | **PASS** |
| **A4 dividends — corpus reproducibility** | `data/reference/corporate_actions.jsonl` is **5,016** rows, `sha256 6ff7d3edb577a64d…`. A direct call to `generate_corporate_actions_corpus()` returns 5,016 rows from 4,440 derived / 4,429 merged warm-up rows, and `scripts/derive_2022_2024_corpora.py` rewrote the file to that exact digest. All **485** pre-existing rows survive byte-identically as lines (the file is sorted by ex-date, so they are not a prefix), **0** duplicates, **0** deletions | **PASS** |
| **A4 dividends — no fabricated date** | **4,357** `DIVIDEND` rows in 2018-04-01..2021-12-31 (4,495 overall, so the 138 post-2022 rows are untouched by the extension); **4,357 of 4,357** trace to an `(isin, exDate)` pair in one of the 15 payloads; **0** untraceable | **PASS** |
| **A4 dividends — fail-closed** | Mutating **one byte** of `NSE_CA_equities_2018-04-01_2018-06-30.json` makes `check_reference_manifest_integrity()` return False and name both digests (`…1967cd68… on disk but the manifest attests 465fdec5…`) | **PASS** |
| **A2 backward extension** | **931** calendar sessions in the window, **931** covered; **17,864** active rows of **19,283** committed; earliest active row **2018-04-02** = the window's first session; **426** identity pairs, **426** dated at a documented transition, **324** post-2022 tuples preserved | **PASS** |
| **A4 max hold — declaration** | `max_hold_trading_sessions: 21` committed; `Position.entry_date`, `holding_sessions` (authoritative-calendar count, refusing an unscheduled date) and `require_within_hold_bound` exist; the unit test drives 0 / 20 / 21 and the refusal message; the ledger's entry date is set only on the flat→long transition and cleared on close | **declared** |
| **A4 max hold — enforcement** | **No production caller.** A repository-wide search finds `require_within_hold_bound(` only in `position.py` (its definition) and `tests/unit/test_portfolio.py`. The A4 probe line asserts only `max_hold_trading_sessions=21 is committed`, so a simulated position can be carried past the bound with nothing refusing it | **N-177 registered (MEDIUM)** |
| **Criteria 1.1.12** | version **1.1.12**, `MAN-FPR-V1-e95ddf90…` (resealed over the grown manifest), calendar and sourced-window fingerprints unchanged, every numeric threshold byte-identical except the one new binding `max_hold_trading_sessions: 21`; `min_binding_evaluation_start_date` still **2022-01-03** | **unchanged invariants** |
| **Phase 2D artifacts** | **27** evaluations, `PASS=2 FAIL=0 NOT_RUN=25`, overall `NO-GO`, window `2022-01-03..2026-10-30`; the two regenerated files changed **4 lines total** — `criteria_version` and `criteria_fingerprint` — and no evaluation row moved. `data/trials/` has **no** diff: 9 registry rows, `evaluation_count 5`, pin `3326b1b2…`; `reports/verdicts/trial_004..009` untouched | **PASS** |

Two residuals, named rather than implied.

1. **The artifact now names a criteria version that post-dates its own timestamp.** `phase2d_tier_a_2022_2026_verdict.json` keeps `timestamp_utc 2026-11-16T10:00:00+00:00` and now carries `criteria_version 1.1.12` / `CRIT-FPR-V1-50784f1a…`, while 1.1.12 is effective **2026-11-18**. The reseal is *forced* — `verify_phase2d_verdicts` compares the artifact's fingerprint to the loaded criteria, so leaving 1.1.11 would have failed the gate — and it is honest in the sense that matters (no threshold moved, so no evaluation row moved, and the timestamp still names when the numbers were computed). But a reader cannot tell from the artifact that the 25 `NOT RUN` rows were produced under 1.1.11. The 1.1.12 note in `configs/go_no_go_criteria.yaml` records that, which is why this is a residual and not a finding.
2. **The corpus generator is not idempotent on the manifest.** `main()` demotes the current `corporate_actions.jsonl` row and appends a new one whose digest is identical, so a second run leaves **1,027** manifest lines instead of 1,026, a duplicate superseded row pointing at the same bytes, and `MAN-FPR` moved off the pin (`12a45c57…` against `e95ddf90…`). That is the append-only restatement working as designed (§10.1) rather than an edit, but it means *any* regeneration is accompanied by a re-pin, which the next round must expect rather than discover.

### 91.7 Phase verdicts

| Phase | Verdict at `abf198f` | Named residuals |
|---|---|---|
| `§5.1` / `§13.1` entry eligibility (N-175) | **CLOSED** — 0 of 1,336 trade-to-trade ISIN-sessions resolve to `EQ`, 1,336 of 1,336 resolve to a series their own archive shows, 10,849 `EQ` ISIN-sessions unaffected | `probe_n175` admits a vacuous pass; closure rests on §91.2's independent join |
| `§6.1` / `§10.5` interval log | **append-only and answer-preserving** — 14,773 added lines, 0 removed, 4,511-line prefix byte-identical, bisect index equal to a brute-force oracle on ≈1.6 M lookups | restatement evidence spans into the sealed holdout era (series/identity only) |
| `§12.4` test invariant (N-174) | **PARTIAL** — the structural count reads 1,000/1,000 with a per-fill scan installed; the regression fails the benchmark **1 of 5** runs | detection is still timing-based; the counter watches one dunder |
| `§12.4` gate invariant (Gate COV-3, N-176) | **counts PASS, attribution OPEN** — 3,624/2,763/861/1,174/1,589 reproduced exactly; ceiling live at 1,174; the printed 930/220/24 are typed and the measured split is 933/224/17 | the `0 EQ unresolved` claim is measured, not asserted |
| `§10.8` A1 / `§10.8` A5 | **PASS / PASS** — 4 sourced circular years, 8 artifacts, 0 of 4,903 pre-binding sessions | — |
| `§10.8` A2 / A4 dividends | **PASS / PASS** — 931/931 sessions, 426 dated pairs, 4,357 traced ex-dates | pair count moved 324 → 426 by measurement under §90.7 Ruling 1 |
| `§13.2` A4 max hold | **declared, modelled, unit-tested, unenforced** | N-177; the bound has no consumer in the single engine |
| Criteria and pins | **1.1.12** — new binding pre-registered, manifest resealed, no threshold moved, 27 rows and 5 evaluations unchanged | Phase 2D artifacts carry a version newer than their timestamp |
| Gate / cache | **GO** — 544 passed, 9/9 verifiers, tree `457d2691…` reused at `abf198f` with no duplicate row | — |

### 91.8 Ruling 1 — the 931 warm-up sessions are gating-eligible on a sourced calendar and a corrected identity log, and on nothing else

*Evidence (all measured at `abf198f`, §91.1 and §91.6):* A1 **5/5 PASS** — 246/245/252/248 sessions per year reproduced from 7 sourced circular artifacts (1 + 3 + 2 + 1) with provenance digest `7622fbf4…`; A2 **PASS** — 17,864 active rows of 19,283 committed, earliest **2018-04-02** = the window's first session, **931 of 931** sessions covered, **426** identity pairs each dated at its successor ISIN's first session, the **324** post-2022 tuples preserved intact; A4 dividends **PASS** — **4,357** ex-dates in the window, every one traceable to one of 15 byte-attested Bronze payloads; A5 **PASS** — 8 verdict artifacts (every `*.json` under `reports/verdicts/`), **0 of 4,903** evaluated sessions precede the binding start; `configs/partition_spec.yaml` already names `in_sample_start: 2018-04-01`, so the binding start is the one value that lagged the committed partition. The surveillance frameworks the §10.8 window is defined against existed for the whole window — GSM effective 2017-03-14, ASM effective 2018-03-26 — so no session in `2018-04-01..2021-12-31` predates them.

*Ruling:* the 931 sessions `2018-04-01..2021-12-31` move from `WARMUP_NOT_GATABLE` to **gating-eligible**. Concretely, in one round: `min_binding_evaluation_start_date` becomes **2018-04-01** in criteria **1.1.13**; `signal_core/storage/gating.py:BINDING_EVALUATION_START_DATE` becomes 2018-04-01 — the module constant and the criteria value are two sources for one fact and must move together or the guard and the criteria disagree; the **931** manifest rows now reading `gating_mode: WARMUP_NOT_GATABLE` are superseded by an **append**, never edited, with `MAN-FPR` re-pinned over the grown manifest; `probe_pre2022_bronze_coverage.py`'s hard requirement that those rows read `WARMUP_NOT_GATABLE` becomes a requirement that the label agrees with the criteria' binding start, so a tree whose criteria move while its archive labels stay cannot pass; and A5's rule is re-read against the new start. Candidate **seq 10** is authorised to register `2018-04-01..2023-12-31` as its in-sample window with the **2024** fold as its validation window, pre-registered in the trial registry **before** any run (§8.2), taking `N` from 9 to 10 without touching the five recorded evaluations.

*What it does not do.* It moves no numeric threshold, fold boundary, trial count, cost parameter or criterion (§9.2, §12.4); it does not unlock, preview, re-scope or summarise `2025-01-01..2026-11-11`, which stays sealed behind the all-zero token hash with no sentinel, and the restatement rows dated inside that era carry series and identity only (§91.2); it does not make 2024 a *second* validation fold — the fold count stays one, so **CRIT-OVERFIT-06 stays `NOT RUN`** under the still-open N-150 and no report may describe seq 10's overfitting tests as passing; it does not manufacture surveillance state — `surveillance_intervals.jsonl` holds **3** rows dated 2024-01-15..2024-03-01 over **3** ISINs, so **CRIT-B6 is `NOT RUN`** over the extended window exactly as it is over `2022-01-03..2024-12-31`, and the promotion grants the warm-up sessions the same input standing the old window has, no more; it does not repeal **N-177** — until the hold bound has a consumer a seq-10 run may hold past 21 sessions, so the hold-bound criterion is `NOT RUN` as well; and it authorises **no verdict**: a GO or NO-GO remains whatever the gate computes over the extended window, and on the committed artifacts that computation is `NO-GO`.

*The condition this round was asked to meet, measured rather than asserted.* The instrument was requested "with A1 + A2 + A4 + A5 at PASS and 0 open ledger findings". Measured: A1/A2/A5 and A4 dividends are PASS, A4 max-hold is **declared but unenforced**, and the ledger holds **4** open findings after this round — N-150 (MEDIUM, CRIT-OVERFIT-06's fold count), N-174 (LOW, the timing guard), and the two this round registered, N-176 and N-177. None of the four is a defect in the window's *inputs*: N-150 is a verdict-form rule, N-174 a test instrument, N-176 a gate's printed prose, N-177 a policy bound with no consumer. I am recording that deviation rather than resolving it by dropping the finding, because the alternative — closing N-174 on a probe that passes with the regression installed — is the failure mode this section exists to report.

*Work item:* §91.9 items 1–5, serving Phase 3B-2 and §10.8. *Probe:* `probe_pre2022_preconditions.py` must print A5 `PASS` against `min_binding_evaluation_start_date = 2018-04-01`, A2/A4 unchanged, and a session dated 2018-03-29 must still be refused by `assert_no_warmup_sessions_in_evaluation`; the manifest relabel must leave every Bronze digest intact (W0.5-5) and re-pin `MAN-FPR` by measurement.

*Falsified by:* any window session without a calendar row from a sourced circular; any identity pair dated at the 2022-01-03 seam or not dated at its successor's first session; any dividend row in the window not traceable to a Bronze payload; a criteria value moved while `gating.py`'s constant stays at 2022-01-03 (or the reverse); a fold, trial count, cost parameter, criteria threshold or holdout seal that moves with the promotion; or any seq-10 verdict computed over a 2025 or 2026 session.

### 91.9 Work order for feat-s92

Ordered by what it unblocks. Each item names the probe that must fail closed before it closes, and the phase it serves in `CURRENT_STAGE_OF_WORK.md`.

1. **N-177 — give the hold bound a consumer** (serves `§13.2` / Phase 3B-2; MEDIUM). Call `Position.require_within_hold_bound` from the single engine's session loop with the criteria value, so a hold that reaches the bound is refused at the exit-evaluation point, and a hold that cannot exit inside it because the bid is locked at the lower circuit records a refusal rather than an extension (§5.3). **Probe:** `probe_n177` flips to asserting a production call site exists; the acceptance attack is a synthetic position held one session past the bound, refused **without** a direct `Position` call, and the A4 line must print a refusal count that is non-zero when one occurs.
2. **N-176 — compute Gate COV-3's attribution, and assert the invariant** (serves `§12.4` / `§9.1`; MEDIUM). Derive the untraded / trade-to-trade / other-non-`EQ` split from the same session's Bhavcopy at run time (930 → the measured 933, 220 → 224, 24 → 17), delete the literals, and assert `0` scrips the Bhavcopy reports as `EQ` fail to resolve — the sentence that actually matters. **Probe:** `probe_n176` flips to asserting the printed split equals one recomputed from the archive and that the literals are absent; a run whose printed split disagrees with the Bhavcopy exits non-zero.
3. **N-174 — count every access to the guard, not one dunder** (serves `§12.4`; LOW). The `CountingReplayGuard` counts `__contains__` only, and iterating an `OrderedDict` calls nothing, so the scan that regressed the engine is invisible (§91.4). Count `__iter__`, `keys`, `values`, `get`, `popitem` and `__contains__`, and require the total to stay at one per fill regardless of how many instances are held. **Probe:** `probe_n174` asserts the widened counter; the acceptance attack is §90.3's scan failing **5 of 5** runs, measured on this host.
4. **Promotion mechanics — move both sources in one commit** (serves `§10.8` / Phase 3B-2). Criteria **1.1.13** with `min_binding_evaluation_start_date: 2018-04-01`, `gating.py:BINDING_EVALUATION_START_DATE` to the same date with its `classify_gating_window` / `resolve_gating_verdict` docstrings, the 931 `gating_mode` rows superseded by append, `probe_pre2022_bronze_coverage.py`'s label rule re-expressed against the criteria, A5 re-read, and `MAN-FPR` re-pinned by measurement — expecting a **duplicate superseded row** if `derive_2022_2024_corpora.main()` is re-run (§91.6 residual 2). **Probe:** `probe_pre2022_preconditions.py` prints A5 `PASS` at the new start and A2/A4 unchanged; `assert_no_warmup_sessions_in_evaluation` refuses a 2018-03-29 session; W0.5-5 still attests all 931 Bronze archives; a tree with the criteria moved and the labels left `WARMUP_NOT_GATABLE` fails the coverage certificate.
5. **Register candidate seq 10 before it is run** (serves `§8.2` / Phase 3B-2). One registry row: hypothesis stated, `partition` in-sample `2018-04-01..2023-12-31`, fold spec naming **2024** as validation, `criteria_version 1.1.13`, registry manifest re-pinned; `N` 9 → 10 with `evaluation_count` still 5 until a run exists. **Probe:** the registry's `N` and its manifest pin agree with the criteria; a run whose evaluated sessions include any date in `2025-01-01..2026-11-11` fails closed, and no path under `data/raw/2025` or `2026` appears in the trial's provenance.
6. **N-150 — CRIT-OVERFIT-06 needs either a second fold or an explicit admission** (carried, not new; MEDIUM). The extended window does not create a second validation fold, so the criterion is `NOT RUN` for seq 10; either register a second fold **before** seq 10 runs, or record the criterion's `NOT RUN` in the seq-10 report as its final state. **Probe:** the verdict bundle names the fold count it used, and a verdict claiming CRIT-OVERFIT-06 `PASS` on fewer than two folds fails closed.

### 91.10 What would falsify this verdict

- If any of the six sampled sessions returns a trade-to-trade ISIN whose resolved series is not one its archive shows — or returns `None` — the closure of §91.2 rests on the wrong property and N-175 is not closed.
- If the first 4,511 lines of the interval log are not byte-identical to `fb02eea`, or any of the 324 parent identity tuples is absent from the 426, §90.8 Ruling 2 was misapplied and N-175's correction is an edit.
- If the `bisect` index disagrees with the brute-force oracle on any (ISIN, date) pair once more of the log is appended, §90.9 item 2 traded an answer for a speed-up.
- If a widened counter (item 3) still cannot see §90.3's scan, N-174 is wrong as stated and should be re-measured rather than re-scoped.
- If the 1,174 unresolved include a single scrip the 2024-01-16 Bhavcopy reports as `EQ`, then Gate COV-2's 100 % resolution invariant is false on this session and the COV-3 attribution is hiding a real regression rather than mislabeling a correct one.
- If the printed 933/224/17 split is reproducible from a different session's archive or from the price-band report rather than the Bhavcopy, my classification is the artifact and N-176 should be withdrawn.
- If any session in `2018-04-01..2021-12-31` lacks an authoritative calendar row, or an identity boundary in the window is dated at the 2022-01-03 seam, Ruling 1 rests on a fabricated input and the window stays warm-up.
- If promoting the start moves any fold, `N`, `N_eval`, cost parameter, criteria threshold or the holdout token hash, the promotion was a scope change disguised as an eligibility change.
## §92 — Audit of `1aff4c6` (tag `feat-s92-1aff4c6`): the hold bound exits through the engine, Gate COV-3 computes its attribution, the scan is caught five of five, and the binding start moves while its labels stay

**Date:** 18 November 2026
**Commit under review:** `826ef95` (28 files, +693/−143: the portfolio-level hold-bound consumer and its two call sites, seven instrumented replay-guard accessors, Gate COV-3's attribution helper, criteria 1.1.13 and three flipped probes), plus `1aff4c6` (the green-cache row, +19 lines; the source tree projects to the same hash at both, so the gate found it already recorded and appended nothing).
**Verdicts:** **N-177 CLOSED** · **N-176 CLOSED** · **N-174 CLOSED** — 5 of 5, measured on this host · criteria **1.1.13** with every pin the round promised intact, including `MAN-FPR-V1-e95ddf90…` · A1 / A2 / A4 dividends / A4 max hold / A5 **PASS** · **§91.9 item 4 PARTIAL** — the criteria moved to 2018-04-01, the 931 archive rows still read `WARMUP_NOT_GATABLE`, and the certificate refuses the relabel that would align them · **Ruling 1**: the relabel and `MAN-FPR` re-pin land as `1.1.14` **before** seq 10 registers · **Ruling 2**: eight-trial hold-bound invariance is **not measured**; it needs a targeted verification run before any seq-10 comparison

### 92.1 Baseline re-measured at `1aff4c6`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite under the gate | **544 passed in 55.72 s**, **0 skipped / 0 xfailed** |
| Verifiers | **9/9 exit 0** — audit_findings 84.41 s, cash_universe_coverage 33.77 s, historical_snapshot 5.36 s, phase2a 1.35 s, phase2b5 2.67 s, phase2b_significance 0.91 s, phase2c 2.68 s, phase2d 3.82 s, wave1 4.38 s |
| W0.5-4 / W0.5-5 | every tag verified, including `feat-s92-1aff4c6` → `1aff4c6`; **1,000** current artifacts match byte count and sha256, **26** superseded rows skipped as history |
| Green cache | the source tree was already recorded; the forced run printed `already recorded; not appending a duplicate row`; `git status` clean before and after |
| Findings ledger before this round | **46** rows / **27** ids; **4 open** — N-150, N-174, N-176, N-177 |
| Criteria / pins | **1.1.13**, `MAN-FPR-V1-e95ddf90…`, `CAL-FPR-V1-6acb5f45…`, sourced-window `CAL-FPR-V1-2d5ac7ac…`, **2,936** / **1,201** / **1,196** sessions, binding start **2018-04-01**, `max_hold_trading_sessions` **21** |
| Trials / fold / holdout | **N = 9** (seq 1–9), `evaluation_count` **5**, manifest head `50de55e9…`, eval head `ec66b016…`; in-sample `2018-04-01..2023-12-31`, validation `2024-01-01..2024-12-31`, holdout `2025-01-01..2026-11-11` with the all-zero token hash and no sentinel on disk |
| `probe_pre2022_preconditions.py` | **exit 0** — A1 5/5 (246/245/252/248, provenance digest `7622fbf4…`), A2 17,864 active of 19,283 over all 931 sessions, A4 **4,357** ex-dates, A4 max hold `enforced at 1 production call site(s); refusals=1`, A5 `0 of 4,903` before 2018-04-01 |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931 … WARMUP_NOT_GATABLE on every row` |
| Ledger probes | N-174, N-176, N-177 each PASS individually |
| Files the code commit touches | 28; **no** path under `reports/audit/`, `data/`, `data/trials/`, `configs/partition_spec.yaml`, `data/raw/2025`, `data/raw/2026` |
| `data/reference/manifest.jsonl`, `data/trials/` | **no diff** against `abf198f` |

The calendar arithmetic of the promotion closes: **2,127** sessions fall in `2018-04-01..2026-10-31` and **1,196** in `2022-01-03..2026-10-31`, and 2,127 − 1,196 = **931**, the A1-counted warm-up sessions (246 + 245 + 252 + 248). The moved value is therefore exactly the span A1, A2 and A4 certified, not a rounder.

### 92.2 N-177 — CLOSED: the bound has a consumer, and a frozen bid is a refusal, measured through the harness

| Measurement | Result |
|---|---|
| `Portfolio.require_hold_bounds(as_of, bound, calendar)` | `portfolio.py:123`; returns each refused ISIN beside its refusal, and the bound is an argument — no module default (§10.8) |
| Engine call site | `run_phase3b2_walkforward.py:1235`, `portfolio.require_hold_bounds(next_session, criteria.max_hold_trading_sessions, cal)`, inside the session loop |
| Same ledger as the harness | `runner = build_authoritative_runner(portfolio=portfolio, …)`, so the consumer reads and the harness writes the same `Portfolio`; the consumer is not reading a parallel book |
| Forced exit | `execute_swing_strategy_session(forced_exit_isins=…)` drops any strategy SELL for those ISINs and emits exactly one SELL at `next_session` with `exit_reason=MAX_HOLD_BOUND_EXIT`, through the same runner and simulator |
| **Attack — at the bound, normal bar** | refused `INE002A01018`; **one ticket, `FILLED`**, `exit_reason=MAX_HOLD_BOUND_EXIT`, position closed (`qty_left=0`) |
| **Attack — at the bound, bar locked at the lower circuit** (volume 100,000, turnover ₹9.0 cr) | **one ticket, `REJECTED_LOWER_CIRCUIT`**, `exit_reason=MAX_HOLD_BOUND_EXIT`, position **still open** (`qty_left=10`), refusal counted **1** — the §5.3 property, measured rather than inferred |
| **Attack — one session inside the bound** | no refusal, no ticket, position untouched |
| Probe flip | replacing the consumer call with an empty set makes `probe_n177` exit 1: `the walk-forward session loop does not consult the hold bound; the production consumer is never reached by a run` |
| A4 line | `max_hold_trading_sessions=21 is committed and enforced at 1 production call site(s); refusals=1 for one synthetic hold 21 sessions after entry` |

Three residuals, named rather than implied.

1. **The A4 line's "1 production call site" is `portfolio.py`'s wrapper.** The counter scans `src/signal_core` for files other than `position.py` that call `require_within_hold_bound(`, and the engine's call site is a *script* path, so it is not counted. The printed 1 is correct for what it measures and understates the surface; the engine seam is covered by `probe_n177`'s string assertion on `run_phase3b2_walkforward.py`, not by that number.
2. **No committed test drives `forced_exit_isins`.** `grep` over `tests/` finds no reference to it, and `test_max_hold_bound_refuses_the_session_past_it` calls `Position.require_within_hold_bound` directly. The engine seam therefore rests on §92.2's attack, which is my measurement and not the suite's. Work order item 4 asks for the test; the finding closes on the property, not on the missing test, because I drove the property end to end.
3. **A partial fill at the bound counts as a forced exit** and the residue is refused again next session. That is correct for the hold (never extended) but the reported counter is per ISIN, not per share, so a partially exited position reads as one forced exit and zero refusals on the session it partially filled.

### 92.3 N-176 — CLOSED: the attribution is computed from the archive it describes, and the zero is asserted

| Measurement | Result |
|---|---|
| Helper | `attribute_unresolved_eq_scrips(master, session)` in `scripts/verify_cash_universe_coverage.py`, four buckets, no literal |
| Measured split at `1aff4c6` | **1,174** unresolved = **933** with no row in the Bhavcopy + **224** in `BE`/`BZ` + **17** in another non-`EQ` series + **0** reported as `EQ` and unresolved |
| Gate assertions | `attribution["unresolved"] != summary.unresolved_isin_count` → `return False`; `attribution["eq_unresolved"] != 0` → `return False` naming Gate COV-2's 100 % invariant |
| Printed | the computed split, ending `… <n> reported as EQ and unresolved` — the one number that matters is now in the output because it is asserted in the code |
| Typed literals | gone; re-adding a `930 untraded` string makes `probe_n176` exit 1 (`Gate COV-3 still prints typed attribution literals`) |
| `probe_n176` | recomputes the split independently from `sec_list_20240116.csv` + `cm16JAN2024bhav.csv.zip`, asserts `(1174, 933, 224, 17)` and `eq_rows == 0`, then runs the gate function under `redirect_stdout`, parses the printed tuple and asserts it equals its own computation |
| Fail-closed containment | `attribute_unresolved_eq_scrips(master, 2024-01-17)` raises `BhavcopyIngestError` — `Row trade_date 2024-01-16 does not match partition date 2024-01-17 … (H-24)` — rather than attributing from another session's archive |

**Residual.** The archive filename (`cm16JAN2024bhav.csv.zip`) and the gate's session (`t_date = 2024-01-16`) are still two literals that must move together. They cannot drift silently — H-24 refuses the mismatch as measured above — but a COV-3 that moves to another session and forgets the filename fails closed with an ingest error rather than an attribution, which is a harder failure to read. Work order item 3 does not move this session; naming it here is enough while the gate asserts one date.

### 92.4 N-174 — CLOSED: the counter now sees the scan, five of five

| Measurement | Result |
|---|---|
| Accessors instrumented | **7** — `__contains__`, `__iter__`, `keys`, `values`, `items`, `__getitem__`, `__len__`, each incrementing `access_counts` through one `count()` |
| Test assertions | iteration-shaped accesses (`__iter__`, `keys`, `values`, `items`, `__getitem__`) **== 0**; `__contains__` **== fill_count**; `__len__` **≤ fill_count** |
| Ceilings | `per_fill_1k_us < 250.0`, `per_fill_4k_us < 250.0`, `scaling_ratio < 2.5` — asserted present by `probe_n174` and untouched by this commit |
| **Acceptance attack, at `1aff4c6`** | §90.3's per-fill scan over every held instance installed in `Portfolio.process_fill` in a detached worktree: **failed 5 of 5 runs** (2.2–2.9 s each), against 1 of 5 at `abf198f` and a pass outright for the cheap variant at `fb02eea` |
| Probe flip | deleting the `def __iter__` counter makes `probe_n174` exit 1: the replay-guard counter does not instrument `__iter__` |

**Residual.** Two accessors named in §91.9 item 3 are not counted — `get` and `popitem` — and I measured that this is not harmless in form even if it is in effect: a per-fill `self._processed_fill_instances.get(id(fill))` inserted into `process_fill` leaves the benchmark **passing** (`1 passed`). It does not hide an `O(n)` regression, because `.get` is a hash lookup, but the work order asked for the accessor and the counter does not have it. A scan expressed as `super().__iter__()` or `OrderedDict.__iter__(guard)` likewise bypasses the override. `__len__` is allowed up to one access per fill. The closure rests on the named regression being caught 5 of 5, which is the acceptance §91.9 item 3 wrote.

### 92.5 Criteria 1.1.13 — one value moved, everything it was pinned against measured intact

| Measure | `abf198f` (1.1.12) | `1aff4c6` (1.1.13) |
|---|---|---|
| `version` | 1.1.12 | **1.1.13**, effective 2026-11-18 |
| `min_binding_evaluation_start_date` | 2022-01-03 | **2018-04-01** — in `configs/go_no_go_criteria.yaml`, the `criteria.py` dataclass default, the loader's fallback, `storage/gating.py:BINDING_EVALUATION_START_DATE` and the module docstrings |
| `SOURCED_WINDOW_START_DATE` | did not exist | **2022-01-03**, `storage/calendar.py`; the three places that had used the binding start as a stand-in now read it: the calendar loader's session count and sourced fingerprint, `reporting/verdicts.py`'s CRIT-DATA-06 window, `verify_cash_universe_coverage.py`'s COV-2 reconciliation window, `generate_phase2d_tier_a_report.py` |
| `expected_manifest_fingerprint` | `MAN-FPR-V1-e95ddf90…` | **unchanged**, and `data/reference/manifest.jsonl` has no diff |
| `expected_calendar_fingerprint` | `CAL-FPR-V1-6acb5f45…` | **unchanged**; the loaded calendar still reports 2,936 sessions and that fingerprint |
| `expected_sourced_window_calendar_fingerprint` | `CAL-FPR-V1-2d5ac7ac…` | **unchanged**; recomputed over 1,196 sessions |
| Session anchors | 2,936 / 1,201 / 1,196 | **unchanged**, and the arm that reads 1,196 now reads `SOURCED_WINDOW_START_DATE` rather than the moved binding start |
| `max_hold_trading_sessions` | 21 | **21** |
| Trials | N = 9, N_eval = 5 | **N = 9**, `evaluation_count` **5**, registry rows seq 1–9, head `50de55e9…`, eval head `ec66b016…` |
| Fold / holdout | in-sample to 2023-12-31, validation 2024, holdout sealed | **unchanged**; partition spec identical, all-zero token hash, no `HOLDOUT_UNLOCK` sentinel |
| Phase 2D artifacts | 27 rows, PASS=2 / FAIL=0 / NOT RUN=25, NO-GO | **identical counts**, overall **NO-GO**, window `2022-01-03..2026-10-30`, criteria 1.1.13, `CRIT-FPR-V1-3aaac725…`; the two files changed **9 lines** in total (5/5 json, 4/4 md) and no evaluation row moved |

**The adversarial dates moved with the pin, and that is the Ruling rather than a weakened assertion.** `verify_phase2d_verdicts`'s pre-binding probe used `2019-01-01`; it now uses `2016-01-01`. `verify_phase2b5_storage`'s Gate G2B.5-7 used `2019-01-01`; it now uses `2018-03-29`. `test_storage`'s warm-up date and `test_pre2022_gating_mode`'s window moved the same way. 2019 is now **inside** the binding window, so a probe that used it would assert the opposite of the criteria; the property tested — a date before the binding start cannot reach GO and is classified `PRE_SURVEILLANCE_WARMUP` — is still tested, with a date before the start. What is lost is coverage of the *old* boundary: no committed test now proves that 2022-01-03 is no longer special, which is exactly what the promotion claims. `test_walkforward.test_n32_pre_window_fold_refused_fail_closed` covers the analogous shape for folds (a 2017 fold refused, `execution_config` carrying `2018-04-01`).

**Residual, carried from §91.6 and now one reseal worse.** `phase2d_tier_a_2022_2026_verdict.json` still carries `timestamp_utc 2026-11-16T10:00:00+00:00` while its `criteria_version` is now 1.1.13, effective 2026-11-18: the third version this one artifact has held against one timestamp. The reseal is forced (`verify_phase2d_verdicts` compares the artifact's fingerprint to the loaded criteria), and it is honest where it matters — no threshold moved, so no row moved — but the artifact cannot tell a reader that its 25 `NOT RUN` rows were computed under 1.1.11. The yaml note is again the only place that records it.

### 92.6 §91.9 item 4 — PARTIAL: the criteria moved, the labels did not, and the certificate enforces the stale half

| Measurement | Result |
|---|---|
| `grep -c WARMUP_NOT_GATABLE data/reference/manifest.jsonl` | **931** — every warm-up row, unrelabelled |
| `probe_pre2022_bronze_coverage.py:179` | `if row.get("gating_mode") != WARMUP_LABEL:` → a problem; `WARMUP_LABEL = "WARMUP_NOT_GATABLE"` is a module constant |
| Does the certificate read the criteria? | **no** — zero matches for `criteria`, `go_no_go`, `BINDING` in that script |
| Certificate on this tree (criteria 2018-04-01, labels `WARMUP_NOT_GATABLE`) | **exit 0**, `COVERED — 931/931 … WARMUP_NOT_GATABLE on every row` |
| Certificate after relabelling **one** row to `BINDING_EVALUATION` | **exit 1** — `[FAIL] session 2018-04-02 (FULL): … carries gating_mode 'BINDING_EVALUATION', expected 'WARMUP_NOT_GATABLE'` |
| Is seq 10 mechanically blocked by the stale label? | **no** — the guard is date-based (`warmup_sessions_in` compares `session_date < binding_start_date` and never reads a label), and A5 already reports `0 of 4,903` against 2018-04-01 |

So §91.9 item 4's acceptance is not met, and the failure is worse than a missing check: the certificate passes a tree whose criteria and manifest disagree, and **fails** on the only edit that would make them agree. The implementer records the gap in `CURRENT_STAGE_OF_WORK.md` ("the remaining promotion mechanic"), which is why this is `PARTIAL` rather than a new defect. Two claims in that note are contradicted by measurement and are corrected here: it says work-order items 5 and 6 "were not ordered" — §91.9 orders six items, and seq-10 registration and N-150 are items 5 and 6; and it calls the relabel "outside the ordered scope", when item 4 orders it by name ("the 931 `gating_mode` rows superseded by append, `MAN-FPR` re-pinned").

### 92.7 Ruling 1 — the 931 labels and the certificate's label rule move before seq 10 registers

*Evidence:* §92.6, measured at `1aff4c6`: binding start 2018-04-01, **931** rows still `WARMUP_NOT_GATABLE`, the certificate exits **0** on that contradiction and **1** on the relabel that resolves it, and it reads no criteria to notice either.

*Ruling:* the binding start is `2018-04-01` (criteria 1.1.13, verified in §92.5), and a capture label must describe the same fact or the manifest is wrong about the sessions a result rests on. The **931** rows are superseded by **append** with the label the criteria now imply, `MAN-FPR` is re-pinned over the grown manifest as criteria **1.1.14**, and `probe_pre2022_bronze_coverage.py`'s label rule is re-expressed against `min_binding_evaluation_start_date` in the same commit, so the certificate and the guard read one source. This lands **before** candidate seq 10 is registered, because the registry row names the criteria version the run is made under (§8.2): registering against 1.1.13 and re-pinning afterwards would leave the run's provenance describing its own in-sample sessions as not gatable.

*It does not change:* any archive's bytes, byte count or digest; the 931 sessions' calendar, identity or dividend evidence; the binding start; the sourced-window pins (`CAL-FPR-V1-2d5ac7ac…`, 1,196); any threshold, fold or trial count; the holdout seal. A relabel states the maturity of an input A1, A2 and A4 have already certified; it asserts nothing new about prices.

*Work item:* §92.10 item 1, serving `§10.8` / Phase 3B-2. *Probe:* the coverage certificate exits non-zero on a tree whose criteria and labels disagree (today it exits 0, and the aligned relabel makes it exit 1), `probe_pre2022_preconditions.py` stays READY 9/9, W0.5-5 still attests all **931** archives, and the manifest diff is additions only.

*Falsified by:* a 1.1.14 that relabels while leaving the hard-coded label rule in place (the certificate would then fail on its own tree); a relabel that edits a row instead of appending one; a relabel that changes any Bronze digest; or a seq 10 registered against 1.1.13 with the labels as they stand.

### 92.8 Ruling 2 — eight-trial hold-bound invariance is a claim without a measurement, and needs a targeted run

*Evidence:* §92.2 establishes the enforcement is real. The committed artifacts cannot bound it: `in_sample_metrics` carries `{cagr, closed_trades, end_equity, fold, max_drawdown, profit_factor, sessions, start_equity, win_rate, window}` and `validation_metrics` is `null` in `trial_009`, so no holding period is recoverable from any of the eight. Seven of the eight verdict artifacts are byte-identical to `abf198f` **because they were not re-run** — a fact about files, not about outcomes — and the eighth (`phase2d_tier_a`) moved only its version and fingerprint. The commit's own note says it in the implementer's words: "NOT RUN: the eight post-2022 trial outcomes were not re-run … outcome invariance is not measured here."

*Ruling:* §90.9 item 4's condition ("no existing post-2022 trial outcome may move") is **not satisfied by this round** and cannot be satisfied by inspection. Before any seq-10 result is compared with the eight recorded trials, one recorded trial's in-sample window (`2022-01-03..2023-12-29`) is re-run under the committed engine and criteria with the new counters, and the run must report `hold_bound_forced_exits == 0` and reproduce `closed_trades`, `end_equity`, `profit_factor`, `win_rate` and `max_drawdown` from its committed artifact. A non-zero forced exit is a finding about comparability and is reported as one, never smoothed into "the bound was unlikely to bind".

*It does not change:* the bound (**21**), the window, the fold, the cost schedule or any threshold. It adds a measurement the round said it would make and did not.

*Work item:* §92.10 item 2, serving `§13.2` / Phase 3B-2. *Probe:* the re-run's result carries `hold_bound_forced_exits` and `hold_bound_refusals`, and the metric comparison is an equality assertion against the committed artifact; a run whose evaluated sessions include any date in `2025-01-01..2026-11-11` fails closed.

*Falsified by:* a targeted run with 0 forced exits whose metrics differ — the enforcement path perturbs the engine another way, for example the `declared_exit_reason` precedence now applied to every SELL — or a run that produces a forced exit yet still reproduces the committed metrics, in which case the bound was reached but did not change a fill and invariance was the wrong question.

*Why the run is expected to be cheap:* with `forced_exit_isins` empty the new path is inert — `raw_intents` is untouched when `forced` is empty — so a zero-forced-exit run measures the enforcement the round asks about, plus the reordering (sorted forced intents first) only when one exists.

### 92.9 Phase verdicts

| Phase | Verdict at `1aff4c6` | Named residuals |
|---|---|---|
| `§13.2` A4 max hold (N-177) | **CLOSED** — consumer in the session loop, one forced SELL through the same simulator, a locked bid leaves the position open and counts a refusal | the engine seam has no committed test; the A4 "1 production call site" counts the portfolio wrapper, not the script |
| `§12.4` Gate COV-3 (N-176) | **CLOSED** — split computed from the session Bhavcopy, `0` Bhavcopy-`EQ` unresolved asserted in code | archive filename and session are literals, bound together by H-24 |
| `§12.4` test invariant (N-174) | **CLOSED** — §90.3's scan fails **5 of 5**; ceilings unchanged | `get`/`popitem` uncounted; `super().__iter__()` bypasses the override |
| `§10.8` A1 / A2 | **PASS / PASS** — 246/245/252/248 from 7 sourced artifacts; 17,864 of 19,283 rows over 931 sessions | — |
| `§10.8` A4 dividends / max hold | **PASS / PASS** — 4,357 ex-dates; enforced with `refusals=1` | invariance run outstanding (Ruling 2) |
| `§10.8` A5 | **PASS** — 0 of 4,903 evaluated sessions before 2018-04-01 | the corpus is still the post-2022 one; A5 tests the pin, not the new window's roll-forward |
| Criteria and pins | **1.1.13** — one value moved, every other pin measured unchanged; Phase 2D regenerated to `PASS=2 / FAIL=0 / NOT RUN=25 / NO-GO` | the artifact's timestamp predates the criteria version it carries |
| `§91.9` item 4 promotion mechanics | **PARTIAL** — criteria and guard moved; labels and certificate did not (§92.6) | Ruling 1 |
| `§91.9` item 5 (seq 10) / item 6 (N-150) | **not done** — N = 9, `N_eval = 5`, registry untouched | blocked behind Ruling 1; N-150 stays OPEN |
| Gate / cache | **GO** — 544 passed, 9/9 verifiers, tree already recorded, no duplicate row appended | — |

### 92.10 Work order for feat-s93

Ordered by what it unblocks. Each item names the probe that must fail closed before it closes, and the phase it serves.

1. **Ruling 1 — relabel the 931 rows by append, re-express the certificate, re-pin `MAN-FPR` as 1.1.14** (serves `§10.8` / Phase 3B-2). Supersede the 931 `WARMUP_NOT_GATABLE` rows with the label the binding start implies, never editing one; re-express `probe_pre2022_bronze_coverage.py`'s label rule against `load_go_no_go_criteria().min_binding_evaluation_start_date`; re-pin `expected_manifest_fingerprint` by measurement over the grown manifest. **Probe:** the certificate exits non-zero on a tree whose criteria and labels disagree and zero on the aligned tree; `probe_pre2022_preconditions.py` READY 9/9; W0.5-5 attests all 931 archives; the manifest diff is additions only. **Blocks item 3.**
2. **Ruling 2 — the targeted eight-trial invariant run** (serves `§13.2`). Re-run one recorded trial's in-sample window with the enforcement in place and compare the five metrics to its committed artifact. **Probe:** the result carries `hold_bound_forced_exits` / `hold_bound_refusals`; the equality assertion fails loudly on any metric drift; a sealed-era session in the evaluated set fails closed.
3. **Register seq 10 against 1.1.14** (§91.9 item 5, re-issued): one registry row, in-sample `2018-04-01..2023-12-31`, fold spec naming **2024** as validation, `N` 9 → 10 with `evaluation_count` still 5, registry manifest re-pinned, no path under `data/raw/2025` or `2026` in its provenance. **Probe:** the registry's `N`, `criteria_version` and pin agree with the criteria; a run that evaluates a sealed session fails closed.
4. **A committed test at the swing seam** (serves `§12.4`). `forced_exit_isins` through `execute_swing_strategy_session`: one `MAX_HOLD_BOUND_EXIT` fill on a normal bar, `REJECTED_LOWER_CIRCUIT` with the position still open on a locked bar, and nothing at all one session inside the bound. **Probe:** `probe_n177` asserts that test exists — today it asserts the consumer call and a string in the script, so a call that is unreachable still passes it.
5. **N-150 — CRIT-OVERFIT-06 needs a second fold or a recorded admission** (carried, MEDIUM; §91.9 item 6). **Probe:** the verdict bundle names the fold count it used, and a `PASS` on fewer than two folds fails closed.
6. **The counter's named accessors** (serves `§12.4`). `get` and `popitem` were ordered in §91.9 item 3 and are not counted; either instrument them or record why iteration-shaped access is the whole surface. **Probe:** `probe_n174` asserts the accessor set it can measure, so a narrowed counter fails it.

### 92.11 What would falsify this verdict

- If a position at the bound is refused but its SELL is not routed through the harness — two tickets, or none — N-177 rests on the wrong seam. Measured here: one ticket, `MAX_HOLD_BOUND_EXIT`, position closed.
- If a bar locked at the lower circuit still fills a forced SELL, §5.3 is violated and the refusal counter is decorative. Measured `REJECTED_LOWER_CIRCUIT` with `qty_left=10`.
- If 933/224/17 is reproducible only from the price-band report or from another session's archive, N-176's closure rests on the wrong artifact and should be withdrawn.
- If the regression that actually returns is a `super().__iter__()` scan or a per-fill `.get()`, the closure is about the shape the counter watches and not about `O(1)`; the residual is named, and the finding should be re-opened rather than re-scoped.
- If the certificate still exits 0 on a tree whose criteria and labels disagree after 1.1.14, Ruling 1 was applied additively — a new label beside the old rule.
- If a targeted re-run yields 0 forced exits and moved metrics, the enforcement is not inert when the bound is not reached, and Ruling 2's condition is unmet for a different reason.
- If any pin measured unchanged in §92.1 (`MAN-FPR`, `CAL-FPR`, `2d5ac7ac`, 2,936 / 1,201 / 1,196, N = 9, `N_eval = 5`, the 2024 fold, the all-zero token hash) moves later without being named, this baseline described the wrong tree.
## §93 — Audit of `e5e9217` (tag `feat-s93-e5e9217`): the 931 labels align with the binding start and the certificate reads the criteria, the seam test binds the harness but not the engine, and seq 10's baseline does not reproduce

**Date:** 18 November 2026
**Commit under review:** `bd204a2` (19 files, +2,625/−964: the 931-row relabel by supersession, the certificate's derived label rule, criteria 1.1.14, the Phase 2D regeneration, `probe_hold_bound_invariance.py`, and the swing-seam test), plus `e5e9217` (the green-cache row, +19 lines).
**Verdicts:** **§92.7 Ruling 1 CLOSED** — 931/931 rows read `BINDING_EVALUATION`, the certificate exits 1 on a tree whose criteria and labels disagree and 0 on the aligned tree, and 1.1.14 moves no numeric value · **§92.10 item 4 CLOSED as ordered** — three committed tests drive the seam and `probe_n177` executes them, though the session loop's use of the harness is still asserted by no test · **§92.8 Ruling 2 NOT SATISFIED** — the bound binds 175 times rather than 0, and 0 of 5 recorded metrics reproduce either with or without the consumer · **Ruling 3** — seq 10 may register and run on `2018-04-01..2023-12-31`, but the eight `1.1.5` artifacts are history, not its baseline.

### 93.1 Baseline re-measured at `e5e9217`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite under the gate | **548 passed in 57.27 s**, **0 skipped / 0 xfailed** (544 at `1aff4c6`; the four added tests are the three seam tests and the certificate's misaligned-pin test) |
| Verifiers | **9/9 exit 0** — Gate W0.5-2 |
| W0.5-4 / W0.5-5 | every tag verified, including `feat-s93-e5e9217` → `e5e9217`; **1,000** current artifacts match byte count and sha256, **957** superseded rows skipped as history |
| Green cache | the source tree `ad5f0737…` was already recorded at this commit; the forced run printed `already recorded; not appending a duplicate row`; `git status` clean before and after |
| Findings ledger | **49** rows / **29** ids; **27 CLOSED**, **1 OPEN** (N-150), **1 ACCEPTED** (N-152) |
| Criteria / pins | **1.1.14**, `MAN-FPR-V1-a421d3d2…`, `CRIT-FPR-V1-a2f83d04…`, `CAL-FPR-V1-6acb5f45…`, sourced-window `CAL-FPR-V1-2d5ac7ac…`, **2,936** / **1,201** / **1,196** sessions, binding start **2018-04-01**, `max_hold_trading_sessions` **21** |
| Trials / fold / holdout | **N = 9** (seq 1–9), `evaluation_count` **5**, heads `50de55e9…` / `ec66b016…`, registry pin `3326b1b2…`; in-sample `2018-04-01..2023-12-31`, validation `2024-01-01..2024-12-31`, holdout `2025-01-01..2026-11-11` with the all-zero token hash; `data/trials/` byte-identical to `abf198f`, `git status` clean after every run below |
| `probe_pre2022_preconditions.py` | **exit 0, READY 9/9** — A1 5/5 (246/245/252/248), A2 17,864 active of 19,283 over all 931 sessions, A4 **4,357** ex-dates, A4 max hold `enforced at 1 production call site(s); refusals=1`, A5 `0 of 4,903` before 2018-04-01 |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `931/931 … 931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE` |
| `probe_audit_findings.py N-177` | **exit 0** — `PASS N-177` |
| `probe_hold_bound_invariance.py` | **exit 1** — `NOT INVARIANT`, 175 forced exits / 203 refusals, 5/5 metrics drifted (§93.4) |
| Files the code commit touches | 19; **no** path under `reports/audit/`, `data/trials/`, `data/raw/2025`, `data/raw/2026`, `configs/partition_spec.yaml` |

The calendar arithmetic is unchanged from §92.5: 2,127 sessions in `2018-04-01..2026-10-31` less 1,196 in `2022-01-03..2026-10-31` is the 931 relabelled sessions.

### 93.2 §92.7 Ruling 1 — CLOSED: the labels, the certificate and the pin moved together, and the certificate now fails on the contradiction it used to pass

| Measurement | Result |
|---|---|
| Manifest rows | **1,026 → 1,957**; current **1,000 → 1,000**; superseded **26 → 957** |
| The 931 superseded rows | every archive field byte-identical to the row they supersede (`artifact`, `byte_count`, `sha256`, `source_url`, `retrieved_at`, `session_date`, `session_type`); **only** `is_current: true → false` and `status: active → superseded` differ — measured field-by-field, **0** exceptions |
| The 931 appended rows | `is_current: true`, `gating_mode: BINDING_EVALUATION`, and a `retrieval_reference` naming §92.7 Ruling 1 / 1.1.14; every archive field identical to the superseded row; **0** exceptions |
| Code diff shape | 931 removed / 1,862 added lines — **not** additions only. See the correction below |
| Certificate on the aligned tree | **exit 0**, `931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE` |
| **Attack — criteria pushed forward** (pin `2022-01-03`, labels unchanged) | **exit 1**, `931 problem(s)`, first reading `session 2018-04-02 (FULL): … carries gating_mode 'BINDING_EVALUATION', expected 'WARMUP_NOT_GATABLE' for a session before the binding start 2022-01-03 (criteria 1.1.14)` |
| **Attack — criteria pushed back** (pin `2015-01-01`) | **exit 0** — correct: every captured session is still on/after the pin, so the label is right |
| **Attack — one current row mislabelled `WARMUP_NOT_GATABLE`** | **exit 1**, one problem naming `2018-08-01` and the expected `BINDING_EVALUATION` |
| **Attack — one current row's `sha256` forged** | **exit 1**, `sha256 mismatch (disk 37f26540…, row 0000…)` |
| **Attack — one current row duplicated** | **exit 1**, `2 duplicate current row(s)` |
| Criteria 1.1.14 | **45** dataclass fields; **97** yaml leaves; **4** leaves changed — `metadata.version`, `expected_manifest_fingerprint`, `min_binding_evaluation_start_date`, `pre_binding_calendar_provenance_note`; **8** numeric leaves and **33** numeric-as-string leaves unchanged, **0** moved |
| Manifest pin | recomputed over 1,865,503 bytes → `MAN-FPR-V1-a421d3d2de37ada0cf03c536782c64ffb305627ebef7baca15fdd8bfc59646b6`; Gate W0.5-5 verifies it |
| Phase 2D artifacts | 27 rows, **PASS=2 / FAIL=0 / NOT RUN=25**, overall **NO-GO**, window `2022-01-03..2026-10-30`, criteria **1.1.14**, `CRIT-FPR-V1-a2f83d04…`; only the version, the fingerprint, the restatement and the derived `CRIT-WINDOW-01` threshold moved |

**Correction to §92.7's own probe wording, appended rather than edited.** The Ruling asked that "the manifest diff is additions only". The diff is **931 removed / 1,862 added**, because the repository's supersession convention rewrites the superseded row's `is_current`/`status` in place and appends the new current row (the same shape `append_series_restatements.py` uses for the interval table). The invariant the Ruling was protecting — no archive byte, digest, URL or retrieval time changes, and the prior row survives — holds on measurement, and the implementer measured it precisely in `CURRENT_STAGE_OF_WORK.md` rather than repeating my wording. The probe as written was measuring the wrong shape; the correct acceptance, which I adopt from here, is "no archive field of a superseded row changed, and the count of current rows per archive is one". This is a correction of a probe's wording, not a relaxation of a threshold (§12.4 is untouched).

**Residual, carried.** No verifier asserts the superseded rows' archive fields are intact; the check I ran above is this round's measurement, not the suite's. Work order item 3 asks for it.

### 93.3 §92.10 item 4 — CLOSED as ordered: the harness seam is driven by the suite, and the engine's use of it is not

| Measurement | Result |
|---|---|
| Test file | `tests/unit/test_phase3b2_audit_s93_items.py`, **3** tests |
| Surfaces driven | `Portfolio.require_hold_bounds(execution_session, 21, calendar)` returns the refused ISIN with `Hold bound refused`; `execute_swing_strategy_session(..., forced_exit_isins=tuple(sorted(refusals)))` carries the exit |
| **At the bound, normal bar** | one ticket, `FILLED`, `exit_reason=MAX_HOLD_BOUND_EXIT`, position `is_closed`, counters `(1 forced, 0 refused)` |
| **At the bound, bar locked at the lower circuit** (`LOW = LOWER_LIMIT`, volume 100,000) | one ticket, `REJECTED_LOWER_CIRCUIT`, position open at quantity 10, counters `(0, 1)` — §5.3 measured, not inferred |
| **One session inside the bound** | no refusal, no ticket, position untouched, counters `(0, 0)` |
| Run | **3 passed in 0.90 s** |
| `probe_n177` | **PASS**; it asserts the file exists, asserts the four tokens (`forced_exit_isins=`, `MAX_HOLD_BOUND_EXIT`, `REJECTED_LOWER_CIRCUIT`, `require_hold_bounds(`), and **executes** `pytest -q <file>` rather than naming it |
| **Mutation — harness ignores the argument** (`forced = set()`) | **2 failed / 1 passed**, `probe_n177` **exit 1** — the test binds the harness |
| **Mutation — the session loop stops passing it** (line removed) | **3 passed**, `probe_n177` **exit 0** — nothing fails |

The last row is the §14.4 shape and is named as a residual rather than smoothed: the seam is proven at the harness, and the edge from the session loop into the harness is asserted by no committed test. It is not unmeasured, however — `probe_hold_bound_invariance.py`'s run A reports **175** forced exits produced by the real session loop (§93.4), so the edge is live at this commit; what is missing is a check that would notice if it were cut later. Work order item 2.

### 93.4 §92.8 Ruling 2 — NOT SATISFIED on both clauses: the bound binds 175 times, and the drift is not the bound's

`scripts/probe_hold_bound_invariance.py`, measured here (exit **1**):

| Run | Sessions | `hold_bound_forced_exits` | `hold_bound_refusals` | Metrics vs `trial_009` / criteria `1.1.5` |
|---|---|---|---|---|
| A — committed engine, bound **21** | 494, `2022-01-03..2023-12-29` | **175** | **203** | **5/5 differ** |
| B — same engine, bound raised to 10⁶ in the loaded criteria only | 494, same window | **0** | **0** | **5/5 differ** |

| Metric | Committed `trial_009` (1.1.5) | Run A (bound 21) | Run B (bound disabled) |
|---|---|---|---|
| `closed_trades` | 193 | **382** | **194** |
| `end_equity` | 1,283,327.73 | **1,086,020.54** | **1,164,053.76** |
| `profit_factor` | 0.99196 | **1.10696** | **0.84146** |
| `win_rate` | 0.25389 | **0.40838** | **0.26289** |
| `max_drawdown` | 0.20733 | **0.32642** | **0.28422** |

What this establishes, in the probe's own attribution logic:

1. **Ruling 2's acceptance is not met.** It required `hold_bound_forced_exits == 0` and five metrics reproduced. Measured 175 forced exits / 203 refusals and 0 of 5 reproduced. The Ruling's expectation that the run would be cheap because the path is inert when the set is empty was half right — run B is inert (0 / 0), which is the path's own behaviour — and wrong about the world: a 21-session bound is reached 175 times in one 493-session fold. The assumption, not the code, was falsified.
2. **The drift is not the bound's.** Run B disables the consumer and still fails all five metrics (194 vs 193 closed trades, end equity short by ₹119,273.97). The engine or its inputs moved between the `1.1.5` artifact (2026-11-17T05:30:30) and this tree. The probe's docstring names the likely cause — `security_master_fingerprint` moved when the interval table was restated under §91.2, which N-130 correctly refuses to treat as a re-render — and that remains a named, unmeasured hypothesis.
3. **The bound is materially not inert.** A-vs-B on the same window: 194 → 382 closed trades, PF 0.841 → 1.107, end equity 1,164,053.76 → 1,086,020.54, win rate 0.263 → 0.408, max drawdown 0.284 → 0.326. Any trial that did not enforce the bound is a different strategy from one that does.
4. **Registry containment is measured.** `data/trials/trial_registry.jsonl` and its three sidecars hash identically before and after both runs (the probe asserts it and would have raised); `data/trials/` is **N = 9**, `evaluation_count` **5**, heads `50de55e9…` / `ec66b016…`, `git status` clean. The two verification rows live only in the temporary registry copies the probe deletes.
5. **One more honest difference.** Run A reports **494** executed sessions against the artifact's **493**. The bound cannot change how many sessions are traversed, so this is an input/traversal difference of the same family as (2); it is named, not asserted to be an error.

**Residual for comparability.** The eight recorded trial artifacts were produced under criteria `1.1.5`, and neither the bound's presence nor the engine's current inputs reproduce them. Nothing in this round re-ran them under the current tree. A seq-10 result must therefore carry its own current-tree baseline, and the eight remain history.

### 93.5 Ruling 3 — seq 10 may register and run; its baseline is the current tree, never the `1.1.5` artifacts

*Evidence:* §93.4, measured at `e5e9217`: the bound binds 175 times / 203 refusals on the 2022–2023 fold, the bound's own effect is 194 → 382 closed trades, and both the bound-live and bound-disabled runs fail 5/5 against `trial_009`'s `1.1.5` artifact. §93.2: the 931 rows now carry `BINDING_EVALUATION`, so a 2018-start in-sample window is label-consistent and `probe_pre2022_preconditions.py` is READY 9/9 over it (§93.1). §92.10 item 3 ordered seq 10 only after Ruling 1, and Ruling 1 is closed.

*Ruling:* candidate **seq 10** is authorised to be registered and run on the expanded in-sample window **`2018-04-01..2023-12-31`**, with **2024** frozen as the validation fold and `2025-01-01..2026-11-11` sealed. Its comparability baseline is **a current-tree run of the same configuration over its own window**, not `trial_001..009`. The registry moves `N` 9 → 10 with `evaluation_count` still **5**, its manifest re-pinned by measurement, and the row names criteria **1.1.14** and the in-sample window. The report of seq 10 must carry `hold_bound_forced_exits` and `hold_bound_refusals`, and it must state that trials 1–9 were run without an enforced hold bound.

*It does not change:* the bound (**21**), any threshold, the cost schedule, the fold boundaries, the trial count's meaning (`N` counts registered hypotheses, `evaluation_count` counts evaluations of the sealed/validation set), the holdout seal, or the trial registry's history. It opens no new scope: delivery swing on `EQ`, no intraday, no F&O, no `BE` entry.

*Work item:* §93.7 item 1, serving `§13.2` / Phase 3B-2. *Probe:* the registry row's `N`, `criteria_version`, window and manifest pin agree with the committed criteria; a run whose evaluated set contains any session in `2025-01-01..2026-11-11` fails closed; the artifact carries both counters; a report that names a `1.1.5` artifact as its baseline fails review.

*Falsified by:* a seq 10 presented against `trial_009` or any `1.1.5` artifact as its comparison; a seq-10 run with **0** forced exits over a 1,400-session window reported as evidence the bound is inert; a registry row that moves `evaluation_count`; or any evaluated session on/after `2025-01-01`.

### 93.6 Phase verdicts

| Phase | Verdict at `e5e9217` | Named residuals |
|---|---|---|
| `§10.8` Ruling 1 — labels, certificate, pin | **CLOSED** — 931/931 `BINDING_EVALUATION`, certificate exit 0 aligned / exit 1 misaligned, pin `a421d3d2…`, 1.1.14 moves no numeric value | §92.7's "additions only" wording corrected to "no archive field changed"; no verifier asserts the superseded rows' archive fields (§93.7 item 3) |
| `§12.4` / `§13.2` §92.10 item 4 — seam test | **CLOSED as ordered** — 3 tests through the harness, `probe_n177` executes them, locked bid refuses and leaves the position open | the session loop → harness edge is unasserted: removing it leaves 3 passed / `PASS N-177` |
| `§13.2` §92.8 Ruling 2 — invariance | **NOT SATISFIED** — 175 forced exits, 203 refusals, 5/5 metrics drift; bound-disabled run also 5/5 | the drift's cause is named (interval restatement / engine movement since 1.1.5) and unmeasured; the eight artifacts are not re-run under the current tree |
| `§10.8` A1 / A2 / A4 / A5 | **PASS** — READY 9/9 on the expanded window | A5 still evaluates the post-2022 verdict corpus only; it tests the pin, not a 2018-start run |
| `§10.8` / `§10.5` manifest provenance | **PASS** — 1,000 current / 957 superseded rows attested, archive digests unchanged | a superseded row's digest is not re-verified after the flip |
| Phase 2D | **NO-GO** — PASS=2 / FAIL=0 / NOT RUN=25, criteria 1.1.14 | artifact `timestamp_utc` still 2026-11-16T10:00:00 under a 1.1.14 fingerprint (carried from §91.6, §92.5) |
| Trials / fold / holdout | **N = 9 / N_eval = 5**, data/trials byte-identical; 2024 fold frozen; holdout sealed, all-zero token hash | seq 10 not yet registered (Ruling 3 authorises it) |
| Gate / cache | **GO** — 548 passed, 9/9 verifiers, tree `ad5f0737…` already recorded, no duplicate row | — |

### 93.7 Work order for feat-s94

Ordered by what it unblocks. Each item names the probe that must fail closed before it closes, and the phase it serves.

1. **Register and run candidate seq 10 under Ruling 3** (serves `§13.2` / Phase 3B-2). One registry row: in-sample `2018-04-01..2023-12-31`, validation fold **2024** frozen, `N` 9 → 10, `evaluation_count` **5**, manifest re-pinned, criteria **1.1.14** named, no path under `data/raw/2025` or `2026` in its provenance, and a current-tree baseline run rather than a `1.1.5` artifact. **Probe:** the registry row's `N`, version, window and pin agree with the criteria; a sealed-era session in the evaluated set fails closed; the artifact carries `hold_bound_forced_exits` / `hold_bound_refusals`; a report naming a `1.1.5` baseline is refused.
2. **Assert the engine → harness edge** (serves `§12.4`, `§14.4`). Removing `forced_exit_isins=tuple(sorted(forced_exits))` from the session loop must make a committed check fail; today 3 tests pass and `probe_n177` exits 0. Either assert the passthrough in `probe_n177` (source, plus a short run whose counters are non-zero) or drive one session through `run_phase3b2_walkforward`'s loop. **Probe:** the mutation above makes `probe_n177` exit 1.
3. **Verify the superseded rows survive their own flip** (serves `§10.1`, `§10.5`). A verifier must assert that for every superseded manifest row there is exactly one current row for the same artifact and that `byte_count`, `sha256`, `source_url`, `retrieved_at`, `session_date` and `session_type` are unchanged. **Probe:** editing a superseded row's `sha256` must fail the verifier; today only this round's measurement checks it.
4. **N-150 — CRIT-OVERFIT-06 needs a second fold or a recorded admission** (carried, MEDIUM). **Probe:** the verdict bundle names the fold count it used, and a `PASS` on fewer than two folds fails closed.
5. **The replay counter's `get` and `popitem`** (carried, `§92.10` item 6). **Probe:** `probe_n174` asserts the accessor set it can measure, so a narrowed counter fails it.
6. **Restate the Phase 2D artifact's timestamp** (carried, LOW). The artifact has carried `2026-11-16T10:00:00+00:00` through 1.1.11, 1.1.12, 1.1.13 and now 1.1.14; the yaml note is the only record of which criteria its 25 `NOT RUN` rows were computed under. **Probe:** the artifact's `timestamp_utc` is later than its `criteria_version`'s effective date, or a `restatement_history` block names each version it has carried.

### 93.8 What would falsify this verdict

- If the certificate still exits 0 with a single current row mislabelled `WARMUP_NOT_GATABLE`, Ruling 1 was applied additively and this closure is wrong. Measured: exit 1 on that row.
- If a superseded manifest row's `sha256` differs from the row it supersedes, the relabel edited history rather than appending over it. Measured: 0 exceptions across 931.
- If 1.1.14 changed a numeric threshold that my leaf comparison did not cover (a value embedded in a note or a new field), the "no numeric change" claim is a scan artefact. Measured: 97 leaves, 8 numeric + 33 numeric-string, 0 moved.
- If run B was not actually bound-disabled, the attribution in §93.4 collapses. Measured: 0 forced exits / 0 refusals and metrics that differ from run A's, so the switch took effect.
- If the 175/203 counters count anything other than `MAX_HOLD_BOUND_EXIT` tickets, the bound's effect is overstated. The counter is `len(forced_exits - forced_filled)` over tickets carrying that reason; a partial fill reads as a forced exit and no refusal, so 203 is a floor on refusals, not a ceiling.
- If seq 10 is registered against the `1.1.5` artifacts as its comparison, Ruling 3 was ignored and any "improvement" it reports is uninterpretable.
- If `data/trials/` gains a row without a new numbered section and a registry row naming 1.1.14, the N = 9 baseline in §93.1 described the wrong tree.

## §94 — Audit of `0287aae` (tag `feat-s94-0287aae`): the seam is asserted in the source and the row in its fields, seq 10 refuses on a measured block, and neither new check can see a live path

**Date:** 18 November 2026
**Commit under review:** `d726e38` (6 files, +1,108/−2: the AST passthrough check and its mutation self-check in `probe_n177`, `superseded_archive_problems` in the Bronze certificate, the seq-10 runner and its certificate, four tests, and the phase note), plus `0287aae` (the green-cache row, +19 lines). Neither commit touches a path under `reports/audit/`, `data/trials/`, `data/raw/2025`, `data/raw/2026` or `configs/partition_spec.yaml`.
**Verdicts:** **§93.7 item 2 CLOSED as ordered** — the check parses the call and refuses both the deletion and the emptied keyword, a committed test binds the same mutation, and the probe builds it · **§93.7 item 3 CLOSED as ordered** — 931/931 superseded session rows are compared field-by-field against their current row, and an edited digest, byte count, URL, retrieval time or session fails the certificate · **§93.5 Ruling 3 block PASS** — seq 10 refuses on a measured precondition, every invariant the Ruling fixed still holds, and **seq 10 is not registered** (`N = 9`, `N_eval = 5`) · **three new findings**: **N-178** the passthrough check cannot see an unreachable call, **N-179** a deleted superseded row is invisible, **N-180** the registration path writes seq 9's fold specification for the expanded window.

### 94.1 Baseline re-measured at `0287aae`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite under the gate | **552 passed in 57.38 s** (58.43 s wall), **0 skipped / 0 xfailed** — 548 at `e5e9217`; the four added tests are `test_phase3b2_audit_s94_items.py`'s |
| Verifiers | **9/9 exit 0** — Gate W0.5-2 |
| W0.5-4 / W0.5-5 | every tag verified, including `feat-s94-0287aae` → `0287aae`; **1,000** current artifacts match byte count and sha256, **957** superseded rows skipped as history |
| Green cache | source tree `4a273db3…` already recorded at this commit; the forced run printed `already recorded; not appending a duplicate row`; `git status` clean before and after |
| Findings ledger | **49** rows / **29** ids; **27 CLOSED**, **1 OPEN** (N-150), **1 ACCEPTED** (N-152); `verify_audit_findings.py` **exit 0**, `ALL 29 FINDING PROBE(S) PASSED` |
| Criteria / pins | **1.1.14** (45 dataclass fields), `MAN-FPR-V1-a421d3d2…`, trial-registry pin `3326b1b2…` (recomputed, matches), binding start **2018-04-01**, `max_hold_trading_sessions` **21** |
| Trials / fold / holdout | **9** rows, seq 1–9, criteria versions `1.1.0/1.1.1/1.1.2/1.1.4/1.1.5`, **5** evaluation rows, registry manifest sha256 **3326b1b2…**; partition spec in-sample `2018-04-01..2023-12-31`, validation `2024-01-01..2024-12-31`, holdout `2025-01-01..2026-11-11` with the all-zero token hash; `data/trials/` byte-identical after every run below |
| `probe_pre2022_preconditions.py` | **exit 0, READY 9/9** — A1 246/245/252/248, A4 **4,357** dividend ex-dates `2018-04-03..2021-12-30`, A4 max hold `enforced at 1 production call site(s); refusals=1`, A5 `0 of 4,903` before 2018-04-01 |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931 … 931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE; 931 superseded session row(s) retain their archive digest and provenance` |
| `probe_audit_findings.py N-177` | **exit 0** — `PASS N-177` |
| `tests/unit/test_phase3b2_audit_s94_items.py` | **4 passed in 0.69 s** |
| `scripts/run_seq10_candidate.py` | **exit 1** — `NOT REGISTERED`, corpus precondition (§94.4) |
| `scripts/probe_seq10_candidate.py` | **exit 1** — `NOT CERTIFIED … seq 10 is NOT REGISTERED; the registry is N = 9 / N_eval = 5` |
| Files the code commit touches | 6; **no** path under `reports/audit/`, `data/trials/`, `data/raw/2025`, `data/raw/2026`, `configs/partition_spec.yaml` |

### 94.2 §93.7 item 2 — CLOSED as ordered: the call is parsed, the mutation is built, and a dead guard still passes

The check §93.3 asked for exists: `_session_loop_passthrough_problem` walks the module's AST, collects every `execute_swing_strategy_session` call, and compares `ast.unparse` of the `forced_exit_isins` keyword to `tuple(sorted(forced_exits))`, so a comment, a dead branch and an edited expression are distinguishable. `probe_n177` then builds the mutation the work order names — it strips the passthrough line from the source text, asserts the text actually changed, and requires the stripped source to be refused, which makes a check that cannot fail a failure of the probe itself (§14.4). A committed test asserts the same pair.

Attacks in a detached worktree at `0287aae`:

| Mutation | `probe_n177` | `tests/unit/test_phase3b2_audit_s94_items.py` |
|---|---|---|
| none (control) | **exit 0**, `PASS N-177` | 4 passed |
| **A — passthrough line deleted** from the session loop | **exit 1**, `… does not hand the hold bound's exits to the harness (line 1241: no forced_exit_isins keyword)` | **1 failed / 3 passed** (`test_session_loop_hands_the_hold_bound_exits_to_the_harness`) |
| **B — expression emptied** (`forced_exit_isins=()`) | **exit 1**, `(line 1241: forced_exit_isins=())` | **1 failed / 3 passed** |
| **D — live call wrapped in `if forced_exits is None:`** (lines 1241–1256, keyword intact, source parses) | **exit 0**, `PASS N-177` | **4 passed** |

Row D is the §14.4 shape one level down: the check reads an expression wherever it is written, not the call that executes. The two mutations the work order named both fail closed, so the item is **CLOSED as ordered**; the reachability gap is registered separately as **N-178** rather than used to reopen it (§14.5). Note also that `probe_hold_bound_invariance.py` — the only instrument that observes the seam at run time, 175 forced exits — is a `probe_*.py`, not a `verify_*.py`, and is therefore not executed by the gate.

### 94.3 §93.7 item 3 — CLOSED as ordered over 931 rows: an edit fails, a deletion does not

`superseded_archive_problems(rows)` groups the whole manifest by `artifact`, requires exactly one current row for every artifact that carries a `session_date`, and compares each superseded row's six archive fields (`sha256`, `byte_count`, `source_url`, `retrieved_at`, `session_date`, `session_type`) against that current row. The Bronze certificate now prints the count it checked, which is the number that makes the scope auditable rather than implied.

| Measurement | Result |
|---|---|
| Scope | 1,957 manifest rows = 1,000 current + **957** superseded; **931** superseded rows carry a `session_date` and are all checked |
| The 26 superseded rows not checked | **23** are content artifacts whose digest is meant to move (`cash_equity_symbol_intervals.csv` 6, `corporate_actions.jsonl` 4, `calendar_reconciliation_2022_2026.json` 3, `configs/trading_calendar_nse.json` 3, circulars 7) and each has exactly one current row; **3** are circulars with no current row at all. Scoping them out is correct: a content artifact is superseded *because* its content changed |
| Committed tree | **0** divergences across 931 rows, `(0 problem(s))` |
| **T1 — superseded `sha256` edited** (`data/raw/2018/cm02APR2018bhav.csv.zip`) | certificate **exit 1**, naming the field; suite **2 failed / 2 passed** (`…keep_their_archive_fields` and `…edited_superseded_sha256_is_refused`, the latter because its own "committed row is intact" control now fails) |
| **T2 — superseded `retrieved_at` edited** | certificate **exit 1**, `931 (1 problem(s))` |
| **T4 — superseded `gating_mode` edited** | certificate **exit 0** — correct: a relabel is what a supersession is allowed to move |
| **T3 — a superseded row deleted** | certificate **exit 0**, `COVERED — 931/931 …`; suite **4 passed** |

T3 is the hole: the check verifies that a superseded row, *if present*, still attests its archive, and nothing pins how many there are. §93.2 adopted "the prior row survives" as the acceptance wording, and a deletion satisfies every assertion made today. Registered as **N-179**. The item itself named only the edit probe, which passes, so it is **CLOSED as ordered** with the deletion hole as the new finding.

### 94.4 §93.5 Ruling 3 — the refusal is measured, every precondition is true, and the run is correctly blocked

`run_seq10_candidate.py` refuses before it registers anything, and the refusal names its evidence. Each claim in it was re-measured independently rather than read:

| Claim in the refusal | Measured at `0287aae` |
|---|---|
| The committed snapshot covers 2022+ only | `historical_dev_dataset_2022_2024.json` / `.gz`: `2022-01-03..2024-12-31`, `adjustment_version=v1.4`, `corporate_actions_fingerprint=CA-FPR-6d7aae6d8…` — neither covers `2018-04-01..2023-12-29`, so both are rejected by the coverage test, not by their name |
| **74** pre-2022 split/bonus ex-dates | **74** `SPLIT`/`BONUS` rows (`SPLIT` 72, `BONUS` 2) with `ex_date < 2022-01-03`, over **71** distinct ex-dates, out of 5,016 CA rows of which 4,533 pre-date 2022 (`DIVIDEND` 4,357, `ISIN_TRANSITION` 102, split/bonus 74). The count is right; the noun is approximate — 74 rows, not 74 distinct dates |
| `data/silver/bhavcopy` holds no partitions | **0** entries (`data/silver/bhavcopy` and `data/silver/price_bands` both empty) |
| Defect 1 — `symbols_by_instrument` is not a fingerprint parameter | `compute_legacy_dataset_content_fingerprint(trading_dates, prices_by_instrument, benchmark_prices=None, legacy_adjustments=None)` at `contracts/legacy_compat.py:49`, while `run_phase3b2_walkforward.py:645-649` passes `symbols_by_instrument=symbols_by_isin` — a latent `TypeError` on the fallback path only |
| Defect 2 — `PriceConvention.UNADJUSTED_CLOSE` no longer exists | `contracts/dataset.py:30-34` holds `UNADJUSTED_RAW`, `SPLIT_BONUS_ADJUSTED`, `FULLY_ADJUSTED`; `run_phase3b2_walkforward.py:655` names `UNADJUSTED_CLOSE` — a latent `AttributeError` on the same path |

| Refusal / certificate measurement | Result |
|---|---|
| `run_seq10_candidate.py` | **exit 1**, `NOT REGISTERED — no committed corpus covers … with split/bonus-adjusted prices derived from the committed corporate-action table`, naming both candidate snapshots |
| `probe_seq10_candidate.py` | **exit 1**, `NOT CERTIFIED`; `Registry: N = 9 (expected 9), N_eval = 5, seq 10 rows = 0`; `Registry manifest 3326b1b221b2e026… vs criteria pin 3326b1b221b2e026…`; `Corpus check: ABSENT` |
| Sealed-era refusal | the certificate drives the engine at `2025-01-02..2025-03-31` and gets `HoldoutSealedError` — `Requested evaluation window [2025-01-02..2025-03-31] touches sealed Holdout partition` |
| Registry containment | 9 rows, seqs `1..9`, 5 evaluation rows, `git status` clean after both script runs; no row's provenance names `data/raw/2025`, `data/raw/2026` or `2025-01-01` |
| Ruling-3 invariants | **N = 9** (not 10), **N_eval = 5**, criteria **1.1.14**, pin **3326b1b2…**, validation **2024** frozen in `configs/partition_spec.yaml`, holdout `2025-01-01..2026-11-11` sealed with the all-zero token hash |

The block is honest and the state is preserved. Two latents survive it:

1. **The registration path and the certificate disagree about the fold (N-180).** `probe_seq10_candidate._expected_fold_fingerprint()` builds the fold the authorised window implies — train `2018-04-01..2022-12-30`, test `2023-01-02..2023-12-31`, embargo 0, `IN_SAMPLE` — and gets `FOLD-SPEC-V1-36a39987dcade377…`. `run_seq10_candidate._register` copies `fold_spec_fingerprint=template["fold_spec_fingerprint"]` from the last registry row (seq 9), whose value is `FOLD-SPEC-V1-4b44a1f2…`. Measured: the two differ. A run that cleared the corpus precondition would therefore append a row the certificate is built to refuse — after `N` had already moved to 10. Fail-closed at the certificate, mutating at the registry.
2. **The engine's in-sample fold is hardcoded.** `run_phase3b2_walkforward.py:1024-1032` fixes train `2022-01-03..2022-12-30` / test `2023-01-02..2023-12-29`, `:1732` derives the artifact's `window` from that fold, and `:2616` carries the literal `2022-01-03 .. 2023-12-29 (In-Sample only; 2024 Validation FROZEN)`. So the runner's own second precondition (`in_sample_metrics['window']` must equal the requested window) would refuse the run even with a corpus in place — the block is two-deep, not one.

Nit, measured: the committed `RATIONALE` names `criteria 1.1.13` for the binding start while the tree loads 1.1.14. The string would be written into the registry row verbatim; a trial row may not misstate the criteria version it ran under.

### 94.5 Phase verdicts

| Phase | Verdict at `0287aae` | Named residuals |
|---|---|---|
| `§12.4` / `§14.4` §93.7 item 2 — engine → harness seam | **CLOSED as ordered** — AST check, mutation self-check, 3 seam tests + 1 passthrough test, both named mutations fail closed | reachability is unasserted (N-178); the only run-time witness, `probe_hold_bound_invariance.py`, is not gated |
| `§10.1` / `§10.5` §93.7 item 3 — superseded rows | **CLOSED as ordered** — 931/931 checked, 0 divergences, digest/byte-count/URL/retrieval-date/session edits refuse | a deleted superseded row is invisible (N-179); the 26 undated rows are out of scope by design (23 content artifacts, 3 circulars with no current row) |
| `§13.2` / Phase 3B-2 §93.7 item 1 — seq 10 | **BLOCKED, correctly** — refusal names a measured corpus block, certificate `NOT CERTIFIED`, N and N_eval unchanged, 2024 frozen, holdout sealed | corpus + expanded fold are the blockers (work order 1–2); the runner would register seq 9's fold (N-180); a stale `1.1.13` in the rationale |
| `§10.8` labels / certificate | **PASS** — `931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE` under criteria 1.1.14 | — (carried from §93.2) |
| `§10.8` A1 / A2 / A4 / A5 | **PASS** — READY 9/9 on the expanded window | A5 still evaluates the post-2022 verdict corpus only |
| Trials / fold / holdout | **N = 9 / N_eval = 5**, `data/trials/` unchanged, 2024 fold frozen, holdout sealed | seq 10 remains unregistered |
| Gate / cache | **GO** — 552 passed, 9/9 verifiers, tree `4a273db3…` already recorded, no duplicate row | — |

### 94.6 Work order for feat-s95

Ordered by what it unblocks. Items 1–3 are one chain: the corpus, then the fold, then the run.

1. **Build the derived-layer `SPLIT_BONUS_ADJUSTED` 2018–2023 corpus** (serves `§5.4`, `§10.3`, `§13.2`; unblocks seq 10). Two admissible routes; the certificate reads the header contract, not the route.
   - *Route A (Silver → Gold, preferred).* Promote the **931** attested Bronze archives `2018-04-01..2021-12-31` into `data/silver/bhavcopy/` as one append-only partition per session, atomic on promotion, prices and turnover persisted as `DECIMAL` and read back as `Decimal` (§10.1, §10.6, §10.7); then derive with `GoldEngine(SilverStorage, TradingCalendar, SecurityMaster)` over the committed 5,016-row corporate-action table.
   - *Route B (attested back-adjustment).* Back-adjust the same raw archives with exact integer split/bonus ratios applied strictly before each ex-date, adjusting the price side only.
   - *Either route must write* a snapshot matching `data/reference/historical*dataset*.json*` whose header declares `start_date` ≤ `2018-04-01`, `end_date` ≥ `2023-12-29`, a non-empty `adjustment_version`, and `corporate_actions_fingerprint` equal to `sha256` of `data/reference/corporate_actions.jsonl`.
   - *Adjustment rules, non-negotiable:* the **74** pre-2022 `SPLIT`/`BONUS` rows (71 ex-dates) are price adjustments; the **102** pre-2022 `ISIN_TRANSITION` rows are identity events that are never stitched across; the **4,357** dividends are held-position cash inflows, never price adjustments; no forward-fill, no interpolation, and a missing expected session fails closed with the window partitioned rather than bridged (§6.3, §13.2).
   - **Probe:** `python scripts/probe_seq10_candidate.py` prints `Corpus check: available at …` instead of `ABSENT`; `python scripts/run_seq10_candidate.py` clears the corpus check and stops at the fold precondition (item 2); a corpus that covers 2022+ only, omits `adjustment_version`, or carries a `corporate_actions_fingerprint` other than the committed digest is still refused with exit 1. Today: exit 1, `NOT REGISTERED`.
2. **Define the expanded in-sample fold as committed configuration** (serves `§12.4`, `§93.5 Ruling 3`; unblocks seq 10). Replace the hardcoded fold at `run_phase3b2_walkforward.py:1024-1032` and the literal at `:2616` with a fold derived from the requested window: **train `2018-04-01..2022-12-30`, test `2023-01-02..2023-12-31`, `embargo_sessions=0`, `partition_role=IN_SAMPLE`**, i.e. `FOLD-SPEC-V1-36a39987dcade377…`, with validation `2024-01-01..2024-12-31` unchanged and frozen. The definition is committed **before** the run (§9.2): the certificate already encodes this expectation, so this item makes the rule explicit rather than adding a threshold. If the maintainer prefers `2023-12-29` as `test_end`, that is a fold change and must be recorded before execution, never after seeing a result (§8.2).
   - **Probe:** the artifact's `in_sample_metrics['window']` reads `2018-04-01 .. 2023-12-31`; the registered row's `fold_spec_fingerprint` equals `FOLD-SPEC-V1-36a39987…`; `probe_n180` is flipped to assert that agreement. Today: `4b44a1f2…` vs `36a39987…`, and `probe_n180` passes on the disagreement.
3. **Register and run candidate seq 10 after items 1–2** (serves `§13.2`, Phase 3B-2). One registry row: `N` 9 → 10, `evaluation_count` **5**, criteria **1.1.14** in both the row and the `RATIONALE` text (today the constant says 1.1.13), in-sample `2018-04-01..2023-12-31`, validation 2024 frozen, manifest re-pinned by measurement, no path under `data/raw/2025` or `data/raw/2026` in its provenance; the artifact carries `hold_bound_forced_exits` and `hold_bound_refusals`; the comparator is the current-tree baseline run written to `reports/analysis/s94/`, with the bound-disabled counterfactual reporting **0** forced exits. **Probe:** `probe_seq10_candidate.py` exits 0 at `CERTIFIED`; a row whose window, version, fold or pin disagrees with the criteria fails it; an evaluated session on/after `2025-01-01` fails closed through `HoldoutSealedError`; a baseline block naming `reports/verdicts/…` or criteria `1.1.5` is refused (already measured in the certificate's two mutant arms, which only execute once a row exists).
4. **Repair or retire `build_historical_dataset_from_raw_bhavcopy`** (serves `§7.4`, `§10.3`). Two lines, named: `:648` passes `symbols_by_instrument=`, which `compute_legacy_dataset_content_fingerprint` does not accept; `:655` names `PriceConvention.UNADJUSTED_CLOSE`, which does not exist. Either fix both and assert the fallback's snapshot declares `ProvenanceStatus.CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`, or delete the function and any caller — a dead fallback that raises is a §14.4 path beside the live one. **Probe:** constructing it over a two-archive fixture produces a dataset whose `price_convention` is stated, or `grep` finds no reference to the symbol anywhere in `src/` and `scripts/`.
5. **N-178 — assert the seam's reachability, not only its shape** (serves `§12.4`, `§14.4`). Either drive one session through `run_phase3b2_walkforward`'s loop and assert non-zero forced exits, or assert that the call's enclosing function is the session loop. **Probe:** the dead-guarded mutation in §94.2 (live call beneath `if forced_exits is None:`, keyword intact) makes `probe_n177` exit 1 and a committed test fail; today both stay green.
6. **N-179 — pin the superseded-row count** (serves `§10.1`, `§10.5`). A count, or a digest over the superseded session rows, must be asserted against a committed value so that removal is a failure rather than a smaller check. **Probe:** deleting one superseded session-dated row makes the Bronze certificate exit 1 and name the missing artifact; today exit 0 at `931/931`.
7. **N-150 — `CRIT-OVERFIT-06` needs a second fold or a recorded admission** (carried, MEDIUM). **Probe:** the verdict bundle names the fold count it used, and a `PASS` on fewer than two folds fails closed.
8. **The replay counter's `get` and `popitem`** (carried, `§92.10` item 6). **Probe:** `probe_n174` asserts the accessor set it can measure, so a narrowed counter fails it.
9. **Restate the Phase 2D artifact's timestamp** (carried, LOW). **Probe:** the artifact's `timestamp_utc` is later than its `criteria_version`'s effective date, or a `restatement_history` block names each version it has carried.

### 94.7 What would falsify this verdict

- If the passthrough check still passed with the keyword deleted, item 2 was applied additively. Measured: `probe_n177` exit 1 and one test failing on that mutation.
- If an edited superseded `sha256` still certified, item 3 was a print rather than a check. Measured: certificate exit 1 naming the field, two tests failing.
- If N-178 were a branch no reviewer could ever write by accident, calling it a finding would overstate the risk. Measured: the tree parses, the four tests pass, and `probe_n177` prints `PASS N-177`, so nothing in the gate distinguishes it.
- If `run_seq10_candidate` had registered a row, the block would be a report rather than a refusal. Measured: exit 1 before any write, registry still 9 rows / 5 evaluations.
- If the corpus it refuses over actually existed, the block would be a false NOT RUN. Measured: both committed snapshots declare `2022-01-03..2024-12-31` and `CA-FPR-6d7aae6d8…`; `data/silver/bhavcopy` is empty; the alternative path raises at two named lines.
- If N-180 were harmless because the certificate catches it, the registry would still have moved to 10 before the catch. Measured: the two fold fingerprints differ, and `_register` writes the template's.
- If a superseded row's `gating_mode` were meant to be pinned too, §94.3's T4 would be a missed failure rather than a correct pass. Measured: the relabel is exactly what the flip moves, so it is excluded by design.

## §95 — Audit of `77fb043` (tag `feat-s95-77fb043`): the corpus reproduces bit-for-bit and then charges its own fake returns, the three checks close with one hole apiece, and the panel built to carry seq 10 is a survivor set

**Date:** 19 November 2026
**Commit under review:** `dcfbe35` (17 files, +1,006/−101: the 433-line corpus builder, the fold derived from the requested window at `run_phase3b2_walkforward.py:724-778` and `:1090`, the superseded-row count pin in the Bronze certificate, five tests in `test_phase3b2_audit_s95_items.py`, the criteria bump 1.1.14 → 1.1.15, and the 45.5 MB corpus artifact with its manifest row) and `1ccf341` (3 files, +20/−6: the Phase 2D Tier-A restatement under 1.1.15), plus `77fb043` (the green-cache row, +19 lines). None of the three touches a path under `reports/audit/`, `data/trials/`, `data/raw/2025`, `data/raw/2026` or `configs/partition_spec.yaml`.
**Verdicts:** **§94.6 item 5 CLOSED as ordered** (N-178) · **item 6 CLOSED as ordered** (N-179) · **item 2 CLOSED as ordered** (N-180) — each carrying one named residual rather than a reopening · **§94.6 item 1 PARTIAL** — the artifact exists, reproduces exactly from 1,425 committed archives, and its ratio arithmetic is correct on every row it applies, but its adjustment table is not the archive's and its panel is not a universe · **§7.2 refusal PASS** on a live, measured precondition, with the provenance of the schedule it refuses on as the next blocker · **Ruling 1:** the full-span filter is a continuity construct and is inadmissible as a point-in-time universe · **Ruling 2:** an adjustment row is admissible only where the committed archive and the panel's own prices both attest it.

### 95.1 Baseline re-measured at `77fb043`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Suite under the gate | **557 passed in 188.07 s**, **0 skipped / 0 xfailed** — 552 at `0287aae`; the five added are `test_phase3b2_audit_s95_items.py`'s |
| Verifiers | **10/10 exit 0**. The tree has carried ten `scripts/verify_*.py` since before `0287aae` (`git ls-tree`), so §94.1's "9/9" was one short; no script was added here |
| W0.5-4 / W0.5-5 | every tag verified, including `feat-s95-77fb043` → `77fb043`; **1,001** current artifacts match byte count and sha256, **958** superseded rows skipped as history |
| Green cache | source tree `e26be07f…` already recorded at this commit; the forced run printed `already recorded; not appending a duplicate row`; `git status` clean before and after |
| Findings ledger | **52** rows / **32** ids; latest-per-id **27 CLOSED**, **4 OPEN** (N-150, N-178, N-179, N-180), **1 ACCEPTED** (N-152); `verify_audit_findings.py` **exit 0** inside the verifier sweep |
| Criteria / pins | **1.1.15**; `MAN-FPR-V1-4b813090cab7f9be555833039029b1882dc60b05485fb83c0e9dcaba76609c1d` recomputed over **1,867,504** bytes of `data/reference/manifest.jsonl` (matches); **97** leaves, **8** numeric; the 1.1.14 → 1.1.15 leaf diff is **2 changed leaves, 0 numeric** (`metadata.version`, `expected_manifest_fingerprint`) |
| Trials / fold / holdout | **9** rows, seq 1–9, **5** evaluation rows, pin `3326b1b2…` recomputed over `data/trials/trial_registry.jsonl.manifest` (matches); in-sample `2018-04-01..2023-12-31`, validation **2024** frozen, holdout `2025-01-01..2026-11-11` with the all-zero token hash; `data/trials/` byte-identical after every run below |
| `probe_audit_findings.py` | **N-177, N-178, N-179, N-180 all exit 0** (`PASS <id>`) |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931 … 931 of 931 pinned, 0 problem(s)` |
| `probe_pre2022_preconditions.py` | **exit 0, READY 9/9** — A1 246/245/252/248, A2 17,864/19,283 sessions, A4 **4,357** dividend ex-dates, A5 `0 of 4,903` before 2018-04-01 |
| `derive_2018_2023_corpus.py --check` | **exit 0** — `OVERALL: CURRENT — historical_dataset_2018_2023.json.gz reproduces the Bronze-derived header over 1425 archive(s)`; `Panel: 1082 instrument(s), 1541850 bar(s)`; `Observed ISINs: 2735; excluded short-span 1463, internal-gap 190`; `Adjusted instruments: 7 carrying 8 price-side action(s)` |
| `run_seq10_candidate.py` | **exit 1** — `NOT REGISTERED`, now on the cost schedule rather than the corpus |
| `probe_seq10_candidate.py` | **exit 1** — `NOT CERTIFIED`; `N = 9`, `N_eval = 5`, seq 10 rows 0; sealed-era arm raises `HoldoutSealedError` |
| `probe_hold_bound_invariance.py` | **exit 1** — `NOT INVARIANT`: **175** forced exits / **203** refusals, run B `0 / 0`, and **5/5** committed metrics fail to reproduce in **both** runs. Carried from §94.4, re-measured here |
| Files the code commits touch | 20 across `dcfbe35` + `1ccf341`; **no** path under `reports/audit/`, `data/trials/`, `data/raw/2025`, `data/raw/2026`, `configs/partition_spec.yaml` |

### 95.2 §94.6 item 5 — CLOSED as ordered: the seam's reachability refuses now, and a `for` body over an empty tuple still passes

N-178 asked for a check that can see the passthrough line *executed* rather than merely written. `_session_loop_passthrough_problem` now collects the call's enclosing statements while walking the module and refuses a call whose ancestors exclude a reachable context; `probe_n178` builds the mutation the item names. Attacks in the detached worktree at `77fb043`, each restored with `git checkout --`:

| Mutation | `probe_audit_findings.py N-178` | Committed test |
|---|---|---|
| none (control) | **exit 0**, `PASS N-178` | passed |
| the `if forced_exits is None:` guard of §94.2 row D (the ordered mutation) | **exit 1**, naming the unexecuted guard | failed, as intended |
| live call placed under `for _unreachable in ():` | **exit 0**, `PASS N-178` | passed |
| the keyword deleted outright | **exit 1** | failed |

The ordered mutation fails closed, so the item is **CLOSED as ordered** (§14.5). The residual is named, not smoothed: the ancestor walk tests `isinstance(cursor, (ast.If, ast.While, ast.Try))` (`probe_audit_findings.py:1892`) and nothing else, so a call a tuple literal can never reach is still accepted — the same §14.4 shape one statement-type narrower. Separately, `probe_n178`'s own text-surgery mutation raised `IndentationError` when the tree was edited under it; a probe that dies is a probe that cannot assert, and it belongs in the work order with the ancestor gap it was written to catch.

### 95.3 §94.6 item 6 — CLOSED as ordered: the count is pinned, so a deletion refuses; a deletion plus a fabricated replacement does not

| Mutation | Bronze certificate | `probe_audit_findings.py N-179` |
|---|---|---|
| none (control) | **exit 0**, `931 superseded session row(s) retain their archive digest and provenance` | **exit 0**, `PASS N-179` |
| one superseded session row deleted | **exit 1**, `930` vs the pinned `931` | **exit 1**, naming the same `930` |
| one superseded row duplicated | **exit 1**, `932` | **exit 1** |
| one row deleted **and** a synthetic superseded row appended carrying the current row's six archive fields | **exit 0**, `931/931` | **exit 0**, `PASS N-179` |

The ordered mutation (deletion) now fails closed, so the item is **CLOSED as ordered**. The residual: the pin is a **count**, so a substitution that preserves the count is invisible. Closing that requires identity — a digest over the ordered set of superseded `(artifact, sha256, session_date)` triples — and it is named in the work order rather than used to reopen the item.

### 95.4 §94.6 item 2 — CLOSED as ordered: the fold is derived from the window, on one of the two paths

`derive_in_sample_fold(calendar, eval_start, eval_end)` (`:724`) computes test as the evaluation year's sessions and train as every session before them, and `in_sample_fold_for_dates` / `in_sample_fold_fingerprint` read it from the anchored calendar once. Measured, not read:

| Window | Derived fold | `FOLD-SPEC-V1-…` |
|---|---|---|
| `2018-04-01..2023-12-31` | train `2018-04-01..2022-12-30`, test `2023-01-02..2023-12-31`, embargo 0, `IN_SAMPLE` | **`36a39987dcade377afd18ce6b544596d82b830f10c24314665dfa700e134fce7`** |
| `2022-01-03..2023-12-29` | train `2022-01-03..2022-12-30`, test `2023-01-02..2023-12-29` | **`4b44a1f25f3087e4c7e089834496b33a6a06753f06f9457094ae2a7cb1b972a3`** — identical to the last registry row (§14.5: the derivation reproduces the typed fold it replaced) |

| Mutation | `probe_audit_findings.py N-180` |
|---|---|
| none (control) | **exit 0**, `PASS N-180` |
| `WINDOW_END` moved to `2023-12-29` | **exit 1** — `FOLD-SPEC-V1-e31b8ae6…` vs `36a39987…`, the disagreement §94.4 measured |
| the template copy restored (`fold_spec_fingerprint` taken from the previous row) | **exit 1** |

Both mutations fail closed, so the item is **CLOSED as ordered**. Two residuals are named. First, the derivation runs only when `in_sample_only` is true (`:1090`); the walk-forward branch at `:1091-1100` still types `2022-01-03..2023-12-29` and ignores the requested window, which is the additive-fix shape §14.4 warns about, one `if` above the one that was fixed — harmless today because no validation run is authorised over the expanded window and 2024 is frozen outside the corpus. Second, a derived fold is still **one** train/test split; N-150's "second fold or recorded admission" is untouched by this item.

### 95.5 §94.6 item 1 — PARTIAL: the corpus is real, reproduces exactly, and is wrong in its universe and incomplete in its adjustments

`data/reference/historical_dataset_2018_2023.json.gz` — **45,565,892** bytes, sha256 `5926e1c2aea6c6c220f9452597bc2c525899598bced5beddd9c66b8ccd2982c5` (the current manifest row; the superseded row `aff57c09…`, 45,565,871 bytes, is one manifest line above it), `content_fingerprint DATA-CTNT-V2-1862c1f2f26c14bf3c48cb3521f2fda7`, `data_version EXP-DEV-2018-2023-V1`, `1,082` instrument ids, `1,425` sessions `2018-04-02..2023-12-29`, `1,541,850` bars, `adjustment_version v1.0-split-bonus-backadjust-2018-2023`, `corporate_actions_fingerprint 6ff7d3ed…` equal to the sha256 of `data/reference/corporate_actions.jsonl`.

#### 95.5.1 Form, provenance and what the artifact cannot express

The manifest row declares `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED` and its `retrieval_reference` says in terms that the artifact is derived, not retrieved, and names the builder and the action table it applied. That is the §6.5 / §10.2 discipline correctly applied to a derived artifact, and it is the reason the defects below are *scope* questions rather than provenance claims: nothing here overstates its own status. `--check` rebuilds in memory and compares header and every bar: `CURRENT`, and the sha256 is stable across the run.

What the artifact does not carry: **series**. Bars were drawn from `EQ`, `BE` and `BZ` (`derive_2018_2023_corpus.py:71`) but a bar stores only `instrument_id`, date, OHLC, volume and traded value, so the artifact cannot say which series a name was in on a date. This is not an entry-eligibility hole — the harness pins `explicit_series=ExchangeSeries.EQ` (`run_phase3b2_walkforward.py:1323`), so §13.1 is enforced at the call — but it means a reader of the artifact cannot verify the series mix the builder claims, and any future `BE`-eligibility question must go back to Bronze.

#### 95.5.2 The ratio arithmetic is exact wherever a row is applied

The five in-window applications on panel ISINs were recomputed against the raw bars: INFY 2018-09-12 ×0.5, IOC 2022-06-30, GAIL 2022-09-06, ASTRAL 2023-03-14, IDEA 2023-09-15 ×10 — each equals its row's `denominator/numerator` to the last quantised digit, applies strictly before the ex-date and leaves the ex-date bar at its traded level, volume and traded value untouched, and `cumulative_factor` composes multiple rows correctly. There is no float anywhere in the path, no interpolation, no forward fill and no zero-price bar (`derive_2018_2023_corpus.py:182-186` refuses a non-positive price rather than materialising it). **The arithmetic is not the problem. The table and the panel are.**

#### 95.5.3 The table is not the archive: 95 attested actions are missing, 44 of them on the panel

Committed Bronze carries **166** price-side attestations over **160** distinct `(ISIN, ex-date)` pairs (subject text matched on `split`/`sub-division`, `bonus`, `consolidation`). The committed table carries **85** price-side rows (75 `SPLIT`, 7 `BONUS`, 3 `CONSOLIDATION`). Set difference, measured both ways:

| Direction | Count | Composition |
|---|---|---|
| in the archive, absent from the table | **95** | **94 `BONUS`**, **1 `CONSOLIDATION`** (`INE743C01013` 2018-08-29, capital reduction), **0 `SPLIT`** |
| in the table, absent from the archive | **14** | 13 rows whose `circular_ref` begins `UNATTESTED_`, plus one `AVANTIFEED` 2018-06-26 row labelled `ATTESTED_NSE_CA_…` with no matching archive record |
| absent from the table **and** on a panel ISIN at a panel session | **44** | all `BONUS`; **34** of the 44 show a one-session move beyond **±25%** in the corpus, because a bonus is not a return |

The fourteen largest, from the panel:

| Ex-date | Symbol | Attested action | Corpus one-session return |
|---|---|---|---|
| 2021-10-13 | SRF | Bonus 4:1 | **−0.8069** |
| 2021-12-16 | KKCL | Bonus 4:1 | **−0.7997** |
| 2020-09-30 | AARTIDRUGS | Bonus 3:1 | **−0.7375** |
| 2021-09-14 | MAHLIFE | Bonus 2:1 | **−0.6715** |
| 2018-07-11 | UNOMINDA | Bonus 2:1 + dividend | **−0.6644** |
| 2021-03-18 | INFIBEAM | Bonus 1:1 | **−0.5718** |
| 2018-07-18 | MMFL | Bonus 1:1 | **−0.5350** |
| 2019-06-12 | BIOCON | Bonus 1:1 | **−0.5198** |
| 2018-07-12 | GICRE | Bonus 1:1 + dividend | **−0.5147** |
| 2019-07-09 | GAIL | Bonus 1:1 | **−0.5131** |
| 2018-09-11 | GLAXO | Bonus 1:1 | **−0.5130** |
| 2018-06-20 | EPL | Bonus 1:1 | **−0.5099** |
| 2018-06-27 | NIACL | Bonus 1:1 + dividend | **−0.5076** |
| 2018-08-08 | WHEELS | Bonus 1:1 | **−0.5072** |

Across the whole panel there are 1,540,768 one-session returns, `|r|>0.35` **88**, `>0.50` **47**, `>0.75` **11**, `>1.0` **1**. Attributed by date, the 88 are: **2** on a row the corpus applies (`INFY` **+1.0234**, `IDEA` **−0.8927** — both fabricated), **24** on an archive-attested action the table omits, **16** on a date the committed archive records *some* action (10 of them demerger, scheme-of-arrangement or merger rows, one an "Interim Dividend − Rs 974 Per Share" that is a demerger's own record date), and **46** on a date with **no archive record at all** — `BEL` 2022-09-15 **−0.6692**, `BSE` 2022-03-21 **−0.6681**, `GMMPFAUDLR` 2022-07-11 **−0.6467**, `AUBANK` 2022-06-09 **−0.5126**, `EMAMILTD` 2018-06-21 **−0.5061**, and 41 more. Several of the 46 are almost certainly real corporate actions the committed corporate-action payloads do not carry; the point that survives either way is that **on those dates the artifact cannot tell a corporate action from a crash**, which is exactly what an adjustment layer exists to settle. The builder prints no warning for any of them.

#### 95.5.4 The fourteen rows with no archive counterpart, and the one the archive contradicts

Thirteen of the fourteen carry `UNATTESTED_NSE_CML_*`, which is honest in form and unusable in effect. Five have ex-dates outside the window: `RELIANCE` 2017-09-07 is inert (its ex-date precedes every bar), `RELIANCE` 2024-10-28 applies ×0.5 to the whole series and is the correct back-adjustment for a 2024 bonus, and `NESTLEIND` 2024-01-05, `RCOM` 2024-03-22, `BPCL` 2024-06-21 are inert because their ISINs are not on the panel. Eight are applied inside the window. One of the eight is a **contradiction of committed evidence**:

- **INFY, `UNATTESTED_NSE_CML_2018_BONUS_INFY`, 2018-09-12.** The committed archive row says `exDate 04-Sep-2018`, `subject Bonus 1:1`. The table says 2018-09-12. The corpus therefore leaves 2018-09-04 unadjusted (**−0.4860** on the session the price actually halved) and then applies ×0.5 to every bar before 2018-09-12, so the 2018-09-12 return is **+1.0234** — the single `>1.0` observation in the panel, and the panel's largest. One correct 0% ex-date return is replaced by two fabricated ones, eight sessions apart, in a Nifty-50 name.
- **IDEA, `UNATTESTED_NSE_CML_2023_CONSOL_IDEA`, 2023-09-15, `CONSOLIDATION` 1:10.** No archive record of any price-side action for `INE669E01016` on or near that date, and no fall in the raw series: the corpus multiplies every earlier bar by 10 and prints **−0.8927** on 2023-09-15. This is a fabricated corporate action applied to a held-position series for the last three months of the window.
- The remaining six in-window unattested rows (`IOC` 2022-06-30, `GAIL` 2022-09-06, `ASTRAL` 2023-03-14, `LLOYDSENG` 2022-04-18, `TATASTEEL`-labelled `INE081A01012` 2022-07-28, `VBL` 2023-06-15) and the out-of-window `NESTLEIND`, `RCOM`, `BPCL` rows are unattested but not contradicted by anything committed — unverifiable rather than false, which is the difference between §6.5's two states and why they cannot be gating input either.

The single `ATTESTED_NSE_CA_2018-04-01_AVANTIFEED_20180626` row is the sharpest form of the same problem: a row that *says* attested and points at no committed byte. Either the attestation exists somewhere and the reference is wrong, or the label is the claim.

#### 95.5.5 The panel is a survivor set, and it removes almost exactly the names the table was built for

The builder's own header states the rule: *"1082 of 2735 observed ISINs: every session from 2018-04-02 to 2023-12-29 carries an exchange observation … 1463 ISIN(s) whose observations start after the first session or **stop before the last** are excluded"*, and `derive_2018_2023_corpus.py:204` implements it as `min(rows) != first_session or max(rows) != last_session → skip`. Measured consequences:

| Measurement | Result |
|---|---|
| ISINs trading on 2018-04-02 (the window's first session) | **1,646** — 1,505 `EQ` + 118 `BE` + 23 `BZ` |
| of those, in the panel | **1,082** (every panel member trades on day one) |
| of those, excluded from **every** date in the panel | **564 — 34.3%** |
| panel members per date | **1,082 on all 1,425 dates**; `universe_by_date` is the identical list 1,425 times |
| excluded in total | 1,653 of 2,735 (60.4%) — 1,463 short-span, 190 with an internal gap |
| table rows that touch the panel | **8** of **85**; **2** of the **74** pre-2022 rows (`INFY` 2018-09-12, `RELIANCE` 2017-09-07) |

The last row is the interaction that matters. The 74 pre-2022 split/bonus rows this artifact exists to apply sit almost entirely on names the filter deleted, and on the panel the net position is **2 rows applied against 44 attested actions missing**. The corpus's pre-2022 adjusted coverage of its own panel is therefore negative: it fabricates two returns on one name while leaving 44 unadjusted bonus drops in place, 34 of them beyond ±25%.

Two things are true at once and both are measured. The continuity requirement itself is legitimate — §6.3 forbids computing a lookback across an unexplained gap, and requiring an observation on every session is a clean way to guarantee that. Selecting **membership** by it is not: a name that stops trading in 2021 is dropped from 2018 as well, which is exactly `§6.1`'s "never select universe constituents based on … survival". And the requirement is not even necessary for continuity, because the engine already partitions on gaps independently (`IndicatorValidationError` refusals, `continuous_instruments_passed`, `fail_closed_on_unexplained`) — the filter is a second, cross-sectional copy of a per-series rule.

#### 95.5.6 Holding-period events: 32 attested demergers, none of them a type

The table's action types are `BONUS` 7, `DIVIDEND` 4,495, `SPLIT` 75, `ISIN_TRANSITION` 426, `CONSOLIDATION` 3, `RIGHTS` 4, `MERGER` 3, `DELISTING` 3 — 5,016 rows. There is no `DEMERGER` type and no row mentions one. The archive attests **32** demerger events in the window, of which **1** has any table row at the same ISIN and date and **28** sit on panel ISINs, with one-session moves of:

`SUVEN` 2020-01-21 **−0.9471**, `GFLLIMITED` 2019-08-06 **−0.8911**, `AGI` 2019-08-19 **−0.7371**, `ARVIND` 2018-11-28 **−0.6509**, `TATACHEM` 2020-03-04 **−0.5653**, `THOMASCOOK` 2019-12-05 **−0.5555**, `CENTURYTEX` 2019-10-11 **−0.5536**, `DCM` 2019-05-30 **−0.4903**, `ANANTRAJ` 2020-10-06 **−0.4386**, `DEEPENR` 2020-11-10 **−0.3853**, `TATACOMM` 2019-09-17 **−0.3481`, and 17 more between −0.03 and −0.26.

§13.2 requires a corporate action inside a holding window to be applied to the open position, and a demerger delivers shares in the resulting entity — so a position carried through one of these dates is booked as a −65% to −95% loss and the consideration is never credited. The corpus is not the ledger, so this is not yet a P&L error; it becomes one the moment a gating run holds a name across any of these 28 dates, and today there is no action type with which to book it.

#### 95.5.7 Two counts in prose that the artifact contradicts

`configs/go_no_go_criteria.yaml:132` and `scripts/run_seq10_candidate.py:31` both say the corpus holds **1,061** ISINs. The artifact, the builder's own `--check` output and the certificate all say **1,082**. The builder's counters are internally consistent (7 instruments carrying 8 price actions, matching the header); only the two comments are stale. This is a prose number in a file that gates a run, and it is fixed with the rebuild below rather than separately.

### 95.6 Ruling 1 — the full-span filter is a continuity construct, not a universe, and it may not carry a gating evaluation

*The artifact's `universe_by_date` is admissible only as a continuity panel. It is inadmissible as the point-in-time universe of any gating evaluation, including candidate seq 10.*

The reason is literal (§6.1): membership is conditioned on trading on the window's **last** session, so a name delisted, merged, suspended or simply illiquid after 2021 is removed from 2018–2020 as well. Measured, that is 564 names — 34.3% of the securities trading on the window's first day — deleted retroactively, and a panel that is the identical 1,082-name list on all 1,425 dates. A backtest over it cannot lose a name that died, which is the definition of survivorship.

The remedy is not a relabel, and the repository already contains the correct construction: `build_historical_dataset_from_raw_bhavcopy` (`run_phase3b2_walkforward.py:556`) builds `universe_by_date` as **exactly the ISINs that traded that session** from the same committed archives, with no full-span requirement, and that is the route trials 1–9 ran through. So the 2018–2023 window does not *need* a survivor panel to be loadable; the filter was a choice, and it is the one thing that makes the new artifact unusable where the old route was usable.

What this ruling does **not** do is block §94.6 item 3. Candidate seq 10 may be registered and run on this corpus as a **non-gating pipeline measurement** under the §94.5 Ruling: registering it is required by §8.2's trial accounting, and the claim it supports is that the pipeline executes end-to-end over 2018–2023 — not that any number in it estimates a return. A gating verdict, a DSR, or a comparison against trials 1–9 computed on this panel would be a report of a survivor set, and is refused until the panel is rebuilt point-in-time.

### 95.7 Ruling 2 — an adjustment row is admitted only where the archive and the panel's own prices both attest it

*An adjustment may be applied to a gating series only when (a) a committed Bronze corporate-action record attests the same ISIN, action type and ex-date, and (b) the panel's own prices move at that ex-date in the direction and magnitude the ratio implies. The build fails closed on any archive-attested action it lacks for an in-panel ISIN.*

Both halves are necessary and neither is sufficient. Attestation alone cannot catch a row that is real but dated wrong — the INFY row is the demonstration: it is a genuine bonus for a genuine ISIN, and the archive dates it eight days earlier, which is why checking the ex-date is not a formality but the whole check. Price confirmation alone cannot catch a ratio that happens to match a move caused by something else. Together they would have caught all three defects found here: the INFY date (archive mismatch), the IDEA consolidation (no archive record **and** no price move), and the 44 missing bonuses (archive record **and** a −50% move with no row to explain it).

The ruling applies to the archive as well as the table, and the archive falls short of it on its own terms: **46** panel returns beyond ±35% sit on dates for which the committed corporate-action payloads hold no record whatsoever (`BEL` 2022-09-15, `BSE` 2022-03-21, `AUBANK` 2022-06-09, `GMMPFAUDLR` 2022-07-11, `EMAMILTD` 2018-06-21, `MIRZAINT` 2023-03-29, `NDLVENTURE` 2022-11-22, and 39 more). Whether those are actions whose payloads were never captured, or actions captured under a different `exDate` (the INFY failure mode), cannot be decided from this repository — and either way, no adjustment layer can be attested against an action set that is itself incomplete. Reconciling those 46 dates is therefore a precondition of attesting anything, not a refinement of it.

Under this ruling the committed artifact is **not** gating input today, for two independent reasons: its universe fails Ruling 1 and its adjustment set fails this one. The builder's own honest provenance (`CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`) is the correct label for what it is — a derived panel whose sources are named but whose content is not attested — and it is what keeps this a scope refusal rather than a provenance overclaim.

### 95.8 §7.2 — the statutory-cost refusal is live, correct, and standing on rows that no committed byte attests

`run_seq10_candidate.py` refuses with `NOT REGISTERED — … the earliest exchange-fee row starts 2021-01-01 … the first session 2018-04-02 has no governing NSE circular`. Re-measured rather than read: with the earliest fee row's `from_date` monkeypatched to `2018-01-01`, `2018-04-02` passes (`problem None`) and `2018-04-03` and `2019-01-01` still refuse, each naming the first uncovered session — so the refusal is a boundary, not a blanket. The registry stayed at 9 rows / 5 evaluations, `data/trials/` was byte-identical afterwards, and the sealed-era arm still raises `HoldoutSealedError`. **The §7.2 refusal works.**

What it refuses on is thinner than it looks:

| Component | Representation at 1.1.15 | Attested by committed bytes? |
|---|---|---|
| exchange turnover charge + IPFT | 5 interval rows `2021-01-01 → null`, keyed by `circular_ref` (`NSE/FA/46730`, `56129`, `61137`, `64323`, `73061`) | **No.** `data/raw/circulars/` holds **20** files and every one is a CMTR/MSD trading-calendar circular; there is **no `NSE/FA/*` payload for any period**, so even the 2021+ rows are attested by a string in a YAML file |
| STT (delivery and intraday), stamp duty (delivery and intraday), SEBI turnover, GST, brokerage | **single scalars**, no date dimension | No, and structurally cannot be: a scalar cannot represent a within-window statutory change even in principle (§10.5's interval-table rule applied to costs) |

Two consequences follow, both measured in the file rather than argued from outside it. First, the schedule cannot represent a rate that changed inside `2018-04-01..2023-12-29` at all, so a session in 2018 and a session in 2023 are charged the identical stamp duty and STT by construction; whether each scalar equals the rate that governed 2018, 2023, or neither is **not determinable from this repository**, because no circular bytes exist to check it against. Second, the same field carries `ipft_rate 0.000000001` for `2021-01-01..2023-03-31` and `0.000001` from `2023-04-01` — a **1,000×** step in adjacent rows of the same schedule, with the second row's own description calling it the "revised ₹10/cr IPFT". One of the two rows is wrong by three orders of magnitude (worth ~0.0001% of turnover), and only a sourced circular can say which.

So the block on seq 10 is not a corpus problem, a fold problem, or a code problem. It is the §7.2 requirement that a cost schedule be attested, met by a schedule whose exchange rows have no bytes and whose statutory rows have no dates.

### 95.9 Phase verdicts

| Phase | Verdict at `77fb043` | Named residuals |
|---|---|---|
| `§12.4` / `§14.4` §94.6 item 5 — seam reachability | **CLOSED as ordered** — the ordered guard mutation refuses, keyword deletion refuses, a committed test binds both | a call under `for _unreachable in ():` still passes (ancestor set lacks `ast.For`); `probe_n178`'s text surgery raised `IndentationError` under edit |
| `§10.1` / `§10.5` §94.6 item 6 — superseded rows | **CLOSED as ordered** — 931 pinned, deletion and duplication both refuse and name the count | count pinned, identity not: delete-plus-fabricate passes |
| `§12.4` §94.6 item 2 — derived in-sample fold | **CLOSED as ordered** — `36a39987…` for the expanded window, `4b44a1f2…` reproduced for the old one, both mutations refuse | derivation only on the `in_sample_only` path; the walk-forward branch still types the 2022–2023 fold; one split is not a walk-forward (N-150 open) |
| `§5.4` / `§10.3` §94.6 item 1 — derived corpus | **PARTIAL** — artifact exists, 45,565,892 bytes, reproduces exactly from 1,425 archives, exact Decimal ratios, honest `CONTENT_IDENTIFIED_ONLY` label | universe is a survivor set (§95.6); 95 attested actions missing (44 on the panel, 34 beyond ±25%); 14 rows unattested, one contradicted (INFY +1.0234), one fabricated (IDEA −0.8927); 46 dates where the panel moves beyond ±35% and the committed archive holds no record at all; no `DEMERGER` type for 28 in-window events; two prose counts say 1,061 |
| `§7.2` — statutory cost schedule | **PASS** on the refusal — live boundary, registry and holdout intact | the schedule it refuses on has no circular bytes for any period and no date dimension for STT/stamp/SEBI; IPFT rows differ 1,000× |
| `§13.2` / Phase 3B-2 item 3 — seq 10 | **BLOCKED, correctly** — `NOT REGISTERED` on the cost precondition, `NOT CERTIFIED`, `N = 9`, `N_eval = 5` | the block now sits exactly on §7.2 sourcing (work order 1) |
| `§10.8` labels / A1 / A2 / A4 / A5 | **PASS** — `931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE`; READY 9/9 on the expanded window | A5 still evaluates the post-2022 verdict corpus only (carried) |
| Gate / cache | **GO** — 557 passed, 10/10 verifiers, tree `e26be07f…` already recorded, no duplicate row | §94.1's verifier count was one short; corrected here |

### 95.10 Work order for feat-s96

Ordered by what it unblocks. Items 1–2 unblock the cost precondition seq 10 refuses on; items 3–5 make the corpus usable at all; item 6 is the registration step that lets §96 close what this section can only name.

1. **Source and commit the exchange-charge circular bytes for every fee row, starting with `2018-04-01..2020-12-31`** (serves `§7.2`, `§10.7`; unblocks seq 10's cost precondition). The pre-2021 cash-equity turnover circular is the specific gap the refusal names, but the 2021+ rows (`NSE/FA/46730`, `56129`, `61137`, `64323`, `73061`) are unattested too, and fixing only the first would leave four rows asserting rates no committed byte supports. Each row gains `circular_sha256` resolving to a byte-exact payload under `data/raw/circulars/<ref>/` with its manifest line (URL, retrieval timestamp, byte count, sha256), and the schedule gains a row whose `from_date` covers `2018-04-02`. **Probe:** `statutory_cost_schedule_problem(2018-04-02)` returns `None` **because** a covering row's `circular_sha256` resolves to a committed file — today that passes only when a synthetic row is monkeypatched in, and no row carries a digest at all; a row whose digest resolves to no committed byte fails closed.
2. **Resolve the 1,000× IPFT step and give the statutory scalars a date dimension** (serves `§7.2`, `§10.5`). `ipft_rate` is `0.000000001` for `2021-01-01..2023-03-31` and `0.000001` afterwards; the circular text settles which. STT, stamp duty and the SEBI turnover charge are scalars over a 5.7-year window, so a within-window change cannot be represented at all — either convert them to interval rows under the same attestation discipline, or commit a decision file that names the span and the source for each rate and states that no change falls inside it. **Probe:** a session either side of any re-rated component is costed from different rows, or the decision file names each rate's span and source; a scalar schedule with no decision file fails closed.
3. **Rebuild the corpus with a point-in-time universe** (serves `§6.1`, `§5.4`, `§13.2`; Ruling 1). `universe_by_date[D]` is the ISINs that traded on `D`. Continuity keeps its role for **feature windows** (the engine already refuses a lookback spanning an unexplained gap) and loses it as a membership condition. Record `universe_selection` as the rule, not as the outcome, and fix the two `1,061` prose counts while touching them. **Probe:** `universe_by_date` differs between `2018-04-02` and `2018-12-31`; the 564 names trading on the first session appear on the dates they traded; a name whose observations stop in 2021 is absent after its last session and present before it, rather than missing from all 1,425 dates.
4. **Attest the adjustment table against the archive and fail the build on any gap** (Ruling 2; serves `§5.4`, `§6.5`, `§13.2`). Add the **94** missing `BONUS` rows (44 on panel ISINs at panel sessions, 34 beyond ±25%), correct INFY's ex-date to `2018-09-04`, resolve or delete the IDEA consolidation (no archive record, −0.8927 fabricated), replace the `ATTESTED_NSE_CA_…` AVANTIFEED reference with a real digest or relabel it, and attach `source_digest` to every row. First reconcile the **46** dates at which the panel moves beyond ±35% and the archive holds no record at all (§95.7): each is either a payload to capture or an `exDate` to correct, and until each is one or the other no completeness claim can be made. **Probe:** a builder run over a table missing one archive-attested action for an in-panel ISIN exits non-zero naming the action; a row whose ex-date disagrees with the archive fails closed; every panel return beyond ±35% is explained by an applied row or by an archive record at that ISIN and date, and any that is not fails the build with the ISIN and date printed (today: **46** dates, **88** returns, **62** unexplained by the adjustment layer).
5. **Add a `DEMERGER` / merger-consideration action type and exercise it on a held position** (serves `§13.2`). 32 attested events, 28 on the panel, 1 table row, 0 typed. **Probe:** a position held across a demerger ex-date books the consideration (or is force-exited with a reason) instead of realising the raw −65%…−95% drop; today no type exists to book it.
6. **Register probes for the corpus defects before registering the findings** (serves `§9.1`, `§14.2`). §95.5 measures five defects and registers **no** ledger rows, because `verify_audit_findings.py` executes every row's probe and no committed probe asserts them yet — a row without an executable probe would either fail the gate or be a row that cannot fail. **Probe:** `probe_audit_findings.py N-181`…`N-185` exist and exit 0 on the defect (survivor filter, missing bonuses, INFY date, IDEA row, demerger type); §96 then registers them with those commands. Do not add the rows first.
7. **A registry row whose metrics do not reproduce** (carried, `§94.4`, re-measured here). `probe_hold_bound_invariance.py` exits 1: 175 forced exits / 203 refusals, and **5/5** metrics fail to reproduce even with the consumer disabled (run B: 194 closed trades vs 193 committed, `end_equity` 1,164,053.76 vs 1,283,327.73). The engine moved after seq 9 ran, so `TRIAL-PHASE3B2-RANKED-009`'s committed numbers cannot be regenerated by this tree. Either annotate the row `NON_REPRODUCIBLE_AT <sha>` with the measured divergence, or re-run and restate it. **Probe:** a registry row whose committed metrics do not reproduce under the current tree is refused by the certificate, or carries the annotation and the divergence.
8. **Carried, unchanged:** N-150 (`CRIT-OVERFIT-06` needs a second fold or a recorded admission); the replay counter's `get`/`popitem` (§92.10 item 6); the Phase 2D artifact's `timestamp_utc` still `2026-11-16T10:00:00+00:00` (LOW).

### 95.11 What would falsify this verdict

- If the ordered N-178 mutation still passed, item 5 would be unclosed. Measured: `probe_n178` exit 1 and the committed test failing on the guarded call.
- If the `for`-body residual were unreachable code a reviewer would never write, calling it a residual would overstate it. Measured: the module parses, the suite passes and `probe_n178` prints `PASS N-178` with the call beneath `for _unreachable in ():`, so nothing in the gate distinguishes the two.
- If deleting a superseded row were still invisible, item 6 would be unclosed. Measured: certificate exit 1 at `930` vs `931`.
- If the derived fold disagreed with the committed 2022–2023 fold, item 2 would have changed a historical definition rather than generalised it. Measured: `4b44a1f2…` reproduced exactly.
- If the corpus's 44 missing bonuses were immaterial because those names produce no signals, the ruling on the table would still stand but its severity would not. Measured: all 44 are on panel ISINs at panel sessions, and 34 of them carry moves beyond ±25%.
- If the panel's largest returns were all fabricated, the reading of the tail would be simpler than it is. Measured: of the 11 beyond ±75%, 2 are applied rows, 2 are omitted attested actions, and 7 are explained by nothing the table carries (6 of them demergers or scheme-of-arrangement dates the archive does record), so the adjustment layer is wrong in both directions — it invents moves and it leaves real ones unexplained.
- If the survivor filter removed only untradeable microcaps, Ruling 1 would be a theoretical objection. Measured: 564 of 1,646 names trading on 2018-04-02 are removed from every date, and the panel is the identical list on all 1,425 dates.
- If the archive's INFY row were wrong and the table right, §95.5.4 would be a false accusation. Measured: the committed Bronze row reads `exDate 04-Sep-2018`, `Bonus 1:1`, and the raw price series halves on 2018-09-04, not 2018-09-12.
- If the corpus were already filed as gating input, the provenance label would be a lie rather than a scope question. Measured: the manifest row says `CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`, and no trial row names the artifact.
- If seq 10's block were the fold or the corpus, item 1–2 of §94.6 would be unfinished. Measured: both preconditions clear, and the refusal names the fee schedule.
- If the fee schedule's missing circular bytes did not matter because the rates are only used as a constant, the §7.2 finding would be cosmetic. Measured: the statutory component varies inside the window, the exchange component varies by circular, and the schedule can express neither without dates it does not have.

## §96 — Audit of `ac16232` (tag `feat-s96-12c6dae`): the statutory schedule prices every session and one of its eleven sources does not resolve to the bytes git stores, the point-in-time universe closes, and the builder's own fatal class is published instead of failing

**Date:** 19 November 2026
**Commit under review:** `12c6dae` (69 files, +37,453/−310: 11 captured statutory sources with manifests and `ingest_statutory_sources.py`, the interval-table rewrite of `StatutoryCostCriteria` and `costs.py`, six `effective_dated_exchange_fees` rows each carrying `circular_sha256`, the 407-line `attest_price_actions.py`, the rebuilt 75.4 MB corpus, 355 appended and 10 superseded corporate-action rows, `DEMERGER` as a type and as a forced-exit constraint, `scripts/probe_audit_findings.py` `N-181..N-185`, the seq-10 registry row and `reports/verdicts/trial_010/`, the `trial_annotations.jsonl` sidecar, the 119-line `test_phase3b2_audit_s96_items.py`, and criteria 1.1.15 → 1.1.16) and `ac16232` (the green-cache row, +19 lines). Neither touches a path under `reports/audit/`, `data/raw/2025` or `data/raw/2026`.
**Verdicts:** **§95.10 item 3 CLOSED** (N-181) · **item 6 CLOSED as ordered** (N-181…N-185 registered, flipping on the reverted fix 5 of 5) · **item 7 CLOSED as ordered** (sidecar re-measured, divergence identical) · **item 1 PARTIAL** — every levy is an attested interval, `2018-04-02` prices, and the 1,000× IPFT step is settled by the circular; one of the eleven sources resolves to nothing git stores (N-186) · **item 4 PARTIAL** — the archive and the table reconcile exactly in both directions, but the class the builder calls fatal is published not refused (N-187) and the missing-set direction has no build gate (N-188) · **item 5 PARTIAL** — the demerger is typed and attributable, and in the only run that exercised it the exit never filled and the refusal counter counts events (N-189) · **seq 10 CERTIFIED and NO-GO**, with a named residual that no ledger row checks its score · **the gate's verdict on this SHA is not reproducible**: two heavy runs fail and one passes on the same bytes (N-190).

### 96.1 Baseline re-measured at `ac16232`

The tree is unchanged from `12c6dae`; `ac16232` appends one cache row. Everything below was measured on that tree before any edit in this section.

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 1** — `OVERALL VERDICT: ONE OR MORE GATES FAILED`. The failing gate is W0.5-3: **1 failed, 560 passed in 76.52 s**, `test_n1_replay_guard_o1_lookup_and_bounded_memory` at **265.62 µs/fill** against its `250.0` ceiling. **No row was appended**; `git status` was clean apart from the auditor's own scratch file, which was moved out of the tree. Of three further `--force-full` runs on the same source, **two exit 0** (`561 passed in 62.48 s` and `561 passed in 72.71 s`) and one re-ran the suite command directly at 253.90 µs. Two of four heavy runs on one source tree fail; two pass |
| Gate W0.5-2 (verifiers) | **9/9 exit 0** — the gate discovers and runs every `verify_*.py` except itself, so the tree's **10** files are 9 executed + the gate. §95.1's "10/10" and §94.1's "9/9" are the gate's own count and the file count respectively; the gate prints `All 9 verification scripts passed exit 0` |
| Gate W0.5-4 / W0.5-5 | **108/108 commit-bearing tags verified**, `feat-s96-12c6dae` → `12c6dae` included; **1,009** current artifacts match byte count and sha256, **960** superseded rows skipped as history |
| Re-run of the gate's own suite command | `python -m pytest -n auto --dist loadfile -q` → **1 failed, 560 passed in 83.52 s**, the same test at **253.90 µs**; the same test serially **passes 3/3** (2.54 s, 2.55 s, 2.27 s). The committed green row for this tree records `561 passed, 69.19 s` |
| Green cache | a row for this source tree is recorded at `12c6dae` (suite 561, 69.19 s); the heavy run above did not reproduce it, so nothing was appended and nothing reused |
| Findings ledger at `ac16232` | **55** rows / **32** ids — latest-per-id **30 CLOSED**, **1 OPEN** (`N-150`), **1 ACCEPTED** (`N-152`); after this section **65** rows / **42** ids — **35 CLOSED**, **6 OPEN**, **1 ACCEPTED**; `verify_audit_findings.py` **exit 0**, **42/42 probes matched** |
| Criteria / pins | **1.1.16**; `CRIT-FPR-V1-9ee0a88c260d27fbe3ab13bb7c8c4c992e7d185986f28f5f803cf5db6db8634e`; `MAN-FPR-V1-f5b1f1f12e62564a…` recomputed over **1,875,421** bytes of `data/reference/manifest.jsonl` (matches, was 1,867,504 at 1.1.15); `min_binding_evaluation_start_date` **2018-04-01**; `expected_calendar_fingerprint` `CAL-FPR-V1-6acb5f45…` and `expected_sourced_window_calendar_fingerprint` `CAL-FPR-V1-2d5ac7ac…` unchanged |
| Leaf diff 1.1.15 → 1.1.16 | 97 → 169 leaves, **30 changed / 77 added / 5 removed**; **0 thresholds moved**. The only numeric movement is the new `2018-04-01..2020-12-31` fee row plus index shifts — re-keyed by `from_date`, all five pre-existing rows keep byte-identical `exchange_turnover_rate` and `ipft_rate` (`2024-10-01` changes only its `circular_ref`, `NSE/FA/64323` → `NSE/FA/64232`). The five STT/SEBI/stamp scalars are **gone from the schema**, not shadowed |
| Trials / fold / holdout | **10** rows, seq 1–10, **5** evaluation rows, pin `0246c276d52d3a9b…` recomputed over `data/trials/trial_registry.jsonl.manifest` (matches the criteria pin); seq 10 `IN_SAMPLE`, `FOLD-SPEC-V1-36a39987…`; validation **2024** frozen; holdout `2025-01-01..2026-11-11` sealed and refused by the engine |
| `probe_audit_findings.py` | **N-181, N-182, N-183, N-184, N-185 exit 0** (`PASS <id>`); `--list` ends at **N-190** |
| `probe_pre2022_bronze_coverage.py` | **exit 0** — `COVERED — 931/931`, `931 BINDING_EVALUATION, 0 WARMUP_NOT_GATABLE`, 931 superseded rows retain digest and provenance |
| `probe_pre2022_preconditions.py` | **exit 0, READY 9/9** — A1 246/245/252/248, A2 17,864/19,283, A4 **4,357** dividend ex-dates and now `enforced at 1 production call site(s); refusals=1`, A5 `0 of 7,753` before 2018-04-01 |
| `probe_seq10_candidate.py` | **exit 0 — `CERTIFIED`** |
| `probe_hold_bound_invariance.py` | **exit 1 — `NOT INVARIANT`**, run A 175 forced exits / 203 refusals, **5/5** committed metrics absent, run B 194 closed trades / `1,164,053.76` — reproducing the sidecar's recorded divergence exactly |
| `derive_2018_2023_corpus.py --check` | **exit 0 — `OVERALL: CURRENT`** (§96.4 reports the printed line) |
| Files the code commits touch | 69; **no** path under `reports/audit/`, `data/raw/2025`, `data/raw/2026`, `configs/partition_spec.yaml` |

The gate's verdict is the first thing a reader has to hold, because it decides what "green" means for every claim below. On one unchanged source tree it is **not a function of the tree**: four heavy runs give two exits 1 (265.62 µs and 253.90 µs against a 250.0 ceiling) and two exits 0 (561 passed in 62.48 s and 72.71 s), while the same test passes **3/3 serially** (2.54 s, 2.55 s, 2.27 s) in every one of those windows. The failure is **fail-closed** — a run is refused, nothing is certified that did not run — but it is **nondeterministic**: per-fill cost is ~47 µs serially, so the ceiling carries 5.3× headroom that the gate's own `-n auto` invocation can consume entirely when the host is busy, and the committed green row for this tree (561 passed, 69.19 s) is indistinguishable from the run that passed here and from the two that failed. Registered as **N-190**; no threshold was moved to clear it (§12.4).

### 96.2 §95.10 items 1–2 — PARTIAL: every levy is attested and priced per session, and one of the eleven sources is not the bytes git stores

Item 1 asked for the exchange-charge circular bytes, `circular_sha256` on every fee row, and a row covering `2018-04-02`; item 2 asked for the 1,000× IPFT step to be resolved and the statutory scalars to gain a date dimension. Both halves are present and measured.

| Claim | Measurement |
|---|---|
| 11 sources under `data/raw/circulars/<ref>/`, byte-exact, with manifests | **11/11 directories**, each a payload + `manifest.json` carrying `source_url`, `retrieved_at`, `http_status`, `byte_count`, `sha256`, `provenance_status: CONTENT_IDENTIFIED_ONLY / SOURCE_UNVERIFIED`. 7 `NSE/FA/*` PDFs (`45147`, `46225`, `46730`, `56129`, `61137`, `64232`, `73061`), `MAHARASHTRA_STAMP_DUTY_2019`, `SEBI_PAYMENT_OF_FEES_2020_011`, `SEBI_STAMP_DUTY_FAQ` (ten PDFs in all), plus the NSE STT/turnover HTML |
| `circular_sha256` on **all** fee rows, `NSE/FA/64232` included | **6/6 rows** carry a 64-hex digest; `criteria._digest_field` refuses anything else at load. `NSE/FA/64232` = `85b816208f33bdd1…`, equal to the committed `FA64232.pdf`. The row's `from_date 2024-10-01..2026-02-28`, rate `0.0000297` — the unverified `NSE/FA/64323` reference is gone |
| Half-open `[from, to)` intervals for STT / SEBI / stamp duty | Boundaries measured on `StatutoryCostCriteria.get_rate`: `SEBI_TURNOVER` **1e-6** on 2020-05-31, **5e-7** on 2020-06-01 and 2021-03-31, **1e-6** on 2021-04-01; `STAMP_DUTY_DELIVERY_BUY` **1e-4** on 2020-06-30 → **1.5e-4** on 2020-07-01; `STAMP_DUTY_INTRADAY_BUY` **2e-5** → **3e-5** on the same boundary; `STT_DELIVERY` 1e-3 and `STT_INTRADAY_SELL` 2.5e-4 identical at 2018-04-02 and 2023-12-29. The consumer is the engine, not a second table: `costs.py` calls `get_rate` at all five levy sites (STT delivery, STT intraday sell, SEBI turnover, stamp duty delivery buy, stamp duty intraday buy) and the scalars no longer exist on the dataclass |
| Pre-2023 IPFT confirmed | The pre-2021 and `2021-01-01..2023-03-31` rows both carry `ipft_rate 1e-9` (₹0.01/cr), the `2023-04-01..2024-03-31` row `1e-6` (₹10/cr) — the 1,000× step §95.8 could not settle is a real re-rating, stated in `configs/statutory_rate_decisions.yaml` with the circular quotation, and reversed from 2026-03-01 by `NSE/FA/73061` |
| `2018-04-02` priced | `statutory_cost_schedule_problem` returns **None** on the working copy; the first session resolves `NSE/FA/46730` `2018-04-01..2020-12-31`, ₹3.25/lakh slab 1, IPFT ₹0.01/cr, and every levy has a covering interval |
| Source substantiation is live, not declared | In a detached worktree: deleting `FA64232.pdf` → `exchange-fee row 'NSE/FA/64232' … cites NSE_FA_64232, but data/raw/circulars/NSE_FA_64232/ holds no committed payload`; deleting `NSE_STT_RATES/` → the same refusal naming that ref; zeroing a `source_sha256` → `…which is not the digest of any committed payload…` |

The one thing that is not true is the premise under all of it. **`NSE_STT_RATES` does not resolve to the bytes git stores**:

| | stated | worktree | `git cat-file blob HEAD:` |
|---|---|---|---|
| `NSE_SEBI_TURNOVER_FEES_STT_OTHER_LEVIES.html` | 330,003 B, `5df41b04…` | 330,001 B, `91e8ace7…` (fresh checkout) | 330,001 B, `91e8ace7…` |

`.gitattributes` opens with `* text=auto eol=lf`, so the captured `.html` is normalised on checkout and its CRLF bytes are rewritten; `git status` cannot see the difference because the same attribute makes the comparison normalising. In the main working copy the file is still the 330,003-byte download, so `statutory_source_problem` returns `None` there and the committed test passes. In a fresh checkout of the same commit it returns `SEBI_TURNOVER interval from 2018-04-01 cites NSE_STT_RATES with sha256 5df41b049103c757…, which is not the digest of any committed payload under data/raw/circulars/NSE_STT_RATES/ ([91e8ace7fde9ca8b…])`, `statutory_cost_schedule_problem` is non-`None`, seq 10 is **NOT REGISTERED**, and `tests/unit/test_phase3b2_audit_s96_items.py::test_pre_2021_session_is_priced_from_committed_bytes` **fails (1 failed, 3 passed)**. The attestation is a working-copy digest — the precise defect §79.7 recorded for the frozen-volume pin and §86.3 (N-170) for 1,221 archives, recurring on a new file type; N-170's repair marked archives `-text` and did not reach `data/raw/circulars/`. Ten payloads resolve to both worktree and blob; the 23 corporate-action `.json` payloads resolve to both. Registered as **N-186**.

So item 1's substance is right and item 1's *evidence chain* fails on every clone. **PARTIAL.**

### 96.3 §95.10 item 3 — CLOSED: the universe is the ISINs that traded, and a name that dies stays on the dates it lived

| Measurement | `77fb043` (§95.5.5) | `ac16232` |
|---|---|---|
| header rule | `"1082 of 2735 observed ISINs: every session from … 1463 ISIN(s) … are excluded"` | `POINT_IN_TIME_TRADED: universe_by_date[D] is exactly the set of ISINs with a valid exchange observation on D, with no full-span, survival or look-ahead condition` |
| members on the first session | 1,082 (the whole panel) | **1,646** |
| members on the last session | 1,082 | **2,118** |
| membership identical on every date | yes, all 1,425 | **no** — min 1,619, max 2,139, mean 1,809.2 |
| distinct members over the window | 1,082 | **2,735** |
| instruments stopping before the last session | excluded from all dates | **617**, each present on its own last bar and absent the next |
| the witness | — | `IN9623B01058` last trades 2023-12-26: a member that day, absent 2023-12-27 |

`instrument_count` 2,735 and `total_instrument_records` 2,578,060 match the header and the commit claim exactly. The 564 day-one names §95.5.5 measured as retroactively deleted are back on the dates they traded. `universe_selection` states the rule rather than the outcome, which is what item 3 asked for, and the two `1,061` prose counts are gone (§95.5.7). **CLOSED**, registered as **N-181**.

The residual that survives is structural and was not created here: a bar carries no series, so the artifact cannot label a `BE`/`BZ` observation. §13.1 entry eligibility is enforced at the call site (`explicit_series=ExchangeSeries.EQ`), so this is not an entry hole — but it is not provable from the artifact either.

### 96.4 §95.10 item 4 — PARTIAL: the table is the archive in both directions, and the class the builder calls fatal is published instead of failing

The reconciliation is now an equality, not a count of examples. Measured independently over the committed archive and table:

| Measurement | Result |
|---|---|
| archive-attested price-side events | **430** over **23** payloads |
| attested but absent from the table | **0** (was 95) |
| live price-side rows with no attestation | **0** (was 14) |
| live rows that are attested | **430** — exact both ways |
| applied factors | **301** ISINs, **0** refusals |
| rows with `source_digest` | **430** of 5,371; every one resolves to a committed payload on both the worktree and the blob |
| table census | `DIVIDEND` 4,495, `ISIN_TRANSITION` 426, `BONUS` 194, `SPLIT` 175, **`DEMERGER` 68**, `RIGHTS` 4, `CONSOLIDATION` 3, `MERGER` 3, `DELISTING` 3 — 5,371 rows, sha256 `d7b425e5f444c8c0…` equal to the corpus header's `corporate_actions_fingerprint` |

**INFY (N-183).** `ATTESTED_NSE_CA_S96_INFY_20180904` (BONUS 2:1, digest-resolved) is the live row; the `2018-09-12` row is superseded by `RESTATED_S96_INE009A01021_2018-09-12`. On the corpus INFY returns **+0.0279 on 2018-09-04** and **+0.0117 on 2018-09-12**, where §95.5.4 measured −0.4860 and +1.0234.

**IDEA (N-184).** The `2023-09-15` CONSOLIDATION is superseded by `RESTATED_S96_INE669E01016_2023-09-15` with no replacement — the ordered outcome was "resolve or delete" and there is no archive record to re-date it to. IDEA returns **+0.0734** on 2023-09-15, where §95.5.4 measured −0.8927.

**What is not true.** `classify_extreme_moves` says of its `EX_DATE_MISMATCH` class, in the committed docstring: *"**This is the class that fails the build.**"* It does not. `build` binds `failures` at `derive_2018_2023_corpus.py:296` and never reads it; an AST census finds the name loaded only at `:453`, `:466`, `:468`, all inside the function's own local. Re-running the classifier over the committed corpus reproduces the header exactly — 1 applied, 24 archive, 71 not ratio-shaped, 730 ratio-shaped unattested, **6 ex-date mismatch** — and names the six:

| ISIN | session | one-session return | the archive attests an action on |
|---|---|---|---|
| `INE292A01023` | 2018-07-06 | **−0.5000** | 2018-07-11 |
| `INE292A01023` | 2019-12-09 | **−0.5000** | 2019-12-19 |
| `INE292A01023` | 2019-12-20 | **−0.5000** | 2019-12-19 |
| `INE803A01027` | 2019-09-18 | **−0.5000** | 2019-09-16 |
| `INE251H01024` | 2022-08-12 | **+1.2800** | 2022-08-18 |
| `INE784B01035` | 2023-09-26 | **+56.0000** | 2023-09-22 |

Four of the four ISINs carry **no price-side row anywhere in the table**, so each of these six returns is a real discontinuity charged as a return, on a name the archive does say something about within seven sessions. That is the INFY failure mode at six more observations, in the class the builder's own sentence calls fatal. Item 4's probe required "any that is not fails the build with the ISIN and date printed"; the ISIN and date are printed during a build and the build exits 0. Registered as **N-187**.

The ±35% detector's *other* four classes being publish-only is the scoped deviation the work order authorised and it is defensible: 730 ratio-shaped unattested moves are rights-entitlement expiries, ETF unit re-denominations and the March-2020 collapse, and §95.7 states this repository cannot tell those from an uncaptured action. The `EX_DATE_MISMATCH` class is not in that deviation. One prose consequence of the same sentence: `CURRENT_STAGE_OF_WORK.md` §96 says "classifies **826** one-session moves beyond ±0.35" and then lists five buckets — 1 + 24 + 71 + 6 + 730 = **832**. 826 is the four-bucket total the builder prints; the sentence's total excludes the six it names in the same line.

**The second half of the item has no consumer.** `applied_actions` refuses an inadmissible row and `build` raises on a non-empty refusal list, so the direction "a row in the table that the archive contradicts" is live. The direction "an attested action the table does not carry" is not: withdrawing the single attested row `SRF 2021-10-13` — which the archive still attests, `(INE647A01010, 2021-10-13)` is a key in `bronze_attestations()` — leaves **0 refusals** and 300 instead of 301 applied ISINs. The only completeness check in the repository is `attest_price_actions.reconcile()` / `report()`, which exits 1 and names the gap; **no build path calls it and no `verify_*.py` mentions the module**, so the gate never runs it. That is the §14.4 shape exactly — the check exists beside the build, not in it. Registered as **N-188**. Item 4 is **PARTIAL**: reconciled today by measurement, not by a gate that would notice tomorrow.

### 96.5 §95.10 item 5 — PARTIAL: the demerger is typed, attributable, and never exited

| Claim | Measurement |
|---|---|
| `DEMERGER` exists as a type | `CorporateActionType.DEMERGER` present; the ledger books it as a named no-op that "invents no ratio and settles at book value" (`portfolio.py`, `position.py`) |
| every attested demerger is a typed row with a digest | **68** rows, **68** with `source_digest`, **0** superseded |
| the exit constraint runs off the archive, not the book | the loop builds `demerger_exits` from `sec_master.corporate_actions()` filtered on `not ca.superseded` for `sessions_to_run[i+2]`, seeds `forced_reasons.setdefault(isin, "DEMERGER_FORCED_EXIT")`, passes `forced_exit_reasons=forced_reasons`, and the harness stamps `intent_id = SWING_{reason}_{isin}_{date}` |
| the reason reaches the order | measured by reversion: replacing `DEMERGER_FORCED_EXIT` in the loop makes probe N-185 exit 1; restoring returns PASS |
| the two counters are attributed apart | `hold_bound_exits` is filtered on the reason, so the **7,309** hold-bound refusals no longer absorb demerger reasons; the bound-disabled counterfactual reads **0 / 0** on both counters, and the fraction the comparison records (`413` trades, `1,501,180.25`, PF `1.1140…`) is the consumer's own effect |
| **did it exit anything?** | **No.** `demerger_forced_exits` **0**, `demerger_forced_refusals` **66**, and `closed_trade_exit_reasons` = `{SIGNAL_EXIT 55, STOP_LOSS 304, MAX_HOLD_BOUND_EXIT 422}` summing to the 781 closed trades — not one `DEMERGER_FORCED_EXIT` among them |

The reason the 66 cannot be read as "66 refused exits" is structural: `demerger_exits` is every non-superseded demerger on the session after `next_session`, **archive-derived**, with no held-position filter, while `execute_swing_strategy_session` skips `held is None or held.is_closed or held.quantity <= 0`. A demerger on a name the book never owned is therefore counted as a refused exit, and the artifact cannot distinguish "66 positions could not exit" from "66 events, none of them held". Over 1,425 sessions and 781 closed trades, `0` fills also means no held position is *known* to have crossed a demerger date — so whether the constraint ever bound a real position is unmeasured. Registered as **N-189**. Item 5 is **PARTIAL**: the mechanism and the attribution are real and the reversion attack fails closed; the operation and the counter are not.

### 96.6 §95.10 item 6 — CLOSED as ordered: the five probes exist, pass, and fail on the reverted fix

Item 6 ordered the probes *before* the rows, and §95.10 was explicit that a row without an executable probe is either a gate failure or a row that cannot fail. All five exist in `scripts/probe_audit_findings.py` and all five **PASS** on the committed tree (`--list` now ends at `N-190`). Each was then made to face the fix it was written for, in a detached worktree at `ac16232`:

| Reverted fix | probe | `PASS` when committed |
|---|---|---|
| A. header rule restored to the full-span text and `universe_by_date` collapsed to the last session's list | N-181 | **exit 1** — `the corpus does not state a point-in-time rule …` |
| B. one attested bonus row marked superseded (`SRF 2021-10-13`) | N-182 | **exit 1** — `… is still not applied with an archive digest: ['SRF 2021-10-13']` |
| C. the `2018-09-12` INFY bonus un-superseded | N-183 | **exit 1** — `the 2018-09-12 INFY bonus row is still live` |
| D. the IDEA consolidation un-superseded | N-184 | **exit 1** — `the unattested IDEA 2023-09-15 consolidation is still live` |
| E. `DEMERGER_FORCED_EXIT` removed from the session loop | N-185 | **exit 1** — `the session loop does not force a position out of a demerger ex-date` |
| control, all restored | all five | **exit 0** — `PASS <id>` |

The five `CLOSED` rows are registered with those commands. Two residuals are named rather than smoothed. First, `probe_n182` asserts **fourteen named examples**, not the general set; the equality that actually holds is `attest_price_actions.reconcile()`'s 430 = 430, measured here and gated nowhere (N-188). Second, `probe_n185` asserts the exit reason is *reached*, not that it ever *fires* — which is N-189.

### 96.7 §95.10 item 7 — CLOSED as ordered: the sidecar is real, and its divergence re-measures identically

`data/trials/trial_annotations.jsonl` carries one row keyed on the committed seq-9 `record_hash 50de55e960ad5937…` (the registry row's own hash, unchanged): `annotation NON_REPRODUCIBLE_AT`, `annotated_at_sha 77fb043`, and a `divergence` block. Re-measured at `ac16232` by running `probe_hold_bound_invariance.py` rather than reading its output:

| Sidecar claim | Re-measured |
|---|---|
| hold-bound forced exits 175 / refusals 203 | **175 / 203** |
| committed metrics reproduced 0 of 5 | **0 of 5** — `closed_trades` 382 vs 193, `end_equity` 1,086,020.54 vs 1,283,327.73, PF 1.1070 vs 0.9920, win rate 0.4084 vs 0.2539, MaxDD 0.3264 vs 0.2073 |
| run B (bound disabled) 194 trades / `1,164,053.76` | **194 / 1,164,053.76** — identical, so the annotation's "the drift is not the bound's alone" is confirmed and not merely asserted |

No historical metric was edited, the hash chain is untouched, and the row stays at criteria 1.1.5 as history. **CLOSED as ordered.** The residual: nothing consumes the annotation. `probe_seq10_candidate.py` does not read the file, `verify_*.py` does not, and `probe_hold_bound_invariance.py` is a `probe_*.py` the gate does not execute — so the sidecar is read by one committed unit test and by whoever opens the directory. The written contract ("refused by the certificate, **or** carries the annotation and the divergence") is met; a *computed* consequence is not.

### 96.8 Candidate seq 10 — CERTIFIED, NO-GO, and the exemption is wider than it looks

`python scripts/probe_seq10_candidate.py` exits **0 — CERTIFIED**, printing `N = 10 (expected 10), N_eval = 5, seq 10 rows = 1`, the registry-manifest and criteria pins agreeing at `0246c276…`, the row's criteria `1.1.16` and partition `IN_SAMPLE`, `FOLD-SPEC-V1-36a39987dca…` reproduced from `2018-04-01..2023-12-31` by the same function the engine runs, the artifact at `2018-04-02..2023-12-29` with `hold_bound_forced_exits 422` / `hold_bound_refusals 7309`, a baseline that is a current-tree run (`reports/analysis/s94/seq10_baseline_2018_2023_verdict.json`, `f5fe3af5a1e2de83…`, criteria 1.1.16) whose digest re-computes, and a sealed-era window refused by the engine with `HoldoutSealedError`.

| Claim | Measurement |
|---|---|
| `N = 10, N_eval = 5` | 10 registry rows, 5 evaluation rows; seq 10 carries `returns_digest: null` and every metric `null` — a registration, not an evaluation, so the count correctly did not move |
| criteria 1.1.16 | row, artifact, comparison and the live criteria all read `1.1.16`; the RATIONALE's stale `1.1.13` that §94.4 measured is gone |
| 2024 fold frozen / holdout sealed | partition `IN_SAMPLE`, fold test ends 2023-12-31; no registry row's provenance contains `2025-01-01`, `data/raw/2025` or `data/raw/2026`; a 2025 window raises `HoldoutSealedError` before a bar is read |
| `781` trades, `1,072,507.24`, PF `1.0583`, `72.65%` MaxDD | artifact `closed_trades` 781, `end_equity` 1,072,507.24, `closed_only_profit_factor` 1.058319814…, `max_drawdown` 0.7264709014…; `5/5` `metric_agreement` true between the candidate artifact and a baseline run of the same configuration recorded under a different digest (`f5fe3af5a1e2de83…`) with identical figures. What was measured here is the agreement of the two committed artifacts and the digest of each, **not** a third execution of the run |
| `422` forced exits / `7,309` refusals | artifact counters, and the bound-disabled counterfactual reads `0 / 0` with 413 trades — the consumer's own cost, isolated |
| verdict | `overall_verdict: NO-GO`. PF 1.0583 < `min_profit_factor 1.50`, MaxDD 72.65% ≫ `max_portfolio_drawdown 0.25`, `positive_is_fold_ratio` 0, annualized Sharpe 0.1843, `2,735`/`2,578,060` rows resolved 100%. Under §95.6 Ruling 1 this is a non-gating pipeline measurement and it does not need to pass; it would fail every profitability gate if it were offered as one |

**The `G2A-6.7` re-render exemption** (`trials.py`, N-178's neighbour) is the item's weakest seam and it behaves as designed and wider than it reads. It exempts an artifact from the artifact→ledger direction when the trial's row is `IN_SAMPLE` and the artifact declares the registry's own evaluated count. Attacked against a copy of the real `reports/verdicts/` tree:

| Artifact | Result |
|---|---|
| the committed seq-10 artifact | **accepted** (`checked=5`) |
| **seq 10 with `annualized_sharpe: "99.9"` and `evaluated_trial_count: 5`** | **accepted** — the score is exempt from the ledger check, by construction |
| seq 9 doctored to `42.0` (has an evaluation row) | refused — `does not equal the ledger's 0.8730934047…` |
| seq 5 doctored to `42.0` (has an evaluation row) | refused — `does not equal the ledger's −0.6995862169…` |
| seq 10 doctored, **no** declared count / wrong count `4` | refused — the exemption does not open without the count |
| an unregistered trial id | refused — `is not in the registry; a scored figure must be registered` |
| seq 1–4 (pre-sidecar carve-out) | accepted, as `_PRE_SIDECAR_TRIAL_SEQ_MAX` documents |

So the exemption's two clauses both fail closed, and within them **nothing checks the score**. That is the correct reading of §93.5 Ruling 3 — a candidate run as a re-render of its own row has no evaluation to compare against — and it means seq 10's 0.1843 Sharpe and 781 trades rest on the certificate plus the artifact digest, not on a ledger row. It is named here as a residual, not a defect: the `99.9` attack succeeding is the *definition* of the exemption, and its containment is that `evaluation_count` cannot move and the artifact must declare it.

### 96.9 Phase verdicts

| Phase | Verdict at `ac16232` | Named residuals |
|---|---|---|
| `§7.2` / `§10.5` / `§10.7` §95.10 items 1–2 — statutory sources and interval tables | **PARTIAL** — 11 sources captured, 6/6 fee rows digest-attested, all five levies resolve per session, both 2020 boundaries exact, `2018-04-02` priced, three refusal paths measured live | **N-186**: `NSE_STT_RATES` is a working-copy digest (330,003/`5df41b04…` stated vs 330,001/`91e8ace7…` stored), so a fresh checkout refuses the schedule and the committed S96 test fails. GST on SEBI turnover before 2022-07-18 and the 2020 turnover concession remain declared-not-modelled |
| `§6.1` §95.10 item 3 — point-in-time universe | **CLOSED** — 1,646 / 2,118 / 2,735, membership varies, 617 names stop and stay on their dates | artifact cannot label a bar's series |
| `§5.4` / `§6.5` §95.10 item 4 — attested adjustments | **PARTIAL** — 430 = 430 in both directions, 301 applied / 0 refused, INFY and IDEA corrected by restatement | **N-187**: the `EX_DATE_MISMATCH` class is documented as fatal, counted at 6, and `failures` is never read; 4 ISINs carry no row at all. **N-188**: withdrawing an attested row leaves 0 refusals; `reconcile()` has no gate consumer. Prose: `826` vs its own five buckets `832` |
| `§13.2` §95.10 item 5 — demerger | **PARTIAL** — type, attested rows, forced exit and attributable reason all present and reversion-tested | **N-189**: 0 fills / 66 refusals, and the refusal counter counts events, not refused exits, because the set is archive-derived and unheld ISINs are skipped silently |
| `§9.1` §95.10 item 6 — probes | **CLOSED as ordered** — five probes exist, pass, and exit 1 on each reverted fix | `probe_n182` asserts 14 examples not the general equality; `probe_n185` asserts reach, not effect |
| `§8.2` / `§10.1` §95.10 item 7 — non-reproducible row | **CLOSED as ordered** — sidecar keyed on the unchanged hash, divergence re-measured identical | nothing computes a consequence of the annotation |
| `§13.2` / Phase 3B-2 item 3 — seq 10 | **CERTIFIED, NO-GO** — N 10 / N_eval 5, fold `36a39987…`, holdout sealed, 5/5 metrics reproduce a current-tree baseline | the score is ledger-unattested by the Ruling's own design; the run is diagnostic until the corpus is gating input |
| Gate / cache | **NOT REPRODUCIBLE** — of four heavy runs on one source tree, two exit 1 at W0.5-3 (265.62 and 253.90 µs) and two exit 0 (561 passed in 62.48 s and 72.71 s); 9/9 verifiers and 108/108 tags pass in every one | **N-190**: a 250 µs CPU budget decided by the gate's own `-n auto`; the recorded row for this tree reads 561 passed, which is what half the runs measured |

### 96.10 Work order for feat-s97

Ordered by what it unblocks. Item 1 is a gate defect, so it is first: nothing else can be certified while the gate's green is a function of host load. Items 2–3 restore the two attestation chains; items 4–6 close what §96 named; item 7 is carried.

1. **Make the gate's verdict independent of host load** (serves `§12.3`, `§12.4`; N-190). Pin the worker count the gate passes to pytest, or replace the replay guard's CPU-per-fill ceilings with the structural count N-174 already names, and record which was done. **Probe:** `python scripts/verify_audit_append_only.py --force-full` exits 0 on a tree whose serial suite is green **and** exits 0 on the same tree when the host is loaded to saturation; three consecutive heavy runs of one tree must return one verdict. Do not raise `250.0` — that is a threshold move under §12.4.
2. **Re-state the `NSE_STT_RATES` payload so its manifest describes the bytes git stores** (serves `§10.7`, `§6.5`; N-186). Either capture the payload again with `data/raw/circulars/** -text` in `.gitattributes` and re-digest 330,001/`91e8ace7…` from the stored bytes, or correct the manifest and the four criteria rows to the blob it already has. State which, because the two answers mean different things about what was retrieved. **Probe:** a fresh `git clone --no-local` runs `test_pre_2021_session_is_priced_from_committed_bytes` green and `statutory_source_problem` returns `None` with **no** working-copy bytes in the path; every manifest's `sha256` equals `git cat-file blob HEAD:` of its payload. `probe_n186` must then exit 1.
3. **Make the builder fail on the class it calls fatal, and gate the missing direction** (serves `§9.1`, `§95.7` Ruling 2; N-187, N-188). Consume `failures`: a non-empty `EX_DATE_MISMATCH` list must raise, naming ISIN and date, so the six measured here are either re-dated to the archive or the archive record is corrected — not published. Then call `attest_price_actions.reconcile()` from `build` and raise on `missing`, or run it from a `verify_*.py`. **Probe:** deleting one attested row makes the build exit non-zero naming the ISIN, action and ex-date; an `EX_DATE_MISMATCH` of one makes the build exit non-zero; `probe_n187` and `probe_n188` both exit 1 afterwards.
4. **Make the demerger counter count refused exits of held positions** (serves `§13.2`; N-189). Intersect `demerger_exits` with the book before counting, and record whether any position was ever held across one; if none was, say so and measure the constraint on a synthetic hold instead of reading a zero as an effect. **Probe:** a demerger event on an ISIN the book does not hold increments no refusal counter; an event on a held ISIN increments `demerger_forced_exits` when it fills and `demerger_forced_refusals` only when it does not. `probe_n189` must then exit 1.
5. **Filter superseded rows where the action feed is read** (serves `§10.1`, `§13.2`; N-183's residual). The corpus builder and the demerger set filter `superseded`; `SecurityMaster.get_corporate_actions()` does not, so the superseded INFY 2018-09-12 and IDEA 2023-09-15 rows still reach `walkforward.py:650`'s ex-date adjustment. **Probe:** a superseded row is absent from `get_corporate_actions(isin)` output, and a session whose only action is superseded books no adjustment.
6. **Let the certificate see the annotation** (serves `§9.1`, `§8.2`; item 7's residual). A row carrying `NON_REPRODUCIBLE_AT` should either be refused when offered as a comparator or printed by the certificate as the reason it is not one. **Probe:** `probe_seq10_candidate.py` prints the annotation for seq 9 and fails if a row annotated `NON_REPRODUCIBLE_AT` is used as a baseline.
7. **Carried, unchanged:** N-150 (`CRIT-OVERFIT-06` needs a second fold or a recorded admission); the replay counter's `get`/`popitem` (§92.10 item 6); the Phase 2D artifact's `timestamp_utc` still `2026-11-16T10:00:00+00:00` (LOW); N-178's `for`-body ancestor gap.

### 96.11 What would falsify this verdict

- If the gate were deterministically green at this SHA, N-190 would be a measurement artefact of the auditor's host. Measured: of four heavy runs on one source tree, two exit 1 (265.62 and 253.90 µs) and two exit 0 (561 passed in 62.48 s and 72.71 s), while the single test passes 3/3 serially inside every one of those windows — so the verdict is not a function of the bytes committed. If a fifth run fails to reproduce *either* outcome the pass/fail split is the finding; if four runs all agreed, there would be none.
- If `NSE_STT_RATES` resolved to the stored blob, N-186 would be a checkout artefact rather than a committed digest. Measured: `git cat-file blob HEAD:` yields 330,001 bytes / `91e8ace7…`, the manifest and four criteria rows state 330,003 / `5df41b04…`, and a fresh worktree at `ac16232` refuses the schedule and fails the committed test.
- If the six `EX_DATE_MISMATCH` returns were a classification artefact, N-187 would overstate. Measured: they are 4 ISINs / 6 one-session returns of −0.5000 or larger, re-derived from the committed corpus with the builder's own function, four of the ISINs having no price-side row anywhere.
- If `failures` were consumed anywhere, the builder's sentence would be true. Measured: an AST census shows the module-level binding read nowhere.
- If withdrawing an attested row refused, N-188 would be closed. Measured: 0 refusals, 300 vs 301 applied ISINs, and the archive still attests the event.
- If a demerger exit had ever fired, N-189's "inert" reading would be wrong. Measured: `demerger_forced_exits 0` and no `DEMERGER_FORCED_EXIT` among 781 closed-trade reasons.
- If the point-in-time universe still removed names retroactively, item 3 would not close. Measured: 1,646 first / 2,118 last / 2,735 distinct, with a named name absent the session after its last bar.
- If INFY or IDEA still carried their wrong rows, items 4's closures would be prose. Measured: both superseded by restatement, corpus returns +0.0279 / +0.0117 / +0.0734 where §95.5.4 measured −0.4860 / +1.0234 / −0.8927, and the probes flip on the revert.
- If the seq-10 exemption refused a doctored score, the residual would be overstated. Measured: `99.9` is accepted for an `IN_SAMPLE` row with no evaluation row and the declared count, and refused without it.
- If seq 10's metrics did not reproduce, `CERTIFIED` would be wrong. Measured: 5/5 agreement between the candidate artifact and the baseline artifact, with both digests re-computed. A third execution was not performed, so what is established is agreement between two recorded runs, not that either re-executes today.
- If the 7,309 hold-bound refusals still absorbed demerger reasons, the attribution fix would be prose. Measured: `hold_bound_exits` is filtered on `MAX_HOLD_BOUND_EXIT`, the two counter pairs sum independently, and the bound-disabled run reads `0 / 0`.
## §97 — Audit of `612e82a` (tag `feat-s97-612e82a`): the captured statutory payload survives a clone, the builder refuses the class it documents as fatal, a demerger refusal counts a held exit, and the gate is green three times running

**Date:** 19 November 2026
**Commit under review:** `612e82a` (13 files, +648/−122: `.gitattributes`, `configs/go_no_go_criteria.yaml`, the re-staged 330,003-byte `NSE_STT_RATES` payload, the rebuilt 75,390,038-byte corpus with the manifest row that supersedes its predecessor, the regenerated Phase 2D verdict pair, `scripts/derive_2018_2023_corpus.py`, `scripts/run_phase3b2_walkforward.py`, `scripts/verify_audit_append_only.py`, `scripts/probe_audit_findings.py`, `tests/unit/test_phase3b2_audit_s97_items.py` and `CURRENT_STAGE_OF_WORK.md`) and `437e0c4` (the green-cache row, +19 lines). Neither commit touches a path under `reports/audit/`, `data/raw/2025` or `data/raw/2026`.
**Verdicts:** **§96.10 item 1 CLOSED** (N-186) · **item 2 CLOSED** (N-187) — the gate fires, and the six pairs it used to name leave the fatal class for the reason §96.4 gave; two new findings fall out of the same function (N-191, N-192) · **item 3 CLOSED** (N-188) · **item 4 CLOSED** (N-189) — the counter is right and its artifact still publishes the old number (N-194) · **item 5 CLOSED** (N-190) — three consecutive heavy runs, 3/3, both ceilings byte-identical · **Ruling: `criteria_version` stays at `1.1.16`** (accepted on measurement, conditional on N-193).

### 97.1 Baseline re-measured at `437e0c4`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` ×3 | **exit 0, 0, 0** in **341 s / 364 s / 350 s**. Each run: **564 passed** in the parallel invocation (63.50 s / 82.91 s / 65.75 s) + **1 passed** in the isolated invocation (2.41 s / 2.55 s / 2.50 s), reconciled as `564 + 1 = 565 of 565 collected` (68.93 s / 88.31 s / 70.54 s). `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` three times on one unchanged tree |
| Gate W0.5-1 / -1b / -1c | Audit report append-only verified; **2** audit volumes; the index reproduces |
| Gate W0.5-2 (verifiers) | **9/9 exit 0** in every run (`verify_audit_findings.py` 188.02 s, `verify_cash_universe_coverage.py` 46.32 s, `verify_historical_snapshot.py` 6.96 s, `verify_phase2a_containment_and_trials.py` 1.74 s, `verify_phase2b5_storage.py` 3.43 s, `verify_phase2b_significance.py` 1.04 s, `verify_phase2c_walkforward.py` 3.51 s, `verify_phase2d_verdicts.py` 5.02 s, `verify_wave1_thin_slice.py` 5.44 s) |
| Gate W0.5-4 / W0.5-5 | All commit-bearing tags verified, `feat-s97-612e82a` among them (**110** tags in the repository, was 108 at §96); **1,009** current artifacts match byte count and sha256, **961** superseded rows skipped as history (was 960) |
| `pytest --collect-only` | **565 tests collected in 0.91 s** — the `564 + 1` split is the collected suite, not a literal |
| Criteria / pins | **1.1.16**; `CRIT-FPR-V1-b2876d9850088fb01b90374bfc648fd2505a09bd766c839319aeacdf7b3917cd`; `MAN-FPR-V1-e79d791518a4337adaa871fed32257f12e09359ddcdbaf2c3f8e4094feb411ee` **recomputed** over **1,876,489** bytes / **1,970** rows of `data/reference/manifest.jsonl` (**1,009** current + **961** superseded) — equals the pin (was `f5b1f1f1…` / 1,875,421 bytes at §96) |
| Ledger at `437e0c4` | **65** rows / **42** ids — latest-per-id **35 CLOSED**, **6 OPEN** (`N-150`, `N-186`…`N-190`), **1 ACCEPTED** (`N-152`); `verify_audit_findings.py` **exit 0** in all three heavy runs |
| Fresh detached worktree at `437e0c4` | `tests/unit/test_phase3b2_audit_s96_items.py` + `tests/unit/test_phase3b2_audit_s97_items.py` → **8 passed in 1.16 s**; `probe_audit_findings.py N-186` **exit 0**; `statutory_source_problem(criteria)` **None**; `statutory_cost_schedule_problem(criteria)` **None**; `git status --porcelain` empty |
| Corpus | `derive_2018_2023_corpus.py --check` **exit 0 — `OVERALL: CURRENT`** over 1,425 archives. Header: **1,425** sessions (2018-04-02..2023-12-29), **2,735** instruments, **2,578,060** bars, reconciliation **1** applied / **24** archive / **72** no-ratio / **735** ratio-shaped / **0** ex-date mismatch; **832** moves beyond ±35% |
| Probes | **N-186…N-190 exit 0** (`PASS <id>`); `--list` now ends at **N-194** (four probes added by this section, §97.8) |
| Trials / fold / holdout | **10** registry rows, seq 1–10; seq 10 `TRIAL-PHASE3B2-EXPANDED-010`, `IN_SAMPLE`, `criteria_version 1.1.16`, `FOLD-SPEC-V1-36a39987dca…`; `probe_seq10_candidate.py` **exit 0 — `CERTIFIED`**, `N = 10` (expected 10), `N_eval = 5`, one seq-10 row, pin `0246c276d52d3a9b…` on both sides, baseline `f5fe3af5a1e2de83…`, 422 forced exits / 7,309 refusals, and the sealed-era fold `2025-01-02..2025-03-31` **refused**; `configs/partition_spec.yaml` validation **2024-01-01..2024-12-31**, holdout **2025-01-01..2026-11-11**, unlock token hash 64 zeros (no token minted) |
| `probe_pre2022_bronze_coverage.py`, `probe_pre2022_preconditions.py`, `probe_hold_bound_invariance.py` | **NOT RUN** this round (no path they read is touched by either commit; §96.1's values stand: 931/931 covered, READY 9/9, `NOT INVARIANT` 175/203 vs 194) |
| Files the two commits touch | 13 + 1; **no** path under `reports/`, `data/raw/2025`, `data/raw/2026`, `configs/partition_spec.yaml`, `reports/audit/` |

The gate's verdict is a **function of the tree** on this commit in a way §96.1 could not state: three consecutive `--force-full` runs, three exits 0, the same `564 + 1` split each time, with the benchmark that decided §96 measuring beside no worker (2.41–2.50 s) instead of beside fifteen (253.90–265.62 µs/fill). No threshold moved to get there (§12.4): the two ceilings are byte-identical and `probe_n190` asserts it.

One measurement in this section was the auditor's own error and is recorded so the next round does not repeat it. The first `verify_audit_findings.py` run of this round exited **1** with three failures — `N-160` (`a directory is in the dirty set: ['_audit_wt_s97/']`), `N-163`, and one more — because the auditor's detached worktree was sitting inside the repository while the verifier ran. Removing the worktree (`git worktree remove --force`, then `prune`) made the gate green and the same three probes pass. The dirty-set probes are doing their job; **an auditor's scratch tree is dirty state too**.
### 97.2 §96.10 item 1 — CLOSED (N-186): the statutory payload is the blob git stores, and a clone proves it

| | stated by `manifest.json` | worktree | `git cat-file blob HEAD:` | fresh detached checkout of `437e0c4` |
|---|---|---|---|---|
| `NSE_STT_RATES/NSE_SEBI_TURNOVER_FEES_STT_OTHER_LEVIES.html` | 330,003 B / `5df41b049103c75784324c846f62cf55cd1157c0dcbc2e7748220e6564f2e277` | **330,003 B / `5df41b04…`** | **330,003 B / `5df41b04…`** | **330,003 B / `5df41b04…`**, `git status` clean |
| attribute | — | `data/raw/circulars/*/**` → `text: unset` (`git check-attr`) | — | same |
| witness test | — | — | — | `tests/unit/test_phase3b2_audit_s96_items.py` **4 passed**, `probe N-186` **PASS**, both statutory problem functions **None** |

§96.2's defect is gone: the three columns that disagreed (worktree 330,001 / blob 330,001 / manifest 330,003) now agree with the manifest, and the checkout is byte-faithful rather than "faithful in the main working copy only". The four `NSE_STT_RATES` criteria interval rows still carry `5df41b04…`; the manifest, `data/reference/manifest.jsonl` and every threshold were **not** edited for this item, so the pin move measured in §97.1 belongs to item 2.

The reversion is clean. Deleting the `.gitattributes` line and re-running the probe:

```
FAIL N-186: no attribute pins the captured statutory payloads to their own bytes, so a checkout can rewrite them again (§96.2)
```

One observation, measured and **not** a finding. A byte comparison of all **2,191** tracked paths under `data/raw` against their index blobs (`git ls-files -s` versus a locally recomputed Git blob hash) finds **11** whose working-copy bytes differ: every `data/raw/circulars/*/manifest.json`, e.g. `NSE_FA_45147/manifest.json` is 626 B with 13 CRLF in the worktree and 613 B / 0 CRLF in the blob. No digest in the repository covers a `manifest.json`'s own bytes, and JSON parsing is indifferent to the line endings, so nothing downstream can observe it; a clone writes the 613-byte blob. It is working-copy staleness, not repository state. **N-186 is CLOSED.**
### 97.3 §96.10 item 2 — CLOSED for the ordered item (N-187), with two findings on the same function (N-191, N-192)

Both halves §96.4 asked for are present and refuse by name. `require_no_ex_date_mismatch(failures)` raises `SystemExit` naming ISIN and session, is called from the module-level build path with the classifier's own list, and `require_attested_actions_present(attested_actions_missing_from_table())` is called from `build` before any corpus is written. Reverting each in a detached worktree flips the probe:

| Reversion | Probe result |
|---|---|
| delete `require_no_ex_date_mismatch(failures)` | `FAIL N-187: no module-level call passes the classifier's failures list into the gate, so the build still exits 0 with the class published` |
| widen the near miss from `kind in PRICE_SIDE_KINDS` back to `kind != "DIVIDEND"` | `FAIL N-187: a routine AGM within the mismatch window still makes a one-session move fatal: [('INE000000001', '2022-01-08', '-0.5000 but the archive attests an action on 2022-01-11')]` |
| delete `require_attested_actions_present(attested_actions_missing_from_table())` | `FAIL N-188: the build never calls the completeness gate (§14.4: the check sits beside the build)` |

The committed classification is the one the builder now refuses to publish non-empty: **0** ex-date mismatches, and the six §96.4 named re-enter the publish-only classes exactly as the implementer states — **5** `RATIO_SHAPED_UNATTESTED`, **1** `NO_RATIO_MATCH` (the detail list grows 730 → 735, `NO_RATIO_MATCH` 71 → 72, and the total is unchanged at 832). Their current returns, from the committed corpus:

| ISIN | session | return | previous bar | calendar previous | bucket |
|---|---|---|---|---|---|
| `INE292A01023` | 2018-07-06 | **+0.5000** | 2018-07-05 | 2018-07-05 | ratio-shaped |
| `INE292A01023` | 2019-12-09 | **+0.5000** | 2019-12-06 | 2019-12-06 | ratio-shaped |
| `INE292A01023` | 2019-12-20 | **+0.5000** | 2019-12-19 | 2019-12-19 | ratio-shaped |
| `INE803A01027` | 2019-09-18 | **+0.5000** | 2019-09-17 | 2019-09-17 | ratio-shaped |
| `INE251H01024` | 2022-08-12 | **+1.2800** | **2021-08-02** | 2022-08-11 | ratio-shaped |
| `INE784B01035` | 2023-09-26 | **+56.0000** | **2020-07-20** | 2023-09-25 | no-ratio |

Four of the six are session moves near an AGM, and §96.4's diagnosis was right: an AGM carries no share ratio, so it cannot be a mis-dated ratio and the fatal class must not fire on it. **The ordered item is delivered. N-187 is CLOSED.**

Two things in the same function are not right, and both were measured before this section was written.
**N-191 — adjacent bars are not adjacent sessions.** `classify_extreme_moves` pairs `bars` with `bars[1:]` and calls the quotient a *one-session* return; it never asks whether the two `trade_date`s are consecutive in `trading_dates`, which the same header carries. Two of the six are not moves at all: `INE784B01035` 2023-09-26 follows a bar from 2020-07-20 (**792** sessions absent) and produces a "+5600%" return that no session produced; `INE251H01024` 2022-08-12 follows one from 2021-08-02 (**256** absent). Over the corpus, **16,194** adjacent pairs straddle a calendar gap and **58** of **832** extreme moves are computed across one. That is the assumption §6.3 forbids in as many words, and it matters here because the gate's fatal class is defined on these returns: the fix's `0` is a count of a diagnostic whose inputs include 58 gaps. Falsifiable and registered as **N-191**.

**N-192 — a record with no ratio exonerates the move.** The `explained_by_archive_record` branch admits any non-`DIVIDEND` record at the exact date *before* the move is tested for a ratio shape, so an AGM, a scheme, a demerger or a rights entitlement disposes of the move with no diagnostic. **26** moves beyond ±35% sit on a date whose archive records are all non-price-side, and one of them is `INE803A01027` **2019-09-16, +0.5000, under an `OTHER` record** — a 2× move filed as explained by an Annual General Meeting, with the neighbouring 2019-09-18 move (this section's table) published as unattested ratio-shaped. 13,003 of the 13,348 archive keys carry no price-side record. Registered as **N-192**.

### 97.4 §96.10 item 3 — CLOSED (N-188): the build exits on an archive-attested action the table lacks

| Measurement | Result |
|---|---|
| gate | `require_attested_actions_present(gaps)` raises `SystemExit` naming ISIN and ex-date; called from `build` with `attested_actions_missing_from_table()` |
| committed table | gap set **empty** (`attested_actions_missing_from_table() == []`) |
| the SRF witness | withdrawing `SRF` 2021-10-13 from a copy of the table names `INE647A01010 2021-10-13 BONUS`; the gate refuses `INE647A01010 … 2021-10-13 …` |
| reversion | deleting the call from `build` → `FAIL N-188`, quoted in §97.3 |

The check is on the build path, not beside it (§14.4), and it is the same reconciliation §96.4 said no build path called. **CLOSED.**
### 97.5 §96.10 item 4 — CLOSED (N-189), and the artifact that still publishes the old pair (N-194)

`count_forced_exit_outcomes(forced_reasons, held_isins, filled_isins, reason)` returns exits and refusals over `forced_reasons` entries whose ISIN the book held, the held set is read from `portfolio.get_open_positions()` with `quantity > 0` before the session executes, and both counters (demerger and hold-bound) go through it. Four unit tests pin the pairing — (1 fill held) → `(1, 0)`, (1 refusal held) → `(0, 1)`, (2 held, none filled) → `(0, 2)`, (unheld event) → `(0, 0)`, and the bound pair never absorbs the demerger's fill — **4 passed**. Reverting the call site to `len(demerger_exits - demerger_filled)`:

```
FAIL N-189: the counter exists but no session loop calls it, so the demerger pair still counts events (§14.4)
```

**CLOSED.** The residual is that the published artifact was not re-run, and the implementer names it as deliberate rather than hiding it.

**N-194 — the certificate publishes a number the code no longer computes.** `612e82a` touches no path under `reports/` (verified from `git show --name-status`), so `reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json` and `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json` still carry `demerger_forced_exits 0` / `demerger_forced_refusals 66` — the event-counted pair §96.5 proved wrong and this commit replaced. Whether any position was held across a demerger ex-date is therefore **still unmeasured on this tree**, and a reader citing the artifact cites the previous counter. §10.1 makes the correction an append, not an edit, which is the right shape for it. Registered as **N-194**.

### 97.6 §96.10 item 5 — CLOSED (N-190): the gate's verdict is a function of the tree

| Measurement | §96.1 at `ac16232` | §97.1 at `437e0c4` |
|---|---|---|
| heavy runs on one tree | 1, 1, 0, 0 | **0, 0, 0** |
| parallel invocation | `-n auto --dist loadfile -q`, 561 tests, benchmark included | `-n auto --dist loadfile -q --deselect tests/unit/test_portfolio.py::test_n1_replay_guard_o1_lookup_and_bounded_memory`, **564 passed** |
| isolated invocation | none | `-m pytest -q <benchmark>`, no `-n`, **1 passed in 2.41–2.50 s** |
| reconciliation | none | `564 + 1 = 565 of 565 collected`, refusing a deselect that dropped a test |
| ceilings | `250.0` µs/fill, `< 2.5` | **byte-identical**, asserted by `probe_n190` |

Three reversions in a detached worktree, each flipping the probe: emptying `ISOLATED_TIMING_TESTS` → `the gate names no isolated timing test`; dropping the `--deselect` loop → `… is not deselected from the parallel invocation: -m pytest -n auto --dist loadfile -q`; putting `-n auto` back into the isolated command → `the isolated invocation still starts xdist workers`. **CLOSED**, with the residual the fix leaves in place: the benchmark still measures CPU per fill on the host, so a machine loaded by something other than the gate can still exceed 250 µs — the gate no longer creates that contention itself, and it has no witness that it did not. That residual is §12.3's, not this round's, and no threshold was moved for it.
### 97.7 Ruling — `criteria_version` is held at `1.1.16`

The question put to this round is whether re-sealing the manifest pin while holding the version is legitimate. **Ruling: hold `1.1.16`.** The evidence, in order:

1. **No criterion, threshold, fold, calendar pin, cost schedule or gating start moved.** The whole `configs/go_no_go_criteria.yaml` diff is one line: `expected_manifest_fingerprint` `MAN-FPR-V1-f5b1f1f1…` → `MAN-FPR-V1-e79d7915…`, plus a seven-line comment. `configs/partition_spec.yaml` is untouched, and §97.1 re-measures the pin against the file it describes.
2. **The fingerprint moves only because the pin is inside it, and the version label is inside it too.** Measured directly: recomputing with the previous pin yields `CRIT-FPR-V1-9ee0a88c260d27fbe3ab13bb7c8c4c992e7d185986f28f5f803cf5db6db8634e` — the value every pre-§97 artifact cites — and bumping `version` to `1.1.17` yields `CRIT-FPR-V1-6fdfd4ced312b9bfec385708af77199d9e805d335099cb635a2185a1f56c4744`. So the version string is *not* an identifier of a criteria set; `CRIT-FPR-V1` is. Any rule that treats the label as one has been wrong for 16 pins: the file's history contains **16** distinct `MAN-FPR-V1` values and **16** superseded `version:` strings.
3. **A bump cannot repair what it would be for.** `probe_seq10_candidate.py` refuses a row whose `criteria_version` differs from the live version, so `1.1.17` would make the certificate reject the row it was registered under; the row is append-only (§12.1) and cannot be rewritten to `1.1.17`. Holding `1.1.16` keeps the registry consistent, and the cost is exactly the one the implementer names: `1.1.16` now labels two contents.

Because of (2), holding the version is only sound if the repository stops citing a bare version where it means a criteria set, and that part is **not** done. The Phase 2D pair was regenerated to `b2876d98…`; `reports/verdicts/trial_010/seq10_baseline_comparison.json` and `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json` still say `criteria_version 1.1.16` with `CRIT-FPR-V1-9ee0a88c…`, and nothing compares a certificate's stored fingerprint with the live one (`verify_phase2d_verdicts.py` prints it; `probe_seq10_candidate.py` compares the row's *version*). So **two artifacts under one label disagree about the criteria they ran under, and no gate can see it** — **N-193**, registered. The ruling is `HOLD`, conditional on the hash being reconciled by append and by a gate, not on a version bump.

### 97.8 Findings ledger after this section

| | before §97 | after §97 |
|---|---|---|
| rows / ids | 65 / 42 | **74 / 46** |
| latest per id | 35 CLOSED, 6 OPEN, 1 ACCEPTED | **40 CLOSED**, **5 OPEN**, **1 ACCEPTED** |
| OPEN ids | `N-150`, `N-186`…`N-190` | `N-150`, **`N-191`**, **`N-192`**, **`N-193`**, **`N-194`** |

N-186…N-190 gain `CLOSED` rows with `closed_in_section: 97` and the measurement that decided each; the four new rows carry the probe commands added to `scripts/probe_audit_findings.py` in this commit, each passing while the defect it names is live (§96's convention, so the gate stays green and the implementer flips them as they land).
### 97.9 Phase verdicts

| Phase (`CURRENT_STAGE_OF_WORK.md` §97 row) | Verdict | Residual |
|---|---|---|
| Statutory cost schedule / captured sources (item 1) | **CLOSED** — payload, blob and manifest agree, checkout byte-faithful, 8 tests green in a clone | none; the 11 CRLF `manifest.json` working copies are inert (§97.2) |
| Point-in-time corpus builder (item 2) | **CLOSED as ordered** — both gates fire, the fatal class is 0, the six leave it for the stated reason | **N-191** (cross-gap returns, 58/832), **N-192** (non-ratio exoneration, 26 moves) |
| Corporate-action completeness (item 3) | **CLOSED** — build-path gate, empty gap set, SRF witness named | a re-introduced gap is still invisible to the ±35% reconciliation if it lands outside the fatal classes (§96.4's note stands) |
| Demerger forced exit (item 4) | **CLOSED** — held-position counter, 4 tests, call site asserted | **N-194** — the published pair is the old one; whether a hold ever crossed a demerger ex-date is **NOT RUN** on this tree |
| Gate reproducibility (item 5) | **CLOSED** — 3/3 heavy runs, 564+1 reconciled, ceilings unchanged | host contention outside the gate remains unbounded |
| Criteria / seq 10 (item 5, version) | **HOLD `1.1.16`** — no threshold moved, the pin is the only change, `probe_seq10_candidate` CERTIFIED (`N=10`, `N_eval=5`, 2024 fold frozen, holdout sealed) | **N-193** — the trial_010 certificate cites the pre-re-seal hash |
| Phase 2D artifacts | **regenerated and consistent** — `CRIT-FPR-V1-b2876d98…` in both files, `verify_phase2d_verdicts.py` exit 0 | none observed |

### 97.10 Work order (feat-s98), ordered by what it unblocks

1. **N-191 — no cross-gap pair may enter the reconciliation as a return.** The classifier reads adjacent surviving bars as consecutive sessions; two of its six former fatal pairs are 256 and 792 sessions apart and 58 of its 832 "moves" are computed across a calendar gap. Required: a pair whose two `trade_date`s are not consecutive in `trading_dates` is a gap record (or an `UNEXPLAINED_MISSING_RECORD` partition boundary, §6.3), never a one-session return; `probe_audit_findings.py N-191` flips to assert *zero* extreme moves computed across a gap and must exit 1 on this tree before the item is closed. Phase: `CURRENT_STAGE_OF_WORK.md` §97 item 2 (point-in-time corpus).
2. **N-192 — only a price-side record may explain a ratio-shaped move.** The exact-date exoneration branch admits AGM/scheme/rights/demerger records before the ratio test, so 26 moves beyond ±35% — including `INE803A01027` 2019-09-16 at +0.5000 under an `OTHER` record — are filed as explained by a record that carries no ratio. Required: a non-price-side record at the exact date does not exonerate; the move is published as `RATIO_SHAPED_UNATTESTED` with that record named; `N-192` flips and must fail closed on the AGM witness. Phase: same.
3. **N-193 — a certificate's criteria fingerprint must be compared with the live one.** Two artifacts under `criteria_version 1.1.16` cite `9ee0a88c…` while the live criteria compute `b2876d98…`, and no gate reads a stored hash. Required: either regenerate the trial_010 pair (if that is what the run computed) or append a restatement naming the executed hash and the live one, **and** add the comparison to `verify_phase2d_verdicts.py` or `probe_seq10_candidate.py` so a mismatch fails closed by naming both hashes. The version label itself stays `1.1.16` per §97.7. Phase: `CURRENT_STAGE_OF_WORK.md` §97 item 2 / §9.1.
4. **N-194 — restate the seq-10 demerger pair.** Both committed artifacts publish `0` / `66` from the replaced counter. Required: an append-only restatement (a new artifact, or a row in the trial annotation sidecar) naming the pair restated and the held-position measurement that replaces it, with the session-level count the fixed counter produces; "whether any hold crossed a demerger ex-date" is then measured, not inferred. `N-194` flips and must fail closed while the artifact still reads 66. Phase: `CURRENT_STAGE_OF_WORK.md` §97 item 4.

Carried unchanged, still not done: §96.10 items 5 (superseded rows in `get_corporate_actions()`), 6 (the certificate reading the `NON_REPRODUCIBLE_AT` annotation) and 7 (the carried residuals, `N-150` included). N-186…N-190 are closed and leave this list.
### 97.11 What would falsify this verdict

- **N-186**: a tracked path under `data/raw/circulars/` whose worktree bytes differ from its blob *after* a fresh `git checkout -f` of this commit — the 11 `manifest.json` staleness would then be repository state, not a working copy's.
- **N-187 / N-188**: a build on this tree that publishes a non-empty `EX_DATE_MISMATCH` or exits 0 with `attested_actions_missing_from_table()` non-empty; or a reversion of either gate that leaves its probe green.
- **N-189**: a demerger refusal counted for an ISIN the book did not hold, or a held demerger exit counted as a refusal.
- **N-190**: a fourth heavy run on this unchanged tree that exits 1, or a ceiling that differs from `250.0` / `2.5` in the test source.
- **The Ruling**: any criterion value, threshold, fold boundary, calendar pin, cost-schedule row or gating start that differs between the configuration that produced `9ee0a88c…` and the one that produces `b2876d98…`. If one exists, `1.1.16` labels a research decision and must be bumped; the diff measured here is the pin and a comment, and a bump is wrong only for the reason given in §97.7.3.
- **N-191 / N-192 / N-193 / N-194**: their probes as written. Each asserts the defect's current shape, so a fix that leaves the assertion green is no fix.
## §98 — Audit of `1b16d43` (tag `feat-s98-1b16d43`): the reconciliation stops reading a calendar gap as a return and an AGM stops exonerating a 2× move, while the feature layer still has no gap partition and one gate trusts a number it never compares

**Date:** 19 November 2026
**Commit under review:** `f8a7e97` (12 files, +1,343/−160: `configs/go_no_go_criteria.yaml`, the rebuilt 75,390,706-byte corpus with the manifest row that supersedes its predecessor, `data/reference/manifest.jsonl`, the two `reports/analysis/s98/` restatements, `reports/analysis/s98/seq10_drawdown_decomposition.json`, `scripts/derive_2018_2023_corpus.py`, `scripts/diagnose_seq10_drawdown.py`, `scripts/probe_audit_findings.py`, `scripts/probe_seq10_candidate.py`, `tests/unit/test_phase3b2_audit_s98_items.py`, `CURRENT_STAGE_OF_WORK.md`), `960792f` (the regenerated Phase 2D Tier-A pair, one line each) and `1b16d43` (the green-cache row, +19 lines). None of the three touches a path under `reports/verdicts/trial_010/`, `reports/analysis/s94/`, `reports/audit/`, `data/trials/`, `data/raw/2025` or `data/raw/2026` — measured from `git show --name-status`.
**Verdicts:** **§97.10 item 1 CLOSED** (N-191) · **item 2 CLOSED** (N-192) · **item 3 CLOSED** (N-193) · **item 4 CLOSED** (N-194) · **Ruling 1: the pin may be re-sealed under a held `1.1.16`, and the attestation is now mechanical** (§98.6).

### 98.1 Baseline re-measured at `1b16d43`

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Gate W0.5-1 / -1b / -1c | 0 deleted lines in working tree, index or commits; frozen volume **8,442** lines at its pin; active volume an **unchanged prefix** (3,333 committed / 3,333 now); index reproduces over **97** section rows |
| Gate W0.5-2 (verifiers) | **9/9 exit 0**: `verify_audit_findings.py` 210.96 s, `verify_cash_universe_coverage.py` 43.81 s, `verify_historical_snapshot.py` 7.02 s, `verify_phase2a_containment_and_trials.py` 1.34 s, `verify_phase2b5_storage.py` 3.07 s, `verify_phase2b_significance.py` 0.96 s, `verify_phase2c_walkforward.py` 3.20 s, `verify_phase2d_verdicts.py` 4.49 s, `verify_wave1_thin_slice.py` 4.77 s |
| Gate W0.5-3 (suite) | **570 passed** in the parallel invocation (63.08 s) + **1 passed** isolated (2.28 s) = **571 of 571 collected** (67.53 s), **0 skipped, 0 xfailed** — was 565 at §97; the 6 new tests are this commit's |
| Gate W0.5-4 / W0.5-5 | **112** commit-bearing tags verified (`feat-s98-1b16d43` among them; 110 at §97); **1,009** current artifacts match byte count and sha256, **962** superseded rows skipped |
| Criteria / pins | **1.1.16**; live `CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470`; pin `MAN-FPR-V1-be45b7e791d5d3cd683ee119ae4beeae8cba3aab7728ac194d6b19521a691045` **recomputed** by `compute_manifest_fingerprint` over **1,877,557** bytes / **1,971** rows (1,009 current + 962 superseded) — equals the pin |
| Ledger at `1b16d43` | **74** rows / **46** ids — latest-per-id **40 CLOSED**, **5 OPEN** (`N-150`, `N-191`…`N-194`), **1 ACCEPTED** (`N-152`); `verify_audit_findings.py` exit 0 |
| Corpus | `derive_2018_2023_corpus.py --check` **exit 0 — `OVERALL: CURRENT`** over 1,425 archives. **1,425** sessions, **2,735** instruments, **2,578,060** bars, `content_fingerprint DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15`; reconciliation **1** applied / **0** archive / **74** no-ratio / **699** ratio-shaped / **0** ex-date mismatch = **774** moves, **16,194** cross-gap pairs, **58** cross-gap extremes |
| Probes | **N-191…N-194 exit 0** (`PASS <id>`); `--list` ends at **N-194** |
| Trials / fold / holdout | **10** registry rows; `probe_seq10_candidate.py` **exit 0 — `CERTIFIED`**: `N = 10` (expected 10), `N_eval = 5`, one seq-10 row, registry manifest pin `0246c276d52d3a9b…` on both sides, `FOLD-SPEC-V1-36a39987dca…` reproduces the row, artifact 422/7,309, baseline `f5fe3af5a1e2de83…`, sealed-era fold `2025-01-02..2025-03-31` **refused**; `configs/partition_spec.yaml` validation **2024-01-01..2024-12-31**, holdout **2025-01-01..2026-11-11**, `holdout_token_hash` 64 zeros (no token minted) |
| Green cache | tree `456c9e7258ba3b26…`, row `gate_sha 960792f`; this round's `--force-full` re-derived the same tree hash and **appended nothing** (`already recorded; not appending a duplicate row`) — post-commit outcome 3, and the cache path is inside the gate's own excluded set, so `1b16d43` and its parent project to one hash by construction |
| Detached worktree at `1b16d43` | created **outside** the repository, so N-160/N-163's dirty-set probes never see the auditor's scratch tree — §97.1's own error, not repeated; every attack below was run there |

The gate did not move for a second round: same worker split, same ceilings, 571 collected. The suite takes 78.36 s in the committed cache row and 67.53 s here, against an isolated benchmark of 2.28 s.

### 98.2 §97.10 item 1 — CLOSED (N-191): a pair of adjacent surviving bars is a return only if the sessions are adjacent too

`classify_extreme_moves` now takes `trading_dates`, builds `calendar_previous = {trading_dates[i]: trading_dates[i-1]}`, and a pair whose two `trade_date`s are not consecutive increments `cross_gap_pairs`, is appended to `cross_gap_moves` when it clears ±35%, and `continue`s **before** every class. Recomputed this round from the committed corpus rather than from its header:

| Measurement | at `437e0c4` (§97.3) | at `1b16d43`, recomputed here |
|---|---|---|
| adjacent pairs | 2,575,325 | **2,575,325** |
| pairs straddling a calendar gap | 16,194 (unpublished) | **16,194**, published as `cross_gap_pairs` |
| extremes between consecutive sessions | 832 | **774** = 1 applied + 0 archive + 699 ratio-shaped + 74 no-ratio |
| extremes computed across a gap | **58** inside the 832 | **58** published in `cross_gap_detail`, **0** in any class |
| class sum | 832 | **774**; publish-only identity: 773 = 699+74 = (735+72) − 58 + 24 |

The published `cross_gap_detail` set is identical to the one recomputed here pair by pair, and it contains both instruments §97.3 named: `INE251H01024` 2022-08-12 (+1.2800 after 2021-08-02) and `INE784B01035` 2023-09-26 (+56.0000 after 2020-07-20). Of the 58, **53** had been published as ratio-shaped moves and **5** as no-ratio matches — measured by intersecting the 58 against the **previous** corpus blob's 735-row ratio class — which is what makes the identity close: 735 − 53 + 17 = 699, 72 − 5 + 7 = 74, and all 58 leave the classes.

Two reversions, both in a detached worktree:

| Reversion | Probe result |
|---|---|
| delete the `calendar_previous` branch outright | `FAIL N-191: 0` (the synthetic `cross_gap_pairs == 1` assertion fires; the message is a bare number — §98.8.3) |
| keep the counter and the publication, drop the `continue` (the additive fix) | `FAIL N-191: a cross-gap pair still enters a one-session return class` |

**CLOSED.** The residual is not rhetorical: the 16,194 gap-straddling pairs are still in `prices_by_instrument`, and no `UNEXPLAINED_MISSING_RECORD` partition or feature-window boundary exists in the corpus builder. §6.3 asks for both; this commit delivers the reconciliation half, so an EMA or ATR window still spans `INE784B01035`'s 792-session hole in the same file that now refuses to call it a move. Carried as §98.10 item 1.

### 98.3 §97.10 item 2 — CLOSED (N-192): only a record that could carry a share ratio may explain a ratio-shaped move

Exoneration is `any(kind in PRICE_SIDE_KINDS …)`; everything else falls through, and the published row now names what was there instead:

| Measurement | §97.3 | here |
|---|---|---|
| `explained_by_archive_record` | 24 | **0** |
| `ratio_shaped_unattested` / `no_ratio_match` | 735 / 72 | **699 / 74** |
| ratio-shaped moves naming a non-price-side record | not published | **18** — 13 `DEMERGER`, 2 `RIGHTS`, 1 `DIVIDEND`, 1 `DEMERGER,DIVIDEND`, 1 `OTHER` |
| `INE803A01027` 2019-09-16 +0.5000 | filed as explained by `OTHER` | **published** as ratio-shaped with `record: OTHER`, and measured **absent** from the pre-fix ratio class |

The 18 do not equal the 24, and the difference is not slack: 17 are moves the fix newly published, and 1 — `INE080A01014` 2020-03-16 — was already ratio-shaped because the old branch only exonerated `kind != "DIVIDEND"`, so a pure dividend record never disposed of a move. Measured by intersecting the 18 against the previous blob's ratio class: 18 − 1 = 17 newly published. The witness §97.3 wrote the finding around is now on the right side of the line — a 2× move beside an Annual General Meeting is published with the AGM named, not filed as explained by it.

| Reversion | Probe result |
|---|---|
| restore the `non_dividend` branch | `FAIL N-192: the exact-date exoneration branch still admits a record that carries no share ratio` |
| keep the price-side test and re-add `if any(kind not in PRICE_SIDE_KINDS …)` after it | `FAIL N-192: an AGM at the exact date still exonerates the move without a diagnostic` |

**CLOSED.** The behavioural half of the probe is what catches the additive form; the source-text assertions alone would not have.

### 98.4 §97.10 item 3 — CLOSED (N-193): the certificate's stored hash is compared with the live one, and the pin-only claim is recomputed

| Measurement | Result |
|---|---|
| live criteria | `CRIT-FPR-V1-535e47f5…` under `criteria_version 1.1.16` |
| pin | `MAN-FPR-V1-be45b7e7…`, recomputed from the committed manifest (§98.1) |
| pin-only attestation | substituting `f5b1f1f1…` into the **live** criteria reproduces `CRIT-FPR-V1-9ee0a88c260d27…` exactly; the §97 intermediate pin `e79d7915…` reproduces `b2876d98…` — both recomputed here, not read |
| certificates | three stored hashes, all `9ee0a88c…`, all reconciled: `reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json`, `reports/verdicts/trial_010/seq10_baseline_comparison.json`, `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json` |
| `probe_seq10_candidate.py` | **exit 0 — `CERTIFIED`**, printing `Certificate … reconciles with CRIT-FPR-V1-535e47f5a4a9…` three times |

`certificate_problem` refuses by name, not by assertion alone. Measured inputs against a stale certificate:

| Attack | Result |
|---|---|
| no restatement at all | refused, quoting `9ee0a88c…` and `535e47f5…` in one message |
| forged `executed_criteria_fingerprint` | refused: the restatement records `CRIT-FPR-V1-forged`, the certificate cites `9ee0a88c…` |
| forged `executed_manifest_fingerprint` | refused: substituting `MAN-FPR-V1-forged` yields `6b156260…`, not the cited hash — *"the difference … is not pin-only"* |
| forged `live_criteria_fingerprint` | refused: *"the restatement is stale by name"* |
| artifact dropped from `certificates` | refused: names no executed fingerprint for it |
| **a criterion moved, not the pin** (six numeric fields, each doubled in memory) | refused for every one: `sessions_per_year`, `min_total_trades`, `max_drawdown_duration_sessions`, `min_execution_latency_sessions`, `max_hold_trading_sessions`, `expected_baseline_calendar_sessions` — each moves the live hash and makes the restatement stale |

The last row is what decides the finding. §97.7's Ruling was sound only if a restatement could not launder a criteria change, and the recomputation makes that impossible: an attestation is accepted exactly when substituting one pin string into the live criteria reproduces the cited hash. probe N-193 asserts the same chain and exits 0. **CLOSED.**

Two residuals are the gate's shape, not the finding's. First, **no `verify_*.py` runs `probe_seq10_candidate.py`** — the nine discovered verifiers do not include it — so the certificate gate fails closed when a round runs it, not when a commit lands; §97.10 item 3 permitted either `verify_phase2d_verdicts.py` or `probe_seq10_candidate.py`, and this is the probe route. Second, the registry row still carries no `criteria_fingerprint`, so `1.1.16` now labels **three** criteria sets (`9ee0a88c…`, `b2876d98…`, `535e47f5…`). Carried as §98.10 items 3-4.

### 98.5 §97.10 item 4 — CLOSED (N-194): the demerger pair is restated by a replay this round re-ran, not by a file it read

The two artifacts are unedited (last commit `12c6dae`) and still publish `0` / `66`; the append is `reports/analysis/s98/seq10_demerger_restatement.json`. This round re-rendered seq 10's own configuration read-only, over the committed corpus, into a temporary registry copy, hashing the four registry files and the three certificates before and after:

| Quantity | committed artifact / restatement | this round's independent replay |
|---|---|---|
| sessions | 1,425 | **1,425**, 2018-04-02..2023-12-29 |
| `hold_bound_forced_exits` / `hold_bound_refusals` | 422 / 7,309 | **422 / 7,309** |
| `demerger_forced_exits` / `demerger_forced_refusals` | 0 / 66 published, **0 / 0 restated** | **0 / 0** |
| `max_drawdown` | `0.7264709014681672238018483779` | **`0.7264709014681672238018483779`**, digit for digit |
| closed trades / final equity | 781 / `1072507.24` | **781 / `1072507.24`** |
| criteria | `535e47f5…` under `1.1.16` | **same** |
| files mutated | — | **none** — registry (4 files) and trial_010 pair + s94 baseline unchanged, sha256 before = after |
| wall time | — | 504.1 s |

"No position crossed a demerger ex-date in this configuration" is therefore a measurement, and the 66 are events on ISINs the book did not hold — the event-versus-holding confusion §96.5 named. The gate's refusals were measured too:

| Attack | `demerger_restatement_problem` |
|---|---|
| no restatement | refused, naming `(0, 66)` |
| restated pair `0/65` against a `0/66` artifact | refused, quoting both |
| `measurement: {}` or a non-integer | refused, naming the missing key |
| replay `hold_bound_refusals` forged to 1,234 | refused: *"the measurement is not this artifact's run"* |
| replay `hold_bound_forced_exits` forged to 1 | refused, same reason |
| artifact pair moved to `0/65` | refused |
| **measurement `7/9` beside its own `0/0` replay** | **accepted** — and that is the residual |
| `restates` list emptied | accepted (the list is prose; the pair and the counters are the gate) |

The seventh row is a real asymmetry, named rather than papered over: the certificate type-checks `measurement` but never compares it with the `replay` block it *does* compare against the artifact, so a restatement whose measurement contradicts its own replay passes `probe_seq10_candidate.py`; only probe N-194 catches it, because the probe asserts `replay.demerger_* == measurement.demerger_*`. It does not reopen N-194 — the ordered artifact exists, names the pair, and carries a measurement this round reproduced — but it is the additive-fix shape §14.4 warns about, one function away. Carried as §98.10 item 2. **CLOSED**, with that residual.

### 98.6 Ruling 1 — the pin is re-sealed under a held `1.1.16`, and a pin-only attestation is now mechanical

**Evidence.** At `1b16d43` the criteria pin is `MAN-FPR-V1-be45b7e7…` and the live fingerprint `CRIT-FPR-V1-535e47f5…`, while three certificates cite `9ee0a88c…` under the same `criteria_version 1.1.16`. `configs/go_no_go_criteria.yaml` moved one pin line and a comment since §97; no criterion, threshold, fold boundary, calendar pin, cost-schedule row or gating start moved (measured: six numeric criteria fields each move the hash, so a moved one could not be attested by a pin substitution — §98.4). The pin had to move because `data/reference/manifest.jsonl` gained a row and superseded another when the corpus header was rebuilt, and §10.1 makes that an append.

**Ruling.** §97.7 is **continued, not superseded**: `criteria_version` stays `1.1.16`, and a certificate may cite a fingerprint other than the live one **only** when an appended restatement names that artifact, the executed fingerprint and the executed pin, and substituting that pin into the live criteria reproduces the cited fingerprint. **It changes one definition** — what "certified under `1.1.16`" means for a stored hash: a claimed criteria set, checked by recomputation, instead of a version label. **It changes nothing numeric**: no threshold, fold, window, cost row, trial count or gating start, and no version bump. **Its probe** is `python scripts/probe_audit_findings.py N-193` plus `python scripts/probe_seq10_candidate.py`, both exit 0 here and both refusing the forgeries in §98.4. **Its work** is §98.10 items 3-4. **Its falsifier**: a configuration differing from the one that produced `9ee0a88c…` in anything other than `expected_manifest_fingerprint` that still reconciles through the restatement — measured impossible for the six numeric fields above, and a threshold, fold, calendar or cost change lives in one of them; or a fourth re-seal that moves the pin without appending a restatement naming the new live hash, which would refuse **every** certificate rather than pass one.

The cost is stated plainly because it is real: one label now denotes three criteria sets, and the only thing distinguishing them is a hash nobody is required to cite outside the three certificates. That is §98.10 item 4's job, not a reason to bump a version an append-only registry row names.

### 98.7 The rebuild is a header change, measured against the previous blob

| Top-level key | equal to `609084fa…` (the superseded blob) |
|---|---|
| `prices_by_instrument` | **yes** — every bar, equal as parsed |
| `trading_dates` / `universe_by_date` / `symbols_by_instrument` | **yes** |
| `session_count` / `instrument_count` / `total_instrument_records` | 1,425 / 2,735 / 2,578,060 — **same** |
| `content_fingerprint` / `corporate_actions_fingerprint` | `DATA-CTNT-V2-cb4832c0…` / same |
| `reconciliation` | **differs** — the only one: 1/24/735/72/0 → 1/0/699/74/0 with the gap fields added |

So "prices unchanged" is not the implementer's assurance; it is the diff of the two committed blobs. The corpus file's own manifest row matches the file on disk (75,390,706 B / `ea0b65a3…`), and the re-seal is exactly the pin consequence of that one header change. The recomputation also settles two things the fix could have broken silently: no bar carries a close ≤ 0 or a zero volume (so the `previous.close <= 0` skip never runs ahead of the gap counter), and the 58 published gap rows are a **set** equal to the recomputed one, not merely a matching count.

### 98.8 Findings ledger after this section

| | before §98 | after §98 |
|---|---|---|
| rows / ids | 74 / 46 | **78 / 46** |
| latest per id | 40 CLOSED, 5 OPEN, 1 ACCEPTED | **44 CLOSED**, **1 OPEN**, **1 ACCEPTED** |
| OPEN ids | `N-150`, `N-191`…`N-194` | **`N-150`** |

N-191…N-194 gain `CLOSED` rows with `closed_in_section: 98` and the measurement that decided each; `verify_audit_findings.py` exits 0 over **46** findings with every probe matched. Three observations are recorded without being promoted to findings, because none of them is a contract the work order set:

1. **The 16,194 gap pairs outlive their own finding.** N-191 closes on the reconciliation and the feature layer is untouched; that is a residual in the closure row, not a line of prose here.
2. **`demerger_restatement_problem` trusts a measurement it could compare.** §98.5, measured.
3. **One refusal is a bare number.** Deleting the `calendar_previous` branch yields `FAIL N-191: 0` because that assertion carries no message; the probe refuses, the diagnostic is not self-describing. Cosmetic, and left as found (§3: a change should trace to the request, and this one would not).

### 98.9 Phase verdicts

| Phase (`CURRENT_STAGE_OF_WORK.md` §98 row) | Verdict | Residual |
|---|---|---|
| Point-in-time corpus builder / calendar adjacency (item 1) | **CLOSED** — 774 moves, 58 gap records, recomputed set equality, two reversions refused | **the 16,194 pairs and 58 gaps remain in prices with no `UNEXPLAINED_MISSING_RECORD` partition**; feature lookbacks still span them (§6.3, §98.10 item 1) |
| Corporate-action attestation / price-side exoneration (item 2) | **CLOSED** — archive exoneration 0, 18 named rows, witness published with `OTHER`, additive reversion refused | the 18 stay unattested; a demerger or rights repricing is indistinguishable from a mis-dated ratio by this diagnostic alone |
| Certificate / criteria reconciliation (item 3) | **CLOSED** — live `535e47f5…`, pin `be45b7e7…` recomputed, three certificates reconciled, five forgeries and six moved criteria refused | the certificate is a standing probe, not a verifier the gate runs; the registry row carries no fingerprint field |
| Seq-10 demerger restatement (item 4) | **CLOSED** — artifacts unedited, `0/0` restated, independently replayed at 422/7,309 and `0.7264709…` with no file mutated | the gate type-checks the measurement instead of comparing it with its own replay block; nothing re-runs the engine per commit |
| Criteria / seq 10 / fold / holdout | **held and sealed** — `N=10`, `N_eval=5`, `CERTIFIED`, fold spec reproduces, sealed-era window refused, validation fold 2024 untouched, holdout `2025-01-01..2026-11-11` unread | `1.1.16` labels three criteria sets (§98.6) |
| Phase 2D artifacts | **regenerated and consistent** — `960792f` carries `CRIT-FPR-V1-535e47f5a4a9…` in `.json` and `.md`, `verify_phase2d_verdicts.py` exit 0 | none observed |

### 98.10 Work order (feat-s99), ordered by what it unblocks

1. **The gap must partition the feature layer, not only the reconciliation.** §6.3 requires a missing-session sequence to be an `UNEXPLAINED_MISSING_RECORD` boundary and feature engines to refuse lookbacks across it. Measured on this tree: 16,194 adjacent pairs straddle a calendar gap and 58 clear ±35%, and no derived-layer consumer is told. Required: a committed partition (or per-instrument segment boundary) that every rolling feature reads, plus the count of feature values currently computed across a gap. The probe that must fail closed is a new one asserting that no EMA/ATR window spans a gap pair for `INE251H01024` or `INE784B01035`, and it must exit 1 before this item is closed. Phase: `CURRENT_STAGE_OF_WORK.md` §98 item 1 (point-in-time corpus) / §6.3.
2. **`demerger_restatement_problem` must compare the measurement with the replay it already trusts.** `measurement: 7/9` beside `replay: 0/0` passes the certificate (§98.5). Required: the two demerger keys agree between `measurement` and `replay`, refused by name otherwise, with `probe_audit_findings.py N-194` extended to fail closed on that pair — today only the probe's own assertion catches it. Phase: §98 item 4 / §13.2.
3. **The certificate must be in the gate.** Measured: 9 discovered verifiers, none of them `probe_seq10_candidate.py`, so a criteria re-seal that forgot its restatement leaves `verify_audit_append_only.py` green and refuses only when a round remembers to run the certificate. Required: either a `verify_seq10_certificate.py` on the gate's discovery path, or the certificate invoked from an existing verifier, with its exit status required zero. Phase: §9.1 / §11.3.
4. **Record the executed criteria fingerprint on the registry, not a third meaning for `1.1.16`.** The row is append-only, so this is a new sidecar field or annotation row naming row, version and executed hash — the shape §97.7's Ruling was conditional on. Phase: §9.1 / §97.7 Ruling.
5. Carried unchanged: §96.10 items 5 (superseded rows in `get_corporate_actions()`), 6 (the certificate reading the `NON_REPRODUCIBLE_AT` annotation) and 7 (the carried residuals, `N-150` included). N-191…N-194 leave this list.

### 98.11 What would falsify this verdict

- **N-191**: a class sum exceeding the number of extremes computed between consecutive sessions on any later corpus (`in_classes > consecutive_extremes`), or a `cross_gap_detail` differing from a pair-by-pair recomputation, or a gap pair published in `ratio_shaped_detail` — the exact shape the additive attack produced.
- **N-192**: `explained_by_archive_record > 0`, a ratio-shaped row naming a `SPLIT`/`BONUS`/`CONSOLIDATION` record at its own date, or the `INE803A01027` witness filed under anything but a named non-price-side record.
- **N-193**: a certificate passing `certificate_problem` while the criteria differ from the pin-substituted set in any field other than `expected_manifest_fingerprint`; or a restatement's `live_criteria_fingerprint` accepted when the committed criteria compute another value (measured refused); or a fourth re-seal with no appended restatement that still reports `CERTIFIED`.
- **N-194**: a replay that does not return 422/7,309 and 0/0 with `max_drawdown 0.7264709…` on this corpus, or any registry or artifact digest that moves across a re-render. Today's pass is a 504-second read-only run, not an inference from the file.
- **Ruling 1**: any criterion, threshold, fold boundary, calendar pin, cost row or gating start differing between the configuration that produced `9ee0a88c…` and the one producing `535e47f5…`. If one exists, `1.1.16` labels a research decision and the Ruling is wrong, not merely stale — and the substitution test would have to accept it, which §98.4 measured it does not.
- **§98.10 item 1**: a feature value on `INE784B01035` computed across its 792-session hole. That is where the open part of N-191 now lives.

## §99 — Audit of `3136783` (code commit under tag `feat-s99-b1e5fbd`): the gap now partitions the feature layer and a probe proves it, the certificate runs on the gate, and the implementer's own seq-10 column publishes two profit factors no artifact computes

**Scope.** `3136783` carries the §98.10 work order: `scripts/measure_feature_gap_partition.py` (279 lines), `reports/analysis/s99/feature_gap_partition.json`, `scripts/verify_seq10_certificate.py` (27), `scripts/run_seq11_candidate.py` (459), `configs/trial_011_candidate.yaml` (81), `tests/unit/test_phase3b2_audit_s99_items.py` (181), three `reports/verdicts/trial_011/` artifacts, and the engine/registry/criteria edits behind them. `b1e5fbd` adds `.continue/` to `.gitignore` and appends the green row for tree `16641961842ea5d7…` (577 passed, 72.04 s); the tag `feat-s99-b1e5fbd` points at `b1e5fbd`.

**Verdicts:** **§98.10 item 1 CLOSED** (N-191) · **item 2 CLOSED** (N-194) · **item 3 CLOSED** (N-193) · **§98.6 Ruling 1 holds** — `seq 11`'s controls are in `configs/trial_011_candidate.yaml`, so the live `1.1.16` does not move and the three seq-10 certificates stay attested · **seq 11 evaluated: NO-GO, on `CRIT-STAT-02`, not on statistical ambiguity** · **new HIGH finding N-195 OPEN** — the seq-10 status column publishes two profit factors no committed artifact computes.

### 99.1 Baseline re-measured at `3136783`

`python scripts/verify_audit_append_only.py --force-full`, in the primary checkout, exit 0.

| Measurement | Value |
|---|---|
| Overall verdict line | `ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| §11.1 append-only | working tree & index vs HEAD: **0 deleted lines**; commits since `a3a40f1`: **0 deleted lines** |
| Frozen volume | sha256 and 8,442 lines match the pin (1-78) |
| Active volume | `volume2.md` HEAD content an unchanged prefix (3,517 committed / 3,517 now) |
| Audit index | matches the volumes (**98** section rows, before this append) |
| Discovered verifiers | **10**, every one exit 0 — `verify_audit_findings.py` 202.80 s, `verify_cash_universe_coverage.py` 53.53 s, `verify_historical_snapshot.py` 6.02 s, `verify_phase2a_containment_and_trials.py` 1.92 s, `verify_phase2b5_storage.py` 3.15 s, `verify_phase2b_significance.py` 1.05 s, `verify_phase2c_walkforward.py` 3.18 s, `verify_phase2d_verdicts.py` 4.76 s, `verify_seq10_certificate.py` 1.25 s, `verify_wave1_thin_slice.py` 4.88 s |
| Suite | 576 parallel + 1 isolated = **577 of 577 collected**, **0 skipped, 0 xfailed**, 63.77 s |
| Source tree | `16641961842ea5d7…`; already recorded, **no duplicate green row appended**; tree clean after the run |

Two method facts cost this round time and are recorded so the next one does not repeat them:

1. **A linked worktree is not a valid gate environment here.** In `C:/Users/DEB/sa_audit_s99` (detached at `3136783`) the same command exits 1 with `4 FINDING PROBE(S) FAILED`: N-165, N-167, N-168 and N-169 write `.git/info/exclude`, and in a worktree `.git` is a *file*, so `exclude.parent.mkdir(...)` raises `FileExistsError` on the worktree's own `.git` path. The four probes pass in the primary checkout. The red run was mine, not the repository's — but it means a worktree cannot produce a §99.1 baseline.
2. **A worktree source mutation silently does not apply.** `signal_core` resolves to the primary checkout's `src` even when the process runs inside the worktree (`MODULE_FILE` printed for `signal_core.features.engine` was the primary path). One attack below was void for that reason and was redone in the primary checkout, with the printed module path and the written marker both confirmed before the measurement was believed.

### 99.2 N-191 — the partition reaches the feature layer (CLOSED)

`reports/analysis/s99/feature_gap_partition.json` derives its boundaries from the calendar and the committed corpus, never from a typed list:

| Field | Value |
|---|---|
| `partition_fingerprint` | `GAP-PTN-V1-3fe08af638a6ee723031692ffeccb3aa6d6e6f585fd45fe0344128c75742ade6` |
| instruments with a hole / in-series missing sessions | **539** / **58,941** |
| subsegments | **16,733** |
| material holes (≥ 20 sessions) | **74**, longest 792 |
| feature values measured / computed across a gap | **28,457,131** / **0**, over 12 features |
| witness `INE251H01024` (GVKPIL) | 1,062 bars, 363 missing, longest contiguous 256, 28 segments, first boundary 2021-01-18 |
| witness `INE784B01035` (WINSOME) | 404 bars, 1,021 missing, longest contiguous 792, 81 segments, first boundary 2018-04-03 |

The witness geometry is recomputed here from the raw corpus, not read from the artifact: 363 missing / 256 contiguous / 28 segments and 1,021 / 792 / 81; the largest bar-to-bar calendar distance is 257 sessions (2021-08-02 → 2022-08-12) and 793 (2020-07-20 → 2023-09-26), so `longest_hole_sessions` is the longest contiguous run and its label is accurate. `scripts/measure_feature_gap_partition.py --check` reproduces the committed bytes (exit 0). The value the fix suppresses is concrete: on the clean tree the engine's `sma_20` at `INE251H01024` 2021-02-08 is `None`, while the 20-surviving-bar mean an unpartitioned engine would publish is 2.990000.

Attacks, each reverted, tree clean after:

| Attack | Artifact `--check` | `probe N-191` |
|---|---|---|
| shared `partition_into_continuous_subsegments` returns one segment | **exit 1** — "the committed partition is not the one this corpus derives" | **exit 1** — "INE251H01024 has 27 contiguous hole(s) but 1 segment(s)" |
| committed artifact tampered: `values_across_gap` 0 → 7 | **exit 1** | **exit 1** — "7 feature value(s) are computed across a gap" |
| engine consumer site (`compute_standard_features_for_instrument`) unpartitioned | — | **exit 1** — "sma_20 is computed at 2021-02-08, the first bar after a gap, so its window spans the 363 boundary(ies)" |

**CLOSED.** The residual is named, not implied: the 58,941 missing sessions and 74 material holes are still records absent from `prices_by_instrument`, so "what was observable at T" still depends on a derived artifact plus a probe rather than on `UNEXPLAINED_MISSING_RECORD` rows in the validated layer; and the engine's default is `fail_closed_on_unexplained=False`, so a caller is told by `None` values, not by an exception.

### 99.3 N-193 — the certificate is on the gate (CLOSED)

`scripts/verify_seq10_certificate.py` is a 27-line discovery hook that returns `probe_seq10_candidate.main()` and adds no assertion of its own — the two-paths shape §14.4 names is absent. The gate discovers **10** verifiers including it, and it exits 0 in 1.25 s. `probe_seq10_candidate.py` reports `CERTIFIED`: `N = 11`, `N_eval = 6`, one seq-10 row at `1.1.16`, `FOLD-SPEC-V1-36a39987dca…` reproducing the row, three certificates reconciled through the §98 restatements, the demerger pair restated, and the sealed-era window refused by the engine.

Attack, in the worktree (the target files are read by path, so worktree resolution is the correct one here): forge both `criteria_fingerprint` fields in `reports/verdicts/trial_010/seq10_baseline_comparison.json` to `CRIT-FPR-V1-000…` → the verifier exits 1, naming the restatement's recorded `9ee0a88c…` against the cited `000…`. Baseline exit 0.

**CLOSED.** Residuals: (a) the verifier set is a glob, so deleting `scripts/verify_seq10_certificate.py` drops discovery to **9** with no complaint — measured; nothing pins the inventory, and this is a property of every `verify_*.py`, not of this one; (b) the certificate is still not run by any *other* verifier, so the guarantee is "one more file on the discovery path", which is exactly what §98.10 item 3 asked for.

### 99.4 N-194 — the measurement is compared with its own replay (CLOSED)

`demerger_restatement_problem` now refuses a replay that omits either key and refuses a `measurement` that differs from `replay` on either. Attack: set the restatement's measurement to 7/9 while its replay stays 0/0 → the verifier exits 1, "the restatement measures demerger_forced_exits 7, but its own replay returns 0; the measurement is not this replay's (§98.10 item 2)". `probe N-194` also exits 1 under the same tamper.

**CLOSED.** Residual: `FAIL N-194: ` with an empty diagnostic under that tamper — cosmetic, and the same bare-message shape §98.8.3 recorded.

### 99.5 G2A-6.7 — the exemption counts the evaluations *preceding* the row

`trials.py` computes `prior_evaluations = sum(1 for earlier in registry.get_trials() if earlier.seq < row.seq and registry.get_evaluation(earlier.trial_id) is not None)` and admits an unmatched artifact only when it is `IN_SAMPLE` and `declared_count == prior_evaluations`. Measured against the live ledger (6 evaluations after seq 11 appended): the seq-10 artifact declares 5 and `verify_phase2a_containment_and_trials.py` exits **0**; doctored to 6 (today's total) it exits **1**; doctored to 4 it exits **1**. So a later trial's append cannot retroactively un-attest an earlier artifact, an erased ledger computes 0 and fails, and an inflated claim fails.

### 99.6 seq 11 — measured, and refused by its own criteria

| Metric | seq 10 | seq 11 |
|---|---|---|
| Closed round trips | 781 | **1,101** |
| Profit factor (closed only) | 1.058319814406791810331206697 | 1.215059254115567619027472003 |
| Net profit factor | 1.020542895… | 1.162521938150914922887549000 |
| Liquidated profit factor | 1.062288461598504234259941013 | 1.281989670001573246299919807 |
| Max portfolio drawdown | 0.7264709014681672238018483779 | 0.5193109028986467506648719406 |

The pre-registered drawdown claim is met: the reduction is exactly **0.2071599985695204731369764373 absolute, 28.5159 % relative**. `overall_verdict` is **NO-GO** because `CRIT-STAT-02` reads `1.2820 < 1.50` (`configs/go_no_go_criteria.yaml` pins `min_profit_factor: "1.50"`); `summary_counts` is 15 PASS / 6 FAIL / 7 NOT_RUN, `validation_folds_count` is 0, `evaluated_trial_count` 6. The registry manifest is `total_trials 11` / `evaluation_count 6`, head `e76c249f…`; the criteria pin is `b8ff325c…`, which is also what the live criteria hash under `1.1.16` excludes (`expected_trial_registry_manifest_sha256`, N-139), so the live fingerprint stays `CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470`. The seq-11 controls live in `configs/trial_011_candidate.yaml` (sha256 `199786951cb1c53693732cd52e5a923acfe23cddf0983283706f3a3d6b21d84e`, equal to the comparison artifact's `pre_registration.sha256`), not in `configs/go_no_go_criteria.yaml` — which is what keeps §98.6 Ruling 1 true. The 2024 validation fold is untouched and the holdout `2025-01-01..2026-11-11` is sealed (the engine refuses a sealed-era window by name). The verdict is therefore a NO-GO on the committed floor, and the drawdown improvement does not buy an exemption from it.

### 99.7 N-195 — two cells in the implementer's seq-10 column are unsourced (OPEN, HIGH)

`CURRENT_STAGE_OF_WORK.md:2535` publishes seq 10 as profit factor `1.1178…` and liquidated profit factor `1.1773…`. The committed artifact publishes `closed_only_profit_factor` **1.058319814406791810331206697** and `liquidated_profit_factor` **1.062288461598504234259941013**. The two cells that do match — 781 closed round trips and final equity 1,072,507.24 — are the same row, and the seq-11 column matches its artifact exactly, so the error is confined to the seq-10 pair. `grep -rn "1\.1178"` over the tree returns **only** that status line: no verdict, analysis artifact, config, or script produces either figure.

Under §9.1 a published figure is a computed one, and under §11.3 a status claim must cite the verdict that grants it. A doc that prints a profit factor 5.9 % above the artifact's is a claim with no computation behind it, in the one document a reader uses to see what the round achieved. This is **N-195**, HIGH, OPEN; the doc is the implementer's (§11.4), so the correction is theirs and the probe that must fail closed is `python scripts/probe_audit_findings.py N-195`, added here to assert the defect while it is open and to fail the moment the row matches its artifact.

### 99.8 Findings ledger after this section

| | before §99 | after §99 |
|---|---|---|
| rows / ids | 78 / 46 | **79 / 47** |
| latest per id | 44 CLOSED, 1 OPEN, 1 ACCEPTED | **44 CLOSED, 2 OPEN, 1 ACCEPTED** |
| OPEN ids | `N-150` | **`N-150`, `N-195`** |

No new CLOSED row is appended for N-191, N-193 or N-194: they already carry a CLOSED row from §98, and `validate_ledger` treats a repeated id at the same status as a duplicate (`ALLOWED_TRANSITIONS`, N-157). Their closure is re-verified here and cited by §99.2-99.4; the ledger keeps the §98 rows as the closure of record.

### 99.9 Phase verdicts

| Phase (`CURRENT_STAGE_OF_WORK.md` §99 row) | Verdict | Residual |
|---|---|---|
| Gap partition of the feature layer (§98.10 item 1) | **CLOSED** — 539 instruments / 58,941 sessions / 16,733 subsegments committed, 0 of 28,457,131 values across a gap, three attacks refused | holes remain absent records, not `UNEXPLAINED_MISSING_RECORD` rows; compliance is `None`, not an exception |
| `demerger_restatement_problem` measurement vs replay (§98.10 item 2) | **CLOSED** — 7/9-beside-0/0 refused by name | probe's bare failure message |
| Certificate on the gate (§98.10 item 3) | **CLOSED** — 10th verifier, exit 0, forged fingerprint refused | verifier inventory is an unpinned glob |
| seq 11 candidate / G2A-6.7 / criteria `1.1.16` | **evaluated; NO-GO** — 1,101 trades, dd −0.20716, `CRIT-STAT-02` 1.2820 < 1.50, N=11/N_eval=6, live pin unmoved | the strategy's drawdown gain is not a pass; the floor is the binding constraint |
| Status document (§11.3) | **FAIL** — N-195 OPEN | two cells have no computation behind them |
| Phase 2D artifacts / holdout | **held** — 2024 fold untouched, `2025-01-01..2026-11-11` sealed and refused | none observed |

### 99.10 Work order (feat-s100), ordered by what it unblocks

1. **Correct the seq-10 profit-factor cells, or cite the artifact that produces them** (N-195). Required: `CURRENT_STAGE_OF_WORK.md` publishes `1.058319814…` / `1.062288461…`, or names a committed artifact that computes `1.1178…` / `1.1773…`; the row may not stand unsourced. The probe that must fail closed is `python scripts/probe_audit_findings.py N-195`, which today asserts the defect and must be replaced by a fix-assertion in the same commit. Phase: §9.1 / §11.3.
2. **Pin the verifier inventory.** Measured: deleting one `verify_*.py` drops discovery from 10 to 9 with no diagnostic, so a check can leave the gate by deleting a file. Required: a committed expected set (or count) the gate compares against discovery, with the deletion refused by name. Phase: §12.3.
3. **Carry the executed criteria fingerprint on the registry surface used by readers.** The evaluations sidecar now records it (seq 11's row carries `CRIT-FPR-V1-535e47f5…`, `eval_hash b1d90636…`), but `criteria_version` still labels three criteria sets and nothing a reader of the row sees distinguishes them without recomputation. Phase: §9.1 / §97.7 Ruling.
4. Carried unchanged: §96.10 items 5 (superseded rows in `get_corporate_actions()`), 6 (the certificate reading the `NON_REPRODUCIBLE_AT` annotation) and 7 (the carried residuals, `N-150` included); plus the bare failure message in `probe N-194` (§99.4).

### 99.11 What would falsify this verdict

- **N-191**: any feature value whose lookback window contains an `UNEXPLAINED_MISSING_RECORD` boundary on a later corpus; or `partition_into_continuous_subsegments` returning fewer segments than a witness's contiguous holes + 1; or a `feature_values_across_gap` that stays 0 when the engine is unpartitioned — the opposite of what §99.2 measured.
- **N-193**: a certificate passing while its stored `criteria_fingerprint` differs from the restatement's recorded executed hash; or a fourth re-seal moving the live hash with no appended restatement, yet `verify_seq10_certificate.py` exiting 0.
- **N-194**: a restatement whose `measurement` differs from its own `replay` and still exits 0; or a replay that omits the pair and is accepted.
- **G2A-6.7**: an artifact declaring today's ledger total (6) accepted for a trial that ran when the ledger held 5; or an erased ledger making `prior_evaluations` 0 and still being exempted.
- **N-195**: a committed artifact, verdict or config computing `1.1178…` or `1.1773…` for seq 10 — which `probe N-195` now scans for on every gate run. If one exists, the finding is wrong and the status row is sourced.
- **§99.1**: a gate run in a linked worktree that reports green — it cannot, and the four `.git/info/exclude` probes are the reason.
## §100 — Audit of `7c0957e` (tag `feat-s101-7c0957e`): the pre-registration is clean, the STOP is correct, and the QA that produced it tests the wrong thing — two of its five stops are attested ₹ dividends it excludes by rule, the miss it exists to catch is checked on the signal day only, and the artifact it writes gates no code

**Scope.** `f2133ef` adds `configs/trial_012_candidate.yaml` alone (sha256 `66a05b4a…`, 4-clause `all_of` decision rule, window `2018-04-01..2023-12-31`, holdout `2025-01-01..2026-11-11`). `7c0957e` adds `scripts/run_seq12_candidate.py` (558 lines), `reports/analysis/s101/seq12_data_qa.json` (7,363 B), `src/signal_core/strategy/mean_reversion.py`, `tests/unit/test_phase3b2_seq12_data_qa.py` and `tests/unit/test_phase3b2_seq12_mean_reversion.py` (7 + 7 tests), and edits `features/engine.py` (+3 fields), `strategy/__init__.py`, `strategy/swing.py` (signature widened to `Strategy`) and `scripts/run_phase3b2_walkforward.py` (the `strategy=` seam). `3f7691f` appends the green row only. The tag is lightweight and points at `7c0957e459f7de5abd4870c1b6f70f8741380496`.

**Verdicts:** **the STOP is justified — on 3 of its 5 rows, not 5** · **its stated reason is false for 2 of the 5** (N-196) · **the trigger it protects is tested too narrowly to be the protection it claims** (N-197) · **the QA gates no code path** (N-198) · **the exit/hold side of a delivery-swing rule is unmeasured, and `at_lower_circuit: 0` is unmeasured rather than zero** (N-199) · **the "no record" evidence rests on archives covering two-thirds of the corpus** (N-200) · **the NIFTYBEES boundary the decision rule compares against is unadjusted in the corpus** (N-201) · **pre-registration leaves one interaction unpinned** (N-202).

### 100.1 Baseline re-measured at `3f7691f`

`HEAD = 3f7691f`, working tree clean at audit time (`git status --porcelain` empty).

| Probe | Measured |
|---|---|
| `python -m pytest -q` | **600 passed**, 0 failed, 0 skipped, 0 xfailed, exit **0** (276.03 s) |
| `scripts/verify_*.py`, each run individually | **11 scripts, 11 exit 0** — `audit_append_only` (post-commit mode), `audit_findings`, `cash_universe_coverage`, `historical_snapshot`, `phase2a_containment_and_trials`, `phase2b_significance`, `phase2b5_storage`, `phase2c_walkforward`, `phase2d_verdicts`, `seq10_certificate`, `wave1_thin_slice` |
| gate verdict line | `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| source-tree row | `Source tree d67eb8fab2855854… is already recorded; not appending a duplicate row` |
| registry | `N = 11`, `N_eval = 6`; no `TRIAL-PHASE3B2-MEANREV-012` row |
| criteria | `1.1.16`, `CRIT-FPR-V1-535e47f5…` |

The commit message's "600 passed, 0 skipped, 0 xfailed" reproduces exactly. Its "10 of 10 verifiers" does not match a bare glob of 11 — the natural reading is that `verify_audit_append_only.py` is the gate and ten is the count beside it, and both readings are consistent with the tree, so this is recorded as **ambiguous, not wrong**.

### 100.2 Item 1 — the pre-registration preceded the code, and it did not move (clean)

`git merge-base --is-ancestor f2133ef 7c0957e` → exit 0. `git diff f2133ef..7c0957e -- configs/trial_012_candidate.yaml` → **empty**, so the spec executed is the spec committed before the code, which is what §8.2 asks. A degrees-of-freedom grep (`e.g.`, `or`, `TBD`, `approximately`, `~`, `around`, `about`, `roughly`) returns two hits, both inside the `falsifier` prose at lines 129-130 and neither a parameter. No run artifact other than `seq12_data_qa.json` exists at `7c0957e` (`git ls-tree`), so no result was produced before its QA. **Clean.**

### 100.3 Item 2 — protected paths untouched (clean)

`7c0957e` touches no path under `reports/audit/**`, no `AGENTS.md`, no `configs/go_no_go_criteria.yaml`, no `data/trials/**`, and no fold or holdout path. `CURRENT_STAGE_OF_WORK.md` gains **115 lines and removes 0** in both `7c0957e` and `3f7691f`, and 0 across `f2133ef..7c0957e` — append-only confirmed by line diff, not by intent. **Clean.**

### 100.4 Item 3 — reproduced from raw Bronze, and the reason for two of the five stops is refuted (N-196)

Reproduced independently of the artifact, from `data/raw/**/cmDDMONYYYYbhav.csv.zip`. For all eight rows `PREVCLOSE(T) == CLOSE(T-1)`, so the exchange did not rebase its own reference price on any of them; the level change is in the traded series. A control over 362 known SPLIT/BONUS ex-dates shows that marker is not a rebasing detector — only **3 of 362** have `PREVCLOSE != CLOSE(T-1)`, and MARATHON's 10:5 split (ex 2018-04-05) prints `2018-04-04 C=426.3` → `2018-04-05 PREVC=426.3, O=220.05`, i.e. an unadjusted `PREVCLOSE`. That refuted hypothesis is recorded so the next round does not re-derive it.

What the Bronze payloads do carry is decisive for two rows. The QA's docstring states the exclusion explicitly — *"a dividend that cannot reprice anything"* — and `PRICE_SIDE_KINDS = {SPLIT, BONUS, CONSOLIDATION}`. **An ex-dividend session reprices the stock by the dividend, permanently.** Measured against the reference row on the exact ex-date:

| Instrument | Ex-date | Prev close | Dividend (Bronze + reference) | Predicted close | Actual close | \|close − (prev − div)\| / prev | Dividend ÷ opening gap |
|---|---|---|---|---|---|---|---|
| HEUBACHIND `INE492A01029` | 2020-07-16 | 563.30 | **₹140** special | **423.30** | **423.55** | **0.0444 %** | **87.34 %** |
| VARDHACRLC `INE116G01013` | 2021-10-28 | 72.35 | **₹25** interim | 47.35 | 56.60 | 12.79 % | **117.10 %** |

HEUBACHIND is not a coincidence: a ₹140 dividend on a ₹563.30 close predicts 423.30 and the session closed 423.55. The "opening gap of −28.46 % with no price-side corporate action attested" is an attested cash dividend, and under §13.2 an ex-dividend gap is a cash inflow, never a loss. VARDHACRLC is weaker evidence — the dividend is 117 % of the gap but the close does not land on the predicted level — and is registered as corroborating, not decisive.

So the count is **5 → 3**: ASTRAL (`INE006I01046`, 2021-03-18), DTIL (`INE341R01014`, 2021-08-05) and MANINFRA (`INE949H01023`, 2021-11-17) carry no record on that date in Bronze or in the reference table, and ASTRAL carries **no Bronze corporate-action row at all** across the whole archive. Those three are genuinely unattested; the fail-closed §6.3 response to them is correct, and **the STOP therefore stands**. What does not stand is the reason and the number: a reader of `seq12_data_qa.json` is told five price levels are fabricated when two of them are explained to 0.04 % by a dividend the same table contains. This is **N-196**, HIGH, OPEN.

### 100.5 Item 4 — the trigger is real, and it is tested on the wrong day (N-197)

The stop's justification is the one the implementer states: *"the trigger is `RSI(2) < 10`, and an opening gap of −22 % to −37 % manufactures that condition."* That reasoning is sound, and it is exactly why the test must be wider than the test that exists. Measured over the corpus, independently of `entry_signals`: the census below applies the same price-side-ratio attestation the QA uses, with a **₹5 previous-close floor** (at a ₹0.05 prev close the 5-paise tick is a 100 % "gap"; the ₹25 Cr ADTV floor excludes every such name anyway), and treats a gap as unattested when neither the opening gap nor the close-to-close move is attested.

| Measurement | Value |
|---|---|
| unattested \|open gap\| ≥ 10 %, either direction, corpus-wide | **6,612** (isin, date) events |
| … on a session where the pre-registered rule fires | **129** |
| … of those, gap ≤ −20 % — the QA's own class | **6** (the artifact publishes 5) |
| … inside the 200-session lookback of at least one signal | **5,387** events |
| signals whose lookback holds ≥ 1 such day | **22,740 of ≈100,310** |
| instruments with ≥ 1 in a lookback | **1,309** |
| distinct (isin, session) lookback cells carrying one | **44,237** |

The scan reproduces a signal set of **100,310** against the artifact's **93,463** — 7.3 % larger, because the scan resolves `EQ` from `data/reference/cash_equity_symbol_intervals.csv` while the runner uses `build_production_security_master()`. The difference is in EQ resolution, not in the feature arithmetic, and it can only make the in-lookback share an over-estimate, so the direction of every number above survives it. It is reported rather than smoothed.

Two things follow. The rule tests a −20 % **close-to-close drop**, so a −10 % to −20 % level step on a signal day is invisible — 129 events pass through a signal session and 6 are counted. And it tests **the signal day only**, so a level step anywhere in the 199 sessions feeding `SMA(200)` or `RSI(2)` is invisible — 5,387 events sit in such a window, and a `SMA(200)` or Wilder `RSI(2)` computed across an unattested level step is the §6.3 violation the QA exists to prevent, one step removed from the day it looks at. The floor is not the defect; the ceiling is 20 % on one day in one direction. **N-197**, HIGH, OPEN.

### 100.6 Item 5 — the wording is honest about what it measured and overstated in what it concluded (N-196, N-197)

The `stop_reason` string reads: *"5 entry-signal day(s) open more than 20 % below the previous close — a change of price level between two sessions, not a session's trading — with no price-side corporate action attested on that date; 5 of them are ratio-shaped"*.

Two of those three clauses are computed and one is not. "No price-side corporate action attested" is true **under the code's definition** and false under the language a reader brings to it, because a ₹140 dividend matching the close to 0.04 % is a corporate action that repriced that session (§100.4). "5 of them are ratio-shaped" is near-tautological: `ratio_shapes` enumerates **271 distinct ratios over [0.0417, 24]**, and a uniformly random target is caught by that enumeration **62.50 %** of the time in `[0.60, 0.90]`, **65.56 %** in `[0.30, 0.60]` and **62.17 %** in `[1.05, 1.60]` — a −20 % move (target 0.80) is *always* ratio-shaped. The implementer's own Limitations note says as much ("A non-empty list means a split or bonus of that shape would print exactly this return, not that one happened"), and the artifact's `ratio_shapes` field is nonetheless the third clause of the verdict sentence. §9.1 asks for verdicts computed from values; this clause is computed and uninformative, which reads to a user as corroboration.

The three surviving rows keep the STOP. The wording is the implementer's to change; the finding is that the reason must be re-derived after N-196, not reworded around.

### 100.7 Item 6 — no regression, and the seam is single-engine but has no client (N-198)

**No regression to seq 10 / seq 11.** `git diff 7c0957e~1 7c0957e -- src/signal_core/features/engine.py` is **purely additive**: three fields (`sma_5`, `sma_200`, `rsi_2`), three `_run_subsegment_indicator` maps, three keyword arguments, two docstring lines. No existing computation is touched, and there is no feature-fingerprint function in `features/engine.py` at all (`grep` for `sha256|hashlib|fingerprint|digest` returns nothing there), so the added fields cannot move a committed digest. The one line that could have changed prior rows, `trial_params["entry_rank_indicator"] = str(strategy.parameters.get(...))` at `scripts/run_phase3b2_walkforward.py:1643`, is byte-identical in effect: `DeliverySwingTrendStrategy` is constructed at line 1208 with `entry_rank_indicator=committed_rank_indicator`, and the committed `canonical_params` of `TRIAL-PHASE3B2-EXPANDED-010` and `-011` both already read `{'entry_rank_indicator': 'mom_63'}`. Feature-layer and registry parity hold; 600 tests pass.

**The seam is single-engine.** `execute_swing_strategy_session(strategy=strategy, ...)` is called from exactly one site (`scripts/run_phase3b2_walkforward.py:1417`), and `swing.py` reaches the rule only through `strategy.generate_signals(...)` at line 400 — no `isinstance` branch, no second fill or cost path. §7.4 and §13.5 hold at the seam.

**But nothing calls it.** `scripts/run_seq12_candidate.py` imports `scripts.run_phase3b2_walkforward as walkforward` for exactly one attribute, `load_go_no_go_criteria()` at line 502. It contains no call to `run_phase3b2_walkforward`, no call to `execute_swing_strategy_session`, and no `DailyTPlus1OrderRunner`. `MeanReversionSwingStrategy` is constructed **nowhere outside `tests/`**. So Step 3 is not "blocked by Step 2" — it does not exist, and the STOP is not wired to any consumer. That is the §14.4 shape in advance: a later round can add execution beside this artifact without its exit status ever being consulted, and nothing would fail. **N-198**, MEDIUM, OPEN.

### 100.8 Item 7 — the fail-closed probes pass (clean)

- Deleting `reports/analysis/s101/seq12_data_qa.json` and running `--check` → `FAIL: no committed QA evidence at …`, exit **1**. Restored; `git status --porcelain` empty.
- The default no-flag path → exit **1**, printing `OVERALL: STOP — …` and `Step 3 is NOT RUN: no session was simulated, no P&L was read, no registry row and no verdict artifact was written.` The refusal is real and it is on the default path.
- Byte reproduction of the artifact is claimed by `--check` and reproduces (exit 0 at `3f7691f`, consistent with the committed sha256).

The probes pass. Their value is bounded by N-198: they prove the artifact refuses, not that anything depends on the refusal.

### 100.9 Item 8 — the exit side is not measured, and one published zero is not a measurement (N-199)

`blocked_by_locked_session` publishes `total: 431` with `no_band_recorded: 431` — **100 %** — and `at_lower_circuit: 0`, `at_upper_circuit: 0`, `banded_but_not_at_a_limit: 0`. The zero is not evidence that no locked session sat at a limit: `data/silver/price_bands` holds **0 files** (`git ls-tree -r --name-only HEAD | grep -c silver/price_bands` → 0), so `master.get_price_band()` returns `None` for every session and the three categorical counters are unreachable by construction. `data/reference/surveillance_intervals.jsonl` is `SYNTHETIC_FIXTURE`. Under §5.3 and §13.2 the lower-circuit freeze is the unbounded exit delay a delivery-swing rule cannot ignore, and it is precisely the case this QA cannot see.

Separately, no field in the artifact mentions exits, holds, positions or round trips: `[k for k in artifact if any(t in k.lower() for t in ('exit','hold','position','round_trip'))]` → **[]**. For an intraday rule an entry-side QA could be sufficient; for a 2-to-21-session hold it is not, and §13.3 puts the cost test on the round trip. **N-199**, HIGH, OPEN.
### 100.10 Item 9 — tag, trailers, and status claims (clean)

`feat-s101-7c0957e` is a lightweight tag resolving to `7c0957e459f7de5abd4870c1b6f70f8741380496`; no `--amend`, no rewrite. No `Co-Authored-By`, "Generated with" or model-identity trailer across `f2133ef^..3f7691f` (§12.7). The §101 status block opens with *"**Not audited.** Nothing below is reviewed by an audit section, so nothing below is signed off, verified or closed by a verdict"*, labels its own table `NOT RUN` where Step 3 did not run, states *"This section states a refusal, not a finding"*, and cites no § because none exists. §11.3 is satisfied: it claims nothing a verdict must grant. **Clean.**

### 100.11 Item 10 — NIFTYBEES is not continuous across 2019-12-19, and the corpus says it is adjusted (N-201)

`INF732E01011` has 424 corpus bars ending 2019-12-19. The corpus stores `2019-12-18 close 1292.54` and `2019-12-19 open 129.2, close 130.20` — ratio **0.100730**, **−89.93 %** — and stamps both bars `adjustment_version: v2.0-attested-split-bonus-backadjust-2018-2023`. `INF204KB14I2` begins 2019-12-20 at 134.95. This is an ISIN transition carrying a 1:10 unit re-denomination, **unadjusted in the corpus**, and `INF732E01011` is in `universe_by_date` on 2019-12-18. The opening gap at the boundary is **−0.900042**.

Two consequences. Decision clause (d) compares Calmar against NIFTYBEES buy-and-hold over `2018-04-02..2023-12-29`; a benchmark series carrying a −89.93 % step inside that window makes whatever it produces meaningless, and clause (d) cannot be evaluated as currently specified. And `reconciliation.ratio_shaped_detail` publishes **0** rows for either ISIN while `ratio_shaped_unattested` is 699 and the threshold is 0.35 — so a −89.93 % close-to-close move in an in-universe instrument is absent from the reconciliation's own detail. That makes the 699 not a census, and the `adjustment_version` stamp on those two bars a claim the data does not support.

### 100.12 Item 3, residual — the "no record" evidence covers two-thirds of the corpus (N-200)

The attestation test's negative claim is only as strong as the archive behind it. Measured: the Bronze corporate-action payloads cover **2,200 distinct ISINs** against **2,735** corpus instruments, so **910 corpus ISINs (33.3 %) have no Bronze corporate-action record of any kind**. The reference table holds **5,288** `(isin, ex_date)` keys against Bronze's **13,349**; among corpus ISINs, **6,886** Bronze keys have no reference row, of which **102** carry a price-side subject — sample after sample a **rights issue** (`Rights 49:100 @ Premium Rs 9/-`, `Rights 87:38 @ Premium Of Rs 2.50 Per Share`, …), and the reference table carries only **4** `RIGHTS` rows in 5,371. Rights repricing is a §5.4 adjustment like any other.

So `UNATTESTED_NO_RECORD` conflates "no corporate action occurred" with "the archive we hold does not cover this instrument on this date", and the reference table is demonstrably incomplete on the class that matters most after N-196 — cash and rights adjustments that move price without a share ratio. ASTRAL, DTIL and MANINFRA stay unattested, so the STOP survives this too; the finding is that the evidence class is weaker than the verdict sentence implies. **N-200**, HIGH, OPEN.

### 100.13 One interaction is unpinned (N-202)

`MeanReversionSwingStrategy.generate_signals` emits the sell for a name whose `close > SMA(5)` and then `continue`s (`src/signal_core/strategy/mean_reversion.py:114`), so a name satisfying both the exit and the entry condition on the same session cannot be entered that day. The pre-registration pins `entry_condition` (line 36) and `exit_condition` (lines 38-39) as separate predicates and says nothing about their interaction. That is a degree of freedom the code resolves and the spec does not, in a rule committed as *"a single closed-form mean-reversion rule, executed exactly once"* (§8.1, §2.1). It does not affect this round — nothing executed — but it is unpinned now and will be pinned by whoever runs it. **N-202**, MEDIUM, OPEN.

### 100.14 Findings ledger after this section

| | before §100 | after §100 |
|---|---|---|
| rows / ids | 79 / 47 | **86 / 54** |
| latest per id | 45 CLOSED, 2 OPEN, 1 ACCEPTED | **45 CLOSED, 9 OPEN, 1 ACCEPTED** |
| OPEN ids | `N-150`, `N-195` | `N-150`, `N-195`, **`N-196`…`N-202`** |

### 100.15 Phase verdicts

| Phase (§101 row) | Verdict | Residual |
|---|---|---|
| Pre-registration (`f2133ef`, §8.2) | **PASS** — committed before code, unchanged at `7c0957e`, no alternates, no sweep | N-202: exit/entry interaction unpinned |
| Step 1 implementation (§7.4, §13.5) | **PASS at the seam, NOT WIRED** — one `strategy=` call site, no second fill or cost path, 600 tests green, engine diff additive | N-198: nothing outside `tests/` constructs the rule |
| Step 2 data QA (§6.1, §6.3, §5.4) | **FAIL** — 2 of 5 stops refuted by an attested dividend (N-196); trigger tested on one day in one direction (N-197); evidence class covers 2,200 of 2,735 instruments (N-200); exit side absent (N-199) | the STOP itself stands on 3 genuine rows |
| Step 3 execution | **NOT RUN** — reported as not run, no artifact, no registry row, N/N_eval unchanged | nothing to verify |
| Decision clause (d), Calmar vs NIFTYBEES | **BLOCKED** — benchmark series carries an unadjusted −89.93 % step (N-201) | clause cannot be evaluated as specified |
| Status document (§11.3) | **PASS** — "Not audited" opening, `NOT RUN` rows, no uncited claim | none observed |
| Holdout / 2024 fold | **held** — `2025-01-01..2026-11-11` sealed, 2024 fold untouched | none observed |

### 100.16 Work order (feat-s102), ordered by what it unblocks

1. **Add a cash-adjustment branch to the attestation test and re-derive the count** (N-196). Required: `_classify_drop` treats a `DIVIDEND` or `RIGHTS` row on the exact ex-date as attested when the cash amount reproduces the opening gap or the close within a recorded tolerance, and `seq12_data_qa.json` republishes `unattested_level_steps_feeding_a_signal` from the widened test. The probe that must fail closed: a fixture whose ex-date dividend predicts the close to < 0.5 % must classify as an attested cash adjustment; the HEUBACHIND row must leave the stop list while ASTRAL, DTIL and MANINFRA stay in it. The stop must still trip — a fix that empties the list is a failure, not a pass. Phase: §6.1 / §5.4.
2. **Test the gap over the window, not only the signal day, and in both directions** (N-197). Required: a committed measurement of unattested \|gap\| ≥ 10 % events inside the 200-session lookback of each signal, published beside the existing count, plus a stated policy for a lookback that contains one. The probe: a fixture with a clean signal day and an unattested −15 % step at T−100 must not yield a usable `SMA(200)`, and the artifact must say so. Phase: §6.3.
3. **Make the artifact gate something, or say it gates nothing** (N-198). Required: either the seq-12 execution path exists and refuses to start when the artifact's status is `STOP` (the refusal named in the probe), or §101 states that no code consumes the artifact. Phase: §14.4 / §7.4.
4. **Populate `data/silver/price_bands` or retire the three band counters** (N-199). Required: `at_lower_circuit`, `at_upper_circuit` and `banded_but_not_at_a_limit` report `NOT RUN` while the partition is empty, rather than 0; and the round-trip exit-freeze case is measured before any swing verdict is computed. The probe: an empty band partition must not yield `at_lower_circuit: 0` as a computed value. Phase: §5.3 / §13.2.
5. **Resolve the NIFTYBEES boundary or drop clause (d)** (N-201). Required: either the corpus back-adjusts `INF732E01011` across 2019-12-19 with a committed corporate-action row, or clause (d) names a benchmark that is continuous, with the reason committed. The probe: a benchmark series carrying a > 50 % unattested step inside the evaluation window must be refused by name. Phase: §5.4 / §9.2.
6. **Publish the archive's coverage beside the "no record" verdict** (N-200). Required: the artifact reports how many instruments in the scanned set have no Bronze corporate-action coverage, so `UNATTESTED_NO_RECORD` is read as "no record in a partial archive". Phase: §10.5 / §9.1.
7. **Pin the exit/entry interaction in the pre-registration** (N-202), or record it as an explicit parameter. Phase: §8.1.
8. Carried unchanged: §99.10 items 1 (`N-195`), 2 (verifier inventory — measured again here at 11, all exit 0) and 3, and §96.10 items 5-7.

### 100.17 What would falsify this verdict

- **N-196**: a dividend-aware repricing test under which HEUBACHIND 2020-07-16 does *not* match — a committed source showing the ₹140 on that date is not an ex-date dividend, or a session-level record showing the stock traded at 423 for reasons other than the dividend. Falsified also if a re-derived count that includes dividends still returns five unattested rows.
- **N-197**: a measurement showing that unattested gaps between 10 % and 20 %, or inside lookback windows, are absent or immaterial — for instance a scan restricted to the ₹25 Cr ADTV universe where the in-lookback count collapses to O(1). My scan's signal set is 7.3 % larger than the artifact's, so a scan on the artifact's own EQ resolution that finds materially fewer in-window events would weaken the finding, not its direction.
- **N-198**: a code path anywhere in the tree that reads `seq12_data_qa.json` or invokes the seq-12 rule before executing. `grep -rn 'seq12_data_qa' --include=*.py` returning a non-test consumer would falsify it.
- **N-199**: a non-empty `data/silver/price_bands` partition for 2018-2023, or a session where `get_price_band` returns a band — either would make `at_lower_circuit: 0` a measurement.
- **N-200**: a census showing the 910 uncovered ISINs are all non-tradeable, or that no unattested stop row belongs to one of them. ASTRAL, DTIL and MANINFRA are the three that matter, and none of them is covered.
- **N-201**: a corpus in which `INF732E01011`'s 2019-12-19 bar is back-adjusted, or a committed corporate-action row attesting the 1:10 transition — which is what the `adjustment_version` stamp already asserts and the data does not show.
- **The STOP verdict itself**: a session-simulation run whose P&L is unchanged when ASTRAL, DTIL and MANINFRA are excluded. That would make the three genuine rows immaterial rather than disqualifying, and the stop over-cautious rather than wrong.
## §101 — Audit of `46a99ec` (tag `feat-s102-46a99ec`): the cash test is stated before the count and the count is 4, the window census reproduces to the digit, and the benchmark refusal fires — while the corpus boundary, the band partition and one committed digest stay open

**Scope.** `20bb6ff` states the cash-adjustment test and its 0.5 % tolerance and re-derives nothing; `11a366b` names a continuous benchmark for clause (d) and adds the refusal; `468b2e0` pins the entry/exit interaction; `46a99ec` carries the re-derived artifact (`reports/analysis/s102/seq12_data_qa.json`, 77,387 B), the wider census, the `NOT RUN` band counters, the archive coverage and the consumer scan; `739e64b` appends the green row only. `f2133ef` is an ancestor of all five and of `739e64b`. The tag is lightweight and resolves to `46a99eccb8af5b4ba2ccd6bef003842eaa3ce17f`.

**Verdicts:** **§100.16 item 1 CLOSED** (N-196) · **item 2 CLOSED** (N-197) · **item 3 CLOSED** on the branch the order permits — the artifact now says it gates nothing (N-198) · **item 4 PARTIAL** — counters fixed, population BLOCKED (N-199) · **item 5 PARTIAL** — clause half closed, corpus half untouched (N-201) · **item 6 CLOSED** (N-200) · **item 7 CLOSED** (N-202) · **N-195 CLOSED** (`eea1757`) · **two new findings: N-203** (the comparison artifact's digest is a CRLF working copy's, so `--check` fails on a clean clone) and **N-204** (the QA artifact's corpus digest is the sha256 of a CRLF-mutated gzip stream, not of the file).

### 101.1 Baseline re-measured at `46a99ec`

`739e64b` touches only `data/reference/source_tree_green.json`, which is inside the gate's own excluded set, so the tree measured here is `46a99ec`'s. `git status --porcelain` empty at audit time.

| Probe | Measured |
|---|---|
| `python scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| §11.1 append-only | working tree & index vs HEAD **0 deleted lines**; commits since `a3a40f1` **0 deleted lines** |
| Discovered verifiers | **10, all exit 0** — `verify_audit_findings` 205.92 s, `cash_universe_coverage` 34.76 s, `historical_snapshot` 5.29 s, `phase2a_containment_and_trials` 1.15 s, `phase2b5_storage` 2.69 s, `phase2b_significance` 0.82 s, `phase2c_walkforward` 2.68 s, `phase2d_verdicts` 3.91 s, `seq10_certificate` 1.00 s, `wave1_thin_slice` 4.27 s. `verify_audit_append_only.py` is the 11th file on disk and the gate itself (exit 0) |
| Suite | **611 passed, 0 skipped, 0 xfailed**, exit 0, 241.16 s in one invocation |
| Manifest / tags | 1,009 current artifacts match byte count and sha256, 962 superseded; every commit-bearing tag verified |
| Source tree | `255bc803f7a387be…` — `already recorded; not appending a duplicate row`. The green row records `gate_sha 46a99ec`, 611, and ten verifier exits 0 |
| Criteria / pins | `1.1.16`, `CRIT-FPR-V1-535e47f5…`; `probe_seq10_candidate.py` **CERTIFIED**, `N = 11`, `N_eval = 6`, baseline `f5fe3af5…`, sealed-era window refused |
| Registry | **11** trials / **6** evaluations, read from `data/trials/` — unchanged |
| Ledger before this section | 86 rows / 54 ids; 9 OPEN (`N-150`, `N-195`…`N-202`); 54 probes, all exit 0 |
| Corpus | 75,390,706 B, raw sha256 `ea0b65a3…`, 1,425 sessions, 2,735 instruments, `DATA-CTNT-V2-cb4832c0…` |
| Trailers | no `Co-Authored-By`, "Generated with" or model-identity line in `84643ae..739e64b` (§12.7) |

### 101.2 Item 1 — the process holds, with one citation missing (clean, one note)

`git merge-base --is-ancestor f2133ef <c>` exits 0 for `20bb6ff`, `11a366b`, `468b2e0`, `46a99ec` and `739e64b`; the parents chain `84643ae → 20bb6ff → 11a366b → 468b2e0 → 46a99ec → 739e64b`, so both amendments are new commits, not rewrites, and both precede the only commit that writes a result.

`468b2e0` cites `f2133ef` by SHA in its message and pins `entry_exit_interaction` in the spec. `11a366b` cites **§100.16 item 5** and says "before any execution", but it does **not** name `f2133ef` — a small deviation from the order's wording, and not a process defect: the amendment is a commit after the pre-registration and before `46a99ec`, which is what the citation is for. Recorded, not raised.

The four implementer commits touch `scripts/probe_audit_findings.py`, `scripts/run_seq12_candidate.py`, `scripts/compare_seq10_baselines.py`, `tests/unit/test_phase3b2_seq12_data_qa.py`, `tests/unit/test_phase3b2_audit_s102_items.py`, `configs/trial_012_candidate.yaml`, `src/signal_core/strategy/mean_reversion.py`, the `s102` artifact and `CURRENT_STAGE_OF_WORK.md`. Measured by `git diff --name-status 84643ae..46a99ec`: no path under `configs/go_no_go_criteria.yaml`, `reports/audit/**`, `AGENTS.md`, `data/trials/**`, `configs/partition_spec.yaml`, the 2024 fold or the holdout. No P&L exists: the artifact's `mode` is `COUNTS_AND_LISTS_ONLY_NO_PNL`, there is no seq-12 verdict artifact, and the registry is unchanged at 11/6. **`reports/analysis/s101/seq12_data_qa.json` is unedited** — its bytes are the §101 round's record, restated by hash in the new artifact.

### 101.3 Item 2 (N-196) — the test preceded the count, the count is 4, and the stop census is invariant across a 0.25 %–2 % sweep

`20bb6ff` (12:08:43) commits the docstring, `CASH_ADJUSTMENT_KINDS`, `CASH_ADJUSTMENT_TOLERANCE = 0.005`, `_cash_adjustment_prediction`, `_cash_adjustment_test`, the `_classify_drop` cash branch and the test file, and writes no artifact. `46a99ec` (12:38:19) writes the artifact. The count was therefore re-derived under a test that existed first.

I recomputed the census from the corpus and the committed action table with my own partition, my own ratio test, my own dividend/rights arithmetic and a `tolerance` parameter — no `run_seq12_candidate` function called. Corpus-wide, 6,736 consecutive-session steps open 10 % or more away from the previous close (₹5 floor, inside a continuous subsegment); the committed test attests **5** and publishes **6,731** unattested — the artifact's number exactly.

| Tolerance | Attested | Unattested corpus-wide | Instruments with one | Stop census (unattested level steps) | Rows first admitted at this tolerance |
|---|---|---|---|---|---|
| 0.25 % | 2 | 6,734 | 1,668 | **4** | HEUBACHIND 0.0444 %, AURUM 0.0558 % |
| **0.5 % (committed)** | **5** | **6,731** | **1,668** | **4** | MANAKSIA 0.3021 %, HAL 0.3716 %, UFO 0.3929 % |
| 1 % | 8 | 6,728 | 1,667 | **4** | PFC 0.979 %, PGHL 0.857 %, POLYPLEX 0.966 % |
| 2 % | 10 | 6,726 | 1,667 | **4** | BANCOINDIA 1.971 %, NLCINDIA 1.975 % |

**No false attestation at any of the four tolerances.** Each attested row's record is a cash amount that is 9.5 %–98.8 % of the previous close and whose predicted level the session trades to within the tolerance: AURUM `INE898S01029` 2020-12-23 pays ₹974.00 on a ₹985.65 close and opens at ₹12.20 against a predicted ₹11.65 (0.0558 %); MANAKSIA pays ₹7.50 on ₹49.65; HAL ₹33.25 on ₹282.575; UFO ₹15.00 on ₹127.25, where the *open* is the leg that reproduces (0.3929 %) and the close falls a further 8.5 % during the session — which is the level-step/trading distinction the test is built on; POLYPLEX ₹100 on ₹911.20. What widening buys is not a false explanation but a **looser one**: at 2 % the two last rows are admitted with 1.97 % of the previous close unexplained, i.e. an ordinary market gap of that size is absorbed into the corporate-action story. The committed 0.5 % is the last tolerance at which every attestation is a level reproduction to a few tenths of a percent, and the stop count does not move at all.

**The four rows, re-derived independently:**

| ISIN | Session | Previous close | Opening gap | Move | Record on the date | Predicted level | Residual (close / open) | Disposition |
|---|---|---|---|---|---|---|---|---|
| `INE006I01046` ASTRAL | 2021-03-18 | 300.95 | −29.72 % | −30.11 % | none | — | — | `UNATTESTED_NO_RECORD` |
| `INE341R01014` DTIL | 2021-08-05 | 187.20 | −36.68 % | −33.48 % | none | — | — | `UNATTESTED_NO_RECORD` |
| `INE949H01023` MANINFRA | 2021-11-17 | 66.10 | −28.02 % | −22.33 % | none | — | — | `UNATTESTED_NO_RECORD` |
| `INE116G01013` VARDHACRLC | 2021-10-28 | 72.35 | −29.51 % | −21.77 % | ₹25.00 interim | 47.35 | 12.79 % / 5.04 % | `UNATTESTED_CASH_MISMATCH` |

So **4 is right**, and **I agree with the implementer's disagreement with §100.4**, on §100.4's own numbers: the test §100.16 item 1 ordered is a *level reproduction* at 0.5 % of the previous close. VARDHACRLC's ₹25 is 117 % of the opening gap, but a dividend-to-gap ratio is not a level reproduction, and the session closes 12.79 % away from the level that dividend predicts. §100.4 called the row "corroborating, not decisive" and then counted 3; those two statements cannot both hold under the test the work order named. The implementer's 4 is the count the committed test produces, and it was published with the residuals rather than disposed of. **§100.4's "5 → 3" was wrong; the correction is appended here and §100 is not edited** (§10.1).

**RIGHTS.** The code does **not** apply a cash-amount test to a rights record: `_cash_adjustment_prediction` returns `(prev·denominator + premium·numerator)/(denominator + numerator)`, the theoretical ex-rights price, which is the valid repricing — a rights issue's ex-date move depends on the ratio and the issue price, so `prev − premium` would be wrong, and the implementer did not use it. The prose around it ("a cash record … whose cash amount reproduces the session's close") conflates the two, but the arithmetic does not. The branch is **unexercised on this corpus**: the reference table holds 4 `RIGHTS` rows and none sits on a ≥10 % step, so 0 of the 6,736 candidates is attested by TERP at any tolerance. All four carry `UNATTESTED_NSE_CML_…` circular refs, and the premium is parsed out of a free-text `description`, so the branch's first real use will attest a price level against an unattested record with a regex-extracted number. Named as a residual; it changes nothing this round.

### 101.4 Item 3 (N-201, clause half) — the definition moved, the window did not, and the gate got stricter

The `configs/trial_012_candidate.yaml` diff adds a `benchmark` block under clause (d) naming `scripts/compare_seq10_baselines.py:buy_and_hold_arm`, the within-ISIN construction, the two unmeasured sessions and the refusal, and moves no clause id, threshold, window, fold or cost field. Under a Ruling, that is a **definition** change and permitted; I checked it does not smuggle a threshold or a window:

- **What is measured** changes: the benchmark is a chained within-ISIN daily return series, 1,422 measured returns across 2018-04-02..2023-12-29, not a price series spliced at 2019-12-19.
- **The window does not change.** Both arms span the same calendar, 2018-04-02..2023-12-29. The strategy arm measures 1,424 returns; the benchmark measures **1,422** — the two dropped sessions are the only asymmetry, and they are named in the clause.
- **The gate gets stricter, not looser.** Chaining the boundary would leave the benchmark at ₹225,888 from ₹1,000,000 (−77.4 %) with a ≥89.93 % drawdown, i.e. a negative Calmar that any strategy beats. Excluding it makes the benchmark ₹2,242,471 (+124.25 %) with a 0.3634 drawdown — the harder comparator.
- **The two dropped sessions carry real return.** `INF732E01011` 2019-12-19 opens at 129.20 against a 1,292.54 close: the implied unit ratio is 0.099958, so the *economic* return on the level-break session is **−0.042 %**, not −89.93 %. And 2019-12-19 closes 130.20 while `INF204KB14I2` closes 130.34 on 2019-12-20 — the same unit, so that session's **+0.108 %** return is comparable and is also dropped. Together the benchmark is understated by ≈0.065 %. Immaterial, measurable, and now named rather than implied.
- **Strategy window still equals benchmark window** in calendar terms; it does **not** equal it in measured-return count (1,424 vs 1,422). That asymmetry is the residual, not a moved goalpost.

**Refusal, fed a retained step of its own.** `refuse_unattested_level_break([("2020-01-02", −0.60)], 0.5)` raises `SystemExit` naming the session and N-201. The arm itself: with its drop in place, a 4-session fixture with a −60 % step measures 2 returns and records `2020-01-02` as unmeasured; with `LEVEL_BREAK_THRESHOLD` raised to 2 so the drop stops firing, `buy_and_hold_arm` **refuses by name** ("a one-session step of -0.6 at 2020-01-02"). Both thresholds are `0.5`, so the refusal is unreachable while the drop works — it is a belt for exactly the regression it exists to catch, and it fires.

**The corpus half is untouched, and no fingerprint moved.** `INF732E01011` still carries 2019-12-18 close 1292.54 against 2019-12-19 open 129.2 / close 130.20 (ratio 0.100731), both bars still stamped `v2.0-attested-split-bonus-backadjust-2018-2023`, and `reconciliation.ratio_shaped_detail` still publishes 0 rows for either ISIN while 699 ratio-shaped moves are unexposed. Corpus bytes and raw sha are unchanged (`ea0b65a3…`, 75,390,706 B), as are `DATA-CTNT-V2-cb4832c0…`, `CRIT-FPR-V1-535e47f5…` and the manifest pin. `git diff f2133ef..46a99ec -- reports/verdicts data/reference` is empty.

**The +124 % figure traced.** `reports/analysis/s100/seq10_baseline_comparison.json` publishes `niftybees_buy_hold.final_equity 2242471.2967…` with `sessions 1422` and `unmeasured_sessions [2019-12-19 (level break), 2019-12-20 (ISIN transition)]`; entry ISIN `INF732E01011`, exit ISIN `INF204KB14I2`. It is the compounded product of 1,422 within-ISIN daily returns starting from ₹1,000,000 — a series that *spans* the boundary with the boundary's two sessions removed, not a splice across it. `compare_seq10_baselines.py --check` exits 0 **in the primary checkout**; on a clean clone it does not (§101.11, N-203).

### 101.5 Item 4 (N-197) — every published count reproduces from my own code, and the 200-row list is a nine-instrument prefix

| Measurement | Artifact | Mine, independently |
|---|---|---|
| entry signals (EQ, universe, `close > SMA(200)`, `RSI(2) < 10`) | 93,463 | **93,463** |
| unattested ≥10 % steps, corpus-wide (both directions) | 6,731 | **6,731** |
| … on a session where the rule fires | 128 | **128** |
| instruments with at least one | 1,668 | **1,668** |
| signals with one in their own 200-session window | 21,276 | **21,276** |
| usable entry signals | 72,187 | **72,187** |

My indicators were first checked against the library on all 2,578,060 bars (0 SMA mismatches, 0 RSI mismatches), then the counts were produced by my own segment partition and my own step classifier. One number explains the first attempt's 93,525: the runner's signal loop skips any session with `position + 1 >= len(sessions)`, so the **62 signals on the final session, 2023-12-29, are excluded** and never published. Excluding them is right for an *executable* signal (there is no T+1 open to fill at, §7.1) and the count is that of executable signals — but the artifact calls the field `entry_signals` and publishes no count of the 62. Named as a residual, not a finding: the exclusion is correct, the label is incomplete.

**Forty published detail rows, 64 step entries, checked against the corpus bars: 0 problems.** Every step is in the same continuous subsegment as its signal, at an offset of 0–199 sessions, opens at least 10 % away from the previous close, and its published 4-dp `opening_gap` equals my recomputation. But the 200-row list covers **9 distinct ISINs** (`IN9155A01020` … `INE008A01015`) of the **1,668** instruments that carry an event: it is a prefix in corpus insertion order, not a sample. So the list can hide an instrument-specific bias perfectly — a defect in the classifier for any of the other 1,659 instruments leaves the 200 rows clean, and probe N-197 checks the first 25 rows, which are drawn from roughly the same nine. The counts are complete; the evidence for them is one half of one percent of the affected instruments.

### 101.6 Item 5 — the consumer scan, the bands and the coverage

**N-198, consumer scan.** My own scan of `scripts/*.py` and `src/**/*.py` for the artifact's name returns the producer and the probe, nothing else; `gated_by.consumers` is `[]`, `gates_execution` is `false`, and the statement says the STOP is a record of a refusal, not a gate. I created `scripts/_audit_tmp_consumer.py` containing the artifact path: `probe N-198` exits 1 naming it, and removing it restores exit 0. No code outside `tests/` constructs `MeanReversionSwingStrategy`. The work order permitted exactly this branch ("or §101 states that no code consumes the artifact"), so the item is met; the STOP still gates nothing, and the residual is that a future execution path must be made to read it.

**N-199, band counters.** `data/silver/price_bands` is an empty directory, 0 files tracked, `data/raw/price_bands` does not exist, and `data/reference/surveillance_intervals.jsonl` is still `SYNTHETIC_FIXTURE`. The three categorical counters publish `"NOT RUN"` with `price_band_partition: {files: 0, populated: false}`, and `not_run.exit_freeze_round_trip` names the archive the measurement needs. No band datum is synthesised anywhere: the only writers of the partition are `ingest_daily_price_bands` (raw→silver) and no raw payload exists to promote. `band_counter(0, False) == "NOT RUN"` and `band_counter(7, False) == "NOT RUN"`, both tested. **PARTIAL**: the counters are a property of the reader no longer, but the population half is BLOCKED on a sourced per-session NSE band archive, and the exit-freeze round trip — the case §13.2 says a 2-to-21-session hold cannot ignore — remains **NOT RUN**.

**N-200, coverage.** Recomputed from the 23 Bronze payloads: 13,568 rows, **2,200** distinct ISINs, **2,735** scanned, **910 (33.3 %)** with no record, and the three uncovered stop rows are ASTRAL, DTIL and MANINFRA. CLOSED as ordered. Resident residual: coverage is counted per **ISIN**, not per `(ISIN, date)`, so VARDHACRLC counts as "covered" on the strength of seven rows none of which is near 2021-10-28, and the reference table still carries only 4 `RIGHTS` rows against the 102 unreferenced price-side Bronze keys §100.12 measured. `UNATTESTED_NO_RECORD` now means "no record in this archive" for the 910; for the other 1,825 it still means "no record on this date in an archive that mentions the instrument".

### 101.7 Item 6 — probe ownership: every rewritten probe refuses a tamper, but four of them recompute with the producer's own functions

Twelve attacks, each applied to a tracked file, each restored byte-identically, tree clean after every one. A refusal is exit 1.

| Tamper | Probe | Result |
|---|---|---|
| artifact: `unattested_level_steps_feeding_a_signal` 4→3 | N-196 | **FAIL** — "publishes 3 … the corpus recomputes 4" |
| source: `CASH_ADJUSTMENT_TOLERANCE` 0.005→0.5 | N-196 | **FAIL** — "the tolerance is 0.5, not the 0.5 % the test states" |
| artifact: `signals_with_an_unattested_level_step_in_lookback` 21276→21275 | N-197 | **FAIL** — "the usable set does not subtract the published window count" |
| source: `LOOKBACK_SESSIONS` 200→20 | N-197 | **FAIL** — the T−100 fixture step leaves the window |
| artifact: `gates_execution` false→true | N-198 | **FAIL** |
| source: a committed consumer exists | N-198 | **FAIL** — names `scripts/_audit_tmp_consumer.py` |
| artifact: `at_lower_circuit` `"NOT RUN"`→0 | N-199 | **FAIL** — "an empty partition makes that zero a property of the reader" |
| source: `band_counter` always returns a value | N-199 **unit test** | **FAIL** — the probe reads only the artifact and does not see it |
| artifact: `bronze_distinct_isins` 2200→2199 | N-200 | **FAIL** |
| source: only the first Bronze payload | N-200 | **FAIL** — "the archive holds 156" |
| config: `entry_exit_interaction` removed | N-202 | **FAIL** |
| source: exit branch never fires | N-202 | **FAIL** — the both-true session emits `['BUY']` |
| corpus: `INF732E01011` 2019-12-19 repaired to the same unit (temp tree) | N-201 | **FAIL** — "the corpus ratio … is now 1.0073189224" |

**N-201 has no artifact to tamper** — its probe reads the corpus and the reconciliation, so the "artifact half" of the order is vacuous for it, and the attack that can fail it is a repaired corpus. That was run against a copy outside the repository with `REPO_ROOT` redirected, and it refuses.

**Registry inventory:** 66 function definitions, **0 duplicate definitions**, 54 registered probes, **0** mapping to an undefined function, **0** with no assertion, **0** consisting only of `pass`, **0** unregistered `probe_*` functions, and every OPEN finding has a probe. `--list` ends at `N-202` on this tree. So the specific failure the order names — duplicate definitions, dead probes, probes that assert nothing — is not present.

**What is present is circularity.** N-196, N-197, N-198 and N-200 "recompute" by importing `_classify_drop`, `InstrumentSeries`, `artifact_consumers` and `corporate_action_archive_coverage` from the producer. They therefore catch artifact drift and a regression in the *call path*, which is what their tamper results show, but they cannot detect a wrong classifier: probe and producer would agree on the same error. The only independent evidence for the census is a recomputation that writes its own arithmetic — §101.3 and §101.5 above. This is not a defect the order asked about, but it bounds what "54 probes pass" certifies, and it is why N-199's producer tamper is invisible to its probe (the unit test catches it) and N-201's probe is the only one that measures the corpus rather than the artifact.

**N-195, verified and closed.** `CURRENT_STAGE_OF_WORK.md:2535` publishes `1.058319814…` and `:2536` publishes `1.062288461…`, which are the artifact's `closed_only_profit_factor` and `liquidated_profit_factor` for its 781 closed round trips; neither `1.1178…` nor `1.1773…` remains in the row, `grep` finds no committed artifact producing them, and `probe N-195` exits 0. The fixing commit is **`eea1757`** (§99.10 item 1); `46a99ec` also appears in a `git log -S` because the §102 log quotes the digits. **CLOSED at §101.**

### 101.8 Item 7 — a clean clone reproduces the new artifact and the certificates, and fails the old comparison

Clone of `main` at `739e64b` into a fresh directory outside the repository, `core.autocrlf=true`, `.gitattributes` in force (`*.json text eol=lf`, `*.json.gz -text`):

| Check | Primary checkout | Clean clone |
|---|---|---|
| `run_seq12_candidate.py --check` | exit 0 | **exit 0** — "reproduces the committed bytes (QA status STOP)" |
| `compare_seq10_baselines.py --check` | exit 0 | **exit 1** — "the recomputed comparison is not the committed one" |
| `probe_seq10_candidate.py` | — | **exit 0 — CERTIFIED**, N=11, N_eval=6, pin agrees, sealed-era window refused |
| `python -m pytest` | 611 passed | — (not re-run there; the clone is the same commit) |

The clone's recomputation differs from the committed artifact in **one field**:

```
- "seq10_artifact_sha256": "4a729dbca70e5cb4071804119e701900ed8f6d6824acb1d70163d3dfc01a980b",
+ "seq10_artifact_sha256": "75571da3ebff56531addc6afdecdac6f05cf5a0799327a3ac85a97177ae067ae",
```

Measured cause: the trial_010 verdict is 498,216 B / LF in the blob and 512,882 B / **14,666 CRLF** in the primary working copy. `sha256(blob)` is `75571da3…`; `sha256(blob with LF re-rendered as CRLF)` is **`4a729dbc…`** — exactly the committed field. `compare_seq10_baselines.py` hashes the working copy with raw `read_bytes()` and no normalisation, so the digest it publishes is a digest of *the author's line endings*, and `--check` can never pass on a checkout that stores the blob's own LF. The new `seq12_data_qa.json` is CRLF in the primary (3,368) and LF in the blob, and `--check` passes in both — because `_render` is compared through universal-newline `read_text` — so the §102 artifact is clone-stable and this is a §100 artifact's problem, surfaced by the check the order asked for. **N-203**, MEDIUM.

**seq 10 / seq 11 byte reproduction.** `probe_seq10_candidate.py` certifies both in the clone; `git diff f2133ef..46a99ec -- reports/verdicts reports/analysis/s94` is empty; the corpus and criteria digests are unchanged. The certificate's three stored fingerprints (`9ee0a88c…`) still reconcile through the §98 pin-only restatements, and the seq-11 evaluation row is untouched.

### 101.9 A second digest that is not the file's — N-204

The new artifact publishes `corpus.sha256 = 0fdc728a81acbb39…`. That is **not** the corpus file's sha256. Measured: the file is 75,390,706 B with raw sha256 **`ea0b65a3…`** — the value the manifest and `reports/analysis/s100/seq10_baseline_comparison.json` publish — and the gzip stream happens to contain **1,089** `0D 0A` byte pairs. `run_seq12_candidate._digest` does `read_bytes().replace(b"\r\n", b"\n")` on every path it is given; applied to a `.gz` it hashes a **mutated stream**, and `sha256(raw.replace(b"\r\n", b"\n"))` is exactly `0fdc728a…`. So the artifact carries a deterministic digest that no reader can reproduce from the file, the manifest and the artifact disagree about the same 75 MB, and the CRLF normalisation that makes a text digest clone-stable is incoherent for a binary one (`.gitattributes` already marks `*.json.gz -text` for precisely this reason). Nothing in the data is wrong; the provenance field is. **N-204**, MEDIUM.

### 101.10 Findings ledger after this section

| | before §101 | after §101 |
|---|---|---|
| rows / ids | 86 / 54 | **94 / 56** |
| latest per id | 45 CLOSED, 9 OPEN, 1 ACCEPTED | **50 CLOSED**, **5 OPEN**, 1 ACCEPTED |
| OPEN ids | `N-150`, `N-195`…`N-202` | **`N-150`, `N-199`, `N-201`, `N-203`, `N-204`** |

N-195, N-196, N-197, N-198, N-200 and N-202 gain `CLOSED` rows with `closed_in_section: 101` and the measurement that decided each. N-199 and N-201 stay `OPEN` — their closure is PARTIAL and the ledger has no PARTIAL state; a repeated `OPEN` row would be a duplicate (N-157), so the partial measurement lives here rather than in a row that would misreport it. N-203 and N-204 are new, with executable probes added in this commit that pass while the defects are live (§96's convention). No finding is deleted or re-scoped.

### 101.11 Phase verdicts

| Phase (§102's row in `CURRENT_STAGE_OF_WORK.md`) | Verdict | Residual |
|---|---|---|
| Pre-registration amendments (§8.1) | **PASS** — two new commits after `f2133ef`, before any result; N-202 cites the SHA, the clause-(d) amendment cites only §100.16 item 5 | the clause-(d) commit names the work-order item, not the parent SHA |
| Step 2 data QA, cash attestation (§6.1, §5.4) | **CLOSED** — test committed first, count 5→4, HEUBACHIND attested to 0.0444 %, the three no-record rows kept, stop still trips, no false attestation at 0.25–2 % | the RIGHTS/TERP branch is unexercised and prose-parsed; the corpus-wide count is tolerance-sensitive (6,734→6,726) |
| Step 2 data QA, window (§6.3) | **CLOSED** — 128 / 21,276 of 93,463 / 72,187 reproduced independently; policy published; probe refuses a 20-session window | the detail list is a 9-instrument prefix of 1,668; 62 final-session signals are excluded and unpublished |
| Artifact consumer (§14.4, §7.4) | **CLOSED as ordered** — the artifact states it gates nothing and the statement is the scan; a new consumer fails the probe | the STOP still gates no execution path |
| Circuit freeze / band counters (§5.3, §13.2) | **PARTIAL** — three counters are `NOT RUN` with the empty partition named; nothing synthesised | **population BLOCKED**, exit-freeze round trip **NOT RUN** |
| Benchmark continuity, clause (d) (§5.4, §9.2) | **PARTIAL** — construction named before execution, refusal fires on a retained −60 % step, window unmoved, +124.25 % traced | **corpus half open**: bar unadjusted, stamp false, `ratio_shaped_detail` still not a census; clone digest fails (N-203) |
| Archive coverage (§10.5, §9.1) | **CLOSED** — 910 of 2,735 published beside the verdict, the three uncovered stop rows named | coverage is per-ISIN, not per-date |
| Status document (§11.3) | **PASS** — "Not audited" opening, `NOT RUN` where nothing ran, no signed-off/verified/closed claim without a verdict, registry and holdout stated correctly | the §102 log's "reproduces byte for byte" is true only of the author's checkout (N-203) |
| Seq 10 / seq 11 / criteria / fold / holdout | **held** — `CERTIFIED`, N=11 / N_eval=6, `1.1.16` / `535e47f5…`, corpus `ea0b65a3…`, 2024 fold untouched, holdout `2025-01-01..2026-11-11` unread | `1.1.16` still labels three criteria sets (§98.6) |

### 101.12 Work order (feat-s103), ordered by what it unblocks

1. **N-203 — a committed digest must be the stored bytes' digest.** `seq10_artifact_sha256` is the sha256 of a CRLF rendering, so `compare_seq10_baselines.py --check` exits 1 on every clone that stores LF. Required: hash the LF-normalised bytes (or the blob), regenerate `reports/analysis/s100/seq10_baseline_comparison.json`, and put the check on a discovery path so a clone-failing comparison fails the gate instead of passing silently. The probe that must fail closed is a new one asserting the committed digest equals `sha256(LF bytes)` and refusing the CRLF rendering; `python scripts/compare_seq10_baselines.py --check` must exit 0 in a clone. Phase: §9.1 / §12.3.
2. **N-204 — one dataset, one fingerprint.** The artifact's `corpus.sha256` hashes a CRLF-mutated gzip stream. Required: publish the raw sha256 (`ea0b65a3…`, the manifest's) for binary payloads, or state the normalisation in the field name, and make the probe compare the field with `sha256(file bytes)`. Phase: §10.5 / §6.5.
3. **N-199 — populate the band partition or retire the counters.** The exit-freeze round trip is **NOT RUN** and no swing verdict may be computed before it is measured. Required: a sourced per-session NSE price-band archive for `2018-04-01..2023-12-31` under `data/raw/price_bands/` with retrieval metadata, promoted one session per partition, and the round-trip exit delay measured; the probe is the existing biconditional. Phase: §5.3 / §13.2 / §13.3.
4. **N-201 — the corpus half.** Either attest the 1:10 across `INF732E01011`→`INF204KB14I2` with a committed corporate-action row and back-adjust, or keep the boundary excluded and mark `reconciliation.ratio_shaped_detail` as not a census in the corpus header. The two dropped sessions carry −0.042 % and +0.108 % of real return; say so where the clause names them, or keep them. The probe is N-201 as written plus the refusal. Phase: §5.4 / §9.2.
5. **Publish the two silent boundaries in the QA artifact.** The 62 signals on 2023-12-29 excluded by the `position + 1` guard, and the 9-instrument reach of the 200-row detail list, are both measured here and neither is published. Required: a field for the excluded final-session signals and one for the distinct-instrument count behind the detail list (or a sampled list), so a reader can see the coverage the counts rest on. Phase: §9.1 / §6.3.
6. **Exercise or retire the RIGHTS branch.** No `RIGHTS` row sits on a ≥10 % step, so the TERP path has never run in anger; its premium is a regex over prose and its four records are `UNATTESTED_`. Required: a sourced rights record with a verified ratio and issue price, or a stated limitation that the branch is unexercised and why its first use is not evidence. Phase: §5.4.
7. Carried unchanged: `N-150`; §99.10 items 2–3 (verifier inventory, criteria fingerprint on the registry surface); §96.10 items 5–7; the §98.5 asymmetry between a restatement's `measurement` and its `replay`.

### 101.13 What would falsify this verdict

- **N-196 / the count of 4**: a tolerance at or below 0.5 % under which VARDHACRLC's ₹25 dividend reproduces the 2021-10-28 close (56.60) or open (51.00) to within the tolerance — measured impossible: 12.79 % and 5.04 %. Or a dividend record for ASTRAL, DTIL or MANINFRA that the archive holds and this scan missed.
- **N-197**: a signal set other than 93,463 under the runner's own EQ resolution and its `position + 1` guard; or a detail row whose gap, window offset or subsegment contradicts the corpus. My counts came from my own indicators and classifier and matched to the digit; a mismatch would mean one of us is wrong and the corpus decides which.
- **N-198**: any committed path outside `tests/` that reads `seq12_data_qa.json` or constructs `MeanReversionSwingStrategy`; the probe and the scan both currently return none.
- **N-199**: a non-empty `data/silver/price_bands`, or a session for which `get_price_band` returns a band — either would make `NOT RUN` wrong and the counters measurable.
- **N-200**: a census showing the 910 uncovered ISINs are non-tradeable, or that no stop row belongs to one. The three that matter are uncovered and named.
- **N-201**: a committed corporate-action row attesting the 1:10 for `INF732E01011`, or a corpus in which the 2019-12-19 bar is back-adjusted — either makes the corpus half closable and the refusal's object disappear. Or a benchmark whose `sessions` equals the strategy's 1,424 after the boundary exclusion; today it is 1,422.
- **N-202**: a config without `entry_exit_interaction`, or a strategy emitting both intents on a both-true session; both attacked and both refused.
- **N-203**: a clone in which `compare_seq10_baselines.py --check` exits 0 with `seq10_artifact_sha256` still `4a729dbc…`. That would mean the digest is not CRLF-dependent, and the field I measured is coincidence; `sha256(LF-rendered CRLF)` reproducing it to 64 hex digits makes that implausible.
- **N-204**: a reader who can reproduce `0fdc728a…` from `sha256(file bytes)` — measured impossible; the mutated-stream hash matches it exactly and the raw hash is `ea0b65a3…`.
- **The overall verdict**: a P&L run on this tree, which would make the STOP's consequences measurable rather than prospective. None exists, and none may be read from the holdout.
## §102 — Audit of `325bab8` (tag `feat-s103-325bab8`): the stored bytes' digest reproduces in a clone and in the writing checkout, the 86 excluded signals and the 9-instrument detail reach recompute to the digit, and the corpus boundary is marked where it is read rather than where §101 ordered it

**Scope.** One code commit, `325bab8` (parent `38d22a6`), 11 paths, +427/−27. It executes §101.12 items 1, 2, 5 and 6, and takes a fifth thing the order did not ask for: an artifact-surface mark for item 4's corpus half. Tag `feat-s103-325bab8` resolves to `325bab853cce023ad7182b3461de62ed08ac9cd6`.

**Verdicts:** **item 1 CLOSED** (N-203) · **item 2 CLOSED** (N-204) · **item 5 CLOSED** · **item 6 CLOSED** on the branch it names (the RIGHTS branch is stated, not exercised) · **item 4 (N-201) OPEN** — the artifact-surface mark is measured true but it is not the corpus header §101.12 item 4 named, and the corpus half is a sealed-surface change this round was not ordered to make · **no new finding**; **one Ruling** (§102.3).

### 102.1 Baseline re-measured at `325bab8`

`--force-full` in a fresh clone of this repository checked out at `325bab8`, `core.autocrlf=true`, working tree clean. A second clone with `core.autocrlf=false` and a forced re-checkout was used for the digest comparisons of §102.4.

| Probe | Measured |
|---|---|
| `python scripts/verify_audit_append_only.py --force-full` | **exit 0** — `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| §11.1 append-only | working tree & index vs HEAD **0 deleted lines**; commits since `a3a40f1` **0 deleted lines** |
| Discovered verifiers | **11, all exit 0** — `verify_audit_findings` 292.01 s, `cash_universe_coverage` 67.17 s, `historical_snapshot` 7.51 s, `phase2a_containment_and_trials` 1.70 s, `phase2b5_storage` 3.28 s, `phase2b_significance` 0.95 s, `phase2c_walkforward` 3.09 s, `phase2d_verdicts` 5.77 s, **`seq10_baseline_comparison` 39.57 s**, `seq10_certificate` 1.45 s, `wave1_thin_slice` 6.35 s |
| Suite | **610 passed** parallel + **1 passed** isolated = **611 of 611 collected**, 0 skipped, 0 xfailed, 88.01 s |
| Tags | **121** commit-bearing tags verified, including all four wave sign-offs |
| Source tree | `90b534704ad55d42…` — forced; the gate appended **one** row (`gate_sha 325bab8`, 611, 11 exits 0) in the clone |
| Criteria / pins | `1.1.16`, `CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470` — recomputed from my own canonicalisation |
| Manifest | 1,971 rows / **1,009 current** / 962 superseded; `MAN-FPR-V1-be45b7e791d5d3cd683ee119ae4beeae8cba3aab7728ac194d6b19521a691045` — recomputed from the bytes |
| Registry | **N = 11, N_eval = 6** read from `data/trials/` — unchanged |
| Corpus | **75,390,706 B**, raw sha256 **`ea0b65a3…`**, `DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15` — recomputed bar by bar |
| Ledger before this section | 94 rows / 56 ids; 50 CLOSED, 5 OPEN (`N-150`, `N-199`, `N-201`, `N-203`, `N-204`), 1 ACCEPTED |

**The round has no committed green row, and that is a property of the round, not of this section.** `git show 325bab8:data/reference/source_tree_green.json` holds 42 rows whose last `gate_sha` is `672c9d0`; `325bab8` appears zero times. The implementer's working tree carried three pre-existing paths it may not commit (`AGENTS.md` modified, the two `.agents/skills/*/SKILL.md` untracked), so the gate refused to certify a working copy it did not measure and wrote no row (§80.3). **Consequence for the baseline: the green claim for this round cannot be checked by reuse; it can only be re-measured.** I re-measured it, above, on a clean checkout of the commit's own tree — and the run wrote the row the commit could not (§102.8).

### 102.2 Process — the scope is clean, the protected surfaces did not move, and no trailer exists

`git diff --name-status 38d22a6..325bab8` returns exactly 11 paths: `CURRENT_STAGE_OF_WORK.md`; `reports/analysis/s100/seq10_baseline_comparison.json`; `reports/analysis/s102/seq12_data_qa.json`; `scripts/compare_seq10_baselines.py`; `scripts/probe_audit_findings.py`; `scripts/run_seq12_candidate.py`; `scripts/verify_audit_append_only.py`; `scripts/verify_seq10_baseline_comparison.py` (new); and the three verifier-count tests. A `git diff --stat` restricted to `configs/go_no_go_criteria.yaml`, `configs/trial_012_candidate.yaml`, `reports/audit`, `AGENTS.md`, `.agents`, `data/trials`, the corpus, `data/reference/manifest.jsonl`, `configs/partition_spec.yaml` and `reports/verdicts` is **empty**. So: no criteria value, no pre-registration clause, no audit prose, no trial row, no corpus byte, no manifest row, no fold spec and no verdict artifact moved. The 2024 fold is untouched and no holdout session was read (nothing in the diff names `2025-01-01..2026-11-11`).

No `Co-Authored-By`, `Generated with`, model-identity or co-author line exists in the commit message or body (§12.7). The commit is not an amendment; `38d22a6` is its parent and `feat-s103-325bab8` is a tag at it.

One note, recorded not raised: the commit message says items 1, 2, 5 and 6, and also says "Items 3 and 4's corpus half stay untaken". The artifact-surface mark that *is* delivered for item 4 appears in no ordered item. It is measured in §102.6 and its true scope is stated there.

### 102.3 Ruling 1 — a digest field's subject is the byte sequence it hashes, and the field must name it

**Evidence.** At `325bab8`: the trial_010 verdict is 498,216 B with **0** CRLF in the stored blob, sha256 `75571da3…`, and 512,882 B with **14,666** CRLF in the writing checkout, sha256 `4a729dbc…`; the corpus gzip is 75,390,706 B, sha256 `ea0b65a3…`, and contains **1,089** `0D 0A` pairs, so `sha256(bytes.replace(b"\r\n", b"\n"))` is `0fdc728a…`. Both defects §101 raised were the same error: a field whose *name* says "the file" whose *value* is a re-rendering of it.

**The single definition it changes.** A published digest of a tracked file is the sha256 of the sequence that file's reader will read from the repository: for a text path, the LF-normalised stored form; for a binary path, the stored bytes unmodified. A field carrying such a digest must carry a sibling `_of` naming which of the two it is. It changes nothing else: no threshold, window, fold, trial count or criterion; it does not authorise a digest of one file to stand for another; and it does not retroactively relabel a frozen round's record.

**Why the normalisation is well defined here.** I hashed all **2,434** tracked blobs at `325bab8` and asked `git check-attr text` of each: **0** blobs under a `text` attribute contain a CR byte, and **2,164** blobs under `-text` do. So for every tracked text path "LF-normalised" is today identical to "the bytes git stores" (the AGENTS boundary holds), and for every binary path it is identity or corruption — which is exactly why the two paths must be separate functions.

**The work it creates** is §102.13 item 5 (make a normalising digest function unable to receive a binary path by construction; `run_seq10_candidate._digest` and `run_seq11_candidate._digest` still normalise unconditionally). **The probe that must fail closed** is `probe N-203` plus `probe N-204`, both of which refuse the wrong rendering today (§102.8). **What would make this Ruling wrong:** a tracked text blob stored with a CR byte (then "LF-normalised" is not "the bytes git stores" and the text arm needs the blob, not the worktree), or a binary path for which normalisation is identity (then the split is ceremony). Phase: §10.5 / §9.1 / §12.3.

### 102.4 Item 1 (N-203) — the committed digest is the stored bytes' digest, and both checkouts now recompute it

`.gitattributes` exists at `325bab8` (1,619 B) and pins `* text=auto eol=lf`, `*.json text eol=lf`, `reports/audit/** text eol=lf`, and — after every text rule, last-match-wins — `*.json.gz -text`, `*.csv.zip -text`, `*.zip -text`, `*.gz -text`, `data/raw/circulars/*/** -text`.

| Measurement | Value |
|---|---|
| `sha256(git cat-file blob 325bab8:reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json)` | **`75571da3ebff56531addc6afdecdac6f05cf5a0799327a3ac85a97177ae067ae`** |
| `sha256` of that verdict with LF re-rendered as CRLF | `4a729dbc…` — the value §101 found committed, now gone |
| Committed `seq10_artifact_sha256` | **`75571da3…`**, with `seq10_artifact_sha256_of` naming "stored text bytes with CRLF normalised to LF" |
| `compare_seq10_baselines.py --check`, clean clone, `core.autocrlf=true` | **exit 0** |
| `compare_seq10_baselines.py --check`, clean clone, `core.autocrlf=false` + forced re-checkout (498,216 B, 0 CRLF) | **exit 0** |
| `compare_seq10_baselines.py --check`, writing checkout (512,882 B, 14,666 CRLF) | **exit 0** |
| `python scripts/verify_seq10_baseline_comparison.py`, clone | **exit 0** |

The digest is now checkout-independent **by construction**, and I measured it on both renderings rather than on the one the author had: the same 64 hex digits from a 14,666-CRLF worktree and from a 0-CRLF clone. `_sha256` normalises and is used for the verdict (text); the new `_sha256_bytes` is used for the corpus gzip (binary, §102.5). `probe N-203` additionally refuses the old shape: it asserts the field's own `_of` value as its message when the assertion fails, so the failure names the defect rather than the number.

### 102.5 Item 2 (N-204) — one dataset, one fingerprint, and every other published digest inventoried

| Measurement | Value |
|---|---|
| Corpus stored bytes | 75,390,706 B, sha256 **`ea0b65a3…`** |
| `sha256(bytes with CRLF→LF)` | `0fdc728a…` — the value the s102 artifact published at `46a99ec`, now gone from it |
| Manifest's current corpus row | exactly 1, `sha256 ea0b65a3…`, `byte_count 75,390,706` |
| s100 `dataset_sha256` | `ea0b65a3…` **and it was already `ea0b65a3…` at `38d22a6`** — this field did not move in this commit; only its `_of` label was added |
| s102 `corpus.sha256` | **`ea0b65a3…`**, with a `sha256_of` naming "the file's stored bytes, unnormalised" |

**Every published digest in `reports/analysis/**`, with what it hashes** (29 digest-valued fields across 8 files; the two per-certificate pairs that repeat are collapsed into one row each):

| File | Field | Hashes | Named? |
|---|---|---|---|
| s100 comparison | `criteria_fingerprint` | the typed criteria payload | by field name |
| s100 comparison | `dataset_content_fingerprint` | the corpus's logical content (calendar + bars) | by field name |
| s100 comparison | `dataset_sha256` | the corpus gzip's stored bytes | **yes** (`_of`) |
| s100 comparison | `seq10_artifact_sha256` | the verdict's LF form | **yes** (`_of`) |
| s101 QA | `corpus.sha256` | **the CRLF-mutated gzip stream** (`0fdc728a…`) | **no** — frozen record, see below |
| s101 QA | `pre_registration.sha256` | the config **before** the clause-(d) amendment (`66a05b4a…`) | no |
| s101 QA | `criteria.fingerprint` | the typed criteria payload | by field name |
| s102 QA | `pre_registration.sha256` | the config's LF bytes (`5a7f7b8f…`, recomputed) | **yes** (`_of`) |
| s102 QA | `restates.sha256` | the s101 artifact's LF bytes (`54c08bcb…`, recomputed) | **yes** (`_of`) |
| s94 verdict | `criteria_fingerprint`, `calendar_fingerprint`, `returns_digest` | criteria, calendar, return series | by field name |
| s98 criteria restatement | `live_criteria_fingerprint`, `live_manifest_fingerprint`, `pin_only_proof.executed_manifest_fingerprint`, `certificates.executed_{criteria,manifest}_fingerprint` | the live criteria and manifest, the manifest the pin-only proof executed against, and the executed pair per certificate | by field name |
| s98 demerger / drawdown restatements | `replay.corpus_fingerprint`, `replay.criteria_fingerprint` | corpus content; criteria | by field name |
| s99 feature partition | `derived_from.content_fingerprint`, `partition_fingerprint` | corpus content; the gap partition | by field name |

**Remaining mutating hash paths — flagged, not raised.** Fifteen `read_bytes().replace(b"\r\n", b"\n")` sites remain in `scripts/`, `src/` and `tests/`. I read every call site: all fifteen are applied to text (config, `.jsonl`, a captured `.html`, the manifest, audit volumes, verdict artifacts). The two sites that had been applied to a binary were the two this commit split, and they are now `_digest_bytes` / `_sha256_bytes`. `run_seq10_candidate._digest` and `run_seq11_candidate._digest` are still unguarded normalisers applied to text only; a future `.gz` argument repeats N-204 exactly. That is §102.13 item 5, not a finding, because no current call hashes a binary.

The s101 artifact's unlabelled `0fdc728a…` is **left as the §101 round's frozen record** (§10.1, §97.5): it is a statement of what that round published, it is superseded by the s102 artifact's labelled field, and relabelling it in place would be the overwrite §102.10 judges. Its presence is why the space of published corpus digests is not yet one value with one meaning.

### 102.6 Item 5 — the two silent boundaries are published, and every count recomputes from my own code

I wrote my own SMA(200) (simple, 6 dp, half-up), my own Wilder RSI(2) (2 dp), my own calendar-continuity segmentation, my own series resolution from `cash_equity_symbol_intervals.csv`, and my own step attestation (exact-date price-side ratio ≈ `1+move` within 0.5 %, or an exact-date DIVIDEND/RIGHTS cash amount reproducing close or open within 0.5 % of the previous close, with the TERP formula for rights). The library was used only as a cross-check, never to produce a count: **2,578,060 bars, 0 SMA mismatches, 0 RSI mismatches.**

| Measurement | Artifact | Mine |
|---|---|---|
| eligible signals after the point-in-time universe filter | — | 108,990 |
| executable entry signals | 93,463 | **93,463** |
| signals on the final session, no T+1 to fill at | 86 | **86** |
| … of those, EQ series | 62 | **62** |
| … of those, not EQ (24) | — | **24** |
| signals including the final session | 93,525 | **93,525** |
| signals refused for a non-EQ series | 15,441 | **15,441** |
| unattested ≥10 % level steps (corpus-wide) | (unchanged) | **6,731** |
| instruments carrying one | (unchanged) | **1,668** |
| signals with a step in their own 200-session window | 21,276 | **21,276** |
| usable entry signals | 72,187 | **72,187** |
| 200-row detail: distinct instruments | 9 | **9** |

**Field-by-field diff of `reports/analysis/s102/seq12_data_qa.json`, `46a99ec` → `325bab8`:** 94 flattened fields become 117. Exactly **23 added and 1 value changed**, and every one traces to an ordered item:

| Change | Ordered by |
|---|---|
| `corpus.sha256` `0fdc…`→`ea0b…`; `corpus.sha256_of` added | item 2 (N-204) |
| `pre_registration.sha256_of`; `restates.sha256_of` added | item 2's definition applied to the other two text digests (labels only; no value moved) |
| `signals_without_a_next_session` 86; `…_in_eq_series` 62; `entry_signals_including_the_final_session` 93,525; `entry_signal_scope` | item 5 |
| `signal_level_steps_in_lookback_detail_distinct_instruments` 9; `…_detail_scope` | item 5 |
| `rights_terp_branch.{records_in_the_table 4, records_on_a_candidate_step 0, limitation}` | item 6 |
| `corpus_reconciliation.{detail_is_a_census, detail_scope, unattested_unit_break{…9 fields}}` | **not in an ordered item** — the artifact-surface half of item 4 (§102.7) |

No field moved without a traceable origin. `status` stays `STOP` with the same `stop_reason`; `unattested_level_steps_feeding_a_signal` stays 4; `below_minus_20pct_level_step_at_open` stays 5; `blocked_by_adtv_floor`, the locked-session counters, `signals_in_non_eq_series`, `level_step_events`, `instruments_with_a_level_step` and the 200 detail rows are byte-identical.

**The guard reordering is semantically neutral for every previously published count, and I checked that rather than reading it.** `run_seq12_candidate` now computes `fillable = position + 1 < len(sessions)` after the universe filter and after series resolution, and counts a non-fillable signal **before** the series filter instead of `continue`-ing before it. The old order skipped those rows before `other_series_filtered += 1`, so the 24 non-EQ final-session signals were never in 15,441; the new order counts them in the new field and still excludes them from 15,441. Measured: 15,441 unchanged, and the four blocked counters unchanged. The signal predicate, the fill rule, the cost path and the engine are untouched by the commit; this is instrumentation around an unchanged loop.

### 102.7 Item 4 (N-201) — the mark is true, and it is not the header §101 asked for

**The ratio, recomputed with exact decimals:** `130.20 / 1292.54 = 0.1007318922431800950067309328918253980534`; at 6 dp round-half-up that is **`0.100732`**; at 4 dp it is `0.1007`. So of the three values the repository shows, `0.100732` is the only defensible 6-dp rounding, `0.100731` (audit §101.4, §101.7's prose) is a truncation, and `0.100730` (`.continue/sec100b.md`, quoted into §100) is wrong at the sixth digit. The artifact publishes `0.100732` and I confirm it. **No number in the audit record is edited; the correction is stated here** (§10.1).

**The band claim, recomputed:** `|0.100732 − 0.1| / 0.1 = 0.00732 > 0.005`, so the boundary is outside the ±0.5 % ratio band and is counted in `no_ratio_match`, not listed in `ratio_shaped_detail`. The artifact's `listed_in_ratio_shaped_detail: false` is measured true.

**The `detail_is_a_census: false` claim, recomputed against the corpus.** The corpus header publishes `threshold 0.35`, `explained_by_applied_row 1`, `explained_by_archive_record 0`, `no_ratio_match 74`, `ratio_shaped_unattested 699`, `ex_date_mismatch 0`, `cross_gap_pairs 16,194`, `cross_gap_extreme_moves 58`, `ratio_shaped_detail` 699 rows. My own census of one-session moves beyond ±35 % between **adjacent calendar sessions** finds **774**, of which **699** are in the detail list; the other 75 are the 74 `no_ratio_match` rows plus the one applied-row explanation. So the detail list is 699 of 774: **not a census**, and the scope note's three filters are the right three.

**The stamp claim.** The per-bar `adjustment_version` field exists on both boundary bars: `2019-12-18` at close 1292.54 and `2019-12-19` at open 129.2 / close 130.20 both carry `v2.0-attested-split-bonus-backadjust-2018-2023`. So the stamp is per bar, the bar's level is not adjusted across the transition, and `stamp_scope: SERIES_POLICY_NOT_A_PER_BAR_ATTESTATION` states exactly that. Measured true.

**Is an artifact-only mark an adequate stand-in? No — it is adequate as what it is, and N-201 stays OPEN.** It is a faithful transcription of the corpus's own reconciliation arithmetic beside the reader of the QA artifact, and it removes the specific misreading §101.5 measured (a reader taking `ratio_shaped_detail` for a census). It does not satisfy §101.12 item 4, whose two permitted branches were (a) attest the 1:10 with a committed corporate-action row and back-adjust, or (b) **mark `reconciliation.ratio_shaped_detail` as not a census in the corpus header**. The mark delivered lives in `reports/analysis/s102/seq12_data_qa.json`, which no consumer reads (`gated_by.consumers: []`), not in the corpus a reader loads. The corpus header still invites the census reading, and the 2019-12-19 bar still carries a stamp that is false for its level.

**What the corpus half requires, stated without touching a threshold.** Either branch changes the corpus file, which changes its gzip sha256, which appends a manifest row, which moves `MAN-FPR-V1`, which re-seals a criteria pin (`expected_manifest_fingerprint`). The pre-registration and the criteria are frozen post-hoc by §9.2 except for pin-only re-derivations, which this repository has done by precedent (§77–§79) but which no work order in this round authorised. So the corpus half is a **sealed-surface change requiring an explicit maintainer decision** — not a data-quality measurement, and not something this commit could take by editing the artifact that reads the corpus. The implementer's own statement of that reason is correct as far as it goes; what it does not establish is that the delivered mark closes the item.

**Clause (d)'s real-return sentence remains untaken.** The two excluded benchmark sessions still carry no stated return (−0.042 % on the level-break session, +0.108 % on the ISIN-transition session); the clause names the sessions as unmeasured but not what they were worth. Named residual.

### 102.8 Independence — which probes recompute, and which only agree with the producer

Thirteen attacks, each on a tracked file in a clean clone at `325bab8`, each restored byte-identically (`git status` clean after every case).

| Tamper | Probe / check | Result |
|---|---|---|
| hook file deleted | `N-203` | **FAIL** — names the missing file; inventory reports "pinned verifier(s) missing from discovery" |
| hook removed from `EXPECTED_VERIFICATION_SCRIPTS` | `N-203`; pin test | **FAIL**; pin test exit 1 |
| `seq10_artifact_sha256` → `0…0` | `N-203`; new verifier | **FAIL**; verifier exit 1 |
| `signals_without_a_next_session` 86→0 | `N-197` | **FAIL** |
| `entry_signals_including_the_final_session` 93,525→93,524 | `N-197` | **FAIL** |
| detail reach 9→8 | `N-197` | **FAIL** |
| source `LOOKBACK_SESSIONS` 200→20 | `N-197` | **FAIL** — the T−100 fixture step leaves the window |
| `detail_is_a_census` false→true | `N-201` | **FAIL** |
| `stamp_scope` rewritten | `N-201` | **FAIL** |
| **ratio made wrong in the producer *and* published** (`0.000001`→`0.0001` quantise; artifact `0.1007`) | `N-201` | **PASS — the probe cannot see it** |
| `corpus.sha256` → the mutated stream digest | `N-204` | **FAIL** |
| `_digest_bytes` made to normalise (producer only) | `N-204` | **PASS — the probe never calls the producer** |
| manifest's current corpus row → `0…0` | `N-204` | **FAIL** |

| Probe / check | Recomputes independently | Detects | Blind to |
|---|---|---|---|
| `N-197` | arithmetic and the distinct-ISIN count, from the artifact's own fields; 25 detail rows against corpus positions | artifact drift; a lookback regression via its fixture | **the counts themselves** — nothing recomputes 93,463/21,276; and the step classifier |
| `N-201` | the corpus ratio (own Decimal) and the detail-list absence | a corpus repair; artifact drift on the literal fields | **a wrong claim published with a wrong producer** (attack 10) — the equality is `published == producer(corpus)` |
| `N-203` | the sha256 itself, from file bytes | drift, and a wrong `_digest_text` in the published artifact | a producer regression that is also republished |
| `N-204` | the sha256 itself; the manifest row; the s100 field | drift and a republished mutated digest | a **source-only** regression (attack 12), because it never calls `_digest_bytes` |
| `verify_seq10_baseline_comparison.py` | **no** — it calls `compare_seq10_baselines.main(["--check"])` | any drifted field the producer would recompute differently | a wrong producer: producer and check are one code path |

The new verifier's shape is right and its independence is zero on purpose: a second implementation of the comparison would be the §14.4 two-paths defect. Its contribution is **discovery**, not corroboration, and the value it adds is measured — §101 found the check passing silently off every clone, and now deleting it fails both the probe and the gate inventory.

**Registry inventory, recomputed with my own AST walk:** 68 top-level functions, 56 `probe_*` functions, **0 duplicate definitions**, 56 registry entries, **0** mapping to an undefined function, **0** unregistered `probe_*`, **0** without an `assert`. No dead or assertion-free probe.

### 102.9 Gate and pins — 11/11, 611/611, and the three 10→11 edits did not weaken the pin

The suite and the eleven verifiers are §102.1. The three tests that pinned the discovered sweep moved `10 → 11` with a comment naming the new file. **They were not weakened:** each still asserts `list(EXPECTED_VERIFICATION_SCRIPTS) == discovered_verification_scripts()` and `verification_inventory_problem(discovered) is None`, and `verification_inventory_problem` fails closed in **both** directions — a pinned name missing from discovery (attack 1: "pinned verifier(s) missing from discovery") and a discovered name absent from the pin ("verifier(s) not in the pinned inventory"). The integer assertion is a second witness of the exact-equality assertion, not a substitute for it; adding the hook to the pin and to discovery is what moved it.

### 102.10 In-place regeneration — two overwrites, no consumer of either old digest

`git log -- reports/analysis/s100/seq10_baseline_comparison.json` shows two commits: `eea1757` (created) and `325bab8` (rewritten). The rewrite changed three keys — `seq10_artifact_sha256` `4a729dbc…`→`75571da3…`, and two `_of` labels. `dataset_sha256` was **already** `ea0b65a3…` at `38d22a6` and did not move; §101's corpus-digest finding was about the s102 artifact, not this one.

`git log -- reports/analysis/s102/seq12_data_qa.json` shows `46a99ec` and `325bab8`. The artifact's `restates` block points at **s101**, and its `changed_fields` are computed against s101's five `RESTATED_FIELDS`, so the 325bab8-vs-46a99ec delta it actually carries appears nowhere inside it. The s101 artifact is untouched, as §101.2 required.

**Judgement: both are overwrites of a published artifact, recoverable only from git — not restatements by the §97.5 append convention.** The s100 overwrite was ordered by §101.12 item 1, which named that path. The s102 overwrite was not ordered in those words and skips its own predecessor in the restatement chain. Neither is a threshold move, neither deletes a record, and neither broke a reader:

**Consumers of the old digests.** `4a729dbc…` appears nowhere at `325bab8` except git history. `0fdc728a…` appears in exactly four places: `reports/analysis/s101/seq12_data_qa.json` (the frozen §101 record, which is what it should say), `CURRENT_STAGE_OF_WORK.md` (prose quoting the defect), and two untracked `.continue/` scratch files. **No code, config, test or verifier reads either value.** So the overwrite is safe in the consumer sense and incomplete in the audit-trail sense; §102.13 item 6 asks the next round to publish the predecessor bytes by name.

### 102.11 Item 6 (RIGHTS) and item 3 (N-199)

**RIGHTS — 4 records, 0 on a candidate step, confirmed from the table, not the artifact.** `data/reference/corporate_actions.jsonl` holds 5,371 rows, of which **4** are `RIGHTS` and **0** superseded: `INE397D01024` 2022-08-01 (1:14 @ ₹535), `INE040H01021` 2022-10-14 (5:21 @ ₹5.00), `INE140A01024` 2023-05-12 (1:10 @ ₹750, description "PIRAMAL ENTERPRISES…" — the ISIN belongs to PEL), `INE683A01023` 2024-02-27 (1:4 @ ₹22, outside the corpus). All four are `CONTENT_IDENTIFIED_ONLY` with `UNATTESTED_NSE_CML_…` refs. Their ex-date opening gaps are **0.0 %**, **2.94 %**, **0.196 %**, and one has no bar in the window — so **0** sits on a ≥10 % step. The artifact's `4 / 0` is measured. The exercised-branch limitation it states is correct and is the point: the TERP path's first real use would attest a price level against an unattested record whose premium is a regex over prose, and that first use is not evidence.

**N-199 — still blocked, and nothing was synthesised.** `data/silver/price_bands` is an empty directory (0 files); `data/raw/price_bands` does not exist; no tracked path under `data/` contains the string `price_band`; `data/reference/surveillance_intervals.jsonl` is a **3-row `SYNTHETIC_FIXTURE`** set dated 2024 (outside the evaluation window) and is not band data. The only writer of the partition, `ingest_daily_price_bands`, has no raw payload to promote. The three categorical counters are `"NOT RUN"` with `price_band_partition: {files: 0, populated: false}`, and `not_run.exit_freeze_round_trip` says why. I confirm both limitations: **the exit-freeze round trip is unmeasured**, and no value in the artifact was manufactured from prices.

### 102.12 Findings ledger after this section

| | before §102 | after §102 |
|---|---|---|
| rows / ids | 94 / 56 | **96 / 56** |
| latest per id | 50 CLOSED, 5 OPEN, 1 ACCEPTED | **52 CLOSED, 3 OPEN, 1 ACCEPTED** |
| OPEN ids | `N-150`, `N-199`, `N-201`, `N-203`, `N-204` | **`N-150`, `N-199`, `N-201`** |

N-203 and N-204 gain `CLOSED` rows with `closed_in_section: 102` and the measurement that decided each. **N-201 stays OPEN**: its artifact surface is measured true and its corpus half is untouched, and the ledger has no PARTIAL state, so the partial measurement lives here rather than in a row that would misreport it (N-157). N-199 stays OPEN and BLOCKED. No finding is deleted, softened or re-scoped.

### 102.13 Phase verdicts

| Phase (§103's row in `CURRENT_STAGE_OF_WORK.md`) | Verdict | Residual |
|---|---|---|
| Digest provenance, text vs binary (§9.1, §12.3, §10.5) | **PASS** — stored-bytes digest `75571da3…` / `ea0b65a3…`; `--check` exit 0 in a CRLF checkout and in both clones; Ruling 1 stated | `run_seq10`/`run_seq11` still normalise unconditionally; the s101 artifact keeps an unlabelled mutated-stream digest as its frozen record |
| Step 2 QA counts and boundaries (§6.3, §9.1) | **CLOSED** — 86/62/24, 93,525, 15,441, 9-of-1,668, 21,276, 72,187 all recomputed with own code; every moved field traces to an ordered item | the published counts are still attested by a prefix of 1,668 instruments, and 62 final-session signals carry no per-signal list |
| Corpus continuity, clause (d) (§5.4, §9.2) | **PARTIAL** — the mark is measured true (699 of 774, ratio 0.100732, stamp scope); the corpus half and clause (d)'s real-return sentence are untaken | **corpus-header mark or attested 1:10**, both sealed-surface changes; the two dropped sessions' −0.042 %/+0.108 % still unstated in the clause |
| RIGHTS/TERP branch (§5.4) | **CLOSED as ordered** — 4 records, 0 on a candidate step, limitation stated | the branch remains unexercised; its first use is not evidence |
| Circuit freeze / band counters (§5.3, §13.2) | **BLOCKED, unchanged** — `NOT RUN`, empty partition, nothing synthesised | population and the exit-freeze round trip |
| Verifier discovery and pins (§12.3, §12.4) | **PASS** — 11/11 exit 0 in a clean clone, 611/611, both inventory directions fail closed | the round's own green row did not exist; recorded in the commit that follows this section |
| Artifact restatement discipline (§10.1) | **PARTIAL** — s101 untouched; both rewritten artifacts reproduce from their producers | two in-place overwrites with no `restates` entry naming their predecessor bytes |
| Seq 10 / seq 11 / criteria / fold / holdout | **held** — `CRIT-FPR-V1-535e47f5…` `1.1.16`, corpus `ea0b65a3…` / `DATA-CTNT-V2-cb4832c0…`, `MAN-FPR-V1-be45b7e7…`, N = 11 / N_eval = 6, 2024 fold untouched, holdout unread | `1.1.16` still labels three criteria sets (§98.6) |

### 102.14 Work order (feat-s104), ordered by what it unblocks

1. **N-201, the corpus half — a maintainer decision, then one of two branches.** Either (a) a committed corporate-action row attesting the 1:10 across `INF732E01011`→`INF204KB14I2` and a back-adjusted 2019-12-19 bar, or (b) a corpus-header field marking `reconciliation.ratio_shaped_detail` as a filtered list. Both change the gzip and therefore append a manifest row, move `MAN-FPR-V1` and re-seal `expected_manifest_fingerprint`; the pin-only re-derivation is the §77–§79 precedent and must be recorded as such in the same commit. **The probe that must fail closed:** `probe N-201` as written plus the refusal, **and** — because §102.8 attack 10 passes — a new independent recomputation inside `probe N-201` that derives the published ratio from the corpus bars with its own Decimal arithmetic instead of importing `corpus_reconciliation_claim`. Phase: §5.4 / §9.2 / §10.5.
2. **Clause (d)'s real-return sentence.** State −0.042 % and +0.108 % where the clause names the two unmeasured sessions, as a new commit after `325bab8`; no threshold, window or fold field moves. **Probe:** `probe N-201` must keep passing and a new assertion must require both figures in the clause beside the session dates. Phase: §5.4 / §9.2.
3. **N-199 — populate the band partition or retire the counters.** A sourced per-session NSE price-band archive for `2018-04-01..2023-12-31` under `data/raw/price_bands/` with retrieval metadata, promoted one session per partition, and the exit-freeze round trip measured. **Probe:** the existing biconditional (`NOT RUN` iff the partition is empty). Phase: §5.3 / §13.2 / §13.3.
4. **Ruling 1's enforcement.** Make a normalising digest function unable to receive a binary path by construction (suffix or attribute check that raises), starting with `run_seq10_candidate._digest` and `run_seq11_candidate._digest`; no published value changes. **Probe:** a unit test that passes a `.gz` to each normaliser and requires the refusal, plus `N-203`/`N-204` unchanged. Phase: §10.5 / §9.1.
5. **Restatement discipline for in-place regenerations.** The s102 artifact should carry the predecessor it replaced (`reports/analysis/s102/seq12_data_qa.json` at `46a99ec`) with its bytes' digest and the fields that moved between the two s102 revisions, or the next round must append a new path rather than rewrite one. **Probe:** a new one requiring the artifact's `restates` block to name the immediately preceding revision of its own path and to reconcile the fields that moved. Phase: §10.1 / §9.1.
6. Carried unchanged: `N-150`; §101.12 item 7 (the §98.5 restatement/replay asymmetry; the §98.6 label of three criteria sets); §99.10 items 2–3; §96.10 items 5–7.

### 102.15 What would falsify this verdict

- **N-203:** a clone in which `compare_seq10_baselines.py --check` exits 1, or a stored text blob containing a CR byte (which would make "LF-normalised" something other than "the bytes git stores", and Ruling 1's text arm wrong). I scanned all 2,434 blobs and found 0.
- **N-204:** a reader who can reproduce the artifact's `corpus.sha256` from anything but the raw file — measured impossible: the raw digest is `ea0b65a3…` and the mutated one is `0fdc728a…`, and the artifact, the manifest and the s100 field now all say `ea0b65a3…`.
- **The counts:** a signal set other than 93,463 under the runner's own EQ resolution and T+1 guard, or a final-session count other than 86/62, or an instruments-with-a-step count other than 1,668. My indicators matched the library on all 2,578,060 bars and my classifier reproduced 6,731 / 21,276 / 72,187; a mismatch would mean the corpus decides between us.
- **The guard reordering:** any previously published count that moved — 15,441 and the blocked counters did not, and I diffed all 94 pre-existing fields.
- **N-201's mark:** a corpus whose `ratio_shaped_detail` is a census (699 of 774 measured), or a boundary ratio inside ±0.5 % of 0.1 (0.00732 measured outside), or a stamp that is a per-bar attestation after all.
- **The gate:** a `--force-full` run at `325bab8` that is not 11/11 and 611/611, or any tamper in §102.8 that passes besides the two I report as passing.
- **The overall verdict:** a consumer of the QA artifact, which would make its `NOT RUN` counters gate something. There is none, and the STOP still gates no execution path.


## §103 — Audit of `1824857` (tag `feat-s104-1824857`): Ruling 1 reaches six of ten digest producers, the ratio is recomputed from the corpus bars, and both predecessor pointers verify from the blob — while a copy without history cannot publish either artifact

**Date:** 21 November 2026
**Commit under review:** `1824857` (13 files, +510/−58; parent `c47f3ce`)
**Baseline:** `c47f3ce` (§102, tag `audit-s102-1e3c836`)
**Verdicts:** item 3 **PASS** · item 4 **PARTIAL** · item 5 **CLOSED** · item 6 **PASS** · item 7 **PASS** · item 8 **PASS** · N-201 **PARTIAL, held OPEN** · N-199 OPEN, still BLOCKED · N-150 carried · **no new ledger row** (§103.10), two named residuals and one instrument defect measured

### 103.1 Baseline re-measured at `1824857`

Everything below was executed on this host, in a clean clone whose only addition was the log files the run wrote outside the tree.

| Measurement | Result |
|---|---|
| `scripts/verify_audit_append_only.py --force-full`, clean clone at `1824857` | exit **0**, `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)` |
| Verifiers discovered / executed | **11 / 11**, every one exit 0; source tree `00af5b8c226ca0585c9617503de025ec3a663f68b8f8606342e560ea6a9684a9` |
| Test suite | **620 of 620** collected — 619 in the parallel invocation + 1 isolated — **0 skipped, 0 xfailed** (111.3 s) |
| `verify_audit_findings.py` | exit 0 (part of the 11); 96 rows / 56 ids, latest 52 CLOSED, 3 OPEN, 1 ACCEPTED |
| Green row | the `--force-full` run appended **one** row (43 → 44) naming `1824857`; the plain run at `fc69bce` reuses it and appends nothing (§103.7) |
| Trial registry | N = **11**, N_eval = **6**, manifest head `e76c249f…` |
| Criteria | **1.1.16**, `CRIT-FPR-V1-535e47f5a4a98569f0ecfc6f8fbf5623420192b555808e655ed000969ec8e470` — the library's value and my own canonicalisation agree |
| Manifest | `MAN-FPR-V1-be45b7e791d5d3cd683ee119ae4beeae8cba3aab7728ac194d6b19521a691045`, 1,877,557 B |
| Corpus | 75,390,706 B, sha256 `ea0b65a32a89a7b497cc9dc40cbec3fdbdcb9b582c74105e1a9ea6959d4ab1c5`; 1,089 CRLF pairs; `DATA-CTNT-V2-cb4832c0b43952c4a03d58ee65ff5b15` recomputed from 2,578,060 bars / 2,735 instruments |
| 2024 fold / holdout | `git diff --name-only c47f3ce..1824857` matches no path containing `2024`, `2025`, `fold` or `holdout`; `data/` and `configs/` are untouched; the sealed window `2025-01-01..2026-11-11` was not read |
| Rule files | `0fa680d` adds nine NON-NEGOTIABLES lines to `AGENTS.md`, `c47f3ce` adds two skill files: both are **ancestors of the base**, none inside the commit under review |
| Protected trees | `git diff --stat c47f3ce..1824857` over `data/`, `configs/`, `reports/verdicts/`, `src/signal_core/research/` is **empty**; the only analysis paths that move are the two the commit was ordered to regenerate |

### 103.2 Item 2 — the bypass matrix, re-measured

Nine cases against `artifact_digest`, each run on a tracked checkout at `1824857`.

| Case handed to the guard | Text arm | Binary arm | Reading |
|---|---|---|---|
| text bytes named `.gz` | **refused** (`ValueError`) | hashes stored bytes | correct |
| gzip bytes named `.json` | **accepted**, returns the LF-mutated digest | refuses (text suffix) | **gap** — the arm is the suffix, not the payload |
| gzip bytes named `.GZ` | **refused** (`lower()`) | hashes | correct |
| empty file named `.gz` | refused | hashes (`e3b0c442…`) | correct |
| directory named `.gz` | `PermissionError` | `PermissionError` | not `ValueError`; not a payload |
| gzip bytes, no suffix | **accepted** | refuses (no binary suffix) | **gap**, same class as row 2 |
| `.html` under `data/raw/circulars/**` (`-text` in `.gitattributes`) | **accepted**, digest of the LF form ≠ digest of stored bytes | refuses | **gap** — the glob rule is not mirrored by `BINARY_SUFFIXES` |
| symlink to a binary path | not runnable on this host (`WinError 1314`, no symlink privilege) | — | **NOT RUN** |
| `data/reference/historical_dataset_2018_2023.json.gz` | refused | `ea0b65a3…` | correct |

`BINARY_SUFFIXES = (".gz", ".zip")` mirrors three of the four `-text` rules in `.gitattributes` — `*.csv.zip`, `*.json.gz`, `*.zip`, `*.gz` — and not the fourth, `data/raw/circulars/*/**`. **No current call passes a binary to a text arm**: 12 of the 13 remaining replacement sites outside the module operate on text, and the thirteenth (`probe_audit_findings.py`, `probe N-204`) applies the replacement to the corpus bytes deliberately, to name the value a normalising digest would publish. So no published value is wrong; the exposure is latent and is named as residual 103.12 item 2, under §102.5's own test ("not a finding, because no current call hashes a binary").

### 103.3 Item 3 — the four consumers, run at both commits, compared byte-for-byte

Each consumer was run to completion in a clone at `c47f3ce` and in a clone at `1824857`, on the same corpus, with stdout captured. Timing lines and absolute clone paths were the only expected differences.

| Consumer | `c47f3ce` | `1824857` | Difference |
|---|---|---|---|
| `run_seq10_candidate.py` | exit **1** — `DuplicateTrialError: TRIAL-PHASE3B2-EXPANDED-010 is already registered`; Run A `hold_bound_forced_exits=422`, `refusals=7,309`; Run B 0 / 0 | identical exit and numbers | build time 138.1 s both; the `sha256` line differs (`4d8279bc…` vs `04129d68…`) — see below |
| `run_seq11_candidate.py` | exit **1** — `DuplicateTrialError: TRIAL-PHASE3B2-LIQUIDITY-ATR-011`; dataset 1,425 sessions / 2,735 instruments, `DATA-CTNT-V2-cb4832c0…` | identical exit, ids and fingerprint | load 101.9 s vs 93.1 s; traceback paths |
| `probe_seq10_candidate.py` | exit **1** in the run-dirtied checkout: "the baseline … hashes to `4d8279bc…`, not the digest the comparison records" | exit **1**, same message, `04129d68…` | on **pristine** clones both exit **0** with **byte-identical** stdout ("CERTIFIED … N = 11 … evaluation_count 6 … sealed-era run refused") |
| `diagnose_seq10_drawdown.py` | exit **0**, 1,491 B | exit **0**, 1,491 B | build 84.2 vs 84.4 s; replay **32,112.8 s** vs **32,124.2 s**; every other line identical |

**The digest difference is the artifact's own timestamp, not the commit.** `run_seq10_candidate.py` rewrites `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json` in place on every execution; the two rewritten files differ in exactly **one** line, `timestamp_utc` (`2026-11-20T18:21:11.683314` vs `2026-11-20T18:20:08.018859`), and their digests differ accordingly. Both commits do it, so it is not introduced here — but it means a checkout that has run the consumer fails `compare_seq10_baselines.py --check` until the artifact is restored, and it is why the two dirty-tree probe runs fail. That is residual 103.12 item 3, not an item-3 failure. **Behaviour is preserved**: no count, fingerprint, verdict or exit code moved.

### 103.4 Item 4 — Ruling 1 reaches six consumers, and four normalising producers remain outside the module

The commit's `§104` says: *"Every normalising digest function in `scripts/` was **replaced** by a delegation to it, not left beside a guarded copy"*. Measured at `1824857`, six scripts import the module —

`compare_seq10_baselines` (`_sha256`, `_sha256_bytes`), `run_seq12_candidate` (`_digest_text`, `_digest_bytes`), `run_seq10_candidate` (`_digest`), `run_seq11_candidate` (`_digest`), `probe_seq10_candidate` (`_digest`), `diagnose_seq10_drawdown` (`_digest`)

— and their old bodies are gone. Four digest producers are **not** routed, and two of them publish the result:

| Site | Produces | Published where | Applied to |
|---|---|---|---|
| `src/signal_core/contracts/criteria.py:29` `compute_manifest_fingerprint` | **`MAN-FPR-V1`** | every verdict artifact, the criteria pin | text (manifest) |
| `scripts/derive_2018_2023_corpus.py:377` `corporate_actions_digest` | corpus header field | the corpus snapshot's own header | text (corporate actions) |
| `src/signal_core/storage/circulars.py:176` | per-file circular digest | circular bundle | text (circular JSON) |
| `scripts/probe_hold_bound_invariance.py:82` `_digest` | registry fingerprint | a probe workspace | text (registry JSONL) |

So the sentence is false as written: two normalising digest **functions** in `scripts/` survive (`probe_hold_bound_invariance._digest`, and `derive_2018_2023_corpus`'s inline `corporate_actions_digest`), and the most load-bearing one of all — `MAN-FPR-V1`, which every criteria pin depends on — is in `src/`. The commit's own count is also off: it says "the nine `read_bytes().replace(b"\r\n", b"\n")` sites that remain"; I count **13** outside `artifact_digest.py` (1 derive, 4 in `probe_audit_findings` — one of which computes the mutated digest on purpose, 1 `probe_hold_bound`, 1 `verify_audit_append_only`, 2 `verify_cash_universe_coverage`, 2 `verify_phase2a`, 1 criteria, 1 circulars). Ten are parsing or probe-side text comparisons, one is the deliberate binary attack computation in `probe N-204`, and the two digest producers are the residue.

**What is right and was measured:** the guard does refuse the two arms it defines (103.2 rows 1, 3, 4, 9); reverting a producer to normalise now fails at the producer rather than at a number (`t12`, 103.6); and **no published fingerprint moved** — `MAN-FPR-V1-be45b7e7…`, `CRIT-FPR-V1-535e47f5…` and `ea0b65a3…` are the values `c47f3ce` carried, and the s100/s102 artifacts gained only their pointer (§103.5). **Verdict: PARTIAL.** The rule is enforced where the defect occurred and at the two producers the order named; it is stated as universal and is not.

### 103.5 Item 5 — both pointers verify from the blob, and reproduction now requires the object

| Artifact | Predecessor | sha256 of the blob (`git cat-file blob`) | Moved |
|---|---|---|---|
| `reports/analysis/s100/seq10_baseline_comparison.json` | `eea1757f15ed1daf202eb36df7f2aa3151188a2e` | `b5c14b9f5f7b5b2e239360b6ca3e1165532f20be1c47ae2e669e9b00e58a7528` — **matches** | +2 added, 1 changed (`seq10_artifact_sha256`) |
| `reports/analysis/s102/seq12_data_qa.json` | `46a99eccb8af5b4ba2ccd6bef003842eaa3ce17f` | `0dffff1540744f4f7e2b32e9a7ac93235721efa85cfb02d6ff6be7804f8c24b3` — **matches** | +8 added, 3 changed (`corpus`, `pre_registration`, `restates`), 0 removed |

I recomputed both digests from the objects and both field lists from `(blob, committed artifact)`; the field diff `c47f3ce → 1824857` of the two artifacts is **exactly `predecessor` added, 0 values changed** (s100 +14 lines, s102 +22 lines). The commit is pinned, not `HEAD`-derived, so the pointer keeps naming the same revision after later commits — measured: `--check` exits 0 at `1824857` in three checkouts.

**The cost, measured: a copy without the objects can no longer publish either artifact.** In a `--depth 1 --no-local` clone `git fetch --depth 1 1824857` leaves the commit and tree but **not** `eea1757`; in a `git archive 1824857` export there is no repository at all. Both run `compare_seq10_baselines.py --check` to exit **1** — `cannot read the predecessor blob eea1757…: the artifact must name the revision it replaced, and a checkout without that object cannot publish it` — and the tarball fails `run_seq12_candidate.py --check` the same way on `46a99ec`. That is a behaviour change: at `c47f3ce` the check needed only the tree's bytes. It fails **closed and by name**, which is the right direction, but the requirement is nowhere a reader meets it. Named limitation, 103.12 item 4. **Verdict on what was ordered: CLOSED.**

### 103.6 Item 6 — fifteen tampers, fourteen refused

Each case was applied to a tracked file in a clone at `1824857`, the probe or check run, and the file restored byte-identically (`git status` clean after every case).

| Tamper | Probe | Result |
|---|---|---|
| hook file deleted | `N-203` | **FAIL** — "pinned verifier(s) missing from discovery" |
| hook removed from the pin | `N-203` | **FAIL** |
| `seq10_artifact_sha256` zeroed | `N-203` | **FAIL** |
| `signals_without_a_next_session` 86 → 0 | `N-197` | **FAIL** |
| `entry_signals_including_the_final_session` 93,525 → 93,524 | `N-197` | **FAIL** |
| detail reach 9 → 8 | `N-197` | **FAIL** |
| `LOOKBACK_SESSIONS` 200 → 20 | `N-197` | **FAIL** |
| `detail_is_a_census` false → true | `N-201` | **FAIL** |
| stamp scope rewritten | `N-201` | **FAIL** |
| codec ratio quantised **and** artifact published `0.1007` | `N-201` | **FAIL** — "the artifact publishes ratio 0.1007, and 130.2 / 1292.54 = 0.1007318922431800950067309329 is 0.100732 at 6 dp" (attack 10, **closed**) |
| producer quantised only | `N-201` | **PASS** — correct: the probe recomputes from the corpus bars and no longer reads the producer |
| `_digest_bytes` made to normalise (producer only) | `N-204` | **FAIL** — the guard's own refusal (attack 12, **closed**) |
| corpus digest mutated in the artifact | `N-204` | **FAIL** |
| manifest's current corpus row zeroed | `N-204` | **FAIL** |
| corpus bar tampered | `N-201` | **FAIL** |

The two attacks §102.8 reported as passing now fail, and the one that still passes is the one that should: with the producer wrong **and** the artifact not republished, an independent recomputation is exactly the evidence the probe was rebuilt to be. Its blind spot is now the opposite one — an artifact that publishes a wrong ratio *and* a corpus whose bars agree with it.

### 103.7 Item 7 — the gate, the green row, and the nine tests

- `--force-full` at `1824857`: **620/620**, **0** skipped, **0** xfailed, **11/11** verifiers exit 0, tree `00af5b8c…`, one appended row naming `1824857`.
- Plain `python scripts/verify_audit_append_only.py` at `fc69bce` (the commit that recorded the row): exit **0**, `[INFO] Source tree 00af5b8c… is already recorded; not appending a duplicate row`, `git status` clean — legal outcome 1/3 of the skill's three.
- The row is the **single** append (43 → 44), its `gate_sha` is `1824857`, and its `source_tree_hash` recomputes to `00af5b8c…` from `HEAD`'s tree.
- The nine new tests in `tests/unit/test_phase3b2_audit_s104_items.py`: **9/9 pass** at `1824857`, **9/9 fail** at `c47f3ce`; `tests/` differs by one **added** file and **0** modified ones.
- The tree hash is computed from object ids, so a bare `git checkout` on this host cannot move it; the CRLF case is measured separately (103.8).

### 103.8 Item 8 — a CRLF checkout still publishes the same digests

In a clone at `1824857` with `core.autocrlf=true`, both artifacts rewritten to CRLF on disk (5,808 B and 84,557 B), `compare_seq10_baselines.py --check` and `run_seq12_candidate.py --check` both exit **0**. The text arm normalises CRLF to LF, which is what the repository stores for a text path (measured over all tracked blobs in §102.3); the binary arm hashes stored bytes, which git does not re-encode.

### 103.9 Item 9 — the band partition, and what `§104` accounts for correctly

**Band data: nothing was synthesised.** `data/silver/price_bands` is an empty directory (0 files), `data/raw/price_bands` does not exist, no tracked path contains `price_band`, and `data/reference/surveillance_intervals.jsonl` is three `SYNTHETIC_FIXTURE` rows dated 2024 — outside the evaluation window and not band data. The census, the exit-freeze round trip and the three categorical counters stay `NOT RUN`. N-199 stays OPEN and BLOCKED, unchanged from §102.

**`§104`'s accounting against my measurements.** Confirmed: the two predecessor pointers and their field lists (103.5); the ratio `0.100732`, its distance `0.00732` from 0.1, the 699-of-774 census, the 16,194 gap pairs and the 74 `no_ratio_match` rows (103.6, table rows 8–11); the gate numbers and that the pre-commit run recorded no row. Not confirmed: "every normalising digest function in `scripts/` was replaced" and the count of nine remaining sites (103.4 — two script-level digest producers survive and the count is 13); "`BINARY_SUFFIXES` mirrors the `-text` rules" (103.2 — three of four; the `data/raw/circulars/*/**` glob is not mirrored). The `§104` log is the implementer's document; I record the difference here and do not edit it.
### 103.10 Findings ledger after this section

| | before §103 | after §103 |
|---|---|---|
| rows / ids | 96 / 56 | **96 / 56** |
| latest per id | 52 CLOSED, 3 OPEN, 1 ACCEPTED | **52 CLOSED, 3 OPEN (`N-150`, `N-199`, `N-201`), 1 ACCEPTED** |

**No row is added, and this is a deliberate instrument decision.** A new finding must carry a probe that fails closed (§14.2), and `verify_audit_findings.py` executes every latest row's probe on every run. A probe written to fail on this tree would turn the gate red on `main` (§12.3); a probe written to pass on this tree is the inverted-probe shape I measured in this round's own predecessor.

**That defect is worth stating plainly.** `probe N-204` as first published by the audit round at `672c9d0` asserted `committed == mutated` — it **passed on the defective tree** and would have failed on the repair; the implementer had to rewrite it at `325bab8`. So an OPEN finding's registered probe is, by construction, a witness that the defect is present, not an acceptance test that the fix is real, and the gate is blind to a wrong fix until the probe is flipped. I re-ran it at `672c9d0`: `PASS N-204`, exit 0, on the tree that still published `0fdc728a…`. Under that convention the two residuals below stay residuals — they are named, measured, ordered, and carry the assertions that must exist before anyone claims them closed (§103.12 items 1–2). The next round should state the closure-mode assertion in the work order for every OPEN id, so the flip is the implementer's obligation rather than their discretion.

### 103.11 Phase verdicts

| Phase (§104's row in `CURRENT_STAGE_OF_WORK.md`) | Verdict | Residual |
|---|---|---|
| Digest provenance, text vs binary (§9.1, §10.5, §12.3) | **PARTIAL** — the two arms work and refuse the cases they define; six consumers delegate; no published value moved; `--check` exit 0 in a CRLF checkout | four normalising producers outside the module (`MAN-FPR-V1` among them), the suffix-only binary key, the `data/raw/circulars/*/**` glob, symlinks NOT RUN |
| Behaviour parity of the four consumers (§9.1, §12.3) | **PASS** — identical exits, counts, fingerprints and verdict lines at both commits | `run_seq10_candidate` rewrites a committed s94 artifact in place; `probe_seq10` is only clean on a tree that has not just run it |
| Restatement discipline (§10.1) | **CLOSED as ordered** — both pointers pinned, blob-verified, field lists recomputed; +14/+22 lines and nothing else | a tree without the predecessor objects cannot publish either artifact, and the requirement is unstated |
| N-201 probe independence (§8.2, §9.1) | **PARTIAL** — the ratio, the band distance, the census and the counters are recomputed with own Decimal and own census; attacks 10 and 12 now fail | the corpus half is untaken (sealed surface, maintainer decision) |
| Circuit freeze / band counters (§5.3, §13.2) | **BLOCKED, unchanged** — empty partition, `NOT RUN`, nothing synthesised | population and the exit-freeze round trip |
| Verifier discovery and pins (§12.3, §12.4) | **PASS** — 11/11 exit 0, one row appended, plain run reuses it and appends nothing | the audit probe convention in 103.10 |
| Seq 10 / seq 11 / criteria / fold / holdout | **held** — `CRIT-FPR-V1-535e47f5…` at 1.1.16, `MAN-FPR-V1-be45b7e7…`, corpus `ea0b65a3…` / `DATA-CTNT-V2-cb4832c0…`, N = 11 / N_eval = 6, no 2024/2025 path touched | `1.1.16` still labels three criteria sets (§98.6) |

### 103.12 Work order (feat-s105), ordered by what it unblocks

1. **N-201, the corpus half — still a maintainer decision, then one of two branches.** Either a committed corporate-action row attesting the 1:10 across `INF732E01011`→`INF204KB14I2` with a back-adjusted 2019-12-19 bar, or a corpus-header field marking `reconciliation.ratio_shaped_detail` as a filtered list. Both change the gzip → a manifest row → `MAN-FPR-V1` → `expected_manifest_fingerprint`. **The probe that must fail closed:** the existing `probe N-201` (independent Decimal recomputation, attacks 10 and 12 failing) **and** a new assertion that reads the chosen branch's marker out of the corpus buffer, not the QA artifact. Phase: §5.4 / §9.2 / §10.5.
2. **Finish Ruling 1 by construction, or stop claiming it universally.** Route `criteria.compute_manifest_fingerprint`, `circulars`' per-file digest, `derive_2018_2023_corpus`'s `corporate_actions_digest` and `probe_hold_bound_invariance._digest` through `artifact_digest`; mirror the `data/raw/circulars/*/**` `-text` rule (glob or `git check-attr`) or amend the module docstring and `§104`'s sentence to say the key is the suffix. No published value changes. **Probe:** one case per producer passing a `.gz` and requiring the refusal, a case passing gzip bytes named `.json` and requiring the refusal, and a case on the circulars glob; `N-203`/`N-204` unchanged. Phase: §10.5 / §9.1.
3. **Stop the seq-10 consumer rewriting a committed artifact.** `run_seq10_candidate.py` overwrites `reports/analysis/s94/seq10_baseline_2018_2023_verdict.json` with a fresh `timestamp_utc` on every execution, so the committed digest is reproducible only until the script is run. **Probe:** two consecutive runs produce the same artifact digest, and `compare_seq10_baselines.py --check` exits 0 after a run. Phase: §10.1.
4. **State the history requirement where it is met.** The two `--check` paths now need the predecessor objects; a shallow clone and an archive export both refuse. Say so in the scripts' help text and in the artifact's `predecessor` documentation — or carry enough to verify the pointer's well-formedness without the blob, and say which of the two a reader is being given. **Probe:** the tarball case exits 1 with the named refusal, and the documented requirement is quoted by a test. Phase: §12.3 / §10.1.
5. **Audit instrument.** For every OPEN id, the work order must carry its closure-mode assertion, and the probe must be flipped in the commit that closes it (103.10). **Probe:** `verify_audit_findings.py` fails if a CLOSED row's probe still asserts the defect. Phase: §9.1 / §14.2.
6. **N-199 — unchanged.** Populate `data/raw/price_bands/` from a sourced per-session NSE archive for `2018-04-01..2023-12-31`, promote one session per partition, measure the exit-freeze round trip. **Probe:** the biconditional (`NOT RUN` iff the partition is empty). Phase: §5.3 / §13.2 / §13.3.
7. Carried unchanged: `N-150`; clause (d)'s real-return sentence (`§102.14` item 2, still untaken — it lives in `configs/trial_012_candidate.yaml`, which this round may not edit); §101.12 item 7; §99.10 items 2–3; §96.10 items 5–7.

### 103.13 What would falsify this verdict

- **Item 4's PARTIAL:** a seventh script importing `artifact_digest`, or a fourth `-text` rule that `BINARY_SUFFIXES` does mirror after all — impossible for the glob rule as written, but if `data/raw/circulars/**` were re-declared by suffix the mirroring would hold and the residual would shrink to the two script-level producers.
- **Item 3's PASS:** any consumer output line that differs between the two commits in anything but a timing, an absolute path, or the s94 artifact's `timestamp_utc`-derived digest. I diffed all four stdouts; the only numeric differences are 101.9 → 93.1 s and 32,112.8 → 32,124.2 s.
- **The pointer verification:** a `git cat-file blob` of either predecessor yielding a digest other than `b5c14b9f…` / `0dffff15…`, or a field list that the blob and the committed artifact do not jointly produce. Both recomputed true.
- **The gate:** a `--force-full` run at `1824857` that is not 620/620 and 11/11, or a plain run at `fc69bce` that appends a second row or rewrites one. Neither happened.
- **N-201's probe:** a corpus whose bars give a different 6-dp ratio, or an artifact that publishes a value the bars contradict — attack 10 now catches the second, which is why it failed.
- **The band verdict:** a tracked band payload anywhere under `data/` — `0` files found; any counter other than `NOT RUN` in the artifact would be fabrication.
- **The instrument defect in 103.10:** a probe registered at an audit commit that fails on the tree it was opened against. `N-204` at `672c9d0` passes, so the defect is real; a probe that failed there would falsify it.
### 103.14 Post-commit gate run, and a correction to this section's own index handling

- `python scripts/verify_audit_append_only.py` at `9e94336` (plain, no `--force-full`): exit **0**, `OVERALL VERDICT: ALL REPOSITORY FOUNDATION GATES PASSED (100%)`, and `[INFO] Source tree 00af5b8c… is already recorded; not appending a duplicate row`. This is the skill's legal outcome **3**: an audit commit is docs-only, projects to the source tree `1824857` already recorded, and appends nothing — so there is no green row to commit after this section, and `git status --porcelain` is clean.
- The **first** post-commit run exited **1** on `[FAIL] reports/audit/INDEX.md is stale`. The index was generated before the last two wording edits in `103.2`/`103.4`, so it pinned `e8ca8e1e…` for a `volume2.md` whose committed bytes hash `dde9726d…`. The gate caught a real inconsistency rather than a text change; `INDEX.md` was regenerated, committed as `1b7633b`, and `generate_audit_index.py --check` now exits **0** with 103 section rows. No §N content changed in that commit — only the index's digest of it.
- The pre-commit `--force-full` run on the section's tree was green: **620/620** (619 parallel + 1 isolated), 0 skipped, 0 xfailed, **11/11** verifiers, 1,009 current manifest artifacts matching, and it appended nothing because the working tree's `HEAD` tree was already recorded.
