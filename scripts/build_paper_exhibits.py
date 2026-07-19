#!/usr/bin/env python3
"""Generate reproducible paper exhibits from compact project outputs.

This script does not call external APIs and does not create new scientific claims.
It converts already published audits into figures and tables for manuscript review.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SIM_DIR = Path("data/simulations/calibrated_v0_2")
CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
EXTRACTION_PATH = Path("data/audits/adaptive_extraction_monitor.json")
READINESS_PATH = Path("data/model_readiness/annual_model_readiness.json")
OUT = Path("paper/exhibits")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_figure(name: str) -> None:
    plt.tight_layout()
    plt.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    convergence = pd.read_csv(SIM_DIR / "simulation_convergence.csv")
    scorelines = pd.read_csv(SIM_DIR / "simulation_scoreline_distribution.csv")
    audit = load_json(SIM_DIR / "simulation_audit_summary.json")
    calibration = load_json(CALIBRATION_PATH)
    extraction = load_json(EXTRACTION_PATH)
    readiness = load_json(READINESS_PATH)

    # Figure 1 — Monte Carlo convergence
    plt.figure(figsize=(8.4, 4.8))
    plt.plot(
        convergence["simulations"],
        convergence["synthetic_win_probability"] * 100,
        marker="o",
        label="Synthetic XI win",
    )
    plt.plot(
        convergence["simulations"],
        convergence["draw_probability"] * 100,
        marker="o",
        label="Draw",
    )
    plt.plot(
        convergence["simulations"],
        convergence["real_win_probability"] * 100,
        marker="o",
        label="Real Best XI win",
    )
    plt.xlabel("Number of simulated matches")
    plt.ylabel("Estimated probability (%)")
    plt.title("Monte Carlo convergence of match outcomes")
    plt.grid(alpha=0.25)
    plt.legend(frameon=False)
    save_figure("figure_01_monte_carlo_convergence.png")

    # Figure 2 — Most common scorelines
    top = scorelines.head(12).sort_values("probability")
    plt.figure(figsize=(8.4, 5.4))
    plt.barh(top["scoreline"], top["probability"] * 100)
    plt.xlabel("Probability (%)")
    plt.ylabel("Scoreline: Synthetic XI–Real Best XI")
    plt.title("Most frequent scorelines across 10,000 simulations")
    plt.grid(axis="x", alpha=0.25)
    save_figure("figure_02_scoreline_distribution.png")

    # Figure 3 — Calibration ratios. A ratio of 1 is exact aggregate agreement.
    observed = {
        "Goals": calibration["mean_goals_per_match"],
        "Shots": calibration["mean_shots_per_match"],
        "Shots on target": calibration["mean_shots_on_target_per_match"],
        "0–0 rate": calibration["zero_zero_rate"],
    }
    simulated = {
        "Goals": audit["means"]["total_goals"],
        "Shots": audit["means"]["total_shots"],
        "Shots on target": audit["means"]["total_shots_on_target"],
        "0–0 rate": audit["means"]["zero_zero_probability"],
    }
    ratios = pd.DataFrame(
        {
            "metric": list(observed),
            "simulated_to_observed_ratio": [
                simulated[key] / observed[key] for key in observed
            ],
        }
    )
    plt.figure(figsize=(8.4, 4.8))
    plt.bar(ratios["metric"], ratios["simulated_to_observed_ratio"])
    plt.axhline(1.0, linewidth=1.2, linestyle="--")
    plt.ylabel("Simulated / observed")
    plt.title("Aggregate calibration of the event simulator")
    plt.grid(axis="y", alpha=0.25)
    save_figure("figure_03_aggregate_calibration.png")
    ratios.to_csv(OUT / "table_calibration_ratios.csv", index=False)

    # Table 1 — Dataset and model readiness
    coverage = pd.DataFrame(
        [
            ["Eligible players", extraction["eligible_players"]],
            ["Eligible players observed", extraction["eligible_players_seen"]],
            ["Eligible-player recall", extraction["eligible_player_recall"]],
            ["Benchmark players", extraction["benchmark_players"]],
            ["Benchmark players observed", extraction["benchmark_players_seen"]],
            ["Benchmark-player recall", extraction["benchmark_player_recall"]],
            ["Fixtures processed", extraction["completed_fixtures"]],
            ["Active player-match rows", extraction["active_player_rows"]],
            ["Players with grid evidence", readiness["players_with_grid_evidence"]],
            ["Players in current annual window", readiness["current_window_players"]],
            ["Players in pre-World-Cup window", readiness["pre_world_cup_players"]],
        ],
        columns=["Indicator", "Value"],
    )
    coverage.to_csv(OUT / "table_01_data_and_model_readiness.csv", index=False)

    # Table 2 — Main exploratory simulation result
    result = pd.DataFrame(
        [
            ["Synthetic XI wins", audit["outcomes"]["synthetic_wins"], audit["probabilities"]["synthetic_win"]],
            ["Draws", audit["outcomes"]["draws"], audit["probabilities"]["draw"]],
            ["Real Best XI wins", audit["outcomes"]["real_best_xi_wins"], audit["probabilities"]["real_best_xi_win"]],
        ],
        columns=["Outcome", "Matches", "Probability"],
    )
    result.to_csv(OUT / "table_02_exploratory_match_outcomes.csv", index=False)

    # Table 3 — Distributional statistics
    metrics = []
    for key, label in [
        ("total_goals", "Total goals"),
        ("total_shots", "Total shots"),
        ("total_shots_on_target", "Shots on target"),
        ("home_xg", "Synthetic XI xG"),
        ("away_xg", "Real Best XI xG"),
    ]:
        row = {"Metric": label}
        row.update(audit["percentiles"][key])
        metrics.append(row)
    pd.DataFrame(metrics).to_csv(
        OUT / "table_03_simulation_percentiles.csv", index=False
    )

    # Table 4 — Scientific gates
    gates = pd.DataFrame(
        [
            ["Computational reproducibility", "Passed", "Same data and seeds reproduce the ledger"],
            ["Aggregate event calibration", "Passed", "Goals, shots, shots on target and 0–0 frequency"],
            ["Annual player coverage", "In progress", "Exact per-player coverage by temporal window pending"],
            ["Definitive eleven-role resolution", "Pending", "Requires lateral-orientation validation and ≥60% stability"],
            ["Out-of-sample predictive validation", "Pending", "Requires rolling-origin backtest and proper scoring rules"],
            ["Final team-comparison claim", "Blocked", "Exploratory until all methodological gates pass"],
        ],
        columns=["Gate", "Status", "Evidence or requirement"],
    )
    gates.to_csv(OUT / "table_04_scientific_gates.csv", index=False)

    summary = [
        "# Paper exhibit build",
        "",
        "Generated automatically from versioned project outputs.",
        "",
        "## Figures",
        "",
        "1. Monte Carlo convergence.",
        "2. Top scoreline distribution.",
        "3. Aggregate calibration ratios.",
        "",
        "## Tables",
        "",
        "1. Data and model readiness.",
        "2. Exploratory match outcomes.",
        "3. Simulation percentiles.",
        "4. Scientific validation gates.",
        "",
        "These exhibits do not remove the exploratory-status warning.",
    ]
    (OUT / "README.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
