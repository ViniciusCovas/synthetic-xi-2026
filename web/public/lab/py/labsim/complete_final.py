"""Complete knockout-final state machine for Synthetic XI.

This module extends the calibrated 90-minute engine with the events and rules
needed for a reproducible final: dynamic tactics, fatigue, fouls, cards,
injuries, substitutions, VAR, stoppage time, extra time and penalties.

The model remains an event simulator, not a reconstruction of continuous
football physics. All structural assumptions are explicit in ``FinalConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import exp
from typing import Any, Iterable

import numpy as np

from .calibrated_core import CalibrationTargets
from .engine import OUTFIELD_ROLES, ROLE_ORDER, PlayerProfile, TeamProfile, _clip


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


@dataclass(frozen=True)
class FinalRules:
    regulation_minutes: int = 90
    extra_time_period_minutes: int = 15
    regulation_substitutions: int = 5
    extra_time_substitution: int = 1
    regulation_substitution_windows: int = 3
    extra_time_substitution_windows: int = 1
    initial_penalty_kicks: int = 5
    maximum_sudden_death_rounds: int = 20

    def __post_init__(self) -> None:
        if self.regulation_minutes != 90:
            raise ValueError("The preregistered primary final uses 90 regulation minutes")
        if self.extra_time_period_minutes != 15:
            raise ValueError("Extra-time periods must be 15 minutes")
        if self.regulation_substitutions < 0 or self.extra_time_substitution < 0:
            raise ValueError("Substitution limits cannot be negative")


@dataclass(frozen=True)
class FinalConfig:
    seed: int | None = None
    home_advantage: float = 0.0
    ability_scale: float = 0.75
    shot_edge_scale: float = 0.95
    conversion_edge_scale: float = 0.80
    home_coordination_mean: float = 1.0
    away_coordination_mean: float = 1.0
    coordination_sd: float = 0.035
    bench_quality: float = 0.91
    bench_uncertainty: float = 0.045
    fouls_per_team_90: float = 11.2
    yellows_per_team_90: float = 2.15
    direct_reds_per_team_90: float = 0.055
    injuries_per_team_90: float = 0.18
    severe_injury_share: float = 0.22
    penalty_foul_share_in_zone_three: float = 0.035
    var_review_goal_probability: float = 0.34
    var_goal_overturn_probability: float = 0.075
    var_penalty_review_probability: float = 0.44
    var_penalty_overturn_probability: float = 0.09
    fatigue_per_90: float = 0.19
    referee_strictness_mean: float = 1.0
    referee_strictness_sd: float = 0.12
    rules: FinalRules = field(default_factory=FinalRules)

    def __post_init__(self) -> None:
        probability_fields = (
            "severe_injury_share",
            "penalty_foul_share_in_zone_three",
            "var_review_goal_probability",
            "var_goal_overturn_probability",
            "var_penalty_review_probability",
            "var_penalty_overturn_probability",
        )
        for name in probability_fields:
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.bench_quality <= 0 or self.coordination_sd < 0:
            raise ValueError("Invalid structural parameter")


@dataclass
class PlayerMatchState:
    profile: PlayerProfile
    stamina: float = 1.0
    yellow_cards: int = 0
    sent_off: bool = False
    injured: bool = False
    severe_injury: bool = False
    entry_minute: float = 0.0
    substitute_generation: int = 0

    @property
    def active(self) -> bool:
        return not self.sent_off and not self.severe_injury

    def effective(self, attribute: str) -> float:
        base = float(getattr(self.profile, attribute))
        fatigue_multiplier = 0.70 + 0.30 * _clip(self.stamina)
        injury_multiplier = 0.88 if self.injured else 1.0
        return _clip(base * fatigue_multiplier * injury_multiplier)


@dataclass
class TeamMatchState:
    name: str
    side: str
    players: dict[str, PlayerMatchState]
    tempo: float
    press: float
    directness: float
    coordination: float
    goals: int = 0
    regulation_goals: int = 0
    extra_time_goals: int = 0
    xg: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    regulation_xg: float = 0.0
    regulation_shots: int = 0
    regulation_shots_on_target: int = 0
    regulation_possessions: int = 0
    possessions: int = 0
    fouls: int = 0
    yellows: int = 0
    # COMPLETE_FINAL_YELLOW_CARD_MEASUREMENT_V1
    second_yellows: int = 0
    reds: int = 0
    injuries: int = 0
    substitutions: int = 0
    substitution_windows: int = 0
    extra_time_windows: int = 0
    var_reviews: int = 0
    penalties_awarded: int = 0
    tactic: str = "balanced"
    used_substitution_marks: set[str] = field(default_factory=set)

    @classmethod
    def from_profile(
        cls,
        team: TeamProfile,
        side: str,
        coordination: float,
    ) -> "TeamMatchState":
        return cls(
            name=team.name,
            side=side,
            players={
                player.role: PlayerMatchState(profile=player)
                for player in team.players
            },
            tempo=team.tempo,
            press=team.press,
            directness=team.directness,
            coordination=coordination,
        )

    @property
    def active_count(self) -> int:
        return sum(player.active for player in self.players.values())

    @property
    def numerical_factor(self) -> float:
        return _clip(self.active_count / 11.0, 0.64, 1.0)

    def active_roles(self, roles: Iterable[str] = ROLE_ORDER) -> list[str]:
        return [role for role in roles if role in self.players and self.players[role].active]

    def mean(self, attribute: str, roles: Iterable[str] = OUTFIELD_ROLES) -> float:
        active = self.active_roles(roles)
        if not active:
            return 0.0
        return float(np.mean([self.players[role].effective(attribute) for role in active]))

    def choose_role(
        self,
        rng: np.random.Generator,
        roles: Iterable[str],
        attribute: str = "overall",
        inverse: bool = False,
    ) -> str:
        active = self.active_roles(roles)
        if not active:
            active = self.active_roles(ROLE_ORDER)
        if not active:
            raise RuntimeError(f"{self.name} has no active players")
        values = np.array(
            [0.10 + self.players[role].effective(attribute) for role in active],
            dtype=float,
        )
        if inverse:
            values = 1.25 - np.clip(values, 0.0, 1.25)
            values += 0.05
        values /= values.sum()
        return str(rng.choice(active, p=values))

    def can_substitute(self, extra_time: bool, rules: FinalRules) -> bool:
        maximum = rules.regulation_substitutions + (
            rules.extra_time_substitution if extra_time else 0
        )
        return self.substitutions < maximum

    def replace_role(
        self,
        role: str,
        minute: float,
        rng: np.random.Generator,
        config: FinalConfig,
    ) -> tuple[str, str]:
        outgoing = self.players[role]
        source = outgoing.profile
        attributes = {}
        for attribute in (
            "overall",
            "build_up",
            "progression",
            "creation",
            "finishing",
            "defending",
            "duels",
            "retention",
            "goalkeeping",
        ):
            sampled = rng.normal(
                float(getattr(source, attribute)) * config.bench_quality,
                config.bench_uncertainty,
            )
            attributes[attribute] = _clip(float(sampled))
        generation = outgoing.substitute_generation + 1
        reserve = PlayerProfile(
            player_id=f"{source.player_id}-BENCH-{generation}",
            name=f"{source.name} · reserva funcional {generation}",
            role=role,
            minutes=0.0,
            uncertainty=max(source.uncertainty, config.bench_uncertainty),
            synthetic=source.synthetic,
            **attributes,
        )
        self.players[role] = PlayerMatchState(
            profile=reserve,
            stamina=1.0,
            entry_minute=minute,
            substitute_generation=generation,
        )
        self.substitutions += 1
        return outgoing.profile.name, reserve.name

    def snapshot(self) -> dict[str, Any]:
        return {
            "goals": self.goals,
            "regulation_goals": self.regulation_goals,
            "extra_time_goals": self.extra_time_goals,
            "xg": round(self.xg, 4),
            "shots": self.shots,
            "shots_on_target": self.shots_on_target,
            "regulation_xg": round(self.regulation_xg, 4),
            "regulation_shots": self.regulation_shots,
            "regulation_shots_on_target": self.regulation_shots_on_target,
            "regulation_possessions": self.regulation_possessions,
            "possessions": self.possessions,
            "fouls": self.fouls,
            "yellows": self.yellows,
            "second_yellows": self.second_yellows,
            "benchmark_comparable_yellows": self.yellows - self.second_yellows,
            "reds": self.reds,
            "injuries": self.injuries,
            "substitutions": self.substitutions,
            "substitution_windows": self.substitution_windows,
            "extra_time_windows": self.extra_time_windows,
            "var_reviews": self.var_reviews,
            "penalties_awarded": self.penalties_awarded,
            "players_remaining": self.active_count,
            "final_tactic": self.tactic,
            "coordination_draw": round(self.coordination, 5),
        }


@dataclass
class CompleteFinalResult:
    home: str
    away: str
    seed: int | None
    regulation_home_goals: int
    regulation_away_goals: int
    extra_time_home_goals: int
    extra_time_away_goals: int
    home_penalties: int | None
    away_penalties: int | None
    winner: str
    decided_by: str
    home_stats: dict[str, Any]
    away_stats: dict[str, Any]
    first_half_added_time: int
    second_half_added_time: int
    extra_time_first_added_time: int
    extra_time_second_added_time: int
    referee_strictness: float
    timeline: list[dict[str, Any]] = field(default_factory=list)

    @property
    def home_goals(self) -> int:
        return self.regulation_home_goals + self.extra_time_home_goals

    @property
    def away_goals(self) -> int:
        return self.regulation_away_goals + self.extra_time_away_goals

    def as_dict(self) -> dict[str, Any]:
        return {
            "home": self.home,
            "away": self.away,
            "seed": self.seed,
            "regulation_score": (
                f"{self.regulation_home_goals}-{self.regulation_away_goals}"
            ),
            "extra_time_score": (
                f"{self.extra_time_home_goals}-{self.extra_time_away_goals}"
            ),
            "final_score_before_penalties": f"{self.home_goals}-{self.away_goals}",
            "home_penalties": self.home_penalties,
            "away_penalties": self.away_penalties,
            "winner": self.winner,
            "decided_by": self.decided_by,
            "home_stats": self.home_stats,
            "away_stats": self.away_stats,
            "stoppage_time": {
                "first_half": self.first_half_added_time,
                "second_half": self.second_half_added_time,
                "extra_time_first_half": self.extra_time_first_added_time,
                "extra_time_second_half": self.extra_time_second_added_time,
            },
            "referee_strictness": round(self.referee_strictness, 5),
            "timeline": self.timeline,
        }


class CompleteFinalSimulator:
    """Simulate a knockout final under explicit rules and structural uncertainty."""

    def __init__(
        self,
        home: TeamProfile,
        away: TeamProfile,
        targets: CalibrationTargets,
        config: FinalConfig | None = None,
    ) -> None:
        self.home_profile = home
        self.away_profile = away
        self.targets = targets
        self.config = config or FinalConfig()
        self.rng = np.random.default_rng(self.config.seed)
        self.timeline: list[dict[str, Any]] = []
        self._sequence = 0
        self.referee_strictness = _clip(
            float(
                self.rng.normal(
                    self.config.referee_strictness_mean,
                    self.config.referee_strictness_sd,
                )
            ),
            0.65,
            1.45,
        )

    def simulate(self, keep_timeline: bool = True) -> CompleteFinalResult:
        sampled_home = self.home_profile.sampled(self.rng)
        sampled_away = self.away_profile.sampled(self.rng)
        home_coordination = _clip(
            float(
                self.rng.normal(
                    self.config.home_coordination_mean,
                    self.config.coordination_sd,
                )
            ),
            0.82,
            1.12,
        )
        away_coordination = _clip(
            float(
                self.rng.normal(
                    self.config.away_coordination_mean,
                    self.config.coordination_sd,
                )
            ),
            0.82,
            1.12,
        )
        home = TeamMatchState.from_profile(sampled_home, "home", home_coordination)
        away = TeamMatchState.from_profile(sampled_away, "away", away_coordination)

        first_added = max(1, int(self.rng.poisson(2.4)))
        second_added = max(3, int(self.rng.poisson(5.2)))
        extra_first_added = extra_second_added = 0

        first_half_end = 45.0 + first_added
        self._run_period(
            home,
            away,
            start_minute=0.0,
            nominal_minutes=45,
            added_minutes=first_added,
            period="first_half",
            keep_timeline=keep_timeline,
            extra_time=False,
        )
        self._event(
            first_half_end,
            "system",
            "half_time",
            "Intervalo",
            home,
            away,
            keep_timeline,
        )
        regulation_end = first_half_end + 45.0 + second_added
        self._run_period(
            home,
            away,
            start_minute=first_half_end,
            nominal_minutes=45,
            added_minutes=second_added,
            period="second_half",
            keep_timeline=keep_timeline,
            extra_time=False,
        )
        home.regulation_goals = home.goals
        away.regulation_goals = away.goals
        final_clock = regulation_end

        if home.goals != away.goals:
            decided_by = "regulation"
            home_penalties = away_penalties = None
        else:
            extra_first_added = max(1, int(self.rng.poisson(1.2)))
            extra_second_added = max(1, int(self.rng.poisson(1.4)))
            self._event(
                regulation_end,
                "system",
                "extra_time_start",
                "Início da prorrogação",
                home,
                away,
                keep_timeline,
            )
            extra_first_end = (
                regulation_end
                + self.config.rules.extra_time_period_minutes
                + extra_first_added
            )
            self._run_period(
                home,
                away,
                start_minute=regulation_end,
                nominal_minutes=self.config.rules.extra_time_period_minutes,
                added_minutes=extra_first_added,
                period="extra_time_first",
                keep_timeline=keep_timeline,
                extra_time=True,
            )
            final_clock = (
                extra_first_end
                + self.config.rules.extra_time_period_minutes
                + extra_second_added
            )
            self._run_period(
                home,
                away,
                start_minute=extra_first_end,
                nominal_minutes=self.config.rules.extra_time_period_minutes,
                added_minutes=extra_second_added,
                period="extra_time_second",
                keep_timeline=keep_timeline,
                extra_time=True,
            )
            home.extra_time_goals = home.goals - home.regulation_goals
            away.extra_time_goals = away.goals - away.regulation_goals
            if home.goals != away.goals:
                decided_by = "extra_time"
                home_penalties = away_penalties = None
            else:
                decided_by = "penalties"
                shootout_clock = final_clock + 1.0
                home_penalties, away_penalties = self._penalty_shootout(
                    home, away, keep_timeline, shootout_clock
                )
                final_clock = shootout_clock + 1.0

        if decided_by == "penalties":
            winner = home.name if int(home_penalties) > int(away_penalties) else away.name
        else:
            winner = home.name if home.goals > away.goals else away.name

        self._event(
            final_clock,
            "system",
            "full_time",
            f"Final: {winner} campeão",
            home,
            away,
            keep_timeline,
        )
        timeline = sorted(
            self.timeline,
            key=lambda event: (float(event["clock"]), int(event["sequence"])),
        )
        return CompleteFinalResult(
            home=home.name,
            away=away.name,
            seed=self.config.seed,
            regulation_home_goals=home.regulation_goals,
            regulation_away_goals=away.regulation_goals,
            extra_time_home_goals=home.extra_time_goals,
            extra_time_away_goals=away.extra_time_goals,
            home_penalties=home_penalties,
            away_penalties=away_penalties,
            winner=winner,
            decided_by=decided_by,
            home_stats=home.snapshot(),
            away_stats=away.snapshot(),
            first_half_added_time=first_added,
            second_half_added_time=second_added,
            extra_time_first_added_time=extra_first_added,
            extra_time_second_added_time=extra_second_added,
            referee_strictness=self.referee_strictness,
            timeline=timeline if keep_timeline else [],
        )

    def _run_period(
        self,
        home: TeamMatchState,
        away: TeamMatchState,
        start_minute: float,
        nominal_minutes: int,
        added_minutes: int,
        period: str,
        keep_timeline: bool,
        extra_time: bool,
    ) -> None:
        actual_minutes = nominal_minutes + added_minutes
        # Stoppage time stretches the same calibrated possession exposure instead
        # of creating additional possessions beyond the 90-minute target.
        expected = self.targets.model_possessions_per_match * nominal_minutes / 90.0
        possessions = max(1, int(self.rng.poisson(expected)))
        durations = self.rng.gamma(2.2, 1.0, size=possessions)
        durations *= actual_minutes / durations.sum()
        elapsed = 0.0
        for duration in durations:
            delta = float(duration)
            elapsed += delta
            clock = start_minute + elapsed
            self._apply_fatigue(home, delta, extra_time)
            self._apply_fatigue(away, delta, extra_time)
            self._update_tactics(home, away, clock)
            self._update_tactics(away, home, clock)
            self._maybe_tactical_substitution(home, clock, extra_time, keep_timeline, away)
            self._maybe_tactical_substitution(away, clock, extra_time, keep_timeline, home)

            home_probability = self._possession_probability(home, away)
            home_attacks = bool(self.rng.random() < home_probability)
            attack, defend = (home, away) if home_attacks else (away, home)
            attack.possessions += 1
            if not extra_time:
                attack.regulation_possessions += 1

            if self._simulate_foul(
                attack,
                defend,
                clock,
                period,
                extra_time,
                keep_timeline,
            ):
                continue
            self._simulate_possession(
                attack,
                defend,
                clock,
                period,
                keep_timeline,
            )

    def _apply_fatigue(
        self,
        team: TeamMatchState,
        delta_minutes: float,
        extra_time: bool,
    ) -> None:
        role_load = {
            "GK": 0.45,
            "CB1": 0.82,
            "CB2": 0.82,
            "FB1": 1.12,
            "FB2": 1.12,
            "DM": 1.02,
            "CM": 1.08,
            "AM": 1.05,
            "W1": 1.10,
            "W2": 1.10,
            "ST": 0.96,
        }
        extra_multiplier = 1.12 if extra_time else 1.0
        tempo_multiplier = 0.82 + 0.36 * team.tempo
        for role, state in team.players.items():
            if not state.active:
                continue
            decay = (
                self.config.fatigue_per_90
                * delta_minutes
                / 90.0
                * role_load.get(role, 1.0)
                * tempo_multiplier
                * extra_multiplier
            )
            state.stamina = _clip(state.stamina - decay, 0.45, 1.0)

    def _update_tactics(
        self,
        team: TeamMatchState,
        opponent: TeamMatchState,
        minute: float,
    ) -> None:
        if team.active_count < opponent.active_count:
            team.tactic = "numerical_disadvantage"
        elif team.goals < opponent.goals and minute >= 58:
            team.tactic = "chase"
        elif team.goals > opponent.goals and minute >= 74:
            team.tactic = "protect"
        elif minute >= 105 and team.goals == opponent.goals:
            team.tactic = "extra_time_control"
        else:
            team.tactic = "balanced"

    def _tactical_modifiers(self, tactic: str) -> tuple[float, float, float]:
        # possession, attack, defence
        return {
            "balanced": (0.0, 0.0, 0.0),
            "chase": (0.015, 0.095, -0.045),
            "protect": (-0.018, -0.055, 0.085),
            "numerical_disadvantage": (-0.045, -0.075, -0.070),
            "extra_time_control": (0.025, -0.020, 0.020),
        }[tactic]

    def _possession_probability(
        self,
        home: TeamMatchState,
        away: TeamMatchState,
    ) -> float:
        roles = ("CB1", "CB2", "FB1", "FB2", "DM", "CM")

        def strength(team: TeamMatchState) -> float:
            possession_mod, _, _ = self._tactical_modifiers(team.tactic)
            return (
                0.40 * team.mean("build_up", roles)
                + 0.32 * team.mean("retention")
                + 0.16 * team.mean("duels")
                + 0.12 * team.tempo
                + possession_mod
            ) * team.coordination * team.numerical_factor

        edge = (strength(home) - strength(away)) * self.config.ability_scale
        return _clip(
            _sigmoid(2.0 * edge + self.config.home_advantage),
            0.27,
            0.73,
        )

    def _attack_strength(self, team: TeamMatchState) -> float:
        _, attack_mod, _ = self._tactical_modifiers(team.tactic)
        return (
            0.24 * team.mean("progression")
            + 0.24 * team.mean("creation")
            + 0.21 * team.mean("finishing", ("AM", "W1", "W2", "ST"))
            + 0.17 * team.mean("retention")
            + 0.14 * team.mean("duels")
            + attack_mod
        ) * team.coordination * team.numerical_factor

    def _defence_strength(self, team: TeamMatchState) -> float:
        roles = ("CB1", "CB2", "FB1", "FB2", "DM")
        goalkeeper = team.players["GK"].effective("goalkeeping") if team.players["GK"].active else 0.05
        _, _, defence_mod = self._tactical_modifiers(team.tactic)
        return (
            0.34 * team.mean("defending", roles)
            + 0.22 * team.mean("duels", roles)
            + 0.22 * goalkeeper
            + 0.12 * team.press
            + 0.10 * team.mean("retention")
            + defence_mod
        ) * team.coordination * team.numerical_factor

    def _simulate_possession(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        keep_timeline: bool,
    ) -> None:
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

        if zone == 3 and self.rng.random() < 0.00085:
            defender_role = defend.choose_role(
                self.rng, ("CB1", "CB2", "FB1", "FB2", "DM"), "defending", inverse=True
            )
            self._record_goal(
                attack,
                defend,
                clock,
                period,
                scorer=f"{defend.players[defender_role].profile.name} (contra)",
                xg=0.025,
                event_type="own_goal",
                keep_timeline=keep_timeline,
            )
            return

        if self.rng.random() >= _clip(shot_probability, 0.025, 0.60):
            turnover_probability = _clip(
                0.08 + 0.10 * defend.press - 0.06 * attack.mean("retention"),
                0.03,
                0.24,
            )
            if zone >= 2 and self.rng.random() < turnover_probability:
                role = attack.choose_role(
                    self.rng,
                    ("CM", "AM", "W1", "W2", "ST"),
                    "retention",
                    inverse=True,
                )
                self._event(
                    clock,
                    attack.side,
                    "turnover",
                    f"{attack.players[role].profile.name} perde sob pressão",
                    attack,
                    defend,
                    keep_timeline,
                    period=period,
                    actor=attack.players[role].profile.name,
                    zone=zone,
                )
            return
        self._shot(attack, defend, clock, period, zone, edge, keep_timeline)

    def _choose_shooter(self, team: TeamMatchState, zone: int) -> str:
        roles = team.active_roles(("ST", "W1", "W2", "AM", "CM", "DM"))
        if not roles:
            roles = team.active_roles(OUTFIELD_ROLES)
        if not roles:
            roles = team.active_roles(ROLE_ORDER)
        boosts = {
            "ST": 1.35 if zone == 3 else 1.05,
            "W1": 1.05,
            "W2": 1.05,
            "AM": 1.0,
            "CM": 0.55,
            "DM": 0.25,
        }
        weights = np.array(
            [
                (
                    0.15
                    + 1.70 * team.players[role].effective("finishing")
                    + 0.45 * team.players[role].effective("creation")
                )
                * boosts.get(role, 0.35)
                for role in roles
            ],
            dtype=float,
        )
        weights /= weights.sum()
        return str(self.rng.choice(roles, p=weights))

    def _shot(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        zone: int,
        team_edge: float,
        keep_timeline: bool,
        penalty: bool = False,
    ) -> None:
        shooter_role = self._choose_shooter(attack, 3 if penalty else zone)
        shooter = attack.players[shooter_role]
        goalkeeper = defend.players["GK"]
        goalkeeper_skill = (
            goalkeeper.effective("goalkeeping") if goalkeeper.active else 0.08
        )
        goalkeeper_overall = (
            goalkeeper.effective("overall") if goalkeeper.active else 0.15
        )
        finishing_edge = (
            shooter.effective("finishing")
            - 0.50 * goalkeeper_skill
            - 0.25 * goalkeeper_overall
        )
        if penalty:
            goal_probability = _clip(
                0.76
                + 0.18 * (shooter.effective("finishing") - 0.5)
                - 0.16 * (goalkeeper_skill - 0.5),
                0.58,
                0.91,
            )
            on_target_probability = 0.89
        else:
            zone_adjustment = {1: -0.55, 2: -0.08, 3: 0.40}[zone]
            goal_probability = self.targets.goal_rate * exp(
                self.config.conversion_edge_scale * finishing_edge
                + zone_adjustment
                + 0.20 * team_edge
            )
            goal_probability = _clip(goal_probability, 0.012, 0.58)
            on_target_probability = _clip(
                self.targets.on_target_rate
                + 0.18 * (shooter.effective("finishing") - 0.5)
                - (0.06 if zone == 1 else 0.0),
                0.18,
                0.80,
            )
        on_target = bool(self.rng.random() < on_target_probability)
        goal_given_on_target = _clip(
            goal_probability / max(on_target_probability, 1e-9),
            0.03,
            0.86,
        )
        goal = bool(on_target and self.rng.random() < goal_given_on_target)

        attack.shots += 1
        attack.xg += float(goal_probability)
        regulation_period = period in {"first_half", "second_half", "regulation"}
        if regulation_period:
            attack.regulation_shots += 1
            attack.regulation_xg += float(goal_probability)
        if on_target:
            attack.shots_on_target += 1
            if regulation_period:
                attack.regulation_shots_on_target += 1

        event_type = "penalty" if penalty else "shot"
        headline = f"Finalização de {shooter.profile.name}"
        if goal:
            review_probability = (
                self.config.var_penalty_review_probability
                if penalty
                else self.config.var_review_goal_probability
            )
            overturn_probability = (
                self.config.var_penalty_overturn_probability
                if penalty
                else self.config.var_goal_overturn_probability
            )
            if self.rng.random() < review_probability:
                attack.var_reviews += 1
                self._event(
                    clock + 0.02,
                    "system",
                    "var_review",
                    "VAR revisa o lance",
                    attack,
                    defend,
                    keep_timeline,
                    period=period,
                    actor=shooter.profile.name,
                    zone=zone,
                )
                if self.rng.random() < overturn_probability:
                    self._event(
                        clock + 0.04,
                        "system",
                        "var_overturn",
                        "Gol anulado após revisão do VAR",
                        attack,
                        defend,
                        keep_timeline,
                        period=period,
                        actor=shooter.profile.name,
                        zone=zone,
                    )
                    return
            self._record_goal(
                attack,
                defend,
                clock,
                period,
                scorer=shooter.profile.name,
                xg=goal_probability,
                event_type="penalty_goal" if penalty else "goal",
                keep_timeline=keep_timeline,
            )
        elif on_target:
            headline = f"{goalkeeper.profile.name} defende finalização de {shooter.profile.name}"
            self._event(
                clock,
                attack.side,
                "shot_on_target",
                headline,
                attack,
                defend,
                keep_timeline,
                period=period,
                actor=shooter.profile.name,
                zone=zone,
                xg=goal_probability,
            )
        elif goal_probability >= 0.13:
            self._event(
                clock,
                attack.side,
                "shot_off_target",
                f"Grande chance de {shooter.profile.name} para fora",
                attack,
                defend,
                keep_timeline,
                period=period,
                actor=shooter.profile.name,
                zone=zone,
                xg=goal_probability,
            )
        elif penalty:
            self._event(
                clock,
                attack.side,
                event_type,
                f"{shooter.profile.name} desperdiça o pênalti",
                attack,
                defend,
                keep_timeline,
                period=period,
                actor=shooter.profile.name,
                zone=zone,
                xg=goal_probability,
            )

    def _record_goal(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        scorer: str,
        xg: float,
        event_type: str,
        keep_timeline: bool,
    ) -> None:
        attack.goals += 1
        self._event(
            clock,
            attack.side,
            event_type,
            f"GOL de {scorer}",
            attack,
            defend,
            keep_timeline,
            period=period,
            actor=scorer,
            zone=3,
            xg=xg,
        )

    def _simulate_foul(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        extra_time: bool,
        keep_timeline: bool,
    ) -> bool:
        expected_defensive_possessions = max(
            self.targets.model_possessions_per_match / 2.0,
            1.0,
        )
        foul_probability = _clip(
            self.config.fouls_per_team_90
            / expected_defensive_possessions
            * self.referee_strictness,
            0.04,
            0.34,
        )
        if self.rng.random() >= foul_probability:
            return False

        zone_draw = self.rng.random()
        zone = 3 if zone_draw > 0.78 else 2 if zone_draw > 0.36 else 1
        defender_role = defend.choose_role(
            self.rng,
            ("CB1", "CB2", "FB1", "FB2", "DM", "CM", "W1", "W2", "ST"),
            "defending",
            inverse=True,
        )
        defender = defend.players[defender_role]
        defend.fouls += 1
        self._event(
            clock,
            defend.side,
            "foul",
            f"Falta de {defender.profile.name}",
            attack,
            defend,
            keep_timeline,
            period=period,
            actor=defender.profile.name,
            zone=zone,
        )

        yellow_probability = _clip(
            self.config.yellows_per_team_90 / max(self.config.fouls_per_team_90, 1e-9)
            * self.referee_strictness
            * (1.18 if zone == 3 else 1.0),
            0.05,
            0.55,
        )
        direct_red_probability = _clip(
            self.config.direct_reds_per_team_90
            / max(self.config.fouls_per_team_90, 1e-9)
            * self.referee_strictness
            * (1.35 if zone == 3 else 1.0),
            0.0005,
            0.035,
        )
        if self.rng.random() < direct_red_probability:
            defender.sent_off = True
            defend.reds += 1
            self._event(
                clock + 0.01,
                defend.side,
                "red_card",
                f"Cartão vermelho para {defender.profile.name}",
                attack,
                defend,
                keep_timeline,
                period=period,
                actor=defender.profile.name,
                zone=zone,
            )
        elif self.rng.random() < yellow_probability:
            defender.yellow_cards += 1
            defend.yellows += 1
            if defender.yellow_cards >= 2:
                defend.second_yellows += 1
                defender.sent_off = True
                defend.reds += 1
                self._event(
                    clock + 0.01,
                    defend.side,
                    "second_yellow_red",
                    f"Segundo amarelo e expulsão de {defender.profile.name}",
                    attack,
                    defend,
                    keep_timeline,
                    period=period,
                    actor=defender.profile.name,
                    zone=zone,
                )
            else:
                self._event(
                    clock + 0.01,
                    defend.side,
                    "yellow_card",
                    f"Cartão amarelo para {defender.profile.name}",
                    attack,
                    defend,
                    keep_timeline,
                    period=period,
                    actor=defender.profile.name,
                    zone=zone,
                )

        injury_probability = _clip(
            self.config.injuries_per_team_90
            / max(self.config.fouls_per_team_90, 1e-9)
            * (1.18 if extra_time else 1.0),
            0.001,
            0.06,
        )
        if self.rng.random() < injury_probability:
            victim_role = attack.choose_role(self.rng, OUTFIELD_ROLES, "duels", inverse=True)
            self._injure_player(
                attack,
                victim_role,
                clock + 0.015,
                extra_time,
                keep_timeline,
                defend,
                period,
            )

        if zone == 3 and self.rng.random() < self.config.penalty_foul_share_in_zone_three:
            attack.penalties_awarded += 1
            self._event(
                clock + 0.02,
                attack.side,
                "penalty_awarded",
                f"Pênalti para {attack.name}",
                attack,
                defend,
                keep_timeline,
                period=period,
                zone=3,
            )
            if self.rng.random() < self.config.var_penalty_review_probability:
                attack.var_reviews += 1
                self._event(
                    clock + 0.025,
                    "system",
                    "var_review",
                    "VAR revisa a marcação do pênalti",
                    attack,
                    defend,
                    keep_timeline,
                    period=period,
                    zone=3,
                )
                if self.rng.random() < self.config.var_penalty_overturn_probability:
                    self._event(
                        clock + 0.035,
                        "system",
                        "var_overturn",
                        "Pênalti cancelado após revisão",
                        attack,
                        defend,
                        keep_timeline,
                        period=period,
                        zone=3,
                    )
                    return True
            edge = self._attack_strength(attack) - self._defence_strength(defend)
            self._shot(
                attack,
                defend,
                clock + 0.04,
                period,
                3,
                edge,
                keep_timeline,
                penalty=True,
            )
            return True
        elif zone == 3 and self.rng.random() < 0.055:
            edge = self._attack_strength(attack) - self._defence_strength(defend)
            self._shot(
                attack,
                defend,
                clock + 0.03,
                period,
                2,
                edge - 0.15,
                keep_timeline,
            )
            return True
        # A normal free kick resumes the same attacking state. Treating every
        # foul as a terminal possession would mechanically depress the calibrated
        # shot distribution by roughly the foul rate.
        return False

    def _injure_player(
        self,
        team: TeamMatchState,
        role: str,
        clock: float,
        extra_time: bool,
        keep_timeline: bool,
        opponent: TeamMatchState,
        period: str,
    ) -> None:
        state = team.players[role]
        if not state.active:
            return
        team.injuries += 1
        state.injured = True
        severe = bool(self.rng.random() < self.config.severe_injury_share)
        state.severe_injury = severe
        self._event(
            clock,
            team.side,
            "injury",
            f"{state.profile.name} recebe atendimento médico",
            team,
            opponent,
            keep_timeline,
            period=period,
            actor=state.profile.name,
        )
        if severe and team.can_substitute(extra_time, self.config.rules):
            self._perform_substitution(
                team,
                role,
                clock + 0.02,
                extra_time,
                keep_timeline,
                opponent,
                period,
                injury=True,
            )
        elif severe:
            self._event(
                clock + 0.02,
                team.side,
                "injury_exit_no_sub",
                f"{state.profile.name} deixa o campo sem substituição disponível",
                team,
                opponent,
                keep_timeline,
                period=period,
                actor=state.profile.name,
            )

    # COMPLETE_FINAL_RULES_FIX_V1_1_BATCH_WINDOWS
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

    def _penalty_shootout(
        self,
        home: TeamMatchState,
        away: TeamMatchState,
        keep_timeline: bool,
        start_clock: float,
    ) -> tuple[int, int]:
        self._event(
            start_clock,
            "system",
            "penalty_shootout_start",
            "Início da disputa de pênaltis",
            home,
            away,
            keep_timeline,
            period="penalty_shootout",
        )
        home_score = away_score = 0
        home_taken = away_taken = 0
        initial = self.config.rules.initial_penalty_kicks

        for round_index in range(initial):
            scored = self._take_shootout_kick(home, away, round_index, keep_timeline, start_clock)
            home_taken += 1
            home_score += int(scored)
            if home_score > away_score + (initial - away_taken):
                return home_score, away_score
            scored = self._take_shootout_kick(away, home, round_index, keep_timeline, start_clock)
            away_taken += 1
            away_score += int(scored)
            if away_score > home_score + (initial - home_taken):
                return home_score, away_score

        if home_score != away_score:
            return home_score, away_score

        for sudden_round in range(self.config.rules.maximum_sudden_death_rounds):
            home_goal = self._take_shootout_kick(
                home, away, initial + sudden_round, keep_timeline, start_clock
            )
            away_goal = self._take_shootout_kick(
                away, home, initial + sudden_round, keep_timeline, start_clock
            )
            home_score += int(home_goal)
            away_score += int(away_goal)
            if home_goal != away_goal:
                return home_score, away_score

        # Practically unreachable fallback that preserves the no-draw rule.
        home_edge = self._shootout_team_strength(home) - self._shootout_team_strength(away)
        if self.rng.random() < _sigmoid(3.0 * home_edge):
            home_score += 1
        else:
            away_score += 1
        return home_score, away_score

    def _shootout_team_strength(self, team: TeamMatchState) -> float:
        shooters = team.active_roles(("ST", "W1", "W2", "AM", "CM", "DM", "FB1", "FB2", "CB1", "CB2"))
        if not shooters:
            return 0.0
        return float(
            np.mean(
                [
                    0.60 * team.players[role].effective("finishing")
                    + 0.25 * team.players[role].effective("overall")
                    + 0.15 * team.players[role].effective("retention")
                    for role in shooters
                ]
            )
        )

    def _take_shootout_kick(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        kick_index: int,
        keep_timeline: bool,
        start_clock: float,
    ) -> bool:
        roles = attack.active_roles(("ST", "W1", "W2", "AM", "CM", "DM", "FB1", "FB2", "CB1", "CB2", "GK"))
        roles = sorted(
            roles,
            key=lambda role: (
                0.60 * attack.players[role].effective("finishing")
                + 0.25 * attack.players[role].effective("overall")
                + 0.15 * attack.players[role].effective("retention")
            ),
            reverse=True,
        )
        role = roles[kick_index % len(roles)]
        shooter = attack.players[role]
        goalkeeper = defend.players["GK"]
        goalkeeper_skill = (
            goalkeeper.effective("goalkeeping") if goalkeeper.active else 0.08
        )
        probability = _clip(
            0.75
            + 0.18 * (shooter.effective("finishing") - 0.5)
            + 0.08 * (shooter.effective("overall") - 0.5)
            - 0.18 * (goalkeeper_skill - 0.5)
            - 0.05 * (1.0 - shooter.stamina),
            0.55,
            0.93,
        )
        scored = bool(self.rng.random() < probability)
        self._event(
            start_clock + kick_index * 0.01 + (0.001 if attack.side == "away" else 0.0),
            attack.side,
            "shootout_goal" if scored else "shootout_miss",
            (
                f"{shooter.profile.name} converte"
                if scored
                else f"{shooter.profile.name} desperdiça"
            ),
            attack,
            defend,
            keep_timeline,
            period="penalty_shootout",
            actor=shooter.profile.name,
            xg=probability,
        )
        return scored

    def _event(
        self,
        clock: float,
        side: str,
        event_type: str,
        headline: str,
        team: TeamMatchState,
        opponent: TeamMatchState,
        keep_timeline: bool,
        period: str | None = None,
        actor: str | None = None,
        zone: int | None = None,
        xg: float | None = None,
    ) -> None:
        if not keep_timeline:
            return
        self._sequence += 1
        if team.side == "home":
            home_score, away_score = team.goals, opponent.goals
        elif team.side == "away":
            home_score, away_score = opponent.goals, team.goals
        else:
            home_score = away_score = 0
        self.timeline.append(
            {
                "sequence": self._sequence,
                "clock": round(float(clock), 3),
                "minute": int(float(clock)) + 1,
                "period": period or "match",
                "side": side,
                "team": team.name if side in {"home", "away"} else None,
                "type": event_type,
                "actor": actor,
                "zone": zone,
                "xg": round(float(xg), 4) if xg is not None else None,
                "score": f"{home_score}-{away_score}",
                "headline": headline,
            }
        )


def clone_config(config: FinalConfig, **changes: Any) -> FinalConfig:
    """Typed convenience wrapper used by Monte Carlo runners."""
    return replace(config, **changes)
