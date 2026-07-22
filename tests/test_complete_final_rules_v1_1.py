from dataclasses import replace

from simulator.calibrated_core import CalibrationTargets
from simulator.complete_final import CompleteFinalSimulator, FinalConfig
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
                finishing=base + (0.04 if role in {"ST", "W1", "W2"} else -0.03),
                defending=base + (0.05 if role in {"CB1", "CB2", "DM"} else -0.03),
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


def test_v1_1_uses_batch_substitutions_without_exceeding_windows():
    combined_regulation_substitutions = []
    batch_examples = 0
    for seed in range(40):
        result = CompleteFinalSimulator(
            HOME,
            AWAY,
            TARGETS,
            replace(FinalConfig(), seed=seed),
        ).simulate(True)
        extra_time_played = result.decided_by in {"extra_time", "penalties"}
        for stats in (result.home_stats, result.away_stats):
            assert stats["substitutions"] <= (6 if extra_time_played else 5)
            assert stats["substitution_windows"] <= 3
            assert stats["extra_time_windows"] <= 1
            if stats["substitutions"] > stats["substitution_windows"] + stats["extra_time_windows"]:
                batch_examples += 1
        if not extra_time_played:
            combined_regulation_substitutions.append(
                result.home_stats["substitutions"] + result.away_stats["substitutions"]
            )

    assert batch_examples > 0
    assert combined_regulation_substitutions
    assert sum(combined_regulation_substitutions) / len(combined_regulation_substitutions) >= 9.0
