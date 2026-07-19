#!/usr/bin/env python3
"""Evaluate exact coverage only for players who can affect the final comparison.

The scientific estimand does not require every eligible squad player to reach 80%.
The gate is evaluated for: (a) preliminary benchmark candidates and (b) the top
30 players per resolved functional role, which contains every Top-10/20/30 avatar
member used in sensitivity analysis. Rankings remain blocked until these relevant
players pass, or are transparently excluded and teams are rebuilt.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

OUT=Path('data/model_readiness')

def as_bool(v): return str(v).strip().lower() in {'true','1','yes','y'}

def main():
    coverage=pd.read_csv(OUT/'player_window_coverage.csv')
    roles=pd.read_csv(OUT/'eleven_role_evidence.csv')
    totals=pd.read_csv(OUT/'partial_annual_current_totals.csv')
    precheck=pd.read_csv('data/audits/annual_player_precheck.csv')
    metric_cols=['player_id','minutes_num','goals_total','assists','passes_key','shots_on','tackles_total','interceptions','duels_won']
    for c in metric_cols:
        if c not in totals.columns: totals[c]=0.0
    base=roles.merge(totals[metric_cols].copy(),on='player_id',how='left')
    for c in metric_cols[1:]:
        base[c]=pd.to_numeric(base[c],errors='coerce').fillna(0.0)
    m=(base['minutes_num']/90).clip(lower=1e-9)
    base['transparent_score']=(
        5*(base['goals_total']/m)+3*(base['assists']/m)+1.2*(base['passes_key']/m)+
        .8*(base['shots_on']/m)+.7*(base['tackles_total']/m)+.9*(base['interceptions']/m)+.25*(base['duels_won']/m)
    )
    role_pool=(base.loc[base['role_stability'].ge(.60)&base['resolved_role'].notna()]
               .sort_values(['resolved_role','transparent_score','minutes_num'],ascending=[True,False,False])
               .groupby('resolved_role',group_keys=False).head(30))
    benchmark_ids=set(precheck.loc[precheck['benchmark_precheck'].map(as_bool),'player_id'].astype(int))
    avatar_ids=set(role_pool['player_id'].astype(int))
    relevant=benchmark_ids|avatar_ids
    ledger=coverage.loc[coverage['player_id'].astype(int).isin(relevant)].copy()
    ledger['candidate_type']=ledger['player_id'].astype(int).map(lambda x:'benchmark_and_avatar' if x in benchmark_ids and x in avatar_ids else 'benchmark' if x in benchmark_ids else 'avatar_top30_pool')
    ledger.to_csv(OUT/'candidate_window_coverage.csv',index=False)
    rows=[]
    for window,sub in ledger.groupby('window'):
        passed=sub['coverage_pass_80pct'].map(as_bool)
        rows.append({'window':window,'relevant_players':int(sub['player_id'].nunique()),'players_passing_80pct':int(sub.loc[passed,'player_id'].nunique()),'pass_rate':float(passed.mean()),'missing_fixture_endpoints':int(pd.to_numeric(sub['missing_fixture_endpoints'],errors='coerce').fillna(0).sum())})
    current=ledger.loc[ledger['window'].eq('annual_current'),'coverage_pass_80pct'].map(as_bool)
    pre=ledger.loc[ledger['window'].eq('pre_world_cup'),'coverage_pass_80pct'].map(as_bool)
    status={'status':'candidate_relevant_coverage_evaluated','estimand':'final Real XI plus every Top-10/20/30 avatar candidate','benchmark_candidates':len(benchmark_ids),'avatar_top30_candidates':len(avatar_ids),'relevant_union':len(relevant),'windows':rows,'candidate_coverage_gate_passed':bool(len(current) and current.all() and len(pre) and pre.all()),'policy':'players below 80% must be targeted for extraction or excluded before rebuilding final teams','rankings_allowed':False}
    (OUT/'candidate_coverage_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
