#!/usr/bin/env bash
# W-01 (ADR-032, B-36, B-39): el limite de ritmo responde 429 sin banear; un error repetido de otro tipo
# si banea (control negativo); /front/locale.php de GLPI llega completo a traves del WAF. Stack LOCAL.
#
#   bash auditoria/scripts/verificar-w01.sh
#
# Levanta los baneos antes y despues: la prueba banea a proposito la IP del equipo.
set -u
export MSYS_NO_PATHCONV=1
C="docker compose -f infra/compose.yaml"
fallos=0
# Con MSYS_NO_PATHCONV el curl de Windows no entiende /dev/null (codigo 23): los cuerpos van a un temporal.
TMPW="$(mktemp)"; CUERPO_U="$(mktemp)"; trap 'rm -f "$TMPW" "$CUERPO_U"' EXIT
CUERPO="$(cygpath -w "$CUERPO_U" 2>/dev/null || echo "$CUERPO_U")"  # el curl de Windows necesita la ruta de Windows
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }
desbanear() { $C exec -T bw-scheduler bwcli unban 10.20.40.128 > /dev/null 2>&1; sleep 3; }
baneos() { $C exec -T bw-scheduler bwcli bans 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -c "10.20.40.128"; }
pedir() {  # host ruta -> codigo
  curl -sk -o "$CUERPO" -w "%{http_code}" --max-time 15 --resolve "$1:443:127.0.0.1" "https://$1$2"
}

echo "== 1. /front/locale.php completo por el WAF (B-39: la regla 953100 cortaba el catalogo de traducciones)"
desbanear
for lang in en_GB es_419; do
  curl -sk -o "$CUERPO" --max-time 30 --resolve glpi.localhost:443:127.0.0.1 \
    -w "%{http_code} %{size_download}\n" "https://glpi.localhost/front/locale.php?domain=glpi&lang=$lang&v=w01" > "$TMPW" 2>&1
  codigo_curl=$?
  echo "   $lang: $(cat "$TMPW") (codigo de curl $codigo_curl)"
  afirmar "locale.php ($lang) llega completo" '[ $codigo_curl -eq 0 ] && grep -q "^200 " "$TMPW"'
done

echo "== 2. rafaga sobre el limite (P-12): 429 sin baneo"
desbanear
codigos=""
for _ in $(seq 1 30); do codigos="$codigos $(pedir glpi.localhost /)"; done
echo "   codigos:$codigos"
n429=$(echo "$codigos" | tr ' ' '\n' | grep -c '^429$')
afirmar "la rafaga produce 429 ($n429)" '[ $n429 -ge 10 ]'
sleep 4
afirmar "sin baneo tras $n429 respuestas 429" '[ "$(baneos)" -eq 0 ]'
sleep 2
siguiente=$(pedir glpi.localhost /)
afirmar "la siguiente pagina responde ($siguiente)" '[ "$siguiente" = 200 ]'

echo "== 3. control negativo: 404 repetidos SI banean"
desbanear
for _ in $(seq 1 25); do pedir glpi.localhost /no-existe-w01.php > /dev/null; sleep 0.6; done
sleep 4
afirmar "baneo tras 25 respuestas 404" '[ "$(baneos)" -ge 1 ]'
desbanear

echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
