# Definitive Real XI vs AI XI Protocol

This branch freezes a single-team experiment. No partial identification is allowed.

## Final estimand

The final study must compare exactly one deterministic Real XI with exactly one deterministic AI XI in the following slots:

`GK, RB, RCB, LCB, LB, DM, CM, AM, RW, LW, ST`.

Previous identified-set and exploratory simulations remain preserved as diagnostics only.

## Player eligibility

A real player may compete for a slot only when all requirements are met:

- at least 1,800 minutes in the frozen annual window;
- at least 900 minutes and three complete-lineup observations in the slot's positional family;
- the exact slot is supported by two independent blind reviewers or explicit adjudication;
- at least 90% relevant coverage in both frozen windows;
- one canonical identity per `player_id`;
- complete role-specific statistical profile;
- no unresolved high-impact review conflict.

The positional families are frozen as follows:

- `GK`: `GK`;
- `FB`: `RB, LB`;
- `CB`: `RCB, LCB`;
- `MID`: `DM, CM, AM`;
- `WING`: `RW, LW`;
- `ST`: `ST`.

Family minutes are used only to establish that a player has substantial experience in the relevant tactical line. The two blind reviewers resolve the exact slot. This prevents a circular rule in which the automatic ontology would have to be accepted before it could be independently audited.

A player may be eligible for a maximum of two reviewed slots, but one `player_id` may occupy only one slot in the final XI.

Every final slot must contain at least 20 reviewed, eligible and fully covered candidates. The pipeline may not silently reduce the pool size.

## Ontology-v3.1 gate

The blind packet is built from players with at least 1,800 annual minutes and at least 900 minutes in one positional family, plus preregistered high-impact challengers. It does not require 20 automatically assigned exact-role primaries before review.

Two independent reviewers classify the packet without seeing model ranks, previous roles or simulation results. The original reliability target is:

- Cohen's kappa of at least 0.80 for primary slots;
- at least 90% agreement for high-impact cases;
- at least 90% compatibility with official public anchors;
- zero unresolved high-impact cases after adjudication;
- at least 20 reviewed eligible candidates in every final slot.

Official club, league and federation sources validate plausibility but never add ranking points.

### Recorded adjudication amendment — 2026-07-21

The two independent classifications produced exact agreement of 0.667 and Cohen's kappa of 0.634. These statistics remain frozen and must be reported; post-adjudication consensus does not replace them.

All 221 disagreements were resolved through an outcome-blind adjudication that excluded player scores, rankings, selected teams, synthetic vectors and simulation results. Exact-slot promotion may therefore proceed through the amended adjudication pathway only when:

1. every disagreement has an explicit final slot;
2. zero cases remain unresolved;
3. the original agreement and kappa remain reported as reliability diagnostics;
4. each final slot has at least 20 eligible candidates before and after coverage validation;
5. all other frozen thresholds, role weights, seeds, engine gates and simulation rules remain unchanged.

Use of this pathway must be recorded as a protocol deviation. It does not imply that the original kappa threshold passed.

## Real XI selection

The Real XI is selected by a global one-to-one assignment across the eleven slots. The optimizer maximizes the frozen sum of role-specific adjusted scores subject to:

- exactly one player per slot;
- no player occupying two slots;
- only reviewed, eligible and fully covered candidate-role pairs;
- deterministic tie-breaking.

For equal total team utility, ties are resolved by:

1. higher sum of conservative scores;
2. higher sum of valid annual minutes;
3. higher sum of reviewed-family minutes;
4. lexicographically lower ordered `player_id` vector.

A greedy slot-by-slot selection is not permitted because it can assign a versatile player suboptimally.

## AI XI generation

Each AI player is generated only from complete vectors of eligible real players approved for the same reviewed slot.

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
