# Scientific validity notice

Date: 2026-07-21

The completed 100,000-match run is preserved as a fully reproducible computational artifact, but it is **not publication-ready as a global-best-XI result**.

A post-result plausibility audit identified two material external-validity failures:

1. the eligible goalkeeper pool has an effectively constant `goalkeeping` score (`0.9996646498695336` across the inspected eligible goalkeepers), so goalkeeper selection is driven mainly by secondary dimensions rather than a discriminative goalkeeper model;
2. the final candidate table and team-selection objective contain no explicit club/league/opponent-strength adjustment, allowing statistically dominant performances from materially different competition environments to be treated as directly exchangeable.

The surprising selection of Sipho Chaine at goalkeeper and Mohammed Abu Al-Shamat at right-back exposed these weaknesses. Both are real and valid professional players; the problem is not identity resolution. The problem is that the model cannot yet defend the claim that they were the best global options after adjusting for competition strength and goalkeeper-specific performance.

Therefore:

- the existing teams, hashes, logs and 100,000-match result remain immutable for audit;
- the result is reclassified as `diagnostic_invalidated_for_global_best_xi_claim`;
- no global-best-XI publication claim is allowed until the external-validity gate passes;
- the next release must include a discriminative goalkeeper model, competition/opponent-strength adjustment and a selected-player plausibility report against leading alternatives.
