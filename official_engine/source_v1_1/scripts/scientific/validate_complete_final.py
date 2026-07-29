#!/usr/bin/env python3
"""Execute engineering checks and repository-level scientific gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from simulator.calibrated_core import CalibrationTargets
from simulator.profiles_v2 import build_teams
from simulator.validation import validate_complete_final_engine

CALIBRATION_PATH = Path("data/simulations/calibration/world_cup_2026_targets.json")
DEFAULT_OUT = Path("data/simulations/complete_final_v1/validation_report.json")


# Complete Final validation JSON scalar normalization v1
def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=20260723)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--allow-engineering-failure",
        action="store_true",
        help="Write diagnostics but return success even if engineering checks fail.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    targets = CalibrationTargets.from_dict(payload)
    synthetic, real, _, _ = build_teams(top_n=args.top_n)
    report = validate_complete_final_engine(
        synthetic,
        real,
        targets,
        simulations=args.simulations,
        seed=args.seed,
        repository_root=Path("."),
    )
    report = _to_builtin(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = [
        "# Validação do motor de final completa",
        "",
        f"- Versão: `{report['engine_version']}`",
        f"- Simulações do lote principal: **{report['simulation_count']}**",
        f"- Gate de engenharia: **{'PASS' if report['engineering_gate']['passed'] else 'FAIL'}**",
        f"- Gate científico para publicação: **{'PASS' if report['scientific_publication_gate']['passed'] else 'BLOCKED'}**",
        "",
        "## Checks de engenharia",
        "",
    ]
    markdown.extend(
        f"- `{key}`: **{'PASS' if value else 'FAIL'}**"
        for key, value in report["engineering_gate"]["checks"].items()
    )
    markdown.extend(["", "## Gates científicos", ""])
    markdown.extend(
        f"- `{key}`: **{'PASS' if value else 'BLOCKED'}**"
        for key, value in report["scientific_publication_gate"]["checks"].items()
    )
    args.output.with_suffix(".md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["engineering_gate"], ensure_ascii=False, indent=2))
    print(json.dumps(report["scientific_publication_gate"], ensure_ascii=False, indent=2))
    if not report["engineering_gate"]["passed"] and not args.allow_engineering_failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
