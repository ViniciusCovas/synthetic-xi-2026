"""Valida o pacote EMBARCADO do app (web/public/lab/py) em CPython.

O mesmo código que roda no navegador via Pyodide é importado daqui e
executado de verdade: carregar dados exportados, montar bundles, simular
finais com condições e devolver um sumário coerente.
"""

from pathlib import Path
import importlib
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "web" / "public" / "lab" / "py"
DATA_DIR = ROOT / "web" / "public" / "lab" / "data"

pytestmark = pytest.mark.skipif(
    not (PACKAGE_ROOT / "labsim" / "lab_runtime.py").exists(),
    reason="pacote do app não exportado (rode scripts/export_lab_app_data.py)",
)


@pytest.fixture(scope="module")
def runtime():
    sys.path.insert(0, str(PACKAGE_ROOT))
    module = importlib.import_module("labsim.lab_runtime")
    module.load_data(
        (DATA_DIR / "teams.json").read_text(encoding="utf-8"),
        (DATA_DIR / "calibration.json").read_text(encoding="utf-8"),
    )
    return module


def test_shipped_package_runs_a_conditioned_match(runtime):
    started = json.loads(
        runtime.start_session(
            "Spain",
            "Argentina",
            simulations=6,
            seed=99,
            conditions_json=json.dumps(
                {
                    "label": "Mexico City (teste)",
                    "apparent_temperature_c": 30.0,
                    "altitude_m": 2240,
                    "scheme": "primary",
                }
            ),
        )
    )
    assert started["ready"] is True
    assert len(started["rosters"]["home"]) == 26 or started["rosters"]["home"]

    progress = json.loads(runtime.run_chunk(4))
    assert progress["completed"] == 4
    progress = json.loads(runtime.run_chunk(10))
    assert progress["completed"] == 6

    result = json.loads(runtime.summary())
    probabilities = result["win_probability"]
    assert set(probabilities) == {"Spain", "Argentina"}
    assert abs(sum(probabilities.values()) - 1.0) < 1e-9
    assert result["conditions"]["config_overrides"]["fatigue_per_90"] > 0.19


def test_shipped_package_neutral_conditions(runtime):
    runtime.start_session("France", "Brazil", simulations=3, seed=5)
    runtime.run_chunk(3)
    result = json.loads(runtime.summary())
    assert result["simulations"] == 3
    assert result["conditions"] is None


def test_shipped_package_representative_final(runtime):
    runtime.start_session("Spain", "Argentina", simulations=8, seed=77)
    runtime.run_chunk(8)
    final = json.loads(runtime.representative_final())
    assert final["winner"] in {"Spain", "Argentina"}
    assert final["decided_by"] in {"regulation", "extra_time", "penalties"}
    assert len(final["events"]) > 10
    # narrativa em português com placar coerente no último evento com placar
    scored = [e for e in final["events"] if e["score"]]
    assert scored and scored[-1]["score"] == final["final_score"]
    kickoff_headlines = " ".join(e["headline"] for e in final["events"][:6])
    assert kickoff_headlines  # narrado
    if final["decided_by"] == "penalties":
        assert final["penalties"] is not None
