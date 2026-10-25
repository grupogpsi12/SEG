# Estado de la auditoría

**Plan:** `docs/PLAN_AUDITORIA.md` (v2.0) · **Base auditada:** `grupogpsi12/SEG` `master` en `5fa3f32` · **Rama de trabajo:** `auditoria/entrega` · **Inicio:** 24/10/2026 (UTC 25/10).

Este archivo es la **única fuente de qué sigue** (prompt §17.1.4). El ítem activo es el primero pendiente cuyas dependencias están verificadas. Un ítem no pasa a ✔ sin su evidencia (`cmd.txt`, `salida.txt`, versión, commit, fecha UTC y sha256 en `auditoria/evidencia/` y `manifiesto.sha256`) y, si vigila un control, sin que la prueba falle al quitarlo.

**Leyenda.** ✔ verificado · ◐ en curso · ○ pendiente · ⛔ bloqueado `[PENDIENTE: motivo]` · ✖ no aplica (con motivo).

**Compuertas por fase (§9.1).** F0–F2 → G0, G1b · F3 → G2 · F4 → G1 · F5–F6 → G5 (parcial) · F7 → G3 · F8 → G4 · F9 → G5 completa.

## F0 — Preparación

| ID | Tarea | Criterio de verificación (binario) | Depende | Estado |
|---|---|---|---|---|
| F0-01 | Leer los documentos en el orden del prompt y colocar el plan en `docs/PLAN_AUDITORIA.md` | El plan está en `docs/`; ninguna orden de escaneo se dio antes de terminar F0 | — | ✔ |
| F0-02 | Rama `auditoria/entrega` y estructura de `auditoria/` | La rama existe y `auditoria/{hallazgos,herramientas,scripts,controles-positivos,evidencia/*}` existen | F0-01 | ✔ |
| F0-03 | Herramientas de la auditoría: `enmascarar.py`, `registrar.py`, `marcadores.py`, `trazar.py`, `congelar-herramientas.py`, `herramientas.lock`, `dread-anclas.md` | Cada herramienta con autoprueba o uso real; `enmascarar.py --probar` falla si el enmascarador no hace nada | F0-02 | ✔ |
| F0-04 | Confirmar o refutar D-01…D-12 contra el código real | 12 veredictos con evidencia registrada; los confirmados tienen `hallazgos/B-nn.md` | F0-03 | ✔ |
| F0-05 | `trazabilidad.csv` con una fila por cada RF, RNF, RS, RD, RI, CA, T y N | 141 filas, generadas por `trazar.py` (reproducible) | F0-03 | ✔ |
| F0-06 | Stack local y contenedores de auditoría | Los 10 contenedores `healthy` y `infra/waf/pruebas.sh app.localhost` en verde | F0-02 | ✔ (hallazgo B-01 en el camino) |
| F0-07 | Línea base en verde **antes de tocar el código**: la suite en un `git worktree` del commit `5fa3f32` | 0 fallos; la cifra de pruebas queda en `metricas.json` | F0-06 | ✔ 1618 pruebas en verde (F1-01-LINEA-BASE) |

**Resultado de F0-04.** Confirmados: D-01, D-04, D-05, D-06, D-07, D-08, D-09, D-10, D-11, D-12. **Pendientes de medición (F6):** D-02 (la Entrega 3 no está en el repositorio: `casos-de-uso.txt` no existe, no es verificable desde archivos) y D-03 (el límite de 2 r/s es plausible pero no medido). Correcciones al plan: D-11 son 22 patrones de URL (24 si se cuenta cada acción de `decidir`). **Hallazgos nuevos de F0:** B-01 (IP de confianza de bunkerweb no reservada), B-03 (deriva en `estado.md`).

## F1 — Línea base medida

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F1-01 | Suite unitaria con cobertura de ramas (los comandos de `make verificar`, que no está instalado aquí) | 0 fallos; dominio ≥ 95 % y aplicación ≥ 90 %; `junit.xml` y el reporte guardados | F0-07 | ✔ dominio 97,74 % y aplicación 94,4 % de ramas (F1-01-COBERTURA); B-13, B-14 |
| F1-02 | Integración contra PostgreSQL 17 (`integracion-local.sh`) | 0 fallos | F1-01 | ✔ 251 pasan, 18 omitidas (F1-02-INTEGRACION) |
| F1-03 | Contrato y flujos contra GLPI real (`contrato-glpi.sh`) | 30 pruebas, 0 fallos | F0-06 | ✔ 30 de 30 tras B-16 y B-17 (F1-03-GLPI-REAL-3) |
| F1-04 | Playwright por el WAF (`e2e-interfaz.sh`) | 4 pruebas, 0 fallos | F0-06 | ✔ 4 de 4 (F1-04-E2E) |
| F1-05 | `metricas.json` con los números medidos hoy y comparación con los documentados | Cada diferencia > 1 % entre lo medido y `estado.md` es un hallazgo | F1-01…04 | ✔ `metricas.json` completo; diferencias: B-14 (ramas puras 94,4 % frente a «99 %»), 1618 frente a 1600 pruebas (+1,1 %) |
| F1-06 | Estabilidad: 20 corridas de la suite unitaria | < 1 % de pruebas inestables y cero reintentos automáticos | F1-01 | ✔ 20 de 20 corridas sin fallos, 1632 pruebas cada una, sin reintentos (F1-06-ESTABILIDAD). La primera tanda quedó invalidada por una edición mía a mitad de corrida (F1-06-ESTABILIDAD-CONTAMINADA) |

## F2 — Caja blanca estática

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F2-01 | **Control positivo estático**: `controles-positivos/vulnerable.py` generado en carpeta temporal (nunca versionado: contiene un secreto falso y `gitleaks` de la CI lo rechazaría) | `bandit` y `ruff` marcan SQL por f-string, `mark_safe` de entrada, `shell=True` y cabecera concatenada; `gitleaks` marca el secreto. Si no, el escaneo no cuenta | F0-03 | ✔ ruff S, bandit, gitleaks y pip-audit ven lo sembrado; Trivy config y fs también (F2-01-CONTROL-POSITIVO, F2-06-TRIVY) |
| F2-02 | `ruff`, `mypy --strict`, `lint-imports` | 0 errores; los 3 contratos de `import-linter` cumplidos | F2-01 | ✔ 0 errores; 3 contratos cumplidos (F2-02) |
| F2-03 | `bandit` sobre `src` y `tests` | 0 hallazgos Medio o superior sin triage | F2-01 | ✔ 0 con Medio o superior sin triage: 3 falsos positivos en `tests` (F2-03-BANDIT-2) |
| F2-04 | `pip-audit` | 0 vulnerabilidades sin exención escrita | F2-01 | ✔ 0 tras B-15 (certifi) (F2-04-PIP-AUDIT) |
| F2-05 | `gitleaks` en árbol e historial | 0 secretos; los avisos de `infra/.env` y `secrets/` (ignorados por git) documentados | F2-01 | ✔ historial 0; árbol: 5 en rutas ignoradas por git (`secrets/`, `infra/.env`, `.venv`), documentadas en F2-05 |
| F2-06 | `trivy fs` y `trivy config` sobre `infra/` y el repositorio | 0 críticas sin exención | F2-01 | ✔ 0 HIGH/CRITICAL en `fs` y `config` (F2-06-TRIVY). Trivy no analiza `compose.yaml`: lo cubre la revisión manual de F7 |
| F2-07 | SBOM de la imagen de la aplicación | Archivo CycloneDX o SPDX generado y su sha256 registrado | F2-06 | ✔ CycloneDX, 115 componentes, sha256 e47eaa05… (F2-07-SBOM); la imagen trae 1 CRITICAL (certifi, B-15) y 44 HIGH del SO sin parche (B-18) |
| F2-08 | Revisión manual dirigida: TOCTOU en decidir y sincronizar, orden de estados, idempotencia del *outbox*, `request.META`, manejo de excepciones | Cada punto con veredicto y archivo:línea; cero sin triage | F1-01 | ✔ 12 puntos con veredicto: `auditoria/revision-manual-f2-08.md`; salen B-17, B-19 y B-20 |
| F2-09 | D-08: activar las reglas `S` de `ruff` o aceptar con motivo | `ruff check .` en verde con `S`, o el motivo de aceptación escrito en `docs/decisiones.md` | F2-03 | ✔ `ruff` con `S` en verde en toda la base (F2-09-RUFF-S) |
| F2-10 | **G0** pre-commit con `gitleaks` y `ruff` (B-07) | Un commit con un secreto sembrado es **rechazado** por el gancho y uno limpio pasa | F2-05 | ✔ gancho `.githooks/pre-commit`: rechaza el secreto sembrado y el error de ruff; sin él, el secreto pasa (F2-10-G0-GANCHO) |

## F3 — Pruebas nuevas de seguridad (`tests/seguridad`)

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F3-U01 | Código TOTP ya consumido no vuelve a servir; contraseña con el desafío de otra sesión no entra | Rojo contra el defecto sembrado «permitir el segundo uso» y verde sin él | F1-01 | ✔ `tests/seguridad/test_segundo_factor.py`; rojo con el defecto «segundo uso» y verde sin él (F3-U01) |
| F3-U02 | Soporte: PDF políglota, 20 MB exactos, 20 MB + 1, nombre con `../`, `\x00` y ancho cero | Rechazo por firma y nombre antes de tocar el disco | F1-01 | ✔ `tests/seguridad/test_soporte.py`; rojo sin la comprobación de firma (F3-U02). Un PDF políglota pasa por diseño: B-22 (aceptado) |
| F3-U03 | Toda ruta de `urlpatterns` está en la matriz de autorización | Falla si se agrega una vista sin clasificar | F5-01 | ✔ `test_U03_…`: las 22 rutas de `urlpatterns` están en la matriz y no sobra ninguna |
| F3-U04 | Propiedad (Hypothesis): ningún valor sensible sobrevive al filtro de logs | 0 contraejemplos en 1000 casos | F1-01 | ✔ propiedad de 1000 casos; halló `contraseña` → B-21 corregido; rojo con el filtro roto (F3-U04) |
| F3-U05 | Dos conexiones concurrentes registran la misma solicitud | Exactamente una gana | F1-02 | ✔ dos decisiones simultáneas: una gana; rojo sin `select_for_update` (F3-U05, F3-U05-CONTROL) |
| F3-U06 | Cabeceras hostiles (`User-Agent`, `Referer`, `Accept-Language`, `Cookie`): se atiende o bloquea el WAF, valor literal en logs, base íntegra | Conteo de filas y esquema iguales antes y después | F1-01 | ✔ 14 cabeceras hostiles: 403 del WAF o atendidas, sin 5xx; base íntegra; control legítimo 302 antes y después (F3-U06) |
| F3-U07 | Caída simultánea de Supabase y GLPI | Ninguna ruta protegida responde 200 ni filtra detalle | F1-01 | ✔ ninguna ruta protegida responde 200 sin sesión; sin detalle; la web no importa el adaptador de GLPI (F3-U07) |
| F3-U08 | `manage.py check --deploy` con los ajustes de producción | Salida vacía | F1-01 | ✔ `check --deploy` sin avisos (4 silenciados, exactamente los que cubre BunkerWeb) (F3-U08) |
| F3-U09 | Un intento denegado por rol siempre deja evento de auditoría | Un evento por cada denegación de la matriz | F5-02 | ✔ 118 celdas de denegación por rol → un evento cada una; salió B-25 (corregido) (F3-U09) |
| F3-BD | Pruebas de base de datos con `SET ROLE` (dueño, REVOKE, disparadores, `PUBLIC`/`anon`/`authenticated`) | Aserciones que fallan al quitar cada control | F1-02 | ✔ 15 pruebas por rol; tres defectos sembrados detectados; salió B-23 (RLS en tablas de Django) (F3-BD) |
| F3-PAR | Paridad del catálogo local frente a Supabase de desarrollo, **solo lectura** | Diferencia vacía salvo las declaradas (TLS y `pg_hba`) | F1-02 | ✔ autorizada por el usuario (lectura de catálogo). Igual en columnas, restricciones, índices, disparadores, funciones, RLS, privilegios y esquema. Difieren solo 4 extensiones de la plataforma (`pgcrypto`, `uuid-ossp`, `supabase_vault`, `pg_stat_statements`) y los roles `anon`, `authenticated` y `service_role` (en Supabase traen `statement_timeout` y `service_role` omite RLS) (F3-PAR) |
| F3-COV | Cobertura de ramas y mutación de los módulos de seguridad | ≥ 95 % y ≥ 85 %, o hallazgo abierto con plan | F3-U01…09 | ✔ cobertura de ramas de los 7 módulos de seguridad = 100 % (antes 84,48 % en ingreso); salieron B-24 y B-13 verificado. La mutación ≥ 85 % queda en F8 (aplazada por el equipo) |

## F4 — Gherkin ejecutable

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F4-01 | Instalar `pytest-bdd` (solo `dev`) y registrar la justificación en `tasks/todo.md` | Versión y licencia confirmadas en PyPI; `uv.lock` actualizado | F1-01 | ✔ pytest-bdd 9.0.0 (MIT, 30/09/2026) solo en `dev`; justificación en `tasks/todo.md`; `uv.lock` actualizado |
| F4-02 | Características del §8: ingreso, autorización, inmutabilidad, restringidos, cabeceras, borde | Cada una con camino feliz, borde y adversarial | F4-01 | ✔ ingreso, autorización, inmutabilidad (en memoria y en PostgreSQL), restringidos, cabeceras y borde; todas con camino feliz o borde y caso adversarial |
| F4-03 | Características restantes: soporte-pdf, cuentas-derivadas, resiliencia, supabase-aislada, cadena-de-suministro, secretos-y-logs | Ídem | F4-02 | ✔ soporte-pdf, cuentas-derivadas, resiliencia, supabase-aislada, cadena-de-suministro y secretos-y-logs |
| F4-04 | Trazabilidad Gherkin | Cero etiquetas sin trazar; ninguna amenaza sin escenario | F4-03 | ✔ `test_trazabilidad.py`: ninguna etiqueta sin trazar; T1–T21 y N-1..N-5 con escenario; 3 escenarios omitidos a F7 marcados (S-37, S-38) |

## F5 — Autorización y rotura deliberada

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F5-01 | `matriz-authz.csv`: rutas × roles × métodos, con lo esperado tomado del SRS §3.3 | 100 % de las celdas clasificadas | F1-01 | ✔ `auditoria/matriz-authz.csv`: 440 celdas (22 rutas × 2 métodos × 10 roles) generadas desde el SRS; una excepción conocida: B-26 |
| F5-02 | Prueba parametrizada que recorre cada celda | 0 resultados distintos del esperado; 403 frente a 404 comprobado | F5-01 | ✔ 440 celdas = lo esperado (la excepción B-26 está rastreada); 403 frente a 404 comprobado (ocultamiento del detalle) |
| F5-03 | IDOR, asignación masiva y CSRF cruzado | Respuesta idéntica a un identificador inexistente | F5-02 | ✔ IDOR idéntico a un id inexistente, asignación masiva ignorada, CSRF sin token o con token ajeno rechazado y control positivo (`test_idor_csrf.py`) |
| F5-04…09 | **Seis defectos sembrados**, de uno en uno, en un `git worktree` descartable: (1) SQL por f-string, (2) quitar el `REVOKE`, (3) apagar el disparador, (4) quitar el decorador de rol, (5) aceptar el `.pdf` renombrado, (6) permitir el segundo uso del TOTP | Cada defecto hace fallar al menos una prueba; tabla `defecto → detectado por → evidencia` completa | F5-02, F3-U01 | ✔ los seis detectados (`auditoria/defectos-sembrados.md`); el primer intento del #4 no se detectó por defensa en profundidad y se resembró |

## F6 — Caja negra dinámica

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F6-00 | **Control positivo de sqlmap y ZAP**: aplicación sembrada vulnerable en una red de laboratorio | sqlmap y ZAP la detectan; si no, el escaneo no cuenta | F2-01 | ✔ sqlmap ve la inyección SQL y ZAP ve el XSS y las cabeceras ausentes de la app sembrada (F6-00-CONTROL-POSITIVO) |
| F6-01 | Neutralización y `pruebas.sh` como control | `pg_dump` previo, worker apuntando al GLPI desechable, `bwcli unban` y `correlation_id` de laboratorio; `pruebas.sh` en verde | F6-00 | ✔ `pruebas.sh` en verde en `app.*` y `glpi.*` (F6-01-PRUEBAS-SH); neutralización con `neutralizar.sh` (copia de la base, worker detenido, desbaneo) |
| F6-02 | `seguridad-dinamica.sh` completo **con** WAF y exención de baneo solo para la IP del escáner (B-04) | ModSecurity y la CRS siguen en bloqueo durante la corrida; la exención queda registrada | F6-01 | ✔ ZAP activo (RRHH y técnico) y sqlmap nivel 3 por el WAF con la exención registrada; ModSecurity siguió en bloqueo (403 antes y después). 0 inyecciones; las 4 alertas Medio o superior triadas en `auditoria/triage-f6.md` (falso positivo, no reproducido, 2 informativas) (F6-02-ESCANER-EXENTO) |
| F6-03 | La misma corrida **sin** exención | El baneo actúa (RS-08); se reporta aparte | F6-02 | ✔ el baneo actúa: la IP del escáner (`10.20.30.1`) quedó baneada en el primer minuto y ZAP/sqlmap no llegaron a la aplicación (sqlmap venció sus 10 min por objetivo). **No concluyente sobre la aplicación**, concluyente sobre el WAF; se reporta aparte de F6-02 (F6-03-ESCANER-SIN-EXENCION) |
| F6-04 | sqlmap nivel 5 con `Host` y verificación de segundo orden (B-05, B-02) | 0 hallazgos y la cadena de auditoría íntegra; reemplaza a la corrida preliminar | F6-00 | ✔ nivel 5 (incluye `Host`), 8 objetivos, segundo orden incluido: 0 inyectables. Sqlmap marcó `User-Agent` y `Referer` de `/solicitudes` como «boolean-based blind» a mitad de la corrida y lo retiró en su veredicto final; triage: falso positivo por página dinámica, y el código no lee esas cabeceras fuera del middleware (búsqueda en `src`). Cadena de auditoría íntegra después (551 registros) y base restaurada (F6-04-SQLMAP-NIVEL5) |
| F6-05 | Cobertura de superficie del escáner | ≥ 95 % de las rutas de `urls.py` vistas por rol | F6-02 | ◐ 20 de 22 rutas = 90,9 % (RRHH 10, técnico 10, administrador 10, solicitante 8, auditor 7). Faltan `reintentar` (exige una solicitud en `error`) y `segundo_factor` (exige un desafío en la sesión): inalcanzables con una sesión inyectada; 20 de 20 sin ellas. Compensado por la matriz de 440 celdas (F5), el Gherkin de ingreso y sqlmap dirigido (F6-05-COBERTURA-SUPERFICIE; `triage-f6.md`) |
| F6-06 | Reproducir D-02/D-03: el Auditor verifica la cadena **a través del WAF** a ritmo humano y a ritmo de guion | Sin 429 a ritmo humano; con el 429 a ritmo de guion se decide si es hallazgo | F6-01 | ✔ ritmo humano: 5 de 5 verificaciones en 200 sin 429; ritmo de guion: 429 por el límite de 2 r/s, que es el diseño (RS-08). D-02/D-03 reproducidos y explicados (F6-06-AUDITOR-POR-WAF) |
| F6-07 | Regresión de las exclusiones del WAF | `infra/bunkerweb/configs/` sin exclusiones: se anota «0 exclusiones, 0 pruebas necesarias» | F6-01 | ✔ 0 exclusiones, 0 pruebas necesarias (F6-07-EXCLUSIONES) |
| F6-08 | Cada 403/429 esperado con su control positivo (la misma operación legítima da 200) | Cero bloqueos sin su control | F6-02 | ✔ cada 403/429 esperado con su control positivo: pruebas.sh, cabeceras hostiles, ritmo humano frente a ritmo de guion, baneo y ModSecurity antes y después (`triage-f6.md`) |

## F7 — Infraestructura, red y datos

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F7-01 | `nmap -p-` del host y de las tres redes (imagen por digest) | Solo 80 y 443 de BunkerWeb responden desde el host | F6-01 | ✔ solo 80 y 443 de BunkerWeb publican hacia fuera del equipo; en las redes: web 8000, GLPI 80, MariaDB 3306, PostgreSQL 5432 y, en BunkerWeb, 5000 (API), 8080 y 8443. `db_net` y `pg_net` son internas (F7-01-NMAP). Grafana y fluent-bit publican en 127.0.0.1: B-27 |
| F7-02 | Prueba activa a `bunkerweb:5000` desde la red `app`, con y sin token, dentro y fuera de `API_WHITELIST_IP` (N-2) | Ninguna respuesta 200 sin token correcto | F7-01 | ✔ N-2 medido: desde la red `app` las 6 combinaciones (con y sin token, a dos rutas) terminan en reinicio de conexión; desde `bw-universe` el token correcto se procesa y el malo o ausente no (control positivo). B-29: RS-19 desfasado, documental (F7-02-API-BUNKERWEB) |
| F7-03 | Trivy de las cinco imágenes con priorización por explotabilidad (KEV/EPSS) | 0 críticas sin exención escrita | F2-06 | ✔ 0 en KEV de 139 CVE distintas; todas las CRÍTICAS corregidas o con exención escrita en `exenciones-trivy.md` (B-31). La imagen propia necesita reconstruirse para llevar el certifi corregido (F7-03-TRIVY-IMAGENES) |
| F7-04 | Captura de tráfico con aserciones: centinela de T7 y tokens en claro (N-1) | 0 tramas del centinela hacia GLPI; conteo de `App-Token`/`Session-Token` en claro registrado | F6-01 | ○ |
| F7-05 | Respaldo y restauración (reejecución) | `restaurar-prueba.sh` verde con la cadena íntegra | F1-02 | ○ |
| F7-06 | Revisión de `local_infile` y del tramo GLPI↔MariaDB | Estado registrado y propuesta de ADR si es en claro | F7-01 | ✔ `local_infile = ON` y GLPI→MariaDB sin TLS declarado por la red interna `db_net`; el usuario `glpi` no tiene FILE. B-30, propuesta de ADR; la captura de F7-04 lo confirma o descarta (F7-06-MARIADB-GLPI) |
| F7-07 | `testssl` del borde local | Resultado registrado (certificado autofirmado: solo para el borde local) | F7-01 | ✔ TLS 1.2 y 1.3 solamente, sin SSLv2/3 ni TLS 1.0/1.1, HSTS de un año, sin Heartbleed, ROBOT, POODLE, BEAST, SWEET32 ni RC4; certificado autofirmado de BunkerWeb (CN `www.example.com`, solo válido para el borde local) (F7-07-TESTSSL) |
| F7-08 | Detección de caída (reejecución de `deteccion.sh`) | GLPI < 120 s y base < 120 s | F1-03 | ○ |
| F7-09 | Escenario del centinela de retiro de punta a punta sobre GLPI real (**G3**) | El valor aparece solo en `solicitud_restringida` y en el detalle de RRHH | F7-04 | ○ |

## F8 — Mutación y consolidación

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F8-01 | `make mutacion` sobre el dominio (cierra 5.10) | ≥ 85 % (último: 93,6 %) | F1-01 | ○ (aplazada por el equipo hasta F8) |
| F8-02 | Primera medición sobre `aplicacion` y los módulos de seguridad (contenedor Linux si mutmut<3 no corre) | ≥ 85 % o supervivientes convertidos en pruebas | F8-01 | ○ |
| F8-03 | DREAD inherente y residual, score global y plan de remediación | Cada hallazgo con falsabilidad e indicador; residual solo con prueba | F6, F7 | ○ |
| F8-04 | Propuestas de ADR: N-1…N-5 al SRS §7, refresco de imágenes, TLS interno hacia GLPI, RNF-11 (B-12) | ADR redactados; el SRS sube de versión si cambia | F8-03 | ○ |
| F8-05 | `asvs-l2.csv` desde el CSV oficial de ASVS 5.0 (nivel 2) | Ningún requisito L2 aplicable sin prueba o sin «no aplica» justificado | F8-03 | ◐ 253 requisitos L1/L2: 144 verificados, 36 parciales, 19 pendientes, 54 no aplican (72,4 % de los aplicables; el resto lo cierra F7 y las decisiones B-10, B-28). Clasificación por sección: revisión del 10 % [PENDIENTE: segunda persona] |

## F9 — Empaquetado y informes

| ID | Tarea | Criterio | Depende | Estado |
|---|---|---|---|---|
| F9-01 | Carpeta `docs/entregables/auditoria/` con los cinco documentos en `.md` | Estructura del §15 completa | F8 | ○ |
| F9-02 | PDF por guion con `reportlab` y `pillow` (justificar en `tasks/todo.md`) | Los 5 PDF se regeneran con un comando | F9-01 | ○ |
| F9-03 | `manifiesto.sha256`, enmascarado y `gitleaks` sobre la carpeta | El manifiesto cuadra y `gitleaks` limpio | F9-01 | ○ |
| F9-04 | `verificar-entrega.py` | Falla ante un marcador, un CA sin evidencia o un hash que no cuadra; pasa sobre la entrega | F9-03 | ○ |
| F9-05 | Remedir el rendimiento con `carga.sh` | p95 < 800 ms por página y dashboard < 2 s tras todas las correcciones | F8 | ○ |
| F9-06 | **G0 a G5** en verde, seis defectos detectados, trazabilidad al 100 % de T1–T21 y N-1–N-5, 0 hallazgos Críticos o Altos abiertos | Los cinco criterios de término del prompt | F9-01…05 | ○ |

## Decisiones pendientes para el equipo (se acumulan; no bloquean el siguiente ítem independiente)

| # | Decisión | Motivo | Ítems afectados |
|---|---|---|---|
| 1 | ¿Se lee el Supabase de desarrollo (solo catálogo) para la paridad? | **Resuelta:** el usuario la autorizó el 24/10/2026 | F3-PAR ✔ |
| 2 | Proteger `master` y fijar la política de ramas | Exige permisos de dueño del repositorio | B-07 |
| 3 | Ejecutar el asesor de Supabase y la contraseña mínima | Acción humana en el Dashboard | B-10 |
| 4 | Aceptar o cambiar el proceso único de `gunicorn` | Es una decisión de diseño (ADR-017/S-29) | B-06 |
