#!/usr/bin/env python3
"""Independent post-freeze directional check for the definitive Real XI vs AI XI.

This check is separate from the event simulator. It maps frozen team profiles to
neutral-site Poisson scoring intensities through a transparent role-balanced model,
verifies team hashes, and tests direction stability under role jackknifing and parameter
sensitivity. It records a directional prior; it does not replace the final 100,000-match
simulation.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pandas as pd

ROOT = Path("data/definitive_experiment_v1")
REAL = ROOT / "real_xi.csv"
AI = ROOT / "ai_xi.csv"
MANIFEST = ROOT / "team_manifest.json"
OUT = Path("data/audits/engine_validation_v1/independent_direction_check.json")
SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
BASE_GOALS_PER_TEAM = 1.35
BETA = 2.0

ATTACK_METRIC_WEIGHTS: dict[str, dict[str, float]] = {
    "GK": {"build_up": .60, "retention": .40},
    "RB": {"progression": .35, "creation": .25, "build_up": .20, "finishing": .10, "retention": .10},
    "LB": {"progression": .35, "creation": .25, "build_up": .20, "finishing": .10, "retention": .10},
    "RCB": {"build_up": .50, "progression": .20, "retention": .30},
    "LCB": {"build_up": .50, "progression": .20, "retention": .30},
    "DM": {"build_up": .30, "progression": .25, "creation": .15, "retention": .30},
    "CM": {"build_up": .20, "progression": .25, "creation": .25, "retention": .20, "finishing": .10},
    "AM": {"creation": .35, "progression": .25, "finishing": .25, "retention": .15},
    "RW": {"progression": .30, "creation": .30, "finishing": .30, "duels": .10},
    "LW": {"progression": .30, "creation": .30, "finishing": .30, "duels": .10},
    "ST": {"finishing": .55, "creation": .15, "progression": .10, "duels": .15, "retention": .05},
}
DEFENCE_METRIC_WEIGHTS: dict[str, dict[str, float]] = {
    "GK": {"goalkeeping": .75, "retention": .15, "build_up": .10},
    "RB": {"defending": .35, "duels": .25, "progression": .15, "retention": .15, "build_up": .10},
    "LB": {"defending": .35, "duels": .25, "progression": .15, "retention": .15, "build_up": .10},
    "RCB": {"defending": .45, "duels": .35, "retention": .10, "build_up": .10},
    "LCB": {"defending": .45, "duels": .35, "retention": .10, "build_up": .10},
    "DM": {"defending": .40, "duels": .30, "retention": .20, "build_up": .10},
    "CM": {"defending": .25, "duels": .20, "retention": .30, "build_up": .15, "progression": .10},
    "AM": {"defending": .10, "duels": .15, "retention": .35, "build_up": .15, "progression": .25},
    "RW": {"defending": .10, "duels": .20, "retention": .25, "progression": .25, "build_up": .10, "creation": .10},
    "LW": {"defending": .10, "duels": .20, "retention": .25, "progression": .25, "build_up": .10, "creation": .10},
    "ST": {"duels": .25, "retention": .25, "progression": .20, "creation": .15, "defending": .05, "build_up": .10},
}
ATTACK_ROLE_WEIGHTS = {"GK": .02, "RB": .07, "RCB": .03, "LCB": .03, "LB": .07, "DM": .08, "CM": .12, "AM": .16, "RW": .17, "LW": .17, "ST": .22}
DEFENCE_ROLE_WEIGHTS = {"GK": .25, "RB": .08, "RCB": .14, "LCB": .14, "LB": .08, "DM": .12, "CM": .07, "AM": .03, "RW": .025, "LW": .025, "ST": .02}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def role_composite(row: pd.Series, weights: Mapping[str, Mapping[str, float]]) -> float:
    return sum(float(row[metric]) * weight for metric, weight in weights[str(row.slot)].items())


def team_scores(frame: pd.DataFrame, excluded_slot: str | None = None) -> tuple[float, float]:
    current = frame.loc[frame.slot.ne(excluded_slot)].copy() if excluded_slot else frame.copy()
    current["attack_component"] = current.apply(lambda row: role_composite(row, ATTACK_METRIC_WEIGHTS), axis=1)
    current["defence_component"] = current.apply(lambda row: role_composite(row, DEFENCE_METRIC_WEIGHTS), axis=1)
    attack_weights = {role: weight for role, weight in ATTACK_ROLE_WEIGHTS.items() if role != excluded_slot}
    defence_weights = {role: weight for role, weight in DEFENCE_ROLE_WEIGHTS.items() if role != excluded_slot}
    attack = sum(float(current.loc[current.slot.eq(role), "attack_component"].iloc[0]) * weight for role, weight in attack_weights.items()) / sum(attack_weights.values())
    defence = sum(float(current.loc[current.slot.eq(role), "defence_component"].iloc[0]) * weight for role, weight in defence_weights.items()) / sum(defence_weights.values())
    return attack, defence


def intensities(real: pd.DataFrame, ai: pd.DataFrame, beta: float, base: float, excluded_slot: str | None = None) -> tuple[float, float]:
    real_attack, real_defence = team_scores(real, excluded_slot)
    ai_attack, ai_defence = team_scores(ai, excluded_slot)
    return base * math.exp(beta * (real_attack - ai_defence)), base * math.exp(beta * (ai_attack - real_defence))


def poisson_vector(rate: float, maximum: int = 12) -> list[float]:
    values = [math.exp(-rate) * rate**goals / math.factorial(goals) for goals in range(maximum + 1)]
    values[-1] += 1.0 - sum(values)
    return values


def result_probabilities(real_lambda: float, ai_lambda: float) -> dict[str, float]:
    real = poisson_vector(real_lambda)
    ai = poisson_vector(ai_lambda)
    real_win = sum(real[i] * ai[j] for i in range(len(real)) for j in range(len(ai)) if i > j)
    draw = sum(real[i] * ai[i] for i in range(len(real)))
    return {"real_win": real_win, "draw": draw, "ai_win": 1.0 - real_win - draw}


def validate_team(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    required = {"slot", "overall", "build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"{label} is missing columns: {missing}")
    frame = frame.copy()
    if len(frame) != 11 or set(frame.slot.astype(str)) != set(SLOTS):
        raise RuntimeError(f"{label} does not contain exactly the eleven frozen slots")
    for column in required - {"slot"}:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[list(required - {"slot"})].isna().any().any():
        raise RuntimeError(f"{label} contains incomplete profile metrics")
    return frame


def main() -> None:
    for path in (REAL, AI, MANIFEST):
        if not path.exists():
            raise RuntimeError(f"missing frozen-team input: {path}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    hash_pass = bool(manifest.get("status") == "definitive_teams_frozen" and manifest.get("real_xi_sha256") == sha256(REAL) and manifest.get("ai_xi_sha256") == sha256(AI))
    real = validate_team(pd.read_csv(REAL), "Real XI")
    ai = validate_team(pd.read_csv(AI), "AI XI")

    real_attack, real_defence = team_scores(real)
    ai_attack, ai_defence = team_scores(ai)
    real_lambda, ai_lambda = intensities(real, ai, BETA, BASE_GOALS_PER_TEAM)
    probabilities = result_probabilities(real_lambda, ai_lambda)
    margin = real_lambda - ai_lambda
    direction = "REAL_XI" if margin > 0 else "AI_XI" if margin < 0 else "TIE"

    jackknife = []
    for slot in SLOTS:
        real_rate, ai_rate = intensities(real, ai, BETA, BASE_GOALS_PER_TEAM, slot)
        current_margin = real_rate - ai_rate
        current_direction = "REAL_XI" if current_margin > 0 else "AI_XI" if current_margin < 0 else "TIE"
        jackknife.append({"excluded_slot": slot, "real_expected_goals": real_rate, "ai_expected_goals": ai_rate, "expected_goal_margin": current_margin, "direction": current_direction})
    jackknife_agreement = sum(row["direction"] == direction for row in jackknife) / len(jackknife)

    sensitivity = []
    for beta in (1.0, 1.5, 2.0, 2.5, 3.0):
        for base in (1.20, 1.35, 1.50):
            real_rate, ai_rate = intensities(real, ai, beta, base)
            current_margin = real_rate - ai_rate
            current_direction = "REAL_XI" if current_margin > 0 else "AI_XI" if current_margin < 0 else "TIE"
            sensitivity.append({"beta": beta, "base_goals_per_team": base, "real_expected_goals": real_rate, "ai_expected_goals": ai_rate, "expected_goal_margin": current_margin, "direction": current_direction})
    sensitivity_agreement = sum(row["direction"] == direction for row in sensitivity) / len(sensitivity)

    plausible_rates = 0.20 <= real_lambda <= 4.50 and 0.20 <= ai_lambda <= 4.50
    nondegenerate = direction != "TIE" and abs(margin) >= 0.005
    passed = bool(hash_pass and plausible_rates and nondegenerate and jackknife_agreement >= 0.90 and sensitivity_agreement == 1.0)
    payload = {
        "status": "independent_post_freeze_direction_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": "transparent neutral-site independent Poisson goal model",
        "model_is_separate_from_event_simulator": True,
        "event_simulation_results_used": False,
        "teams_frozen_and_hashed": hash_pass,
        "real_xi_sha256": sha256(REAL),
        "ai_xi_sha256": sha256(AI),
        "parameters": {"base_goals_per_team": BASE_GOALS_PER_TEAM, "beta": BETA},
        "team_scores": {"real_attack": real_attack, "real_defence": real_defence, "ai_attack": ai_attack, "ai_defence": ai_defence},
        "expected_goals": {"real_xi": real_lambda, "ai_xi": ai_lambda, "margin_real_minus_ai": margin},
        "result_probabilities": probabilities,
        "directional_prior": direction,
        "jackknife": jackknife,
        "jackknife_direction_agreement": jackknife_agreement,
        "parameter_sensitivity": sensitivity,
        "parameter_sensitivity_direction_agreement": sensitivity_agreement,
        "plausible_goal_rates": plausible_rates,
        "nondegenerate_direction": nondegenerate,
        "independent_direction_check_passed": passed,
        "interpretation": "This is a directional prior for comparison with the final event simulation; it is not a match result and does not replace the 100,000-match experiment.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
