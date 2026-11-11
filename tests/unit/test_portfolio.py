"""Unit Test Suite for Portfolio Accounting, Cash Ledger, and Position Tracking.

Verifies:
- Exact Decimal ledger arithmetic with contract-note paise quantization (0.01 INR).
- Fail-closed overdraft protection and statutory cost deductions.
- Multi-instrument position accounting with weighted average price and proportional fee allocation.
- Prohibition of short selling under cash delivery settlement (CNC).
- Strict reconciliation: (Final Cash - Initial Cash) == Cumulative Realized Net PnL.
- Portfolio mark-to-market valuation, peak equity, drawdown calculation, and risk limit enforcement.
- Fail-closed valuation price presence (zero silent omissions or NaNs).
- Remediation of Audit §13 Findings:
  * I-1: Atomic fill processing; failed position updates leave cash ledger completely untouched.
  * I-2: Idempotent fill processing; replayed / duplicate fills fail closed with unique reference enforcement.
  * I-3: Concentration cap is evaluated on total capital deployed (gross + statutory charges).
  * I-4: Exact Decimal drawdown comparison preserves threshold crossing (0.25001 > 0.25).
  * I-5: Chronological date monotonicity rejects past-dated ledger postings.
  * I-7: Proportional cost basis allocation eliminates sub-paise drift across partial sales.
"""

import datetime
from decimal import Decimal
from typing import Optional
import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.execution.costs import TransactionCostBreakdown, TransactionCostModel
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
    order_id: Optional[str] = None,
    fill_id: Optional[str] = None,
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
        order_id=order_id,
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
        fill_id=fill_id,
    )


# ==============================================================================
# 1. Authoritative CashLedger Tests
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

    # 2. SELL fill (verified circuit evidence) on next date
    d2 = datetime.date(2026, 11, 12)
    sell_fill = _make_dummy_fill(
        instrument_id="RELIANCE",
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal("1100.00"),
        trade_date=d2,
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
    1. BUY 100 @ ₹1000 (Session 1)
    2. BUY 100 @ ₹1200 (Session 2) -> Average price ₹1100, quantity 200
    3. Partial SELL 50 @ ₹1300 (Session 3)
    4. Full SELL remaining 150 @ ₹1400 (Session 4)
    5. Reconcile: Cash Ledger Net Flow == Position Realized Net PnL to the exact paisa.
    """
    d1 = datetime.date(2026, 11, 10)
    d2 = datetime.date(2026, 11, 11)
    d3 = datetime.date(2026, 11, 12)
    d4 = datetime.date(2026, 11, 13)

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
    f2 = _make_dummy_fill("INFY", OrderSide.BUY, 100, Decimal("1200.00"), d2)
    ledger.record_fill(f2)
    pos.apply_fill(f2)
    assert pos.quantity == 200
    assert pos.total_cost_basis == Decimal("220000.00")
    assert pos.average_entry_price == Decimal("1100.0000")

    # Fill 3: Partial SELL 50 @ 1300
    f3 = _make_dummy_fill("INFY", OrderSide.SELL, 50, Decimal("1300.00"), d3)
    ledger.record_fill(f3)
    gross_pnl_3, net_pnl_3 = pos.apply_fill(f3)
    assert pos.quantity == 150
    assert pos.total_cost_basis == Decimal("165000.00")
    assert pos.average_entry_price == Decimal("1100.0000")
    # Gross PnL on 50 shares = 50 * (1300 - 1100) = 10,000.00
    assert gross_pnl_3 == Decimal("10000.00")
    assert net_pnl_3 < gross_pnl_3  # reduced by statutory charges

    # Fill 4: Full SELL remaining 150 @ 1400
    f4 = _make_dummy_fill("INFY", OrderSide.SELL, 150, Decimal("1400.00"), d4)
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
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria)
    d1 = datetime.date(2026, 11, 11)

    # 1. 8% allocation (₹80,000) is permitted (<= 10%)
    valid_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 80, Decimal("1000.00"), d1)
    entry = portfolio.process_fill(valid_fill, enforce_risk_limits=True)
    assert entry.amount == Decimal("-80118.60")
    assert portfolio.get_position("RELIANCE").quantity == 80  # type: ignore

    # 2. Attempting to add another ₹50,000 (total ₹130,000 = ~13% > 10%) must fail closed
    d2 = datetime.date(2026, 11, 12)
    breach_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 50, Decimal("1000.00"), d2)
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
    assert snap1.current_drawdown == Decimal("0.00014234")  # exact Decimal cost friction
    assert snap1.open_positions_count == 1

    # Session 2: Price rises to 1200
    snap2 = portfolio.mark_to_market(s2, {"TCS": Decimal("1200.00")})
    assert snap2.total_portfolio_value == Decimal("1019857.66")
    assert snap2.peak_portfolio_value == Decimal("1019857.66")
    assert snap2.current_drawdown == Decimal("0.00")
    assert snap2.drawdown_duration_sessions == 0

    # Session 3: Price drops to 900
    snap3 = portfolio.mark_to_market(s3, {"TCS": Decimal("900.00")})
    assert snap3.total_portfolio_value == Decimal("989857.66")
    assert snap3.peak_portfolio_value == Decimal("1019857.66")
    # Drawdown = (1019857.66 - 989857.66) / 1019857.66 = 30000 / 1019857.66 = ~0.02941587...
    assert snap3.current_drawdown.quantize(Decimal("0.0001")) == Decimal("0.0294")
    assert snap3.drawdown_duration_sessions == 1
    assert portfolio.is_max_drawdown_breached is False

    # Session 4: Price drops to 700
    snap4 = portfolio.mark_to_market(s4, {"TCS": Decimal("700.00")})
    assert snap4.current_drawdown.quantize(Decimal("0.0001")) == Decimal("0.0490")
    assert snap4.max_drawdown.quantize(Decimal("0.0001")) == Decimal("0.0490")
    assert snap4.drawdown_duration_sessions == 2

    # Session 5: Price rockets to 1300
    snap5 = portfolio.mark_to_market(s5, {"TCS": Decimal("1300.00")})
    assert snap5.total_portfolio_value == Decimal("1029857.66")
    assert snap5.peak_portfolio_value == Decimal("1029857.66")
    assert snap5.current_drawdown == Decimal("0.00")
    assert snap5.drawdown_duration_sessions == 0
    assert snap5.max_drawdown.quantize(Decimal("0.0001")) == Decimal("0.0490")


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


# ==============================================================================
# 4. Audit §13 Remediation Probes (I-1, I-2, I-3, I-4, I-5, I-7)
# ==============================================================================


def test_finding_i1_process_fill_atomicity_and_short_sale_leaves_cash_untouched():
    """
    Verify I-1 remediation:
    Portfolio.process_fill pre-validates position transitions before moving cash.
    A rejected oversell raises LedgerValidationError and leaves the cash balance
    and ledger entries count COMPLETELY UNTOUCHED (zero fabricated inflows).
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 10)
    d2 = datetime.date(2026, 11, 11)

    # 1. Buy 100 shares of RELIANCE
    buy_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 100, Decimal("1000.00"), d1)
    portfolio.process_fill(buy_fill, enforce_risk_limits=False)
    cash_after_buy = portfolio.ledger.current_cash
    entries_count_after_buy = len(portfolio.ledger.entries)
    assert cash_after_buy == Decimal("899857.66")
    assert entries_count_after_buy == 2

    # 2. Attempt illegal oversell: sell 200 shares when holding only 100
    oversell_fill = _make_dummy_fill("RELIANCE", OrderSide.SELL, 200, Decimal("1000.00"), d2)
    with pytest.raises(LedgerValidationError, match="Illegal short delivery: cannot sell 200 shares"):
        portfolio.process_fill(oversell_fill, enforce_risk_limits=False)

    # Verify atomicity: cash and entries MUST be identical to post-buy state
    assert portfolio.ledger.current_cash == cash_after_buy
    assert len(portfolio.ledger.entries) == entries_count_after_buy
    assert portfolio.get_position("RELIANCE").quantity == 100  # type: ignore

    # 3. Attempt selling an instrument never held (TCS)
    never_held_fill = _make_dummy_fill("TCS", OrderSide.SELL, 50, Decimal("3500.00"), d2)
    with pytest.raises(LedgerValidationError, match="Illegal short delivery: cannot sell 50 shares of TCS"):
        portfolio.process_fill(never_held_fill, enforce_risk_limits=False)

    assert portfolio.ledger.current_cash == cash_after_buy
    assert len(portfolio.ledger.entries) == entries_count_after_buy


def test_finding_i2_idempotent_fill_processing_rejection():
    """
    Verify I-2 remediation:
    The same ExecutionFillResult processed twice is rejected on the second call.
    Replays fail closed without double-debiting cash or duplicating entries.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 10)

    buy_fill = _make_dummy_fill("INFY", OrderSide.BUY, 100, Decimal("1000.00"), d1)
    portfolio.process_fill(buy_fill, enforce_risk_limits=False)
    cash_after_first = portfolio.ledger.current_cash
    entries_after_first = len(portfolio.ledger.entries)

    # Replaying the exact same fill must raise LedgerValidationError
    with pytest.raises(LedgerValidationError, match="Duplicate entry rejected: fill"):
        portfolio.process_fill(buy_fill, enforce_risk_limits=False)

    assert portfolio.ledger.current_cash == cash_after_first
    assert len(portfolio.ledger.entries) == entries_after_first


def test_finding_i3_concentration_cap_includes_statutory_charges():
    """
    Verify I-3 remediation:
    Concentration limit evaluates total capital deployed (gross amount + statutory charges).
    A buy of exactly 10.00% gross deployed capital exceeds 10.00% once charges are included,
    and fails closed with PortfolioRiskLimitError.
    """
    criteria = load_go_no_go_criteria()
    # Portfolio equity = ₹1,000,000
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"), criteria=criteria)
    d1 = datetime.date(2026, 11, 10)

    # Order of 100 shares @ ₹1000.00 = gross ₹100,000.00 (exactly 10.00% gross).
    # With statutory charges (~₹142.34), total deployed = ₹100,142.34 (10.0142% > 10.00%).
    exact_gross_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 100, Decimal("1000.00"), d1)
    with pytest.raises(PortfolioRiskLimitError, match="Allocation breach for 'RELIANCE'"):
        portfolio.process_fill(exact_gross_fill, enforce_risk_limits=True)

    # A 9% allocation (90 shares = ₹90,130.46 deployed = 9.01% <= 10.00%) passes
    valid_fill = _make_dummy_fill("RELIANCE", OrderSide.BUY, 90, Decimal("1000.00"), d1)
    entry = portfolio.process_fill(valid_fill, enforce_risk_limits=True)
    assert entry.amount == Decimal("-90130.46")


def test_finding_i4_drawdown_breach_precision_preserves_threshold_crossing():
    """
    Verify I-4 remediation:
    Drawdown comparison is unrounded. An equity drop of 0.25001 against max_portfolio_drawdown
    of 0.25 correctly flags is_max_drawdown_breached == True without premature 4 dp rounding loss.
    """
    criteria = load_go_no_go_criteria()
    portfolio = Portfolio(initial_capital=Decimal("100000.00"), criteria=criteria)
    d1 = datetime.date(2026, 11, 10)

    # Buy 1 share @ ₹74,999.00
    fill = _make_dummy_fill("NIFTY_BEES", OrderSide.BUY, 1, Decimal("74999.00"), d1)
    portfolio.process_fill(fill, enforce_risk_limits=False)

    # Session MTM: market price is ₹74,999.00, but charges caused equity to drop to ₹99857.66
    # To test exact Probe G: force portfolio total equity to ₹74,999.00
    # Peak was 100,000.00. If current value is 74,999.00, drop = 25,001.00 / 100,000.00 = 0.25001
    portfolio._peak_portfolio_value = Decimal("100000.00")
    # Take snapshot with price that causes equity to be exactly ₹74,999.00
    # Current cash is 100,000 - (74999 + 112.65) = 24888.35
    # If market price is 50110.65: equity = 24888.35 + 50110.65 = 74999.00
    snap = portfolio.mark_to_market(d1, {"NIFTY_BEES": Decimal("50110.65")})
    assert snap.total_portfolio_value == Decimal("74999.00")
    assert portfolio.current_drawdown == Decimal("0.25001")
    assert portfolio.is_max_drawdown_breached is True


def test_finding_i5_chronological_ordering_rejects_past_dated_entry():
    """
    Verify I-5 remediation:
    CashLedger enforces chronological date monotonicity.
    Posting an entry on 11 Nov after an entry on 12 Nov raises LedgerValidationError.
    """
    ledger = CashLedger(initial_capital=Decimal("100000.00"))
    d_later = datetime.date(2026, 11, 12)
    d_earlier = datetime.date(2026, 11, 11)

    ledger.deposit(d_later, Decimal("1000.00"))
    with pytest.raises(LedgerValidationError, match="Non-monotonic trade_date"):
        ledger.deposit(d_earlier, Decimal("500.00"))


def test_finding_i7_proportional_basis_eliminates_sub_paise_drift():
    """
    Verify I-7 remediation (Probe D''):
    Deriving partial-sale cost basis proportionally directly from total_cost_basis
    eliminates sub-paise drift across multiple partial sales, leaving exactly 0.00 on full exit.
    """
    pos = Position("INFY")
    d1 = datetime.date(2026, 11, 10)
    d2 = datetime.date(2026, 11, 11)
    d3 = datetime.date(2026, 11, 12)
    d4 = datetime.date(2026, 11, 13)

    # Buy 3 shares @ ₹333.3333... (total ₹1000.00)
    # Using 3 shares with total cost basis 1000.00:
    buy_fill = _make_dummy_fill("INFY", OrderSide.BUY, 3, Decimal("333.33"), d1)
    pos.apply_fill(buy_fill)
    # Initial cost basis is 3 * 333.33 = 999.99
    assert pos.quantity == 3

    # Sell 1 share
    sell_1 = _make_dummy_fill("INFY", OrderSide.SELL, 1, Decimal("350.00"), d2)
    pos.apply_fill(sell_1)
    assert pos.quantity == 2

    # Sell 1 share
    sell_2 = _make_dummy_fill("INFY", OrderSide.SELL, 1, Decimal("350.00"), d3)
    pos.apply_fill(sell_2)
    assert pos.quantity == 1

    # Sell final share
    sell_3 = _make_dummy_fill("INFY", OrderSide.SELL, 1, Decimal("350.00"), d4)
    pos.apply_fill(sell_3)
    assert pos.quantity == 0
    assert pos.is_closed is True
    # Invariant: residual cost basis and unallocated charges MUST be exactly 0.00
    assert pos.total_cost_basis == Decimal("0.00")
    assert pos.unallocated_buy_charges == Decimal("0.00")


def test_multi_fill_scale_in_same_session():
    """
    Verify R-1: Multi-fill scale-in in the same session without explicit references.
    3 consecutive buys of RELIANCE on 2026-11-11 must all succeed and produce sequential
    references (#1, #2, #3), holding a total of 60 shares.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 11)

    f1 = _make_dummy_fill("RELIANCE", OrderSide.BUY, 20, Decimal("2500.00"), d1)
    f2 = _make_dummy_fill("RELIANCE", OrderSide.BUY, 20, Decimal("2500.00"), d1)
    f3 = _make_dummy_fill("RELIANCE", OrderSide.BUY, 20, Decimal("2500.00"), d1)

    e1 = portfolio.process_fill(f1, enforce_risk_limits=False)
    e2 = portfolio.process_fill(f2, enforce_risk_limits=False)
    e3 = portfolio.process_fill(f3, enforce_risk_limits=False)

    assert e1.reference_id == "FILL_RELIANCE_2026-11-11#1"
    assert e2.reference_id == "FILL_RELIANCE_2026-11-11#2"
    assert e3.reference_id == "FILL_RELIANCE_2026-11-11#3"

    pos = portfolio.get_position("RELIANCE")
    assert pos is not None
    assert pos.quantity == 60


def test_multi_fill_partial_fill_remainder():
    """
    Verify R-1: Multi-fill partial fill execution (60 shares, then 40 shares remainder)
    on the same session for the same instrument without explicit references.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 11)

    f1 = _make_dummy_fill("INFY", OrderSide.BUY, 60, Decimal("1500.00"), d1)
    f2 = _make_dummy_fill("INFY", OrderSide.BUY, 40, Decimal("1500.00"), d1)

    e1 = portfolio.process_fill(f1, enforce_risk_limits=False)
    e2 = portfolio.process_fill(f2, enforce_risk_limits=False)

    assert e1.reference_id == "FILL_INFY_2026-11-11#1"
    assert e2.reference_id == "FILL_INFY_2026-11-11#2"

    pos = portfolio.get_position("INFY")
    assert pos is not None
    assert pos.quantity == 100


def test_replayed_fill_with_explicit_reference_id_rejected():
    """
    Verify replay protection with explicit reference_id:
    A duplicate fill re-using an existing reference_id is rejected fail-closed.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 11)

    f1 = _make_dummy_fill("TCS", OrderSide.BUY, 50, Decimal("3200.00"), d1)
    portfolio.process_fill(f1, reference_id="ORD_TCS_101", enforce_risk_limits=False)

    cash_after = portfolio.ledger.current_cash
    entries_count = len(portfolio.ledger.entries)

    f2 = _make_dummy_fill("TCS", OrderSide.BUY, 50, Decimal("3200.00"), d1)
    with pytest.raises(LedgerValidationError, match="Duplicate entry rejected"):
        portfolio.process_fill(f2, reference_id="ORD_TCS_101", enforce_risk_limits=False)

    assert portfolio.ledger.current_cash == cash_after
    assert len(portfolio.ledger.entries) == entries_count


def test_r2_reconciliation_mismatch_fails_closed():
    """
    Verify R-2: Reconciliation between costs.gross_amount and quantity × executed_price.
    A mismatch between the statutory breakdown and the price/quantity calculation fails closed.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 11)

    valid_fill = _make_dummy_fill("HDFCBANK", OrderSide.BUY, 10, Decimal("1500.00"), d1)
    # Expected gross is 15000.00; craft costs with mismatched gross of 14900.00
    import dataclasses
    mismatched_costs = dataclasses.replace(valid_fill.costs, gross_amount=Decimal("14900.00"))
    bad_fill = ExecutionFillResult(
        order=valid_fill.order,
        status=valid_fill.status,
        fill_date=valid_fill.fill_date,
        latency_sessions=valid_fill.latency_sessions,
        filled_quantity=valid_fill.filled_quantity,
        unfilled_quantity=valid_fill.unfilled_quantity,
        executed_price=valid_fill.executed_price,
        slippage=valid_fill.slippage,
        costs=mismatched_costs,
        circuit_evidence_present=valid_fill.circuit_evidence_present,
        rejection_reason=None,
    )

    with pytest.raises(LedgerValidationError, match="Reconciliation error"):
        portfolio.process_fill(bad_fill, enforce_risk_limits=False)

    # Verify executed_price <= 0 fails closed
    zero_price_fill = ExecutionFillResult(
        order=valid_fill.order,
        status=valid_fill.status,
        fill_date=valid_fill.fill_date,
        latency_sessions=valid_fill.latency_sessions,
        filled_quantity=valid_fill.filled_quantity,
        unfilled_quantity=valid_fill.unfilled_quantity,
        executed_price=Decimal("0.00"),
        slippage=valid_fill.slippage,
        costs=valid_fill.costs,
        circuit_evidence_present=valid_fill.circuit_evidence_present,
        rejection_reason=None,
    )
    with pytest.raises(LedgerValidationError, match="executed_price must be positive finite Decimal"):
        portfolio.process_fill(zero_price_fill, enforce_risk_limits=False)


def test_r3_phantom_position_discarded_on_rollback():
    """
    Verify R-3: If position.apply_fill fails, rollback discards the empty Position object
    from portfolio._positions for newly traded scrips.
    """
    portfolio = Portfolio(initial_capital=Decimal("1000000.00"))
    d1 = datetime.date(2026, 11, 11)

    assert "WIPRO" not in portfolio._positions

    # Create fill with invalid executed_price that passes portfolio checks but fails in position
    valid_fill = _make_dummy_fill("WIPRO", OrderSide.BUY, 10, Decimal("400.00"), d1)

    # Monkeypatch apply_fill to simulate an unexpected error during position update
    target_pos = Position("WIPRO")
    def _exploding_apply_fill(self, f):
        raise RuntimeError("Simulated internal position failure")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Position, "apply_fill", _exploding_apply_fill)
        with pytest.raises(RuntimeError, match="Simulated internal position failure"):
            portfolio.process_fill(valid_fill, enforce_risk_limits=False)

    # Rollback must have cleaned up the phantom Position
    assert "WIPRO" not in portfolio._positions
    # Cash ledger must have no trade entries
    assert len(portfolio.ledger.entries) == 1
    assert portfolio.ledger.current_cash == Decimal("1000000.00")


def test_r4_initial_deposit_derived_from_first_trade_date():
    """
    Verify R-4: When initial_date is omitted in Portfolio(initial_capital=...),
    the initial deposit date is derived lazily from the first trade session,
    avoiding date disorder or fabricated today's date.
    """
    portfolio = Portfolio(initial_capital=Decimal("500000.00"))
    trade_date = datetime.date(2022, 1, 5)

    # Before any trades, 1 entry exists (initial deposit, awaiting anchor to first trade date)
    assert len(portfolio.ledger.entries) == 1
    assert portfolio.current_cash == Decimal("500000.00")

    fill = _make_dummy_fill("SBIN", OrderSide.BUY, 100, Decimal("450.00"), trade_date)
    portfolio.process_fill(fill, enforce_risk_limits=False)

    # Ledger now has 2 entries: deposit and buy, both dated 2022-01-05
    assert len(portfolio.ledger.entries) == 2
    assert portfolio.ledger.entries[0].entry_type == CashEntryType.CAPITAL_DEPOSIT
    assert portfolio.ledger.entries[0].trade_date == trade_date
    assert portfolio.ledger.entries[0].amount == Decimal("500000.00")
    assert portfolio.ledger.entries[1].entry_type == CashEntryType.TRADE_BUY_OUTFLOW
    assert portfolio.ledger.entries[1].trade_date == trade_date

