# Spike 0.3 — API de GLPI 11 (11/10/2026)

Hecho con GLPI **11.0.11** (imagen `glpi/glpi` fijada por digest) en `infra/compose.yaml`, contra el adaptador real `SistemaDeTicketsGlpi` (API REST v1, `apirest.php`). Complementa `glpi-puerto.md`, que listaba lo que había que confirmar.

## Resultado

| # | Punto | Resultado |
|---|---|---|
| 1 | Autenticación de servicio | **API v1** con `App-Token` + `Authorization: user_token`. Cliente de API restringido a `10.20.40.3`–`10.20.40.254`: la red interna sin la puerta de enlace ni el WAF. Usuario `jml-servicio` con un perfil acotado. Sin inicio de sesión por credenciales en la API, y API cerrada en el WAF (auditoría del 12/10/2026). ADR-014 decidido: v1, sin OAuth; la v2 de GLPI 11 no se necesita |
| 2 | Buscar un ticket por referencia externa | **Sí**: el campo `externalid` existe en `Ticket` y se puede escribir. `searchText` busca por subcadena y `externalid` **no es único**, así que el adaptador filtra exacto y purga duplicados |
| 3 | Ticket en «En espera» | **Sí**: `status: 4` al crear |
| 4 | Categoría ITIL y enrutamiento | **Sí**: 114 categorías `JML/<tipo>/<cola>/<acción>`; la regla asigna el grupo y una categoría desconocida va a «Revisión manual» (CA-03 verificado) |
| 5 | Leer estado, solución y documentos | **Sí**: `ITILSolution` y `Document_Item` por ticket |
| 6 | Mapeo de estados | 1 Nuevo, 2 y 3 En curso, 4 En espera, 5 Resuelto, 6 Cerrado. Un ticket recién creado se observa «En curso» porque la regla le asigna el grupo (S-34) |
| 7 | Subir un PDF de 20 MB | **Sí**, tras subir los límites de PHP de GLPI (`infra/glpi/php-jml.ini`) y `document_max_size`; antes respondía 413 |
| 8 | Subir el mismo contenido dos veces | Se busca por `sha1sum` antes de subir: un solo documento |
| 9 | Hash del documento | GLPI guarda **SHA-1**. El adaptador descarga el documento y calcula el SHA-256 (opción a de la lección 24). **No cambia el puerto** |
| 10 | Vincular un documento a dos tickets | **Sí**, idempotente (se consulta antes de crear el vínculo) |
| 11 | Usuario sin credenciales | Se crea por `registration_number` = id del colaborador, sin contraseña |
| 12 | Activos y licencias | `Computer` y `SoftwareLicense` por `users_id`; fecha de entrega de `Infocom`; acta = documento vinculado al equipo |
| 13 | Plantilla de solución por categoría | Las 4 plantillas se crean (`SolutionTemplate`); GLPI no obliga a usarlas, y el núcleo no cuenta un ticket sin solución (RF-24) |
| 14 | Inyectar fallos | Un transporte HTTP que corta o duplica la petición (`TransporteConFallos`): sin Toxiproxy |

## Lo que GLPI hace distinto de lo que decía la documentación

1. **`priority` se ignora al crear.** GLPI la calcula desde urgencia × impacto: con urgencia = impacto = 3, 4 o 5 sale la prioridad 3, 4 o 5. Con 5 salta la regla del SLA de la emergencia (1 hora) y GLPI calcula el vencimiento.
2. **`time_to_resolve` se ignora al crear**; se fija con un `PUT` posterior, y solo si el perfil tiene el **bit 256 del derecho `slm`**. Sin él, GLPI responde 200 y no guarda nada. Si el ticket ya tiene SLA, el adaptador no lo toca.
3. **Responde 200 con una lista a `Ticket/no-existe`** y acepta vincular un documento con id 0: los identificadores se validan como enteros antes de pedirlos.
4. **Los tokens se guardan cifrados** (GLPI 11): hay que descifrarlos con la clave de GLPI para entregarlos (`infra/glpi/bootstrap.php`). El token personal de un usuario nuevo no se guarda si se pide por la API de usuarios: se escribe directo en la base, cifrado.
5. **Trabaja en UTC** aunque el contenedor tenga `TZ=America/Bogota`. El adaptador envía UTC (S-35).
6. **Trae cuentas de demostración** (`glpi`, `post-only`, `tech`, `normal`) con contraseñas por defecto: `preparar-glpi.sh` las deshabilita y cambia la del administrador.

## Cómo se reproduce

```bash
export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"        # Git Bash en Windows
COMPOSE="-f infra/compose.yaml -f infra/compose.local.yaml" infra/glpi/preparar-glpi.sh
docker compose -f infra/compose.yaml -f infra/compose.local.yaml run --rm configurar-glpi
JML_GLPI_DE_PRUEBAS=si infra/scripts/contrato-glpi.sh     # 30 pruebas contra el GLPI real
```

`contrato-glpi.sh` corre dentro de la red de Docker y **borra los tickets cuya clave empieza con `SOL-`**: úselo solo con un GLPI de pruebas.

## Pendiente

- Correr esta suite en la CI (necesita levantar GLPI y MariaDB como servicios).
- La zona horaria de los técnicos en GLPI (S-35) y su doble factor: pasos manuales de operación.
- ~~Los flujos VAC, RET y EMG de extremo a extremo~~: hechos el 12/10/2026 (`tests/integracion/test_flujos_glpi_real.py`).
