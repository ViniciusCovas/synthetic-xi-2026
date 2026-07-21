"""Bootstrap entrypoint for complete-final engineering and scientific validation."""
from __future__ import annotations
from pathlib import Path
import runpy

_TARGET = Path(__file__).resolve()
_ROOT = _TARGET.parents[1]
_MARKER = "Bootstrap entrypoint for complete-final engineering and scientific validation"
runpy.run_path(str(_ROOT / "scripts" / "install_complete_final_bundle.py"), run_name="__complete_final_installer__")
_SOURCE = _TARGET.read_text(encoding="utf-8")
if _MARKER in _SOURCE:
    raise RuntimeError("Complete-final bundle did not materialize simulator/validation.py")
exec(compile(_SOURCE, str(_TARGET), "exec"), globals(), globals())
