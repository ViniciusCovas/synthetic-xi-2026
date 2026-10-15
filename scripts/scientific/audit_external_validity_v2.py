#!/usr/bin/env python3
"""Audit whether a frozen XI can support a global-best-XI claim."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CANDIDATES = Path("data/audits/position_ontology_v3/final_candidate_roles.csv")
REAL_XI = Path("data/definitive_experiment_v1/real_xi.csv")
OUT = Path("data/audits/external_validity_v2")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
COMPETITION_FIELDS = [
    "club_name",
    "competition_id",
    "competition_name",
    "competition_strength",
    "opponent_strength_adjusted",
]
ROLE_PRIMARY = {
    "GK": ["goalkeeping"],
    "RB": ["defending", "progression", "creation"],
    "RCB": ["defending", "duels", "build_up"],
    "LCB": ["defending", "duels", "build_up"],
    "LB": ["defending", "progression", "creation"],
    "DM": ["defending", "duels", "build_up", "retention"],
    "CM": ["build_up", "progression", "creation", "retention"],
    "AM": ["creation", "progression", "finishing"],
    "RW": ["progression", "creation", "finishing"],
    "LW": ["progression", "creation", "finishing"],
    "ST": ["finishing", "creation", "duels"],
}


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not CANDIDATES.exists() or not REAL_XI.exists():
        raise RuntimeError("candidate table and frozen Real XI are required")

    candidates = pd.read_csv(CANDIDATES, low_memory=False)
    selected = pd.read_csv(REAL_XI, low_memory=False)
    eligible = candidates.loc[truth(candidates["final_candidate_eligible"])].copy()
    eligible["final_role"] = eligible["final_role"].astype(str).str.upper()

    missing_competition_fields = [field for field in COMPETITION_FIELDS if field not in candidates.columns]
    competition_context_passed = not missing_competition_fields

    role_diagnostics = {}
    role_variance_passed = True
    for role in ROLES:
        pool = eligible.loc[eligible.final_role.eq(role)].copy()
        metric_rows = {}
        for metric in ROLE_PRIMARY[role]:
            values = pd.to_numeric(pool.get(metric), errors="coerce").dropna()
            metric_rows[metric] = {
                "eligible_values": int(len(values)),
                "unique_values": int(values.nunique()),
                "standard_deviation": float(values.std(ddof=0)) if len(values) else None,
                "minimum": float(values.min()) if len(values) else None,
                "maximum": float(values.max()) if len(values) else None,
            }
        primary_discriminates = all(
            row["unique_values"] >= 5 and (row["standard_deviation"] or 0.0) >= 0.01
            for row in metric_rows.values()
        )
        role_variance_passed = role_variance_passed and primary_discriminates
        role_diagnostics[role] = {
            "eligible_candidates": int(pool.player_id.nunique()),
            "primary_metrics": metric_rows,
            "primary_metrics_discriminate": primary_discriminates,
        }

    gk = role_diagnostics["GK"]["primary_metrics"]["goalkeeping"]
    goalkeeper_model_passed = bool(
        gk["eligible_values"] >= 20
        and gk["unique_values"] >= 5
        and (gk["standard_deviation"] or 0.0) >= 0.01
    )

    selected_fields = set(selected.columns)
    selected_traceability_fields = {
        "slot", "player_id", "player_name", "minutes", "adjusted_role_score",
        "conservative_score", "uncertainty",
    }
    selected_traceability_passed = selected_traceability_fields.issubset(selected_fields)

    publication_gate_passed = bool(
        competition_context_passed
        and goalkeeper_model_passed
        and role_variance_passed
        and selected_traceability_passed
    )

    status = {
        "status": "global_best_xi_external_validity_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_under_review": "best global Real XI for the frozen 2025-2026 window",
        "competition_context_passed": competition_context_passed,
        "missing_competition_context_fields": missing_competition_fields,
        "goalkeeper_model_passed": goalkeeper_model_passed,
        "all_role_primary_metrics_discriminate": role_variance_passed,
        "selected_player_traceability_passed": selected_traceability_passed,
        "role_diagnostics": role_diagnostics,
        "global_best_xi_publication_gate_passed": publication_gate_passed,
        "existing_100000_match_run_classification": (
            "publication_ready" if publication_gate_passed
            else "diagnostic_invalidated_for_global_best_xi_claim"
        ),
        "required_repairs": [] if publication_gate_passed else [
            "build a discriminative goalkeeper-specific model",
            "add explicit competition and opponent-strength adjustment",
            "rebuild role rankings and frozen teams",
            "publish a selected-player plausibility report versus leading alternatives",
            "rerun independent validation and the 100000-match experiment under new hashes",
        ],
    }
    (OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# External validity audit v2", "",
        f"Publication gate: **{publication_gate_passed}**", "",
        f"Competition context present: **{competition_context_passed}**", 
        f"Goalkeeper model discriminates: **{goalkeeper_model_passed}**", "",
        "## Goalkeeper diagnostic", "",
        f"- eligible values: {gk['eligible_values']}",
        f"- unique goalkeeping values: {gk['unique_values']}",
        f"- standard deviation: {gk['standard_deviation']}", "",
        "## Missing competition fields", "",
    ]
    lines.extend([f"- {field}" for field in missing_competition_fields] or ["- none"])
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
