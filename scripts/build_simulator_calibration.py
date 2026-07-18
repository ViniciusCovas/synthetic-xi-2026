#!/usr/bin/env python3
"""Deriva objetivos de calibración del Mundial 2026 observado.

La calibración principal utiliza únicamente partidos terminados en 90 minutos
(status FT). Los partidos AET y PEN quedan documentados, pero no se mezclan con
la distribución principal porque tienen distinta exposición temporal.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FIXTURES_PATH = Path("data/processed/fixtures.csv")
PLAYER_MATCHES_PATH = Path("data/processed/player_matches.csv")
OUT_DIR = Path("data/simulations/calibration")


def safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def main() -> None:
    fixtures = pd.read_csv(FIXTURES_PATH)
    players = pd.read_csv(PLAYER_MATCHES_PATH)

    for column in ["home_goals", "away_goals"]:
        fixtures[column] = pd.to_numeric(fixtures[column], errors="coerce")
    fixtures = fixtures.dropna(subset=["home_goals", "away_goals"]).copy()
    fixtures["total_goals"] = fixtures["home_goals"] + fixtures["away_goals"]

    primary = fixtures.loc[fixtures["status"].eq("FT")].copy()
    if primary.empty:
        raise RuntimeError("No hay partidos FT para calibrar el simulador")

    primary_ids = set(primary["fixture_id"].astype(int))
    players = players.loc[players["fixture_id"].astype(int).isin(primary_ids)].copy()
    for column in ["shots", "shots_on", "goals"]:
        players[column] = pd.to_numeric(players[column], errors="coerce").fillna(0.0)

    exact_goals = float(primary["total_goals"].sum())
    captured_goals = float(players["goals"].sum())
    goal_capture_rate = safe_div(captured_goals, exact_goals)

    # Las filas posicionales pueden omitir alguna participación o autogol. Se usa
    # la razón de captura de goles como corrección conservadora para los disparos,
    # limitada para impedir una extrapolación excesiva.
    raw_adjustment = safe_div(exact_goals, captured_goals) if captured_goals else 1.0
    event_capture_adjustment = float(np.clip(raw_adjustment, 1.0, 1.40))
    captured_shots = float(players["shots"].sum())
    captured_shots_on = float(players["shots_on"].sum())
    adjusted_shots = captured_shots * event_capture_adjustment
    adjusted_shots_on = captured_shots_on * event_capture_adjustment

    match_count = int(len(primary))
    home_wins = int((primary["home_goals"] > primary["away_goals"]).sum())
    draws = int((primary["home_goals"] == primary["away_goals"]).sum())
    away_wins = int((primary["home_goals"] < primary["away_goals"]).sum())
    zero_zero = int(
        ((primary["home_goals"] == 0) & (primary["away_goals"] == 0)).sum()
    )

    goal_distribution = (
        primary["total_goals"].value_counts().sort_index().rename_axis("goals").reset_index(name="matches")
    )
    goal_distribution["probability"] = goal_distribution["matches"] / match_count

    targets = {
        "status": "world_cup_2026_calibration_ready",
        "primary_sample_rule": "Solo partidos con status FT; 90 minutos reglamentarios.",
        "source_match_count": match_count,
        "excluded_aet_matches": int(fixtures["status"].eq("AET").sum()),
        "excluded_pen_matches": int(fixtures["status"].eq("PEN").sum()),
        "exact_total_goals": exact_goals,
        "mean_goals_per_match": float(primary["total_goals"].mean()),
        "goals_standard_deviation": float(primary["total_goals"].std(ddof=1)),
        "zero_zero_rate": safe_div(zero_zero, match_count),
        "home_win_rate": safe_div(home_wins, match_count),
        "draw_rate": safe_div(draws, match_count),
        "away_win_rate": safe_div(away_wins, match_count),
        "captured_player_goals": captured_goals,
        "player_goal_capture_rate": goal_capture_rate,
        "event_capture_adjustment": event_capture_adjustment,
        "captured_shots": captured_shots,
        "captured_shots_on_target": captured_shots_on,
        "mean_shots_per_match": safe_div(adjusted_shots, match_count),
        "mean_shots_on_target_per_match": safe_div(adjusted_shots_on, match_count),
        "model_possessions_per_match": 104.0,
        "model_possessions_note": (
            "Parámetro de estados de posesión del simulador; no se presenta como una "
            "medición de posesiones reales del proveedor."
        ),
        "shot_probability_per_model_possession": safe_div(
            safe_div(adjusted_shots, match_count), 104.0
        ),
        "goal_probability_per_shot": safe_div(exact_goals, adjusted_shots),
        "shots_on_target_probability_per_shot": safe_div(
            adjusted_shots_on, adjusted_shots
        ),
        "methodological_gate": {
            "calibration_targets_allowed": True,
            "final_team_comparison_allowed": False,
            "reason": (
                "Los objetivos de calibración son observados, pero los perfiles anuales "
                "y las once funciones todavía son provisionales."
            ),
        },
    }

    if targets["mean_shots_per_match"] <= targets["mean_goals_per_match"]:
        raise RuntimeError("Objetivos imposibles: los disparos no superan a los goles")
    if targets["mean_shots_on_target_per_match"] > targets["mean_shots_per_match"]:
        raise RuntimeError("Objetivos imposibles: disparos a puerta superiores a disparos")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "world_cup_2026_targets.json").write_text(
        json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    goal_distribution.to_csv(OUT_DIR / "observed_goal_distribution.csv", index=False)

    report = [
        "# Calibración observada del simulador",
        "",
        f"- Partidos FT utilizados: **{match_count}**.",
        f"- Goles por partido: **{targets['mean_goals_per_match']:.3f}**.",
        f"- Disparos ajustados por partido: **{targets['mean_shots_per_match']:.3f}**.",
        f"- Disparos a puerta ajustados por partido: **{targets['mean_shots_on_target_per_match']:.3f}**.",
        f"- Partidos 0-0: **{targets['zero_zero_rate']:.1%}**.",
        f"- Captura de goles en filas posicionales: **{goal_capture_rate:.1%}**.",
        "",
        "La corrección de disparos queda limitada a 1.40 y se declarará como aproximación. "
        "Los goles y resultados proceden directamente del marcador exacto de cada fixture.",
    ]
    (OUT_DIR / "CALIBRATION_REPORT_ES.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print(json.dumps(targets, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
