#!/usr/bin/env bash
# CA-13 con la definicion del SRS v2.5 (ADR-031): la base de la aplicacion es el PostgreSQL 17 local.
# Solo lectura del catalogo y de la configuracion de los contenedores; no cambia nada.
#
#   bash auditoria/scripts/ca-13-postgres-local.sh
#
# Cada bloque dice lo esperado; el codigo de salida es 1 si algo no coincide.
set -u
export MSYS_NO_PATHCONV=1
q() { docker exec jml-postgres-1 psql -U postgres -Atc "$1"; }
fallos=0
igual() {  # etiqueta obtenido esperado
  if [ "$2" = "$3" ]; then echo "OK    $1: $2"; else echo "FALLA $1: obtenido «$2», esperado «$3»"; fallos=$((fallos + 1)); fi
}

igual "privilegios de anon y authenticated sobre tablas de app" \
  "$(q "select count(*) from information_schema.role_table_grants where table_schema='app' and grantee in ('anon','authenticated')")" 0
igual "uso del esquema app por anon y authenticated" \
  "$(q "select has_schema_privilege('anon','app','USAGE')::text || ' ' || has_schema_privilege('authenticated','app','USAGE')::text")" "false false"
igual "tablas de app sin RLS (B-23)" \
  "$(q "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='app' and c.relkind='r' and not c.relrowsecurity")" 0
igual "politicas de RLS en app (RLS sin politicas)" "$(q "select count(*) from pg_policies where schemaname='app'")" 0
igual "app_backend con UPDATE, DELETE o TRUNCATE en auditoria, decision o cuenta_historial" \
  "$(q "select count(*) from information_schema.role_table_grants where table_schema='app' and grantee='app_backend' and table_name in ('auditoria','decision','cuenta_historial') and privilege_type in ('UPDATE','DELETE','TRUNCATE')")" 0
# Control positivo: si la consulta de privilegios no viera nada, los ceros de arriba no dirian nada.
positivos="$(q "select count(*) from information_schema.role_table_grants where table_schema='app' and grantee='app_backend'")"
if [ "$positivos" -gt 0 ]; then echo "OK    control positivo: app_backend tiene $positivos privilegios en app"; else echo "FALLA control positivo: 0 privilegios para app_backend"; fallos=$((fallos + 1)); fi
igual "puertos publicados por postgres" "$(docker inspect jml-postgres-1 --format '{{range $p, $b := .NetworkSettings.Ports}}{{if $b}}{{$p}} {{end}}{{end}}')" ""
igual "redes de postgres" "$(docker inspect jml-postgres-1 --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')" "jml_pg_net"
igual "pg_net es internal" "$(docker network inspect jml_pg_net --format '{{.Internal}}')" "true"
for c in jml-web-1 jml-worker-1; do
  igual "service_role en $c (secretos y entorno)" "$(docker exec "$c" sh -c 'ls /run/secrets 2>/dev/null; env' | grep -ci service_role)" 0
done
echo "fallos: $fallos"
[ "$fallos" -eq 0 ]
