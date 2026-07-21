"""Bootstrap the complete-final focused test suite from the reviewed bundle."""
from __future__ import annotations
from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve()
_ROOT = _TARGET.parents[1]
_MARKER = "Bootstrap the complete-final focused test suite from the reviewed bundle"
runpy.run_path(str(_ROOT / "scripts" / "install_complete_final_bundle.py"), run_name="__complete_final_installer__")
_SOURCE = _TARGET.read_text(encoding="utf-8")
if _MARKER in _SOURCE:
    raise RuntimeError("Complete-final bundle did not materialize tests/test_complete_final.py")
exec(compile(_SOURCE, str(_TARGET), "exec"), globals(), globals())
