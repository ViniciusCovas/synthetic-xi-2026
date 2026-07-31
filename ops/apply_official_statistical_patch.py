#!/usr/bin/env python3
"""One-shot deterministic patch for official_v1 statistical validation."""
from __future__ import annotations

import json
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Runner: use the paired confidence-interval equivalence implementation.
replace_once(
    "scripts/run_official_experiment.py",
    "from simulator.official_monte_carlo import (\n    paired_orientation_diagnostic,\n    seed_stability_diagnostic,\n    simulate_official_finals,\n)\n",
    "from simulator.official_monte_carlo import (\n    seed_stability_diagnostic,\n    simulate_official_finals,\n)\nfrom simulator.official_orientation import paired_orientation_diagnostic\n",
)
replace_once(
    "scripts/run_official_experiment.py",
    "        maximum_difference=float(orientation_cfg[\"maximum_absolute_difference\"]),\n        config=final_config,\n    )\n",
    "        maximum_difference=float(orientation_cfg[\"maximum_absolute_difference\"]),\n        config=final_config,\n        minimum_simulations=int(orientation_cfg[\"minimum_simulations_per_orientation\"]),\n        confidence_level=float(orientation_cfg.get(\"confidence_level\", 0.95)),\n    )\n",
)
replace_once(
    "scripts/run_official_experiment.py",
    "                \"orientation_gate\": orientation[\"passed\"],\n",
    "                \"orientation_status\": orientation[\"status\"],\n                \"orientation_release_gate\": orientation[\"passed\"],\n                \"orientation_point_estimate_within_margin\": orientation[\"point_estimate_within_margin\"],\n",
)

# Configuration: freeze the confidence level and the diagnostic smoke sample.
config_path = Path("config/official_experiment_v1.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
config["analysis"]["smoke_simulations"] = 200
config["orientation_equivalence"]["confidence_level"] = 0.95
config["orientation_equivalence"]["smoke_diagnostic_simulations"] = 200
config["orientation_equivalence"]["decision_rule"] = (
    "Release passes only when the paired 95% confidence interval for the signed "
    "home/away probability difference is fully contained in [-0.04, +0.04] and "
    "at least 2000 paired observations are available."
)
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Provenance: hash the new statistical implementation and its contract tests.
replace_once(
    "simulator/official_provenance.py",
    "        \"official_monte_carlo_source\": Path(\"simulator/official_monte_carlo.py\"),\n",
    "        \"official_monte_carlo_source\": Path(\"simulator/official_monte_carlo.py\"),\n        \"official_orientation_source\": Path(\"simulator/official_orientation.py\"),\n",
)
replace_once(
    "simulator/official_provenance.py",
    "        \"official_test_source\": Path(\"tests/test_official_experiment.py\"),\n",
    "        \"official_test_source\": Path(\"tests/test_official_experiment.py\"),\n        \"official_orientation_test_source\": Path(\"tests/test_official_orientation.py\"),\n",
)

# PR smoke: use the frozen 200-match sample and test the equivalence contract.
pr_path = Path(".github/workflows/official-pr-smoke.yml")
pr = pr_path.read_text(encoding="utf-8")
pr = pr.replace(
    "            simulator/official_monte_carlo.py \\\n",
    "            simulator/official_monte_carlo.py \\\n            simulator/official_orientation.py \\\n",
    1,
)
pr = pr.replace(
    "      - name: Focused tests\n        run: PYTHONPATH=. pytest -q tests/test_official_experiment.py\n",
    "      - name: Focused tests\n        run: PYTHONPATH=. pytest -q tests/test_official_experiment.py tests/test_official_orientation.py\n",
    1,
)
pr = pr.replace("            --simulations 48 \\\n", "            --simulations 200 \\\n", 1)
if "--simulations 48" in pr:
    raise RuntimeError("PR smoke still contains the obsolete 48-simulation override")
pr_path.write_text(pr, encoding="utf-8")

# Branch workflow: normal pushes use the same frozen smoke sample.
workflow_path = Path(".github/workflows/official-experiment-v1.yml")
workflow = workflow_path.read_text(encoding="utf-8")
workflow = workflow.replace("            simulations='48'\n", "            simulations='200'\n", 1)
workflow = workflow.replace(
    "            simulator/official_monte_carlo.py \\\n",
    "            simulator/official_monte_carlo.py \\\n            simulator/official_orientation.py \\\n",
    1,
)
workflow = workflow.replace(
    "      - name: Run focused official tests\n        run: PYTHONPATH=. pytest -q tests/test_official_experiment.py\n",
    "      - name: Run focused official tests\n        run: PYTHONPATH=. pytest -q tests/test_official_experiment.py tests/test_official_orientation.py\n",
    1,
)
if "simulations='48'" in workflow:
    raise RuntimeError("Branch workflow still contains the obsolete 48-simulation override")
workflow_path.write_text(workflow, encoding="utf-8")

# Documentation: state the separation between diagnostic smoke and release gate.
doc_path = Path("EXPERIMENT_DEPLOYMENT_OFFICIAL_V1.md")
doc = doc_path.read_text(encoding="utf-8")
anchor = "El smoke nunca autoriza resultados confirmatorios.\n"
addition = (
    "El smoke nunca autoriza resultados confirmatorios.\n\n"
    "La prueba de orientación del smoke usa 200 pares y se etiqueta como diagnóstico. "
    "Aunque su estimación puntual quede dentro del margen, no puede aprobar el gate de "
    "equivalencia. El gate formal requiere 2.000 pares y que todo el intervalo de confianza "
    "del 95% quede dentro de ±0,04.\n"
)
if anchor not in doc:
    raise RuntimeError("deployment documentation anchor not found")
doc_path.write_text(doc.replace(anchor, addition, 1), encoding="utf-8")

print("official statistical patch applied")
