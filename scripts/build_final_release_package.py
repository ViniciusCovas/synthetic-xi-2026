#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('.'); REL=Path('data/releases/v1_0'); PAPER=Path('paper'); TABLE=PAPER/'tables'
def load(p,d=None):
 x=Path(p);return json.loads(x.read_text()) if x.exists() else ({} if d is None else d)
def esc(v): return str(v).replace('\\','\\textbackslash{}').replace('%','\\%').replace('_','\\_').replace('&','\\&')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 REL.mkdir(parents=True,exist_ok=True);TABLE.mkdir(parents=True,exist_ok=True)
 st=load('data/model_readiness/scientific_validation_status.json');sf=load('data/model_readiness/selection_sufficiency_status.json');bt=load('data/validation/predictive_backtest_summary.json');ex=load('data/validation/external_pre_tournament_holdout_summary.json');cal=load('data/simulations/calibrated_v0_3/calibration_quality.json');sen=load('data/validation/sensitivity_summary.json');nu=load('data/validation/nested_uncertainty_summary.json')
 ready=bool(st.get('arxiv_results_ready'));now=datetime.now(timezone.utc).isoformat();files=[]
 for base in ['data/model_readiness','data/validation','data/simulations/calibrated_v0_3','paper/exhibits','paper/exhibits_scientific']:
  p=Path(base)
  if not p.exists():continue
  for f in sorted(q for q in p.rglob('*') if q.is_file()):
   size=f.stat().st_size
   files.append({'path':str(f),'bytes':size,'sha256':sha(f)})
 manifest={'release':'v1.0' if ready else 'v1.0-candidate','generated_at_utc':now,'scientific_ready':ready,'claim_ceiling':st.get('current_claim_ceiling'),'blocking_gates':st.get('blocking_gates',[]),'files':files}
 (REL/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 roles=sf.get('roles',[]);role_lines=['role,required_pool_size,covered_candidates,unresolved_challengers,role_gate_passed']+[f"{r.get('role')},{r.get('required_pool_size')},{r.get('covered_candidates')},{r.get('unresolved_challengers')},{r.get('role_gate_passed')}" for r in roles];(TABLE/'selection_sufficiency_by_role.csv').write_text('\n'.join(role_lines)+'\n')
 models=bt.get('models',[]);model_lines=['model,matches,brier_score,log_loss,ranked_probability_score,top1_accuracy']+[f"{m.get('model')},{m.get('matches')},{m.get('brier_score')},{m.get('log_loss')},{m.get('ranked_probability_score')},{m.get('top1_accuracy')}" for m in models];(TABLE/'predictive_validation.csv').write_text('\n'.join(model_lines)+'\n')
 ints=nu.get('intervals',{});int_lines=['metric,mean,p025,p975']+[f"{k},{v.get('mean')},{v.get('p025')},{v.get('p975')}" for k,v in ints.items()];(TABLE/'nested_uncertainty_intervals.csv').write_text('\n'.join(int_lines)+'\n')
 md=[f"# Synthetic XI scientific release {'v1.0' if ready else 'candidate'}",'',f"Generated: {now}",f"Scientific status: **{'READY' if ready else 'BLOCKED'}**",f"Claim ceiling: {st.get('current_claim_ceiling')}",'']
 if not ready:md+=['## Remaining blockers','']+[f"- {x}" for x in st.get('blocking_gates',[])]+['']
 md+=['## Data-selection sufficiency','',f"- Eligible candidates: {sf.get('eligible_candidates')}",f"- Fully covered in both windows: {sf.get('fully_covered_both_windows')}",f"- Unresolved challengers: {sf.get('unresolved_players')}",f"- Remaining priority fixtures: {sf.get('priority_unique_fixtures')}",'','## Predictive validation','',f"- Internal best model: {bt.get('best_model_by_log_loss')}",f"- Internal temporal gate: {bt.get('internal_temporal_validation_passed')}",f"- External holdout matches: {ex.get('matches')}",f"- External log loss: {ex.get('log_loss')}",f"- External accuracy: {ex.get('top1_accuracy')}",f"- External skill vs naive: {ex.get('log_loss_skill_vs_naive')}",'','## Simulator validation','',f"- Shared tempo sigma: {cal.get('selected_shared_tempo_sigma')}",f"- Goal error: {cal.get('absolute_goal_error')}",f"- Zero-zero error: {cal.get('absolute_zero_zero_error')}",f"- Engineering gate: {cal.get('engineering_gate_passed')}",'','## Robustness and uncertainty','',f"- Sensitivity scenarios: {sen.get('scenarios')}",f"- Robust direction: {sen.get('robust_direction')}",f"- Nested parameter worlds: {nu.get('outer_parameter_worlds')}",f"- Total nested matches: {nu.get('total_matches')}",f"- P(Real XI more likely than Synthetic): {nu.get('probability_real_xi_more_likely_than_synthetic')}",'','## Interpretation','',('All declared scientific gates passed. The comparative result may be frozen and reported with the stated limitations.' if ready else 'The system remains exploratory for the final team comparison. Validated components may be reported, but rankings and the definitive comparison remain blocked.'),'']
 (PAPER/'FINAL_SCIENTIFIC_RESULTS.md').write_text('\n'.join(map(str,md)),encoding='utf-8')
 tex=['% Auto-generated; do not edit manually.',f"\\section{{Generated scientific status}}",f"The release status is \\textbf{{{esc('ready' if ready else 'blocked')}}}. The current claim ceiling is {esc(st.get('current_claim_ceiling'))}.",f"The frozen pre-tournament holdout contains {esc(ex.get('matches'))} matches, with log loss {esc(ex.get('log_loss'))} and top-1 accuracy {esc(ex.get('top1_accuracy'))}.",f"The calibrated v0.3 goal error is {esc(cal.get('absolute_goal_error'))}, and the absolute 0--0 frequency error is {esc(cal.get('absolute_zero_zero_error'))}.",f"Nested uncertainty used {esc(nu.get('outer_parameter_worlds'))} parameter worlds and {esc(nu.get('total_matches'))} simulated matches."]
 (PAPER/'generated_scientific_results.tex').write_text('\n\n'.join(tex)+'\n',encoding='utf-8')
 status={'status':'final_release_package_built','generated_at_utc':now,'scientific_ready':ready,'release_label':manifest['release'],'blocking_gates':manifest['blocking_gates'],'manifest_files':len(files)};(REL/'release_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2));print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
