#!/usr/bin/env python3
"""Generate paper-ready exhibits from scientific validation outputs."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
O=Path('paper/exhibits_scientific')
def save(n):plt.tight_layout();plt.savefig(O/n,dpi=240,bbox_inches='tight');plt.close()
def main():
    O.mkdir(parents=True,exist_ok=True);made=[]
    p=Path('data/model_readiness/player_window_coverage.csv')
    if p.exists():
        x=pd.read_csv(p);x.to_csv(O/'table_05_player_window_coverage.csv',index=False);plt.figure(figsize=(8.6,5))
        for w,g in x.groupby('window'):
            v=pd.to_numeric(g.fixture_endpoint_coverage,errors='coerce').dropna().sort_values();
            if len(v):plt.plot(v*100,np.arange(1,len(v)+1)/len(v)*100,label=w.replace('_',' '))
        plt.axvline(80,ls='--');plt.xlabel('Processed eligible fixture endpoints (%)');plt.ylabel('Cumulative share of eligible players (%)');plt.title('Per-player coverage by temporal window');plt.grid(alpha=.25);plt.legend(frameon=False);save('figure_04_player_coverage_ecdf.png');made.append('figure_04_player_coverage_ecdf.png')
    p=Path('data/model_readiness/eleven_role_candidate_counts.csv')
    if p.exists():
        x=pd.read_csv(p);x.to_csv(O/'table_06_eleven_role_candidates.csv',index=False);plt.figure(figsize=(9.2,4.8));plt.bar(x.role,x.eligible_players);plt.axhline(2,ls='--');plt.xlabel('Definitive role');plt.ylabel('Covered, stable candidates');plt.title('Candidate depth after coverage and role-stability gates');plt.grid(axis='y',alpha=.25);save('figure_05_role_candidate_depth.png');made.append('figure_05_role_candidate_depth.png')
    p=Path('data/validation/predictive_model_scores.csv')
    if p.exists():
        x=pd.read_csv(p).sort_values('log_loss',ascending=False);x.to_csv(O/'table_07_predictive_model_scores.csv',index=False);plt.figure(figsize=(8.8,5));plt.barh(x.model,x.log_loss);plt.xlabel('Rolling-origin log loss (lower is better)');plt.title('Predictive baselines without future-match leakage');plt.grid(axis='x',alpha=.25);save('figure_06_predictive_log_loss.png');made.append('figure_06_predictive_log_loss.png')
    p=Path('data/validation/predictive_calibration_bins.csv')
    if p.exists():
        x=pd.read_csv(p);x.to_csv(O/'table_08_predictive_calibration.csv',index=False);plt.figure(figsize=(6.4,6))
        for m,g in x.groupby('model'):
            g=g.sort_values('mean_confidence');plt.plot(g.mean_confidence*100,g.observed_accuracy*100,marker='o',label=m)
        plt.plot([0,100],[0,100],ls='--');plt.xlabel('Mean predicted confidence (%)');plt.ylabel('Observed accuracy (%)');plt.title('Reliability of rolling-origin probabilities');plt.grid(alpha=.25);plt.legend(frameon=False,fontsize=8);save('figure_07_predictive_reliability.png');made.append('figure_07_predictive_reliability.png')
    p=Path('data/validation/topn_chemistry_sensitivity.csv')
    if p.exists():
        x=pd.read_csv(p);x.to_csv(O/'table_09_sensitivity.csv',index=False);plt.figure(figsize=(9,5.2))
        for s,g in x.groupby('scenario'):
            g=g.sort_values('top_n');plt.plot(g.top_n,g.synthetic_win_probability*100,marker='o',label=s.replace('_',' '))
        plt.xlabel('Avatar pool size (Top N)');plt.ylabel('Synthetic XI win probability (%)');plt.title('Sensitivity to pool size and coordination');plt.grid(alpha=.25);plt.legend(frameon=False,fontsize=8);save('figure_08_topn_coordination_sensitivity.png');made.append('figure_08_topn_coordination_sensitivity.png')
    p=Path('data/validation/nested_uncertainty_worlds.csv')
    if p.exists():
        x=pd.read_csv(p);x.to_csv(O/'table_10_nested_uncertainty_worlds.csv',index=False);cols=['synthetic_win_probability','draw_probability','real_win_probability'];labels=['Synthetic win','Draw','Real XI win'];means=[x[c].mean()*100 for c in cols];lo=[(x[c].mean()-x[c].quantile(.025))*100 for c in cols];hi=[(x[c].quantile(.975)-x[c].mean())*100 for c in cols];plt.figure(figsize=(7.8,5));plt.errorbar(labels,means,yerr=[lo,hi],fmt='o',capsize=6);plt.ylabel('Probability across parameter worlds (%)');plt.title('Nested Monte Carlo uncertainty');plt.grid(axis='y',alpha=.25);save('figure_09_nested_uncertainty.png');made.append('figure_09_nested_uncertainty.png')
    a=Path('data/simulations/calibrated_v0_2/simulation_summary.json');b=Path('data/simulations/calibrated_v0_3/simulation_summary.json');c=Path('data/simulations/calibration/world_cup_2026_targets.json')
    if a.exists() and b.exists() and c.exists():
        v2=json.loads(a.read_text());v3=json.loads(b.read_text());t=json.loads(c.read_text());rows=[]
        for label,key,target in [('Goals','mean_total_goals','mean_goals_per_match'),('Shots','mean_total_shots','mean_shots_per_match'),('Shots on target','mean_total_shots_on_target','mean_shots_on_target_per_match'),('0–0 rate','zero_zero_probability','zero_zero_rate')]:rows.append({'metric':label,'observed':t[target],'v0_2':v2[key],'v0_3':v3[key],'v0_2_absolute_error':abs(v2[key]-t[target]),'v0_3_absolute_error':abs(v3[key]-t[target])})
        x=pd.DataFrame(rows);x.to_csv(O/'table_11_v02_v03_calibration.csv',index=False);z=np.arange(len(x));w=.25;plt.figure(figsize=(9.2,5));plt.bar(z-w,x.observed,w,label='Observed');plt.bar(z,x.v0_2,w,label='v0.2');plt.bar(z+w,x.v0_3,w,label='v0.3');plt.xticks(z,x.metric);plt.ylabel('Metric value');plt.title('Calibration before and after shared tempo');plt.grid(axis='y',alpha=.25);plt.legend(frameon=False);save('figure_10_v02_v03_calibration.png');made.append('figure_10_v02_v03_calibration.png')
    p=Path('data/model_readiness/scientific_validation_status.json')
    if p.exists():
        s=json.loads(p.read_text());pd.DataFrame([{'gate':k,'passed':v} for k,v in s['gates'].items()]).to_csv(O/'table_12_scientific_validation_gates.csv',index=False)
    (O/'README.md').write_text('# Scientific validation exhibits\n\nGenerated automatically from versioned outputs.\n\n'+'\n'.join(f'- {x}' for x in made)+'\n\nFinal claims remain controlled by readiness gates.\n')
if __name__=='__main__':main()
