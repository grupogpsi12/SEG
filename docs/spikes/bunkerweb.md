# Spike 0.6 — BunkerWeb 1.6.15 con los dos sitios (11/10/2026)

Hecho en el equipo de desarrollo (Windows 11, Docker Desktop, 15 GB), con `infra/compose.yaml` + `infra/compose.local.yaml`. Imágenes por digest (RS-18). `SECURITY_MODE=block` en ambos sitios.

## Resultado

| Pregunta del spike | Resultado |
|---|---|
| ¿`pruebas.sh` en verde en `app.*` y `glpi.*`? | **Sí**, en los dos sitios: tráfico normal 200/302/301; los 7 ataques (SQL por GET y POST, XSS, recorrido de rutas, inyección de comandos, Log4Shell en cabecera y escáner `sqlmap`) reciben **403 del CRS** |
| ¿PDF de 20 MB a través de ModSecurity en bloqueo? | **Sí**: un PDF de exactamente 20 MB se acepta (HTTP 302, 0,8 s) por el flujo real de ingreso con sesión, TOTP y CSRF. Uno de 22 MB lo corta BunkerWeb con **413** en 0,1 s (`MAX_CLIENT_SIZE=21m`). Un ejecutable disfrazado de PDF **pasa el WAF sin falso positivo** y lo rechaza la aplicación por su contenido (RF-39) |
| ¿Hacen falta exclusiones del CRS? | **Ninguna hasta ahora**: ni el ingreso, ni el formulario de ingreso con adjunto de 20 MB, ni la pantalla de ingreso de GLPI dispararon falsos positivos |
| ¿RAM del stack? | Con el uso descrito: `bunkerweb` 290 MiB, `bw-scheduler` 164 MiB, `glpi` 72 MiB, `mariadb` 195 MiB, `web` 74 MiB (≈ 0,8 GB sin la base de la aplicación, que en producción es Supabase). Cabe de sobra en una B2s de 4 GB. **Sin medir:** la reportería (Fluent Bit, Loki, Grafana) |
| ¿Comando de desbloqueo? | `docker compose … exec bw-scheduler bwcli unban <ip>` ✔; `bwcli bans` lista los baneos |
| ¿Cabeceras con una sola fuente (RS-07)? | **Sí**: Django envía `Content-Security-Policy` y `X-Frame-Options: DENY`; BunkerWeb añade HSTS, `X-Content-Type-Options` y `Referrer-Policy`, y quita `Server`. La cookie sale `Secure; HttpOnly; SameSite=Lax` |
| ¿Solo `bunkerweb` publica puertos (RS-02)? | **Sí**: 80 y 443; los puertos 8000, 3306 y 5000 están cerrados desde fuera |
| ¿API interna con `API_TOKEN` (RS-19)? | **Sí**: sin token o con uno malo, BunkerWeb **cierra la conexión** (no devuelve 401); con el token correcto y `Host: bwapi` responde 200 |

## Hallazgos que cambiaron el repositorio

1. **No se puede montar `/data/configs` de solo lectura.** El scheduler crea sus propias subcarpetas ahí y se reiniciaba en bucle. Ahora solo `modsec-crs/` y `modsec/` van de solo lectura (`infra/compose.yaml`).
2. **Dos límites distintos se parecen en el resultado.** El límite de 2 peticiones por segundo (RS-08) responde **429**, y el CRS responde **403**. `pruebas.sh` esperaba 403 pero disparaba los ataques sin pausa, así que cuatro de siete daban 429 y la prueba no demostraba que el CRS los detectara. Ahora espera 1 s entre peticiones.
3. **El baneo es por sitio, no global.** Tras los ataques de la prueba, `app.localhost` queda baneado una hora para la IP del cliente, mientras que `glpi.localhost` no. Desde Docker Desktop el cliente se ve como la puerta de enlace de la red (`10.20.40.1`), no como `127.0.0.1`.
4. **Una petición `HEAD` a una ruta que solo acepta GET/POST** devuelve la página de error de BunkerWeb, con **su** CSP (`default-src 'none'`, con nonces), no la de Django. No es un defecto, pero engaña al revisar cabeceras con `curl -I`; usar `curl -D - -o /dev/null`.
5. **La API interna exige el `Host: bwapi`** además del token, y rechaza cerrando la conexión. `pruebas.sh` lo comprueba ahora de verdad (sin token, token malo y token correcto).
6. **El empaquetado de la imagen no incluía plantillas ni estáticos** (no es de BunkerWeb, pero lo reveló este spike): `/ingreso` daba 500. Corregido en `pyproject.toml` con una prueba (lección 42).

## Pendiente de este spike

- Recorrer GLPI creando un ticket con texto enriquecido y adjunto en modo `detect`, y registrar las reglas del CRS que salten (hace falta GLPI configurado: items 0.3 y 3.1).
- Medir la RAM con la reportería (ítem 5.5).
- Repetir `pruebas.sh` en la VM de Azure con Let's Encrypt real.
