"""
Standalone runner for Phase 2C strategy contract and walk-forward engine verification probe.
"""

from scripts.verify_phase2c_walkforward import run_phase_2c_verification

if __name__ == "__main__":
    import sys
    success = run_phase_2c_verification()
    sys.exit(0 if success else 1)
