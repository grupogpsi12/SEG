# Prompt de ejecución — Núcleo primero

> Pega este documento completo como primer mensaje de la sesión de Claude Code, con el repositorio ya creado (ítem 0.1) y `docs/SRS.md` v2.2, `CLAUDE.md`, `tasks/todo.md`, `tasks/lessons.md` y `docs/decisiones.md` presentes.

---

## 1. Tu rol y tu objetivo

Eres un ingeniero de software senior con criterio de arquitecto y de ingeniero de seguridad. Vas a construir el **núcleo** del «Sistema integrado de eventos laborales» (Andina Servicios S.A.S., empresa ficticia): las capas `dominio` y `aplicacion` de la arquitectura hexagonal, **completas, probadas exhaustivamente y congeladas**, antes de escribir un solo adaptador.

El núcleo es el producto. Django, PostgreSQL, GLPI, BunkerWeb y las vistas son piezas intercambiables que se conectan después. Si el núcleo es correcto, lo demás es traducción; si el núcleo tiene un hueco, ningún adaptador lo arregla.

**Alcance de esta ejecución:** Fase 1 de `tasks/todo.md`, ítems 1.1 a 1.14, hasta el **Hito N (núcleo congelado)**. No avances a la Fase 2.

**Qué significa «terminado»:** cada regla del SRS que pertenece al núcleo tiene al menos una prueba que falla si la regla se rompe, comprobado por cobertura de ramas, pruebas de propiedades y pruebas de mutación. No «parece que funciona»: hay evidencia.

## 2. Antes de escribir código

1. Lee completos, en este orden: `CLAUDE.md`, `docs/SRS.md` (secciones 3 a 6 en detalle: roles, modelo del proceso, RF, RD), `tasks/todo.md`, `tasks/lessons.md` y `docs/decisiones.md` (ADR vigentes; los marcados REEMPLAZADA no se aplican).
2. Escribe en `tasks/todo.md`, bajo el ítem 1.1, el plan de la sesión con su criterio de verificación.
3. Responde en una sola respuesta corta: qué vas a hacer primero y qué dudas bloqueantes tienes. Si no hay dudas bloqueantes, empieza. Las ambigüedades no bloqueantes se registran como supuestos (§6) y se siguen.

## 3. Reglas inviolables del núcleo

Son las invariantes de `CLAUDE.md`, aplicadas al núcleo. Si un cambio las toca, di **«Pausa —»**, explica y espera.

- `dominio` importa **solo la biblioteca estándar**. `aplicacion` importa **solo `dominio`**. Nada de Django, `httpx`, ORM, ni `datetime.now()`/`uuid4()`/`random` llamados directamente: el tiempo viene del puerto `Reloj`; los identificadores, de un generador inyectado. Eso hace el núcleo determinista y probable.
- No relajes ni desactives un contrato de `import-linter` para que algo pase.
- **Sin acciones sobre directorios.** El núcleo no sabe qué es LDAP, Graph ni Samba. Genera listas de verificación de texto para técnicos humanos.
- **Estados abiertos** (deduplicación, RD-01): `pendiente_aprobacion`, `aprobada`, `en_ejecucion`, `error`. Contar uno de ellos como final es el error n.º 1 de `lessons.md`.
- **Campos restringidos** (motivo de retiro, descripción de emergencia): jamás en el ticket, la auditoría, los logs ni las consultas del dashboard o la ficha. El dominio los modela como un objeto aparte que **no se puede serializar** hacia fuera por accidente (sin `__repr__` ni `__str__` con el contenido).
- **Sin contraseñas** en ningún texto que el núcleo genere.
- **Errores tipados.** Cada violación de regla es una excepción de dominio con nombre y datos útiles (p. ej., `SolicitudDuplicada(existente_id=...)`). Nada de `ValueError`/`Exception` genéricos, nada de `assert` como validación.
- **Inmutabilidad por diseño:** objetos de valor y entidades congeladas (`@dataclass(frozen=True, slots=True)`); las operaciones devuelven un valor nuevo o eventos de dominio, no mutan.
- **Tipado estricto:** `mypy --strict` sin `Any` ni `# type: ignore` sin comentario que cite el motivo.
- No inventes funcionalidad «por si acaso» (CLAUDE.md, «Estilo»). Solo existen los puertos del SRS (§10.1). Un puerto nuevo exige una segunda implementación y un ADR.

## 4. Diseño del núcleo (qué construir)

Los nombres del dominio van en español, como el glosario del SRS. La estructura es una propuesta; si encuentras una mejor, justifícala en el plan y sigue los contratos de capas.

```
src/jml/
  dominio/
    tipos.py           # enumeraciones: TipoEvento(ING,VAC,CDP,CSU,RET,EMG), Subtipo, EstadoSolicitud,
                       #   Cola(AD,COMUNICACIONES,LICENCIAS,INVENTARIO,REVISION_MANUAL), ClaseTicket,
                       #   SistemaDeCuenta(AD,RED,M365), EstadoDeCuenta, MarcaDeCuenta, PerfilDeRecurso,
                       #   Prioridad, Rol
    valores.py         # SolicitudId (SOL-AAAA-NNNNNN), Documento, Usuario, CorreoUPN, FechaEfectiva,
                       #   CalendarioHabil, Sha256, NombreDeSoporteSaneado
    errores.py         # jerarquía de ErrorDeDominio con códigos estables
    catalogo.py        # campos por tipo (§4.8), validación pura de los datos de cada evento
    permisos.py        # quién registra qué y sobre quién (§4.1), roles incompatibles (§3.3)
    solicitud.py       # agregado Solicitud: transiciones, inmutabilidad, cancelación, decisión
    colaborador.py     # Colaborador y su estado (por_ingresar, activo, suspendido, retirado)
    perfiles.py        # PerfilDeAcceso, RecursoCompartido, diferencia entre perfiles (§4.9, ADR-022)
    tickets.py         # TicketDeCola, generación por la matriz evento × cola (§4.4), listas de verificación
    sla.py             # vencimientos y prioridades por tipo (§4.1) con calendario hábil
    usuarios.py        # usuario sugerido y UPN (§4.10)
    resolucion.py      # ¿ticket resuelto? ¿solicitud cerrable? (RF-24, RF-26)
    cuentas.py         # Cuenta y derivación de estado desde tickets (§4.7)
    auditoria.py       # registro canónico y cadena SHA-256 (RD-03), verificación
  aplicacion/
    puertos.py         # Protocol: Repositorios (+UnidadDeTrabajo), Auditoria, SistemaDeTickets,
                       #   ProveedorDeIdentidad, Reloj, AlmacenDeSoportes
    casos/             # un módulo por caso de uso (registrar, aprobar, rechazar, emitir,
                       #   emitir_por_excepcion, cancelar, procesar_bandeja, reintentar_emision,
                       #   sincronizar_tickets, sincronizar_activos, contratos_por_vencer,
                       #   consultar_dashboard, buscar_cuentas, consultar_ficha)
    dtos.py            # entradas y salidas de los casos de uso (dataclasses congeladas)
tests/
  dominio/  aplicacion/  contratos/  escenarios/
  dobles/              # implementaciones en memoria de cada puerto
```

### 4.1 `Solicitud` y su máquina de estados

- La **tabla de transiciones es datos explícitos** (diccionario de `(estado, acción) → estado`), no un `if` disperso. Una prueba itera **todas** las combinaciones `estado × acción` y exige que cada una esté en la tabla como permitida o falle con `TransicionInvalida`.
- Transiciones del SRS (§4.2 y diagrama `docs/img/estados.png`): `pendiente_aprobacion → aprobada | rechazada | cancelada`; `aprobada → en_ejecucion | cancelada (solo sin tickets creados) | error`; `en_ejecucion → cerrada | error`; `error → aprobada/en_ejecucion` por reintento del Administrador. Finales: `cerrada`, `rechazada`, `cancelada` (absorbentes). Revisa el diagrama y la tabla antes de fijar la tuya y cita la fuente.
- **Inmutabilidad (RF-14):** tras `aprobada`, ninguna operación cambia el contenido; solo cambian estado y referencias a tickets. Para corregir: cancelar y registrar una nueva con `solicitud_origen_id`.
- **EMG (RF-10):** se acepta aunque existan abiertas de otros tipos del mismo colaborador, y al emitirse las marca «para revisar por RRHH» (evento de dominio, sin tocar su estado).
- **Quién registra qué (§4.1, RF-15, §3.3):** matriz completa (solicitante × tipo × sujeto), incluyendo: colaborador solo VAC y renuncia sobre sí mismo; jefe directo (por `jefe_id`) para CDP y CSU; RRHH todo salvo sobre sí misma; la excepción del Administrador. Tabla de pruebas exhaustiva `rol × tipo × (sobre sí / sobre subordinado / sobre tercero)`.
- **Decisión (RF-12, RF-13):** rechazar exige justificación no vacía; emitir directamente exige justificación; aprobar la acepta opcional. Quien decide no puede ser el sujeto.

### 4.2 Generación de tickets (el corazón de las reglas)

`generar_tickets(solicitud, perfil_actual, perfil_nuevo, colaborador, calendario, ahora) -> tuple[TicketDeCola, ...]` es una **función pura**. La prueba principal es una **tabla parametrizada que reproduce la matriz evento × cola del SRS celda por celda**, para cada tipo y subtipo, con variantes: contratista y empleado, con y sin equipo, cambio de departamento con y sin diferencia, cambio de sede con y sin traslado de equipo, RET renuncia y fin de contrato, EMG despido y fuga.

Cada ticket tiene: cola, clase (cierre inmediato / cierre programado / posterior), categoría, prioridad, vencimiento, estado inicial (`Nuevo` o `En espera` si es programado o posterior), lista de verificación (texto ordenado), clave de idempotencia determinista (`solicitud_id + cola + clase + ordinal`) y **solo** los datos técnicos de RF-20.

Verifica explícitamente:

- VAC: suspensión (Nuevo) y reactivación (En espera, vence el día de regreso) en AD y Licencias; Comunicaciones e Inventario no reciben ticket.
- RET y EMG: ticket de baja por cola, más ticket **posterior** de eliminación a 90 días en AD y Licencias que **no bloquea el cierre**.
- ING: la lista de AD incluye grupos del perfil, usuario sugerido, **cada recurso compartido con ruta, serie, perfil y grupo**, y la verificación del soporte; Licencias incluye la verificación del soporte; contratista con fecha de expiración. El soporte se adjunta a los tickets de AD y Licencias (la referencia, no el archivo).
- CDP: diferencia de grupos y recursos (nuevos con su perfil, «Retiro de accesos» en los que ya no corresponden); sin diferencia no se genera ticket vacío (ver supuesto).
- RET/EMG: «Retiro de accesos» en **todos** los recursos compartidos; contraseña nunca mencionada salvo «cambiar a un valor aleatorio que no se comunica».
- Propiedad: serializar cualquier ticket generado con un motivo/descripción centinela en la solicitud **nunca** contiene el centinela; ningún texto contiene «contraseña:» ni campo password (CA-10 en el dominio).

### 4.3 Resolución, cierre y cuentas (la fuente de la verdad)

- `ticket_resuelto(ticket_observado)`: estado ≥ Resuelto **y** solución registrada; Inventario además ≥ 1 documento adjunto (RF-24). Si no: «cierre incompleto».
- `solicitud_cerrable(solicitud, tickets)`: todos los de cierre (inmediatos y programados) resueltos; los **posteriores no bloquean** (RF-26).
- `derivar_cuenta(cuenta, ticket_anterior_observado, ticket_observado)`: la tabla de §4.7 **fila por fila** y las tres reglas complementarias (cierre sin solución no cambia la cuenta; reabierto devuelve al estado previo al ticket y marca «reabierto»; equipos salen de activos, no de tickets). Cola → sistema: AD→AD, Comunicaciones→Red, Licencias→M365, Inventario→ninguno.
- Toda mutación de `Cuenta` produce una fila de `cuenta_historial` (solo inserción) y un evento de auditoría. **No existe ninguna operación que cambie una cuenta fuera de la sincronización** (RD-11): comprueba por reflexión/estructura que `Cuenta` no expone un método público de edición manual.
- Sincronización **idempotente** y tolerante al orden de llegada: observar dos veces lo mismo no cambia nada; el estado final no depende de procesar primero un ticket u otro cuando son de sistemas distintos.

### 4.4 Auditoría encadenada

`hash = SHA-256(hash_anterior ‖ contenido_canónico)`, con serialización canónica (JSON con claves ordenadas, separadores fijos, UTF-8, fechas en UTC ISO-8601, sin espacios) definida **una sola vez** y documentada. Verificación devuelve el **primer registro afectado**. El primer registro usa un `hash_anterior` génesis fijo y documentado. La auditoría no recibe nunca campos restringidos (el tipo de `datos` lo impide o lo detecta).

### 4.5 Casos de uso, puertos y transacciones

- Cada caso de uso es una clase o función con dependencias inyectadas por constructor (los puertos). Devuelve un DTO de resultado o lanza un error de dominio. No hace E/S salvo por los puertos.
- **`UnidadDeTrabajo` atómica:** aprobar/emitir = guardar decisión + cambiar estado + escribir tickets en la **bandeja de salida** + escribir auditoría, todo o nada. El doble en memoria implementa *rollback real*: la prueba fuerza un fallo en el último paso y comprueba que no queda rastro de los anteriores.
- **Deduplicación (RD-01, RD-09):** el caso de uso no «comprueba y luego inserta». El repositorio expone `guardar(solicitud)` que lanza `DuplicadoAbierto(existente_id)` según la regla de la restricción parcial; el caso de uso la traduce a `SolicitudDuplicada`. El doble en memoria aplica **la misma regla** (mismo conjunto de estados abiertos) y el documento único. Más adelante el adaptador PostgreSQL pasará la misma suite de contrato.
- **Bandeja de salida (RF-18):** el trabajo toma entradas pendientes, llama a `SistemaDeTickets.crear_ticket(ticket)` y registra el resultado. Reintentos con espera creciente determinista (función pura del número de intento y del `Reloj`); **tras 10 intentos fallidos, la solicitud pasa a `error`**; el Administrador reintenta (`reintentar_emision`, RF-38).
- **Idempotencia del puerto `SistemaDeTickets`:** `crear_ticket` es idempotente por `clave_idempotencia`. El doble en memoria soporta *fallos programados*: error antes de crear, **timeout después de crear** (el ticket existe pero la respuesta se perdió), caída de N llamadas, respuesta duplicada. La prueba clave: con cualquier calendario de fallos, al terminar existe **exactamente un** ticket por clave.
- **Soporte de vinculación (RF-39, RF-40, RD-12):** el núcleo valida firma `%PDF-` (primeros bytes) y tamaño ≤ 20 MiB sobre los *bytes* recibidos, sanea el nombre original, calcula el SHA-256, guarda con nombre aleatorio inyectado vía `AlmacenDeSoportes`, y registra metadatos. El worker (caso de uso `procesar_bandeja`) lo sube una sola vez, vincula a AD y Licencias, verifica el hash y borra la copia; si la solicitud se cancela, se borra sin subir; si la copia se perdió antes de subir, la solicitud pasa a `error` (RD-12).
- **Consultas de lectura (RF-29 a RF-33):** los indicadores (a) a (h), la búsqueda con sus filtros y la ficha son métodos de lectura del puerto `Repositorios`. El doble en memoria los calcula con Python simple y claro: **ese resultado es el oráculo** con el que más adelante se comparará la consulta SQL (CA-15). Escribe la expectativa de cada indicador a mano sobre un conjunto de semilla de dominio pequeño y legible.
- **Auditoría (RF-35):** cada caso de uso emite sus eventos por el puerto `Auditoria`; una prueba recorre todos los casos de uso y comprueba que el evento esperado queda registrado y que la cadena verifica.

## 5. Estrategia de pruebas (esto es lo que hace sólido el núcleo)

Orden: **escribe la prueba que falla, luego el código** para toda regla del SRS. Cada prueba lleva en su nombre o docstring el ID que verifica (`RF-09`, `RD-01`, `S-07`...).

1. **Tablas exhaustivas** (parametrizadas): transiciones de estado, `rol × tipo × sujeto`, matriz evento × cola, tabla de derivación de cuentas, SLA por tipo, convención de nombres.
2. **Propiedades con `hypothesis`** (mínimo las siguientes; usa estrategias propias del dominio):
   - **P1 Deduplicación:** para cualquier secuencia aleatoria de registrar/aprobar/rechazar/cancelar/cerrar, el repositorio nunca contiene dos solicitudes abiertas del mismo (colaborador, tipo); y tras llegar a un estado final se puede registrar otra.
   - **P2 Máquina de estados:** recorridos aleatorios solo visitan estados alcanzables; los finales son absorbentes; una aprobada nunca cambia de contenido.
   - **P3 Cadena de auditoría:** alterar cualquier campo, quitar, duplicar o reordenar cualquier registro rompe la verificación **y** la indica en el primer registro afectado.
   - **P4 Generación de tickets:** para cualquier combinación válida tipo × subtipo × perfil × colaborador, los tickets cumplen la matriz, las claves de idempotencia son únicas y deterministas, y no hay datos restringidos ni contraseñas.
   - **P5 Diferencia de perfiles:** `diferencia(a, a)` vacía; `aplicar(diferencia(a, b), a) == b`; los retirados ∪ los nuevos cubren exactamente la diferencia de recursos.
   - **P6 Usuario sugerido:** único frente a cualquier conjunto de existentes, ≤ 20 caracteres, ASCII, minúsculas, determinista, ñ → n, tildes eliminadas.
   - **P7 Derivación de cuentas:** idempotencia ante observaciones repetidas; reabrir devuelve el estado previo; el resultado final no depende del orden entre sistemas distintos.
   - **P8 Bandeja de salida:** con cualquier calendario de fallos del GLPI falso, nunca hay dos tickets con la misma clave; con ≥ 10 fallos seguidos la solicitud queda en `error`; con recuperación antes del límite, todos los tickets existen.
   - **P9 Cierre:** la solicitud está `cerrada` si y solo si todos los tickets de cierre están resueltos; añadir o resolver un posterior no cambia nada.
   - **P10 Confidencialidad:** para cualquier valor centinela de campos restringidos, ninguna salida de los casos de uso hacia los puertos de salida (ticket, auditoría, DTOs de dashboard/ficha para roles no RRHH, mensajes de error) lo contiene.
3. **Pruebas de contrato por puerto** (`tests/contratos/`): una suite parametrizada por «fábrica de implementación». Hoy solo la fábrica del doble en memoria. Debe cubrir, por puerto, el comportamiento observable completo (incluido el duplicado abierto, el rollback de la unidad de trabajo, la idempotencia, el borrado del soporte). Mañana el adaptador real se agrega como segunda fábrica **sin tocar las pruebas**.
4. **Escenarios de extremo a extremo en memoria** (`tests/escenarios/`): ING, VAC, CDP, CSU, RET y EMG completos, con `Reloj` simulado y GLPI falso con fallos. Incluir: EMG sobre una VAC abierta; ING con soporte inválido; reapertura de un ticket tras el cierre; cierre sin solución; Inventario sin acta; caída larga de GLPI y recuperación; cancelación antes y después de crearse tickets; reintento del Administrador tras `error`; RRHH como sujeto (excepción del Administrador).
5. **Pruebas de mutación** (`mutmut` sobre `dominio`): ≥ 85 % de mutantes eliminados. Cada superviviente se clasifica: *equivalente* (se documenta por qué) o *falta una prueba* (se agrega). Registro en `docs/spikes/mutacion.md`.
6. **Cobertura de ramas:** ≥ 95 % `dominio`, ≥ 90 % `aplicacion`. El número no es la meta, es el síntoma: si sube sin que baje el número de mutantes supervivientes, las pruebas son decorativas.
7. **Sin pruebas omitidas.** `skip`/`xfail` solo con el ID de un supuesto abierto.

## 6. Ambigüedades conocidas — decide, registra, sigue

No bloquees por estas. Para cada una, elige el valor por defecto razonable (los sugeridos abajo son mi propuesta), escríbelo en `docs/supuestos-nucleo.md` con ID `S-nn`, justificación y la prueba que lo fija, y sigue. Se revisan con el equipo en el Hito N. Si encuentras más, agrégalas; si alguna **contradice** el SRS, di «Pausa —».

| ID | Ambigüedad | Valor por defecto propuesto |
|---|---|---|
| S-01 | Qué es un «día hábil» (SLA de CDP/CSU) | Lunes a viernes; los festivos entran como datos del objeto `CalendarioHabil` (vacío por defecto); no hay puerto nuevo |
| S-02 | «Final del último día laborado» / «resuelto antes de la fecha de ingreso» | Hora de corte 23:59:59 America/Bogotá (`zoneinfo`); ING vence a las 00:00 del día de ingreso en esa zona; todo se guarda en UTC |
| S-03 | Base del «vencimiento a 90 días» de los tickets posteriores | RET: 90 días calendario desde la fecha efectiva (último día laborado). EMG: desde la emisión |
| S-04 | ING con «requiere equipo = no» | No se genera ticket de Inventario |
| S-05 | CDP/CSU sin diferencia de grupos, recursos o licencias en una cola | No se genera ticket vacío para esa cola; si ninguna cola tiene trabajo, la solicitud se aprueba y cierra sin tickets y se audita |
| S-06 | Cuándo se crea el `Colaborador` de un ING | Al registrar el ingreso, en estado `por_ingresar`, dentro de la misma unidad de trabajo; si la solicitud se rechaza o cancela, el colaborador queda `por_ingresar` sin solicitudes abiertas y el documento sigue reservado hasta que RRHH lo marque `retirado` (decisión del equipo) |
| S-07 | Cómo cambia el estado del `Colaborador` | Lo deriva la sincronización: ING resuelto → `activo`; VAC → `suspendido`/`activo`; RET/EMG resueltos → `retirado` |
| S-08 | «Emitir» por el Administrador cuando el sujeto es RRHH (§4.1) frente a «el Administrador no aprueba» (§3.3) | Emitir ≠ aprobar: caso de uso aparte `emitir_por_excepcion`, solo para sujeto RRHH, solo Administrador, siempre con justificación y evento de auditoría de excepción |
| S-09 | Ticket posterior cuya cuenta ya fue eliminada o la solicitud se cancela | No se cancela; la sincronización lo ignora si no hay cuenta y lo audita |
| S-10 | Dos tickets que afectan la misma cuenta a la vez (p. ej., CDP en curso y RET) | Prevalece el estado del ticket más reciente por fecha de emisión; la marca «cambio pendiente» se limpia al resolverse |
| S-11 | Reapertura de un ticket antiguo cuando ya hay uno más reciente en la misma cuenta | Se marca «reabierto» y se audita, pero el estado de la cuenta lo sigue marcando el más reciente |
| S-12 | Límite y unidad de «20 MB» | 20 × 1024 × 1024 bytes; 20 MiB exactos se aceptan, un byte más se rechaza |
| S-13 | Espera entre reintentos de la bandeja de salida | 30 s, 1 min, 2 min, 5 min, 10 min, luego 15 min fijos (con tope en el 10.º intento); función pura |

## 7. Protocolo de trabajo

- **Ítem por ítem**, en el orden de `tasks/todo.md` (1.1 → 1.14). Marca `[~]` al empezar y `[x]` solo con la evidencia pegada (salida de `make verificar`, cobertura, mutación). No avances de ítem con pruebas en rojo.
- **Commits pequeños**, uno por propósito, con mensaje en español y el ID del requisito: `feat(dominio): matriz evento × cola para VAC (RF-16, RF-17)`. Test y código pueden ir en el mismo commit; refactor y corrección, no.
- **Si algo falla:** detente, escribe la hipótesis en `tasks/todo.md`, corrige la causa raíz. Para un bug, primero el test que lo reproduce.
- **Si el SRS contradice lo que te piden o dos requisitos se contradicen:** «Pausa —», cita ambos pasajes, propón dos opciones y espera.
- **Si un requisito cambia:** edita `docs/SRS.md`, sube la versión en «Control del documento» y avisa. No se genera Word.
- **Proporcionalidad:** el código del dominio recibe el máximo rigor (N3). No gastes ese rigor en andamiaje trivial; sí en cada regla. Ni una línea de configurabilidad «por si acaso».
- Mantén `docs/supuestos-nucleo.md`, `tasks/todo.md` y `tasks/lessons.md` al día. Al terminar cada ítem, registra en `lessons.md` lo que evitaría repetir un error.
- No agregues dependencias fuera de la tabla de la Fase 1 sin justificarla en `todo.md`.

## 8. Qué NO hacer en esta ejecución

- No crees Django, migraciones, modelos, vistas, plantillas, contenedores, `compose.yaml`, BunkerWeb ni nada bajo `src/jml/adaptadores`, `src/config` o `infra/`.
- No llames a GLPI, Supabase ni a la red; los tests no tocan red ni disco (salvo `tmp_path` donde el contrato lo exija).
- No pongas lógica de negocio en DTOs, ni «utilidades» genéricas compartidas fuera de `dominio`.
- No ocultes una prueba inestable: elimina el origen del no determinismo (reloj, orden, azar).
- No cierres el Hito N tú misma/o: lo cierra el equipo tras revisar los supuestos.

## 9. Entrega del Hito N (formato del informe final)

Al terminar el ítem 1.13, responde con un informe corto (no repitas el código):

1. **Estado:** ítems 1.1–1.13 con la evidencia de cada compuerta (cobertura de ramas por capa, `mypy --strict`, `import-linter`, mutación y supervivientes).
2. **Supuestos:** tabla S-nn con valor adoptado, y los que **requieren decisión del equipo** marcados.
3. **Puertos:** la firma final de cada puerto y qué necesita confirmar el spike 0.3 (GLPI) antes de congelar `SistemaDeTickets`.
4. **Riesgos y huecos:** lo que no pudiste verificar y por qué.
5. **Siguiente paso propuesto:** la Fase 2, ítem por ítem, solo cuando el equipo apruebe.

## 10. Primer paso

Empieza por **0.1** si el repositorio base no existe; si existe, por **1.1**. Muestra el plan de la sesión en `tasks/todo.md` y arranca. No hace falta que esperes confirmación para empezar.
