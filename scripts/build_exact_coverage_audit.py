#!/usr/bin/env python3
"""Build an auditable per-player, per-window coverage ledger.

Coverage is defined at fixture level: every official senior fixture involving a
reported player/team/competition association is reconstructed and checked
against the durable extraction progress. Non-appearances therefore count as
observed when the fixture endpoint itself was processed.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

AUDIT_DIR = Path("data/audits")
LAKE_DIR = Path("data/lake")
BATCH_DIR = LAKE_DIR / "batches"
OUT_DIR = Path("data/model_readiness")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def read_many(pattern: str) -> pd.DataFrame:
    frames = [pd.read_csv(path) for path in sorted(glob.glob(pattern))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def safe_ratio(num: float, den: float) -> float | None:
    if den is None or not np.isfinite(den) or den <= 0:
        return None
    return float(num / den)


def build_expected_fixture_map(
    fixtures: pd.DataFrame,
    competitions: pd.DataFrame,
    eligible_ids: set[int],
) -> dict[tuple[int, str], set[int]]:
    required = {
        "fixture_id", "league_id", "season", "home_team_id", "away_team_id",
        "official_senior_main", "in_current_window", "in_pre_world_cup_window",
    }
    missing = required - set(fixtures.columns)
    if missing:
        raise RuntimeError(f"exact_fixture_inventory.csv missing columns: {sorted(missing)}")
    assoc_required = {"player_id", "league_id", "season", "team_id"}
    assoc_missing = assoc_required - set(competitions.columns)
    if assoc_missing:
        raise RuntimeError(
            f"annual_player_competitions.csv missing columns: {sorted(assoc_missing)}"
        )

    fixtures = fixtures.loc[fixtures["official_senior_main"].map(as_bool)].copy()
    number_cols = ["fixture_id", "league_id", "season", "home_team_id", "away_team_id"]
    for column in number_cols:
        fixtures[column] = pd.to_numeric(fixtures[column], errors="coerce")
    fixtures = fixtures.dropna(subset=number_cols)
    fixtures[number_cols] = fixtures[number_cols].astype(int)

    competitions = competitions.loc[
        competitions["player_id"].astype(int).isin(eligible_ids)
    ].copy()
    assoc_cols = ["player_id", "league_id", "season", "team_id"]
    for column in assoc_cols:
        competitions[column] = pd.to_numeric(competitions[column], errors="coerce")
    competitions = competitions.dropna(subset=assoc_cols)
    competitions[assoc_cols] = competitions[assoc_cols].astype(int)

    expected: dict[tuple[int, str], set[int]] = {}
    for row in competitions[assoc_cols].drop_duplicates().itertuples(index=False):
        mask = (
            fixtures["league_id"].eq(row.league_id)
            & fixtures["season"].eq(row.season)
            & (
                fixtures["home_team_id"].eq(row.team_id)
                | fixtures["away_team_id"].eq(row.team_id)
            )
        )
        block = fixtures.loc[mask]
        for flag, label in [
            ("in_current_window", "annual_current"),
            ("in_pre_world_cup_window", "pre_world_cup"),
        ]:
            ids = set(block.loc[block[flag].map(as_bool), "fixture_id"].astype(int))
            expected.setdefault((int(row.player_id), label), set()).update(ids)
    return expected


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    precheck = pd.read_csv(AUDIT_DIR / "annual_player_precheck.csv")
    fixtures = pd.read_csv(AUDIT_DIR / "exact_fixture_inventory.csv")
    competitions = pd.read_csv(AUDIT_DIR / "annual_player_competitions.csv")
    progress_path = LAKE_DIR / "adaptive_fixture_progress.csv"
    progress = pd.read_csv(progress_path) if progress_path.exists() else pd.DataFrame()
    players = read_many(str(BATCH_DIR / "batch_*_players.csv.gz"))

    eligible = precheck.loc[precheck["rank_entry_precheck"].map(as_bool)].copy()
    eligible["player_id"] = pd.to_numeric(eligible["player_id"], errors="coerce")
    eligible = eligible.dropna(subset=["player_id"])
    eligible["player_id"] = eligible["player_id"].astype(int)
    eligible_ids = set(eligible["player_id"])
    expected_map = build_expected_fixture_map(fixtures, competitions, eligible_ids)

    processed_ids: set[int] = set()
    if not progress.empty:
        progress["fixture_id"] = pd.to_numeric(progress["fixture_id"], errors="coerce")
        progress = progress.dropna(subset=["fixture_id"])
        progress["fixture_id"] = progress["fixture_id"].astype(int)
        processed_ids = set(
            progress.loc[
                ~progress["status"].astype(str).eq("retryable_error"), "fixture_id"
            ]
        )

    details: dict[tuple[int, str], dict[str, float]] = {}
    if not players.empty:
        players["player_id"] = pd.to_numeric(players["player_id"], errors="coerce")
        players["fixture_id"] = pd.to_numeric(players["fixture_id"], errors="coerce")
        players["minutes_num"] = pd.to_numeric(players.get("minutes"), errors="coerce").fillna(0.0)
        players = players.dropna(subset=["player_id", "fixture_id"])
        players[["player_id", "fixture_id"]] = players[["player_id", "fixture_id"]].astype(int)
        players = players.drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
        for flag, label in [
            ("in_current_window", "annual_current"),
            ("in_pre_world_cup_window", "pre_world_cup"),
        ]:
            subset = players.loc[players[flag].map(as_bool)]
            grouped = subset.groupby("player_id").agg(
                detailed_appearance_fixtures=("fixture_id", "nunique"),
                detailed_minutes=("minutes_num", "sum"),
            )
            for player_id, row in grouped.iterrows():
                details[(int(player_id), label)] = row.to_dict()

    rows = []
    priority = []
    identity_cols = [
        "player_id", "player_name", "world_cup_team", "squad_position",
        "reported_minutes", "benchmark_precheck",
    ]
    identity_cols = [c for c in identity_cols if c in eligible.columns]
    for player in eligible[identity_cols].drop_duplicates("player_id").itertuples(index=False):
        identity = player._asdict()
        player_id = int(identity["player_id"])
        for label in ["annual_current", "pre_world_cup"]:
            expected_ids = expected_map.get((player_id, label), set())
            processed = expected_ids & processed_ids
            missing_ids = sorted(expected_ids - processed_ids)
            detail = details.get((player_id, label), {})
            fixture_coverage = safe_ratio(len(processed), len(expected_ids))
            reported = pd.to_numeric(
                pd.Series([identity.get("reported_minutes")]), errors="coerce"
            ).iloc[0]
            detailed_minutes = float(detail.get("detailed_minutes", 0.0))
            minute_raw = (
                safe_ratio(detailed_minutes, float(reported))
                if label == "annual_current" and pd.notna(reported)
                else None
            )
            minute_clipped = (
                min(1.0, max(0.0, minute_raw)) if minute_raw is not None else None
            )
            passed = bool(
                fixture_coverage is not None
                and fixture_coverage >= 0.80
                and (
                    label != "annual_current"
                    or minute_clipped is None
                    or minute_clipped >= 0.80
                )
            )
            rows.append(
                {
                    **identity,
                    "window": label,
                    "expected_official_fixtures": len(expected_ids),
                    "processed_fixture_endpoints": len(processed),
                    "fixture_endpoint_coverage": fixture_coverage,
                    "missing_fixture_endpoints": len(missing_ids),
                    "detailed_appearance_fixtures": int(
                        detail.get("detailed_appearance_fixtures", 0)
                    ),
                    "detailed_minutes": detailed_minutes,
                    "aggregate_reported_minutes": (
                        float(reported)
                        if label == "annual_current" and pd.notna(reported)
                        else None
                    ),
                    "minute_reconciliation_ratio_raw": minute_raw,
                    "minute_reconciliation_ratio_clipped": minute_clipped,
                    "coverage_pass_80pct": passed,
                    "denominator_note": (
                        "provider aggregate minutes plus exact fixture inventory"
                        if label == "annual_current"
                        else "exact fixture inventory; no independent aggregate-minute denominator"
                    ),
                }
            )
            if not passed:
                for fixture_id in missing_ids:
                    priority.append(
                        {
                            "player_id": player_id,
                            "player_name": identity.get("player_name"),
                            "world_cup_team": identity.get("world_cup_team"),
                            "window": label,
                            "fixture_id": fixture_id,
                            "benchmark_precheck": identity.get("benchmark_precheck"),
                            "priority_reason": "player_below_80pct_coverage",
                        }
                    )

    ledger = pd.DataFrame(rows)
    ledger.to_csv(OUT_DIR / "player_window_coverage.csv", index=False)
    pd.DataFrame(priority).drop_duplicates(
        ["player_id", "window", "fixture_id"]
    ).to_csv(OUT_DIR / "coverage_priority_fixtures.csv", index=False)

    summaries = []
    for label, subset in ledger.groupby("window"):
        values = pd.to_numeric(subset["fixture_endpoint_coverage"], errors="coerce").dropna()
        summaries.append(
            {
                "window": label,
                "eligible_players": int(len(subset)),
                "players_with_expected_fixtures": int(
                    subset["expected_official_fixtures"].gt(0).sum()
                ),
                "players_passing_80pct": int(subset["coverage_pass_80pct"].sum()),
                "pass_rate": float(subset["coverage_pass_80pct"].mean()),
                "median_fixture_coverage": float(values.median()) if not values.empty else None,
                "p10_fixture_coverage": float(values.quantile(0.10)) if not values.empty else None,
            }
        )
    pd.DataFrame(summaries).to_csv(
        OUT_DIR / "coverage_summary_by_window.csv", index=False
    )
    current = ledger.loc[ledger["window"].eq("annual_current"), "coverage_pass_80pct"]
    pre = ledger.loc[ledger["window"].eq("pre_world_cup"), "coverage_pass_80pct"]
    status = {
        "status": "exact_fixture_coverage_audited",
        "definition": "processed eligible fixture endpoints / expected official senior fixtures",
        "eligible_players": int(ledger["player_id"].nunique()),
        "windows": summaries,
        "all_players_pass_current_window": bool(len(current) and current.all()),
        "all_players_pass_pre_world_cup_window": bool(len(pre) and pre.all()),
        "coverage_gate_passed": bool(len(current) and current.all() and len(pre) and pre.all()),
        "rankings_allowed": False,
        "note": "Final rankings remain blocked until role and predictive gates also pass.",
    }
    (OUT_DIR / "coverage_audit_summary.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
