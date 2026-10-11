# Plan de trabajo (SRS v2.2, núcleo primero)

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho (con evidencia) · `[-]` recortado.
Cada ítem tiene un **criterio de verificación** (✔). No se marca `[x]` sin evidencia.
Ítem activo: **1.13** (mutación en curso)

**Regla de orden:** primero el núcleo (Fase 1), completo y congelado en el **Hito N**; después los adaptadores (Fases 2 a 4) y la entrega (Fase 5). Ningún adaptador, vista, contenedor o migración se escribe antes del Hito N, salvo el repositorio base (0.1) y los spikes que alimentan los puertos (0.3).

## Fase 0 — Aprobación y pruebas técnicas (spikes)

- [ ] **0.0 Aprobar el SRS v2.2** con el equipo y el docente.
  ✔ Comentarios incorporados; versión aprobada registrada en "Control del documento".
- [ ] **0.1 Repositorio base:** GitHub con la estructura de `CLAUDE.md`, `.gitignore`, pre-commit (gitleaks, ruff) y protección de `main`.
  ✔ Un commit con un secreto falso es bloqueado.
- [ ] **0.2 Spike de Supabase** (SUP-02, ADR-015). *No bloquea el núcleo; se hace antes de la Fase 2.*
  - Crear los proyectos de desarrollo y de entrega en `us-east-1`.
  - Crear el esquema `app` y el rol `app_backend`.
  - Conectarse desde Django por el *session pooler* con TLS.
  - Confirmar la versión mayor de PostgreSQL para fijar la imagen de pruebas.
  - Comprobar que la actividad del worker evita la pausa (o documentar el procedimiento de reactivación).

  ✔ `migrate` funciona; una petición a `/rest/v1/<tabla>` con la clave `anon` falla; `pg_dump` y `pg_restore` funcionan contra un proyecto vacío.
- [ ] **0.3 Spike de la API de GLPI 11** (SUP-03, SUP-04). **Alimenta el puerto `SistemaDeTickets`: debe estar hecho antes de congelar el núcleo (1.9), o el puerto queda marcado «provisional».** Probar la autenticación de servicio (API v2 con OAuth2 o v1 con tokens); crear un ticket en estado «En espera» con vencimiento; **buscar un ticket por una referencia externa (idempotencia)**; leer estado, solución y documentos; leer activos y licencias por usuario; subir un PDF y vincularlo a dos tickets (R10); ver si se puede exigir la plantilla de solución por categoría.
  ✔ Script que lo demuestra; ADR-014 decidido; hallazgos anotados en `docs/spikes/glpi.md` para ajustar el puerto.
- [ ] **0.4 Spike de Supabase Auth con MFA desde el servidor** (SUP-05). Inicio de sesión con contraseña → inscripción de TOTP (código QR) → desafío → verificación, desde Python. *Antes de la Fase 2.*
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
- [~] **1.13 Compuertas de calidad del núcleo.**
  - Cobertura de ramas ≥ 95 % en `dominio` y ≥ 90 % en `aplicacion` (el SRS exige 80 % en RNF-11; esta es la meta interna).
  - `mypy --strict` y `ruff` sin avisos; `import-linter` en verde.
  - `mutmut` sobre `dominio`: ≥ 85 % de mutantes eliminados; cada superviviente se revisa y se documenta en `docs/spikes/mutacion.md` (equivalente, o falta una prueba y se agrega).
  - Cero pruebas omitidas (`skip`/`xfail`) sin ID de supuesto.

  ✔ Informes de cobertura y mutación adjuntos en `docs/spikes/`.
- [ ] **1.14 Hito N — núcleo congelado.** Revisión del equipo de `docs/supuestos-nucleo.md` y de los puertos; etiqueta `nucleo-v1`.
  ✔ Supuestos aprobados o corregidos; spike 0.3 hecho o puerto `SistemaDeTickets` marcado provisional. A partir de aquí, un cambio en `dominio` o en un puerto exige su test primero y, si cambia un contrato, un ADR.

## Fase 2 — Adaptadores base y seguridad (solo tras el Hito N)

- [ ] **2.1 Proyecto Django** con `src/jml/adaptadores`, `config` que lee `/run/secrets`, logging JSON con filtro de campos prohibidos y `/salud`.
  ✔ `lint-imports` sigue en verde; el log filtra los campos prohibidos.
- [ ] **2.2 `infra/compose.yaml`:** bunkerweb, bw-scheduler, web, worker, glpi y mariadb, más el servicio `admin-usuarios` (perfil aparte). Redes `bw-universe` (aislada), `app` y `db_net` (interna). BunkerWeb en multisitio con `API_TOKEN`, CRS en bloqueo, `MAX_CLIENT_SIZE=21m` en `app.*`, límites (RS-08) y real IP. Django con WhiteNoise, `SECURE_PROXY_SSL_HEADER` y confianza en `X-Forwarded-For` solo desde BunkerWeb. Chequeos de salud, límites de memoria e imágenes por digest.
  ✔ Todo en healthy; `docker port` solo muestra `bunkerweb`; `service_role` no aparece en web ni worker; `pruebas.sh` en verde contra `app.localhost` y `glpi.localhost`; una petición a la API interna sin token es rechazada.
- [ ] **2.3 Persistencia** (RD-01 a RD-03, RD-09 a RD-11, RF-14): modelos, migraciones y repositorios que implementan los puertos; restricción parcial, documento único, disparador de inmutabilidad, `REVOKE` y RLS por `RunSQL`.
  ✔ **La suite de contrato de 1.9 pasa contra PostgreSQL sin cambios**; duplicado abierto falla (incluido el concurrente, CA-01); UPDATE sobre una aprobada falla; UPDATE sobre la auditoría con `app_backend` falla (CA-09).
- [ ] **2.4 Auditoría encadenada sobre PostgreSQL** (adaptador del puerto `Auditoria`) y verificación desde la base.
  ✔ CA-09 contra PostgreSQL.
- [ ] **2.5 Autenticación** (RF-01 a RF-06, RS-08, RS-16): adaptador `ProveedorDeIdentidad` (Supabase Auth), vistas de inicio de sesión, inscripción y verificación de TOTP; sesión de Django; grupos como roles; incompatibilidades; comando `admin-usuarios`.
  ✔ CA-14; con roles incompatibles se recibe 403 y queda en auditoría.
- [ ] **2.6 Semillas** (RD-07): 3 sedes, 6 departamentos, la matriz de perfiles con sus recursos compartidos (§4.9) y 30 colaboradores.
  ✔ Comando idempotente.
- [ ] **2.7 Vistas web:** nueva solicitud, mis solicitudes, bandeja de RRHH y contratos por vencer (RF-28). Solo validan el formulario, verifican el rol y llaman al caso de uso.
  ✔ Pruebas de extremo a extremo por rol.
- [ ] **2.8 Campos restringidos en la persistencia y las vistas** (RD-05).
  ✔ CA-10 completo (logs, respuestas, fichas).
- [ ] **2.9 Carga del soporte de vinculación** (RF-39, RD-12, RS-17): formulario con archivo, adaptador `AlmacenDeSoportes` sobre el volumen `noexec`, validación de firma y tamaño, y límite en BunkerWeb.
  ✔ CA-18 (parte de la carga): un archivo no PDF renombrado a `.pdf` y uno de más de 20 MB se rechazan; el nombre en disco es aleatorio; la suite de contrato de `AlmacenDeSoportes` pasa.

## Fase 3 — Integración con GLPI

- [ ] **3.1 Configuración de GLPI como código:** categorías, 4 grupos más «Revisión manual», reglas de negocio, SLA (incluida la emergencia de 1 h con escalamiento), plantillas de solución por cola, perfil de la cuenta de servicio y doble factor para técnicos.
  ✔ Script reproducible contra un GLPI limpio.
- [ ] **3.2 Adaptador de GLPI + worker de la bandeja de salida** (RF-16 a RF-21, RF-40): implementa `SistemaDeTickets`; incluye subir el soporte una sola vez, vincularlo a los tickets de AD y Licencias y borrar la copia local tras verificar el hash.
  ✔ **La suite de contrato de `SistemaDeTickets` pasa contra GLPI en contenedor sin cambios** (incluida la idempotencia tras timeout); CA-03, CA-04, CA-07 y CA-18 (parte de GLPI).
- [ ] **3.3 Sincronización de tickets, activos y licencias** (RF-22 a RF-26) con el comando `worker`.
  ✔ CA-08; la solicitud se cierra solo con solución y acta.
- [ ] **3.4 Derivación de cuentas sobre datos reales** (RF-27, §4.7).
  ✔ Los escenarios de 1.12 pasan con el adaptador real de GLPI.

## Fase 4 — Dashboard y búsqueda

- [ ] **4.1 Consultas SQL del dashboard** (RF-29, RF-30 a–h, RF-31): agregaciones en la base e índices.
  ✔ CA-15: **el resultado SQL es idéntico al oráculo en memoria de 1.11** con los mismos datos; el percentil 95 está por debajo de 2 s con 300 colaboradores (RNF-06).
- [ ] **4.2 Gráficos SVG en el servidor**, sin JavaScript.
  ✔ La CSP estricta no reporta violaciones.
- [ ] **4.3 Búsqueda de cuentas y ficha del colaborador** (RF-32, RF-33), con auditoría de cada consulta.
  ✔ CA-16.
- [ ] **4.4 Exportación a CSV** (RF-34) — *primer recorte*.

## Fase 5 — Flujos completos y entrega

- [ ] **5.1 Pruebas de extremo a extremo** de ING, VAC, RET y EMG con GLPI en contenedor.
  ✔ CA-05 y CA-06 (los mismos escenarios de 1.12, ahora con los adaptadores reales).
- [ ] **5.2 Despliegue en Azure:** VM, NSG (80/443 públicos y 22 restringido), DuckDNS, Let's Encrypt emitido por BunkerWeb y Key Vault (bootstrap a tmpfs). Si ADR-024 se acepta: `cloudflared`, dominio en Cloudflare, Access para `glpi.*`, real IP desde `CF-Connecting-IP` y NSG sin 80/443.
  ✔ Procedimiento de 10 pasos o menos, ejecutado desde cero por un integrante distinto del autor.
- [ ] **5.3 Respaldos y restauración** (RD-06, RNF-04).
  ✔ CA-11 con evidencia.
- [ ] **5.4 Pruebas de seguridad**, sin WAF (en local) y a través de BunkerWeb (RS-13).
  ✔ CA-12, CA-13 y CA-20; informes adjuntos.
- [ ] **5.5 Reportería del WAF** (RNF-16, debería): Fluent Bit con `clasificar.lua`, Loki con Blob e identidad administrada, y el dashboard de Grafana de `waf-stack` en `127.0.0.1:3000`.
  ✔ CA-21.
- [ ] **5.6 Documentación final:** `docs/SRS.md` actualizado, manual de usuario por rol (incluidas las plantillas de solución para técnicos) y manual de operación.

## Orden de recorte (SRS §14)

Reportería del WAF (RNF-16) → RF-34 (CSV) → RF-30 (g) → gráficos SVG, conservando las tablas. **Nunca se recortan:** RET, EMG, deduplicación, auditoría, MFA, derivación de cuentas, WAF en modo bloqueo e indicadores (a), (c) y (e). **El núcleo (Fase 1) no se recorta**: si falta tiempo, se recortan adaptadores y vistas, no reglas.
