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

**Cuentas.** Las crea el Administrador, con la clave `service_role` en `secrets/supabase_service_role`:

```bash
docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm admin-usuarios \
  crear --correo persona@andina.example --rol rrhh --colaborador col-006
```

Los colaboradores de las semillas van de `col-001` a `col-030` (`col-006` a `col-010` son de RRHH). Para probar todos los roles, cree una cuenta por rol.

## 4. Qué funciona y qué no todavía

| Funciona | Pendiente |
|---|---|
| Ingreso con TOTP, solicitudes, bandeja de RRHH, detalle, dashboard, cuentas, ficha y CSV, Auditor, área de administración, reintento | **Creación de tickets en GLPI**: el worker no arranca hasta que exista el adaptador de GLPI (ítem 3.2). Las solicitudes aprobadas quedan en la bandeja de salida |
| GLPI 11 en `https://glpi.localhost` (se instala solo la primera vez) | Configuración de GLPI como código (3.1) |
| El WAF bloquea los ataques: `infra/waf/pruebas.sh app.localhost` | Exclusiones del CRS (spike 0.6): si algo legítimo da 403, avise con la ruta |

## 5. Problemas comunes

- **Todo da 403 después de probar ataques**: su IP quedó baneada 1 hora. Desbloquéela con `docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban 172.17.0.1` (o con su IP).
- **`web` no queda *healthy***: revise `docker compose ... logs web`. Casi siempre falta `migrar` o la clave publicable.
- **Empezar de cero**: `docker compose -f infra/compose.yaml -f infra/compose.local.yaml down -v` (borra la base local).
