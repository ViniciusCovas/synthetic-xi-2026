#!/usr/bin/env python3
"""Build an auditable FIFA World Cup 2026 match-weather record.

The script uses the API-Football World Cup fixture list only to obtain match,
kick-off and venue metadata. Weather is requested from Open-Meteo. Reanalysis
is preferred; the historical-forecast archive is used only when reanalysis is
not yet available and is explicitly labelled as a lower evidence grade.

No weather value is imputed into the observed record. Outdoor conditions at a
roofed or climate-controlled venue remain contextual and are not represented as
measured pitch conditions.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "context"
RAW = OUT / "world_cup_2026_fixture_schedule_raw.json"
CSV_OUT = OUT / "world_cup_2026_weather_by_match.csv"
SUMMARY_OUT = OUT / "world_cup_2026_weather_summary.json"
MANIFEST_OUT = OUT / "world_cup_2026_weather_source_manifest.json"

FIXTURES_URL = "https://v3.football.api-sports.io/fixtures"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
]


def norm(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


# Coordinates identify the stadium area, not a weather station. Open-Meteo maps
# them to its gridded product. The exposure label prevents a roofed venue's
# outdoor weather from being treated as direct on-pitch measurement.
VENUES: list[dict[str, Any]] = [
    {"host_city": "Toronto", "latitude": 43.6332, "longitude": -79.4186, "timezone": "America/Toronto", "exposure": "open_air", "aliases": ["toronto stadium", "bmo field", "toronto"]},
    {"host_city": "Vancouver", "latitude": 49.2768, "longitude": -123.1119, "timezone": "America/Vancouver", "exposure": "retractable_or_fixed_roof", "aliases": ["bc place vancouver", "bc place", "vancouver"]},
    {"host_city": "Mexico City", "latitude": 19.3029, "longitude": -99.1505, "timezone": "America/Mexico_City", "exposure": "open_air", "aliases": ["mexico city stadium", "estadio azteca", "ciudad de mexico", "mexico city"]},
    {"host_city": "Guadalajara", "latitude": 20.6818, "longitude": -103.4626, "timezone": "America/Mexico_City", "exposure": "open_air", "aliases": ["guadalajara stadium", "estadio guadalajara", "estadio akron", "guadalajara"]},
    {"host_city": "Monterrey", "latitude": 25.6693, "longitude": -100.2446, "timezone": "America/Monterrey", "exposure": "open_air", "aliases": ["monterrey stadium", "estadio monterrey", "estadio bbva", "monterrey"]},
    {"host_city": "Atlanta", "latitude": 33.7554, "longitude": -84.4008, "timezone": "America/New_York", "exposure": "retractable_or_fixed_roof", "aliases": ["atlanta stadium", "mercedes benz stadium", "atlanta"]},
    {"host_city": "Boston", "latitude": 42.0909, "longitude": -71.2643, "timezone": "America/New_York", "exposure": "open_air", "aliases": ["boston stadium", "gillette stadium", "foxborough", "boston"]},
    {"host_city": "Dallas", "latitude": 32.7473, "longitude": -97.0945, "timezone": "America/Chicago", "exposure": "retractable_or_fixed_roof", "aliases": ["dallas stadium", "at t stadium", "arlington", "dallas"]},
    {"host_city": "Houston", "latitude": 29.6847, "longitude": -95.4107, "timezone": "America/Chicago", "exposure": "retractable_or_fixed_roof", "aliases": ["houston stadium", "nrg stadium", "houston"]},
    {"host_city": "Kansas City", "latitude": 39.0489, "longitude": -94.4839, "timezone": "America/Chicago", "exposure": "open_air", "aliases": ["kansas city stadium", "arrowhead stadium", "kansas city"]},
    {"host_city": "Los Angeles", "latitude": 33.9535, "longitude": -118.3392, "timezone": "America/Los_Angeles", "exposure": "covered_open_sides", "aliases": ["los angeles stadium", "sofi stadium", "inglewood", "los angeles"]},
    {"host_city": "Miami", "latitude": 25.9580, "longitude": -80.2389, "timezone": "America/New_York", "exposure": "open_air", "aliases": ["miami stadium", "hard rock stadium", "miami gardens", "miami"]},
    {"host_city": "New York New Jersey", "latitude": 40.8135, "longitude": -74.0745, "timezone": "America/New_York", "exposure": "open_air", "aliases": ["new york new jersey stadium", "metlife stadium", "east rutherford", "new jersey", "new york"]},
    {"host_city": "Philadelphia", "latitude": 39.9008, "longitude": -75.1675, "timezone": "America/New_York", "exposure": "open_air", "aliases": ["philadelphia stadium", "lincoln financial field", "philadelphia"]},
    {"host_city": "San Francisco Bay Area", "latitude": 37.4030, "longitude": -121.9700, "timezone": "America/Los_Angeles", "exposure": "open_air", "aliases": ["san francisco bay area stadium", "levis stadium", "levi s stadium", "santa clara", "san francisco"]},
    {"host_city": "Seattle", "latitude": 47.5952, "longitude": -122.3316, "timezone": "America/Los_Angeles", "exposure": "open_air", "aliases": ["seattle stadium", "lumen field", "seattle"]},
]


def venue_for(name: object, city: object) -> dict[str, Any] | None:
    target = f"{norm(name)} {norm(city)}"
    candidates: list[tuple[int, dict[str, Any]]] = []
    for venue in VENUES:
        score = max((len(norm(alias)) for alias in venue["aliases"] if norm(alias) in target), default=0)
        if score:
            candidates.append((score, venue))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def get_json(url: str, *, params: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(url, params=params, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json()


def load_fixtures() -> list[dict[str, Any]]:
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY is required to freeze the official provider fixture metadata")
    league_id = int(os.getenv("WORLD_CUP_LEAGUE_ID", "1"))
    payload = get_json(
        FIXTURES_URL,
        params={"league": league_id, "season": 2026, "from": "2026-06-11", "to": "2026-07-19"},
        headers={"x-apisports-key": key},
    )
    errors = payload.get("errors") or {}
    if errors:
        raise SystemExit(f"API-Football fixture request failed: {errors}")
    fixtures = payload.get("response") or []
    if not fixtures:
        raise SystemExit("No World Cup 2026 fixtures returned")
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fixtures


def hourly_frame(payload: dict[str, Any]) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame()
    data: dict[str, Any] = {"time": pd.to_datetime(times, errors="coerce")}
    for variable in HOURLY:
        values = hourly.get(variable)
        data[variable] = values if isinstance(values, list) and len(values) == len(times) else [None] * len(times)
    return pd.DataFrame(data).dropna(subset=["time"])


def fetch_venue_weather(venue: dict[str, Any], start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    common = {
        "latitude": venue["latitude"],
        "longitude": venue["longitude"],
        "hourly": ",".join(HOURLY),
        "timezone": venue["timezone"],
    }
    archive = pd.DataFrame()
    fallback = pd.DataFrame()
    archive_cutoff = min(end, datetime.now(timezone.utc).date() - timedelta(days=5))
    if archive_cutoff >= start:
        try:
            payload = get_json(ARCHIVE_URL, params={**common, "start_date": start.isoformat(), "end_date": archive_cutoff.isoformat()})
            archive = hourly_frame(payload)
        except Exception:
            archive = pd.DataFrame()
    recent_start = max(start, archive_cutoff + timedelta(days=1))
    if recent_start <= end:
        try:
            payload = get_json(HISTORICAL_FORECAST_URL, params={**common, "start_date": recent_start.isoformat(), "end_date": end.isoformat()})
            fallback = hourly_frame(payload)
        except Exception:
            fallback = pd.DataFrame()
    return archive, fallback


def safe_mean(values: pd.Series) -> float | None:
    nums = pd.to_numeric(values, errors="coerce").dropna()
    return round(float(nums.mean()), 3) if len(nums) else None


def safe_max(values: pd.Series) -> float | None:
    nums = pd.to_numeric(values, errors="coerce").dropna()
    return round(float(nums.max()), 3) if len(nums) else None


def safe_sum(values: pd.Series) -> float | None:
    nums = pd.to_numeric(values, errors="coerce").dropna()
    return round(float(nums.sum()), 3) if len(nums) else None


def mode_code(values: pd.Series) -> int | None:
    nums = pd.to_numeric(values, errors="coerce").dropna().astype(int).tolist()
    return Counter(nums).most_common(1)[0][0] if nums else None


def heat_band(apparent_max: float | None) -> str | None:
    if apparent_max is None or math.isnan(apparent_max):
        return None
    if apparent_max < 24:
        return "cool_or_mild"
    if apparent_max < 29:
        return "warm"
    if apparent_max < 35:
        return "hot"
    return "very_hot"


def main() -> None:
    fixtures = load_fixtures()
    parsed: list[dict[str, Any]] = []
    unresolved_venues: list[dict[str, Any]] = []
    for item in fixtures:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        venue_block = fixture.get("venue") or {}
        raw_date = fixture.get("date")
        try:
            kickoff_utc = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        if not (date(2026, 6, 11) <= kickoff_utc.date() <= date(2026, 7, 20)):
            continue
        venue = venue_for(venue_block.get("name"), venue_block.get("city"))
        base = {
            "fixture_id": fixture.get("id"),
            "stage": league.get("round"),
            "kickoff_utc": kickoff_utc.isoformat(),
            "home_team": ((teams.get("home") or {}).get("name")),
            "away_team": ((teams.get("away") or {}).get("name")),
            "provider_venue_name": venue_block.get("name"),
            "provider_venue_city": venue_block.get("city"),
            "status_short": ((fixture.get("status") or {}).get("short")),
        }
        if venue is None:
            unresolved_venues.append(base)
            continue
        local = kickoff_utc.astimezone(ZoneInfo(venue["timezone"]))
        parsed.append({**base, **{k: v for k, v in venue.items() if k != "aliases"}, "kickoff_local": local.isoformat(), "match_date_local": local.date().isoformat()})
    if len(parsed) < 90:
        raise SystemExit(f"Only {len(parsed)} World Cup fixtures mapped to host venues; expected at least 90")

    start = min(datetime.fromisoformat(row["kickoff_local"]).date() for row in parsed)
    end = max(datetime.fromisoformat(row["kickoff_local"]).date() for row in parsed)
    weather_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for venue in VENUES:
        weather_cache[venue["host_city"]] = fetch_venue_weather(venue, start, end)

    rows: list[dict[str, Any]] = []
    for match in parsed:
        local = datetime.fromisoformat(match["kickoff_local"])
        window_start = local.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        window_end = window_start + timedelta(hours=4)
        archive, fallback = weather_cache[match["host_city"]]
        chosen = pd.DataFrame()
        grade = "unavailable"
        source = None
        if not archive.empty:
            block = archive.loc[(archive.time >= window_start) & (archive.time <= window_end)]
            if len(block):
                chosen = block
                grade = "A_reanalysis"
                source = ARCHIVE_URL
        if chosen.empty and not fallback.empty:
            block = fallback.loc[(fallback.time >= window_start) & (fallback.time <= window_end)]
            if len(block):
                chosen = block
                grade = "B_historical_forecast_archive"
                source = HISTORICAL_FORECAST_URL
        metrics = {
            "temperature_mean_c": safe_mean(chosen.get("temperature_2m", pd.Series(dtype=float))),
            "temperature_max_c": safe_max(chosen.get("temperature_2m", pd.Series(dtype=float))),
            "relative_humidity_mean_pct": safe_mean(chosen.get("relative_humidity_2m", pd.Series(dtype=float))),
            "apparent_temperature_mean_c": safe_mean(chosen.get("apparent_temperature", pd.Series(dtype=float))),
            "apparent_temperature_max_c": safe_max(chosen.get("apparent_temperature", pd.Series(dtype=float))),
            "precipitation_sum_mm": safe_sum(chosen.get("precipitation", pd.Series(dtype=float))),
            "wind_speed_mean_kmh": safe_mean(chosen.get("wind_speed_10m", pd.Series(dtype=float))),
            "wind_gust_max_kmh": safe_max(chosen.get("wind_gusts_10m", pd.Series(dtype=float))),
            "weather_code_mode": mode_code(chosen.get("weather_code", pd.Series(dtype=float))),
        }
        rows.append({
            **match,
            **metrics,
            "heat_band": heat_band(metrics["apparent_temperature_max_c"]),
            "weather_evidence_grade": grade,
            "weather_source_endpoint": source,
            "weather_window_hours": int(len(chosen)),
            "direct_pitch_exposure_claim_allowed": match["exposure"] == "open_air",
            "weather_interpretation": "outdoor stadium-area context" if match["exposure"] == "open_air" else "outdoor context only; roof or covered venue may decouple pitch conditions",
        })

    frame = pd.DataFrame(rows).sort_values(["kickoff_utc", "fixture_id"])
    frame.to_csv(CSV_OUT, index=False)
    total = len(frame)
    available = int(frame.weather_evidence_grade.ne("unavailable").sum())
    grade_a = int(frame.weather_evidence_grade.eq("A_reanalysis").sum())
    open_air = frame.loc[frame.exposure.eq("open_air")]
    summary = {
        "status": "world_cup_2026_weather_record_complete" if total and available / total >= 0.90 else "world_cup_2026_weather_record_incomplete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_source": "API-Football league fixture metadata; official schedule cross-check required",
        "official_tournament_reference": "FIFA World Cup 2026: 104 matches, 16 host cities, 11 June to 19 July 2026",
        "matches_in_record": total,
        "matches_with_weather": available,
        "weather_coverage": round(available / total, 6) if total else 0.0,
        "reanalysis_matches": grade_a,
        "reanalysis_coverage": round(grade_a / total, 6) if total else 0.0,
        "lower_grade_historical_forecast_matches": int(frame.weather_evidence_grade.eq("B_historical_forecast_archive").sum()),
        "unavailable_matches": int(frame.weather_evidence_grade.eq("unavailable").sum()),
        "unresolved_fixture_venues": len(unresolved_venues),
        "venue_exposure_counts": frame.exposure.value_counts(dropna=False).to_dict(),
        "heat_band_counts_all_venues": frame.heat_band.value_counts(dropna=False).to_dict(),
        "open_air_matches": int(len(open_air)),
        "open_air_temperature_mean_c": safe_mean(open_air.temperature_mean_c),
        "open_air_apparent_temperature_max_c": safe_max(open_air.apparent_temperature_max_c),
        "open_air_matches_with_precipitation": int(pd.to_numeric(open_air.precipitation_sum_mm, errors="coerce").fillna(0).gt(0).sum()),
        "methodological_use": "paired nuisance distribution for neutral-environment sensitivity; never a team-specific advantage",
        "missing_weather_imputed": False,
        "outdoor_weather_used_as_indoor_pitch_measurement": False,
        "output": str(CSV_OUT.relative_to(ROOT)),
    }
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schedule_reference": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums",
        "fixture_metadata_endpoint": FIXTURES_URL,
        "weather_primary_endpoint": ARCHIVE_URL,
        "weather_fallback_endpoint": HISTORICAL_FORECAST_URL,
        "weather_variables": HOURLY,
        "aggregation_window": "kickoff local hour through four hours after kickoff",
        "quality_grades": {
            "A_reanalysis": "Open-Meteo Historical Weather API gridded reanalysis",
            "B_historical_forecast_archive": "archived numerical forecast; not an observation",
            "unavailable": "no value; no imputation",
        },
        "venue_registry": [{k: v for k, v in venue.items() if k != "aliases"} for venue in VENUES],
        "unresolved_venues": unresolved_venues,
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
