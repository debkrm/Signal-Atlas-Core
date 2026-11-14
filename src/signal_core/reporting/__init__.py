"""
Signal Atlas Automated Reporting & Verdict Engine Package.
Implements fail-closed quantitative reporting, computed verdicts, and Go/No-Go criteria evaluation
per AGENTS.md §9 (Rule 9.1, 9.2, 9.3) and Phase 2D specifications.
"""

from signal_core.reporting.verdicts import (
    CriterionEvaluation,
    OverallVerdict,
    VerdictReport,
    VerdictStatus,
    evaluate_verdicts,
)

__all__ = [
    "CriterionEvaluation",
    "OverallVerdict",
    "VerdictReport",
    "VerdictStatus",
    "evaluate_verdicts",
]

