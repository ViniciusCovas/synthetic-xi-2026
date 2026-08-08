from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_xi_2026.annual_v05 import build_annual_table

from simulator.engine import ROLE_ORDER
from simulator.lab_teams import LAB_MINIMUM_MINUTES, build_national_bundle


@pytest.fixture(scope="module")
def table():
    return build_annual_table("primary", minimum_minutes=LAB_MINIMUM_MINUTES)


@pytest.mark.parametrize("team", ["Spain", "Argentina", "Brazil", "France"])
def test_national_bundle_is_a_real_squad(table, team):
    bundle, decisions = build_national_bundle(team, table)
    # Onze completo, um jogador por slot do motor, sem repetição.
    roles = [player.role for player in bundle.team.players]
    assert sorted(roles) == sorted(ROLE_ORDER)
    starter_ids = set(bundle.starter_ids)
    assert len(starter_ids) == 11
    # Banco real: nenhum reserva é titular; ids registrados únicos.
    bench_ids = {
        profile.player_id
        for reserves in bundle.bench_by_role.values()
        for profile in reserves
    }
    assert not (bench_ids & starter_ids)
    assert len(set(bundle.registered_ids)) == len(bundle.registered_ids)
    # Ordem de pênaltis definida e composta por titulares.
    assert len(bundle.penalty_order_ids) == 11
    assert set(bundle.penalty_order_ids) == starter_ids
    # Toda decisão de fallback fica declarada.
    assert all("decision" in item for item in decisions)


def test_unknown_team_raises(table):
    with pytest.raises(ValueError):
        build_national_bundle("Atlantis", table)
