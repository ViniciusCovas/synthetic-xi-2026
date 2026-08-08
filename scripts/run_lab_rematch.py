#!/usr/bin/env python3
"""Laboratório Fase A: rematch entre duas seleções reais da Copa 2026.

Simula uma final eliminatória completa (prorrogação, pênaltis, banco real,
janelas de substituição, cartões, VAR) entre quaisquer duas seleções, com
elencos construídos dos dados anuais v0.5 do repositório.

Uso:
  PYTHONPATH=. python scripts/run_lab_rematch.py \
      --home Spain --away Argentina --simulations 2000 --seed 20260808
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from simulator.calibrated_core import CalibrationTargets
from simulator.lab_conditions import venue_conditions
from simulator.lab_teams import LAB_MINIMUM_MINUTES, build_national_bundle
from simulator.official_complete_final import (
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
    official_config_with_seed,
)
from synthetic_xi_2026.annual_v05 import build_annual_table

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260808)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--venue", default=None,
        help="Cidade-sede da Copa 2026 (ex.: 'Mexico City'); ativa a Fase B",
    )
    parser.add_argument("--kickoff", choices=["day", "night"], default="night")
    parser.add_argument(
        "--conditions-scheme", choices=["off", "primary", "strong"],
        default="primary",
    )
    args = parser.parse_args()

    targets = CalibrationTargets.from_dict(
        json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    )
    table = build_annual_table("primary", minimum_minutes=LAB_MINIMUM_MINUTES)
    home_bundle, home_decisions = build_national_bundle(args.home, table)
    away_bundle, away_decisions = build_national_bundle(args.away, table)

    master = np.random.default_rng(args.seed)
    child_seeds = master.integers(1, 2**31 - 1, size=args.simulations)

    wins = Counter()
    decided_by = Counter()
    scores = Counter()
    goals_home: list[int] = []
    goals_away: list[int] = []
    representative_timeline: list[dict] | None = None
    conditions_report = None
    base_config = OfficialFinalConfig()
    if args.venue:
        conditions = venue_conditions(
            args.venue, kickoff=args.kickoff, scheme=args.conditions_scheme
        )
        conditions_report = conditions.describe()
        base_config = dataclasses.replace(
            base_config, **conditions.config_overrides()
        )

    for index, child in enumerate(child_seeds):
        config = official_config_with_seed(base_config, int(child))
        simulator = OfficialCompleteFinalSimulator(
            home_bundle, away_bundle, targets, config
        )
        result = simulator.simulate(keep_timeline=index == 0)
        wins[result.winner] += 1
        decided_by[result.decided_by] += 1
        scores[f"{result.home_goals}-{result.away_goals}"] += 1
        goals_home.append(result.home_goals)
        goals_away.append(result.away_goals)
        if index == 0:
            representative_timeline = result.timeline

    n = args.simulations
    summary = {
        "status": "lab_rematch_completed",
        "engine": "official complete-final engine (bench real, ET, penalties)",
        "home": args.home,
        "away": args.away,
        "simulations": n,
        "master_seed": args.seed,
        "eligibility_minutes_floor": LAB_MINIMUM_MINUTES,
        "conditions": conditions_report,
        "win_probability": {
            args.home: wins.get(args.home, 0) / n,
            args.away: wins.get(args.away, 0) / n,
        },
        "decided_by": {k: v / n for k, v in sorted(decided_by.items())},
        "mean_goals": {
            args.home: float(np.mean(goals_home)),
            args.away: float(np.mean(goals_away)),
        },
        "top_scorelines_before_penalties": [
            {"score": score, "probability": count / n}
            for score, count in scores.most_common(8)
        ],
        "team_construction_decisions": home_decisions + away_decisions,
        "interpretation": (
            "Resultado exploratório do laboratório: elencos derivados de dados "
            "anuais v0.5, motor calibrado no torneio. Não é o experimento "
            "oficial congelado."
        ),
    }

    out = Path(
        args.output
        or f"data/lab/rematch_{args.home.lower()}_{args.away.lower()}"
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, bundle in (("home", home_bundle), ("away", away_bundle)):
        pd.DataFrame(list(bundle.roster_rows)).to_csv(
            out / f"roster_{name}.csv", index=False
        )
    if representative_timeline:
        pd.DataFrame(representative_timeline).to_csv(
            out / "sample_match_timeline.csv", index=False
        )

    print(json.dumps({k: summary[k] for k in (
        "home", "away", "simulations", "win_probability", "decided_by", "mean_goals",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
