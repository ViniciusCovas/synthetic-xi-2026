#!/usr/bin/env python3
"""Patch only Complete Final validation-report JSON serialization.

The engine and all generated match events remain unchanged. The materialized
validation runner is amended to convert NumPy scalar values to equivalent Python
scalars immediately before serialization, preventing `numpy.bool_` from blocking
an otherwise completed isolated validation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/scientific/validate_complete_final.py"
STATUS = ROOT / "data/model_readiness/complete_final_validation_json_v1_status.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    before = digest(TARGET)
    marker = "Complete Final validation JSON scalar normalization v1"
    changed = False

    if marker not in source:
        import_anchor = "from pathlib import Path\n"
        import_replacement = (
            "from pathlib import Path\n"
            "from typing import Any\n\n"
            "import numpy as np\n"
        )
        if import_anchor not in source:
            raise SystemExit("Validation JSON patch import anchor not found")
        source = source.replace(import_anchor, import_replacement, 1)

        function_anchor = "\n\ndef parse_args() -> argparse.Namespace:\n"
        function_replacement = '''\n\n# Complete Final validation JSON scalar normalization v1\ndef _to_builtin(value: Any) -> Any:\n    if isinstance(value, dict):\n        return {str(key): _to_builtin(item) for key, item in value.items()}\n    if isinstance(value, (list, tuple)):\n        return [_to_builtin(item) for item in value]\n    if isinstance(value, np.generic):\n        return value.item()\n    if isinstance(value, Path):\n        return str(value)\n    return value\n\n\ndef parse_args() -> argparse.Namespace:\n'''
        if function_anchor not in source:
            raise SystemExit("Validation JSON patch function anchor not found")
        source = source.replace(function_anchor, function_replacement, 1)

        report_anchor = '''    report = validate_complete_final_engine(\n        synthetic,\n        real,\n        targets,\n        simulations=args.simulations,\n        seed=args.seed,\n        repository_root=Path("."),\n    )\n    args.output.parent.mkdir(parents=True, exist_ok=True)\n'''
        report_replacement = '''    report = validate_complete_final_engine(\n        synthetic,\n        real,\n        targets,\n        simulations=args.simulations,\n        seed=args.seed,\n        repository_root=Path("."),\n    )\n    report = _to_builtin(report)\n    args.output.parent.mkdir(parents=True, exist_ok=True)\n'''
        if report_anchor not in source:
            raise SystemExit("Validation JSON patch report anchor not found")
        source = source.replace(report_anchor, report_replacement, 1)
        TARGET.write_text(source, encoding="utf-8")
        changed = True

    after = digest(TARGET)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "complete_final_validation_json_v1_applied",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": str(TARGET.relative_to(ROOT)),
        "source_sha256_before_patch": before,
        "source_sha256_after_patch": after,
        "patch_changed_materialized_source": changed,
        "normalization": "NumPy scalars to equivalent Python scalars before JSON serialization",
        "match_events_changed": False,
        "model_parameters_changed": False,
        "team_strength_parameters_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
        "gate_logic_changed": False,
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
