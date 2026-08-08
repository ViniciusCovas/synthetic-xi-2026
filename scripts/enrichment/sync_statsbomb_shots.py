#!/usr/bin/env python3
"""Ingesta completa de remates dos torneios internacionais do StatsBomb Open Data.

Baixa os eventos de FIFA World Cup 2018/2022 e UEFA Euro 2020/2024, extrai
apenas os REMATES (com coordenadas, corpo, contexto e o xG do provedor) e
agregados por partida, e grava tabelas compactas versionáveis. Os JSONs brutos
não são versionados (transientes).

Atribuição obrigatória: Hudl StatsBomb Open Data
(https://github.com/statsbomb/open-data). Uso de investigação; verificar os
termos antes de qualquer uso comercial derivado.

Uso: python scripts/enrichment/sync_statsbomb_shots.py [--max-matches N]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
OUT = Path("data/enrichment/statsbomb")
TARGET_COMPETITIONS = {
    ("FIFA World Cup", "2018"),
    ("FIFA World Cup", "2022"),
    ("UEFA Euro", "2020"),
    ("UEFA Euro", "2024"),
}
GOAL_X, GOAL_Y, GOAL_WIDTH = 120.0, 40.0, 7.32 * (80.0 / 68.0)  # unidades SB


def fetch_json(path: str):
    request = urllib.request.Request(
        f"{BASE}/{path}", headers={"User-Agent": "synthetic-xi-2026 research"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    dx, dy = GOAL_X - x, GOAL_Y - y
    distance = math.hypot(dx, dy)
    post_left, post_right = GOAL_Y - GOAL_WIDTH / 2, GOAL_Y + GOAL_WIDTH / 2
    angle = abs(
        math.atan2(post_right - y, dx) - math.atan2(post_left - y, dx)
    )
    return distance, angle


def extract_match(meta: dict) -> tuple[list[dict], dict]:
    match_id = meta["match_id"]
    events = fetch_json(f"events/{match_id}.json")
    shots: list[dict] = []
    passes = 0
    possessions = set()
    for event in events:
        possessions.add(event.get("possession"))
        kind = (event.get("type") or {}).get("name")
        if kind == "Pass":
            passes += 1
            continue
        if kind != "Shot":
            continue
        shot = event.get("shot") or {}
        location = event.get("location") or [None, None]
        if location[0] is None:
            continue
        distance, angle = shot_geometry(float(location[0]), float(location[1]))
        outcome = (shot.get("outcome") or {}).get("name")
        shots.append(
            {
                "competition": meta["competition"]["competition_name"],
                "season": meta["season"]["season_name"],
                "match_id": match_id,
                "minute": event.get("minute"),
                "period": event.get("period"),
                "team": (event.get("team") or {}).get("name"),
                "player": (event.get("player") or {}).get("name"),
                "x": float(location[0]),
                "y": float(location[1]),
                "distance_m": distance * 0.9144 * (100 / 120),  # jardas SB→m aprox
                "distance_sb": distance,
                "visible_angle_rad": angle,
                "body_part": (shot.get("body_part") or {}).get("name"),
                "technique": (shot.get("technique") or {}).get("name"),
                "shot_type": (shot.get("type") or {}).get("name"),
                "under_pressure": bool(event.get("under_pressure")),
                "one_on_one": bool(shot.get("one_on_one")),
                "open_goal": bool(shot.get("open_goal")),
                "first_time": bool(shot.get("first_time")),
                "is_goal": outcome == "Goal",
                "on_target": outcome in {"Goal", "Saved", "Saved To Post"},
                "statsbomb_xg": shot.get("statsbomb_xg"),
            }
        )
    aggregate = {
        "match_id": match_id,
        "competition": meta["competition"]["competition_name"],
        "season": meta["season"]["season_name"],
        "home_team": meta["home_team"]["home_team_name"],
        "away_team": meta["away_team"]["away_team_name"],
        "home_score": meta.get("home_score"),
        "away_score": meta.get("away_score"),
        "shots": len(shots),
        "goals": sum(1 for s in shots if s["is_goal"]),
        "passes": passes,
        "possessions": max(p for p in possessions if p is not None),
    }
    return shots, aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-matches", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    competitions = fetch_json("competitions.json")
    selected = [
        c for c in competitions
        if (c["competition_name"], str(c["season_name"])) in TARGET_COMPETITIONS
    ]
    matches: list[dict] = []
    for comp in selected:
        matches.extend(
            fetch_json(f"matches/{comp['competition_id']}/{comp['season_id']}.json")
        )
    if args.max_matches:
        matches = matches[: args.max_matches]

    all_shots: list[dict] = []
    aggregates: list[dict] = []
    failures: list[int] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract_match, meta): meta for meta in matches}
        for future in as_completed(futures):
            meta = futures[future]
            try:
                shots, aggregate = future.result()
                all_shots.extend(shots)
                aggregates.append(aggregate)
            except Exception:
                failures.append(meta["match_id"])

    shots_frame = pd.DataFrame(all_shots).sort_values(["match_id", "period", "minute"])
    agg_frame = pd.DataFrame(aggregates).sort_values("match_id")
    with gzip.open(OUT / "international_shots.csv.gz", "wt", encoding="utf-8") as fh:
        shots_frame.to_csv(fh, index=False)
    agg_frame.to_csv(OUT / "international_match_aggregates.csv", index=False)

    status = {
        "status": "statsbomb_international_shots_synced",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "competitions": sorted(
            {f"{c['competition_name']} {c['season_name']}" for c in selected}
        ),
        "matches_ingested": int(len(agg_frame)),
        "matches_failed": failures,
        "shots": int(len(shots_frame)),
        "goals": int(shots_frame["is_goal"].sum()),
        "attribution": "Hudl StatsBomb Open Data",
        "license_note": (
            "Uso de investigação com atribuição; confirmar termos StatsBomb "
            "antes de uso comercial derivado."
        ),
    }
    (OUT / "international_shots_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
