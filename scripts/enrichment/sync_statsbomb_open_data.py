#!/usr/bin/env python3
"""Synchronise an auditable Hudl StatsBomb Open Data development sample."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from scripts.enrichment.statsbomb_open import flatten_events, get_json, summarise_team_matches

OUT_DIR = Path("data/enrichment/statsbomb")


def match_row(match: dict[str, Any], competition: Any) -> dict[str, Any]:
    metadata = match.get("metadata") or {}
    return {
        "match_id": int(match["match_id"]),
        "competition_id": int(competition.competition_id),
        "season_id": int(competition.season_id),
        "competition_name": competition.competition_name,
        "season_name": competition.season_name,
        "match_date": match.get("match_date"),
        "kick_off": match.get("kick_off"),
        "home_team": ((match.get("home_team") or {}).get("home_team_name")),
        "away_team": ((match.get("away_team") or {}).get("away_team_name")),
        "home_score": match.get("home_score"),
        "away_score": match.get("away_score"),
        "stadium": ((match.get("stadium") or {}).get("name")),
        "referee": ((match.get("referee") or {}).get("name")),
        "data_version": metadata.get("data_version"),
        "shot_fidelity_version": metadata.get("shot_fidelity_version"),
        "xy_fidelity_version": metadata.get("xy_fidelity_version"),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    competitions = get_json(session, "competitions.json", "competitions") or []
    comp_df = pd.json_normalize(competitions)
    comp_df.to_csv(OUT_DIR / "open_competitions.csv", index=False)

    candidates = comp_df[
        comp_df["competition_gender"].astype(str).eq("male")
        & comp_df["competition_international"].fillna(False).astype(bool)
        & comp_df["competition_name"].astype(str).str.contains("World Cup|Euro", case=False, regex=True)
    ].copy()
    candidates["season_sort"] = candidates["season_name"].astype(str).str.extract(r"(\d{4})")[0].fillna("0").astype(int)
    candidates = candidates.sort_values(["season_sort", "match_available_360"], ascending=[False, False])
    selected = candidates.head(int(os.getenv("STATSBOMB_OPEN_COMPETITIONS", "2")))

    match_rows: list[dict[str, Any]] = []
    for competition in selected.itertuples(index=False):
        matches = get_json(
            session,
            f"matches/{int(competition.competition_id)}/{int(competition.season_id)}.json",
            "matches",
        ) or []
        match_rows.extend(match_row(match, competition) for match in matches)
    matches_df = pd.DataFrame(match_rows)
    matches_df.to_csv(OUT_DIR / "open_matches_selected.csv", index=False)

    sample_n = int(os.getenv("STATSBOMB_OPEN_SAMPLE_MATCHES", "3"))
    sample = matches_df.sort_values("match_date", ascending=False).head(sample_n) if not matches_df.empty else matches_df
    event_rows: list[dict[str, Any]] = []
    for match in sample.itertuples(index=False):
        events = get_json(session, f"events/{int(match.match_id)}.json", "events") or []
        frames = get_json(session, f"three-sixty/{int(match.match_id)}.json", "frames")
        event_rows.extend(flatten_events(int(match.match_id), events, frames))
    events_df = pd.DataFrame(event_rows)
    if not events_df.empty:
        events_df.to_csv(OUT_DIR / "open_event_sample.csv.gz", index=False, compression="gzip")
    features = summarise_team_matches(events_df, matches_df)
    features.to_csv(OUT_DIR / "open_match_team_features.csv", index=False)

    status = {
        "status": "statsbomb_open_data_sync_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "competitions_available": int(len(comp_df)),
        "development_competitions_selected": int(len(selected)),
        "matches_catalogued": int(len(matches_df)),
        "sample_matches_ingested": int(sample.match_id.nunique()) if not sample.empty else 0,
        "sample_events": int(len(events_df)),
        "sample_team_match_feature_rows": int(len(features)),
        "licensed_world_cup_2026_data_available": False,
        "methodological_role": "development and external spatial validation only; never merged into Synthetic XI v1.0 player rankings without a separate harmonisation study",
        "attribution_required": "Hudl StatsBomb Open Data",
    }
    (OUT_DIR / "statsbomb_open_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
