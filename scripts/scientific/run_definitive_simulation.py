#!/usr/bin/env python3
"""Run the frozen 100,000-match definitive Real XI versus AI XI experiment."""
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

TEAM_ROOT = Path("data/definitive_experiment_v1")
AUDIT_ROOT = Path("data/audits/definitive_experiment_v1")
ENGINE_ROOT = Path("data/audits/engine_validation_v1")
OUT = Path("data/definitive_experiment_v1/final_simulation")
REAL_CSV = TEAM_ROOT / "real_xi.csv"
AI_CSV = TEAM_ROOT / "ai_xi.csv"
TEAM_MANIFEST = TEAM_ROOT / "team_manifest.json"
GATE = AUDIT_ROOT / "gate_status.json"
DIRECTION = ENGINE_ROOT / "independent_direction_check.json"
ENGINE_FILE = Path("simulator/calibrated_core.py")
PROFILE_FILE = Path("simulator/engine.py")
MASTER_SEED = 20260720
PAIRS = 50_000
TOTAL_MATCHES = PAIRS * 2
SLOT_TO_ENGINE = {
    "GK": "GK", "RCB": "CB1", "LCB": "CB2", "RB": "FB1", "LB": "FB2",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W1", "LW": "W2", "ST": "ST",
}
PROFILE_METRICS = ["overall", "build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def mean_ci(values: list[float], z: float = 1.959963984540054) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    mean = float(array.mean())
    se = float(array.std(ddof=1) / math.sqrt(len(array))) if len(array) > 1 else 0.0
    return {"mean": mean, "standard_error": se, "ci95_low": mean - z * se, "ci95_high": mean + z * se}


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
    for path in (REAL_CSV, AI_CSV, TEAM_MANIFEST, GATE, DIRECTION, ENGINE_FILE, PROFILE_FILE):
        if not path.exists():
            raise RuntimeError(f"missing frozen input: {path}")
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    if not gate.get("final_experiment_gate_passed", False) or not gate.get("final_simulation_allowed", False):
        raise RuntimeError("final experiment gate is not open")
    manifest = json.loads(TEAM_MANIFEST.read_text(encoding="utf-8"))
    direction = json.loads(DIRECTION.read_text(encoding="utf-8"))
    if manifest.get("real_xi_sha256") != sha256(REAL_CSV) or manifest.get("ai_xi_sha256") != sha256(AI_CSV):
        raise RuntimeError("frozen team hash mismatch")
    if not direction.get("independent_direction_check_passed", False):
        raise RuntimeError("independent post-freeze direction check has not passed")
    if direction.get("real_xi_sha256") != sha256(REAL_CSV) or direction.get("ai_xi_sha256") != sha256(AI_CSV):
        raise RuntimeError("direction check refers to different team hashes")

    real = build_team(validate_frame(pd.read_csv(REAL_CSV), "Real XI"), "Real XI", False)
    ai = build_team(validate_frame(pd.read_csv(AI_CSV), "AI XI"), "AI XI", True)
    targets = calibration_targets()
    rng = np.random.default_rng(MASTER_SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    raw_path = OUT / "matches.csv.gz"
    fields = ["pair_id", "orientation", "seed", "real_goals", "ai_goals", "real_xg", "ai_xg", "real_shots", "ai_shots", "real_shots_on_target", "ai_shots_on_target", "real_possessions", "ai_possessions"]

    outcomes = Counter()
    scorelines = Counter()
    orientation_outcomes = {"real_nominal_home": Counter(), "ai_nominal_home": Counter()}
    sums = Counter()
    goal_margins: list[float] = []
    xg_margins: list[float] = []
    pair_orientation_goal_effects: list[float] = []

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
            pair_margins = []
            for orientation, rg, ag, rxg, axg, rs, ass, rsot, asot, rp, ap in rows:
                outcome = "real_win" if rg > ag else "ai_win" if ag > rg else "draw"
                outcomes[outcome] += 1
                orientation_outcomes[orientation][outcome] += 1
                scorelines[(int(rg), int(ag))] += 1
                sums.update({"real_goals": rg, "ai_goals": ag, "real_xg": rxg, "ai_xg": axg, "real_shots": rs, "ai_shots": ass, "real_sot": rsot, "ai_sot": asot, "real_possessions": rp, "ai_possessions": ap})
                goal_margins.append(float(rg - ag)); xg_margins.append(float(rxg - axg)); pair_margins.append(float(rg - ag))
                writer.writerow({"pair_id": pair_id, "orientation": orientation, "seed": seed, "real_goals": rg, "ai_goals": ag, "real_xg": rxg, "ai_xg": axg, "real_shots": rs, "ai_shots": ass, "real_shots_on_target": rsot, "ai_shots_on_target": asot, "real_possessions": rp, "ai_possessions": ap})
            pair_orientation_goal_effects.append(pair_margins[0] - pair_margins[1])

    probabilities = {name: outcomes[name] / TOTAL_MATCHES for name in ("real_win", "draw", "ai_win")}
    intervals = {name: wilson(outcomes[name], TOTAL_MATCHES) for name in probabilities}
    orientation_summary = {
        orientation: {name: counter[name] / PAIRS for name in ("real_win", "draw", "ai_win")}
        for orientation, counter in orientation_outcomes.items()
    }
    main_direction = "REAL_XI" if probabilities["real_win"] > probabilities["ai_win"] else "AI_XI" if probabilities["ai_win"] > probabilities["real_win"] else "TIE"
    direction_consistent = main_direction == direction.get("directional_prior")
    summary = {
        "status": "definitive_100000_match_simulation_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "matches": TOTAL_MATCHES,
        "paired_orientations": PAIRS,
        "matches_per_orientation": PAIRS,
        "neutral_home_advantage": 0.0,
        "master_seed": MASTER_SEED,
        "common_random_seed_within_orientation_pairs": True,
        "real_xi_sha256": sha256(REAL_CSV),
        "ai_xi_sha256": sha256(AI_CSV),
        "team_manifest_sha256": sha256(TEAM_MANIFEST),
        "calibrated_core_sha256": sha256(ENGINE_FILE),
        "profile_engine_sha256": sha256(PROFILE_FILE),
        "raw_match_log_sha256": sha256(raw_path),
        "outcome_counts": dict(outcomes),
        "outcome_probabilities": probabilities,
        "outcome_probability_ci95": intervals,
        "orientation_probabilities": orientation_summary,
        "means_per_match": {key: value / TOTAL_MATCHES for key, value in sums.items()},
        "goal_margin_real_minus_ai": mean_ci(goal_margins),
        "xg_margin_real_minus_ai": mean_ci(xg_margins),
        "paired_orientation_goal_effect": mean_ci(pair_orientation_goal_effects),
        "most_common_scorelines_real_ai": [{"real_goals": score[0], "ai_goals": score[1], "count": count, "probability": count / TOTAL_MATCHES} for score, count in scorelines.most_common(20)],
        "independent_directional_prior": direction.get("directional_prior"),
        "final_event_simulation_direction": main_direction,
        "direction_consistent_with_independent_model": direction_consistent,
        "claim_boundary": "A probabilistic comparison under the frozen model and profiles; not a physical match prediction.",
        "raw_match_log": str(raw_path),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = [
        "# Definitive Real XI vs AI XI simulation", "",
        f"Matches: **{TOTAL_MATCHES:,}**", f"Master seed: `{MASTER_SEED}`", "",
        "| Outcome | Probability | 95% CI |", "|---|---:|---:|",
    ]
    for name, label in (("real_win", "Real XI win"), ("draw", "Draw"), ("ai_win", "AI XI win")):
        low, high = intervals[name]
        readme.append(f"| {label} | {probabilities[name]:.4%} | {low:.4%}–{high:.4%} |")
    readme.extend(["", f"Mean goal margin (Real − AI): **{summary['goal_margin_real_minus_ai']['mean']:.4f}**", f"Independent direction: **{direction.get('directional_prior')}**", f"Event-simulation direction: **{main_direction}**", f"Direction consistent: **{direction_consistent}**", "", "This result is conditional on the frozen data, ontology, profiles, generator and calibrated event engine."])
    (OUT / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
