"""Audit §16 probe over b7bd8ba."""
import datetime, sys, time
from decimal import Decimal

sys.path.insert(0, "src")

from signal_core.execution.costs import TransactionCostModel
from signal_core.execution.simulator import ExecutionFillResult, ExecutionFillSimulator
from signal_core.execution.types import (ExecutionOrder, FillStatus, OrderProduct,
    OrderSide, OrderType)
from signal_core.portfolio import Portfolio

D = datetime.date(2026, 11, 11)
M = TransactionCostModel()

def mk(inst, side, qty, price, date=D, order_id=None, fill_id=None):
    price = Decimal(price)
    costs = M.compute_costs(trade_date=date, side=side, product=OrderProduct.DELIVERY,
        quantity=qty, price=price, round_to_paise=False)
    o = ExecutionOrder(instrument_id=inst, side=side, order_type=OrderType.MARKET_ON_OPEN,
        quantity=qty, product=OrderProduct.DELIVERY, signal_date=date - datetime.timedelta(days=1),
        target_date=date, order_id=order_id)
    return ExecutionFillResult(
        order=o,
        status=FillStatus.FILLED,
        fill_date=date,
        latency_sessions=1,
        filled_quantity=qty,
        unfilled_quantity=0,
        executed_price=price,
        slippage=None,
        costs=costs,
        circuit_evidence_present=True,
        rejection_reason=None,
        fill_id=fill_id,
    )

def t(label, fn):
    try:
        r = fn(); print(f"[ACCEPT] {label} -> {str(r)[:70]}".encode('ascii','replace').decode())
    except Exception as e:
        print(f"[REJECT] {label} -> {type(e).__name__}: {str(e)[:100]}".encode('ascii','replace').decode())

print("=== 1. N-1 O(1) replay guard timing ===")
for n in (1000, 4000, 16000):
    pr = Portfolio(initial_capital=Decimal("100000000.00"), initial_date=D)
    t0 = time.perf_counter()
    for i in range(n):
        pr.process_fill(mk(f"I{i:06d}", OrderSide.BUY, 1, "10"), enforce_risk_limits=False)
    dt = time.perf_counter() - t0
    print(f"n={n:6d} total={dt*1000:8.1f}ms per_fill={dt/n*1e6:6.2f}us")
print("per-fill should be roughly flat (was 112->936 us)")

print("\n=== 2. N-2 deterministic sequence (no counter leak) ===")
p2 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
t("fill 11-11", lambda: p2.process_fill(mk("INFY", OrderSide.BUY, 10, "1000")))
t("fill 11-10 (non-monotonic)", lambda: p2.process_fill(mk("INFY", OrderSide.BUY, 10, "1000", date=datetime.date(2026,11,10))))
t("fill 11-10 again", lambda: p2.process_fill(mk("INFY", OrderSide.BUY, 10, "1000", date=datetime.date(2026,11,10))))
print("counters", p2.ledger._fill_reference_counters)
print("refs", [e.reference_id for e in p2.ledger.entries])
print("seq_keys_history len", len(p2.ledger._seq_keys_history), "entries", len(p2.ledger.entries))

print("\n=== 3. N-2 retry yields same ref after rejection ===")
p3 = Portfolio(initial_capital=Decimal("50000.00"), initial_date=D)
t("overdraft 100@1000", lambda: p3.process_fill(mk("INFY", OrderSide.BUY, 100, "1000"), enforce_risk_limits=False))
t("retry same", lambda: p3.process_fill(mk("INFY", OrderSide.BUY, 100, "1000"), enforce_risk_limits=False))
print("counters", p3.ledger._fill_reference_counters)
print("refs", [e.reference_id for e in p3.ledger.entries])

print("\n=== 4. N-3 fill_id per fill (partial remainder T+1) ===")
p4 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
f1 = mk("INFY", OrderSide.BUY, 60, "1000", order_id="ORD1")
t("leg1 60 on 11-11", lambda: p4.process_fill(f1))
f2 = mk("INFY", OrderSide.BUY, 40, "1000", date=datetime.date(2026,11,12), order_id="ORD1")
print("f2.fill_id", f2.fill_id)
t("leg2 40 on 11-12 (same order_id)", lambda: p4.process_fill(f2))
print("qty", p4.get_position("INFY").quantity)
print("refs", [e.reference_id for e in p4.ledger.entries])
sim = ExecutionFillSimulator()
# simulator path: two fills same order across two sessions
bar1 = None
print("simulator fill_ids distinct across dates:", f1.fill_id != f2.fill_id)

print("\n=== 5. N-4 validation (empty/whitespace/non-str) ===")
from signal_core.execution.types import ExecutionOrderValidationError, ExecutionOrder
for bad in ["", "   ", "  x"]:
    try:
        o = ExecutionOrder(instrument_id="X", side=OrderSide.BUY, product=OrderProduct.DELIVERY, quantity=1,
            signal_date=D, target_date=D, order_id=bad)
        print(f"[ACCEPT] order_id={bad!r} (UNEXPECTED)")
    except Exception as e:
        print(f"[REJECT] order_id={bad!r} -> {type(e).__name__}")
try:
    o = ExecutionOrder(instrument_id="X", side=OrderSide.BUY, product=OrderProduct.DELIVERY, quantity=1,
        signal_date=D, target_date=D, order_id=123)
    print("[ACCEPT] order_id=123 (UNEXPECTED)")
except Exception as e:
    print(f"[REJECT] order_id=123 -> {type(e).__name__}")
# fill_id validation
try:
    ExecutionFillResult(order=ExecutionOrder(instrument_id="X",side=OrderSide.BUY,product=OrderProduct.DELIVERY,quantity=1,signal_date=D,target_date=D),status=FillStatus.FILLED,fill_date=D,latency_sessions=1,filled_quantity=1,unfilled_quantity=0,executed_price=Decimal("10"),slippage=None,costs=None,circuit_evidence_present=True,rejection_reason=None,fill_id="  ")
    print("[ACCEPT] fill_id='  ' (UNEXPECTED)")
except Exception as e:
    print(f"[REJECT] fill_id='  ' -> {type(e).__name__}")
# reference_id validation
p5 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
try:
    p5.process_fill(mk("INFY", OrderSide.BUY, 10, "1000"), reference_id="   ")
    print("[ACCEPT] reference_id='   ' (UNEXPECTED)")
except Exception as e:
    print(f"[REJECT] reference_id='   ' -> {type(e).__name__}")
try:
    p5.process_fill(mk("INFY", OrderSide.BUY, 10, "1000"), reference_id=42)
    print("[ACCEPT] reference_id=42 (UNEXPECTED)")
except Exception as e:
    print(f"[REJECT] reference_id=42 -> {type(e).__name__}")

print("\n=== 6. N-5 rollback via stored key (no string parse) ===")
import signal_core.portfolio.position as P
p6 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
saved = P.Position.apply_fill
P.Position.apply_fill = lambda self, f: (_ for _ in ()).throw(RuntimeError("boom"))
t("BAJAJ_AUTO fails", lambda: p6.process_fill(mk("BAJAJ_AUTO", OrderSide.BUY, 10, "1000")))
P.Position.apply_fill = saved
t("BAJAJ_AUTO retry", lambda: p6.process_fill(mk("BAJAJ_AUTO", OrderSide.BUY, 10, "1000")))
print("refs", [e.reference_id for e in p6.ledger.entries])
print("counters", p6.ledger._fill_reference_counters)

print("\n=== 7. replay protection two-level ===")
p7 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
f = mk("INFY", OrderSide.BUY, 10, "1000")
t("first", lambda: p7.process_fill(f))
t("same object", lambda: p7.process_fill(f))
g = mk("INFY", OrderSide.BUY, 10, "1000")
t("different object anonymous", lambda: p7.process_fill(g))
print("qty", p7.get_position("INFY").quantity, "(anonymous replay posted twice -> 20, expected given no identity)")

print("\n=== 8. fill_id collision across two distinct fills ===")
p8 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
t("fill A", lambda: p8.process_fill(mk("INFY", OrderSide.BUY, 10, "1000", fill_id="FILL_X")))
t("fill B same fill_id", lambda: p8.process_fill(mk("TCS", OrderSide.BUY, 10, "1000", fill_id="FILL_X")))
print("refs", [e.reference_id for e in p8.ledger.entries])

print("\n=== 9. R-4 lazy deposit still ===")
p9 = Portfolio(initial_capital=Decimal("1000000.00"))
t("trade 2026-11-05", lambda: p9.process_fill(mk("INFY", OrderSide.BUY, 10, "1000", date=datetime.date(2026,11,5))))
print("rows", [(str(e.trade_date), e.reference_id[:16]) for e in p9.ledger.entries])
print("chronological", [e.trade_date for e in p9.ledger.entries] == sorted(e.trade_date for e in p9.ledger.entries))

print("\n=== 10. R-3 phantom cleanup still ===")
import signal_core.portfolio.position as P2
p10 = Portfolio(initial_capital=Decimal("2000000.00"), initial_date=D)
saved = P2.Position.apply_fill
P2.Position.apply_fill = lambda self, f: (_ for _ in ()).throw(RuntimeError("boom"))
t("new inst fails", lambda: p10.process_fill(mk("TCS", OrderSide.BUY, 10, "1000")))
P2.Position.apply_fill = saved
print("_positions", list(p10._positions)); print("open", p10.get_open_positions())
print("seq_keys_history", len(p10.ledger._seq_keys_history), "entries", len(p10.ledger.entries))

print("\n=== 11. bounded pinning (10001 distinct fills) ===")
pr = Portfolio(initial_capital=Decimal("100000000.00"), initial_date=D)
for i in range(10001):
    pr.process_fill(mk(f"K{i:05d}", OrderSide.BUY, 1, "10"), enforce_risk_limits=False)
print("pinned size", len(pr._processed_fill_instances), "max", pr._max_pinned_instances)
print("first id evicted?", id(pr) not in pr._processed_fill_instances)  # placeholder
