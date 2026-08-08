#!/usr/bin/env python3
"""Reconstruye la selección (v0.4.1) desde la caché de la API, sin red.

Corrige dos defectos de la capa de selección v0.4.0 detectados en auditoría:

1. Identidades duplicadas: el proveedor alterna grafías del mismo jugador
   ("Bono"/"Yassine Bounou"), partiéndolo en filas separadas y diluyendo sus
   minutos. Ahora se canonicaliza por player_id antes de agregar.
2. Slots laterales ordinales: RB/LB, RCB/LCB y RW/LW se asignaban solo por
   ranking. Ahora el lado se decide con la orientación de grid validada más
   las anclas públicas de rol; la elegibilidad sigue siendo solo por ranking.

Entradas (todas versionadas en el repo): data/processed/player_matches.csv,
data/lake/batches/*_lineups.csv.gz, data/model_readiness/lateral_grid_validation.json,
data/reference/public_role_anchors_2026.csv.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.config import StudySpec
from synthetic_xi_2026.export import export_web_data
from synthetic_xi_2026.features_v04 import aggregate_features
from synthetic_xi_2026.ranking import (
    build_avatars,
    build_experimental_lineups,
    build_positional_comparisons,
    build_real_benchmarks,
    rank_players,
)
from synthetic_xi_2026.sides import build_side_evidence

PROCESSED = ROOT / "data" / "processed"


def merged_identity_report(player_matches: pd.DataFrame) -> list[dict[str, object]]:
    names = player_matches.groupby("player_id")["player_name"].agg(["unique"])
    report = []
    for player_id, (variants,) in names.iterrows():
        if len(variants) > 1:
            report.append(
                {
                    "player_id": int(player_id),
                    "name_variants": sorted(str(v) for v in variants),
                }
            )
    return report


def main() -> None:
    spec = StudySpec()
    player_matches = pd.read_csv(PROCESSED / "player_matches.csv")
    features = aggregate_features(player_matches)
    rankings = rank_players(
        features,
        minimum_minutes=spec.minimum_minutes,
        reliability_prior_minutes=spec.reliability_prior_minutes,
    )
    avatars, avatar_metrics, avatar_members = build_avatars(
        rankings,
        requested_top_n=spec.requested_top_n,
        seed=spec.seed,
        trim_fraction=spec.trim_fraction,
    )
    real_benchmarks = build_real_benchmarks(rankings)
    positional_comparisons = build_positional_comparisons(
        avatar_metrics, real_benchmarks
    )
    side_by_player, side_evidence = build_side_evidence()
    synthetic_xi, real_best_xi = build_experimental_lineups(
        rankings, avatars, side_by_player
    )

    frames = {
        "player_features": features,
        "rankings": rankings,
        "avatars": avatars,
        "avatar_metrics": avatar_metrics,
        "avatar_members": avatar_members,
        "real_benchmarks": real_benchmarks,
        "positional_comparisons": positional_comparisons,
        "synthetic_xi": synthetic_xi,
        "real_best_xi": real_best_xi,
    }
    for name, frame in frames.items():
        frame.to_csv(PROCESSED / f"{name}.csv", index=False)
    side_evidence.to_csv(PROCESSED / "xi_side_evidence.csv", index=False)

    merged = merged_identity_report(player_matches)
    manifest_path = PROCESSED / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["project_version"] = "0.4.1"
    manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["corrections_v0_4_1"] = {
        "player_identity_canonicalization": {
            "rule": (
                "player_name canonicalizado por player_id (nombre del partido "
                "con más minutos) antes de agregar features"
            ),
            "merged_players": merged,
        },
        "lateral_slot_assignment": {
            "rule": (
                "RB/LB, RCB/LCB y RW/LW asignados por lado observado (grid "
                "validado low_is_left + anclas públicas); la elegibilidad "
                "sigue siendo exclusivamente por ranking"
            ),
            "side_evidence_file": "xi_side_evidence.csv",
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    methods_path = PROCESSED / "methods.json"
    methods = json.loads(methods_path.read_text(encoding="utf-8"))
    methods["canonicalizacion_identidad"] = (
        "Las variantes de grafía del proveedor se unifican por player_id antes "
        "de la agregación; los minutos y conteos del jugador se consolidan en "
        "una sola fila."
    )
    methods["asignacion_de_lados"] = (
        "Dentro de cada par de slots (RB/LB, RCB/LCB, RW/LW) el lado se decide "
        "con el mapeo de grid validado contra anclas humanas y con las anclas "
        "públicas de rol; sin evidencia concluyente se conserva el orden de "
        "ranking. La evidencia queda en xi_side_evidence.csv."
    )
    methods_path.write_text(
        json.dumps(methods, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    export_web_data(PROCESSED, ROOT / "web" / "public" / "data")

    print(
        json.dumps(
            {
                "status": "selection_rebuilt_v0_4_1",
                "players_ranked": int(len(rankings)),
                "merged_identities": merged,
                "side_assignments": {
                    row["slot"]: {
                        "player": row["entity_name"],
                        "observed_side": row["observed_side"],
                        "rule": row["side_assignment_rule"],
                    }
                    for _, row in real_best_xi.iterrows()
                    if row["slot"] in {"RB", "LB", "RCB", "LCB", "RW", "LW"}
                },
                "real_best_xi": {
                    row["slot"]: row["entity_name"]
                    for _, row in real_best_xi.iterrows()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
