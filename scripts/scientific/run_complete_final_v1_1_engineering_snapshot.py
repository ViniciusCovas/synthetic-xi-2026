#!/usr/bin/env python3
"""Execute the v1.1 engineering builder and preserve any failure traceback."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/simulations/complete_final_v1_1/engineering_validation_snapshot.json"
LOG = ROOT / "data/simulations/complete_final_v1_1/engineering_build.log"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260731)
    args = parser.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "scripts/scientific/build_complete_final_v1_1_engineering_snapshot.py",
        "--simulations",
        str(args.simulations),
        "--seed",
        str(args.seed),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout or ""
    LOG.write_text(output, encoding="utf-8")
    print(output, end="")
    if result.returncode != 0 and not OUT.exists():
        payload = {
            "status": "complete_final_v1_1_engineering_builder_failed",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "engine_version": "complete_final_v1_1_rules_fix",
            "simulations": args.simulations,
            "seed": args.seed,
            "engineering_gate_passed": False,
            "builder_exit_code": int(result.returncode),
            "failure_log": str(LOG.relative_to(ROOT)),
            "failure_output": output[-12000:],
            "player_abilities_changed": False,
            "team_strength_parameters_changed": False,
            "selection_thresholds_changed": False,
            "event_tolerances_changed": False,
            "definitive_10000_executed": False,
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
