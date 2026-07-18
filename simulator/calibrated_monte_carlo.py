"""Monte Carlo aggregation for the calibrated match engine."""

from __future__ import annotations

from typing import Any

import numpy as np

from .calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibratedResult,
    CalibrationTargets,
)
from .engine import TeamProfile


def simulate_many_calibrated(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    simulations: int = 10_000,
    seed: int = 20260718,
    config: CalibratedConfig | None = None,
) -> dict[str, Any]:
    if simulations < 1:
        raise ValueError("simulations must be positive")

    rng = np.random.default_rng(seed)
    base = config or CalibratedConfig()
    home_wins = draws = away_wins = 0
    home_goals: list[int] = []
    away_goals: list[int] = []
    home_shots: list[int] = []
    away_shots: list[int] = []
    home_shots_on: list[int] = []
    away_shots_on: list[int] = []
    home_xg: list[float] = []
    away_xg: list[float] = []
    scorelines: dict[str, int] = {}

    for _ in range(simulations):
        result = _simulate_once(home, away, targets, base, rng, False)
        home_goals.append(result.home_goals)
        away_goals.append(result.away_goals)
        home_shots.append(result.home_shots)
        away_shots.append(result.away_shots)
        home_shots_on.append(result.home_shots_on_target)
        away_shots_on.append(result.away_shots_on_target)
        home_xg.append(result.home_xg)
        away_xg.append(result.away_xg)

        if result.home_goals > result.away_goals:
            home_wins += 1
        elif result.home_goals == result.away_goals:
            draws += 1
        else:
            away_wins += 1
        score = f"{result.home_goals}-{result.away_goals}"
        scorelines[score] = scorelines.get(score, 0) + 1

    mean_home_goals = float(np.mean(home_goals))
    mean_away_goals = float(np.mean(away_goals))
    mean_total_shots = float(np.mean(home_shots) + np.mean(away_shots))
    representative = _representative_match(
        home,
        away,
        targets,
        base,
        rng,
        mean_home_goals,
        mean_away_goals,
        mean_total_shots,
    )

    mean_total_goals = mean_home_goals + mean_away_goals
    mean_total_shots_on = float(
        np.mean(home_shots_on) + np.mean(away_shots_on)
    )
    zero_zero_probability = scorelines.get("0-0", 0) / simulations
    top_scorelines = sorted(
        scorelines.items(), key=lambda item: (-item[1], item[0])
    )[:10]

    return {
        "status": "calibrated_exploratory_simulation_completed",
        "simulations": simulations,
        "home": home.name,
        "away": away.name,
        "home_win_probability": home_wins / simulations,
        "draw_probability": draws / simulations,
        "away_win_probability": away_wins / simulations,
        "mean_home_goals": mean_home_goals,
        "mean_away_goals": mean_away_goals,
        "mean_total_goals": mean_total_goals,
        "mean_home_xg": float(np.mean(home_xg)),
        "mean_away_xg": float(np.mean(away_xg)),
        "mean_total_shots": mean_total_shots,
        "mean_total_shots_on_target": mean_total_shots_on,
        "zero_zero_probability": zero_zero_probability,
        "top_scorelines": [
            {"score": score, "probability": count / simulations}
            for score, count in top_scorelines
        ],
        "calibration_targets": targets.__dict__,
        "calibration_error": {
            "goals_per_match": mean_total_goals - targets.mean_goals_per_match,
            "shots_per_match": mean_total_shots - targets.mean_shots_per_match,
            "shots_on_target_per_match": (
                mean_total_shots_on
                - targets.mean_shots_on_target_per_match
            ),
            "zero_zero_rate": zero_zero_probability - targets.zero_zero_rate,
        },
        "representative_match": representative.as_dict(),
        "methodological_gate": {
            "publication_as_final_result_allowed": False,
            "reason": (
                "The engine is calibrated, but annual coverage and definitive "
                "eleven-role resolution remain incomplete."
            ),
        },
    }


def _simulate_once(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    base: CalibratedConfig,
    rng: np.random.Generator,
    keep_timeline: bool,
) -> CalibratedResult:
    seed = int(rng.integers(0, 2**32 - 1))
    config = CalibratedConfig(**{**base.__dict__, "seed": seed})
    return CalibratedMatchSimulator(home, away, targets, config).simulate(
        keep_timeline=keep_timeline
    )


def _representative_match(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    base: CalibratedConfig,
    rng: np.random.Generator,
    mean_home_goals: float,
    mean_away_goals: float,
    mean_total_shots: float,
) -> CalibratedResult:
    representative: CalibratedResult | None = None
    closest = float("inf")
    for _ in range(250):
        result = _simulate_once(home, away, targets, base, rng, True)
        distance = (
            abs(result.home_goals - mean_home_goals)
            + abs(result.away_goals - mean_away_goals)
            + 0.15
            * abs(
                result.home_shots
                + result.away_shots
                - mean_total_shots
            )
        )
        if distance < closest:
            closest = distance
            representative = result
    if representative is None:
        raise RuntimeError("Representative match was not generated")
    return representative
