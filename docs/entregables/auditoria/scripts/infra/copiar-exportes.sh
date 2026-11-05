#!/usr/bin/env bash
# RD-04 (ADR-031): copia la auditoria diaria y su ancla del volumen `exportes` a un medio externo
# al equipo (disco externo), sin sobrescribir nunca un archivo ya copiado, y verifica cada copia
# por SHA-256. Se programa una vez al dia en el host (Programador de tareas de Windows o cron).
#
#   JML_MEDIO_EXTERNO=/e/jml infra/scripts/copiar-exportes.sh
#
# La retencion es de 365 dias: este script no borra nada del medio externo; un archivo que ya
# existe con otro contenido es una alarma (alguien reescribio la exportacion), no una copia.
set -euo pipefail
export MSYS_NO_PATHCONV=1

DESTINO="${JML_MEDIO_EXTERNO:?defina JML_MEDIO_EXTERNO (carpeta del disco externo)}/auditoria"
VOLUMEN="${JML_VOLUMEN_EXPORTES:-jml_exportes}"
mkdir -p "$DESTINO"
DESTINO_ABS="$(cd "$DESTINO" && (pwd -W 2>/dev/null || pwd))"

# El volumen solo se lee desde un contenedor de un solo uso: en Docker Desktop no vive en el host.
# Imagen ya fijada por digest en el proyecto (RS-18): no se trae una nueva solo para copiar.
IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
docker run --rm --network none -v "$VOLUMEN:/origen:ro" -v "$DESTINO_ABS:/destino" "$IMAGEN" sh -eu -c '
  copiados=0; iguales=0; distintos=0
  for f in /origen/auditoria-*.jsonl /origen/ancla-*.json; do
    [ -e "$f" ] || continue
    n=$(basename "$f")
    if [ -e "/destino/$n" ]; then
      if [ "$(sha256sum < "$f")" = "$(sha256sum < "/destino/$n")" ]; then
        iguales=$((iguales + 1))
      else
        echo "ALARMA: /destino/$n existe con otro contenido; no se sobrescribe" >&2
        distintos=$((distintos + 1))
      fi
      continue
    fi
    cp "$f" "/destino/$n.tmp" && mv "/destino/$n.tmp" "/destino/$n"
    [ "$(sha256sum < "$f")" = "$(sha256sum < "/destino/$n")" ] || { echo "copia corrupta: $n" >&2; exit 1; }
    copiados=$((copiados + 1))
  done
  echo "copiados: $copiados · ya estaban: $iguales · con otro contenido: $distintos"
  [ "$distintos" -eq 0 ]
'
