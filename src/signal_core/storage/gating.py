"""
Gating Window Enforcement and Surveillance History Invariants.

Implements evaluation window restrictions per AGENTS.md Rule 10.8:
- No gating on unsimulatable history: A GO/NO-GO verdict may only be computed on sessions
  in which every required input exists: authoritative calendar, verified security identity,
  and surveillance state (GSM effective 14 Mar 2017, ASM effective 26 Mar 2018).
- Sessions prior to 2018-04-01 are warm-up only; metrics computed on them are strictly NOT RUN for gating.
- Gate G2B.5-7: No session before 2018-04-01 can reach a GO verdict.
"""

from dataclasses import dataclass
import datetime
from enum import Enum
from typing import Optional, Union

BINDING_EVALUATION_START_DATE = datetime.date(2022, 1, 3)


class GatingWindowValidationError(ValueError):
    """Raised when an evaluation window violates gating validity or attempts GO on warm-up data."""
    pass


class GatingWindowClassification(str, Enum):
    """Classification of evaluation windows according to surveillance data completeness."""
    BINDING_EVALUATION = "BINDING_EVALUATION"      # All sessions >= 2018-04-01; eligible for GO/NO-GO gating
    PRE_SURVEILLANCE_WARMUP = "PRE_SURVEILLANCE_WARMUP"  # Sessions < 2018-04-01; strictly warm-up, NOT RUN for gating


def classify_gating_window(
    start_date: datetime.date,
    end_date: datetime.date,
) -> GatingWindowClassification:
    """
    Classifies a date window based on the authoritative binding start date (2018-04-01).
    """
    if type(start_date) is not datetime.date:
        raise GatingWindowValidationError(f"start_date must be genuine datetime.date, got {type(start_date).__name__}")
    if type(end_date) is not datetime.date:
        raise GatingWindowValidationError(f"end_date must be genuine datetime.date, got {type(end_date).__name__}")
    if start_date > end_date:
        raise GatingWindowValidationError(f"start_date {start_date} cannot be after end_date {end_date}")

    if start_date < BINDING_EVALUATION_START_DATE:
        return GatingWindowClassification.PRE_SURVEILLANCE_WARMUP
    return GatingWindowClassification.BINDING_EVALUATION


def check_gating_verdict_eligibility(
    start_date: datetime.date,
    proposed_verdict: str,
) -> None:
    """
    Enforces Gate G2B.5-7: No session before 2018-04-01 can reach a GO verdict.
    Fails closed with GatingWindowValidationError if a GO verdict is attempted on warm-up history.
    """
    if type(start_date) is not datetime.date:
        raise GatingWindowValidationError(f"start_date must be genuine datetime.date, got {type(start_date).__name__}")

    clean_verdict = proposed_verdict.strip().upper()
    if start_date < BINDING_EVALUATION_START_DATE and clean_verdict in ("GO", "APPROVED", "PASS"):
        raise GatingWindowValidationError(
            f"Gate G2B.5-7 Violation: Cannot issue {clean_verdict} verdict for evaluation window starting {start_date}. "
            f"The binding evaluation window starts on {BINDING_EVALUATION_START_DATE}. "
            "Prior sessions lack authoritative surveillance history and are restricted to warm-up only; "
            "metrics computed on them must be classified as 'NOT RUN'."
        )


def resolve_gating_verdict(
    start_date: datetime.date,
    computed_verdict: str,
) -> str:
    """
    Resolves the final gating verdict:
    If start_date < 2018-04-01, forces 'NOT RUN' for warm-up history.
    Otherwise preserves computed_verdict.
    """
    if type(start_date) is not datetime.date:
        raise GatingWindowValidationError(f"start_date must be genuine datetime.date, got {type(start_date).__name__}")

    if start_date < BINDING_EVALUATION_START_DATE:
        return "NOT RUN"
    return computed_verdict.strip().upper()

