# Evidencia de RNF-06 — rendimiento con 300 colaboradores y 20 usuarios concurrentes

Para quién: el equipo y quien evalúe el proyecto (ítem 4.1, CA-15). **Fecha:** 24/10/2026.

**Requisito (RNF-06).** El p95 de las páginas debe ser menor a 800 ms y el del dashboard menor a 2 s, con 300 colaboradores y 20 usuarios concurrentes.

**Resultado.** Cumple en todas las páginas, después de corregir lo que encontró la primera medición.

## Cómo se midió

```bash
VUELTAS=20 infra/scripts/carga.sh     # reproducible; todo desechable
```

- **Entorno desechable** en una red propia:
  - un PostgreSQL 17 con los mismos roles que Supabase (`infra/local/initdb/01-roles.sh` y ADR-028);
  - la **imagen de la aplicación con su configuración de producción**: gunicorn con 1 proceso y 8 hilos (S-29), límite de 512 MiB.

  No toca la base ni el GLPI del stack.
- **Semilla** (`tests/carga/sembrar.py`), con los casos de uso reales:
  - 300 ingresos, dos tercios ya resueltos por TI;
  - 60 vacaciones, 30 retiros y 6 emergencias.

  En total, 6586 registros de auditoría con la cadena válida.
- **Carga** (`tests/carga/medir.py`): 20 hilos, cada uno con su sesión.
  - Reparto: 10 técnicos, 6 de RRHH y 4 auditores.
  - Todos arrancan a la vez y encadenan peticiones **sin pausa**, que es más exigente que 20 personas reales.
  - Se mide contra `web` directo, sin el WAF: su límite es de 2 peticiones por segundo **por IP** (RS-08) y frenaría a un generador que sale de una sola IP. Veinte personas reales usan veinte IP.
- **Equipo:** el portátil de desarrollo (Windows 11 y Docker Desktop). Ver «Límites» abajo.

## Resultados (20 usuarios, 1440 peticiones en 40,6 s, sin errores)

| Página | Peticiones | p50 (ms) | p95 (ms) | Máx (ms) | Umbral (ms) | Cumple |
|---|---|---|---|---|---|---|
| Dashboard | 200 | 547 | **791** | 1002 | 2000 | sí |
| Cuentas | 200 | 407 | 596 | 774 | 800 | sí |
| Cuentas filtradas | 200 | 387 | 504 | 557 | 800 | sí |
| Cuentas, página 3 | 200 | 354 | 469 | 516 | 800 | sí |
| Ficha del colaborador | 200 | 340 | 459 | 513 | 800 | sí |
| Mis solicitudes (RRHH) | 120 | 387 | 589 | 832 | 800 | sí |
| Bandeja de RRHH | 120 | 453 | 594 | 670 | 800 | sí |
| Detalle de solicitud | 120 | 400 | 622 | 706 | 800 | sí |
| Auditoría | 80 | 481 | 620 | 678 | 800 | sí |

## Qué encontró la primera medición y cómo se corrigió

Primera medición: 720 peticiones en 66,8 s, con 8 de 9 páginas fuera del umbral. «Mis solicitudes» llegaba a un p95 de 5,7 s.

| Problema | Consultas por vista, antes → después | Corrección |
|---|---|---|
| «Mis solicitudes»: una consulta por fila para el campo restringido y otra para el colaborador (N+1), y la lista entera sin paginar | 805 → 14 | `select_related` del campo restringido; caché de colaboradores por unidad de trabajo, precargada con una consulta `IN`; paginación de 50 (ADR-030) |
| Búsqueda de cuentas: una consulta de cuentas por colaborador al filtrar | 339 → 16 | Todas las cuentas en una consulta |
| Auditoría: cargaba la cadena entera (6586 registros) para mostrar 50 | 6586 registros leídos → 50 | `Auditoria.total()` y `tramo()` (ADR-030) |

El resultado de las consultas no cambió: el oráculo en memoria (`test_persistencia_oraculo.py`) y las suites de contrato pasan igual, también contra PostgreSQL (`infra/scripts/integracion-local.sh`).

Con un solo usuario por rol, después de las correcciones, cada página tarda entre 8 y 84 ms (`tests/carga/perfilar.py`). Bajo carga, el resto del tiempo es la espera en el único proceso de gunicorn.

## Límites de esta evidencia

- **Equipo.** Se midió en el portátil, no en la VM de Azure B2s (2 vCPU). La VM tiene menos CPU que el portátil, pero la base (Supabase) estará en la misma región. **Repetir esta medición en Azure** (ítem 5.2).
- **Proceso único.** El techo es el único proceso de gunicorn (S-29: los desafíos TOTP viven en su memoria). Si en Azure no alcanza, la salida es separar `/ingreso` en su propio proceso y dar más procesos al resto. Eso requiere un ADR.
