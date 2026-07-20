#!/usr/bin/env python3
"""Promote independently reviewed roles into the definitive ontology-v3 table.

Promotion is impossible until the preregistered blind-review gate passes. Every reviewer
disagreement must have an explicit adjudication. Final eligibility is recalculated in
the reviewed role rather than inherited from the automated primary role.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3")
REVIEW = ROOT / "blind_review"
EVALUATION = REVIEW / "blind_review_evaluation.json"
CONSENSUS = REVIEW / "blind_review_consensus.csv"
ANSWER_KEY = REVIEW / "answer_key_do_not_share_with_reviewers.csv"
ADJUDICATION = REVIEW / "reviewer_disagreement_adjudication.csv"
ROLE_MINUTES = ROOT / "complete_lineup_player_role_minutes.csv"
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
OUTPUT = ROOT / "promoted_player_roles_uncovered.csv"
STATUS = ROOT / "ontology_v3_status.json"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_role(value: object) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "CBR": "RCB", "CBL": "LCB", "RWB": "RB", "LWB": "LB",
        "CF": "ST", "CAM": "AM", "CDM": "DM",
    }
    return aliases.get(text, text)


def public_compatible(role: str, allowed: object) -> bool:
    permitted = {
        normalize_role(item) for item in str(allowed or "").split("|") if str(item).strip()
    }
    return not permitted or role in permitted


def write_blocked(reason: str, details: dict | None = None) -> None:
    status = {
        "status": "ontology_v3_promotion_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "final_ontology_gate_passed": False,
        "final_team_construction_allowed": False,
        "details": details or {},
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


def main() -> None:
    evaluation = load_json(EVALUATION)
    if not evaluation.get("review_gate_passed", False):
        write_blocked("preregistered blind-review reliability gate has not passed", evaluation)
        return
    required = [CONSENSUS, ANSWER_KEY, ROLE_MINUTES, FRONTIER]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        write_blocked("required promotion inputs are missing", {"missing_files": missing})
        return

    consensus = pd.read_csv(CONSENSUS, low_memory=False)
    key = pd.read_csv(ANSWER_KEY, low_memory=False)
    role_minutes = pd.read_csv(ROLE_MINUTES, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    for frame in (consensus, key, role_minutes, frontier):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    consensus["role_a"] = consensus.role_a.map(normalize_role)
    consensus["role_b"] = consensus.role_b.map(normalize_role)
    consensus["agree"] = consensus.role_a.eq(consensus.role_b)
    consensus["final_role"] = consensus.role_a.where(consensus.agree, "")

    disagreements = consensus.loc[~consensus.agree, ["review_id", "player_id"]].copy()
    if not disagreements.empty:
        if not ADJUDICATION.exists():
            write_blocked(
                "reviewer disagreements require explicit adjudication",
                {"unadjudicated_cases": int(len(disagreements)), "required_file": str(ADJUDICATION)},
            )
            return
        adjudication = pd.read_csv(ADJUDICATION, low_memory=False)
        required_columns = {"review_id", "adjudicated_role", "adjudicator", "rationale"}
        if not required_columns.issubset(adjudication.columns):
            raise RuntimeError(f"adjudication file lacks columns: {sorted(required_columns - set(adjudication.columns))}")
        adjudication["adjudicated_role"] = adjudication.adjudicated_role.map(normalize_role)
        invalid = sorted(set(adjudication.adjudicated_role) - set(ROLES))
        if invalid:
            raise RuntimeError(f"invalid adjudicated roles: {invalid}")
        adjudication = adjudication.drop_duplicates("review_id", keep="last")
        disagreement_ids = set(disagreements.review_id)
        adjudicated_ids = set(adjudication.review_id)
        missing_ids = sorted(disagreement_ids - adjudicated_ids)
        if missing_ids:
            write_blocked("some reviewer disagreements remain unadjudicated", {"review_ids": missing_ids})
            return
        consensus = consensus.merge(
            adjudication[["review_id", "adjudicated_role", "adjudicator", "rationale"]],
            on="review_id", how="left",
        )
        consensus["final_role"] = consensus.final_role.where(
            consensus.agree, consensus.adjudicated_role
        )
    else:
        consensus["adjudicator"] = "not_required"
        consensus["rationale"] = "reviewers_agreed"

    consensus["final_role"] = consensus.final_role.map(normalize_role)
    invalid_final = sorted(set(consensus.final_role) - set(ROLES))
    if invalid_final:
        raise RuntimeError(f"invalid promoted final roles: {invalid_final}")

    key_columns = [
        column for column in [
            "review_id", "player_id", "display_name", "world_cup_team", "squad_position",
            "annual_minutes", "eligible_primary_candidate", "high_impact_current_release",
            "allowed_roles", "public_anchor_available", "source_type", "source_url",
            "public_position", "evidence_note",
        ] if column in key.columns
    ]
    promoted = consensus.merge(
        key[key_columns].drop_duplicates("review_id"),
        on=["review_id", "player_id"], how="left", validate="one_to_one",
    )

    role_minutes["role"] = role_minutes.role.map(normalize_role)
    for column in ["role_minutes", "role_observations", "role_share"]:
        role_minutes[column] = pd.to_numeric(role_minutes.get(column), errors="coerce").fillna(0.0)
    role_specific = role_minutes.rename(columns={
        "role": "final_role",
        "role_minutes": "role_minutes_final",
        "role_observations": "role_observations_final",
        "role_share": "role_stability_final",
    })
    promoted = promoted.merge(
        role_specific[[
            "player_id", "final_role", "role_minutes_final",
            "role_observations_final", "role_stability_final",
        ]],
        on=["player_id", "final_role"], how="left",
    )
    for column in ["role_minutes_final", "role_observations_final", "role_stability_final"]:
        promoted[column] = pd.to_numeric(promoted.get(column), errors="coerce").fillna(0.0)

    frontier = frontier.sort_values("player_id").drop_duplicates("player_id")
    metric_columns = [
        column for column in [
            "player_id", "player_name", "world_cup_team", "squad_position", "minutes_num",
            "reported_minutes", "overall", "uncertainty", "conservative_score",
            "build_up", "progression", "creation", "finishing", "defending", "duels",
            "retention", "goalkeeping", "identity_rows_before_deduplication",
        ] if column in frontier.columns
    ]
    promoted = promoted.merge(
        frontier[metric_columns], on="player_id", how="left", suffixes=("_review", "")
    )
    total_column = "minutes_num" if "minutes_num" in promoted else "reported_minutes"
    promoted["exact_window_total_minutes"] = pd.to_numeric(
        promoted.get(total_column), errors="coerce"
    ).fillna(0.0)
    promoted["public_anchor_available"] = (
        promoted.get("public_anchor_available", False)
        .astype(str).str.lower().isin({"true", "1", "yes", "y"})
    )
    promoted["final_role_publicly_compatible"] = promoted.apply(
        lambda row: public_compatible(row.final_role, row.get("allowed_roles")), axis=1
    )
    promoted["human_review_resolved"] = True
    promoted["final_role_eligible_before_coverage"] = (
        promoted.final_role.isin(ROLES)
        & promoted.exact_window_total_minutes.ge(1800)
        & promoted.role_minutes_final.ge(900)
        & promoted.role_observations_final.ge(3)
        & promoted.role_stability_final.ge(0.60)
        & (~promoted.public_anchor_available | promoted.final_role_publicly_compatible)
    )
    promoted["overall_final"] = pd.to_numeric(promoted.get("overall"), errors="coerce")
    promoted["conservative_score_final"] = pd.to_numeric(
        promoted.get("conservative_score"), errors="coerce"
    )
    promoted["eligibility_exclusion_reason"] = ""
    promoted.loc[promoted.exact_window_total_minutes.lt(1800), "eligibility_exclusion_reason"] += "total_minutes_lt_1800;"
    promoted.loc[promoted.role_minutes_final.lt(900), "eligibility_exclusion_reason"] += "reviewed_role_minutes_lt_900;"
    promoted.loc[promoted.role_observations_final.lt(3), "eligibility_exclusion_reason"] += "reviewed_role_observations_lt_3;"
    promoted.loc[promoted.role_stability_final.lt(0.60), "eligibility_exclusion_reason"] += "reviewed_role_share_lt_0_60;"
    promoted.loc[
        promoted.public_anchor_available & ~promoted.final_role_publicly_compatible,
        "eligibility_exclusion_reason",
    ] += "public_anchor_conflict;"
    promoted = promoted.sort_values(["final_role", "player_id"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    promoted.to_csv(OUTPUT, index=False)

    eligible = promoted.loc[promoted.final_role_eligible_before_coverage].copy()
    counts = (
        eligible.groupby("final_role").player_id.nunique()
        .reindex(ROLES, fill_value=0).astype(int).to_dict()
    )
    public_conflicts = int((
        promoted.public_anchor_available & ~promoted.final_role_publicly_compatible
    ).sum())
    high_impact_unresolved = int((
        promoted.get("high_impact_current_release", False).astype(str).str.lower().isin({"true", "1", "yes", "y"})
        & ~promoted.final_role_eligible_before_coverage
    ).sum())
    gate = bool(
        all(count >= 20 for count in counts.values())
        and public_conflicts == 0
        and high_impact_unresolved == 0
    )
    status = {
        "status": "ontology_v3_promotion_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_gate_passed": True,
        "all_reviewer_disagreements_adjudicated": True,
        "promoted_reviewed_players": int(len(promoted)),
        "final_eligible_candidates_before_coverage": int(len(eligible)),
        "final_eligible_candidates_by_role": counts,
        "minimum_20_candidates_each_role": all(count >= 20 for count in counts.values()),
        "public_anchor_conflicts": public_conflicts,
        "high_impact_ineligible_or_unresolved": high_impact_unresolved,
        "final_ontology_gate_passed": gate,
        "final_team_construction_allowed": False,
        "output": str(OUTPUT),
        "next_action": (
            "evaluate exact-window data coverage for every promoted candidate"
            if gate else "resolve ontology population or public-anchor blockers before coverage evaluation"
        ),
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
