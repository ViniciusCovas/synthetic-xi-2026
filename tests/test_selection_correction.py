from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.features_v04 import aggregate_features
from synthetic_xi_2026.ranking import build_avatars, build_experimental_lineups, rank_players


def _match_row(player_id: int, name: str, fixture_id: int, minutes: float, group: str = "GK") -> dict:
    return {
        "fixture_id": fixture_id,
        "team_id": 31,
        "team_name": "Morocco",
        "player_id": player_id,
        "player_name": name,
        "position_group": group,
        "classification_rule": "test",
        "minutes": minutes,
        "provider_rating": 7.0,
        "shots": 0.0, "shots_on": 0.0, "goals": 0.0, "goals_conceded": 1.0,
        "assists": 0.0, "saves": 3.0, "passes": 20.0, "passes_accurate": 16.0,
        "key_passes": 0.0, "tackles": 0.0, "blocks": 0.0, "interceptions": 0.0,
        "duels": 2.0, "duels_won": 1.0, "dribbles_attempted": 0.0,
        "dribbles_completed": 0.0, "fouls_drawn": 0.0, "fouls_committed": 0.0,
        "yellow_cards": 0.0, "red_cards": 0.0,
    }


def test_name_variants_merge_into_single_identity() -> None:
    frame = pd.DataFrame(
        [
            _match_row(2701, "Bono", 1, 90.0),
            _match_row(2701, "Yassine Bounou", 2, 120.0),
            _match_row(2701, "Bono", 3, 90.0),
        ]
    )
    result = aggregate_features(frame)
    assert len(result) == 1
    assert result.iloc[0]["minutes"] == 300.0
    # Nombre canónico: el del partido con más minutos.
    assert result.iloc[0]["player_name"] == "Yassine Bounou"


def _ranked_pair_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    position_counts = {"GK": 1, "CB": 2, "FB": 2, "DM": 1, "CM": 1, "AM": 1, "W": 2, "ST": 1}
    player_id = 0
    for group, count in position_counts.items():
        for i in range(1, max(count, 3) + 1):
            player_id += 1
            row = _match_row(player_id, f"{group} {i}", i, 200.0 + i * 40, group)
            row["team_id"] = i
            row["team_name"] = f"Equipo {i}"
            row["goals"] = i / 2
            row["passes"] = 20.0 + 5 * i
            row["passes_accurate"] = 16.0 + 4 * i
            rows.append(row)
    features = aggregate_features(pd.DataFrame(rows))
    ranked = rank_players(features, minimum_minutes=180, reliability_prior_minutes=180)
    avatars, _, _ = build_avatars(ranked, requested_top_n=20, seed=1)
    return ranked, avatars


def test_side_evidence_reorders_paired_slots() -> None:
    ranked, avatars = _ranked_pair_fixture()
    fb_pool = ranked[ranked["position_group"] == "FB"].sort_values(
        ["position_rank", "minutes"]
    )
    best_fb = int(fb_pool.iloc[0]["player_id"])
    second_fb = int(fb_pool.iloc[1]["player_id"])

    # El mejor FB juega por la izquierda: debe ocupar LB, no RB.
    sides = {best_fb: "L", second_fb: "R"}
    _, real_xi = build_experimental_lineups(ranked, avatars, sides)
    by_slot = real_xi.set_index("slot")
    assert int(by_slot.loc["LB", "entity_id"]) == best_fb
    assert int(by_slot.loc["RB", "entity_id"]) == second_fb
    assert "evidencia" in by_slot.loc["LB", "side_assignment_rule"]


def test_without_side_evidence_rank_order_is_preserved() -> None:
    ranked, avatars = _ranked_pair_fixture()
    _, real_xi = build_experimental_lineups(ranked, avatars, None)
    by_slot = real_xi.set_index("slot")
    fb_pool = ranked[ranked["position_group"] == "FB"].sort_values(
        ["position_rank", "minutes"]
    )
    assert int(by_slot.loc["RB", "entity_id"]) == int(fb_pool.iloc[0]["player_id"])
    assert int(by_slot.loc["LB", "entity_id"]) == int(fb_pool.iloc[1]["player_id"])
    # Once completo y sin repetidos.
    assert len(real_xi) == 11
    assert real_xi["entity_id"].nunique() == 11
