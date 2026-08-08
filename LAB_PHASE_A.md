# Laboratório de simulação — Fase A: rematch de seleções reais

"Como se o Mundial continuasse": simular uma final completa entre quaisquer
duas seleções da Copa 2026, com elencos reais, banco real e as regras
completas de uma final (janelas de substituição, prorrogação, pênaltis,
cartões, VAR), usando o MESMO motor do experimento oficial.

## Como funciona

```bash
PYTHONPATH=. python scripts/run_lab_rematch.py \
    --home Spain --away Argentina --simulations 2000 --seed 20260808
```

1. `simulator/lab_teams.py` constrói um `OfficialTeamBundle` para cada
   seleção a partir da tabela anual v0.5 (papéis corrigidos, identidades
   únicas, ajuste de liga): XI titular por papel, banco com todos os demais
   extraídos, ordem de pênaltis por finalização.
2. O bundle alimenta `OfficialCompleteFinalSimulator` — o motor de finais do
   experimento oficial — sem nenhuma modificação no motor.
3. Saída em `data/lab/rematch_<home>_<away>/`: probabilidades de vitória,
   como se decidiu (90′/prorrogação/pênaltis), placares mais prováveis,
   elencos usados e uma timeline de exemplo.

## Regras declaradas

- Piso de elegibilidade do laboratório: **450 minutos anuais** (a seleção
  v0.5 principal usa 900) — necessário para cobrir elencos nacionais.
- Papel sem titular natural → melhor vizinho declarado entra **penalizado**
  pela regra oficial de fora-de-posição (×0,90 habilidade, +0,03 incerteza);
  toda decisão fica registrada em `team_construction_decisions`.
- Elencos derivados de dados anuais de clube: um rematch responde "com a
  força anual desses jogadores", não "com a escalação exata daquele dia".

## Validação (Espanha × Argentina, a final real)

Resultados em `data/lab/rematch_spain_argentina/summary.json` — comparar com:
- resultado real: Espanha campeã, 1–0 na prorrogação;
- forecast pré-jogo do repositório (features de torneio, outro método):
  Espanha 61,4% (`projects/2026_final_forecast/`).

Divergências são esperadas e informativas: o laboratório usa força anual de
clube; o forecast usou forma do torneio.

## Fase B — condições de jogo (implementada)

`simulator/lab_conditions.py` adiciona modificadores estruturais declarados,
com fontes e esquema de sensibilidade (`off`/`primary`/`strong`):

- **Calor**: fadiga +0,005/°C de temperatura aparente acima de 24 °C
  (Mohr & Krustrup 2013; protocolo FIFA de pausas de hidratação).
- **Altitude**: fadiga +0,02/1.000 m e conversão ofensiva ×(1+0,02/km)
  (McSharry, BMJ 2007).
- **Dia/noite**: muda a temperatura aparente usada — médias empíricas por
  cidade-sede calculadas da evidência meteorológica do próprio repositório
  (`data/reference/lab_venue_conditions_2026.csv`, gerada por
  `scripts/build_lab_venue_conditions.py`).

```bash
PYTHONPATH=. python scripts/run_lab_rematch.py \
    --home Spain --away Argentina --venue "Mexico City" --kickoff day
```

## Aplicativo no navegador

`web/public/lab/` é um app estático (`/lab/` no site) em que se escolhe as
duas seleções, o estádio, o horário e a intensidade das condições — e o
**mesmo motor Python de finais roda no navegador** via Pyodide (numpy, sem
servidor). Os elencos das 44 seleções montáveis, os presets de estádio e a
calibração são exportados por `scripts/export_lab_app_data.py`; o pacote
embarcado é validado em CPython por `tests/test_lab_app_package.py` (mesmo
código nas duas plataformas).

## Limitações e próximas fases

- Cobertura anual parcial de alguns elencos (jogador ausente da caché não
  pode ser escalado; ex.: laterais titulares de algumas seleções) — a
  extração dirigida via API (workflows com secret) fecha essas lacunas.
- **Fase B (condições)**: modificadores calibrados e declarados para
  noite/calor/altitude, usando a evidência meteorológica já coletada em
  `data/context/`.
- **Fase C (contrafactuais)**: trocas de jogador entre elencos ("e se X
  jogasse pela seleção Y?") — a construção de bundles já aceita qualquer
  lista de jogadores; falta apenas a interface de swap.
