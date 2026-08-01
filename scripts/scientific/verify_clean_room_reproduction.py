#!/usr/bin/env python3
"""Verify an independently regenerated official_v1 run against frozen evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import shutil
import sys
from typing import Any

import pandas as pd

CORE_JSON_FILES = (
    "simulation_summary.json",
    "official_hypotheses_summary.json",
)
VERSIONED_TABLE_FILES = (
    "official_h7_state_rates.csv",
    "official_h7_interactions.csv",
    "representative_final_timeline.csv",
    "synthetic_starting_xi.csv",
    "real_starting_xi.csv",
)
SUMMARY_PATHS = (
    "status",
    "version",
    "simulations",
    "master_seed",
    "match_seed_ledger_sha256",
    "home",
    "away",
    "home_champion_probability.estimate",
    "home_champion_probability.low",
    "home_champion_probability.high",
    "away_champion_probability.estimate",
    "away_champion_probability.low",
    "away_champion_probability.high",
    "regulation_home_win_probability.estimate",
    "regulation_draw_probability.estimate",
    "regulation_away_win_probability.estimate",
    "extra_time_probability.estimate",
    "penalty_shootout_probability.estimate",
    "mean_regulation_goals",
    "mean_total_goals",
    "mean_total_shots",
    "mean_total_shots_on_target",
    "mean_total_fouls",
    "mean_total_yellows",
    "mean_total_reds",
    "source_hashes",
    "canonical_runtime",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--environment-copy", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dotted_get(value: Any, path: str) -> Any:
    current = value
    for key in path.split("."):
        current = current[key]
    return current


def normalized_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_summary(reference: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for path in SUMMARY_PATHS:
        left = dotted_get(reference, path)
        right = dotted_get(candidate, path)
        passed = normalized_json(left) == normalized_json(right)
        checks.append({"path": path, "passed": passed, "reference": left, "candidate": right})
    return checks


def compare_json_file(reference: Path, candidate: Path) -> dict[str, Any]:
    left = load_json(reference)
    right = load_json(candidate)
    exact = normalized_json(left) == normalized_json(right)
    return {
        "file": reference.name,
        "passed": exact,
        "reference_sha256": sha256(reference),
        "candidate_sha256": sha256(candidate),
        "byte_identical": sha256(reference) == sha256(candidate),
    }


def compare_table(reference: Path, candidate: Path) -> dict[str, Any]:
    left = pd.read_csv(reference)
    right = pd.read_csv(candidate)
    error: str | None = None
    try:
        pd.testing.assert_frame_equal(
            left,
            right,
            check_dtype=False,
            check_exact=True,
            check_names=True,
            check_like=False,
        )
        passed = True
    except AssertionError as exc:
        passed = False
        error = str(exc)[:2000]
    return {
        "file": reference.name,
        "passed": passed,
        "rows": int(len(left)),
        "columns": list(left.columns),
        "reference_sha256": sha256(reference),
        "candidate_sha256": sha256(candidate),
        "byte_identical": sha256(reference) == sha256(candidate),
        "error": error,
    }


def compare_manifest(reference_dir: Path, candidate_dir: Path) -> list[dict[str, Any]]:
    reference_manifest = load_json(reference_dir / "manifest.json")
    expected_files = reference_manifest.get("files", {})
    checks: list[dict[str, Any]] = []
    for relative_path, metadata in sorted(expected_files.items()):
        candidate = candidate_dir / relative_path
        expected_sha = metadata.get("sha256")
        actual_sha = sha256(candidate) if candidate.is_file() else None
        checks.append({
            "file": relative_path,
            "passed": actual_sha == expected_sha,
            "expected_sha256": expected_sha,
            "candidate_sha256": actual_sha,
            "expected_bytes": metadata.get("bytes"),
            "candidate_bytes": candidate.stat().st_size if candidate.is_file() else None,
        })
    return checks


def main() -> None:
    args = parse_args()
    for directory in (args.reference, args.candidate):
        if not directory.is_dir():
            raise FileNotFoundError(directory)
    if not args.environment.is_file():
        raise FileNotFoundError(args.environment)

    reference_summary = load_json(args.reference / "simulation_summary.json")
    candidate_summary = load_json(args.candidate / "simulation_summary.json")
    summary_checks = compare_summary(reference_summary, candidate_summary)

    json_checks = []
    for filename in CORE_JSON_FILES:
        ref = args.reference / filename
        cand = args.candidate / filename
        if not ref.is_file() or not cand.is_file():
            json_checks.append({"file": filename, "passed": False, "error": "missing file"})
        else:
            json_checks.append(compare_json_file(ref, cand))

    table_checks = []
    for filename in VERSIONED_TABLE_FILES:
        ref = args.reference / filename
        cand = args.candidate / filename
        if not ref.is_file() or not cand.is_file():
            table_checks.append({"file": filename, "passed": False, "error": "missing file"})
        else:
            table_checks.append(compare_table(ref, cand))

    manifest_checks = compare_manifest(args.reference, args.candidate)
    passed = (
        all(item["passed"] for item in summary_checks)
        and all(item["passed"] for item in json_checks)
        and all(item["passed"] for item in table_checks)
        and bool(manifest_checks)
        and all(item["passed"] for item in manifest_checks)
    )
    byte_identity = bool(manifest_checks) and all(item["passed"] for item in manifest_checks)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.environment_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.environment, args.environment_copy)
    report = {
        "status": "clean_room_reproduction_passed" if passed else "clean_room_reproduction_failed",
        "passed": passed,
        "all_manifest_artifacts_byte_identical": byte_identity,
        "manifest_artifact_count": len(manifest_checks),
        "reference_directory": str(args.reference),
        "candidate_directory": str(args.candidate),
        "python": sys.version,
        "platform": platform.platform(),
        "environment_sha256": sha256(args.environment_copy),
        "summary_checks": summary_checks,
        "json_checks": json_checks,
        "versioned_table_checks": table_checks,
        "manifest_checks": manifest_checks,
        "interpretation": (
            "The independently regenerated 10,000-run official experiment reproduced every artifact "
            "hash recorded in the frozen manifest, together with the primary estimands and H5-H7 outputs."
            if passed
            else "At least one frozen identifier, estimand, H5-H7 output, versioned table, or manifest artifact did not reproduce."
        ),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failed_summary = [item["path"] for item in summary_checks if not item["passed"]]
    failed_files = [
        item["file"]
        for item in [*json_checks, *table_checks, *manifest_checks]
        if not item["passed"]
    ]
    markdown = f"""# Clean-room reproduction — Official Experiment v1

- Status: **{'PASS' if passed else 'FAIL'}**
- All frozen manifest artifacts byte-identical: **{'yes' if byte_identity else 'no'}**
- Manifest artifacts checked: **{len(manifest_checks)}**
- Candidate simulations: **{candidate_summary.get('simulations')}**
- Candidate master seed: **`{candidate_summary.get('master_seed')}`**
- Synthetic XI champion probability: **{candidate_summary['home_champion_probability']['estimate']:.4%}**
- Real Best XI champion probability: **{candidate_summary['away_champion_probability']['estimate']:.4%}**
- Environment lock SHA-256: `{sha256(args.environment_copy)}`

## Audit scope

The audit was executed in a fresh GitHub-hosted Ubuntu environment with a new Python 3.12 installation and dependencies installed without a pip cache. It regenerated the preregistered 10,000-run official experiment from the frozen code and seed. Every candidate artifact was checked against the SHA-256 recorded in the frozen manifest, including full match and state tables that are retained in the immutable experiment package rather than versioned individually in Git.

## Failed summary checks

{chr(10).join(f'- `{name}`' for name in failed_summary) if failed_summary else '- None'}

## Failed files

{chr(10).join(f'- `{name}`' for name in failed_files) if failed_files else '- None'}

## Interpretation

{report['interpretation']}
"""
    args.markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps({"passed": passed, "byte_identity": byte_identity, "output": str(args.output)}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
