#!/usr/bin/env python3
"""Top-N and declared coordination sensitivity for exploratory teams."""
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
import numpy as np,pandas as pd
from simulator.calibrated_core import CalibrationTargets
from simulator.engine import TeamProfile
from simulator.profiles_v2 import build_teams
from simulator.shared_tempo import SharedTempoConfig,SharedTempoMatchSimulator
C=Path('data/simulations/calibration/world_cup_2026_targets.json');Q=Path('data/simulations/calibrated_v0_3/calibration_quality.json');O=Path('data/validation');SEED=20260720
def adjust(team,f,label):
    ps=[]
    for p in team.players:
        v={k:float(np.clip(.5+f*(float(getattr(p,k))-.5),0,1)) for k in ['build_up','progression','creation','retention','duels']};ps.append(replace(p,**v))
    return TeamProfile(name=f'{team.name} [{label}]',players=tuple(ps),tempo=float(np.clip(.5+f*(team.tempo-.5),0,1)),press=float(np.clip(.5+f*(team.press-.5),0,1)),directness=team.directness)
def sim(h,a,t,sigma,n,seed):
    r=np.random.default_rng(seed);w=d=l=0;g=[]
    for _ in range(n):
        x=SharedTempoMatchSimulator(h,a,t,SharedTempoConfig(seed=int(r.integers(0,2**32-1)),shared_tempo_sigma=sigma)).simulate(False);w+=x.home_goals>x.away_goals;d+=x.home_goals==x.away_goals;l+=x.home_goals<x.away_goals;g.append(x.home_goals+x.away_goals)
    return {'synthetic_win_probability':w/n,'draw_probability':d/n,'real_win_probability':l/n,'mean_total_goals':float(np.mean(g))}
def main():
    O.mkdir(parents=True,exist_ok=True);t=CalibrationTargets.from_dict(json.loads(C.read_text()));sigma=float(json.loads(Q.read_text())['selected_shared_tempo_sigma']);sc={'equal_full_coordination':(1,1),'equal_moderate_coordination':(.95,.95),'synthetic_coordination_penalty':(.9,1),'real_xi_coordination_penalty':(1,.9)};rows=[];rr=[];run=0
    for n in [10,20,30]:
        syn,real,av,sel=build_teams(n)
        for x in av.itertuples(index=False):rr.append({'top_n':n,'team':'synthetic','slot':x.slot,'selection':x.member_names})
        for x in sel.itertuples(index=False):rr.append({'top_n':n,'team':'real','slot':x.slot,'selection':x.player_name})
        for name,(sf,rf) in sc.items():
            run+=1;rows.append({'top_n':n,'scenario':name,'synthetic_coordination_factor':sf,'real_coordination_factor':rf,'simulations':1500,'shared_tempo_sigma':sigma,**sim(adjust(syn,sf,name),adjust(real,rf,name),t,sigma,1500,SEED+run*131)})
    x=pd.DataFrame(rows);x.to_csv(O/'topn_chemistry_sensitivity.csv',index=False);pd.DataFrame(rr).to_csv(O/'topn_roster_sensitivity.csv',index=False);base=x[(x.top_n==20)&x.scenario.eq('equal_full_coordination')].iloc[0];status={'status':'topn_and_coordination_sensitivity_complete','scenarios':len(x),'simulations_per_scenario':1500,'baseline_top_n':20,'baseline':base.to_dict(),'ranges':{'synthetic_win_min':float(x.synthetic_win_probability.min()),'synthetic_win_max':float(x.synthetic_win_probability.max()),'draw_min':float(x.draw_probability.min()),'draw_max':float(x.draw_probability.max()),'real_win_min':float(x.real_win_probability.min()),'real_win_max':float(x.real_win_probability.max())},'robust_direction':bool((x.real_win_probability>x.synthetic_win_probability).all()),'final_scientific_gate_passed':False,'note':'Coordination factors are declared sensitivity assumptions, not estimated chemistry parameters.'};(O/'sensitivity_summary.json').write_text(json.dumps(status,ensure_ascii=False,indent=2));print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
