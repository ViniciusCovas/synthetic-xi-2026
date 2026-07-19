#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
O=Path('data/model_readiness'); R=['GK','RB','RCB','LCB','LB','DM','CM','AM','RW','LW','ST']; Z=1.6448536269514722
def b(v): return str(v).strip().lower() in {'true','1','yes','y'}
def main():
 O.mkdir(parents=True,exist_ok=True); fp=O/'selection_frontier_all_candidates.csv'; cp=O/'player_window_coverage.csv'; pp=O/'coverage_priority_fixtures.csv'
 if not fp.exists() or not cp.exists():
  s={'status':'waiting_for_selection_candidates_or_coverage','selection_sufficiency_gate_passed':False};(O/'selection_sufficiency_status.json').write_text(json.dumps(s,indent=2));return
 x=pd.read_csv(fp)
 for c in ['player_id','reported_minutes','role_observations','role_stability','overall','uncertainty','conservative_score']: x[c]=pd.to_numeric(x.get(c),errors='coerce')
 x=x.dropna(subset=['player_id','resolved_role']);x.player_id=x.player_id.astype(int);x=x.sort_values(['player_id','role_observations','role_stability'],ascending=[True,False,False]).drop_duplicates('player_id');x=x[x.resolved_role.isin(R)&x.reported_minutes.fillna(0).ge(900)].copy()
 c=pd.read_csv(cp);c.player_id=pd.to_numeric(c.player_id,errors='coerce');c=c.dropna(subset=['player_id']);c.player_id=c.player_id.astype(int);c.coverage_pass_80pct=c.coverage_pass_80pct.map(b)
 for w in ['annual_current','pre_world_cup']:
  z=c[c.window.eq(w)].sort_values('fixture_endpoint_coverage').drop_duplicates('player_id',keep='last')[['player_id','fixture_endpoint_coverage','coverage_pass_80pct','missing_fixture_endpoints']].rename(columns={'fixture_endpoint_coverage':f'cov_{w}','coverage_pass_80pct':f'pass_{w}','missing_fixture_endpoints':f'miss_{w}'})
  x=x.merge(z,on='player_id',how='left');x[f'pass_{w}']=x[f'pass_{w}'].fillna(False).map(b);x[f'cov_{w}']=pd.to_numeric(x[f'cov_{w}'],errors='coerce').fillna(0);x[f'miss_{w}']=pd.to_numeric(x[f'miss_{w}'],errors='coerce').fillna(0).astype(int)
 x['covered']=x.pass_annual_current&x.pass_pre_world_cup;x['uncertainty']=x.uncertainty.fillna(.25).clip(.025,.35);x['lo90']=(x.overall-Z*x.uncertainty).clip(0,1);x['hi90']=(x.overall+Z*x.uncertainty).clip(0,1);x['stable']=x.role_stability.fillna(0).ge(.6)&x.role_observations.fillna(0).ge(3)&x.overall.notna();x['rank']=np.nan;x['urank']=np.nan;x['needed']=False;x['reason']='outside_decision_frontier';rs=[]
 for role in R:
  idx=x.index[x.resolved_role.eq(role)];g=x.loc[idx].copy()
  if g.empty: rs.append({'role':role,'required_pool_size':0,'covered_candidates':0,'unresolved_challengers':0,'role_gate_passed':False});continue
  q=g.sort_values(['conservative_score','reported_minutes'],ascending=[False,False]);x.loc[q.index,'rank']=range(1,len(q)+1);u=g.sort_values(['hi90','reported_minutes'],ascending=[False,False]);x.loc[u.index,'urank']=range(1,len(u)+1);g=x.loc[idx].copy();st=g[g.stable];k=min(30,len(st));cv=st[st.covered].sort_values('lo90',ascending=False);en=len(cv)>=k and k>0;tt=float(cv.iloc[k-1].lo90) if en else -1;bt=float(cv.iloc[0].lo90) if len(cv) else -1;ids=set();why={}
  under=g[~g.covered]
  if not en:
   for r in under.sort_values(['rank','hi90'],ascending=[True,False]).head(max(k-len(cv),5)).itertuples(): ids.add(int(r.player_id));why[int(r.player_id)]='covered_pool_shortage'
  for r in under.itertuples():
   pid=int(r.player_id);hi=float(r.hi90) if pd.notna(r.hi90) else 1.;rk=int(r.rank) if pd.notna(r.rank) else 9999;ur=int(r.urank) if pd.notna(r.urank) else 9999
   if r.stable and en and hi>=tt: ids.add(pid);why[pid]='upper90_can_enter_top30'
   if r.stable and len(cv) and hi>=bt: ids.add(pid);why[pid]='upper90_can_enter_real_xi'
   if r.stable and rk<=k+5: ids.add(pid);why.setdefault(pid,'top35_guardrail')
   if not r.stable and (ur<=15 or rk<=15): ids.add(pid);why[pid]='high_ability_role_stabilization'
  m=x.player_id.isin(ids);x.loc[m,'needed']=True;x.loc[m,'reason']=x.loc[m,'player_id'].map(why);rs.append({'role':role,'eligible_candidates':len(g),'stable_candidates':len(st),'required_pool_size':k,'covered_candidates':len(cv),'unresolved_challengers':len(ids),'role_gate_passed':bool(en and not ids)})
 un=x[x.needed].copy();x.to_csv(O/'selection_sufficiency_all_players.csv',index=False);un.to_csv(O/'selection_sufficiency_unresolved_players.csv',index=False)
 if pp.exists() and not un.empty:
  p=pd.read_csv(pp);p.player_id=pd.to_numeric(p.player_id,errors='coerce');p=p.dropna(subset=['player_id']);p.player_id=p.player_id.astype(int);p=p[p.player_id.isin(set(un.player_id))].copy();p['selection_resolution_reason']=p.player_id.map(un.set_index('player_id').reason.to_dict())
 else:p=pd.DataFrame(columns=['player_id','fixture_id','window','selection_resolution_reason'])
 p.to_csv(O/'selection_sufficiency_priority_fixtures.csv',index=False);rf=pd.DataFrame(rs);gate=bool(len(rf) and rf.role_gate_passed.all() and un.empty);s={'status':'selection_sufficiency_evaluated','screening_interval':'90% ability interval; final estimates retain 95% intervals','eligible_candidates':len(x),'fully_covered_both_windows':int(x.covered.sum()),'unresolved_players':int(un.player_id.nunique()),'priority_player_fixture_pairs':len(p),'priority_unique_fixtures':int(p.fixture_id.nunique()) if len(p) else 0,'roles':rs,'selection_sufficiency_gate_passed':gate,'rankings_allowed':gate,'policy':'Exclude a sub-covered player only when its 90% upper bound cannot alter the covered Top-30 or best-XI set and it is outside declared guardrails.'};(O/'selection_sufficiency_status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2));print(json.dumps(s,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
