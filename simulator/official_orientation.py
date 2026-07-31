"""Paired equivalence diagnostics for home/away orientation in official_v1.

The smoke deployment may compute this diagnostic, but only a sample meeting the
preregistered minimum can authorize the release gate. Equivalence is assessed
with a two-sided 95% confidence interval for the paired difference in Synthetic
XI championship probability under swapped neutral orientations.
"""
from __future__ import annotations

from dataclasses import replace
from math import sqrt
from typing import Any, Iterable

import numpy as np

from .official_complete_final import (
    OFFICIAL_ENGINE_VERSION,
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
)
from .official_profiles import OfficialTeamBundle

NORMAL_95_Z = 1.959963984540054


def paired_equivalence_summary(
    paired_differences: Iterable[int | float],
    maximum_difference: float,
    minimum_simulations: int,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Evaluate equivalence from paired {-1, 0, 1} outcome differences.

    A release passes only when the entire confidence interval lies inside the
    preregistered equivalence region [-maximum_difference, +maximum_difference]
    and the minimum sample size has been reached.
    """
    values = np.asarray(list(paired_differences), dtype=float)
    if values.size < 2:
        raise ValueError("paired equivalence requires at least two paired observations")
    if maximum_difference <= 0:
        raise ValueError("maximum_difference must be positive")
    if minimum_simulations < 2:
        raise ValueError("minimum_simulations must be at least two")
    if abs(confidence_level - 0.95) > 1e-12:
        raise ValueError("official_v1 currently freezes a 95% confidence level")

    estimate = float(values.mean())
    standard_error = float(values.std(ddof=1) / sqrt(values.size))
    lower = float(estimate - NORMAL_95_Z * standard_error)
    upper = float(estimate + NORMAL_95_Z * standard_error)
    release_eligible = bool(values.size >= minimum_simulations)
    interval_inside_margin = bool(
        lower >= -maximum_difference and upper <= maximum_difference
    )
    passed = bool(release_eligible and interval_inside_margin)

    if not release_eligible:
        status = "diagnostic_only_insufficient_sample"
    elif passed:
        status = "paired_equivalence_passed"
    else:
        status = "paired_equivalence_failed"

    return {
        "status": status,
        "method": "paired_difference_normal_95ci_equivalence",
        "confidence_level": float(confidence_level),
        "paired_observations": int(values.size),
        "minimum_required_observations": int(minimum_simulations),
        "release_eligible": release_eligible,
        "signed_probability_difference": estimate,
        "absolute_probability_difference": abs(estimate),
        "paired_standard_error": standard_error,
        "confidence_interval": {"low": lower, "high": upper},
        "equivalence_region": {
            "low": -float(maximum_difference),
            "high": float(maximum_difference),
        },
        "point_estimate_within_margin": bool(abs(estimate) <= maximum_difference),
        "confidence_interval_inside_margin": interval_inside_margin,
        "passed": passed,
    }


def paired_orientation_diagnostic(
    synthetic: OfficialTeamBundle,
    real: OfficialTeamBundle,
    targets: Any,
    simulations: int,
    seed: int,
    maximum_difference: float,
    config: OfficialFinalConfig | None = None,
    minimum_simulations: int = 2000,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Run neutral paired home/away simulations and test statistical equivalence."""
    if simulations < 20:
        raise ValueError("paired orientation diagnostic requires at least 20 simulations")

    base = replace(config or OfficialFinalConfig(), home_advantage=0.0)
    rng = np.random.default_rng(seed)
    synthetic_wins_home = 0
    synthetic_wins_away = 0
    paired_differences: list[int] = []

    for _ in range(simulations):
        match_seed = int(rng.integers(0, 2**32 - 1))
        first = OfficialCompleteFinalSimulator(
            synthetic,
            real,
            targets,
            replace(base, seed=match_seed),
        ).simulate(keep_timeline=False)
        second = OfficialCompleteFinalSimulator(
            real,
            synthetic,
            targets,
            replace(
                base,
                seed=match_seed,
                home_coordination_mean=base.away_coordination_mean,
                away_coordination_mean=base.home_coordination_mean,
            ),
        ).simulate(keep_timeline=False)
        first_win = int(first.winner == synthetic.team.name)
        second_win = int(second.winner == synthetic.team.name)
        synthetic_wins_home += first_win
        synthetic_wins_away += second_win
        paired_differences.append(first_win - second_win)

    summary = paired_equivalence_summary(
        paired_differences,
        maximum_difference=maximum_difference,
        minimum_simulations=minimum_simulations,
        confidence_level=confidence_level,
    )
    summary.update(
        {
            "engine_version": OFFICIAL_ENGINE_VERSION,
            "simulations_per_orientation": int(simulations),
            "common_random_numbers": True,
            "synthetic_probability_as_home": synthetic_wins_home / simulations,
            "synthetic_probability_as_away": synthetic_wins_away / simulations,
        }
    )
    return summary
