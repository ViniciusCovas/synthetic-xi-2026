#!/usr/bin/env python3
"""Tune shared match tempo and run calibrated simulator v0.3."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
import numpy as np,pandas as pd
from simulator.calibrated_core import CalibrationTargets
from simulator.profiles_v2 import build_teams
from simulator.shared_tempo import SharedTempoConfig,SharedTempoMatchSimulator
C=Path('data/simulations/calibration/world_cup_2026_targets.json');O=Path('data/simulations/calibrated_v0_3');SEED=20260719
def batch(home,away,t,sigma,n,seed,rep=False):
    rng=np.random.default_rng(seed); rows=[]; score={}
    for _ in range(n):
        r=SharedTempoMatchSimulator(home,away,t,SharedTempoConfig(seed=int(rng.integers(0,2**32-1)),shared_tempo_sigma=sigma)).simulate(False)
        rows.append((r.home_goals,r.away_goals,r.home_shots+r.away_shots,r.home_shots_on_target+r.away_shots_on_target,r.home_xg,r.away_xg));k=f'{r.home_goals}-{r.away_goals}';score[k]=score.get(k,0)+1
    a=np.asarray(rows,float);hg,ag=a[:,0],a[:,1];s={'simulations':n,'shared_tempo_sigma':sigma,'home_win_probability':float((hg>ag).mean()),'draw_probability':float((hg==ag).mean()),'away_win_probability':float((hg<ag).mean()),'mean_home_goals':float(hg.mean()),'mean_away_goals':float(ag.mean()),'mean_total_goals':float((hg+ag).mean()),'mean_total_shots':float(a[:,2].mean()),'mean_total_shots_on_target':float(a[:,3].mean()),'mean_home_xg':float(a[:,4].mean()),'mean_away_xg':float(a[:,5].mean()),'zero_zero_probability':score.get('0-0',0)/n,'top_scorelines':[{'score':k,'probability':v/n} for k,v in sorted(score.items(),key=lambda x:(-x[1],x[0]))[:12]],'outcomes':{'home_wins':int((hg>ag).sum()),'draws':int((hg==ag).sum()),'away_wins':int((hg<ag).sum())}}
    if rep:
        target=np.array([s['mean_home_goals'],s['mean_away_goals'],s['mean_total_shots']]);best=None;dist=1e99
        for _ in range(300):
            r=SharedTempoMatchSimulator(home,away,t,SharedTempoConfig(seed=int(rng.integers(0,2**32-1)),shared_tempo_sigma=sigma)).simulate(True);v=np.array([r.home_goals,r.away_goals,r.home_shots+r.away_shots]);d=abs(v[0]-target[0])+abs(v[1]-target[1])+.15*abs(v[2]-target[2])
            if d<dist:dist=d;best=r.as_dict()
        s['representative_match']=best
    return s
def loss(s,t):return abs(s['mean_total_goals']-t.mean_goals_per_match)/.3+abs(s['mean_total_shots']-t.mean_shots_per_match)/2+abs(s['mean_total_shots_on_target']-t.mean_shots_on_target_per_match)+abs(s['zero_zero_probability']-t.zero_zero_rate)/.03
def main():
    O.mkdir(parents=True,exist_ok=True);t=CalibrationTargets.from_dict(json.loads(C.read_text()));syn,real,av,sel=build_teams(20);rows=[]
    for i,x in enumerate(np.linspace(0,.6,7)):
        s=batch(syn,real,t,float(x),1200,SEED+i*101);s['calibration_loss']=loss(s,t);rows.append(s)
    tune=pd.DataFrame([{k:v for k,v in s.items() if k not in {'top_scorelines','outcomes','representative_match'}} for s in rows]).sort_values('calibration_loss');tune.to_csv(O/'shared_tempo_tuning.csv',index=False);sigma=float(tune.iloc[0].shared_tempo_sigma)
    final=batch(syn,real,t,sigma,10000,SEED,True);final.update({'status':'shared_tempo_calibrated_simulation_completed','version':'calibrated_v0.3','home':syn.name,'away':real.name,'calibration_targets':asdict(t),'calibration_error':{'goals_per_match':final['mean_total_goals']-t.mean_goals_per_match,'shots_per_match':final['mean_total_shots']-t.mean_shots_per_match,'shots_on_target_per_match':final['mean_total_shots_on_target']-t.mean_shots_on_target_per_match,'zero_zero_rate':final['zero_zero_probability']-t.zero_zero_rate},'shared_tempo_interpretation':'Mean-one match-wide lognormal tempo creates shared low-event and high-event states without post-hoc score editing.','methodological_gate':{'publication_as_final_result_allowed':False,'reason':'Coverage, roles, external prediction and parameter uncertainty gates remain.'}});(O/'simulation_summary.json').write_text(json.dumps(final,ensure_ascii=False,indent=2));av.to_csv(O/'synthetic_xi_membership.csv',index=False);sel.to_csv(O/'real_best_xi_provisional.csv',index=False)
    e=final['calibration_error'];q={'status':'v0_3_calibration_quality_evaluated','selected_shared_tempo_sigma':sigma,'absolute_goal_error':abs(e['goals_per_match']),'absolute_shot_error':abs(e['shots_per_match']),'absolute_shot_on_target_error':abs(e['shots_on_target_per_match']),'absolute_zero_zero_error':abs(e['zero_zero_rate']),'engineering_gate_passed':bool(abs(e['goals_per_match'])<=.35 and abs(e['shots_per_match'])<=2.5 and abs(e['shots_on_target_per_match'])<=1.2 and abs(e['zero_zero_rate'])<=.025),'final_scientific_gate_passed':False};(O/'calibration_quality.json').write_text(json.dumps(q,ensure_ascii=False,indent=2));print(json.dumps({'quality':q,'simulation':final},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
