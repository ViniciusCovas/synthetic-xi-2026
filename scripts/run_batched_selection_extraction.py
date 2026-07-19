#!/usr/bin/env python3
"""Resolve residual selection challengers with quota-efficient fixture bundles.

Fixtures whose endpoint was never processed are fetched normally. Fixtures that
were processed but contain a known startXI player without a detailed statistics
row may be re-queried a bounded number of times. Substitution and card events are
persisted so missing-minute exposure can be bounded more precisely.
"""
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
REQUERY_PROGRESS_PATH = LAKE_DIR / "scope_requery_progress.csv"


def event_minute(event: dict) -> float | None:
    time = event.get("time") or {}
    elapsed = pd.to_numeric(pd.Series([time.get("elapsed")]), errors="coerce").iloc[0]
    extra = pd.to_numeric(pd.Series([time.get("extra")]), errors="coerce").iloc[0]
    if pd.isna(elapsed):
        return None
    return float(elapsed + (0 if pd.isna(extra) else extra))


def flatten_target_events(fixture: pd.Series, item: dict, target_ids: set[int]) -> list[dict]:
    rows: list[dict] = []
    for event in item.get("events") or []:
        player = event.get("player") or {}
        assist = event.get("assist") or {}
        player_id = player.get("id")
        assist_id = assist.get("id")
        ids = {
            int(value)
            for value in (player_id, assist_id)
            if value is not None and str(value).isdigit()
        }
        event_type = str(event.get("type") or "")
        detail = str(event.get("detail") or "")
        relevant_type = event_type.lower() in {"subst", "card"}
        if not relevant_type or not (ids & target_ids):
            continue
        minute = event_minute(event)
        rows.append({
            "fixture_id": int(fixture.fixture_id),
            "date_utc": fixture.date_utc,
            "league_id": int(fixture.league_id),
            "season": int(fixture.season),
            "team_id": (event.get("team") or {}).get("id"),
            "team_name": (event.get("team") or {}).get("name"),
            "event_type": event_type,
            "detail": detail,
            "elapsed": minute,
            "player_id": player_id,
            "player_name": player.get("name"),
            "assist_id": assist_id,
            "assist_name": assist.get("name"),
            "comments": event.get("comments"),
        })
    return rows


def load_requery_progress() -> pd.DataFrame:
    if not REQUERY_PROGRESS_PATH.exists():
        return pd.DataFrame(columns=[
            "fixture_id", "attempts", "last_run_utc", "player_rows",
            "lineup_rows", "event_rows", "status",
        ])
    frame = pd.read_csv(REQUERY_PROGRESS_PATH, low_memory=False)
    frame["fixture_id"] = pd.to_numeric(frame.fixture_id, errors="coerce")
    frame = frame.dropna(subset=["fixture_id"])
    frame["fixture_id"] = frame.fixture_id.astype(int)
    frame["attempts"] = pd.to_numeric(frame.get("attempts"), errors="coerce").fillna(0).astype(int)
    return frame


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%dT%H%M%S")
    batch_id = f"batch_bundle_{run_id}"
    if not PRIORITY_PATH.exists():
        STATUS_PATH.write_text(json.dumps({"status": "waiting_for_priority_queue", "network_calls": 0}, indent=2))
        return
    priority = pd.read_csv(PRIORITY_PATH, low_memory=False)
    if priority.empty:
        STATUS_PATH.write_text(json.dumps({"status": "no_missing_coverage_fixtures", "network_calls": 0}, indent=2))
        return

    inventory = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv", low_memory=False)
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv", low_memory=False)
    competitions = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv", low_memory=False)
    eligible = precheck.loc[precheck["rank_entry_precheck"].map(as_bool)].copy()
    eligible_ids = set(pd.to_numeric(eligible.player_id, errors="coerce").dropna().astype(int))
    assoc_cols = ["player_id", "league_id", "season", "team_id"]
    for column in assoc_cols:
        competitions[column] = pd.to_numeric(competitions[column], errors="coerce")
    competitions = competitions.dropna(subset=assoc_cols)
    competitions[assoc_cols] = competitions[assoc_cols].astype(int)
    competitions = competitions.loc[competitions.player_id.isin(eligible_ids)]
    association: dict[tuple[int, int, int], set[int]] = {}
    for row in competitions[assoc_cols].drop_duplicates().itertuples(index=False):
        association.setdefault((row.league_id, row.season, row.team_id), set()).add(row.player_id)

    priority["fixture_id"] = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id"])
    priority["fixture_id"] = priority.fixture_id.astype(int)
    if "priority_reason" not in priority:
        priority["priority_reason"] = "missing_fixture_endpoint"
    priority["is_detail_requery"] = priority.priority_reason.astype(str).eq(
        "known_startXI_without_detailed_row"
    )
    aggregation = {
        "missing_player_pairs": ("player_id", "nunique"),
        "affected_windows": ("window", "nunique"),
        "detail_requery": ("is_detail_requery", "max"),
    }
    if "priority_score" in priority:
        aggregation["declared_priority"] = ("priority_score", "max")
    counts = priority.groupby("fixture_id").agg(**aggregation).reset_index()
    if "declared_priority" not in counts:
        counts["declared_priority"] = 0.0

    inventory["fixture_id"] = pd.to_numeric(inventory.fixture_id, errors="coerce")
    inventory = inventory.dropna(subset=["fixture_id"])
    inventory.fixture_id = inventory.fixture_id.astype(int)
    queue = inventory.merge(counts, on="fixture_id", how="inner")

    progress = load_progress()
    completed = (
        set(pd.to_numeric(progress.get("fixture_id"), errors="coerce").dropna().astype(int))
        if not progress.empty else set()
    )
    requery = load_requery_progress()
    attempt_map = requery.set_index("fixture_id")["attempts"].to_dict() if not requery.empty else {}
    max_requery_attempts = max(1, int(os.getenv("SCOPE_MAX_REQUERY_ATTEMPTS", "2")))
    queue["previous_requery_attempts"] = queue.fixture_id.map(attempt_map).fillna(0).astype(int)
    queue = queue.loc[
        (~queue.fixture_id.isin(completed))
        | (
            queue.detail_requery
            & queue.previous_requery_attempts.lt(max_requery_attempts)
        )
    ].copy()
    queue["priority"] = (
        pd.to_numeric(queue.declared_priority, errors="coerce").fillna(0) * 1000
        + queue.detail_requery.astype(int) * 500
        + queue.missing_player_pairs * 100
        + queue.affected_windows * 25
    )
    queue["date_sort"] = pd.to_datetime(queue.date_utc, utc=True, errors="coerce")
    queue = queue.sort_values(["priority", "date_sort"], ascending=[False, False])
    if queue.empty:
        STATUS_PATH.write_text(json.dumps({
            "status": "no_unprocessed_or_requeryable_priority_fixtures",
            "network_calls": 0,
            "max_requery_attempts": max_requery_attempts,
        }, indent=2))
        return

    client = BatchClient()
    client.status()
    bundle_size = min(20, max(1, int(os.getenv("FIXTURE_BUNDLE_SIZE", "20"))))
    player_rows: list[dict] = []
    lineup_rows: list[dict] = []
    event_rows: list[dict] = []
    progress_rows: list[dict] = []
    requery_rows: list[dict] = []
    requested = returned = completed_this_run = 0
    quota_stopped = False
    rows_by_id = {int(row.fixture_id): pd.Series(row._asdict()) for row in queue.itertuples(index=False)}
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
                progress_rows.append({
                    "fixture_id": fixture_id, "status": "retryable_error",
                    "target_players": 0, "player_rows": 0, "lineup_rows": 0,
                    "updated_at_utc": now.isoformat(), "error": str(exc)[:300],
                })
            continue
        requested += len(ids)
        items = payload.get("response") or []
        returned += len(items)
        item_by_id = {
            int((item.get("fixture") or {}).get("id")): item
            for item in items
            if (item.get("fixture") or {}).get("id") is not None
        }
        for fixture_id in ids:
            fixture = rows_by_id[fixture_id]
            item = item_by_id.get(fixture_id)
            if item is None:
                progress_rows.append({
                    "fixture_id": fixture_id, "status": "retryable_error",
                    "target_players": 0, "player_rows": 0, "lineup_rows": 0,
                    "updated_at_utc": now.isoformat(), "error": "fixture_missing_from_bundle",
                })
                continue
            key_home = (int(fixture.league_id), int(fixture.season), int(fixture.home_team_id))
            key_away = (int(fixture.league_id), int(fixture.season), int(fixture.away_team_id))
            target_ids = association.get(key_home, set()) | association.get(key_away, set())
            players_payload = {"response": item.get("players") or []}
            lineups_payload = {"response": item.get("lineups") or []}
            targets = flatten_target_players(fixture, players_payload, target_ids)
            lineups = flatten_target_lineups(fixture, lineups_payload, target_ids)
            events = flatten_target_events(fixture, item, target_ids)
            player_rows.extend(targets)
            lineup_rows.extend(lineups)
            event_rows.extend(events)
            state = (
                "rechecked_completed" if bool(fixture.detail_requery) and targets
                else "rechecked_player_endpoint_empty" if bool(fixture.detail_requery) and not players_payload["response"]
                else "rechecked_no_target_player_returned" if bool(fixture.detail_requery) and not targets
                else "completed" if targets
                else "player_endpoint_empty" if not players_payload["response"]
                else "no_target_player_returned"
            )
            progress_rows.append({
                "fixture_id": fixture_id, "status": state,
                "target_players": len(target_ids), "player_rows": len(targets),
                "lineup_rows": len(lineups), "updated_at_utc": now.isoformat(),
            })
            if bool(fixture.detail_requery):
                requery_rows.append({
                    "fixture_id": fixture_id,
                    "attempts": int(fixture.previous_requery_attempts) + 1,
                    "last_run_utc": now.isoformat(),
                    "player_rows": len(targets),
                    "lineup_rows": len(lineups),
                    "event_rows": len(events),
                    "status": state,
                })
            completed_this_run += 1

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    new_progress = pd.DataFrame(progress_rows)
    if not new_progress.empty:
        durable = new_progress.loc[~new_progress.status.eq("retryable_error")]
        retryable = new_progress.loc[new_progress.status.eq("retryable_error")]
        progress = pd.concat([progress, durable], ignore_index=True).drop_duplicates("fixture_id", keep="last")
        if not retryable.empty:
            retryable.to_csv(BATCH_DIR / f"{batch_id}_retryable_errors.csv", index=False)
    progress.to_csv(PROGRESS_PATH, index=False)

    if requery_rows:
        updated_requery = pd.concat([requery, pd.DataFrame(requery_rows)], ignore_index=True)
        updated_requery = updated_requery.sort_values(["fixture_id", "attempts"]).drop_duplicates(
            "fixture_id", keep="last"
        )
        updated_requery.to_csv(REQUERY_PROGRESS_PATH, index=False)
    if player_rows:
        pd.DataFrame(player_rows).to_csv(BATCH_DIR / f"{batch_id}_players.csv.gz", index=False, compression="gzip")
    if lineup_rows:
        pd.DataFrame(lineup_rows).to_csv(BATCH_DIR / f"{batch_id}_lineups.csv.gz", index=False, compression="gzip")
    if event_rows:
        pd.DataFrame(event_rows).to_csv(BATCH_DIR / f"{batch_id}_events.csv.gz", index=False, compression="gzip")

    status = {
        "status": "batched_targeted_extraction_completed",
        "bundle_size": bundle_size,
        "priority_fixture_candidates": int(len(queue)),
        "detail_requery_candidates": int(queue.detail_requery.sum()),
        "fixtures_requested_this_run": requested,
        "fixtures_returned_this_run": returned,
        "fixtures_completed_this_run": completed_this_run,
        "player_rows": len(player_rows),
        "lineup_rows": len(lineup_rows),
        "event_rows": len(event_rows),
        "network_calls": client.calls,
        "daily_limit_reported": client.daily_limit,
        "quota_remaining_reported": client.remaining,
        "quota_stopped": quota_stopped,
        "max_requery_attempts": max_requery_attempts,
        "rankings_allowed": False,
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
