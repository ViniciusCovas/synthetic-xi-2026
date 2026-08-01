# Provenance Matrix — Q1 Results Package

| Manuscript element | Frozen evidence |
|---|---|
| Scientific release status and evidence hierarchy | `SCIENTIFIC_RELEASE_OFFICIAL_V1.md` |
| Confirmatory 10,000-run championship probabilities and regulation outcomes | `data/experiments/official_v1/official/simulation_summary.json` |
| Confirmatory completion and integrity gates | `data/model_readiness/official_experiment_v1_completion.json` |
| Independent 50,000-run replication estimates | `data/experiments/official_v1_precision_replication_50000/official/simulation_summary.json` |
| Replication preregistration | `protocol/official_v1_precision_replication_50000_preregistration.json` |
| Replication completion and gates | `data/model_readiness/official_v1_precision_replication_50000_completion.json` |
| Formal comparison between 10,000 and 50,000 runs | `data/model_readiness/official_v1_precision_replication_50000_comparison.json` |
| H5, H6, and H7 confirmatory estimands | `data/experiments/official_v1/official/official_hypotheses_summary.json` |
| H5 and H6 precision-replication estimands | `data/experiments/official_v1_precision_replication_50000/official/official_hypotheses_summary.json` |
| H7 interaction cells in the precision replication | `data/experiments/official_v1_precision_replication_50000/official/official_h7_interactions.csv` |
| H7 state rates in the precision replication | `data/experiments/official_v1_precision_replication_50000/official/official_h7_state_rates.csv` |
| Nine-scenario sensitivity analysis | `data/experiments/official_v1/robustness/official_sensitivity_summary.json` and `official_sensitivity_scenarios.csv` |
| Nested structural uncertainty | `data/experiments/official_v1/robustness/official_nested_uncertainty_summary.json` |
| Release authorization and authorized hashes | `data/model_readiness/official_release_authorization_v1.json` |
| Full artifact hashes for confirmatory run | `data/experiments/official_v1/official/manifest.json` |
| Full artifact hashes for replication | `data/experiments/official_v1_precision_replication_50000/official/manifest.json` |

## Interpretation control

Any numerical value added to the manuscript must be traceable to one of the files above. Derived quantities must state the formula and preserve the distinction among confirmatory, replication, pooled precision, sensitivity, and nested-uncertainty roles.

Any change to the scientific model or estimands requires a new version and, where inferentially relevant, a new preregistration. Editorial rewording and figure formatting must not alter the frozen values.
