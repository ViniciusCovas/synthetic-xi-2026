#!/usr/bin/env python3
"""Evaluate two completed blind position reviews and enforce preregistered gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("data/audits/position_ontology_v2/blind_review")
A_PATH = ROOT / "reviewer_a_completed.csv"
B_PATH = ROOT / "reviewer_b_completed.csv"
KEY_PATH = ROOT / "answer_key_do_not_share_with_reviewers.csv"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST", "UNRESOLVED"]


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def normalize_role(value: object) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "CBR": "RCB",
        "CBL": "LCB",
        "RWB": "RB",
        "LWB": "LB",
        "CF": "ST",
        "CAM": "AM",
        "CDM": "DM",
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
    permitted = {normalize_role(item) for item in str(allowed or "").split("|") if str(item).strip()}
    return not permitted or role in permitted


def main() -> None:
    missing = [str(path) for path in [A_PATH, B_PATH, KEY_PATH] if not path.exists()]
    if missing:
        status = {
            "status": "waiting_for_completed_blind_reviews",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "missing_files": missing,
            "manual_blind_review_complete": False,
            "review_gate_passed": False,
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
        frame["reviewer_primary_role"] = frame["reviewer_primary_role"].map(normalize_role)
        invalid = sorted(set(frame["reviewer_primary_role"]) - set(ROLES))
        if invalid:
            raise RuntimeError(f"Reviewer {name} contains invalid roles: {invalid}")
        if frame["reviewer_primary_role"].eq("").any():
            raise RuntimeError(f"Reviewer {name} contains blank primary roles")

    merged = (
        a[["review_id", "player_name", "reviewer_primary_role", "confidence_1_3", "evidence_or_rationale"]]
        .rename(columns={
            "reviewer_primary_role": "role_a",
            "confidence_1_3": "confidence_a",
            "evidence_or_rationale": "rationale_a",
        })
        .merge(
            b[["review_id", "reviewer_primary_role", "confidence_1_3", "evidence_or_rationale"]]
            .rename(columns={
                "reviewer_primary_role": "role_b",
                "confidence_1_3": "confidence_b",
                "evidence_or_rationale": "rationale_b",
            }),
            on="review_id",
            how="inner",
            validate="one_to_one",
        )
        .merge(key, on="review_id", how="left", validate="one_to_one")
    )
    if len(merged) != len(key):
        raise RuntimeError("Completed forms do not cover the complete review packet")

    merged["agree"] = merged["role_a"].eq(merged["role_b"])
    merged["consensus_role"] = np.where(merged["agree"], merged["role_a"], "UNRESOLVED")
    merged["high_impact"] = as_bool(merged["high_impact_current_release"])
    merged["public_anchor"] = as_bool(merged["public_anchor_available"])
    merged["public_compatible"] = merged.apply(
        lambda row: public_compatible(row["consensus_role"], row.get("allowed_roles"))
        if row["agree"] and row["public_anchor"]
        else False if row["public_anchor"] else True,
        axis=1,
    )

    agreement = float(merged["agree"].mean())
    high_impact_agreement = float(merged.loc[merged["high_impact"], "agree"].mean())
    kappa = cohen_kappa(merged["role_a"], merged["role_b"])
    anchored = merged.loc[merged["public_anchor"] & merged["agree"]]
    public_compatibility = float(anchored["public_compatible"].mean()) if len(anchored) else 0.0
    unresolved_high_impact = int((merged["high_impact"] & ~merged["agree"]).sum())

    confusion = pd.crosstab(
        merged["role_a"], merged["role_b"], rownames=["reviewer_a"], colnames=["reviewer_b"]
    ).reindex(index=ROLES, columns=ROLES, fill_value=0)
    confusion.to_csv(ROOT / "reviewer_confusion_matrix.csv")
    disagreements = merged.loc[~merged["agree"]].copy()
    disagreements.to_csv(ROOT / "reviewer_disagreements_for_adjudication.csv", index=False)
    consensus = merged[[
        "review_id", "player_id", "player_name", "world_cup_team", "role_a", "role_b",
        "consensus_role", "high_impact", "public_anchor", "public_compatible",
    ]].copy()
    consensus.to_csv(ROOT / "blind_review_consensus.csv", index=False)

    gate = bool(
        kappa >= 0.80
        and high_impact_agreement >= 0.90
        and public_compatibility >= 0.90
        and unresolved_high_impact == 0
    )
    status = {
        "status": "blind_position_review_evaluated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_cases": int(len(merged)),
        "raw_agreement": agreement,
        "cohen_kappa": kappa,
        "high_impact_agreement": high_impact_agreement,
        "public_anchor_compatibility_among_agreements": public_compatibility,
        "unresolved_high_impact_cases": unresolved_high_impact,
        "thresholds": {
            "cohen_kappa": 0.80,
            "high_impact_agreement": 0.90,
            "public_anchor_compatibility": 0.90,
            "unresolved_high_impact_cases": 0,
        },
        "manual_blind_review_complete": True,
        "review_gate_passed": gate,
        "new_final_simulation_allowed": False,
        "next_action": (
            "adjudicate disagreements, rebuild role populations and rerun the final ontology gate"
            if not gate
            else "promote consensus roles into ontology v3, rebuild populations and evaluate Top-20 sufficiency"
        ),
    }
    (ROOT / "blind_review_evaluation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
