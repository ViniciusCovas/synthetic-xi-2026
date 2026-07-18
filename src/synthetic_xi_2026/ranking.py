"""Ranking intraposición, avatares robustos y construcción de los dos onces."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import POSITION_METRICS, POSITION_ORDER, XI_SLOTS


def _winsorized_z(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if len(numeric) >= 5:
        low, high = numeric.quantile([0.05, 0.95])
        numeric = numeric.clip(low, high)
    std = numeric.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (numeric - numeric.mean()) / std


def rank_players(
    features: pd.DataFrame,
    minimum_minutes: float = 180.0,
    reliability_prior_minutes: float = 180.0,
) -> pd.DataFrame:
    """Clasifica jugadores únicamente contra otros de su misma posición funcional."""
    parts: list[pd.DataFrame] = []
    for group in POSITION_ORDER:
        metrics = POSITION_METRICS[group]
        subset = features[
            (features["position_group"] == group)
            & (features["minutes"] >= minimum_minutes)
        ].copy()
        if subset.empty:
            continue
        reliability = subset["minutes"] / (
            subset["minutes"] + reliability_prior_minutes
        )
        subset["reliability"] = reliability
        z_cols: list[str] = []
        for metric, direction in metrics.items():
            if metric not in subset:
                subset[metric] = 0.0
            mean = subset[metric].mean()
            adjusted = mean + reliability * (subset[metric] - mean)
            adjusted_col = f"adjusted__{metric}"
            z_col = f"z__{metric}"
            subset[adjusted_col] = adjusted
            subset[z_col] = _winsorized_z(adjusted) * direction
            z_cols.append(z_col)
        subset["rank_score"] = subset[z_cols].mean(axis=1)
        subset["position_rank"] = (
            subset["rank_score"].rank(method="min", ascending=False).astype(int)
        )
        parts.append(
            subset.sort_values(["rank_score", "minutes"], ascending=[False, False])
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _trimmed_mean(values: np.ndarray, trim_fraction: float = 0.10) -> float:
    clean = np.sort(values[np.isfinite(values)])
    if clean.size == 0:
        return 0.0
    cut = int(np.floor(clean.size * trim_fraction))
    if cut > 0 and clean.size - 2 * cut >= 2:
        clean = clean[cut:-cut]
    return float(clean.mean())


def _bootstrap_trimmed_ci(
    values: np.ndarray,
    seed: int,
    trim_fraction: float = 0.10,
    n_resamples: int = 2000,
) -> tuple[float, float]:
    clean = values[np.isfinite(values)]
    if clean.size == 0:
        return 0.0, 0.0
    if clean.size == 1:
        return float(clean[0]), float(clean[0])
    rng = np.random.default_rng(seed)
    estimates = np.empty(n_resamples, dtype=float)
    for idx in range(n_resamples):
        sample = rng.choice(clean, size=clean.size, replace=True)
        estimates[idx] = _trimmed_mean(sample, trim_fraction)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def build_avatars(
    ranked: pd.DataFrame,
    requested_top_n: int = 20,
    seed: int = 20260718,
    trim_fraction: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Crea un centroide robusto de los Top-N elegibles de cada posición."""
    summaries: list[dict[str, Any]] = []
    metrics_long: list[dict[str, Any]] = []
    members: list[pd.DataFrame] = []
    for group in POSITION_ORDER:
        pool = ranked[ranked["position_group"] == group].sort_values(
            "rank_score", ascending=False
        )
        if pool.empty:
            continue
        selected = pool.head(requested_top_n).copy()
        actual_n = len(selected)
        avatar_id = f"SYN-{group}{requested_top_n}"
        selected["avatar_id"] = avatar_id
        members.append(selected)
        summaries.append(
            {
                "avatar_id": avatar_id,
                "position_group": group,
                "requested_top_n": requested_top_n,
                "actual_n": actual_n,
                "eligible_pool_n": len(pool),
                "sample_complete": actual_n >= requested_top_n,
                "mean_rank_score": float(selected["rank_score"].mean()),
                "median_minutes": float(selected["minutes"].median()),
                "interpretation_label": (
                    f"centroide robusto de los {actual_n} mejores {group} elegibles "
                    "en el corte acumulado de la Copa 2026"
                ),
            }
        )
        for offset, (metric, direction) in enumerate(POSITION_METRICS[group].items()):
            values = selected[metric].astype(float).to_numpy()
            robust_mean = _trimmed_mean(values, trim_fraction)
            low, high = _bootstrap_trimmed_ci(
                values,
                seed + offset + len(metrics_long) * 101,
                trim_fraction=trim_fraction,
            )
            pool_values = pool[metric].astype(float)
            percentile = float((pool_values <= robust_mean).mean() * 100.0)
            metrics_long.append(
                {
                    "avatar_id": avatar_id,
                    "position_group": group,
                    "metric": metric,
                    "mean": robust_mean,
                    "arithmetic_mean": float(values.mean()) if values.size else 0.0,
                    "median": float(np.median(values)) if values.size else 0.0,
                    "std": float(np.std(values, ddof=1)) if values.size > 1 else 0.0,
                    "ci95_low": low,
                    "ci95_high": high,
                    "position_percentile": percentile,
                    "direction": direction,
                    "actual_n": actual_n,
                }
            )
    return (
        pd.DataFrame(summaries),
        pd.DataFrame(metrics_long),
        pd.concat(members, ignore_index=True) if members else pd.DataFrame(),
    )


def build_real_benchmarks(ranked: pd.DataFrame) -> pd.DataFrame:
    """Selecciona el número 1 real de cada posición tras ajuste por minutos."""
    rows: list[dict[str, Any]] = []
    for group in POSITION_ORDER:
        pool = ranked[ranked["position_group"] == group].sort_values(
            ["position_rank", "minutes"]
        )
        if pool.empty:
            continue
        player = pool.iloc[0]
        row = player.to_dict()
        row.update(
            {
                "benchmark_id": f"REAL-{group}1",
                "benchmark_rule": "número 1 del índice posicional ajustado por confiabilidad",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_positional_comparisons(
    avatar_metrics: pd.DataFrame,
    real_benchmarks: pd.DataFrame,
) -> pd.DataFrame:
    """Compara cada atributo del avatar con el mejor jugador real de la posición."""
    rows: list[dict[str, Any]] = []
    for _, metric_row in avatar_metrics.iterrows():
        group = metric_row["position_group"]
        benchmark = real_benchmarks[
            real_benchmarks["position_group"] == group
        ]
        if benchmark.empty:
            continue
        player = benchmark.iloc[0]
        metric = metric_row["metric"]
        real_value = float(player.get(metric, 0.0) or 0.0)
        avatar_value = float(metric_row["mean"])
        direction = int(metric_row["direction"])
        adjusted_difference = (avatar_value - real_value) * direction
        rows.append(
            {
                "position_group": group,
                "avatar_id": metric_row["avatar_id"],
                "benchmark_id": player["benchmark_id"],
                "player_id": player["player_id"],
                "player_name": player["player_name"],
                "team_name": player["team_name"],
                "metric": metric,
                "direction": direction,
                "avatar_value": avatar_value,
                "real_value": real_value,
                "direction_adjusted_difference": adjusted_difference,
                "descriptive_leader": (
                    "avatar" if adjusted_difference > 0 else
                    "jugador_real" if adjusted_difference < 0 else "empate"
                ),
            }
        )
    return pd.DataFrame(rows)


def build_experimental_lineups(
    ranked: pd.DataFrame,
    avatars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construye Synthetic XI y Real Best XI con exactamente once plazas."""
    synthetic_rows: list[dict[str, Any]] = []
    real_rows: list[dict[str, Any]] = []
    for slot_spec in XI_SLOTS:
        slot = str(slot_spec["slot"])
        group = str(slot_spec["position_group"])
        ordinal = int(slot_spec["ordinal"])

        avatar = avatars[avatars["position_group"] == group]
        synthetic_rows.append(
            {
                "slot": slot,
                "position_group": group,
                "source_ordinal": ordinal,
                "entity_type": "avatar_sintético",
                "entity_id": avatar.iloc[0]["avatar_id"] if not avatar.empty else None,
                "entity_name": avatar.iloc[0]["avatar_id"] if not avatar.empty else None,
                "team_name": "Synthetic XI",
                "available": not avatar.empty,
            }
        )

        pool = ranked[ranked["position_group"] == group].sort_values(
            ["position_rank", "minutes"]
        )
        if len(pool) >= ordinal:
            player = pool.iloc[ordinal - 1]
            real_rows.append(
                {
                    "slot": slot,
                    "position_group": group,
                    "source_ordinal": ordinal,
                    "entity_type": "jugador_real",
                    "entity_id": int(player["player_id"]),
                    "entity_name": player["player_name"],
                    "team_name": player["team_name"],
                    "rank_score": float(player["rank_score"]),
                    "minutes": float(player["minutes"]),
                    "available": True,
                }
            )
        else:
            real_rows.append(
                {
                    "slot": slot,
                    "position_group": group,
                    "source_ordinal": ordinal,
                    "entity_type": "jugador_real",
                    "entity_id": None,
                    "entity_name": None,
                    "team_name": None,
                    "rank_score": None,
                    "minutes": None,
                    "available": False,
                }
            )
    return pd.DataFrame(synthetic_rows), pd.DataFrame(real_rows)
