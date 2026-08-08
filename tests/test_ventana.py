from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from ventana.aggregate import (
    bootstrap_mean,
    build_exhibits,
    diurnal_profile,
    dispersion_index,
    flow_asymmetry,
    large_share,
    sky_barcode,
)
from ventana.gates import GATE_THRESHOLDS, evaluate_minute, evaluate_session
from ventana.records import (
    SchemaError,
    load_jsonl,
    split_records,
    validate_minute,
    validate_session_header,
)

START = datetime(2026, 8, 3, 3, 0, tzinfo=timezone.utc)

SESSION_HEADER = {
    "schema": "ventana.session.v1",
    "engine": "ventana-engine-1.0.0",
    "session_id": "abc123",
    "t_start": START.isoformat().replace("+00:00", "Z"),
    "utc_offset_minutes": -180,
    "config": {"target_fps": 10},
    "calibration": {
        "sky": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 0.3},
        "street": [{"x": 0.0, "y": 0.6}, {"x": 1.0, "y": 0.6}, {"x": 1.0, "y": 1.0}],
        "line": {"a": {"x": 0.5, "y": 0.6}, "b": {"x": 0.5, "y": 1.0}},
        "facade": None,
    },
    "site_label": "prueba",
}


def make_minute(index: int = 0, *, crossings: int = 4, **overrides):
    t_start = START + timedelta(minutes=index)
    small = 1 if crossings >= 1 else 0
    large = 1 if crossings >= 2 else 0
    medium = crossings - small - large
    minute = {
        "schema": "ventana.minute.v1",
        "engine": "ventana-engine-1.0.0",
        "session_id": "abc123",
        "t_start": t_start.isoformat().replace("+00:00", "Z"),
        "t_end": (t_start + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
        "duration_s": 60.0,
        "partial": False,
        "frames": 600,
        "fps_mean": 10.0,
        "street": {
            "crossings_a": crossings,
            "crossings_b": 0,
            "crossings_total": crossings,
            "by_size": {"small": small, "medium": medium, "large": large},
            "area_histogram": [0] * 9,
            "motion_energy_mean": 0.01,
            "motion_energy_p95": 0.05,
            "tracks_active_mean": 1.2,
        },
        "sky": {
            "luminance_mean": 0.6,
            "luminance_sd": 0.01,
            "saturation_mean": 0.2,
            "blueness_mean": 0.3,
            "texture_mean": 0.02,
            "rgb_mean": [0.4, 0.6, 0.8],
            "hex": "#6699cc",
        },
        "facade": None,
        "exposure": {"clipped_high_frac": 0.01, "clipped_low_frac": 0.0},
        "quality": {
            "night": False,
            "camera_shift": False,
            "frame_ms_p95": 40.0,
            "measurable_frames": 590,
        },
    }
    minute.update(overrides)
    return minute


def make_session(minutes):
    return split_records([copy.deepcopy(SESSION_HEADER), *minutes])[0]


# --------------------------------------------------------------------- #
# Esquema                                                                #
# --------------------------------------------------------------------- #

def test_valid_records_pass_schema():
    validate_session_header(copy.deepcopy(SESSION_HEADER))
    validate_minute(make_minute())


def test_size_breakdown_must_sum_to_total():
    minute = make_minute()
    minute["street"]["by_size"]["small"] += 1
    with pytest.raises(SchemaError, match="porte"):
        validate_minute(minute)


def test_direction_breakdown_must_sum_to_total():
    minute = make_minute()
    minute["street"]["crossings_a"] += 1
    with pytest.raises(SchemaError, match="sentido"):
        validate_minute(minute)


def test_end_before_start_is_rejected():
    minute = make_minute()
    minute["t_end"] = minute["t_start"]
    with pytest.raises(SchemaError, match="posterior"):
        validate_minute(minute)


def test_calibration_without_line_is_rejected():
    header = copy.deepcopy(SESSION_HEADER)
    header["calibration"]["line"] = None
    with pytest.raises(SchemaError, match="line"):
        validate_session_header(header)


def test_minute_without_session_header_is_rejected():
    with pytest.raises(SchemaError, match="sin cabecera"):
        split_records([make_minute()])


def test_minutes_are_ordered_by_time():
    session = make_session([make_minute(5), make_minute(0), make_minute(2)])
    stamps = [m["t_start"] for m in session.minutes]
    assert stamps == sorted(stamps)


def test_local_time_uses_declared_offset():
    session = make_session([make_minute(0)])
    local = session.local_time(session.minutes[0])
    assert local.hour == 0  # 03:00 UTC con desfase -180 min
    assert local.utcoffset() == timedelta(minutes=-180)


# --------------------------------------------------------------------- #
# Compuertas                                                             #
# --------------------------------------------------------------------- #

def test_clean_minute_passes_every_gate():
    verdict = evaluate_minute(make_minute())
    assert verdict.passed
    assert verdict.failed == ()


@pytest.mark.parametrize(
    ("patch", "gate"),
    [
        ({"partial": True}, "complete_minute"),
        ({"duration_s": 31.0}, "complete_minute"),
        ({"fps_mean": 2.0}, "frame_rate"),
        ({"quality": {"camera_shift": True, "measurable_frames": 590, "night": False}}, "camera_stable"),
        ({"quality": {"camera_shift": False, "measurable_frames": 10, "night": False}}, "measurable_coverage"),
        ({"exposure": {"clipped_high_frac": 0.9, "clipped_low_frac": 0.0}}, "exposure"),
    ],
)
def test_each_gate_rejects_its_own_defect(patch, gate):
    verdict = evaluate_minute(make_minute(**patch))
    assert not verdict.passed
    assert gate in verdict.failed


def test_night_alone_does_not_invalidate_a_minute():
    minute = make_minute()
    minute["quality"]["night"] = True
    assert evaluate_minute(minute).passed


def test_session_gate_needs_enough_valid_minutes():
    few = make_session([make_minute(i) for i in range(10)])
    report = evaluate_session(few)
    assert not report.passed
    assert "session_valid_minutes_min" in report.blocking

    enough = make_session([make_minute(i) for i in range(120)])
    assert evaluate_session(enough).passed


def test_session_gate_fails_when_too_many_minutes_are_dirty():
    good = [make_minute(i) for i in range(100)]
    dirty = [make_minute(100 + i, fps_mean=1.0) for i in range(60)]
    report = evaluate_session(make_session(good + dirty))
    assert report.valid_minutes == 100
    assert report.valid_fraction < GATE_THRESHOLDS["session_valid_fraction_min"]
    assert "session_valid_fraction_min" in report.blocking
    assert report.failures_by_gate["frame_rate"] == 60


# --------------------------------------------------------------------- #
# Agregación                                                             #
# --------------------------------------------------------------------- #

def test_bootstrap_is_deterministic_for_a_given_seed():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    first = bootstrap_mean(values, seed=7, iterations=500)
    second = bootstrap_mean(values, seed=7, iterations=500)
    assert first == second
    assert first.mean == pytest.approx(3.5)
    assert first.ci_low < first.mean < first.ci_high


def test_bootstrap_without_data_reports_no_estimate():
    empty = bootstrap_mean([], seed=1, iterations=100)
    assert empty.n == 0 and empty.mean is None

    single = bootstrap_mean([2.0], seed=1, iterations=100)
    assert single.n == 1 and single.ci_low is None


def test_undefined_ratios_are_none_without_crossings():
    idle = make_minute(crossings=0)
    assert large_share(idle) is None
    assert flow_asymmetry(idle) is None


def test_crossings_are_normalised_to_a_full_minute():
    from ventana.aggregate import crossings_per_minute

    half = make_minute(crossings=3, duration_s=30.0)
    assert crossings_per_minute(half) == pytest.approx(6.0)


def test_diurnal_profile_separates_hours():
    minutes = [make_minute(i, crossings=1) for i in range(60)]  # hora local 0
    minutes += [make_minute(600 + i, crossings=9) for i in range(60)]  # hora local 10
    profile = diurnal_profile(make_session(minutes), "crossings_per_minute", seed=3, iterations=400)
    by_hour = {h["hour_local"]: h for h in profile["hours"]}
    assert by_hour[0]["mean"] == pytest.approx(1.0)
    assert by_hour[10]["mean"] == pytest.approx(9.0)
    assert by_hour[5]["n"] == 0 and by_hour[5]["mean"] is None


def test_invalid_minutes_never_reach_the_profile():
    minutes = [make_minute(i, crossings=1) for i in range(30)]
    minutes += [make_minute(30 + i, crossings=99, fps_mean=1.0) for i in range(30)]
    profile = diurnal_profile(make_session(minutes), "crossings_per_minute", seed=3, iterations=200)
    hour_zero = profile["hours"][0]
    assert hour_zero["n"] == 30
    assert hour_zero["mean"] == pytest.approx(1.0)


def test_dispersion_index_detects_a_constant_stream():
    session = make_session([make_minute(i, crossings=3) for i in range(90)])
    assert dispersion_index(session)["index"] == pytest.approx(0.0)


def test_sky_barcode_excludes_invalid_minutes_by_default():
    minutes = [make_minute(0), make_minute(1, fps_mean=1.0)]
    session = make_session(minutes)
    assert len(sky_barcode([session])) == 1
    assert len(sky_barcode([session], include_invalid=True)) == 2


def test_claim_ceiling_stays_exploratory_on_a_thin_sample():
    exhibits = build_exhibits([make_session([make_minute(i) for i in range(120)])], iterations=200)
    assert "exploratorio" in exhibits["claim_ceiling"]
    assert exhibits["minutes_valid"] == 120


# --------------------------------------------------------------------- #
# Extremo a extremo sobre el generador sintético                         #
# --------------------------------------------------------------------- #

def test_synthetic_session_survives_the_whole_pipeline(tmp_path):
    from scripts.ventana.simulate_session import build

    records = build(days=1, seed=11, start=START, offset_minutes=-180)
    path = tmp_path / "synthetic.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        import json

        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    sessions = split_records(load_jsonl(path))
    assert len(sessions) == 1
    assert len(sessions[0].minutes) == 1440

    exhibits = build_exhibits(sessions, iterations=200)
    assert exhibits["minutes_valid"] > 1400

    profile = exhibits["diurnal_profiles"]["crossings_per_minute"]["hours"]
    busiest = max(profile, key=lambda h: h["mean"] or -1)["hour_local"]
    quietest = min(
        (h for h in profile if h["mean"] is not None), key=lambda h: h["mean"]
    )["hour_local"]
    assert busiest in (8, 18)
    assert quietest in (2, 3, 4)
    # La calle sintética llega a ráfagas: la varianza supera a la media.
    assert exhibits["dispersion"]["index"] > 1.0
