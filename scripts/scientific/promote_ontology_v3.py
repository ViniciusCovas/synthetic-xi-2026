#!/usr/bin/env python3
"""Promote the frozen outcome-blind adjudication into ontology-v3.1 candidates."""
from __future__ import annotations
import base64, gzip, io, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path("data/audits/position_ontology_v3")
ROLE_MINUTES=ROOT/"complete_lineup_player_role_minutes.csv"
FRONTIER=Path("data/model_readiness/selection_frontier_all_candidates.csv")
OUTPUT=ROOT/"promoted_candidate_roles_uncovered.csv"
STATUS=ROOT/"ontology_v3_status.json"
ROLES=["GK","RB","RCB","LCB","LB","DM","CM","AM","RW","LW","ST"]
FAMILY={"GK":"GK","RB":"FB","LB":"FB","RCB":"CB","LCB":"CB","DM":"MID","CM":"MID","AM":"MID","RW":"WING","LW":"WING","ST":"ST"}
DIMS=["build_up","progression","creation","finishing","defending","duels","retention","goalkeeping"]
PAYLOAD="""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"""
ADJ={"review_cases":664,"initial_exact_agreement":0.667169,"initial_cohens_kappa":0.6337,"predeclared_kappa_threshold":0.80,"initial_disagreements":221,"adjudicated_disagreements":221,"unresolved_after_adjudication":0,"explicit_adjudication_complete":True,"outcome_blind_adjudication":True,"scores_rankings_and_simulation_results_used":False}

def role(v):
    if pd.isna(v): return ""
    v=str(v).strip().upper()
    return {"CBR":"RCB","CBL":"LCB","RWB":"RB","LWB":"LB","CF":"ST","CAM":"AM","CDM":"DM"}.get(v,v)

def blocked(reason,details=None):
    x={"status":"ontology_v3_1_adjudicated_promotion_blocked","generated_at_utc":datetime.now(timezone.utc).isoformat(),"reason":reason,"details":details or {},"explicit_adjudication_complete":False,"final_ontology_gate_passed":False}
    STATUS.parent.mkdir(parents=True,exist_ok=True); STATUS.write_text(json.dumps(x,ensure_ascii=False,indent=2)); print(json.dumps(x,ensure_ascii=False,indent=2))

def main():
    missing=[str(p) for p in [ROLE_MINUTES,FRONTIER] if not p.exists()]
    if missing: return blocked("required promotion inputs are missing",{"missing_files":missing})
    raw=gzip.decompress(base64.b64decode(PAYLOAD.encode("ascii")))
    adjudicated=pd.read_csv(io.BytesIO(raw))
    adjudicated["player_id"]=pd.to_numeric(adjudicated.player_id,errors="coerce")
    adjudicated=adjudicated.dropna(subset=["player_id"]).copy(); adjudicated.player_id=adjudicated.player_id.astype(int)
    adjudicated["final_role"]=adjudicated.final_role.map(role)
    if len(adjudicated)!=658 or not adjudicated.final_role.isin(ROLES).all(): return blocked("embedded adjudication failed validation",{"rows":len(adjudicated)})
    adjudicated["annual_minutes"]=pd.to_numeric(adjudicated.annual_minutes,errors="coerce").fillna(0)
    adjudicated["final_family"]=adjudicated.final_role.map(FAMILY)
    adjudicated=adjudicated.sort_values(["player_id","final_role"]).drop_duplicates(["player_id","final_role"])

    rm=pd.read_csv(ROLE_MINUTES,low_memory=False); rm["player_id"]=pd.to_numeric(rm.player_id,errors="coerce"); rm=rm.dropna(subset=["player_id"]); rm.player_id=rm.player_id.astype(int); rm["role"]=rm.role.map(role); rm=rm[rm.role.isin(ROLES)]
    for c in ["role_minutes","role_observations"]: rm[c]=pd.to_numeric(rm[c],errors="coerce").fillna(0)
    exact=rm.groupby(["player_id","role"],as_index=False).agg(exact_role_minutes=("role_minutes","sum"),exact_role_observations=("role_observations","sum")).rename(columns={"role":"final_role"})
    exact["exact_role_share"]=exact.exact_role_minutes/exact.groupby("player_id").exact_role_minutes.transform("sum").replace(0,pd.NA)
    fam=rm.assign(family=rm.role.map(FAMILY)).groupby(["player_id","family"],as_index=False).agg(family_minutes=("role_minutes","sum"),family_observations=("role_observations","sum"))
    fam["family_share"]=fam.family_minutes/fam.groupby("player_id").family_minutes.transform("sum").replace(0,pd.NA)
    out=adjudicated.merge(exact,on=["player_id","final_role"],how="left").merge(fam,left_on=["player_id","final_family"],right_on=["player_id","family"],how="left")
    for c in ["exact_role_minutes","exact_role_observations","exact_role_share","family_minutes","family_observations","family_share"]: out[c]=pd.to_numeric(out[c],errors="coerce").fillna(0)

    fr=pd.read_csv(FRONTIER,low_memory=False); fr["player_id"]=pd.to_numeric(fr.player_id,errors="coerce"); fr=fr.dropna(subset=["player_id"]); fr.player_id=fr.player_id.astype(int); fr=fr.sort_values("player_id").drop_duplicates("player_id")
    cols=[c for c in ["player_id","player_name","world_cup_team","squad_position","overall","uncertainty","conservative_score",*DIMS,"identity_rows_before_deduplication","high_impact_current_release"] if c in fr.columns]
    out=out.merge(fr[cols],on="player_id",how="left")
    out["exact_window_total_minutes"]=out.annual_minutes; out["human_review_resolved"]=True; out["review_resolved"]=True; out["assignment_source"]="explicit_outcome_blind_adjudication"
    out["overall_final"]=pd.to_numeric(out.get("overall"),errors="coerce"); out["conservative_score_final"]=pd.to_numeric(out.get("conservative_score"),errors="coerce")
    for c in ["uncertainty",*DIMS]: out[c]=pd.to_numeric(out.get(c),errors="coerce")
    profile=["overall_final","conservative_score_final","uncertainty",*DIMS]
    out["complete_role_specific_profile"]=out[profile].notna().all(axis=1)
    out["final_role_eligible_before_coverage"]=out.exact_window_total_minutes.ge(1800)&out.family_minutes.ge(900)&out.family_observations.ge(3)&out.complete_role_specific_profile
    out["eligibility_exclusion_reason"]=""
    out.loc[out.exact_window_total_minutes.lt(1800),"eligibility_exclusion_reason"]+="total_minutes_lt_1800;"
    out.loc[out.family_minutes.lt(900),"eligibility_exclusion_reason"]+="positional_family_minutes_lt_900;"
    out.loc[out.family_observations.lt(3),"eligibility_exclusion_reason"]+="positional_family_observations_lt_3;"
    out.loc[~out.complete_role_specific_profile,"eligibility_exclusion_reason"]+="incomplete_role_specific_profile;"
    out=out.sort_values(["final_role","player_id"]); OUTPUT.parent.mkdir(parents=True,exist_ok=True); out.to_csv(OUTPUT,index=False)
    eligible=out[out.final_role_eligible_before_coverage]
    counts=eligible.groupby("final_role").player_id.nunique().reindex(ROLES,fill_value=0).astype(int).to_dict()
    gate=all(v>=20 for v in counts.values())
    status={"status":"ontology_v3_1_adjudicated_candidate_roles_promoted","generated_at_utc":datetime.now(timezone.utc).isoformat(),**ADJ,"protocol_deviation_recorded":True,"provider_linked_review_cases":658,"review_cases_without_provider_player_id":6,"promoted_candidate_role_pairs":len(out),"eligible_candidate_role_pairs_before_coverage":int(out.final_role_eligible_before_coverage.sum()),"final_eligible_candidates_by_role":counts,"minimum_20_candidates_each_final_role_before_coverage":gate,"complete_profile_required":True,"family_experience_rule":">=900 complete-lineup minutes and >=3 observations in frozen positional family","final_ontology_gate_passed":gate,"final_team_construction_allowed_before_coverage":gate,"promoted_candidate_table":str(OUTPUT),"next_action":"recalculate 90% exact-window coverage for every promoted candidate-role pair" if gate else "repair deficient role pools without changing adjudicated slots"}
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)); print(json.dumps(status,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
