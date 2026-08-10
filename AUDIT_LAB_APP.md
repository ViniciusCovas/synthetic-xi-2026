# Auditoria científica do aplicativo visual

Auditoria do que o app em `/lab/` **realmente roda**, feita sobre o pacote
publicado em `web/public/lab/py` — o mesmo que o navegador baixa — e não
sobre as fontes do repositório, de modo que uma exportação desatualizada
apareceria como falha.

Verificações fixadas em `tests/test_lab_app_audit.py` (7 testes).

## O que passou

| Verificação | Resultado |
|---|---|
| 44 seleções com 11 titulares, um por papel, sem repetição | ✅ |
| Titulares e ordem de pênaltis dentro da lista de inscritos | ✅ |
| Nenhum reserva que também seja titular | ✅ |
| Nenhum goleiro improvisado | ✅ |
| Probabilidades somam 1; todo jogo tem vencedor | ✅ |
| Modos de decisão somam 1 (74% nos 90′, 11% prorrogação, 15% pênaltis) | ✅ |
| **Narrar não altera o resultado** | ✅ |
| Lances em ordem cronológica; último placar narrado = placar final | ✅ |
| Número de gols narrados = placar | ✅ |
| Nenhum protagonista fora dos elencos; autor do gol no lado certo | ✅ |
| `summary()` bate com o que foi simulado | ✅ |

O teste de determinismo merece destaque: a interface conta os resultados com
`keep_timeline=False` e depois **re-simula** a final escolhida com
`keep_timeline=True`. Se narrar consumisse sorteios diferentes, o usuário
assistiria a uma partida que nunca entrou na estatística mostrada logo acima
dela. Verificado idêntico em placar, vencedor e modo de decisão.

## O que estava errado e foi corrigido

### 1. Precisão falsa na probabilidade de vitória

A tela exibia `46,5%` a partir de 200 simulações. O erro de Monte Carlo nesse
regime é ±6,9 pontos: o terceiro dígito era ruído, e o usuário não tinha como
saber que 46,5% × 53,5% é **empate técnico**.

Agora a página calcula IC95% = ±1,96·√(p(1−p)/N), arredonda as casas decimais
conforme a margem, desenha a faixa de incerteza sobre a barra e declara em
texto se a vantagem se separa ou não do erro amostral.

### 2. As condições de jogo prometiam mais do que entregam

Medição com **1.500 finais pareadas por seed** (México × Noruega). O pareamento
é exato porque `_apply_fatigue` não consome RNG, então os fluxos ficam alinhados
e a comparação tem variância mínima:

| Cenário | Vitória do México | Gols/jogo | Partidas alteradas | Δ vitória |
|---|---|---|---|---|
| sem condições | 0,5107 | 2,838 | — | — |
| Cidade do México 14h (calibrado) | 0,5093 | 2,825 | 185/1500 (12,3%) | −0,0013 ± 0,0109 |
| Cidade do México 14h (acentuado) | 0,5107 | 2,800 | 328/1500 (21,9%) | +0,0000 ± 0,0140 |
| 40 °C + 2240 m (acentuado) | 0,5113 | 2,795 | 348/1500 (23,2%) | +0,0007 ± 0,0144 |

Leitura: as condições **estão ligadas** e mudam de 12% a 23% das partidas
individualmente, além de reduzirem os gols de forma monotônica (−1,5% no
extremo). Mas **não deslocam quem vence** — os três Δ são indistinguíveis de
zero.

A razão é estrutural: calor e altitude entram como `fatigue_per_90`, um
parâmetro **global** que recai igualmente sobre os dois times. O resultado do
motor depende da *diferença* de força entre eles, e uma fadiga simétrica quase
se cancela nessa diferença.

**Limitação declarada:** o modelo não representa aclimatação. O achado de
McSharry (BMJ 2007) que motiva o canal de altitude é justamente sobre
*vantagem do mandante aclimatado* — uma assimetria que esta implementação não
tem. Modelá-la exigiria um canal por seleção, com fonte e esquema de
sensibilidade próprios; não foi feito por conta própria.

A página agora diz isso onde o usuário escolhe o estádio: escolher a sede muda
**como a final se desenrola**, não o favoritismo.

### 3. Improvisos de posição invisíveis

138 improvisos declarados em 42 das 44 seleções (nenhum no gol). O motor já os
penaliza e registra; o campo os desenhava como posição natural. Agora recebem
anel tracejado, asterisco e contagem na legenda.

## Diferença declarada em relação ao paper

O laboratório monta elencos com piso de elegibilidade de **450 minutos**,
enquanto a seleção anual do estudo usa **900**. Os onzes podem divergir. Está
no manifesto de exportação e no rodapé da página.

## O que o campo animado é e não é

Os **lances** — gols, defesas, faltas, cartões, substituições, pênaltis, VAR —
são exatamente os que o motor sorteou, na ordem e no minuto que ele produziu.
A **movimentação entre eles** é interpolação plausível: os jogadores convergem
para o lance seguinte, mas o motor não simula posições no campo. A página
declara isso abaixo do campo, e a distinção é a mesma do visualizador do
Football Manager.
