# Quão bom precisa ser um time de agentes sintéticos para vencer o melhor XI do mundo? Uma curva dose-resposta com dados reais do ciclo 2025-26

**Rascunho v1 — 2026-08-08.** Todos os números desta versão são reproduzíveis
offline a partir da caché versionada do repositório (comandos ao final).

## Resumo

Construímos o melhor onze real do ano (Real Annual XI) a partir das
estatísticas anuais 2025-26 dos 1.248 convocados à Copa do Mundo de 2026, com
três correções de validade: resolução posicional geométrica corrigida (o
"bug do 9 isolado" classificava Kane, Mbappé, Haaland e Salah como pontas
direitas), identidade única por jogador e ajuste por força de liga com tabela
versionada de fontes públicas. Contra esse onze, simulamos times de agentes
sintéticos construídos em **quatro níveis da distribuição da elite humana**
por posição — média aparada do Top-20, média do Top-5, percentil 90 e máximo
por atributo ("best-of-breed") — em um motor de partida probabilístico
calibrado nos observáveis do próprio torneio (gols, finalizações, 0-0), com
incerteza de amostragem pareada entre equipes. O time sintético médio perde
com clareza (26,7% × 50,9% em 10.000 partidas); o composto best-of-breed
vence com folga (59,5% × 21,5%). O ponto de cruzamento estimado —
força de arquétipo 0,773 — coincide, dentro de ~1%, com a força média do
próprio XI real (0,765): neste motor, um time homogêneo de clones não exibe
vantagem nem desvantagem emergente relevante frente a um time heterogêneo de
especialistas de mesma força média.

## 1. Pergunta

Times sintéticos definidos como "a média dos melhores" perdem, por
construção, para "os melhores" — a média de um pool é inferior ao seu máximo.
A pergunta científica interessante não é *se* um sintético médio perde, mas
**em que ponto da distribuição da elite humana um time de agentes idênticos
passa a superar o melhor onze real** — e se a composição por clones tem
efeitos emergentes próprios (positivos ou negativos) além da força
individual.

## 2. Dados

- **Universo**: 1.248 jogadores convocados (48 seleções × 26), com totais
  anuais 2025-26 extraídos da API-Football e cacheados no repositório
  (`data/model_readiness/partial_annual_current_totals.csv`; 1.062 jogadores
  com dados, 1.019 com ≥900 minutos).
- **Alinhações**: grids de escalação por partida
  (`data/lake/batches/*_lineups.csv.gz`) para resolução posicional, com
  orientação lateral validada contra âncoras humanas (96% de acordo,
  `lateral_grid_validation.json`).
- **Calibração do motor**: 94 partidas completadas da Copa 2026
  (`data/simulations/calibration/world_cup_2026_targets.json`).

## 3. Método

### 3.1 Validade posicional (correções sobre a camada anual v1)

1. **Normalização lateral centrada**: a v1 usava `col/largura`, que atribui
   1,0 a qualquer jogador sozinho na sua linha — todo "9" isolado virava
   ponta-direita. A v2 usa `(col−(w+1)/2)/max(w−1,1)`; teste de regressão:
   Kane→ST, Hakimi→RB, N. Mendes→LB.
2. **Identidade única** por `player_id` (o provedor alterna grafias).
3. **Flexíveis mantidos**: estabilidade <60% não exclui; aloca ao papel modal
   com flag declarada (Mbappé, 56% ST, permanece elegível como ST).
4. **Âncoras públicas** (clubes/ligas oficiais, com URL por linha) têm
   prioridade sobre o grid.

### 3.2 Ajuste por força de liga

Volumes por-90 multiplicados pelo fator médio (ponderado por minutos) das
ligas da janela anual: T1=1,00 (top-5 europeu, UCL, Copa), T2=0,92, demais
0,85 (`league_strength_tiers_2026.csv`, fonte por linha). Taxas limitadas não
são ajustadas. Sensibilidade com cenários `none` e `steep`: sem ajuste, um
goleiro e um lateral de ligas fora do top-30 entram no XI — evidência direta
do viés que o ajuste remove.

### 3.3 Seleção

- **Real Annual XI** (cenário primário): melhor elegível por papel nas 11
  posições, sem repetição — Joan García; Cancelo, Romero, Söyüncü,
  N. Mendes; Pedri (flexível), Cherki, Yamal; Messi, Baturina (flexível),
  Mbappé.
- **Plantel de 26** com regras de time real: 3 goleiros, reserva direto por
  posição, 3 vagas de profundidade, zero duplicados (verificado por teste).
- **Validação externa**: sobreposição com listas humanas versionadas — FIFPro
  World 11 2025 (anual, como nós): 4/10; FIFA Best XI da Copa (torneio, outro
  construto): 2/11; UEFA TOTS 2025-26 (clube): 1/11. Divergências discutidas
  na §5.

### 3.4 Times sintéticos em níveis

Do mesmo pool Top-20 por arquétipo (GK, CB, FB, DM, CM, AM, W, ST):
`mean20` (média aparada 10%), `top5`, `p90` (percentil 90 por atributo),
`max20` (máximo por atributo). Incerteza de amostragem por partida
**pareada**: cada avatar herda a média aparada das σ dos membros —
eliminando o viés direcional de recorte identificado em auditoria (avatares
quase determinísticos contra reais ruidosos).

### 3.5 Motor

Motor probabilístico de partida (90′) por posses, calibrado nos observáveis
da Copa 2026 (gate de engenharia: erro absoluto ≤0,45 gol, ≤3,0 chutes,
≤1,5 chutes no alvo, ≤0,06 na taxa de 0-0). 10.000 partidas por nível, seed
única 20260718, RNG determinístico.

## 4. Resultados

| Nível sintético | Força média | Vitória sintético | Empate | Vitória real | Gols (sin×real) |
|---|---|---|---|---|---|
| mean20 (média Top-20) | 0,704 | 26,7% | 22,4% | **50,9%** | 1,29 × 1,86 |
| top5 | 0,749 | 33,8% | 22,8% | **43,4%** | 1,48 × 1,69 |
| p90 | 0,811 | **46,1%** | 22,6% | 31,4% | 1,85 × 1,48 |
| max20 (best-of-breed) | 0,874 | **59,5%** | 19,0% | 21,5% | 2,27 × 1,30 |

- A curva é **monotônica** e o cruzamento (margem de vitória = 0) ocorre em
  força de arquétipo **0,773** (interpolação linear entre top5 e p90).
- A força média do Real Annual XI é **0,765**. O cruzamento a ~1% desse valor
  indica que, neste motor, **onze clones de força x rendem como onze
  especialistas heterogêneos de força média x** — nem sinergia nem
  fragilidade emergente detectável da homogeneidade.
- Corolário: a pergunta "um time de IAs vence os melhores do mundo?" reduz-se
  a "em que percentil da elite os agentes operam?". A média da elite não
  basta (26,7%); o percentil 90 disputa de igual (46,1% × 31,4%); o composto
  best-of-breed — atributos que nenhum humano reúne simultaneamente — vence
  6 em cada 10 partidas com decisão.

## 5. Limitações

1. Universo restrito a convocados à Copa (Donnarumma e Palmer, p.ex., ficam
   fora do pool anual cacheado).
2. Fatores de liga são supostos estruturais com fontes públicas, delimitados
   por sensibilidade — não estimados de partidas inter-liga (extração via API
   é o próximo incremento).
3. Motor de partida única sem substituições; os planteles de 26 estão
   construídos e a integração com o motor de finais (banco, cartões,
   prorrogação, pênaltis) é a fase seguinte.
4. O índice usa estatísticas observáveis de contagem; inteligência
   sem bola e qualidades defensivas finas são parcialmente observadas.
5. Duas seleções do XI carregam flag de flexibilidade posicional declarada
   (Pedri DM/CM; Baturina LW) — a seleção é do índice pré-registrado, não de
   consenso editorial; a validação externa (§3.3) quantifica a distância a
   esse consenso.

## 6. Reprodução

```bash
python scripts/build_annual_selection_v05.py
PYTHONPATH=. python scripts/run_dose_response_grid.py --simulations 10000
PYTHONPATH=. pytest tests/test_annual_v05.py -q
```

Artefatos: `data/annual_v05/` (seleção), 
`data/simulations/annual_v05_dose_response/` (grade e sumários por nível).
