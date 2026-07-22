#!/usr/bin/env python3
"""Combine the core preflight with the isolated 2,000-match validation gate."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "data/model_readiness/complete_final_preflight_status.json"
VALIDATION = ROOT / "data/model_readiness/complete_final_validation_2000_status.json"


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    status = load(STATUS)
    validation = load(VALIDATION)
    core_passed = bool(status.get("complete_final_preflight_passed"))
    validation_passed = bool(validation.get("validation_2000_passed")) and validation.get("simulations") == 2000
    gates = dict(status.get("gates") or {})
    gates["isolated_validation_2000"] = validation_passed
    blockers = [name for name, passed in gates.items() if not passed]
    passed = core_passed and validation_passed and not blockers
    status.update({
        "status": "complete_final_preflight_passed" if passed else "complete_final_preflight_blocked",
        "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_preflight_passed_before_validation_2000": core_passed,
        "validation_2000_passed": validation_passed,
        "complete_final_preflight_passed": passed,
        "final_10000_authorized": passed,
        "gates": gates,
        "blocking_gates": blockers,
        "validation_2000_status": validation.get("status", "missing"),
        "definitive_10000_executed": False,
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
        "policy": "The definitive 10,000-match distribution is authorized only after the core preflight and isolated 2,000-match validation both pass."
    })
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": status["status"],
        "core_preflight_passed": core_passed,
        "validation_2000_passed": validation_passed,
        "final_10000_authorized": passed,
        "blocking_gates": blockers,
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
