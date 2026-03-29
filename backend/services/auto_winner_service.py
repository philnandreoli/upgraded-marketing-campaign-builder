from __future__ import annotations

from typing import Optional

from backend.models.experiments import Experiment, StatMethod, VariantMetric
from backend.services.statistical_significance import bayesian_ab_test, chi_squared_test


def evaluate_auto_winner(experiment: Experiment, metrics: list[VariantMetric]) -> Optional[str]:
    """Return winning variant when experiment thresholds are met, else None."""
    if not experiment.config.auto_winner_enabled:
        return None
    if len(metrics) < 2:
        return None

    by_variant: dict[str, dict[str, int]] = {}
    for metric in metrics:
        bucket = by_variant.setdefault(metric.variant, {"impressions": 0, "conversions": 0})
        bucket["impressions"] += metric.impressions
        bucket["conversions"] += metric.conversions

    if len(by_variant) < 2:
        return None

    ranked = sorted(
        by_variant.items(),
        key=lambda kv: (kv[1]["conversions"] / kv[1]["impressions"]) if kv[1]["impressions"] > 0 else 0.0,
        reverse=True,
    )
    best_name, best = ranked[0]
    control_name, control = ranked[1]

    if (
        best["impressions"] < experiment.config.min_sample_size
        or control["impressions"] < experiment.config.min_sample_size
    ):
        return None

    if experiment.config.stat_method == StatMethod.FREQUENTIST:
        result = chi_squared_test(
            control_conversions=control["conversions"],
            control_impressions=control["impressions"],
            variant_conversions=best["conversions"],
            variant_impressions=best["impressions"],
        )
        if result["confidence"] >= experiment.config.confidence_threshold and result["significant"]:
            return best_name
        return None

    bayes = bayesian_ab_test(
        control_conversions=control["conversions"],
        control_impressions=control["impressions"],
        variant_conversions=best["conversions"],
        variant_impressions=best["impressions"],
    )
    if bayes["prob_b_beats_a"] >= experiment.config.confidence_threshold:
        return best_name
    return None
