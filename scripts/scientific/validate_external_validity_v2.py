#!/usr/bin/env python3
"""Validate opponent-strength adjustment, goalkeeper stability and v2 XI robustness."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CONTEXT = Path("data/lake/v2_fixture_context.csv.gz")
PROFILES = Path("data/audits/external_validity_v2/strength_adjusted_candidate_roles.csv")
REAL_XI = Path("data/definitive_experiment_v2/real_xi.csv")
MANIFEST = Path("data/definitive_experiment_v2/team_manifest.json")
OUT = Path("data/audits/external_validity_v2")
STATUS = OUT / "validation_status.json"
SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMS = ["build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]
ROLE_WEIGHTS = {
    "GK": {"goalkeeping": .55, "build_up": .20, "retention": .15, "overall_final": .10},
    "RB": {"defending": .22, "duels": .14, "build_up": .18, "progression": .28, "creation": .18},
    "LB": {"defending": .22, "duels": .14, "build_up": .18, "progression": .28, "creation": .18},
    "RCB": {"defending": .33, "duels": .25, "build_up": .22, "retention": .20},
    "LCB": {"defending": .33, "duels": .25, "build_up": .22, "retention": .20},
    "DM": {"defending": .25, "duels": .18, "build_up": .25, "retention": .20, "progression": .12},
    "CM": {"build_up": .23, "retention": .20, "progression": .20, "creation": .16, "defending": .12, "duels": .09},
    "AM": {"creation": .32, "progression": .24, "finishing": .17, "retention": .15, "build_up": .12},
    "RW": {"progression": .29, "creation": .23, "finishing": .22, "retention": .14, "duels": .12},
    "LW": {"progression": .29, "creation": .23, "finishing": .22, "retention": .14, "duels": .12},
    "ST": {"finishing": .44, "creation": .12, "progression": .12, "duels": .18, "retention": .14},
}
NATIONAL_PATTERNS = (
    "world cup", "qualification", "qualifiers", "nations league", "friendlies",
    "copa america", "gold cup", "africa cup of nations", "asian cup",
    "european championship", "euro championship", "ofc nations", "arab cup",
    "africa nations championship", "olympics men", "olympic games men",
)
CLUB_EXCLUSIONS = ("club world cup", "uefa champions league", "afc champions league", "caf champions league", "concacaf champions", "copa libertadores")


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def is_national(name: object) -> bool:
    text = str(name or "").strip().lower()
    if any(value in text for value in CLUB_EXCLUSIONS):
        return False
    return any(value in text for value in NATIONAL_PATTERNS)


def logit_adjust(value: float, shift: float) -> float:
    if not np.isfinite(value):
        return np.nan
    clipped = min(1 - 1e-6, max(1e-6, float(value)))
    return 1.0 / (1.0 + math.exp(-(math.log(clipped / (1 - clipped)) + shift)))


def score(frame: pd.DataFrame, role: str) -> pd.Series:
    result = pd.Series(0.0, index=frame.index)
    for metric, weight in ROLE_WEIGHTS[role].items():
        result += pd.to_numeric(frame[metric], errors="coerce") * weight
    return result


def elo_holdout(context: pd.DataFrame) -> dict:
    frame = context.copy()
    frame["date_utc"] = pd.to_datetime(frame.date_utc, utc=True, errors="coerce")
    for col in ["home_team_id", "away_team_id", "home_goals", "away_goals"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["date_utc", "home_team_id", "away_team_id", "home_goals", "away_goals"]).copy()
    frame["domain"] = np.where(frame.league_name.map(is_national), "national", "club")
    diagnostics = {}
    combined_actual = []
    combined_expected = []
    combined_naive = []
    for domain, group in frame.groupby("domain"):
        group = group.sort_values(["date_utc", "fixture_id"]).copy()
        cut = max(1, int(len(group) * 0.80))
        train = group.iloc[:cut]
        holdout = group.iloc[cut:]
        ratings: dict[int, float] = defaultdict(lambda: 1500.0)
        home_advantage = 45.0 if domain == "club" else 25.0
        k = 22.0 if domain == "club" else 26.0

        def update(row):
            home = int(row.home_team_id)
            away = int(row.away_team_id)
            rh = ratings[home]
            ra = ratings[away]
            expected = 1 / (1 + 10 ** ((ra - (rh + home_advantage)) / 400))
            actual = 1.0 if row.home_goals > row.away_goals else 0.0 if row.home_goals < row.away_goals else 0.5
            margin = abs(float(row.home_goals) - float(row.away_goals))
            multiplier = 1.0 if margin <= 1 else 1.0 + 0.35 * math.log1p(margin - 1)
            delta = k * multiplier * (actual - expected)
            ratings[home] = rh + delta
            ratings[away] = ra - delta
            return actual, expected

        train_actual = []
        for row in train.itertuples(index=False):
            actual, _ = update(row)
            train_actual.append(actual)
        naive = float(np.mean(train_actual)) if train_actual else 0.5
        actuals = []
        expected_values = []
        for row in holdout.itertuples(index=False):
            actual, expected = update(row)
            actuals.append(actual)
            expected_values.append(expected)
        brier = float(np.mean((np.asarray(actuals) - np.asarray(expected_values)) ** 2)) if actuals else None
        naive_brier = float(np.mean((np.asarray(actuals) - naive) ** 2)) if actuals else None
        skill = 1 - brier / naive_brier if brier is not None and naive_brier and naive_brier > 0 else None
        diagnostics[domain] = {"train_matches": len(train), "holdout_matches": len(holdout), "brier": brier, "naive_brier": naive_brier, "skill": skill}
        combined_actual.extend(actuals)
        combined_expected.extend(expected_values)
        combined_naive.extend([naive] * len(actuals))
    brier = float(np.mean((np.asarray(combined_actual) - np.asarray(combined_expected)) ** 2))
    naive_brier = float(np.mean((np.asarray(combined_actual) - np.asarray(combined_naive)) ** 2))
    skill = 1 - brier / naive_brier if naive_brier > 0 else 0.0
    return {"domains": diagnostics, "holdout_matches": len(combined_actual), "brier": brier, "naive_brier": naive_brier, "skill": skill, "passed": bool(skill > 0.0 and len(combined_actual) >= 500)}


def gamma_sensitivity(profiles: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    eligible = profiles.loc[truth(profiles.final_candidate_eligible_v2)].copy()
    gammas = [0.0, 0.09, 0.18, 0.27, 0.36]
    rows = []
    selected_ids = selected.set_index("slot").player_id.astype(int).to_dict()
    overlap_values = []
    selected_top3_checks = []
    for gamma in gammas:
        current = eligible.copy()
        shift = gamma * pd.to_numeric(current.context_strength_z, errors="coerce").fillna(0).clip(-3, 3) * pd.to_numeric(current.network_reliability, errors="coerce").fillna(0)
        for metric in ["overall_final", "build_up", "progression", "creation", "finishing", "defending", "duels", "retention"]:
            raw = pd.to_numeric(current[f"raw_{metric}"], errors="coerce")
            current[metric] = [logit_adjust(value, delta) for value, delta in zip(raw, shift, strict=True)]
        non_gk = ~current.final_role.eq("GK")
        current.loc[non_gk, "goalkeeping"] = [logit_adjust(value, delta) for value, delta in zip(pd.to_numeric(current.loc[non_gk, "raw_goalkeeping"], errors="coerce"), shift.loc[non_gk], strict=True)]
        current.loc[~non_gk, "goalkeeping"] = current.loc[~non_gk, "goalkeeping_v2"]
        winners = set()
        for role in SLOTS:
            pool = current.loc[current.final_role.eq(role)].copy()
            pool["sensitivity_score"] = score(pool, role)
            pool = pool.sort_values(["sensitivity_score", "player_id"], ascending=[False, True]).reset_index(drop=True)
            frozen_id = selected_ids[role]
            frozen_rank = int(pool.index[pool.player_id.astype(int).eq(frozen_id)][0] + 1)
            winner = pool.iloc[0]
            winners.add(int(winner.player_id))
            selected_top3_checks.append(frozen_rank <= 3)
            rows.append({"gamma": gamma, "role": role, "winner_player_id": int(winner.player_id), "winner_player_name": winner.player_name, "frozen_player_id": frozen_id, "frozen_rank": frozen_rank, "frozen_score": float(pool.loc[pool.player_id.astype(int).eq(frozen_id), "sensitivity_score"].iloc[0]), "winner_score": float(winner.sensitivity_score)})
        overlap_values.append(len(winners & set(selected_ids.values())))
    result = pd.DataFrame(rows)
    summary = {"gammas": gammas, "mean_xi_overlap_of_11": float(np.mean(overlap_values)), "minimum_xi_overlap_of_11": int(min(overlap_values)), "frozen_slot_top3_rate": float(np.mean(selected_top3_checks)), "passed": bool(min(overlap_values) >= 8 and np.mean(selected_top3_checks) >= 0.90)}
    return result, summary


def goalkeeper_sensitivity(profiles: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    gk = profiles.loc[profiles.final_role.eq("GK") & truth(profiles.final_candidate_eligible_v2)].copy()
    selected_id = int(selected.loc[selected.slot.eq("GK"), "player_id"].iloc[0])
    variants = {
        "base": {"save_pct_component": .50, "goals_prevented_component": .20, "clean_sheet_component": .15, "distribution_component": .10, "penalty_component": .05},
        "shot_stopping_heavy": {"save_pct_component": .65, "goals_prevented_component": .20, "clean_sheet_component": .05, "distribution_component": .05, "penalty_component": .05},
        "balanced": {"save_pct_component": .40, "goals_prevented_component": .25, "clean_sheet_component": .15, "distribution_component": .15, "penalty_component": .05},
        "distribution_heavy": {"save_pct_component": .40, "goals_prevented_component": .15, "clean_sheet_component": .10, "distribution_component": .30, "penalty_component": .05},
    }
    rows = []
    selected_ranks = []
    for name, weights in variants.items():
        unshrunk = sum(pd.to_numeric(gk[metric], errors="coerce") * weight for metric, weight in weights.items())
        reliability = pd.to_numeric(gk.goalkeeper_model_reliability, errors="coerce").fillna(0)
        current = gk.copy()
        current["goalkeeping"] = 0.5 + reliability * (unshrunk - 0.5)
        current["variant_role_score"] = score(current, "GK")
        current = current.sort_values(["variant_role_score", "player_id"], ascending=[False, True]).reset_index(drop=True)
        rank = int(current.index[current.player_id.astype(int).eq(selected_id)][0] + 1)
        selected_ranks.append(rank)
        rows.append({"variant": name, "winner_player_id": int(current.iloc[0].player_id), "winner_player_name": current.iloc[0].player_name, "frozen_gk_id": selected_id, "frozen_rank": rank, "frozen_score": float(current.loc[current.player_id.astype(int).eq(selected_id), "variant_role_score"].iloc[0]), "winner_score": float(current.iloc[0].variant_role_score)})
    result = pd.DataFrame(rows)
    summary = {"variants": list(variants), "frozen_goalkeeper_ranks": selected_ranks, "maximum_rank": max(selected_ranks), "passed": bool(max(selected_ranks) <= 3)}
    return result, summary


def selected_audit(profiles: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    merged = selected[["slot", "player_id", "player_name"]].merge(profiles, left_on=["slot", "player_id"], right_on=["final_role", "player_id"], how="left", suffixes=("_selected", ""))
    rows = []
    checks = []
    for row in merged.itertuples(index=False):
        pool = profiles.loc[profiles.final_role.eq(row.slot) & truth(profiles.final_candidate_eligible_v2)].sort_values(["adjusted_role_score_v2", "player_id"], ascending=[False, True]).reset_index(drop=True)
        rank = int(pool.index[pool.player_id.astype(int).eq(int(row.player_id))][0] + 1)
        top2 = float(pool.iloc[1].adjusted_role_score_v2) if len(pool) > 1 else np.nan
        margin = float(row.adjusted_role_score_v2 - top2) if rank == 1 else float(row.adjusted_role_score_v2 - float(pool.iloc[0].adjusted_role_score_v2))
        passed = bool(row.context_coverage >= .90 and row.context_matches >= 5 and row.family_minutes >= 900 and row.family_observations >= 3 and rank <= 3)
        checks.append(passed)
        rows.append({"slot": row.slot, "player_id": int(row.player_id), "player_name": row.player_name, "club_name": row.club_name, "competition_name": row.competition_name, "exact_role_minutes": float(row.exact_role_minutes), "exact_role_observations": int(row.exact_role_observations), "exact_role_share": float(row.exact_role_share), "family_minutes": float(row.family_minutes), "family_observations": int(row.family_observations), "context_matches": int(row.context_matches), "context_coverage": float(row.context_coverage), "opponent_strength": float(row.opponent_strength_adjusted), "competition_strength": float(row.competition_strength), "rank_v2": rank, "score_margin_vs_best_alternative": margin, "plausibility_gate_passed": passed})
    frame = pd.DataFrame(rows)
    return frame, {"selected_players": len(frame), "all_selected_passed": bool(all(checks)), "passed_count": int(sum(checks)), "passed": bool(all(checks))}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in [CONTEXT, PROFILES, REAL_XI, MANIFEST]:
        if not path.exists():
            raise RuntimeError(f"missing v2 validation input: {path}")
    context = pd.read_csv(CONTEXT, low_memory=False)
    profiles = pd.read_csv(PROFILES, low_memory=False)
    selected = pd.read_csv(REAL_XI, low_memory=False)
    selected["player_id"] = pd.to_numeric(selected.player_id, errors="coerce").astype(int)

    holdout = elo_holdout(context)
    gamma_frame, gamma_summary = gamma_sensitivity(profiles, selected)
    gk_frame, gk_summary = goalkeeper_sensitivity(profiles, selected)
    audit_frame, audit_summary = selected_audit(profiles, selected)
    gamma_frame.to_csv(OUT / "gamma_sensitivity.csv", index=False)
    gk_frame.to_csv(OUT / "goalkeeper_weight_sensitivity.csv", index=False)
    audit_frame.to_csv(OUT / "selected_player_validity_audit.csv", index=False)

    passed = bool(holdout["passed"] and gamma_summary["passed"] and gk_summary["passed"] and audit_summary["passed"])
    status = {"status": "external_validity_v2_validation_completed", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "elo_predictive_holdout": holdout, "context_gamma_sensitivity": gamma_summary, "goalkeeper_weight_sensitivity": gk_summary, "selected_player_plausibility": audit_summary, "external_validity_v2_validation_passed": passed, "simulation_authorized": False, "next_action": "run independent post-freeze directional validation" if passed else "repair failed validation component before simulation"}
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
