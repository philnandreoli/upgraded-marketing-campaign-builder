from __future__ import annotations

import math
from random import betavariate

try:
    from scipy.stats import chi2_contingency  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    chi2_contingency = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


def _safe_rate(conversions: int, impressions: int) -> float:
    if impressions <= 0:
        return 0.0
    return conversions / impressions


def chi_squared_test(
    control_conversions: int,
    control_impressions: int,
    variant_conversions: int,
    variant_impressions: int,
) -> dict:
    """Run a frequentist significance test for 2-proportion conversion data."""
    control_failures = max(control_impressions - control_conversions, 0)
    variant_failures = max(variant_impressions - variant_conversions, 0)
    contingency = [
        [control_conversions, control_failures],
        [variant_conversions, variant_failures],
    ]

    if chi2_contingency is not None:
        _chi2, p_value, _dof, _expected = chi2_contingency(contingency, correction=False)
    else:
        # Manual 2x2 chi-square test fallback (df=1)
        total = sum(sum(row) for row in contingency)
        if total <= 0:
            p_value = 1.0
        else:
            row_sums = [sum(r) for r in contingency]
            col_sums = [contingency[0][0] + contingency[1][0], contingency[0][1] + contingency[1][1]]
            chi2 = 0.0
            for i in range(2):
                for j in range(2):
                    expected = (row_sums[i] * col_sums[j]) / total if total else 0.0
                    if expected > 0:
                        chi2 += ((contingency[i][j] - expected) ** 2) / expected
            # df=1 => survival function = erfc(sqrt(x/2))
            p_value = math.erfc(math.sqrt(max(chi2, 0.0) / 2.0))

    confidence = 1.0 - float(p_value)
    return {
        "p_value": float(p_value),
        "confidence": confidence,
        "significant": bool(p_value < 0.05),
        "control_rate": _safe_rate(control_conversions, control_impressions),
        "variant_rate": _safe_rate(variant_conversions, variant_impressions),
    }


def bayesian_ab_test(
    control_conversions: int,
    control_impressions: int,
    variant_conversions: int,
    variant_impressions: int,
    num_samples: int = 10000,
) -> dict:
    """Bayesian A/B test using beta-binomial posteriors."""
    a_alpha = control_conversions + 1
    a_beta = max(control_impressions - control_conversions, 0) + 1
    b_alpha = variant_conversions + 1
    b_beta = max(variant_impressions - variant_conversions, 0) + 1

    if np is not None:
        a_samples = np.random.beta(a_alpha, a_beta, size=num_samples)
        b_samples = np.random.beta(b_alpha, b_beta, size=num_samples)
        prob_b_beats_a = float(np.mean(b_samples > a_samples))
        expected_loss = float(np.mean(np.maximum(a_samples - b_samples, 0.0)))
    else:
        wins = 0
        losses: list[float] = []
        for _ in range(num_samples):
            a = betavariate(a_alpha, a_beta)
            b = betavariate(b_alpha, b_beta)
            if b > a:
                wins += 1
            losses.append(max(a - b, 0.0))
        prob_b_beats_a = wins / max(num_samples, 1)
        expected_loss = sum(losses) / max(len(losses), 1)

    return {
        "prob_b_beats_a": prob_b_beats_a,
        "expected_loss": expected_loss,
    }


def calculate_lift(control_rate: float, variant_rate: float) -> float:
    """Calculate relative lift from control to variant."""
    if control_rate <= 0:
        return 0.0
    return (variant_rate - control_rate) / control_rate
