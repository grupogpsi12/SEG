#!/usr/bin/env bash
# W-02 (ADR-033): las tarjetas del panel de GLPI (rafagas en paralelo a /ajax/) no reciben 429, y el
# resto de GLPI sigue con el limite general de 2 r/s (control). Stack LOCAL; no banea (ADR-032).
#
#   bash auditoria/scripts/verificar-w02.sh
set -u
export MSYS_NO_PATHCONV=1
DIR="$(mktemp -d)"; trap 'rm -rf "$DIR"' EXIT
fallos=0
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }
rafaga() {  # n ruta -> cuantas respuestas 429 (peticiones en paralelo, como el panel de GLPI)
  local n="$1" ruta="$2" i
  rm -f "$DIR"/c.*
  for i in $(seq 1 "$n"); do
    curl -sk -o "$(cygpath -w "$DIR/b.$i" 2>/dev/null || echo "$DIR/b.$i")" -w "%{http_code}" --max-time 15 \
      --resolve glpi.localhost:443:127.0.0.1 "https://glpi.localhost$ruta&i=$i" > "$DIR/c.$i" &
  done
  wait
  cat "$DIR"/c.* | fold -w3 | sort | uniq -c | tr '\n' ' ' >&2
  cat "$DIR"/c.* | fold -w3 | grep -c '^429$'
}
sleep 2
echo "== rafaga de 7 a /ajax/dashboard.php (las tarjetas del panel de tickets)"
n=$(rafaga 7 "/ajax/dashboard.php?action=get_card&card_id=w02"); echo
afirmar "0 respuestas 429 ($n)" '[ "$n" -eq 0 ]'
sleep 2
echo "== rafaga de 20 a /ajax/ (el panel central)"
n=$(rafaga 20 "/ajax/dashboard.php?action=get_card&card_id=w02"); echo
afirmar "0 respuestas 429 ($n)" '[ "$n" -eq 0 ]'
sleep 2
echo "== control: rafaga de 20 a la raiz de GLPI (limite general de 2 r/s)"
n=$(rafaga 20 "/?w02=1"); echo
afirmar "el limite general sigue frenando ($n respuestas 429)" '[ "$n" -ge 10 ]'
echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
