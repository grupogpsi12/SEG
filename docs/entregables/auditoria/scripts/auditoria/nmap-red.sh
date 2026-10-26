#!/usr/bin/env bash
# F7-01: `nmap -p-` de cada contenedor del stack LOCAL desde dentro de cada red interna, con la imagen
# fijada por digest (herramientas.lock). Solo escanea direcciones de contenedores de este proyecto.
#
#   auditoria/scripts/nmap-red.sh
#
# Salida: por red, cada «contenedor ip: puertos abiertos». Es la base de F7-01 (T19) y de F7-02 (N-2).
set -u
export MSYS_NO_PATHCONV=1
NMAP=instrumentisto/nmap@sha256:96f6ed194519b62421a1a1c57809e65a7f94d2aa1c8c25676f247e5e148c0827
for red in jml_app jml_bw-universe jml_db_net jml_pg_net jml_waf-logs; do
  [ -n "$(docker network ls -q --filter "name=^${red}$")" ] || continue
  echo "### red $red ($(docker network inspect "$red" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}') · interna=$(docker network inspect "$red" --format '{{.Internal}}'))"
  docker network inspect "$red" --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}' | sed '/^$/d' | while read -r nombre cidr; do
    ip="${cidr%/*}"
    abiertos=$(docker run --rm --network "$red" "$NMAP" -Pn -p- --min-rate 4000 -T4 --open -oG - "$ip" 2>/dev/null       | grep -E '^Host:.*Ports:' | sed -E 's/.*Ports: //' | tr ',' '
' | awk -F/ 'NF > 3 {gsub(/ /, "", $1); printf "%s/%s ", $1, $5}')
    echo "  $nombre $ip: ${abiertos:-ninguno}"
  done
done
