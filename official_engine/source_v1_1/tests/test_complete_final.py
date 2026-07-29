from dataclasses import replace
from pathlib import Path
import json
import pytest
from simulator.engine import PlayerProfile, TeamProfile, ROLE_ORDER
from simulator.calibrated_core import CalibrationTargets
from simulator.complete_final import CompleteFinalSimulator, FinalConfig
from simulator.complete_final_monte_carlo import simulate_complete_finals
from simulator.validation import discover_repository_readiness


def team(name, edge=0.0, synthetic=False):
    players=[]
    for i,role in enumerate(ROLE_ORDER):
        base=.60+edge
        players.append(PlayerProfile(
            player_id=f'{name}-{role}', name=f'{name} {role}', role=role, minutes=900,
            overall=base, build_up=base+(0.02 if role in {'CB1','CB2','DM','CM'} else 0),
            progression=base, creation=base, finishing=base+(0.04 if role in {'ST','W1','W2'} else -0.03),
            defending=base+(0.05 if role in {'CB1','CB2','DM'} else -0.03), duels=base,
            retention=base, goalkeeping=.72+edge if role=='GK' else .20,
            uncertainty=.025, synthetic=synthetic,
        ))
    return TeamProfile(name,tuple(players),tempo=.55,press=.54,directness=.51)

TARGETS=CalibrationTargets(64,2.65,25.0,8.7,.075,.39,.26,.35,104.0)
HOME=team('Synthetic',0.01,True)
AWAY=team('Real',0.0,False)


def test_same_seed_is_bitwise_reproducible():
    config=FinalConfig(seed=12345)
    a=CompleteFinalSimulator(HOME,AWAY,TARGETS,config).simulate(True).as_dict()
    b=CompleteFinalSimulator(HOME,AWAY,TARGETS,config).simulate(True).as_dict()
    assert a==b


def test_final_always_has_a_champion_and_respects_rules():
    for seed in range(50):
        result=CompleteFinalSimulator(HOME,AWAY,TARGETS,FinalConfig(seed=seed)).simulate(True)
        assert result.winner in {HOME.name,AWAY.name}
        if result.decided_by=='penalties':
            assert result.home_penalties != result.away_penalties
        else:
            assert result.home_goals != result.away_goals
        for stats in (result.home_stats,result.away_stats):
            assert stats['substitutions'] <= 6
            assert stats['substitution_windows'] <= 3
            assert stats['extra_time_windows'] <= 1
            assert 0 <= stats['players_remaining'] <= 11
            assert stats['regulation_shots'] <= stats['shots']
            assert stats['regulation_shots_on_target'] <= stats['shots_on_target']
        clocks=[event['clock'] for event in result.timeline]
        assert clocks==sorted(clocks)


def test_monte_carlo_returns_no_draw_probability_and_regulation_metrics():
    summary=simulate_complete_finals(HOME,AWAY,TARGETS,simulations=300,seed=991,audit_sample_size=20)
    p=summary['home_champion_probability']['estimate']+summary['away_champion_probability']['estimate']
    assert p==pytest.approx(1.0)
    assert 0 <= summary['extra_time_probability']['estimate'] <= 1
    assert 0 <= summary['penalty_shootout_probability']['estimate'] <= 1
    assert summary['mean_regulation_shots'] > summary['mean_regulation_goals']
    assert len(summary['audit_sample'])==20
    assert summary['representative_match']['winner'] in {HOME.name,AWAY.name}


def test_missing_readiness_evidence_fails_closed(tmp_path: Path):
    (tmp_path/'PROTOCOLO_FINAL_COMPLETA.md').write_text('frozen',encoding='utf-8')
    readiness=discover_repository_readiness(tmp_path)
    assert readiness['preregistered_protocol_present'] is True
    assert readiness['selection_sufficiency'] is False
    assert readiness['external_holdout_passed'] is False
    assert readiness['position_review_passed'] is False
    assert readiness['final_team_comparison_allowed'] is False


def test_affirmative_readiness_requires_all_discovered_flags(tmp_path: Path):
    (tmp_path/'PROTOCOLO_FINAL_COMPLETA.md').write_text('frozen',encoding='utf-8')
    model=tmp_path/'data'/'model_readiness'; model.mkdir(parents=True)
    validation=tmp_path/'data'/'validation'; validation.mkdir(parents=True)
    review=tmp_path/'data'/'audits'/'position_ontology_v2'/'blind_review'; review.mkdir(parents=True)
    (model/'selection_sufficiency_status.json').write_text(json.dumps({
        'status':'evaluated','selection_sufficiency_gate_passed':True
    }),encoding='utf-8')
    (validation/'external_pre_tournament_holdout_summary.json').write_text(json.dumps({
        'status':'evaluated','external_pre_tournament_validation_passed':True
    }),encoding='utf-8')
    (review/'blind_review_evaluation.json').write_text(json.dumps({
        'status':'evaluated','review_gate_passed':True
    }),encoding='utf-8')
    (model/'scientific_validation_status.json').write_text(json.dumps({
        'status':'evaluated','final_team_comparison_allowed':True
    }),encoding='utf-8')
    readiness=discover_repository_readiness(tmp_path)
    assert readiness['selection_sufficiency'] is True
    assert readiness['external_holdout_passed'] is True
    assert readiness['position_review_passed'] is True
    assert readiness['final_team_comparison_allowed'] is True
