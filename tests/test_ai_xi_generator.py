from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from simulator.ai_xi_generator import build_ai_xi, generate_role_agent


def role_frame(rows: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(20260720)
    build_up = rng.normal(0.60, 0.08, rows)
    progression = 0.55 * build_up + rng.normal(0.25, 0.05, rows)
    creation = 0.50 * progression + rng.normal(0.30, 0.05, rows)
    return pd.DataFrame(
        {
            "role": ["CM"] * rows,
            "build_up": build_up,
            "progression": progression,
            "creation": creation,
        }
    )


def test_role_agent_is_deterministic_and_not_a_real_copy() -> None:
    frame = role_frame()
    weights = {"build_up": 0.4, "progression": 0.35, "creation": 0.25}
    first = generate_role_agent(
        frame,
        "CM",
        list(weights),
        weights,
        seed=77,
        candidates=2_000,
    )
    second = generate_role_agent(
        frame,
        "CM",
        list(weights),
        weights,
        seed=77,
        candidates=2_000,
    )
    assert first == second
    vector = np.array([first.metrics[name] for name in weights])
    real = frame[list(weights)].to_numpy()
    assert not np.isclose(real, vector).all(axis=1).any()
    assert first.nearest_real_distance > 0


def test_role_agent_stays_inside_observed_bounds() -> None:
    frame = role_frame()
    weights = {"build_up": 0.4, "progression": 0.35, "creation": 0.25}
    agent = generate_role_agent(
        frame,
        "CM",
        list(weights),
        weights,
        seed=11,
        candidates=2_000,
    )
    for metric, value in agent.metrics.items():
        assert frame[metric].min() <= value <= frame[metric].max()


def test_minimum_pool_is_hard_gate() -> None:
    frame = role_frame(rows=10)
    weights = {"build_up": 0.4, "progression": 0.35, "creation": 0.25}
    with pytest.raises(ValueError, match="at least 20"):
        generate_role_agent(frame, "CM", list(weights), weights, seed=1)


def test_build_ai_xi_requires_every_role_pool() -> None:
    frame = role_frame()
    weights = {
        "CM": {"build_up": 0.4, "progression": 0.35, "creation": 0.25}
    }
    agents = build_ai_xi(
        frame,
        "role",
        weights,
        seed=55,
        candidates_per_role=1_000,
    )
    assert [agent.role for agent in agents] == ["CM"]
