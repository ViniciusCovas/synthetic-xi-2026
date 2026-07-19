#!/usr/bin/env python3
"""Attach historical hourly weather to World Cup fixtures via Open-Meteo."""
from __future__ import annotations

import json
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from scripts.enrichment.common import cache_path, choose_geocode_result, nearest_time_index, parse_iso

CATALOG_PATH = Path("data/enrichment/context/fixture_context_catalog.csv")
OUT_DIR = Path("data/enrichment/context")
RAW_DIR = Path("data/raw/open_meteo")
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "surface_pressure",
    "cloud_cover",
    "visibility",
    "wind_speed_10m",
    "wind_gusts_10m",
]


def cached_json(session: requests.Session, url: str, params: dict[str, Any], prefix: str) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(RAW_DIR, prefix, [url, params])
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = session.get(url, params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def value_at(hourly: dict[str, Any], variable: str, index: int) -> Any:
    values = hourly.get(variable) or []
    return values[index] if index < len(values) else None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CATALOG_PATH.exists():
        (OUT_DIR / "open_meteo_status.json").write_text(json.dumps({"status": "waiting_for_fixture_context_catalog"}, indent=2))
        return
    catalog = pd.read_csv(CATALOG_PATH)
    available = catalog[catalog["venue_city"].notna()].copy()
    if available.empty:
        status = {"status": "waiting_for_venue_metadata", "fixtures": int(len(catalog)), "weather_rows": 0}
        (OUT_DIR / "open_meteo_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    session = requests.Session()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for fixture in available.itertuples(index=False):
        country = getattr(fixture, "league_country", None)
        city = str(fixture.venue_city)
        try:
            geo = cached_json(session, GEOCODE_URL, {"name": city, "count": 10, "language": "en", "format": "json"}, "geocode")
            chosen = choose_geocode_result(geo.get("results") or [], city, country)
            if not chosen:
                raise ValueError("geocoding returned no usable result")
            kickoff = parse_iso(fixture.date).astimezone(timezone.utc)
            start_date = (kickoff - timedelta(hours=4)).date().isoformat()
            end_date = (kickoff + timedelta(hours=4)).date().isoformat()
            params = {
                "latitude": chosen["latitude"],
                "longitude": chosen["longitude"],
                "start_date": start_date,
                "end_date": end_date,
                "hourly": ",".join(HOURLY),
                "timezone": "UTC",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
            }
            weather = cached_json(session, WEATHER_URL, params, "weather")
            hourly = weather.get("hourly") or {}
            times = hourly.get("time") or []
            idx = nearest_time_index(times, kickoff)
            parsed_times = [parse_iso(item) for item in times]
            pre_idx = [i for i, timestamp in enumerate(parsed_times) if kickoff - timedelta(hours=3) <= timestamp <= kickoff]
            row: dict[str, Any] = {
                "fixture_id": int(fixture.fixture_id),
                "kickoff_utc": kickoff.isoformat(),
                "venue_name": getattr(fixture, "venue_name", None),
                "venue_city": city,
                "weather_grid_name": chosen.get("name"),
                "weather_country": chosen.get("country"),
                "latitude": chosen.get("latitude"),
                "longitude": chosen.get("longitude"),
                "elevation_m": weather.get("elevation"),
                "weather_hour_utc": times[idx],
                "geocode_confidence": "city_country" if country else "city_only",
                "weather_source": "Open-Meteo Historical Forecast API",
                "context_in_main_v1": False,
            }
            for variable in HOURLY:
                row[f"kickoff_{variable}"] = value_at(hourly, variable, idx)
            for variable in ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "wind_speed_10m"]:
                values = [value_at(hourly, variable, i) for i in pre_idx]
                numeric = [float(v) for v in values if v is not None]
                row[f"pre3h_{variable}_mean"] = float(np.mean(numeric)) if numeric else None
            precip = [value_at(hourly, "precipitation", i) for i in pre_idx]
            gusts = [value_at(hourly, "wind_gusts_10m", i) for i in pre_idx]
            row["pre3h_precipitation_sum"] = float(np.sum([float(v) for v in precip if v is not None])) if precip else None
            row["pre3h_wind_gusts_10m_max"] = float(np.max([float(v) for v in gusts if v is not None])) if any(v is not None for v in gusts) else None
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append({"fixture_id": int(fixture.fixture_id), "venue_city": city, "error": str(exc)[:300]})

    output = pd.DataFrame(rows)
    output.to_csv(OUT_DIR / "match_weather_open_meteo.csv", index=False)
    status = {
        "status": "open_meteo_enrichment_completed",
        "fixtures_with_context": int(len(output)),
        "fixtures_failed": int(len(errors)),
        "errors": errors[:20],
        "dataset_choice": "Historical Forecast API for recent match-day conditions; UTC hourly nearest-kickoff value plus pre-match three-hour summaries",
        "context_in_main_v1": False,
    }
    (OUT_DIR / "open_meteo_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
