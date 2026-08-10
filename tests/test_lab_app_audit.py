"""Auditoria científica do aplicativo visual.

Exercita o pacote realmente publicado em ``web/public/lab/py`` — o mesmo
que o navegador baixa — e não as fontes do repositório, para que uma
exportação desatualizada seja detectada.

As verificações respondem a perguntas que a tela faz ao usuário:
as probabilidades fecham em 1? a final que ele assiste é a mesma que
entrou na estatística? o narrador inventa jogadores? as condições de
jogo fazem o que a página diz que fazem?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAB_PY = ROOT / "web" / "public" / "lab" / "py"
LAB_DATA = ROOT / "web" / "public" / "lab" / "data"
sys.path.insert(0, str(LAB_PY))

pytest.importorskip("numpy")

from labsim.lab_runtime import LabSession  # noqa: E402

ROLES = {"GK", "FB1", "CB1", "CB2", "FB2", "DM", "CM", "AM", "W1", "W2", "ST"}


@pytest.fixture(scope="module")
def payloads() -> tuple[dict, dict]:
    teams = json.loads((LAB_DATA / "teams.json").read_text(encoding="utf-8"))
    calibration = json.loads((LAB_DATA / "calibration.json").read_text(encoding="utf-8"))
    return teams, calibration


@pytest.fixture(scope="module")
def session(payloads):
    teams, calibration = payloads
    lab = LabSession(teams, calibration, "France", "Argentina", 120, 918711772)
    while lab.completed < lab.total:
        lab.run_chunk(40)
    return lab


def test_every_exported_squad_can_field_a_legal_eleven(payloads):
    teams, _ = payloads
    assert len(teams) >= 40
    for name, team in teams.items():
        starters = team["starters"]
        roles = [p["role"] for p in starters]
        ids = [p["player_id"] for p in starters]
        assert len(starters) == 11, name
        assert set(roles) == ROLES, name
        assert len(set(ids)) == 11, f"{name}: titular repetido"
        assert roles.count("GK") == 1, name
        registered = set(team["registered_ids"])
        assert set(ids) <= registered, f"{name}: titular fora dos inscritos"
        assert set(team["penalty_order_ids"]) <= registered, name
        bench = {p["player_id"] for rs in team["bench_by_role"].values() for p in rs}
        assert not (bench & set(ids)), f"{name}: reserva que também é titular"


def test_goalkeeper_is_never_improvised(payloads):
    """Um zagueiro no gol destruiria a validade da simulação."""
    teams, _ = payloads
    for name, team in teams.items():
        for decision in team["construction_decisions"]:
            if decision["slot"] == "GK":
                assert "fora de posição" not in decision["decision"], name


def test_probability_is_conserved(session):
    summary = session.summary()
    assert sum(session.wins.values()) == session.completed
    assert set(session.wins) <= {"France", "Argentina"}
    probabilities = summary["win_probability"]
    assert probabilities["France"] + probabilities["Argentina"] == pytest.approx(1.0)
    assert sum(summary["decided_by"].values()) == pytest.approx(1.0)
    assert sum(session.scores.values()) == session.completed


def test_narrating_does_not_change_the_match(session):
    """A UI conta com keep_timeline=False e reexibe com True.

    Se narrar consumisse sorteios diferentes, a final assistida não seria
    a mesma que entrou na estatística mostrada logo acima dela.
    """
    from labsim.official_complete_final import (
        OfficialCompleteFinalSimulator,
        official_config_with_seed,
    )

    for child in session.child_seeds[:8]:
        config = official_config_with_seed(session.base_config, int(child))
        silent = OfficialCompleteFinalSimulator(
            session.home, session.away, session.targets, config
        ).simulate(keep_timeline=False)
        narrated = OfficialCompleteFinalSimulator(
            session.home, session.away, session.targets, config
        ).simulate(keep_timeline=True)
        assert (silent.home_goals, silent.away_goals, silent.winner, silent.decided_by) == (
            narrated.home_goals, narrated.away_goals, narrated.winner, narrated.decided_by
        )


def test_narrated_final_is_internally_consistent(session, payloads):
    teams, _ = payloads
    report = session.representative_final()

    if report["is_modal"]:
        assert report["final_score"] == report["modal_score"]

    minutes = [event["minute"] for event in report["events"]]
    assert minutes == sorted(minutes), "lances fora de ordem cronológica"

    running = [e["score"] for e in report["events"] if e["score"]]
    assert running and running[-1] == report["final_score"]

    home_goals = sum(
        1 for e in report["events"]
        if e["headline"].startswith("GOL") and e["side"] == "home"
    )
    away_goals = sum(
        1 for e in report["events"]
        if e["headline"].startswith("GOL") and e["side"] == "away"
    )
    expected_home, expected_away = (int(x) for x in report["final_score"].split("-"))
    assert (home_goals, away_goals) == (expected_home, expected_away)

    squads = {
        side: {p["name"] for p in teams[name]["starters"]}
        | {p["name"] for rs in teams[name]["bench_by_role"].values() for p in rs}
        for side, name in (("home", "France"), ("away", "Argentina"))
    }
    everyone = squads["home"] | squads["away"]
    for event in report["events"]:
        if event["actor"]:
            assert event["actor"] in everyone, f"protagonista inventado: {event['actor']}"
        if event["headline"].startswith("GOL") and event["actor"]:
            assert event["actor"] in squads[event["side"]], (
                f"{event['actor']} marcou pelo lado errado"
            )


def test_conditions_reach_the_engine_and_off_is_a_true_no_op(payloads):
    """As condições precisam chegar ao motor — e 'off' precisa ser inerte.

    O efeito medido é sobre a *textura* da partida (12% a 23% dos jogos
    terminam diferente), não sobre quem vence: calor e altitude recaem
    igualmente sobre os dois times. A página declara isso; o teste fixa
    as duas pontas para que a declaração continue verdadeira.
    """
    from dataclasses import replace

    from labsim.lab_conditions import MatchConditions
    from labsim.official_complete_final import (
        OfficialCompleteFinalSimulator,
        OfficialFinalConfig,
        official_config_with_seed,
    )

    teams, calibration = payloads
    lab = LabSession(teams, calibration, "Mexico", "Norway", 60, 12345)

    neutral = OfficialFinalConfig()
    off = replace(neutral, **MatchConditions("x", 34.0, 2240.0, "off").config_overrides())
    assert off == neutral, "'sem efeito' não pode alterar a configuração"

    hot_conditions = MatchConditions("x", 34.0, 2240.0, "primary")
    overrides = hot_conditions.config_overrides()
    assert overrides["fatigue_per_90"] > neutral.fatigue_per_90
    assert overrides["shot_edge_scale"] > neutral.shot_edge_scale
    hot = replace(neutral, **overrides)

    changed = 0
    for child in lab.child_seeds:
        base_result = OfficialCompleteFinalSimulator(
            lab.home, lab.away, lab.targets, official_config_with_seed(neutral, int(child))
        ).simulate(keep_timeline=False)
        hot_result = OfficialCompleteFinalSimulator(
            lab.home, lab.away, lab.targets, official_config_with_seed(hot, int(child))
        ).simulate(keep_timeline=False)
        if (base_result.home_goals, base_result.away_goals, base_result.winner) != (
            hot_result.home_goals, hot_result.away_goals, hot_result.winner
        ):
            changed += 1

    share = changed / len(lab.child_seeds)
    assert share > 0.02, (
        "as condições não alteraram partida alguma — o canal está desligado "
        "em algum ponto entre a interface e o motor"
    )
    assert share < 0.60, (
        "efeito grande demais para um deslocamento simétrico de fadiga; "
        "reveja lab_conditions antes de anunciar o número na tela"
    )


def test_summary_matches_what_the_screen_draws(session):
    """A tela lê apenas summary(); os números têm de fechar com o que rodou."""
    summary = session.summary()
    assert summary["simulations"] == session.completed
    assert summary["mean_goals"]["France"] == pytest.approx(
        sum(session.goals_home) / session.completed
    )
    top = summary["top_scorelines_before_penalties"][0]
    assert top["score"] == session.scores.most_common(1)[0][0]
    assert all(0.0 <= s["probability"] <= 1.0 for s in summary["top_scorelines_before_penalties"])
