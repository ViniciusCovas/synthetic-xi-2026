"""Canonical runtime wrappers that enforce all explicitly frozen real values.

The roster freeze contains a subset of profile dimensions reviewed for each real
player.  Those values take precedence over auxiliary feature reconstruction.
Dimensions not present in the freeze remain sourced from the audited feature
frame.  The historical profile builders are preserved unchanged.
"""
from __future__ import annotations

from dataclasses import replace
import json
from typing import Any

from .engine import PlayerProfile, TeamProfile
from .official_profiles import (
    ROSTER_PATH,
    OfficialTeamBundle,
    build_official_bundles as _build_official_bundles,
)
from .official_profile_sensitivity import (
    RoleVariant,
    build_official_bundles_with_role_variant as _build_with_role_variant,
)

FROZEN_PROFILE_METRICS = (
    "overall",
    "uncertainty",
    "finishing",
    "creation",
    "goalkeeping",
)


def _real_entries() -> dict[str, dict[str, Any]]:
    payload = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    real = payload["teams"]["real_best_xi"]
    entries = list(real.get("starters", [])) + list(real.get("bench", []))
    return {str(entry["player_id"]): entry for entry in entries}


def _patch_profile(
    profile: PlayerProfile,
    entries: dict[str, dict[str, Any]],
) -> PlayerProfile:
    entry = entries.get(str(profile.player_id))
    if entry is None:
        raise RuntimeError(
            f"Real runtime profile {profile.player_id} is absent from the frozen roster"
        )
    overrides = {
        metric: float(entry[metric])
        for metric in FROZEN_PROFILE_METRICS
        if metric in entry and entry[metric] is not None
    }
    return replace(
        profile,
        name=str(entry.get("name") or profile.name),
        synthetic=False,
        **overrides,
    )


def enforce_frozen_real_values(bundle: OfficialTeamBundle) -> OfficialTeamBundle:
    entries = _real_entries()
    team = TeamProfile(
        name=bundle.team.name,
        players=tuple(_patch_profile(player, entries) for player in bundle.team.players),
        tempo=bundle.team.tempo,
        press=bundle.team.press,
        directness=bundle.team.directness,
    )
    bench_by_role = {
        role: tuple(_patch_profile(player, entries) for player in players)
        for role, players in bundle.bench_by_role.items()
    }
    runtime_ids = {
        player.player_id for player in team.players
    } | {
        player.player_id
        for players in bench_by_role.values()
        for player in players
    }
    if runtime_ids != set(bundle.registered_ids):
        missing = set(bundle.registered_ids) - runtime_ids
        extra = runtime_ids - set(bundle.registered_ids)
        raise RuntimeError(
            f"Frozen real runtime mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )
    return replace(bundle, team=team, bench_by_role=bench_by_role)


def build_official_bundles(
    top_n: int | None = None,
    minimum_minutes: int | None = None,
) -> tuple[OfficialTeamBundle, OfficialTeamBundle]:
    synthetic, real = _build_official_bundles(
        top_n=top_n,
        minimum_minutes=minimum_minutes,
    )
    return synthetic, enforce_frozen_real_values(real)


def build_official_bundles_with_role_variant(
    role_variant: RoleVariant,
    top_n: int | None = None,
    minimum_minutes: int | None = None,
) -> tuple[OfficialTeamBundle, OfficialTeamBundle]:
    synthetic, real = _build_with_role_variant(
        role_variant,
        top_n=top_n,
        minimum_minutes=minimum_minutes,
    )
    return synthetic, enforce_frozen_real_values(real)


def frozen_profile_mismatches(bundle: OfficialTeamBundle) -> list[dict[str, Any]]:
    entries = _real_entries()
    runtime: dict[str, PlayerProfile] = {
        player.player_id: player for player in bundle.team.players
    }
    for players in bundle.bench_by_role.values():
        for player in players:
            runtime.setdefault(player.player_id, player)
    mismatches: list[dict[str, Any]] = []
    for player_id, entry in entries.items():
        profile = runtime.get(player_id)
        if profile is None:
            mismatches.append(
                {"player_id": player_id, "metric": "profile", "reason": "missing"}
            )
            continue
        for metric in FROZEN_PROFILE_METRICS:
            if metric not in entry or entry[metric] is None:
                continue
            runtime_value = float(getattr(profile, metric))
            frozen_value = float(entry[metric])
            if abs(runtime_value - frozen_value) > 1e-12:
                mismatches.append(
                    {
                        "player_id": player_id,
                        "metric": metric,
                        "runtime": runtime_value,
                        "frozen": frozen_value,
                    }
                )
    return mismatches
