#!/usr/bin/env python3
"""Genera el paquete web de replay probabilístico a partir del simulador calibrado.

La timeline representativa procede directamente del motor (corrida
calibrated_v0.4_selection, misma capa de selección que publica la web). Dos
escenarios visuales adicionales se reconstruyen de forma determinista a partir
de marcadores presentes en la distribución Monte Carlo, usando únicamente
jugadores del Real Best XI y avatares del Synthetic XI publicados, y se
etiquetan explícitamente como reconstrucciones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

SUMMARY = Path("data/simulations/calibrated_v0_4_selection/simulation_summary.json")
REAL_XI = Path("data/processed/real_best_xi.csv")
SYNTHETIC_XI = Path("data/processed/synthetic_xi.csv")
OUTPUT = Path("web/public/data/replay_package.json")


def compact_event(minute: int, team: str, kind: str, actor: str, zone: int, xg: float) -> dict[str, Any]:
    return {"minute": minute, "team": team, "type": kind, "actor": actor, "zone": zone, "xg": round(xg, 3)}


def choose_probability(summary: dict[str, Any], score: str, fallback: float) -> float:
    for item in summary.get("top_scorelines", []):
        if item.get("score") == score:
            return float(item.get("probability", fallback))
    return fallback


def build_package(summary: dict[str, Any]) -> dict[str, Any]:
    real = {
        str(row["slot"]): str(row["entity_name"])
        for _, row in pd.read_csv(REAL_XI).iterrows()
    }
    syn = {
        str(row["slot"]): str(row["entity_id"])
        for _, row in pd.read_csv(SYNTHETIC_XI).iterrows()
    }

    representative = summary["representative_match"]
    representative_events = [
        compact_event(
            int(event["minute"]),
            "home" if event["team"] == summary["home"] else "away",
            str(event["type"]),
            str(event["actor"]),
            int(event.get("zone", 2)),
            float(event.get("xg", 0.0)),
        )
        for event in representative.get("timeline", [])
    ]

    upset = [
        compact_event(8, "away", "shot_on_target", real["RW"], 2, .13),
        compact_event(14, "home", "shot_off_target", syn["LW"], 2, .12),
        compact_event(25, "home", "goal", syn["ST"], 2, .18),
        compact_event(32, "away", "turnover", real["CM"], 2, 0),
        compact_event(44, "away", "goal", real["ST"], 3, .24),
        compact_event(51, "home", "shot_on_target", syn["AM"], 2, .16),
        compact_event(63, "away", "shot_off_target", real["AM"], 3, .21),
        compact_event(76, "home", "goal", syn["RW"], 2, .15),
        compact_event(84, "away", "shot_on_target", real["ST"], 3, .28),
        compact_event(90, "away", "turnover", real["RW"], 2, 0),
    ]
    intense = [
        compact_event(6, "home", "goal", syn["LW"], 2, .17),
        compact_event(12, "away", "shot_on_target", real["ST"], 2, .14),
        compact_event(19, "away", "goal", real["AM"], 2, .20),
        compact_event(27, "home", "shot_off_target", syn["ST"], 3, .26),
        compact_event(34, "away", "goal", real["ST"], 3, .29),
        compact_event(40, "home", "shot_on_target", syn["AM"], 2, .16),
        compact_event(53, "home", "goal", syn["ST"], 2, .18),
        compact_event(61, "away", "shot_on_target", real["LW"], 2, .14),
        compact_event(69, "home", "shot_on_target", syn["RW"], 2, .12),
        compact_event(78, "away", "shot_off_target", real["AM"], 3, .25),
        compact_event(87, "home", "turnover", syn["CM"], 2, 0),
    ]

    calibration = summary.get("calibration_targets", {})
    return {
        "version": "broadcast_v1.1",
        "title": "Synthetic XI vs Real Best XI",
        "engine_run": summary.get("version"),
        "probabilities": {
            "synthetic_win": summary["home_win_probability"],
            "draw": summary["draw_probability"],
            "real_win": summary["away_win_probability"],
        },
        "calibration": {
            "matches": calibration.get("source_match_count"),
            "mean_goals": calibration.get("mean_goals_per_match"),
            "mean_shots": calibration.get("mean_shots_per_match"),
            "mean_shots_on_target": calibration.get("mean_shots_on_target_per_match"),
            "zero_zero_rate": calibration.get("zero_zero_rate"),
        },
        "teams": {
            "home": {"name": "Synthetic XI", "short": "SYN"},
            "away": {"name": "Real Best XI", "short": "RBX"},
        },
        "replays": [
            {
                "id": "representative",
                "label": "Partido representativo",
                "description": "Timeline directa del partido seleccionado por el motor por cercanía a las medias de 10.000 simulaciones.",
                "scoreline_probability": choose_probability(summary, f"{representative['home_goals']}-{representative['away_goals']}", .08),
                "stats": {
                    "home_goals": representative["home_goals"],
                    "away_goals": representative["away_goals"],
                    "home_xg": representative["home_xg"],
                    "away_xg": representative["away_xg"],
                    "home_shots": representative["home_shots"],
                    "away_shots": representative["away_shots"],
                    "home_shots_on_target": representative["home_shots_on_target"],
                    "away_shots_on_target": representative["away_shots_on_target"],
                    "home_possession": representative["home_possession_share"],
                },
                "events": representative_events,
            },
            {
                "id": "synthetic-upset",
                "label": "Sorpresa sintética",
                "description": "Reconstrucción visual coherente con el marcador 2–1 muestreado por Monte Carlo.",
                "scoreline_probability": choose_probability(summary, "2-1", .05),
                "stats": {"home_goals": 2, "away_goals": 1, "home_xg": 1.49, "away_xg": 1.37, "home_shots": 9, "away_shots": 10, "home_shots_on_target": 5, "away_shots_on_target": 5, "home_possession": .494},
                "events": upset,
            },
            {
                "id": "high-intensity",
                "label": "Alta intensidad",
                "description": "Reconstrucción visual coherente con el marcador 2–2 muestreado por Monte Carlo.",
                "scoreline_probability": choose_probability(summary, "2-2", .04),
                "stats": {"home_goals": 2, "away_goals": 2, "home_xg": 1.68, "away_xg": 1.74, "home_shots": 11, "away_shots": 12, "home_shots_on_target": 6, "away_shots_on_target": 6, "home_possession": .487},
                "events": intense,
            },
        ],
        "methodological_note": (
            "El replay representativo usa la timeline directa del motor calibrado "
            "sobre los onces publicados (selección v0.4.1). Los otros dos son "
            "reconstrucciones visuales coherentes con marcadores muestreados de "
            "la distribución. Probabilidades de partido único a 90 minutos; no "
            "corresponden al experimento oficial de finales eliminatorias."
        ),
    }


def main() -> None:
    if not SUMMARY.exists():
        raise SystemExit(f"Falta la simulación calibrada: {SUMMARY}")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    package = build_package(summary)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "replay_broadcast_ready", "output": str(OUTPUT), "replays": len(package["replays"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
