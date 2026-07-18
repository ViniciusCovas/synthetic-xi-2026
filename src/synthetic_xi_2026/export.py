"""Exporta artefactos compactos consumidos por la interfaz estática."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _records(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    frame = pd.read_csv(path)
    return json.loads(frame.to_json(orient="records"))


def export_web_data(
    processed_dir: str | Path = "data/processed",
    web_data_dir: str | Path = "web/public/data",
) -> None:
    src = Path(processed_dir)
    dst = Path(web_data_dir)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ["manifest", "methods"]:
        source = src / f"{name}.json"
        if source.exists():
            (dst / source.name).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
    for name in [
        "avatars",
        "avatar_metrics",
        "avatar_members",
        "rankings",
        "fixtures",
        "real_benchmarks",
        "positional_comparisons",
        "synthetic_xi",
        "real_best_xi",
    ]:
        payload = _records(src / f"{name}.csv")
        (dst / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
