#!/usr/bin/env python3
"""Evaluate two completed ontology-v3.1 blind position reviews.

Primary-role reliability is measured with Cohen's kappa. Optional secondary roles are
used only when both reviewers independently include the same exact slot. The evaluator
never promotes players or authorizes a simulation; promotion and family-experience
eligibility are separate downstream gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("data/audits/position_ontology_v3/blind_review")
A_PATH = ROOT / "reviewer_a_completed.csv"
B_PATH = ROOT / "reviewer_b_completed.csv"
KEY_PATH = ROOT / "answer_key_do_not_share_with_reviewers.csv"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST", "UNRESOLVED"]
FINAL_ROLES = ROLES[:-1]


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


def cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    labels = sorted(set(a) | set(b))
    if not labels:
        return float("nan")
    observed = float((a == b).mean())
    pa = a.value_counts(normalize=True).reindex(labels, fill_value=0)
    pb = b.value_counts(normalize=True).reindex(labels, fill_value=0)
    expected = float((pa * pb).sum())
    return float((observed - expected) / (1 - expected)) if expected < 1 else 1.0


def reviewer_set(primary: str, secondary: str) -> set[str]:
    values = {role for role in [primary, secondary] if role in FINAL_ROLES}
    return values


def encode_roles(values: set[str]) -> str:
    return "|".join(role for role in FINAL_ROLES if role in values)


def public_role_compatible(role: str, allowed: object) -> bool:
    permitted = {
        normalize_role(item) for item in str(allowed or "").split("|") if str(item).strip()
    }
    return not permitted or role in permitted


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    missing = [str(path) for path in [A_PATH, B_PATH, KEY_PATH] if not path.exists()]
    if missing:
        status = {
            "status": "waiting_for_completed_blind_reviews_v3_1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "missing_files": missing,
            "manual_blind_review_complete": False,
            "review_gate_passed": False,
            "final_ontology_gate_passed": False,
            "new_final_simulation_allowed": False,
        }
        (ROOT / "blind_review_evaluation.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    a = pd.read_csv(A_PATH, low_memory=False)
    b = pd.read_csv(B_PATH, low_memory=False)
    key = pd.read_csv(KEY_PATH, low_memory=False)
    required = {"review_id", "reviewer_primary_role", "reviewer_secondary_role"}
    for name, frame in [("A", a), ("B", b)]:
        if not required.issubset(frame.columns):
            raise RuntimeError(f"Reviewer {name} form lacks required columns")
        frame["reviewer_primary_role"] = frame.reviewer_primary_role.map(normalize_role)
        frame["reviewer_secondary_role"] = frame.reviewer_secondary_role.map(normalize_role)
        invalid_primary = sorted(set(frame.reviewer_primary_role) - set(ROLES))
        invalid_secondary = sorted(
            set(frame.reviewer_secondary_role) - (set(FINAL_ROLES) | {""})
        )
        if invalid_primary:
            raise RuntimeError(f"Reviewer {name} contains invalid primary roles: {invalid_primary}")
        if invalid_secondary:
            raise RuntimeError(f"Reviewer {name} contains invalid secondary roles: {invalid_secondary}")
        if frame.reviewer_primary_role.eq("").any():
            raise RuntimeError(f"Reviewer {name} contains blank primary roles")
        duplicate = (
            frame.reviewer_secondary_role.ne("")
            & frame.reviewer_secondary_role.eq(frame.reviewer_primary_role)
        )
        if duplicate.any():
            raise RuntimeError(f"Reviewer {name} repeated the primary role as secondary")

    a_columns = [
        "review_id", "player_name", "reviewer_primary_role", "reviewer_secondary_role",
        "confidence_1_3", "evidence_or_rationale",
    ]
    b_columns = [
        "review_id", "reviewer_primary_role", "reviewer_secondary_role",
        "confidence_1_3", "evidence_or_rationale",
    ]
    merged = (
        a[a_columns].rename(columns={
            "reviewer_primary_role": "primary_a",
            "reviewer_secondary_role": "secondary_a",
            "confidence_1_3": "confidence_a",
            "evidence_or_rationale": "rationale_a",
        })
        .merge(
            b[b_columns].rename(columns={
                "reviewer_primary_role": "primary_b",
                "reviewer_secondary_role": "secondary_b",
                "confidence_1_3": "confidence_b",
                "evidence_or_rationale": "rationale_b",
            }),
            on="review_id", how="inner", validate="one_to_one",
        )
        .merge(key, on="review_id", how="left", validate="one_to_one")
    )
    if len(merged) != len(key):
        raise RuntimeError("Completed forms do not cover the complete v3.1 review packet")

    merged["primary_agree"] = merged.primary_a.eq(merged.primary_b)
    merged["roles_a"] = merged.apply(
        lambda row: encode_roles(reviewer_set(row.primary_a, row.secondary_a)), axis=1
    )
    merged["roles_b"] = merged.apply(
        lambda row: encode_roles(reviewer_set(row.primary_b, row.secondary_b)), axis=1
    )
    merged["consensus_roles"] = merged.apply(
        lambda row: encode_roles(
            reviewer_set(row.primary_a, row.secondary_a)
            & reviewer_set(row.primary_b, row.secondary_b)
        ),
        axis=1,
    )
    merged["role_sets_exactly_agree"] = merged.roles_a.eq(merged.roles_b)
    merged["high_impact"] = as_bool(merged.get(
        "high_impact_current_release", pd.Series(False, index=merged.index)
    ))
    merged["public_anchor"] = as_bool(merged.get(
        "public_anchor_available", pd.Series(False, index=merged.index)
    ))

    def compatible_consensus(row: pd.Series) -> bool:
        if not row.public_anchor:
            return True
        roles = [role for role in str(row.consensus_roles).split("|") if role]
        if not roles:
            return False
        return all(public_role_compatible(role, row.get("allowed_roles")) for role in roles)

    merged["public_compatible"] = merged.apply(compatible_consensus, axis=1)
    primary_agreement = float(merged.primary_agree.mean())
    exact_role_set_agreement = float(merged.role_sets_exactly_agree.mean())
    high_impact_agreement = (
        float(merged.loc[merged.high_impact, "primary_agree"].mean())
        if merged.high_impact.any() else 1.0
    )
    kappa = cohen_kappa(merged.primary_a, merged.primary_b)
    anchored = merged.loc[merged.public_anchor]
    public_compatibility = (
        float(anchored.public_compatible.mean()) if len(anchored) else 0.0
    )
    unresolved_high_impact = int((merged.high_impact & ~merged.primary_agree).sum())

    role_rows: list[dict] = []
    for row in merged.itertuples(index=False):
        for role in [value for value in str(row.consensus_roles).split("|") if value]:
            role_rows.append({
                "review_id": row.review_id,
                "player_id": int(row.player_id),
                "role": role,
                "primary_consensus": bool(row.primary_agree and row.primary_a == role),
                "high_impact": bool(row.high_impact),
                "public_compatible": bool(row.public_compatible),
            })
    consensus_pairs = pd.DataFrame(role_rows, columns=[
        "review_id", "player_id", "role", "primary_consensus", "high_impact",
        "public_compatible",
    ])
    consensus_pairs.to_csv(ROOT / "blind_review_consensus_candidate_roles.csv", index=False)
    consensus_counts = (
        consensus_pairs.groupby("role").player_id.nunique()
        .reindex(FINAL_ROLES, fill_value=0).astype(int).to_dict()
        if not consensus_pairs.empty else {role: 0 for role in FINAL_ROLES}
    )

    confusion = pd.crosstab(
        merged.primary_a, merged.primary_b,
        rownames=["reviewer_a_primary"], colnames=["reviewer_b_primary"],
    ).reindex(index=ROLES, columns=ROLES, fill_value=0)
    confusion.to_csv(ROOT / "reviewer_primary_confusion_matrix.csv")
    disagreement_mask = ~merged.primary_agree | ~merged.role_sets_exactly_agree
    merged.loc[disagreement_mask].to_csv(
        ROOT / "reviewer_disagreements_for_adjudication.csv", index=False
    )
    consensus_columns = [
        column for column in [
            "review_id", "player_id", "player_name", "world_cup_team",
            "primary_a", "primary_b", "secondary_a", "secondary_b", "roles_a", "roles_b",
            "consensus_roles", "primary_agree", "role_sets_exactly_agree", "high_impact",
            "public_anchor", "public_compatible", "confidence_a", "confidence_b",
            "rationale_a", "rationale_b",
        ] if column in merged.columns
    ]
    merged[consensus_columns].to_csv(ROOT / "blind_review_consensus.csv", index=False)

    review_gate = bool(
        kappa >= 0.80
        and high_impact_agreement >= 0.90
        and public_compatibility >= 0.90
        and unresolved_high_impact == 0
    )
    status = {
        "status": "blind_position_review_v3_1_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_cases": int(len(merged)),
        "primary_raw_agreement": primary_agreement,
        "exact_primary_secondary_set_agreement": exact_role_set_agreement,
        "cohen_kappa_primary": kappa,
        "high_impact_primary_agreement": high_impact_agreement,
        "public_anchor_compatibility_of_consensus_roles": public_compatibility,
        "unresolved_high_impact_primary_cases": unresolved_high_impact,
        "consensus_candidate_role_pairs": int(len(consensus_pairs)),
        "consensus_candidates_by_role_before_family_eligibility": consensus_counts,
        "thresholds": {
            "cohen_kappa_primary": 0.80,
            "high_impact_primary_agreement": 0.90,
            "public_anchor_compatibility": 0.90,
            "unresolved_high_impact_primary_cases": 0,
        },
        "manual_blind_review_complete": True,
        "review_gate_passed": review_gate,
        "final_ontology_gate_passed": False,
        "new_final_simulation_allowed": False,
        "next_action": (
            "adjudicate primary or secondary-role disagreements and rerun this evaluator"
            if not review_gate
            else "promote agreed/adjudicated candidate-role pairs and apply family-experience eligibility"
        ),
    }
    (ROOT / "blind_review_evaluation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
