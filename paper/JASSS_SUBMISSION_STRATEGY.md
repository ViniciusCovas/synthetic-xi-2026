# JASSS Submission Strategy

## Primary target

**Journal of Artificial Societies and Social Simulation (JASSS)**

## Why this is the strongest fit

The study is fundamentally a social-simulation paper rather than a sports-prediction paper. Its contribution lies in using a transparent computational model to examine how two different logics of collective composition generate distinct distributions of collective performance under interdependent, state-dependent conditions.

The manuscript should therefore be positioned around five elements that closely match the journal's intellectual center:

1. **Artificial societies and synthetic collectives.** The Synthetic XI is a population-derived collective whose members instantiate role-specific statistical profiles rather than correspond one-to-one to existing persons.
2. **Social process through simulation.** The model represents interaction, coordination, adaptation, sanctions, injuries, substitutions, score states, numerical asymmetry, and collective decision consequences over time.
3. **Mechanism-oriented comparison.** The central question is not which team would literally win a physical match, but how composition logic shapes performance probability, variance, extreme outcomes, and context dependence.
4. **Reproducibility.** The study has frozen inputs, preregistered estimands, deterministic role mappings, source hashes, seed ledgers, release gates, a confirmatory run, and an independent precision replication.
5. **Uncertainty discipline.** The paper explicitly separates Monte Carlo error from structural uncertainty and shows that a highly reproducible estimate under a frozen specification is not equivalent to invariance across plausible model specifications.

## Proposed title

**Can a Synthetic Collective Rival an Elite Team? A Reproducible Social Simulation of Composition, Variability, and Context Dependence**

### Alternative titles

- **Synthetic Collective Intelligence Under Competition: Composition, Variability, and State Dependence in a Reproducible Social Simulation**
- **From Statistical Archetypes to Collective Performance: A Preregistered Simulation of Synthetic and Elite Human Teams**
- **When the Average Becomes a Team: Simulating the Performance Signature of a Synthetic Collective**

The first title is recommended because it is accessible, theoretically legible, and does not falsely claim that the Synthetic XI is an autonomous AI system.

## Central theoretical claim

Collective performance is not reducible to either average individual ability or the presence of exceptional individuals. Different composition logics can produce different **performance signatures**: characteristic combinations of expected success, variability, lower-tail risk, extreme upside, and responsiveness to changing states.

The study contrasts:

- a **distributionally composed synthetic collective**, built from robust positional centers of an empirical population; and
- an **elite individually composed collective**, built from distinct top-ranked real players.

The main result is not simply that the Real Best XI has a higher championship probability. The more valuable theoretical result is that the two collectives express different modes of performance:

- the Synthetic XI is less variable on several output dimensions;
- the Synthetic XI nevertheless has greater zero-output and lower-tail offensive risk;
- the Real Best XI produces high-impact outcomes more frequently;
- the relative advantage changes with score state, match phase, and numerical state;
- the primary probability estimate is highly stable across independent Monte Carlo runs but not invariant across all plausible structural specifications.

## Definition to use consistently

> A **synthetic collective** is a simulated group whose members do not correspond one-to-one to existing persons but instantiate role-specific profiles derived from an empirical population, with independent states and interactions inside a shared task environment.

This definition must be introduced early. It prevents three category errors:

1. calling the Synthetic XI a team of large language models;
2. treating statistical archetypes as average humans without an interaction environment;
3. claiming that synthetic agents possess consciousness, intention, or physical embodiment.

## Research question and hypotheses

### Primary research question

**RQ1.** Under the preregistered model, data snapshot, and paired initial conditions, how does the championship probability of a distributionally composed Synthetic XI compare with that of an elite individually composed Real Best XI?

### Preregistered secondary hypotheses

**H5 — Variability.** The Synthetic XI exhibits lower outcome variability than the Real Best XI across goals, expected goals, and shots.

**H6 — Extreme performance.** The Real Best XI produces high-impact and upper-tail outcomes more frequently than the Synthetic XI.

**H7 — Context dependence.** The relative performance of the two teams depends on score state, match phase, and numerical state.

The numbering H5–H7 should be retained and explained as inherited from the broader preregistered research program. Renumbering after observing results would weaken traceability.

## Recommended manuscript architecture

Target a concise main text of approximately **7,500–8,500 words**, excluding the full ODD supplement and references. This is an editorial target rather than a claimed journal limit.

1. **Introduction**
   - collective performance as a composition problem;
   - limits of individual-level optimization;
   - synthetic collectives as a new simulation object;
   - empirical and methodological gap;
   - contributions and research question.
2. **Theoretical Framework**
   - individual ability, diversity, and collective intelligence;
   - distributional versus elite composition;
   - coordination, variance, and extreme performance;
   - state-dependent collective behavior;
   - hypotheses.
3. **Model and Methods**
   - concise Overview, Design concepts, and Details summary in the article;
   - full ODD protocol in the supplement;
   - construction of both teams;
   - event-state engine;
   - preregistration and release gates;
   - confirmatory, replication, sensitivity, and nested-uncertainty layers.
4. **Results**
   - championship probability;
   - replication consistency;
   - H5, H6, and H7;
   - Monte Carlo precision versus structural uncertainty.
5. **Discussion**
   - competitive proximity without equivalence;
   - synthetic regularity and elite extremity;
   - contextual rather than fixed advantage;
   - implications for collective intelligence and artificial collectives;
   - epistemic lessons for simulation research;
   - limitations.
6. **Conclusion**

## ODD implementation

The submission should include two levels of model description:

- a concise ODD-aligned description in the main manuscript; and
- a complete ODD supplement covering purpose and patterns, entities and state variables, process overview and scheduling, design concepts, initialization, input data, and submodels.

The ODD supplement must describe the model that generated the frozen official results, not an idealized future version. It should link every model component to repository files and state clearly which processes are empirical, calibrated, assumed, paired, or sensitivity-only.

## Evidence hierarchy

The manuscript must preserve the following hierarchy:

1. **Primary confirmatory evidence:** 10,000 simulations, seed `2026073001`.
2. **Independent precision replication:** 50,000 simulations, seed `2026073102`.
3. **Secondary pooled precision summary:** 60,000 simulations.
4. **Sensitivity analysis:** nine alternative scenarios.
5. **Nested uncertainty:** 160 parameter worlds × 100 matches.

The pooled estimate must never replace the preregistered confirmatory estimate. Sensitivity and nested uncertainty must not be presented as failed replications; they answer a different question about specification dependence.

## Strongest defensible claim

> Under the preregistered primary specification of the frozen official engine, the Real Best XI was more likely than the Synthetic XI to become champion. This result was reproduced with an independent seed and substantially greater Monte Carlo precision. However, the magnitude and even direction of the advantage were not invariant across all plausible model specifications and parameter worlds.

## Claims to avoid

Do not write that:

- humans defeated artificial intelligence;
- the Synthetic XI would lose a real match;
- the model proves elite talent is superior to collective intelligence;
- lower variance means better performance;
- 60,000 simulations eliminate model uncertainty;
- the synthetic players think, communicate, or coordinate like humans unless the specific modeled mechanism is described;
- sensitivity reversals invalidate the confirmatory result;
- narrow Monte Carlo intervals establish external validity.

## Key contribution statements

The manuscript should make four contributions explicit:

1. **Conceptual:** defines the synthetic collective as a distributionally constructed, interacting group rather than a single synthetic persona or a set of autonomous language agents.
2. **Substantive:** demonstrates that elite and synthetic composition generate different performance signatures, not merely different mean outcomes.
3. **Methodological:** shows how preregistration, fail-closed release gates, independent replication, and nested uncertainty can coexist in an agent-based or event-state simulation workflow.
4. **Epistemological:** empirically illustrates the distinction between Monte Carlo precision and structural certainty.

## Journal-specific presentation choices

- Lead with the social mechanism and only then introduce football as the empirical task environment.
- Treat football as a highly interdependent, rule-bounded social system with observable state transitions, sanctions, substitutions, and collective consequences.
- Include an ODD summary in the manuscript and the full protocol as supplementary material.
- Make the model purpose explicit: theory-guided counterfactual exploration with empirical anchoring, not deterministic forecasting.
- Provide a permanent repository release or archival DOI before submission.
- Include a data and code availability statement with the exact frozen commit and release.
- Include a transparent computational-assistance statement if required by the journal: generative AI may be acknowledged for language or editorial assistance, but not listed as an author; all claims, references, code, and analyses remain the authors' responsibility.

## Backup journal sequence

### 2. AI & Society

Use only if the paper is reframed more strongly around the ontology and societal implications of synthetic collectives. It would require less model detail in the main argument and more philosophical analysis of representation, artificial collectivity, and human–machine boundaries.

### 3. Simulation & Gaming

A plausible methodological outlet, but the article would need substantial compression and stronger emphasis on simulation design and application. It is a weaker theoretical fit for the present collective-intelligence contribution.

### 4. New Media & Society

Not recommended for the current version. A viable submission would require a major reframing around algorithmic representation, mediated expertise, and cultural narratives of synthetic performance rather than the simulation mechanism itself.

## Submission package still required

Before submission, complete:

- final manuscript in the journal's accepted format;
- full ODD supplement;
- reference audit with DOI verification;
- model verification and validation appendix;
- data/code availability statement with archival DOI;
- author contribution, funding, conflict-of-interest, and AI-use statements;
- cover letter;
- anonymized manuscript and non-anonymized title page if double-blind review is used;
- final accessibility review of figures and captions.
