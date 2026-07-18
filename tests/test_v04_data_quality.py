from __future__ import annotations

import pandas as pd

from synthetic_xi_2026.features_v04 import accurate_passes, aggregate_features
from synthetic_xi_2026.pipeline_v04 import select_stable_primary_roles


def test_accurate_passes_supports_counts_and_percentages() -> None:
    assert accurate_passes(40, 32) == 32
    assert accurate_passes(40, "80%") == 32
    assert accurate_passes(40, 80) == 32


def test_pass_accuracy_is_accurate_over_total() -> None:
    frame = pd.DataFrame(
        [
            {
                "player_id": 1,
                "player_name": "Jugador",
                "team_id": 1,
                "team_name": "Equipo",
                "position_group": "CM",
                "minutes": 90.0,
                "provider_rating": 7.0,
                "shots": 0.0,
                "shots_on": 0.0,
                "goals": 0.0,
                "goals_conceded": 0.0,
                "assists": 0.0,
                "saves": 0.0,
                "passes": 40.0,
                "passes_accurate": 32.0,
                "key_passes": 0.0,
                "tackles": 0.0,
                "blocks": 0.0,
                "interceptions": 0.0,
                "duels": 0.0,
                "duels_won": 0.0,
                "dribbles_attempted": 0.0,
                "dribbles_completed": 0.0,
                "fouls_drawn": 0.0,
                "fouls_committed": 0.0,
                "yellow_cards": 0.0,
                "red_cards": 0.0,
            }
        ]
    )
    result = aggregate_features(frame)
    assert result.iloc[0]["pass_accuracy"] == 80.0


def test_primary_role_requires_sixty_percent_share() -> None:
    examples = {
        1: {
            "CB": {"position_group": "CB", "classification_rule": "exacta"},
            "FB": {"position_group": "FB", "classification_rule": "exacta"},
        },
        2: {
            "CM": {"position_group": "CM", "classification_rule": "exacta"},
            "DM": {"position_group": "DM", "classification_rule": "exacta"},
        },
    }
    selected, ambiguous = select_stable_primary_roles(
        {1: {"CB": 180.0, "FB": 60.0}, 2: {"CM": 90.0, "DM": 90.0}},
        examples,
        minimum_share=0.60,
    )
    assert selected[1]["position_group"] == "CB"
    assert selected[1]["role_share"] == 0.75
    assert 2 not in selected
    assert ambiguous == 1
