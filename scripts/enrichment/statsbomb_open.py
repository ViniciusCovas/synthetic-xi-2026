#!/usr/bin/env python3
"""Small helpers for Hudl StatsBomb Open Data JSON files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from scripts.enrichment.common import cache_path

BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data"
RAW_DIR = Path("data/raw/statsbomb_open")


def get_json(session: requests.Session, relative_path: str, prefix: str) -> Any:
    url = f"{BASE}/{relative_path.lstrip('/')}"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(RAW_DIR, prefix, [url])
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = session.get(url, timeout=180)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def coordinate(value: Any, index: int) -> float | None:
    if not isinstance(value, list) or len(value) <= index:
        return None
    try:
        return float(value[index])
    except (TypeError, ValueError):
        return None


def flatten_events(match_id: int, events: list[dict[str, Any]], frames: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    frame_map = {item.get("event_uuid"): item for item in (frames or [])}
    rows: list[dict[str, Any]] = []
    for event in events:
        event_type = ((event.get("type") or {}).get("name"))
        start = event.get("location")
        end = None
        if event_type == "Pass":
            end = (event.get("pass") or {}).get("end_location")
        elif event_type == "Carry":
            end = (event.get("carry") or {}).get("end_location")
        shot = event.get("shot") or {}
        freeze = (frame_map.get(event.get("id")) or {}).get("freeze_frame") or []
        rows.append({
            "match_id": match_id,
            "event_id": event.get("id"),
            "index": event.get("index"),
            "period": event.get("period"),
            "minute": event.get("minute"),
            "second": event.get("second"),
            "team": ((event.get("team") or {}).get("name")),
            "player": ((event.get("player") or {}).get("name")),
            "position": ((event.get("position") or {}).get("name")),
            "event_type": event_type,
            "under_pressure": bool(event.get("under_pressure") or False),
            "counterpress": bool(event.get("counterpress") or False),
            "start_x": coordinate(start, 0),
            "start_y": coordinate(start, 1),
            "end_x": coordinate(end, 0),
            "end_y": coordinate(end, 1),
            "pass_outcome": (((event.get("pass") or {}).get("outcome") or {}).get("name")),
            "shot_xg": shot.get("statsbomb_xg"),
            "shot_outcome": ((shot.get("outcome") or {}).get("name")),
            "visible_players_360": len(freeze),
            "visible_teammates_360": sum(bool(item.get("teammate")) for item in freeze),
            "visible_opponents_360": sum(not bool(item.get("teammate")) for item in freeze),
            "source": "Hudl StatsBomb Open Data",
        })
    return rows


def summarise_team_matches(events: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    events = events.copy()
    events["is_pass"] = events.event_type.eq("Pass")
    events["is_completed_pass"] = events.is_pass & events.pass_outcome.isna()
    events["is_shot"] = events.event_type.eq("Shot")
    events["is_pressure"] = events.event_type.eq("Pressure")
    events["is_carry"] = events.event_type.eq("Carry")
    events["progressive_action"] = (
        events.event_type.isin(["Pass", "Carry"])
        & events.start_x.notna()
        & events.end_x.notna()
        & ((events.end_x - events.start_x) >= 15)
    )
    summary = events.groupby(["match_id", "team"], as_index=False).agg(
        events=("event_id", "count"),
        passes=("is_pass", "sum"),
        completed_passes=("is_completed_pass", "sum"),
        shots=("is_shot", "sum"),
        xg=("shot_xg", "sum"),
        pressure_events=("is_pressure", "sum"),
        carries=("is_carry", "sum"),
        progressive_actions=("progressive_action", "sum"),
        under_pressure_events=("under_pressure", "sum"),
        counterpress_events=("counterpress", "sum"),
        events_with_360=("visible_players_360", lambda s: int((s > 0).sum())),
        mean_visible_players_360=("visible_players_360", "mean"),
    )
    summary["pass_completion"] = summary.completed_passes / summary.passes.replace(0, pd.NA)
    return summary.merge(matches, on="match_id", how="left")
