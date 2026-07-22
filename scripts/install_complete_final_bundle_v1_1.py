#!/usr/bin/env python3
"""Materialize Complete Final Engine v1 and apply frozen v1.1 audit patches."""
from __future__ import annotations

from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(
    str(ROOT / "scripts" / "install_complete_final_bundle.py"),
    run_name="__complete_final_v1_installer__",
)
rules_namespace = runpy.run_path(
    str(ROOT / "scripts" / "patch_complete_final_rules_v1_1.py"),
    run_name="__complete_final_v1_1_rules_patch__",
)
rules_exit_code = int(rules_namespace["main"]())
if rules_exit_code:
    raise SystemExit(rules_exit_code)

measurement_namespace = runpy.run_path(
    str(ROOT / "scripts" / "patch_complete_final_yellow_measurement_v1.py"),
    run_name="__complete_final_yellow_measurement_patch__",
)
measurement_exit_code = int(measurement_namespace["main"]())
if measurement_exit_code:
    raise SystemExit(measurement_exit_code)

json_namespace = runpy.run_path(
    str(ROOT / "scripts" / "patch_complete_final_validation_json_v1.py"),
    run_name="__complete_final_validation_json_patch__",
)
json_exit_code = int(json_namespace["main"]())
if json_exit_code:
    raise SystemExit(json_exit_code)

role_namespace = runpy.run_path(
    str(ROOT / "scripts" / "patch_complete_final_validation_role_gate_v1.py"),
    run_name="__complete_final_validation_role_gate_patch__",
)
role_exit_code = int(role_namespace["main"]())
if role_exit_code:
    raise SystemExit(role_exit_code)
