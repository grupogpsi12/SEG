# Propuestas de ADR de la auditoría (F8-04)

Estado de todas: **Propuesta** (no vigente). Según `CLAUDE.md`, una decisión vigente solo cambia con un ADR nuevo aceptado por el equipo; por eso estas propuestas **no** se copian a `docs/decisiones.md` ni modifican el SRS. Si el equipo acepta una, se numera como ADR-031 en adelante, se copia allí y, si cambia un requisito, `docs/SRS.md` sube de versión (2.5). Si el equipo decide distinto, se respeta y la disidencia se anota en `docs/decisiones.md`.

Ordenadas por la prioridad de los hallazgos que las originan (`score-global.md`).

---

## P-1 · Red dedicada para el tramo worker ↔ GLPI (B-32, N-1) — **recomendada, la de mayor valor**

**Contexto.** F7-04 midió 382 peticiones con `App-Token` y 378 con `Session-Token` en claro, y 4 `user_token`, en la red `app`, que comparten `web`, `bunkerweb`, `glpi` y `worker`. `web` nunca llama a GLPI (invariante, probado en `test_caidas.py`), pero puede leer su tráfico si se compromete.

**Decisión propuesta.** Crear la red interna `glpi_api`, compartida SOLO por `worker` y `glpi`, y sacar a `worker` de `app`. BunkerWeb sigue llegando a GLPI por `app` para la interfaz web de los técnicos.

**Alternativas.** (a) TLS interno hacia GLPI: cifra, pero exige certificados internos y rotación. (b) Aceptar el riesgo: el tramo es interno y la API está cerrada hacia fuera (RS-02). Descartada como única medida porque la red dedicada cuesta unas líneas de compose y TLS interno no.

**Consecuencias.** Baja el residual de B-32 de 5,4 a ~2,4. Prueba: `captura-trafico.sh` debe dar 0 en las líneas N-1 desde la red `app`, y una prueba de `test_infra.py` exige que `web` y `bunkerweb` no estén en `glpi_api`.

---

## P-2 · Política de refresco de imágenes de terceros (B-31, B-18)

**Contexto.** Las cinco imágenes están fijadas por digest (reproducibilidad) y por eso envejecen: 18 hallazgos CRÍTICOS (6 CVE distintas) y 303 HIGH de Trivy, ninguno en KEV. Hoy no hay un ritmo escrito de refresco; `imagen.yml` solo vigila la imagen propia.

**Decisión propuesta.** Revisar los digests cada mes y ante cualquier entrada nueva en KEV que afecte a un paquete presente; correr `trivy-imagenes.py` en un trabajo nocturno de la CI (G4) y fallar si hay una vulnerabilidad en KEV o una CRÍTICA con parche. Las exenciones viven en `exenciones-trivy.md` con fecha de revisión.

**Consecuencias.** B-31 pasa de «aceptado con exención» a «controlado»; costo: media hora al mes y el riesgo de que un refresco rompa algo (se mitiga con `pruebas.sh` y la suite contra GLPI real).

---

## P-3 · Endurecer el tramo GLPI ↔ MariaDB (B-30)

**Decisión propuesta.** `local_infile=0` en MariaDB (una línea en el comando). Cifrar el tramo con TLS (`require_secure_transport=ON` y certificado interno) solo si P-1 no se acepta o si el tramo deja de ser una red interna de dos contenedores.

**Alternativa.** Dejarlo: red `internal: true` con dos contenedores, usuario sin privilegio FILE. Riesgo Bajo (3,0).

**Consecuencias.** Una prueba que exija `local_infile = OFF` en `mariadb-glpi.sh`.

---

## P-4 · Incorporar las amenazas N-1 a N-5 al SRS §7

| ID | Amenaza | Estado tras la auditoría |
|---|---|---|
| N-1 | Tokens de GLPI en claro en el tramo worker→GLPI | Medida (B-32); mitigación en P-1 |
| N-2 | API de BunkerWeb alcanzable por TCP desde la red `app` | Medida y descartada como exposición real (B-29); corregir RS-19 |
| N-3 | `gunicorn` con un solo proceso | Ver P-6 |
| N-4 | Deriva entre el PostgreSQL local y Supabase | Medida: catálogo igual salvo extensiones y roles de la plataforma (F3-PAR) |
| N-5 | Deriva documental | Cerrada con `test_documentos.py` y `verificar_entrega.py` |

**Decisión propuesta.** Agregarlas al SRS con su evidencia y subir la versión a 2.5. **Corregir de paso RS-19** («el puerto 5000 es alcanzable por TCP en `app`; solo responde dentro de `API_WHITELIST_IP` con token») y **RNF-11** (ver P-7).

---

## P-5 · Verificar la firma del JWT de Supabase (B-28)

**Contexto.** `_claims` lee `aal` y `sub` del JWT sin verificar su firma ni `exp`/`iss`. El token llega por TLS `verify-full` en respuesta a una petición del servidor, lo que acota el riesgo (3,6).

**Decisión propuesta.** Verificar la firma HS256 con el secreto JWT del proyecto (`hmac` y `hashlib`, unas 30 líneas, sin dependencia nueva) y comprobar `exp` e `iss`. El secreto entra como un secreto nuevo en `/run/secrets` (SOPS).

**Alternativa.** Aceptar con la justificación del canal (ADR-017 ya lo dice) y registrar la disidencia. **Se pide decisión del equipo antes de implementar**: añade un secreto que operar.

---

## P-6 · `gunicorn` de un solo proceso (B-06, N-3)

**Contexto.** Los desafíos de segundo factor viven en la memoria del proceso (ADR-017/S-29). Con varios procesos, el desafío creado en uno no existiría en otro; con uno, un reinicio los pierde (se midió: el desafío ya no existe y no entra, nada se abre).

**Decisión propuesta.** **Aceptar un proceso con 8 hilos** a la escala del proyecto (50–300 colaboradores, ~50 eventos al mes), con el procedimiento documentado: un reinicio solo obliga a repetir el inicio de sesión. No pasar a varios procesos sin llevar los desafíos a la base de datos.

**Consecuencias.** B-06 queda aceptado con motivo. Escalar exigiría una tabla de desafíos (cambio de puerto: ADR aparte).

---

## P-7 · Corregir RNF-11 (B-12, B-14)

**Contexto.** RNF-11 pide cobertura ≥ 80 %; la compuerta real exige 95 % (dominio) y 90 % (aplicación). Y «cobertura de ramas 99 %» es la cifra combinada de líneas y ramas; las ramas puras son 97,7 % en dominio y 94 % en aplicación.

**Decisión propuesta.** RNF-11: «cobertura de ramas ≥ 95 % en dominio y ≥ 90 % en aplicación, medida por `coverage` con `--branch`; se informan ambas cifras, la combinada y la de ramas puras».

---

## P-8 · El Auditor lee solicitudes (B-26)

**Contexto.** El SRS dice que el Auditor puede «leer solicitudes sin campos restringidos»; la aplicación le responde 404.

**Alternativas.** (a) Implementar una vista de solo lectura con detalle sin campos restringidos y un listado paginado (~3 h, entra a la matriz de autorización como celda nueva). (b) Quitar la frase del SRS y dejar al Auditor solo con la cadena.

**Recomendación.** (a): quien audita necesita contrastar la cadena con la solicitud que describe. Mientras tanto, la celda está registrada como excepción conocida en `matriz-authz.csv`.

---

## P-9 · Excepción «solo bunkerweb publica puertos» para la reportería (B-27)

**Decisión propuesta.** Escribir en ADR-023 y en el invariante 14: «la reportería del WAF, opcional, publica Grafana (3000) y el receptor de logs (24224) únicamente en `127.0.0.1`; ningún otro servicio publica fuera de BunkerWeb». La prueba `test_borde.py` ya vigila la forma estricta.

---

## P-10 · Dónde se registran las denegaciones por rol (B-25)

**Contexto.** Cada denegación por rol deja ahora el evento `acceso.denegado` en el log estructurado (usuario, ruta, método y `correlation_id`). La cadena de auditoría (SRS RF-35) **no** los incluye.

**Decisión propuesta.** Mantenerlo en el log y NO en la cadena: la cadena se escribe con un candado global, y un usuario que repitiera una URL prohibida inflaría la cadena y la volvería lenta; el WAF limita el ritmo, pero la cadena es para decisiones, no para ruido. Si el equipo quiere los intentos en la cadena, hacerlo con un máximo por usuario y minuto.
