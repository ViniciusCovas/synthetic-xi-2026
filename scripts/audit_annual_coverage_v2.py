#!/usr/bin/env python3
"""Audita la cobertura anual para los jugadores del Mundial 2026.

Versión tolerante a límites por minuto y a datos faltantes. Esta fase no crea
rankings: mapea jugadores, competiciones y cobertura antes de la extracción por
partido.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

API_BASE = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE_ID = 1
WORLD_CUP_SEASON = 2026
ANNUAL_SEASONS = (2025, 2026)
OUT_DIR = Path("data/audits")
RAW_DIR = Path("data/raw/annual_coverage")
MAX_ATTEMPTS = 7
MAX_REQUESTS_PER_MINUTE = int(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "220"))
MIN_REQUEST_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE


class AuditClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("API_FOOTBALL_KEY")
        if not self.api_key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.session = requests.Session()
        self.calls = 0
        self.remaining: str | None = None
        self.response_hashes: list[str] = []
        self.failures: list[dict[str, Any]] = []
        self.last_network_call = 0.0

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self.last_network_call
        wait = MIN_REQUEST_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)

    @staticmethod
    def _error_text(errors: Any) -> str:
        if isinstance(errors, dict):
            return " | ".join(f"{key}: {value}" for key, value in errors.items())
        return str(errors)

    @staticmethod
    def _looks_transient(message: str) -> bool:
        lowered = message.lower()
        tokens = (
            "too many",
            "rate",
            "limit",
            "request",
            "temporar",
            "timeout",
            "unavailable",
        )
        return any(token in lowered for token in tokens)

    def get(self, endpoint: str, params: dict[str, Any], cache_name: str) -> dict[str, Any]:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / f"{cache_name}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = "cache"
        else:
            last_error: Exception | None = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    self._wait_for_slot()
                    response = self.session.get(
                        f"{API_BASE}/{endpoint.lstrip('/')}",
                        params=params,
                        headers={"x-apisports-key": self.api_key},
                        timeout=90,
                    )
                    self.last_network_call = time.monotonic()
                    self.calls += 1
                    self.remaining = response.headers.get("x-ratelimit-requests-remaining")

                    if response.status_code == 429:
                        retry_after = float(response.headers.get("retry-after") or 60)
                        raise requests.HTTPError(
                            f"429 rate limit; retry-after={retry_after}", response=response
                        )
                    if response.status_code >= 500:
                        raise requests.HTTPError(
                            f"HTTP {response.status_code}", response=response
                        )
                    response.raise_for_status()
                    payload = response.json()
                    errors = payload.get("errors") or {}
                    if errors:
                        message = self._error_text(errors)
                        if self._looks_transient(message):
                            raise RuntimeError(message)
                        raise ValueError(
                            f"API-Football devolvió errores en {endpoint}: {message}"
                        )
                    path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    source = "network"
                    break
                except (requests.RequestException, RuntimeError) as exc:
                    last_error = exc
                    if attempt == MAX_ATTEMPTS:
                        raise RuntimeError(
                            f"No se pudo completar {endpoint} después de {MAX_ATTEMPTS} intentos: {exc}"
                        ) from exc
                    response = getattr(exc, "response", None)
                    retry_header = None
                    if response is not None:
                        retry_header = response.headers.get("retry-after")
                    delay = float(retry_header or min(90, 3 * (2 ** (attempt - 1))))
                    print(
                        f"[retry {attempt}/{MAX_ATTEMPTS}] {endpoint} {params}: {exc}; "
                        f"espera={delay:.1f}s"
                    )
                    time.sleep(delay)
            else:
                raise RuntimeError(f"Solicitud sin resultado: {last_error}")

        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.response_hashes.append(
            hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        )
        print(f"[{source}] {endpoint} {params}")
        return payload

    def safe_get(
        self, endpoint: str, params: dict[str, Any], cache_name: str, context: str
    ) -> dict[str, Any]:
        try:
            return self.get(endpoint, params, cache_name)
        except Exception as exc:  # registra el caso y permite continuar la auditoría
            failure = {
                "endpoint": endpoint,
                "params": params,
                "context": context,
                "error": str(exc),
            }
            self.failures.append(failure)
            print(f"[warning] {failure}")
            return {"response": []}


def _coverage_row(item: dict[str, Any], league_id: int, season: int) -> dict[str, Any]:
    league = item.get("league") or {}
    country = item.get("country") or {}
    selected = {}
    for season_item in item.get("seasons") or []:
        if int(season_item.get("year") or -1) == season:
            selected = season_item
            break
    coverage = selected.get("coverage") or {}
    fixtures = coverage.get("fixtures") or {}
    return {
        "league_id": league_id,
        "league_name": league.get("name"),
        "league_type": league.get("type"),
        "country": country.get("name"),
        "season": season,
        "coverage_events": bool(fixtures.get("events")),
        "coverage_lineups": bool(fixtures.get("lineups")),
        "coverage_fixture_statistics": bool(fixtures.get("statistics_fixtures")),
        "coverage_player_statistics": bool(fixtures.get("statistics_players")),
        "coverage_players": bool(coverage.get("players")),
        "coverage_injuries": bool(coverage.get("injuries")),
        "coverage_predictions": bool(coverage.get("predictions")),
        "coverage_odds": bool(coverage.get("odds")),
        "coverage_standings": bool(coverage.get("standings")),
        "season_start": selected.get("start"),
        "season_end": selected.get("end"),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = AuditClient()
    generated_at = datetime.now(timezone.utc).isoformat()

    teams_payload = client.get(
        "teams",
        {"league": WORLD_CUP_LEAGUE_ID, "season": WORLD_CUP_SEASON},
        "world_cup_2026_teams",
    )
    teams = teams_payload.get("response") or []
    if not teams:
        raise RuntimeError("La API no devolvió las selecciones del Mundial 2026")

    player_map: dict[int, dict[str, Any]] = {}
    squad_rows: list[dict[str, Any]] = []
    for team_item in teams:
        team = team_item.get("team") or {}
        team_id = int(team["id"])
        payload = client.safe_get(
            "players/squads",
            {"team": team_id},
            f"squad_{team_id}",
            context=f"selección {team.get('name')}",
        )
        for block in payload.get("response") or []:
            response_team = block.get("team") or team
            for player in block.get("players") or []:
                player_id = int(player["id"])
                row = {
                    "player_id": player_id,
                    "player_name": player.get("name"),
                    "world_cup_team_id": int(response_team.get("id") or team_id),
                    "world_cup_team": response_team.get("name") or team.get("name"),
                    "squad_position": player.get("position"),
                    "age": player.get("age"),
                    "number": player.get("number"),
                }
                squad_rows.append(row)
                player_map.setdefault(player_id, row)

    if not player_map:
        raise RuntimeError("No se recuperó ningún jugador de las selecciones")

    max_players_raw = os.getenv("AUDIT_MAX_PLAYERS")
    player_ids = sorted(player_map)
    if max_players_raw:
        player_ids = player_ids[: int(max_players_raw)]

    stat_rows: list[dict[str, Any]] = []
    player_status: list[dict[str, Any]] = []
    league_seasons: set[tuple[int, int]] = set()

    total = len(player_ids)
    for index, player_id in enumerate(player_ids, start=1):
        base = player_map[player_id]
        seasons_found: Counter[int] = Counter()
        competition_lines = 0
        total_minutes = 0.0
        failed_seasons: list[int] = []
        for season in ANNUAL_SEASONS:
            payload = client.safe_get(
                "players",
                {"id": player_id, "season": season},
                f"player_{player_id}_season_{season}",
                context=f"jugador {player_id} temporada {season}",
            )
            if not payload.get("response") and any(
                item.get("context") == f"jugador {player_id} temporada {season}"
                for item in client.failures
            ):
                failed_seasons.append(season)
            for response_item in payload.get("response") or []:
                profile = response_item.get("player") or {}
                for stat in response_item.get("statistics") or []:
                    team = stat.get("team") or {}
                    league = stat.get("league") or {}
                    games = stat.get("games") or {}
                    league_id = league.get("id")
                    raw_stat_season = league.get("season")
                    try:
                        stat_season = int(raw_stat_season or season)
                    except (TypeError, ValueError):
                        stat_season = season
                    if league_id is None:
                        continue
                    minutes = float(games.get("minutes") or 0)
                    row = {
                        **base,
                        "profile_name": profile.get("name"),
                        "season_query": season,
                        "season": stat_season,
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "league_id": int(league_id),
                        "league_name": league.get("name"),
                        "league_country": league.get("country"),
                        "appearances": games.get("appearences"),
                        "lineups": games.get("lineups"),
                        "minutes": minutes,
                        "provider_position": games.get("position"),
                        "provider_rating": games.get("rating"),
                    }
                    stat_rows.append(row)
                    league_seasons.add((int(league_id), stat_season))
                    seasons_found[season] += 1
                    competition_lines += 1
                    total_minutes += minutes
        player_status.append(
            {
                **base,
                "has_2025_statistics": bool(seasons_found[2025]),
                "has_2026_statistics": bool(seasons_found[2026]),
                "failed_2025_query": 2025 in failed_seasons,
                "failed_2026_query": 2026 in failed_seasons,
                "competition_stat_lines": competition_lines,
                "reported_minutes_across_lines": total_minutes,
            }
        )
        if index % 25 == 0 or index == total:
            print(
                f"Jugadores auditados: {index}/{total}; "
                f"llamadas_red={client.calls}; fallos={len(client.failures)}"
            )

    coverage_rows: list[dict[str, Any]] = []
    for league_id, season in sorted(league_seasons):
        payload = client.safe_get(
            "leagues",
            {"id": league_id, "season": season},
            f"coverage_league_{league_id}_season_{season}",
            context=f"cobertura liga {league_id} temporada {season}",
        )
        response_items = payload.get("response") or []
        if response_items:
            coverage_rows.append(
                _coverage_row(response_items[0], league_id=league_id, season=season)
            )

    squads = pd.DataFrame(squad_rows).drop_duplicates(
        subset=["player_id", "world_cup_team_id"]
    )
    players = pd.DataFrame(player_status).drop_duplicates(subset=["player_id"])
    statistics = pd.DataFrame(stat_rows)
    coverage = pd.DataFrame(coverage_rows)

    squads.to_csv(OUT_DIR / "world_cup_2026_squad_universe.csv", index=False)
    players.to_csv(OUT_DIR / "annual_player_coverage.csv", index=False)
    statistics.to_csv(OUT_DIR / "annual_player_competitions.csv", index=False)
    coverage.to_csv(OUT_DIR / "annual_competition_coverage.csv", index=False)
    (OUT_DIR / "annual_audit_failures.json").write_text(
        json.dumps(client.failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    unique_players = int(players["player_id"].nunique()) if not players.empty else 0
    both_seasons = int(
        (players["has_2025_statistics"] & players["has_2026_statistics"]).sum()
    ) if not players.empty else 0
    no_statistics = int(
        (~players["has_2025_statistics"] & ~players["has_2026_statistics"]).sum()
    ) if not players.empty else 0
    player_stats_coverage = float(
        coverage["coverage_player_statistics"].mean()
    ) if not coverage.empty else 0.0
    digest = hashlib.sha256(
        "".join(sorted(client.response_hashes)).encode("utf-8")
    ).hexdigest()

    summary = {
        "status": (
            "audit_completed_with_warnings_decision_pending"
            if client.failures
            else "audit_completed_decision_pending"
        ),
        "generated_at_utc": generated_at,
        "window_current": ["2025-07-18", "2026-07-17"],
        "window_pre_world_cup": ["2025-06-11", "2026-06-10"],
        "world_cup_teams": len(teams),
        "squad_rows": int(len(squads)),
        "unique_players_audited": unique_players,
        "players_with_2025_statistics": int(players["has_2025_statistics"].sum()) if not players.empty else 0,
        "players_with_2026_statistics": int(players["has_2026_statistics"].sum()) if not players.empty else 0,
        "players_with_both_seasons": both_seasons,
        "players_without_statistics": no_statistics,
        "competition_stat_lines": int(len(statistics)),
        "unique_league_season_pairs": int(len(coverage)),
        "league_season_pairs_with_player_match_statistics_share": player_stats_coverage,
        "network_calls_this_run": client.calls,
        "daily_requests_remaining_reported": client.remaining,
        "failed_requests": len(client.failures),
        "configured_requests_per_minute_ceiling": MAX_REQUESTS_PER_MINUTE,
        "raw_responses_sha256": digest,
        "methodological_gate": {
            "ranking_allowed": False,
            "next_decision": "Revisar sesgo de cobertura por país, liga, posición y selección antes de extraer partidos.",
        },
        "notes": [
            "Las estadísticas de temporada sirven para mapear el universo, no para el ranking final de ventana exacta.",
            "La auditoría usa caché persistente y puede reanudarse sin repetir respuestas ya guardadas.",
            "La siguiente fase recogerá fixtures dentro de fechas exactas y deduplicará partidos.",
            "Los amistosos se marcarán y se excluirán del modelo principal.",
        ],
    }
    (OUT_DIR / "annual_coverage_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
