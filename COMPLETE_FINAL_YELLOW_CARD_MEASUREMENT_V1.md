# Complete Final — yellow-card measurement alignment v1

## Observed mismatch

After the substitution-window rules correction, the engine produced 5.09 raw yellow cautions per match. The selected FIFA World Cup 2026 provider statistic produced 2.872 ordinary yellow cards per match. The absolute difference, 2.218, exceeded the frozen limit of 2.0.

Inspection showed a taxonomy mismatch:

- the engine increments `yellows` when a player receives a second yellow;
- the same occurrence also increments `reds` and produces a `second_yellow_red` event;
- the World Cup event benchmark classifies second-yellow events with red cards and excludes them from ordinary-yellow events;
- the preflight therefore counted a second-yellow dismissal in both the yellow and red comparison gates on the engine side, but only in the red gate on the benchmark side.

## Frozen measurement rule

The simulation itself is unchanged. Three quantities are now retained:

1. `raw_yellows`: every yellow caution shown, including a second yellow;
2. `second_yellows`: cautions that immediately generate a second-yellow dismissal;
3. `benchmark_comparable_yellows`: `raw_yellows - second_yellows`.

The yellow-card gate uses `benchmark_comparable_yellows`. The red-card gate continues to include direct reds and second-yellow dismissals.

## What remains unchanged

- foul generation;
- card probabilities;
- referee strictness;
- player discipline or ability;
- dismissals and players remaining;
- goals and match winners;
- selection rankings;
- preflight tolerances.

This is a semantic alignment between two event taxonomies, not parameter fitting. All gates must be rerun before the confirmatory distribution is authorized.
