"""Shared provenance contract for official_experiment_v1."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .official_profiles import CONFIG_PATH, ROSTER_PATH


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def critical_source_paths(config: dict[str, Any]) -> dict[str, Path]:
    return {
        "experiment_config": CONFIG_PATH,
        "protocol_amendment": Path(config["protocol_amendment"]),
        "protocol_addendum_emergency_substitution": Path(
            "PROTOCOL_AMENDMENT_OFFICIAL_V1_ADDENDUM_01.md"
        ),
        "canonical_rosters": ROSTER_PATH,
        "rankings_authorization": Path(
            config["canonical_inputs"]["rankings_authorization"]
        ),
        "requirements": Path("requirements.txt"),
        "simulator_package_policy": Path("simulator/__init__.py"),
        "official_features_source": Path("simulator/official_features.py"),
        "official_profiles_source": Path("simulator/official_profiles.py"),
        "official_profile_sensitivity_source": Path(
            "simulator/official_profile_sensitivity.py"
        ),
        "official_frozen_runtime_source": Path(
            "simulator/official_frozen_runtime.py"
        ),
        "official_engine_source": Path("simulator/official_complete_final.py"),
        "official_monte_carlo_source": Path("simulator/official_monte_carlo.py"),
        "official_orientation_source": Path("simulator/official_orientation.py"),
        "official_provenance_source": Path("simulator/official_provenance.py"),
        "official_runner_source": Path("scripts/run_official_experiment.py"),
        "official_statistical_launcher_source": Path(
            "scripts/run_official_experiment_v1_1.py"
        ),
        "hypothesis_source": Path(
            "scripts/scientific/analyze_official_hypotheses.py"
        ),
        "robustness_source": Path(
            "scripts/scientific/run_official_robustness.py"
        ),
        "release_validator_source": Path(
            "scripts/scientific/validate_official_release.py"
        ),
        "official_test_source": Path("tests/test_official_experiment.py"),
        "official_orientation_test_source": Path(
            "tests/test_official_orientation.py"
        ),
    }


def critical_source_hashes(config: dict[str, Any]) -> dict[str, str | None]:
    return {
        name: sha256_file(path)
        for name, path in critical_source_paths(config).items()
    }


def missing_critical_sources(config: dict[str, Any]) -> list[str]:
    return [
        name
        for name, digest in critical_source_hashes(config).items()
        if digest is None
    ]
