#!/usr/bin/env python3
"""Audit all cached project data for final-match event capabilities.

The audit is descriptive only. It scans CSV/CSV.GZ/JSON assets already present in the
repository and reports whether the project currently has usable evidence for:
extra time, penalty shootouts, in-match penalties, cards, dismissals, fouls,
substitutions, benches, injuries, referees, VAR, stoppage time, corners, offsides,
and event coordinates.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path("data")
OUT = Path("data/audits/match_event_capability_v1")
MAX_SAMPLE_ROWS = 200_000

CAPABILITIES: dict[str, list[str]] = {
    "extra_time": ["extra_time", "extratime", "extra time", "after_extra_time", "elapsed_extra"],
    "penalty_shootout": ["shootout", "penalty_shootout", "penalties_score", "penalty_winner", "after_penalties"],
    "in_match_penalties": ["penalty", "penalty_scored", "penalty_missed", "penalty_saved", "penalty_committed", "penalty_won"],
    "yellow_cards": ["yellow", "yellow_card", "cards_yellow", "card_yellow"],
    "red_cards": ["red", "red_card", "cards_red", "card_red", "second_yellow"],
    "fouls": ["foul", "fouls", "fouls_committed", "fouls_drawn"],
    "substitutions": ["substitution", "substitute", "sub_in", "sub_out", "player_in", "player_out"],
    "bench_lineups": ["bench", "substitutes", "lineup", "formation", "starting_xi", "startxi"],
    "injuries": ["injury", "injured", "medical", "treatment"],
    "referees": ["referee", "official", "fourth_official", "var_referee"],
    "var": ["var", "video_assistant", "goal_cancelled", "goal_disallowed"],
    "stoppage_time": ["stoppage", "added_time", "injury_time", "elapsed_extra"],
    "corners": ["corner", "corners"],
    "offsides": ["offside", "offsides"],
    "event_timeline": ["event", "events", "timeline", "elapsed", "minute", "time"],
    "event_coordinates": ["coordinate", "location", "start_x", "start_y", "end_x", "end_y", "x_coordinate", "y_coordinate"],
    "player_fatigue_load": ["fatigue", "load", "distance", "sprint", "recovery", "rest_days"],
}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def read_header(path: Path) -> list[str]:
    if path.name.endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace") as handle:
            return next(csv.reader(handle), [])
    if path.suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            return next(csv.reader(handle), [])
    return []


def json_keys(obj: Any, prefix: str = "", depth: int = 0) -> set[str]:
    if depth > 4:
        return set()
    keys: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            keys.add(full)
            keys.update(json_keys(value, full, depth + 1))
    elif isinstance(obj, list) and obj:
        for value in obj[:5]:
            keys.update(json_keys(value, prefix, depth + 1))
    return keys


def column_matches(columns: list[str], terms: list[str]) -> list[str]:
    normalized = {column: normalize(column) for column in columns}
    hits = []
    for original, current in normalized.items():
        for term in terms:
            target = normalize(term)
            if target == current or target in current or current in target:
                hits.append(original)
                break
    return sorted(set(hits))


def sample_csv(path: Path, columns: list[str]) -> tuple[int, dict[str, int], dict[str, list[str]]]:
    if not columns:
        return 0, {}, {}
    try:
        frame = pd.read_csv(path, usecols=columns, nrows=MAX_SAMPLE_ROWS, low_memory=False)
    except Exception:
        return 0, {}, {}
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for column in columns:
        series = frame[column]
        present = series.notna() & series.astype(str).str.strip().ne("")
        counts[column] = int(present.sum())
        values = series.loc[present].astype(str).drop_duplicates().head(8).tolist()
        examples[column] = values
    return len(frame), counts, examples


def classify(capability: str, evidence: list[dict[str, Any]]) -> tuple[str, str]:
    if not evidence:
        return "not_found", "Nenhum campo correspondente encontrado nos arquivos cacheados."
    non_null = sum(sum(item.get("non_null_counts", {}).values()) for item in evidence)
    paths = {item["path"] for item in evidence}
    if non_null >= 1000 and len(paths) >= 1:
        return "available_substantial", f"Campos encontrados com pelo menos {non_null} valores não vazios amostrados."
    if non_null > 0:
        return "available_limited", f"Campos encontrados, mas apenas {non_null} valores não vazios foram confirmados na amostra."
    return "schema_only", "Nomes de campos encontrados, porém sem valores não vazios confirmados na amostra."


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = [path for path in ROOT.rglob("*") if path.is_file() and (path.suffix in {".csv", ".json"} or path.name.endswith(".csv.gz"))]
    schema_rows: list[dict[str, Any]] = []
    evidence_by_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_bytes = 0

    for path in sorted(files):
        if OUT in path.parents:
            continue
        total_bytes += path.stat().st_size
        columns: list[str] = []
        kind = ""
        error = ""
        try:
            if path.suffix == ".json":
                kind = "json"
                obj = json.loads(path.read_text(encoding="utf-8"))
                columns = sorted(json_keys(obj))
            else:
                kind = "csv.gz" if path.name.endswith(".csv.gz") else "csv"
                columns = read_header(path)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        all_hits: dict[str, list[str]] = {}
        union_columns: set[str] = set()
        for capability, terms in CAPABILITIES.items():
            hits = column_matches(columns, terms)
            if hits:
                all_hits[capability] = hits
                union_columns.update(hits)

        sampled_rows = 0
        non_null: dict[str, int] = {}
        examples: dict[str, list[str]] = {}
        if kind.startswith("csv") and union_columns:
            sampled_rows, non_null, examples = sample_csv(path, sorted(union_columns))

        for capability, hits in all_hits.items():
            item = {
                "path": str(path),
                "kind": kind,
                "matched_columns": hits,
                "sampled_rows": sampled_rows,
                "non_null_counts": {column: non_null.get(column, 0) for column in hits},
                "examples": {column: examples.get(column, []) for column in hits},
            }
            evidence_by_capability[capability].append(item)

        schema_rows.append({
            "path": str(path),
            "kind": kind,
            "bytes": path.stat().st_size,
            "column_count": len(columns),
            "columns": "|".join(columns),
            "matched_capabilities": "|".join(sorted(all_hits)),
            "sampled_rows": sampled_rows,
            "error": error,
        })

    capability_rows = []
    status_map = {}
    for capability in CAPABILITIES:
        evidence = evidence_by_capability.get(capability, [])
        status, note = classify(capability, evidence)
        files_with_evidence = sorted({item["path"] for item in evidence})
        columns = sorted({col for item in evidence for col in item["matched_columns"]})
        non_null = sum(sum(item["non_null_counts"].values()) for item in evidence)
        capability_rows.append({
            "capability": capability,
            "status": status,
            "files_with_evidence": len(files_with_evidence),
            "matched_columns": "|".join(columns),
            "sample_non_null_values": non_null,
            "note": note,
        })
        status_map[capability] = {
            "status": status,
            "files": files_with_evidence,
            "matched_columns": columns,
            "sample_non_null_values": non_null,
            "evidence": evidence,
        }

    pd.DataFrame(schema_rows).to_csv(OUT / "schema_inventory.csv", index=False)
    pd.DataFrame(capability_rows).to_csv(OUT / "capability_matrix.csv", index=False)
    (OUT / "evidence_details.json").write_text(json.dumps(status_map, ensure_ascii=False, indent=2), encoding="utf-8")

    ready_90 = all(status_map[key]["status"] in {"available_substantial", "available_limited"} for key in ["event_timeline"])
    ready_final = all(status_map[key]["status"] == "available_substantial" for key in [
        "extra_time", "penalty_shootout", "yellow_cards", "red_cards", "substitutions", "bench_lineups"
    ])
    status = {
        "status": "match_event_capability_audit_completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files_scanned": len(schema_rows),
        "bytes_scanned": total_bytes,
        "maximum_rows_sampled_per_file": MAX_SAMPLE_ROWS,
        "capabilities": {key: {k: v for k, v in value.items() if k != "evidence"} for key, value in status_map.items()},
        "current_90_minute_engine_data_ready": ready_90,
        "full_knockout_final_data_ready": ready_final,
        "final_with_cards_subs_extra_time_penalties_authorized": ready_final,
        "interpretation_rule": "schema_only is not treated as usable data; substantial status requires confirmed non-null values.",
        "next_action": "extract missing event endpoints and build player/team calibration tables" if not ready_final else "calibrate and validate knockout-final event engine",
    }
    (OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Auditoria de dados para uma final completa", "",
        f"Arquivos examinados: **{len(schema_rows)}**", "",
        "| Capacidade | Situação | Arquivos | Valores não vazios na amostra |",
        "|---|---|---:|---:|",
    ]
    for row in capability_rows:
        lines.append(f"| {row['capability']} | {row['status']} | {row['files_with_evidence']} | {row['sample_non_null_values']} |")
    lines += [
        "", f"Final completa autorizada com os dados cacheados: **{ready_final}**", "",
        "`schema_only` significa que o nome de um campo apareceu, mas valores utilizáveis não foram confirmados.",
        "A auditoria não inventa eventos e não transforma agregados em dados evento a evento.",
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
