"""Tests for strict paired production comparison."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.tools.comparison import (
    ComparisonConfig,
    ComparisonResult,
    MetricComparison,
    _apply_holm,
    _holm_order_indices,
    compare_distributions,
    format_comparison,
)


# ---------------------------------------------------------------------------
# compare_distributions tests
# ---------------------------------------------------------------------------


class TestCompareDistributions:
    """Statistical comparison via the exact paired sign test."""

    def test_identical_distributions_high_p(self) -> None:
        """Same values should give p > 0.05."""
        rng = np.random.default_rng(42)
        values = rng.normal(5.0, 1.0, 30).tolist()
        mc = compare_distributions(values, values, "test_metric")
        assert mc.p_value > 0.05
        assert not mc.significant

    def test_different_distributions_low_p(self) -> None:
        """Clearly different distributions should give p < 0.05."""
        a = [float(index) for index in range(10)]
        b = [value + 1.0 for value in a]
        mc = compare_distributions(a, b, "test_metric")
        assert mc.raw_p_value < 0.05
        assert mc.positive == 10
        assert mc.negative == 0
        assert mc.tied == 0

    def test_paired_direction_and_superiority(self) -> None:
        """Direction and ties are exposed without an unpaired effect size."""
        a = [1.0, 2.0, 3.0, 4.0]
        b = [2.0, 1.0, 3.0, 5.0]
        mc = compare_distributions(a, b, "metric")
        assert (mc.positive, mc.negative, mc.tied) == (2, 1, 1)
        assert mc.n_nonzero == 3
        assert mc.paired_superiority == pytest.approx(0.625)
        assert mc.mean_paired_difference == pytest.approx(0.25)

    @pytest.mark.parametrize(
        (
            "differences",
            "expected_positive",
            "expected_negative",
            "expected_tied",
            "expected_p_value",
        ),
        [
            ([1.0] * 6 + [0.0] * 2, 6, 0, 2, 0.03125),
            ([-1.0] * 6 + [0.0] * 2, 0, 6, 2, 0.03125),
            ([1.0] * 5 + [-1.0] + [0.0] * 2, 5, 1, 2, 0.21875),
            ([1.0] * 3 + [-1.0] * 3 + [0.0] * 2, 3, 3, 2, 1.0),
            ([0.0] * 8, 0, 0, 8, 1.0),
        ],
        ids=[
            "positive-tail",
            "negative-tail",
            "mixed-signs",
            "balanced-signs",
            "all-tied",
        ],
    )
    def test_exact_dixon_mood_sign_counts_and_p_values(
        self,
        differences: list[float],
        expected_positive: int,
        expected_negative: int,
        expected_tied: int,
        expected_p_value: float,
    ) -> None:
        """The paired sign test drops ties and uses the exact binomial tail."""
        baseline = [0.0] * len(differences)

        comparison = compare_distributions(
            baseline,
            differences,
            "metric",
        )

        assert comparison.n_total == len(differences)
        assert comparison.n_nonzero == (
            expected_positive + expected_negative
        )
        assert comparison.positive == expected_positive
        assert comparison.negative == expected_negative
        assert comparison.tied == expected_tied
        assert comparison.raw_p_value == expected_p_value
        assert comparison.holm_adjusted_p_value == expected_p_value

    def test_small_sample_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            compare_distributions([5.0], [10.0], "metric")

    def test_empty_sample_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            compare_distributions([], [], "metric")

    def test_unequal_pairs_rejected(self) -> None:
        with pytest.raises(ValueError, match="equal length"):
            compare_distributions([1.0, 2.0], [1.0, 2.0, 3.0], "metric")

    @pytest.mark.parametrize(
        ("values_a", "values_b"),
        [
            ([True, 2.0], [1.0, 2.0]),
            ([1.0, 2.0], [False, 2.0]),
            (["1.0", 2.0], [1.0, 2.0]),
            ([1.0, 2.0], ["1.0", 2.0]),
            ([float("nan"), 2.0], [1.0, 2.0]),
            ([1.0, 2.0], [float("inf"), 2.0]),
        ],
    )
    def test_malformed_vector_values_rejected(
        self,
        values_a: list[float],
        values_b: list[float],
    ) -> None:
        with pytest.raises(ValueError, match="strict|finite"):
            compare_distributions(values_a, values_b, "metric")

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
        """All ties are a declared exact-sign-test outcome."""
        mc = compare_distributions([5.0, 5.0, 5.0], [5.0, 5.0, 5.0], "metric")
        assert mc.raw_p_value == 1.0
        assert mc.n_nonzero == 0
        assert mc.tied == 3

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

    def test_holm_exact_adjustments_are_monotone_and_ties_keep_index_order(
        self,
    ) -> None:
        comparisons = [
            compare_distributions(
                [0.0] * 6,
                [1.0] * 6,
                "tie_first",
                alpha=0.2,
            ),
            compare_distributions(
                [0.0] * 6,
                [1.0] * 5 + [-1.0],
                "later_raw_p",
                alpha=0.2,
            ),
            compare_distributions(
                [0.0] * 6,
                [-1.0] * 6,
                "tie_second",
                alpha=0.2,
            ),
            compare_distributions(
                [0.0] * 5,
                [1.0] * 5,
                "middle_raw_p",
                alpha=0.2,
            ),
            compare_distributions(
                [0.0] * 6,
                [0.0] * 6,
                "all_tied",
                alpha=0.2,
            ),
        ]
        adjusted = _apply_holm(comparisons, alpha=0.2)

        assert [item.metric for item in adjusted] == [
            "tie_first",
            "later_raw_p",
            "tie_second",
            "middle_raw_p",
            "all_tied",
        ]
        assert [item.raw_p_value for item in adjusted] == [
            0.03125,
            0.21875,
            0.03125,
            0.0625,
            1.0,
        ]
        assert [item.holm_adjusted_p_value for item in adjusted] == [
            0.15625,
            0.4375,
            0.15625,
            0.1875,
            1.0,
        ]
        ordered_indexes = _holm_order_indices(comparisons)
        assert ordered_indexes == (0, 2, 3, 1, 4)
        assert [
            adjusted[index].metric
            for index in ordered_indexes
        ] == [
            "tie_first",
            "tie_second",
            "middle_raw_p",
            "later_raw_p",
            "all_tied",
        ]
        monotone_adjusted = [
            adjusted[index].holm_adjusted_p_value
            for index in ordered_indexes
        ]
        assert monotone_adjusted == [
            0.15625,
            0.15625,
            0.1875,
            0.4375,
            1.0,
        ]
        assert [item.family_wise_significant for item in adjusted] == [
            True,
            False,
            True,
            True,
            False,
        ]


class TestComparisonConfig:
    def test_rejects_one_iteration_and_nonfinite_alpha(self) -> None:
        with pytest.raises(ValueError):
            ComparisonConfig(scenario_path="scenario.yaml", num_iterations=1)
        with pytest.raises(ValueError):
            ComparisonConfig(scenario_path="scenario.yaml", alpha=float("nan"))


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
                    n_total=20,
                    n_nonzero=17,
                    positive=14,
                    negative=3,
                    tied=3,
                    mean_paired_difference=0.6,
                    median_paired_difference=0.5,
                    paired_superiority=0.775,
                    raw_p_value=0.03,
                    holm_adjusted_p_value=0.03,
                    alpha=0.05,
                    family_wise_significant=True,
                ),
            ],
        )
        text = format_comparison(result)
        assert "Config A" in text
        assert "Config B" in text
        assert "exchange_ratio" in text
        assert "*" in text  # significant marker
        assert "Holm" in text
