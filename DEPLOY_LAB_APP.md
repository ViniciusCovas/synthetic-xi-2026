# Publicar o laboratório (link público)

O app é estático e roda inteiramente no navegador: **não há servidor, não há
chave de API no frontend e não há custo por visita**. Qualquer host estático
serve; o repositório já está preparado para Cloudflare Pages.

## O que fazer no Cloudflare (uma vez)

1. Entrar em <https://dash.cloudflare.com> → **Workers & Pages** →
   **Create application** → **Pages** → **Connect to Git**.
2. Autorizar o GitHub e escolher `ViniciusCovas/synthetic-xi-2026`.
3. Configurar a build:
   - **Production branch**: `main`
   - **Root directory**: `web`
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
   - Framework preset: `None` (ou Vite)
4. **Save and Deploy**. Ao terminar, o site fica em
   `https://<nome-do-projeto>.pages.dev` e o laboratório em
   `https://<nome-do-projeto>.pages.dev/lab/`.

### Preview por branch (recomendado)

Em **Settings → Builds & deployments → Preview deployments**, deixar
"All non-Production branches". Cada branch/PR passa a receber a sua própria
URL — dá para revisar antes de publicar em produção.

### Domínio próprio (opcional)

**Custom domains → Set up a domain** → por exemplo `lab.seudominio.com`.
Se o domínio já estiver na Cloudflare, o DNS é criado automaticamente; caso
contrário, basta apontar um CNAME para `<projeto>.pages.dev`.

### Analytics sem cookies (opcional)

Em **Settings → Web Analytics → Enable**, a Cloudflare injeta o script
sozinha, sem alterar o código e sem exigir banner de consentimento.

## O que já está resolvido no repositório

- `web/public/_headers`: cache imutável de um ano para `/lab/py/*` e
  `/lab/data/*` (motor e elencos versionados), HTML sempre revalidado,
  `X-Content-Type-Options` e `Referrer-Policy`.
- Meta tags Open Graph/Twitter e capa `og-cover.png` (1200×630) para o link
  ficar apresentável quando compartilhado.
- Aviso claro de primeira carga e **fallback amigável** quando a CDN do
  Pyodide está bloqueada (redes corporativas), com botão de repetir.
- Padrão de 200 simulações em telas pequenas (o motor roda no aparelho).
- Versão do Pyodide fixada (`v0.26.2`) — nunca `latest` em produção.

## Pesos reais

| Item | Tamanho |
|---|---|
| `dist` completo | 4,4 MB |
| `teams.json` (44 seleções) | 2,3 MB → **260 KB** com gzip |
| Motor Pyodide + numpy | ~10–15 MB, da CDN pública, cacheado pelo navegador |

Segunda visita carrega praticamente do cache.

## Alternativas equivalentes

GitHub Pages (exige um workflow de build do Vite), Vercel ou Netlify servem
igualmente bem. A escolha do Cloudflare é apenas por já estar documentada em
`CLOUDFLARE.md`.
