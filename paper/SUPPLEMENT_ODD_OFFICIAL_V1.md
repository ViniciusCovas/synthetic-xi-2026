# Supplementary Material A — ODD Description of the Official Experiment v1

## Document status

This supplement describes the frozen model that generated the official confirmatory and precision-replication results. It follows the Overview, Design concepts, and Details (ODD) structure. It is descriptive, not normative: where the implemented model differs from an ideal future model, the implemented behavior is reported.

Canonical implementation: `complete_final_official_v1`

Primary confirmatory run: 10,000 finals, master seed `2026073001`

Independent precision replication: 50,000 finals, master seed `2026073102`

Authorized source revision: `06c750cfef3246d3c6112f6bd86d25a83287308f`

Confirmatory evidence revision: `0461ed7b5cf796cd4ab484eeca4ceb5a8075e41b`

Precision-replication evidence revision: `7c55141d9a597deaf25058a2eec28f1d945af093`

## 1. Overview

### 1.1 Purpose and patterns

#### Purpose

The model compares two collective-composition logics in an interdependent elimination task:

1. a **Synthetic XI** whose players instantiate robust, population-derived positional profiles; and
2. a **Real Best XI** composed of distinct elite real-player profiles occupying the same roles.

The model estimates the conditional distribution of elimination-final outcomes under the frozen data, construction rules, parameters, and assumptions. Its purpose is mechanism-oriented counterfactual exploration, not deterministic forecasting of a physical match.

The primary output is championship probability. Secondary outputs characterize the form of collective performance through:

- regulation win, draw, and loss probabilities;
- goals, expected goals, and shots;
- outcome variability;
- zero-output and lower-tail risk;
- high-impact and upper-tail outcomes;
- score-state, phase, and numerical-state interactions;
- sensitivity across alternative specifications;
- nested uncertainty across parameter worlds.

#### Patterns used for model evaluation

The model was not released on the basis of visual plausibility alone. The following empirical or structural patterns were used in calibration, verification, or validation:

- plausible total match-event distributions;
- frozen benchmark rates for fouls, comparable yellow cards, and red cards;
- absence of impossible roster membership or event actors;
- no residual draws after extra time and penalty procedures;
- correct substitution and substitution-window limits;
- correct dismissal and numerical-state behavior;
- orientation equivalence under neutral conditions;
- deterministic reproducibility under identical seeds;
- stability across independent seed batches;
- external holdout and repository-level selection authorization;
- exact correspondence between authorized rosters and runtime rosters.

The model was also expected to generate endogenous state dependence: score, phase, fatigue, discipline, injury, and numerical balance affect later events rather than merely appear as output labels.

### 1.2 Entities, state variables, and scales

#### Teams

There are two team entities:

- `Synthetic XI`
- `Real Best XI`

Each team contains a frozen roster of 26 registered players, a starting eleven, bench compatibility rules, penalty order, and emergency goalkeeper policy. Team-level state includes score, tactical orientation, coordination realization, substitution capacity, substitution windows, active-player set, numerical strength, and aggregate match statistics.

#### Players

Each player instance has at least the following state variables:

- unique identifier;
- team membership;
- canonical role and internal slot compatibility;
- modeled ability dimensions used in event probabilities;
- active, bench, substituted, dismissed, or unavailable status;
- accumulated fatigue;
- disciplinary state, including prior yellow card;
- injury state and severity where applicable;
- eligibility for substitution or emergency role;
- independent match-event history.

Synthetic instances occupying repeated archetypes—center backs, fullbacks, and wingers—share the same frozen positional center but have separate identifiers and independent states. A card, injury, action, or substitution affecting one instance does not automatically affect another.

Real-player instances are distinct persons and cannot occupy more than one roster slot.

#### Match and environment

The match entity stores:

- current period and minute;
- regulation, added-time, extra-time, or shootout status;
- current score;
- current possession team;
- score state from each team's perspective;
- numerical state from each team's perspective;
- remaining substitutions and windows;
- referee-context realization;
- environment-context label;
- accumulated event and team statistics;
- decision stage in the elimination process.

The environment label is retained for paired sensitivity and provenance. It is not used as an unvalidated direct modifier of individual ability.

#### Events

Each official event records, where applicable:

- event type;
- period and minute;
- acting team;
- affected team;
- possession team;
- benefiting team;
- actor and actor team;
- actor-membership validity;
- score state before the action;
- numerical state;
- resulting state changes.

The inherited `team` field denotes the acting team but is not used as the sole analytical source where actor, affected, possession, or benefiting semantics differ.

#### Spatial and temporal scales

The model is an event-state simulation rather than a continuous physical simulation. Territorial progression and action zones are represented probabilistically. Time advances through match phases and event chronology. Regulation consists of two halves plus added time. If required, extra time consists of two 15-minute periods, followed by a penalty shootout with a finite sudden-death safeguard.

### 1.3 Process overview and scheduling

A simulation proceeds in the following high-level sequence:

1. load and verify the frozen experiment configuration;
2. load authorized source hashes and release authorization;
3. load the two frozen 26-player rosters and starting elevens;
4. initialize team, player, referee, environment, and match state;
5. generate sequential possession and event processes through the first half;
6. update score, fatigue, disciplinary, injury, tactical, substitution, and numerical states after each relevant event;
7. execute halftime state transition;
8. continue the event process through the second half and added time;
9. if tied, initialize and execute extra time under the extra-time substitution policy;
10. if still tied, execute the penalty shootout;
11. store match-level outputs and, for selected runs, audited event histories;
12. update Monte Carlo summaries and seed ledger;
13. after the batch, calculate intervals, diagnostics, H5–H7 estimands, and representative replay selection.

Events occur sequentially, and later event probabilities can depend on earlier state changes. The scheduling order is therefore substantively meaningful. Score changes precede tactical responses; cards precede booked-player behavioral adaptation; dismissals precede numerical-state recalculation; injuries precede forced-substitution decisions; substitutions modify the active roster before subsequent possessions.

## 2. Design Concepts

### 2.1 Basic principles

The model is built around four principles.

First, collective outcome is generated through specialized, interacting roles rather than an additive team score alone. Second, match behavior is state dependent: score, time, fatigue, discipline, and numerical balance affect subsequent actions. Third, the two collectives differ in composition logic while sharing a common event environment. Fourth, all official claims are conditional on the frozen model and are blocked unless the full release-gate chain passes.

### 2.2 Emergence

Championship outcome, scoreline, event totals, performance variance, tail behavior, and state-conditional rate differences emerge from the interaction of player profiles, team composition, stochastic events, tactical state, fatigue, discipline, injury, and elimination rules.

No championship probability is assigned directly to either team. It is estimated from complete simulated trajectories. H5, H6, and H7 outputs are also derived after simulation rather than imposed as targets.

### 2.3 Adaptation

The model includes bounded state-dependent adaptation rather than open-ended learning.

- Tactical behavior changes with score state, phase, and numerical state.
- Fatigue changes later action probabilities.
- A booked player reduces subsequent foul propensity through the frozen adaptation multiplier.
- Injury can trigger forced substitution.
- Substitution decisions respond to time, state, fatigue, injury, and compatibility.
- Teams modify risk when leading or trailing according to frozen policies.

Agents do not learn across matches. The 10,000 and 50,000 finals are independent conditional realizations, not a season in which strategies update from prior simulations.

### 2.4 Objectives

Players do not solve explicit utility-maximization problems. Their action probabilities are generated from profiles, roles, current states, and frozen process rules. At the collective level, behavior is aligned with the football objective of producing favorable match states and ultimately becoming champion, but the model does not attribute conscious optimization or subjective preferences to synthetic instances.

### 2.5 Learning

There is no reinforcement learning, parameter updating, or cross-match memory in the official model. Calibration occurred before the official experiment and was frozen. The confirmatory and replication outputs were not used to update parameters.

### 2.6 Prediction

The model makes local stochastic predictions of possible next actions conditional on the current state. It does not assume that agents possess explicit forecasts of the entire match. Tactical state rules indirectly encode responses to remaining time and score.

### 2.7 Sensing

Modeled decision processes have access to the state variables required by their rules, including:

- current score state;
- current phase and approximate time;
- numerical balance;
- player fatigue;
- disciplinary and injury status;
- substitution availability;
- role compatibility;
- possession and territorial context.

The model does not assume perfect sensing of unmodeled mental states or continuous physical positions.

### 2.8 Interaction

Interaction occurs through the shared possession and event process. The probability and consequence of an action depend on profiles from both teams, current active players, collective coordination, tactical state, referee realization, and match history. Fouls affect opponents; cards change future behavior; dismissals change team numerical state; injuries and substitutions change the active interaction structure.

### 2.9 Stochasticity

Stochasticity enters through the Monte Carlo seed system and event-level random draws. It affects, among other processes:

- possession and progression outcomes;
- duels and turnovers;
- shot generation and expected-goal value;
- conversion;
- fouls and cards;
- injury occurrence and severity;
- video-review events and overturns;
- added-time realizations;
- substitution contingencies;
- penalty outcomes;
- match-level coordination and referee-context realizations.

The seed ledger makes every official match reproducible. Identical code, inputs, configuration, and seed reproduce the same trajectory.

### 2.10 Collectives

Team membership is explicit and frozen. Team-level outcomes emerge from independently evolving player instances. The Synthetic XI is itself the principal artificial collective of interest. It is not treated as a homogeneous scalar profile: repeated archetype instances retain separate state and event histories.

### 2.11 Observation

All simulations contribute to match-level aggregate summaries. Compact official evidence includes:

- simulation summary;
- championship probabilities and Wilson intervals;
- regulation outcomes;
- event-sanity and calibration gates;
- orientation and seed-stability diagnostics;
- H5–H7 summaries;
- H7 interaction tables;
- starting elevens and roster evidence;
- a representative match timeline;
- manifests and cryptographic hashes.

The complete match and state-condition datasets were preserved as immutable workflow artifacts where repository size made compact evidence preferable.

The representative replay is selected by a frozen distance rule relative to Monte Carlo medians and the modal decision stage. It is not selected for dramatic quality or narrative convenience.

## 3. Details

### 3.1 Initialization

At the beginning of each final:

- the authorized team bundles are loaded;
- starting elevens are activated;
- bench players are registered but inactive;
- scores and disciplinary states are set to zero;
- players begin without match injuries or dismissals;
- fatigue is initialized according to the frozen engine policy;
- substitutions and windows are initialized under elimination-match rules;
- home advantage is set to zero;
- team coordination values are drawn from the frozen neutral distributions;
- referee context is drawn and paired where required;
- the environment context label is initialized;
- the match seed is derived from the batch's master seed and ledger procedure.

The two orientations were tested using common random numbers. Official release required the paired confidence interval for the orientation difference to lie within the preregistered equivalence margin.

### 3.2 Input data

#### Player-performance inputs

Player inputs derive from the frozen data snapshot and the documented selection pipeline. The official primary analysis requires at least 900 minutes in the declared windows. Top 20 is the primary positional cohort; Top 10 and Top 30 are sensitivities. When fewer than N eligible players exist, the actual available N is used and recorded rather than imputed.

Opaque provider ratings do not enter directly into event-success probabilities.

#### Synthetic profiles

For each positional archetype, a 10% trimmed mean is calculated for each modeled profile dimension among the selected eligible cohort. The canonical archetypes are goalkeeper, center back, fullback, defensive midfielder, central midfielder, attacking midfielder, winger, and striker. These map deterministically to eleven lineup slots.

#### Real profiles and rosters

Real-player profiles and roster membership are loaded from the authorized canonical roster file. All real players are unique. The runtime checks exact identifiers, roles, roster sizes, and hashes.

#### Calibration targets

Disciplinary targets are frozen at approximately:

- 23.192 comparable fouls per match;
- 2.872 comparable yellow cards per match;
- 0.144 red cards per match.

Release tolerances are defined in the protocol and enforced automatically. Calibration targets constrain model plausibility but do not determine which team wins.

### 3.3 Submodels

#### 3.3.1 Profile construction

The profile-construction submodel ranks eligible players within role cohorts and aggregates selected dimensions with a 10% trimmed mean for synthetic archetypes. Real-player selection uses the frozen ranking and deterministic role assignment. Sensitivity variants modify Top-N, minimum minutes, or role ontology without changing the official event engine.

#### 3.3.2 Team assembly and role translation

Canonical external roles are translated to internal engine slots deterministically:

- right back to first fullback slot;
- right center back to first center-back slot;
- left center back to second center-back slot;
- left back to second fullback slot;
- right winger to first winger slot;
- left winger to second winger slot.

No player may fill multiple real-team slots. Synthetic repeated-role instances receive separate IDs.

#### 3.3.3 Possession and territorial progression

The possession submodel generates sequential opportunities for territorial advancement, retention, turnover, and shot creation. Probabilities depend on active-player profiles, role structure, team coordination, tactical state, fatigue, numerical balance, and opposing profiles. The model represents zones and action stages probabilistically rather than continuous coordinates.

#### 3.3.4 Shot generation, expected goals, and conversion

When a possession reaches a shooting state, the model generates shot probability and expected-goal value from the relevant offensive and defensive profile dimensions and current context. Goal conversion is stochastic and linked to shot quality and frozen conversion parameters. Expected goals are stored independently of actual conversion.

#### 3.3.5 Score-state policy

After a goal, both teams' score states update. Tactical multipliers depend on whether a team is leading, tied, or trailing and on match phase. These rules affect later attacking commitment, shot production, and exposure. H7 measures the resulting conditional rates rather than inserting a fixed H7 effect.

#### 3.3.6 Coordination

A match-level coordination realization modifies collective event performance. The official primary configuration gives both teams the same neutral coordination mean and distribution. Alternative coordination assumptions are evaluated in sensitivity and nested uncertainty. Coordination is an explicit modeling construct and should not be interpreted as a complete empirical measure of interpersonal chemistry.

#### 3.3.7 Fatigue

Fatigue accumulates through match exposure and affects later action probabilities. Extra time extends fatigue exposure. Substituted players leave the active process; entering players bring their own profile and initialized match state under the engine policy.

#### 3.3.8 Fouls and discipline

Foul probability depends on relevant profiles, context, referee strictness, and current state. A foul can produce no card, a yellow card, a second yellow and dismissal, or a direct red card. A booked player subsequently reduces foul propensity by the frozen behavioral-adaptation multiplier. Dismissal removes the player and updates numerical state.

#### 3.3.9 Injuries

Injuries occur stochastically with frozen incidence and severity parameters. Severe injuries can force substitution when a compatible registered substitute and legal substitution opportunity are available. The model records injury and substitution consequences but does not model clinical recovery beyond the match.

#### 3.3.10 Substitutions

Regulation permits five substitutions within three substitution windows, with the frozen additional extra-time allowance and window. Only unused, compatible registered bench players may enter. A substitute can enter once. No functional reserve is generated from the outgoing player.

#### 3.3.11 Video review and penalties

The engine includes frozen probabilities for review and overturn of relevant goal and penalty decisions. Penalty fouls and penalty conversion are modeled stochastically. Video-review logic updates the official score and event record before subsequent state-dependent behavior.

#### 3.3.12 Added time, extra time, and shootout

Added time extends the event chronology without altering the calibration exposure convention for regulation observables. If regulation ends tied, two 15-minute extra-time periods are simulated. If the score remains tied, a penalty shootout begins with five scheduled kicks per team and proceeds to sudden death subject to a high finite safeguard. No official final ends without a champion.

#### 3.3.13 H5 and H6 analysis

After batch simulation, match-level distributions are used to calculate variance differences, threshold probabilities, and upper quantiles. Bootstrap uncertainty uses match simulations as the resampling unit.

#### 3.3.14 H7 analysis

Event histories are aggregated into per-possession rates within combinations of score state, numerical state, phase, and outcome metric. Simulation-level resampling preserves dependence among events within the same match.

#### 3.3.15 Sensitivity analysis

Nine scenarios vary preregistered construction and coordination choices. The same official engine is retained. Directional reversals are reported rather than suppressed or treated automatically as release failure.

#### 3.3.16 Nested uncertainty

The nested procedure samples 160 outer parameter worlds. Within each world, 100 matches estimate outcome probability conditional on that world. The outer distribution includes uncertainty in profiles, roles, Top-N, minimum-minute thresholds, coordination, engine parameters, referee context, environment context, and match randomness. The resulting cross-world interval is not a conventional confidence interval for one fixed model.

## 4. Verification, Validation, and Reproducibility

### 4.1 Verification

Verification includes compilation, unit tests, deterministic replay, roster invariants, substitution rules, event-actor membership, elimination completion, score consistency, seed-ledger integrity, and source-hash checks.

### 4.2 Validation

Validation includes frozen benchmark calibration, external holdout evidence, orientation equivalence, seed stability, event sanity, disciplinary calibration, selection sufficiency, and repository-level authorization. Engineering validity alone cannot authorize the substantive team comparison; all scientific release gates must pass simultaneously.

### 4.3 Reproducibility

The official experiment is reproducible from the frozen repository revision and dependencies. The repository contains:

- protocol and configuration;
- canonical rosters;
- profile and engine source;
- tests and release validator;
- seed ledgers;
- compact official outputs;
- manifests with SHA-256 hashes;
- confirmatory completion evidence;
- replication preregistration and completion evidence;
- sensitivity and nested-uncertainty summaries;
- a provenance matrix connecting manuscript claims to artifacts.

A permanent archival DOI should be created before submission.

## 5. Scope and Exclusions

The model does not represent:

- continuous biomechanics or complete spatial movement;
- every off-ball interaction;
- natural-language communication;
- consciousness, subjective intention, emotion, or identity;
- endogenous learning across matches;
- complete coaching behavior;
- every historical interpersonal relationship;
- a literal physical realization of the Synthetic XI.

Outputs are conditional distributions under the implemented model. The authorized inference is a comparison between two constructed collectives under frozen assumptions. The model does not establish how either team would perform in a real physical match.
