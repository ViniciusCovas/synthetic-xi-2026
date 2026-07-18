# Publicación en Cloudflare Pages

La interfaz es estática y no expone la clave de la API.

## Configuración

1. En Cloudflare, abrir **Workers & Pages**.
2. Elegir **Create application → Pages → Connect to Git**.
3. Seleccionar `ViniciusCovas/synthetic-xi-2026`.
4. Configurar:
   - Production branch: `main`
   - Root directory: `web`
   - Build command: `npm run build`
   - Build output directory: `dist`
5. Desplegar.

No se necesita Worker en esta fase. GitHub Actions procesa los datos y Cloudflare sirve los JSON y la interfaz.
