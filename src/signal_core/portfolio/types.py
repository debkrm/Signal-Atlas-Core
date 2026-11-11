"""Portfolio, Ledger, and Risk Domain Types and Enums.

Defines immutable contracts for cash ledger entries, position states,
portfolio valuation snapshots, and risk limit exceptions in exact Decimal arithmetic.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class CashEntryType(str, Enum):
    """Classification of cash ledger entries."""
    CAPITAL_DEPOSIT = "CAPITAL_DEPOSIT"          # Initial or supplementary capital injection
    CAPITAL_WITHDRAWAL = "CAPITAL_WITHDRAWAL"    # Capital distribution / withdrawal
    TRADE_BUY_OUTFLOW = "TRADE_BUY_OUTFLOW"      # Trade purchase outflow (gross + charges)
    TRADE_SELL_INFLOW = "TRADE_SELL_INFLOW"      # Trade proceeds inflow (gross - charges)
    DIVIDEND_INFLOW = "DIVIDEND_INFLOW"          # Corporate action cash dividend
    FEE_DEBIT = "FEE_DEBIT"                      # Miscellaneous / custodial fee debit


class LedgerValidationError(ValueError):
    """Raised when a cash ledger operation violates financial invariants."""
    pass


class PortfolioRiskLimitError(ValueError):
    """Raised when an order or allocation breaches committed portfolio risk limits."""
    pass


@dataclass(frozen=True, slots=True)
class CashLedgerEntry:
    """
    Immutable double-entry cash ledger record.
    All monetary amounts are exact Decimals quantized to paise (0.01 INR).
    """
    entry_id: str
    trade_date: datetime.date
    entry_type: CashEntryType
    amount: Decimal             # Positive for cash credits/inflows; negative for debits/outflows
    balance_after: Decimal      # Running cash balance after entry posting
    description: str
    reference_id: Optional[str] = None
    circuit_evidence_present: bool = True
    metadata: Optional[Tuple[Tuple[str, str], ...]] = None


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """
    Immutable snapshot of an open security position.
    """
    instrument_id: str
    quantity: int
    average_entry_price: Decimal
    total_cost_basis: Decimal
    realized_net_pnl: Decimal
    market_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_gross_pnl: Decimal = Decimal("0.00")
    total_charges_paid: Decimal = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """
    Comprehensive mark-to-market valuation and risk snapshot for a trading session.
    """
    as_of_date: datetime.date
    cash_balance: Decimal
    invested_capital: Decimal
    total_portfolio_value: Decimal
    peak_portfolio_value: Decimal
    current_drawdown: Decimal
    max_drawdown: Decimal
    drawdown_duration_sessions: int
    open_positions_count: int
    positions: Tuple[PositionSnapshot, ...]
