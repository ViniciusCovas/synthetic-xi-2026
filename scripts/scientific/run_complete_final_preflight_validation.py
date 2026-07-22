#!/usr/bin/env python3
"""Run the isolated 2,000-match validation required before the final 10,000.

This command never calls the definitive Monte Carlo runner. It materializes the
reviewed engine bundle, invokes only the validation suite and writes a compact
status file. GitHub Actions restores materialized source wrappers before
publishing evidence.
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
ENGINEERING = ROOT / "data/simulations/complete_final_v1/engineering_validation_snapshot.json"


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


def main() -> int:
    installed = run([sys.executable, "scripts/install_complete_final_bundle.py"])
    validation = 99 if installed else run([
        sys.executable,
        "scripts/scientific/validate_complete_final.py",
        "--simulations",
        "2000",
    ])
    passed = installed == 0 and validation == 0
    payload = {
        "status": "complete_final_validation_2000_passed" if passed else "complete_final_validation_2000_failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulations": 2000,
        "bundle_install_exit_code": installed,
        "validation_exit_code": validation,
        "validation_2000_passed": passed,
        "definitive_10000_executed": False,
        "engineering_snapshot_sha256": sha(ENGINEERING),
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
