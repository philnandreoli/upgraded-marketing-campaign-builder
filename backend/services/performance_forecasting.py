from __future__ import annotations

import math

from backend.models.experiments import VariantMetric

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


def forecast_performance(metrics: list[VariantMetric], days_ahead: int = 30) -> dict:
    """Forecast variant performance using posterior conversion rate estimates."""
    by_variant: dict[str, dict[str, float]] = {}
    for metric in metrics:
        bucket = by_variant.setdefault(
            metric.variant,
            {
                "impressions": 0.0,
                "conversions": 0.0,
                "revenue": 0.0,
                "records": 0.0,
            },
        )
        bucket["impressions"] += metric.impressions
        bucket["conversions"] += metric.conversions
        bucket["revenue"] += metric.revenue
        bucket["records"] += 1

    variants: list[dict] = []
    for name, agg in by_variant.items():
        alpha = agg["conversions"] + 1.0
        beta = max(agg["impressions"] - agg["conversions"], 0.0) + 1.0
        posterior_mean = alpha / (alpha + beta)

        if np is not None:
            samples = np.random.beta(alpha, beta, size=5000)
            low, high = np.percentile(samples, [5, 95])
            low_rate = float(low)
            high_rate = float(high)
        else:
            var = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
            std = math.sqrt(max(var, 0.0))
            low_rate = max(0.0, posterior_mean - 1.645 * std)
            high_rate = min(1.0, posterior_mean + 1.645 * std)

        avg_daily_impressions = agg["impressions"] / max(agg["records"], 1.0)
        projected_impressions = avg_daily_impressions * max(days_ahead, 0)
        avg_revenue_per_conversion = agg["revenue"] / agg["conversions"] if agg["conversions"] > 0 else 0.0

        projected_conversions = projected_impressions * posterior_mean
        projected_revenue = projected_conversions * avg_revenue_per_conversion
        variants.append(
            {
                "variant": name,
                "posterior_rate_mean": posterior_mean,
                "credible_interval_90": [low_rate, high_rate],
                "projected_impressions": int(projected_impressions),
                "projected_conversions": projected_conversions,
                "projected_revenue": projected_revenue,
            }
        )

    return {
        "days_ahead": days_ahead,
        "variants": sorted(variants, key=lambda v: v["posterior_rate_mean"], reverse=True),
    }
