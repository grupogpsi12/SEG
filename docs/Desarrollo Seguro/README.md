# Desarrollo Seguro: entregables

**SSGUI · Sistema de Solicitud de Gestión de Usuarios Interno** · ANDINA S.A.S. (empresa ficticia; todos los datos son ficticios)
José Bedoya, Carlos Ruiz, Luis Cerón y Cristian Caro · Institución Universitaria Politécnico Grancolombiano · Taller de Desarrollo Seguro de Software · Grupo G01 · Docente: José Eduardo Patiño Santafé

## Lista de entregables

| N.º | Entregable | Contenido | Archivo |
|---|---|---|---|
| 1 | Resultados de pruebas funcionales | Pruebas de casos de uso: suite automatizada, recorrido con navegador a través del WAF, pruebas contra GLPI 11 y criterios de aceptación | [PDF](1-Resultados-de-pruebas-funcionales.pdf) · [fuente](1-Resultados-de-pruebas-funcionales.md) |
| 2 | Resultados de pruebas de vulnerabilidades | Resultados obtenidos con escáneres: OWASP ZAP, sqlmap, Nikto, testssl.sh, Trivy (con KEV y EPSS) y Docker Bench, a través del WAF y directamente contra la aplicación | [PDF](2-Resultados-de-pruebas-de-vulnerabilidades.pdf) · [fuente](2-Resultados-de-pruebas-de-vulnerabilidades.md) |
| 3 | Análisis de captura de tráfico de la aplicación web | Capturas para casos de uso: ingreso, vacaciones, retiro, emergencia, consulta técnica y verificación de la auditoría, en tres puntos de la red | [PDF](3-Analisis-de-captura-de-trafico.pdf) · [fuente](3-Analisis-de-captura-de-trafico.md) |
| 4 | Propuesta de controles de seguridad de la información | Controles en términos de confidencialidad, autenticidad e integridad, con la descripción y los diagramas de la arquitectura de seguridad propuesta | [PDF](4-Propuesta-de-controles-de-seguridad.pdf) · [fuente](4-Propuesta-de-controles-de-seguridad.md) |

Las figuras de los entregables están en [`figuras/`](figuras/).

## Arquitectura de referencia

Los cuatro documentos corresponden a la arquitectura definida en la primera entrega (`DS_1eraEntrega_Local`): todo el sistema se ejecuta en la máquina local con Docker Desktop; la base de datos de la aplicación es PostgreSQL 17 en contenedor; GLPI 11 conserva su MariaDB; Supabase Auth es el único servicio externo; los secretos son Docker secrets fuera del repositorio; el borde usa un certificado autofirmado para `app.localhost` y `glpi.localhost`; y la auditoría exportada y los respaldos se copian a un disco externo. En el repositorio, esta decisión es el ADR-031 y la versión 2.5 del SRS.

## Evidencia y reproducción

- La evidencia cruda (comando exacto, salida enmascarada, versión de la herramienta, commit y fecha) está en `auditoria/evidencia/` y se empaqueta en `docs/entregables/auditoria/evidencias/`. Las capturas `.pcap` no se versionan porque contienen tokens y valores centinela; se conservan el comando y el análisis.
- Los PDF se regeneran desde los `.md` con un comando: `uv run python auditoria/scripts/generar-desarrollo-seguro.py`.
- Las capturas por caso de uso se repiten con `JML_GLPI_DE_PRUEBAS=si bash auditoria/scripts/captura-por-caso-de-uso.sh`.
