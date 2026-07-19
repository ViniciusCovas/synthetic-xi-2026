#!/usr/bin/env python3
"""Quota-aware API-Football client for batched fixture retrieval."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://v3.football.api-sports.io"
RAW_DIR = Path("data/raw/adaptive_annual/bundles")


class QuotaStop(RuntimeError):
    pass


class BatchClient:
    def __init__(self) -> None:
        key = os.getenv("API_FOOTBALL_KEY")
        if not key:
            raise RuntimeError("Falta API_FOOTBALL_KEY")
        self.key = key
        self.session = requests.Session()
        self.calls = 0
        self.remaining: int | None = None
        self.daily_limit: int | None = None
        self.minute_limit: int | None = None
        self.max_calls = int(os.getenv("MAX_NETWORK_REQUESTS", "700"))
        self.min_remaining = int(os.getenv("MIN_DAILY_REQUESTS_REMAINING", "20"))
        safe_rpm = float(os.getenv("API_SAFE_REQUESTS_PER_MINUTE", "180"))
        self.interval = 60.0 / max(safe_rpm, 1.0)
        self.last_call = 0.0

    def _headers(self, response: requests.Response) -> None:
        mapping = {
            "x-ratelimit-requests-remaining": "remaining",
            "x-ratelimit-requests-limit": "daily_limit",
            "x-ratelimit-limit": "minute_limit",
        }
        lower = {k.lower(): v for k, v in response.headers.items()}
        for header, attr in mapping.items():
            value = lower.get(header)
            if value is not None:
                try:
                    setattr(self, attr, int(value))
                except ValueError:
                    pass

    def status(self) -> dict[str, Any]:
        response = self.session.get(
            f"{API_BASE}/status",
            headers={"x-apisports-key": self.key},
            timeout=90,
        )
        self._headers(response)
        response.raise_for_status()
        payload = response.json()
        req = ((payload.get("response") or {}).get("requests") or {})
        if req.get("limit_day") is not None:
            self.daily_limit = int(req["limit_day"])
        if req.get("current") is not None and self.daily_limit is not None:
            self.remaining = max(0, self.daily_limit - int(req["current"]))
        return payload

    def get_fixtures_bundle(self, fixture_ids: list[int]) -> dict[str, Any]:
        if not fixture_ids or len(fixture_ids) > 20:
            raise ValueError("fixture_ids must contain between 1 and 20 ids")
        ids = "-".join(str(x) for x in fixture_ids)
        digest = hashlib.sha256(ids.encode()).hexdigest()[:20]
        path = RAW_DIR / f"fixtures_{digest}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if self.calls >= self.max_calls:
            raise QuotaStop("Límite de llamadas del lote alcanzado")
        if self.remaining is not None and self.remaining <= self.min_remaining:
            raise QuotaStop("Reserva diaria de seguridad alcanzada")
        attempts = 0
        while True:
            attempts += 1
            wait = self.interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            response = self.session.get(
                f"{API_BASE}/fixtures",
                params={"ids": ids},
                headers={"x-apisports-key": self.key},
                timeout=120,
            )
            self.last_call = time.monotonic()
            self._headers(response)
            if response.status_code in {429, 500, 502, 503, 504} and attempts < 7:
                retry_after = float(response.headers.get("retry-after") or min(90, 2**attempts))
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            payload = response.json()
            errors = payload.get("errors") or {}
            if errors and attempts < 7:
                text = json.dumps(errors).lower()
                if any(token in text for token in ("limit", "rate", "tempor", "timeout")):
                    time.sleep(min(90, 2**attempts))
                    continue
            if errors:
                raise RuntimeError(f"API-Football bundle error: {errors}")
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self.calls += 1
            return payload
