from __future__ import annotations

import json
from pathlib import Path

from simulator.calibrated_core import CalibrationTargets
from simulator.official_complete_final import (
    OFFICIAL_ENGINE_VERSION,
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
)
from simulator.official_features import load_official_feature_table
from simulator.official_monte_carlo import simulate_official_finals
from simulator.official_profiles import ROSTER_PATH, build_official_bundles, team_rows


def targets() -> CalibrationTargets:
    payload = json.loads(
        Path("data/simulations/calibration/world_cup_2026_targets.json").read_text(
            encoding="utf-8"
        )
    )
    return CalibrationTargets.from_dict(payload)


def test_official_runtime_matches_frozen_rosters() -> None:
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    synthetic, real = build_official_bundles(top_n=20, minimum_minutes=900)
    frozen_synthetic = {
        str(row["player_id"])
        for row in roster["teams"]["synthetic_xi"]["registered_squad"]
    }
    frozen_real = {
        str(row["player_id"])
        for row in roster["teams"]["real_best_xi"]["registered_squad"]
    }
    assert set(synthetic.registered_ids) == frozen_synthetic
    assert set(real.registered_ids) == frozen_real
    assert len(synthetic.registered_ids) == 26
    assert len(real.registered_ids) == 26
    assert len(synthetic.team.players) == 11
    assert len(real.team.players) == 11
    assert all(row["provisional"] is False for row in team_rows(synthetic))
    assert all(row["provisional"] is False for row in team_rows(real))
    assert "explor" not in synthetic.team.name.lower()
    assert "explor" not in real.team.name.lower()


def test_minimum_minutes_sensitivity_is_exact() -> None:
    frame_180 = load_official_feature_table(180)
    frame_450 = load_official_feature_table(450)
    frame_900 = load_official_feature_table(900)
    assert frame_180.minutes_num.min() >= 180
    assert frame_450.minutes_num.min() >= 450
    assert frame_900.minutes_num.min() >= 900
    assert len(frame_180) >= len(frame_450) >= len(frame_900)
    assert (frame_180.minutes_num < 450).any()


def test_top_n_uses_real_n_when_requested_n_exceeds_role_universe() -> None:
    requested = 1_000
    synthetic, _ = build_official_bundles(
        top_n=requested,
        minimum_minutes=900,
    )
    membership = list(synthetic.membership_rows)
    assert membership
    role_sizes: dict[str, int] = {}
    declared_sizes: dict[str, int] = {}
    for row in membership:
        role = str(row["engine_role"])
        role_sizes[role] = role_sizes.get(role, 0) + 1
        declared_sizes[role] = int(row["top_n_real"])
        assert 1 <= int(row["top_n_real"]) <= requested
    assert set(role_sizes) == set(declared_sizes)
    assert all(role_sizes[role] == declared_sizes[role] for role in role_sizes)
    assert all(size < requested for size in role_sizes.values())


def test_official_config_uses_stricter_discipline_defaults() -> None:
    config = OfficialFinalConfig()
    assert config.official_engine_version == OFFICIAL_ENGINE_VERSION
    assert config.yellows_per_team_90 < 2.15
    assert config.direct_reds_per_team_90 < 0.055
    assert 0 < config.booked_player_foul_multiplier < 1


def test_one_match_uses_only_frozen_bench_and_valid_actor_semantics() -> None:
    synthetic, real = build_official_bundles(top_n=20, minimum_minutes=900)
    result = OfficialCompleteFinalSimulator(
        synthetic,
        real,
        targets(),
        OfficialFinalConfig(seed=2026072999),
    ).simulate(keep_timeline=True)
    runtime = result.official_runtime
    assert set(runtime["used_home_bench_ids"]) <= set(synthetic.registered_ids)
    assert set(runtime["used_away_bench_ids"]) <= set(real.registered_ids)
    assert len(runtime["used_home_bench_ids"]) == len(set(runtime["used_home_bench_ids"]))
    assert len(runtime["used_away_bench_ids"]) == len(set(runtime["used_away_bench_ids"]))
    assert result.official_diagnostics["actor_membership_failures"] == []
    assert result.timeline
    for event in result.timeline:
        assert "acting_team" in event
        assert "affected_team" in event
        assert "possession_team" in event
        assert "actor_team" in event
        assert "actor_membership_valid" in event
        if event["actor_membership_valid"] is not None:
            assert event["actor_membership_valid"] is True


def test_small_monte_carlo_is_deterministic_and_sane() -> None:
    experiment = json.loads(
        Path("config/official_experiment_v1.json").read_text(encoding="utf-8")
    )
    synthetic, real = build_official_bundles(top_n=20, minimum_minutes=900)
    first = simulate_official_finals(
        synthetic,
        real,
        targets(),
        experiment,
        simulations=24,
        seed=2026072988,
        audit_sample_size=24,
    )
    second = simulate_official_finals(
        synthetic,
        real,
        targets(),
        experiment,
        simulations=24,
        seed=2026072988,
        audit_sample_size=24,
    )
    assert first["match_seed_ledger_sha256"] == second["match_seed_ledger_sha256"]
    assert first["home_champion_probability"] == second["home_champion_probability"]
    assert first["event_sanity_gate"]["passed"] is True
    assert first["version"] == OFFICIAL_ENGINE_VERSION
    assert first["rows"] == second["rows"]
