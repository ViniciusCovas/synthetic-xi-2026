#!/usr/bin/env python3
"""Evaluate two completed ontology-v3 blind position reviews."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
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
    text = str(value or "").strip().upper()
    aliases = {
        "CBR": "RCB", "CBL": "LCB", "RWB": "RB", "LWB": "LB",
        "CF": "ST", "CAM": "AM", "CDM": "DM",
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


def public_compatible(role: str, allowed: object) -> bool:
    permitted = {
        normalize_role(item) for item in str(allowed or "").split("|") if str(item).strip()
    }
    return not permitted or role in permitted


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    missing = [str(path) for path in [A_PATH, B_PATH, KEY_PATH] if not path.exists()]
    if missing:
        status = {
            "status": "waiting_for_completed_blind_reviews_v3",
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
    required = {"review_id", "reviewer_primary_role"}
    for name, frame in [("A", a), ("B", b)]:
        if not required.issubset(frame.columns):
            raise RuntimeError(f"Reviewer {name} form lacks required columns")
        frame["reviewer_primary_role"] = frame.reviewer_primary_role.map(normalize_role)
        invalid = sorted(set(frame.reviewer_primary_role) - set(ROLES))
        if invalid:
            raise RuntimeError(f"Reviewer {name} contains invalid roles: {invalid}")
        if frame.reviewer_primary_role.eq("").any():
            raise RuntimeError(f"Reviewer {name} contains blank primary roles")

    a_columns = ["review_id", "player_name", "reviewer_primary_role", "confidence_1_3", "evidence_or_rationale"]
    b_columns = ["review_id", "reviewer_primary_role", "confidence_1_3", "evidence_or_rationale"]
    merged = (
        a[a_columns].rename(columns={
            "reviewer_primary_role": "role_a",
            "confidence_1_3": "confidence_a",
            "evidence_or_rationale": "rationale_a",
        })
        .merge(
            b[b_columns].rename(columns={
                "reviewer_primary_role": "role_b",
                "confidence_1_3": "confidence_b",
                "evidence_or_rationale": "rationale_b",
            }),
            on="review_id", how="inner", validate="one_to_one",
        )
        .merge(key, on="review_id", how="left", validate="one_to_one")
    )
    if len(merged) != len(key):
        raise RuntimeError("Completed forms do not cover the complete v3 review packet")

    merged["agree"] = merged.role_a.eq(merged.role_b)
    merged["consensus_role"] = np.where(merged.agree, merged.role_a, "UNRESOLVED")
    merged["high_impact"] = as_bool(merged.get(
        "high_impact_current_release", pd.Series(False, index=merged.index)
    ))
    merged["eligible_primary_candidate"] = as_bool(merged.get(
        "eligible_primary_candidate", pd.Series(False, index=merged.index)
    ))
    merged["public_anchor"] = as_bool(merged.get(
        "public_anchor_available", pd.Series(False, index=merged.index)
    ))
    merged["public_compatible"] = merged.apply(
        lambda row: public_compatible(row.consensus_role, row.get("allowed_roles"))
        if row.agree and row.public_anchor
        else False if row.public_anchor else True,
        axis=1,
    )

    agreement = float(merged.agree.mean())
    high_impact_agreement = float(merged.loc[merged.high_impact, "agree"].mean()) if merged.high_impact.any() else 1.0
    kappa = cohen_kappa(merged.role_a, merged.role_b)
    anchored = merged.loc[merged.public_anchor & merged.agree]
    public_compatibility = float(anchored.public_compatible.mean()) if len(anchored) else 0.0
    unresolved_high_impact = int((merged.high_impact & ~merged.agree).sum())

    consensus_eligible = merged.loc[
        merged.eligible_primary_candidate
        & merged.agree
        & merged.consensus_role.isin(FINAL_ROLES)
    ].copy()
    consensus_counts = (
        consensus_eligible.groupby("consensus_role").player_id.nunique()
        .reindex(FINAL_ROLES, fill_value=0).astype(int).to_dict()
    )
    population_pass = all(count >= 20 for count in consensus_counts.values())

    confusion = pd.crosstab(
        merged.role_a, merged.role_b, rownames=["reviewer_a"], colnames=["reviewer_b"]
    ).reindex(index=ROLES, columns=ROLES, fill_value=0)
    confusion.to_csv(ROOT / "reviewer_confusion_matrix.csv")
    merged.loc[~merged.agree].to_csv(
        ROOT / "reviewer_disagreements_for_adjudication.csv", index=False
    )
    consensus_columns = [
        column for column in [
            "review_id", "player_id", "player_name", "world_cup_team", "role_a", "role_b",
            "consensus_role", "agree", "high_impact", "eligible_primary_candidate",
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
    final_ontology_gate = bool(review_gate and population_pass and not (~merged.agree & merged.high_impact).any())
    status = {
        "status": "blind_position_review_v3_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_cases": int(len(merged)),
        "raw_agreement": agreement,
        "cohen_kappa": kappa,
        "high_impact_agreement": high_impact_agreement,
        "public_anchor_compatibility_among_agreements": public_compatibility,
        "unresolved_high_impact_cases": unresolved_high_impact,
        "consensus_eligible_candidates_by_role": consensus_counts,
        "minimum_20_consensus_candidates_each_role": population_pass,
        "thresholds": {
            "cohen_kappa": 0.80,
            "high_impact_agreement": 0.90,
            "public_anchor_compatibility": 0.90,
            "unresolved_high_impact_cases": 0,
            "consensus_candidates_each_role": 20,
        },
        "manual_blind_review_complete": True,
        "review_gate_passed": review_gate,
        "final_ontology_gate_passed": final_ontology_gate,
        "new_final_simulation_allowed": False,
        "next_action": (
            "adjudicate disagreements and rerun this evaluator"
            if not review_gate
            else "promote consensus roles and recalculate final candidate coverage"
            if final_ontology_gate
            else "adjudicate or expand deficient role pools before ontology promotion"
        ),
    }
    (ROOT / "blind_review_evaluation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
