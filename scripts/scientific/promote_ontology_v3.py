#!/usr/bin/env python3
"""Promote reviewed ontology-v3.1 candidate-role pairs.

Exact slots come from independent reviewers. Automatic complete-lineup evidence is used
only to verify at least 900 minutes and three observations in the corresponding broad
positional family. This separation avoids circular validation of the exact-role decoder.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3")
REVIEW = ROOT / "blind_review"
EVALUATION = REVIEW / "blind_review_evaluation.json"
CONSENSUS_PAIRS = REVIEW / "blind_review_consensus_candidate_roles.csv"
CONSENSUS = REVIEW / "blind_review_consensus.csv"
ANSWER_KEY = REVIEW / "answer_key_do_not_share_with_reviewers.csv"
ADJUDICATION = REVIEW / "reviewer_disagreement_adjudication.csv"
ROLE_MINUTES = ROOT / "complete_lineup_player_role_minutes.csv"
FRONTIER = Path("data/model_readiness/selection_frontier_all_candidates.csv")
OUTPUT = ROOT / "promoted_candidate_roles_uncovered.csv"
STATUS = ROOT / "ontology_v3_status.json"
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


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def normalize_role(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().upper()
    aliases = {
        "CBR": "RCB", "CBL": "LCB", "RWB": "RB", "LWB": "LB",
        "CF": "ST", "CAM": "AM", "CDM": "DM", "NONE": "", "N/A": "",
    }
    return aliases.get(text, text)


def public_compatible(role: str, allowed: object) -> bool:
    permitted = {
        normalize_role(item) for item in str(allowed or "").split("|") if str(item).strip()
    }
    return not permitted or role in permitted


def write_blocked(reason: str, details: dict | None = None) -> None:
    status = {
        "status": "ontology_v3_1_promotion_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "final_ontology_gate_passed": False,
        "final_team_construction_allowed": False,
        "details": details or {},
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


def family_evidence(role_minutes: pd.DataFrame) -> pd.DataFrame:
    role_minutes = role_minutes.copy()
    role_minutes["role"] = role_minutes.role.map(normalize_role)
    role_minutes["family"] = role_minutes.role.map(ROLE_FAMILY)
    role_minutes = role_minutes.dropna(subset=["family"]).copy()
    role_minutes["role_minutes"] = pd.to_numeric(
        role_minutes.get("role_minutes"), errors="coerce"
    ).fillna(0.0)
    role_minutes["role_observations"] = pd.to_numeric(
        role_minutes.get("role_observations"), errors="coerce"
    ).fillna(0.0)
    exact = role_minutes.rename(columns={
        "role": "final_role",
        "role_minutes": "exact_role_minutes",
        "role_observations": "exact_role_observations",
        "role_share": "exact_role_share",
    })
    family = role_minutes.groupby(["player_id", "family"], as_index=False).agg(
        family_minutes=("role_minutes", "sum"),
        family_observations=("role_observations", "sum"),
    )
    totals = family.groupby("player_id").family_minutes.transform("sum")
    family["family_share"] = family.family_minutes / totals.replace(0, pd.NA)
    return exact[[
        "player_id", "final_role", "exact_role_minutes", "exact_role_observations",
        "exact_role_share",
    ]].merge(
        family,
        left_on=["player_id", exact["final_role"].map(ROLE_FAMILY)],
        right_on=["player_id", "family"],
        how="left",
    )


def main() -> None:
    evaluation = load_json(EVALUATION)
    if not evaluation.get("review_gate_passed", False):
        write_blocked("preregistered blind-review reliability gate has not passed", evaluation)
        return
    required = [CONSENSUS_PAIRS, CONSENSUS, ANSWER_KEY, ROLE_MINUTES, FRONTIER]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        write_blocked("required promotion inputs are missing", {"missing_files": missing})
        return

    pairs = pd.read_csv(CONSENSUS_PAIRS, low_memory=False)
    consensus = pd.read_csv(CONSENSUS, low_memory=False)
    key = pd.read_csv(ANSWER_KEY, low_memory=False)
    role_minutes = pd.read_csv(ROLE_MINUTES, low_memory=False)
    frontier = pd.read_csv(FRONTIER, low_memory=False)
    for frame in (pairs, consensus, key, role_minutes, frontier):
        frame["player_id"] = pd.to_numeric(frame.get("player_id"), errors="coerce")
        frame.dropna(subset=["player_id"], inplace=True)
        frame["player_id"] = frame.player_id.astype(int)

    pairs["role"] = pairs.role.map(normalize_role)
    pairs = pairs.loc[pairs.role.isin(ROLES)].rename(columns={"role": "final_role"})
    pairs["assignment_source"] = "independent_reviewer_intersection"

    consensus["high_impact"] = as_bool(consensus.get(
        "high_impact", pd.Series(False, index=consensus.index)
    ))
    consensus["primary_agree"] = as_bool(consensus.get(
        "primary_agree", pd.Series(False, index=consensus.index)
    ))
    unresolved_high = consensus.loc[consensus.high_impact & ~consensus.primary_agree].copy()
    if not unresolved_high.empty:
        if not ADJUDICATION.exists():
            write_blocked(
                "high-impact primary-role disagreements require adjudication",
                {
                    "unadjudicated_high_impact_cases": int(len(unresolved_high)),
                    "required_file": str(ADJUDICATION),
                    "required_columns": [
                        "review_id", "adjudicated_primary_role", "adjudicated_secondary_role",
                        "adjudicator", "rationale",
                    ],
                },
            )
            return
        adjudication = pd.read_csv(ADJUDICATION, low_memory=False)
        required_columns = {
            "review_id", "adjudicated_primary_role", "adjudicated_secondary_role",
            "adjudicator", "rationale",
        }
        if not required_columns.issubset(adjudication.columns):
            raise RuntimeError(
                f"adjudication file lacks columns: {sorted(required_columns - set(adjudication.columns))}"
            )
        adjudication["adjudicated_primary_role"] = adjudication.adjudicated_primary_role.map(normalize_role)
        adjudication["adjudicated_secondary_role"] = adjudication.adjudicated_secondary_role.map(normalize_role)
        invalid_primary = sorted(set(adjudication.adjudicated_primary_role) - set(ROLES))
        invalid_secondary = sorted(
            set(adjudication.adjudicated_secondary_role) - (set(ROLES) | {""})
        )
        if invalid_primary or invalid_secondary:
            raise RuntimeError(
                f"invalid adjudicated roles: primary={invalid_primary}, secondary={invalid_secondary}"
            )
        adjudication = adjudication.drop_duplicates("review_id", keep="last")
        missing_ids = sorted(set(unresolved_high.review_id) - set(adjudication.review_id))
        if missing_ids:
            write_blocked("some high-impact disagreements remain unadjudicated", {"review_ids": missing_ids})
            return
        lookup = key[["review_id", "player_id"]].drop_duplicates("review_id")
        adjudication = adjudication.merge(lookup, on="review_id", how="left", validate="one_to_one")
        rows = []
        for row in adjudication.itertuples(index=False):
            for role in [row.adjudicated_primary_role, row.adjudicated_secondary_role]:
                if role in ROLES:
                    rows.append({
                        "review_id": row.review_id,
                        "player_id": int(row.player_id),
                        "final_role": role,
                        "primary_consensus": role == row.adjudicated_primary_role,
                        "high_impact": True,
                        "public_compatible": True,
                        "assignment_source": "explicit_adjudication",
                        "adjudicator": row.adjudicator,
                        "adjudication_rationale": row.rationale,
                    })
        pairs = pd.concat([pairs, pd.DataFrame(rows)], ignore_index=True, sort=False)

    pairs = pairs.drop_duplicates(["player_id", "final_role"], keep="last")
    per_player = pairs.groupby("player_id").final_role.nunique()
    excessive = per_player.loc[per_player.gt(2)]
    if not excessive.empty:
        raise RuntimeError(f"review promotion assigned more than two roles: {excessive.to_dict()}")

    key_columns = [
        column for column in [
            "review_id", "player_id", "display_name", "world_cup_team", "squad_position",
            "annual_minutes", "high_impact_current_release", "allowed_roles",
            "public_anchor_available", "source_type", "source_url", "public_position",
            "evidence_note", "dominant_family", "family_distribution",
        ] if column in key.columns
    ]
    promoted = pairs.merge(
        key[key_columns].drop_duplicates("player_id"),
        on="player_id", how="left", suffixes=("", "_key"),
    )

    role_minutes["role"] = role_minutes.role.map(normalize_role)
    for column in ["role_minutes", "role_observations", "role_share"]:
        role_minutes[column] = pd.to_numeric(role_minutes.get(column), errors="coerce").fillna(0.0)
    exact = role_minutes.rename(columns={
        "role": "final_role",
        "role_minutes": "exact_role_minutes",
        "role_observations": "exact_role_observations",
        "role_share": "exact_role_share",
    })
    family = role_minutes.assign(family=role_minutes.role.map(ROLE_FAMILY)).dropna(subset=["family"])
    family = family.groupby(["player_id", "family"], as_index=False).agg(
        family_minutes=("role_minutes", "sum"),
        family_observations=("role_observations", "sum"),
    )
    total_family = family.groupby("player_id").family_minutes.transform("sum")
    family["family_share"] = family.family_minutes / total_family.replace(0, pd.NA)
    promoted["family"] = promoted.final_role.map(ROLE_FAMILY)
    promoted = promoted.merge(
        exact[[
            "player_id", "final_role", "exact_role_minutes", "exact_role_observations",
            "exact_role_share",
        ]],
        on=["player_id", "final_role"], how="left",
    ).merge(
        family,
        on=["player_id", "family"], how="left",
    )
    for column in [
        "exact_role_minutes", "exact_role_observations", "exact_role_share",
        "family_minutes", "family_observations", "family_share",
    ]:
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
    promoted["public_anchor_available"] = as_bool(promoted.get(
        "public_anchor_available", pd.Series(False, index=promoted.index)
    ))
    promoted["final_role_publicly_compatible"] = promoted.apply(
        lambda row: public_compatible(row.final_role, row.get("allowed_roles")), axis=1
    )
    promoted["human_review_resolved"] = True
    promoted["final_role_eligible_before_coverage"] = (
        promoted.final_role.isin(ROLES)
        & promoted.exact_window_total_minutes.ge(1800)
        & promoted.family_minutes.ge(900)
        & promoted.family_observations.ge(3)
        & (~promoted.public_anchor_available | promoted.final_role_publicly_compatible)
    )
    promoted["overall_final"] = pd.to_numeric(promoted.get("overall"), errors="coerce")
    promoted["conservative_score_final"] = pd.to_numeric(
        promoted.get("conservative_score"), errors="coerce"
    )
    promoted["eligibility_exclusion_reason"] = ""
    promoted.loc[promoted.exact_window_total_minutes.lt(1800), "eligibility_exclusion_reason"] += "total_minutes_lt_1800;"
    promoted.loc[promoted.family_minutes.lt(900), "eligibility_exclusion_reason"] += "positional_family_minutes_lt_900;"
    promoted.loc[promoted.family_observations.lt(3), "eligibility_exclusion_reason"] += "positional_family_observations_lt_3;"
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
    high_impact_ids = set(
        key.loc[as_bool(key.get(
            "high_impact_current_release", pd.Series(False, index=key.index)
        )), "player_id"].astype(int)
    )
    eligible_high_ids = set(eligible.player_id.astype(int))
    high_impact_unresolved = len(high_impact_ids - eligible_high_ids)
    gate = bool(
        all(count >= 20 for count in counts.values())
        and public_conflicts == 0
        and high_impact_unresolved == 0
    )
    status = {
        "status": "ontology_v3_1_candidate_role_promotion_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_gate_passed": True,
        "candidate_role_pairs_promoted": int(len(promoted)),
        "unique_reviewed_players_promoted": int(promoted.player_id.nunique()),
        "final_eligible_candidate_role_pairs_before_coverage": int(len(eligible)),
        "final_eligible_candidates_by_role": counts,
        "minimum_20_candidates_each_role": all(count >= 20 for count in counts.values()),
        "public_anchor_conflicts": public_conflicts,
        "high_impact_players_without_an_eligible_reviewed_role": high_impact_unresolved,
        "eligibility_rule": (
            ">=1800 annual minutes; >=900 minutes and >=3 observations in the reviewed "
            "slot's positional family; reviewer consensus/adjudication; public compatibility"
        ),
        "final_ontology_gate_passed": gate,
        "final_team_construction_allowed": False,
        "output": str(OUTPUT),
        "next_action": (
            "evaluate exact-window data coverage for every promoted candidate-role pair"
            if gate else "resolve candidate-role population, adjudication or public-anchor blockers"
        ),
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
