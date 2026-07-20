#!/usr/bin/env python3
"""Build phased gates for one definitive Real XI versus one definitive AI XI.

Phase A allows deterministic team construction only after ontology, blind review,
coverage and role-population sufficiency pass. Phase B allows the final event simulation
only after teams are frozen/hashed and independent engine validation also passes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/audits/definitive_experiment_v1")
ONTOLOGY = Path("data/audits/position_ontology_v2/ontology_audit_status.json")
BLIND = Path("data/audits/position_ontology_v2/blind_review/blind_review_evaluation.json")
COVERAGE = Path("data/audits/scope_correct_coverage/shadow_selection/shadow_selection_status.json")
ENGINE = Path("data/audits/engine_validation_v1/status.json")
PROTOCOL = Path("DEFINITIVE_REAL_VS_AI_PROTOCOL.md")
GENERATOR = Path("simulator/ai_xi_generator.py")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
MIN_ROLE_POOL = 20


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def role_counts(ontology: dict) -> dict[str, int]:
    counts = {role: 0 for role in ROLES}
    for row in ontology.get("role_population", []):
        role = str(row.get("role", ""))
        if role in counts:
            counts[role] = int(row.get("audited_stable_candidates", 0) or 0)
    return counts


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    ontology = load_json(ONTOLOGY)
    blind = load_json(BLIND)
    coverage = load_json(COVERAGE)
    engine = load_json(ENGINE)

    counts = role_counts(ontology)
    population_pass = all(counts[role] >= MIN_ROLE_POOL for role in ROLES)
    blind_pass = bool(blind.get("review_gate_passed", False))
    coverage_pass = bool(coverage.get("shadow_selection_sufficiency_gate_passed", False))
    ontology_pass = bool(ontology.get("final_ontology_gate_passed", False)) and population_pass
    protocol_pass = PROTOCOL.exists()
    generator_pass = GENERATOR.exists()
    preteam_engine_pass = bool(engine.get("preteam_engine_gate_passed", False))
    final_engine_pass = bool(engine.get("final_engine_gate_passed", False))
    teams_frozen = bool(engine.get("teams_frozen_and_hashed", False))

    gates = {
        "protocol_frozen": protocol_pass,
        "partial_identification_forbidden": True,
        "single_real_xi_required": True,
        "single_ai_xi_required": True,
        "blind_review_gate_passed": blind_pass,
        "ontology_v3_gate_passed": ontology_pass,
        "minimum_20_candidates_each_role": population_pass,
        "final_candidate_coverage_gate_passed": coverage_pass,
        "ai_generator_implemented": generator_pass,
        "preteam_engine_validation_passed": preteam_engine_pass,
        "teams_frozen_and_hashed": teams_frozen,
        "independent_final_engine_validation_passed": final_engine_pass,
    }

    design_requirements = [
        "protocol_frozen",
        "blind_review_gate_passed",
        "ontology_v3_gate_passed",
        "minimum_20_candidates_each_role",
        "final_candidate_coverage_gate_passed",
        "ai_generator_implemented",
    ]
    design_gate = all(bool(gates[name]) for name in design_requirements)
    team_generation_allowed = design_gate

    final_requirements = design_requirements + [
        "preteam_engine_validation_passed",
        "teams_frozen_and_hashed",
        "independent_final_engine_validation_passed",
    ]
    final_pass = all(bool(gates[name]) for name in final_requirements)

    design_blockers = [name for name in design_requirements if not gates[name]]
    final_blockers = [name for name in final_requirements if not gates[name]]
    if design_gate and not teams_frozen:
        next_action = "build exactly one Real XI and one AI XI, freeze both files and record SHA-256 hashes"
    elif design_gate and teams_frozen and not final_pass:
        next_action = "complete independent post-freeze engine checks before the 100,000-match run"
    elif final_pass:
        next_action = "run the preregistered final simulation under the frozen team and code hashes"
    else:
        next_action = "resolve design blockers without producing definitive team claims"

    status = {
        "status": "definitive_real_vs_ai_gate_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "estimand": "one deterministic Real XI versus one deterministic AI XI",
        "partial_identification_allowed": False,
        "formation_slots": ROLES,
        "minimum_role_pool": MIN_ROLE_POOL,
        "audited_stable_candidates_by_role": counts,
        "gates": gates,
        "design_gate_passed": design_gate,
        "design_blockers": design_blockers,
        "final_blockers": final_blockers,
        "final_experiment_gate_passed": final_pass,
        "final_team_files_allowed": team_generation_allowed,
        "final_simulation_allowed": final_pass,
        "next_action": next_action,
        "source_files": {
            "ontology": str(ONTOLOGY),
            "blind_review": str(BLIND),
            "coverage": str(COVERAGE),
            "engine_validation": str(ENGINE),
            "protocol": str(PROTOCOL),
            "ai_generator": str(GENERATOR),
        },
    }
    (ROOT / "gate_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = [
        "# Definitive Real XI vs AI XI gate",
        "",
        f"Design gate: **{design_gate}**",
        f"Final simulation gate: **{final_pass}**",
        "",
        "## Role populations",
        "",
        "| Role | Stable candidates | Required | Pass |",
        "|---|---:|---:|---|",
    ]
    for role in ROLES:
        rows.append(f"| {role} | {counts[role]} | {MIN_ROLE_POOL} | {counts[role] >= MIN_ROLE_POOL} |")
    rows.extend(["", "## Design blockers", ""])
    rows.extend([f"- {item}" for item in design_blockers] or ["- none"])
    rows.extend(["", "## Final-simulation blockers", ""])
    rows.extend([f"- {item}" for item in final_blockers] or ["- none"])
    (ROOT / "README.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
