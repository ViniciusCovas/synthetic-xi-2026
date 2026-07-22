#!/usr/bin/env python3
"""Align Complete Final validation with the repository's canonical role gate.

The materialized v1 validator still referenced a provisional blind-review file
that is not the canonical release evidence. The definitive release orchestrator
and scientific status use `data/model_readiness/eleven_role_readiness.json` with
the unchanged boolean key `eleven_role_gate_passed`. This patch changes only the
evidence lookup path/key; it does not create evidence or alter its value.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "simulator/validation.py"
STATUS = ROOT / "data/model_readiness/complete_final_validation_role_gate_v1_status.json"
CANONICAL = ROOT / "data/model_readiness/eleven_role_readiness.json"

OLD = '''        "position_review_passed": (\n            root\n            / "data"\n            / "audits"\n            / "position_ontology_v2"\n            / "blind_review"\n            / "blind_review_evaluation.json",\n            "review_gate_passed",\n        ),\n'''
NEW = '''        "position_review_passed": (\n            root / "data" / "model_readiness" / "eleven_role_readiness.json",\n            "eleven_role_gate_passed",\n        ),\n'''


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    before = digest(TARGET)
    changed = False
    if OLD in source:
        source = source.replace(OLD, NEW, 1)
        TARGET.write_text(source, encoding="utf-8")
        changed = True
    elif NEW not in source:
        raise SystemExit("Canonical role-gate patch anchor not found")

    evidence = json.loads(CANONICAL.read_text(encoding="utf-8")) if CANONICAL.exists() else {}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "complete_final_validation_role_gate_v1_applied",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": str(TARGET.relative_to(ROOT)),
        "source_sha256_before_patch": before,
        "source_sha256_after_patch": digest(TARGET),
        "patch_changed_materialized_source": changed,
        "superseded_lookup": "data/audits/position_ontology_v2/blind_review/blind_review_evaluation.json:review_gate_passed",
        "canonical_lookup": "data/model_readiness/eleven_role_readiness.json:eleven_role_gate_passed",
        "canonical_evidence_status": evidence.get("status"),
        "canonical_gate_value": evidence.get("eleven_role_gate_passed"),
        "evidence_value_overridden": False,
        "gate_threshold_changed": False,
        "match_events_changed": False,
        "model_parameters_changed": False,
        "team_strength_parameters_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
