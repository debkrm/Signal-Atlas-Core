"""
Statistical Significance Engine: Deflated Sharpe Ratio (DSR) & Haircut Sharpe Ratio.

Implements statistical testing protocols per AGENTS.md Rule 8.2 and Phase 2B:
- Exact Decimal estimators for sample mean, variance, standard deviation, skewness, and kurtosis.
- Deflated Sharpe Ratio (DSR) per Bailey & Lopez de Prado (2014), adjusting for selection bias,
  number of trials N, variance of trials V, track record length T, skewness, and kurtosis.
- Haircut Sharpe Ratio per Harvey & Liu (2015) under the Bonferroni multiple-testing adjustment.
- Strict isolation of floating-point arithmetic (SIG-FLOAT-BOUNDARY) to standard normal CDF/quantile.
- Pinned methodology constants consumed directly from committed GoNoGoCriteria.
- Every statistical result is explicitly tagged with the trial count N actually used.

Operational Residual C-2 Architecture Note:
------------------------------------------
Truncating a trial registry to an empty file and deleting its manifest produces a clean empty registry.
Detection of an intentional or accidental audit wipe relies on version control (git commit history / diff).
The authoritative trial count N feeding DSR must originate from a committed, version-controlled TrialRegistry.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from signal_core.contracts.criteria import GoNoGoCriteria
from signal_core.research.trials import TrialRegistry


STAT_PRECISION = Decimal("0.000001")


class SignificanceError(ValueError):
    """Base exception for statistical significance engine errors."""
    pass


class InvalidSampleError(SignificanceError):
    """Raised when return series or sample size violates statistical preconditions."""
    pass


# ==============================================================================
# Exact Decimal Moment Estimators
# ==============================================================================

def _validate_decimal_sequence(
    values: Sequence[Decimal],
    param_name: str,
    min_length: int = 1,
) -> Tuple[Decimal, ...]:
    """Validates that the input is a sequence of finite Decimal instances."""
    if not isinstance(values, (list, tuple)):
        raise InvalidSampleError(f"'{param_name}' must be a list or tuple of Decimals, got {type(values)}")
    if len(values) < min_length:
        raise InvalidSampleError(
            f"'{param_name}' must contain at least {min_length} observations, got {len(values)}"
        )
    result = []
    for idx, v in enumerate(values):
        if isinstance(v, bool) or not isinstance(v, Decimal):
            raise InvalidSampleError(
                f"Element at index {idx} in '{param_name}' must be a Decimal, got {type(v).__name__}: {v!r}"
            )
        if not v.is_finite():
            raise InvalidSampleError(
                f"Element at index {idx} in '{param_name}' must be finite, got {v!r}"
            )
        result.append(v)
    return tuple(result)


def sample_mean(returns: Sequence[Decimal]) -> Decimal:
    """
    Computes arithmetic sample mean of a Decimal sequence:
    mean = sum(returns) / T
    """
    clean = _validate_decimal_sequence(returns, "returns", min_length=1)
    total = sum(clean, Decimal("0.00"))
    return total / Decimal(len(clean))


def sample_variance(returns: Sequence[Decimal], ddof: int = 1) -> Decimal:
    """
    Computes sample variance using exact Decimal arithmetic:
    s^2 = sum((r_t - mean)^2) / (T - ddof)
    """
    if ddof < 0:
        raise SignificanceError(f"ddof must be non-negative, got {ddof}")
    clean = _validate_decimal_sequence(returns, "returns", min_length=ddof + 1)
    t = len(clean)
    mean_val = sample_mean(clean)
    sq_diff_sum = sum(((r - mean_val) ** 2 for r in clean), Decimal("0.00"))
    return sq_diff_sum / Decimal(t - ddof)


def sample_std(returns: Sequence[Decimal], ddof: int = 1) -> Decimal:
    """
    Computes sample standard deviation using exact Decimal.sqrt():
    s = sqrt(sample_variance(returns, ddof))
    """
    var_val = sample_variance(returns, ddof=ddof)
    return var_val.sqrt()


def sample_skewness(returns: Sequence[Decimal]) -> Decimal:
    """
    Computes sample skewness (Fisher-Pearson standard moment):
    gamma_3 = m_3 / (m_2^(3/2))
    where m_k = sum((r_t - mean)^k) / T.
    Returns Decimal("0.00") if variance is zero.
    Requires T >= 3 observations.
    """
    clean = _validate_decimal_sequence(returns, "returns", min_length=3)
    t = Decimal(len(clean))
    mean_val = sample_mean(clean)

    m2 = sum(((r - mean_val) ** 2 for r in clean), Decimal("0.00")) / t
    if m2 == Decimal("0.00"):
        return Decimal("0.00")

    m3 = sum(((r - mean_val) ** 3 for r in clean), Decimal("0.00")) / t
    std_m2 = m2.sqrt()
    denom = m2 * std_m2
    if denom == Decimal("0.00"):
        return Decimal("0.00")
    return m3 / denom


def sample_kurtosis(returns: Sequence[Decimal], convention: str = "RAW_NORMAL_THREE") -> Decimal:
    """
    Computes sample kurtosis:
    raw_kurtosis = m_4 / (m_2^2)
    where m_k = sum((r_t - mean)^k) / T.
    If convention == 'RAW_NORMAL_THREE': returns raw_kurtosis (standard normal = 3.0).
    If convention == 'EXCESS_NORMAL_ZERO': returns raw_kurtosis - 3.0 (standard normal = 0.0).
    Returns Decimal("3.00") (or 0.00) if variance is zero.
    Requires T >= 4 observations.
    """
    if convention not in ("RAW_NORMAL_THREE", "EXCESS_NORMAL_ZERO"):
        raise SignificanceError(
            f"Unsupported kurtosis convention '{convention}'. Must be 'RAW_NORMAL_THREE' or 'EXCESS_NORMAL_ZERO'."
        )
    clean = _validate_decimal_sequence(returns, "returns", min_length=4)
    t = Decimal(len(clean))
    mean_val = sample_mean(clean)

    m2 = sum(((r - mean_val) ** 2 for r in clean), Decimal("0.00")) / t
    if m2 == Decimal("0.00"):
        return Decimal("3.00") if convention == "RAW_NORMAL_THREE" else Decimal("0.00")

    m4 = sum(((r - mean_val) ** 4 for r in clean), Decimal("0.00")) / t
    raw_kurt = m4 / (m2 ** 2)

    if convention == "RAW_NORMAL_THREE":
        return raw_kurt
    return raw_kurt - Decimal("3.00")


def annualized_sharpe(
    returns: Sequence[Decimal],
    sessions_per_year: int = 250,
    risk_free_rate: Decimal = Decimal("0.00"),
) -> Decimal:
    """
    Computes annualized Sharpe ratio from daily session returns using exact Decimal:
    SR_ann = ((mean(returns) - r_f) / std(returns, ddof=1)) * sqrt(sessions_per_year)
    Requires T >= 2 observations.
    """
    if isinstance(sessions_per_year, bool) or not isinstance(sessions_per_year, int) or sessions_per_year <= 0:
        raise SignificanceError(f"sessions_per_year must be a positive integer, got {sessions_per_year!r}")
    if isinstance(risk_free_rate, bool) or not isinstance(risk_free_rate, Decimal) or not risk_free_rate.is_finite():
        raise SignificanceError(f"risk_free_rate must be a finite Decimal, got {risk_free_rate!r}")

    clean = _validate_decimal_sequence(returns, "returns", min_length=2)
    mean_val = sample_mean(clean)
    std_val = sample_std(clean, ddof=1)
    if std_val == Decimal("0.00"):
        return Decimal("0.00")

    daily_sr = (mean_val - risk_free_rate) / std_val
    annualization_factor = Decimal(sessions_per_year).sqrt()
    return daily_sr * annualization_factor


# ==============================================================================
# SIG-FLOAT-BOUNDARY: Isolated Floating-Point Arithmetic Boundary
# Confined strictly to standard normal CDF (Phi) and quantile (Phi^-1) functions.
# No float values leak out of this boundary into financial ledger, cost, or PnL paths.
# ==============================================================================

_NORMAL_DIST = statistics.NormalDist(mu=0.0, sigma=1.0)
_EULER_MASCHERONI_FLOAT = 0.57721566490153286060651209
_EULER_E_FLOAT = math.e


def _normal_cdf(x: float) -> float:
    """Computes standard normal cumulative distribution function Phi(x)."""
    return _NORMAL_DIST.cdf(x)


def _normal_quantile(p: float) -> float:
    """Computes standard normal quantile / inverse CDF Phi^-1(p) for p in (0, 1)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"Normal quantile argument p must be strictly in (0, 1), got {p}")
    return _NORMAL_DIST.inv_cdf(p)


def _compute_expected_max_sharpe_float(variance_ann: float, n: int) -> float:
    """
    Computes expected maximum Sharpe ratio under H0: SR = 0 across N trials.
    Formula: Bailey & Lopez de Prado (2014), Equation (10):
    SR* = sqrt(V) * ((1 - gamma) * Z^-1(1 - 1/N) + gamma * Z^-1(1 - 1/(N * e)))
    When N = 1 or V <= 0, SR* = 0.0.
    """
    if n <= 1 or variance_ann <= 0.0:
        return 0.0
    q1 = max(1e-15, min(1.0 - 1e-15, 1.0 - 1.0 / n))
    q2 = max(1e-15, min(1.0 - 1e-15, 1.0 - 1.0 / (n * _EULER_E_FLOAT)))
    z1 = _normal_quantile(q1)
    z2 = _normal_quantile(q2)
    return math.sqrt(variance_ann) * ((1.0 - _EULER_MASCHERONI_FLOAT) * z1 + _EULER_MASCHERONI_FLOAT * z2)


def _compute_dsr_float(
    sr_ann: float,
    expected_max_sr_ann: float,
    observation_count: int,
    sessions_per_year: int,
    skewness: float,
    kurtosis: float,
) -> Tuple[float, float, float]:
    """
    Evaluates Deflated Sharpe Ratio test statistic and probability.
    Returns: (dsr_prob, z_score, p_value)
    """
    t = observation_count
    q = sessions_per_year
    sr_daily = sr_ann / math.sqrt(q)
    sr0_daily = expected_max_sr_ann / math.sqrt(q)

    # Mertens (2002) variance of Sharpe ratio under non-normality
    variance_term = 1.0 - skewness * sr_daily + ((kurtosis - 1.0) / 4.0) * (sr_daily ** 2)
    if variance_term <= 0.0:
        denom = 1e-6
    else:
        denom = math.sqrt(variance_term)

    numerator = (sr_daily - sr0_daily) * math.sqrt(t - 1)
    z = numerator / denom
    dsr = _normal_cdf(z)
    p_val = max(0.0, 1.0 - dsr)
    return dsr, z, p_val


def _compute_haircut_sharpe_float(
    sr_ann: float,
    observation_count: int,
    sessions_per_year: int,
    trial_count_n: int,
) -> Tuple[float, float, float, float, float]:
    """
    Evaluates Harvey & Liu (2015) Bonferroni Haircut Sharpe Ratio.
    Returns: (haircut_sr, haircut_pct, t_stat, p_val, p_adj)
    """
    t_years = observation_count / sessions_per_year
    if t_years <= 0:
        return 0.0, 100.0, 0.0, 1.0, 1.0

    t_stat = sr_ann * math.sqrt(t_years)
    abs_t = abs(t_stat)
    p_val = 2.0 * (1.0 - _normal_cdf(abs_t))
    p_adj = min(1.0, max(0.0, trial_count_n * p_val))

    if p_adj >= 1.0 or sr_ann <= 0.0:
        haircut_sr = 0.0
        haircut_pct = 100.0
    elif p_adj <= 0.0:
        # Statistically overwhelming significance; p-value underflows float
        haircut_sr = sr_ann
        haircut_pct = 0.0
    else:
        q_prob = 1.0 - p_adj / 2.0
        if q_prob >= 1.0:
            haircut_sr = sr_ann
            haircut_pct = 0.0
        else:
            q_prob = min(1.0 - 1e-15, q_prob)
            t_adj = _normal_quantile(q_prob)
            haircut_sr = (t_adj / math.sqrt(t_years)) * (1.0 if sr_ann >= 0.0 else -1.0)
            if sr_ann > 0.0:
                haircut_pct = max(0.0, min(100.0, (sr_ann - haircut_sr) / sr_ann * 100.0))
            else:
                haircut_pct = 100.0

    return haircut_sr, haircut_pct, t_stat, p_val, p_adj

# ==============================================================================
# End of SIG-FLOAT-BOUNDARY
# ==============================================================================


# ==============================================================================
# Public Statistical Significance Dataclasses & Calculators
# ==============================================================================

@dataclass(frozen=True, slots=True)
class DeflatedSharpeResult:
    """
    Immutable representation of Deflated Sharpe Ratio calculation per Bailey & Lopez de Prado (2014).
    Every instance is explicitly tagged with trial_count_n per auditor condition.
    """
    deflated_sharpe_ratio: Decimal      # DSR probability in [0.0, 1.0]
    expected_max_sharpe: Decimal        # SR* (expected maximum Sharpe ratio under H0)
    z_score: Decimal                    # z-score test statistic
    observed_annualized_sharpe: Decimal # Strategy annualized Sharpe ratio
    trial_count_n: int                  # Authoritative N used for multiple-testing penalty
    evaluated_trial_count: int          # N_eval used for variance estimation
    trial_sharpe_variance: Decimal      # Variance V of trial Sharpe ratios
    observation_count: int              # T (number of return observations)
    skewness: Decimal                   # gamma_3
    kurtosis: Decimal                   # gamma_4 (raw kurtosis, normal = 3)
    sessions_per_year: int              # Annualization factor q
    p_value: Decimal                    # 1 - DSR (tail probability under H0)


@dataclass(frozen=True, slots=True)
class HaircutSharpeResult:
    """
    Immutable representation of Haircut Sharpe Ratio calculation per Harvey & Liu (2015).
    Every instance is explicitly tagged with trial_count_n per auditor condition.
    """
    haircut_sharpe_ratio: Decimal       # Haircut Sharpe ratio
    haircut_percentage: Decimal         # Percentage haircut: (SR - SR_hc) / SR * 100
    original_annualized_sharpe: Decimal # Original annualized Sharpe ratio
    t_statistic: Decimal                # Strategy t-statistic
    original_p_value: Decimal           # Unadjusted two-tailed p-value
    adjusted_p_value: Decimal           # Multiple-testing adjusted p-value (Bonferroni: min(1.0, N * p))
    trial_count_n: int                  # Authoritative N used for haircut
    observation_count: int              # T (number of return observations)
    sessions_per_year: int              # Annualization factor q
    haircut_variant: str                # Methodology variant (e.g. "BONFERRONI")


@dataclass(frozen=True, slots=True)
class SignificanceReport:
    """
    Consolidated statistical significance report evaluated against committed Go/No-Go criteria.
    """
    strategy_id: str
    trial_count_n: int
    evaluated_trial_count: int
    observation_count: int
    annualized_sharpe: Decimal
    skewness: Decimal
    kurtosis: Decimal
    dsr_result: DeflatedSharpeResult
    haircut_result: HaircutSharpeResult
    criteria_version: str
    dsr_threshold: Decimal
    haircut_threshold: Decimal
    dsr_verdict: str                    # "PASS" or "FAIL" (computed)
    haircut_verdict: str                # "PASS" or "FAIL" (computed)
    overall_verdict: str                # "PASS" or "FAIL" (computed)


def compute_deflated_sharpe_ratio(
    annualized_sharpe: Decimal,
    trial_sharpe_variance: Decimal,
    observation_count: int,
    trial_count_n: int,
    sessions_per_year: int = 250,
    skewness: Decimal = Decimal("0.00"),
    kurtosis: Decimal = Decimal("3.00"),
    evaluated_trial_count: Optional[int] = None,
) -> DeflatedSharpeResult:
    """
    Computes the Deflated Sharpe Ratio (DSR) per Bailey & Lopez de Prado (2014).

    Inputs:
    - annualized_sharpe: Strategy annualized Sharpe ratio (Decimal).
    - trial_sharpe_variance: Sample variance V of trial Sharpe ratios (Decimal).
    - observation_count: Number of trading sessions T (int >= 2).
    - trial_count_n: Total attempted trials N (int >= 1).
    - sessions_per_year: Annualization factor (int >= 1, default 250).
    - skewness: Return series sample skewness gamma_3 (Decimal, default 0.00).
    - kurtosis: Return series sample raw kurtosis gamma_4 (Decimal, default 3.00 for normal).
    - evaluated_trial_count: Optional count of evaluated trials (int, defaults to trial_count_n).

    Returns:
    - DeflatedSharpeResult tagged with trial_count_n and exact Decimal metrics.
    """
    if isinstance(annualized_sharpe, bool) or not isinstance(annualized_sharpe, Decimal) or not annualized_sharpe.is_finite():
        raise SignificanceError(f"annualized_sharpe must be a finite Decimal, got {annualized_sharpe!r}")
    if isinstance(trial_sharpe_variance, bool) or not isinstance(trial_sharpe_variance, Decimal) or not trial_sharpe_variance.is_finite() or trial_sharpe_variance < 0:
        raise SignificanceError(f"trial_sharpe_variance must be a non-negative finite Decimal, got {trial_sharpe_variance!r}")
    if isinstance(observation_count, bool) or not isinstance(observation_count, int) or observation_count < 2:
        raise InvalidSampleError(f"observation_count must be an integer >= 2, got {observation_count!r}")
    if isinstance(trial_count_n, bool) or not isinstance(trial_count_n, int) or trial_count_n < 1:
        raise SignificanceError(f"trial_count_n must be an integer >= 1, got {trial_count_n!r}")
    if isinstance(sessions_per_year, bool) or not isinstance(sessions_per_year, int) or sessions_per_year < 1:
        raise SignificanceError(f"sessions_per_year must be an integer >= 1, got {sessions_per_year!r}")
    if isinstance(skewness, bool) or not isinstance(skewness, Decimal) or not skewness.is_finite():
        raise SignificanceError(f"skewness must be a finite Decimal, got {skewness!r}")
    if isinstance(kurtosis, bool) or not isinstance(kurtosis, Decimal) or not kurtosis.is_finite() or kurtosis <= 0:
        raise SignificanceError(f"kurtosis must be a positive finite Decimal, got {kurtosis!r}")

    n_eval = evaluated_trial_count if evaluated_trial_count is not None else trial_count_n
    if isinstance(n_eval, bool) or not isinstance(n_eval, int) or n_eval < 0:
        raise SignificanceError(f"evaluated_trial_count must be a non-negative integer, got {n_eval!r}")

    # Enter SIG-FLOAT-BOUNDARY
    sr_ann_fl = float(annualized_sharpe)
    var_ann_fl = float(trial_sharpe_variance)
    skew_fl = float(skewness)
    kurt_fl = float(kurtosis)

    sr0_fl = _compute_expected_max_sharpe_float(var_ann_fl, trial_count_n)
    dsr_fl, z_fl, p_val_fl = _compute_dsr_float(
        sr_ann=sr_ann_fl,
        expected_max_sr_ann=sr0_fl,
        observation_count=observation_count,
        sessions_per_year=sessions_per_year,
        skewness=skew_fl,
        kurtosis=kurt_fl,
    )
    # Exit SIG-FLOAT-BOUNDARY: Convert immediately to exact Decimal with standard precision

    return DeflatedSharpeResult(
        deflated_sharpe_ratio=Decimal(f"{dsr_fl:.6f}"),
        expected_max_sharpe=Decimal(f"{sr0_fl:.6f}"),
        z_score=Decimal(f"{z_fl:.6f}"),
        observed_annualized_sharpe=annualized_sharpe,
        trial_count_n=trial_count_n,
        evaluated_trial_count=n_eval,
        trial_sharpe_variance=trial_sharpe_variance,
        observation_count=observation_count,
        skewness=skewness,
        kurtosis=kurtosis,
        sessions_per_year=sessions_per_year,
        p_value=Decimal(f"{p_val_fl:.6f}"),
    )


def compute_haircut_sharpe_ratio(
    annualized_sharpe: Decimal,
    observation_count: int,
    trial_count_n: int,
    sessions_per_year: int = 250,
    haircut_variant: str = "BONFERRONI",
) -> HaircutSharpeResult:
    """
    Computes the Haircut Sharpe Ratio per Harvey & Liu (2015).

    Inputs:
    - annualized_sharpe: Strategy annualized Sharpe ratio (Decimal).
    - observation_count: Number of trading sessions T (int >= 2).
    - trial_count_n: Total attempted trials N (int >= 1).
    - sessions_per_year: Annualization factor (int >= 1, default 250).
    - haircut_variant: Methodology variant (default 'BONFERRONI').

    Returns:
    - HaircutSharpeResult tagged with trial_count_n and exact Decimal metrics.
    """
    if isinstance(annualized_sharpe, bool) or not isinstance(annualized_sharpe, Decimal) or not annualized_sharpe.is_finite():
        raise SignificanceError(f"annualized_sharpe must be a finite Decimal, got {annualized_sharpe!r}")
    if isinstance(observation_count, bool) or not isinstance(observation_count, int) or observation_count < 2:
        raise InvalidSampleError(f"observation_count must be an integer >= 2, got {observation_count!r}")
    if isinstance(trial_count_n, bool) or not isinstance(trial_count_n, int) or trial_count_n < 1:
        raise SignificanceError(f"trial_count_n must be an integer >= 1, got {trial_count_n!r}")
    if isinstance(sessions_per_year, bool) or not isinstance(sessions_per_year, int) or sessions_per_year < 1:
        raise SignificanceError(f"sessions_per_year must be an integer >= 1, got {sessions_per_year!r}")
    if haircut_variant != "BONFERRONI":
        raise SignificanceError(f"Unsupported haircut_variant '{haircut_variant}'. Currently supported: 'BONFERRONI'.")

    # Enter SIG-FLOAT-BOUNDARY
    sr_fl = float(annualized_sharpe)
    hc_sr_fl, hc_pct_fl, t_stat_fl, p_val_fl, p_adj_fl = _compute_haircut_sharpe_float(
        sr_ann=sr_fl,
        observation_count=observation_count,
        sessions_per_year=sessions_per_year,
        trial_count_n=trial_count_n,
    )
    # Exit SIG-FLOAT-BOUNDARY: Convert immediately to exact Decimal with standard precision

    return HaircutSharpeResult(
        haircut_sharpe_ratio=Decimal(f"{hc_sr_fl:.6f}"),
        haircut_percentage=Decimal(f"{hc_pct_fl:.4f}"),
        original_annualized_sharpe=annualized_sharpe,
        t_statistic=Decimal(f"{t_stat_fl:.6f}"),
        original_p_value=Decimal(f"{p_val_fl:.6f}"),
        adjusted_p_value=Decimal(f"{p_adj_fl:.6f}"),
        trial_count_n=trial_count_n,
        observation_count=observation_count,
        sessions_per_year=sessions_per_year,
        haircut_variant=haircut_variant,
    )


def evaluate_strategy_significance(
    returns: Sequence[Decimal],
    registry: TrialRegistry,
    criteria: GoNoGoCriteria,
    strategy_id: str = "STRATEGY_UNDER_TEST",
    risk_free_rate: Decimal = Decimal("0.00"),
) -> SignificanceReport:
    """
    Evaluates comprehensive strategy significance against Go/No-Go criteria and trial registry.

    Fulfills Auditor Conditions:
    1. Consumes total_trial_count as N and evaluated_trial_count for variance directly from registry.
    2. Uses methodology constants (sessions_per_year, kurtosis_convention, haircut_variant) from criteria.
    3. Tags every DSR and Haircut result with trial_count_n.
    4. Evaluates verdicts computed from boolean assertions, never typed.
    """
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise SignificanceError(f"strategy_id must be a non-empty string, got {strategy_id!r}")
    if not isinstance(registry, TrialRegistry):
        raise SignificanceError(f"registry must be a TrialRegistry instance, got {type(registry)}")
    if not isinstance(criteria, GoNoGoCriteria):
        raise SignificanceError(f"criteria must be a GoNoGoCriteria instance, got {type(criteria)}")

    clean_returns = _validate_decimal_sequence(returns, "returns", min_length=4)
    t_obs = len(clean_returns)

    # Resolve N per committed criteria convention (A-11 / Auditor Condition 1)
    if criteria.dsr_trial_count_basis == "TOTAL_ATTEMPTED_TRIALS":
        trial_count_n = max(1, registry.total_trial_count)
    elif criteria.dsr_trial_count_basis == "EVALUATED_TRIALS":
        trial_count_n = max(1, registry.evaluated_trial_count)
    else:
        raise SignificanceError(f"Unsupported dsr_trial_count_basis: {criteria.dsr_trial_count_basis!r}")

    # Resolve variance V per committed criteria convention
    if criteria.dsr_sharpe_variance_divisor == "EVALUATED_TRIALS_MINUS_ONE":
        trial_variance = registry.compute_trial_sharpe_variance()
    else:
        raise SignificanceError(f"Unsupported dsr_sharpe_variance_divisor: {criteria.dsr_sharpe_variance_divisor!r}")

    n_eval = registry.evaluated_trial_count
    q = criteria.sessions_per_year
    kurt_conv = criteria.kurtosis_convention
    hc_var = criteria.haircut_variant

    # Compute return moments
    skew = sample_skewness(clean_returns)
    kurt = sample_kurtosis(clean_returns, convention=kurt_conv)
    sr_ann = annualized_sharpe(clean_returns, sessions_per_year=q, risk_free_rate=risk_free_rate)

    # Compute DSR & Haircut Sharpe
    dsr_res = compute_deflated_sharpe_ratio(
        annualized_sharpe=sr_ann,
        trial_sharpe_variance=trial_variance,
        observation_count=t_obs,
        trial_count_n=trial_count_n,
        sessions_per_year=q,
        skewness=skew,
        kurtosis=kurt,
        evaluated_trial_count=n_eval,
    )

    hc_res = compute_haircut_sharpe_ratio(
        annualized_sharpe=sr_ann,
        observation_count=t_obs,
        trial_count_n=trial_count_n,
        sessions_per_year=q,
        haircut_variant=hc_var,
    )

    # Verdicts are computed programmatically per AGENTS.md Rule 9.1
    dsr_pass = dsr_res.deflated_sharpe_ratio >= criteria.min_deflated_sharpe_ratio
    hc_pass = hc_res.haircut_sharpe_ratio >= criteria.min_haircut_sharpe_ratio
    overall_pass = dsr_pass and hc_pass

    dsr_verdict = "PASS" if dsr_pass else "FAIL"
    hc_verdict = "PASS" if hc_pass else "FAIL"
    overall_verdict = "PASS" if overall_pass else "FAIL"

    return SignificanceReport(
        strategy_id=strategy_id,
        trial_count_n=trial_count_n,
        evaluated_trial_count=n_eval,
        observation_count=t_obs,
        annualized_sharpe=sr_ann,
        skewness=skew,
        kurtosis=kurt,
        dsr_result=dsr_res,
        haircut_result=hc_res,
        criteria_version=criteria.version,
        dsr_threshold=criteria.min_deflated_sharpe_ratio,
        haircut_threshold=criteria.min_haircut_sharpe_ratio,
        dsr_verdict=dsr_verdict,
        haircut_verdict=hc_verdict,
        overall_verdict=overall_verdict,
    )
