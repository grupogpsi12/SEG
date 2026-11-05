#!/usr/bin/env bash
# CA-11 / RNF-04 (RTO 4 h): simulacro de restauracion con evidencia, en instancias DESECHABLES.
#
#   JML_MODO=local JML_RESPALDO_DESTINO=.contrato-tmp/respaldos infra/scripts/respaldo.sh
#   infra/scripts/restaurar-prueba.sh .contrato-tmp/respaldos [AAAA-MM-DD]
#
# 1. Un PostgreSQL 17 nuevo con los roles de Supabase y el duenio separado (01-roles.sh, ADR-028)
#    y `pg_restore` del esquema `app` como app_owner. Luego `migrar`, como manda docs/operacion.md.
# 2. Un MariaDB nuevo con el volcado de GLPI.
# 3. Comprobaciones contra el ORIGEN (el stack local): mismas filas por tabla, misma cabeza de la
#    cadena de auditoria y cadena VALIDA segun la propia aplicacion, `app_backend` sin UPDATE sobre
#    `auditoria` (CA-13) y los mismos tickets en GLPI.
# Imprime el tiempo total. No toca el stack: el origen solo se lee.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
CARPETA="$(cd "${1:?uso: $0 <carpeta-de-respaldos> [AAAA-MM-DD]}" && pwd)"
FECHA="${2:-$(TZ='<-05>5' date +%Y-%m-%d)}"  # desfase fijo: ver respaldo.sh
IMAGEN="${JML_IMAGEN:-jml-app:local}"
PG_IMAGEN=postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3
MARIADB_IMAGEN=mariadb:11.4@sha256:1292844148b311e4ed4300022a996d39083f415a963e970cf47cad1b3b18e3a6
RED=jml-restauracion
TMP="$RAIZ/.contrato-tmp/restauracion"
DUMP="$CARPETA/app-$FECHA.dump"
GLPI="$CARPETA/glpi-$FECHA.sql.gz"
[ -s "$DUMP" ] && [ -s "$GLPI" ] || { echo "faltan $DUMP o $GLPI" >&2; exit 1; }

limpiar() {
  docker rm -f jml-rest-pg jml-rest-mariadb > /dev/null 2>&1 || true
  docker network rm "$RED" > /dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap limpiar EXIT
limpiar
umask 077
mkdir -p "$TMP/backend" "$TMP/duenio"
aleatorio() { head -c 24 /dev/urandom | base64 | tr -d '=+/\n'; }
for d in backend duenio; do aleatorio > "$TMP/$d/django_secret_key"; : > "$TMP/$d/supabase_ca_crt"; done
aleatorio > "$TMP/backend/db_password"
aleatorio > "$TMP/duenio/db_password"
cp "$TMP/backend/db_password" "$TMP/pg_backend"; cp "$TMP/duenio/db_password" "$TMP/pg_duenio"
chmod a+r "$TMP"/pg_* "$TMP"/backend/* "$TMP"/duenio/*
export MSYS_NO_PATHCONV=1

inicio=$(date +%s)
docker network create "$RED" > /dev/null
echo "== 1. PostgreSQL nuevo con los roles de Supabase y el duenio separado"
docker run -d --name jml-rest-pg --network "$RED" -e POSTGRES_PASSWORD="$(aleatorio)" \
  -v "$TMP/pg_backend:/run/secrets/db_password:ro" -v "$TMP/pg_duenio:/run/secrets/db_owner_password:ro" \
  -v "$RAIZ/infra/local/initdb/01-roles.sh:/docker-entrypoint-initdb.d/01-roles.sh:ro" \
  -v "$RAIZ/infra/supabase/duenio-separado.sql:/opt/jml/duenio-separado.sql:ro" \
  -v "$CARPETA:/respaldos:ro" "$PG_IMAGEN" > /dev/null
for _ in $(seq 1 60); do docker exec jml-rest-pg pg_isready -U postgres -h 127.0.0.1 > /dev/null 2>&1 && break; sleep 1; done
sleep 3
echo "== 2. pg_restore del esquema app como app_owner"
# El esquema ya existe (vacio y de app_owner): se omite su CREATE para poder fallar al primer error.
docker exec -e PGPASSWORD="$(cat "$TMP/pg_duenio")" jml-rest-pg sh -c "
  pg_restore -l /respaldos/app-$FECHA.dump | grep -v ' SCHEMA - app ' > /tmp/lista &&
  pg_restore -h 127.0.0.1 -U app_owner -d postgres --no-owner --role=app_owner --exit-on-error \
    -L /tmp/lista /respaldos/app-$FECHA.dump"
echo "== 3. migrar (como en docs/operacion.md: aplica lo que falte)"
docker run --rm --network "$RED" -e DJANGO_ALLOWED_HOSTS=web -e JML_DB_HOST=jml-rest-pg \
  -e JML_DB_SSLMODE=disable -e JML_DB_USUARIO=app_owner -v "$TMP/duenio:/run/secrets:ro" \
  "$IMAGEN" python manage.py migrate --noinput -v 0
echo "== 4. MariaDB nuevo con el volcado de GLPI"
clave_glpi="$(aleatorio)"
docker run -d --name jml-rest-mariadb --network "$RED" -e MARIADB_RANDOM_ROOT_PASSWORD=yes \
  -e MARIADB_DATABASE=glpi -e MARIADB_USER=glpi -e MARIADB_PASSWORD="$clave_glpi" \
  -v "$CARPETA:/respaldos:ro" "$MARIADB_IMAGEN" > /dev/null
for _ in $(seq 1 90); do docker exec jml-rest-mariadb healthcheck.sh --connect --innodb_initialized > /dev/null 2>&1 && break; sleep 1; done
docker exec jml-rest-mariadb sh -c "gunzip -c /respaldos/glpi-$FECHA.sql.gz | mariadb -u glpi -p'$clave_glpi' glpi"
fin_restauracion=$(date +%s)

echo "== 5. Comprobaciones contra el origen"
cuentas_sql() {  # contenedor -> filas exactas por tabla del esquema app
  docker exec "$1" psql -qtA -U postgres -d postgres -c "
    do \$\$ declare t text; begin
      create temp table conteo(t text, n bigint);
      -- El origen sigue vivo: el worker y las sesiones escriben solos despues del respaldo.
      for t in select tablename from pg_tables where schemaname = 'app'
               and tablename not in ('sincronizacion', 'django_session') loop
        execute format('insert into conteo select %L, count(*) from app.%I', t, t);
      end loop; end \$\$;
    select string_agg(t || '=' || n, ' ' order by t) from conteo;" | tail -1
}
cabeza="select secuencia || ':' || hash from app.auditoria order by secuencia desc limit 1"
origen_pg="$(docker ps -q --filter name=jml-postgres-1)"
[ -n "$origen_pg" ] || { echo "no encuentro el PostgreSQL del stack local (jml-postgres-1)" >&2; exit 1; }
a="$(cuentas_sql "$origen_pg")"; b="$(cuentas_sql jml-rest-pg)"
[ "$a" = "$b" ] && echo "  filas por tabla: iguales en $(echo "$b" | wc -w) tablas (sincronizacion y django_session las escribe el sistema solo)" \
  || { echo "  filas por tabla: DISTINTAS"; echo "    origen:     $a"; echo "    restaurada: $b"; exit 1; }
ca="$(docker exec "$origen_pg" psql -qtA -U postgres -d postgres -c "$cabeza")"
cb="$(docker exec jml-rest-pg psql -qtA -U postgres -d postgres -c "$cabeza")"
[ "$ca" = "$cb" ] && echo "  cabeza de la cadena: igual (secuencia ${cb%%:*})" || { echo "  cabeza DISTINTA: $ca / $cb"; exit 1; }
docker run --rm --network "$RED" -e DJANGO_ALLOWED_HOSTS=web -e JML_DB_HOST=jml-rest-pg \
  -e JML_DB_SSLMODE=disable -e JML_DB_USUARIO=app_backend -v "$TMP/backend:/run/secrets:ro" \
  "$IMAGEN" python -c "
import django; django.setup()
from django.db import DatabaseError, connection, transaction
from jml.adaptadores.salida.persistencia.repositorios import RepositoriosDjango
from jml.adaptadores.salida.reloj import RelojDelSistema
with RepositoriosDjango(RelojDelSistema()).unidad_de_trabajo() as u:
    r = u.auditoria.verificar()
assert r.valida, r
print('  cadena de auditoria: VALIDA segun la aplicacion, leida como app_backend')
try:
    with transaction.atomic(), connection.cursor() as c:
        c.execute('update auditoria set actor = actor where secuencia = 1')
    raise SystemExit('  app_backend PUEDE modificar la auditoria: NO')
except DatabaseError:
    print('  app_backend no puede modificar la auditoria (RD-02, CA-13)')
"
tickets="select concat_ws(char(32), (select count(*) from glpi_tickets), (select count(*) from glpi_itilcategories), (select count(*) from glpi_groups), (select count(*) from glpi_rules), (select count(*) from glpi_users), (select count(*) from glpi_documents))"
ta="$(cd "$RAIZ" && docker compose -f infra/compose.yaml -f infra/compose.local.yaml exec -T mariadb sh -c "mariadb -N -u glpi -p\"\$(cat /run/secrets/glpi_db_password)\" glpi -e '$tickets'")"
tb="$(docker exec jml-rest-mariadb mariadb -N -u glpi -p"$clave_glpi" glpi -e "$tickets")"
[ "$ta" = "$tb" ] && echo "  GLPI (tickets, categorias, grupos, reglas, usuarios, documentos): iguales ($tb)" \
  || { echo "  GLPI DISTINTO: $ta / $tb"; exit 1; }
fin=$(date +%s)
echo "RESTAURACION COMPLETA Y VERIFICADA: $(( fin_restauracion - inicio )) s de restauracion, $(( fin - inicio )) s con las comprobaciones (RTO exigido: 4 h)"
