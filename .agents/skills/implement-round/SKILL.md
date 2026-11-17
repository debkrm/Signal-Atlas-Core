---
name: implement-round
description: Execute one audit work order for Signal-Atlas-Core as the implementing agent — read the latest audit section and the open findings, implement the ordered items without touching auditor-owned files, verify with the gate, and commit plus tag. Use when asked to implement a §N round, act on a work order, or continue the audit remediation loop.
---

# Implement one audit round

You are the **implementing agent**. The auditor's verdict is the contract; the work order inside it is
the task list. Nothing here authorises editing an auditor-owned document, moving a threshold, or
appending a trial.

## 1. Read the contract before touching a file

- Latest section: the last `## §N` in `reports/audit/volume2.md` (and volume 1 while it is the last
  one written). Read it whole — baseline table, per-finding status, verdicts, work order, and
  `What would falsify this verdict`.
- Open work: `reports/audit/findings.jsonl` — the **last row per id** is authoritative; `OPEN` rows and
  `ACCEPTED` residuals whose work item landed are the queue.
- `AGENTS.md` §11-§14 (role boundary, audit cadence, repository discipline, strategy scope) and the
  tail of `CURRENT_STAGE_OF_WORK.md`.

## 2. Hard boundaries — check them before every commit

| Never write | Never move |
|---|---|
| `reports/audit/signal_atlas_phase1c_audit_deepseek_review_.md` (frozen volume 1) | `data/trials/trial_registry.jsonl{,.evaluations}` (N = 9, N_eval = 5) |
| `reports/audit/volume2.md` and `reports/audit/findings.jsonl` (auditor-owned) | `validation_folds_count = 0` (2024 fold stays frozen) |
| `AGENTS.md` | Holdout `2025-01-01..2026-11-11` (`HOLDOUT_UNLOCK` stays absent) |

Never run seq 10 without an explicit instruction in the work order. Never re-record a green cache row,
relax a threshold, or add a skip/xfail to reach green (§12.4).

## 3. Implement, then make the probe fail closed

For each ordered item, the work order names the probe that must fail **before** the item is closed.
Write that probe first, watch it fail on the current tree, then fix the cause — not the guard beside
it. §14.4's recurring defect is the additive fix: a new guarded path while the old unguarded one stays
reachable. Measure at every existing consumer.

When a value is computed by the runtime (a fold count, a liquidated count), the producer must state
it; never hardcode a number a test wants to see.

## 4. Verify

```
python scripts/probe_audit_findings.py --list            # one probe per open finding
python scripts/verify_audit_findings.py                  # every ledger row executes
python scripts/verify_audit_append_only.py --force-full  # full gate: 0 skipped, 0 xfailed
```

Report exactly what ran. A check that could not run is reported as not run, never as passed (§9.3).

## 5. Record the round

Append a section to `CURRENT_STAGE_OF_WORK.md` that cites the audit section (`§N`) and the commit it
reviews, states the measurements actually taken, and says plainly that the work is **not audited**.
Status words (closed, verified, signed off) may appear only with the cited verdict that grants them
(§11.3).

## 6. Commit and tag

```
git status --porcelain                     # protected paths must be absent
git commit -m "<what changed and why>"     # no Co-Authored-By, no generated-with trailer (§12.7)
# The gate records green against a commit's tree, not against a working copy (§80.3, N-160), so the full
# run above recorded nothing. Run it once more on the committed tree and commit the single row it appends.
python scripts/verify_audit_append_only.py
git add data/reference/source_tree_green.json && git commit -m "Record the post-commit green source tree."
git tag feat-s<N>-$(git rev-parse --short HEAD)
```

Never amend, rebase or force-push `main` (§12.1). Then stop: the next round is the auditor's.
