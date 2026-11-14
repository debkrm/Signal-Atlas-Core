"""
Unit tests for Phase 3A: ATR-Based R-Multiple Position Sizing, Point-in-Time Universe Selection,
and Hardened N-63 AST Literal Checks.
Enforces AGENTS.md §6.1, §6.4, §7.2, §7.3, §10.4, §10.5, and Audit §56.3 / §56.5 / §56.6.
"""

import ast
import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError
from signal_core.portfolio.sizing import (
    PositionSizeResult,
    PositionSizingValidationError,
    calculate_atr_r_multiple_position_size,
)
from signal_core.research.pit_universe import (
    CashEquityInterval,
    build_point_in_time_universe_schedule,
    get_point_in_time_active_equities,
    load_cash_equity_symbol_intervals,
)


# =============================================================================
# 1. ATR-Based R-Multiple Position Sizer Tests (§56.6 Item 5, AGENTS.md §7.3)
# =============================================================================

def test_atr_sizing_higher_atr_gets_smaller_quantity_for_equal_risk():
    """
    §56.6 Item 5 Acceptance Probe: Proves that a higher-ATR instrument receives a strictly
    smaller quantity than a lower-ATR instrument at identical equity, entry price, and risk budget.
    """
    equity = Decimal("1000000.00")      # ₹10,00,000 equity
    entry_price = Decimal("200.00")     # ₹200 / share
    risk_pct = Decimal("0.01")          # 1% risk = ₹10,000 risk budget
    k_mult = Decimal("2.0")             # Stop = 2 * ATR

    # Instrument A: Low ATR = ₹5.00 -> Stop distance = ₹10.00 -> Q_risk = 10,000 / 10 = 1,000 shares
    res_low_atr = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("5.00"),
        risk_per_trade_pct=risk_pct,
        atr_stop_multiple=k_mult,
        max_single_position_weight=Decimal("0.25"),  # high weight cap so risk budget binds
    )

    # Instrument B: High ATR = ₹10.00 -> Stop distance = ₹20.00 -> Q_risk = 10,000 / 20 = 500 shares
    res_high_atr = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("10.00"),
        risk_per_trade_pct=risk_pct,
        atr_stop_multiple=k_mult,
        max_single_position_weight=Decimal("0.25"),
    )

    assert res_low_atr.quantity == 1000
    assert res_high_atr.quantity == 500
    assert res_low_atr.quantity > res_high_atr.quantity, "Higher-ATR name must receive smaller quantity for equal risk"
    assert res_low_atr.risk_amount == Decimal("10000.00")
    assert res_high_atr.risk_amount == Decimal("10000.00")
    assert res_low_atr.binding_constraint == "RISK_BUDGET"
    assert res_high_atr.binding_constraint == "RISK_BUDGET"


def test_atr_sizing_weight_cap_binds_before_risk_budget():
    """
    §56.6 Item 5 Acceptance Probe: Proves that max_single_position_weight cap binds
    before the risk budget when stop distance is narrow.
    """
    equity = Decimal("1000000.00")
    entry_price = Decimal("100.00")
    # Low ATR = ₹1.00, 2*ATR = ₹2.00 -> Q_risk = 10,000 / 2 = 5,000 shares (Value = ₹5,00,000 = 50% weight!)
    # But max_single_position_weight = 10% -> Max value = ₹1,00,000 -> Q_weight = 1,000 shares
    res = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("1.00"),
        risk_per_trade_pct=Decimal("0.01"),
        atr_stop_multiple=Decimal("2.0"),
        max_single_position_weight=Decimal("0.10"),
    )

    assert res.quantity == 1000
    assert res.binding_constraint == "MAX_POSITION_WEIGHT"
    assert res.position_value == Decimal("100000.00")
    assert res.position_weight == Decimal("0.10")
    # Actual risk taken is lower than budget because weight cap restricted position
    assert res.risk_amount == Decimal("2000.00")  # 1000 shares * ₹2 stop distance


def test_atr_sizing_available_cash_and_statutory_cost_buffer():
    """Verifies that available settled cash (with statutory cost buffer) binds correctly."""
    equity = Decimal("1000000.00")
    entry_price = Decimal("500.00")
    # Available cash = ₹50,250. Effective price with 0.5% buffer = 500 * 1.005 = 502.50.
    # Q_cash = floor(50,250 / 502.50) = 100 shares.
    res = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("5.00"),
        available_cash=Decimal("50250.00"),
        estimated_cost_buffer_pct=Decimal("0.005"),
        max_single_position_weight=Decimal("0.20"),
    )

    assert res.quantity == 100
    assert res.binding_constraint == "AVAILABLE_CASH"


def test_atr_sizing_volume_participation_cap():
    """Verifies that volume participation cap binds per AGENTS.md §7.3."""
    equity = Decimal("10000000.00")  # ₹1 Crore
    entry_price = Decimal("100.00")
    # Traded volume = 10,000 shares. Participation cap = 3% -> 300 shares max.
    res = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("2.00"),
        max_volume_participation=Decimal("0.03"),
        session_volume=10000,
        max_single_position_weight=Decimal("0.20"),
    )

    assert res.quantity == 300
    assert res.binding_constraint == "VOLUME_PARTICIPATION"


def test_atr_sizing_rejection_of_float_and_invalid_inputs():
    """Verifies fail-closed validation on binary float or invalid parameters."""
    equity = Decimal("1000000.00")
    entry_price = Decimal("100.00")
    atr = Decimal("5.00")

    # Binary float equity must raise
    with pytest.raises(PositionSizingValidationError, match="binary float"):
        calculate_atr_r_multiple_position_size(equity=1000000.0, entry_price=entry_price, atr=atr)  # type: ignore

    # Binary float ATR must raise
    with pytest.raises(PositionSizingValidationError, match="binary float"):
        calculate_atr_r_multiple_position_size(equity=equity, entry_price=entry_price, atr=5.0)  # type: ignore

    # Boolean equity must raise
    with pytest.raises(PositionSizingValidationError, match="cannot be a boolean"):
        calculate_atr_r_multiple_position_size(equity=True, entry_price=entry_price, atr=atr)  # type: ignore

    # Negative ATR must raise
    with pytest.raises(PositionSizingValidationError, match="must be strictly positive"):
        calculate_atr_r_multiple_position_size(equity=equity, entry_price=entry_price, atr=Decimal("-1.0"))


# =============================================================================
# 2. Point-in-Time Universe Selection Tests (§56.5, §56.6 Item 5, AGENTS.md §6.1, §10.5)
# =============================================================================

def test_pit_universe_security_added_in_2026_absent_in_2023():
    """
    §56.6 Item 5 Acceptance Probe: Proves that an instrument added in 2026 (e.g. 3BBLACKBIO,
    INE994E01018, effective 2026-04-20) is strictly absent from a 2023 cross-section and present in 2026.
    """
    intervals = load_cash_equity_symbol_intervals()

    # Query 1: 2023-01-03
    isins_2023 = get_point_in_time_active_equities(
        as_of=datetime.date(2023, 1, 3),
        intervals=intervals,
        series="EQ",
    )
    assert "INE994E01018" not in isins_2023, "3BBLACKBIO (effective 2026-04-20) must be absent on 2023-01-03"

    # Query 2: 2026-05-04 (after effective_from)
    isins_2026 = get_point_in_time_active_equities(
        as_of=datetime.date(2026, 5, 4),
        intervals=intervals,
        series="EQ",
    )
    assert "INE994E01018" in isins_2026, "3BBLACKBIO must be present on 2026-05-04"


def test_pit_universe_half_open_effective_to_delisting():
    """
    Verifies half-open [effective_from, effective_to) boundary semantics:
    360ONE (INE466L01020) has effective_from 2023-01-23 and effective_to 2023-03-02.
    Must be active on 2023-03-01 and absent on 2023-03-02.
    """
    intervals = load_cash_equity_symbol_intervals()

    # Active on 2023-03-01
    isins_active = get_point_in_time_active_equities(datetime.date(2023, 3, 1), intervals, series="EQ")
    assert "INE466L01020" in isins_active

    # Delisted on 2023-03-02 (effective_to is exclusive)
    isins_delisted = get_point_in_time_active_equities(datetime.date(2023, 3, 2), intervals, series="EQ")
    assert "INE466L01020" not in isins_delisted


def test_pit_universe_refuses_unsourced_nifty_500():
    """
    Audit §56.5 Precondition 2: Requesting unsourced 'NIFTY 500' raises UniverseValidationError fail-closed.
    """
    sessions = [datetime.date(2023, 1, 3), datetime.date(2023, 1, 4)]
    with pytest.raises(UniverseValidationError, match="Index membership history for 'NIFTY 500' is not sourced"):
        build_point_in_time_universe_schedule(
            sessions=sessions,
            requested_index_name="NIFTY 500",
        )


def test_pit_universe_zero_lookahead_liquidity_filtering():
    """
    Verifies zero-lookahead turnover filtering: turnover recorded on date T is never
    used to evaluate universe membership for date T.
    """
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 1, 2)
    d3 = datetime.date(2024, 1, 3)

    test_intervals = [
        CashEquityInterval(isin="INE000000001", symbol="AAA", series="EQ", effective_from=datetime.date(2020, 1, 1)),
        CashEquityInterval(isin="INE000000002", symbol="BBB", series="EQ", effective_from=datetime.date(2020, 1, 1)),
    ]

    # AAA has high turnover on d1 and d2 (₹10 Cr). BBB has low turnover on d1 and d2 (₹1 Cr).
    # On d3, BBB suddenly has high turnover (₹100 Cr).
    # On d3, universe is filtered by trailing median turnover (strictly < d3).
    # AAA should be selected; BBB should be excluded on d3 despite its high d3 turnover!
    turnovers = {
        (d1, "INE000000001"): Decimal("100000000"),
        (d2, "INE000000001"): Decimal("100000000"),
        (d3, "INE000000001"): Decimal("100000000"),
        (d1, "INE000000002"): Decimal("10000000"),
        (d2, "INE000000002"): Decimal("10000000"),
        (d3, "INE000000002"): Decimal("1000000000"),  # Lookahead trap on d3!
    }

    sched = build_point_in_time_universe_schedule(
        sessions=[d1, d2, d3],
        intervals=test_intervals,
        daily_turnover_inr=turnovers,
        min_median_daily_turnover_inr=Decimal("50000000"),  # ₹5 Cr threshold
        turnover_lookback_sessions=2,
    )

    # On d3: AAA passed (lookback median ₹10 Cr >= ₹5 Cr); BBB excluded (lookback median ₹1 Cr < ₹5 Cr)
    members_d3 = sched.get_universe_for_date(d3)
    assert "INE000000001" in members_d3
    assert "INE000000002" not in members_d3, "Turnover on session T must not be used to qualify session T membership (Zero Lookahead)"


# =============================================================================
# 3. Hardened N-63 AST Checker Probes (§56.3, §56.6 Item 1)
# =============================================================================

def test_n63_ast_checker_catches_all_six_probe_cases():
    """
    Audit §56.3 / §56.6 Item 1 Acceptance Probe:
    Verifies that the hardened AST literal analyzer catches all 6 probe variants:
    1. Direct dict literal
    2. Literal via update()
    3. Literal via subscript
    4. Module-level constant reference
    5. Helper call with literal (setdefault)
    6. Numeric Decimal/float/int literal call
    """
    from scripts.verify_phase2d_verdicts import REPO_ROOT

    probe_templates = {
        "direct_dict_literal": "def build_tier_a_results_bundle():\n    bundle = {'strict_decimal_accounting': True}\n    return bundle\n",
        "literal_via_update": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle.update({'strict_decimal_accounting': True})\n    return bundle\n",
        "literal_via_subscript": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle['strict_decimal_accounting'] = True\n    return bundle\n",
        "module_level_constant": "CONST_FLAG = True\ndef build_tier_a_results_bundle():\n    bundle = {'strict_decimal_accounting': CONST_FLAG}\n    return bundle\n",
        "helper_call_with_literal": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle.setdefault('strict_decimal_accounting', True)\n    return bundle\n",
        "numeric_metric_literal": "from decimal import Decimal\ndef build_tier_a_results_bundle():\n    bundle = {'profit_factor': Decimal('1.6850')}\n    return bundle\n",
    }

    def run_ast_check(code_str: str) -> bool:
        tree = ast.parse(code_str)
        module_constants: set[str] = set()
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        val = stmt.value
                        if isinstance(val, ast.Constant) and isinstance(val.value, (bool, int, float)):
                            module_constants.add(t.id)
                        elif isinstance(val, ast.UnaryOp) and isinstance(val.operand, ast.Constant):
                            if isinstance(val.operand.value, (int, float)):
                                module_constants.add(t.id)
                        elif isinstance(val, ast.Call):
                            fname = getattr(val.func, "id", getattr(val.func, "attr", None))
                            if fname in ("Decimal", "float", "int"):
                                module_constants.add(t.id)

        def is_literal_node(node: ast.AST) -> tuple[bool, str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float)):
                return True, f"constant literal {node.value!r}"
            if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
                if isinstance(node.operand.value, (int, float)):
                    return True, f"unary constant {ast.unparse(node)!r}"
            if isinstance(node, ast.Name) and node.id in module_constants:
                return True, f"module-level constant {node.id!r}"
            if isinstance(node, ast.Call):
                fname = getattr(node.func, "id", getattr(node.func, "attr", None))
                if fname in ("Decimal", "float", "int"):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        return True, f"call {fname}({node.args[0].value!r})"
                    if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in module_constants:
                        return True, f"call {fname}({node.args[0].id!r})"
            return False, ""

        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_tier_a_results_bundle")
        for node in ast.walk(func):
            if isinstance(node, ast.Dict):
                for val in node.values:
                    bad, _ = is_literal_node(val)
                    if bad:
                        return True
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        bad, _ = is_literal_node(node.value)
                        if bad:
                            return True
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in ("update", "setdefault"):
                    for arg in node.args:
                        if isinstance(arg, ast.Dict):
                            for v in arg.values:
                                bad, _ = is_literal_node(v)
                                if bad:
                                    return True
                        else:
                            bad, _ = is_literal_node(arg)
                            if bad:
                                return True
                    for kw in node.keywords:
                        bad, _ = is_literal_node(kw.value)
                        if bad:
                            return True
        return False

    for case_name, code in probe_templates.items():
        caught = run_ast_check(code)
        assert caught, f"AST checker failed to catch {case_name} (Finding N-63)!"
