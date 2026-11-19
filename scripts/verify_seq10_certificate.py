#!/usr/bin/env python3
"""
GATE VERIFIER — the seq-10 candidate certificate (§98.10 item 3)

Audit §98.4 measured that the certificate was a standing probe: nine verifiers were discovered by
`verify_audit_append_only.py`, none of them this one, so a criteria re-seal that forgot its restatement
left the gate green and refused only when a round remembered to run `probe_seq10_candidate.py`.

This file is the discovery hook. It runs the certificate unchanged and returns its exit status, so the
gate's W0.5-2 sweep requires zero from the same check a round runs by hand. It adds no assertion of its
own: duplicating the certificate here would be the two-paths defect §14.4 names.
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.probe_seq10_candidate as certificate  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(certificate.main())
