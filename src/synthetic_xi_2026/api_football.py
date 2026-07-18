"""Small cached client for API-FOOTBALL endpoints used by the study."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .config import API_BASE, COMPLETED_STATUSES


class APIDataError(RuntimeError):
    """Raised when the provider response is unavailable or malformed."""


class APIFootballClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path = "data/raw/api_football",
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY")
        if not self.api_key:
            raise APIDataError(
                "API_FOOTBALL_KEY is missing. Add it locally or as a GitHub Actions secret."
            )
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.request_log: list[dict[str, Any]] = []

    def _record(self, endpoint: str, params: dict[str, Any], payload: dict[str, Any], source: str) -> None:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.request_log.append(
            {
                "endpoint": endpoint,
                "params": params,
                "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "source": source,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _get(
        self,
        endpoint: str,
        params: dict[str, Any],
        cache_name: str,
        use_cache: bool = False,
    ) -> list[dict[str, Any]]:
        cache_path = self.cache_dir / f"{cache_name}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if use_cache and cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self._record(endpoint, params, payload, "cache")
            data = payload.get("response")
            if isinstance(data, list):
                return data

        response = requests.get(
            f"{API_BASE}/{endpoint.lstrip('/')}",
            params=params,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise APIDataError(f"Provider request failed for {endpoint}: {exc}") from exc
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise APIDataError(f"Provider returned errors for {endpoint}: {errors}")
        data = payload.get("response")
        if not isinstance(data, list):
            raise APIDataError(f"Unexpected response shape for {endpoint}")
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._record(endpoint, params, payload, "network")
        return data

    def fixtures(self, league_id: int, season: int) -> list[dict[str, Any]]:
        # Always refresh the fixture index because tournament status changes.
        return self._get(
            "fixtures",
            {"league": league_id, "season": season},
            f"fixtures_{league_id}_{season}",
            use_cache=False,
        )

    def completed_fixtures(
        self, league_id: int, season: int, cutoff_timestamp: int | None = None
    ) -> list[dict[str, Any]]:
        fixtures = self.fixtures(league_id, season)
        completed: list[dict[str, Any]] = []
        for item in fixtures:
            fixture = item.get("fixture") or {}
            status = (fixture.get("status") or {}).get("short")
            timestamp = fixture.get("timestamp")
            if status not in COMPLETED_STATUSES:
                continue
            if cutoff_timestamp is not None and timestamp and int(timestamp) > cutoff_timestamp:
                continue
            completed.append(item)
        return sorted(completed, key=lambda x: (x.get("fixture") or {}).get("timestamp") or 0)

    def enriched_fixtures(self, fixture_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch up to 20 fixtures with embedded lineups/player data in one call."""
        if not fixture_ids:
            return []
        if len(fixture_ids) > 20:
            raise ValueError("API-FOOTBALL supports at most 20 fixture IDs per batch")
        ordered = sorted(int(value) for value in fixture_ids)
        id_string = "-".join(str(value) for value in ordered)
        return self._get(
            "fixtures",
            {"ids": id_string},
            f"enriched_{id_string}",
            use_cache=True,
        )

    def lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        return self._get(
            "fixtures/lineups", {"fixture": fixture_id}, f"lineups_{fixture_id}", use_cache=True
        )

    def player_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        return self._get(
            "fixtures/players",
            {"fixture": fixture_id},
            f"players_{fixture_id}",
            use_cache=True,
        )
