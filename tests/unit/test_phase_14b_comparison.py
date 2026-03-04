"""Tests for Phase 14b: A/B statistical comparison."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.tools.comparison import (
    ComparisonConfig,
    ComparisonResult,
    MetricComparison,
    compare_distributions,
    format_comparison,
)


# ---------------------------------------------------------------------------
# compare_distributions tests
# ---------------------------------------------------------------------------


class TestCompareDistributions:
    """Statistical comparison via Mann-Whitney U."""

    def test_identical_distributions_high_p(self) -> None:
        """Same values should give p > 0.05."""
        rng = np.random.default_rng(42)
        values = rng.normal(5.0, 1.0, 30).tolist()
        mc = compare_distributions(values, values, "test_metric")
        assert mc.p_value > 0.05
        assert not mc.significant

    def test_different_distributions_low_p(self) -> None:
        """Clearly different distributions should give p < 0.05."""
        rng = np.random.default_rng(42)
        a = rng.normal(5.0, 0.5, 50).tolist()
        b = rng.normal(10.0, 0.5, 50).tolist()
        mc = compare_distributions(a, b, "test_metric")
        assert mc.p_value < 0.05
        assert mc.significant

    def test_effect_size_direction(self) -> None:
        """Effect size should be nonzero for different distributions."""
        rng = np.random.default_rng(42)
        a = rng.normal(2.0, 0.3, 40).tolist()
        b = rng.normal(8.0, 0.3, 40).tolist()
        mc = compare_distributions(a, b, "metric")
        assert abs(mc.effect_size) > 0.5

    def test_small_sample_graceful(self) -> None:
        """Single-element samples should not crash."""
        mc = compare_distributions([5.0], [10.0], "metric")
        assert mc.p_value == 1.0
        assert not mc.significant

    def test_empty_sample_graceful(self) -> None:
        """Empty samples should not crash."""
        mc = compare_distributions([], [], "metric")
        assert mc.p_value == 1.0

    def test_mean_std_correct(self) -> None:
        mc = compare_distributions([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], "metric")
        assert abs(mc.mean_a - 2.0) < 1e-10
        assert abs(mc.mean_b - 5.0) < 1e-10
        assert mc.std_a > 0
        assert mc.std_b > 0

    def test_metric_name_preserved(self) -> None:
        mc = compare_distributions([1.0, 2.0], [1.0, 2.0], "exchange_ratio")
        assert mc.metric == "exchange_ratio"

    def test_identical_values_no_crash(self) -> None:
        """All identical values should not crash mannwhitneyu."""
        mc = compare_distributions([5.0, 5.0, 5.0], [5.0, 5.0, 5.0], "metric")
        assert mc.p_value >= 0.0  # should handle gracefully

    def test_alpha_threshold(self) -> None:
        """Custom alpha should affect significance."""
        rng = np.random.default_rng(42)
        a = rng.normal(5.0, 1.0, 20).tolist()
        b = rng.normal(5.5, 1.0, 20).tolist()
        mc_strict = compare_distributions(a, b, "metric", alpha=0.01)
        mc_loose = compare_distributions(a, b, "metric", alpha=0.5)
        # The loose threshold is more likely to find significance
        if mc_strict.significant:
            assert mc_loose.significant  # strict implies loose


# ---------------------------------------------------------------------------
# ComparisonResult / format tests
# ---------------------------------------------------------------------------


class TestFormatComparison:
    """Formatting of comparison results."""

    def test_format_output(self) -> None:
        result = ComparisonResult(
            label_a="Config A",
            label_b="Config B",
            num_iterations=20,
            metrics=[
                MetricComparison(
                    metric="exchange_ratio",
                    mean_a=2.5, std_a=0.8,
                    mean_b=3.1, std_b=0.9,
                    u_statistic=150.0, p_value=0.03,
                    significant=True, effect_size=0.25,
                ),
            ],
        )
        text = format_comparison(result)
        assert "Config A" in text
        assert "Config B" in text
        assert "exchange_ratio" in text
        assert "*" in text  # significant marker
