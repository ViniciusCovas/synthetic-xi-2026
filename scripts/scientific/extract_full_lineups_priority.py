#!/usr/bin/env python3
"""Fetch complete provider line-ups for the ontology-v3 priority fixtures.

One provider call recovers both complete team line-ups for a fixture. The script is
quota-aware, resumable and stores every starter/substitute rather than filtering to the
target players that motivated the request.
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

API_BASE = "https://v3.football.api-sports.io"
PRIORITY = Path("data/audits/position_ontology_v3/lineup_extraction_priority.csv")
BATCH = Path("data/lake/batches/batch_full_provider_lineups.csv.gz")
PROGRESS = Path("data/lake/full_lineup_extraction_progress.csv")
STATUS = Path("data/audits/position_ontology_v3/full_lineup_extraction_status.json")


class QuotaStop(RuntimeError):
    pass


class Client:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("API_FOOTBALL_KEY is required")
        self.session = requests.Session()
        self.key = key
        self.calls = 0
        self.remaining: int | None = None
        self.max_calls = int(os.getenv("MAX_NETWORK_REQUESTS", "800"))
        self.min_remaining = int(os.getenv("MIN_DAILY_REQUESTS_REMAINING", "500"))
        self.interval = 60.0 / float(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "175"))
        self.last_call = 0.0

    def lineups(self, fixture_id: int) -> dict[str, Any]:
        if self.calls >= self.max_calls:
            raise QuotaStop("batch call limit reached")
        if self.remaining is not None and self.remaining <= self.min_remaining:
            raise QuotaStop("daily quota safety margin reached")
        attempts = 0
        while True:
            attempts += 1
            wait = self.interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            response = self.session.get(
                f"{API_BASE}/fixtures/lineups",
                params={"fixture": fixture_id},
                headers={"x-apisports-key": self.key},
                timeout=90,
            )
            self.last_call = time.monotonic()
            remaining = response.headers.get("x-ratelimit-requests-remaining")
            if remaining is not None:
                try:
                    self.remaining = int(remaining)
                except ValueError:
                    pass
            if response.status_code in {429, 500, 502, 503, 504} and attempts < 6:
                time.sleep(float(response.headers.get("retry-after") or min(60, 2**attempts)))
                continue
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or {}
            if errors and attempts < 6:
                text = json.dumps(errors).lower()
                if "limit" in text or "rate" in text or "tempor" in text:
                    time.sleep(min(60, 2**attempts))
                    continue
            if errors:
                raise RuntimeError(f"provider errors for fixture {fixture_id}: {errors}")
            self.calls += 1
            return payload


def flatten(fixture_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for block in payload.get("response") or []:
        team = block.get("team") or {}
        if team.get("id") is None:
            continue
        for source, entries in (
            ("startXI", block.get("startXI") or []),
            ("substitutes", block.get("substitutes") or []),
        ):
            for entry in entries:
                player = (entry or {}).get("player") or {}
                if player.get("id") is None:
                    continue
                rows.append({
                    "fixture_id": int(fixture_id),
                    "team_id": int(team["id"]),
                    "team_name": team.get("name"),
                    "formation": block.get("formation"),
                    "lineup_source": source,
                    "player_id": int(player["id"]),
                    "player_name": player.get("name"),
                    "number": player.get("number"),
                    "lineup_position": player.get("pos"),
                    "grid": player.get("grid"),
                    "full_lineup_provider_recovery": True,
                })
    return rows


def load_progress() -> pd.DataFrame:
    if not PROGRESS.exists():
        return pd.DataFrame(columns=["fixture_id", "status", "rows", "updated_at_utc"])
    frame = pd.read_csv(PROGRESS)
    return frame.drop_duplicates("fixture_id", keep="last")


def main() -> None:
    if not PRIORITY.exists():
        raise RuntimeError("run audit_complete_lineups_v3.py before extraction")
    priority = pd.read_csv(PRIORITY, low_memory=False)
    priority["fixture_id"] = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id"]).copy()
    priority["fixture_id"] = priority.fixture_id.astype(int)
    priority["minutes_observed"] = pd.to_numeric(priority.get("minutes_observed"), errors="coerce").fillna(0.0)
    priority["high_impact_current_release"] = priority.get("high_impact_current_release", False).astype(str).str.lower().isin({"true", "1", "yes"})
    queue = priority.groupby("fixture_id", as_index=False).agg(
        high_impact_players=("high_impact_current_release", "sum"),
        candidate_players=("player_id", "nunique"),
        candidate_minutes=("minutes_observed", "sum"),
    )
    queue = queue.sort_values(
        ["high_impact_players", "candidate_players", "candidate_minutes", "fixture_id"],
        ascending=[False, False, False, True],
    )

    progress = load_progress()
    completed = set(progress.loc[progress.status.isin(["completed", "endpoint_empty"]), "fixture_id"].astype(int))
    queue = queue.loc[~queue.fixture_id.isin(completed)].copy()

    client = Client()
    new_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    quota_stopped = False
    for item in queue.itertuples(index=False):
        fixture_id = int(item.fixture_id)
        try:
            payload = client.lineups(fixture_id)
            rows = flatten(fixture_id, payload)
            status = "completed" if rows else "endpoint_empty"
            new_rows.extend(rows)
            progress_rows.append({
                "fixture_id": fixture_id, "status": status, "rows": len(rows),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            print(f"fixture={fixture_id} rows={len(rows)} calls={client.calls} remaining={client.remaining}")
        except QuotaStop as exc:
            quota_stopped = True
            print(str(exc))
            break
        except Exception as exc:
            errors.append({"fixture_id": fixture_id, "error": str(exc)})
            progress_rows.append({
                "fixture_id": fixture_id, "status": "error", "rows": 0,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            })

    new = pd.DataFrame(new_rows)
    if BATCH.exists():
        old = pd.read_csv(BATCH, low_memory=False)
        combined = pd.concat([old, new], ignore_index=True) if not new.empty else old
    else:
        combined = new
    if combined.empty:
        combined = pd.DataFrame(columns=[
            "fixture_id", "team_id", "team_name", "formation", "lineup_source",
            "player_id", "player_name", "number", "lineup_position", "grid",
            "full_lineup_provider_recovery",
        ])
    else:
        combined = combined.drop_duplicates(
            ["fixture_id", "team_id", "lineup_source", "player_id"], keep="last"
        ).sort_values(["fixture_id", "team_id", "lineup_source", "player_id"])
    BATCH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(BATCH, index=False, compression="gzip")

    updated_progress = pd.concat([progress, pd.DataFrame(progress_rows)], ignore_index=True)
    updated_progress = updated_progress.drop_duplicates("fixture_id", keep="last")
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    updated_progress.to_csv(PROGRESS, index=False)

    starters = combined.loc[combined.lineup_source.eq("startXI")]
    groups = starters.groupby(["fixture_id", "team_id"]).player_id.nunique() if not starters.empty else pd.Series(dtype=int)
    status = {
        "status": "priority_full_lineup_extraction_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": client.calls,
        "provider_remaining": client.remaining,
        "quota_stopped": quota_stopped,
        "queue_before_batch": int(len(queue)),
        "fixtures_processed_this_batch": int(len(progress_rows)),
        "new_rows_this_batch": int(len(new)),
        "total_recovered_rows": int(len(combined)),
        "total_fixture_team_groups": int(len(groups)),
        "groups_with_exactly_11_starters": int(groups.eq(11).sum()),
        "errors": errors[:100],
        "remaining_priority_fixtures": int(max(0, len(queue) - len(progress_rows))),
        "output_batch": str(BATCH),
        "progress_file": str(PROGRESS),
        "next_action": "rerun the ontology-v3 complete-lineup audit",
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
