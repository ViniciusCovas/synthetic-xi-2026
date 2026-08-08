#!/usr/bin/env python3
"""Benchmark do modelo congelado contra as odds de mercado (harness).

A validação externa declara como limitação a ausência de comparação com o
mercado. Este harness fecha-a assim que existir um CSV de odds de fecho:

    data/reference/market_odds_worldcup2026.csv
    colunas: home_team, away_team, odds_home, odds_draw, odds_away, source
    (nomes de equipa iguais aos de external_pre_tournament_predictions.csv)

As odds são convertidas em probabilidades sem margem (de-vig proporcional) e
comparadas jogo a jogo com as previsões pré-torneio congeladas. Fontes
típicas: arquivo de odds de fecho de casas licenciadas (verificar termos).

Sem o CSV, o script sai com instruções — nunca inventa dados.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ODDS_PATH = Path("data/reference/market_odds_worldcup2026.csv")
PREDICTIONS_PATH = Path("data/validation/external_pre_tournament_predictions.csv")
OUT = Path("data/validation/market_benchmark_summary.json")


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    eps = 1e-12
    onehot = np.eye(3)[y]
    p = np.clip(p, eps, 1)
    p = p / p.sum(axis=1, keepdims=True)
    return {
        "log_loss": float(-np.mean(np.log(p[np.arange(len(y)), y]))),
        "brier": float(np.mean(np.sum((p - onehot) ** 2, axis=1))),
        "top1_accuracy": float(np.mean(p.argmax(axis=1) == y)),
    }


def main() -> None:
    if not ODDS_PATH.exists():
        raise SystemExit(
            f"Falta {ODDS_PATH}.\n"
            "Crie o CSV com: home_team, away_team, odds_home, odds_draw, "
            "odds_away, source — odds decimais de fecho dos 91+ jogos FT do "
            "Mundial 2026. O harness faz o resto."
        )
    odds = pd.read_csv(ODDS_PATH)
    predictions = pd.read_csv(PREDICTIONS_PATH)
    for frame in (odds, predictions):
        frame["key"] = frame["home_team"].map(norm) + "|" + frame["away_team"].map(norm)
    merged = predictions.merge(odds, on="key", suffixes=("", "_mkt"))
    if merged.empty:
        raise SystemExit("Nenhum jogo casou entre previsões e odds — verifique nomes.")

    inverse = 1.0 / merged[["odds_home", "odds_draw", "odds_away"]].to_numpy(float)
    market = inverse / inverse.sum(axis=1, keepdims=True)  # de-vig proporcional
    model = merged[["p_home", "p_draw", "p_away"]].to_numpy(float)
    outcome = merged["outcome"].to_numpy(int)  # 0=home,1=draw,2=away

    summary = {
        "status": "market_benchmark_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "matches_compared": int(len(merged)),
        "overround_mean": float(inverse.sum(axis=1).mean()),
        "model": scores(outcome, model),
        "market_devig": scores(outcome, market),
        "model_minus_market_log_loss": float(
            scores(outcome, model)["log_loss"]
            - scores(outcome, market)["log_loss"]
        ),
        "reading": (
            "log-loss do modelo menos o do mercado: negativo = modelo bate o "
            "mercado; pequenas diferenças positivas ainda podem indicar valor "
            "em nichos, mas a alegação padrão é 'não bate o mercado'."
        ),
        "odds_source": sorted(odds["source"].astype(str).unique()),
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
