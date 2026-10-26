#!/usr/bin/env bash
# F2-10: el gancho G0 rechaza un commit con un secreto sembrado y deja pasar uno limpio.
#   auditoria/scripts/probar-gancho.sh
# Trabaja en un repositorio temporal; el secreto falso se arma en ejecucion (no esta en el repositorio).
set -u
RAIZ="$(pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q . && git config user.email t@t && git config user.name t && git config core.hooksPath "$RAIZ/.githooks"
secreto="ghp_$(printf '%s' 0h2v4j6x8l0z2n4b6p8d0r2f4t6h8v0j2x4l)"

echo "# limpio" > ok.md && git add ok.md
git commit -q -m "limpio" && echo "OK    commit limpio: aceptado" || { echo "FALLA commit limpio rechazado"; exit 1; }

printf 'TOKEN = "%s"\n' "$secreto" > malo.py && git add malo.py
if git commit -q -m "con secreto" 2> salida.txt; then
  echo "FALLA el commit con secreto fue ACEPTADO"; exit 1
else
  echo "OK    commit con secreto: rechazado ($(grep -c 'gitleaks' salida.txt) mensajes del gancho)"
fi
git reset -q HEAD malo.py && rm malo.py

printf 'import os\n' > feo.py && git add feo.py
if git commit -q -m "ruff" 2> salida.txt; then echo "FALLA ruff no rechazo F401"; exit 1; elif grep -q F401 salida.txt; then echo "OK    commit con error de ruff: rechazado por F401"; else echo "FALLA rechazado por otra causa: $(head -1 salida.txt)"; exit 1; fi
echo "G0 verificado"

# Rotura deliberada (plan 10): sin el gancho, el mismo commit con secreto SI pasa.
git reset -q HEAD feo.py && rm -f feo.py
git config --unset core.hooksPath
printf 'TOKEN = "%s"\n' "$secreto" > malo2.py && git add malo2.py
git commit -q -m "sin gancho" && echo "OK    sin el gancho el secreto se confirma (el gancho es lo que lo impide)" || { echo "FALLA"; exit 1; }
