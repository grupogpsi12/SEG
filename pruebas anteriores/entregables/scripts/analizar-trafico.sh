#!/bin/sh
# Analisis de las capturas del entregable 5.7 con tshark (corre dentro de nicolaka/netshoot):
#   docker run --rm -v "<evidencias/trafico>:/cap" -v "<scripts>:/s" nicolaka/netshoot sh /s/analizar-trafico.sh
# Escribe un .txt por capitulo en /cap/analisis. Los valores de secretos se enmascaran (sed).
set -u
O=/cap/analisis
mkdir -p "$O"
B=/cap/bunkerweb.pcap; P=/cap/postgres.pcap; G=/cap/glpi.pcap
OCULTAR='s/(App-Token|Session-Token|Authorization: user_token|Authorization|user_token)([:= ]+)[A-Za-z0-9+\/=_ -]{8,}/\1\2<oculto>/g; s/(sessionid|csrftoken|glpi_[0-9a-f]+)=[A-Za-z0-9%._-]{6,}/\1=<oculto>/g; s/csrfmiddlewaretoken=[A-Za-z0-9]+/csrfmiddlewaretoken=<oculto>/g'

for f in $B $P $G; do
  n=$(basename "$f" .pcap)
  tshark -r "$f" -q -z io,phs > "$O/$n-protocolos.txt" 2>&1
  tshark -r "$f" -q -z conv,tcp > "$O/$n-conversaciones.txt" 2>&1
  tshark -r "$f" -q -z endpoints,ip > "$O/$n-extremos.txt" 2>&1
done

# 1. Tramo externo (cliente -> BunkerWeb :8443): TLS
tshark -r $B -Y "tls.handshake.type==1" -T fields -e frame.time_relative -e ip.src -e tls.handshake.extensions_server_name \
  -e tls.handshake.extensions.supported_version -e tls.handshake.extensions_alpn_str > "$O/tls-clienthello.txt" 2>&1
tshark -r $B -Y "tls.handshake.type==2" -T fields -e ip.src -e tls.handshake.extensions.supported_version \
  -e tls.handshake.ciphersuite | sort | uniq -c > "$O/tls-serverhello.txt" 2>&1
tshark -r $B -Y "tcp.port==8443 && tls.app_data" -T fields -e frame.number -e ip.src -e ip.dst -e tls.record.content_type \
  -e tls.app_data | cut -c1-140 | head -15 > "$O/tls-datos-cifrados.txt" 2>&1
tshark -r $B -Y "tcp.port==8080 && http" -T fields -e ip.src -e http.request.method -e http.request.uri -e http.response.code \
  -e http.location > "$O/http-80-redireccion.txt" 2>&1

# 2. Tramo interno BunkerWeb -> web:8000 y -> glpi:80 (HTTP en claro dentro de la red app)
tshark -r $B -Y "tcp.dstport==8000 && http.request" -T fields -e frame.time_relative -e http.request.method -e http.request.uri \
  -e http.x_forwarded_for -e http.content_type > "$O/interno-web-peticiones.txt" 2>&1
tshark -r $B -Y "tcp.srcport==8000 && http.response" -T fields -e frame.time_relative -e http.response.code -e http.location \
  -e http.content_type > "$O/interno-web-respuestas.txt" 2>&1
tshark -r $B -Y "tcp.srcport==8000 && http.response" -T fields -e http.response.code -e http.set_cookie -e http.response.line \
  | sed -E "$OCULTAR" | grep -iE "set-cookie|content-security|x-frame|cache-control" | sort | uniq -c | sort -rn | head -20 > "$O/interno-web-cabeceras.txt" 2>&1
tshark -r $B -Y "tcp.dstport==8000 && http.request.method==POST" -T fields -e http.request.uri -e http.file_data \
  | sed -E "$OCULTAR" | cut -c1-400 > "$O/interno-web-formularios.txt" 2>&1
tshark -r $B -Y "tcp.dstport==80 && http.request" -T fields -e ip.dst -e http.host -e http.request.method -e http.request.uri \
  > "$O/interno-glpi-peticiones.txt" 2>&1
tshark -r $B -Y "http.response.code==403 || http.response.code==429" -T fields -e frame.time_relative -e ip.src -e ip.dst -e http.response.code \
  | sort -k4 | awk '{print $2" -> "$3" "$4}' | sort | uniq -c > "$O/bloqueos-waf.txt" 2>&1

# 3. Base de datos de la aplicacion (web y worker -> postgres:5432)
tshark -r $P -Y "pgsql.type == \"Startup message\"" -T fields -e ip.src -e pgsql.parameter_name -e pgsql.parameter_value \
  | sort | uniq -c > "$O/pg-inicio.txt" 2>&1
tshark -r $P -Y "pgsql.authtype" -T fields -e ip.dst -e pgsql.authtype | sort | uniq -c > "$O/pg-autenticacion.txt" 2>&1
tshark -r $P -Y "pgsql.query" -T fields -e ip.src -e pgsql.query | cut -c1-220 | sort | uniq -c | sort -rn | head -40 > "$O/pg-consultas.txt" 2>&1
tshark -r $P -Y "ssl || tls" -T fields -e frame.number | wc -l > "$O/pg-tls-tramas.txt" 2>&1
tshark -r $P -Y 'frame contains "CENTINELA"' -T fields -e frame.number -e ip.src -e ip.dst -e pgsql.type > "$O/pg-centinela.txt" 2>&1

# 4. Worker -> API de GLPI (http://glpi/apirest.php) y GLPI -> MariaDB
tshark -r $G -Y "tcp.dstport==80 && http.request" -T fields -e ip.src -e http.request.method -e http.request.uri \
  | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -40 > "$O/glpi-api-peticiones.txt" 2>&1
tshark -r $G -Y "tcp.dstport==80 && http.request && !(ip.src==127.0.0.1)" -T fields -e http.request.line | tr "," "\n" \
  | sed -E 's/\\r\\n//; s/(-Token: |user_token )[A-Za-z0-9]+/\1<oculto>/' | grep -iE "token|authorization" \
  | sort | uniq -c > "$O/glpi-api-credenciales-en-claro.txt" 2>&1
tshark -r $G -Y "mysql.query" -T fields -e ip.src -e mysql.query | cut -c1-200 | sed -E 's/[0-9]{2,}/N/g' | sort | uniq -c | sort -rn | head -30 > "$O/mariadb-consultas.txt" 2>&1
tshark -r $G -Y "mysql.login_request" -T fields -e ip.src -e mysql.user -e mysql.caps.cs -e mysql.caps.ssl > "$O/mariadb-inicio.txt" 2>&1
tshark -r $G -Y 'frame contains "CENTINELA"' -T fields -e frame.number | wc -l > "$O/glpi-centinela.txt" 2>&1
tshark -r $B -Y 'frame contains "CENTINELA"' -T fields -e frame.number -e ip.src -e ip.dst -e tcp.dstport > "$O/borde-centinela.txt" 2>&1
echo listo
