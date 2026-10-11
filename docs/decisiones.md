# Registro de decisiones de arquitectura (ADR)

Formato: contexto → decisión → alternativas descartadas → consecuencias. Los ADR no se borran: cuando una decisión cambia, el ADR anterior queda **Reemplazado** con referencia al nuevo.

| ADR | Título | Estado | Fecha |
|---|---|---|---|
| 001 | Aplicación propia + GLPI | Aceptada (precisada por ADR-016) | 05/10/2026 |
| 002 | Docker Compose en una VM de Azure | Aceptada | 05/10/2026 |
| 003 | Samba AD DC + Entra ID sin sincronización | **Reemplazada** por ADR-019 | 05/10/2026 |
| 004 | Automatización con autorización humana | **Reemplazada** por ADR-019 | 05/10/2026 |
| 005 | Cuenta única de RRHH (con disidencia) | Aceptada | 05/10/2026 |
| 006 | Deduplicación con índice único parcial | Aceptada | 05/10/2026 |
| 007 | Auditoría de solo inserción con cadena de hashes | Aceptada | 05/10/2026 |
| 008 | OIDC con Entra ID y BFF | **Reemplazada** por ADR-017 | 05/10/2026 |
| 009 | Secretos en Key Vault como archivos en tmpfs | Aceptada | 05/10/2026 |
| 010 | Licencias de M365 registradas en GLPI | **Reemplazada** por ADR-019 | 05/10/2026 |
| 011 | Sincronización con GLPI por consulta periódica | Aceptada | 05/10/2026 |
| 012 | Stack FastAPI + React + PostgreSQL | **Reemplazada** por ADR-015 y ADR-018 | 05/10/2026 |
| 013 | Exclusión del monitoreo del DC | Aceptada | 05/10/2026 |
| 014 | Autenticación de servicio contra la API de GLPI | **Pendiente** (sprint 0) | — |
| 015 | Supabase como base de datos de la aplicación | Aceptada | 07/10/2026 |
| 016 | Arquitectura hexagonal con la solicitud y sus tickets como núcleo | Aceptada | 07/10/2026 |
| 017 | Supabase Auth con TOTP mediado por el servidor | Aceptada | 07/10/2026 |
| 018 | Django 5.2 LTS con interfaz generada en el servidor | Aceptada | 07/10/2026 |
| 019 | Sin automatizaciones fuera de GLPI ni directorio montado | Aceptada | 07/10/2026 |
| 020 | Dashboard sin tiempo real para técnicos | Aceptada | 07/10/2026 |
| 021 | Soporte de vinculación adjunto a GLPI, sin almacenamiento permanente en la aplicación | Aceptada | 07/10/2026 |
| 022 | Permisos sobre recursos compartidos dentro de los eventos laborales | Aceptada | 07/10/2026 |
| 023 | BunkerWeb como WAF y proxy inverso (en lugar de nginx y de Application Gateway) | Aceptada | 10/10/2026 |
| 024 | Cloudflare Tunnel + Access delante de BunkerWeb | **Propuesta** (pendiente del equipo) | 10/10/2026 |
| 025 | Tres consultas de lectura nuevas en los repositorios para las vistas (2.7) | Aceptada | 10/10/2026 |
| 026 | Consulta de solicitudes en `error` para el reintento del Administrador (2.12) | Aceptada | 11/10/2026 |
| 027 | Matriz y usuarios completos para el área de administración (2.13) | Aceptada | 11/10/2026 |

---

## ADR-001 — Aplicación propia + GLPI 11

**Contexto.** GLPI trae formularios, reglas y API, pero el proyecto exige una aplicación propia.

**Decisión.** La aplicación gestiona colaboradores, solicitudes, deduplicación, aprobación, registro de cuentas, dashboard y auditoría. GLPI gestiona colas, SLA, el trabajo técnico, inventario y licencias.

**Consecuencias.** Los técnicos trabajan en GLPI y consultan el dashboard en la aplicación. ADR-016 precisa la relación: GLPI es un adaptador del núcleo.

## ADR-002 — Docker Compose en una sola VM de Azure

**Decisión.** Una VM B2s con Docker Compose y apagado automático aloja el borde (BunkerWeb desde ADR-023), web, worker, GLPI y MariaDB. Key Vault y Blob Storage como servicios gestionados de bajo costo. Desde v2.0 la base de datos de la aplicación vive en Supabase (ADR-015).

**Alternativas descartadas.** AKS o Container Apps: más complejidad y costo sin un requisito que lo justifique.

**Consecuencias.** La VM es un punto único de falla. Se mitiga con chequeos de salud, respaldos diarios y una restauración probada.

## ADR-003 — Samba AD DC + Entra ID sin sincronización · REEMPLAZADA

Reemplazada por ADR-019: el equipo decidió no montar ningún directorio en el entregable.

## ADR-004 — Automatización con autorización humana · REEMPLAZADA

Reemplazada por ADR-019: no hay automatizaciones fuera de GLPI.

## ADR-005 — Cuenta única de RRHH (con disidencia)

**Contexto.** El arquitecto recomendó separar al Analista de RRHH (registra) del Líder de RRHH (aprueba). El equipo prefiere una sola cuenta.

**Decisión.** Una sola cuenta de RRHH. La doble firma se logra así:
- Solicitante + RRHH, en las solicitudes iniciadas por un colaborador.
- RRHH + técnico, en las emitidas por RRHH, con justificación obligatoria.

RRHH no puede aprobar eventos sobre sí misma.

**Disidencia registrada.** Si la cuenta de RRHH se compromete, se puede emitir un retiro falso que un técnico ejecute. En un entorno real se recomienda separar las funciones. El riesgo residual se acepta en el entorno académico y se mitiga con TOTP, revisión del técnico y auditoría.

## ADR-006 — Deduplicación con un índice único parcial

**Decisión.** Restricción única parcial sobre (`colaborador_id`, `tipo`) para los estados abiertos `pendiente_aprobacion`, `aprobada`, `en_ejecucion` y `error`. En Django se expresa con `UniqueConstraint(condition=Q(...))`, que en PostgreSQL (Supabase) crea el índice parcial. Se elimina la «ventana de enfriamiento» de la Propuesta 2.

**Consecuencias.** La garantía resiste condiciones de carrera (CA-01). Las emergencias no se bloquean por solicitudes abiertas de otros tipos.

## ADR-007 — Auditoría de solo inserción con cadena de hashes

**Decisión.**
- El rol `app_backend` no tiene `UPDATE` ni `DELETE` sobre la auditoría.
- Cadena SHA-256 entre registros.
- Exportación diaria a Blob con inmutabilidad de 365 días.

**Consecuencias.** Un administrador del proyecto de Supabase podría alterar la tabla, pero la alteración se detecta al verificar la cadena y al compararla con la copia en Blob (CA-09).

## ADR-008 — OIDC con Entra ID y BFF · REEMPLAZADA

Reemplazada por ADR-017. Entra ID solo seguía en el diseño para el inicio de sesión, y el equipo eligió Supabase Auth.

## ADR-009 — Secretos en Key Vault entregados como archivos en tmpfs

**Decisión.** Al arrancar, la VM lee los secretos de Key Vault con su identidad administrada y los escribe en un sistema de archivos en memoria (tmpfs) montado en `/run/secrets`. La aplicación solo lee archivos, de modo que el mismo código funciona en local (archivos no versionados) y en Azure.

**Consecuencias.** No hay SDK de Azure dentro de la aplicación. La clave `service_role` de Supabase se monta solo al ejecutar el comando de administración (RS-15).

## ADR-010 — Licencias de M365 registradas en GLPI · REEMPLAZADA

Reemplazada por ADR-019. Las licencias siguen registrándose en GLPI, pero ahora como trabajo manual de la cola Licencias.

## ADR-011 — Sincronización con GLPI por consulta periódica

**Decisión.** El worker consulta GLPI cada 5 minutos: tickets, soluciones, documentos, activos y licencias.

**Alternativas descartadas.** Webhooks de GLPI 11: implican un endpoint entrante con verificación HMAC, sin un requisito de tiempo que lo justifique.

**Consecuencias.** Latencia de hasta 5 minutos, coherente con un dashboard sin tiempo real (ADR-020). La sincronización también mantiene activo el proyecto de Supabase.

## ADR-012 — Stack FastAPI + React + PostgreSQL · REEMPLAZADA

Reemplazada por ADR-015 (base de datos) y ADR-018 (framework e interfaz).

## ADR-013 — Exclusión del monitoreo del DC y de las rutinas de limpieza

**Decisión.** Se excluyen; no son parte de la gestión del ciclo de vida de identidades. Desde v2.0 tampoco hay DC montado.

## ADR-014 — Autenticación de servicio contra la API de GLPI · PENDIENTE

Se decide en el sprint 0 (tarea 0.3): API v2 con OAuth2 si admite autenticación de servicio; si no, API v1 con token de aplicación y token de usuario.

## ADR-015 — Supabase como base de datos de la aplicación

**Contexto.** El equipo decidió usar Supabase (plan gratuito) como base de datos de la aplicación. Se verificó el 07/10/2026 en fuentes oficiales:
- GLPI 11 solo admite MySQL 8.0+ y MariaDB 10.6+.
- El plan gratuito de Supabase incluye 500 MB, pausa el proyecto tras 1 semana de inactividad y no incluye respaldos.
- La conexión directa de Supabase requiere IPv6 (o un complemento IPv4); el *session pooler* sí acepta IPv4.
- El pooler en modo transacción no admite *prepared statements*.
- Desde el 30/05/2026 las tablas nuevas no se exponen en la Data API sin un `GRANT` explícito.

**Decisión.**
- Supabase (PostgreSQL) es la base de datos del núcleo. GLPI conserva su MariaDB.
- Web y worker se conectan por el *session pooler* (puerto 5432) con TLS, con el rol dedicado `app_backend`.
- Las tablas viven en el esquema `app`, que no se expone en la Data API. No se otorga nada a `anon` ni a `authenticated`, y RLS está activo sin políticas como segunda barrera.
- Respaldos propios diarios con `pg_dump` a Blob. El worker mantiene actividad para evitar la pausa del proyecto.

**Alternativas descartadas.**
- Usar la Data API con `supabase-js` desde el navegador: deja RLS como único control, contradice la arquitectura hexagonal y expone el modelo de datos.
- Plan Pro: elimina la pausa y agrega respaldos, pero tiene costo. Se reconsidera si el sprint 0 muestra que la actividad no evita la pausa.

**Consecuencias.** Las reglas de base de datos (índice parcial, disparadores, permisos) se mantienen porque es PostgreSQL. El backend no puede ser `postgres` ni usar `service_role` en ejecución normal.

Fuentes: glpi-install.readthedocs.io/en/latest/prerequisites.html · supabase.com/pricing · github.com/orgs/supabase/discussions/45329 · supabase.com/docs/guides/database/connecting-to-postgres · supabase.com/docs/guides/troubleshooting/disabling-prepared-statements-qL8lEL

## ADR-016 — Arquitectura hexagonal con la solicitud y sus tickets como núcleo

**Contexto.** El equipo pidió una arquitectura hexagonal en la que la interacción RRHH–TI mediante tickets sea el núcleo, con GLPI como un servicio integrado que puede tener sus propios procesos.

**Decisión.**
- La aplicación es dueña del ciclo **Solicitud → TicketDeCola**. GLPI es un adaptador detrás del puerto `SistemaDeTickets`: el lugar donde TI trabaja y la fuente de la verdad sobre el estado de cada ticket.
- Capas: `dominio` (sin dependencias externas), `aplicacion` (casos de uso y puertos) y `adaptadores` (entrada: vistas de Django y worker; salida: GLPI, persistencia, identidad y reloj).
- Es un solo desplegable (monolito modular). Los límites se verifican con `import-linter` en la integración continua.
- Solo existen puertos que tienen una implementación real y un doble de prueba: `SistemaDeTickets`, `Repositorios`/`Auditoria`, `ProveedorDeIdentidad` y `Reloj`.

**Alternativas descartadas.**
- Microservicios: complejidad operativa sin un requisito que la justifique.
- Que la aplicación tenga su propio sistema de tickets y GLPI sea un espejo: duplicaría GLPI y crearía dos fuentes de verdad.
- Usar los modelos de Django como dominio: acopla las reglas al ORM y rompe la arquitectura hexagonal.

**Consecuencias.** Hay código de mapeo entre modelos de Django y entidades del dominio; ese es el costo aceptado de la hexagonal. Los tickets que GLPI crea por su cuenta se ignoran.

## ADR-017 — Supabase Auth con TOTP mediado por el servidor

**Contexto.** El equipo eligió Supabase Auth. La documentación oficial indica que la MFA TOTP es gratuita, viene activa en todos los proyectos y que el cliente de Python soporta inscripción, desafío y verificación (verificado el 07/10/2026).

**Decisión.**
- El navegador envía las credenciales a Django.
- Django autentica contra Supabase Auth, exige la inscripción del TOTP en el primer ingreso y verifica el código.
- Solo al llegar al nivel AAL2 crea una sesión de Django: cookie `HttpOnly`, identificador rotado. Los tokens de Supabase se descartan.
- Los roles son grupos de Django.
- El registro abierto está deshabilitado. Los usuarios se crean con un comando de administración que es el único que usa `service_role`.

**Alternativas descartadas.**
- `supabase-js` en el navegador: tokens accesibles desde JavaScript y más superficie ante XSS.
- Entra ID con OIDC: exigiría mantener un tenant solo para el inicio de sesión.
- Autenticación propia de Django con `django-otp`: viable, pero contradice la elección del equipo.

**Consecuencias.** Se valida el flujo en el sprint 0 (SUP-05). Cada usuario tiene un registro en Supabase Auth y otro en Django, vinculados por el id de Supabase.

Fuentes: supabase.com/docs/guides/auth/auth-mfa/totp · supabase.com/docs/reference/python/auth-mfa-api

## ADR-018 — Django 5.2 LTS con interfaz generada en el servidor

**Contexto.** El equipo priorizó robustez, seguridad y confiabilidad, y pidió mantener Python o Django si cumplen. Django 5.2 es la versión LTS vigente, con soporte extendido hasta abril de 2028 (djangoproject.com/download, verificado el 07/10/2026).

**Decisión.** Django 5.2 LTS con plantillas generadas en el servidor. Los gráficos del dashboard se generan como SVG en el servidor, sin JavaScript de terceros. El área de administración de Django solo se usa para catálogos, la matriz de perfiles y los roles, restringida al rol Administrador con sesión MFA.

**Alternativas descartadas.**
- FastAPI + React: obliga a construir a mano CSRF, sesiones, cabeceras y manejo de tokens, que es código crítico de seguridad.
- SPA: sin tiempo real, no aporta valor y agrega CORS, tokens en el navegador y otro contenedor.

**Consecuencias.** Hay protección por defecto contra CSRF, XSS (escape automático), clickjacking y fijación de sesión, y restricciones únicas parciales nativas. La CSP es estricta porque no hay scripts externos.

## ADR-019 — Sin automatizaciones fuera de GLPI ni directorio montado

**Contexto.** Decisión del equipo (07/10/2026): no se automatiza nada fuera de GLPI y no se monta Samba AD en el entregable. Automatizaciones permitidas:
- (a) Creación de tickets por API.
- (b) Reglas de negocio nativas de GLPI (enrutamiento, SLA, escalamiento).
- (d) Tickets con fecha programada.

Excluidas: notificaciones por correo y tareas programadas de la aplicación que creen tickets después.

**Decisión.**
- Toda acción técnica es manual y se documenta con una plantilla de solución obligatoria por cola.
- Las fechas futuras se resuelven creando en la emisión tickets «En espera» con vencimiento (reactivación de vacaciones y eliminación a 90 días).
- Los contratos por vencer se muestran a RRHH como una consulta, no se generan tickets.
- El estado de las cuentas se deriva de los tickets resueltos.

**Consecuencias.**
- Se pierde la reducción automática del tiempo de exposición. El indicador de exposición del dashboard y el SLA de 1 hora con escalamiento pasan a ser el control principal (riesgo residual aceptado).
- La aplicación ya no maneja credenciales de directorios: desaparecen las amenazas sobre Graph y LDAP.
- El estado de las cuentas refleja lo que se documentó, no el estado real del sistema; se rotula así.

## ADR-020 — Dashboard sin tiempo real para técnicos

**Decisión.**
- El dashboard lee los datos de la última sincronización (cada 5 minutos), muestra la hora de actualización y tiene un botón que vuelve a consultar la base de datos.
- Sin websockets, Supabase Realtime ni recarga automática.
- Lo ven solo los roles técnicos.
- Incluye una búsqueda de cuentas con la ficha del colaborador: cuentas, equipos, licencias e historial.
- No incluye el tiempo promedio de atención (decisión del equipo).

**Consecuencias.** Las consultas se agregan en la base de datos con índices adecuados (RNF-06). Cada consulta de ficha se audita (T10).

## ADR-021 — Soporte de vinculación adjunto a GLPI, sin almacenamiento permanente en la aplicación

**Contexto.** Los formularios de referencia de sistemas similares exigen adjuntar el acta de inicio (contratistas) o el acto administrativo de nombramiento (funcionarios) al solicitar un ingreso. Es un control útil: RRHH no emite un ingreso sin respaldo y TI verifica el soporte antes de crear identidades.

**Decisión.**
- El ingreso exige un PDF de máximo 20 MB. La aplicación lo valida por extensión y por firma de contenido (`%PDF-`).
- Lo guarda temporalmente con un nombre aleatorio en un volumen `noexec` compartido por web y worker.
- El worker lo sube una sola vez a GLPI y lo vincula a los tickets de AD y Licencias, que son los que crean identidades. Después borra la copia local y conserva solo los metadatos y el hash SHA-256.
- La aplicación nunca abre, procesa ni sirve el archivo.
- Hay un puerto `AlmacenDeSoportes`, con implementación en disco y un doble en memoria.

**Alternativas descartadas.**
- Guardarlo en la base de datos de Supabase: 20 MB por archivo consumen rápido el límite de 500 MB.
- Supabase Storage: exige otra credencial con privilegios y otra superficie de acceso. Queda como plan B si la API de GLPI no permite subir documentos (R10).
- Escaneo antivirus con ClamAV: un contenedor más y firmas que actualizar. Se acepta como riesgo residual porque el archivo solo lo abren técnicos en GLPI, desde equipos con antivirus.

**Consecuencias.**
- GLPI es el único lugar donde vive el soporte (ahí tiene sus propios respaldos y permisos).
- Si la copia temporal se pierde antes de subirse, la solicitud pasa a `error` y RRHH registra el ingreso de nuevo.
- La subida y vinculación de documentos se valida en el sprint 0.

## ADR-022 — Permisos sobre recursos compartidos dentro de los eventos laborales

**Contexto.** Los formularios de referencia piden, para permisos sobre recursos compartidos: ruta completa, recurso raíz o serie documental, y perfil (Consulta, Edición o Retiro de accesos). El equipo decidió mantenerlo dentro de los eventos laborales.

**Decisión.**
- La matriz de perfiles incluye, por departamento, los recursos con ruta, serie, perfil (Consulta o Edición) y el grupo `FS-*` que lo materializa.
- Los tickets de la cola AD listan esos recursos:
  - ING: aplicar.
  - CDP: aplicar los nuevos y «Retiro de accesos» en los que ya no corresponden.
  - RET y EMG: «Retiro de accesos» en todos.
- La plantilla de solución de AD incluye «ruta – perfil aplicado o retirado».

**Alternativas descartadas.** Un tipo de solicitud de acceso independiente, para permisos fuera de un evento laboral: agrega un flujo completo (registro, aprobación, ticket y revocación) que no está en el alcance.

**Consecuencias.** Un permiso puntual que no corresponda al perfil se tramita directamente en GLPI con sus propios procesos, fuera de la aplicación.

## ADR-023 — BunkerWeb como WAF y proxy inverso (en lugar de nginx y de Application Gateway)

**Contexto.** El equipo pidió Application Gateway. Se verificó su costo en la API de precios de Azure (East US, 07/10/2026): Standard_v2 cuesta unos USD 0,20 por hora más capacidad y WAF_v2 unos USD 0,36 por hora más capacidad, es decir, entre USD 150 y 270 al mes encendido. Agota el crédito de USD 100. El SKU Basic está en preview y no tiene WAF. El equipo tiene un prototipo propio, `waf-stack` (github.com/davcarlos860617/waf-stack, commit 87a5f62 del 08/10/2026), con BunkerWeb (nginx + ModSecurity + OWASP CRS) y reportería en Fluent Bit, Loki y Grafana.

**Decisión.** BunkerWeb 1.6.15 (última estable; los avisos altos de 2026 están corregidos desde 1.6.13) es el único punto de entrada.
- Modo multisitio: `app.*` → web:8000 y `glpi.*` → glpi.
- CRS 4 en `SECURITY_MODE=block`.
- `USE_LIMIT_REQ` con un límite estricto en el inicio de sesión y la verificación TOTP; `USE_BAD_BEHAVIOR` con ban de 1 hora.
- `MAX_CLIENT_SIZE=21m` en `app.*` (el valor por defecto es 10 MB).
- Let's Encrypt automático con el desafío HTTP.

Se reutiliza de `waf-stack`: la estructura de bunkerweb y scheduler, `clasificar.lua`, `loki.yaml`, el dashboard de Grafana y `pruebas.sh`, con estos cambios:

| En `waf-stack` | En este proyecto | Motivo |
|---|---|---|
| `.env` y `reporteria/.env` versionados (hoy con valores de ejemplo) | Solo `.env.example`; los valores vienen de Key Vault → tmpfs | Evitar que una clave real termine en el historial (ADR-009) |
| `API_TOKEN` sin definir (vacío por defecto) | `API_TOKEN` obligatorio en bunkerweb y scheduler | GHSA-79fm-4xj6-pp5g: la API interna sin token permitía escritura arbitraria de archivos (corregido en 1.6.13, pero la autenticación es defensa en profundidad) |
| Interfaz `bw-ui` + MariaDB `bw-db` | Sin interfaz en Azure; scheduler con SQLite (valor por defecto) | La mayoría de los avisos de 2026 están en la interfaz (subida de plugins con ejecución remota, recorrido de rutas, escalada por la cabecera Host); dos contenedores menos; configuración como código |
| Imágenes por etiqueta (`mariadb:11`, `fluent-bit:3.2`) | Fijadas por digest, revisadas con Trivy | Reproducibilidad y cadena de suministro |
| Loki con la cadena de conexión de la cuenta de Storage | Identidad administrada de la VM con rol sobre el contenedor | La cadena da acceso total a la cuenta |
| `blob-init` y Azurite | Solo en local; en Azure el contenedor se crea al aprovisionar | Menos piezas con credenciales en producción |
| `BAD_BEHAVIOR_BAN_TIME=300` | 3600 s, con desbloqueo por línea de comandos | Equilibrio entre protección y las pruebas del equipo |
| App de demostración `whoami` | web (Django) y GLPI, en multisitio | — |

**Reparto de cabeceras.** Django envía la CSP de la aplicación y `X-Frame-Options`; BunkerWeb las conserva (`KEEP_UPSTREAM_HEADERS`) y pone HSTS, `Referrer-Policy` y `X-Content-Type-Options`, además de una CSP por defecto para GLPI. Los estáticos de Django los sirve WhiteNoise.

**Alternativas descartadas.**
- Application Gateway WAF_v2 o Standard_v2: costo (ver contexto).
- Basic: en preview y sin WAF.
- nginx con ModSecurity o Coraza armado a mano: es lo que BunkerWeb ya integra y mantiene.
- Solo Cloudflare: el WAF gestionado completo (OWASP CRS) exige el plan Pro; se evalúa como capa adicional en ADR-024.

**Consecuencias.**
- Se reduce el riesgo pero se agrega una pieza con historial de vulnerabilidades (8 avisos en julio de 2026): se mitiga con versión ≥ 1.6.15, sin interfaz, `API_TOKEN` y red aislada (R13).
- El CRS puede dar falsos positivos en GLPI y en la carga de PDF: se ajusta en el spike 0.6 con exclusiones puntuales versionadas (R12).
- La RAM de la VM se mide en el spike; la reportería es lo primero que se recorta (R11).

Fuentes: prices.azure.com (Application Gateway, eastus) · learn.microsoft.com/azure/application-gateway/overview-v2 · github.com/bunkerity/bunkerweb/security · definiciones de ajustes en `src/common/core/*/plugin.json` de la etiqueta v1.6.15 (MAX_CLIENT_SIZE=10m, API_TOKEN vacío, DATABASE_URI sqlite, KEEP_UPSTREAM_HEADERS, LIMIT_REQ_RATE=2r/s, BAD_BEHAVIOR_BAN_TIME=86400).

## ADR-024 — Cloudflare Tunnel + Access delante de BunkerWeb · PROPUESTA

**Contexto.** El equipo analiza Cloudflare. Datos verificados el 10/10/2026:
- El plan gratuito incluye solo la «Cloudflare Free Managed Ruleset»; el OWASP Core Ruleset y el Managed Ruleset completos requieren Pro.
- Publicar con un túnel con nombre requiere un registro DNS administrado en Cloudflare, es decir, un dominio propio. Los Quick Tunnels (trycloudflare) son solo para pruebas: no requieren cuenta, pero tienen un límite de 200 peticiones simultáneas y URL aleatoria.
- No se pudo verificar en la página oficial el límite de usuarios del plan gratuito de Zero Trust (el análisis previo del equipo habla de 50). Se confirma al crear la cuenta.

**Propuesta (recomendada).** Cloudflare como capa externa y BunkerWeb como segunda capa:
- `cloudflared` en el compose abre un túnel saliente: la VM no expone los puertos 80 ni 443 y el NSG solo permite SSH desde las IP del equipo.
- Cloudflare Access solo delante de `glpi.*` (técnicos y administrador, muy por debajo del límite gratuito). GLPI deja de ser alcanzable de forma anónima, lo que importa porque GLPI publicó correcciones críticas en junio de 2026.
- `app.*` no lleva Access: ya tiene Supabase Auth con TOTP y no conviene un doble inicio de sesión para todos los colaboradores.
- BunkerWeb toma la IP real de `CF-Connecting-IP`, confiando solo en la IP del contenedor `cloudflared` (`USE_REAL_IP`, `REAL_IP_FROM`, `REAL_IP_HEADER`). Sin esto, los límites y los baneos verían una sola IP para todos.
- Los certificados de borde los gestiona Cloudflare; BunkerWeb no necesita Let's Encrypt.

**Costos y condiciones.**
- Hace falta un dominio propio (costo anual, a confirmar).
- Cloudflare termina TLS y ve el tráfico descifrado, incluidos los soportes de vinculación. Con datos reales sería encargado del tratamiento según la Ley 1581 de 2012; con datos ficticios no aplica, pero debe documentarse.
- Agrega una dependencia externa.

**Si se rechaza.** BunkerWeb queda expuesto en 80/443 con Let's Encrypt y DuckDNS (ADR-023), sin otros cambios.

**Pendiente.** Decisión del equipo en la tarea 0.7 del plan. Solo afecta al despliegue (fase 5).

Fuentes: developers.cloudflare.com/waf/managed-rules · developers.cloudflare.com/cloudflare-one/connections/connect-networks/routing-to-tunnel · developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare

## ADR-025 — Tres consultas de lectura nuevas en los repositorios para las vistas

**Contexto.** El núcleo se congeló en el Hito N (`nucleo-v1`) con los repositorios de los casos de uso de escritura y de las consultas del dashboard. Al construir las vistas de la sección 2.7 aparecen tres lecturas que ninguno cubría:
- «Mis solicitudes» (RF-11: el solicitante consulta y cancela las suyas): solicitudes registradas por un usuario.
- La bandeja de RRHH (RF-12): solicitudes pendientes de aprobación.
- El jefe elige entre sus subordinados directos al pedir un CDP o un CSU (SRS 3.3, 4.1).

**Decisión.** Se agregan, sin tocar ningún método existente:
- `RepoSolicitudes.del_solicitante(usuario_id)` y `RepoSolicitudes.pendientes_de_aprobacion()`.
- `RepoColaboradores.subordinados_de(jefe_id)` (excluye a los retirados).

Cada una tiene su prueba en la suite de contrato, que corre contra el doble y contra el ORM. Las vistas no consultan modelos: usan casos de uso de lectura (`MisSolicitudes`, `PendientesDeAprobacion`, `SubordinadosDe`) que devuelven DTOs sin campos restringidos.

**Alternativas descartadas.**
- Filtrar en la vista con `de_colaborador` en un bucle: N consultas y lógica de negocio en la vista.
- Una consulta genérica `buscar_solicitudes(filtro)`: es el «por si acaso» que `CLAUDE.md` prohíbe; hoy hay exactamente tres lecturas.

**Consecuencias.** El contrato crece en tres métodos; los adaptadores existentes (doble y ORM) los implementan en el mismo commit. No cambia ninguna regla del dominio ni de los casos de uso de escritura.

## ADR-026 — Consulta de solicitudes en `error` para el reintento (RF-38)

**Contexto.** RF-38 exige que el Administrador reintente la emisión de una solicitud en `error`. El caso de uso `ReintentarEmision` existe desde el núcleo, pero ningún repositorio lista las solicitudes en ese estado, de modo que la interfaz no puede mostrarlas.

**Decisión.** Se agrega `RepoSolicitudes.en_error()` (por id), con su prueba en la suite de contrato, implementada en el doble y en el ORM en el mismo commit. La vista usa el caso de lectura `SolicitudesEnError`, solo para el Administrador.

**Alternativas descartadas.** Pedir el id a mano (el Administrador no tiene forma de saberlo); reutilizar el indicador (d) del dashboard (solo da conteos y es de los técnicos).

**Consecuencias.** El contrato crece en un método de lectura; no cambia ninguna regla.

## ADR-027 — Matriz y usuarios completos para el área de administración (RF-37)

**Contexto.** RF-37 pide que el Administrador mantenga la matriz de perfiles y los roles desde un área restringida. Los repositorios solo permiten obtener un perfil por (departamento, sede) y un actor activo por id; no hay forma de listar.

**Decisión.** Se agregan `RepoPerfiles.todos()` (por departamento y sede) y `RepoUsuarios.todos()` (activos e inactivos, por id), con su prueba de contrato en el doble y el ORM. El área de administración es propia (vistas sobre casos de uso), **no** el admin de Django: el admin editaría los modelos sin pasar por el dominio (validación de la matriz, incompatibilidad de roles, RF-05) ni por la auditoría (RF-35).

**Alternativas descartadas.** El admin de Django (salta el dominio y la auditoría); cambiar roles solo por línea de comandos (RF-37 pide «área de administración»).

**Consecuencias.** Dos lecturas más en el contrato. Si alguien guarda a mano roles incompatibles en la base, `RepoUsuarios.todos()` falla en lugar de ocultarlo: se corrige con `admin_usuarios`.
