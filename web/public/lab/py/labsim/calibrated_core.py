"""Núcleo calibrado do simulador de partida v0.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from typing import Any

import numpy as np

from .engine import PlayerProfile, TeamProfile, _clip


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


@dataclass(frozen=True)
class CalibrationTargets:
    source_match_count: int
    mean_goals_per_match: float
    mean_shots_per_match: float
    mean_shots_on_target_per_match: float
    zero_zero_rate: float
    home_win_rate: float
    draw_rate: float
    away_win_rate: float
    model_possessions_per_match: float = 104.0

    def __post_init__(self) -> None:
        if self.source_match_count < 1 or self.mean_goals_per_match <= 0:
            raise ValueError("Invalid calibration sample")
        if self.mean_shots_per_match <= self.mean_goals_per_match:
            raise ValueError("Shots must exceed goals")
        if self.model_possessions_per_match <= self.mean_shots_per_match:
            raise ValueError("Possessions must exceed shots")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationTargets":
        names = cls.__dataclass_fields__.keys()
        return cls(**{name: payload[name] for name in names})

    @property
    def shot_rate(self) -> float:
        return _clip(
            self.mean_shots_per_match / self.model_possessions_per_match,
            0.05,
            0.55,
        )

    @property
    def goal_rate(self) -> float:
        return _clip(
            self.mean_goals_per_match / self.mean_shots_per_match,
            0.04,
            0.30,
        )

    @property
    def on_target_rate(self) -> float:
        return _clip(
            self.mean_shots_on_target_per_match / self.mean_shots_per_match,
            0.20,
            0.70,
        )


@dataclass(frozen=True)
class CalibratedConfig:
    match_minutes: int = 90
    home_advantage: float = 0.0
    seed: int | None = None
    ability_scale: float = 0.75
    shot_edge_scale: float = 0.95
    conversion_edge_scale: float = 0.80


@dataclass
class CalibratedResult:
    home: str
    away: str
    home_goals: int = 0
    away_goals: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0
    home_shots: int = 0
    away_shots: int = 0
    home_shots_on_target: int = 0
    away_shots_on_target: int = 0
    home_possessions: int = 0
    away_possessions: int = 0
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        possessions = self.home_possessions + self.away_possessions
        return {
            "home": self.home,
            "away": self.away,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_xg": round(self.home_xg, 3),
            "away_xg": round(self.away_xg, 3),
            "home_shots": self.home_shots,
            "away_shots": self.away_shots,
            "home_shots_on_target": self.home_shots_on_target,
            "away_shots_on_target": self.away_shots_on_target,
            "home_possession_share": (
                round(self.home_possessions / possessions, 4)
                if possessions
                else 0.5
            ),
            "timeline": self.timeline,
        }


class CalibratedMatchSimulator:
    def __init__(
        self,
        home: TeamProfile,
        away: TeamProfile,
        targets: CalibrationTargets,
        config: CalibratedConfig | None = None,
    ) -> None:
        self.home = home
        self.away = away
        self.targets = targets
        self.config = config or CalibratedConfig()
        self.rng = np.random.default_rng(self.config.seed)

    def simulate(self, keep_timeline: bool = True) -> CalibratedResult:
        home = self.home.sampled(self.rng)
        away = self.away.sampled(self.rng)
        result = CalibratedResult(home.name, away.name)
        count = max(
            70,
            int(self.rng.poisson(self.targets.model_possessions_per_match)),
        )
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
                setattr(
                    result,
                    f"{prefix}_shots",
                    getattr(result, f"{prefix}_shots") + 1,
                )
                setattr(
                    result,
                    f"{prefix}_xg",
                    getattr(result, f"{prefix}_xg") + event["xg"],
                )
                if event["on_target"]:
                    setattr(
                        result,
                        f"{prefix}_shots_on_target",
                        getattr(result, f"{prefix}_shots_on_target") + 1,
                    )
                if event["goal"]:
                    setattr(
                        result,
                        f"{prefix}_goals",
                        getattr(result, f"{prefix}_goals") + 1,
                    )
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
                    }
                )
        return result

    def _possession_probability(
        self, home: TeamProfile, away: TeamProfile
    ) -> float:
        roles = ("CB1", "CB2", "FB1", "FB2", "DM", "CM")

        def strength(team: TeamProfile) -> float:
            return (
                0.40 * team.mean("build_up", roles)
                + 0.32 * team.mean("retention")
                + 0.16 * team.mean("duels")
                + 0.12 * team.tempo
            )

        edge = (strength(home) - strength(away)) * self.config.ability_scale
        return _clip(
            sigmoid(2 * edge + self.config.home_advantage),
            0.34,
            0.66,
        )

    def _possession(
        self, attack: TeamProfile, defend: TeamProfile
    ) -> dict[str, Any]:
        edge = self._attack_strength(attack) - self._defence_strength(defend)
        zone_score = float(
            self.rng.normal(
                0.48 + 0.30 * edge + 0.10 * (attack.directness - 0.5),
                0.20,
            )
        )
        zone = 1 if zone_score < 0.38 else 2 if zone_score < 0.67 else 3
        zone_adjustment = 0.18 if zone == 3 else -0.12 if zone == 1 else 0.0
        shot_probability = self.targets.shot_rate * exp(
            self.config.shot_edge_scale * edge + zone_adjustment
        )
        shooter = self._choose_shooter(attack, zone)
        if self.rng.random() >= _clip(shot_probability, 0.03, 0.58):
            turnover_probability = _clip(
                0.08
                + 0.10 * defend.press
                - 0.06 * attack.mean("retention"),
                0.03,
                0.22,
            )
            if zone >= 2 and self.rng.random() < turnover_probability:
                return self._empty(
                    shooter,
                    zone,
                    f"{shooter.name} pierde el balón bajo presión",
                )
            return self._empty(shooter, zone, "")
        return self._shot(shooter, defend.by_role["GK"], zone, edge)

    @staticmethod
    def _attack_strength(team: TeamProfile) -> float:
        return (
            0.24 * team.mean("progression")
            + 0.24 * team.mean("creation")
            + 0.21 * team.mean("finishing", ("AM", "W1", "W2", "ST"))
            + 0.17 * team.mean("retention")
            + 0.14 * team.mean("duels")
        )

    @staticmethod
    def _defence_strength(team: TeamProfile) -> float:
        roles = ("CB1", "CB2", "FB1", "FB2", "DM")
        return (
            0.34 * team.mean("defending", roles)
            + 0.22 * team.mean("duels", roles)
            + 0.22 * team.by_role["GK"].goalkeeping
            + 0.12 * team.press
            + 0.10 * team.mean("retention")
        )

    def _choose_shooter(
        self, team: TeamProfile, zone: int
    ) -> PlayerProfile:
        players = team.by_role
        roles = ("ST", "W1", "W2", "AM", "CM")
        boosts = {
            "ST": 1.35 if zone == 3 else 1.05,
            "W1": 1.05,
            "W2": 1.05,
            "AM": 1.0,
            "CM": 0.55,
        }
        weights = np.array(
            [
                (
                    0.15
                    + 1.70 * players[role].finishing
                    + 0.45 * players[role].creation
                )
                * boosts[role]
                for role in roles
            ],
            dtype=float,
        )
        weights /= weights.sum()
        return players[str(self.rng.choice(list(roles), p=weights))]

    def _shot(
        self,
        shooter: PlayerProfile,
        goalkeeper: PlayerProfile,
        zone: int,
        team_edge: float,
    ) -> dict[str, Any]:
        finishing_edge = (
            shooter.finishing
            - 0.50 * goalkeeper.goalkeeping
            - 0.25 * goalkeeper.overall
        )
        zone_adjustment = {1: -0.55, 2: -0.08, 3: 0.40}[zone]
        goal_probability = self.targets.goal_rate * exp(
            self.config.conversion_edge_scale * finishing_edge
            + zone_adjustment
            + 0.20 * team_edge
        )
        goal_probability = _clip(goal_probability, 0.015, 0.55)
        on_target_probability = _clip(
            self.targets.on_target_rate
            + 0.18 * (shooter.finishing - 0.5)
            - (0.06 if zone == 1 else 0.0),
            0.18,
            0.78,
        )
        on_target = bool(self.rng.random() < on_target_probability)
        goal_given_on_target = _clip(
            goal_probability / max(on_target_probability, 1e-6),
            0.03,
            0.82,
        )
        goal = bool(on_target and self.rng.random() < goal_given_on_target)

        if goal:
            event_type, headline = "goal", f"GOL de {shooter.name}"
        elif on_target:
            event_type = "shot_on_target"
            headline = f"Remate de {shooter.name} detenido por el portero"
        elif goal_probability > 0.13:
            event_type, headline = "shot_off_target", f"Ocasión de {shooter.name} fuera"
        else:
            event_type, headline = "shot", ""
        return {
            "shot": True,
            "on_target": on_target,
            "goal": goal,
            "xg": float(goal_probability),
            "type": event_type,
            "actor": shooter.name,
            "zone": zone,
            "headline": headline,
        }

    @staticmethod
    def _empty(
        actor: PlayerProfile, zone: int, headline: str
    ) -> dict[str, Any]:
        return {
            "shot": False,
            "on_target": False,
            "goal": False,
            "xg": 0.0,
            "type": "turnover" if headline else "possession_end",
            "actor": actor.name,
            "zone": zone,
            "headline": headline,
        }
