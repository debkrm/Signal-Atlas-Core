"""Unit Test Suite for Portfolio Accounting, Cash Ledger, and Position Tracking.

Verifies:
- Exact Decimal double-entry ledger arithmetic with contract-note paise quantization (0.01 INR).
- Fail-closed overdraft protection and statutory cost deductions.
- Multi-instrument position accounting with weighted average price and proportional fee allocation.
- Prohibition of short selling under cash delivery settlement (CNC).
- Strict reconciliation: (Final Cash - Initial Cash) == Cumulative Realized Net PnL.
- Portfolio mark-to-market valuation, peak equity, drawdown calculation, and risk limit enforcement.
- Fail-closed valuation price presence (zero silent omissions or NaNs).
"""

import datetime
from decimal import Decimal
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.simulator import ExecutionFillResult
from signal_core.execution.types import (
    ExecutionOrder,
    FillStatus,
    OrderProduct,
    OrderSide,
    OrderType,
)
from signal_core.portfolio.ledger import (
    CashLedger,
    PAISE_PRECISION,
    UNVERIFIED_CIRCUIT_WARNING,
)
from signal_core.portfolio.position import Position
from signal_core.portfolio.portfolio import Portfolio
from signal_core.portfolio.types import (
    CashEntryType,
    LedgerValidationError,
    PortfolioRiskLimitError,
)


def _make_dummy_fill(
    instrument_id: str,
    side: OrderSide,
    quantity: int,
    price: Decimal,
    trade_date: datetime.date,
    circuit_evidence_present: bool = True,
) -> ExecutionFillResult:
    """Helper to create realistic filled ExecutionFillResult with statutory costs."""
    cost_model = TransactionCostModel()
    costs = cost_model.compute_costs(
        trade_date=trade_date,
        side=side,
        product=OrderProduct.DELIVERY,
        quantity=quantity,
        price=price,
        round_to_paise=False,  # simulator produces raw, ledger quantizes to paise
    )
    order = ExecutionOrder(
        instrument_id=instrument_id,
        side=side,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=quantity,
        product=OrderProduct.DELIVERY,
        signal_date=trade_date - datetime.timedelta(days=1),
        target_date=trade_date,
    )
    return ExecutionFillResult(
        order=order,
        status=FillStatus.FILLED,
        fill_date=trade_date,
        latency_sessions=1,
        filled_quantity=quantity,
        unfilled_quantity=0,
        executed_price=price,
        slippage=None,
        costs=costs,
        circuit_evidence_present=circuit_evidence_present,
        rejection_reason=None,
    )


# ==============================================================================
# 1. Double-Entry CashLedger Tests
# ==============================================================================


def test_cash_ledger_initialization_and_type_rejections():
    """Verify CashLedger initialization invariants and rejection of invalid types."""
    # 1. Valid non-negative initial capital
    ledger = CashLedger(initial_capital=Decimal("100000.00"))
    assert ledger.current_cash == Decimal("100000.00")
    assert len(ledger.entries) == 1
    assert ledger.entries[0].entry_type == CashEntryType.CAPITAL_DEPOSIT
    assert ledger.entries[0].amount == Decimal("100000.00")
    assert ledger.entries[0].balance_after == Decimal("100000.00")
    assert ledger.entries[0].amount.as_tuple().exponent == -2

    # 2. Reject boolean initial capital
    with pytest.raises(LedgerValidationError, match="initial_capital must be non-negative Decimal"):
        CashLedger(initial_capital=True)  # type: ignore

    # 3. Reject float initial capital
    with pytest.raises(LedgerValidationError, match="initial_capital must be non-negative Decimal"):
        CashLedger(initial_capital=100000.0)  # type: ignore

    # 4. Reject negative initial capital
    with pytest.raises(LedgerValidationError, match="initial_capital must be non-negative Decimal"):
        CashLedger(initial_capital=Decimal("-500.00"))


def test_cash_ledger_deposit_and_withdrawal_paise_quantization():
    """Verify deposit and withdrawal operations, exact paise quantization, and overdraft prevention."""
    ledger = CashLedger(initial_capital=Decimal("50000.00"), allow_overdraft=False)
    d1 = datetime.date(2026, 11, 11)

    # 1. Deposit
    dep = ledger.deposit(d1, Decimal("25000.505"))  # should round to 25000.51
    assert dep.amount == Decimal("25000.51")
    assert dep.balance_after == Decimal("75000.51")
    assert dep.amount.as_tuple().exponent == -2
    assert ledger.current_cash == Decimal("75000.51")

    # 2. Withdrawal
    withd = ledger.withdraw(d1, Decimal("10000.25"))
    assert withd.amount == Decimal("-10000.25")
    assert withd.balance_after == Decimal("65000.26")
    assert ledger.current_cash == Decimal("65000.26")

    # 3. Overdraft rejection
    with pytest.raises(LedgerValidationError, match="Cash overdraft prohibited"):
        ledger.withdraw(d1, Decimal("70000.00"))

    # 4. Overdraft permitted when configured
    permissive_ledger = CashLedger(initial_capital=Decimal("1000.00"), allow_overdraft=True)
    overdraft_entry = permissive_ledger.withdraw(d1, Decimal("5000.00"))
    assert overdraft_entry.balance_after == Decimal("-4000.00")
    assert permissive_ledger.current_cash == Decimal("-4000.00")


def test_cash_ledger_record_fill_and_circuit_evidence_tracking():
    """Verify recording BUY/SELL fills, paise quantization, and unverified circuit evidence disclosure."""
    ledger = CashLedger(initial_capital=Decimal("200000.00"))
    d1 = datetime.date(2026, 11, 11)

    # 1. BUY fill (unverified circuit evidence)
    buy_fill = _make_dummy_fill(
        instrument_id="RELIANCE",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("1000.00"),
        trade_date=d1,
        circuit_evidence_present=False,
    )
    buy_entry = ledger.record_fill(buy_fill)

    # Cost breakdown for BUY 100 @ 1000 is gross 100000 + charges 142.34 = 100142.34 outflow
    assert buy_entry.entry_type == CashEntryType.TRADE_BUY_OUTFLOW
    assert buy_entry.amount == Decimal("-100142.34")
    assert buy_entry.balance_after == Decimal("99857.66")
    assert buy_entry.circuit_evidence_present is False
    assert buy_entry.metadata is not None
    # Check circuit warning attached in metadata
    meta_dict = dict(buy_entry.metadata)
    assert meta_dict["circuit_warning"] == UNVERIFIED_CIRCUIT_WARNING
    assert meta_dict["gross_amount"] == "100000.00"
    assert meta_dict["total_charges"] == "142.34"

    # 2. SELL fill (verified circuit evidence)
    sell_fill = _make_dummy_fill(
        instrument_id="RELIANCE",
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal("1100.00"),
        trade_date=d1,
        circuit_evidence_present=True,
    )
    sell_entry = ledger.record_fill(sell_fill)

    # Cost breakdown for SELL 100 @ 1100: gross 110000 - charges = net inflow
    assert sell_entry.entry_type == CashEntryType.TRADE_SELL_INFLOW
    assert sell_entry.amount > Decimal("0.00")
    assert sell_entry.circuit_evidence_present is True
    meta_dict_sell = dict(sell_entry.metadata)
    assert "circuit_warning" not in meta_dict_sell


def test_cash_ledger_rejects_non_fill_status():
    """Verify that posting rejected order outcomes to cash ledger fails closed."""
    ledger = CashLedger(initial_capital=Decimal("100000.00"))
    order = ExecutionOrder(
        instrument_id="INFY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET_ON_OPEN,
        quantity=10,
        product=OrderProduct.DELIVERY,
        signal_date=datetime.date(2026, 11, 10),
        target_date=datetime.date(2026, 11, 11),
    )
    rej_fill = ExecutionFillResult(
        order=order,
        status=FillStatus.REJECTED_UPPER_CIRCUIT,
        fill_date=datetime.date(2026, 11, 11),
        latency_sessions=1,
        filled_quantity=0,
        unfilled_quantity=10,
        executed_price=None,
        slippage=None,
        costs=None,
        circuit_evidence_present=True,
        rejection_reason="Price at upper circuit",
    )
    with pytest.raises(LedgerValidationError, match="Cannot post non-fill outcome"):
        ledger.record_fill(rej_fill)


# ==============================================================================
# 2. Multi-Fill Position Accounting Tests
# ==============================================================================


def test_position_initialization_and_validation():
    """Verify Position initialization and identifier validation."""
    pos = Position("TCS")
    assert pos.instrument_id == "TCS"
    assert pos.quantity == 0
    assert pos.is_closed is True
    assert pos.total_cost_basis == Decimal("0.00")
    assert pos.realized_net_pnl == Decimal("0.00")

    with pytest.raises(LedgerValidationError, match="Invalid instrument_id"):
        Position("  ")

    with pytest.raises(LedgerValidationError, match="illegal delimiters"):
        Position("TCS,EQ")


def test_position_prohibits_short_selling_delivery():
    """Verify that selling more shares than held raises LedgerValidationError (no short delivery)."""
    pos = Position("HDFCBANK")
    d1 = datetime.date(2026, 11, 11)
    sell_fill = _make_dummy_fill("HDFCBANK", OrderSide.SELL, 50, Decimal("1500.00"), d1)

    with pytest.raises(LedgerValidationError, match="Illegal short delivery: cannot sell 50 shares"):
        pos.apply_fill(sell_fill)


def test_position_full_and_partial_sales_reconciliation():
    """
    Verify complete multi-fill lifecycle:
    1. BUY 100 @ ₹1000
    2. BUY 100 @ ₹1200 -> Average price ₹1100, quantity 200
    3. Partial SELL 50 @ ₹1300
    4. Full SELL remaining 150 @ ₹1400
    5. Reconcile: Cash Ledger Net Flow == Position Realized Net PnL to the exact paisa.
    """
    d1 = datetime.date(2026, 11, 11)
    ledger = CashLedger(initial_capital=Decimal("500000.00"))
    pos = Position("INFY")

    # Fill 1: BUY 100 @ 1000
    f1 = _make_dummy_fill("INFY", OrderSide.BUY, 100, Decimal("1000.00"), d1)
    ledger.record_fill(f1)
    pos.apply_fill(f1)
    assert pos.quantity == 100
    assert pos.total_cost_basis == Decimal("100000.00")
    assert pos.average_entry_price == Decimal("1000.0000")

    # Fill 2: BUY 100 @ 1200
    f2 = _make_dummy_fill("INFY", OrderSide.BUY, 100, Decimal("1200.00"), d1)
    ledger.record_fill(f2)
    pos.apply_fill(f2)
    assert pos.quantity == 200
    assert pos.total_cost_basis == Decimal("220000.00")
    assert pos.average_entry_price == Decimal("1100.0000")

    # Fill 3: Partial SELL 50 @ 1300
    f3 = _make_dummy_fill("INFY", OrderSide.SELL, 50, Decimal("1300.00"), d1)
    ledger.record_fill(f3)
    gross_pnl_3, net_pnl_3 = pos.apply_fill(f3)
    assert pos.quantity == 150
    assert pos.total_cost_basis == Decimal("165000.00")
    assert pos.average_entry_price == Decimal("1100.0000")
    # Gross PnL on 50 shares = 50 * (1300 - 1100) = 10,000.00
    assert gross_pnl_3 == Decimal("10000.00")
    assert net_pnl_3 < gross_pnl_3  # reduced by statutory charges

    # Fill 4: Full SELL remaining 150 @ 1400
    f4 = _make_dummy_fill("INFY", OrderSide.SELL, 150, Decimal("1400.00"), d1)
    ledger.record_fill(f4)
    gross_pnl_4, net_pnl_4 = pos.apply_fill(f4)
    assert pos.quantity == 0
    assert pos.is_closed is True
    assert pos.total_cost_basis == Decimal("0.00")
    # Gross PnL on 150 shares = 150 * (1400 - 1100) = 45,000.00
    assert gross_pnl_4 == Decimal("45000.00")

    # TOTAL RECONCILIATION:
    # Final cash in ledger minus initial capital MUST equal cumulative realized net PnL!
    cash_delta = ledger.current_cash - Decimal("500000.00")
    assert cash_delta == pos.realized_net_pnl
    assert cash_delta.as_tuple().exponent == -2
    assert pos.realized_net_pnl.as_tuple().exponent == -2


# ==============================================================================
# 3. Portfolio Risk Limits and Drawdown Tests
# ==============================================================================


def test_portfolio_single_position_allocation_limit_breach():
    """
    Verify Rule 7 & Criteria 3.3:
    max_single_position_weight = 0.10 (10% allocation cap).
    Attempting to allocate >10% of portfolio equity to a single stock raises PortfolioRiskLimitError.
    """
    criteria = load_go_no_go_criteria()
    # Portfolio with ₹1,000,000 initial cash
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria)
    d1 = datetime.date(2026, 11, 11)

    # 1. 8% allocation (₹80,000) is permitted (<= 10%)
    valid_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 80, Decimal("1000.00"), d1)
    entry = portfolio.process_fill(valid_fill, enforce_risk_limits=True)
    assert entry.amount == Decimal("-80118.60")
    assert portfolio.get_position("RELIANCE").quantity == 80  # type: ignore

    # 2. Attempting to add another ₹50,000 (total ₹130,000 = ~13% > 10%) must fail closed
    breach_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 50, Decimal("1000.00"), d1)
    with pytest.raises(PortfolioRiskLimitError, match="Allocation breach for 'RELIANCE'"):
        portfolio.process_fill(breach_fill, enforce_risk_limits=True)


def test_portfolio_mark_to_market_valuation_and_drawdown_tracking():
    """
    Verify daily mark-to-market session valuation, peak tracking, and drawdown computation:
    - Session 1: Buy 100 shares @ ₹1000. MTM @ ₹1000.
    - Session 2: Price rises to ₹1200. Peak equity established. Drawdown = 0%.
    - Session 3: Price drops to ₹900. Drawdown calculated. Duration = 1 session.
    - Session 4: Price drops further to ₹800. Drawdown increases. Duration = 2 sessions.
    - Session 5: Price recovers to ₹1300. New peak established. Drawdown = 0%, Duration resets.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    s1 = datetime.date(2026, 11, 10)
    s2 = datetime.date(2026, 11, 11)
    s3 = datetime.date(2026, 11, 12)
    s4 = datetime.date(2026, 11, 13)
    s5 = datetime.date(2026, 11, 14)

    # Session 1: BUY 100 @ 1000
    fill = _make_dummy_fill("TCS", OrderSide.BUY, 100, Decimal("1000.00"), s1)
    portfolio.process_fill(fill, enforce_risk_limits=False)
    snap1 = portfolio.mark_to_market(s1, {"TCS": Decimal("1000.00")})
    # Equity = cash (1000000 - 100142.34 = 899857.66) + 100000 = 999857.66
    assert snap1.total_portfolio_value == Decimal("999857.66")
    assert snap1.current_drawdown == Decimal("0.0001")  # slight cost friction against 1M initial peak
    assert snap1.open_positions_count == 1

    # Session 2: Price rises to 1200
    snap2 = portfolio.mark_to_market(s2, {"TCS": Decimal("1200.00")})
    # Equity = 899857.66 + 120000 = 1019857.66 (new peak!)
    assert snap2.total_portfolio_value == Decimal("1019857.66")
    assert snap2.peak_portfolio_value == Decimal("1019857.66")
    assert snap2.current_drawdown == Decimal("0.0000")
    assert snap2.drawdown_duration_sessions == 0

    # Session 3: Price drops to 900
    snap3 = portfolio.mark_to_market(s3, {"TCS": Decimal("900.00")})
    # Equity = 899857.66 + 90000 = 989857.66
    # Drawdown = (1019857.66 - 989857.66) / 1019857.66 = 30000 / 1019857.66 = ~0.0294 (2.94%)
    assert snap3.total_portfolio_value == Decimal("989857.66")
    assert snap3.peak_portfolio_value == Decimal("1019857.66")
    assert snap3.current_drawdown == Decimal("0.0294")
    assert snap3.drawdown_duration_sessions == 1
    assert portfolio.is_max_drawdown_breached is False

    # Session 4: Price drops to 700
    snap4 = portfolio.mark_to_market(s4, {"TCS": Decimal("700.00")})
    # Equity = 899857.66 + 70000 = 969857.66
    # Drawdown = (1019857.66 - 969857.66) / 1019857.66 = 50000 / 1019857.66 = ~0.0490 (4.90%)
    assert snap4.current_drawdown == Decimal("0.0490")
    assert snap4.max_drawdown == Decimal("0.0490")
    assert snap4.drawdown_duration_sessions == 2

    # Session 5: Price rockets to 1300
    snap5 = portfolio.mark_to_market(s5, {"TCS": Decimal("1300.00")})
    # Equity = 899857.66 + 130000 = 1029857.66 (surpasses previous peak!)
    assert snap5.total_portfolio_value == Decimal("1029857.66")
    assert snap5.peak_portfolio_value == Decimal("1029857.66")
    assert snap5.current_drawdown == Decimal("0.0000")
    assert snap5.drawdown_duration_sessions == 0
    assert snap5.max_drawdown == Decimal("0.0490")  # max drawdown recorded remains 4.90%


def test_portfolio_mark_to_market_fail_closed_missing_price():
    """Verify that mark_to_market fails closed if an open position lacks a market price."""
    portfolio = Portfolio(initial_capital=Decimal("500000.00"))
    d1 = datetime.date(2026, 11, 10)
    fill = _make_dummy_fill("INFY", OrderSide.BUY, 50, Decimal("1500.00"), d1)
    portfolio.process_fill(fill, enforce_risk_limits=False)

    # Missing price for 'INFY'
    with pytest.raises(LedgerValidationError, match="Fail-closed valuation: missing required market price"):
        portfolio.mark_to_market(d1, {"TCS": Decimal("3500.00")})


def test_portfolio_mark_to_market_rejects_non_monotonic_dates():
    """Verify that valuation date must be strictly after the previous valuation date."""
    portfolio = Portfolio(initial_capital=Decimal("100000.00"))
    d1 = datetime.date(2026, 11, 11)
    d2 = datetime.date(2026, 11, 10)

    portfolio.mark_to_market(d1, {})
    with pytest.raises(LedgerValidationError, match="must be strictly after last valuation date"):
        portfolio.mark_to_market(d2, {})
