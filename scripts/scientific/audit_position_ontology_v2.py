#!/usr/bin/env python3
"""Robust formation-aware and public-source position ontology audit.

This diagnostic rebuild is intentionally isolated from the frozen simulation release.
It uses only durable repository caches and makes zero network/provider calls.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODEL = Path("data/model_readiness")
OUT = Path("data/audits/position_ontology_v2")
ANCHOR_PATH = Path("data/reference/public_role_anchors_2026.csv")
PERFORMANCE_PATH = Path("data/reference/public_performance_checks_2026.csv")
FRONTIER_PATH = MODEL / "selection_frontier_all_candidates.csv"
CURRENT_ROLE_PATH = MODEL / "eleven_role_evidence.csv"
SYNTHETIC_MEMBERS = Path("data/simulations/identified_set_v1/synthetic_avatar_membership.csv")
REAL_MEMBERS = Path("data/simulations/identified_set_v1/real_identified_set_membership.csv")

ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMS = ["build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]
BROAD = {"GK": "GK", "RB": "FB", "LB": "FB", "RCB": "CB", "LCB": "CB", "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W", "ST": "ST"}
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

# Each list is ordered left-to-right. The provider's low grid column was previously
# validated as the left side of the displayed formation.
TEMPLATES: dict[str, list[list[str]]] = {
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


def read_many(patterns: list[str], wanted: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted({p for pattern in patterns for p in glob.glob(pattern)}):
        try:
            frame = pd.read_csv(path, low_memory=False, usecols=lambda c: c in wanted)
        except Exception:
            continue
        if not frame.empty:
            frame["source_file"] = path
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def numeric(frame: pd.DataFrame, names: list[str], default: float = np.nan) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def strings(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name].astype("string")
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def booleans(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def parse_grid(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    left, right = value.split(":", 1)
    try:
        return int(float(left)), int(float(right))
    except (TypeError, ValueError):
        return None, None


def normalize_formation(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().replace(" ", "")


def generic_roles(parts: list[int], index: int, count: int) -> list[str]:
    first = index == 0
    last = index == len(parts) - 1
    if first:
        return {2: ["LCB", "RCB"], 3: ["LCB", "CB", "RCB"], 4: ["LB", "LCB", "RCB", "RB"], 5: ["LB", "LCB", "CB", "RCB", "RB"]}.get(count, ["UNRESOLVED"] * count)
    if last:
        return {1: ["ST"], 2: ["ST", "ST"], 3: ["LW", "ST", "RW"], 4: ["LW", "ST", "ST", "RW"]}.get(count, ["UNRESOLVED"] * count)
    if index == 1 and parts and parts[0] == 3:
        return {4: ["LB", "CM", "CM", "RB"], 5: ["LB", "CM", "DM", "CM", "RB"]}.get(count, ["UNRESOLVED"] * count)
    if count == 1:
        return ["DM" if index == 1 else "AM"]
    if count == 2:
        return ["DM", "DM"] if index == 1 else ["AM", "AM"]
    if count == 3:
        return ["CM", "DM", "CM"]
    if count == 4:
        return ["LW", "CM", "CM", "RW"]
    if count == 5:
        return ["LB", "CM", "DM", "CM", "RB"]
    return ["UNRESOLVED"] * count


def roles_for_line(formation: str, line_index: int, count: int) -> tuple[list[str], str]:
    template = TEMPLATES.get(formation)
    if template and line_index < len(template) and len(template[line_index]) == count:
        return template[line_index], "formation_template"
    try:
        parts = [int(part) for part in formation.split("-") if part]
    except ValueError:
        parts = []
    return generic_roles(parts, line_index, count), "formation_generic"


def reconstruct() -> tuple[pd.DataFrame, dict[str, Any]]:
    lineup_cols = {"fixture_id", "team_id", "player_id", "player_name", "formation", "grid", "lineup_source", "lineup_position", "position", "pos"}
    player_cols = {"fixture_id", "team_id", "player_id", "minutes", "minutes_num", "provider_position", "position", "pos"}
    lineups = read_many(["data/lake/batches/*_lineups.csv*", "data/audits/fixture_detail_pilot_lineups.csv"], lineup_cols)
    players = read_many(["data/lake/batches/*_players.csv*", "data/audits/fixture_detail_pilot_players.csv"], player_cols)
    if lineups.empty:
        return pd.DataFrame(), {"lineup_rows": 0, "player_rows": int(len(players)), "precise_role_rows": 0}

    for key in ["fixture_id", "team_id", "player_id"]:
        lineups[key] = numeric(lineups, [key])
    lineups = lineups.dropna(subset=["fixture_id", "team_id", "player_id"]).copy()
    for key in ["fixture_id", "team_id", "player_id"]:
        lineups[key] = lineups[key].astype(int)
    if "lineup_source" in lineups.columns:
        source = strings(lineups, ["lineup_source"]).fillna("").str.lower()
        if source.eq("startxi").any():
            lineups = lineups.loc[source.eq("startxi")].copy()
    lineups = lineups.drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
    lineups["formation_clean"] = strings(lineups, ["formation"]).map(normalize_formation)
    parsed = strings(lineups, ["grid"]).apply(parse_grid)
    lineups["grid_row"] = parsed.map(lambda x: x[0])
    lineups["grid_col"] = parsed.map(lambda x: x[1])
    lineups = lineups.dropna(subset=["grid_row", "grid_col"]).copy()
    lineups[["grid_row", "grid_col"]] = lineups[["grid_row", "grid_col"]].astype(int)

    if not players.empty:
        for key in ["fixture_id", "team_id", "player_id"]:
            players[key] = numeric(players, [key])
        players["observed_minutes"] = numeric(players, ["minutes", "minutes_num"], 0).fillna(0).clip(lower=0, upper=130)
        players = players.dropna(subset=["fixture_id", "team_id", "player_id"]).copy()
        for key in ["fixture_id", "team_id", "player_id"]:
            players[key] = players[key].astype(int)
        players = players.sort_values("observed_minutes").drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
        lineups = lineups.merge(players[["fixture_id", "team_id", "player_id", "observed_minutes"]], on=["fixture_id", "team_id", "player_id"], how="left")
    else:
        lineups["observed_minutes"] = np.nan

    records: list[dict[str, Any]] = []
    for (fixture_id, team_id), team in lineups.groupby(["fixture_id", "team_id"], sort=False):
        formation_values = team["formation_clean"].dropna()
        formation = str(formation_values.iloc[0]) if len(formation_values) else ""
        rows = sorted(team.grid_row.unique())
        outfield_rows = [row for row in rows if row != 1]
        row_index = {row: idx for idx, row in enumerate(outfield_rows)}
        for grid_row, block in team.groupby("grid_row", sort=True):
            ordered = block.sort_values("grid_col")
            if grid_row == 1:
                assigned, method = ["GK"] * len(ordered), "goalkeeper_grid"
            else:
                assigned, method = roles_for_line(formation, row_index[grid_row], len(ordered))
            for role, item in zip(assigned, ordered.itertuples(index=False)):
                records.append({
                    "fixture_id": int(fixture_id), "team_id": int(team_id),
                    "player_id": int(item.player_id), "player_name_observed": getattr(item, "player_name", None),
                    "formation": formation, "grid_row": int(item.grid_row), "grid_col": int(item.grid_col),
                    "formation_role": role, "role_method": method,
                    "observed_minutes": float(item.observed_minutes) if pd.notna(item.observed_minutes) else np.nan,
                })
    evidence = pd.DataFrame(records)
    diagnostics = {
        "lineup_rows_with_grid": int(len(lineups)), "player_detail_rows": int(len(players)),
        "precise_role_rows": int(len(evidence)),
        "fixtures": int(evidence.fixture_id.nunique()) if not evidence.empty else 0,
        "teams": int(evidence.team_id.nunique()) if not evidence.empty else 0,
        "rows_with_observed_minutes": int(evidence.observed_minutes.notna().sum()) if not evidence.empty else 0,
        "template_share": float(evidence.role_method.eq("formation_template").mean()) if not evidence.empty else 0.0,
        "unresolved_rows": int(evidence.formation_role.eq("UNRESOLVED").sum()) if not evidence.empty else 0,
        "top_formations": evidence.formation.value_counts().head(15).to_dict() if not evidence.empty else {},
    }
    return evidence, diagnostics


def aggregate_roles(evidence: pd.DataFrame, current_roles: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["player_id", "formation_primary_role"])
    usable = evidence.loc[~evidence.formation_role.eq("UNRESOLVED")].copy()
    usable["weight_minutes"] = pd.to_numeric(usable.observed_minutes, errors="coerce").fillna(0)
    grouped = usable.groupby(["player_id", "formation_role"], as_index=False).agg(
        role_minutes=("weight_minutes", "sum"), role_observations=("fixture_id", "nunique")
    )
    current_map = current_roles.set_index("player_id")["resolved_role"].to_dict()
    rows: list[dict[str, Any]] = []
    for player_id, block in grouped.groupby("player_id"):
        total = float(block.role_minutes.sum())
        observations = int(block.role_observations.sum())
        ranked = block.sort_values(["role_minutes", "role_observations", "formation_role"], ascending=[False, False, True])
        raw = str(ranked.iloc[0].formation_role)
        if raw == "CB":
            current = current_map.get(int(player_id))
            primary = current if current in {"RCB", "LCB"} else None
        else:
            primary = raw if raw in ROLES else None
        best_minutes = float(ranked.iloc[0].role_minutes)
        distribution = " | ".join(f"{r.formation_role}:{r.role_minutes:.0f}m/{int(r.role_observations)}" for r in ranked.itertuples(index=False))
        rows.append({
            "player_id": int(player_id), "formation_primary_role": primary,
            "formation_primary_role_raw": raw, "formation_role_stability_minutes": best_minutes / total if total > 0 else 0,
            "formation_precise_minutes": total, "formation_role_observations": observations,
            "formation_role_distribution": distribution,
        })
    return pd.DataFrame(rows)


def high_impact_ids() -> set[int]:
    ids: set[int] = set()
    if SYNTHETIC_MEMBERS.exists():
        frame = pd.read_csv(SYNTHETIC_MEMBERS, low_memory=False)
        frame["player_id"] = numeric(frame, ["player_id"])
        primary = frame.loc[numeric(frame, ["top_n_requested"]).eq(20) & strings(frame, ["uncertainty_mode"]).fillna("").eq("pooled")]
        ids.update(primary.player_id.dropna().astype(int))
    if REAL_MEMBERS.exists():
        frame = pd.read_csv(REAL_MEMBERS, low_memory=False)
        frame["player_id"] = numeric(frame, ["player_id"])
        ids.update(frame.player_id.dropna().astype(int))
    return ids


def score_role(row: pd.Series, role: object) -> float:
    if role not in BROAD:
        return np.nan
    weights = WEIGHTS[BROAD[str(role)]]
    score = 0.0
    for key, weight in weights.items():
        value = 0.5 if key == "base" else pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
        if pd.isna(value):
            return np.nan
        score += weight * float(value)
    return float(score)


def resolve_role(row: pd.Series) -> tuple[object, str]:
    current = row.get("resolved_role")
    formation = row.get("formation_primary_role")
    allowed = row.get("allowed_role_set", set())
    preferred = row.get("preferred_role")
    if allowed:
        if pd.notna(formation) and formation in allowed:
            return formation, "formation_and_public_agree"
        if pd.notna(preferred) and str(preferred) in allowed:
            return str(preferred), "public_preferred_override"
        if len(allowed) == 1:
            return next(iter(allowed)), "single_public_role_override"
        if current in allowed:
            return current, "current_role_publicly_allowed"
        return pd.NA, "public_anchor_unresolved_conflict"
    if pd.notna(formation):
        return formation, "formation_only"
    return current, "current_fallback_no_precise_minutes"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frontier = pd.read_csv(FRONTIER_PATH, low_memory=False)
    current = pd.read_csv(CURRENT_ROLE_PATH, low_memory=False)
    anchors = pd.read_csv(ANCHOR_PATH, low_memory=False)
    for frame in [frontier, current, anchors]:
        frame["player_id"] = numeric(frame, ["player_id"])
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)
    current["role_observations"] = numeric(current, ["role_observations"], 0).fillna(0)
    current["role_stability"] = numeric(current, ["role_stability"], 0).fillna(0)
    alias_rows = current.groupby("player_id").size().rename("identity_rows_before_deduplication")
    current = current.sort_values(["player_id", "role_observations", "role_stability"], ascending=[True, False, False]).drop_duplicates("player_id")
    current = current.merge(alias_rows, on="player_id", how="left")
    frontier["minutes_num"] = numeric(frontier, ["minutes_num"], 0).fillna(0)
    frontier = frontier.sort_values(["player_id", "minutes_num"], ascending=[True, False]).drop_duplicates("player_id")

    evidence, reconstruction = reconstruct()
    if not evidence.empty:
        evidence.to_csv(OUT / "formation_role_observations.csv.gz", index=False, compression="gzip")
    formation = aggregate_roles(evidence, current)

    base_columns = ["player_id", "player_name", "world_cup_team", "squad_position", "resolved_role", "role_stability", "role_observations", "role_distribution", "minutes_num", "overall", "uncertainty", "conservative_score", *DIMS, "profile_scored"]
    for column in base_columns:
        if column not in frontier.columns:
            frontier[column] = np.nan
    audit = frontier[base_columns].merge(current[["player_id", "identity_rows_before_deduplication"]], on="player_id", how="left")
    audit = audit.merge(formation, on="player_id", how="left")
    audit = audit.merge(anchors, on="player_id", how="left", suffixes=("", "_public"))
    audit["high_impact_current_release"] = audit.player_id.isin(high_impact_ids())
    audit["public_anchor_available"] = audit.allowed_roles.notna()
    audit["allowed_role_set"] = audit.allowed_roles.fillna("").map(lambda value: {x for x in str(value).split("|") if x})
    audit["current_role_publicly_compatible"] = audit.apply(lambda row: not row.public_anchor_available or row.resolved_role in row.allowed_role_set, axis=1)
    audit["formation_role_publicly_compatible"] = audit.apply(lambda row: not row.public_anchor_available or (pd.notna(row.formation_primary_role) and row.formation_primary_role in row.allowed_role_set), axis=1)
    choices = audit.apply(resolve_role, axis=1)
    audit["audited_role"] = choices.map(lambda x: x[0])
    audit["audited_role_source"] = choices.map(lambda x: x[1])
    audit["audited_role_publicly_compatible"] = audit.apply(lambda row: not row.public_anchor_available or row.audited_role in row.allowed_role_set, axis=1)
    audit["role_changed"] = audit.audited_role.notna() & audit.resolved_role.ne(audit.audited_role)
    audit["public_conflict_current"] = audit.public_anchor_available & ~audit.current_role_publicly_compatible
    audit["public_conflict_formation"] = audit.public_anchor_available & ~audit.formation_role_publicly_compatible
    audit["formation_evidence_stable"] = numeric(audit, ["formation_role_stability_minutes"], 0).fillna(0).ge(.60) & numeric(audit, ["formation_role_observations"], 0).fillna(0).ge(3) & numeric(audit, ["formation_precise_minutes"], 0).fillna(0).ge(900)
    audit["profile_scored_bool"] = booleans(audit.profile_scored)
    audit["audited_role_eligible"] = audit.audited_role.isin(ROLES) & audit.minutes_num.ge(900) & audit.profile_scored_bool & (audit.formation_evidence_stable | audit.public_anchor_available)
    for dim in DIMS:
        audit[dim] = numeric(audit, [dim])
    audit["overall_audited"] = audit.apply(lambda row: score_role(row, row.audited_role), axis=1)
    audit["uncertainty"] = numeric(audit, ["uncertainty"], .25).fillna(.25).clip(.025, .35)
    audit["conservative_score_audited"] = audit.overall_audited - audit.uncertainty

    rankings = audit.loc[audit.audited_role_eligible & audit.overall_audited.notna()].copy()
    rankings = rankings.sort_values(["audited_role", "conservative_score_audited", "minutes_num"], ascending=[True, False, False])
    rankings["audited_role_rank"] = rankings.groupby("audited_role").cumcount() + 1
    role_counts_before = audit.groupby("resolved_role").player_id.nunique().reindex(ROLES, fill_value=0)
    role_counts_after = rankings.groupby("audited_role").player_id.nunique().reindex(ROLES, fill_value=0)
    populations = pd.DataFrame({"role": ROLES, "eligible_current_ontology": [int(role_counts_before.get(r, 0)) for r in ROLES], "audited_stable_candidates": [int(role_counts_after.get(r, 0)) for r in ROLES]})
    populations["minimum_10_pool"] = populations.audited_stable_candidates.ge(10)
    populations["top20_complete"] = populations.audited_stable_candidates.ge(20)

    high = audit.loc[audit.high_impact_current_release].copy()
    high_conflicts = high.loc[high.public_conflict_current | high.public_conflict_formation | ~high.audited_role_publicly_compatible | high.audited_role.isna()].copy()
    high_formation_coverage = float(high.formation_primary_role.notna().mean()) if len(high) else 0.0
    automated_gate = bool(
        high.audited_role_publicly_compatible.all()
        and high.audited_role.notna().all()
        and high_formation_coverage >= .80
        and populations.minimum_10_pool.all()
    )
    status = {
        "status": "position_ontology_v2_audited",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0, "provider_api_calls": 0,
        "frozen_candidate_simulation_preserved": True,
        "frontier_players": int(audit.player_id.nunique()),
        "public_role_anchors": int(len(anchors)),
        "high_impact_current_release": int(len(high)),
        "high_impact_with_public_anchor": int(high.public_anchor_available.sum()),
        "high_impact_formation_coverage": high_formation_coverage,
        "current_role_public_conflicts_all": int(audit.public_conflict_current.sum()),
        "current_role_public_conflicts_high_impact": int(high.public_conflict_current.sum()),
        "formation_role_public_conflicts_high_impact": int(high.public_conflict_formation.sum()),
        "unresolved_or_incompatible_high_impact_after_audit": int(len(high_conflicts)),
        "players_changing_role_diagnostic": int(audit.role_changed.sum()),
        "duplicate_identity_rows_removed": int((current.identity_rows_before_deduplication.fillna(1) - 1).clip(lower=0).sum()),
        "formation_reconstruction": reconstruction,
        "role_population": populations.to_dict("records"),
        "automated_ontology_gate_passed": automated_gate,
        "manual_blind_review_complete": False,
        "final_ontology_gate_passed": False,
        "new_final_simulation_allowed": False,
        "diagnostic_rankings_allowed": True,
        "next_action": "blind-review high-impact conflicts and stratified sample; then rerun selection and simulation only if validated",
    }

    audit.drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "player_position_audit.csv", index=False)
    rankings.drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "diagnostic_audited_rankings.csv", index=False)
    populations.to_csv(OUT / "role_population_before_after.csv", index=False)
    rankings.loc[rankings.audited_role_rank.eq(1)].drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "diagnostic_real_xi.csv", index=False)
    rankings.loc[rankings.audited_role_rank.le(20)].drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "diagnostic_synthetic_avatar_members.csv", index=False)
    audit.loc[audit.public_conflict_current | audit.public_conflict_formation | audit.audited_role.isna()].drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "public_position_conflicts.csv", index=False)
    high_conflicts.drop(columns=["allowed_role_set"], errors="ignore").to_csv(OUT / "high_impact_position_conflicts.csv", index=False)

    if PERFORMANCE_PATH.exists():
        performance = pd.read_csv(PERFORMANCE_PATH, low_memory=False)
        performance["player_id"] = numeric(performance, ["player_id"])
        performance = performance.dropna(subset=["player_id"]).copy()
        performance.player_id = performance.player_id.astype(int)
        convergence = performance.merge(rankings[["player_id", "audited_role", "audited_role_rank", "conservative_score_audited", "minutes_num"]], on="player_id", how="left")
    else:
        convergence = pd.DataFrame()
    convergence.to_csv(OUT / "public_performance_convergence.csv", index=False)
    (OUT / "position_ontology_audit_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    conflict_lines = []
    for row in high_conflicts.sort_values("player_name").itertuples(index=False):
        conflict_lines.append(f"| {row.player_name} | {row.resolved_role} | {row.formation_primary_role} | {row.allowed_roles} | {row.audited_role} | {row.audited_role_source} |")
    population_lines = [f"| {r.role} | {r.eligible_current_ontology} | {r.audited_stable_candidates} | {'sí' if r.top20_complete else 'no'} |" for r in populations.itertuples(index=False)]
    convergence_lines = []
    for row in convergence.itertuples(index=False):
        result = "sin ranking auditable" if pd.isna(row.audited_role_rank) else f"#{int(row.audited_role_rank)} {row.audited_role}"
        convergence_lines.append(f"| {row.canonical_name} | {row.public_result} | {result} |")
    report = f"""# Auditoría pública de la ontología de posiciones v2

## Dictamen

La ontología anterior no puede promoverse como definitiva. Se reconstruyeron las posiciones desde formaciones y grids, se ponderaron por minutos observados, se deduplicaron identidades por `player_id` y se contrastaron jugadores de alto impacto con fuentes públicas versionadas.

- Jugadores del release actual con conflicto público: **{status['current_role_public_conflicts_high_impact']}**.
- Conflictos formación–fuente pública: **{status['formation_role_public_conflicts_high_impact']}**.
- Cambios de rol en el rebuild diagnóstico: **{status['players_changing_role_diagnostic']}**.
- Gate automático: **{'aprobado' if automated_gate else 'no aprobado'}**.
- Nueva simulación final: **bloqueada hasta revisión humana ciega**.

## Conflictos de alto impacto todavía abiertos

| Jugador | Rol anterior | Rol por formación | Roles públicos | Rol auditado | Regla |
|---|---|---|---|---|---|
{chr(10).join(conflict_lines) if conflict_lines else '| — | — | — | — | — | ninguno |'}

## Universo por rol

| Rol | Ontología anterior | Candidatos estables auditados | Top 20 completo |
|---|---:|---:|---|
{chr(10).join(population_lines)}

## Convergencia pública 2025/26

Los premios y noticias no determinan el ranking. Se utilizan como validación externa de plausibilidad: si un goleador reconocido desaparece de ST o un lateral aparece como CM, la ontología debe explicar la discrepancia.

| Jugador | Evidencia pública | Ranking diagnóstico |
|---|---|---|
{chr(10).join(convergence_lines) if convergence_lines else '| — | — | — |'}

## Restricción científica

El Real XI y el Synthetic XI de esta auditoría son diagnósticos. Solo se volverá a simular después de una revisión ciega, matriz de confusión y promoción explícita de la ontología.
"""
    (OUT / "PUBLIC_AUDIT_REPORT_ES.md").write_text(report, encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
