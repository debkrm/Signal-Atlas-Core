"""Authoritative Cash Ledger for Indian Equity Portfolios.

Enforces exact Decimal arithmetic, contract-note paise quantization (0.01 INR),
chronological date monotonicity, idempotency / unique reference constraints,
overdraft protection, and unverified circuit evidence disclosure tracking.
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Sequence, Set, Tuple

from signal_core.execution.simulator import ExecutionFillResult
from signal_core.execution.types import FillStatus, OrderSide
from signal_core.portfolio.types import (
    CashEntryType,
    CashLedgerEntry,
    LedgerValidationError,
)

PAISE_PRECISION = Decimal("0.01")
UNVERIFIED_CIRCUIT_WARNING = (
    "UNVERIFIED_CIRCUIT_EVIDENCE: Fill executed without verified exchange circuit band evidence."
)


def _quantize_paise(val: Decimal) -> Decimal:
    """Quantizes a Decimal monetary quantity to exact paise (0.01 INR) via ROUND_HALF_UP."""
    if isinstance(val, bool) or not isinstance(val, Decimal) or not val.is_finite():
        raise LedgerValidationError(f"Expected finite Decimal monetary value, got {val!r}")
    return val.quantize(PAISE_PRECISION, rounding=ROUND_HALF_UP)


class CashLedger:
    """
    Authoritative Single-Entry Cash Book & Ledger.
    Tracks all capital flows, trade settlements, brokerage fees, and statutory taxes.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("0.00"),
        allow_overdraft: bool = False,
        initial_date: Optional[datetime.date] = None,
    ) -> None:
        if isinstance(initial_capital, bool) or not isinstance(initial_capital, Decimal) or not initial_capital.is_finite() or initial_capital < 0:
            raise LedgerValidationError(f"initial_capital must be non-negative Decimal, got {initial_capital!r}")

        self._allow_overdraft = allow_overdraft
        self._entries: List[CashLedgerEntry] = []
        self._current_cash = Decimal("0.00")
        self._entry_counter = 0
        self._posted_reference_ids: Set[str] = set()
        self._last_trade_date: Optional[datetime.date] = initial_date

        initial_quantized = _quantize_paise(initial_capital)
        if initial_quantized > Decimal("0.00"):
            deposit_date = initial_date if initial_date is not None else datetime.date.today()
            self._post_entry(
                trade_date=deposit_date,
                entry_type=CashEntryType.CAPITAL_DEPOSIT,
                amount=initial_quantized,
                description="Initial Capital Deposit",
                reference_id="INIT_DEPOSIT",
                circuit_evidence_present=True,
                metadata=None,
            )
            # If initial_date was None, leave _last_trade_date unset so the first real trade can set it
            if initial_date is None:
                self._last_trade_date = None

    @property
    def current_cash(self) -> Decimal:
        return self._current_cash

    @property
    def allow_overdraft(self) -> bool:
        return self._allow_overdraft

    @property
    def entries(self) -> Tuple[CashLedgerEntry, ...]:
        return tuple(self._entries)

    def deposit(
        self,
        trade_date: datetime.date,
        amount: Decimal,
        description: str = "Capital Deposit",
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """Deposits cash capital into the ledger."""
        if type(trade_date) is not datetime.date:
            raise LedgerValidationError(f"trade_date must be exact datetime.date, got {type(trade_date).__name__}")
        paise_amount = _quantize_paise(amount)
        if paise_amount <= Decimal("0.00"):
            raise LedgerValidationError(f"Deposit amount must be positive, got {amount!r}")

        return self._post_entry(
            trade_date=trade_date,
            entry_type=CashEntryType.CAPITAL_DEPOSIT,
            amount=paise_amount,
            description=description,
            reference_id=reference_id,
            circuit_evidence_present=True,
            metadata=None,
        )

    def withdraw(
        self,
        trade_date: datetime.date,
        amount: Decimal,
        description: str = "Capital Withdrawal",
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """Withdraws cash capital from the ledger."""
        if type(trade_date) is not datetime.date:
            raise LedgerValidationError(f"trade_date must be exact datetime.date, got {type(trade_date).__name__}")
        paise_amount = _quantize_paise(amount)
        if paise_amount <= Decimal("0.00"):
            raise LedgerValidationError(f"Withdrawal amount must be positive, got {amount!r}")

        return self._post_entry(
            trade_date=trade_date,
            entry_type=CashEntryType.CAPITAL_WITHDRAWAL,
            amount=-paise_amount,
            description=description,
            reference_id=reference_id,
            circuit_evidence_present=True,
            metadata=None,
        )

    def record_fill(
        self,
        fill: ExecutionFillResult,
        description: Optional[str] = None,
        reference_id: Optional[str] = None,
    ) -> CashLedgerEntry:
        """
        Posts the complete cash impact of an executed trade fill into the ledger.
        
        Enforces:
        - Exact contract-note paise quantization (0.01 INR) at the posting boundary.
        - Outflow accounting for BUY (net cash flow negative).
        - Inflow accounting for SELL (net cash flow positive).
        - Explicit tracking of circuit evidence provenance.
        - Idempotency via unique reference_id enforcement.
        - Fail-closed cash overdraft protection.
        """
        if not isinstance(fill, ExecutionFillResult):
            raise LedgerValidationError(f"Expected ExecutionFillResult, got {type(fill)}")

        if fill.status not in (FillStatus.FILLED, FillStatus.PARTIALLY_FILLED):
            raise LedgerValidationError(
                f"Cannot post non-fill outcome '{fill.status.value}' to cash ledger: {fill.rejection_reason}"
            )

        if fill.costs is None:
            raise LedgerValidationError("ExecutionFillResult lacks required TransactionCostBreakdown.")

        # Ensure costs are quantized to paise per Rule 6.4 and E-6
        paise_costs = fill.costs.to_paise()
        net_flow = paise_costs.net_cash_flow

        # Format metadata and circuit evidence disclosure
        meta_items: List[Tuple[str, str]] = [
            ("instrument_id", fill.order.instrument_id),
            ("side", fill.order.side.value),
            ("product", fill.order.product.value),
            ("quantity", str(fill.filled_quantity)),
            ("price", str(fill.executed_price)),
            ("gross_amount", str(paise_costs.gross_amount)),
            ("brokerage", str(paise_costs.brokerage)),
            ("total_taxes", str(paise_costs.total_statutory_taxes)),
            ("total_charges", str(paise_costs.total_charges)),
            ("circular_ref", paise_costs.circular_ref),
        ]
        if not fill.circuit_evidence_present:
            meta_items.append(("circuit_warning", UNVERIFIED_CIRCUIT_WARNING))

        if description is None:
            action_desc = "Buy" if fill.order.side == OrderSide.BUY else "Sell"
            desc = f"{action_desc} {fill.filled_quantity} {fill.order.instrument_id} @ ₹{fill.executed_price}"
        else:
            desc = description

        entry_type = (
            CashEntryType.TRADE_BUY_OUTFLOW
            if fill.order.side == OrderSide.BUY
            else CashEntryType.TRADE_SELL_INFLOW
        )

        ref_id = reference_id if reference_id is not None else f"FILL_{fill.order.instrument_id}_{fill.fill_date}"

        return self._post_entry(
            trade_date=fill.fill_date,
            entry_type=entry_type,
            amount=net_flow,
            description=desc,
            reference_id=ref_id,
            circuit_evidence_present=fill.circuit_evidence_present,
            metadata=tuple(meta_items),
        )

    def _post_entry(
        self,
        trade_date: datetime.date,
        entry_type: CashEntryType,
        amount: Decimal,
        description: str,
        reference_id: Optional[str],
        circuit_evidence_present: bool,
        metadata: Optional[Tuple[Tuple[str, str], ...]],
    ) -> CashLedgerEntry:
        if type(trade_date) is not datetime.date:
            raise LedgerValidationError(f"trade_date must be exact datetime.date, got {type(trade_date).__name__}")

        if self._last_trade_date is not None and trade_date < self._last_trade_date:
            raise LedgerValidationError(
                f"Non-monotonic trade_date: cannot post entry for date {trade_date} "
                f"after existing entry on {self._last_trade_date}."
            )

        if reference_id is not None and reference_id in self._posted_reference_ids:
            raise LedgerValidationError(
                f"Duplicate entry rejected: reference_id '{reference_id}' already posted to ledger."
            )

        new_balance = self._current_cash + amount
        if not self._allow_overdraft and new_balance < Decimal("0.00"):
            raise LedgerValidationError(
                f"Cash overdraft prohibited: posting amount ₹{amount} against current cash "
                f"₹{self._current_cash} would produce negative balance ₹{new_balance}."
            )

        self._entry_counter += 1
        entry_id = f"TXN_{self._entry_counter:06d}"
        entry = CashLedgerEntry(
            entry_id=entry_id,
            trade_date=trade_date,
            entry_type=entry_type,
            amount=amount,
            balance_after=new_balance,
            description=description,
            reference_id=reference_id,
            circuit_evidence_present=circuit_evidence_present,
            metadata=metadata,
        )

        if reference_id is not None:
            self._posted_reference_ids.add(reference_id)
        self._last_trade_date = trade_date
        self._current_cash = new_balance
        self._entries.append(entry)
        return entry

    def _rollback_last_entry(self) -> CashLedgerEntry:
        """
        Rolls back the most recently posted entry to guarantee atomicity on failed operations.
        """
        if not self._entries:
            raise LedgerValidationError("Cannot rollback: ledger is empty.")
        entry = self._entries.pop()
        self._current_cash -= entry.amount
        self._entry_counter -= 1
        if entry.reference_id is not None:
            self._posted_reference_ids.discard(entry.reference_id)
        if self._entries:
            self._last_trade_date = self._entries[-1].trade_date
        else:
            self._last_trade_date = None
        return entry
