#!/usr/bin/env python3
"""Partial-identification sensitivity analysis for irreducible provider missingness.

The dedicated fixture-player endpoint was exhausted for every physical residual
fixture. This audit does not invent match statistics. It propagates the maximum
missing exposure through score-space bounds and reports identified sets rather
than forcing a point ranking.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("data/audits/structural_missingness")
SHADOW = Path("data/audits/scope_correct_coverage/shadow_selection/shadow_selection_all_players.csv")
COVERAGE = Path("data/audits/scope_correct_coverage/player_window_coverage_scope_correct.csv")
DIRECT = Path("data/lake/direct_player_stats_progress.csv")
RESIDUAL = Path("data/model_readiness/cache_rebuild/truly_unresolved_player_fixture_pairs.csv")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
SCENARIOS = [
    "observed",
    "empirical_low",
    "empirical_median",
    "empirical_high",
    "strict_low",
    "strict_high",
]
TERMINAL_DIRECT = {
    "provider_endpoint_empty",
    "target_player_missing",
    "target_rows_without_positive_minutes",
    "resolved_positive_minutes",
}


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def jaccard(left: set[int], right: set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    players = pd.read_csv(SHADOW, low_memory=False)
    coverage = pd.read_csv(COVERAGE, low_memory=False)
    direct = pd.read_csv(DIRECT, low_memory=False)
    residual = pd.read_csv(RESIDUAL, low_memory=False)

    players["player_id"] = pd.to_numeric(players.player_id, errors="coerce")
    players = players.dropna(subset=["player_id", "resolved_role"]).copy()
    players["player_id"] = players.player_id.astype(int)
    players = players.loc[players.resolved_role.isin(ROLES)].copy()
    players["stable"] = as_bool(players.get("stable", pd.Series(False, index=players.index)))
    players["covered"] = as_bool(players.get("covered", pd.Series(False, index=players.index)))
    players["needed"] = as_bool(players.get("needed", pd.Series(False, index=players.index)))
    players["overall"] = numeric(players, "overall", np.nan)
    players["uncertainty"] = numeric(players, "uncertainty", 0.25).clip(0.025, 0.35)
    players["minutes_num"] = numeric(players, "minutes_num", 0)
    players = players.loc[players.minutes_num.ge(900) & players.overall.notna()].copy()

    coverage["player_id"] = pd.to_numeric(coverage.player_id, errors="coerce")
    coverage = coverage.dropna(subset=["player_id"]).copy()
    coverage["player_id"] = coverage.player_id.astype(int)
    annual = coverage.loc[coverage.window.eq("annual_current")].copy()
    annual = annual[[
        "player_id", "exact_detailed_minutes", "known_missing_minutes_upper_bound",
        "known_missing_startXI_fixtures", "known_minute_coverage_lower_bound",
        "fixture_endpoint_coverage", "coverage_pass_80pct",
    ]].drop_duplicates("player_id")
    annual["coverage_pass_80pct"] = as_bool(annual.coverage_pass_80pct)
    players = players.merge(annual, on="player_id", how="left")
    players["observed_minutes"] = numeric(players, "exact_detailed_minutes", 0)
    players["missing_minutes_bound"] = numeric(players, "known_missing_minutes_upper_bound", 0).clip(lower=0)
    denominator = players.observed_minutes + players.missing_minutes_bound
    players["missing_fraction"] = np.where(denominator.gt(0), players.missing_minutes_bound / denominator, 0.0)
    players["missing_fraction"] = players.missing_fraction.clip(0, 1)

    direct["fixture_id"] = pd.to_numeric(direct.fixture_id, errors="coerce")
    direct = direct.dropna(subset=["fixture_id"]).copy()
    direct["fixture_id"] = direct.fixture_id.astype(int)
    direct_terminal = set(direct.loc[direct.status.astype(str).isin(TERMINAL_DIRECT), "fixture_id"])
    residual["fixture_id"] = pd.to_numeric(residual.fixture_id, errors="coerce")
    residual["player_id"] = pd.to_numeric(residual.player_id, errors="coerce")
    residual = residual.dropna(subset=["fixture_id", "player_id"]).copy()
    residual[["fixture_id", "player_id"]] = residual[["fixture_id", "player_id"]].astype(int)
    structural_by_player = residual.groupby("player_id").fixture_id.apply(
        lambda values: bool(len(values) and set(values.astype(int)).issubset(direct_terminal))
    )
    players["provider_structural_missingness_confirmed"] = players.player_id.map(structural_by_player).fillna(False)

    empirical = {}
    for role in ROLES:
        reference = players.loc[
            players.resolved_role.eq(role) & players.stable & players.covered,
            "overall",
        ].dropna()
        if reference.empty:
            reference = players.loc[players.resolved_role.eq(role), "overall"].dropna()
        empirical[role] = {
            "q05": float(reference.quantile(0.05)) if len(reference) else 0.0,
            "median": float(reference.quantile(0.50)) if len(reference) else 0.5,
            "q95": float(reference.quantile(0.95)) if len(reference) else 1.0,
        }

    q05 = players.resolved_role.map(lambda role: empirical[role]["q05"])
    q50 = players.resolved_role.map(lambda role: empirical[role]["median"])
    q95 = players.resolved_role.map(lambda role: empirical[role]["q95"])
    weight = players.missing_fraction
    observed_weight = 1.0 - weight
    players["score_observed"] = players.overall
    players["score_empirical_low"] = observed_weight * players.overall + weight * q05
    players["score_empirical_median"] = observed_weight * players.overall + weight * q50
    players["score_empirical_high"] = observed_weight * players.overall + weight * q95
    players["score_strict_low"] = observed_weight * players.overall
    players["score_strict_high"] = observed_weight * players.overall + weight

    for scenario in SCENARIOS:
        players[f"conservative_{scenario}"] = (
            players[f"score_{scenario}"] - players.uncertainty
        ).clip(0, 1)

    winners: list[dict] = []
    memberships: list[dict] = []
    scenario_sets: dict[str, set[int]] = {}
    for scenario in SCENARIOS:
        chosen: set[int] = set()
        for role in ROLES:
            group = players.loc[players.resolved_role.eq(role) & players.stable].copy()
            group = group.sort_values(
                [f"conservative_{scenario}", "minutes_num"], ascending=[False, False]
            )
            if group.empty:
                continue
            winner = group.iloc[0]
            chosen.add(int(winner.player_id))
            winners.append({
                "scenario": scenario,
                "role": role,
                "player_id": int(winner.player_id),
                "player_name": winner.get("player_name"),
                "world_cup_team": winner.get("world_cup_team"),
                "score": float(winner[f"score_{scenario}"]),
                "conservative_score": float(winner[f"conservative_{scenario}"]),
                "covered": bool(winner.covered),
                "provider_structural_missingness_confirmed": bool(winner.provider_structural_missingness_confirmed),
            })
            for rank, row in enumerate(group.head(min(30, len(group))).itertuples(index=False), start=1):
                memberships.append({
                    "scenario": scenario,
                    "role": role,
                    "rank": rank,
                    "player_id": int(row.player_id),
                    "player_name": getattr(row, "player_name", None),
                    "covered": bool(row.covered),
                    "provider_structural_missingness_confirmed": bool(row.provider_structural_missingness_confirmed),
                })
        scenario_sets[scenario] = chosen

    winner_frame = pd.DataFrame(winners)
    membership_frame = pd.DataFrame(memberships)
    baseline = scenario_sets.get("observed", set())
    stability_rows = []
    for scenario, chosen in scenario_sets.items():
        stability_rows.append({
            "scenario": scenario,
            "xi_size": len(chosen),
            "jaccard_vs_observed": jaccard(chosen, baseline),
            "changed_players_vs_observed": len(chosen.symmetric_difference(baseline)),
        })

    role_sets = winner_frame.groupby("role").agg(
        scenario_winner_count=("player_id", "nunique"),
        scenario_winner_ids=("player_id", lambda s: " | ".join(map(str, sorted(set(s.astype(int)))))),
        scenario_winner_names=("player_name", lambda s: " | ".join(sorted(set(s.dropna().astype(str))))),
    ).reset_index()

    strict_rows = []
    for role in ROLES:
        group = players.loc[players.resolved_role.eq(role) & players.stable].copy()
        if group.empty:
            strict_rows.append({"role": role, "strict_identified": False, "identified_player_id": None})
            continue
        lower_ranked = group.sort_values(["conservative_strict_low", "minutes_num"], ascending=[False, False])
        candidate = lower_ranked.iloc[0]
        competitor_upper = group.loc[group.player_id.ne(candidate.player_id), "conservative_strict_high"].max()
        strict_identified = bool(pd.isna(competitor_upper) or candidate.conservative_strict_low > competitor_upper)
        strict_rows.append({
            "role": role,
            "strict_identified": strict_identified,
            "identified_player_id": int(candidate.player_id) if strict_identified else None,
            "identified_player_name": candidate.get("player_name") if strict_identified else None,
            "winner_strict_lower": float(candidate.conservative_strict_low),
            "best_competitor_strict_upper": None if pd.isna(competitor_upper) else float(competitor_upper),
        })
    strict_frame = pd.DataFrame(strict_rows)
    role_sets = role_sets.merge(strict_frame, on="role", how="outer")
    role_sets["scenario_identified"] = role_sets.scenario_winner_count.eq(1)
    role_sets["role_point_identified"] = role_sets.scenario_identified & role_sets.strict_identified.fillna(False)

    unresolved = players.loc[players.provider_structural_missingness_confirmed | players.needed].copy()
    keep = [
        "player_id", "player_name", "world_cup_team", "resolved_role", "stable", "covered", "needed",
        "overall", "uncertainty", "observed_minutes", "missing_minutes_bound", "missing_fraction",
        "known_missing_startXI_fixtures", "known_minute_coverage_lower_bound", "fixture_endpoint_coverage",
        "provider_structural_missingness_confirmed",
    ] + [f"score_{scenario}" for scenario in SCENARIOS] + [f"conservative_{scenario}" for scenario in SCENARIOS]
    unresolved[keep].to_csv(ROOT / "structural_missingness_player_bounds.csv", index=False)
    winner_frame.to_csv(ROOT / "scenario_role_winners.csv", index=False)
    membership_frame.to_csv(ROOT / "scenario_top30_membership.csv", index=False)
    pd.DataFrame(stability_rows).to_csv(ROOT / "scenario_xi_stability.csv", index=False)
    role_sets.to_csv(ROOT / "identified_set_by_role.csv", index=False)

    ambiguous_roles = role_sets.loc[~role_sets.role_point_identified.fillna(False), "role"].dropna().tolist()
    identified_roles = role_sets.loc[role_sets.role_point_identified.fillna(False), "role"].dropna().tolist()
    status = {
        "status": "structural_missingness_sensitivity_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "provider_api_calls": 0,
        "direct_terminal_fixtures": int(len(direct_terminal)),
        "structurally_missing_players": int(players.provider_structural_missingness_confirmed.sum()),
        "scenarios": SCENARIOS,
        "identified_roles": identified_roles,
        "ambiguous_roles": ambiguous_roles,
        "point_identified_xi": bool(len(identified_roles) == len(ROLES)),
        "rankings_allowed": False,
        "claim_ceiling": "role-level identified sets under confirmed structural provider missingness",
        "decision": (
            "all roles are point-identified; manual scientific review can consider unblocking"
            if not ambiguous_roles
            else "do not force a unique Real Best XI; report scenario-robust winners and identified sets"
        ),
    }
    (ROOT / "structural_missingness_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    decision = [
        "# Structural provider missingness decision",
        "",
        f"Generated: {status['generated_at_utc']}",
        "",
        "The dedicated fixture-player endpoint was exhausted for every physical residual fixture.",
        "No synthetic match statistics were inserted. Missing exposure is propagated through strict",
        "and role-empirical score-space bounds, and the result is expressed as an identified set.",
        "",
        f"Point-identified XI: **{status['point_identified_xi']}**",
        f"Identified roles: {', '.join(identified_roles) if identified_roles else 'none'}",
        f"Ambiguous roles: {', '.join(ambiguous_roles) if ambiguous_roles else 'none'}",
        "",
        f"Decision: {status['decision']}.",
    ]
    (ROOT / "STRUCTURAL_MISSINGNESS_DECISION.md").write_text("\n".join(decision) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
