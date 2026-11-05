# Defectos sembrados (plan §10, F5-04 a F5-09)

Cada defecto se siembra con `auditoria/scripts/defecto-sembrado.py <ID>`, que (1) corre la prueba SIN el defecto y exige verde, (2) lo siembra, (3) corre la misma prueba y exige rojo, y (4) **restaura el archivo byte a byte** y lo comprueba, también si algo falla (`finally`). Se hace en el árbol de trabajo y no en un `git worktree` porque la restauración verificada es equivalente y evita copiar `.venv` y el estado de Docker; el árbol queda sin cambios (`git status` limpio después de cada corrida).

| # | Defecto sembrado | ID | Archivo | Detectado por | Evidencia |
|---|---|---|---|---|---|
| 1 | SQL por f-string con entrada del usuario | `F5-sql-fstring` | `persistencia/repositorios.py` | `ruff` con la regla `S608` (compuerta de la CI y del gancho G0) | `controles-positivos/F5-F5-sql-fstring` |
| 2 | Quitar el `REVOKE` de solo inserción | `BD-sin-revoke` | migración 0004 | `test_BD_las_tablas_de_solo_insercion…` y `test_RD_02_…` | `controles-positivos/F3-BD-sin-revoke` |
| 3 | Apagar el disparador de inmutabilidad | `BD-sin-disparador` | migración 0002 | `test_RF_14_…` y `test_BD_los_disparadores_…` | `controles-positivos/F3-BD-sin-disparador` |
| 4 | Quitar la comprobación de rol técnico | `F5-sin-decorador-de-rol` | `casos/consultas.py` | matriz de autorización: celdas de `dashboard`, `cuentas` y `ficha` | `controles-positivos/F5-F5-sin-decorador-de-rol` |
| 5 | Aceptar el `.pdf` renombrado (sin comprobar la firma) | `U02-sin-firma` | `dominio/soporte.py` | `tests/seguridad/test_soporte.py` | `controles-positivos/F3-U02` |
| 6 | Permitir el segundo uso del desafío de TOTP | `U01-segundo-uso` | `identidad/supabase.py` | `tests/seguridad/test_segundo_factor.py` | `controles-positivos/F3-U01` |

Defectos adicionales de la misma técnica: `BD-sin-rls` (B-23), `U04-filtro-roto` (filtro de logs), `U05-sin-bloqueo` (decisiones simultáneas).

**Una lección de la siembra.** El primer intento del defecto 4 (quitar el rol RRHH de `PendientesDeAprobacion`) **no** fue detectado: la vista `bandeja` llama a dos casos de uso y el segundo (`ContratosPorVencer`) repite la comprobación. Es defensa en profundidad real, pero también significa que la matriz no distingue cuál de las dos comprobaciones faltó. Se sembró entonces en la comprobación única del dashboard.
