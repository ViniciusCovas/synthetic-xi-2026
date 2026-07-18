#!/usr/bin/env python3
"""Refresh the dated 2026 World Cup snapshot and publish static JSON artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.api_football import APIFootballClient  # noqa: E402
from synthetic_xi_2026.config import StudySpec  # noqa: E402
from synthetic_xi_2026.export import export_web_data  # noqa: E402
from synthetic_xi_2026.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Synthetic XI World Cup 2026 data")
    parser.add_argument("--cutoff-utc", default=None, help="ISO-8601 frozen data cutoff")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--min-minutes", type=float, default=180.0)
    parser.add_argument("--prior-minutes", type=float, default=180.0)
    parser.add_argument("--seed", type=int, default=20260718)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = StudySpec(
        requested_top_n=args.top_n,
        minimum_minutes=args.min_minutes,
        reliability_prior_minutes=args.prior_minutes,
        seed=args.seed,
    )
    client = APIFootballClient()
    artifacts = run_pipeline(client, spec=spec, cutoff_utc=args.cutoff_utc)
    export_web_data()
    print(artifacts["manifest"])


if __name__ == "__main__":
    main()
