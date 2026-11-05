# Entrega 3 — Pruebas, vulnerabilidades, tráfico y controles

Cuatro documentos PDF con su evidencia cruda reproducible. Todo se ejecutó el 24/10/2026 contra el
despliegue local completo (`infra/compose.yaml` + `infra/compose.local.yaml`): BunkerWeb (WAF),
aplicación, worker, PostgreSQL 17 local (sustituye a Supabase, ADR-028), GLPI 11.0.11 y MariaDB.

**No se escaneó Supabase** (servicio de terceros en la nube, sin autorización para pruebas activas):
su PostgreSQL se sustituyó por el local con los mismos roles, esquema y dueño separado. Los secretos
y tokens de las evidencias están enmascarados.

## Documentos

| PDF | Contenido |
|---|---|
| `Documento-1-Pruebas-funcionales.pdf` | Suite automatizada (1581 pruebas) y recorrido de 34 pasos por los casos de uso a través del WAF, con capturas de pantalla. |
| `Documento-2-Pruebas-de-vulnerabilidades.pdf` | nmap, testssl.sh, OWASP ZAP, sqlmap (nivel 3, con cabeceras), Nikto, Trivy y auditoría de configuración de las dos bases. Cinco hallazgos. |
| `Documento-3-Analisis-de-trafico.pdf` | Captura (tcpdump) y análisis (tshark) del tráfico en tres puntos, por caso de uso; confidencialidad de los campos restringidos sobre el cable. |
| `Documento-4-Controles-de-seguridad.pdf` | Arquitectura de seguridad (dos diagramas) y controles de confidencialidad, autenticidad e integridad, con su evidencia y los hallazgos abiertos. |

## Evidencia cruda — `evidencias/`

- `funcionales/`: `junit-suite.xml` (suite), `casos-de-uso.json` / `.txt` (recorrido), `pantallas/` (capturas).
- `vulnerabilidades/`: salidas de nmap, `testssl-app.txt`, `zap-*.{json,html,txt}`, `sqlmap-*.txt`,
  `nikto-*.txt`, `trivy/*.{json,txt}`, `bases-config.txt`, `docker-puertos-publicados.txt`.
- `trafico/`: `*.pcap` crudos y `analisis/` (salidas de tshark por tramo y por caso de uso).

## Reproducir

Con el stack local arriba (ver `docs/probar-localmente.md`) y el entorno Python (`uv sync`):

```bash
# 1. Suite automatizada
.venv/Scripts/python.exe -m pytest tests/dominio tests/aplicacion tests/contratos tests/escenarios tests/adaptadores --junitxml=docs/entregables/evidencias/funcionales/junit-suite.xml

# 2. Recorrido de casos de uso (crea las sesiones de prueba en la base local primero; ver el guion)
.venv/Scripts/python.exe docs/entregables/scripts/casos_de_uso.py <sesiones.env> docs/entregables/evidencias/funcionales/casos-de-uso.json

# 3. Auditoría de las bases
bash docs/entregables/scripts/auditar-bases.sh > docs/entregables/evidencias/vulnerabilidades/bases-config.txt

# 4. Análisis de las capturas (dentro de netshoot)
docker run --rm -v "<trafico>:/cap" -v "<scripts>:/s:ro" nicolaka/netshoot sh /s/analizar-trafico.sh

# 5. Generar los cuatro PDF
cd docs/entregables/scripts && for n in 1 2 3 4; do python informe_$n.py; done
```

Los guiones de escaneo (nmap, ZAP, sqlmap, Trivy, testssl, Nikto) se lanzaron con las imágenes de
contenedor `instrumentisto/nmap`, `zaproxy/zap-stable`, `aquasec/trivy`, `drwetter/testssl.sh`,
`ghcr.io/sullo/nikto` y `nicolaka/netshoot`; los comandos exactos quedan citados en cada PDF.
