#!/usr/bin/env python3
"""Build and hash exactly one Real XI and one AI XI after the design gate passes.

The script is intentionally inert while ontology, blind-review, coverage or role-pool
requirements remain open. It never reads exploratory match outcomes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from simulator.ai_xi_generator import build_ai_xi

GATE = Path("data/audits/definitive_experiment_v1/gate_status.json")
PLAYERS = Path("data/audits/position_ontology_v3/final_player_roles.csv")
OUT = Path("data/definitive_experiment_v1")
SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMENSIONS = [
    "build_up", "progression", "creation", "finishing", "defending", "duels",
    "retention", "goalkeeping",
]
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
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
    weights = ROLE_WEIGHTS[role]
    output = pd.Series(0.0, index=frame.index)
    for metric, weight in weights.items():
        output = output + pd.to_numeric(frame[metric], errors="coerce") * weight
    return output


def validate(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "audited_role": "final_role",
        "overall_audited": "overall_final",
        "conservative_score_audited": "conservative_score_final",
        "formation_role_stability_minutes": "role_stability_final",
        "formation_precise_minutes": "role_minutes_final",
    }
    for source, target in aliases.items():
        if target not in frame and source in frame:
            frame[target] = frame[source]
    required = {
        "player_id", "player_name", "final_role", "minutes_num", "role_minutes_final",
        "role_stability_final", "coverage_pass_90pct", "human_review_resolved",
        "overall_final", "conservative_score_final", *DIMENSIONS,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"final_player_roles.csv is missing required columns: {missing}")
    frame = frame.copy()
    numeric_columns = [
        "player_id", "minutes_num", "role_minutes_final", "role_stability_final",
        "overall_final", "conservative_score_final", *DIMENSIONS,
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["player_id", "final_role", "overall_final"])
    frame["player_id"] = frame.player_id.astype(int)
    frame = frame.sort_values(
        ["player_id", "role_minutes_final", "role_stability_final"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id")
    eligible = (
        frame.final_role.isin(SLOTS)
        & frame.minutes_num.ge(1800)
        & frame.role_minutes_final.ge(900)
        & frame.role_stability_final.ge(0.60)
        & truth(frame.coverage_pass_90pct)
        & truth(frame.human_review_resolved)
    )
    frame = frame.loc[eligible].copy()
    counts = frame.groupby("final_role").player_id.nunique().reindex(SLOTS, fill_value=0)
    failures = counts.loc[counts.lt(20)].to_dict()
    if failures:
        raise RuntimeError(f"minimum role pool not satisfied: {failures}")
    return frame


def main() -> None:
    if not GATE.exists():
        raise RuntimeError("run build_definitive_experiment_gate.py first")
    gate = load_json(GATE)
    if not gate.get("design_gate_passed", False):
        raise RuntimeError(f"definitive team construction is blocked: {gate.get('design_blockers')}")
    if not PLAYERS.exists():
        raise RuntimeError(f"missing promoted ontology-v3 player table: {PLAYERS}")

    frame = validate(pd.read_csv(PLAYERS, low_memory=False))
    for role in SLOTS:
        frame.loc[frame.final_role.eq(role), "adjusted_role_score"] = role_score(
            frame.loc[frame.final_role.eq(role)], role
        )

    real_rows = []
    used: set[int] = set()
    for role in SLOTS:
        candidates = frame.loc[frame.final_role.eq(role) & ~frame.player_id.isin(used)].copy()
        candidates = candidates.sort_values(
            [
                "adjusted_role_score", "conservative_score_final", "role_minutes_final",
                "role_stability_final", "player_id",
            ],
            ascending=[False, False, False, False, True],
        )
        if candidates.empty:
            raise RuntimeError(f"no unused candidate for {role}")
        winner = candidates.iloc[0]
        used.add(int(winner.player_id))
        real_rows.append({
            "slot": role,
            "player_id": int(winner.player_id),
            "player_name": str(winner.player_name),
            "world_cup_team": winner.get("world_cup_team"),
            "minutes": float(winner.minutes_num),
            "role_minutes": float(winner.role_minutes_final),
            "role_stability": float(winner.role_stability_final),
            "adjusted_role_score": float(winner.adjusted_role_score),
            "conservative_score": float(winner.conservative_score_final),
            **{metric: float(winner[metric]) for metric in DIMENSIONS},
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
        ai_rows.append({
            "slot": agent.role,
            "agent_id": f"AI-{agent.role}-20260720",
            "utility": agent.utility,
            "mahalanobis_distance": agent.mahalanobis_distance,
            "nearest_real_distance": agent.nearest_real_distance,
            "seed": agent.seed,
            "candidates_evaluated": agent.candidates_evaluated,
            "donor_player_ids": "|".join(
                str(int(generator_frame.iloc[index].player_id)) for index in agent.donor_rows
            ),
            "donor_weights": "|".join(f"{value:.12f}" for value in agent.donor_weights),
            **agent.metrics,
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
        "promoted_player_table_sha256": sha256(PLAYERS),
        "real_players": int(len(real)),
        "ai_agents": int(len(ai)),
        "slots": SLOTS,
        "selection_tiebreakers": [
            "adjusted_role_score", "conservative_score_final", "role_minutes_final",
            "role_stability_final", "lower_player_id",
        ],
        "ai_generation": {
            "method": "whole-vector empirical convex combinations",
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
