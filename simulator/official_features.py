"""Configurable feature construction for official minute-threshold analyses.

The historical ``profiles.load_feature_table`` intentionally freezes a 450-minute
exploratory floor.  Official v1 requires genuine 180, 450 and 900-minute runs,
so this module reconstructs the same transparent features while applying the
requested threshold exactly.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .profiles import (
    NUMERIC_METRICS,
    ROLE_PATH,
    TOTALS_PATH,
    _canonicalize,
    _infer_role,
    _robust_unit,
    _role_score,
    _safe_div,
)


def load_official_feature_table(minimum_minutes: int) -> pd.DataFrame:
    if int(minimum_minutes) < 1:
        raise ValueError("minimum_minutes must be positive")
    totals = pd.read_csv(TOTALS_PATH)
    roles = pd.read_csv(ROLE_PATH)
    for column in NUMERIC_METRICS:
        if column not in totals:
            totals[column] = 0.0
        totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0.0)
    totals = _canonicalize(totals)

    role_keep = [
        "player_id",
        "active_minutes",
        "modal_provider_position",
        "provider_position_stability",
        "modal_lineup_position",
        "lineup_position_stability",
        "modal_grid_row",
        "grid_row_stability",
        "modal_grid_band",
        "grid_band_stability",
        "world_cup_team",
        "squad_position",
        "rank_entry_precheck",
        "benchmark_precheck",
    ]
    role_keep = [column for column in role_keep if column in roles.columns]
    roles = (
        roles.sort_values(["player_id", "active_minutes"], ascending=[True, False])
        .drop_duplicates("player_id")
    )
    frame = totals.merge(roles[role_keep], on="player_id", how="left")
    frame["minutes_num"] = pd.to_numeric(
        frame["minutes_num"], errors="coerce"
    ).fillna(0.0)
    frame = frame.loc[frame["minutes_num"] >= float(minimum_minutes)].copy()
    if frame.empty:
        raise RuntimeError(
            f"No players satisfy exact minimum_minutes={minimum_minutes}"
        )
    minutes_factor = frame["minutes_num"] / 90.0

    count_cols = [
        "shots_total",
        "shots_on",
        "goals_total",
        "assists",
        "saves",
        "passes_total",
        "passes_completed",
        "passes_key",
        "tackles_total",
        "blocks",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
    ]
    for column in count_cols:
        frame[f"{column}_p90"] = _safe_div(frame[column], minutes_factor)

    frame["pass_completion"] = _safe_div(
        frame["passes_completed"], frame["passes_total"]
    )
    frame["duel_success"] = _safe_div(frame["duels_won"], frame["duels_total"])
    frame["dribble_success_rate"] = _safe_div(
        frame["dribbles_success"], frame["dribbles_attempts"]
    )
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
    frame["creation_raw"] = (
        5.5 * frame["assists_p90"] + 2.5 * frame["passes_key_p90"]
    )
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
    frame["duels_raw"] = (
        1.4 * frame["duels_won_p90"] + 3.0 * frame["duel_success"]
    )
    frame["retention_raw"] = (
        3.5 * frame["pass_completion"]
        + 1.8 * frame["dribble_success_rate"]
        + 0.4 * frame["duel_success"]
        - 0.08 * frame["fouls_committed_p90"]
    )
    frame["goalkeeping_raw"] = (
        1.5 * frame["saves_p90"] + 0.2 * frame["pass_completion"]
    )

    for dimension in (
        "build_up",
        "progression",
        "creation",
        "finishing",
        "defending",
        "duels",
        "retention",
        "goalkeeping",
    ):
        frame[dimension] = _robust_unit(frame[f"{dimension}_raw"])

    frame["exploratory_role"] = frame.apply(_infer_role, axis=1)
    frame["overall"] = frame.apply(_role_score, axis=1)
    frame["uncertainty"] = (
        0.22
        / np.sqrt(
            (frame["minutes_num"] / float(minimum_minutes)).clip(lower=1.0)
        )
    ).clip(0.035, 0.18)
    frame["conservative_score"] = frame["overall"] - frame["uncertainty"]
    frame["official_minimum_minutes"] = int(minimum_minutes)
    frame["player_id_key"] = frame["player_id"].astype(str)
    return frame
