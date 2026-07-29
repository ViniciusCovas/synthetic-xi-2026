"""Monte Carlo aggregation and diagnostics for complete knockout finals."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from math import sqrt
from typing import Any

import numpy as np

from .calibrated_core import CalibrationTargets
from .complete_final import CompleteFinalResult, CompleteFinalSimulator, FinalConfig
from .engine import TeamProfile


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float]:
    if total <= 0:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0}
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
        / denominator
    )
    return {
        "estimate": p,
        "low": max(0.0, centre - margin),
        "high": min(1.0, centre + margin),
    }


def simulate_complete_finals(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    simulations: int = 10_000,
    seed: int = 20260721,
    config: FinalConfig | None = None,
    audit_sample_size: int = 250,
) -> dict[str, Any]:
    if simulations < 1:
        raise ValueError("simulations must be positive")
    rng = np.random.default_rng(seed)
    base = config or FinalConfig()
    rows: list[dict[str, Any]] = []
    match_seeds: list[int] = []

    for simulation_id in range(simulations):
        match_seed = int(rng.integers(0, 2**32 - 1))
        match_seeds.append(match_seed)
        result = CompleteFinalSimulator(
            home,
            away,
            targets,
            replace(base, seed=match_seed),
        ).simulate(keep_timeline=False)
        rows.append(_compact_row(simulation_id, match_seed, result))

    home_wins = sum(row["winner"] == home.name for row in rows)
    away_wins = simulations - home_wins
    extra_time = sum(row["decided_by"] in {"extra_time", "penalties"} for row in rows)
    penalties = sum(row["decided_by"] == "penalties" for row in rows)
    regulation_draws = sum(row["regulation_draw"] for row in rows)

    representative_row = _representative_row(rows)
    representative = CompleteFinalSimulator(
        home,
        away,
        targets,
        replace(base, seed=int(representative_row["match_seed"])),
    ).simulate(keep_timeline=True)

    mean_regulation_goals = float(
        np.mean([row["regulation_total_goals"] for row in rows])
    )
    mean_regulation_shots = float(
        np.mean([row["total_shots"] for row in rows])
    )
    mean_regulation_shots_on = float(
        np.mean([row["total_shots_on_target"] for row in rows])
    )
    zero_zero_rate = float(
        np.mean(
            [
                row["regulation_home_goals"] == 0
                and row["regulation_away_goals"] == 0
                for row in rows
            ]
        )
    )
    seed_hash = hashlib.sha256(
        ",".join(str(value) for value in match_seeds).encode("utf-8")
    ).hexdigest()

    summary = {
        "status": "complete_final_monte_carlo_completed",
        "version": "complete_final_v1",
        "simulations": simulations,
        "master_seed": seed,
        "match_seed_ledger_sha256": seed_hash,
        "home": home.name,
        "away": away.name,
        "home_champion_probability": _wilson(home_wins, simulations),
        "away_champion_probability": _wilson(away_wins, simulations),
        "regulation_draw_probability": _wilson(regulation_draws, simulations),
        "extra_time_probability": _wilson(extra_time, simulations),
        "penalty_shootout_probability": _wilson(penalties, simulations),
        "mean_regulation_goals": mean_regulation_goals,
        "mean_regulation_shots": mean_regulation_shots,
        "mean_regulation_shots_on_target": mean_regulation_shots_on,
        "regulation_zero_zero_rate": zero_zero_rate,
        "mean_total_fouls": float(np.mean([row["total_fouls"] for row in rows])),
        # COMPLETE_FINAL_YELLOW_CARD_MEASUREMENT_V1
        "mean_total_yellows": float(np.mean([row["total_yellows"] for row in rows])),
        "mean_total_yellows_raw": float(np.mean([row["total_yellows_raw"] for row in rows])),
        "mean_total_second_yellows": float(np.mean([row["total_second_yellows"] for row in rows])),
        "mean_total_reds": float(np.mean([row["total_reds"] for row in rows])),
        "mean_total_injuries": float(np.mean([row["total_injuries"] for row in rows])),
        "mean_total_substitutions": float(
            np.mean([row["total_substitutions"] for row in rows])
        ),
        "calibration_targets": targets.__dict__,
        "regulation_calibration_error": {
            "goals_per_match": mean_regulation_goals - targets.mean_goals_per_match,
            "shots_per_match": mean_regulation_shots - targets.mean_shots_per_match,
            "shots_on_target_per_match": (
                mean_regulation_shots_on - targets.mean_shots_on_target_per_match
            ),
            "zero_zero_rate": zero_zero_rate - targets.zero_zero_rate,
        },
        "representative_match_selection": {
            "rule": (
                "Minimum standardized distance to Monte Carlo medians across "
                "regulation goals, shots, fouls, cards and decision stage."
            ),
            "simulation_id": int(representative_row["simulation_id"]),
            "match_seed": int(representative_row["match_seed"]),
        },
        "representative_match": representative.as_dict(),
        "audit_sample": rows[: min(audit_sample_size, simulations)],
    }
    summary["engineering_calibration_gate"] = calibration_gate(summary)
    return summary


def calibration_gate(summary: dict[str, Any]) -> dict[str, Any]:
    errors = summary["regulation_calibration_error"]
    checks = {
        "absolute_goal_error_le_0_45": abs(errors["goals_per_match"]) <= 0.45,
        "absolute_shot_error_le_3": abs(errors["shots_per_match"]) <= 3.0,
        "absolute_shot_on_target_error_le_1_5": (
            abs(errors["shots_on_target_per_match"]) <= 1.5
        ),
        "absolute_zero_zero_error_le_0_06": abs(errors["zero_zero_rate"]) <= 0.06,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "scope": (
            "Engineering distribution gate for regulation-time observables. "
            "It does not by itself authorize substantive publication claims."
        ),
    }


def paired_swap_diagnostic(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    simulations: int = 2_000,
    seed: int = 20260722,
    config: FinalConfig | None = None,
) -> dict[str, Any]:
    if simulations < 20:
        raise ValueError("paired swap diagnostic requires at least 20 simulations")
    base = config or FinalConfig()
    base = replace(base, home_advantage=0.0)
    rng = np.random.default_rng(seed)
    home_wins_original = 0
    home_entity_wins_when_away = 0

    for _ in range(simulations):
        match_seed = int(rng.integers(0, 2**32 - 1))
        original = CompleteFinalSimulator(
            home,
            away,
            targets,
            replace(base, seed=match_seed),
        ).simulate(keep_timeline=False)
        swapped = CompleteFinalSimulator(
            away,
            home,
            targets,
            replace(
                base,
                seed=match_seed,
                home_coordination_mean=base.away_coordination_mean,
                away_coordination_mean=base.home_coordination_mean,
            ),
        ).simulate(keep_timeline=False)
        home_wins_original += int(original.winner == home.name)
        home_entity_wins_when_away += int(swapped.winner == home.name)

    first = home_wins_original / simulations
    second = home_entity_wins_when_away / simulations
    difference = first - second
    return {
        "simulations_per_orientation": simulations,
        "neutral_home_entity_probability_original_orientation": first,
        "neutral_home_entity_probability_swapped_orientation": second,
        "absolute_orientation_difference": abs(difference),
        "passed": abs(difference) <= 0.055,
        "threshold": 0.055,
    }


def _compact_row(
    simulation_id: int,
    match_seed: int,
    result: CompleteFinalResult,
) -> dict[str, Any]:
    home_stats = result.home_stats
    away_stats = result.away_stats
    return {
        "simulation_id": simulation_id,
        "match_seed": match_seed,
        "winner": result.winner,
        "decided_by": result.decided_by,
        "regulation_home_goals": result.regulation_home_goals,
        "regulation_away_goals": result.regulation_away_goals,
        "regulation_total_goals": (
            result.regulation_home_goals + result.regulation_away_goals
        ),
        "regulation_draw": (
            result.regulation_home_goals == result.regulation_away_goals
        ),
        "extra_time_home_goals": result.extra_time_home_goals,
        "extra_time_away_goals": result.extra_time_away_goals,
        "home_penalties": result.home_penalties,
        "away_penalties": result.away_penalties,
        "total_shots": (
            home_stats["regulation_shots"] + away_stats["regulation_shots"]
        ),
        "total_shots_on_target": (
            home_stats["regulation_shots_on_target"]
            + away_stats["regulation_shots_on_target"]
        ),
        "total_fouls": home_stats["fouls"] + away_stats["fouls"],
        "total_yellows": (
            home_stats.get("benchmark_comparable_yellows", home_stats["yellows"])
            + away_stats.get("benchmark_comparable_yellows", away_stats["yellows"])
        ),
        "total_yellows_raw": home_stats["yellows"] + away_stats["yellows"],
        "total_second_yellows": (
            home_stats.get("second_yellows", 0) + away_stats.get("second_yellows", 0)
        ),
        "total_reds": home_stats["reds"] + away_stats["reds"],
        "total_injuries": home_stats["injuries"] + away_stats["injuries"],
        "total_substitutions": (
            home_stats["substitutions"] + away_stats["substitutions"]
        ),
    }


def _representative_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_keys = (
        "regulation_total_goals",
        "total_shots",
        "total_fouls",
        "total_yellows",
        "total_reds",
        "total_injuries",
        "total_substitutions",
    )
    medians = {
        key: float(np.median([float(row[key]) for row in rows]))
        for key in numeric_keys
    }
    scales = {
        key: max(
            1.0,
            float(np.std([float(row[key]) for row in rows], ddof=0)),
        )
        for key in numeric_keys
    }
    stage_counts: dict[str, int] = {}
    for row in rows:
        stage_counts[row["decided_by"]] = stage_counts.get(row["decided_by"], 0) + 1
    modal_stage = max(stage_counts, key=stage_counts.get)

    def distance(row: dict[str, Any]) -> float:
        value = sum(
            abs(float(row[key]) - medians[key]) / scales[key]
            for key in numeric_keys
        )
        if row["decided_by"] != modal_stage:
            value += 1.25
        return value

    return min(rows, key=distance)
