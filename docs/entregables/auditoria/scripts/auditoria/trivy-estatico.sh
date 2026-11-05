#!/usr/bin/env bash
# F2-01 (control positivo de Trivy) y F2-06 (fs + config sobre el repositorio), con la imagen fijada
# por digest (herramientas.lock). La base de vulnerabilidades queda en el volumen `jml-trivy-cache`.
#   auditoria/scripts/trivy-estatico.sh
set -u
export MSYS_NO_PATHCONV=1
IMG=aquasec/trivy:0.67.2@sha256:e2b22eac59c02003d8749f5b8d9bd073b62e30fefaef5b7c8371204e0a4b0c08
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python
RAIZ="$(pwd)"
trivy() { docker run --rm -v jml-trivy-cache:/root/.cache -v "$1":/src:ro "$IMG" "${@:2}"; }

echo "== control positivo: lo sembrado DEBE aparecer"
D="$(mktemp -d -p "$RAIZ" .cp-trivy-XXXX)"
trap 'rm -rf "$D"' EXIT
$PY auditoria/controles-positivos/generar.py "$D" > /dev/null
n=$(trivy "$D" config --severity HIGH,CRITICAL /src 2>&1 | grep -cE 'DS-0002|DS-0001|DS-0017|DS-0026|DS-0005')
echo "trivy config sobre Dockerfile.vulnerable: $n reglas (se espera >= 1)"
mkdir -p "$D/dep" && cp "$D/requirements-vulnerable.txt" "$D/dep/requirements.txt"  # Trivy solo reconoce ese nombre
n2=$(trivy "$D" fs --scanners vuln --severity HIGH,CRITICAL /src 2>&1 | grep -cE 'CVE-[0-9]+-[0-9]+')
echo "trivy fs sobre requirements-vulnerable.txt: $n2 CVE (se espera >= 1)"
[ "$n" -ge 1 ] && [ "$n2" -ge 1 ] || { echo "CONTROL POSITIVO DE TRIVY FALLIDO"; exit 3; }

echo "== trivy config (infra/ y Dockerfile)"
trivy "$RAIZ" config --severity HIGH,CRITICAL --skip-dirs .venv --skip-dirs .contrato-tmp --skip-dirs secrets /src
echo "config=$?"
echo "== trivy fs (dependencias, secretos y configuracion) del repositorio"
trivy "$RAIZ" fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --skip-dirs .venv --skip-dirs .contrato-tmp --skip-dirs secrets --skip-files infra/.env /src
echo "fs=$?"
