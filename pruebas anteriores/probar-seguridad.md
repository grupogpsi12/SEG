# Pruebas de seguridad manuales con otras herramientas

Guía de laboratorio complementaria a los informes de la entrega 3 (`docs/entregables/`). Cubre tres
herramientas más: **bandit** (análisis estático del código), **Wireshark** (inspección del tráfico
ya capturado) y la **verificación del control anti-DoS** (límite de peticiones y baneo del WAF).

> Es tu propio sistema, en local, con el stack de Docker arriba (`docs/probar-localmente.md`).
> Pruebas autorizadas de laboratorio. No apuntes nada de esto a un sistema que no sea tuyo.

## 1. Bandit — análisis estático del código (SAST)

Bandit **lee** el código Python y busca patrones inseguros (SQL con f-strings, `shell=True`,
deserialización peligrosa, secretos embebidos). No ataca nada; es la cara de «caja blanca» que
complementa a ZAP y sqlmap (caja negra). Ya corre en la CI (`.github/workflows/verificar.yml`, job
`seguridad`). A mano, igual que la CI:

```bash
uvx bandit==1.9.4 -r src -x '*/migrations/*'
```

**Resultado esperado** (verificado el 24/10/2026):

```
Test results:  No issues identified.
Total lines of code: 8509
Total issues (by severity): Low 0, Medium 0, High 0
```

Hay 3 avisos deshabilitados con `#nosec` y su motivo (p. ej. `B108` en `settings.py`): son usos
revisados, no hallazgos. Si bandit marcara algo nuevo con severidad media o alta, la CI debe
fallar.

Para un reporte con formato (útil como evidencia del laboratorio):

```bash
uvx bandit==1.9.4 -r src -x '*/migrations/*' -f html -o docs/entregables/evidencias/vulnerabilidades/bandit.html
```

## 2. Wireshark — inspección del tráfico capturado

Wireshark es la versión gráfica del análisis que en el Documento 3 se hizo con `tshark`. No necesitas
capturar de nuevo: abre los `.pcap` que ya están en
`docs/entregables/evidencias/trafico/` y explóralos con filtros de visualización. Es observación
**pasiva** de tu propio tráfico.

| Qué observar | Filtro de visualización | Archivo |
|---|---|---|
| TLS externo (tráfico cifrado) | `tcp.port==8443 && tls` | `bunkerweb.pcap` |
| HTTP interno WAF→Django (en claro) | `tcp.port==8000 && http` | `bunkerweb.pcap` |
| Campo restringido en tránsito | `frame contains "CENTINELA"` | `postgres.pcap` (aparece) / `glpi.pcap` (**vacío**) |
| Consultas a PostgreSQL | `pgsql.query` | `postgres.pcap` |
| Llamadas a la API de GLPI | `http.request.uri contains "apirest"` | `glpi.pcap` |
| Credenciales de GLPI en el tramo interno | `http.request.line contains "Token"` | `glpi.pcap` |

**Experimentos recomendados para el informe:**

1. **Confidencialidad externa.** En `bunkerweb.pcap`, clic derecho en un paquete TLS →
   *Follow → TLS Stream*: el contenido es ilegible (cifrado). Confirma que lo que sale del host va
   protegido (RS-01).
2. **El campo restringido nunca llega a GLPI.** Abre `glpi.pcap`, aplica
   `frame contains "CENTINELA"` → **cero paquetes**. Luego el mismo filtro en `postgres.pcap` sí los
   muestra: el motivo del retiro vive solo en PostgreSQL (invariante 5, T7).
3. **Consultas parametrizadas.** En `postgres.pcap`, filtra `pgsql.query` y revisa que las sentencias
   usan identificadores entre comillas, no concatenación de input (defensa contra T4).

Si quisieras capturar en vivo (equivale a lo que hice con `tcpdump`), hazlo contra tu propio stack;
Wireshark en Windows no ve dentro de las redes de Docker, así que lo práctico es capturar con
`tcpdump` adosado al contenedor y abrir el `.pcap` resultante en Wireshark:

```bash
docker run --rm --name cap --net container:jml-bunkerweb-1 \
  --cap-add NET_RAW --cap-add NET_ADMIN -v "$PWD/captura:/cap" \
  nicolaka/netshoot tcpdump -i any -s 0 -w /cap/vivo.pcap
# (haz tus acciones en la app; Ctrl-C para parar; abre captura/vivo.pcap en Wireshark)
```

## 3. Verificación del control anti-DoS (límite de peticiones y baneo)

Importante entender el encuadre: un pentest de este sistema **no** busca tumbar el servicio, sino
**comprobar que las protecciones de disponibilidad funcionan**. El sistema las tiene explícitas
(RS-08; amenazas T13 «solicitudes masivas» y T21; criterio CA-14 «el sexto intento en un minuto se
bloquea»):

| Control (en `infra/compose.yaml`) | Valor |
|---|---|
| Límite general por IP | `LIMIT_REQ_RATE=2r/s` |
| Límite en `/ingreso` y TOTP | `5r/m` (`LIMIT_REQ_RATE_1`) |
| Baneo por mal comportamiento | `USE_BAD_BEHAVIOR`, `BAN_TIME=3600` (1 h) |

### Prueba acotada (confirma el control, no causa caída)

Una ráfaga **pequeña y controlada** contra `/ingreso` basta para ver el `429` y el baneo. No es un
flood: son una docena de peticiones para disparar un umbral de 5/min.

```bash
# ~12 peticiones rápidas a /ingreso -> deben empezar a salir 429 (límite 5/min)
for i in $(seq 1 12); do
  curl -sk -o /dev/null -w "%{http_code} " --resolve app.localhost:443:127.0.0.1 \
    https://app.localhost/ingreso
done; echo

# ver el baneo que se activó
docker compose -f infra/compose.yaml exec bw-scheduler bwcli bans

# levantarlo al terminar (desde el host, el WAF te ve como 10.20.40.1)
docker compose -f infra/compose.yaml exec bw-scheduler bwcli unban 10.20.40.1
```

**Esperado:** una mezcla de `200`/`302` y luego `429 Too Many Requests`, y tu IP (`10.20.40.1`)
aparece en `bwcli bans` con motivo *bad behavior*. Que el baneo ocurra **es** la evidencia de que el
control funciona (lección 58). Tu `infra/waf/pruebas.sh` ya ejercita esta superficie de forma
ordenada, con 1 s de pausa entre peticiones para no confundir el `429` del límite con el `403` del
CRS (lección 43).

### Dónde está la frontera

- **Sí (defensivo):** la ráfaga acotada de arriba, que demuestra el límite de peticiones y el baneo;
  medir cuántas peticiones legítimas pasan antes del `429`; comprobar que `bwcli unban` restablece.
- **No:** un ataque volumétrico real (flooding, agotamiento de conexiones, amplificación) cuyo
  objetivo sea dejar el servicio caído. Aun contra tu propia máquina, no aporta evidencia defensiva
  que la prueba acotada no dé ya, y el objetivo del laboratorio —probar que el *rate limiting* y el
  baneo responden— se cumple sin provocar la caída. Esa es la diferencia entre «verificar el control
  de disponibilidad» y «ejecutar un DoS».

## 4. OWASP ZAP en modo activo

El escaneo *baseline* del Documento 2 es **pasivo**: araña el sitio y analiza las respuestas sin
enviar cargas de ataque. El escaneo **activo** (`zap-full-scan.py`) sí inyecta payloads reales
(SQLi, XSS, inyección de comandos, recorrido de rutas, etc.) contra cada parámetro. Es más agresivo
y más lento, y por eso conviene correrlo **contra Django directamente** (en la red interna), no a
través del WAF: así mides el código, no el borde. Atravesar el WAF con un escaneo activo solo
consigue que BunkerWeb te banee a los pocos segundos (lo que ya quedó demostrado en el Documento 2).

Primero crea una sesión de prueba (igual que para los casos de uso) y guarda su cookie. Luego:

```bash
# K = cookie de sesión de un rol (p. ej. rrhh); V = carpeta de evidencias
AUTH="-config replacer.full_list(0).description=auth \
-config replacer.full_list(0).enabled=true \
-config replacer.full_list(0).matchtype=REQ_HEADER \
-config replacer.full_list(0).matchstr=Cookie \
-config replacer.full_list(0).regex=false \
-config replacer.full_list(0).replacement=sessionid=$K"

docker run --rm -u root -v "$V:/zap/wrk" --network jml_app --add-host app.localhost:10.20.40.3 \
  zaproxy/zap-stable zap-full-scan.py -t http://app.localhost:8000/ \
  -m 5 -I -j -r zap-activo-sin-waf.html -J zap-activo-sin-waf.json -z "$AUTH"
```

- `-m 5`: minutos máximos de araña (acota la corrida). `-I`: no falla el proceso por avisos.
  `-j`: usa la araña AJAX además de la tradicional. `-z`: inyecta la cookie de sesión en cada
  petición (escaneo autenticado).
- **Resultado** (verificado el 24/10/2026): **0 FAIL, 110 reglas PASS**. Las reglas de inyección
  activa pasaron todas —SQLi, *Remote OS Command Injection (Time Based)*, *Server Side Template
  Injection (Blind)*, recorrido de rutas, *Padding Oracle*, etc.—: con payloads reales y desde fuera,
  el código no es inyectable. Confirma lo que bandit ve por dentro y sqlmap en el parámetro concreto.
- Los 3 WARN son los mismos de bajo riesgo y explicables al probar **contra Django sin el WAF**:
  `X-Content-Type-Options` ausente (lo añade BunkerWeb en el borde, RS-07), `ACAO:*` en el CSS
  estático, y «HTTP Only Site» (porque se probó por HTTP directo; en producción todo es HTTPS). Los
  tres los resuelve el borde y no aparecen a través del WAF.
- El reporte `zap-activo-sin-waf.html` / `.json` es la evidencia para el laboratorio.

**Cuidado:** el escaneo activo **modifica estado** (envía POSTs con payloads). Córrelo contra el
stack local desechable, nunca contra Supabase ni contra datos que te importe conservar. Tras la
corrida, puedes recrear los datos con `migrar` + `semillas`.

## 5. Endurecimiento de contenedores y host (Docker Bench, Lynis)

### Docker Bench for Security (CIS Docker Benchmark)

Audita el *daemon* y los contenedores contra el CIS Docker Benchmark. Da evidencia directa de RS-14
(contenedores sin privilegios, sistema de archivos de solo lectura, imágenes por digest, límites).

```bash
docker run --rm --net host --pid host \
  -v /var/run/docker.sock:/var/run/docker.sock:ro -v /etc:/etc:ro \
  docker/docker-bench-security
```

**Resultado esperado** (verificado el 24/10/2026; 105 chequeos). Lo relevante del stack:

| Chequeo | Resultado | Lectura |
|---|---|---|
| 5.3 Capacidades restringidas | PASS | `cap_drop: ALL` en el compose |
| 5.4 Sin contenedores privilegiados | PASS | Ninguno es `--privileged` |
| 5.5 Sin directorios sensibles del host montados | PASS | — |
| 5.6 Sin SSH dentro de contenedores | PASS | — |
| 5.15–5.31 Namespaces, seccomp, socket | PASS | Aislamiento del host correcto; socket no montado |
| 5.1 AppArmor | WARN | Limitación de Docker Desktop; en la VM de Azure (Linux) debe activarse |
| 5.11 Límite de CPU | WARN | Hay `mem_limit`, falta `cpus`; agregarlo endurece T13 |
| Running as root (postgres, mariadb) | WARN | Sus imágenes oficiales arrancan como root para el `chown` del volumen y bajan de usuario; aceptable |
| 5.12 rootfs de solo lectura | WARN (parcial) | `web` y `worker` tienen `read_only: true`; las bases y la reportería no pueden |

Guarda la salida completa como evidencia:

```bash
docker run --rm --net host --pid host \
  -v /var/run/docker.sock:/var/run/docker.sock:ro -v /etc:/etc:ro \
  docker/docker-bench-security > docs/entregables/evidencias/vulnerabilidades/docker-bench-completo.txt
```

### Lynis (endurecimiento del host)

Lynis audita un host **Linux** (servicios, permisos, kernel, firewall). En tu equipo de desarrollo
Windows no aplica; su lugar es la **VM de Azure** cuando se despliegue (fase 5.2). Allí:

```bash
# en la VM Linux de Azure, no en el equipo Windows
sudo apt-get install -y lynis && sudo lynis audit system
```

Interesa el *hardening index* y las sugerencias de SSH, firewall (UFW/NSG) y actualizaciones. Para el
laboratorio local basta con dejarlo documentado como paso de la fase de despliegue; el endurecimiento
de los contenedores ya lo cubre Docker Bench.

## 6. Resumen

| Herramienta | Tipo | Qué demuestra | Requisito |
|---|---|---|---|
| bandit | Estático (caja blanca) | El código no tiene patrones inseguros | RS-11, RS-05 |
| Wireshark | Observación de tráfico | TLS externo; campo restringido no llega a GLPI; consultas parametrizadas | RS-01, T7, T4 |
| Ráfaga acotada al WAF | Verificación de control | El límite de peticiones y el baneo responden | RS-08, T13/T21, CA-14 |
| ZAP activo (sin WAF) | Dinámico con payloads | El código no es inyectable ni vulnerable a XSS, desde fuera | RS-13, T4 |
| Docker Bench | Config de contenedores | Aislamiento, sin privilegios, solo lectura, límites | RS-14 |
| Lynis (en Azure) | Config del host | Endurecimiento del SO de la VM | Fase 5.2 |

Todas son complementarias a los escáneres del Documento 2 (ZAP baseline, sqlmap, nmap, testssl,
Nikto, Trivy) y al análisis de tráfico del Documento 3.
