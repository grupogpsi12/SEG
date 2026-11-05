# Verificación del Anexo A («AnexoA. Tablas.xlsx»): ¿se cumple lo que dicen las 18 hojas?

Fecha: 25 de octubre de 2026 · Archivo: `AnexoA. Tablas.xlsx` (SHA-256 `44456086…9c6f`, volcado en `auditoria/referencias/AnexoA-tablas.json`)
Alcance: stack local (Docker Compose, GLPI 11 desechable, PostgreSQL 17 local). Supabase solo en lectura de catálogo.

**Actualización del 25/10/2026 (ADR-031, SRS v2.5).** La arquitectura vigente es 100 % local. El Excel todavía describe la versión con Azure, Let's Encrypt y Cloudflare; esas filas pasan de «no verificable en local» a **no aplica**, con la pieza local que las reemplaza en la nota.

## 1. Resultado en una tabla

157 filas en 18 hojas. Cada una se verificó con pruebas que **leen la celda del Excel** y la comparan con lo que el sistema hace (`tests/escenarios/test_anexo_a.py`, 64 pruebas), con las pruebas existentes del proyecto, o con mediciones en el stack. Ninguna fila falla.

| Resultado | Filas | Qué significa |
|---|---|---|
| **CUMPLE** | **139** | La celda se contrastó con el sistema y coincide |
| **PARCIAL** | **6** | Se cumple en parte; la salvedad está explicada y trazada a un hallazgo |
| **NO VERIFICABLE EN LOCAL** | **2** | Exigen el servicio real de Supabase Auth; no se afirma nada |
| **NO APLICA (ADR-031)** | **10** | La celda describe Azure, Let's Encrypt o Cloudflare, que la arquitectura vigente descarta |
| FALLA | 0 | — |

| Hoja | Tema | Filas | Cumple | Parcial | No verificable | No aplica |
|---|---|---|---|---|---|---|
| I | Funciones F1–F8 | 8 | 8 | | |
| II | Decisiones de arquitectura (ADR) | 28 | 26 | 1 | | 1 |
| III | Puertos, protocolos y flujos | 20 | 11 | | 2 | 7 |
| IV | Roles y segregación de funciones | 8 | 6 | 2 | |
| V | Eventos, aprobación y SLA | 6 | 6 | | |
| VI | Estados de la solicitud | 7 | 7 | | |
| VII | Clases de tickets | 3 | 3 | | |
| VIII | Acciones por cola | 6 | 6 | | |
| IX | Suspensión y deshabilitación | 6 | 6 | | |
| X | Plantillas de solución | 4 | 4 | | |
| XI | Derivación del estado de las cuentas | 6 | 6 | | |
| XII | Campos por evento | 6 | 6 | | |
| XIII | Perfiles de acceso | 6 | 6 | | |
| XIV | Recursos compartidos | 9 | 9 | | |
| XV | RF autenticación | 6 | 6 | | |
| XVI | RF solicitudes | 6 | 6 | | |
| XVII | RF aprobación, emisión y tickets | 16 | 16 | | |
| XVIII | RI interfaces externas | 6 | 1 | 3 | | 2 |

Detalle fila por fila, con las pruebas y evidencias de cada una: [`anexo-a-matriz.csv`](anexo-a-matriz.csv). El informe JUnit de la suite (2574 pruebas, 0 fallas, 2 omitidas con motivo, 1 `xfail` declarada) está en `evidencia/funcionales/ANEXO-A-JUNIT`.

## 2. Lo que NO se cumple del todo (6 filas parciales)

| Hoja · fila | Qué falta | Hallazgo |
|---|---|---|
| IV · **Solicitante** | La celda del Excel promete «creación de cuentas», «eliminaciones de cuentas» y «generar correos electrónicos». El sistema no lo hace, y **no debe**: ADR-019 prohíbe las acciones sobre directorios y los correos están fuera de alcance. Lo que sí cumple es lo que dice el SRS (sus vacaciones y renuncia, los cambios de sus subordinados, consultar y cancelar sus pendientes). **Es un error del Excel, no del sistema.** | — |
| IV · **Auditor** | «Leer solicitudes sin campos restringidos»: la aplicación responde 404. Sí lee la auditoría y verifica su integridad. | B-26 · S-39 · propuesta P-8 |
| XVIII · **RI-02** | Todas las operaciones con GLPI funcionan contra GLPI 11 real (30 de 30). Pero la cuenta de servicio, que el requisito limita «a esas operaciones», tiene además **borrar y purgar tickets**. | **B-35 (nuevo)** · P-11 |
| XVIII · **RI-01** | WCAG 2.1 AA: 50 comprobaciones mecánicas en verde. La conformidad completa pide además una evaluación con lector de pantalla, que no se hizo. | B-34 (corregido) |
| XVIII · **RI-04** | `service_role` solo en `admin-usuarios`: comprobado. El servicio real de Supabase Auth no se ejerció desde el servidor. | B-28 |
| II · **ADR-005** | «Cuenta única de RRHH» se cumple por operación; el sistema no impide dar el rol a dos personas. | — |

Con ADR-031 dejaron de ser parciales: ADR-002 (no hay VM; Docker Compose local verificado), ADR-009 (cumple: el principio de archivos en `/run/secrets` se mantiene) y la fila 9 de la Tabla III (Supabase PostgreSQL ya no es la base; la vigente es PostgreSQL 17 en `pg_net`, verificada).

## 3. Lo que esta verificación encontró y no estaba en la auditoría

1. **B-34 (Bajo, corregido).** RI-01 pide WCAG 2.1 AA y no había ninguna prueba que lo midiera. Al calcular los contrastes: el texto cumple (mínimo 6,09:1), pero el borde de los campos medía **1,39:1** y las barras del gráfico **2,07:1**, ambos bajo el 3:1 de WCAG 1.4.11. Corregido con dos colores (3,74:1 y 3,40:1); rojo y verde registrados (`B-34-ROJO`, `B-34-VERDE`).
2. **B-35 (Bajo, abierto).** El perfil «JML - servicio» concede `BORRAR` y `PURGAR` sobre tickets (viene de `infra/glpi/bootstrap.php`, porque la suite de contrato limpia con él). Medido con la propia cuenta del worker. Propuesta P-11: perfil de producción sin esos derechos y un perfil de pruebas aparte.
3. **S-39 y S-40** en `docs/supuestos-nucleo.md`, con su prueba nombrada.

## 4. El Excel está desfasado respecto al SRS v2.5

Estas diferencias son de **texto**, no de comportamiento (`evidencia/funcionales/anexo-a-tablas/comparacion-con-el-srs.csv`). Conviene corregir el Excel; no lo modifiqué.

| Hoja · fila | El Excel dice | El SRS / `decisiones.md` dice |
|---|---|---|
| I | 8 funciones; F2 con «y de duplicación» | 9 funciones: falta **F3 Aprobación** (RF-12 a RF-15, que sí se cumplen); «deduplicación»; F7 Dashboard con «datos de la última sincronización» |
| II · ADR-14 | «Pendiente (sprint 0)» | **Aceptada** (spike 0.3): API v1 con App-Token y token de usuario |
| II · ADR-28 | título abreviado | añade «(revisión externa H1 a H3)» |
| II | llega hasta el ADR-28 | existen **ADR-029, ADR-030 y ADR-031** (secretos con SOPS + age; paginación; despliegue local) |
| II · ADR-02, 09, 15, 24 | VM de Azure, Key Vault, Supabase PostgreSQL y Cloudflare | ADR-031: Docker Desktop local, Docker secrets, PostgreSQL 17 local y Cloudflare descartada |
| III | flujos hacia Key Vault, Blob, Let's Encrypt, Cloudflare y SSH a la VM | no existen en la arquitectura vigente (SRS v2.5) |
| XVIII · RI-05, RI-06 | Azure Key Vault y Azure Blob Storage | Docker secrets en `secrets/`; volumen `exportes` y disco externo |
| IV · Solicitante | permisos de otro documento (ver §2) | «Registrar sus propias vacaciones y su renuncia…»; «Incompatible con: —» |
| IV · Técnico AD | «DashBoards» | «Dashboard» |
| XII · ING | «contratista(tercero)» y sin «(ficticio)» | «contratista»; «número de documento (ficticio)» |
| XV · RF-06 | termina en «…Administrador del sistema.» | añade el comando `vincular` para cuentas que ya existen en otra base |
| XVI · RF-10 | «aceptarse, aunque» | «aceptarse aunque» |
| XVIII · RI-03 | «El rol app_backend tiene solo los permisos de RD-02» | añade que no es dueño de ningún objeto, `BYPASSRLS`, y que las migraciones las corre `app_owner` (ADR-028) |

Las hojas **V a XI, XIII, XIV, XVII** coinciden con el SRS palabra por palabra (tras normalizar formato).

## 5. Método y límites

- **Qué prueba cada fila.** Las hojas V a X, XII a XIV se contrastan con pruebas generadas desde el Excel: emitir cada evento con el `Mundo` de pruebas y comparar prioridad, vencimiento (ING antes de la fecha; VAC el día de inicio y de regreso; CDP/CSU 1 día hábil; RET al final del último día; EMG 1 h), clases de ticket, listas de verificación por cola (frase por frase), plantillas de GLPI, campos y las matrices sembradas.
- **Controles negativos.** Las celdas «—» exigen que **no** haya ticket en esa cola; los pares de roles no prohibidos se aceptan; los flujos de red que la Tabla III no contempla se intentan y deben fallar (28 comprobaciones, 0 diferencias).
- **Límite.** Un «CUMPLE» dice que el comportamiento coincide con la celda en el stack local, que desde ADR-031 es el entorno de destino. La copia al disco externo (RD-04, RD-06) se verificó contra una carpeta que lo simula (L-01).
- **Reproducir.** `python auditoria/scripts/anexo-a-tablas-vs-srs.py` · `bash auditoria/scripts/anexo-a-puertos.sh` · `uv run pytest tests/escenarios/test_anexo_a.py` · `python auditoria/scripts/anexo-a-matriz.py`.
