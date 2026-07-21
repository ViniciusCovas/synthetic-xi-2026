#!/usr/bin/env python3
"""Run the frozen 100,000-match externally contextualized v2 experiment."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from simulator.calibrated_core import CalibratedConfig, CalibratedMatchSimulator, CalibrationTargets
from simulator.engine import PlayerProfile, TeamProfile, ROLE_ORDER

TEAM_ROOT = Path("data/definitive_experiment_v2")
AUDIT_ROOT = Path("data/audits/external_validity_v2")
OUT = TEAM_ROOT / "final_simulation"
REAL_CSV = TEAM_ROOT / "real_xi.csv"
AI_CSV = TEAM_ROOT / "ai_xi.csv"
TEAM_MANIFEST = TEAM_ROOT / "team_manifest.json"
GATE = AUDIT_ROOT / "final_gate_status.json"
DIRECTION = AUDIT_ROOT / "independent_direction_check.json"
VALIDATION = AUDIT_ROOT / "validation_status.json"
ENGINE_FILE = Path("simulator/calibrated_core.py")
PROFILE_FILE = Path("simulator/engine.py")
MASTER_SEED = 20260721
PAIRS = 50_000
TOTAL_MATCHES = PAIRS * 2
SLOT_TO_ENGINE = {
    "GK": "GK", "RCB": "CB1", "LCB": "CB2", "RB": "FB1", "LB": "FB2",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W1", "LW": "W2", "ST": "ST",
}
PROFILE_METRICS = ["overall", "build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_ci(values: list[float], z: float = 1.959963984540054) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    mean = float(array.mean())
    se = float(array.std(ddof=1) / math.sqrt(len(array))) if len(array) > 1 else 0.0
    return {"mean": mean, "standard_error": se, "ci95_low": mean - z * se, "ci95_high": mean + z * se, "clusters": int(len(array))}


def validate_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    required = {"slot", "minutes", "uncertainty", *PROFILE_METRICS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"{label} missing columns: {missing}")
    frame = frame.copy()
    if len(frame) != 11 or set(frame.slot.astype(str)) != set(SLOT_TO_ENGINE):
        raise RuntimeError(f"{label} does not contain the frozen eleven slots")
    for column in required - {"slot"}:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[list(required - {"slot"})].isna().any().any():
        raise RuntimeError(f"{label} has incomplete profile values")
    return frame


def build_team(frame: pd.DataFrame, name: str, synthetic: bool) -> TeamProfile:
    players = []
    for row in frame.itertuples(index=False):
        engine_role = SLOT_TO_ENGINE[str(row.slot)]
        identifier = getattr(row, "agent_id", None) if synthetic else getattr(row, "player_id", None)
        player_name = getattr(row, "agent_id", None) if synthetic else getattr(row, "player_name", None)
        players.append(PlayerProfile(
            player_id=str(identifier), name=str(player_name), role=engine_role,
            minutes=float(row.minutes), uncertainty=float(row.uncertainty), synthetic=synthetic,
            **{metric: float(getattr(row, metric)) for metric in PROFILE_METRICS},
        ))
    by_role = {player.role: player for player in players}
    return TeamProfile(name=name, players=tuple(by_role[role] for role in ROLE_ORDER), tempo=0.50, press=0.50, directness=0.50)


def calibration_targets() -> CalibrationTargets:
    return CalibrationTargets(
        source_match_count=94,
        mean_goals_per_match=2.9148936170212765,
        mean_shots_per_match=18.094871004214205,
        mean_shots_on_target_per_match=8.378558947476618,
        zero_zero_rate=0.07446808510638298,
        home_win_rate=0.40,
        draw_rate=0.25,
        away_win_rate=0.35,
    )


def main() -> None:
    for path in [REAL_CSV, AI_CSV, TEAM_MANIFEST, GATE, DIRECTION, VALIDATION, ENGINE_FILE, PROFILE_FILE]:
        if not path.exists():
            raise RuntimeError(f"missing frozen v2 input: {path}")
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    manifest = json.loads(TEAM_MANIFEST.read_text(encoding="utf-8"))
    direction = json.loads(DIRECTION.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if not gate.get("v2_final_gate_passed", False) or not gate.get("v2_simulation_allowed", False):
        raise RuntimeError(f"v2 final gate is closed: {gate.get('blockers')}")
    if not validation.get("external_validity_v2_validation_passed", False):
        raise RuntimeError("external-validity validation is not passing")
    if manifest.get("real_xi_sha256") != sha256(REAL_CSV) or manifest.get("ai_xi_sha256") != sha256(AI_CSV):
        raise RuntimeError("frozen v2 team hash mismatch")
    if not direction.get("independent_direction_check_passed", False):
        raise RuntimeError("independent v2 direction check has not passed")
    if direction.get("real_xi_sha256") != sha256(REAL_CSV) or direction.get("ai_xi_sha256") != sha256(AI_CSV):
        raise RuntimeError("direction check refers to different v2 hashes")

    real = build_team(validate_frame(pd.read_csv(REAL_CSV), "Real XI v2"), "Real XI v2", False)
    ai = build_team(validate_frame(pd.read_csv(AI_CSV), "AI XI v2"), "AI XI v2", True)
    targets = calibration_targets()
    rng = np.random.default_rng(MASTER_SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    raw_path = OUT / "matches.csv.gz"
    fields = ["pair_id", "orientation", "seed", "real_goals", "ai_goals", "real_xg", "ai_xg", "real_shots", "ai_shots", "real_shots_on_target", "ai_shots_on_target", "real_possessions", "ai_possessions"]

    outcomes = Counter()
    scorelines = Counter()
    orientation_outcomes = {"real_nominal_home": Counter(), "ai_nominal_home": Counter()}
    sums = Counter()
    pair_real_win: list[float] = []
    pair_draw: list[float] = []
    pair_ai_win: list[float] = []
    pair_goal_margin: list[float] = []
    pair_xg_margin: list[float] = []
    pair_orientation_goal_effect: list[float] = []

    with gzip.open(raw_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for pair_id in range(PAIRS):
            seed = int(rng.integers(0, 2**32 - 1))
            first = CalibratedMatchSimulator(real, ai, targets, CalibratedConfig(seed=seed, home_advantage=0.0)).simulate(False)
            second = CalibratedMatchSimulator(ai, real, targets, CalibratedConfig(seed=seed, home_advantage=0.0)).simulate(False)
            rows = [
                ("real_nominal_home", first.home_goals, first.away_goals, first.home_xg, first.away_xg, first.home_shots, first.away_shots, first.home_shots_on_target, first.away_shots_on_target, first.home_possessions, first.away_possessions),
                ("ai_nominal_home", second.away_goals, second.home_goals, second.away_xg, second.home_xg, second.away_shots, second.home_shots, second.away_shots_on_target, second.home_shots_on_target, second.away_possessions, second.home_possessions),
            ]
            pair_values = []
            for orientation, rg, ag, rxg, axg, rs, ass, rsot, asot, rp, ap in rows:
                outcome = "real_win" if rg > ag else "ai_win" if ag > rg else "draw"
                outcomes[outcome] += 1
                orientation_outcomes[orientation][outcome] += 1
                scorelines[(int(rg), int(ag))] += 1
                sums.update({"real_goals": rg, "ai_goals": ag, "real_xg": rxg, "ai_xg": axg, "real_shots": rs, "ai_shots": ass, "real_sot": rsot, "ai_sot": asot, "real_possessions": rp, "ai_possessions": ap})
                pair_values.append({"real_win": float(rg > ag), "draw": float(rg == ag), "ai_win": float(ag > rg), "goal_margin": float(rg - ag), "xg_margin": float(rxg - axg)})
                writer.writerow({"pair_id": pair_id, "orientation": orientation, "seed": seed, "real_goals": rg, "ai_goals": ag, "real_xg": rxg, "ai_xg": axg, "real_shots": rs, "ai_shots": ass, "real_shots_on_target": rsot, "ai_shots_on_target": asot, "real_possessions": rp, "ai_possessions": ap})
            pair_real_win.append(sum(value["real_win"] for value in pair_values) / 2)
            pair_draw.append(sum(value["draw"] for value in pair_values) / 2)
            pair_ai_win.append(sum(value["ai_win"] for value in pair_values) / 2)
            pair_goal_margin.append(sum(value["goal_margin"] for value in pair_values) / 2)
            pair_xg_margin.append(sum(value["xg_margin"] for value in pair_values) / 2)
            pair_orientation_goal_effect.append(pair_values[0]["goal_margin"] - pair_values[1]["goal_margin"])

    probabilities = {name: outcomes[name] / TOTAL_MATCHES for name in ["real_win", "draw", "ai_win"]}
    paired = {
        "real_win_probability": mean_ci(pair_real_win),
        "draw_probability": mean_ci(pair_draw),
        "ai_win_probability": mean_ci(pair_ai_win),
        "real_minus_ai_win_probability": mean_ci([r - a for r, a in zip(pair_real_win, pair_ai_win, strict=True)]),
        "real_minus_ai_goal_margin": mean_ci(pair_goal_margin),
        "real_minus_ai_xg_margin": mean_ci(pair_xg_margin),
        "orientation_goal_effect": mean_ci(pair_orientation_goal_effect),
    }
    orientation_summary = {
        orientation: {name: counter[name] / PAIRS for name in ["real_win", "draw", "ai_win"]}
        for orientation, counter in orientation_outcomes.items()
    }
    direction_final = "REAL_XI" if probabilities["real_win"] > probabilities["ai_win"] else "AI_XI" if probabilities["ai_win"] > probabilities["real_win"] else "TIE"
    direction_consistent = direction_final == direction.get("directional_prior")
    summary = {
        "status": "v2_definitive_100000_match_simulation_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_version": "v2_external_validity",
        "matches": TOTAL_MATCHES,
        "paired_orientations": PAIRS,
        "matches_per_orientation": PAIRS,
        "neutral_home_advantage": 0.0,
        "master_seed": MASTER_SEED,
        "common_random_seed_within_orientation_pairs": True,
        "real_xi_sha256": sha256(REAL_CSV),
        "ai_xi_sha256": sha256(AI_CSV),
        "team_manifest_sha256": sha256(TEAM_MANIFEST),
        "final_gate_sha256": sha256(GATE),
        "validation_sha256": sha256(VALIDATION),
        "direction_check_sha256": sha256(DIRECTION),
        "calibrated_core_sha256": sha256(ENGINE_FILE),
        "profile_engine_sha256": sha256(PROFILE_FILE),
        "raw_match_log_sha256": sha256(raw_path),
        "outcome_counts": dict(outcomes),
        "outcome_probabilities": probabilities,
        "paired_cluster_inference": paired,
        "orientation_probabilities": orientation_summary,
        "means_per_match": {key: value / TOTAL_MATCHES for key, value in sums.items()},
        "most_common_scorelines_real_ai": [{"real_goals": score[0], "ai_goals": score[1], "count": count, "probability": count / TOTAL_MATCHES} for score, count in scorelines.most_common(20)],
        "independent_directional_prior": direction.get("directional_prior"),
        "final_event_simulation_direction": direction_final,
        "direction_consistent_with_independent_model": direction_consistent,
        "v1_result_status": "preserved diagnostic; invalidated for global-best-XI claim",
        "claim_boundary": "Conditional on the frozen 2025-2026 data, reviewed slots, goalkeeper proxy, results-based Elo context model, synthetic generator and calibrated event engine; not an absolute physical-match prediction.",
        "raw_match_log": str(raw_path),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    win_difference = paired["real_minus_ai_win_probability"]
    goal_margin = paired["real_minus_ai_goal_margin"]
    readme = [
        "# Definitive externally contextualized v2 simulation", "",
        f"Matches: **{TOTAL_MATCHES:,}**", f"Master seed: `{MASTER_SEED}`", "",
        "| Outcome | Probability | pair-cluster 95% CI |", "|---|---:|---:|",
        f"| Real XI win | {probabilities['real_win']:.4%} | {paired['real_win_probability']['ci95_low']:.4%}–{paired['real_win_probability']['ci95_high']:.4%} |",
        f"| Draw | {probabilities['draw']:.4%} | {paired['draw_probability']['ci95_low']:.4%}–{paired['draw_probability']['ci95_high']:.4%} |",
        f"| AI XI win | {probabilities['ai_win']:.4%} | {paired['ai_win_probability']['ci95_low']:.4%}–{paired['ai_win_probability']['ci95_high']:.4%} |",
        "",
        f"Real-minus-AI win-probability difference: **{win_difference['mean']:.4%}** ({win_difference['ci95_low']:.4%}–{win_difference['ci95_high']:.4%}).",
        f"Mean goal margin, Real − AI: **{goal_margin['mean']:.5f}** ({goal_margin['ci95_low']:.5f}–{goal_margin['ci95_high']:.5f}).",
        f"Independent direction: **{direction.get('directional_prior')}**.",
        f"Event-simulation direction: **{direction_final}**.",
        f"Direction consistent: **{direction_consistent}**.", "",
        "The v1 simulation remains preserved only as a diagnostic because its global-player ranking lacked a discriminative goalkeeper model and explicit competition/opponent context.",
    ]
    (OUT / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
