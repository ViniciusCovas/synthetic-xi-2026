"""Pipeline acumulativo de la Copa 2026."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .api_football import APIFootballClient
from .config import POSITION_METRICS, StudySpec, XI_SLOTS
from .features import aggregate_features, flatten_player_match
from .ranking import (
    build_avatars,
    build_experimental_lineups,
    build_positional_comparisons,
    build_real_benchmarks,
    rank_players,
)
from .roles import infer_starting_roles


def _iso_to_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp())


def run_pipeline(
    client: APIFootballClient,
    spec: StudySpec = StudySpec(),
    cutoff_utc: str | None = None,
    output_dir: str | Path = "data/processed",
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    cutoff_timestamp = _iso_to_timestamp(cutoff_utc)
    fixtures = client.completed_fixtures(spec.league_id, spec.season, cutoff_timestamp)
    player_rows: list[dict[str, Any]] = []
    fixture_rows: list[dict[str, Any]] = []

    fixture_ids = [int((item.get("fixture") or {})["id"]) for item in fixtures]
    enriched_by_id: dict[int, dict[str, Any]] = {}
    for start in range(0, len(fixture_ids), 20):
        for enriched in client.enriched_fixtures(fixture_ids[start : start + 20]):
            enriched_fixture = enriched.get("fixture") or {}
            if enriched_fixture.get("id") is not None:
                enriched_by_id[int(enriched_fixture["id"])] = enriched
    excluded_substitute_entries = 0
    classification_counts: dict[str, int] = {}

    for item in fixtures:
        fixture = item.get("fixture") or {}
        fixture_id = int(fixture["id"])
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        fixture_rows.append(
            {
                "fixture_id": fixture_id,
                "date": fixture.get("date"),
                "status": (fixture.get("status") or {}).get("short"),
                "home_team": (teams.get("home") or {}).get("name"),
                "away_team": (teams.get("away") or {}).get("name"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            }
        )

        enriched = enriched_by_id.get(fixture_id, {})
        lineups = enriched.get("lineups") or client.lineups(fixture_id)
        roles_by_team: dict[int, dict[int, dict[str, Any]]] = {}
        for lineup in lineups:
            team = lineup.get("team") or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            roles = infer_starting_roles(lineup)
            roles_by_team[int(team_id)] = roles
            for role in roles.values():
                classification_counts[role["position_group"]] = (
                    classification_counts.get(role["position_group"], 0) + 1
                )

        stats_teams = enriched.get("players") or client.player_statistics(fixture_id)
        for team_block in stats_teams:
            team = team_block.get("team") or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            role_map = roles_by_team.get(int(team_id), {})
            for player_entry in team_block.get("players") or []:
                player_id = (player_entry.get("player") or {}).get("id")
                role = role_map.get(int(player_id)) if player_id is not None else None
                if role is None:
                    excluded_substitute_entries += 1
                    continue
                row = flatten_player_match(
                    fixture_id,
                    int(team_id),
                    team.get("name"),
                    player_entry,
                    role,
                )
                if row:
                    player_rows.append(row)

    player_matches = pd.DataFrame(player_rows)
    features = aggregate_features(player_matches)
    rankings = rank_players(
        features,
        minimum_minutes=spec.minimum_minutes,
        reliability_prior_minutes=spec.reliability_prior_minutes,
    )
    avatars, avatar_metrics, avatar_members = build_avatars(
        rankings,
        requested_top_n=spec.requested_top_n,
        seed=spec.seed,
        trim_fraction=spec.trim_fraction,
    )
    real_benchmarks = build_real_benchmarks(rankings)
    positional_comparisons = build_positional_comparisons(
        avatar_metrics, real_benchmarks
    )
    synthetic_xi, real_best_xi = build_experimental_lineups(rankings, avatars)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = {
        "fixtures": pd.DataFrame(fixture_rows),
        "player_matches": player_matches,
        "player_features": features,
        "rankings": rankings,
        "avatars": avatars,
        "avatar_metrics": avatar_metrics,
        "avatar_members": avatar_members,
        "real_benchmarks": real_benchmarks,
        "positional_comparisons": positional_comparisons,
        "synthetic_xi": synthetic_xi,
        "real_best_xi": real_best_xi,
    }
    for name, frame in frames.items():
        frame.to_csv(out / f"{name}.csv", index=False)

    raw_hashes = sorted(item["sha256"] for item in client.request_log)
    aggregate_digest = (
        hashlib.sha256("".join(raw_hashes).encode("utf-8")).hexdigest()
        if raw_hashes
        else None
    )
    raw_manifest = {
        "aggregate_sha256": aggregate_digest,
        "responses": client.request_log,
    }
    (out / "raw_manifest.json").write_text(
        json.dumps(raw_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest = {
        "status": "ready" if not avatars.empty else "no_eligible_avatars",
        "project_version": "0.3.0",
        "competition": spec.competition_name,
        "league_id": spec.league_id,
        "season": spec.season,
        "generated_at_utc": generated_at,
        "data_cutoff_utc": cutoff_utc or generated_at,
        "completed_matches_included": len(fixtures),
        "starter_player_match_rows": len(player_matches),
        "excluded_entries_without_precise_starting_role": excluded_substitute_entries,
        "position_classification_counts": classification_counts,
        "requested_top_n": spec.requested_top_n,
        "minimum_minutes": spec.minimum_minutes,
        "reliability_prior_minutes": spec.reliability_prior_minutes,
        "trim_fraction": spec.trim_fraction,
        "source": "API-FOOTBALL / API-SPORTS",
        "provider_responses_hashed": len(raw_hashes),
        "raw_snapshot_digest_sha256": aggregate_digest,
        "scope_claim": (
            "Mejor significa mayor puntuación dentro de la misma posición, en este "
            "corte acumulado de la Copa 2026 y bajo el índice pre-registrado."
        ),
        "studies": [
            "Estudio 1: avatar Top-20 vs mejor jugador real por posición",
            "Estudio 2: Synthetic XI vs Real Best XI, ambos con once integrantes",
        ],
        "xi_slots": XI_SLOTS,
    }
    methods = {
        "idioma": "español",
        "especificacion": spec.__dict__,
        "metricas_por_posicion": POSITION_METRICS,
        "inferencia_de_rol": (
            "Solo titulares; rol inferido con posición del proveedor, formación y "
            "coordenada de la alineación."
        ),
        "ranking": (
            "Media de z-scores winsorizados, con dirección corregida y retracción "
            "por minutos hacia la media de la posición."
        ),
        "mejor_jugador_real": (
            "Número 1 del índice posicional después del ajuste por confiabilidad."
        ),
        "avatar": (
            "Media recortada al 10% de los Top-20 elegibles de cada posición; "
            "Top-10 y Top-30 quedan como análisis de sensibilidad."
        ),
        "incertidumbre": (
            "Intervalo bootstrap no paramétrico de 95% con semilla determinista."
        ),
        "once_experimental": (
            "4-3-3 funcional: 1 GK, 2 CB, 2 FB, 1 DM, 1 CM, 1 AM, 2 W y 1 ST."
        ),
        "limitaciones": [
            "El torneo está en curso; todo resultado corresponde a un corte fechado.",
            "En v0.3 se excluyen suplentes cuyo rol detallado no puede inferirse con seguridad.",
            "Las estadísticas agregadas no observan por completo la inteligencia sin balón.",
            "El Estudio 2 no afirmará causalidad física hasta completar y validar el motor de simulación.",
        ],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "methods.json").write_text(
        json.dumps(methods, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {**frames, "manifest": manifest, "methods": methods}
