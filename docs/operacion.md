# Manual de operación

Para quién: el Administrador del sistema y quien despliegue u opere la plataforma. Supone conocer Docker. Desde ADR-031 todo corre en la máquina local con Docker Desktop: PostgreSQL 17 en contenedor, Supabase solo para Auth y sin exposición pública. Lo marcado **(sin verificar)** está escrito, pero todavía no se ha ejecutado (ver `docs/estado.md`).

## 1. Piezas y secretos

| Servicio | Qué hace | Secretos que monta (`/run/secrets`) |
|---|---|---|
| `bunkerweb` + `bw-scheduler` | WAF y proxy inverso; único con puertos (80/443) | (API_TOKEN por variable, desde `infra/.env`) |
| `web` | Aplicación Django (gunicorn: 1 proceso × 8 hilos, S-29) | `django_secret_key`, `db_password` |
| `worker` | Bandeja de salida a GLPI, sincronización cada 5 minutos, exportación diaria de auditoría | lo anterior + `glpi_app_token`, `glpi_user_token` |
| `migrar` (una sola vez) | `migrate` como `app_owner` (ADR-028) | `db_owner_password` (como `db_password`) |
| `admin-usuarios` (una sola vez) | Crear, vincular o desactivar cuentas (RF-06) | lo de `web` + `supabase_service_role` |
| `configurar-glpi` (una sola vez) | GLPI como código (3.1) | `glpi_app_token`, `glpi_admin_user_token` |
| `glpi` + `mariadb` | Mesa de servicio | `glpi_db_password` |

Ningún secreto se versiona **en claro**. Viven en `secrets/` (excluido de Git) y Docker Compose los monta en `/run/secrets` (ADR-009, ADR-031). Los que el equipo comparte durante el desarrollo se versionan **cifrados** con SOPS + age en `infra/secretos/` (ADR-029):
- `equipo`: URL y clave publicable de Supabase Auth.
- `administracion`: `service_role` de Supabase Auth.

Se gestionan con `infra/scripts/secretos.sh` (`docs/probar-localmente.md` §1 y §7). Los de la base local los genera `preparar-entorno.sh` y nunca van al repositorio. Rotación cada 90 días (RS-06): sección 7.

## 2. Primera instalación

```bash
JML_MODO=local infra/scripts/preparar-entorno.sh                         # secretos en secrets/ y infra/.env
docker compose -f infra/compose.yaml -f infra/compose.local.yaml up -d --build
docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm migrar
docker compose -f infra/compose.yaml -f infra/compose.local.yaml exec web python manage.py semillas   # datos ficticios
```

**Base de datos.** El contenedor `postgres` crea `app_owner`, `app_backend`, `anon` y `authenticated` al iniciarse por primera vez (`infra/local/initdb/01-roles.sh`); `migrar` aplica el esquema, el dueño separado (ADR-028) y RLS.

**Supabase Auth, una vez por proyecto, en el Dashboard:** registro abierto desactivado, contraseña mínima de 12 y TOTP habilitado (RS-16); después, el asesor de seguridad.

**GLPI, una vez** (probado el 11/10/2026 contra un GLPI limpio; ver `docs/spikes/glpi.md`):

```bash
infra/glpi/preparar-glpi.sh                              # API, cliente de API, perfil y usuario de servicio, tokens
docker compose -f infra/compose.yaml run --rm configurar-glpi   # categorías, reglas, SLA y plantillas
docker compose -f infra/compose.yaml up -d worker               # (en compose.local.yaml: --profile glpi)
```

Los dos primeros son idempotentes. **Nunca los corra dos veces a la vez**: cada corrida busca, no encuentra y crea, y quedan duplicados. Si los encuentra, `configurar-glpi` se detiene y nombra los ids que sobran.

`preparar-glpi.sh` hace además lo siguiente:
- Escribe en `secrets/` los tres tokens y la clave del administrador de GLPI (`glpi_admin_password`).
- **Deshabilita las cuentas de demostración** de GLPI.
- Deja la API **solo para la red interna**: el cliente de API excluye la IP del WAF y no se admite el inicio de sesión por usuario y contraseña.

Además, BunkerWeb responde 403 a `/apirest.php` y `/api.php` desde fuera (auditoría del 12/10/2026).

Pasos que **siguen siendo manuales**:
1. Doble factor para los técnicos (*Configuración > Autenticación*, SRS 3.1).
2. Zona horaria de los técnicos en sus preferencias de GLPI (S-35): GLPI guarda UTC. Requiere `php bin/console database:enable_timezones` y que el usuario `glpi` de MariaDB tenga `SELECT` sobre `mysql.time_zone_name`.
3. Crear las cuentas de los técnicos con su perfil (el de servicio es solo del worker).

## 3. Puesta en marcha en la máquina local (ADR-031)

1. **Equipo**: Windows 11 con Docker Desktop (WSL2), al menos 4 GiB de RAM para Docker y los puertos 80 y 443 libres.
2. **Nombres**: `127.0.0.1 app.localhost glpi.localhost` en el archivo hosts. El certificado es autofirmado: el navegador lo advierte una vez.
3. **Secretos y arranque**: sección 2. La reportería es opcional (`-f infra/compose.reporteria.yaml`).
4. **Tareas diarias del host** (Programador de tareas de Windows o cron, hora de Bogotá), con el disco externo conectado:
   - 01:30 · `JML_MEDIO_EXTERNO=<disco>/jml infra/scripts/copiar-exportes.sh` (RD-04: auditoría y ancla, sin sobrescribir, 365 días).
   - 02:00 · `JML_RESPALDO_DESTINO=<disco>/jml/respaldos infra/scripts/respaldo.sh` (RD-06: 30 días de retención).
5. **Antes de cada demostración**: comprobar que el proyecto de Supabase Auth no esté pausado (RNF-05) y que todo esté *healthy*.
6. **Comprobar**:
    - `infra/waf/pruebas.sh app.localhost` y `infra/waf/pruebas.sh glpi.localhost` (CA-20).
    - `bash auditoria/scripts/ca-13-postgres-local.sh` (CA-13).
    - Iniciar sesión con una cuenta de prueba.
    - Al día siguiente, revisar que exista `ancla-AAAA-MM-DD.json` en `<disco>/jml/auditoria`.

## 4. Operación diaria

| Qué | Cómo |
|---|---|
| Salud | `docker compose -f infra/compose.yaml ps`. `web` revisa la base (`/salud`); `worker` revisa que haya sincronizado en los últimos 15 minutos y que GLPI responda. Una caída se nota en menos de 2 minutos (RNF-01) |
| Logs | `docker compose … logs -f web worker`. Son JSON con `correlation_id`; el mismo id viaja en la cabecera `X-Request-ID` |
| IP bloqueada por el WAF | `docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban <ip>`. El baneo dura 1 hora (RS-08) |
| Falso positivo del WAF | Nunca desactivar el CRS. Agregar una exclusión puntual en `infra/bunkerweb/configs/` (ver su README) y probar el flujo completo |
| Solicitudes en `error` | Aplicación → **Solicitudes en error → Reintentar**, una vez que GLPI responda (RF-38) |
| Integridad de la auditoría | El Auditor: **Auditoría → Verificar**. Además, comparar la cabeza de la cadena con el último `ancla-*.json` del disco externo: si no coinciden, alguien reescribió la cadena |
| Crear o desactivar una cuenta | `docker compose -f infra/compose.yaml run --rm admin-usuarios crear --correo X --rol Y [--colaborador col-…]` / `desactivar --usuario <id>` |
| Registrar en otra base una cuenta que ya existe en Supabase | `… run --rm admin-usuarios vincular --usuario <id> --rol Y [--colaborador col-…]`. No usa `service_role`. Lo usa cada integrante con su base local (`docs/probar-localmente.md` §4) |
| Cambio de esquema | `docker compose … run --rm migrar` (nunca `migrate` desde `web`: `app_backend` no tiene permisos para eso) |

### Antes de cada entrega o cambio grande

Cada criterio de aceptación con evidencia tiene un script reproducible. Las evidencias del 24/10/2026 están en `docs/evidencia/`, y las de la auditoría en `auditoria/evidencia/`.

| Criterio | Comando | Evidencia |
|---|---|---|
| RNF-06 (rendimiento) | `infra/scripts/carga.sh` | `rendimiento-2026-10-24.md` |
| RNF-01 y CA-11 (detección) | `infra/scripts/deteccion.sh glpi` y `deteccion.sh base` (cortan el servicio un momento) | `disponibilidad-2026-10-24.md` |
| CA-11 (restauración) | `respaldo.sh`, seguido de `restaurar-prueba.sh <carpeta>` | `disponibilidad-2026-10-24.md` |
| CA-12 (seguridad dinámica) | `infra/scripts/seguridad-dinamica.sh` | `seguridad-2026-10-24.md` |
| CA-20 (WAF) | `infra/waf/pruebas.sh app.localhost` y `pruebas.sh glpi.localhost` | `docs/spikes/bunkerweb.md` |
| GLPI real y flujos | `JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh`, solo con un GLPI de pruebas | job `glpi-real` de la CI |
| Interfaz (5.8) | `JML_GLPI_DE_PRUEBAS=si infra/scripts/e2e-interfaz.sh`, solo en un stack de pruebas | — |

## 5. Incidentes

- **Supabase Auth no responde o el proyecto está pausado** (R1): nadie puede iniciar sesión; la aplicación responde con error genérico. Reactivar el proyecto desde el Dashboard (RNF-05).
- **PostgreSQL local caído** (T12): `web` queda *unhealthy* y muestra la página de mantenimiento; Docker reinicia el contenedor (`restart: unless-stopped`).
- **GLPI caído**: la aplicación sigue aceptando y aprobando; los tickets esperan en la bandeja con reintentos (30 s, 2, 5, 15 minutos…). Tras 10 fallos la solicitud pasa a `error` (RF-18, S-13). En una emergencia, el técnico puede crear el ticket a mano en GLPI (T11).
- **Una sesión de base queda bloqueando** (`statement timeout` en cascada): como `postgres`, `select pg_terminate_backend(pid) from pg_stat_activity where usename like 'app_%' and state = 'idle in transaction';` (lecciones 34 y 35).
- **La cadena de auditoría está rota**: no tocar la base. Exportar evidencia (la exportación diaria la incluye igual), avisar al Auditor y comparar con las anclas del disco externo para acotar desde cuándo.

## 6. Restauración (RNF-04: RPO 24 h, RTO 4 h)

Simulacro **verificado en local** el 24/10/2026: restauración completa y verificada en 23 s (`docs/evidencia/disponibilidad-2026-10-24.md`). Repítalo antes de la entrega y tras cada cambio de esquema:

```bash
JML_RESPALDO_DESTINO=.contrato-tmp/respaldos infra/scripts/respaldo.sh
infra/scripts/restaurar-prueba.sh .contrato-tmp/respaldos
```

**Ante una pérdida real** del equipo o de la base, en un clon limpio (o en el equipo de otro integrante):
1. **Aplicación.** Levantar el stack (sección 2) sin correr `migrar` ni `semillas`; el contenedor `postgres` crea los roles al iniciar. Restaurar el volcado del disco externo como `app_owner`, **sin su `CREATE SCHEMA`** (`restaurar-prueba.sh` hace lo mismo en una instancia desechable y sirve de guía):
   ```bash
   pg_restore -l app-AAAA-MM-DD.dump | grep -v ' SCHEMA - app ' > lista
   pg_restore -d "host=postgres dbname=postgres user=app_owner" --no-owner --role=app_owner --exit-on-error -L lista app-AAAA-MM-DD.dump
   ```
   (desde un contenedor `postgres:17` de un solo uso en la red `jml_pg_net`). Después, `migrar` aplica lo que falte.
2. **GLPI.** `gunzip -c glpi-AAAA-MM-DD.sql.gz | docker compose … exec -T mariadb sh -c 'mariadb -u glpi -p"$(cat /run/secrets/glpi_db_password)" glpi'`.
3. **Comprobar.** El Auditor pulsa **Verificar**, y la cabeza de la cadena se compara con el ancla del día del respaldo (RD-04).
4. **Evidencia.** Registrar tiempos y capturas para CA-11.

## 7. Rotación de secretos (RS-06, cada 90 días)

| Secreto | Cómo |
|---|---|
| `django_secret_key` | Generar uno nuevo en `secrets/` y reiniciar `web` y `worker` (cierra todas las sesiones) |
| `db_password`, `db_owner_password` | Como `postgres`: `ALTER ROLE app_backend PASSWORD '…'` (o `app_owner`) en el PostgreSQL local; actualizar `secrets/`; reiniciar |
| `supabase_service_role` | Dashboard → API Keys: crear una nueva y revocar la anterior |
| `glpi_*_token` | Regenerarlos en GLPI (cliente de API y preferencias del usuario). El de administrador (`glpi_admin_user_token`) solo lo usa `configurar-glpi`: regenérelo después de configurar |
| `bw_api_token` | Generar uno nuevo y recrear `bunkerweb` y `bw-scheduler` |
| Contraseña de `postgres` del proyecto de Supabase usado antes de ADR-031 | Dashboard → Database → Reset password. **Pendiente**: se compartió en una conversación durante el desarrollo |
| Secretos de `infra/secretos/` | Cambiar el valor en su origen, dejarlo en `secrets/` y `secretos.sh cifrar <grupo> <nombre>`. **Siempre** que se quite a una persona con `secretos.sh quitar` (ADR-029) |
| Llave age de una persona perdida o expuesta | Quitarla (`secretos.sh quitar`), rotar los secretos de sus grupos y agregar su llave nueva |
| `grafana_admin_password` | Generar una nueva en `secrets/` y recrear `grafana` (la reportería guarda el usuario en su volumen: cambiarla también en Grafana) |
