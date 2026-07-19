#!/usr/bin/env python3
"""Build exact-window, scope-correct player coverage from cached evidence.

Coverage is recomputed from the frozen official fixture inventory rather than
inherited from a prior ledger. The unchanged gate requires:

1. at least 80% of expected official-senior fixture endpoints processed; and
2. at least 80% lower-bound coverage of known exact-window minutes.

For an identified startXI appearance without a positive-minute statistics row,
missing exposure is bounded by the substitution/red-card exit minute when an
event is available. Otherwise the conservative match maximum is used (90, or
120 for AET/PEN). No season-wide aggregate denominator is used.
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
LAKE = Path("data/lake")
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
EVENT_PATTERNS = [
    "data/lake/batches/*_events.csv.gz",
    "data/lake/batches/*_events.csv",
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


def safe_read(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def load_players() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths(PLAYER_PATTERNS):
        frame = safe_read(path)
        if not {"player_id", "fixture_id"}.issubset(frame.columns):
            continue
        minutes_source = frame["minutes"] if "minutes" in frame else frame.get("minutes_num")
        part = pd.DataFrame({
            "player_id": pd.to_numeric(frame["player_id"], errors="coerce"),
            "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
            "minutes": pd.to_numeric(minutes_source, errors="coerce").fillna(0.0),
        }).dropna(subset=["player_id", "fixture_id"])
        part[["player_id", "fixture_id"]] = part[["player_id", "fixture_id"]].astype(int)
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["player_id", "fixture_id", "minutes"])
    union = pd.concat(frames, ignore_index=True)
    union["minutes"] = union.minutes.clip(lower=0, upper=130)
    return union.sort_values(["player_id", "fixture_id", "minutes"]).drop_duplicates(
        ["player_id", "fixture_id"], keep="last"
    )


def load_lineups() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths(LINEUP_PATTERNS):
        frame = safe_read(path)
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
        return pd.DataFrame(columns=["player_id", "fixture_id", "lineup_source", "is_starter"])
    union = pd.concat(frames, ignore_index=True)
    union["is_starter"] = union.lineup_source.str.strip().str.lower().eq("startxi")
    return union.sort_values("is_starter").drop_duplicates(["player_id", "fixture_id"], keep="last")


def load_exit_events() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in paths(EVENT_PATTERNS):
        frame = safe_read(path)
        if frame.empty or "fixture_id" not in frame:
            continue
        event_type = frame.get("event_type", pd.Series("", index=frame.index)).astype(str).str.lower()
        detail = frame.get("detail", pd.Series("", index=frame.index)).astype(str).str.lower()
        elapsed = pd.to_numeric(frame.get("elapsed"), errors="coerce")
        player_id = pd.to_numeric(frame.get("player_id"), errors="coerce")
        is_sub_out = event_type.eq("subst") & player_id.notna()
        is_red = event_type.eq("card") & detail.str.contains("red", na=False) & player_id.notna()
        part = pd.DataFrame({
            "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
            "player_id": player_id,
            "exit_minute": elapsed,
        }).loc[is_sub_out | is_red]
        part = part.dropna(subset=["fixture_id", "player_id", "exit_minute"])
        if not part.empty:
            part[["fixture_id", "player_id"]] = part[["fixture_id", "player_id"]].astype(int)
            part["exit_minute"] = part.exit_minute.clip(lower=0, upper=130)
            rows.append(part)
    if not rows:
        return pd.DataFrame(columns=["player_id", "fixture_id", "exit_minute"])
    return pd.concat(rows, ignore_index=True).groupby(
        ["player_id", "fixture_id"], as_index=False
    ).agg(exit_minute=("exit_minute", "min"))


def build_expected_map(fixtures: pd.DataFrame, associations: pd.DataFrame, player_ids: set[int]):
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
    OUT.mkdir(parents=True, exist_ok=True)
    canonical = pd.read_csv(MODEL / "player_window_coverage.csv", low_memory=False)
    fixtures = pd.read_csv(AUDIT / "exact_fixture_inventory.csv", low_memory=False)
    associations = pd.read_csv(AUDIT / "annual_player_competitions.csv", low_memory=False)
    frontier = pd.read_csv(MODEL / "selection_frontier_all_candidates.csv", low_memory=False)
    progress = pd.read_csv(LAKE / "adaptive_fixture_progress.csv", low_memory=False)

    fixture_numeric = ["fixture_id", "league_id", "season", "home_team_id", "away_team_id"]
    for column in fixture_numeric:
        fixtures[column] = pd.to_numeric(fixtures[column], errors="coerce")
    fixtures = fixtures.dropna(subset=fixture_numeric)
    fixtures[fixture_numeric] = fixtures[fixture_numeric].astype(int)
    for column in ["official_senior_main", "in_current_window", "in_pre_world_cup_window"]:
        fixtures[column] = bools(fixtures[column])
    fixtures = fixtures.loc[fixtures.official_senior_main].copy()
    fixtures["match_max_minutes"] = np.where(
        fixtures.get("status", pd.Series("", index=fixtures.index)).astype(str).str.upper().isin({"AET", "PEN"}),
        120.0,
        90.0,
    )
    flags = fixtures[[
        "fixture_id", "official_senior_main", "in_current_window",
        "in_pre_world_cup_window", "match_max_minutes",
    ]].drop_duplicates("fixture_id")

    assoc_cols = ["player_id", "league_id", "season", "team_id"]
    for column in assoc_cols:
        associations[column] = pd.to_numeric(associations[column], errors="coerce")
    associations = associations.dropna(subset=assoc_cols)
    associations[assoc_cols] = associations[assoc_cols].astype(int)

    canonical["player_id"] = pd.to_numeric(canonical.player_id, errors="coerce")
    canonical = canonical.dropna(subset=["player_id"])
    canonical["player_id"] = canonical.player_id.astype(int)
    canonical["original_coverage_pass_80pct"] = bools(canonical.coverage_pass_80pct)
    player_ids = set(canonical.player_id)
    expected = build_expected_map(fixtures, associations, player_ids)

    progress["fixture_id"] = pd.to_numeric(progress.fixture_id, errors="coerce")
    progress = progress.dropna(subset=["fixture_id"])
    progress["fixture_id"] = progress.fixture_id.astype(int)
    processed_ids = set(
        progress.loc[~progress.status.astype(str).eq("retryable_error"), "fixture_id"]
    )

    players = load_players().merge(flags, on="fixture_id", how="inner", validate="many_to_one")
    lineups = load_lineups().merge(flags, on="fixture_id", how="inner", validate="many_to_one")
    exits = load_exit_events()
    active_players = players.loc[players.minutes.gt(0)].copy()

    output_rows: list[dict] = []
    identity_columns = [column for column in canonical.columns if column not in {
        "window", "expected_official_fixtures", "processed_fixture_endpoints",
        "fixture_endpoint_coverage", "missing_fixture_endpoints",
        "detailed_appearance_fixtures", "detailed_minutes", "aggregate_reported_minutes",
        "minute_reconciliation_ratio_raw", "minute_reconciliation_ratio_clipped",
        "coverage_pass_80pct", "denominator_note", "original_coverage_pass_80pct",
        "exact_detailed_appearance_fixtures", "exact_detailed_minutes",
        "known_startXI_fixtures", "startXI_with_detailed_row",
        "known_missing_startXI_fixtures", "known_missing_minutes_upper_bound",
        "known_minute_coverage_lower_bound", "coverage_definition_version",
        "pass_changed_false_to_true", "pass_changed_true_to_false",
        "missing_minutes_inferred_from_events", "missing_startXI_with_exit_event",
    }]
    identity = canonical[identity_columns].drop_duplicates("player_id").set_index("player_id")
    prior_pass = canonical.set_index(["player_id", "window"])["original_coverage_pass_80pct"].to_dict()

    for player_id in sorted(player_ids):
        base = identity.loc[player_id].to_dict() if player_id in identity.index else {}
        for window, flag in [
            ("annual_current", "in_current_window"),
            ("pre_world_cup", "in_pre_world_cup_window"),
        ]:
            expected_ids = expected.get((player_id, window), set())
            processed = expected_ids & processed_ids
            missing_endpoint_ids = expected_ids - processed_ids

            p = active_players.loc[
                active_players.player_id.eq(player_id)
                & active_players[flag]
                & active_players.fixture_id.isin(expected_ids)
            ].copy()
            detailed_pairs = set(p.fixture_id.astype(int))
            detailed_minutes = float(p.minutes.sum())

            starter = lineups.loc[
                lineups.player_id.eq(player_id)
                & lineups.is_starter
                & lineups[flag]
                & lineups.fixture_id.isin(expected_ids),
                ["player_id", "fixture_id", "match_max_minutes"],
            ].drop_duplicates(["player_id", "fixture_id"])
            starter["has_detailed_row"] = starter.fixture_id.isin(detailed_pairs)
            missing_starter = starter.loc[~starter.has_detailed_row].merge(
                exits, on=["player_id", "fixture_id"], how="left"
            )
            missing_starter["missing_minutes_bound"] = pd.to_numeric(
                missing_starter.exit_minute, errors="coerce"
            ).fillna(missing_starter.match_max_minutes)
            missing_starter["missing_minutes_bound"] = missing_starter[[
                "missing_minutes_bound", "match_max_minutes"
            ]].min(axis=1).clip(lower=0)
            missing_minutes = float(missing_starter.missing_minutes_bound.sum())
            denominator = detailed_minutes + missing_minutes
            minute_coverage = detailed_minutes / denominator if denominator > 0 else 1.0
            fixture_coverage = len(processed) / len(expected_ids) if expected_ids else None
            passed = bool(
                fixture_coverage is not None
                and fixture_coverage >= 0.80
                and minute_coverage >= 0.80
            )
            original = bool(prior_pass.get((player_id, window), False))
            output_rows.append({
                **base,
                "player_id": player_id,
                "window": window,
                "expected_official_fixtures": len(expected_ids),
                "processed_fixture_endpoints": len(processed),
                "fixture_endpoint_coverage": fixture_coverage,
                "missing_fixture_endpoints": len(missing_endpoint_ids),
                "detailed_appearance_fixtures": len(detailed_pairs),
                "detailed_minutes": detailed_minutes,
                "aggregate_reported_minutes": None,
                "minute_reconciliation_ratio_raw": minute_coverage,
                "minute_reconciliation_ratio_clipped": minute_coverage,
                "coverage_pass_80pct": passed,
                "denominator_note": "exact-window detailed minutes plus event-bounded exposure for known startXI appearances without a positive-minute statistics row",
                "original_coverage_pass_80pct": original,
                "exact_detailed_appearance_fixtures": len(detailed_pairs),
                "exact_detailed_minutes": detailed_minutes,
                "known_startXI_fixtures": int(len(starter)),
                "startXI_with_detailed_row": int(starter.has_detailed_row.sum()) if not starter.empty else 0,
                "known_missing_startXI_fixtures": int(len(missing_starter)),
                "known_missing_minutes_upper_bound": missing_minutes,
                "missing_startXI_with_exit_event": int(missing_starter.exit_minute.notna().sum()) if not missing_starter.empty else 0,
                "missing_minutes_inferred_from_events": float(
                    missing_starter.loc[missing_starter.exit_minute.notna(), "missing_minutes_bound"].sum()
                ) if not missing_starter.empty else 0.0,
                "known_minute_coverage_lower_bound": minute_coverage,
                "coverage_definition_version": "exact_window_known_minutes_v2_event_bounded",
                "pass_changed_false_to_true": (not original) and passed,
                "pass_changed_true_to_false": original and (not passed),
            })

    result = pd.DataFrame(output_rows)
    result.to_csv(OUT / "player_window_coverage_scope_correct.csv", index=False)

    current_minutes = result.loc[
        result.window.eq("annual_current"), ["player_id", "exact_detailed_minutes"]
    ]
    frontier["player_id"] = pd.to_numeric(frontier.player_id, errors="coerce")
    frontier = frontier.dropna(subset=["player_id"])
    frontier["player_id"] = frontier.player_id.astype(int)
    eligibility = frontier.merge(current_minutes, on="player_id", how="left")
    eligibility["exact_detailed_minutes"] = pd.to_numeric(
        eligibility.exact_detailed_minutes, errors="coerce"
    ).fillna(0)
    eligibility["old_aggregate_minute_eligible"] = pd.to_numeric(
        eligibility.get("reported_minutes"), errors="coerce"
    ).fillna(0).ge(900)
    eligibility["exact_window_minute_eligible"] = eligibility.exact_detailed_minutes.ge(900)
    eligibility["eligibility_changed_to_ineligible"] = (
        eligibility.old_aggregate_minute_eligible & ~eligibility.exact_window_minute_eligible
    )
    eligibility.to_csv(OUT / "exact_window_minute_eligibility_audit.csv", index=False)

    status = {
        "status": "scope_correct_coverage_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "threshold_changed": False,
        "scope_correction": "season aggregates removed; exact fixture coverage recomputed from durable progress",
        "coverage_definition": "fixture endpoint >=80% and event-bounded lower coverage of exact-window known minutes >=80%",
        "cached_player_fixture_pairs": int(len(active_players)),
        "cached_lineup_player_fixture_pairs": int(len(lineups)),
        "cached_exit_event_pairs": int(len(exits)),
        "window_rows_passing_before": int(result.original_coverage_pass_80pct.sum()),
        "window_rows_passing_after": int(result.coverage_pass_80pct.sum()),
        "false_to_true_window_rows": int(result.pass_changed_false_to_true.sum()),
        "true_to_false_window_rows": int(result.pass_changed_true_to_false.sum()),
        "annual_players_passing": int(result.loc[result.window.eq("annual_current"), "coverage_pass_80pct"].sum()),
        "pre_world_cup_players_passing": int(result.loc[result.window.eq("pre_world_cup"), "coverage_pass_80pct"].sum()),
        "players_with_known_missing_startXI": int(result.loc[result.known_missing_startXI_fixtures.gt(0), "player_id"].nunique()),
        "missing_startXI_pairs_with_exit_event": int(result.missing_startXI_with_exit_event.sum()),
        "aggregate_eligible_but_below_900_exact_minutes": int(eligibility.eligibility_changed_to_ineligible.sum()),
        "next_action": "run shadow selection, promote ledger, and query only residual evidence",
    }
    (OUT / "scope_correct_coverage_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
