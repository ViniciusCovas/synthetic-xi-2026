# Synthetic XI 2026 Lab

Laboratorio científico reproducible para construir avatares sintéticos por posición con datos acumulados de la Copa Mundial de 2026 y compararlos con los mejores futbolistas reales del mismo corte.

## Dos estudios

### Estudio 1 — Avatares posicionales vs élite individual

Compara ocho avatares (`GK`, `CB`, `FB`, `DM`, `CM`, `AM`, `W`, `ST`) con el jugador real número 1 de cada posición. El avatar principal es el centroide robusto de los **Top 20** elegibles.

### Estudio 2 — Synthetic XI vs Real Best XI

Construye dos equipos de once integrantes:

- **Synthetic XI:** 1 GK, 2 CB, 2 FB, 1 DM, 1 CM, 1 AM, 2 W y 1 ST.
- **Real Best XI:** los mejores jugadores reales necesarios para cubrir esas mismas once plazas.

El segundo estudio reutiliza los perfiles del primero y añade un motor de simulación por eventos. No confunde una comparación estadística con un partido físico real.

## Alcance temporal

La Copa de 2026 está en curso. Cada salida es un snapshot acumulado con fecha de corte, partidos incluidos, versión del método, semilla, tamaño solicitado y tamaño real de cada muestra.

## Decisiones pre-registradas

- Top 20 como análisis principal.
- Top 10 y Top 30 como sensibilidad.
- Mínimo de 180 minutos.
- Retracción hacia la media de la posición con prior de 180 minutos.
- Media recortada al 10% para construir cada avatar.
- La calificación opaca del proveedor no entra en el ranking.
- Ningún jugador se mezcla entre posiciones.
- Si no existen 20 elegibles, se informa el N real.

## Arquitectura

```text
API-FOOTBALL (clave privada)
          ↓
GitHub Actions (cálculo y pruebas)
          ↓
Snapshots CSV/JSON fechados
          ↓
Vite + Cloudflare Pages
```

## Ejecución local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export API_FOOTBALL_KEY="tu_clave"
python scripts/refresh_2026.py --cutoff-utc 2026-07-18T05:59:59Z

cd web
npm install
npm run dev
```

## Acción necesaria del propietario

1. Crear en GitHub el repositorio `synthetic-xi-2026` con README.
2. Añadir el secret `API_FOOTBALL_KEY` en `Settings → Secrets and variables → Actions`.
3. Cuando los datos reales estén validados, conectar el repositorio a Cloudflare Pages con raíz `web`, comando `npm run build` y salida `dist`.

## Documentos del estudio

- `METHODS.md`: metodología consolidada.
- `PRERREGISTRO.md`: decisiones fijadas antes de observar resultados.
- `ESTUDIO_1_POSICIONES.md`: borrador del primer artículo.
- `ESTUDIO_2_ONCE.md`: protocolo del segundo artículo.
