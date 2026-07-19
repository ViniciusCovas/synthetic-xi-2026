#!/usr/bin/env python3
"""Fetch compact API-Football fixture metadata in bundles of up to 20 IDs.

This module is separate from player extraction. It only retrieves match-level
metadata needed by contextual enrichments: venue, city, referee and timezone.
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

from scripts.enrichment.common import cache_path

API_BASE = "https://v3.football.api-sports.io"
FIXTURES_PATH = Path("data/processed/fixtures.csv")
RAW_DIR = Path("data/raw/world_cup_fixture_metadata")
STATUS_PATH = Path("data/enrichment/context/fixture_metadata_status.json")


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        write_status({"status": "waiting_for_api_football_key", "network_calls": 0})
        return
    if not FIXTURES_PATH.exists():
        write_status({"status": "waiting_for_processed_fixtures", "network_calls": 0})
        return

    fixture_ids = pd.read_csv(FIXTURES_PATH)["fixture_id"].dropna().astype(int).drop_duplicates().tolist()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    headers = {"x-apisports-key": key}
    status_response = session.get(f"{API_BASE}/status", headers=headers, timeout=90)
    status_response.raise_for_status()
    request_info = ((status_response.json().get("response") or {}).get("requests") or {})
    limit_day = int(request_info.get("limit_day") or 0)
    current = int(request_info.get("current") or 0)
    remaining = max(0, limit_day - current) if limit_day else None
    reserve = int(os.getenv("FIXTURE_METADATA_MIN_REMAINING", "20"))
    if remaining is not None and remaining <= reserve:
        write_status({
            "status": "waiting_for_daily_reset",
            "fixtures_total": len(fixture_ids),
            "daily_limit_reported": limit_day,
            "quota_remaining_reported": remaining,
            "network_calls": 0,
        })
        return

    max_calls = int(os.getenv("FIXTURE_METADATA_MAX_CALLS", "10"))
    interval = 60.0 / max(float(os.getenv("API_SAFE_REQUESTS_PER_MINUTE", "120")), 1.0)
    last_call = 0.0
    calls = fetched = cached = 0
    errors: list[dict[str, Any]] = []

    for start in range(0, len(fixture_ids), 20):
        ids = fixture_ids[start:start + 20]
        path = cache_path(RAW_DIR, "fixtures", ids)
        if path.exists():
            cached += len(ids)
            continue
        if calls >= max_calls or (remaining is not None and remaining <= reserve):
            break
        wait = interval - (time.monotonic() - last_call)
        if wait > 0:
            time.sleep(wait)
        response = session.get(
            f"{API_BASE}/fixtures",
            params={"ids": "-".join(map(str, ids))},
            headers=headers,
            timeout=120,
        )
        last_call = time.monotonic()
        header_remaining = response.headers.get("x-ratelimit-requests-remaining")
        if header_remaining is not None:
            try:
                remaining = int(header_remaining)
            except ValueError:
                pass
        if response.status_code == 429:
            errors.append({"fixture_ids": ids, "error": "rate_limited"})
            break
        response.raise_for_status()
        payload = response.json()
        api_errors = payload.get("errors") or {}
        if api_errors:
            errors.append({"fixture_ids": ids, "error": api_errors})
            continue
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        calls += 1
        fetched += len(payload.get("response") or [])

    write_status({
        "status": "fixture_metadata_fetch_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixtures_total": len(fixture_ids),
        "fixtures_returned": fetched,
        "fixtures_already_cached": cached,
        "network_calls": calls,
        "daily_limit_reported": limit_day,
        "quota_remaining_reported": remaining,
        "errors": errors,
        "methodological_role": "contextual enrichment only; not an input to Synthetic XI v1.0 selection gates",
    })


if __name__ == "__main__":
    main()
