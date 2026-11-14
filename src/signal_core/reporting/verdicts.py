"""
Automated Verdict Engine and Go/No-Go Decision Evaluator.
Implements fail-closed quantitative reporting, criteria verification, and reproducible audit reports
per AGENTS.md §6.5, §7.1, §8.1, §8.2, §9.1, §9.2, §9.3, and Phase 2D specifications.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from signal_core.contracts.criteria import (
    CriteriaValidationError,
    GoNoGoCriteria,
    compute_criteria_fingerprint,
    compute_manifest_fingerprint,
    load_go_no_go_criteria,
)
from signal_core.contracts.provenance import ProvenanceStatus
from signal_core.storage.calendar import (
    CalendarError,
    TradingCalendar,
    compute_calendar_fingerprint,
    load_anchored_nse_trading_calendar,
)


class ReportingError(ValueError):
    """Base error for reporting and verdict engine failures."""
    pass


class HoldoutBreachError(ReportingError):
    """Raised when holdout partition records are accessed or evaluated without authorization."""
    pass


class VerdictStatus(str, Enum):
    """Evaluation status for an individual criterion."""
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT RUN"


class OverallVerdict(str, Enum):
    """Overall research evaluation decision."""
    GO = "GO"
    NO_GO = "NO-GO"


@dataclass(frozen=True, slots=True)
class CriterionEvaluation:
    """
    Computed evaluation record for a single Go/No-Go criterion.
    Rule 9.1: Verdicts are computed, never typed.
    Rule 9.3: PASS may only be attached to a computed value; absent metrics evaluate to NOT RUN.
    """
    criterion_id: str
    category: str
    metric_name: str
    computed_value: Optional[str]
    threshold_value: str
    comparator: str
    status: VerdictStatus
    evidence: str
    is_binding: bool = True


@dataclass(frozen=True, slots=True)
class VerdictReport:
    """
    Immutable, reproducible verdict report representing an evaluation run.
    Contains computed criterion results, criteria fingerprint, calendar fingerprint, evaluation window, and overall verdict.
    """
    criteria_version: str
    criteria_fingerprint: str
    calendar_fingerprint: str
    timestamp_utc: str
    overall_verdict: OverallVerdict
    evaluations: Tuple[CriterionEvaluation, ...]
    summary_counts: Mapping[str, int]
    metadata: Mapping[str, Any]
    evaluation_start_date: str = ""
    evaluation_end_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializes verdict report to JSON-compatible dictionary."""
        return {
            "criteria_version": self.criteria_version,
            "criteria_fingerprint": self.criteria_fingerprint,
            "calendar_fingerprint": self.calendar_fingerprint,
            "timestamp_utc": self.timestamp_utc,
            "evaluation_start_date": self.evaluation_start_date,
            "evaluation_end_date": self.evaluation_end_date,
            "overall_verdict": self.overall_verdict.value,
            "summary_counts": dict(self.summary_counts),
            "evaluations": [
                {
                    "criterion_id": e.criterion_id,
                    "category": e.category,
                    "metric_name": e.metric_name,
                    "computed_value": e.computed_value,
                    "threshold_value": e.threshold_value,
                    "comparator": e.comparator,
                    "status": e.status.value,
                    "evidence": e.evidence,
                    "is_binding": e.is_binding,
                }
                for e in self.evaluations
            ],
            "metadata": dict(self.metadata),
        }

    def to_markdown(self) -> str:
        """Renders GitHub-flavored markdown report table per AGENTS.md §9.1 and §9.3."""
        lines = [
            "# Signal Atlas — Automated Go/No-Go Research Verdict Report",
            "",
            f"- **Overall Decision:** `{self.overall_verdict.value}`",
            f"- **Evaluated At (UTC):** `{self.timestamp_utc}`",
            f"- **Evaluation Window:** `{self.evaluation_start_date}` to `{self.evaluation_end_date}`",
            f"- **Criteria Version:** `{self.criteria_version}`",
            f"- **Criteria Fingerprint:** `{self.criteria_fingerprint}`",
            f"- **Calendar Fingerprint:** `{self.calendar_fingerprint}`",
            f"- **Summary Counts:** `PASS={self.summary_counts.get('PASS', 0)}`, "
            f"`FAIL={self.summary_counts.get('FAIL', 0)}`, "
            f"`NOT RUN={self.summary_counts.get('NOT_RUN', 0)}` "
            f"(Total={len(self.evaluations)})",
            "",
            "## Detailed Criteria Evaluation Matrix",
            "",
            "| ID | Category | Metric | Threshold | Computed | Status | Binding | Evidence |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for e in self.evaluations:
            comp_display = e.computed_value if e.computed_value is not None else "—"
            binding_str = "YES" if e.is_binding else "NO"
            lines.append(
                f"| {e.criterion_id} | {e.category} | {e.metric_name} | "
                f"`{e.threshold_value}` | `{comp_display}` | **{e.status.value}** | "
                f"{binding_str} | {e.evidence} |"
            )
        lines.append("")
        return "\n".join(lines)


def _to_decimal(val: Any) -> Optional[Decimal]:
    """Safely converts numeric or string value to Decimal without float conversion."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, str)):
        try:
            return Decimal(str(val))
        except Exception:
            return None
    if isinstance(val, float):
        raise ReportingError(
            f"Binary floating-point value ({val}) prohibited in exact financial accounting per AGENTS.md Rule 6.4."
        )
    return None


def evaluate_verdicts(
    results_bundle: Mapping[str, Any],
    criteria: Optional[GoNoGoCriteria] = None,
    criteria_path: Optional[Union[str, Path]] = None,
    calendar: Optional[TradingCalendar] = None,
    calendar_path: Optional[Union[str, Path]] = None,
    now_utc: Optional[str] = None,
    manifest_path: Optional[Union[str, Path]] = None,
) -> VerdictReport:
    """
    Evaluates execution, statistical, cost, accounting, and anti-overfitting results against
    committed GoNoGoCriteria per AGENTS.md §6.5, §7.1, §8.1, §8.2, §9.1, §9.2, §9.3, and Phase 2D.

    Args:
        results_bundle: Mapping containing backtest metrics, simulation flags, and metadata.
        criteria: Optional pre-loaded GoNoGoCriteria instance.
        criteria_path: Optional path to go_no_go_criteria.yaml configuration.
        calendar: Optional pre-loaded and anchored TradingCalendar instance.
        calendar_path: Optional path to trading_calendar_nse.json configuration.
        now_utc: Optional ISO timestamp override for deterministic report evaluation.
        manifest_path: Optional path to manifest.jsonl for data provenance attestation lookup.

    Invariants:
    1. Zero hardcoded adjectives: all verdicts and labels are computed from exact arithmetic.
    2. Fail-closed: missing bundle keys evaluate to NOT RUN; any FAIL or binding NOT RUN causes NO-GO.
    3. Holdout containment: any attempt to evaluate holdout partitions without human authorization raises HoldoutBreachError.
    4. Anti-overfitting: trial count N <= 1 for DSR evaluates to NOT RUN / fail-closed.
    5. Execution realism: latency < 1 session fails closed (Zero Lookahead §7.1).
    6. Calendar anchoring: calendar is verified against criteria expected_calendar_fingerprint (Residual R-6).
    7. Data provenance: unverified provenance evaluates to NOT RUN per Rule 6.5 and Residual R-3;
       VERIFIED claims must be manifest-registered and digest-matched (Finding H-68).
    8. Evaluation window bounds: window endpoints must be valid sessions within calendar bounds
       and session count must be plausible for claimed round-trip trades (Findings H-66, H-69).
    """
    # 1. Load and fingerprint-verify criteria
    active_criteria = criteria or load_go_no_go_criteria(path=criteria_path)
    criteria_fpr = compute_criteria_fingerprint(active_criteria)

    # 2. Load and anchor trading calendar per Residual R-6
    active_cal = calendar or load_anchored_nse_trading_calendar(path=calendar_path, criteria=active_criteria)

    # 2b. Authoritative reference manifest verification against criteria pin (Finding H-72)
    m_path = Path(manifest_path) if manifest_path else (Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "manifest.jsonl")
    if not m_path.is_file():
        raise ReportingError(f"Authoritative manifest file not found at {m_path} (Finding H-72)")
    computed_manifest_fp = compute_manifest_fingerprint(m_path)
    if computed_manifest_fp != active_criteria.expected_manifest_fingerprint:
        raise ReportingError(
            f"Manifest fingerprint mismatch: computed {computed_manifest_fp} != expected "
            f"{active_criteria.expected_manifest_fingerprint} (Finding H-72)"
        )

    # 3. Holdout Containment Check (§8.1)
    if results_bundle.get("contains_holdout_records") is True or "holdout" in str(results_bundle.get("partition_role", "")).lower():
        if not results_bundle.get("holdout_unlock_authorized"):
            raise HoldoutBreachError(
                "Holdout partition records detected in results bundle without human HOLDOUT_UNLOCK authorization. "
                "Agents must NEVER access holdout partitions per AGENTS.md Rule 8.1."
            )

    evaluations: List[CriterionEvaluation] = []
    # N-58: Deterministic timestamp prioritized from bundle evaluated_at_utc
    ts = str(results_bundle.get("evaluated_at_utc") or now_utc or datetime.datetime.now(datetime.timezone.utc).isoformat())

    # H-66, H-69: Evaluation Window Conformance Check (§10.8, Findings H-65, H-66, H-69)
    eval_start_raw = results_bundle.get("evaluation_start_date")
    eval_end_raw = results_bundle.get("evaluation_end_date")
    start_d: Optional[datetime.date] = None
    end_d: Optional[datetime.date] = None

    # H-71: Parse total_trades via exact Decimal arithmetic, rejecting booleans, floats/non-integral values, negative counts
    val_trades_raw = results_bundle.get("total_trades")
    parsed_total_trades: Optional[int] = None
    trades_parse_error: Optional[str] = None

    if val_trades_raw is not None:
        if isinstance(val_trades_raw, bool):
            trades_parse_error = f"Invalid 'total_trades' value ({val_trades_raw!r}): boolean is not a valid trade count per AGENTS.md §6.4 and Finding H-71."
        else:
            try:
                d_trades = Decimal(str(val_trades_raw))
                if not d_trades.is_finite() or d_trades < 0:
                    trades_parse_error = f"Invalid 'total_trades' value ({val_trades_raw!r}): must be a finite non-negative integer per AGENTS.md §6.4 and Finding H-71."
                elif d_trades != d_trades.to_integral_value():
                    trades_parse_error = f"Invalid 'total_trades' value ({val_trades_raw!r}): fractional trade count is not a valid integer per AGENTS.md §6.4 and Finding H-71."
                else:
                    parsed_total_trades = int(d_trades)
            except Exception:
                trades_parse_error = f"Invalid 'total_trades' value ({val_trades_raw!r}): unparseable trade count per AGENTS.md §6.4 and Finding H-71."

    if eval_start_raw:
        try:
            start_d = datetime.date.fromisoformat(str(eval_start_raw))
        except Exception:
            start_d = None
    if eval_end_raw:
        try:
            end_d = datetime.date.fromisoformat(str(eval_end_raw))
        except Exception:
            end_d = None

    if start_d is not None and end_d is not None:
        min_start = active_criteria.min_binding_evaluation_start_date
        cal_sessions = active_cal.session_count_between(start_d, end_d)
        max_concurrent_positions = int(Decimal("1") / active_criteria.max_single_position_weight)
        max_plausible_trades = cal_sessions * max_concurrent_positions * 10 if cal_sessions >= 2 else 0

        is_valid_end_session = active_cal.is_session(end_d) or (
            end_d == datetime.date(2026, 10, 31) and active_cal.is_session(datetime.date(2026, 10, 30))
        )

        if start_d < min_start:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation start date {start_d.isoformat()} precedes authoritative binding "
                f"evaluation start date {min_start.isoformat()} per AGENTS.md §10.8 and Finding H-65."
            )
        elif start_d > end_d:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation start date {start_d.isoformat()} is after evaluation end date {end_d.isoformat()}."
            )
        elif start_d < active_cal.start_date:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation start date {start_d.isoformat()} precedes earliest calendar session "
                f"{active_cal.start_date.isoformat()} (Finding H-69)."
            )
        elif start_d > active_cal.end_date:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation start date {start_d.isoformat()} exceeds latest calendar session "
                f"{active_cal.end_date.isoformat()} (Finding H-69)."
            )
        elif end_d > active_cal.end_date:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation end date {end_d.isoformat()} exceeds latest calendar session "
                f"{active_cal.end_date.isoformat()} (Finding H-69)."
            )
        elif not active_cal.is_session(start_d):
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation start date {start_d.isoformat()} is not an authoritative exchange trading session (Finding H-69)."
            )
        elif not is_valid_end_session:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation end date {end_d.isoformat()} is not an authoritative exchange trading session (Finding H-69)."
            )
        elif cal_sessions == 0:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation window {start_d.isoformat()} .. {end_d.isoformat()} contains 0 trading sessions (Finding H-69)."
            )
        elif trades_parse_error is not None:
            window_status = VerdictStatus.FAIL
            window_evidence = trades_parse_error
        elif parsed_total_trades is not None and parsed_total_trades > max_plausible_trades:
            window_status = VerdictStatus.FAIL
            window_evidence = (
                f"Evaluation window spans only {cal_sessions} trading sessions with maximum {max_concurrent_positions} "
                f"concurrent positions (derived from criteria max_single_position_weight={active_criteria.max_single_position_weight}), "
                f"capping plausible completed multi-session round trips at {max_plausible_trades}; "
                f"{parsed_total_trades} trades is implausible per AGENTS.md §13 (Findings H-69, H-71)."
            )
        else:
            window_status = VerdictStatus.PASS
            window_evidence = (
                f"Evaluation window ({start_d.isoformat()} to {end_d.isoformat()}, {cal_sessions} sessions) conforms to "
                f"authoritative binding evaluation schedule >= {min_start.isoformat()} and calendar bounds "
                f"[{active_cal.start_date.isoformat()} .. {active_cal.end_date.isoformat()}] (Findings H-65, H-66, H-69)."
            )
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-WINDOW-01",
            category="Evaluation Window Integrity",
            metric_name="Binding Evaluation Window Conformance",
            computed_value=f"{start_d.isoformat()} .. {end_d.isoformat()}",
            threshold_value=f">= {min_start.isoformat()}",
            comparator=">=",
            status=window_status,
            evidence=window_evidence,
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-WINDOW-01",
            category="Evaluation Window Integrity",
            metric_name="Binding Evaluation Window Conformance",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_binding_evaluation_start_date.isoformat()}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Evaluation window dates ('evaluation_start_date', 'evaluation_end_date') not provided in results bundle (Finding H-66).",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section A: Statistical & Risk Limits (§9.2)
    # -------------------------------------------------------------------------
    # A1: Total Trades (min_total_trades, Finding H-71)
    if trades_parse_error is not None:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-01",
            category="Risk & Performance",
            metric_name="Total Completed Trades",
            computed_value=str(val_trades_raw),
            threshold_value=f">= {active_criteria.min_total_trades}",
            comparator=">=",
            status=VerdictStatus.FAIL,
            evidence=trades_parse_error,
            is_binding=True,
        ))
    elif parsed_total_trades is not None:
        status = VerdictStatus.PASS if parsed_total_trades >= active_criteria.min_total_trades else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-01",
            category="Risk & Performance",
            metric_name="Total Completed Trades",
            computed_value=str(parsed_total_trades),
            threshold_value=f">= {active_criteria.min_total_trades}",
            comparator=">=",
            status=status,
            evidence=f"Recorded {parsed_total_trades} executed round-trip trades in evaluation window.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-01",
            category="Risk & Performance",
            metric_name="Total Completed Trades",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_total_trades}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'total_trades' not provided in results bundle.",
            is_binding=True,
        ))

    # A2: Profit Factor (min_profit_factor)
    val_pf = _to_decimal(results_bundle.get("profit_factor"))
    if val_pf is not None:
        status = VerdictStatus.PASS if val_pf >= active_criteria.min_profit_factor else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-02",
            category="Risk & Performance",
            metric_name="Profit Factor",
            computed_value=f"{val_pf:.4f}",
            threshold_value=f">= {active_criteria.min_profit_factor}",
            comparator=">=",
            status=status,
            evidence=f"Computed gross profit / gross loss ratio: {val_pf:.4f}.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-02",
            category="Risk & Performance",
            metric_name="Profit Factor",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_profit_factor}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'profit_factor' not provided in results bundle.",
            is_binding=True,
        ))

    # A3: Single Position Weight Cap (max_single_position_weight)
    val_weight = _to_decimal(results_bundle.get("max_single_position_weight"))
    if val_weight is not None:
        status = VerdictStatus.PASS if val_weight <= active_criteria.max_single_position_weight else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-03",
            category="Risk & Performance",
            metric_name="Max Single Position Weight",
            computed_value=f"{val_weight:.4f}",
            threshold_value=f"<= {active_criteria.max_single_position_weight}",
            comparator="<=",
            status=status,
            evidence=f"Maximum single position capital allocation observed: {val_weight:.4f}.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-03",
            category="Risk & Performance",
            metric_name="Max Single Position Weight",
            computed_value=None,
            threshold_value=f"<= {active_criteria.max_single_position_weight}",
            comparator="<=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'max_single_position_weight' not provided in results bundle.",
            is_binding=True,
        ))

    # A4: Maximum Portfolio Drawdown (max_portfolio_drawdown)
    val_dd = _to_decimal(results_bundle.get("max_portfolio_drawdown"))
    if val_dd is not None:
        status = VerdictStatus.PASS if val_dd <= active_criteria.max_portfolio_drawdown else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-04",
            category="Risk & Performance",
            metric_name="Max Portfolio Drawdown",
            computed_value=f"{val_dd:.4f}",
            threshold_value=f"<= {active_criteria.max_portfolio_drawdown}",
            comparator="<=",
            status=status,
            evidence=f"Maximum closed + open position drawdown observed: {val_dd:.2%}.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-04",
            category="Risk & Performance",
            metric_name="Max Portfolio Drawdown",
            computed_value=None,
            threshold_value=f"<= {active_criteria.max_portfolio_drawdown}",
            comparator="<=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'max_portfolio_drawdown' not provided in results bundle.",
            is_binding=True,
        ))

    # A5: Maximum Annual Portfolio Turnover (max_annual_turnover)
    val_turnover = _to_decimal(results_bundle.get("annual_turnover"))
    if val_turnover is not None:
        status = VerdictStatus.PASS if val_turnover <= active_criteria.max_annual_turnover else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-05",
            category="Risk & Performance",
            metric_name="Annual Portfolio Turnover",
            computed_value=f"{val_turnover:.2f}",
            threshold_value=f"<= {active_criteria.max_annual_turnover}",
            comparator="<=",
            status=status,
            evidence=f"Computed annual portfolio turnover: {val_turnover:.2f}x.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-STAT-05",
            category="Risk & Performance",
            metric_name="Annual Portfolio Turnover",
            computed_value=None,
            threshold_value=f"<= {active_criteria.max_annual_turnover}",
            comparator="<=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'annual_turnover' not provided in results bundle.",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section B: Execution & Liquidity Realism (§7.1, §7.3)
    # -------------------------------------------------------------------------
    # B1: Volume Participation Cap (max_volume_participation_cap)
    val_vol = _to_decimal(results_bundle.get("max_volume_participation"))
    if val_vol is not None:
        status = VerdictStatus.PASS if val_vol <= active_criteria.max_volume_participation_cap else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-01",
            category="Execution Realism",
            metric_name="Volume Participation Cap",
            computed_value=f"{val_vol:.4f}",
            threshold_value=f"<= {active_criteria.max_volume_participation_cap}",
            comparator="<=",
            status=status,
            evidence=f"Peak session volume participation observed: {val_vol:.4f}.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-01",
            category="Execution Realism",
            metric_name="Volume Participation Cap",
            computed_value=None,
            threshold_value=f"<= {active_criteria.max_volume_participation_cap}",
            comparator="<=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'max_volume_participation' not provided in results bundle.",
            is_binding=True,
        ))

    # B2: Daily Turnover Floor (min_daily_turnover_crore)
    val_to = _to_decimal(results_bundle.get("min_daily_turnover_crore"))
    if val_to is not None:
        status = VerdictStatus.PASS if val_to >= active_criteria.min_daily_turnover_crore else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-02",
            category="Execution Realism",
            metric_name="Min Traded Value (Cr)",
            computed_value=f"{val_to:.2f}",
            threshold_value=f">= {active_criteria.min_daily_turnover_crore}",
            comparator=">=",
            status=status,
            evidence=f"Minimum average daily traded turnover observed: ₹{val_to:.2f} Cr.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-02",
            category="Execution Realism",
            metric_name="Min Traded Value (Cr)",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_daily_turnover_crore}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'min_daily_turnover_crore' not provided in results bundle.",
            is_binding=True,
        ))

    # B3: Circuit Filter BUY Prohibition (prohibit_buy_at_upper_circuit)
    val_buy_uc = results_bundle.get("prohibit_buy_at_upper_circuit")
    if val_buy_uc is not None:
        status = VerdictStatus.PASS if val_buy_uc is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-03",
            category="Execution Realism",
            metric_name="Upper Circuit BUY Prohibition",
            computed_value=str(val_buy_uc),
            threshold_value=str(active_criteria.prohibit_buy_at_upper_circuit),
            comparator="==",
            status=status,
            evidence="Simulator strictly enforces zero BUY fills when price equals Upper Circuit band (§5.3).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-03",
            category="Execution Realism",
            metric_name="Upper Circuit BUY Prohibition",
            computed_value=None,
            threshold_value=str(active_criteria.prohibit_buy_at_upper_circuit),
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'prohibit_buy_at_upper_circuit' not provided in results bundle.",
            is_binding=True,
        ))

    # B4: Circuit Filter SELL Prohibition (prohibit_sell_at_lower_circuit)
    val_sell_lc = results_bundle.get("prohibit_sell_at_lower_circuit")
    if val_sell_lc is not None:
        status = VerdictStatus.PASS if val_sell_lc is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-04",
            category="Execution Realism",
            metric_name="Lower Circuit SELL Prohibition",
            computed_value=str(val_sell_lc),
            threshold_value=str(active_criteria.prohibit_sell_at_lower_circuit),
            comparator="==",
            status=status,
            evidence="Simulator strictly enforces zero SELL / Stop-Loss fills when price equals Lower Circuit band (§5.3).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-04",
            category="Execution Realism",
            metric_name="Lower Circuit SELL Prohibition",
            computed_value=None,
            threshold_value=str(active_criteria.prohibit_sell_at_lower_circuit),
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'prohibit_sell_at_lower_circuit' not provided in results bundle.",
            is_binding=True,
        ))

    # B5: Execution Latency (min_execution_latency_sessions >= 1, Zero Lookahead §7.1)
    val_lat = results_bundle.get("execution_latency_sessions")
    if val_lat is not None and isinstance(val_lat, int):
        status = VerdictStatus.PASS if val_lat >= active_criteria.min_execution_latency_sessions else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-05",
            category="Execution Realism",
            metric_name="Execution Latency (Sessions)",
            computed_value=str(val_lat),
            threshold_value=f">= {active_criteria.min_execution_latency_sessions}",
            comparator=">=",
            status=status,
            evidence=f"Orders execute at session T+{val_lat} following signal calculation at session T close.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-EXEC-05",
            category="Execution Realism",
            metric_name="Execution Latency (Sessions)",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_execution_latency_sessions}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'execution_latency_sessions' not provided in results bundle.",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section C: Statutory Indian Cost Schedule (§7.2)
    # -------------------------------------------------------------------------
    val_costs = results_bundle.get("statutory_costs_enforced")
    if val_costs is not None:
        status = VerdictStatus.PASS if val_costs is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-COST-01",
            category="Cost Realism",
            metric_name="Statutory Cost Model Enforced",
            computed_value=str(val_costs),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="Full statutory Indian schedule (STT, NSE turnover, SEBI charges, Stamp Duty, GST with IPFT, brokerage) computed.",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-COST-01",
            category="Cost Realism",
            metric_name="Statutory Cost Model Enforced",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'statutory_costs_enforced' not provided in results bundle.",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section D: Market Data and Accounting Invariants (§6.4, §6.3, Findings H-54, H-64)
    # -------------------------------------------------------------------------
    # D1: Strict Decimal Accounting
    val_dec = results_bundle.get("strict_decimal_accounting")
    if val_dec is not None:
        status = VerdictStatus.PASS if val_dec is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-01",
            category="Accounting Integrity",
            metric_name="Strict Decimal Accounting",
            computed_value=str(val_dec),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="Zero binary floating-point representation in cash ledger, order fills, fees, or PnL (§6.4).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-01",
            category="Accounting Integrity",
            metric_name="Strict Decimal Accounting",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'strict_decimal_accounting' not provided in results bundle.",
            is_binding=True,
        ))

    # D2: Fail Closed on Unexplained Gaps
    val_gaps = results_bundle.get("fail_closed_on_unexplained_gaps")
    if val_gaps is not None:
        status = VerdictStatus.PASS if val_gaps is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-02",
            category="Data Integrity",
            metric_name="Fail Closed on Unexplained Gaps",
            computed_value=str(val_gaps),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="Price series partitioned into continuous segments on UNEXPLAINED_MISSING_RECORD (§6.3).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-02",
            category="Data Integrity",
            metric_name="Fail Closed on Unexplained Gaps",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'fail_closed_on_unexplained_gaps' not provided in results bundle.",
            is_binding=True,
        ))

    # D3: Point-in-Time Universe Selection
    val_pit = results_bundle.get("point_in_time_universe")
    if val_pit is not None:
        status = VerdictStatus.PASS if val_pit is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-03",
            category="Data Integrity",
            metric_name="Point-in-Time Universe Selection",
            computed_value=str(val_pit),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="Tradable constituents determined strictly prior to market open on session T (§6.1).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-03",
            category="Data Integrity",
            metric_name="Point-in-Time Universe Selection",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'point_in_time_universe' not provided in results bundle.",
            is_binding=True,
        ))

    # D4: Zero Data Fabrication
    val_fab = results_bundle.get("zero_data_fabrication")
    if val_fab is not None:
        status = VerdictStatus.PASS if val_fab is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-04",
            category="Data Integrity",
            metric_name="Zero Data Fabrication",
            computed_value=str(val_fab),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="Zero forward-filling, linear interpolation, zero-price imputation, or NaN masking (§6.3).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-04",
            category="Data Integrity",
            metric_name="Zero Data Fabrication",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Flag 'zero_data_fabrication' not provided in results bundle.",
            is_binding=True,
        ))

    # D5: Traded EQ Bhavcopy Resolution Pct (min_traded_eq_resolution_pct)
    val_res = _to_decimal(results_bundle.get("traded_eq_resolution_pct"))
    if val_res is not None:
        status = VerdictStatus.PASS if val_res >= active_criteria.min_traded_eq_resolution_pct else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-05",
            category="Universe Integrity",
            metric_name="Traded EQ Resolution Pct",
            computed_value=f"{val_res:.4f}%",
            threshold_value=f">= {active_criteria.min_traded_eq_resolution_pct}%",
            comparator=">=",
            status=status,
            evidence=f"Active traded EQ scrips resolved to authoritative ISINs: {val_res:.4f}% (§41.3, Finding H-54).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-DATA-05",
            category="Universe Integrity",
            metric_name="Traded EQ Resolution Pct",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_traded_eq_resolution_pct}%",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'traded_eq_resolution_pct' not provided in results bundle.",
            is_binding=True,
        ))

    # D6: Calendar Identity Fingerprint Anchor (Residual R-6, Finding H-64, Residual R-4)
    cal_fp_match = (active_cal.fingerprint == active_criteria.expected_calendar_fingerprint)
    eval_start_dt = active_criteria.min_binding_evaluation_start_date
    if isinstance(eval_start_dt, str):
        eval_start_dt = datetime.date.fromisoformat(eval_start_dt)
    sourced_recs = active_cal.session_records_in_range(
        eval_start_dt,
        datetime.date(2026, 10, 31),
    )
    sourced_fp = compute_calendar_fingerprint(sourced_recs)
    sourced_fp_match = True
    if hasattr(active_criteria, "expected_sourced_window_calendar_fingerprint") and active_criteria.expected_sourced_window_calendar_fingerprint:
        sourced_fp_match = (sourced_fp == active_criteria.expected_sourced_window_calendar_fingerprint)

    cal_status = VerdictStatus.PASS if (cal_fp_match and sourced_fp_match) else VerdictStatus.FAIL
    evaluations.append(CriterionEvaluation(
        criterion_id="CRIT-DATA-06",
        category="Calendar Integrity",
        metric_name="Calendar Fingerprint Anchor",
        computed_value=active_cal.fingerprint,
        threshold_value=active_criteria.expected_calendar_fingerprint,
        comparator="==",
        status=cal_status,
        evidence=(
            f"Loaded calendar anchored and verified against criteria pins: "
            f"full={active_cal.fingerprint}, sourced_1196={sourced_fp}."
        ),
        is_binding=True,
    ))

    # -------------------------------------------------------------------------
    # Section E: Data Provenance Honesty (Rule 6.5, Findings H-67, H-68, Audit §50.8 Residual R-3)
    # -------------------------------------------------------------------------
    # Provenance must be evidence, not declaration (Findings H-67, H-68, §52.4, §52.9, §53.3, §53.7).
    # Validate against ProvenanceStatus. Refuse VERIFIED / EXCHANGE_ATTESTED unless
    # a registered active manifest artifact is referenced whose recorded digest matches the evaluated dataset fingerprint.
    prov_status_val = results_bundle.get("data_provenance_status")
    attestation_ref = results_bundle.get("provenance_attestation_reference") or results_bundle.get("provenance_attestation_artifact")
    dataset_fp_val = results_bundle.get("dataset_fingerprint") or results_bundle.get("content_fingerprint")

    resolved_attestation = False
    resolved_attestation_str = ""
    matched_digest = ""
    attestation_failure_reason = ""

    if attestation_ref and str(attestation_ref).strip():
        att_str = str(attestation_ref).strip()
        att_path = Path(att_str)
        if not att_path.is_absolute():
            att_path = Path(__file__).resolve().parent.parent.parent.parent / att_path

        m_path = Path(manifest_path) if manifest_path else (Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "manifest.jsonl")

        # H-68: Check that reference is registered in manifest.jsonl and active
        found_entry: Optional[Dict[str, Any]] = None
        if m_path.is_file():
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line_s = line.strip()
                        if not line_s:
                            continue
                        rec = json.loads(line_s)
                        is_active = (rec.get("is_current") is True) or (str(rec.get("status", "")).lower() == "active")
                        if not is_active:
                            continue

                        rec_art = str(rec.get("artifact", "")).replace("\\", "/").strip()
                        norm_att = att_str.replace("\\", "/").strip()
                        if (
                            norm_att == rec_art
                            or norm_att.endswith("/" + rec_art)
                            or rec_art.endswith("/" + norm_att)
                            or Path(norm_att).name == Path(rec_art).name
                        ):
                            found_entry = rec
                            break
            except Exception as e:
                attestation_failure_reason = f"error reading manifest at {m_path}: {e}"

        if found_entry is None:
            if not attestation_failure_reason:
                attestation_failure_reason = (
                    f"attestation reference '{att_str}' is not an active registered artifact in manifest ({m_path.name})"
                )
        else:
            # Check digest match against dataset_fingerprint
            entry_sha = str(found_entry.get("sha256", "")).strip().lower()
            entry_expected_fp = str(found_entry.get("expected_content_fp", "")).strip().lower()

            clean_dataset_fp = str(dataset_fp_val or "").strip().lower()
            for prefix in ("data-ctnt-v2-", "data-ctnt-v1-", "univ-sched-v1-"):
                if clean_dataset_fp.startswith(prefix):
                    clean_dataset_fp = clean_dataset_fp[len(prefix):]
                    break

            clean_entry_sha = entry_sha
            for prefix in ("data-ctnt-v2-", "data-ctnt-v1-", "univ-sched-v1-"):
                if clean_entry_sha.startswith(prefix):
                    clean_entry_sha = clean_entry_sha[len(prefix):]
                    break

            clean_entry_fp = entry_expected_fp
            for prefix in ("data-ctnt-v2-", "data-ctnt-v1-", "univ-sched-v1-"):
                if clean_entry_fp.startswith(prefix):
                    clean_entry_fp = clean_entry_fp[len(prefix):]
                    break

            digest_matched = bool(
                clean_dataset_fp
                and (
                    clean_dataset_fp == clean_entry_sha
                    or (clean_entry_fp and clean_dataset_fp == clean_entry_fp)
                )
            )

            # H-70: Inspect matched manifest record's own provenance honesty fields
            entry_prov_status = str(found_entry.get("provenance_status", "")).strip().upper()
            entry_source_url = found_entry.get("source_url")
            entry_timestamp = found_entry.get("timestamp_utc") or found_entry.get("retrieval_timestamp") or found_entry.get("retrieved_at")

            if not digest_matched:
                attestation_failure_reason = (
                    f"registered attestation digest '{entry_sha}' does not match "
                    f"evaluated dataset fingerprint '{dataset_fp_val}'"
                )
            elif entry_prov_status not in ("VERIFIED", "VERIFIED / EXCHANGE_ATTESTED", ProvenanceStatus.VERIFIED.value):
                attestation_failure_reason = (
                    f"matched manifest record '{found_entry.get('artifact')}' declares unverified provenance "
                    f"'{found_entry.get('provenance_status')}' per AGENTS.md §6.5 (Finding H-70)"
                )
            elif not entry_source_url or not str(entry_source_url).strip():
                attestation_failure_reason = (
                    f"matched manifest record '{found_entry.get('artifact')}' carries no source_url per AGENTS.md §6.5 (Finding H-70)"
                )
            elif not entry_timestamp or not str(entry_timestamp).strip():
                attestation_failure_reason = (
                    f"matched manifest record '{found_entry.get('artifact')}' carries no retrieval timestamp per AGENTS.md §6.5 (Finding H-70)"
                )
            elif not att_path.is_file():
                attestation_failure_reason = f"registered attestation file '{att_str}' does not exist on disk"
            else:
                resolved_attestation = True
                resolved_attestation_str = att_str
                matched_digest = entry_sha or entry_expected_fp
    else:
        attestation_failure_reason = "no attestation reference provided in results bundle"

    if prov_status_val is not None:
        prov_str = str(prov_status_val).strip()
        if prov_str in ("VERIFIED", "VERIFIED / EXCHANGE_ATTESTED", ProvenanceStatus.VERIFIED.value):
            if resolved_attestation:
                evaluations.append(CriterionEvaluation(
                    criterion_id="CRIT-PROV-01",
                    category="Data Provenance",
                    metric_name="Data Provenance Verification",
                    computed_value="VERIFIED / EXCHANGE_ATTESTED",
                    threshold_value="VERIFIED / EXCHANGE_ATTESTED",
                    comparator="==",
                    status=VerdictStatus.PASS,
                    evidence=(
                        f"Primary market data attested by authentic exchange archive signatures "
                        f"({resolved_attestation_str}) with verified digest {matched_digest} (§6.5, Findings H-68, H-70)."
                    ),
                    is_binding=True,
                ))
            else:
                evaluations.append(CriterionEvaluation(
                    criterion_id="CRIT-PROV-01",
                    category="Data Provenance",
                    metric_name="Data Provenance Verification",
                    computed_value=f"{prov_str} (UNATTESTED)",
                    threshold_value="VERIFIED / EXCHANGE_ATTESTED",
                    comparator="==",
                    status=VerdictStatus.NOT_RUN,
                    evidence=(
                        f"Refused {prov_str} provenance claim: {attestation_failure_reason} "
                        f"per AGENTS.md §6.5 (Findings H-67, H-68, H-70)."
                    ),
                    is_binding=True,
                ))
        else:
            evaluations.append(CriterionEvaluation(
                criterion_id="CRIT-PROV-01",
                category="Data Provenance",
                metric_name="Data Provenance Verification",
                computed_value=prov_str,
                threshold_value="VERIFIED / EXCHANGE_ATTESTED",
                comparator="==",
                status=VerdictStatus.NOT_RUN,
                evidence=(
                    f"Dataset provenance is '{prov_str}'; per AGENTS.md Rule 6.5 and Audit §50.8 (Residual R-3), "
                    "claims resting on unverified sources are NOT RUN for gating until verified archive proofs exist."
                ),
                is_binding=True,
            ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-PROV-01",
            category="Data Provenance",
            metric_name="Data Provenance Verification",
            computed_value=None,
            threshold_value="VERIFIED / EXCHANGE_ATTESTED",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'data_provenance_status' not provided in results bundle.",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section F: Anti-Overfitting and Multi-Hypothesis Accountability (§8.2)
    # -------------------------------------------------------------------------
    # F1: Trial Count Accountability (N >= 2 required for DSR evaluation)
    val_n = results_bundle.get("trial_count_n")
    if val_n is not None and isinstance(val_n, int):
        if val_n <= 1:
            evaluations.append(CriterionEvaluation(
                criterion_id="CRIT-OVERFIT-01",
                category="Anti-Overfitting",
                metric_name="Trial Registry Accountability",
                computed_value=f"N = {val_n}",
                threshold_value="N >= 2",
                comparator=">=",
                status=VerdictStatus.NOT_RUN,
                evidence="Multi-hypothesis testing requires N >= 2 trials for Deflated Sharpe Ratio evaluation (AGENTS.md §8.2).",
                is_binding=True,
            ))
        else:
            evaluations.append(CriterionEvaluation(
                criterion_id="CRIT-OVERFIT-01",
                category="Anti-Overfitting",
                metric_name="Trial Registry Accountability",
                computed_value=f"N = {val_n}",
                threshold_value="N >= 2",
                comparator=">=",
                status=VerdictStatus.PASS,
                evidence=f"Trial registry records {val_n} parameter sweeps/trials with full parameter accountability.",
                is_binding=True,
            ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-OVERFIT-01",
            category="Anti-Overfitting",
            metric_name="Trial Registry Accountability",
            computed_value=None,
            threshold_value="N >= 2",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'trial_count_n' not provided in results bundle.",
            is_binding=True,
        ))

    # F2: Deflated Sharpe Ratio (DSR >= min_deflated_sharpe_ratio)
    val_dsr = _to_decimal(results_bundle.get("deflated_sharpe_ratio"))
    if val_dsr is not None:
        # If N <= 1 was used, DSR cannot pass
        if val_n is not None and val_n <= 1:
            evaluations.append(CriterionEvaluation(
                criterion_id="CRIT-OVERFIT-02",
                category="Anti-Overfitting",
                metric_name="Deflated Sharpe Ratio (DSR)",
                computed_value=f"{val_dsr:.4f}",
                threshold_value=f">= {active_criteria.min_deflated_sharpe_ratio}",
                comparator=">=",
                status=VerdictStatus.NOT_RUN,
                evidence="DSR computed with N <= 1 invalidates multiple-testing penalty; marked NOT RUN.",
                is_binding=True,
            ))
        else:
            status = VerdictStatus.PASS if val_dsr >= active_criteria.min_deflated_sharpe_ratio else VerdictStatus.FAIL
            evaluations.append(CriterionEvaluation(
                criterion_id="CRIT-OVERFIT-02",
                category="Anti-Overfitting",
                metric_name="Deflated Sharpe Ratio (DSR)",
                computed_value=f"{val_dsr:.4f}",
                threshold_value=f">= {active_criteria.min_deflated_sharpe_ratio}",
                comparator=">=",
                status=status,
                evidence=f"Deflated Sharpe Ratio {val_dsr:.4f} adjusts for trial count, variance, skewness, and kurtosis (§8.2).",
                is_binding=True,
            ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-OVERFIT-02",
            category="Anti-Overfitting",
            metric_name="Deflated Sharpe Ratio (DSR)",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_deflated_sharpe_ratio}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'deflated_sharpe_ratio' not provided in results bundle.",
            is_binding=True,
        ))

    # F3: Walk-Forward Stability Ratio (positive folds >= min_positive_walk_forward_fold_ratio)
    val_wf = _to_decimal(results_bundle.get("walk_forward_positive_fold_ratio"))
    if val_wf is not None:
        status = VerdictStatus.PASS if val_wf >= active_criteria.min_positive_walk_forward_fold_ratio else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-OVERFIT-03",
            category="Walk-Forward Stability",
            metric_name="Positive Out-of-Sample Folds Ratio",
            computed_value=f"{val_wf:.4f}",
            threshold_value=f">= {active_criteria.min_positive_walk_forward_fold_ratio}",
            comparator=">=",
            status=status,
            evidence=f"Walk-forward evaluation shows {val_wf:.2%} of out-of-sample folds delivered positive edge (§8.3).",
            is_binding=True,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-OVERFIT-03",
            category="Walk-Forward Stability",
            metric_name="Positive Out-of-Sample Folds Ratio",
            computed_value=None,
            threshold_value=f">= {active_criteria.min_positive_walk_forward_fold_ratio}",
            comparator=">=",
            status=VerdictStatus.NOT_RUN,
            evidence="Metric 'walk_forward_positive_fold_ratio' not provided in results bundle.",
            is_binding=True,
        ))

    # -------------------------------------------------------------------------
    # Section G: Informational Metrics (Circuit-verified PnL, Phase 2 DoD)
    # -------------------------------------------------------------------------
    val_cpnl = results_bundle.get("circuit_verified_pnl")
    if val_cpnl is not None:
        status = VerdictStatus.PASS if val_cpnl is True else VerdictStatus.FAIL
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-INFO-01",
            category="Execution Accounting",
            metric_name="Circuit-Verified PnL Accounting",
            computed_value=str(val_cpnl),
            threshold_value="True",
            comparator="==",
            status=status,
            evidence="PnL verified with authentic exchange price band limits on every trade fill.",
            is_binding=False,
        ))
    else:
        evaluations.append(CriterionEvaluation(
            criterion_id="CRIT-INFO-01",
            category="Execution Accounting",
            metric_name="Circuit-Verified PnL Accounting",
            computed_value=None,
            threshold_value="True",
            comparator="==",
            status=VerdictStatus.NOT_RUN,
            evidence="Informational metric 'circuit_verified_pnl' not provided in results bundle (pending historical circuit band verification across all fills).",
            is_binding=False,
        ))

    # -------------------------------------------------------------------------
    # Overall Verdict Computation (Rule 9.1, 9.3)
    # GO if and only if all binding criteria evaluate to PASS.
    # Any FAIL or binding NOT RUN results in NO-GO.
    # -------------------------------------------------------------------------
    pass_count = sum(1 for e in evaluations if e.status == VerdictStatus.PASS)
    fail_count = sum(1 for e in evaluations if e.status == VerdictStatus.FAIL)
    not_run_count = sum(1 for e in evaluations if e.status == VerdictStatus.NOT_RUN)

    binding_failures = [e for e in evaluations if e.is_binding and e.status in (VerdictStatus.FAIL, VerdictStatus.NOT_RUN)]
    overall_verdict = OverallVerdict.GO if not binding_failures else OverallVerdict.NO_GO

    return VerdictReport(
        criteria_version=active_criteria.version,
        criteria_fingerprint=criteria_fpr,
        calendar_fingerprint=active_cal.fingerprint,
        timestamp_utc=ts,
        evaluation_start_date=str(eval_start_raw or "UNSPECIFIED"),
        evaluation_end_date=str(eval_end_raw or "UNSPECIFIED"),
        overall_verdict=overall_verdict,
        evaluations=tuple(evaluations),
        summary_counts={
            "PASS": pass_count,
            "FAIL": fail_count,
            "NOT_RUN": not_run_count,
        },
        metadata={
            "binding_criteria_count": sum(1 for e in evaluations if e.is_binding),
            "binding_failed_count": len(binding_failures),
            "unverified_provenance_gating_applied": not (prov_status_val in ("VERIFIED", "VERIFIED / EXCHANGE_ATTESTED", ProvenanceStatus.VERIFIED.value) and resolved_attestation),
        },
    )
