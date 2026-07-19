#!/usr/bin/env python3
"""Promote the audited exact-window coverage ledger and build residual queue.

This script makes no network calls. It preserves the former canonical ledger,
promotes the reviewed v2 ledger, and creates a targeted queue for only the
remaining selection challengers.
"""
from __future__ import annotations

import glob
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AUDIT = Path("data/audits")
MODEL = Path("data/model_readiness")
SCOPE = AUDIT / "scope_correct_coverage"
SHADOW = SCOPE / "shadow_selection"


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def read_many(patterns: list[str]) -> pd.DataFrame:
    frames = []
    seen = set()
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            frame = pd.read_csv(path, low_memory=False)
            frame["_source_path"] = path
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_expected_map(fixtures: pd.DataFrame, associations: pd.DataFrame, player_ids: set[int]):
    fixtures = fixtures.loc[fixtures.official_senior_main].copy()
    associations = associations.loc[associations.player_id.isin(player_ids)].copy()
    expected: dict[tuple[int, str], set[int]] = {}
    for row in associations[["player_id", "league_id", "season", "team_id"]].drop_duplicates().itertuples(index=False):
        block = fixtures.loc[
            fixtures.league_id.eq(row.league_id)
            & fixtures.season.eq(row.season)
            & (fixtures.home_team_id.eq(row.team_id) | fixtures.away_team_id.eq(row.team_id))
        ]
        expected.setdefault((int(row.player_id), "annual_current"), set()).update(
            block.loc[block.in_current_window, "fixture_id"].astype(int)
        )
        expected.setdefault((int(row.player_id), "pre_world_cup"), set()).update(
            block.loc[block.in_pre_world_cup_window, "fixture_id"].astype(int)
        )
    return expected


def main() -> None:
    source_ledger = SCOPE / "player_window_coverage_scope_correct.csv"
    shadow_unresolved = SHADOW / "shadow_selection_unresolved_players.csv"
    shadow_status = SHADOW / "shadow_selection_status.json"
    if not source_ledger.exists() or not shadow_unresolved.exists() or not shadow_status.exists():
        raise SystemExit("Scope-correct audit or shadow gate outputs are missing")

    canonical = MODEL / "player_window_coverage.csv"
    backup = MODEL / "player_window_coverage_v1_season_denominator.csv"
    if canonical.exists() and not backup.exists():
        shutil.copyfile(canonical, backup)
    shutil.copyfile(source_ledger, canonical)

    unresolved = pd.read_csv(shadow_unresolved, low_memory=False)
    unresolved["player_id"] = pd.to_numeric(unresolved.player_id, errors="coerce")
    unresolved = unresolved.dropna(subset=["player_id"])
    unresolved["player_id"] = unresolved.player_id.astype(int)
    player_ids = set(unresolved.player_id)
    reason_map = unresolved.set_index("player_id")["reason"].to_dict()
    role_map = unresolved.set_index("player_id")["resolved_role"].to_dict()

    fixtures = pd.read_csv(AUDIT / "exact_fixture_inventory.csv", low_memory=False)
    associations = pd.read_csv(AUDIT / "annual_player_competitions.csv", low_memory=False)
    progress = pd.read_csv("data/lake/adaptive_fixture_progress.csv", low_memory=False)

    numeric_cols = ["fixture_id", "league_id", "season", "home_team_id", "away_team_id"]
    for col in numeric_cols:
        fixtures[col] = pd.to_numeric(fixtures[col], errors="coerce")
    fixtures = fixtures.dropna(subset=numeric_cols)
    fixtures[numeric_cols] = fixtures[numeric_cols].astype(int)
    for col in ["official_senior_main", "in_current_window", "in_pre_world_cup_window"]:
        fixtures[col] = as_bool(fixtures[col])

    for col in ["player_id", "league_id", "season", "team_id"]:
        associations[col] = pd.to_numeric(associations[col], errors="coerce")
    associations = associations.dropna(subset=["player_id", "league_id", "season", "team_id"])
    associations[["player_id", "league_id", "season", "team_id"]] = associations[[
        "player_id", "league_id", "season", "team_id"
    ]].astype(int)

    progress["fixture_id"] = pd.to_numeric(progress.fixture_id, errors="coerce")
    progress = progress.dropna(subset=["fixture_id"])
    progress["fixture_id"] = progress.fixture_id.astype(int)
    processed_ids = set(progress.loc[~progress.status.astype(str).eq("retryable_error"), "fixture_id"])
    expected = build_expected_map(fixtures, associations, player_ids)

    players = read_many([
        "data/lake/batches/*_players.csv.gz",
        "data/lake/batches/*_players.csv",
        "data/audits/fixture_detail_pilot_players.csv",
    ])
    lineups = read_many([
        "data/lake/batches/*_lineups.csv.gz",
        "data/lake/batches/*_lineups.csv",
        "data/audits/fixture_detail_pilot_lineups.csv",
    ])
    if not players.empty:
        players["player_id"] = pd.to_numeric(players.player_id, errors="coerce")
        players["fixture_id"] = pd.to_numeric(players.fixture_id, errors="coerce")
        players["minutes_num"] = pd.to_numeric(players.get("minutes", players.get("minutes_num")), errors="coerce").fillna(0)
        players = players.dropna(subset=["player_id", "fixture_id"])
        players[["player_id", "fixture_id"]] = players[["player_id", "fixture_id"]].astype(int)
        detailed_pairs = set(zip(players.loc[players.minutes_num.gt(0), "player_id"], players.loc[players.minutes_num.gt(0), "fixture_id"]))
    else:
        detailed_pairs = set()

    queue_rows: list[dict] = []
    for pid in sorted(player_ids):
        for window in ["annual_current", "pre_world_cup"]:
            for fixture_id in sorted(expected.get((pid, window), set()) - processed_ids):
                queue_rows.append({
                    "player_id": pid,
                    "fixture_id": fixture_id,
                    "window": window,
                    "priority_reason": "missing_fixture_endpoint",
                    "selection_resolution_reason": reason_map.get(pid),
                    "resolved_role": role_map.get(pid),
                })

    if not lineups.empty:
        lineups["player_id"] = pd.to_numeric(lineups.player_id, errors="coerce")
        lineups["fixture_id"] = pd.to_numeric(lineups.fixture_id, errors="coerce")
        lineups = lineups.dropna(subset=["player_id", "fixture_id"])
        lineups[["player_id", "fixture_id"]] = lineups[["player_id", "fixture_id"]].astype(int)
        starters = lineups.loc[
            lineups.player_id.isin(player_ids)
            & lineups.lineup_source.astype(str).str.strip().str.lower().eq("startxi"),
            ["player_id", "fixture_id"],
        ].drop_duplicates()
        flag_map = fixtures.set_index("fixture_id")[["in_current_window", "in_pre_world_cup_window"]].to_dict("index")
        for row in starters.itertuples(index=False):
            pair = (int(row.player_id), int(row.fixture_id))
            if pair in detailed_pairs:
                continue
            flags = flag_map.get(int(row.fixture_id), {})
            for window, flag in [
                ("annual_current", "in_current_window"),
                ("pre_world_cup", "in_pre_world_cup_window"),
            ]:
                if flags.get(flag) and int(row.fixture_id) in expected.get((int(row.player_id), window), set()):
                    queue_rows.append({
                        "player_id": int(row.player_id),
                        "fixture_id": int(row.fixture_id),
                        "window": window,
                        "priority_reason": "known_startXI_without_detailed_row",
                        "selection_resolution_reason": reason_map.get(int(row.player_id)),
                        "resolved_role": role_map.get(int(row.player_id)),
                    })

    queue = pd.DataFrame(queue_rows).drop_duplicates(["player_id", "fixture_id", "window", "priority_reason"])
    if not queue.empty:
        reason_weight = {
            "covered_pool_shortage": 6.0,
            "upper90_can_enter_real_xi": 5.0,
            "high_ability_role_stabilization": 4.5,
            "upper90_can_enter_top30": 3.5,
            "top35_guardrail": 2.5,
        }
        queue["reason_weight"] = queue.selection_resolution_reason.map(reason_weight).fillna(1.0)
        queue["data_weight"] = queue.priority_reason.map({
            "missing_fixture_endpoint": 2.0,
            "known_startXI_without_detailed_row": 1.5,
        }).fillna(1.0)
        queue["priority_score"] = queue.reason_weight + queue.data_weight
        queue = queue.sort_values(["priority_score", "fixture_id"], ascending=[False, True])
    queue.to_csv(MODEL / "coverage_priority_fixtures.csv", index=False)
    queue.to_csv(SCOPE / "scope_correct_residual_priority_fixtures.csv", index=False)

    fixture_summary = pd.DataFrame()
    if not queue.empty:
        fixture_summary = queue.groupby("fixture_id", as_index=False).agg(
            unresolved_players=("player_id", "nunique"),
            player_fixture_pairs=("player_id", "size"),
            max_priority=("priority_score", "max"),
            total_priority=("priority_score", "sum"),
        )
        fixture_summary["information_value_score"] = (
            fixture_summary.max_priority + 0.5 * fixture_summary.total_priority
        )
        fixture_summary = fixture_summary.sort_values(
            ["information_value_score", "unresolved_players"], ascending=[False, False]
        )
        fixture_summary.to_csv(SCOPE / "scope_correct_residual_fixture_queue.csv", index=False)

    status = {
        "status": "scope_correct_coverage_promoted",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "canonical_ledger": str(canonical),
        "former_ledger_backup": str(backup),
        "unresolved_players_before_canonical_rerun": int(len(player_ids)),
        "residual_player_fixture_pairs": int(len(queue)),
        "residual_unique_fixtures": int(queue.fixture_id.nunique()) if not queue.empty else 0,
        "missing_endpoint_pairs": int(queue.priority_reason.eq("missing_fixture_endpoint").sum()) if not queue.empty else 0,
        "missing_startXI_detail_pairs": int(queue.priority_reason.eq("known_startXI_without_detailed_row").sum()) if not queue.empty else 0,
        "next_action": "run canonical selection, scientific status and release builders",
    }
    (SCOPE / "scope_correct_promotion_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
