#!/usr/bin/env python3
"""Apply the preregistered Complete Final Engine v1.1 rules correction.

The reviewed v1 source bundle remains immutable. This deterministic patch is
applied immediately after bundle materialization, before any import or result.
It changes only the substitution-window implementation documented in
COMPLETE_FINAL_RULES_FIX_V1_1.md.
"""
from __future__ import annotations

import hashlib
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "simulator" / "complete_final.py"
CONFIG = ROOT / "config" / "complete_final_rules_fix_v1_1.json"
STATUS = ROOT / "data" / "model_readiness" / "complete_final_rules_fix_v1_1_status.json"
MARKER = "COMPLETE_FINAL_RULES_FIX_V1_1_BATCH_WINDOWS"
WRAPPER_MARKER = "Transparent bootstrap for the complete-final source bundle"

NEW_BLOCK = '''    # COMPLETE_FINAL_RULES_FIX_V1_1_BATCH_WINDOWS
    def _maybe_tactical_substitution(
        self,
        team: TeamMatchState,
        clock: float,
        extra_time: bool,
        keep_timeline: bool,
        opponent: TeamMatchState,
    ) -> None:
        marks = (
            ((60.0, "60"), (72.0, "72"), (82.0, "82"))
            if not extra_time
            else ((105.0, "ET"),)
        )
        for threshold, mark in marks:
            if clock < threshold or mark in team.used_substitution_marks:
                continue
            team.used_substitution_marks.add(mark)
            if not team.can_substitute(extra_time, self.config.rules):
                continue

            if extra_time:
                remaining_windows = (
                    self.config.rules.extra_time_substitution_windows
                    - team.extra_time_windows
                )
                maximum = (
                    self.config.rules.regulation_substitutions
                    + self.config.rules.extra_time_substitution
                )
            else:
                remaining_windows = (
                    self.config.rules.regulation_substitution_windows
                    - team.substitution_windows
                )
                maximum = self.config.rules.regulation_substitutions

            remaining_substitutions = maximum - team.substitutions
            if remaining_windows <= 0 or remaining_substitutions <= 0:
                continue

            # A same-clock group is one legal substitution window. In regulation,
            # ceil(remaining substitutions / remaining windows) yields 2+2+1
            # when all five substitutions and all three windows remain.
            batch_size = (
                remaining_substitutions
                if extra_time
                else max(
                    1,
                    (
                        remaining_substitutions
                        + remaining_windows
                        - 1
                    )
                    // remaining_windows,
                )
            )
            active = team.active_roles(OUTFIELD_ROLES)
            if not active:
                continue
            fatigue_cutoff = 0.91 if threshold <= 60 else 0.95
            tired = sorted(
                (
                    role
                    for role in active
                    if team.players[role].stamina < fatigue_cutoff
                ),
                key=lambda role: team.players[role].stamina,
            )
            remainder = sorted(
                (role for role in active if role not in tired),
                key=lambda role: team.players[role].stamina,
            )
            selected = (tired + remainder)[:batch_size]
            if not selected:
                continue

            period = "extra_time" if extra_time else "regulation"
            for index, role in enumerate(selected):
                self._perform_substitution(
                    team,
                    role,
                    clock + index * 0.001,
                    extra_time,
                    keep_timeline,
                    opponent,
                    period,
                    injury=False,
                    consume_window=index == 0,
                )
            break

    def _perform_substitution(
        self,
        team: TeamMatchState,
        role: str,
        clock: float,
        extra_time: bool,
        keep_timeline: bool,
        opponent: TeamMatchState,
        period: str,
        injury: bool,
        consume_window: bool = True,
    ) -> None:
        if not team.can_substitute(extra_time, self.config.rules):
            return
        if consume_window:
            if extra_time:
                if (
                    team.extra_time_windows
                    >= self.config.rules.extra_time_substitution_windows
                ):
                    return
            elif (
                team.substitution_windows
                >= self.config.rules.regulation_substitution_windows
            ):
                return

        outgoing, incoming = team.replace_role(role, clock, self.rng, self.config)
        if consume_window:
            if extra_time:
                team.extra_time_windows += 1
            else:
                team.substitution_windows += 1
        reason = "por lesão" if injury else "tática"
        self._event(
            clock,
            team.side,
            "substitution",
            f"Substituição {reason}: sai {outgoing}, entra {incoming}",
            team,
            opponent,
            keep_timeline,
            period=period,
            actor=incoming,
        )

'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit("Missing preregistered v1.1 rules-fix configuration")
    if not TARGET.exists():
        raise SystemExit("Complete-final source was not materialized")

    source = TARGET.read_text(encoding="utf-8")
    if WRAPPER_MARKER in source:
        raise SystemExit("Run the v1 bundle installer before the v1.1 rules patch")
    before_sha = digest(TARGET)
    changed = False

    if MARKER not in source:
        start_token = "    def _maybe_tactical_substitution("
        end_token = "    def _penalty_shootout("
        start = source.find(start_token)
        end = source.find(end_token, start + 1)
        if start < 0 or end < 0 or end <= start:
            raise SystemExit("Frozen v1 substitution methods were not found")
        old_block = source[start:end]
        required_fragments = [
            '((60.0, "60"), (72.0, "72"), (82.0, "82"))',
            "team.substitution_windows += 1",
            "def _perform_substitution(",
        ]
        if not all(fragment in old_block for fragment in required_fragments):
            raise SystemExit("Frozen v1 substitution block does not match the reviewed source")
        TARGET.write_text(source[:start] + NEW_BLOCK + source[end:], encoding="utf-8")
        changed = True

    patched = TARGET.read_text(encoding="utf-8")
    if MARKER not in patched:
        raise SystemExit("v1.1 substitution marker absent after patch")
    py_compile.compile(str(TARGET), doraise=True)
    after_sha = digest(TARGET)

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "complete_final_rules_fix_v1_1_applied",
        "version": "complete_final_v1_1_rules_fix",
        "patch_changed_materialized_source": changed,
        "source_sha256_before_patch": before_sha,
        "source_sha256_after_patch": after_sha,
        "preregistered_config_sha256": digest(CONFIG),
        "batch_rule": "ceil(remaining substitutions / remaining windows)",
        "same_clock_batch_consumes_one_window": True,
        "player_abilities_changed": False,
        "team_strength_parameters_changed": False,
        "selection_thresholds_changed": False,
        "event_tolerances_changed": False,
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
