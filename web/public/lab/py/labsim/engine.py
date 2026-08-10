"""Event-based, probabilistic football match simulator.

The engine is intentionally transparent. It does not attempt continuous physics or
tracking reconstruction. It simulates possession chains, territorial progression,
shots and goals from role-aware player profiles with explicit uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from typing import Any, Iterable

import numpy as np

ROLE_ORDER = ("GK", "CB1", "CB2", "FB1", "FB2", "DM", "CM", "AM", "W1", "W2", "ST")
OUTFIELD_ROLES = ROLE_ORDER[1:]


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(max(low, min(high, value)))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


@dataclass(frozen=True)
class PlayerProfile:
    player_id: str
    name: str
    role: str
    minutes: float
    overall: float
    build_up: float
    progression: float
    creation: float
    finishing: float
    defending: float
    duels: float
    retention: float
    goalkeeping: float = 0.5
    uncertainty: float = 0.10
    synthetic: bool = False

    def sampled(self, rng: np.random.Generator) -> "PlayerProfile":
        """Draw one latent match-level ability realization."""
        sigma = max(0.015, self.uncertainty)
        values = {
            key: _clip(float(rng.normal(getattr(self, key), sigma)))
            for key in (
                "overall",
                "build_up",
                "progression",
                "creation",
                "finishing",
                "defending",
                "duels",
                "retention",
                "goalkeeping",
            )
        }
        return PlayerProfile(
            player_id=self.player_id,
            name=self.name,
            role=self.role,
            minutes=self.minutes,
            uncertainty=self.uncertainty,
            synthetic=self.synthetic,
            **values,
        )


@dataclass(frozen=True)
class TeamProfile:
    name: str
    players: tuple[PlayerProfile, ...]
    tempo: float = 0.50
    press: float = 0.50
    directness: float = 0.50

    def __post_init__(self) -> None:
        roles = [player.role for player in self.players]
        missing = [role for role in ROLE_ORDER if role not in roles]
        if missing:
            raise ValueError(f"Team {self.name!r} is missing roles: {missing}")
        if len(self.players) != len(ROLE_ORDER):
            raise ValueError("A team must contain exactly 11 role slots")

    @property
    def by_role(self) -> dict[str, PlayerProfile]:
        return {player.role: player for player in self.players}

    def sampled(self, rng: np.random.Generator) -> "TeamProfile":
        return TeamProfile(
            name=self.name,
            players=tuple(player.sampled(rng) for player in self.players),
            tempo=self.tempo,
            press=self.press,
            directness=self.directness,
        )

    def mean(self, attr: str, roles: Iterable[str] = OUTFIELD_ROLES) -> float:
        by_role = self.by_role
        return float(np.mean([getattr(by_role[role], attr) for role in roles]))


@dataclass(frozen=True)
class SimulationConfig:
    match_minutes: int = 90
    average_possessions: float = 103.0
    home_advantage: float = 0.0
    extra_time: bool = False
    seed: int | None = None


@dataclass
class MatchResult:
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
    home_completed_actions: int = 0
    away_completed_actions: int = 0
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        total_possessions = self.home_possessions + self.away_possessions
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
                round(self.home_possessions / total_possessions, 4) if total_possessions else 0.5
            ),
            "timeline": self.timeline,
        }


class MatchSimulator:
    """Simulate one match as a sequence of possessions and role-based actions."""

    def __init__(
        self,
        home: TeamProfile,
        away: TeamProfile,
        config: SimulationConfig | None = None,
    ) -> None:
        self.home = home
        self.away = away
        self.config = config or SimulationConfig()
        self.rng = np.random.default_rng(self.config.seed)

    def simulate(self, keep_timeline: bool = True) -> MatchResult:
        home = self.home.sampled(self.rng)
        away = self.away.sampled(self.rng)
        result = MatchResult(home=home.name, away=away.name)

        n_possessions = max(70, int(self.rng.poisson(self.config.average_possessions)))
        possession_strength = self._possession_strength(home) - self._possession_strength(away)
        home_possession_probability = _clip(
            _sigmoid(possession_strength * 2.1 + self.config.home_advantage), 0.34, 0.66
        )
        durations = self.rng.gamma(shape=2.2, scale=23.5, size=n_possessions)
        durations *= (self.config.match_minutes * 60) / durations.sum()
        seconds = 0.0

        for duration in durations:
            seconds += float(duration)
            minute = min(self.config.match_minutes, int(seconds // 60) + 1)
            home_attacks = bool(self.rng.random() < home_possession_probability)
            attack = home if home_attacks else away
            defend = away if home_attacks else home
            if home_attacks:
                result.home_possessions += 1
            else:
                result.away_possessions += 1

            event = self._simulate_possession(attack, defend, minute)
            if event["completed_actions"]:
                if home_attacks:
                    result.home_completed_actions += int(event["completed_actions"])
                else:
                    result.away_completed_actions += int(event["completed_actions"])
            if event["shot"]:
                if home_attacks:
                    result.home_shots += 1
                    result.home_xg += float(event["xg"])
                    if event["on_target"]:
                        result.home_shots_on_target += 1
                    if event["goal"]:
                        result.home_goals += 1
                else:
                    result.away_shots += 1
                    result.away_xg += float(event["xg"])
                    if event["on_target"]:
                        result.away_shots_on_target += 1
                    if event["goal"]:
                        result.away_goals += 1
            if keep_timeline and event["headline"]:
                result.timeline.append(
                    {
                        "minute": minute,
                        "team": attack.name,
                        "type": event["type"],
                        "actor": event["actor"],
                        "xg": round(float(event["xg"]), 3),
                        "headline": event["headline"],
                    }
                )

        return result

    def _possession_strength(self, team: TeamProfile) -> float:
        return (
            0.42 * team.mean("build_up", ("CB1", "CB2", "FB1", "FB2", "DM", "CM"))
            + 0.25 * team.mean("retention")
            + 0.18 * team.mean("duels")
            + 0.15 * team.tempo
        )

    def _simulate_possession(
        self, attack: TeamProfile, defend: TeamProfile, minute: int
    ) -> dict[str, Any]:
        atk = attack.by_role
        dfn = defend.by_role
        zone = 0
        completed = 0
        actor: PlayerProfile = atk["DM"]
        headline = ""

        max_actions = int(self.rng.integers(2, 9))
        for _ in range(max_actions):
            actor = self._choose_actor(atk, zone)
            defender = self._choose_defender(dfn, zone)
            action = self._choose_action(actor, zone, attack.directness)
            success = self._action_success(actor, defender, action, zone, defend)
            if not success:
                if zone >= 2 and self.rng.random() < 0.06 + 0.06 * actor.creation:
                    headline = f"{actor.name} pierde el balón bajo presión cerca del área"
                return self._empty_event(completed, headline, actor.name)
            completed += 1

            if action == "shot" or (zone == 3 and self.rng.random() < 0.46):
                return self._shot_event(actor, dfn["GK"], zone, completed, minute)

            if action in {"carry", "dribble", "vertical_pass"}:
                advance_probability = 0.30 + 0.42 * actor.progression - 0.22 * defender.defending
                if self.rng.random() < _clip(advance_probability, 0.12, 0.78):
                    zone = min(3, zone + 1)
            elif action == "safe_pass" and zone == 0 and self.rng.random() < 0.40:
                zone = 1

            if zone == 3 and self.rng.random() < 0.30 + 0.22 * actor.creation:
                return self._shot_event(self._choose_shooter(atk), dfn["GK"], zone, completed, minute)

        if zone >= 2 and self.rng.random() < 0.22:
            return self._shot_event(self._choose_shooter(atk), dfn["GK"], zone, completed, minute)
        return self._empty_event(completed, headline, actor.name)

    def _choose_actor(self, players: dict[str, PlayerProfile], zone: int) -> PlayerProfile:
        role_weights = {
            0: {"CB1": 2.2, "CB2": 2.2, "FB1": 1.5, "FB2": 1.5, "DM": 2.0, "CM": 1.0},
            1: {"FB1": 1.0, "FB2": 1.0, "DM": 1.6, "CM": 2.2, "AM": 1.8, "W1": 0.8, "W2": 0.8},
            2: {"CM": 1.0, "AM": 2.2, "W1": 2.0, "W2": 2.0, "ST": 1.5, "FB1": 0.6, "FB2": 0.6},
            3: {"AM": 1.3, "W1": 1.8, "W2": 1.8, "ST": 3.1, "CM": 0.4},
        }
        roles = list(role_weights[zone])
        weights = np.array(
            [role_weights[zone][role] * (0.65 + players[role].overall) for role in roles],
            dtype=float,
        )
        weights /= weights.sum()
        return players[str(self.rng.choice(roles, p=weights))]

    def _choose_defender(self, players: dict[str, PlayerProfile], zone: int) -> PlayerProfile:
        roles = {
            0: ("ST", "W1", "W2"),
            1: ("DM", "CM", "FB1", "FB2"),
            2: ("DM", "CB1", "CB2", "FB1", "FB2"),
            3: ("CB1", "CB2", "DM"),
        }[zone]
        weights = np.array([0.55 + players[role].defending + players[role].duels for role in roles])
        weights /= weights.sum()
        return players[str(self.rng.choice(list(roles), p=weights))]

    def _choose_action(self, actor: PlayerProfile, zone: int, directness: float) -> str:
        if zone == 3:
            options = ("shot", "vertical_pass", "dribble")
            weights = np.array(
                [0.38 + actor.finishing, 0.35 + actor.creation, 0.15 + actor.progression]
            )
        elif zone == 2:
            options = ("safe_pass", "vertical_pass", "carry", "dribble", "shot")
            weights = np.array(
                [
                    0.45 + actor.retention,
                    0.30 + actor.creation + directness,
                    0.15 + actor.progression,
                    0.10 + actor.progression,
                    0.03 + actor.finishing,
                ]
            )
        else:
            options = ("safe_pass", "vertical_pass", "carry", "dribble")
            weights = np.array(
                [
                    0.75 + actor.build_up,
                    0.18 + actor.progression + directness * 0.2,
                    0.10 + actor.progression,
                    0.03 + actor.progression,
                ]
            )
        weights /= weights.sum()
        return str(self.rng.choice(options, p=weights))

    def _action_success(
        self,
        actor: PlayerProfile,
        defender: PlayerProfile,
        action: str,
        zone: int,
        defend: TeamProfile,
    ) -> bool:
        attack_value = {
            "safe_pass": 0.60 * actor.build_up + 0.40 * actor.retention,
            "vertical_pass": 0.50 * actor.creation + 0.35 * actor.progression + 0.15 * actor.build_up,
            "carry": 0.60 * actor.progression + 0.40 * actor.retention,
            "dribble": 0.65 * actor.progression + 0.35 * actor.duels,
            "shot": 0.75 * actor.finishing + 0.25 * actor.creation,
        }[action]
        defence_value = 0.58 * defender.defending + 0.32 * defender.duels + 0.10 * defend.press
        base = {"safe_pass": 1.45, "vertical_pass": 0.40, "carry": 0.35, "dribble": -0.15, "shot": -0.05}[action]
        zone_penalty = (0.0, 0.12, 0.28, 0.38)[zone]
        probability = _sigmoid(base + 2.1 * (attack_value - defence_value) - zone_penalty)
        return bool(self.rng.random() < _clip(probability, 0.05, 0.97))

    def _choose_shooter(self, players: dict[str, PlayerProfile]) -> PlayerProfile:
        roles = ("ST", "W1", "W2", "AM", "CM")
        weights = np.array(
            [0.2 + 1.8 * players[role].finishing + 0.4 * players[role].creation for role in roles]
        )
        weights /= weights.sum()
        return players[str(self.rng.choice(list(roles), p=weights))]

    def _shot_event(
        self,
        shooter: PlayerProfile,
        goalkeeper: PlayerProfile,
        zone: int,
        completed: int,
        minute: int,
    ) -> dict[str, Any]:
        distance_factor = {1: 0.035, 2: 0.090, 3: 0.205}.get(zone, 0.025)
        quality = _clip(
            distance_factor
            + 0.25 * shooter.finishing
            + 0.08 * shooter.creation
            - 0.10 * goalkeeper.goalkeeping
            + float(self.rng.normal(0, 0.025)),
            0.015,
            0.62,
        )
        on_target_probability = _clip(0.22 + 0.52 * shooter.finishing - 0.06 * zone, 0.18, 0.78)
        on_target = bool(self.rng.random() < on_target_probability)
        goal = bool(self.rng.random() < (quality if on_target else quality * 0.07))
        if goal:
            headline, event_type = f"GOL de {shooter.name}", "goal"
        elif on_target:
            headline, event_type = f"Remate de {shooter.name} detenido por el portero", "shot_on_target"
        elif quality >= 0.16:
            headline, event_type = f"Ocasión peligrosa de {shooter.name} fuera", "shot_off_target"
        else:
            headline, event_type = "", "shot"
        return {
            "shot": True,
            "on_target": on_target,
            "goal": goal,
            "xg": quality,
            "completed_actions": completed,
            "type": event_type,
            "actor": shooter.name,
            "headline": headline,
            "minute": minute,
        }

    @staticmethod
    def _empty_event(completed: int, headline: str, actor: str) -> dict[str, Any]:
        return {
            "shot": False,
            "on_target": False,
            "goal": False,
            "xg": 0.0,
            "completed_actions": completed,
            "type": "turnover" if headline else "possession_end",
            "actor": actor,
            "headline": headline,
        }


def simulate_many(
    home: TeamProfile,
    away: TeamProfile,
    simulations: int = 10_000,
    seed: int = 2026,
    config: SimulationConfig | None = None,
) -> dict[str, Any]:
    if simulations < 1:
        raise ValueError("simulations must be positive")
    rng = np.random.default_rng(seed)
    home_wins = draws = away_wins = 0
    scorelines: dict[str, int] = {}
    home_goals: list[int] = []
    away_goals: list[int] = []
    home_xg: list[float] = []
    away_xg: list[float] = []
    representative: MatchResult | None = None
    closest_distance = float("inf")
    base = config or SimulationConfig()

    for _ in range(simulations):
        sim_seed = int(rng.integers(0, 2**32 - 1))
        result = MatchSimulator(
            home, away, SimulationConfig(**{**base.__dict__, "seed": sim_seed})
        ).simulate(keep_timeline=False)
        home_goals.append(result.home_goals)
        away_goals.append(result.away_goals)
        home_xg.append(result.home_xg)
        away_xg.append(result.away_xg)
        if result.home_goals > result.away_goals:
            home_wins += 1
        elif result.home_goals == result.away_goals:
            draws += 1
        else:
            away_wins += 1
        score = f"{result.home_goals}-{result.away_goals}"
        scorelines[score] = scorelines.get(score, 0) + 1

    mean_home = float(np.mean(home_goals))
    mean_away = float(np.mean(away_goals))
    for _ in range(250):
        sim_seed = int(rng.integers(0, 2**32 - 1))
        result = MatchSimulator(
            home, away, SimulationConfig(**{**base.__dict__, "seed": sim_seed})
        ).simulate(keep_timeline=True)
        distance = abs(result.home_goals - mean_home) + abs(result.away_goals - mean_away)
        if distance < closest_distance:
            closest_distance = distance
            representative = result

    top_scorelines = sorted(scorelines.items(), key=lambda item: (-item[1], item[0]))[:10]
    return {
        "status": "exploratory_simulation_completed",
        "simulations": simulations,
        "home": home.name,
        "away": away.name,
        "home_win_probability": home_wins / simulations,
        "draw_probability": draws / simulations,
        "away_win_probability": away_wins / simulations,
        "mean_home_goals": mean_home,
        "mean_away_goals": mean_away,
        "mean_home_xg": float(np.mean(home_xg)),
        "mean_away_xg": float(np.mean(away_xg)),
        "top_scorelines": [
            {"score": score, "probability": count / simulations} for score, count in top_scorelines
        ],
        "representative_match": representative.as_dict() if representative else None,
        "methodological_gate": {
            "publication_as_final_result_allowed": False,
            "reason": "Exploratory engine built on partial annual coverage and provisional role resolution.",
        },
    }
