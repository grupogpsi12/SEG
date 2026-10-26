# Revisión del núcleo por lectura (antes del Hito N)

Revisión hecha leyendo el código confirmado en git, sin ejecutarlo (la mutación estaba en curso). Recoge lo que las pruebas actuales **no** ven. Cada hallazgo indica su severidad y qué hacer.

## Hallazgos

### R1 · Carrera entre cancelar y crear el primer ticket (media) — CORREGIDO en el núcleo, bloqueo pendiente en la Fase 2

`CancelarSolicitud` permite a RRHH cancelar una aprobada mientras `solicitud.tickets` esté vacío. El worker (`ProcesarBandeja`) lee la solicitud, **sale de la transacción**, llama a GLPI y luego confirma en otra transacción. Si RRHH cancela entre la creación en GLPI y la confirmación:

- `_confirmar` falla (`registrar_ticket_creado` sobre una `cancelada` lanza `TransicionInvalida`) y la transacción se deshace.
- En la siguiente ronda, `_cargar` ve la solicitud cancelada y **descarta** la entrada.
- Resultado: queda **un ticket huérfano en GLPI** de una solicitud cancelada, sin registro en la aplicación.

Con dobles en memoria y un solo hilo no se reproduce. **Qué hacer:**
- En la Fase 2, el adaptador de PostgreSQL bloquea la fila de la solicitud (`SELECT … FOR UPDATE`) en `CancelarSolicitud` y en `_cargar`/`_confirmar`.
- Además, si `_confirmar` encuentra la solicitud cancelada, el ticket ya existe: debería registrarse igualmente y auditarse como «ticket de una solicitud cancelada» para que TI lo cierre a mano.

**Estado:** el núcleo ya no pierde el ticket: si la solicitud se cancela mientras GLPI lo crea, se registra y se audita como `ticket.huerfano` (`test_R1_…`). El bloqueo de la fila (`SELECT … FOR UPDATE`) sigue pendiente en la Fase 2, con una prueba de contrato de concurrencia (igual que CA-01).

### R2 · Una excepción inesperada detiene toda la sincronización (baja) — CORREGIDO

`SincronizarTickets.ejecutar` aísla por solicitud solo `NoEncontrado` y `OperacionNoPermitida`. Cualquier otro `ErrorDeDominio` en una solicitud (por ejemplo, `DatoInvalido` al aplicar un CDP con datos corruptos) corta la sincronización de **todas** las siguientes, y no se registra la ejecución fallida.

**Qué hacer:** capturar `ErrorDeDominio` por solicitud, contar el error y auditarlo. Requiere prueba primero.

### R3 · Rama inalcanzable en la sincronización (cosmética) — CORREGIDO

En `SincronizarTickets._ticket`, `actual = observado.observacion` nunca es `None` después de `observar(nueva)`. La rama `if actual is None: return` es inalcanzable (aparece en el informe de cobertura). La variable `assert_id` tiene un nombre engañoso. **Qué hacer:** simplificarlo en un commit de refactor aparte.

### R4 · `_Conteo` con listas opcionales (cosmética) — CORREGIDO

`ProcesarBandeja._Conteo` declara `en_error` y `en_ejecucion` como `list | None` y luego comprueba `is not None` en cada uso. Las dos ramas `None` nunca ocurren. **Qué hacer:** `field(default_factory=list)` en un commit de refactor aparte.

### R5 · Indicadores con dos definiciones de «sin resolver» (intencional, documentar)

- Los indicadores (a) pendientes, (b) vencidos y (g) programados usan «estado en GLPI < Resuelto».
- El indicador (c) exposición usa `ticket_resuelto`, que además exige la solución.
- Consecuencia: una baja resuelta **sin solución** deja de estar «pendiente» en (a), pero **sigue exponiendo** en (c).

Es lo correcto según T5: no se confía en un cierre sin solución. Pero debe quedar escrito para que la consulta SQL de la Fase 4 lo replique igual.

### R6 · Nombre de campo engañoso en la sincronización de activos (cosmética)

`SincronizarActivos` reutiliza `ResultadoDeSincronizacion.tickets_leidos` para contar **colaboradores** leídos. Además no registra su ejecución en `sincronizaciones`: el dashboard solo muestra la hora de la sincronización de tickets. **Qué hacer:** decidir en el Hito N si RF-29 se refiere a ambas sincronizaciones.

### R7 · Hash del documento en GLPI (pendiente del spike 0.3)

Ver `docs/spikes/glpi-puerto.md`, punto 9, y lessons.md n.º 24.

## Sin hallazgos

- Atomicidad de aprobar/emitir.
- Compensación del archivo de soporte si la transacción falla.
- Errores de inicio de sesión genéricos en el doble de identidad.
- Ausencia de llamadas no deterministas en `dominio` y `aplicacion`; lo comprueba `test_pureza.py`.
- Ningún DTO de lectura tiene campos para el motivo ni la descripción.
