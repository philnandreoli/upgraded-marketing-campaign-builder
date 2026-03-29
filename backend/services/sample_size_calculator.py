from __future__ import annotations

import math
from statistics import NormalDist


def calculate_sample_size(
    baseline_rate: float,
    mde: float,
    confidence_level: float = 0.95,
    power: float = 0.80,
    daily_traffic: int = 0,
) -> dict:
    """Estimate two-variant sample size for conversion-rate experiments.

    Input values are clamped to valid ranges:
    - baseline_rate is clamped to (0, 1) exclusive to avoid log-domain errors
      in the normal-distribution calculations.
    - mde is clamped to a small positive value to avoid zero-division when
      computing the absolute effect size delta = |p2 - p1|.
    """
    p1 = min(max(baseline_rate, 1e-6), 1 - 1e-6)
    uplift = max(mde, 1e-6)
    p2 = min(max(p1 * (1.0 + uplift), 1e-6), 1 - 1e-6)
    delta = abs(p2 - p1)

    z_alpha = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    z_beta = NormalDist().inv_cdf(power)

    pooled = (p1 + p2) / 2
    numerator = (z_alpha * math.sqrt(2 * pooled * (1 - pooled)) + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    n_per_variant = math.ceil(numerator / max(delta ** 2, 1e-12))
    total_sample_size = n_per_variant * 2

    estimated_days = None
    if daily_traffic > 0:
        estimated_days = math.ceil(total_sample_size / daily_traffic)

    return {
        "sample_size_per_variant": int(n_per_variant),
        "total_sample_size": int(total_sample_size),
        "estimated_days": estimated_days,
    }
