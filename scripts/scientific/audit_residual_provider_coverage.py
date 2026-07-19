#!/usr/bin/env python3
"""Audit whether residual selection fixtures have declared player-stat coverage.

Diagnostic only. No thresholds, gates or rankings are changed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

MODEL = Path("data/model_readiness")
AUDIT = Path("data/audits")
OUT = AUDIT / "residual_provider_coverage"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    queue = pd.read_csv(MODEL / "coverage_priority_fixtures.csv", low_memory=False)
    inventory = pd.read_csv(AUDIT / "exact_fixture_inventory.csv", low_memory=False)
    coverage = pd.read_csv(AUDIT / "annual_competition_coverage.csv", low_memory=False)

    if queue.empty:
        status = {
            "status": "no_residual_selection_fixtures",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "network_calls": 0,
        }
        (OUT / "residual_provider_coverage_status.json").write_text(json.dumps(status, indent=2))
        return

    for frame, columns in [
        (queue, ["fixture_id", "player_id"]),
        (inventory, ["fixture_id", "league_id", "season"]),
        (coverage, ["league_id", "season"]),
    ]:
        for column in columns:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    queue = queue.dropna(subset=["fixture_id", "player_id"])
    queue[["fixture_id", "player_id"]] = queue[["fixture_id", "player_id"]].astype(int)
    inventory = inventory.dropna(subset=["fixture_id", "league_id", "season"])
    inventory[["fixture_id", "league_id", "season"]] = inventory[["fixture_id", "league_id", "season"]].astype(int)
    coverage = coverage.dropna(subset=["league_id", "season"])
    coverage[["league_id", "season"]] = coverage[["league_id", "season"]].astype(int)

    fixture_columns = [column for column in [
        "fixture_id", "date_utc", "status", "league_id", "league_name", "season",
        "home_team_name", "away_team_name", "official_senior_main",
    ] if column in inventory]
    provider_columns = [column for column in [
        "league_id", "season", "league_name", "league_type", "country",
        "coverage_events", "coverage_lineups", "coverage_fixture_statistics",
        "coverage_player_statistics", "coverage_players",
    ] if column in coverage]
    provider = coverage[provider_columns].drop_duplicates(["league_id", "season"])
    if "league_name" in provider and "league_name" in fixture_columns:
        provider = provider.rename(columns={"league_name": "provider_league_name"})

    detailed = queue.merge(
        inventory[fixture_columns].drop_duplicates("fixture_id"),
        on="fixture_id",
        how="left",
        validate="many_to_one",
    ).merge(
        provider,
        on=["league_id", "season"],
        how="left",
        validate="many_to_one",
    )
    for column in [
        "coverage_events", "coverage_lineups", "coverage_fixture_statistics",
        "coverage_player_statistics", "coverage_players",
    ]:
        if column in detailed:
            detailed[column] = detailed[column].astype(str).str.strip().str.lower().isin({"true", "1", "yes"})

    detailed.to_csv(OUT / "residual_fixture_provider_support.csv", index=False)

    group_columns = [column for column in [
        "league_id", "season", "league_name", "provider_league_name", "country",
        "coverage_player_statistics", "coverage_lineups", "coverage_events",
        "priority_reason", "selection_resolution_reason", "resolved_role",
    ] if column in detailed]
    summary = detailed.groupby(group_columns, dropna=False, as_index=False).agg(
        unique_fixtures=("fixture_id", "nunique"),
        unique_players=("player_id", "nunique"),
        player_fixture_pairs=("player_id", "size"),
    ).sort_values(["unique_fixtures", "player_fixture_pairs"], ascending=[False, False])
    summary.to_csv(OUT / "residual_provider_support_summary.csv", index=False)

    fixture_level = detailed.drop_duplicates("fixture_id")
    declared = fixture_level.get("coverage_player_statistics", pd.Series(False, index=fixture_level.index)).fillna(False)
    missing_metadata = fixture_level["league_id"].isna() | (
        fixture_level.get("coverage_player_statistics", pd.Series(index=fixture_level.index, dtype=object)).isna()
    )
    status = {
        "status": "residual_provider_coverage_audited",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "residual_players": int(detailed.player_id.nunique()),
        "residual_unique_fixtures": int(detailed.fixture_id.nunique()),
        "residual_player_fixture_pairs": int(len(detailed)),
        "fixtures_declared_with_player_statistics": int(fixture_level.loc[declared, "fixture_id"].nunique()),
        "fixtures_declared_without_player_statistics": int(fixture_level.loc[~declared & ~missing_metadata, "fixture_id"].nunique()),
        "fixtures_without_coverage_metadata": int(fixture_level.loc[missing_metadata, "fixture_id"].nunique()),
        "players_touching_unsupported_fixtures": int(
            detailed.loc[~detailed.get("coverage_player_statistics", False).fillna(False), "player_id"].nunique()
        ) if "coverage_player_statistics" in detailed else int(detailed.player_id.nunique()),
        "interpretation": "Declared provider support is an audit signal, not evidence that every fixture contains a player-statistics row.",
        "next_action": "requery declared-supported fixtures; classify persistent gaps as structural provider missingness",
    }
    (OUT / "residual_provider_coverage_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
