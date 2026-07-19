#!/usr/bin/env python3
"""Build a match-context catalog from processed fixtures and cached metadata."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

FIXTURES_PATH = Path("data/processed/fixtures.csv")
RAW_GLOBS = (
    "data/raw/world_cup_fixture_metadata/*.json",
    "data/raw/adaptive_annual/bundles/*.json",
    "data/raw/fixture_inventory/*.json",
)
OUT_DIR = Path("data/enrichment/context")
METADATA_COLUMNS = [
    "fixture_id",
    "api_date",
    "api_timestamp",
    "api_timezone",
    "referee",
    "venue_id",
    "venue_name",
    "venue_city",
    "league_id",
    "league_name",
    "league_country",
    "home_team_api",
    "away_team_api",
]


def iter_items() -> Iterable[dict[str, Any]]:
    seen_paths: set[Path] = set()
    for pattern in RAW_GLOBS:
        for path in Path(".").glob(pattern):
            if path in seen_paths or not path.is_file():
                continue
            seen_paths.add(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            for item in payload.get("response") or []:
                if isinstance(item, dict):
                    yield item


def flatten(item: dict[str, Any]) -> dict[str, Any] | None:
    fixture = item.get("fixture") or {}
    fixture_id = fixture.get("id")
    if fixture_id is None:
        return None
    venue = fixture.get("venue") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    return {
        "fixture_id": int(fixture_id),
        "api_date": fixture.get("date"),
        "api_timestamp": fixture.get("timestamp"),
        "api_timezone": fixture.get("timezone"),
        "referee": fixture.get("referee"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "venue_city": venue.get("city"),
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "league_country": league.get("country"),
        "home_team_api": ((teams.get("home") or {}).get("name")),
        "away_team_api": ((teams.get("away") or {}).get("name")),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not FIXTURES_PATH.exists():
        status = {"status": "waiting_for_processed_fixtures"}
        (OUT_DIR / "fixture_context_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        return

    fixtures = pd.read_csv(FIXTURES_PATH)
    metadata_rows = [row for item in iter_items() if (row := flatten(item)) is not None]
    metadata = pd.DataFrame(metadata_rows, columns=METADATA_COLUMNS)
    if not metadata.empty:
        metadata = metadata.drop_duplicates("fixture_id", keep="last")
    catalog = fixtures.merge(metadata, on="fixture_id", how="left")
    catalog["metadata_available"] = catalog["venue_city"].notna() | catalog["venue_name"].notna()
    catalog["context_source"] = "API-Football fixture metadata"
    catalog["context_in_main_v1"] = False
    catalog.to_csv(OUT_DIR / "fixture_context_catalog.csv", index=False)
    status = {
        "status": "fixture_context_catalog_built",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixtures": int(len(catalog)),
        "fixtures_with_venue_metadata": int(catalog["metadata_available"].sum()),
        "fixtures_missing_venue_metadata": int((~catalog["metadata_available"]).sum()),
        "context_in_main_v1": False,
    }
    (OUT_DIR / "fixture_context_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
