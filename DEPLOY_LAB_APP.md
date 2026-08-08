# Publicar o laboratório (link público)

O app é estático e roda inteiramente no navegador: **não há servidor, não há
chave de API no frontend e não há custo por visita**.

O repositório traz `wrangler.jsonc` na raiz, configurado como *Worker de
assets estáticos* apontando para `web/dist`. É o formato atual da Cloudflare
(o painel novo cria Workers por padrão) e serve o site inteiro, incluindo o
laboratório em `/lab/`.

## Configuração na Cloudflare

No projeto (**Workers & Pages → synthetic-xi-2026 → Settings → Build**):

| Campo | Valor |
|---|---|
| Comando da build | `cd web && npm install && npm run build` |
| Comando de implantação | `npx wrangler deploy` |
| Diretório raiz | `/` |
| Branch de produção | `main` |

O campo que costuma vir vazio é o **comando da build** — sem ele o Vite nunca
compila, o `wrangler` publica um Worker vazio e a página abre em branco.

Depois de salvar, **Retry deployment** (ou um novo push em `main`) publica o
site. O laboratório fica em `https://<worker>.workers.dev/lab/`.

### Preview por branch (recomendado)

Em **Settings → Build → Branch control**, habilitar builds de branches que não
são produção: cada branch/PR recebe a sua própria URL de preview, permitindo
revisar antes de publicar.

### Domínio próprio (opcional)

**Settings → Domains & Routes → Add** → por exemplo `lab.seudominio.com`.
Se o domínio já estiver na Cloudflare, o DNS é criado automaticamente.

### Analytics sem cookies (opcional)

**Web Analytics → Enable**: a Cloudflare injeta o script sozinha, sem alterar
o código e sem exigir banner de consentimento.

## Alternativa: projeto Pages clássico

Também funciona criar um projeto **Pages** (Create application → Pages →
Connect to Git) com Root directory `web`, Build command `npm run build` e
Output directory `dist`. Nesse formato o `wrangler.jsonc` é ignorado.

## O que já está resolvido no repositório

- `wrangler.jsonc`: Worker de assets apontando para `web/dist`.
- `web/public/_headers`: cache imutável de um ano para `/lab/py/*` e
  `/lab/data/*` (motor e elencos versionados), HTML sempre revalidado,
  `X-Content-Type-Options` e `Referrer-Policy`.
- Meta tags Open Graph/Twitter e capa `og-cover.png` (1200×630).
- Aviso de primeira carga e **fallback amigável** quando a CDN do Pyodide
  está bloqueada (redes corporativas), com botão de repetir.
- Padrão de 200 simulações em telas pequenas.
- Versão do Pyodide fixada (`v0.26.2`) — nunca `latest` em produção.

## Pesos reais

| Item | Tamanho |
|---|---|
| `web/dist` completo | 4,4 MB |
| `teams.json` (44 seleções) | 2,3 MB → **260 KB** com gzip |
| Motor Pyodide + numpy | ~10–15 MB, da CDN pública, cacheado pelo navegador |

Segunda visita carrega praticamente do cache.
