#!/usr/bin/env python3
"""Repair only unavailable World Cup 2026 weather rows using the same sources.

The initial reconstruction deliberately swallows individual weather-provider
failures so the audit can report missingness. This second pass retries only the
missing host-city evidence with bounded backoff. Existing observed/reanalysis
values are immutable, and no value is imputed or statistically inferred.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "data" / "context"
CSV_PATH = CONTEXT / "world_cup_2026_weather_by_match.csv"
SUMMARY_PATH = CONTEXT / "world_cup_2026_weather_summary.json"
MANIFEST_PATH = CONTEXT / "world_cup_2026_weather_source_manifest.json"
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
METRIC_COLUMNS = [
    "temperature_mean_c",
    "temperature_max_c",
    "relative_humidity_mean_pct",
    "apparent_temperature_mean_c",
    "apparent_temperature_max_c",
    "precipitation_sum_mm",
    "wind_speed_mean_kmh",
    "wind_gust_max_kmh",
    "weather_code_mode",
]


def get_json_with_retry(url: str, params: dict[str, Any], attempts: int = 5) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "synthetic-xi-scientific-audit/1.0"},
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("weather response is not a JSON object")
            return payload
        except Exception as exc:  # bounded retry, preserved in audit metadata
            errors.append(f"attempt_{attempt}:{type(exc).__name__}:{exc}")
            if attempt < attempts:
                time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(" | ".join(errors))


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


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def safe_mean(series: pd.Series) -> float | None:
    values = numeric(series)
    return round(float(values.mean()), 3) if len(values) else None


def safe_max(series: pd.Series) -> float | None:
    values = numeric(series)
    return round(float(values.max()), 3) if len(values) else None


def safe_sum(series: pd.Series) -> float | None:
    values = numeric(series)
    return round(float(values.sum()), 3) if len(values) else None


def mode_code(series: pd.Series) -> int | None:
    values = numeric(series).astype(int).tolist()
    return Counter(values).most_common(1)[0][0] if values else None


def heat_band(value: float | None) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value < 24:
        return "cool_or_mild"
    if value < 29:
        return "warm"
    if value < 35:
        return "hot"
    return "very_hot"


def fetch_city_block(venue: dict[str, Any], start_date: str, end_date: str, endpoint: str) -> pd.DataFrame:
    payload = get_json_with_retry(
        endpoint,
        {
            "latitude": venue["latitude"],
            "longitude": venue["longitude"],
            "hourly": ",".join(HOURLY),
            "timezone": venue["timezone"],
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    return hourly_frame(payload)


def recompute_summary(frame: pd.DataFrame, previous: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
    total = len(frame)
    available = int(frame.weather_evidence_grade.ne("unavailable").sum())
    grade_a = int(frame.weather_evidence_grade.eq("A_reanalysis").sum())
    open_air = frame.loc[frame.exposure.eq("open_air")]
    return {
        **previous,
        "status": "world_cup_2026_weather_record_complete" if total and available / total >= 0.90 else "world_cup_2026_weather_record_incomplete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "matches_in_record": total,
        "matches_with_weather": available,
        "weather_coverage": round(available / total, 6) if total else 0.0,
        "reanalysis_matches": grade_a,
        "reanalysis_coverage": round(grade_a / total, 6) if total else 0.0,
        "lower_grade_historical_forecast_matches": int(frame.weather_evidence_grade.eq("B_historical_forecast_archive").sum()),
        "unavailable_matches": int(frame.weather_evidence_grade.eq("unavailable").sum()),
        "venue_exposure_counts": frame.exposure.value_counts(dropna=False).to_dict(),
        "heat_band_counts_all_venues": frame.heat_band.value_counts(dropna=False).to_dict(),
        "open_air_matches": int(len(open_air)),
        "open_air_temperature_mean_c": safe_mean(open_air.temperature_mean_c),
        "open_air_apparent_temperature_max_c": safe_max(open_air.apparent_temperature_max_c),
        "open_air_matches_with_precipitation": int(pd.to_numeric(open_air.precipitation_sum_mm, errors="coerce").fillna(0).gt(0).sum()),
        "missing_weather_imputed": False,
        "outdoor_weather_used_as_indoor_pitch_measurement": False,
        "missing_evidence_repair": repair,
    }


def main() -> None:
    if not CSV_PATH.exists() or not SUMMARY_PATH.exists() or not MANIFEST_PATH.exists():
        raise SystemExit("Initial World Cup weather record must exist before repair")

    frame = pd.read_csv(CSV_PATH)
    previous_summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    registry = {item["host_city"]: item for item in manifest.get("venue_registry", [])}
    missing_before = frame.weather_evidence_grade.eq("unavailable")
    immutable_before = frame.loc[~missing_before].copy(deep=True).reset_index(drop=True)
    errors: dict[str, str] = {}
    attempted: list[str] = []

    for host_city, group in frame.loc[missing_before].groupby("host_city", sort=True):
        attempted.append(str(host_city))
        venue = registry.get(host_city)
        if not venue:
            errors[str(host_city)] = "venue_not_in_frozen_registry"
            continue
        dates = pd.to_datetime(group.match_date_local, errors="coerce").dropna()
        if dates.empty:
            errors[str(host_city)] = "missing_local_dates"
            continue
        start_date = dates.min().date().isoformat()
        end_date = dates.max().date().isoformat()
        newest = dates.max().date()
        endpoint = ARCHIVE_URL if newest <= datetime.now(timezone.utc).date() - timedelta(days=5) else HISTORICAL_FORECAST_URL
        grade = "A_reanalysis" if endpoint == ARCHIVE_URL else "B_historical_forecast_archive"
        try:
            weather = fetch_city_block(venue, start_date, end_date, endpoint)
        except Exception as exc:
            errors[str(host_city)] = f"{type(exc).__name__}:{exc}"
            continue
        if weather.empty:
            errors[str(host_city)] = "provider_returned_no_hourly_rows"
            continue

        for index in group.index:
            local = pd.to_datetime(frame.at[index, "kickoff_local"], errors="coerce")
            if pd.isna(local):
                continue
            local_naive = local.tz_localize(None) if getattr(local, "tzinfo", None) is not None else local
            start = local_naive.floor("h")
            end = start + pd.Timedelta(hours=4)
            block = weather.loc[(weather.time >= start) & (weather.time <= end)]
            if block.empty:
                continue
            values = {
                "temperature_mean_c": safe_mean(block.get("temperature_2m", pd.Series(dtype=float))),
                "temperature_max_c": safe_max(block.get("temperature_2m", pd.Series(dtype=float))),
                "relative_humidity_mean_pct": safe_mean(block.get("relative_humidity_2m", pd.Series(dtype=float))),
                "apparent_temperature_mean_c": safe_mean(block.get("apparent_temperature", pd.Series(dtype=float))),
                "apparent_temperature_max_c": safe_max(block.get("apparent_temperature", pd.Series(dtype=float))),
                "precipitation_sum_mm": safe_sum(block.get("precipitation", pd.Series(dtype=float))),
                "wind_speed_mean_kmh": safe_mean(block.get("wind_speed_10m", pd.Series(dtype=float))),
                "wind_gust_max_kmh": safe_max(block.get("wind_gusts_10m", pd.Series(dtype=float))),
                "weather_code_mode": mode_code(block.get("weather_code", pd.Series(dtype=float))),
            }
            for column, value in values.items():
                frame.at[index, column] = value
            frame.at[index, "heat_band"] = heat_band(values["apparent_temperature_max_c"])
            frame.at[index, "weather_evidence_grade"] = grade
            frame.at[index, "weather_source_endpoint"] = endpoint
            frame.at[index, "weather_window_hours"] = int(len(block))

    immutable_after = frame.loc[~missing_before].copy(deep=True).reset_index(drop=True)
    pd.testing.assert_frame_equal(immutable_before, immutable_after, check_dtype=False)
    remaining = int(frame.weather_evidence_grade.eq("unavailable").sum())
    recovered = int(missing_before.sum()) - remaining
    repair = {
        "status": "complete" if remaining == 0 else "partial",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "same-source bounded retry; missing rows only; no imputation",
        "host_cities_attempted": attempted,
        "missing_matches_before": int(missing_before.sum()),
        "recovered_matches": recovered,
        "remaining_unavailable_matches": remaining,
        "errors": errors,
        "existing_available_rows_changed": False,
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
    }

    frame.to_csv(CSV_PATH, index=False)
    summary = recompute_summary(frame, previous_summary, repair)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["missing_evidence_repair"] = repair
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["weather_coverage"] < 0.90:
        raise SystemExit(f"Weather coverage remains below 0.90: {summary['weather_coverage']}")


if __name__ == "__main__":
    main()
