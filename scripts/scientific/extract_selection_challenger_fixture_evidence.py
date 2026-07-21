#!/usr/bin/env python3
"""Fetch full lineup/event evidence only for unresolved selection challengers.

This extraction does not calculate ratings, alter role assignments, change model
weights, or generate rankings. It queries the fixture-bundle endpoint once per
unique priority fixture (in bundles of at most 20) and stores complete lineup and
event evidence needed to reconstruct exact exposure minutes.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.api_football_batch_client import BatchClient, QuotaStop

PRIORITY_PATH = Path("data/model_readiness/selection_sufficiency_priority_fixtures.csv")
UNRESOLVED_PATH = Path("data/model_readiness/selection_sufficiency_unresolved_players.csv")
OUT_DIR = Path("data/lake/selection_challenger_evidence")
AUDIT_DIR = Path("data/audits/selection_challenger_resolution")
STATUS_PATH = AUDIT_DIR / "fixture_evidence_extraction_status.json"


def scalar_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def event_minute(event: dict[str, Any]) -> float | None:
    time = event.get("time") or {}
    elapsed = pd.to_numeric(pd.Series([time.get("elapsed")]), errors="coerce").iloc[0]
    extra = pd.to_numeric(pd.Series([time.get("extra")]), errors="coerce").iloc[0]
    if pd.isna(elapsed):
        return None
    return float(elapsed + (0.0 if pd.isna(extra) else extra))


def normalize_lineups(fixture_id: int, item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in item.get("lineups") or []:
        team = team_block.get("team") or {}
        formation = team_block.get("formation")
        for source, entries in (
            ("startXI", team_block.get("startXI") or []),
            ("substitutes", team_block.get("substitutes") or []),
        ):
            for entry in entries:
                player = entry.get("player") or {}
                player_id = player.get("id")
                if player_id is None:
                    continue
                rows.append({
                    "fixture_id": fixture_id,
                    "team_id": team.get("id"),
                    "team_name": team.get("name"),
                    "formation": formation,
                    "lineup_source": source,
                    "player_id": int(player_id),
                    "player_name": player.get("name"),
                    "number": player.get("number"),
                    "lineup_position": player.get("pos"),
                    "grid": player.get("grid"),
                })
    return rows


def normalize_events(fixture_id: int, item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in item.get("events") or []:
        player = event.get("player") or {}
        assist = event.get("assist") or {}
        rows.append({
            "fixture_id": fixture_id,
            "team_id": (event.get("team") or {}).get("id"),
            "team_name": (event.get("team") or {}).get("name"),
            "event_type": event.get("type"),
            "detail": event.get("detail"),
            "elapsed": event_minute(event),
            "player_id": player.get("id"),
            "player_name": player.get("name"),
            "assist_id": assist.get("id"),
            "assist_name": assist.get("name"),
            "comments": event.get("comments"),
        })
    return rows


def fixture_metadata(fixture_id: int, item: dict[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture") or {}
    status = fixture.get("status") or {}
    lineups = item.get("lineups")
    events = item.get("events")
    normalized_lineups = normalize_lineups(fixture_id, item)
    starts = pd.DataFrame(normalized_lineups)
    start_counts: dict[int, int] = {}
    if not starts.empty:
        block = starts.loc[starts.lineup_source.eq("startXI")]
        start_counts = {
            int(team_id): int(count)
            for team_id, count in block.groupby("team_id").player_id.nunique().items()
            if pd.notna(team_id)
        }
    return {
        "fixture_id": fixture_id,
        "fixture_returned": True,
        "status_short": status.get("short"),
        "status_elapsed": status.get("elapsed"),
        "lineups_key_present": "lineups" in item,
        "events_key_present": "events" in item,
        "lineup_team_blocks": len(lineups or []),
        "event_count": len(events or []),
        "home_team_id": ((item.get("teams") or {}).get("home") or {}).get("id"),
        "away_team_id": ((item.get("teams") or {}).get("away") or {}).get("id"),
        "home_startxi_count": start_counts.get(
            int(((item.get("teams") or {}).get("home") or {}).get("id") or -1), 0
        ),
        "away_startxi_count": start_counts.get(
            int(((item.get("teams") or {}).get("away") or {}).get("id") or -1), 0
        ),
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%dT%H%M%S")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not PRIORITY_PATH.exists() or not UNRESOLVED_PATH.exists():
        raise SystemExit("Selection challenger inputs are missing")

    priority = pd.read_csv(PRIORITY_PATH, low_memory=False)
    unresolved = pd.read_csv(UNRESOLVED_PATH, low_memory=False)
    for frame in (priority, unresolved):
        frame["player_id"] = pd.to_numeric(frame.player_id, errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    unresolved_ids = set(unresolved.player_id)
    priority["fixture_id"] = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id"])
    priority["fixture_id"] = priority.fixture_id.astype(int)
    priority = priority.loc[
        priority.player_id.isin(unresolved_ids)
        & priority.get("priority_reason", "").astype(str).eq("known_startXI_without_detailed_row")
    ].copy()
    fixture_ids = sorted(set(priority.fixture_id))

    if not fixture_ids:
        status = {
            "status": "no_challenger_fixtures_to_fetch",
            "generated_at_utc": now.isoformat(),
            "unresolved_players": len(unresolved_ids),
            "network_calls": 0,
        }
        STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    client = BatchClient()
    client.status()
    quota_start = client.remaining
    bundle_size = min(20, max(1, int(os.getenv("FIXTURE_BUNDLE_SIZE", "20"))))

    lineup_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    requested = returned = 0
    errors: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    for start in range(0, len(fixture_ids), bundle_size):
        ids = fixture_ids[start:start + bundle_size]
        try:
            payload = client.get_fixtures_bundle(ids, force_refresh=True)
        except QuotaStop as exc:
            stopped_reason = str(exc)
            break
        except Exception as exc:
            errors.append({"fixture_ids": "-".join(map(str, ids)), "error": str(exc)[:1000]})
            continue
        requested += len(ids)
        items = payload.get("response") or []
        item_by_id = {
            int((item.get("fixture") or {}).get("id")): item
            for item in items
            if (item.get("fixture") or {}).get("id") is not None
        }
        returned += len(item_by_id)
        for fixture_id in ids:
            item = item_by_id.get(fixture_id)
            if item is None:
                metadata_rows.append({
                    "fixture_id": fixture_id,
                    "fixture_returned": False,
                    "lineups_key_present": False,
                    "events_key_present": False,
                })
                continue
            lineup_rows.extend(normalize_lineups(fixture_id, item))
            event_rows.extend(normalize_events(fixture_id, item))
            metadata_rows.append(fixture_metadata(fixture_id, item))

    lineup_path = OUT_DIR / f"challenger_full_lineups_{run_id}.csv.gz"
    event_path = OUT_DIR / f"challenger_full_events_{run_id}.csv.gz"
    metadata_path = OUT_DIR / f"challenger_fixture_metadata_{run_id}.csv"
    if lineup_rows:
        pd.DataFrame(lineup_rows).drop_duplicates(
            ["fixture_id", "team_id", "lineup_source", "player_id"], keep="last"
        ).to_csv(lineup_path, index=False, compression="gzip")
    if event_rows:
        pd.DataFrame(event_rows).drop_duplicates().to_csv(event_path, index=False, compression="gzip")
    pd.DataFrame(metadata_rows).drop_duplicates("fixture_id", keep="last").to_csv(
        metadata_path, index=False
    )
    if errors:
        pd.DataFrame(errors).to_csv(AUDIT_DIR / "fixture_evidence_extraction_errors.csv", index=False)

    meta = pd.DataFrame(metadata_rows)
    complete_lineups = 0
    event_feeds = 0
    if not meta.empty:
        complete_lineups = int(
            (
                meta.get("lineups_key_present", pd.Series(False, index=meta.index)).map(scalar_bool)
                & pd.to_numeric(meta.get("home_startxi_count"), errors="coerce").fillna(0).ge(11)
                & pd.to_numeric(meta.get("away_startxi_count"), errors="coerce").fillna(0).ge(11)
            ).sum()
        )
        event_feeds = int(
            meta.get("events_key_present", pd.Series(False, index=meta.index)).map(scalar_bool).sum()
        )

    status = {
        "status": "selection_challenger_fixture_evidence_extracted",
        "generated_at_utc": now.isoformat(),
        "methodological_effect": "data_recovery_only_no_model_or_threshold_changes",
        "unresolved_players_at_start": int(len(unresolved_ids)),
        "priority_player_fixture_pairs": int(len(priority)),
        "priority_unique_fixtures": int(len(fixture_ids)),
        "fixtures_requested": int(requested),
        "fixtures_returned": int(returned),
        "complete_two_team_lineups": complete_lineups,
        "fixtures_with_event_feed_key": event_feeds,
        "network_calls": int(client.calls),
        "quota_remaining_at_start": quota_start,
        "quota_remaining_at_end": client.remaining,
        "stopped_reason": stopped_reason,
        "errors": int(len(errors)),
        "lineup_rows": int(len(lineup_rows)),
        "event_rows": int(len(event_rows)),
        "outputs": {
            "lineups": str(lineup_path) if lineup_rows else None,
            "events": str(event_path) if event_rows else None,
            "metadata": str(metadata_path),
        },
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if returned < len(fixture_ids) and stopped_reason is None:
        raise SystemExit("Not all priority fixtures were returned; evidence remains incomplete")


if __name__ == "__main__":
    main()
