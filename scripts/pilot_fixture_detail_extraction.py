#!/usr/bin/env python3
"""Piloto estratificado de estadísticas individuales y alineaciones por partido.

Selecciona hasta dos partidos por combinación liga-temporada del inventario exacto:
el primero y el último cronológicamente. El objetivo es validar el esquema, la
completitud y la capacidad de asignar roles antes de iniciar la extracción masiva.
No genera rankings.
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
RAW_DIR = Path("data/raw/fixture_detail_pilot")
COMPLETED_CACHE = RAW_DIR / "completed_fixture_ids.json"


class Client:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.key = key
        self.session = requests.Session()
        self.calls = 0
        self.remaining: str | None = None
        self.hashes: list[str] = []
        self.min_interval = 60.0 / float(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "200"))
        self.last_call = 0.0

    def get(self, endpoint: str, fixture_id: int, suffix: str) -> dict[str, Any]:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / f"fixture_{fixture_id}_{suffix}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = "cache"
        else:
            attempts = 0
            while True:
                attempts += 1
                wait = self.min_interval - (time.monotonic() - self.last_call)
                if wait > 0:
                    time.sleep(wait)
                response = self.session.get(
                    f"{API_BASE}/{endpoint.lstrip('/')}",
                    params={"fixture": fixture_id},
                    headers={"x-apisports-key": self.key},
                    timeout=90,
                )
                self.last_call = time.monotonic()
                self.remaining = response.headers.get("x-ratelimit-requests-remaining")
                if response.status_code in {429, 500, 502, 503, 504} and attempts < 6:
                    retry_after = float(response.headers.get("retry-after") or min(60, 2 ** attempts))
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                payload = response.json()
                errors = payload.get("errors") or {}
                if errors and attempts < 6:
                    text = json.dumps(errors).lower()
                    if "limit" in text or "rate" in text or "tempor" in text:
                        time.sleep(min(60, 2 ** attempts))
                        continue
                if errors:
                    raise RuntimeError(f"API-Football devolvió errores en {endpoint}: {errors}")
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self.calls += 1
                source = "network"
                break
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.hashes.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        print(f"[{source}] {endpoint} fixture={fixture_id}")
        return payload


def select_pilot(fixtures: pd.DataFrame) -> pd.DataFrame:
    eligible = fixtures.loc[fixtures["official_senior_main"].astype(bool)].copy()
    eligible["date_utc"] = pd.to_datetime(eligible["date_utc"], utc=True)
    selected: list[pd.DataFrame] = []
    for _, group in eligible.groupby(["league_id", "season"], sort=True):
        ordered = group.sort_values(["date_utc", "fixture_id"])
        if len(ordered) == 1:
            selected.append(ordered.head(1))
        else:
            selected.append(pd.concat([ordered.head(1), ordered.tail(1)]))
    pilot = pd.concat(selected, ignore_index=True)
    pilot = pilot.drop_duplicates("fixture_id").sort_values(["league_id", "season", "date_utc"])
    max_fixtures = int(os.getenv("PILOT_MAX_FIXTURES", "250"))
    if len(pilot) > max_fixtures:
        pilot = pilot.head(max_fixtures)
    return pilot.reset_index(drop=True)


def flatten_player_stats(fixture: pd.Series, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in payload.get("response") or []:
        team = team_block.get("team") or {}
        for item in team_block.get("players") or []:
            player = item.get("player") or {}
            for stat in item.get("statistics") or []:
                games = stat.get("games") or {}
                shots = stat.get("shots") or {}
                goals = stat.get("goals") or {}
                passes = stat.get("passes") or {}
                tackles = stat.get("tackles") or {}
                duels = stat.get("duels") or {}
                dribbles = stat.get("dribbles") or {}
                fouls = stat.get("fouls") or {}
                cards = stat.get("cards") or {}
                penalty = stat.get("penalty") or {}
                rows.append(
                    {
                        "fixture_id": int(fixture["fixture_id"]),
                        "date_utc": fixture["date_utc"],
                        "league_id": int(fixture["league_id"]),
                        "league_name": fixture["league_name"],
                        "season": int(fixture["season"]),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "player_id": player.get("id"),
                        "player_name": player.get("name"),
                        "minutes": games.get("minutes"),
                        "number": games.get("number"),
                        "provider_position": games.get("position"),
                        "rating": games.get("rating"),
                        "captain": games.get("captain"),
                        "substitute": games.get("substitute"),
                        "offsides": stat.get("offsides"),
                        "shots_total": shots.get("total"),
                        "shots_on": shots.get("on"),
                        "goals_total": goals.get("total"),
                        "goals_conceded": goals.get("conceded"),
                        "assists": goals.get("assists"),
                        "saves": goals.get("saves"),
                        "passes_total": passes.get("total"),
                        "passes_key": passes.get("key"),
                        "passes_accuracy_raw": passes.get("accuracy"),
                        "tackles_total": tackles.get("total"),
                        "blocks": tackles.get("blocks"),
                        "interceptions": tackles.get("interceptions"),
                        "duels_total": duels.get("total"),
                        "duels_won": duels.get("won"),
                        "dribbles_attempts": dribbles.get("attempts"),
                        "dribbles_success": dribbles.get("success"),
                        "fouls_drawn": fouls.get("drawn"),
                        "fouls_committed": fouls.get("committed"),
                        "yellow": cards.get("yellow"),
                        "red": cards.get("red"),
                        "penalty_won": penalty.get("won"),
                        "penalty_committed": penalty.get("commited"),
                        "penalty_scored": penalty.get("scored"),
                        "penalty_missed": penalty.get("missed"),
                        "penalty_saved": penalty.get("saved"),
                    }
                )
    return rows


def flatten_lineups(fixture: pd.Series, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in payload.get("response") or []:
        team = team_block.get("team") or {}
        formation = team_block.get("formation")
        for source, entries in (("startXI", team_block.get("startXI") or []), ("substitutes", team_block.get("substitutes") or [])):
            for entry in entries:
                player = entry.get("player") or {}
                rows.append(
                    {
                        "fixture_id": int(fixture["fixture_id"]),
                        "date_utc": fixture["date_utc"],
                        "league_id": int(fixture["league_id"]),
                        "league_name": fixture["league_name"],
                        "season": int(fixture["season"]),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "formation": formation,
                        "lineup_source": source,
                        "player_id": player.get("id"),
                        "player_name": player.get("name"),
                        "number": player.get("number"),
                        "lineup_position": player.get("pos"),
                        "grid": player.get("grid"),
                    }
                )
    return rows


def ratio(series: pd.Series) -> float:
    return float(series.notna().mean()) if len(series) else 0.0


def main() -> None:
    fixtures = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")
    pilot = select_pilot(fixtures)
    client = Client()

    player_rows: list[dict[str, Any]] = []
    lineup_rows: list[dict[str, Any]] = []
    fixture_quality: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, fixture in pilot.iterrows():
        fixture_id = int(fixture["fixture_id"])
        try:
            players_payload = client.get("fixtures/players", fixture_id, "players")
            lineups_payload = client.get("fixtures/lineups", fixture_id, "lineups")
            players_flat = flatten_player_stats(fixture, players_payload)
            lineups_flat = flatten_lineups(fixture, lineups_payload)
            player_rows.extend(players_flat)
            lineup_rows.extend(lineups_flat)
            fixture_quality.append(
                {
                    "fixture_id": fixture_id,
                    "league_id": int(fixture["league_id"]),
                    "league_name": fixture["league_name"],
                    "season": int(fixture["season"]),
                    "player_rows": len(players_flat),
                    "lineup_rows": len(lineups_flat),
                    "players_response_nonempty": bool(players_flat),
                    "lineups_response_nonempty": bool(lineups_flat),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "fixture_id": fixture_id,
                    "league_id": int(fixture["league_id"]),
                    "league_name": fixture["league_name"],
                    "season": int(fixture["season"]),
                    "error": str(exc),
                }
            )
        if (index + 1) % 25 == 0 or index + 1 == len(pilot):
            print(f"Partidos piloto procesados: {index + 1}/{len(pilot)}")

    players = pd.DataFrame(player_rows)
    lineups = pd.DataFrame(lineup_rows)
    quality = pd.DataFrame(fixture_quality)
    errors_df = pd.DataFrame(errors)

    player_minutes = pd.to_numeric(players.get("minutes"), errors="coerce") if not players.empty else pd.Series(dtype=float)
    starters = lineups.loc[lineups["lineup_source"] == "startXI"] if not lineups.empty else lineups

    metrics = {
        "sampled_fixtures": int(len(pilot)),
        "successful_fixtures": int(len(quality)),
        "failed_fixtures": int(len(errors_df)),
        "player_stat_rows": int(len(players)),
        "lineup_rows": int(len(lineups)),
        "players_response_nonempty_rate": float(quality["players_response_nonempty"].mean()) if not quality.empty else 0.0,
        "lineups_response_nonempty_rate": float(quality["lineups_response_nonempty"].mean()) if not quality.empty else 0.0,
        "minutes_nonnull_rate": ratio(players["minutes"]) if not players.empty else 0.0,
        "position_nonnull_rate": ratio(players["provider_position"]) if not players.empty else 0.0,
        "rating_nonnull_rate": ratio(players["rating"]) if not players.empty else 0.0,
        "passes_total_nonnull_rate": ratio(players["passes_total"]) if not players.empty else 0.0,
        "starter_grid_nonnull_rate": ratio(starters["grid"]) if not starters.empty else 0.0,
        "starter_position_nonnull_rate": ratio(starters["lineup_position"]) if not starters.empty else 0.0,
        "positive_minute_rows": int((player_minutes > 0).sum()) if len(player_minutes) else 0,
        "network_calls_this_run": client.calls,
        "daily_requests_remaining_reported": client.remaining,
    }

    thresholds = {
        "players_response_nonempty_rate": 0.95,
        "lineups_response_nonempty_rate": 0.90,
        "minutes_nonnull_rate": 0.95,
        "position_nonnull_rate": 0.95,
        "passes_total_nonnull_rate": 0.90,
        "starter_grid_nonnull_rate": 0.85,
        "starter_position_nonnull_rate": 0.95,
    }
    checks = {key: metrics[key] >= value for key, value in thresholds.items()}
    approved = all(checks.values()) and metrics["failed_fixtures"] == 0

    summary = {
        "status": "pilot_approved_for_resumable_full_extraction" if approved else "pilot_requires_methodological_repairs",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "Hasta dos fixtures por combinación liga-temporada: primero y último cronológicamente.",
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "methodological_gate": {
            "full_extraction_allowed": approved,
            "rankings_allowed": False,
            "next_step": "Diseñar extracción completa por lotes con estado persistente." if approved else "Revisar campos y competiciones que no superaron los umbrales.",
        },
        "raw_responses_sha256": hashlib.sha256("".join(sorted(client.hashes)).encode("utf-8")).hexdigest(),
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    pilot.to_csv(AUDIT_DIR / "fixture_detail_pilot_sample.csv", index=False)
    players.to_csv(AUDIT_DIR / "fixture_detail_pilot_players.csv", index=False)
    lineups.to_csv(AUDIT_DIR / "fixture_detail_pilot_lineups.csv", index=False)
    quality.to_csv(AUDIT_DIR / "fixture_detail_pilot_quality.csv", index=False)
    errors_df.to_csv(AUDIT_DIR / "fixture_detail_pilot_errors.csv", index=False)
    (AUDIT_DIR / "fixture_detail_pilot_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    COMPLETED_CACHE.write_text(json.dumps(sorted(pilot["fixture_id"].astype(int).tolist())), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
