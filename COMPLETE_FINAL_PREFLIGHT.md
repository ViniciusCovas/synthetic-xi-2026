# Complete Final Preflight v1

## Purpose

This preflight is the final fail-closed layer before the confirmatory distribution of 10,000 Synthetic XI versus Real Best XI matches. It does not alter player abilities, selection thresholds or simulator weights. It freezes missing operational context and checks the frozen engine against the completed FIFA World Cup 2026 event record.

The definitive distribution is blocked until this preflight and a separate 2,000-match validation both pass.

## Frozen components

### Teams and bench

- 26 registered instances per team;
- 11 named starters and 15 named bench players/instances;
- at least three goalkeepers in each registered squad;
- no duplicate real player IDs;
- fixed penalty order;
- fixed emergency goalkeeper order;
- Real Best XI selected mechanically from the canonical fully covered candidates by frozen conservative score;
- Synthetic XI represented by independent named instances of the eight frozen positional archetypes, with no new ability parameter.

### Competition rules

The reference is a FIFA World Cup 2026 knockout match:

- five substitutions in normal time and three normal-time windows;
- one additional substitution and window in extra time;
- two 15-minute extra-time periods;
- five initial shootout kicks followed by sudden death;
- 26-player registered squad, including at least three goalkeepers;
- three-minute hydration breaks in both halves, independent of weather.

The concussion rule is recorded as a limitation: the current engine represents it through its injury-substitution policy rather than through a separately estimated additional process.

### Referee

The confirmatory primary condition uses a neutral latent median referee. A named official is not predicted. Permissive, median and strict profiles are retained only as paired sensitivity scenarios. The same sampled profile applies to both teams and cannot be chosen after the result.

### Environment and World Cup 2026 weather record

`scripts/scientific/build_world_cup_2026_weather_record.py`:

1. obtains the 2026 World Cup fixture, kick-off and venue metadata from the configured football-data provider;
2. maps every fixture to one of the 16 official host-city stadium areas;
3. requests hourly weather for the kick-off hour through four hours after kick-off;
4. prefers Open-Meteo Historical Weather API reanalysis;
5. uses the Open-Meteo Historical Forecast archive only for recent matches that are not yet present in reanalysis;
6. never imputes an unavailable weather value;
7. labels roofed or covered venues so outdoor weather is not misrepresented as measured pitch conditions.

Recorded variables:

- temperature;
- relative humidity;
- apparent temperature;
- precipitation;
- wind speed and gusts;
- weather code;
- evidence grade;
- venue exposure class.

Weather is retained as a paired contextual/sensitivity distribution. No unvalidated team acclimatisation or player-performance multiplier is introduced.

Official references:

- FIFA schedule and venues: `https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums`
- FIFA squad rules: `https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/squad-lists-number-date`
- FIFA substitution history/rules: `https://www.fifa.com/en/tournaments/mens/worldcup/articles/substitutions-substitutes-rule-changes-history`
- FIFA hydration-break policy: `https://inside.fifa.com/organisation/news/hydration-breaks-world-cup-2026-player-welfare`
- Open-Meteo historical weather documentation: `https://open-meteo.com/en/docs/historical-weather-api`
- Open-Meteo historical forecast documentation: `https://open-meteo.com/en/docs/historical-forecast-api`

## World Cup event benchmark

`scripts/scientific/build_world_cup_2026_event_benchmark.py` freezes match-level distributions for:

- regulation goals;
- shots and shots on target;
- fouls and corners;
- yellow and red cards;
- substitutions;
- penalty events;
- VAR events;
- observable injury substitutions;
- extra-time and shootout frequency among knockout matches.

The model is not fitted after this record is read. Frozen error limits live in `config/complete_final_preflight_tolerances_v1.json`. Every gating metric must remain within its preregistered limit. VAR, injuries, awarded penalties and stoppage time remain descriptive when provider completeness is insufficient.

## Execution order

1. Freeze rosters and policies.
2. Build the 104-match weather record.
3. Build and normalize the 104-match event benchmark.
4. Evaluate the outcome-blind core preflight.
5. If the core passes, run the isolated 2,000-match validation.
6. Finalize the preflight status.
7. Refresh the release gate with `--evaluate-only`; do not execute 10,000 matches.
8. Publish hashes, records, metric audit and blocker list.

GitHub Actions:

`Actions → Complete Final Preflight and World Cup Weather → Run workflow → main → Run workflow`

## Authorization rule

The 10,000-match runner is authorized only when:

- all previous canonical scientific gates remain true;
- both 26-player rosters are frozen and valid;
- competition and referee policies are frozen;
- World Cup weather coverage reaches the declared thresholds;
- World Cup event-distribution compatibility passes every frozen tolerance;
- the isolated 2,000-match validation passes.

A green workflow means the audit pipeline completed. The authoritative scientific result is the boolean `final_10000_authorized` in `data/model_readiness/complete_final_preflight_status.json`.
