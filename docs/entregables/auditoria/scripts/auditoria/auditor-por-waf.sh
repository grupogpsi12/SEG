#!/usr/bin/env bash
# F6-06: el Auditor verifica la cadena por el WAF a ritmo humano y de guion (D-02, D-03). Stack LOCAL.
set -u
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"
C="-f infra/compose.yaml -f infra/compose.local.yaml"
bash auditoria/scripts/neutralizar.sh pre
AUD="$(docker compose $C run --rm --no-deps -T -v "$RAIZ:/repo:ro" -w /repo -e PYTHONPATH=/repo web \
  python auditoria/scripts/sesiones-laboratorio.py 2>/dev/null | tail -1 | sed -E 's/.*"auditor": "([^"]+)".*/\1/')"
PY=".venv/Scripts/python.exe"; [ -x "$PY" ] || PY=python
PYTHONUTF8=1 $PY auditoria/scripts/auditor-por-waf.py "$AUD"
codigo=$?
bash auditoria/scripts/neutralizar.sh post
exit $codigo
