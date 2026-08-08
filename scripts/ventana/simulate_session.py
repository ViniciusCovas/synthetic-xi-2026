#!/usr/bin/env python3
"""Genera una sesión sintética de Ventana con la forma exacta del export real.

Sirve para ejercitar la validación, la agregación y el tablero antes de que el
teléfono haya observado un solo minuto. Los ficheros que produce llevan la
etiqueta ``SINTÉTICO`` en la cabecera y nunca deben mezclarse con observación.

Uso:
    python scripts/ventana/simulate_session.py --days 3 \
        --output data/ventana/synthetic/ventana_synthetic.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ventana.aggregate import DEFAULT_SEED  # noqa: E402

SYNTHETIC_LABEL = "SINTÉTICO — no es observación"


def diurnal_traffic(hour_float: float, weekend: bool) -> float:
    """Intensidad media de cruces por minuto según la hora local."""
    base = 0.35 + 2.6 * math.exp(-((hour_float - 8.4) ** 2) / 1.6)
    base += 2.9 * math.exp(-((hour_float - 18.3) ** 2) / 2.4)
    base += 1.1 * math.exp(-((hour_float - 13.0) ** 2) / 5.0)
    night = 0.9 / (1 + math.exp(-(hour_float - 6.0) * 2.2)) / (
        1 + math.exp((hour_float - 23.0) * 2.2)
    )
    value = (base + night) * (0.55 if weekend else 1.0)
    return max(0.02, value)


def daylight(hour_float: float) -> float:
    """Luz diurna normalizada, con amanecer sobre las 6:30 y ocaso a las 20:30."""
    if hour_float < 5.5 or hour_float > 21.5:
        return 0.0
    return max(0.0, math.sin(math.pi * (hour_float - 5.5) / 16.0)) ** 0.7


def build(days: int, seed: int, start: datetime, offset_minutes: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    session_id = f"synthetic{seed:08x}"
    calibration = {
        "sky": {"x0": 0.05, "y0": 0.02, "x1": 0.95, "y1": 0.30},
        "street": [
            {"x": 0.02, "y": 0.62},
            {"x": 0.98, "y": 0.58},
            {"x": 0.98, "y": 0.97},
            {"x": 0.02, "y": 0.97},
        ],
        "line": {"a": {"x": 0.50, "y": 0.58}, "b": {"x": 0.50, "y": 0.97}},
        "facade": {"x0": 0.06, "y0": 0.30, "x1": 0.62, "y1": 0.56},
    }
    header = {
        "schema": "ventana.session.v1",
        "engine": "ventana-engine-1.0.0",
        "session_id": session_id,
        "t_start": start.isoformat().replace("+00:00", "Z"),
        "timezone": "synthetic/fixed-offset",
        "utc_offset_minutes": offset_minutes,
        "device": {
            "user_agent": "synthetic-generator",
            "capture_width": 1280,
            "capture_height": 720,
            "capture_fps": 30,
        },
        "analysis": {"width": 320, "height": 180},
        "config": {"target_fps": 10, "generator_seed": seed},
        "calibration": calibration,
        "site_label": SYNTHETIC_LABEL,
    }

    records: list[dict] = [header]
    offset = timedelta(minutes=offset_minutes)
    total_minutes = days * 24 * 60
    # Un desplazamiento de cámara por sesión, para que la compuerta correspondiente
    # tenga algo real que descartar.
    shift_at = int(rng.integers(60, max(61, total_minutes - 60)))

    for index in range(total_minutes):
        t_start = start + timedelta(minutes=index)
        local = t_start + offset
        hour_float = local.hour + local.minute / 60.0
        weekend = local.weekday() >= 5

        lam = diurnal_traffic(hour_float, weekend)
        # Sobredispersión: la calle llega a ráfagas tras cada ciclo de semáforo.
        rate = float(rng.gamma(shape=4.0, scale=lam / 4.0))
        total = int(rng.poisson(rate))
        toward_a = int(rng.binomial(total, 0.53)) if total else 0

        large = int(rng.binomial(total, 0.06)) if total else 0
        small = int(rng.binomial(total - large, 0.22)) if total - large else 0
        medium = total - large - small

        light = daylight(hour_float)
        cloud = float(np.clip(rng.normal(0.35, 0.18), 0.0, 1.0))
        luminance = float(np.clip(0.04 + 0.80 * light * (1 - 0.35 * cloud) + rng.normal(0, 0.01), 0, 1))
        blueness = float(np.clip(0.34 * (1 - cloud) * (0.3 + 0.7 * light) + rng.normal(0, 0.02), -1, 1))
        saturation = float(np.clip(0.10 + 0.45 * blueness + rng.normal(0, 0.02), 0, 1))
        texture = float(np.clip(0.015 + 0.13 * cloud * light + rng.normal(0, 0.006), 0, 1))
        red = float(np.clip(luminance * (1 - 0.55 * blueness), 0, 1))
        blue = float(np.clip(luminance * (1 + 0.55 * blueness), 0, 1))
        green = float(np.clip(luminance, 0, 1))

        # Ventanas encendidas: el barrio se acuesta tarde y madruga poco.
        evening = 1 / (1 + math.exp(-(hour_float - 18.5) * 1.8))
        late = 1 / (1 + math.exp((hour_float - 24.5) * 1.4))
        morning = 1 / (1 + math.exp(-(hour_float - 6.5) * 2.0)) * (
            1 / (1 + math.exp((hour_float - 9.0) * 2.0))
        )
        lit = max(0.0, 14.0 * evening * late + 6.0 * morning) * (1 - light * 0.85)
        lit_windows = float(max(0.0, rng.normal(lit, 1.1)))

        fps = float(np.clip(rng.normal(9.6, 0.6), 2.0, 12.0))
        frames = int(round(fps * 60))
        camera_shift = index in (shift_at, shift_at + 1)

        records.append(
            {
                "schema": "ventana.minute.v1",
                "engine": "ventana-engine-1.0.0",
                "session_id": session_id,
                "t_start": t_start.isoformat().replace("+00:00", "Z"),
                "t_end": (t_start + timedelta(seconds=60)).isoformat().replace("+00:00", "Z"),
                "duration_s": 60.0,
                "partial": False,
                "frames": frames,
                "fps_mean": round(fps, 2),
                "street": {
                    "crossings_a": toward_a,
                    "crossings_b": total - toward_a,
                    "crossings_total": total,
                    "by_size": {"small": small, "medium": medium, "large": large},
                    "area_histogram": [small, medium, large, 0, 0, 0, 0, 0, 0],
                    "motion_energy_mean": round(float(np.clip(0.002 + 0.010 * lam + rng.normal(0, 0.001), 0, 1)), 5),
                    "motion_energy_p95": round(float(np.clip(0.01 + 0.05 * lam + rng.normal(0, 0.004), 0, 1)), 5),
                    "tracks_active_mean": round(float(max(0.0, rng.normal(lam * 1.4, 0.3))), 2),
                },
                "sky": {
                    "luminance_mean": round(luminance, 4),
                    "luminance_sd": round(float(abs(rng.normal(0.012, 0.004))), 4),
                    "saturation_mean": round(saturation, 4),
                    "blueness_mean": round(blueness, 4),
                    "texture_mean": round(texture, 4),
                    "rgb_mean": [round(red, 4), round(green, 4), round(blue, 4)],
                    "hex": "#{:02x}{:02x}{:02x}".format(
                        int(red * 255), int(green * 255), int(blue * 255)
                    ),
                },
                "facade": {
                    "lit_fraction_mean": round(lit_windows / 400.0, 5),
                    "lit_windows_mean": round(lit_windows, 2),
                    "lit_windows_p95": round(lit_windows * 1.2, 2),
                },
                "exposure": {
                    "clipped_high_frac": round(float(np.clip(rng.normal(0.01 + 0.05 * light, 0.01), 0, 1)), 5),
                    "clipped_low_frac": round(float(np.clip(rng.normal(0.02 * (1 - light), 0.01), 0, 1)), 5),
                },
                "quality": {
                    "night": light < 0.02,
                    "camera_shift": camera_shift,
                    "frame_ms_p95": round(float(rng.normal(46, 6)), 1),
                    "measurable_frames": 0 if camera_shift else frames - int(rng.integers(0, 12)),
                },
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--utc-offset-minutes", type=int, default=-180)
    parser.add_argument(
        "--start",
        type=str,
        default="2026-08-03T03:00:00Z",
        help="inicio en UTC; el valor por defecto cae en lunes hora local",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/ventana/synthetic/ventana_synthetic.jsonl"),
    )
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(timezone.utc)
    records = build(args.days, args.seed, start, args.utc_offset_minutes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"minutos sintéticos: {len(records) - 1}")
    print(f"escrito: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
