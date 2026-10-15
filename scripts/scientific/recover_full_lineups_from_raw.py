#!/usr/bin/env python3
"""Recover complete team line-ups from committed raw API payloads without network calls.

Earlier adaptive batches intentionally flattened only target players. The original raw
line-up response, when available, contains the complete startXI. This recovery restores
all players so formation grids can be audited structurally.
"""
from __future__ import annotations

import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

OUT = Path("data/audits/position_ontology_v3")
RECOVERED = Path("data/lake/batches/batch_full_raw_recovery_lineups.csv.gz")
PATTERN = re.compile(r"fixture[_-](\d+).*lineups?\.json$", re.IGNORECASE)


def fixture_id_from_path(path: str) -> int | None:
    match = PATTERN.search(Path(path).name)
    return int(match.group(1)) if match else None


def load_payload(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RECOVERED.parent.mkdir(parents=True, exist_ok=True)
    paths = sorted(set(glob.glob("data/raw/**/*lineup*.json", recursive=True)))
    rows: list[dict[str, Any]] = []
    readable = 0
    response_blocks = 0
    for path in paths:
        fixture_id = fixture_id_from_path(path)
        if fixture_id is None:
            continue
        payload = load_payload(path)
        response = payload.get("response") or []
        if not isinstance(response, list):
            continue
        readable += 1
        for block in response:
            if not isinstance(block, dict):
                continue
            team = block.get("team") or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            response_blocks += 1
            formation = block.get("formation")
            for source, entries in (
                ("startXI", block.get("startXI") or []),
                ("substitutes", block.get("substitutes") or []),
            ):
                for entry in entries:
                    player = (entry or {}).get("player") or {}
                    player_id = player.get("id")
                    if player_id is None:
                        continue
                    rows.append({
                        "fixture_id": int(fixture_id),
                        "team_id": int(team_id),
                        "team_name": team.get("name"),
                        "formation": formation,
                        "lineup_source": source,
                        "player_id": int(player_id),
                        "player_name": player.get("name"),
                        "number": player.get("number"),
                        "lineup_position": player.get("pos"),
                        "grid": player.get("grid"),
                        "recovery_source_file": path,
                    })
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=[
            "fixture_id", "team_id", "team_name", "formation", "lineup_source",
            "player_id", "player_name", "number", "lineup_position", "grid",
            "recovery_source_file",
        ])
    else:
        frame = frame.sort_values(["fixture_id", "team_id", "lineup_source", "player_id"])
        frame = frame.drop_duplicates(["fixture_id", "team_id", "lineup_source", "player_id"], keep="last")
    frame.to_csv(RECOVERED, index=False, compression="gzip")

    starters = frame.loc[frame.lineup_source.eq("startXI")].copy() if not frame.empty else frame
    group_sizes = starters.groupby(["fixture_id", "team_id"]).player_id.nunique() if not starters.empty else pd.Series(dtype=int)
    status = {
        "status": "raw_full_lineup_recovery_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "raw_lineup_files_discovered": int(len(paths)),
        "raw_lineup_files_readable_with_fixture_id": int(readable),
        "team_response_blocks": int(response_blocks),
        "recovered_rows": int(len(frame)),
        "recovered_startxi_rows": int(len(starters)),
        "recovered_fixture_team_groups": int(len(group_sizes)),
        "groups_with_exactly_11_starters": int(group_sizes.eq(11).sum()),
        "output": str(RECOVERED),
        "next_action": (
            "rerun complete-lineup ontology audit using the recovered full grids"
            if len(frame)
            else "raw line-up payloads are absent; use targeted provider extraction"
        ),
    }
    (OUT / "raw_lineup_recovery_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
