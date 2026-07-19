# Exact-window coverage correction

## Why a correction was required

The study preregistered two exact temporal windows and required at least 80% coverage of known minutes. An early implementation compared exact-window detailed match minutes against season-level aggregate minutes. Those quantities did not share the same scope: the aggregate could include dates and competitions outside the frozen analysis window, including competitions excluded from the principal model.

The discrepancy was detected before rankings, the final Synthetic XI vs Real XI comparison, or the arXiv results were authorized.

## Corrected definition

A player passes a window only when both conditions hold:

1. at least 80% of expected official-senior fixture endpoints were processed; and
2. detailed exact-window minutes cover at least 80% of the known minute exposure.

For an identified starting appearance without a positive-minute statistics row, missing exposure is bounded conservatively. A substitution or red-card event supplies the exit minute when available; otherwise the match maximum is used (90 minutes, or 120 for AET/PEN).

The 900-minute eligibility threshold is also evaluated using detailed minutes inside the exact annual window.

## Invariants preserved

- Annual window: 18 July 2025–17 July 2026.
- Frozen pre-World-Cup window: 11 June 2025–10 June 2026.
- Official club and senior national-team matches only.
- Friendlies and youth competitions remain excluded.
- Coverage threshold remains 80%.
- Role-stability threshold remains 60%.
- Screening retains 90% ability intervals; final estimates retain 95% intervals.
- Rankings remain blocked until every scientific gate passes.

## Audited effect

| Quantity | Former implementation | Corrected exact-window implementation |
|---|---:|---:|
| Eligible candidates | 1,060 | 971 |
| Fully covered in both windows | 631 | 935 |
| Unresolved selection challengers | 323 | 31 |
| Priority fixtures | 364 | 292 |

The reduction is not caused by lowering a threshold. It follows from removing an invalid season-level denominator and applying the 900-minute rule to the intended exact window. The correction also moved 43 window rows from passing to failing because lineup evidence showed starting appearances without detailed player statistics. Those cases remain unresolved rather than being silently accepted.

## Current residual blocker

Thirty-one players remain capable, under conservative uncertainty bounds, of altering a Top-30 positional pool or the best-XI selection. They are concentrated in five functions:

- GK: 3
- RB: 9
- CM: 1
- AM: 10
- RW: 8

Six functions already pass the corrected gate: RCB, LCB, LB, DM, LW, and ST.

The residual extraction queue contains 292 unique fixtures. It includes genuinely unprocessed fixture endpoints and bounded rechecks of fixtures where a player is identified in the startXI but lacks a detailed statistics row.

## Claim status

The correction improves internal validity and auditability but does not authorize final rankings. The project remains an exploratory, calibrated, and auditable simulation until selection sufficiency passes.
