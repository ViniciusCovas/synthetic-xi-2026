"""Runtime do laboratório no navegador (e testável em CPython).

Recebe elencos pré-computados (JSON), monta os bundles e roda a final
completa em blocos — a UI chama ``run_chunk`` repetidamente para manter a
página responsiva e mostrar progresso.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from typing import Any

import numpy as np

from .calibrated_core import CalibrationTargets
from .engine import PlayerProfile, ROLE_ORDER, TeamProfile
from .lab_conditions import MatchConditions
from .official_complete_final import (
    OfficialCompleteFinalSimulator,
    OfficialFinalConfig,
    official_config_with_seed,
)
from .official_profiles import OfficialTeamBundle

DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)


def _profile(payload: dict[str, Any]) -> PlayerProfile:
    return PlayerProfile(
        player_id=str(payload["player_id"]),
        name=str(payload["name"]),
        role=str(payload["role"]),
        minutes=float(payload["minutes"]),
        overall=float(payload["overall"]),
        uncertainty=float(payload["uncertainty"]),
        synthetic=bool(payload.get("synthetic", False)),
        **{dim: float(payload[dim]) for dim in DIMENSIONS},
    )


def bundle_from_payload(payload: dict[str, Any], name: str) -> OfficialTeamBundle:
    order = {role: index for index, role in enumerate(ROLE_ORDER)}
    starters = sorted(
        (_profile(item) for item in payload["starters"]),
        key=lambda profile: order[profile.role],
    )
    return OfficialTeamBundle(
        team=TeamProfile(name=name, players=tuple(starters)),
        bench_by_role={
            role: tuple(_profile(item) for item in reserves)
            for role, reserves in payload["bench_by_role"].items()
        },
        registered_ids=tuple(payload["registered_ids"]),
        starter_ids=tuple(payload["starter_ids"]),
        penalty_order_ids=tuple(payload["penalty_order_ids"]),
        emergency_goalkeeper_ids=tuple(payload["emergency_goalkeeper_ids"]),
        roster_rows=tuple(payload["roster"]),
        membership_rows=(),
    )


class LabSession:
    """Uma partida configurada; roda simulações em blocos."""

    def __init__(
        self,
        teams_payload: dict[str, Any],
        calibration_payload: dict[str, Any],
        home: str,
        away: str,
        simulations: int,
        seed: int,
        conditions: dict[str, Any] | None = None,
    ) -> None:
        if home == away:
            raise ValueError("Escolha duas seleções diferentes")
        self.home_name, self.away_name = home, away
        self.home = bundle_from_payload(teams_payload[home], home)
        self.away = bundle_from_payload(teams_payload[away], away)
        self.targets = CalibrationTargets.from_dict(calibration_payload)
        self.total = int(simulations)
        self.completed = 0
        self.wins: Counter[str] = Counter()
        self.decided_by: Counter[str] = Counter()
        self.scores: Counter[str] = Counter()
        self.goals_home: list[int] = []
        self.goals_away: list[int] = []
        self.conditions_report = None

        config = OfficialFinalConfig()
        if conditions:
            match_conditions = MatchConditions(
                label=str(conditions.get("label", "custom")),
                apparent_temperature_c=float(conditions["apparent_temperature_c"]),
                altitude_m=float(conditions["altitude_m"]),
                scheme=str(conditions.get("scheme", "primary")),
            )
            self.conditions_report = match_conditions.describe()
            config = replace(config, **match_conditions.config_overrides())
        self.base_config = config
        master = np.random.default_rng(int(seed))
        self.child_seeds = master.integers(1, 2**31 - 1, size=self.total)

    def run_chunk(self, chunk: int = 10) -> dict[str, Any]:
        end = min(self.completed + int(chunk), self.total)
        while self.completed < end:
            child = int(self.child_seeds[self.completed])
            simulator = OfficialCompleteFinalSimulator(
                self.home,
                self.away,
                self.targets,
                official_config_with_seed(self.base_config, child),
            )
            result = simulator.simulate(keep_timeline=False)
            self.wins[result.winner] += 1
            self.decided_by[result.decided_by] += 1
            self.scores[f"{result.home_goals}-{result.away_goals}"] += 1
            self.goals_home.append(result.home_goals)
            self.goals_away.append(result.away_goals)
            self.completed += 1
        return {"completed": self.completed, "total": self.total}

    def representative_final(self, max_attempts: int = 40) -> dict[str, Any]:
        """Re-simula seeds já usadas até achar uma final com o placar modal.

        Determinístico: mesmas seeds da corrida, ordem fixa. Devolve a
        timeline narrada completa dessa final (o motor narra em português),
        para o modo 'assistir' do app.
        """
        if not self.scores:
            raise RuntimeError("Rode as simulações antes de pedir a final")
        modal_score, _ = self.scores.most_common(1)[0]
        chosen = None
        for child in self.child_seeds[: min(self.completed, max_attempts)]:
            simulator = OfficialCompleteFinalSimulator(
                self.home, self.away, self.targets,
                official_config_with_seed(self.base_config, int(child)),
            )
            result = simulator.simulate(keep_timeline=True)
            if f"{result.home_goals}-{result.away_goals}" == modal_score:
                chosen = result
                break
            if chosen is None:
                chosen = result  # fallback: primeira final re-simulada
        events = [
            {
                "minute": int(event.get("minute", 0)),
                "period": str(event.get("period", "")),
                "side": str(event.get("side", "")),
                "actor": str(event.get("actor", "") or ""),
                "headline": str(event.get("headline", "")),
                "score": str(event.get("score", "")),
                "xg": float(event["xg"]) if event.get("xg") not in (None, "") else None,
            }
            for event in chosen.timeline
        ]
        return {
            "home": self.home_name,
            "away": self.away_name,
            "seed": int(chosen.seed) if chosen.seed is not None else None,
            "final_score": f"{chosen.home_goals}-{chosen.away_goals}",
            "regulation_score": f"{chosen.regulation_home_goals}-{chosen.regulation_away_goals}",
            "decided_by": chosen.decided_by,
            "winner": chosen.winner,
            "penalties": (
                [chosen.home_penalties, chosen.away_penalties]
                if chosen.home_penalties is not None else None
            ),
            "events": events,
        }

    def summary(self) -> dict[str, Any]:
        n = max(self.completed, 1)
        return {
            "status": "lab_app_simulation_completed",
            "engine": "official complete-final engine",
            "home": self.home_name,
            "away": self.away_name,
            "simulations": self.completed,
            "win_probability": {
                self.home_name: self.wins.get(self.home_name, 0) / n,
                self.away_name: self.wins.get(self.away_name, 0) / n,
            },
            "decided_by": {k: v / n for k, v in sorted(self.decided_by.items())},
            "mean_goals": {
                self.home_name: float(np.mean(self.goals_home)) if self.goals_home else 0.0,
                self.away_name: float(np.mean(self.goals_away)) if self.goals_away else 0.0,
            },
            "top_scorelines_before_penalties": [
                {"score": score, "probability": count / n}
                for score, count in self.scores.most_common(8)
            ],
            "conditions": self.conditions_report,
        }


_SESSION: LabSession | None = None
_DATA: dict[str, Any] = {}


def load_data(teams_json: str, calibration_json: str) -> str:
    _DATA["teams"] = json.loads(teams_json)
    _DATA["calibration"] = json.loads(calibration_json)
    return json.dumps({"teams": sorted(_DATA["teams"].keys())})


def start_session(
    home: str,
    away: str,
    simulations: int,
    seed: int,
    conditions_json: str = "",
) -> str:
    global _SESSION
    conditions = json.loads(conditions_json) if conditions_json else None
    _SESSION = LabSession(
        _DATA["teams"],
        _DATA["calibration"],
        home,
        away,
        simulations,
        seed,
        conditions,
    )
    rosters = {
        "home": list(_SESSION.home.roster_rows),
        "away": list(_SESSION.away.roster_rows),
    }
    return json.dumps({"ready": True, "rosters": rosters})


def run_chunk(chunk: int = 10) -> str:
    assert _SESSION is not None
    return json.dumps(_SESSION.run_chunk(chunk))


def summary() -> str:
    assert _SESSION is not None
    return json.dumps(_SESSION.summary())


def representative_final() -> str:
    assert _SESSION is not None
    return json.dumps(_SESSION.representative_final())
