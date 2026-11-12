"""
Unit Tests for Strategy Contracts, Order Intent Validation, and Zero Lookahead Invariants (Phase 2C).

Covers:
- Strict validation of OrderIntent parameters, sizing, and immutability.
- Gate G2C-2: Rejection of same-session (T close -> T fill) or backward-dated execution intents.
- Rejection of datetime.datetime leakage into signal_date or target_date.
- Conversion of OrderIntent to ExecutionOrder for single execution simulator path.
- Reference TechnicalCrossStrategy signal generation logic.
"""

import datetime
from decimal import Decimal
import pytest

from signal_core.execution.types import OrderProduct, OrderSide, OrderType
from signal_core.features.engine import InstrumentTechnicalFeatures
from signal_core.strategy.base import (
    LookaheadIntentError,
    OrderIntent,
    OrderIntentValidationError,
    TechnicalCrossStrategy,
)


def test_order_intent_valid_creation():
    d1 = datetime.date(2024, 1, 8)
    d2 = datetime.date(2024, 1, 9)

    # Valid with quantity
    intent_qty = OrderIntent(
        instrument_id="INE009A01021",
        signal_date=d1,
        target_date=d2,
        side=OrderSide.BUY,
        quantity=100,
        intent_id="INT-1",
    )
    assert intent_qty.instrument_id == "INE009A01021"
    assert intent_qty.signal_date == d1
    assert intent_qty.target_date == d2
    assert intent_qty.quantity == 100
    assert intent_qty.target_weight is None

    # Valid with target_weight
    intent_weight = OrderIntent(
        instrument_id="INE009A01021",
        signal_date=d1,
        target_date=d2,
        side=OrderSide.BUY,
        target_weight=Decimal("0.15"),
        intent_id="INT-2",
    )
    assert intent_weight.target_weight == Decimal("0.15")
    assert intent_weight.quantity is None


def test_order_intent_lookahead_rejection_gate_g2c_2():
    d1 = datetime.date(2024, 1, 8)

    # 1. Same-session execution (T close -> T fill) MUST raise LookaheadIntentError
    with pytest.raises(LookaheadIntentError, match=r"Gate G2C-2"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d1,
            side=OrderSide.BUY,
            quantity=100,
        )

    # 2. Backward-dated execution (T close -> T-1 fill) MUST raise LookaheadIntentError
    d_prev = datetime.date(2024, 1, 7)
    with pytest.raises(LookaheadIntentError, match=r"Gate G2C-2"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d_prev,
            side=OrderSide.BUY,
            quantity=100,
        )


def test_order_intent_date_type_safety():
    d1 = datetime.date(2024, 1, 8)
    dt1 = datetime.datetime(2024, 1, 8, 15, 30)
    d2 = datetime.date(2024, 1, 9)

    # datetime.datetime in signal_date rejected
    with pytest.raises(OrderIntentValidationError, match="signal_date must be genuine datetime.date"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=dt1,  # type: ignore
            target_date=d2,
            side=OrderSide.BUY,
            quantity=100,
        )

    # datetime.datetime in target_date rejected
    with pytest.raises(OrderIntentValidationError, match="target_date must be genuine datetime.date"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=dt1,  # type: ignore
            side=OrderSide.BUY,
            quantity=100,
        )


def test_order_intent_sizing_validation():
    d1 = datetime.date(2024, 1, 8)
    d2 = datetime.date(2024, 1, 9)

    # Neither quantity nor weight
    with pytest.raises(OrderIntentValidationError, match="must specify either quantity or target_weight"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
        )

    # Both quantity and weight
    with pytest.raises(OrderIntentValidationError, match="cannot specify both quantity and target_weight"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
            quantity=100,
            target_weight=Decimal("0.10"),
        )

    # Non-positive quantity
    with pytest.raises(OrderIntentValidationError, match="quantity must be a positive integer"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
            quantity=0,
        )

    # Boolean quantity rejected
    with pytest.raises(OrderIntentValidationError, match="quantity must be a positive integer"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
            quantity=True,  # type: ignore
        )

    # Invalid weight (<= 0 or > 1.0)
    with pytest.raises(OrderIntentValidationError, match="target_weight must be a finite Decimal in"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
            target_weight=Decimal("0.00"),
        )
    with pytest.raises(OrderIntentValidationError, match="target_weight must be a finite Decimal in"):
        OrderIntent(
            instrument_id="INE009A01021",
            signal_date=d1,
            target_date=d2,
            side=OrderSide.BUY,
            target_weight=Decimal("1.05"),
        )


def test_order_intent_to_execution_order():
    d1 = datetime.date(2024, 1, 8)
    d2 = datetime.date(2024, 1, 9)

    # Fixed quantity intent
    intent = OrderIntent(
        instrument_id="INE009A01021",
        signal_date=d1,
        target_date=d2,
        side=OrderSide.BUY,
        quantity=50,
        intent_id="INT-50",
    )
    order = intent.to_execution_order()
    assert order.instrument_id == "INE009A01021"
    assert order.quantity == 50
    assert order.signal_date == d1
    assert order.target_date == d2
    assert order.order_id == "INT-50"

    # Target weight intent requires computed_quantity
    intent_w = OrderIntent(
        instrument_id="INE009A01021",
        signal_date=d1,
        target_date=d2,
        side=OrderSide.BUY,
        target_weight=Decimal("0.20"),
    )
    with pytest.raises(OrderIntentValidationError, match="valid positive quantity required"):
        intent_w.to_execution_order()

    order_w = intent_w.to_execution_order(computed_quantity=75, order_id="ORD-CALC-75")
    assert order_w.quantity == 75
    assert order_w.order_id == "ORD-CALC-75"


def test_technical_cross_strategy_signal_generation():
    d1 = datetime.date(2024, 1, 8)
    d2 = datetime.date(2024, 1, 9)

    strat = TechnicalCrossStrategy(
        strategy_id="TEST-STRAT",
        fast_indicator="sma_20",
        slow_indicator="sma_50",
        allocation_weight=Decimal("0.25"),
    )
    assert strat.strategy_id == "TEST-STRAT"
    assert strat.parameters["allocation_weight"] == "0.25"

    # Create mock features
    feat_bullish = InstrumentTechnicalFeatures(
        instrument_id="INE009A01021",
        trade_date=d1,
        open=Decimal("1500.00"),
        high=Decimal("1520.00"),
        low=Decimal("1490.00"),
        close=Decimal("1515.00"),
        volume=100000,
        sma_20=Decimal("1505.00"),
        sma_50=Decimal("1480.00"),
    )
    feat_bearish = InstrumentTechnicalFeatures(
        instrument_id="INE002A01018",
        trade_date=d1,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2450.00"),
        close=Decimal("2460.00"),
        volume=200000,
        sma_20=Decimal("2490.00"),
        sma_50=Decimal("2480.00"),
    )

    features = {
        "INE009A01021": feat_bullish,
        "INE002A01018": feat_bearish,
    }

    intents = strat.generate_signals(
        as_of=d1,
        next_session=d2,
        universe=["INE009A01021", "INE002A01018"],
        features=features,
    )

    assert len(intents) == 2
    buy_intent = next(i for i in intents if i.instrument_id == "INE009A01021")
    assert buy_intent.side == OrderSide.BUY
    assert buy_intent.signal_date == d1
    assert buy_intent.target_date == d2
    assert buy_intent.target_weight == Decimal("0.25")

    sell_intent = next(i for i in intents if i.instrument_id == "INE002A01018")
    assert sell_intent.side == OrderSide.SELL
    assert sell_intent.signal_date == d1
    assert sell_intent.target_date == d2
