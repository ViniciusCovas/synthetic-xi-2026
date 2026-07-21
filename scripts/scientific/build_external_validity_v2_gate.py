#!/usr/bin/env python3
"""Build the final scientific gate for the externally contextualized v2 experiment."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FIXTURE = Path("data/audits/external_validity_v2/fixture_context_status.json")
STRENGTH = Path("data/audits/external_validity_v2/strength_model_status.json")
VALIDATION = Path("data/audits/external_validity_v2/validation_status.json")
DIRECTION = Path("data/audits/external_validity_v2/independent_direction_check.json")
MANIFEST = Path("data/definitive_experiment_v2/team_manifest.json")
REAL = Path("data/definitive_experiment_v2/real_xi.csv")
AI = Path("data/definitive_experiment_v2/ai_xi.csv")
OUT = Path("data/audits/external_validity_v2/final_gate_status.json")


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def main() -> None:
    fixture = load(FIXTURE)
    strength = load(STRENGTH)
    validation = load(VALIDATION)
    direction = load(DIRECTION)
    manifest = load(MANIFEST)
    hash_pass = bool(
        REAL.exists() and AI.exists()
        and manifest.get("real_xi_sha256") == sha256(REAL)
        and manifest.get("ai_xi_sha256") == sha256(AI)
        and manifest.get("real_players") == 11
        and manifest.get("ai_agents") == 11
    )
    direction_hash_pass = bool(
        direction.get("real_xi_sha256") == sha256(REAL)
        and direction.get("ai_xi_sha256") == sha256(AI)
    )
    gates = {
        "fixture_context_complete": float(fixture.get("target_coverage", 0) or 0) >= 0.995,
        "strength_adjusted_profiles_passed": bool(strength.get("external_validity_profile_gate_passed", False)),
        "goalkeeper_model_discriminative": bool(strength.get("goalkeeper_model", {}).get("passed", False)),
        "minimum_20_candidates_each_role": bool(strength.get("minimum_20_each_role", False)),
        "predictive_elo_holdout_passed": bool(validation.get("elo_predictive_holdout", {}).get("passed", False)),
        "context_gamma_sensitivity_passed": bool(validation.get("context_gamma_sensitivity", {}).get("passed", False)),
        "goalkeeper_weight_sensitivity_passed": bool(validation.get("goalkeeper_weight_sensitivity", {}).get("passed", False)),
        "selected_player_plausibility_passed": bool(validation.get("selected_player_plausibility", {}).get("passed", False)),
        "v2_teams_frozen_and_hashed": hash_pass,
        "independent_post_freeze_direction_passed": bool(direction.get("independent_direction_check_passed", False) and direction_hash_pass),
        "v1_global_claim_invalidated_and_preserved": manifest.get("old_v1_result_status") == "preserved_diagnostic_invalidated_for_global_best_xi_claim",
    }
    passed = all(gates.values())
    blockers = [name for name, value in gates.items() if not value]
    status = {
        "status": "external_validity_v2_final_gate_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "estimand": "one externally contextualized deterministic Real XI versus one role-conditioned AI XI",
        "experiment_version": "v2_external_validity",
        "gates": gates,
        "blockers": blockers,
        "v2_final_gate_passed": passed,
        "v2_simulation_allowed": passed,
        "real_xi_sha256": sha256(REAL),
        "ai_xi_sha256": sha256(AI),
        "master_seed": 20260721,
        "matches_required": 100000,
        "paired_orientations_required": 50000,
        "next_action": "run the frozen v2 100000-match simulation" if passed else "resolve v2 blockers without publishing a definitive result",
        "claim_boundary": "Best under the frozen 2025-2026 data, role ontology, goalkeeper proxy and results-based opponent-strength model; not an absolute truth about player quality.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
