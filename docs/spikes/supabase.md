# Spikes 0.2 y 0.4 — Supabase (base de datos y Auth)

Proyecto de **desarrollo**: ref `tzxziubxwzgqdbmfkdiq` (`https://tzxziubxwzgqdbmfkdiq.supabase.co`), región `us-east-1`, plan gratuito. El proyecto de **entrega** se aprovisiona con los mismos pasos (pendiente).

Ningún secreto está en este documento ni en el repositorio. Los secretos locales viven en `secrets/` (ignorado por git) y en Azure en Key Vault → `/run/secrets` (ADR-009).

| Secreto (`secrets/<nombre>`) | Qué es | Quién lo monta |
|---|---|---|
| `db_password` | Contraseña de `app_backend` (aleatoria, 48 caracteres) | web, worker, admin-usuarios |
| `supabase_ca_crt` | CA de Supabase para `sslmode=verify-full` (Dashboard → Database → SSL) | web, worker, admin-usuarios |
| `django_secret_key` | Clave de Django | web, worker, admin-usuarios |
| `supabase_service_role` | Clave secreta `sb_secret_…` (Dashboard → API Keys) | **solo** admin-usuarios (invariante 8). **Pendiente: el equipo debe crearla localmente.** |
| `db_owner_password` | Contraseña de `app_owner`, dueño del esquema (ADR-028) | **solo** `migrar` |

Variables de entorno no secretas: `JML_DB_HOST=aws-0-us-east-1.pooler.supabase.com`, `JML_DB_USUARIO=app_backend.tzxziubxwzgqdbmfkdiq`, `JML_SUPABASE_URL=https://tzxziubxwzgqdbmfkdiq.supabase.co`, `JML_SUPABASE_CLAVE_PUBLICA=sb_publishable_…` (la clave publicable es pública por diseño: el esquema `app` no está expuesto).

## 0.2 — Base de datos (hecho el 10/10/2026)

**Hallazgos**
- PostgreSQL **17.11** → la imagen de pruebas en contenedor debe ser `postgres:17`.
- El host directo `db.<ref>.supabase.co` solo tiene IPv6; desde redes IPv4 (y Azure por defecto) se usa el **session pooler** `aws-0-us-east-1.pooler.supabase.com:5432`, con el usuario `app_backend.<ref>`. Admite *prepared statements* (lessons n.º 9).
- `app_backend` no puede crear bases ni esquemas (mínimo privilegio): las pruebas de integración usan el esquema `app_test`, creado una vez por el administrador.

**Aprovisionamiento (como `postgres`, una sola vez; la contraseña de `postgres` no se guarda)**

```sql
create role app_backend login nosuperuser nocreatedb nocreaterole noinherit nobypassrls
  connection limit 20 password '<aleatoria → secrets/db_password>';
grant app_backend to postgres;               -- para crear objetos a su nombre
create schema app authorization app_backend;
revoke all on schema app from public, anon, authenticated, service_role;
alter role app_backend set search_path = app;
alter role app_backend set statement_timeout = '30s';
alter default privileges for role app_backend in schema app
  revoke all on tables from anon, authenticated, service_role;
-- esquema de pruebas de integración (mismo trato)
create schema app_test authorization app_backend;
revoke all on schema app_test from public, anon, authenticated, service_role;
```

Después: `python manage.py migrate` (corre como `app_backend`, dueño de las tablas). La migración `0002` aplica el disparador de inmutabilidad (RF-14), el `REVOKE` de UPDATE/DELETE/TRUNCATE sobre `auditoria`, `decision` y `cuenta_historial` (RD-02) y RLS sin políticas en todas las tablas (RD-10).

**Evidencia**: `tests/integracion/test_postgresql.py` 7/7 contra Supabase (disparador, REVOKE, duplicado concurrente CA-01, auditoría CA-09, RLS). Comando:

```bash
JML_PG_HOST=aws-0-us-east-1.pooler.supabase.com JML_PG_USUARIO=app_backend.<ref> \
JML_PG_CLAVE="$(cat secrets/db_password)" JML_PG_CA=secrets/supabase_ca_crt \
  pytest --ds tests.integracion.ajustes tests/integracion
```

**Cuidado:** nunca correr dos sesiones de pruebas contra `app_test` a la vez (comparten esquema; la segunda se queda esperando bloqueos y falla con `statement timeout`). Si la red corta una corrida, su transacción queda huérfana: desde el 11/10/2026 la conexión lleva `idle_in_transaction_session_timeout=60000`, así que el servidor la corta al minuto (lecciones 34 y 35).

**Pendiente de 0.2**: `pg_dump`/`pg_restore` contra un proyecto vacío; comprobar que la petición `/rest/v1/<tabla>` con la clave publicable falla; procedimiento de reactivación si el proyecto se pausa.

## 0.4 — Supabase Auth con TOTP desde el servidor (11/10/2026)

**Decisión de implementación**: API REST de GoTrue con `httpx` (sin `supabase-py`): son 7 llamadas y así no entra una dependencia más.

| Paso | Llamada | Notas |
|---|---|---|
| Contraseña | `POST /auth/v1/token?grant_type=password` | 400 para correo desconocido y para clave mala: idéntico (RS-08) |
| Factores del usuario | `user.factors` en la respuesta anterior; `GET /auth/v1/user` | `factor_type=totp`, `status=verified/unverified` |
| Limpiar inscripciones abandonadas | `DELETE /auth/v1/factors/{id}` | Supabase limita la cantidad de factores |
| Inscribir | `POST /auth/v1/factors` `{factor_type: totp, issuer}` | Devuelve `totp.uri` (`otpauth://…?secret=…`). Con AAL1 Supabase **no** deja inscribir si ya hay uno verificado; el adaptador además lo niega antes (T1) |
| Desafío | `POST /auth/v1/factors/{id}/challenge` | |
| Verificar | `POST /auth/v1/factors/{id}/verify` `{challenge_id, code}` | Devuelve un token con `aal: aal2`; el adaptador comprueba `aal` y `sub` |
| Cerrar | `POST /auth/v1/logout?scope=local` | La sesión de Supabase no se usa; se cierra |
| Admin (solo `admin-usuarios`) | `POST/PUT/DELETE /auth/v1/admin/users` | Crear confirmado, banear (`ban_duration`), borrar (compensación) |

**Dónde vive el token AAL1** (S-29): solo en la memoria del proceso web, 5 minutos, 5 intentos. Por eso la web corre con **un** proceso de gunicorn con hilos (`--workers 1 --threads 8`).

**Evidencia**
- `tests/contratos` (fábrica `orm`): la suite de contrato del puerto pasa con el adaptador real contra un GoTrue simulado (`tests/dobles/gotrue.py`).
- `tests/adaptadores/test_identidad_supabase.py`, `test_ingreso_web.py`, `test_admin_usuarios.py`.
- Contra el Supabase real (`tests/integracion/test_supabase_auth.py`): error genérico ✔; vector RFC 6238 ✔; **registro abierto: FALLA** (ver abajo); flujo completo omitido (S-28) hasta tener `supabase_service_role`.

**Acciones pendientes del equipo en el Dashboard de Supabase (RS-16)**
1. Authentication → Sign In / Providers → desactivar **Allow new users to sign up** (hoy `disable_signup: false`).
2. Authentication → Policies (Passwords) → longitud mínima **12**.
3. Authentication → Multi-Factor → TOTP **habilitado** (viene así por defecto; confirmar).
4. API Keys → crear una clave secreta y guardarla en `secrets/supabase_service_role`; luego correr `tests/integracion/test_supabase_auth.py` completo.
5. Rotar la contraseña de `postgres` (se compartió en una conversación) al terminar el desarrollo.
6. Correr el asesor de seguridad de Supabase sin hallazgos antes de la entrega (RS-16, CA-12).

## Dueño separado (ADR-028, revisión externa H1) — aplicado el 11/10/2026

`app_backend` ya **no** es dueño. Desde el 11/10/2026 en el proyecto de desarrollo:
- `app_owner` (LOGIN, `connection limit 3`, clave en `secrets/db_owner_password`) es dueño de `app` y `app_test` y de su contenido; corre `migrate`.
- `app_backend` tiene `BYPASSRLS` (RLS sigue sin políticas: invariante 8), `USAGE` en los esquemas y DML por tabla (migración 0004), sin `CREATE` ni permisos sobre las tablas de solo inserción.
- Script idempotente: `infra/supabase/duenio-separado.sql` (como `postgres`). Hay que correrlo también en el proyecto de entrega, **antes** de la primera migración.
- Pruebas de integración: `JML_PG_DUENIO_USUARIO=app_owner.<ref>` y `JML_PG_DUENIO_CLAVE="$(cat secrets/db_owner_password)"` además de las variables de `app_backend`.
- El esquema `app` de producción **todavía no tiene tablas**: la primera `migrate` real se hace con el contenedor `migrar`.

Observación pendiente de explicar: una sesión de `app_backend` quedó «idle in transaction» 8 minutos pese a `idle_in_transaction_session_timeout=60000`; quizá el pooler no aplica esa opción. Si se repite, terminarla como `postgres` (`pg_terminate_backend`) o pedir el ajuste por rol (`ALTER ROLE app_backend SET idle_in_transaction_session_timeout = '60s'`, que requiere `postgres`).
