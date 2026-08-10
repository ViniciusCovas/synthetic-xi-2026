"""Perfiles de equipo desde la selección corregida del Mundial 2026 (v0.4.1).

Construye Synthetic XI y Real Best XI para el motor calibrado a partir de los
artefactos de selección de `data/processed/` (pipeline de torneo, caché de la
API), en lugar de la extracción anual parcial que usa `profiles_v2`.

Decisiones explícitas:
- El rol de cada jugador es su rol primario del torneo (rankings.csv), no una
  inferencia exploratoria.
- Los once reales son exactamente los de real_best_xi.csv (slots con lado ya
  resuelto); los avatares son la media recortada al 10% de sus miembros
  publicados (avatar_members.csv).
- Incertidumbre de muestreo por partido PAREADA entre equipos: el avatar hereda
  la media recortada de las incertidumbres de sus miembros, en lugar del error
  estándar del centroide. Esto evita el sesgo direccional de recorte detectado
  en auditoría (perfiles reales con σ alta frente a avatares casi
  deterministas).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile
from .profiles import _robust_unit, _role_score

PROCESSED = Path("data/processed")

SLOT_TO_ENGINE_ROLE = {
    "GK": "GK",
    "RCB": "CB1",
    "LCB": "CB2",
    "RB": "FB1",
    "LB": "FB2",
    "DM": "DM",
    "CM": "CM",
    "AM": "AM",
    "RW": "W1",
    "LW": "W2",
    "ST": "ST",
}

DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)


def _trimmed_mean(values: np.ndarray, trim_fraction: float = 0.10) -> float:
    clean = np.sort(values[np.isfinite(values)])
    if clean.size == 0:
        return 0.0
    cut = int(np.floor(clean.size * trim_fraction))
    if cut > 0 and clean.size - 2 * cut >= 2:
        clean = clean[cut:-cut]
    return float(clean.mean())


def load_wc_feature_table(minimum_minutes: float = 180.0) -> pd.DataFrame:
    """Tabla de atributos del motor desde los features agregados del torneo.

    Usa las mismas fórmulas de dimensiones que `profiles.load_feature_table`,
    trasladadas a las columnas del pipeline del Mundial, y normaliza dentro del
    pool elegible del torneo (mismo umbral de minutos que el ranking).
    """
    features = pd.read_csv(PROCESSED / "player_features.csv")
    rankings = pd.read_csv(
        PROCESSED / "rankings.csv",
        usecols=["player_id", "position_group", "rank_score", "position_rank"],
    )
    frame = features.loc[features["minutes"] >= minimum_minutes].copy()
    frame = frame.merge(rankings, on="player_id", how="left", suffixes=("", "_rank"))
    if "position_group_rank" in frame.columns:
        frame["position_group"] = frame["position_group_rank"].fillna(
            frame["position_group"]
        )
        frame = frame.drop(columns="position_group_rank")

    minutes_factor = frame["minutes"] / 90.0
    frame["shots_on_p90"] = frame["shots_on"].div(minutes_factor).fillna(0.0)
    frame["pass_completion"] = (
        frame["passes_accurate"].div(frame["passes"].replace(0, np.nan)).fillna(0.0)
    )
    frame["shot_accuracy"] = frame["shots_on_target_rate"]

    frame["build_up_raw"] = (
        0.45 * frame["passes_p90"]
        + 25 * frame["pass_completion"]
        + 2.0 * frame["key_passes_p90"]
    )
    frame["progression_raw"] = (
        2.5 * frame["dribbles_completed_p90"]
        + 1.8 * frame["key_passes_p90"]
        + 0.5 * frame["fouls_drawn_p90"]
    )
    frame["creation_raw"] = (
        5.5 * frame["assists_p90"] + 2.5 * frame["key_passes_p90"]
    )
    frame["finishing_raw"] = (
        8.0 * frame["goals_p90"]
        + 1.4 * frame["shots_on_p90"]
        + 2.0 * frame["shot_accuracy"]
    )
    frame["defending_raw"] = (
        1.8 * frame["tackles_p90"]
        + 2.0 * frame["interceptions_p90"]
        + 1.1 * frame["blocks_p90"]
    )
    frame["duels_raw"] = (
        1.4 * frame["duels_won"].div(minutes_factor).fillna(0.0)
        + 3.0 * frame["duel_win_rate"]
    )
    frame["retention_raw"] = (
        3.5 * frame["pass_completion"]
        + 1.8 * frame["dribble_success_rate"]
        + 0.4 * frame["duel_win_rate"]
        - 0.08 * frame["fouls_committed_p90"]
    )
    frame["goalkeeping_raw"] = (
        1.5 * frame["saves_p90"] + 0.2 * frame["pass_completion"]
    )
    for dimension in DIMENSIONS:
        frame[dimension] = _robust_unit(frame[f"{dimension}_raw"])

    frame["exploratory_role"] = frame["position_group"]
    frame["overall"] = frame.apply(_role_score, axis=1)
    frame["uncertainty"] = (
        0.22 / np.sqrt((frame["minutes"] / 450.0).clip(lower=1.0))
    ).clip(0.035, 0.18)
    return frame


def build_teams_from_selection() -> tuple[TeamProfile, TeamProfile, pd.DataFrame, pd.DataFrame]:
    """Devuelve (synthetic, real, membresía_avatares, selección_real)."""
    frame = load_wc_feature_table().set_index("player_id", drop=False)
    real_xi = pd.read_csv(PROCESSED / "real_best_xi.csv")
    members = pd.read_csv(
        PROCESSED / "avatar_members.csv",
        usecols=["avatar_id", "position_group", "player_id", "player_name"],
    )

    real_players: list[PlayerProfile] = []
    for _, row in real_xi.iterrows():
        if not bool(row["available"]):
            raise RuntimeError(f"Slot real sin jugador disponible: {row['slot']}")
        player_id = int(row["entity_id"])
        if player_id not in frame.index:
            raise RuntimeError(
                f"Jugador {player_id} del XI no está en el pool elegible"
            )
        source = frame.loc[player_id]
        engine_role = SLOT_TO_ENGINE_ROLE[str(row["slot"])]
        real_players.append(
            PlayerProfile(
                player_id=str(player_id),
                name=str(source["player_name"]),
                role=engine_role,
                minutes=float(source["minutes"]),
                overall=float(source["overall"]),
                uncertainty=float(source["uncertainty"]),
                synthetic=False,
                **{dim: float(source[dim]) for dim in DIMENSIONS},
            )
        )

    synthetic_players: list[PlayerProfile] = []
    for slot, engine_role in SLOT_TO_ENGINE_ROLE.items():
        group = "CB" if slot in {"RCB", "LCB"} else (
            "FB" if slot in {"RB", "LB"} else (
                "W" if slot in {"RW", "LW"} else slot
            )
        )
        member_ids = members.loc[
            members["position_group"] == group, "player_id"
        ].astype(int)
        member_rows = frame.loc[frame.index.intersection(member_ids)]
        if member_rows.empty:
            raise RuntimeError(f"Avatar sin miembros elegibles: {group}")
        values = {
            dim: _trimmed_mean(member_rows[dim].to_numpy(dtype=float))
            for dim in DIMENSIONS
        }
        avatar_id = str(
            members.loc[members["position_group"] == group, "avatar_id"].iloc[0]
        )
        proxy = pd.Series({**values, "exploratory_role": group})
        synthetic_players.append(
            PlayerProfile(
                player_id=avatar_id,
                name=avatar_id,
                role=engine_role,
                minutes=float(member_rows["minutes"].median()),
                overall=float(_role_score(proxy)),
                # σ pareada: media recortada de las σ de los miembros, no el
                # error estándar del centroide.
                uncertainty=_trimmed_mean(
                    member_rows["uncertainty"].to_numpy(dtype=float)
                ),
                synthetic=True,
                **values,
            )
        )

    order = {role: index for index, role in enumerate(ROLE_ORDER)}
    real_players.sort(key=lambda player: order[player.role])
    synthetic_players.sort(key=lambda player: order[player.role])
    synthetic = TeamProfile(name="Synthetic XI", players=tuple(synthetic_players))
    real = TeamProfile(name="Real Best XI", players=tuple(real_players))

    membership = members.copy()
    return synthetic, real, membership, real_xi
