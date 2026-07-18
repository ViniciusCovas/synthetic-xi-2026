#!/usr/bin/env python3
"""Construye el inventario exacto de partidos para los modelos anual y pre-Mundial.

Esta fase no descarga todavía estadísticas individuales por partido y no genera
rankings. Identifica los fixtures oficiales, terminados, relevantes para los
jugadores mundialistas y comprendidos en las dos ventanas temporales.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

API_BASE = "https://v3.football.api-sports.io"
AUDIT_DIR = Path("data/audits")
RAW_DIR = Path("data/raw/fixture_inventory")
CURRENT_START = pd.Timestamp("2025-07-18", tz="UTC")
CURRENT_END = pd.Timestamp("2026-07-17 23:59:59", tz="UTC")
PRE_START = pd.Timestamp("2025-06-11", tz="UTC")
PRE_END = pd.Timestamp("2026-06-10 23:59:59", tz="UTC")
UNION_START = min(CURRENT_START, PRE_START)
UNION_END = max(CURRENT_END, PRE_END)
COMPLETED = {"FT", "AET", "PEN"}
FRIENDLY_IDS = {10, 667}
YOUTH_TOKENS = ("u21", "u20", "u19", "youth", "juvenil", "under 21", "under 20", "under 19")


class Client:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.key = key
        self.session = requests.Session()
        self.calls = 0
        self.hashes: list[str] = []
        self.min_interval = 60.0 / float(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "220"))
        self.last_call = 0.0

    def get(self, endpoint: str, params: dict[str, Any], cache_name: str) -> dict[str, Any]:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / f"{cache_name}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            wait = self.min_interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            response = self.session.get(
                f"{API_BASE}/{endpoint.lstrip('/')}",
                params=params,
                headers={"x-apisports-key": self.key},
                timeout=90,
            )
            self.last_call = time.monotonic()
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or {}
            if errors:
                raise RuntimeError(f"API-Football devolvió errores: {errors}")
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.calls += 1
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.hashes.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        return payload


def is_youth(name: str) -> bool:
    lowered = (name or "").lower()
    return any(token in lowered for token in YOUTH_TOKENS)


def main() -> None:
    stats = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    coverage = pd.read_csv(AUDIT_DIR / "annual_competition_coverage.csv")

    bool_cols = [
        "coverage_events",
        "coverage_lineups",
        "coverage_fixture_statistics",
        "coverage_player_statistics",
    ]
    for col in bool_cols:
        coverage[col] = coverage[col].fillna(False).astype(bool)
    coverage["usable_detailed"] = coverage[bool_cols].all(axis=1)

    pairs = (
        stats[["league_id", "season", "team_id", "league_name", "league_country"]]
        .dropna(subset=["league_id", "season", "team_id"])
        .merge(
            coverage[["league_id", "season", "league_type", "country", "usable_detailed"]],
            on=["league_id", "season"],
            how="left",
        )
    )
    pairs["usable_detailed"] = pairs["usable_detailed"].fillna(False).astype(bool)
    pairs = pairs.loc[pairs["usable_detailed"]].copy()
    pairs["league_id"] = pairs["league_id"].astype(int)
    pairs["season"] = pairs["season"].astype(int)
    pairs["team_id"] = pairs["team_id"].astype(int)

    client = Client()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    grouped = list(pairs.groupby(["league_id", "season"], sort=True))
    for index, ((league_id, season), group) in enumerate(grouped, start=1):
        team_ids = set(group["team_id"].astype(int))
        league_name_hint = str(group["league_name"].dropna().iloc[0]) if group["league_name"].notna().any() else ""
        try:
            payload = client.get(
                "fixtures",
                {"league": int(league_id), "season": int(season)},
                f"fixtures_{int(league_id)}_{int(season)}",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"league_id": int(league_id), "season": int(season), "error": str(exc)})
            continue

        for item in payload.get("response") or []:
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            status = (fixture.get("status") or {}).get("short")
            timestamp = fixture.get("timestamp")
            if status not in COMPLETED or timestamp is None:
                continue
            date = pd.to_datetime(int(timestamp), unit="s", utc=True)
            if date < UNION_START or date > UNION_END:
                continue
            home_id = home.get("id")
            away_id = away.get("id")
            if home_id not in team_ids and away_id not in team_ids:
                continue

            league_name = str(league.get("name") or league_name_hint)
            friendly = int(league_id) in FRIENDLY_IDS or "friendly" in league_name.lower()
            youth = is_youth(league_name)
            official_senior_main = not friendly and not youth

            rows.append(
                {
                    "fixture_id": int(fixture["id"]),
                    "date_utc": date.isoformat(),
                    "league_id": int(league_id),
                    "league_name": league_name,
                    "league_type": group["league_type"].dropna().iloc[0] if group["league_type"].notna().any() else None,
                    "country": league.get("country") or (group["country"].dropna().iloc[0] if group["country"].notna().any() else None),
                    "season": int(season),
                    "home_team_id": int(home_id) if home_id is not None else None,
                    "home_team": home.get("name"),
                    "away_team_id": int(away_id) if away_id is not None else None,
                    "away_team": away.get("name"),
                    "status": status,
                    "is_friendly": friendly,
                    "is_youth": youth,
                    "official_senior_main": official_senior_main,
                    "in_current_window": bool(CURRENT_START <= date <= CURRENT_END),
                    "in_pre_world_cup_window": bool(PRE_START <= date <= PRE_END),
                }
            )
        if index % 25 == 0 or index == len(grouped):
            print(f"Competiciones procesadas: {index}/{len(grouped)}")

    fixtures = pd.DataFrame(rows)
    if not fixtures.empty:
        fixtures = fixtures.sort_values(["date_utc", "fixture_id"]).drop_duplicates("fixture_id")
    errors_df = pd.DataFrame(errors)

    main_fixtures = fixtures.loc[fixtures["official_senior_main"]].copy() if not fixtures.empty else fixtures
    summary = {
        "status": "fixture_inventory_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "league_season_pairs_requested": len(grouped),
        "network_calls_this_run": client.calls,
        "failed_league_season_pairs": int(len(errors_df)),
        "unique_fixtures_union_window": int(len(fixtures)),
        "official_senior_fixtures_union_window": int(len(main_fixtures)),
        "official_senior_fixtures_current_window": int(main_fixtures["in_current_window"].sum()) if not main_fixtures.empty else 0,
        "official_senior_fixtures_pre_world_cup_window": int(main_fixtures["in_pre_world_cup_window"].sum()) if not main_fixtures.empty else 0,
        "friendlies_excluded": int(fixtures["is_friendly"].sum()) if not fixtures.empty else 0,
        "youth_fixtures_excluded": int(fixtures["is_youth"].sum()) if not fixtures.empty else 0,
        "raw_responses_sha256": hashlib.sha256("".join(sorted(client.hashes)).encode("utf-8")).hexdigest(),
        "methodological_gate": {
            "rankings_allowed": False,
            "next_step": "Priorizar fixtures que contienen jugadores elegibles y descargar estadísticas individuales en lotes auditables.",
        },
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fixtures.to_csv(AUDIT_DIR / "exact_fixture_inventory.csv", index=False)
    errors_df.to_csv(AUDIT_DIR / "fixture_inventory_errors.csv", index=False)
    if not main_fixtures.empty:
        by_comp = (
            main_fixtures.groupby(["league_id", "league_name", "season"], as_index=False)
            .agg(
                fixtures=("fixture_id", "nunique"),
                current_window=("in_current_window", "sum"),
                pre_world_cup_window=("in_pre_world_cup_window", "sum"),
            )
            .sort_values("fixtures", ascending=False)
        )
    else:
        by_comp = pd.DataFrame()
    by_comp.to_csv(AUDIT_DIR / "fixture_inventory_by_competition.csv", index=False)
    (AUDIT_DIR / "fixture_inventory_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
