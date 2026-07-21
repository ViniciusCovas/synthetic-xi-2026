#!/usr/bin/env python3
"""Bootstrap and execute complete-final engineering/scientific validation."""
from __future__ import annotations
from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve()
_ROOT = _TARGET.parents[2]
_MARKER = "Bootstrap and execute complete-final engineering/scientific validation"
runpy.run_path(str(_ROOT / "scripts" / "install_complete_final_bundle.py"), run_name="__complete_final_installer__")
_SOURCE = _TARGET.read_text(encoding="utf-8")
if _MARKER in _SOURCE:
    raise RuntimeError("Complete-final bundle did not materialize the validation runner")
exec(compile(_SOURCE, str(_TARGET), "exec"), globals(), globals())
