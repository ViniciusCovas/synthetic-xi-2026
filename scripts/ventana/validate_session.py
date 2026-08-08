#!/usr/bin/env python3
"""Valida un export JSONL de Ventana y evalúa las compuertas de calidad.

Uso:
    python scripts/ventana/validate_session.py data/ventana/raw/ventana_*.jsonl

Devuelve código de salida 1 si alguna sesión no supera su compuerta, de modo
que pueda encadenarse en integración continua.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ventana.gates import evaluate_session  # noqa: E402
from ventana.records import SchemaError, load_jsonl, split_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="ficheros JSONL exportados")
    parser.add_argument("--json", action="store_true", help="imprime el informe como JSON")
    parser.add_argument(
        "--allow-failed-gate",
        action="store_true",
        help="informa las compuertas fallidas pero devuelve código 0",
    )
    args = parser.parse_args()

    records = []
    for path in args.paths:
        if not path.exists():
            print(f"no existe: {path}", file=sys.stderr)
            return 2
        records.extend(load_jsonl(path))

    try:
        sessions = split_records(records)
    except SchemaError as exc:
        print(f"esquema inválido: {exc}", file=sys.stderr)
        return 2

    reports = [evaluate_session(s).to_dict() for s in sessions]
    payload = {
        "status": "ventana_validation_complete",
        "files": [str(p) for p in args.paths],
        "sessions": len(sessions),
        "minutes_observed": sum(len(s.minutes) for s in sessions),
        "minutes_valid": sum(r["valid_minutes"] for r in reports),
        "reports": reports,
        "all_session_gates_passed": all(r["session_gate_passed"] for r in reports),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"sesiones: {payload['sessions']}")
        print(f"minutos observados: {payload['minutes_observed']}")
        print(f"minutos válidos: {payload['minutes_valid']}")
        for report in reports:
            mark = "PASS" if report["session_gate_passed"] else "FAIL"
            print(
                f"  [{mark}] {report['session_id']}  "
                f"{report['valid_minutes']}/{report['total_minutes']} "
                f"({report['valid_fraction']:.1%})"
            )
            for gate, count in report["failures_by_gate"].items():
                if count:
                    print(f"        {gate}: {count} minutos descartados")
            for blocker in report["blocking"]:
                print(f"        bloquea: {blocker}")

    if payload["all_session_gates_passed"] or args.allow_failed_gate:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
