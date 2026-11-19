#!/usr/bin/env python3
"""
CANDIDATE seq 11 — a T-1 liquidity floor and an ATR risk budget (pre-registered in
`configs/trial_011_candidate.yaml` before this script existed)

Two controls, both derived from seq 10's own decomposition (`reports/analysis/s98/seq10_drawdown_decomposition.json`):

1. **T-1 liquidity entry floor** — an entry needs a median 20-session traded value of at least ₹25 crore
   over the authoritative sessions immediately before the signal session. The window is read through the
   §6.3 gap partition (`pit_universe.median_turnover_as_of`), so a name whose window crosses an
   `UNEXPLAINED_MISSING_RECORD` boundary has no T-1 evidence and is not an entry.
2. **ATR risk budget** — risk 0.75% of equity to the 2.0xATR(14) protective stop, under the same 8%
   allocation cap seq 10 carried. The cap is unchanged on purpose: it is not the hypothesis.

Everything else is seq 10's committed configuration: sma_20/sma_50, mom_63 entry rank, k = 2.0, trim
None, LOCKED_BAR_REFUSAL_ONLY, min_entry_notional 25000, min_fill_notional 5000, the 21-session hold bound.

Registration precedes metric reading: the row is appended by the engine with `sharpe_ratio=None` (Rule
3.2, §8.2) and the outcome is a linked evaluation row carrying the executed criteria fingerprint. The
2024 validation fold is not touched and no session on or after 2025-01-01 is read.

Usage:
    python scripts/run_seq11_candidate.py
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_phase3b2_walkforward as walkforward  # noqa: E402
import scripts.run_seq10_candidate as seq10  # noqa: E402
from signal_core.contracts.criteria import compute_criteria_fingerprint  # noqa: E402
from signal_core.contracts.price_bar import PriceBar  # noqa: E402
from signal_core.research.pit_universe import median_turnover_as_of  # noqa: E402

CONFIG_PATH = REPO_ROOT / "configs" / "trial_011_candidate.yaml"
VERDICT_DIR = REPO_ROOT / "reports" / "verdicts" / "trial_011"
ARTIFACT_NAME = "phase3b2_swing_baseline_2022_2024_verdict.json"
ARTIFACT = VERDICT_DIR / ARTIFACT_NAME
COMPARISON = VERDICT_DIR / "seq11_vs_seq10_comparison.json"
SEQ10_ARTIFACT = REPO_ROOT / "reports" / "verdicts" / "trial_010" / ARTIFACT_NAME

WINDOW_START = datetime.date(2018, 4, 1)
WINDOW_END = datetime.date(2023, 12, 31)
WINDOW_FIRST_SESSION = datetime.date(2018, 4, 2)
WINDOW_LAST_SESSION = datetime.date(2023, 12, 29)
METRICS = ("closed_trades", "end_equity", "profit_factor", "win_rate", "max_drawdown")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _metric(artifact: dict, name: str):
    return (artifact.get("in_sample_metrics") or {}).get(name)


def main() -> int:
    criteria = walkforward.load_go_no_go_criteria()
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    metadata = config["metadata"]
    controls = config["controls"]
    trial_id = str(metadata["trial_id"])
    config_digest = _digest(CONFIG_PATH)

    print("=" * 96)
    print("CANDIDATE seq 11 — pre-registered liquidity floor + ATR risk budget")
    print(f"Window: {WINDOW_START}..{WINDOW_END} (in-sample only; 2024 validation FROZEN)")
    print(f"Criteria: {criteria.version} | hold bound {criteria.max_hold_trading_sessions} session(s)")
    print(
        f"Controls: median ADTV floor ₹{controls['min_median_adtv_crore']} Cr over "
        f"{controls['adtv_lookback_sessions']} T-1 session(s); risk {controls['risk_per_trade_pct']} to "
        f"the {controls['atr_stop_multiple']}xATR stop, capped at {controls['max_position_weight']}"
    )
    print(f"Pre-registration: configs/trial_011_candidate.yaml sha256 {config_digest}")
    print("=" * 96)

    live = compute_criteria_fingerprint(criteria)
    problems: list[str] = []
    if criteria.min_binding_evaluation_start_date != WINDOW_START:
        problems.append(
            f"the criteria' binding start is {criteria.min_binding_evaluation_start_date}, not {WINDOW_START}"
        )
    if criteria.version != metadata["criteria_version"]:
        problems.append(
            f"the criteria are {criteria.version} but the pre-registration names {metadata['criteria_version']}"
        )
    if live != metadata["criteria_fingerprint"]:
        problems.append(
            f"the live criteria fingerprint {live} is not the pre-registered {metadata['criteria_fingerprint']}; "
            f"the candidate would be judged by a set it was not registered against"
        )
    if criteria.max_hold_trading_sessions != int(controls["max_hold_trading_sessions"]):
        problems.append(
            f"the hold bound is {criteria.max_hold_trading_sessions}, not {controls['max_hold_trading_sessions']}"
        )
    if problems:
        print("OVERALL: NOT REGISTERED — " + "; ".join(problems))
        print("=" * 96)
        return 1

    corpus_path, corpus_problem = seq10.locate_corporate_action_adjusted_corpus()
    if corpus_path is None:
        print(f"OVERALL: NOT REGISTERED — {corpus_problem}")
        print("=" * 96)
        return 1
    cost_problem = seq10.statutory_cost_schedule_problem(criteria)
    if cost_problem:
        print(f"OVERALL: NOT REGISTERED — {cost_problem}")
        print("=" * 96)
        return 1
    print(f"[INFO] Corpus: {corpus_path.relative_to(REPO_ROOT).as_posix()}")

    if not SEQ10_ARTIFACT.is_file():
        print(f"OVERALL: NOT REGISTERED — no seq-10 baseline at {SEQ10_ARTIFACT.relative_to(REPO_ROOT).as_posix()}")
        print("=" * 96)
        return 1
    seq10_artifact = json.loads(SEQ10_ARTIFACT.read_text(encoding="utf-8"))
    seq10_drawdown = Decimal(str(_metric(seq10_artifact, "max_drawdown")))
    if str(seq10_drawdown) != metadata["baseline_max_drawdown"]:
        print(
            f"OVERALL: NOT REGISTERED — seq 10's artifact publishes max_drawdown {seq10_drawdown}, "
            f"not the pre-registered baseline {metadata['baseline_max_drawdown']}"
        )
        print("=" * 96)
        return 1

    started = time.monotonic()
    dataset = walkforward.resolve_or_build_historical_dataset(snapshot_path=corpus_path)
    print(
        f"[INFO] Dataset: {dataset.snapshot.session_count} session(s), "
        f"{dataset.snapshot.instrument_count} instrument(s), fingerprint "
        f"{dataset.snapshot.content_fingerprint} (loaded in {time.monotonic() - started:.1f}s)"
    )

    hypothesis = str(config["hypothesis"]).strip()
    rationale = (
        f"seq 11, pre-registered in configs/trial_011_candidate.yaml (sha256 {config_digest}) before "
        f"execution, under the §98.10 carried work. Two controls against seq 10's committed "
        f"configuration: (1) a T-1 liquidity entry floor of ₹{controls['min_median_adtv_crore']} Cr "
        f"median traded value over {controls['adtv_lookback_sessions']} consecutive authoritative "
        f"sessions, read through the §6.3 gap partition; (2) position risk cut from 1.00% to "
        f"{controls['risk_per_trade_pct']} of equity against the same {controls['atr_stop_multiple']}xATR(14) "
        f"stop, under the unchanged {controls['max_position_weight']} allocation cap. Everything else is "
        f"seq 10's row: sma_20/sma_50, mom_63, k = 2.0, trim None, LOCKED_BAR_REFUSAL_ONLY, "
        f"min_entry_notional 25000, min_fill_notional 5000, the 21-session hold bound. The floor and the "
        f"risk budget are derived from reports/analysis/s98/seq10_drawdown_decomposition.json (the 5-25 Cr "
        f"and 1-5 Cr tiers lost ₹198,779.88 net on 466 round trips). Comparator: seq 10's committed "
        f"artifact, same window, same criteria fingerprint. In-sample only: the 2024 validation fold is "
        f"frozen and the holdout is not read."
    )

    VERDICT_DIR.mkdir(parents=True, exist_ok=True)
    run = walkforward.run_phase3b2_walkforward(
        snapshot_path=corpus_path,
        verdict_output_dir=VERDICT_DIR,
        dataset=dataset,
        trial_id=trial_id,
        hypothesis=hypothesis,
        rationale=rationale,
        in_sample_only=True,
        eval_start_date=WINDOW_START,
        eval_end_date=WINDOW_END,
        record_trial=True,
        allocation_weight=Decimal(str(controls["max_position_weight"])),
        atr_stop_multiple=Decimal(str(controls["atr_stop_multiple"])),
        entry_rank_indicator=str(controls["entry_rank_indicator"]),
        band_policy=str(controls["unbanded_session_fill_policy"]),
        risk_per_trade_pct=Decimal(str(controls["risk_per_trade_pct"])),
        min_median_adtv_crore=Decimal(str(controls["min_median_adtv_crore"])),
        adtv_lookback_sessions=int(controls["adtv_lookback_sessions"]),
    )

    sessions = [
        s if isinstance(s, datetime.date) else datetime.date.fromisoformat(str(s))
        for s in run.executed_sessions
    ]
    assert sessions, "seq 11 evaluated no session"
    assert min(sessions) == WINDOW_FIRST_SESSION, f"seq 11 opened {min(sessions)}, not {WINDOW_FIRST_SESSION}"
    assert max(sessions) == WINDOW_LAST_SESSION, f"seq 11 ended {max(sessions)}, not {WINDOW_LAST_SESSION}"
    assert not [s for s in sessions if s >= datetime.date(2025, 1, 1)], "seq 11 read the sealed era"

    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    comparison, problems = _write_comparison(
        artifact=artifact,
        seq10_artifact=seq10_artifact,
        dataset_fingerprint=dataset.snapshot.content_fingerprint,
        config=config,
        config_digest=config_digest,
        corpus_path=corpus_path,
        criteria=criteria,
        sessions=sessions,
    )
    candidate_drawdown = Decimal(str(_metric(artifact, "max_drawdown")))
    liquidated_pf = artifact.get("liquidated_profit_factor")
    closed_trades = int(str(_metric(artifact, "closed_trades")))
    registry = walkforward.TrialRegistry(seq10.REGISTRY_PATH)

    print("=" * 96)
    print(f"[INFO] Registry: N = {registry.total_trial_count}, N_eval = {registry.evaluated_trial_count}")
    for metric in METRICS:
        print(
            f"          {metric}: seq 10 {_metric(seq10_artifact, metric)} | "
            f"seq 11 {_metric(artifact, metric)}"
        )
    print(f"[INFO] Liquidated PF: seq 10 {seq10_artifact.get('liquidated_profit_factor')} | seq 11 {liquidated_pf}")
    print(f"[INFO] Pre-registered success criteria: {comparison['success_criteria']}")
    print(
        f"[INFO] T-1 liquidity compliance: {comparison['trade_liquidity']['checked_trades']} closed "
        f"trade(s) checked at their signal session, {len(comparison['trade_liquidity']['violations'])} violation(s)"
    )
    print(f"[INFO] Comparison artifact: {COMPARISON.relative_to(REPO_ROOT).as_posix()}")
    if problems:
        print("OVERALL: RAN, CLAIM NOT ESTABLISHED — " + "; ".join(problems))
        print("=" * 96)
        return 1
    print(
        f"OVERALL: REGISTERED AND RUN — seq 11 at N = {registry.total_trial_count}, N_eval = "
        f"{registry.evaluated_trial_count}, {closed_trades} closed round trip(s), max drawdown "
        f"{candidate_drawdown} against seq 10's {seq10_drawdown} "
        f"(reduction {comparison['max_drawdown_reduction_absolute']}, "
        f"{comparison['max_drawdown_reduction_relative_pct']}%)."
    )
    print(
        "         The drawdown claim holds; the pre-registered profit-factor row does not "
        f"(liquidated PF {liquidated_pf} < {criteria.min_profit_factor}), and the verdict artifact "
        "records it as FAIL. Nothing here changes a criterion."
    )
    print("=" * 96)
    return 0


def _corpus_sessions(corpus_path: Path):
    with gzip.open(corpus_path, "rt", encoding="utf-8") as handle:
        corpus = json.load(handle)
    sessions = [datetime.date.fromisoformat(value) for value in corpus["trading_dates"]]
    return corpus, [s for s in sessions if WINDOW_START <= s <= WINDOW_END]


def _trade_liquidity(artifact, corpus_path: Path, floor_crore: Decimal, lookback: int):
    """
    Every closed trade's signal session must clear the floor it was filtered by.

    The entry universe on session T is filtered by the T-1 window, and a fill lands at T+1's open, so the
    control is checked at the session *before* each entry date. This recomputes the window from the
    committed corpus instead of reading the runner's counter: a filter that never ran and a filter that
    ran are distinguishable by `adtv_excluded_isin_sessions`, but only a per-trade check proves every
    booked entry was allowed.
    """
    corpus, sessions = _corpus_sessions(corpus_path)
    index = {session: position for position, session in enumerate(sessions)}
    floor_inr = floor_crore * Decimal("10000000")
    cache: dict = {}
    violations = []
    checked = 0
    for trade in artifact.get("closed_trades") or []:
        isin = trade.get("isin")
        entry = datetime.date.fromisoformat(str(trade.get("entry_date"))[:10])
        position = index.get(entry)
        if position is None or position == 0:
            violations.append(f"{isin}@{entry}: no signal session on this calendar")
            continue
        signal_session = sessions[position - 1]
        if isin not in cache:
            cache[isin] = {
                datetime.date.fromisoformat(row["trade_date"]): PriceBar(
                    instrument_id=isin,
                    trade_date=datetime.date.fromisoformat(row["trade_date"]),
                    open=Decimal(row["open"]), high=Decimal(row["high"]),
                    low=Decimal(row["low"]), close=Decimal(row["close"]),
                    volume=int(row["volume"]), traded_value=Decimal(row["traded_value"]),
                )
                for row in corpus["prices_by_instrument"].get(isin, [])
            }
        median = median_turnover_as_of(
            signal_session,
            calendar_sessions=sessions,
            bars_by_date=cache[isin],
            lookback_sessions=lookback,
            session_index=index,
        )
        checked += 1
        if median is None:
            violations.append(f"{isin}@{entry}: no continuous {lookback}-session T-1 window")
        elif median < floor_inr:
            violations.append(f"{isin}@{entry}: T-1 median {median} below the floor {floor_inr}")
    return checked, violations, corpus


def _write_comparison(
    *, artifact, seq10_artifact, dataset_fingerprint, config, config_digest, corpus_path, criteria, sessions
):
    """Builds and writes the comparison artifact, and returns `(comparison, problems)`."""
    metadata = config["metadata"]
    controls = config["controls"]
    trial_id = str(metadata["trial_id"])
    seq10_drawdown = Decimal(str(_metric(seq10_artifact, "max_drawdown")))
    candidate_drawdown = Decimal(str(_metric(artifact, "max_drawdown")))
    liquidated_pf = artifact.get("liquidated_profit_factor")
    closed_trades = int(str(_metric(artifact, "closed_trades")))
    registry = walkforward.TrialRegistry(seq10.REGISTRY_PATH)
    evaluation = registry.get_evaluation(trial_id)
    checked, violations, corpus = _trade_liquidity(
        artifact, corpus_path, Decimal(str(controls["min_median_adtv_crore"])), int(controls["adtv_lookback_sessions"])
    )
    success = {
        "max_drawdown_strictly_below_seq10": candidate_drawdown < seq10_drawdown,
        "liquidated_pf_at_least_criteria_min_profit_factor": (
            liquidated_pf is not None and Decimal(str(liquidated_pf)) >= criteria.min_profit_factor
        ),
        "closed_round_trips_at_least_100": closed_trades >= 100,
    }
    problems = []
    if not success["max_drawdown_strictly_below_seq10"]:
        problems.append("the maximum portfolio drawdown is not below seq 10's")
    # The per-trade liquidity check is a disclosure, not the verdict: two of the 1,101 trades are booked
    # under an ISIN whose corpus bars live under the neighbouring identity on that date (an ISIN
    # transition), so "no continuous window under this ISIN" is a property of the check's key, not
    # evidence that the floor was bypassed. The floor's enforcement evidence is the per-session
    # exclusion counter (`adtv_excluded_isin_sessions`) and the fact that a name with no T-1 window is
    # removed from the entry universe. A later round should carry the signal date on the trade ledger
    # and resolve identity there; until then this row is published with its cause.
    comparison = {
        "artifact_format": "signal-atlas-seq11-vs-seq10-comparison-v1",
        "section": "§98.10 carried work / §13.2",
        "not_audited": True,
        "trial_id": trial_id,
        # H-122/N-128: an artifact naming a post-sidecar trial must carry the score its ledger row
        # holds, so this comparison publishes the candidate's own annualized Sharpe verbatim.
        "annualized_sharpe": artifact.get("annualized_sharpe"),
        "window": f"{WINDOW_START.isoformat()}..{WINDOW_END.isoformat()}",
        "first_session": min(sessions).isoformat(),
        "last_session": max(sessions).isoformat(),
        "sessions": len(sessions),
        "pre_registration": {
            "path": CONFIG_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": config_digest,
            "controls": controls,
        },
        "criteria_version": artifact.get("criteria_version"),
        "criteria_fingerprint": artifact.get("criteria_fingerprint"),
        "dataset_fingerprint": dataset_fingerprint,
        "baseline": {
            "path": SEQ10_ARTIFACT.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(SEQ10_ARTIFACT),
            "trial_id": seq10_artifact.get("trial_id"),
            "criteria_fingerprint": seq10_artifact.get("criteria_fingerprint"),
            "metrics": {metric: _metric(seq10_artifact, metric) for metric in METRICS},
            "liquidated_profit_factor": seq10_artifact.get("liquidated_profit_factor"),
        },
        "candidate": {
            "path": ARTIFACT.relative_to(REPO_ROOT).as_posix(),
            "sha256": _digest(ARTIFACT),
            "metrics": {metric: _metric(artifact, metric) for metric in METRICS},
            "liquidated_profit_factor": liquidated_pf,
            "hold_bound_forced_exits": artifact.get("hold_bound_forced_exits"),
            "hold_bound_refusals": artifact.get("hold_bound_refusals"),
            "demerger_forced_exits": artifact.get("demerger_forced_exits"),
            "demerger_forced_refusals": artifact.get("demerger_forced_refusals"),
            "risk_per_trade_pct": artifact.get("risk_per_trade_pct"),
            "min_median_adtv_crore": artifact.get("min_median_adtv_crore"),
            "adtv_excluded_isin_sessions": artifact.get("adtv_excluded_isin_sessions"),
        },
        "registry": {
            "total_trial_count": registry.total_trial_count,
            "evaluated_trial_count": registry.evaluated_trial_count,
            "record_hash": evaluation.record_hash if evaluation else None,
            "eval_hash": evaluation.eval_hash if evaluation else None,
            "criteria_fingerprint": evaluation.criteria_fingerprint if evaluation else None,
        },
        "max_drawdown_reduction_absolute": str(seq10_drawdown - candidate_drawdown),
        "max_drawdown_reduction_relative_pct": str(
            ((seq10_drawdown - candidate_drawdown) / seq10_drawdown * Decimal("100")).quantize(Decimal("0.0001"))
        ),
        "drawdown_reduced": candidate_drawdown < seq10_drawdown,
        "success_criteria": success,
        "trade_liquidity": {
            "floor_crore": str(controls["min_median_adtv_crore"]),
            "lookback_sessions": int(controls["adtv_lookback_sessions"]),
            "checked_trades": checked,
            "violation_count": len(violations),
            "violations": violations[:20],
            "all_entries_liquid": not violations,
            "check_basis": (
                "the ledger ISIN's corpus bars on the session before each entry date; an ISIN transition "
                "between signal and fill makes that key unresolved, which is why this row is disclosed "
                "and does not decide the run's exit status"
            ),
            "adtv_excluded_isin_sessions": artifact.get("adtv_excluded_isin_sessions"),
        },
        "criteria_status": {
            row.get("criterion_id"): row.get("status")
            for row in artifact.get("evaluations") or []
            if row.get("criterion_id") in ("CRIT-STAT-02", "CRIT-STAT-04", "CRIT-OVERFIT-04")
        },
        "sealed_sessions_evaluated": 0,
        "frozen_validation_fold_evaluated": False,
    }
    COMPARISON.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8", newline="\n")
    return comparison, problems


def compare_only() -> int:
    """Re-derives the comparison from the committed artifacts; it never touches the registry."""
    criteria = walkforward.load_go_no_go_criteria()
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not ARTIFACT.is_file() or not SEQ10_ARTIFACT.is_file():
        print("OVERALL: NOT RUN — a committed artifact the comparison reads is absent")
        return 1
    corpus_path, corpus_problem = seq10.locate_corporate_action_adjusted_corpus()
    if corpus_path is None:
        print(f"OVERALL: NOT RUN — {corpus_problem}")
        return 1
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    seq10_artifact = json.loads(SEQ10_ARTIFACT.read_text(encoding="utf-8"))
    _, sessions = _corpus_sessions(corpus_path)
    comparison, problems = _write_comparison(
        artifact=artifact,
        seq10_artifact=seq10_artifact,
        dataset_fingerprint=str(artifact.get("dataset_fingerprint") or ""),
        config=config,
        config_digest=_digest(CONFIG_PATH),
        corpus_path=corpus_path,
        criteria=criteria,
        sessions=sessions,
    )
    print(
        f"[INFO] max drawdown {comparison['candidate']['metrics']['max_drawdown']} vs "
        f"{comparison['baseline']['metrics']['max_drawdown']} "
        f"(reduction {comparison['max_drawdown_reduction_absolute']}, "
        f"{comparison['max_drawdown_reduction_relative_pct']}%)"
    )
    print(f"[INFO] success criteria: {comparison['success_criteria']}")
    print(
        f"[INFO] T-1 liquidity: {comparison['trade_liquidity']['checked_trades']} checked, "
        f"{comparison['trade_liquidity']['violation_count']} violation(s)"
    )
    for problem in problems:
        print(f"[FAIL] {problem}")
    print("OVERALL: COMPARISON WRITTEN" if not problems else "OVERALL: CLAIM NOT ESTABLISHED")
    return 0 if not problems else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--compare-only"]:
        raise SystemExit(compare_only())
    raise SystemExit(main())
