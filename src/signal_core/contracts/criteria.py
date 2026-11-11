"""Authoritative Research Go/No-Go Decision Criteria Contract & Loader.

Implements typed domain representations and parsing for committed quantitative criteria:
- Anti-overfitting thresholds (DSR, Haircut Sharpe, walk-forward stability)
- Risk and drawdown bounds
- Execution & liquidity constraints
- Effective-dated Indian statutory transaction cost schedule per NSE/SEBI circulars
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import yaml

DEFAULT_CRITERIA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "go_no_go_criteria.yaml"


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

    return GoNoGoCriteria(
        version=str(meta.get("version", "1.0.0")),
        effective_date=datetime.date.fromisoformat(str(meta.get("effective_date", "2026-11-11"))),
        market=str(meta.get("market", "NSE_CASH_EQUITY")),
        currency=str(meta.get("currency", "INR")),
        min_deflated_sharpe_ratio=_to_decimal(anti_ov["min_deflated_sharpe_ratio"], "min_deflated_sharpe_ratio"),
        min_haircut_sharpe_ratio=_to_decimal(anti_ov["min_haircut_sharpe_ratio"], "min_haircut_sharpe_ratio"),
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
    )
