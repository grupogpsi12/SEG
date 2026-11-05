#!/usr/bin/env bash
# Entregable «Analisis de captura de trafico»: captura el trafico de CADA caso de uso por separado, en tres puntos del stack
# LOCAL (bunkerweb, postgres y glpi), y lo analiza con tshark. Los .pcap NO se versionan (llevan tokens y valores centinela).
#
#   JML_GLPI_DE_PRUEBAS=si auditoria/scripts/captura-por-caso-de-uso.sh
#
# CU-01 a CU-04: el recorrido de Playwright por el WAF (ING, VAC, RET, EMG), una prueba por captura.
# CU-05 y CU-06: lecturas con la sesion de un tecnico y de un auditor (dashboard, cuentas, ficha; auditoria y su verificacion).
# Neutraliza antes (copia de la base, baneos levantados) y restaura despues.
set -u
export MSYS_NO_PATHCONV=1
if [ "${JML_GLPI_DE_PRUEBAS:-}" != "si" ]; then echo "Crea datos y tickets de prueba: JML_GLPI_DE_PRUEBAS=si $0" >&2; exit 2; fi
RAIZ="$(pwd -W 2>/dev/null || pwd)"
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
C="-f infra/compose.yaml -f infra/compose.local.yaml"
S="$RAIZ/auditoria/.captura-local"
rm -rf "$S" && mkdir -p "$S" && chmod 777 "$S"

purgar() { docker exec -i jml-worker-1 python - 22 < auditoria/scripts/limpiar-tickets-de-prueba.py 2>&1 | tail -1; }

bash auditoria/scripts/neutralizar.sh pre
docker start jml-worker-1 > /dev/null
# B-37: tras restaurar la base los consecutivos SOL-2026-nnnnnn se repiten y GLPI conserva los tickets de la corrida anterior:
# una prueba que espera «los tickets de la solicitud X» los encontraria viejos y pasaria sin que se cree ninguno.
echo "limpieza previa de GLPI: $(purgar)"

iniciar() {  # caso
  mkdir -p "$S/$1" && chmod 777 "$S/$1"
  docker rm -f jml-cap-bw jml-cap-pg jml-cap-glpi > /dev/null 2>&1
  docker run -d --name jml-cap-bw --net container:jml-bunkerweb-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$S/$1:/cap" "$NET" \
    tcpdump -i any -s 0 -U -w /cap/bunkerweb.pcap "port 8443 or port 8080 or port 8000" > /dev/null
  docker run -d --name jml-cap-pg --net container:jml-postgres-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$S/$1:/cap" "$NET" \
    tcpdump -i any -s 0 -U -w /cap/postgres.pcap "port 5432" > /dev/null
  docker run -d --name jml-cap-glpi --net container:jml-glpi-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$S/$1:/cap" "$NET" \
    tcpdump -i any -s 0 -U -w /cap/glpi.pcap "port 80 or port 3306" > /dev/null
  sleep 3
}
detener() {  # [segundos de espera antes de cortar]
  sleep "${1:-3}"
  docker stop jml-cap-bw jml-cap-pg jml-cap-glpi > /dev/null 2>&1
  docker rm jml-cap-bw jml-cap-pg jml-cap-glpi > /dev/null 2>&1
}
an() { local caso="$1" f="$2"; shift 2; docker run --rm -v "$S/$caso:/cap" "$NET" tshark -r "/cap/$f" "$@" 2> /dev/null; }

analizar() {  # caso
  local c="$1" CEN='frame contains "CENTINELA-"'
  echo "--- resultado del caso $c"
  echo "tramas: bunkerweb $(an "$c" bunkerweb.pcap | wc -l) · postgres $(an "$c" postgres.pcap | wc -l) · glpi $(an "$c" glpi.pcap | wc -l)"
  echo "TLS: saludos del cliente con TLS 1.3: $(an "$c" bunkerweb.pcap -Y 'tls.handshake.type==1 && tls.handshake.extensions.supported_version==0x0304' | wc -l) · suites elegidas: $(an "$c" bunkerweb.pcap -Y 'tls.handshake.type==2' -T fields -e tls.handshake.ciphersuite | sort | uniq -c | tr '\n' ';')"
  echo "peticiones del WAF a la aplicacion (metodo ruta, sin parametros):"
  an "$c" bunkerweb.pcap -Y 'tcp.dstport==8000 && http.request' -T fields -e http.request.method -e http.request.uri \
    | sed -E 's/\?.*//; s/SOL-[0-9]{4}-[0-9]{6}/SOL-<id>/; s#/colaboradores/[A-Za-z0-9-]+#/colaboradores/<id>#' | sort | uniq -c | sort -rn | sed 's/^/   /'
  echo "respuestas de la aplicacion por codigo: $(an "$c" bunkerweb.pcap -Y 'tcp.srcport==8000 && http.response' -T fields -e http.response.code | sort | uniq -c | tr '\n' ';')"
  echo "centinela: tramo externo cifrado $(an "$c" bunkerweb.pcap -Y "tcp.port==8443 && $CEN" | wc -l) · WAF a aplicacion $(an "$c" bunkerweb.pcap -Y "tcp.dstport==8000 && $CEN" | wc -l) · base de datos $(an "$c" postgres.pcap -Y "$CEN" | wc -l) · hacia GLPI $(an "$c" glpi.pcap -Y "http.request and $CEN" | wc -l)"
  echo "base de datos: BEGIN $(an "$c" postgres.pcap -Y 'pgsql.query contains "BEGIN"' | wc -l) · COMMIT $(an "$c" postgres.pcap -Y 'pgsql.query contains "COMMIT"' | wc -l) · contrasena en claro $(an "$c" postgres.pcap -Y 'pgsql.authtype == 3' | wc -l)"
  echo "tickets creados por el worker en GLPI (POST /apirest.php/Ticket): $(an "$c" glpi.pcap -Y 'http.request.method=="POST" and http.request.uri matches "/apirest.php/Ticket/?($|[?])"' | wc -l) · documentos subidos (POST /apirest.php/Document): $(an "$c" glpi.pcap -Y 'http.request.method=="POST" and http.request.uri matches "/apirest.php/Document/?($|[?])"' | wc -l)"
  echo "escrituras del worker hacia GLPI (metodo ruta, agrupadas):"
  an "$c" glpi.pcap -Y 'http.request and (http.request.method=="POST" or http.request.method=="PUT")' -T fields -e http.request.method -e http.request.uri \
    | sed -E 's/\?.*//; s#/[0-9]+#/<id>#g' | sort | uniq -c | sort -rn | sed 's/^/   /'
  echo "consultas del worker a GLPI (cantidad de peticiones GET): $(an "$c" glpi.pcap -Y 'http.request.method=="GET"' | wc -l)"
  echo "tokens de GLPI en claro (B-32): App-Token $(an "$c" glpi.pcap -Y 'http.request and http contains "App-Token"' | wc -l) · Session-Token $(an "$c" glpi.pcap -Y 'http.request and http contains "Session-Token"' | wc -l)"
  echo "autenticacion hacia PostgreSQL: SASL/SCRAM $(an "$c" postgres.pcap -Y 'pgsql.authtype == 10' | wc -l)"
  echo "GLPI a MariaDB: tramas $(an "$c" glpi.pcap -Y 'tcp.port == 3306' | wc -l) · con TLS $(an "$c" glpi.pcap -Y 'tcp.port == 3306 and tls' | wc -l)"
}

rm_baneos() { bash auditoria/scripts/neutralizar.sh unban > /dev/null 2>&1; sleep 2; }
# JML_CASOS="CU-06" repite solo esos casos (p. ej., tras corregir uno); vacio = todos.
quiere() { [ -z "${JML_CASOS:-}" ] || [[ " $JML_CASOS " == *" $1 "* ]]; }

echo "################ CU-01 a CU-04: recorrido por el navegador, una prueba por captura"
for par in "CU-01-ingreso:test_ING" "CU-02-vacaciones:test_VAC" "CU-03-retiro:test_RET" "CU-04-emergencia:test_EMG"; do
  caso="${par%%:*}"; filtro="${par##*:}"
  quiere "${caso:0:5}" || continue
  echo "=============== $caso"
  rm_baneos
  iniciar "$caso"
  resultado=$(env -u MSYS_NO_PATHCONV bash infra/scripts/e2e-interfaz.sh -k "$filtro" 2>&1 | tail -3 | tr '\n' ' ')
  detener 35  # un ciclo completo de la bandeja de salida (30 s), para que entren todos los tickets del caso
  echo "prueba de navegador: $resultado"
  analizar "$caso"
done

echo "################ CU-05 y CU-06: lecturas con la sesion de un tecnico y de un auditor"
docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2> /dev/null | tail -1 > "$S/sesiones.json"
clave() { sed -E "s/.*\"$1\": \"([^\"]+)\".*/\1/" "$S/sesiones.json"; }
TEC="$(clave tecnico)"; AUD="$(clave auditor)"
COL="$(sed -E 's/.*"colaborador": "([^"]+)".*/\1/' "$S/sesiones.json")"
WAF="--resolve app.localhost:8443:10.20.40.2"

leer() {  # etiqueta cookie ruta
  docker run --rm --network jml_app "$NET" sh -c "sleep 1.2; curl -sk $WAF -o /dev/null -w '$1 -> %{http_code}\n' -H 'Cookie: sessionid=$2' https://app.localhost:8443$3"
}
if quiere CU-05; then
echo "=============== CU-05-consulta-tecnica"
rm_baneos
iniciar CU-05-consulta-tecnica
leer "GET /dashboard" "$TEC" /dashboard
leer "GET /cuentas" "$TEC" "/cuentas?departamento=Finanzas"
leer "GET /colaboradores/<id>" "$TEC" "/colaboradores/$COL"
detener
analizar CU-05-consulta-tecnica
fi

if quiere CU-06; then
echo "=============== CU-06-auditoria"
rm_baneos
iniciar CU-06-auditoria
leer "GET /auditoria" "$AUD" /auditoria
docker run --rm --network jml_app "$NET" sh -c "
  sleep 1.2
  curl -sk $WAF -D /tmp/h -b 'sessionid=$AUD' https://app.localhost:8443/auditoria -o /tmp/p
  CS=\$(grep -i 'set-cookie: csrftoken' /tmp/h | sed 's/.*csrftoken=\\([^;]*\\).*/\\1/' | tr -d '\\r')
  T=\$(grep -o 'name=\"csrfmiddlewaretoken\" value=\"[^\"]*' /tmp/p | head -1 | sed 's/.*value=\"//')
  sleep 1.2
  curl -sk $WAF -o /tmp/r -w 'POST /auditoria (verificar la cadena) -> %{http_code}\\n' \
    -H \"Cookie: sessionid=$AUD; csrftoken=\$CS\" -H 'Referer: https://app.localhost/' \
    --data-urlencode \"csrfmiddlewaretoken=\$T\" https://app.localhost:8443/auditoria
  printf 'la respuesta confirma que la cadena esta integra: %s\\n' \$(grep -ci 'ntegra' /tmp/r)"
detener
analizar CU-06-auditoria
fi

echo "################ restauracion"
bash auditoria/scripts/neutralizar.sh post
echo "limpieza final de GLPI: $(purgar)"
echo "FIN DE LA CAPTURA POR CASO DE USO"
