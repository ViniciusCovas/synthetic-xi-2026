#!/usr/bin/env python3
"""Run the isolated 2,000-match validation required before the final 10,000.

This command never calls the definitive Monte Carlo runner. It materializes the
reviewed v1 bundle, applies the preregistered v1.1 rules and measurement patches,
invokes only the validation suite and writes a compact status file.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/model_readiness/complete_final_validation_2000_status.json"
ENGINEERING = ROOT / "data/simulations/complete_final_v1_1/engineering_validation_snapshot.json"
VALIDATION_REPORT = ROOT / "data/simulations/complete_final_v1_1/validation_report.json"
RULE_STATUS = ROOT / "data/model_readiness/complete_final_rules_fix_v1_1_status.json"
MEASUREMENT_STATUS = ROOT / "data/model_readiness/complete_final_yellow_card_measurement_v1_status.json"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str]) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return int(result.returncode)


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    installed = run([sys.executable, "scripts/install_complete_final_bundle_v1_1.py"])
    VALIDATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    validation = 99 if installed else run([
        sys.executable,
        "scripts/scientific/validate_complete_final.py",
        "--simulations",
        "2000",
        "--output",
        str(VALIDATION_REPORT),
    ])
    engineering = load(ENGINEERING)
    rules = load(RULE_STATUS)
    measurement = load(MEASUREMENT_STATUS)
    passed = (
        installed == 0
        and validation == 0
        and VALIDATION_REPORT.exists()
        and engineering.get("engineering_gate_passed") is True
        and rules.get("status") == "complete_final_rules_fix_v1_1_applied"
        and measurement.get("status") == "complete_final_yellow_card_measurement_v1_applied"
    )
    payload = {
        "status": "complete_final_validation_2000_passed" if passed else "complete_final_validation_2000_failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": "complete_final_v1_1_rules_fix",
        "simulations": 2000,
        "bundle_install_and_audit_patches_exit_code": installed,
        "validation_exit_code": validation,
        "validation_2000_passed": passed,
        "definitive_10000_executed": False,
        "engineering_snapshot_sha256": sha(ENGINEERING),
        "validation_report_path": str(VALIDATION_REPORT.relative_to(ROOT)),
        "validation_report_sha256": sha(VALIDATION_REPORT),
        "rules_fix_status_sha256": sha(RULE_STATUS),
        "rules_fix_applied": rules.get("status") == "complete_final_rules_fix_v1_1_applied",
        "yellow_measurement_status_sha256": sha(MEASUREMENT_STATUS),
        "yellow_measurement_applied": measurement.get("status") == "complete_final_yellow_card_measurement_v1_applied",
        "model_parameters_changed": False,
        "rules_implementation_changed": True,
        "measurement_alignment_changed": True,
        "event_generation_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
