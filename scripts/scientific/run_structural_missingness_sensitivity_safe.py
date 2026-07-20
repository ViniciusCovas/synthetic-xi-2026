#!/usr/bin/env python3
"""Run the structural-missingness audit with schema-safe output selection."""
from pathlib import Path

source_path = Path("scripts/scientific/build_structural_missingness_sensitivity.py")
source = source_path.read_text(encoding="utf-8")
source = source.replace(
    'unresolved[keep].to_csv(ROOT / "structural_missingness_player_bounds.csv", index=False)',
    'unresolved[[column for column in keep if column in unresolved.columns]].to_csv(ROOT / "structural_missingness_player_bounds.csv", index=False)',
)
exec(compile(source, str(source_path), "exec"), {"__name__": "__main__", "__file__": str(source_path)})
