"""Monte Carlo and diagnostics for the official_v1 final experiment."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
from math import sqrt
from typing import Any

import numpy as np

from .official_complete_final import (
    OFFICIAL_ENGINE_VERSION,
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
)
from .official_profiles import OfficialTeamBundle


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float]:
    if total <= 0:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0}
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = z * sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return {
        "estimate": float(p),
        "low": float(max(0.0, centre - margin)),
        "high": float(min(1.0, centre + margin)),
    }


def _compact_row(simulation_id: int, match_seed: int, result: Any) -> dict[str, Any]:
    home = result.home_stats
    away = result.away_stats
    return {
        "simulation_id": int(simulation_id),
        "match_seed": int(match_seed),
        "winner": result.winner,
        "decided_by": result.decided_by,
        "regulation_home_goals": result.regulation_home_goals,
        "regulation_away_goals": result.regulation_away_goals,
        "extra_time_home_goals": result.extra_time_home_goals,
        "extra_time_away_goals": result.extra_time_away_goals,
        "home_penalties": result.home_penalties,
        "away_penalties": result.away_penalties,
        "home_goals": result.home_goals,
        "away_goals": result.away_goals,
        "home_xg": float(home["xg"]),
        "away_xg": float(away["xg"]),
        "home_shots": int(home["shots"]),
        "away_shots": int(away["shots"]),
        "home_shots_on_target": int(home["shots_on_target"]),
        "away_shots_on_target": int(away["shots_on_target"]),
        "home_fouls": int(home["fouls"]),
        "away_fouls": int(away["fouls"]),
        "home_yellows": int(home.get("benchmark_comparable_yellows", home["yellows"])),
        "away_yellows": int(away.get("benchmark_comparable_yellows", away["yellows"])),
        "home_yellows_raw": int(home["yellows"]),
        "away_yellows_raw": int(away["yellows"]),
        "home_second_yellows": int(home.get("second_yellows", 0)),
        "away_second_yellows": int(away.get("second_yellows", 0)),
        "home_reds": int(home["reds"]),
        "away_reds": int(away["reds"]),
        "home_injuries": int(home["injuries"]),
        "away_injuries": int(away["injuries"]),
        "home_substitutions": int(home["substitutions"]),
        "away_substitutions": int(away["substitutions"]),
        "home_players_remaining": int(home["players_remaining"]),
        "away_players_remaining": int(away["players_remaining"]),
        "goal_margin_home_minus_away": int(result.home_goals - result.away_goals),
        "regulation_draw": bool(result.regulation_home_goals == result.regulation_away_goals),
        "actor_membership_failure_count": len(
            getattr(result, "official_diagnostics", {}).get("actor_membership_failures", [])
        ),
        "used_home_bench_ids": "|".join(
            getattr(result, "official_runtime", {}).get("used_home_bench_ids", [])
        ),
        "used_away_bench_ids": "|".join(
            getattr(result, "official_runtime", {}).get("used_away_bench_ids", [])
        ),
    }


def _flatten_state_diagnostics(simulation_id: int, result: Any) -> list[dict[str, Any]]:
    diagnostics = getattr(result, "official_diagnostics", {})
    exposures = diagnostics.get("exposures", {})
    outcomes = diagnostics.get("outcomes", {})
    rows: list[dict[str, Any]] = []
    for team, by_score in exposures.items():
        for score_state, by_numerical in by_score.items():
            for numerical_state, by_phase in by_numerical.items():
                for phase, possessions in by_phase.items():
                    outcome = (
                        outcomes.get(team, {})
                        .get(score_state, {})
                        .get(numerical_state, {})
                        .get(phase, {})
                    )
                    rows.append(
                        {
                            "simulation_id": int(simulation_id),
                            "team": team,
                            "score_state": score_state,
                            "numerical_state": numerical_state,
                            "phase": phase,
                            "possessions": float(possessions),
                            "shots": float(outcome.get("shots", 0.0)),
                            "goals": float(outcome.get("goals", 0.0)),
                            "xg": float(outcome.get("xg", 0.0)),
                        }
                    )
    return rows


def _representative_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "home_goals",
        "away_goals",
        "home_shots",
        "away_shots",
        "home_fouls",
        "away_fouls",
        "home_yellows",
        "away_yellows",
        "home_reds",
        "away_reds",
        "home_substitutions",
        "away_substitutions",
    )
    medians = {key: float(np.median([float(row[key]) for row in rows])) for key in keys}
    scales = {
        key: max(1.0, float(np.std([float(row[key]) for row in rows], ddof=0)))
        for key in keys
    }
    stages: dict[str, int] = {}
    for row in rows:
        stages[row["decided_by"]] = stages.get(row["decided_by"], 0) + 1
    modal_stage = max(stages, key=stages.get)

    def distance(row: dict[str, Any]) -> float:
        value = sum(abs(float(row[key]) - medians[key]) / scales[key] for key in keys)
        if row["decided_by"] != modal_stage:
            value += 1.25
        return value

    return min(rows, key=distance)


def discipline_gate(summary: dict[str, Any], discipline: dict[str, Any]) -> dict[str, Any]:
    targets = discipline["targets"]
    limits = discipline["release_limits"]
    errors = {
        "fouls": float(summary["mean_total_fouls"] - targets["mean_total_fouls"]),
        "yellows": float(summary["mean_total_yellows"] - targets["mean_total_yellows"]),
        "reds": float(summary["mean_total_reds"] - targets["mean_total_reds"]),
    }
    red_ratio = float(summary["mean_total_reds"] / max(targets["mean_total_reds"], 1e-12))
    checks = {
        "absolute_foul_error": abs(errors["fouls"]) <= limits["absolute_foul_error"],
        "absolute_yellow_error": abs(errors["yellows"]) <= limits["absolute_yellow_error"],
        "absolute_red_error": abs(errors["reds"]) <= limits["absolute_red_error"],
        "red_ratio_lower": red_ratio >= limits["red_ratio_min"],
        "red_ratio_upper": red_ratio <= limits["red_ratio_max"],
    }
    return {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "errors": errors,
        "red_ratio": red_ratio,
        "targets": targets,
        "limits": limits,
    }


def event_sanity_gate(rows: list[dict[str, Any]], home: OfficialTeamBundle, away: OfficialTeamBundle) -> dict[str, Any]:
    home_registered = set(home.registered_ids)
    away_registered = set(away.registered_ids)
    failures: list[str] = []
    for row in rows:
        if int(row["actor_membership_failure_count"]) != 0:
            failures.append(f"simulation {row['simulation_id']}: invalid actor membership")
        for field, registered in (
            ("used_home_bench_ids", home_registered),
            ("used_away_bench_ids", away_registered),
        ):
            used = {value for value in str(row[field]).split("|") if value}
            if not used <= registered:
                failures.append(
                    f"simulation {row['simulation_id']}: non-roster bench IDs {sorted(used - registered)}"
                )
            if len(used) != len(str(row[field]).split("|")) and str(row[field]):
                failures.append(f"simulation {row['simulation_id']}: duplicate bench entry")
        if int(row["home_substitutions"]) > 6 or int(row["away_substitutions"]) > 6:
            failures.append(f"simulation {row['simulation_id']}: substitution maximum exceeded")
        if int(row["home_players_remaining"]) < 7 or int(row["away_players_remaining"]) < 7:
            failures.append(f"simulation {row['simulation_id']}: impossible player count")
    return {
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures[:100],
    }


def simulate_official_finals(
    home: OfficialTeamBundle,
    away: OfficialTeamBundle,
    targets: Any,
    experiment_config: dict[str, Any],
    simulations: int,
    seed: int,
    final_config: OfficialFinalConfig | None = None,
    audit_sample_size: int = 250,
) -> dict[str, Any]:
    if simulations < 1:
        raise ValueError("simulations must be positive")
    base = final_config or OfficialFinalConfig(seed=None)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    match_seeds: list[int] = []

    for simulation_id in range(simulations):
        match_seed = int(rng.integers(0, 2**32 - 1))
        match_seeds.append(match_seed)
        result = OfficialCompleteFinalSimulator(
            home,
            away,
            targets,
            replace(base, seed=match_seed),
        ).simulate(keep_timeline=False)
        rows.append(_compact_row(simulation_id, match_seed, result))
        state_rows.extend(_flatten_state_diagnostics(simulation_id, result))

    home_champions = sum(row["winner"] == home.team.name for row in rows)
    away_champions = simulations - home_champions
    regulation_home_wins = sum(row["regulation_home_goals"] > row["regulation_away_goals"] for row in rows)
    regulation_away_wins = sum(row["regulation_home_goals"] < row["regulation_away_goals"] for row in rows)
    regulation_draws = simulations - regulation_home_wins - regulation_away_wins
    extra_time = sum(row["decided_by"] in {"extra_time", "penalties"} for row in rows)
    shootouts = sum(row["decided_by"] == "penalties" for row in rows)

    representative_row = _representative_row(rows)
    representative = OfficialCompleteFinalSimulator(
        home,
        away,
        targets,
        replace(base, seed=int(representative_row["match_seed"])),
    ).simulate(keep_timeline=True)

    seed_hash = hashlib.sha256(
        ",".join(str(value) for value in match_seeds).encode("utf-8")
    ).hexdigest()
    summary: dict[str, Any] = {
        "status": "official_final_monte_carlo_completed",
        "version": OFFICIAL_ENGINE_VERSION,
        "simulations": int(simulations),
        "master_seed": int(seed),
        "match_seed_ledger_sha256": seed_hash,
        "home": home.team.name,
        "away": away.team.name,
        "home_champion_probability": wilson(home_champions, simulations),
        "away_champion_probability": wilson(away_champions, simulations),
        "regulation_home_win_probability": wilson(regulation_home_wins, simulations),
        "regulation_draw_probability": wilson(regulation_draws, simulations),
        "regulation_away_win_probability": wilson(regulation_away_wins, simulations),
        "extra_time_probability": wilson(extra_time, simulations),
        "penalty_shootout_probability": wilson(shootouts, simulations),
        "mean_regulation_goals": float(
            np.mean([row["regulation_home_goals"] + row["regulation_away_goals"] for row in rows])
        ),
        "mean_total_goals": float(np.mean([row["home_goals"] + row["away_goals"] for row in rows])),
        "mean_total_shots": float(np.mean([row["home_shots"] + row["away_shots"] for row in rows])),
        "mean_total_shots_on_target": float(
            np.mean([row["home_shots_on_target"] + row["away_shots_on_target"] for row in rows])
        ),
        "mean_total_fouls": float(np.mean([row["home_fouls"] + row["away_fouls"] for row in rows])),
        "mean_total_yellows": float(np.mean([row["home_yellows"] + row["away_yellows"] for row in rows])),
        "mean_total_yellows_raw": float(
            np.mean([row["home_yellows_raw"] + row["away_yellows_raw"] for row in rows])
        ),
        "mean_total_second_yellows": float(
            np.mean([row["home_second_yellows"] + row["away_second_yellows"] for row in rows])
        ),
        "mean_total_reds": float(np.mean([row["home_reds"] + row["away_reds"] for row in rows])),
        "mean_total_injuries": float(
            np.mean([row["home_injuries"] + row["away_injuries"] for row in rows])
        ),
        "mean_total_substitutions": float(
            np.mean([row["home_substitutions"] + row["away_substitutions"] for row in rows])
        ),
        "calibration_targets": targets.__dict__,
        "final_config": asdict(base),
        "representative_match_selection": {
            "rule": "Minimum standardized distance to preregistered Monte Carlo medians; no excitement selection.",
            "simulation_id": int(representative_row["simulation_id"]),
            "match_seed": int(representative_row["match_seed"]),
        },
        "representative_match": {
            **representative.as_dict(),
            "official_runtime": getattr(representative, "official_runtime", {}),
            "official_diagnostics": getattr(representative, "official_diagnostics", {}),
        },
    }
    summary["discipline_calibration_gate"] = discipline_gate(
        summary, experiment_config["discipline"]
    )
    summary["event_sanity_gate"] = event_sanity_gate(rows, home, away)
    summary["audit_sample"] = rows[: min(int(audit_sample_size), simulations)]
    summary["rows"] = rows
    summary["state_condition_rows"] = state_rows
    return summary


def paired_orientation_diagnostic(
    synthetic: OfficialTeamBundle,
    real: OfficialTeamBundle,
    targets: Any,
    simulations: int,
    seed: int,
    maximum_difference: float,
    config: OfficialFinalConfig | None = None,
) -> dict[str, Any]:
    if simulations < 20:
        raise ValueError("paired orientation diagnostic requires at least 20 simulations")
    base = replace(config or OfficialFinalConfig(), home_advantage=0.0)
    rng = np.random.default_rng(seed)
    synthetic_wins_home = synthetic_wins_away = 0
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
    first_probability = synthetic_wins_home / simulations
    second_probability = synthetic_wins_away / simulations
    difference = abs(first_probability - second_probability)
    standard_error = float(np.std(paired_differences, ddof=1) / np.sqrt(simulations))
    return {
        "engine_version": OFFICIAL_ENGINE_VERSION,
        "simulations_per_orientation": int(simulations),
        "common_random_numbers": true,
        "synthetic_probability_as_home": first_probability,
        "synthetic_probability_as_away": second_probability,
        "absolute_orientation_difference": difference,
        "paired_standard_error": standard_error,
        "maximum_allowed_difference": maximum_difference,
        "passed": bool(difference <= maximum_difference),
    }


def seed_stability_diagnostic(
    synthetic: OfficialTeamBundle,
    real: OfficialTeamBundle,
    targets: Any,
    experiment_config: dict[str, Any],
    seeds: list[int],
    simulations_per_seed: int,
    maximum_spread: float,
    config: OfficialFinalConfig | None = None,
) -> dict[str, Any]:
    estimates: list[float] = []
    for seed in seeds:
        result = simulate_official_finals(
            synthetic,
            real,
            targets,
            experiment_config,
            simulations=simulations_per_seed,
            seed=int(seed),
            final_config=config,
            audit_sample_size=0,
        )
        estimates.append(float(result["home_champion_probability"]["estimate"]))
    spread = max(estimates) - min(estimates)
    return {
        "engine_version": OFFICIAL_ENGINE_VERSION,
        "seeds": [int(seed) for seed in seeds],
        "simulations_per_seed": int(simulations_per_seed),
        "synthetic_champion_estimates": estimates,
        "maximum_spread": float(spread),
        "maximum_allowed_spread": float(maximum_spread),
        "passed": bool(spread <= maximum_spread),
    }
