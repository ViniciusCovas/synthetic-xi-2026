"""Agregación e inferencia sobre los minutos válidos de Ventana.

Todo intervalo de confianza es un bootstrap de percentiles sobre la media, con
semilla explícita: dos ejecuciones con la misma semilla y los mismos datos
producen exactamente el mismo número.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from ventana.gates import evaluate_minute, evaluate_session
from ventana.records import Session

DEFAULT_BOOTSTRAP = 10_000
DEFAULT_SEED = 20260808

Extractor = Callable[[dict[str, Any]], float | None]


@dataclass(frozen=True)
class Estimate:
    """Media puntual con su intervalo de confianza bootstrap."""

    n: int
    mean: float | None
    ci_low: float | None
    ci_high: float | None
    sd: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean": _round(self.mean, 4),
            "ci95_low": _round(self.ci_low, 4),
            "ci95_high": _round(self.ci_high, 4),
            "sd": _round(self.sd, 4),
        }


def _round(value: float | None, digits: int) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return round(float(value), digits)


def bootstrap_mean(
    values: Sequence[float],
    *,
    seed: int = DEFAULT_SEED,
    iterations: int = DEFAULT_BOOTSTRAP,
    alpha: float = 0.05,
) -> Estimate:
    """Media e IC del 95% por bootstrap de percentiles.

    Con menos de dos observaciones no hay incertidumbre estimable: se devuelve
    la media sin intervalo en lugar de inventar uno degenerado.
    """
    array = np.asarray([v for v in values if v is not None], dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return Estimate(n=0, mean=None, ci_low=None, ci_high=None, sd=None)
    if array.size == 1:
        return Estimate(n=1, mean=float(array[0]), ci_low=None, ci_high=None, sd=None)

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, array.size, size=(iterations, array.size))
    means = array[draws].mean(axis=1)
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return Estimate(
        n=int(array.size),
        mean=float(array.mean()),
        ci_low=float(low),
        ci_high=float(high),
        sd=float(array.std(ddof=1)),
    )


# --------------------------------------------------------------------- #
# Extractores de magnitudes                                              #
# --------------------------------------------------------------------- #

def crossings_per_minute(minute: dict[str, Any]) -> float:
    """Cruces normalizados a un minuto exacto de observación."""
    duration = float(minute.get("duration_s") or 60.0)
    return float(minute["street"]["crossings_total"]) * 60.0 / duration


def large_share(minute: dict[str, Any]) -> float | None:
    """Fracción de cruces de porte grande; indefinida si no hubo cruces."""
    by_size = minute["street"]["by_size"]
    total = float(minute["street"]["crossings_total"])
    if total <= 0:
        return None
    return float(by_size["large"]) / total


def flow_asymmetry(minute: dict[str, Any]) -> float | None:
    """Asimetría de sentido en [-1, 1]; indefinida si no hubo cruces."""
    street = minute["street"]
    total = float(street["crossings_total"])
    if total <= 0:
        return None
    return (float(street["crossings_a"]) - float(street["crossings_b"])) / total


def motion_energy(minute: dict[str, Any]) -> float | None:
    return _maybe_float(minute["street"].get("motion_energy_mean"))


def sky_luminance(minute: dict[str, Any]) -> float | None:
    sky = minute.get("sky")
    return _maybe_float(sky.get("luminance_mean")) if sky else None


def sky_blueness(minute: dict[str, Any]) -> float | None:
    sky = minute.get("sky")
    return _maybe_float(sky.get("blueness_mean")) if sky else None


def sky_texture(minute: dict[str, Any]) -> float | None:
    sky = minute.get("sky")
    return _maybe_float(sky.get("texture_mean")) if sky else None


def lit_windows(minute: dict[str, Any]) -> float | None:
    facade = minute.get("facade")
    return _maybe_float(facade.get("lit_windows_mean")) if facade else None


def _maybe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


METRICS: dict[str, Extractor] = {
    "crossings_per_minute": crossings_per_minute,
    "large_share": large_share,
    "flow_asymmetry": flow_asymmetry,
    "motion_energy": motion_energy,
    "sky_luminance": sky_luminance,
    "sky_blueness": sky_blueness,
    "sky_texture": sky_texture,
    "lit_windows": lit_windows,
}


# --------------------------------------------------------------------- #
# Perfiles                                                               #
# --------------------------------------------------------------------- #

def as_sessions(sessions: Session | Iterable[Session]) -> list[Session]:
    """Acepta indistintamente una sesión suelta o una colección de ellas."""
    if isinstance(sessions, Session):
        return [sessions]
    return list(sessions)


def valid_pairs(sessions: Session | Iterable[Session]) -> list[tuple[Session, dict[str, Any]]]:
    """Minutos que superan las compuertas, junto a su sesión de origen."""
    pairs: list[tuple[Session, dict[str, Any]]] = []
    for session in as_sessions(sessions):
        for minute in session.minutes:
            if evaluate_minute(minute).passed:
                pairs.append((session, minute))
    return pairs


def diurnal_profile(
    sessions: Session | Iterable[Session],
    metric: str,
    *,
    seed: int = DEFAULT_SEED,
    iterations: int = DEFAULT_BOOTSTRAP,
) -> dict[str, Any]:
    """Perfil de una magnitud por hora local del día, con IC por hora."""
    if metric not in METRICS:
        raise KeyError(f"magnitud desconocida: {metric!r}")
    extractor = METRICS[metric]

    buckets: dict[int, list[float]] = defaultdict(list)
    for session, minute in valid_pairs(sessions):
        value = extractor(minute)
        if value is None:
            continue
        buckets[session.local_time(minute).hour].append(value)

    hours = []
    for hour in range(24):
        values = buckets.get(hour, [])
        # Semilla derivada de la hora: cada celda es reproducible por separado,
        # y añadir horas nuevas no altera los intervalos ya publicados.
        estimate = bootstrap_mean(values, seed=seed + hour, iterations=iterations)
        hours.append({"hour_local": hour, **estimate.to_dict()})

    return {
        "metric": metric,
        "seed": seed,
        "bootstrap_iterations": iterations,
        "minutes_used": sum(len(v) for v in buckets.values()),
        "hours": hours,
    }


def weekday_contrast(
    sessions: Session | Iterable[Session],
    metric: str = "crossings_per_minute",
    *,
    seed: int = DEFAULT_SEED,
    iterations: int = DEFAULT_BOOTSTRAP,
) -> dict[str, Any]:
    """Contraste laborable frente a fin de semana para una magnitud."""
    extractor = METRICS[metric]
    groups: dict[str, list[float]] = {"weekday": [], "weekend": []}
    for session, minute in valid_pairs(sessions):
        value = extractor(minute)
        if value is None:
            continue
        local = session.local_time(minute)
        groups["weekend" if local.weekday() >= 5 else "weekday"].append(value)

    weekday = bootstrap_mean(groups["weekday"], seed=seed + 101, iterations=iterations)
    weekend = bootstrap_mean(groups["weekend"], seed=seed + 202, iterations=iterations)
    difference = None
    if weekday.mean is not None and weekend.mean is not None:
        difference = weekday.mean - weekend.mean

    return {
        "metric": metric,
        "weekday": weekday.to_dict(),
        "weekend": weekend.to_dict(),
        "difference_weekday_minus_weekend": _round(difference, 4),
        "comparable": weekday.n >= 30 and weekend.n >= 30,
    }


def dispersion_index(sessions: Session | Iterable[Session]) -> dict[str, Any]:
    """Índice de dispersión de los cruces por minuto.

    Un valor cercano a 1 indica llegadas compatibles con un proceso de Poisson;
    por encima de 1, tráfico a ráfagas —lo típico de una calle con semáforo.
    """
    counts = [float(m["street"]["crossings_total"]) for _, m in valid_pairs(sessions)]
    if len(counts) < 2:
        return {"n": len(counts), "mean": None, "variance": None, "index": None}
    array = np.asarray(counts, dtype=float)
    mean = float(array.mean())
    variance = float(array.var(ddof=1))
    return {
        "n": int(array.size),
        "mean": _round(mean, 4),
        "variance": _round(variance, 4),
        "index": _round(variance / mean, 4) if mean > 0 else None,
    }


def sky_barcode(
    sessions: Session | Iterable[Session], *, include_invalid: bool = False
) -> list[dict[str, Any]]:
    """Serie ordenada de colores medios de cielo, uno por minuto.

    Es la base del retrato del día: una franja donde cada píxel vertical es un
    minuto real de cielo medido desde la ventana.
    """
    rows: list[dict[str, Any]] = []
    for session in as_sessions(sessions):
        for minute in session.minutes:
            sky = minute.get("sky")
            if not sky or not sky.get("hex"):
                continue
            passed = evaluate_minute(minute).passed
            if not passed and not include_invalid:
                continue
            local = session.local_time(minute)
            rows.append(
                {
                    "session_id": session.session_id,
                    "t_local": local.isoformat(),
                    "date_local": local.date().isoformat(),
                    "minute_of_day": local.hour * 60 + local.minute,
                    "hex": sky["hex"],
                    "luminance": _round(_maybe_float(sky.get("luminance_mean")), 4),
                    "blueness": _round(_maybe_float(sky.get("blueness_mean")), 4),
                    "texture": _round(_maybe_float(sky.get("texture_mean")), 4),
                    "valid": passed,
                }
            )
    rows.sort(key=lambda r: r["t_local"])
    return rows


def coverage_by_date(sessions: Session | Iterable[Session]) -> list[dict[str, Any]]:
    """Minutos observados y válidos por fecha local."""
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"observed": 0, "valid": 0})
    for session in as_sessions(sessions):
        for minute in session.minutes:
            key = session.local_time(minute).date().isoformat()
            totals[key]["observed"] += 1
            if evaluate_minute(minute).passed:
                totals[key]["valid"] += 1
    return [
        {
            "date_local": date,
            "minutes_observed": counts["observed"],
            "minutes_valid": counts["valid"],
            "valid_fraction": round(counts["valid"] / counts["observed"], 4)
            if counts["observed"]
            else 0.0,
            "day_coverage_fraction": round(counts["valid"] / 1440, 4),
        }
        for date, counts in sorted(totals.items())
    ]


def build_exhibits(
    sessions: Session | Sequence[Session],
    *,
    seed: int = DEFAULT_SEED,
    iterations: int = DEFAULT_BOOTSTRAP,
) -> dict[str, Any]:
    """Construye el paquete completo de resultados para el tablero y el informe."""
    sessions = as_sessions(sessions)
    gate_reports = [evaluate_session(s).to_dict() for s in sessions]
    pairs = valid_pairs(sessions)
    profiles = {
        metric: diurnal_profile(sessions, metric, seed=seed, iterations=iterations)
        for metric in METRICS
    }
    return {
        "schema": "ventana.exhibits.v1",
        "seed": seed,
        "bootstrap_iterations": iterations,
        "sessions": [
            {
                "session_id": s.session_id,
                "site_label": s.site_label,
                "t_start": s.header["t_start"],
                "engine": s.header.get("engine"),
                "minutes": len(s.minutes),
            }
            for s in sessions
        ],
        "gates": gate_reports,
        "minutes_observed": sum(len(s.minutes) for s in sessions),
        "minutes_valid": len(pairs),
        "coverage_by_date": coverage_by_date(sessions),
        "diurnal_profiles": profiles,
        "weekday_contrast": weekday_contrast(sessions, seed=seed, iterations=iterations),
        "dispersion": dispersion_index(sessions),
        "sky_barcode": sky_barcode(sessions),
        "claim_ceiling": _claim_ceiling(sessions, len(pairs)),
    }


def _claim_ceiling(sessions: Sequence[Session], valid: int) -> str:
    """Techo de afirmación permitido por la cobertura disponible."""
    dates = {row["date_local"] for row in coverage_by_date(sessions)}
    if valid < 600:
        return "exploratorio: la muestra no sostiene ninguna afirmación sobre el ritmo del sitio"
    if len(dates) < 7:
        return "descriptivo de las fechas observadas; sin afirmación semanal"
    if len(dates) < 28:
        return "perfil diurno del sitio con contraste laborable/fin de semana declarado"
    return "perfil diurno y semanal estable del sitio, con estacionalidad aún no evaluable"
