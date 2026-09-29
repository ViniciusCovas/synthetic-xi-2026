#!/usr/bin/env python3
"""Build one externally contextualized Real XI and one AI XI for experiment v2."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from simulator.ai_xi_generator import build_ai_xi

STATUS = Path("data/audits/external_validity_v2/strength_model_status.json")
CANDIDATES = Path("data/audits/external_validity_v2/strength_adjusted_candidate_roles.csv")
OUT = Path("data/definitive_experiment_v2")
SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMENSIONS = ["build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]
PROFILE_METRICS = ["overall_final", *DIMENSIONS]
BASE_ROLE_WEIGHTS: dict[str, dict[str, float]] = {
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
ROLE_WEIGHTS = {role: {metric: float(weights.get(metric, 0.0)) for metric in PROFILE_METRICS} for role, weights in BASE_ROLE_WEIGHTS.items()}


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def state_is_better(candidate: tuple, incumbent: tuple | None, frame: pd.DataFrame) -> bool:
    if incumbent is None:
        return True
    for index in range(4):
        left = round(float(candidate[index]), 12)
        right = round(float(incumbent[index]), 12)
        if left != right:
            return left > right
    sentinel = 10**18
    candidate_ids = tuple(int(frame.loc[i, "player_id"]) if i >= 0 else sentinel for i in candidate[4])
    incumbent_ids = tuple(int(frame.loc[i, "player_id"]) if i >= 0 else sentinel for i in incumbent[4])
    return candidate_ids < incumbent_ids


def global_real_xi(frame: pd.DataFrame) -> pd.DataFrame:
    role_index = {role: index for index, role in enumerate(SLOTS)}
    full_mask = (1 << len(SLOTS)) - 1
    empty = tuple([-1] * len(SLOTS))
    states: dict[int, tuple] = {0: (0.0, 0.0, 0.0, 0.0, empty)}
    for _, player_rows in frame.groupby("player_id", sort=True):
        current = dict(states)
        for mask, state in states.items():
            for row_index in player_rows.index:
                role = str(frame.loc[row_index, "final_role"])
                bit = 1 << role_index[role]
                if mask & bit:
                    continue
                selection = list(state[4])
                selection[role_index[role]] = int(row_index)
                candidate = (
                    state[0] + float(frame.loc[row_index, "adjusted_role_score_v2"]),
                    state[1] + float(frame.loc[row_index, "conservative_score_final"]),
                    state[2] + float(frame.loc[row_index, "exact_window_total_minutes"]),
                    state[3] + float(frame.loc[row_index, "context_matches"]),
                    tuple(selection),
                )
                new_mask = mask | bit
                if state_is_better(candidate, current.get(new_mask), frame):
                    current[new_mask] = candidate
        states = current
    if full_mask not in states:
        raise RuntimeError("no feasible one-player-per-slot v2 assignment")
    selected = frame.loc[list(states[full_mask][4])].copy()
    selected["slot_order"] = selected.final_role.map(role_index)
    return selected.sort_values("slot_order").drop(columns="slot_order")


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "player_id", "player_name", "final_role", "final_candidate_eligible_v2",
        "exact_window_total_minutes", "context_matches", "context_coverage",
        "club_name", "competition_id", "competition_name", "competition_strength",
        "opponent_strength_adjusted", "adjusted_role_score_v2", "overall_final",
        "conservative_score_final", "uncertainty", *DIMENSIONS,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"v2 candidate table missing columns: {missing}")
    frame = frame.copy()
    numeric = [
        "player_id", "exact_window_total_minutes", "context_matches", "context_coverage",
        "competition_strength", "opponent_strength_adjusted", "adjusted_role_score_v2",
        "overall_final", "conservative_score_final", "uncertainty", *DIMENSIONS,
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["player_id", "final_role", "adjusted_role_score_v2", *PROFILE_METRICS])
    frame.player_id = frame.player_id.astype(int)
    frame.final_role = frame.final_role.astype(str).str.upper()
    frame = frame.loc[frame.final_role.isin(SLOTS) & truth(frame.final_candidate_eligible_v2)].copy()
    frame = frame.sort_values(["player_id", "final_role", "context_matches"], ascending=[True, True, False]).drop_duplicates(["player_id", "final_role"])
    counts = frame.groupby("final_role").player_id.nunique().reindex(SLOTS, fill_value=0)
    failures = counts.loc[counts.lt(20)].to_dict()
    if failures:
        raise RuntimeError(f"v2 minimum role pool failed: {failures}")
    return frame.reset_index(drop=True)


def main() -> None:
    if not STATUS.exists() or not CANDIDATES.exists():
        raise RuntimeError("run build_strength_adjusted_profiles_v2.py first")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if not status.get("external_validity_profile_gate_passed", False):
        raise RuntimeError(f"v2 profile gate blocked: {status}")
    frame = validate(pd.read_csv(CANDIDATES, low_memory=False))
    real_selected = global_real_xi(frame)

    real_columns = [
        "final_role", "player_id", "player_name", "world_cup_team", "club_name",
        "competition_id", "competition_name", "exact_window_total_minutes",
        "context_matches", "context_coverage", "opponent_strength_adjusted",
        "competition_strength", "context_strength_z", "raw_role_score",
        "adjusted_role_score_v2", "conservative_score_final", "uncertainty",
        "overall_final", *DIMENSIONS,
    ]
    real = real_selected[real_columns].rename(columns={
        "final_role": "slot", "exact_window_total_minutes": "minutes",
        "adjusted_role_score_v2": "adjusted_role_score",
        "conservative_score_final": "conservative_score", "overall_final": "overall",
    })

    generator_frame = frame.rename(columns={"final_role": "generator_role"}).copy()
    agents = build_ai_xi(
        generator_frame, "generator_role", ROLE_WEIGHTS,
        seed=20260721, candidates_per_role=50_000, minimum_pool=20,
    )
    ai_rows = []
    for agent in agents:
        role_pool = generator_frame.loc[generator_frame.generator_role.eq(agent.role)].copy()
        numeric_profile = role_pool[PROFILE_METRICS].apply(pd.to_numeric, errors="coerce")
        clean_positions = numeric_profile.dropna().index.to_list()
        donor_records = [role_pool.loc[clean_positions[position]] for position in agent.donor_rows]
        donor_ids = [int(record.player_id) for record in donor_records]
        donor_names = [str(record.player_name) for record in donor_records]
        uncertainty = sum(weight * float(record.uncertainty) for weight, record in zip(agent.donor_weights, donor_records, strict=True))
        annual_minutes = sum(weight * float(record.exact_window_total_minutes) for weight, record in zip(agent.donor_weights, donor_records, strict=True))
        metrics = dict(agent.metrics)
        ai_rows.append({
            "slot": agent.role,
            "agent_id": f"AI-V2-{agent.role}-20260721",
            "utility": agent.utility,
            "mahalanobis_distance": agent.mahalanobis_distance,
            "nearest_real_distance": agent.nearest_real_distance,
            "seed": agent.seed,
            "candidates_evaluated": agent.candidates_evaluated,
            "donor_player_ids": "|".join(map(str, donor_ids)),
            "donor_player_names": "|".join(donor_names),
            "donor_weights": "|".join(f"{value:.12f}" for value in agent.donor_weights),
            "minutes": annual_minutes,
            "uncertainty": uncertainty,
            "overall": float(metrics.pop("overall_final")),
            **{metric: float(metrics[metric]) for metric in DIMENSIONS},
        })
    ai = pd.DataFrame(ai_rows)

    OUT.mkdir(parents=True, exist_ok=True)
    real_path = OUT / "real_xi.csv"
    ai_path = OUT / "ai_xi.csv"
    real.to_csv(real_path, index=False, float_format="%.12f")
    ai.to_csv(ai_path, index=False, float_format="%.12f")

    plausibility_rows = []
    for selected in real.itertuples(index=False):
        pool = frame.loc[frame.final_role.eq(selected.slot)].sort_values(["adjusted_role_score_v2", "player_id"], ascending=[False, True]).head(10)
        for rank, alternative in enumerate(pool.itertuples(index=False), start=1):
            plausibility_rows.append({
                "slot": selected.slot,
                "selected_player_id": int(selected.player_id),
                "selected_player_name": selected.player_name,
                "alternative_rank": rank,
                "alternative_player_id": int(alternative.player_id),
                "alternative_player_name": alternative.player_name,
                "alternative_club": alternative.club_name,
                "alternative_competition": alternative.competition_name,
                "raw_role_score": float(alternative.raw_role_score),
                "adjusted_role_score_v2": float(alternative.adjusted_role_score_v2),
                "opponent_strength": float(alternative.opponent_strength_adjusted),
                "competition_strength": float(alternative.competition_strength),
                "context_matches": int(alternative.context_matches),
                "context_coverage": float(alternative.context_coverage),
                "selected": int(alternative.player_id) == int(selected.player_id),
            })
    pd.DataFrame(plausibility_rows).to_csv(OUT / "selected_player_plausibility.csv", index=False)

    manifest = {
        "status": "v2_teams_frozen_pending_independent_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_version": "v2_external_validity",
        "master_seed": 20260721,
        "real_xi_sha256": sha256(real_path),
        "ai_xi_sha256": sha256(ai_path),
        "candidate_role_table_sha256": sha256(CANDIDATES),
        "strength_model_status_sha256": sha256(STATUS),
        "real_players": int(len(real)),
        "ai_agents": int(len(ai)),
        "slots": SLOTS,
        "external_context_required": True,
        "goalkeeper_model_discriminative": bool(status.get("goalkeeper_model", {}).get("passed")),
        "old_v1_result_status": "preserved_diagnostic_invalidated_for_global_best_xi_claim",
        "next_action": "audit selected-player plausibility, run independent post-freeze validation, then authorize a new simulation",
    }
    canonical_json(OUT / "team_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
