#!/usr/bin/env python3
"""Shared helpers for enrichment pipelines."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or "unknown"


def cache_path(directory: Path, prefix: str, parts: Iterable[Any]) -> Path:
    payload = json.dumps(list(parts), ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return directory / f"{prefix}_{digest}.json"


def parse_iso(value: Any) -> datetime:
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def nearest_time_index(times: list[str], target: datetime) -> int:
    if not times:
        raise ValueError("times cannot be empty")
    distances = [abs((parse_iso(item) - target).total_seconds()) for item in times]
    return int(min(range(len(distances)), key=distances.__getitem__))


def choose_geocode_result(results: list[dict[str, Any]], city: str, country: str | None = None) -> dict[str, Any] | None:
    if not results:
        return None
    city_slug = slug(city)
    country_slug = slug(country or "")

    def score(item: dict[str, Any]) -> tuple[int, int, int, float]:
        name_match = int(slug(item.get("name", "")) == city_slug)
        country_match = int(
            not country_slug
            or slug(item.get("country", "")) == country_slug
            or slug(item.get("country_code", "")) == country_slug
        )
        admin_match = int(city_slug in {slug(item.get("admin1", "")), slug(item.get("admin2", ""))})
        population = float(item.get("population") or 0)
        return country_match, name_match, admin_match, population

    return max(results, key=score)
