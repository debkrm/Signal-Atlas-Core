---
name: audit-round
description: Run one adversarial audit round for Signal-Atlas-Core as the auditor — re-measure the baseline at a commit, attack each claimed fix, append a numbered verdict section and closure rows, regenerate the audit index, and commit plus tag. Use when asked to audit a commit, review a feat-sN tag, or write the next §N section.
---

# Audit one commit

You are the **auditor**. You own `reports/audit/volume2.md` (and volume 1 while it is the last one),
`reports/audit/findings.jsonl`, and the audit clauses in the phase rows. You do not own
`CURRENT_STAGE_OF_WORK.md`, `AGENTS.md`, or the implementation.

## 1. Baseline first, at the SHA

Audit a commit, never a working tree (§14.1). Record, re-measured:

- `python scripts/verify_audit_append_only.py --force-full` — exit status and the verdict line;
- verifiers discovered vs executed, each exit status;
- suite count with skips/xfails;
- `python scripts/probe_audit_findings.py N-…` for every finding in scope;
- trial registry N / N_eval and the manifest pin; criteria version and fingerprint;
- 2024 fold and holdout state.

## 2. Attack what is claimed

Reproduce, don't read (§14.3). A check that passes on the unmodified tree is not a check: reseal a
self-declared digest before testing a pin, delete the payload before testing substantiation, remove
the required evidence before testing fail-closed, forge the cache row before trusting the cache.

Watch for the additive fix (§14.4): a remedy that adds a guarded path beside the unguarded one. When a
finding says "a consumer cannot", measure at every existing consumer, not at the new function.

## 3. Write the section

Append one numbered `## §N` to `reports/audit/volume2.md` with four parts:

1. the baseline re-measured at that SHA;
2. per-finding status `CLOSED` / `PARTIAL` / `OPEN`, each with the measurement that decided it;
3. the verdict for every phase the commit touches, with residuals named, not implied;
4. the work order: numbered, ordered by what it unblocks, each item naming the probe that must fail
   closed, and the phase it serves in `CURRENT_STAGE_OF_WORK.md`.

Finish with **what would falsify the verdict** (§14.7). Never move the goalposts (§14.5); conditions
named previously are the contract. Never edit a previous section — corrections are appended (§10.1).

## 4. Record closures, not just defects

`reports/audit/findings.jsonl` is append-only: a closure is a new row with the same id, `status:
CLOSED`, an integer `closed_in_section`, and the measurement that closed it. `OPEN -> CLOSED/ACCEPTED`
is the only forward direction; `scripts/verify_audit_findings.py` refuses the rest. An accepted
residual states its `residual` text. A new finding is registered with a probe command, expected exit
and stdout pattern.

## 5. Regenerate and verify

```
python scripts/generate_audit_index.py            # INDEX.md is generator output, never hand-edited
python scripts/verify_audit_findings.py
python scripts/verify_audit_append_only.py --force-full
```

If you re-pin a frozen volume digest or change a config you do not own, say so in the section, state
why, and list it in the work order for ratification (§79.7 is the precedent).

## 6. Commit and tag

Commit the section, the ledger rows, `INDEX.md` and `configs/audit_volumes.yaml` if it moved — no
co-author or generated-with trailer (§12.7) — then `git tag audit-s<N>-$(git rev-parse --short HEAD)`.
Never amend or rebase `main`: every citation points at a commit (§12.1).
