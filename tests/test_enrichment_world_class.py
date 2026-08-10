from pathlib import Path
import json
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SB = ROOT / "data" / "enrichment" / "statsbomb"


@pytest.mark.skipif(not (SB / "international_shots.csv.gz").exists(),
                    reason="remates não sincronizados")
def test_statsbomb_shots_table_is_sound():
    shots = pd.read_csv(SB / "international_shots.csv.gz")
    assert len(shots) > 5000
    assert shots["match_id"].nunique() > 220
    assert set(shots["season"].astype(str)) == {"2018", "2020", "2022", "2024"}
    # geometria coerente (tolerância de 0,5 para cantos na linha) e ângulo positivo
    assert shots["x"].between(0, 120.5).all() and shots["y"].between(0, 80.5).all()
    # ângulo 0 é legítimo para remates na própria linha de fundo fora dos postes
    assert (shots["visible_angle_rad"] >= 0).all()
    # golos são subconjunto dos no-alvo
    assert not (shots["is_goal"] & ~shots["on_target"]).any()


@pytest.mark.skipif(not (SB / "xg_model_v1.json").exists(),
                    reason="modelo xG não ajustado")
def test_xg_model_holdout_quality():
    model = json.loads((SB / "xg_model_v1.json").read_text())
    holdout = model["metrics"]["test_holdout_wc2022_euro2024"]
    provider = model["metrics"]["provider_xg_on_same_holdout"]
    naive = 0.31  # log-loss de prever a taxa-base (~9,1%) para todos
    assert holdout["log_loss"] < naive
    # dentro de 15% do xG do provedor (que usa freeze-frames que não temos)
    assert holdout["log_loss"] < provider["log_loss"] * 1.15
    # calibrado: média prevista perto da taxa-base
    assert abs(holdout["mean_predicted"] - holdout["base_rate"]) < 0.01


def test_league_strength_estimates_have_sane_direction():
    table = pd.read_csv(ROOT / "data/reference/league_strength_estimated_2026.csv")
    table = table.set_index("league_id")
    estimable = table[table["estimable"] == True]  # noqa: E712
    assert len(estimable) >= 20
    # Big-5 perto de 1.0 por construção da referência
    big5 = estimable.loc[[i for i in (39, 140, 78, 135, 61) if i in estimable.index]]
    assert ((big5["factor_estimated"] - 1.0).abs() < 0.12).all()
    assert estimable["factor_estimated"].between(0.70, 1.05).all()


def test_estimated_scenario_produces_selection():
    from synthetic_xi_2026.annual_v05 import build_annual_table, select_real_xi
    xi = select_real_xi(build_annual_table("estimated"))
    assert len(xi) == 11 and xi["player_id"].nunique() == 11
