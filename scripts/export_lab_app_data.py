#!/usr/bin/env python3
"""Exporta dados e o pacote Python do laboratório para o app web.

Gera em ``web/public/lab/``:
- ``data/teams.json``: bundles pré-computados de todas as seleções da Copa
  que os dados anuais permitem montar (XI + banco + ordem de pênaltis);
- ``data/venues.json``: presets de condições por cidade-sede;
- ``data/calibration.json``: alvos de calibração do torneio;
- ``py/labsim/``: o motor de finais real (mesmos arquivos versionados) para
  executar no navegador via Pyodide — numpy apenas, sem pandas.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from simulator.lab_teams import LAB_MINIMUM_MINUTES, build_national_bundle
from synthetic_xi_2026.annual_v05 import build_annual_table

LAB_DIR = ROOT / "web" / "public" / "lab"
DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)

PACKAGE_SOURCES = {
    "engine.py": ROOT / "simulator" / "engine.py",
    "calibrated_core.py": ROOT / "simulator" / "calibrated_core.py",
    # Motor materializado v1.1 (export oficial versionado, não o bootstrap).
    "complete_final.py": ROOT
    / "official_engine" / "source_v1_1" / "simulator" / "complete_final.py",
    "official_complete_final.py": ROOT / "simulator" / "official_complete_final.py",
    "lab_conditions.py": ROOT / "simulator" / "lab_conditions.py",
    "official_profiles.py": ROOT / "simulator" / "lab_pyodide" / "official_profiles.py",
    "lab_runtime.py": ROOT / "simulator" / "lab_pyodide" / "lab_runtime.py",
}


def profile_payload(profile) -> dict:
    return {
        "player_id": profile.player_id,
        "name": profile.name,
        "role": profile.role,
        "minutes": profile.minutes,
        "overall": profile.overall,
        "uncertainty": profile.uncertainty,
        "synthetic": profile.synthetic,
        **{dim: float(getattr(profile, dim)) for dim in DIMENSIONS},
    }


def main() -> None:
    (LAB_DIR / "data").mkdir(parents=True, exist_ok=True)
    package_dir = LAB_DIR / "py" / "labsim"
    package_dir.mkdir(parents=True, exist_ok=True)

    table = build_annual_table("primary", minimum_minutes=LAB_MINIMUM_MINUTES)
    teams: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    for team_name in sorted(table["world_cup_team"].dropna().unique()):
        try:
            bundle, decisions = build_national_bundle(str(team_name), table)
        except (RuntimeError, ValueError) as error:
            skipped[str(team_name)] = str(error)
            continue
        teams[str(team_name)] = {
            "starters": [profile_payload(p) for p in bundle.team.players],
            "bench_by_role": {
                role: [profile_payload(p) for p in reserves]
                for role, reserves in bundle.bench_by_role.items()
            },
            "registered_ids": list(bundle.registered_ids),
            "starter_ids": list(bundle.starter_ids),
            "penalty_order_ids": list(bundle.penalty_order_ids),
            "emergency_goalkeeper_ids": list(bundle.emergency_goalkeeper_ids),
            "roster": list(bundle.roster_rows),
            "construction_decisions": decisions,
        }
    (LAB_DIR / "data" / "teams.json").write_text(
        json.dumps(teams, ensure_ascii=False), encoding="utf-8"
    )

    venues = pd.read_csv(ROOT / "data" / "reference" / "lab_venue_conditions_2026.csv")
    (LAB_DIR / "data" / "venues.json").write_text(
        venues.to_json(orient="records", force_ascii=False), encoding="utf-8"
    )
    shutil.copyfile(
        ROOT / "data" / "simulations" / "calibration" / "world_cup_2026_targets.json",
        LAB_DIR / "data" / "calibration.json",
    )

    for target_name, source in PACKAGE_SOURCES.items():
        shutil.copyfile(source, package_dir / target_name)
    (package_dir / "__init__.py").write_text(
        '"""Motor do laboratório para execução no navegador (Pyodide)."""\n',
        encoding="utf-8",
    )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "teams_exported": len(teams),
        "teams_skipped": skipped,
        "eligibility_minutes_floor": LAB_MINIMUM_MINUTES,
        "package_files": sorted(PACKAGE_SOURCES) + ["__init__.py"],
    }
    (LAB_DIR / "data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
