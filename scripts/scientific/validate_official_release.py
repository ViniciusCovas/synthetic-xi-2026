#!/usr/bin/env python3
"""Fail-closed structural and release validator for official_experiment_v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from simulator.official_complete_final import OFFICIAL_ENGINE_VERSION
from simulator.official_frozen_runtime import (
    build_official_bundles,
    frozen_profile_mismatches,
)
from simulator.official_profiles import CONFIG_PATH, ROSTER_PATH, team_rows
from simulator.official_provenance import critical_source_hashes

DEFAULT_VALIDATION = Path("data/experiments/official_v1/validation")
DEFAULT_ROBUSTNESS = Path("data/experiments/official_v1/robustness")
DEFAULT_STATUS = Path(
    "data/model_readiness/official_experiment_v1_preflight_status.json"
)
DEFAULT_AUTHORIZATION = Path(
    "data/model_readiness/official_release_authorization_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("structural", "release"), default="structural"
    )
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--robustness", type=Path, default=DEFAULT_ROBUSTNESS)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS)
    parser.add_argument(
        "--authorization-output", type=Path, default=DEFAULT_AUTHORIZATION
    )
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _source_hashes(config: dict[str, Any]) -> dict[str, str | None]:
    return critical_source_hashes(config)


def _canonical_structural_checks(
    config: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, Any]]:
    inputs = config["canonical_inputs"]
    selection = _read(Path(inputs["selection_sufficiency"]))
    historical_roles = _read(Path(inputs["role_readiness"]))
    rankings = _read(Path(inputs["rankings_authorization"]))
    scientific = _read(Path(inputs["scientific_validation"]))
    holdout = _read(Path(inputs["external_holdout"]))
    rosters = _read(ROSTER_PATH)
    synthetic, real = build_official_bundles()

    synthetic_rows = team_rows(synthetic)
    real_rows = team_rows(real)
    runtime_ids = {
        "synthetic": set(synthetic.registered_ids),
        "real": set(real.registered_ids),
    }
    frozen_ids = {
        "synthetic": {
            str(row["player_id"])
            for row in rosters["teams"]["synthetic_xi"]["registered_squad"]
        },
        "real": {
            str(row["player_id"])
            for row in rosters["teams"]["real_best_xi"]["registered_squad"]
        },
    }
    profile_mismatches = frozen_profile_mismatches(real)
    source_hashes = _source_hashes(config)
    missing_sources = [name for name, digest in source_hashes.items() if digest is None]

    checks = {
        "canonical_rosters_match_runtime": runtime_ids == frozen_ids,
        "canonical_frozen_profile_values_match_runtime": not profile_mismatches,
        "synthetic_registered_squad_26": len(runtime_ids["synthetic"]) == 26,
        "real_registered_squad_26": len(runtime_ids["real"]) == 26,
        "synthetic_starting_xi_11": len(synthetic.team.players) == 11,
        "real_starting_xi_11": len(real.team.players) == 11,
        "no_provisional_profiles": all(
            row.get("provisional") is False
            for row in synthetic_rows + real_rows
        ),
        "no_exploratory_labels": all(
            "explor" not in name.lower()
            for name in (synthetic.team.name, real.team.name)
        ),
        "selection_sufficiency": bool(
            selection.get("selection_sufficiency_gate_passed")
        ),
        "historical_eleven_role_gate": bool(
            historical_roles.get("eleven_role_gate_passed")
        ),
        "rankings_allowed": bool(rankings.get("official_rankings_allowed")),
        "external_holdout_passed": bool(
            holdout.get("external_pre_tournament_validation_passed")
        ),
        "final_team_comparison_allowed": bool(
            scientific.get("final_team_comparison_allowed")
        ),
        "protocol_amendment_present": Path(
            config["protocol_amendment"]
        ).exists(),
        "protocol_emergency_substitution_addendum_present": Path(
            "PROTOCOL_AMENDMENT_OFFICIAL_V1_ADDENDUM_01.md"
        ).exists(),
        "all_critical_sources_present": not missing_sources,
        "post_result_tuning_performed_false": (
            config.get("post_result_tuning_performed") is False
        ),
        "engine_version_frozen": (
            config.get("engine_version") == OFFICIAL_ENGINE_VERSION
        ),
    }
    evidence = {
        "selection_status": selection.get("status"),
        "historical_role_status": historical_roles.get("status"),
        "historical_rankings_allowed_preserved": historical_roles.get(
            "rankings_allowed"
        ),
        "official_rankings_status": rankings.get("status"),
        "external_holdout_status": holdout.get("status"),
        "scientific_status": scientific.get("status"),
        "synthetic_registered_ids": sorted(runtime_ids["synthetic"]),
        "real_registered_ids": sorted(runtime_ids["real"]),
        "frozen_profile_mismatches": profile_mismatches,
        "missing_critical_sources": missing_sources,
    }
    return checks, evidence


def _release_checks(
    config: dict[str, Any],
    validation: Path,
    robustness: Path,
    source_hashes: dict[str, str | None],
) -> tuple[dict[str, bool], dict[str, Any]]:
    simulation = _read(validation / "simulation_summary.json")
    hypotheses = _read(validation / "official_hypotheses_summary.json")
    sensitivity = _read(robustness / "official_sensitivity_summary.json")
    nested = _read(robustness / "official_nested_uncertainty_summary.json")
    manifest = _read(validation / "manifest.json")
    roster = _read(ROSTER_PATH)

    frozen_synthetic = {
        str(row["player_id"])
        for row in roster["teams"]["synthetic_xi"]["registered_squad"]
    }
    frozen_real = {
        str(row["player_id"])
        for row in roster["teams"]["real_best_xi"]["registered_squad"]
    }
    runtime = simulation.get("canonical_runtime", {})
    runtime_synthetic = {
        str(value) for value in runtime.get("synthetic_registered_ids", [])
    }
    runtime_real = {
        str(value) for value in runtime.get("real_registered_ids", [])
    }
    validation_hashes = simulation.get("source_hashes", {})

    checks = {
        "validation_engine_version": (
            simulation.get("version") == OFFICIAL_ENGINE_VERSION
        ),
        "validation_simulation_count": (
            int(simulation.get("simulations", 0))
            >= int(config["analysis"]["validation_simulations"])
        ),
        "canonical_rosters_match_runtime": (
            runtime_synthetic == frozen_synthetic and runtime_real == frozen_real
        ),
        "no_provisional_profiles": bool(runtime.get("no_provisional_profiles")),
        "no_exploratory_labels": bool(runtime.get("no_exploratory_labels")),
        "event_sanity_passed": bool(
            simulation.get("event_sanity_gate", {}).get("passed")
        ),
        "discipline_calibration_passed": bool(
            simulation.get("discipline_calibration_gate", {}).get("passed")
        ),
        "orientation_equivalence_passed": bool(
            simulation.get("orientation_equivalence", {}).get("passed")
        ),
        "seed_stability_passed": bool(
            simulation.get("seed_stability", {}).get("passed")
        ),
        "official_sensitivity_complete": bool(
            sensitivity.get("official_sensitivity_complete")
        ),
        "official_nested_uncertainty_complete": bool(
            nested.get("official_nested_uncertainty_complete")
        ),
        "h5_h6_h7_estimands_present": bool(
            hypotheses.get("h5_h6_h7_estimands_present")
        ),
        "source_hashes_match_validation": validation_hashes == source_hashes,
        "manifest_engine_version": (
            manifest.get("engine_version") == OFFICIAL_ENGINE_VERSION
        ),
        "manifest_source_hashes_match": (
            manifest.get("source_hashes") == source_hashes
        ),
        "post_result_tuning_performed_false": (
            config.get("post_result_tuning_performed") is False
        ),
    }
    evidence = {
        "validation_summary": str(validation / "simulation_summary.json"),
        "hypotheses_summary": str(
            validation / "official_hypotheses_summary.json"
        ),
        "sensitivity_summary": str(
            robustness / "official_sensitivity_summary.json"
        ),
        "nested_summary": str(
            robustness / "official_nested_uncertainty_summary.json"
        ),
        "discipline_gate": simulation.get("discipline_calibration_gate"),
        "event_sanity_gate": simulation.get("event_sanity_gate"),
        "orientation": simulation.get("orientation_equivalence"),
        "seed_stability": simulation.get("seed_stability"),
        "runtime_synthetic_registered_ids": sorted(runtime_synthetic),
        "runtime_real_registered_ids": sorted(runtime_real),
    }
    return checks, evidence


def main() -> None:
    args = parse_args()
    config = _read(CONFIG_PATH)
    source_hashes = _source_hashes(config)
    structural_checks, structural_evidence = _canonical_structural_checks(config)
    release_checks: dict[str, bool] = {}
    release_evidence: dict[str, Any] = {}
    if args.mode == "release":
        release_checks, release_evidence = _release_checks(
            config, args.validation, args.robustness, source_hashes
        )

    all_checks = {**structural_checks, **release_checks}
    if args.mode == "release":
        missing_or_failed_mandatory = [
            gate
            for gate in config["mandatory_release_gates"]
            if gate not in all_checks or not bool(all_checks[gate])
        ]
        all_checks["mandatory_release_gates_all_present_and_true"] = (
            not missing_or_failed_mandatory
        )
    else:
        missing_or_failed_mandatory = []
        all_checks["structural_gate_set_passed"] = all(
            structural_checks.values()
        )

    blockers = [name for name, passed in all_checks.items() if not passed]
    passed = not blockers

    status = {
        "status": (
            "official_experiment_v1_release_authorized"
            if args.mode == "release" and passed
            else "official_experiment_v1_structurally_ready"
            if args.mode == "structural" and passed
            else "official_experiment_v1_blocked"
        ),
        "mode": args.mode,
        "engine_version": OFFICIAL_ENGINE_VERSION,
        "passed": passed,
        "checks": all_checks,
        "blocking_checks": blockers,
        "missing_or_failed_mandatory_gates": missing_or_failed_mandatory,
        "source_hashes": source_hashes,
        "structural_evidence": structural_evidence,
        "release_evidence": release_evidence,
        "absence_policy": config["absence_policy"],
        "post_result_tuning_performed": config[
            "post_result_tuning_performed"
        ],
    }
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.mode == "release":
        authorization = {
            **status,
            "official_release_authorized": passed,
            "validation_output": str(args.validation),
            "robustness_output": str(args.robustness),
            "mandatory_release_gates": config["mandatory_release_gates"],
        }
        args.authorization_output.parent.mkdir(parents=True, exist_ok=True)
        args.authorization_output.write_text(
            json.dumps(authorization, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
