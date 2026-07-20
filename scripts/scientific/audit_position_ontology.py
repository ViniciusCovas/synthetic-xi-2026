#!/usr/bin/env python3
"""Formation-aware, minute-weighted and publicly anchored position audit.

This is an audit pipeline. It never overwrites the frozen candidate release and never
calls a provider API. It reconstructs starting roles from durable line-up/player caches,
checks the highest-impact players against versioned public sources, recalculates scores
under the audited role, and decides whether a new simulation is scientifically allowed.
"""
from __future__ import annotations

import glob
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODEL = Path("data/model_readiness")
AUDIT = Path("data/audits/position_ontology_v2")
ANCHORS = Path("data/reference/public_role_anchors_2026.csv")
PERFORMANCE = Path("data/reference/public_performance_checks_2026.csv")
CURRENT_ROLES = MODEL / "eleven_role_evidence.csv"
FRONTIER = MODEL / "selection_frontier_all_candidates.csv"
COVERAGE = Path("data/audits/scope_correct_coverage/player_window_coverage_scope_correct.csv")
SYNTHETIC_MEMBERS = Path("data/simulations/identified_set_v1/synthetic_avatar_membership.csv")
REAL_MEMBERS = Path("data/simulations/identified_set_v1/real_identified_set_membership.csv")

ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
BROAD = {
    "GK": "GK", "RB": "FB", "LB": "FB", "RCB": "CB", "LCB": "CB",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W", "ST": "ST",
}
WEIGHTS: dict[str, dict[str, float]] = {
    "GK": {"goalkeeping": .55, "build_up": .20, "retention": .15, "base": .10},
    "CB": {"defending": .33, "duels": .25, "build_up": .22, "retention": .20},
    "FB": {"defending": .22, "duels": .14, "build_up": .18, "progression": .28, "creation": .18},
    "DM": {"defending": .25, "duels": .18, "build_up": .25, "retention": .20, "progression": .12},
    "CM": {"build_up": .23, "retention": .20, "progression": .20, "creation": .16, "defending": .12, "duels": .09},
    "AM": {"creation": .32, "progression": .24, "finishing": .17, "retention": .15, "build_up": .12},
    "W": {"progression": .29, "creation": .23, "finishing": .22, "retention": .14, "duels": .12},
    "ST": {"finishing": .44, "creation": .12, "progression": .12, "duels": .18, "retention": .14},
}
DIMENSIONS = ["build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]

# Ordered from the provider's low grid column (validated as left) to high (right).
FORMATION_TEMPLATES: dict[str, list[list[str]]] = {
    "4-3-3": [["LB", "LCB", "RCB", "RB"], ["CM", "DM", "CM"], ["LW", "ST", "RW"]],
    "4-2-3-1": [["LB", "LCB", "RCB", "RB"], ["DM", "DM"], ["LW", "AM", "RW"], ["ST"]],
    "4-1-4-1": [["LB", "LCB", "RCB", "RB"], ["DM"], ["LW", "CM", "CM", "RW"], ["ST"]],
    "4-4-2": [["LB", "LCB", "RCB", "RB"], ["LW", "CM", "CM", "RW"], ["ST", "ST"]],
    "4-3-1-2": [["LB", "LCB", "RCB", "RB"], ["CM", "DM", "CM"], ["AM"], ["ST", "ST"]],
    "4-2-2-2": [["LB", "LCB", "RCB", "RB"], ["DM", "DM"], ["AM", "AM"], ["ST", "ST"]],
    "4-2-4": [["LB", "LCB", "RCB", "RB"], ["DM", "CM"], ["LW", "ST", "ST", "RW"]],
    "4-1-2-3": [["LB", "LCB", "RCB", "RB"], ["DM"], ["CM", "CM"], ["LW", "ST", "RW"]],
    "3-5-2": [["LCB", "CB", "RCB"], ["LB", "CM", "DM", "CM", "RB"], ["ST", "ST"]],
    "3-4-2-1": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["AM", "AM"], ["ST"]],
    "3-4-1-2": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["AM"], ["ST", "ST"]],
    "3-4-3": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["LW", "ST", "RW"]],
    "5-3-2": [["LB", "LCB", "CB", "RCB", "RB"], ["CM", "DM", "CM"], ["ST", "ST"]],
    "5-4-1": [["LB", "LCB", "CB", "RCB", "RB"], ["LW", "CM", "CM", "RW"], ["ST"]],
    "4-5-1": [["LB", "LCB", "RCB", "RB"], ["LW", "CM", "DM", "CM", "RW"], ["ST"]],
}


def numeric(frame: pd.DataFrame, names: list[str], default: float = np.nan) -> pd.Series:
    for name in names:
        if name in frame:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def text(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name].astype("string")
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def read_many(patterns: list[str], columns: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    paths = sorted({path for pattern in patterns for path in glob.glob(pattern)})
    for path in paths:
        try:
            frame = pd.read_csv(path, low_memory=False, usecols=lambda c: c in columns)
        except Exception:
            continue
        if not frame.empty:
            frame["_source_file"] = path
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_grid(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    left, right = value.split(":", 1)
    try:
        return int(float(left)), int(float(right))
    except ValueError:
        return None, None


def normalize_formation(value: object) -> str:
    return str(value or "").strip().replace(" ", "")


def generic_line_roles(parts: list[int], line_index: int, count: int) -> list[str]:
    last = line_index == len(parts) - 1
    first = line_index == 0
    if first:
        if count == 5:
            return ["LB", "LCB", "CB", "RCB", "RB"]
        if count == 4:
            return ["LB", "LCB", "RCB", "RB"]
        if count == 3:
            return ["LCB", "CB", "RCB"]
        if count == 2:
            return ["LCB", "RCB"]
    if last:
        if count == 1:
            return ["ST"]
        if count == 2:
            return ["ST", "ST"]
        if count == 3:
            return ["LW", "ST", "RW"]
        if count == 4:
            return ["LW", "ST", "ST", "RW"]
    if line_index == 1 and parts and parts[0] == 3 and count >= 4:
        if count == 4:
            return ["LB", "CM", "CM", "RB"]
        if count == 5:
            return ["LB", "CM", "DM", "CM", "RB"]
    if count == 1:
        return ["DM" if line_index == 1 else "AM"]
    if count == 2:
        return ["DM", "DM"] if line_index == 1 else ["AM", "AM"]
    if count == 3:
        if line_index == len(parts) - 2 and parts[-1] == 1:
            return ["LW", "AM", "RW"]
        return ["CM", "DM", "CM"]
    if count == 4:
        return ["LW", "CM", "CM", "RW"]
    if count == 5:
        return ["LB", "CM", "DM", "CM", "RB"]
    return ["UNRESOLVED"] * count


def line_roles(formation: str, line_index: int, count: int) -> tuple[list[str], str]:
    template = FORMATION_TEMPLATES.get(formation)
    if template and line_index < len(template) and len(template[line_index]) == count:
        return template[line_index], "formation_template"
    try:
        parts = [int(part) for part in formation.split("-") if part]
    except ValueError:
        parts = []
    return generic_line_roles(parts, line_index, count), "formation_generic"


def reconstruct_roles() -> tuple[pd.DataFrame, dict[str, Any]]:
    lineup_columns = {
        "fixture_id", "team_id", "player_id", "player_name", "formation", "grid",
        "lineup_source", "lineup_position", "position", "pos",
    }
    player_columns = {
        "fixture_id", "team_id", "player_id", "player_name", "minutes", "minutes_num",
        "provider_position", "position", "pos", "substitute",
    }
    lineups = read_many([
        "data/lake/batches/*_lineups.csv*",
        "data/audits/fixture_detail_pilot_lineups.csv",
    ], lineup_columns)
    players = read_many([
        "data/lake/batches/*_players.csv*",
        "data/audits/fixture_detail_pilot_players.csv",
    ], player_columns)
    if lineups.empty:
        return pd.DataFrame(), {"lineup_rows": 0, "player_rows": int(len(players))}

    lineups["fixture_id"] = numeric(lineups, ["fixture_id"])
    lineups["team_id"] = numeric(lineups, ["team_id"])
    lineups["player_id"] = numeric(lineups, ["player_id"])
    lineups = lineups.dropna(subset=["fixture_id", "team_id", "player_id"]).copy()
    for column in ["fixture_id", "team_id", "player_id"]:
        lineups[column] = lineups[column].astype(int)
    source = text(lineups, ["lineup_source"])
    lineups = lineups.loc[source.fillna("").str.lower().eq("startxi")].copy()
    lineups = lineups.drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
    lineups["formation"] = text(lineups, ["formation"]).map(normalize_formation)
    parsed = text(lineups, ["grid"]).apply(parse_grid)
    lineups["grid_row"] = parsed.apply(lambda item: item[0])
    lineups["grid_col"] = parsed.apply(lambda item: item[1])
    lineups = lineups.dropna(subset=["grid_row", "grid_col"]).copy()
    lineups[["grid_row", "grid_col"]] = lineups[["grid_row", "grid_col"]].astype(int)

    if not players.empty:
        players["fixture_id"] = numeric(players, ["fixture_id"])
        players["team_id"] = numeric(players, ["team_id"])
        players["player_id"] = numeric(players, ["player_id"])
        players["minutes_observed"] = numeric(players, ["minutes", "minutes_num"], 0.0).fillna(0.0)
        players = players.dropna(subset=["fixture_id", "team_id", "player_id"]).copy()
        for column in ["fixture_id", "team_id", "player_id"]:
            players[column] = players[column].astype(int)
        players = players.sort_values("minutes_observed").drop_duplicates(
            ["fixture_id", "team_id", "player_id"], keep="last"
        )
        lineups = lineups.merge(
            players[["fixture_id", "team_id", "player_id", "minutes_observed"]],
            on=["fixture_id", "team_id", "player_id"], how="left",
        )
    else:
        lineups["minutes_observed"] = np.nan

    records: list[dict[str, Any]] = []
    for (fixture_id, team_id), team in lineups.groupby(["fixture_id", "team_id"], sort=False):
        formation = str(team["formation"].dropna().iloc[0]) if team["formation"].notna().any() else ""
        rows = sorted(team["grid_row"].unique())
        outfield_rows = [row for row in rows if row != 1]
        row_to_line = {row: index for index, row in enumerate(outfield_rows)}
        for row_value, row_group in team.groupby("grid_row", sort=True):
            ordered = row_group.sort_values("grid_col")
            if row_value == 1:
                role_list, method = ["GK"] * len(ordered), "goalkeeper_grid_row"
            else:
                role_list, method = line_roles(formation, row_to_line[row_value], len(ordered))
            for role, item in zip(role_list, ordered.itertuples(index=False)):
                records.append({
                    "fixture_id": int(fixture_id),
                    "team_id": int(team_id),
                    "player_id": int(item.player_id),
                    "player_name": getattr(item, "player_name", None),
                    "formation": formation,
                    "grid_row": int(item.grid_row),
                    "grid_col": int(item.grid_col),
                    "formation_role": role,
                    "role_method": method,
                    "minutes_observed": float(item.minutes_observed) if pd.notna(item.minutes_observed) else np.nan,
                })
    evidence = pd.DataFrame(records)
    diagnostics = {
        "lineup_rows": int(len(lineups)),
        "player_rows": int(len(players)),
        "precise_role_rows": int(len(evidence)),
        "fixtures": int(evidence.fixture_id.nunique()) if not evidence.empty else 0,
        "formations": evidence.formation.value_counts().head(20).to_dict() if not evidence.empty else {},
        "unresolved_role_rows": int(evidence.formation_role.isin(["CB", "UNRESOLVED"]).sum()) if not evidence.empty else 0,
        "rows_with_observed_minutes": int(evidence.minutes_observed.notna().sum()) if not evidence.empty else 0,
    }
    return evidence, diagnostics


def aggregate_role_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["player_id", "formation_primary_role"])
    usable = evidence.loc[evidence.formation_role.isin(ROLES)].copy()
    usable["role_weight"] = usable["minutes_observed"].fillna(0.0)
    # Observations without minutes remain visible but do not receive fabricated minutes.
    minutes = usable.groupby(["player_id", "formation_role"], as_index=False).agg(
        role_minutes=("role_weight", "sum"),
        role_observations=("fixture_id", "nunique"),
    )
    names = evidence.sort_values("minutes_observed", ascending=False).drop_duplicates("player_id")[["player_id", "player_name"]]
    rows: list[dict[str, Any]] = []
    for player_id, block in minutes.groupby("player_id"):
        total = float(block.role_minutes.sum())
        observations = int(block.role_observations.sum())
        ranked = block.sort_values(["role_minutes", "role_observations", "formation_role"], ascending=[False, False, True])
        primary = str(ranked.iloc[0].formation_role)
        primary_minutes = float(ranked.iloc[0].role_minutes)
        share = primary_minutes / total if total > 0 else 0.0
        distribution = " | ".join(
            f"{row.formation_role}:{row.role_minutes:.0f}m/{int(row.role_observations)}"
            for row in ranked.itertuples(index=False)
        )
        rows.append({
            "player_id": int(player_id),
            "formation_primary_role": primary,
            "formation_role_stability_minutes": share,
            "formation_precise_minutes": total,
            "formation_role_observations": observations,
            "formation_role_distribution": distribution,
        })
    return pd.DataFrame(rows).merge(names, on="player_id", how="left")


def role_score(row: pd.Series, role: str) -> float:
    broad = BROAD.get(role)
    if broad not in WEIGHTS:
        return np.nan
    score = 0.0
    for key, weight in WEIGHTS[broad].items():
        score += weight * (0.5 if key == "base" else float(row.get(key, np.nan)))
    return float(score)


def current_high_impact_ids() -> set[int]:
    ids: set[int] = set()
    if SYNTHETIC_MEMBERS.exists():
        members = pd.read_csv(SYNTHETIC_MEMBERS, low_memory=False)
        members["player_id"] = pd.to_numeric(members["player_id"], errors="coerce")
        primary = members.loc[
            pd.to_numeric(members.get("top_n_requested"), errors="coerce").eq(20)
            & members.get("uncertainty_mode", "").astype(str).eq("pooled")
        ]
        ids.update(primary.player_id.dropna().astype(int))
    if REAL_MEMBERS.exists():
        real = pd.read_csv(REAL_MEMBERS, low_memory=False)
        real["player_id"] = pd.to_numeric(real["player_id"], errors="coerce")
        ids.update(real.player_id.dropna().astype(int))
    return ids


def build_audit() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    current = pd.read_csv(CURRENT_ROLES, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    anchors = pd.read_csv(ANCHORS, low_memory=False)
    for frame in [current, frontier, anchors]:
        frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame["player_id"].astype(int)
    current["role_observations"] = pd.to_numeric(current.get("role_observations"), errors="coerce").fillna(0)
    current["role_stability"] = pd.to_numeric(current.get("role_stability"), errors="coerce").fillna(0)
    current = current.sort_values(["player_id", "role_observations", "role_stability"], ascending=[True, False, False])
    alias_counts = current.groupby("player_id").size().rename("identity_alias_rows")
    current = current.drop_duplicates("player_id", keep="first").merge(alias_counts, on="player_id", how="left")
    frontier = frontier.sort_values(["player_id", "minutes_num"], ascending=[True, False]).drop_duplicates("player_id")

    evidence, reconstruction = reconstruct_roles()
    if not evidence.empty:
        evidence.to_csv(AUDIT / "formation_role_observations.csv.gz", index=False, compression="gzip")
    formation = aggregate_role_evidence(evidence)

    keep = [
        "player_id", "player_name", "world_cup_team", "squad_position", "resolved_role",
        "role_stability", "role_observations", "role_distribution", "reported_minutes",
        "scientific_role_eligible", "minutes_num", "overall", "uncertainty", "conservative_score",
        *DIMENSIONS, "profile_scored",
    ]
    for column in keep:
        if column not in frontier:
            frontier[column] = np.nan
    audit = frontier[keep].merge(
        current[["player_id", "identity_alias_rows"]], on="player_id", how="left"
    ).merge(formation, on="player_id", how="left", suffixes=("", "_formation"))
    audit = audit.merge(anchors, on="player_id", how="left")
    high_impact = current_high_impact_ids()
    audit["high_impact_current_release"] = audit.player_id.isin(high_impact)
    audit["public_anchor_available"] = audit.allowed_roles.notna()
    audit["allowed_role_set"] = audit.allowed_roles.fillna("").map(
        lambda value: {part for part in str(value).split("|") if part}
    )
    audit["current_role_publicly_compatible"] = audit.apply(
        lambda row: (not row.public_anchor_available) or row.resolved_role in row.allowed_role_set,
        axis=1,
    )
    audit["formation_role_publicly_compatible"] = audit.apply(
        lambda row: (not row.public_anchor_available)
        or (pd.notna(row.formation_primary_role) and row.formation_primary_role in row.allowed_role_set),
        axis=1,
    )

    def audited_role(row: pd.Series) -> tuple[str | None, str]:
        formation_role = row.get("formation_primary_role")
        current_role = row.get("resolved_role")
        allowed = row.get("allowed_role_set", set())
        preferred = row.get("preferred_role")
        if allowed:
            if pd.notna(formation_role) and formation_role in allowed:
                return str(formation_role), "formation_and_public_agree"
            if pd.notna(preferred) and str(preferred) in allowed:
                return str(preferred), "public_anchor_override"
            if current_role in allowed:
                return str(current_role), "current_role_publicly_allowed"
            if len(allowed) == 1:
                return next(iter(allowed)), "single_public_role_override"
            return None, "public_anchor_ambiguous_conflict"
        if pd.notna(formation_role):
            return str(formation_role), "formation_only"
        return str(current_role) if pd.notna(current_role) else None, "current_fallback_no_formation"

    resolved = audit.apply(audited_role, axis=1)
    audit["audited_role"] = resolved.map(lambda item: item[0])
    audit["audited_role_source"] = resolved.map(lambda item: item[1])
    audit["role_changed"] = audit.audited_role.notna() & audit.resolved_role.ne(audit.audited_role)
    audit["public_conflict_current"] = audit.public_anchor_available & ~audit.current_role_publicly_compatible
    audit["public_conflict_formation"] = audit.public_anchor_available & ~audit.formation_role_publicly_compatible
    audit["formation_evidence_stable"] = (
        pd.to_numeric(audit.formation_role_stability_minutes, errors="coerce").fillna(0).ge(.60)
        & pd.to_numeric(audit.formation_role_observations, errors="coerce").fillna(0).ge(3)
        & pd.to_numeric(audit.formation_precise_minutes, errors="coerce").fillna(0).ge(900)
    )
    audit["audited_role_eligible"] = (
        audit.audited_role.isin(ROLES)
        & pd.to_numeric(audit.minutes_num, errors="coerce").fillna(0).ge(900)
        & as_bool(audit.profile_scored)
        & (audit.formation_evidence_stable | audit.public_anchor_available)
    )
    for dimension in DIMENSIONS:
        audit[dimension] = pd.to_numeric(audit[dimension], errors="coerce")
    audit["overall_audited"] = audit.apply(
        lambda row: role_score(row, str(row.audited_role)) if row.audited_role in ROLES else np.nan,
        axis=1,
    )
    audit["uncertainty"] = pd.to_numeric(audit.uncertainty, errors="coerce").fillna(.25).clip(.025, .35)
    audit["conservative_score_audited"] = audit.overall_audited - audit.uncertainty

    rankings = audit.loc[audit.audited_role_eligible].copy()
    rankings = rankings.sort_values(
        ["audited_role", "conservative_score_audited", "minutes_num"],
        ascending=[True, False, False],
    )
    rankings["audited_role_rank"] = rankings.groupby("audited_role").cumcount() + 1
    real = rankings.loc[rankings.audited_role_rank.eq(1)].copy()
    avatar = rankings.loc[rankings.audited_role_rank.le(20)].copy()

    before = audit.groupby("resolved_role").player_id.nunique().reindex(ROLES, fill_value=0)
    after = rankings.groupby("audited_role").player_id.nunique().reindex(ROLES, fill_value=0)
    populations = pd.DataFrame({
        "role": ROLES,
        "eligible_current_ontology": [int(before.get(role, 0)) for role in ROLES],
        "audited_stable_candidates": [int(after.get(role, 0)) for role in ROLES],
    })
    populations["top20_complete"] = populations.audited_stable_candidates.ge(20)
    populations["minimum_10_pool"] = populations.audited_stable_candidates.ge(10)

    high = audit.loc[audit.high_impact_current_release].copy()
    critical_conflicts = high.loc[
        high.public_conflict_current | high.public_conflict_formation | high.audited_role.isna()
    ].copy()
    anchored_high = high.public_anchor_available.sum()
    high_formation_coverage = float(high.formation_primary_role.notna().mean()) if len(high) else 0.0
    status = {
        "status": "position_ontology_v2_audited",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "provider_api_calls": 0,
        "current_release_preserved": True,
        "players_in_frontier": int(audit.player_id.nunique()),
        "public_role_anchors": int(len(anchors)),
        "high_impact_players_current_release": int(len(high)),
        "high_impact_players_with_public_anchor": int(anchored_high),
        "high_impact_formation_role_coverage": high_formation_coverage,
        "current_role_public_conflicts_all": int(audit.public_conflict_current.sum()),
        "current_role_public_conflicts_high_impact": int(high.public_conflict_current.sum()),
        "formation_role_public_conflicts_high_impact": int(high.public_conflict_formation.sum()),
        "high_impact_critical_conflicts": int(len(critical_conflicts)),
        "players_changing_role_in_diagnostic_rebuild": int(audit.role_changed.sum()),
        "duplicate_alias_rows_removed": int((audit.identity_alias_rows.fillna(1) - 1).clip(lower=0).sum()),
        "formation_reconstruction": reconstruction,
        "role_population": populations.to_dict("records"),
        "ontology_gate_requirements": {
            "zero_high_impact_public_conflicts": True,
            "high_impact_formation_coverage_minimum": .80,
            "minimum_stable_candidates_per_role": 10,
            "manual_blind_review_required": True,
        },
        "automated_gate_passed": bool(
            len(critical_conflicts) == 0
            and high_formation_coverage >= .80
            and populations.minimum_10_pool.all()
        ),
        "manual_blind_review_complete": False,
        "final_ontology_gate_passed": False,
        "new_final_simulation_allowed": False,
        "diagnostic_rankings_allowed": True,
        "claim": (
            "The outputs are a public-source and formation-aware audit. They are diagnostic "
            "until the high-impact conflict set receives blind human review."
        ),
    }
    return audit, rankings, populations, status


def build_performance_convergence(rankings: pd.DataFrame) -> pd.DataFrame:
    if not PERFORMANCE.exists():
        return pd.DataFrame()
    public = pd.read_csv(PERFORMANCE, low_memory=False)
    public["player_id"] = pd.to_numeric(public.player_id, errors="coerce")
    public = public.dropna(subset=["player_id"]).copy()
    public.player_id = public.player_id.astype(int)
    keep = [
        "player_id", "audited_role", "audited_role_rank", "overall_audited",
        "conservative_score_audited", "minutes_num", "world_cup_team",
    ]
    return public.merge(rankings[keep], on="player_id", how="left")


def write_report(status: dict[str, Any], conflicts: pd.DataFrame, populations: pd.DataFrame, convergence: pd.DataFrame) -> None:
    conflict_rows = []
    for row in conflicts.sort_values(["high_impact_current_release", "player_name"], ascending=[False, True]).head(40).itertuples(index=False):
        conflict_rows.append(
            f"| {row.player_name} | {row.resolved_role} | {row.formation_primary_role} | "
            f"{row.allowed_roles} | {row.audited_role} | {row.audited_role_source} |"
        )
    population_rows = [
        f"| {r.role} | {r.eligible_current_ontology} | {r.audited_stable_candidates} | {'Sí' if r.top20_complete else 'No'} |"
        for r in populations.itertuples(index=False)
    ]
    convergence_rows = []
    if not convergence.empty:
        for row in convergence.itertuples(index=False):
            rank = "sin ranking auditable" if pd.isna(row.audited_role_rank) else f"#{int(row.audited_role_rank)} en {row.audited_role}"
            convergence_rows.append(f"| {row.canonical_name} | {row.public_result} | {rank} |")
    report = f"""# Auditoría pública de la ontología de posiciones v2

Generada: {status['generated_at_utc']}

## Dictamen

La ontología anterior **no queda validada para publicación final**. La auditoría reconstruyó los
roles desde formaciones y grids, ponderó la estabilidad por minutos observados, eliminó alias por
`player_id` y contrastó los jugadores de mayor impacto con fuentes públicas versionadas.

- Conflictos públicos en jugadores de alto impacto: **{status['current_role_public_conflicts_high_impact']}**.
- Conflictos entre reconstrucción de formación y fuente pública: **{status['formation_role_public_conflicts_high_impact']}**.
- Jugadores que cambian de función en el rebuild diagnóstico: **{status['players_changing_role_in_diagnostic_rebuild']}**.
- Gate automático aprobado: **{'sí' if status['automated_gate_passed'] else 'no'}**.
- Nueva simulación final permitida: **no** hasta revisión humana ciega.

## Conflictos críticos

| Jugador | Rol anterior | Rol por formación | Roles públicos permitidos | Rol auditado | Regla |
|---|---|---|---|---|---|
{chr(10).join(conflict_rows) if conflict_rows else '| — | — | — | — | — | Sin conflictos |'}

## Tamaño de los universos posicionales

| Rol | Ontología anterior | Candidatos estables auditados | Top 20 completo |
|---|---:|---:|---|
{chr(10).join(population_rows)}

## Convergencia con resultados públicos 2025/26

Los premios y noticias no determinan el ranking; funcionan como prueba externa de plausibilidad.
Un goleador públicamente reconocido que desaparece del universo ST es una señal de error de
clasificación, no una razón para cambiar pesos después de observar resultados.

| Jugador | Evidencia pública | Posición/ranking en rebuild diagnóstico |
|---|---|---|
{chr(10).join(convergence_rows) if convergence_rows else '| — | — | — |'}

## Próxima condición científica

Dos revisores deben evaluar de manera ciega todos los conflictos de alto impacto y una muestra
estratificada. Solo después de registrar acuerdo, matriz de confusión y macro-F1 se puede promover
esta ontología, reconstruir el Real XI y los avatares y repetir la simulación con la misma semilla.
"""
    (AUDIT / "PUBLIC_AUDIT_REPORT_ES.md").write_text(report, encoding="utf-8")


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    audit, rankings, populations, status = build_audit()
    audit.to_csv(AUDIT / "player_position_audit.csv", index=False)
    rankings.to_csv(AUDIT / "diagnostic_audited_rankings.csv", index=False)
    populations.to_csv(AUDIT / "role_population_before_after.csv", index=False)
    real = rankings.loc[rankings.audited_role_rank.eq(1)].copy()
    avatar = rankings.loc[rankings.audited_role_rank.le(20)].copy()
    real.to_csv(AUDIT / "diagnostic_real_xi.csv", index=False)
    avatar.to_csv(AUDIT / "diagnostic_synthetic_avatar_members.csv", index=False)
    conflicts = audit.loc[
        audit.public_conflict_current | audit.public_conflict_formation | audit.audited_role.isna()
    ].copy()
    conflicts.to_csv(AUDIT / "public_position_conflicts.csv", index=False)
    high = conflicts.loc[conflicts.high_impact_current_release].copy()
    high.to_csv(AUDIT / "high_impact_position_conflicts.csv", index=False)
    convergence = build_performance_convergence(rankings)
    convergence.to_csv(AUDIT / "public_performance_convergence.csv", index=False)
    (AUDIT / "position_ontology_audit_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(status, high, populations, convergence)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
