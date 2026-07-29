#!/usr/bin/env python3
"""Estimate the preregistered H5–H7 quantities from official Monte Carlo output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

BOOTSTRAP_SEED = 2026072906
BOOTSTRAP_DRAWS = 2000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=Path, required=True)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/official_experiment_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _interval(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"estimate": float("nan"), "low": float("nan"), "high": float("nan")}
    return {
        "estimate": float(np.mean(finite)),
        "low": float(np.quantile(finite, 0.025)),
        "high": float(np.quantile(finite, 0.975)),
    }


def _paired_bootstrap(
    frame: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float],
    draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, float]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(frame)
    if n < 2:
        raise ValueError("At least two simulations are required")
    observed = float(statistic(frame))
    values = np.empty(draws, dtype=float)
    for index in range(draws):
        sample = frame.iloc[rng.integers(0, n, size=n)]
        values[index] = float(statistic(sample))
    result = _interval(values)
    result["estimate"] = observed
    return result


def _variance_difference(frame: pd.DataFrame, home_col: str, away_col: str) -> float:
    return float(frame[home_col].var(ddof=1) - frame[away_col].var(ddof=1))


def analyze_h5(matches: pd.DataFrame) -> dict[str, object]:
    metrics = {
        "goals_variance_difference_synthetic_minus_real": ("home_goals", "away_goals"),
        "xg_variance_difference_synthetic_minus_real": ("home_xg", "away_xg"),
        "shots_variance_difference_synthetic_minus_real": ("home_shots", "away_shots"),
    }
    estimates: dict[str, object] = {}
    for name, (home_col, away_col) in metrics.items():
        estimates[name] = _paired_bootstrap(
            matches,
            lambda sample, h=home_col, a=away_col: _variance_difference(sample, h, a),
        )
    estimates["zero_goal_probability_difference_synthetic_minus_real"] = _paired_bootstrap(
        matches,
        lambda sample: float((sample.home_goals.eq(0).astype(float) - sample.away_goals.eq(0).astype(float)).mean()),
    )
    estimates["offensive_lower_tail_difference_synthetic_minus_real"] = _paired_bootstrap(
        matches,
        lambda sample: float(
            (
                ((sample.home_goals.eq(0)) | (sample.home_xg.lt(0.8))).astype(float)
                - ((sample.away_goals.eq(0)) | (sample.away_xg.lt(0.8))).astype(float)
            ).mean()
        ),
    )
    direction_count = sum(
        float(value["estimate"]) < 0
        for key, value in estimates.items()
        if "variance_difference" in key
    )
    return {
        "hypothesis": "H5 Synthetic XI shows lower outcome variability",
        "interpretation_rule": "Negative variance differences favor lower Synthetic XI variability; lower variability is not automatically superiority.",
        "estimands": estimates,
        "variance_estimands_favor_synthetic": int(direction_count),
        "variance_estimands_total": 3,
    }


def _probability_difference(matches: pd.DataFrame, home_mask: pd.Series, away_mask: pd.Series) -> float:
    return float((home_mask.astype(float) - away_mask.astype(float)).mean())


def analyze_h6(matches: pd.DataFrame, config: dict[str, object]) -> dict[str, object]:
    thresholds = config["h6"]["thresholds"]  # type: ignore[index]
    definitions = {
        "three_plus_goals_probability_difference_synthetic_minus_real": (
            lambda frame: frame.home_goals.ge(int(thresholds["goals"])),
            lambda frame: frame.away_goals.ge(int(thresholds["goals"])),
        ),
        "xg_over_threshold_probability_difference_synthetic_minus_real": (
            lambda frame: frame.home_xg.ge(float(thresholds["xg"])),
            lambda frame: frame.away_xg.ge(float(thresholds["xg"])),
        ),
        "shots_over_threshold_probability_difference_synthetic_minus_real": (
            lambda frame: frame.home_shots.ge(int(thresholds["shots"])),
            lambda frame: frame.away_shots.ge(int(thresholds["shots"])),
        ),
        "win_by_margin_probability_difference_synthetic_minus_real": (
            lambda frame: frame.goal_margin_home_minus_away.ge(int(thresholds["goal_margin"])),
            lambda frame: frame.goal_margin_home_minus_away.le(-int(thresholds["goal_margin"])),
        ),
    }
    estimates: dict[str, object] = {}
    for name, (home_fn, away_fn) in definitions.items():
        estimates[name] = _paired_bootstrap(
            matches,
            lambda sample, h=home_fn, a=away_fn: _probability_difference(sample, h(sample), a(sample)),
        )
    quantiles: list[dict[str, float | str]] = []
    for probability in config["h6"]["quantiles"]:  # type: ignore[index]
        q = float(probability)
        for metric in ("goals", "xg", "shots"):
            home = float(matches[f"home_{metric}"].quantile(q))
            away = float(matches[f"away_{metric}"].quantile(q))
            quantiles.append(
                {
                    "metric": metric,
                    "quantile": q,
                    "synthetic": home,
                    "real": away,
                    "synthetic_minus_real": home - away,
                }
            )
    return {
        "hypothesis": "H6 Real Best XI produces more extreme impact actions",
        "interpretation_rule": "Negative Synthetic-minus-Real tail differences favor H6.",
        "threshold_estimands": estimates,
        "quantiles": quantiles,
    }


def _state_rate_table(states: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        states.groupby(["team", "score_state", "numerical_state", "phase"], as_index=False)
        .agg(
            simulations=("simulation_id", "nunique"),
            possessions=("possessions", "sum"),
            shots=("shots", "sum"),
            goals=("goals", "sum"),
            xg=("xg", "sum"),
        )
    )
    grouped["shots_per_possession"] = grouped.shots / grouped.possessions.replace(0, np.nan)
    grouped["goals_per_possession"] = grouped.goals / grouped.possessions.replace(0, np.nan)
    grouped["xg_per_possession"] = grouped.xg / grouped.possessions.replace(0, np.nan)
    return grouped


def _simulation_state_rates(states: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        states.groupby(
            ["simulation_id", "team", "score_state", "numerical_state", "phase"],
            as_index=False,
        )
        .agg(possessions=("possessions", "sum"), shots=("shots", "sum"), goals=("goals", "sum"), xg=("xg", "sum"))
    )
    for outcome in ("shots", "goals", "xg"):
        grouped[f"{outcome}_rate"] = grouped[outcome] / grouped.possessions.replace(0, np.nan)
    return grouped


def analyze_h7(states: pd.DataFrame, synthetic_name: str, real_name: str) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    aggregate = _state_rate_table(states)
    per_sim = _simulation_state_rates(states)
    dimensions = (
        per_sim[["score_state", "numerical_state", "phase"]]
        .drop_duplicates()
        .sort_values(["score_state", "numerical_state", "phase"])
    )
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED + 1)
    simulation_ids = np.sort(states.simulation_id.unique())
    for dimension in dimensions.itertuples(index=False):
        subset = per_sim.loc[
            per_sim.score_state.eq(dimension.score_state)
            & per_sim.numerical_state.eq(dimension.numerical_state)
            & per_sim.phase.eq(dimension.phase)
        ]
        for outcome in ("shots", "goals", "xg"):
            column = f"{outcome}_rate"
            pivot = subset.pivot_table(index="simulation_id", columns="team", values=column, aggfunc="sum")
            pivot = pivot.reindex(index=simulation_ids, columns=[synthetic_name, real_name]).fillna(0.0)
            differences = pivot[synthetic_name] - pivot[real_name]
            boot = np.empty(BOOTSTRAP_DRAWS, dtype=float)
            values = differences.to_numpy(dtype=float)
            for index in range(BOOTSTRAP_DRAWS):
                boot[index] = float(np.mean(values[rng.integers(0, len(values), size=len(values))]))
            rows.append(
                {
                    "score_state": dimension.score_state,
                    "numerical_state": dimension.numerical_state,
                    "phase": dimension.phase,
                    "outcome": outcome,
                    "synthetic_minus_real_rate": float(values.mean()),
                    "low": float(np.quantile(boot, 0.025)),
                    "high": float(np.quantile(boot, 0.975)),
                    "simulation_count": int(len(values)),
                }
            )
    interactions = pd.DataFrame(rows)
    return (
        {
            "hypothesis": "H7 relative advantage depends on score, numerical state and match phase",
            "unit_of_uncertainty": "simulation, not individual event",
            "interaction_cells": int(len(interactions)),
            "estimands_present": bool(not interactions.empty),
        },
        aggregate,
        interactions,
    )


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    matches = pd.read_csv(args.matches)
    states = pd.read_csv(args.states)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    required_match_columns = {
        "simulation_id",
        "home_goals",
        "away_goals",
        "home_xg",
        "away_xg",
        "home_shots",
        "away_shots",
        "goal_margin_home_minus_away",
    }
    missing = required_match_columns - set(matches.columns)
    if missing:
        raise RuntimeError(f"Missing official match columns: {sorted(missing)}")
    if states.empty:
        raise RuntimeError("Official state-condition table is empty")

    synthetic_name = str(matches.get("home", pd.Series(["Synthetic XI"])).iloc[0]) if "home" in matches else "Synthetic XI"
    real_name = str(matches.get("away", pd.Series(["Real Best XI"])).iloc[0]) if "away" in matches else "Real Best XI"
    # The official runner always uses Synthetic XI as home in the primary orientation.
    synthetic_name = "Synthetic XI"
    real_name = "Real Best XI"

    h5 = analyze_h5(matches)
    h6 = analyze_h6(matches, config)
    h7, rates, interactions = analyze_h7(states, synthetic_name, real_name)
    payload = {
        "status": "official_h5_h6_h7_analysis_complete",
        "engine_version": config["engine_version"],
        "simulations": int(matches.simulation_id.nunique()),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "h5": h5,
        "h6": h6,
        "h7": h7,
        "h5_h6_h7_estimands_present": True,
    }
    (args.output / "official_hypotheses_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rates.to_csv(args.output / "official_h7_state_rates.csv", index=False)
    interactions.to_csv(args.output / "official_h7_interactions.csv", index=False)
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
