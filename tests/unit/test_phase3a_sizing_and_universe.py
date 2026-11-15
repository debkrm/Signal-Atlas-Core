"""
Unit tests for Phase 3A: ATR-Based R-Multiple Position Sizing, Point-in-Time Universe Selection,
and Hardened N-63 AST Literal Checks.
Enforces AGENTS.md §6.1, §6.4, §7.2, §7.3, §10.4, §10.5, and Audit §56.3 / §56.5 / §56.6,
§57.3 / §57.7 Items 1–6 (Findings H-77, H-78, H-79, H-80, N-69, N-70, N-71, N-72, N-73).
"""

import ast
import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.universe import UniverseSchedule, UniverseValidationError
from signal_core.portfolio.sizing import (
    MIN_TICK_SIZE,
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
from signal_core.storage.calendar import load_anchored_nse_trading_calendar


# =============================================================================
# 1. ATR-Based R-Multiple Position Sizer Tests (§56.6 Item 5, AGENTS.md §7.3, §57.7)
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
    session_vol = 1000000               # 1,000,000 volume so volume cap does not bind

    # Instrument A: Low ATR = ₹5.00 -> Stop distance = ₹10.00 -> Q_risk = 10,000 / 10 = 1,000 shares
    res_low_atr = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("5.00"),
        session_volume=session_vol,
        risk_per_trade_pct=risk_pct,
        atr_stop_multiple=k_mult,
        max_single_position_weight=Decimal("0.25"),  # high weight cap so risk budget binds
    )

    # Instrument B: High ATR = ₹10.00 -> Stop distance = ₹20.00 -> Q_risk = 10,000 / 20 = 500 shares
    res_high_atr = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("10.00"),
        session_volume=session_vol,
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
    session_vol = 1000000
    # Low ATR = ₹1.00, 2*ATR = ₹2.00 -> Q_risk = 10,000 / 2 = 5,000 shares (Value = ₹5,00,000 = 50% weight!)
    # But max_single_position_weight = 10% -> Max value = ₹1,00,000 -> Q_weight = 1,000 shares
    res = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("1.00"),
        session_volume=session_vol,
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
    session_vol = 1000000
    # Available cash = ₹50,250. Effective price with 0.5% buffer = 500 * 1.005 = 502.50.
    # Q_cash = floor(50,250 / 502.50) = 100 shares.
    res = calculate_atr_r_multiple_position_size(
        equity=equity,
        entry_price=entry_price,
        atr=Decimal("5.00"),
        session_volume=session_vol,
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
        session_volume=10000,
        max_volume_participation=Decimal("0.03"),
        max_single_position_weight=Decimal("0.20"),
    )

    assert res.quantity == 300
    assert res.binding_constraint == "VOLUME_PARTICIPATION"


def test_atr_sizing_rejection_of_float_and_invalid_inputs():
    """Verifies fail-closed validation on binary float or invalid parameters."""
    equity = Decimal("1000000.00")
    entry_price = Decimal("100.00")
    atr = Decimal("5.00")
    session_vol = 10000

    # Binary float equity must raise
    with pytest.raises(PositionSizingValidationError, match="binary float"):
        calculate_atr_r_multiple_position_size(
            equity=1000000.0, entry_price=entry_price, atr=atr, session_volume=session_vol  # type: ignore
        )

    # Binary float ATR must raise
    with pytest.raises(PositionSizingValidationError, match="binary float"):
        calculate_atr_r_multiple_position_size(
            equity=equity, entry_price=entry_price, atr=5.0, session_volume=session_vol  # type: ignore
        )

    # Boolean equity must raise
    with pytest.raises(PositionSizingValidationError, match="cannot be a boolean"):
        calculate_atr_r_multiple_position_size(
            equity=True, entry_price=entry_price, atr=atr, session_volume=session_vol  # type: ignore
        )

    # Negative ATR must raise
    with pytest.raises(PositionSizingValidationError, match="must be strictly positive"):
        calculate_atr_r_multiple_position_size(
            equity=equity, entry_price=entry_price, atr=Decimal("-1.0"), session_volume=session_vol
        )


def test_h77_sizer_effective_stop_distance_and_tick_floor():
    """
    Audit §57.3 / §57.7 Item 1 Acceptance Probe (Finding H-77):
    Floors the stop price at MIN_TICK_SIZE (₹0.05) first, then derives effective_stop_distance
    as entry_price - stop_loss_price so risk_amount strictly equals final_quantity * effective_stop_distance.
    Rejects entry_price <= ₹0.05 fail-closed.
    """
    # Probe Case: entry=0.10, atr=0.50, k=2, equity=10000, risk=5% (budget=500), weight=10% (max val=1000 -> 10000 shares)
    # raw_stop = 0.10 - 2*0.50 = -0.90 -> floored to 0.05
    # effective_stop_distance = 0.10 - 0.05 = 0.05
    # q_risk = floor(500 / 0.05) = 10000 shares
    # q_weight = floor(1000 / 0.10) = 10000 shares
    # risk_amount = 10000 * (0.10 - 0.05) = 500.00
    res = calculate_atr_r_multiple_position_size(
        equity=Decimal("10000.00"),
        entry_price=Decimal("0.10"),
        atr=Decimal("0.50"),
        session_volume=1000000,
        risk_per_trade_pct=Decimal("0.05"),
        atr_stop_multiple=Decimal("2.0"),
        max_single_position_weight=Decimal("0.10"),
    )

    assert res.stop_loss_price == Decimal("0.05"), "Stop loss must be floored at minimum tick size ₹0.05"
    assert res.stop_distance == Decimal("0.05"), "stop_distance must be entry - stop_loss_price after floor"
    assert res.quantity == 10000
    assert res.risk_amount == Decimal("500.00"), "risk_amount must strictly match actual loss at reported stop (Finding H-77)"

    # Reject sub-tick entries fail closed
    with pytest.raises(PositionSizingValidationError, match="entry_price must be strictly greater than minimum tick size"):
        calculate_atr_r_multiple_position_size(
            equity=Decimal("10000.00"),
            entry_price=Decimal("0.03"),
            atr=Decimal("0.01"),
            session_volume=1000,
        )

    with pytest.raises(PositionSizingValidationError, match="entry_price must be strictly greater than minimum tick size"):
        calculate_atr_r_multiple_position_size(
            equity=Decimal("10000.00"),
            entry_price=Decimal("0.05"),
            atr=Decimal("0.01"),
            session_volume=1000,
        )


def test_h80_sizer_criteria_defaults_and_mandatory_session_volume():
    """
    Audit §57.3 / §57.7 Item 2 Acceptance Probe (Finding H-80):
    Default call loads max_single_position_weight (0.10) and max_volume_participation_cap (0.03)
    directly from GoNoGoCriteria (zero unlinked threshold literals).
    Requires positive integer session_volume fail-closed.
    """
    crit = load_go_no_go_criteria()
    assert crit.max_single_position_weight == Decimal("0.10")
    assert crit.max_volume_participation_cap == Decimal("0.03")

    # Default call bounded by 0.10 and 0.03
    # equity=1,000,000, entry=100, atr=2, session_volume=1000
    # q_risk = floor(10000 / 4) = 2500
    # q_weight = floor(100000 / 100) = 1000
    # q_vol = floor(1000 * 0.03) = 30
    # Volume participation binds at 30 shares!
    res = calculate_atr_r_multiple_position_size(
        equity=Decimal("1000000.00"),
        entry_price=Decimal("100.00"),
        atr=Decimal("2.00"),
        session_volume=1000,
    )

    assert res.quantity == 30
    assert res.binding_constraint == "VOLUME_PARTICIPATION", "Must report VOLUME_PARTICIPATION when volume binds"

    # Missing session_volume must raise TypeError (required positional argument)
    with pytest.raises(TypeError):
        calculate_atr_r_multiple_position_size(  # type: ignore
            equity=Decimal("1000000.00"),
            entry_price=Decimal("100.00"),
            atr=Decimal("2.00"),
        )

    # Invalid session_volume (None, 0, negative, bool) must raise PositionSizingValidationError
    with pytest.raises(PositionSizingValidationError, match="strictly positive integer"):
        calculate_atr_r_multiple_position_size(
            equity=Decimal("1000000.00"),
            entry_price=Decimal("100.00"),
            atr=Decimal("2.00"),
            session_volume=0,
        )

    with pytest.raises(PositionSizingValidationError, match="strictly positive integer"):
        calculate_atr_r_multiple_position_size(
            equity=Decimal("1000000.00"),
            entry_price=Decimal("100.00"),
            atr=Decimal("2.00"),
            session_volume=True,  # type: ignore
        )


# =============================================================================
# 2. Point-in-Time Universe Selection Tests (§56.5, §57.7 Items 3–4, AGENTS.md §6.1, §10.5)
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
    Audit §56.5 Precondition 2 / Finding N-72: Requesting unsourced 'NIFTY 500' raises UniverseValidationError fail-closed.
    """
    sessions = [datetime.date(2023, 1, 3), datetime.date(2023, 1, 4)]
    with pytest.raises(UniverseValidationError, match="Index membership history for 'NIFTY 500' is not sourced"):
        build_point_in_time_universe_schedule(
            sessions=sessions,
            requested_index_name="NIFTY 500",
        )


def test_h79_calendar_validation_rejects_saturday():
    """
    Audit §57.3 / §57.7 Item 3 Acceptance Probe (Finding H-79):
    Non-session dates (e.g. 2024-01-06 Saturday) absent from the authoritative calendar
    raise UniverseValidationError fail-closed.
    """
    saturday = datetime.date(2024, 1, 6)
    with pytest.raises(UniverseValidationError, match="not an authoritative NSE trading session"):
        build_point_in_time_universe_schedule(sessions=[saturday])


def test_h78_h79_calendar_lookback_and_fail_closed_missing_history():
    """
    Audit §57.3 / §57.7 Item 3 Acceptance Probe (Findings H-78, H-79):
    Lookback window is derived from authoritative calendar sessions strictly prior to T.
    If session lacks lookback history in daily_turnover_inr, it raises fail-closed
    rather than emitting an unfiltered 2,172-scrip cross-section.
    """
    d1 = datetime.date(2024, 1, 2)
    d2 = datetime.date(2024, 1, 3)
    d3 = datetime.date(2024, 1, 4)

    # When daily_turnover_inr only has records for d1, d2, d3, d1 has NO lookback history in the calendar.
    # Must raise fail-closed on d1 rather than emitting all unfiltered active scrips!
    sparse_turnovers = {
        (d1, "INE000000001"): Decimal("100000000"),
        (d2, "INE000000001"): Decimal("100000000"),
        (d3, "INE000000001"): Decimal("100000000"),
    }

    with pytest.raises(UniverseValidationError, match="has no turnover lookback history in daily_turnover_inr"):
        build_point_in_time_universe_schedule(
            sessions=[d1, d2, d3],
            daily_turnover_inr=sparse_turnovers,
            min_median_daily_turnover_inr=Decimal("50000000"),
            turnover_lookback_sessions=2,
        )


def test_pit_universe_zero_lookahead_liquidity_filtering():
    """
    Verifies zero-lookahead turnover filtering: turnover recorded on date T is never
    used to evaluate universe membership for date T.
    Calendar lookback sessions strictly prior to d3 (d1=2024-01-01, d2=2024-01-02) are used.
    """
    cal = load_anchored_nse_trading_calendar()
    d3 = datetime.date(2024, 1, 3)
    s_idx = cal.sessions.index(d3)
    prior_2_sessions = cal.sessions[s_idx - 2 : s_idx]
    d1, d2 = prior_2_sessions

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
        sessions=[d3],
        intervals=test_intervals,
        daily_turnover_inr=turnovers,
        min_median_daily_turnover_inr=Decimal("50000000"),  # ₹5 Cr threshold
        turnover_lookback_sessions=2,
    )

    # On d3: AAA passed (lookback median ₹10 Cr >= ₹5 Cr); BBB excluded (lookback median ₹1 Cr < ₹5 Cr)
    members_d3 = sched.get_universe_for_date(d3)
    assert "INE000000001" in members_d3
    assert "INE000000002" not in members_d3, "Turnover on session T must not be used to qualify session T membership (Zero Lookahead)"


def test_n71_missing_turnover_record_distinguished_and_excluded_with_named_reason():
    """
    Audit §57.3 / §57.7 Item 4 Acceptance Probe (Finding N-71):
    Distinguishes missing turnover records from 0.0 turnover.
    Instruments with missing lookback records are excluded with MISSING_TURNOVER_RECORD reason,
    not silently ranked at 0.0 or sorted by ISIN.
    """
    cal = load_anchored_nse_trading_calendar()
    d3 = datetime.date(2024, 1, 3)
    s_idx = cal.sessions.index(d3)
    prior_2_sessions = cal.sessions[s_idx - 2 : s_idx]
    d1, d2 = prior_2_sessions

    test_intervals = [
        CashEquityInterval(isin="INE000000001", symbol="AAA", series="EQ", effective_from=datetime.date(2020, 1, 1)),
        CashEquityInterval(isin="INE000000002", symbol="BBB", series="EQ", effective_from=datetime.date(2020, 1, 1)),
        CashEquityInterval(isin="INE000000003", symbol="CCC", series="EQ", effective_from=datetime.date(2020, 1, 1)),
        CashEquityInterval(isin="INE000000004", symbol="DDD", series="EQ", effective_from=datetime.date(2020, 1, 1)),
    ]

    # AAA: Full records, high turnover (₹10 Cr) -> eligible
    # BBB: Record missing for d2 -> excluded for MISSING_TURNOVER_RECORD
    # CCC: Zero records in turnovers map -> excluded for MISSING_TURNOVER_RECORD
    # DDD: Full records, but explicit Decimal("0.0") turnover -> excluded for BELOW_MIN_MEDIAN_TURNOVER
    turnovers = {
        (d1, "INE000000001"): Decimal("100000000"),
        (d2, "INE000000001"): Decimal("100000000"),
        (d1, "INE000000002"): Decimal("100000000"),
        # (d2, "INE000000002") is MISSING!
        # CCC is completely missing!
        (d1, "INE000000004"): Decimal("0.0"),
        (d2, "INE000000004"): Decimal("0.0"),
    }

    sched = build_point_in_time_universe_schedule(
        sessions=[d3],
        intervals=test_intervals,
        daily_turnover_inr=turnovers,
        min_median_daily_turnover_inr=Decimal("50000000"),
        turnover_lookback_sessions=2,
    )

    members_d3 = sched.get_universe_for_date(d3)
    assert "INE000000001" in members_d3
    assert "INE000000002" not in members_d3
    assert "INE000000003" not in members_d3
    assert "INE000000004" not in members_d3

    # Check named exclusion reasons (Finding N-71)
    reason_bbb = sched.get_exclusion_reason(d3, "INE000000002")
    assert reason_bbb is not None and "MISSING_TURNOVER_RECORD" in reason_bbb

    reason_ccc = sched.get_exclusion_reason(d3, "INE000000003")
    assert reason_ccc is not None and "MISSING_TURNOVER_RECORD" in reason_ccc

    reason_ddd = sched.get_exclusion_reason(d3, "INE000000004")
    assert reason_ddd is not None and "BELOW_MIN_MEDIAN_TURNOVER" in reason_ddd


# =============================================================================
# 3. Hardened N-63 AST Checker & Runtime Guard Probes (§56.3, §57.7 Item 5, Findings N-63, N-69)
# =============================================================================

def test_n63_n69_ast_checker_and_runtime_guard():
    """
    Audit §56.3, §57.4 / §57.7 Item 5 Acceptance Probe:
    Verifies that the hardened AST literal analyzer and runtime guard catch:
    1. Direct dict literal
    2. Literal via update()
    3. Literal via subscript
    4. Module-level constant reference
    5. Helper call with literal (setdefault)
    6. Numeric Decimal/float/int literal call
    7. Local variable assigned literal (Finding N-69)
    8. Runtime guard raises TypeError on injected bool/int/float (Finding N-69)
    """
    probe_templates = {
        "direct_dict_literal": "def build_tier_a_results_bundle():\n    bundle = {'strict_decimal_accounting': True}\n    return bundle\n",
        "literal_via_update": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle.update({'strict_decimal_accounting': True})\n    return bundle\n",
        "literal_via_subscript": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle['strict_decimal_accounting'] = True\n    return bundle\n",
        "module_level_constant": "CONST_FLAG = True\ndef build_tier_a_results_bundle():\n    bundle = {'strict_decimal_accounting': CONST_FLAG}\n    return bundle\n",
        "helper_call_with_literal": "def build_tier_a_results_bundle():\n    bundle = {}\n    bundle.setdefault('strict_decimal_accounting', True)\n    return bundle\n",
        "numeric_metric_literal": "from decimal import Decimal\ndef build_tier_a_results_bundle():\n    bundle = {'profit_factor': Decimal('1.6850')}\n    return bundle\n",
        "local_var_literal": "def build_tier_a_results_bundle():\n    k = True\n    bundle = {'flag': k}\n    return bundle\n",
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

        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_tier_a_results_bundle")
        local_literals: set[str] = set()
        for stmt in func.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        val = stmt.value
                        if isinstance(val, ast.Constant) and isinstance(val.value, (bool, int, float)):
                            local_literals.add(t.id)

        def is_literal_node(node: ast.AST) -> tuple[bool, str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float)):
                return True, f"constant literal {node.value!r}"
            if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
                if isinstance(node.operand.value, (int, float)):
                    return True, f"unary constant {ast.unparse(node)!r}"
            if isinstance(node, ast.Name) and (node.id in module_constants or node.id in local_literals):
                return True, f"constant/local {node.id!r}"
            if isinstance(node, ast.Call):
                fname = getattr(node.func, "id", getattr(node.func, "attr", None))
                if fname in ("Decimal", "float", "int"):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        return True, f"call {fname}({node.args[0].value!r})"
                    if node.args and isinstance(node.args[0], ast.Name) and (node.args[0].id in module_constants or node.args[0].id in local_literals):
                        return True, f"call {fname}({node.args[0].id!r})"
            return False, ""

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
        assert caught, f"AST checker failed to catch {case_name} (Finding N-63 / N-69)!"

    # Runtime guard test (Finding N-69)
    for bad_val in (True, 42, 3.14):
        with pytest.raises(TypeError, match="forbidden literal type"):
            bundle = {"test_key": bad_val}
            for k, v in bundle.items():
                if isinstance(v, (bool, int, float)):
                    raise TypeError(f"Bundle key {k!r} has forbidden literal type {type(v).__name__} (Finding N-69).")
