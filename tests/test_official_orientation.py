"""Statistical contract tests for official_v1 orientation equivalence."""
from simulator.official_orientation import paired_equivalence_summary


def test_small_smoke_sample_is_diagnostic_only() -> None:
    result = paired_equivalence_summary(
        [0] * 200,
        maximum_difference=0.04,
        minimum_simulations=2000,
    )
    assert result["status"] == "diagnostic_only_insufficient_sample"
    assert result["release_eligible"] is False
    assert result["point_estimate_within_margin"] is True
    assert result["passed"] is False


def test_equivalent_large_paired_sample_passes() -> None:
    result = paired_equivalence_summary(
        [0] * 2000,
        maximum_difference=0.04,
        minimum_simulations=2000,
    )
    assert result["release_eligible"] is True
    assert result["confidence_interval_inside_margin"] is True
    assert result["passed"] is True


def test_large_but_non_equivalent_sample_fails() -> None:
    result = paired_equivalence_summary(
        [1] * 120 + [0] * 1880,
        maximum_difference=0.04,
        minimum_simulations=2000,
    )
    assert result["release_eligible"] is True
    assert result["signed_probability_difference"] > 0.04
    assert result["passed"] is False
