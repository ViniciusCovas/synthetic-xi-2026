"""Compuertas de calidad de Ventana.

Los umbrales están congelados en ``PROTOCOLO_VENTANA_V1.md`` y se declaran
antes de mirar los datos. Un minuto que falla cualquiera de ellas queda fuera
del análisis principal, pero nunca se borra: se cuenta y se informa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ventana.records import Session

#: Umbrales del protocolo v1. Cambiarlos exige una enmienda documentada.
GATE_THRESHOLDS: Mapping[str, float] = {
    "duration_min_s": 55.0,
    "duration_max_s": 65.0,
    "fps_min": 4.0,
    "measurable_frame_fraction_min": 0.50,
    "clipped_high_frac_max": 0.25,
    "session_valid_fraction_min": 0.80,
    "session_valid_minutes_min": 60.0,
}

GATE_NAMES = (
    "complete_minute",
    "frame_rate",
    "measurable_coverage",
    "camera_stable",
    "exposure",
)


@dataclass(frozen=True)
class MinuteVerdict:
    """Resultado de aplicar las compuertas a un minuto."""

    passed: bool
    gates: Mapping[str, bool]
    failed: tuple[str, ...]

    @property
    def first_failure(self) -> str | None:
        return self.failed[0] if self.failed else None


def evaluate_minute(minute: dict[str, Any]) -> MinuteVerdict:
    """Aplica las cinco compuertas de minuto y devuelve el veredicto."""
    thresholds = GATE_THRESHOLDS
    quality = minute.get("quality") or {}
    exposure = minute.get("exposure") or {}

    duration = float(minute.get("duration_s") or 0.0)
    frames = float(minute.get("frames") or 0.0)
    measurable = float(quality.get("measurable_frames") or 0.0)
    fps = minute.get("fps_mean")
    clipped_high = exposure.get("clipped_high_frac")

    gates = {
        "complete_minute": (
            not bool(minute.get("partial"))
            and thresholds["duration_min_s"] <= duration <= thresholds["duration_max_s"]
        ),
        "frame_rate": fps is not None and float(fps) >= thresholds["fps_min"],
        "measurable_coverage": (
            frames > 0 and measurable / frames >= thresholds["measurable_frame_fraction_min"]
        ),
        "camera_stable": not bool(quality.get("camera_shift")),
        # Un cielo quemado invalida la fotometría, no el conteo de la calle;
        # aun así se descarta el minuto entero para no mezclar poblaciones.
        "exposure": (
            clipped_high is None or float(clipped_high) <= thresholds["clipped_high_frac_max"]
        ),
    }
    failed = tuple(name for name in GATE_NAMES if not gates[name])
    return MinuteVerdict(passed=not failed, gates=gates, failed=failed)


@dataclass(frozen=True)
class SessionGateReport:
    """Resumen de compuertas de una sesión completa."""

    session_id: str
    total_minutes: int
    valid_minutes: int
    valid_fraction: float
    failures_by_gate: Mapping[str, int]
    passed: bool
    blocking: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_minutes": self.total_minutes,
            "valid_minutes": self.valid_minutes,
            "valid_fraction": round(self.valid_fraction, 4),
            "failures_by_gate": dict(self.failures_by_gate),
            "session_gate_passed": self.passed,
            "blocking": list(self.blocking),
        }


def evaluate_session(session: Session) -> SessionGateReport:
    """Evalúa una sesión: cuántos minutos sobreviven y qué la bloquea."""
    total = len(session.minutes)
    failures = {name: 0 for name in GATE_NAMES}
    valid = 0
    for minute in session.minutes:
        verdict = evaluate_minute(minute)
        if verdict.passed:
            valid += 1
        for name in verdict.failed:
            failures[name] += 1

    fraction = valid / total if total else 0.0
    blocking: list[str] = []
    if valid < GATE_THRESHOLDS["session_valid_minutes_min"]:
        blocking.append("session_valid_minutes_min")
    if fraction < GATE_THRESHOLDS["session_valid_fraction_min"]:
        blocking.append("session_valid_fraction_min")

    return SessionGateReport(
        session_id=session.session_id,
        total_minutes=total,
        valid_minutes=valid,
        valid_fraction=fraction,
        failures_by_gate=failures,
        passed=not blocking,
        blocking=tuple(blocking),
    )


def valid_minutes(session: Session) -> list[dict[str, Any]]:
    """Devuelve sólo los minutos que superan todas las compuertas."""
    return [m for m in session.minutes if evaluate_minute(m).passed]
