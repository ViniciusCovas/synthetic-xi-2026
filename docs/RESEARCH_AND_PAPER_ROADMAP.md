# Synthetic XI 2026 — Research and Paper Completion Roadmap

## Current scientific status

The project currently contains an auditable event-based simulator, calibrated against completed 90-minute World Cup 2026 matches, plus a complete ledger of 10,000 simulated matches. The engine is computationally reproducible and its aggregate event volume is calibrated. The final team comparison is not yet authorized because annual player coverage, definitive positional roles, and out-of-sample predictive validity remain incomplete.

## Publication strategy

### arXiv v1

Target: a complete preprint of approximately 8,000–10,000 words, excluding references and appendices.

Minimum evidence package:

1. Data provenance and coverage audit.
2. Formal definition of the annual and pre-World-Cup windows.
3. Definitive player eligibility and eleven-role resolution.
4. Synthetic-avatar construction with Top 10/20/30 sensitivity.
5. Real-player benchmark selection with uncertainty.
6. Observed calibration targets.
7. Complete 10,000-match Monte Carlo ledger and convergence.
8. Baseline models: independent Poisson, Dixon–Coles and Elo-strength baseline.
9. Out-of-sample backtest.
10. Nested uncertainty analysis.
11. Ablations and failure cases.
12. Communication analysis of probabilistic replay and narrative framing.

### Journal version

The Q1 submission should add a human-subject communication experiment comparing:

- probability table versus animated replay;
- neutral, emotional and analytical narration;
- “AI simulation” versus “statistical model” labels.

Primary outcomes: perceived realism, credibility, uncertainty comprehension, trust, attributed agency, emotional response and intention to share.

## Scientific gates

### Gate A — Data completion

- At least 80% detailed coverage for each included player and temporal window.
- Minimum 900 minutes for ranking eligibility.
- Minimum 1,800 minutes and 15 appearances for the main real-player benchmark.
- All exclusions reported by country, competition and role.

### Gate B — Positional validity

- Eleven final roles: GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST.
- At least 60% stable positional evidence.
- Provider lateral orientation empirically validated before assigning left/right.

### Gate C — Model validity

- Comparison against simple baselines.
- Out-of-sample validation with no temporal leakage.
- Calibration plots and proper scoring rules.
- Sensitivity to eligibility thresholds, Top N and temporal decay.

### Gate D — Uncertainty

- Aleatory match variation.
- Epistemic uncertainty in player skills, competition strength and model weights.
- Nested Monte Carlo with intervals over the final win probabilities.

### Gate E — Communication claims

The current 2D animation must remain labelled as probabilistic event choreography. It cannot be described as reconstructed tracking. Claims about trust, realism or communication effects require a human-subject study.

## Immediate implementation order

1. Continue quota-safe adaptive extraction.
2. Calculate exact per-player coverage in both temporal windows.
3. Validate the provider grid and resolve eleven roles.
4. Freeze definitive annual and pre-World-Cup datasets.
5. Fit a hierarchical player-skill model.
6. Implement Poisson, Dixon–Coles and Elo baselines.
7. Run rolling-origin out-of-sample backtests.
8. Run Top 10/20/30 and threshold sensitivity analyses.
9. Run nested Monte Carlo and final simulations.
10. Replace exploratory results in the paper.
11. Expand the manuscript with final tables, figures and appendices.
12. Deposit arXiv v1, then prepare the communication experiment for a Q1 journal.

## Multi-agent spatial extension

This is a second methodological layer, not a prerequisite for the event-simulation paper.

Recommended hybrid architecture:

- macro engine: possessions, score, fatigue, cards, substitutions and event outcomes;
- micro engine: 5–12 second spatial segments with 22 agents and the ball at 10 Hz;
- tactical controller: formation, width, line height, pressure and risk;
- role-conditioned agents: target zones and responsibilities;
- learned residual: graph-temporal model trained on open tracking data;
- physical constraints: velocity, acceleration, turning radius, offside and pitch limits.

Validation must include ADE/FDE, joint trajectory error, team width/length, line spacing, pitch control, tactical coherence and blinded expert evaluation.
