#!/usr/bin/env python3
"""Construye el paquete de resultados de Ventana a partir de los JSONL crudos.

Uso:
    python scripts/ventana/build_ventana_exhibits.py \
        --input data/ventana/raw \
        --output data/ventana/exhibits/ventana_exhibits.json

La salida alimenta el tablero de `projects/ventana_observatory/dashboard` y es
el único artefacto que las figuras y el informe pueden citar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ventana.aggregate import DEFAULT_BOOTSTRAP, DEFAULT_SEED, build_exhibits  # noqa: E402
from ventana.records import SchemaError, load_jsonl, split_records  # noqa: E402


def collect(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        if path.is_dir():
            files = sorted(path.glob("*.jsonl"))
            if not files:
                raise SystemExit(f"sin ficheros .jsonl en {path}")
            for file in files:
                records.extend(load_jsonl(file))
        else:
            records.extend(load_jsonl(path))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        nargs="+",
        type=Path,
        default=[Path("data/ventana/raw")],
        help="ficheros o directorios JSONL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/ventana/exhibits/ventana_exhibits.json"),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    args = parser.parse_args()

    try:
        sessions = split_records(collect(args.input))
    except SchemaError as exc:
        print(f"esquema inválido: {exc}", file=sys.stderr)
        return 2

    exhibits = build_exhibits(sessions, seed=args.seed, iterations=args.bootstrap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(exhibits, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"sesiones: {len(sessions)}")
    print(f"minutos válidos: {exhibits['minutes_valid']} / {exhibits['minutes_observed']}")
    print(f"techo de afirmación: {exhibits['claim_ceiling']}")
    print(f"escrito: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
