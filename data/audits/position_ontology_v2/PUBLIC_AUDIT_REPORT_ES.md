# Auditoría pública de la ontología de posiciones v2

## Dictamen

La ontología anterior no puede promoverse como definitiva. Se reconstruyeron las posiciones desde formaciones y grids, se ponderaron por minutos observados, se deduplicaron identidades por `player_id` y se contrastaron jugadores de alto impacto con fuentes públicas versionadas.

- Jugadores del release actual con conflicto público: **14**.
- Conflictos formación–fuente pública: **4**.
- Cambios de rol en el rebuild diagnóstico: **723**.
- Gate automático: **no aprobado**.
- Nueva simulación final: **bloqueada hasta revisión humana ciega**.

## Conflictos de alto impacto todavía abiertos

| Jugador | Rol anterior | Rol por formación | Roles públicos | Rol auditado | Regla |
|---|---|---|---|---|---|
| D. Kamada | ST | AM | AM|CM | AM | formation_and_public_agree |
| D. Raum | RB | LB | LB | LB | formation_and_public_agree |
| E. Alvarez | RB | DM | DM|RCB | DM | formation_and_public_agree |
| E. Palacios | RB | RCB | CM|DM | CM | public_preferred_override |
| F. Bjorkan | RB | LB | LB | LB | formation_and_public_agree |
| J. Doku | CM | LW | RW|LW | LW | formation_and_public_agree |
| J. Hadjam | RB | LB | LB | LB | formation_and_public_agree |
| J. Musiala | ST | AM | AM|CM | AM | formation_and_public_agree |
| K. Mbappe | RW | ST | ST|LW | ST | formation_and_public_agree |
| K. Tierney | RB | LCB | LB | LB | public_preferred_override |
| L. Diaz | CM | AM | LW|ST | LW | public_preferred_override |
| L. Paredes | AM | DM | DM|CM | DM | formation_and_public_agree |
| M. Olise | CM | AM | RW|AM | AM | formation_and_public_agree |
| P. Ciss | RB | RCB | DM|CM | DM | public_preferred_override |

## Universo por rol

| Rol | Ontología anterior | Candidatos estables auditados | Top 20 completo |
|---|---:|---:|---|
| GK | 109 | 94 | sí |
| RB | 260 | 7 | no |
| RCB | 42 | 69 | sí |
| LCB | 25 | 74 | sí |
| LB | 45 | 10 | no |
| DM | 25 | 145 | sí |
| CM | 111 | 7 | no |
| AM | 155 | 22 | sí |
| RW | 258 | 2 | no |
| LW | 11 | 5 | no |
| ST | 19 | 42 | sí |

## Convergencia pública 2025/26

Los premios y noticias no determinan el ranking. Se utilizan como validación externa de plausibilidad: si un goleador reconocido desaparece de ST o un lateral aparece como CM, la ontología debe explicar la discrepancia.

| Jugador | Evidencia pública | Ranking diagnóstico |
|---|---|---|
| Harry Kane | European Golden Shoe and Bundesliga top scorer with 36 league goals in 2025-26 | #2 ST |
| Lautaro Martinez | Serie A 2025-26 Best Striker and league top scorer | #7 ST |
| Kylian Mbappe | La Liga 2025-26 Pichichi winner with 25 league goals | #1 ST |
| Ousmane Dembele | Onze d'Or 2025 after 35 goals and 16 assists in 53 matches | #4 ST |
| Michael Olise | Bundesliga 2025-26 Player of the Season | #1 AM |
| Achraf Hakimi | CAF African Player of the Year 2025 and publicly described as an elite right-back | #1 RB |

## Restricción científica

El Real XI y el Synthetic XI de esta auditoría son diagnósticos. Solo se volverá a simular después de una revisión ciega, matriz de confusión y promoción explícita de la ontología.
