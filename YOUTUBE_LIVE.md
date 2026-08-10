# Transmitir a final simulada no YouTube (ao vivo, com imagens)

O laboratório tem um **modo TV**: uma página 1920×1080 desenhada para
transmissão que roda o motor científico ao vivo no navegador e narra a final
lance a lance — placar, relógio, ticker de eventos, cartão de golo com avatar
ilustrado e cartão final com troféu.

E o centro do ecrã é um **campo 2D animado** (`match2d.js`): os 22 titulares
reais movem-se em formação viva, trocam passes, e a coreografia converge
sempre para o lance que o motor decidiu — o autor recebe a bola antes do seu
remate, o goleiro defende, o golo dispara a celebração e o reinício. Como no
visualizador do Football Manager: os LANCES são do motor científico; o
movimento entre eles é interpolação plausível, declarada como tal.

## URL do modo TV

```
https://<seu-site>/lab/tv/?home=Spain&away=Argentina&sims=200&loop=1
```

Parâmetros: `home`, `away` (nomes em inglês das 44 seleções), `sims`
(finais simuladas antes de escolher a mais provável; 200 é bom equilíbrio),
`seed` (fixa a transmissão para reprodutibilidade), `speed` (aceleração),
`loop=1` (recomeça sozinho a cada 20 s do fim — ideal para stream contínua).

## Passo a passo (OBS → YouTube Live)

1. **YouTube Studio** → Criar → Transmitir ao vivo → copie a *chave de stream*.
2. **OBS Studio** (grátis): Configurações → Stream → YouTube → cole a chave.
3. Fontes → **+ → Navegador**: URL do modo TV acima, largura **1920**,
   altura **1080**. (Marque "Atualizar navegador quando a cena ficar ativa".)
4. Áudio opcional: adicione uma fonte de mídia com ambiente de estádio em
   loop (use áudio licenciado/livre).
5. **Iniciar transmissão**. Com `loop=1`, cada ciclo simula 200 finais novas
   e transmite a mais provável — a stream nunca repete exatamente.

Alternativa sem "ao vivo": grave 10–15 minutos do modo TV no OBS e publique
como **Estreia** (Premiere) — o chat funciona como num live.

## As imagens (avatares e cenografia)

Quatro ilustrações editoriais geradas (Recraft V4.1, paleta do projeto):
estádio noturno (fundo), avatar verde e avatar índigo **estilizados e sem
rosto** (cartões de golo), e troféu com confete (cartão final).

Para colocá-las no repositório: **Actions → Fetch TV Assets → Run workflow**
(um clique, sem secrets — baixa e commita os 4 PNG). A página funciona com
fallback elegante enquanto os PNG não estão presentes.

### Direitos de imagem — leia antes de monetizar

- Os avatares são **estilizados de propósito**: usar o rosto/semelhança de
  jogadores reais (Messi etc.) em conteúdo comercial viola direitos de
  imagem. Nomes como dado editorial/estatístico na narração são outra coisa
  — mas para monetização agressiva, consulte alguém de confiança.
- "Copa do Mundo"/"World Cup" e marcas FIFA são registradas; o modo TV usa
  "final simulada · Copa 2026" como descrição factual do estudo. Evite logos
  oficiais, mascotes e material audiovisual da FIFA na stream.
- A narração diz sempre **simulada** no rótulo AO VIVO da página — mantenha
  isso visível: transparência também é proteção.

## A "final do Mundial 2026 simulada"

```
/lab/tv/?home=Spain&away=Argentina&venue=New%20York%20New%20Jersey&sims=500&seed=20260719
```

Espanha × Argentina — o confronto real da final — com seed fixa: a mesma
transmissão, reproduzível por qualquer pessoa, para sempre.
