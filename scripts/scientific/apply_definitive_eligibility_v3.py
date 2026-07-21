#!/usr/bin/env python3
"""Apply the frozen definitive eligibility rule to ontology-v3 primary roles.

This step separates positional evidence from study eligibility. A candidate is eligible
only with at least 1,800 exact-window total minutes, 900 minutes in one primary role,
three complete-lineup observations and a primary-role share of at least 60%.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3")
PRIMARY = ROOT / "complete_lineup_primary_roles.csv"
STATUS = ROOT / "lineup_completeness_status.json"
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    if not PRIMARY.exists() or not FRONTIER.exists():
        raise FileNotFoundError("primary-role evidence or selection frontier is missing")
    primary = pd.read_csv(PRIMARY, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    for frame in (primary, frontier):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    minute_column = next(
        (name for name in ["minutes_num", "reported_minutes", "minutes"] if name in frontier),
        None,
    )
    if minute_column is None:
        raise RuntimeError("selection frontier lacks an exact-window total-minutes column")
    frontier["exact_window_total_minutes"] = pd.to_numeric(
        frontier[minute_column], errors="coerce"
    ).fillna(0.0)
    totals = (
        frontier.sort_values(["player_id", "exact_window_total_minutes"], ascending=[True, False])
        .drop_duplicates("player_id")[["player_id", "exact_window_total_minutes"]]
    )
    primary = primary.drop(columns=["exact_window_total_minutes"], errors="ignore").merge(
        totals, on="player_id", how="left"
    )
    primary["exact_window_total_minutes"] = pd.to_numeric(
        primary.exact_window_total_minutes, errors="coerce"
    ).fillna(0.0)
    for column in [
        "primary_role_minutes", "primary_role_observations", "primary_role_share"
    ]:
        primary[column] = pd.to_numeric(primary.get(column), errors="coerce").fillna(0.0)
    primary["positional_gate_passed"] = (
        primary.primary_role_minutes.ge(900)
        & primary.primary_role_observations.ge(3)
        & primary.primary_role_share.ge(0.60)
        & primary.primary_role.isin(ROLES)
    )
    primary["total_minutes_gate_passed"] = primary.exact_window_total_minutes.ge(1800)
    primary["primary_role_eligible"] = (
        primary.positional_gate_passed & primary.total_minutes_gate_passed
    )
    primary.to_csv(PRIMARY, index=False)

    eligible = primary.loc[primary.primary_role_eligible].copy()
    counts = (
        eligible.groupby("primary_role").player_id.nunique()
        .reindex(ROLES, fill_value=0).astype(int).to_dict()
    )
    status = load_json(STATUS)
    status.update({
        "status": "complete_lineup_position_evidence_and_eligibility_audited",
        "eligibility_updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_role_eligible_players": int(len(eligible)),
        "eligible_primary_candidates_by_role": counts,
        "all_roles_have_20_primary_candidates": all(count >= 20 for count in counts.values()),
        "eligibility_policy": (
            "one primary role per player; >=1800 exact-window total minutes; "
            ">=900 primary-role minutes; >=3 observations; >=60% of classified role minutes"
        ),
        "next_action": (
            "build the ontology-v3 blind-review packet"
            if all(count >= 20 for count in counts.values())
            else "extract more complete lineups for deficient roles; total-minute failures cannot be repaired by lineup extraction"
        ),
    })
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
