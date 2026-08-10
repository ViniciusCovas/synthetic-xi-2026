#!/usr/bin/env python3
"""Grade dose-resposta: sintético em 4 níveis vs Real Annual XI v0.5.

Para cada nível (mean20, top5, p90, max20) roda o motor calibrado com a mesma
seed e N; produz a curva "força do arquétipo → probabilidade de vitória" e o
ponto de cruzamento (nível em que o sintético passa a superar o real).

Uso: PYTHONPATH=. python scripts/run_dose_response_grid.py [--simulations 10000]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulator.calibrated_core import CalibrationTargets
from simulator.calibrated_monte_carlo import simulate_many_calibrated
from simulator.profiles_annual_v05 import (
    build_real_annual_team,
    build_synthetic_tier_team,
)

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
OUT_DIR = Path("data/simulations/annual_v05_dose_response")
TIERS = ["mean20", "top5", "p90", "max20"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260718)
    args = parser.parse_args()

    targets = CalibrationTargets.from_dict(
        json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    )
    real = build_real_annual_team()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    curve = []
    for tier in TIERS:
        synthetic = build_synthetic_tier_team(tier)
        result = simulate_many_calibrated(
            synthetic, real, targets,
            simulations=args.simulations, seed=args.seed,
        )
        mean_overall = sum(p.overall for p in synthetic.players) / 11.0
        point = {
            "tier": tier,
            "synthetic_mean_overall": mean_overall,
            "synthetic_win": result["home_win_probability"],
            "draw": result["draw_probability"],
            "real_win": result["away_win_probability"],
            "mean_goals_synthetic": result["mean_home_goals"],
            "mean_goals_real": result["mean_away_goals"],
        }
        curve.append(point)
        (OUT_DIR / f"summary_{tier}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(point, ensure_ascii=False))

    crossing = None
    for a, b in zip(curve, curve[1:]):
        margin_a = a["synthetic_win"] - a["real_win"]
        margin_b = b["synthetic_win"] - b["real_win"]
        if margin_a < 0 <= margin_b:
            share = -margin_a / (margin_b - margin_a)
            crossing = {
                "between_tiers": [a["tier"], b["tier"]],
                "interpolated_mean_overall": (
                    a["synthetic_mean_overall"]
                    + share
                    * (b["synthetic_mean_overall"] - a["synthetic_mean_overall"])
                ),
                "interpolation": "linear na margem de vitória entre níveis adjacentes",
            }

    real_mean_overall = sum(p.overall for p in real.players) / 11.0
    grid = {
        "status": "dose_response_grid_completed",
        "simulations_per_tier": args.simulations,
        "seed": args.seed,
        "engine": "calibrated 90-minute match engine (exploratory)",
        "real_team": "Real Annual XI v0.5",
        "real_mean_overall": real_mean_overall,
        "paired_uncertainty": True,
        "curve": curve,
        "crossing_point": crossing,
        "reading": (
            "curve[i] responde: um time de agentes sintéticos construídos no "
            "nível i da elite humana vence o melhor XI real do ano com que "
            "probabilidade? crossing_point estima o nível mínimo para superá-lo."
        ),
    }
    (OUT_DIR / "dose_response_grid.json").write_text(
        json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"crossing_point": crossing, "real_mean_overall": real_mean_overall}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
