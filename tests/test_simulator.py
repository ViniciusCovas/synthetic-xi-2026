from __future__ import annotations

from simulator.engine import (
    MatchSimulator,
    PlayerProfile,
    SimulationConfig,
    TeamProfile,
    simulate_many,
)

ROLES = ("GK", "CB1", "CB2", "FB1", "FB2", "DM", "CM", "AM", "W1", "W2", "ST")


def make_team(name: str, strength: float) -> TeamProfile:
    players = []
    for role in ROLES:
        players.append(
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
        )
    return TeamProfile(name=name, players=tuple(players))


def test_single_match_is_reproducible() -> None:
    a = make_team("A", 0.65)
    b = make_team("B", 0.55)
    config = SimulationConfig(seed=77)
    first = MatchSimulator(a, b, config).simulate().as_dict()
    second = MatchSimulator(a, b, config).simulate().as_dict()
    assert first == second


def test_stronger_team_wins_more_often() -> None:
    strong = make_team("Strong", 0.78)
    weak = make_team("Weak", 0.38)
    result = simulate_many(strong, weak, simulations=400, seed=42)
    assert result["home_win_probability"] > result["away_win_probability"]
    assert result["mean_home_goals"] > result["mean_away_goals"]


def test_probabilities_sum_to_one() -> None:
    a = make_team("A", 0.60)
    b = make_team("B", 0.60)
    result = simulate_many(a, b, simulations=100, seed=9)
    total = (
        result["home_win_probability"]
        + result["draw_probability"]
        + result["away_win_probability"]
    )
    assert abs(total - 1.0) < 1e-12
