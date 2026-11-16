"""
Unit tests for the Audit §72 remediation items (audit §72 at 05806ae, reviewing 5176bc5).

Target invariants:
- H-124: one value of `atr_stop_multiple` reaches DailyTPlus1OrderRunner, governs sizing (so it
  changes fill quantity only when the risk leg binds, i.e. ATR/price > 0.125/k) and is the value the
  trial row records.
- Ruling 1: a protective T+1 STOP_LOSS order is persisted at entry, evaluated bar-by-bar through the
  single authoritative simulator (gap -> open, intraday -> stop price), deferred rather than filled
  when the session's bid side is frozen at the lower circuit (§5.3), and cancelled by a signal exit.
- N-128: the registry-manifest evaluation witness is mandatory (an explicit 0 is a witnessed zero),
  a post-sidecar artifact with a nulled score is refused, and the committed manifest carries a
  criteria pin.
- N-129: the artifact's `closed_trades` array reproduces the reported mean net expectancy and
  statutory costs to the paisa.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from signal_core.contracts.criteria import load_go_no_go_criteria
from signal_core.contracts.exchange_series import ExchangeSeries
from signal_core.contracts.order_types import OrderProduct, OrderSide, OrderType
from signal_core.contracts.price_band import PriceBandRecord
from signal_core.contracts.price_bar import PriceBar
from signal_core.execution.order_runner import (
    DailySignalCandidate,
    DailyTPlus1OrderRunner,
)
from signal_core.execution.simulator import ExecutionFillSimulator, FillStatus
from signal_core.portfolio.portfolio import Portfolio
from signal_core.research.trials import (
    RegistryTamperedError,
    TrialEvaluationError,
    TrialRegistry,
    TrialRegistryError,
    verify_evaluation_artifact_agreement,
)
from signal_core.storage.calendar import load_anchored_nse_trading_calendar
from scripts.run_phase3b2_walkforward import (
    build_authoritative_runner,
    run_phase3b2_walkforward,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ISIN = "INE001A01036"
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


def _band(trade_date: datetime.date, lower: str = "900.00") -> PriceBandRecord:
    return PriceBandRecord(
        isin=ISIN,
        trade_date=trade_date,
        series="EQ",
        upper_circuit_limit=Decimal("1100.00"),
        lower_circuit_limit=Decimal(lower),
        band_percentage=Decimal("10.00"),
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


def _buy(runner: DailyTPlus1OrderRunner, target: datetime.date, bar: PriceBar):
    candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=bar.volume,
        series="EQ",
        allocation_weight=Decimal("0.05"),
        metadata={"intent_id": "S72-BUY"},
    )
    return runner.run_candidate(
        candidate=candidate,
        t_plus_1_bar=bar,
        target_date=target,
        price_band=_band(target),
        explicit_series=ExchangeSeries.EQ,
    )


# --- H-124: one k, from the CLI to the sizing engine ------------------------------------


def test_h124_cli_k_reaches_the_runner_that_sizes():
    runner = _runner(_portfolio(), k="3.0")
    assert runner.atr_stop_multiple == Decimal("3.0")
    assert isinstance(runner, DailyTPlus1OrderRunner)


def test_h124_k_changes_sizing_only_when_the_risk_leg_binds():
    """q_risk < q_weight <=> ATR/price > 0.125/k: 8% ATR binds at both k, 2% binds at neither."""
    high_atr_candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("80.00"),
        session_volume=100000,
        series="EQ",
    )
    low_atr_candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=SIGNAL_SESSION,
        side=OrderSide.BUY,
        entry_reference_price=Decimal("1000.00"),
        atr=Decimal("20.00"),
        session_volume=100000,
        series="EQ",
    )

    high_k2 = _runner(_portfolio(), k="2.0").generate_order_intent(high_atr_candidate)[1]
    high_k3 = _runner(_portfolio(), k="3.0").generate_order_intent(high_atr_candidate)[1]
    assert high_k2.quantity == 62 and high_k2.binding_constraint == "RISK_BUDGET"
    assert high_k3.quantity == 41 and high_k3.binding_constraint == "RISK_BUDGET"
    assert high_k2.quantity != high_k3.quantity

    # The measured 2022-2023 tape (ATR 1.96-2.14%) cannot reach the risk leg at either multiple,
    # so a k sweep on that corpus is null for entries; the stop order is the only channel left.
    low_k2 = _runner(_portfolio(), k="2.0").generate_order_intent(low_atr_candidate)[1]
    low_k3 = _runner(_portfolio(), k="3.0").generate_order_intent(low_atr_candidate)[1]
    assert low_k2.quantity == low_k3.quantity == 100
    assert low_k2.binding_constraint == low_k3.binding_constraint == "MAX_POSITION_WEIGHT"


# --- Ruling 1: persisted protective stop through the single simulator -------------------


def test_protective_stop_is_armed_at_the_entry_fill():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    ticket = _buy(
        runner,
        ENTRY_SESSION,
        _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"),
    )
    assert ticket.status == FillStatus.FILLED
    stop = runner.protective_stops[ISIN]
    # entry reference 1000 - 2 * ATR 20, from the signal session's close, not recomputed later.
    assert stop.stop_price == Decimal("960.000")
    assert stop.quantity == ticket.fill_result.filled_quantity
    assert stop.signal_date == SIGNAL_SESSION


def test_protective_stop_gap_through_fills_at_the_open_not_the_stop():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    session = datetime.date(2024, 1, 18)
    result = runner.evaluate_protective_stops(
        session_date=session,
        bars={ISIN: _bar(session, "940.00", "955.00", "935.00", "950.00")},
        price_bands={ISIN: _band(session)},
    )
    assert result.filled_count == 1
    fill = result.tickets[0].fill_result
    # The reference price is the session open (a gap through the stop), not the stop price; the
    # statutory slippage model then moves the fill off that reference by the modelled market impact.
    assert fill.slippage.reference_price == Decimal("940.00")
    assert fill.executed_price < Decimal("960.000")
    assert ISIN not in runner.protective_stops


def test_protective_stop_intraday_breach_fills_at_the_stop():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    session = datetime.date(2024, 1, 18)
    result = runner.evaluate_protective_stops(
        session_date=session,
        bars={ISIN: _bar(session, "1000.00", "1005.00", "955.00", "960.00")},
        price_bands={ISIN: _band(session)},
    )
    assert result.filled_count == 1
    assert result.tickets[0].fill_result.slippage.reference_price == Decimal("960.000")


def test_protective_stop_is_not_filled_while_the_bid_side_is_frozen():
    """§5.3: a session pinned at the lower circuit defers the exit, it never fills the stop."""
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    session = datetime.date(2024, 1, 18)
    frozen = _bar(session, "900.00", "900.00", "900.00", "900.00")
    result = runner.evaluate_protective_stops(
        session_date=session,
        bars={ISIN: frozen},
        price_bands={ISIN: _band(session)},
    )

    assert result.filled_count == 0
    assert result.circuit_deferred_count == 1
    assert result.tickets[0].status == FillStatus.REJECTED_LOWER_CIRCUIT
    assert ISIN in runner.protective_stops, "a deferred exit stays pending"
    position = portfolio.get_position(ISIN)
    assert position is not None and position.quantity == 50

    # The next session offers a bid, and the still-persisted stop fills then.
    recovery = datetime.date(2024, 1, 19)
    second = runner.evaluate_protective_stops(
        session_date=recovery,
        bars={ISIN: _bar(recovery, "955.00", "965.00", "945.00", "950.00")},
        price_bands={ISIN: _band(recovery)},
    )
    assert second.filled_count == 1
    assert second.tickets[0].fill_result.slippage.reference_price == Decimal("955.00")


def test_signal_exit_cancels_the_open_protective_stop():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))
    assert runner.protective_stops

    exit_session = datetime.date(2024, 1, 18)
    exit_candidate = DailySignalCandidate(
        instrument_id=ISIN,
        signal_date=ENTRY_SESSION,
        side=OrderSide.SELL,
        entry_reference_price=Decimal("990.00"),
        atr=Decimal("20.00"),
        session_volume=100000,
        series="EQ",
        metadata={"exit_reason": "SIGNAL_EXIT"},
    )
    ticket = runner.run_candidate(
        candidate=exit_candidate,
        t_plus_1_bar=_bar(exit_session, "985.00", "990.00", "980.00", "985.00"),
        target_date=exit_session,
        price_band=_band(exit_session),
        explicit_series=ExchangeSeries.EQ,
    )
    assert ticket.status == FillStatus.FILLED
    assert runner.protective_stops == {}

    result = runner.evaluate_protective_stops(
        session_date=exit_session,
        bars={ISIN: _bar(exit_session, "985.00", "990.00", "980.00", "985.00")},
        price_bands={ISIN: _band(exit_session)},
    )
    assert result.tickets == ()


def test_split_reattaches_the_stop_to_the_post_action_price_scale():
    portfolio = _portfolio()
    runner = _runner(portfolio, k="2.0")
    _buy(runner, ENTRY_SESSION, _bar(ENTRY_SESSION, "1000.00", "1010.00", "990.00", "1000.00"))

    assert runner.adjust_protective_stop_for_split(ISIN, 2, 1) is True
    stop = runner.protective_stops[ISIN]
    assert stop.stop_price == Decimal("480.0000")
    assert stop.quantity == 100


# --- N-128: the evaluation witness is rooted outside itself ----------------------------


def _registry_with_one_scored_trial(tmp_path: Path) -> TrialRegistry:
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    registry.append_trial(
        trial_id="TRIAL-S72-1",
        hypothesis="h",
        rationale="r",
        partition="IN_SAMPLE",
        canonical_params={"k": "2.0"},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.2",
        timestamp_utc="2026-11-16T10:00:00+00:00",
    )
    registry.append_trial_evaluation(
        "TRIAL-S72-1", Decimal("0.50"), "RET-V1-s72", 100, "2026-11-16T10:05:00+00:00"
    )
    return registry


def test_n128_witness_zero_is_written_and_read_as_a_witnessed_zero(tmp_path: Path):
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    registry.append_trial(
        trial_id="TRIAL-S72-UNSCORED",
        hypothesis="h",
        rationale="r",
        partition="IN_SAMPLE",
        canonical_params={"k": "2.0"},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.2",
        timestamp_utc="2026-11-16T10:00:00+00:00",
    )
    manifest = json.loads((tmp_path / "trial_registry.jsonl.manifest").read_text(encoding="utf-8"))
    assert manifest["evaluation_count"] == 0
    assert manifest["head_eval_hash"] == "0" * 64
    assert TrialRegistry(tmp_path / "trial_registry.jsonl").evaluated_trial_count == 0


def test_n128_removing_the_witness_keys_fails_closed(tmp_path: Path):
    _registry_with_one_scored_trial(tmp_path)
    manifest_path = tmp_path / "trial_registry.jsonl.manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evaluation_count")
    manifest.pop("head_eval_hash")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RegistryTamperedError, match="evaluation witness"):
        TrialRegistry(tmp_path / "trial_registry.jsonl")


def test_n128_committed_manifest_digest_matches_the_criteria_pin():
    criteria = _criteria()
    committed = REPO_ROOT / "data" / "trials" / "trial_registry.jsonl.manifest"
    digest = hashlib.sha256(committed.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert criteria.expected_trial_registry_manifest_sha256 == digest

    # Editing any witnessed value changes the digest, so the pin can no longer match.
    payload = json.loads(committed.read_text(encoding="utf-8"))
    payload["head_eval_hash"] = "f" * 64
    assert hashlib.sha256(json.dumps(payload, indent=2).encode("utf-8")).hexdigest() != digest


def test_n128_criteria_loader_refuses_a_missing_or_malformed_pin(tmp_path: Path):
    import yaml

    from signal_core.contracts.criteria import CriteriaValidationError, load_go_no_go_criteria

    base = yaml.safe_load((REPO_ROOT / "configs" / "go_no_go_criteria.yaml").read_text(encoding="utf-8"))

    missing = json.loads(json.dumps(base))
    del missing["market_data_and_accounting_invariants"]["expected_trial_registry_manifest_sha256"]
    missing_file = tmp_path / "missing_pin.yaml"
    missing_file.write_text(yaml.dump(missing), encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="expected_trial_registry_manifest_sha256"):
        load_go_no_go_criteria(missing_file)

    malformed = json.loads(json.dumps(base))
    malformed["market_data_and_accounting_invariants"]["expected_trial_registry_manifest_sha256"] = "not-a-digest"
    malformed_file = tmp_path / "malformed_pin.yaml"
    malformed_file.write_text(yaml.dump(malformed), encoding="utf-8")
    with pytest.raises(CriteriaValidationError, match="expected_trial_registry_manifest_sha256"):
        load_go_no_go_criteria(malformed_file)


def test_n128_post_sidecar_artifact_with_null_score_is_refused(tmp_path: Path):
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    for i in range(5):
        registry.append_trial(
            trial_id=f"TRIAL-S72-{i}",
            hypothesis="h",
            rationale="r",
            partition="IN_SAMPLE",
            canonical_params={"k": "2.0"},
            fold_spec_fingerprint="F1",
            dataset_fingerprint="D1",
            criteria_version="1.1.2",
            timestamp_utc=f"2026-11-16T10:0{i}:00+00:00",
        )
        registry.append_trial_evaluation(
            f"TRIAL-S72-{i}", Decimal("0.10"), f"RET-V1-{i}", 10, f"2026-11-16T11:0{i}:00+00:00"
        )

    art_dir = tmp_path / "verdicts"
    art_dir.mkdir()
    for i in range(5):
        (art_dir / f"trial_{i}.json").write_text(
            json.dumps({"trial_id": f"TRIAL-S72-{i}", "annualized_sharpe": "0.10"}), encoding="utf-8"
        )
    checked, _ = verify_evaluation_artifact_agreement(registry, art_dir)
    assert checked == 5

    (art_dir / "trial_4.json").write_text(
        json.dumps({"trial_id": "TRIAL-S72-4", "annualized_sharpe": None}), encoding="utf-8"
    )
    with pytest.raises(TrialEvaluationError, match="annualized_sharpe"):
        verify_evaluation_artifact_agreement(registry, art_dir)


def test_n128_manifest_without_a_ledger_and_without_witness_is_not_silently_accepted(tmp_path: Path):
    registry = TrialRegistry(tmp_path / "trial_registry.jsonl")
    registry.append_trial(
        trial_id="TRIAL-S72-2",
        hypothesis="h",
        rationale="r",
        partition="IN_SAMPLE",
        canonical_params={"k": "2.0"},
        fold_spec_fingerprint="F1",
        dataset_fingerprint="D1",
        criteria_version="1.1.2",
        timestamp_utc="2026-11-16T10:00:00+00:00",
    )
    manifest_path = tmp_path / "trial_registry.jsonl.manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["evaluation_count"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(TrialRegistryError):
        registry.verify_integrity()


# --- N-129: the Gate-A input is reproducible from the committed artifact ---------------


def _oscillating_snapshot(tmp_path: Path, num_sessions: int = 120) -> Path:
    """A deterministic swing-inducing tape: rising for ~20 sessions, then falling ~20, repeating."""
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
        "data_version": "EXP-DEV-SYNTHETIC-S72",
        "source_identity": "NSE_BHAVCOPY_DAILY",
        "content_fingerprint": "DATA-CTNT-V2-s72synthetic1234567890",
        "session_count": len(sessions),
        "instrument_count": len(symbols),
        "trading_dates": [s.isoformat() for s in sessions],
        "symbols_by_instrument": symbols,
        "universe_by_date": {s.isoformat(): list(symbols.keys()) for s in sessions},
        "prices_by_instrument": prices,
        "benchmark_prices": bench,
    }
    snap_file = tmp_path / "synthetic_s72_snapshot.json"
    snap_file.write_text(json.dumps(data), encoding="utf-8")
    return snap_file


def test_n129_artifact_ledger_reproduces_expectancy_and_costs(tmp_path: Path):
    snap = _oscillating_snapshot(tmp_path)
    verdict_dir = tmp_path / "verdicts"
    res = run_phase3b2_walkforward(
        snapshot_path=snap,
        registry_path=tmp_path / "trial_reg.jsonl",
        verdict_output_dir=verdict_dir,
        trial_id="TRIAL-S72-LEDGER",
        max_sessions=120,
        in_sample_only=True,
        write_verdict_files=True,
    )
    assert len(res.closed_trades) > 0, "fixture must produce closed round trips"

    artifact = json.loads(
        (verdict_dir / "phase3b2_swing_baseline_2022_2024_verdict.json").read_text(encoding="utf-8")
    )
    ledger = artifact["closed_trades"]
    assert len(ledger) == len(res.closed_trades)

    net = [Decimal(row["net_pnl"]) for row in ledger]
    costs = [Decimal(row["statutory_costs"]) for row in ledger]
    assert Decimal(artifact["mean_net_expectancy"]) == (sum(net) / Decimal(len(net))).quantize(Decimal("0.0001")) or (
        abs(Decimal(artifact["mean_net_expectancy"]) - sum(net) / Decimal(len(net))) < Decimal("0.0000001")
    )
    assert Decimal(artifact["total_statutory_costs"]) == sum(costs)

    for row in ledger:
        assert row["exit_reason"] in ("STOP_LOSS", "SIGNAL_EXIT", "MAX_POSITION_WEIGHT_TRIM")
        assert row["entry_date"] <= row["exit_date"]
        assert Decimal(row["gross_pnl"]) - Decimal(row["statutory_costs"]) + Decimal(
            row["dividends"]
        ) == Decimal(row["net_pnl"])
        if row["realized_r"] is not None:
            assert abs(
                Decimal(row["realized_r"]) * Decimal(row["risk_per_share"]) * Decimal(row["quantity"])
                - Decimal(row["net_pnl"])
            ) < Decimal("0.01")

    assert "protective_stop_exits" in artifact
    assert "protective_stop_circuit_deferrals" in artifact
    assert artifact["atr_stop_multiple"] == "2.0"
