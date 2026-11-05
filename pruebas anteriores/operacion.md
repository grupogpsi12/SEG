# Manual de operación

Para quién: el Administrador del sistema y quien despliegue u opere la plataforma. Supone conocer Docker y la consola de Azure. Lo marcado **(sin verificar)** está escrito, pero todavía no se ha ejecutado en Azure ni contra GLPI real (ver `docs/estado.md`).

## 1. Piezas y secretos

| Servicio | Qué hace | Secretos que monta (`/run/secrets`) |
|---|---|---|
| `bunkerweb` + `bw-scheduler` | WAF y proxy inverso; único con puertos (80/443) | (API_TOKEN por variable, desde `infra/.env`) |
| `web` | Aplicación Django (gunicorn: 1 proceso × 8 hilos, S-29) | `django_secret_key`, `db_password`, `supabase_ca_crt` |
| `worker` | Bandeja de salida a GLPI, sincronización cada 5 minutos, exportación diaria de auditoría | lo anterior + `glpi_app_token`, `glpi_user_token` |
| `migrar` (una sola vez) | `migrate` como `app_owner` (ADR-028) | `db_owner_password` (como `db_password`) |
| `admin-usuarios` (una sola vez) | Crear, vincular o desactivar cuentas (RF-06) | lo de `web` + `supabase_service_role` |
| `configurar-glpi` (una sola vez) | GLPI como código (3.1) | `glpi_app_token`, `glpi_admin_user_token` |
| `glpi` + `mariadb` | Mesa de servicio | `glpi_db_password` |

Ningún secreto se versiona. En Azure vienen de Key Vault a un tmpfs (ADR-009). Rotación cada 90 días (RS-06): sección 7.

## 2. Primera instalación

```bash
infra/scripts/preparar-entorno.sh              # en local: JML_MODO=local (docs/probar-localmente.md)
docker compose -f infra/compose.yaml up -d --build
docker compose -f infra/compose.yaml run --rm migrar
docker compose -f infra/compose.yaml exec web python manage.py semillas       # solo datos ficticios
```

**Supabase, una vez por proyecto, como `postgres`:**
1. `docs/spikes/supabase.md`: crear el rol `app_backend` y el esquema `app`.
2. `infra/supabase/duenio-separado.sql`: crear `app_owner` y aplicar el dueño separado.
3. En el Dashboard: registro abierto desactivado, contraseña mínima de 12 y TOTP habilitado (RS-16).

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

Además, BunkerWeb responde 403 a `/apirest.php` y `/api.php` desde fuera (auditoría del 12/10/2026). En Azure, `JML_SECRETOS` apunta al tmpfs y los secretos pasan a Key Vault.

Pasos que **siguen siendo manuales**:
1. Doble factor para los técnicos (*Configuración > Autenticación*, SRS 3.1).
2. Zona horaria de los técnicos en sus preferencias de GLPI (S-35): GLPI guarda UTC. Requiere `php bin/console database:enable_timezones` y que el usuario `glpi` de MariaDB tenga `SELECT` sobre `mysql.time_zone_name`.
3. Crear las cuentas de los técnicos con su perfil (el de servicio es solo del worker).

## 3. Despliegue en Azure (ítem 5.2) **(sin verificar)**

1. **VM** B2s, Ubuntu 24.04, con apagado automático y alerta de presupuesto al 50 % (0.5). Asignarle una **identidad administrada**.
2. **NSG**: 80 y 443 abiertos al público; 22 solo desde las IP del equipo y solo con llave. Si se adopta Cloudflare (ADR-024), el NSG cierra también 80 y 443.
3. **DNS**: DuckDNS (o el dominio del equipo) para `app.<dominio>` y `glpi.<dominio>`, apuntando a la IP pública.
4. **Key Vault** con todos los secretos de la sección 1. Dar a la identidad de la VM el rol *Key Vault Secrets User*.
5. **Storage**: contenedores `auditoria` (con política de inmutabilidad por tiempo de 365 días, bloqueada) y `respaldos`. Dar a la identidad el rol *Storage Blob Data Contributor* **solo sobre esos dos contenedores** (RS-20).
6. En la VM: instalar Docker, Azure CLI y `git`. Crear `/srv/jml/soportes` en un sistema de archivos montado con `noexec,nosuid,nodev` (entrada en `/etc/fstab`, RS-17). Clonar el repositorio.
7. **Secretos a tmpfs** al arrancar: un servicio de systemd que monta un tmpfs en `/run/secrets` y escribe cada secreto con `az keyvault secret show --id … --query value -o tsv` usando `az login --identity`. Después corre `JML_SECRETOS=/run/secrets ENV_SALIDA=/run/secrets/compose.env infra/scripts/preparar-entorno.sh`.
8. **Levantar**: `docker compose --env-file /run/secrets/compose.env -f infra/compose.yaml -f infra/compose.azure.yaml up -d`. Luego `run --rm migrar` y los pasos de GLPI de la sección 2. Let's Encrypt lo emite BunkerWeb solo.
9. **Cron del host** (hora de Bogotá): `30 1 * * * infra/scripts/subir-exportes.sh` (RD-04) y `0 2 * * * infra/scripts/respaldo.sh` (RD-06), ambos con `JML_STORAGE_CUENTA=<cuenta>`.
10. **Comprobar**:
    - `infra/waf/pruebas.sh app.<dominio> <ip>` y `infra/waf/pruebas.sh glpi.<dominio> <ip>` (CA-20).
    - `docker compose ps`: todo debe estar *healthy*.
    - Iniciar sesión con una cuenta de prueba.
    - Al día siguiente, revisar que exista `ancla-AAAA-MM-DD.json` en el contenedor `auditoria`.

## 4. Operación diaria

| Qué | Cómo |
|---|---|
| Salud | `docker compose -f infra/compose.yaml ps`. `web` revisa la base (`/salud`); `worker` revisa que haya sincronizado en los últimos 15 minutos (RNF-01) |
| Logs | `docker compose … logs -f web worker`. Son JSON con `correlation_id`; el mismo id viaja en la cabecera `X-Request-ID` |
| IP bloqueada por el WAF | `docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban <ip>`. El baneo dura 1 hora (RS-08) |
| Falso positivo del WAF | Nunca desactivar el CRS. Agregar una exclusión puntual en `infra/bunkerweb/configs/` (ver su README) y probar el flujo completo |
| Solicitudes en `error` | Aplicación → **Solicitudes en error → Reintentar**, una vez que GLPI responda (RF-38) |
| Integridad de la auditoría | El Auditor: **Auditoría → Verificar**. Además, comparar la cabeza de la cadena con el último `ancla-*.json` de Blob: si no coinciden, alguien reescribió la cadena |
| Crear o desactivar una cuenta | `docker compose -f infra/compose.yaml run --rm admin-usuarios crear --correo X --rol Y [--colaborador col-…]` / `desactivar --usuario <id>` |
| Registrar en otra base una cuenta que ya existe en Supabase | `… run --rm admin-usuarios vincular --usuario <id> --rol Y [--colaborador col-…]`. No usa `service_role`. Lo usa cada integrante con su base local (`docs/probar-localmente.md` §4) |
| Cambio de esquema | `docker compose … run --rm migrar` (nunca `migrate` desde `web`: `app_backend` no tiene permisos para eso) |

## 5. Incidentes

- **Supabase no responde o el proyecto está pausado** (R1): `web` queda *unhealthy* y la aplicación responde con error genérico. Reactivar el proyecto desde el Dashboard. El worker mantiene actividad cada 5 minutos para que no se pause (RNF-05).
- **GLPI caído**: la aplicación sigue aceptando y aprobando; los tickets esperan en la bandeja con reintentos (30 s, 2, 5, 15 minutos…). Tras 10 fallos la solicitud pasa a `error` (RF-18, S-13). En una emergencia, el técnico puede crear el ticket a mano en GLPI (T11).
- **Una sesión de base queda bloqueando** (`statement timeout` en cascada): como `postgres`, `select pg_terminate_backend(pid) from pg_stat_activity where usename like 'app_%' and state = 'idle in transaction';` (lecciones 34 y 35).
- **La cadena de auditoría está rota**: no tocar la base. Exportar evidencia (la exportación diaria la incluye igual), avisar al Auditor y comparar con las anclas guardadas en Blob para acotar desde cuándo.

## 6. Restauración (RNF-04: RPO 24 h, RTO 4 h) **(sin verificar)**

1. **Aplicación**:
   - Crear un proyecto de Supabase nuevo y aplicar la sección 2 (roles y `duenio-separado.sql`).
   - Restaurar con `pg_restore --no-owner --role=app_owner --schema=app -d "<conexión como app_owner>" app-AAAA-MM-DD.dump` (descargar antes el archivo del contenedor `respaldos`).
   - Correr `migrar`: aplica lo que falte y los permisos de la 0004.
2. **GLPI**: `gunzip -c glpi-AAAA-MM-DD.sql.gz | docker compose … exec -T mariadb sh -c 'mariadb -u glpi -p"$(cat /run/secrets/glpi_db_password)" glpi'`.
3. Comprobar con el Auditor (**Verificar**) y comparar con el ancla del día del respaldo.
4. Registrar tiempos y capturas como evidencia de CA-11.

## 7. Rotación de secretos (RS-06, cada 90 días)

| Secreto | Cómo |
|---|---|
| `django_secret_key` | Generar uno nuevo, actualizar Key Vault y reiniciar `web` y `worker` (cierra todas las sesiones) |
| `db_password`, `db_owner_password` | Como `postgres`: `ALTER ROLE app_backend PASSWORD '…'` (o `app_owner`); actualizar Key Vault; reiniciar |
| `supabase_service_role` | Dashboard → API Keys: crear una nueva y revocar la anterior |
| `glpi_*_token` | Regenerarlos en GLPI (cliente de API y preferencias del usuario). El de administrador (`glpi_admin_user_token`) solo lo usa `configurar-glpi`: en Azure, regenérelo después de configurar |
| `bw_api_token` | Generar uno nuevo y recrear `bunkerweb` y `bw-scheduler` |
| Contraseña de `postgres` en Supabase | Dashboard → Database → Reset password. **Pendiente**: se compartió en una conversación durante el desarrollo |
