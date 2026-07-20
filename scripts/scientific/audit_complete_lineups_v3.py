#!/usr/bin/env python3
"""Audit role evidence using only structurally complete starting line-ups.

The v2 audit interpreted partial team grids as full formations. This script rejects any
fixture-team line-up unless it has exactly 11 unique starters, one goalkeeper row and
outfield row sizes matching the declared formation. It creates extraction priorities
for relevant candidates whose appearances lack a complete line-up.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

OUT = Path("data/audits/position_ontology_v3")
BATCH = Path("data/lake/batches")
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
REAL = Path("data/simulations/identified_set_v1/real_identified_set_membership.csv")
SYNTHETIC = Path("data/simulations/identified_set_v1/synthetic_avatar_membership.csv")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]

FORMATION_TEMPLATES: dict[str, list[list[str]]] = {
    "4-3-3": [["LB", "LCB", "RCB", "RB"], ["CM", "DM", "CM"], ["LW", "ST", "RW"]],
    "4-2-3-1": [["LB", "LCB", "RCB", "RB"], ["DM", "DM"], ["LW", "AM", "RW"], ["ST"]],
    "4-1-4-1": [["LB", "LCB", "RCB", "RB"], ["DM"], ["LW", "CM", "CM", "RW"], ["ST"]],
    "4-4-2": [["LB", "LCB", "RCB", "RB"], ["LW", "CM", "CM", "RW"], ["ST", "ST"]],
    "4-3-1-2": [["LB", "LCB", "RCB", "RB"], ["CM", "DM", "CM"], ["AM"], ["ST", "ST"]],
    "4-2-2-2": [["LB", "LCB", "RCB", "RB"], ["DM", "DM"], ["AM", "AM"], ["ST", "ST"]],
    "4-2-4": [["LB", "LCB", "RCB", "RB"], ["DM", "CM"], ["LW", "ST", "ST", "RW"]],
    "4-1-2-3": [["LB", "LCB", "RCB", "RB"], ["DM"], ["CM", "CM"], ["LW", "ST", "RW"]],
    "3-5-2": [["LCB", "CB", "RCB"], ["LB", "CM", "DM", "CM", "RB"], ["ST", "ST"]],
    "3-4-2-1": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["AM", "AM"], ["ST"]],
    "3-4-1-2": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["AM"], ["ST", "ST"]],
    "3-4-3": [["LCB", "CB", "RCB"], ["LB", "CM", "CM", "RB"], ["LW", "ST", "RW"]],
    "5-3-2": [["LB", "LCB", "CB", "RCB", "RB"], ["CM", "DM", "CM"], ["ST", "ST"]],
    "5-4-1": [["LB", "LCB", "CB", "RCB", "RB"], ["LW", "CM", "CM", "RW"], ["ST"]],
    "4-5-1": [["LB", "LCB", "RCB", "RB"], ["LW", "CM", "DM", "CM", "RW"], ["ST"]],
}


def read_many(pattern: str, columns: set[str]) -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(pattern)):
        try:
            frame = pd.read_csv(path, low_memory=False, usecols=lambda name: name in columns)
        except Exception:
            continue
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def num(frame: pd.DataFrame, names: list[str], default=None) -> pd.Series:
    for name in names:
        if name in frame:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(default, index=frame.index, dtype=float)


def text(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name].astype("string")
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def parse_grid(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    try:
        left, right = value.split(":", 1)
        return int(float(left)), int(float(right))
    except ValueError:
        return None, None


def normalize_formation(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().replace(" ", "")


def candidate_ids() -> tuple[set[int], set[int]]:
    relevant: set[int] = set()
    high_impact: set[int] = set()
    if FRONTIER.exists():
        frame = pd.read_csv(FRONTIER, low_memory=False)
        ids = pd.to_numeric(frame.get("player_id"), errors="coerce").dropna().astype(int)
        relevant.update(ids)
    for path in (REAL, SYNTHETIC):
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        ids = pd.to_numeric(frame.get("player_id"), errors="coerce").dropna().astype(int)
        high_impact.update(ids)
        relevant.update(ids)
    return relevant, high_impact


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lineup_cols = {"fixture_id", "team_id", "player_id", "player_name", "formation", "grid", "lineup_source"}
    player_cols = {"fixture_id", "team_id", "player_id", "player_name", "minutes", "minutes_num"}
    lineups = read_many(str(BATCH / "batch_*_lineups.csv*"), lineup_cols)
    players = read_many(str(BATCH / "batch_*_players.csv*"), player_cols)
    if lineups.empty:
        raise RuntimeError("No durable lineup rows were found")

    for frame in (lineups, players):
        for key in ("fixture_id", "team_id", "player_id"):
            frame[key] = pd.to_numeric(frame.get(key), errors="coerce")
        frame.dropna(subset=["fixture_id", "team_id", "player_id"], inplace=True)
        for key in ("fixture_id", "team_id", "player_id"):
            frame[key] = frame[key].astype(int)

    lineups = lineups.loc[text(lineups, ["lineup_source"]).str.lower().eq("startxi")].copy()
    lineups = lineups.drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
    lineups["formation_norm"] = text(lineups, ["formation"]).map(normalize_formation)
    parsed = text(lineups, ["grid"]).apply(parse_grid)
    lineups["grid_row"] = parsed.apply(lambda item: item[0])
    lineups["grid_col"] = parsed.apply(lambda item: item[1])

    players["minutes_observed"] = num(players, ["minutes", "minutes_num"], 0.0).fillna(0.0)
    players = players.sort_values("minutes_observed").drop_duplicates(
        ["fixture_id", "team_id", "player_id"], keep="last"
    )
    minutes = players[["fixture_id", "team_id", "player_id", "minutes_observed"]]
    lineups = lineups.merge(minutes, on=["fixture_id", "team_id", "player_id"], how="left")

    group_status = []
    records = []
    complete_keys: set[tuple[int, int]] = set()
    for (fixture_id, team_id), group in lineups.groupby(["fixture_id", "team_id"], sort=False):
        formation_values = group["formation_norm"].dropna()
        formation = str(formation_values.mode().iloc[0]) if not formation_values.empty else ""
        template = FORMATION_TEMPLATES.get(formation)
        valid_grid = group.dropna(subset=["grid_row", "grid_col"]).copy()
        unique_players = int(group.player_id.nunique())
        row_counts = valid_grid.groupby("grid_row").player_id.nunique().sort_index().to_dict()
        goalkeeper_count = int(row_counts.get(1.0, row_counts.get(1, 0)))
        outfield_counts = [int(count) for row, count in row_counts.items() if int(row) != 1]
        expected_counts = [len(line) for line in template] if template else []
        complete = bool(
            template
            and unique_players == 11
            and len(valid_grid) == 11
            and goalkeeper_count == 1
            and outfield_counts == expected_counts
        )
        reason = "complete" if complete else (
            "unsupported_formation" if not template else
            "not_11_unique_starters" if unique_players != 11 else
            "missing_or_invalid_grid" if len(valid_grid) != 11 else
            "goalkeeper_row_invalid" if goalkeeper_count != 1 else
            "row_sizes_do_not_match_formation"
        )
        group_status.append({
            "fixture_id": int(fixture_id), "team_id": int(team_id), "formation": formation,
            "unique_starters": unique_players, "valid_grid_rows": int(len(valid_grid)),
            "observed_row_sizes": "-".join(map(str, outfield_counts)),
            "expected_row_sizes": "-".join(map(str, expected_counts)),
            "complete_lineup": complete, "failure_reason": reason,
        })
        if not complete:
            continue
        complete_keys.add((int(fixture_id), int(team_id)))
        ordered_rows = sorted(row for row in row_counts if int(row) != 1)
        row_roles = {row: template[index] for index, row in enumerate(ordered_rows)}
        for row, row_group in valid_grid.groupby("grid_row", sort=True):
            ordered = row_group.sort_values("grid_col")
            roles = ["GK"] if int(row) == 1 else row_roles[row]
            for role, item in zip(roles, ordered.itertuples(index=False)):
                if role == "CB":
                    continue
                records.append({
                    "fixture_id": int(fixture_id), "team_id": int(team_id),
                    "player_id": int(item.player_id), "player_name": item.player_name,
                    "formation": formation, "grid_row": int(item.grid_row),
                    "grid_col": int(item.grid_col), "role": role,
                    "minutes_observed": float(item.minutes_observed) if pd.notna(item.minutes_observed) else 0.0,
                })

    status_frame = pd.DataFrame(group_status)
    evidence = pd.DataFrame(records)
    status_frame.to_csv(OUT / "lineup_group_completeness.csv", index=False)
    evidence.to_csv(OUT / "complete_lineup_role_observations.csv", index=False)

    role_rows = []
    if not evidence.empty:
        aggregated = evidence.groupby(["player_id", "player_name", "role"], as_index=False).agg(
            role_minutes=("minutes_observed", "sum"),
            role_observations=("fixture_id", "nunique"),
        )
        totals = aggregated.groupby("player_id").role_minutes.transform("sum")
        aggregated["role_share"] = aggregated.role_minutes / totals.replace(0, pd.NA)
        aggregated.to_csv(OUT / "complete_lineup_player_role_minutes.csv", index=False)
        role_rows = aggregated.to_dict("records")
    else:
        pd.DataFrame(columns=["player_id", "player_name", "role", "role_minutes", "role_observations", "role_share"]).to_csv(
            OUT / "complete_lineup_player_role_minutes.csv", index=False
        )

    relevant, high_impact = candidate_ids()
    candidate_appearances = players.loc[players.player_id.isin(relevant) & players.minutes_observed.gt(0)].copy()
    complete_df = status_frame[["fixture_id", "team_id", "complete_lineup", "failure_reason", "formation"]]
    priority = candidate_appearances.merge(complete_df, on=["fixture_id", "team_id"], how="left")
    priority["complete_lineup"] = priority.complete_lineup.fillna(False)
    priority["failure_reason"] = priority.failure_reason.fillna("no_startxi_lineup_rows")
    priority["high_impact_current_release"] = priority.player_id.isin(high_impact)
    priority = priority.loc[~priority.complete_lineup].sort_values(
        ["high_impact_current_release", "minutes_observed"], ascending=[False, False]
    )
    priority.to_csv(OUT / "lineup_extraction_priority.csv", index=False)

    eligible_counts = {role: 0 for role in ROLES}
    for row in role_rows:
        if float(row["role_minutes"]) >= 900 and int(row["role_observations"]) >= 3:
            eligible_counts[str(row["role"])] += 1

    complete_groups = int(status_frame.complete_lineup.sum())
    all_groups = int(len(status_frame))
    high_impact_priority = priority.loc[priority.high_impact_current_release]
    status = {
        "status": "complete_lineup_position_evidence_audited",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "fixture_team_lineup_groups": all_groups,
        "structurally_complete_groups": complete_groups,
        "complete_group_rate": float(complete_groups / all_groups) if all_groups else 0.0,
        "complete_role_observations": int(len(evidence)),
        "players_with_complete_role_evidence": int(evidence.player_id.nunique()) if not evidence.empty else 0,
        "eligible_900_minutes_and_3_observations_by_role": eligible_counts,
        "all_roles_have_20_candidates": all(count >= 20 for count in eligible_counts.values()),
        "priority_candidate_fixture_team_pairs": int(len(priority)),
        "high_impact_priority_pairs": int(len(high_impact_priority)),
        "high_impact_players_needing_more_complete_lineups": int(high_impact_priority.player_id.nunique()),
        "classification_policy": "only exact 11-player grids whose row sizes match a supported declared formation",
        "next_action": "extract or recover complete startXI lineups for the priority fixture-team list",
    }
    (OUT / "lineup_completeness_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
