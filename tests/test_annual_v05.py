from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.annual_v05 import (
    DIMENSIONS,
    build_annual_table,
    build_synthetic_tiers,
    resolve_roles_v2,
    select_real_xi,
    select_squad26,
)

import pytest


@pytest.fixture(scope="module")
def roles():
    return resolve_roles_v2().set_index("player_id")


@pytest.fixture(scope="module")
def table():
    return build_annual_table("primary")


def test_lone_striker_bug_is_fixed(roles):
    # Regressão do bug "9 isolado -> RW": com normalização centrada, os
    # centroavantes de referência resolvem como ST e os laterais como RB/LB.
    assert roles.loc[184, "resolved_role"] == "ST"  # Harry Kane
    assert roles.loc[9, "resolved_role"] == "RB"  # Achraf Hakimi (âncora)
    assert roles.loc[263482, "resolved_role"] == "LB"  # Nuno Mendes (âncora)


def test_identities_are_unique(roles, table):
    assert roles.index.is_unique
    assert table["player_id"].is_unique


def test_flexible_players_are_kept_not_dropped(table):
    flexible = table[table["flexible"]]
    assert len(flexible) > 0
    assert flexible["resolved_role"].notna().all()


def test_real_xi_has_eleven_distinct_players(table):
    xi = select_real_xi(table)
    assert len(xi) == 11
    assert xi["player_id"].nunique() == 11
    assert list(xi["slot"]) == [
        "GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST",
    ]


def test_squad26_realistic_composition(table):
    xi = select_real_xi(table)
    squad = select_squad26(table, xi)
    assert len(squad) == 26
    assert squad["player_id"].nunique() == 26
    goalkeepers = squad[squad["cover_slot"] == "GK"]
    assert len(goalkeepers) >= 3  # titular + 2 reservas
    assert (squad["squad_role"] == "starter").sum() == 11
    assert (squad["squad_role"] == "bench_cover").sum() == 12
    assert (squad["squad_role"] == "bench_flex").sum() == 3


def test_synthetic_tier_monotonicity(table):
    avatars, members = build_synthetic_tiers(table)
    assert set(avatars["tier"]) == {"mean20", "top5", "p90", "max20"}
    for group, block in avatars.groupby("position_group"):
        block = block.set_index("tier")
        for dim in DIMENSIONS:
            assert block.loc["max20", dim] >= block.loc["p90", dim] - 1e-9
            assert block.loc["p90", dim] >= block.loc["mean20", dim] - 1e-9
    # Incerteza pareada: igual entre níveis do mesmo grupo (herdada dos membros).
    sigma_spread = avatars.groupby("position_group")["uncertainty"].nunique()
    assert (sigma_spread == 1).all()
    assert members.groupby("position_group").size().max() <= 20
