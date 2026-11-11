"""
Standalone runner for Phase 2A containment and trial registry verification probe.
"""

from scripts.verify_phase2a_containment_and_trials import run_phase_2a_verification

if __name__ == "__main__":
    import sys
    success = run_phase_2a_verification()
    sys.exit(0 if success else 1)
