#!/usr/bin/env python3
"""Build a release package for the role-level identified set, not a forced XI."""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AUDIT = Path("data/audits/structural_missingness")
OUT = Path("data/releases/v1_0_identified_set")
PAPER = Path("paper/IDENTIFIED_SET_RESULTS.md")
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.parent.mkdir(parents=True, exist_ok=True)
    role_sets = pd.read_csv(AUDIT / "identified_set_by_role.csv", low_memory=False)
    winners = pd.read_csv(AUDIT / "scenario_role_winners.csv", low_memory=False)
    status = json.loads((AUDIT / "structural_missingness_status.json").read_text(encoding="utf-8"))

    candidates = winners[[
        "role", "player_id", "player_name", "world_cup_team", "covered",
        "provider_structural_missingness_confirmed",
    ]].drop_duplicates(["role", "player_id"])
    candidates["player_id"] = pd.to_numeric(candidates.player_id, errors="coerce").astype("Int64")
    candidates = candidates.dropna(subset=["player_id"]).copy()
    candidates["player_id"] = candidates.player_id.astype(int)

    counts = candidates.groupby("role").player_id.nunique()
    invariant_roles = [role for role in ROLES if int(counts.get(role, 0)) == 1]
    ambiguous_roles = [role for role in ROLES if int(counts.get(role, 0)) > 1]
    invariant = candidates.loc[candidates.role.isin(invariant_roles)].sort_values("role")
    ambiguous = candidates.loc[candidates.role.isin(ambiguous_roles)].sort_values(["role", "player_name"])
    invariant.to_csv(OUT / "real_xi_invariant_core.csv", index=False)
    ambiguous.to_csv(OUT / "ambiguous_role_candidates.csv", index=False)

    role_options = []
    for role in ROLES:
        block = candidates.loc[candidates.role.eq(role)].sort_values("player_id")
        role_options.append([row._asdict() for row in block.itertuples(index=False)])
    if any(not options for options in role_options):
        missing = [role for role, options in zip(ROLES, role_options) if not options]
        raise RuntimeError(f"No identified-set candidates for roles: {missing}")

    combination_rows = []
    combinations = list(itertools.product(*role_options))
    for number, combination in enumerate(combinations, start=1):
        combination_id = f"real_xi_set_{number:02d}"
        for row in combination:
            combination_rows.append({"combination_id": combination_id, **row})
    combination_frame = pd.DataFrame(combination_rows)
    combination_frame.to_csv(OUT / "plausible_real_xi_combinations.csv", index=False)

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "release": "v1.0-identified-set-candidate",
        "generated_at_utc": generated_at,
        "source_audit": "structural_missingness_sensitivity_complete",
        "provider_residual_fixtures_exhausted": int(status.get("direct_terminal_fixtures", 0)),
        "unique_real_best_xi_identified": False,
        "scientific_ready_for_unique_xi_claim": False,
        "scientific_ready_for_identified_set_reporting": True,
        "invariant_roles": invariant_roles,
        "ambiguous_roles": ambiguous_roles,
        "invariant_core_size": int(len(invariant_roles)),
        "plausible_real_xi_count": int(len(combinations)),
        "rankings_allowed": False,
        "synthetic_vs_real_point_comparison_allowed": False,
        "allowed_claim": "eight role-level invariant selections plus a finite set of plausible Real XIs under confirmed structural provider missingness",
        "files": [
            "real_xi_invariant_core.csv",
            "ambiguous_role_candidates.csv",
            "plausible_real_xi_combinations.csv",
        ],
    }
    (OUT / "identified_set_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    core_lines = [
        f"- **{row.role}:** {row.player_name} ({row.world_cup_team})"
        for row in invariant.itertuples(index=False)
    ]
    ambiguous_lines = []
    for role in ambiguous_roles:
        names = ambiguous.loc[ambiguous.role.eq(role)].apply(
            lambda row: f"{row.player_name} ({row.world_cup_team})", axis=1
        ).tolist()
        ambiguous_lines.append(f"- **{role}:** " + " / ".join(names))
    document = [
        "# Real XI identified-set result",
        "",
        f"Generated: {generated_at}",
        "",
        "The provider's dedicated fixture-player endpoint was exhausted for every residual fixture.",
        "Because three roles remain non-point-identified under strict missingness bounds, this release",
        "reports an invariant core and a finite identified set instead of forcing a unique Real Best XI.",
        "",
        f"## Invariant core ({len(invariant_roles)} roles)",
        "",
        *core_lines,
        "",
        "## Ambiguous roles",
        "",
        *ambiguous_lines,
        "",
        f"The Cartesian identified set contains **{len(combinations)} plausible Real XI combinations**.",
        "A unique Synthetic XI versus Real XI point comparison remains blocked; later analysis may",
        "compare the Synthetic XI against the full identified set and report an outcome envelope.",
    ]
    PAPER.write_text("\n".join(document) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
