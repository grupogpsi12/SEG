# Revisión externa del 11/10/2026 y propuesta para H1 a H3

Revisión hecha por una persona del equipo sobre el commit `693f51c`, de solo lectura, con PostgreSQL 16 local. Este documento resume sus hallazgos, los verifica contra el código actual y propone cómo cerrarlos. **H1 a H3 tocan los invariantes 3, 4 y 8: según `CLAUDE.md` esperan una decisión N3 del equipo antes de implementarse.**

## Verificación contra el código actual (`b85ebe2`)

| # | Hallazgo | ¿Sigue vigente? | Evidencia |
|---|---|---|---|
| H1 | `app_backend` es dueño del esquema y las tablas: puede `GRANT UPDATE ON auditoria TO app_backend` y `ALTER TABLE … DISABLE TRIGGER` | **Sí** | Es así en PostgreSQL por diseño (el dueño conserva esos derechos). En Supabase, `app` y `app_test` son de `app_backend` (`docs/spikes/supabase.md`) |
| H2 | `app_solicitud_inmutable()` no valida el cambio de estado: pendiente → editar → cerrada pasa | **Sí** | `migrations/0002_reglas_de_postgresql.py`: solo compara contenido cuando `OLD.estado <> 'pendiente_aprobacion'` |
| H3 | Dos aprobaciones simultáneas se aceptan | **Sí** | `RepoSolicitudes.obtener` no usa `select_for_update`; lo usan decidir, cancelar y el worker |
| M1–M6 | Menores | Resueltos o justificados | `tasks/todo.md` 2.14 |

## Propuesta (para aprobar)

### H1 — Dueño separado (ADR-028 propuesto)
1. Rol nuevo `app_owner` (LOGIN, contraseña propia en `secrets/db_owner_password`), dueño del esquema `app` y de todo lo que contiene. **Solo lo usa un contenedor de una sola vez, `migrar`** (como `admin-usuarios` con `service_role`). Web y worker siguen con `app_backend`.
2. `app_backend` deja de ser dueño: `USAGE` en el esquema; `SELECT, INSERT, UPDATE, DELETE` por tabla; `USAGE` en las secuencias; **sin** `UPDATE`, `DELETE` ni `TRUNCATE` en `auditoria`, `decision` y `cuenta_historial`; sin `CREATE` en el esquema. Con `ALTER DEFAULT PRIVILEGES FOR ROLE app_owner`, las tablas nuevas heredan esos permisos.
3. Migración `0003`: la parte de permisos, que no hace nada en SQLite.
4. Aprovisionamiento en Supabase (una vez, como `postgres`): crear `app_owner`, `ALTER SCHEMA app OWNER TO app_owner`, reasignar las tablas (`REASSIGN OWNED BY app_backend TO app_owner` dentro del esquema) y lo mismo en `app_test`.
5. Pruebas nuevas en `tests/integracion`: `app_backend` no puede `GRANT`, `ALTER TABLE … DISABLE TRIGGER`, `UPDATE auditoria` ni `CREATE TABLE`. El arnés de pruebas migra con `app_owner` (un segundo alias de base de datos) y prueba con `app_backend`.
6. Anclaje del último hash fuera de la base: ya está previsto en RD-04 (exportación diaria a Blob inmutable, item 2.4/5.3). Se agrega a esa exportación el hash del último registro, para que reescribir la cadena entera sea detectable.

**Costo y riesgo:** un secreto más y un contenedor de una sola vez; hay que usar `postgres` una vez en Supabase (después se rota, como ya está previsto).

### H2 — El disparador valida transiciones
La función compara `(OLD.estado, NEW.estado)` contra la tabla de transiciones del dominio (`TRANSICIONES` en `dominio/solicitud.py`). Una prueba de Python comprueba que el conjunto escrito en SQL es **idéntico** al del dominio, para que no se separen. Como mínimo, rechaza volver a `pendiente_aprobacion` y cualquier cambio desde un estado final. Prueba nueva: el ataque de tres `UPDATE` de la revisión falla.

### H3 — Bloqueo al cargar para decidir
`RepoSolicitudes.obtener` del ORM hace `select_for_update()` dentro de la unidad de trabajo, que ya es atómica. El contrato del puerto no cambia y en SQLite no tiene efecto. Así la segunda aprobación espera y luego ve `aprobada`: el dominio la rechaza con `TransicionInvalida`. Pruebas concurrentes en PostgreSQL como la de CA-01: dos aprobadores, y aprobar contra cancelar. Cierra el R1 de `docs/spikes/revision-nucleo.md`.

## Orden propuesto
Primero H3 (no requiere roles nuevos), luego H2 y por último H1, que necesita una acción en Supabase. Cada uno empieza por la prueba que falla y va en su propio commit, citando su requisito.
