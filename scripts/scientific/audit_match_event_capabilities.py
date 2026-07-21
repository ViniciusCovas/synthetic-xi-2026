#!/usr/bin/env python3
"""Strict audit of cached data for a complete knockout-final simulator."""
from __future__ import annotations

import csv, gzip, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd

ROOT=Path('data'); OUT=Path('data/audits/match_event_capability_v1'); MAX_ROWS=200_000
EXACT={
'extra_time':{'extratime_home','extratime_away'},
'penalty_shootout':{'penalty_home','penalty_away'},
'in_match_penalties':{'penalty_scored','penalty_missed','penalty_saved','penalty_committed','penalty_won'},
'yellow_cards':{'yellow','yellow_cards'},
'red_cards':{'red','red_cards'},
'fouls':{'fouls_committed','fouls_drawn'},
'substitute_appearance_flag':{'substitute','is_unused_substitute'},
'bench_lineups':{'lineup_source','lineup_position','formation'},
'referees':{'referee'},
'offsides':{'offsides'},
'event_coordinates':{'start_x','start_y','end_x','end_y'},
}
EVENT_COLS={'event_type','detail','elapsed','player_id','player_name','assist_id','assist_name','comments'}

def header(path:Path)->list[str]:
    if path.name.endswith('.csv.gz'):
        with gzip.open(path,'rt',encoding='utf-8-sig',errors='replace') as f:return next(csv.reader(f),[])
    with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:return next(csv.reader(f),[])

def sample(path:Path, cols:list[str])->pd.DataFrame:
    try:return pd.read_csv(path,usecols=cols,nrows=MAX_ROWS,low_memory=False)
    except Exception:return pd.DataFrame(columns=cols)

def status(nonnull:int,files:int,partial:bool=False)->str:
    if nonnull==0:return 'not_found'
    if partial:return 'available_partial'
    return 'available_substantial' if nonnull>=1000 else 'available_limited'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    files=[p for p in ROOT.rglob('*') if p.is_file() and (p.suffix=='.csv' or p.name.endswith('.csv.gz')) and OUT not in p.parents]
    schema=[]; evidence=defaultdict(list); event_counts=Counter(); event_detail_counts=Counter(); elapsed_values=[]
    for path in sorted(files):
        try: cols=header(path)
        except Exception as exc:
            schema.append({'path':str(path),'bytes':path.stat().st_size,'columns':'','error':f'{type(exc).__name__}:{exc}'})
            continue
        lower={c.lower():c for c in cols}
        matched=[]
        for cap,names in EXACT.items():
            hits=[lower[n] for n in names if n in lower]
            if not hits:continue
            frame=sample(path,hits); counts={c:int(frame[c].notna().sum()) for c in hits}; examples={c:frame[c].dropna().astype(str).drop_duplicates().head(10).tolist() for c in hits}
            evidence[cap].append({'path':str(path),'columns':hits,'non_null_counts':counts,'examples':examples})
            matched.append(cap)
        if EVENT_COLS.issubset(set(cols)):
            frame=sample(path,list(EVENT_COLS))
            event_counts.update(frame.event_type.dropna().astype(str).str.strip().value_counts().to_dict())
            event_detail_counts.update(frame.detail.dropna().astype(str).str.strip().value_counts().to_dict())
            elapsed_values.extend(pd.to_numeric(frame.elapsed,errors='coerce').dropna().tolist())
            evidence['event_timeline'].append({'path':str(path),'columns':sorted(EVENT_COLS),'rows':len(frame)})
            matched.append('event_timeline')
        schema.append({'path':str(path),'bytes':path.stat().st_size,'columns':'|'.join(cols),'matched_capabilities':'|'.join(sorted(set(matched))),'error':''})

    # Semantic event-level capabilities from event type/detail values.
    text_counts=Counter()
    for key,value in event_counts.items():text_counts[str(key).lower()]+=value
    for key,value in event_detail_counts.items():text_counts[str(key).lower()]+=value
    def semantic_count(words):return sum(v for k,v in text_counts.items() if any(w in k for w in words))
    semantic={
      'substitution_events':semantic_count(['subst']),
      'card_events':semantic_count(['card']),
      'goal_events':semantic_count(['goal']),
      'var_events':semantic_count(['var','cancelled','disallowed']),
      'injury_events':semantic_count(['injur','medical','treatment']),
      'corner_events':semantic_count(['corner']),
      'penalty_events':semantic_count(['penalty']),
    }
    # Exact fixture-score context.
    totals={cap:sum(sum(item.get('non_null_counts',{}).values()) for item in items) for cap,items in evidence.items()}
    matrix=[]
    for cap in ['extra_time','penalty_shootout','in_match_penalties','yellow_cards','red_cards','fouls','substitute_appearance_flag','bench_lineups','referees','offsides','event_coordinates','event_timeline']:
        partial=cap in {'substitute_appearance_flag','bench_lineups','event_coordinates'}
        n=totals.get(cap,0) if cap!='event_timeline' else sum(item.get('rows',0) for item in evidence.get(cap,[]))
        matrix.append({'capability':cap,'status':status(n,len(evidence.get(cap,[])),partial),'files_with_evidence':len(evidence.get(cap,[])),'confirmed_values_or_rows':n})
    for cap,key in [('substitution_events','substitution_events'),('var','var_events'),('injuries','injury_events'),('corners','corner_events')]:
        n=semantic[key]; matrix.append({'capability':cap,'status':status(n,1 if n else 0),'files_with_evidence':len(evidence.get('event_timeline',[])) if n else 0,'confirmed_values_or_rows':n})
    stoppage=sum(1 for v in elapsed_values if 90 < v < 120)
    matrix.append({'capability':'stoppage_time_events','status':status(stoppage,1 if stoppage else 0,True),'files_with_evidence':len(evidence.get('event_timeline',[])) if stoppage else 0,'confirmed_values_or_rows':stoppage})
    # These are explicitly absent from current schemas/semantic events.
    for cap in ['fatigue_tracking','injury_risk_model','individual_shootout_order','substitution_minute_state','var_review_outcomes']:
        matrix.append({'capability':cap,'status':'not_found','files_with_evidence':0,'confirmed_values_or_rows':0})

    pd.DataFrame(schema).to_csv(OUT/'schema_inventory.csv',index=False)
    pd.DataFrame(matrix).to_csv(OUT/'capability_matrix.csv',index=False)
    details={'event_type_counts':dict(event_counts),'event_detail_counts':dict(event_detail_counts),'semantic_event_counts':semantic,'evidence':evidence}
    (OUT/'evidence_details.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
    by={r['capability']:r for r in matrix}
    ready=all(by[k]['status']=='available_substantial' for k in ['extra_time','penalty_shootout','yellow_cards','red_cards','fouls','substitution_events','bench_lineups']) and by['individual_shootout_order']['status']!='not_found'
    status_payload={
      'status':'strict_match_event_capability_audit_completed','generated_at_utc':datetime.now(timezone.utc).isoformat(),'files_scanned':len(schema),
      'event_rows_scanned':sum(item.get('rows',0) for item in evidence.get('event_timeline',[])),'event_type_counts':dict(event_counts),'event_detail_counts':dict(event_detail_counts),
      'capabilities':{r['capability']:{k:v for k,v in r.items() if k!='capability'} for r in matrix},
      'full_knockout_final_data_ready':ready,'final_with_cards_subs_extra_time_penalties_authorized':ready,
      'key_interpretation':'Aggregate and fixture-level fields exist for several mechanisms, but a complete final remains blocked where sequence/state data are missing.',
      'next_action':'build calibrated tables for discipline and extra time; acquire/derive substitution timing, shootout taker order and player fatigue state before authorizing v3.'
    }
    (OUT/'status.json').write_text(json.dumps(status_payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Auditoria estrita de dados para uma final completa','',f"Arquivos examinados: **{len(schema)}**",f"Linhas de eventos examinadas: **{status_payload['event_rows_scanned']}**",'', '| Capacidade | Situação | Valores/linhas confirmados |','|---|---|---:|']
    for r in matrix:lines.append(f"| {r['capability']} | {r['status']} | {r['confirmed_values_or_rows']} |")
    lines += ['',f"Final completa autorizada: **{ready}**",'', 'Campos agregados não substituem uma sequência evento a evento. `available_partial` significa que o dado ajuda, mas não basta para reconstruir o estado completo da partida.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(status_payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
