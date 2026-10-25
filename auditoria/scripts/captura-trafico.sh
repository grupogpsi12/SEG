#!/usr/bin/env bash
# F7-04 / F7-09: captura del tráfico que ve GLPI mientras corren los flujos reales de RET y EMG (con el centinela
# del campo restringido) y análisis con aserciones. Stack LOCAL.
#
#   JML_GLPI_DE_PRUEBAS=si auditoria/scripts/captura-trafico.sh
#
# Se captura en el espacio de red del contenedor de GLPI (worker→GLPI por HTTP en `app`, GLPI→MariaDB en `db_net`).
# Aserciones: (T7) 0 tramas con el centinela; (N-1) cuántas cabeceras App-Token/Session-Token viajan en claro;
# (V-04) si el tramo GLPI↔MariaDB usa TLS. El .pcap queda en el repositorio SOLO si no contiene el centinela.
set -u
export MSYS_NO_PATHCONV=1
if [ "${JML_GLPI_DE_PRUEBAS:-}" != "si" ]; then echo "Crea y borra tickets de prueba: JML_GLPI_DE_PRUEBAS=si $0" >&2; exit 2; fi
RAIZ="$(pwd -W 2>/dev/null || pwd)"
NET=nicolaka/netshoot@sha256:b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70
SALIDA="$RAIZ/auditoria/.captura-local"  # fuera de .contrato-tmp: contrato-glpi.sh lo borra al terminar; y NO se versiona (lleva tokens)
rm -rf "$SALIDA" && mkdir -p "$SALIDA" && chmod 777 "$SALIDA"
SENTINELA="SENTINELA-RESTRINGIDA-9f3a"

docker rm -f jml-captura > /dev/null 2>&1
docker run -d --name jml-captura --net container:jml-glpi-1 --cap-add NET_RAW --cap-add NET_ADMIN -v "$SALIDA:/cap" "$NET" \
  tcpdump -i any -s 0 -U -w /cap/glpi.pcap "port 80 or port 3306" > /dev/null || exit 2
sleep 3
echo "== flujos reales de RET y EMG contra GLPI 11 (con el centinela en el campo restringido)"
# sin MSYS_NO_PATHCONV: `uv export` (nativo de Windows) necesita la ruta traducida; el propio guion la fija despues
env -u MSYS_NO_PATHCONV bash infra/scripts/contrato-glpi.sh -k "RET_real or CA_06_EMG" 2>&1 | tail -4
sleep 3
docker stop jml-captura > /dev/null; docker rm jml-captura > /dev/null

an() { docker run --rm -v "$SALIDA:/cap" "$NET" tshark -r /cap/glpi.pcap "$@" 2>/dev/null; }
echo "== análisis"
echo "tramas capturadas: $(an | wc -l)"
echo "peticiones HTTP hacia GLPI (método y ruta): $(an -Y 'http.request' -T fields -e http.request.method -e http.request.uri | sed -E 's/\?.*//' | sort | uniq -c | sort -rn | head -6 | tr '\n' ';')"
echo "T7  tramas con el centinela «$SENTINELA» (esperado 0): $(an -Y "frame contains \"$SENTINELA\"" | wc -l)"
echo "N-1 peticiones con App-Token en claro: $(an -Y 'http.request and http contains "App-Token"' | wc -l)"
echo "N-1 peticiones con Session-Token en claro: $(an -Y 'http.request and http contains "Session-Token"' | wc -l)"
echo "N-1 peticiones con el user_token en la cabecera Authorization: $(an -Y 'http.request and http contains "user_token"' | wc -l)"
echo "V-04 tramas GLPI↔MariaDB (puerto 3306): $(an -Y 'tcp.port == 3306' | wc -l) · con TLS: $(an -Y 'tcp.port == 3306 and tls' | wc -l)"
echo "V-04 consultas SQL legibles en claro (protocolo mysql): $(an -Y 'mysql.command == 3' | wc -l)"
con_centinela=$(an -Y "frame contains \"$SENTINELA\"" | wc -l)
true
[ "$con_centinela" -eq 0 ] && echo "ASERCION T7 CUMPLIDA: 0 tramas con el centinela" || { echo "ASERCION T7 FALLA"; exit 1; }
