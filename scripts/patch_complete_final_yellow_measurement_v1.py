#!/usr/bin/env python3
"""Align simulator yellow-card outputs with the frozen provider taxonomy.

This patch changes only counters and Monte Carlo aggregation. It does not alter
random draws, foul/card probabilities, dismissals, player states or winners.
"""
from __future__ import annotations

import hashlib
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "simulator/complete_final.py"
MONTE_CARLO = ROOT / "simulator/complete_final_monte_carlo.py"
CONFIG = ROOT / "config/complete_final_yellow_card_measurement_v1.json"
STATUS = ROOT / "data/model_readiness/complete_final_yellow_card_measurement_v1_status.json"
MARKER = "COMPLETE_FINAL_YELLOW_CARD_MEASUREMENT_V1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {label} block; found {count}")
    return source.replace(old, new, 1)


def patch_engine() -> bool:
    source = ENGINE.read_text(encoding="utf-8")
    if MARKER in source:
        return False
    source = replace_once(
        source,
        "    yellows: int = 0\n    reds: int = 0\n",
        "    yellows: int = 0\n    # COMPLETE_FINAL_YELLOW_CARD_MEASUREMENT_V1\n    second_yellows: int = 0\n    reds: int = 0\n",
        "team-state yellow counter",
    )
    source = replace_once(
        source,
        '            "yellows": self.yellows,\n            "reds": self.reds,\n',
        '            "yellows": self.yellows,\n            "second_yellows": self.second_yellows,\n            "benchmark_comparable_yellows": self.yellows - self.second_yellows,\n            "reds": self.reds,\n',
        "snapshot yellow fields",
    )
    source = replace_once(
        source,
        "            if defender.yellow_cards >= 2:\n                defender.sent_off = True\n",
        "            if defender.yellow_cards >= 2:\n                defend.second_yellows += 1\n                defender.sent_off = True\n",
        "second-yellow counter",
    )
    ENGINE.write_text(source, encoding="utf-8")
    py_compile.compile(str(ENGINE), doraise=True)
    return True


def patch_monte_carlo() -> bool:
    source = MONTE_CARLO.read_text(encoding="utf-8")
    if MARKER in source:
        return False
    source = replace_once(
        source,
        '        "mean_total_yellows": float(np.mean([row["total_yellows"] for row in rows])),\n        "mean_total_reds": float(np.mean([row["total_reds"] for row in rows])),\n',
        '        # COMPLETE_FINAL_YELLOW_CARD_MEASUREMENT_V1\n        "mean_total_yellows": float(np.mean([row["total_yellows"] for row in rows])),\n        "mean_total_yellows_raw": float(np.mean([row["total_yellows_raw"] for row in rows])),\n        "mean_total_second_yellows": float(np.mean([row["total_second_yellows"] for row in rows])),\n        "mean_total_reds": float(np.mean([row["total_reds"] for row in rows])),\n',
        "Monte Carlo yellow summary",
    )
    source = replace_once(
        source,
        '        "total_yellows": home_stats["yellows"] + away_stats["yellows"],\n        "total_reds": home_stats["reds"] + away_stats["reds"],\n',
        '        "total_yellows": (\n            home_stats.get("benchmark_comparable_yellows", home_stats["yellows"])\n            + away_stats.get("benchmark_comparable_yellows", away_stats["yellows"])\n        ),\n        "total_yellows_raw": home_stats["yellows"] + away_stats["yellows"],\n        "total_second_yellows": (\n            home_stats.get("second_yellows", 0) + away_stats.get("second_yellows", 0)\n        ),\n        "total_reds": home_stats["reds"] + away_stats["reds"],\n',
        "compact-row yellow aggregation",
    )
    MONTE_CARLO.write_text(source, encoding="utf-8")
    py_compile.compile(str(MONTE_CARLO), doraise=True)
    return True


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit("Missing preregistered yellow-card measurement configuration")
    if not ENGINE.exists() or not MONTE_CARLO.exists():
        raise SystemExit("Complete-final source must be materialized before measurement patch")

    before = {
        "complete_final_py": digest(ENGINE),
        "complete_final_monte_carlo_py": digest(MONTE_CARLO),
    }
    engine_changed = patch_engine()
    monte_changed = patch_monte_carlo()
    after = {
        "complete_final_py": digest(ENGINE),
        "complete_final_monte_carlo_py": digest(MONTE_CARLO),
    }
    status = {
        "status": "complete_final_yellow_card_measurement_v1_applied",
        "version": "complete_final_yellow_card_measurement_v1",
        "engine_source_changed": engine_changed,
        "monte_carlo_source_changed": monte_changed,
        "source_sha256_before_patch": before,
        "source_sha256_after_patch": after,
        "preregistered_config_sha256": digest(CONFIG),
        "raw_yellows_preserved": True,
        "second_yellows_separately_recorded": True,
        "benchmark_comparable_yellows_exclude_second_yellows": True,
        "event_generation_changed": False,
        "match_outcomes_changed": False,
        "player_abilities_changed": False,
        "team_strength_parameters_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
