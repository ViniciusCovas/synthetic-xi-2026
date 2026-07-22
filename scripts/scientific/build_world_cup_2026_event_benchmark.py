#!/usr/bin/env python3
"""Create a descriptive event benchmark from FIFA World Cup 2026 matches.

This script does not update simulator parameters. It freezes the observed
provider distributions that the already-frozen engine must be checked against.
Missing provider fields remain missing and are reported by metric coverage.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from scripts.api_football_batch_client import BatchClient, QuotaStop

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "data" / "context"
RAW_FIXTURES = CONTEXT / "world_cup_2026_fixture_schedule_raw.json"
MATCH_OUT = CONTEXT / "world_cup_2026_event_benchmark_by_match.csv"
SUMMARY_OUT = CONTEXT / "world_cup_2026_event_benchmark_summary.json"
FIXTURES_URL = "https://v3.football.api-sports.io/fixtures"


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def schedule_payload() -> dict[str, Any]:
    if RAW_FIXTURES.exists():
        return json.loads(RAW_FIXTURES.read_text(encoding="utf-8"))
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY is required")
    response = requests.get(
        FIXTURES_URL,
        params={
            "league": int(os.getenv("WORLD_CUP_LEAGUE_ID", "1")),
            "season": 2026,
            "from": "2026-06-11",
            "to": "2026-07-19",
        },
        headers={"x-apisports-key": key},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise SystemExit(f"Fixture request failed: {payload['errors']}")
    CONTEXT.mkdir(parents=True, exist_ok=True)
    RAW_FIXTURES.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def stat_map(item: dict[str, Any]) -> dict[int, dict[str, float | None]]:
    mapped: dict[int, dict[str, float | None]] = {}
    for block in item.get("statistics") or []:
        team_id = ((block.get("team") or {}).get("id"))
        if team_id is None:
            continue
        stats: dict[str, float | None] = {}
        for entry in block.get("statistics") or []:
            key = norm(entry.get("type"))
            value = entry.get("value")
            if isinstance(value, str) and value.endswith("%"):
                value = value[:-1]
            try:
                stats[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                stats[key] = None
        mapped[int(team_id)] = stats
    return mapped


def pick(stats: dict[str, float | None], *names: str) -> float | None:
    for name in names:
        value = stats.get(norm(name))
        if value is not None:
            return float(value)
    return None


def sum_optional(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None and not pd.isna(value)]
    return float(sum(present)) if present else None


def event_minute(event: dict[str, Any]) -> float | None:
    time = event.get("time") or {}
    try:
        elapsed = float(time.get("elapsed"))
    except (TypeError, ValueError):
        return None
    try:
        extra = float(time.get("extra") or 0)
    except (TypeError, ValueError):
        extra = 0.0
    return elapsed + extra


def event_counts(item: dict[str, Any]) -> dict[str, int]:
    yellow = red = substitutions = penalties = var_reviews = observable_injuries = 0
    for event in item.get("events") or []:
        event_type = norm(event.get("type"))
        detail = norm(event.get("detail"))
        comments = norm(event.get("comments"))
        minute = event_minute(event)
        if minute is not None and minute > 130:
            continue
        if event_type == "card":
            if "yellow" in detail and "second" not in detail:
                yellow += 1
            if "red" in detail or "second yellow" in detail:
                red += 1
        if event_type in {"subst", "substitution"}:
            substitutions += 1
            if any(word in comments for word in ["injury", "injured", "medical"]):
                observable_injuries += 1
        if "penalty" in detail and "shootout" not in comments:
            penalties += 1
        if event_type == "var" or "var" in detail:
            var_reviews += 1
    return {
        "event_yellow_cards": yellow,
        "event_red_cards": red,
        "substitutions": substitutions,
        "penalty_events": penalties,
        "var_reviews": var_reviews,
        "observable_injuries": observable_injuries,
    }


def score_value(item: dict[str, Any], period: str, side: str) -> int | None:
    value = (((item.get("score") or {}).get(period) or {}).get(side))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fixture_row(item: dict[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    home_id = ((teams.get("home") or {}).get("id"))
    away_id = ((teams.get("away") or {}).get("id"))
    stats = stat_map(item)
    home_stats = stats.get(int(home_id), {}) if home_id is not None else {}
    away_stats = stats.get(int(away_id), {}) if away_id is not None else {}
    events = event_counts(item)
    status = norm(((fixture.get("status") or {}).get("short"))).upper()
    total_goals = sum_optional([
        float(goals.get("home")) if goals.get("home") is not None else None,
        float(goals.get("away")) if goals.get("away") is not None else None,
    ])
    return {
        "fixture_id": fixture.get("id"),
        "kickoff": fixture.get("date"),
        "round": ((item.get("league") or {}).get("round")),
        "home_team": ((teams.get("home") or {}).get("name")),
        "away_team": ((teams.get("away") or {}).get("name")),
        "status_short": status,
        "total_goals_all_periods": total_goals,
        "halftime_goals": sum_optional([
            score_value(item, "halftime", "home"),
            score_value(item, "halftime", "away"),
        ]),
        "fulltime_goals": sum_optional([
            score_value(item, "fulltime", "home"),
            score_value(item, "fulltime", "away"),
        ]),
        "extra_time_played": status in {"AET", "PEN"},
        "shootout_played": status == "PEN",
        "shots": sum_optional([pick(home_stats, "Total Shots"), pick(away_stats, "Total Shots")]),
        "shots_on_target": sum_optional([pick(home_stats, "Shots on Goal", "Shots on Target"), pick(away_stats, "Shots on Goal", "Shots on Target")]),
        "fouls": sum_optional([pick(home_stats, "Fouls"), pick(away_stats, "Fouls")]),
        "corners": sum_optional([pick(home_stats, "Corner Kicks", "Corners"), pick(away_stats, "Corner Kicks", "Corners")]),
        "yellow_cards_stat": sum_optional([pick(home_stats, "Yellow Cards"), pick(away_stats, "Yellow Cards")]),
        "red_cards_stat": sum_optional([pick(home_stats, "Red Cards"), pick(away_stats, "Red Cards")]),
        **events,
    }


def metric_summary(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if not len(values):
        return {"n": 0, "coverage": 0.0}
    return {
        "n": int(len(values)),
        "coverage": round(len(values) / len(series), 6),
        "mean": round(float(values.mean()), 6),
        "sd": round(float(values.std(ddof=1)), 6) if len(values) > 1 else 0.0,
        "p05": round(float(values.quantile(0.05)), 6),
        "p25": round(float(values.quantile(0.25)), 6),
        "median": round(float(values.median()), 6),
        "p75": round(float(values.quantile(0.75)), 6),
        "p95": round(float(values.quantile(0.95)), 6),
        "min": round(float(values.min()), 6),
        "max": round(float(values.max()), 6),
    }


def main() -> None:
    payload = schedule_payload()
    fixtures = payload.get("response") or []
    fixture_ids = sorted({int((item.get("fixture") or {}).get("id")) for item in fixtures if (item.get("fixture") or {}).get("id") is not None})
    if len(fixture_ids) < 90:
        raise SystemExit(f"Only {len(fixture_ids)} fixture ids available")

    client = BatchClient()
    client.status()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    bundle_size = min(20, max(1, int(os.getenv("FIXTURE_BUNDLE_SIZE", "20"))))
    for start in range(0, len(fixture_ids), bundle_size):
        ids = fixture_ids[start:start + bundle_size]
        try:
            response = client.get_fixtures_bundle(ids, force_refresh=True)
        except QuotaStop as exc:
            errors.append(f"quota_stop:{exc}")
            break
        except Exception as exc:
            errors.append(f"bundle_{start}:{type(exc).__name__}:{exc}")
            continue
        items.extend(response.get("response") or [])

    rows = [fixture_row(item) for item in items]
    frame = pd.DataFrame(rows).drop_duplicates("fixture_id", keep="last").sort_values("kickoff")
    CONTEXT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(MATCH_OUT, index=False)
    metrics = [
        "fulltime_goals",
        "shots",
        "shots_on_target",
        "fouls",
        "corners",
        "yellow_cards_stat",
        "red_cards_stat",
        "event_yellow_cards",
        "event_red_cards",
        "substitutions",
        "penalty_events",
        "var_reviews",
        "observable_injuries",
    ]
    distributions = {metric: metric_summary(frame.get(metric, pd.Series(dtype=float))) for metric in metrics}
    total = len(fixture_ids)
    returned = len(frame)
    fixture_coverage = returned / total if total else 0.0
    core_metric_coverage = {
        metric: distributions[metric].get("coverage", 0.0)
        for metric in ["fulltime_goals", "shots", "shots_on_target", "fouls", "yellow_cards_stat", "red_cards_stat", "substitutions"]
    }
    summary = {
        "status": "world_cup_2026_event_benchmark_complete" if fixture_coverage >= 0.90 and min(core_metric_coverage.values(), default=0.0) >= 0.80 else "world_cup_2026_event_benchmark_incomplete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "methodological_effect": "benchmark_freeze_only_no_model_parameter_update",
        "scheduled_fixtures": total,
        "fixtures_returned_with_bundle": returned,
        "fixture_coverage": round(fixture_coverage, 6),
        "extra_time_matches": int(frame.extra_time_played.fillna(False).astype(bool).sum()) if len(frame) else 0,
        "extra_time_frequency": round(float(frame.extra_time_played.fillna(False).astype(bool).mean()), 6) if len(frame) else None,
        "shootout_matches": int(frame.shootout_played.fillna(False).astype(bool).sum()) if len(frame) else 0,
        "shootout_frequency": round(float(frame.shootout_played.fillna(False).astype(bool).mean()), 6) if len(frame) else None,
        "distributions": distributions,
        "core_metric_coverage": core_metric_coverage,
        "network_calls": int(client.calls),
        "quota_remaining": client.remaining,
        "errors": errors,
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
        "output": str(MATCH_OUT.relative_to(ROOT)),
        "limitations": [
            "Penalty events are provider event classifications and may undercount awarded penalties without a recorded kick.",
            "VAR and observable injury fields are descriptive because provider event coverage is not guaranteed.",
            "Stoppage time is not promoted to a calibrated target unless a complete provider field is found."
        ],
    }
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
