#!/usr/bin/env python3
"""Leakage-resistant rolling-origin outcome baselines for completed 90-minute games."""
from __future__ import annotations
import json,math
from collections import defaultdict,deque
from pathlib import Path
import numpy as np,pandas as pd
F=Path('data/processed/fixtures.csv'); P=Path('data/processed/player_matches.csv'); O=Path('data/validation'); M=10; E=1e-12
def pmf(k,r): r=max(1e-6,float(r)); return math.exp(k*math.log(r)-r-math.lgamma(k+1))
def matrix(l,m,rho=0.0):
    z=np.outer([pmf(i,l) for i in range(M+1)],[pmf(i,m) for i in range(M+1)])
    for (i,j),t in {(0,0):1-l*m*rho,(0,1):1+l*rho,(1,0):1+m*rho,(1,1):1-rho}.items(): z[i,j]*=max(.05,t)
    return z/z.sum()
def probs(z):
    x=np.array([np.tril(z,-1).sum(),np.trace(z),np.triu(z,1).sum()],float); return x/x.sum()
def label(h,a): return 'H' if h>a else 'D' if h==a else 'A'
def vec(x): return np.array([x=='H',x=='D',x=='A'],float)
def norm(x): x=np.clip(np.array(x,float),1e-8,None); return x/x.sum()
def scores(p,y):
    k=int(y.argmax()); return {'brier':float(((p-y)**2).sum()),'log_loss':float(-math.log(max(E,p[k]))),'rps':float((((np.cumsum(p)[:-1]-np.cumsum(y)[:-1])**2).sum())/2),'accuracy':float(p.argmax()==k)}
def rho_fit(hist):
    if len(hist)<10:return 0.0
    best=(0.0,-1e99)
    for r in np.linspace(-.2,.2,81):
        ll=0.0
        for q in hist:
            z=matrix(q['lh'],q['la'],float(r)); ll+=math.log(max(E,z[min(M,q['gh']),min(M,q['ga'])]))
        if ll>best[1]:best=(float(r),ll)
    return best[0]
def team_features(pm):
    if pm.empty:return {}
    for c in ['minutes','provider_rating','shots','shots_on','passes','passes_accurate','duels','duels_won']:
        if c not in pm:pm[c]=np.nan
        pm[c]=pd.to_numeric(pm[c],errors='coerce')
    pm['w']=pm.minutes.fillna(0).clip(lower=0); pm['rn']=pm.provider_rating.fillna(0)*pm.w
    g=pm.groupby(['fixture_id','team_name'],as_index=False).agg(rn=('rn','sum'),w=('w','sum'),shots=('shots','sum'),shots_on=('shots_on','sum'),passes=('passes','sum'),passes_accurate=('passes_accurate','sum'),duels=('duels','sum'),duels_won=('duels_won','sum'))
    g['rating']=g.rn/g.w.replace(0,np.nan); g['pass_accuracy']=g.passes_accurate/g.passes.replace(0,np.nan); g['duel_success']=g.duels_won/g.duels.replace(0,np.nan)
    return {(int(r.fixture_id),str(r.team_name)):{'rating':float(r.rating) if pd.notna(r.rating) else 6.5,'shots':float(r.shots or 0),'pass_accuracy':float(r.pass_accuracy) if pd.notna(r.pass_accuracy) else .75,'duel_success':float(r.duel_success) if pd.notna(r.duel_success) else .5} for r in g.itertuples(index=False)}
def mean(h,k,d):
    v=[x[k] for x in h if k in x and np.isfinite(x[k])]; return float(np.mean(v)) if v else d
def main():
    O.mkdir(parents=True,exist_ok=True); f=pd.read_csv(F); pm=pd.read_csv(P)
    f['date']=pd.to_datetime(f.date,utc=True,errors='coerce'); f.home_goals=pd.to_numeric(f.home_goals,errors='coerce'); f.away_goals=pd.to_numeric(f.away_goals,errors='coerce')
    f=f[f.status.astype(str).eq('FT')&f.date.notna()&f.home_goals.notna()&f.away_goals.notna()].copy().sort_values(['date','fixture_id']).reset_index(drop=True); f[['home_goals','away_goals']]=f[['home_goals','away_goals']].astype(int)
    feat=team_features(pm); gf=defaultdict(list); ga=defaultdict(list); elo=defaultdict(lambda:1500.); form=defaultdict(lambda:deque(maxlen=5)); oc={'H':1.,'D':1.,'A':1.}; ph=[]; rows=[]; allh=[]; alla=[]
    for i,r in f.iterrows():
        h,a=str(r.home_team),str(r.away_team); gh,gaa=int(r.home_goals),int(r.away_goals); ylab=label(gh,gaa); gr=(sum(allh)+sum(alla))/max(1,2*len(allh)) if allh else 1.35
        if i>=12:
            hgf=(sum(gf[h])+4*gr)/(len(gf[h])+4); hga=(sum(ga[h])+4*gr)/(len(ga[h])+4); agf=(sum(gf[a])+4*gr)/(len(gf[a])+4); aga=(sum(ga[a])+4*gr)/(len(ga[a])+4)
            lh=float(np.clip(gr*(hgf/gr)*(aga/gr),.2,4.5)); la=float(np.clip(gr*(agf/gr)*(hga/gr),.2,4.5)); naive=norm([oc['H'],oc['D'],oc['A']]); poi=probs(matrix(lh,la)); rho=rho_fit(ph); dc=probs(matrix(lh,la,rho))
            edge=.0042*(elo[h]-elo[a])+.45*(mean(form[h],'rating',6.5)-mean(form[a],'rating',6.5))+.035*(mean(form[h],'shots',10)-mean(form[a],'shots',10))+1.2*(mean(form[h],'pass_accuracy',.75)-mean(form[a],'pass_accuracy',.75)); win=1/(1+math.exp(-edge)); draw=float(np.clip((oc['D']/sum(oc.values()))*(.72+.55*math.exp(-abs(edge))),.12,.38)); fm=norm([(1-draw)*win,draw,(1-draw)*(1-win)])
            y=vec(ylab)
            for name,p in {'naive_base_rate':naive,'poisson_shrunk':poi,'dixon_coles_shrunk':dc,'transparent_form':fm}.items():
                rows.append({'fixture_id':int(r.fixture_id),'date':r.date.isoformat(),'home_team':h,'away_team':a,'home_goals':gh,'away_goals':gaa,'actual_outcome':ylab,'model':name,'p_home':float(p[0]),'p_draw':float(p[1]),'p_away':float(p[2]),'predicted_outcome':['H','D','A'][int(p.argmax())],'home_goal_rate':lh,'away_goal_rate':la,'dixon_coles_rho':rho if name=='dixon_coles_shrunk' else None,'training_matches_available':i,**scores(p,y)})
            ph.append({'lh':lh,'la':la,'gh':gh,'ga':gaa})
        gf[h].append(gh);ga[h].append(gaa);gf[a].append(gaa);ga[a].append(gh);oc[ylab]+=1;allh.append(gh);alla.append(gaa)
        ex=1/(1+10**((elo[a]-elo[h])/400)); sh=1 if gh>gaa else .5 if gh==gaa else 0; u=24*(math.log(abs(gh-gaa)+1)+1)*(sh-ex);elo[h]+=u;elo[a]-=u
        if feat.get((int(r.fixture_id),h)):form[h].append(feat[(int(r.fixture_id),h)])
        if feat.get((int(r.fixture_id),a)):form[a].append(feat[(int(r.fixture_id),a)])
    x=pd.DataFrame(rows)
    if x.empty:raise RuntimeError('Backtest produced no predictions')
    x.to_csv(O/'rolling_origin_predictions.csv',index=False)
    s=x.groupby('model',as_index=False).agg(matches=('fixture_id','count'),brier_score=('brier','mean'),log_loss=('log_loss','mean'),ranked_probability_score=('rps','mean'),top1_accuracy=('accuracy','mean')).sort_values('log_loss'); n=float(s[s.model.eq('naive_base_rate')].log_loss.iloc[0]);s['log_loss_skill_vs_naive']=1-s.log_loss/n;s.to_csv(O/'predictive_model_scores.csv',index=False)
    cal=[]
    for m,g in x.groupby('model'):
        conf=g[['p_home','p_draw','p_away']].max(axis=1); ok=g.predicted_outcome.eq(g.actual_outcome).astype(float); bins=pd.cut(conf,[0,.35,.45,.55,.65,.75,1],include_lowest=True); t=pd.DataFrame({'confidence':conf,'correct':ok,'bin':bins})
        for q,z in t.groupby('bin',observed=True):cal.append({'model':m,'bin':str(q),'matches':len(z),'mean_confidence':float(z.confidence.mean()),'observed_accuracy':float(z.correct.mean())})
    pd.DataFrame(cal).to_csv(O/'predictive_calibration_bins.csv',index=False)
    best=s.iloc[0]; bn=s[~s.model.eq('naive_base_rate')].iloc[0]; passed=bool(bn.log_loss<n); status={'status':'internal_rolling_origin_backtest_complete','scope':'World Cup 2026 completed 90-minute matches','protocol':'each prediction uses only earlier tournament matches','evaluation_matches_per_model':int(best.matches),'models':s.to_dict(orient='records'),'best_model_by_log_loss':str(best.model),'best_non_naive_model':str(bn.model),'non_naive_beats_naive_log_loss':passed,'internal_temporal_validation_passed':passed,'external_pre_tournament_validation_passed':False,'final_predictive_gate_passed':False,'limitations':['small tournament sample','team histories begin inside the same tournament','no betting-market benchmark','not yet based on frozen pre-World-Cup player profiles']};(O/'predictive_backtest_summary.json').write_text(json.dumps(status,ensure_ascii=False,indent=2));print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
