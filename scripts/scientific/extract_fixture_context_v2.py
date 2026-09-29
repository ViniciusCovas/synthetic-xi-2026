#!/usr/bin/env python3
"""Recover fixture, opponent and competition context for the v2 external-validity model.

The script is resumable and quota-aware. It scans the cached player-detail batches,
keeps fixtures involving reviewed candidate players in the frozen windows, requests up
to 20 fixture IDs per API-FOOTBALL call, and persists only the metadata needed for
opponent/competition adjustment.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BATCH_DIR = Path("data/lake/batches")
CANDIDATES = Path("data/audits/position_ontology_v3/final_candidate_roles.csv")
OUT = Path("data/lake/v2_fixture_context.csv.gz")
PROGRESS = Path("data/lake/v2_fixture_context_progress.csv")
STATUS = Path("data/audits/external_validity_v2/fixture_context_status.json")
API_BASE = "https://v3.football.api-sports.io"
COMPLETED = {"FT", "AET", "PEN"}


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def candidate_ids() -> set[int]:
    if not CANDIDATES.exists():
        raise RuntimeError(f"missing candidate table: {CANDIDATES}")
    frame = pd.read_csv(CANDIDATES, usecols=lambda c: c in {"player_id", "final_candidate_eligible"})
    frame["player_id"] = pd.to_numeric(frame.player_id, errors="coerce")
    if "final_candidate_eligible" in frame:
        frame = frame.loc[truth(frame.final_candidate_eligible)]
    return set(frame.player_id.dropna().astype(int))


def discover_fixture_ids(players: set[int]) -> list[int]:
    fixture_ids: set[int] = set()
    files = sorted(BATCH_DIR.glob("*players*.csv*"))
    if not files:
        raise RuntimeError("no cached player-detail batches were found")
    for path in files:
        try:
            header = pd.read_csv(path, nrows=0).columns
            wanted = [c for c in ["fixture_id", "player_id", "in_current_window", "in_pre_world_cup_window"] if c in header]
            if not {"fixture_id", "player_id"}.issubset(wanted):
                continue
            frame = pd.read_csv(path, usecols=wanted, low_memory=False)
        except Exception as exc:
            print(f"skip unreadable batch {path}: {exc}")
            continue
        frame["player_id"] = pd.to_numeric(frame.player_id, errors="coerce")
        frame["fixture_id"] = pd.to_numeric(frame.fixture_id, errors="coerce")
        mask = frame.player_id.isin(players)
        window_columns = [c for c in ["in_current_window", "in_pre_world_cup_window"] if c in frame]
        if window_columns:
            window_mask = pd.Series(False, index=frame.index)
            for column in window_columns:
                window_mask |= truth(frame[column])
            mask &= window_mask
        fixture_ids.update(frame.loc[mask, "fixture_id"].dropna().astype(int).tolist())
    return sorted(fixture_ids)


def load_existing() -> pd.DataFrame:
    if not OUT.exists():
        return pd.DataFrame()
    frame = pd.read_csv(OUT, low_memory=False)
    frame["fixture_id"] = pd.to_numeric(frame.fixture_id, errors="coerce")
    return frame.dropna(subset=["fixture_id"]).drop_duplicates("fixture_id", keep="last")


def parse_fixture(item: dict[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    score = item.get("score") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    status = fixture.get("status") or {}
    venue = fixture.get("venue") or {}
    return {
        "fixture_id": fixture.get("id"),
        "date_utc": fixture.get("date"),
        "timestamp": fixture.get("timestamp"),
        "status_short": status.get("short"),
        "status_long": status.get("long"),
        "elapsed": status.get("elapsed"),
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "league_country": league.get("country"),
        "season": league.get("season"),
        "round": league.get("round"),
        "home_team_id": home.get("id"),
        "home_team_name": home.get("name"),
        "away_team_id": away.get("id"),
        "away_team_name": away.get("name"),
        "home_winner": home.get("winner"),
        "away_winner": away.get("winner"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "halftime_home": (score.get("halftime") or {}).get("home"),
        "halftime_away": (score.get("halftime") or {}).get("away"),
        "fulltime_home": (score.get("fulltime") or {}).get("home"),
        "fulltime_away": (score.get("fulltime") or {}).get("away"),
        "extratime_home": (score.get("extratime") or {}).get("home"),
        "extratime_away": (score.get("extratime") or {}).get("away"),
        "penalty_home": (score.get("penalty") or {}).get("home"),
        "penalty_away": (score.get("penalty") or {}).get("away"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "venue_city": venue.get("city"),
        "provider_fixture_complete": status.get("short") in COMPLETED,
    }


def remaining_from_headers(headers: requests.structures.CaseInsensitiveDict) -> int | None:
    for key in ("x-ratelimit-requests-remaining", "x-ratelimit-remaining", "x-requests-remaining"):
        value = headers.get(key)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                pass
    return None


def save(existing: pd.DataFrame, new_rows: list[dict[str, Any]], progress_rows: list[dict[str, Any]]) -> pd.DataFrame:
    parts = [frame for frame in [existing, pd.DataFrame(new_rows)] if not frame.empty]
    merged = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not merged.empty:
        merged["fixture_id"] = pd.to_numeric(merged.fixture_id, errors="coerce")
        merged = merged.dropna(subset=["fixture_id"]).sort_values("fixture_id").drop_duplicates("fixture_id", keep="last")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(OUT, index=False, compression="gzip")
    if progress_rows:
        progress = pd.DataFrame(progress_rows)
        if PROGRESS.exists():
            old = pd.read_csv(PROGRESS, low_memory=False)
            progress = pd.concat([old, progress], ignore_index=True)
        progress.to_csv(PROGRESS, index=False)
    return merged


def main() -> None:
    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        raise RuntimeError("API_FOOTBALL_KEY is required")
    max_requests = int(os.getenv("MAX_NETWORK_REQUESTS", "600"))
    min_remaining = int(os.getenv("MIN_DAILY_REQUESTS_REMAINING", "300"))
    max_per_minute = max(1, int(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "160")))
    sleep_seconds = max(0.35, 60.0 / max_per_minute)

    target_ids = discover_fixture_ids(candidate_ids())
    existing = load_existing()
    completed_ids = set(pd.to_numeric(existing.get("fixture_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    pending = [fixture_id for fixture_id in target_ids if fixture_id not in completed_ids]
    print(json.dumps({"target_fixtures": len(target_ids), "already_present": len(completed_ids & set(target_ids)), "pending": len(pending)}, indent=2))

    session = requests.Session()
    session.headers.update({"x-apisports-key": api_key})
    rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    requests_used = 0
    last_remaining: int | None = None
    stop_reason = "queue_exhausted"

    for start in range(0, len(pending), 20):
        if requests_used >= max_requests:
            stop_reason = "max_network_requests_reached"
            break
        chunk = pending[start:start + 20]
        id_string = "-".join(map(str, chunk))
        started = datetime.now(timezone.utc).isoformat()
        try:
            response = session.get(f"{API_BASE}/fixtures", params={"ids": id_string}, timeout=90)
            requests_used += 1
            last_remaining = remaining_from_headers(response.headers)
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(str(payload["errors"]))
            returned = payload.get("response") or []
            parsed = [parse_fixture(item) for item in returned]
            rows.extend(parsed)
            progress_rows.append({
                "requested_at_utc": started,
                "fixture_ids": id_string,
                "requested_count": len(chunk),
                "returned_count": len(parsed),
                "http_status": response.status_code,
                "provider_remaining": last_remaining,
                "success": True,
                "error": "",
            })
            returned_ids = {int(row["fixture_id"]) for row in parsed if row.get("fixture_id") is not None}
            for fixture_id in chunk:
                if fixture_id not in returned_ids:
                    errors.append({"fixture_id": fixture_id, "error": "provider_response_missing_fixture"})
        except Exception as exc:
            errors.extend({"fixture_id": fixture_id, "error": str(exc)} for fixture_id in chunk)
            progress_rows.append({
                "requested_at_utc": started,
                "fixture_ids": id_string,
                "requested_count": len(chunk),
                "returned_count": 0,
                "http_status": getattr(locals().get("response", None), "status_code", None),
                "provider_remaining": last_remaining,
                "success": False,
                "error": str(exc),
            })
        if requests_used % 10 == 0:
            existing = save(existing, rows, progress_rows)
            rows.clear()
            progress_rows.clear()
        if last_remaining is not None and last_remaining <= min_remaining:
            stop_reason = "provider_daily_margin_reached"
            break
        time.sleep(sleep_seconds)

    existing = save(existing, rows, progress_rows)
    present_ids = set(pd.to_numeric(existing.get("fixture_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    status = {
        "status": "v2_fixture_context_extraction_completed" if set(target_ids).issubset(present_ids) else "v2_fixture_context_extraction_partial",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_fixtures": len(target_ids),
        "fixture_context_rows": int(len(existing)),
        "target_fixtures_present": len(set(target_ids) & present_ids),
        "target_coverage": len(set(target_ids) & present_ids) / len(target_ids) if target_ids else 0.0,
        "network_requests_used_this_run": requests_used,
        "provider_remaining_last_seen": last_remaining,
        "stop_reason": stop_reason,
        "errors_this_run": len(errors),
        "output": str(OUT),
        "next_action": "build opponent/competition-strength profiles" if set(target_ids).issubset(present_ids) else "resume fixture-context extraction",
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        pd.DataFrame(errors).drop_duplicates().to_csv(STATUS.parent / "fixture_context_errors.csv", index=False)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
