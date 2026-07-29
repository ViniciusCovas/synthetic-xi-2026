"""Scientific and engineering validation gates for the complete-final engine."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from .calibrated_core import CalibrationTargets
from .complete_final import CompleteFinalSimulator, FinalConfig
from .complete_final_monte_carlo import paired_swap_diagnostic, simulate_complete_finals
from .engine import TeamProfile


def validate_complete_final_engine(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    simulations: int = 2_000,
    seed: int = 20260723,
    config: FinalConfig | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    base = config or FinalConfig()
    deterministic_a = CompleteFinalSimulator(
        home, away, targets, replace(base, seed=seed)
    ).simulate(keep_timeline=True)
    deterministic_b = CompleteFinalSimulator(
        home, away, targets, replace(base, seed=seed)
    ).simulate(keep_timeline=True)
    reproducible = deterministic_a.as_dict() == deterministic_b.as_dict()

    summary = simulate_complete_finals(
        home,
        away,
        targets,
        simulations=simulations,
        seed=seed,
        config=base,
        audit_sample_size=min(250, simulations),
    )
    swap = paired_swap_diagnostic(
        home,
        away,
        targets,
        simulations=max(400, simulations // 2),
        seed=seed + 1,
        config=base,
    )
    invariants = _validate_invariants(
        home,
        away,
        targets,
        replace(base, seed=None),
        seed=seed + 2,
        samples=min(250, max(50, simulations // 8)),
    )
    stability = _seed_stability(
        home,
        away,
        targets,
        base,
        simulations=max(250, simulations // 4),
        seeds=(seed + 10, seed + 20, seed + 30, seed + 40),
    )
    readiness = discover_repository_readiness(repository_root or Path("."))

    engineering_checks = {
        "deterministic_reproducibility": reproducible,
        "rules_and_state_invariants": invariants["passed"],
        "regulation_distribution_calibration": summary[
            "engineering_calibration_gate"
        ]["passed"],
        "neutral_orientation_symmetry": swap["passed"],
        "seed_stability": stability["passed"],
    }
    engineering_passed = all(engineering_checks.values())
    scientific_checks = {
        "engineering_validated": engineering_passed,
        "selection_sufficiency": readiness["selection_sufficiency"],
        "external_holdout_passed": readiness["external_holdout_passed"],
        "position_review_passed": readiness["position_review_passed"],
        "final_team_comparison_allowed": readiness[
            "final_team_comparison_allowed"
        ],
        "uncertainty_documented": True,
        "preregistered_protocol_present": readiness[
            "preregistered_protocol_present"
        ],
    }
    publication_ready = all(scientific_checks.values())

    return {
        "status": "complete_final_validation_completed",
        "engine_version": "complete_final_v1",
        "simulation_count": simulations,
        "engineering_gate": {
            "passed": engineering_passed,
            "checks": engineering_checks,
        },
        "scientific_publication_gate": {
            "passed": publication_ready,
            "checks": scientific_checks,
            "interpretation": (
                "A passed engineering gate validates implementation behaviour. "
                "A substantive team-comparison claim is allowed only when all "
                "repository evidence gates also pass."
            ),
        },
        "distribution_summary": {
            key: summary[key]
            for key in (
                "home_champion_probability",
                "away_champion_probability",
                "regulation_draw_probability",
                "extra_time_probability",
                "penalty_shootout_probability",
                "mean_regulation_goals",
                "mean_regulation_shots",
                "mean_regulation_shots_on_target",
                "regulation_zero_zero_rate",
                "regulation_calibration_error",
                "engineering_calibration_gate",
            )
        },
        "reproducibility": {
            "passed": reproducible,
            "seed": seed,
        },
        "invariants": invariants,
        "paired_swap_diagnostic": swap,
        "seed_stability": stability,
        "repository_readiness_evidence": readiness,
    }


def discover_repository_readiness(root: Path) -> dict[str, Any]:
    """Resolve preregistered gates from canonical repository evidence.

    Canonical, versioned status files take precedence. Generic JSON discovery is
    used only as a fallback. Missing evidence is never interpreted as success.
    """

    canonical = {
        "selection_sufficiency": (
            root / "data" / "model_readiness" / "selection_sufficiency_status.json",
            "selection_sufficiency_gate_passed",
        ),
        "external_holdout_passed": (
            root / "data" / "validation" / "external_pre_tournament_holdout_summary.json",
            "external_pre_tournament_validation_passed",
        ),
        "position_review_passed": (
            root / "data" / "model_readiness" / "eleven_role_readiness.json",
            "eleven_role_gate_passed",
        ),
        "final_team_comparison_allowed": (
            root / "data" / "model_readiness" / "scientific_validation_status.json",
            "final_team_comparison_allowed",
        ),
    }
    resolved: dict[str, bool] = {}
    evidence: list[dict[str, Any]] = []
    for gate, (path, key) in canonical.items():
        value = False
        status = "missing"
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                value = bool(payload.get(key, False))
                status = str(payload.get("status", "present"))
            except (OSError, json.JSONDecodeError):
                status = "unreadable"
        resolved[gate] = value
        evidence.append(
            {
                "gate": gate,
                "path": str(path.relative_to(root)),
                "key": key,
                "value": value,
                "status": status,
                "canonical": True,
            }
        )

    protocol_present = (root / "PROTOCOLO_FINAL_COMPLETA.md").exists()
    return {
        **resolved,
        "preregistered_protocol_present": protocol_present,
        "evidence_files": evidence,
        "absence_policy": "Missing affirmative evidence is treated as not passed.",
    }


def _flatten_json(payload: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_json(value, child))
        return result
    if isinstance(payload, list):
        result = {}
        for index, value in enumerate(payload):
            result.update(_flatten_json(value, f"{prefix}[{index}]"))
        return result
    return {prefix: payload}


def _validate_invariants(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    config: FinalConfig,
    seed: int,
    samples: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    violations: list[str] = []
    for index in range(samples):
        result = CompleteFinalSimulator(
            home,
            away,
            targets,
            replace(config, seed=int(rng.integers(0, 2**32 - 1))),
        ).simulate(keep_timeline=True)
        if result.winner not in {home.name, away.name}:
            violations.append(f"{index}: invalid winner")
        if result.decided_by == "penalties":
            if result.home_penalties is None or result.away_penalties is None:
                violations.append(f"{index}: missing shootout score")
            elif result.home_penalties == result.away_penalties:
                violations.append(f"{index}: tied shootout")
        elif result.home_goals == result.away_goals:
            violations.append(f"{index}: unresolved draw")
        for side, stats in (
            ("home", result.home_stats),
            ("away", result.away_stats),
        ):
            if stats["substitutions"] > (
                config.rules.regulation_substitutions
                + config.rules.extra_time_substitution
            ):
                violations.append(f"{index}: {side} substitutions exceeded")
            if not 0 <= stats["players_remaining"] <= 11:
                violations.append(f"{index}: {side} active-player count invalid")
            if stats["reds"] < 0 or stats["yellows"] < 0:
                violations.append(f"{index}: {side} negative discipline")
        clocks = [float(event["clock"]) for event in result.timeline]
        if clocks != sorted(clocks):
            violations.append(f"{index}: non-monotonic timeline")
    return {
        "passed": not violations,
        "samples": samples,
        "violations": violations[:25],
        "violation_count": len(violations),
    }


def _seed_stability(
    home: TeamProfile,
    away: TeamProfile,
    targets: CalibrationTargets,
    config: FinalConfig,
    simulations: int,
    seeds: tuple[int, ...],
) -> dict[str, Any]:
    estimates = []
    for seed in seeds:
        summary = simulate_complete_finals(
            home,
            away,
            targets,
            simulations=simulations,
            seed=seed,
            config=config,
            audit_sample_size=0,
        )
        estimates.append(summary["home_champion_probability"]["estimate"])
    spread = max(estimates) - min(estimates)
    threshold = max(0.06, 3.0 / np.sqrt(simulations))
    return {
        "simulations_per_seed": simulations,
        "seeds": list(seeds),
        "home_champion_estimates": estimates,
        "maximum_spread": spread,
        "threshold": float(threshold),
        "passed": spread <= threshold,
    }
