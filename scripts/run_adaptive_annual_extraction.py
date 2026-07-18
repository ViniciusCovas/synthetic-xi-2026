#!/usr/bin/env python3
"""Extração adaptativa e retomável de estatísticas por partida.

Prioriza jogadores pré-elegíveis, partidas úteis às duas janelas temporais e
competições com cobertura validada. Para antes de esgotar a cota diária, salva
progresso e nunca gera rankings nesta etapa.
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
LAKE_DIR = Path("data/lake")
BATCH_DIR = LAKE_DIR / "batches"
RAW_DIR = Path("data/raw/adaptive_annual")
PROGRESS_PATH = LAKE_DIR / "adaptive_fixture_progress.csv"
STATUS_PATH = AUDIT_DIR / "adaptive_extraction_status.json"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


class QuotaStop(RuntimeError):
    pass


class Client:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.session = requests.Session()
        self.key = key
        self.calls = 0
        self.remaining: int | None = None
        self.hashes: list[str] = []
        self.max_calls = int(os.getenv("MAX_NETWORK_REQUESTS", "2800"))
        self.min_remaining = int(os.getenv("MIN_DAILY_REQUESTS_REMAINING", "600"))
        self.interval = 60.0 / float(os.getenv("API_MAX_REQUESTS_PER_MINUTE", "190"))
        self.last_call = 0.0

    def get(self, endpoint: str, fixture_id: int, suffix: str) -> dict[str, Any]:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / f"fixture_{fixture_id}_{suffix}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = "cache"
        else:
            if self.calls >= self.max_calls:
                raise QuotaStop("Límite de llamadas de este lote alcanzado")
            if self.remaining is not None and self.remaining <= self.min_remaining:
                raise QuotaStop("Margen de seguridad de la cuota diaria alcanzado")
            attempts = 0
            while True:
                attempts += 1
                wait = self.interval - (time.monotonic() - self.last_call)
                if wait > 0:
                    time.sleep(wait)
                response = self.session.get(
                    f"{API_BASE}/{endpoint.lstrip('/')}",
                    params={"fixture": fixture_id},
                    headers={"x-apisports-key": self.key},
                    timeout=90,
                )
                self.last_call = time.monotonic()
                remaining = response.headers.get("x-ratelimit-requests-remaining")
                if remaining is not None:
                    try:
                        self.remaining = int(remaining)
                    except ValueError:
                        pass
                if response.status_code in {429, 500, 502, 503, 504} and attempts < 6:
                    retry_after = float(response.headers.get("retry-after") or min(60, 2**attempts))
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                payload = response.json()
                errors = payload.get("errors") or {}
                if errors and attempts < 6:
                    text = json.dumps(errors).lower()
                    if "limit" in text or "rate" in text or "tempor" in text:
                        time.sleep(min(60, 2**attempts))
                        continue
                if errors:
                    raise RuntimeError(f"API-Football devolvió errores en {endpoint}: {errors}")
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                self.calls += 1
                source = "network"
                break
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.hashes.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        print(f"[{source}] {endpoint} fixture={fixture_id} remaining={self.remaining}")
        return payload


def flatten_target_players(fixture: pd.Series, payload: dict[str, Any], target_ids: set[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in payload.get("response") or []:
        team = team_block.get("team") or {}
        for item in team_block.get("players") or []:
            player = item.get("player") or {}
            player_id = player.get("id")
            if player_id is None or int(player_id) not in target_ids:
                continue
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
                        "in_current_window": as_bool(fixture["in_current_window"]),
                        "in_pre_world_cup_window": as_bool(fixture["in_pre_world_cup_window"]),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "player_id": int(player_id),
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


def flatten_target_lineups(fixture: pd.Series, payload: dict[str, Any], target_ids: set[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team_block in payload.get("response") or []:
        team = team_block.get("team") or {}
        formation = team_block.get("formation")
        for source, entries in (("startXI", team_block.get("startXI") or []), ("substitutes", team_block.get("substitutes") or [])):
            for entry in entries:
                player = entry.get("player") or {}
                player_id = player.get("id")
                if player_id is None or int(player_id) not in target_ids:
                    continue
                rows.append(
                    {
                        "fixture_id": int(fixture["fixture_id"]),
                        "date_utc": fixture["date_utc"],
                        "league_id": int(fixture["league_id"]),
                        "season": int(fixture["season"]),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "formation": formation,
                        "lineup_source": source,
                        "player_id": int(player_id),
                        "player_name": player.get("name"),
                        "number": player.get("number"),
                        "lineup_position": player.get("pos"),
                        "grid": player.get("grid"),
                    }
                )
    return rows


def load_progress() -> pd.DataFrame:
    columns = ["fixture_id", "status", "target_players", "player_rows", "lineup_rows", "updated_at_utc"]
    if not PROGRESS_PATH.exists():
        return pd.DataFrame(columns=columns)
    progress = pd.read_csv(PROGRESS_PATH)
    return progress.drop_duplicates("fixture_id", keep="last")


def main() -> None:
    generated_at = datetime.now(timezone.utc)
    run_id = os.getenv("GITHUB_RUN_ID") or generated_at.strftime("%Y%m%dT%H%M%S")
    batch_id = f"batch_{run_id}"

    fixtures = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")
    competitions = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    pilot_pairs = pd.read_csv(AUDIT_DIR / "fixture_detail_pilot_by_competition.csv")

    eligible = precheck.loc[precheck["rank_entry_precheck"].map(as_bool)].copy()
    eligible_ids = set(eligible["player_id"].astype(int))
    benchmark_ids = set(eligible.loc[eligible["benchmark_precheck"].map(as_bool), "player_id"].astype(int))

    competitions = competitions.loc[competitions["player_id"].astype(int).isin(eligible_ids)].copy()
    for col in ["player_id", "league_id", "season", "team_id"]:
        competitions[col] = pd.to_numeric(competitions[col], errors="coerce")
    competitions = competitions.dropna(subset=["player_id", "league_id", "season", "team_id"])
    competitions[["player_id", "league_id", "season", "team_id"]] = competitions[["player_id", "league_id", "season", "team_id"]].astype(int)

    pair_quality = pilot_pairs.set_index(["league_id", "season"])["player_endpoint_rate"].to_dict()
    zero_pairs = {key for key, value in pair_quality.items() if float(value) == 0.0}

    association: dict[tuple[int, int, int], set[int]] = {}
    for row in competitions[["player_id", "league_id", "season", "team_id"]].drop_duplicates().itertuples(index=False):
        association.setdefault((row.league_id, row.season, row.team_id), set()).add(row.player_id)

    fixtures = fixtures.loc[fixtures["official_senior_main"].map(as_bool)].copy()
    fixtures = fixtures.loc[
        fixtures["in_current_window"].map(as_bool) | fixtures["in_pre_world_cup_window"].map(as_bool)
    ].copy()

    queue_rows: list[dict[str, Any]] = []
    unsupported_pairs: list[dict[str, Any]] = []
    for _, fixture in fixtures.iterrows():
        league_id = int(fixture["league_id"])
        season = int(fixture["season"])
        pair = (league_id, season)
        home_ids = association.get((league_id, season, int(fixture["home_team_id"])), set())
        away_ids = association.get((league_id, season, int(fixture["away_team_id"])), set())
        target_ids = home_ids | away_ids
        if not target_ids:
            continue
        if pair in zero_pairs:
            unsupported_pairs.append(
                {
                    "fixture_id": int(fixture["fixture_id"]),
                    "league_id": league_id,
                    "league_name": fixture["league_name"],
                    "season": season,
                    "target_players": len(target_ids),
                    "reason": "pilot_zero_player_endpoint",
                }
            )
            continue
        benchmark_count = len(target_ids & benchmark_ids)
        both_windows = as_bool(fixture["in_current_window"]) and as_bool(fixture["in_pre_world_cup_window"])
        quality = float(pair_quality.get(pair, 0.75))
        priority = benchmark_count * 100 + len(target_ids) * 10 + int(both_windows) * 50 + quality * 20
        queue_rows.append({**fixture.to_dict(), "target_ids": sorted(target_ids), "priority": priority})

    queue = pd.DataFrame(queue_rows)
    if queue.empty:
        raise RuntimeError("No se construyó ninguna cola de extracción")
    queue["date_sort"] = pd.to_datetime(queue["date_utc"], utc=True)
    queue = queue.sort_values(["priority", "date_sort"], ascending=[False, False])

    progress = load_progress()
    completed_ids = set(progress["fixture_id"].astype(int)) if not progress.empty else set()
    queue = queue.loc[~queue["fixture_id"].astype(int).isin(completed_ids)].reset_index(drop=True)

    client = Client()
    player_rows: list[dict[str, Any]] = []
    lineup_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    quota_stopped = False

    for index, fixture in queue.iterrows():
        fixture_id = int(fixture["fixture_id"])
        target_ids = {int(value) for value in fixture["target_ids"]}
        status = "completed"
        try:
            players_payload = client.get("fixtures/players", fixture_id, "players")
            targets = flatten_target_players(fixture, players_payload, target_ids)
            player_rows.extend(targets)
            if not (players_payload.get("response") or []):
                status = "player_endpoint_empty"
                lineups = []
            elif targets:
                lineups_payload = client.get("fixtures/lineups", fixture_id, "lineups")
                lineups = flatten_target_lineups(fixture, lineups_payload, target_ids)
                lineup_rows.extend(lineups)
            else:
                status = "no_target_player_returned"
                lineups = []
            progress_rows.append(
                {
                    "fixture_id": fixture_id,
                    "status": status,
                    "target_players": len(target_ids),
                    "player_rows": len(targets),
                    "lineup_rows": len(lineups),
                    "updated_at_utc": generated_at.isoformat(),
                }
            )
        except QuotaStop as exc:
            print(f"Extracción detenida de forma segura: {exc}")
            quota_stopped = True
            break
        except Exception as exc:  # noqa: BLE001
            print(f"Error reintentable fixture={fixture_id}: {exc}")
            progress_rows.append(
                {
                    "fixture_id": fixture_id,
                    "status": "retryable_error",
                    "target_players": len(target_ids),
                    "player_rows": 0,
                    "lineup_rows": 0,
                    "updated_at_utc": generated_at.isoformat(),
                }
            )
        if (index + 1) % 100 == 0:
            print(f"Fixtures recorridos en este lote: {index + 1}")

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    players_df = pd.DataFrame(player_rows)
    lineups_df = pd.DataFrame(lineup_rows)
    new_progress = pd.DataFrame(progress_rows)
    if not new_progress.empty:
        durable = new_progress.loc[new_progress["status"] != "retryable_error"]
        retryable = new_progress.loc[new_progress["status"] == "retryable_error"]
        progress = pd.concat([progress, durable], ignore_index=True).drop_duplicates("fixture_id", keep="last")
        # Erros reintentáveis não bloqueiam o fixture em execuções futuras.
        if not retryable.empty:
            retryable.to_csv(BATCH_DIR / f"{batch_id}_retryable_errors.csv", index=False)
    progress.to_csv(PROGRESS_PATH, index=False)

    if not players_df.empty:
        players_df.to_csv(BATCH_DIR / f"{batch_id}_players.csv.gz", index=False, compression="gzip")
    if not lineups_df.empty:
        lineups_df.to_csv(BATCH_DIR / f"{batch_id}_lineups.csv.gz", index=False, compression="gzip")
    pd.DataFrame(unsupported_pairs).drop_duplicates("fixture_id").to_csv(
        AUDIT_DIR / "adaptive_unsupported_fixtures.csv", index=False
    )

    total_queue = len(queue) + len(completed_ids)
    status = {
        "status": "adaptive_batch_completed",
        "generated_at_utc": generated_at.isoformat(),
        "batch_id": batch_id,
        "eligible_players": len(eligible_ids),
        "benchmark_players": len(benchmark_ids),
        "queue_total_estimate": total_queue,
        "completed_fixtures_total": int(len(progress)),
        "fixtures_processed_this_batch": int(len(new_progress)),
        "player_rows_this_batch": int(len(players_df)),
        "lineup_rows_this_batch": int(len(lineups_df)),
        "network_calls_this_batch": client.calls,
        "daily_requests_remaining_reported": client.remaining,
        "stopped_by_quota_guard": quota_stopped,
        "unsupported_zero_endpoint_fixtures": len({row["fixture_id"] for row in unsupported_pairs}),
        "raw_responses_sha256": hashlib.sha256("".join(sorted(client.hashes)).encode("utf-8")).hexdigest(),
        "methodological_gate": {
            "rankings_allowed": False,
            "next_step": "Recalcular cobertura por jugador y continuar por lotes hasta completar la cola elegible.",
        },
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    (BATCH_DIR / f"{batch_id}_manifest.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
