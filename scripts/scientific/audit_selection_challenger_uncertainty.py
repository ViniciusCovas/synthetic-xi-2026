#!/usr/bin/env python3
"""Audit frozen uncertainty bounds after resolving the 41 selection challengers.

This script never adjusts an ability, uncertainty, role, threshold, or ranking.
It verifies that the canonical gate recomputed the same 90% bounds from the
frozen inputs and reports whether only evidence coverage changed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

Z90 = 1.6448536269514722
AUDIT_DIR = Path("data/audits/selection_challenger_resolution")
BEFORE = AUDIT_DIR / "frozen_unresolved_before.csv"
AFTER = Path("data/model_readiness/selection_sufficiency_all_players.csv")
STATUS = Path("data/model_readiness/selection_sufficiency_status.json")
OUT = AUDIT_DIR / "uncertainty_bound_recalculation.csv"
SUMMARY = AUDIT_DIR / "uncertainty_bound_audit.json"
TOL = 1e-12


def num(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column), errors="coerce")


def max_abs(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().abs()
    return float(values.max()) if not values.empty else 0.0


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if not BEFORE.exists() or not AFTER.exists() or not STATUS.exists():
        raise SystemExit("Frozen before snapshot or rebuilt gate output is missing")

    before = pd.read_csv(BEFORE, low_memory=False)
    after = pd.read_csv(AFTER, low_memory=False)
    before["player_id"] = pd.to_numeric(before.player_id, errors="coerce")
    after["player_id"] = pd.to_numeric(after.player_id, errors="coerce")
    before = before.dropna(subset=["player_id"]).copy()
    after = after.dropna(subset=["player_id"]).copy()
    before["player_id"] = before.player_id.astype(int)
    after["player_id"] = after.player_id.astype(int)
    before = before.drop_duplicates("player_id")
    after = after.loc[after.player_id.isin(set(before.player_id))].drop_duplicates("player_id")
    merged = before.merge(after, on="player_id", how="left", suffixes=("_before", "_after"), validate="one_to_one")

    compared = ["overall", "uncertainty", "lo90", "hi90", "top30_lower_threshold", "best_lower_threshold"]
    missing_columns = [
        f"{column}_{side}"
        for column in compared
        for side in ("before", "after")
        if f"{column}_{side}" not in merged.columns
    ]
    if missing_columns:
        raise SystemExit(f"Required frozen comparison columns missing: {missing_columns}")

    for column in compared:
        merged[f"{column}_before"] = num(merged, f"{column}_before")
        merged[f"{column}_after"] = num(merged, f"{column}_after")
        merged[f"{column}_delta"] = merged[f"{column}_after"] - merged[f"{column}_before"]

    merged["lo90_recalculated"] = (
        merged.overall_after - Z90 * merged.uncertainty_after.clip(0.025, 0.35)
    ).clip(0, 1)
    merged["hi90_recalculated"] = (
        merged.overall_after + Z90 * merged.uncertainty_after.clip(0.025, 0.35)
    ).clip(0, 1)
    merged["lo90_formula_error"] = merged.lo90_after - merged.lo90_recalculated
    merged["hi90_formula_error"] = merged.hi90_after - merged.hi90_recalculated
    merged["covered_before"] = merged.get("covered_before", False)
    merged["covered_after"] = merged.get("covered_after", False)
    merged.to_csv(OUT, index=False)

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    checks = {
        "all_41_present_after": int(merged.overall_after.notna().sum()) == int(len(before)) == 41,
        "overall_unchanged": max_abs(merged.overall_delta) <= TOL,
        "uncertainty_unchanged": max_abs(merged.uncertainty_delta) <= TOL,
        "top30_thresholds_unchanged": max_abs(merged.top30_lower_threshold_delta) <= TOL,
        "best_xi_thresholds_unchanged": max_abs(merged.best_lower_threshold_delta) <= TOL,
        "lo90_formula_exact": max_abs(merged.lo90_formula_error) <= TOL,
        "hi90_formula_exact": max_abs(merged.hi90_formula_error) <= TOL,
    }
    audit_passed = all(checks.values())
    summary = {
        "status": "selection_challenger_uncertainty_audited",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_challengers": int(len(before)),
        "checks": checks,
        "audit_passed": audit_passed,
        "model_parameters_changed": not (
            checks["overall_unchanged"] and checks["uncertainty_unchanged"]
        ),
        "selection_thresholds_changed": not (
            checks["top30_thresholds_unchanged"] and checks["best_xi_thresholds_unchanged"]
        ),
        "maximum_absolute_deltas": {
            "overall": max_abs(merged.overall_delta),
            "uncertainty": max_abs(merged.uncertainty_delta),
            "top30_lower_threshold": max_abs(merged.top30_lower_threshold_delta),
            "best_lower_threshold": max_abs(merged.best_lower_threshold_delta),
            "lo90_formula_error": max_abs(merged.lo90_formula_error),
            "hi90_formula_error": max_abs(merged.hi90_formula_error),
        },
        "selection_sufficiency_gate_passed": bool(status.get("selection_sufficiency_gate_passed", False)),
        "unresolved_players_after": int(status.get("unresolved_players", -1)),
        "output": str(OUT),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not audit_passed:
        raise SystemExit("Frozen model or uncertainty thresholds changed unexpectedly")


if __name__ == "__main__":
    main()
