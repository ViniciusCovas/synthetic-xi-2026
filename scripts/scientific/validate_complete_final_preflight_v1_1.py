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

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "data/simulations/complete_final_v1/engineering_validation_snapshot.json"
V11 = ROOT / "data/simulations/complete_final_v1_1/engineering_validation_snapshot.json"
STATUS = ROOT / "data/model_readiness/complete_final_preflight_status.json"
RULE_STATUS = ROOT / "data/model_readiness/complete_final_rules_fix_v1_1_status.json"


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    if not V11.exists():
        raise SystemExit("Missing Complete Final Engine v1.1 engineering snapshot")
    evidence = json.loads(V11.read_text(encoding="utf-8"))
    if evidence.get("engineering_gate_passed") is not True:
        raise SystemExit("v1.1 engineering gate is not affirmative")
    rules = json.loads(RULE_STATUS.read_text(encoding="utf-8")) if RULE_STATUS.exists() else {}
    if rules.get("status") != "complete_final_rules_fix_v1_1_applied":
        raise SystemExit("v1.1 rules-fix runtime evidence is not affirmative")

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

    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
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
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
