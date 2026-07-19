#!/usr/bin/env python3
"""Resolve selection challengers using up to 20 complete fixtures per API call."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.api_football_batch_client import BatchClient, QuotaStop
from scripts.run_adaptive_annual_extraction import (
    AUDIT_DIR,
    BATCH_DIR,
    LAKE_DIR,
    PROGRESS_PATH,
    as_bool,
    flatten_target_lineups,
    flatten_target_players,
    load_progress,
)

PRIORITY_PATH = Path("data/model_readiness/coverage_priority_fixtures.csv")
STATUS_PATH = AUDIT_DIR / "targeted_coverage_extraction_status.json"


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%dT%H%M%S")
    batch_id = f"batch_bundle_{run_id}"
    if not PRIORITY_PATH.exists():
        STATUS_PATH.write_text(json.dumps({"status": "waiting_for_priority_queue", "network_calls": 0}, indent=2))
        return
    priority = pd.read_csv(PRIORITY_PATH)
    if priority.empty:
        STATUS_PATH.write_text(json.dumps({"status": "no_missing_coverage_fixtures", "network_calls": 0}, indent=2))
        return

    inventory = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")
    competitions = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    eligible = precheck.loc[precheck["rank_entry_precheck"].map(as_bool)].copy()
    eligible_ids = set(pd.to_numeric(eligible.player_id, errors="coerce").dropna().astype(int))
    assoc_cols = ["player_id", "league_id", "season", "team_id"]
    for col in assoc_cols:
        competitions[col] = pd.to_numeric(competitions[col], errors="coerce")
    competitions = competitions.dropna(subset=assoc_cols)
    competitions[assoc_cols] = competitions[assoc_cols].astype(int)
    competitions = competitions[competitions.player_id.isin(eligible_ids)]
    association: dict[tuple[int, int, int], set[int]] = {}
    for row in competitions[assoc_cols].drop_duplicates().itertuples(index=False):
        association.setdefault((row.league_id, row.season, row.team_id), set()).add(row.player_id)

    priority.fixture_id = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id"])
    priority.fixture_id = priority.fixture_id.astype(int)
    counts = priority.groupby("fixture_id").agg(
        missing_player_pairs=("player_id", "nunique"),
        affected_windows=("window", "nunique"),
    ).reset_index()
    inventory.fixture_id = pd.to_numeric(inventory.fixture_id, errors="coerce")
    inventory = inventory.dropna(subset=["fixture_id"])
    inventory.fixture_id = inventory.fixture_id.astype(int)
    queue = inventory.merge(counts, on="fixture_id", how="inner")
    progress = load_progress()
    completed = set(pd.to_numeric(progress.get("fixture_id"), errors="coerce").dropna().astype(int)) if not progress.empty else set()
    queue = queue[~queue.fixture_id.isin(completed)].copy()
    queue["priority"] = queue.missing_player_pairs * 100 + queue.affected_windows * 25
    queue["date_sort"] = pd.to_datetime(queue.date_utc, utc=True, errors="coerce")
    queue = queue.sort_values(["priority", "date_sort"], ascending=[False, False])
    if queue.empty:
        STATUS_PATH.write_text(json.dumps({"status": "no_unprocessed_priority_fixtures", "network_calls": 0}, indent=2))
        return

    client = BatchClient()
    client.status()
    bundle_size = min(20, max(1, int(os.getenv("FIXTURE_BUNDLE_SIZE", "20"))))
    player_rows: list[dict] = []
    lineup_rows: list[dict] = []
    progress_rows: list[dict] = []
    requested = returned = completed_this_run = 0
    quota_stopped = False
    rows_by_id = {int(r.fixture_id): pd.Series(r._asdict()) for r in queue.itertuples(index=False)}
    fixture_ids = queue.fixture_id.astype(int).tolist()

    for start in range(0, len(fixture_ids), bundle_size):
        ids = fixture_ids[start:start + bundle_size]
        try:
            payload = client.get_fixtures_bundle(ids)
        except QuotaStop:
            quota_stopped = True
            break
        except Exception as exc:
            for fixture_id in ids:
                progress_rows.append({"fixture_id": fixture_id, "status": "retryable_error", "target_players": 0, "player_rows": 0, "lineup_rows": 0, "updated_at_utc": now.isoformat(), "error": str(exc)[:300]})
            continue
        requested += len(ids)
        items = payload.get("response") or []
        returned += len(items)
        item_by_id = {int((item.get("fixture") or {}).get("id")): item for item in items if (item.get("fixture") or {}).get("id") is not None}
        for fixture_id in ids:
            fixture = rows_by_id[fixture_id]
            item = item_by_id.get(fixture_id)
            if item is None:
                progress_rows.append({"fixture_id": fixture_id, "status": "retryable_error", "target_players": 0, "player_rows": 0, "lineup_rows": 0, "updated_at_utc": now.isoformat(), "error": "fixture_missing_from_bundle"})
                continue
            key_home = (int(fixture.league_id), int(fixture.season), int(fixture.home_team_id))
            key_away = (int(fixture.league_id), int(fixture.season), int(fixture.away_team_id))
            target_ids = association.get(key_home, set()) | association.get(key_away, set())
            players_payload = {"response": item.get("players") or []}
            lineups_payload = {"response": item.get("lineups") or []}
            targets = flatten_target_players(fixture, players_payload, target_ids)
            lineups = flatten_target_lineups(fixture, lineups_payload, target_ids)
            player_rows.extend(targets)
            lineup_rows.extend(lineups)
            state = "completed" if targets else "player_endpoint_empty" if not players_payload["response"] else "no_target_player_returned"
            progress_rows.append({"fixture_id": fixture_id, "status": state, "target_players": len(target_ids), "player_rows": len(targets), "lineup_rows": len(lineups), "updated_at_utc": now.isoformat()})
            completed_this_run += 1

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    new_progress = pd.DataFrame(progress_rows)
    if not new_progress.empty:
        durable = new_progress[~new_progress.status.eq("retryable_error")]
        retryable = new_progress[new_progress.status.eq("retryable_error")]
        progress = pd.concat([progress, durable], ignore_index=True).drop_duplicates("fixture_id", keep="last")
        if not retryable.empty:
            retryable.to_csv(BATCH_DIR / f"{batch_id}_retryable_errors.csv", index=False)
    progress.to_csv(PROGRESS_PATH, index=False)
    if player_rows:
        pd.DataFrame(player_rows).to_csv(BATCH_DIR / f"{batch_id}_players.csv.gz", index=False, compression="gzip")
    if lineup_rows:
        pd.DataFrame(lineup_rows).to_csv(BATCH_DIR / f"{batch_id}_lineups.csv.gz", index=False, compression="gzip")

    status = {
        "status": "batched_targeted_extraction_completed",
        "bundle_size": bundle_size,
        "priority_fixture_candidates": int(len(queue)),
        "fixtures_requested_this_run": requested,
        "fixtures_returned_this_run": returned,
        "fixtures_completed_this_run": completed_this_run,
        "player_rows": len(player_rows),
        "lineup_rows": len(lineup_rows),
        "network_calls": client.calls,
        "daily_limit_reported": client.daily_limit,
        "quota_remaining_reported": client.remaining,
        "quota_stopped": quota_stopped,
        "rankings_allowed": False,
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
