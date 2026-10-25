#!/usr/bin/env bash
# F7-02 (N-2, T20): la API de BunkerWeb (puerto 5000) desde la red `app`, con y sin token, dentro y fuera de
# API_WHITELIST_IP. El token se toma del entorno del planificador y NUNCA se imprime.
set -u
export MSYS_NO_PATHCONV=1
PY=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
T="$(docker exec jml-bw-scheduler-1 printenv API_TOKEN)"
sonda() {  # red, descripcion, ruta, tipo-de-token
  docker run --rm --network "$1" -e T="$T" -e TIPO="$4" -e RUTA="$3" "$PY" python -c '
import os, urllib.request as u, urllib.error as e
r = u.Request("http://bunkerweb:5000" + os.environ["RUTA"], headers={"Host": "bwapi"})  # el servidor de la API solo responde a ese Host
t = os.environ["TIPO"]
if t == "correcto": r.add_header("Authorization", "Bearer " + os.environ["T"])
elif t == "malo": r.add_header("Authorization", "Bearer token-incorrecto")
try: print(u.urlopen(r, timeout=8).status)
except e.HTTPError as x: print(x.code)
except Exception as x: print("sin respuesta:", type(x).__name__)
'
}
echo "# desde la red app (10.20.40.0/24), FUERA de API_WHITELIST_IP (127.0.0.0/8 y 10.20.30.0/24)"
for tipo in ninguno malo correcto; do
  printf '  /instances  token %-9s -> %s\n' "$tipo" "$(sonda jml_app x /instances "$tipo")"
  printf '  /health     token %-9s -> %s\n' "$tipo" "$(sonda jml_app x /health "$tipo")"
done
echo "# desde la red bw-universe (10.20.30.0/24), DENTRO de la lista blanca: el control positivo"
for tipo in ninguno malo correcto; do
  printf '  /instances  token %-9s -> %s\n' "$tipo" "$(sonda jml_bw-universe x /instances "$tipo")"
done
