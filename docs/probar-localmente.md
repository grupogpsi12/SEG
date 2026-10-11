# Probar la aplicación en su propio equipo

Para quién: integrantes del equipo que quieren usar la aplicación sin montar Azure. Se necesita Docker Desktop (en Windows, con WSL2) y unos 4 GB de RAM libres.

La base de datos es un PostgreSQL 17 local con los mismos roles y reglas que Supabase. El inicio de sesión **sí** usa el Supabase Auth del proyecto de desarrollo, así que el Administrador debe crearle una cuenta. BunkerWeb queda delante, igual que en producción.

## 1. Preparar (una vez)

```bash
git clone <repositorio> && cd proyecto-artefactos-v2.3
export JML_SUPABASE_URL=https://tzxziubxwzgqdbmfkdiq.supabase.co
export JML_SUPABASE_CLAVE_PUBLICA=sb_publishable_...    # pídasela al equipo (es pública por diseño)
JML_MODO=local infra/scripts/preparar-entorno.sh         # crea secretos aleatorios en ./secrets e infra/.env
```

En Windows, ejecútelo en **Git Bash**.

## 2. Levantar

Con la imagen publicada (más rápido, cuando el repositorio ya esté en GitHub):

```bash
export JML_IMAGEN=ghcr.io/<organizacion>/jml-app:ultima
docker compose -f infra/compose.yaml -f infra/compose.local.yaml up -d --no-build
```

Construyéndola en su equipo:

```bash
docker compose -f infra/compose.yaml -f infra/compose.local.yaml up -d --build
```

Después, una sola vez, cree las tablas (como `app_owner`, ADR-028) y cargue los datos ficticios:

```bash
docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm migrar
docker compose -f infra/compose.yaml -f infra/compose.local.yaml exec web python manage.py semillas
```

## 3. Entrar

1. Agregue a su archivo `hosts` (en Windows: `C:\Windows\System32\drivers\etc\hosts`, como administrador): `127.0.0.1 app.localhost glpi.localhost`.
2. Abra `https://app.localhost`. El certificado es autofirmado: acepte la advertencia del navegador.
3. Ingrese con la cuenta que le dio el Administrador. La primera vez se inscribe el TOTP (ver `docs/manual-usuario.md`).

**Cuentas.** Las crea el Administrador, con la clave `service_role` en `secrets/supabase_service_role`. Para el equipo ya existen cuatro (administrador, rrhh, tecnico.ad y auditor, todas `@andina.example`); sus contraseñas iniciales están en `secrets/cuentas-de-prueba.txt` (no se versiona). Cada persona inscribe **su propio** TOTP la primera vez. Para crear más:

```bash
docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm admin-usuarios \
  crear --correo persona@andina.example --rol rrhh --colaborador col-006
```

Los colaboradores de las semillas van de `col-001` a `col-030` (`col-006` a `col-010` son de RRHH). Para probar todos los roles, cree una cuenta por rol.

## 4. Qué funciona y qué no todavía

| Funciona | Pendiente |
|---|---|
| Ingreso con TOTP, solicitudes, bandeja de RRHH, detalle, dashboard, cuentas, ficha y CSV, Auditor, área de administración, reintento, subida de PDF de hasta 20 MB | **Creación de tickets en GLPI**: el worker no arranca (perfil `glpi`) hasta que GLPI tenga la API habilitada y los tokens en `secrets/` (ítem 3.1 y spike 0.3). Las solicitudes aprobadas quedan en la bandeja de salida. En la base local ya hay una solicitud de ingreso de la prueba del WAF (`Prueba Subida`) |
| GLPI 11 en `https://glpi.localhost` (se instala solo la primera vez) | Configuración de GLPI como código (3.1) |
| El WAF bloquea los ataques: `infra/waf/pruebas.sh app.localhost` | Exclusiones del CRS (spike 0.6): si algo legítimo da 403, avise con la ruta |

## 5. Problemas comunes

- **Todo da 403 después de probar ataques**: su IP quedó baneada 1 hora, **solo en ese sitio**. Desde Docker Desktop el cliente se ve como `10.20.40.1`. Vea los baneos con `… exec bw-scheduler bwcli bans` y desbloquee con `… exec bw-scheduler bwcli unban 10.20.40.1`.
- **`web` no queda *healthy***: revise `docker compose ... logs web`. Casi siempre falta `migrar` o la clave publicable.
- **Empezar de cero**: `docker compose -f infra/compose.yaml -f infra/compose.local.yaml down -v` (borra la base local).
