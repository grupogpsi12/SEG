# Probar Supabase a mano (base de datos y Auth)

Guía de laboratorio para verificar, contra el **Supabase real** del proyecto, los controles de
seguridad que el sistema exige: permisos mínimos, inmutabilidad, RLS, el esquema `app` no expuesto
por la Data API, y el inicio de sesión con TOTP. Es el complemento manual de las pruebas
automatizadas (`tests/integracion/test_postgresql.py` y `test_supabase_auth.py`), para que puedas
ver cada control con tus propias manos.

> Proyecto de **desarrollo**, datos ficticios. Es tu propio backend: pruebas autorizadas. No apuntes
> estos comandos a un proyecto que no sea tuyo.

## Reglas del laboratorio (leer antes de empezar)

- **Nunca dos corridas a la vez** contra la base: comparten el esquema y la segunda se cuelga en
  bloqueos hasta el `statement timeout` (lecciones 34 y 35). Trabaja de a una.
- Si la red corta una sesión a mitad, puede quedar «idle in transaction»; el servidor la corta al
  minuto. Si se repite, termínala como `postgres` (`pg_terminate_backend`).
- **No pegues secretos en el chat ni los subas al repo.** Viven en `secrets/` (ignorado por git).
- El plan gratuito **se pausa a la semana** sin actividad y no tiene respaldos: no guardes nada que
  no puedas recrear con `migrate` + `semillas`.

## 0. Qué necesitas

| Dato | De dónde sale |
|---|---|
| Ref del proyecto `<ref>` | El subdominio de `JML_SUPABASE_URL` en `infra/.env` (`https://<ref>.supabase.co`) |
| Clave publicable `sb_publishable_…` | `infra/.env` (`JML_SUPABASE_CLAVE_PUBLICA`). Es **pública** por diseño |
| Contraseña de `app_backend` | `secrets/db_password` (ya existe) |
| Contraseña de `app_owner` | `secrets/db_owner_password` (ya existe) |
| Certificado CA de Supabase | **Falta**: Dashboard → Project Settings → Database → SSL → *Download certificate* → guardar en `secrets/supabase_ca_crt` |
| Clave secreta `service_role` | **Falta** (solo para el flujo completo de Auth): Dashboard → Project Settings → API Keys → clave secreta → guardar en `secrets/supabase_service_role` |

En Git Bash (Windows), define una vez por terminal:

```bash
REF=$(grep JML_SUPABASE_URL infra/.env | sed -E 's#.*//([^.]+)\..*#\1#')
URL="https://$REF.supabase.co"
CLAVE=$(grep JML_SUPABASE_CLAVE_PUBLICA infra/.env | cut -d= -f2)
PSQL="/c/Program Files/PostgreSQL/18/bin/psql"
HOST=aws-0-us-east-1.pooler.supabase.com      # session pooler (IPv4); el host directo es solo IPv6
echo "ref=$REF  url=$URL"
```

## 1. Conectarse a la base (session pooler, TLS)

El usuario de conexión lleva el ref como sufijo: `app_backend.<ref>`. Con el certificado CA
descargado, usa `verify-full` (lo que hace la aplicación); sin él, `require` cifra pero no valida.

```bash
# como app_backend (el rol de la aplicación: permisos mínimos)
PGSSLMODE=verify-full PGSSLROOTCERT=secrets/supabase_ca_crt \
PGPASSWORD="$(cat secrets/db_password)" \
"$PSQL" "host=$HOST port=5432 dbname=postgres user=app_backend.$REF" -c "select current_user, version();"
```

Si todavía no bajaste el CA, cambia a `PGSSLMODE=require` y quita `PGSSLROOTCERT` para una primera
conexión. Para las pruebas de dueño necesitarás también `app_owner.<ref>` con
`secrets/db_owner_password`.

## 2. Pruebas de la base de datos

Cada bloque dice qué control verifica, el comando y **qué debes ver**. Define un atajo para no
repetir la conexión de `app_backend`:

```bash
BK() { PGSSLMODE=require PGPASSWORD="$(cat secrets/db_password)" \
  "$PSQL" "host=$HOST port=5432 dbname=postgres user=app_backend.$REF" "$@"; }
OW() { PGSSLMODE=require PGPASSWORD="$(cat secrets/db_owner_password)" \
  "$PSQL" "host=$HOST port=5432 dbname=postgres user=app_owner.$REF" "$@"; }
```

### A. Roles y dueño separado (ADR-028 / invariante 8)

```bash
BK -c "select rolname, rolsuper, rolbypassrls, rolcanlogin
       from pg_roles where rolname in ('app_backend','app_owner','anon','authenticated','service_role')
       order by 1;"
```
**Debes ver:** `app_backend` → super=f, bypassrls=t, login=t · `app_owner` → super=f, login=t ·
`anon`/`authenticated`/`service_role` → login=f. Ningún rol de la aplicación es superusuario.

```bash
BK -c "select tablename, tableowner from pg_tables where schemaname='app' order by 1 limit 5;"
```
**Debes ver:** el dueño es **`app_owner`**, no `app_backend` (corrección del hallazgo H1).

### B. RLS activo en todas las tablas (RD-10)

```bash
BK -c "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
       where n.nspname='app' and c.relkind='r' and not c.relrowsecurity
         and relname not like 'django_%' and relname not like 'auth_%';"
```
**Debes ver:** **cero filas** (todas las tablas de negocio tienen RLS).

### C. Auditoría de solo inserción (RD-02)

Como `app_backend`, intenta modificar las tablas que solo admiten INSERT:

```bash
BK -c "update app.auditoria set accion = accion;"      # esperado: ERROR permission denied
BK -c "delete from app.auditoria;"                      # esperado: ERROR permission denied
BK -c "truncate app.auditoria;"                         # esperado: ERROR permission denied
BK -c "insert into app.auditoria default values;" 2>&1 | head -1   # INSERT sí está permitido (fallará por columnas, no por permiso)
```
**Debes ver:** `permission denied for table auditoria` en los tres primeros. Repite con
`decision` y `cuenta_historial`.

### D. Inmutabilidad de una solicitud aprobada (RF-14, disparador)

Las semillas no dejan solicitudes aprobadas; si hiciste el recorrido de casos de uso hay varias en
`en_ejecucion` (que fueron aprobadas). Prueba el disparador **dentro de una transacción que
reviertes**, para no tocar los datos:

```bash
BK <<'SQL'
begin;
-- intenta cambiar el contenido de una solicitud ya aprobada/en ejecución
update app.solicitud set fecha_efectiva = fecha_efectiva + 1
  where estado in ('aprobada','en_ejecucion');
rollback;
SQL
```
**Debes ver:** `ERROR … RF-14 … inmutable` (lo lanza `app.app_solicitud_inmutable()`). El `rollback`
garantiza que no cambiaste nada. Una transición de estado válida (p. ej. a `en_ejecucion`) sí se
permite; lo que el disparador bloquea es editar el contenido de una aprobada y las transiciones
inválidas.

### E. Deduplicación concurrente (CA-01) — opcional

Es difícil de forzar a mano (hacen falta dos sesiones exactamente simultáneas). La cubre la prueba
automatizada `test_CA_01_...` con dos hilos y una barrera. Para una verificación simple de la
restricción, intenta dos inserciones del mismo `(colaborador, tipo)` abierto en sesiones distintas:
la segunda debe fallar por el índice único parcial.

## 3. Data API (REST): el esquema `app` no está expuesto (RD-10, T8)

Con la clave **publicable** (la que ve el navegador), ninguna tabla de la aplicación debe leerse,
ni por el esquema público ni pidiendo el esquema `app`:

```bash
# por el esquema public (por defecto): 404, la tabla no existe para la API
curl -s -o /dev/null -w "public  -> %{http_code}\n" \
  -H "apikey: $CLAVE" "$URL/rest/v1/solicitud?limit=1"

# pidiendo explícitamente el esquema app: error PGRST106 (Invalid schema)
curl -s -H "apikey: $CLAVE" -H "Accept-Profile: app" \
  "$URL/rest/v1/solicitud?limit=1" | grep -o '"code":"[^"]*"'
```
**Debes ver:** `public -> 404` y `"code":"PGRST106"`. Repite con `auditoria`,
`solicitud_restringida` y `colaborador`: ninguna responde datos.

## 4. Supabase Auth

### F. Registro abierto deshabilitado (RS-16)

```bash
curl -s -H "apikey: $CLAVE" "$URL/auth/v1/settings" | grep -o '"disable_signup":[a-z]*'
```
**Debes ver:** `"disable_signup":true`. Si da `false`, actívalo en el Dashboard
(Authentication → Sign In / Providers → *Allow new users to sign up* = off).

### G. Error de ingreso genérico (RS-08, T1)

El mismo error para un correo que no existe y para una contraseña incorrecta (no revela si el correo
existe):

```bash
# correo inexistente
curl -s -X POST "$URL/auth/v1/token?grant_type=password" -H "apikey: $CLAVE" \
  -H "Content-Type: application/json" \
  -d '{"email":"nadie-'"$RANDOM"'@andina.example","password":"contrasena-larga"}' \
  | grep -o '"error_code":"[^"]*"\|"error":"[^"]*"'
```
**Debes ver:** `invalid_credentials` (400), idéntico a cuando la contraseña es mala para un correo
real. El mensaje no distingue un caso del otro.

### H. Política de contraseña y MFA (RS-16)

- **Longitud mínima 12:** Dashboard → Authentication → Policies → *Minimum password length* = 12.
  Para comprobarlo con datos, al crear una cuenta con `service_role` (paso I) una clave de 11
  caracteres debe ser rechazada.
- **TOTP habilitado:** Dashboard → Authentication → Multi-Factor → TOTP activado (viene así por
  defecto). El flujo del paso I lo ejercita de punta a punta.

### I. Flujo completo contraseña → TOTP → AAL2 (necesita `service_role`)

Este flujo crea una cuenta de prueba, inscribe el TOTP, verifica y la borra. Necesita
`secrets/supabase_service_role`. La forma más segura y repetible es la prueba automatizada, que ya
calcula el código TOTP con RFC 6238:

```bash
# requiere secrets/supabase_service_role y secrets/supabase_ca_crt
JML_SUPABASE_URL="$URL" JML_SUPABASE_CLAVE_PUBLICA="$CLAVE" \
  .venv/Scripts/python.exe -m pytest -v \
  --ds tests.adaptadores.ajustes tests/integracion/test_supabase_auth.py -rs
```
**Debes ver:** `test_flujo_completo_contrasena_inscripcion_y_aal2 PASSED` (y los demás). Si falta el
`service_role`, ese caso aparece como `skipped` con el motivo S-28 (por eso el `-rs`: muestra los
omitidos). El `test_RS_16_...` falla en rojo si el registro abierto sigue activo — es la señal que
debes mirar.

Si quieres hacerlo a mano con `curl`, la secuencia de GoTrue es: `POST /auth/v1/token?grant_type=password`
(obtiene el `access_token` AAL1) → `POST /auth/v1/factors` con `{"factor_type":"totp"}` (devuelve
`totp.secret` y el `otpauth://…`) → cargas el secreto en tu app autenticadora →
`POST /auth/v1/factors/{id}/challenge` → `POST /auth/v1/factors/{id}/verify` con el código de 6
dígitos → la respuesta trae un token con `"aal":"aal2"`. Todas las llamadas llevan la cabecera
`Authorization: Bearer <access_token>` además de `apikey`.

## 5. Validación cruzada con la suite automatizada

Lo que probaste a mano, corrido de una vez (lee los secretos del repo). **No lo ejecutes al mismo
tiempo que las pruebas manuales** (lección 34):

```bash
export JML_PG_HOST=$HOST JML_PG_CA=secrets/supabase_ca_crt
export JML_PG_USUARIO=app_backend.$REF JML_PG_CLAVE="$(cat secrets/db_password)"
export JML_PG_DUENIO_USUARIO=app_owner.$REF JML_PG_DUENIO_CLAVE="$(cat secrets/db_owner_password)"
.venv/Scripts/python.exe -m pytest -v --ds tests.integracion.ajustes \
  tests/integracion/test_postgresql.py tests/integracion/test_revision_externa.py -rs
```
**Debes ver:** las 7 de `test_postgresql.py` (CA-01 concurrente, RF-14, RD-02 ×3, RD-10) en verde.

## 6. Checklist del Dashboard (RS-16, acciones manuales)

Estas no se automatizan; revísalas en el Dashboard y deja captura para el laboratorio:

- [ ] Authentication → Sign In → **Allow new users to sign up = off** (verificado en el paso F).
- [ ] Authentication → Policies → **Minimum password length = 12**.
- [ ] Authentication → Multi-Factor → **TOTP habilitado**.
- [ ] API Keys → existe una clave secreta y está solo en `secrets/supabase_service_role`.
- [ ] **Advisors → Security Advisor** → sin hallazgos (RS-16, CA-12). Deja captura.
- [ ] Rotar la contraseña de `postgres` al terminar (se compartió en una conversación).

## 7. Resumen de lo que estás demostrando

| Prueba | Propiedad | Requisito |
|---|---|---|
| A. Roles y dueño | Mínimo privilegio; dueño separado | ADR-028, inv. 8 |
| B. RLS en todas las tablas | Aislamiento de datos | RD-10 |
| C. Auditoría solo inserción | Integridad / no repudio | RD-02, T6 |
| D. Solicitud aprobada inmutable | Integridad | RF-14, T3 |
| F. Registro cerrado | Control de cuentas | RS-16, T15 |
| G. Error genérico | No enumeración de usuarios | RS-08, T1 |
| H/I. Contraseña + TOTP (AAL2) | Autenticación fuerte | RF-01/02, T1 |
| Data API cerrada (§3) | Confidencialidad | RD-10, T8 |
