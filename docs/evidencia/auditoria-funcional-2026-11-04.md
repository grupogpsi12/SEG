# Auditoría funcional del 04/11/2026

**Alcance:** la aplicación a través de BunkerWeb, con navegador real y los datos del stack local. Motivo: el equipo informó errores 4xx y funciones que no respondían. Evidencia: `V-02-VERDE`, `V-02-INTEGRACION`, `V-02-RENDIMIENTO`, `V-02-RENDIMIENTO-NO-CUMPLE` y `V-02-CORRIDA1-INGRESO-AGOTADO`.

## Resultado

Se encontraron y corrigieron siete defectos. En la última corrida, el recorrido por roles terminó sin respuestas 4xx ni 5xx, sin errores de consola y sin desbordes.

| # | Defecto | Efecto | Causa | Corrección |
|---|---|---|---|---|
| 1 | Filtros de Tickets «no funcionan» | 429 y la página desaparece al filtrar dos veces en menos de 0,7 s | Límite de 2 r/s, sin ráfaga | 10 r/s en páginas con sesión (ADR-034) |
| 2 | Enlace a la solicitud en Tickets | 404 para técnicos y Administrador | El detalle es de RRHH y de quien la registró | Enlace solo a quien puede abrirla |
| 3 | Enlace al colaborador en Tickets | 403 para el Administrador | La ficha es de los técnicos (T10) | Nombre sin enlace para el Administrador |
| 4 | Columna Colaborador | Mostraba el id interno | La fila no traía el nombre | Muestra el nombre |
| 5 | Panel central de GLPI | 9 de 26 tarjetas con 429 | ADR-033 se verificó con menos peticiones que el caso real | 60 r/s en `/ajax/` y 10 r/s en `/front/locale.php` (ADR-036) |
| 6 | `/favicon.ico` | 404 en cada sesión nueva | La página no declaraba icono | Icono propio |
| 7 | Archivo del editor en `/static/` | `.code-workspace` publicado, sin datos sensibles | No estaba en `.dockerignore` | Excluido de la imagen |

## Introducidos y corregidos durante este trabajo

| Defecto | Cómo se detectó | Corrección |
|---|---|---|
| Mis solicitudes con p95 de 1058 ms (meta de RNF-06: 800 ms), por una consulta de tickets por fila | `carga.sh` | Una consulta agregada, comparada con el oráculo: 682 ms |
| Contrato de `import-linter` roto: los adaptadores importaban `config` | `lint-imports` | El token se lee en `settings` |
| `preparar-entorno.sh` vaciaba `infra/.env` si faltaba un valor | Al ejecutarlo sin `secretos.sh descifrar` | Escribe a un temporal y conserva los valores anteriores |
| No se podía retirar el acceso a una cuenta que ya no existe en Supabase | Revisión del flujo | Se retira el acceso local igual |

## Qué se verificó

| Verificación | Resultado |
|---|---|
| Recorrido por `solicitante`, `rrhh`, `tecnico_ad`, `auditor` y `administrador`: enlaces, filtros, formularios vacíos, ráfaga de filtros y vista móvil | 0 hallazgos |
| Matriz de autorización: 540 celdas de rol, ruta y método | Todas dan lo esperado |
| CRUD de usuarios por el WAF: vincular, roles incompatibles, colaborador inexistente, desactivar y reactivar | Correcto, sin 4xx |
| Aislamiento de `admin-usuarios` | `web` lo alcanza; el worker no; `service_role` no está en `web` ni en `worker` |
| Interfaz de extremo a extremo: ING, VAC, RET y EMG hasta GLPI | 4 de 4 |
| Integración con PostgreSQL 17 | 273 pasan, 18 omitidas |
| WAF en los dos sitios | Todo según lo esperado |
| Controles de los límites: raíz de GLPI, fichas e ingreso | Siguen frenando |
| Rendimiento: 300 colaboradores y 20 usuarios | Las 9 páginas cumplen |

## Qué no se verificó

- **Crear, desactivar y eliminar una cuenta real en Supabase.** Se probó contra el GoTrue simulado y, en real, solo la lectura de cuentas. Las reglas de la auditoría limitan Supabase a lectura, y el proyecto es compartido por el equipo.
- **GLPI con sesión iniciada.** Las ráfagas a `/ajax/` se probaron sin sesión, por lo que GLPI responde 302. Prueban el límite del WAF, no el panel dibujado. Falta abrirlo en un navegador.
- **Los otros tres roles técnicos en el navegador.** No hay usuarios con esos roles en el stack. Están cubiertos por la matriz de autorización.
- **Tecnología de asistencia.** Sigue pendiente la evaluación con lector de pantalla.

## Riesgos que quedan

- Quien comprometa `web` puede pedir operaciones sobre cuentas, aunque no obtenga la clave (ADR-035).
- La sincronización sigue sin avisar cuando un ticket desaparece de GLPI. Requiere una decisión del equipo sobre el SRS.
- La página de usuarios se alarga con muchas cuentas. Hoy hay 40 filas, casi todas de pruebas E2E, y no tiene paginación.
