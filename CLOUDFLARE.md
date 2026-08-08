# Publicación en Cloudflare

> **Actualización:** el panel actual de Cloudflare crea *Workers* por defecto.
> El repositorio incluye `wrangler.jsonc` en la raíz (Worker de assets
> estáticos que sirve `web/dist`). La guía operativa vigente, con los comandos
> de build exactos, está en `DEPLOY_LAB_APP.md`. Lo de abajo describe el
> formato Pages clásico, que sigue funcionando.

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
