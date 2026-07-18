"""Build exploratory role profiles and two XI teams from partial annual data."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile

TOTALS_PATH = Path("data/model_readiness/partial_annual_current_totals.csv")
ROLE_PATH = Path("data/model_readiness/partial_role_evidence.csv")

NUMERIC_METRICS = (
    "minutes_num", "shots_total", "shots_on", "goals_total", "assists", "saves",
    "passes_total", "passes_completed", "passes_key", "tackles_total", "blocks",
    "interceptions", "duels_total", "duels_won", "dribbles_attempts",
    "dribbles_success", "fouls_drawn", "fouls_committed",
)


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan)).fillna(0.0)


def _robust_unit(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    median = numeric.median()
    scale = max(float(numeric.quantile(0.75) - numeric.quantile(0.25)), 1e-9)
    z = (numeric - median) / scale
    return (1.0 / (1.0 + np.exp(-z.clip(-8, 8)))).fillna(0.5)


def _canonicalize(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["player_id", "minutes_num"], ascending=[True, False])
    sum_columns = [
        "fixtures", "starts", "minutes_num", "shots_total", "shots_on", "goals_total",
        "assists", "saves", "passes_total", "passes_completed", "passes_key",
        "tackles_total", "blocks", "interceptions", "duels_total", "duels_won",
        "dribbles_attempts", "dribbles_success", "fouls_drawn", "fouls_committed",
        "yellow", "red",
    ]
    aggregation: dict[str, Any] = {
        column: "sum" for column in sum_columns if column in frame.columns
    }
    aggregation["player_name"] = "first"
    if "window" in frame.columns:
        aggregation["window"] = "first"
    return frame.groupby("player_id", as_index=False).agg(aggregation)


def load_feature_table() -> pd.DataFrame:
    totals = pd.read_csv(TOTALS_PATH)
    roles = pd.read_csv(ROLE_PATH)
    for column in NUMERIC_METRICS:
        if column not in totals:
            totals[column] = 0.0
        totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0.0)
    totals = _canonicalize(totals)

    role_keep = [
        "player_id", "active_minutes", "modal_provider_position",
        "provider_position_stability", "modal_lineup_position",
        "lineup_position_stability", "modal_grid_row", "grid_row_stability",
        "modal_grid_band", "grid_band_stability", "world_cup_team",
        "squad_position", "rank_entry_precheck", "benchmark_precheck",
    ]
    role_keep = [column for column in role_keep if column in roles.columns]
    roles = roles.sort_values(["player_id", "active_minutes"], ascending=[True, False]).drop_duplicates("player_id")
    frame = totals.merge(roles[role_keep], on="player_id", how="left")
    frame = frame.loc[frame["minutes_num"] >= 450].copy()
    minutes_factor = frame["minutes_num"] / 90.0

    count_cols = [
        "shots_total", "shots_on", "goals_total", "assists", "saves",
        "passes_total", "passes_completed", "passes_key", "tackles_total",
        "blocks", "interceptions", "duels_total", "duels_won",
        "dribbles_attempts", "dribbles_success", "fouls_drawn", "fouls_committed",
    ]
    for column in count_cols:
        frame[f"{column}_p90"] = _safe_div(frame[column], minutes_factor)

    frame["pass_completion"] = _safe_div(frame["passes_completed"], frame["passes_total"])
    frame["duel_success"] = _safe_div(frame["duels_won"], frame["duels_total"])
    frame["dribble_success_rate"] = _safe_div(frame["dribbles_success"], frame["dribbles_attempts"])
    frame["shot_accuracy"] = _safe_div(frame["shots_on"], frame["shots_total"])

    frame["build_up_raw"] = (
        0.45 * frame["passes_total_p90"]
        + 25 * frame["pass_completion"]
        + 2.0 * frame["passes_key_p90"]
    )
    frame["progression_raw"] = (
        2.5 * frame["dribbles_success_p90"]
        + 1.8 * frame["passes_key_p90"]
        + 0.5 * frame["fouls_drawn_p90"]
    )
    frame["creation_raw"] = 5.5 * frame["assists_p90"] + 2.5 * frame["passes_key_p90"]
    frame["finishing_raw"] = (
        8.0 * frame["goals_total_p90"]
        + 1.4 * frame["shots_on_p90"]
        + 2.0 * frame["shot_accuracy"]
    )
    frame["defending_raw"] = (
        1.8 * frame["tackles_total_p90"]
        + 2.0 * frame["interceptions_p90"]
        + 1.1 * frame["blocks_p90"]
    )
    frame["duels_raw"] = 1.4 * frame["duels_won_p90"] + 3.0 * frame["duel_success"]
    frame["retention_raw"] = (
        3.5 * frame["pass_completion"]
        + 1.8 * frame["dribble_success_rate"]
        + 0.4 * frame["duel_success"]
        - 0.08 * frame["fouls_committed_p90"]
    )
    frame["goalkeeping_raw"] = 1.5 * frame["saves_p90"] + 0.2 * frame["pass_completion"]

    for dimension in (
        "build_up", "progression", "creation", "finishing", "defending",
        "duels", "retention", "goalkeeping",
    ):
        frame[dimension] = _robust_unit(frame[f"{dimension}_raw"])

    frame["exploratory_role"] = frame.apply(_infer_role, axis=1)
    frame["overall"] = frame.apply(_role_score, axis=1)
    frame["uncertainty"] = (
        0.22 / np.sqrt((frame["minutes_num"] / 450.0).clip(lower=1.0))
    ).clip(0.035, 0.18)
    frame["conservative_score"] = frame["overall"] - frame["uncertainty"]
    return frame


def _infer_role(row: pd.Series) -> str:
    squad = str(row.get("squad_position", ""))
    provider = str(row.get("modal_provider_position", ""))
    grid_row = pd.to_numeric(pd.Series([row.get("modal_grid_row")]), errors="coerce").iloc[0]
    band = str(row.get("modal_grid_band", ""))

    if squad == "Goalkeeper" or provider == "G":
        return "GK"
    if squad == "Defender" or provider == "D":
        if band.startswith("outer") and (pd.isna(grid_row) or grid_row <= 2.5):
            return "FB"
        return "CB"
    if squad == "Attacker" or provider == "F":
        winger_signal = row["progression"] + row["creation"] - row["finishing"]
        return "W" if winger_signal > 0.18 else "ST"

    attack_signal = 0.55 * row["creation"] + 0.45 * row["progression"]
    defence_signal = 0.62 * row["defending"] + 0.38 * row["duels"]
    if defence_signal - attack_signal > 0.18:
        return "DM"
    if attack_signal - defence_signal > 0.20:
        return "AM"
    return "CM"


def _role_score(row: pd.Series) -> float:
    weights = {
        "GK": {"goalkeeping": 0.55, "build_up": 0.20, "retention": 0.15, "base": 0.10},
        "CB": {"defending": 0.33, "duels": 0.25, "build_up": 0.22, "retention": 0.20},
        "FB": {"defending": 0.22, "duels": 0.14, "build_up": 0.18, "progression": 0.28, "creation": 0.18},
        "DM": {"defending": 0.25, "duels": 0.18, "build_up": 0.25, "retention": 0.20, "progression": 0.12},
        "CM": {"build_up": 0.23, "retention": 0.20, "progression": 0.20, "creation": 0.16, "defending": 0.12, "duels": 0.09},
        "AM": {"creation": 0.32, "progression": 0.24, "finishing": 0.17, "retention": 0.15, "build_up": 0.12},
        "W": {"progression": 0.29, "creation": 0.23, "finishing": 0.22, "retention": 0.14, "duels": 0.12},
        "ST": {"finishing": 0.44, "creation": 0.12, "progression": 0.12, "duels": 0.18, "retention": 0.14},
    }
    score = 0.0
    for key, weight in weights[str(row["exploratory_role"])].items():
        score += weight * (0.5 if key == "base" else float(row[key]))
    return float(score)


def _to_profile(
    row: pd.Series, slot: str, synthetic: bool = False, name: str | None = None
) -> PlayerProfile:
    return PlayerProfile(
        player_id=str(row.get("player_id", f"SYN-{slot}")),
        name=name or str(row["player_name"]),
        role=slot,
        minutes=float(row.get("minutes_num", 0.0)),
        overall=float(row["overall"]),
        build_up=float(row["build_up"]),
        progression=float(row["progression"]),
        creation=float(row["creation"]),
        finishing=float(row["finishing"]),
        defending=float(row["defending"]),
        duels=float(row["duels"]),
        retention=float(row["retention"]),
        goalkeeping=float(row["goalkeeping"]),
        uncertainty=float(row.get("uncertainty", 0.08)),
        synthetic=synthetic,
    )


def build_teams(
    top_n: int = 20,
) -> tuple[TeamProfile, TeamProfile, pd.DataFrame, pd.DataFrame]:
    frame = load_feature_table()
    slot_to_role = {
        "GK": "GK", "CB1": "CB", "CB2": "CB", "FB1": "FB", "FB2": "FB",
        "DM": "DM", "CM": "CM", "AM": "AM", "W1": "W", "W2": "W", "ST": "ST",
    }

    real_players: list[PlayerProfile] = []
    used_ids: set[int] = set()
    real_rows: list[dict[str, Any]] = []
    synthetic_players: list[PlayerProfile] = []
    avatar_rows: list[dict[str, Any]] = []

    for slot in ROLE_ORDER:
        role = slot_to_role[slot]
        candidates = frame.loc[frame["exploratory_role"] == role].sort_values(
            ["conservative_score", "minutes_num"], ascending=False
        )
        if len(candidates) < 2:
            raise RuntimeError(f"Insufficient exploratory candidates for role {role}")

        available = candidates.loc[~candidates["player_id"].astype(int).isin(used_ids)]
        chosen = (available if not available.empty else candidates).iloc[0]
        used_ids.add(int(chosen["player_id"]))
        real_players.append(_to_profile(chosen, slot))
        real_rows.append(
            {
                "slot": slot,
                "role_group": role,
                "player_id": int(chosen["player_id"]),
                "player_name": chosen["player_name"],
                "minutes": float(chosen["minutes_num"]),
                "overall": float(chosen["overall"]),
                "conservative_score": float(chosen["conservative_score"]),
                "provisional": True,
            }
        )

        members = candidates.head(top_n).copy()
        metric_columns = [
            "overall", "build_up", "progression", "creation", "finishing",
            "defending", "duels", "retention", "goalkeeping",
        ]
        values: dict[str, float] = {}
        for column in metric_columns:
            ordered = members[column].sort_values()
            trim = int(len(ordered) * 0.10)
            trimmed = (
                ordered.iloc[trim : len(ordered) - trim]
                if trim and len(ordered) > 2 * trim
                else ordered
            )
            values[column] = float(trimmed.mean())

        avatar = pd.Series(
            {
                "player_id": f"SYN-{slot}-{top_n}",
                "player_name": f"SYN-{slot}{top_n}",
                "minutes_num": float(members["minutes_num"].median()),
                "uncertainty": float(
                    max(0.025, members["uncertainty"].mean() / np.sqrt(len(members)))
                ),
                **values,
            }
        )
        synthetic_players.append(
            _to_profile(avatar, slot, synthetic=True, name=f"SYN-{slot}{top_n}")
        )
        avatar_rows.append(
            {
                "slot": slot,
                "role_group": role,
                "avatar_name": f"SYN-{slot}{top_n}",
                "members": int(len(members)),
                "member_names": " | ".join(members["player_name"].astype(str).tolist()),
                "overall": values["overall"],
                "uncertainty": float(avatar["uncertainty"]),
                "provisional": True,
            }
        )

    real = TeamProfile(name="Real Best XI — exploratorio", players=tuple(real_players))
    synthetic = TeamProfile(name="Synthetic XI — exploratorio", players=tuple(synthetic_players))
    return synthetic, real, pd.DataFrame(avatar_rows), pd.DataFrame(real_rows)


def team_to_rows(team: TeamProfile) -> list[dict[str, Any]]:
    return [asdict(player) for player in team.players]
