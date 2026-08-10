"""Laboratório Fase A: bundles de seleções nacionais reais da Copa 2026.

Constrói um ``OfficialTeamBundle`` (titulares + banco real por posição +
ordem de pênaltis) para qualquer seleção da Copa, a partir da tabela anual
v0.5, e o alimenta no MESMO motor de finais do experimento oficial (janelas
de substituição, prorrogação, pênaltis, cartões, banco real).

Regras declaradas:
- XI titular: melhor elegível da seleção por papel nas 11 posições; se um
  papel não tem ninguém, o melhor de um papel vizinho entra com a penalização
  fora-de-posição do protocolo oficial (×0.90 habilidade, +0.03 incerteza).
- Banco: todos os demais jogadores extraídos da seleção; para cada posição,
  reservas exatas primeiro (por qualidade), depois vizinhas penalizadas.
- Piso de minutos anuais do laboratório: 450 (declarado; a seleção v0.5
  principal usa 900) — necessário para cobrir elencos nacionais completos.
- Pênaltis: ordem por atributo de finalização entre os registrados.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .engine import PlayerProfile, ROLE_ORDER, TeamProfile
from .official_profiles import OfficialTeamBundle
from .official_frozen_runtime import _penalize_out_of_role

ELEVEN_ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
SLOT_TO_ENGINE_ROLE = {
    "GK": "GK", "RCB": "CB1", "LCB": "CB2", "RB": "FB1", "LB": "FB2",
    "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W1", "LW": "W2", "ST": "ST",
}
DIMENSIONS = (
    "build_up", "progression", "creation", "finishing",
    "defending", "duels", "retention", "goalkeeping",
)

# Vizinhanças declaradas para cobrir papéis sem titular natural.
ROLE_FALLBACKS = {
    "GK": [],
    "RB": ["LB", "RCB"],
    "LB": ["RB", "LCB"],
    "RCB": ["LCB", "DM", "RB"],
    "LCB": ["RCB", "DM", "LB"],
    "DM": ["CM", "RCB"],
    "CM": ["DM", "AM"],
    "AM": ["CM", "RW", "LW"],
    "RW": ["LW", "AM", "ST"],
    "LW": ["RW", "AM", "ST"],
    "ST": ["RW", "LW", "AM"],
}
LAB_MINIMUM_MINUTES = 450.0

# Degraus finais de improvisação (sempre penalizados e declarados): mesma
# linha primeiro, depois qualquer jogador de linha. GK nunca improvisa.
ROLE_LINES = {
    "RB": ["LB", "RCB", "LCB", "DM", "CM"],
    "LB": ["RB", "LCB", "RCB", "DM", "CM"],
    "RCB": ["LCB", "RB", "LB", "DM"],
    "LCB": ["RCB", "LB", "RB", "DM"],
    "DM": ["CM", "RCB", "LCB", "AM"],
    "CM": ["DM", "AM", "RW", "LW"],
    "AM": ["CM", "RW", "LW", "ST"],
    "RW": ["LW", "AM", "ST", "CM"],
    "LW": ["RW", "AM", "ST", "CM"],
    "ST": ["RW", "LW", "AM", "CM"],
}
OUTFIELD_ELEVEN = [role for role in ELEVEN_ROLES if role != "GK"]


def _fallback_chain(role: str) -> list[str]:
    chain = list(ROLE_FALLBACKS[role])
    for step in ROLE_LINES.get(role, []):
        if step not in chain:
            chain.append(step)
    if role != "GK":
        for step in OUTFIELD_ELEVEN:
            if step != role and step not in chain:
                chain.append(step)
    return chain


def _profile_from_row(row: pd.Series, engine_role: str) -> PlayerProfile:
    return PlayerProfile(
        player_id=str(int(row["player_id"])),
        name=str(row["player_name"]),
        role=engine_role,
        minutes=float(row["minutes_num"]),
        overall=float(row["overall"]),
        uncertainty=float(row["uncertainty"]),
        synthetic=False,
        **{d: float(row[d]) for d in DIMENSIONS},
    )


def build_national_bundle(
    team_name: str, table: pd.DataFrame
) -> tuple[OfficialTeamBundle, list[dict[str, object]]]:
    """Bundle da seleção + relatório de decisões (fallbacks, cobertura)."""
    nation = table[table["world_cup_team"] == team_name].copy()
    if nation.empty:
        available = sorted(table["world_cup_team"].dropna().unique())
        raise ValueError(
            f"Seleção {team_name!r} sem jogadores elegíveis; disponíveis: {available}"
        )
    nation = nation.sort_values("overall", ascending=False)
    decisions: list[dict[str, object]] = []

    used: set[int] = set()
    starters: dict[str, PlayerProfile] = {}
    starter_rows: dict[str, pd.Series] = {}
    for role in ELEVEN_ROLES:
        engine_role = SLOT_TO_ENGINE_ROLE[role]
        pool = nation[
            (nation["resolved_role"] == role) & (~nation["player_id"].isin(used))
        ]
        if not pool.empty:
            row = pool.iloc[0]
            profile = _profile_from_row(row, engine_role)
        else:
            row, profile = None, None
            for fallback in _fallback_chain(role):
                fallback_pool = nation[
                    (nation["resolved_role"] == fallback)
                    & (~nation["player_id"].isin(used))
                ]
                if not fallback_pool.empty:
                    row = fallback_pool.iloc[0]
                    profile = _penalize_out_of_role(
                        _profile_from_row(row, engine_role), engine_role
                    )
                    decisions.append(
                        {
                            "team": team_name,
                            "slot": role,
                            "player": str(row["player_name"]),
                            "decision": f"fora de posição ({fallback} -> {role}), penalizado",
                        }
                    )
                    break
            if profile is None:
                raise RuntimeError(
                    f"{team_name}: nenhum jogador disponível para {role} nem vizinhos"
                )
        used.add(int(row["player_id"]))
        starters[role] = profile
        starter_rows[role] = row

    order = {role: i for i, role in enumerate(ROLE_ORDER)}
    team = TeamProfile(
        name=team_name,
        players=tuple(
            sorted(starters.values(), key=lambda p: order[p.role])
        ),
    )

    bench = nation[~nation["player_id"].isin(used)]
    bench_by_role: dict[str, tuple[PlayerProfile, ...]] = {}
    for role in ELEVEN_ROLES:
        engine_role = SLOT_TO_ENGINE_ROLE[role]
        exact = bench[bench["resolved_role"] == role].sort_values(
            "overall", ascending=False
        )
        candidates = [
            _profile_from_row(row, engine_role) for _, row in exact.iterrows()
        ]
        for fallback in _fallback_chain(role):
            near = bench[bench["resolved_role"] == fallback].sort_values(
                "overall", ascending=False
            )
            candidates.extend(
                _penalize_out_of_role(_profile_from_row(row, engine_role), engine_role)
                for _, row in near.iterrows()
            )
        bench_by_role[engine_role] = tuple(candidates)

    registered = [starters[role] for role in ELEVEN_ROLES]
    registered_rows = list(starter_rows.values()) + [
        row for _, row in bench.iterrows()
    ]
    penalty_order = sorted(
        (
            _profile_from_row(row, "ST")
            for row in (starter_rows[role] for role in ELEVEN_ROLES)
        ),
        key=lambda p: p.finishing,
        reverse=True,
    )
    bench_gk_ids = tuple(
        str(int(row["player_id"]))
        for _, row in bench[bench["resolved_role"] == "GK"].iterrows()
    )

    bundle = OfficialTeamBundle(
        team=team,
        bench_by_role=bench_by_role,
        registered_ids=tuple(
            str(int(row["player_id"])) for row in registered_rows
        ),
        starter_ids=tuple(p.player_id for p in registered),
        penalty_order_ids=tuple(p.player_id for p in penalty_order),
        emergency_goalkeeper_ids=bench_gk_ids,
        roster_rows=tuple(
            {
                "player_id": int(row["player_id"]),
                "player_name": str(row["player_name"]),
                "resolved_role": str(row["resolved_role"]),
                "assigned_slot": (
                    ELEVEN_ROLES[index] if index < len(ELEVEN_ROLES) else "bench"
                ),
                "minutes_num": float(row["minutes_num"]),
            }
            for index, row in enumerate(registered_rows)
        ),
        membership_rows=(),
    )
    decisions.append(
        {
            "team": team_name,
            "slot": "coverage",
            "player": None,
            "decision": (
                f"{len(nation)} jogadores elegíveis (piso {LAB_MINIMUM_MINUTES:.0f}'), "
                f"{len(bench)} no banco"
            ),
        }
    )
    return bundle, decisions
