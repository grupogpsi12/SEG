# Puerto `SistemaDeTickets`: qué debe confirmar el spike 0.3 antes de congelarlo

**Estado del puerto (11/10/2026): CONFIRMADO contra GLPI 11.0.11 real**; el resultado del spike está en `docs/spikes/glpi.md`. Lo que sigue es el texto original, que listaba lo que había que confirmar.

**Estado original del puerto:** PROVISIONAL. El núcleo y su suite de contrato (`tests/contratos/test_sistema_de_tickets.py`) están hechos contra un doble en memoria. El puerto se congela en el Hito N solo si el spike 0.3 confirma cada punto de esta lista contra GLPI 11 real. Si un punto falla, se cambia el **adaptador**, no el puerto, salvo donde se indica.

## Firma actual

```python
class SistemaDeTickets(Protocol):
    def asegurar_usuario(self, colaborador: Colaborador) -> str
    def crear_ticket(self, ticket: TicketDeCola) -> TicketCreado          # idempotente por clave
    def subir_documento(self, nombre: NombreDeSoporteSaneado, contenido: bytes) -> str  # idempotente por contenido
    def hash_de_documento(self, id_documento: str) -> Sha256
    def vincular_documento(self, id_documento: str, id_ticket: str) -> None  # idempotente
    def leer_tickets(self, ids: Sequence[str]) -> Mapping[str, Observacion]
    def leer_activos(self, id_usuario: str) -> Sequence[ActivoAsignado]
    def leer_licencias(self, id_usuario: str) -> Sequence[LicenciaAsignada]
```

Errores: `GlpiNoDisponible` (reintentable), `TiempoAgotado` (la escritura **pudo** aplicarse), `GlpiRechazo` (la petición fue rechazada). Los tres cuentan como intento fallido en la bandeja (RF-18).

## Lista de verificación del spike

| # | Qué confirmar | Por qué lo necesita el núcleo | Prueba de contrato que lo exige | Si GLPI no lo permite |
|---|---|---|---|---|
| 1 | Autenticación de servicio (API v2 OAuth2 o v1 con `App-Token` + `user_token`) con un perfil limitado a estas operaciones y sin acceso a la interfaz | RI-02, RS-10, T2 | — (configuración) | Decidir ADR-014 |
| 2 | **Buscar un ticket por una referencia externa** (la clave de idempotencia `SOL-AAAA-NNNNNN:COLA:clase:1`) | Sin esto, un timeout después de crear (`TiempoAgotado`) duplica el ticket (RF-18, CA-07) | `test_el_timeout_despues_de_crear_no_duplica_RF_18`, `test_una_respuesta_duplicada_no_duplica` | Guardar la clave en un campo buscable (p. ej. `externalid` o un campo adicional por plugin) o en el título y buscar por él. **No** se cambia el puerto |
| 3 | Crear un ticket en estado **«En espera»** con fecha de vencimiento futura | RF-17, CA-04 | `test_un_ticket_programado_nace_en_espera_RF_17` | Crear «Nuevo» y pasarlo a «En espera» en una segunda llamada, dentro del adaptador y de forma idempotente |
| 4 | Fijar la **categoría ITIL** (`JML/<tipo>/<cola>/<acción>`) y que una regla de negocio asigne el grupo; una categoría desconocida va a «Revisión manual» | RF-19, CA-03 | (integración, 3.1) | Configuración de GLPI como código (3.1) |
| 5 | Leer estado, **solución registrada** y **número de documentos** de varios tickets en una llamada | RF-22, RF-24 | `test_leer_tickets_refleja_lo_que_hace_el_tecnico_RF_22`, `test_leer_tickets_omite_los_desconocidos_y_acepta_lotes` | Lotes más pequeños en el adaptador |
| 6 | Mapeo de los estados de GLPI (1 Nuevo, 2 En curso asignado, 3 En curso planificado, 4 En espera, 5 Resuelto, 6 Cerrado) al `EstadoDeTicket` del núcleo, que solo necesita el orden «≥ Resuelto» | RF-24 | `test_resuelto_exige_estado_y_solucion_RF_24` | El mapeo vive en el adaptador |
| 7 | **Subir un PDF de 20 MB** y obtener su id | RF-40, CA-18 | `test_subir_el_mismo_contenido_dos_veces_da_el_mismo_documento` | R10: bucket privado (exige ADR) |
| 8 | **Subir el mismo contenido dos veces devuelve el mismo documento** (o el adaptador lo busca antes de subir) | El worker debe subir el soporte una sola vez aunque un timeout corte la respuesta (RF-40) | `test_subir_el_mismo_contenido_dos_veces_da_el_mismo_documento` | Buscar por hash antes de subir, en el adaptador |
| 9 | **Qué hash expone GLPI del documento.** GLPI guarda `sha1sum`, no SHA-256 | `hash_de_documento` devuelve `Sha256` y el worker lo compara antes de borrar la copia (RF-40) | `test_el_hash_del_documento_coincide_con_el_del_contenido` | **Decisión pendiente** (lessons.md n.º 24): (a) el adaptador descarga el documento y calcula el SHA-256 (costoso con 20 MB), o (b) el puerto cambia a «verificar documento» y el adaptador compara SHA-1 con un SHA-1 calculado al validar. La opción (b) **cambia el puerto y la suite**: exigiría un ADR |
| 10 | **Vincular un documento a dos tickets** (AD y Licencias) y que vincular dos veces no falle | RF-40, T18 | `test_vincular_un_documento_a_dos_tickets_es_idempotente` | Consultar el vínculo antes de crearlo, en el adaptador |
| 11 | Crear o actualizar el usuario del colaborador **sin credenciales** de inicio de sesión | RF-21 | `test_asegurar_usuario_es_idempotente` | Buscar por un identificador estable antes de crear |
| 12 | Leer activos (con número de serie, modelo, fecha y si tiene acta) y licencias por usuario | RF-23, RF-33 | `test_leer_activos_y_licencias` | Una llamada por tipo de activo en el adaptador |
| 13 | Exigir la plantilla de solución por categoría al resolver | SUP-04, T5 | — | Ya mitigado: el núcleo no cuenta un ticket sin solución (RF-24) |
| 14 | Inyectar fallos contra GLPI en contenedor (timeout después de escribir, caída de N llamadas) | La suite de contrato debe correr contra GLPI **sin cambios** (3.2) | Toda la sección de fallos | Un proxy (p. ej. toxiproxy) que implemente `InyectorDeFallos` en `tests/contratos/protocolos.py` |

## Cómo se cierra

1. Se escribe la fábrica real en `tests/contratos/conftest.py` (`FABRICAS["glpi"]`), con un `Tecnico` que trabaja los tickets por la API y un `InyectorDeFallos` sobre el proxy.
2. La suite completa de `test_sistema_de_tickets.py` debe pasar **sin modificar una sola prueba**.
3. Si el punto 9 obliga a cambiar el puerto, se escribe el ADR antes de tocar la firma.

## Adaptador escrito antes del spike (11/10/2026)

`src/jml/adaptadores/salida/glpi/cliente.py` implementa el puerto sobre la API v1 y pasa la suite de contrato contra `tests/dobles/glpi_api.py`, un GLPI simulado que sigue la documentación. **El spike 0.3 debe confirmar** cada supuesto del simulador:

| Punto | Cómo lo resuelve el adaptador | Confirmar en GLPI 11 real |
|---|---|---|
| 1 | `initSession` con `App-Token` + `Authorization: user_token`; renueva la sesión si recibe 401 | Que la API v1 siga habilitada en GLPI 11 y que el perfil de servicio alcance; si no, ADR-014 hacia la v2 |
| 2 | `externalid` = clave; búsqueda con `searchText[externalid]` (por subcadena) y filtro exacto; **purga** de duplicados tras crear | Que `externalid` exista en `Ticket` y se pueda escribir por la API |
| 3 | Crea directamente con `status: 4` («En espera») y `time_to_resolve` en hora de Bogotá | Que GLPI acepte crear en espera y no lo cambie una regla |
| 4 | Categoría por `completename`; desconocida → 0 (la regla la manda a «Revisión manual») | Formato del `completename` (`JML > …`) |
| 5 | Una llamada por ticket más `ITILSolution` y `Document_Item` | Rendimiento con 100 tickets |
| 6 | 1→Nuevo, 2 y 3→En curso, 4→En espera, 5→Resuelto, 6→Cerrado | — |
| 7, 8 | Busca por `sha1sum`; si no existe, sube multipart (`uploadManifest` + `filename[0]`) | Que `sha1sum` sea buscable y el límite de subida admita 20 MB |
| 9 | Descarga con `Accept: application/octet-stream` y calcula SHA-256 | Que la descarga por la API funcione con el perfil de servicio |
| 10 | Consulta `Document/{id}/Document_Item` antes de crear el vínculo | — |
| 11 | `registration_number` = id del colaborador; `name` = id; sin contraseña | Que la regla de usuarios no exija credenciales |
| 12 | `Computer` con `users_id`; `Infocom.delivery_date`; acta = documento vinculado; `SoftwareLicense.users_id` | Dónde registra el equipo de Inventario la fecha de entrega y la asignación de licencias |
| 14 | El simulador inyecta los fallos en el transporte | Toxiproxy para correr la suite contra GLPI en contenedor |
