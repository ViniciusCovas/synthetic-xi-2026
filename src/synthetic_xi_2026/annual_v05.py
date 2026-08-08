"""Seleção anual v0.5 — melhores do ano, com validade posicional e de liga.

Camada nova, 100% offline sobre a caché versionada. Não modifica nenhum
artefato do experimento oficial v1 (que permanece congelado).

Correções e decisões metodológicas (todas declaradas):

1. **Papéis v2 com normalização centrada.** A resolução anual v1 usava
   ``coluna/largura`` do grid: numa linha com um único jogador (o "9" isolado
   do 4-2-3-1) isso dá 1,0 e o classifica como ponta direita — Kane, Mbappé,
   Haaland e Salah ficavam como "RW". Aqui a coordenada lateral é centrada
   (``(col - (w+1)/2) / max(w-1, 1)``): linha de largura 1 = central.
2. **Identidade única por player_id** (o provedor alterna grafias).
3. **Jogadores flexíveis não são descartados**: quem não atinge 60% de
   estabilidade entra no pool do papel modal com a flag ``flexible=True``.
4. **Âncoras públicas têm prioridade** sobre o grid quando declaram papel.
5. **Ajuste por força de liga**: cada estatística de volume por-90 é
   multiplicada pelo fator médio (ponderado por minutos) das ligas em que o
   jogador atuou na janela anual, segundo a tabela versionada
   ``data/reference/league_strength_tiers_2026.csv`` (fontes por linha).
   Cenários: ``primary``, ``none`` (sem ajuste) e ``steep`` (sensibilidade).
6. **Elegibilidade**: ≥900 minutos anuais (regra principal do protocolo).
"""

from __future__ import annotations

import glob
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

BATCH_DIR = Path("data/lake/batches")
TOTALS_PATH = Path("data/model_readiness/partial_annual_current_totals.csv")
PRECHECK_PATH = Path("data/audits/annual_player_precheck.csv")
ANCHORS_PATH = Path("data/reference/public_role_anchors_2026.csv")
LEAGUE_TIERS_PATH = Path("data/reference/league_strength_tiers_2026.csv")

ELEVEN_ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
ROLE_TO_GROUP = {
    "GK": "GK", "RB": "FB", "LB": "FB", "RCB": "CB", "LCB": "CB",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W", "ST": "ST",
}
DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)
LATERAL_THRESHOLD = 0.28
MINIMUM_ANNUAL_MINUTES = 900.0
STABILITY_THRESHOLD = 0.60

LEAGUE_SCENARIOS = {"primary": "factor_primary", "steep": "factor_steep", "none": None}
DEFAULT_FACTOR = {"primary": 0.85, "steep": 0.72, "none": 1.0}


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _read_batches(pattern: str, usecols: list[str] | None = None) -> pd.DataFrame:
    frames = [
        pd.read_csv(path, usecols=usecols)
        for path in sorted(glob.glob(str(BATCH_DIR / pattern)))
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def resolve_roles_v2() -> pd.DataFrame:
    """Papel por jogador nas 11 posições, com normalização lateral centrada."""
    lineups = _read_batches("batch_*_lineups.csv.gz")
    lineups = lineups[lineups["lineup_source"].astype(str).eq("startXI")]
    lineups = lineups.drop_duplicates(
        ["fixture_id", "team_id", "player_id"], keep="last"
    ).copy()
    grid = lineups["grid"].astype(str).str.split(":", n=1, expand=True)
    lineups["grid_row"] = pd.to_numeric(grid[0], errors="coerce")
    lineups["grid_col"] = pd.to_numeric(grid[1], errors="coerce")
    lineups = lineups.dropna(subset=["grid_row", "grid_col"])
    lineups["row_width"] = lineups.groupby(
        ["fixture_id", "team_id", "grid_row"]
    )["grid_col"].transform("max")
    # Coordenada lateral centrada em 0; linha de largura 1 é central (0.0).
    lineups["xc"] = (
        lineups["grid_col"] - (lineups["row_width"] + 1) / 2
    ) / np.maximum(lineups["row_width"] - 1, 1)
    lineups["max_row"] = lineups.groupby(
        ["fixture_id", "team_id"]
    )["grid_row"].transform("max")
    lineups["row_depth"] = (
        (lineups["grid_row"] - 2) / (lineups["max_row"] - 2).clip(lower=1)
    ).clip(0, 1)

    players = _read_batches(
        "batch_*_players.csv.gz", usecols=["player_id", "provider_position"]
    )
    modal_position = (
        players.groupby("player_id")["provider_position"]
        .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
        .rename("provider_position")
    )
    lineups["player_id"] = pd.to_numeric(lineups["player_id"], errors="coerce")
    lineups = lineups.dropna(subset=["player_id"])
    lineups["player_id"] = lineups["player_id"].astype(int)
    lineups = lineups.merge(modal_position, on="player_id", how="left")

    precheck = pd.read_csv(PRECHECK_PATH)
    precheck["player_id"] = pd.to_numeric(precheck["player_id"], errors="coerce")
    precheck = precheck.dropna(subset=["player_id"])
    precheck["player_id"] = precheck["player_id"].astype(int)
    lineups = lineups.merge(
        precheck[["player_id", "world_cup_team", "squad_position"]]
        .drop_duplicates("player_id"),
        on="player_id",
        how="left",
    )

    def observation_role(row: pd.Series) -> str:
        squad = str(row.squad_position or "")
        provider = str(row.provider_position or "")
        if squad == "Goalkeeper" or provider == "G":
            return "GK"
        side = "L" if row.xc < 0 else "R"
        lateral = abs(row.xc) >= LATERAL_THRESHOLD and row.row_width > 1
        if squad == "Defender" or provider == "D":
            if lateral:
                return f"{side}B"
            return "RCB" if row.xc >= 0 else "LCB"
        if squad == "Attacker" or provider == "F":
            return f"{side}W" if lateral else "ST"
        if row.row_depth <= 0.38:
            return "DM"
        if row.row_depth >= 0.70:
            return "AM"
        return "CM"

    lineups["role_observation"] = lineups.apply(observation_role, axis=1)

    rows: list[dict[str, object]] = []
    for player_id, group in lineups.groupby("player_id"):
        counts = group["role_observation"].value_counts()
        first = group.iloc[0]
        rows.append(
            {
                "player_id": int(player_id),
                "world_cup_team": first["world_cup_team"],
                "resolved_role": str(counts.index[0]),
                "role_stability": float(counts.iloc[0] / counts.sum()),
                "role_observations": int(counts.sum()),
                "role_distribution": " | ".join(
                    f"{k}:{v}" for k, v in counts.items()
                ),
                "role_source": "grid_centered_v2",
            }
        )
    resolved = pd.DataFrame(rows)

    anchors = pd.read_csv(ANCHORS_PATH)
    anchor_roles = {
        int(row.player_id): str(row.preferred_role)
        for row in anchors.itertuples(index=False)
        if str(row.preferred_role or "").strip() in ELEVEN_ROLES
    }
    override = resolved["player_id"].map(anchor_roles)
    resolved.loc[override.notna(), "resolved_role"] = override[override.notna()]
    resolved.loc[override.notna(), "role_source"] = "public_anchor"
    resolved["flexible"] = resolved["role_stability"] < STABILITY_THRESHOLD
    resolved.loc[override.notna(), "flexible"] = False
    return resolved


def league_factors(scenario: str = "primary") -> pd.Series:
    """Fator de liga por jogador: média dos fatores ponderada por minutos."""
    column = LEAGUE_SCENARIOS[scenario]
    exposure = _read_batches(
        "batch_*_players.csv.gz",
        usecols=["player_id", "league_id", "minutes", "in_current_window"],
    )
    exposure = exposure[exposure["in_current_window"] == True]  # noqa: E712
    exposure["minutes"] = pd.to_numeric(exposure["minutes"], errors="coerce").fillna(0)
    exposure = exposure[exposure["minutes"] > 0]
    if column is None:
        players = exposure["player_id"].unique()
        return pd.Series(1.0, index=pd.Index(players, name="player_id"))
    tiers = pd.read_csv(LEAGUE_TIERS_PATH)
    factor_by_league = dict(zip(tiers["league_id"], tiers[column]))
    exposure["factor"] = exposure["league_id"].map(factor_by_league).fillna(
        DEFAULT_FACTOR[scenario]
    )
    weighted = exposure.groupby("player_id").apply(
        lambda g: float(np.average(g["factor"], weights=g["minutes"])),
        include_groups=False,
    )
    weighted.name = "league_factor"
    return weighted


def _robust_unit(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    median = numeric.median()
    scale = max(float(numeric.quantile(0.75) - numeric.quantile(0.25)), 1e-9)
    z = (numeric - median) / scale
    return (1.0 / (1.0 + np.exp(-z.clip(-8, 8)))).fillna(0.5)


ROLE_WEIGHTS = {
    "GK": {"goalkeeping": 0.55, "build_up": 0.20, "retention": 0.15, "base": 0.10},
    "CB": {"defending": 0.33, "duels": 0.25, "build_up": 0.22, "retention": 0.20},
    "FB": {"defending": 0.22, "duels": 0.14, "build_up": 0.18, "progression": 0.28, "creation": 0.18},
    "DM": {"defending": 0.25, "duels": 0.18, "build_up": 0.25, "retention": 0.20, "progression": 0.12},
    "CM": {"build_up": 0.23, "retention": 0.20, "progression": 0.20, "creation": 0.16, "defending": 0.12, "duels": 0.09},
    "AM": {"creation": 0.32, "progression": 0.24, "finishing": 0.17, "retention": 0.15, "build_up": 0.12},
    "W": {"progression": 0.29, "creation": 0.23, "finishing": 0.22, "retention": 0.14, "duels": 0.12},
    "ST": {"finishing": 0.44, "creation": 0.12, "progression": 0.12, "duels": 0.18, "retention": 0.14},
}


def role_score(row: pd.Series, group: str) -> float:
    score = 0.0
    for key, weight in ROLE_WEIGHTS[group].items():
        score += weight * (0.5 if key == "base" else float(row[key]))
    return float(score)


def build_annual_table(scenario: str = "primary") -> pd.DataFrame:
    """Tabela anual v0.5: identidade única, papéis v2, dims ajustadas por liga."""
    totals = pd.read_csv(TOTALS_PATH)
    for column in totals.columns:
        if column not in {"player_name", "window"}:
            totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0.0)
    totals = totals.sort_values(
        ["player_id", "minutes_num"], ascending=[True, False]
    )
    aggregation = {
        column: "sum"
        for column in totals.columns
        if column not in {"player_id", "player_name", "window", "pass_completion_rate"}
    }
    aggregation["player_name"] = "first"
    totals = totals.groupby("player_id", as_index=False).agg(aggregation)
    totals = totals[totals["minutes_num"] >= MINIMUM_ANNUAL_MINUTES].copy()

    factors = league_factors(scenario)
    totals["league_factor"] = totals["player_id"].map(factors).fillna(
        DEFAULT_FACTOR[scenario]
    )

    minutes90 = totals["minutes_num"] / 90.0
    volume_columns = [
        "shots_total", "shots_on", "goals_total", "assists", "saves",
        "passes_total", "passes_completed", "passes_key", "tackles_total",
        "blocks", "interceptions", "duels_total", "duels_won",
        "dribbles_attempts", "dribbles_success", "fouls_drawn", "fouls_committed",
    ]
    for column in volume_columns:
        totals[f"{column}_p90"] = (
            totals[column].div(minutes90).fillna(0.0) * totals["league_factor"]
        )
    # Taxas limitadas não recebem fator (são qualidades, não volumes).
    totals["pass_completion"] = totals["passes_completed"].div(
        totals["passes_total"].replace(0, np.nan)
    ).fillna(0.0)
    totals["duel_success"] = totals["duels_won"].div(
        totals["duels_total"].replace(0, np.nan)
    ).fillna(0.0)
    totals["dribble_success_rate"] = totals["dribbles_success"].div(
        totals["dribbles_attempts"].replace(0, np.nan)
    ).fillna(0.0)
    totals["shot_accuracy"] = totals["shots_on"].div(
        totals["shots_total"].replace(0, np.nan)
    ).fillna(0.0)

    totals["build_up_raw"] = (
        0.45 * totals["passes_total_p90"]
        + 25 * totals["pass_completion"]
        + 2.0 * totals["passes_key_p90"]
    )
    totals["progression_raw"] = (
        2.5 * totals["dribbles_success_p90"]
        + 1.8 * totals["passes_key_p90"]
        + 0.5 * totals["fouls_drawn_p90"]
    )
    totals["creation_raw"] = (
        5.5 * totals["assists_p90"] + 2.5 * totals["passes_key_p90"]
    )
    totals["finishing_raw"] = (
        8.0 * totals["goals_total_p90"]
        + 1.4 * totals["shots_on_p90"]
        + 2.0 * totals["shot_accuracy"]
    )
    totals["defending_raw"] = (
        1.8 * totals["tackles_total_p90"]
        + 2.0 * totals["interceptions_p90"]
        + 1.1 * totals["blocks_p90"]
    )
    totals["duels_raw"] = (
        1.4 * totals["duels_won_p90"] + 3.0 * totals["duel_success"]
    )
    totals["retention_raw"] = (
        3.5 * totals["pass_completion"]
        + 1.8 * totals["dribble_success_rate"]
        + 0.4 * totals["duel_success"]
        - 0.08 * totals["fouls_committed_p90"]
    )
    totals["goalkeeping_raw"] = (
        1.5 * totals["saves_p90"] + 0.2 * totals["pass_completion"]
    )
    for dimension in DIMENSIONS:
        totals[dimension] = _robust_unit(totals[f"{dimension}_raw"])

    roles = resolve_roles_v2()
    table = totals.merge(roles, on="player_id", how="inner")
    table["position_group"] = table["resolved_role"].map(ROLE_TO_GROUP)
    table = table.dropna(subset=["position_group"])
    table["overall"] = table.apply(
        lambda row: role_score(row, str(row["position_group"])), axis=1
    )
    table["uncertainty"] = (
        0.22 / np.sqrt((table["minutes_num"] / 450.0).clip(lower=1.0))
    ).clip(0.035, 0.18)
    return table.sort_values("overall", ascending=False).reset_index(drop=True)


def select_real_xi(table: pd.DataFrame) -> pd.DataFrame:
    """Melhor titular por papel (11 posições), sem repetição de jogador."""
    used: set[int] = set()
    rows: list[dict[str, object]] = []
    for role in ELEVEN_ROLES:
        pool = table[
            (table["resolved_role"] == role) & (~table["player_id"].isin(used))
        ].sort_values("overall", ascending=False)
        if pool.empty:
            raise RuntimeError(f"Pool anual vazio para o papel {role}")
        player = pool.iloc[0]
        used.add(int(player["player_id"]))
        rows.append(
            {
                "slot": role,
                "player_id": int(player["player_id"]),
                "player_name": player["player_name"],
                "world_cup_team": player["world_cup_team"],
                "minutes": float(player["minutes_num"]),
                "overall": float(player["overall"]),
                "league_factor": float(player["league_factor"]),
                "role_stability": float(player["role_stability"]),
                "flexible": bool(player["flexible"]),
                "role_source": player["role_source"],
            }
        )
    return pd.DataFrame(rows)


BENCH_COVER_SLOTS = [
    "GK", "GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST",
]
FLEX_BENCH_SLOTS = 3


def select_squad26(table: pd.DataFrame, xi: pd.DataFrame) -> pd.DataFrame:
    """Plantel de 26: 11 titulares + cobertura por posição + 3 vagas livres.

    Regras de time real: 3 goleiros no plantel, um reserva direto por posição
    de linha, nenhum jogador repetido, e as 3 últimas vagas vão para os
    melhores restantes de qualquer posição (profundidade).
    """
    used = set(xi["player_id"].astype(int))
    rows = [
        {**row, "squad_role": "starter", "cover_slot": row["slot"]}
        for row in xi.to_dict("records")
    ]
    for cover in BENCH_COVER_SLOTS:
        pool = table[
            (table["resolved_role"] == cover) & (~table["player_id"].isin(used))
        ].sort_values("overall", ascending=False)
        if pool.empty:
            raise RuntimeError(f"Sem reserva disponível para {cover}")
        player = pool.iloc[0]
        used.add(int(player["player_id"]))
        rows.append(
            {
                "slot": None,
                "player_id": int(player["player_id"]),
                "player_name": player["player_name"],
                "world_cup_team": player["world_cup_team"],
                "minutes": float(player["minutes_num"]),
                "overall": float(player["overall"]),
                "league_factor": float(player["league_factor"]),
                "role_stability": float(player["role_stability"]),
                "flexible": bool(player["flexible"]),
                "role_source": player["role_source"],
                "squad_role": "bench_cover",
                "cover_slot": cover,
            }
        )
    flex_pool = table[~table["player_id"].isin(used)].sort_values(
        "overall", ascending=False
    )
    for _, player in flex_pool.head(FLEX_BENCH_SLOTS).iterrows():
        used.add(int(player["player_id"]))
        rows.append(
            {
                "slot": None,
                "player_id": int(player["player_id"]),
                "player_name": player["player_name"],
                "world_cup_team": player["world_cup_team"],
                "minutes": float(player["minutes_num"]),
                "overall": float(player["overall"]),
                "league_factor": float(player["league_factor"]),
                "role_stability": float(player["role_stability"]),
                "flexible": bool(player["flexible"]),
                "role_source": player["role_source"],
                "squad_role": "bench_flex",
                "cover_slot": player["resolved_role"],
            }
        )
    squad = pd.DataFrame(rows)
    assert len(squad) == 26 and squad["player_id"].nunique() == 26
    return squad


SYNTHETIC_TIERS = ["mean20", "top5", "p90", "max20"]


def build_synthetic_tiers(
    table: pd.DataFrame, top_n: int = 20, trim_fraction: float = 0.10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Avatares por arquétipo em 4 níveis: média, top-5, percentil 90, máximo.

    Todos os níveis derivam do MESMO pool Top-N por grupo posicional; a
    incerteza de amostragem por partido é sempre a média aparada das σ dos
    membros (pareada com os jogadores reais).
    """

    def trimmed(values: np.ndarray) -> float:
        clean = np.sort(values[np.isfinite(values)])
        cut = int(np.floor(clean.size * trim_fraction))
        if cut > 0 and clean.size - 2 * cut >= 2:
            clean = clean[cut:-cut]
        return float(clean.mean()) if clean.size else 0.0

    avatar_rows: list[dict[str, object]] = []
    member_rows: list[dict[str, object]] = []
    for group in ["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]:
        pool = table[table["position_group"] == group].sort_values(
            "overall", ascending=False
        )
        members = pool.head(top_n)
        for _, member in members.iterrows():
            member_rows.append(
                {
                    "position_group": group,
                    "player_id": int(member["player_id"]),
                    "player_name": member["player_name"],
                    "world_cup_team": member["world_cup_team"],
                    "overall": float(member["overall"]),
                }
            )
        sigma = trimmed(members["uncertainty"].to_numpy(dtype=float))
        top5 = members.head(5)
        for tier in SYNTHETIC_TIERS:
            if tier == "mean20":
                values = {d: trimmed(members[d].to_numpy(float)) for d in DIMENSIONS}
            elif tier == "top5":
                values = {d: float(top5[d].mean()) for d in DIMENSIONS}
            elif tier == "p90":
                values = {d: float(members[d].quantile(0.90)) for d in DIMENSIONS}
            else:  # max20
                values = {d: float(members[d].max()) for d in DIMENSIONS}
            avatar_rows.append(
                {
                    "avatar_id": f"SYN-{group}-{tier.upper()}",
                    "position_group": group,
                    "tier": tier,
                    "members_n": int(len(members)),
                    "uncertainty": sigma,
                    "overall": role_score(pd.Series(values), group),
                    **values,
                }
            )
    return pd.DataFrame(avatar_rows), pd.DataFrame(member_rows)


def external_validation(xi: pd.DataFrame, table: pd.DataFrame) -> dict:
    """Sobreposição do XI anual com as listas externas versionadas."""
    reference = pd.read_csv("data/reference/external_best_xi_2026.csv")
    reference["name_norm"] = reference["player_name"].map(normalize_name)
    table_names = {normalize_name(n) for n in table["player_name"]}
    xi_names = {normalize_name(n) for n in xi["player_name"]}
    results = {}
    for list_id, rows in reference.groupby("list_id"):
        listed = set(rows["name_norm"])
        overlap = sorted(listed & xi_names)
        coverage = sorted(listed & table_names)
        results[str(list_id)] = {
            "label": rows["list_label"].iloc[0],
            "listed_players": int(len(listed)),
            "in_our_xi": len(overlap),
            "overlap_names": overlap,
            "present_in_annual_pool": len(coverage),
            "note": (
                "present_in_annual_pool conta quantos da lista externa existem "
                "no nosso universo elegível (convocados à Copa com ≥900 min "
                "anuais); a sobreposição só é interpretável sobre esse subconjunto."
            ),
        }
    return results
