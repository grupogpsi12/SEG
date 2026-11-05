#!/usr/bin/env bash
# V-02 (ADR-034, ADR-036): rafagas reales por el WAF. El panel central de GLPI pide 26 tarjetas en un
# segundo (medido), los filtros de la aplicacion no reciben 429, y los limites del ingreso, las fichas
# y la raiz de GLPI siguen frenando (controles). Stack LOCAL; el 429 no banea (ADR-032).
#
#   bash auditoria/scripts/verificar-v02.sh
set -u
export MSYS_NO_PATHCONV=1
DIR="$(mktemp -d)"; trap 'rm -rf "$DIR"' EXIT
NUL="$(cygpath -w "$DIR/cuerpo" 2>/dev/null || echo "$DIR/cuerpo")"
fallos=0
afirmar() { if eval "$2"; then echo "OK    $1"; else echo "FALLA $1"; fallos=$((fallos + 1)); fi; }
rafaga() {  # host n ruta -> cuantas respuestas 429, en paralelo
  local host="$1" n="$2" ruta="$3" i
  rm -f "$DIR"/c.*
  for i in $(seq 1 "$n"); do
    curl -sk -o "$NUL.$i" -w "%{http_code}" --max-time 20 \
      --resolve "$host:443:127.0.0.1" "https://$host$ruta" > "$DIR/c.$i" &
  done
  wait
  cat "$DIR"/c.* | fold -w3 | sort | uniq -c | tr '\n' ' ' >&2
  cat "$DIR"/c.* | fold -w3 | grep -c '^429$'
}
for n in 26 40; do
  sleep 2; echo "== rafaga de $n a /ajax/dashboard.php de GLPI"
  c=$(rafaga glpi.localhost "$n" "/ajax/dashboard.php?action=get_card&card_id=v02&dashboard=central"); echo
  afirmar "0 respuestas 429 ($c)" '[ "$c" -eq 0 ]'
done
sleep 2; echo "== rafaga de 6 a /front/locale.php"
c=$(rafaga glpi.localhost 6 "/front/locale.php?domain=glpi&lang=en_GB&v=v02"); echo
afirmar "0 respuestas 429 ($c)" '[ "$c" -eq 0 ]'
sleep 2; echo "== rafaga de 8 a /tickets (sin sesion: redirige al ingreso)"
c=$(rafaga app.localhost 8 "/tickets?cola=AD"); echo
afirmar "0 respuestas 429 ($c)" '[ "$c" -eq 0 ]'
sleep 2; echo "== control: rafaga de 20 a la raiz de GLPI (2 r/s)"
c=$(rafaga glpi.localhost 20 "/"); echo
afirmar "el limite general sigue frenando ($c)" '[ "$c" -ge 10 ]'
sleep 2; echo "== control: rafaga de 8 a /colaboradores (2 r/s, T10)"
c=$(rafaga app.localhost 8 "/colaboradores/col-1"); echo
afirmar "el limite de las fichas sigue frenando ($c)" '[ "$c" -ge 3 ]'
sleep 61; echo "== control: rafaga de 10 a /ingreso (5 por minuto, T1)"
c=$(rafaga app.localhost 10 "/ingreso"); echo
afirmar "el limite del ingreso sigue frenando ($c)" '[ "$c" -ge 4 ]'
sleep 61  # devuelve los intentos de /ingreso: pruebas.sh corre despues y los necesita
echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
