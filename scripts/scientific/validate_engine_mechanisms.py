#!/usr/bin/env python3
"""Deterministic structural tests for the calibrated event engine.

These tests do not establish empirical predictive validity. They verify that controlled
changes in football-relevant abilities move simulated mechanisms in the preregistered
direction while all other team inputs and random seeds are held constant.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from simulator.calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibrationTargets,
)
from simulator.engine import PlayerProfile, TeamProfile, ROLE_ORDER

OUT = Path("data/audits/engine_validation_v1")
SIMULATIONS = 4000
MASTER_SEED = 20260720


def player(role: str) -> PlayerProfile:
    return PlayerProfile(
        player_id=f"CONTROL-{role}",
        name=f"Control {role}",
        role=role,
        minutes=3000.0,
        overall=0.50,
        build_up=0.50,
        progression=0.50,
        creation=0.50,
        finishing=0.50,
        defending=0.50,
        duels=0.50,
        retention=0.50,
        goalkeeping=0.50,
        uncertainty=0.015,
        synthetic=True,
    )


def team(name: str) -> TeamProfile:
    return TeamProfile(name=name, players=tuple(player(role) for role in ROLE_ORDER))


def modify_team(base: TeamProfile, changes: dict[str, dict[str, float]], name: str) -> TeamProfile:
    players = []
    for item in base.players:
        updates = changes.get(item.role, {})
        players.append(replace(item, **updates))
    return TeamProfile(
        name=name,
        players=tuple(players),
        tempo=base.tempo,
        press=base.press,
        directness=base.directness,
    )


def simulate_pair(
    home_a: TeamProfile,
    away_a: TeamProfile,
    home_b: TeamProfile,
    away_b: TeamProfile,
    targets: CalibrationTargets,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    a_goals = []
    b_goals = []
    a_shots = []
    b_shots = []
    a_xg = []
    b_xg = []
    for _ in range(SIMULATIONS):
        match_seed = int(rng.integers(0, 2**32 - 1))
        config = CalibratedConfig(seed=match_seed, home_advantage=0.0)
        first = CalibratedMatchSimulator(home_a, away_a, targets, config).simulate(False)
        second = CalibratedMatchSimulator(home_b, away_b, targets, config).simulate(False)
        a_goals.append(first.home_goals)
        b_goals.append(second.home_goals)
        a_shots.append(first.home_shots)
        b_shots.append(second.home_shots)
        a_xg.append(first.home_xg)
        b_xg.append(second.home_xg)
    goal_delta = np.asarray(b_goals, dtype=float) - np.asarray(a_goals, dtype=float)
    shot_delta = np.asarray(b_shots, dtype=float) - np.asarray(a_shots, dtype=float)
    xg_delta = np.asarray(b_xg, dtype=float) - np.asarray(a_xg, dtype=float)
    return {
        "mean_goal_delta": float(goal_delta.mean()),
        "mean_shot_delta": float(shot_delta.mean()),
        "mean_xg_delta": float(xg_delta.mean()),
        "goal_delta_se": float(goal_delta.std(ddof=1) / np.sqrt(len(goal_delta))),
        "shot_delta_se": float(shot_delta.std(ddof=1) / np.sqrt(len(shot_delta))),
        "xg_delta_se": float(xg_delta.std(ddof=1) / np.sqrt(len(xg_delta))),
    }


def lower95(mean: float, se: float) -> float:
    return float(mean - 1.96 * se)


def upper95(mean: float, se: float) -> float:
    return float(mean + 1.96 * se)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = CalibrationTargets(
        source_match_count=94,
        mean_goals_per_match=2.9148936170212765,
        mean_shots_per_match=18.094871004214205,
        mean_shots_on_target_per_match=8.378558947476618,
        zero_zero_rate=0.07446808510638298,
        home_win_rate=0.40,
        draw_rate=0.25,
        away_win_rate=0.35,
    )
    home = team("Controlled home")
    away = team("Controlled away")

    finishing = modify_team(
        home,
        {"ST": {"finishing": 0.80, "overall": 0.60}},
        "Higher finishing",
    )
    creation = modify_team(
        home,
        {
            "AM": {"creation": 0.80, "progression": 0.72, "overall": 0.60},
            "W1": {"creation": 0.68, "progression": 0.72, "overall": 0.58},
            "W2": {"creation": 0.68, "progression": 0.72, "overall": 0.58},
        },
        "Higher creation",
    )
    goalkeeper = modify_team(
        away,
        {"GK": {"goalkeeping": 0.80, "overall": 0.62}},
        "Higher goalkeeper",
    )
    defence = modify_team(
        away,
        {
            role: {"defending": 0.75, "duels": 0.70, "overall": 0.60}
            for role in ("CB1", "CB2", "FB1", "FB2", "DM")
        },
        "Higher defence",
    )

    finishing_result = simulate_pair(home, away, finishing, away, targets, MASTER_SEED + 1)
    creation_result = simulate_pair(home, away, creation, away, targets, MASTER_SEED + 2)
    goalkeeper_result = simulate_pair(home, away, home, goalkeeper, targets, MASTER_SEED + 3)
    defence_result = simulate_pair(home, away, home, defence, targets, MASTER_SEED + 4)

    checks = {
        "finishing_increases_goals": lower95(
            finishing_result["mean_goal_delta"], finishing_result["goal_delta_se"]
        ) > 0,
        "creation_increases_xg": lower95(
            creation_result["mean_xg_delta"], creation_result["xg_delta_se"]
        ) > 0,
        "creation_does_not_reduce_shots": lower95(
            creation_result["mean_shot_delta"], creation_result["shot_delta_se"]
        ) >= -0.05,
        "goalkeeper_reduces_opponent_goals": upper95(
            goalkeeper_result["mean_goal_delta"], goalkeeper_result["goal_delta_se"]
        ) < 0,
        "defence_reduces_opponent_xg": upper95(
            defence_result["mean_xg_delta"], defence_result["xg_delta_se"]
        ) < 0,
    }
    passed = all(checks.values())
    status = {
        "status": "controlled_event_mechanisms_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulations_per_comparison": SIMULATIONS,
        "master_seed": MASTER_SEED,
        "common_random_numbers": True,
        "tests": {
            "finishing": finishing_result,
            "creation": creation_result,
            "goalkeeper": goalkeeper_result,
            "defence": defence_result,
        },
        "checks": checks,
        "mechanism_validation_passed": passed,
        "claim_scope": (
            "structural monotonicity of coded mechanisms under controlled profiles; "
            "not standalone empirical validation"
        ),
    }
    (OUT / "mechanism_validation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
