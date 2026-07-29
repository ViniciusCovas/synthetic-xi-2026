#!/usr/bin/env python3
"""Run the preregistered complete-final Monte Carlo simulation.

The command writes an auditable distribution, a representative replay selected
without excitement cherry-picking, and the exact team/profile inputs used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from simulator.calibrated_core import CalibrationTargets
from simulator.complete_final import FinalConfig
from simulator.complete_final_monte_carlo import simulate_complete_finals
from simulator.profiles import TOTALS_PATH, ROLE_PATH, team_to_rows
from simulator.profiles_v2 import build_teams
from simulator.validation import discover_repository_readiness

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
DEFAULT_OUT = Path("data/simulations/complete_final_v1")


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
    parser.add_argument("--simulations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--audit-sample-size", type=int, default=250)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.simulations < 1:
        raise ValueError("--simulations must be positive")
    calibration_payload = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    targets = CalibrationTargets.from_dict(calibration_payload)
    synthetic, real, avatars, real_selection = build_teams(top_n=args.top_n)
    config = FinalConfig(seed=None)
    summary = simulate_complete_finals(
        synthetic,
        real,
        targets,
        simulations=args.simulations,
        seed=args.seed,
        config=config,
        audit_sample_size=args.audit_sample_size,
    )
    readiness = discover_repository_readiness(Path("."))
    engineering_passed = bool(summary["engineering_calibration_gate"]["passed"])
    publication_allowed = bool(
        engineering_passed
        and readiness["selection_sufficiency"]
        and readiness["external_holdout_passed"]
        and readiness["position_review_passed"]
        and readiness["final_team_comparison_allowed"]
        and readiness["preregistered_protocol_present"]
    )
    summary["methodological_gate"] = {
        "engineering_distribution_gate_passed": engineering_passed,
        "publication_as_final_result_allowed": publication_allowed,
        "claim_status": (
            "validated comparative result with declared limitations"
            if publication_allowed
            else "exploratory, calibrated and auditable complete-final simulation"
        ),
        "repository_readiness": readiness,
    }
    summary["provenance"] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "calibration_path": str(CALIBRATION_PATH),
        "calibration_sha256": sha256_file(CALIBRATION_PATH),
        "annual_totals_path": str(TOTALS_PATH),
        "annual_totals_sha256": sha256_file(TOTALS_PATH),
        "role_evidence_path": str(ROLE_PATH),
        "role_evidence_sha256": sha256_file(ROLE_PATH),
        "top_n": args.top_n,
        "master_seed": args.seed,
        "complete_final_config": asdict(config),
    }

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    audit_rows = summary.pop("audit_sample", [])
    representative = summary["representative_match"]
    (out / "simulation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(audit_rows).to_csv(out / "audit_sample.csv", index=False)
    pd.DataFrame(representative["timeline"]).to_csv(
        out / "representative_final_timeline.csv", index=False
    )
    avatars.to_csv(out / "synthetic_xi_membership.csv", index=False)
    real_selection.to_csv(out / "real_best_xi_selection.csv", index=False)
    pd.DataFrame(team_to_rows(synthetic)).to_csv(
        out / "synthetic_xi_profiles.csv", index=False
    )
    pd.DataFrame(team_to_rows(real)).to_csv(
        out / "real_best_xi_profiles.csv", index=False
    )
    manifest: dict[str, Any] = {
        "status": "complete_final_artifacts_written",
        "output_directory": str(out),
        "files": {},
    }
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            manifest["files"][path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "simulations": args.simulations,
                "engineering_gate": summary["engineering_calibration_gate"],
                "publication_allowed": publication_allowed,
                "output": str(out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
