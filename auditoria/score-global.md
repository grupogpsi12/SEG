# Puntajes DREAD y score global

Generado por `auditoria/scripts/score-global.py` desde `auditoria/hallazgos/` (33 hallazgos). Un residual solo baja si hay una prueba que se rompe al quitar el control (anclas: `dread-anclas.md`).

## Hallazgos ordenados por prioridad (DREAD × factor)

| ID | Severidad | Estado | DREAD inherente | Factor | Prioridad | DREAD residual |
|---|---|---|---|---|---|---|
| B-06 | Media | abierto — decisión del equipo (ADR) en F8 | 6,0 | ×1,0 | 6,0 | n/a |
| B-10 | Media | abierto — [PENDIENTE: acción humana en el Dashbo | 6,0 | ×1,0 | 6,0 | n/a |
| B-15 | Media | verificado (rojo→verde, evidencia B-15-ROJO / B- | 6,0 | ×1,0 | 6,0 | 2,0 |
| B-02 | Media | verificado | 5,4 | ×1,0 | 5,4 | 3,8 |
| B-17 | Media | verificado (rojo→verde, evidencia B-17-ROJO / F1 | 5,4 | ×1,0 | 5,4 | 2,4 |
| B-07 | Baja | abierto — pre-commit verificado (F2-10); protecc | 5,2 | ×1,0 | 5,2 | n/a |
| B-05 | Baja | verificado (U-06 en F3 y sqlmap nivel 5 con `Hos | 5,0 | ×1,0 | 5,0 | n/a |
| B-24 | Baja | verificado (rojo→verde, evidencia B-24-ROJO / B- | 5,0 | ×1,0 | 5,0 | 1,0 |
| B-31 | Media | aceptado con exención escrita (`exenciones-trivy | 4,8 | ×1,0 | 4,8 | 3,0 |
| B-16 | Media | verificado (rojo→verde, evidencia B-16-ROJO / B- | 4,2 | ×1,0 | 4,2 | 2,0 |
| B-20 | Media | verificado (rojo→verde, evidencia B-20-ROJO / B- | 4,2 | ×1,0 | 4,2 | 2,0 |
| B-19 | Media | verificado (rojo→verde, evidencia B-19-ROJO / B- | 4,0 | ×1,0 | 4,0 | 2,0 |
| B-25 | Media | verificado (rojo→verde: 118 celdas de la matriz  | 5,4 | ×0,7 (exige una sesión) | 3,8 | 1,8 |
| B-13 | Baja | verificado (cobertura de ramas de `seguridad:ing | 3,6 | ×1,0 | 3,6 | n/a |
| B-21 | Baja | verificado (rojo→verde, evidencia B-21-ROJO / B- | 3,4 | ×1,0 | 3,4 | 1,0 |
| B-18 | Baja | aceptado — sin parche en Debian 13,7; se revisa  | 3,0 | ×1,0 | 3,0 | 3,0 |
| B-27 | Baja | abierto — decisión del equipo: ADR-023 e invaria | 3,0 | ×1,0 | 3,0 | 3,0 |
| B-33 | Baja | abierto — endurecimiento de ejecución de contene | 3,0 | ×1,0 | 3,0 | 3,0 |
| B-22 | Informativa | aceptado — límite conocido de ADR-021 (sin antiv | 2,8 | ×1,0 | 2,8 | 2,8 |
| B-32 | Media | abierto — propuesta de ADR en F8-04 (red dedicad | 5,4 | ×0,5 (exige un contenedor comprometido en la red interna) | 2,7 | 5,4 |
| B-23 | Baja | corregido en el código (migración 0006); falta a | 2,6 | ×1,0 | 2,6 | 1,0 |
| B-01 | Media | verificado | 5,0 | ×0,5 (exige acceso al host) | 2,5 | 4,0 |
| B-29 | Informativa | abierto — corregir RS-19 y la descripción de la  | 5,0 | ×0,5 (exige la red interna) | 2,5 | 2,0 |
| B-28 | Baja | abierto — decisión del equipo (ASVS V9,1, V9,2 y | 3,6 | ×0,5 (exige interponerse en el tramo servidor→Supabase) | 1,8 | 3,6 |
| B-30 | Baja | abierto — propuesta de endurecimiento (ADR en F8 | 3,0 | ×0,5 (exige la red interna) | 1,5 | 1,8 |
| B-03 | Informativa | corregido (sin prueba automática viable) | n/a | ×1,0 | — | n/a |
| B-04 | Media | verificado (F6-02 con la exención registrada y F | n/a | ×1,0 | — | n/a |
| B-08 | Informativa | verificado (reglas S de ruff activas en toda la  | n/a | ×1,0 | — | n/a |
| B-09 | Baja | abierto — F8 | n/a | ×1,0 | — | n/a |
| B-11 | Media | verificado (matriz de 440 celdas y U-03 en F5; u | n/a | ×1,0 | — | 3,0 |
| B-12 | Informativa | abierto — F8 | n/a | ×1,0 | — | n/a |
| B-14 | Informativa | abierto — F8 | n/a | ×1,0 | — | n/a |
| B-26 | Baja | abierto — decisión del equipo: el Auditor no pue | n/a | ×0,7 (exige una sesión) | — | n/a |

## Score global

- Hallazgos que siguen en pie (abiertos o aceptados): **16** (Crítica: 0, Alta: 0, Media: 4, Baja: 8; informativos 4 no suman).
- Exposición ponderada: **16**.
- Controles verificados (ASVS L1/L2 en «verificado»): **144**.
- **Score global = 16 / (144 × 10) × 100 = 1,1** → aceptable (escala: 0–20 aceptable · 21–40 requiere mejoras · 41–60 deficiente · 61–80 crítica · 81–100 exposición crítica).

Se reporta junto al número de controles verificados: con 144 probados el score tiene sentido; con 10 no lo tendría.
