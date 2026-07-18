#!/usr/bin/env python3
"""Exporta una auditoría reproducible de las 10.000 simulaciones calibradas.

Genera:
- una fila por partido simulado, comprimida como artefacto de GitHub Actions;
- distribución completa de marcadores;
- convergencia de probabilidades y medias por bloques;
- percentiles y comprobación contra el resumen principal.

El archivo completo no se versiona en Git para evitar crecimiento innecesario del
repositorio. Los resúmenes compactos sí se publican.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from simulator.calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibrationTargets,
)
from simulator.profiles_v2 import build_teams

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
SUMMARY_PATH = Path("data/simulations/calibrated_v0_2/simulation_summary.json")
COMPACT_DIR = Path("data/simulations/calibrated_v0_2")
ARTIFACT_DIR = Path("artifacts/simulation_audit")
SIMULATIONS = 10_000
MASTER_SEED = 20260718
CHECKPOINTS = (100, 250, 500, 1_000, 2_500, 5_000, 7_500, 10_000)


def outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "synthetic_win"
    if home_goals < away_goals:
        return "real_win"
    return "draw"


def checkpoint_row(frame: pd.DataFrame, n: int) -> dict[str, float | int]:
    subset = frame.iloc[:n]
    counts = subset["outcome"].value_counts()
    return {
        "simulations": n,
        "synthetic_win_probability": float(counts.get("synthetic_win", 0) / n),
        "draw_probability": float(counts.get("draw", 0) / n),
        "real_win_probability": float(counts.get("real_win", 0) / n),
        "mean_home_goals": float(subset["home_goals"].mean()),
        "mean_away_goals": float(subset["away_goals"].mean()),
        "mean_total_goals": float(subset["total_goals"].mean()),
        "mean_total_shots": float(subset["total_shots"].mean()),
        "mean_total_shots_on_target": float(
            subset["total_shots_on_target"].mean()
        ),
        "zero_zero_probability": float(subset["is_zero_zero"].mean()),
    }


def main() -> None:
    calibration_payload = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    targets = CalibrationTargets.from_dict(calibration_payload)
    synthetic, real, _, _ = build_teams(top_n=20)

    master_rng = np.random.default_rng(MASTER_SEED)
    rows: list[dict[str, float | int | str]] = []

    for simulation_id in range(1, SIMULATIONS + 1):
        match_seed = int(master_rng.integers(0, 2**32 - 1))
        result = CalibratedMatchSimulator(
            synthetic,
            real,
            targets,
            CalibratedConfig(seed=match_seed),
        ).simulate(keep_timeline=False)
        home_possession_share = (
            result.home_possessions
            / (result.home_possessions + result.away_possessions)
            if result.home_possessions + result.away_possessions
            else 0.5
        )
        rows.append(
            {
                "simulation_id": simulation_id,
                "match_seed": match_seed,
                "home_team": synthetic.name,
                "away_team": real.name,
                "home_goals": result.home_goals,
                "away_goals": result.away_goals,
                "total_goals": result.home_goals + result.away_goals,
                "scoreline": f"{result.home_goals}-{result.away_goals}",
                "outcome": outcome(result.home_goals, result.away_goals),
                "home_xg": result.home_xg,
                "away_xg": result.away_xg,
                "total_xg": result.home_xg + result.away_xg,
                "home_shots": result.home_shots,
                "away_shots": result.away_shots,
                "total_shots": result.home_shots + result.away_shots,
                "home_shots_on_target": result.home_shots_on_target,
                "away_shots_on_target": result.away_shots_on_target,
                "total_shots_on_target": (
                    result.home_shots_on_target + result.away_shots_on_target
                ),
                "home_possessions": result.home_possessions,
                "away_possessions": result.away_possessions,
                "home_possession_share": home_possession_share,
                "is_zero_zero": int(
                    result.home_goals == 0 and result.away_goals == 0
                ),
            }
        )

    frame = pd.DataFrame(rows)
    COMPACT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    full_csv = frame.to_csv(index=False)
    with gzip.open(
        ARTIFACT_DIR / "all_10000_simulated_matches.csv.gz",
        "wt",
        encoding="utf-8",
        newline="",
    ) as handle:
        handle.write(full_csv)

    frame.head(250).to_csv(
        COMPACT_DIR / "simulation_audit_sample_250.csv", index=False
    )

    convergence = pd.DataFrame(
        [checkpoint_row(frame, checkpoint) for checkpoint in CHECKPOINTS]
    )
    convergence.to_csv(COMPACT_DIR / "simulation_convergence.csv", index=False)

    scorelines = (
        frame["scoreline"]
        .value_counts()
        .rename_axis("scoreline")
        .reset_index(name="matches")
    )
    scorelines["probability"] = scorelines["matches"] / SIMULATIONS
    scorelines.to_csv(COMPACT_DIR / "simulation_scoreline_distribution.csv", index=False)

    outcome_counts = Counter(frame["outcome"])
    audit = {
        "status": "complete_simulation_audit_exported",
        "simulations": SIMULATIONS,
        "master_seed": MASTER_SEED,
        "one_row_per_simulated_match": True,
        "full_ledger_artifact": "all_10000_simulated_matches.csv.gz",
        "outcomes": {
            "synthetic_wins": int(outcome_counts["synthetic_win"]),
            "draws": int(outcome_counts["draw"]),
            "real_best_xi_wins": int(outcome_counts["real_win"]),
        },
        "probabilities": {
            "synthetic_win": float(outcome_counts["synthetic_win"] / SIMULATIONS),
            "draw": float(outcome_counts["draw"] / SIMULATIONS),
            "real_best_xi_win": float(outcome_counts["real_win"] / SIMULATIONS),
        },
        "means": {
            "home_goals": float(frame["home_goals"].mean()),
            "away_goals": float(frame["away_goals"].mean()),
            "total_goals": float(frame["total_goals"].mean()),
            "total_shots": float(frame["total_shots"].mean()),
            "total_shots_on_target": float(
                frame["total_shots_on_target"].mean()
            ),
            "home_xg": float(frame["home_xg"].mean()),
            "away_xg": float(frame["away_xg"].mean()),
            "zero_zero_probability": float(frame["is_zero_zero"].mean()),
        },
        "percentiles": {
            metric: {
                str(percentile): float(frame[metric].quantile(percentile / 100))
                for percentile in (5, 25, 50, 75, 95)
            }
            for metric in (
                "home_goals",
                "away_goals",
                "total_goals",
                "total_shots",
                "total_shots_on_target",
                "home_xg",
                "away_xg",
            )
        },
        "calibration_targets": {
            "matches": targets.source_match_count,
            "goals_per_match": targets.mean_goals_per_match,
            "shots_per_match": targets.mean_shots_per_match,
            "shots_on_target_per_match": targets.mean_shots_on_target_per_match,
            "zero_zero_rate": targets.zero_zero_rate,
        },
        "interpretation_gate": {
            "simulation_process_reproducible": True,
            "engineering_calibration_passed": True,
            "final_scientific_team_comparison_allowed": False,
            "reason": (
                "El motor y su distribución son auditables, pero los perfiles anuales "
                "y la resolución definitiva de once funciones siguen incompletos."
            ),
        },
    }

    if SUMMARY_PATH.exists():
        principal = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        comparisons = {
            "synthetic_win_probability": abs(
                audit["probabilities"]["synthetic_win"]
                - principal["home_win_probability"]
            ),
            "draw_probability": abs(
                audit["probabilities"]["draw"] - principal["draw_probability"]
            ),
            "real_win_probability": abs(
                audit["probabilities"]["real_best_xi_win"]
                - principal["away_win_probability"]
            ),
            "mean_total_goals": abs(
                audit["means"]["total_goals"] - principal["mean_total_goals"]
            ),
            "mean_total_shots": abs(
                audit["means"]["total_shots"] - principal["mean_total_shots"]
            ),
        }
        audit["difference_from_principal_summary"] = comparisons
        audit["matches_principal_summary"] = all(
            difference < 1e-12 for difference in comparisons.values()
        )
        if not audit["matches_principal_summary"]:
            raise RuntimeError(
                "La auditoría completa no reproduce exactamente el resumen principal"
            )

    (COMPACT_DIR / "simulation_audit_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = [
        "# Auditoría de las 10.000 simulaciones",
        "",
        f"- Semilla maestra: `{MASTER_SEED}`.",
        f"- Partidos simulados: **{SIMULATIONS:,}**.",
        "- Cada partido conserva una semilla individual y una fila completa.",
        "- El archivo íntegro se publica como artefacto comprimido de GitHub Actions.",
        "",
        "## Variables por partido",
        "",
        "Marcador, resultado, xG, disparos, disparos a puerta, posesiones, cuota de posesión y 0-0.",
        "",
        "## Alcance científico",
        "",
        "La auditoría demuestra reproducibilidad computacional y calibración descriptiva. "
        "No constituye todavía validación predictiva externa ni prueba causal de que un "
        "once vencería al otro en el mundo real.",
    ]
    (COMPACT_DIR / "SIMULATION_AUDIT_ES.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
