"""Audited cumulative World Cup 2026 pipeline, version 0.4."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .api_football import APIFootballClient
from .config import POSITION_METRICS, POSITION_ORDER, StudySpec, XI_SLOTS
from .features_v04 import aggregate_features, flatten_player_match, player_match_minutes
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
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def select_stable_primary_roles(
    role_minutes: dict[int, dict[str, float]],
    role_examples: dict[int, dict[str, dict[str, Any]]],
    minimum_share: float = 0.60,
) -> tuple[dict[int, dict[str, Any]], int]:
    """Select one primary role per player from precise starting-role minutes."""

    order = {role: index for index, role in enumerate(POSITION_ORDER)}
    selected: dict[int, dict[str, Any]] = {}
    ambiguous = 0
    for player_id, distribution in role_minutes.items():
        total = float(sum(distribution.values()))
        if total <= 0:
            continue
        best_role, best_minutes = sorted(
            distribution.items(), key=lambda item: (-item[1], order.get(item[0], 999))
        )[0]
        share = float(best_minutes / total)
        if share < minimum_share:
            ambiguous += 1
            continue
        example = dict(role_examples[player_id][best_role])
        example.update(
            {
                "position_group": best_role,
                "role_share": share,
                "precise_role_minutes": total,
                "classification_rule": (
                    f"rol primario del torneo: {best_role}, "
                    f"{share:.1%} de minutos con rol inicial preciso"
                ),
            }
        )
        selected[player_id] = example
    return selected, ambiguous


def run_pipeline(
    client: APIFootballClient,
    spec: StudySpec = StudySpec(),
    cutoff_utc: str | None = None,
    output_dir: str | Path = "data/processed",
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    fixtures = client.completed_fixtures(
        spec.league_id, spec.season, _iso_to_timestamp(cutoff_utc)
    )

    fixture_ids = [int((item.get("fixture") or {})["id"]) for item in fixtures]
    enriched_by_id: dict[int, dict[str, Any]] = {}
    for start in range(0, len(fixture_ids), 20):
        for enriched in client.enriched_fixtures(fixture_ids[start : start + 20]):
            fixture = enriched.get("fixture") or {}
            if fixture.get("id") is not None:
                enriched_by_id[int(fixture["id"])] = enriched

    fixture_rows: list[dict[str, Any]] = []
    pending_entries: list[dict[str, Any]] = []
    role_minutes: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    role_examples: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    precise_start_role_observations = 0

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
            team_id = (lineup.get("team") or {}).get("id")
            if team_id is not None:
                roles_by_team[int(team_id)] = infer_starting_roles(lineup)

        stats_teams = enriched.get("players") or client.player_statistics(fixture_id)
        for team_block in stats_teams:
            team = team_block.get("team") or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            exact_roles = roles_by_team.get(int(team_id), {})
            for player_entry in team_block.get("players") or []:
                player = player_entry.get("player") or {}
                player_id = player.get("id")
                minutes = player_match_minutes(player_entry)
                if player_id is None or minutes <= 0:
                    continue
                player_id = int(player_id)
                exact_role = exact_roles.get(player_id)
                if exact_role is not None:
                    group = exact_role["position_group"]
                    role_minutes[player_id][group] += minutes
                    role_examples[player_id][group] = exact_role
                    precise_start_role_observations += 1
                pending_entries.append(
                    {
                        "fixture_id": fixture_id,
                        "team_id": int(team_id),
                        "team_name": team.get("name"),
                        "player_id": player_id,
                        "player_entry": player_entry,
                        "exact_role": exact_role,
                    }
                )

    primary_roles, ambiguous_players = select_stable_primary_roles(
        role_minutes, role_examples, minimum_share=0.60
    )

    player_rows: list[dict[str, Any]] = []
    recovered_entries = 0
    reassigned_entries = 0
    excluded_entries = 0
    classification_counts: dict[str, int] = {}

    for pending in pending_entries:
        primary = primary_roles.get(pending["player_id"])
        if primary is None:
            excluded_entries += 1
            continue
        role = dict(primary)
        exact_role = pending["exact_role"]
        if exact_role is None:
            role["role_source"] = "rol primario inferido para aparicion no titular"
            recovered_entries += 1
        elif exact_role["position_group"] == role["position_group"]:
            role["role_source"] = "rol inicial preciso consistente con rol primario"
            role["formation"] = exact_role.get("formation")
        else:
            role["role_source"] = "aparicion secundaria reasignada al rol primario estable"
            reassigned_entries += 1

        row = flatten_player_match(
            pending["fixture_id"],
            pending["team_id"],
            pending["team_name"],
            pending["player_entry"],
            role,
        )
        if row:
            player_rows.append(row)
            group = role["position_group"]
            classification_counts[group] = classification_counts.get(group, 0) + 1

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
    digest = (
        hashlib.sha256("".join(raw_hashes).encode("utf-8")).hexdigest()
        if raw_hashes
        else None
    )
    (out / "raw_manifest.json").write_text(
        json.dumps(
            {"aggregate_sha256": digest, "responses": client.request_log},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = {
        "status": "ready" if not avatars.empty else "no_eligible_avatars",
        "project_version": "0.4.0",
        "competition": spec.competition_name,
        "league_id": spec.league_id,
        "season": spec.season,
        "generated_at_utc": generated_at,
        "data_cutoff_utc": cutoff_utc or generated_at,
        "completed_matches_included": len(fixtures),
        "player_match_rows_included": len(player_matches),
        "precise_start_role_observations": precise_start_role_observations,
        "recovered_entries_via_primary_role": recovered_entries,
        "reassigned_secondary_start_entries": reassigned_entries,
        "excluded_entries_without_stable_role": excluded_entries,
        "players_with_stable_primary_role": len(primary_roles),
        "players_excluded_for_ambiguous_role": ambiguous_players,
        "minimum_primary_role_share": 0.60,
        "position_classification_counts": classification_counts,
        "requested_top_n": spec.requested_top_n,
        "minimum_minutes": spec.minimum_minutes,
        "reliability_prior_minutes": spec.reliability_prior_minutes,
        "trim_fraction": spec.trim_fraction,
        "source": "API-FOOTBALL / API-SPORTS",
        "provider_responses_hashed": len(raw_hashes),
        "raw_snapshot_digest_sha256": digest,
        "scope_claim": (
            "Mejor significa mayor puntuacion dentro de la misma posicion, en este "
            "corte acumulado de la Copa 2026 y bajo el indice pre-registrado."
        ),
        "studies": [
            "Estudio 1: avatar Top-20 vs mejor jugador real por posicion",
            "Estudio 2: Synthetic XI vs Real Best XI, ambos con once integrantes",
        ],
        "xi_slots": XI_SLOTS,
    }
    methods = {
        "idioma": "espanol",
        "especificacion": spec.__dict__,
        "metricas_por_posicion": POSITION_METRICS,
        "inferencia_de_rol": (
            "Rol primario unico por jugador a partir de minutos de titular con rol "
            "preciso. Se exige al menos 60% en la misma funcion; despues se incorporan "
            "sus apariciones como suplente bajo ese rol estable."
        ),
        "precision_de_pase": (
            "passes.accuracy se normaliza como numero de pases acertados y la tasa "
            "se calcula como 100 por pases acertados dividido entre pases totales."
        ),
        "ranking": (
            "Media de z-scores winsorizados, con direccion corregida y retraccion "
            "por minutos hacia la media de la posicion."
        ),
        "mejor_jugador_real": (
            "Numero 1 del indice posicional despues del ajuste por confiabilidad."
        ),
        "avatar": (
            "Media recortada al 10% de los Top-20 elegibles de cada posicion; "
            "Top-10 y Top-30 quedan como analisis de sensibilidad."
        ),
        "incertidumbre": (
            "Intervalo bootstrap no parametrico de 95% con semilla determinista."
        ),
        "once_experimental": (
            "4-3-3 funcional: 1 GK, 2 CB, 2 FB, 1 DM, 1 CM, 1 AM, 2 W y 1 ST."
        ),
        "limitaciones": [
            "El torneo esta en curso; todo resultado corresponde a un corte fechado.",
            "Jugadores sin rol primario estable o sin titularidad clasificable se excluyen.",
            "Las estadisticas agregadas no observan por completo la inteligencia sin balon.",
            "El Estudio 2 no afirmara causalidad fisica hasta validar el motor de simulacion.",
        ],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "methods.json").write_text(
        json.dumps(methods, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {**frames, "manifest": manifest, "methods": methods}
