#!/usr/bin/env bash
# F7-07: testssl del borde LOCAL (certificado autofirmado: solo vale para el borde local; en Azure sera Let's Encrypt).
# Protocolos, cifrados, vulnerabilidades conocidas y cabeceras. testssl.sh por digest (herramientas.lock).
set -u
export MSYS_NO_PATHCONV=1
TESTSSL=drwetter/testssl.sh@sha256:d28eaa071ac821d553d259522e794fcfa3fd42cfea994dde1e83c84a4f6a5dd6
bash auditoria/scripts/neutralizar.sh unban > /dev/null 2>&1
# `app.localhost` resuelve a 127.0.0.1 dentro del contenedor: se le da la IP del anfitrion con --ip y el nombre
# queda como SNI y como Host
HG="$(docker run --rm --add-host hg:host-gateway python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 getent ahostsv4 hg | awk 'NR==1 {print $1}')"
echo "borde local: app.localhost:443 via $HG (SNI app.localhost)"
docker run --rm "$TESTSSL" --color 0 --warnings off --ip "$HG" --protocols --server-defaults --vulnerable --headers app.localhost:443 2>&1   | sed -E 's/\[[0-9;]*m//g' | grep -vE "^\s*$|Start 20|Done 20|Testing |^ -->>"
bash auditoria/scripts/neutralizar.sh unban > /dev/null 2>&1
