#!/usr/bin/env python3
"""Identified-set Monte Carlo simulation for Synthetic XI vs plausible Real XIs.

Primary estimand: the envelope of match-outcome probabilities across every Real XI
that remains admissible after structural provider missingness. The main Synthetic XI
is the preregistered Top-20 trimmed-mean avatar by exact role. Top-10/Top-30,
uncertainty pooling, and ability-response parameters are sensitivity analyses.

No provider API calls are made.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simulator.calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibrationTargets,
)
from simulator.engine import PlayerProfile, ROLE_ORDER, TeamProfile

SEED = 20260720
SHADOW = Path("data/audits/scope_correct_coverage/shadow_selection/shadow_selection_all_players.csv")
IDENTIFIED_SET = Path("data/releases/v1_0_identified_set/plausible_real_xi_combinations.csv")
IDENTIFIED_MANIFEST = Path("data/releases/v1_0_identified_set/identified_set_manifest.json")
CALIBRATION = Path("data/simulations/calibration/world_cup_2026_targets.json")
FIXTURES = Path("data/processed/fixtures.csv")
PLAYER_MATCHES = Path("data/processed/player_matches.csv")
CALIBRATION_QUALITY = Path("data/simulations/calibrated_v0_2/calibration_quality.json")
OUT = Path("data/simulations/identified_set_v1")

ROLE_TO_SLOT = {
    "GK": "GK",
    "RCB": "CB1",
    "LCB": "CB2",
    "RB": "FB1",
    "LB": "FB2",
    "DM": "DM",
    "CM": "CM",
    "AM": "AM",
    "RW": "W1",
    "LW": "W2",
    "ST": "ST",
}
SLOT_TO_ROLE = {slot: role for role, slot in ROLE_TO_SLOT.items()}
DIMS = [
    "overall",
    "build_up",
    "progression",
    "creation",
    "finishing",
    "defending",
    "duels",
    "retention",
    "goalkeeping",
]
SCENARIOS = [
    {
        "scenario": "primary_top20_pooled",
        "top_n": 20,
        "synthetic_uncertainty": "pooled",
        "ability_scale": 0.75,
        "shot_edge_scale": 0.95,
        "conversion_edge_scale": 0.80,
        "worlds": 80,
        "matches_per_orientation": 100,
        "primary": True,
    },
    {
        "scenario": "sensitivity_top10",
        "top_n": 10,
        "synthetic_uncertainty": "pooled",
        "ability_scale": 0.75,
        "shot_edge_scale": 0.95,
        "conversion_edge_scale": 0.80,
        "worlds": 40,
        "matches_per_orientation": 100,
        "primary": False,
    },
    {
        "scenario": "sensitivity_top30",
        "top_n": 30,
        "synthetic_uncertainty": "pooled",
        "ability_scale": 0.75,
        "shot_edge_scale": 0.95,
        "conversion_edge_scale": 0.80,
        "worlds": 40,
        "matches_per_orientation": 100,
        "primary": False,
    },
    {
        "scenario": "sensitivity_no_uncertainty_pooling",
        "top_n": 20,
        "synthetic_uncertainty": "member_median",
        "ability_scale": 0.75,
        "shot_edge_scale": 0.95,
        "conversion_edge_scale": 0.80,
        "worlds": 40,
        "matches_per_orientation": 100,
        "primary": False,
    },
    {
        "scenario": "sensitivity_ability_low",
        "top_n": 20,
        "synthetic_uncertainty": "pooled",
        "ability_scale": 0.60,
        "shot_edge_scale": 0.80,
        "conversion_edge_scale": 0.65,
        "worlds": 30,
        "matches_per_orientation": 80,
        "primary": False,
    },
    {
        "scenario": "sensitivity_ability_high",
        "top_n": 20,
        "synthetic_uncertainty": "pooled",
        "ability_scale": 0.90,
        "shot_edge_scale": 1.10,
        "conversion_edge_scale": 0.95,
        "worlds": 30,
        "matches_per_orientation": 80,
        "primary": False,
    },
]


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_hashes() -> dict[str, str]:
    return {
        str(path): sha256(path)
        for path in [SHADOW, IDENTIFIED_SET, IDENTIFIED_MANIFEST, CALIBRATION, FIXTURES, PLAYER_MATCHES]
    }


def load_players() -> pd.DataFrame:
    frame = pd.read_csv(SHADOW, low_memory=False)
    frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
    frame = frame.dropna(subset=["player_id", "resolved_role"]).copy()
    frame["player_id"] = frame["player_id"].astype(int)
    for column in DIMS + ["uncertainty", "minutes_num", "conservative_score"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["stable", "covered", "profile_scored", "scientific_role_eligible"]:
        frame[column] = as_bool(frame.get(column, pd.Series(False, index=frame.index)))
    frame = frame.loc[frame["resolved_role"].isin(ROLE_TO_SLOT)].copy()
    return frame


def profile_from_row(
    row: pd.Series,
    slot: str,
    *,
    synthetic: bool,
    name: str | None = None,
    uncertainty: float | None = None,
) -> PlayerProfile:
    return PlayerProfile(
        player_id=str(row.get("player_id", f"SYN-{slot}")),
        name=name or str(row.get("player_name", f"SYN-{slot}")),
        role=slot,
        minutes=float(row.get("minutes_num", 0.0)),
        overall=float(row["overall"]),
        build_up=float(row["build_up"]),
        progression=float(row["progression"]),
        creation=float(row["creation"]),
        finishing=float(row["finishing"]),
        defending=float(row["defending"]),
        duels=float(row["duels"]),
        retention=float(row["retention"]),
        goalkeeping=float(row["goalkeeping"]),
        uncertainty=float(row.get("uncertainty", 0.08) if uncertainty is None else uncertainty),
        synthetic=synthetic,
    )


def trimmed_mean(series: pd.Series) -> float:
    ordered = pd.to_numeric(series, errors="coerce").dropna().sort_values()
    if ordered.empty:
        raise RuntimeError("Cannot compute a trimmed mean from an empty series")
    trim = int(len(ordered) * 0.10)
    if trim and len(ordered) > 2 * trim:
        ordered = ordered.iloc[trim : len(ordered) - trim]
    return float(ordered.mean())


def synthetic_team(
    players: pd.DataFrame, top_n: int, uncertainty_mode: str
) -> tuple[TeamProfile, pd.DataFrame]:
    profiles: list[PlayerProfile] = []
    membership: list[dict[str, Any]] = []
    for slot in ROLE_ORDER:
        role = SLOT_TO_ROLE[slot]
        candidates = players.loc[
            players["resolved_role"].eq(role)
            & players["stable"]
            & players["covered"]
            & players["profile_scored"]
            & players["scientific_role_eligible"]
            & players["minutes_num"].ge(900)
        ].sort_values(["conservative_score", "minutes_num"], ascending=[False, False])
        if candidates.empty:
            raise RuntimeError(f"No scientifically covered candidates for role {role}")
        members = candidates.head(top_n).copy()
        values = {dimension: trimmed_mean(members[dimension]) for dimension in DIMS}
        pooled = max(0.025, float(members["uncertainty"].mean()) / math.sqrt(len(members)))
        member_median = float(members["uncertainty"].median())
        syn_uncertainty = pooled if uncertainty_mode == "pooled" else member_median
        row = pd.Series(
            {
                "player_id": f"SYN-{role}-T{top_n}-{uncertainty_mode}",
                "player_name": f"SYN-{role}-T{top_n}",
                "minutes_num": float(members["minutes_num"].median()),
                "uncertainty": syn_uncertainty,
                **values,
            }
        )
        profiles.append(
            profile_from_row(
                row,
                slot,
                synthetic=True,
                name=f"SYN-{role}-T{top_n}",
                uncertainty=syn_uncertainty,
            )
        )
        for rank, member in enumerate(members.itertuples(index=False), start=1):
            membership.append(
                {
                    "top_n_requested": top_n,
                    "uncertainty_mode": uncertainty_mode,
                    "role": role,
                    "slot": slot,
                    "actual_n": int(len(members)),
                    "member_rank": rank,
                    "player_id": int(member.player_id),
                    "player_name": member.player_name,
                    "world_cup_team": getattr(member, "world_cup_team", None),
                    "minutes_num": float(member.minutes_num),
                    "overall": float(member.overall),
                    "conservative_score": float(member.conservative_score),
                    "member_uncertainty": float(member.uncertainty),
                    "avatar_uncertainty": syn_uncertainty,
                }
            )
    return TeamProfile(name=f"Synthetic XI Top {top_n}", players=tuple(profiles)), pd.DataFrame(membership)


def real_teams(players: pd.DataFrame) -> tuple[dict[str, TeamProfile], pd.DataFrame]:
    identified = pd.read_csv(IDENTIFIED_SET, low_memory=False)
    identified["player_id"] = pd.to_numeric(identified["player_id"], errors="coerce").astype(int)
    profiles_by_id = players.drop_duplicates("player_id").set_index("player_id")
    teams: dict[str, TeamProfile] = {}
    rows: list[dict[str, Any]] = []
    for combination_id, group in identified.groupby("combination_id", sort=True):
        team_players: list[PlayerProfile] = []
        for role, slot in ROLE_TO_SLOT.items():
            chosen = group.loc[group["role"].eq(role)]
            if len(chosen) != 1:
                raise RuntimeError(
                    f"{combination_id}: expected one player for role {role}, got {len(chosen)}"
                )
            selected = chosen.iloc[0]
            player_id = int(selected["player_id"])
            if player_id not in profiles_by_id.index:
                raise RuntimeError(f"Profile missing for player_id={player_id}")
            row = profiles_by_id.loc[player_id]
            team_players.append(profile_from_row(row, slot, synthetic=False))
            rows.append(
                {
                    "combination_id": combination_id,
                    "role": role,
                    "slot": slot,
                    "player_id": player_id,
                    "player_name": row["player_name"],
                    "world_cup_team": row.get("world_cup_team"),
                    "overall": float(row["overall"]),
                    "uncertainty": float(row["uncertainty"]),
                    "minutes_num": float(row["minutes_num"]),
                    "provider_structural_missingness_confirmed": bool(
                        as_bool(
                            pd.Series(
                                [selected.get("provider_structural_missingness_confirmed", False)]
                            )
                        ).iloc[0]
                    ),
                }
            )
        teams[str(combination_id)] = TeamProfile(
            name=f"Real XI {combination_id}", players=tuple(team_players)
        )
    return teams, pd.DataFrame(rows)


def observed_calibration() -> CalibrationTargets:
    payload = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return CalibrationTargets.from_dict(payload)


def calibration_worlds(count: int) -> list[CalibrationTargets]:
    fixtures = pd.read_csv(FIXTURES, low_memory=False)
    players = pd.read_csv(PLAYER_MATCHES, low_memory=False)
    for column in ["home_goals", "away_goals"]:
        fixtures[column] = pd.to_numeric(fixtures[column], errors="coerce")
    primary = fixtures.loc[fixtures["status"].eq("FT")].dropna(
        subset=["home_goals", "away_goals"]
    ).copy()
    if primary.empty:
        raise RuntimeError("No FT calibration fixtures")
    primary["fixture_id"] = pd.to_numeric(primary["fixture_id"], errors="coerce").astype(int)
    primary["total_goals"] = primary["home_goals"] + primary["away_goals"]
    players["fixture_id"] = pd.to_numeric(players["fixture_id"], errors="coerce")
    players = players.dropna(subset=["fixture_id"]).copy()
    players["fixture_id"] = players["fixture_id"].astype(int)
    for column in ["shots", "shots_on", "goals"]:
        if column not in players:
            players[column] = 0.0
        players[column] = pd.to_numeric(players[column], errors="coerce").fillna(0.0)
    per_fixture = players.groupby("fixture_id", as_index=False).agg(
        captured_shots=("shots", "sum"),
        captured_shots_on=("shots_on", "sum"),
        captured_goals=("goals", "sum"),
    )
    primary = primary.merge(per_fixture, on="fixture_id", how="left")
    for column in ["captured_shots", "captured_shots_on", "captured_goals"]:
        primary[column] = primary[column].fillna(0.0)

    rng = np.random.default_rng(SEED + 11)
    result: list[CalibrationTargets] = [observed_calibration()]
    n = len(primary)
    for _ in range(max(0, count - 1)):
        sample = primary.iloc[rng.integers(0, n, n)]
        exact_goals = float(sample["total_goals"].sum())
        captured_goals = float(sample["captured_goals"].sum())
        adjustment = float(
            np.clip(exact_goals / captured_goals if captured_goals else 1.0, 1.0, 1.40)
        )
        shots = float(sample["captured_shots"].sum()) * adjustment
        shots_on = float(sample["captured_shots_on"].sum()) * adjustment
        mean_goals = exact_goals / n
        mean_shots = max(shots / n, mean_goals + 0.01)
        mean_shots_on = min(max(shots_on / n, 0.01), mean_shots)
        result.append(
            CalibrationTargets(
                source_match_count=n,
                mean_goals_per_match=mean_goals,
                mean_shots_per_match=mean_shots,
                mean_shots_on_target_per_match=mean_shots_on,
                zero_zero_rate=float(
                    ((sample["home_goals"] == 0) & (sample["away_goals"] == 0)).mean()
                ),
                home_win_rate=float((sample["home_goals"] > sample["away_goals"]).mean()),
                draw_rate=float((sample["home_goals"] == sample["away_goals"]).mean()),
                away_win_rate=float((sample["home_goals"] < sample["away_goals"]).mean()),
                model_possessions_per_match=104.0,
            )
        )
    return result


def single_result(
    synthetic: TeamProfile,
    real: TeamProfile,
    targets: CalibrationTargets,
    config_values: dict[str, float],
    seed: int,
    synthetic_home: bool,
) -> dict[str, Any]:
    config = CalibratedConfig(
        seed=seed,
        home_advantage=0.0,
        ability_scale=config_values["ability_scale"],
        shot_edge_scale=config_values["shot_edge_scale"],
        conversion_edge_scale=config_values["conversion_edge_scale"],
    )
    home, away = (synthetic, real) if synthetic_home else (real, synthetic)
    result = CalibratedMatchSimulator(home, away, targets, config).simulate(keep_timeline=False)
    if synthetic_home:
        sg, rg = result.home_goals, result.away_goals
        sxg, rxg = result.home_xg, result.away_xg
        ss, rs = result.home_shots, result.away_shots
        sso, rso = result.home_shots_on_target, result.away_shots_on_target
        sp = result.home_possessions / max(1, result.home_possessions + result.away_possessions)
    else:
        sg, rg = result.away_goals, result.home_goals
        sxg, rxg = result.away_xg, result.home_xg
        ss, rs = result.away_shots, result.home_shots
        sso, rso = result.away_shots_on_target, result.home_shots_on_target
        sp = result.away_possessions / max(1, result.home_possessions + result.away_possessions)
    return {
        "synthetic_goals": int(sg),
        "real_goals": int(rg),
        "synthetic_xg": float(sxg),
        "real_xg": float(rxg),
        "synthetic_shots": int(ss),
        "real_shots": int(rs),
        "synthetic_shots_on_target": int(sso),
        "real_shots_on_target": int(rso),
        "synthetic_possession_share": float(sp),
        "synthetic_win": int(sg > rg),
        "draw": int(sg == rg),
        "real_win": int(sg < rg),
        "goal_difference": int(sg - rg),
        "xg_difference": float(sxg - rxg),
        "scoreline": f"{sg}-{rg}",
    }


def run_simulation(
    players: pd.DataFrame,
    real: dict[str, TeamProfile],
    worlds: list[CalibrationTargets],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    match_rows: list[dict[str, Any]] = []
    membership_frames: list[pd.DataFrame] = []
    profile_rows: list[dict[str, Any]] = []
    synthetic_cache: dict[tuple[int, str], TeamProfile] = {}

    for scenario_index, scenario in enumerate(SCENARIOS):
        cache_key = (scenario["top_n"], scenario["synthetic_uncertainty"])
        if cache_key not in synthetic_cache:
            team, membership = synthetic_team(players, *cache_key)
            synthetic_cache[cache_key] = team
            membership_frames.append(membership)
            for profile in team.players:
                profile_rows.append(
                    {
                        "team_type": "synthetic",
                        "scenario_profile": f"top{cache_key[0]}_{cache_key[1]}",
                        **asdict(profile),
                    }
                )
        synthetic = synthetic_cache[cache_key]
        config_values = {
            "ability_scale": scenario["ability_scale"],
            "shot_edge_scale": scenario["shot_edge_scale"],
            "conversion_edge_scale": scenario["conversion_edge_scale"],
        }
        for combination_id, real_team in sorted(real.items()):
            for world_id in range(scenario["worlds"]):
                targets = worlds[world_id]
                for orientation in (0, 1):
                    synthetic_home = orientation == 0
                    for replicate in range(scenario["matches_per_orientation"]):
                        # The same stream is reused across all line-up combinations and mirrored orientation.
                        match_seed = int(
                            np.random.SeedSequence(
                                [SEED, scenario_index, world_id, replicate]
                            ).generate_state(1)[0]
                        )
                        outcome = single_result(
                            synthetic,
                            real_team,
                            targets,
                            config_values,
                            match_seed,
                            synthetic_home,
                        )
                        match_rows.append(
                            {
                                "scenario": scenario["scenario"],
                                "primary": scenario["primary"],
                                "top_n": scenario["top_n"],
                                "synthetic_uncertainty": scenario["synthetic_uncertainty"],
                                "ability_scale": scenario["ability_scale"],
                                "shot_edge_scale": scenario["shot_edge_scale"],
                                "conversion_edge_scale": scenario["conversion_edge_scale"],
                                "combination_id": combination_id,
                                "world_id": world_id,
                                "orientation": "synthetic_home" if synthetic_home else "real_home",
                                "replicate": replicate,
                                "match_seed": match_seed,
                                **outcome,
                            }
                        )
    for combination_id, team in sorted(real.items()):
        for profile in team.players:
            profile_rows.append(
                {
                    "team_type": "real",
                    "scenario_profile": combination_id,
                    **asdict(profile),
                }
            )
    return (
        pd.DataFrame(match_rows),
        pd.concat(membership_frames, ignore_index=True).drop_duplicates(),
        pd.DataFrame(profile_rows),
    )


def q025(series: pd.Series) -> float:
    return float(series.quantile(0.025))


def q975(series: pd.Series) -> float:
    return float(series.quantile(0.975))


def summarize(
    matches: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    world = matches.groupby(["scenario", "combination_id", "world_id"], as_index=False).agg(
        matches=("synthetic_win", "size"),
        synthetic_win_probability=("synthetic_win", "mean"),
        draw_probability=("draw", "mean"),
        real_win_probability=("real_win", "mean"),
        mean_synthetic_goals=("synthetic_goals", "mean"),
        mean_real_goals=("real_goals", "mean"),
        mean_goal_difference=("goal_difference", "mean"),
        mean_synthetic_xg=("synthetic_xg", "mean"),
        mean_real_xg=("real_xg", "mean"),
        mean_xg_difference=("xg_difference", "mean"),
        mean_synthetic_possession=("synthetic_possession_share", "mean"),
    )
    world["win_probability_margin"] = (
        world["synthetic_win_probability"] - world["real_win_probability"]
    )
    combo = world.groupby(["scenario", "combination_id"], as_index=False).agg(
        calibration_worlds=("world_id", "nunique"),
        simulated_matches=("matches", "sum"),
        synthetic_win_probability=("synthetic_win_probability", "mean"),
        synthetic_win_q025=("synthetic_win_probability", q025),
        synthetic_win_q975=("synthetic_win_probability", q975),
        draw_probability=("draw_probability", "mean"),
        real_win_probability=("real_win_probability", "mean"),
        real_win_q025=("real_win_probability", q025),
        real_win_q975=("real_win_probability", q975),
        win_margin=("win_probability_margin", "mean"),
        win_margin_q025=("win_probability_margin", q025),
        win_margin_q975=("win_probability_margin", q975),
        mean_synthetic_goals=("mean_synthetic_goals", "mean"),
        mean_real_goals=("mean_real_goals", "mean"),
        goal_difference=("mean_goal_difference", "mean"),
        goal_difference_q025=("mean_goal_difference", q025),
        goal_difference_q975=("mean_goal_difference", q975),
        mean_synthetic_xg=("mean_synthetic_xg", "mean"),
        mean_real_xg=("mean_real_xg", "mean"),
        xg_difference=("mean_xg_difference", "mean"),
        xg_difference_q025=("mean_xg_difference", q025),
        xg_difference_q975=("mean_xg_difference", q975),
        synthetic_possession_share=("mean_synthetic_possession", "mean"),
    )
    envelope_rows: list[dict[str, Any]] = []
    for scenario, group in combo.groupby("scenario", sort=False):
        robust_synthetic = bool(group["win_margin_q025"].gt(0).all())
        robust_real = bool(group["win_margin_q975"].lt(0).all())
        direction = (
            "synthetic" if robust_synthetic else "real" if robust_real else "not_point_identified"
        )
        envelope_rows.append(
            {
                "scenario": scenario,
                "plausible_real_xis": int(len(group)),
                "simulated_matches": int(group["simulated_matches"].sum()),
                "synthetic_win_probability_min": float(
                    group["synthetic_win_probability"].min()
                ),
                "synthetic_win_probability_max": float(
                    group["synthetic_win_probability"].max()
                ),
                "draw_probability_min": float(group["draw_probability"].min()),
                "draw_probability_max": float(group["draw_probability"].max()),
                "real_win_probability_min": float(group["real_win_probability"].min()),
                "real_win_probability_max": float(group["real_win_probability"].max()),
                "win_margin_min": float(group["win_margin"].min()),
                "win_margin_max": float(group["win_margin"].max()),
                "identified_interval_lower": float(group["win_margin_q025"].min()),
                "identified_interval_upper": float(group["win_margin_q975"].max()),
                "goal_difference_min": float(group["goal_difference"].min()),
                "goal_difference_max": float(group["goal_difference"].max()),
                "xg_difference_min": float(group["xg_difference"].min()),
                "xg_difference_max": float(group["xg_difference"].max()),
                "directionally_robust": bool(robust_synthetic or robust_real),
                "robust_direction": direction,
            }
        )
    envelope = pd.DataFrame(envelope_rows)
    scores = matches.groupby(
        ["scenario", "combination_id", "scoreline"], as_index=False
    ).size()
    totals = scores.groupby(["scenario", "combination_id"])["size"].transform("sum")
    scores["probability"] = scores["size"] / totals
    scores = scores.sort_values(
        ["scenario", "combination_id", "probability"],
        ascending=[True, True, False],
    )
    return world, combo, envelope, scores


def representative_match(
    players: pd.DataFrame,
    real: dict[str, TeamProfile],
    combo: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    primary = combo.loc[combo["scenario"].eq("primary_top20_pooled")].copy()
    midpoint = float(primary["synthetic_win_probability"].mean())
    chosen_index = (primary["synthetic_win_probability"] - midpoint).abs().idxmin()
    chosen_combo = str(primary.loc[chosen_index, "combination_id"])
    synthetic, _ = synthetic_team(players, 20, "pooled")
    real_team = real[chosen_combo]
    target = observed_calibration()
    global_goal_diff = float(primary["goal_difference"].mean())
    global_syn_goals = float(primary["mean_synthetic_goals"].mean())
    global_real_goals = float(primary["mean_real_goals"].mean())
    best: tuple[float, Any, int, bool] | None = None
    for index in range(600):
        synthetic_home = index % 2 == 0
        seed = int(np.random.SeedSequence([SEED, 999, index]).generate_state(1)[0])
        config = CalibratedConfig(seed=seed, home_advantage=0.0)
        home, away = (synthetic, real_team) if synthetic_home else (real_team, synthetic)
        result = CalibratedMatchSimulator(home, away, target, config).simulate(
            keep_timeline=True
        )
        sg, rg = (
            (result.home_goals, result.away_goals)
            if synthetic_home
            else (result.away_goals, result.home_goals)
        )
        distance = (
            abs(sg - global_syn_goals)
            + abs(rg - global_real_goals)
            + 0.35 * abs((sg - rg) - global_goal_diff)
            + 0.05
            * abs((result.home_shots + result.away_shots) - target.mean_shots_per_match)
        )
        candidate = (distance, result, seed, synthetic_home)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise RuntimeError("No representative match generated")
    distance, result, seed, synthetic_home = best
    payload = result.as_dict()
    if synthetic_home:
        synthetic_goals, real_goals = result.home_goals, result.away_goals
    else:
        synthetic_goals, real_goals = result.away_goals, result.home_goals
    metadata = {
        "selection_rule": (
            "deterministic medoid lineup and closest-to-aggregate match among "
            "600 prespecified candidates"
        ),
        "combination_id": chosen_combo,
        "seed": seed,
        "synthetic_home": synthetic_home,
        "distance": float(distance),
        "synthetic_goals": int(synthetic_goals),
        "real_goals": int(real_goals),
        "raw_result": payload,
    }
    timeline = pd.DataFrame(payload["timeline"])
    return metadata, timeline


def decision(
    envelope: pd.DataFrame, calibration_quality: dict[str, Any]
) -> dict[str, Any]:
    primary = envelope.loc[
        envelope["scenario"].eq("primary_top20_pooled")
    ].iloc[0]
    all_robust = bool(envelope["directionally_robust"].all())
    directions = set(envelope["robust_direction"])
    same_direction = all_robust and len(directions) == 1
    engineering_gate = bool(calibration_quality.get("engineering_gate_passed", False))
    headline_allowed = bool(same_direction and engineering_gate)
    if headline_allowed and next(iter(directions)) == "synthetic":
        headline = (
            "El equipo promedio por posición superó a las ocho versiones plausibles "
            "del mejor XI real"
        )
    elif headline_allowed and next(iter(directions)) == "real":
        headline = "El mejor XI real resistió a todas las versiones del equipo sintético"
    else:
        headline = (
            "Ocho versiones del mejor XI real revelan dónde la simulación sí es robusta "
            "y dónde no"
        )
    return {
        "status": "identified_set_simulation_complete",
        "primary_estimand": (
            "outcome-probability envelope across all eight plausible Real XIs"
        ),
        "primary_scenario": "primary_top20_pooled",
        "primary_directionally_robust": bool(primary["directionally_robust"]),
        "primary_robust_direction": primary["robust_direction"],
        "all_prespecified_sensitivities_directionally_robust": all_robust,
        "all_sensitivities_same_direction": same_direction,
        "engineering_calibration_gate_passed": engineering_gate,
        "headline_claim_allowed": headline_allowed,
        "recommended_public_headline": headline,
        "unique_real_xi_claim_allowed": False,
        "point_comparison_claim_allowed": False,
        "allowed_scientific_claim": (
            "Report the identified envelope across every plausible Real XI, calibration-bootstrap "
            "intervals, and prespecified Top-N, uncertainty, and model-response sensitivities."
        ),
    }


def methods_text(total_matches: int) -> str:
    return f"""# Métodos — simulación Synthetic XI vs. conjunto identificado de Real XI

## Estimando principal

No se selecciona retrospectivamente un único Real XI. La comparación principal es el
**envolvente de resultados** frente a las ocho alineaciones completas compatibles con la
evidencia disponible. Este tratamiento sigue la lógica de identificación parcial ante datos
faltantes: se reporta lo que queda identificado sin imponer supuestos suficientes para fabricar
un punto único.

## Diseño preespecificado antes de observar los resultados

- Synthetic XI principal: media recortada al 10% del Top 20 por cada una de las once funciones.
- Si una función contiene menos de 20 candidatos elegibles, se utiliza y declara el N real.
- Elegibilidad: perfil puntuable, rol estable, cobertura aprobada y al menos 900 minutos.
- Campo neutral: ventaja local igual a cero.
- Ocho Real XI plausibles; ninguna combinación recibe probabilidad subjetiva.
- Incertidumbre de calibración: remuestreo bootstrap de los 94 partidos FT.
- Comparaciones pareadas: mismas corrientes de semillas para todas las alineaciones y espejo
  Synthetic-local/Real-local.
- Simulaciones ejecutadas: **{total_matches:,}**.
- Semilla maestra: **{SEED}**.

## Sensibilidades

1. Top 10 y Top 30 por función.
2. Incertidumbre sintética agrupada (principal) frente a no reducirla por el tamaño del Top-N.
3. Respuesta baja y alta de la ventaja de habilidad en posesión, disparo y conversión.

## Interpretación

El motor es una simulación probabilística de eventos —posesiones, tiros y goles— calibrada con
el Mundial observado. No es tracking, física continua ni reconstrucción causal de un partido.
Una conclusión solo se considera robusta cuando mantiene dirección en las ocho alineaciones y
en todas las sensibilidades preespecificadas.

## Bases metodológicas

- Dixon y Coles (1997), modelación probabilística de marcadores de fútbol. DOI: 10.1111/1467-9876.00065.
- Gneiting, Balabdaoui y Raftery (2007), calibración y nitidez de pronósticos probabilísticos. DOI: 10.1111/j.1467-9868.2007.00587.x.
- Manski (2005), identificación parcial con datos faltantes. DOI: 10.1016/j.ijar.2004.10.006.
- Nelson y Hsu (1993), números aleatorios comunes para reducir varianza en comparaciones de simulación. DOI: 10.1287/mnsc.39.8.989.
"""


def viral_text(
    decision_payload: dict[str, Any], envelope: pd.DataFrame, total_matches: int
) -> str:
    primary = envelope.loc[
        envelope["scenario"].eq("primary_top20_pooled")
    ].iloc[0]
    return f"""# Paquete narrativo público — Synthetic XI

## Titular autorizado

**{decision_payload['recommended_public_headline']}**

## Gancho

No simulamos un solo partido contra un once elegido a conveniencia. Construimos un jugador
sintético por posición, conservamos las ocho versiones científicamente plausibles del mejor XI
real y ejecutamos **{total_matches:,}** partidos con incertidumbre de datos, calibración y modelo.

## Dato principal que debe aparecer en pantalla

- Probabilidad de victoria Synthetic XI: {primary['synthetic_win_probability_min']:.1%}–{primary['synthetic_win_probability_max']:.1%}
- Probabilidad de empate: {primary['draw_probability_min']:.1%}–{primary['draw_probability_max']:.1%}
- Probabilidad de victoria Real XI: {primary['real_win_probability_min']:.1%}–{primary['real_win_probability_max']:.1%}

## Frase metodológica breve

“Como tres posiciones reales no podían identificarse de manera única, no ocultamos la
incertidumbre: simulamos las ocho alineaciones posibles.”

## Guardrails

No decir “demostramos quién ganaría en la realidad”. No presentar el partido representativo
como observación. No esconder el intervalo entre alineaciones. La animación es una narrativa
de una realización representativa de una distribución, no evidencia de tracking.
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    players = load_players()
    real, real_profiles = real_teams(players)
    if len(real) != 8:
        raise RuntimeError(f"Expected 8 plausible Real XIs, found {len(real)}")
    max_worlds = max(int(s["worlds"]) for s in SCENARIOS)
    worlds = calibration_worlds(max_worlds)
    matches, membership, team_profiles = run_simulation(players, real, worlds)
    world, combo, envelope, scorelines = summarize(matches)

    calibration_quality: dict[str, Any] = {}
    if CALIBRATION_QUALITY.exists():
        calibration_quality = json.loads(CALIBRATION_QUALITY.read_text(encoding="utf-8"))
    decision_payload = decision(envelope, calibration_quality)
    rep_metadata, rep_timeline = representative_match(players, real, combo)

    matches.to_csv(OUT / "match_outcomes.csv.gz", index=False, compression="gzip")
    world.to_csv(OUT / "world_level_results.csv", index=False)
    combo.to_csv(OUT / "combination_results.csv", index=False)
    envelope.to_csv(OUT / "identified_outcome_envelope.csv", index=False)
    scorelines.to_csv(OUT / "scoreline_distribution.csv", index=False)
    membership.to_csv(OUT / "synthetic_avatar_membership.csv", index=False)
    team_profiles.to_csv(OUT / "team_profiles.csv", index=False)
    real_profiles.to_csv(OUT / "real_identified_set_membership.csv", index=False)
    rep_timeline.to_csv(OUT / "representative_match_timeline.csv", index=False)
    (OUT / "representative_match.json").write_text(
        json.dumps(rep_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "robustness_decision.json").write_text(
        json.dumps(decision_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total_matches = int(len(matches))
    manifest = {
        "release": "v1.0-identified-set-simulation-candidate",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.getenv("GITHUB_SHA"),
        "seed": SEED,
        "network_calls": 0,
        "provider_api_calls": 0,
        "simulation_engine": "transparent calibrated event engine v0.2",
        "primary_scenario": "primary_top20_pooled",
        "plausible_real_xis": len(real),
        "calibration_matches": observed_calibration().source_match_count,
        "bootstrap_calibration_worlds": max_worlds,
        "total_simulated_matches": total_matches,
        "scenario_design": SCENARIOS,
        "input_sha256": file_hashes(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "unique_real_xi_claim_allowed": False,
        "final_point_ranking_generated": False,
        "decision": decision_payload,
    }
    (OUT / "simulation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "METHODS_ES.md").write_text(methods_text(total_matches), encoding="utf-8")
    (OUT / "VIRAL_STORY_PACKAGE_ES.md").write_text(
        viral_text(decision_payload, envelope, total_matches), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
