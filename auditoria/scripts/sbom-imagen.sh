#!/usr/bin/env bash
# F2-07: SBOM CycloneDX de la imagen de la aplicacion, y sus vulnerabilidades HIGH/CRITICAL.
#   auditoria/scripts/sbom-imagen.sh [imagen]     (por defecto jml-app:local)
set -eu
export MSYS_NO_PATHCONV=1
IMG=aquasec/trivy:0.67.2@sha256:e2b22eac59c02003d8749f5b8d9bd073b62e30fefaef5b7c8371204e0a4b0c08
APP="${1:-jml-app:local}"
SALIDA="auditoria/evidencia/estaticos/F2-07-SBOM"
mkdir -p "$SALIDA"
echo "imagen: $APP ($(docker image inspect "$APP" --format '{{.Id}}'))"
docker run --rm -v jml-trivy-cache:/root/.cache -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd)/$SALIDA":/out "$IMG" image --skip-version-check --format cyclonedx --output /out/sbom.cdx.json "$APP" 2>&1 | tail -2
echo "componentes: $(grep -o '"bom-ref"' "$SALIDA/sbom.cdx.json" | wc -l)"
sha256sum "$SALIDA/sbom.cdx.json"
echo "== vulnerabilidades HIGH/CRITICAL de la imagen"
docker run --rm -v jml-trivy-cache:/root/.cache -v /var/run/docker.sock:/var/run/docker.sock \
  "$IMG" image --skip-version-check --severity HIGH,CRITICAL --scanners vuln --ignore-unfixed=false "$APP" 2>&1 | grep -vE 'INFO|^$' | tail -40
