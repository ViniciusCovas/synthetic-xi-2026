"""Canonical runtime wrappers for official_experiment_v1.

The roster freeze contains reviewed real-player dimensions that take precedence
over auxiliary reconstruction.  This module also defines the preregistered
emergency substitution policy used only when all unused exact-role reserves are
exhausted: another unused member of the frozen 26-player squad may cover a
compatible role with an explicit ability penalty and increased uncertainty.
"""
from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, Iterable

from .engine import PlayerProfile, TeamProfile
from .official_profiles import (
    ROSTER_PATH,
    OfficialTeamBundle,
    build_official_bundles as _build_official_bundles,
    compatible_reserves as _exact_compatible_reserves,
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
OUT_OF_ROLE_ABILITY_MULTIPLIER = 0.90
OUT_OF_ROLE_UNCERTAINTY_INCREMENT = 0.03
EMERGENCY_ROLE_PREFERENCE: dict[str, tuple[str, ...]] = {
    "GK": (),
    "CB1": ("CB2", "FB1", "FB2", "DM"),
    "CB2": ("CB1", "FB2", "FB1", "DM"),
    "FB1": ("FB2", "W1", "CB1", "DM", "CM"),
    "FB2": ("FB1", "W2", "CB2", "DM", "CM"),
    "DM": ("CM", "CB1", "CB2", "AM", "FB1", "FB2"),
    "CM": ("DM", "AM", "W1", "W2", "FB1", "FB2"),
    "AM": ("CM", "W1", "W2", "ST", "DM"),
    "W1": ("W2", "AM", "ST", "FB1", "CM"),
    "W2": ("W1", "AM", "ST", "FB2", "CM"),
    "ST": ("W1", "W2", "AM", "CM"),
}
ABILITY_FIELDS = (
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
    runtime_ids = {player.player_id for player in team.players} | {
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


def _penalize_out_of_role(profile: PlayerProfile, target_role: str) -> PlayerProfile:
    overrides = {
        field: max(0.0, min(1.0, float(getattr(profile, field)) * OUT_OF_ROLE_ABILITY_MULTIPLIER))
        for field in ABILITY_FIELDS
    }
    return replace(
        profile,
        role=target_role,
        uncertainty=min(
            0.30,
            float(profile.uncertainty) + OUT_OF_ROLE_UNCERTAINTY_INCREMENT,
        ),
        **overrides,
    )


def compatible_reserves(
    bundle: OfficialTeamBundle,
    role: str,
    used_ids: Iterable[str],
) -> list[PlayerProfile]:
    """Return exact reserves, then deterministic emergency frozen-squad cover.

    Emergency cover never creates a new identity and never reuses a player.  It
    is unavailable for goalkeeper because each frozen squad already contains the
    required emergency goalkeeper order.
    """
    exact = _exact_compatible_reserves(bundle, role, used_ids)
    if exact:
        return exact
    if role == "GK":
        return []

    used = {str(value) for value in used_ids}
    seen: set[str] = set()
    candidates: list[tuple[int, float, PlayerProfile]] = []
    preferences = EMERGENCY_ROLE_PREFERENCE.get(role, ())
    for preference_rank, source_role in enumerate(preferences):
        for profile in bundle.bench_by_role.get(source_role, ()):
            player_id = str(profile.player_id)
            if player_id in used or player_id in seen:
                continue
            seen.add(player_id)
            conservative = float(profile.overall) - float(profile.uncertainty)
            candidates.append(
                (
                    preference_rank,
                    -conservative,
                    _penalize_out_of_role(profile, role),
                )
            )
    candidates.sort(key=lambda item: (item[0], item[1], item[2].player_id))
    return [item[2] for item in candidates]
