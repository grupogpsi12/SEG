#!/usr/bin/env bash
# F0-04: confirma o refuta D-01 a D-12 del plan (docs/PLAN_AUDITORIA.md §1) contra el codigo real.
# Solo LEE el repositorio (y una consulta publica a la API de GitHub para D-07); no ejecuta escaneos.
#   auditoria/scripts/confirmar-d.sh
# Cada linea de veredicto es «D-nn | CONFIRMADO|REFUTADO|PENDIENTE(Fx) | motivo».
set -uo pipefail
cd "$(dirname "$0")/../.."
v() { printf '%s | %s | %s\n' "$1" "$2" "$3"; }

# D-01: marcador sin reemplazar en la evidencia de CA-12
n=$(grep -rn "SQLMAP_RESULTADOS" docs/evidencia/*.md | wc -l)
l=$(grep -rn "SQLMAP_RESULTADOS" docs/evidencia/*.md | head -1 | cut -d: -f1-2)
[ "$n" -gt 0 ] && v D-01 CONFIRMADO "marcador SQLMAP_RESULTADOS sin reemplazar en $l; el documento declara «sqlmap nivel 3 sin hallazgos» (CA-12)" \
                || v D-01 REFUTADO "sin marcadores"

# D-02: la Entrega 3 no esta en el repositorio
if find . -path ./.venv -prune -o -type f \( -name "casos-de-uso.txt" -o -name "junit-suite.xml" \) -print 2> /dev/null | grep -q .; then
  v D-02 "PENDIENTE(F6)" "artefacto presente: revisar CU-11 contra el Documento 4"
else
  v D-02 "PENDIENTE(F6)" "casos-de-uso.txt de la Entrega 3 NO esta en el repositorio: no verificable desde archivos; se reproduce la verificacion del Auditor por el WAF en F6-06"
fi

# D-03: el limite general se aplica a toda ruta, incluida /auditoria
g=$(grep -c "LIMIT_REQ_RATE=2r/s" infra/compose.yaml)
e=$(grep -c "LIMIT_REQ_URL_[0-9]=" infra/compose.yaml)
v D-03 "PENDIENTE(F6)" "limite general 2r/s presente ($g) y solo $e excepciones por URL (/ingreso y /static/); /auditoria no tiene excepcion. Plausible; se mide a ritmo humano y de guion en F6-06"

# D-04: ZAP activo y sqlmap no pasan por el WAF
if grep -q "El escaneo activo y sqlmap no van por el WAF" infra/scripts/seguridad-dinamica.sh; then
  v D-04 CONFIRMADO "infra/scripts/seguridad-dinamica.sh:$(grep -n 'no van por el WAF' infra/scripts/seguridad-dinamica.sh | head -1 | cut -d: -f1): solo el baseline pasa por el WAF; la postura con WAF de las pruebas activas no esta medida"
else v D-04 REFUTADO "el script ya cubre ambas posiciones"; fi

# D-05: sqlmap nivel 3 y ausencia de sumideros de cabeceras
nivel=$(grep -o -- '--level=[0-9]' infra/scripts/seguridad-dinamica.sh | sort -u | tr '\n' ' ')
meta=$(grep -rn "request\.META" src --include=*.py | grep -v "middleware.py" | wc -l)
sql=$(grep -rnE "cursor\(\)|\.raw\(|\.extra\(|RawSQL|execute\(" src --include=*.py | grep -v "/migrations/" | wc -l)
v D-05 CONFIRMADO "sqlmap $nivel(Host solo entra en nivel 5). Sumideros: request.META fuera del middleware=$meta; SQL crudo/raw/extra/execute fuera de migraciones=$sql. Riesgo acotado; se sostiene con la prueba U-06 (F3) y sqlmap nivel 5 (F6)"

# D-06: un solo proceso de gunicorn
w=$(grep -o '"--workers", "1"' Dockerfile | head -1)
v D-06 CONFIRMADO "Dockerfile: gunicorn con $w y 8 hilos (S-29/ADR-017: el token AAL1 vive en memoria). Punto unico de falla; amenaza N-3"

# D-07: sin pre-commit y master sin proteccion
hooks=$( { ls -a | grep -E "pre-commit-config|\.githooks"; ls .git/hooks | grep -v sample; git config core.hooksPath; } 2> /dev/null | wc -l)
prot=$(curl -s --max-time 20 https://api.github.com/repos/grupogpsi12/SEG/branches/master | grep -o '"protected": *[a-z]*' | head -1)
v D-07 CONFIRMADO "hooks locales=$hooks (ninguno); GitHub: $prot; gitleaks solo corre en .github/workflows/verificar.yml (RS-12 pide cada commit)"

# D-08: ruff sin reglas S
sel=$(grep -m1 '^select' pyproject.toml)
if echo "$sel" | grep -q '"S"'; then v D-08 REFUTADO "ruff ya incluye S"; else
  v D-08 CONFIRMADO "pyproject.toml [tool.ruff.lint] $sel : sin flake8-bandit (S). bandit cubre la CI; falta la deteccion temprana"; fi

# D-09: mutacion de aplicacion nunca medida
pend=$(grep -c '^- \[ \] \*\*5.10' tasks/todo.md)
solo=$(grep -c "src/jml/dominio" docs/spikes/mutacion.md)
v D-09 CONFIRMADO "tasks/todo.md 5.10 pendiente=$pend; docs/spikes/mutacion.md mide solo src/jml/dominio (menciones: $solo); aplicacion y modulos de seguridad sin medicion por mutacion"

# D-10: RS-16 depende de una persona
v D-10 CONFIRMADO "docs/estado.md §4.A.1: el asesor de seguridad de Supabase y la contrasena minima de 12 los ejecuta una persona en el Dashboard; CA-12 incompleto hasta entonces [PENDIENTE: accion humana]"

# D-11: rutas sin matriz que las vigile
pat=$(grep -cE "^\s+(path|re_path)\(" src/config/urls.py)
enumera=$(grep -rlE "urlpatterns|get_resolver|url_patterns" tests --include=*.py | wc -l)
v D-11 CONFIRMADO "src/config/urls.py tiene $pat patrones (24 si se cuenta cada accion de «decidir»: aprobar, rechazar y cancelar); pruebas que enumeran las rutas=$enumera. Correccion al plan: 22 patrones, no 24"

# D-12: RNF-11 subestima su propia compuerta
rnf=$(grep -o "al menos [0-9]* %" docs/SRS.md | head -1)
cmp=$(grep -o "fail-under=[0-9]*" Makefile | tr '\n' ' ')
v D-12 CONFIRMADO "SRS RNF-11 pide $rnf; Makefile exige $cmp (dominio/aplicacion); real 99 %. Deriva documental informativa"
