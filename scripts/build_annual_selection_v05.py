#!/usr/bin/env python3
"""Constrói a seleção anual v0.5: XI real, plantel de 26, sintético em níveis.

Saídas em ``data/annual_v05/`` (novo diretório; nada do experimento oficial é
tocado): tabela anual, XI titular, plantel de 26, avatares em 4 níveis,
membresías, validação externa e manifesto com parâmetros. Cenários de liga
``primary``/``none``/``steep`` para sensibilidade.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.annual_v05 import (  # noqa: E402
    build_annual_table,
    build_synthetic_tiers,
    external_validation,
    select_real_xi,
    select_squad26,
)

OUT = ROOT / "data" / "annual_v05"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenario_xis = {}
    for scenario in ["primary", "none", "steep"]:
        table = build_annual_table(scenario)
        xi = select_real_xi(table)
        scenario_xis[scenario] = xi
        if scenario == "primary":
            squad = select_squad26(table, xi)
            avatars, members = build_synthetic_tiers(table)
            validation = external_validation(xi, table)
            table.to_csv(OUT / "annual_table_primary.csv", index=False)
            xi.to_csv(OUT / "real_annual_xi.csv", index=False)
            squad.to_csv(OUT / "real_annual_squad26.csv", index=False)
            avatars.to_csv(OUT / "synthetic_tiers.csv", index=False)
            members.to_csv(OUT / "synthetic_tier_members.csv", index=False)
            (OUT / "external_validation.json").write_text(
                json.dumps(validation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            xi.to_csv(OUT / f"real_annual_xi_{scenario}.csv", index=False)

    sensitivity = {
        scenario: dict(zip(frame["slot"], frame["player_name"]))
        for scenario, frame in scenario_xis.items()
    }
    manifest = {
        "status": "annual_selection_v0_5_built",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "role_resolution": "grid centrado v2 + âncoras públicas; flexíveis mantidos",
            "identity": "uma identidade por player_id",
            "eligibility_minutes": 900,
            "league_adjustment": {
                "table": "data/reference/league_strength_tiers_2026.csv",
                "primary": "T1=1.00, T2=0.92, T3/default=0.85 (volumes por-90; taxas não ajustadas)",
                "sensitivity": ["none (sem ajuste)", "steep (T2=0.85, T3/default=0.72)"],
            },
            "squad_rules": "11 titulares + 2 GK reservas + cobertura por posição + 3 vagas livres = 26, sem repetições",
            "synthetic_tiers": ["mean20", "top5", "p90", "max20"],
            "paired_uncertainty": "avatar herda média aparada das σ dos membros",
        },
        "xi_by_league_scenario": sensitivity,
        "frozen_official_v1_untouched": True,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest["xi_by_league_scenario"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
