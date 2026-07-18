from __future__ import annotations

from simulator.calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibrationTargets,
)
from simulator.calibrated_monte_carlo import simulate_many_calibrated
from simulator.engine import PlayerProfile, TeamProfile

ROLES = (
    "GK",
    "CB1",
    "CB2",
    "FB1",
    "FB2",
    "DM",
    "CM",
    "AM",
    "W1",
    "W2",
    "ST",
)
TARGETS = CalibrationTargets(
    source_match_count=100,
    mean_goals_per_match=2.7,
    mean_shots_per_match=25.0,
    mean_shots_on_target_per_match=8.5,
    zero_zero_rate=0.08,
    home_win_rate=0.40,
    draw_rate=0.25,
    away_win_rate=0.35,
    model_possessions_per_match=104.0,
)


def make_team(name: str, strength: float) -> TeamProfile:
    return TeamProfile(
        name=name,
        players=tuple(
            PlayerProfile(
                player_id=f"{name}-{role}",
                name=f"{name} {role}",
                role=role,
                minutes=2500,
                overall=strength,
                build_up=strength,
                progression=strength,
                creation=strength,
                finishing=strength,
                defending=strength,
                duels=strength,
                retention=strength,
                goalkeeping=strength,
                uncertainty=0.01,
            )
            for role in ROLES
        ),
    )


def test_calibrated_match_is_reproducible() -> None:
    home = make_team("A", 0.60)
    away = make_team("B", 0.60)
    config = CalibratedConfig(seed=4)
    first = CalibratedMatchSimulator(home, away, TARGETS, config).simulate().as_dict()
    second = CalibratedMatchSimulator(home, away, TARGETS, config).simulate().as_dict()
    assert first == second


def test_neutral_teams_approximate_calibration() -> None:
    result = simulate_many_calibrated(
        make_team("A", 0.60),
        make_team("B", 0.60),
        TARGETS,
        simulations=2_000,
        seed=9,
    )
    assert 20 < result["mean_total_shots"] < 30
    assert 1.8 < result["mean_total_goals"] < 3.6
    assert 6 < result["mean_total_shots_on_target"] < 11
    total = (
        result["home_win_probability"]
        + result["draw_probability"]
        + result["away_win_probability"]
    )
    assert abs(total - 1.0) < 1e-12


def test_stronger_team_has_advantage() -> None:
    result = simulate_many_calibrated(
        make_team("Strong", 0.80),
        make_team("Weak", 0.35),
        TARGETS,
        simulations=800,
        seed=8,
    )
    assert result["home_win_probability"] > result["away_win_probability"]
    assert result["mean_home_goals"] > result["mean_away_goals"]
