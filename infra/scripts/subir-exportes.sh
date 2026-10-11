#!/usr/bin/env bash
# RD-04: sube la auditoria diaria y su ancla a Blob con politica de inmutabilidad (365 dias).
# Corre en el HOST de la VM (cron diario, 01:30 hora de Bogota), con la identidad administrada:
# ni la aplicacion ni este script tienen claves de la cuenta de Storage (RS-20, ADR-009).
#
#   JML_STORAGE_CUENTA=<cuenta> infra/scripts/subir-exportes.sh
#
# Requisitos (paso de 5.2): Azure CLI en el host; contenedor `auditoria` creado con politica de
# inmutabilidad por tiempo (365 dias, bloqueada); rol «Storage Blob Data Contributor» de la
# identidad de la VM SOLO sobre ese contenedor.
# SIN VERIFICAR contra Azure todavia (item 5.2/5.3).
set -euo pipefail

CUENTA="${JML_STORAGE_CUENTA:?defina JML_STORAGE_CUENTA}"
ORIGEN="${JML_EXPORTES_HOST:-$(docker volume inspect jml_exportes --format '{{ .Mountpoint }}')}"

az login --identity --output none
# --overwrite false: un blob ya subido nunca se reemplaza (y la politica tampoco lo permitiria).
for ancla in "$ORIGEN"/ancla-*.json; do
  [ -e "$ancla" ] || continue
  dia="$(basename "$ancla" .json)"; dia="${dia#ancla-}"
  for archivo in "$ORIGEN/auditoria-$dia.jsonl" "$ancla"; do
    if ! az storage blob exists --auth-mode login --account-name "$CUENTA" --container-name auditoria \
         --name "$(basename "$archivo")" --query exists --output tsv | grep -q true; then
      az storage blob upload --auth-mode login --account-name "$CUENTA" --container-name auditoria \
        --file "$archivo" --name "$(basename "$archivo")" --overwrite false --output none
      echo "subido: $(basename "$archivo")"
    fi
  done
done
