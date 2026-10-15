#!/usr/bin/env python3
"""Build the definitive ontology-v3.1 blind-review packet.

The packet uses broad positional-family experience only as a pre-review support gate.
Reviewers never see automated exact roles, role families, rankings, scores, public
anchors, previous simulation membership or outcomes. Exact slots are established by
two independent reviewers, avoiding circular validation of the automatic ontology.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3")
STATUS = ROOT / "lineup_completeness_status.json"
PRIMARY = ROOT / "complete_lineup_primary_roles.csv"
ROLE_MINUTES = ROOT / "complete_lineup_player_role_minutes.csv"
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
V2_AUDIT = Path("data/audits/position_ontology_v2/audited_player_roles.csv")
REAL = Path("data/simulations/identified_set_v1/real_identified_set_membership.csv")
SYNTHETIC = Path("data/simulations/identified_set_v1/synthetic_avatar_membership.csv")
OUT = ROOT / "blind_review"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
ROLE_FAMILY = {
    "GK": "GK",
    "RB": "FB", "LB": "FB",
    "RCB": "CB", "LCB": "CB",
    "DM": "MID", "CM": "MID", "AM": "MID",
    "RW": "WING", "LW": "WING",
    "ST": "ST",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def high_impact_ids() -> set[int]:
    ids: set[int] = set()
    for path in (REAL, SYNTHETIC):
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        values = pd.to_numeric(frame.get("player_id"), errors="coerce").dropna().astype(int)
        ids.update(values)
    return ids


def family_evidence(role_minutes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    role_minutes = role_minutes.copy()
    role_minutes["role"] = role_minutes.role.astype(str).str.strip().str.upper()
    role_minutes["family"] = role_minutes.role.map(ROLE_FAMILY)
    role_minutes = role_minutes.dropna(subset=["family"]).copy()
    role_minutes["role_minutes"] = pd.to_numeric(
        role_minutes.get("role_minutes"), errors="coerce"
    ).fillna(0.0)
    role_minutes["role_observations"] = pd.to_numeric(
        role_minutes.get("role_observations"), errors="coerce"
    ).fillna(0.0)
    family = role_minutes.groupby(["player_id", "family"], as_index=False).agg(
        family_minutes=("role_minutes", "sum"),
        family_observations=("role_observations", "sum"),
    )
    totals = family.groupby("player_id", as_index=False).agg(
        classified_family_minutes=("family_minutes", "sum"),
        classified_family_observations=("family_observations", "sum"),
    )
    family = family.merge(totals, on="player_id", how="left")
    family["family_share"] = (
        family.family_minutes / family.classified_family_minutes.replace(0, pd.NA)
    )
    family["family_support_eligible"] = (
        family.family_minutes.ge(900)
        & family.family_observations.ge(3)
    )
    ranked = family.sort_values(
        ["player_id", "family_minutes", "family_observations", "family"],
        ascending=[True, False, False, True],
    ).drop_duplicates("player_id")
    ranked = ranked.rename(columns={
        "family": "dominant_family",
        "family_minutes": "dominant_family_minutes",
        "family_observations": "dominant_family_observations",
        "family_share": "dominant_family_share",
    })
    return family, ranked


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not PRIMARY.exists() or not ROLE_MINUTES.exists() or not FRONTIER.exists():
        raise FileNotFoundError("ontology-v3 role evidence or selection frontier is missing")

    primary = pd.read_csv(PRIMARY, low_memory=False)
    role_minutes = pd.read_csv(ROLE_MINUTES, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    for frame in (primary, role_minutes, frontier):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    family, dominant = family_evidence(role_minutes)
    primary = primary.sort_values("player_id").drop_duplicates("player_id")
    frontier = frontier.sort_values("player_id").drop_duplicates("player_id")
    minute_column = next(
        (name for name in ["minutes_num", "reported_minutes", "minutes"] if name in frontier),
        None,
    )
    if minute_column is None:
        raise RuntimeError("selection frontier lacks exact-window annual minutes")
    frontier["annual_minutes"] = pd.to_numeric(frontier[minute_column], errors="coerce").fillna(0.0)

    metadata_columns = [
        column for column in [
            "player_id", "player_name", "world_cup_team", "squad_position", "annual_minutes",
            "identity_rows_before_deduplication",
        ] if column in frontier.columns
    ]
    candidates = frontier[metadata_columns].merge(dominant, on="player_id", how="left")
    primary_columns = [
        column for column in [
            "player_id", "primary_role", "primary_role_minutes", "primary_role_observations",
            "classified_role_minutes", "primary_role_share",
        ] if column in primary.columns
    ]
    candidates = candidates.merge(primary[primary_columns], on="player_id", how="left")
    for column in [
        "dominant_family_minutes", "dominant_family_observations", "classified_family_minutes",
        "classified_family_observations", "dominant_family_share", "primary_role_minutes",
        "primary_role_observations", "classified_role_minutes", "primary_role_share",
    ]:
        if column not in candidates:
            candidates[column] = 0.0
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce").fillna(0.0)

    candidates["family_review_support"] = (
        candidates.annual_minutes.ge(1800)
        & candidates.dominant_family_minutes.ge(900)
        & candidates.dominant_family_observations.ge(3)
    )
    candidates["near_family_threshold"] = (
        candidates.annual_minutes.ge(1800)
        & candidates.dominant_family_minutes.ge(600)
        & candidates.dominant_family_minutes.lt(900)
        & candidates.dominant_family_observations.ge(3)
    )
    high_impact = high_impact_ids()
    candidates["high_impact_current_release"] = candidates.player_id.isin(high_impact)

    family_supported = family.loc[
        family.family_support_eligible
    ].merge(
        frontier[["player_id", "annual_minutes"]], on="player_id", how="left"
    )
    family_supported = family_supported.loc[family_supported.annual_minutes.ge(1800)]
    family_counts = family_supported.groupby("family").player_id.nunique().to_dict()
    slot_support_counts = {
        role: int(family_counts.get(ROLE_FAMILY[role], 0) or 0) for role in ROLES
    }
    ready = all(count >= 20 for count in slot_support_counts.values())
    if not ready:
        blocked = {
            "status": "blind_review_packet_blocked",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "minimum 20 annual-minute and family-experience support candidates not reached for every slot",
            "family_support_candidates": {
                family_name: int(family_counts.get(family_name, 0) or 0)
                for family_name in sorted(set(ROLE_FAMILY.values()))
            },
            "slot_support_candidates": slot_support_counts,
            "review_packet_ready": False,
            "next_action": "extract complete lineups only for deficient positional families",
        }
        (OUT / "packet_manifest.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return

    selected = candidates.loc[
        candidates.family_review_support
        | candidates.near_family_threshold
        | candidates.high_impact_current_release
    ].copy()

    if V2_AUDIT.exists():
        anchors = pd.read_csv(V2_AUDIT, low_memory=False)
        anchors["player_id"] = pd.to_numeric(anchors.get("player_id"), errors="coerce")
        anchors = anchors.dropna(subset=["player_id"]).copy()
        anchors["player_id"] = anchors.player_id.astype(int)
        anchor_columns = [
            column for column in [
                "player_id", "canonical_name", "allowed_roles", "preferred_role",
                "public_position", "source_type", "source_url", "evidence_note",
                "public_anchor_available", "audited_role", "resolved_role",
            ] if column in anchors.columns
        ]
        selected = selected.merge(
            anchors.sort_values("player_id").drop_duplicates("player_id")[anchor_columns],
            on="player_id", how="left",
        )

    selected["display_name"] = selected.get(
        "canonical_name", pd.Series(pd.NA, index=selected.index)
    ).fillna(selected.get("player_name"))
    selected = selected.sort_values("player_id").reset_index(drop=True)
    selected["blind_order"] = selected.player_id.map(
        lambda value: hashlib.sha256(f"20260720:v3.1:{int(value)}".encode()).hexdigest()
    )
    selected = selected.sort_values("blind_order").reset_index(drop=True)
    selected["review_id"] = [f"V31-{index:04d}" for index in range(1, len(selected) + 1)]

    packet = pd.DataFrame({
        "review_id": selected.review_id,
        "player_name": selected.display_name.fillna(""),
        "national_team": selected.get("world_cup_team", ""),
        "provider_squad_group": selected.get("squad_position", ""),
        "annual_minutes": selected.annual_minutes.round(0).astype(int),
        "classified_position_minutes": selected.classified_family_minutes.round(0).astype(int),
        "complete_lineup_observations": selected.classified_family_observations.round(0).astype(int),
        "reviewer_primary_role": "",
        "reviewer_secondary_role": "",
        "confidence_1_3": "",
        "evidence_or_rationale": "",
    }).fillna("")

    family_distribution = family.groupby("player_id").apply(
        lambda block: " | ".join(
            f"{row.family}:{row.family_minutes:.0f}m/{int(row.family_observations)}"
            for row in block.sort_values(
                ["family_minutes", "family_observations", "family"],
                ascending=[False, False, True],
            ).itertuples(index=False)
        ),
        include_groups=False,
    ).rename("family_distribution").reset_index()
    selected = selected.merge(family_distribution, on="player_id", how="left")
    hidden_columns = [
        column for column in [
            "review_id", "player_id", "display_name", "world_cup_team", "squad_position",
            "annual_minutes", "dominant_family", "dominant_family_minutes",
            "dominant_family_observations", "dominant_family_share", "family_distribution",
            "family_review_support", "near_family_threshold", "primary_role",
            "primary_role_minutes", "primary_role_observations", "primary_role_share",
            "high_impact_current_release", "canonical_name", "allowed_roles",
            "preferred_role", "public_position", "source_type", "source_url",
            "evidence_note", "public_anchor_available", "audited_role", "resolved_role",
        ] if column in selected.columns
    ]
    answer_key = selected[hidden_columns].copy()

    packet.to_csv(OUT / "reviewer_a_form.csv", index=False)
    packet.to_csv(OUT / "reviewer_b_form.csv", index=False)
    answer_key.to_csv(OUT / "answer_key_do_not_share_with_reviewers.csv", index=False)

    public_anchor_count = 0
    if "public_anchor_available" in answer_key:
        public_anchor_count = int(bool_series(answer_key.public_anchor_available).sum())
    manifest = {
        "status": "blind_position_review_v3_1_packet_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "protocol": "non-circular family-support gate followed by independent exact-slot review",
        "source_role_minutes": str(ROLE_MINUTES),
        "source_role_minutes_sha256": sha256(ROLE_MINUTES),
        "review_cases": int(len(packet)),
        "family_supported_cases": int(selected.family_review_support.sum()),
        "near_family_threshold_cases": int(selected.near_family_threshold.sum()),
        "high_impact_cases": int(selected.high_impact_current_release.sum()),
        "family_support_candidates": {
            family_name: int(family_counts.get(family_name, 0) or 0)
            for family_name in sorted(set(ROLE_FAMILY.values()))
        },
        "slot_support_candidates": slot_support_counts,
        "public_anchor_cases_hidden_from_reviewers": public_anchor_count,
        "selection_rule": (
            ">=1800 annual minutes and >=900 minutes/3 observations in one positional family; "
            "plus preregistered high-impact and 600-899-minute near-threshold challengers"
        ),
        "blinded_fields": [
            "automatic exact roles and role families", "scores and rankings",
            "public anchors", "simulation membership and outcomes",
        ],
        "reviewers_required": 2,
        "allowed_primary_roles": ROLES + ["UNRESOLVED"],
        "secondary_role_policy": "optional; at most one secondary slot",
        "review_packet_ready": True,
        "next_action": "two independent football experts complete the forms; then run evaluate_blind_position_review_v3.py",
    }
    (OUT / "packet_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    instructions = """# Revisão cega da ontologia v3.1

1. Os dois revisores trabalham de forma independente e não discutem casos durante a primeira rodada.
2. Usar os códigos do `POSITION_ONTOLOGY_CODEBOOK_ES.md`.
3. Não abrir answer key, rankings, papéis automáticos, famílias posicionais ou resultados de simulação.
4. Classificar a função principal realmente desempenhada na janela anual, não a reputação histórica do atleta.
5. A função secundária é opcional e deve ser usada somente quando o atleta demonstrou experiência substancial real nessa função.
6. É permitido consultar páginas oficiais de clube, liga e federação, escalações públicas e fontes jornalísticas confiáveis.
7. Usar `UNRESOLVED` quando a evidência for insuficiente.
8. Preencher função principal, no máximo uma função secundária, confiança de 1 a 3 e justificativa curta.
9. Não alterar `review_id`, nomes, ordem ou quantidade de linhas.
10. Salvar como `reviewer_a_completed.csv` e `reviewer_b_completed.csv`.
"""
    (OUT / "REVIEW_INSTRUCTIONS_PT.md").write_text(instructions, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
