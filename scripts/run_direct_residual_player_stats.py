#!/usr/bin/env python3
"""Query the dedicated API-Football fixture-player endpoint for true residual fixtures.

This stage uses only the deduplicated physical residual (fixture_id + player_id),
queries each fixture at most once per terminal outcome, persists partial progress,
and never creates final rankings.
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

from scripts.run_adaptive_annual_extraction import flatten_target_players

API_BASE = "https://v3.football.api-sports.io"
RESIDUAL_PATH = Path("data/model_readiness/cache_rebuild/truly_unresolved_player_fixture_pairs.csv")
FALLBACK_PATH = Path("data/model_readiness/coverage_priority_fixtures.csv")
INVENTORY_PATH = Path("data/audits/exact_fixture_inventory.csv")
PROGRESS_PATH = Path("data/lake/direct_player_stats_progress.csv")
BATCH_DIR = Path("data/lake/batches")
RAW_DIR = Path("data/raw/direct_residual_players")
STATUS_PATH = Path("data/audits/direct_residual_player_stats_status.json")

TERMINAL = {
    "resolved_positive_minutes",
    "provider_endpoint_empty",
    "target_player_missing",
    "target_rows_without_positive_minutes",
}
ROLE_WEIGHT = {"GK": 6, "RB": 6, "CM": 5, "AM": 6, "RW": 6}


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_residual() -> pd.DataFrame:
    path = RESIDUAL_PATH if RESIDUAL_PATH.exists() else FALLBACK_PATH
    frame = pd.read_csv(path, low_memory=False)
    for column in ["fixture_id", "player_id"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["fixture_id", "player_id"]).copy()
    frame[["fixture_id", "player_id"]] = frame[["fixture_id", "player_id"]].astype(int)
    if "primary_position" not in frame:
        frame["primary_position"] = frame.get("resolved_role", "")
    if "priority_score" not in frame:
        frame["priority_score"] = 0.0
    return frame.drop_duplicates(["fixture_id", "player_id"])


def load_progress() -> pd.DataFrame:
    columns = [
        "fixture_id", "attempts", "last_run_utc", "status", "target_players",
        "response_team_blocks", "response_player_items", "target_rows",
        "positive_target_rows", "network_calls", "error",
    ]
    if not PROGRESS_PATH.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(PROGRESS_PATH, low_memory=False)
    frame["fixture_id"] = pd.to_numeric(frame.fixture_id, errors="coerce")
    frame = frame.dropna(subset=["fixture_id"]).copy()
    frame["fixture_id"] = frame.fixture_id.astype(int)
    frame["attempts"] = pd.to_numeric(frame.get("attempts"), errors="coerce").fillna(0).astype(int)
    return frame.drop_duplicates("fixture_id", keep="last")


class DirectClient:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.session = requests.Session()
        self.key = key
        self.calls = 0
        self.remaining: int | None = None
        self.daily_limit: int | None = None
        self.max_calls = max(0, int(os.getenv("MAX_NETWORK_REQUESTS", "200")))
        self.min_remaining = max(0, int(os.getenv("MIN_DAILY_REQUESTS_REMAINING", "5")))
        safe_rpm = max(1.0, float(os.getenv("API_SAFE_REQUESTS_PER_MINUTE", "120")))
        self.interval = 60.0 / safe_rpm
        self.last_call = 0.0

    def _headers(self, response: requests.Response) -> None:
        lower = {key.lower(): value for key, value in response.headers.items()}
        for header, attribute in [
            ("x-ratelimit-requests-remaining", "remaining"),
            ("x-ratelimit-requests-limit", "daily_limit"),
        ]:
            value = lower.get(header)
            if value is not None:
                try:
                    setattr(self, attribute, int(value))
                except ValueError:
                    pass

    def status(self) -> dict[str, Any]:
        response = self.session.get(
            f"{API_BASE}/status",
            headers={"x-apisports-key": self.key},
            timeout=90,
        )
        self._headers(response)
        response.raise_for_status()
        payload = response.json()
        requests_status = ((payload.get("response") or {}).get("requests") or {})
        if requests_status.get("limit_day") is not None:
            self.daily_limit = int(requests_status["limit_day"])
        if requests_status.get("current") is not None and self.daily_limit is not None:
            self.remaining = max(0, self.daily_limit - int(requests_status["current"]))
        return payload

    def get_players(self, fixture_id: int) -> dict[str, Any]:
        if self.calls >= self.max_calls:
            raise StopIteration("run_call_cap_reached")
        if self.remaining is not None and self.remaining <= self.min_remaining:
            raise StopIteration("daily_safety_reserve_reached")
        attempts = 0
        while True:
            attempts += 1
            wait = self.interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            response = self.session.get(
                f"{API_BASE}/fixtures/players",
                params={"fixture": fixture_id},
                headers={"x-apisports-key": self.key},
                timeout=120,
            )
            self.last_call = time.monotonic()
            self._headers(response)
            if response.status_code in {429, 500, 502, 503, 504} and attempts < 6:
                time.sleep(float(response.headers.get("retry-after") or min(60, 2**attempts)))
                continue
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or {}
            if errors and attempts < 6:
                text = json.dumps(errors).lower()
                if any(token in text for token in ("limit", "rate", "tempor", "timeout")):
                    time.sleep(min(60, 2**attempts))
                    continue
            if errors:
                raise RuntimeError(f"API-Football fixtures/players error: {errors}")
            self.calls += 1
            return payload


def fixture_series(row: pd.Series) -> pd.Series:
    values = row.to_dict()
    values.setdefault("league_name", "")
    values.setdefault("date_utc", values.get("match_date", ""))
    values.setdefault("in_current_window", True)
    values.setdefault("in_pre_world_cup_window", True)
    return pd.Series(values)


def save_progress(progress: pd.DataFrame) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    progress.sort_values("fixture_id").drop_duplicates("fixture_id", keep="last").to_csv(
        PROGRESS_PATH, index=False
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%dT%H%M%S")
    residual = load_residual()
    inventory = pd.read_csv(INVENTORY_PATH, low_memory=False)
    inventory["fixture_id"] = pd.to_numeric(inventory.fixture_id, errors="coerce")
    inventory = inventory.dropna(subset=["fixture_id"]).copy()
    inventory["fixture_id"] = inventory.fixture_id.astype(int)

    summary = residual.groupby("fixture_id", as_index=False).agg(
        target_players=("player_id", "nunique"),
        role_weight=("primary_position", lambda s: max([ROLE_WEIGHT.get(str(v), 1) for v in s] or [1])),
        declared_priority=("priority_score", "max"),
    )
    queue = inventory.merge(summary, on="fixture_id", how="inner")
    queue["priority"] = (
        pd.to_numeric(queue.declared_priority, errors="coerce").fillna(0) * 1000
        + queue.role_weight * 100
        + queue.target_players * 10
    )
    queue["date_sort"] = pd.to_datetime(queue.get("date_utc"), utc=True, errors="coerce")

    progress = load_progress()
    terminal_ids = set(progress.loc[progress.status.astype(str).isin(TERMINAL), "fixture_id"])
    queue = queue.loc[~queue.fixture_id.isin(terminal_ids)].copy()
    queue = queue.sort_values(["priority", "date_sort"], ascending=[False, False])

    client = DirectClient()
    client.status()
    quota_at_start = client.remaining
    usable_by_quota = (
        max(0, client.remaining - client.min_remaining)
        if client.remaining is not None else client.max_calls
    )
    queue = queue.head(min(client.max_calls, usable_by_quota))

    target_map = residual.groupby("fixture_id").player_id.apply(lambda s: set(s.astype(int))).to_dict()
    prior_attempts = progress.set_index("fixture_id")["attempts"].to_dict() if not progress.empty else {}
    rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for item in queue.itertuples(index=False):
        fixture_id = int(item.fixture_id)
        target_ids = target_map.get(fixture_id, set())
        try:
            payload = client.get_players(fixture_id)
        except StopIteration as exc:
            stopped_reason = str(exc)
            break
        except Exception as exc:
            progress_rows.append({
                "fixture_id": fixture_id,
                "attempts": int(prior_attempts.get(fixture_id, 0)) + 1,
                "last_run_utc": now.isoformat(),
                "status": "retryable_error",
                "target_players": len(target_ids),
                "response_team_blocks": 0,
                "response_player_items": 0,
                "target_rows": 0,
                "positive_target_rows": 0,
                "network_calls": client.calls,
                "error": str(exc)[:500],
            })
            continue

        (RAW_DIR / f"fixture_{fixture_id}_players.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        response = payload.get("response") or []
        player_items = sum(len(block.get("players") or []) for block in response)
        fixture = fixture_series(pd.Series(item._asdict()))
        target_rows = flatten_target_players(fixture, payload, target_ids)
        rows.extend(target_rows)
        positive_rows = sum(
            pd.to_numeric(pd.Series([row.get("minutes")]), errors="coerce").fillna(0).iloc[0] > 0
            for row in target_rows
        )
        returned_target_ids = {int(row["player_id"]) for row in target_rows}
        if positive_rows:
            state = "resolved_positive_minutes"
        elif not response or player_items == 0:
            state = "provider_endpoint_empty"
        elif not returned_target_ids:
            state = "target_player_missing"
        else:
            state = "target_rows_without_positive_minutes"
        progress_rows.append({
            "fixture_id": fixture_id,
            "attempts": int(prior_attempts.get(fixture_id, 0)) + 1,
            "last_run_utc": now.isoformat(),
            "status": state,
            "target_players": len(target_ids),
            "response_team_blocks": len(response),
            "response_player_items": player_items,
            "target_rows": len(target_rows),
            "positive_target_rows": int(positive_rows),
            "network_calls": client.calls,
            "error": "",
        })
        progress = pd.concat([progress, pd.DataFrame([progress_rows[-1]])], ignore_index=True)
        save_progress(progress)

    if progress_rows:
        progress = pd.concat([progress, pd.DataFrame(progress_rows)], ignore_index=True)
        save_progress(progress)
    if rows:
        BATCH_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).drop_duplicates(["fixture_id", "player_id"], keep="last").to_csv(
            BATCH_DIR / f"direct_residual_{run_id}_players.csv.gz",
            index=False,
            compression="gzip",
        )

    final = load_progress()
    current_ids = set(summary.fixture_id.astype(int))
    current = final.loc[final.fixture_id.isin(current_ids)].copy()
    status_counts = current.status.value_counts().to_dict() if not current.empty else {}
    status = {
        "status": "direct_residual_player_stats_completed",
        "generated_at_utc": now.isoformat(),
        "endpoint": "fixtures/players",
        "physical_residual_pairs_at_start": int(len(residual)),
        "physical_residual_fixtures_at_start": int(summary.fixture_id.nunique()),
        "fixtures_queued_this_run": int(len(queue)),
        "network_calls_this_run": int(client.calls),
        "quota_daily_limit_reported": client.daily_limit,
        "quota_remaining_at_start": quota_at_start,
        "quota_remaining_at_end": client.remaining,
        "daily_safety_reserve": client.min_remaining,
        "stopped_reason": stopped_reason,
        "player_rows_written": int(len(rows)),
        "positive_player_rows_written": int(sum(pd.to_numeric(pd.Series([r.get('minutes')]), errors='coerce').fillna(0).iloc[0] > 0 for r in rows)),
        "terminal_fixture_status_counts": status_counts,
        "terminal_fixtures": int(current.status.astype(str).isin(TERMINAL).sum()) if not current.empty else 0,
        "remaining_unattempted_or_retryable_fixtures": int((~current.status.astype(str).isin(TERMINAL)).sum()) + int(len(current_ids - set(current.fixture_id))) if not current.empty else int(len(current_ids)),
        "rankings_allowed": False,
        "next_action": "rebuild coverage and selection gate from newly recovered player rows",
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
