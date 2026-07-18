#!/usr/bin/env python3
"""Reevalúa el piloto de detalles por partido con denominadores futbolísticamente válidos.

La primera evaluación trató como valores faltantes a suplentes no utilizados. Esta
versión distingue: disponibilidad del endpoint por partido, jugadores que actuaron,
titulares, suplentes no utilizados y posibilidad de resolver la función posicional.
No genera rankings ni autoriza por sí sola resultados científicos finales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

AUDIT_DIR = Path("data/audits")


def rate(series: pd.Series) -> float:
    return float(series.fillna(False).astype(bool).mean()) if len(series) else 0.0


def nonnull(series: pd.Series) -> float:
    return float(series.notna().mean()) if len(series) else 0.0


def main() -> None:
    players = pd.read_csv(AUDIT_DIR / "fixture_detail_pilot_players.csv")
    lineups = pd.read_csv(AUDIT_DIR / "fixture_detail_pilot_lineups.csv")
    quality = pd.read_csv(AUDIT_DIR / "fixture_detail_pilot_quality.csv")
    inventory = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")

    players["minutes_num"] = pd.to_numeric(players["minutes"], errors="coerce")
    players["rating_num"] = pd.to_numeric(players["rating"], errors="coerce")
    numeric_action_cols = [
        "passes_total",
        "shots_total",
        "tackles_total",
        "duels_total",
        "dribbles_attempts",
        "goals_total",
        "assists",
        "saves",
    ]
    for col in numeric_action_cols:
        players[col] = pd.to_numeric(players[col], errors="coerce")

    player_key = ["fixture_id", "team_id", "player_id"]
    lineup_small = lineups[
        player_key
        + [
            "lineup_source",
            "lineup_position",
            "grid",
            "formation",
        ]
    ].drop_duplicates(player_key)
    merged = players.merge(lineup_small, on=player_key, how="left")

    action_evidence = merged[numeric_action_cols].fillna(0).abs().sum(axis=1) > 0
    merged["is_starter"] = merged["lineup_source"].eq("startXI")
    merged["is_unused_substitute"] = (
        merged["lineup_source"].eq("substitutes")
        & merged["minutes_num"].isna()
        & ~action_evidence
        & merged["rating_num"].isna()
    )
    merged["appeared"] = (
        merged["minutes_num"].fillna(0).gt(0)
        | action_evidence
        | merged["is_starter"]
        | merged["rating_num"].notna()
    )
    active = merged.loc[merged["appeared"]].copy()
    starters = merged.loc[merged["is_starter"]].copy()

    active["role_resolvable"] = (
        active["lineup_position"].notna()
        | active["provider_position"].notna()
        | active["grid"].notna()
    )
    starters["role_resolvable"] = (
        starters["lineup_position"].notna()
        | starters["provider_position"].notna()
        | starters["grid"].notna()
    )

    inv = inventory[["fixture_id", "date_utc", "league_id", "season"]].copy()
    inv["date_utc"] = pd.to_datetime(inv["date_utc"], utc=True)
    quality = quality.merge(inv, on=["fixture_id", "league_id", "season"], how="left")
    quality = quality.sort_values(["league_id", "season", "date_utc"])
    quality["sample_order"] = quality.groupby(["league_id", "season"]).cumcount()
    quality["sample_count"] = quality.groupby(["league_id", "season"])["fixture_id"].transform("count")
    quality["is_latest_sample"] = quality["sample_order"].eq(quality["sample_count"] - 1)
    latest = quality.loc[quality["is_latest_sample"]]

    by_pair = (
        quality.groupby(["league_id", "league_name", "season"], as_index=False)
        .agg(
            sampled_fixtures=("fixture_id", "nunique"),
            player_endpoint_available=("players_response_nonempty", "sum"),
            lineup_endpoint_available=("lineups_response_nonempty", "sum"),
        )
    )
    by_pair["player_endpoint_rate"] = (
        by_pair["player_endpoint_available"] / by_pair["sampled_fixtures"]
    )
    by_pair["lineup_endpoint_rate"] = (
        by_pair["lineup_endpoint_available"] / by_pair["sampled_fixtures"]
    )

    metrics = {
        "sampled_fixtures": int(quality["fixture_id"].nunique()),
        "fixture_player_endpoint_nonempty_rate": rate(quality["players_response_nonempty"]),
        "latest_sample_player_endpoint_nonempty_rate": rate(latest["players_response_nonempty"]),
        "fixture_lineup_endpoint_nonempty_rate": rate(quality["lineups_response_nonempty"]),
        "latest_sample_lineup_endpoint_nonempty_rate": rate(latest["lineups_response_nonempty"]),
        "player_rows": int(len(merged)),
        "active_player_rows": int(len(active)),
        "unused_substitute_rows": int(merged["is_unused_substitute"].sum()),
        "active_minutes_nonnull_rate": nonnull(active["minutes_num"]),
        "starter_minutes_nonnull_rate": nonnull(starters["minutes_num"]),
        "active_provider_position_nonnull_rate": nonnull(active["provider_position"]),
        "active_passes_total_nonnull_rate": nonnull(active["passes_total"]),
        "active_rating_nonnull_rate": nonnull(active["rating_num"]),
        "active_role_resolvable_rate": rate(active["role_resolvable"]),
        "starter_role_resolvable_rate": rate(starters["role_resolvable"]),
        "starter_grid_nonnull_rate": nonnull(starters["grid"]),
        "league_season_pairs_sampled": int(len(by_pair)),
        "league_season_pairs_with_zero_player_detail": int((by_pair["player_endpoint_rate"] == 0).sum()),
        "league_season_pairs_with_partial_player_detail": int(((by_pair["player_endpoint_rate"] > 0) & (by_pair["player_endpoint_rate"] < 1)).sum()),
        "league_season_pairs_with_full_player_detail": int((by_pair["player_endpoint_rate"] == 1).sum()),
    }

    thresholds = {
        "latest_sample_player_endpoint_nonempty_rate": 0.90,
        "fixture_lineup_endpoint_nonempty_rate": 0.95,
        "active_minutes_nonnull_rate": 0.95,
        "active_provider_position_nonnull_rate": 0.95,
        "active_passes_total_nonnull_rate": 0.90,
        "active_role_resolvable_rate": 0.98,
        "starter_role_resolvable_rate": 0.98,
    }
    checks = {key: metrics[key] >= value for key, value in thresholds.items()}

    # La extracción puede continuar de forma adaptativa aunque algunas competiciones
    # históricas no tengan detalle. La publicación de rankings seguirá condicionada a
    # cobertura individual >= 80% y a análisis de sensibilidad por competición.
    extraction_allowed = all(checks.values())
    status = (
        "pilot_approved_for_adaptive_full_extraction"
        if extraction_allowed
        else "pilot_requires_targeted_schema_repairs"
    )

    summary = {
        "status": status,
        "interpretation": (
            "Los campos deben evaluarse entre jugadores que actuaron; los suplentes no utilizados no constituyen datos faltantes."
        ),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "methodological_gate": {
            "adaptive_full_extraction_allowed": extraction_allowed,
            "rankings_allowed": False,
            "player_ranking_future_requirement": "Al menos 80% de sus minutos anuales cubiertos por estadísticas detalladas y función estable.",
            "next_step": (
                "Extraer fixtures por lotes, conservar respuestas vacías como ausencia documentada y calcular cobertura exacta por jugador."
                if extraction_allowed
                else "Reparar la definición de aparición y función posicional antes de la extracción masiva."
            ),
        },
    }

    active.to_csv(AUDIT_DIR / "fixture_detail_pilot_active_players.csv", index=False)
    by_pair.sort_values(["player_endpoint_rate", "league_name"]).to_csv(
        AUDIT_DIR / "fixture_detail_pilot_by_competition.csv", index=False
    )
    quality.to_csv(AUDIT_DIR / "fixture_detail_pilot_quality_enriched.csv", index=False)
    (AUDIT_DIR / "fixture_detail_pilot_reassessment.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
