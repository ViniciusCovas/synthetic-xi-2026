# Results — Manuscript Draft

## Primary confirmatory outcome and independent replication

Under the preregistered primary specification, the Real Best XI was more likely to become champion than the Synthetic XI. In the confirmatory experiment of 10,000 simulated finals, the Synthetic XI won 44.590% of championships (95% Wilson CI [43.618%, 45.566%]), compared with 55.410% for the Real Best XI (95% CI [54.434%, 56.382%]). The estimated between-team difference was 10.820 percentage points in favor of the Real Best XI.

The result was reproduced in an independently seeded precision replication of 50,000 finals. The Synthetic XI won 44.696% of championships (95% CI [44.261%, 45.132%]), while the Real Best XI won 55.304% (95% CI [54.868%, 55.739%]). The replication estimate differed from the confirmatory estimate by 0.106 percentage points, well below the preregistered Monte Carlo consistency threshold of 1.067 percentage points. The direction and magnitude of the primary result were therefore stable to independent match-level randomness. A pooled 60,000-run estimate, reported only as a secondary precision summary, placed the Synthetic XI championship probability at 44.678% (95% CI [44.281%, 45.076%]).

## H5: outcome variability

H5 predicted lower outcome variability for the Synthetic XI. This hypothesis was supported across all three preregistered variance estimands. In the 50,000-run replication, the Synthetic-minus-Real variance difference was -0.180 for goals (95% bootstrap CI [-0.210, -0.151]), -0.058 for xG (95% CI [-0.066, -0.051]), and -0.561 for shots (95% CI [-0.761, -0.352]). All intervals excluded zero, and all directions reproduced the 10,000-run findings.

Lower variance did not imply uniformly better offensive reliability. The Synthetic XI had a 5.604-percentage-point higher probability of scoring zero goals and a 7.764-percentage-point higher probability of falling into the preregistered offensive lower tail. The results therefore indicate a narrower distribution accompanied by greater concentration in low-output states, rather than an unqualified performance advantage.

## H6: extreme impact outcomes

H6 predicted that the Real Best XI would generate more extreme offensive outcomes. The 50,000-run replication supported this prediction for all four threshold estimands. Relative to the Real Best XI, the Synthetic XI was 5.908 percentage points less likely to score three or more goals (95% CI [-6.416, -5.408]), 12.538 percentage points less likely to exceed the preregistered xG threshold (95% CI [-13.048, -12.020]), 3.378 percentage points less likely to exceed the shot threshold (95% CI [-3.706, -3.034]), and 7.290 percentage points less likely to win by the preregistered margin (95% CI [-7.838, -6.766]). The corresponding confirmatory estimates were similar in direction and magnitude.

The upper-tail quantiles reinforced this interpretation. Although both teams reached the same integer goal values at the 90th and 95th percentiles, the Real Best XI produced higher xG and shot quantiles. The Real Best XI was therefore characterized by a greater frequency of high-impact offensive realizations, whereas the Synthetic XI occupied a narrower outcome distribution.

## H7: context-dependent relative performance

H7 predicted that the relative advantage between teams would vary across score state, numerical state, and match phase. The analysis included 81 interaction cells and treated the simulation, rather than the individual event, as the uncertainty unit.

At equal numerical strength, the Synthetic XI produced lower xG-event rates when the match was tied, both in the first half (difference = -0.00710, 95% CI [-0.00766, -0.00655]) and second half (difference = -0.00195, 95% CI [-0.00234, -0.00154]). In contrast, when trailing at equal numerical strength in the second half, the Synthetic XI showed higher shot (difference = 0.01603, 95% CI [0.01402, 0.01806]), goal (difference = 0.00216, 95% CI [0.00091, 0.00345]), and xG rates (difference = 0.00183, 95% CI [0.00142, 0.00223]). Many extra-time and rare numerical-state cells remained close to zero and had intervals crossing zero.

The interaction results therefore support heterogeneous and state-responsive performance rather than a constant team effect. The Synthetic XI was comparatively weaker in neutral tied states but intensified production when trailing, particularly during the second half.

## Sensitivity and structural uncertainty

The primary result was computationally precise but not invariant across model specifications. Across nine preregistered sensitivity scenarios, the Synthetic XI championship probability ranged from 35.467% to 58.800%, and the direction of the primary advantage was not consistent across all scenarios. All event-sanity and discipline gates nevertheless passed.

The nested uncertainty analysis sampled 160 parameter worlds with 100 matches per world. The Synthetic XI championship probability had a mean of 45.144%, a median of 45.000%, a 10th–90th percentile range of 35.000%–58.000%, and a 2.5th–97.5th percentile range of 27.975%–64.025%. The Real Best XI was more likely than the Synthetic XI in 71.875% of sampled parameter worlds.

Together, these analyses distinguish two forms of uncertainty. Match-level Monte Carlo uncertainty was small: the frozen primary estimate was precise and independently replicated. Structural uncertainty was substantially larger: alternative plausible profile, role, coordination, and engine assumptions changed the magnitude and, in some cases, the direction of the comparison.
