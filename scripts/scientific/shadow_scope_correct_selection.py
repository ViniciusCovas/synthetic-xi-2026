#!/usr/bin/env python3
"""Evaluate the final selection gate using scope-correct exact-window coverage.

Shadow mode only: canonical coverage, rankings and release files are untouched.
The logic matches the existing uncertainty-bounded selection gate, except that:
- coverage comes from exact_window_known_minutes_v2;
- the 900-minute eligibility threshold uses exact-window detailed minutes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MODEL = Path("data/model_readiness")
AUDIT = Path("data/audits/scope_correct_coverage")
OUT = AUDIT / "shadow_selection"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
Z90 = 1.6448536269514722


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frontier = pd.read_csv(MODEL / "selection_frontier_all_candidates.csv", low_memory=False)
    coverage = pd.read_csv(AUDIT / "player_window_coverage_scope_correct.csv", low_memory=False)

    for column in [
        "player_id", "reported_minutes", "minutes_num", "role_observations",
        "role_stability", "overall", "uncertainty", "conservative_score",
    ]:
        frontier[column] = pd.to_numeric(frontier.get(column), errors="coerce")
    frontier = frontier.dropna(subset=["player_id", "resolved_role"])
    frontier["player_id"] = frontier["player_id"].astype(int)
    frontier = frontier.sort_values(
        ["player_id", "role_observations", "role_stability"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id")
    frontier = frontier.loc[
        frontier.resolved_role.isin(ROLES)
        & frontier.minutes_num.fillna(0).ge(900)
    ].copy()

    coverage["player_id"] = pd.to_numeric(coverage["player_id"], errors="coerce")
    coverage = coverage.dropna(subset=["player_id"])
    coverage["player_id"] = coverage["player_id"].astype(int)
    coverage["coverage_pass_80pct"] = as_bool(coverage["coverage_pass_80pct"])
    for window in ["annual_current", "pre_world_cup"]:
        block = coverage.loc[coverage.window.eq(window), [
            "player_id", "fixture_endpoint_coverage", "coverage_pass_80pct",
            "missing_fixture_endpoints", "known_minute_coverage_lower_bound",
            "known_missing_startXI_fixtures", "exact_detailed_minutes",
        ]].drop_duplicates("player_id")
        block = block.rename(columns={
            "fixture_endpoint_coverage": f"cov_{window}",
            "coverage_pass_80pct": f"pass_{window}",
            "missing_fixture_endpoints": f"miss_{window}",
            "known_minute_coverage_lower_bound": f"known_minute_cov_{window}",
            "known_missing_startXI_fixtures": f"missing_startXI_{window}",
            "exact_detailed_minutes": f"exact_minutes_{window}",
        })
        frontier = frontier.merge(block, on="player_id", how="left")
        frontier[f"pass_{window}"] = as_bool(frontier[f"pass_{window}"])
        frontier[f"cov_{window}"] = pd.to_numeric(frontier[f"cov_{window}"], errors="coerce").fillna(0)
        frontier[f"miss_{window}"] = pd.to_numeric(frontier[f"miss_{window}"], errors="coerce").fillna(0).astype(int)

    frontier["covered"] = frontier.pass_annual_current & frontier.pass_pre_world_cup
    frontier["uncertainty"] = frontier.uncertainty.fillna(0.25).clip(0.025, 0.35)
    frontier["lo90"] = (frontier.overall - Z90 * frontier.uncertainty).clip(0, 1)
    frontier["hi90"] = (frontier.overall + Z90 * frontier.uncertainty).clip(0, 1)
    frontier["stable"] = (
        frontier.role_stability.fillna(0).ge(0.60)
        & frontier.role_observations.fillna(0).ge(3)
        & frontier.overall.notna()
    )
    frontier["rank"] = np.nan
    frontier["urank"] = np.nan
    frontier["needed"] = False
    frontier["reason"] = "outside_decision_frontier"

    role_status: list[dict] = []
    for role in ROLES:
        idx = frontier.index[frontier.resolved_role.eq(role)]
        group = frontier.loc[idx].copy()
        if group.empty:
            role_status.append({
                "role": role, "eligible_candidates": 0, "stable_candidates": 0,
                "required_pool_size": 0, "covered_candidates": 0,
                "unresolved_challengers": 0, "role_gate_passed": False,
            })
            continue
        ranked = group.sort_values(["conservative_score", "minutes_num"], ascending=[False, False])
        frontier.loc[ranked.index, "rank"] = range(1, len(ranked) + 1)
        upper_ranked = group.sort_values(["hi90", "minutes_num"], ascending=[False, False])
        frontier.loc[upper_ranked.index, "urank"] = range(1, len(upper_ranked) + 1)
        group = frontier.loc[idx].copy()
        stable = group.loc[group.stable]
        required = min(30, len(stable))
        covered = stable.loc[stable.covered].sort_values("lo90", ascending=False)
        pool_enabled = len(covered) >= required and required > 0
        top30_threshold = float(covered.iloc[required - 1].lo90) if pool_enabled else -1.0
        best_threshold = float(covered.iloc[0].lo90) if len(covered) else -1.0
        ids: set[int] = set()
        reasons: dict[int, str] = {}
        under = group.loc[~group.covered]
        if not pool_enabled:
            count = max(required - len(covered), 5)
            for row in under.sort_values(["rank", "hi90"], ascending=[True, False]).head(count).itertuples():
                pid = int(row.player_id)
                ids.add(pid)
                reasons[pid] = "covered_pool_shortage"
        for row in under.itertuples():
            pid = int(row.player_id)
            hi = float(row.hi90) if pd.notna(row.hi90) else 1.0
            rank = int(row.rank) if pd.notna(row.rank) else 9999
            urank = int(row.urank) if pd.notna(row.urank) else 9999
            if row.stable and pool_enabled and hi >= top30_threshold:
                ids.add(pid); reasons[pid] = "upper90_can_enter_top30"
            if row.stable and len(covered) and hi >= best_threshold:
                ids.add(pid); reasons[pid] = "upper90_can_enter_real_xi"
            if row.stable and rank <= required + 5:
                ids.add(pid); reasons.setdefault(pid, "top35_guardrail")
            if not row.stable and (urank <= 15 or rank <= 15):
                ids.add(pid); reasons[pid] = "high_ability_role_stabilization"
        mask = frontier.player_id.isin(ids)
        frontier.loc[mask, "needed"] = True
        frontier.loc[mask, "reason"] = frontier.loc[mask, "player_id"].map(reasons)
        role_status.append({
            "role": role,
            "eligible_candidates": int(len(group)),
            "stable_candidates": int(len(stable)),
            "required_pool_size": int(required),
            "covered_candidates": int(len(covered)),
            "unresolved_challengers": int(len(ids)),
            "role_gate_passed": bool(pool_enabled and not ids),
        })

    unresolved = frontier.loc[frontier.needed].copy()
    frontier.to_csv(OUT / "shadow_selection_all_players.csv", index=False)
    unresolved.to_csv(OUT / "shadow_selection_unresolved_players.csv", index=False)
    pd.DataFrame(role_status).to_csv(OUT / "shadow_selection_roles.csv", index=False)

    # Coverage correction review.
    false_to_true = coverage.loc[coverage.get("pass_changed_false_to_true", False).map(lambda v: str(v).lower() in {"true", "1"})]
    true_to_false = coverage.loc[coverage.get("pass_changed_true_to_false", False).map(lambda v: str(v).lower() in {"true", "1"})]
    review = {
        "false_to_true_by_window": false_to_true.groupby("window").size().to_dict(),
        "true_to_false_by_window": true_to_false.groupby("window").size().to_dict(),
        "true_to_false_players": int(true_to_false.player_id.nunique()),
        "true_to_false_missing_startXI_total": int(pd.to_numeric(true_to_false.get("known_missing_startXI_fixtures"), errors="coerce").fillna(0).sum()),
    }
    (OUT / "coverage_correction_review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")

    roles = pd.DataFrame(role_status)
    gate = bool(len(roles) and roles.role_gate_passed.all() and unresolved.empty)
    status = {
        "status": "shadow_scope_correct_selection_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "canonical_files_changed": False,
        "eligibility_definition": ">=900 exact-window detailed minutes",
        "coverage_definition": "exact_window_known_minutes_v2",
        "eligible_candidates": int(len(frontier)),
        "fully_covered_both_windows": int(frontier.covered.sum()),
        "unresolved_players": int(unresolved.player_id.nunique()),
        "roles": role_status,
        "shadow_selection_sufficiency_gate_passed": gate,
        "rankings_allowed": False,
        "next_action": "promote audited scope correction to canonical pipeline" if gate else "prioritize only residual unresolved players after scope correction",
    }
    (OUT / "shadow_selection_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
