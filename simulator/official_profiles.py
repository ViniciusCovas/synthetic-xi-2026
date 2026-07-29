"""Canonical profile and roster loader for the official_v1 experiment.

This module is intentionally separate from ``profiles_v2``.  It consumes the
frozen 26-player rosters, enforces exact starter identities and constructs the
Synthetic XI archetypes only from players meeting the declared minutes rule.
No output produced here is provisional or labelled exploratory.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile
from .profiles import _to_profile, load_feature_table
from .profiles_v2 import resolve_exploratory_roles

CONFIG_PATH = Path("config/official_experiment_v1.json")
ROSTER_PATH = Path("data/model_readiness/complete_final_rosters_v1.json")

CANONICAL_TO_ENGINE = {
    "GK": "GK",
    "RB": "FB1",
    "RCB": "CB1",
    "LCB": "CB2",
    "LB": "FB2",
    "DM": "DM",
    "CM": "CM",
    "AM": "AM",
    "RW": "W1",
    "LW": "W2",
    "ST": "ST",
}
ENGINE_TO_ARCHETYPE = {
    "GK": "GK",
    "CB1": "CB",
    "CB2": "CB",
    "FB1": "FB",
    "FB2": "FB",
    "DM": "DM",
    "CM": "CM",
    "AM": "AM",
    "W1": "W",
    "W2": "W",
    "ST": "ST",
}
BROAD_COMPATIBILITY = {
    "GK": ("GK",),
    "RB": ("FB1",),
    "LB": ("FB2",),
    "FB": ("FB1", "FB2"),
    "RCB": ("CB1",),
    "LCB": ("CB2",),
    "CB": ("CB1", "CB2"),
    "DM": ("DM",),
    "CM": ("CM",),
    "AM": ("AM",),
    "RW": ("W1",),
    "LW": ("W2",),
    "W": ("W1", "W2"),
    "ST": ("ST",),
}
PROFILE_COLUMNS = (
    "overall",
    "build_up",
    "progression",
    "creation",
    "finishing",
    "defending",
    "duels",
    "retention",
    "goalkeeping",
)


@dataclass(frozen=True)
class OfficialTeamBundle:
    team: TeamProfile
    bench_by_role: dict[str, tuple[PlayerProfile, ...]]
    registered_ids: tuple[str, ...]
    starter_ids: tuple[str, ...]
    penalty_order_ids: tuple[str, ...]
    emergency_goalkeeper_ids: tuple[str, ...]
    roster_rows: tuple[dict[str, Any], ...]
    membership_rows: tuple[dict[str, Any], ...]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _config() -> dict[str, Any]:
    return _read_json(CONFIG_PATH)


def _canonical_role(entry: dict[str, Any]) -> str:
    role = str(entry.get("resolved_role") or entry.get("squad_role") or "")
    role = role.split("_reserve", 1)[0].split("_utility", 1)[0]
    if role not in BROAD_COMPATIBILITY:
        raise ValueError(f"Unsupported canonical roster role: {role!r}")
    return role


def _feature_frame(minimum_minutes: int) -> pd.DataFrame:
    frame = resolve_exploratory_roles(load_feature_table()).copy()
    frame["player_id_key"] = frame["player_id"].astype(str)
    frame["minutes_num"] = pd.to_numeric(frame["minutes_num"], errors="coerce").fillna(0.0)
    eligible = frame.loc[frame["minutes_num"] >= float(minimum_minutes)].copy()
    if eligible.empty:
        raise RuntimeError("No players satisfy the official minimum-minutes rule")
    return eligible


def _trimmed_profile(members: pd.DataFrame, engine_role: str, synthetic_id: str, name: str) -> PlayerProfile:
    if members.empty:
        raise RuntimeError(f"No eligible members for synthetic role {engine_role}")
    values: dict[str, float] = {}
    for column in PROFILE_COLUMNS:
        ordered = pd.to_numeric(members[column], errors="coerce").dropna().sort_values()
        if ordered.empty:
            raise RuntimeError(f"Synthetic role {engine_role} has no values for {column}")
        trim = int(len(ordered) * 0.10)
        selected = ordered.iloc[trim : len(ordered) - trim] if trim and len(ordered) > 2 * trim else ordered
        values[column] = float(selected.mean())
    uncertainty = float(max(0.025, members["uncertainty"].mean() / np.sqrt(len(members))))
    return PlayerProfile(
        player_id=synthetic_id,
        name=name,
        role=engine_role,
        minutes=float(members["minutes_num"].median()),
        uncertainty=uncertainty,
        synthetic=True,
        **values,
    )


def _synthetic_archetypes(frame: pd.DataFrame, top_n: int) -> tuple[dict[str, PlayerProfile], list[dict[str, Any]]]:
    archetypes: dict[str, PlayerProfile] = {}
    membership: list[dict[str, Any]] = []
    for engine_role in ROLE_ORDER:
        broad = ENGINE_TO_ARCHETYPE[engine_role]
        candidates = frame.loc[frame["exploratory_role"].eq(broad)].sort_values(
            ["conservative_score", "minutes_num", "player_id_key"],
            ascending=[False, False, True],
        )
        if candidates.empty:
            raise RuntimeError(f"Official role universe is empty for {broad}")
        members = candidates.head(min(int(top_n), len(candidates))).copy()
        profile = _trimmed_profile(
            members,
            engine_role,
            synthetic_id=f"OFFICIAL-ARCHETYPE-{engine_role}-TOP{top_n}",
            name=f"Official {engine_role} archetype Top {len(members)}",
        )
        archetypes[engine_role] = profile
        for rank, row in enumerate(members.itertuples(index=False), start=1):
            membership.append(
                {
                    "engine_role": engine_role,
                    "archetype": broad,
                    "rank": rank,
                    "player_id": str(row.player_id),
                    "player_name": str(row.player_name),
                    "minutes": float(row.minutes_num),
                    "top_n_requested": int(top_n),
                    "top_n_real": int(len(members)),
                    "minimum_minutes": float(frame["minutes_num"].min()),
                }
            )
    return archetypes, membership


def _clone_synthetic(entry: dict[str, Any], engine_role: str, base: PlayerProfile) -> PlayerProfile:
    return replace(
        base,
        player_id=str(entry["player_id"]),
        name=str(entry["name"]),
        role=engine_role,
        synthetic=True,
    )


def _real_profile(entry: dict[str, Any], engine_role: str, frame_by_id: dict[str, pd.Series]) -> PlayerProfile:
    key = str(entry["player_id"])
    if key not in frame_by_id:
        raise RuntimeError(
            f"Frozen real player {key} ({entry.get('name')}) is absent from the official eligible feature frame"
        )
    profile = _to_profile(frame_by_id[key], engine_role)
    return replace(
        profile,
        player_id=key,
        name=str(entry.get("name") or profile.name),
        role=engine_role,
        synthetic=False,
    )


def _compatible_engine_roles(entry: dict[str, Any]) -> tuple[str, ...]:
    return BROAD_COMPATIBILITY[_canonical_role(entry)]


def _validate_roster(team_payload: dict[str, Any], label: str) -> None:
    registered = list(team_payload.get("registered_squad", []))
    starters = list(team_payload.get("starters", []))
    bench = list(team_payload.get("bench", []))
    ids = [str(row.get("player_id")) for row in registered]
    starter_ids = [str(row.get("player_id")) for row in starters]
    if len(registered) != 26 or len(ids) != len(set(ids)):
        raise RuntimeError(f"{label}: registered squad must contain 26 unique IDs")
    if len(starters) != 11 or len(starter_ids) != len(set(starter_ids)):
        raise RuntimeError(f"{label}: starters must contain 11 unique IDs")
    if set(starter_ids) | {str(row.get('player_id')) for row in bench} != set(ids):
        raise RuntimeError(f"{label}: starters plus bench do not equal the registered squad")
    canonical_roles = {_canonical_role(row) for row in starters}
    required = set(CANONICAL_TO_ENGINE)
    if canonical_roles != required:
        raise RuntimeError(f"{label}: starter roles differ from canonical roles: {canonical_roles ^ required}")


def _build_team_bundle(
    team_payload: dict[str, Any],
    synthetic: bool,
    frame_by_id: dict[str, pd.Series],
    archetypes: dict[str, PlayerProfile],
    membership_rows: list[dict[str, Any]],
) -> OfficialTeamBundle:
    label = str(team_payload.get("team"))
    _validate_roster(team_payload, label)
    starters: list[PlayerProfile] = []
    roster_rows: list[dict[str, Any]] = []

    for entry in team_payload["starters"]:
        canonical = _canonical_role(entry)
        engine_role = CANONICAL_TO_ENGINE[canonical]
        profile = (
            _clone_synthetic(entry, engine_role, archetypes[engine_role])
            if synthetic
            else _real_profile(entry, engine_role, frame_by_id)
        )
        starters.append(profile)
        roster_rows.append(
            {
                **entry,
                "canonical_role": canonical,
                "engine_role": engine_role,
                "runtime_name": profile.name,
                "runtime_player_id": profile.player_id,
                "runtime_provisional": False,
            }
        )

    starters = sorted(starters, key=lambda p: ROLE_ORDER.index(p.role))
    team = TeamProfile(name=label, players=tuple(starters))

    bench_by_role_lists: dict[str, list[PlayerProfile]] = {role: [] for role in ROLE_ORDER}
    for entry in team_payload["bench"]:
        compatible = _compatible_engine_roles(entry)
        for engine_role in compatible:
            profile = (
                _clone_synthetic(entry, engine_role, archetypes[engine_role])
                if synthetic
                else _real_profile(entry, engine_role, frame_by_id)
            )
            bench_by_role_lists[engine_role].append(profile)
        roster_rows.append(
            {
                **entry,
                "canonical_role": _canonical_role(entry),
                "compatible_engine_roles": list(compatible),
                "runtime_provisional": False,
            }
        )

    for role, values in bench_by_role_lists.items():
        values.sort(key=lambda p: (p.overall - p.uncertainty, p.minutes, p.player_id), reverse=True)

    return OfficialTeamBundle(
        team=team,
        bench_by_role={key: tuple(value) for key, value in bench_by_role_lists.items()},
        registered_ids=tuple(str(row["player_id"]) for row in team_payload["registered_squad"]),
        starter_ids=tuple(str(row["player_id"]) for row in team_payload["starters"]),
        penalty_order_ids=tuple(str(value) for value in team_payload.get("penalty_order_player_ids", [])),
        emergency_goalkeeper_ids=tuple(
            str(value) for value in team_payload.get("emergency_goalkeeper_order_player_ids", [])
        ),
        roster_rows=tuple(roster_rows),
        membership_rows=tuple(membership_rows if synthetic else []),
    )


def build_official_bundles(
    top_n: int | None = None,
    minimum_minutes: int | None = None,
) -> tuple[OfficialTeamBundle, OfficialTeamBundle]:
    config = _config()
    analysis = config["analysis"]
    top_n = int(top_n if top_n is not None else analysis["top_n_primary"])
    minimum_minutes = int(
        minimum_minutes if minimum_minutes is not None else analysis["minutes_primary"]
    )
    if top_n < 1 or minimum_minutes < 1:
        raise ValueError("top_n and minimum_minutes must be positive")

    roster = _read_json(ROSTER_PATH)
    teams = roster.get("teams", {})
    if set(teams) != {"synthetic_xi", "real_best_xi"}:
        raise RuntimeError("Frozen roster file must contain synthetic_xi and real_best_xi")

    frame = _feature_frame(minimum_minutes)
    frame_by_id = {
        str(row["player_id"]): row
        for _, row in frame.sort_values(["player_id_key", "minutes_num"], ascending=[True, False])
        .drop_duplicates("player_id_key")
        .iterrows()
    }
    archetypes, membership = _synthetic_archetypes(frame, top_n)
    synthetic = _build_team_bundle(
        teams["synthetic_xi"], True, frame_by_id, archetypes, membership
    )
    real = _build_team_bundle(
        teams["real_best_xi"], False, frame_by_id, archetypes, membership
    )

    if "exploratorio" in synthetic.team.name.lower() or "exploratorio" in real.team.name.lower():
        raise RuntimeError("Official team names cannot contain exploratory labels")
    overlap = set(real.starter_ids) & set(synthetic.starter_ids)
    if overlap:
        raise RuntimeError(f"Synthetic and real runtime IDs unexpectedly overlap: {sorted(overlap)}")
    return synthetic, real


def team_rows(bundle: OfficialTeamBundle) -> list[dict[str, Any]]:
    return [
        {
            "player_id": player.player_id,
            "name": player.name,
            "role": player.role,
            "minutes": player.minutes,
            "overall": player.overall,
            "build_up": player.build_up,
            "progression": player.progression,
            "creation": player.creation,
            "finishing": player.finishing,
            "defending": player.defending,
            "duels": player.duels,
            "retention": player.retention,
            "goalkeeping": player.goalkeeping,
            "uncertainty": player.uncertainty,
            "synthetic": player.synthetic,
            "provisional": False,
        }
        for player in bundle.team.players
    ]


def bench_rows(bundle: OfficialTeamBundle) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for role, profiles in bundle.bench_by_role.items():
        for profile in profiles:
            key = (profile.player_id, role)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "player_id": profile.player_id,
                    "name": profile.name,
                    "compatible_engine_role": role,
                    "overall": profile.overall,
                    "uncertainty": profile.uncertainty,
                    "synthetic": profile.synthetic,
                    "provisional": False,
                }
            )
    return rows


def registered_id_set(bundle: OfficialTeamBundle) -> set[str]:
    return set(bundle.registered_ids)


def compatible_reserves(bundle: OfficialTeamBundle, role: str, used_ids: Iterable[str]) -> list[PlayerProfile]:
    used = {str(value) for value in used_ids}
    return [profile for profile in bundle.bench_by_role.get(role, ()) if profile.player_id not in used]
