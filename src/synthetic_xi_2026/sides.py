"""Evidencia de lado (derecho/izquierdo) desde la caché de alineaciones.

El lado observado de un jugador solo se usa si la orientación del grid del
proveedor fue validada contra anclas humanas revisadas
(`data/model_readiness/lateral_grid_validation.json`). Las anclas públicas de
rol (`data/reference/public_role_anchors_2026.csv`) tienen prioridad sobre la
evidencia de grid cuando declaran un lado inequívoco.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

LATERAL_VALIDATION_PATH = Path("data/model_readiness/lateral_grid_validation.json")
BATCH_DIR = Path("data/lake/batches")
PUBLIC_ANCHORS_PATH = Path("data/reference/public_role_anchors_2026.csv")

_ROLE_SIDE = {
    "RB": "R", "RCB": "R", "RW": "R",
    "LB": "L", "LCB": "L", "LW": "L",
}

_BAND_MAPPINGS = {
    "low_is_left": {"low": "L", "high": "R"},
    "low_is_right": {"low": "R", "high": "L"},
}


def _parse_grid(value: object) -> tuple[float, float] | tuple[None, None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    left, right = value.split(":", 1)
    try:
        return float(left), float(right)
    except ValueError:
        return None, None


def _grid_side_observations(mapping: dict[str, str]) -> pd.DataFrame:
    frames = [
        pd.read_csv(path)
        for path in sorted(glob.glob(str(BATCH_DIR / "batch_*_lineups.csv.gz")))
    ]
    if not frames:
        return pd.DataFrame(columns=["player_id", "side"])
    lineups = pd.concat(frames, ignore_index=True)
    lineups = lineups.loc[lineups["lineup_source"].astype(str).eq("startXI")].copy()
    lineups = lineups.drop_duplicates(
        ["fixture_id", "team_id", "player_id"], keep="last"
    )
    parsed = lineups["grid"].apply(_parse_grid)
    lineups["grid_row"] = parsed.apply(lambda item: item[0])
    lineups["grid_col"] = parsed.apply(lambda item: item[1])
    lineups = lineups.dropna(subset=["grid_row", "grid_col"])
    lineups["row_width"] = lineups.groupby(
        ["fixture_id", "team_id", "grid_row"]
    )["grid_col"].transform("max")
    lineups["grid_col_normalized"] = lineups["grid_col"] / lineups["row_width"]

    low = lineups["grid_col_normalized"] <= 0.34
    high = lineups["grid_col_normalized"] >= 0.76
    lineups = lineups.loc[low | high].copy()
    lineups["band"] = "low"
    lineups.loc[lineups["grid_col_normalized"] >= 0.76, "band"] = "high"
    lineups["side"] = lineups["band"].map(mapping)
    return lineups[["player_id", "fixture_id", "side"]]


def _anchor_sides() -> dict[int, str]:
    if not PUBLIC_ANCHORS_PATH.exists():
        return {}
    anchors = pd.read_csv(PUBLIC_ANCHORS_PATH)
    result: dict[int, str] = {}
    for row in anchors.itertuples(index=False):
        preferred = str(row.preferred_role or "")
        side = _ROLE_SIDE.get(preferred)
        if side is None:
            allowed = {
                _ROLE_SIDE.get(role.strip())
                for role in str(row.allowed_roles or "").split("|")
            }
            allowed.discard(None)
            side = allowed.pop() if len(allowed) == 1 else None
        if side is not None:
            result[int(row.player_id)] = side
    return result


def build_side_evidence(
    minimum_observations: int = 2,
    minimum_share: float = 0.60,
) -> tuple[dict[int, str], pd.DataFrame]:
    """Devuelve (player_id -> lado, tabla de evidencia auditable)."""
    if not LATERAL_VALIDATION_PATH.exists():
        return _anchor_sides(), pd.DataFrame()
    validation = json.loads(LATERAL_VALIDATION_PATH.read_text(encoding="utf-8"))
    mapping_name = validation.get("selected_mapping")
    if not validation.get("orientation_validated") or mapping_name not in _BAND_MAPPINGS:
        return _anchor_sides(), pd.DataFrame()

    observations = _grid_side_observations(_BAND_MAPPINGS[mapping_name])
    evidence_rows: list[dict[str, object]] = []
    sides: dict[int, str] = {}
    if not observations.empty:
        grouped = observations.groupby("player_id")["side"]
        for player_id, values in grouped:
            counts = values.value_counts()
            total = int(counts.sum())
            top_side = str(counts.index[0])
            share = float(counts.iloc[0] / total)
            accepted = total >= minimum_observations and share >= minimum_share
            if accepted:
                sides[int(player_id)] = top_side
            evidence_rows.append(
                {
                    "player_id": int(player_id),
                    "observations": total,
                    "majority_side": top_side,
                    "majority_share": share,
                    "accepted": accepted,
                    "source": f"grid:{mapping_name}",
                }
            )

    for player_id, side in _anchor_sides().items():
        sides[player_id] = side
        evidence_rows.append(
            {
                "player_id": player_id,
                "observations": None,
                "majority_side": side,
                "majority_share": 1.0,
                "accepted": True,
                "source": "public_role_anchor",
            }
        )
    return sides, pd.DataFrame(evidence_rows)
