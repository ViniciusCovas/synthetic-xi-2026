#!/usr/bin/env python3
"""Bootstrap and execute the complete-final Monte Carlo runner."""
from __future__ import annotations
from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve()
_ROOT = _TARGET.parents[1]
_MARKER = "Bootstrap and execute the complete-final Monte Carlo runner"
runpy.run_path(str(_ROOT / "scripts" / "install_complete_final_bundle_v1_1.py"), run_name="__complete_final_installer_v1_1__")
_SOURCE = _TARGET.read_text(encoding="utf-8")
if _MARKER in _SOURCE:
    raise RuntimeError("Complete-final bundle did not materialize the simulation runner")
exec(compile(_SOURCE, str(_TARGET), "exec"), globals(), globals())
