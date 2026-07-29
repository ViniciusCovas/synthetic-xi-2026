"""Official v1 final simulator.

The historical ``complete_final`` engine remains untouched.  This module wraps it
with the corrections required by the 2026-07-29 protocol amendment:

* frozen 26-player benches rather than generated functional reserves;
* stricter discipline parameters and booked-player adaptation;
* explicit event semantics and actor-membership diagnostics;
* state-conditioned exposure and outcome counters for H7.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

import numpy as np

from .complete_final import (
    CompleteFinalResult,
    CompleteFinalSimulator,
    FinalConfig,
    PlayerMatchState,
    TeamMatchState,
)
from .engine import OUTFIELD_ROLES, ROLE_ORDER, PlayerProfile, TeamProfile, _clip
from .official_profiles import OfficialTeamBundle, compatible_reserves

OFFICIAL_ENGINE_VERSION = "complete_final_official_v1"
SHOT_EVENT_TYPES = {"shot", "shot_on_target", "shot_off_target", "penalty", "penalty_goal", "goal", "own_goal"}
GOAL_EVENT_TYPES = {"goal", "penalty_goal", "own_goal"}
DISCIPLINE_EVENT_TYPES = {"foul", "yellow_card", "red_card", "second_yellow_red"}
OFFENSIVE_EVENT_TYPES = SHOT_EVENT_TYPES | {
    "turnover",
    "penalty_awarded",
    "shootout_goal",
    "shootout_miss",
}
SELF_AFFECTING_EVENT_TYPES = {
    "yellow_card",
    "red_card",
    "second_yellow_red",
    "injury",
    "injury_exit_no_sub",
    "substitution",
}


@dataclass(frozen=True)
class OfficialFinalConfig(FinalConfig):
    fouls_per_team_90: float = 11.596154
    yellows_per_team_90: float = 1.43617
    direct_reds_per_team_90: float = 0.018
    booked_player_foul_multiplier: float = 0.35
    official_engine_version: str = OFFICIAL_ENGINE_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0.0 < self.booked_player_foul_multiplier <= 1.0:
            raise ValueError("booked_player_foul_multiplier must be in (0, 1]")
        if self.fouls_per_team_90 <= 0 or self.yellows_per_team_90 < 0:
            raise ValueError("Invalid official discipline rates")


class OfficialCompleteFinalSimulator(CompleteFinalSimulator):
    """Complete-final simulator bound to canonical rosters and official diagnostics."""

    def __init__(
        self,
        home: OfficialTeamBundle,
        away: OfficialTeamBundle,
        targets: Any,
        config: OfficialFinalConfig | None = None,
    ) -> None:
        self.home_bundle = home
        self.away_bundle = away
        self._bundle_by_side = {"home": home, "away": away}
        self._used_bench_ids: dict[str, set[str]] = {"home": set(), "away": set()}
        self._penalty_order_by_side = {
            "home": tuple(home.penalty_order_ids),
            "away": tuple(away.penalty_order_ids),
        }
        self._official_diagnostics: dict[str, Any] = {
            "engine_version": OFFICIAL_ENGINE_VERSION,
            "exposures": {},
            "outcomes": {},
            "events": {},
            "actor_membership_failures": [],
            "bench_entries": {"home": [], "away": []},
        }
        self._current_context: dict[str, Any] | None = None
        super().__init__(
            home.team,
            away.team,
            targets,
            config or OfficialFinalConfig(),
        )

    @property
    def official_config(self) -> OfficialFinalConfig:
        return self.config  # type: ignore[return-value]

    def simulate(self, keep_timeline: bool = True) -> CompleteFinalResult:
        result = super().simulate(keep_timeline=keep_timeline)
        setattr(result, "official_diagnostics", self._official_diagnostics)
        setattr(
            result,
            "official_runtime",
            {
                "engine_version": OFFICIAL_ENGINE_VERSION,
                "home_registered_ids": list(self.home_bundle.registered_ids),
                "away_registered_ids": list(self.away_bundle.registered_ids),
                "home_starter_ids": list(self.home_bundle.starter_ids),
                "away_starter_ids": list(self.away_bundle.starter_ids),
                "used_home_bench_ids": sorted(self._used_bench_ids["home"]),
                "used_away_bench_ids": sorted(self._used_bench_ids["away"]),
            },
        )
        return result

    @staticmethod
    def _score_state(team: TeamMatchState, opponent: TeamMatchState) -> str:
        return "leading" if team.goals > opponent.goals else "trailing" if team.goals < opponent.goals else "tied"

    @staticmethod
    def _numerical_state(team: TeamMatchState, opponent: TeamMatchState) -> str:
        return (
            "superior"
            if team.active_count > opponent.active_count
            else "inferior"
            if team.active_count < opponent.active_count
            else "equal"
        )

    @staticmethod
    def _phase(period: str) -> str:
        if period in {"first_half"}:
            return "first_half"
        if period in {"second_half", "regulation"}:
            return "second_half"
        if period.startswith("extra_time") or period == "extra_time":
            return "extra_time"
        return period

    @staticmethod
    def _increment(container: dict[str, Any], keys: Iterable[str], value: float = 1.0) -> None:
        cursor = container
        key_list = list(keys)
        for key in key_list[:-1]:
            cursor = cursor.setdefault(str(key), {})
        final = str(key_list[-1])
        cursor[final] = float(cursor.get(final, 0.0)) + float(value)

    def _record_exposure(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        period: str,
    ) -> None:
        context = {
            "team": attack.name,
            "opponent": defend.name,
            "score_state": self._score_state(attack, defend),
            "numerical_state": self._numerical_state(attack, defend),
            "phase": self._phase(period),
            "home_goals_before": attack.goals if attack.side == "home" else defend.goals,
            "away_goals_before": attack.goals if attack.side == "away" else defend.goals,
        }
        self._current_context = context
        self._increment(
            self._official_diagnostics["exposures"],
            (context["team"], context["score_state"], context["numerical_state"], context["phase"]),
        )

    def _record_outcome_delta(
        self,
        attack: TeamMatchState,
        before_shots: int,
        before_goals: int,
        before_xg: float,
    ) -> None:
        context = self._current_context
        if not context or context.get("team") != attack.name:
            return
        key = (
            context["team"],
            context["score_state"],
            context["numerical_state"],
            context["phase"],
        )
        shot_delta = attack.shots - before_shots
        goal_delta = attack.goals - before_goals
        xg_delta = attack.xg - before_xg
        if shot_delta:
            self._increment(self._official_diagnostics["outcomes"], (*key, "shots"), shot_delta)
        if goal_delta:
            self._increment(self._official_diagnostics["outcomes"], (*key, "goals"), goal_delta)
        if xg_delta:
            self._increment(self._official_diagnostics["outcomes"], (*key, "xg"), xg_delta)

    def _simulate_possession(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        keep_timeline: bool,
    ) -> None:
        before = (attack.shots, attack.goals, attack.xg)
        super()._simulate_possession(attack, defend, clock, period, keep_timeline)
        self._record_outcome_delta(attack, *before)

    def _choose_fouling_role(self, defend: TeamMatchState) -> str:
        roles = defend.active_roles(("CB1", "CB2", "FB1", "FB2", "DM", "CM", "W1", "W2", "ST"))
        if not roles:
            roles = defend.active_roles(OUTFIELD_ROLES)
        weights = []
        for role in roles:
            state = defend.players[role]
            inverse_defending = 0.12 + (1.0 - state.effective("defending"))
            adaptation = (
                self.official_config.booked_player_foul_multiplier
                if state.yellow_cards > 0
                else 1.0
            )
            weights.append(max(1e-9, inverse_defending * adaptation))
        probabilities = np.asarray(weights, dtype=float)
        probabilities /= probabilities.sum()
        return str(self.rng.choice(roles, p=probabilities))

    def _simulate_foul(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        clock: float,
        period: str,
        extra_time: bool,
        keep_timeline: bool,
    ) -> bool:
        self._record_exposure(attack, defend, period)
        before = (attack.shots, attack.goals, attack.xg)
        expected_defensive_possessions = max(self.targets.model_possessions_per_match / 2.0, 1.0)
        foul_probability = _clip(
            self.config.fouls_per_team_90 / expected_defensive_possessions * self.referee_strictness,
            0.04,
            0.34,
        )
        if self.rng.random() >= foul_probability:
            return False

        zone_draw = self.rng.random()
        zone = 3 if zone_draw > 0.78 else 2 if zone_draw > 0.36 else 1
        defender_role = self._choose_fouling_role(defend)
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
            0.025,
            0.45,
        )
        direct_red_probability = _clip(
            self.config.direct_reds_per_team_90 / max(self.config.fouls_per_team_90, 1e-9)
            * self.referee_strictness
            * (1.35 if zone == 3 else 1.0),
            0.0001,
            0.02,
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
            self.config.injuries_per_team_90 / max(self.config.fouls_per_team_90, 1e-9)
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
            self._shot(attack, defend, clock + 0.04, period, 3, edge, keep_timeline, penalty=True)
            self._record_outcome_delta(attack, *before)
            return True
        if zone == 3 and self.rng.random() < 0.055:
            edge = self._attack_strength(attack) - self._defence_strength(defend)
            self._shot(attack, defend, clock + 0.03, period, 2, edge - 0.15, keep_timeline)
            self._record_outcome_delta(attack, *before)
            return True
        return False

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
            if extra_time and team.extra_time_windows >= self.config.rules.extra_time_substitution_windows:
                return
            if not extra_time and team.substitution_windows >= self.config.rules.regulation_substitution_windows:
                return

        bundle = self._bundle_by_side[team.side]
        available = compatible_reserves(bundle, role, self._used_bench_ids[team.side])
        if not available:
            raise RuntimeError(
                f"Canonical bench exhausted or incompatible for {team.name} role {role}"
            )
        reserve_source = available[0]
        reserve = replace(reserve_source.sampled(self.rng), role=role)
        outgoing = team.players[role]
        team.players[role] = PlayerMatchState(
            profile=reserve,
            stamina=1.0,
            entry_minute=clock,
            substitute_generation=1,
        )
        team.substitutions += 1
        self._used_bench_ids[team.side].add(reserve.player_id)
        self._official_diagnostics["bench_entries"][team.side].append(
            {
                "player_id": reserve.player_id,
                "name": reserve.name,
                "role": role,
                "minute": round(float(clock), 3),
                "outgoing_player_id": outgoing.profile.player_id,
            }
        )
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
            f"Substituição {reason}: sai {outgoing.profile.name}, entra {reserve.name}",
            team,
            opponent,
            keep_timeline,
            period=period,
            actor=reserve.name,
        )

    def _eligible_penalty_order(self, team: TeamMatchState) -> list[str]:
        active_by_id = {
            state.profile.player_id: role
            for role, state in team.players.items()
            if state.active
        }
        frozen = [
            active_by_id[player_id]
            for player_id in self._penalty_order_by_side[team.side]
            if player_id in active_by_id
        ]
        remainder = [
            role
            for role in team.active_roles(ROLE_ORDER)
            if role not in frozen
        ]
        remainder.sort(
            key=lambda role: (
                0.60 * team.players[role].effective("finishing")
                + 0.25 * team.players[role].effective("overall")
                + 0.15 * team.players[role].effective("retention")
            ),
            reverse=True,
        )
        return frozen + remainder

    def _take_shootout_kick(
        self,
        attack: TeamMatchState,
        defend: TeamMatchState,
        kick_index: int,
        keep_timeline: bool,
        start_clock: float,
    ) -> bool:
        roles = self._eligible_penalty_order(attack)
        if not roles:
            raise RuntimeError(f"{attack.name} has no eligible penalty taker")
        role = roles[kick_index % len(roles)]
        shooter = attack.players[role]
        goalkeeper = defend.players["GK"]
        goalkeeper_skill = goalkeeper.effective("goalkeeping") if goalkeeper.active else 0.08
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
            f"{shooter.profile.name} converte" if scored else f"{shooter.profile.name} desperdiça",
            attack,
            defend,
            keep_timeline,
            period="penalty_shootout",
            actor=shooter.profile.name,
            xg=probability,
        )
        return scored

    @staticmethod
    def _state_for_side(
        side: str,
        team: TeamMatchState,
        opponent: TeamMatchState,
    ) -> TeamMatchState | None:
        if side == team.side:
            return team
        if side == opponent.side:
            return opponent
        return None

    @staticmethod
    def _actor_belongs(actor: str | None, state: TeamMatchState | None) -> bool | None:
        if actor is None or state is None:
            return None
        normalized = actor.replace(" (contra)", "")
        return any(
            normalized in {player.profile.name, player.profile.player_id}
            for player in state.players.values()
        )

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
        side_state = self._state_for_side(side, team, opponent)
        possession_team: str | None = None
        acting_state: TeamMatchState | None = side_state
        affected_team: str | None = None
        benefiting_team: str | None = None

        if event_type == "own_goal":
            acting_state = opponent
            possession_team = team.name
            affected_team = opponent.name
            benefiting_team = team.name
        elif event_type in DISCIPLINE_EVENT_TYPES:
            possession_team = team.name
            affected_team = team.name if event_type == "foul" else (acting_state.name if acting_state else None)
        elif event_type in OFFENSIVE_EVENT_TYPES:
            possession_team = acting_state.name if acting_state else team.name
            affected_team = opponent.name if acting_state is team else team.name
            if event_type in GOAL_EVENT_TYPES or event_type == "penalty_awarded":
                benefiting_team = possession_team
        elif event_type in SELF_AFFECTING_EVENT_TYPES:
            affected_team = acting_state.name if acting_state else team.name

        actor_team = acting_state.name if acting_state else None
        actor_valid = self._actor_belongs(actor, acting_state)
        if actor is not None and actor_valid is False:
            self._official_diagnostics["actor_membership_failures"].append(
                {
                    "clock": round(float(clock), 3),
                    "event_type": event_type,
                    "actor": actor,
                    "actor_team": actor_team,
                }
            )

        event_team = actor_team
        self._increment(
            self._official_diagnostics["events"],
            (event_team or "system", event_type),
        )

        if not keep_timeline:
            return
        self._sequence += 1
        home_state = team if team.side == "home" else opponent
        away_state = team if team.side == "away" else opponent
        context = self._current_context or {}
        self.timeline.append(
            {
                "sequence": self._sequence,
                "clock": round(float(clock), 3),
                "minute": int(float(clock)) + 1,
                "period": period or "match",
                "side": side,
                "team": event_team,
                "acting_team": event_team,
                "affected_team": affected_team,
                "possession_team": possession_team,
                "benefiting_team": benefiting_team,
                "actor": actor,
                "actor_team": actor_team,
                "actor_membership_valid": actor_valid,
                "zone": zone,
                "xg": round(float(xg), 4) if xg is not None else None,
                "home_score_before_context": context.get("home_goals_before"),
                "away_score_before_context": context.get("away_goals_before"),
                "score_state_before": context.get("score_state"),
                "numerical_state_before": context.get("numerical_state"),
                "score": f"{home_state.goals}-{away_state.goals}",
                "headline": headline,
            }
        )


def official_config_with_seed(config: OfficialFinalConfig, seed: int) -> OfficialFinalConfig:
    return replace(config, seed=int(seed))
