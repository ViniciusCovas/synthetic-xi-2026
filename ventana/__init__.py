"""Ventana — observatorio de ventana.

Capa de análisis para los registros producidos por la aplicación de captura
que corre en el teléfono. El motor de visión vive en
``projects/ventana_observatory/capture``; aquí sólo entran filas numéricas.
"""

from __future__ import annotations

from ventana.gates import (
    MinuteVerdict,
    SessionGateReport,
    evaluate_minute,
    evaluate_session,
)
from ventana.records import (
    MINUTE_SCHEMA,
    SESSION_SCHEMA,
    SchemaError,
    Session,
    load_jsonl,
    split_records,
    validate_minute,
    validate_session_header,
)

__all__ = [
    "MINUTE_SCHEMA",
    "SESSION_SCHEMA",
    "MinuteVerdict",
    "SchemaError",
    "Session",
    "SessionGateReport",
    "evaluate_minute",
    "evaluate_session",
    "load_jsonl",
    "split_records",
    "validate_minute",
    "validate_session_header",
]
