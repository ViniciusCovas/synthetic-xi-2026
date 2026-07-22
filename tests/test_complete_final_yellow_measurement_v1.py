from dataclasses import replace

from simulator.calibrated_core import CalibrationTargets
from simulator.complete_final import CompleteFinalSimulator, FinalConfig
from simulator.complete_final_monte_carlo import simulate_complete_finals
from simulator.engine import ROLE_ORDER, PlayerProfile, TeamProfile


def team(name: str, synthetic: bool) -> TeamProfile:
    players = []
    for role in ROLE_ORDER:
        base = 0.60
        players.append(
            PlayerProfile(
                player_id=f"{name}-{role}",
                name=f"{name} {role}",
                role=role,
                minutes=900,
                overall=base,
                build_up=base,
                progression=base,
                creation=base,
                finishing=base,
                defending=base,
                duels=base,
                retention=base,
                goalkeeping=0.72 if role == "GK" else 0.20,
                uncertainty=0.025,
                synthetic=synthetic,
            )
        )
    return TeamProfile(name, tuple(players), tempo=0.55, press=0.54, directness=0.51)


TARGETS = CalibrationTargets(64, 2.65, 25.0, 8.7, 0.075, 0.39, 0.26, 0.35, 104.0)
HOME = team("Neutral A", True)
AWAY = team("Neutral B", False)


def test_yellow_measurement_separates_second_yellow_without_changing_reds():
    second_yellows = 0
    for seed in range(120):
        result = CompleteFinalSimulator(
            HOME,
            AWAY,
            TARGETS,
            replace(FinalConfig(), seed=seed),
        ).simulate(True)
        for stats in (result.home_stats, result.away_stats):
            assert stats["yellows"] == stats["benchmark_comparable_yellows"] + stats["second_yellows"]
            assert stats["second_yellows"] <= stats["reds"]
            second_yellows += stats["second_yellows"]
    assert second_yellows > 0


def test_monte_carlo_preserves_raw_and_comparable_yellow_means():
    summary = simulate_complete_finals(
        HOME,
        AWAY,
        TARGETS,
        simulations=200,
        seed=20260741,
        config=FinalConfig(),
        audit_sample_size=20,
    )
    assert summary["mean_total_yellows_raw"] >= summary["mean_total_yellows"]
    assert abs(
        summary["mean_total_yellows_raw"]
        - summary["mean_total_yellows"]
        - summary["mean_total_second_yellows"]
    ) < 1e-9
