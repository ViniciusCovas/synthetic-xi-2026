#!/usr/bin/env python3
"""Build provisional teams and run an exploratory Synthetic XI match simulation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from simulator.engine import SimulationConfig, simulate_many
from simulator.profiles import build_teams, team_to_rows

OUT_DIR = Path("data/simulations/exploratory_v0_1")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    synthetic, real, avatars, real_selection = build_teams(top_n=20)
    result = simulate_many(
        synthetic,
        real,
        simulations=10_000,
        seed=20260718,
        config=SimulationConfig(average_possessions=103.0),
    )
    result["version"] = "exploratory_v0.1"
    result["data_scope"] = "Partial annual-current extraction available at workflow runtime"
    result["interpretation"] = (
        "The output validates the simulator architecture. It is not a final estimate of "
        "Synthetic XI superiority until player-level coverage and eleven-role gates pass."
    )

    (OUT_DIR / "simulation_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    avatars.to_csv(OUT_DIR / "synthetic_xi_membership.csv", index=False)
    real_selection.to_csv(OUT_DIR / "real_best_xi_provisional.csv", index=False)
    pd.DataFrame(team_to_rows(synthetic)).to_csv(
        OUT_DIR / "synthetic_xi_profiles.csv", index=False
    )
    pd.DataFrame(team_to_rows(real)).to_csv(
        OUT_DIR / "real_best_xi_profiles.csv", index=False
    )
    representative = result.get("representative_match")
    if representative:
        pd.DataFrame(representative["timeline"]).to_csv(
            OUT_DIR / "representative_match_timeline.csv", index=False
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
