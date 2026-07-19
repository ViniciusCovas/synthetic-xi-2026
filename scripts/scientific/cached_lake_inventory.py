#!/usr/bin/env python3
"""Inventory all cached football data sources without network access.

Diagnostic only: this script does not change eligibility, coverage gates, rankings,
or model outputs. It discovers every local player/lineup cache, measures overlap,
and quantifies minutes recoverable from sources not currently used by the exact
coverage ledger.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(".")
OUT = Path("data/audits/cache_reconciliation")
MODEL = Path("data/model_readiness")
AUDIT = Path("data/audits")

PLAYER_HINTS = ("player", "players")
LINEUP_HINTS = ("lineup", "lineups")
CSV_PATTERNS = [
    "data/lake/**/*.csv",
    "data/lake/**/*.csv.gz",
    "data/processed/**/*.csv",
    "data/processed/**/*.csv.gz",
    "data/audits/**/*.csv",
    "data/audits/**/*.csv.gz",
]


def rel(path: str | Path) -> str:
    return str(Path(path).as_posix())


def read_csv_safe(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def numeric(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(index=frame.index, dtype=float)


def classify(path: str, columns: list[str]) -> str:
    lower = path.lower()
    cols = {c.lower() for c in columns}
    if any(h in lower for h in LINEUP_HINTS):
        return "lineup_candidate"
    if any(h in lower for h in PLAYER_HINTS):
        return "player_candidate"
    if {"player_id", "fixture_id"}.issubset(cols):
        return "player_fixture_table"
    if "fixture_id" in cols and any("position" in c for c in cols):
        return "lineup_candidate"
    return "other"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for pattern in CSV_PATTERNS:
        paths.extend(glob.glob(pattern, recursive=True))
    paths = sorted(set(paths))

    inventory_rows: list[dict] = []
    player_parts: list[pd.DataFrame] = []
    lineup_schemas: list[dict] = []

    for path in paths:
        frame = read_csv_safe(path)
        columns = frame.columns.astype(str).tolist()
        kind = classify(path, columns)
        inventory_rows.append({
            "path": rel(path),
            "kind": kind,
            "rows": int(len(frame)),
            "columns": " | ".join(columns),
            "has_player_id": "player_id" in frame.columns,
            "has_fixture_id": "fixture_id" in frame.columns,
            "has_minutes": any(c in frame.columns for c in ("minutes", "minutes_num", "detailed_minutes")),
        })

        if kind in {"player_candidate", "player_fixture_table"} and {"player_id", "fixture_id"}.issubset(frame.columns):
            p = pd.DataFrame({
                "player_id": pd.to_numeric(frame["player_id"], errors="coerce"),
                "fixture_id": pd.to_numeric(frame["fixture_id"], errors="coerce"),
                "minutes": numeric(frame, ("minutes", "minutes_num")),
                "source_path": rel(path),
            })
            for flag in ("in_current_window", "in_pre_world_cup_window"):
                if flag in frame.columns:
                    p[flag] = frame[flag].astype(str).str.lower().isin({"true", "1", "yes"})
            if "team_id" in frame.columns:
                p["team_id"] = pd.to_numeric(frame["team_id"], errors="coerce")
            p = p.dropna(subset=["player_id", "fixture_id"])
            if not p.empty:
                p[["player_id", "fixture_id"]] = p[["player_id", "fixture_id"]].astype(int)
                player_parts.append(p)

        if kind == "lineup_candidate":
            lineup_schemas.append({
                "path": rel(path),
                "rows": int(len(frame)),
                "columns": " | ".join(columns),
                "sample": json.dumps(frame.head(2).fillna("").to_dict("records"), ensure_ascii=False)[:4000],
            })

    inventory = pd.DataFrame(inventory_rows)
    inventory.to_csv(OUT / "cached_csv_inventory.csv", index=False)
    pd.DataFrame(lineup_schemas).to_csv(OUT / "lineup_source_schemas.csv", index=False)

    if player_parts:
        union = pd.concat(player_parts, ignore_index=True)
        union["minutes"] = pd.to_numeric(union["minutes"], errors="coerce").fillna(0.0)
        source_summary = union.groupby("source_path", as_index=False).agg(
            rows=("fixture_id", "size"),
            players=("player_id", "nunique"),
            fixtures=("fixture_id", "nunique"),
            minutes=("minutes", "sum"),
        ).sort_values("minutes", ascending=False)
        source_summary.to_csv(OUT / "player_source_summary.csv", index=False)

        dedup = union.sort_values(["player_id", "fixture_id", "minutes"]).drop_duplicates(
            ["player_id", "fixture_id"], keep="last"
        )
        dedup.to_csv(OUT / "cached_player_fixture_union.csv.gz", index=False, compression="gzip")
        player_totals = dedup.groupby("player_id", as_index=False).agg(
            cached_detailed_fixtures=("fixture_id", "nunique"),
            cached_detailed_minutes=("minutes", "sum"),
        )
    else:
        union = pd.DataFrame()
        source_summary = pd.DataFrame()
        player_totals = pd.DataFrame(columns=["player_id", "cached_detailed_fixtures", "cached_detailed_minutes"])

    precheck_path = AUDIT / "annual_player_precheck.csv"
    ledger_path = MODEL / "player_window_coverage.csv"
    unresolved_path = MODEL / "selection_sufficiency_unresolved_players.csv"

    precheck = read_csv_safe(str(precheck_path)) if precheck_path.exists() else pd.DataFrame()
    ledger = read_csv_safe(str(ledger_path)) if ledger_path.exists() else pd.DataFrame()
    unresolved = read_csv_safe(str(unresolved_path)) if unresolved_path.exists() else pd.DataFrame()

    compare = player_totals.copy()
    if not precheck.empty and "player_id" in precheck:
        keep = [c for c in ["player_id", "player_name", "reported_minutes", "detailed_match_minutes"] if c in precheck.columns]
        pc = precheck[keep].copy()
        pc["player_id"] = pd.to_numeric(pc["player_id"], errors="coerce")
        compare = compare.merge(pc.dropna(subset=["player_id"]).drop_duplicates("player_id"), on="player_id", how="outer")
    if not ledger.empty and "player_id" in ledger:
        current = ledger[ledger.get("window", "").astype(str).eq("annual_current")].copy()
        keep = [c for c in ["player_id", "detailed_minutes", "aggregate_reported_minutes", "fixture_endpoint_coverage", "missing_fixture_endpoints", "coverage_pass_80pct"] if c in current.columns]
        current = current[keep]
        current["player_id"] = pd.to_numeric(current["player_id"], errors="coerce")
        current = current.rename(columns={
            "detailed_minutes": "ledger_detailed_minutes",
            "aggregate_reported_minutes": "ledger_aggregate_minutes",
            "coverage_pass_80pct": "ledger_pass",
        })
        compare = compare.merge(current.dropna(subset=["player_id"]).drop_duplicates("player_id"), on="player_id", how="outer")

    unresolved_ids: set[int] = set()
    if not unresolved.empty and "player_id" in unresolved:
        unresolved_ids = set(pd.to_numeric(unresolved["player_id"], errors="coerce").dropna().astype(int))
    if "player_id" in compare:
        compare["player_id"] = pd.to_numeric(compare["player_id"], errors="coerce")
        compare["is_unresolved"] = compare["player_id"].isin(unresolved_ids)
        compare["cache_minus_ledger_minutes"] = (
            pd.to_numeric(compare.get("cached_detailed_minutes"), errors="coerce").fillna(0)
            - pd.to_numeric(compare.get("ledger_detailed_minutes"), errors="coerce").fillna(0)
        )
    compare.to_csv(OUT / "cache_vs_current_ledger.csv", index=False)

    raw_json = sorted(glob.glob("data/raw/**/*.json", recursive=True))
    status = {
        "status": "cached_lake_inventory_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "methodological_effect": "diagnostic_only",
        "csv_files_scanned": len(paths),
        "raw_json_files_available": len(raw_json),
        "player_sources_found": int(len(source_summary)),
        "lineup_sources_found": int(len(lineup_schemas)),
        "cached_unique_player_fixture_pairs": int(len(player_totals) and len(pd.concat(player_parts, ignore_index=True).drop_duplicates(["player_id", "fixture_id"]))),
        "cached_players": int(player_totals["player_id"].nunique()) if not player_totals.empty else 0,
        "cached_minutes_total": float(player_totals["cached_detailed_minutes"].sum()) if not player_totals.empty else 0.0,
        "unresolved_players_in_comparison": int(compare.get("is_unresolved", pd.Series(dtype=bool)).sum()) if not compare.empty else 0,
        "positive_cache_minus_ledger_players": int((pd.to_numeric(compare.get("cache_minus_ledger_minutes"), errors="coerce").fillna(0) > 0).sum()) if not compare.empty else 0,
        "positive_cache_minus_ledger_minutes": float(pd.to_numeric(compare.get("cache_minus_ledger_minutes"), errors="coerce").clip(lower=0).fillna(0).sum()) if not compare.empty else 0.0,
        "next_action": "use source inventory and lineup schema to build a scope-correct exact-window coverage ledger",
    }
    (OUT / "cached_lake_inventory_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
