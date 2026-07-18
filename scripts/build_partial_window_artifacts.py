#!/usr/bin/env python3
"""Constrói agregados parciais e evidência posicional sem produzir rankings."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

AUDIT_DIR = Path("data/audits")
LAKE_DIR = Path("data/lake")
BATCH_DIR = LAKE_DIR / "batches"
OUT_DIR = Path("data/model_readiness")


def read_many(pattern: str) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in sorted(glob.glob(pattern))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def parse_grid(value: object) -> tuple[float | None, float | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    left, right = value.split(":", 1)
    try:
        return float(left), float(right)
    except ValueError:
        return None, None


def mode_or_none(series: pd.Series) -> object:
    valid = series.dropna()
    if valid.empty:
        return None
    modes = valid.mode()
    return modes.iloc[0] if not modes.empty else valid.iloc[0]


def stable_share(series: pd.Series) -> float:
    valid = series.dropna()
    if valid.empty:
        return 0.0
    return float(valid.value_counts(normalize=True).iloc[0])


def window_aggregate(active: pd.DataFrame, flag: str, label: str) -> pd.DataFrame:
    subset = active.loc[bool_series(active[flag])].copy()
    if subset.empty:
        return pd.DataFrame()

    sum_cols = [
        "minutes_num",
        "shots_total",
        "shots_on",
        "goals_total",
        "assists",
        "saves",
        "passes_total",
        "passes_completed",
        "passes_key",
        "tackles_total",
        "blocks",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
        "yellow",
        "red",
    ]
    available = [col for col in sum_cols if col in subset.columns]
    grouped = subset.groupby(["player_id", "player_name"], as_index=False).agg(
        fixtures=("fixture_id", "nunique"),
        starts=("is_starter", "sum"),
        **{col: (col, "sum") for col in available},
    )
    grouped["pass_completion_rate"] = grouped.apply(
        lambda row: (
            float(row.get("passes_completed", 0) / row.get("passes_total", 0))
            if row.get("passes_total", 0) and row.get("passes_total", 0) > 0
            else None
        ),
        axis=1,
    )
    grouped["window"] = label
    return grouped


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    players = read_many(str(BATCH_DIR / "batch_*_players.csv.gz"))
    lineups = read_many(str(BATCH_DIR / "batch_*_lineups.csv.gz"))
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")

    if players.empty:
        status = {
            "status": "waiting_for_adaptive_extraction_batches",
            "rankings_allowed": False,
        }
        (OUT_DIR / "annual_model_readiness.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    keys = ["fixture_id", "team_id", "player_id"]
    players = players.drop_duplicates(keys, keep="last")
    if not lineups.empty:
        lineups = lineups.drop_duplicates(keys, keep="last")
        keep = keys + [
            "formation",
            "lineup_source",
            "lineup_position",
            "grid",
        ]
        players = players.merge(lineups[keep], on=keys, how="left")
    else:
        players["formation"] = None
        players["lineup_source"] = None
        players["lineup_position"] = None
        players["grid"] = None

    numeric_cols = [
        "minutes",
        "rating",
        "shots_total",
        "shots_on",
        "goals_total",
        "assists",
        "saves",
        "passes_total",
        "passes_key",
        "passes_accuracy_raw",
        "tackles_total",
        "blocks",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
        "yellow",
        "red",
    ]
    numeric(players, numeric_cols)
    players["minutes_num"] = players["minutes"].fillna(0.0)
    players["passes_completed"] = players["passes_accuracy_raw"]

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
    action_evidence = players[action_cols].fillna(0).abs().sum(axis=1) > 0
    players["is_starter"] = players["lineup_source"].eq("startXI") | ~bool_series(players["substitute"])
    players["appeared"] = (
        players["minutes_num"].gt(0)
        | action_evidence
        | players["rating"].notna()
        | players["is_starter"]
    )
    active = players.loc[players["appeared"]].copy()

    grids = active["grid"].apply(parse_grid)
    active["grid_row"] = grids.apply(lambda item: item[0])
    active["grid_col"] = grids.apply(lambda item: item[1])
    line_width = active.groupby(["fixture_id", "team_id", "grid_row"])["grid_col"].transform("max")
    active["grid_col_normalized"] = active["grid_col"] / line_width
    active["grid_band"] = pd.cut(
        active["grid_col_normalized"],
        bins=[-0.01, 0.34, 0.67, 1.01],
        labels=["outer_low", "center", "outer_high"],
    ).astype(object)

    evidence = (
        active.groupby(["player_id", "player_name"], as_index=False)
        .agg(
            active_fixtures=("fixture_id", "nunique"),
            active_minutes=("minutes_num", "sum"),
            starts=("is_starter", "sum"),
            modal_provider_position=("provider_position", mode_or_none),
            provider_position_stability=("provider_position", stable_share),
            modal_lineup_position=("lineup_position", mode_or_none),
            lineup_position_stability=("lineup_position", stable_share),
            modal_grid_row=("grid_row", mode_or_none),
            grid_row_stability=("grid_row", stable_share),
            modal_grid_band=("grid_band", mode_or_none),
            grid_band_stability=("grid_band", stable_share),
            modal_formation=("formation", mode_or_none),
        )
    )
    evidence = evidence.merge(
        precheck[
            [
                "player_id",
                "world_cup_team",
                "squad_position",
                "rank_entry_precheck",
                "benchmark_precheck",
            ]
        ],
        on="player_id",
        how="left",
    )
    evidence.to_csv(OUT_DIR / "partial_role_evidence.csv", index=False)

    current = window_aggregate(active, "in_current_window", "annual_current")
    pre = window_aggregate(active, "in_pre_world_cup_window", "pre_world_cup")
    current.to_csv(OUT_DIR / "partial_annual_current_totals.csv", index=False)
    pre.to_csv(OUT_DIR / "partial_pre_world_cup_totals.csv", index=False)

    status = {
        "status": "partial_window_artifacts_updated",
        "rankings_allowed": False,
        "active_rows": int(len(active)),
        "players_with_detail": int(active["player_id"].nunique()),
        "players_with_grid_evidence": int(active.loc[active["grid"].notna(), "player_id"].nunique()),
        "current_window_players": int(current["player_id"].nunique()) if not current.empty else 0,
        "pre_world_cup_players": int(pre["player_id"].nunique()) if not pre.empty else 0,
        "pass_accuracy_rule": "sum(passes_accuracy_raw) / sum(passes_total)",
        "lateral_grid_warning": "outer_low y outer_high no se interpretarán como izquierda/derecha hasta validar la orientación del proveedor.",
        "next_steps": [
            "Continuar la extracción adaptativa.",
            "Validar empíricamente la orientación lateral del grid.",
            "Resolver las once funciones con estabilidad mínima del 60%.",
            "Calcular cobertura exacta por jugador y ventana.",
        ],
    }
    (OUT_DIR / "annual_model_readiness.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
