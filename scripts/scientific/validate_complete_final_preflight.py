#!/usr/bin/env python3
"""Validate the final 10,000-match preflight without tuning the model.

The decision is fail-closed. World Cup 2026 event and weather records are used
as external context/benchmark evidence. The script never updates abilities,
weights, thresholds or calibration parameters.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "data/model_readiness"
CONTEXT = ROOT / "data/context"
SIM = ROOT / "data/simulations/complete_final_v1"
CONFIG = ROOT / "config/complete_final_preflight_v1.json"
TOLERANCES = ROOT / "config/complete_final_preflight_tolerances_v1.json"
ROSTERS = MODEL / "complete_final_rosters_v1.json"
WEATHER = CONTEXT / "world_cup_2026_weather_summary.json"
EVENT_SUMMARY = CONTEXT / "world_cup_2026_event_benchmark_summary.json"
EVENT_MATCHES = CONTEXT / "world_cup_2026_event_benchmark_by_match.csv"
STATUS_OUT = MODEL / "complete_final_preflight_status.json"
AUDIT_OUT = CONTEXT / "complete_final_preflight_metric_audit.csv"


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean_from(distributions: dict[str, Any], preferred: list[str]) -> tuple[str | None, float | None, float]:
    for name in preferred:
        entry = distributions.get(name) or {}
        if entry.get("mean") is not None:
            return name, float(entry["mean"]), float(entry.get("coverage", 0.0))
    return None, None, 0.0


def role_from_round(value: object) -> bool:
    text = str(value or "").casefold()
    return bool(text) and "group" not in text and any(token in text for token in ["round", "final", "quarter", "semi", "3rd", "third"])


def main() -> int:
    config = load(CONFIG)
    tolerances = load(TOLERANCES)
    rosters = load(ROSTERS)
    weather = load(WEATHER)
    events = load(EVENT_SUMMARY)
    engineering = load(SIM / "engineering_validation_snapshot.json")
    selection = load(MODEL / "selection_sufficiency_status.json")
    scientific = load(MODEL / "scientific_validation_status.json")

    teams = rosters.get("teams") or {}
    synthetic = teams.get("synthetic_xi") or {}
    real = teams.get("real_best_xi") or {}
    real_squad = real.get("registered_squad") or []
    synthetic_squad = synthetic.get("registered_squad") or []
    team_checks = {
        "rosters_frozen": rosters.get("status") == "complete_final_rosters_frozen",
        "real_squad_26": len(real_squad) == 26,
        "real_unique_26": len({str(player.get("player_id")) for player in real_squad}) == 26,
        "real_minimum_three_goalkeepers": sum(player.get("resolved_role") == "GK" for player in real_squad) >= 3,
        "synthetic_squad_26": len(synthetic_squad) == 26,
        "synthetic_unique_26": len({str(player.get("player_id")) for player in synthetic_squad}) == 26,
        "synthetic_minimum_three_goalkeepers": sum(player.get("resolved_role") == "GK" for player in synthetic_squad) >= 3,
        "penalty_orders_frozen": bool(real.get("penalty_order_player_ids")) and bool(synthetic.get("penalty_order_player_ids")),
        "emergency_goalkeepers_frozen": bool(real.get("emergency_goalkeeper_order_player_ids")) and bool(synthetic.get("emergency_goalkeeper_order_player_ids")),
    }
    team_gate = all(team_checks.values())

    rules = config.get("competition_rules") or {}
    hydration = rules.get("mandatory_hydration_breaks") or {}
    rules_checks = {
        "squad_size_26": rules.get("registered_squad_size") == 26,
        "starting_xi_11": rules.get("starting_players") == 11,
        "five_normal_substitutions": rules.get("normal_time_substitutions") == 5,
        "three_normal_windows": rules.get("normal_time_substitution_windows") == 3,
        "extra_time_substitution": rules.get("extra_time_additional_substitution") == 1,
        "two_extra_time_periods": rules.get("extra_time_periods") == 2 and rules.get("extra_time_period_minutes") == 15,
        "shootout_sudden_death": bool(rules.get("shootout_sudden_death")),
        "hydration_breaks_recorded": bool(hydration.get("enabled")) and hydration.get("duration_minutes") == 3,
    }
    rules_gate = all(rules_checks.values())

    referee = config.get("referee_context") or {}
    scenarios = referee.get("scenario_sensitivity") or []
    referee_checks = {
        "neutral_primary_profile": referee.get("primary_profile") == "median_neutral",
        "paired_draw": bool(referee.get("paired_draw")),
        "three_declared_scenarios": {item.get("name") for item in scenarios} == {"permissive", "median_neutral", "strict"},
        "weights_sum_one": abs(sum(float(item.get("weight", 0.0)) for item in scenarios) - 1.0) < 1e-9,
        "sensitivity_only": bool(referee.get("scenario_parameters_are_sensitivity_only")),
        "named_referee_claim_forbidden": bool(referee.get("named_referee_claim_forbidden")),
    }
    referee_gate = all(referee_checks.values())

    coverage_req = tolerances.get("coverage_requirements") or {}
    weather_gate = (
        weather.get("status") == "world_cup_2026_weather_record_complete"
        and float(weather.get("weather_coverage", 0.0)) >= float(coverage_req.get("weather_any_grade", 0.90))
        and float(weather.get("reanalysis_coverage", 0.0)) >= float(coverage_req.get("weather_reanalysis_grade_a", 0.85))
        and weather.get("missing_weather_imputed") is False
        and weather.get("outdoor_weather_used_as_indoor_pitch_measurement") is False
    )

    observed = (engineering.get("checks") or {}).get("regulation_distribution_calibration", {}).get("observed", {})
    distributions = events.get("distributions") or {}
    error_limits = tolerances.get("absolute_mean_error_limits") or {}
    metric_specs = [
        ("regulation_goals", "mean_regulation_goals", ["fulltime_goals"]),
        ("regulation_shots", "mean_regulation_shots", ["shots"]),
        ("regulation_shots_on_target", "mean_regulation_shots_on_target", ["shots_on_target"]),
        ("fouls", "mean_total_fouls", ["fouls"]),
        ("yellow_cards", "mean_total_yellows", ["yellow_cards_stat", "event_yellow_cards"]),
        ("red_cards", "mean_total_reds", ["red_cards_stat", "event_red_cards"]),
        ("substitutions", "mean_total_substitutions", ["substitutions"]),
    ]
    audit_rows: list[dict[str, Any]] = []
    core_coverage_min = float(coverage_req.get("core_event_metric", 0.80))
    for label, engine_key, benchmark_names in metric_specs:
        source_name, benchmark_mean, coverage = mean_from(distributions, benchmark_names)
        engine_mean = observed.get(engine_key)
        limit = float(error_limits.get(label, -1.0))
        absolute_error = abs(float(engine_mean) - benchmark_mean) if engine_mean is not None and benchmark_mean is not None else None
        passed = bool(absolute_error is not None and limit >= 0 and absolute_error <= limit and coverage >= core_coverage_min)
        audit_rows.append({
            "metric": label,
            "engine_metric": engine_key,
            "benchmark_metric": source_name,
            "engine_mean": engine_mean,
            "benchmark_mean": benchmark_mean,
            "absolute_error": absolute_error,
            "frozen_error_limit": limit,
            "benchmark_coverage": coverage,
            "minimum_coverage": core_coverage_min,
            "passed": passed,
        })

    knockout_matches = 0
    knockout_et = knockout_pen = 0
    if EVENT_MATCHES.exists():
        frame = pd.read_csv(EVENT_MATCHES, low_memory=False)
        mask = frame.get("round", pd.Series("", index=frame.index)).map(role_from_round)
        knockout = frame.loc[mask]
        knockout_matches = int(len(knockout))
        if knockout_matches:
            knockout_et = int(knockout.get("extra_time_played", False).astype(str).str.lower().isin({"true", "1"}).sum())
            knockout_pen = int(knockout.get("shootout_played", False).astype(str).str.lower().isin({"true", "1"}).sum())
    for label, engine_key, count in [
        ("extra_time_frequency_knockout", "extra_time_probability", knockout_et),
        ("shootout_frequency_knockout", "penalty_shootout_probability", knockout_pen),
    ]:
        benchmark_mean = count / knockout_matches if knockout_matches else None
        engine_mean = observed.get(engine_key)
        limit = float(error_limits.get(label, -1.0))
        absolute_error = abs(float(engine_mean) - benchmark_mean) if engine_mean is not None and benchmark_mean is not None else None
        passed = bool(absolute_error is not None and limit >= 0 and absolute_error <= limit and knockout_matches >= 20)
        audit_rows.append({
            "metric": label,
            "engine_metric": engine_key,
            "benchmark_metric": "knockout_match_frequency",
            "engine_mean": engine_mean,
            "benchmark_mean": benchmark_mean,
            "absolute_error": absolute_error,
            "frozen_error_limit": limit,
            "benchmark_coverage": knockout_matches,
            "minimum_coverage": 20,
            "passed": passed,
        })

    audit = pd.DataFrame(audit_rows)
    CONTEXT.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_OUT, index=False)
    event_gate = (
        events.get("status") == "world_cup_2026_event_benchmark_complete"
        and float(events.get("fixture_coverage", 0.0)) >= float(coverage_req.get("world_cup_fixtures", 0.90))
        and bool(len(audit))
        and bool(audit.passed.all())
        and events.get("model_parameters_changed") is False
        and events.get("selection_thresholds_changed") is False
    )

    canonical_checks = {
        "engineering_gate": bool(engineering.get("engineering_gate_passed")),
        "selection_sufficiency": bool(selection.get("selection_sufficiency_gate_passed")) and selection.get("unresolved_players") == 0,
        "scientific_comparison_allowed": bool(scientific.get("final_team_comparison_allowed")),
        "arxiv_results_ready": bool(scientific.get("arxiv_results_ready")),
    }
    canonical_gate = all(canonical_checks.values())
    methodological = config.get("methodological_policy") or {}
    freeze_checks = {
        "outcome_blind": bool(methodological.get("outcome_blind")),
        "no_model_weight_changes": bool(methodological.get("no_model_weight_changes")),
        "no_selection_threshold_changes": bool(methodological.get("no_selection_threshold_changes")),
        "no_post_result_tuning": bool(methodological.get("no_post_result_tuning")),
        "benchmark_declares_no_parameter_update": bool(tolerances.get("parameter_update_allowed_after_benchmark") is False),
    }
    freeze_gate = all(freeze_checks.values())

    gates = {
        "canonical_scientific_gates": canonical_gate,
        "team_and_bench_freeze": team_gate,
        "competition_rules_freeze": rules_gate,
        "neutral_referee_context": referee_gate,
        "world_cup_2026_weather_record": weather_gate,
        "world_cup_2026_event_distribution_compatibility": event_gate,
        "outcome_blind_freeze": freeze_gate,
    }
    blockers = [name for name, passed in gates.items() if not passed]
    passed = not blockers
    status = {
        "status": "complete_final_preflight_passed" if passed else "complete_final_preflight_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "preflight_version": config.get("preflight_version"),
        "complete_final_preflight_passed": passed,
        "final_10000_authorized": passed,
        "gates": gates,
        "blocking_gates": blockers,
        "team_checks": team_checks,
        "rules_checks": rules_checks,
        "referee_checks": referee_checks,
        "canonical_checks": canonical_checks,
        "freeze_checks": freeze_checks,
        "weather_summary": {
            "matches_in_record": weather.get("matches_in_record"),
            "matches_with_weather": weather.get("matches_with_weather"),
            "weather_coverage": weather.get("weather_coverage"),
            "reanalysis_coverage": weather.get("reanalysis_coverage"),
            "heat_band_counts_all_venues": weather.get("heat_band_counts_all_venues"),
            "open_air_temperature_mean_c": weather.get("open_air_temperature_mean_c"),
            "open_air_apparent_temperature_max_c": weather.get("open_air_apparent_temperature_max_c"),
        },
        "event_benchmark": {
            "fixtures": events.get("fixtures_returned_with_bundle"),
            "fixture_coverage": events.get("fixture_coverage"),
            "knockout_matches": knockout_matches,
            "knockout_extra_time_matches": knockout_et,
            "knockout_shootout_matches": knockout_pen,
            "all_frozen_metric_checks_passed": bool(len(audit)) and bool(audit.passed.all()),
            "audit_csv": str(AUDIT_OUT.relative_to(ROOT)),
        },
        "environment_model_use": {
            "weather_recorded": True,
            "primary_team_specific_weather_advantage": False,
            "performance_modifier_added": False,
            "use_in_final": "sampled paired context and sensitivity label; no unvalidated ability modifier",
        },
        "declared_limitations": [
            "The referee is a neutral latent profile, not a prediction about a named official.",
            "Weather at roofed or covered venues is outdoor context, not measured pitch climate.",
            "Weather is not converted into a new player-performance modifier without external validation.",
            "VAR, observable injuries and stoppage time remain descriptive where provider completeness is insufficient.",
            "The concussion substitution rule is represented by the injury substitution policy rather than a separately estimated process."
        ],
        "source_hashes": {
            str(CONFIG.relative_to(ROOT)): sha(CONFIG),
            str(TOLERANCES.relative_to(ROOT)): sha(TOLERANCES),
            str(ROSTERS.relative_to(ROOT)): sha(ROSTERS),
            str(WEATHER.relative_to(ROOT)): sha(WEATHER),
            str(EVENT_SUMMARY.relative_to(ROOT)): sha(EVENT_SUMMARY),
            str(EVENT_MATCHES.relative_to(ROOT)): sha(EVENT_MATCHES),
        },
        "model_parameters_changed": False,
        "selection_thresholds_changed": False,
        "policy": "The definitive 10,000-match distribution remains blocked unless every preflight gate is affirmative.",
    }
    MODEL.mkdir(parents=True, exist_ok=True)
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
