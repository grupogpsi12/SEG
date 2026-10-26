#!/usr/bin/env bash
# RNF-06 (item 4.1): mide el p95 de las paginas con 300 colaboradores y 20 usuarios concurrentes.
#
#   infra/scripts/carga.sh                    # 300 colaboradores, 20 usuarios, 10 vueltas
#   COLABORADORES=300 USUARIOS=20 VUELTAS=10 infra/scripts/carga.sh
#   MANTENER=si infra/scripts/carga.sh       # deja el entorno arriba para perfilar
#
# Todo DESECHABLE, en una red propia (jml-carga): un PostgreSQL 17 con los mismos roles que el modo
# local (infra/local/initdb/01-roles.sh) y la imagen de la aplicacion con su configuracion de
# produccion (gunicorn 1 x 8 hilos, S-29). No toca la base ni el GLPI del stack. Se mide contra
# web directo, sin BunkerWeb: su limite es por IP (2 r/s, RS-08) y frenaria a un solo generador.
#
# Imagen: JML_IMAGEN (por defecto jml-app:local, la que construye compose).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGEN="${JML_IMAGEN:-jml-app:local}"
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
RED=jml-carga
TMP="$RAIZ/.contrato-tmp/carga"   # dentro del repo: Docker Desktop no ve el /tmp de Git Bash
COLABORADORES="${COLABORADORES:-300}"
USUARIOS="${USUARIOS:-20}"
VUELTAS="${VUELTAS:-10}"

limpiar() {
  docker rm -f jml-carga-web jml-carga-pg > /dev/null 2>&1 || true
  docker network rm "$RED" > /dev/null 2>&1 || true
  rm -rf "$TMP"
}
# MANTENER=si deja la base y web arriba para perfilar (luego: MANTENER=no ... o `limpiar` a mano).
[ "${MANTENER:-no}" = si ] || trap limpiar EXIT
limpiar
umask 077
mkdir -p "$TMP/backend" "$TMP/duenio"
aleatorio() { head -c 24 /dev/urandom | base64 | tr -d '=+/\n'; }
for d in backend duenio; do aleatorio > "$TMP/$d/django_secret_key"; : > "$TMP/$d/supabase_ca_crt"; done
aleatorio > "$TMP/backend/db_password"
aleatorio > "$TMP/duenio/db_password"
cp "$TMP/backend/db_password" "$TMP/pg_backend"
cp "$TMP/duenio/db_password" "$TMP/pg_duenio"
chmod a+r "$TMP"/pg_* "$TMP"/backend/* "$TMP"/duenio/*   # los contenedores no corren como este usuario

# Despues de crear los archivos con rutas de Git Bash: las de los contenedores no se traducen.
export MSYS_NO_PATHCONV=1
docker network create "$RED" > /dev/null
docker run -d --name jml-carga-pg --network "$RED" \
  -e POSTGRES_PASSWORD="$(aleatorio)" \
  -v "$TMP/pg_backend:/run/secrets/db_password:ro" \
  -v "$TMP/pg_duenio:/run/secrets/db_owner_password:ro" \
  -v "$RAIZ/infra/local/initdb/01-roles.sh:/docker-entrypoint-initdb.d/01-roles.sh:ro" \
  -v "$RAIZ/infra/supabase/duenio-separado.sql:/opt/jml/duenio-separado.sql:ro" \
  "$PG_IMAGEN" > /dev/null
for _ in $(seq 1 60); do
  docker exec jml-carga-pg pg_isready -U postgres -h 127.0.0.1 > /dev/null 2>&1 && break
  sleep 1
done
sleep 3  # initdb reinicia el servidor una vez despues de los scripts

ENTORNO=(-e DJANGO_ALLOWED_HOSTS=web -e JML_DB_HOST=jml-carga-pg -e JML_DB_SSLMODE=disable
         -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1)
correr() {  # secretos (backend|duenio) usuario-de-db comando...
  local secretos="$1" usuario="$2"; shift 2
  docker run --rm --network "$RED" "${ENTORNO[@]}" -e JML_DB_USUARIO="$usuario" \
    -v "$TMP/$secretos:/run/secrets:ro" -v "$RAIZ:/repo:ro" -w /repo "$IMAGEN" "$@"
}

echo "== migraciones como app_owner (ADR-028)"
correr duenio app_owner python /app/manage.py migrate --noinput -v 0
echo "== semilla: $COLABORADORES colaboradores con su historia"
correr backend app_backend python -m tests.carga.sembrar "$COLABORADORES" | tail -1 > "$TMP/semilla.json"
cat "$TMP/semilla.json"; echo
correr backend app_backend python -m tests.carga.sesiones | tail -1 > "$TMP/sesiones.json"

echo "== web con la configuracion de produccion (gunicorn 1 x 8 hilos)"
docker run -d --name jml-carga-web --network "$RED" --network-alias web "${ENTORNO[@]}" \
  -e JML_DB_USUARIO=app_backend -v "$TMP/backend:/run/secrets:ro" --memory 512m \
  "$IMAGEN" > /dev/null
for _ in $(seq 1 60); do
  docker exec jml-carga-web python -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/salud', headers={'Host': 'web'}), timeout=3)" > /dev/null 2>&1 && break
  sleep 1
done

echo "== medicion: $USUARIOS usuarios concurrentes x $VUELTAS vueltas"
correr backend app_backend python -m tests.carga.medir http://web:8000 \
  /repo/.contrato-tmp/carga/sesiones.json /repo/.contrato-tmp/carga/semilla.json "$USUARIOS" "$VUELTAS" \
  | tail -1 | tee "$RAIZ/.contrato-tmp/resultado-carga.json"
cp "$RAIZ/.contrato-tmp/resultado-carga.json" "${SALIDA:-/dev/null}" 2> /dev/null || true
