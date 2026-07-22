#!/usr/bin/env python3
"""Release the definitive complete-final run only when every canonical gate passes.

This orchestrator is deliberately fail-closed. While evidence is incomplete it
writes a machine-readable blocker report and does not execute or publish a
substantive Synthetic XI versus Real Best XI result. Complete Final Engine v1.1,
its rules and measurement evidence, the 2026 World Cup preflight and the isolated
2,000-match validation are all mandatory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "simulations" / "complete_final_v1_1"
RULE_STATUS = ROOT / "data/model_readiness/complete_final_rules_fix_v1_1_status.json"
MEASUREMENT_STATUS = ROOT / "data/model_readiness/complete_final_yellow_card_measurement_v1_status.json"
VALIDATION_2000 = ROOT / "data/model_readiness/complete_final_validation_2000_status.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate() -> dict[str, Any]:
    selection = read_json(ROOT / "data/model_readiness/selection_sufficiency_status.json")
    holdout = read_json(ROOT / "data/validation/external_pre_tournament_holdout_summary.json")
    roles = read_json(ROOT / "data/model_readiness/eleven_role_readiness.json")
    scientific = read_json(ROOT / "data/model_readiness/scientific_validation_status.json")
    engineering = read_json(OUT / "engineering_validation_snapshot.json")
    preflight = read_json(ROOT / "data/model_readiness/complete_final_preflight_status.json")
    rules = read_json(RULE_STATUS)
    measurement = read_json(MEASUREMENT_STATUS)
    validation = read_json(VALIDATION_2000)

    gates = {
        "engineering_v1_1_gate_passed": bool(engineering.get("engineering_gate_passed", False)),
        "rules_fix_v1_1_applied": rules.get("status") == "complete_final_rules_fix_v1_1_applied",
        "yellow_card_measurement_alignment_applied": measurement.get("status") == "complete_final_yellow_card_measurement_v1_applied",
        "selection_sufficiency_gate_passed": bool(selection.get("selection_sufficiency_gate_passed", False)),
        "external_pre_tournament_validation_passed": bool(holdout.get("external_pre_tournament_validation_passed", False)),
        "eleven_role_gate_passed": bool(roles.get("eleven_role_gate_passed", False)),
        "final_team_comparison_allowed": bool(scientific.get("final_team_comparison_allowed", False)),
        "preregistered_protocol_present": (ROOT / "PROTOCOLO_FINAL_COMPLETA.md").exists(),
        "rules_fix_preregistered": (ROOT / "config/complete_final_rules_fix_v1_1.json").exists(),
        "yellow_measurement_preregistered": (ROOT / "config/complete_final_yellow_card_measurement_v1.json").exists(),
        "preflight_uses_v1_1": preflight.get("engine_version") == "complete_final_v1_1_rules_fix",
        "complete_final_preflight_passed": bool(preflight.get("complete_final_preflight_passed", False)),
        "isolated_validation_2000_passed": (
            validation.get("engine_version") == "complete_final_v1_1_rules_fix"
            and validation.get("simulations") == 2000
            and validation.get("validation_2000_passed") is True
            and validation.get("yellow_measurement_applied") is True
        ),
        "final_10000_authorized": bool(preflight.get("final_10000_authorized", False)),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "status": "complete_final_release_ready" if not blockers else "complete_final_release_blocked",
        "ready": not blockers,
        "engine_version": "complete_final_v1_1_rules_fix",
        "measurement_version": "complete_final_yellow_card_measurement_v1",
        "gates": gates,
        "blocking_gates": blockers,
        "unresolved_players": selection.get("unresolved_players"),
        "preflight_status": preflight.get("status", "missing"),
        "preflight_blockers": preflight.get("blocking_gates", ["complete_final_preflight_status_missing"]),
        "claim_ceiling": scientific.get("current_claim_ceiling", "exploratory only"),
        "policy": "No definitive result is executed or published unless every canonical, v1.1 rules, measurement, preflight and isolated-validation gate is affirmative.",
    }


def run_checked(command: list[str]) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=10000)
    parser.add_argument("--validation-simulations", type=int, default=2000)
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--evaluate-only", action="store_true", help="Refresh the release gate without executing simulations")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    status = evaluate()
    status_path = OUT / "release_gate_status.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if args.evaluate_only:
        return 2 if args.require_ready and not status["ready"] else 0
    if not status["ready"]:
        return 2 if args.require_ready else 0

    run_checked([sys.executable, "scripts/install_complete_final_bundle_v1_1.py"])
    run_checked([
        sys.executable,
        "scripts/run_complete_final_simulation.py",
        "--simulations",
        str(args.simulations),
        "--output",
        str(OUT),
    ])
    run_checked([
        sys.executable,
        "scripts/scientific/validate_complete_final.py",
        "--simulations",
        str(args.validation_simulations),
        "--output",
        str(OUT / "release_validation_report.json"),
    ])

    final_status = evaluate()
    final_status["status"] = "complete_final_release_executed"
    final_status["simulations"] = args.simulations
    final_status["validation_simulations"] = args.validation_simulations
    final_status["definitive_10000_executed"] = args.simulations == 10000
    status_path.write_text(json.dumps(final_status, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
