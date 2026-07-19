#!/usr/bin/env python3
"""Validate provider lateral-grid orientation against versioned role anchors."""

from __future__ import annotations

import glob
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

BATCH_DIR = Path("data/lake/batches")
REFERENCE_PATH = Path("data/reference/lateral_role_anchors.csv")
OUT_DIR = Path("data/model_readiness")


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def parse_grid(value: object) -> tuple[float | None, float | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    left, right = value.split(":", 1)
    try:
        return float(left), float(right)
    except ValueError:
        return None, None


def read_lineups() -> pd.DataFrame:
    frames = [
        pd.read_csv(path)
        for path in sorted(glob.glob(str(BATCH_DIR / "batch_*_lineups.csv.gz")))
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    anchors = pd.read_csv(REFERENCE_PATH)
    lineups = read_lineups()
    if lineups.empty:
        status = {
            "status": "waiting_for_lineup_data",
            "orientation_validated": False,
            "rankings_allowed": False,
        }
        (OUT_DIR / "lateral_grid_validation.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, indent=2))
        return

    lineups = lineups.loc[lineups["lineup_source"].astype(str).eq("startXI")].copy()
    lineups = lineups.drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
    parsed = lineups["grid"].apply(parse_grid)
    lineups["grid_row"] = parsed.apply(lambda item: item[0])
    lineups["grid_col"] = parsed.apply(lambda item: item[1])
    lineups = lineups.dropna(subset=["grid_row", "grid_col"])
    lineups["row_width"] = lineups.groupby(
        ["fixture_id", "team_id", "grid_row"]
    )["grid_col"].transform("max")
    lineups["grid_col_normalized"] = lineups["grid_col"] / lineups["row_width"]
    lineups["name_norm"] = lineups["player_name"].map(normalize_name)

    alias_to_anchor: dict[str, tuple[str, str, str]] = {}
    for row in anchors.itertuples(index=False):
        values = [row.canonical_name] + str(row.aliases).split("|")
        for value in values:
            alias_to_anchor[normalize_name(value)] = (
                str(row.canonical_name),
                str(row.expected_side).upper(),
                str(row.confidence),
            )

    records = []
    for row in lineups.itertuples(index=False):
        anchor = alias_to_anchor.get(row.name_norm)
        if not anchor:
            continue
        canonical, expected, confidence = anchor
        if row.grid_col_normalized <= 0.34:
            observed_band = "low"
        elif row.grid_col_normalized >= 0.76:
            observed_band = "high"
        else:
            continue
        records.append(
            {
                "canonical_name": canonical,
                "player_name": row.player_name,
                "fixture_id": int(row.fixture_id),
                "team_id": int(row.team_id),
                "formation": row.formation,
                "grid": row.grid,
                "grid_row": row.grid_row,
                "grid_col_normalized": float(row.grid_col_normalized),
                "observed_band": observed_band,
                "expected_side": expected,
                "confidence": confidence,
            }
        )

    evidence = pd.DataFrame(records)
    if evidence.empty:
        status = {
            "status": "no_anchor_observations_matched",
            "orientation_validated": False,
            "matched_anchor_players": 0,
            "anchor_observations": 0,
            "rankings_allowed": False,
        }
        (OUT_DIR / "lateral_grid_validation.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, indent=2))
        return

    mappings = {
        "low_is_left": {"low": "L", "high": "R"},
        "low_is_right": {"low": "R", "high": "L"},
    }
    results = []
    for name, mapping in mappings.items():
        predicted = evidence["observed_band"].map(mapping)
        agreement = float(predicted.eq(evidence["expected_side"]).mean())
        per_player = (
            evidence.assign(correct=predicted.eq(evidence["expected_side"]))
            .groupby("canonical_name")["correct"]
            .mean()
        )
        results.append(
            {
                "mapping": name,
                "observation_agreement": agreement,
                "player_majority_agreement": float((per_player >= 0.5).mean()),
            }
        )
    result_frame = pd.DataFrame(results).sort_values(
        ["observation_agreement", "player_majority_agreement"], ascending=False
    )
    winner = result_frame.iloc[0]
    matched_players = int(evidence["canonical_name"].nunique())
    observations = int(len(evidence))
    validated = bool(
        matched_players >= 5
        and observations >= 15
        and float(winner["observation_agreement"]) >= 0.80
        and float(winner["player_majority_agreement"]) >= 0.80
    )
    mapping_name = str(winner["mapping"]) if validated else None
    chosen_map = mappings[mapping_name] if mapping_name else {}
    evidence["inferred_side"] = evidence["observed_band"].map(chosen_map)
    evidence["correct_under_selected_mapping"] = (
        evidence["inferred_side"].eq(evidence["expected_side"])
        if validated
        else False
    )
    evidence.to_csv(OUT_DIR / "lateral_grid_anchor_evidence.csv", index=False)
    result_frame.to_csv(OUT_DIR / "lateral_grid_mapping_comparison.csv", index=False)

    status = {
        "status": "lateral_grid_orientation_evaluated",
        "orientation_validated": validated,
        "selected_mapping": mapping_name,
        "matched_anchor_players": matched_players,
        "anchor_observations": observations,
        "observation_agreement": float(winner["observation_agreement"]),
        "player_majority_agreement": float(winner["player_majority_agreement"]),
        "minimum_requirements": {
            "anchor_players": 5,
            "observations": 15,
            "agreement": 0.80,
        },
        "manual_anchor_source": str(REFERENCE_PATH),
        "rankings_allowed": False,
        "note": (
            "Left/right labels may be used only when orientation_validated is true. "
            "The audit depends on a versioned, human-reviewed anchor list."
        ),
    }
    (OUT_DIR / "lateral_grid_validation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
