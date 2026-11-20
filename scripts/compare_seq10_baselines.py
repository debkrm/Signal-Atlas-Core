#!/usr/bin/env python3
"""
SEQ 10 vs BENCHMARKS — read-only strategy comparison (Audit §99.10 item 3, implemented in §100).

Three arms over the binding evaluation window `2018-04-02 .. 2023-12-29`, on the committed 2,735-ISIN
corpus the seq-10 run itself used:

- **SEQ10** — the committed candidate. Its daily equity returns and its 781 closed round trips are read
  from `reports/verdicts/trial_010/phase3b2_swing_baseline_2022_2024_verdict.json`, and this script
  recomputes final equity, max drawdown, trade-level profit factor and trade-level win rate from those
  fields. It refuses to publish if the recomputation does not reproduce the artifact's own cells, so the
  strategy arm is attested by computation, not by quoting (§9.1).
- **NIFTYBEES_BUY_HOLD** — buy at the first session's open, hold to the last session's close, statutory
  delivery costs on both sides (`signal_core.execution.costs.TransactionCostModel`). NIFTYBEES trades
  under two ISINs inside this window (`INF732E01011` → `INF204KB14I2` on 2019-12-20) and the price level
  drops ~10x at the transition; the corpus records that as an `ISIN_TRANSITION` with share ratio 1:1 and
  provenance `CONTENT_IDENTIFIED_ONLY`, i.e. the split ratio is **not** attested. Chaining the two levels
  would fabricate a −92% session (§5.3, §6.3). The benchmark is therefore built from within-ISIN daily
  returns, the one boundary session's return (2019-12-20) is left unmeasured and counted, and no level is
  spliced across the two identities.
- **RANDOM_ENTRY** — the null the momentum signal has to beat: a matched-trade randomization. Each of
  seq 10's 781 closed round trips is re-placed on a uniformly drawn session of the point-in-time universe
  with that trade's own holding length, buying at the next session's open (§7.1) and exiting at the close
  of the matched exit session, priced with the committed statutory cost model. Trade count, holding
  distribution and gross exposure are therefore seq 10's; only the (ISIN, entry date) is random. Volume
  participation is capped at 2.5% of the entry session's traded quantity (§7.3) and an over-cap draw is
  refused and counted.

Metrics use one convention for all three arms so the columns are comparable:

- `profit_factor` — sum of positive **session** P&L over |sum of negative session P&L| on the arm's daily
  marked-to-market equity curve. Well defined for a single round trip, unlike a trade-level ratio.
- `max_drawdown` — running-peak drawdown on that same curve.
- `win_rate` — share of sessions with positive P&L.
- `trade_profit_factor` / `trade_win_rate` — the artifact's own round-trip convention, reported where it is
  defined (SEQ10 and RANDOM_ENTRY); NIFTYBEES has one round trip, so a trade-level ratio is undefined there
  and the artifact records `null` rather than an infinity.

Read-only: writes no registry row, appends no evaluation, writes no verdict artifact, and refuses any
session in the sealed holdout era. It moves neither N nor N_eval and is not a registered trial — the
randomized draws explore no parameter and select no rule, so they add nothing to the multiple-testing
budget (§8.2).

Usage:
    python scripts/compare_seq10_baselines.py            # compute and write the committed artifact
    python scripts/compare_seq10_baselines.py --check    # recompute and compare with the committed bytes
"""

from __future__ import annotations

import argparse
import datetime
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from signal_core.contracts.criteria import (  # noqa: E402
    compute_criteria_fingerprint,
    load_go_no_go_criteria,
)
from signal_core.execution.costs import TransactionCostModel  # noqa: E402
from signal_core.execution.types import OrderProduct, OrderSide  # noqa: E402

DATASET_PATH = REPO_ROOT / "data" / "reference" / "historical_dataset_2018_2023.json.gz"
SEQ10_ARTIFACT = (
    REPO_ROOT / "reports" / "verdicts" / "trial_010" / "phase3b2_swing_baseline_2022_2024_verdict.json"
)
OUTPUT_PATH = REPO_ROOT / "reports" / "analysis" / "s100" / "seq10_baseline_comparison.json"

WINDOW_START = "2018-04-02"
WINDOW_END = "2023-12-29"
SEALED_START = datetime.date(2025, 1, 1)
INITIAL_CAPITAL = Decimal("1000000.00")

# NIFTYBEES under two ISINs; the second starts on the transition ex-date (§5.3, §10.4).
NIFTYBEES_ISINS = ("INF732E01011", "INF204KB14I2")

# The null: deterministic seed, fixed draw count, declared before the first run (§8.1).
RANDOM_SEED = 100_010_010
RANDOM_DRAWS = 200
VOLUME_PARTICIPATION_CAP = Decimal("0.025")
# A one-session move this large is a level change (an unattested split/bonus), not a return (§5.3, §6.3).
LEVEL_BREAK_THRESHOLD = Decimal("0.5")
# The benchmark a pre-registered decision clause is compared against must be continuous: a retained
# one-session step at or above this is refused by name rather than carried into a Calmar (§9.2, N-201).
BENCHMARK_LEVEL_BREAK_REFUSAL = Decimal("0.5")


def refuse_unattested_level_break(returns: Sequence[Tuple[str, Decimal]], threshold) -> None:
    """
    Refuse a benchmark series that carries a one-session level break, by session and by name (N-201).

    The buy-and-hold arm drops the transition session and any level break, and this runs on the returns
    it *kept*: a series can only reach a decision clause through here, so an exclusion that stops
    working fails closed instead of quietly pricing the break.
    """
    limit = Decimal(threshold)
    for session, ret in returns:
        if abs(ret) >= limit:
            raise SystemExit(
                f"refused: the benchmark series carries a one-session step of {ret} at {session} "
                f"(|return| >= {limit}) — an unattested level break inside the evaluation window makes "
                f"every Calmar computed from it meaningless (N-201, §5.4, §9.2)"
            )

# Pre-registered decision rule (§8.1, §9.1) — recorded in the artifact and evaluated from the numbers:
#   GO   iff SEQ10's round-trip profit factor is above the 95th percentile of the randomized-entry null
#        AND SEQ10's final equity is above the buy-and-hold benchmark's.
#   KILL otherwise (the strategy family is not carried into seq 12).
DECISION_RULE = (
    "GO iff seq10.trade_profit_factor > p95(random_entry.trade_profit_factor) AND "
    "seq10.final_equity > niftybees_buy_hold.final_equity; otherwise KILL"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_dataset() -> dict:
    with gzip.open(DATASET_PATH, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _dec(value) -> Decimal:
    return Decimal(str(value))


def curve_metrics(equity: Sequence[Decimal]) -> Dict[str, Optional[str]]:
    """Session-level profit factor, running-peak drawdown and session win rate of one equity curve."""
    peak = equity[0]
    drawdown = Decimal(0)
    gains = Decimal(0)
    losses = Decimal(0)
    winning_sessions = 0
    for previous, current in zip(equity, equity[1:]):
        pnl = current - previous
        if pnl > 0:
            gains += pnl
            winning_sessions += 1
        elif pnl < 0:
            losses += -pnl
        if current > peak:
            peak = current
        depth = (peak - current) / peak
        if depth > drawdown:
            drawdown = depth
    sessions = max(1, len(equity) - 1)
    return {
        "profit_factor": str(gains / losses) if losses > 0 else None,
        "max_drawdown": str(drawdown),
        "win_rate": str(Decimal(winning_sessions) / Decimal(sessions)),
    }


def trade_metrics(net_pnls: Sequence[Decimal]) -> Dict[str, Optional[str]]:
    """Round-trip profit factor and win rate — the artifact's own convention."""
    gains = sum((pnl for pnl in net_pnls if pnl > 0), Decimal(0))
    losses = -sum((pnl for pnl in net_pnls if pnl < 0), Decimal(0))
    wins = sum(1 for pnl in net_pnls if pnl > 0)
    return {
        "trade_profit_factor": str(gains / losses) if losses > 0 else None,
        "trade_win_rate": str(Decimal(wins) / Decimal(len(net_pnls))) if net_pnls else None,
    }


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal:
    """Linear-interpolated percentile of an already sorted sequence."""
    if not values:
        raise ValueError("no values")
    if len(values) == 1:
        return values[0]
    position = fraction * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight


# --- Arm 1: the committed candidate ------------------------------------------------------


def seq10_arm(artifact: dict) -> Tuple[dict, List[str]]:
    problems: List[str] = []
    daily = artifact["daily_returns"]
    sessions = sorted(daily)
    for day in sessions:
        if datetime.date.fromisoformat(day) >= SEALED_START:
            problems.append(f"the artifact's daily returns contain the sealed session {day}")
    with localcontext() as ctx:
        ctx.prec = 60
        equity = [INITIAL_CAPITAL]
        for day in sessions:
            equity.append(equity[-1] * (Decimal(1) + Decimal(daily[day])))
    metrics = curve_metrics(equity)
    trades = artifact["closed_trades"]
    net_pnls = [_dec(trade["net_pnl"]) for trade in trades]
    gross_pnls = [_dec(trade["gross_pnl"]) for trade in trades]
    # Like-for-like with the randomized arm, which pays statutory costs and no impact: the comparison
    # uses each arm's net-of-cost round-trip ratio. The artifact's `closed_only_profit_factor` is the
    # **gross** ratio, so both bases are reported and both are attested below.
    metrics.update(trade_metrics(net_pnls))
    metrics["trade_profit_factor_gross"] = trade_metrics(gross_pnls)["trade_profit_factor"]
    metrics["trade_win_rate_gross"] = trade_metrics(gross_pnls)["trade_win_rate"]
    metrics["sessions"] = len(sessions)
    metrics["trades"] = len(trades)
    metrics["final_equity"] = str(equity[-1])

    claimed = artifact["in_sample_metrics"]
    # The strategy arm is published only if this recomputation is the artifact's own arithmetic.
    ending = equity[-1].quantize(Decimal("0.01"))
    if str(ending) != str(claimed["end_equity"]):
        problems.append(
            f"recomputed final equity {ending} does not reproduce the artifact's {claimed['end_equity']}"
        )
    if Decimal(metrics["max_drawdown"]) - Decimal(claimed["max_drawdown"]) > Decimal("1e-24"):
        problems.append(
            f"recomputed max drawdown {metrics['max_drawdown']} does not reproduce the artifact's "
            f"{claimed['max_drawdown']}"
        )
    if metrics["trade_profit_factor_gross"] != str(Decimal(artifact["closed_only_profit_factor"])):
        problems.append(
            f"recomputed gross round-trip profit factor {metrics['trade_profit_factor_gross']} is not the "
            f"artifact's {artifact['closed_only_profit_factor']}"
        )
    # The artifact's `win_rate` counts a round trip as a win on its **net** P&L, while its
    # `closed_only_profit_factor` is the gross ratio — two different bases in one document, attested here
    # on the basis each one actually uses.
    if metrics["trade_win_rate"] != str(Decimal(claimed["win_rate"])):
        problems.append(
            f"recomputed net round-trip win rate {metrics['trade_win_rate']} is not the artifact's "
            f"{claimed['win_rate']}"
        )
    return metrics, problems


# --- Arm 2: buy-and-hold NIFTYBEES -------------------------------------------------------


def buy_and_hold_arm(dataset: dict, cost_model: TransactionCostModel) -> dict:
    """
    NIFTYBEES buy-and-hold, built from within-ISIN returns.

    The transition session's return is not measured: the two ISINs' price levels are not comparable (the
    10:1 unit change is not in the corpus as a verified ratio), so chaining them would invent a return.
    """
    trading_dates = dataset["trading_dates"]
    bars: Dict[str, Dict[str, dict]] = {}
    for isin in NIFTYBEES_ISINS:
        bars[isin] = {b["trade_date"]: b for b in dataset["prices_by_instrument"][isin]}
    # The symbol's sessions, mapped to the ISIN that traded them.
    session_isin: Dict[str, str] = {}
    for isin, by_date in bars.items():
        for day in by_date:
            session_isin[day] = isin
    uncovered = [d for d in trading_dates if d not in session_isin]
    transitions = sum(
        1
        for previous, current in zip(trading_dates, trading_dates[1:])
        if current in session_isin
        and previous in session_isin
        and session_isin[current] != session_isin[previous]
    )

    unmeasured: List[dict] = []
    with localcontext() as ctx:
        ctx.prec = 60
        returns: List[Tuple[str, Decimal]] = []
        for previous, current in zip(trading_dates, trading_dates[1:]):
            if current not in session_isin or previous not in session_isin:
                unmeasured.append({"session": current, "reason": "no bar for the symbol"})
                continue
            if session_isin[previous] != session_isin[current]:
                unmeasured.append({"session": current, "reason": "ISIN transition; levels incomparable"})
                continue
            previous_close = _dec(bars[session_isin[previous]][previous]["close"])
            current_close = _dec(bars[session_isin[current]][current]["close"])
            ret = current_close / previous_close - Decimal(1)
            if abs(ret) >= LEVEL_BREAK_THRESHOLD:
                # A move no NSE session produces: the price level changed, the security did not. The
                # split this is (10:1, on the old ISIN's last bar) is not in the committed corporate
                # action table, so the session is left unmeasured rather than booked as a −90% day.
                unmeasured.append(
                    {"session": current, "reason": f"level break {ret} — unattested corporate action"}
                )
                continue
            returns.append((current, ret))

        refuse_unattested_level_break(returns, BENCHMARK_LEVEL_BREAK_REFUSAL)
        equity = [INITIAL_CAPITAL]
        for _day, ret in returns:
            equity.append(equity[-1] * (Decimal(1) + ret))

    metrics = curve_metrics(equity)
    # One round trip: bought at the first session's open, liquidated at the last session's close. The buy
    # leg is priced on units; the sell leg is priced on **turnover**, because the split ratio that would
    # turn the entry's units into the exit's units is exactly the unattested fact left unmeasured above.
    first_day = trading_dates[0]
    last_day = trading_dates[-1]
    entry_price = _dec(bars[session_isin[first_day]][first_day]["open"])
    quantity = int(INITIAL_CAPITAL / entry_price)
    entry_notional = entry_price * quantity
    exit_notional = equity[-1]
    entry_cost = cost_model.compute_costs(
        datetime.date.fromisoformat(first_day), OrderSide.BUY, OrderProduct.DELIVERY,
        quantity, entry_price,
    ).total_charges
    exit_cost = cost_model.compute_costs(
        datetime.date.fromisoformat(last_day), OrderSide.SELL, OrderProduct.DELIVERY,
        1, exit_notional,
    ).total_charges
    metrics.update(trade_metrics([exit_notional - entry_notional]))
    metrics["trade_profit_factor"] = None  # one round trip cannot yield a ratio; never publish an infinity
    metrics["trade_win_rate"] = None
    metrics["sessions"] = len(returns)
    metrics["trades"] = 1
    metrics["final_equity"] = str(exit_notional - entry_cost - exit_cost)
    metrics["entry_isin"] = session_isin[first_day]
    metrics["exit_isin"] = session_isin[last_day]
    metrics["isin_transitions_in_window"] = transitions
    metrics["unmeasured_sessions"] = unmeasured
    metrics["sessions_without_a_bar"] = uncovered
    metrics["statutory_costs"] = str(entry_cost + exit_cost)
    metrics["cost_model"] = "signal_core.execution.costs.TransactionCostModel(committed criteria)"
    return metrics


# --- Arm 3: matched-trade randomized entry -----------------------------------------------

def random_entry_arm(
    dataset: dict, artifact: dict, cost_model: TransactionCostModel, limit_sessions: int
) -> dict:
    trading_dates = dataset["trading_dates"]
    index_of = {day: position for position, day in enumerate(trading_dates)}
    universe = dataset["universe_by_date"]
    prices = dataset["prices_by_instrument"]
    # Per ISIN: session index -> (open, close, traded quantity, raw strings kept for exact Decimal).
    series: Dict[str, Dict[int, Tuple[str, str, str]]] = {}
    for isin, rows in prices.items():
        # `raw_volume` is the session's actual traded quantity (`TOTTRDQTY`), which is what the 2.5%
        # participation cap must be measured against (§7.3); `volume` is the adjusted series.
        series[isin] = {
            index_of[row["trade_date"]]: (row["open"], row["close"], str(row["raw_volume"]))
            for row in rows
        }

    matched: List[Tuple[int, Decimal]] = []
    for trade in artifact["closed_trades"]:
        entry = index_of[trade["entry_date"]]
        exit_ = index_of[trade["exit_date"]]
        holding = exit_ - entry
        gross_exposure = _dec(trade["entry_price"]) * int(trade["quantity"])
        matched.append((holding, gross_exposure))

    rng = random.Random(RANDOM_SEED)
    draw_results: List[Dict[str, Optional[str]]] = []
    rejects = 0
    untradeable = 0

    for _draw in range(RANDOM_DRAWS):
        legs: List[dict] = []
        for holding, gross_exposure in matched:
            attempt = 0
            while True:
                attempt += 1
                signal_index = rng.randrange(0, limit_sessions - holding - 1)
                entry_index = signal_index + 1
                exit_index = entry_index + holding
                candidates = universe[trading_dates[signal_index]]
                isin = candidates[rng.randrange(len(candidates))]
                bars = series[isin]
                entry_bar = bars.get(entry_index)
                exit_bar = bars.get(exit_index)
                if entry_bar is None or exit_bar is None:
                    if attempt >= 8:
                        untradeable += 1
                        break
                    continue
                entry_price = _dec(entry_bar[0])
                exit_price = _dec(exit_bar[1])
                quantity = int(gross_exposure / entry_price)
                cap = int(Decimal(entry_bar[2]) * VOLUME_PARTICIPATION_CAP)
                if quantity < 1 or quantity > cap:
                    rejects += 1
                    if attempt >= 8:
                        untradeable += 1
                        break
                    continue
                buy_cost = cost_model.compute_costs(
                    datetime.date.fromisoformat(trading_dates[entry_index]),
                    OrderSide.BUY, OrderProduct.DELIVERY, quantity, entry_price,
                ).total_charges
                sell_cost = cost_model.compute_costs(
                    datetime.date.fromisoformat(trading_dates[exit_index]),
                    OrderSide.SELL, OrderProduct.DELIVERY, quantity, exit_price,
                ).total_charges
                legs.append(
                    {
                        "entry_index": entry_index,
                        "exit_index": exit_index,
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "buy_cost": buy_cost,
                        "gross_pnl": (exit_price - entry_price) * quantity,
                        "net_pnl": (exit_price - entry_price) * quantity - buy_cost - sell_cost,
                        # Marking closes for the held sessions; the running mark starts at the fill.
                        "marks": {
                            day: _dec(bars[day][1])
                            for day in range(entry_index, exit_index + 1)
                            if day in bars
                        },
                        "mark": entry_price,
                    }
                )
                break

        net_pnls = [leg["net_pnl"] for leg in legs]
        metrics = trade_metrics(net_pnls)
        metrics["trade_profit_factor_gross"] = trade_metrics(
            [leg["gross_pnl"] for leg in legs]
        )["trade_profit_factor"]
        # Daily marked-to-market curve: realised P&L plus open positions marked at the session close.
        open_legs: List[dict] = []
        legs_by_entry: Dict[int, List[dict]] = {}
        for leg in legs:
            legs_by_entry.setdefault(leg["entry_index"], []).append(leg)
        equity = [INITIAL_CAPITAL]
        realised = Decimal(0)
        with localcontext() as ctx:
            ctx.prec = 60
            for session in range(1, limit_sessions):
                for leg in legs_by_entry.get(session, ()):
                    open_legs.append(leg)
                still_open: List[dict] = []
                for leg in open_legs:
                    if leg["exit_index"] == session:
                        realised += leg["net_pnl"]
                    else:
                        leg["mark"] = leg["marks"].get(session, leg["mark"])
                        still_open.append(leg)
                open_legs = still_open
                marked = realised
                for leg in open_legs:
                    marked += (leg["mark"] - leg["entry_price"]) * leg["quantity"] - leg["buy_cost"]
                equity.append(INITIAL_CAPITAL + marked)
        metrics.update(curve_metrics(equity))
        metrics["trades"] = len(legs)
        draw_results.append(metrics)

    def _collect(key: str) -> List[Decimal]:
        return [_dec(row[key]) for row in draw_results if row.get(key) is not None]

    trade_pfs = sorted(_collect("trade_profit_factor"))
    gross_trade_pfs = sorted(_collect("trade_profit_factor_gross"))
    drawdowns = sorted(_collect("max_drawdown"))
    curve_pfs = sorted(_collect("profit_factor"))
    trade_win_rates = sorted(_collect("trade_win_rate"))
    return {
        "draws": RANDOM_DRAWS,
        "seed": RANDOM_SEED,
        "matched_trades_per_draw": len(matched),
        "rejected_over_volume_cap": rejects,
        "untradeable_draws_per_trade": untradeable,
        "trade_profit_factor": {
            "median": str(_percentile(trade_pfs, Decimal("0.5"))),
            "p05": str(_percentile(trade_pfs, Decimal("0.05"))),
            "p95": str(_percentile(trade_pfs, Decimal("0.95"))),
        },
        "curve_profit_factor": {
            "median": str(_percentile(curve_pfs, Decimal("0.5"))),
            "p05": str(_percentile(curve_pfs, Decimal("0.05"))),
            "p95": str(_percentile(curve_pfs, Decimal("0.95"))),
        },
        "gross_trade_profit_factor": {
            "median": str(_percentile(gross_trade_pfs, Decimal("0.5"))),
            "p95": str(_percentile(gross_trade_pfs, Decimal("0.95"))),
        },
        "max_drawdown": {
            "median": str(_percentile(drawdowns, Decimal("0.5"))),
            "p05": str(_percentile(drawdowns, Decimal("0.05"))),
            "p95": str(_percentile(drawdowns, Decimal("0.95"))),
        },
        "trade_win_rate": {"median": str(_percentile(trade_win_rates, Decimal("0.5")))},
        "convention": (
            "trade_profit_factor / trade_win_rate are round-trip metrics over each draw's matched trade "
            "count; profit_factor / max_drawdown / win_rate are session-level metrics of the draw's daily "
            "marked-to-market equity curve"
        ),
    }


# --- Assembly -----------------------------------------------------------------------------


def build_artifact() -> dict:
    criteria = load_go_no_go_criteria()
    cost_model = TransactionCostModel(criteria.statutory_costs)
    dataset = _load_dataset()
    artifact = json.loads(SEQ10_ARTIFACT.read_text(encoding="utf-8"))

    trading_dates = dataset["trading_dates"]
    if trading_dates[0] != WINDOW_START or trading_dates[-1] != WINDOW_END:
        raise SystemExit(
            f"the corpus covers {trading_dates[0]}..{trading_dates[-1]}, not {WINDOW_START}..{WINDOW_END}"
        )
    sealed = [d for d in trading_dates if datetime.date.fromisoformat(d) >= SEALED_START]
    if sealed:
        raise SystemExit(f"the corpus contains sealed holdout sessions ({sealed[0]}); refusing to run")

    seq10, problems = seq10_arm(artifact)
    if problems:
        raise SystemExit("the seq-10 arm does not reproduce its committed artifact: " + "; ".join(problems))

    buy_hold = buy_and_hold_arm(dataset, cost_model)
    randomized = random_entry_arm(dataset, artifact, cost_model, len(trading_dates))

    # Net of statutory costs on both sides, so neither arm is credited with costs the other paid.
    trade_pf = _dec(seq10["trade_profit_factor"])
    null_p95 = _dec(randomized["trade_profit_factor"]["p95"])
    signal_condition = trade_pf > null_p95
    investability_condition = _dec(seq10["final_equity"]) > _dec(buy_hold["final_equity"])
    verdict = "GO — execute seq 12" if (signal_condition and investability_condition) else (
        "KILL — the strategy family is not carried into seq 12"
    )

    return {
        "artifact": "seq10_baseline_comparison",
        "audit_section": "§99.10 item 3 (implemented in §100)",
        "mode": "READ_ONLY_BENCHMARK",
        "window": f"{WINDOW_START}..{WINDOW_END}",
        "sessions": len(trading_dates),
        "universe_instrument_count": dataset["instrument_count"],
        "dataset_corpus": DATASET_PATH.relative_to(REPO_ROOT).as_posix(),
        "dataset_content_fingerprint": dataset["content_fingerprint"],
        "dataset_sha256": _sha256(DATASET_PATH),
        "seq10_artifact": SEQ10_ARTIFACT.relative_to(REPO_ROOT).as_posix(),
        "seq10_artifact_sha256": _sha256(SEQ10_ARTIFACT),
        "criteria_version": criteria.version,
        "criteria_fingerprint": compute_criteria_fingerprint(criteria),
        "arms": {
            "seq10": seq10,
            "niftybees_buy_hold": buy_hold,
            "random_entry": randomized,
        },
        "decision": {
            "rule": DECISION_RULE,
            "inputs": {
                "basis": "round-trip profit factor net of statutory costs (each arm's own fill set)",
                "seq10_trade_profit_factor": seq10["trade_profit_factor"],
                "random_entry_trade_profit_factor_p95": randomized["trade_profit_factor"]["p95"],
                "seq10_final_equity": seq10["final_equity"],
                "niftybees_buy_hold_final_equity": buy_hold["final_equity"],
            },
            "signal_condition_met": signal_condition,
            "investability_condition_met": investability_condition,
            "verdict": verdict,
        },
        "limitations": [
            "the randomized arm prices statutory costs only: no market impact, no slippage and no dividend "
            "income inside a hold, so it is advantaged against seq10 on cost and disadvantaged on dividends",
            "the randomized arm assumes every matched trade is fundable, i.e. it carries no cash-slot "
            "competition; seq 10's book is capital constrained",
            "the NIFTYBEES series leaves the 2019-12-20 return unmeasured because the 10:1 unit change that "
            "accompanies its ISIN transition is not attested in the committed corporate-action table",
            "this comparison is not a registered trial: it appends no registry row, moves neither N nor "
            "N_eval, and its draws explore no parameter",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="reproduce the committed artifact")
    args = parser.parse_args()

    payload = build_artifact()
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"FAIL: no committed artifact at {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}")
            return 1
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != text:
            print("FAIL: the recomputed comparison is not the committed one")
            return 1
        print("PASS: the comparison reproduces the committed artifact")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(payload["decision"], indent=1))
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
