"""Alternative outcome-blind role classifications for official robustness runs."""
from __future__ import annotations

from typing import Literal

from .official_profiles import (
    ROSTER_PATH,
    OfficialTeamBundle,
    _build_team_bundle,
    _config,
    _feature_frame,
    _read_json,
    _synthetic_archetypes,
    build_official_bundles,
)
from .profiles import load_feature_table

RoleVariant = Literal["cohort_relative", "provider_grid"]


def build_official_bundles_with_role_variant(
    role_variant: RoleVariant,
    top_n: int | None = None,
    minimum_minutes: int | None = None,
) -> tuple[OfficialTeamBundle, OfficialTeamBundle]:
    """Build exact frozen rosters under one of two pre-result role ontologies.

    ``cohort_relative`` is the official primary mapping from ``profiles_v2``.
    ``provider_grid`` uses the transparent grid/provider rule already implemented
    in ``profiles.load_feature_table``.  Only synthetic archetype membership can
    change; frozen real-player identities remain fixed.
    """
    if role_variant == "cohort_relative":
        return build_official_bundles(top_n=top_n, minimum_minutes=minimum_minutes)
    if role_variant != "provider_grid":
        raise ValueError(f"Unknown role_variant: {role_variant}")

    config = _config()
    analysis = config["analysis"]
    top_n = int(top_n if top_n is not None else analysis["top_n_primary"])
    minimum_minutes = int(
        minimum_minutes if minimum_minutes is not None else analysis["minutes_primary"]
    )
    roster = _read_json(ROSTER_PATH)
    teams = roster["teams"]
    frame = load_feature_table().copy()
    frame["player_id_key"] = frame["player_id"].astype(str)
    frame = frame.loc[frame["minutes_num"] >= float(minimum_minutes)].copy()
    if frame.empty:
        raise RuntimeError("Provider-grid role sensitivity produced no eligible players")
    frame_by_id = {
        str(row["player_id"]): row
        for _, row in frame.sort_values(["player_id_key", "minutes_num"], ascending=[True, False])
        .drop_duplicates("player_id_key")
        .iterrows()
    }
    archetypes, membership = _synthetic_archetypes(frame, top_n)
    for row in membership:
        row["role_variant"] = "provider_grid"
    synthetic = _build_team_bundle(
        teams["synthetic_xi"], True, frame_by_id, archetypes, membership
    )
    real = _build_team_bundle(
        teams["real_best_xi"], False, frame_by_id, archetypes, membership
    )
    return synthetic, real
