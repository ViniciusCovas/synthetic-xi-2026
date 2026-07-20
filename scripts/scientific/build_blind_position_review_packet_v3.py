#!/usr/bin/env python3
"""Build the definitive ontology-v3 blind-review packet.

The packet is generated only after every role has at least 20 stable primary candidates
from structurally complete line-ups. Reviewers never see automated roles, rankings,
scores, public anchors, previous simulation membership or outcomes.
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    status = load_json(STATUS)
    counts = status.get("eligible_primary_candidates_by_role", {})
    ready = bool(
        status.get("all_roles_have_20_primary_candidates", False)
        and all(int(counts.get(role, 0) or 0) >= 20 for role in ROLES)
    )
    if not ready:
        blocked = {
            "status": "blind_review_packet_blocked",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "minimum 20 stable primary candidates not reached in every role",
            "eligible_primary_candidates_by_role": {role: int(counts.get(role, 0) or 0) for role in ROLES},
            "review_packet_ready": False,
            "next_action": "continue outcome-blind complete-lineup extraction for deficient roles",
        }
        (OUT / "packet_manifest.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return

    if not PRIMARY.exists() or not FRONTIER.exists():
        raise FileNotFoundError("ontology-v3 primary roles or selection frontier is missing")

    primary = pd.read_csv(PRIMARY, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    for frame in (primary, frontier):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    for column in [
        "primary_role_minutes", "primary_role_observations", "classified_role_minutes",
        "primary_role_share",
    ]:
        primary[column] = pd.to_numeric(primary.get(column), errors="coerce").fillna(0.0)
    primary["primary_role_eligible"] = bool_series(primary.get(
        "primary_role_eligible", pd.Series(False, index=primary.index)
    ))
    primary = primary.sort_values(
        ["player_id", "primary_role_minutes", "primary_role_observations"],
        ascending=[True, False, False],
    ).drop_duplicates("player_id")

    high_impact = high_impact_ids()
    primary["high_impact_current_release"] = primary.player_id.isin(high_impact)
    near_threshold = (
        primary.primary_role_minutes.ge(600)
        & primary.primary_role_observations.ge(3)
        & primary.primary_role_share.ge(0.50)
    )
    selected_ids = set(primary.loc[
        primary.primary_role_eligible | primary.high_impact_current_release | near_threshold,
        "player_id",
    ].astype(int))

    frontier = frontier.sort_values("player_id").drop_duplicates("player_id")
    metadata_columns = [
        column for column in [
            "player_id", "player_name", "world_cup_team", "squad_position", "minutes_num",
            "reported_minutes", "identity_rows_before_deduplication",
        ] if column in frontier.columns
    ]
    selected = primary.loc[primary.player_id.isin(selected_ids)].merge(
        frontier[metadata_columns], on="player_id", how="left", suffixes=("_ontology", "")
    )

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

    selected["display_name"] = selected.get("canonical_name", pd.Series(pd.NA, index=selected.index))
    selected["display_name"] = selected.display_name.fillna(selected.get("player_name"))
    selected["annual_minutes"] = pd.to_numeric(
        selected.get("minutes_num", selected.get("reported_minutes")), errors="coerce"
    ).fillna(0.0)
    selected["high_impact_current_release"] = selected.player_id.isin(high_impact)
    selected["eligible_primary_candidate"] = bool_series(selected.primary_role_eligible)
    selected = selected.sort_values("player_id").reset_index(drop=True)

    # Deterministic order is shuffled by a stable hash rather than by role or score.
    selected["blind_order"] = selected.player_id.map(
        lambda value: hashlib.sha256(f"20260720:{int(value)}".encode()).hexdigest()
    )
    selected = selected.sort_values("blind_order").reset_index(drop=True)
    selected["review_id"] = [f"V3-{index:04d}" for index in range(1, len(selected) + 1)]

    packet = pd.DataFrame({
        "review_id": selected.review_id,
        "player_name": selected.display_name.fillna(""),
        "national_team": selected.get("world_cup_team", ""),
        "provider_squad_group": selected.get("squad_position", ""),
        "annual_minutes": selected.annual_minutes.round(0).astype(int),
        "classified_position_minutes": selected.classified_role_minutes.round(0).astype(int),
        "complete_lineup_observations": selected.primary_role_observations.round(0).astype(int),
        "reviewer_primary_role": "",
        "reviewer_secondary_role": "",
        "confidence_1_3": "",
        "evidence_or_rationale": "",
    }).fillna("")

    hidden_columns = [
        column for column in [
            "review_id", "player_id", "display_name", "world_cup_team", "squad_position",
            "annual_minutes", "primary_role", "primary_role_minutes",
            "primary_role_observations", "classified_role_minutes", "primary_role_share",
            "primary_role_eligible", "eligible_primary_candidate",
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
        "status": "blind_position_review_v3_packet_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "source_primary_roles": str(PRIMARY),
        "source_primary_roles_sha256": sha256(PRIMARY),
        "review_cases": int(len(packet)),
        "eligible_primary_candidates": int(answer_key.eligible_primary_candidate.sum()),
        "high_impact_cases": int(answer_key.high_impact_current_release.sum()),
        "public_anchor_cases_hidden_from_reviewers": public_anchor_count,
        "selection_rule": "all eligible primary candidates, all current high-impact players, and near-threshold challengers",
        "blinded_fields": [
            "automated primary role and role distribution", "old ontology roles",
            "scores and rankings", "public anchors", "simulation membership and outcomes",
        ],
        "reviewers_required": 2,
        "allowed_primary_roles": ROLES + ["UNRESOLVED"],
        "review_packet_ready": True,
        "next_action": "two independent football experts complete the forms; then run evaluate_blind_position_review_v3.py",
    }
    (OUT / "packet_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    instructions = """# Revisão cega da ontologia v3

1. Os dois revisores trabalham de forma independente e não discutem casos durante a primeira rodada.
2. Usar os códigos do `POSITION_ONTOLOGY_CODEBOOK_ES.md`.
3. Não abrir answer key, rankings, papéis automáticos ou resultados de simulação.
4. Classificar a função principal realmente desempenhada na janela anual, não a reputação histórica do atleta.
5. É permitido consultar páginas oficiais de clube, liga e federação e escalações públicas.
6. Usar `UNRESOLVED` quando a evidência for insuficiente.
7. Preencher função principal, função secundária opcional, confiança de 1 a 3 e justificativa curta.
8. Não alterar `review_id`, nomes, ordem ou quantidade de linhas.
9. Salvar como `reviewer_a_completed.csv` e `reviewer_b_completed.csv`.
"""
    (OUT / "REVIEW_INSTRUCTIONS_PT.md").write_text(instructions, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
