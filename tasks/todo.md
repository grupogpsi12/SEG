# Plan de trabajo (SRS v2.2, núcleo primero)

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho (con evidencia) · `[-]` recortado.
Cada ítem tiene un **criterio de verificación** (✔). No se marca `[x]` sin evidencia.
Ítem activo: **2.2** (necesita Docker: instalación pendiente del equipo, ver `docs/estado.md`). Estado general y traspaso: **`docs/estado.md`**.

**Regla de orden:** primero el núcleo (Fase 1), completo y congelado en el **Hito N**; después los adaptadores (Fases 2 a 4) y la entrega (Fase 5). Ningún adaptador, vista, contenedor o migración se escribe antes del Hito N, salvo el repositorio base (0.1) y los spikes que alimentan los puertos (0.3).

## Fase 0 — Aprobación y pruebas técnicas (spikes)

- [ ] **0.0 Aprobar el SRS v2.2** con el equipo y el docente.
  ✔ Comentarios incorporados; versión aprobada registrada en "Control del documento".
- [ ] **0.1 Repositorio base:** GitHub con la estructura de `CLAUDE.md`, `.gitignore`, pre-commit (gitleaks, ruff) y protección de `main`.
  ✔ Un commit con un secreto falso es bloqueado.
- [~] **0.2 Spike de Supabase** (SUP-02, ADR-015). Hecho lo de la base (`docs/spikes/supabase.md`); falta `pg_dump`/`pg_restore`, la prueba de `/rest/v1` y el proyecto de entrega. *No bloquea el núcleo; se hace antes de la Fase 2.*
  - Crear los proyectos de desarrollo y de entrega en `us-east-1`.
  - Crear el esquema `app` y el rol `app_backend`.
  - Conectarse desde Django por el *session pooler* con TLS.
  - Confirmar la versión mayor de PostgreSQL para fijar la imagen de pruebas.
  - Comprobar que la actividad del worker evita la pausa (o documentar el procedimiento de reactivación).

  ✔ `migrate` funciona; una petición a `/rest/v1/<tabla>` con la clave `anon` falla; `pg_dump` y `pg_restore` funcionan contra un proyecto vacío.
- [ ] **0.3 Spike de la API de GLPI 11** (SUP-03, SUP-04). **Alimenta el puerto `SistemaDeTickets`: debe estar hecho antes de congelar el núcleo (1.9), o el puerto queda marcado «provisional».** Probar la autenticación de servicio (API v2 con OAuth2 o v1 con tokens); crear un ticket en estado «En espera» con vencimiento; **buscar un ticket por una referencia externa (idempotencia)**; leer estado, solución y documentos; leer activos y licencias por usuario; subir un PDF y vincularlo a dos tickets (R10); ver si se puede exigir la plantilla de solución por categoría.
  ✔ Script que lo demuestra; ADR-014 decidido; hallazgos anotados en `docs/spikes/glpi.md` para ajustar el puerto.
- [~] **0.4 Spike de Supabase Auth con MFA desde el servidor** (SUP-05). Adaptador hecho y probado contra un GoTrue simulado; contra el real: error genérico ✔, **registro abierto aún habilitado** ✘ y flujo completo pendiente de la clave `service_role` (`docs/spikes/supabase.md`). Inicio de sesión con contraseña → inscripción de TOTP (código QR) → desafío → verificación, desde Python. *Antes de la Fase 2.*
  ✔ Script que llega a AAL2 con un usuario de prueba; registro abierto deshabilitado comprobado.
- [ ] **0.5 Costos y región en Azure.** Confirmar la región permitida, configurar el apagado automático y una alerta de presupuesto al 50 %. *Antes de la Fase 5.*
  ✔ Capturas de la alerta y del apagado; tabla de costos del SRS actualizada.
- [ ] **0.6 Spike de BunkerWeb** (ADR-023, RS-17 a RS-19, R11, R12). *Antes de la Fase 2 (1.2 de infraestructura).* Partir de `waf-stack` y aplicar los ajustes de ADR-023 (sin interfaz, sin MariaDB para el WAF, `API_TOKEN`, digest, sin `.env` versionado). Modo multisitio `app.localhost` → web y `glpi.localhost` → GLPI.
  - Medir la RAM del stack completo con la reportería.
  - Subir un PDF de 20 MB a través de ModSecurity en modo bloqueo.
  - Recorrer GLPI (crear un ticket con texto enriquecido y adjunto) en modo `detect` y registrar las reglas que saltan.
  - Confirmar el comando de desbloqueo de IP desde el scheduler (`bwcli`).

  ✔ Informe en `docs/spikes/bunkerweb.md` con la RAM medida, las exclusiones necesarias (ruta y regla) y el `pruebas.sh` adaptado en verde.
- [ ] **0.7 Decidir Cloudflare** (ADR-024): el equipo decide si compra un dominio para Tunnel + Access. Solo afecta al despliegue (fase 5), no al desarrollo.
  ✔ ADR-024 pasa a Aceptada o Rechazada.

## Fase 1 — Núcleo (`dominio` + `aplicacion`), sin Django, sin red, sin base de datos

Todo el código de esta fase es Python puro con dobles en memoria. Se construye en este orden; cada ítem termina con sus pruebas escritas **antes o junto** con el código. Instrucciones detalladas en `PROMPT_EJECUCION.md`.

**Dependencias de esta fase (justificación exigida por CLAUDE.md):**

| Paquete | Qué resuelve | Por qué no alcanza la biblioteca estándar | Mantenimiento y licencia |
|---|---|---|---|
| `pytest`, `pytest-cov` | Pruebas y cobertura de ramas | `unittest` no mide ramas ni parametriza con comodidad | Muy activos; MIT |
| `hypothesis` | Pruebas basadas en propiedades (máquina de estados, cadena de hashes, outbox, diferencia de perfiles) | Generar secuencias aleatorias de operaciones a mano son cientos de líneas y no minimizan el contraejemplo | Muy activo; MPL-2.0 |
| `mutmut` | Pruebas de mutación: mide si las pruebas detectan cambios en el código | No existe en la biblioteca estándar | Activo; BSD-3 |
| `ruff`, `mypy`, `import-linter` | Estilo, tipos estrictos y límites de capas | — | Activos; MIT/BSD |
| `mutmut` **2.5.1** (no 3.x) | La versión 3 no corre en Windows (necesita `fork`); el equipo trabaja en Windows | — | Mantenido; BSD-3. Obliga a no usar `type X = …` (PEP 695) en `dominio` |
| `pytest-timeout` (solo desarrollo) | Corta los mutantes que entran en bucle infinito; sin él mutmut 2 se queda colgado en Windows | Un `signal.alarm` no existe en Windows; reimplementarlo con hilos son más de 30 líneas frágiles | Activo; MIT |

- [x] **1.1 Esqueleto del núcleo** (sin Django): `pyproject.toml`, `src/jml/{dominio,aplicacion}`, `tests/{dominio,aplicacion,contratos,dobles,escenarios}`, `ruff`, `mypy --strict`, `import-linter` con los contratos de CA-17, cobertura de ramas, CI mínima (`make verificar`).
  ✔ `lint-imports` falla con un `import django` en `dominio` (test intencional que se revierte); `make verificar` en verde con un test de humo.
  ✔✔ Evidencia: `lint-imports` rompe con `import django` en `dominio` (probado y revertido); además `tests/dominio/test_pureza.py` rechaza cualquier import fuera de la stdlib y las llamadas `now()`/`uuid4()`/`random`. Commit `2f5c879`.

  **Plan de la sesión (1.1 → 1.13).**
  - Entorno: el equipo usa Windows sin `make`; Python local 3.14, el proyecto exige 3.12 → `uv venv --python 3.12` en `.venv/`. El `Makefile` existe (CLAUDE.md) y repite los comandos que yo ejecuto directo. `git init` local (0.1 queda parcial: GitHub, pre-commit y protección de `main` son del equipo).
  - Orden: 1.1 esqueleto → 1.2 supuestos S-01..S-14 → 1.3 tipos/valores/errores → 1.4 `Solicitud` → 1.5 perfiles → 1.6 tickets → 1.7 cierre/cuentas → 1.8 auditoría → 1.9 puertos/dobles/contratos → 1.10 casos de uso → 1.11 consultas → 1.12 escenarios → 1.13 compuertas (cobertura, mypy, mutmut).
  - Fuente de la tabla de transiciones: `docs/img/estados.dot` + tabla §4.2. El diagrama NO tiene `en_ejecucion → error`; el prompt sí. Se sigue el diagrama y se registra S-14 (decisión del equipo).
  - Regla: test primero por cada regla; el ID del requisito va en el nombre del test.
  - Criterio de verificación global: `ruff check . && mypy src tests && lint-imports && pytest` en verde; cobertura de ramas ≥ 95 % dominio / ≥ 90 % aplicación; mutmut ≥ 85 % en dominio.
- [x] **1.2 Registro de supuestos** `docs/supuestos-nucleo.md`: toda interpretación que el SRS deje abierta (lista inicial en `PROMPT_EJECUCION.md` §6) con su valor por defecto, su justificación y su prueba.
  ✔ Cada supuesto tiene ID `S-nn` y una prueba que lo nombra.
  ✔✔ Evidencia: S-01 a S-27 en `docs/supuestos-nucleo.md`; `tests/dominio/test_supuestos.py` verifica que cada ID tiene prueba, que cada prueba citada existe y que no hay IDs huérfanos en el código. 8 supuestos marcados ● para el equipo.
- [x] **1.3 Tipos y errores del dominio:** enumeraciones, objetos de valor (identificadores `SOL-AAAA-NNNNNN`, documento, usuario, fecha efectiva, calendario hábil) y jerarquía de errores de dominio tipados.
  ✔ Pruebas de construcción válida e inválida de cada objeto de valor; ningún error es `ValueError` genérico.
  ✔✔ Evidencia: `tests/dominio/test_valores.py`; `test_ningun_error_de_dominio_es_value_error` y códigos de error únicos.
- [x] **1.4 Agregado `Solicitud`** (RF-07 a RF-15, RF-39): máquina de estados con tabla explícita de transiciones, catálogo de campos por tipo (§4.8), reglas de quién registra qué y sobre quién (§4.1), inmutabilidad tras la aprobación, cancelación, rechazo con justificación, EMG por encima de otras abiertas.
  ✔ Cada celda de la tabla de transiciones (permitida y prohibida) tiene un test; propiedad: ninguna secuencia aleatoria de operaciones deja una solicitud en un estado inalcanzable ni modifica una aprobada.
  ✔✔ Evidencia: `test_cada_celda_estado_x_accion` (7 estados × 8 acciones = 56 celdas), matriz rol × tipo × sujeto exhaustiva, propiedad P2 (`test_P2_recorridos_aleatorios`).
- [x] **1.5 Perfiles y recursos compartidos** (§4.9, RF-16, ADR-022): `PerfilDeAcceso`, recursos con ruta, serie, perfil y grupo, diferencia entre perfiles, «Retiro de accesos» generado por el dominio.
  ✔ CA-19 a nivel de dominio; propiedades: `diferencia(a, a)` vacía y `aplicar(diferencia(a, b), a) == b`.
  ✔✔ Evidencia: CA-19 en `test_perfiles_usuarios_soporte_colaborador.py` y `test_tickets.py`; P5 (tres propiedades) y P6 (usuario sugerido).
- [x] **1.6 Generación de tickets** (RF-16, RF-17, §4.3 a §4.5): matriz evento × cola completa para los 6 tipos y sus subtipos, clases (cierre, programado, posterior), prioridad, SLA con calendario hábil, usuario sugerido (§4.10), contenido mínimo del ticket (RF-20).
  ✔ Una tabla de pruebas parametrizada que reproduce la matriz del SRS celda por celda; propiedad: ningún ticket serializado contiene el valor centinela de un campo restringido ni un campo de contraseña (CA-10 a nivel de dominio).
  ✔✔ Evidencia: `test_matriz_evento_x_cola_celda_por_celda` (14 variantes), P4 con centinela y patrón de contraseñas, SLA por tipo con calendario hábil.
- [x] **1.7 Cierre y derivación de cuentas** (RF-24 a RF-27, §4.7): regla de ticket resuelto, cierre de la solicitud, tabla de derivación completa con «cierre sin solución», «reabierto» y «cambio pendiente».
  ✔ Una prueba por fila de la tabla de derivación y por regla complementaria; propiedad: aplicar dos veces la misma observación equivale a aplicarla una; reabrir devuelve el estado anterior al ticket.
  ✔✔ Evidencia: `test_fila_de_la_tabla_4_7` (8 filas), reglas complementarias, S-09/S-10/S-11, P7 (idempotencia, reapertura y orden entre sistemas), P9 (cierre), y por reflexión `Cuenta` no expone edición (RD-11).
- [x] **1.8 Auditoría encadenada** (RD-03, RF-35, RF-36): serialización canónica, cálculo de la cadena y verificación que indica el primer registro afectado.
  ✔ CA-09 a nivel de dominio; propiedad: alterar cualquier campo de cualquier registro, o quitar, duplicar o reordenar registros, rompe la verificación en el primer afectado.
  ✔✔ Evidencia: vector canónico fijo (`test_formato_canonico_golden_RD_03`), CA-09 y P3 (alterar, quitar, duplicar y reordenar).
- [x] **1.9 Puertos y dobles:** `Repositorios` (con `UnidadDeTrabajo` atómica y la regla de duplicado abierto), `Auditoria`, `SistemaDeTickets` (idempotente por clave, con inyección de fallos), `ProveedorDeIdentidad`, `Reloj` (fijo y avanzable), `AlmacenDeSoportes`. Suite de **pruebas de contrato** parametrizada por implementación, hoy solo con el doble.
  ✔ Los dobles pasan la suite de contrato; la suite está lista para recibir las implementaciones reales sin cambios.
  ✔✔ Evidencia: `tests/contratos/` (≈70 pruebas) contra la fábrica `memoria`; mypy comprueba que cada doble cumple su `Protocol`. `SistemaDeTickets` queda PROVISIONAL: ver `docs/spikes/glpi-puerto.md`.
- [x] **1.10 Casos de uso** (RF-07 a RF-15, RF-18, RF-22 a RF-27, RF-38, RF-39, RF-40 con dobles): registrar, aprobar, rechazar, emitir (en un solo paso y por excepción), cancelar, procesar la bandeja de salida (reintentos, idempotencia, paso a `error`, reintento del Administrador), sincronizar tickets, sincronizar activos y licencias, consultar contratos por vencer (RF-28).
  ✔ CA-01 y CA-02 con dobles; la unidad de trabajo es atómica (si falla la auditoría, no queda decisión ni bandeja de salida).
  ✔✔ Evidencia: `tests/aplicacion/` (registro, decisión, bandeja con P8, sincronización, defensas). CA-02: `test_CA_02_si_falla_la_auditoria_no_queda_decision_ni_bandeja` compara el almacén completo antes y después.
- [x] **1.11 Consultas de lectura** (RF-29 a RF-33): indicadores (a) a (h), búsqueda con filtros y ficha, calculados por el doble en memoria. **El resultado del doble es el oráculo** que después verificará la consulta SQL (CA-15).
  ✔ Con datos de semilla de dominio, cada indicador coincide con una expectativa escrita a mano.
  ✔✔ Evidencia: `tests/aplicacion/test_consultas.py`, una expectativa escrita a mano por indicador (a)–(h), filtros de búsqueda, ficha auditada y sin campos restringidos.
- [x] **1.12 Escenarios de extremo a extremo en memoria:** ING, VAC, CDP, CSU, RET y EMG completos desde el registro hasta `cerrada` y la cuenta derivada, con reloj simulado y un GLPI falso con fallos programados (timeout tras crear, 500, caída larga, ticket reabierto, cierre sin solución, Inventario sin acta).
  ✔ CA-05, CA-06 y CA-07 contra dobles; ninguna ejecución duplica un ticket.
  ✔✔ Evidencia: `tests/escenarios/test_escenarios.py`, 12 escenarios con un verificador común de invariantes (un ticket por clave, cadena válida, sin centinela, sin duplicados abiertos, cuentas = último historial, cerradas con cierre real).
- [x] **1.13 Compuertas de calidad del núcleo.**
  - Cobertura de ramas ≥ 95 % en `dominio` y ≥ 90 % en `aplicacion` (el SRS exige 80 % en RNF-11; esta es la meta interna).
  - `mypy --strict` y `ruff` sin avisos; `import-linter` en verde.
  - `mutmut` sobre `dominio`: ≥ 85 % de mutantes eliminados; cada superviviente se revisa y se documenta en `docs/spikes/mutacion.md` (equivalente, o falta una prueba y se agrega).
  - Cero pruebas omitidas (`skip`/`xfail`) sin ID de supuesto.

  ✔ Informes de cobertura y mutación adjuntos en `docs/spikes/`.
  ✔✔ Evidencia (ver `docs/spikes/mutacion.md`): 1080 pruebas, 0 omitidas · `mypy --strict` y `ruff` sin avisos · `import-linter` 3 contratos cumplidos · cobertura de ramas **dominio 99 %** (meta 95), **aplicacion 99 %** (meta 90), total 99 % · mutación (mutmut 2.5.1, 1340 mutantes): **93,6 % eliminados** (meta 85), 86 supervivientes clasificados: 27 equivalentes y 59 con prueba agregada. **Pendiente de medir:** la tasa tras agregar `test_supervivientes.py` (3.ª corrida interrumpida por decisión del equipo).
  Hallazgos de la revisión del núcleo (`docs/spikes/revision-nucleo.md`): R1 y R2 corregidos con su prueba; R3 y R4 simplificados; R5, R6 y R7 quedan para decisión del equipo.

- [x] **1.14 Hito N — núcleo congelado.** Revisión del equipo de `docs/supuestos-nucleo.md` y de los puertos; etiqueta `nucleo-v1`.
  ✔ Supuestos aprobados o corregidos; spike 0.3 hecho o puerto `SistemaDeTickets` marcado provisional. A partir de aquí, un cambio en `dominio` o en un puerto exige su test primero y, si cambia un contrato, un ADR.
  ✔✔ Evidencia: el equipo aprobó los supuestos S-01 a S-27 con los valores adoptados (10-oct-2026); etiqueta `nucleo-v1`; `SistemaDeTickets` queda PROVISIONAL hasta el spike 0.3 (`docs/spikes/glpi-puerto.md`). Pendiente: repetir `make mutacion` para medir la tasa final.

## Fase 2 — Adaptadores base y seguridad (solo tras el Hito N)

- [x] **2.1 Proyecto Django** con `src/jml/adaptadores`, `config` que lee `/run/secrets`, logging JSON con filtro de campos prohibidos y `/salud`.
  ✔ `lint-imports` sigue en verde; el log filtra los campos prohibidos.

  **Plan (sin Docker: SQLite en memoria solo en las pruebas; PostgreSQL llega en 2.3).**
  - Dependencias de esta fase, ya en la tabla del stack de CLAUDE.md: `django` 5.2 LTS, `django-stubs` 5.2 y `pytest-django`.
  - `src/config/`: `secretos.py` (lee `/run/secrets/<nombre>`; nombre validado contra recorrido de rutas; error que nombra el secreto, nunca su valor), `settings.py`, `urls.py`, `wsgi.py`; `manage.py` en la raíz.
  - Seguridad que es solo configuración: `DEBUG` falso por defecto, `ALLOWED_HOSTS` explícito, cookies `Secure`/`HttpOnly`/`SameSite=Lax`, `X-Frame-Options: DENY` y la CSP de RS-07 desde Django. **No** se duplican HSTS, `Referrer-Policy` ni `nosniff`, que pone BunkerWeb (RS-07).
  - Logging JSON con `correlation_id` y filtro de campos prohibidos (`password`, `token`, `totp`, `secret`, `motivo`, `descripcion`), en `jml/adaptadores/registro.py`.
  - `/salud`: 200 si la base responde, 503 genérico si no (RNF-01), sin detalles internos.
  - `import-linter`: `config` → `adaptadores` → `aplicacion` → `dominio`; el núcleo no puede importar `config` ni `adaptadores`.
  - Fuera de 2.1 (a propósito): confianza en `X-Forwarded-*` solo desde BunkerWeb y WhiteNoise (2.2); sesión de 8 horas máximo (2.5).
  ✔✔ Evidencia: 1129 pruebas (49 de adaptadores); `mypy --strict` con `django-stubs` y `ruff` limpios; `import-linter` cumple y **rompe** si `aplicacion` importa `config` o si `dominio` importa `jml.adaptadores` (probado y revertido); los logs filtran `password`, `token`, `totp`, `secret`, `motivo` y `descripcion` (también anidados) y un `CampoRestringido` se imprime `<oculto>`; `/salud` responde 200 o 503 genérico; la CSP y `X-Frame-Options` salen de Django y las demás cabeceras no se duplican; `manage.py check --deploy` sin avisos (solo se silencian los cuatro que resuelve BunkerWeb). Cobertura de `config` + `adaptadores`: 97 % (`wsgi.py` se prueba en 2.2 con gunicorn). Nueva dependencia: `psycopg[binary]` 3 (driver de PostgreSQL, ya en la tabla de herramientas del SRS).
- [~] **2.2 `infra/compose.yaml`:** bunkerweb, bw-scheduler, web, worker, glpi y mariadb, más el servicio `admin-usuarios` (perfil aparte). Redes `bw-universe` (aislada), `app` y `db_net` (interna). BunkerWeb en multisitio con `API_TOKEN`, CRS en bloqueo, `MAX_CLIENT_SIZE=21m` en `app.*`, límites (RS-08) y real IP. Django con WhiteNoise, `SECURE_PROXY_SSL_HEADER` y confianza en `X-Forwarded-For` solo desde BunkerWeb. Chequeos de salud, límites de memoria e imágenes por digest.
  ✔ Todo en healthy; `docker port` solo muestra `bunkerweb`; `service_role` no aparece en web ni worker; `pruebas.sh` en verde contra `app.localhost` y `glpi.localhost`; una petición a la API interna sin token es rechazada.
  ✔ Escrito y probado sin Docker (11/10/2026): `Dockerfile` (base por digest, dependencias con hash desde `requirements.lock`, usuario sin root, `collectstatic` con secretos de un solo uso, gunicorn 1 proceso × 8 hilos por S-29), `infra/compose.yaml` (bunkerweb + scheduler en multisitio sin interfaz, web, worker, admin-usuarios en perfil `admin`, GLPI 11.0.11, MariaDB 11.4; todo por digest; redes `bw-universe`, `app` con IP fija de bunkerweb y `db_net` interna; `read_only`, `cap_drop`, límites de memoria y chequeos de salud), `infra/compose.azure.yaml` (Let's Encrypt y soportes en un sistema de archivos `noexec`), `infra/scripts/preparar-entorno.sh`, `infra/waf/pruebas.sh` adaptado y `infra/bunkerweb/configs/README.md`. Django: WhiteNoise y `proxy_confiable` (RS-05). `tests/adaptadores/test_infra.py` vigila RS-02, RS-03, RS-05, RS-08, RS-17, RS-18, RS-19 y los invariantes 8 y 14 sin Docker.
  ⏳ Falta lo que exige Docker: `up --build`, todo healthy, `pruebas.sh` en ambos sitios, API sin token rechazada, y confirmar los nombres de ajustes de BunkerWeb (spike 0.6). `infra/.env.example` no se pudo crear por una regla de permisos del asistente; su contenido está en `docs/estado.md`.
  **Dependencias nuevas:** `whitenoise` 6 (MIT; estáticos sin nginx, ADR-023), `gunicorn` 23 (MIT; servidor WSGI del stack), y solo para pruebas `pyyaml` 6 (MIT; leer el compose en `test_infra.py`, la biblioteca estándar no lee YAML).
- [~] **2.3 Persistencia** (RD-01 a RD-03, RD-09 a RD-11, RF-14): modelos, migraciones y repositorios que implementan los puertos; restricción parcial, documento único, disparador de inmutabilidad, `REVOKE` y RLS por `RunSQL`.
  ✔ **La suite de contrato de 1.9 pasa contra PostgreSQL sin cambios**; duplicado abierto falla (incluido el concurrente, CA-01); UPDATE sobre una aprobada falla; UPDATE sobre la auditoría con `app_backend` falla (CA-09).

  **Plan (sin Docker todavía).**
  - App de Django `jml.adaptadores.salida.persistencia`: modelos, migraciones y mapeo modelo ↔ entidad (los modelos no son el dominio).
  - Las restricciones viven en la base: índice único parcial de solicitudes abiertas (RD-01) y documento único entre no retirados (RD-09) con `UniqueConstraint(condition=…)`. El código solo traduce el `IntegrityError` al error del puerto.
  - Solo en PostgreSQL, por `RunSQL`: el disparador de inmutabilidad (RF-14); el `REVOKE` de UPDATE, DELETE y TRUNCATE sobre `auditoria`, `decision` y `cuenta_historial` (RD-02); y RLS sin políticas (RD-10). El repositorio repite la comprobación de RF-14 como defensa en profundidad.
  - Unidad de trabajo = `transaction.atomic()`. La auditoría serializa la cadena bloqueando una fila candado (`select_for_update`), para que dos escritores no bifurquen la cadena.
  - La suite de contrato gana una segunda fábrica, `orm`, que hoy corre sobre SQLite en memoria **sin modificar las pruebas**.
  - `tests/integracion/` (fuera de `make verificar`) agrega lo exclusivo de PostgreSQL: duplicado concurrente (CA-01), UPDATE sobre una aprobada, UPDATE y DELETE sobre la auditoría con `app_backend`, y la fábrica `orm` contra PostgreSQL. Se activa con `JML_DB_PRUEBAS`.
  - Las consultas del dashboard (`indicadores`) se implementan de forma directa y se comparan con el oráculo; su versión agregada en SQL es el ítem 4.1.
  ✔ Hecho sin PostgreSQL (evidencia): modelos y migraciones (0001 generada; 0002 con disparador, REVOKE y RLS solo para PostgreSQL); repositorios, unidad de trabajo y auditoría encadenada con fila candado sobre el ORM. **La suite de contrato pasa con la fábrica `orm` (SQLite) sin cambiar una sola expectativa**: 69 pruebas, más las 69 del doble. Solo se agregaron los datos padre que exigen las claves foráneas (lessons n.º 27). CA-15 adelantado: indicadores (a) a (h) agregados en la base con `COUNT`/`MIN … GROUP BY`, búsqueda y ficha **idénticos al oráculo** en un barrido de instantes que cruza cada borde (la prueba detectó 8 de 8 cambios introducidos a propósito en las consultas). Mapeo: ida y vuelta de los 6 tipos, de los 55 tickets dorados, y error tipado ante datos corruptos. Cobertura de `adaptadores`: 98 %.
  ⏳ Pendiente (necesita PostgreSQL, Docker o Supabase): correr `tests/integracion` y la suite de contrato con `--ds tests.integracion.ajustes` (CA-01 concurrente, RF-14 por disparador, RD-02 REVOKE, RD-10 RLS).
- [~] **2.4 Auditoría encadenada sobre PostgreSQL** (adaptador del puerto `Auditoria`) y verificación desde la base.
  ✔ CA-09 contra PostgreSQL.
  ✔✔ Adaptador `AuditoriaDjango` con fila candado para la secuencia; CA-09 y el REVOKE probados contra Supabase (`tests/integracion/test_postgresql.py`); verificación desde la interfaz en 2.11. ✔ RD-04 escrito (11/10/2026): caso `ExportarAuditoria` (registros del día en forma canónica con sus hashes, verificables sin la base, más el **ancla** = cabeza de toda la cadena, que delata una reescritura completa: revisión externa H1, punto 3); el worker deja `auditoria-AAAA-MM-DD.jsonl` y `ancla-AAAA-MM-DD.json` en el volumen `exportes` una vez al día, de forma idempotente; `infra/scripts/subir-exportes.sh` los sube a Blob inmutable con la identidad de la VM. `tests/adaptadores/test_exportacion_auditoria.py`. ⏳ Probar la subida en Azure (5.2).
- [x] **2.5 Autenticación** (RF-01 a RF-06, RS-08, RS-16): adaptador `ProveedorDeIdentidad` (Supabase Auth), vistas de inicio de sesión, inscripción y verificación de TOTP; sesión de Django; grupos como roles; incompatibilidades; comando `admin-usuarios`.
  ✔ CA-14; con roles incompatibles se recibe 403 y queda en auditoría.
  ✔✔ Evidencia: `ProveedorSupabase` (API REST de GoTrue con `httpx`) pasa la suite de contrato del puerto sin cambios contra un GoTrue simulado; 21 pruebas propias (token AAL1 solo en memoria 5 min y 5 intentos —S-29—, logout de Supabase al llegar a AAL2, sin inscribir un segundo factor con solo la contraseña, comprobación de `aal2`, errores de red sin detalles). Caso de uso `CompletarIngreso` audita `sesion.iniciada` / `sesion.denegada` (RF-05 probado con grupos incompatibles en la base). Vistas `/ingreso`, `/ingreso/segundo-factor` y `/salir`: 13 pruebas de extremo a extremo (CA-14 sin código no hay sesión, RF-02 inscripción con clave manual —S-30—, error genérico, id de sesión rotado, sin tokens en la sesión, `no-store`, 8 h máximo y 30 min de inactividad —RF-04—). Comando `admin_usuarios crear|desactivar` (RF-06, S-31): 7 pruebas, incluida la compensación si la base falla. Suite: 1349 pruebas, cobertura 98 %.
  ⏳ Contra el Supabase real falta: deshabilitar el registro abierto y crear `secrets/supabase_service_role` (acciones del equipo, `docs/spikes/supabase.md`). CA-14 «el sexto intento en un minuto se bloquea» es de BunkerWeb (2.2).
  **Dependencia nueva:** `httpx` 0.28 (BSD-3, muy activo; ya en la tabla del stack para GLPI). Resuelve HTTP con timeouts y un transporte simulable en pruebas (`MockTransport`); `urllib` no permite simular el servidor sin parchear y exigiría más de 30 líneas de manejo de errores.
- [x] **2.6 Semillas** (RD-07): 3 sedes, 6 departamentos, la matriz de perfiles con sus recursos compartidos (§4.9) y 30 colaboradores.
  ✔ Comando idempotente.
  ✔✔ Evidencia: `python manage.py semillas` crea 18 perfiles y 30 colaboradores con 48 eventos de auditoría; la segunda corrida cambia 0 y no audita nada. La matriz de las semillas coincide celda por celda con la transcripción independiente de `tests/fabricas.py`. **Decisión:** no siembra cuentas (invariante 6: solo nacen de tickets resueltos) ni usuarios (los crea `admin-usuarios`, RF-06); 10 contratistas con fin escalonado alimentan RF-28.
- [x] **2.7 Vistas web:** nueva solicitud, mis solicitudes, bandeja de RRHH y contratos por vencer (RF-28). Solo validan el formulario, verifican el rol y llaman al caso de uso.
  ✔ Pruebas de extremo a extremo por rol.
  ✔✔ Evidencia: `tests/adaptadores/test_vistas.py` (36 pruebas con el cliente de Django sobre el ORM) cubre sesión, CSRF, método, rol por ruta (403/404), vacaciones y renuncia del colaborador, CDP/CSU del jefe (solo sus subordinados), bandeja de RRHH con contratos por vencer, aprobar/rechazar/cancelar, emisión por documento, emergencia con fecha de hoy, ingreso con soporte PDF (rechazo por contenido) y emisión por excepción del Administrador. Suite completa: 1302 pruebas, cobertura 98 %.
  **Decisiones:** (1) la identidad llega en `request.session["usuario_id"]`, que creará 2.5 tras verificar el TOTP; sin sesión → `/ingreso`. (2) Los roles se leen de la base en cada petición (`MiPerfil`), no de la sesión: desactivar a alguien cierra su sesión. (3) La lógica de «a quién afecta» y de permisos sigue en el dominio; la vista solo elige el caso (registrar / emitir / emitir por excepción). (4) Los errores se traducen con `mensajes.texto_del_error`; nunca se muestra el detalle interno ni un campo restringido. (5) Sin JavaScript: CSS propio en `static/web/estilo.css`.
  ⏳ Pendiente de otros ítems: pantalla de ingreso (2.5), WhiteNoise y límite de tamaño en BunkerWeb (2.2/2.9), búsqueda del jefe/colaborador por nombre en lugar de ids para `jefe_id` y `jefe_nuevo_id` (mejora de usabilidad, no de seguridad).
- [x] **2.8 Campos restringidos en la persistencia y las vistas** (RD-05).
  ✔ CA-10 completo (logs, respuestas, fichas).
  ✔✔ Evidencia: caso `ConsultarSolicitud` y vista `/solicitudes/<id>`: RRHH ve el motivo o la descripción (página `no-store`, consulta auditada como `restringido.consultado`); quien registró ve el detalle sin el campo; los demás reciben 404 (no se confirma que el id exista). `tests/adaptadores/test_restringidos.py` recorre todas las páginas con los 9 roles no-RRHH tras un RET, una EMG y una renuncia con el centinela, y comprueba que no aparece en ninguna respuesta, ni en la auditoría, ni en ningún log capturado del proceso. Persistencia: el campo vive solo en `solicitud_restringida` (2.3). Fichas: el DTO no tiene el campo (1.11). GLPI: el generador de tickets ya lo excluye (1.6); se revalida con el adaptador real en 3.2.
- [~] **2.9 Carga del soporte de vinculación** (RF-39, RD-12, RS-17): formulario con archivo, adaptador `AlmacenDeSoportes` sobre el volumen `noexec`, validación de firma y tamaño, y límite en BunkerWeb.
  ✔ CA-18 (parte de la carga): un archivo no PDF renombrado a `.pdf` y uno de más de 20 MB se rechazan; el nombre en disco es aleatorio; la suite de contrato de `AlmacenDeSoportes` pasa.
  ✔ Hecho (adaptador): `AlmacenDeSoportesEnDisco` pasa la suite de contrato sin cambios (fábrica `orm`, sobre `tmp_path`): nombre aleatorio de 32 hex sin extensión, creación exclusiva con 0o600, y un nombre manipulado en la base no sale del volumen. ⏳ Falta el formulario de carga (con 2.7) y el límite en BunkerWeb (2.2).

- [x] **2.10 Ingresos fallidos en la auditoría** (RF-35): contraseña o código TOTP rechazados quedan como `sesion.fallida`, sin la contraseña ni el código.
  ✔ Prueba: un intento fallido deja un registro y el contenido no incluye la contraseña.
  ✔✔ `IniciarIngreso` y `CompletarIngreso` auditan `sesion.fallida` (`paso`: `contrasena` o `totp`; objeto: el correo normalizado o el id de Supabase del primer factor). Pruebas en `tests/aplicacion/test_ingreso.py`. El volumen lo acota el límite de BunkerWeb (RS-08).
- [x] **2.11 Vista del Auditor** (RF-36, CA-09): consultar la auditoría (paginada) y verificar la cadena desde la interfaz, mostrando el primer registro afectado. Solo el rol Auditor.
  ✔ 403 para los demás roles; con un registro alterado en la base, la vista muestra la posición del primero afectado.
  ✔✔ Casos `ConsultarAuditoria` (50 por página, del más reciente) y `VerificarAuditoria` (la verificación queda auditada como `auditoria.verificada`). Vista `/auditoria` (GET consulta, POST verifica). `tests/adaptadores/test_auditor_web.py`: 403 para RRHH, Administrador, técnico y solicitante; un `UPDATE` directo sobre `auditoria` hace que la vista informe «cadena ROTA, posición 1» (CA-09 por la interfaz).
- [x] **2.12 Reintento de emisión** (RF-38): el Administrador ve las solicitudes en `error` y las devuelve a la bandeja. Requiere la consulta `solicitudes.en_error()` (ADR-026).
  ✔ 403 para los demás; tras el reintento, la solicitud sale de la lista y la bandeja vuelve a intentar.
  ✔✔ ADR-026 (`RepoSolicitudes.en_error()`, con su prueba de contrato en doble y ORM), caso `SolicitudesEnError`, vistas `/errores` y `POST /solicitudes/<id>/reintentar` (usa `ReintentarEmision` del núcleo). `tests/adaptadores/test_reintento_web.py`: el Administrador reintenta un ingreso en `error` y desaparece de la lista; los demás roles reciben 403 y el mensaje de «sin permiso» (lección 30).
- [x] **2.13 Área de administración** (RF-37): matriz de perfiles, catálogos y roles, solo para el Administrador, con auditoría de cada cambio (RF-35) y validación de incompatibilidades (RF-05).
  ✔✔ ADR-027 (`RepoPerfiles.todos()` y `RepoUsuarios.todos()`, con contrato en doble y ORM) y área propia, no el admin de Django: casos `ConsultarMatriz`, `GuardarPerfil` (audita `perfil.actualizado`), `ConsultarUsuarios` y `CambiarRoles` (RF-05 por el dominio, audita `usuario.roles_cambiados`; nadie cambia sus propios roles). Vistas `/administracion/perfiles`, `/administracion/perfil` y `/administracion/usuarios`. Pruebas: `tests/aplicacion/test_administracion.py` (10) y `tests/adaptadores/test_administracion_web.py` (11). Catálogos = la matriz (S-32). Crear y desactivar cuentas sigue en el comando `admin_usuarios` (RF-06).

- [x] **2.14 Revisión externa del 11/10/2026** (sobre `693f51c`; texto completo en `docs/spikes/revision-externa-2026-10-11.md`).
  - [x] **H1 (alta)** `app_backend` era dueño de las tablas. ✔✔ ADR-028: `app_owner` es dueño y migra (contenedor `migrar`); `app_backend` con permisos mínimos (migración 0004) y `BYPASSRLS`; aprovisionado en Supabase con `infra/supabase/duenio-separado.sql`. Pruebas H1 en verde contra Supabase.
  - [x] **H2 (media)** El disparador no validaba transiciones. ✔✔ Migración 0003 con el cierre transitivo de `TRANSICIONES`; `test_migraciones.py` impide que se separen; pruebas H2 en verde contra Supabase.
  - [x] **H3 (media)** Dos aprobaciones simultáneas se aceptaban. ✔✔ `select_for_update(of=("self",))` en `RepoSolicitudes.obtener`; pruebas concurrentes (dos aprobadores; aprobar contra cancelar) en verde contra Supabase. Cierra R1.
  - [x] M1 el filtro de logs recorre listas y tuplas (`test_M1_tambien_dentro_de_listas_y_tuplas`).
  - [x] M2 `Makefile` para Windows y Linux.
  - [x] M3 CI en `.github/workflows/verificar.yml`: compuertas + integración contra `postgres:17` (acciones por SHA). Se activa cuando exista el repositorio en GitHub (0.1).
  - [-] M4 `skip_locked` en `vencidas()`: **no se aplica**. `vencidas()` corre en una unidad de trabajo corta y cada entrada se procesa en otra, así que el bloqueo se libera antes de procesar y no protegería a dos workers. Hay un solo worker por diseño y la clave de idempotencia evita duplicar en GLPI. Si algún día hay más de uno, hace falta un arriendo de la entrada (estado «en proceso» con vencimiento).
  - [x] M5 ya estaba resuelto en 2.5 (30 minutos y 8 horas).
  - [x] M6 `mensajes.py` al 100 % (`tests/adaptadores/test_mensajes.py`).

## Fase 3 — Integración con GLPI

- [~] **3.1 Configuración de GLPI como código:** categorías, 4 grupos más «Revisión manual», reglas de negocio, SLA (incluida la emergencia de 1 h con escalamiento), plantillas de solución por cola, perfil de la cuenta de servicio y doble factor para técnicos.
  ✔ Script reproducible contra un GLPI limpio.
  ✔ Escrito sin GLPI real (11/10/2026), **PROVISIONAL hasta el spike 0.3**: `adaptadores/salida/glpi/configuracion.py` y el comando `configurar_glpi` (contenedor `configurar-glpi`, perfil `admin`, con un token de administrador de GLPI que el worker nunca monta). Idempotente; crea 5 grupos, 114 categorías (`categorias()` cubre todas las que produce el dominio: lo comprueba la prueba dorada), 6 reglas (una por cola, «Revisión manual» sin categoría y el SLA de emergencia por prioridad muy alta), el SLA de 1 hora con escalamiento a «Revisión manual» (S-33) y las 4 plantillas de solución de §4.6 sin contraseñas (T9). `tests/adaptadores/test_glpi_configuracion.py`. ⏳ Confirmar códigos de condición y acción de las reglas, y hacer a mano: habilitar la API, perfil de servicio y doble factor de técnicos (`docs/operacion.md`).
- [~] **3.2 Adaptador de GLPI + worker de la bandeja de salida** (RF-16 a RF-21, RF-40): implementa `SistemaDeTickets`; incluye subir el soporte una sola vez, vincularlo a los tickets de AD y Licencias y borrar la copia local tras verificar el hash.
  ✔ **La suite de contrato de `SistemaDeTickets` pasa contra GLPI en contenedor sin cambios** (incluida la idempotencia tras timeout); CA-03, CA-04, CA-07 y CA-18 (parte de GLPI).
  ✔ Escrito sin GLPI real (11/10/2026), **PROVISIONAL hasta el spike 0.3**: `adaptadores/salida/glpi/cliente.py` (`SistemaDeTicketsGlpi`, API REST v1 `apirest.php`). La suite de contrato de `SistemaDeTickets` (17 pruebas) pasa **sin cambios** contra un GLPI simulado sobre HTTP (`tests/dobles/glpi_api.py`, fábrica `glpi_api`), con caída, error antes de escribir, timeout después de escribir y petición duplicada. Además, `tests/adaptadores/test_glpi_cliente.py` (sesión que vence, credenciales, prioridad, categoría, purga de duplicados, búsqueda por subcadena, RF-20). Cobertura 97 %. El worker lo arma con los secretos `glpi_app_token` y `glpi_user_token`, que solo monta él.
  **Decisiones** (detalle en `docs/spikes/glpi-puerto.md`): la clave va en `externalid`, que GLPI no hace única, así que tras crear se purgan los duplicados; documentos buscados por `sha1sum` antes de subir y SHA-256 calculado descargando (lessons n.º 24, opción a); usuarios por `registration_number` = id del colaborador, sin credenciales; activos = `Computer` del usuario con la entrega de `Infocom` y el acta = documento vinculado; licencias = `SoftwareLicense` con `users_id`.
  ⏳ Falta: el spike 0.3 contra GLPI 11 real (cada punto marcado «spike 0.3» en el código) y CA-18 de extremo a extremo.
- [~] **3.3 Sincronización de tickets, activos y licencias** (RF-22 a RF-26) con el comando `worker`.
  ✔ Los casos `SincronizarTickets` y `SincronizarActivos` (núcleo) corren en el ciclo del worker cada 5 minutos con el adaptador de 3.2; latido para el chequeo de salud. ⏳ Probar contra GLPI real.
  ✔ CA-08; la solicitud se cierra solo con solución y acta.
- [ ] **3.4 Derivación de cuentas sobre datos reales** (RF-27, §4.7).
  ✔ Los escenarios de 1.12 pasan con el adaptador real de GLPI.

## Fase 4 — Dashboard y búsqueda

- [~] **4.1 Consultas SQL del dashboard** (RF-29, RF-30 a–h, RF-31): agregaciones en la base e índices.
  ✔ CA-15: **el resultado SQL es idéntico al oráculo en memoria de 1.11** con los mismos datos; el percentil 95 está por debajo de 2 s con 300 colaboradores (RNF-06).
  ✔✔ Hecho: las consultas del ORM (`persistencia/consultas.py`) dan lo mismo que el oráculo en ~230 instantes con bordes (`test_persistencia_oraculo.py`, SQLite y PostgreSQL). ⏳ Falta: índices y medir el p95 con 300 colaboradores sobre PostgreSQL (necesita una semilla grande). **No medir contra Supabase desde Colombia**: la latencia de red (~150 ms por consulta) domina el resultado; medir con PostgreSQL 17 local en Docker o desde la VM de Azure (misma región que Supabase).
- [x] **4.2 Gráficos SVG en el servidor**, sin JavaScript.
  ✔ La CSP estricta no reporta violaciones.
  ✔✔ `web/graficos.py` (barras de (a) y (e), cola propia resaltada): único `mark_safe`, con etiquetas escapadas y valores enteros; sin `<script>` ni recarga (`test_tecnicos_web.py`). La revisión con las herramientas del navegador queda para 5.4.
- [x] **4.3 Búsqueda de cuentas y ficha del colaborador** (RF-32, RF-33), con auditoría de cada consulta.
  ✔ CA-16.
  ✔✔ Vistas `/dashboard`, `/cuentas`, `/colaboradores/<id>` (`web/tecnicos.py`): 403 para roles no técnicos (CA-15), filtros y paginación, parámetros manipulados → 404, ficha sin centinela y auditada (`ficha.consultada`), enlaces a GLPI con `JML_GLPI_URL` (la web no llama a GLPI).
- [x] **4.4 Exportación a CSV** (RF-34) — *primer recorte*.
  ✔✔ `/cuentas.csv` con el caso `ExportarCuentas` (todas las páginas, tope 5000, auditado como `cuentas.exportadas` con el filtro: T10), BOM para Excel, `no-store` y celdas que empiezan con `= + - @` neutralizadas (inyección CSV).

## Fase 5 — Flujos completos y entrega

- [ ] **5.1 Pruebas de extremo a extremo** de ING, VAC, RET y EMG con GLPI en contenedor.
  ✔ CA-05 y CA-06 (los mismos escenarios de 1.12, ahora con los adaptadores reales).
- [ ] **5.2 Despliegue en Azure:** VM, NSG (80/443 públicos y 22 restringido), DuckDNS, Let's Encrypt emitido por BunkerWeb y Key Vault (bootstrap a tmpfs). Si ADR-024 se acepta: `cloudflared`, dominio en Cloudflare, Access para `glpi.*`, real IP desde `CF-Connecting-IP` y NSG sin 80/443.
  ✔ Procedimiento de 10 pasos o menos, ejecutado desde cero por un integrante distinto del autor.
- [~] **5.3 Respaldos y restauración** (RD-06, RNF-04).
  ✔ Escrito sin Azure: `infra/scripts/respaldo.sh` (`pg_dump` del esquema `app` como `app_owner` por TLS + `mariadb-dump` de GLPI, subidos a Blob con la identidad de la VM); restauración en `docs/operacion.md`. ⏳ Ejecutarlo y probar la restauración con evidencia (CA-11).
  ✔ CA-11 con evidencia.
- [ ] **5.4 Pruebas de seguridad**, sin WAF (en local) y a través de BunkerWeb (RS-13).
  ✔ CA-12, CA-13 y CA-20; informes adjuntos.
- [ ] **5.5 Reportería del WAF** (RNF-16, debería): Fluent Bit con `clasificar.lua`, Loki con Blob e identidad administrada, y el dashboard de Grafana de `waf-stack` en `127.0.0.1:3000`.
  ✔ CA-21.
- [~] **5.6 Documentación final:** `docs/SRS.md` actualizado, manual de usuario por rol (incluidas las plantillas de solución para técnicos) y manual de operación.
  ✔ Parcial (11/10/2026): `docs/manual-usuario.md` por rol (ingreso con TOTP, solicitante, jefe, RRHH, técnicos, Auditor y Administrador) y `docs/estado.md` (estado y traspaso). ⏳ Faltan las plantillas de solución por cola (dependen de 3.1) y el manual de operación (dependen de 2.2 y 5.2).

## Orden de recorte (SRS §14)

Reportería del WAF (RNF-16) → RF-34 (CSV) → RF-30 (g) → gráficos SVG, conservando las tablas. **Nunca se recortan:** RET, EMG, deduplicación, auditoría, MFA, derivación de cuentas, WAF en modo bloqueo e indicadores (a), (c) y (e). **El núcleo (Fase 1) no se recorta**: si falta tiempo, se recortan adaptadores y vistas, no reglas.
