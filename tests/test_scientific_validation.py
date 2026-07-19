from __future__ import annotations
import numpy as np,pandas as pd,pytest
from scripts.build_exact_coverage_audit import build_expected_fixture_map
from scripts.resolve_eleven_roles import side
from scripts.run_predictive_backtest import matrix,probs,scores
from simulator.calibrated_core import CalibrationTargets
from simulator.engine import PlayerProfile,ROLE_ORDER,TeamProfile
from simulator.shared_tempo import SharedTempoConfig,SharedTempoMatchSimulator
def team(name,edge=0):
    return TeamProfile(name=name,players=tuple(PlayerProfile(player_id=f'{name}-{r}',name=f'{name}-{r}',role=r,minutes=1800,overall=.55+edge,build_up=.55+edge,progression=.55+edge,creation=.55+edge,finishing=.55+edge,defending=.55+edge,duels=.55+edge,retention=.55+edge,goalkeeping=.55+edge,uncertainty=.02) for r in ROLE_ORDER))
def targets():return CalibrationTargets(source_match_count=94,mean_goals_per_match=2.9,mean_shots_per_match=18,mean_shots_on_target_per_match=8.4,zero_zero_rate=.075,home_win_rate=.45,draw_rate=.25,away_win_rate=.3)
def test_score_matrix_distribution():
    z=matrix(1.4,1.1,-.05);assert z.shape==(11,11);assert np.isclose(z.sum(),1);p=probs(z);assert np.isclose(p.sum(),1);assert p.min()>0
def test_proper_scores_finite():
    s=scores(np.array([.5,.25,.25]),np.array([1.,0.,0.]));assert 0<=s['brier']<=2;assert s['log_loss']>0;assert 0<=s['rps']<=1
def test_expected_fixture_map_windows():
    f=pd.DataFrame([{'fixture_id':1,'league_id':10,'season':2026,'home_team_id':100,'away_team_id':200,'official_senior_main':True,'in_current_window':True,'in_pre_world_cup_window':False},{'fixture_id':2,'league_id':10,'season':2026,'home_team_id':300,'away_team_id':100,'official_senior_main':True,'in_current_window':True,'in_pre_world_cup_window':True}]);c=pd.DataFrame([{'player_id':7,'league_id':10,'season':2026,'team_id':100}]);m=build_expected_fixture_map(f,c,{7});assert m[(7,'annual_current')]=={1,2};assert m[(7,'pre_world_cup')]=={2}
def test_lateral_mapping_explicit():
    assert side(.25,'low_is_left')=='L';assert side(.75,'low_is_left')=='R';assert side(.25,'low_is_right')=='R';assert side(.25,None)=='LOW'
def test_shared_tempo_reproducible():
    c=SharedTempoConfig(seed=42,shared_tempo_sigma=.3);a=SharedTempoMatchSimulator(team('A'),team('B'),targets(),c).simulate(False);b=SharedTempoMatchSimulator(team('A'),team('B'),targets(),c).simulate(False);assert a.as_dict()==b.as_dict()
def test_invalid_sigma():
    with pytest.raises(ValueError):SharedTempoConfig(shared_tempo_sigma=1.2)
