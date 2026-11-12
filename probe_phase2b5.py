"""
Standalone runner for Phase 2B.5 market data ingestion and storage layer verification probe.
"""

from scripts.verify_phase2b5_storage import run_phase_2b5_verification

if __name__ == "__main__":
    import sys
    success = run_phase_2b5_verification()
    sys.exit(0 if success else 1)

