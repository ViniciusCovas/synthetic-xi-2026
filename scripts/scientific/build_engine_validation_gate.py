#!/usr/bin/env python3
"""Evaluate pre-team and post-freeze engine validation for the definitive study.

The script only reads committed or same-run validation evidence. It cannot promote an
exploratory result and never treats the pre-tournament Poisson holdout as proof of every
micro-event mechanism.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

OUT = Path("data/audits/engine_validation_v1")
HOLDOUT = Path("data/validation/external_pre_tournament_holdout_summary.json")
DIRECTION = OUT / "independent_direction_check.json"
MECHANISM = OUT / "mechanism_validation.json"
SEARCH_ROOTS = [Path("data/simulations/calibrated_v0_2"), Path("data/validation"), OUT]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def numeric(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def discover_json() -> list[Path]:
    files: set[Path] = set()
    for root in SEARCH_ROOTS:
        if root.exists():
            files.update(Path(name) for name in glob.glob(str(root / "**/*.json"), recursive=True))
    files.discard(OUT / "status.json")
    files.discard(DIRECTION)
    return sorted(files)


def calibration_candidates(files: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in files:
        payload = load_json(path)
        for block in walk_dicts(payload):
            errors = block.get("calibration_error")
            if not isinstance(errors, dict):
                continue
            values = {
                "goals_per_match": numeric(errors.get("goals_per_match")),
                "shots_per_match": numeric(errors.get("shots_per_match")),
                "shots_on_target_per_match": numeric(errors.get("shots_on_target_per_match")),
                "zero_zero_rate": numeric(errors.get("zero_zero_rate")),
            }
            if any(value is not None for value in values.values()):
                candidates.append({"source": str(path), **values})
    return candidates


def calibration_pass(row: dict[str, Any]) -> bool:
    limits = {
        "goals_per_match": 0.15,
        "shots_per_match": 2.0,
        "shots_on_target_per_match": 1.0,
        "zero_zero_rate": 0.03,
    }
    return all(
        row.get(metric) is not None and abs(float(row[metric])) <= limit
        for metric, limit in limits.items()
    )


def explicit_mechanism_evidence(files: list[Path]) -> list[dict[str, Any]]:
    keys = {
        "mechanism_validation_passed",
        "event_mechanism_validation_passed",
        "calibrated_event_engine_passed",
        "posterior_predictive_checks_passed",
    }
    found: list[dict[str, Any]] = []
    for path in files:
        for block in walk_dicts(load_json(path)):
            for key in keys:
                if key in block:
                    found.append({"source": str(path), "key": key, "value": bool(block[key])})
    return found


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    holdout = load_json(HOLDOUT)
    direction = load_json(DIRECTION)
    files = discover_json()
    calibrations = calibration_candidates(files)
    mechanisms = explicit_mechanism_evidence(files)

    holdout_pass = bool(
        holdout.get("external_pre_tournament_validation_passed", False)
        and int(holdout.get("matches", 0) or 0) >= 80
        and float(holdout.get("log_loss", 99.0) or 99.0)
        < float(holdout.get("naive_log_loss", 0.0) or 0.0)
        and float(holdout.get("log_loss_skill_vs_naive", -1.0) or -1.0) > 0
    )
    passing_calibrations = [row for row in calibrations if calibration_pass(row)]
    event_calibration_pass = bool(passing_calibrations)
    mechanism_pass = any(item["value"] for item in mechanisms)
    preteam_gate = bool(holdout_pass and event_calibration_pass and mechanism_pass)

    frozen_teams_present = bool(direction.get("teams_frozen_and_hashed", False))
    independent_direction_pass = bool(
        direction.get("independent_direction_check_passed", False)
        and frozen_teams_present
        and direction.get("real_xi_sha256")
        and direction.get("ai_xi_sha256")
    )
    final_engine_gate = bool(preteam_gate and independent_direction_pass)

    blockers = []
    if not holdout_pass:
        blockers.append("external_temporal_holdout")
    if not event_calibration_pass:
        blockers.append("event_engine_calibration_tolerances")
    if not mechanism_pass:
        blockers.append("event_mechanism_or_posterior_predictive_validation")
    if not frozen_teams_present:
        blockers.append("frozen_team_hashes")
    if not independent_direction_pass:
        blockers.append("independent_post_freeze_direction_check")

    status = {
        "status": "engine_validation_gate_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "The external Poisson holdout validates predictive information in frozen "
            "player profiles; it does not by itself validate the event simulator."
        ),
        "external_holdout": {
            "source": str(HOLDOUT),
            "matches": int(holdout.get("matches", 0) or 0),
            "log_loss": holdout.get("log_loss"),
            "naive_log_loss": holdout.get("naive_log_loss"),
            "skill": holdout.get("log_loss_skill_vs_naive"),
            "passed": holdout_pass,
        },
        "calibration_json_files_scanned": [str(path) for path in files],
        "calibration_candidates": calibrations,
        "passing_calibration_candidates": passing_calibrations,
        "explicit_mechanism_evidence": mechanisms,
        "mechanism_source_expected": str(MECHANISM),
        "preteam_engine_gate_passed": preteam_gate,
        "teams_frozen_and_hashed": frozen_teams_present,
        "independent_post_freeze_direction_check_passed": independent_direction_pass,
        "final_engine_gate_passed": final_engine_gate,
        "blockers": blockers,
        "next_action": (
            "run the final event simulation under frozen hashes"
            if final_engine_gate
            else "resolve engine blockers without using exploratory outcomes as validation"
        ),
    }
    (OUT / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
