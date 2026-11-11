#!/usr/bin/env python3
"""Recover complete line-ups only for currently deficient primary-role pools.

This outcome-blind extraction phase reads the strict ontology-v3 audit and prioritizes
players whose current primary role belongs to a pool with fewer than 20 eligible
candidates. Near-threshold candidates (300-899 primary-role minutes) are processed
first. The script reuses the provider client and durable storage format from the general
priority extractor.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.scientific.extract_full_lineups_priority import (
    BATCH,
    PRIORITY,
    PROGRESS,
    STATUS,
    Client,
    QuotaStop,
    flatten,
    load_progress,
)

AUDIT_STATUS = Path("data/audits/position_ontology_v3/lineup_completeness_status.json")
PRIMARY = Path("data/audits/position_ontology_v3/complete_lineup_primary_roles.csv")
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
MINIMUM = 20


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def normalized_role(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def candidate_focus(priority: pd.DataFrame, deficient: set[str]) -> pd.DataFrame:
    ids = pd.to_numeric(priority.player_id, errors="coerce").dropna().astype(int).unique()
    focus = pd.DataFrame({"player_id": ids})
    focus["primary_role"] = pd.NA
    focus["primary_role_minutes"] = 0.0
    focus["frontier_role"] = pd.NA

    if PRIMARY.exists():
        primary = pd.read_csv(PRIMARY, low_memory=False)
        primary["player_id"] = pd.to_numeric(primary.get("player_id"), errors="coerce")
        primary = primary.dropna(subset=["player_id"]).copy()
        primary["player_id"] = primary.player_id.astype(int)
        primary["primary_role"] = normalized_role(primary.get("primary_role"))
        primary["primary_role_minutes"] = pd.to_numeric(
            primary.get("primary_role_minutes"), errors="coerce"
        ).fillna(0.0)
        primary = primary.sort_values(
            ["player_id", "primary_role_minutes"], ascending=[True, False]
        ).drop_duplicates("player_id")
        focus = focus.drop(columns=["primary_role", "primary_role_minutes"]).merge(
            primary[["player_id", "primary_role", "primary_role_minutes"]],
            on="player_id", how="left",
        )

    if FRONTIER.exists():
        frontier = pd.read_csv(FRONTIER, low_memory=False)
        frontier["player_id"] = pd.to_numeric(frontier.get("player_id"), errors="coerce")
        frontier = frontier.dropna(subset=["player_id"]).copy()
        frontier["player_id"] = frontier.player_id.astype(int)
        role_column = "resolved_role" if "resolved_role" in frontier else "role"
        frontier["frontier_role"] = normalized_role(frontier.get(role_column))
        frontier = frontier.sort_values("player_id").drop_duplicates("player_id")
        focus = focus.drop(columns=["frontier_role"]).merge(
            frontier[["player_id", "frontier_role"]], on="player_id", how="left"
        )

    focus["primary_role_minutes"] = pd.to_numeric(
        focus.primary_role_minutes, errors="coerce"
    ).fillna(0.0)
    focus["deficient_primary"] = focus.primary_role.isin(deficient)
    focus["deficient_frontier"] = focus.frontier_role.isin(deficient)
    focus["deficient_candidate"] = focus.deficient_primary | focus.deficient_frontier
    focus["near_threshold"] = (
        focus.deficient_primary
        & focus.primary_role_minutes.ge(300)
        & focus.primary_role_minutes.lt(900)
    )
    focus["distance_to_900"] = (900.0 - focus.primary_role_minutes).clip(lower=0.0)
    return focus


def main() -> None:
    audit = load_json(AUDIT_STATUS)
    counts = audit.get("eligible_primary_candidates_by_role", {})
    deficient = {role for role in ROLES if int(counts.get(role, 0) or 0) < MINIMUM}
    if not deficient:
        status = {
            "status": "deficit_role_extraction_not_required",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "network_calls": 0,
            "eligible_primary_candidates_by_role": {
                role: int(counts.get(role, 0) or 0) for role in ROLES
            },
            "deficient_roles": [],
            "next_action": "build the ontology-v3 blind-review packet",
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
    if not PRIORITY.exists():
        raise RuntimeError("run audit_complete_lineups_v3.py before deficit extraction")

    priority = pd.read_csv(PRIORITY, low_memory=False)
    priority["fixture_id"] = pd.to_numeric(priority.get("fixture_id"), errors="coerce")
    priority["player_id"] = pd.to_numeric(priority.get("player_id"), errors="coerce")
    priority["minutes_observed"] = pd.to_numeric(
        priority.get("minutes_observed"), errors="coerce"
    ).fillna(0.0)
    priority = priority.dropna(subset=["fixture_id", "player_id"]).copy()
    priority["fixture_id"] = priority.fixture_id.astype(int)
    priority["player_id"] = priority.player_id.astype(int)
    priority["high_impact_current_release"] = (
        priority.get("high_impact_current_release", False)
        .astype(str).str.lower().isin({"true", "1", "yes"})
    )

    focus = candidate_focus(priority, deficient)
    priority = priority.merge(focus, on="player_id", how="left")
    priority = priority.loc[priority.deficient_candidate.fillna(False)].copy()
    if priority.empty:
        raise RuntimeError(f"no remaining priority appearances for deficient roles: {sorted(deficient)}")

    queue = priority.groupby("fixture_id", as_index=False).agg(
        near_threshold_players=("near_threshold", "sum"),
        deficient_primary_players=("deficient_primary", "sum"),
        deficient_frontier_players=("deficient_frontier", "sum"),
        high_impact_players=("high_impact_current_release", "sum"),
        closest_distance_to_900=("distance_to_900", "min"),
        candidate_minutes=("minutes_observed", "sum"),
    )
    queue = queue.sort_values(
        [
            "near_threshold_players", "deficient_primary_players",
            "deficient_frontier_players", "high_impact_players",
            "closest_distance_to_900", "candidate_minutes", "fixture_id",
        ],
        ascending=[False, False, False, False, True, False, True],
    )

    progress = load_progress()
    completed = set(
        progress.loc[progress.status.isin(["completed", "endpoint_empty"]), "fixture_id"]
        .astype(int)
    )
    queue = queue.loc[~queue.fixture_id.isin(completed)].copy()

    client = Client()
    new_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    quota_stopped = False
    for item in queue.itertuples(index=False):
        fixture_id = int(item.fixture_id)
        try:
            payload = client.lineups(fixture_id)
            rows = flatten(fixture_id, payload)
            result_status = "completed" if rows else "endpoint_empty"
            new_rows.extend(rows)
            progress_rows.append({
                "fixture_id": fixture_id,
                "status": result_status,
                "rows": len(rows),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            print(
                f"fixture={fixture_id} rows={len(rows)} near={item.near_threshold_players} "
                f"deficient={item.deficient_primary_players} calls={client.calls} "
                f"remaining={client.remaining}"
            )
        except QuotaStop as exc:
            quota_stopped = True
            print(str(exc))
            break
        except Exception as exc:
            errors.append({"fixture_id": fixture_id, "error": str(exc)})
            progress_rows.append({
                "fixture_id": fixture_id,
                "status": "error",
                "rows": 0,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            })

    new = pd.DataFrame(new_rows)
    if BATCH.exists():
        old = pd.read_csv(BATCH, low_memory=False)
        combined = pd.concat([old, new], ignore_index=True) if not new.empty else old
    else:
        combined = new
    if combined.empty:
        combined = pd.DataFrame(columns=[
            "fixture_id", "team_id", "team_name", "formation", "lineup_source",
            "player_id", "player_name", "number", "lineup_position", "grid",
            "full_lineup_provider_recovery",
        ])
    else:
        combined = combined.drop_duplicates(
            ["fixture_id", "team_id", "lineup_source", "player_id"], keep="last"
        ).sort_values(["fixture_id", "team_id", "lineup_source", "player_id"])
    BATCH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(BATCH, index=False, compression="gzip")

    updated_progress = pd.concat([progress, pd.DataFrame(progress_rows)], ignore_index=True)
    updated_progress = updated_progress.drop_duplicates("fixture_id", keep="last")
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    updated_progress.to_csv(PROGRESS, index=False)

    starters = combined.loc[combined.lineup_source.eq("startXI")]
    groups = (
        starters.groupby(["fixture_id", "team_id"]).player_id.nunique()
        if not starters.empty else pd.Series(dtype=int)
    )
    status = {
        "status": "deficit_role_full_lineup_extraction_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "priority_policy": {
            "deficient_roles_at_batch_start": sorted(deficient),
            "primary": "300-899 primary-role minutes in a deficient role",
            "secondary": "other players whose primary or frontier role is deficient",
            "outcome_blind": True,
        },
        "network_calls": client.calls,
        "provider_remaining": client.remaining,
        "quota_stopped": quota_stopped,
        "queue_before_batch": int(len(queue)),
        "fixtures_processed_this_batch": int(len(progress_rows)),
        "new_rows_this_batch": int(len(new)),
        "total_recovered_rows": int(len(combined)),
        "total_fixture_team_groups": int(len(groups)),
        "groups_with_exactly_11_starters": int(groups.eq(11).sum()),
        "errors": errors[:100],
        "remaining_deficit_priority_fixtures": int(max(0, len(queue) - len(progress_rows))),
        "output_batch": str(BATCH),
        "progress_file": str(PROGRESS),
        "next_action": "rerun strict ontology-v3 primary-role audit",
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
