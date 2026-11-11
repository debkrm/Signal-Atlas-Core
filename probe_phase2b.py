"""
Standalone runner for Phase 2B statistical significance engine verification probe.
"""

from scripts.verify_phase2b_significance import run_phase_2b_verification

if __name__ == "__main__":
    import sys
    success = run_phase_2b_verification()
    sys.exit(0 if success else 1)

