#!/usr/bin/env python3
"""Run the frozen preflight evaluator against v1.1 engineering evidence.

The v1 snapshot is preserved byte-for-byte. A temporary compatibility view is
used only while the unchanged v1 preflight metric evaluator runs; the resulting
status is then annotated with the v1.1 source path and hash.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "data/simulations/complete_final_v1/engineering_validation_snapshot.json"
V11 = ROOT / "data/simulations/complete_final_v1_1/engineering_validation_snapshot.json"
STATUS = ROOT / "data/model_readiness/complete_final_preflight_status.json"
RULE_STATUS = ROOT / "data/model_readiness/complete_final_rules_fix_v1_1_status.json"


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_blocked(reason: str, evidence: dict[str, Any], rules: dict[str, Any]) -> int:
    previous = load(STATUS)
    gates = dict(previous.get("gates") or {})
    gates["complete_final_v1_1_engineering"] = False
    gates["isolated_validation_2000"] = False
    blockers = [name for name, passed in gates.items() if not passed]
    if "complete_final_v1_1_engineering" not in blockers:
        blockers.append("complete_final_v1_1_engineering")
    status = {
        **previous,
        "status": "complete_final_preflight_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": "complete_final_v1_1_rules_fix",
        "complete_final_preflight_passed": False,
        "final_10000_authorized": False,
        "gates": gates,
        "blocking_gates": blockers,
        "engineering_evidence": {
            "path": str(V11.relative_to(ROOT)),
            "sha256": sha(V11),
            "engineering_gate_passed": evidence.get("engineering_gate_passed"),
            "rules_fix_status_path": str(RULE_STATUS.relative_to(ROOT)),
            "rules_fix_status_sha256": sha(RULE_STATUS),
            "rules_fix_applied": rules.get("status") == "complete_final_rules_fix_v1_1_applied",
            "failure_reason": reason,
        },
        "v1_snapshot_preserved": True,
        "v1_1_preflight_evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "definitive_10000_executed": False,
        "model_parameters_changed": False,
        "rules_implementation_changed": True,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 2


def main() -> int:
    evidence = load(V11)
    rules = load(RULE_STATUS)
    if not V11.exists():
        return write_blocked("missing_v1_1_engineering_snapshot", evidence, rules)
    if evidence.get("engineering_gate_passed") is not True:
        return write_blocked("v1_1_engineering_gate_not_affirmative", evidence, rules)
    if rules.get("status") != "complete_final_rules_fix_v1_1_applied":
        return write_blocked("v1_1_rules_fix_runtime_evidence_not_affirmative", evidence, rules)

    V1.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="complete-final-v1-backup-") as tmp:
        backup = Path(tmp) / "engineering_validation_snapshot.json"
        existed = V1.exists()
        if existed:
            shutil.copy2(V1, backup)
        shutil.copy2(V11, V1)
        try:
            result = subprocess.run(
                [sys.executable, "scripts/scientific/validate_complete_final_preflight.py"],
                cwd=ROOT,
                check=False,
            )
        finally:
            if existed:
                shutil.copy2(backup, V1)
            elif V1.exists():
                V1.unlink()

    status = load(STATUS)
    gates = dict(status.get("gates") or {})
    gates["complete_final_v1_1_engineering"] = True
    status["gates"] = gates
    status["blocking_gates"] = [name for name, passed in gates.items() if not passed]
    status["complete_final_preflight_passed"] = not status["blocking_gates"]
    status["final_10000_authorized"] = status["complete_final_preflight_passed"]
    status["status"] = (
        "complete_final_preflight_passed"
        if status["complete_final_preflight_passed"]
        else "complete_final_preflight_blocked"
    )
    status["engine_version"] = "complete_final_v1_1_rules_fix"
    status["engineering_evidence"] = {
        "path": str(V11.relative_to(ROOT)),
        "sha256": sha(V11),
        "engineering_gate_passed": evidence.get("engineering_gate_passed"),
        "rules_fix_status_path": str(RULE_STATUS.relative_to(ROOT)),
        "rules_fix_status_sha256": sha(RULE_STATUS),
        "rules_fix_applied": True,
    }
    status["v1_snapshot_preserved"] = True
    status["v1_1_preflight_evaluated_at_utc"] = datetime.now(timezone.utc).isoformat()
    status["rules_implementation_changed"] = True
    status["event_tolerances_changed"] = False
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
