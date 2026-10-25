# Evidencia de CA-12 — pruebas dinámicas de seguridad (ZAP y sqlmap)

Para quién: el equipo y quien evalúe el proyecto (ítem 5.4; CA-12, RS-11 a RS-13). **Fecha:** 24/10/2026.

**CA-12:**
- ZAP *baseline* sin alertas altas.
- sqlmap nivel 3 sin hallazgos.
- gitleaks, Trivy y pip-audit sin críticos.
- El asesor de Supabase sin hallazgos.

```bash
infra/scripts/seguridad-dinamica.sh     # informes HTML y JSON en .contrato-tmp/seguridad/
```

**Herramientas:**
- **ZAP:** `ghcr.io/zaproxy/zaproxy`, fijada por digest.
- **sqlmap 1.10.10:** instalada por hash.

**Dónde se probó:**
- **Directo, sin WAF:** contra la aplicación en el entorno desechable de `infra/scripts/carga.sh`, con 30 colaboradores y la configuración de producción. Así se ve si la aplicación resiste por sí misma.
- **A través del WAF:** el *baseline* contra `https://app.localhost`. El escaneo activo y sqlmap no van por el WAF: los bloquea, que es su trabajo (CA-20), y banean la IP una hora.

## 1. ZAP

| Escaneo | URL | Altas | Medias | Bajas | Informativas |
|---|---|---|---|---|---|
| *Baseline* (pasivo), a través del WAF | 9 | **0** | **0** | **0** | 4 |
| *Baseline* (pasivo), directo | 9 | 0 | 0 | 4 | 3 |
| Activo y autenticado como RRHH, directo | 68 | 0 | 1 | 5 | 6 |
| Activo y autenticado como técnico, directo | 50 | 1 (falso positivo) | 1 | 5 | 6 |

- **El criterio de ZAP *baseline* se cumple:** sin alertas altas, y a través del WAF sin medias ni bajas. El escaneo activo solo se hizo directo, sin WAF. [PENDIENTE: auditoría F6, con y sin exención de baneo]
- **Escaneo activo autenticado.** Una cookie de sesión y una CSRF válida, inyectadas con un *hook*, le permitieron recorrer la bandeja, los formularios de las seis solicitudes, el dashboard, la búsqueda y las fichas. No hubo inyección SQL, XSS, inyección de comandos ni inclusión de archivos.
- **«Path Traversal», alta con confianza baja.** ZAP la levantó con `documento=cuentas` (el nombre de la propia página) y sin evidencia en la respuesta. Se comprobó a mano que es un falso positivo: con `../../../../etc/passwd`, `/etc/passwd` y su versión codificada, la respuesta es la misma búsqueda vacía de 1097 bytes, sin contenido del sistema. `documento` solo se compara con un campo de la base, y la aplicación no abre ningún archivo salvo los soportes, con nombre validado.
- **«HTTP Only Site», media.** Es propio de atacar `web` directo: HTTPS y HSTS los pone el WAF (RS-01).
- **Bajas del escaneo directo.** `X-Content-Type-Options`, `Permissions-Policy`, CORP y COEP los pone BunkerWeb, con una sola fuente por cabecera (RS-07), y a través del WAF están todas. «Cookie Slack Detector» es informativa: la página cambia sin la cookie de sesión, como debe.

**Corregido por estas pruebas:**
- WhiteNoise servía los estáticos con `Access-Control-Allow-Origin: *` (riesgo medio).
- Faltaban `Cross-Origin-Resource-Policy` y `Cross-Origin-Embedder-Policy` (bajos).

Commit `89112ea`.

## 2. sqlmap (nivel 3, riesgo 1)

Corrida **preliminar**, directa (sin WAF), sobre la imagen ya corregida de gunicorn. Evidencia cruda:
`auditoria/evidencia/vulnerabilidades/B-02-sqlmap-previo/` (comando, versión, commit, fecha y sha256).

| Objetivo | Rol | Resultado |
|---|---|---|
| `GET /cuentas` (8 parámetros) | técnico | ningún parámetro inyectable |
| `/colaboradores/<id>` (ruta) | técnico | ningún parámetro inyectable |
| `GET /solicitudes?pagina` | RRHH | ningún parámetro inyectable |
| `/solicitudes/<id>` (ruta) | RRHH | ningún parámetro inyectable |
| `GET /auditoria?pagina` | Auditor | ningún parámetro inyectable |
| `POST /ingreso` | sin sesión | ningún parámetro inyectable |
| `POST /solicitudes/nueva/RET` | RRHH | ningún parámetro inyectable |

- 7 de 7 objetivos sin hallazgos y **cero cortes de conexión** (la corrida anterior, con `--max-requests`, tuvo 26).
- **Límite de esta corrida.** No tiene control positivo (plan de auditoría, §10): no se demostró que sqlmap detecte una inyección sembrada ni que los POST llegaran a la lógica de las vistas. Hasta entonces es evidencia preliminar de CA-12. [PENDIENTE: auditoría F6-04, con control positivo, nivel 5 y `Host`]

**Corregido por estas pruebas.** gunicorn reiniciaba su único proceso cada ~2000 peticiones (`--max-requests`): la aplicación quedaba unos segundos sin servicio («Broken pipe») y se perdían los desafíos TOTP en curso (S-29). Se quitó; commit `64b4847`.

## 3. Análisis estático y de dependencias (en cada push, job `seguridad`)

| Herramienta | Resultado |
|---|---|
| gitleaks, sobre todo el historial | 0 secretos |
| pip-audit, sobre las dependencias de la imagen | 0 vulnerabilidades |
| bandit | 0 hallazgos |
| Trivy, en la imagen de la aplicación antes de publicarla | 0 altas o críticas con corrección |

## 4. Pendiente para CA-12

- **El asesor de seguridad de Supabase (RS-16).** Lo corre el equipo desde el Dashboard.
- **Repetir estas pruebas contra Azure** (5.2) con el mismo script, sacando del baneo la IP del escáner.
