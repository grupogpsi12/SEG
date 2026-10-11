-- ADR-028 (revision externa H1): app_owner es duenio del esquema; app_backend solo opera.
-- Se corre UNA vez como `postgres` en cada proyecto de Supabase (desarrollo y entrega), y en la
-- base de la CI. Idempotente. Despues: `python manage.py migrate` como app_owner (contenedor
-- `migrar`), que aplica la migracion 0004 con los permisos minimos de app_backend.
--
--   psql "...postgres..." -v clave_duenio="'<aleatoria: secrets/db_owner_password>'" \
--        -f infra/supabase/duenio-separado.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_owner') THEN
        CREATE ROLE app_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
            CONNECTION LIMIT 3;
    END IF;
END $$;
ALTER ROLE app_owner PASSWORD :clave_duenio;
ALTER ROLE app_owner SET statement_timeout = '120s';
GRANT app_owner TO postgres;  -- para reasignar objetos a su nombre

-- RLS sin politicas (invariante 8) bloquea a anon y authenticated. Mientras app_backend era
-- duenio no lo afectaba; ahora necesita BYPASSRLS para seguir operando sin agregar politicas.
ALTER ROLE app_backend BYPASSRLS;

-- Esquemas: app (produccion) y app_test (pruebas de integracion), si existen.
DO $$
DECLARE esquema text; objeto record;
BEGIN
    FOREACH esquema IN ARRAY ARRAY['app', 'app_test'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = esquema) THEN
            CONTINUE;
        END IF;
        EXECUTE format('ALTER SCHEMA %I OWNER TO app_owner', esquema);
        FOR objeto IN
            SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            -- Las secuencias de columnas identity/serial cambian de duenio con su tabla.
            WHERE n.nspname = esquema AND c.relkind IN ('r', 'v', 'p')
        LOOP
            EXECUTE format('ALTER %s %I.%I OWNER TO app_owner',
                CASE objeto.relkind WHEN 'v' THEN 'VIEW' ELSE 'TABLE' END, esquema, objeto.relname);
        END LOOP;
        FOR objeto IN
            SELECT p.oid::regprocedure AS firma FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = esquema
        LOOP
            EXECUTE format('ALTER FUNCTION %s OWNER TO app_owner', objeto.firma);
        END LOOP;
        EXECUTE format('REVOKE ALL ON SCHEMA %I FROM public, anon, authenticated, service_role', esquema);
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO app_backend', esquema);
    END LOOP;
END $$;
ALTER ROLE app_owner SET search_path = app;
