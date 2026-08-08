"""Laboratório Fase B: condições de jogo (calor, altitude, dia/noite).

Modificadores estruturais DECLARADOS do motor de finais, com fontes públicas
e esquema de sensibilidade — mesmo padrão da tabela de força de liga.

Canais (esquema ``primary``):

- **Calor**: a fadiga por 90′ aumenta 0,005 por °C de temperatura aparente
  acima de 24 °C. Base: efeitos documentados do calor no volume de corrida em
  futebol de elite (Mohr & Krustrup, Eur J Appl Physiol 2013; protocolo FIFA
  de pausas de hidratação a partir de WBGT 32 °C).
- **Altitude**: fadiga +0,02 por 1.000 m e leve aumento da conversão ofensiva
  (shot_edge_scale ×(1+0,02/km)) — partidas em altitude registram mais gols
  (McSharry, BMJ 2007, análise de 100 anos de jogos na América do Sul).
- **Dia/noite**: não é um canal próprio; muda a temperatura aparente usada
  (médias empíricas por cidade-sede calculadas da evidência meteorológica do
  próprio repositório, ``data/context/world_cup_2026_weather_by_match.csv``).

Esquemas: ``off`` (sem efeito), ``primary``, ``strong`` (dobro do primary).
Nenhum modificador altera as regras da final nem o RNG.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

VENUES_PATH = Path("data/reference/lab_venue_conditions_2026.csv")

HEAT_COMFORT_C = 24.0
HEAT_FATIGUE_PER_C = 0.005
ALTITUDE_FATIGUE_PER_KM = 0.02
ALTITUDE_SHOT_EDGE_PER_KM = 0.02
SCHEME_MULTIPLIER = {"off": 0.0, "primary": 1.0, "strong": 2.0}

BASE_FATIGUE_PER_90 = 0.19
BASE_SHOT_EDGE_SCALE = 0.95
MAX_FATIGUE_PER_90 = 0.40


@dataclass(frozen=True)
class MatchConditions:
    label: str
    apparent_temperature_c: float
    altitude_m: float
    scheme: str = "primary"

    def config_overrides(self) -> dict[str, float]:
        multiplier = SCHEME_MULTIPLIER[self.scheme]
        heat_excess = max(0.0, self.apparent_temperature_c - HEAT_COMFORT_C)
        altitude_km = max(0.0, self.altitude_m) / 1000.0
        fatigue = BASE_FATIGUE_PER_90 + multiplier * (
            heat_excess * HEAT_FATIGUE_PER_C + altitude_km * ALTITUDE_FATIGUE_PER_KM
        )
        shot_edge = BASE_SHOT_EDGE_SCALE * (
            1.0 + multiplier * altitude_km * ALTITUDE_SHOT_EDGE_PER_KM
        )
        overrides: dict[str, float] = {}
        if abs(fatigue - BASE_FATIGUE_PER_90) > 1e-12:
            overrides["fatigue_per_90"] = min(MAX_FATIGUE_PER_90, fatigue)
        if abs(shot_edge - BASE_SHOT_EDGE_SCALE) > 1e-12:
            overrides["shot_edge_scale"] = shot_edge
        return overrides

    def describe(self) -> dict[str, object]:
        return {
            "label": self.label,
            "apparent_temperature_c": self.apparent_temperature_c,
            "altitude_m": self.altitude_m,
            "scheme": self.scheme,
            "config_overrides": self.config_overrides(),
            "sources": [
                "Mohr & Krustrup 2013 (calor e volume de corrida)",
                "FIFA cooling breaks (WBGT >= 32C)",
                "McSharry BMJ 2007 (altitude e gols)",
                "data/context/world_cup_2026_weather_by_match.csv (temperaturas empíricas)",
            ],
        }


def load_venues(path: Path = VENUES_PATH) -> dict[str, dict[str, float | str]]:
    venues: dict[str, dict[str, float | str]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            venues[str(row["host_city"])] = {
                "host_city": row["host_city"],
                "stadium": row["stadium"],
                "altitude_m": float(row["altitude_m"]),
                "day_apparent_c": float(row["day_apparent_c"]),
                "night_apparent_c": float(row["night_apparent_c"]),
                "matches_observed": int(row["matches_observed"]),
                "altitude_source": row["altitude_source"],
            }
    return venues


def venue_conditions(
    host_city: str,
    kickoff: str = "night",
    scheme: str = "primary",
    venues: dict | None = None,
) -> MatchConditions:
    catalog = venues or load_venues()
    if host_city not in catalog:
        raise ValueError(
            f"Cidade-sede desconhecida: {host_city!r}; opções: {sorted(catalog)}"
        )
    if kickoff not in {"day", "night"}:
        raise ValueError("kickoff deve ser 'day' ou 'night'")
    venue = catalog[host_city]
    temperature = float(
        venue["day_apparent_c" if kickoff == "day" else "night_apparent_c"]
    )
    return MatchConditions(
        label=f"{host_city} ({venue['stadium']}), kickoff {kickoff}",
        apparent_temperature_c=temperature,
        altitude_m=float(venue["altitude_m"]),
        scheme=scheme,
    )
