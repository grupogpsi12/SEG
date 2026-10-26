# Entrega de la auditoría · Sistema integrado de eventos laborales (JML)

Andina Servicios S.A.S. es una empresa ficticia y todos los datos lo son. Politécnico Grancolombiano · Gerencia de Proyectos en Seguridad de la Información · Grupo D01.

Generada el 25/10/2026 desde el commit `610fa6d` de la rama `auditoria/entrega` (base auditada: `5fa3f32`). Todo lo de esta carpeta se regenera con un comando: `uv run python auditoria/scripts/generar-entrega.py`.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `informes/0-Informe-maestro` | El informe extenso: alcance, método, resultados, hallazgos por prioridad, remediación y lo que queda pendiente (`.md` y `.pdf`) |
| `informes/1-Pruebas-y-cobertura` | Suite, cobertura de ramas, mutación, Gherkin, defectos sembrados |
| `informes/2-Vulnerabilidades` | Estático, dependencias, imágenes, escaneo dinámico, red, bases, TLS, WAF |
| `informes/3-Analisis-de-trafico` | Capturas por tramo, centinelas, tokens en claro |
| `informes/4-Controles-de-seguridad` | Controles por propiedad, criterios de aceptación CA-01 a CA-21, ASVS y el Excel del Anexo A |
| `evidencias/` | `funcionales`, `estaticos`, `vulnerabilidades`, `trafico`, `autorizacion`, `disponibilidad`, `controles-positivos`. Cada carpeta lleva `cmd.txt`, `salida.txt`, `version.txt`, `commit.txt`, `fecha-utc.txt` y `codigo.txt` |
| `hallazgos/B-nn.md` | Un archivo por hallazgo, con DREAD, evidencia, corrección, prueba de regresión, falsabilidad e indicador temprano |
| `scripts/` | Los guiones que generan la evidencia y los PDF |
| `anexos/` | Puntajes DREAD, propuestas de ADR, defectos sembrados, triage, verificación del Anexo A (PDF y Excel) |
| `trazabilidad.csv`, `metricas.json`, `asvs-l2.csv`, `herramientas.lock`, `dread-anclas.md` | Datos de la auditoría |
| `manifiesto.sha256` | El hash de cada archivo de esta carpeta |
| `verificar-entrega.py` | Falla si hay un marcador sin reemplazar, un criterio de aceptación sin evidencia o un hash que no cuadra |

## Cómo comprobarla

```bash
python docs/entregables/auditoria/verificar-entrega.py docs/entregables/auditoria
```

## Lo que NO se incluye

- Los archivos `.pcap` de las capturas de tráfico: llevan tokens de GLPI y valores centinela. Se conservan el comando, el análisis enmascarado y el hash.
- Cualquier secreto. Los valores están enmascarados y `gitleaks` se corrió sobre esta carpeta.

## Alcance y reglas de compromiso

Solo el stack local de Docker. GLPI 11 desechable. Supabase únicamente en lectura de catálogo, autorizada por el equipo el 24/10/2026. Nada de Azure, Cloudflare ni terceros. Antes de cada escáner: copia de la base, worker detenido, baneos levantados y un identificador de correlación de laboratorio; después, restauración.
