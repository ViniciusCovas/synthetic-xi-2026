#!/usr/bin/env python3
"""Run targeted extraction and persist a diagnostic status on any exception."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone

from scripts.run_adaptive_annual_extraction import AUDIT_DIR
from scripts.run_batched_selection_extraction import main


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        status = {
            "status": "batched_targeted_extraction_failed",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:2000],
            "traceback_tail": traceback.format_exc()[-6000:],
            "network_calls": None,
            "rankings_allowed": False,
        }
        (AUDIT_DIR / "targeted_coverage_extraction_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        raise
