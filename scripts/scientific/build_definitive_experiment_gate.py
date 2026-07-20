#!/usr/bin/env python3
"""Build phased gates for one definitive Real XI versus one definitive AI XI.

Phase A allows deterministic team construction only after complete-lineup positional
evidence, blind review, ontology promotion, final candidate coverage and role-population
sufficiency pass. Phase B allows the final event simulation only after teams are frozen,
hashed and independently validated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/audits/definitive_experiment_v1")
EVIDENCE = Path("data/audits/position_ontology_v3/lineup_completeness_status.json")
ONTOLOGY = Path("data/audits/position_ontology_v3/ontology_v3_status.json")
BLIND = Path("data/audits/position_ontology_v3/blind_review/blind_review_evaluation.json")
COVERAGE = Path("data/audits/position_ontology_v3/final_candidate_coverage_status.json")
ENGINE = Path("data/audits/engine_validation_v1/status.json")
TEAM_MANIFEST = Path("data/definitive_experiment_v1/team_manifest.json")
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


def role_counts(evidence: dict, ontology: dict, blind: dict) -> dict[str, int]:
    candidates = [
        ontology.get("final_eligible_candidates_by_role", {}),
        blind.get("consensus_eligible_candidates_by_role", {}),
        evidence.get("eligible_primary_candidates_by_role", {}),
    ]
    for source in candidates:
        if isinstance(source, dict) and any(role in source for role in ROLES):
            return {role: int(source.get(role, 0) or 0) for role in ROLES}
    return {role: 0 for role in ROLES}


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    evidence = load_json(EVIDENCE)
    ontology = load_json(ONTOLOGY)
    blind = load_json(BLIND)
    coverage = load_json(COVERAGE)
    engine = load_json(ENGINE)
    team_manifest = load_json(TEAM_MANIFEST)

    counts = role_counts(evidence, ontology, blind)
    population_pass = all(counts[role] >= MIN_ROLE_POOL for role in ROLES)
    complete_lineup_evidence_pass = bool(
        evidence.get("all_roles_have_20_primary_candidates", False) and population_pass
    )
    blind_pass = bool(blind.get("review_gate_passed", False))
    ontology_pass = bool(ontology.get("final_ontology_gate_passed", False)) and population_pass
    coverage_pass = bool(coverage.get("final_candidate_coverage_gate_passed", False))
    protocol_pass = PROTOCOL.exists()
    generator_pass = GENERATOR.exists()
    preteam_engine_pass = bool(engine.get("preteam_engine_gate_passed", False))

    teams_frozen = bool(
        team_manifest.get("status") == "definitive_teams_frozen"
        and team_manifest.get("real_xi_sha256")
        and team_manifest.get("ai_xi_sha256")
        and int(team_manifest.get("real_players", 0) or 0) == 11
        and int(team_manifest.get("ai_agents", 0) or 0) == 11
    )
    final_engine_pass = bool(engine.get("final_engine_gate_passed", False))

    gates = {
        "protocol_frozen": protocol_pass,
        "partial_identification_forbidden": True,
        "single_real_xi_required": True,
        "single_ai_xi_required": True,
        "complete_lineup_position_evidence_ready": complete_lineup_evidence_pass,
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
        "complete_lineup_position_evidence_ready",
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
    if not complete_lineup_evidence_pass:
        next_action = "continue outcome-blind complete-lineup extraction for deficient primary-role pools"
    elif not blind_pass:
        next_action = "complete two independent ontology-v3 blind reviews and adjudicate disagreements"
    elif not ontology_pass:
        next_action = "promote adjudicated consensus roles into the definitive ontology-v3 table"
    elif not coverage_pass:
        next_action = "recalculate exact-window coverage for all promoted final candidates"
    elif design_gate and not teams_frozen:
        next_action = "build exactly one Real XI and one AI XI, freeze both files and record SHA-256 hashes"
    elif design_gate and teams_frozen and not final_pass:
        next_action = "complete independent post-freeze engine checks before the 100,000-match run"
    elif final_pass:
        next_action = "run the preregistered final simulation under frozen team and code hashes"
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
            "complete_lineup_evidence": str(EVIDENCE),
            "ontology": str(ONTOLOGY),
            "blind_review": str(BLIND),
            "coverage": str(COVERAGE),
            "engine_validation": str(ENGINE),
            "team_manifest": str(TEAM_MANIFEST),
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
        "| Role | Stable primary candidates | Required | Pass |",
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
