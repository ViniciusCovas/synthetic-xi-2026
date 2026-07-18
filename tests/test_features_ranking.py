from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.features import aggregate_features
from synthetic_xi_2026.ranking import (
    build_avatars,
    build_experimental_lineups,
    build_real_benchmarks,
    rank_players,
)


def _rows():
    rows = []
    position_counts = {"GK": 1, "CB": 2, "FB": 2, "DM": 1, "CM": 1, "AM": 1, "W": 2, "ST": 2}
    player_id = 0
    for position, count in position_counts.items():
        for i in range(1, max(count, 5) + 1):
            player_id += 1
            rows.append(
                {
                    "fixture_id": 1,
                    "team_id": i,
                    "team_name": f"Equipo {i}",
                    "player_id": player_id,
                    "player_name": f"{position} {i}",
                    "position_group": position,
                    "classification_rule": "test",
                    "formation": "4-3-3",
                    "minutes": 180 + i * 30,
                    "provider_rating": 6 + i / 10,
                    "shots": i + 1,
                    "shots_on": i,
                    "goals": i / 3,
                    "goals_conceded": 1 if position == "GK" else 0,
                    "assists": 1,
                    "saves": i if position == "GK" else 0,
                    "passes": 20 + i,
                    "key_passes": i,
                    "pass_accuracy_sum": 80 * (180 + i * 30),
                    "tackles": i,
                    "blocks": i,
                    "interceptions": i,
                    "duels": 10,
                    "duels_won": 5 + i / 2,
                    "dribbles_attempted": 2,
                    "dribbles_completed": 1,
                    "fouls_drawn": i,
                    "fouls_committed": 1,
                    "yellow_cards": 0,
                    "red_cards": 0,
                }
            )
    return rows


def test_ranking_avatars_benchmarks_and_eleven():
    features = aggregate_features(pd.DataFrame(_rows()))
    ranked = rank_players(features, minimum_minutes=180, reliability_prior_minutes=180)
    avatars, metrics, members = build_avatars(
        ranked, requested_top_n=20, seed=1, trim_fraction=0.10
    )
    benchmarks = build_real_benchmarks(ranked)
    synthetic_xi, real_xi = build_experimental_lineups(ranked, avatars)

    assert len(avatars) == 8
    assert len(benchmarks) == 8
    assert len(synthetic_xi) == 11
    assert len(real_xi) == 11
    assert synthetic_xi["available"].all()
    assert real_xi["available"].all()
    assert set(real_xi["slot"]) == {"GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"}
    assert avatars["actual_n"].max() == 5
    assert not metrics.empty
    assert not members.empty
