# Definitive Real XI vs AI XI Protocol

This branch freezes a single-team experiment. No partial identification is allowed.

## Final estimand

The final study must compare exactly one deterministic Real XI with exactly one deterministic AI XI in the following slots:

`GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`.

Previous identified-set and exploratory simulations remain preserved as diagnostics only.

## Player eligibility

A real player may compete for one slot only when all requirements are met:

- at least 1,800 minutes in the frozen annual window;
- at least 900 positional minutes or 60% of classified minutes in the evaluated role;
- at least 90% relevant coverage;
- one canonical identity per `player_id`;
- validated ontology-v3 role;
- complete role-specific statistical profile;
- no unresolved high-impact human-review conflict.

Every role must contain at least 20 eligible players. The pipeline may not silently reduce the pool size.

## Ontology-v3 gate

Two independent reviewers must classify the blind packet without seeing model ranks, previous roles or simulation results. Promotion requires:

- Cohen's kappa of at least 0.80;
- at least 90% agreement for high-impact cases;
- at least 90% compatibility with official public anchors;
- zero unresolved high-impact cases after adjudication;
- at least 20 eligible candidates in every role.

Official club, league and federation sources validate plausibility but never add ranking points.

## Real XI selection

The top player in every role is selected by the frozen role-specific score. Ties are resolved in this order:

1. adjusted role score;
2. conservative score;
3. valid role minutes;
4. positional stability;
5. lower `player_id`.

One `player_id` cannot occupy two slots.

## AI XI generation

Each AI player is generated only from complete vectors of eligible real players in the same role.

The main generator:

- samples convex combinations of complete real-player profiles;
- preserves multivariate relationships by mixing whole vectors rather than independent metrics;
- enforces empirical 0.5% to 99.5% limits;
- enforces a Mahalanobis-distance envelope;
- rejects exact copies of real players;
- never assembles independent column maxima;
- optimizes the frozen role score without access to the opponent or match engine.

The generator code, role weights, seed and selected vectors must be frozen and hashed before simulation.

## Engine gate

The final match engine requires temporal holdout validation, probability calibration, Brier score, log loss, goal/shot error checks and directional confirmation from an independent goal model.

## Final simulation

Only when `final_experiment_gate_passed=true`:

- 100,000 matches;
- 50,000 in each nominal orientation;
- neutral conditions;
- master seed `20260720`;
- immutable teams, parameters and code hashes;
- full publication of teams, candidate rankings, exclusions, seeds, logs and results.

Until that gate passes, every lineup and result must be labeled diagnostic or exploratory.
