"""Flatten provider player-match statistics and construct interpretable features."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.replace("%", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def flatten_player_match(
    fixture_id: int,
    team_id: int | None,
    team_name: str | None,
    player_entry: dict[str, Any],
    role: dict[str, Any],
) -> dict[str, Any] | None:
    player = player_entry.get("player") or {}
    statistics = player_entry.get("statistics") or []
    if not statistics:
        return None
    stat = statistics[0] or {}
    games = stat.get("games") or {}
    minutes = _number(games.get("minutes"))
    if minutes <= 0:
        return None

    shots = stat.get("shots") or {}
    goals = stat.get("goals") or {}
    passes = stat.get("passes") or {}
    tackles = stat.get("tackles") or {}
    duels = stat.get("duels") or {}
    dribbles = stat.get("dribbles") or {}
    fouls = stat.get("fouls") or {}
    cards = stat.get("cards") or {}

    return {
        "fixture_id": fixture_id,
        "team_id": team_id,
        "team_name": team_name,
        "player_id": int(player.get("id")),
        "player_name": player.get("name"),
        "position_group": role["position_group"],
        "classification_rule": role["classification_rule"],
        "formation": role.get("formation"),
        "minutes": minutes,
        "provider_rating": _number(games.get("rating")),
        "shots": _number(shots.get("total")),
        "shots_on": _number(shots.get("on")),
        "goals": _number(goals.get("total")),
        "goals_conceded": _number(goals.get("conceded")),
        "assists": _number(goals.get("assists")),
        "saves": _number(goals.get("saves")),
        "passes": _number(passes.get("total")),
        "key_passes": _number(passes.get("key")),
        "pass_accuracy_sum": _number(passes.get("accuracy")) * minutes,
        "tackles": _number(tackles.get("total")),
        "blocks": _number(tackles.get("blocks")),
        "interceptions": _number(tackles.get("interceptions")),
        "duels": _number(duels.get("total")),
        "duels_won": _number(duels.get("won")),
        "dribbles_attempted": _number(dribbles.get("attempts")),
        "dribbles_completed": _number(dribbles.get("success")),
        "fouls_drawn": _number(fouls.get("drawn")),
        "fouls_committed": _number(fouls.get("committed")),
        "yellow_cards": _number(cards.get("yellow")),
        "red_cards": _number(cards.get("red")),
    }


def aggregate_features(player_matches: pd.DataFrame) -> pd.DataFrame:
    if player_matches.empty:
        return pd.DataFrame()
    count_cols = [
        "minutes", "shots", "shots_on", "goals", "goals_conceded", "assists",
        "saves", "passes", "key_passes", "pass_accuracy_sum", "tackles", "blocks",
        "interceptions", "duels", "duels_won", "dribbles_attempted",
        "dribbles_completed", "fouls_drawn", "fouls_committed", "yellow_cards",
        "red_cards",
    ]
    agg = (
        player_matches.groupby(
            ["player_id", "player_name", "team_id", "team_name", "position_group"],
            as_index=False,
        )[count_cols]
        .sum()
    )
    rating = (
        player_matches[player_matches["provider_rating"] > 0]
        .groupby("player_id", as_index=False)["provider_rating"]
        .mean()
        .rename(columns={"provider_rating": "provider_rating_mean"})
    )
    agg = agg.merge(rating, on="player_id", how="left")
    factor = np.where(agg["minutes"] > 0, 90.0 / agg["minutes"], 0.0)
    per90 = [
        "shots", "goals", "goals_conceded", "assists", "saves", "passes",
        "key_passes", "tackles", "blocks", "interceptions", "duels",
        "dribbles_completed", "fouls_drawn", "fouls_committed",
    ]
    for col in per90:
        agg[f"{col}_p90"] = agg[col] * factor
    agg["cards_p90"] = (agg["yellow_cards"] + 2 * agg["red_cards"]) * factor
    agg["shots_on_target_rate"] = np.where(
        agg["shots"] > 0, agg["shots_on"] / agg["shots"], 0.0
    )
    agg["duel_win_rate"] = np.where(
        agg["duels"] > 0, agg["duels_won"] / agg["duels"], 0.0
    )
    agg["dribble_success_rate"] = np.where(
        agg["dribbles_attempted"] > 0,
        agg["dribbles_completed"] / agg["dribbles_attempted"],
        0.0,
    )
    agg["pass_accuracy"] = np.where(
        agg["minutes"] > 0, agg["pass_accuracy_sum"] / agg["minutes"], 0.0
    )
    return agg.replace([np.inf, -np.inf], 0).fillna(0)
