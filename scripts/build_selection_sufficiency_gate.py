#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("data/model_readiness")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
Z90 = 1.6448536269514722


def as_bool(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frontier_path = OUT / "selection_frontier_all_candidates.csv"
    coverage_path = OUT / "player_window_coverage.csv"
    priority_path = OUT / "coverage_priority_fixtures.csv"
    if not frontier_path.exists() or not coverage_path.exists():
        status = {
            "status": "waiting_for_selection_candidates_or_coverage",
            "selection_sufficiency_gate_passed": False,
        }
        (OUT / "selection_sufficiency_status.json").write_text(json.dumps(status, indent=2))
        return

    players = pd.read_csv(frontier_path, low_memory=False)
    for column in [
        "player_id", "reported_minutes", "minutes_num", "role_observations",
        "role_stability", "overall", "uncertainty", "conservative_score",
    ]:
        players[column] = pd.to_numeric(players.get(column), errors="coerce")
    players = players.dropna(subset=["player_id", "resolved_role"])
    players["player_id"] = players["player_id"].astype(int)
    players = players.sort_values(
        ["player_id", "role_observations", "role_stability"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id")
    # Frozen v0.5 eligibility: 900 minutes inside the exact annual window.
    players = players.loc[
        players.resolved_role.isin(ROLES)
        & players.minutes_num.fillna(0).ge(900)
    ].copy()

    coverage = pd.read_csv(coverage_path, low_memory=False)
    coverage["player_id"] = pd.to_numeric(coverage.player_id, errors="coerce")
    coverage = coverage.dropna(subset=["player_id"])
    coverage["player_id"] = coverage.player_id.astype(int)
    coverage["coverage_pass_80pct"] = coverage.coverage_pass_80pct.map(as_bool)

    for window in ["annual_current", "pre_world_cup"]:
        available = [
            column for column in [
                "player_id", "fixture_endpoint_coverage", "coverage_pass_80pct",
                "missing_fixture_endpoints", "known_minute_coverage_lower_bound",
                "known_missing_startXI_fixtures", "exact_detailed_minutes",
                "coverage_definition_version",
            ] if column in coverage.columns
        ]
        block = coverage.loc[coverage.window.eq(window), available].copy()
        block = block.sort_values("fixture_endpoint_coverage").drop_duplicates("player_id", keep="last")
        rename = {
            "fixture_endpoint_coverage": f"cov_{window}",
            "coverage_pass_80pct": f"pass_{window}",
            "missing_fixture_endpoints": f"miss_{window}",
            "known_minute_coverage_lower_bound": f"known_minute_cov_{window}",
            "known_missing_startXI_fixtures": f"missing_startXI_{window}",
            "exact_detailed_minutes": f"exact_minutes_{window}",
            "coverage_definition_version": f"coverage_version_{window}",
        }
        block = block.rename(columns=rename)
        players = players.merge(block, on="player_id", how="left")
        players[f"pass_{window}"] = players[f"pass_{window}"].fillna(False).map(as_bool)
        players[f"cov_{window}"] = pd.to_numeric(players[f"cov_{window}"], errors="coerce").fillna(0)
        players[f"miss_{window}"] = pd.to_numeric(players[f"miss_{window}"], errors="coerce").fillna(0).astype(int)

    players["covered"] = players.pass_annual_current & players.pass_pre_world_cup
    players["uncertainty"] = players.uncertainty.fillna(0.25).clip(0.025, 0.35)
    players["lo90"] = (players.overall - Z90 * players.uncertainty).clip(0, 1)
    players["hi90"] = (players.overall + Z90 * players.uncertainty).clip(0, 1)
    players["stable"] = (
        players.role_stability.fillna(0).ge(0.60)
        & players.role_observations.fillna(0).ge(3)
        & players.overall.notna()
    )
    players["rank"] = np.nan
    players["urank"] = np.nan
    players["needed"] = False
    players["reason"] = "outside_decision_frontier"

    role_status: list[dict] = []
    for role in ROLES:
        indices = players.index[players.resolved_role.eq(role)]
        group = players.loc[indices].copy()
        if group.empty:
            role_status.append({
                "role": role,
                "eligible_candidates": 0,
                "stable_candidates": 0,
                "required_pool_size": 0,
                "covered_candidates": 0,
                "unresolved_challengers": 0,
                "role_gate_passed": False,
            })
            continue

        ranked = group.sort_values(["conservative_score", "minutes_num"], ascending=[False, False])
        players.loc[ranked.index, "rank"] = range(1, len(ranked) + 1)
        upper_ranked = group.sort_values(["hi90", "minutes_num"], ascending=[False, False])
        players.loc[upper_ranked.index, "urank"] = range(1, len(upper_ranked) + 1)

        group = players.loc[indices].copy()
        stable = group.loc[group.stable]
        required = min(30, len(stable))
        covered = stable.loc[stable.covered].sort_values("lo90", ascending=False)
        pool_enabled = len(covered) >= required and required > 0
        top30_threshold = float(covered.iloc[required - 1].lo90) if pool_enabled else -1.0
        best_threshold = float(covered.iloc[0].lo90) if len(covered) else -1.0
        unresolved_ids: set[int] = set()
        reasons: dict[int, str] = {}
        undercovered = group.loc[~group.covered]

        if not pool_enabled:
            count = max(required - len(covered), 5)
            for row in undercovered.sort_values(["rank", "hi90"], ascending=[True, False]).head(count).itertuples():
                pid = int(row.player_id)
                unresolved_ids.add(pid)
                reasons[pid] = "covered_pool_shortage"

        for row in undercovered.itertuples():
            pid = int(row.player_id)
            hi = float(row.hi90) if pd.notna(row.hi90) else 1.0
            rank = int(row.rank) if pd.notna(row.rank) else 9999
            upper_rank = int(row.urank) if pd.notna(row.urank) else 9999
            if row.stable and pool_enabled and hi >= top30_threshold:
                unresolved_ids.add(pid); reasons[pid] = "upper90_can_enter_top30"
            if row.stable and len(covered) and hi >= best_threshold:
                unresolved_ids.add(pid); reasons[pid] = "upper90_can_enter_real_xi"
            if row.stable and rank <= required + 5:
                unresolved_ids.add(pid); reasons.setdefault(pid, "top35_guardrail")
            if not row.stable and (upper_rank <= 15 or rank <= 15):
                unresolved_ids.add(pid); reasons[pid] = "high_ability_role_stabilization"

        mask = players.player_id.isin(unresolved_ids)
        players.loc[mask, "needed"] = True
        players.loc[mask, "reason"] = players.loc[mask, "player_id"].map(reasons)
        role_status.append({
            "role": role,
            "eligible_candidates": int(len(group)),
            "stable_candidates": int(len(stable)),
            "required_pool_size": int(required),
            "covered_candidates": int(len(covered)),
            "unresolved_challengers": int(len(unresolved_ids)),
            "role_gate_passed": bool(pool_enabled and not unresolved_ids),
        })

    unresolved = players.loc[players.needed].copy()
    players.to_csv(OUT / "selection_sufficiency_all_players.csv", index=False)
    unresolved.to_csv(OUT / "selection_sufficiency_unresolved_players.csv", index=False)

    if priority_path.exists() and not unresolved.empty:
        raw = pd.read_csv(priority_path, low_memory=False)
        raw.to_csv(OUT / "coverage_priority_fixtures_all.csv", index=False)
        raw["player_id"] = pd.to_numeric(raw.player_id, errors="coerce")
        raw = raw.dropna(subset=["player_id"])
        raw["player_id"] = raw.player_id.astype(int)
        priority = raw.loc[raw.player_id.isin(set(unresolved.player_id))].copy()
        priority["selection_resolution_reason"] = priority.player_id.map(
            unresolved.set_index("player_id").reason.to_dict()
        )
    else:
        priority = pd.DataFrame(columns=["player_id", "fixture_id", "window", "selection_resolution_reason"])

    priority.to_csv(OUT / "selection_sufficiency_priority_fixtures.csv", index=False)
    priority.to_csv(priority_path, index=False)
    roles = pd.DataFrame(role_status)
    gate = bool(len(roles) and roles.role_gate_passed.all() and unresolved.empty)
    status = {
        "status": "selection_sufficiency_evaluated",
        "coverage_definition": "exact_window_known_minutes_v2",
        "eligibility_definition": ">=900 exact-window detailed minutes",
        "screening_interval": "90% ability interval; final estimates retain 95% intervals",
        "eligible_candidates": int(len(players)),
        "fully_covered_both_windows": int(players.covered.sum()),
        "unresolved_players": int(unresolved.player_id.nunique()),
        "priority_player_fixture_pairs": int(len(priority)),
        "priority_unique_fixtures": int(priority.fixture_id.nunique()) if len(priority) else 0,
        "roles": role_status,
        "selection_sufficiency_gate_passed": gate,
        "rankings_allowed": gate,
        "policy": "Exclude a sub-covered player only when its 90% upper bound cannot alter the covered Top-30 or best-XI set and it is outside declared guardrails.",
    }
    (OUT / "selection_sufficiency_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
