#!/usr/bin/env python3
"""Analiza la auditoría anual y decide si procede la extracción por partido.

No construye rankings. Pondera la cobertura por minutos observados, selección y
posición amplia para evitar que el simple conteo de competiciones distorsione la
decisión metodológica.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

AUDIT_DIR = Path("data/audits")


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def grouped_coverage(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for value, group in df.groupby(group_col, dropna=False):
        players = int(group["player_id"].nunique())
        players_any = int(group.loc[group["has_any_statistics"], "player_id"].nunique())
        players_both = int(group.loc[group["has_both_seasons"], "player_id"].nunique())
        total_minutes = float(group["minutes"].sum())
        detailed_minutes = float(group.loc[group["usable_detailed"], "minutes"].sum())
        rows.append(
            {
                group_col: value,
                "players": players,
                "players_with_any_statistics": players_any,
                "players_with_both_seasons": players_both,
                "player_any_statistics_rate": safe_ratio(players_any, players),
                "player_both_seasons_rate": safe_ratio(players_both, players),
                "reported_minutes": total_minutes,
                "detailed_match_minutes": detailed_minutes,
                "detailed_minutes_share": safe_ratio(detailed_minutes, total_minutes),
            }
        )
    return pd.DataFrame(rows).sort_values(group_col).reset_index(drop=True)


def main() -> None:
    players = pd.read_csv(AUDIT_DIR / "annual_player_coverage.csv")
    stats = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    competitions = pd.read_csv(AUDIT_DIR / "annual_competition_coverage.csv")

    for column in [
        "coverage_events",
        "coverage_lineups",
        "coverage_fixture_statistics",
        "coverage_player_statistics",
    ]:
        competitions[column] = competitions[column].fillna(False).astype(bool)

    competitions["usable_detailed"] = (
        competitions["coverage_events"]
        & competitions["coverage_lineups"]
        & competitions["coverage_fixture_statistics"]
        & competitions["coverage_player_statistics"]
    )

    stats["minutes"] = pd.to_numeric(stats["minutes"], errors="coerce").fillna(0.0)
    stats = stats.merge(
        competitions[
            [
                "league_id",
                "season",
                "league_name",
                "league_type",
                "country",
                "usable_detailed",
                "coverage_player_statistics",
            ]
        ],
        on=["league_id", "season"],
        how="left",
        suffixes=("", "_coverage"),
    )
    stats["usable_detailed"] = stats["usable_detailed"].fillna(False).astype(bool)

    players["has_any_statistics"] = (
        players["has_2025_statistics"].astype(bool)
        | players["has_2026_statistics"].astype(bool)
    )
    players["has_both_seasons"] = (
        players["has_2025_statistics"].astype(bool)
        & players["has_2026_statistics"].astype(bool)
    )

    player_minutes = (
        stats.groupby("player_id", as_index=False)
        .agg(
            reported_minutes=("minutes", "sum"),
            detailed_match_minutes=(
                "minutes",
                lambda values: float(
                    values[stats.loc[values.index, "usable_detailed"]].sum()
                ),
            ),
        )
    )
    player_minutes["detailed_minutes_share"] = player_minutes.apply(
        lambda row: safe_ratio(
            row["detailed_match_minutes"], row["reported_minutes"]
        ),
        axis=1,
    )

    players = players.merge(player_minutes, on="player_id", how="left")
    for col in ["reported_minutes", "detailed_match_minutes", "detailed_minutes_share"]:
        players[col] = pd.to_numeric(players[col], errors="coerce").fillna(0.0)

    stats = stats.merge(
        players[
            [
                "player_id",
                "has_any_statistics",
                "has_both_seasons",
                "squad_position",
                "world_cup_team",
            ]
        ],
        on="player_id",
        how="left",
        suffixes=("", "_player"),
    )

    team = grouped_coverage(stats, "world_cup_team")
    position = grouped_coverage(stats, "squad_position")

    competition = (
        stats.groupby(
            [
                "league_id",
                "season",
                "league_name",
                "league_type",
                "country",
                "usable_detailed",
            ],
            as_index=False,
        )
        .agg(
            players=("player_id", "nunique"),
            reported_minutes=("minutes", "sum"),
        )
        .sort_values("reported_minutes", ascending=False)
        .reset_index(drop=True)
    )

    total_players = int(players["player_id"].nunique())
    players_any = int(players.loc[players["has_any_statistics"], "player_id"].nunique())
    players_both = int(players.loc[players["has_both_seasons"], "player_id"].nunique())
    total_minutes = float(stats["minutes"].sum())
    detailed_minutes = float(stats.loc[stats["usable_detailed"], "minutes"].sum())

    without_stats = players.loc[
        ~players["has_any_statistics"],
        [
            "player_id",
            "player_name",
            "world_cup_team",
            "squad_position",
            "age",
        ],
    ].sort_values(["world_cup_team", "player_name"])

    preliminary_eligible = players.assign(
        rank_entry_precheck=(players["reported_minutes"] >= 900)
        & (players["detailed_minutes_share"] >= 0.80),
        benchmark_precheck=(players["reported_minutes"] >= 1800)
        & (players["detailed_minutes_share"] >= 0.80),
    )

    metrics = {
        "player_any_statistics_rate": safe_ratio(players_any, total_players),
        "player_both_seasons_rate": safe_ratio(players_both, total_players),
        "weighted_detailed_minutes_share": safe_ratio(detailed_minutes, total_minutes),
        "minimum_team_any_statistics_rate": float(
            team["player_any_statistics_rate"].min()
        ),
        "minimum_team_detailed_minutes_share": float(
            team["detailed_minutes_share"].min()
        ),
        "minimum_position_any_statistics_rate": float(
            position["player_any_statistics_rate"].min()
        ),
        "players_rank_entry_precheck": int(
            preliminary_eligible["rank_entry_precheck"].sum()
        ),
        "players_benchmark_precheck": int(
            preliminary_eligible["benchmark_precheck"].sum()
        ),
    }

    thresholds = {
        "player_any_statistics_rate": 0.98,
        "player_both_seasons_rate": 0.95,
        "weighted_detailed_minutes_share": 0.85,
        "minimum_team_any_statistics_rate": 0.85,
        "minimum_position_any_statistics_rate": 0.95,
    }
    checks = {key: metrics[key] >= value for key, value in thresholds.items()}
    approved = all(checks.values())

    decision = {
        "status": (
            "approved_for_exact_fixture_extraction"
            if approved
            else "conditional_coverage_review_required"
        ),
        "scope": "Jugadores de las 48 selecciones del Mundial 2026; auditoría 2025-2026",
        "methodological_warning": (
            "Esta decisión autoriza únicamente la extracción exacta por partido. "
            "No autoriza publicar rankings construidos con agregados de temporada."
        ),
        "players": {
            "total": total_players,
            "with_any_statistics": players_any,
            "with_both_seasons": players_both,
            "without_statistics": int(len(without_stats)),
        },
        "minutes": {
            "reported_total": total_minutes,
            "usable_detailed": detailed_minutes,
        },
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "next_step": (
            "Construir inventario de fixtures oficiales dentro de las dos ventanas exactas, excluir amistosos y deduplicar partidos."
            if approved
            else "Revisar las selecciones y posiciones por debajo de los umbrales antes de extraer fixtures."
        ),
    }

    team.to_csv(AUDIT_DIR / "annual_team_weighted_coverage.csv", index=False)
    position.to_csv(AUDIT_DIR / "annual_position_weighted_coverage.csv", index=False)
    competition.to_csv(
        AUDIT_DIR / "annual_competition_weighted_coverage.csv", index=False
    )
    without_stats.to_csv(
        AUDIT_DIR / "annual_players_without_statistics.csv", index=False
    )
    preliminary_eligible.to_csv(
        AUDIT_DIR / "annual_player_precheck.csv", index=False
    )
    (AUDIT_DIR / "annual_coverage_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = [
        "# Decisión de cobertura anual 2025-2026",
        "",
        f"**Estado:** `{decision['status']}`",
        "",
        "## Métricas centrales",
        "",
        f"- Jugadores con alguna estadística: {players_any}/{total_players} ({metrics['player_any_statistics_rate']:.1%}).",
        f"- Jugadores con datos en ambas temporadas consultadas: {players_both}/{total_players} ({metrics['player_both_seasons_rate']:.1%}).",
        f"- Minutos en competiciones con eventos, alineaciones y estadísticas individuales por partido: {metrics['weighted_detailed_minutes_share']:.1%}.",
        f"- Peor cobertura nominal por selección: {metrics['minimum_team_any_statistics_rate']:.1%}.",
        f"- Peor cobertura nominal por posición amplia: {metrics['minimum_position_any_statistics_rate']:.1%}.",
        f"- Preselección con al menos 900 minutos y 80% de cobertura detallada: {metrics['players_rank_entry_precheck']} jugadores.",
        f"- Preselección de benchmark con al menos 1.800 minutos y 80% de cobertura detallada: {metrics['players_benchmark_precheck']} jugadores.",
        "",
        "## Regla",
        "",
        decision["methodological_warning"],
        "",
        "## Próximo paso",
        "",
        decision["next_step"],
    ]
    (AUDIT_DIR / "annual_coverage_decision.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
