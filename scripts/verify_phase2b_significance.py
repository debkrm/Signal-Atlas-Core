"""
Authoritative Reproducible Verification Probe for Phase 2B (Statistical Significance Engine).

Computes and prints exact verdicts for all Phase 2B gates:
- Gate G2B-1: DSR reproduces published worked examples within stated tolerance (Bailey & Lopez de Prado 2014).
- Gate G2B-2: DSR decays monotonically as N grows at fixed Sharpe.
- Gate G2B-3: Identical inputs yield bit-for-bit identical Decimal output.
- Gate G2B-4: Haircut Sharpe decreases monotonically as N grows (Harvey & Liu 2015).
- Gate G2B-5: Floating-point isolation (SIG-FLOAT-BOUNDARY) prevents floats from reaching ledger/PnL paths.
- Integration: Consumes N and V from TrialRegistry and methodology constants from GoNoGoCriteria.

No hand-typed status labels. All verdicts are derived from runtime assertions and computed booleans.
"""

import datetime
from decimal import Decimal
import inspect
from pathlib import Path
import shutil
import sys
import tempfile

# Ensure src/ is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_core.contracts.criteria import GoNoGoCriteria, load_go_no_go_criteria
from signal_core.research.trials import TrialRegistry
from signal_core.research.significance import (
    DeflatedSharpeResult,
    HaircutSharpeResult,
    InvalidSampleError,
    SignificanceError,
    SignificanceReport,
    annualized_sharpe,
    compute_deflated_sharpe_ratio,
    compute_haircut_sharpe_ratio,
    evaluate_strategy_significance,
    sample_kurtosis,
    sample_mean,
    sample_skewness,
    sample_std,
    sample_variance,
)


def run_phase_2b_verification() -> bool:
    print("=" * 80)
    print("SIGNAL ATLAS — PHASE 2B STATISTICAL SIGNIFICANCE ENGINE VERIFICATION PROBE")
    print(f"Executed at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    all_passed = True
    temp_dir = Path(tempfile.mkdtemp(prefix="phase2b_probe_"))

    try:
        # ----------------------------------------------------------------------
        # GATE G2B-1: DSR Golden Vector Parity (Bailey & Lopez de Prado 2014)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B-1: DSR Golden Vector Parity against Published Example ---")
        g2b1_passed = True

        res = compute_deflated_sharpe_ratio(
            annualized_sharpe=Decimal("2.50"),
            trial_sharpe_variance=Decimal("0.50"),
            observation_count=1250,
            trial_count_n=100,
            sessions_per_year=250,
            skewness=Decimal("-3.00"),
            kurtosis=Decimal("10.00"),
        )

        # Published paper: DSR approx 0.9004, expected maximum Sharpe ~ 1.7894
        sr0_ok = abs(res.expected_max_sharpe - Decimal("1.789406")) <= Decimal("0.00001")
        dsr_4dec_ok = round(res.deflated_sharpe_ratio, 4) == Decimal("0.9004")
        dsr_6dec_ok = res.deflated_sharpe_ratio == Decimal("0.900397")

        if sr0_ok and dsr_4dec_ok and dsr_6dec_ok and res.trial_count_n == 100:
            print(f"[PASS] G2B-1.1: Golden vector reproduced exactly:")
            print(f"       Published: DSR=0.9004 | Computed: DSR={res.deflated_sharpe_ratio} (rounded: {round(res.deflated_sharpe_ratio, 4)})")
            print(f"       Expected max Sharpe SR*: {res.expected_max_sharpe} | z-score: {res.z_score}")
        else:
            print(f"[FAIL] G2B-1.1: Golden vector mismatch: DSR={res.deflated_sharpe_ratio}, SR*={res.expected_max_sharpe}")
            g2b1_passed = False

        all_passed = all_passed and g2b1_passed

        # ----------------------------------------------------------------------
        # GATE G2B-2: Monotonic Decay of DSR as N Grows at Fixed Sharpe
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B-2: Monotonic Decay of DSR as Trial Count N Increases ---")
        g2b2_passed = True

        trial_counts = [1, 5, 20, 100, 500]
        dsr_curve = []
        for n in trial_counts:
            r = compute_deflated_sharpe_ratio(
                annualized_sharpe=Decimal("1.50"),
                trial_sharpe_variance=Decimal("0.25"),
                observation_count=500,
                trial_count_n=n,
                sessions_per_year=250,
            )
            dsr_curve.append((n, r.deflated_sharpe_ratio, r.expected_max_sharpe))

        monotonic_decay = True
        for idx in range(1, len(dsr_curve)):
            if not (dsr_curve[idx][1] < dsr_curve[idx - 1][1]):
                monotonic_decay = False
                break

        if monotonic_decay:
            print(f"[PASS] G2B-2.1: DSR decays strictly monotonically as N increases at fixed Sharpe (1.50):")
            for n, val, sr0 in dsr_curve:
                print(f"       N = {n:4d}  ->  DSR = {val}  (expected max SR* = {sr0})")
        else:
            print(f"[FAIL] G2B-2.1: DSR failed monotonic decay: {dsr_curve}")
            g2b2_passed = False

        all_passed = all_passed and g2b2_passed

        # ----------------------------------------------------------------------
        # GATE G2B-3: Identical Inputs Yield Bit-for-Bit Identical Decimal Output
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B-3: Bit-for-Bit Determinism across Identical Inputs ---")
        g2b3_passed = True

        params = {
            "annualized_sharpe": Decimal("1.85"),
            "trial_sharpe_variance": Decimal("0.12"),
            "observation_count": 750,
            "trial_count_n": 25,
            "sessions_per_year": 250,
            "skewness": Decimal("-0.25"),
            "kurtosis": Decimal("4.50"),
        }
        res_a = compute_deflated_sharpe_ratio(**params)
        res_b = compute_deflated_sharpe_ratio(**params)

        exact_match = (
            res_a.deflated_sharpe_ratio == res_b.deflated_sharpe_ratio
            and str(res_a.deflated_sharpe_ratio) == str(res_b.deflated_sharpe_ratio)
            and res_a.expected_max_sharpe == res_b.expected_max_sharpe
            and res_a.z_score == res_b.z_score
            and res_a.p_value == res_b.p_value
        )

        hc_a = compute_haircut_sharpe_ratio(Decimal("1.85"), 750, 25, 250)
        hc_b = compute_haircut_sharpe_ratio(Decimal("1.85"), 750, 25, 250)
        hc_exact = (
            hc_a.haircut_sharpe_ratio == hc_b.haircut_sharpe_ratio
            and str(hc_a.haircut_sharpe_ratio) == str(hc_b.haircut_sharpe_ratio)
            and hc_a.haircut_percentage == hc_b.haircut_percentage
        )

        if exact_match and hc_exact:
            print(f"[PASS] G2B-3.1: Identical inputs produce bit-for-bit identical Decimal results.")
            print(f"       DSR: {res_a.deflated_sharpe_ratio} == {res_b.deflated_sharpe_ratio}")
            print(f"       Haircut SR: {hc_a.haircut_sharpe_ratio} == {hc_b.haircut_sharpe_ratio}")
        else:
            print(f"[FAIL] G2B-3.1: Output variation detected between identical calls.")
            g2b3_passed = False

        all_passed = all_passed and g2b3_passed

        # ----------------------------------------------------------------------
        # GATE G2B-4: Haircut Sharpe Monotonic Decrease in N (Harvey & Liu 2015)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B-4: Monotonic Decrease of Haircut Sharpe in N ---")
        g2b4_passed = True

        hc_counts = [1, 5, 20, 100, 1000]
        hc_curve = []
        for n in hc_counts:
            h = compute_haircut_sharpe_ratio(
                annualized_sharpe=Decimal("2.00"),
                observation_count=1250,
                trial_count_n=n,
                sessions_per_year=250,
                haircut_variant="BONFERRONI",
            )
            hc_curve.append((n, h.haircut_sharpe_ratio, h.haircut_percentage, h.adjusted_p_value))

        # Check N=1 is zero haircut
        n1_ok = hc_curve[0][1] == Decimal("2.000000") and hc_curve[0][2] == Decimal("0.0000")
        hc_monotonic = True
        for idx in range(1, len(hc_curve)):
            if not (hc_curve[idx][1] < hc_curve[idx - 1][1] and hc_curve[idx][2] > hc_curve[idx - 1][2]):
                hc_monotonic = False
                break

        if n1_ok and hc_monotonic:
            print(f"[PASS] G2B-4.1: Haircut Sharpe decreases and haircut % increases monotonically in N:")
            for n, sr_hc, pct, p_adj in hc_curve:
                print(f"       N = {n:4d}  ->  Haircut SR = {sr_hc}  |  Haircut = {pct}%  |  p_adj = {p_adj}")
        else:
            print(f"[FAIL] G2B-4.1: Haircut Sharpe failed monotonic properties: {hc_curve}")
            g2b4_passed = False

        all_passed = all_passed and g2b4_passed

        # ----------------------------------------------------------------------
        # GATE G2B-5: Floating-Point Boundary Isolation (SIG-FLOAT-BOUNDARY)
        # ----------------------------------------------------------------------
        print("\n--- Gate G2B-5: Float Boundary Isolation (SIG-FLOAT-BOUNDARY) ---")
        g2b5_passed = True

        # 1. Output types check
        for field in ("deflated_sharpe_ratio", "expected_max_sharpe", "z_score", "p_value", "observed_annualized_sharpe", "trial_sharpe_variance", "skewness", "kurtosis"):
            val = getattr(res_a, field)
            if not isinstance(val, Decimal):
                print(f"[FAIL] G2B-5.1: Field {field} is {type(val)}, expected Decimal")
                g2b5_passed = False

        for field in ("haircut_sharpe_ratio", "haircut_percentage", "original_annualized_sharpe", "t_statistic", "original_p_value", "adjusted_p_value"):
            val = getattr(hc_a, field)
            if not isinstance(val, Decimal):
                print(f"[FAIL] G2B-5.2: Field {field} is {type(val)}, expected Decimal")
                g2b5_passed = False

        # 2. Strict rejection of float inputs in moment calculations
        float_rejected = False
        try:
            sample_mean([0.01, 0.02])  # type: ignore
        except InvalidSampleError:
            float_rejected = True

        # 3. Static assertion that accounting / ledger code does not import significance
        import signal_core.portfolio.ledger as ledger_mod
        import signal_core.portfolio.position as pos_mod
        import signal_core.portfolio.portfolio as port_mod

        isolation_verified = True
        for mod in (ledger_mod, pos_mod, port_mod):
            source = inspect.getsource(mod)
            if "significance" in source or "_normal_cdf" in source or "_normal_quantile" in source:
                isolation_verified = False
                print(f"[FAIL] G2B-5.3: Module {mod.__name__} violates float boundary isolation")

        if g2b5_passed and float_rejected and isolation_verified:
            print(f"[PASS] G2B-5.1: Pure Decimal outputs across all statistical result objects (zero float leakage).")
            print(f"[PASS] G2B-5.2: Moment estimators fail closed on float inputs with InvalidSampleError.")
            print(f"[PASS] G2B-5.3: Portfolio, ledger, and position engines strictly decoupled from significance math.")
        else:
            g2b5_passed = False

        all_passed = all_passed and g2b5_passed

        # ----------------------------------------------------------------------
        # INTEGRATION: TrialRegistry & GoNoGoCriteria End-to-End Evaluation
        # ----------------------------------------------------------------------
        print("\n--- Integration: TrialRegistry Consumption & Criteria Thresholding ---")
        integ_passed = True

        registry_path = temp_dir / "audit_registry.jsonl"
        reg = TrialRegistry(registry_path)

        reg.append_trial(
            trial_id="TR_01", hypothesis="Momentum breakout", rationale="50-day high entry",
            partition="IN_SAMPLE", canonical_params={"lookback": 50}, fold_spec_fingerprint="F1",
            dataset_fingerprint="D1", criteria_version="1.1.0", timestamp_utc="2026-11-11T10:00:00Z",
            sharpe_ratio=Decimal("1.60"),
        )
        reg.append_trial(
            trial_id="TR_02", hypothesis="Trend follow", rationale="Failed filter",
            partition="IN_SAMPLE", canonical_params={"lookback": 100}, fold_spec_fingerprint="F1",
            dataset_fingerprint="D1", criteria_version="1.1.0", timestamp_utc="2026-11-11T10:01:00Z",
            sharpe_ratio=None,
        )
        reg.append_trial(
            trial_id="TR_03", hypothesis="Momentum pull-back", rationale="20-day dip entry",
            partition="IN_SAMPLE", canonical_params={"lookback": 20}, fold_spec_fingerprint="F1",
            dataset_fingerprint="D1", criteria_version="1.1.0", timestamp_utc="2026-11-11T10:02:00Z",
            sharpe_ratio=Decimal("2.00"),
        )

        crit = load_go_no_go_criteria()

        # Generate realistic synthetic equity return series
        returns = [Decimal("0.0012") + (Decimal("0.0008") if i % 3 != 0 else Decimal("-0.0015")) for i in range(500)]

        report = evaluate_strategy_significance(
            returns=returns,
            registry=reg,
            criteria=crit,
            strategy_id="NIFTY_MOMENTUM_ALPHA",
        )

        # Invariants from Auditor Conditions:
        # N = 3 consumed from total_trial_count
        # N_eval = 2 consumed for variance
        n_ok = report.trial_count_n == 3 and report.dsr_result.trial_count_n == 3 and report.haircut_result.trial_count_n == 3
        var_ok = report.evaluated_trial_count == 2 and report.dsr_result.trial_sharpe_variance == Decimal("0.08")
        verdict_computed = report.dsr_verdict in ("PASS", "FAIL") and report.overall_verdict in ("PASS", "FAIL")

        if n_ok and var_ok and verdict_computed:
            print(f"[PASS] Integration.1: N = {report.trial_count_n} consumed from total_trial_count.")
            print(f"[PASS] Integration.2: N_eval = {report.evaluated_trial_count}, Sharpe variance V = {report.dsr_result.trial_sharpe_variance}.")
            print(f"[PASS] Integration.3: Annualized Sharpe = {report.annualized_sharpe}, DSR = {report.dsr_result.deflated_sharpe_ratio} (threshold {report.dsr_threshold}) -> {report.dsr_verdict}.")
            print(f"[PASS] Integration.4: Haircut Sharpe = {report.haircut_result.haircut_sharpe_ratio} (threshold {report.haircut_threshold}) -> {report.haircut_verdict}.")
            print(f"[PASS] Integration.5: Overall computed verdict: {report.overall_verdict}.")
        else:
            print(f"[FAIL] Integration checks failed: N={report.trial_count_n}, V={report.dsr_result.trial_sharpe_variance}")
            integ_passed = False

        all_passed = all_passed and integ_passed

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 80)
    if all_passed:
        print("PHASE 2B FINAL PROBE VERDICT: ALL MEASURED GATES PASSED (100%)")
    else:
        print("PHASE 2B FINAL PROBE VERDICT: ONE OR MORE GATES FAILED")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_phase_2b_verification()
    sys.exit(0 if success else 1)

