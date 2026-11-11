#!/usr/bin/env python3
"""Build and hash exactly one Real XI and one AI XI after every design gate passes.

The Real XI is selected by an exact global one-to-one assignment, not a greedy role
order. The AI XI is generated from complete whole-player vectors inside each reviewed
slot and never consults the opponent, exploratory outcomes or match engine.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from simulator.ai_xi_generator import build_ai_xi

GATE = Path("data/audits/definitive_experiment_v1/gate_status.json")
CANDIDATES = Path("data/audits/position_ontology_v3/final_candidate_roles.csv")
OUT = Path("data/definitive_experiment_v1")
SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMENSIONS = [
    "build_up", "progression", "creation", "finishing", "defending", "duels",
    "retention", "goalkeeping",
]
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
ROLE_WEIGHTS = {
    role: {metric: float(weights.get(metric, 0.0)) for metric in PROFILE_METRICS}
    for role, weights in BASE_ROLE_WEIGHTS.items()
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def role_score(frame: pd.DataFrame, role: str) -> pd.Series:
    output = pd.Series(0.0, index=frame.index)
    for metric, weight in ROLE_WEIGHTS[role].items():
        output = output + pd.to_numeric(frame[metric], errors="coerce") * weight
    return output


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "player_id", "player_name", "final_role", "exact_window_total_minutes",
        "family_minutes", "family_share", "coverage_pass_90pct", "human_review_resolved",
        "final_candidate_eligible", "overall_final", "conservative_score_final",
        "uncertainty", *DIMENSIONS,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"final_candidate_roles.csv is missing required columns: {missing}")
    frame = frame.copy()
    numeric_columns = [
        "player_id", "exact_window_total_minutes", "family_minutes", "family_share",
        "overall_final", "conservative_score_final", "uncertainty", *DIMENSIONS,
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["player_id", "final_role", *PROFILE_METRICS])
    frame["player_id"] = frame.player_id.astype(int)
    frame["final_role"] = frame.final_role.astype(str).str.strip().str.upper()
    frame = frame.loc[
        frame.final_role.isin(SLOTS)
        & truth(frame.coverage_pass_90pct)
        & truth(frame.human_review_resolved)
        & truth(frame.final_candidate_eligible)
    ].copy()
    frame = frame.sort_values(
        ["player_id", "final_role", "family_minutes", "family_share"],
        ascending=[True, True, False, False],
    ).drop_duplicates(["player_id", "final_role"], keep="first")
    counts = frame.groupby("final_role").player_id.nunique().reindex(SLOTS, fill_value=0)
    failures = counts.loc[counts.lt(20)].to_dict()
    if failures:
        raise RuntimeError(f"minimum reviewed and covered role pool not satisfied: {failures}")
    return frame


def state_is_better(candidate: tuple, incumbent: tuple | None, frame: pd.DataFrame) -> bool:
    if incumbent is None:
        return True
    for index in range(4):
        left = round(float(candidate[index]), 12)
        right = round(float(incumbent[index]), 12)
        if left != right:
            return left > right
    candidate_rows = candidate[4]
    incumbent_rows = incumbent[4]
    sentinel = 10**18
    candidate_ids = tuple(
        int(frame.loc[row_index, "player_id"]) if row_index >= 0 else sentinel
        for row_index in candidate_rows
    )
    incumbent_ids = tuple(
        int(frame.loc[row_index, "player_id"]) if row_index >= 0 else sentinel
        for row_index in incumbent_rows
    )
    return candidate_ids < incumbent_ids


def global_real_xi(frame: pd.DataFrame) -> pd.DataFrame:
    role_index = {role: index for index, role in enumerate(SLOTS)}
    full_mask = (1 << len(SLOTS)) - 1
    empty_selection = tuple([-1] * len(SLOTS))
    states: dict[int, tuple] = {0: (0.0, 0.0, 0.0, 0.0, empty_selection)}

    for player_id, player_rows in frame.groupby("player_id", sort=True):
        current_states = dict(states)
        options = list(player_rows.index)
        for mask, state in states.items():
            for row_index in options:
                role = str(frame.loc[row_index, "final_role"])
                bit = 1 << role_index[role]
                if mask & bit:
                    continue
                selection = list(state[4])
                selection[role_index[role]] = int(row_index)
                candidate = (
                    state[0] + float(frame.loc[row_index, "adjusted_role_score"]),
                    state[1] + float(frame.loc[row_index, "conservative_score_final"]),
                    state[2] + float(frame.loc[row_index, "exact_window_total_minutes"]),
                    state[3] + float(frame.loc[row_index, "family_minutes"]),
                    tuple(selection),
                )
                new_mask = mask | bit
                if state_is_better(candidate, current_states.get(new_mask), frame):
                    current_states[new_mask] = candidate
        states = current_states

    if full_mask not in states:
        raise RuntimeError("no feasible one-player-per-slot Real XI assignment exists")
    selected_indices = states[full_mask][4]
    selected = frame.loc[list(selected_indices)].copy()
    selected["slot_order"] = selected.final_role.map(role_index)
    selected = selected.sort_values("slot_order").drop(columns="slot_order")
    if selected.player_id.nunique() != 11 or set(selected.final_role) != set(SLOTS):
        raise RuntimeError("global Real XI assignment is incomplete or duplicated")
    return selected


def main() -> None:
    if not GATE.exists():
        raise RuntimeError("run build_definitive_experiment_gate.py first")
    gate = load_json(GATE)
    if not gate.get("design_gate_passed", False):
        raise RuntimeError(f"definitive team construction is blocked: {gate.get('design_blockers')}")
    if not CANDIDATES.exists():
        raise RuntimeError(f"missing final reviewed candidate-role table: {CANDIDATES}")

    frame = validate(pd.read_csv(CANDIDATES, low_memory=False)).reset_index(drop=True)
    for role in SLOTS:
        mask = frame.final_role.eq(role)
        frame.loc[mask, "adjusted_role_score"] = role_score(frame.loc[mask], role)
    real_selected = global_real_xi(frame)
    real_rows = []
    for winner in real_selected.itertuples(index=False):
        real_rows.append({
            "slot": winner.final_role,
            "player_id": int(winner.player_id),
            "player_name": str(winner.player_name),
            "world_cup_team": getattr(winner, "world_cup_team", None),
            "minutes": float(winner.exact_window_total_minutes),
            "family_minutes": float(winner.family_minutes),
            "family_share": float(winner.family_share),
            "adjusted_role_score": float(winner.adjusted_role_score),
            "conservative_score": float(winner.conservative_score_final),
            "uncertainty": float(winner.uncertainty),
            "overall": float(winner.overall_final),
            **{metric: float(getattr(winner, metric)) for metric in DIMENSIONS},
        })
    real = pd.DataFrame(real_rows)

    generator_frame = frame.rename(columns={"final_role": "generator_role"}).copy()
    agents = build_ai_xi(
        generator_frame,
        "generator_role",
        ROLE_WEIGHTS,
        seed=20260720,
        candidates_per_role=50_000,
        minimum_pool=20,
    )
    ai_rows = []
    for agent in agents:
        role_pool = generator_frame.loc[
            generator_frame.generator_role.eq(agent.role)
        ].copy()
        numeric_profile = role_pool[PROFILE_METRICS].apply(pd.to_numeric, errors="coerce")
        clean_positions = numeric_profile.dropna().index.to_list()
        donor_records = [role_pool.loc[clean_positions[position]] for position in agent.donor_rows]
        donor_ids = [int(record.player_id) for record in donor_records]
        uncertainty = sum(
            weight * float(record.uncertainty)
            for weight, record in zip(agent.donor_weights, donor_records, strict=True)
        )
        annual_minutes = sum(
            weight * float(record.exact_window_total_minutes)
            for weight, record in zip(agent.donor_weights, donor_records, strict=True)
        )
        metrics = dict(agent.metrics)
        ai_rows.append({
            "slot": agent.role,
            "agent_id": f"AI-{agent.role}-20260720",
            "utility": agent.utility,
            "mahalanobis_distance": agent.mahalanobis_distance,
            "nearest_real_distance": agent.nearest_real_distance,
            "seed": agent.seed,
            "candidates_evaluated": agent.candidates_evaluated,
            "donor_player_ids": "|".join(map(str, donor_ids)),
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
    manifest = {
        "status": "definitive_teams_frozen",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "partial_identification": False,
        "master_seed": 20260720,
        "real_xi_sha256": sha256(real_path),
        "ai_xi_sha256": sha256(ai_path),
        "candidate_role_table_sha256": sha256(CANDIDATES),
        "real_players": int(len(real)),
        "ai_agents": int(len(ai)),
        "slots": SLOTS,
        "real_selection": {
            "method": "exact dynamic-programming maximum-weight bipartite assignment",
            "one_player_per_slot": True,
            "one_slot_per_player": True,
            "objective": "maximum frozen total role-specific adjusted score",
            "tiebreakers": [
                "higher total conservative score", "higher total annual minutes",
                "higher total positional-family minutes", "lower ordered player_id vector",
            ],
        },
        "ai_generation": {
            "method": "whole-vector empirical convex combinations",
            "profile_metrics": PROFILE_METRICS,
            "candidates_per_role": 50_000,
            "minimum_role_pool": 20,
            "generator_has_match_engine_access": False,
            "generator_has_opponent_access": False,
        },
    }
    canonical_json(OUT / "team_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
