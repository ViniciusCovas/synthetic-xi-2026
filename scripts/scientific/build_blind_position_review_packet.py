#!/usr/bin/env python3
"""Build a deterministic blind-review packet for the audited position ontology.

The public reviewer sheets omit rankings, scores, old roles, automated roles, public anchors,
and simulation results. The hidden answer key remains in the repository for later agreement
and plausibility analysis. No network or provider API calls are made.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260720
AUDIT = Path("data/audits/position_ontology_v2")
SOURCE = AUDIT / "audited_player_roles.csv"
OUT = AUDIT / "blind_review"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
ADDITIONAL_PER_ROLE = 10


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def sample_packet(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    for column in [
        "high_impact_current_release",
        "public_anchor_available",
        "public_conflict_current",
        "public_conflict_formation",
        "formation_evidence_stable",
    ]:
        frame[column] = as_bool(frame.get(column, pd.Series(False, index=frame.index)))

    frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
    frame = frame.dropna(subset=["player_id"]).copy()
    frame["player_id"] = frame["player_id"].astype(int)
    frame = frame.sort_values(
        ["player_id", "formation_precise_minutes", "role_observations"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id")

    mandatory = frame.loc[frame["high_impact_current_release"]].copy()
    remaining = frame.loc[~frame["player_id"].isin(mandatory["player_id"])].copy()

    rng = np.random.default_rng(SEED)
    extra_parts: list[pd.DataFrame] = []
    for role in ROLES:
        block = remaining.loc[remaining["formation_primary_role"].astype(str).eq(role)].copy()
        if block.empty:
            continue
        take = min(ADDITIONAL_PER_ROLE, len(block))
        indexes = rng.choice(block.index.to_numpy(), size=take, replace=False)
        extra_parts.append(block.loc[indexes])

    unresolved = remaining.loc[
        remaining["formation_primary_role"].isna()
        | remaining["formation_primary_role"].astype(str).isin({"", "UNRESOLVED", "CB"})
    ].copy()
    if not unresolved.empty:
        take = min(20, len(unresolved))
        indexes = rng.choice(unresolved.index.to_numpy(), size=take, replace=False)
        extra_parts.append(unresolved.loc[indexes])

    extra = pd.concat(extra_parts, ignore_index=False) if extra_parts else remaining.iloc[0:0]
    selected = pd.concat([mandatory, extra], ignore_index=True).drop_duplicates("player_id")
    selected = selected.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    selected["review_id"] = [f"PR-{index:04d}" for index in range(1, len(selected) + 1)]

    packet = pd.DataFrame(
        {
            "review_id": selected["review_id"],
            "player_name": selected["canonical_name"].where(
                selected["canonical_name"].notna(), selected["player_name"]
            ),
            "national_team": selected.get("world_cup_team", ""),
            "provider_squad_group": selected.get("squad_position", ""),
            "precise_position_minutes": pd.to_numeric(
                selected.get("formation_precise_minutes"), errors="coerce"
            ).fillna(0).round(0).astype(int),
            "position_observations": pd.to_numeric(
                selected.get("formation_role_observations"), errors="coerce"
            ).fillna(0).round(0).astype(int),
            "reviewer_primary_role": "",
            "reviewer_secondary_role": "",
            "confidence_1_3": "",
            "evidence_or_rationale": "",
        }
    )
    packet = packet.fillna("")

    hidden_columns = [
        "review_id",
        "player_id",
        "player_name",
        "canonical_name",
        "world_cup_team",
        "squad_position",
        "resolved_role",
        "role_stability",
        "role_observations",
        "role_distribution",
        "formation_primary_role",
        "formation_primary_role_raw",
        "formation_role_stability_minutes",
        "formation_precise_minutes",
        "formation_role_observations",
        "formation_role_distribution",
        "allowed_roles",
        "preferred_role",
        "public_position",
        "source_type",
        "source_url",
        "evidence_note",
        "high_impact_current_release",
        "public_anchor_available",
        "public_conflict_current",
        "public_conflict_formation",
        "audited_role",
        "audited_role_source",
        "audited_role_eligible",
        "conservative_score_audited",
        "audited_role_rank",
    ]
    hidden_columns = [column for column in hidden_columns if column in selected.columns]
    answer_key = selected[hidden_columns].copy()
    return packet, answer_key


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing ontology audit source: {SOURCE}")
    OUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(SOURCE, low_memory=False)
    packet, answer_key = sample_packet(frame)

    packet.to_csv(OUT / "reviewer_a_form.csv", index=False)
    packet.to_csv(OUT / "reviewer_b_form.csv", index=False)
    answer_key.to_csv(OUT / "answer_key_do_not_share_with_reviewers.csv", index=False)

    manifest = {
        "status": "blind_position_review_packet_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "network_calls": 0,
        "provider_api_calls": 0,
        "source": str(SOURCE),
        "source_sha256": sha256(SOURCE),
        "mandatory_rule": "all players used by the current candidate release",
        "additional_sampling": f"up to {ADDITIONAL_PER_ROLE} per formation-derived role plus up to 20 unresolved cases",
        "review_cases": int(len(packet)),
        "high_impact_cases": int(as_bool(answer_key["high_impact_current_release"]).sum()),
        "public_anchor_cases_hidden_from_reviewers": int(
            as_bool(answer_key["public_anchor_available"]).sum()
        ),
        "blinded_fields": [
            "current role",
            "formation-derived role",
            "audited role",
            "scores and rankings",
            "public sources and allowed roles",
            "simulation membership and outcomes",
        ],
        "reviewers_required": 2,
        "allowed_primary_roles": ROLES + ["UNRESOLVED"],
        "next_step": "two independent reviewers complete the two forms; then run evaluate_blind_position_review.py",
    }
    (OUT / "packet_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    instructions = """# Instrucciones de revisión ciega\n\n1. Cada revisor trabaja de forma independiente.\n2. Consultar `POSITION_ONTOLOGY_CODEBOOK_ES.md`.\n3. No abrir el answer key, rankings, simulaciones ni auditorías automáticas.\n4. Completar únicamente las cuatro columnas vacías del formulario asignado.\n5. Usar solo los códigos permitidos y `UNRESOLVED` cuando la evidencia sea insuficiente.\n6. Guardar como `reviewer_a_completed.csv` o `reviewer_b_completed.csv`.\n7. No modificar `review_id` ni el orden de las filas.\n"""
    (OUT / "REVIEW_INSTRUCTIONS_ES.md").write_text(instructions, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
