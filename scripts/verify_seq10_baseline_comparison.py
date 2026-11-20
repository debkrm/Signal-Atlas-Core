#!/usr/bin/env python3
"""
GATE VERIFIER — the s100 baseline comparison reproduces from the stored bytes (§101.12 item 1)

Audit §101.8 measured that `compare_seq10_baselines.py --check` exited 0 in the writing checkout and 1
on every clone that stores the blob's LF, and that the script was on no verifier's discovery path, so
the gate stayed green while the comparison failed outside one directory. This file is the discovery
hook: it runs the reproduction unchanged and returns its exit status, so the gate's W0.5-2 sweep
requires zero from the same check a round runs by hand. It adds no assertion of its own — duplicating
the comparison here would be the two-paths defect §14.4 names.
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.compare_seq10_baselines as comparison  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(comparison.main(["--check"]))
