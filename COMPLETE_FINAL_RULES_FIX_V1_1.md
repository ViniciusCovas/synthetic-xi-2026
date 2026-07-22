# Complete Final Engine v1.1 — substitution-window rules correction

## Why v1.1 exists

The frozen FIFA World Cup 2026 event benchmark returned 9.615 substitutions per match. Complete Final Engine v1 produced 6.506, outside the preregistered absolute-error limit of 2.5.

Source inspection showed a rules implementation defect rather than an ability-calibration problem:

- the engine declared five regulation substitutions and three regulation windows;
- tactical marks existed at minutes 60, 72 and 82;
- each mark replaced only one player;
- `_perform_substitution` consumed a complete window for every individual replacement;
- ordinary matches therefore converged on three substitutions per team even though five were declared.

## Frozen correction

v1.1 uses the remaining legal substitutions and remaining legal windows to determine the size of each same-clock batch:

`ceil(remaining substitutions / remaining windows)`

With no previous injury window, the regulation sequence is therefore:

- minute 60: two players;
- minute 72: two players;
- minute 82: one player.

All replacements made in the same batch consume one window. Distinct active outfield roles are selected by lowest remaining stamina. Injury substitutions continue to consume a window and reduce the remaining legal quota. The rule is identical for Synthetic XI and Real Best XI.

## What is not changed

- no player ability;
- no team-strength coefficient;
- no selection ranking or threshold;
- no event-compatibility tolerance;
- no referee or weather multiplier;
- no use of the exploratory v1 winner probability as a calibration objective.

## Validation requirement

The v1 exploratory comparison cannot be promoted. v1.1 must pass, in order:

1. deterministic and logical tests;
2. substitution-window invariants;
3. the already-frozen World Cup 2026 event tolerances;
4. the isolated 2,000-match validation;
5. the complete preflight gate.

Only after those checks may a new confirmatory 10,000-match distribution be executed.
