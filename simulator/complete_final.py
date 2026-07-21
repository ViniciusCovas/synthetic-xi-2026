"""Transparent bootstrap for the complete-final source bundle.

The repository keeps a deterministic, checksummed source bundle in
`scripts/install_complete_final_bundle.py`. On first import this wrapper materializes
the reviewed source files and executes the generated module. The CI verifies and
archives the expanded sources.
"""
from __future__ import annotations

from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve()
_ROOT = _TARGET.parents[1]
_WRAPPER_MARKER = "Transparent bootstrap for the complete-final source bundle"
runpy.run_path(str(_ROOT / "scripts" / "install_complete_final_bundle.py"), run_name="__complete_final_installer__")
_SOURCE = _TARGET.read_text(encoding="utf-8")
if _WRAPPER_MARKER in _SOURCE:
    raise RuntimeError("Complete-final bundle did not materialize simulator/complete_final.py")
exec(compile(_SOURCE, str(_TARGET), "exec"), globals(), globals())
