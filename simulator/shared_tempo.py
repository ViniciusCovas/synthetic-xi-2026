"""Shared-tempo extension for the calibrated event simulator.

A latent match-wide tempo variable induces positive dependence between both
teams' event volumes. Mixing over tempo raises the probability of low-event,
low-score matches without adding a post-hoc score correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

import numpy as np

from .calibrated_core import (
    CalibratedConfig,
    CalibratedMatchSimulator,
    CalibratedResult,
)
from .engine import _clip


@dataclass(frozen=True)
class SharedTempoConfig(CalibratedConfig):
    shared_tempo_sigma: float = 0.0
    shot_tempo_elasticity: float = 0.35

    def __post_init__(self) -> None:
        if self.shared_tempo_sigma < 0 or self.shared_tempo_sigma > 1.0:
            raise ValueError("shared_tempo_sigma must be in [0, 1]")
        if self.shot_tempo_elasticity < 0 or self.shot_tempo_elasticity > 1.0:
            raise ValueError("shot_tempo_elasticity must be in [0, 1]")


class SharedTempoMatchSimulator(CalibratedMatchSimulator):
    config: SharedTempoConfig

    def __init__(self, home, away, targets, config: SharedTempoConfig | None = None):
        super().__init__(home, away, targets, config or SharedTempoConfig())
        self._tempo_multiplier = 1.0

    def simulate(self, keep_timeline: bool = True) -> CalibratedResult:
        home = self.home.sampled(self.rng)
        away = self.away.sampled(self.rng)
        result = CalibratedResult(home.name, away.name)

        sigma = self.config.shared_tempo_sigma
        self._tempo_multiplier = float(
            self.rng.lognormal(mean=-0.5 * sigma * sigma, sigma=sigma)
        )
        expected_possessions = (
            self.targets.model_possessions_per_match * self._tempo_multiplier
        )
        count = max(55, int(self.rng.poisson(expected_possessions)))
        home_probability = self._possession_probability(home, away)
        durations = self.rng.gamma(2.2, 23.5, size=count)
        durations *= (self.config.match_minutes * 60) / durations.sum()
        elapsed = 0.0

        for duration in durations:
            elapsed += float(duration)
            minute = min(self.config.match_minutes, int(elapsed // 60) + 1)
            home_attacks = bool(self.rng.random() < home_probability)
            attack, defend = (home, away) if home_attacks else (away, home)
            prefix = "home" if home_attacks else "away"
            setattr(
                result,
                f"{prefix}_possessions",
                getattr(result, f"{prefix}_possessions") + 1,
            )
            event = self._possession(attack, defend)
            if event["shot"]:
                setattr(result, f"{prefix}_shots", getattr(result, f"{prefix}_shots") + 1)
                setattr(result, f"{prefix}_xg", getattr(result, f"{prefix}_xg") + event["xg"])
                if event["on_target"]:
                    setattr(
                        result,
                        f"{prefix}_shots_on_target",
                        getattr(result, f"{prefix}_shots_on_target") + 1,
                    )
                if event["goal"]:
                    setattr(result, f"{prefix}_goals", getattr(result, f"{prefix}_goals") + 1)
            if keep_timeline and event["headline"]:
                result.timeline.append(
                    {
                        "minute": minute,
                        "team": attack.name,
                        "type": event["type"],
                        "actor": event["actor"],
                        "zone": event["zone"],
                        "xg": round(event["xg"], 3),
                        "headline": event["headline"],
                        "shared_tempo_multiplier": round(self._tempo_multiplier, 4),
                    }
                )
        return result

    def _possession(self, attack, defend):
        edge = self._attack_strength(attack) - self._defence_strength(defend)
        zone_score = float(
            self.rng.normal(
                0.48 + 0.30 * edge + 0.10 * (attack.directness - 0.5),
                0.20,
            )
        )
        zone = 1 if zone_score < 0.38 else 2 if zone_score < 0.67 else 3
        zone_adjustment = 0.18 if zone == 3 else -0.12 if zone == 1 else 0.0
        tempo_effect = self._tempo_multiplier ** self.config.shot_tempo_elasticity
        shot_probability = self.targets.shot_rate * tempo_effect * exp(
            self.config.shot_edge_scale * edge + zone_adjustment
        )
        shooter = self._choose_shooter(attack, zone)
        if self.rng.random() >= _clip(shot_probability, 0.02, 0.62):
            turnover_probability = _clip(
                0.08
                + 0.10 * defend.press
                - 0.06 * attack.mean("retention")
                + 0.03 * max(0.0, 1.0 - self._tempo_multiplier),
                0.03,
                0.25,
            )
            if zone >= 2 and self.rng.random() < turnover_probability:
                return self._empty(
                    shooter,
                    zone,
                    f"{shooter.name} pierde el balón bajo presión",
                )
            return self._empty(shooter, zone, "")
        return self._shot(shooter, defend.by_role["GK"], zone, edge)
