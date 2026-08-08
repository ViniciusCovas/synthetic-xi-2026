#!/usr/bin/env python3
"""Modelo de xG próprio + auditoria espacial das suposições do motor.

Ajusta uma regressão logística (numpy, gradiente, determinística) sobre os
5.8k remates internacionais do StatsBomb Open Data e produz:

1. ``xg_model_v1.json`` — coeficientes, métricas (log-loss, Brier), curvas de
   calibração e comparação com o xG do provedor;
2. ``engine_spatial_audit.json`` — taxas EMPÍRICAS de conversão, no-alvo e
   golo-dado-no-alvo por banda de distância e por tipo (jogo aberto, bola
   parada, pênalti), frente às constantes estruturais assumidas pelo motor de
   finais. É a evidência que transforma "suposto declarado" em "verificado".

Atribuição: Hudl StatsBomb Open Data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SB = Path("data/enrichment/statsbomb")
SEED = 20260808

# Constantes estruturais do motor de finais (complete_final v1.1) auditadas.
ENGINE_ASSUMPTIONS = {
    "goal_given_on_target_cap": 0.86,
    "penalty_goal_probability": 0.91,
    "penalty_effective_conversion_after_cap": 0.765,
}


def features(frame: pd.DataFrame) -> np.ndarray:
    return np.column_stack([
        np.ones(len(frame)),
        frame["distance_sb"].to_numpy(float),
        np.log1p(frame["distance_sb"].to_numpy(float)),
        frame["visible_angle_rad"].to_numpy(float),
        (frame["body_part"] == "Head").to_numpy(float),
        (frame["shot_type"] == "Free Kick").to_numpy(float),
        frame["under_pressure"].to_numpy(float),
        frame["one_on_one"].to_numpy(float),
        frame["first_time"].to_numpy(float),
    ])


FEATURE_NAMES = [
    "intercept", "distance", "log1p_distance", "visible_angle", "header",
    "free_kick", "under_pressure", "one_on_one", "first_time",
]


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1e-3,
                 iters: int = 4000, lr: float = 0.05) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    beta = np.zeros(X.shape[1])
    scale = X.std(axis=0); scale[0] = 1.0
    Xs = X / scale
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-Xs @ beta))
        grad = Xs.T @ (p - y) / len(y) + l2 * beta
        beta -= lr * grad
    _ = rng  # semente reservada para bootstraps futuros
    return beta / scale


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    eps = 1e-12
    p = np.clip(p, eps, 1 - eps)
    return {
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "brier": float(np.mean((p - y) ** 2)),
        "mean_predicted": float(p.mean()),
        "base_rate": float(y.mean()),
    }


def calibration_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        out.append({
            "bin_low": float(lo), "bin_high": float(hi),
            "n": int(mask.sum()),
            "predicted": float(p[mask].mean()),
            "observed": float(y[mask].mean()),
        })
    return out


def main() -> None:
    shots = pd.read_csv(SB / "international_shots.csv.gz")
    open_play = shots[~shots["shot_type"].isin(["Penalty"])].copy()
    y = open_play["is_goal"].to_numpy(float)
    X = features(open_play)

    # Divisão temporal determinística: treina em WC2018+Euro2020, testa em
    # WC2022+Euro2024 (fora-de-amostra de verdade, sem fuga).
    train_mask = open_play["season"].astype(str).isin(["2018", "2020"]).to_numpy()
    beta = fit_logistic(X[train_mask], y[train_mask])
    p_all = 1.0 / (1.0 + np.exp(-X @ beta))

    provider = open_play["statsbomb_xg"].to_numpy(float)
    metrics = {
        "train": evaluate(y[train_mask], p_all[train_mask]),
        "test_holdout_wc2022_euro2024": evaluate(y[~train_mask], p_all[~train_mask]),
        "provider_xg_on_same_holdout": evaluate(
            y[~train_mask], provider[~train_mask]
        ),
    }

    model = {
        "status": "xg_model_v1_fitted",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "training": "WC2018+Euro2020 (aberto, sem pênaltis)",
        "holdout": "WC2022+Euro2024",
        "n_shots_open_play": int(len(open_play)),
        "coefficients": dict(zip(FEATURE_NAMES, np.round(beta, 6).tolist())),
        "metrics": metrics,
        "calibration_bins_holdout": calibration_bins(
            y[~train_mask], p_all[~train_mask]
        ),
        "attribution": "Hudl StatsBomb Open Data",
    }
    (SB / "xg_model_v1.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- auditoria espacial do motor ----
    bands = pd.cut(
        shots["distance_sb"],
        [0, 6, 12, 18, 25, 40, 120],
        labels=["0-6", "6-12", "12-18", "18-25", "25-40", "40+"],
    )
    def rates(mask) -> dict:
        subset = shots[mask]
        on_target = subset["on_target"]
        return {
            "n": int(len(subset)),
            "p_goal": round(float(subset["is_goal"].mean()), 4),
            "p_on_target": round(float(on_target.mean()), 4),
            "p_goal_given_on_target": round(
                float(subset.loc[on_target, "is_goal"].mean()), 4
            ) if on_target.any() else None,
        }

    audit = {
        "status": "engine_spatial_audit_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample": "230 partidas internacionais (WC18/22, Euro20/24)",
        "by_distance_band": {
            str(band): rates((bands == band) & (shots["shot_type"] != "Penalty"))
            for band in bands.cat.categories
        },
        "penalties_in_game": rates(
            (shots["shot_type"] == "Penalty") & (shots["period"] < 5)
        ),
        "penalties_shootout": rates(
            (shots["shot_type"] == "Penalty") & (shots["period"] == 5)
        ),
        "set_pieces_free_kick": rates(shots["shot_type"] == "Free Kick"),
        "engine_assumptions_audited": ENGINE_ASSUMPTIONS,
        "verdicts": {},
    }
    empirical_pen = audit["penalties_in_game"]["p_goal"]
    max_ggot = max(
        v["p_goal_given_on_target"] or 0
        for v in audit["by_distance_band"].values()
    )
    audit["verdicts"] = {
        "penalty_conversion": {
            "engine_effective": ENGINE_ASSUMPTIONS[
                "penalty_effective_conversion_after_cap"
            ],
            "empirical": empirical_pen,
            "gap": round(
                empirical_pen
                - ENGINE_ASSUMPTIONS["penalty_effective_conversion_after_cap"], 4
            ),
        },
        "goal_given_on_target_cap": {
            "engine_cap": ENGINE_ASSUMPTIONS["goal_given_on_target_cap"],
            "empirical_max_by_band": max_ggot,
            "cap_binds_in_close_range": bool(
                max_ggot > ENGINE_ASSUMPTIONS["goal_given_on_target_cap"]
            ),
        },
    }
    (SB / "engine_spatial_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "xg_metrics": metrics,
        "penalty": audit["verdicts"]["penalty_conversion"],
        "ggot_cap": audit["verdicts"]["goal_given_on_target_cap"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
