"""
Unit tests for the Audit §73 remediation items (audit §73 at 46a0d08, reviewing 9171464).

Target invariants:
- H-125: a partial SELL (trim, or a partially filled stop) leaves the protective stop armed for the
  residual quantity at the same entry-fixed price, a merger / ISIN transition carries the stop onto
  the successor ISIN rescaled by the exchange ratio, and a position that crosses an identity change
  without protection is counted rather than silently dropped.
- N-130: `--no-record-trial` (record_trial=False) refuses a configuration the registry does not
  already record, and an unrecorded artifact says `"recorded": false` in its own bytes.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_types import OrderSide, OrderType
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import (
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
)
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.research.trials import TrialRegistry
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from signal_core.storage.security_master import CorporateAction, CorporateActionType
from scripts.run_phase3b2_walkforward import (
    build_authoritative_runner,
    carry_protective_stop_across_corporate_action,
    run_phase3b2_walkforward,
)

ISIN = "INE001A01036"
SUCCESSOR_ISIN = "INE001A01044"
SIGNAL_SESSION = datetime.date(2024, 1, 16)
ENTRY_SESSION = datetime.date(2024, 1, 17)


def _criteria():
    return load_go_no_go_criteria()


def _calendar():
    return load_anchored_nse_trading_calendar(criteria=_criteria())


def _portfolio(initial: str = "1000000.00") -> Portfolio:
    return Portfolio(
        initial_capital=Decimal(initial),
        criteria=_criteria(),
        initial_date=SIGNAL_SESSION,
    )


def _runner(portfolio: Portfolio, k: str = "2.0") -> DailyTPlus1OrderRunner:
    return build_authoritative_runner(
        portfolio=portfolio,
        simulator=ExecutionFillSimulator(criteria=_criteria()),
        calendar=_calendar(),
        criteria=_criteria(),
        atr_stop_multiple=Decimal(k),
    )


def _band(trade_date: datetime.date) -> PriceBandRecord:
    return PriceBandRecord(
        isin=ISIN,
        trade_date=trade_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal("900.00"),
    )


def _bar(
    trade_date: datetime.date,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: int = 100000,
) -> PriceBar:
    return PriceBar(
        instrument_id=ISIN,
        trade_date=trade_date,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        traded_value=Decimal(close) * Decimal(volume),
    )


def _buy(
    runner: DailyTPlus1OrderRunner,
    target: datetime.date,
    bar: PriceBar,
    allocation: str = "0.05",
):
    """Entry reference 1000 with ATR 20 at k=2.0 arms a 960 stop for the filled quantity."""
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=bar.volume,
        series="EQ",
        allocation_weight=Decimal(allocation),
        metadata={"intent_id": "S73-BUY"},
    )
    return runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=bar,
        target_date=target,
        price_band=_band(target),
        explicit_series=ExchangeSeries.EQ,
    )


# --- H-125: a partial SELL must not retire protection for the shares it leaves behind ------


def test_h125_trim_keeps_the_stop_for_the_residual_quantity():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    entry = _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))
    assert entry.status == FillStatus.FILLED
    assert runner.protective_stops[ISIN].quantity == 50
    assert runner.protective_stops[ISIN].stop_price == Decimal("960.000")

    trim_session = datetime.date(2024, 1, 18)
    trim = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=ENTRY_SESSION,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=100000,
        series="EQ",
        sell_quantity=20,
        metadata={"exit_reason": "MAX_POSITION_WEIGHT_TRIM"},
    )
    trim_ticket = runner.run_candidate(
        candidate=trim,
        t_plus_1_bar=_bar(trim_session, "1005.00", "1010.00", "1000.00", "1005.00"),
        target_date=trim_session,
        price_band=_band(trim_session),
        explicit_series=ExchangeSeries.EQ,
    )
    assert trim_ticket.status == FillStatus.FILLED
    assert trim_ticket.fill_result.filled_quantity == 20
    assert portfolio.get_position(ISIN).quantity == 30

    # The audit's probe: the stop survives the trim, for exactly the residual 30 shares, at the
    # price fixed at entry (not recomputed from the trim session's close).
    stop = runner.protective_stops[ISIN]
    assert stop.quantity == 30
    assert stop.stop_price == Decimal("960.000")
    assert stop.signal_date == SIGNAL_SESSION
    assert stop.armed_session == ENTRY_SESSION
    assert stop.atr == Decimal("20.00")

    # ... and it still fills on a later gap through it, for 30 shares, not 50 and not nothing.
    gap_session = datetime.date(2024, 1, 19)
    result = runner.evaluate_protective_stops(
        session_date=gap_session,
        bars={ISIN: _bar(gap_session, "940.00", "950.00", "930.00", "945.00")},
        price_bands={ISIN: _band(gap_session)},
    )
    assert result.filled_count == 1
    assert result.tickets[0].fill_result.filled_quantity == 30
    assert portfolio.get_position(ISIN).quantity == 0
    assert runner.protective_stops == {}


def test_h125_partial_stop_fill_keeps_the_stop_for_the_remainder():
    """A volume-capped stop sell leaves shares behind; the remainder stays protected."""
    # A large book is needed for the 3% participation cap to bind on a single order: at the small
    # book the cap always exceeds the position, which is why the session evaluator does not request
    # partial fills and defers instead (§5.3). This probes the fill path directly.
    portfolio = _portfolio("30000000.00")
    runner = _runner(portfolio, k="2.0")
    _buy(
        runner,
        ENTRY_SESSION,
        _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"),
        allocation="0.09",
    )
    held = runner.protective_stops[ISIN].quantity
    assert held == 2700

    stop_session = datetime.date(2024, 1, 18)
    # ₹5.67 crore of turnover clears the ₹5 crore liquidity floor while letting the 3% participation
    # cap bind at 1,800 shares against a 2,700-share stop.
    bar = _bar(stop_session, "950.00", "955.00", "940.00", "945.00", volume=60000)
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=ENTRY_SESSION,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("960.000"),
        atr=Decimal("20.00"),
        session_volume=bar.volume,
        series="EQ",
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("960.000"),
        sell_quantity=held,
        allow_partial_fill=True,
        metadata={"exit_reason": "STOP_LOSS"},
    )
    ticket = runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=bar,
        target_date=stop_session,
        price_band=_band(stop_session),
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket.status == FillStatus.PARTIALLY_FILLED
    filled = ticket.fill_result.filled_quantity
    assert 0 < filled < held
    residual = held - filled
    stop = runner.protective_stops[ISIN]
    assert portfolio.get_position(ISIN).quantity == residual
    assert stop.quantity == residual
    assert stop.stop_price == Decimal("960.000")


def test_h125_merger_carries_the_stop_to_the_successor_isin():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    # 2 successor shares per 1 held share: quantity doubles, the stop price halves with the lot's
    # restated entry price, so the economic distance is unchanged.
    merger = CorporateAction(
        isin=ISIN,
        ex_date=datetime.date(2024, 1, 18),
        action_type=CorporateActionType.MERGER,
        ratio_numerator=Decimal("2"),
        ratio_denominator=Decimal("1"),
        new_isin=SUCCESSOR_ISIN,
        delisting_price=Decimal("500.00"),
        description="S73 synthetic merger",
    )
    assert carry_protective_stop_across_corporate_action(runner, merger) is True

    assert ISIN not in runner.protective_stops
    moved = runner.protective_stops[SUCCESSOR_ISIN]
    assert moved.stop_price == Decimal("480.0000")
    assert moved.quantity == 100
    assert moved.signal_date == SIGNAL_SESSION
    assert moved.atr == Decimal("10.0000")


def test_h125_isin_transition_carries_the_stop_at_the_same_price_scale():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    transition = CorporateAction(
        isin=ISIN,
        ex_date=datetime.date(2024, 1, 18),
        action_type=CorporateActionType.ISIN_TRANSITION,
        old_isin=ISIN,
        new_isin=SUCCESSOR_ISIN,
        description="S73 synthetic ISIN transition",
    )
    assert carry_protective_stop_across_corporate_action(runner, transition) is True
    moved = runner.protective_stops[SUCCESSOR_ISIN]
    assert moved.stop_price == Decimal("960.0000")
    assert moved.quantity == 50


def test_h125_identity_change_without_a_stop_is_reported_not_silent():
    """The False return is what the run counts as `unprotected_corporate_action_positions`."""
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    assert runner.protective_stops == {}

    transition = CorporateAction(
        isin=ISIN,
        ex_date=datetime.date(2024, 1, 18),
        action_type=CorporateActionType.ISIN_TRANSITION,
        old_isin=ISIN,
        new_isin=SUCCESSOR_ISIN,
    )
    assert carry_protective_stop_across_corporate_action(runner, transition) is False

    # A successor identity that already carries its own stop cannot host a second order for the
    # same lot: the incoming stop is retired and the position is counted as unprotected.
    runner.arm_protective_stop(
        instrument_id=SUCCESSOR_ISIN,
        stop_price=Decimal("480.0000"),
        quantity=10,
        signal_date=SIGNAL_SESSION,
        armed_session=ENTRY_SESSION,
        atr=Decimal("10.00"),
    )
    runner.arm_protective_stop(
        instrument_id=ISIN,
        stop_price=Decimal("960.000"),
        quantity=50,
        signal_date=SIGNAL_SESSION,
        armed_session=ENTRY_SESSION,
        atr=Decimal("20.00"),
    )
    assert carry_protective_stop_across_corporate_action(runner, transition) is False
    assert ISIN not in runner.protective_stops
    assert runner.protective_stops[SUCCESSOR_ISIN].stop_price == Decimal("480.0000")


# --- N-130: the sweep path is either registered or refused --------------------------------


def _snapshot(tmp_path: Path, num_sessions: int = 120) -> Path:
    """Deterministic swing-inducing tape: rising ~20 sessions, then falling ~20, repeating."""
    criteria = _criteria()
    cal = load_anchored_nse_trading_calendar(criteria=criteria)
    sessions = cal.sessions_in_range(datetime.date(2022, 1, 3), datetime.date(2022, 12, 30))[:num_sessions]

    symbols = {"UUID-INFY": "INFY", "UUID-TCS": "TCS", "UUID-RIL": "RELIANCE"}
    prices = {}
    for u, sym in symbols.items():
        base_p = 1000 if sym == "INFY" else (3000 if sym == "TCS" else 2000)
        bars = []
        for i, s in enumerate(sessions):
            leg = (i % 40)
            drift = leg * 12 if leg < 20 else (39 - leg) * 12
            p = base_p + drift
            bars.append({
                "trade_date": s.isoformat(),
                "open": f"{p}.00",
                "high": f"{p + 10}.00",
                "low": f"{p - 10}.00",
                "close": f"{p + 5}.00",
                "volume": "100000.000000",
                "raw_volume": 100000,
                "traded_value": f"{(p + 5) * 100000}.00",
                "cumulative_multiplier": "1.000000",
                "prev_close": f"{p}.00",
                "prev_close_multiplier": "1.000000",
                "raw_prev_close": f"{p}.00",
                "adjustment_version": "v1.4",
            })
        prices[u] = bars

    bench = []
    for i, s in enumerate(sessions):
        p = 17000 + (i % 40) * 20
        bench.append({
            "trade_date": s.isoformat(),
            "open": f"{p}.00",
            "high": f"{p + 50}.00",
            "low": f"{p - 20}.00",
            "close": f"{p + 30}.00",
            "volume": "50000.000000",
            "raw_volume": 50000,
            "traded_value": f"{(p + 30) * 50000}.00",
            "cumulative_multiplier": "1.000000",
            "prev_close": f"{p}.00",
            "prev_close_multiplier": "1.000000",
            "raw_prev_close": f"{p}.00",
            "adjustment_version": "v1.4",
        })

    data = {
        "snapshot_format": "signal-atlas-dataset-snapshot-v1",
        "data_version": "EXP-DEV-SYNTHETIC-S73",
        "source_identity": "NSE_BHAVCOPY_DAILY",
        "content_fingerprint": "DATA-CTNT-V2-s73synthetic1234567890",
        "session_count": len(sessions),
        "instrument_count": len(symbols),
        "trading_dates": [s.isoformat() for s in sessions],
        "symbols_by_instrument": symbols,
        "universe_by_date": {s.isoformat(): list(symbols.keys()) for s in sessions},
        "prices_by_instrument": prices,
        "benchmark_prices": bench,
    }
    snap_file = tmp_path / "synthetic_s73_snapshot.json"
    snap_file.write_text(json.dumps(data), encoding="utf-8")
    return snap_file


def test_n130_rerender_of_an_unregistered_configuration_is_refused(tmp_path: Path):
    snap = _snapshot(tmp_path)
    registry_path = tmp_path / "trial_reg.jsonl"
    trial_id = "TRIAL-S73-N130"

    # Register the k=2.0 configuration exactly once.
    run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=registry_path,
        verdict_output_dir=tmp_path / "v_recorded",
        trial_id=trial_id,
        max_sessions=120,
        in_sample_only=True,
        hypothesis="S73 N-130 probe",
        rationale="Registers the k=2.0 configuration so the re-render guard has a row to match.",
        atr_stop_multiple=Decimal("2.0"),
    )
    assert TrialRegistry(registry_path).total_trial_count == 1

    # A re-render of the same configuration is allowed and says it is unrecorded.
    run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=registry_path,
        verdict_output_dir=tmp_path / "v_rerender",
        trial_id=trial_id,
        max_sessions=120,
        in_sample_only=True,
        record_trial=False,
        atr_stop_multiple=Decimal("2.0"),
    )
    artifact = json.loads(
        (tmp_path / "v_rerender" / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["recorded"] is False
    assert artifact["trial_id"] == trial_id
    recorded_artifact = json.loads(
        (tmp_path / "v_recorded" / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    assert recorded_artifact["recorded"] is True
    # No new row was appended by the re-render.
    assert TrialRegistry(registry_path).total_trial_count == 1

    # The audit's probe: the same trial_id at an unregistered ATR multiple must exit non-zero
    # instead of writing an artifact that impersonates a registered trial.
    with pytest.raises(ValueError, match="does not reproduce its registered canonical parameters"):
        run_phase3b2_walkforward(
            snapshot_path=snap,
            registry_path=registry_path,
            verdict_output_dir=tmp_path / "v_sweep",
            trial_id=trial_id,
            max_sessions=120,
            in_sample_only=True,
            record_trial=False,
            atr_stop_multiple=Decimal("3.0"),
        )
    assert not (tmp_path / "v_sweep").exists()

    # An indicator change is a parameter variation too.
    with pytest.raises(ValueError, match="does not reproduce its registered canonical parameters"):
        run_phase3b2_walkforward(
            snapshot_path=snap,
            registry_path=registry_path,
            verdict_output_dir=tmp_path / "v_sweep2",
            trial_id=trial_id,
            max_sessions=120,
            in_sample_only=True,
            record_trial=False,
            fast_indicator="ema_10",
        )


def test_n130_rerender_whose_sharpe_disagrees_with_the_ledger_is_refused(tmp_path: Path):
    """Matching parameters are not enough: the re-render must reproduce the scored figure."""
    snap = _snapshot(tmp_path)
    registry_path = tmp_path / "trial_reg.jsonl"
    recorded_id = "TRIAL-S73-N130-TRUE"
    run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=registry_path,
        verdict_output_dir=tmp_path / "v_true",
        trial_id=recorded_id,
        max_sessions=120,
        in_sample_only=True,
        # Fixed clock: the falsified row below is dated 23:59, and the registry refuses a
        # non-monotonic timestamp, so this run must not inherit the wall clock.
        now_utc="2026-11-16T12:00:00+00:00",
    )

    registry = TrialRegistry(registry_path)
    parent = next(t for t in registry.get_trials() if t.trial_id == recorded_id)
    falsified_id = "TRIAL-S73-N130-FALSIFIED"
    registry.append_trial(
        trial_id=falsified_id,
        hypothesis="S73 N-130 probe",
        rationale="Same configuration as the recorded run, with a deliberately wrong scored figure.",
        partition="IN_SAMPLE",
        canonical_params=dict(parent.canonical_params),
        fold_spec_fingerprint=parent.fold_spec_fingerprint,
        dataset_fingerprint=parent.dataset_fingerprint,
        criteria_version=parent.criteria_version,
        timestamp_utc="2026-11-16T23:59:00+00:00",
    )
    registry.append_trial_evaluation(
        trial_id=falsified_id,
        sharpe_ratio=Decimal("0.5"),
        returns_digest="RET-V1-s73falsified",
        observation_count=119,
        evaluated_at_utc="2026-11-16T23:59:00+00:00",
    )

    with pytest.raises(ValueError, match="recomputes annualized_sharpe"):
        run_phase3b2_walkforward(
            snapshot_path=snap,
            registry_path=registry_path,
            verdict_output_dir=tmp_path / "v_falsified",
            trial_id=falsified_id,
            max_sessions=120,
            in_sample_only=True,
            record_trial=False,
        )
    assert not (tmp_path / "v_falsified").exists()


def test_n130_unprotected_corporate_action_counter_is_surfaced(tmp_path: Path):
    """The counter a reader needs never has to be inferred from an absent stop."""
    snap = _snapshot(tmp_path)
    artifact_dir = tmp_path / "verdicts"
    res = run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=artifact_dir,
        trial_id="TRIAL-S73-CA-COUNTER",
        max_sessions=120,
        in_sample_only=True,
    )
    artifact = json.loads(
        (artifact_dir / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(encoding="utf-8")
    )
    assert artifact["unprotected_corporate_action_positions"] == 0
    assert res.unprotected_corporate_action_positions == 0
