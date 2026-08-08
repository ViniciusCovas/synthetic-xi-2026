#!/usr/bin/env python3
"""Força de liga ESTIMADA por contrastes intra-jogador (v2, 100% offline).

Modelo aditivo de dois fatores sobre o rating por jogador-jogo do lake:

    rating[i,j] = efeito_jogador[i] + efeito_liga[j] + ruído

ajustado por backfitting ponderado por minutos. Como o mesmo jogador aparece
em várias competições (liga + UCL + seleção), o efeito de liga é identificado
pelas diferenças *dentro do mesmo jogador* — controlando a qualidade
individual. Um efeito de liga alto significa "os mesmos jogadores rendem mais
aí" (liga mais fácil) e recebe fator < 1.

Mapeamento declarado (constantes pré-fixadas, não ajustadas aos resultados):
    fator = clip(1 − 0.5 · (efeito_liga − efeito_big5), 0.70, 1.05)

Ligas com amostra insuficiente (< 8 jogadores ou < 60 linhas) não recebem
estimativa e caem no default do cenário. Substitui os *tiers supostos* como
cenário `estimated`; o cenário `primary` pré-registrado permanece intacto.
"""

from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BIG5 = [39, 140, 78, 135, 61]
SLOPE, FLOOR, CEIL = 0.5, 0.70, 1.05
MIN_PLAYERS, MIN_ROWS = 8, 60
OUT_CSV = Path("data/reference/league_strength_estimated_2026.csv")
OUT_STATUS = Path("data/reference/league_strength_estimated_status.json")


def load_rows() -> pd.DataFrame:
    frames = [
        pd.read_csv(path, usecols=[
            "player_id", "league_id", "league_name", "minutes", "rating",
            "in_current_window",
        ])
        for path in sorted(glob.glob("data/lake/batches/batch_*_players.csv.gz"))
    ]
    rows = pd.concat(frames, ignore_index=True)
    rows = rows[rows["in_current_window"] == True]  # noqa: E712
    rows["rating"] = pd.to_numeric(rows["rating"], errors="coerce")
    rows["minutes"] = pd.to_numeric(rows["minutes"], errors="coerce").fillna(0.0)
    rows = rows.dropna(subset=["rating"])
    rows = rows[(rows["rating"] > 0) & (rows["minutes"] >= 30)]
    return rows


def backfit(rows: pd.DataFrame, iterations: int = 60) -> pd.Series:
    weight = rows["minutes"].to_numpy(float)
    rating = rows["rating"].to_numpy(float)
    players = rows["player_id"].to_numpy()
    leagues = rows["league_id"].to_numpy()
    player_effect = pd.Series(0.0, index=pd.unique(players))
    league_effect = pd.Series(0.0, index=pd.unique(leagues))
    for _ in range(iterations):
        residual = rating - league_effect.reindex(leagues).to_numpy()
        player_effect = (
            pd.DataFrame({"p": players, "v": residual * weight, "w": weight})
            .groupby("p").sum().eval("v / w")
        )
        residual = rating - player_effect.reindex(players).to_numpy()
        league_effect = (
            pd.DataFrame({"l": leagues, "v": residual * weight, "w": weight})
            .groupby("l").sum().eval("v / w")
        )
    return league_effect


def main() -> None:
    rows = load_rows()
    league_effect = backfit(rows)
    counts = rows.groupby("league_id").agg(
        league_name=("league_name", "first"),
        rows=("rating", "size"),
        players=("player_id", "nunique"),
        minutes=("minutes", "sum"),
    )
    table = counts.join(league_effect.rename("league_effect"))
    eligible = (table["players"] >= MIN_PLAYERS) & (table["rows"] >= MIN_ROWS)

    big5 = table.loc[[i for i in BIG5 if i in table.index]]
    reference = float(
        np.average(big5["league_effect"], weights=big5["minutes"])
    )
    table["estimable"] = eligible
    table["factor_estimated"] = np.where(
        eligible,
        np.clip(1.0 - SLOPE * (table["league_effect"] - reference), FLOOR, CEIL),
        np.nan,
    )
    table = table.sort_values("league_effect")
    table.reset_index().to_csv(OUT_CSV, index=False)

    status = {
        "status": "league_strength_estimated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "two-way additive backfitting on per-match provider rating, minute-weighted; identified by within-player contrasts",
        "rows_used": int(len(rows)),
        "players": int(rows["player_id"].nunique()),
        "leagues_total": int(len(table)),
        "leagues_estimable": int(eligible.sum()),
        "reference": "minute-weighted Big-5 mean effect",
        "mapping": f"factor = clip(1 - {SLOPE}*(effect - big5), {FLOOR}, {CEIL})",
        "big5_effect": reference,
        "extremes": {
            "hardest": table[table["estimable"]].head(5)[
                ["league_name", "league_effect", "factor_estimated"]
            ].round(3).to_dict("records"),
            "easiest": table[table["estimable"]].tail(5)[
                ["league_name", "league_effect", "factor_estimated"]
            ].round(3).to_dict("records"),
        },
    }
    OUT_STATUS.write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
