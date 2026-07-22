#!/usr/bin/env python3
"""Build outcome-blind engineering evidence for Complete Final Engine v1.1."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "simulations" / "complete_final_v1_1"
RULE_STATUS = ROOT / "data" / "model_readiness" / "complete_final_rules_fix_v1_1_status.json"
RULE_CONFIG = ROOT / "config" / "complete_final_rules_fix_v1_1.json"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize() -> None:
    subprocess.run(
        [sys.executable, "scripts/install_complete_final_bundle_v1_1.py"],
        cwd=ROOT,
        check=True,
    )
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260731)
    args = parser.parse_args()
    if args.simulations < 500:
        raise SystemExit("v1.1 engineering snapshot requires at least 500 simulations")

    materialize()
    from simulator.calibrated_core import CalibrationTargets
    from simulator.complete_final import CompleteFinalSimulator, FinalConfig
    from simulator.complete_final_monte_carlo import simulate_complete_finals
    from simulator.engine import OUTFIELD_ROLES, ROLE_ORDER, PlayerProfile, TeamProfile

    def team(name: str, edge: float = 0.0, synthetic: bool = False) -> TeamProfile:
        players = []
        for role in ROLE_ORDER:
            base = 0.60 + edge
            players.append(
                PlayerProfile(
                    player_id=f"{name}-{role}",
                    name=f"{name} {role}",
                    role=role,
                    minutes=900,
                    overall=base,
                    build_up=base + (0.02 if role in {"CB1", "CB2", "DM", "CM"} else 0),
                    progression=base,
                    creation=base,
                    finishing=base + (0.04 if role in {"ST", "W1", "W2"} else -0.03),
                    defending=base + (0.05 if role in {"CB1", "CB2", "DM"} else -0.03),
                    duels=base,
                    retention=base,
                    goalkeeping=0.72 + edge if role == "GK" else 0.20,
                    uncertainty=0.025,
                    synthetic=synthetic,
                )
            )
        return TeamProfile(name, tuple(players), tempo=0.55, press=0.54, directness=0.51)

    targets = CalibrationTargets(64, 2.65, 25.0, 8.7, 0.075, 0.39, 0.26, 0.35, 104.0)
    home = team("Neutral A", 0.0, True)
    away = team("Neutral B", 0.0, False)
    config = FinalConfig()

    deterministic_a = CompleteFinalSimulator(home, away, targets, replace(config, seed=args.seed)).simulate(True).as_dict()
    deterministic_b = CompleteFinalSimulator(home, away, targets, replace(config, seed=args.seed)).simulate(True).as_dict()
    reproducible = deterministic_a == deterministic_b

    summary = simulate_complete_finals(
        home,
        away,
        targets,
        simulations=args.simulations,
        seed=args.seed,
        config=config,
        audit_sample_size=min(250, args.simulations),
    )

    rng = np.random.default_rng(args.seed + 1)
    violations: list[str] = []
    regulation_combined_substitutions: list[int] = []
    batch_window_examples = 0
    invariant_samples = min(300, max(100, args.simulations // 4))
    for index in range(invariant_samples):
        result = CompleteFinalSimulator(
            home,
            away,
            targets,
            replace(config, seed=int(rng.integers(0, 2**32 - 1))),
        ).simulate(True)
        for side, stats in (("home", result.home_stats), ("away", result.away_stats)):
            maximum = 6 if result.extra_time_played else 5
            if stats["substitutions"] > maximum:
                violations.append(f"{index}:{side}:substitution_limit")
            if stats["substitution_windows"] > 3:
                violations.append(f"{index}:{side}:regulation_window_limit")
            if stats["extra_time_windows"] > 1:
                violations.append(f"{index}:{side}:extra_time_window_limit")
            if stats["substitutions"] > stats["substitution_windows"] + stats["extra_time_windows"]:
                batch_window_examples += 1
        if not result.extra_time_played:
            regulation_combined_substitutions.append(
                int(result.home_stats["substitutions"] + result.away_stats["substitutions"])
            )
        clocks = [float(event["clock"]) for event in result.timeline]
        if clocks != sorted(clocks):
            violations.append(f"{index}:timeline_non_monotonic")

    observed = {
        "mean_regulation_goals": summary.get("mean_regulation_goals"),
        "mean_regulation_shots": summary.get("mean_regulation_shots"),
        "mean_regulation_shots_on_target": summary.get("mean_regulation_shots_on_target"),
        "regulation_zero_zero_rate": summary.get("regulation_zero_zero_rate"),
        "mean_total_fouls": summary.get("mean_total_fouls"),
        "mean_total_yellows": summary.get("mean_total_yellows"),
        "mean_total_reds": summary.get("mean_total_reds"),
        "mean_total_injuries": summary.get("mean_total_injuries"),
        "mean_total_substitutions": summary.get("mean_total_substitutions"),
        "extra_time_probability": (summary.get("extra_time_probability") or {}).get("estimate"),
        "penalty_shootout_probability": (summary.get("penalty_shootout_probability") or {}).get("estimate"),
    }
    mean_regulation_substitutions = (
        float(np.mean(regulation_combined_substitutions))
        if regulation_combined_substitutions
        else None
    )
    distribution_gate = bool((summary.get("engineering_calibration_gate") or {}).get("passed"))
    rules_status = json.loads(RULE_STATUS.read_text(encoding="utf-8")) if RULE_STATUS.exists() else {}
    structural_checks = {
        "rules_fix_applied": rules_status.get("status") == "complete_final_rules_fix_v1_1_applied",
        "deterministic_reproducibility": reproducible,
        "substitution_and_window_limits": not violations,
        "same_window_batching_observed": batch_window_examples > 0,
        "regulation_uses_declared_five_substitution_capacity": bool(
            mean_regulation_substitutions is not None and mean_regulation_substitutions >= 9.0
        ),
        "regulation_distribution_calibration": distribution_gate,
    }
    engineering_gate_passed = all(structural_checks.values())

    payload = {
        "status": "complete_final_v1_1_engineering_validation_passed" if engineering_gate_passed else "complete_final_v1_1_engineering_validation_failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": "complete_final_v1_1_rules_fix",
        "simulations": args.simulations,
        "seed": args.seed,
        "engineering_gate_passed": engineering_gate_passed,
        "checks": {
            "structural_rules_fix": {
                "passed": all(value for key, value in structural_checks.items() if key != "regulation_distribution_calibration"),
                "checks": structural_checks,
                "invariant_samples": invariant_samples,
                "violations": violations[:25],
                "violation_count": len(violations),
                "batch_window_examples": batch_window_examples,
                "mean_combined_substitutions_regulation_only": mean_regulation_substitutions,
            },
            "regulation_distribution_calibration": {
                "passed": distribution_gate,
                "observed": observed,
                "original_gate": summary.get("engineering_calibration_gate"),
            },
        },
        "source_hashes": {
            "materialized_complete_final_py": sha(ROOT / "simulator" / "complete_final.py"),
            "rules_fix_config": sha(RULE_CONFIG),
            "rules_fix_status": sha(RULE_STATUS),
        },
        "player_abilities_changed": False,
        "team_strength_parameters_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
        "definitive_10000_executed": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "engineering_validation_snapshot.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if engineering_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
