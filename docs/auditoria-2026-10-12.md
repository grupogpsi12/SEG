# Auditoría de funcionalidad y seguridad — 12/10/2026

Para quién: el equipo del proyecto y quien evalúe la entrega. Resume qué se revisó, qué se encontró, cómo se corrigió y con qué evidencia. Todo hallazgo corregido tiene su commit y una prueba que falla sin la corrección.

**Base auditada:** `master` en `1ac4d29` (spike 0.3 cerrado). **Resultado:** `master` con la CI en verde y la imagen publicada en GHCR (ver `git log` desde `3b52ddf`).

## 1. Alcance y método

| Qué | Cómo |
|---|---|
| Código de la web, el worker y los adaptadores | Lectura completa de autenticación, sesión, vistas, formularios, subida de soportes, control de acceso por objeto, consultas, auditoría, registro y cliente de GLPI |
| Núcleo (`dominio`, `aplicacion`) | Reglas de autorización (quién decide, cancela, emite, ve restringidos) y casos de uso que las aplican |
| Infraestructura | `Dockerfile`, los tres `compose`, configuración de BunkerWeb, arranque de GLPI, scripts y CI |
| Sistema en ejecución | Peticiones reales a través del WAF a `app.localhost` y `glpi.localhost`: cabeceras, cookies, API de GLPI, rechazo por IP |
| Herramientas | `gitleaks` (historial y árbol), `pip-audit` (dependencias de la imagen), `bandit` (análisis estático), `trivy` (imagen Docker), `infra/waf/pruebas.sh` |
| Funcionalidad | Flujos VAC, RET, EMG y caída de GLPI de extremo a extremo con PostgreSQL y GLPI reales; la guía del equipo seguida desde un clon limpio |

## 2. Hallazgos

| ID | Severidad | Hallazgo | Corrección | Evidencia |
|---|---|---|---|---|
| A-01 | **Alta** | La API REST de GLPI (`/apirest.php`) respondía desde internet a través del WAF: `initSession` devolvía 200 con los tokens del worker. Además aceptaba **usuario y contraseña**, un inicio de sesión que **no pide el doble factor** de la interfaz de GLPI | BunkerWeb bloquea `^/api(rest)?\.php` en `glpi.*`. `bootstrap.php` desactiva el inicio de sesión por credenciales en la API | `62ae0e6`. Desde fuera: 403 en la API v1 y v2 (`pruebas.sh`). Por clave: `ERROR_LOGIN_WITH_CREDENTIALS_DISABLED` |
| A-02 | Media | El cliente de API de GLPI admitía `10.20.40.0/24`, que incluye la IP de BunkerWeb (`10.20.40.2`): la restricción por IP no frenaba nada que llegara por el WAF | Rango `10.20.40.3`–`10.20.40.254`, reaplicado en cada corrida de `preparar-glpi.sh` | `62ae0e6`. Desde el contenedor del WAF, con tokens válidos: `ERROR_NOT_ALLOWED_IP` |
| A-03 | Media | La imagen `ultima` de GHCR era de `6d9b9fb`, **anterior** a la corrección del empaquetado de plantillas: quien la usara obtenía un error 500 en `/ingreso`. Causa: una prueba de concurrencia (H3) fallaba según qué hilo ganara, la CI quedaba en rojo y la imagen no se publicaba | La prueba exige que gane exactamente una decisión, no cuál | `3b52ddf`. CI verde en `91b36ab` e imagen publicada |
| A-04 | Media | Dos corridas simultáneas de `configurar-glpi` duplicaban grupos, reglas, SLA y plantillas sin avisar. Con dos grupos del mismo nombre, el enrutamiento queda ambiguo | El configurador se detiene y nombra los ids duplicados | `25ebd15`. Prueba con el simulador y contra GLPI real: `Group 'JML - AD' duplicado en GLPI (ids [1, 2])` |
| A-05 | Baja | `bunkerweb`, `bw-scheduler` y `glpi` corrían con las capacidades por defecto de Docker | `cap_drop: ALL`. GLPI conserva solo `NET_BIND_SERVICE`, que su `apache2` necesita para arrancar | `62ae0e6`. Los tres quedan sanos y `pruebas.sh` pasa |
| A-06 | Baja | La CSP de la aplicación no limitaba `base-uri` ni `form-action`, que no heredan de `default-src` | `base-uri 'none'; form-action 'self'` | `8638323`. `test_web.py` |
| A-07 | Baja (funcional) | El Administrador veía el formulario de ingreso con el campo del PDF, aunque el núcleo siempre lo rechaza: la persona no existe aún, así que no es de RRHH (S-08), y el soporte solo lo sube RRHH (invariante 12) | La interfaz no le ofrece el ingreso y responde 403 a la URL | `8638323`. `test_el_administrador_no_ve_el_ingreso_ni_su_soporte` |
| A-10 | Media (funcional) | Un integrante que prueba con su PostgreSQL local no podía usar las cuentas del Supabase compartido: `crear` guarda los roles en la base de quien lo ejecuta, y en las demás bases el ingreso respondía «sin acceso» | Subcomando `admin-usuarios vincular --usuario <id> --rol …`: registra los roles en la base local, sin `service_role`. Un id inventado no da acceso: la sesión solo se crea si Supabase autentica ese id con TOTP | `732c2dc`. 6 pruebas nuevas y prueba real desde un clon: «sin acceso» → `vincular` → ingreso con TOTP → bandeja de RRHH |
| A-11 | Media (funcional) | BunkerWeb reemplazaba **todos** los errores de la aplicación por su página genérica de bloqueo. «Su cuenta no tiene acceso» y los errores de formulario que la vista devuelve con 403 se veían como un bloqueo del WAF | En `app.*`, BunkerWeb solo intercepta 502, 503 y 504. Sus propios bloqueos (CRS, límites) no cambian | `b94072f`. Prueba real a través del WAF: el 403 llega con el mensaje de la aplicación y `pruebas.sh` sigue en verde |
| A-08 | Informativa | SHA-1 de GLPI sin marcar como no criptográfico. Textos «PROVISIONAL hasta el spike 0.3» desactualizados | `usedforsecurity=False` y excepciones de bandit con su motivo. Textos actualizados | `8638323`, `6d52d28` |
| A-09 | Informativa | La CI no tenía análisis de seguridad | Job `seguridad` (gitleaks, pip-audit, bandit) en cada push. Trivy bloquea la publicación de una imagen con vulnerabilidades altas o críticas que tengan corrección | `91b36ab`. Verde en GitHub |

## 3. Revisado sin hallazgos

- **Ingreso:** dos pasos con rotación del id de sesión, desafío opaco, token AAL1 solo en memoria, 5 intentos por desafío, errores genéricos, `never_cache` y límite de 5 por minuto en el WAF.
- **Control de acceso por objeto:**
  - Una solicitud ajena responde «no encontrada».
  - RRHH no decide sobre sí mismo.
  - Solo quien la registró cancela una pendiente.
  - Nadie cambia sus propios roles.
  - Los permisos se verifican en los casos de uso, no solo en la vista.
- **Soportes:** firma `%PDF-`, máximo 20 MB, nombre aleatorio con `O_EXCL` y permisos 0600, validación del nombre antes de tocar el disco, borrado tras verificar el hash.
- **Datos:** sin SQL construido con cadenas. La auditoría encadenada se serializa con un candado de fila. Los disparadores de inmutabilidad y transiciones y los permisos mínimos de `app_backend` están probados contra PostgreSQL.
- **Salida:**
  - Escape automático en todas las plantillas. `mark_safe` solo en el SVG de números.
  - CSV con fórmulas neutralizadas.
  - Logs sin campos prohibidos y sin datos sensibles en los mensajes.
  - Ningún campo restringido llega a GLPI: CA-10, también contra GLPI real.
- **Borde:**
  - Solo `bunkerweb` publica puertos.
  - El CRS bloquea los 7 ataques de prueba en ambos sitios.
  - La API interna de BunkerWeb exige el token.
  - HSTS, `nosniff`, `Referrer-Policy`, CSP y `X-Frame-Options` presentes.
  - Cookies `Secure` y `HttpOnly`.
- **Herramientas:**
  - gitleaks: historial limpio. Los 3 avisos del árbol son `secrets/` e `infra/.env`, ignorados por git y Docker.
  - pip-audit: 0 vulnerabilidades.
  - bandit: 0 hallazgos.
  - Trivy: 0 vulnerabilidades altas o críticas corregibles en Debian 13 y Python.

## 4. Funcionalidad verificada con sistemas reales

`JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh` ejecuta 30 pruebas contra GLPI 11.0.11 real, con un PostgreSQL 17 desechable que tiene los roles de Supabase:

- Contrato de `SistemaDeTickets` (17).
- Integración de GLPI: CA-03, CA-06, CA-10, prioridad, vencimiento y configuración (9).
- **Flujos nuevos (4):**
  - VAC con reactivación programada (CA-04).
  - RET que cierra sin esperar la eliminación a 90 días (CA-04).
  - EMG con prioridad 5, SLA de 1 hora y exposición en el dashboard (CA-06).
  - GLPI caído: 10 reintentos, `error`, reintento del Administrador sin duplicar y la aplicación sigue aprobando (CA-07).

Además, la guía `docs/probar-localmente.md` se siguió **desde un clon limpio de GitHub**, con secretos y volúmenes nuevos:

- Construcción, migraciones y semillas.
- GLPI preparado y configurado.
- Worker sano.
- `pruebas.sh` en verde en ambos sitios.
- La suite real.
- El ingreso con una cuenta del Supabase compartido. Para esta prueba se crearon dos cuentas desechables, que se desactivaron al terminar.

Ahí aparecieron A-04, A-10 y A-11.

## 5. Riesgos aceptados y pendientes

| Riesgo | Por qué se acepta o qué falta |
|---|---|
| MariaDB conserva las capacidades por defecto | Su entrada corre como root la primera vez para ajustar el volumen y luego baja al usuario `mysql`. Está en una red interna sin salida (`db_net`) |
| Subidas simultáneas de PDF grandes | Por encima de 2,5 MB Django usa `/tmp`, un tmpfs `noexec` de 64 MB: tres PDF de 20 MB a la vez fallarían. Solo RRHH sube y la concurrencia real es baja |
| Token de administrador de GLPI en `secrets/` | Solo lo monta `configurar-glpi`. En Azure, regenerarlo después de configurar (`docs/operacion.md` §7) |
| Primera inscripción del TOTP | Quien tenga la contraseña inicial antes que su dueño inscribe el TOTP. La contraseña inicial se entrega por un canal seguro y se cambia |
| Pruebas dinámicas (ZAP, sqlmap) | Ítem 5.4: correrlas contra Azure, con una exclusión temporal del baneo para la IP del escáner |
| Pasos manuales | Doble factor y zona horaria de los técnicos en GLPI. Política de contraseñas y asesor de seguridad de Supabase (RS-16). Rotar la contraseña de `postgres` de Supabase |
