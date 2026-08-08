# Enriquecimento world-class — quatro fontes, quatro fraquezas fechadas

Cada item ataca uma limitação *declarada* do projeto. Nada altera os
artefatos congelados do experimento oficial v1.

## 1. Remates reais (StatsBomb Open Data) + modelo de xG próprio ✅

- `scripts/enrichment/sync_statsbomb_shots.py`: **230 partidas** internacionais
  (Mundial 2018 e 2022, Euro 2020 e 2024), **5.829 remates, 659 golos**, com
  coordenadas, corpo, técnica, pressão e o xG do provedor. Tabela compacta em
  `data/enrichment/statsbomb/international_shots.csv.gz` (296 KB); zero falhas.
- `scripts/enrichment/build_xg_model.py`: regressão logística determinística
  (numpy) com divisão temporal honesta — treina em WC18+Euro20, testa em
  WC22+Euro24:

| Métrica (holdout) | Nosso xG | xG StatsBomb |
|---|---|---|
| log-loss | 0,265 | 0,247 |
| Brier | 0,074 | 0,069 |

  ~92% da qualidade do provedor usando só geometria+contexto (sem
  freeze-frames), e bem calibrado (média prevista 8,9% vs taxa-base 9,1%).
- **Auditoria espacial do motor** (`engine_spatial_audit.json`):
  - conversão de pênalti em jogo: **70,4% empírica (n=81)** vs 76,5% efetiva
    do motor → o motor é ~6 p.p. otimista em torneios internacionais;
  - pênaltis de disputa: 66,9% (n=142) — mais baixos que os de jogo, como o
    motor supõe qualitativamente;
  - o teto `goal_given_on_target = 0,86` **nunca é atingido** empiricamente
    (máximo por banda: 0,79) — a suposição não distorce.

  Atribuição obrigatória: **Hudl StatsBomb Open Data**. Uso de investigação;
  confirmar termos antes de uso comercial derivado.

## 2. Força de liga ESTIMADA, não suposta ✅

`scripts/build_league_strength_estimate.py`: modelo aditivo de dois fatores
sobre o rating por jogador-jogo (45k linhas, ponderado por minutos),
identificado pelos **contrastes intra-jogador** (o mesmo jogador em liga,
UCL e seleção). Mapeamento a fator declarado a priori
(`clip(1 − 0.5·Δ, 0.70, 1.05)`, referência = média Big-5).

- Direção sã: qualificatórias asiáticas/CONCACAF e ligas nórdicas/Qatar
  inflacionam ratings (fator 0,73–0,80); Big-5 ≈ 1,0.
- Novo cenário **`estimated`** na seleção anual v0.5 (o `primary`
  pré-registrado fica intacto). Efeito no XI anual: **entra Rodri no DM** e
  Aït-Nouri no LB — a estimativa aproxima o índice do consenso humano
  (validade convergente).

## 3. Benchmark de mercado — harness pronto ✅ (dados: passo manual)

`scripts/scientific/market_benchmark.py` compara as previsões pré-torneio
congeladas com odds de fecho de-vigadas (log-loss, Brier, top-1). Falta só o
CSV de odds (`data/reference/market_odds_worldcup2026.csv`, esquema
documentado no script) — as fontes livres estão bloqueadas pelo proxy deste
ambiente e exigem verificação de termos; o harness nunca inventa dados.

## 4. Atributos de jogador do Wikidata (CC0) — script + workflow ✅

`scripts/enrichment/fetch_wikidata_player_attributes.py` + workflow
`wikidata-player-attributes` (dispatch manual, sem secrets): altura e data de
nascimento por match de nome com validação de unicidade; ambíguos ficam
marcados e não são usados. Nota honesta: o Wikidata não tem propriedade
consolidada de pé dominante — para lados continuamos com a evidência
observada de grid (33k escalações), que é superior por ser comportamental.

## O que fica explicitamente fora

- Mais chamadas à API-Football: cobertura mediana já é 100%; só faria sentido
  para um produto de scouting com universo 10-50×.
- Scraping de Transfermarkt/Understat: termos proíbem.
- ClubElo/football-data: bloqueados neste ambiente; o harness (3) aceita os
  dados quando obtidos de fonte licenciada.
