#!/usr/bin/env python3
"""Simulación calibrada de los onces corregidos de la selección v0.4.1.

Ejecuta el motor calibrado (mismos targets observados del Mundial 2026) sobre
los equipos construidos desde la capa de selección corregida
(`simulator.profiles_wc`), de modo que el paquete web (probabilidades, replay)
cite exactamente los mismos jugadores y avatares que publica la interfaz.

Uso: PYTHONPATH=. python scripts/run_calibrated_selection_simulation.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from simulator.calibrated_core import CalibrationTargets
from simulator.calibrated_monte_carlo import simulate_many_calibrated
from simulator.profiles import team_to_rows
from simulator.profiles_wc import build_teams_from_selection

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
OUT_DIR = Path("data/simulations/calibrated_v0_4_selection")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()

    calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    targets = CalibrationTargets.from_dict(calibration)
    synthetic, real, membership, real_selection = build_teams_from_selection()
    result = simulate_many_calibrated(
        synthetic,
        real,
        targets,
        simulations=args.simulations,
        seed=args.seed,
    )
    result["version"] = "calibrated_v0.4_selection"
    result["data_scope"] = (
        "Calibrado con los partidos completados del Mundial 2026; los perfiles "
        "de ambos equipos provienen de la capa de selección corregida v0.4.1 "
        "(identidades canonicalizadas y lados asignados por evidencia)."
    )
    result["interpretation"] = (
        "Resultado exploratorio de partido único a 90 minutos entre los onces "
        "publicados en la web. No es la corrida científica oficial de finales "
        "eliminatorias (experimento oficial v1)."
    )
    result["team_symmetry_note"] = (
        "La incertidumbre de muestreo por partido está pareada: cada avatar "
        "hereda la media recortada de las incertidumbres de sus miembros."
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "simulation_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    membership.to_csv(OUT_DIR / "synthetic_xi_membership.csv", index=False)
    real_selection.to_csv(OUT_DIR / "real_best_xi_selection.csv", index=False)
    pd.DataFrame(team_to_rows(synthetic)).to_csv(
        OUT_DIR / "synthetic_xi_profiles.csv", index=False
    )
    pd.DataFrame(team_to_rows(real)).to_csv(
        OUT_DIR / "real_best_xi_profiles.csv", index=False
    )
    pd.DataFrame(result["representative_match"]["timeline"]).to_csv(
        OUT_DIR / "representative_match_timeline.csv", index=False
    )

    errors = result["calibration_error"]
    quality = {
        "status": "calibration_quality_evaluated",
        "absolute_goal_error": abs(errors["goals_per_match"]),
        "absolute_shot_error": abs(errors["shots_per_match"]),
        "absolute_shot_on_target_error": abs(errors["shots_on_target_per_match"]),
        "absolute_zero_zero_error": abs(errors["zero_zero_rate"]),
        "engineering_gate_passed": (
            abs(errors["goals_per_match"]) <= 0.45
            and abs(errors["shots_per_match"]) <= 3.0
            and abs(errors["shots_on_target_per_match"]) <= 1.5
            and abs(errors["zero_zero_rate"]) <= 0.06
        ),
        "final_scientific_gate_passed": False,
    }
    (OUT_DIR / "calibration_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "simulations": result["simulations"],
                "synthetic_win": result["home_win_probability"],
                "draw": result["draw_probability"],
                "real_win": result["away_win_probability"],
                "engineering_gate_passed": quality["engineering_gate_passed"],
                "output": str(OUT_DIR),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
