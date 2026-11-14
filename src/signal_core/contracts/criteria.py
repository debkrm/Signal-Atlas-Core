"""Authoritative Research Go/No-Go Decision Criteria Contract & Loader.

Implements typed domain representations and parsing for committed quantitative criteria:
- Anti-overfitting thresholds (DSR, Haircut Sharpe, walk-forward stability)
- Risk and drawdown bounds
- Execution & liquidity constraints
- Effective-dated Indian statutory transaction cost schedule per NSE/SEBI circulars
"""

from dataclasses import dataclass, fields, is_dataclass
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import yaml

DEFAULT_CRITERIA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "go_no_go_criteria.yaml"
CRITERIA_FINGERPRINT_PREFIX = "CRIT-FPR-V1-"


class CriteriaValidationError(ValueError):
    """Raised when criteria configuration violates structure or numeric invariants."""
    pass


def _to_decimal(val: Any, field_name: str) -> Decimal:
    if val is None:
        raise CriteriaValidationError(f"Missing required criteria field '{field_name}'.")
    if isinstance(val, bool):
        raise CriteriaValidationError(f"Field '{field_name}' cannot be boolean.")
    if isinstance(val, float):
        raise CriteriaValidationError(f"Field '{field_name}' cannot be float in criteria config. String-typed decimal required.")
    try:
        d = Decimal(str(val))
    except Exception as exc:
        raise CriteriaValidationError(f"Invalid decimal for '{field_name}': {val!r}") from exc
    if not d.is_finite():
        raise CriteriaValidationError(f"Field '{field_name}' must be finite: {val!r}")
    return d


@dataclass(frozen=True, slots=True)
class EffectiveDatedExchangeFee:
    """Represents an effective-dated historical NSE exchange and IPFT fee schedule."""
    circular_ref: str
    from_date: datetime.date
    to_date: Optional[datetime.date]
    exchange_turnover_rate: Decimal
    ipft_rate: Decimal
    description: str

    def is_applicable(self, query_date: datetime.date) -> bool:
        if query_date < self.from_date:
            return False
        if self.to_date is not None and query_date > self.to_date:
            return False
        return True


@dataclass(frozen=True, slots=True)
class StatutoryCostCriteria:
    """Full statutory Indian transaction cost and tax schedule."""
    stt_delivery_rate: Decimal
    stt_intraday_sell_rate: Decimal
    sebi_turnover_charge_rate: Decimal
    stamp_duty_delivery_buy_rate: Decimal
    stamp_duty_intraday_buy_rate: Decimal
    gst_rate: Decimal
    brokerage_per_order_inr: Decimal
    gst_taxable_base_components: Tuple[str, ...]
    effective_dated_exchange_fees: Tuple[EffectiveDatedExchangeFee, ...]

    def get_exchange_fee_for_date(self, trade_date: datetime.date) -> EffectiveDatedExchangeFee:
        """Resolves the governing circular and rates for a specific trading session."""
        for fee_period in self.effective_dated_exchange_fees:
            if fee_period.is_applicable(trade_date):
                return fee_period
        raise CriteriaValidationError(
            f"No governing NSE exchange fee schedule found for trade date {trade_date}."
        )


@dataclass(frozen=True, slots=True)
class GoNoGoCriteria:
    """Immutable authoritative threshold model committed per AGENTS.md Rule 9.2."""
    version: str
    effective_date: datetime.date
    market: str
    currency: str

    # Anti-overfitting & significance
    min_deflated_sharpe_ratio: Decimal
    min_haircut_sharpe_ratio: Decimal
    dsr_trial_count_basis: str
    dsr_sharpe_variance_divisor: str
    sessions_per_year: int
    kurtosis_convention: str
    haircut_variant: str
    min_total_trades: int
    max_annual_turnover: Decimal
    min_positive_walk_forward_fold_ratio: Decimal

    # Risk & drawdown limits
    max_portfolio_drawdown: Decimal
    max_drawdown_duration_sessions: int
    min_profit_factor: Decimal
    max_single_position_weight: Decimal

    # Execution & liquidity realism
    max_volume_participation_cap: Decimal
    min_daily_turnover_crore: Decimal
    prohibit_buy_at_upper_circuit: bool
    prohibit_sell_at_lower_circuit: bool
    min_execution_latency_sessions: int

    # Statutory cost schedule
    statutory_costs: StatutoryCostCriteria

    # Market data and accounting invariants (§10.8, Audit §40.5, Finding H-54, H-61, H-62, H-64)
    min_binding_evaluation_start_date: datetime.date = datetime.date(2022, 1, 3)
    min_traded_eq_resolution_pct: Decimal = Decimal("100.0")
    # H-64: calendar fingerprint pinned as human anchor independent of the calendar file (Finding H-64)
    # CAL-FPR-V1 covers dates, session_types, open/close times of all 2,935 sessions — recomputed from
    # session_records at load time and compared against this pin; a date swap passes counting but not identity.
    expected_calendar_fingerprint: str = ""
    # R-4: calendar fingerprint pinned for the 1,196 sourced sessions in binding window 2022-01-03..2026-10-31
    expected_sourced_window_calendar_fingerprint: str = ""
    expected_baseline_calendar_sessions: int = 1201
    expected_authoritative_calendar_sessions: int = 1196
    expected_total_calendar_sessions: int = 2935
    authorized_unarchived_special_sessions: Tuple[str, ...] = ("2025-02-01",)
    authorized_calendar_holiday_exclusions: Tuple[str, ...] = (
        "2025-10-22",
        "2026-01-15",
        "2026-03-26",
        "2026-03-31",
        "2026-05-28",
        "2026-06-26",
        "2026-09-14",
    )
    authorized_calendar_trading_inclusions: Tuple[str, ...] = (
        "2026-03-20",
        "2026-05-27",
    )


def load_go_no_go_criteria(path: Optional[Union[str, Path]] = None) -> GoNoGoCriteria:
    """
    Loads and validates the committed Go/No-Go criteria YAML file into typed immutable contracts.
    Fails closed if thresholds or effective-dated schedules are missing.
    """
    file_path = Path(path) if path else DEFAULT_CRITERIA_PATH
    if not file_path.is_file():
        raise FileNotFoundError(f"Go/No-Go criteria configuration not found at: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise CriteriaValidationError(f"Invalid YAML content in {file_path}. Must be a dictionary.")

    meta = data.get("metadata", {})
    anti_ov = data.get("anti_overfitting_and_significance", {})
    risk = data.get("risk_and_drawdown_limits", {})
    exec_liq = data.get("execution_and_liquidity_realism", {})
    costs_raw = data.get("statutory_indian_cost_schedule", {})

    # Parse effective-dated fee periods
    raw_periods = costs_raw.get("effective_dated_exchange_fees", [])
    fee_periods: List[EffectiveDatedExchangeFee] = []
    for p in raw_periods:
        fee_periods.append(
            EffectiveDatedExchangeFee(
                circular_ref=str(p["circular_ref"]),
                from_date=datetime.date.fromisoformat(str(p["from_date"])),
                to_date=datetime.date.fromisoformat(str(p["to_date"])) if p.get("to_date") else None,
                exchange_turnover_rate=_to_decimal(p["exchange_turnover_rate"], "exchange_turnover_rate"),
                ipft_rate=_to_decimal(p["ipft_rate"], "ipft_rate"),
                description=str(p.get("description", "")),
            )
        )

    costs = StatutoryCostCriteria(
        stt_delivery_rate=_to_decimal(costs_raw["stt_delivery_rate"], "stt_delivery_rate"),
        stt_intraday_sell_rate=_to_decimal(costs_raw["stt_intraday_sell_rate"], "stt_intraday_sell_rate"),
        sebi_turnover_charge_rate=_to_decimal(costs_raw["sebi_turnover_charge_rate"], "sebi_turnover_charge_rate"),
        stamp_duty_delivery_buy_rate=_to_decimal(costs_raw["stamp_duty_delivery_buy_rate"], "stamp_duty_delivery_buy_rate"),
        stamp_duty_intraday_buy_rate=_to_decimal(costs_raw["stamp_duty_intraday_buy_rate"], "stamp_duty_intraday_buy_rate"),
        gst_rate=_to_decimal(costs_raw["gst_rate"], "gst_rate"),
        brokerage_per_order_inr=_to_decimal(costs_raw["brokerage_per_order_inr"], "brokerage_per_order_inr"),
        gst_taxable_base_components=tuple(costs_raw.get("gst_taxable_base_components", [])),
        effective_dated_exchange_fees=tuple(fee_periods),
    )

    # Validate anti-overfitting methodology constants
    sessions_raw = anti_ov.get("sessions_per_year", 250)
    if isinstance(sessions_raw, bool) or not isinstance(sessions_raw, int) or sessions_raw <= 0:
        raise CriteriaValidationError(f"sessions_per_year must be a positive integer, got {sessions_raw!r}")
    sessions_per_year = sessions_raw

    kurtosis_conv = str(anti_ov.get("kurtosis_convention", "RAW_NORMAL_THREE")).strip()
    if kurtosis_conv not in ("RAW_NORMAL_THREE", "EXCESS_NORMAL_ZERO"):
        raise CriteriaValidationError(f"Unsupported kurtosis_convention: {kurtosis_conv!r}")

    haircut_var = str(anti_ov.get("haircut_variant", "BONFERRONI")).strip()
    if haircut_var not in ("BONFERRONI", "HOLM", "BHY"):
        raise CriteriaValidationError(f"Unsupported haircut_variant: {haircut_var!r}")

    dsr_n_basis = str(anti_ov.get("dsr_trial_count_basis", "TOTAL_ATTEMPTED_TRIALS")).strip()
    if dsr_n_basis not in ("TOTAL_ATTEMPTED_TRIALS", "EVALUATED_TRIALS"):
        raise CriteriaValidationError(f"Unsupported dsr_trial_count_basis: {dsr_n_basis!r}")

    dsr_var_div = str(anti_ov.get("dsr_sharpe_variance_divisor", "EVALUATED_TRIALS_MINUS_ONE")).strip()
    if dsr_var_div != "EVALUATED_TRIALS_MINUS_ONE":
        raise CriteriaValidationError(
            f"Unsupported dsr_sharpe_variance_divisor: {dsr_var_div!r}. "
            f"Must be 'EVALUATED_TRIALS_MINUS_ONE'."
        )

    # N-51: All pinned calendar identity invariants are MANDATORY — missing key fails closed, no silent fallback.
    mda = data.get("market_data_and_accounting_invariants", {})

    def _require_mda(key: str) -> Any:
        if key not in mda:
            raise CriteriaValidationError(
                f"Mandatory pinned invariant '{key}' is absent from "
                f"market_data_and_accounting_invariants in {file_path}. "
                f"All calendar identity pins are required; there is no silent default (Note N-51)."
            )
        return mda[key]

    # expected_calendar_fingerprint must be present and non-empty (Finding H-64)
    raw_fingerprint = _require_mda("expected_calendar_fingerprint")
    if not isinstance(raw_fingerprint, str) or not raw_fingerprint.startswith("CAL-FPR-V1-"):
        raise CriteriaValidationError(
            f"expected_calendar_fingerprint must be a CAL-FPR-V1-... string, got {raw_fingerprint!r} (Finding H-64)"
        )

    # expected_sourced_window_calendar_fingerprint must be present and non-empty (Residual R-4)
    raw_sourced_fingerprint = _require_mda("expected_sourced_window_calendar_fingerprint")
    if not isinstance(raw_sourced_fingerprint, str) or not raw_sourced_fingerprint.startswith("CAL-FPR-V1-"):
        raise CriteriaValidationError(
            f"expected_sourced_window_calendar_fingerprint must be a CAL-FPR-V1-... string, got {raw_sourced_fingerprint!r} (Residual R-4)"
        )

    return GoNoGoCriteria(
        version=str(meta.get("version", "1.0.0")),
        effective_date=datetime.date.fromisoformat(str(meta.get("effective_date", "2026-11-11"))),
        market=str(meta.get("market", "NSE_CASH_EQUITY")),
        currency=str(meta.get("currency", "INR")),
        min_deflated_sharpe_ratio=_to_decimal(anti_ov["min_deflated_sharpe_ratio"], "min_deflated_sharpe_ratio"),
        min_haircut_sharpe_ratio=_to_decimal(anti_ov["min_haircut_sharpe_ratio"], "min_haircut_sharpe_ratio"),
        dsr_trial_count_basis=dsr_n_basis,
        dsr_sharpe_variance_divisor=dsr_var_div,
        sessions_per_year=sessions_per_year,
        kurtosis_convention=kurtosis_conv,
        haircut_variant=haircut_var,
        min_total_trades=int(anti_ov["min_total_trades"]),
        max_annual_turnover=_to_decimal(anti_ov["max_annual_turnover"], "max_annual_turnover"),
        min_positive_walk_forward_fold_ratio=_to_decimal(anti_ov["min_positive_walk_forward_fold_ratio"], "min_positive_walk_forward_fold_ratio"),
        max_portfolio_drawdown=_to_decimal(risk["max_portfolio_drawdown"], "max_portfolio_drawdown"),
        max_drawdown_duration_sessions=int(risk["max_drawdown_duration_sessions"]),
        min_profit_factor=_to_decimal(risk["min_profit_factor"], "min_profit_factor"),
        max_single_position_weight=_to_decimal(risk["max_single_position_weight"], "max_single_position_weight"),
        max_volume_participation_cap=_to_decimal(exec_liq["max_volume_participation_cap"], "max_volume_participation_cap"),
        min_daily_turnover_crore=_to_decimal(exec_liq["min_daily_turnover_crore"], "min_daily_turnover_crore"),
        prohibit_buy_at_upper_circuit=bool(exec_liq["prohibit_buy_at_upper_circuit"]),
        prohibit_sell_at_lower_circuit=bool(exec_liq["prohibit_sell_at_lower_circuit"]),
        min_execution_latency_sessions=int(exec_liq["min_execution_latency_sessions"]),
        statutory_costs=costs,
        min_binding_evaluation_start_date=datetime.date.fromisoformat(
            str(mda.get("min_binding_evaluation_start_date", "2022-01-03"))
        ),
        min_traded_eq_resolution_pct=_to_decimal(
            mda.get("min_traded_eq_resolution_pct", "100.0"),
            "min_traded_eq_resolution_pct",
        ),
        # H-64 / N-51: mandatory human-authored identity anchors — no defaults
        expected_calendar_fingerprint=raw_fingerprint,
        expected_sourced_window_calendar_fingerprint=raw_sourced_fingerprint,
        expected_baseline_calendar_sessions=int(_require_mda("expected_baseline_calendar_sessions")),
        expected_authoritative_calendar_sessions=int(_require_mda("expected_authoritative_calendar_sessions")),
        expected_total_calendar_sessions=int(_require_mda("expected_total_calendar_sessions")),
        authorized_unarchived_special_sessions=tuple(_require_mda("authorized_unarchived_special_sessions")),
        authorized_calendar_holiday_exclusions=tuple(_require_mda("authorized_calendar_holiday_exclusions")),
        authorized_calendar_trading_inclusions=tuple(_require_mda("authorized_calendar_trading_inclusions")),
    )

def _canonical_criteria_value(value: Any) -> Any:
    """Recursively converts typed criteria values to canonical JSON-compatible primitives."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CriteriaValidationError(f"Criteria values must be finite Decimals, got {value!r}")
        return str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, (bool, int, str)):
        return value
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return [_canonical_criteria_value(v) for v in value]
    if is_dataclass(value):
        return {f.name: _canonical_criteria_value(getattr(value, f.name)) for f in fields(value)}
    raise CriteriaValidationError(f"Unsupported type in criteria fingerprint: {type(value).__name__}")


def compute_criteria_fingerprint(criteria: GoNoGoCriteria) -> str:
    """
    Computes a deterministic content fingerprint of the criteria in force (Audit §33 H-39).

    A trial record must identify a run by the thresholds that judged it, not by a hand-maintained
    version string: editing a threshold without bumping `metadata.version` must change the
    fingerprint. Every field of GoNoGoCriteria is included, including the statutory cost schedule.
    """
    if not isinstance(criteria, GoNoGoCriteria):
        raise CriteriaValidationError(
            f"criteria must be GoNoGoCriteria, got {type(criteria).__name__}"
        )
    payload = _canonical_criteria_value(criteria)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return CRITERIA_FINGERPRINT_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

