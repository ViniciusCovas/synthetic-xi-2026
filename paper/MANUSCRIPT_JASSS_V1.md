# Can a Synthetic Collective Rival an Elite Team? A Reproducible Social Simulation of Composition, Variability, and Context Dependence

## Abstract

Research on collective intelligence has long asked whether group performance follows primarily from exceptional individuals or from the composition and interaction of the collective itself. Computational models now make it possible to construct collectives that do not correspond one-to-one to existing people, yet the performance implications of such distributionally composed groups remain poorly understood. We define a **synthetic collective** as a simulated group whose members instantiate role-specific profiles derived from an empirical population and interact as independent entities within a shared task environment. We compare a Synthetic XI, constructed from robust positional archetypes, with a Real Best XI composed of distinct elite players. A preregistered event-state simulation generated 10,000 confirmatory elimination finals and an independent 50,000-run precision replication. Under the frozen primary specification, the Real Best XI became champion in 55.410% of confirmatory simulations and 55.304% of replication simulations; the corresponding Synthetic XI probabilities were 44.590% and 44.696%. The 0.106-percentage-point difference between runs indicates high Monte Carlo stability. Performance signatures nevertheless differed beyond the mean: the Synthetic XI showed lower variance in goals, expected goals, and shots, but greater zero-goal and lower-tail offensive risk, while the Real Best XI produced extreme outputs more often. Relative performance also depended on score state, match phase, and numerical state. Sensitivity and nested-uncertainty analyses showed that computational precision under a frozen specification did not imply structural invariance across plausible model worlds. The study contributes a reproducible framework for analyzing synthetic collectives and demonstrates why collective performance should be characterized through probability, variability, extremity, context dependence, and structural uncertainty rather than a single average outcome.

**Keywords:** synthetic collectives; collective intelligence; social simulation; team composition; agent-based modeling; Monte Carlo; structural uncertainty; football

## 1. Introduction

Collective performance is commonly explained through one of two intuitions. The first locates success in exceptional individuals: assemble the most capable members, and the group should outperform its competitors. The second emphasizes relational and compositional properties: diversity, coordination, role complementarity, and interaction patterns may allow a collective to exceed—or fail to realize—the potential implied by its members. Research on collective intelligence has repeatedly shown that group performance cannot be reduced to the sum of individual scores alone (Woolley et al. 2010). Formal work has likewise demonstrated conditions under which diverse problem solvers can outperform collections of individually superior agents (Hong and Page 2004). Yet these traditions usually assume that group members are identifiable persons or autonomous agents whose traits exist before the collective is assembled.

A different possibility emerges when the members themselves are constructed from a population distribution. Rather than selecting an existing individual for a role, a model can derive a robust positional profile from many eligible individuals and instantiate that profile as an independent agent. Repeating this process across roles yields a collective that is empirically anchored but does not correspond one-to-one to any real group. Such a collective is neither a simple average nor a team of interchangeable clones. Its members share population-derived role profiles but maintain separate identities, states, fatigue, disciplinary histories, decisions, and trajectories inside the simulation.

We call this object a **synthetic collective**: a simulated group whose members do not correspond one-to-one to existing persons but instantiate role-specific profiles derived from an empirical population, with independent states and interactions inside a shared task environment. This definition distinguishes synthetic collectives from synthetic populations used primarily to reproduce demographic distributions (Chapuis, Taillandier, and Drogoul 2022), from large-language-model populations that negotiate conventions through communication (Ashery, Aiello, and Baronchelli 2025), and from human–AI teams in which machines participate alongside humans (Seeber et al. 2020; Cui and Yasseri 2024). The Synthetic XI studied here is not a team of language models, does not possess consciousness or physical embodiment, and is not assumed to communicate like human athletes. It is a distributionally constructed collective whose performance emerges from role-specific profiles interacting through a common event-state environment.

This distinction matters because distributional construction changes the composition problem. Selecting the best observed individual at each position preserves high-end ability and idiosyncratic strengths, but it may also preserve heterogeneity, extreme tendencies, and coordination challenges. Constructing an archetype from the robust center of a high-performing positional cohort suppresses some individual extremes. That suppression may regularize performance, but it may also remove rare abilities that generate decisive outcomes. Consequently, synthetic and elite composition may not differ only in expected performance. They may generate different **performance signatures**: distinct combinations of average success, variance, lower-tail failure, upper-tail impact, and responsiveness to changing task states.

A rule-bounded team sport offers a useful environment for examining these questions. Football is a highly interdependent social system in which outcomes arise from sequential interaction, specialized roles, incomplete control, state-dependent tactics, sanctions, injuries, substitutions, numerical asymmetries, and stochastic events. No player can independently realize the collective outcome, and the value of an action depends on the score, phase, available teammates, opposition, and prior events. At the same time, the formal rules and observable event structure make it possible to specify mechanisms and audit simulated trajectories. The purpose of the present study is not to predict a physical match or claim that a synthetic team could literally take the field. Football is used as a structured task environment for a broader question about collective composition.

We compare two counterfactual collectives built from the same frozen empirical snapshot. The **Synthetic XI** consists of independent role instances derived from robust positional profiles among eligible high-performing players. The **Real Best XI** consists of distinct elite players selected to occupy the same canonical roles. Both teams operate in the same preregistered event-state simulation, under neutral and paired initial conditions. The model includes possession sequences, territorial progression, shots, expected goals, goals, fatigue, coordination, state-dependent tactics, fouls, cards, injuries, substitutions, video review, extra time, and penalties.

The analysis is designed around an evidence hierarchy rather than a single large Monte Carlo run. A 10,000-final preregistered experiment provides the primary confirmatory estimate. A separate 50,000-final run, using a different master seed and no changes to code, rosters, parameters, or hypotheses, serves as an independent precision replication. Nine sensitivity scenarios evaluate alternative composition and modeling choices. A nested analysis separates match randomness from uncertainty across parameter worlds. This design allows us to distinguish two questions that simulation studies often conflate: whether an estimate is stable under repeated sampling from the same model, and whether the conclusion is stable across plausible versions of the model.

The study makes four contributions. First, it develops the synthetic collective as a conceptual object situated between synthetic populations, artificial-agent societies, and human–AI teams. Second, it shows that composition logics can be compared through multidimensional performance signatures rather than average success alone. Third, it demonstrates a reproducible workflow combining preregistration, fail-closed release gates, confirmatory simulation, independent precision replication, sensitivity analysis, and nested uncertainty. Fourth, it provides an empirical illustration of a central epistemic principle: narrow Monte Carlo intervals can coexist with substantial structural uncertainty.

The primary research question is:

**RQ1.** Under the preregistered model, frozen data snapshot, and paired initial conditions, how does the championship probability of a distributionally composed Synthetic XI compare with that of an elite individually composed Real Best XI?

Three preregistered secondary hypotheses examine the shape and context of collective performance. Their numbering is retained from the broader preregistered research program to preserve traceability:

**H5 — Variability.** The Synthetic XI exhibits lower outcome variability than the Real Best XI across goals, expected goals, and shots.

**H6 — Extreme performance.** The Real Best XI produces high-impact and upper-tail outcomes more frequently than the Synthetic XI.

**H7 — Context dependence.** The relative performance of the two teams depends on score state, match phase, and numerical state.

## 2. Theoretical Framework

### 2.1 From individual ability to collective performance

The relationship between member ability and collective performance is neither linear nor context-free. Collective-intelligence research shows that groups can possess a general capacity that is not adequately explained by the maximum or average intelligence of their members (Woolley et al. 2010). Diversity models similarly demonstrate that heterogeneous problem-solving repertoires can outperform collections of individually superior agents when the task permits complementary search and when participants are sufficiently capable (Hong and Page 2004). These findings redirect attention from isolated attributes toward composition, interaction, and task structure.

Team settings also reveal limits to the assumption that more talent monotonically improves performance. The too-much-talent effect suggests that concentrations of elite performers can become counterproductive in highly interdependent tasks when status competition or coordination costs interfere with collaboration (Swaab et al. 2014). Research on professional football has likewise connected network structure and interaction patterns to team performance (Grund 2012), while studies of talent disparity indicate that the distribution of ability within a squad can matter alongside total talent (Franck and Nüesch 2010). These literatures do not imply that elite individuals are unimportant. They imply that ability becomes consequential through a collective architecture.

The present study extends this problem by altering the ontological status of the members. The comparison is not between two sets of existing people selected by different rules. One collective is composed of empirically observed elite individuals, while the other is composed of role-specific statistical archetypes derived from distributions of eligible performers. The relevant question is therefore not simply whether diversity beats ability. It is whether replacing individual distinctiveness with robust positional centrality changes the distribution of collective outcomes.

### 2.2 Synthetic collectives as distributionally constructed teams

Synthetic populations are widely used to create micro-level populations that reproduce aggregate characteristics when complete individual-level populations are unavailable (Chapuis, Taillandier, and Drogoul 2022). Artificial-society research similarly creates agents whose interactions generate macro-level patterns. More recent work explores artificial collective intelligence as an engineering problem (Casadei 2023), AI-enhanced collective intelligence (Cui and Yasseri 2024), and populations of generative agents capable of social interaction and convention formation (Park et al. 2023; Ashery, Aiello, and Baronchelli 2025).

The synthetic collective introduced here differs in purpose and construction. Its agents are not sampled to reconstruct a demographic population, and they are not foundation models endowed with open-ended language behavior. Each role profile is constructed from an empirical performance cohort using a preregistered robust aggregation rule. The resulting profile is then instantiated as an agent in a dynamic collective task. The collective is synthetic because no one-to-one real-world team corresponds to it; it is collective because its outcomes emerge through interaction among independently evolving role instances.

This construction can be understood as a form of distributional abstraction. Individual noise and idiosyncratic extremes are reduced while role-relevant central tendencies are retained. In statistical terms, the synthetic profile behaves partly like regularization: it limits the influence of unusually high or low individual values. In social terms, however, this abstraction removes biographies, embodied histories, tacit relationships, and unmeasured styles. A synthetic collective may consequently appear more consistent within the dimensions represented in the model while remaining vulnerable to omitted forms of heterogeneity and coordination.

The framework therefore rejects two symmetrical simplifications. The Synthetic XI is not an “average team” in the ordinary sense because its profiles are derived from eligible high-performing cohorts and operate as independent agents. But it is also not an artificial superteam, because averaging cannot preserve every exceptional capability simultaneously. Distributional composition may improve regularity while attenuating rare combinations that enable extreme performance.

### 2.3 Coordination, variability, and extreme outcomes

A single expected-value comparison conceals important distinctions among collectives. Two teams can have similar average output while differing sharply in variance, tail risk, and capacity for extreme outcomes. These distinctions are especially important in elimination environments, where rare decisive events can outweigh stable but moderate performance.

The robust centers used to construct the Synthetic XI should, by design, attenuate individual extremes. This suggests lower variance in aggregate outputs such as goals, expected goals, and shots. Yet lower variance is not equivalent to lower downside risk in every metric. A collective may be tightly concentrated around a modest offensive process while still produce zero output more often than a collective with greater upside. Variance, probability of failure, and upper-tail capacity are analytically distinct.

The Real Best XI preserves distinct elite profiles. Such a team may combine higher maximum capabilities with greater heterogeneity. In a dynamic model, heterogeneity can create both coordination costs and opportunities for nonlinear impact. Rare high-output performances may be more frequent even when average differences are moderate. The expected signature is therefore not simply “real is better” or “synthetic is more consistent,” but a structured tradeoff between regularity and extremity.

This motivates H5 and H6. H5 predicts lower Synthetic XI variability in core outputs. H6 predicts more frequent high-impact outcomes for the Real Best XI, operationalized through threshold probabilities and upper quantiles. The two hypotheses are compatible: a less variable synthetic collective can remain competitive in many simulations while losing some of the elite collective's upside.

### 2.4 State-dependent collective performance

Collective performance is produced within states, not outside them. A team that is leading can reduce risk, change territorial priorities, substitute differently, and accept lower shot volume. A trailing team may increase attacking commitment, tolerate transition exposure, and generate more attempts. Numerical superiority or inferiority changes available passing options, defensive coverage, and decision thresholds. First-half behavior may differ from second-half or extra-time behavior because remaining time, fatigue, and elimination risk change.

State dependence is central to social simulation because aggregate averages can obscure feedback between outcomes and behavior. The score is simultaneously a result of prior collective performance and an input into subsequent decisions. Sanctions and injuries likewise modify the interaction network. H7 therefore treats relative performance as conditional on score state, match phase, and numerical state. The objective is not to identify a timeless team effect but to map when and under what conditions one composition logic generates a relative advantage.

This perspective also cautions against treating events within a match as independent observations. Possessions are embedded in common trajectories, and the same latent match conditions affect many events. The analysis therefore estimates uncertainty at the simulation level rather than inflating sample size through event-level pseudo-replication.

### 2.5 Precision and structural uncertainty in social simulation

Simulation output is conditional on code, inputs, parameters, and assumptions. Increasing the number of runs reduces Monte Carlo error for a fixed model, but it does not establish that the model specification is uniquely correct. Validation and uncertainty analysis must therefore distinguish stochastic uncertainty from structural uncertainty (Windrum, Fagiolo, and Moneta 2007). ODD-style documentation helps make model assumptions inspectable (Grimm et al. 2020), while sensitivity analysis reveals whether conclusions depend on plausible modeling choices.

The present design treats independent replication and structural sensitivity as complementary. The 50,000-run replication asks whether the primary estimate is reproducible under an unchanged model and a new seed. The sensitivity and nested analyses ask whether the result persists when composition rules, role classifications, minimum-minute thresholds, coordination assumptions, profiles, or engine parameters vary. A result can pass the first test and remain uncertain under the second. Rather than treating this as a contradiction, we regard it as an essential characterization of model-based knowledge.

## 3. Model and Methods

### 3.1 Study design and preregistration

The study is a preregistered computational comparison of two counterfactual teams constructed from the same frozen data snapshot. A historical 10,000-run release generated before the official protocol amendment was retained unchanged as a pilot and was not used to choose the direction of the confirmatory result. The official protocol froze team-construction rules, rosters, role mappings, simulation parameters, estimands, validation gates, and claim boundaries before the confirmatory run.

The unit of analysis is a simulated elimination final. The primary estimand is the probability that each team becomes champion after regulation, extra time, and penalties where required. The model is intended for theory-guided counterfactual exploration with empirical anchoring. It is not a deterministic forecast of a physical match.

A concise ODD-aligned description appears below. The complete ODD protocol is provided in `SUPPLEMENT_ODD_OFFICIAL_V1.md`, and exact implementation details are available in the frozen repository.

### 3.2 Purpose and empirical environment

The model evaluates how distributional and elite composition logics affect collective performance in a highly interdependent task. Football supplies a rule-bounded environment with specialized roles, sequential interaction, sanctions, substitutions, score feedback, and stochastic outcomes. Input profiles were constructed from the frozen 2026 data snapshot described in the repository. Every critical input and output is associated with a SHA-256 hash and seed ledger.

### 3.3 Entities, state variables, and scales

The principal entities are two teams, their active players, bench players, the ball-possession process, match events, and the match state. Each player has a unique identifier, role compatibility, ability dimensions, fatigue, disciplinary state, injury state, active/bench status, and match-specific trajectory. The match state includes minute, period, score, possession, numerical balance, substitution availability, tactical state, environmental and referee labels, and elimination stage.

The canonical roles are goalkeeper, right back, right center back, left center back, left back, defensive midfielder, central midfielder, attacking midfielder, right winger, left winger, and striker. Each team has a frozen 26-member roster. Only compatible registered bench players may enter as substitutes.

### 3.4 Construction of the Synthetic XI

For each positional archetype, eligible players were ranked using the frozen selection procedure. The primary profile used the Top 20 eligible players with at least 900 minutes in the declared windows. A 10% trimmed mean was calculated for each modeled dimension. Top 10 and Top 30, as well as 450- and 180-minute thresholds, were reserved for sensitivity analyses.

The Synthetic XI contains independent instances of the resulting positional profiles. Positions requiring two players—center back, fullback, and winger—share an archetype center but receive distinct identifiers and independent states. They can therefore accumulate different fatigue, cards, injuries, substitutions, actions, and outcomes. No synthetic instance is treated as a copy of a realized human player.

### 3.5 Construction of the Real Best XI

The Real Best XI consists of eleven distinct top-ranked real players occupying the same canonical roles. The starting eleven, 26-player roster, bench compatibility, penalty order, and emergency goalkeeper policy were frozen before execution. Deterministic tie-breaking rules prevented one player from occupying multiple roles. The runtime aborted if any identifier, role, roster size, or hash differed from the authorized roster.

### 3.6 Process overview and scheduling

The event-state engine represents possession sequences and territorial progression, shot generation, expected goals, conversion, score updates, fatigue, coordination, tactical adjustments, fouls, yellow cards, second-yellow dismissals, direct red cards, injuries, substitutions, video review, penalties, added time, extra time, and penalty shootouts. Events update the state sequentially. Score, phase, fatigue, and numerical balance affect later decision probabilities, creating feedback between prior outcomes and subsequent behavior.

Initial home advantage was neutral. Where permitted, referee and environmental conditions were paired between the two team orientations. Common random numbers were used in orientation diagnostics. Environmental context was recorded but did not introduce an unvalidated player-performance modifier.

### 3.7 Calibration, verification, and release gates

The model used frozen disciplinary benchmarks for fouls, comparable yellow cards, and red cards. Release required event-sanity checks, valid actor membership, deterministic reproducibility, disciplinary calibration, orientation equivalence, seed stability, external holdout approval, selection sufficiency, authorized rankings, completed sensitivity analysis, completed nested uncertainty, and presence of all H5–H7 estimands. Absence of affirmative evidence counted as failure. Official execution was fail-closed: a changed critical source hash, roster, protocol, or configuration blocked the run.

Orientation equivalence was assessed with 2,000 paired observations and a preregistered equivalence margin. Seed stability was evaluated across four independent 1,000-run batches. No post-result tuning was permitted or performed.

### 3.8 Confirmatory experiment and independent replication

The primary confirmatory experiment consisted of 10,000 finals with master seed `2026073001`. Binary probabilities were reported with 95% Wilson intervals. The independent precision replication consisted of 50,000 finals with master seed `2026073102`. It used the same authorized source, engine, rosters, parameters, hypotheses, and output definitions. Sample size was fixed, early stopping was prohibited, and the replication was preregistered before execution.

The replication-consistency criterion required the direction of the championship difference to match and the absolute difference between primary and replication estimates to remain within a preregistered Monte Carlo consistency threshold based on the combined binomial variances. A pooled 60,000-run estimate was computed only as a secondary precision summary; it did not replace the confirmatory result.

### 3.9 H5, H6, and H7 estimands

H5 evaluated Synthetic-minus-Real differences in the variance of goals, expected goals, and shots, together with differences in zero-goal probability and offensive lower-tail probability. Negative variance differences supported lower Synthetic XI variability. Lower variability was not interpreted automatically as superiority.

H6 evaluated Synthetic-minus-Real differences in the probability of scoring at least three goals, exceeding 2.0 expected goals, taking at least 15 shots, and winning by at least two goals. Quantile differences at 0.90 and 0.95 were also examined. Negative threshold differences supported more frequent extreme output by the Real Best XI.

H7 estimated Synthetic-minus-Real rates of shots, goals, and expected goals per possession across combinations of score state (leading, tied, trailing), match phase (first half, second half, extra time), and numerical state (equal, superior, inferior). Uncertainty was estimated by simulation rather than individual event.

### 3.10 Sensitivity and nested uncertainty

Nine preregistered scenarios varied Top-N, minimum minutes, role ontology, and coordination assumptions while preserving the official engine. Each scenario contained 750 simulations. Directional consistency was reported but was not a validity gate.

Nested uncertainty used 160 outer parameter worlds and 100 matches per world, for 16,000 matches. Components included player-profile uncertainty, role-classification sensitivity, Top-N, minimum minutes, coordination, engine parameters, paired referee context, paired environmental context, and match randomness. This analysis characterized uncertainty across plausible model worlds rather than Monte Carlo error within the primary world.

## 4. Results

### 4.1 Primary championship probability

In the 10,000-run confirmatory experiment, the Synthetic XI became champion in **44.590%** of finals (95% Wilson interval: **43.618%–45.566%**). The Real Best XI became champion in **55.410%** (95% Wilson interval: **54.434%–56.382%**). The estimated Real Best XI advantage was therefore **10.820 percentage points**.

During regulation time, the Real Best XI won 42.40% of simulations, the Synthetic XI won 32.07%, and 25.53% were tied at the end of regulation. The championship comparison includes matches resolved in extra time or by penalties.

The result answers RQ1 conditionally: under the frozen preregistered primary specification, the elite individually composed collective was more likely to become champion, while the distributionally composed synthetic collective remained competitive in a substantial minority of simulated finals.

### 4.2 Independent precision replication

The 50,000-run replication produced a Synthetic XI championship probability of **44.696%** (95% Wilson interval: **44.261%–45.132%**) and a Real Best XI probability of **55.304%**. The replication estimate differed from the confirmatory estimate by only **0.106 percentage points**, well within the preregistered Monte Carlo consistency threshold. Direction, precision, source-hash equality, event sanity, disciplinary calibration, orientation equivalence, seed stability, and the presence of all preregistered estimands passed.

The secondary pooled estimate across 60,000 simulations was 44.678% for the Synthetic XI (95% Wilson interval: 44.281%–45.076%). Because the confirmatory and replication runs have different epistemic roles, the pooled estimate is reported only to summarize precision.

The near identity of the two independent estimates indicates that the primary result is not an artifact of the original master seed or consequential Monte Carlo noise under the frozen specification.

### 4.3 H5: lower variability with greater lower-tail risk

The confirmatory and replication runs supported H5 for all three preregistered variance estimands. In the 50,000-run replication, the Synthetic-minus-Real variance difference was **−0.1805** for goals (95% bootstrap interval: −0.2103 to −0.1507), **−0.0585** for expected goals (−0.0656 to −0.0512), and **−0.5607** for shots (−0.7612 to −0.3515). All intervals excluded zero in the direction of lower Synthetic XI variability.

Lower variance did not translate into uniformly lower downside risk. The Synthetic XI's zero-goal probability exceeded that of the Real Best XI by **5.604 percentage points** (5.062–6.108), and its offensive lower-tail probability was **7.764 points** higher (7.218–8.310). The confirmatory run showed the same pattern.

These results identify a more specific performance signature than “consistency.” The Synthetic XI generated a narrower distribution in major outputs, but the distribution was not simply a safer version of elite performance. It was more compressed while also placing more probability on offensive failure. Robust positional centrality reduced dispersion without reproducing the Real Best XI's capacity to escape the lower tail.

### 4.4 H6: elite composition and extreme outcomes

The replication supported H6 across all four threshold estimands. Relative to the Real Best XI, the Synthetic XI was **5.908 percentage points** less likely to score at least three goals, **12.538 points** less likely to exceed the preregistered expected-goals threshold, **3.378 points** less likely to exceed the shot threshold, and **7.290 points** less likely to win by at least two goals. All bootstrap intervals excluded zero.

At the 0.90 and 0.95 quantiles, the teams shared the same integer goal thresholds, but the Real Best XI retained higher expected-goal and shot quantiles. At the 0.95 quantile, for example, expected goals were approximately 2.566 for the Synthetic XI and 2.888 for the Real Best XI; shot counts were 15 and 16, respectively.

The elite individually composed team therefore derived much of its advantage from the upper tail. It was not merely shifted upward by a constant amount. It produced decisive offensive states more often, consistent with the preservation of exceptional individual profiles and combinations that robust aggregation attenuates.

### 4.5 H7: context-dependent relative performance

H7 was supported descriptively through systematic variation across the 81 preregistered interaction cells. The largest and clearest differences occurred under equal numerical conditions. When tied in the first half, the Synthetic-minus-Real rate differences were **−0.01999** for shots per possession, **−0.01554** for goals per possession, and **−0.00710** for expected goals per possession. When the Synthetic XI was trailing under equal numbers in the second half, the signs reversed: **+0.01603** for shots, **+0.00216** for goals, and **+0.00183** for expected goals.

When leading under equal numbers, the Synthetic XI generally generated lower offensive rates, especially during the first and second halves. Many extra-time and numerically asymmetric cells were small or had intervals crossing zero, reflecting the relative rarity of those states.

The aggregate championship difference therefore did not represent a uniform advantage applied identically throughout a match. The Real Best XI was particularly effective in neutral score states, while the Synthetic XI increased offensive production when trailing later in the match. Relative performance emerged through feedback between prior outcomes and state-dependent behavior.

### 4.6 Monte Carlo precision versus structural uncertainty

The high consistency between the 10,000- and 50,000-run estimates establishes strong Monte Carlo reproducibility for the frozen primary world. Sensitivity analysis, however, produced Synthetic XI championship probabilities ranging from **35.467%** to **58.800%** across nine plausible scenarios. The direction of the primary comparison was therefore not invariant across all preregistered specification changes.

Nested uncertainty produced a mean Synthetic XI championship probability of **45.144%**, a median of 45.0%, and a central 95% interval across parameter worlds from **27.975%** to **64.025%**. The Real Best XI was more likely than the Synthetic XI in **71.875%** of the 160 parameter worlds.

These analyses answer different questions. The replication shows that repeated simulation from the frozen model produces nearly the same estimate. The sensitivity and nested analyses show that uncertainty about profiles, roles, thresholds, coordination, and engine parameters is substantially larger than stochastic simulation error. The primary result is computationally precise but structurally conditional.

## 5. Discussion

### 5.1 Competitive proximity without equivalence

The Synthetic XI won approximately 44.6% of elimination finals under both the confirmatory and replication runs. This is neither parity nor failure. The distributionally constructed team remained competitively close to an elite real-player team while showing a stable disadvantage of roughly eleven percentage points in championship probability under the primary specification.

The result complicates narratives in which synthetic construction either automatically surpasses human expertise or collapses because averages cannot compete with exceptional people. Robust population-derived profiles retained enough positional capacity to create a credible collective. Yet preserving the strongest observed individuals produced a meaningful advantage. The comparison suggests that distributional abstraction can approximate elite collective performance without reproducing its full performance signature.

This interpretation is deliberately narrower than “humans beat artificial intelligence.” The Synthetic XI is not an AI teammate, an autonomous language-agent society, or a physical robotic team. It is a model-based synthetic collective. The relevant contrast is between **distributional composition** and **elite individual composition** within a common simulated environment.

### 5.2 Synthetic regularity and elite extremity

H5 and H6 together reveal the central theoretical pattern. The Synthetic XI was less variable in goals, expected goals, and shots, but the Real Best XI produced extreme outcomes more often. At the same time, the Synthetic XI had greater zero-goal and lower-tail offensive risk. This combination shows why variance cannot be used as a synonym for reliability or quality.

Robust aggregation removes some individual noise and extreme values. In the model, this produced narrower distributions. But exceptional players do not contribute only random instability; they also contribute rare abilities that generate high-impact sequences and rescue a collective from low-output states. Distributional construction regularized the team while attenuating precisely the upper-tail capabilities that matter in elimination competition.

The result resembles a bias–variance tradeoff at the collective level. The synthetic collective is more regular in represented dimensions, but its regularity is centered on a profile that lacks some elite extremes. The real collective has greater dispersion and greater upside. Future research could develop this idea as **collective regularization**: the extent to which population-derived archetypes stabilize group behavior while reducing adaptive or exceptional capacity.

### 5.3 State dependence and emergent advantage

H7 demonstrates that collective advantage is not a fixed attribute detached from interaction history. The Real Best XI's strongest relative performance appeared in tied states, when both teams faced similar immediate constraints and the elite profiles could generate superior opportunities. When the Synthetic XI trailed in the second half, its simulated policy increased offensive activity and partially reversed rate differences.

This does not mean the Synthetic XI became globally superior when behind. It means that state-dependent adaptation altered the local performance relationship. The score is both an outcome and a behavioral input. A team that falls behind changes risk tolerance, while a leading team may protect its position. Aggregated title probabilities compress these feedback loops into a single number.

For social simulation, this is an important reminder that group comparisons should be decomposed by endogenous states. A collective's observed effectiveness may result from the frequency with which it enters certain states, its behavior within those states, or both. The model makes these mechanisms inspectable even when causal interpretation remains conditional on the specification.

### 5.4 What replication can and cannot establish

The independent 50,000-run replication is a strong result. It used a new seed, fixed sample size, identical authorized source hashes, and no post-result changes. The 0.106-percentage-point difference from the primary estimate is negligible relative to the substantive gap. This substantially reduces concern that the confirmatory result was driven by an unusual random sequence.

Yet the sensitivity and nested analyses prevent overconfidence. Across plausible model specifications and parameter worlds, the Synthetic XI's estimated probability moved widely and sometimes exceeded 50%. This does not invalidate the primary result, because those analyses do not repeat the same estimand under the same model. They show that the primary estimand is conditional on consequential assumptions.

The distinction between Monte Carlo precision and structural certainty should be reported more routinely in computational social science. Researchers can often make confidence intervals arbitrarily narrow by increasing simulation count. Such intervals characterize sampling from the code that was written; they do not measure uncertainty about whether alternative reasonable code or parameters would yield the same conclusion. Our evidence hierarchy makes that distinction visible.

### 5.5 Implications for collective intelligence and artificial collectives

The synthetic-collective framework extends collective-intelligence research in three ways. First, it shifts attention from selecting members to constructing members from distributions. This creates a new design space between real teams and fully generative artificial-agent societies. Second, it encourages multidimensional evaluation. Collective intelligence should not be judged only by mean success but also by variance, tail behavior, adaptability, and context dependence. Third, it reveals that synthetic collectives can be competitively plausible without being functionally equivalent to elite human collectives.

These implications are relevant to emerging research on artificial collective intelligence (Casadei 2023), AI-enhanced groups (Cui and Yasseri 2024), and machines as teammates (Seeber et al. 2020). Systems built from archetypes, digital twins, or population summaries may reproduce central tendencies while losing rare capacities, tacit complementarities, and historically developed coordination. Conversely, their reduced idiosyncrasy may yield predictable behavior in bounded environments. The desirable composition depends on whether the task rewards consistency, exploration, resilience, or extreme performance.

The present model does not include natural-language communication, reflective reasoning, or endogenous learning across matches. These would be necessary to study many forms of human–AI or multi-agent collective intelligence. The contribution is more foundational: it identifies composition logic itself as a mechanism that can be isolated before adding richer cognition and communication.

### 5.6 Methodological contribution

The study also demonstrates a workflow for high-stakes simulation claims. The historical pilot was preserved rather than overwritten. An amended protocol froze corrections before the new run. The official mode required literal affirmative gates and matching hashes. The confirmatory result and the replication were separated. Sensitivity was not used to select a favorable specification after observing results. A full seed ledger, manifests, source hashes, and compact evidence files were retained.

This architecture reduces several common risks: silent model drift, selective rerunning, conflation of validation with confirmation, and retrospective reclassification of exploratory output. It does not eliminate model error, but it makes the provenance of each claim inspectable. The full ODD description and repository-level provenance matrix are intended to support independent reproduction.

### 5.7 Limitations

Several limitations constrain inference.

First, the player profiles are abstractions of measured performance. They cannot include every embodied, tactical, psychological, communicative, or relational characteristic that distinguishes real players. A trimmed positional center may suppress measurement noise and genuine rare skill simultaneously.

Second, coordination is modeled through explicit parameters and state-dependent rules rather than learned from a complete history of interpersonal relationships. The Real Best XI combines elite individuals who may never have played together, while the Synthetic XI has no biography at all. Neither team should be interpreted as reproducing a fully established real squad.

Third, the engine is event-state based rather than a continuous physical simulation. It represents possessions, actions, fatigue, discipline, and tactical state, but it does not model every off-ball movement, spatial microinteraction, biomechanics, coaching instruction, or emotional process.

Fourth, the study uses one frozen data snapshot and one task environment. Results may differ in league play, repeated tournaments, tasks with different interdependence, or domains in which average competence and extreme skill have different payoff structures.

Fifth, the sensitivity analysis is broad but not exhaustive. The nested parameter worlds reflect declared uncertainty components rather than a posterior distribution learned from all relevant real-world evidence. The 71.875% probability that the Real Best XI is superior across those worlds is therefore a model-uncertainty summary, not a universal probability of real-world superiority.

Finally, the study compares a synthetic collective with an elite human-derived collective inside a simulation. It does not observe actual human interaction with synthetic agents and cannot support claims about trust, legitimacy, communication, or organizational adoption.

### 5.8 Future research

Future work should compare multiple synthetic-construction rules, including medoids, mixture profiles, generative profiles, and archetypes optimized for complementarity rather than positional centrality. Coordination could be learned from empirical passing and interaction networks. Agents could adapt across repeated matches, communicate, or revise strategies based on observed opponents. Tournament designs could test whether lower variance is more valuable in leagues than in elimination games.

Beyond sport, the framework can be applied to project teams, emergency response, scientific collaboration, deliberative groups, and human–AI organizations. The central design question would remain the same: what is gained and lost when a collective is constructed from robust population profiles rather than identifiable individuals?

## 6. Conclusion

A distributionally constructed Synthetic XI remained competitive with an elite Real Best XI but did not match its championship probability under the preregistered primary specification. The result was reproduced almost exactly in an independent 50,000-run simulation. More importantly, the collectives differed in how they performed: the Synthetic XI was less variable but more exposed to offensive lower-tail outcomes, whereas the Real Best XI generated decisive extremes more frequently. Their relative performance changed across endogenous match states.

These findings support a view of collective performance as a multidimensional signature rather than a single average. They also demonstrate that reproducibility within a model and robustness across models are different achievements. The primary estimate is highly precise as a statement about the frozen simulation, yet materially conditional as a statement about plausible structural worlds.

Synthetic collectives provide a useful object for social simulation because they make composition itself experimentally manipulable. They allow researchers to ask not only which members form a group, but what it means for group members to be constructed from a population distribution. The resulting comparison offers a disciplined way to study the boundaries among individual ability, collective organization, artificial representation, and emergent performance.

## Data and Code Availability

All code, frozen model inputs, preregistration materials, seed ledgers, validation evidence, manifests, confirmatory outputs, replication outputs, sensitivity analyses, nested-uncertainty summaries, figures, and provenance documentation are maintained in the `ViniciusCovas/synthetic-xi-2026` repository. The submission version should cite a permanent archival release and DOI created from the final frozen commit. The 10,000-run confirmatory experiment remains the primary result; the 50,000-run experiment remains an independent precision replication.

## Ethics Statement

The study uses computational profiles and simulated events. It does not involve intervention with human participants. Real-player data are represented through the documented frozen data pipeline and are used for aggregate scientific comparison. The manuscript does not claim that the simulation reproduces the full identity, agency, or embodied performance of any individual.

## Computational Assistance Statement

Generative AI tools may have been used for editorial organization, language refinement, or software-development assistance. They are not authors. The human authors retain responsibility for the study design, code, data, verification, interpretation, references, and submitted text. This statement should be adapted to the journal's policy at submission.

## References

Ashery, A. F., Aiello, L. M., and Baronchelli, A. (2025). Emergent social conventions and collective bias in LLM populations. *Science Advances*, 11(20), eadu9368. https://doi.org/10.1126/sciadv.adu9368

Casadei, R. (2023). Artificial collective intelligence engineering: A survey of concepts and perspectives. *Artificial Life*, 29(4), 433–467. https://doi.org/10.1162/artl_a_00408

Chapuis, K., Taillandier, P., and Drogoul, A. (2022). Generation of synthetic populations in social simulations: A review of methods and practices. *Journal of Artificial Societies and Social Simulation*, 25(2), 6. https://doi.org/10.18564/jasss.4762

Cioffi-Revilla, C. (2010). A methodology for complex social simulations. *Journal of Artificial Societies and Social Simulation*, 13(1), 7.

Cui, H., and Yasseri, T. (2024). AI-enhanced collective intelligence. *Patterns*, 5(11), 101074. https://doi.org/10.1016/j.patter.2024.101074

Franck, E., and Nüesch, S. (2010). The effect of talent disparity on team productivity in soccer. *Journal of Economic Psychology*, 31(2), 218–229. https://doi.org/10.1016/j.joep.2009.12.003

Grimm, V., Railsback, S. F., Vincenot, C. E., Berger, U., Gallagher, C., DeAngelis, D. L., Edmonds, B., Ge, J., Giske, J., Groeneveld, J., Johnston, A. S. A., Milles, A., Nabe-Nielsen, J., Polhill, J. G., Radchuk, V., Rohwäder, M.-S., Stillman, R. A., Thiele, J. C., and Ayllón, D. (2020). The ODD protocol for describing agent-based and other simulation models: A second update to improve clarity, replication, and structural realism. *Journal of Artificial Societies and Social Simulation*, 23(2), 7. https://doi.org/10.18564/jasss.4259

Grund, T. U. (2012). Network structure and team performance: The case of English Premier League soccer teams. *Social Networks*, 34(4), 682–690. https://doi.org/10.1016/j.socnet.2012.08.004

Hong, L., and Page, S. E. (2004). Groups of diverse problem solvers can outperform groups of high-ability problem solvers. *Proceedings of the National Academy of Sciences*, 101(46), 16385–16389. https://doi.org/10.1073/pnas.0403723101

Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., and Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. In *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology*. https://doi.org/10.1145/3586183.3606763

Seeber, I., Bittner, E., Briggs, R. O., de Vreede, T., de Vreede, G.-J., Elkins, A., Maier, R., Merz, A. B., Oeste-Reiß, S., Randrup, N., Schwabe, G., and Söllner, M. (2020). Machines as teammates: A research agenda on AI in team collaboration. *Information & Management*, 57(2), 103174. https://doi.org/10.1016/j.im.2019.103174

Swaab, R. I., Schaerer, M., Anicich, E. M., Ronay, R., and Galinsky, A. D. (2014). The too-much-talent effect: Team interdependence determines when more talent is too much or not enough. *Psychological Science*, 25(8), 1581–1591. https://doi.org/10.1177/0956797614537280

Windrum, P., Fagiolo, G., and Moneta, A. (2007). Empirical validation of agent-based models: Alternatives and prospects. *Journal of Artificial Societies and Social Simulation*, 10(2), 8.

Woolley, A. W., Chabris, C. F., Pentland, A., Hashmi, N., and Malone, T. W. (2010). Evidence for a collective intelligence factor in the performance of human groups. *Science*, 330(6004), 686–688. https://doi.org/10.1126/science.1193147
