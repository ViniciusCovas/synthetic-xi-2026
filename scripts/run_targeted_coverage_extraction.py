#!/usr/bin/env python3
"""Quota-safe extraction targeted by the exact per-player coverage audit.

The priority file identifies missing player-fixture pairs. For each selected
fixture, the extractor still requests every eligible associated player so that
the durable fixture-level progress remains semantically complete.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.run_adaptive_annual_extraction import (
    AUDIT_DIR,
    BATCH_DIR,
    LAKE_DIR,
    PROGRESS_PATH,
    Client,
    QuotaStop,
    as_bool,
    flatten_target_lineups,
    flatten_target_players,
    load_progress,
)

PRIORITY_PATH = Path("data/model_readiness/coverage_priority_fixtures.csv")
STATUS_PATH = AUDIT_DIR / "targeted_coverage_extraction_status.json"


def main() -> None:
    generated_at = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or generated_at.strftime("%Y%m%dT%H%M%S")
    batch_id = f"batch_targeted_{run_id}"
    if not PRIORITY_PATH.exists():
        status = {"status": "waiting_for_coverage_priority_file", "network_calls": 0}
        STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    priority = pd.read_csv(PRIORITY_PATH)
    if priority.empty:
        status = {"status": "no_missing_coverage_fixtures", "network_calls": 0}
        STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    inventory = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")
    competitions = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    eligible = precheck.loc[precheck["rank_entry_precheck"].map(as_bool)].copy()
    eligible_ids = set(pd.to_numeric(eligible["player_id"], errors="coerce").dropna().astype(int))

    assoc_cols = ["player_id", "league_id", "season", "team_id"]
    for col in assoc_cols:
        competitions[col] = pd.to_numeric(competitions[col], errors="coerce")
    competitions = competitions.dropna(subset=assoc_cols)
    competitions[assoc_cols] = competitions[assoc_cols].astype(int)
    competitions = competitions.loc[competitions["player_id"].isin(eligible_ids)]
    association: dict[tuple[int, int, int], set[int]] = {}
    for row in competitions[assoc_cols].drop_duplicates().itertuples(index=False):
        association.setdefault((row.league_id, row.season, row.team_id), set()).add(row.player_id)

    priority["fixture_id"] = pd.to_numeric(priority["fixture_id"], errors="coerce")
    priority = priority.dropna(subset=["fixture_id"])
    priority["fixture_id"] = priority["fixture_id"].astype(int)
    priority_counts = priority.groupby("fixture_id").agg(
        missing_player_pairs=("player_id", "nunique"),
        affected_windows=("window", "nunique"),
        benchmark_pairs=("benchmark_precheck", lambda s: int(s.map(as_bool).sum())),
    ).reset_index()

    inventory["fixture_id"] = pd.to_numeric(inventory["fixture_id"], errors="coerce")
    inventory = inventory.dropna(subset=["fixture_id"])
    inventory["fixture_id"] = inventory["fixture_id"].astype(int)
    queue = inventory.merge(priority_counts, on="fixture_id", how="inner")
    progress = load_progress()
    completed_ids = set(pd.to_numeric(progress.get("fixture_id"), errors="coerce").dropna().astype(int)) if not progress.empty else set()
    queue = queue.loc[~queue["fixture_id"].isin(completed_ids)].copy()
    queue["targeted_priority"] = (
        queue["benchmark_pairs"] * 1000
        + queue["missing_player_pairs"] * 100
        + queue["affected_windows"] * 25
    )
    queue["date_sort"] = pd.to_datetime(queue["date_utc"], utc=True, errors="coerce")
    queue = queue.sort_values(["targeted_priority", "date_sort"], ascending=[False, False])

    client = Client()
    player_rows: list[dict] = []
    lineup_rows: list[dict] = []
    progress_rows: list[dict] = []
    fixtures_completed = 0
    quota_stopped = False
    for fixture in queue.itertuples(index=False):
        league_id = int(fixture.league_id)
        season = int(fixture.season)
        home_ids = association.get((league_id, season, int(fixture.home_team_id)), set())
        away_ids = association.get((league_id, season, int(fixture.away_team_id)), set())
        target_ids = home_ids | away_ids
        if not target_ids:
            continue
        fixture_series = pd.Series(fixture._asdict())
        fixture_id = int(fixture.fixture_id)
        try:
            players_payload = client.get("fixtures/players", fixture_id, "players")
            targets = flatten_target_players(fixture_series, players_payload, target_ids)
            player_rows.extend(targets)
            if not (players_payload.get("response") or []):
                state = "player_endpoint_empty"
                lineups = []
            elif targets:
                lineups_payload = client.get("fixtures/lineups", fixture_id, "lineups")
                lineups = flatten_target_lineups(fixture_series, lineups_payload, target_ids)
                lineup_rows.extend(lineups)
                state = "completed"
            else:
                state = "no_target_player_returned"
                lineups = []
            progress_rows.append({
                "fixture_id": fixture_id,
                "status": state,
                "target_players": len(target_ids),
                "player_rows": len(targets),
                "lineup_rows": len(lineups),
                "updated_at_utc": generated_at.isoformat(),
            })
            fixtures_completed += 1
        except QuotaStop as exc:
            print(f"Targeted extraction stopped safely: {exc}")
            quota_stopped = True
            break
        except Exception as exc:
            print(f"Retryable targeted error fixture={fixture_id}: {exc}")
            progress_rows.append({
                "fixture_id": fixture_id,
                "status": "retryable_error",
                "target_players": len(target_ids),
                "player_rows": 0,
                "lineup_rows": 0,
                "updated_at_utc": generated_at.isoformat(),
            })

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    new_progress = pd.DataFrame(progress_rows)
    if not new_progress.empty:
        durable = new_progress.loc[~new_progress["status"].eq("retryable_error")]
        retryable = new_progress.loc[new_progress["status"].eq("retryable_error")]
        progress = pd.concat([progress, durable], ignore_index=True).drop_duplicates("fixture_id", keep="last")
        if not retryable.empty:
            retryable.to_csv(BATCH_DIR / f"{batch_id}_retryable_errors.csv", index=False)
    progress.to_csv(PROGRESS_PATH, index=False)
    if player_rows:
        pd.DataFrame(player_rows).to_csv(BATCH_DIR / f"{batch_id}_players.csv.gz", index=False, compression="gzip")
    if lineup_rows:
        pd.DataFrame(lineup_rows).to_csv(BATCH_DIR / f"{batch_id}_lineups.csv.gz", index=False, compression="gzip")

    status = {
        "status": "targeted_coverage_extraction_completed",
        "priority_fixture_candidates": int(len(queue)),
        "fixtures_completed_this_run": fixtures_completed,
        "player_rows": len(player_rows),
        "lineup_rows": len(lineup_rows),
        "network_calls": client.calls,
        "quota_remaining_reported": client.remaining,
        "quota_stopped": quota_stopped,
        "rankings_allowed": False,
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
