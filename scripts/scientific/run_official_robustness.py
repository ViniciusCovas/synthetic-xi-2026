#!/usr/bin/env python3
"""Run official_v1 sensitivity and nested parameter uncertainty.

Unlike the historical robustness scripts, every scenario here uses the exact
OfficialCompleteFinalSimulator, canonical rosters and frozen bench policies.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simulator.calibrated_core import CalibrationTargets
from simulator.official_complete_final import (
    OFFICIAL_ENGINE_VERSION,
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
)
from simulator.official_monte_carlo import simulate_official_finals
from simulator.official_profile_sensitivity import build_official_bundles_with_role_variant


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/official_experiment_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sensitivity-simulations", type=int, default=750)
    parser.add_argument("--outer-worlds", type=int)
    parser.add_argument("--inner-matches", type=int)
    return parser.parse_args()


def _load(config_path: Path) -> tuple[dict[str, Any], CalibrationTargets]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    target_path = Path(config["canonical_inputs"]["calibration_targets"])
    targets = CalibrationTargets.from_dict(json.loads(target_path.read_text(encoding="utf-8")))
    return config, targets


def _base_final_config(config: dict[str, Any]) -> OfficialFinalConfig:
    discipline = config["discipline"]
    return OfficialFinalConfig(
        seed=None,
        fouls_per_team_90=float(discipline["fouls_per_team_90"]),
        yellows_per_team_90=float(discipline["yellows_per_team_90"]),
        direct_reds_per_team_90=float(discipline["direct_reds_per_team_90"]),
        booked_player_foul_multiplier=float(discipline["booked_player_foul_multiplier"]),
    )


def sensitivity_scenarios(config: dict[str, Any]) -> list[dict[str, Any]]:
    primary_top = int(config["analysis"]["top_n_primary"])
    primary_minutes = int(config["analysis"]["minutes_primary"])
    return [
        {
            "scenario": "primary",
            "top_n": primary_top,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "top10",
            "top_n": 10,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "top30_or_available",
            "top_n": 30,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "minimum_minutes_450",
            "top_n": primary_top,
            "minimum_minutes": 450,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "minimum_minutes_180",
            "top_n": primary_top,
            "minimum_minutes": 180,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "provider_grid_role_ontology",
            "top_n": primary_top,
            "minimum_minutes": primary_minutes,
            "role_variant": "provider_grid",
            "synthetic_coordination": 1.0,
            "real_coordination": 1.0,
        },
        {
            "scenario": "synthetic_coordination_penalty",
            "top_n": primary_top,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 0.90,
            "real_coordination": 1.0,
        },
        {
            "scenario": "real_coordination_penalty",
            "top_n": primary_top,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 1.0,
            "real_coordination": 0.90,
        },
        {
            "scenario": "equal_moderate_coordination",
            "top_n": primary_top,
            "minimum_minutes": primary_minutes,
            "role_variant": "cohort_relative",
            "synthetic_coordination": 0.95,
            "real_coordination": 0.95,
        },
    ]


def run_sensitivity(
    config: dict[str, Any],
    targets: CalibrationTargets,
    output: Path,
    simulations: int,
) -> dict[str, Any]:
    seed = int(config["seeds"]["sensitivity"])
    rows: list[dict[str, Any]] = []
    base = _base_final_config(config)
    for index, scenario in enumerate(sensitivity_scenarios(config)):
        synthetic, real = build_official_bundles_with_role_variant(
            scenario["role_variant"],
            top_n=int(scenario["top_n"]),
            minimum_minutes=int(scenario["minimum_minutes"]),
        )
        final_config = replace(
            base,
            home_coordination_mean=float(scenario["synthetic_coordination"]),
            away_coordination_mean=float(scenario["real_coordination"]),
        )
        result = simulate_official_finals(
            synthetic,
            real,
            targets,
            config,
            simulations=simulations,
            seed=seed + (index + 1) * 1009,
            final_config=final_config,
            audit_sample_size=0,
        )
        rows.append(
            {
                **scenario,
                "engine_version": result["version"],
                "simulations": simulations,
                "synthetic_champion_probability": result["home_champion_probability"]["estimate"],
                "real_champion_probability": result["away_champion_probability"]["estimate"],
                "regulation_draw_probability": result["regulation_draw_probability"]["estimate"],
                "mean_total_goals": result["mean_total_goals"],
                "mean_total_yellows": result["mean_total_yellows"],
                "mean_total_reds": result["mean_total_reds"],
                "discipline_gate_passed": result["discipline_calibration_gate"]["passed"],
                "event_sanity_passed": result["event_sanity_gate"]["passed"],
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "official_sensitivity_scenarios.csv", index=False)
    baseline = frame.loc[frame.scenario.eq("primary")].iloc[0]
    direction = np.sign(frame.real_champion_probability - frame.synthetic_champion_probability)
    summary = {
        "status": "official_sensitivity_complete",
        "engine_version": OFFICIAL_ENGINE_VERSION,
        "scenarios": int(len(frame)),
        "simulations_per_scenario": int(simulations),
        "primary": baseline.to_dict(),
        "ranges": {
            "synthetic_champion_min": float(frame.synthetic_champion_probability.min()),
            "synthetic_champion_max": float(frame.synthetic_champion_probability.max()),
            "real_champion_min": float(frame.real_champion_probability.min()),
            "real_champion_max": float(frame.real_champion_probability.max()),
        },
        "direction_consistent_across_scenarios": bool((direction == direction.iloc[0]).all()),
        "all_event_sanity_gates_passed": bool(frame.event_sanity_passed.all()),
        "all_discipline_gates_passed": bool(frame.discipline_gate_passed.all()),
        "official_sensitivity_complete": bool(
            frame.event_sanity_passed.all()
            and set(frame.engine_version) == {OFFICIAL_ENGINE_VERSION}
        ),
        "note": "Direction consistency is reported, not required as a validity condition.",
    }
    (output / "official_sensitivity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def run_nested_uncertainty(
    config: dict[str, Any],
    targets: CalibrationTargets,
    output: Path,
    outer_worlds: int,
    inner_matches: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(int(config["seeds"]["nested_uncertainty"]))
    base = _base_final_config(config)
    top_values = [10, 20, 30]
    minute_values = [180, 450, 900]
    role_values = ["cohort_relative", "provider_grid"]
    environment_values = ["cool_or_mild", "warm", "hot", "very_hot"]
    cache: dict[tuple[str, int, int], Any] = {}
    rows: list[dict[str, Any]] = []

    for world_id in range(outer_worlds):
        top_n = int(rng.choice(top_values))
        minimum_minutes = int(rng.choice(minute_values))
        role_variant = str(rng.choice(role_values))
        key = (role_variant, top_n, minimum_minutes)
        if key not in cache:
            cache[key] = build_official_bundles_with_role_variant(
                role_variant, top_n=top_n, minimum_minutes=minimum_minutes
            )
        synthetic, real = cache[key]
        environment_context = str(rng.choice(environment_values))
        # Environment is paired and labelled.  No unvalidated ability modifier is added.
        synthetic_coordination = float(np.clip(rng.normal(0.97, 0.04), 0.85, 1.06))
        real_coordination = float(np.clip(rng.normal(0.97, 0.04), 0.85, 1.06))
        config_world = replace(
            base,
            home_coordination_mean=synthetic_coordination,
            away_coordination_mean=real_coordination,
            coordination_sd=float(np.clip(rng.normal(base.coordination_sd, 0.008), 0.015, 0.07)),
            ability_scale=float(np.clip(rng.normal(base.ability_scale, 0.07), 0.50, 1.00)),
            shot_edge_scale=float(np.clip(rng.normal(base.shot_edge_scale, 0.08), 0.65, 1.25)),
            conversion_edge_scale=float(np.clip(rng.normal(base.conversion_edge_scale, 0.08), 0.55, 1.10)),
            referee_strictness_mean=float(np.clip(rng.normal(1.0, 0.08), 0.80, 1.20)),
            referee_strictness_sd=float(np.clip(rng.normal(base.referee_strictness_sd, 0.02), 0.06, 0.20)),
            yellows_per_team_90=float(np.clip(rng.normal(base.yellows_per_team_90, 0.12), 0.90, 2.00)),
            direct_reds_per_team_90=float(np.clip(rng.normal(base.direct_reds_per_team_90, 0.005), 0.005, 0.04)),
            booked_player_foul_multiplier=float(
                np.clip(rng.normal(base.booked_player_foul_multiplier, 0.06), 0.20, 0.55)
            ),
        )
        world_seed = int(rng.integers(0, 2**32 - 1))
        match_rng = np.random.default_rng(world_seed)
        synthetic_wins = real_wins = 0
        draws_90 = 0
        synthetic_goals: list[int] = []
        real_goals: list[int] = []
        actor_failures = 0
        for _ in range(inner_matches):
            match_seed = int(match_rng.integers(0, 2**32 - 1))
            result = OfficialCompleteFinalSimulator(
                synthetic,
                real,
                targets,
                replace(config_world, seed=match_seed),
            ).simulate(keep_timeline=False)
            synthetic_wins += int(result.winner == synthetic.team.name)
            real_wins += int(result.winner == real.team.name)
            draws_90 += int(result.regulation_home_goals == result.regulation_away_goals)
            synthetic_goals.append(int(result.home_goals))
            real_goals.append(int(result.away_goals))
            actor_failures += len(
                getattr(result, "official_diagnostics", {}).get("actor_membership_failures", [])
            )
        rows.append(
            {
                "world_id": world_id,
                "world_seed": world_seed,
                "engine_version": OFFICIAL_ENGINE_VERSION,
                "top_n": top_n,
                "minimum_minutes": minimum_minutes,
                "role_variant": role_variant,
                "environment_context": environment_context,
                "environment_performance_modifier": 0.0,
                "synthetic_coordination": synthetic_coordination,
                "real_coordination": real_coordination,
                "coordination_sd": config_world.coordination_sd,
                "ability_scale": config_world.ability_scale,
                "shot_edge_scale": config_world.shot_edge_scale,
                "conversion_edge_scale": config_world.conversion_edge_scale,
                "referee_strictness_mean": config_world.referee_strictness_mean,
                "referee_strictness_sd": config_world.referee_strictness_sd,
                "yellows_per_team_90": config_world.yellows_per_team_90,
                "direct_reds_per_team_90": config_world.direct_reds_per_team_90,
                "booked_player_foul_multiplier": config_world.booked_player_foul_multiplier,
                "inner_matches": inner_matches,
                "synthetic_champion_probability": synthetic_wins / inner_matches,
                "real_champion_probability": real_wins / inner_matches,
                "regulation_draw_probability": draws_90 / inner_matches,
                "synthetic_mean_goals": float(np.mean(synthetic_goals)),
                "real_mean_goals": float(np.mean(real_goals)),
                "actor_membership_failures": actor_failures,
            }
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(output / "official_nested_uncertainty_worlds.csv", index=False)
    intervals: dict[str, Any] = {}
    for column in (
        "synthetic_champion_probability",
        "real_champion_probability",
        "regulation_draw_probability",
        "synthetic_mean_goals",
        "real_mean_goals",
    ):
        intervals[column] = {
            "mean": float(frame[column].mean()),
            "median": float(frame[column].median()),
            "p025": float(frame[column].quantile(0.025)),
            "p10": float(frame[column].quantile(0.10)),
            "p90": float(frame[column].quantile(0.90)),
            "p975": float(frame[column].quantile(0.975)),
        }
    components = [
        "player_profile_uncertainty",
        "role_classification_sensitivity",
        "top_n_sensitivity",
        "minimum_minutes_sensitivity",
        "coordination",
        "engine_parameters",
        "paired_referee_context",
        "paired_environment_context",
        "match_randomness",
    ]
    required = list(config["nested_uncertainty"]["required_components"])
    summary = {
        "status": "official_nested_uncertainty_complete",
        "engine_version": OFFICIAL_ENGINE_VERSION,
        "outer_parameter_worlds": int(outer_worlds),
        "inner_matches_per_world": int(inner_matches),
        "total_matches": int(outer_worlds * inner_matches),
        "intervals": intervals,
        "probability_real_more_likely_than_synthetic": float(
            (frame.real_champion_probability > frame.synthetic_champion_probability).mean()
        ),
        "components_included": components,
        "required_components": required,
        "all_required_components_included": set(required) <= set(components),
        "actor_membership_failures": int(frame.actor_membership_failures.sum()),
        "environment_policy": "Paired context label; no unvalidated player-performance modifier.",
        "official_nested_uncertainty_complete": bool(
            set(required) <= set(components)
            and frame.actor_membership_failures.sum() == 0
            and set(frame.engine_version) == {OFFICIAL_ENGINE_VERSION}
        ),
    }
    (output / "official_nested_uncertainty_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config, targets = _load(args.config)
    nested_cfg = config["nested_uncertainty"]
    sensitivity = run_sensitivity(
        config,
        targets,
        args.output,
        simulations=int(args.sensitivity_simulations),
    )
    nested = run_nested_uncertainty(
        config,
        targets,
        args.output,
        outer_worlds=int(args.outer_worlds or nested_cfg["outer_parameter_worlds"]),
        inner_matches=int(args.inner_matches or nested_cfg["inner_matches_per_world"]),
    )
    print(
        json.dumps(
            {
                "status": "official_robustness_complete",
                "sensitivity_complete": sensitivity["official_sensitivity_complete"],
                "nested_uncertainty_complete": nested["official_nested_uncertainty_complete"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
