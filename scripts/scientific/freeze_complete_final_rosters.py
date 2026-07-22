#!/usr/bin/env python3
"""Freeze nominal 26-player match squads for the complete final.

Real Best XI is selected mechanically from the canonical covered candidate table
using the already-declared conservative score. Synthetic players are named
instances of the frozen positional archetypes; this file does not create or
change their abilities. The engine's functional bench may consume these role
instances without introducing a new performance parameter.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/model_readiness/selection_sufficiency_all_players.csv"
SELECTION_STATUS = ROOT / "data/model_readiness/selection_sufficiency_status.json"
CONFIG = ROOT / "config/complete_final_preflight_v1.json"
OUT = ROOT / "data/model_readiness/complete_final_rosters_v1.json"
STARTING_SLOTS = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def real_player(row: pd.Series, *, squad_role: str, status: str) -> dict[str, Any]:
    return {
        "player_id": int(row.player_id),
        "name": str(row.player_name),
        "national_team": str(row.world_cup_team),
        "squad_role": squad_role,
        "resolved_role": str(row.resolved_role),
        "status": status,
        "conservative_score": round(float(row.conservative_score), 12),
        "overall": round(float(row.overall), 12),
        "uncertainty": round(float(row.uncertainty), 12),
        "finishing": round(float(row.finishing), 12),
        "creation": round(float(row.creation), 12),
        "goalkeeping": round(float(row.goalkeeping), 12),
        "source": "canonical_selection_sufficiency_all_players",
    }


def pick_best(frame: pd.DataFrame, role: str, used: set[int]) -> pd.Series:
    candidates = frame.loc[frame.resolved_role.eq(role) & ~frame.player_id.isin(used)].copy()
    if candidates.empty:
        raise SystemExit(f"No unused eligible candidate for role {role}")
    return candidates.sort_values(
        ["conservative_score", "overall", "minutes_num", "player_id"],
        ascending=[False, False, False, True],
    ).iloc[0]


def build_real_roster(frame: pd.DataFrame) -> dict[str, Any]:
    used: set[int] = set()
    starters: list[dict[str, Any]] = []
    for slot in STARTING_SLOTS:
        row = pick_best(frame, slot, used)
        used.add(int(row.player_id))
        starters.append(real_player(row, squad_role=slot, status="starter"))

    bench: list[dict[str, Any]] = []
    # Two reserve goalkeepers ensure a three-GK 26-player squad.
    for index in range(2):
        row = pick_best(frame, "GK", used)
        used.add(int(row.player_id))
        bench.append(real_player(row, squad_role=f"GK_reserve_{index + 1}", status="bench"))

    # One role-specific reserve for every outfield slot.
    for role in ["RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]:
        row = pick_best(frame, role, used)
        used.add(int(row.player_id))
        bench.append(real_player(row, squad_role=f"{role}_reserve", status="bench"))

    # Three best unused players across all roles complete the 26-player squad.
    remaining = frame.loc[~frame.player_id.isin(used)].sort_values(
        ["conservative_score", "overall", "minutes_num", "player_id"],
        ascending=[False, False, False, True],
    )
    for index, (_, row) in enumerate(remaining.head(3).iterrows(), start=1):
        used.add(int(row.player_id))
        bench.append(real_player(row, squad_role=f"best_available_{index}", status="bench"))

    if len(starters) != 11 or len(bench) != 15 or len(used) != 26:
        raise SystemExit(f"Invalid Real Best XI squad dimensions: {len(starters)}+{len(bench)} unique={len(used)}")
    penalty_order = sorted(
        [player for player in starters if player["resolved_role"] != "GK"],
        key=lambda player: (player["finishing"], player["creation"], player["overall"], -player["player_id"]),
        reverse=True,
    ) + [player for player in starters if player["resolved_role"] == "GK"]
    reserve_gks = [player for player in bench if player["resolved_role"] == "GK"]
    return {
        "team": "Real Best XI",
        "selection_policy": "highest frozen conservative_score per role; distinct players; deterministic tie-breakers",
        "starters": starters,
        "bench": bench,
        "registered_squad": starters + bench,
        "penalty_order_player_ids": [player["player_id"] for player in penalty_order],
        "emergency_goalkeeper_order_player_ids": [player["player_id"] for player in reserve_gks],
    }


def synthetic_instance(instance_id: str, role: str, archetype: str, status: str) -> dict[str, Any]:
    return {
        "player_id": instance_id,
        "name": instance_id.replace("_", " ").title(),
        "squad_role": role,
        "resolved_role": role.split("_")[0],
        "archetype": archetype,
        "status": status,
        "source": "frozen_positional_archetype_no_new_ability_parameter",
    }


def build_synthetic_roster() -> dict[str, Any]:
    archetype = {
        "GK": "GK", "RB": "FB", "RCB": "CB", "LCB": "CB", "LB": "FB",
        "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W", "ST": "ST",
    }
    starters = [synthetic_instance(f"synthetic_{role.lower()}_1", role, archetype[role], "starter") for role in STARTING_SLOTS]
    bench_roles = [
        "GK_reserve_1", "GK_reserve_2", "RB_reserve", "LB_reserve", "RCB_reserve",
        "LCB_reserve", "DM_reserve", "CM_reserve", "AM_reserve", "RW_reserve",
        "LW_reserve", "ST_reserve_1", "ST_reserve_2", "FB_utility", "W_utility",
    ]
    role_to_archetype = {
        "GK": "GK", "RB": "FB", "LB": "FB", "RCB": "CB", "LCB": "CB",
        "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W",
        "ST": "ST", "FB": "FB", "W": "W",
    }
    bench = []
    for label in bench_roles:
        role = label.split("_")[0]
        bench.append(synthetic_instance(f"synthetic_{label.lower()}", label, role_to_archetype[role], "bench"))
    penalty_priority = ["ST", "RW", "LW", "AM", "CM", "DM", "RB", "LB", "RCB", "LCB", "GK"]
    penalty_ids = [next(player["player_id"] for player in starters if player["resolved_role"] == role) for role in penalty_priority]
    reserve_gks = [player["player_id"] for player in bench if player["resolved_role"] == "GK"]
    return {
        "team": "Synthetic XI",
        "selection_policy": "named independent instances of eight frozen positional archetypes",
        "starters": starters,
        "bench": bench,
        "registered_squad": starters + bench,
        "penalty_order_player_ids": penalty_ids,
        "emergency_goalkeeper_order_player_ids": reserve_gks,
    }


def main() -> None:
    if not SOURCE.exists() or not SELECTION_STATUS.exists() or not CONFIG.exists():
        raise SystemExit("Preflight roster inputs are missing")
    selection = json.loads(SELECTION_STATUS.read_text(encoding="utf-8"))
    if not selection.get("selection_sufficiency_gate_passed") or selection.get("unresolved_players") != 0:
        raise SystemExit("Canonical selection gate is not complete")
    frame = pd.read_csv(SOURCE, low_memory=False)
    numeric = ["player_id", "conservative_score", "overall", "uncertainty", "finishing", "creation", "goalkeeping", "minutes_num"]
    for column in numeric:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame["covered"] = as_bool(frame.get("covered", pd.Series(False, index=frame.index)))
    frame["stable"] = as_bool(frame.get("stable", pd.Series(False, index=frame.index)))
    frame = frame.loc[
        frame.covered & frame.stable & frame.resolved_role.isin(STARTING_SLOTS)
        & frame.player_id.notna() & frame.conservative_score.notna() & frame.overall.notna()
    ].copy()
    frame["player_id"] = frame.player_id.astype(int)
    frame = frame.sort_values(["player_id", "role_observations"], ascending=[True, False]).drop_duplicates("player_id")

    real = build_real_roster(frame)
    synthetic = build_synthetic_roster()
    payload = {
        "status": "complete_final_rosters_frozen",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "roster_version": "complete_final_rosters_v1",
        "formation": STARTING_SLOTS,
        "teams": {"synthetic_xi": synthetic, "real_best_xi": real},
        "checks": {
            "real_registered_players": len(real["registered_squad"]),
            "real_unique_player_ids": len({player["player_id"] for player in real["registered_squad"]}),
            "real_goalkeepers": sum(player["resolved_role"] == "GK" for player in real["registered_squad"]),
            "synthetic_registered_instances": len(synthetic["registered_squad"]),
            "synthetic_unique_instance_ids": len({player["player_id"] for player in synthetic["registered_squad"]}),
            "synthetic_goalkeeper_instances": sum(player["resolved_role"] == "GK" for player in synthetic["registered_squad"]),
            "penalty_orders_present": bool(real["penalty_order_player_ids"] and synthetic["penalty_order_player_ids"]),
            "emergency_goalkeeper_orders_present": bool(real["emergency_goalkeeper_order_player_ids"] and synthetic["emergency_goalkeeper_order_player_ids"]),
        },
        "source_hashes": {
            str(SOURCE.relative_to(ROOT)): sha256(SOURCE),
            str(SELECTION_STATUS.relative_to(ROOT)): sha256(SELECTION_STATUS),
            str(CONFIG.relative_to(ROOT)): sha256(CONFIG),
        },
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], **payload["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
