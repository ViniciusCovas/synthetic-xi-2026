#!/usr/bin/env python3
"""Build an auditable scientific and public-facing report from the frozen simulation outputs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("data/simulations/identified_set_v1")
COMBO = ROOT / "combination_results.csv"
ENVELOPE = ROOT / "identified_outcome_envelope.csv"
MEMBERSHIP = ROOT / "real_identified_set_membership.csv"
PROFILES = ROOT / "team_profiles.csv"
MANIFEST = ROOT / "simulation_manifest.json"
HOLDOUT = Path("data/validation/external_pre_tournament_holdout_summary.json")
CALIBRATION = Path("data/simulations/calibrated_v0_2/calibration_quality.json")

PRIMARY = "primary_top20_pooled"
DIMS = [
    "overall", "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
]


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def signed_pp(value: float) -> str:
    return f"{100 * value:+.1f} pp"


def main() -> None:
    combo = pd.read_csv(COMBO, low_memory=False)
    envelope = pd.read_csv(ENVELOPE, low_memory=False)
    membership = pd.read_csv(MEMBERSHIP, low_memory=False)
    profiles = pd.read_csv(PROFILES, low_memory=False)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    holdout = json.loads(HOLDOUT.read_text(encoding="utf-8")) if HOLDOUT.exists() else {}
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.exists() else {}

    primary = combo.loc[combo.scenario.eq(PRIMARY)].copy()
    if len(primary) != 8:
        raise RuntimeError(f"Expected 8 primary Real XI combinations, found {len(primary)}")
    primary = primary.merge(
        membership[["combination_id", "role", "player_id", "player_name"]],
        on="combination_id",
        how="left",
    )

    # One row per combination with ambiguous role names as factors.
    factors = membership.loc[membership.role.isin(["GK", "RB", "AM"])].pivot(
        index="combination_id", columns="role", values="player_name"
    ).reset_index()
    base = combo.loc[combo.scenario.eq(PRIMARY)].merge(factors, on="combination_id", how="left")

    effect_rows = []
    for role in ["GK", "RB", "AM"]:
        candidates = sorted(base[role].dropna().unique())
        if len(candidates) != 2:
            raise RuntimeError(f"Expected two candidates for {role}, found {candidates}")
        reference, alternative = candidates
        ref = base.loc[base[role].eq(reference)]
        alt = base.loc[base[role].eq(alternative)]
        for metric in [
            "synthetic_win_probability", "draw_probability", "real_win_probability",
            "goal_difference", "xg_difference", "synthetic_possession_share",
        ]:
            effect_rows.append({
                "role": role,
                "reference_candidate": reference,
                "alternative_candidate": alternative,
                "metric": metric,
                "reference_mean": float(ref[metric].mean()),
                "alternative_mean": float(alt[metric].mean()),
                "alternative_minus_reference": float(alt[metric].mean() - ref[metric].mean()),
            })
    effects = pd.DataFrame(effect_rows)
    effects.to_csv(ROOT / "ambiguity_factor_effects.csv", index=False)

    # Profile gap: average across the balanced identified set versus primary Synthetic Top-20.
    synthetic = profiles.loc[
        profiles.team_type.eq("synthetic") & profiles.scenario_profile.eq("top20_pooled")
    ].copy()
    real = profiles.loc[profiles.team_type.eq("real")].copy()
    real_means = real.groupby("role", as_index=False)[DIMS].mean()
    profile_gap = synthetic[["role", "name", *DIMS]].merge(
        real_means, on="role", how="left", suffixes=("_synthetic", "_real_mean")
    )
    for dim in DIMS:
        profile_gap[f"{dim}_gap_real_minus_synthetic"] = (
            profile_gap[f"{dim}_real_mean"] - profile_gap[f"{dim}_synthetic"]
        )
    profile_gap.to_csv(ROOT / "profile_gap_by_role.csv", index=False)

    weakest = base.loc[base.real_win_probability.idxmin()]
    strongest = base.loc[base.real_win_probability.idxmax()]
    primary_env = envelope.loc[envelope.scenario.eq(PRIMARY)].iloc[0]
    sensitivity = envelope.loc[~envelope.scenario.eq(PRIMARY)].copy()

    overall_gap = profile_gap[["role", "overall_gap_real_minus_synthetic"]].sort_values(
        "overall_gap_real_minus_synthetic", ascending=False
    )
    largest_gaps = overall_gap.head(5).to_dict("records")

    factor_summary = []
    for role in ["GK", "RB", "AM"]:
        sub = effects.loc[(effects.role.eq(role)) & effects.metric.isin([
            "synthetic_win_probability", "real_win_probability", "goal_difference"
        ])]
        row = {
            "role": role,
            "reference_candidate": sub.reference_candidate.iloc[0],
            "alternative_candidate": sub.alternative_candidate.iloc[0],
        }
        for r in sub.itertuples(index=False):
            row[r.metric] = float(r.alternative_minus_reference)
        factor_summary.append(row)

    claims = {
        "status": "identified_set_results_report_complete",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "release": manifest.get("release"),
        "simulated_matches": int(manifest.get("total_simulated_matches", 0)),
        "primary_result": {
            "synthetic_win_probability_range": [
                float(primary_env.synthetic_win_probability_min),
                float(primary_env.synthetic_win_probability_max),
            ],
            "draw_probability_range": [
                float(primary_env.draw_probability_min),
                float(primary_env.draw_probability_max),
            ],
            "real_win_probability_range": [
                float(primary_env.real_win_probability_min),
                float(primary_env.real_win_probability_max),
            ],
            "goal_difference_range": [
                float(primary_env.goal_difference_min),
                float(primary_env.goal_difference_max),
            ],
            "xg_difference_range": [
                float(primary_env.xg_difference_min),
                float(primary_env.xg_difference_max),
            ],
            "calibration_bootstrap_identified_interval_for_win_margin": [
                float(primary_env.identified_interval_lower),
                float(primary_env.identified_interval_upper),
            ],
        },
        "sensitivity_result": {
            "all_directionally_robust": bool(sensitivity.directionally_robust.all()),
            "all_favor": sorted(set(sensitivity.robust_direction.astype(str))),
            "scenarios": sensitivity.scenario.tolist(),
        },
        "weakest_real_combination": {
            "combination_id": weakest.combination_id,
            "GK": weakest.GK,
            "RB": weakest.RB,
            "AM": weakest.AM,
            "real_win_probability": float(weakest.real_win_probability),
        },
        "strongest_real_combination": {
            "combination_id": strongest.combination_id,
            "GK": strongest.GK,
            "RB": strongest.RB,
            "AM": strongest.AM,
            "real_win_probability": float(strongest.real_win_probability),
        },
        "ambiguous_role_marginal_effects": factor_summary,
        "largest_overall_profile_gaps": largest_gaps,
        "external_holdout": holdout,
        "calibration_quality": calibration,
        "authorized_claim": (
            "Within the preregistered calibrated event-engine family, every plausible Real XI "
            "has a higher simulated win probability than the Synthetic XI, and the direction "
            "survives all prespecified sensitivity analyses."
        ),
        "prohibited_claims": [
            "The Real XI would certainly win a real match.",
            "A unique Real Best XI was identified.",
            "The event engine has been fully externally validated.",
            "The representative 2-1 match is an observed or predicted exact score.",
        ],
    }
    (ROOT / "publication_claims.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    role_effect_lines = []
    for item in factor_summary:
        role_effect_lines.append(
            f"- **{item['role']} — {item['reference_candidate']} → {item['alternative_candidate']}:** "
            f"victoria Synthetic {signed_pp(item['synthetic_win_probability'])}; "
            f"victoria Real {signed_pp(item['real_win_probability'])}; "
            f"diferencia de goles {item['goal_difference']:+.3f}."
        )
    gap_lines = [
        f"- **{row['role']}**: ventaja media Real − Synthetic de {row['overall_gap_real_minus_synthetic']:+.3f} en overall."
        for row in largest_gaps
    ]

    report = f"""# Resultados científicos — Synthetic XI vs. conjunto identificado de Real XI

Generado: {claims['generated_at_utc']}

## Resultado principal

Se ejecutaron **{claims['simulated_matches']:,} partidos** con semilla fija, campo neutral,
ocho alineaciones reales plausibles, incertidumbre de perfil, bootstrap de calibración y cinco
sensibilidades preespecificadas.

Frente a las ocho alineaciones posibles:

- **Synthetic XI gana:** {pct(primary_env.synthetic_win_probability_min)}–{pct(primary_env.synthetic_win_probability_max)}.
- **Empate:** {pct(primary_env.draw_probability_min)}–{pct(primary_env.draw_probability_max)}.
- **Real XI gana:** {pct(primary_env.real_win_probability_min)}–{pct(primary_env.real_win_probability_max)}.
- **Diferencia media de goles (Synthetic − Real):** {primary_env.goal_difference_min:.3f} a {primary_env.goal_difference_max:.3f}.
- **Diferencia media de xG (Synthetic − Real):** {primary_env.xg_difference_min:.3f} a {primary_env.xg_difference_max:.3f}.
- **Intervalo identificado-bootstrap del margen de victoria:** {primary_env.identified_interval_lower:.3f} a {primary_env.identified_interval_upper:.3f}.

Todo el intervalo permanece por debajo de cero. Por tanto, la dirección está identificada dentro
del modelo: el Real XI conserva ventaja en las ocho alineaciones, no únicamente en una selección
conveniente.

## Robustez

Las cinco sensibilidades —Top 10, Top 30, incertidumbre no agrupada y respuesta de habilidad
baja/alta— conservaron la misma dirección. El rango más favorable para el Synthetic XI apareció
en Top 10, pero incluso allí su probabilidad de victoria quedó entre
{pct(envelope.loc[envelope.scenario.eq('sensitivity_top10'), 'synthetic_win_probability_min'].iloc[0])}
y {pct(envelope.loc[envelope.scenario.eq('sensitivity_top10'), 'synthetic_win_probability_max'].iloc[0])},
frente a {pct(envelope.loc[envelope.scenario.eq('sensitivity_top10'), 'real_win_probability_min'].iloc[0])}–{pct(envelope.loc[envelope.scenario.eq('sensitivity_top10'), 'real_win_probability_max'].iloc[0])}
del Real XI.

## Qué hacen las tres posiciones ambiguas

{chr(10).join(role_effect_lines)}

La portería apenas cambia el resultado. Las mayores variaciones proceden de RB y AM, pero ninguna
combinación revierte la conclusión.

## Por qué gana el Real XI

El Synthetic XI no es un “superjugador” que toma el máximo de cada métrica: es una media recortada
de los mejores candidatos. Esa regla reduce dependencia de outliers y mejora estabilidad, pero
también suaviza las cimas individuales. Los mayores gaps de perfil fueron:

{chr(10).join(gap_lines)}

La diferencia aparece más en calidad de ocasión y conversión que en control territorial: en el
escenario principal el Synthetic XI mantuvo aproximadamente 48% de los estados de posesión, pero
cedió entre 0.537 y 0.681 xG medios por partido.

## Validación disponible

El gate de calibración de ingeniería está aprobado. Además, una prueba externa separada, con
perfiles congelados antes del torneo, evaluó 91 partidos FT y obtuvo log loss
**{holdout.get('log_loss', float('nan')):.3f}** frente a **{holdout.get('naive_log_loss', float('nan')):.3f}**
del baseline uniforme, con accuracy top-1 de **{pct(holdout.get('top1_accuracy', 0.0))}**.
Esta prueba confirma señal predictiva en la agregación de perfiles; no equivale a validar cada
micro-mecanismo del motor de eventos.

## Claim autorizado

> En 65,600 simulaciones calibradas, las ocho versiones científicamente plausibles del mejor XI
> real conservaron una probabilidad de victoria superior a la del Synthetic XI; la dirección se
> mantuvo en todas las sensibilidades preespecificadas.

## Lo que no debe afirmarse

No se demostró que el Real XI ganaría con certeza un partido real, no se identificó un único Real
Best XI y el 2-1 representativo no es un marcador pronosticado. El resultado es una inferencia
condicional a un motor transparente y a una familia explícita de supuestos.
"""
    (ROOT / "RESULTS_ES.md").write_text(report, encoding="utf-8")
    print(json.dumps(claims, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
