#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SEED = 20260719
SOURCE = Path("data/processed/fixtures.csv")
OUTPUT = Path("data/forecasts/2026_final")
EXPECTED_BLOB_SHA = "e2fa340a1dd3b4678f85f89684fe5b9acc30e6d6"
RNG = np.random.default_rng(SEED)


def load_matches() -> tuple[pd.DataFrame, pd.DataFrame]:
    all_matches = pd.read_csv(SOURCE, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    all_matches["match_number"] = np.arange(1, len(all_matches) + 1)
    all_matches["knockout"] = (all_matches["match_number"] > 72).astype(int)
    regulation = all_matches[all_matches["status"].eq("FT")].reset_index(drop=True)
    return all_matches, regulation


def long_rows(matches: pd.DataFrame) -> pd.DataFrame:
    home = pd.DataFrame({
        "date": matches.date,
        "attack": matches.home_team,
        "defense": matches.away_team,
        "knockout": matches.knockout,
        "goals": matches.home_goals,
    })
    away = pd.DataFrame({
        "date": matches.date,
        "attack": matches.away_team,
        "defense": matches.home_team,
        "knockout": matches.knockout,
        "goals": matches.away_goals,
    })
    return pd.concat([home, away], ignore_index=True)


def pipeline(alpha: float) -> Pipeline:
    transform = ColumnTransformer(
        [("teams", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["attack", "defense"])],
        remainder="passthrough",
    )
    model = PoissonRegressor(alpha=alpha, solver="newton-cholesky", max_iter=80, tol=1e-6)
    return Pipeline([("transform", transform), ("model", model)])


def time_weights(dates: pd.Series, reference: pd.Timestamp, half_life: float | None) -> np.ndarray:
    if half_life is None:
        return np.ones(len(dates))
    age_days = (reference - pd.to_datetime(dates, utc=True)).dt.total_seconds().to_numpy() / 86400
    return 0.5 ** (age_days / half_life)


def result_probabilities(home_lambda: float, away_lambda: float, maximum: int = 10) -> np.ndarray:
    home = poisson.pmf(np.arange(maximum + 1), home_lambda)
    away = poisson.pmf(np.arange(maximum + 1), away_lambda)
    matrix = np.outer(home, away)
    values = np.array([np.tril(matrix, -1).sum(), np.trace(matrix), np.triu(matrix, 1).sum()])
    return values / values.sum()


def tune(matches: pd.DataFrame) -> tuple[dict, list[dict]]:
    split = len(matches) - 18
    train, test = matches.iloc[:split], matches.iloc[split:]
    evaluations = []
    for alpha in (0.03, 0.1, 0.3, 1.0):
        for half_life in (21.0, None):
            rows = long_rows(train)
            fitted = pipeline(alpha)
            fitted.fit(
                rows[["attack", "defense", "knockout"]],
                rows.goals,
                model__sample_weight=time_weights(rows.date, train.date.max(), half_life),
            )
            probabilities, observed = [], []
            for match in test.itertuples(index=False):
                home = pd.DataFrame([{"attack": match.home_team, "defense": match.away_team, "knockout": match.knockout}])
                away = pd.DataFrame([{"attack": match.away_team, "defense": match.home_team, "knockout": match.knockout}])
                home_lambda = float(fitted.predict(home)[0])
                away_lambda = float(fitted.predict(away)[0])
                probabilities.append(result_probabilities(home_lambda, away_lambda))
                observed.append(0 if match.home_goals > match.away_goals else 1 if match.home_goals == match.away_goals else 2)
            evaluations.append({
                "alpha": alpha,
                "half_life_days": half_life,
                "log_loss": float(log_loss(observed, np.asarray(probabilities), labels=[0, 1, 2])),
            })
    return min(evaluations, key=lambda item: item["log_loss"]), evaluations


def fit(matches: pd.DataFrame, alpha: float, half_life: float | None) -> Pipeline:
    rows = long_rows(matches)
    fitted = pipeline(alpha)
    fitted.fit(
        rows[["attack", "defense", "knockout"]],
        rows.goals,
        model__sample_weight=time_weights(rows.date, matches.date.max(), half_life),
    )
    return fitted


def team_games(matches: pd.DataFrame, team: str) -> pd.DataFrame:
    rows = []
    for match in matches.itertuples(index=False):
        if match.home_team == team:
            rows.append((match.date, match.home_goals, match.away_goals))
        elif match.away_team == team:
            rows.append((match.date, match.away_goals, match.home_goals))
    return pd.DataFrame(rows, columns=["date", "gf", "ga"])


def shrunk_lambda(matches: pd.DataFrame, team: str, opponent: str, team_sample: pd.DataFrame, opponent_sample: pd.DataFrame) -> float:
    global_rate = (matches.home_goals.sum() + matches.away_goals.sum()) / (2 * len(matches))
    prior_games = 4.0

    def rate(frame: pd.DataFrame, column: str) -> float:
        return float((frame[column].sum() + prior_games * global_rate) / (len(frame) + prior_games))

    attack = rate(team_sample, "gf") / global_rate
    defense = rate(opponent_sample, "ga") / global_rate
    knockout = matches[matches.knockout.eq(1)]
    group = matches[matches.knockout.eq(0)]
    knockout_rate = (knockout.home_goals.sum() + knockout.away_goals.sum()) / (2 * len(knockout))
    group_rate = (group.home_goals.sum() + group.away_goals.sum()) / (2 * len(group))
    return float(global_rate * attack * defense * knockout_rate / group_rate)


def uncertainty_worlds(matches: pd.DataFrame, spain_glm: float, argentina_glm: float, count: int = 5000) -> np.ndarray:
    spain = team_games(matches, "Spain")
    argentina = team_games(matches, "Argentina")
    worlds = np.zeros((count, 2))
    glm_weight = 0.72
    for index in range(count):
        spain_sample = spain.iloc[RNG.integers(0, len(spain), len(spain))].reset_index(drop=True)
        argentina_sample = argentina.iloc[RNG.integers(0, len(argentina), len(argentina))].reset_index(drop=True)
        spain_form = shrunk_lambda(matches, "Spain", "Argentina", spain_sample, argentina_sample)
        argentina_form = shrunk_lambda(matches, "Argentina", "Spain", argentina_sample, spain_sample)
        worlds[index, 0] = math.exp(glm_weight * math.log(spain_glm) + (1 - glm_weight) * math.log(spain_form))
        worlds[index, 1] = math.exp(glm_weight * math.log(argentina_glm) + (1 - glm_weight) * math.log(argentina_form))
    return worlds


def simulate(worlds: np.ndarray, count: int = 250000, tempo_sigma: float = 0.2) -> dict:
    lambdas = worlds[RNG.integers(0, len(worlds), count)]
    tempo = np.exp(RNG.normal(-0.5 * tempo_sigma**2, tempo_sigma, count))
    spain = RNG.poisson(lambdas[:, 0] * tempo)
    argentina = RNG.poisson(lambdas[:, 1] * tempo)
    level_90 = spain == argentina
    extra_tempo = np.exp(RNG.normal(-0.5 * tempo_sigma**2, tempo_sigma, level_90.sum()))
    final_spain, final_argentina = spain.copy(), argentina.copy()
    final_spain[level_90] += RNG.poisson(lambdas[level_90, 0] * extra_tempo / 3)
    final_argentina[level_90] += RNG.poisson(lambdas[level_90, 1] * extra_tempo / 3)
    penalties = final_spain == final_argentina
    coin = RNG.random(penalties.sum()) < 0.5
    champion_spain = final_spain > final_argentina
    champion_argentina = final_argentina > final_spain
    champion_spain[penalties] = coin
    champion_argentina[penalties] = ~coin
    scorelines = Counter(zip(spain.tolist(), argentina.tolist()))
    return {
        "regulation_probabilities": {
            "spain_win": float((spain > argentina).mean()),
            "draw": float(level_90.mean()),
            "argentina_win": float((spain < argentina).mean()),
        },
        "trophy_probabilities": {
            "spain": float(champion_spain.mean()),
            "argentina": float(champion_argentina.mean()),
        },
        "expected_goals_90": {"spain": float(spain.mean()), "argentina": float(argentina.mean())},
        "extra_time_probability": float(level_90.mean()),
        "penalty_probability": float(penalties.mean()),
        "top_scorelines_90": [
            {"score": f"{home}-{away}", "probability": frequency / count}
            for (home, away), frequency in scorelines.most_common(10)
        ],
    }


def summary(matches: pd.DataFrame, team: str) -> dict:
    games = team_games(matches, team)
    return {
        "matches": int(len(games)),
        "goals_for": int(games.gf.sum()),
        "goals_against": int(games.ga.sum()),
        "clean_sheets": int(games.ga.eq(0).sum()),
    }


def main() -> None:
    all_matches, regulation = load_matches()
    best, evaluations = tune(regulation)
    fitted = fit(regulation, best["alpha"], best["half_life_days"])
    spain_row = pd.DataFrame([{"attack": "Spain", "defense": "Argentina", "knockout": 1}])
    argentina_row = pd.DataFrame([{"attack": "Argentina", "defense": "Spain", "knockout": 1}])
    spain_glm = float(fitted.predict(spain_row)[0])
    argentina_glm = float(fitted.predict(argentina_row)[0])
    worlds = uncertainty_worlds(regulation, spain_glm, argentina_glm)
    simulation = simulate(worlds)
    result = {
        "status": "pre_match_forecast_complete",
        "data_freeze_utc": "2026-07-15T23:59:59Z",
        "source_path": str(SOURCE),
        "expected_source_blob_sha": EXPECTED_BLOB_SHA,
        "seed": SEED,
        "matches_used": int(len(regulation)),
        "model": {
            "selected_alpha": best["alpha"],
            "selected_half_life_days": best["half_life_days"],
            "holdout_log_loss": best["log_loss"],
            "shared_tempo_sigma": 0.2,
            "uncertainty_worlds": int(len(worlds)),
            "simulated_matches": 250000,
        },
        "lambda_interval_95": {
            "spain": [float(np.quantile(worlds[:, 0], 0.025)), float(np.quantile(worlds[:, 0], 0.975))],
            "argentina": [float(np.quantile(worlds[:, 1], 0.025)), float(np.quantile(worlds[:, 1], 0.975))],
        },
        "simulation": simulation,
        "full_tournament_context": {
            "spain": summary(all_matches, "Spain"),
            "argentina": summary(all_matches, "Argentina"),
        },
        "claim_scope": "Reproducible probabilistic pre-match forecast, not certainty.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "forecast_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame(evaluations).sort_values("log_loss").to_csv(OUTPUT / "model_tuning.csv", index=False)
    pd.DataFrame(simulation["top_scorelines_90"]).to_csv(OUTPUT / "top_scorelines.csv", index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
