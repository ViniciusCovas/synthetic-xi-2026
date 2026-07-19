#!/usr/bin/env python3
"""Build a scope-correct exact-window coverage ledger from cached data.

The frozen protocol requires >=80% coverage of known minutes inside each exact
window. Season aggregate minutes cannot serve as the denominator because they
span dates and competitions outside the frozen window. This audit therefore uses:

  detailed observed minutes /
  (detailed observed minutes + 90 * known missing startXI appearances)

The 90-minute value is a conservative upper bound for every identified starter
without a detailed player row. Fixture-endpoint coverage must also be >=80%.
No network calls are made and no threshold is relaxed.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

AUDIT = Path("data/audits")
MODEL = Path("data/model_readiness")
OUT = AUDIT / "scope_correct_coverage"

PLAYER_PATTERNS = [
    "data/lake/batches/*_players.csv.gz",
    "data/lake/batches/*_players.csv",
    "data/audits/fixture_detail_pilot_players.csv",
]
LINEUP_PATTERNS = [
    "data/lake/batches/*_lineups.csv.gz",
    "data/lake/batches/*_lineups.csv",
    "data/audits/fixture_detail_pilot_lineups.csv",
]


def bools(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def paths(patterns: list[str]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        values.extend(glob.glob(pattern))
    return sorted(set(values))


def load_players() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths(PLAYER_PATTERNS):
        frame = pd.read_csv(path, low_memory=False)
        if not {"player_id", "fixture_id"}.issubset(frame.columns):
            continue
        part = pd.DataFrame({
            "player_id": pd.to_numeric(frame["player_id"], errors="coerce"),
            "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
            "minutes": pd.to_numeric(frame.get("minutes", frame.get("minutes_num")), errors="coerce").fillna(0.0),
        }).dropna(subset=["player_id", "fixture_id"])
        part[["player_id", "fixture_id"]] = part[["player_id", "fixture_id"]].astype(int)
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["player_id", "fixture_id", "minutes"])
    union = pd.concat(frames, ignore_index=True)
    union["minutes"] = union["minutes"].clip(lower=0, upper=130)
    return union.sort_values(["player_id", "fixture_id", "minutes"]).drop_duplicates(
        ["player_id", "fixture_id"], keep="last"
    )


def load_lineups() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths(LINEUP_PATTERNS):
        frame = pd.read_csv(path, low_memory=False)
        if not {"player_id", "fixture_id", "lineup_source"}.issubset(frame.columns):
            continue
        part = pd.DataFrame({
            "player_id": pd.to_numeric(frame["player_id"], errors="coerce"),
            "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
            "lineup_source": frame["lineup_source"].astype(str),
        }).dropna(subset=["player_id", "fixture_id"])
        part[["player_id", "fixture_id"]] = part[["player_id", "fixture_id"]].astype(int)
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["player_id", "fixture_id", "lineup_source"])
    union = pd.concat(frames, ignore_index=True)
    union["is_starter"] = union["lineup_source"].str.strip().str.lower().eq("startxi")
    return union.sort_values("is_starter").drop_duplicates(["player_id", "fixture_id"], keep="last")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    canonical = pd.read_csv(MODEL / "player_window_coverage.csv", low_memory=False)
    fixture_inventory = pd.read_csv(AUDIT / "exact_fixture_inventory.csv", low_memory=False)
    precheck = pd.read_csv(AUDIT / "annual_player_precheck.csv", low_memory=False)
    frontier = pd.read_csv(MODEL / "selection_frontier_all_candidates.csv", low_memory=False)

    fixture_inventory["fixture_id"] = pd.to_numeric(fixture_inventory["fixture_id"], errors="coerce")
    fixture_inventory = fixture_inventory.dropna(subset=["fixture_id"])
    fixture_inventory["fixture_id"] = fixture_inventory["fixture_id"].astype(int)
    for column in ["official_senior_main", "in_current_window", "in_pre_world_cup_window"]:
        fixture_inventory[column] = bools(fixture_inventory[column])
    flags = fixture_inventory[[
        "fixture_id", "official_senior_main", "in_current_window", "in_pre_world_cup_window"
    ]].drop_duplicates("fixture_id")

    players = load_players().merge(flags, on="fixture_id", how="inner", validate="many_to_one")
    lineups = load_lineups().merge(flags, on="fixture_id", how="inner", validate="many_to_one")
    players = players.loc[players.official_senior_main].copy()
    lineups = lineups.loc[lineups.official_senior_main].copy()

    canonical["player_id"] = pd.to_numeric(canonical["player_id"], errors="coerce")
    canonical = canonical.dropna(subset=["player_id"])
    canonical["player_id"] = canonical["player_id"].astype(int)
    canonical["original_coverage_pass_80pct"] = bools(canonical["coverage_pass_80pct"])

    output_parts: list[pd.DataFrame] = []
    for flag, window in [
        ("in_current_window", "annual_current"),
        ("in_pre_world_cup_window", "pre_world_cup"),
    ]:
        p = players.loc[players[flag]].copy()
        l = lineups.loc[lineups[flag]].copy()
        detailed = p.groupby("player_id", as_index=False).agg(
            exact_detailed_appearance_fixtures=("fixture_id", "nunique"),
            exact_detailed_minutes=("minutes", "sum"),
        )
        starters = l.loc[l.is_starter, ["player_id", "fixture_id"]].drop_duplicates()
        detailed_pairs = set(zip(p.player_id.astype(int), p.fixture_id.astype(int)))
        starters["has_detailed_row"] = [
            (int(pid), int(fid)) in detailed_pairs
            for pid, fid in zip(starters.player_id, starters.fixture_id)
        ]
        starter_summary = starters.groupby("player_id", as_index=False).agg(
            known_startXI_fixtures=("fixture_id", "nunique"),
            startXI_with_detailed_row=("has_detailed_row", "sum"),
        )
        starter_summary["known_missing_startXI_fixtures"] = (
            starter_summary["known_startXI_fixtures"] - starter_summary["startXI_with_detailed_row"]
        )
        block = canonical.loc[canonical.window.eq(window)].copy()
        block = block.merge(detailed, on="player_id", how="left").merge(starter_summary, on="player_id", how="left")
        for column in [
            "exact_detailed_appearance_fixtures", "exact_detailed_minutes",
            "known_startXI_fixtures", "startXI_with_detailed_row", "known_missing_startXI_fixtures",
        ]:
            block[column] = pd.to_numeric(block[column], errors="coerce").fillna(0)
        block["known_missing_minutes_upper_bound"] = 90.0 * block["known_missing_startXI_fixtures"]
        denominator = block["exact_detailed_minutes"] + block["known_missing_minutes_upper_bound"]
        block["known_minute_coverage_lower_bound"] = np.where(
            denominator.gt(0), block["exact_detailed_minutes"] / denominator, 1.0
        )
        endpoint = pd.to_numeric(block["fixture_endpoint_coverage"], errors="coerce")
        block["coverage_pass_80pct"] = endpoint.ge(0.80) & block["known_minute_coverage_lower_bound"].ge(0.80)
        block["detailed_minutes"] = block["exact_detailed_minutes"]
        block["detailed_appearance_fixtures"] = block["exact_detailed_appearance_fixtures"].astype(int)
        block["minute_reconciliation_ratio_raw"] = block["known_minute_coverage_lower_bound"]
        block["minute_reconciliation_ratio_clipped"] = block["known_minute_coverage_lower_bound"]
        block["aggregate_reported_minutes"] = np.nan
        block["coverage_definition_version"] = "exact_window_known_minutes_v2"
        block["denominator_note"] = (
            "exact-window detailed minutes plus conservative 90-minute upper bound for each known startXI without a detailed row"
        )
        block["pass_changed_false_to_true"] = (~block.original_coverage_pass_80pct) & block.coverage_pass_80pct
        block["pass_changed_true_to_false"] = block.original_coverage_pass_80pct & (~block.coverage_pass_80pct)
        output_parts.append(block)

    result = pd.concat(output_parts, ignore_index=True)
    result.to_csv(OUT / "player_window_coverage_scope_correct.csv", index=False)

    # Audit exact-window minutes used by the selection frontier.
    current_minutes = result.loc[result.window.eq("annual_current"), ["player_id", "exact_detailed_minutes"]]
    frontier["player_id"] = pd.to_numeric(frontier["player_id"], errors="coerce")
    frontier = frontier.dropna(subset=["player_id"])
    frontier["player_id"] = frontier["player_id"].astype(int)
    eligibility = frontier.merge(current_minutes, on="player_id", how="left")
    eligibility["exact_detailed_minutes"] = pd.to_numeric(eligibility["exact_detailed_minutes"], errors="coerce").fillna(0)
    eligibility["old_aggregate_minute_eligible"] = pd.to_numeric(eligibility.get("reported_minutes"), errors="coerce").fillna(0).ge(900)
    eligibility["exact_window_minute_eligible"] = eligibility["exact_detailed_minutes"].ge(900)
    eligibility["eligibility_changed_to_ineligible"] = eligibility.old_aggregate_minute_eligible & (~eligibility.exact_window_minute_eligible)
    eligibility.to_csv(OUT / "exact_window_minute_eligibility_audit.csv", index=False)

    pass_before = int(result.original_coverage_pass_80pct.sum())
    pass_after = int(result.coverage_pass_80pct.sum())
    mapping_ok = bool(len(players) > 0 and len(lineups) > 0)
    status = {
        "status": "scope_correct_coverage_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "threshold_changed": False,
        "scope_correction": "removed season aggregates from exact-window denominator",
        "coverage_definition": "fixture endpoint >=80% and conservative lower-bound coverage of exact-window known minutes >=80%",
        "cached_player_fixture_pairs": int(len(players)),
        "cached_lineup_player_fixture_pairs": int(len(lineups)),
        "window_rows_passing_before": pass_before,
        "window_rows_passing_after": pass_after,
        "false_to_true_window_rows": int(result.pass_changed_false_to_true.sum()),
        "true_to_false_window_rows": int(result.pass_changed_true_to_false.sum()),
        "annual_players_passing": int(result.loc[result.window.eq("annual_current"), "coverage_pass_80pct"].sum()),
        "pre_world_cup_players_passing": int(result.loc[result.window.eq("pre_world_cup"), "coverage_pass_80pct"].sum()),
        "players_with_known_missing_startXI": int(result.loc[result.known_missing_startXI_fixtures.gt(0), "player_id"].nunique()),
        "aggregate_eligible_but_below_900_exact_minutes": int(eligibility.eligibility_changed_to_ineligible.sum()),
        "promotion_candidate": mapping_ok and pass_after >= pass_before and int(result.pass_changed_true_to_false.sum()) == 0,
        "next_action": "promote v2 ledger and enforce exact-window 900-minute eligibility" if mapping_ok else "review missing cache sources",
    }
    (OUT / "scope_correct_coverage_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
