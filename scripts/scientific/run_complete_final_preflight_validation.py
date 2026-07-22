#!/usr/bin/env python3
"""Run the isolated 2,000-match validation required before the final 10,000.

This command never calls the definitive Monte Carlo runner. It materializes the
reviewed v1 bundle, applies the preregistered v1.1 rules and measurement patches,
executes only the isolated validation suite, and persists complete diagnostics.
No failed gate is converted into success: both the engineering and repository
scientific-publication gates must be affirmative.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/model_readiness/complete_final_validation_2000_status.json"
ENGINEERING = ROOT / "data/simulations/complete_final_v1_1/engineering_validation_snapshot.json"
VALIDATION_REPORT = ROOT / "data/simulations/complete_final_v1_1/validation_report.json"
VALIDATION_LOG = ROOT / "data/simulations/complete_final_v1_1/validation_build.log"
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


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def run_live(command: list[str]) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return int(result.returncode)


def run_captured(command: list[str]) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return int(result.returncode), result.stdout or ""


def failed_checks(section: dict[str, Any]) -> list[str]:
    checks = section.get("checks") or {}
    return sorted(str(name) for name, value in checks.items() if value is not True)


def main() -> int:
    installed = run_live([sys.executable, "scripts/install_complete_final_bundle_v1_1.py"])
    VALIDATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    for stale in (VALIDATION_REPORT, VALIDATION_REPORT.with_suffix(".md"), VALIDATION_LOG):
        if stale.exists():
            stale.unlink()

    validation = 99
    output = "Validation was not started because bundle installation failed.\n"
    if installed == 0:
        validation, output = run_captured([
            sys.executable,
            "scripts/scientific/validate_complete_final.py",
            "--simulations",
            "2000",
            "--output",
            str(VALIDATION_REPORT),
            "--allow-engineering-failure",
        ])
    VALIDATION_LOG.write_text(output, encoding="utf-8")
    print(output, end="" if output.endswith("\n") else "\n")

    engineering = load(ENGINEERING)
    rules = load(RULE_STATUS)
    measurement = load(MEASUREMENT_STATUS)
    report = load(VALIDATION_REPORT)
    engineering_section = report.get("engineering_gate") or {}
    publication_section = report.get("scientific_publication_gate") or {}
    report_engineering_passed = engineering_section.get("passed") is True
    report_publication_passed = publication_section.get("passed") is True

    passed = (
        installed == 0
        and validation == 0
        and VALIDATION_REPORT.exists()
        and report_engineering_passed
        and report_publication_passed
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
        "validation_process_exit_code": validation,
        "validation_report_generated": VALIDATION_REPORT.exists(),
        "validation_engineering_gate_passed": report_engineering_passed,
        "validation_scientific_publication_gate_passed": report_publication_passed,
        "failed_engineering_checks": failed_checks(engineering_section),
        "failed_scientific_publication_checks": failed_checks(publication_section),
        "validation_2000_passed": passed,
        "definitive_10000_executed": False,
        "engineering_snapshot_sha256": sha(ENGINEERING),
        "validation_report_path": str(VALIDATION_REPORT.relative_to(ROOT)),
        "validation_report_sha256": sha(VALIDATION_REPORT),
        "validation_log_path": str(VALIDATION_LOG.relative_to(ROOT)),
        "validation_log_sha256": sha(VALIDATION_LOG),
        "validation_log_tail": output[-8000:],
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
        "failure_policy": "Any missing report, process error, engineering failure, or scientific-publication failure blocks the 10,000-match release.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
