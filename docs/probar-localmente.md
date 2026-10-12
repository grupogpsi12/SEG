# Probar la aplicación en su propio equipo

Para quién: integrantes del equipo que quieren usar la aplicación completa sin Azure. Esta guía se siguió de principio a fin desde un clon limpio el 12/10/2026 (`docs/auditoria-2026-10-12.md`).

**Qué se levanta:** BunkerWeb (WAF) delante de todo, la aplicación (web y worker), un PostgreSQL 17 local con los mismos roles y reglas que Supabase, y GLPI 11 con su MariaDB. El inicio de sesión **sí** usa el Supabase Auth compartido del proyecto, así que cada persona necesita una cuenta.

## 0. Requisitos

- **Docker Desktop**, con WSL2 en Windows, y unos **4 GB de RAM** libres.
- **Git**. En Windows, todos los comandos se ejecutan en **Git Bash**, no en PowerShell.
- Si Git Bash no encuentra `docker`: `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"`.
- Los puertos 80 y 443 libres.

**Pídale al equipo, por un canal privado:**

1. La URL de Supabase y la clave publicable `sb_publishable_…`. La clave es pública por diseño.
2. Su cuenta: correo, contraseña inicial, **id de usuario** (UUID) y rol. La crea el Administrador (sección 7).

## 1. Clonar y preparar (una vez)

```bash
git clone https://github.com/grupogpsi12/SEG.git jml && cd jml
export JML_SUPABASE_URL=https://tzxziubxwzgqdbmfkdiq.supabase.co
export JML_SUPABASE_CLAVE_PUBLICA=sb_publishable_...      # la que le dio el equipo
JML_MODO=local infra/scripts/preparar-entorno.sh           # secretos aleatorios en ./secrets e infra/.env
```

`secrets/` e `infra/.env` no se versionan. Nunca los suba ni los comparta.

## 2. Levantar

Defina un atajo para los comandos que siguen (en cada terminal nueva):

```bash
C="-f infra/compose.yaml -f infra/compose.local.yaml"
```

**Opción A: imagen publicada** (no compila nada). El paquete de GHCR es privado: inicie sesión una vez con un token personal de GitHub que tenga el permiso `read:packages`.

```bash
docker login ghcr.io -u <su-usuario-de-github>          # pega el token como contraseña
export JML_IMAGEN=ghcr.io/grupogpsi12/jml-app:ultima
docker compose $C up -d --no-build
```

**Opción B: construir en su equipo** (tarda unos minutos la primera vez):

```bash
docker compose $C up -d --build
```

Después, una sola vez, cree las tablas y cargue los datos ficticios (30 colaboradores, `col-001` a `col-030`):

```bash
docker compose $C run --rm migrar
docker compose $C exec web python manage.py semillas
```

## 3. GLPI (una vez)

GLPI se instala solo la primera vez y tarda de 2 a 4 minutos. Cuando `docker compose $C ps` muestre `glpi` como *healthy*, ejecute:

```bash
COMPOSE="$C" infra/glpi/preparar-glpi.sh            # API solo interna, usuario de servicio, tokens y clave del admin
docker compose $C run --rm configurar-glpi            # grupos, 114 categorías, reglas, SLA y plantillas
docker compose $C --profile glpi up -d worker         # crea los tickets y sincroniza cada 5 minutos
```

- Corra `configurar-glpi` **una vez y nunca dos a la vez**. Si detecta duplicados, se detiene y dice qué ids sobran.
- Para entrar a GLPI use el usuario `glpi`. Su clave está en `secrets/glpi_admin_password`.

## 4. Vincular su cuenta (una vez)

Las cuentas viven en el Supabase compartido, pero los roles se guardan en **su** base local. Sin este paso, el ingreso dice «Su cuenta no tiene acceso».

```bash
docker compose $C exec web python manage.py admin_usuarios vincular \
  --usuario <su-id-de-usuario> --rol <su-rol> [--colaborador col-0NN]
```

**Roles posibles:**

| Rol | Puede |
|---|---|
| `rrhh` | Emitir, aprobar y ver campos restringidos |
| `administrador` | Matriz de perfiles, roles y reintentos |
| `auditor` | Auditoría |
| `tecnico_ad`, `tecnico_comunicaciones`, `tecnico_licencias`, `tecnico_inventario` | Dashboard, cuentas y fichas |
| `solicitante` | Registrar sus vacaciones o su renuncia |

**`--colaborador`** vincula la cuenta a una persona de las semillas. Es obligatorio para quien solicita, y `col-006` a `col-010` son de RRHH.

Para probar varios roles, vincule varias cuentas. Cambiar los roles de una cuenta ya vinculada se hace en la aplicación: **Administración → Usuarios**, con una cuenta de Administrador.

## 5. Entrar

1. Agregue esta línea al archivo `hosts` como administrador. En Windows está en `C:\Windows\System32\drivers\etc\hosts`.

   ```
   127.0.0.1 app.localhost glpi.localhost
   ```

2. Abra `https://app.localhost`. El certificado es autofirmado: acepte la advertencia.
3. Ingrese con su correo y su contraseña. La primera vez se inscribe el TOTP: escriba la clave que muestra la página en su app autenticadora (ver `docs/manual-usuario.md`).
4. Las solicitudes que se emiten o aprueban aparecen como tickets en `https://glpi.localhost` en unos 30 segundos. La sincronización de vuelta corre cada 5 minutos.

## 6. Comprobar que todo está bien (opcional)

```bash
docker compose $C --profile glpi ps                 # los 7 servicios "healthy"
infra/waf/pruebas.sh app.localhost                  # tráfico normal pasa, ataques 403
infra/waf/pruebas.sh glpi.localhost                 # además, la API de GLPI cerrada desde fuera
JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh   # 30 pruebas contra su GLPI (necesita uv)
```

`contrato-glpi.sh` **borra los tickets cuya clave empieza con `SOL-`** en su GLPI: úselo solo en su equipo.

## 7. Para el Administrador: crear cuentas

Solo quien tiene `secrets/supabase_service_role` (no se comparte):

```bash
docker compose $C run --rm admin-usuarios crear --correo persona@andina.example --rol rrhh --colaborador col-006
```

El comando muestra el **id de usuario** y la **contraseña inicial** una sola vez. Entréguelos a la persona por un canal privado, junto con el rol, para que haga la sección 4. Los ids de las cuentas existentes están en Supabase: *Authentication → Users*, columna *UID*.

Para desactivar una cuenta: `run --rm admin-usuarios desactivar --usuario <id>`.

## 8. Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| Todo da **403** después de probar ataques o de muchos intentos de ingreso | Su IP quedó baneada 1 hora **en ese sitio**. Desde Docker Desktop el cliente se ve como `10.20.40.1`: `docker compose $C exec bw-scheduler bwcli unban 10.20.40.1` |
| **429** en `/ingreso` | Límite de 5 intentos por minuto. Espere un minuto |
| «Su cuenta no tiene acceso» | Falta la sección 4, o el rol o el id no son los correctos |
| `web` no queda *healthy* | `docker compose $C logs web`. Casi siempre falta `migrar` o la clave publicable |
| `worker` no queda *healthy* | Espera a que `glpi` esté *healthy*. Si sigue así, falta la sección 3: `docker compose $C logs worker` |
| `preparar-glpi.sh` falla | GLPI aún se está instalando: espere a que `glpi` esté *healthy* y repítalo. Es idempotente |
| `pool overlaps` al levantar | Hay otra copia del proyecto con las mismas redes: `docker compose … down` en la otra carpeta |

**Apagar** sin perder datos: `docker compose $C --profile glpi down`. **Empezar de cero**, borrando la base y GLPI: `docker compose $C --profile glpi down -v` y repetir desde la sección 2.
