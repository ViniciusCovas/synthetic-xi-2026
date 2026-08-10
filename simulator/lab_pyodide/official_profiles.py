"""Shim do pacote de navegador: apenas o contrato de bundle, sem pandas.

Réplica mínima de ``simulator.official_profiles`` com o que o motor de
finais importa (``OfficialTeamBundle`` e ``compatible_reserves``). Os bundles
chegam pré-computados em JSON — nenhuma leitura de arquivo aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .engine import PlayerProfile, TeamProfile


@dataclass(frozen=True)
class OfficialTeamBundle:
    team: TeamProfile
    bench_by_role: dict[str, tuple[PlayerProfile, ...]]
    registered_ids: tuple[str, ...]
    starter_ids: tuple[str, ...]
    penalty_order_ids: tuple[str, ...]
    emergency_goalkeeper_ids: tuple[str, ...]
    roster_rows: tuple[dict[str, Any], ...]
    membership_rows: tuple[dict[str, Any], ...]


def compatible_reserves(
    bundle: OfficialTeamBundle, role: str, used_ids: Iterable[str]
) -> list[PlayerProfile]:
    used = {str(value) for value in used_ids}
    return [
        profile
        for profile in bundle.bench_by_role.get(role, ())
        if profile.player_id not in used
    ]
