"""Especificación pre-registrada, métricas posicionales y fuente de datos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

API_BASE: Final = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE_ID: Final = 1
WORLD_CUP_SEASON: Final = 2026
COMPLETED_STATUSES: Final = {"FT", "AET", "PEN"}
POSITION_ORDER: Final = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]

# Once experimental 4-3-3 funcional: 1+2+2+1+1+1+2+1 = 11.
XI_SLOTS: Final[list[dict[str, object]]] = [
    {"slot": "GK", "position_group": "GK", "ordinal": 1},
    {"slot": "RB", "position_group": "FB", "ordinal": 1},
    {"slot": "RCB", "position_group": "CB", "ordinal": 1},
    {"slot": "LCB", "position_group": "CB", "ordinal": 2},
    {"slot": "LB", "position_group": "FB", "ordinal": 2},
    {"slot": "DM", "position_group": "DM", "ordinal": 1},
    {"slot": "CM", "position_group": "CM", "ordinal": 1},
    {"slot": "AM", "position_group": "AM", "ordinal": 1},
    {"slot": "RW", "position_group": "W", "ordinal": 1},
    {"slot": "LW", "position_group": "W", "ordinal": 2},
    {"slot": "ST", "position_group": "ST", "ordinal": 1},
]

# Solo estadísticas observables entran en el índice central.
# La calificación opaca del proveedor se conserva solo para validación convergente.
POSITION_METRICS: Final[dict[str, dict[str, int]]] = {
    "GK": {
        "saves_p90": 1,
        "goals_conceded_p90": -1,
        "pass_accuracy": 1,
        "passes_p90": 1,
    },
    "CB": {
        "interceptions_p90": 1,
        "tackles_p90": 1,
        "blocks_p90": 1,
        "duel_win_rate": 1,
        "pass_accuracy": 1,
        "passes_p90": 1,
        "cards_p90": -1,
    },
    "FB": {
        "interceptions_p90": 1,
        "tackles_p90": 1,
        "duel_win_rate": 1,
        "key_passes_p90": 1,
        "assists_p90": 1,
        "dribbles_completed_p90": 1,
        "pass_accuracy": 1,
    },
    "DM": {
        "interceptions_p90": 1,
        "tackles_p90": 1,
        "duel_win_rate": 1,
        "passes_p90": 1,
        "pass_accuracy": 1,
        "key_passes_p90": 1,
        "cards_p90": -1,
    },
    "CM": {
        "passes_p90": 1,
        "pass_accuracy": 1,
        "key_passes_p90": 1,
        "assists_p90": 1,
        "dribbles_completed_p90": 1,
        "tackles_p90": 1,
        "interceptions_p90": 1,
    },
    "AM": {
        "goals_p90": 1,
        "assists_p90": 1,
        "shots_p90": 1,
        "shots_on_target_rate": 1,
        "key_passes_p90": 1,
        "dribbles_completed_p90": 1,
        "pass_accuracy": 1,
    },
    "W": {
        "goals_p90": 1,
        "assists_p90": 1,
        "shots_on_target_rate": 1,
        "key_passes_p90": 1,
        "dribbles_completed_p90": 1,
        "dribble_success_rate": 1,
        "duel_win_rate": 1,
    },
    "ST": {
        "goals_p90": 1,
        "assists_p90": 1,
        "shots_p90": 1,
        "shots_on_target_rate": 1,
        "key_passes_p90": 1,
        "duel_win_rate": 1,
        "fouls_drawn_p90": 1,
    },
}


@dataclass(frozen=True)
class StudySpec:
    league_id: int = WORLD_CUP_LEAGUE_ID
    season: int = WORLD_CUP_SEASON
    competition_name: str = "Copa Mundial de la FIFA 2026"
    requested_top_n: int = 20
    minimum_minutes: float = 180.0
    reliability_prior_minutes: float = 180.0
    trim_fraction: float = 0.10
    seed: int = 20260718
