"""Cohort-relative role resolution for the exploratory simulator.

This module deliberately avoids interpreting the provider's lateral grid as
left/right. It separates functional groups relative to players with the same broad
position, guaranteeing transparent and sufficiently populated provisional roles.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile
from .profiles import _role_score, _to_profile, load_feature_table


def resolve_exploratory_roles(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    squad = frame["squad_position"].fillna("").astype(str)
    provider = frame["modal_provider_position"].fillna("").astype(str)

    goalkeeper = squad.eq("Goalkeeper") | provider.eq("G")
    defender = (~goalkeeper) & (squad.eq("Defender") | provider.eq("D"))
    attacker = (~goalkeeper) & (squad.eq("Attacker") | provider.eq("F"))
    midfielder = ~(goalkeeper | defender | attacker)

    frame["exploratory_role"] = "CM"
    frame.loc[goalkeeper, "exploratory_role"] = "GK"

    if defender.any():
        flank_signal = (
            0.42 * frame.loc[defender, "progression"]
            + 0.28 * frame.loc[defender, "creation"]
            + 0.15 * frame.loc[defender, "build_up"]
            - 0.10 * frame.loc[defender, "defending"]
            - 0.05 * frame.loc[defender, "duels"]
        )
        percentile = flank_signal.rank(pct=True, method="average")
        frame.loc[defender, "exploratory_role"] = np.where(
            percentile >= 0.56, "FB", "CB"
        )

    if midfielder.any():
        midfield_signal = (
            0.55 * frame.loc[midfielder, "creation"]
            + 0.45 * frame.loc[midfielder, "progression"]
            - 0.58 * frame.loc[midfielder, "defending"]
            - 0.42 * frame.loc[midfielder, "duels"]
        )
        percentile = midfield_signal.rank(pct=True, method="average")
        frame.loc[midfielder, "exploratory_role"] = "CM"
        frame.loc[midfielder & percentile.reindex(frame.index).fillna(False).le(0.30), "exploratory_role"] = "DM"
        frame.loc[midfielder & percentile.reindex(frame.index).fillna(False).ge(0.70), "exploratory_role"] = "AM"

    if attacker.any():
        striker_signal = (
            frame.loc[attacker, "finishing"]
            + 0.20 * frame.loc[attacker, "duels"]
            - 0.42 * frame.loc[attacker, "progression"]
            - 0.28 * frame.loc[attacker, "creation"]
        )
        percentile = striker_signal.rank(pct=True, method="average")
        frame.loc[attacker, "exploratory_role"] = np.where(
            percentile >= 0.60, "ST", "W"
        )

    frame["overall"] = frame.apply(_role_score, axis=1)
    frame["conservative_score"] = frame["overall"] - frame["uncertainty"]
    return frame


def build_teams(
    top_n: int = 20,
) -> tuple[TeamProfile, TeamProfile, pd.DataFrame, pd.DataFrame]:
    frame = resolve_exploratory_roles(load_feature_table())
    slot_to_role = {
        "GK": "GK",
        "CB1": "CB",
        "CB2": "CB",
        "FB1": "FB",
        "FB2": "FB",
        "DM": "DM",
        "CM": "CM",
        "AM": "AM",
        "W1": "W",
        "W2": "W",
        "ST": "ST",
    }

    role_counts = frame["exploratory_role"].value_counts().to_dict()
    insufficient = {
        role: count
        for role, count in role_counts.items()
        if role in set(slot_to_role.values()) and count < 2
    }
    missing = set(slot_to_role.values()) - set(role_counts)
    if missing or insufficient:
        raise RuntimeError(
            f"Role resolution failed. missing={sorted(missing)} insufficient={insufficient}"
        )

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
        dimensions = [
            "overall",
            "build_up",
            "progression",
            "creation",
            "finishing",
            "defending",
            "duels",
            "retention",
            "goalkeeping",
        ]
        values: dict[str, float] = {}
        for column in dimensions:
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
                "role_universe_size": int(len(candidates)),
            }
        )

    real = TeamProfile(name="Real Best XI — exploratorio", players=tuple(real_players))
    synthetic = TeamProfile(name="Synthetic XI — exploratorio", players=tuple(synthetic_players))
    return synthetic, real, pd.DataFrame(avatar_rows), pd.DataFrame(real_rows)
