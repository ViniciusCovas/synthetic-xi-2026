#!/usr/bin/env python3
"""Materialize Complete Final Engine v1 and apply the frozen v1.1 rules fix."""
from __future__ import annotations

from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts" / "install_complete_final_bundle.py"), run_name="__complete_final_v1_installer__")
runpy.run_path(str(ROOT / "scripts" / "patch_complete_final_rules_v1_1.py"), run_name="__complete_final_v1_1_patch__")
