#!/usr/bin/env python3
"""Run smoke, validation or confirmatory official_v1 experiments."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd

from simulator.calibrated_core import CalibrationTargets
from simulator.official_complete_final import OFFICIAL_ENGINE_VERSION, OfficialFinalConfig
from simulator.official_monte_carlo import (
    paired_orientation_diagnostic,
    seed_stability_diagnostic,
    simulate_official_finals,
)
from simulator.official_profiles import (
    CONFIG_PATH,
    ROSTER_PATH,
    bench_rows,
    build_official_bundles,
    team_rows,
)

DEFAULT_OUTPUT = Path("data/experiments/official_v1")
AUTHORIZATION_PATH = Path("data/model_readiness/official_release_authorization_v1.json")


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "validation", "official"), default="smoke")
    parser.add_argument("--simulations", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--minimum-minutes", type=int)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-hypotheses", action="store_true")
    return parser.parse_args()


def _load() -> tuple[dict[str, Any], CalibrationTargets]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    target_path = Path(config["canonical_inputs"]["calibration_targets"])
    targets = CalibrationTargets.from_dict(json.loads(target_path.read_text(encoding="utf-8")))
    return config, targets


def _source_hashes(config: dict[str, Any]) -> dict[str, str | None]:
    paths = {
        "experiment_config": CONFIG_PATH,
        "protocol_amendment": Path(config["protocol_amendment"]),
        "canonical_rosters": ROSTER_PATH,
        "official_profiles_source": Path("simulator/official_profiles.py"),
        "official_engine_source": Path("simulator/official_complete_final.py"),
        "official_monte_carlo_source": Path("simulator/official_monte_carlo.py"),
        "official_runner_source": Path("scripts/run_official_experiment.py"),
        "hypothesis_source": Path("scripts/scientific/analyze_official_hypotheses.py"),
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def _require_authorization(config: dict[str, Any], hashes: dict[str, str | None]) -> dict[str, Any]:
    if not AUTHORIZATION_PATH.exists():
        raise RuntimeError(
            "Official release is blocked: run the validation deployment and commit its authorization first"
        )
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    if not authorization.get("official_release_authorized"):
        raise RuntimeError("Official release authorization is not affirmative")
    if authorization.get("engine_version") != OFFICIAL_ENGINE_VERSION:
        raise RuntimeError("Authorization engine version differs from runtime")
    expected = authorization.get("source_hashes", {})
    mismatches = {
        key: {"authorized": expected.get(key), "runtime": value}
        for key, value in hashes.items()
        if expected.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"Official release source hashes changed after authorization: {mismatches}")
    if config.get("post_result_tuning_performed") is not False:
        raise RuntimeError("post_result_tuning_performed must remain false")
    return authorization


def _write_manifest(output: Path, metadata: dict[str, Any]) -> None:
    files: dict[str, Any] = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files[str(path.relative_to(output))] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    manifest = {
        "status": "official_experiment_artifacts_written",
        **metadata,
        "files": files,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    config, targets = _load()
    analysis = config["analysis"]
    simulations = int(
        args.simulations
        if args.simulations is not None
        else analysis[
            "smoke_simulations"
            if args.mode == "smoke"
            else "validation_simulations"
            if args.mode == "validation"
            else "official_simulations"
        ]
    )
    seed = int(
        args.seed
        if args.seed is not None
        else config["seeds"][
            "smoke" if args.mode == "smoke" else "validation" if args.mode == "validation" else "official"
        ]
    )
    top_n = int(args.top_n if args.top_n is not None else analysis["top_n_primary"])
    minimum_minutes = int(
        args.minimum_minutes if args.minimum_minutes is not None else analysis["minutes_primary"]
    )
    if simulations < 1:
        raise ValueError("simulations must be positive")

    source_hashes = _source_hashes(config)
    authorization = _require_authorization(config, source_hashes) if args.mode == "official" else None
    synthetic, real = build_official_bundles(top_n=top_n, minimum_minutes=minimum_minutes)
    discipline = config["discipline"]
    final_config = OfficialFinalConfig(
        seed=None,
        fouls_per_team_90=float(discipline["fouls_per_team_90"]),
        yellows_per_team_90=float(discipline["yellows_per_team_90"]),
        direct_reds_per_team_90=float(discipline["direct_reds_per_team_90"]),
        booked_player_foul_multiplier=float(discipline["booked_player_foul_multiplier"]),
    )
    result = simulate_official_finals(
        synthetic,
        real,
        targets,
        config,
        simulations=simulations,
        seed=seed,
        final_config=final_config,
        audit_sample_size=int(analysis["audit_sample_size"]),
    )
    match_rows = result.pop("rows")
    state_rows = result.pop("state_condition_rows")
    audit_rows = result.pop("audit_sample")

    orientation_cfg = config["orientation_equivalence"]
    orientation_simulations = (
        max(100, min(500, simulations))
        if args.mode == "smoke"
        else int(orientation_cfg["minimum_simulations_per_orientation"])
    )
    orientation = paired_orientation_diagnostic(
        synthetic,
        real,
        targets,
        simulations=orientation_simulations,
        seed=int(config["seeds"]["orientation"]),
        maximum_difference=float(orientation_cfg["maximum_absolute_difference"]),
        config=final_config,
    )
    if args.mode == "smoke":
        stability = {
            "engine_version": OFFICIAL_ENGINE_VERSION,
            "status": "not_run_in_smoke_mode",
            "passed": None,
        }
    else:
        stability_cfg = config["seed_stability"]
        stability = seed_stability_diagnostic(
            synthetic,
            real,
            targets,
            config,
            seeds=[int(value) for value in config["seeds"]["stability"]],
            simulations_per_seed=int(stability_cfg["simulations_per_seed"]),
            maximum_spread=float(stability_cfg["maximum_probability_spread"]),
            config=final_config,
        )

    result["mode"] = args.mode
    result["top_n"] = top_n
    result["minimum_minutes"] = minimum_minutes
    result["orientation_equivalence"] = orientation
    result["seed_stability"] = stability
    result["source_hashes"] = source_hashes
    result["canonical_runtime"] = {
        "synthetic_registered_ids": list(synthetic.registered_ids),
        "real_registered_ids": list(real.registered_ids),
        "synthetic_starter_ids": list(synthetic.starter_ids),
        "real_starter_ids": list(real.starter_ids),
        "no_provisional_profiles": True,
        "no_exploratory_labels": True,
    }
    result["official_release_authorization_used"] = authorization

    output = args.output / args.mode
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(match_rows).to_csv(output / "official_matches.csv", index=False)
    pd.DataFrame(state_rows).to_csv(output / "official_state_conditions.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(output / "audit_sample.csv", index=False)
    pd.DataFrame(result["representative_match"]["timeline"]).to_csv(
        output / "representative_final_timeline.csv", index=False
    )
    pd.DataFrame(team_rows(synthetic)).to_csv(output / "synthetic_starting_xi.csv", index=False)
    pd.DataFrame(team_rows(real)).to_csv(output / "real_starting_xi.csv", index=False)
    pd.DataFrame(bench_rows(synthetic)).to_csv(output / "synthetic_bench_compatibility.csv", index=False)
    pd.DataFrame(bench_rows(real)).to_csv(output / "real_bench_compatibility.csv", index=False)
    pd.DataFrame(synthetic.roster_rows).to_csv(output / "synthetic_runtime_roster.csv", index=False)
    pd.DataFrame(real.roster_rows).to_csv(output / "real_runtime_roster.csv", index=False)
    pd.DataFrame(synthetic.membership_rows).to_csv(output / "synthetic_archetype_membership.csv", index=False)
    (output / "simulation_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not args.skip_hypotheses:
        subprocess.run(
            [
                sys.executable,
                "scripts/scientific/analyze_official_hypotheses.py",
                "--matches",
                str(output / "official_matches.csv"),
                "--states",
                str(output / "official_state_conditions.csv"),
                "--config",
                str(CONFIG_PATH),
                "--output",
                str(output),
            ],
            check=True,
        )

    _write_manifest(
        output,
        {
            "engine_version": OFFICIAL_ENGINE_VERSION,
            "mode": args.mode,
            "simulations": simulations,
            "master_seed": seed,
            "top_n": top_n,
            "minimum_minutes": minimum_minutes,
            "source_hashes": source_hashes,
            "final_config": asdict(final_config),
        },
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "mode": args.mode,
                "simulations": simulations,
                "discipline_gate": result["discipline_calibration_gate"]["passed"],
                "event_sanity_gate": result["event_sanity_gate"]["passed"],
                "orientation_gate": orientation["passed"],
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
