#!/usr/bin/env python3
"""Audit the final selection blocker without making network requests.

This module is diagnostic only. It does not change rankings, thresholds, player
eligibility, role assignments, or scientific gates. It produces transparent
reports that help prioritize the next targeted extraction cycle.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path("data/model_readiness")
AUDIT_DIR = Path("data/audits/offline_readiness")
UNRESOLVED_PATH = MODEL_DIR / "selection_sufficiency_unresolved_players.csv"
STATUS_PATH = MODEL_DIR / "selection_sufficiency_status.json"
PRIORITY_FIXTURES_PATH = MODEL_DIR / "selection_sufficiency_priority_fixtures.csv"

REASON_WEIGHT = {
    "covered_pool_shortage": 6.0,
    "upper90_can_enter_real_xi": 5.0,
    "high_ability_role_stabilization": 4.5,
    "upper90_can_enter_top30": 3.5,
    "top35_guardrail": 2.5,
}


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def numeric(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def add_consistency_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    cov_a = numeric(out, "cov_annual_current")
    cov_p = numeric(out, "cov_pre_world_cup")
    miss_a = numeric(out, "miss_annual_current", 0).fillna(0)
    miss_p = numeric(out, "miss_pre_world_cup", 0).fillna(0)
    pass_a = as_bool(out.get("pass_annual_current", pd.Series(False, index=out.index)))
    pass_p = as_bool(out.get("pass_pre_world_cup", pd.Series(False, index=out.index)))
    covered = as_bool(out.get("covered", pd.Series(False, index=out.index)))
    role_stability = numeric(out, "role_stability")
    stable = as_bool(out.get("stable", pd.Series(False, index=out.index)))

    out["anomaly_cov80_but_annual_fail"] = cov_a.ge(0.8) & ~pass_a
    out["anomaly_cov80_but_prewc_fail"] = cov_p.ge(0.8) & ~pass_p
    out["anomaly_zero_missing_but_annual_fail"] = miss_a.eq(0) & ~pass_a
    out["anomaly_zero_missing_but_prewc_fail"] = miss_p.eq(0) & ~pass_p
    out["anomaly_both_windows_pass_but_not_covered"] = pass_a & pass_p & ~covered
    out["anomaly_covered_without_both_windows"] = covered & ~(pass_a & pass_p)
    out["anomaly_role_stability_flag"] = role_stability.ge(0.6).ne(stable)
    return out


def role_shortage(status: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in status.get("roles", []):
        required = max(float(row.get("required_pool_size", 0)), 1.0)
        covered = float(row.get("covered_candidates", 0))
        unresolved = float(row.get("unresolved_challengers", 0))
        shortage = max(0.0, required - covered) / required
        unresolved_pressure = unresolved / max(required, 1.0)
        values[str(row.get("role"))] = shortage + 0.25 * unresolved_pressure
    return values


def score_challengers(frame: pd.DataFrame, status: dict) -> pd.DataFrame:
    out = frame.copy()
    shortage = role_shortage(status)
    lo90 = numeric(out, "lo90")
    hi90 = numeric(out, "hi90")
    best = numeric(out, "best_lower_threshold")
    top30 = numeric(out, "top30_lower_threshold")
    uncertainty_width = (hi90 - lo90).clip(lower=0).fillna(0)
    xi_margin = (hi90 - best).fillna(0).clip(lower=-1, upper=1)
    top30_margin = (hi90 - top30).fillna(0).clip(lower=-1, upper=1)
    role_pressure = out.get("resolved_role", pd.Series("", index=out.index)).map(shortage).fillna(0)
    reason_score = out.get("reason", pd.Series("", index=out.index)).map(REASON_WEIGHT).fillna(1.0)
    missing = numeric(out, "miss_annual_current", 0).fillna(0) + numeric(out, "miss_pre_world_cup", 0).fillna(0)
    missing_signal = np.log1p(missing)

    out["decision_priority_score"] = (
        reason_score
        + 2.0 * role_pressure
        + 1.5 * uncertainty_width
        + 0.75 * xi_margin.clip(lower=0)
        + 0.35 * top30_margin.clip(lower=0)
        + 0.15 * missing_signal
    )
    out["uncertainty_width_90"] = uncertainty_width
    out["role_gate_pressure"] = role_pressure
    out["missing_fixture_count"] = missing
    keep = [
        "player_id", "player_name", "world_cup_team", "resolved_role", "reason",
        "decision_priority_score", "role_gate_pressure", "uncertainty_width_90",
        "lo90", "hi90", "best_lower_threshold", "top30_lower_threshold",
        "rank", "urank", "missing_fixture_count", "cov_annual_current",
        "cov_pre_world_cup", "role_stability", "stable",
    ]
    keep = [column for column in keep if column in out.columns]
    return out.sort_values(["decision_priority_score", "player_id"], ascending=[False, True])[keep]


def prioritize_fixtures(players: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if not PRIORITY_FIXTURES_PATH.exists():
        return pd.DataFrame(), {"status": "priority_fixture_file_missing"}
    fixtures = pd.read_csv(PRIORITY_FIXTURES_PATH)
    if fixtures.empty:
        return fixtures, {"status": "priority_fixture_file_empty"}

    score_map = players.set_index(players["player_id"].astype(str))["decision_priority_score"].to_dict()
    player_column = next((c for c in ("player_id", "target_player_id", "challenger_player_id") if c in fixtures.columns), None)
    fixture_column = next((c for c in ("fixture_id", "target_fixture_id") if c in fixtures.columns), None)
    if player_column is None or fixture_column is None:
        return fixtures, {
            "status": "priority_fixture_schema_not_joinable",
            "columns": fixtures.columns.tolist(),
        }

    working = fixtures.copy()
    working["_player_key"] = working[player_column].astype(str)
    working["player_decision_priority"] = working["_player_key"].map(score_map).fillna(0.0)
    aggregation = working.groupby(fixture_column, as_index=False).agg(
        unresolved_players=("_player_key", "nunique"),
        max_player_priority=("player_decision_priority", "max"),
        total_player_priority=("player_decision_priority", "sum"),
    )
    aggregation["information_value_score"] = (
        aggregation["max_player_priority"]
        + 0.45 * aggregation["total_player_priority"]
        + 0.8 * np.log1p(aggregation["unresolved_players"])
    )
    aggregation = aggregation.sort_values(
        ["information_value_score", "unresolved_players", fixture_column],
        ascending=[False, False, True],
    )
    return aggregation, {
        "status": "fixture_information_value_queue_built",
        "fixture_column": fixture_column,
        "player_column": player_column,
        "fixtures": int(aggregation[fixture_column].nunique()),
        "player_fixture_pairs": int(len(working)),
    }


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if not UNRESOLVED_PATH.exists() or not STATUS_PATH.exists():
        result = {
            "status": "waiting_for_selection_sufficiency_outputs",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        (AUDIT_DIR / "offline_readiness_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    unresolved = pd.read_csv(UNRESOLVED_PATH)
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    flagged = add_consistency_flags(unresolved)
    prioritized = score_challengers(flagged, status)
    fixture_queue, fixture_status = prioritize_fixtures(prioritized)

    reason_distribution = (
        flagged.groupby(["resolved_role", "reason"], dropna=False)
        .size().reset_index(name="players")
        .sort_values(["players", "resolved_role"], ascending=[False, True])
    )
    overall_reasons = Counter(flagged.get("reason", pd.Series(dtype=str)).fillna("unknown"))
    anomaly_columns = [c for c in flagged.columns if c.startswith("anomaly_")]
    anomaly_counts = {c: int(as_bool(flagged[c]).sum()) for c in anomaly_columns}

    duplicate_player_ids = int(flagged.duplicated("player_id", keep=False).sum()) if "player_id" in flagged else 0
    duplicate_names = int(flagged.duplicated(["player_name", "world_cup_team"], keep=False).sum()) if {"player_name", "world_cup_team"}.issubset(flagged.columns) else 0

    flagged.to_csv(AUDIT_DIR / "unresolved_players_with_consistency_flags.csv", index=False)
    reason_distribution.to_csv(AUDIT_DIR / "unresolved_reason_by_role.csv", index=False)
    prioritized.to_csv(AUDIT_DIR / "selection_challenger_priority.csv", index=False)
    if not fixture_queue.empty:
        fixture_queue.to_csv(AUDIT_DIR / "fixture_information_value_queue.csv", index=False)

    result = {
        "status": "offline_selection_readiness_audit_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "methodological_effect": "diagnostic_only_no_gate_or_ranking_changes",
        "eligible_candidates": int(status.get("eligible_candidates", 0)),
        "fully_covered_both_windows": int(status.get("fully_covered_both_windows", 0)),
        "unresolved_players": int(len(flagged)),
        "priority_unique_fixtures_declared": int(status.get("priority_unique_fixtures", 0)),
        "reason_counts": dict(sorted(overall_reasons.items())),
        "anomaly_counts": anomaly_counts,
        "duplicate_rows": {
            "rows_with_duplicated_player_id": duplicate_player_ids,
            "rows_with_duplicated_player_name_and_team": duplicate_names,
        },
        "fixture_queue": fixture_status,
        "next_action": "review anomalies and consume fixtures in information-value order after quota reset",
    }
    (AUDIT_DIR / "offline_readiness_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
