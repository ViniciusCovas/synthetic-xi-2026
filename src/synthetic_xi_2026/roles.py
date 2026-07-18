"""Transparent functional-role inference from starting-lineup grids."""

from __future__ import annotations

from collections import Counter
from typing import Any


def parse_grid(grid: str | None) -> tuple[int, int] | None:
    if not grid or ":" not in grid:
        return None
    left, right = grid.split(":", maxsplit=1)
    try:
        return int(left), int(right)
    except ValueError:
        return None


def infer_starting_roles(lineup: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Infer eight functional roles for starters only.

    The algorithm uses provider position (G/D/M/F), formation, and grid row/column.
    It deliberately excludes substitute-only players because their precise role is not
    consistently encoded. Every classification retains its rule for auditing.
    """

    starters = lineup.get("startXI") or []
    parsed: list[dict[str, Any]] = []
    for item in starters:
        player = item.get("player") or {}
        player_id = player.get("id")
        grid = parse_grid(player.get("grid"))
        if player_id is None or grid is None:
            continue
        row, col = grid
        parsed.append(
            {
                "player_id": int(player_id),
                "player_name": player.get("name"),
                "provider_position": player.get("pos"),
                "row": row,
                "col": col,
            }
        )

    row_sizes = Counter(row["row"] for row in parsed)
    out: dict[int, dict[str, Any]] = {}
    max_row = max(row_sizes, default=1)
    formation = str(lineup.get("formation") or "")
    try:
        formation_lines = [int(part) for part in formation.split("-") if part]
    except ValueError:
        formation_lines = []

    for player in parsed:
        pos = player["provider_position"]
        row = player["row"]
        col = player["col"]
        count = row_sizes[row]
        edge = count >= 3 and col in {1, count}
        role = None
        rule = None

        if pos == "G" or row == 1:
            role, rule = "GK", "goalkeeper/provider-G"
        elif pos == "D":
            if count >= 4 and edge:
                role, rule = "FB", "defensive-row edge in back four/five"
            else:
                role, rule = "CB", "defensive-row central or back-three defender"
        elif pos == "F":
            if count >= 3 and edge:
                role, rule = "W", "forward-row edge in front three"
            else:
                role, rule = "ST", "central or two-player forward line"
        elif pos == "M":
            midfield_rows = sorted({
                item["row"] for item in parsed if item["provider_position"] == "M"
            })
            back_three_wingback = (
                bool(formation_lines)
                and formation_lines[0] == 3
                and len(midfield_rows) == 1
                and count >= 4
                and edge
            )
            if back_three_wingback:
                role, rule = "FB", "wide midfielder functioning as wing-back in back-three formation"
            elif len(midfield_rows) >= 2 and count >= 3 and edge and row == max(midfield_rows):
                role, rule = "W", "advanced-midfield edge"
            elif len(midfield_rows) >= 2 and row == min(midfield_rows):
                role, rule = "DM", "deepest midfield row"
            elif len(midfield_rows) >= 2 and row == max(midfield_rows):
                role, rule = "AM", "highest midfield row"
            else:
                role, rule = "CM", "single or intermediate midfield row"

        if role:
            out[player["player_id"]] = {
                **player,
                "position_group": role,
                "classification_rule": rule,
                "formation": lineup.get("formation"),
            }
    return out
