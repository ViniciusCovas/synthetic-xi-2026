# Open audit — externally contextualized Real XI vs AI XI v2

## Claim boundary

The result supports a comparison under the frozen 2025–2026 data, reviewed positional ontology, goalkeeper proxy, results-based Elo context adjustment, role-conditioned synthetic generator and calibrated event engine. It is not an absolute or causal claim about a physical match.

The v1 result remains preserved but is invalidated for a global-best-XI claim because its goalkeeper metric did not discriminate and its candidate table lacked explicit competition/opponent context.

## Frozen specification

- Real XI: one deterministic globally assigned team
- AI XI: one deterministic role-conditioned convex-combination team
- slots: `GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`
- master seed: `20260721`
- matches: `100000`
- paired orientations: `50000`
- neutral home advantage: `0.0`

## Frozen hashes

- Real XI SHA-256: `cb5fce1cc56b7f5dbf22b41c76a59848fa9d1f5b61a25c3eacec2fba9a0cd585`
- AI XI SHA-256: `badd74b15a7bd601241dea8f8e97d89e9d9f63aa78433336ede28f2328c655fb`
- raw match log SHA-256: `7d21b4667689463ee08b4933e1c2aff0108f774fc00caebc96087a13eb3e2526`
- calibrated core SHA-256: `03221cf9ed6f2909a2a699b975dff67926f92d0f737977af58469f4787ca32a9`
- profile engine SHA-256: `c0c2b7db48db4cfdc1eaf1b90f997856e5f4a928d8762065509062c66a8f4099`

## Gate sequence

1. Exact positional ontology resolved for all reviewed players.
2. Minimum role pools and 90% coverage passed.
3. Fixture/opponent context recovered for 4,794 of 4,794 target fixtures.
4. Strength-adjusted profiles built for 541 eligible candidate-role pairs.
5. Goalkeeper model produced 50 unique values across 50 eligible goalkeepers.
6. Elo temporal holdout passed against a naive baseline.
7. Context-gamma sensitivity passed.
8. Goalkeeper-weight sensitivity passed.
9. All eleven selected-player plausibility checks passed.
10. Real and AI teams were frozen and hashed.
11. Independent post-freeze direction check passed all jackknife and parameter checks.
12. Final v2 simulation gate opened.
13. The 100,000-match run completed and the raw log was hashed.

## Key files

### Data and context

- `data/lake/v2_fixture_context.csv.gz`
- `data/audits/external_validity_v2/candidate_match_context.csv.gz`
- `data/audits/external_validity_v2/team_elo_ratings.csv`
- `data/audits/external_validity_v2/competition_strength.csv`

### Candidate profiles and selection

- `data/audits/external_validity_v2/strength_adjusted_candidate_roles.csv`
- `data/audits/external_validity_v2/role_top10_plausibility.csv`
- `data/definitive_experiment_v2/real_xi.csv`
- `data/definitive_experiment_v2/ai_xi.csv`
- `data/definitive_experiment_v2/selected_player_plausibility.csv`
- `data/definitive_experiment_v2/team_manifest.json`

### Validation

- `data/audits/external_validity_v2/strength_model_status.json`
- `data/audits/external_validity_v2/validation_status.json`
- `data/audits/external_validity_v2/gamma_sensitivity.csv`
- `data/audits/external_validity_v2/goalkeeper_weight_sensitivity.csv`
- `data/audits/external_validity_v2/selected_player_validity_audit.csv`
- `data/audits/external_validity_v2/independent_direction_check.json`
- `data/audits/external_validity_v2/final_gate_status.json`

### Result

- `data/definitive_experiment_v2/final_simulation/summary.json`
- `data/definitive_experiment_v2/final_simulation/matches.csv.gz`
- `data/definitive_experiment_v2/final_simulation/README.md`

## Reproduction order

```bash
export PYTHONPATH=.
export API_FOOTBALL_KEY='...'

python scripts/scientific/extract_fixture_context_v2.py
python scripts/scientific/build_strength_adjusted_profiles_v2.py
python scripts/scientific/build_definitive_teams_v2.py
python scripts/scientific/validate_external_validity_v2.py
python scripts/scientific/validate_postfreeze_direction_v2.py
python scripts/scientific/build_external_validity_v2_gate.py
python scripts/scientific/run_definitive_simulation_v2.py
```

## Final outcome

- Real XI win: `39.879%`
- Draw: `22.469%`
- AI XI win: `37.652%`
- Real-minus-AI win difference: `2.227 percentage points`
- pair-cluster 95% CI: `2.061–2.393 percentage points`
- mean goal margin, Real minus AI: `+0.05574`
- independent and event-simulation direction: `REAL_XI`
