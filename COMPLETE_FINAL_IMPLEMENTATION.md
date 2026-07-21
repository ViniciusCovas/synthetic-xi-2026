# Implementação — Complete Final Engine v1

## Escopo implementado

A versão `complete_final_v1` adiciona ao núcleo calibrado de 90 minutos uma máquina de estados eliminatória com:

- primeiro e segundo tempos, acréscimos e cronologia auditável;
- prorrogação em dois períodos e disputa de pênaltis sem empate residual;
- fadiga individual, coordenação latente e superioridade numérica;
- políticas táticas dependentes de minuto, placar e número de jogadores;
- faltas, amarelos, segundos amarelos, vermelhos e pênaltis;
- revisão VAR e anulação probabilística pré-parametrizada;
- lesões leves e graves, substituições táticas e por lesão;
- limites de substituições e janelas, incluindo a janela adicional da prorrogação;
- Monte Carlo com intervalos de Wilson, ledger de seeds e replay representativo;
- diagnóstico pareado de inversão de mando, estabilidade entre seeds e invariantes;
- separação explícita entre gate de engenharia e gate científico de publicação.

## Regra de calibração

Os observáveis calibrados permanecem restritos aos 90 minutos. Tiros e tiros a gol da prorrogação são armazenados separadamente e não contaminam a comparação com a amostra `FT` usada na calibração. Os acréscimos estendem o relógio, mas não criam exposição adicional acima do total de posses calibrado para o tempo regulamentar.

## Regra do replay

O replay não é escolhido por dramaticidade. A realização é selecionada pela menor distância padronizada às medianas Monte Carlo de gols regulamentares, tiros, faltas, cartões, lesões, substituições e etapa de decisão.

## Gates

O CI falha quando o comportamento do motor não passa:

1. reprodutibilidade determinística;
2. invariantes de regras e estado;
3. calibração da distribuição regulamentar;
4. simetria sob inversão neutra;
5. estabilidade entre seeds.

O CI **não falsifica aprovação científica**. Mesmo com engenharia aprovada, a comparação substantiva permanece bloqueada enquanto qualquer evidência canônica do repositório indicar falha ou estiver ausente:

- suficiência de seleção;
- holdout externo pré-torneio;
- revisão cega de posições;
- autorização consolidada de comparação final;
- presença do protocolo preregistrado.

## Fonte expandida e auditabilidade

O bundle determinístico em `scripts/install_complete_final_bundle.py` contém os oito arquivos revisados. Os entrypoints do repositório o materializam antes da execução, e o workflow arquiva as fontes expandidas junto com resultados, manifestos e hashes. Para expandir manualmente:

```bash
python scripts/install_complete_final_bundle.py
```

## Execução

```bash
PYTHONPATH=. python scripts/run_complete_final_simulation.py --simulations 10000
PYTHONPATH=. python scripts/scientific/validate_complete_final.py --simulations 2000
```

Os artefatos são gravados em `data/simulations/complete_final_v1/`.
