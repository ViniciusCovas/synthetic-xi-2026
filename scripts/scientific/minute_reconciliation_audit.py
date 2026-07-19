#!/usr/bin/env python3
"""Compare aggregate, precheck and current detailed minute ledgers.

Diagnostic only: this script does not alter coverage rules, rankings or gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

AUDIT_DIR = Path("data/audits/offline_readiness")
PRECHECK = Path("data/audits/annual_player_precheck.csv")
WINDOW = Path("data/model_readiness/player_window_coverage.csv")
UNRESOLVED = Path("data/model_readiness/selection_sufficiency_unresolved_players.csv")


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if not PRECHECK.exists() or not WINDOW.exists():
        status = {"status": "waiting_for_minute_ledgers"}
        (AUDIT_DIR / "minute_reconciliation_audit.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        return

    pre = pd.read_csv(PRECHECK)
    win = pd.read_csv(WINDOW)
    annual = win.loc[win["window"].eq("annual_current")].copy()
    keep = [
        "player_id", "player_name", "world_cup_team", "reported_minutes",
        "detailed_match_minutes", "detailed_minutes_share",
    ]
    pre = pre[[c for c in keep if c in pre.columns]].drop_duplicates("player_id")
    current_cols = [
        "player_id", "expected_official_fixtures", "processed_fixture_endpoints",
        "fixture_endpoint_coverage", "missing_fixture_endpoints",
        "detailed_appearance_fixtures", "detailed_minutes", "aggregate_reported_minutes",
        "minute_reconciliation_ratio_raw", "minute_reconciliation_ratio_clipped",
        "coverage_pass_80pct",
    ]
    annual = annual[[c for c in current_cols if c in annual.columns]].drop_duplicates("player_id")
    merged = pre.merge(annual, on="player_id", how="inner")
    for c in [
        "reported_minutes", "detailed_match_minutes", "detailed_minutes_share",
        "detailed_minutes", "aggregate_reported_minutes",
        "minute_reconciliation_ratio_clipped", "missing_fixture_endpoints",
        "fixture_endpoint_coverage",
    ]:
        if c in merged:
            merged[c] = pd.to_numeric(merged[c], errors="coerce")

    merged["minutes_present_precheck_not_current"] = (
        merged.get("detailed_match_minutes", 0) - merged.get("detailed_minutes", 0)
    ).clip(lower=0)
    merged["current_share"] = merged.get("minute_reconciliation_ratio_clipped", np.nan)
    merged["precheck_share"] = merged.get("detailed_minutes_share", np.nan)
    merged["precheck_pass80"] = merged["precheck_share"].ge(0.8)
    merged["current_pass80"] = merged["current_share"].ge(0.8)
    merged["classification"] = np.select(
        [
            merged["current_pass80"],
            merged["precheck_pass80"] & ~merged["current_pass80"],
            ~merged["precheck_pass80"] & ~merged["current_pass80"],
        ],
        [
            "current_ledger_passes",
            "minutes_exist_in_precheck_but_not_current_ledger",
            "both_ledgers_below_80pct",
        ],
        default="unclassified",
    )

    if UNRESOLVED.exists():
        unresolved_ids = set(pd.to_numeric(pd.read_csv(UNRESOLVED)["player_id"], errors="coerce").dropna().astype(int))
        merged["selection_unresolved"] = merged["player_id"].isin(unresolved_ids)
    else:
        merged["selection_unresolved"] = False

    merged = merged.sort_values(
        ["selection_unresolved", "minutes_present_precheck_not_current"],
        ascending=[False, False],
    )
    merged.to_csv(AUDIT_DIR / "minute_reconciliation_players.csv", index=False)

    counts = merged.groupby(["selection_unresolved", "classification"]).size().reset_index(name="players")
    counts.to_csv(AUDIT_DIR / "minute_reconciliation_classification.csv", index=False)

    unresolved = merged.loc[merged["selection_unresolved"]]
    status = {
        "status": "minute_reconciliation_audit_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "methodological_effect": "diagnostic_only",
        "players_compared": int(len(merged)),
        "unresolved_players_compared": int(len(unresolved)),
        "classification_counts_all": merged["classification"].value_counts().to_dict(),
        "classification_counts_unresolved": unresolved["classification"].value_counts().to_dict(),
        "unresolved_minutes_present_precheck_not_current_total": float(
            unresolved["minutes_present_precheck_not_current"].sum()
        ),
        "unresolved_players_zero_missing_fixtures": int(
            unresolved.get("missing_fixture_endpoints", pd.Series(dtype=float)).fillna(0).eq(0).sum()
        ),
        "interpretation": (
            "A large precheck/current gap indicates a reconciliation or source-scope problem; "
            "it is not by itself permission to relax the 80% gate."
        ),
        "next_action": (
            "trace the source and competition scope of precheck detailed_match_minutes, then "
            "rebuild the durable lake from cached raw responses before making new API calls"
        ),
    }
    (AUDIT_DIR / "minute_reconciliation_audit.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
