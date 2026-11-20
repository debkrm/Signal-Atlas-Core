---
name: research-round
description: Execute one pre-registered strategy trial for Signal-Atlas-Core as the implementing agent — commit the pre-registration, run data QA, implement through the single engine, run exactly once, compute the verdict by script, and record the trial. Use when a maintainer task asks to implement and run a strategy family, a seq N trial, or a go/no-go evaluation. Not for audit remediation or data-hygiene rounds (use implement-round).
---

# Run one pre-registered trial

A research round is not an audit remediation. The maintainer's task is the contract; it names the
strategy, the window, and the decision rule. You do not tune, extend, or reinterpret any of them.
Everything in `implement-round` §2 (boundaries) still applies, except where this skill authorizes a
registry append.

## 0. Read, then surface ambiguity before committing anything

- The task, `AGENTS.md` (§5-§10 especially), `configs/go_no_go_criteria.yaml`, the tail of
  `CURRENT_STAGE_OF_WORK.md`, the latest audit section and the open findings in `findings.jsonl`.
- If an open finding concerns data, QA, benchmark or band coverage that this trial relies on, STOP and
  report it before pre-registering. A trial built on a known-open data defect is not evidence.
- Every rule the task leaves open (indicator seeding, ATR period, exit tie-breaks, portfolio caps,
  null draw count, bootstrap block size, QA tolerances) is a question for the maintainer BEFORE step 1.
  If you cannot ask, pick the narrowest conventional reading, write it into the pre-registration, and
  list it under `Assumptions` in the work log. Do not leave "e.g." or "or" in the pre-registration.

## 1. Pre-register (commit before any strategy code exists)

One commit containing ONLY: the trial config (`configs/trial_NNN_*.yaml`) and the decision-rule text.
It must pin: strategy id, signal, entry, exit, stop, max hold, sizing, costs, universe filter, window,
null definition, draw count and seed, bootstrap definition and seed, benchmark (its construction, its
window, and how any ISIN boundary is treated), every gate and threshold, the outcome rule (what GO and
KILL each mean, and that KILL stops the search), AND:
- how entry and exit conditions interact when both hold on the same session, and the tie-break when
  signals exceed slots or capital;
- every QA tolerance (for example the cash-dividend reproduction tolerance), stated before any count
  is derived from it.
- Record this commit hash in the work log. Never edit these files afterward. A mistake found before any
  P&L exists is corrected by a NEW commit that names the original SHA in its message and is reported as
  an amendment. A change after any P&L exists is a process failure, not an amendment.
- Do not modify `GoNoGoCriteria` or any fingerprint-bearing config. If the task needs one changed,
  stop and ask.
- Trial registry: register the trial through the existing tooling, one row, immediately before the
  run and only after the QA gate is CLEAR, unless the task says otherwise. A trial that stops at the QA
  gate is recorded in the work log as pre-registered and not run, and N is unchanged. If no tooling
  exists for the append, STOP and report; never hand-write registry rows.

## 2. Data QA before reading any P&L (counts and lists only)

- Flag every session in the window whose adjusted move exceeds the task's threshold, in BOTH
  directions, and every signal whose lookback window (SMA, RSI, ATR windows) contains such a step, not
  only the signal day. Check each against the corporate-action table, including cash dividends and
  rights (an ex-dividend session reprices; test by reproducing the level within the pre-registered
  tolerance, not by ratio shape alone).
- Publish what the evidence covers: how many instruments the corporate-action archive covers at all.
  "No record" is only evidence of "no action" where the archive covers the instrument.
- Count signals blocked by each filter (liquidity, series, circuit, warm-up). A counter whose input
  data is absent (for example no price-band files) is `NOT RUN`, never 0.
- Cover the exit and holding side as well as the entry (freezes, held-position corporate actions).
- State the actual first signal date after warm-up. If it differs from the window start, say so.
- If any unattested corporate-action or ISIN step feeds a signal or its window: STOP and report. Do not
  patch around it, exclude it silently, or proceed.
- The run script must READ the QA artifact and refuse to execute unless its status is CLEAR. Write a
  test for that refusal, and a probe that fails if a new execution path appears that does not consult it.
- Any digest you publish says what it hashes and reproduces from the bytes git stores. Test it in a
  clean clone, because line endings differ between working copies.

## 3. Implement through the single engine

- New strategy class in the existing strategy package (currently `src/signal_core/strategy/`; check the
  tree, do not assume), registered through the existing engine path. No second engine, no vectorized
  shortcut, no float in accounting (§7.4, §6.4).
- Tests first, watched failing: known-answer indicator test on a hand-computed series; no-lookahead
  (signal at T uses data <= T, fill at T+1); warm-up; exit timing; stop vs max-hold precedence; the
  entry/exit interaction rule; a date-ceiling test proving no code path loads data after the window end;
  the QA-gate refusal. When you replace a probe or test, delete the old definition; a later duplicate
  silently shadows an earlier one.
- Do not load, slice, count rows of, or log anything from the frozen fold or the sealed holdout.

## 4. Run exactly once

- One run of the strategy and one run of the null, with the seeds in the pre-registration.
- The verdict is produced by a script reading the computed numbers and the pre-registered thresholds.
  Write the result JSON with a `--check` mode that reproduces its bytes in a clean clone.
- If you find an implementation BUG after seeing results: fix it, rerun, report BOTH runs with the
  bug described, thresholds untouched. A rerun is for bugs only and is never a retry on a
  disappointing number. If unsure whether something is a bug or a tuning, report both and stop.
- No variants, sweeps, "quick checks", or sensitivity runs unless the pre-registration lists them.

## 5. Report

Work-log section marked `Not audited`, containing: pre-registration commit hash (and any amendment
hashes); trial-registry counts before and after, as read from the registry; every computed metric and
null statistic; the gate-by-gate table with the script's verdict string; the QA findings; assumptions
you made; limitations, including what favors the null and what favors the strategy; and, on KILL, the
single sentence the pre-registration prescribes. No status word (closed, verified, signed off) without
a cited audit verdict (§11.3). Do not propose follow-up variants or new families; that is the
maintainer's decision.

## 6. Close out

Run the repository's gate and commit sequence exactly as `implement-round` §4 and §6 describe. Tag by
explicit sha: `git tag feat-s<N>-<code-sha> <code-sha>`, after the green-row commit, so the tag names
the code commit. Never append more than ~40 lines to a file with a shell heredoc; write a scratch file,
then `cat >>` and verify the tail. Then stop.
