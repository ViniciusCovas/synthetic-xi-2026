#!/usr/bin/env python3
"""Strict pre-tournament holdout using frozen player profiles.

Team strengths are computed only from the pre-World-Cup window ending 2026-06-10.
The World Cup fixture outcomes are used exclusively for evaluation. No team-strength
parameter is fitted on the holdout. The global goal prior is fixed at 2.60 goals per
90-minute international match and is declared rather than estimated from the holdout.
This validates whether the frozen player-profile signal carries predictive information;
it is not yet a validation of every micro-event mechanism in the simulator.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd

OUT=Path('data/validation'); OUT.mkdir(parents=True,exist_ok=True)

def poisson(k,lam): return math.exp(-lam)*(lam**k)/math.factorial(k)
def probs(lh,la,maxg=10):
    h=d=a=0.0
    for i in range(maxg+1):
        pi=poisson(i,lh)
        for j in range(maxg+1):
            p=pi*poisson(j,la)
            if i>j:h+=p
            elif i==j:d+=p
            else:a+=p
    z=h+d+a
    return np.array([h/z,d/z,a/z])
def outcome(h,a): return 0 if h>a else 1 if h==a else 2
def scores(y,p):
    one=np.zeros(3);one[y]=1
    return float(np.square(p-one).sum()),float(-math.log(max(1e-12,p[y]))),float(((p[0]-one[0])**2+(p[0]+p[1]-one[0]-one[1])**2)/2)
def robust(s):
    s=pd.to_numeric(s,errors='coerce');med=s.median();iq=max(float(s.quantile(.75)-s.quantile(.25)),1e-9);z=((s-med)/iq).clip(-8,8);return 1/(1+np.exp(-z))
def main():
    totals=pd.read_csv('data/model_readiness/partial_pre_world_cup_totals.csv')
    roles=pd.read_csv('data/model_readiness/partial_role_evidence.csv')
    fixtures=pd.read_csv('data/processed/fixtures.csv')
    for c in ['minutes_num','goals_total','assists','shots_on','passes_key','passes_total','passes_completed','tackles_total','interceptions','duels_won','saves']:
        totals[c]=pd.to_numeric(totals.get(c),errors='coerce').fillna(0.0)
    m=(totals.minutes_num/90).clip(lower=1e-9)
    totals['attack_raw']=5*totals.goals_total/m+2.8*totals.assists/m+1.1*totals.passes_key/m+.7*totals.shots_on/m
    totals['control_raw']=.015*totals.passes_total/m+4*(totals.passes_completed/totals.passes_total.replace(0,np.nan)).fillna(0)+.35*totals.duels_won/m
    totals['defence_raw']=1.1*totals.tackles_total/m+1.5*totals.interceptions/m+.35*totals.duels_won/m+.45*totals.saves/m
    for c in ['attack','control','defence']: totals[c]=robust(totals[c+'_raw'])
    keep=['player_id','world_cup_team','squad_position']
    x=totals.merge(roles[keep].drop_duplicates('player_id'),on='player_id',how='left').dropna(subset=['world_cup_team'])
    x=x.loc[x.minutes_num.ge(450)].copy()
    x['overall']=.42*x.attack+.25*x.control+.33*x.defence
    # Best available 18-player tournament squad signal; minutes-weighted top 11 dominate.
    team_rows=[]
    for team,g in x.groupby('world_cup_team'):
        g=g.sort_values('overall',ascending=False).head(18).copy();w=np.sqrt(g.minutes_num.clip(lower=90));
        team_rows.append({'team':team,'players':len(g),'strength':float(np.average(g.overall,weights=w)),'attack':float(np.average(g.attack,weights=w)),'defence':float(np.average(g.defence,weights=w))})
    teams=pd.DataFrame(team_rows);mu=teams.strength.mean();sd=max(float(teams.strength.std(ddof=0)),1e-9);teams['z']=(teams.strength-mu)/sd
    strength=teams.set_index('team').z.to_dict(); attack=teams.set_index('team').attack.to_dict(); defence=teams.set_index('team').defence.to_dict()
    fixtures=fixtures.loc[fixtures.status.astype(str).eq('FT')].copy()
    rows=[]; prior=np.array([1/3,1/3,1/3])
    for r in fixtures.itertuples(index=False):
        if r.home_team not in strength or r.away_team not in strength: continue
        edge=strength[r.home_team]-strength[r.away_team]
        # Neutral-site tournament: no home advantage. Attack/defence terms come only from frozen profiles.
        lh=1.30*math.exp(.22*edge+.18*(attack[r.home_team]-defence[r.away_team]))
        la=1.30*math.exp(-.22*edge+.18*(attack[r.away_team]-defence[r.home_team]))
        p=probs(lh,la);y=outcome(int(r.home_goals),int(r.away_goals));b,ll,rps=scores(y,p);bn,lln,rn=scores(y,prior)
        rows.append({'fixture_id':int(r.fixture_id),'home_team':r.home_team,'away_team':r.away_team,'home_goals':int(r.home_goals),'away_goals':int(r.away_goals),'lambda_home':lh,'lambda_away':la,'p_home':p[0],'p_draw':p[1],'p_away':p[2],'outcome':y,'brier':b,'log_loss':ll,'rps':rps,'naive_log_loss':lln})
    pred=pd.DataFrame(rows);pred.to_csv(OUT/'external_pre_tournament_predictions.csv',index=False)
    if pred.empty: raise RuntimeError('No holdout matches matched frozen team profiles')
    summary={'status':'external_pre_tournament_holdout_complete','profile_freeze':'2026-06-10','holdout':'World Cup 2026 FT matches','matches':int(len(pred)),'teams_with_frozen_profiles':int(len(teams)),'model':'frozen squad-strength Poisson baseline','fixed_goal_prior':2.60,'brier_score':float(pred.brier.mean()),'log_loss':float(pred.log_loss.mean()),'ranked_probability_score':float(pred.rps.mean()),'top1_accuracy':float((pred[['p_home','p_draw','p_away']].to_numpy().argmax(1)==pred.outcome.to_numpy()).mean()),'naive_log_loss':float(pred.naive_log_loss.mean()),'log_loss_skill_vs_naive':float(1-pred.log_loss.mean()/pred.naive_log_loss.mean()),'external_pre_tournament_validation_passed':bool(len(pred)>=80 and pred.log_loss.mean()<pred.naive_log_loss.mean()),'claim_scope':'predictive information in frozen player-profile aggregation, not full validation of the event simulator','limitations':['fixed global goal prior','no betting-market comparison','club-to-national-team transfer assumption','lineup availability not known before each match']}
    (OUT/'external_pre_tournament_holdout_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));teams.to_csv(OUT/'frozen_pre_tournament_team_strengths.csv',index=False);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
