# F2-08 · Revisión manual dirigida

Commit revisado: `5fa3f32` más las correcciones B-15..B-20 de esta rama. Criterio del plan: cada punto con veredicto y `archivo:línea`; cero sin triage.

| # | Punto | Veredicto | Dónde | Observación |
|---|---|---|---|---|
| 1 | TOCTOU al decidir (dos aprobaciones simultáneas) | **Correcto** | `src/jml/adaptadores/salida/persistencia/repositorios.py:143-155` (`obtener` hace `select_for_update(of=("self",))`); `src/jml/aplicacion/casos/decidir.py:67-82` | Lectura y escritura de la solicitud ocurren en una sola transacción con la fila bloqueada: la segunda aprobación espera y luego ve el estado nuevo (`TransicionInvalida`). La comprobación concurrente contra PostgreSQL real queda en F3-U05. |
| 2 | TOCTOU entre decidir/cancelar y la sincronización | **Correcto** | `sincronizar.py:98-117` (`_solicitud` usa `solicitudes.obtener`, que bloquea) | Sincronizar y decidir/cancelar se serializan por solicitud. |
| 3 | Cancelación mientras el worker crea el ticket en GLPI (R1) | **Correcto, con residuo aceptado** | `bandeja.py:86-87` (`_cargar` descarta la entrada si la solicitud ya no está aprobada) y `bandeja.py:169-182` (`_confirmar` registra `ticket.huerfano`) | La llamada a GLPI se hace fuera de la transacción (a propósito: no retener una transacción esperando la red), así que el ticket puede existir en GLPI tras la cancelación. Se audita como huérfano para que TI lo cierre. Existe la prueba `test_R1_...`. El residuo no tiene vista en el dashboard: se anota en F8 como mejora, no como defecto. |
| 4 | Orden de estados al sincronizar | **Correcto** | `sincronizar.py:107-114` (orden por `emitido_en`, `vence_en`, clave) y `sincronizar.py:131-158` | El orden es determinista, así que repetir la sincronización con los mismos datos no cambia nada (`test_la_sincronizacion_es_idempotente_...`). Un ticket reabierto no devuelve la cuenta ni al colaborador atrás (`sincronizar.py:182-186`). |
| 5 | Idempotencia del *outbox* | **Correcto** | `bandeja.py:97-110`, `cliente.py:217-221`, `cliente.py:305-319` | `crear_ticket` busca por `externalid` antes de crear y completa el vencimiento si un timeout cortó el primer intento; el soporte se busca por SHA-1 y se vincula una sola vez. Observación: `_sin_duplicados` **borra** (`force_purge`) los tickets sobrantes de una misma clave; con un solo worker no ocurre, y por eso el proceso único de gunicorn/worker es una decisión pendiente (estado-auditoria). `vencidas()` no usa `skip_locked`: dos workers procesarían la misma entrada, sin duplicar pero sin eficiencia. |
| 6 | Manejo de excepciones: sincronización | **Defecto → B-19** | `sincronizar.py:72` | Solo se aislaba `ErrorDeDominio`. Corregido. |
| 7 | Manejo de excepciones: bandeja | **Defecto → B-20** | `bandeja.py:101-107` | Solo se traducía `ErrorDeSistemaDeTickets`. Corregido. |
| 8 | Manejo de excepciones: ciclo del worker | **Correcto** | `src/jml/adaptadores/entrada/worker/ciclo.py:30-37` | `_correr` captura `Exception`, registra con traceback y sigue (RNF-02). El latido solo se escribe si todas las tareas terminan bien. |
| 9 | Respuesta de GLPI con éxito aparente | **Defecto → B-17** | `cliente.py:262-278` | GLPI contesta 200 con el rechazo dentro del cuerpo. Corregido. |
| 10 | `request.META` y cabeceras reenviadas | **Correcto** | `src/jml/adaptadores/entrada/web/middleware.py:30-41` | `X-Forwarded-For` y `X-Forwarded-Proto` se **quitan** siempre y solo se reponen si `REMOTE_ADDR` está en `JML_PROXIES_CONFIABLES`; se toma el **último** elemento (el que añade BunkerWeb) y se valida con `ipaddress`. `X-Request-ID` se acepta solo con forma `^[A-Za-z0-9-]{8,64}$`. Ningún otro código lee `request.META`. La pertinencia de la IP de confianza depende de la red (B-01, ya corregido). |
| 11 | Entrada del usuario hacia SQL | **Correcto** | `grep -rnE "\.(execute\|executemany\|raw\|extra)\(" src` (sin migraciones): 0 coincidencias | Todo el acceso a datos pasa por el ORM. El único aviso de bandit con SQL en f-string está en `tests/integracion/test_postgresql.py:102` (tabla de una lista fija de `parametrize`; triage en F2-03). |
| 12 | `mark_safe` y `\|safe` | **Correcto** | `src/jml/adaptadores/entrada/web/graficos.py:39`: único uso en `src/` | El SVG se arma con enteros (`int(valor)`, `round(...)`) y con las etiquetas y el título pasados por `django.utils.html.escape` (incluye comillas, necesario porque el título va en un atributo). Es la excepción que permite CLAUDE.md y está comentada. Ninguna plantilla usa `\|safe` ni `autoescape off`. |

## Hallazgos que salen de esta revisión

- **B-17** (Media, corregido): rechazo por ítem de GLPI ignorado.
- **B-19** (Media, corregido): la sincronización no aísla excepciones que no son de dominio.
- **B-20** (Media, corregido): la bandeja se bloquea con una respuesta inesperada de GLPI.

Los puntos 6, 7 y 9 comparten patrón: una captura más estrecha que la promesa del comentario. Conviene que F8 revise si queda otra captura estrecha en el código de las vistas.
