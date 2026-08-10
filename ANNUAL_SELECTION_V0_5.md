# Seleção anual v0.5 — melhores do ano com validade posicional e de liga

Camada nova e independente (`data/annual_v05/`), construída 100% offline da
caché versionada. **Nenhum artefato do experimento oficial v1 foi modificado.**

## Motivação (achados de auditoria)

1. **Bug do "9 isolado"** na resolução anual v1 (`resolve_eleven_roles.py`):
   numa linha do grid com um único jogador, `coluna/largura = 1/1 = 1,0` caía
   na banda direita — **Kane, Mbappé, Haaland e Salah estavam classificados
   como ponta-direita**, contaminando o pool de cada posição.
2. **Identidades duplicadas** por variação de grafia do provedor (mesmo bug
   corrigido na camada do torneio em v0.4.1).
3. **Sem ajuste por força de liga**: goleiro da liga sul-africana superava
   Courtois por volume estatístico contra oposição mais fraca.
4. **Filtros que descartavam craques**: exigência dura de 60% de estabilidade
   tirava Mbappé (56% ST) do universo em vez de alocá-lo com regra declarada.

## Método

- **Papéis v2**: coordenada lateral centrada `(col−(w+1)/2)/max(w−1,1)`
  (linha de largura 1 = central); zagueiros/atacantes laterais com
  `|xc| ≥ 0,28`; profundidade de linha para DM/CM/AM; âncoras públicas
  (`public_role_anchors_2026.csv`) têm prioridade. Flexíveis (<60%) entram no
  papel modal com `flexible=true`.
- **Identidade**: agregação por `player_id` com nome canônico.
- **Elegibilidade**: ≥900 minutos anuais.
- **Ajuste de liga**: volumes por-90 × fator médio ponderado por minutos das
  ligas da janela anual (`league_strength_tiers_2026.csv`, com fonte por
  linha; taxas limitadas não são ajustadas). Cenários: `primary`
  (T1 1,00 / T2 0,92 / resto 0,85), `none` e `steep` (sensibilidade).
- **XI real**: melhor elegível por papel nas 11 posições, sem repetição.
- **Plantel de 26 como time de verdade**: 11 titulares + 2 goleiros reservas +
  1 reserva direto por posição de linha + 3 vagas livres de profundidade;
  nenhum jogador repetido (validado por teste).
- **Sintético em 4 níveis** sobre o mesmo pool Top-20 por arquétipo:
  `mean20` (média aparada 10%), `top5`, `p90` (percentil 90 por atributo),
  `max20` (melhor valor de cada atributo — o composto "best-of-breed").
  Incerteza de amostragem por partido **pareada**: cada avatar herda a média
  aparada das σ dos seus membros.

## Resultado da seleção (cenário primário)

GK Joan García · RB João Cancelo · RCB Cristian Romero · LCB Çağlar Söyüncü ·
LB Nuno Mendes · DM Pedri (flexível DM/CM) · CM Rayan Cherki ·
AM Lamine Yamal · RW Lionel Messi · LW Martin Baturina (flexível) ·
ST Kylian Mbappé

A sensibilidade de liga muda o XI nas margens (sem ajuste entram
Chaine/Hadjam; com ajuste íngreme, Otamendi e Olise) — evidência direta de
que o ajuste importa. Ver `data/annual_v05/manifest.json`.

## Validação externa

`data/annual_v05/external_validation.json` mede a sobreposição do nosso XI
com listas humanas versionadas em `external_best_xi_2026.csv` (FIFA Best XI
da Copa 2026, UEFA Team of the Season 2025-26, FIFPro World 11 2025) — a
sobreposição só é interpretável sobre o subconjunto dessas listas presente no
nosso universo (convocados à Copa com ≥900′ anuais).

## Dose-resposta (a pergunta do paper)

Em vez de um único sintético que "sempre perde" contra o melhor XI (a média
é, por construção, pior que o nº 1), a grade
`scripts/run_dose_response_grid.py` roda os 4 níveis contra o Real Annual XI
(motor calibrado, 10.000 partidas por nível, mesma seed) e estima o **ponto
de cruzamento**: o nível da elite humana em que um time de agentes sintéticos
passa a superar o melhor onze do mundo. Resultados em
`data/simulations/annual_v05_dose_response/`.

## Reprodução

```bash
python scripts/build_annual_selection_v05.py
PYTHONPATH=. python scripts/run_dose_response_grid.py
PYTHONPATH=. pytest tests/test_annual_v05.py -q
```

## Limitações declaradas

- Universo = convocados à Copa 2026 (jogadores de elite não convocados ficam
  fora; Donnarumma/Palmer, p.ex., não constam da caché anual).
- Fatores de liga são supostos estruturais com fontes públicas, não
  estimados; a análise de sensibilidade delimita seu efeito. Estimá-los da
  API (partidas inter-liga) é o próximo incremento e há workflow com secret
  disponível para a extração.
- O motor calibrado é de partida única (90′) e não modela banco; a
  integração dos planteles de 26 com o motor de finais (substituições) é a
  fase seguinte do laboratório.
