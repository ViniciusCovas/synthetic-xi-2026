#!/usr/bin/env python3
"""Nested Monte Carlo separating parameter worlds from match randomness."""
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
import numpy as np,pandas as pd
from simulator.calibrated_core import CalibrationTargets
from simulator.engine import TeamProfile
from simulator.profiles_v2 import build_teams
from simulator.shared_tempo import SharedTempoConfig,SharedTempoMatchSimulator
C=Path('data/simulations/calibration/world_cup_2026_targets.json');Q=Path('data/simulations/calibrated_v0_3/calibration_quality.json');O=Path('data/validation');SEED=20260721;OUTER=120;INNER=80
def freeze(team,rng,coord):
    s=team.sampled(rng);ps=[]
    for p in s.players:
        v={k:float(np.clip(.5+coord*(float(getattr(p,k))-.5),0,1)) for k in ['build_up','progression','creation','retention','duels']};ps.append(replace(p,uncertainty=.015,**v))
    return TeamProfile(name=s.name,players=tuple(ps),tempo=s.tempo,press=s.press,directness=s.directness)
def main():
    O.mkdir(parents=True,exist_ok=True);t=CalibrationTargets.from_dict(json.loads(C.read_text()));base=float(json.loads(Q.read_text())['selected_shared_tempo_sigma']);syn,real,_,_=build_teams(20);master=np.random.default_rng(SEED);rows=[]
    for wid in range(OUTER):
        seed=int(master.integers(0,2**32-1));r=np.random.default_rng(seed);sc=float(np.clip(r.normal(.97,.035),.85,1.05));rc=float(np.clip(r.normal(.97,.035),.85,1.05));hs=freeze(syn,r,sc);hr=freeze(real,r,rc);sigma=float(np.clip(r.normal(base,.05),0,.8));ability=float(np.clip(r.normal(.75,.07),.5,1));shot=float(np.clip(r.normal(.95,.08),.65,1.25));conv=float(np.clip(r.normal(.8,.08),.55,1.1));w=d=l=0;g=[]
        for _ in range(INNER):
            x=SharedTempoMatchSimulator(hs,hr,t,SharedTempoConfig(seed=int(r.integers(0,2**32-1)),shared_tempo_sigma=sigma,ability_scale=ability,shot_edge_scale=shot,conversion_edge_scale=conv)).simulate(False);w+=x.home_goals>x.away_goals;d+=x.home_goals==x.away_goals;l+=x.home_goals<x.away_goals;g.append(x.home_goals+x.away_goals)
        rows.append({'world_id':wid,'outer_seed':seed,'inner_matches':INNER,'synthetic_coordination':sc,'real_coordination':rc,'shared_tempo_sigma':sigma,'ability_scale':ability,'shot_edge_scale':shot,'conversion_edge_scale':conv,'synthetic_win_probability':w/INNER,'draw_probability':d/INNER,'real_win_probability':l/INNER,'mean_total_goals':float(np.mean(g))})
    x=pd.DataFrame(rows);x.to_csv(O/'nested_uncertainty_worlds.csv',index=False);intervals={}
    for c in ['synthetic_win_probability','draw_probability','real_win_probability','mean_total_goals']:intervals[c]={'mean':float(x[c].mean()),'median':float(x[c].median()),'p025':float(x[c].quantile(.025)),'p10':float(x[c].quantile(.1)),'p90':float(x[c].quantile(.9)),'p975':float(x[c].quantile(.975))}
    s={'status':'nested_uncertainty_complete','outer_parameter_worlds':OUTER,'inner_matches_per_world':INNER,'total_matches':OUTER*INNER,'intervals':intervals,'probability_real_xi_more_likely_than_synthetic':float((x.real_win_probability>x.synthetic_win_probability).mean()),'uncertainty_scope':['player-profile uncertainty','coordination sensitivity','shared tempo','ability and conversion scales','match randomness'],'not_yet_included':['league-strength posterior','role-classification posterior','injury and lineup uncertainty','externally estimated chemistry'],'final_scientific_gate_passed':False};(O/'nested_uncertainty_summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2));print(json.dumps(s,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
