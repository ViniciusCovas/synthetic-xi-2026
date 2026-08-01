# Addendum 01 — Sustitución de emergencia dentro del plantel congelado

**Fecha:** 2026-07-29  
**Estado:** corrección estructural previa a la validación confirmatoria y a la ejecución oficial de 10.000 finales.

## Motivo

El smoke test detectó un estado válido del partido en el que un equipo había agotado todos los suplentes exactos para el slot `W2` después de sustituciones y una lesión. El motor anterior abortaba aunque todavía existían futbolistas no utilizados dentro del plantel congelado de 26 integrantes.

Este hallazgo es de reglas y disponibilidad, no de dirección del resultado. No se observó ni utilizó una distribución oficial confirmatoria para definir la corrección.

## Política congelada

1. Siempre se utiliza primero un suplente exacto compatible con el slot.
2. Si todos los suplentes exactos no utilizados están agotados, se permite cobertura de emergencia con otro integrante **no utilizado** del mismo plantel congelado de 26.
3. No se crea una identidad sintética adicional, no se clona al futbolista sustituido y ningún jugador puede entrar dos veces.
4. La cobertura de emergencia no se aplica a `GK`; se respetan los porteros de emergencia congelados.
5. El futbolista fuera de rol recibe:
   - multiplicador de habilidad `0.90` en todas las dimensiones normalizadas;
   - incremento de incertidumbre `+0.03`, con máximo `0.30`.
6. La elección es determinística: primero la posición más próxima en la matriz congelada y después el mayor score conservador.

## Matriz de proximidad

- `CB1`: CB2, FB1, FB2, DM
- `CB2`: CB1, FB2, FB1, DM
- `FB1`: FB2, W1, CB1, DM, CM
- `FB2`: FB1, W2, CB2, DM, CM
- `DM`: CM, CB1, CB2, AM, FB1, FB2
- `CM`: DM, AM, W1, W2, FB1, FB2
- `AM`: CM, W1, W2, ST, DM
- `W1`: W2, AM, ST, FB1, CM
- `W2`: W1, AM, ST, FB2, CM
- `ST`: W1, W2, AM, CM

## Auditoría

Cada entrada continúa registrando el ID real o sintético congelado, el slot de entrada, el jugador sustituido y el minuto. Los gates de integridad siguen exigiendo que todo suplente pertenezca al plantel registrado y que ningún ID sea reutilizado.

## Límite

Esta política resuelve disponibilidad de banquillo; no estima versatilidad individual ni química táctica. La penalización fuera de rol es un supuesto declarado y puede someterse a sensibilidad, pero no ajustarse después de observar el resultado oficial.
