#!/usr/bin/env python3
from __future__ import annotations
import glob,json
from pathlib import Path
import numpy as np,pandas as pd
B=Path('data/lake/batches'); A=Path('data/audits'); O=Path('data/model_readiness')
def b(v): return str(v).strip().lower() in {'true','1','yes','y'}
def grid(v):
    try:
        a,c=str(v).split(':',1); return float(a),float(c)
    except Exception: return None,None
def side(x,m):
    low=x<=.5
    return ('L' if low else 'R') if m=='low_is_left' else ('R' if low else 'L') if m=='low_is_right' else ('LOW' if low else 'HIGH')
def role(r,m):
    s=str(r.get('squad_position') or ''); p=str(r.get('provider_position') or ''); q=str(r.get('lineup_position') or '')
    x=float(r.grid_col_normalized); d=float(r.row_depth); z=side(x,m)
    if s=='Goalkeeper' or p=='G' or q=='G': return 'GK'
    if s=='Defender' or p=='D' or q=='D':
        if x<=.34 or x>=.82: return f'{z}B' if z in {'L','R'} else f'FB_{z}'
        return f'{z}CB' if z in {'L','R'} else f'CB_{z}'
    if s=='Attacker' or p=='F' or q=='F':
        if x<=.34 or x>=.82: return f'{z}W' if z in {'L','R'} else f'W_{z}'
        return 'ST'
    return 'DM' if d<=.38 else 'AM' if d>=.70 else 'CM'
def main():
    O.mkdir(parents=True,exist_ok=True)
    op=O/'lateral_grid_validation.json'; orient=json.loads(op.read_text()) if op.exists() else {}
    m=orient.get('selected_mapping') if orient.get('orientation_validated') else None
    fs=[pd.read_csv(x) for x in sorted(glob.glob(str(B/'batch_*_lineups.csv.gz')))]
    ps=[pd.read_csv(x) for x in sorted(glob.glob(str(B/'batch_*_players.csv.gz')))]
    if not fs:
        (O/'eleven_role_readiness.json').write_text(json.dumps({'status':'waiting_for_lineup_data','eleven_role_gate_passed':False,'rankings_allowed':False},indent=2)); return
    l=pd.concat(fs,ignore_index=True); l=l[l.lineup_source.astype(str).eq('startXI')].drop_duplicates(['fixture_id','team_id','player_id'],keep='last')
    g=l.grid.apply(grid); l['grid_row']=g.map(lambda x:x[0]); l['grid_col']=g.map(lambda x:x[1]); l=l.dropna(subset=['grid_row','grid_col'])
    l['row_width']=l.groupby(['fixture_id','team_id','grid_row']).grid_col.transform('max'); l['grid_col_normalized']=l.grid_col/l.row_width
    l['max_row']=l.groupby(['fixture_id','team_id']).grid_row.transform('max'); l['row_depth']=((l.grid_row-2)/(l.max_row-2).clip(lower=1)).clip(0,1)
    pre=pd.read_csv(A/'annual_player_precheck.csv'); pre['player_id']=pd.to_numeric(pre.player_id,errors='coerce'); pre=pre.dropna(subset=['player_id']); pre.player_id=pre.player_id.astype(int)
    l.player_id=pd.to_numeric(l.player_id,errors='coerce'); l=l.dropna(subset=['player_id']); l.player_id=l.player_id.astype(int)
    keep=['player_id','world_cup_team','squad_position','reported_minutes','rank_entry_precheck','benchmark_precheck']; l=l.merge(pre[keep].drop_duplicates('player_id'),on='player_id',how='left')
    if ps:
        p=pd.concat(ps,ignore_index=True); p.player_id=pd.to_numeric(p.player_id,errors='coerce'); p=p.dropna(subset=['player_id']); p.player_id=p.player_id.astype(int)
        modal=p.groupby('player_id').provider_position.agg(lambda s:s.dropna().mode().iloc[0] if not s.dropna().empty else None).rename('provider_position'); l=l.merge(modal,on='player_id',how='left')
    else: l['provider_position']=None
    l['resolved_role_observation']=l.apply(role,axis=1,m=m); rows=[]
    for (pid,name),x in l.groupby(['player_id','player_name']):
        c=x.resolved_role_observation.value_counts(); i=x.iloc[0]; rows.append({'player_id':int(pid),'player_name':name,'world_cup_team':i.world_cup_team,'squad_position':i.squad_position,'resolved_role':str(c.index[0]),'role_stability':float(c.iloc[0]/c.sum()),'role_observations':int(c.sum()),'role_distribution':' | '.join(f'{k}:{v}' for k,v in c.items()),'reported_minutes':i.reported_minutes,'orientation_mapping':m})
    e=pd.DataFrame(rows); cp=O/'player_window_coverage.csv'
    if cp.exists():
        c=pd.read_csv(cp); c=c[c.window.eq('annual_current')][['player_id','fixture_endpoint_coverage','coverage_pass_80pct']].drop_duplicates('player_id'); e=e.merge(c,on='player_id',how='left')
    else: e['fixture_endpoint_coverage']=np.nan; e['coverage_pass_80pct']=False
    e['stable_role_60pct']=e.role_stability.ge(.6); e['scientific_role_eligible']=e.stable_role_60pct & e.coverage_pass_80pct.fillna(False).map(b) & e.reported_minutes.fillna(0).astype(float).ge(900); e.to_csv(O/'eleven_role_evidence.csv',index=False)
    roles=['GK','RB','RCB','LCB','LB','DM','CM','AM','RW','LW','ST']; c=e[e.scientific_role_eligible].groupby('resolved_role').size().reindex(roles,fill_value=0).rename('eligible_players').reset_index().rename(columns={'resolved_role':'role'}); c.to_csv(O/'eleven_role_candidate_counts.csv',index=False)
    enough=bool((c.eligible_players>=2).all()); status={'status':'eleven_role_resolution_evaluated','orientation_validated':bool(m),'selected_mapping':m,'players_with_role_evidence':int(len(e)),'players_stable_at_60pct':int(e.stable_role_60pct.sum()),'scientific_role_eligible_players':int(e.scientific_role_eligible.sum()),'candidate_counts':c.set_index('role').eligible_players.to_dict(),'eleven_role_gate_passed':bool(m and enough),'rankings_allowed':False}
    (O/'eleven_role_readiness.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)); print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
