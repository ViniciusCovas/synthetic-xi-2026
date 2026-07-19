#!/usr/bin/env python3
"""Reconcile exact-window detailed minutes from all cached fixture sources.

This preserves the existing 80% coverage policy. It corrects only the numerator:
all cached per-fixture player rows are unioned and deduplicated, then restricted
to the already frozen official-senior fixture inventory and exact windows.
The season-level aggregate denominator remains unchanged for this diagnostic.
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
OUT = AUDIT / "cache_reconciliation"

PLAYER_PATTERNS = [
    "data/lake/batches/*_players.csv.gz",
    "data/lake/batches/*_players.csv",
    "data/audits/fixture_detail_pilot_players.csv",
]


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def read_player_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    source_rows: list[dict] = []
    paths: list[str] = []
    for pattern in PLAYER_PATTERNS:
        paths.extend(glob.glob(pattern))
    for path in sorted(set(paths)):
        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            source_rows.append({"path": path, "status": "read_error", "error": str(exc)})
            continue
        required = {"player_id", "fixture_id"}
        if not required.issubset(frame.columns):
            source_rows.append({"path": path, "status": "schema_skipped", "rows": len(frame)})
            continue
        out = pd.DataFrame({
            "player_id": pd.to_numeric(frame["player_id"], errors="coerce"),
            "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
            "minutes": pd.to_numeric(frame.get("minutes", frame.get("minutes_num")), errors="coerce").fillna(0.0),
            "source_path": path,
        })
        if "team_id" in frame:
            out["team_id"] = pd.to_numeric(frame["team_id"], errors="coerce")
        out = out.dropna(subset=["player_id", "fixture_id"])
        out[["player_id", "fixture_id"]] = out[["player_id", "fixture_id"]].astype(int)
        frames.append(out)
        source_rows.append({
            "path": path,
            "status": "included",
            "rows": int(len(out)),
            "players": int(out.player_id.nunique()),
            "fixtures": int(out.fixture_id.nunique()),
            "minutes": float(out.minutes.sum()),
        })
    union = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["player_id", "fixture_id", "minutes", "source_path"]
    )
    return union, pd.DataFrame(source_rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ledger_path = MODEL / "player_window_coverage.csv"
    inventory_path = AUDIT / "exact_fixture_inventory.csv"
    if not ledger_path.exists() or not inventory_path.exists():
        raise SystemExit("Missing canonical ledger or exact fixture inventory")

    ledger = pd.read_csv(ledger_path, low_memory=False)
    fixtures = pd.read_csv(inventory_path, low_memory=False)
    union, sources = read_player_sources()
    sources.to_csv(OUT / "minute_reconciliation_sources.csv", index=False)

    fixtures["fixture_id"] = pd.to_numeric(fixtures["fixture_id"], errors="coerce")
    fixtures = fixtures.dropna(subset=["fixture_id"])
    fixtures["fixture_id"] = fixtures["fixture_id"].astype(int)
    fixtures["official_senior_main"] = as_bool(fixtures["official_senior_main"])
    fixtures["in_current_window"] = as_bool(fixtures["in_current_window"])
    fixtures["in_pre_world_cup_window"] = as_bool(fixtures["in_pre_world_cup_window"])
    fixture_flags = fixtures[[
        "fixture_id", "official_senior_main", "in_current_window", "in_pre_world_cup_window"
    ]].drop_duplicates("fixture_id")

    raw_pairs = int(union[["player_id", "fixture_id"]].drop_duplicates().shape[0])
    joined = union.merge(fixture_flags, on="fixture_id", how="left", validate="many_to_one")
    mapped = joined["official_senior_main"].notna()
    mapped_pairs = int(joined.loc[mapped, ["player_id", "fixture_id"]].drop_duplicates().shape[0])
    mapping_rate = float(mapped_pairs / raw_pairs) if raw_pairs else 0.0

    joined = joined.loc[mapped & joined["official_senior_main"].fillna(False)].copy()
    joined["minutes"] = pd.to_numeric(joined["minutes"], errors="coerce").fillna(0.0).clip(lower=0, upper=130)
    # Same player/fixture can exist in several caches. The maximum minutes is the
    # least-lossy deterministic reconciliation and prevents double counting.
    dedup = joined.sort_values(["player_id", "fixture_id", "minutes"]).drop_duplicates(
        ["player_id", "fixture_id"], keep="last"
    )
    dedup.to_csv(OUT / "reconciled_cached_player_fixtures.csv.gz", index=False, compression="gzip")

    totals: list[pd.DataFrame] = []
    for flag, window in [
        ("in_current_window", "annual_current"),
        ("in_pre_world_cup_window", "pre_world_cup"),
    ]:
        block = dedup.loc[dedup[flag].fillna(False)].groupby("player_id", as_index=False).agg(
            reconciled_detailed_appearance_fixtures=("fixture_id", "nunique"),
            reconciled_detailed_minutes=("minutes", "sum"),
        )
        block["window"] = window
        totals.append(block)
    reconciled = pd.concat(totals, ignore_index=True) if totals else pd.DataFrame()

    ledger["player_id"] = pd.to_numeric(ledger["player_id"], errors="coerce")
    ledger = ledger.dropna(subset=["player_id"])
    ledger["player_id"] = ledger["player_id"].astype(int)
    result = ledger.merge(reconciled, on=["player_id", "window"], how="left")
    result["reconciled_detailed_appearance_fixtures"] = pd.to_numeric(
        result["reconciled_detailed_appearance_fixtures"], errors="coerce"
    ).fillna(0).astype(int)
    result["reconciled_detailed_minutes"] = pd.to_numeric(
        result["reconciled_detailed_minutes"], errors="coerce"
    ).fillna(0.0)
    result["original_detailed_minutes"] = pd.to_numeric(result["detailed_minutes"], errors="coerce").fillna(0.0)
    result["original_coverage_pass_80pct"] = as_bool(result["coverage_pass_80pct"])
    # Never discard a minute already present in the canonical ledger.
    result["detailed_minutes"] = result[["original_detailed_minutes", "reconciled_detailed_minutes"]].max(axis=1)
    result["detailed_appearance_fixtures"] = result[[
        "detailed_appearance_fixtures", "reconciled_detailed_appearance_fixtures"
    ]].apply(pd.to_numeric, errors="coerce").fillna(0).max(axis=1).astype(int)

    fixture_coverage = pd.to_numeric(result["fixture_endpoint_coverage"], errors="coerce")
    aggregate_minutes = pd.to_numeric(result["aggregate_reported_minutes"], errors="coerce")
    current_mask = result["window"].eq("annual_current")
    ratio = result["detailed_minutes"] / aggregate_minutes.replace(0, np.nan)
    result["minute_reconciliation_ratio_raw"] = np.where(current_mask, ratio, np.nan)
    result["minute_reconciliation_ratio_clipped"] = np.where(current_mask, ratio.clip(0, 1), np.nan)
    annual_pass = fixture_coverage.ge(0.80) & (
        aggregate_minutes.isna() | ratio.ge(0.80)
    )
    pre_pass = fixture_coverage.ge(0.80)
    result["coverage_pass_80pct"] = np.where(current_mask, annual_pass, pre_pass)
    result["recovered_minutes"] = (result["detailed_minutes"] - result["original_detailed_minutes"]).clip(lower=0)
    result["pass_changed_false_to_true"] = (~result["original_coverage_pass_80pct"]) & result["coverage_pass_80pct"]
    result["denominator_note"] = np.where(
        current_mask,
        "existing aggregate-season denominator; exact-window detailed numerator reconciled from all cached official fixture rows",
        "exact fixture inventory; no independent aggregate-minute denominator",
    )

    result.to_csv(OUT / "player_window_coverage_reconciled.csv", index=False)
    deltas = result.loc[result["recovered_minutes"].gt(0) | result["pass_changed_false_to_true"]].copy()
    deltas.sort_values(["pass_changed_false_to_true", "recovered_minutes"], ascending=[False, False]).to_csv(
        OUT / "player_window_coverage_reconciliation_deltas.csv", index=False
    )

    original_pass = int(result["original_coverage_pass_80pct"].sum())
    reconciled_pass = int(result["coverage_pass_80pct"].sum())
    annual = result[result.window.eq("annual_current")]
    pre = result[result.window.eq("pre_world_cup")]
    ratio_over_105 = int((pd.to_numeric(annual["minute_reconciliation_ratio_raw"], errors="coerce") > 1.05).sum())
    promotion_safe = bool(
        mapping_rate >= 0.95
        and reconciled_pass >= original_pass
        and ratio_over_105 <= max(5, int(0.02 * len(annual)))
        and result["recovered_minutes"].sum() > 0
    )

    status = {
        "status": "cached_minute_reconciliation_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "methodological_change": False,
        "policy_preserved": "80% fixture endpoint coverage plus 80% annual detailed-minute reconciliation",
        "source_files_included": int((sources.get("status") == "included").sum()) if not sources.empty else 0,
        "raw_unique_player_fixture_pairs": raw_pairs,
        "mapped_official_inventory_pairs": mapped_pairs,
        "fixture_inventory_mapping_rate": mapping_rate,
        "deduplicated_official_player_fixture_pairs": int(len(dedup)),
        "recovered_detailed_minutes": float(result["recovered_minutes"].sum()),
        "players_with_recovered_minutes": int(result.loc[result.recovered_minutes.gt(0), "player_id"].nunique()),
        "window_rows_originally_passing": original_pass,
        "window_rows_passing_after_reconciliation": reconciled_pass,
        "false_to_true_window_rows": int(result["pass_changed_false_to_true"].sum()),
        "annual_players_passing_after_reconciliation": int(annual["coverage_pass_80pct"].sum()),
        "pre_world_cup_players_passing_after_reconciliation": int(pre["coverage_pass_80pct"].sum()),
        "annual_ratios_above_1_05": ratio_over_105,
        "promotion_safe": promotion_safe,
        "next_action": "promote reconciled ledger and rerun selection gate" if promotion_safe else "review mapping and ratio anomalies before promotion",
    }
    (OUT / "cached_minute_reconciliation_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
