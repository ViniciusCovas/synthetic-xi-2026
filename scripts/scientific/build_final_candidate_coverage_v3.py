#!/usr/bin/env python3
"""Evaluate 90% exact-window coverage for promoted ontology-v3 candidates.

Coverage is an eligibility criterion, not a ranking adjustment. A candidate passes only
when both fixture-endpoint coverage and the known-minute lower bound are at least 90%
in the annual-current and pre-World-Cup windows. No missing value is treated as covered.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3")
ONTOLOGY_STATUS = ROOT / "ontology_v3_status.json"
PROMOTED = ROOT / "promoted_player_roles_uncovered.csv"
COVERAGE = Path("data/audits/scope_correct_coverage/player_window_coverage_scope_correct.csv")
FINAL = ROOT / "final_player_roles.csv"
UNRESOLVED = ROOT / "final_candidate_coverage_unresolved.csv"
STATUS = ROOT / "final_candidate_coverage_status.json"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
WINDOWS = ["annual_current", "pre_world_cup"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def write_blocked(reason: str, details: dict | None = None) -> None:
    payload = {
        "status": "final_candidate_coverage_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "details": details or {},
        "final_candidate_coverage_gate_passed": False,
        "final_team_construction_allowed": False,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    ontology = load_json(ONTOLOGY_STATUS)
    if not ontology.get("final_ontology_gate_passed", False):
        write_blocked("ontology-v3 has not passed promotion", ontology)
        return
    missing = [str(path) for path in [PROMOTED, COVERAGE] if not path.exists()]
    if missing:
        write_blocked("coverage inputs are missing", {"missing_files": missing})
        return

    candidates = pd.read_csv(PROMOTED, low_memory=False)
    coverage = pd.read_csv(COVERAGE, low_memory=False)
    for frame in (candidates, coverage):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)
    candidates["final_role_eligible_before_coverage"] = as_bool(
        candidates.get("final_role_eligible_before_coverage", pd.Series(False, index=candidates.index))
    )

    for window in WINDOWS:
        block = coverage.loc[coverage.window.astype(str).eq(window)].copy()
        block["fixture_endpoint_coverage"] = pd.to_numeric(
            block.get("fixture_endpoint_coverage"), errors="coerce"
        )
        block["known_minute_coverage_lower_bound"] = pd.to_numeric(
            block.get("known_minute_coverage_lower_bound"), errors="coerce"
        )
        block["missing_fixture_endpoints"] = pd.to_numeric(
            block.get("missing_fixture_endpoints"), errors="coerce"
        ).fillna(0).astype(int)
        block["known_missing_startXI_fixtures"] = pd.to_numeric(
            block.get("known_missing_startXI_fixtures"), errors="coerce"
        ).fillna(0).astype(int)
        block["exact_detailed_minutes"] = pd.to_numeric(
            block.get("exact_detailed_minutes"), errors="coerce"
        ).fillna(0.0)
        block = block.sort_values(
            ["player_id", "fixture_endpoint_coverage", "known_minute_coverage_lower_bound"],
            ascending=[True, False, False],
        ).drop_duplicates("player_id")
        block[f"coverage_pass_90_{window}"] = (
            block.fixture_endpoint_coverage.ge(0.90)
            & block.known_minute_coverage_lower_bound.ge(0.90)
        )
        block = block.rename(columns={
            "fixture_endpoint_coverage": f"fixture_coverage_{window}",
            "known_minute_coverage_lower_bound": f"known_minute_coverage_{window}",
            "missing_fixture_endpoints": f"missing_fixture_endpoints_{window}",
            "known_missing_startXI_fixtures": f"missing_startXI_{window}",
            "exact_detailed_minutes": f"exact_detailed_minutes_{window}",
        })
        columns = [
            "player_id", f"fixture_coverage_{window}", f"known_minute_coverage_{window}",
            f"missing_fixture_endpoints_{window}", f"missing_startXI_{window}",
            f"exact_detailed_minutes_{window}", f"coverage_pass_90_{window}",
        ]
        candidates = candidates.merge(block[columns], on="player_id", how="left")
        candidates[f"coverage_pass_90_{window}"] = as_bool(
            candidates.get(f"coverage_pass_90_{window}", pd.Series(False, index=candidates.index))
        )

    candidates["coverage_pass_90pct"] = (
        candidates.coverage_pass_90_annual_current
        & candidates.coverage_pass_90_pre_world_cup
    )
    candidates["final_candidate_eligible"] = (
        candidates.final_role_eligible_before_coverage & candidates.coverage_pass_90pct
    )
    candidates["coverage_exclusion_reason"] = ""
    candidates.loc[
        ~candidates.coverage_pass_90_annual_current,
        "coverage_exclusion_reason",
    ] += "annual_current_coverage_lt_0_90;"
    candidates.loc[
        ~candidates.coverage_pass_90_pre_world_cup,
        "coverage_exclusion_reason",
    ] += "pre_world_cup_coverage_lt_0_90;"
    candidates = candidates.sort_values(["final_role", "player_id"])
    FINAL.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(FINAL, index=False)

    unresolved = candidates.loc[
        candidates.final_role_eligible_before_coverage & ~candidates.coverage_pass_90pct
    ].copy()
    unresolved.to_csv(UNRESOLVED, index=False)
    eligible = candidates.loc[candidates.final_candidate_eligible].copy()
    counts = (
        eligible.groupby("final_role").player_id.nunique()
        .reindex(ROLES, fill_value=0).astype(int).to_dict()
    )
    high_impact = as_bool(candidates.get(
        "high_impact_current_release", pd.Series(False, index=candidates.index)
    ))
    uncovered_high_impact = int((
        candidates.final_role_eligible_before_coverage & high_impact & ~candidates.coverage_pass_90pct
    ).sum())
    gate = bool(
        all(count >= 20 for count in counts.values())
        and uncovered_high_impact == 0
    )
    status = {
        "status": "final_candidate_coverage_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_definition": (
            ">=90% fixture endpoint coverage and >=90% known-minute lower bound "
            "in annual_current and pre_world_cup windows"
        ),
        "promoted_candidates_before_coverage": int(candidates.final_role_eligible_before_coverage.sum()),
        "fully_covered_final_candidates": int(len(eligible)),
        "unresolved_coverage_candidates": int(len(unresolved)),
        "covered_candidates_by_role": counts,
        "minimum_20_covered_candidates_each_role": all(count >= 20 for count in counts.values()),
        "uncovered_high_impact_candidates": uncovered_high_impact,
        "final_candidate_coverage_gate_passed": gate,
        "final_team_construction_allowed": gate,
        "final_player_table": str(FINAL),
        "unresolved_table": str(UNRESOLVED),
        "next_action": (
            "build and hash exactly one Real XI and one AI XI"
            if gate else "extract only missing exact-window endpoints for unresolved promoted candidates"
        ),
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
