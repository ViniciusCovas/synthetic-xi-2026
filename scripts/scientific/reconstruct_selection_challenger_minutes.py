#!/usr/bin/env python3
"""Reconstruct exact exposure minutes for the frozen set of 41 challengers.

Only complete two-team lineup evidence and the full provider event feed are used.
The performance model, player ratings, role ontology, eligibility threshold, and
selection thresholds are not modified.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PRIORITY_PATH = Path("data/model_readiness/selection_sufficiency_priority_fixtures.csv")
UNRESOLVED_PATH = Path("data/model_readiness/selection_sufficiency_unresolved_players.csv")
EVIDENCE_DIR = Path("data/lake/selection_challenger_evidence")
OUT_PATH = Path("data/model_readiness/selection_challenger_reconstructed_minutes.csv")
AUDIT_DIR = Path("data/audits/selection_challenger_resolution")
STATUS_PATH = AUDIT_DIR / "minute_reconstruction_status.json"
TERMINAL = {"FT", "AET", "PEN"}


def read_many(pattern: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(glob.glob(pattern)):
        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception:
            continue
        frame["_source_path"] = path
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def scalar_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> None:
    now = datetime.now(timezone.utc)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if not PRIORITY_PATH.exists() or not UNRESOLVED_PATH.exists():
        raise SystemExit("Frozen challenger inputs are missing")

    priority = pd.read_csv(PRIORITY_PATH, low_memory=False)
    unresolved = pd.read_csv(UNRESOLVED_PATH, low_memory=False)
    for frame in (priority, unresolved):
        frame["player_id"] = pd.to_numeric(frame.player_id, errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)
    unresolved_ids = set(unresolved.player_id)
    priority["fixture_id"] = pd.to_numeric(priority.fixture_id, errors="coerce")
    priority = priority.dropna(subset=["fixture_id"])
    priority["fixture_id"] = priority.fixture_id.astype(int)
    pairs = priority.loc[
        priority.player_id.isin(unresolved_ids)
        & priority.get("priority_reason", "").astype(str).eq("known_startXI_without_detailed_row"),
        ["player_id", "fixture_id", "window", "selection_resolution_reason", "resolved_role"],
    ].drop_duplicates()

    lineups = read_many(str(EVIDENCE_DIR / "challenger_full_lineups_*.csv.gz"))
    events = read_many(str(EVIDENCE_DIR / "challenger_full_events_*.csv.gz"))
    metadata = read_many(str(EVIDENCE_DIR / "challenger_fixture_metadata_*.csv"))
    if lineups.empty or metadata.empty:
        raise SystemExit("Full challenger lineup evidence is missing")

    for frame, columns in [
        (lineups, ["fixture_id", "team_id", "player_id"]),
        (events, ["fixture_id", "team_id", "player_id", "assist_id", "elapsed"]),
        (metadata, ["fixture_id", "home_team_id", "away_team_id", "home_startxi_count", "away_startxi_count"]),
    ]:
        for column in columns:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    lineups = lineups.dropna(subset=["fixture_id", "player_id"])
    lineups[["fixture_id", "player_id"]] = lineups[["fixture_id", "player_id"]].astype(int)
    lineups["team_id"] = pd.to_numeric(lineups.get("team_id"), errors="coerce")
    lineups = lineups.sort_values("_source_path").drop_duplicates(
        ["fixture_id", "team_id", "lineup_source", "player_id"], keep="last"
    )
    if not events.empty:
        events = events.dropna(subset=["fixture_id"])
        events["fixture_id"] = events.fixture_id.astype(int)
        events = events.sort_values("_source_path").drop_duplicates(
            ["fixture_id", "event_type", "detail", "elapsed", "player_id", "assist_id", "team_id"],
            keep="last",
        )
    metadata = metadata.dropna(subset=["fixture_id"])
    metadata["fixture_id"] = metadata.fixture_id.astype(int)
    metadata = metadata.sort_values("_source_path").drop_duplicates("fixture_id", keep="last")
    meta = metadata.set_index("fixture_id").to_dict("index")

    event_type = events.get("event_type", pd.Series("", index=events.index)).astype(str).str.lower()
    detail = events.get("detail", pd.Series("", index=events.index)).astype(str).str.lower()
    events["is_substitution"] = event_type.eq("subst")
    events["is_red_exit"] = event_type.eq("card") & (
        detail.str.contains("red", na=False) | detail.str.contains("second yellow", na=False)
    )

    rows: list[dict] = []
    unresolved_rows: list[dict] = []
    for pair in pairs.itertuples(index=False):
        pid = int(pair.player_id)
        fixture_id = int(pair.fixture_id)
        fixture_meta = meta.get(fixture_id, {})
        status_short = str(fixture_meta.get("status_short") or "").upper()
        match_max = 120.0 if status_short in {"AET", "PEN"} else 90.0
        terminal = status_short in TERMINAL
        events_present = scalar_bool(fixture_meta.get("events_key_present", False))
        event_count = int(
            pd.to_numeric(pd.Series([fixture_meta.get("event_count")]), errors="coerce")
            .fillna(0).iloc[0]
        )
        home_complete = float(fixture_meta.get("home_startxi_count") or 0) >= 11
        away_complete = float(fixture_meta.get("away_startxi_count") or 0) >= 11
        complete_lineups = home_complete and away_complete

        player_lineup = lineups.loc[
            lineups.fixture_id.eq(fixture_id) & lineups.player_id.eq(pid)
        ].copy()
        if player_lineup.empty:
            unresolved_rows.append({
                "player_id": pid,
                "fixture_id": fixture_id,
                "window": pair.window,
                "reason": "target_player_absent_from_full_lineup",
            })
            continue
        player_lineup["starter"] = player_lineup.lineup_source.astype(str).str.lower().eq("startxi")
        lineup_row = player_lineup.sort_values("starter", ascending=False).iloc[0]
        team_id = int(lineup_row.team_id) if pd.notna(lineup_row.team_id) else None
        starter = bool(lineup_row.starter)

        fixture_events = events.loc[events.fixture_id.eq(fixture_id)].copy()
        team_events = (
            fixture_events.loc[fixture_events.team_id.eq(team_id)]
            if team_id is not None else fixture_events.iloc[0:0]
        )
        team_substitution_count = int(team_events.is_substitution.sum()) if not team_events.empty else 0
        explicit_exit = fixture_events.loc[
            fixture_events.player_id.eq(pid)
            & (fixture_events.is_substitution | fixture_events.is_red_exit)
        ]
        exit_minute = pd.to_numeric(explicit_exit.get("elapsed"), errors="coerce").dropna().min()
        exit_minute = (
            float(min(max(exit_minute, 0.0), match_max)) if pd.notna(exit_minute) else None
        )

        exact_minutes: float | None = None
        method: str | None = None
        evidence_grade: str | None = None
        entry_minute: float | None = None
        if starter:
            if exit_minute is not None:
                exact_minutes = exit_minute
                method = "starter_explicit_substitution_or_red_exit"
                evidence_grade = "A"
            elif (
                terminal
                and complete_lineups
                and events_present
                and event_count > 0
                and team_substitution_count > 0
            ):
                exact_minutes = match_max
                method = "starter_full_match_no_exit_in_team_substitution_feed"
                evidence_grade = "B"
        else:
            explicit_entry = fixture_events.loc[
                fixture_events.is_substitution & fixture_events.assist_id.eq(pid)
            ]
            entry = pd.to_numeric(explicit_entry.get("elapsed"), errors="coerce").dropna().min()
            if pd.notna(entry):
                entry_minute = float(min(max(entry, 0.0), match_max))
                end = exit_minute if exit_minute is not None and exit_minute >= entry_minute else match_max
                exact_minutes = max(0.0, end - entry_minute)
                method = "substitute_explicit_entry_and_exit_or_full_time"
                evidence_grade = "A"

        if exact_minutes is None or exact_minutes <= 0:
            unresolved_rows.append({
                "player_id": pid,
                "fixture_id": fixture_id,
                "window": pair.window,
                "team_id": team_id,
                "starter": starter,
                "terminal_status": terminal,
                "complete_two_team_lineups": complete_lineups,
                "events_key_present": events_present,
                "event_count": event_count,
                "team_substitution_count": team_substitution_count,
                "reason": "insufficient_deterministic_exposure_evidence",
            })
            continue

        rows.append({
            "player_id": pid,
            "fixture_id": fixture_id,
            "window": pair.window,
            "team_id": team_id,
            "lineup_source": "startXI" if starter else "substitutes",
            "minutes": exact_minutes,
            "entry_minute": entry_minute,
            "exit_minute": exit_minute,
            "match_max_minutes": match_max,
            "status_short": status_short,
            "reconstruction_method": method,
            "evidence_grade": evidence_grade,
            "complete_two_team_lineups": complete_lineups,
            "events_key_present": events_present,
            "event_count": event_count,
            "team_substitution_count": team_substitution_count,
            "selection_resolution_reason": pair.selection_resolution_reason,
            "resolved_role": pair.resolved_role,
            "model_parameters_changed": False,
            "thresholds_changed": False,
        })

    reconstructed = pd.DataFrame(rows)
    if not reconstructed.empty:
        reconstructed = reconstructed.sort_values(
            ["player_id", "fixture_id", "evidence_grade", "window"]
        ).drop_duplicates(["player_id", "fixture_id", "window"], keep="first")
    reconstructed.to_csv(OUT_PATH, index=False)
    unresolved_evidence = pd.DataFrame(unresolved_rows)
    unresolved_evidence.to_csv(AUDIT_DIR / "minute_reconstruction_unresolved_pairs.csv", index=False)

    resolved_players = set(reconstructed.player_id) if not reconstructed.empty else set()
    status = {
        "status": "selection_challenger_minutes_reconstructed",
        "generated_at_utc": now.isoformat(),
        "methodological_effect": "exposure_data_reconstruction_only",
        "frozen_challengers": int(len(unresolved_ids)),
        "priority_player_fixture_window_pairs": int(len(pairs)),
        "reconstructed_player_fixture_window_pairs": int(len(reconstructed)),
        "reconstructed_unique_physical_pairs": int(
            reconstructed[["player_id", "fixture_id"]].drop_duplicates().shape[0]
        ) if not reconstructed.empty else 0,
        "challengers_with_at_least_one_reconstructed_pair": int(len(resolved_players)),
        "unresolved_evidence_pairs": int(len(unresolved_evidence)),
        "evidence_grade_counts": (
            reconstructed.evidence_grade.value_counts().to_dict() if not reconstructed.empty else {}
        ),
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
        "output": str(OUT_PATH),
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
