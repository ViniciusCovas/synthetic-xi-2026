#!/usr/bin/env python3
"""Gera a tabela de condições por cidade-sede da Copa 2026.

Temperaturas aparentes dia/noite: médias empíricas por cidade calculadas da
evidência meteorológica versionada do repositório
(``data/context/world_cup_2026_weather_by_match.csv``; kickoff local < 18h =
dia). Altitudes: valores públicos por cidade (fonte por linha).
"""

from __future__ import annotations

import pandas as pd

ALTITUDES = {
    "Mexico City": (2240, "https://en.wikipedia.org/wiki/Mexico_City"),
    "Guadalajara": (1566, "https://en.wikipedia.org/wiki/Guadalajara"),
    "Monterrey": (540, "https://en.wikipedia.org/wiki/Monterrey"),
    "Atlanta": (320, "https://en.wikipedia.org/wiki/Atlanta"),
    "Kansas City": (270, "https://en.wikipedia.org/wiki/Kansas_City,_Missouri"),
    "Dallas": (184, "https://en.wikipedia.org/wiki/Arlington,_Texas"),
    "Houston": (15, "https://en.wikipedia.org/wiki/Houston"),
    "Miami": (2, "https://en.wikipedia.org/wiki/Miami_Gardens,_Florida"),
    "New York New Jersey": (3, "https://en.wikipedia.org/wiki/East_Rutherford,_New_Jersey"),
    "Philadelphia": (12, "https://en.wikipedia.org/wiki/Philadelphia"),
    "Boston": (89, "https://en.wikipedia.org/wiki/Foxborough,_Massachusetts"),
    "Seattle": (54, "https://en.wikipedia.org/wiki/Seattle"),
    "San Francisco Bay Area": (25, "https://en.wikipedia.org/wiki/Santa_Clara,_California"),
    "Los Angeles": (45, "https://en.wikipedia.org/wiki/Inglewood,_California"),
    "Toronto": (76, "https://en.wikipedia.org/wiki/Toronto"),
    "Vancouver": (2, "https://en.wikipedia.org/wiki/Vancouver"),
}


def main() -> None:
    weather = pd.read_csv("data/context/world_cup_2026_weather_by_match.csv")
    weather["kickoff_hour"] = pd.to_datetime(
        weather["kickoff_local"], format="ISO8601", utc=True
    ).dt.tz_localize(None).dt.hour
    # kickoff_local já vem no fuso local; extraímos a hora do texto.
    weather["kickoff_hour"] = weather["kickoff_local"].str.slice(11, 13).astype(int)
    weather["daypart"] = weather["kickoff_hour"].apply(
        lambda h: "day" if h < 18 else "night"
    )

    rows = []
    for city, group in weather.groupby("host_city"):
        stadium = group["provider_venue_name"].mode().iloc[0]
        by_part = group.groupby("daypart")["apparent_temperature_mean_c"].mean()
        overall = float(group["apparent_temperature_mean_c"].mean())
        day = float(by_part.get("day", overall))
        night = float(by_part.get("night", overall))
        altitude, source = ALTITUDES.get(str(city), (0, "unknown"))
        rows.append(
            {
                "host_city": city,
                "stadium": stadium,
                "altitude_m": altitude,
                "day_apparent_c": round(day, 2),
                "night_apparent_c": round(night, 2),
                "matches_observed": len(group),
                "altitude_source": source,
                "temperature_source": "data/context/world_cup_2026_weather_by_match.csv",
            }
        )
    frame = pd.DataFrame(rows).sort_values("host_city")
    frame.to_csv("data/reference/lab_venue_conditions_2026.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
