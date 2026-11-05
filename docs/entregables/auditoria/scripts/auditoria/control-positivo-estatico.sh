#!/usr/bin/env bash
# F2-01: cada escaner estatico debe MARCAR el defecto sembrado; si no, su resultado no cuenta (§10).
#   auditoria/scripts/control-positivo-estatico.sh
# Los archivos vulnerables se generan en una carpeta temporal y se borran: nunca se versionan.
set -u
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=python
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
$PY auditoria/controles-positivos/generar.py "$D" > /dev/null || exit 2
falta=0
verificar() {  # herramienta, cuantos esperados, cuantos vistos
  if [ "$3" -ge "$2" ]; then echo "OK    $1: marca $3 (se esperaban >= $2)"; else echo "FALLA $1: marca $3 (se esperaban >= $2)"; falta=1; fi
}

n=$($PY -m ruff check --select S --no-cache --output-format concise "$D/vulnerable.py" 2>&1 | grep -cE ': S(105|608|308|602) ')
verificar "ruff S (secreto, SQL x2, mark_safe, shell=True)" 5 "$n"

n=$(uvx bandit==1.9.4 -q -r "$D/vulnerable.py" 2>&1 | grep -cE 'Issue: \[B(105|608|703|602)')
verificar "bandit (secreto, SQL x2, mark_safe, shell=True)" 5 "$n"

n=$(gitleaks dir "$D" --no-banner --redact 2>&1 | grep -cE 'leaks found: [1-9]')
verificar "gitleaks (token sembrado)" 1 "$n"

n=$(uvx pip-audit==2.10.1 -r "$D/requirements-vulnerable.txt" --no-deps --disable-pip 2>&1 | grep -cE 'PYSEC|GHSA|CVE')
verificar "pip-audit (dependencias con CVE)" 1 "$n"

# Trivy se verifica aparte (imagen por digest): ver F2-06.
[ "$falta" -eq 0 ] && echo "CONTROL POSITIVO: todos los escaneres ven el defecto sembrado" || echo "CONTROL POSITIVO FALLIDO"
exit "$falta"
