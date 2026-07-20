#!/usr/bin/env python3
"""Zero-network cache rebuild and requested exports."""
import glob,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np,pandas as pd
A=Path('data/audits');M=Path('data/model_readiness');S=A/'scope_correct_coverage';H=S/'shadow_selection';O=M/'cache_rebuild'
def rd(p):
 try:return pd.read_csv(p,low_memory=False)
 except:return pd.DataFrame()
def c(d,names,default=np.nan):
 for n in names:
  if n in d:return d[n]
 return pd.Series(default,index=d.index)
def n(d,names):return pd.to_numeric(c(d,names),errors='coerce')
def t(d,names):return c(d,names,None).astype('string')
def b(s):return s.fillna(False) if s.dtype==bool else s.astype(str).str.lower().isin(['true','1','yes','y'])
def j(p):
 try:return json.loads(Path(p).read_text())
 except:return {}
def first(s):
 s=s.dropna();return s.iloc[0] if len(s) else np.nan
def load(patterns,kind):
 out=[]
 for p in sorted({z for q in patterns for z in glob.glob(q)}):
  d=rd(p)
  if d.empty or not {'fixture_id','player_id'}<=set(d):continue
  if kind=='p':
   x=pd.DataFrame({'fixture_id':n(d,['fixture_id']),'player_id':n(d,['player_id']),'team_id':n(d,['team_id']),'competition_id':n(d,['league_id','competition_id']),'season':n(d,['season']),'match_date':t(d,['match_date','fixture_date','date']),'minutes':n(d,['minutes','minutes_num']),'observed_position':t(d,['position','pos']),'source_player':p})
  else:
   src=t(d,['lineup_source','source']);start=src.fillna('').str.lower().eq('startxi')
   if 'is_starter' in d:start=start|b(d.is_starter)
   x=pd.DataFrame({'fixture_id':n(d,['fixture_id']),'player_id':n(d,['player_id']),'team_id_lineup':n(d,['team_id']),'lineup_position':t(d,['position','pos']),'is_starter':start,'source_lineup':p})
  out.append(x.dropna(subset=['fixture_id','player_id']))
 if not out:return pd.DataFrame(columns=['fixture_id','player_id'])
 d=pd.concat(out,ignore_index=True);d[['fixture_id','player_id']]=d[['fixture_id','player_id']].astype(int)
 agg={k:first for k in d.columns if k not in ['fixture_id','player_id','minutes','is_starter']}
 if 'minutes'in d:agg['minutes']='max'
 if 'is_starter'in d:agg['is_starter']='max'
 return d.groupby(['fixture_id','player_id'],as_index=False).agg(agg)
def main():
 O.mkdir(parents=True,exist_ok=True)
 pp=['data/lake/batches/*_players.csv*','data/audits/fixture_detail_pilot_players.csv'];lp=['data/lake/batches/*_lineups.csv*','data/audits/fixture_detail_pilot_lineups.csv']
 p=load(pp,'p');l=load(lp,'l');keys=pd.concat([p[['fixture_id','player_id']],l[['fixture_id','player_id']]]).drop_duplicates();z=keys.merge(p,how='left').merge(l,how='left')
 f=rd(A/'exact_fixture_inventory.csv')
 if not f.empty:
  fm=pd.DataFrame({'fixture_id':n(f,['fixture_id']),'competition_fixture':t(f,['league_name','competition','competition_name']),'competition_id_fixture':n(f,['league_id','competition_id']),'season_fixture':n(f,['season']),'date_fixture':t(f,['fixture_date','match_date','date'])}).dropna(subset=['fixture_id']);fm.fixture_id=fm.fixture_id.astype(int);z=z.merge(fm.drop_duplicates('fixture_id'),on='fixture_id',how='left')
 q=rd(M/'selection_frontier_all_candidates.csv')
 if not q.empty:
  qm=pd.DataFrame({'player_id':n(q,['player_id']),'player_name':t(q,['player_name','name']),'team':t(q,['world_cup_team','team']),'primary_position':t(q,['resolved_role','primary_position','position'])}).dropna(subset=['player_id']);qm.player_id=qm.player_id.astype(int);z=z.merge(qm.drop_duplicates('player_id'),on='player_id',how='left')
 z['team_id']=n(z,['team_id']).combine_first(n(z,['team_id_lineup']));z['competition_id']=n(z,['competition_id']).combine_first(n(z,['competition_id_fixture']));z['competition']=t(z,['competition_fixture']);z['season']=n(z,['season']).combine_first(n(z,['season_fixture']));z['match_date']=t(z,['match_date']).combine_first(t(z,['date_fixture']));z['observed_position']=t(z,['lineup_position']).combine_first(t(z,['observed_position']));z['minutes']=n(z,['minutes']);z['is_starter']=c(z,['is_starter'],False).fillna(False).astype(bool);z['detail_present']=z.minutes.fillna(0).gt(0);z['coverage_status']=np.select([z.detail_present,z.is_starter],['detailed_positive_minutes','lineup_only_startXI'],default='no_positive_minute_row')
 keep=['fixture_id','player_id','player_name','team_id','team','competition_id','competition','season','match_date','primary_position','observed_position','minutes','is_starter','detail_present','coverage_status','source_player','source_lineup']
 for x in keep:
  if x not in z:z[x]=np.nan
 z=z[keep].drop_duplicates(['fixture_id','player_id']);z.to_csv(O/'rebuilt_coverage_ledger.csv',index=False)
 ps=z.groupby('player_id',as_index=False).agg(player_name=('player_name',first),team=('team',first),primary_position=('primary_position',first),player_fixture_pairs=('fixture_id','nunique'),detailed_fixture_pairs=('detail_present','sum'),detailed_minutes=('minutes','sum'),known_startXI_pairs=('is_starter','sum'),missing_startXI_detail_pairs=('coverage_status',lambda x:int(x.eq('lineup_only_startXI').sum())))
 cov=rd(S/'player_window_coverage_scope_correct.csv')
 if not cov.empty:
  x=cov[['player_id','window','fixture_endpoint_coverage','coverage_pass_80pct','known_minute_coverage_lower_bound','known_missing_startXI_fixtures','exact_detailed_minutes']].drop_duplicates(['player_id','window']).pivot(index='player_id',columns='window');x.columns=[f'{a}_{w}'for a,w in x.columns];ps=ps.merge(x.reset_index(),on='player_id',how='left')
 ps.to_csv(O/'coverage_by_player.csv',index=False);roles=rd(H/'shadow_selection_roles.csv');roles.to_csv(O/'coverage_by_position.csv',index=False)
 u=rd(H/'shadow_selection_unresolved_players.csv');ids=set(pd.to_numeric(c(u,['player_id']),errors='coerce').dropna().astype(int));up=z[z.player_id.isin(ids)&z.is_starter&~z.detail_present];up.to_csv(O/'truly_unresolved_player_fixture_pairs.csv',index=False)
 if up.empty:uf=pd.DataFrame(columns=['fixture_id','competition','season','match_date','unresolved_player_count','positions','player_ids'])
 else:uf=up.groupby('fixture_id',as_index=False).agg(competition=('competition',first),season=('season',first),match_date=('match_date',first),unresolved_player_count=('player_id','nunique'),positions=('primary_position',lambda x:' | '.join(sorted(set(x.dropna().astype(str))))),player_ids=('player_id',lambda x:' | '.join(map(str,sorted(set(x.astype(int)))))))
 uf.to_csv(O/'truly_unresolved_priority_fixtures.csv',index=False)
 st=j(S/'scope_correct_coverage_status.json');sh=j(H/'shadow_selection_status.json');pr=j(S/'scope_correct_promotion_status.json');report={'status':'cache_only_coverage_rebuild_complete','generated_at_utc':datetime.now(timezone.utc).isoformat(),'network_calls':0,'provider_api_calls':0,'deduplication_key':['fixture_id','player_id'],'cached_player_fixture_pairs_after_deduplication':len(z),'cached_detailed_minutes_after_deduplication':float(z.minutes.fillna(0).sum()),'eligible_candidates':sh.get('eligible_candidates'),'fully_covered_both_windows':sh.get('fully_covered_both_windows'),'unresolved_players':sh.get('unresolved_players'),'truly_unresolved_player_fixture_pairs':len(up),'truly_unresolved_priority_fixtures':int(up.fixture_id.nunique()),'selection_sufficiency_gate_passed':bool(sh.get('shadow_selection_sufficiency_gate_passed',False)),'rankings_allowed':False,'real_best_xi_provisional_preserved':True,'final_rankings_generated':False,'window_rows_passing_before':st.get('window_rows_passing_before'),'window_rows_passing_after':st.get('window_rows_passing_after'),'canonical_residual_player_fixture_pairs':pr.get('residual_player_fixture_pairs'),'canonical_residual_unique_fixtures':pr.get('residual_unique_fixtures'),'roles':roles.replace({np.nan:None}).to_dict('records')}
 (O/'selection_sufficiency_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
