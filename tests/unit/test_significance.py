"""
Unit Tests for Statistical Significance Engine (DSR & Haircut Sharpe).

Verifies Phase 2B Gates:
- G2B-1: DSR reproduces published worked examples within stated tolerance (Bailey & Lopez de Prado 2014).
- G2B-2: DSR decays monotonically as N grows at fixed Sharpe.
- G2B-3: Identical inputs yield bit-for-bit identical Decimal output.
- G2B-4: Haircut Sharpe decreases monotonically as N grows (Harvey & Liu 2015).
- G2B-5: Floating-point isolation (SIG-FLOAT-BOUNDARY) prevents floats from reaching ledger/PnL paths.
"""

from decimal import Decimal
import inspect
from pathlib import Path
import pytest

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


def test_exact_decimal_moments_estimation():
    """Verify exact Decimal arithmetic for sample mean, variance, std, skewness, and kurtosis."""
    returns = [
        Decimal("0.01"),
        Decimal("-0.02"),
        Decimal("0.015"),
        Decimal("0.005"),
        Decimal("-0.01"),
        Decimal("0.025"),
    ]

    mean_val = sample_mean(returns)
    assert isinstance(mean_val, Decimal)
    assert mean_val == Decimal("0.025") / Decimal("6")

    var_val = sample_variance(returns, ddof=1)
    assert isinstance(var_val, Decimal)
    assert var_val > Decimal("0.00")

    std_val = sample_std(returns, ddof=1)
    assert isinstance(std_val, Decimal)
    assert std_val == var_val.sqrt()

    skew_val = sample_skewness(returns)
    assert isinstance(skew_val, Decimal)

    kurt_raw = sample_kurtosis(returns, convention="RAW_NORMAL_THREE")
    kurt_excess = sample_kurtosis(returns, convention="EXCESS_NORMAL_ZERO")
    assert isinstance(kurt_raw, Decimal)
    assert isinstance(kurt_excess, Decimal)
    # Difference between raw and excess kurtosis must be exactly 3.00
    assert kurt_raw - kurt_excess == Decimal("3.00")

    sr_ann = annualized_sharpe(returns, sessions_per_year=250)
    assert isinstance(sr_ann, Decimal)
    assert sr_ann > Decimal("0.00")


def test_moments_symmetric_and_zero_variance():
    """Verify skewness of symmetric data is zero and zero variance returns valid constants."""
    # Perfectly symmetric returns
    sym_returns = [Decimal("-0.02"), Decimal("-0.01"), Decimal("0.00"), Decimal("0.01"), Decimal("0.02")]
    assert sample_skewness(sym_returns) == Decimal("0.00")

    # Identical returns (zero variance)
    flat_returns = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
    assert sample_variance(flat_returns, ddof=1) == Decimal("0.00")
    assert sample_std(flat_returns, ddof=1) == Decimal("0.00")
    assert sample_skewness(flat_returns) == Decimal("0.00")
    assert sample_kurtosis(flat_returns, convention="RAW_NORMAL_THREE") == Decimal("3.00")
    assert sample_kurtosis(flat_returns, convention="EXCESS_NORMAL_ZERO") == Decimal("0.00")
    assert annualized_sharpe(flat_returns) == Decimal("0.00")


def test_fail_closed_on_invalid_inputs_and_floats():
    """Verify that moment and significance functions fail closed on floats, booleans, and short samples."""
    # Floats strictly rejected
    with pytest.raises(InvalidSampleError, match="must be a Decimal"):
        sample_mean([0.01, 0.02])  # type: ignore

    # Booleans strictly rejected
    with pytest.raises(InvalidSampleError, match="must be a Decimal"):
        sample_variance([True, False])  # type: ignore

    # Non-finite Decimals rejected
    with pytest.raises(InvalidSampleError, match="must be finite"):
        sample_std([Decimal("NaN"), Decimal("0.01")])

    with pytest.raises(InvalidSampleError, match="must be finite"):
        sample_skewness([Decimal("Infinity"), Decimal("0.01"), Decimal("0.02")])

    # Insufficient observations
    with pytest.raises(InvalidSampleError, match="at least 1 observations"):
        sample_mean([])

    with pytest.raises(InvalidSampleError, match="at least 2 observations"):
        sample_variance([Decimal("0.01")], ddof=1)

    with pytest.raises(InvalidSampleError, match="at least 3 observations"):
        sample_skewness([Decimal("0.01"), Decimal("0.02")])

    with pytest.raises(InvalidSampleError, match="at least 4 observations"):
        sample_kurtosis([Decimal("0.01"), Decimal("0.02"), Decimal("0.03")])

    # Invalid parameters to DSR
    with pytest.raises(SignificanceError, match="trial_count_n"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=Decimal("1.50"),
            trial_sharpe_variance=Decimal("0.10"),
            observation_count=250,
            trial_count_n=0,
        )

    with pytest.raises(InvalidSampleError, match="observation_count"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=Decimal("1.50"),
            trial_sharpe_variance=Decimal("0.10"),
            observation_count=1,
            trial_count_n=10,
        )


def test_g2b1_dsr_golden_vector_parity():
    """
    Gate G2B-1: Verify DSR reproduces published worked example (Bailey & Lopez de Prado 2014).
    Reference Setup:
    - N = 100 trials
    - V = 0.50 trial Sharpe variance
    - T = 1250 daily sessions (~5 years)
    - SR_ann = 2.50 annualized Sharpe ratio
    - Skewness = -3.00
    - Kurtosis = 10.00 (raw, normal = 3)
    - q = 250 sessions per year
    Published Result: DSR approx 0.9004 (90.04%).
    """
    res = compute_deflated_sharpe_ratio(
        annualized_sharpe=Decimal("2.50"),
        trial_sharpe_variance=Decimal("0.50"),
        observation_count=1250,
        trial_count_n=100,
        sessions_per_year=250,
        skewness=Decimal("-3.00"),
        kurtosis=Decimal("10.00"),
    )

    assert isinstance(res, DeflatedSharpeResult)
    assert res.trial_count_n == 100
    # Expected maximum Sharpe SR0 evaluated in paper is ~1.7894
    assert abs(res.expected_max_sharpe - Decimal("1.789406")) <= Decimal("0.00001")
    # DSR probability matches published 0.9004 within 4 decimal places
    assert round(res.deflated_sharpe_ratio, 4) == Decimal("0.9004")
    assert res.deflated_sharpe_ratio == Decimal("0.900397")


def test_g2b2_dsr_monotonic_decay_with_n():
    """
    Gate G2B-2: Verify DSR decays strictly monotonically as trial count N grows at fixed Sharpe.
    """
    sr = Decimal("1.50")
    var = Decimal("0.25")
    obs = 500
    q = 250
    trials = [1, 5, 20, 100, 500]

    dsr_values = []
    for n in trials:
        res = compute_deflated_sharpe_ratio(
            annualized_sharpe=sr,
            trial_sharpe_variance=var,
            observation_count=obs,
            trial_count_n=n,
            sessions_per_year=q,
        )
        assert res.trial_count_n == n
        dsr_values.append(res.deflated_sharpe_ratio)

    # Assert strict monotonic decay: DSR(N_k) < DSR(N_{k-1})
    for idx in range(1, len(dsr_values)):
        assert dsr_values[idx] < dsr_values[idx - 1], f"DSR failed to decay at N={trials[idx]}: {dsr_values}"


def test_g2b3_bit_for_bit_identical_output():
    """
    Gate G2B-3: Verify that identical inputs produce bit-for-bit identical Decimal output.
    """
    inputs = {
        "annualized_sharpe": Decimal("1.85"),
        "trial_sharpe_variance": Decimal("0.12"),
        "observation_count": 750,
        "trial_count_n": 25,
        "sessions_per_year": 250,
        "skewness": Decimal("-0.25"),
        "kurtosis": Decimal("4.50"),
    }

    res1 = compute_deflated_sharpe_ratio(**inputs)
    res2 = compute_deflated_sharpe_ratio(**inputs)

    assert res1.deflated_sharpe_ratio == res2.deflated_sharpe_ratio
    assert str(res1.deflated_sharpe_ratio) == str(res2.deflated_sharpe_ratio)
    assert res1.expected_max_sharpe == res2.expected_max_sharpe
    assert res1.z_score == res2.z_score
    assert res1.p_value == res2.p_value

    hc1 = compute_haircut_sharpe_ratio(Decimal("1.85"), 750, 25, 250)
    hc2 = compute_haircut_sharpe_ratio(Decimal("1.85"), 750, 25, 250)

    assert hc1.haircut_sharpe_ratio == hc2.haircut_sharpe_ratio
    assert str(hc1.haircut_sharpe_ratio) == str(hc2.haircut_sharpe_ratio)
    assert hc1.haircut_percentage == hc2.haircut_percentage
    assert hc1.adjusted_p_value == hc2.adjusted_p_value


def test_g2b4_haircut_sharpe_monotonic_decrease_with_n():
    """
    Gate G2B-4: Verify that Haircut Sharpe decreases monotonically as trial count N grows (Harvey & Liu 2015).
    """
    sr = Decimal("2.00")
    obs = 1250
    q = 250
    trials = [1, 5, 20, 100, 1000]

    hc_values = []
    pct_values = []
    for n in trials:
        res = compute_haircut_sharpe_ratio(
            annualized_sharpe=sr,
            observation_count=obs,
            trial_count_n=n,
            sessions_per_year=q,
            haircut_variant="BONFERRONI",
        )
        assert res.trial_count_n == n
        hc_values.append(res.haircut_sharpe_ratio)
        pct_values.append(res.haircut_percentage)

    # At N=1: zero haircut, SR_hc equals original SR
    assert hc_values[0] == Decimal("2.000000")
    assert pct_values[0] == Decimal("0.0000")

    # Assert strict monotonic decrease of Haircut Sharpe
    for idx in range(1, len(hc_values)):
        assert hc_values[idx] < hc_values[idx - 1], f"Haircut Sharpe did not decrease at N={trials[idx]}: {hc_values}"
        assert pct_values[idx] > pct_values[idx - 1], f"Haircut % did not increase at N={trials[idx]}: {pct_values}"


def test_g2b5_float_boundary_isolation():
    """
    Gate G2B-5: Verify that no floating-point values leak across SIG-FLOAT-BOUNDARY into callers.
    """
    res = compute_deflated_sharpe_ratio(
        annualized_sharpe=Decimal("1.75"),
        trial_sharpe_variance=Decimal("0.15"),
        observation_count=500,
        trial_count_n=10,
    )
    for field in ("deflated_sharpe_ratio", "expected_max_sharpe", "z_score", "p_value", "observed_annualized_sharpe", "trial_sharpe_variance", "skewness", "kurtosis"):
        val = getattr(res, field)
        assert isinstance(val, Decimal), f"Field {field} must be Decimal, got {type(val)}"

    hc = compute_haircut_sharpe_ratio(Decimal("1.75"), 500, 10)
    for field in ("haircut_sharpe_ratio", "haircut_percentage", "original_annualized_sharpe", "t_statistic", "original_p_value", "adjusted_p_value"):
        val = getattr(hc, field)
        assert isinstance(val, Decimal), f"Field {field} must be Decimal, got {type(val)}"

    # Static assertion: ledger and position code must NEVER import significance.py
    import signal_core.portfolio.ledger as ledger_mod
    import signal_core.portfolio.position as pos_mod
    import signal_core.portfolio.portfolio as port_mod

    for mod in (ledger_mod, pos_mod, port_mod):
        source = inspect.getsource(mod)
        assert "significance" not in source, f"Module {mod.__name__} must not depend on significance engine"
        assert "_normal_cdf" not in source
        assert "_normal_quantile" not in source


def test_evaluate_strategy_significance_with_registry(tmp_path: Path):
    """
    Verify complete evaluation workflow:
    - Consumes total_trial_count as N and compute_trial_sharpe_variance as V from TrialRegistry.
    - Consumes criteria constants (sessions_per_year, kurtosis_convention, haircut_variant).
    - Tags every result with trial_count_n.
    - Evaluates computed verdicts against committed thresholds.
    """
    registry_file = tmp_path / "trials.jsonl"
    registry = TrialRegistry(registry_file)

    # Record 3 trials: 2 evaluated (SR 1.50 and 1.90), 1 unevaluated (None)
    registry.append_trial(
        trial_id="T1", hypothesis="H1", rationale="R1", partition="IN_SAMPLE",
        canonical_params={"p": 1}, fold_spec_fingerprint="F1", dataset_fingerprint="D1",
        criteria_version="1.1.0", timestamp_utc="2026-11-11T10:00:00Z", sharpe_ratio=Decimal("1.50"),
    )
    registry.append_trial(
        trial_id="T2", hypothesis="H2", rationale="R2", partition="IN_SAMPLE",
        canonical_params={"p": 2}, fold_spec_fingerprint="F1", dataset_fingerprint="D1",
        criteria_version="1.1.0", timestamp_utc="2026-11-11T10:01:00Z", sharpe_ratio=None,
    )
    registry.append_trial(
        trial_id="T3", hypothesis="H3", rationale="R3", partition="IN_SAMPLE",
        canonical_params={"p": 3}, fold_spec_fingerprint="F1", dataset_fingerprint="D1",
        criteria_version="1.1.0", timestamp_utc="2026-11-11T10:02:00Z", sharpe_ratio=Decimal("1.90"),
    )

    criteria = load_go_no_go_criteria()

    # Generate synthetic returns with high positive Sharpe
    returns = [Decimal("0.005") + (Decimal("0.001") if i % 2 == 0 else Decimal("-0.0005")) for i in range(250)]

    report = evaluate_strategy_significance(
        returns=returns,
        registry=registry,
        criteria=criteria,
        strategy_id="TEST_MOMENTUM_EQ",
    )

    assert isinstance(report, SignificanceReport)
    assert report.strategy_id == "TEST_MOMENTUM_EQ"
    # Auditor Condition 1: N = 3 consumed from total_trial_count
    assert report.trial_count_n == 3
    # N_eval = 2
    assert report.evaluated_trial_count == 2
    assert report.dsr_result.trial_count_n == 3
    assert report.haircut_result.trial_count_n == 3
    assert report.dsr_result.trial_sharpe_variance == Decimal("0.08")
    assert report.observation_count == 250
    assert report.criteria_version == "1.1.0"
    assert report.dsr_verdict in ("PASS", "FAIL")
    assert report.haircut_verdict in ("PASS", "FAIL")
    assert report.overall_verdict in ("PASS", "FAIL")


def test_n_equals_one_probabilistic_sharpe():
    """Verify that when N=1, SR0=0 (reduces to PSR) and Haircut Sharpe has zero discount."""
    sr = Decimal("1.50")
    obs = 500
    q = 250

    dsr_res = compute_deflated_sharpe_ratio(
        annualized_sharpe=sr,
        trial_sharpe_variance=Decimal("0.25"),
        observation_count=obs,
        trial_count_n=1,
        sessions_per_year=q,
    )
    # When N=1, expected maximum Sharpe is exactly 0.00
    assert dsr_res.expected_max_sharpe == Decimal("0.000000")
    assert dsr_res.trial_count_n == 1
    assert dsr_res.deflated_sharpe_ratio > Decimal("0.90")

    hc_res = compute_haircut_sharpe_ratio(
        annualized_sharpe=sr,
        observation_count=obs,
        trial_count_n=1,
        sessions_per_year=q,
    )
    # When N=1, no haircut is applied
    assert hc_res.haircut_sharpe_ratio == Decimal("1.500000")
    assert hc_res.haircut_percentage == Decimal("0.0000")
    assert hc_res.adjusted_p_value == hc_res.original_p_value
    assert hc_res.trial_count_n == 1


def test_negative_sharpe_ratio_penalties():
    """Verify that negative Sharpe ratios yield DSR < 0.50 and 100% haircut."""
    sr = Decimal("-0.75")
    obs = 500
    q = 250

    dsr_res = compute_deflated_sharpe_ratio(
        annualized_sharpe=sr,
        trial_sharpe_variance=Decimal("0.10"),
        observation_count=obs,
        trial_count_n=10,
        sessions_per_year=q,
    )
    assert dsr_res.deflated_sharpe_ratio < Decimal("0.50")
    assert dsr_res.z_score < Decimal("0.00")

    hc_res = compute_haircut_sharpe_ratio(
        annualized_sharpe=sr,
        observation_count=obs,
        trial_count_n=10,
        sessions_per_year=q,
    )
    assert hc_res.haircut_sharpe_ratio == Decimal("0.000000")
    assert hc_res.haircut_percentage == Decimal("100.0000")


def test_bonferroni_extreme_penalty_cap():
    """Verify that when Bonferroni p_adj >= 1.0, haircut is strictly capped at 100% and SR_hc is 0."""
    # Marginal Sharpe of 0.30 over 250 sessions with N=100 trials
    hc_res = compute_haircut_sharpe_ratio(
        annualized_sharpe=Decimal("0.30"),
        observation_count=250,
        trial_count_n=100,
        sessions_per_year=250,
    )
    assert hc_res.adjusted_p_value == Decimal("1.000000")
    assert hc_res.haircut_sharpe_ratio == Decimal("0.000000")
    assert hc_res.haircut_percentage == Decimal("100.0000")


def test_significance_report_fail_verdict_when_below_threshold(tmp_path: Path):
    """Verify computed FAIL verdicts when strategy does not meet Go/No-Go criteria thresholds."""
    registry_file = tmp_path / "trials.jsonl"
    registry = TrialRegistry(registry_file)
    registry.append_trial(
        trial_id="T1", hypothesis="H1", rationale="R1", partition="IN_SAMPLE",
        canonical_params={"p": 1}, fold_spec_fingerprint="F1", dataset_fingerprint="D1",
        criteria_version="1.1.0", timestamp_utc="2026-11-11T10:00:00Z", sharpe_ratio=Decimal("1.00"),
    )

    criteria = load_go_no_go_criteria()

    # Noisy, flat returns with low Sharpe
    noisy_returns = [Decimal("0.0001") if i % 2 == 0 else Decimal("-0.0001") for i in range(250)]

    report = evaluate_strategy_significance(
        returns=noisy_returns,
        registry=registry,
        criteria=criteria,
        strategy_id="NOISY_FLAT_STRATEGY",
    )

    # Thresholds are 0.95 for DSR and 1.25 for Haircut Sharpe
    assert report.dsr_verdict == "FAIL"
    assert report.haircut_verdict == "FAIL"
    assert report.overall_verdict == "FAIL"


def test_c2_docstring_and_tagging_invariants():
    """Verify residual C-2 architectural disclosure and trial_count_n tagging invariants."""
    import signal_core.research.significance as sig_mod
    doc = sig_mod.__doc__
    assert doc is not None
    assert "Residual C-2" in doc or "C-2" in doc
    assert "SIG-FLOAT-BOUNDARY" in doc

    # Every public dataclass must carry trial_count_n
    for cls in (DeflatedSharpeResult, HaircutSharpeResult, SignificanceReport):
        assert "trial_count_n" in cls.__slots__


def test_d1_zero_variance_and_insufficient_n_eval_rejection():
    """
    D-1 Remediation: When trial_count_n > 1, computing DSR requires at least 2 evaluated trials
    and strictly positive trial Sharpe variance (V > 0).
    Verifies that N=50, V=0.00 fails closed rather than silently manufacturing DSR 0.966639 PASS.
    """
    sr = Decimal("1.30")
    t_obs = 500
    q = 250
    n = 50

    # 1. Zero variance when N=50 must raise InvalidSampleError fail-closed
    with pytest.raises(InvalidSampleError, match="strictly positive trial Sharpe variance"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=sr,
            trial_sharpe_variance=Decimal("0.00"),
            observation_count=t_obs,
            trial_count_n=n,
            sessions_per_year=q,
            evaluated_trial_count=50,
        )

    # 2. Insufficient evaluated trials (N_eval < 2) must raise InvalidSampleError
    with pytest.raises(InvalidSampleError, match="at least 2 evaluated trials"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=sr,
            trial_sharpe_variance=Decimal("0.25"),
            observation_count=t_obs,
            trial_count_n=n,
            sessions_per_year=q,
            evaluated_trial_count=1,
        )

    # 3. Valid variance V=0.3367 yields the true penalized DSR 0.488273 (FAIL against 0.95)
    res_valid = compute_deflated_sharpe_ratio(
        annualized_sharpe=sr,
        trial_sharpe_variance=Decimal("0.3367"),
        observation_count=t_obs,
        trial_count_n=n,
        sessions_per_year=q,
        evaluated_trial_count=50,
    )
    assert res_valid.deflated_sharpe_ratio == Decimal("0.488273")
    assert res_valid.deflated_sharpe_ratio < Decimal("0.95")  # True FAIL, penalty applied


def test_d2_non_positive_mertens_variance_term_raises():
    """
    D-2 Remediation: Non-positive Mertens asymptotic variance term must raise SignificanceError
    rather than silently substituting denom = 1e-6 and manufacturing a false 1.000000 PASS.
    """
    # Auditor probe: SR_ann = 4.74, skewness = 5.00, kurtosis = 3.00, q = 250 -> var_term = -0.45398 <= 0
    with pytest.raises(SignificanceError, match="Mertens asymptotic Sharpe variance term is non-positive"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=Decimal("4.74"),
            trial_sharpe_variance=Decimal("0.25"),
            observation_count=500,
            trial_count_n=10,
            sessions_per_year=250,
            skewness=Decimal("5.00"),
            kurtosis=Decimal("3.00"),
        )

    # Mirror skewness -5.00 has valid positive variance term and evaluates cleanly
    mirror_res = compute_deflated_sharpe_ratio(
        annualized_sharpe=Decimal("4.74"),
        trial_sharpe_variance=Decimal("0.25"),
        observation_count=500,
        trial_count_n=10,
        sessions_per_year=250,
        skewness=Decimal("-5.00"),
        kurtosis=Decimal("3.00"),
    )
    assert mirror_res.deflated_sharpe_ratio > Decimal("0.00")
    assert mirror_res.z_score > Decimal("0.00")


def test_d3_kurtosis_convention_dsr_invariance():
    """
    D-3 Remediation: DSR must be mathematically invariant whether raw kurtosis (3.00 for normal)
    or excess kurtosis (0.00 for normal) is specified.
    """
    # Raw kurtosis = 4.50 (normal = 3.00) vs Excess kurtosis = 1.50 (normal = 0.00)
    res_raw = compute_deflated_sharpe_ratio(
        annualized_sharpe=Decimal("1.80"),
        trial_sharpe_variance=Decimal("0.20"),
        observation_count=500,
        trial_count_n=15,
        sessions_per_year=250,
        skewness=Decimal("-0.30"),
        kurtosis=Decimal("4.50"),
        kurtosis_convention="RAW_NORMAL_THREE",
    )

    res_excess = compute_deflated_sharpe_ratio(
        annualized_sharpe=Decimal("1.80"),
        trial_sharpe_variance=Decimal("0.20"),
        observation_count=500,
        trial_count_n=15,
        sessions_per_year=250,
        skewness=Decimal("-0.30"),
        kurtosis=Decimal("1.50"),
        kurtosis_convention="EXCESS_NORMAL_ZERO",
    )

    # Both must agree bit-for-bit on all statistical fields
    assert res_raw.deflated_sharpe_ratio == res_excess.deflated_sharpe_ratio
    assert res_raw.z_score == res_excess.z_score
    assert res_raw.expected_max_sharpe == res_excess.expected_max_sharpe
    assert res_raw.p_value == res_excess.p_value
    assert res_raw.kurtosis == Decimal("4.50")
    assert res_excess.kurtosis == Decimal("4.50")  # Effective raw kurtosis


def test_d5_evaluated_trial_count_cannot_exceed_total():
    """
    D-5 Remediation: evaluated_trial_count > trial_count_n must be rejected with SignificanceError.
    """
    with pytest.raises(SignificanceError, match="cannot exceed total trial_count_n"):
        compute_deflated_sharpe_ratio(
            annualized_sharpe=Decimal("1.50"),
            trial_sharpe_variance=Decimal("0.20"),
            observation_count=500,
            trial_count_n=2,
            evaluated_trial_count=50,
        )
