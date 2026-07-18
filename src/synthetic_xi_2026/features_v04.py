"""Audited v0.4 player-match feature engineering."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.replace("%", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def accurate_passes(total_value: Any, accuracy_value: Any) -> float:
    """Return an accurate-pass count from count or percentage representations."""

    total = number(total_value)
    if total <= 0:
        return 0.0
    if isinstance(accuracy_value, str) and "%" in accuracy_value:
        return total * number(accuracy_value) / 100.0
    raw = number(accuracy_value)
    if raw <= 0:
        return 0.0
    if raw <= total:
        return raw
    if raw <= 100:
        return total * raw / 100.0
    return min(raw, total)


def player_match_minutes(player_entry: dict[str, Any]) -> float:
    statistics = player_entry.get("statistics") or []
    if not statistics:
        return 0.0
    games = (statistics[0] or {}).get("games") or {}
    return number(games.get("minutes"))


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
    minutes = number(games.get("minutes"))
    if minutes <= 0 or player.get("id") is None:
        return None

    shots = stat.get("shots") or {}
    goals = stat.get("goals") or {}
    passes = stat.get("passes") or {}
    tackles = stat.get("tackles") or {}
    duels = stat.get("duels") or {}
    dribbles = stat.get("dribbles") or {}
    fouls = stat.get("fouls") or {}
    cards = stat.get("cards") or {}
    total_passes = number(passes.get("total"))

    return {
        "fixture_id": fixture_id,
        "team_id": team_id,
        "team_name": team_name,
        "player_id": int(player["id"]),
        "player_name": player.get("name"),
        "position_group": role["position_group"],
        "classification_rule": role["classification_rule"],
        "role_source": role.get("role_source"),
        "role_share": role.get("role_share"),
        "precise_role_minutes": role.get("precise_role_minutes"),
        "formation": role.get("formation"),
        "minutes": minutes,
        "provider_rating": number(games.get("rating")),
        "shots": number(shots.get("total")),
        "shots_on": number(shots.get("on")),
        "goals": number(goals.get("total")),
        "goals_conceded": number(goals.get("conceded")),
        "assists": number(goals.get("assists")),
        "saves": number(goals.get("saves")),
        "passes": total_passes,
        "passes_accurate": accurate_passes(total_passes, passes.get("accuracy")),
        "key_passes": number(passes.get("key")),
        "tackles": number(tackles.get("total")),
        "blocks": number(tackles.get("blocks")),
        "interceptions": number(tackles.get("interceptions")),
        "duels": number(duels.get("total")),
        "duels_won": number(duels.get("won")),
        "dribbles_attempted": number(dribbles.get("attempts")),
        "dribbles_completed": number(dribbles.get("success")),
        "fouls_drawn": number(fouls.get("drawn")),
        "fouls_committed": number(fouls.get("committed")),
        "yellow_cards": number(cards.get("yellow")),
        "red_cards": number(cards.get("red")),
    }


def aggregate_features(player_matches: pd.DataFrame) -> pd.DataFrame:
    if player_matches.empty:
        return pd.DataFrame()
    count_cols = [
        "minutes", "shots", "shots_on", "goals", "goals_conceded", "assists",
        "saves", "passes", "passes_accurate", "key_passes", "tackles", "blocks",
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
    for col in [
        "shots", "goals", "goals_conceded", "assists", "saves", "passes",
        "key_passes", "tackles", "blocks", "interceptions", "duels",
        "dribbles_completed", "fouls_drawn", "fouls_committed",
    ]:
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
        agg["passes"] > 0, 100.0 * agg["passes_accurate"] / agg["passes"], 0.0
    )
    return agg.replace([np.inf, -np.inf], 0).fillna(0)
