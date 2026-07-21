"""Transparent generator for statistically plausible AI footballers.

The generator creates convex combinations of complete real-player vectors inside one
validated role. It never maximizes each metric independently and never consults the
match simulator or the opposing Real XI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SyntheticAgent:
    role: str
    metrics: dict[str, float]
    utility: float
    donor_rows: tuple[int, ...]
    donor_weights: tuple[float, ...]
    mahalanobis_distance: float
    nearest_real_distance: float
    seed: int
    candidates_evaluated: int


def _validate_inputs(
    frame: pd.DataFrame,
    metrics: Sequence[str],
    weights: Mapping[str, float],
    minimum_pool: int,
) -> pd.DataFrame:
    if len(frame) < minimum_pool:
        raise ValueError(f"role pool has {len(frame)} players; at least {minimum_pool} are required")
    missing = [name for name in metrics if name not in frame.columns]
    if missing:
        raise ValueError(f"missing metrics: {missing}")
    if set(weights) != set(metrics):
        raise ValueError("weights must be supplied for every metric and no others")
    if not np.isfinite(list(weights.values())).all() or sum(abs(v) for v in weights.values()) <= 0:
        raise ValueError("weights must be finite and non-zero")
    clean = frame.loc[:, list(metrics)].apply(pd.to_numeric, errors="coerce").dropna()
    if len(clean) < minimum_pool:
        raise ValueError("too few complete player vectors after missing-data removal")
    if clean.duplicated().all():
        raise ValueError("role pool contains no multivariate variation")
    return clean


def _mahalanobis(values: np.ndarray, center: np.ndarray, inverse_cov: np.ndarray) -> np.ndarray:
    delta = values - center
    squared = np.einsum("ij,jk,ik->i", delta, inverse_cov, delta)
    return np.sqrt(np.maximum(squared, 0.0))


def _nearest_distance(candidates: np.ndarray, real: np.ndarray, scale: np.ndarray) -> np.ndarray:
    normalized_real = real / scale
    output = np.empty(len(candidates), dtype=float)
    for index, row in enumerate(candidates):
        delta = normalized_real - row / scale
        output[index] = float(np.sqrt(np.square(delta).sum(axis=1)).min())
    return output


def generate_role_agent(
    frame: pd.DataFrame,
    role: str,
    metrics: Sequence[str],
    weights: Mapping[str, float],
    *,
    seed: int,
    candidates: int = 50_000,
    minimum_pool: int = 20,
    donors_per_candidate: int = 3,
    lower_quantile: float = 0.005,
    upper_quantile: float = 0.995,
) -> SyntheticAgent:
    """Generate one role-conditioned agent inside the empirical convex hull."""
    if candidates < 1:
        raise ValueError("candidates must be positive")
    if donors_per_candidate < 2:
        raise ValueError("at least two donors are required")
    if not 0 <= lower_quantile < upper_quantile <= 1:
        raise ValueError("invalid quantile bounds")

    clean = _validate_inputs(frame, metrics, weights, minimum_pool)
    real = clean.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)

    lower = np.quantile(real, lower_quantile, axis=0)
    upper = np.quantile(real, upper_quantile, axis=0)
    center = np.mean(real, axis=0)
    covariance = np.cov(real, rowvar=False)
    inverse_cov = np.linalg.pinv(covariance, hermitian=True)
    real_mahalanobis = _mahalanobis(real, center, inverse_cov)
    mahalanobis_limit = float(np.quantile(real_mahalanobis, upper_quantile))

    q05 = np.quantile(real, 0.05, axis=0)
    q95 = np.quantile(real, 0.95, axis=0)
    utility_scale = np.maximum(q95 - q05, 1e-9)
    distance_scale = np.maximum(np.std(real, axis=0, ddof=1), 1e-9)
    weight_vector = np.array([float(weights[name]) for name in metrics], dtype=float)

    donor_indexes = rng.integers(0, len(real), size=(candidates, donors_per_candidate))
    raw_weights = rng.gamma(shape=0.8, scale=1.0, size=(candidates, donors_per_candidate))
    donor_weights = raw_weights / raw_weights.sum(axis=1, keepdims=True)
    generated = np.einsum("cd,cdm->cm", donor_weights, real[donor_indexes])

    within_bounds = ((generated >= lower) & (generated <= upper)).all(axis=1)
    distances = _mahalanobis(generated, center, inverse_cov)
    nearest = _nearest_distance(generated, real, distance_scale)
    non_copy = nearest > 1e-7
    multivariate_ok = distances <= mahalanobis_limit + 1e-12
    valid = within_bounds & non_copy & multivariate_ok
    if not valid.any():
        raise RuntimeError("no plausible synthetic candidate passed the preregistered constraints")

    standardized = (generated - q05) / utility_scale
    utility = standardized @ weight_vector
    utility[~valid] = -np.inf
    winner = int(np.argmax(utility))

    return SyntheticAgent(
        role=str(role),
        metrics={name: float(generated[winner, index]) for index, name in enumerate(metrics)},
        utility=float(utility[winner]),
        donor_rows=tuple(int(value) for value in donor_indexes[winner]),
        donor_weights=tuple(float(value) for value in donor_weights[winner]),
        mahalanobis_distance=float(distances[winner]),
        nearest_real_distance=float(nearest[winner]),
        seed=int(seed),
        candidates_evaluated=int(candidates),
    )


def build_ai_xi(
    frame: pd.DataFrame,
    role_column: str,
    role_weights: Mapping[str, Mapping[str, float]],
    *,
    seed: int = 20260720,
    candidates_per_role: int = 50_000,
    minimum_pool: int = 20,
) -> list[SyntheticAgent]:
    """Build exactly one synthetic agent for every preregistered role."""
    if role_column not in frame.columns:
        raise ValueError(f"missing role column: {role_column}")
    agents: list[SyntheticAgent] = []
    sequence = np.random.SeedSequence(seed).spawn(len(role_weights))
    for role, child_seed in zip(role_weights, sequence, strict=True):
        weights = role_weights[role]
        metrics = list(weights)
        role_frame = frame.loc[frame[role_column].astype(str).eq(str(role))].copy()
        agent = generate_role_agent(
            role_frame,
            role,
            metrics,
            weights,
            seed=int(child_seed.generate_state(1)[0]),
            candidates=candidates_per_role,
            minimum_pool=minimum_pool,
        )
        agents.append(agent)
    if len(agents) != len(role_weights):
        raise RuntimeError("AI XI is incomplete")
    return agents
