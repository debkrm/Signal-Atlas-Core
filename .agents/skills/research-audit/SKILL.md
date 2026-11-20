---
name: research-audit
description: Audit a pre-registered strategy trial round for Signal-Atlas-Core — verify the process (pre-registration ordering, thresholds unchanged, no out-of-window data, trial accounting), attack the data QA, and recompute the verdict independently. Use when asked to audit a research round, a seq N trial result, or a feat-s tag that contains a strategy evaluation.
---

# Audit one research round

Use `audit-round` for structure (baseline, per-finding status, verdict, work order, falsifier,
append-only section). This skill adds what is specific to a strategy result. Audit the commit the tag
names, never the working tree. Do not read the implementor's work log until after you have
measured the items below; compare afterward. Audit section numbers run one behind the tag ordinal
(audit §N audits the round tagged feat-s(N+1)); confirm the next number from the volume's last section.

## 1. Process integrity (these decide whether the result is evidence at all)

- Ancestry: `git merge-base --is-ancestor <prereg-sha> <code-sha>` and `... <results-sha>`.
  The pre-registration commit must precede strategy code and results.
- Immutability: `git diff <prereg-sha> <tag> -- <prereg files>` must be empty, or every change must be
  a new commit that names the original SHA and landed before any P&L existed. Any threshold, window,
  seed, or definition change after P&L = process failure. For each amendment ask: is it a definition
  (allowed) or a threshold or window (not allowed)? Does it loosen or tighten the gate?
- Pre-registration completeness: grep the pre-registration for "e.g.", "or", "TBD", "approximately".
  Each hit is an unpinned degree of freedom; name it. Check specifically that entry/exit interaction,
  tie-breaks, benchmark construction and QA tolerances are pinned.
- QA tolerances and parameters were committed BEFORE the artifact that uses them (compare commit
  times); then sweep the tolerance (for example 0.25x, 1x, 2x, 4x) and report what changes and whether
  any attestation is false.
- Single run: count the runs in the artifacts and logs. More than one requires a reported bug
  justification with both runs shown.
- Registry: read N and N_eval before and after from the registry itself; confirm the trial row's
  timestamp precedes the run's, and that the report's numbers match.

## 2. Leakage attacks (reproduce, don't read)

- Search every data-loading path touched by the commit for dates beyond the window end; then run the
  strategy with the data truncated one session before a signal and confirm the signal at T changes
  only when data <= T changes (shift test).
- Confirm no import or read of the 2024 fold or holdout paths, including via test fixtures, caches,
  and notebooks. Check file access, not only code that "looks" gated.
- Verify fills: every entry at T+1 open, every exit at the next open after its trigger, stops per the
  pre-registered rule. Pull five random trades from the ledger and recompute fill, cost and P&L by hand.
- Corporate actions: for each flagged QA event, confirm the resolution. Recompute the QA counts with
  YOUR OWN code, not the producer's functions (a check that calls the producer's code detects drift, not
  wrong logic). Any unattested step feeding a signal or its lookback window that the run proceeded past
  is a blocking finding.
- QA coverage: does it test both directions, the whole lookback window, cash dividends and rights, the
  exit and holding side, and does it publish the archive's coverage per instrument? Is every counter
  with absent input marked NOT RUN rather than 0?

## 3. Statistical validity

- Null: verify it uses the identical universe, liquidity filter, SMA/regime filter and exit mechanics,
  differs ONLY in the removed condition, and matches the entry count per the pre-registered scheme.
  Recompute its p05/median/p95 from the saved draws.
- Bootstrap: confirm resampling is by the pre-registered date block, with the seed, and recompute the
  interval.
- Benchmark: recompute the benchmark's Calmar for the identical window and cost assumptions; confirm
  the strategy's idle cash is treated as pre-registered; confirm the strategy and benchmark windows are
  the same calendar window and report the number of returns in each.
- Concentration: report how much P&L comes from the top 10 trades and from the single worst-clustered
  month. A GO resting on one episode is a residual even if every gate passes.

## 4. Verdict and artifact reproduction

- Run the result script's `--check` in a CLEAN CLONE (not the working copy) and recompute the gate
  table independently from the raw trade ledger and the pre-registered thresholds. The verdict string
  must match byte for byte. A verdict that cannot be recomputed is not a verdict.
- For every published digest, confirm what it hashes and that it equals the digest of the bytes git
  stores (line-ending dependence is a defect).
- Probes: tamper with the artifact and the source behind EACH probe and confirm it fails closed; check
  the probe module for duplicate or shadowed definitions and assertion-free probes.

## 5. What to write

In the `audit-round` section format, state separately: process verdict (1), leakage verdict (2),
statistical-validity verdict (3), and recomputed trial verdict (4). A process failure voids the trial
as evidence regardless of the numbers. Where your section corrects an earlier section of yours, say so
in a new paragraph; never edit the old one. Never soften a KILL into "more research needed" and never
turn a near-miss into a pass; thresholds are fixed. A KILL that is reproduced is a CLOSED finding for
that family, and the work order must say so and name what the maintainer must decide next, not propose a
new strategy yourself. End with what would falsify the verdict.
