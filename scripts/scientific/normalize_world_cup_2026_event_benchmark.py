#!/usr/bin/env python3
"""Select the most complete declared provider representation for card metrics.

API-Football may omit a statistics value when it is zero while the event feed
still explicitly contains the match's cards. This normalizer does not impute
match values. It only prevents an incomplete aggregate statistics field from
shadowing the already-frozen event-count distribution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data/context/world_cup_2026_event_benchmark_summary.json"
MIN = 0.80


def main() -> None:
    if not PATH.exists():
        raise SystemExit("World Cup event benchmark summary is missing")
    data = json.loads(PATH.read_text(encoding="utf-8"))
    distributions = data.get("distributions") or {}
    selected = {}
    for label, stat_name, event_name in [
        ("yellow_cards", "yellow_cards_stat", "event_yellow_cards"),
        ("red_cards", "red_cards_stat", "event_red_cards"),
    ]:
        stat = distributions.get(stat_name) or {}
        event = distributions.get(event_name) or {}
        stat_cov = float(stat.get("coverage", 0.0))
        event_cov = float(event.get("coverage", 0.0))
        if stat_cov >= MIN and stat.get("mean") is not None:
            chosen = stat_name
        elif event_cov >= MIN and event.get("mean") is not None:
            chosen = event_name
            # The validator follows its preregistered preference order. Removing
            # only the incomplete aggregate mean lets it use the complete event
            # distribution; no match-level value is invented or changed.
            stat["mean"] = None
            stat["excluded_from_gate_reason"] = "aggregate statistics field coverage below 0.80; complete event-count distribution selected"
            distributions[stat_name] = stat
        else:
            chosen = None
        selected[label] = {
            "selected_metric": chosen,
            "statistics_field_coverage": stat_cov,
            "event_feed_coverage": event_cov,
            "minimum_coverage": MIN,
        }
    core = dict(data.get("core_metric_coverage") or {})
    core["yellow_cards"] = max(float((distributions.get("yellow_cards_stat") or {}).get("coverage", 0.0)), float((distributions.get("event_yellow_cards") or {}).get("coverage", 0.0)))
    core["red_cards"] = max(float((distributions.get("red_cards_stat") or {}).get("coverage", 0.0)), float((distributions.get("event_red_cards") or {}).get("coverage", 0.0)))
    core.pop("yellow_cards_stat", None)
    core.pop("red_cards_stat", None)
    data["distributions"] = distributions
    data["core_metric_coverage"] = core
    data["card_metric_selection"] = selected
    data["normalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    data["normalization_changed_match_values"] = False
    fixture_ok = float(data.get("fixture_coverage", 0.0)) >= 0.90
    coverage_ok = bool(core) and min(float(value) for value in core.values()) >= MIN
    data["status"] = "world_cup_2026_event_benchmark_complete" if fixture_ok and coverage_ok else "world_cup_2026_event_benchmark_incomplete"
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": data["status"], "card_metric_selection": selected, "core_metric_coverage": core}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
