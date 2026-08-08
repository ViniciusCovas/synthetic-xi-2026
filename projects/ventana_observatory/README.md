# Ventana — observatório de janela

Um telefone parado na janela vira um instrumento científico.

O aparelho fica preso ao vidro rodando visão computacional **inteiramente no
dispositivo**. Nenhum vídeo é gravado e nenhum quadro sai do telefone: a saída é
uma linha de números por minuto. Cada minuto mede três camadas da mesma cena.

| Camada | O que mede | Sinal que aparece |
| --- | --- | --- |
| **Rua** | objetos que cruzam uma linha virtual, com sentido e porte | ritmo da cidade: picos da manhã e da tarde, domingo lento, rajadas de semáforo |
| **Céu** | luz, azulidade, saturação, textura de nuvem | o dia inteiro em cor; nublado versus limpo sem precisar de sensor |
| **Prédios** | fração de pixels acesos e número de janelas iluminadas | a que horas o bairro dorme e a que horas acorda |

Nada disso usa modelo treinado nem nuvem. É subtração de fundo, componentes
conexas, rastreamento por vizinho mais próximo e fotometria de região — tudo em
JavaScript puro, offline, num telefone parado.

## Como pôr para rodar

1. **Sirva a pasta `capture/` por HTTPS** (ou `http://localhost` via túnel). A
   câmera do navegador exige contexto seguro. Do próprio repositório:

   ```bash
   python -m http.server 8899          # depois use um túnel HTTPS até esta porta
   ```

2. **No Pixel, abra `capture/index.html` no Chrome** e adicione à tela inicial.
   Ela é uma PWA: depois da primeira visita funciona sem rede.

3. **Prenda o telefone na janela.** Estabilidade é tudo — o modelo de fundo
   assume que a câmera não se move. Um suporte de ventosa ou fita larga resolve.
   Ligue na tomada: gravar a noite inteira consome bateria.

4. **Calibre uma vez**, tocando nos quatro botões:
   - `Cielo` — arraste um retângulo sobre uma faixa que seja *só* céu;
   - `Calle` — toque nos vértices da área de rua e feche o polígono;
   - `Línea` — toque em dois pontos: é a linha de contagem, atravessada pelos
     objetos. Perpendicular ao fluxo funciona melhor;
   - `Fachada` — opcional, um retângulo sobre as janelas de um prédio.

   A calibração fica salva no telefone. Se você reposicionar o aparelho, refaça.

5. **`Iniciar sesión`.** A tela fica acesa via Wake Lock, os contadores ao vivo
   sobem e a cada 60 segundos um registro é gravado no IndexedDB local.

6. **`Exportar JSONL`** quando quiser. Copie o arquivo para
   `data/ventana/raw/` neste repositório.

Dicas de campo: trave o foco e a exposição se o Chrome permitir; evite apontar
para um poste de luz que entre e saia de foco; e desligue a rotação automática.

## Do arquivo aos resultados

```bash
# 1. valida o esquema e aplica as comportas de qualidade
python scripts/ventana/validate_session.py data/ventana/raw/*.jsonl

# 2. constrói o pacote de resultados com IC por bootstrap
python scripts/ventana/build_ventana_exhibits.py \
    --input data/ventana/raw \
    --output data/ventana/exhibits/ventana_exhibits.json

# 3. abra o painel
python -m http.server 8899
# http://localhost:8899/projects/ventana_observatory/dashboard/index.html
```

O painel só lê o pacote de resultados; ele não recalcula nada. Qualquer número
mostrado ali já existe no JSON, com a semente que o produziu.

## Sem o telefone ainda

Dá para exercitar o pipeline inteiro hoje, com dados sintéticos gerados por uma
semente fixa:

```bash
python scripts/ventana/simulate_session.py --days 3
python scripts/ventana/build_ventana_exhibits.py \
    --input data/ventana/synthetic \
    --output data/ventana/exhibits/ventana_exhibits_synthetic.json
```

Os arquivos sintéticos carregam a etiqueta `SINTÉTICO — no es observación` na
cabeçalho e nunca devem ser misturados com observação real.

## O que este observatório *não* afirma

O protocolo declara um teto de afirmação que sobe com a cobertura, e o painel o
mostra em destaque. Com poucos dias, os dados descrevem **aquelas datas** e nada
mais. Um perfil semanal exige pelo menos sete dias locais; sazonalidade, muito
mais. O sistema conta objetos que atravessam uma linha — ele não sabe se um
objeto é carro, ônibus ou pessoa. O porte é um proxy de área em pixels, e o
histograma de áreas cruas vai em cada minuto justamente para que os limiares
possam ser recalibrados depois sem refilmar.

## Privacidade

A resolução de análise é 320×180. Nessa escala uma pessoa ocupa poucos pixels e
não há reconhecimento de nada — nem rosto, nem placa, nem identidade. Ainda
assim: aponte para a via pública, não para a janela do vizinho. O único dado que
sai do telefone é a linha numérica por minuto, e só quando você exporta.

## Mapa dos arquivos

```
projects/ventana_observatory/
  capture/          PWA que roda no Pixel (engine.js é o motor de visão)
  dashboard/        painel estático que lê o pacote de resultados
  PROTOCOLO_VENTANA_V1.md   pré-registro: comportas, limiares e teto de afirmação
  SCHEMA_VENTANA_V1.md      esquema dos registros
ventana/            camada de análise em Python (esquema, comportas, agregação)
scripts/ventana/    validação, construção de resultados e gerador sintético
tests/test_ventana.py         testes da camada Python
tests/ventana_engine.test.mjs testes do motor de visão (node --test)
```
