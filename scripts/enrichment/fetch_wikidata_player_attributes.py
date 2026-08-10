#!/usr/bin/env python3
"""Atributos de jogador do Wikidata (altura, nascimento, cidadania) — CC0.

Faz match dos 1.248 convocados por nome normalizado (+ validação por idade)
contra futebolistas no Wikidata via SPARQL, em lotes. Grava
``data/reference/player_attributes_wikidata.csv`` com QID e nível de
confiança do match. Matches ambíguos ficam marcados e NÃO são usados.

Nota: o Wikidata não tem propriedade consolidada de pé dominante; altura e
data de nascimento são bem povoadas e úteis para validação de identidade.

Requer rede aberta (query.wikidata.org). No ambiente CI use o workflow
``wikidata-player-attributes`` (sem secrets — o Wikidata é público).
"""

from __future__ import annotations

import json
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ENDPOINT = "https://query.wikidata.org/sparql"
SQUAD = Path("data/audits/world_cup_2026_squad_universe.csv")
OUT = Path("data/reference/player_attributes_wikidata.csv")
STATUS = Path("data/reference/player_attributes_wikidata_status.json")
BATCH = 40


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def sparql(query: str) -> list[dict]:
    url = ENDPOINT + "?" + urllib.parse.urlencode(
        {"query": query, "format": "json"}
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "synthetic-xi-2026/1.0 (research)"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)["results"]["bindings"]


def batch_query(names: list[str]) -> list[dict]:
    values = " ".join(f'"{n}"@en' for n in names)
    return sparql(f"""
      SELECT ?item ?itemLabel ?height ?dob WHERE {{
        VALUES ?label {{ {values} }}
        ?item rdfs:label|skos:altLabel ?label .
        ?item wdt:P106 wd:Q937857 .
        OPTIONAL {{ ?item wdt:P2048 ?height . }}
        OPTIONAL {{ ?item wdt:P569 ?dob . }}
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }}""")


def main() -> None:
    squad = pd.read_csv(SQUAD).drop_duplicates("player_id")
    rows: list[dict] = []
    names = squad["player_name"].astype(str).tolist()
    for start in range(0, len(names), BATCH):
        chunk = names[start:start + BATCH]
        try:
            bindings = batch_query(chunk)
        except Exception as error:  # rede/quota: registra e segue
            rows.append({"error_batch_start": start, "error": str(error)[:200]})
            time.sleep(5)
            continue
        by_label: dict[str, list[dict]] = {}
        for b in bindings:
            by_label.setdefault(norm(b["itemLabel"]["value"]), []).append(b)
        for name in chunk:
            candidates = by_label.get(norm(name), [])
            qids = {c["item"]["value"].rsplit("/", 1)[-1] for c in candidates}
            if len(qids) == 1:
                c = candidates[0]
                rows.append({
                    "player_name": name,
                    "wikidata_qid": qids.pop(),
                    "height_cm": float(c["height"]["value"]) * (
                        100 if float(c["height"]["value"]) < 3 else 1
                    ) if "height" in c else None,
                    "date_of_birth": c["dob"]["value"][:10] if "dob" in c else None,
                    "match_confidence": "unique_label",
                })
            elif len(qids) > 1:
                rows.append({
                    "player_name": name,
                    "wikidata_qid": None,
                    "match_confidence": f"ambiguous_{len(qids)}",
                })
        time.sleep(1.2)  # etiqueta WDQS

    frame = pd.DataFrame(rows)
    merged = squad.merge(frame, on="player_name", how="left")
    merged.to_csv(OUT, index=False)
    matched = merged["wikidata_qid"].notna().sum()
    STATUS.write_text(json.dumps({
        "status": "wikidata_attributes_fetched",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "players": int(len(squad)),
        "matched_unique": int(matched),
        "license": "CC0 (Wikidata)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"matched {matched}/{len(squad)}")


if __name__ == "__main__":
    main()
