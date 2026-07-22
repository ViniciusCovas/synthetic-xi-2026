#!/usr/bin/env python3
"""Release the definitive complete-final run only when every canonical gate passes.

This orchestrator is deliberately fail-closed. While evidence is incomplete it
writes a machine-readable blocker report and does not execute or publish a
substantive Synthetic XI versus Real Best XI result. The complete-final preflight
is mandatory: rosters, benches, rules, neutral referee context, World Cup 2026
weather record and event-distribution compatibility must all pass first.
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
OUT = ROOT / "data" / "simulations" / "complete_final_v1"


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

    gates = {
        "engineering_gate_passed": bool(engineering.get("engineering_gate_passed", False)),
        "selection_sufficiency_gate_passed": bool(selection.get("selection_sufficiency_gate_passed", False)),
        "external_pre_tournament_validation_passed": bool(holdout.get("external_pre_tournament_validation_passed", False)),
        "eleven_role_gate_passed": bool(roles.get("eleven_role_gate_passed", False)),
        "final_team_comparison_allowed": bool(scientific.get("final_team_comparison_allowed", False)),
        "preregistered_protocol_present": (ROOT / "PROTOCOLO_FINAL_COMPLETA.md").exists(),
        "complete_final_preflight_passed": bool(preflight.get("complete_final_preflight_passed", False)),
        "final_10000_authorized": bool(preflight.get("final_10000_authorized", False)),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "status": "complete_final_release_ready" if not blockers else "complete_final_release_blocked",
        "ready": not blockers,
        "gates": gates,
        "blocking_gates": blockers,
        "unresolved_players": selection.get("unresolved_players"),
        "preflight_status": preflight.get("status", "missing"),
        "preflight_blockers": preflight.get("blocking_gates", ["complete_final_preflight_status_missing"]),
        "claim_ceiling": scientific.get("current_claim_ceiling", "exploratory only"),
        "policy": "No definitive result is executed or published unless every canonical and preflight gate is affirmative.",
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
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    status = evaluate()
    status_path = OUT / "release_gate_status.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if not status["ready"]:
        return 2 if args.require_ready else 0

    run_checked([sys.executable, "scripts/install_complete_final_bundle.py"])
    run_checked([
        sys.executable,
        "scripts/run_complete_final_simulation.py",
        "--simulations",
        str(args.simulations),
    ])
    run_checked([
        sys.executable,
        "scripts/scientific/validate_complete_final.py",
        "--simulations",
        str(args.validation_simulations),
    ])

    final_status = evaluate()
    final_status["status"] = "complete_final_release_executed"
    final_status["simulations"] = args.simulations
    final_status["validation_simulations"] = args.validation_simulations
    status_path.write_text(json.dumps(final_status, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
