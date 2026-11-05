#!/usr/bin/env bash
# Auditoria de configuracion de las bases del stack local (entregable 5.7). Solo lectura, salvo las
# pruebas negativas de RD-02/RF-14, que se ejecutan dentro de una transaccion que se revierte.
#   auditoria/scripts/auditar-bases.sh > auditoria/evidencia/estaticos/bases-config.txt  (repetida de la Entrega 3)
set -u
PG="docker exec -i jml-postgres-1 psql -U postgres -d postgres -X -P pager=off"

echo "### PostgreSQL 17 (sustituto local de Supabase, ADR-028)"
$PG -c "select version();"
$PG -c "select name, setting from pg_settings where name in ('ssl','password_encryption','listen_addresses',
  'log_connections','log_disconnections','log_statement','idle_in_transaction_session_timeout','row_security') order by 1;"
echo "-- pg_hba (reglas efectivas)"
$PG -c "select type, database, user_name, address, auth_method from pg_hba_file_rules;"
echo "-- Roles: superusuario, BYPASSRLS, login"
$PG -c "select rolname, rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb from pg_roles where rolname !~ '^pg_' order by 1;"
echo "-- Tablas del esquema app: duenio y RLS"
$PG -c "select c.relname, pg_get_userbyid(c.relowner) duenio, c.relrowsecurity rls
  from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='app' and c.relkind='r' order by 1;"
echo "-- Privilegios de app_backend sobre tablas sensibles"
$PG -c "select table_name, string_agg(privilege_type, ',' order by privilege_type) privilegios
  from information_schema.role_table_grants where grantee='app_backend'
  and table_name in ('auditoria','decision','cuenta_historial','solicitud','solicitud_restringida') group by 1 order by 1;"
echo "-- Permisos a PUBLIC en el esquema app"
$PG -c "select count(*) grants_a_public from information_schema.role_table_grants where grantee='PUBLIC' and table_schema='app';"
echo "-- Prueba negativa: app_backend no puede modificar la auditoria (RD-02) ni una solicitud aprobada (RF-14)"
$PG <<'SQL'
begin;
set local role app_backend;
savepoint a; update app.auditoria set hash = 'alterado' where secuencia = 1; rollback to savepoint a;
savepoint b; delete from app.auditoria where secuencia = 1; rollback to savepoint b;
savepoint c; update app.solicitud set fecha_efectiva = fecha_efectiva + 1 where estado = 'en_ejecucion'; rollback to savepoint c;
savepoint d; update app.solicitud set estado = 'pendiente_aprobacion' where estado = 'en_ejecucion'; rollback to savepoint d;
rollback;
SQL

echo
echo "### MariaDB 11.4 (base de GLPI)"
docker exec jml-mariadb-1 sh -c 'mariadb -uglpi -p"$(cat /run/secrets/glpi_db_password)" -t -e "
select version();
show grants for current_user();
show global variables where Variable_name in (\"have_ssl\",\"require_secure_transport\",\"local_infile\",\"secure_file_priv\",
  \"skip_name_resolve\",\"bind_address\",\"tls_version\",\"default_authentication_plugin\",\"log_warnings\",\"general_log\");
select user, host from mysql.user;" 2>&1' | sed -E "s/(IDENTIFIED BY PASSWORD )'[^']+'/\1'<oculto>'/g"
echo "-- Usuarios anonimos o root remoto (si la consulta anterior no tiene permiso, se infiere de los GRANT)"
