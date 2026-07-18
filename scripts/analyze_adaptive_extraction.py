#!/usr/bin/env python3
"""Monitora progresso e qualidade da extração adaptativa sem gerar rankings."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

AUDIT_DIR = Path("data/audits")
LAKE_DIR = Path("data/lake")
BATCH_DIR = LAKE_DIR / "batches"


def read_many(pattern: str) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in sorted(glob.glob(pattern))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def safe_rate(num: float, den: float) -> float:
    return float(num / den) if den else 0.0


def canonical_name(series: pd.Series) -> str | None:
    values = series.dropna().astype(str).str.strip()
    values = values.loc[values.ne("")]
    if values.empty:
        return None
    modes = values.mode()
    return str(modes.iloc[0] if not modes.empty else values.iloc[0])


def main() -> None:
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")
    progress_path = LAKE_DIR / "adaptive_fixture_progress.csv"
    progress = pd.read_csv(progress_path) if progress_path.exists() else pd.DataFrame()
    players = read_many(str(BATCH_DIR / "batch_*_players.csv.gz"))
    lineups = read_many(str(BATCH_DIR / "batch_*_lineups.csv.gz"))

    eligible = precheck.loc[
        precheck["rank_entry_precheck"].astype(str).str.lower().eq("true")
    ].copy()
    eligible_ids = set(eligible["player_id"].astype(int))
    benchmark_ids = set(
        eligible.loc[
            eligible["benchmark_precheck"].astype(str).str.lower().eq("true"),
            "player_id",
        ].astype(int)
    )

    if not players.empty:
        players = players.loc[players["player_id"].astype(int).isin(eligible_ids)].copy()
        players["minutes_num"] = pd.to_numeric(players["minutes"], errors="coerce")
        action_cols = [
            "passes_total",
            "shots_total",
            "tackles_total",
            "duels_total",
            "dribbles_attempts",
            "goals_total",
            "assists",
            "saves",
        ]
        for col in action_cols:
            players[col] = pd.to_numeric(players[col], errors="coerce")
        action_evidence = players[action_cols].fillna(0).abs().sum(axis=1) > 0
        players["appeared"] = (
            players["minutes_num"].fillna(0).gt(0)
            | action_evidence
            | players["rating"].notna()
            | (~players["substitute"].astype(str).str.lower().eq("true"))
        )
        active = players.loc[players["appeared"]].copy()
    else:
        active = pd.DataFrame()

    lineup_players = (
        set(lineups["player_id"].dropna().astype(int)) if not lineups.empty else set()
    )

    if not active.empty:
        player_summary = (
            active.groupby("player_id", as_index=False)
            .agg(
                player_name=("player_name", canonical_name),
                detailed_fixtures=("fixture_id", "nunique"),
                detailed_minutes=("minutes_num", "sum"),
                current_window_fixtures=(
                    "in_current_window",
                    lambda s: int(
                        pd.Series(s).astype(str).str.lower().eq("true").sum()
                    ),
                ),
                pre_world_cup_fixtures=(
                    "in_pre_world_cup_window",
                    lambda s: int(
                        pd.Series(s).astype(str).str.lower().eq("true").sum()
                    ),
                ),
                provider_position_rate=(
                    "provider_position",
                    lambda s: float(s.notna().mean()),
                ),
                passes_rate=("passes_total", lambda s: float(s.notna().mean())),
            )
        )
        player_summary["has_lineup_evidence"] = (
            player_summary["player_id"].astype(int).isin(lineup_players)
        )
        player_summary = player_summary.merge(
            eligible[
                [
                    "player_id",
                    "world_cup_team",
                    "squad_position",
                    "reported_minutes",
                    "benchmark_precheck",
                ]
            ].drop_duplicates("player_id"),
            on="player_id",
            how="left",
        )
        player_summary.to_csv(
            AUDIT_DIR / "adaptive_player_coverage.csv", index=False
        )
    else:
        player_summary = pd.DataFrame()

    completed = int(progress["fixture_id"].nunique()) if not progress.empty else 0
    endpoint_empty = (
        int((progress["status"] == "player_endpoint_empty").sum())
        if not progress.empty
        else 0
    )
    no_target = (
        int((progress["status"] == "no_target_player_returned").sum())
        if not progress.empty
        else 0
    )
    completed_with_targets = (
        int((progress["status"] == "completed").sum()) if not progress.empty else 0
    )

    seen_ids = (
        set(player_summary["player_id"].astype(int))
        if not player_summary.empty
        else set()
    )
    players_seen = len(seen_ids)
    benchmarks_seen = len(seen_ids & benchmark_ids)

    status = {
        "status": "adaptive_extraction_monitored",
        "eligible_players": len(eligible_ids),
        "eligible_players_seen": players_seen,
        "eligible_player_recall": safe_rate(players_seen, len(eligible_ids)),
        "benchmark_players": len(benchmark_ids),
        "benchmark_players_seen": benchmarks_seen,
        "benchmark_player_recall": safe_rate(benchmarks_seen, len(benchmark_ids)),
        "completed_fixtures": completed,
        "completed_with_target_players": completed_with_targets,
        "player_endpoint_empty": endpoint_empty,
        "no_target_player_returned": no_target,
        "active_player_rows": int(len(active)),
        "lineup_rows": int(len(lineups)),
        "active_minutes_nonnull_rate": (
            float(active["minutes_num"].notna().mean()) if not active.empty else 0.0
        ),
        "active_position_nonnull_rate": (
            float(active["provider_position"].notna().mean())
            if not active.empty
            else 0.0
        ),
        "active_passes_nonnull_rate": (
            float(active["passes_total"].notna().mean()) if not active.empty else 0.0
        ),
        "methodological_gate": {
            "rankings_allowed": False,
            "requirements_before_ranking": [
                "Finalizar o estabilizar la cola de fixtures elegibles.",
                "Calcular cobertura exacta por jugador dentro de cada ventana.",
                "Resolver 11 funciones posicionales con evidencia estable.",
                "Mantener solo jugadores con al menos 80% de cobertura detallada.",
            ],
        },
    }
    (AUDIT_DIR / "adaptive_extraction_monitor.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = [
        "# Monitor de extracción adaptativa",
        "",
        f"- Fixtures procesados: **{completed}**.",
        f"- Fixtures con jugadores objetivo: **{completed_with_targets}**.",
        f"- Jugadores elegibles observados: **{players_seen}/{len(eligible_ids)}** ({safe_rate(players_seen, len(eligible_ids)):.1%}).",
        f"- Candidatos a benchmark observados: **{benchmarks_seen}/{len(benchmark_ids)}** ({safe_rate(benchmarks_seen, len(benchmark_ids)):.1%}).",
        f"- Filas activas de jugador: **{len(active)}**.",
        f"- Respuestas individuales vacías: **{endpoint_empty}**.",
        "",
        "Los rankings permanecen bloqueados hasta completar las verificaciones metodológicas.",
    ]
    (AUDIT_DIR / "adaptive_extraction_monitor.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
