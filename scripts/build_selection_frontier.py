#!/usr/bin/env python3
"""Build the conservative player-selection frontier for the final estimand.

A player remains in the frontier when they could still enter either the Real Best
XI or a Top-30 synthetic-avatar pool after accounting for profile uncertainty.
Players with insufficient detailed data are retained automatically rather than
being excluded by an incomplete score. This makes targeted extraction efficient
without creating a data-dependent false exclusion.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulator.profiles import load_feature_table

OUT = Path("data/model_readiness")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    role_path = OUT / "eleven_role_evidence.csv"
    coverage_path = OUT / "player_window_coverage.csv"
    priority_path = OUT / "coverage_priority_fixtures.csv"
    if not role_path.exists() or not coverage_path.exists():
        status = {
            "status": "waiting_for_role_or_coverage_evidence",
            "selection_frontier_ready": False,
        }
        (OUT / "selection_frontier_status.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, indent=2))
        return

    roles = pd.read_csv(role_path)
    for column in ["player_id", "role_observations", "role_stability", "reported_minutes"]:
        roles[column] = pd.to_numeric(roles[column], errors="coerce")
    roles = roles.dropna(subset=["player_id", "resolved_role"])
    roles["player_id"] = roles["player_id"].astype(int)
    # Name variants can create duplicate rows for one provider ID. Keep the row with
    # the strongest positional evidence, never two versions of the same player.
    roles = roles.sort_values(
        ["player_id", "role_observations", "role_stability"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id", keep="first")
    roles = roles.loc[roles["resolved_role"].isin(ROLES)].copy()
    roles = roles.loc[roles["reported_minutes"].fillna(0).ge(900)].copy()

    features = load_feature_table().copy()
    features["player_id"] = pd.to_numeric(features["player_id"], errors="coerce")
    features = features.dropna(subset=["player_id"])
    features["player_id"] = features["player_id"].astype(int)
    features = features.sort_values(
        ["player_id", "minutes_num"], ascending=[True, False]
    ).drop_duplicates("player_id")
    keep = [
        "player_id", "minutes_num", "overall", "uncertainty", "conservative_score",
        "build_up", "progression", "creation", "finishing", "defending", "duels",
        "retention", "goalkeeping",
    ]
    frontier = roles.merge(features[keep], on="player_id", how="left")
    frontier["profile_scored"] = frontier["overall"].notna()
    frontier["uncertainty"] = pd.to_numeric(
        frontier["uncertainty"], errors="coerce"
    ).fillna(0.25).clip(0.025, 0.35)
    frontier["lower_95"] = (
        pd.to_numeric(frontier["overall"], errors="coerce")
        - 1.96 * frontier["uncertainty"]
    ).clip(0, 1)
    frontier["upper_95"] = (
        pd.to_numeric(frontier["overall"], errors="coerce")
        + 1.96 * frontier["uncertainty"]
    ).clip(0, 1)
    frontier["role_rank_conservative"] = np.nan
    frontier["top30_lower_threshold"] = np.nan
    frontier["best_lower_threshold"] = np.nan
    frontier["plausible_top30"] = False
    frontier["plausible_real_xi"] = False
    frontier["guardrail_top35"] = False
    frontier["insufficient_evidence_guardrail"] = (
        ~frontier["profile_scored"]
        | frontier["role_observations"].fillna(0).lt(3)
        | frontier["role_stability"].fillna(0).lt(0.60)
    )

    for role, index in frontier.groupby("resolved_role").groups.items():
        block = frontier.loc[index]
        scored = block.loc[block["profile_scored"]].copy()
        if scored.empty:
            continue
        ranked = scored.sort_values(
            ["conservative_score", "minutes_num"], ascending=[False, False]
        )
        frontier.loc[ranked.index, "role_rank_conservative"] = np.arange(1, len(ranked) + 1)
        k = min(30, len(scored))
        top30_threshold = float(scored.nlargest(k, "lower_95")["lower_95"].min())
        best_threshold = float(scored["lower_95"].max())
        frontier.loc[index, "top30_lower_threshold"] = top30_threshold
        frontier.loc[index, "best_lower_threshold"] = best_threshold
        frontier.loc[index, "plausible_top30"] = (
            frontier.loc[index, "upper_95"].fillna(1.0) >= top30_threshold
        )
        frontier.loc[index, "plausible_real_xi"] = (
            frontier.loc[index, "upper_95"].fillna(1.0) >= best_threshold
        )
        frontier.loc[index, "guardrail_top35"] = (
            frontier.loc[index, "role_rank_conservative"].fillna(10_000) <= 35
        )

    frontier["in_selection_frontier"] = (
        frontier["plausible_top30"]
        | frontier["plausible_real_xi"]
        | frontier["guardrail_top35"]
        | frontier["insufficient_evidence_guardrail"]
    )
    frontier["frontier_reason"] = frontier.apply(
        lambda row: "insufficient_evidence_guardrail"
        if row["insufficient_evidence_guardrail"]
        else "plausible_real_xi"
        if row["plausible_real_xi"]
        else "plausible_top30"
        if row["plausible_top30"]
        else "top35_guardrail",
        axis=1,
    )
    frontier.to_csv(OUT / "selection_frontier_all_candidates.csv", index=False)
    selected = frontier.loc[frontier["in_selection_frontier"]].copy()
    selected.to_csv(OUT / "selection_frontier.csv", index=False)

    coverage = pd.read_csv(coverage_path)
    coverage["player_id"] = pd.to_numeric(coverage["player_id"], errors="coerce")
    coverage = coverage.dropna(subset=["player_id"])
    coverage["player_id"] = coverage["player_id"].astype(int)
    selected_ids = set(selected["player_id"].astype(int))
    selected_coverage = coverage.loc[coverage["player_id"].isin(selected_ids)].copy()
    selected_coverage.to_csv(OUT / "selection_frontier_coverage.csv", index=False)

    if priority_path.exists():
        priority = pd.read_csv(priority_path)
        priority["player_id"] = pd.to_numeric(priority["player_id"], errors="coerce")
        priority = priority.dropna(subset=["player_id"])
        priority["player_id"] = priority["player_id"].astype(int)
        targeted = priority.loc[priority["player_id"].isin(selected_ids)].copy()
    else:
        targeted = pd.DataFrame(
            columns=[
                "player_id", "player_name", "world_cup_team", "window",
                "fixture_id", "benchmark_precheck", "priority_reason",
            ]
        )
    targeted.to_csv(OUT / "selection_frontier_priority_fixtures.csv", index=False)

    windows = []
    for window, block in selected_coverage.groupby("window"):
        passed = block["coverage_pass_80pct"].map(as_bool)
        windows.append(
            {
                "window": window,
                "frontier_players": int(block["player_id"].nunique()),
                "players_passing_80pct": int(block.loc[passed, "player_id"].nunique()),
                "pass_rate": float(passed.mean()),
                "missing_fixture_endpoints": int(
                    pd.to_numeric(block["missing_fixture_endpoints"], errors="coerce")
                    .fillna(0)
                    .sum()
                ),
            }
        )
    annual = selected_coverage.loc[
        selected_coverage["window"].eq("annual_current"), "coverage_pass_80pct"
    ].map(as_bool)
    pre = selected_coverage.loc[
        selected_coverage["window"].eq("pre_world_cup"), "coverage_pass_80pct"
    ].map(as_bool)
    status = {
        "status": "selection_frontier_evaluated",
        "method": "role-wise 95% uncertainty frontier plus top-35 and insufficient-evidence guardrails",
        "eligible_role_candidates": int(len(frontier)),
        "frontier_players": int(selected["player_id"].nunique()),
        "frontier_by_role": selected.groupby("resolved_role")["player_id"].nunique().reindex(ROLES, fill_value=0).to_dict(),
        "unscored_or_low_role_evidence_retained": int(selected["insufficient_evidence_guardrail"].sum()),
        "priority_player_fixture_pairs": int(len(targeted)),
        "priority_unique_fixtures": int(targeted["fixture_id"].nunique()) if not targeted.empty else 0,
        "windows": windows,
        "frontier_coverage_gate_passed": bool(len(annual) and annual.all() and len(pre) and pre.all()),
        "rankings_allowed": False,
        "policy": "extract frontier gaps; exclude only when an upper uncertainty bound cannot reach the relevant role threshold",
    }
    (OUT / "selection_frontier_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
