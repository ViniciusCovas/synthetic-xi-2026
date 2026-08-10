"""Equipes para o motor calibrado a partir da seleção anual v0.5.

Real Annual XI e avatares sintéticos em níveis, com incerteza de amostragem
por partido pareada entre as duas equipes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile

ANNUAL_DIR = Path("data/annual_v05")

SLOT_TO_ENGINE_ROLE = {
    "GK": "GK", "RCB": "CB1", "LCB": "CB2", "RB": "FB1", "LB": "FB2",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W1", "LW": "W2", "ST": "ST",
}
ENGINE_ROLE_TO_GROUP = {
    "GK": "GK", "CB1": "CB", "CB2": "CB", "FB1": "FB", "FB2": "FB",
    "DM": "DM", "CM": "CM", "AM": "AM", "W1": "W", "W2": "W", "ST": "ST",
}
DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)


def build_real_annual_team() -> TeamProfile:
    table = pd.read_csv(ANNUAL_DIR / "annual_table_primary.csv").set_index(
        "player_id", drop=False
    )
    xi = pd.read_csv(ANNUAL_DIR / "real_annual_xi.csv")
    players = []
    for _, row in xi.iterrows():
        source = table.loc[int(row["player_id"])]
        players.append(
            PlayerProfile(
                player_id=str(int(row["player_id"])),
                name=str(row["player_name"]),
                role=SLOT_TO_ENGINE_ROLE[str(row["slot"])],
                minutes=float(source["minutes_num"]),
                overall=float(source["overall"]),
                uncertainty=float(source["uncertainty"]),
                synthetic=False,
                **{d: float(source[d]) for d in DIMENSIONS},
            )
        )
    order = {role: i for i, role in enumerate(ROLE_ORDER)}
    players.sort(key=lambda p: order[p.role])
    return TeamProfile(name="Real Annual XI", players=tuple(players))


def build_synthetic_tier_team(tier: str) -> TeamProfile:
    avatars = pd.read_csv(ANNUAL_DIR / "synthetic_tiers.csv")
    avatars = avatars[avatars["tier"] == tier].set_index("position_group")
    players = []
    for engine_role in ROLE_ORDER:
        group = ENGINE_ROLE_TO_GROUP[engine_role]
        row = avatars.loc[group]
        players.append(
            PlayerProfile(
                player_id=str(row["avatar_id"]),
                name=str(row["avatar_id"]),
                role=engine_role,
                minutes=900.0,
                overall=float(row["overall"]),
                uncertainty=float(row["uncertainty"]),
                synthetic=True,
                **{d: float(row[d]) for d in DIMENSIONS},
            )
        )
    return TeamProfile(name=f"Synthetic XI [{tier}]", players=tuple(players))
