#!/usr/bin/env python3
"""Ejecuta el simulador calibrado v0.2 sobre los onces provisionales."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from simulator.calibrated_core import CalibrationTargets
from simulator.calibrated_monte_carlo import simulate_many_calibrated
from simulator.profiles import team_to_rows
from simulator.profiles_v2 import build_teams

CALIBRATION_PATH = Path(
    "data/simulations/calibration/world_cup_2026_targets.json"
)
OUT_DIR = Path("data/simulations/calibrated_v0_2")


def main() -> None:
    calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    targets = CalibrationTargets.from_dict(calibration)
    synthetic, real, avatars, real_selection = build_teams(top_n=20)
    result = simulate_many_calibrated(
        synthetic,
        real,
        targets,
        simulations=10_000,
        seed=20260718,
    )
    result["version"] = "calibrated_v0.2"
    result["data_scope"] = (
        "Calibrated with completed 90-minute World Cup 2026 matches; team profiles "
        "use the partial annual-current extraction available at runtime."
    )
    result["interpretation"] = (
        "The simulation can be used to test architecture and calibration. Team "
        "superiority remains exploratory until coverage and role gates pass."
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "simulation_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    avatars.to_csv(OUT_DIR / "synthetic_xi_membership.csv", index=False)
    real_selection.to_csv(OUT_DIR / "real_best_xi_provisional.csv", index=False)
    pd.DataFrame(team_to_rows(synthetic)).to_csv(
        OUT_DIR / "synthetic_xi_profiles.csv", index=False
    )
    pd.DataFrame(team_to_rows(real)).to_csv(
        OUT_DIR / "real_best_xi_profiles.csv", index=False
    )
    representative = result["representative_match"]
    pd.DataFrame(representative["timeline"]).to_csv(
        OUT_DIR / "representative_match_timeline.csv", index=False
    )

    errors = result["calibration_error"]
    quality = {
        "status": "calibration_quality_evaluated",
        "absolute_goal_error": abs(errors["goals_per_match"]),
        "absolute_shot_error": abs(errors["shots_per_match"]),
        "absolute_shot_on_target_error": abs(
            errors["shots_on_target_per_match"]
        ),
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
    print(json.dumps({"simulation": result, "quality": quality}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
