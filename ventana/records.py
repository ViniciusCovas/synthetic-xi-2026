"""Lectura y validación estructural de los registros de Ventana.

El fichero exportado por el teléfono es JSONL: una cabecera de sesión por cada
sesión y una fila por cada minuto observado. Aquí se comprueba únicamente la
forma; los juicios de calidad viven en :mod:`ventana.gates`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

MINUTE_SCHEMA = "ventana.minute.v1"
SESSION_SCHEMA = "ventana.session.v1"

SIZE_CLASSES = ("small", "medium", "large")


class SchemaError(ValueError):
    """Un registro no cumple el esquema declarado."""


def _require(record: dict[str, Any], path: str) -> Any:
    node: Any = record
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"falta el campo obligatorio {path!r}")
        node = node[part]
    return node


def _require_number(record: dict[str, Any], path: str) -> float:
    value = _require(record, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"el campo {path!r} debe ser numérico, no {type(value).__name__}")
    return float(value)


def parse_timestamp(value: str) -> datetime:
    """Convierte una marca ISO 8601 en un ``datetime`` con zona horaria."""
    if not isinstance(value, str):
        raise SchemaError(f"marca temporal no textual: {value!r}")
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchemaError(f"marca temporal ilegible: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_session_header(record: dict[str, Any]) -> dict[str, Any]:
    """Valida una cabecera de sesión y la devuelve intacta."""
    if record.get("schema") != SESSION_SCHEMA:
        raise SchemaError(f"esquema de sesión inesperado: {record.get('schema')!r}")
    for path in ("session_id", "t_start", "engine", "calibration", "config"):
        _require(record, path)
    parse_timestamp(record["t_start"])
    calibration = record["calibration"]
    for region in ("sky", "street", "line"):
        if not calibration.get(region):
            raise SchemaError(f"la calibración no define la región {region!r}")
    if len(calibration["street"]) < 3:
        raise SchemaError("el polígono de calle necesita al menos tres vértices")
    return record


def validate_minute(record: dict[str, Any]) -> dict[str, Any]:
    """Valida un registro de minuto y lo devuelve intacto."""
    if record.get("schema") != MINUTE_SCHEMA:
        raise SchemaError(f"esquema de minuto inesperado: {record.get('schema')!r}")
    for path in ("t_start", "t_end", "frames", "street.crossings_total", "quality.night"):
        _require(record, path)

    start = parse_timestamp(record["t_start"])
    end = parse_timestamp(record["t_end"])
    if end <= start:
        raise SchemaError("t_end no es posterior a t_start")

    _require_number(record, "frames")
    street = record["street"]
    for key in ("crossings_a", "crossings_b", "crossings_total"):
        value = _require_number(record, f"street.{key}")
        if value < 0:
            raise SchemaError(f"street.{key} no puede ser negativo")
    if street["crossings_a"] + street["crossings_b"] != street["crossings_total"]:
        raise SchemaError("crossings_total no coincide con la suma por sentido")

    by_size = _require(record, "street.by_size")
    missing = [c for c in SIZE_CLASSES if c not in by_size]
    if missing:
        raise SchemaError(f"faltan clases de porte: {missing}")
    if sum(by_size[c] for c in SIZE_CLASSES) != street["crossings_total"]:
        raise SchemaError("el desglose por porte no suma el total de cruces")

    sky = record.get("sky")
    if sky is not None:
        for key in ("luminance_mean", "blueness_mean", "saturation_mean"):
            _require_number(record, f"sky.{key}")
        if not 0.0 <= sky["luminance_mean"] <= 1.0:
            raise SchemaError("sky.luminance_mean fuera de [0, 1]")
    return record


@dataclass(frozen=True)
class Session:
    """Una sesión de observación con sus minutos asociados."""

    header: dict[str, Any]
    minutes: tuple[dict[str, Any], ...]

    @property
    def session_id(self) -> str:
        return str(self.header["session_id"])

    @property
    def site_label(self) -> str | None:
        label = self.header.get("site_label")
        return str(label) if label else None

    @property
    def utc_offset(self) -> timedelta:
        """Desfase horario declarado por el teléfono al abrir la sesión."""
        minutes = self.header.get("utc_offset_minutes")
        if minutes is None:
            return timedelta(0)
        return timedelta(minutes=float(minutes))

    def local_time(self, record: dict[str, Any]) -> datetime:
        """Hora local del sitio observado para un registro de minuto.

        Se usa el desfase declarado en la cabecera en lugar de la zona por
        nombre: una sesión que cruza un cambio de horario de verano queda
        marcada con el desfase vigente al iniciarla, y ese hecho se documenta
        en el protocolo en vez de corregirse en silencio.
        """
        return parse_timestamp(record["t_start"]).astimezone(timezone(self.utc_offset))


@dataclass
class _SessionBuilder:
    header: dict[str, Any]
    minutes: list[dict[str, Any]] = field(default_factory=list)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Lee un fichero JSONL y devuelve la lista de registros."""
    import json

    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SchemaError(f"línea {lineno} ilegible: {exc}") from exc
    return records


def split_records(records: Iterable[dict[str, Any]]) -> list[Session]:
    """Agrupa registros sueltos en sesiones, validando cada uno.

    Los minutos se adjuntan a la sesión cuyo ``session_id`` declaran. Un minuto
    huérfano —exportado sin su cabecera— es un error explícito: sin la
    calibración no se puede interpretar ninguna de sus magnitudes.
    """
    builders: dict[str, _SessionBuilder] = {}
    order: list[str] = []
    orphans: list[str] = []

    for record in records:
        schema = record.get("schema")
        if schema == SESSION_SCHEMA:
            header = validate_session_header(record)
            sid = str(header["session_id"])
            if sid not in builders:
                builders[sid] = _SessionBuilder(header=header)
                order.append(sid)
        elif schema == MINUTE_SCHEMA:
            minute = validate_minute(record)
            sid = str(minute.get("session_id", ""))
            if sid not in builders:
                orphans.append(sid or "<sin session_id>")
                continue
            builders[sid].minutes.append(minute)
        else:
            raise SchemaError(f"esquema desconocido: {schema!r}")

    if orphans:
        unique = sorted(set(orphans))
        raise SchemaError(f"minutos sin cabecera de sesión: {unique}")

    sessions: list[Session] = []
    for sid in order:
        builder = builders[sid]
        ordered = tuple(sorted(builder.minutes, key=lambda r: parse_timestamp(r["t_start"])))
        sessions.append(Session(header=builder.header, minutes=ordered))
    return sessions


def iter_minutes(sessions: Iterable[Session]) -> Iterator[tuple[Session, dict[str, Any]]]:
    """Recorre todos los minutos de varias sesiones conservando su origen."""
    for session in sessions:
        for minute in session.minutes:
            yield session, minute
