#!/usr/bin/env python3
"""Rebuild exact-window coverage with deterministic challenger exposure evidence.

The frozen v2 coverage algorithm is reused without changing its thresholds. The
only added input is a dedicated player-fixture exposure table reconstructed from
complete lineups and substitution/red-card events for the predeclared 41
selection challengers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.scientific import build_scope_correct_coverage as frozen

RECONSTRUCTED = Path("data/model_readiness/selection_challenger_reconstructed_minutes.csv")
SCOPE_DIR = Path("data/audits/scope_correct_coverage")
LEDGER = SCOPE_DIR / "player_window_coverage_scope_correct.csv"
STATUS = SCOPE_DIR / "scope_correct_coverage_status.json"
AUDIT_DIR = Path("data/audits/selection_challenger_resolution")
TEMP_BATCH = Path("data/lake/batches/__selection_challenger_reconstructed_players.csv")


def main() -> None:
    if not RECONSTRUCTED.exists():
        raise SystemExit("Reconstructed challenger minutes are missing")
    reconstructed = pd.read_csv(RECONSTRUCTED, low_memory=False)
    required = {"player_id", "fixture_id", "minutes"}
    if reconstructed.empty or not required.issubset(reconstructed.columns):
        raise SystemExit("No valid reconstructed challenger exposure rows")
    reconstructed["minutes"] = pd.to_numeric(reconstructed.minutes, errors="coerce")
    reconstructed = reconstructed.dropna(subset=["player_id", "fixture_id", "minutes"])
    reconstructed = reconstructed.loc[reconstructed.minutes.gt(0)].copy()
    if reconstructed.empty:
        raise SystemExit("Reconstructed challenger exposure contains no positive minutes")

    # Materialize a temporary player-fixture table in the already audited batch
    # namespace. It is consumed by both the frozen coverage builder and the
    # promotion queue builder, then removed by the workflow before publication.
    TEMP_BATCH.parent.mkdir(parents=True, exist_ok=True)
    reconstructed[["player_id", "fixture_id", "minutes"]].sort_values(
        ["player_id", "fixture_id", "minutes"]
    ).drop_duplicates(["player_id", "fixture_id"], keep="last").to_csv(
        TEMP_BATCH, index=False
    )
    frozen.main()

    ledger = pd.read_csv(LEDGER, low_memory=False)
    ledger["player_id"] = pd.to_numeric(ledger.player_id, errors="coerce")
    reconstructed["player_id"] = pd.to_numeric(reconstructed.player_id, errors="coerce")
    reconstructed["minutes"] = pd.to_numeric(reconstructed.minutes, errors="coerce").fillna(0.0)
    by_window = reconstructed.groupby(["player_id", "window"], as_index=False).agg(
        reconstructed_exact_minutes=("minutes", "sum"),
        reconstructed_fixture_pairs=("fixture_id", "nunique"),
    )
    ledger = ledger.merge(by_window, on=["player_id", "window"], how="left")
    ledger["reconstructed_exact_minutes"] = ledger.reconstructed_exact_minutes.fillna(0.0)
    ledger["reconstructed_fixture_pairs"] = ledger.reconstructed_fixture_pairs.fillna(0).astype(int)
    ledger["provider_detailed_minutes"] = (
        pd.to_numeric(ledger.exact_detailed_minutes, errors="coerce").fillna(0.0)
        - ledger.reconstructed_exact_minutes
    ).clip(lower=0.0)
    affected = ledger.reconstructed_fixture_pairs.gt(0)
    ledger.loc[affected, "coverage_definition_version"] = (
        "exact_window_known_minutes_v3_complete_lineup_event_reconstruction"
    )
    ledger.loc[affected, "denominator_note"] = (
        "exact-window provider minutes plus deterministic exposure reconstructed "
        "from complete two-team lineups and substitution/red-card events; frozen "
        "80% fixture and minute thresholds unchanged"
    )
    ledger.to_csv(LEDGER, index=False)

    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    status.update({
        "status": "scope_correct_coverage_v3_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "threshold_changed": False,
        "model_parameters_changed": False,
        "frozen_fixture_endpoint_threshold": 0.80,
        "frozen_known_minute_threshold": 0.80,
        "reconstructed_physical_player_fixture_pairs": int(
            reconstructed[["player_id", "fixture_id"]].drop_duplicates().shape[0]
        ),
        "reconstructed_player_window_pairs": int(len(reconstructed)),
        "players_receiving_reconstructed_exposure": int(reconstructed.player_id.nunique()),
        "coverage_definition": (
            "fixture endpoint >=80% and exact-window known-minute lower bound >=80%; "
            "challenger missing exposure may be reconstructed only from complete "
            "two-team lineups and explicit full event evidence"
        ),
    })
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit = {
        "status": "challenger_reconstruction_integrated_into_coverage",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_parameters_changed": False,
        "thresholds_changed": False,
        "source": str(RECONSTRUCTED),
        "temporary_batch": str(TEMP_BATCH),
        "ledger": str(LEDGER),
        "affected_window_rows": int(affected.sum()),
        "affected_players": int(ledger.loc[affected, "player_id"].nunique()),
    }
    (AUDIT_DIR / "coverage_v3_integration_status.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
