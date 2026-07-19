# Methodology correction: exact-window coverage denominator

Date frozen: 19 July 2026, before final rankings and before the Synthetic XI vs Real XI comparison were authorized.

## Problem identified

The v0.5 protocol requires official matches inside two exact windows and at least 80% coverage of known minutes. The first implementation used season-level aggregate minutes returned by the provider as the denominator for the annual window.

That denominator was not scope-compatible because it could contain minutes outside the exact dates and from competitions deliberately excluded from the principal model. The original coverage audit itself stated that season aggregates were intended to map the universe, not to produce final exact-window rankings.

## Correction

No eligibility threshold is relaxed. Coverage is now evaluated with two simultaneous conditions:

1. At least 80% of expected official-senior fixture endpoints in the exact window were processed.
2. A conservative lower bound of at least 80% for known exact-window minutes:

   observed detailed minutes /
   (observed detailed minutes + 90 minutes for every identified startXI appearance without a detailed player row).

The 90-minute term is deliberately conservative. It overstates, rather than understates, the potentially missing minutes for a starter who may have been substituted.

## Exact-window eligibility

The 900-minute ranking threshold is evaluated with detailed minutes observed inside the exact annual window, not with season aggregates.

## Invariants

- Windows remain 18 July 2025–17 July 2026 and 11 June 2025–10 June 2026.
- Friendlies and youth competitions remain excluded from the principal model.
- The 80% coverage threshold remains unchanged.
- The 60% role-stability threshold remains unchanged.
- Screening retains 90% ability intervals; final estimates retain 95% intervals.
- Rankings remain blocked until all scientific gates pass.

## Audit trail

The former ledger is preserved before promotion. Diagnostic and shadow outputs are stored under:

- `data/audits/cache_reconciliation/`
- `data/audits/scope_correct_coverage/`

This correction was made before any final ranking, final team comparison, or arXiv result was authorized.
