#!/usr/bin/env python3
"""Fetch complete provider line-ups for ontology-v3 priority fixtures.

One provider call recovers both complete team line-ups for a fixture. The extractor is
quota-aware and resumable. After every audit it gives additional priority to CM, AM,
RW and LW candidates that are close to the 900-minute positional threshold, because
those are the remaining role-pool deficits. It still retains high-impact and general
candidate coverage as secondary criteria.
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
ROLE_EVIDENCE = Path("data/audits/position_ontology_v3/complete_lineup_player_role_minutes.csv")
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
BATCH = Path("data/lake/batches/batch_full_provider_lineups.csv.gz")
PROGRESS = Path("data/lake/full_lineup_extraction_progress.csv")
STATUS = Path("data/audits/position_ontology_v3/full_lineup_extraction_status.json")
FOCUS_ROLES = {"CM", "AM", "RW", "LW"}


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


def text_role(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name].astype("string").str.strip().str.upper()
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def build_player_focus(priority: pd.DataFrame) -> pd.DataFrame:
    """Attach preregistered, outcome-blind extraction priority features by player."""
    player_ids = pd.to_numeric(priority.player_id, errors="coerce").dropna().astype(int).unique()
    focus = pd.DataFrame({"player_id": player_ids})
    focus["frontier_role"] = pd.NA
    focus["complete_primary_role"] = pd.NA
    focus["complete_primary_minutes"] = 0.0
    focus["focus_role_candidate"] = False
    focus["near_900_focus"] = False

    if FRONTIER.exists():
        frontier = pd.read_csv(FRONTIER, low_memory=False)
        frontier["player_id"] = pd.to_numeric(frontier.get("player_id"), errors="coerce")
        frontier = frontier.dropna(subset=["player_id"]).copy()
        frontier["player_id"] = frontier.player_id.astype(int)
        frontier["frontier_role"] = text_role(frontier, ["resolved_role", "role"])
        frontier = frontier.sort_values("player_id").drop_duplicates("player_id")
        focus = focus.drop(columns=["frontier_role"]).merge(
            frontier[["player_id", "frontier_role"]], on="player_id", how="left"
        )

    if ROLE_EVIDENCE.exists():
        evidence = pd.read_csv(ROLE_EVIDENCE, low_memory=False)
        evidence["player_id"] = pd.to_numeric(evidence.get("player_id"), errors="coerce")
        evidence["role_minutes"] = pd.to_numeric(evidence.get("role_minutes"), errors="coerce").fillna(0.0)
        evidence["role_observations"] = pd.to_numeric(evidence.get("role_observations"), errors="coerce").fillna(0.0)
        evidence["role"] = text_role(evidence, ["role"])
        evidence = evidence.dropna(subset=["player_id"]).copy()
        evidence["player_id"] = evidence.player_id.astype(int)
        evidence = evidence.sort_values(
            ["player_id", "role_minutes", "role_observations", "role"],
            ascending=[True, False, False, True],
        )
        primary = evidence.drop_duplicates("player_id").rename(columns={
            "role": "complete_primary_role",
            "role_minutes": "complete_primary_minutes",
        })
        focus = focus.drop(columns=["complete_primary_role", "complete_primary_minutes"]).merge(
            primary[["player_id", "complete_primary_role", "complete_primary_minutes"]],
            on="player_id", how="left",
        )
        focus["complete_primary_minutes"] = pd.to_numeric(
            focus.complete_primary_minutes, errors="coerce"
        ).fillna(0.0)

    frontier_focus = focus.frontier_role.isin(FOCUS_ROLES)
    complete_focus = focus.complete_primary_role.isin(FOCUS_ROLES)
    focus["focus_role_candidate"] = frontier_focus | complete_focus
    focus["near_900_focus"] = (
        focus.focus_role_candidate
        & focus.complete_primary_minutes.ge(300)
        & focus.complete_primary_minutes.lt(900)
    )
    return focus


def main() -> None:
    if not PRIORITY.exists():
        raise RuntimeError("run audit_complete_lineups_v3.py before extraction")
    priority = pd.read_csv(PRIORITY, low_memory=False)
    priority["fixture_id"] = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority["player_id"] = pd.to_numeric(priority.player_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id", "player_id"]).copy()
    priority["fixture_id"] = priority.fixture_id.astype(int)
    priority["player_id"] = priority.player_id.astype(int)
    priority["minutes_observed"] = pd.to_numeric(
        priority.get("minutes_observed"), errors="coerce"
    ).fillna(0.0)
    priority["high_impact_current_release"] = (
        priority.get("high_impact_current_release", False)
        .astype(str).str.lower().isin({"true", "1", "yes"})
    )

    player_focus = build_player_focus(priority)
    priority = priority.merge(player_focus, on="player_id", how="left")
    for column in ("focus_role_candidate", "near_900_focus"):
        priority[column] = priority[column].fillna(False).astype(bool)

    queue = priority.groupby("fixture_id", as_index=False).agg(
        near_900_focus_players=("near_900_focus", "sum"),
        focus_role_players=("focus_role_candidate", "sum"),
        high_impact_players=("high_impact_current_release", "sum"),
        candidate_players=("player_id", "nunique"),
        candidate_minutes=("minutes_observed", "sum"),
    )
    queue = queue.sort_values(
        [
            "near_900_focus_players", "focus_role_players", "high_impact_players",
            "candidate_players", "candidate_minutes", "fixture_id",
        ],
        ascending=[False, False, False, False, False, True],
    )

    progress = load_progress()
    completed = set(
        progress.loc[progress.status.isin(["completed", "endpoint_empty"]), "fixture_id"]
        .astype(int)
    )
    queue = queue.loc[~queue.fixture_id.isin(completed)].copy()

    client = Client()
    new_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    quota_stopped = False
    processed_focus_fixtures = 0
    processed_near_900_fixtures = 0
    for item in queue.itertuples(index=False):
        fixture_id = int(item.fixture_id)
        try:
            payload = client.lineups(fixture_id)
            rows = flatten(fixture_id, payload)
            status = "completed" if rows else "endpoint_empty"
            new_rows.extend(rows)
            processed_focus_fixtures += int(item.focus_role_players > 0)
            processed_near_900_fixtures += int(item.near_900_focus_players > 0)
            progress_rows.append({
                "fixture_id": fixture_id, "status": status, "rows": len(rows),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            print(
                f"fixture={fixture_id} rows={len(rows)} near900={item.near_900_focus_players} "
                f"focus={item.focus_role_players} calls={client.calls} remaining={client.remaining}"
            )
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
    groups = (
        starters.groupby(["fixture_id", "team_id"]).player_id.nunique()
        if not starters.empty else pd.Series(dtype=int)
    )
    status = {
        "status": "priority_full_lineup_extraction_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "priority_policy": {
            "primary": "CM/AM/RW/LW candidates with 300-899 complete-lineup role minutes",
            "secondary": "other CM/AM/RW/LW candidates",
            "tertiary": "high-impact and general candidate coverage",
            "outcome_blind": True,
        },
        "network_calls": client.calls,
        "provider_remaining": client.remaining,
        "quota_stopped": quota_stopped,
        "queue_before_batch": int(len(queue)),
        "fixtures_processed_this_batch": int(len(progress_rows)),
        "processed_focus_role_fixtures": int(processed_focus_fixtures),
        "processed_near_900_focus_fixtures": int(processed_near_900_fixtures),
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
